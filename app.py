import asyncio
import io
import os
import secrets
import time
import urllib.parse
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import requests
import uvicorn
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google_auth_oauthlib.flow import Flow
from pydantic import BaseModel
from pypdf import PdfReader
from sqlalchemy.orm import Session

import config
from ai_agent import generate_personalized_pitch, normalize_single_keyword, parse_resume_text
from db import ColdPitch, Company, OutreachLog, ScoutJob, SessionLocal, User, get_db, init_db
from enricher import deep_enrich_company, is_recruitment_email
from outreach import (
    dispatch_batch_outreach,
    generate_gmail_web_link,
    generate_mailto_link,
)
from scraper_engine import GoogleScraper, is_genuine_company_domain

# In-memory sliding window rate limiter
_rate_limit_store = defaultdict(list)


def enforce_rate_limit(key: str, max_calls: int, window_seconds: int = 60):
    now = time.time()
    recent = [t for t in _rate_limit_store[key] if now - t < window_seconds]
    if len(recent) >= max_calls:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Maximum {max_calls} requests per {window_seconds}s. Please wait a moment."
        )
    recent.append(now)
    _rate_limit_store[key] = recent


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=config.PROJECT_NAME,
    description=config.APP_DESCRIPTOR,
    lifespan=lifespan
)

# Mount static and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Global scraper state
current_scraper: GoogleScraper | None = None
active_task: asyncio.Task | None = None


# --- Request Models ---
class ScrapeRequest(BaseModel):
    keyword: str | None = ""
    city: str | None = ""
    direct_url: str | None = ""
    max_pages: int = 2
    gl: str = "in"
    hl: str = "en"


class BulkEnrichRequest(BaseModel):
    company_ids: list[int]


class PitchGenRequest(BaseModel):
    company_id: int
    target_role: str | None = ""
    candidate_profile: dict[str, Any] | None = None


class BulkPitchRequest(BaseModel):
    company_ids: list[int]
    target_role: str | None = ""
    candidate_profile: dict[str, Any] | None = None


class BatchSendRequest(BaseModel):
    pitch_ids: list[int]
    delay_min: float = 2.0
    delay_max: float = 4.0


class DirectSendRequest(BaseModel):
    pitch_id: int


class DemoLoginRequest(BaseModel):
    as_admin: bool = False
    email: str | None = None


class InvalidateCompanyRequest(BaseModel):
    reason: str | None = "Excluded by Master Admin"


# --- Helper to get or create current user ---
def get_current_user(db: Session, request: Request | None = None) -> User | None:
    email = None
    if request:
        raw_cookie = request.cookies.get("pilot_user_email")
        if raw_cookie:
            verified_email = config.verify_user_email(raw_cookie)
            if verified_email:
                email = verified_email
            elif config.DEV_MODE:
                # In DEV_MODE only, permit plain email if properly formatted
                clean_raw = raw_cookie.strip().strip("\"'").lower()
                if "@" in clean_raw and "." in clean_raw.split("@")[-1]:
                    email = clean_raw

    if not email:
        if config.DEV_MODE:
            email = "demo_user@outreachpilot.ai"
        else:
            return None

    user = db.query(User).filter(User.email == email).first()
    if not user:
        if not config.DEV_MODE:
            return None
        is_admin = config.is_master_admin(email)
        user = User(
            email=email,
            name="Master Admin (Rahul Vora)" if is_admin else "Pilot User",
            target_role="Full-Stack Engineer",
            daily_send_limit=100 if is_admin else 50
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


# --- UI Routes ---
@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(db, request)
    is_logged_in = bool(user and user.oauth_tokens)
    is_master_admin = bool(is_logged_in and config.is_master_admin(user.email))
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "project_name": config.PROJECT_NAME,
            "tagline": config.TAGLINE,
            "app_descriptor": config.APP_DESCRIPTOR,
            "user": user,
            "is_logged_in": is_logged_in,
            "is_master_admin": is_master_admin,
            "master_admin_emails": config.MASTER_ADMIN_EMAILS,
            "google_client_id": config.GOOGLE_CLIENT_ID,
            "dev_mode": config.DEV_MODE,
            "dev_override_email": config.DEV_OVERRIDE_EMAIL
        }
    )


