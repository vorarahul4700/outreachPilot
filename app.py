import asyncio
import copy
import io
import json
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
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google_auth_oauthlib.flow import Flow
from pydantic import BaseModel
from pypdf import PdfReader
from sqlalchemy import String, func, or_
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

# In-memory cached filter metadata (60s TTL)
_filter_cache = {
    "timestamp": 0.0,
    "data": None
}

def invalidate_filter_cache():
    global _filter_cache
    _filter_cache["timestamp"] = 0.0
    _filter_cache["data"] = None


import config
from ai_agent import (
    generate_personalized_pitch,
    normalize_single_keyword,
    parse_resume_text,
)
from db import (
    ColdPitch,
    Company,
    CompanyEmail,
    CompanyProfile,
    OutreachLog,
    ScoutJob,
    SessionLocal,
    User,
    get_db,
    init_db,
)
from enricher import deep_enrich_company, is_recruitment_email
from outreach import (
    dispatch_batch_outreach,
    generate_gmail_web_link,
    generate_mailto_link,
    send_via_google_oauth,
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


# --- Maintenance Mode Middleware ---
@app.middleware("http")
async def maintenance_mode_middleware(request: Request, call_next):
    if config.is_maintenance_mode():
        path = request.url.path
        # Allowed routes: only landing page, maintenance page, static assets, and favicon
        is_allowed = (
            path in ("/", "/home", "/landing", "/maintenance", "/privacy", "/terms", "/favicon.ico")
            or path.startswith("/static/")
        )
        if not is_allowed:
            # Handle API endpoints and JSON requests
            is_api = (
                path.startswith("/api/")
                or path.startswith("/auth/")
                or "application/json" in request.headers.get("accept", "").lower()
            )
            if is_api:
                return JSONResponse(
                    status_code=503,
                    content={
                        "success": False,
                        "maintenance": True,
                        "error": "Service Unavailable",
                        "message": "OutreachPilot is currently undergoing scheduled platform maintenance. Please check back shortly."
                    }
                )
            # Browser routes (e.g. /app, /workspace, or others) redirect to /maintenance
            return RedirectResponse(url="/maintenance", status_code=307)

    response = await call_next(request)
    return response


# --- Global Exception Handlers for 4xx and 5xx Status Codes ---
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    is_api = (
        request.url.path.startswith("/api/")
        or request.url.path.startswith("/auth/")
        or "application/json" in request.headers.get("accept", "").lower()
    )
    if is_api:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "status_code": exc.status_code,
                "error": exc.detail if isinstance(exc.detail, str) else "HTTP Error",
                "detail": exc.detail,
                "path": request.url.path,
            },
        )

    status_code = exc.status_code
    template_name = "404.html" if status_code == 404 else "error.html"
    title = (
        "Page Not Found"
        if status_code == 404
        else (
            "Access Restricted"
            if status_code == 403
            else (
                "Authentication Required"
                if status_code == 401
                else ("Rate Limit Exceeded" if status_code == 429 else f"HTTP {status_code} Error")
            )
        )
    )
    message = (
        "The route you are trying to reach does not exist in OutreachPilot."
        if status_code == 404
        else (
            "Master Admin authorization is required to access this area."
            if status_code == 403
            else (
                "You must be authenticated to view this resource."
                if status_code == 401
                else (
                    "Too many requests. Please pause a moment before trying again."
                    if status_code == 429
                    else str(exc.detail)
                )
            )
        )
    )
    return templates.TemplateResponse(
        request=request,
        name=template_name,
        context={
            "project_name": config.PROJECT_NAME,
            "status_code": status_code,
            "title": title,
            "message": message,
            "path": request.url.path,
        },
        status_code=status_code,
    )


@app.exception_handler(Exception)
async def custom_general_exception_handler(request: Request, exc: Exception):
    print(f"[Internal Server Error] Uncaught exception on {request.method} {request.url.path}: {exc}")
    is_api = (
        request.url.path.startswith("/api/")
        or request.url.path.startswith("/auth/")
        or "application/json" in request.headers.get("accept", "").lower()
    )
    if is_api:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "status_code": 500,
                "error": "Internal Server Error",
                "detail": "An unexpected error occurred while processing your request.",
                "path": request.url.path,
            },
        )
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "project_name": config.PROJECT_NAME,
            "status_code": 500,
            "title": "Internal Server Error",
            "message": "Our telemetry detected an internal system issue while processing this request.",
            "path": request.url.path,
        },
        status_code=500,
    )


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
    force_regenerate: bool = False


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


class BulkInvalidateCompaniesRequest(BaseModel):
    company_ids: list[int]
    reason: str | None = "Excluded by Master Admin"


class BulkRestoreCompaniesRequest(BaseModel):
    company_ids: list[int]


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
        try:
            is_admin = config.is_master_admin(email)
            user = User(
                email=email,
                name="Master Admin" if is_admin else "Pilot User",
                target_role="",
                daily_send_limit=100 if is_admin else 50
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        except Exception:
            db.rollback()
            user = db.query(User).filter(User.email == email).first()
    return user


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.ico")


# --- UI Routes ---
@app.get("/", response_class=HTMLResponse)
@app.get("/home", response_class=HTMLResponse)
async def landing_page(request: Request, db: Session = Depends(get_db)):
    """Dedicated craft-first Landing Home Page for OutreachPilot"""
    user = get_current_user(db, request)
    is_logged_in = bool(user and user.oauth_tokens)
    return templates.TemplateResponse(
        request=request,
        name="landing.html",
        context={
            "project_name": config.PROJECT_NAME,
            "tagline": config.TAGLINE,
            "app_descriptor": config.APP_DESCRIPTOR,
            "user": user,
            "is_logged_in": is_logged_in,
            "google_client_id": config.GOOGLE_CLIENT_ID,
            "dev_mode": config.DEV_MODE,
        }
    )


@app.get("/landing")
async def redirect_landing_to_home():
    return RedirectResponse(url="/", status_code=301)


@app.get("/app", response_class=HTMLResponse)
@app.get("/workspace", response_class=HTMLResponse)
async def workspace_page(request: Request, db: Session = Depends(get_db)):
    """Original Scraping Logic & Outreach Workspace Directory"""
    if config.is_maintenance_mode():
        return RedirectResponse(url="/maintenance", status_code=307)
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
            "user": user if is_logged_in else None,
            "is_logged_in": is_logged_in,
            "is_master_admin": is_master_admin,
            "google_client_id": config.GOOGLE_CLIENT_ID,
            "dev_mode": config.DEV_MODE,
        }
    )