# --- Stage 1: Google Local Lead Scout Endpoints ---
def run_scraper_sync(keyword: str, city: str, direct_url: str, max_pages: int, gl: str, hl: str):
    global current_scraper
    if not current_scraper:
        current_scraper = GoogleScraper(headless=True)
    current_scraper.is_running = True
    try:
        current_scraper.scrape(
            keyword=keyword,
            city=city,
            direct_url=direct_url,
            max_pages=max_pages,
            gl=gl,
            hl=hl
        )
        # Keep running flag active while saving to DB
        current_scraper.is_running = True
        current_scraper.progress = 95
        current_scraper.status_message = f"Saving {len(current_scraper.results)} companies to PostgreSQL..."

        db = SessionLocal()
        clean_keyword = (keyword or "").strip() or "Direct URL"
        clean_city = (city or "").strip().title()
        query_tag = f"{clean_keyword} {clean_city}".strip()
        canonical_kw = normalize_single_keyword(clean_keyword, clean_city) if clean_keyword != "Direct URL" else "Direct Leads"
        seen_domains = set()
        saved_count = 0

        from sqlalchemy.dialects.postgresql import insert as pg_insert

        for item in current_scraper.results:
            domain = item.get("domain", "").strip().lower()
            if not is_genuine_company_domain(domain):
                # Discard companies without an official genuine domain (e.g. .local or missing)
                continue

            # Avoid duplicates within the current scrape batch
            if domain in seen_domains:
                continue
            seen_domains.add(domain)

            stmt = pg_insert(Company).values(
                name=item.get("name", "Unknown"),
                domain=domain,
                website_url=item.get("website_url", ""),
                phone=item.get("phone", ""),
                address=item.get("address", ""),
                location_url=item.get("location_url", ""),
                rating=item.get("rating", 0.0),
                reviews_count=item.get("reviews_count", 0),
                source_query=query_tag,
                search_keyword=clean_keyword,
                city=clean_city,
                normalized_keyword=canonical_kw
            ).on_conflict_do_update(
                index_elements=["domain"],
                set_={
                    "name": item.get("name", "Unknown"),
                    "website_url": item.get("website_url", ""),
                    "phone": item.get("phone", ""),
                    "address": item.get("address", ""),
                    "location_url": item.get("location_url", ""),
                    "rating": item.get("rating", 0.0),
                    "reviews_count": item.get("reviews_count", 0),
                    "source_query": query_tag,
                    "search_keyword": clean_keyword,
                    "city": clean_city,
                    "normalized_keyword": canonical_kw
                }
            )
            db.execute(stmt)
            saved_count += 1

        db.commit()
        db.close()
        current_scraper.progress = 100
        current_scraper.status_message = f"Completed! Successfully saved & updated {saved_count} companies."
    except Exception as e:
        if current_scraper:
            current_scraper.error = str(e)
            current_scraper.status_message = f"Error: {e!s}"
    finally:
        if current_scraper:
            current_scraper.is_running = False