@app.get("/maintenance", response_class=HTMLResponse)
async def maintenance_page(request: Request):
    """Dedicated maintenance page displayed when maintenance mode is active"""
    if not config.is_maintenance_mode():
        return RedirectResponse(url="/app")
    return templates.TemplateResponse(
        request=request,
        name="maintenance.html",
        context={
            "project_name": config.PROJECT_NAME,
            "title": "Under Scheduled Maintenance",
        },
        status_code=503
    )


@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    """Public Privacy Policy required by Google OAuth API verification"""
    return templates.TemplateResponse(
        request=request,
        name="privacy.html",
        context={"project_name": config.PROJECT_NAME}
    )


@app.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request):
    """Public Terms of Service required by Google OAuth API verification"""
    return templates.TemplateResponse(
        request=request,
        name="terms.html",
        context={"project_name": config.PROJECT_NAME}
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

    clean_keyword = req.keyword.strip() if req.keyword else ""
    clean_city = req.city.strip() if req.city else ""
    clean_url = req.direct_url.strip() if req.direct_url else ""

    if not clean_url:
        if not clean_keyword:
            return {"status": "error", "message": "Target Keyword / Industry is required."}
        if not clean_city:
            return {"status": "error", "message": "City / Location is required."}
    else:
        clean_keyword = clean_keyword or "Direct URL"

    # Register ScoutJob in Neon DB
    job = ScoutJob(
        keyword=clean_keyword,
        city=clean_city,
        max_pages=req.max_pages,
        status="QUEUED",
        progress=5,
        status_message=f"Starting search for verified businesses: '{clean_keyword}' in '{clean_city}'...",
        logs=[f"[{datetime.utcnow().strftime('%H:%M:%S')}] Search requested. Initializing cloud search engine..."],
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


@app.get("/api/companies/filters")
async def get_companies_filters(request: Request, db: Session = Depends(get_db)):
    """Cached filter metadata (tech stacks, cities, and aggregate metric counts)"""
    global _filter_cache
    now = time.time()
    try:
        user = get_current_user(db, request)
        is_admin = bool(user and config.is_master_admin(user.email))

        base_query = (
            db.query(Company)
            .filter(~Company.domain.like("%.local"))
            .filter(Company.domain.contains("."))
        )

        # Pitched / contacted count is strictly PER-USER and ONLY available when logged in
        user_contacted_count = None
        if user:
            sent_subq = db.query(OutreachLog.company_id).filter(
                OutreachLog.status == "SENT",
                OutreachLog.user_id == user.id
            ).distinct()
            user_contacted_count = base_query.filter(Company.is_invalid.is_(False), Company.id.in_(sent_subq)).count()

        if _filter_cache.get("data") and (now - _filter_cache.get("timestamp", 0) < 60):
            cached = copy.deepcopy(_filter_cache["data"])
            cached["is_master_admin"] = is_admin
            if "stats" in cached and isinstance(cached["stats"], dict):
                cached["stats"]["contacted"] = user_contacted_count
                cached["stats"]["is_logged_in"] = bool(user)
            return cached

        total_valid = base_query.filter(Company.is_invalid.is_(False)).count()
        invalid_count = base_query.filter(Company.is_invalid.is_(True)).count()
        enriched_count = base_query.filter(Company.is_invalid.is_(False), Company.is_enriched.is_(True)).count()

        emails_subq = db.query(CompanyEmail.company_id).distinct()
        with_emails_count = base_query.filter(Company.is_invalid.is_(False), Company.id.in_(emails_subq)).count()

        # Cities aggregation
        cities_map = defaultdict(int)
        for (c_city,) in db.query(Company.city).filter(Company.is_invalid.is_(False), Company.city.isnot(None), Company.city != "").all():
            if c_city:
                clean = c_city.strip()
                if clean:
                    norm = clean.title()
                    cities_map[norm] += 1

        sorted_cities = [
            {"name": city_name, "count": count}
            for city_name, count in sorted(cities_map.items(), key=lambda x: x[0])
        ]

        # Tech stack aggregation
        tech_map = defaultdict(int)
        for (stack,) in db.query(CompanyProfile.tech_stack).filter(CompanyProfile.tech_stack.isnot(None)).all():
            items = []
            if isinstance(stack, list):
                items = stack
            elif isinstance(stack, str):
                try:
                    parsed = json.loads(stack)
                    if isinstance(parsed, list):
                        items = parsed
                    else:
                        items = [s.strip() for s in stack.split(",") if s.strip()]
                except Exception:
                    items = [s.strip() for s in stack.split(",") if s.strip()]
            for t in items:
                if t and isinstance(t, str):
                    clean = t.strip()
                    if clean:
                        key = clean.lower()
                        if key == ".net" or key.startswith(".net "):
                            display = ".NET" + clean[4:]
                        elif key in ["aws", "php", "html", "css", "sql", "api", "seo", "crm", "erp"]:
                            display = clean.upper()
                        elif key == "javascript":
                            display = "JavaScript"
                        elif key == "typescript":
                            display = "TypeScript"
                        else:
                            display = clean.title() if len(clean) > 3 else clean.upper()
                        tech_map[display] += 1

        sorted_tech = [
            {"name": tech_name, "count": count}
            for tech_name, count in sorted(tech_map.items(), key=lambda x: x[0].lower())
        ]

        result = {
            "cities": sorted_cities,
            "tech_stacks": sorted_tech,
            "stats": {
                "total": total_valid,
                "enriched": enriched_count,
                "emails": with_emails_count,
                "invalid": invalid_count,
                "contacted": user_contacted_count,
                "is_logged_in": bool(user)
            },
            "is_master_admin": is_admin
        }

        _filter_cache["timestamp"] = now
        _filter_cache["data"] = result
        return result
    except Exception as e:
        print(f"[API Error] /api/companies/filters failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        if _filter_cache.get("data"):
            fallback = copy.deepcopy(_filter_cache["data"])
            fallback["error"] = str(e)
            return fallback
        return {
            "cities": [],
            "tech_stacks": [],
            "stats": {
                "total": 0,
                "enriched": 0,
                "emails": 0,
                "invalid": 0,
                "contacted": None,
                "is_logged_in": False
            },
            "is_master_admin": False,
            "error": str(e)
        }


@app.get("/api/companies")
async def get_companies(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    search: str = "",
    tech: str = "",
    city: str = "",
    status: str = "all",
    sort: str = "newest",
    db: Session = Depends(get_db)
):
    """
    Lightweight, high-performance paginated companies endpoint.
    Excludes massive markdown dossiers (detailed_analysis) from batch loads.
    Full intel is queried on-demand via GET /api/companies/{id}.
    """
    try:
        user = get_current_user(db, request)
        is_admin = bool(user and config.is_master_admin(user.email))

        base_query = (
            db.query(Company)
            .filter(~Company.domain.like("%.local"))
            .filter(Company.domain.contains("."))
        )

        invalid_count = base_query.filter(Company.is_invalid.is_(True)).count()

        # 1. Base genuine vs excluded filtering
        if status == "invalid":
            if not is_admin:
                return {
                    "companies": [],
                    "total_count": 0,
                    "total_pages": 0,
                    "current_page": page,
                    "page_size": page_size,
                    "invalid_count": 0,
                    "is_master_admin": False,
                    "dev_mode": config.DEV_MODE
                }
            query = base_query.filter(Company.is_invalid.is_(True))
        else:
            if not is_admin:
                query = base_query.filter(Company.is_invalid.is_(False))
            else:
                query = base_query

        # 2. Metric / Status filter
        if status == "enriched":
            query = query.filter(Company.is_enriched.is_(True))
        elif status == "emails":
            emails_sub = db.query(CompanyEmail.company_id).distinct().subquery()
            query = query.filter(Company.id.in_(emails_sub))
        elif status in ("contacted", "sent"):
            if user:
                sent_sub = db.query(OutreachLog.company_id).filter(
                    OutreachLog.status == "SENT",
                    OutreachLog.user_id == user.id
                ).distinct().subquery()
                query = query.filter(Company.id.in_(sent_sub))
            else:
                query = query.filter(Company.id == -1)
        elif status in ("uncontacted", "ready"):
            if user:
                sent_sub = db.query(OutreachLog.company_id).filter(
                    OutreachLog.status == "SENT",
                    OutreachLog.user_id == user.id
                ).distinct().subquery()
                query = query.filter(~Company.id.in_(sent_sub))

        # 3. Search query filter
        if search and search.strip():
            s = f"%{search.strip().lower()}%"
            query = query.filter(
                (Company.name.ilike(s)) |
                (Company.domain.ilike(s)) |
                (Company.city.ilike(s)) |
                (Company.address.ilike(s)) |
                (Company.source_query.ilike(s)) |
                (Company.normalized_keyword.ilike(s))
            )

        # 4. City filter (multi-select supported via comma-separated string or multiple query params)
        raw_cities = request.query_params.getlist("city")
        city_terms = []
        for c_val in raw_cities:
            city_terms.extend([x.strip().lower() for x in c_val.split(",") if x.strip()])
        if not city_terms and city and city.strip():
            city_terms = [x.strip().lower() for x in city.split(",") if x.strip()]

        if city_terms:
            city_conds = []
            for c_term in city_terms:
                c_pat = f"%{c_term}%"
                city_conds.append(Company.city.ilike(c_pat))
                city_conds.append(Company.address.ilike(c_pat))
            query = query.filter(or_(*city_conds))

        # 5. Tech stack filter (multi-select supported via comma-separated string or multiple query params)
        raw_techs = request.query_params.getlist("tech") or request.query_params.getlist("tech_stack")
        tech_terms = []
        for t_val in raw_techs:
            tech_terms.extend([x.strip().lower() for x in t_val.split(",") if x.strip()])
        if not tech_terms and tech and tech.strip():
            tech_terms = [x.strip().lower() for x in tech.split(",") if x.strip()]

        if tech_terms:
            tech_conds = [
                CompanyProfile.tech_stack.cast(String).ilike(f"%{t_term}%")
                for t_term in tech_terms
            ]
            query = query.join(CompanyProfile, Company.id == CompanyProfile.company_id).filter(
                or_(*tech_conds)
            ).distinct()

        # 6. Sorting
        if sort == "rating_desc":
            query = query.order_by(Company.rating.desc().nullslast(), Company.reviews_count.desc(), Company.id.desc())
        elif sort == "reviews_desc":
            query = query.order_by(Company.reviews_count.desc(), Company.rating.desc().nullslast(), Company.id.desc())
        elif sort == "name_asc":
            query = query.order_by(Company.name.asc())
        else:
            query = query.order_by(Company.id.desc())

        total_count = query.count()

        # 7. Server-side pagination strictly enforcing defined list: [10, 20, 50, 100, 200]
        ALLOWED_PAGE_SIZES = {10, 20, 50, 100, 200, 0}
        if page_size not in ALLOWED_PAGE_SIZES:
            page_size = 20

        if page_size > 0:
            total_pages = max(1, (total_count + page_size - 1) // page_size) if total_count > 0 else 1
            cur_page = max(1, min(page, total_pages)) if total_count > 0 else 1
            companies = query.offset((cur_page - 1) * page_size).limit(page_size).all()
        else:
            total_pages = 1
            cur_page = 1
            companies = query.all()

        company_ids = [c.id for c in companies]

        # Batch load emails for page items only
        emails_by_company = defaultdict(list)
        if company_ids:
            for cid, em in db.query(CompanyEmail.company_id, CompanyEmail.email_address).filter(CompanyEmail.company_id.in_(company_ids)).all():
                emails_by_company[cid].append(em)

        # Batch load lightweight profile card info (omits heavy detailed_analysis!)
        profiles_by_company = {}
        if company_ids:
            for prof in db.query(
                CompanyProfile.company_id,
                CompanyProfile.summary_short,
                CompanyProfile.industry,
                CompanyProfile.tech_stack
            ).filter(CompanyProfile.company_id.in_(company_ids)).all():
                profiles_by_company[prof[0]] = {
                    "summary": prof[1] or "",
                    "industry": prof[2] or "",
                    "tech_stack": prof[3] or []
                }

        sent_logs = {}
        user_pitches = {}
        if user and company_ids:
            sent_logs = {
                log.company_id: log.sent_at
                for log in db.query(OutreachLog)
                .filter(OutreachLog.status == "SENT", OutreachLog.user_id == user.id, OutreachLog.company_id.in_(company_ids))
                .all()
            }
            user_pitches = {
                p.company_id: p.id
                for p in db.query(ColdPitch.company_id, ColdPitch.id)
                .filter(ColdPitch.user_id == user.id, ColdPitch.company_id.in_(company_ids))
                .all()
            }

        out = []
        for c in companies:
            emails = emails_by_company.get(c.id, [])
            profile = profiles_by_company.get(c.id)
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
                "pitch_id": user_pitches.get(c.id),
                "already_contacted": bool(sent_time),
                "contacted_at": sent_time.strftime("%b %d, %Y %I:%M %p") if sent_time else None
            })

        return {
            "companies": out,
            "total_count": total_count,
            "total_pages": total_pages,
            "current_page": cur_page,
            "page_size": page_size,
            "invalid_count": invalid_count if is_admin else 0,
            "is_master_admin": is_admin,
            "dev_mode": config.DEV_MODE
        }
    except Exception as e:
        print(f"[API Error] /api/companies failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return {
            "companies": [],
            "total_count": 0,
            "total_pages": 0,
            "current_page": 1,
            "page_size": page_size,
            "invalid_count": 0,
            "is_master_admin": False,
            "dev_mode": config.DEV_MODE
        }


@app.get("/api/companies/{company_id}")
async def get_company_detail(company_id: int, request: Request, db: Session = Depends(get_db)):
    """On-demand deep intelligence dossier and verified records for a single company modal"""
    user = get_current_user(db, request)
    is_admin = bool(user and config.is_master_admin(user.email))

    query = db.query(Company).filter(Company.id == company_id)
    if not is_admin:
        query = query.filter(Company.is_invalid.is_(False))
    company = query.first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found or access denied.")

    emails = [em.email_address for em in db.query(CompanyEmail).filter(CompanyEmail.company_id == company.id).all()]
    profile_record = db.query(CompanyProfile).filter(CompanyProfile.company_id == company.id).first()

    profile_data = None
    if profile_record:
        profile_data = {
            "summary": profile_record.summary_short or "",
            "detailed_analysis": profile_record.detailed_analysis or "",
            "industry": profile_record.industry or "",
            "tech_stack": profile_record.tech_stack or [],
            "services": profile_record.services or [],
            "tone": profile_record.tone or "Professional",
            "analyzed_at": profile_record.analyzed_at.strftime("%b %d, %Y %I:%M %p") if profile_record.analyzed_at else None
        }

    sent_log = None
    if user:
        sent_log = db.query(OutreachLog).filter(
            OutreachLog.company_id == company.id,
            OutreachLog.status == "SENT",
            OutreachLog.user_id == user.id
        ).order_by(OutreachLog.sent_at.desc()).first()

    maps_query = f"{company.name} {company.address or company.source_query or ''}".strip()
    maps_url = company.location_url or f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(maps_query)}"

    pitch_data = None
    if user:
        latest_pitch = db.query(ColdPitch).filter(
            ColdPitch.company_id == company.id,
            ColdPitch.user_id == user.id
        ).order_by(ColdPitch.created_at.desc()).first()
        if latest_pitch:
            pitch_data = {
                "id": latest_pitch.id,
                "subject": latest_pitch.subject,
                "body": latest_pitch.pitch_body,
                "created_at": latest_pitch.created_at.strftime("%b %d, %Y %I:%M %p") if latest_pitch.created_at else None
            }

    return {
        "id": company.id,
        "name": company.name,
        "domain": company.domain,
        "website_url": company.website_url,
        "location_url": maps_url,
        "phone": company.phone,
        "address": company.address or "",
        "city": company.city or "",
        "rating": company.rating,
        "reviews_count": company.reviews_count,
        "is_enriched": company.is_enriched,
        "is_invalid": bool(company.is_invalid),
        "invalid_reason": company.invalid_reason or "",
        "invalid_at": company.invalid_at.strftime("%b %d, %Y %I:%M %p") if company.invalid_at else None,
        "emails": emails,
        "profile": profile_data,
        "pitch": pitch_data,
        "already_contacted": bool(sent_log),
        "contacted_at": sent_log.sent_at.strftime("%b %d, %Y %I:%M %p") if sent_log else None
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

    req_email = (payload.email.strip().lower() if payload and payload.email else None)

    if req_email and config.is_master_admin(req_email):
        target_email = req_email
        name = "Master Admin"
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
            target_role="",
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
    resp.set_cookie(key="pilot_user_email", value=signed_cookie, path="/", httponly=True, samesite="lax", max_age=config.SESSION_COOKIE_MAX_AGE)
    return resp


@app.get("/auth/logout")
@app.post("/auth/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(db, request)
    if user:
        user.oauth_tokens = None
        db.commit()
    if request.method == "GET":
        resp = RedirectResponse(url="/", status_code=303)
    else:
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
    is_authorized = bool(user and config.is_master_admin(user.email))
    if not is_authorized:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Master Admin privileges required to exclude companies."
        )

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    company.is_invalid = True
    company.invalid_at = datetime.utcnow()
    company.invalid_reason = (req_body.reason if req_body and req_body.reason else "Excluded by Admin")
    db.commit()
    invalidate_filter_cache()

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
    is_authorized = bool(user and config.is_master_admin(user.email))
    if not is_authorized:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Master Admin privileges required to restore companies."
        )

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    company.is_invalid = False
    company.invalid_at = None
    company.invalid_reason = None
    db.commit()
    invalidate_filter_cache()

    return {
        "success": True,
        "message": f"'{company.name}' restored to active genuine leads.",
        "company_id": company.id,
        "is_invalid": False
    }


@app.post("/api/companies/bulk-invalidate")
async def bulk_invalidate_companies(
    req_body: BulkInvalidateCompaniesRequest,
    request: Request = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(db, request)
    is_authorized = bool(user and config.is_master_admin(user.email))
    if not is_authorized:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Master Admin privileges required to exclude companies."
        )

    if not req_body.company_ids:
        return {"success": True, "count": 0, "message": "No companies selected."}

    now = datetime.utcnow()
    reason = req_body.reason or "Excluded by Admin"

    updated = (
        db.query(Company)
        .filter(Company.id.in_(req_body.company_ids))
        .update(
            {
                Company.is_invalid: True,
                Company.invalid_at: now,
                Company.invalid_reason: reason,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    invalidate_filter_cache()

    return {
        "success": True,
        "count": updated,
        "message": f"Successfully marked {updated} companies as invalid and excluded from user views.",
    }


@app.post("/api/companies/bulk-restore")
async def bulk_restore_companies(
    req_body: BulkRestoreCompaniesRequest,
    request: Request = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(db, request)
    is_authorized = bool(user and config.is_master_admin(user.email))
    if not is_authorized:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Master Admin privileges required to restore companies."
        )

    if not req_body.company_ids:
        return {"success": True, "count": 0, "message": "No companies selected."}

    updated = (
        db.query(Company)
        .filter(Company.id.in_(req_body.company_ids))
        .update(
            {
                Company.is_invalid: False,
                Company.invalid_at: None,
                Company.invalid_reason: None,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    invalidate_filter_cache()

    return {
        "success": True,
        "count": updated,
        "message": f"Successfully restored {updated} companies to active genuine leads.",
    }



@app.post("/api/companies/{company_id}/enrich")
async def enrich_single_company(
    company_id: int,
    force_refresh: bool = False,
    request: Request = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(db, request)
    if not user or not user.oauth_tokens:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please connect your Google account or log in to run Deep Enrichment."
        )

    client_id = f"{user.id}_{request.client.host if request and request.client else 'unknown'}"
    enforce_rate_limit(f"enrich_single_{client_id}", max_calls=20, window_seconds=60)

    result = await deep_enrich_company(company_id=company_id, db=db, force_refresh=force_refresh)
    invalidate_filter_cache()
    return result


@app.post("/api/companies/bulk-enrich")
async def enrich_bulk_companies(
    req: BulkEnrichRequest,
    request: Request = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(db, request)
    if not user or not user.oauth_tokens:
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
    if not user or not user.oauth_tokens:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please sign in with Google to analyze your resume."
        )

    client_id = f"{user.id}_{request.client.host if request and request.client else 'unknown'}"
    enforce_rate_limit(f"resume_upload_{client_id}", max_calls=15, window_seconds=60)

    target_role_clean = (target_role or "").strip()
    resume_link_clean = (resume_link or "").strip()
    has_file = bool(file and file.filename)

    if not target_role_clean:
        raise HTTPException(
            status_code=400,
            detail="Target Job Role is required before analyzing your resume."
        )

    if not has_file and not resume_link_clean and not (user.resume_summary and user.resume_summary.get("elevator_pitch")):
        raise HTTPException(
            status_code=400,
            detail="Please select a resume file (PDF or TXT) or enter a portfolio link."
        )

    # Save portfolio/resume link if provided
    if resume_link is not None:
        user.resume_link = resume_link_clean

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
        "target_role": req.target_role or user.target_role or "",
        "top_skills": ["Python", "FastAPI", "React", "PostgreSQL"],
        "key_achievements": ["Built scalable web services and automated data workflows"]
    }
    if user.resume_link and not cand_profile.get("resume_link"):
        cand_profile["resume_link"] = user.resume_link

    comp_profile_data = {
        "summary": company.profile.summary_short if company.profile else "",
        "detailed_analysis": company.profile.detailed_analysis if company.profile else "",
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
    # Strict anti-hallucination: Never synthesize fake or blind contact@domain fallback emails.
    # If no discovered or verified email exists, keep target_email as None.

    pitch_data = generate_personalized_pitch(
        candidate_profile=cand_profile,
        company_name=company.name,
        company_profile=comp_profile_data
    )

    subj = (pitch_data.get("subject_line") or "").strip()
    body = (pitch_data.get("email_body") or "").strip()
    c_name = cand_profile.get("full_name") or (user.name if user and user.name else "Candidate")
    t_role = cand_profile.get("target_role") or (user.target_role if user and user.target_role else "Professional")
    if not subj:
        subj = f"{t_role} inquiry - {c_name}"
    if not body:
        skills_str = ", ".join(cand_profile.get("top_skills", [])[:4]) or "PHP, Python, SQL, REST APIs"
        body = f"Hi {company.name} team,\n\nI’ve been following {company.name} and wanted to reach out directly. As a {t_role} specializing in {skills_str}, I build scalable backend architectures, high-throughput APIs, and optimized databases.\n\nI'm exploring new {t_role} roles and would love to know if {company.name} has open or upcoming engineering positions. Would you be open to a brief chat regarding how my experience could help your product roadmap?\n\nBest regards,\n{c_name}"

    existing_pitch = db.query(ColdPitch).filter(
        ColdPitch.company_id == company.id,
        ColdPitch.user_id == user.id
    ).first()

    # If existing pitch has already been generated with rich deliverables, return immediately unless force_regenerate is requested
    if existing_pitch and not getattr(req, "force_regenerate", False):
        raw_meta = existing_pitch.matched_skills if isinstance(existing_pitch.matched_skills, dict) else {}
        if existing_pitch.email_body and raw_meta.get("variant_a_linkedin"):
            gmail_web_url = generate_gmail_web_link(
                to_email=target_email or existing_pitch.target_email or "",
                subject=existing_pitch.subject_line,
                body=existing_pitch.email_body
            )
            mailto_url = generate_mailto_link(
                to_email=target_email or existing_pitch.target_email or "",
                subject=existing_pitch.subject_line,
                body=existing_pitch.email_body
            )
            return {
                "success": True,
                "pitch_id": existing_pitch.id,
                "company_name": company.name,
                "target_email": target_email or existing_pitch.target_email,
                "subject_line": existing_pitch.subject_line,
                "subject_lines": raw_meta.get("subject_lines") or {
                    "specificity": existing_pitch.subject_line,
                    "curiosity": f"Engineering inquiry - {cand_profile.get('full_name', 'Candidate')}",
                    "benefit_led": f"Scalable systems for {company.name}"
                },
                "email_body": existing_pitch.email_body,
                "primary_email": raw_meta.get("primary_email", existing_pitch.email_body),
                "variant_a_linkedin": raw_meta.get("variant_a_linkedin", ""),
                "variant_b_referral": raw_meta.get("variant_b_referral", existing_pitch.cover_letter or ""),
                "cover_letter": existing_pitch.cover_letter or "",
                "personalization_notes": raw_meta.get("personalization_notes", []),
                "what_to_change_if": raw_meta.get("what_to_change_if", {}),
                "matched_skills": raw_meta.get("skills") if isinstance(raw_meta.get("skills"), list) else (existing_pitch.matched_skills if isinstance(existing_pitch.matched_skills, list) else []),
                "gmail_web_url": gmail_web_url,
                "mailto_url": mailto_url
            }

    pitch_data = generate_personalized_pitch(
        candidate_profile=cand_profile,
        company_name=company.name,
        company_profile=comp_profile_data
    )

    subj = (pitch_data.get("subject_line") or "").strip()
    body = (pitch_data.get("primary_email") or pitch_data.get("email_body") or "").strip()
    c_name = cand_profile.get("full_name") or (user.name if user and user.name else "Candidate")
    t_role = cand_profile.get("target_role") or (user.target_role if user and user.target_role else "Professional")
    if not subj:
        subj = f"{t_role} inquiry - {c_name}"
    if not body:
        skills_str = ", ".join(cand_profile.get("top_skills", [])[:4]) or "PHP, Python, SQL, REST APIs"
        body = f"Hi {company.name} team,\n\nI’ve been following {company.name} and wanted to reach out directly. As a {t_role} specializing in {skills_str}, I build scalable backend architectures, high-throughput APIs, and optimized databases.\n\nI'm exploring new {t_role} roles and would love to know if {company.name} has open or upcoming engineering positions. Would you be open to a brief chat regarding how my experience could help your product roadmap?\n\nBest regards,\n{c_name}"

    matched_meta = {
        "skills": pitch_data.get("matched_skills", []),
        "subject_lines": pitch_data.get("subject_lines", {}),
        "primary_email": body,
        "variant_a_linkedin": pitch_data.get("variant_a_linkedin", ""),
        "variant_b_referral": pitch_data.get("variant_b_referral", ""),
        "personalization_notes": pitch_data.get("personalization_notes", []),
        "what_to_change_if": pitch_data.get("what_to_change_if", {})
    }

    if existing_pitch:
        existing_pitch.subject_line = subj
        existing_pitch.email_body = body
        existing_pitch.cover_letter = pitch_data.get("cover_letter", "")
        existing_pitch.matched_skills = matched_meta
        existing_pitch.target_email = target_email
        db.commit()
        pitch_obj = existing_pitch
    else:
        pitch_obj = ColdPitch(
            company_id=company.id,
            user_id=user.id,
            target_email=target_email,
            subject_line=subj,
            email_body=body,
            cover_letter=pitch_data.get("cover_letter", ""),
            matched_skills=matched_meta,
            status="DRAFT"
        )
        db.add(pitch_obj)
        db.commit()
        db.refresh(pitch_obj)

    gmail_web_url = generate_gmail_web_link(
        to_email=target_email or "",
        subject=pitch_obj.subject_line,
        body=pitch_obj.email_body
    )
    mailto_url = generate_mailto_link(
        to_email=target_email or "",
        subject=pitch_obj.subject_line,
        body=pitch_obj.email_body
    )

    return {
        "success": True,
        "pitch_id": pitch_obj.id,
        "company_name": company.name,
        "target_email": target_email,
        "subject_line": pitch_obj.subject_line,
        "subject_lines": pitch_data.get("subject_lines", {}),
        "email_body": pitch_obj.email_body,
        "primary_email": pitch_data.get("primary_email", pitch_obj.email_body),
        "variant_a_linkedin": pitch_data.get("variant_a_linkedin", ""),
        "variant_b_referral": pitch_data.get("variant_b_referral", ""),
        "cover_letter": pitch_obj.cover_letter,
        "personalization_notes": pitch_data.get("personalization_notes", []),
        "what_to_change_if": pitch_data.get("what_to_change_if", {}),
        "matched_skills": pitch_data.get("matched_skills", []),
        "gmail_web_url": gmail_web_url,
        "mailto_url": mailto_url
    }


@app.post("/api/pitch/bulk-generate")
async def generate_bulk_pitches(
    req: BulkPitchRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    High-throughput concurrent batch pitch generator.
    Replaces slow 1-by-1 sequential AJAX calls with parallel multi-worker execution.
    """
    user = get_current_user(db, request)
    if not user or not user.oauth_tokens:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please connect your Google account to generate personalized pitches."
        )

    client_id = f"{user.id}_{request.client.host if request and request.client else 'unknown'}"
    enforce_rate_limit(f"bulk_pitch_gen_{client_id}", max_calls=30, window_seconds=60)

    if not req.company_ids:
        return {"success": True, "generated_count": 0, "total": 0, "pitches": []}

    cand_profile = req.candidate_profile or user.resume_summary or {
        "full_name": user.name or "Candidate",
        "target_role": req.target_role or user.target_role or "Software Engineer",
        "top_skills": ["Python", "FastAPI", "React", "PostgreSQL"],
        "key_achievements": ["Built scalable web services and automated data workflows"]
    }
    if user.resume_link and not cand_profile.get("resume_link"):
        cand_profile["resume_link"] = user.resume_link

    # Batch load all requested companies in a single SQL query
    companies = db.query(Company).filter(Company.id.in_(req.company_ids)).all()
    if not companies:
        return {"success": True, "generated_count": 0, "total": 0, "pitches": []}

    # Pre-fetch existing pitches to update rather than duplicate
    existing_pitches = {
        p.company_id: p
        for p in db.query(ColdPitch).filter(
            ColdPitch.company_id.in_(req.company_ids),
            ColdPitch.user_id == user.id
        ).all()
    }

    # Extract plain dicts in main thread for complete thread safety
    tasks = []
    for comp in companies:
        target_email = None
        if comp.emails:
            primary_emails = [e.email_address for e in comp.emails if getattr(e, "is_primary", False)]
            if primary_emails:
                target_email = primary_emails[0]
            else:
                for e in comp.emails:
                    if is_recruitment_email(e.email_address):
                        target_email = e.email_address
                        break
                if not target_email:
                    target_email = comp.emails[0].email_address

        comp_profile_data = {
            "summary": comp.profile.summary_short if comp.profile else "",
            "detailed_analysis": comp.profile.detailed_analysis if comp.profile else "",
            "industry": comp.profile.industry if comp.profile else "Tech",
            "tech_stack": comp.profile.tech_stack if comp.profile else [],
            "tone": comp.profile.tone if comp.profile else "Professional"
        }
        tasks.append({
            "company_id": comp.id,
            "company_name": comp.name,
            "target_email": target_email,
            "profile": comp_profile_data
        })

    def process_task(task):
        pitch_data = generate_personalized_pitch(
            candidate_profile=cand_profile,
            company_name=task["company_name"],
            company_profile=task["profile"]
        )

        subj = (pitch_data.get("subject_line") or "").strip()
        body = (pitch_data.get("primary_email") or pitch_data.get("email_body") or "").strip()
        c_name = cand_profile.get("full_name") or (user.name if user and user.name else "Candidate")
        t_role = cand_profile.get("target_role") or (user.target_role if user and user.target_role else "Professional")
        if not subj:
            subj = f"{t_role} inquiry - {c_name}"
        if not body:
            skills_str = ", ".join(cand_profile.get("top_skills", [])[:4]) or "PHP, Python, SQL, REST APIs"
            body = f"Hi {task['company_name']} team,\n\nI’ve been following {task['company_name']} and wanted to reach out directly. As a {t_role} specializing in {skills_str}, I build scalable backend architectures, high-throughput APIs, and optimized databases.\n\nI'm exploring new {t_role} roles and would love to know if {task['company_name']} has open or upcoming engineering positions. Would you be open to a brief chat regarding how my experience could help your product roadmap?\n\nBest regards,\n{c_name}"

        matched_meta = {
            "skills": pitch_data.get("matched_skills", []),
            "subject_lines": pitch_data.get("subject_lines", {}),
            "primary_email": body,
            "variant_a_linkedin": pitch_data.get("variant_a_linkedin", ""),
            "variant_b_referral": pitch_data.get("variant_b_referral", ""),
            "personalization_notes": pitch_data.get("personalization_notes", []),
            "what_to_change_if": pitch_data.get("what_to_change_if", {})
        }

        return {
            "company_id": task["company_id"],
            "company_name": task["company_name"],
            "target_email": task["target_email"],
            "subject_line": subj,
            "email_body": body,
            "cover_letter": pitch_data.get("cover_letter", ""),
            "matched_skills": matched_meta
        }

    # Parallelize generation across threadpool workers (up to 10 concurrent threads)
    from concurrent.futures import ThreadPoolExecutor
    max_workers = min(10, max(2, len(tasks)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(process_task, tasks))

    saved_pitches = []
    for res in results:
        cid = res["company_id"]
        if cid in existing_pitches:
            pitch_obj = existing_pitches[cid]
            pitch_obj.subject_line = res["subject_line"]
            pitch_obj.email_body = res["email_body"]
            pitch_obj.cover_letter = res["cover_letter"]
            pitch_obj.matched_skills = res["matched_skills"]
            pitch_obj.target_email = res["target_email"]
        else:
            pitch_obj = ColdPitch(
                company_id=cid,
                user_id=user.id,
                target_email=res["target_email"],
                subject_line=res["subject_line"],
                email_body=res["email_body"],
                cover_letter=res["cover_letter"],
                matched_skills=res["matched_skills"],
                status="DRAFT"
            )
            db.add(pitch_obj)
        db.flush()
        saved_pitches.append({
            "pitch_id": pitch_obj.id,
            "company_id": cid,
            "company_name": res["company_name"],
            "target_email": res["target_email"]
        })

    db.commit()
    return {
        "success": True,
        "generated_count": len(saved_pitches),
        "total": len(companies),
        "pitches": saved_pitches
    }


# --- Stage 5: Direct & Multi-Tier Outreach Sending ---
@app.post("/api/pitch/{pitch_id}/send-direct")
async def send_single_pitch_direct(
    pitch_id: int,
    request: Request = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(db, request)
    if not user or not user.oauth_tokens:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please connect your Google account to send direct emails."
        )
    pitch = db.query(ColdPitch).filter(ColdPitch.id == pitch_id).first()
    if not pitch:
        raise HTTPException(status_code=404, detail="Pitch not found")

    if not config.is_master_admin(user.email) and pitch.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden: You do not own this pitch record.")

    content_type = request.headers.get("content-type", "") if request else ""
    attach_resume = False
    custom_subject = None
    custom_body = None
    resume_bytes = None
    resume_filename = None

    if "multipart/form-data" in content_type:
        form = await request.form()
        attach_resume = form.get("attach_resume") in ("true", "True", "1", True)
        custom_subject = form.get("subject")
        custom_body = form.get("body")
        uploaded_file = form.get("resume_file")
        if uploaded_file and hasattr(uploaded_file, "read"):
            resume_bytes = await uploaded_file.read()
            resume_filename = getattr(uploaded_file, "filename", "Resume.pdf")
    elif "application/json" in content_type:
        try:
            json_data = await request.json()
            attach_resume = bool(json_data.get("attach_resume"))
            custom_subject = json_data.get("subject")
            custom_body = json_data.get("body")
        except Exception:
            pass

    target = (pitch.target_email or "").strip()
    if not target:
        return {
            "success": False,
            "error": "Company email not found! Cannot send email."
        }
    effective_subject = custom_subject.strip() if custom_subject and custom_subject.strip() else pitch.subject_line
    effective_body = custom_body.strip() if custom_body and custom_body.strip() else pitch.email_body

    # Fallback to saved resume if attachment requested but no temp file was passed in request
    if attach_resume and not resume_bytes:
        user_resume_path = os.path.join("uploads", "resumes", f"user_{user.id}_resume.pdf")
        if os.path.exists(user_resume_path):
            try:
                with open(user_resume_path, "rb") as rf:
                    resume_bytes = rf.read()
                    resume_filename = "Resume.pdf"
            except Exception as read_err:
                print(f"[Send Warning] Could not read user resume: {read_err}")

    result = await send_via_google_oauth(
        user=user,
        to_email=target,
        subject=effective_subject,
        body=effective_body,
        db=db,
        company_id=pitch.company_id,
        resume_attachment_bytes=resume_bytes if attach_resume else None,
        resume_attachment_name=resume_filename if attach_resume else None
    )

    if result.get("success"):
        pitch.subject_line = effective_subject
        pitch.email_body = effective_body
        pitch.status = "SENT"
        pitch.sent_at = datetime.utcnow()
        pitch.delivery_method = "OAUTH_DIRECT"
        db.commit()
        return {"success": True, "message_id": result.get("message_id")}
    else:
        return {"success": False, "error": result.get("error", "Failed to dispatch email via Google OAuth.")}


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

    target = (pitch.target_email or "").strip()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company email not found! Cannot send or log email without recipient."
        )

    pitch.status = "SENT"
    pitch.sent_at = datetime.utcnow()
    pitch.delivery_method = method

    log_entry = OutreachLog(
        company_id=pitch.company_id,
        user_id=pitch.user_id,
        recipient_email=target,
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

    logs = (
        db.query(OutreachLog)
        .filter(OutreachLog.user_id == user.id)
        .order_by(OutreachLog.sent_at.desc())
        .limit(100)
        .all()
    )
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

    query = db.query(OutreachLog).filter(
        OutreachLog.company_id == company_id,
        OutreachLog.status == "SENT",
        OutreachLog.user_id == user.id
    )

    log = query.order_by(OutreachLog.sent_at.desc()).first()
    if not log:
        # Fallback to pitch if log not found
        pitch = db.query(ColdPitch).filter(
            ColdPitch.company_id == company_id,
            ColdPitch.user_id == user.id
        ).first()
        if pitch:
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
    raw_host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    host = raw_host.strip().rstrip("/") if raw_host else ""

    # If running on Render or any non-local public domain:
    if host and not host.startswith("localhost") and not host.startswith("127.0.0.1"):
        return f"{proto}://{host}/auth/google/callback"

    # Otherwise return local configured redirect URI
    return (config.GOOGLE_REDIRECT_URI or "http://localhost:8000/auth/google/callback").strip().rstrip("/")


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
        prompt="consent select_account",
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
                target_role="",
                daily_send_limit=100 if is_admin else 50
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        # Encrypt OAuth credentials before persisting in PostgreSQL
        existing_tokens = {}
        if user.oauth_tokens:
            try:
                decrypted = config.decrypt_tokens(user.oauth_tokens)
                if isinstance(decrypted, dict):
                    existing_tokens = decrypted
            except Exception:
                pass

        user.oauth_tokens = config.encrypt_tokens({
            "token": credentials.token,
            "refresh_token": credentials.refresh_token or existing_tokens.get("refresh_token"),
            "token_uri": credentials.token_uri or "https://oauth2.googleapis.com/token",
            "client_id": credentials.client_id or config.GOOGLE_CLIENT_ID,
            "client_secret": credentials.client_secret or config.GOOGLE_CLIENT_SECRET
        })
        db.commit()

        response = RedirectResponse(url="/app?auth_success=1")
        signed_cookie = config.sign_user_email(user.email)
        response.set_cookie(
            key="pilot_user_email",
            value=signed_cookie,
            path="/",
            httponly=True,
            samesite="lax",
            max_age=config.SESSION_COOKIE_MAX_AGE
        )
        response.delete_cookie(key="oauth_state", path="/")
        return response
    except Exception as e:
        return RedirectResponse(url=f"/?auth_error={urllib.parse.quote(str(e))}")


if __name__ == "__main__":
    print("\n[OutreachPilot] Running! Open in browser: http://localhost:8000 or http://127.0.0.1:8000\n")
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)