@app.post("/api/scrape")
async def start_scrape(req: ScrapeRequest, db: Session = Depends(get_db)):
    global active_task, current_scraper

    clean_keyword = req.keyword.strip() if req.keyword else "IT Companies"
    clean_city = req.city.strip() if req.city else ""

    # Register ScoutJob in Neon DB
    job = ScoutJob(
        keyword=clean_keyword,
        city=clean_city,
        max_pages=req.max_pages,
        status="QUEUED",
        progress=5,
        status_message=f"Dispatching Cloud Scout & AI Worker for '{clean_keyword}' in '{clean_city}'...",
        logs=[f"[{datetime.utcnow().strftime('%H:%M:%S')}] Job registered in Neon DB. Dispatching GitHub Actions Cloud Runner (7 GB RAM)..."],
        results=[]
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Check if GitHub Actions Cloud Dispatch is configured
    github_token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_PAT_TOKEN")
    github_repo = os.getenv("GITHUB_REPOSITORY", "vorarahul4700/outreachPilot")
    dispatched = False

    if github_token:
        try:
            dispatch_url = f"https://api.github.com/repos/{github_repo}/actions/workflows/cloud_scout.yml/dispatches"
            resp = requests.post(
                dispatch_url,
                headers={
                    "Authorization": f"Bearer {github_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                json={
                    "ref": "main",
                    "inputs": {
                        "job_id": str(job.id),
                        "keyword": clean_keyword,
                        "city": clean_city,
                        "max_pages": str(req.max_pages)
                    }
                },
                timeout=6.0
            )
            if resp.status_code in (200, 204):
                dispatched = True
                print(f"[Cloud Dispatch] Successfully dispatched GitHub Actions workflow for Job #{job.id}")
            else:
                print(f"[Cloud Dispatch Notice] GitHub returned {resp.status_code}: {resp.text}")
        except Exception as dispatch_err:
            print(f"[Cloud Dispatch Error] {dispatch_err}")

    # Fallback to local background thread if cloud runner wasn't dispatched
    if not dispatched:
        current_scraper = GoogleScraper(headless=True)
        current_scraper.is_running = True
        current_scraper.progress = 5
        current_scraper.status_message = f"Running scraper locally for {clean_keyword} {clean_city}..."

        loop = asyncio.get_event_loop()
        active_task = loop.run_in_executor(
            None,
            run_scraper_sync,
            clean_keyword,
            clean_city,
            req.direct_url,
            req.max_pages,
            req.gl,
            req.hl
        )

    return {
        "status": "started",
        "job_id": job.id,
        "mode": "cloud_github_actions" if dispatched else "local_thread",
        "message": "Scouting and AI Enrichment dispatched!"
    }


@app.get("/api/progress")
async def get_progress(job_id: int = None, db: Session = Depends(get_db)):
    # 1. Check for specific requested job_id in Neon DB
    if job_id:
        job = db.query(ScoutJob).filter(ScoutJob.id == job_id).first()
        if job:
            return {
                "is_running": job.status in ("QUEUED", "RUNNING"),
                "progress": job.progress,
                "status_message": job.status_message,
                "logs": (job.logs or [])[-15:],
                "total_results": len(job.results or []),
                "results": (job.results or [])[-50:],
                "error": job.error,
                "job_id": job.id
            }

    # 2. Check for any active cloud ScoutJob in Neon DB
    recent_job = (
        db.query(ScoutJob)
        .filter(ScoutJob.status.in_(["QUEUED", "RUNNING"]))
        .order_by(ScoutJob.id.desc())
        .first()
    )
    if recent_job:
        return {
            "is_running": True,
            "progress": recent_job.progress,
            "status_message": recent_job.status_message,
            "logs": (recent_job.logs or [])[-15:],
            "total_results": len(recent_job.results or []),
            "results": (recent_job.results or [])[-50:],
            "error": recent_job.error,
            "job_id": recent_job.id
        }

    # 3. Fallback to local in-memory scraper
    if not current_scraper:
        return {"is_running": False, "progress": 0, "logs": [], "total_results": 0, "results": []}
    return {
        "is_running": current_scraper.is_running,
        "progress": current_scraper.progress,
        "status_message": current_scraper.status_message,
        "logs": current_scraper.logs[-15:],
        "total_results": len(current_scraper.results),
        "results": current_scraper.results[-50:],
        "error": current_scraper.error
    }


@app.post("/api/stop")
async def stop_scrape():
    if current_scraper and current_scraper.is_running:
        current_scraper.is_running = False
        return {"status": "stopped", "message": "Scrape stopping requested."}
    return {"status": "idle", "message": "No active scrape job."}


@app.get("/api/companies")
async def get_companies(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(db, request)
    is_admin = bool(user and user.oauth_tokens and config.is_master_admin(user.email))

    base_query = (
        db.query(Company)
        .filter(~Company.domain.like("%.local"))
        .filter(Company.domain.contains("."))
    )

    invalid_count = base_query.filter(Company.is_invalid.is_(True)).count()

    # If NOT master admin, NEVER expose invalid companies to regular users
    if not is_admin:
        query = base_query.filter(Company.is_invalid.is_(False))
    else:
        # Master Admin receives all genuine companies with is_invalid flag
        query = base_query

    companies = query.order_by(Company.id.desc()).all()
    if user and user.oauth_tokens:
        sent_logs = {
            log.company_id: log.sent_at
            for log in db.query(OutreachLog)
            .filter(OutreachLog.status == "SENT", OutreachLog.user_id == user.id)
            .all()
        }
    else:
        sent_logs = {}

    out = []
    for c in companies:
        emails = [e.email_address for e in c.emails]
        profile = {
            "summary": c.profile.summary_short if c.profile else "",
            "detailed_analysis": c.profile.detailed_analysis if c.profile else "",
            "industry": c.profile.industry if c.profile else "",
            "tech_stack": c.profile.tech_stack if c.profile else [],
            "services": c.profile.services if c.profile else [],
            "tone": c.profile.tone if c.profile else "Professional"
        } if c.profile else None

        sent_time = sent_logs.get(c.id)

        maps_query = f"{c.name} {c.address or c.source_query or ''}".strip()
        maps_url = c.location_url or f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(maps_query)}"

        out.append({
            "id": c.id,
            "name": c.name,
            "domain": c.domain,
            "website_url": c.website_url,
            "location_url": maps_url,
            "phone": c.phone,
            "address": c.address or "",
            "source_query": c.source_query or "General Leads",
            "search_keyword": c.search_keyword or c.source_query or "General Leads",
            "city": c.city or "",
            "normalized_keyword": c.normalized_keyword or c.search_keyword or "General Leads",
            "rating": c.rating,
            "reviews_count": c.reviews_count,
            "is_enriched": c.is_enriched,
            "is_invalid": bool(c.is_invalid),
            "invalid_reason": c.invalid_reason or "",
            "invalid_at": c.invalid_at.strftime("%b %d, %Y %I:%M %p") if c.invalid_at else None,
            "emails": emails,
            "profile": profile,
            "already_contacted": bool(sent_time),
            "contacted_at": sent_time.strftime("%b %d, %Y %I:%M %p") if sent_time else None
        })

    canonical_keywords = sorted(list(set(c.normalized_keyword for c in companies if c.normalized_keyword and c.normalized_keyword.strip())))
    cities = sorted(list(set(c.city for c in companies if c.city and c.city.strip())))
    return {
        "companies": out,
        "total_count": len(out),
        "invalid_count": invalid_count if is_admin else 0,
        "is_master_admin": is_admin,
        "available_keywords": canonical_keywords,
        "available_cities": cities
    }


# --- Stage 2: Deep Subpage Crawler & AI Enrichment (Login Gated) ---
@app.get("/api/auth/status")
async def auth_status(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(db, request)
    is_logged_in = bool(user and user.oauth_tokens)
    is_master = bool(is_logged_in and config.is_master_admin(user.email))
    return {
        "is_logged_in": is_logged_in,
        "email": user.email if is_logged_in else None,
        "name": user.name if is_logged_in else None,
        "picture": user.picture if is_logged_in else None,
        "is_master_admin": is_master,
        "master_admin_emails": config.MASTER_ADMIN_EMAILS,
        "dev_mode": config.DEV_MODE
    }


@app.post("/auth/demo/login")
async def demo_login(
    payload: DemoLoginRequest | None = None,
    db: Session = Depends(get_db)
):
    # Backdoor & Privilege Escalation Mitigation: strictly forbidden outside DEV_MODE
    if not config.DEV_MODE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo sandbox login is strictly disabled in production mode."
        )

    is_admin_req = payload.as_admin if payload else False
    req_email = (payload.email.strip().lower() if payload and payload.email else None)

    if is_admin_req or (req_email and config.is_master_admin(req_email)):
        target_email = req_email if (req_email and config.is_master_admin(req_email)) else "vorarahul111@gmail.com"
        name = "Master Admin (Rahul Vora)"
    elif req_email:
        target_email = req_email
        name = "Verified User"
    else:
        target_email = "demo_user@outreachpilot.ai"
        name = "Verified Pilot User"

    user = db.query(User).filter(User.email == target_email).first()
    if not user:
        is_admin = config.is_master_admin(target_email)
        user = User(
            email=target_email,
            name=name,
            target_role="Full-Stack Engineer",
            daily_send_limit=100 if is_admin else 50
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    user.oauth_tokens = config.encrypt_tokens({
        "token": "sandbox_demo_token",
        "type": "sandbox",
        "email": target_email
    })
    user.name = name
    db.commit()

    resp = JSONResponse(content={
        "success": True,
        "is_logged_in": True,
        "email": user.email,
        "name": user.name,
        "is_master_admin": config.is_master_admin(user.email)
    })
    signed_cookie = config.sign_user_email(user.email)
    resp.set_cookie(key="pilot_user_email", value=signed_cookie, path="/", httponly=True, samesite="lax", max_age=86400 * 30)
    return resp


@app.post("/auth/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(db, request)
    if user:
        user.oauth_tokens = None
        db.commit()
    resp = JSONResponse(content={"success": True, "is_logged_in": False})
    resp.delete_cookie(key="pilot_user_email", path="/")
    return resp


@app.post("/api/companies/{company_id}/invalidate")
async def invalidate_company(
    company_id: int,
    req_body: InvalidateCompanyRequest | None = None,
    request: Request = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(db, request)
    if not (user and user.oauth_tokens and config.is_master_admin(user.email)):
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Only Master Admin can invalidate/delete companies."
        )

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    company.is_invalid = True
    company.invalid_at = datetime.utcnow()
    company.invalid_reason = (req_body.reason if req_body and req_body.reason else "Excluded by Master Admin")
    db.commit()

    return {
        "success": True,
        "message": f"'{company.name}' marked as invalid and excluded from user views.",
        "company_id": company.id,
        "is_invalid": True
    }


@app.post("/api/companies/{company_id}/restore")
async def restore_company(
    company_id: int,
    request: Request = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(db, request)
    if not (user and user.oauth_tokens and config.is_master_admin(user.email)):
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Only Master Admin can restore companies."
        )

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    company.is_invalid = False
    company.invalid_at = None
    company.invalid_reason = None
    db.commit()

    return {
        "success": True,
        "message": f"'{company.name}' restored to active genuine leads.",
        "company_id": company.id,
        "is_invalid": False
    }


@app.post("/api/companies/{company_id}/enrich")
async def enrich_single_company(
    company_id: int,
    force_refresh: bool = False,
    request: Request = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(db, request)
    if not user.oauth_tokens:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please connect your Google account or log in to run Deep Enrichment."
        )

    client_id = f"{user.id}_{request.client.host if request and request.client else 'unknown'}"
    enforce_rate_limit(f"enrich_single_{client_id}", max_calls=20, window_seconds=60)

    result = await deep_enrich_company(company_id=company_id, db=db, force_refresh=force_refresh)
    return result


@app.post("/api/companies/bulk-enrich")
async def enrich_bulk_companies(
    req: BulkEnrichRequest,
    request: Request = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(db, request)
    if not user.oauth_tokens:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please connect your Google account or log in to run Deep Enrichment."
        )

    client_id = f"{user.id}_{request.client.host if request and request.client else 'unknown'}"
    enforce_rate_limit(f"bulk_enrich_{client_id}", max_calls=10, window_seconds=60)

    # Cap maximum concurrent company batch size to prevent resource exhaustion
    target_ids = req.company_ids[:50]
    semaphore = asyncio.Semaphore(8)  # 8 concurrent enrichment workers

    async def worker(cid: int):
        async with semaphore:
            worker_db = SessionLocal()
            try:
                return await deep_enrich_company(company_id=cid, db=worker_db, force_refresh=False)
            except Exception as e:
                return {"error": str(e), "success": False, "company_id": cid}
            finally:
                worker_db.close()

    tasks = [worker(cid) for cid in target_ids]
    results = await asyncio.gather(*tasks)
    return {"total": len(target_ids), "results": results}


# --- Stage 3: In-Memory Resume Ingestion & Parsing ---
MAX_RESUME_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_PDF_PAGES = 15


@app.get("/api/resume/profile")
async def get_candidate_profile(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(db, request)
    if not user:
        return {"profile": None, "resume_link": "", "target_role": ""}
    return {
        "profile": user.resume_summary,
        "resume_link": user.resume_link or "",
        "target_role": user.target_role or ""
    }


@app.post("/api/resume/upload")
async def upload_resume(
    file: UploadFile = File(None),
    resume_link: str = Form(""),
    target_role: str = Form(""),
    request: Request = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(db, request)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please sign in to save your candidate profile."
        )

    client_id = f"{user.id}_{request.client.host if request and request.client else 'unknown'}"
    enforce_rate_limit(f"resume_upload_{client_id}", max_calls=15, window_seconds=60)

    # Save portfolio/resume link if provided
    if resume_link is not None:
        user.resume_link = resume_link.strip()

    parsed_profile = user.resume_summary or {}

    # If file was attached, process and store local copy
    if file and file.filename:
        contents = await file.read()
        if len(contents) > MAX_RESUME_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File too large. Maximum resume size is 5MB."
            )

        filename_lower = (file.filename or "").lower()
        allowed_exts = (".pdf", ".txt", ".md")
        if not any(filename_lower.endswith(ext) for ext in allowed_exts):
            raise HTTPException(
                status_code=400,
                detail="Unsupported file format. Please upload a PDF, TXT, or MD resume."
            )

        raw_text = ""
        if filename_lower.endswith(".pdf"):
            try:
                reader = PdfReader(io.BytesIO(contents))
                if len(reader.pages) > MAX_PDF_PAGES:
                    raise HTTPException(
                        status_code=400,
                        detail=f"PDF exceeds maximum page limit of {MAX_PDF_PAGES} pages."
                    )
                for page in reader.pages:
                    raw_text += (page.extract_text() or "") + "\n"
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to parse PDF: {e!s}")

            # Save local copy in uploads/resumes for direct OAuth attachment
            import os
            os.makedirs(os.path.join("uploads", "resumes"), exist_ok=True)
            save_path = os.path.join("uploads", "resumes", f"user_{user.id}_resume.pdf")
            try:
                with open(save_path, "wb") as f_out:
                    f_out.write(contents)
            except Exception as save_err:
                print(f"[Upload Warning] Could not save resume PDF: {save_err}")
        else:
            raw_text = contents.decode("utf-8", errors="ignore")

        parsed_profile = parse_resume_text(resume_text=raw_text, target_role=target_role)

    if target_role:
        user.target_role = target_role
    elif parsed_profile.get("target_role"):
        user.target_role = parsed_profile.get("target_role")

    if user.resume_link:
        parsed_profile["resume_link"] = user.resume_link

    user.resume_summary = parsed_profile
    db.commit()

    return {
        "success": True,
        "message": "Candidate profile updated successfully.",
        "profile": parsed_profile,
        "resume_link": user.resume_link
    }


# --- Stage 4: Personalized 1-to-1 Pitch Generator ---
@app.post("/api/pitch/generate")
async def generate_single_pitch(
    req: PitchGenRequest,
    request: Request = None,
    db: Session = Depends(get_db)
):
    company = db.query(Company).filter(Company.id == req.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    user = get_current_user(db, request)
    if not user or not user.oauth_tokens:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please connect your Google account to generate personalized pitches."
        )

    client_id = f"{user.id}_{request.client.host if request and request.client else 'unknown'}"
    enforce_rate_limit(f"pitch_gen_{client_id}", max_calls=30, window_seconds=60)
    cand_profile = req.candidate_profile or user.resume_summary or {
        "full_name": user.name or "Candidate",
        "target_role": req.target_role or user.target_role or "Software Engineer",
        "top_skills": ["Python", "FastAPI", "React", "PostgreSQL"],
        "key_achievements": ["Built scalable web services and automated data workflows"]
    }
    if user.resume_link and not cand_profile.get("resume_link"):
        cand_profile["resume_link"] = user.resume_link

    comp_profile_data = {
        "summary": company.profile.summary_short if company.profile else "",
        "industry": company.profile.industry if company.profile else "Tech",
        "tech_stack": company.profile.tech_stack if company.profile else [],
        "tone": company.profile.tone if company.profile else "Professional"
    }

    target_email = None
    if company.emails:
        primary_emails = [e.email_address for e in company.emails if getattr(e, "is_primary", False)]
        if primary_emails:
            target_email = primary_emails[0]
        else:
            for e in company.emails:
                if is_recruitment_email(e.email_address):
                    target_email = e.email_address
                    break
            if not target_email:
                target_email = company.emails[0].email_address
    if not target_email:
        target_email = f"contact@{company.domain}"

    pitch_data = generate_personalized_pitch(
        candidate_profile=cand_profile,
        company_name=company.name,
        company_profile=comp_profile_data
    )

    existing_pitch = db.query(ColdPitch).filter(
        ColdPitch.company_id == company.id,
        ColdPitch.user_id == user.id
    ).first()

    if existing_pitch:
        existing_pitch.subject_line = pitch_data.get("subject_line", "")
        existing_pitch.email_body = pitch_data.get("email_body", "")
        existing_pitch.cover_letter = pitch_data.get("cover_letter", "")
        existing_pitch.matched_skills = pitch_data.get("matched_skills", [])
        existing_pitch.target_email = target_email
        db.commit()
        pitch_obj = existing_pitch
    else:
        pitch_obj = ColdPitch(
            company_id=company.id,
            user_id=user.id,
            target_email=target_email,
            subject_line=pitch_data.get("subject_line", ""),
            email_body=pitch_data.get("email_body", ""),
            cover_letter=pitch_data.get("cover_letter", ""),
            matched_skills=pitch_data.get("matched_skills", []),
            status="DRAFT"
        )
        db.add(pitch_obj)
        db.commit()
        db.refresh(pitch_obj)

    gmail_web_url = generate_gmail_web_link(
        to_email=target_email,
        subject=pitch_obj.subject_line,
        body=pitch_obj.email_body
    )
    mailto_url = generate_mailto_link(
        to_email=target_email,
        subject=pitch_obj.subject_line,
        body=pitch_obj.email_body
    )

    return {
        "success": True,
        "pitch_id": pitch_obj.id,
        "company_name": company.name,
        "target_email": target_email,
        "subject_line": pitch_obj.subject_line,
        "email_body": pitch_obj.email_body,
        "cover_letter": pitch_obj.cover_letter,
        "matched_skills": pitch_obj.matched_skills,
        "gmail_web_url": gmail_web_url,
        "mailto_url": mailto_url
    }


# --- Stage 5: Multi-Tier Outreach & Tracking ---
@app.post("/api/pitch/{pitch_id}/log-sent")
async def log_sent_manual(
    pitch_id: int,
    method: str = "GMAIL_WEB",
    request: Request = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(db, request)
    pitch = db.query(ColdPitch).filter(ColdPitch.id == pitch_id).first()
    if not pitch:
        raise HTTPException(status_code=404, detail="Pitch not found")

    # IDOR Protection: verify user owns this pitch unless Master Admin
    if not config.is_master_admin(user.email) and pitch.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not own this cold pitch record."
        )

    pitch.status = "SENT"
    pitch.sent_at = datetime.utcnow()
    pitch.delivery_method = method

    log_entry = OutreachLog(
        company_id=pitch.company_id,
        user_id=pitch.user_id,
        recipient_email=pitch.target_email or "unknown",
        subject=pitch.subject_line,
        email_body=pitch.email_body,
        delivery_method=method,
        status="SENT",
        sent_at=datetime.utcnow()
    )
    db.add(log_entry)
    db.commit()
    return {"success": True, "message": "Outreach timestamp logged successfully."}


@app.post("/api/pitch/bulk-send")
async def bulk_send_outreach(
    req: BatchSendRequest,
    request: Request = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(db, request)
    if not user or not user.oauth_tokens:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please connect your Google account to perform direct outreach."
        )

    result = await dispatch_batch_outreach(
        pitch_ids=req.pitch_ids,
        user=user,
        db=db,
        delay_min=req.delay_min,
        delay_max=req.delay_max
    )
    return result


@app.get("/api/outreach/logs")
async def get_outreach_logs(request: Request = None, db: Session = Depends(get_db)):
    user = get_current_user(db, request)
    if not user or not user.oauth_tokens:
        return {"logs": []}

    query = db.query(OutreachLog)

    # Multi-tenant isolation: standard users view only their own logs
    if not config.is_master_admin(user.email):
        query = query.filter(OutreachLog.user_id == user.id)

    logs = query.order_by(OutreachLog.sent_at.desc()).limit(100).all()
    return {
        "logs": [{
            "id": log_item.id,
            "company_id": log_item.company_id,
            "company_name": log_item.company.name if log_item.company else "Unknown",
            "recipient_email": log_item.recipient_email,
            "subject": log_item.subject,
            "email_body": log_item.email_body or "",
            "delivery_method": log_item.delivery_method,
            "status": log_item.status,
            "sent_at": log_item.sent_at.strftime("%b %d, %Y %I:%M:%S %p") if log_item.sent_at else ""
        } for log_item in logs]
    }


@app.get("/api/outreach/sent/{company_id}")
async def get_sent_email_for_company(company_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(db, request)
    if not user or not user.oauth_tokens:
        raise HTTPException(status_code=401, detail="Authentication required.")

    query = db.query(OutreachLog).filter(OutreachLog.company_id == company_id, OutreachLog.status == "SENT")
    if not config.is_master_admin(user.email):
        query = query.filter(OutreachLog.user_id == user.id)

    log = query.order_by(OutreachLog.sent_at.desc()).first()
    if not log:
        # Fallback to pitch if log not found
        pitch = db.query(ColdPitch).filter(ColdPitch.company_id == company_id).first()
        if pitch and (config.is_master_admin(user.email) or pitch.user_id == user.id):
            return {
                "found": True,
                "company_name": pitch.company.name if pitch.company else "Unknown",
                "recipient_email": pitch.target_email,
                "subject": pitch.subject_line,
                "email_body": pitch.email_body,
                "delivery_method": pitch.delivery_method or "SENT",
                "sent_at": pitch.sent_at.strftime("%b %d, %Y %I:%M:%S %p") if pitch.sent_at else ""
            }
        return {"found": False}

    return {
        "found": True,
        "company_name": log.company.name if log.company else "Unknown",
        "recipient_email": log.recipient_email,
        "subject": log.subject,
        "email_body": log.email_body or "",
        "delivery_method": log.delivery_method,
        "sent_at": log.sent_at.strftime("%b %d, %Y %I:%M:%S %p") if log.sent_at else ""
    }


def get_effective_redirect_uri(request: Request) -> str:
    """
    Computes the accurate OAuth callback URI based on current request context.
    Prevents cross-domain redirects from Render back to localhost.
    """
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc

    # If running on Render or any non-local public domain:
    if host and not host.startswith("localhost") and not host.startswith("127.0.0.1"):
        return f"{proto}://{host}/auth/google/callback"

    # Otherwise return local configured redirect URI
    return config.GOOGLE_REDIRECT_URI or "http://localhost:8000/auth/google/callback"


# --- Google OAuth Flow ---
@app.get("/auth/google/login")
async def google_login(request: Request):
    if not config.GOOGLE_CLIENT_ID or not config.GOOGLE_CLIENT_SECRET:
        return JSONResponse(status_code=400, content={"error": "Google OAuth credentials not configured in .env."})

    redirect_uri = get_effective_redirect_uri(request)
    client_config = {
        "web": {
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri]
        }
    }
    flow = Flow.from_client_config(
        client_config,
        scopes=[
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/gmail.send"
        ],
        autogenerate_code_verifier=False
    )
    flow.redirect_uri = redirect_uri

    # OAuth CSRF Protection: Generate secure unguessable state token
    oauth_state = secrets.token_urlsafe(32)
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="select_account",
        state=oauth_state
    )
    response = RedirectResponse(authorization_url)
    is_secure = request.url.scheme == "https"
    response.set_cookie(
        key="oauth_state",
        value=oauth_state,
        path="/",
        httponly=True,
        samesite="lax",
        secure=is_secure,
        max_age=600
    )
    return response


@app.get("/auth/google/callback")
async def google_callback(code: str, request: Request, db: Session = Depends(get_db)):
    try:
        # OAuth CSRF Verification
        stored_state = request.cookies.get("oauth_state")
        incoming_state = request.query_params.get("state")
        if stored_state and incoming_state:
            if not secrets.compare_digest(stored_state, incoming_state):
                print(f"[OAuth Warning] State mismatch: stored={stored_state}, incoming={incoming_state}")
                return RedirectResponse(url="/?auth_error=State+mismatch+CSRF+detected")
        elif not incoming_state:
            return RedirectResponse(url="/?auth_error=Missing+OAuth+state+parameter")
        else:
            print("[OAuth Notice] oauth_state cookie was not returned by browser. Proceeding with verified Google exchange.")

        redirect_uri = get_effective_redirect_uri(request)
        client_config = {
            "web": {
                "client_id": config.GOOGLE_CLIENT_ID,
                "client_secret": config.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri]
            }
        }
        flow = Flow.from_client_config(
            client_config,
            scopes=[
                "openid",
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/userinfo.profile",
                "https://www.googleapis.com/auth/gmail.send"
            ],
            autogenerate_code_verifier=False
        )
        flow.redirect_uri = redirect_uri
        flow.fetch_token(code=code)
        credentials = flow.credentials

        user_email = None
        if hasattr(credentials, "id_token") and credentials.id_token:
            if isinstance(credentials.id_token, dict):
                user_email = credentials.id_token.get("email")
            else:
                import google.oauth2.id_token
                from google.auth.transport import requests as google_requests
                try:
                    id_info = google.oauth2.id_token.verify_oauth2_token(
                        credentials.id_token, google_requests.Request(), config.GOOGLE_CLIENT_ID
                    )
                    user_email = id_info.get("email")
                except Exception as id_err:
                    print(f"[OAuth Warning] verify_oauth2_token failed: {id_err}")

        # Fallback directly to Google Userinfo API via authorized credentials
        if not user_email:
            try:
                from googleapiclient.discovery import build
                user_service = build("oauth2", "v2", credentials=credentials)
                user_info = user_service.userinfo().get().execute()
                user_email = user_info.get("email")
            except Exception as user_err:
                print(f"[OAuth Warning] Google userinfo API failed: {user_err}")

        if not user_email:
            return RedirectResponse(url="/?auth_error=Could+not+retrieve+verified+email+from+Google")

        user_email_clean = user_email.strip().lower()
        user = db.query(User).filter(User.email == user_email_clean).first()
        if not user:
            is_admin = config.is_master_admin(user_email_clean)
            user = User(
                email=user_email_clean,
                name="Master Admin (Rahul Vora)" if is_admin else "Pilot User",
                target_role="Full-Stack Engineer",
                daily_send_limit=100 if is_admin else 50
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        # Encrypt OAuth credentials before persisting in PostgreSQL
        user.oauth_tokens = config.encrypt_tokens({
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret
        })
        db.commit()

        response = RedirectResponse(url="/?auth_success=1")
        signed_cookie = config.sign_user_email(user.email)
        response.set_cookie(
            key="pilot_user_email",
            value=signed_cookie,
            path="/",
            httponly=True,
            samesite="lax",
            max_age=86400 * 30
        )
        response.delete_cookie(key="oauth_state", path="/")
        return response
    except Exception as e:
        return RedirectResponse(url=f"/?auth_error={urllib.parse.quote(str(e))}")


if __name__ == "__main__":
    print("\n[OutreachPilot] Running! Open in browser: http://localhost:8000 or http://127.0.0.1:8000\n")
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)

