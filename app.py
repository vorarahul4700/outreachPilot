import asyncio
import copy
import csv
import io
import json
import mimetypes
import os
import re
import secrets
import time
import urllib.parse
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests
import uvicorn
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google_auth_oauthlib.flow import Flow
from pydantic import BaseModel
from pypdf import PdfReader
from sqlalchemy import String, func, literal_column, or_, text
from sqlalchemy.orm import Session, joinedload
from starlette.exceptions import HTTPException as StarletteHTTPException

# In-memory cached filter metadata (300s TTL for fast responses)
_filter_cache = {
    "timestamp": 0.0,
    "data": None
}
_dynamic_filter_cache = {}

# In-memory cached admin metrics (30s TTL with manual invalidate)
_admin_metrics_cache = {
    "timestamp": 0.0,
    "data": None
}

def invalidate_admin_metrics_cache():
    _admin_metrics_cache["timestamp"] = 0.0
    _admin_metrics_cache["data"] = None

_github_telemetry_cache = {}

def invalidate_filter_cache():
    global _filter_cache, _dynamic_filter_cache
    _filter_cache["timestamp"] = 0.0
    _filter_cache["data"] = None
    _dynamic_filter_cache.clear()


import config
import seo_engine
import taxonomy
from ai_agent import (
    generate_personalized_pitch,
    normalize_single_keyword,
    parse_resume_text,
)
from db import (
    Category,
    ColdPitch,
    Company,
    CompanyEmail,
    CompanyProfile,
    CompanyTech,
    Industry,
    OutreachLog,
    ScoutJob,
    SendAttachment,
    SessionLocal,
    SubscriptionTier,
    SystemSetting,
    Tech,
    User,
    engine,
    get_db,
    init_db,
)
from enricher import is_recruitment_email
from outreach import (
    add_do_not_contact,
    read_optout_token,
    generate_mailto_link,
    refund_daily_pitches,
    run_send_queue,
    send_via_google_oauth,
)
from scraper_engine import GoogleScraper, is_genuine_company_domain
from clean_db_company_names import clean_company_name

# In-memory sliding window rate limiter
_rate_limit_store = defaultdict(list)


_rl_call_counter = 0


def enforce_rate_limit(key: str, max_calls: int, window_seconds: int = 60):
    global _rl_call_counter
    now = time.time()

    # Opportunistic eviction so idle keys don't accumulate unbounded in memory.
    _rl_call_counter += 1
    if _rl_call_counter % 500 == 0:
        for k in list(_rate_limit_store.keys()):
            if not any(now - t < window_seconds for t in _rate_limit_store.get(k, [])):
                _rate_limit_store.pop(k, None)

    recent = [t for t in _rate_limit_store[key] if now - t < window_seconds]
    if len(recent) >= max_calls:
        _rate_limit_store[key] = recent  # keep the pruned window accurate
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Maximum {max_calls} requests per {window_seconds}s. Please wait a moment."
        )
    recent.append(now)
    _rate_limit_store[key] = recent


def _prewarm_cache():
    """Pre-warm global filter stats and aggregations in background thread so user requests are instant (<10ms)"""
    try:
        db = SessionLocal()
        now = time.time()
        # Companies in categories hidden from users (admin > Categories) are not counted.
        vis_sql, vis_params = seo_engine.visible_kw_sql(db)
        vis_sql_c, _ = seo_engine.visible_kw_sql(db, prefix="c.")
        counts_res = db.execute(text(f"""
            SELECT
                COUNT(*) FILTER (WHERE is_invalid = FALSE{vis_sql}) AS total_valid,
                COUNT(*) FILTER (WHERE is_invalid = TRUE) AS invalid_count,
                COUNT(*) FILTER (WHERE is_invalid = FALSE AND is_enriched = TRUE{vis_sql}) AS enriched_count
            FROM companies;
        """), vis_params).fetchone()

        total_valid = (counts_res[0] if counts_res else 0) or 0
        invalid_count = (counts_res[1] if counts_res else 0) or 0
        enriched_count = (counts_res[2] if counts_res else 0) or 0

        with_emails_count = db.execute(text(f"""
            SELECT COUNT(DISTINCT ce.company_id)
            FROM company_emails ce
            JOIN companies c ON c.id = ce.company_id
            WHERE c.is_invalid = FALSE{vis_sql_c};
        """), vis_params).scalar() or 0

        city_rows = db.execute(text(f"""
            SELECT initcap(trim(city)) AS norm_city, COUNT(*) AS count
            FROM companies
            WHERE is_invalid = FALSE{vis_sql} AND city IS NOT NULL AND trim(city) != ''
            GROUP BY norm_city
            ORDER BY norm_city ASC;
        """), vis_params).fetchall()

        sorted_cities = [{"name": r[0], "count": r[1]} for r in city_rows if r[0]]

        tech_map = defaultdict(int)
        try:
            tech_rows = db.execute(text("""
                SELECT item, COUNT(*) AS count
                FROM company_profiles,
                     jsonb_array_elements_text(
                         CASE 
                             WHEN jsonb_typeof(tech_stack) = 'array' THEN tech_stack 
                             ELSE '[]'::jsonb 
                         END
                     ) AS item
                WHERE item IS NOT NULL AND trim(item) != ''
                GROUP BY item
                ORDER BY count DESC
                LIMIT 60;
            """)).fetchall()
            for t_name, count in tech_rows:
                if t_name:
                    clean = t_name.strip()
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
                        tech_map[display] += count
        except Exception:
            pass

        sorted_tech = [{"name": k, "count": v} for k, v in sorted(tech_map.items(), key=lambda x: x[0].lower())]
        all_domains = seo_engine.get_all_domains(db)

        _filter_cache["timestamp"] = now
        _filter_cache["data"] = {
            "cities": sorted_cities,
            "tech_stacks": sorted_tech,
            "domains": all_domains,
            "stats": {
                "total": total_valid,
                "enriched": enriched_count,
                "emails": with_emails_count,
                "invalid": invalid_count,
                "contacted": None,
                "is_logged_in": False
            },
            "is_master_admin": False
        }
        print(f"[Cache] Pre-warmed filters cache successfully ({total_valid} valid companies, {len(sorted_cities)} cities).")
        db.close()
    except Exception as e:
        print(f"[Cache Warning] Pre-warming filter cache failed: {e}")


# --- Daily pitch quota: one day = midnight to midnight IST ---
IST = timezone(timedelta(hours=5, minutes=30))


def ist_text(dt, fmt: str = "%b %d, %Y %I:%M %p") -> str:
    """A stored naive-UTC time as India time text, e.g. "Nov 18, 2026 11:43 AM"."""
    return dt.replace(tzinfo=timezone.utc).astimezone(IST).strftime(fmt) if dt else ""


def quota_day_start_utc(now: datetime | None = None) -> datetime:
    """Start of the current quota day (00:00 IST) as a naive UTC datetime,
    matching how timestamps are stored (datetime.utcnow())."""
    now_ist = (now.replace(tzinfo=timezone.utc) if now else datetime.now(timezone.utc)).astimezone(IST)
    midnight_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight_ist.astimezone(timezone.utc).replace(tzinfo=None)


def next_quota_reset_utc(now: datetime | None = None) -> datetime:
    return quota_day_start_utc(now) + timedelta(days=1)


def reset_daily_quota_if_due(user) -> bool:
    """Zero the user's daily pitch counter if it was last reset before today's
    00:00 IST. Returns True when it changed something (caller commits)."""
    last = getattr(user, "last_pitch_reset_date", None)
    if last is None or last < quota_day_start_utc():
        user.pitches_sent_today = 0
        user.last_pitch_reset_date = datetime.utcnow()
        return True
    return False


def reserve_daily_pitches(db: Session, user_id: int, wanted: int) -> int:
    """Atomically take up to `wanted` sends from today's quota and return how many
    were granted (0 = limit reached). The row lock makes parallel sends (two tabs,
    bulk + single) queue up instead of both passing a stale check."""
    if wanted <= 0:
        return 0
    row = db.execute(text("""
        WITH cur AS (
            SELECT id,
                   COALESCE(pitches_sent_today, 0) AS sent,
                   COALESCE(NULLIF(daily_pitch_limit, 0), 10) AS lim
            FROM users WHERE id = :uid FOR UPDATE
        )
        UPDATE users u
        SET pitches_sent_today = cur.sent + LEAST(:wanted, cur.lim - cur.sent)
        FROM cur
        WHERE u.id = cur.id AND cur.sent < cur.lim
        RETURNING LEAST(:wanted, cur.lim - cur.sent)
    """), {"uid": user_id, "wanted": int(wanted)}).fetchone()
    db.commit()
    return int(row[0]) if row else 0


def draft_allowance(db: Session, user) -> tuple[int, int]:
    """Return (new drafts the user may still create today, sends left today).
    New drafts are capped at sends left minus today's unsent drafts, so once the daily
    limit is used the AI writer stops too and users cannot draft here and send by hand."""
    if getattr(user, "is_admin", False) or config.is_master_admin(user.email) or is_subscription_kill_switch_active(db):
        return 999999, 999999
    if reset_daily_quota_if_due(user):
        db.commit()
    sends_left = max(0, (user.daily_pitch_limit or 10) - (user.pitches_sent_today or 0))
    open_drafts = db.query(func.count(ColdPitch.id)).filter(
        ColdPitch.user_id == user.id,
        ColdPitch.status == "DRAFT",
        ColdPitch.created_at >= quota_day_start_utc(),
    ).scalar() or 0
    return max(0, sends_left - open_drafts), sends_left


def resume_profile_or_400(req, user) -> dict:
    """The parsed resume drafts are written from. Without one we refuse rather than invent skills
    or achievements (no fake data)."""
    profile = dict(req.candidate_profile or user.resume_summary or {})
    if not (profile.get("top_skills") or profile.get("key_achievements") or profile.get("strong_points")
            or profile.get("elevator_pitch")):
        raise HTTPException(
            status_code=400,
            detail="Add your resume in Candidate Profile first, so every email uses your real skills."
        )
    profile.setdefault("full_name", user.name or "")
    if not profile.get("target_role"):
        profile["target_role"] = req.target_role or user.target_role or ""
    if user.resume_link and not profile.get("resume_link"):
        profile["resume_link"] = user.resume_link
    return profile


def daily_limit_reached_error(user) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail=(f"You have used today's {user.daily_pitch_limit or 10} applications. "
                "Writing new emails opens again at midnight (IST)."),
    )


def _bulk_reset_daily_quotas() -> int:
    """Reset every user whose counter is from a previous IST day in one UPDATE.
    Idempotent, so it is safe with several workers or a late wake-up."""
    try:
        with SessionLocal() as s:
            n = (
                s.query(User)
                .filter(or_(User.last_pitch_reset_date.is_(None),
                            User.last_pitch_reset_date < quota_day_start_utc()))
                .update({User.pitches_sent_today: 0, User.last_pitch_reset_date: datetime.utcnow()},
                        synchronize_session=False)
            )
            s.commit()
            return n or 0
    except Exception as e:
        print(f"[Quota] Daily reset failed: {e}")
        return 0


async def _daily_quota_reset_loop():
    """Runs the bulk reset at startup and then just after each midnight IST.
    The per-request check in get_current_user stays as the guarantee, so a
    sleeping or restarted server never leaves a user blocked."""
    while True:
        n = await asyncio.to_thread(_bulk_reset_daily_quotas)
        if n:
            print(f"[Quota] Reset daily pitch counters for {n} user(s).")
        wait = (next_quota_reset_utc() - datetime.utcnow()).total_seconds() + 5
        await asyncio.sleep(max(60, wait))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    asyncio.create_task(asyncio.to_thread(_prewarm_cache))
    quota_task = asyncio.create_task(_daily_quota_reset_loop())
    # Local dev shares the production DB: set SEND_QUEUE_WORKER=false there so only production sends.
    send_queue_task = None
    if os.getenv("SEND_QUEUE_WORKER", "true").lower() in ("true", "1", "yes"):
        send_queue_task = asyncio.create_task(run_send_queue())
    yield
    quota_task.cancel()
    if send_queue_task:
        send_queue_task.cancel()


app = FastAPI(
    title=config.PROJECT_NAME,
    description=config.APP_DESCRIPTOR,
    lifespan=lifespan
)

# Ensure font and vector MIME types are registered consistently across OS images (Render Linux / Windows)
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/woff", ".woff")
mimetypes.add_type("image/svg+xml", ".svg")


class CachedStaticFiles(StaticFiles):
    """StaticFiles subclass adding explicit CORS and CDN/browser Cache-Control headers."""

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            lower_path = path.lower()
            response.headers.setdefault("Access-Control-Allow-Origin", "*")
            response.headers.setdefault("Timing-Allow-Origin", "*")
            if lower_path.endswith((".woff2", ".woff", ".ttf", ".otf", ".eot", ".svg", ".png", ".ico", ".webp")):
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            elif lower_path.endswith((".css", ".js")) and b"v=" in scope.get("query_string", b""):
                # ?v=<asset_v> changes on every release, so this URL's content never changes.
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            elif lower_path.endswith((".css", ".js")):
                response.headers["Cache-Control"] = "public, max-age=86400, s-maxage=604800, stale-while-revalidate=604800"
            else:
                response.headers.setdefault("Cache-Control", "public, max-age=3600")
        return response


# Mount static and templates
app.mount("/static", CachedStaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- One render-blocking stylesheet per page instead of ~12 ---------------------
# templates/partials/head_assets.html links /assets/site.css?p=<page css>&v=<asset_v>.
# Order matters: fonts, tokens, base, components, then the page's own sheets.
_CORE_CSS = [
    "core/fonts.css", "core/tokens.css", "core/base.css",
    "components/buttons.css", "components/forms.css", "components/chips.css", "components/cards.css",
    "components/nav.css", "components/footer.css", "components/overlays.css", "components/data.css",
]
_PAGE_CSS_RE = re.compile(r"^(?:(?:app|pages)/)?[a-z0-9-]+\.css$")
_css_bundle_cache: dict[str, str] = {}


@app.get("/assets/site.css")
def css_bundle(p: str = "", v: str = ""):
    """Core CSS + the page's sheets (p: comma list; bare names live in static/css/pages/)."""
    pages = []
    for name in (x.strip() for x in p.split(",") if x.strip()):
        if not _PAGE_CSS_RE.match(name):
            raise HTTPException(status_code=400, detail="Bad stylesheet name")
        pages.append(name if "/" in name else f"pages/{name}")
    key = ",".join(pages)
    css = _css_bundle_cache.get(key)
    if css is None:
        parts = []
        for rel in _CORE_CSS + pages:
            path = os.path.join("static", "css", rel)
            if not os.path.isfile(path):
                raise HTTPException(status_code=404, detail=f"Missing stylesheet {rel}")
            with open(path, encoding="utf-8") as fh:
                parts.append(f"/* {rel} */\n{fh.read()}")
        css = "\n".join(parts)
        _css_bundle_cache[key] = css
    cache = "public, max-age=31536000, immutable" if v else "public, max-age=3600"
    return Response(content=css, media_type="text/css", headers={"Cache-Control": cache})


# --- Maintenance Mode Middleware ---
@app.middleware("http")
async def maintenance_mode_middleware(request: Request, call_next):
    if config.is_maintenance_mode():
        path = request.url.path
        # Allowed routes: health checks, landing page, directory, SEO, GEO, sitemaps, maintenance page, static assets, and icons
        is_allowed = (
            path in ("/health", "/healthz", "/", "/home", "/landing", "/maintenance", "/privacy", "/terms", "/unsubscribe",
                     "/favicon.ico", "/apple-touch-icon.png", "/apple-touch-icon-precomposed.png",
                     "/robots.txt", "/llms.txt", "/llms-full.txt", "/sitemap.xml",
                     "/sitemap-core.xml", "/sitemap-cities.xml", "/sitemap-tech.xml", "/sitemap-directory.xml")
            or path.startswith("/static/")
            or path.startswith("/assets/")
            or path.startswith("/directory")
            or path.startswith("/company/")
            or path.startswith("/sitemap-companies-")
            or (path.startswith("/google") and path.endswith(".html"))
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
    max_pages: int = 0
    gl: str = "in"
    hl: str = "en"


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


class UpdatePlanRequest(BaseModel):
    tier: str
    custom_limit: int | None = None


class BanUserRequest(BaseModel):
    is_banned: bool
    reason: str | None = None


class AddCompanyAdminRequest(BaseModel):
    name: str
    domain: str
    category: str | None = "Information Technology & Software"
    city: str | None = ""
    email: str | None = ""
    phone: str | None = ""
    tech_stack: str | None = ""
    summary: str | None = ""


class UpdateCompanyAdminRequest(BaseModel):
    name: str
    domain: str
    website_url: str | None = None
    category: str | None = None
    city: str | None = None
    email: str | None = None
    phone: str | None = None
    tech_stack: str | None = None
    summary: str | None = None
    is_invalid: bool | None = False
    invalid_reason: str | None = None


class QuarantineCompanyRequest(BaseModel):
    reason: str = "Quarantined by Master Admin"


class BulkCompanyActionRequest(BaseModel):
    ids: list[int]
    action: str  # "quarantine" | "delete"
    reason: str = "Quarantined by Master Admin"


class UpdateTierRequest(BaseModel):
    name: str
    subtitle: str | None = None
    price_inr: int
    daily_pitch_limit: int
    features: list[str] | None = None
    badge: str | None = None
    is_active: bool = True
    sync_users: bool = True


class CreateTierRequest(BaseModel):
    code: str
    name: str
    subtitle: str | None = None
    price_inr: int = 0
    daily_pitch_limit: int = 10
    features: list[str] | None = None
    badge: str | None = None


class SanitizeNamesRequest(BaseModel):
    dry_run: bool = False
    limit: int = 2000


class PurgeNonCompaniesRequest(BaseModel):
    dry_run: bool = False
    limit: int = 5000


class DispatchWorkflowRequest(BaseModel):
    ref: str = "main"
    inputs: dict[str, Any] = {}
    github_token: str | None = None


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
                is_admin=is_admin,
                daily_pitch_limit=999999 if is_admin else 10,
                subscription_tier="premium_plus" if is_admin else "free",
                daily_send_limit=100 if is_admin else 50
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        except Exception:
            db.rollback()
            user = db.query(User).filter(User.email == email).first()

    if user:
        needs_commit = False
        # Bootstrap check for master admin from config
        if config.is_master_admin(user.email) and not getattr(user, "is_admin", False):
            user.is_admin = True
            user.daily_pitch_limit = 999999
            user.subscription_tier = "premium_plus"
            needs_commit = True

        # Daily pitch quota resets at midnight IST.
        if reset_daily_quota_if_due(user):
            needs_commit = True

        if needs_commit:
            try:
                db.commit()
            except Exception:
                db.rollback()

    return user


def require_master_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """Dependency that ensures the authenticated caller possesses Master Admin privileges."""
    user = get_current_user(db, request)
    if not user or not user.oauth_tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please connect your Google account."
        )
    if getattr(user, "is_banned", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account suspended: {user.ban_reason or 'Access denied.'}"
        )
    if not (getattr(user, "is_admin", False) or config.is_master_admin(user.email)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Master Admin privileges required."
        )
    return user


@app.api_route("/healthz", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route("/health", methods=["GET", "HEAD"], include_in_schema=False)
def health_check():
    """Zero-DB readiness/liveness probe for Render health checks and external keep-alive monitors."""
    return JSONResponse(
        content={"status": "ok", "service": config.PROJECT_NAME},
        headers={"Cache-Control": "no-store"}
    )


@app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
def favicon():
    return FileResponse(
        "static/favicon.ico",
        headers={
            "Cache-Control": "public, max-age=604800, s-maxage=604800",
            "Access-Control-Allow-Origin": "*",
        }
    )


@app.api_route("/apple-touch-icon.png", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route("/apple-touch-icon-precomposed.png", methods=["GET", "HEAD"], include_in_schema=False)
def apple_touch_icon():
    return FileResponse(
        "static/img/apple-touch-icon.png",
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=604800, s-maxage=604800",
            "Access-Control-Allow-Origin": "*",
        }
    )


# --- Master Kill Switch & Subscription Helpers ---
def is_subscription_kill_switch_active(db: Session = None) -> bool:
    """
    Checks if the Master Kill Switch is enabled.
    When active:
    - Completely suppresses subscription UI/DOM from landing and app pages.
    - Designates all users as Temp Users with infinite cold pitch generation and zero quota limits.
    - Bypasses RBAC subscription paywalls.
    """
    # 1. Fast path: check DB if session provided or query DB
    try:
        if db:
            setting = db.query(SystemSetting).filter(SystemSetting.key == "subscription_kill_switch").first()
            if setting:
                return setting.value.strip().lower() in ("true", "1", "yes")
        else:
            with SessionLocal() as s:
                setting = s.query(SystemSetting).filter(SystemSetting.key == "subscription_kill_switch").first()
                if setting:
                    return setting.value.strip().lower() in ("true", "1", "yes")
    except Exception:
        pass

    # 2. Local JSON state file fallback (persists across restarts)
    try:
        settings_file = Path(__file__).parent / "var" / "system_settings.json"
        if settings_file.exists():
            with open(settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                val = data.get("subscription_kill_switch")
                if val is not None:
                    return bool(val)
    except Exception:
        pass

    # 3. Environment variable fallback
    return os.getenv("SUBSCRIPTION_KILL_SWITCH", "").strip().lower() in ("true", "1", "yes")


def set_subscription_kill_switch(active: bool, db: Session = None) -> bool:
    """Sets the subscription kill switch state across DB, local file, and environment."""
    val_str = "true" if active else "false"
    os.environ["SUBSCRIPTION_KILL_SWITCH"] = val_str

    # 1. Update local state file
    try:
        var_dir = Path(__file__).parent / "var"
        var_dir.mkdir(parents=True, exist_ok=True)
        settings_file = var_dir / "system_settings.json"
        data = {}
        if settings_file.exists():
            try:
                with open(settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data["subscription_kill_switch"] = active
        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[Warning] Could not write system_settings.json: {e}")

    # 2. Update DB
    def _update(s: Session):
        setting = s.query(SystemSetting).filter(SystemSetting.key == "subscription_kill_switch").first()
        if not setting:
            setting = SystemSetting(
                key="subscription_kill_switch",
                value=val_str,
                description="Master Kill Switch: Bypass Subscriptions & RBAC for All Users"
            )
            s.add(setting)
        else:
            setting.value = val_str
            setting.updated_at = datetime.utcnow()
        s.commit()

    try:
        if db:
            _update(db)
        else:
            with SessionLocal() as s:
                _update(s)
    except Exception as ex:
        print(f"[Warning] Could not save kill switch to DB: {ex}")

    return active


# --- Public plans: what visitors see on the home page and in the workspace ---
# Read from the subscription_tiers table that the admin panel (Tiers & Plans)
# edits, so admin changes show up everywhere. Cached for a few minutes; the
# admin create/update endpoints clear the cache so edits appear immediately.
_PUBLIC_TIERS_CACHE: dict = {"ts": 0.0, "data": None}
_PUBLIC_TIERS_TTL = 300


def load_public_tiers(db: Session) -> list[dict]:
    now = time.time()
    cached = _PUBLIC_TIERS_CACHE["data"]
    if cached is not None and now - _PUBLIC_TIERS_CACHE["ts"] < _PUBLIC_TIERS_TTL:
        return cached
    rows = (
        db.query(SubscriptionTier)
        .filter(SubscriptionTier.is_active.is_(True), SubscriptionTier.code != "master_admin")
        .order_by(SubscriptionTier.price_inr.asc(), SubscriptionTier.id.asc())
        .all()
    )
    data = [
        {
            "code": t.code,
            "name": t.name,
            "subtitle": (t.subtitle or "").strip(),
            "price_inr": int(t.price_inr or 0),
            "daily_pitch_limit": int(t.daily_pitch_limit or 0),
            "features": [f.strip() for f in (t.features or []) if f and str(f).strip()],
            "badge": (t.badge or "").strip(),
        }
        for t in rows
    ]
    _PUBLIC_TIERS_CACHE.update(ts=now, data=data)
    return data


def clear_public_tiers_cache() -> None:
    _PUBLIC_TIERS_CACHE.update(ts=0.0, data=None)


# --- Subscription & Quota Resolution Helper ---
def get_user_subscription_info(user: User | None, db: Session) -> dict:
    kill_switch_active = is_subscription_kill_switch_active(db)
    tier_name_map = {
        "free": "Free Job Seeker",
        "pro": "Job Seeker Pro",
        "premium_plus": "Premium+",
        "master_admin": "Master Admin Persona"
    }
    if not user or not user.oauth_tokens:
        return {
            "tier_code": "guest",
            "tier_name": "Free Job Seeker",
            "daily_pitch_limit": 0,
            "pitches_sent_today": 0,
            "pitches_remaining": 0,
            "status": "guest",
            "is_master_admin": False,
            "kill_switch_active": kill_switch_active
        }

    is_master = bool(getattr(user, "is_admin", False) or config.is_master_admin(user.email))
    tier_code = getattr(user, "subscription_tier", "free") or "free"

    tier_obj = db.query(SubscriptionTier).filter(SubscriptionTier.code == tier_code).first()
    tier_name = tier_obj.name if tier_obj else tier_name_map.get(tier_code, tier_code.title())
    if is_master:
        tier_name = "Master Admin"
    elif kill_switch_active:
        tier_name = "Temp User (Unlimited Applications)"
        tier_code = "temp_user"

    daily_limit = 999999 if (is_master or kill_switch_active) else (getattr(user, "daily_pitch_limit", 10) or 10)
    sent_today = getattr(user, "pitches_sent_today", 0) or 0
    remaining = 999999 if (is_master or kill_switch_active) else max(0, daily_limit - sent_today)

    return {
        "tier_code": tier_code,
        "tier_name": tier_name,
        "daily_pitch_limit": daily_limit,
        "pitches_sent_today": sent_today,
        "pitches_remaining": remaining,
        "status": getattr(user, "subscription_status", "active") or "active",
        "is_master_admin": is_master,
        "kill_switch_active": kill_switch_active
    }


# --- UI Routes ---
@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
@app.api_route("/home", methods=["GET", "HEAD"], response_class=HTMLResponse)
def landing_page(request: Request, db: Session = Depends(get_db)):
    """Dedicated craft-first Landing Home Page for OutreachPilot"""
    user = get_current_user(db, request)
    is_logged_in = bool(user and user.oauth_tokens)
    sub_info = get_user_subscription_info(user, db)
    kill_switch = sub_info.get("kill_switch_active", False)
    
    # Plans for the pricing section, exactly as set in the admin panel
    # (empty while the kill switch is on, which hides pricing).
    public_tiers = [] if kill_switch else load_public_tiers(db)

    # Largest city and category hubs for the crawlable "Browse the directory" section.
    # Both lists come from cached aggregates; on any failure the section simply hides.
    try:
        browse_cities = sorted(seo_engine.get_all_cities(db), key=lambda c: -int(c.get("count") or 0))[:12]
        browse_categories = sorted(seo_engine.get_all_categories(db), key=lambda c: -int(c.get("count") or 0))[:12]
    except Exception:
        browse_cities, browse_categories = [], []

    return templates.TemplateResponse(
        request=request,
        name="landing.html",
        context={
            "project_name": config.PROJECT_NAME,
            "tagline": config.TAGLINE,
            "app_descriptor": config.APP_DESCRIPTOR,
            "user": user,
            "is_logged_in": is_logged_in,
            "sub_info": sub_info,
            "tiers": public_tiers,
            "google_client_id": config.GOOGLE_CLIENT_ID,
            "dev_mode": config.DEV_MODE,
            "subscription_kill_switch": kill_switch,
            "browse_cities": browse_cities,
            "browse_categories": browse_categories,
        }
    )


@app.get("/landing")
async def redirect_landing_to_home():
    return RedirectResponse(url="/", status_code=301)


@app.api_route("/app", methods=["GET", "HEAD"], response_class=HTMLResponse)
@app.api_route("/workspace", methods=["GET", "HEAD"], response_class=HTMLResponse)
def workspace_page(request: Request, db: Session = Depends(get_db)):
    """Original Scraping Logic & Outreach Workspace Directory"""
    if config.is_maintenance_mode():
        return RedirectResponse(url="/maintenance", status_code=307)
    user = get_current_user(db, request)
    is_logged_in = bool(user and user.oauth_tokens)
    is_master_admin = bool(is_logged_in and (getattr(user, "is_admin", False) or config.is_master_admin(user.email)))
    all_domains = seo_engine.get_all_domains(db)
    total_valid = sum(d.get("count", 0) for d in all_domains)
    sub_info = get_user_subscription_info(user, db)
    kill_switch = sub_info.get("kill_switch_active", False)
    
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
            "sub_info": sub_info,
            "subscription_kill_switch": kill_switch,
            "user_subscription_tier": sub_info["tier_code"],
            "user_subscription_tier_name": sub_info["tier_name"],
            "user_daily_limit": sub_info["daily_pitch_limit"],
            "user_sent_today": sub_info["pitches_sent_today"],
            "user_remaining": sub_info["pitches_remaining"],
            "google_client_id": config.GOOGLE_CLIENT_ID,
            "dev_mode": config.DEV_MODE,
            "domains": all_domains,
            "total_companies": total_valid,
            # Plan cards in the subscription window, as set in the admin panel
            "tiers": [] if kill_switch else load_public_tiers(db),
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


@app.api_route("/privacy", methods=["GET", "HEAD"], response_class=HTMLResponse)
def privacy_page(request: Request):
    """Public Privacy Policy required by Google OAuth API verification"""
    return templates.TemplateResponse(
        request=request,
        name="privacy.html",
        context={"project_name": config.PROJECT_NAME}
    )


@app.api_route("/terms", methods=["GET", "HEAD"], response_class=HTMLResponse)
def terms_page(request: Request):
    """Public Terms of Service required by Google OAuth API verification"""
    return templates.TemplateResponse(
        request=request,
        name="terms.html",
        context={"project_name": config.PROJECT_NAME}
    )


def _optout_page(title: str, message: str, form_token: str | None = None) -> HTMLResponse:
    import html as _html
    form = (
        '<form method="post"><input type="hidden" name="t" value="' + _html.escape(form_token) + '">'
        '<button type="submit">Opt out</button></form>'
    ) if form_token else ""
    return HTMLResponse(
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><meta name=robots content=noindex>"
        f"<title>{_html.escape(title)} | OutreachPilot</title><style>"
        "body{font-family:system-ui,sans-serif;max-width:520px;margin:15vh auto;padding:0 16px;"
        "background:#faf9f6;color:#1f2420;line-height:1.5}"
        "@media(prefers-color-scheme:dark){body{background:#161a17;color:#e8ebe6}}"
        "button{font:inherit;padding:10px 20px;border-radius:8px;border:0;background:#2f5d46;color:#fff;cursor:pointer}"
        f"</style></head><body><h1>{_html.escape(title)}</h1><p>{message}</p>{form}</body></html>"
    )


@app.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe_page(t: str = ""):
    """Opt-out link in every email. Shows a confirm button so link scanners do not opt people out."""
    import html as _html
    email = read_optout_token(t)
    if not email:
        return _optout_page("Link not valid", "This opt-out link is broken or incomplete.")
    return _optout_page(
        "Stop these emails?",
        f"No OutreachPilot user will be able to email <b>{_html.escape(email)}</b> again.",
        form_token=t,
    )


@app.post("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_confirm(request: Request, t: str = "", db: Session = Depends(get_db)):
    """Confirm button and RFC 8058 one-click (Gmail posts List-Unsubscribe=One-Click with ?t= in the URL)."""
    import html as _html
    form = await request.form()
    email = read_optout_token(t or str(form.get("t") or ""))
    if not email:
        return _optout_page("Link not valid", "This opt-out link is broken or incomplete.")
    add_do_not_contact(db, email)
    return _optout_page("You are opted out",
                        f"No OutreachPilot user will email <b>{_html.escape(email)}</b> again.")


# ==============================================================================
# PROGRAMMATIC SEO, AEO & GEO SUITE (GEO / Sitemaps / Directories / Companies)
# ==============================================================================

@app.get("/google{token}.html", include_in_schema=False)
async def google_verification_file(token: str):
    """
    Auto-verifies Google Search Console site ownership via HTML file upload method.
    Google requires:
      - File location: https://outreachpilot.in/google[token].html
      - Body: google-site-verification: google[token].html
    Supports either actual file on disk or dynamic string response matching GSC requirements.
    """
    try:
        clean_token = "".join(c for c in token if c.isalnum() or c in "-_")
        filename = f"google{clean_token}.html"
        file_path = os.path.join(os.path.dirname(__file__), filename)
        if os.path.exists(file_path):
            return FileResponse(file_path, media_type="text/html")
        # text/plain + sanitized token only: never reflect raw user input as HTML.
        return PlainTextResponse(content=f"google-site-verification: google{clean_token}.html\n", status_code=200)
    except Exception:
        # Fallback must also use the sanitized token and a non-HTML content type.
        safe = "".join(c for c in (token or "") if c.isalnum() or c in "-_")
        return PlainTextResponse(content=f"google-site-verification: google{safe}.html\n", status_code=200)


@app.api_route("/robots.txt", methods=["GET", "HEAD"], include_in_schema=False)
def robots_txt(request: Request):
    """AI-friendly, crawler-optimized robots.txt explicitly unblocking GPTBot, ClaudeBot, etc."""
    base_url = seo_engine.get_canonical_base_url(request)
    content = seo_engine.generate_robots_txt(base_url)
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "public, max-age=86400, s-maxage=86400, stale-while-revalidate=604800",
            "X-Robots-Tag": "noindex",
        }
    )


@app.api_route("/llms.txt", methods=["GET", "HEAD"], include_in_schema=False)
def llms_txt(request: Request, db: Session = Depends(get_db)):
    """Standardized LLM Context File per llmstxt.org specification"""
    base_url = seo_engine.get_canonical_base_url(request)
    content = seo_engine.generate_llms_txt(base_url, db)
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "public, max-age=86400, s-maxage=86400"}
    )


@app.api_route("/llms-full.txt", methods=["GET", "HEAD"], include_in_schema=False)
def llms_full_txt(request: Request, db: Session = Depends(get_db)):
    """Machine-readable LLM knowledge base for AI crawlers"""
    base_url = seo_engine.get_canonical_base_url(request)
    content = seo_engine.generate_llms_full_txt(base_url, db)
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "public, max-age=86400, s-maxage=86400"}
    )


@app.api_route("/sitemap.xml", methods=["GET", "HEAD"], include_in_schema=False)
def sitemap_index_endpoint(request: Request, db: Session = Depends(get_db)):
    """Master XML Sitemap Index referencing all sub-sitemaps"""
    base_url = seo_engine.get_canonical_base_url(request)
    content = seo_engine.generate_sitemap_index(base_url, db)
    return Response(
        content=content,
        media_type="application/xml; charset=utf-8",
        headers={"Cache-Control": "public, max-age=86400, s-maxage=86400"}
    )


@app.api_route("/sitemap-core.xml", methods=["GET", "HEAD"], include_in_schema=False)
def sitemap_core_endpoint(request: Request):
    """Core Pages XML Sitemap"""
    base_url = seo_engine.get_canonical_base_url(request)
    content = seo_engine.generate_sitemap_core(base_url)
    return Response(
        content=content,
        media_type="application/xml; charset=utf-8",
        headers={"Cache-Control": "public, max-age=86400, s-maxage=86400"}
    )


@app.api_route("/sitemap-cities.xml", methods=["GET", "HEAD"], include_in_schema=False)
def sitemap_cities_endpoint(request: Request, db: Session = Depends(get_db)):
    """All 73 Indian City Hubs XML Sitemap"""
    base_url = seo_engine.get_canonical_base_url(request)
    content = seo_engine.generate_sitemap_cities(base_url, db)
    return Response(
        content=content,
        media_type="application/xml; charset=utf-8",
        headers={"Cache-Control": "public, max-age=86400, s-maxage=86400"}
    )


@app.api_route("/sitemap-tech.xml", methods=["GET", "HEAD"], include_in_schema=False)
def sitemap_tech_endpoint(request: Request, db: Session = Depends(get_db)):
    """All 36 Engineering Stacks XML Sitemap"""
    base_url = seo_engine.get_canonical_base_url(request)
    content = seo_engine.generate_sitemap_tech(base_url, db)
    return Response(
        content=content,
        media_type="application/xml; charset=utf-8",
        headers={"Cache-Control": "public, max-age=86400, s-maxage=86400"}
    )


@app.api_route("/sitemap-directory.xml", methods=["GET", "HEAD"], include_in_schema=False)
def sitemap_directory_endpoint(request: Request, db: Session = Depends(get_db)):
    """Programmatic City + Technology Combinations XML Sitemap"""
    base_url = seo_engine.get_canonical_base_url(request)
    content = seo_engine.generate_sitemap_directory(base_url, db)
    return Response(
        content=content,
        media_type="application/xml; charset=utf-8",
        headers={"Cache-Control": "public, max-age=86400, s-maxage=86400"}
    )


@app.api_route("/sitemap-companies-{page}.xml", methods=["GET", "HEAD"], include_in_schema=False)
def sitemap_companies_endpoint(page: int, request: Request, db: Session = Depends(get_db)):
    """Paginated Company Profiles XML Sitemap (5,000 URLs per file)"""
    if page < 1:
        raise HTTPException(status_code=404, detail="Sitemap page not found")
    base_url = seo_engine.get_canonical_base_url(request)
    content = seo_engine.generate_sitemap_companies(base_url, page, db)
    return Response(
        content=content,
        media_type="application/xml; charset=utf-8",
        headers={"Cache-Control": "public, max-age=86400, s-maxage=86400"}
    )


# --- Programmatic Directory Routes (pSEO & AEO) ---

@app.api_route("/directory", methods=["GET", "HEAD"], response_class=HTMLResponse)
def directory_index_page(request: Request, db: Session = Depends(get_db)):
    """Company directory homepage for job seekers."""
    base_url = seo_engine.get_canonical_base_url(request)
    canonical_url = f"{base_url}/directory"
    stats = seo_engine.get_directory_stats(db)
    cities = seo_engine.get_all_cities(db)
    technologies = seo_engine.get_all_technologies(db)
    domains = seo_engine.get_all_domains(db)

    breadcrumbs = [("Home", f"{base_url}/"), ("Directory", canonical_url)]
    bc_schema = seo_engine.build_breadcrumb_schema(breadcrumbs)
    faq_schema = seo_engine.build_faq_schema([
        {
            "question": "How does OutreachPilot verify technology stacks and company data?",
            "answer": "OutreachPilot utilizes an autonomous multi-pass crawler that directly analyzes live company website source code to detect actual production frameworks."
        },
        {
            "question": "Can I contact the recruiters and engineering leads of these companies?",
            "answer": "Yes. OutreachPilot extracts verified contact emails and enables users to draft hyper-personalized opportunity pitches sent directly through your authorized personal Gmail via OAuth 2.0."
        },
        {
            "question": "How often is the directory intelligence updated?",
            "answer": "Company profiles are re-crawled continuously to detect technology stack changes, new job openings, domain health, and Google review updates."
        }
    ])
    combined_schema = json.dumps([bc_schema, faq_schema], ensure_ascii=False)

    response = templates.TemplateResponse(
        request=request,
        name="directory.html",
        context={
            "project_name": config.PROJECT_NAME,
            "canonical_url": canonical_url,
            "stats": stats,
            "cities": cities,
            "technologies": technologies,
            "domains": domains,
            "json_ld_schema": combined_schema
        }
    )
    response.headers["Cache-Control"] = "public, max-age=3600, s-maxage=86400, stale-while-revalidate=604800"
    return response


@app.api_route("/directory/city/{city_slug}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def directory_city_hub(city_slug: str, request: Request, db: Session = Depends(get_db)):
    """City-Level Technology & Business Directory Hub (73 Indian Cities)"""
    city_name = seo_engine.slug_to_city_name(city_slug)
    domain_param = request.query_params.get("domain")
    domain_clean = (domain_param or "").strip().lower() or None
    # Accept an industry's code or slug (e.g. "it" or "it-software"); anything
    # else (including "all") means no industry filter: every company in the city.
    dom_info = next(
        (d for d in seo_engine.INDUSTRY_DOMAINS if domain_clean in (d["code"], d.get("slug"))),
        None,
    ) if domain_clean else None
    domain_clean = dom_info["code"] if dom_info else None

    all_cities = seo_engine.get_all_cities(db)
    city_match = next((c for c in all_cities if c["slug"] == city_slug), None)
    if not city_match:
        raise HTTPException(status_code=404, detail=f"No verified business cluster found for city: {city_name}")

    companies, total_count = seo_engine.get_companies_list(db, city=city_name, domain=domain_clean, limit=30)

    base_url = seo_engine.get_canonical_base_url(request)
    canonical_url = f"{base_url}/directory/city/{city_slug}" + (f"?domain={domain_clean}" if domain_clean else "")

    # Without an industry the page lists every company in the city, so the wording
    # stays general (it used to fall back to "Software & IT").
    if dom_info:
        dom_display = dom_info["name"]
        page_heading = f"{dom_display} Companies in {city_name} You Can Apply To"
        hub_badge = f"Verified companies in {city_name} ({dom_display})"
        companies_noun = f"{dom_display} companies"
    else:
        page_heading = f"Companies in {city_name} You Can Apply To"
        hub_badge = f"Verified companies in {city_name}"
        companies_noun = "companies"

    workspace_params = {"city": city_name}
    if domain_clean:
        workspace_params["domain"] = domain_clean
    workspace_url = "/app?" + urllib.parse.urlencode(workspace_params)

    all_combos = seo_engine.get_all_combinations(db)
    city_combos = [c for c in all_combos if c["city_slug"] == city_slug]
    if domain_clean:
        filtered_combos = [c for c in city_combos if seo_engine.get_category_domain_code(c["tech_name"]) == domain_clean]
        active_combos = filtered_combos if filtered_combos else city_combos
    else:
        active_combos = city_combos

    related_items = [
        {"name": c["tech_name"], "url": f"{base_url}/directory/companies?city={city_slug}&tech={c['tech_slug']}", "count": c["count"]}
        for c in active_combos[:16]
    ]
    top_tech_names = [c["tech_name"] for c in active_combos[:5]]
    # Average Google rating straight from the database aggregate for the whole city.
    # With an industry filter there is no exact aggregate, so none is shown.
    avg_rating = city_match.get("avg_rating") if not domain_clean else None

    faqs = seo_engine.generate_city_faqs(city_name, total_count, top_tech_names)

    breadcrumbs = [
        ("Home", f"{base_url}/"),
        ("Directory", f"{base_url}/directory"),
        (city_name, canonical_url)
    ]
    bc_schema = seo_engine.build_breadcrumb_schema(breadcrumbs)
    itemlist_schema = seo_engine.build_itemlist_schema(companies, base_url, page_heading)
    faq_schema = seo_engine.build_faq_schema(faqs)
    combined_schema = json.dumps([bc_schema, itemlist_schema, faq_schema], ensure_ascii=False)

    field_label = dom_info["name"] if dom_info else ""
    page_title = (f"{field_label} " if field_label else "") + f"Companies in {city_name} to Apply To ({seo_engine.SEO_YEAR}): Jobs & Careers Emails"
    page_subtitle = (f"{total_count:,} {companies_noun} in {city_name}, India, with what each one does, its Google rating "
                     f"and the email it publishes for job applications. Send your resume directly, as a fresher or an experienced professional.")
    meta_description = (f"Looking for jobs in {city_name}? Browse {total_count:,} {companies_noun} in {city_name} you can apply to directly, "
                        f"with the careers or contact email each one publishes. For freshers and experienced job seekers.")
    meta_keywords = seo_engine.job_seeker_keywords(city=city_name, field=field_label)

    response = templates.TemplateResponse(
        request=request,
        name="directory_hub.html",
        context={
            "project_name": config.PROJECT_NAME,
            "canonical_url": canonical_url,
            "page_title": page_title,
            "page_heading": page_heading,
            "page_subtitle": page_subtitle,
            "meta_description": meta_description,
            "meta_keywords": meta_keywords,
            "hub_name": city_name,
            "hub_badge": hub_badge,
            "workspace_url": workspace_url,
            "total_companies": total_count,
            "avg_rating": avg_rating,
            "related_title": f"Top Specializations in {city_name}",
            "related_items": related_items,
            "companies": companies,
            "faqs": faqs,
            "json_ld_schema": combined_schema
        }
    )
    response.headers["Cache-Control"] = "public, max-age=3600, s-maxage=86400, stale-while-revalidate=604800"
    return response


@app.api_route("/directory/tech/{tech_slug}", methods=["GET", "HEAD"], response_class=HTMLResponse)
@app.api_route("/directory/category/{tech_slug}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def directory_tech_hub(tech_slug: str, request: Request, db: Session = Depends(get_db)):
    """Category & Technology Specialization Hub (Dynamic Across All Industries)"""
    seo_engine.ensure_category_maps(db)
    tech_name = seo_engine.slug_to_tech_name(tech_slug)
    companies, total_count = seo_engine.get_companies_list(db, tech=tech_name, limit=30)
    if total_count == 0:
        raise HTTPException(status_code=404, detail=f"No verified companies found for category/tech: {tech_name}")

    base_url = seo_engine.get_canonical_base_url(request)
    canonical_url = f"{base_url}/directory/tech/{tech_slug}"

    all_combos = seo_engine.get_all_combinations(db)
    tech_combos = [c for c in all_combos if c["tech_slug"] == tech_slug]
    related_items = [
        {"name": c["city_name"], "url": f"{base_url}/directory/companies?city={c['city_slug']}&tech={tech_slug}", "count": c["count"]}
        for c in tech_combos[:16]
    ]
    top_city_names = [c["city_name"] for c in tech_combos[:5]]
    # Average Google rating straight from the database aggregate for this category.
    cat_match = next((t for t in seo_engine.get_all_categories(db) if t.get("slug") == tech_slug), None)
    avg_rating = cat_match.get("avg_rating") if cat_match else None

    faqs = seo_engine.generate_tech_faqs(tech_name, total_count, top_city_names)

    breadcrumbs = [
        ("Home", f"{base_url}/"),
        ("Directory", f"{base_url}/directory"),
        (tech_name, canonical_url)
    ]
    bc_schema = seo_engine.build_breadcrumb_schema(breadcrumbs)
    itemlist_schema = seo_engine.build_itemlist_schema(companies, base_url, f"Top {tech_name} Companies in India")
    faq_schema = seo_engine.build_faq_schema(faqs)
    combined_schema = json.dumps([bc_schema, itemlist_schema, faq_schema], ensure_ascii=False)

    page_title = f"{tech_name} Companies in India to Apply To ({seo_engine.SEO_YEAR}): Jobs & Careers Emails"
    page_subtitle = (f"{total_count:,} {tech_name} companies across India, with what each one does, its Google rating "
                     f"and the email it publishes for job applications.")
    meta_description = (f"Find {tech_name} jobs in India: {total_count:,} {tech_name} companies you can apply to directly, "
                        f"with the careers or contact email each one publishes. For freshers and experienced professionals.")
    meta_keywords = seo_engine.job_seeker_keywords(field=tech_name)

    response = templates.TemplateResponse(
        request=request,
        name="directory_hub.html",
        context={
            "project_name": config.PROJECT_NAME,
            "canonical_url": canonical_url,
            "page_title": page_title,
            "page_heading": f"{tech_name} Companies in India You Can Apply To",
            "page_subtitle": page_subtitle,
            "meta_description": meta_description,
            "meta_keywords": meta_keywords,
            "hub_name": tech_name,
            "hub_badge": f"Verified {tech_name} companies",
            "workspace_url": "/app?" + urllib.parse.urlencode({"tech": tech_name}),
            "total_companies": total_count,
            "avg_rating": avg_rating,
            "related_title": f"Top Indian Cities for {tech_name}",
            "related_items": related_items,
            "companies": companies,
            "faqs": faqs,
            "json_ld_schema": combined_schema
        }
    )
    response.headers["Cache-Control"] = "public, max-age=3600, s-maxage=86400, stale-while-revalidate=604800"
    return response


@app.api_route("/directory/companies", methods=["GET", "HEAD"], response_class=HTMLResponse)
def directory_companies(
    request: Request,
    city: Optional[str] = Query(None, description="City slug or name, e.g. noida, mumbai"),
    tech: Optional[str] = Query(None, description="Category or tech stack slug/name, e.g. nextjs, dentists"),
    category: Optional[str] = Query(None, description="Industry/category alias for tech parameter"),
    domain: Optional[str] = Query(None, description="High-level industry domain, e.g. it, pharma, sales"),
    q: Optional[str] = Query(None, description="General search term"),
    db: Session = Depends(get_db)
):
    """
    Parameterized company directory landing pages for job seekers.
    Supports query parameters: ?city=noida&tech=nextjs and ?city=mumbai&category=dentists
    for future-proof multidimensional expansion across all business domains.
    """
    base_url = seo_engine.get_canonical_base_url(request)
    selected_category = (category or tech or "").strip()
    if selected_category:
        seo_engine.ensure_category_maps(db)

    # Case 1: Both city and category/tech provided -> Render Programmatic Intersection Page
    if city and selected_category:
        city_slug = seo_engine.city_to_slug(city)
        tech_slug = seo_engine.tech_to_slug(selected_category)
        city_name = seo_engine.slug_to_city_name(city_slug)
        tech_name = seo_engine.slug_to_tech_name(tech_slug)

        companies, total_count = seo_engine.get_companies_list(db, city=city_name, tech=tech_name, limit=30)
        if total_count == 0:
            raise HTTPException(status_code=404, detail=f"No verified {tech_name} companies found in {city_name}")

        canonical_url = f"{base_url}/directory/companies?city={city_slug}&tech={tech_slug}"

        all_combos = seo_engine.get_all_combinations(db)
        related_techs = [
            {"name": c["tech_name"], "slug": c["tech_slug"], "count": c["count"]}
            for c in all_combos if c["city_slug"] == city_slug and c["tech_slug"] != tech_slug
        ][:12]
        related_cities = [
            {"name": c["city_name"], "slug": c["city_slug"], "count": c["count"]}
            for c in all_combos if c["tech_slug"] == tech_slug and c["city_slug"] != city_slug
        ][:12]

        # Average Google rating straight from the database aggregate for this city and category.
        combo_match = next((c for c in all_combos if c["city_slug"] == city_slug and c["tech_slug"] == tech_slug), None)
        avg_rating = combo_match.get("avg_rating") if combo_match else None
        faqs = seo_engine.generate_combo_faqs(city_name, tech_name, total_count, avg_rating)

        breadcrumbs = [
            ("Home", f"{base_url}/"),
            ("Directory", f"{base_url}/directory"),
            (city_name, f"{base_url}/directory/city/{city_slug}"),
            (tech_name, canonical_url)
        ]
        bc_schema = seo_engine.build_breadcrumb_schema(breadcrumbs)
        itemlist_schema = seo_engine.build_itemlist_schema(companies, base_url, f"Top {tech_name} Companies in {city_name}")
        faq_schema = seo_engine.build_faq_schema(faqs)
        combined_schema = json.dumps([bc_schema, itemlist_schema, faq_schema], ensure_ascii=False)

        response = templates.TemplateResponse(
            request=request,
            name="directory_combo.html",
            context={
                "project_name": config.PROJECT_NAME,
                "canonical_url": canonical_url,
                "city_name": city_name,
                "city_slug": city_slug,
                "tech_name": tech_name,
                "tech_slug": tech_slug,
                "total_companies": total_count,
                "avg_rating": avg_rating,
                "companies": companies,
                "related_techs": related_techs,
                "related_cities": related_cities,
                "faqs": faqs,
                "seo_year": seo_engine.SEO_YEAR,
                "meta_keywords": seo_engine.job_seeker_keywords(city=city_name, field=tech_name),
                "json_ld_schema": combined_schema
            }
        )
        response.headers["Cache-Control"] = "public, max-age=3600, s-maxage=86400, stale-while-revalidate=604800"
        return response

    # Case 2: Only city provided -> Render City Hub
    if city and not selected_category:
        city_slug = seo_engine.city_to_slug(city)
        return directory_city_hub(city_slug, request, db)

    # Case 3: Only category/tech provided -> Render Category Hub
    if selected_category and not city:
        tech_slug = seo_engine.tech_to_slug(selected_category)
        return directory_tech_hub(tech_slug, request, db)

    # Case 4: General query or empty params -> Redirect to /directory
    return RedirectResponse(url="/directory", status_code=301)


@app.api_route("/company/{slug}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def company_showcase_profile(slug: str, request: Request, db: Session = Depends(get_db)):
    """Verified Individual Company Intelligence Profile Dossier"""
    company_id = seo_engine.parse_company_slug(slug)
    if not company_id:
        raise HTTPException(status_code=404, detail="Company profile not found")

    company = seo_engine.get_company_details(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company profile not found")

    base_url = seo_engine.get_canonical_base_url(request)
    canonical_url = f"{base_url}/company/{company['slug']}"
    city_name = company["city"] or ""
    city_slug = seo_engine.city_to_slug(city_name) if city_name else ""

    # Related companies in same city (light, cached per city)
    nearby_filtered = seo_engine.get_nearby_companies(db, city_name, company["id"], limit=3)

    breadcrumbs = [("Home", f"{base_url}/"), ("Directory", f"{base_url}/directory")]
    if city_slug:
        breadcrumbs.append((city_name, f"{base_url}/directory/city/{city_slug}"))
    breadcrumbs.append((company["name"], canonical_url))
    bc_schema = seo_engine.build_breadcrumb_schema(breadcrumbs)
    org_schema = seo_engine.build_local_business_schema(company, base_url)
    combined_schema = json.dumps([bc_schema, org_schema], ensure_ascii=False)

    # Meta description states only facts we actually hold.
    prof = company["profile"]
    parts = [f"{company['name']}" + (f" in {city_name}, India." if city_name else ".")]
    if prof.get("summary"):
        parts.append(prof["summary"])
    elif company.get("category"):
        parts.append(f"Listed under {company['category']}.")
    if company.get("rating") and company.get("reviews_count"):
        parts.append(f"Rated {company['rating']:.1f} on Google from {company['reviews_count']:,} reviews.")
    if prof.get("tech_stack"):
        parts.append("Uses " + ", ".join(prof["tech_stack"][:4]) + ".")
    meta_description = " ".join(parts)
    if len(meta_description) > 158:
        meta_description = meta_description[:155].rsplit(" ", 1)[0] + "..."

    response = templates.TemplateResponse(
        request=request,
        name="company_profile.html",
        context={
            "project_name": config.PROJECT_NAME,
            "canonical_url": canonical_url,
            "company": company,
            "city_slug": city_slug,
            "nearby_companies": nearby_filtered,
            "meta_description": meta_description,
            "json_ld_schema": combined_schema
        }
    )
    response.headers["Cache-Control"] = "public, max-age=3600, s-maxage=86400, stale-while-revalidate=604800"
    return response


# --- Stage 1: Google Local Lead Scout Endpoints ---
def run_scraper_sync(keyword: str, city: str, direct_url: str, max_pages: int = 0, gl: str = "in", hl: str = "en"):
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
    return {
        "status": "error",
        "message": "Public on-demand scraping is disabled. All directory companies are curated and managed via cloud workflows."
    }
    existing_active = (
        db.query(ScoutJob)
        .filter(
            func.lower(func.trim(ScoutJob.keyword)) == clean_keyword.lower(),
            func.lower(func.trim(ScoutJob.city)) == clean_city.lower(),
            ScoutJob.status.in_(["QUEUED", "RUNNING"])
        )
        .order_by(ScoutJob.id.desc())
        .first()
    )
    if existing_active:
        return {
            "status": "started",
            "job_id": existing_active.id,
            "mode": "existing_active_job",
            "message": f"Search for '{clean_keyword}' in '{clean_city}' is already in progress (Job #{existing_active.id})."
        }

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
                        "mode": "single",
                        "job_id": str(job.id),
                        "keyword": clean_keyword,
                        "city": clean_city
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


# --- Company filters: exact ID matches on the taxonomy tables (taxonomy.py) ---
# City, tech and industry never match on text. Names or slugs from the UI and links
# are looked up exactly; anything unknown matches no company.

def _multi_param(request: Request, names: tuple[str, ...], single: str) -> list[str]:
    """Values of a repeatable / comma-separated query param."""
    vals: list[str] = []
    for n in names:
        for v in request.query_params.getlist(n):
            vals += [x.strip() for x in v.split(",") if x.strip()]
        if vals:
            break
    if not vals and single and single.strip():
        vals = [x.strip() for x in single.split(",") if x.strip()]
    return vals


def _city_id_cond(terms: list[str]):
    if not terms:
        return None
    ids = [i for i in (taxonomy.city_id_for(t) for t in terms) if i]
    return Company.city_id.in_(ids or [-1])


def _tech_id_cond(db: Session, terms: list[str]):
    """A company matches a tech when its category is that tech or its profile lists it."""
    if not terms:
        return None
    cat_ids = [c["id"] for c in (taxonomy.category_for(t) for t in terms) if c]
    tech_ids = [i for i in (taxonomy.tech_id_for(t) for t in terms) if i]
    conds = []
    if cat_ids:
        conds.append(Company.category_id.in_(cat_ids))
    if tech_ids:
        conds.append(Company.id.in_(db.query(CompanyTech.company_id).filter(CompanyTech.tech_id.in_(tech_ids))))
    return or_(*conds) if conds else (Company.id == -1)


def _domain_id_cond(domain: str):
    ids = taxonomy.industry_category_ids(domain)
    return None if ids is None else Company.category_id.in_(ids or [-1])


def _status_cond(db: Session, user, status_val: str):
    if status_val == "enriched":
        return Company.is_enriched.is_(True)
    if status_val == "emails":
        return Company.id.in_(db.query(CompanyEmail.company_id).distinct())
    if status_val in ("contacted", "sent"):
        if not user:
            return Company.id == -1
        return Company.id.in_(db.query(OutreachLog.company_id).filter(
            OutreachLog.status == "SENT", OutreachLog.user_id == user.id).distinct())
    return None


@app.get("/api/companies/filters")
def get_companies_filters(
    request: Request,
    domain: str = "",
    city: str = "",
    tech: str = "",
    status: str = "all",
    search: str = "",
    db: Session = Depends(get_db)
):
    """
    Dynamic, interdependent faceted filter metadata.
    Computes responsive option counts for Cities, Tech Stacks, and Domains
    based on active user selections across Companies and Outreach Hub.
    """
    global _filter_cache, _dynamic_filter_cache
    now = time.time()
    try:
        user = get_current_user(db, request)
        is_admin = bool(user and config.is_master_admin(user.email))

        # Extract multi-values
        raw_cities = request.query_params.getlist("city")
        city_terms = []
        for c_val in raw_cities:
            city_terms.extend([x.strip().lower() for x in c_val.split(",") if x.strip()])
        if not city_terms and city and city.strip():
            city_terms = [x.strip().lower() for x in city.split(",") if x.strip()]

        raw_techs = request.query_params.getlist("tech") or request.query_params.getlist("tech_stack")
        tech_terms = []
        for t_val in raw_techs:
            tech_terms.extend([x.strip().lower() for x in t_val.split(",") if x.strip()])
        if not tech_terms and tech and tech.strip():
            tech_terms = [x.strip().lower() for x in tech.split(",") if x.strip()]

        domain_val = (domain or "").strip().lower()
        if domain_val == "all":
            domain_val = ""
        status_val = (status or "all").strip().lower()
        search_val = (search or "").strip().lower()

        # Check if user has zero active filters (global view)
        is_global = (not city_terms and not tech_terms and not domain_val and status_val == "all" and not search_val)

        # Per-user contacted count
        user_contacted_count = None
        if user:
            user_contacted_count = (
                db.query(OutreachLog.company_id)
                .filter(OutreachLog.status == "SENT", OutreachLog.user_id == user.id)
                .distinct()
                .count()
            )

        # 1. Global Cache hit
        if is_global:
            if _filter_cache.get("data") and (now - _filter_cache.get("timestamp", 0) < 300):
                cached = copy.deepcopy(_filter_cache["data"])
                cached["is_master_admin"] = is_admin
                if "stats" in cached and isinstance(cached["stats"], dict):
                    cached["stats"]["contacted"] = user_contacted_count
                    cached["stats"]["is_logged_in"] = bool(user)
                return cached
        else:
            # Dynamic Filter Cache hit
            cache_key = (domain_val, tuple(sorted(city_terms)), tuple(sorted(tech_terms)), status_val, search_val)
            if cache_key in _dynamic_filter_cache:
                entry = _dynamic_filter_cache[cache_key]
                if now - entry["timestamp"] < 120:
                    cached = copy.deepcopy(entry["data"])
                    cached["is_master_admin"] = is_admin
                    if "stats" in cached and isinstance(cached["stats"], dict):
                        cached["stats"]["contacted"] = user_contacted_count
                        cached["stats"]["is_logged_in"] = bool(user)
                    return cached

        # Every condition is an exact ID match (taxonomy tables). Unknown names match nothing.
        d_cond = _domain_id_cond(domain_val)
        t_cond = _tech_id_cond(db, tech_terms)
        c_cond = _city_id_cond(city_terms)
        st_cond = _status_cond(db, user, status_val)
        # Categories hidden from users (admin > Categories): leave their companies out of every count.
        h_cond = seo_engine.visible_kw_clause(db)

        def scoped(q, *skip):
            for name, cond in (("h", h_cond), ("d", d_cond), ("t", t_cond), ("c", c_cond), ("st", st_cond)):
                if cond is not None and name not in skip:
                    q = q.filter(cond)
            return q

        look = taxonomy.lookup()
        city_slug_by_id = {i: s for s, i in look["cities"].items()}

        # --- FACET 1: Cities (scoped to domain, tech, status - NOT city itself) ---
        if tech_terms or domain_val or status_val != "all":
            rows = scoped(
                db.query(Company.city_id, func.count(Company.id)).filter(
                    Company.is_invalid.is_(False), Company.city_id.isnot(None)),
                "c",
            ).group_by(Company.city_id).all()
            sorted_cities = sorted(
                ({"id": cid, "name": look["city_names"].get(cid, ""), "slug": city_slug_by_id.get(cid, ""), "count": n}
                 for cid, n in rows if n > 0),
                key=lambda x: x["name"].lower(),
            )
        else:
            sorted_cities = sorted(
                ({"id": c["id"], "name": c["name"], "slug": c["slug"], "count": c["count"],
                  "domain_counts": c.get("domain_counts", {})}
                 for c in seo_engine.get_all_cities(db) if c.get("count", 0) > 0),
                key=lambda x: x["name"].lower(),
            )

        # --- FACET 2: Tech stacks (scoped to domain, city, status - NOT tech itself) ---
        # A company "has" a tech when its profile lists it, or its category is that tech (e.g. React).
        tech_rows = scoped(
            db.query(Tech.id, Tech.slug, Tech.name, func.count(func.distinct(Company.id)))
            .join(CompanyTech, CompanyTech.tech_id == Tech.id)
            .join(Company, Company.id == CompanyTech.company_id)
            .filter(Company.is_invalid.is_(False)),
            "t",
        ).group_by(Tech.id).order_by(func.count(func.distinct(Company.id)).desc()).limit(60).all()
        tech_map = {slug: {"id": tid, "name": name, "slug": slug, "count": n} for tid, slug, name, n in tech_rows}
        cat_rows = scoped(
            db.query(Category.slug, Category.name, func.count(Company.id))
            .join(Company, Company.category_id == Category.id)
            .filter(Company.is_invalid.is_(False), Category.slug.in_(db.query(Tech.slug))),
            "t",
        ).group_by(Category.id).all()
        for slug, name, n in cat_rows:
            entry = tech_map.setdefault(slug, {"id": look["techs"].get(slug), "name": name, "slug": slug, "count": 0})
            entry["count"] = max(entry["count"], n)
        sorted_tech = sorted((t for t in tech_map.values() if t["count"] > 0), key=lambda x: x["name"].lower())

        # --- FACET 3: Domains (scoped to city, tech, status - NOT domain itself) ---
        all_domains = seo_engine.get_all_domains(db)
        if city_terms or tech_terms or status_val != "all":
            rows = scoped(
                db.query(Industry.code, func.count(Company.id))
                .join(Category, Category.industry_id == Industry.id)
                .join(Company, Company.category_id == Category.id)
                .filter(Company.is_invalid.is_(False)),
                "d",
            ).group_by(Industry.code).all()
            d_counts = {code: n for code, n in rows}
            d_counts["all"] = sum(d_counts.values())
            domains_result = [{**d, "count": d_counts.get(d["code"], 0)} for d in all_domains]
        else:
            domains_result = all_domains

        # --- STATS: Total matching leads with ALL active filters applied ---
        q_total = scoped(db.query(func.count(Company.id)).filter(Company.is_invalid.is_(False)))
        total_valid = q_total.scalar() or 0

        # Enriched count with filters
        q_enriched = q_total.filter(Company.is_enriched.is_(True))
        enriched_count = q_enriched.scalar() or 0

        # Email count with filters
        emails_sub = db.query(CompanyEmail.company_id).distinct()
        with_emails_count = q_total.filter(Company.id.in_(emails_sub)).scalar() or 0

        result = {
            "cities": sorted_cities,
            "tech_stacks": sorted_tech,
            "domains": domains_result,
            "stats": {
                "total": total_valid,
                "enriched": enriched_count,
                "emails": with_emails_count,
                "invalid": 0,
                "contacted": user_contacted_count,
                "is_logged_in": bool(user)
            },
            "is_master_admin": is_admin
        }

        if is_global:
            _filter_cache["timestamp"] = now
            _filter_cache["data"] = result
        else:
            cache_key = (domain_val, tuple(sorted(city_terms)), tuple(sorted(tech_terms)), status_val, search_val)
            _dynamic_filter_cache[cache_key] = {"timestamp": now, "data": result}

        return result
    except Exception as e:
        print(f"[API Error] /api/companies/filters failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return {
            "cities": [],
            "tech_stacks": [],
            "domains": [],
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
def get_companies(
    request: Request,
    page: int = 1,
    page_size: int = 24,
    search: str = "",
    tech: str = "",
    city: str = "",
    domain: str = "",
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

        base_query = db.query(Company)

        # Pull invalid_count from cache if possible instead of running an extra full count
        cached_invalid = 0
        if is_admin:
            if _filter_cache.get("data") and "stats" in _filter_cache["data"]:
                cached_invalid = _filter_cache["data"]["stats"].get("invalid", 0)
            else:
                cached_invalid = base_query.filter(Company.is_invalid.is_(True)).count()
        invalid_count = cached_invalid

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
            # Everyone (admins included) browses the VALID directory by default;
            # invalid/excluded companies remain reachable via the dedicated "invalid"
            # view. This keeps the list total consistent with the "Total Companies" KPI.
            query = base_query.filter(Company.is_invalid.is_(False))
            # Categories hidden from users (admin > Categories) never appear here.
            query = seo_engine.apply_category_visibility(query, db)

        # 2. Metric / Status filter
        if status == "enriched":
            query = query.filter(Company.is_enriched.is_(True))
        elif status == "emails":
            emails_sub = db.query(CompanyEmail.company_id).distinct()
            query = query.filter(Company.id.in_(emails_sub))
        elif status in ("contacted", "sent"):
            if user:
                sent_sub = db.query(OutreachLog.company_id).filter(
                    OutreachLog.status == "SENT",
                    OutreachLog.user_id == user.id
                ).distinct()
                query = query.filter(Company.id.in_(sent_sub))
            else:
                query = query.filter(Company.id == -1)
        elif status == "ready":
            emails_sub = db.query(CompanyEmail.company_id).distinct()
            query = query.filter(Company.id.in_(emails_sub))
            if user:
                sent_sub = db.query(OutreachLog.company_id).filter(
                    OutreachLog.status == "SENT",
                    OutreachLog.user_id == user.id
                ).distinct()
                query = query.filter(~Company.id.in_(sent_sub))
        elif status == "uncontacted":
            if user:
                sent_sub = db.query(OutreachLog.company_id).filter(
                    OutreachLog.status == "SENT",
                    OutreachLog.user_id == user.id
                ).distinct()
                query = query.filter(~Company.id.in_(sent_sub))

        # 3. Search box: free text on name, website and address (trigram-indexed).
        #    City, tech and industry are ID filters below, not text matches.
        if search and search.strip():
            s = f"%{search.strip()}%"
            query = query.filter(or_(Company.name.ilike(s), Company.domain.ilike(s), Company.address.ilike(s)))

        # 4-5b. City, tech and industry: exact ID matches (taxonomy tables).
        city_terms = _multi_param(request, ("city",), city)
        tech_terms = _multi_param(request, ("tech", "tech_stack"), tech)
        for cond in (_city_id_cond(city_terms), _tech_id_cond(db, tech_terms), _domain_id_cond(domain)):
            if cond is not None:
                query = query.filter(cond)

        # 6. Sorting (Strictly prioritize companies with verified emails and AI enrichment first)
        email_order = Company.has_email.desc()
        enriched_order = Company.is_enriched.desc()

        if sort == "rating_desc":
            query = query.order_by(
                email_order,
                enriched_order,
                Company.rating.desc().nullslast(),
                Company.reviews_count.desc().nullslast(),
                Company.id.desc()
            )
        elif sort == "reviews_desc":
            query = query.order_by(
                email_order,
                enriched_order,
                Company.reviews_count.desc().nullslast(),
                Company.rating.desc().nullslast(),
                Company.id.desc()
            )
        elif sort == "name_asc":
            query = query.order_by(
                email_order,
                enriched_order,
                Company.name.asc(),
                Company.id.desc()
            )
        else:  # "newest" / default
            query = query.order_by(
                email_order,
                enriched_order,
                Company.id.desc()
            )

        # 6b. Fast total_count resolution (reuse cached count when no custom search/city/tech/domain filter is active)
        has_custom_filters = bool(
            (search and search.strip()) or
            (domain and domain.strip() and domain.strip().lower() != "all") or
            city_terms or
            tech_terms or
            status in ("contacted", "sent", "uncontacted", "ready")
        )

        if not has_custom_filters and _filter_cache.get("data") and "stats" in _filter_cache["data"]:
            stats_cache = _filter_cache["data"]["stats"]
            if status == "all":
                # stats_cache["total"] is already the VALID count (is_invalid=FALSE),
                # matching the default list filter and the "Total Companies" KPI.
                # (Applies to admins too, now that the default list excludes invalid.)
                total_count = stats_cache.get("total", 0)
            elif status == "enriched":
                total_count = stats_cache.get("enriched", 0)
            elif status == "emails":
                total_count = stats_cache.get("emails", 0)
            elif status == "invalid" and is_admin:
                total_count = stats_cache.get("invalid", 0)
            else:
                total_count = query.order_by(None).count()
        else:
            total_count = query.order_by(None).count()

        # 7. Server-side pagination
        # If page_size is 0, -1, or all=true, return all matching companies
        is_all_requested = (page_size == 0 or page_size == -1 or request.query_params.get("all") == "true")
        if is_all_requested:
            companies = query.all()
            total_pages = 1
            cur_page = 1
            page_size = total_count
        else:
            # Multiples of 6 (12/24/48/96/192) fill 2- and 3-column card grids evenly;
            # the older sizes stay accepted so existing links keep working.
            ALLOWED_PAGE_SIZES = {12, 24, 48, 96, 192, 10, 20, 50, 100, 200, 500, 1000}
            if page_size not in ALLOWED_PAGE_SIZES:
                page_size = 24

            total_pages = max(1, (total_count + page_size - 1) // page_size) if total_count > 0 else 1
            cur_page = max(1, min(page, total_pages)) if total_count > 0 else 1
            companies = query.offset((cur_page - 1) * page_size).limit(page_size).all()

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
                .order_by(OutreachLog.sent_at.asc())  # latest send wins in the dict
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
                "industry_domain": seo_engine._category_labels(c.category_id)[1],
                "domain_code": seo_engine._category_labels(c.category_id)[2],
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
                "contacted_at": ist_text(sent_time) or None
            })

        # Compute domain-aware scoped stats for frontend cards
        dom_clean = domain.strip().lower() if domain else ""
        base_stats = _filter_cache.get("data", {}).get("stats", {}) if _filter_cache.get("data") else {}
        user_contacted_count = 0
        if user:
            user_contacted_count = (
                db.query(OutreachLog.company_id)
                .filter(OutreachLog.status == "SENT", OutreachLog.user_id == user.id)
                .distinct()
                .count()
            )

        if dom_clean and dom_clean not in ("all", ""):
            cached_domains = _filter_cache.get("data", {}).get("domains", []) if _filter_cache.get("data") else []
            d_item = next((d for d in cached_domains if d.get("code") == dom_clean), None)
            if not d_item:
                all_doms = seo_engine.get_all_domains(db)
                d_item = next((d for d in all_doms if d.get("code") == dom_clean), None)
            scoped_stats = {
                "total": d_item.get("count", 0) if d_item else 0,
                "enriched": d_item.get("enriched_count", 0) if d_item else 0,
                "emails": d_item.get("emails_count", 0) if d_item else 0,
                "invalid": 0,
                "contacted": user_contacted_count if dom_clean == "it" else 0,
                "is_logged_in": bool(user)
            }
        else:
            scoped_stats = {
                "total": base_stats.get("total", 55119),
                "enriched": base_stats.get("enriched", 2114),
                "emails": base_stats.get("emails", 1667),
                "invalid": base_stats.get("invalid", 0),
                "contacted": user_contacted_count,
                "is_logged_in": bool(user)
            }

        return {
            "companies": out,
            "total_count": total_count,
            "total_pages": total_pages,
            "current_page": cur_page,
            "page_size": page_size,
            "invalid_count": invalid_count if is_admin else 0,
            "stats": scoped_stats,
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
def get_company_detail(company_id: int, request: Request, db: Session = Depends(get_db)):
    """On-demand deep intelligence dossier and verified records for a single company modal"""
    user = get_current_user(db, request)
    is_admin = bool(user and config.is_master_admin(user.email))

    query = db.query(Company).filter(Company.id == company_id)
    if not is_admin:
        query = query.filter(Company.is_invalid.is_(False))
        query = seo_engine.apply_category_visibility(query, db)
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
                "subject": latest_pitch.subject_line,
                "body": latest_pitch.email_body,
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
        "contacted_at": (ist_text(sent_log.sent_at) or None) if sent_log else None
    }


# --- Stage 2: Deep Subpage Crawler & AI Enrichment (Login Gated) ---
@app.get("/api/auth/status")
def auth_status(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(db, request)
    is_logged_in = bool(user and user.oauth_tokens)
    is_master = bool(user and (getattr(user, "is_admin", False) or config.is_master_admin(user.email)))
    kill_switch = is_subscription_kill_switch_active(db)

    # Guest users always get zero limits regardless of kill switch
    if not is_logged_in:
        daily_limit = 0
        sent_today = 0
        remaining = 0
        tier_code = "guest"
        tier_name = "Guest"
    elif is_master:
        daily_limit = 999999
        sent_today = getattr(user, "pitches_sent_today", 0) or 0
        remaining = 999999
        # Always read the real underlying tier from DB for master - display name override only
        tier_code = getattr(user, "subscription_tier", "free") or "free"
        tier_name = "Master Admin"
    elif kill_switch:
        # Kill switch ON + logged in: infinite, but real tier preserved in DB (not mutated)
        daily_limit = 999999
        sent_today = getattr(user, "pitches_sent_today", 0) or 0
        remaining = 999999
        tier_code = "temp_user"
        tier_name = "Temp User (Unlimited Applications)"
    else:
        # Normal path: read real tier from user record (kill switch OFF restores this automatically)
        tier_code = getattr(user, "subscription_tier", "free") or "free"
        tier_name_map = {
            "free": "Free Job Seeker",
            "pro": "Job Seeker Pro",
            "premium_plus": "Premium+",
            "master_admin": "Master Admin"
        }
        tier_name = tier_name_map.get(tier_code, tier_code.replace("_", " ").title())
        daily_limit = getattr(user, "daily_pitch_limit", 10) or 10
        sent_today = getattr(user, "pitches_sent_today", 0) or 0
        remaining = max(0, daily_limit - sent_today)
    
    # Preserve the user's real purchased/assigned tier in a separate field.
    # This is ALWAYS read from the DB (never mutated by kill switch),
    # so when kill switch is deactivated the UI can immediately restore the correct tier display.
    real_tier_code = (getattr(user, "subscription_tier", "free") or "free") if is_logged_in else "guest"
    real_tier_name_map = {
        "free": "Free Job Seeker",
        "pro": "Job Seeker Pro",
        "premium_plus": "Premium+",
        "master_admin": "Master Admin"
    }
    real_tier_name = "Master Admin" if is_master else real_tier_name_map.get(real_tier_code, real_tier_code.replace("_", " ").title())

    return {
        "is_logged_in": is_logged_in,
        "email": user.email if is_logged_in else None,
        "name": user.name if is_logged_in else None,
        "picture": user.picture if is_logged_in else None,
        "is_master_admin": is_master,
        "subscription_kill_switch": kill_switch,
        # Effective (displayed) tier: overridden when kill switch is on
        "subscription_tier": tier_code,
        "subscription_tier_name": tier_name,
        # Real (persisted) tier: always reflects what user actually purchased/has assigned
        "real_subscription_tier": real_tier_code,
        "real_subscription_tier_name": real_tier_name,
        "subscription_status": getattr(user, "subscription_status", "active") if is_logged_in else "active",
        "daily_pitch_limit": daily_limit,
        "pitches_sent_today": sent_today,
        "pitches_remaining": remaining,
        "quota_resets_at": next_quota_reset_utc().replace(tzinfo=timezone.utc).isoformat(),
        "is_banned": bool(getattr(user, "is_banned", False)) if is_logged_in else False,
        "dev_mode": config.DEV_MODE
    }


@app.get("/api/tiers")
def get_public_tiers(db: Session = Depends(get_db)):
    """Public customer-facing pricing and subscription plan specification."""
    if is_subscription_kill_switch_active(db):
        return {
            "kill_switch_active": True,
            "tiers": []
        }
    tiers = db.query(SubscriptionTier).filter(SubscriptionTier.is_active == True).order_by(SubscriptionTier.id.asc()).all()
    public_tiers = [t for t in tiers if t.code != "master_admin"]
    if not public_tiers:
        return {
            "tiers": [
                {
                    "code": "free",
                    "name": "Free Job Seeker",
                    "subtitle": "Starter Tier",
                    "price_inr": 0,
                    "daily_pitch_limit": 10,
                    "features": ["10 job applications / day", "Full company directory access", "Careers and contact email discovery", "Sends from your own Gmail"],
                    "badge": None,
                    "is_popular": False
                },
                {
                    "code": "pro",
                    "name": "Job Seeker Pro",
                    "subtitle": "Growth Tier",
                    "price_inr": 499,
                    "daily_pitch_limit": 25,
                    "features": ["25 job applications / day", "AI research of each company website", "Resume PDF attached automatically", "Each application written for that company"],
                    "badge": "Most Popular",
                    "is_popular": True
                },
                {
                    "code": "premium_plus",
                    "name": "Premium+",
                    "subtitle": "Maximum Velocity",
                    "price_inr": 999,
                    "daily_pitch_limit": 50,
                    "features": ["50 job applications / day", "Highest priority email queue", "Matches your skills to each company's tech stack", "Unlimited AI rewrites of each application"],
                    "badge": "Maximum Velocity",
                    "is_popular": False
                }
            ]
        }
    return {
        "tiers": [
            {
                "id": t.id,
                "code": t.code,
                "name": t.name,
                "subtitle": t.subtitle or "",
                "price_inr": t.price_inr,
                "daily_pitch_limit": t.daily_pitch_limit,
                "features": t.features or [],
                "badge": t.badge or "",
                "is_popular": t.code == "pro"
            }
            for t in public_tiers
        ]
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
        is_admin_flag = True
    elif req_email:
        target_email = req_email
        name = "Verified User"
        is_admin_flag = False
    else:
        target_email = "demo_user@outreachpilot.ai"
        name = "Verified Pilot User"
        is_admin_flag = False

    user = db.query(User).filter(User.email == target_email).first()
    if not user:
        user = User(
            email=target_email,
            name=name,
            target_role="",
            is_admin=is_admin_flag,
            daily_pitch_limit=999999 if is_admin_flag else 10,
            subscription_tier="premium_plus" if is_admin_flag else "free",
            daily_send_limit=100 if is_admin_flag else 50
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif is_admin_flag:
        user.is_admin = True
        user.daily_pitch_limit = 999999
        user.subscription_tier = "premium_plus"
        db.commit()

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
        "is_master_admin": bool(user.is_admin or config.is_master_admin(user.email))
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


# Company enrichment and exclusion are admin-only (see /api/admin/...); normal users
# use AI only for resume analysis and personalized emails.


# --- Stage 3: In-Memory Resume Ingestion & Parsing ---
MAX_RESUME_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_PDF_PAGES = 15


@app.get("/api/resume/profile")
def get_candidate_profile(request: Request, db: Session = Depends(get_db)):
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
    if getattr(user, "is_banned", False):
        raise HTTPException(
            status_code=403,
            detail=f"Account suspended: {user.ban_reason or 'Access denied by administrator.'}"
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
            detail="Please select a resume file (PDF or TXT)."
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

        try:
            parsed_profile = parse_resume_text(resume_text=raw_text, target_role=target_role)
        except Exception as e:
            print(f"[Resume Analysis Error] {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to analyze resume with AI: {e!s}. Please try again."
            )

    if target_role:
        user.target_role = target_role
    elif parsed_profile.get("target_role"):
        user.target_role = parsed_profile.get("target_role")

    cand_name = (parsed_profile.get("full_name") or "").strip()
    if cand_name and cand_name.lower() != "candidate":
        # Keep user.name synchronized if current user name is empty, generic, or Pilot User
        if not user.name or "Pilot" in user.name or user.name == "Candidate":
            user.name = cand_name

    if user.resume_link:
        parsed_profile["resume_link"] = user.resume_link

    user.resume_summary = parsed_profile

    # Invalidate and delete stale draft pitches so all future generated pitches reflect the newly uploaded resume
    try:
        deleted_count = db.query(ColdPitch).filter(
            ColdPitch.user_id == user.id,
            ColdPitch.status == "DRAFT"
        ).delete(synchronize_session=False)
        if deleted_count:
            print(f"[Resume Upload] Cleared {deleted_count} stale draft pitches for user {user.id}")
    except Exception as clear_err:
        print(f"[Resume Upload Warning] Could not clear stale pitches: {clear_err}")

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
            detail="Authentication required. Please connect your Google account to write job applications."
        )
    if getattr(user, "is_banned", False):
        raise HTTPException(
            status_code=403,
            detail=f"Account suspended: {user.ban_reason or 'Access denied by administrator.'}"
        )

    client_id = f"{user.id}_{request.client.host if request and request.client else 'unknown'}"
    enforce_rate_limit(f"pitch_gen_{client_id}", max_calls=30, window_seconds=60)
    cand_profile = resume_profile_or_400(req, user)

    comp_profile_data = {
        "summary": company.profile.summary_short if company.profile else "",
        "detailed_analysis": company.profile.detailed_analysis if company.profile else "",
        "industry": (company.profile.industry if company.profile else "") or "",
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

    c_name = cand_profile.get("full_name") or (user.name if user and user.name else "Candidate")
    t_role = cand_profile.get("target_role") or (user.target_role if user and user.target_role else "Professional")
    c_name_clean = c_name.strip() if c_name else "Candidate"

    allowance, sends_left = draft_allowance(db, user)
    has_draft = db.query(ColdPitch.id).filter(
        ColdPitch.company_id == company.id, ColdPitch.user_id == user.id
    ).first() is not None
    # Rewriting an existing draft is fine while sends remain; a new company needs a free slot.
    if sends_left <= 0 or (not has_draft and allowance <= 0):
        raise daily_limit_reached_error(user)

    existing_pitch = db.query(ColdPitch).filter(
        ColdPitch.company_id == company.id,
        ColdPitch.user_id == user.id
    ).first()

    # If existing pitch has already been generated, verify it belongs to the CURRENT candidate name
    if existing_pitch and not getattr(req, "force_regenerate", False):
        existing_body = existing_pitch.email_body or ""
        # If candidate name changed or pitch has old candidate, force re-generation
        if c_name_clean.lower() != "candidate" and c_name_clean.lower() not in existing_body.lower():
            existing_pitch = None
        elif existing_body:
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
                "email_body": existing_pitch.email_body,
                "primary_email": existing_pitch.email_body,
                "cover_letter": existing_pitch.cover_letter or "",
                "matched_skills": existing_pitch.matched_skills if isinstance(existing_pitch.matched_skills, list) else [],
                "mailto_url": mailto_url
            }

    pitch_data = generate_personalized_pitch(
        candidate_profile=cand_profile,
        company_name=company.name,
        company_profile=comp_profile_data
    )

    subj = (pitch_data.get("subject_line") or "").strip()
    body = (pitch_data.get("email_body") or pitch_data.get("primary_email") or "").strip()

    if not subj:
        subj = f"Inquiring about {t_role} opportunities at {company.name} - {c_name_clean}"

    if not body:
        skills_str = ", ".join(cand_profile.get("top_skills", [])[:6]) or "Python, JavaScript, PostgreSQL, FastAPI, React"
        raw_proofs = cand_profile.get("key_achievements") or cand_profile.get("strong_points") or []
        if not raw_proofs:
            raw_proofs = [
                f"Architected scalable backend microservices and high-throughput REST API endpoints utilizing {skills_str}",
                "Rewrote and optimized complex database queries and indexing strategies, significantly decreasing runtime and memory overhead",
                "Built automated data pipelines, continuous integration (CI/CD) workflows, and automated regression testing suites",
                "Engineered responsive user interfaces with modular component architectures and real-time state synchronization"
            ]

        proof_bullets = []
        for p in raw_proofs[:4]:
            p_clean = p.strip().lstrip("-*•").strip()
            if p_clean:
                proof_bullets.append(f"- {p_clean}")

        achievements_block = "\n".join(proof_bullets)
        resume_ref = f" (Portfolio / Code: {cand_profile.get('resume_link')})" if cand_profile.get("resume_link") else ""
        comp_tech_focus = comp_profile_data.get("tech_stack", [])[0] if comp_profile_data.get("tech_stack") else "modern software engineering"

        body = (
            f"Hi {company.name} team,\n\n"
            f"I am writing to inquire about open or upcoming {t_role} opportunities at {company.name}. "
            f"Given your focus on {comp_tech_focus}, my technical experience across {skills_str} aligns directly with your engineering requirements.\n\n"
            f"As a {t_role}, here are key highlights and verified technical achievements from my recent experience:\n\n"
            f"{achievements_block}\n\n"
            f"My core stack encompasses {skills_str}, enabling me to contribute immediately across your architecture and product feature roadmap. "
            f"My detailed resume is attached for your review{resume_ref}.\n\n"
            f"Are you currently hiring for {t_role} positions, or open to considering my profile for upcoming engineering needs?\n\n"
            f"Best regards,\n"
            f"{c_name_clean}"
        )

    matched_meta = {
        "skills": pitch_data.get("matched_skills", []),
        "subject_line": subj,
        "email_body": body
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
            detail="Authentication required. Please connect your Google account to write job applications."
        )
    if getattr(user, "is_banned", False):
        raise HTTPException(
            status_code=403,
            detail=f"Account suspended: {user.ban_reason or 'Access denied by administrator.'}"
        )

    client_id = f"{user.id}_{request.client.host if request and request.client else 'unknown'}"
    enforce_rate_limit(f"bulk_pitch_gen_{client_id}", max_calls=30, window_seconds=60)

    if not req.company_ids:
        return {"success": True, "generated_count": 0, "total": 0, "pitches": []}

    cand_profile = resume_profile_or_400(req, user)

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

    # Daily limit also caps drafting: existing drafts can be rewritten while sends remain,
    # and only as many new companies as there are free slots today.
    allowance, sends_left = draft_allowance(db, user)
    if sends_left <= 0:
        raise daily_limit_reached_error(user)
    requested = len(companies)
    kept = []
    for comp in companies:
        if comp.id in existing_pitches:
            kept.append(comp)
        elif allowance > 0:
            kept.append(comp)
            allowance -= 1
    if not kept:
        raise daily_limit_reached_error(user)
    companies = kept

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
            "industry": (comp.profile.industry if comp.profile else "") or "",
            "tech_stack": comp.profile.tech_stack if comp.profile else [],
            "tone": comp.profile.tone if comp.profile else "Professional"
        }
        # Speed: an existing draft written for this candidate is kept as is (no AI call),
        # the same rule the single generate endpoint uses. Only new companies are drafted.
        reuse = None
        old = existing_pitches.get(comp.id)
        cand_name = (cand_profile.get("full_name") or "").strip().lower()
        if old and (old.email_body or "").strip() and old.status != "SENT" and (
                not cand_name or cand_name in (old.email_body or "").lower()):
            reuse = {
                "company_id": comp.id, "company_name": comp.name, "target_email": target_email or old.target_email,
                "subject_line": old.subject_line, "email_body": old.email_body,
                "cover_letter": old.cover_letter or "", "matched_skills": old.matched_skills or {},
            }
        tasks.append({
            "company_id": comp.id,
            "company_name": comp.name,
            "target_email": target_email,
            "profile": comp_profile_data,
            "reuse": reuse,
        })

    def process_task(task):
        if task.get("reuse"):
            return task["reuse"]
        pitch_data = generate_personalized_pitch(
            candidate_profile=cand_profile,
            company_name=task["company_name"],
            company_profile=task["profile"]
        )

        subj = (pitch_data.get("subject_line") or "").strip()
        body = (pitch_data.get("email_body") or pitch_data.get("primary_email") or "").strip()

        matched_meta = {
            "skills": pitch_data.get("matched_skills", []),
            "subject_line": subj,
            "email_body": body
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
        "skipped_for_daily_limit": requested - len(companies),
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
    if getattr(user, "is_banned", False):
        raise HTTPException(status_code=403, detail=f"Account suspended: {user.ban_reason or 'Contact administrator'}")

    client_id = f"{user.id}_{request.client.host if request and request.client else 'unknown'}"
    enforce_rate_limit(f"send_direct_{client_id}", max_calls=30, window_seconds=60)

    is_master = bool(getattr(user, "is_admin", False) or config.is_master_admin(user.email))
    is_unrestricted = is_master or is_subscription_kill_switch_active(db)

    pitch = db.query(ColdPitch).filter(ColdPitch.id == pitch_id).first()
    if not pitch:
        raise HTTPException(status_code=404, detail="Application not found")

    if not is_master and pitch.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden: You do not own this application record.")
    if pitch.status in ("QUEUED", "SENDING"):
        raise HTTPException(status_code=409, detail="This application is already queued and will be sent shortly.")

    # Take this send from today's quota up front (atomic); refunded below if it fails.
    reserved = 0
    if not is_unrestricted:
        reserved = reserve_daily_pitches(db, user.id, 1)
        if reserved == 0:
            limit = getattr(user, "daily_pitch_limit", 10) or 10
            raise HTTPException(
                status_code=403,
                detail=f"Daily limit reached ({limit} emails a day on your plan). It resets at midnight IST."
            )

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
        refund_daily_pitches(db, user.id, reserved)
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
        refund_daily_pitches(db, user.id, reserved)
        return {"success": False, "error": result.get("error", "Failed to dispatch email via Google OAuth.")}


@app.post("/api/pitch/bulk-send")
async def bulk_send_outreach(
    request: Request,
    db: Session = Depends(get_db)
):
    user = get_current_user(db, request)
    if not user or not user.oauth_tokens:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please connect your Google account to perform direct outreach."
        )
    if getattr(user, "is_banned", False):
        raise HTTPException(status_code=403, detail=f"Account suspended: {user.ban_reason or 'Contact administrator'}")

    client_id = f"{user.id}_{request.client.host if request and request.client else 'unknown'}"
    enforce_rate_limit(f"bulk_send_{client_id}", max_calls=10, window_seconds=60)

    is_master = bool(getattr(user, "is_admin", False) or config.is_master_admin(user.email))

    content_type = request.headers.get("content-type", "")
    resume_bytes = None
    resume_name = None
    pitch_ids = []

    if "multipart/form-data" in content_type:
        form = await request.form()
        raw_pitch_ids = form.get("pitch_ids", "")
        if isinstance(raw_pitch_ids, str):
            try:
                pitch_ids = json.loads(raw_pitch_ids)
            except Exception:
                pitch_ids = [int(x.strip()) for x in raw_pitch_ids.split(",") if x.strip().isdigit()]
        elif isinstance(raw_pitch_ids, list):
            pitch_ids = [int(x) for x in raw_pitch_ids if str(x).isdigit()]

        resume_file = form.get("resume_file")
        if resume_file and hasattr(resume_file, "read"):
            resume_bytes = await resume_file.read()
            resume_name = getattr(resume_file, "filename", "resume.pdf")
    else:
        body = await request.json()
        pitch_ids = body.get("pitch_ids", [])

    is_unrestricted = is_master or is_subscription_kill_switch_active(db)

    # Queue the batch; outreach.run_send_queue sends it in the background, so a closed tab
    # or a server restart no longer cuts a batch off halfway.
    ids = list(dict.fromkeys(int(x) for x in pitch_ids if str(x).isdigit()))[:500]
    found = {pp.id: pp for pp in db.query(ColdPitch).filter(ColdPitch.id.in_(ids)).all()} if ids else {}
    details, sendable = [], []
    for pid in ids:
        pp = found.get(pid)
        if not pp or pp.user_id != user.id:
            details.append({"pitch_id": pid, "status": "FAILED", "error": "Application not found."})
        elif not (pp.target_email or "").strip():
            details.append({"pitch_id": pid, "status": "SKIPPED", "error": "Company email not found! Skipped sending."})
        elif pp.status in ("SENT", "QUEUED", "SENDING"):
            details.append({"pitch_id": pid, "status": pp.status, "error": "Already sent or queued."})
        else:
            sendable.append(pp)

    skipped_over_limit = 0
    if sendable and not is_unrestricted:
        # Atomic: parallel requests cannot both spend the same remaining quota.
        reserved = reserve_daily_pitches(db, user.id, len(sendable))
        if reserved == 0:
            limit = getattr(user, "daily_pitch_limit", 10) or 10
            raise HTTPException(
                status_code=403,
                detail=f"Daily limit reached ({limit} emails a day on your plan). It resets at midnight IST."
            )
        skipped_over_limit = len(sendable) - reserved
        for pp in sendable[reserved:]:
            details.append({"pitch_id": pp.id, "status": "SKIPPED", "error": "Over today's limit."})
        sendable = sendable[:reserved]

    now = datetime.utcnow()  # same stamp on the attachment and the batch: cleanup keys on it
    if resume_bytes and sendable:
        # Kept in the DB (not on disk) so it is still there if the server restarts mid-batch.
        # The worker deletes it once this user's queue is empty.
        db.merge(SendAttachment(user_id=user.id, filename=(resume_name or "Resume.pdf")[:255],
                                data=resume_bytes, updated_at=now))

    for pp in sendable:
        pp.status, pp.queued_at, pp.send_attempts = "QUEUED", now, 0
        pp.next_attempt_at, pp.last_error, pp.quota_reserved = None, None, not is_unrestricted
        details.append({"pitch_id": pp.id, "email": pp.target_email, "status": "QUEUED"})
    db.commit()

    return {
        "queued": len(sendable),
        "skipped_no_email": sum(1 for d in details if d["status"] == "SKIPPED" and "email" in (d.get("error") or "").lower()),
        "skipped_over_limit": skipped_over_limit,
        "failed": sum(1 for d in details if d["status"] == "FAILED"),
        "details": details,
    }


@app.get("/api/pitch/queue-status")
def pitch_queue_status(request: Request, ids: str = "", db: Session = Depends(get_db)):
    """Live status of the signed-in user's queued applications (the Outreach Hub polls this)."""
    user = get_current_user(db, request)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in to see your sending progress.")
    wanted = list(dict.fromkeys(int(x) for x in ids.split(",") if x.strip().isdigit()))[:500]
    q = db.query(ColdPitch.id, ColdPitch.company_id, ColdPitch.status, ColdPitch.last_error).filter(ColdPitch.user_id == user.id)
    q = q.filter(ColdPitch.id.in_(wanted)) if wanted else q.filter(ColdPitch.status.in_(["QUEUED", "SENDING"]))
    rows = [{"pitch_id": r.id, "company_id": r.company_id, "status": r.status, "error": r.last_error} for r in q.all()]
    counts = {k: sum(1 for r in rows if r["status"] == k) for k in ("QUEUED", "SENDING", "SENT", "FAILED")}
    return {"pitches": rows, "counts": counts, "done": counts["QUEUED"] + counts["SENDING"] == 0}


@app.get("/api/outreach/sent/{company_id}")
def get_sent_email_for_company(company_id: int, request: Request, db: Session = Depends(get_db)):
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
                "sent_at": ist_text(pitch.sent_at)
            }
        return {"found": False}

    return {
        "found": True,
        "company_name": log.company.name if log.company else "Unknown",
        "recipient_email": log.recipient_email,
        "subject": log.subject,
        "email_body": log.email_body or "",
        "delivery_method": log.delivery_method,
        "sent_at": ist_text(log.sent_at)
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
@app.get("/auth/login")
async def legacy_login_redirect():
    """Older links pointed here; Google sign-in lives at /auth/google/login."""
    return RedirectResponse(url="/auth/google/login", status_code=302)


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

        # Strict Security Enforcement: Instantly reject login if account is banned
        if user and getattr(user, "is_banned", False):
            ban_reason = user.ban_reason or "Your account has been suspended by an administrator."
            return RedirectResponse(url=f"/?auth_error=Account+Suspended:+{urllib.parse.quote_plus(ban_reason)}")

        is_admin = config.is_master_admin(user_email_clean)
        if not user:
            user = User(
                email=user_email_clean,
                name="Master Admin (Rahul Vora)" if is_admin else "Pilot User",
                target_role="",
                is_admin=is_admin,
                daily_pitch_limit=999999 if is_admin else 10,
                subscription_tier="premium_plus" if is_admin else "free",
                daily_send_limit=100 if is_admin else 50
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        elif is_admin and not getattr(user, "is_admin", False):
            user.is_admin = True
            user.daily_pitch_limit = 999999
            user.subscription_tier = "premium_plus"
            db.commit()

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


# =====================================================================
# ENTERPRISE MASTER ADMIN DASHBOARD & GOVERNANCE ENDPOINTS
# =====================================================================

@app.api_route("/admin", methods=["GET", "HEAD"], response_class=HTMLResponse)
def admin_dashboard_page(request: Request, db: Session = Depends(get_db)):
    """Enterprise Master Admin Dashboard"""
    user = get_current_user(db, request)
    is_logged_in = bool(user and user.oauth_tokens)
    is_admin = bool(user and (getattr(user, "is_admin", False) or config.is_master_admin(user.email)))
    if not is_logged_in:
        return RedirectResponse(url="/app?login=1", status_code=307)
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted: Master Admin privileges required."
        )
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "project_name": config.PROJECT_NAME,
            "tagline": config.TAGLINE,
            "user": user,
            "is_master_admin": True,
            "dev_mode": config.DEV_MODE,
            # Sidebar badge on the Categories tab (cached one-row read)
            "hidden_categories_count": len(seo_engine.get_hidden_category_slugs(db)),
        }
    )


@app.get("/api/admin/metrics")
def get_admin_metrics(
    force: bool = Query(False),
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    now = time.time()
    if not force and _admin_metrics_cache["data"] and (now - _admin_metrics_cache["timestamp"] < 30.0):
        return _admin_metrics_cache["data"]

    # 1. Single aggregate query for users (Neon PostgreSQL fast path)
    user_row = db.query(
        func.count(User.id).label("total"),
        func.count(User.id).filter(User.oauth_tokens != None).label("oauth"),
        func.count(User.id).filter(or_(User.is_admin == True, User.email.in_(config.MASTER_ADMIN_EMAILS))).label("admins"),
        func.count(User.id).filter(or_(User.subscription_tier == "free", User.subscription_tier == None)).label("free"),
        func.count(User.id).filter(User.subscription_tier == "pro").label("pro"),
        func.count(User.id).filter(User.subscription_tier == "premium_plus").label("premium_plus"),
        func.coalesce(func.sum(User.pitches_sent_today), 0).label("pitches")
    ).first()

    # 2. Single aggregate query for companies
    comp_row = db.query(
        func.count(Company.id).filter(Company.is_invalid == False).label("valid"),
        func.count(Company.id).filter(Company.is_invalid == True).label("invalid"),
        func.count(Company.id).filter(Company.is_enriched == True).label("enriched")
    ).first()

    # 3. Single count for verified emails
    verified_emails = db.query(func.count(CompanyEmail.id)).scalar() or 0

    # 4. Pitches actually sent today: count OutreachLog rows (same source as the
    #    Sent Pitches tab), not sum(User.pitches_sent_today): the per-user quota
    #    counter is not incremented for master-admin sends, so it under-reports.
    _today_start = quota_day_start_utc()  # same IST day as the quota
    pitches_today = db.query(func.count(OutreachLog.id)).filter(OutreachLog.sent_at >= _today_start).scalar() or 0

    data = {
        "users_total": user_row.total if user_row else 0,
        "users_with_oauth": user_row.oauth if user_row else 0,
        "master_admins": user_row.admins if user_row else 0,
        "subscribers_free": user_row.free if user_row else 0,
        "subscribers_pro": user_row.pro if user_row else 0,
        "subscribers_premium_plus": user_row.premium_plus if user_row else 0,
        "pitches_sent_today": pitches_today,
        "companies_valid": comp_row.valid if comp_row else 0,
        "companies_invalid": comp_row.invalid if comp_row else 0,
        "verified_emails": verified_emails,
        "companies_researched": comp_row.enriched if comp_row else 0,
        "database": "Neon PostgreSQL Cloud"
    }

    _admin_metrics_cache["timestamp"] = now
    _admin_metrics_cache["data"] = data
    return data


@app.get("/api/admin/users")
def list_admin_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    search: str = Query(""),
    tier: str = Query(""),
    role: str = Query(""),
    sort_by: str = Query("id"),
    sort_order: str = Query("desc"),
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    q = db.query(User)
    if search:
        s = f"%{search.strip().lower()}%"
        q = q.filter(or_(User.email.ilike(s), User.name.ilike(s)))
    if tier:
        q = q.filter(User.subscription_tier == tier)
    if role == "admin":
        q = q.filter(or_(User.is_admin == True, User.email.in_(config.MASTER_ADMIN_EMAILS)))
    elif role == "user":
        q = q.filter(User.is_admin == False, ~User.email.in_(config.MASTER_ADMIN_EMAILS))

    total_count = q.count()
    total_pages = max(1, (total_count + page_size - 1) // page_size)

    sort_order_clean = sort_order.lower() if sort_order in ("asc", "desc") else "desc"
    is_asc = sort_order_clean == "asc"
    if sort_by == "email":
        order_target = User.email.asc() if is_asc else User.email.desc()
    elif sort_by == "role":
        order_target = User.is_admin.asc() if is_asc else User.is_admin.desc()
    elif sort_by == "tier":
        order_target = User.subscription_tier.asc() if is_asc else User.subscription_tier.desc()
    elif sort_by == "pitches":
        order_target = User.pitches_sent_today.asc() if is_asc else User.pitches_sent_today.desc()
    elif sort_by == "status":
        order_target = User.is_banned.asc() if is_asc else User.is_banned.desc()
    else:
        order_target = User.id.asc() if is_asc else User.id.desc()

    users = q.order_by(order_target, User.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    _quota_start = quota_day_start_utc()
    sent_totals = dict(
        db.query(OutreachLog.user_id, func.count(OutreachLog.id))
        .filter(OutreachLog.user_id.in_([u.id for u in users]))
        .group_by(OutreachLog.user_id)
        .all()
    ) if users else {}

    return {
        "total_count": total_count,
        "total_pages": total_pages,
        "current_page": page,
        "page_size": page_size,
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "name": u.name or "Pilot User",
                "is_admin": bool(u.is_admin or config.is_master_admin(u.email)),
                "subscription_tier": u.subscription_tier or "free",
                "subscription_status": u.subscription_status or "active",
                "daily_pitch_limit": 999999 if (u.is_admin or config.is_master_admin(u.email)) else (u.daily_pitch_limit or 10),
                "pitches_sent_today": (u.pitches_sent_today or 0)
                    if (u.last_pitch_reset_date and u.last_pitch_reset_date >= _quota_start) else 0,
                "pitches_sent_total": sent_totals.get(u.id, 0),
                "is_banned": bool(u.is_banned),
                "ban_reason": u.ban_reason or "",
                "created_at": u.created_at.strftime("%Y-%m-%d %H:%M") if hasattr(u, "created_at") and u.created_at else None
            }
            for u in users
        ]
    }


@app.post("/api/admin/users/{user_id}/toggle-admin")
def toggle_user_admin(
    user_id: int,
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot modify your own administrative status")

    new_is_admin = not bool(target.is_admin)
    target.is_admin = new_is_admin
    if new_is_admin:
        target.daily_pitch_limit = 999999
        target.subscription_tier = "premium_plus"
    else:
        target.daily_pitch_limit = 10
        target.subscription_tier = "free"
    db.commit()
    return {
        "success": True,
        "is_admin": new_is_admin,
        "message": f"User {target.email} is now {'a Master Admin (infinite pitches granted)' if new_is_admin else 'a Regular User'}."
    }


@app.post("/api/admin/users/{user_id}/update-plan")
def update_user_plan(
    user_id: int,
    payload: UpdatePlanRequest,
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    tier = payload.tier.lower().strip()
    tier_obj = db.query(SubscriptionTier).filter(SubscriptionTier.code == tier).first()
    if not tier_obj and tier not in ("free", "pro", "premium_plus"):
        raise HTTPException(status_code=400, detail="Invalid tier. Choose free, pro, premium_plus or an active custom tier.")

    target.subscription_tier = tier
    if payload.custom_limit:
        target.daily_pitch_limit = payload.custom_limit
    elif tier_obj:
        target.daily_pitch_limit = tier_obj.daily_pitch_limit
    elif tier == "premium_plus":
        target.daily_pitch_limit = 100
    elif tier == "pro":
        target.daily_pitch_limit = 50
    else:
        target.daily_pitch_limit = 10

    db.commit()
    return {
        "success": True,
        "tier": target.subscription_tier,
        "daily_pitch_limit": target.daily_pitch_limit,
        "message": f"Updated subscription to {tier.upper()} ({target.daily_pitch_limit} pitches/day)."
    }


@app.post("/api/admin/users/{user_id}/ban")
def toggle_user_ban(
    user_id: int,
    payload: BanUserRequest,
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot ban your own administrator account")

    target.is_banned = payload.is_banned
    target.ban_reason = payload.reason if payload.is_banned else None
    db.commit()
    return {
        "success": True,
        "is_banned": target.is_banned,
        "message": f"User {target.email} has been {'suspended' if target.is_banned else 'reactivated'}."
    }


@app.post("/api/admin/companies/add")
def add_company_admin(
    payload: AddCompanyAdminRequest,
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    raw_domain = (payload.domain or "").strip().lower()
    clean_dom = re.sub(r'^(?:https?://)?(?:www\.)?', '', raw_domain).split('/')[0].split(':')[0]
    if not clean_dom or not is_genuine_company_domain(clean_dom):
        raise HTTPException(status_code=400, detail="Invalid domain format or disallowed domain type.")

    existing = db.query(Company).filter(Company.domain == clean_dom).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Company with domain '{clean_dom}' already exists in directory (ID: {existing.id}).")

    clean_name = clean_company_name(payload.name.strip(), clean_dom) or payload.name.strip()

    company = Company(
        name=clean_name,
        domain=clean_dom,
        website_url=f"https://{clean_dom}",
        city=payload.city.strip() if payload.city else None,
        phone=payload.phone.strip() if payload.phone else None,
        source_query=payload.category or "Admin Added",
        search_keyword=payload.category or "Information Technology & Software",
        is_invalid=False
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    if payload.email and "@" in payload.email:
        email_obj = CompanyEmail(
            company_id=company.id,
            email_address=payload.email.strip().lower(),
            is_primary=True,
            email_type="primary"
        )
        db.add(email_obj)
        company.has_email = True

    if payload.tech_stack:
        tech_list = [t.strip() for t in payload.tech_stack.split(",") if t.strip()]
        profile = CompanyProfile(
            company_id=company.id,
            tech_stack=tech_list,
            summary_short=payload.summary or f"{clean_name} is an enterprise operating in {company.city or 'India'}.",
            industry=payload.category or "Tech"
        )
        db.add(profile)
        company.is_enriched = True

    db.commit()
    invalidate_filter_cache()

    return {
        "success": True,
        "company_id": company.id,
        "name": company.name,
        "domain": company.domain,
        "message": f"Successfully registered '{company.name}'."
    }


@app.post("/api/admin/companies/bulk-upload")
async def bulk_upload_companies_csv(
    file: UploadFile = File(...),
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")

    content = await file.read()
    text_content = content.decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(text_content))

    existing_domains = {r[0] for r in db.query(Company.domain).all()}

    imported_count = 0
    duplicate_count = 0
    invalid_domain_count = 0
    total_rows = 0

    companies_to_add = []

    for row in reader:
        total_rows += 1
        name_raw = row.get("name") or row.get("company_name") or row.get("company") or ""
        domain_raw = row.get("domain") or row.get("website") or row.get("url") or ""
        city_raw = row.get("city") or row.get("location") or ""
        cat_raw = row.get("category") or row.get("industry") or "Information Technology & Software"
        phone_raw = row.get("phone") or row.get("contact") or ""

        if not domain_raw or not name_raw:
            continue

        clean_dom = re.sub(r'^(?:https?://)?(?:www\.)?', '', domain_raw.strip().lower()).split('/')[0].split(':')[0]
        if not clean_dom or not is_genuine_company_domain(clean_dom):
            invalid_domain_count += 1
            continue

        if clean_dom in existing_domains:
            duplicate_count += 1
            continue

        clean_name = clean_company_name(name_raw.strip(), clean_dom) or name_raw.strip()

        comp = Company(
            name=clean_name,
            domain=clean_dom,
            website_url=f"https://{clean_dom}",
            city=city_raw.strip() if city_raw else None,
            phone=phone_raw.strip() if phone_raw else None,
            source_query=cat_raw.strip(),
            search_keyword=cat_raw.strip(),
            is_invalid=False
        )
        companies_to_add.append(comp)
        existing_domains.add(clean_dom)
        imported_count += 1

        if len(companies_to_add) >= 500:
            db.bulk_save_objects(companies_to_add)
            db.commit()
            companies_to_add = []

    if companies_to_add:
        db.bulk_save_objects(companies_to_add)
        db.commit()

    if imported_count > 0:
        invalidate_filter_cache()

    return {
        "success": True,
        "total_rows": total_rows,
        "imported": imported_count,
        "skipped_duplicates": duplicate_count,
        "invalid_domains": invalid_domain_count
    }


@app.get("/api/admin/companies/invalid")
def list_invalid_companies(
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    search: str = Query(""),
    sort_by: str = Query("id"),
    sort_order: str = Query("desc"),
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    q = db.query(Company).filter(Company.is_invalid == True)
    if search:
        s = f"%{search.strip().lower()}%"
        q = q.filter(or_(Company.name.ilike(s), Company.domain.ilike(s)))

    total_count = q.count()
    total_pages = max(1, (total_count + page_size - 1) // page_size)

    sort_order_clean = sort_order.lower() if sort_order in ("asc", "desc") else "desc"
    is_asc = sort_order_clean == "asc"
    if sort_by == "name":
        order_target = Company.name.asc() if is_asc else Company.name.desc()
    elif sort_by == "domain":
        order_target = Company.domain.asc() if is_asc else Company.domain.desc()
    elif sort_by == "reason":
        order_target = Company.invalid_reason.asc() if is_asc else Company.invalid_reason.desc()
    else:
        order_target = Company.id.asc() if is_asc else Company.id.desc()

    comps = q.order_by(order_target, Company.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total_count": total_count,
        "total_pages": total_pages,
        "current_page": page,
        "page_size": page_size,
        "companies": [
            {
                "id": c.id,
                "name": c.name,
                "domain": c.domain,
                "invalid_reason": c.invalid_reason or "Flagged as non-company entity",
                "invalid_at": c.invalid_at.strftime("%Y-%m-%d %H:%M") if c.invalid_at else None
            }
            for c in comps
        ]
    }


@app.delete("/api/admin/companies/{company_id}")
def delete_company_admin(
    company_id: int,
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    db.query(CompanyEmail).filter(CompanyEmail.company_id == company_id).delete()
    db.query(CompanyProfile).filter(CompanyProfile.company_id == company_id).delete()
    db.query(ColdPitch).filter(ColdPitch.company_id == company_id).delete()
    db.query(OutreachLog).filter(OutreachLog.company_id == company_id).delete()
    db.delete(company)
    db.commit()
    invalidate_filter_cache()
    return {"success": True, "message": f"Company #{company_id} permanently deleted."}


@app.get("/api/admin/companies")
def list_companies_admin(
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    search: str = Query(""),
    status: str = Query("valid"),  # 'valid', 'invalid', 'all'
    city: str = Query(""),
    category: str = Query(""),
    sort_by: str = Query("id"),
    sort_order: str = Query("desc"),
    ids_only: bool = Query(False),
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    q = db.query(Company)
    if status == "valid":
        q = q.filter(Company.is_invalid == False)
    elif status == "invalid":
        q = q.filter(Company.is_invalid == True)

    if search:
        s = f"%{search.strip()}%"
        q = q.filter(or_(Company.name.ilike(s), Company.domain.ilike(s)))
    # city: a city name or slug; category: an industry code (it, sales, ...). Exact ID matches.
    for cond in (_city_id_cond([city] if city else []), _domain_id_cond(category)):
        if cond is not None:
            q = q.filter(cond)

    # Fast total count: check cache if unfiltered to prevent scanning 132k rows on every click
    is_unfiltered = (not search and not city and not category)
    if is_unfiltered and status == "valid" and _admin_metrics_cache["data"] and _admin_metrics_cache["data"].get("companies_valid"):
        total_count = _admin_metrics_cache["data"]["companies_valid"]
    elif is_unfiltered and status == "invalid" and _admin_metrics_cache["data"] and _admin_metrics_cache["data"].get("companies_invalid"):
        total_count = _admin_metrics_cache["data"]["companies_invalid"]
    else:
        total_count = q.with_entities(func.count(Company.id)).scalar() or 0

    if ids_only:
        # "Select all matching" in the admin bulk bar; capped at the bulk-action limit.
        ids = [r[0] for r in q.with_entities(Company.id).order_by(Company.id).limit(500).all()]
        return {"ids": ids, "total_count": total_count}

    total_pages = max(1, (total_count + page_size - 1) // page_size)

    sort_order_clean = sort_order.lower() if sort_order in ("asc", "desc") else "desc"
    is_asc = sort_order_clean == "asc"

    if sort_by == "name":
        order_target = Company.name.asc() if is_asc else Company.name.desc()
    elif sort_by == "domain":
        order_target = Company.domain.asc() if is_asc else Company.domain.desc()
    elif sort_by in ("city", "location"):
        order_target = Company.city.asc() if is_asc else Company.city.desc()
    elif sort_by in ("email", "has_email"):
        order_target = Company.has_email.asc() if is_asc else Company.has_email.desc()
    elif sort_by == "category":
        order_target = Company.source_query.asc() if is_asc else Company.source_query.desc()
    elif sort_by == "created_at":
        order_target = Company.created_at.asc() if is_asc else Company.created_at.desc()
    else:
        order_target = Company.id.asc() if is_asc else Company.id.desc()

    comps = q.with_entities(
        Company.id,
        Company.name,
        Company.domain,
        Company.website_url,
        Company.city,
        Company.phone,
        Company.source_query,
        Company.search_keyword,
        Company.has_email,
        Company.is_invalid,
        Company.invalid_reason,
        Company.created_at
    ).order_by(order_target, Company.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    comp_ids = [c[0] for c in comps]
    emails_by_comp = {}
    if comp_ids:
        emails = db.query(CompanyEmail.company_id, CompanyEmail.email_address, CompanyEmail.is_primary)\
                   .filter(CompanyEmail.company_id.in_(comp_ids)).all()
        for em in emails:
            if em[0] not in emails_by_comp or em[2]:
                emails_by_comp[em[0]] = em[1]

    profiles_by_comp = {}
    if comp_ids:
        profiles = db.query(CompanyProfile.company_id, CompanyProfile.tech_stack, CompanyProfile.summary_short)\
                     .filter(CompanyProfile.company_id.in_(comp_ids)).all()
        for p in profiles:
            profiles_by_comp[p[0]] = p

    results = []
    for c in comps:
        prof = profiles_by_comp.get(c[0])
        results.append({
            "id": c[0],
            "name": c[1],
            "domain": c[2],
            "website_url": c[3] or f"https://{c[2]}",
            "city": c[4] or "Unknown",
            "phone": c[5] or "",
            "category": c[6] or c[7] or "Tech",
            "email": emails_by_comp.get(c[0]) or "",
            "has_email": c[8] or bool(emails_by_comp.get(c[0])),
            "tech_stack": prof[1] if prof and prof[1] else [],
            "summary": prof[2] if prof and prof[2] else "",
            "is_invalid": c[9],
            "invalid_reason": c[10] or "",
            "created_at": c[11].strftime("%Y-%m-%d %H:%M") if c[11] else None
        })

    return {
        "total_count": total_count,
        "total_pages": total_pages,
        "current_page": page,
        "page_size": page_size,
        "companies": results
    }


@app.get("/api/admin/companies/{company_id}")
def get_company_admin(
    company_id: int,
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Company not found")

    primary_email = db.query(CompanyEmail).filter(CompanyEmail.company_id == c.id, CompanyEmail.is_primary == True).first()
    if not primary_email:
        primary_email = db.query(CompanyEmail).filter(CompanyEmail.company_id == c.id).first()

    prof = db.query(CompanyProfile).filter(CompanyProfile.company_id == c.id).first()

    return {
        "id": c.id,
        "name": c.name,
        "domain": c.domain,
        "website_url": c.website_url or f"https://{c.domain}",
        "city": c.city or "",
        "phone": c.phone or "",
        "category": c.source_query or c.search_keyword or "Tech",
        "email": primary_email.email_address if primary_email else "",
        "tech_stack": prof.tech_stack if prof and prof.tech_stack else [],
        "tech_stack_str": ", ".join(prof.tech_stack) if prof and prof.tech_stack else "",
        "summary": prof.summary_short if prof else "",
        "is_invalid": c.is_invalid,
        "invalid_reason": c.invalid_reason or ""
    }


@app.put("/api/admin/companies/{company_id}")
def update_company_admin(
    company_id: int,
    payload: UpdateCompanyAdminRequest,
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Company not found")

    raw_domain = (payload.domain or c.domain).strip().lower()
    clean_dom = re.sub(r'^(?:https?://)?(?:www\.)?', '', raw_domain).split('/')[0].split(':')[0]
    clean_name = clean_company_name(payload.name.strip(), clean_dom) or payload.name.strip()

    c.name = clean_name
    c.domain = clean_dom
    c.website_url = payload.website_url.strip() if payload.website_url else f"https://{clean_dom}"
    c.city = payload.city.strip() if payload.city else None
    c.phone = payload.phone.strip() if payload.phone else None
    if payload.category:
        c.source_query = payload.category.strip()
        c.search_keyword = payload.category.strip()

    if payload.is_invalid is not None:
        c.is_invalid = payload.is_invalid
        if payload.is_invalid:
            c.invalid_reason = payload.invalid_reason or "Manually quarantined by administrator"
            c.invalid_at = datetime.utcnow()
        else:
            c.invalid_reason = None
            c.invalid_at = None

    # Update or add email
    if payload.email is not None:
        clean_email = payload.email.strip().lower()
        if "@" in clean_email:
            existing_email = db.query(CompanyEmail).filter(CompanyEmail.company_id == c.id).first()
            if existing_email:
                existing_email.email_address = clean_email
                existing_email.is_primary = True
            else:
                db.add(CompanyEmail(company_id=c.id, email_address=clean_email, is_primary=True, email_type="primary"))
            c.has_email = True
        elif clean_email == "":
            db.query(CompanyEmail).filter(CompanyEmail.company_id == c.id).delete()
            c.has_email = False

    # Update profile & tech stack
    prof = db.query(CompanyProfile).filter(CompanyProfile.company_id == c.id).first()
    if payload.tech_stack is not None or payload.summary is not None:
        tech_list = [t.strip() for t in payload.tech_stack.split(",") if t.strip()] if payload.tech_stack else []
        if prof:
            prof.tech_stack = tech_list
            if payload.summary:
                prof.summary_short = payload.summary.strip()
        else:
            db.add(CompanyProfile(
                company_id=c.id,
                tech_stack=tech_list,
                summary_short=payload.summary.strip() if payload.summary else f"{clean_name} enterprise profile",
                industry=c.source_query or "Tech"
            ))
        c.is_enriched = True

    db.commit()
    invalidate_filter_cache()
    return {
        "success": True,
        "company_id": c.id,
        "name": c.name,
        "domain": c.domain,
        "message": f"Successfully updated '{c.name}'."
    }


@app.post("/api/admin/companies/{company_id}/quarantine")
def quarantine_company_admin(
    company_id: int,
    payload: QuarantineCompanyRequest,
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Company not found")
    c.is_invalid = True
    c.invalid_reason = payload.reason or "Quarantined by Master Admin"
    c.invalid_at = datetime.utcnow()
    db.commit()
    invalidate_filter_cache()
    return {"success": True, "message": f"Company '{c.name}' quarantined."}


@app.post("/api/admin/companies/bulk-action")
def bulk_company_action_admin(
    payload: BulkCompanyActionRequest,
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    ids = list({int(i) for i in payload.ids})
    if not ids:
        raise HTTPException(status_code=400, detail="No companies selected.")
    if len(ids) > 500:
        raise HTTPException(status_code=400, detail="Select at most 500 companies per action.")
    if payload.action not in ("quarantine", "delete"):
        raise HTTPException(status_code=400, detail="Action must be 'quarantine' or 'delete'.")

    if payload.action == "quarantine":
        count = db.query(Company).filter(Company.id.in_(ids)).update(
            {Company.is_invalid: True,
             Company.invalid_reason: payload.reason or "Quarantined by Master Admin",
             Company.invalid_at: datetime.utcnow()},
            synchronize_session=False,
        )
    else:
        # Same child-first order as the single delete endpoint.
        for model in (CompanyEmail, CompanyProfile, ColdPitch, OutreachLog):
            db.query(model).filter(model.company_id.in_(ids)).delete(synchronize_session=False)
        count = db.query(Company).filter(Company.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    invalidate_filter_cache()
    verb = "quarantined" if payload.action == "quarantine" else "permanently deleted"
    return {"success": True, "count": count, "message": f"{count} companies {verb}."}


@app.post("/api/admin/companies/{company_id}/restore")
def restore_company_admin(
    company_id: int,
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Company not found")
    c.is_invalid = False
    c.invalid_reason = None
    c.invalid_at = None
    db.commit()
    invalidate_filter_cache()
    return {"success": True, "message": f"Company '{c.name}' restored to active directory."}


# --- Live Database Maintenance Engines ---

@app.post("/api/admin/maintenance/sanitize-names")
def sanitize_names_admin(
    payload: SanitizeNamesRequest,
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    t0 = time.time()
    delimiters = [' - ', ' | ', ' : ', ' – ', ' — ', ' • ', ' · ', '|']
    chunk_size = 1000
    last_id = 0
    scanned = 0
    cleaned = 0
    samples = []

    limit = max(100, min(10000, payload.limit or 2000))

    while scanned < limit:
        rows = (
            db.query(Company.id, Company.name, Company.domain)
            .filter(Company.id > last_id)
            .order_by(Company.id.asc())
            .limit(chunk_size)
            .all()
        )
        if not rows:
            break
        last_id = rows[-1][0]
        scanned += len(rows)

        updates = []
        for cid, cname, cdomain in rows:
            if not cname:
                continue
            if any(d in cname for d in delimiters):
                cleaned_name = clean_company_name(cname, cdomain)
                if cleaned_name and cleaned_name != cname:
                    cleaned += 1
                    if len(samples) < 15:
                        samples.append({"before": cname, "after": cleaned_name, "domain": cdomain})
                    updates.append({"id": cid, "name": cleaned_name})

        if not payload.dry_run and updates:
            db.bulk_update_mappings(Company, updates)
            db.commit()

    if not payload.dry_run and cleaned > 0:
        invalidate_filter_cache()

    return {
        "success": True,
        "dry_run": payload.dry_run,
        "scanned": scanned,
        "cleaned": cleaned,
        "elapsed_seconds": round(time.time() - t0, 2),
        "samples": samples,
        "message": f"{'Previewed' if payload.dry_run else 'Sanitized'} {cleaned} company names out of {scanned} scanned records."
    }


@app.post("/api/admin/maintenance/purge-non-companies")
def purge_non_companies_admin(
    payload: PurgeNonCompaniesRequest,
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    from filter_non_companies import is_non_company
    t0 = time.time()
    os.makedirs("logs", exist_ok=True)
    csv_path = os.path.join("logs", "removed_non_companies_log.csv")

    batch_size = 2000
    last_id = 0
    scanned = 0
    flagged_records = []
    limit = max(500, min(15000, payload.limit or 5000))

    while scanned < limit:
        rows = (
            db.query(Company.id, Company.name, Company.domain, Company.city, Company.source_query)
            .filter(Company.is_invalid == False, Company.id > last_id)
            .order_by(Company.id.asc())
            .limit(batch_size)
            .all()
        )
        if not rows:
            break
        last_id = rows[-1][0]
        scanned += len(rows)

        for cid, cname, cdom, ccity, cquery in rows:
            flagged, reason = is_non_company(cname, cdom)
            if flagged:
                flagged_records.append({
                    "id": cid,
                    "name": cname,
                    "domain": cdom,
                    "city": ccity or "",
                    "source_query": cquery or "",
                    "reason": reason
                })

    if flagged_records:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "name", "domain", "city", "source_query", "reason"])
            writer.writeheader()
            writer.writerows(flagged_records)

    if not payload.dry_run and flagged_records:
        flagged_ids = [r["id"] for r in flagged_records]
        now = datetime.utcnow()
        for i in range(0, len(flagged_ids), 500):
            chunk = flagged_ids[i:i + 500]
            db.query(Company).filter(Company.id.in_(chunk)).update(
                {
                    Company.is_invalid: True,
                    Company.invalid_reason: "Automated Non-Company Filter: Institute / Academy / Coaching / Portfolio / Education",
                    Company.invalid_at: now
                },
                synchronize_session=False
            )
            db.commit()
        invalidate_filter_cache()

    return {
        "success": True,
        "dry_run": payload.dry_run,
        "scanned": scanned,
        "flagged": len(flagged_records),
        "elapsed_seconds": round(time.time() - t0, 2),
        "samples": flagged_records[:20],
        "csv_download_url": "/api/admin/maintenance/download-non-companies-csv" if flagged_records else None,
        "message": f"{'Identified' if payload.dry_run else 'Quarantined'} {len(flagged_records)} non-company leads out of {scanned} scanned records."
    }


@app.get("/api/admin/maintenance/download-non-companies-csv")
def download_non_companies_csv(
    admin: User = Depends(require_master_admin)
):
    csv_path = os.path.join("logs", "removed_non_companies_log.csv")
    if not os.path.exists(csv_path):
        raise HTTPException(status_code=404, detail="No audit CSV generated yet. Run the non-company filter first.")
    return FileResponse(csv_path, filename="removed_non_companies_log.csv", media_type="text/csv")


# --- GitHub CI/CD Workflows Telemetry ---

def get_local_workflow_definitions() -> list[dict]:
    """
    Dynamically scans .github/workflows directory and extracts workflow dispatch inputs,
    types, default values, options, and descriptions. Uses PyYAML when available,
    with a resilient fallback line-parser to guarantee 100% zero-dependency execution.
    """
    workflows_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".github", "workflows")
    if not os.path.isdir(workflows_dir):
        return []

    results = []
    has_yaml = False
    try:
        import yaml
        has_yaml = True
    except ImportError:
        pass

    for fname in sorted(os.listdir(workflows_dir)):
        if not (fname.endswith(".yml") or fname.endswith(".yaml")):
            continue
        fpath = os.path.join(workflows_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content_str = f.read()

            wf_name = fname
            has_dispatch = False
            parsed_inputs = []

            if has_yaml:
                try:
                    data = yaml.safe_load(content_str)
                    if isinstance(data, dict):
                        wf_name = data.get("name") or fname
                        on_block = data.get(True) or data.get("on") or {}
                        raw_inputs = {}
                        if isinstance(on_block, dict):
                            if "workflow_dispatch" in on_block:
                                has_dispatch = True
                                dispatch_cfg = on_block.get("workflow_dispatch") or {}
                                if isinstance(dispatch_cfg, dict):
                                    raw_inputs = dispatch_cfg.get("inputs") or {}
                        elif isinstance(on_block, list) and "workflow_dispatch" in on_block:
                            has_dispatch = True
                        elif on_block == "workflow_dispatch":
                            has_dispatch = True

                        if isinstance(raw_inputs, dict):
                            for p_name, p_cfg in raw_inputs.items():
                                if not isinstance(p_cfg, dict):
                                    p_cfg = {}
                                parsed_inputs.append({
                                    "name": str(p_name),
                                    "description": str(p_cfg.get("description", "")),
                                    "required": bool(p_cfg.get("required", False)),
                                    "default": "" if p_cfg.get("default") is None else str(p_cfg.get("default")),
                                    "type": str(p_cfg.get("type", "string")).lower(),
                                    "options": [str(opt) for opt in p_cfg.get("options", [])] if isinstance(p_cfg.get("options"), list) else []
                                })
                except Exception as y_err:
                    print(f"[Workflow PyYAML Error] {fname}: {y_err}")

            # Fallback regex parser if yaml is absent or returned no inputs while workflow_dispatch exists
            if not parsed_inputs and "workflow_dispatch" in content_str:
                has_dispatch = True
                name_match = re.search(r"^name:\s*(.+)$", content_str, re.MULTILINE)
                if name_match:
                    wf_name = name_match.group(1).strip().strip("'\"")

                inputs_match = re.search(r"workflow_dispatch:\s*\n(?:\s*inputs:\s*\n)?((?:[ \t]{4,}.*\n?)+)", content_str)
                if inputs_match:
                    inputs_block = inputs_match.group(1)
                    param_chunks = re.findall(r"^(\s{4,8})(\w+):\s*\n((?:\1\s{2,}.*\n?)+)", inputs_block, re.MULTILINE)
                    for indent, p_name, body in param_chunks:
                        desc_m = re.search(r'description:\s*["\']?(.*?)["\']?\s*$', body, re.MULTILINE)
                        req_m = re.search(r'required:\s*(true|false)', body, re.MULTILINE | re.IGNORECASE)
                        def_m = re.search(r'default:\s*["\']?(.*?)["\']?\s*$', body, re.MULTILINE)
                        type_m = re.search(r'type:\s*(\w+)', body, re.MULTILINE)
                        options_m = re.findall(r'-\s*(.+)$', body, re.MULTILINE)

                        parsed_inputs.append({
                            "name": p_name,
                            "description": desc_m.group(1).strip() if desc_m else "",
                            "required": req_m.group(1).lower() == "true" if req_m else False,
                            "default": def_m.group(1).strip() if def_m else "",
                            "type": type_m.group(1).lower() if type_m else "string",
                            "options": [opt.strip().strip("'\"") for opt in options_m] if options_m else []
                        })

            results.append({
                "file_name": fname,
                "name": wf_name,
                "path": f".github/workflows/{fname}",
                "has_dispatch": has_dispatch or ("workflow_dispatch" in content_str),
                "inputs": parsed_inputs
            })
        except Exception as file_err:
            print(f"[Workflow Parser Error] {fname}: {file_err}")

    return results


@app.get("/api/admin/github/telemetry")
async def get_github_telemetry(
    workflow: str = Query("cloud_scout.yml"),
    force: bool = Query(False),
    admin: User = Depends(require_master_admin)
):
    repo = "vorarahul4700/outreachPilot"
    # Clean workflow parameter
    clean_wf = workflow.split("/")[-1] if workflow else "cloud_scout.yml"
    if not clean_wf.endswith(".yml") and not clean_wf.endswith(".yaml"):
        clean_wf += ".yml"

    now = time.time()
    cached = _github_telemetry_cache.get(clean_wf)
    if not force and cached and (now - cached.get("timestamp", 0) < 30.0):
        return cached["data"]

    # 1. Dynamically discover all local workflows and their schemas
    local_defs = get_local_workflow_definitions()
    local_map = {w["file_name"]: w for w in local_defs}

    headers = {
        "User-Agent": "OutreachPilot-MasterAdmin",
        "Accept": "application/vnd.github.v3+json"
    }
    gh_token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if gh_token:
        headers["Authorization"] = f"Bearer {gh_token}"

    runs_data = []
    workflows_data = []

    try:
        import httpx
        async with httpx.AsyncClient(timeout=8.0) as client:
            runs_url = f"https://api.github.com/repos/{repo}/actions/workflows/{clean_wf}/runs?per_page=10"
            wf_url = f"https://api.github.com/repos/{repo}/actions/workflows"

            # Parallel non-blocking execution via asyncio.gather
            runs_resp, wf_resp = await asyncio.gather(
                client.get(runs_url, headers=headers),
                client.get(wf_url, headers=headers),
                return_exceptions=True
            )

            # Handle runs response (fallback to general runs if workflow not found)
            if not isinstance(runs_resp, Exception) and runs_resp.status_code != 200:
                try:
                    runs_resp = await client.get(f"https://api.github.com/repos/{repo}/actions/runs?per_page=10", headers=headers)
                except Exception:
                    pass

            if not isinstance(runs_resp, Exception) and getattr(runs_resp, "status_code", None) == 200:
                raw_runs = runs_resp.json().get("workflow_runs", [])
                for r in raw_runs:
                    duration_str = "--"
                    if r.get("run_started_at") and r.get("updated_at"):
                        try:
                            start = datetime.fromisoformat(r["run_started_at"].replace("Z", "+00:00"))
                            end = datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00"))
                            secs = int((end - start).total_seconds())
                            duration_str = f"{secs // 60}m {secs % 60}s" if secs >= 60 else f"{secs}s"
                        except Exception:
                            pass

                    runs_data.append({
                        "id": r.get("id"),
                        "run_number": r.get("run_number"),
                        "name": r.get("name"),
                        "display_title": r.get("display_title") or r.get("name"),
                        "event": r.get("event"),
                        "status": r.get("status"),
                        "conclusion": r.get("conclusion"),
                        "branch": r.get("head_branch") or "main",
                        "commit_sha": (r.get("head_sha") or "")[:7],
                        "commit_msg": (r.get("head_commit") or {}).get("message", "").split("\n")[0][:60],
                        "html_url": r.get("html_url"),
                        "created_at": r.get("created_at"),
                        "duration": duration_str,
                        "actor": {
                            "login": (r.get("actor") or {}).get("login", "automation"),
                            "avatar_url": (r.get("actor") or {}).get("avatar_url", "")
                        }
                    })

            if not isinstance(wf_resp, Exception) and getattr(wf_resp, "status_code", None) == 200:
                raw_wfs = wf_resp.json().get("workflows", [])
                seen_files = set()
                for w in raw_wfs:
                    fname = w.get("path", "").split("/")[-1]
                    seen_files.add(fname)
                    loc = local_map.get(fname, {})
                    workflows_data.append({
                        "id": w.get("id"),
                        "name": w.get("name") or loc.get("name", fname),
                        "path": w.get("path") or f".github/workflows/{fname}",
                        "file_name": fname,
                        "state": w.get("state") or "active",
                        "html_url": w.get("html_url") or f"https://github.com/{repo}/actions/workflows/{fname}",
                        "badge_url": w.get("badge_url"),
                        "has_dispatch": loc.get("has_dispatch", True),
                        "inputs": loc.get("inputs", [])
                    })

                # Append any local workflows not present in GitHub API response
                for loc in local_defs:
                    if loc["file_name"] not in seen_files:
                        workflows_data.append({
                            "id": loc["file_name"],
                            "name": loc["name"],
                            "path": loc["path"],
                            "file_name": loc["file_name"],
                            "state": "active",
                            "html_url": f"https://github.com/{repo}/actions/workflows/{loc['file_name']}",
                            "badge_url": None,
                            "has_dispatch": loc.get("has_dispatch", True),
                            "inputs": loc.get("inputs", [])
                        })
    except Exception as fetch_err:
        print(f"[GitHub API Error] {fetch_err}")

    # Fallback if GitHub API was unreachable: use full dynamic local definitions
    if not workflows_data:
        for loc in local_defs:
            workflows_data.append({
                "id": loc["file_name"],
                "name": loc["name"],
                "path": loc["path"],
                "file_name": loc["file_name"],
                "state": "active",
                "html_url": f"https://github.com/{repo}/actions/workflows/{loc['file_name']}",
                "badge_url": None,
                "has_dispatch": loc.get("has_dispatch", True),
                "inputs": loc.get("inputs", [])
            })

    result_payload = {
        "repo": repo,
        "repo_actions_url": f"https://github.com/{repo}/actions",
        "has_server_token": bool(gh_token),
        "selected_workflow": clean_wf,
        "workflows": workflows_data,
        "runs": runs_data
    }
    _github_telemetry_cache[clean_wf] = {
        "timestamp": time.time(),
        "data": result_payload
    }
    return result_payload


@app.post("/api/admin/github/workflows/{workflow_file}/dispatch")
async def dispatch_github_workflow(
    workflow_file: str,
    payload: DispatchWorkflowRequest,
    admin: User = Depends(require_master_admin)
):
    repo = "vorarahul4700/outreachPilot"
    # Only ever use the server-side token. A caller-supplied token is ignored so a
    # compromised/forged admin session can't smuggle in its own credentials.
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if not token:
        raise HTTPException(
            status_code=400,
            detail="GitHub token is not configured on the server. Set GITHUB_TOKEN in the environment."
        )

    clean_file = workflow_file.split("/")[-1]
    if not clean_file.endswith(".yml") and not clean_file.endswith(".yaml"):
        clean_file += ".yml"

    # Allowlist: only dispatch workflows that actually exist in .github/workflows,
    # never an arbitrary filename passed in the URL.
    _wf_dir = os.path.join(os.path.dirname(__file__), ".github", "workflows")
    try:
        _allowed = {f for f in os.listdir(_wf_dir) if f.endswith((".yml", ".yaml"))}
    except Exception:
        _allowed = set()
    if clean_file not in _allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown workflow '{clean_file}'. Allowed: {sorted(_allowed) or 'none found'}."
        )

    headers = {
        "User-Agent": "OutreachPilot-MasterAdmin",
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {token}"
    }

    dispatch_url = f"https://api.github.com/repos/{repo}/actions/workflows/{clean_file}/dispatches"

    # GitHub dispatch expects inputs as string dictionary
    formatted_inputs = {k: str(v) for k, v in payload.inputs.items() if v is not None} if payload.inputs else {}

    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                dispatch_url,
                json={"ref": payload.ref or "main", "inputs": formatted_inputs},
                headers=headers
            )
            if resp.status_code in (204, 201, 200):
                return {
                    "success": True,
                    "workflow": clean_file,
                    "message": f"Successfully triggered '{clean_file}'! GitHub runner jobs will spin up within seconds."
                }
            else:
                err_body = resp.text
                try:
                    err_json = resp.json()
                    err_msg = err_json.get("message", err_body)
                except Exception:
                    err_msg = err_body
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"GitHub API Error: {err_msg}"
                )
    except HTTPException:
        raise
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Failed to communicate with GitHub: {str(ex)}")


# --- Subscription Tier Administration ---

@app.get("/api/admin/tiers")
def list_tiers_admin(
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    tiers = db.query(SubscriptionTier).order_by(SubscriptionTier.id.asc()).all()
    sub_counts = dict(
        db.query(User.subscription_tier, func.count(User.id))
        .group_by(User.subscription_tier)
        .all()
    )

    return {
        "tiers": [
            {
                "id": t.id,
                "code": t.code,
                "name": t.name,
                "subtitle": t.subtitle or "",
                "price_inr": t.price_inr,
                "daily_pitch_limit": t.daily_pitch_limit,
                "features": t.features or [],
                "badge": t.badge or "",
                "is_active": t.is_active,
                "subscriber_count": sub_counts.get(t.code, 0)
            }
            for t in tiers
        ]
    }


@app.post("/api/admin/tiers")
def create_tier_admin(
    payload: CreateTierRequest,
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    code = payload.code.strip().lower()
    existing = db.query(SubscriptionTier).filter(SubscriptionTier.code == code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Tier with code '{code}' already exists.")

    tier = SubscriptionTier(
        code=code,
        name=payload.name.strip(),
        subtitle=payload.subtitle.strip() if payload.subtitle else "",
        price_inr=payload.price_inr,
        daily_pitch_limit=payload.daily_pitch_limit,
        features=payload.features or [],
        badge=payload.badge.strip() if payload.badge else None,
        is_active=True
    )
    db.add(tier)
    db.commit()
    db.refresh(tier)
    clear_public_tiers_cache()  # show the new plan on the home page right away
    return {"success": True, "tier_id": tier.id, "message": f"Created tier '{tier.name}'."}


@app.put("/api/admin/tiers/{tier_id}")
def update_tier_admin(
    tier_id: int,
    payload: UpdateTierRequest,
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    tier = db.query(SubscriptionTier).filter(SubscriptionTier.id == tier_id).first()
    if not tier:
        raise HTTPException(status_code=404, detail="Subscription tier not found")

    tier.name = payload.name.strip()
    tier.subtitle = payload.subtitle.strip() if payload.subtitle else ""
    tier.price_inr = payload.price_inr
    tier.daily_pitch_limit = payload.daily_pitch_limit
    tier.features = payload.features or []
    tier.badge = payload.badge.strip() if payload.badge else None
    tier.is_active = payload.is_active

    users_synced = 0
    if payload.sync_users and tier.code != "master_admin":
        users_synced = db.query(User).filter(User.subscription_tier == tier.code).update(
            {User.daily_pitch_limit: tier.daily_pitch_limit},
            synchronize_session=False
        )

    db.commit()
    clear_public_tiers_cache()  # show the edit on the home page right away
    return {
        "success": True,
        "tier_id": tier.id,
        "name": tier.name,
        "daily_pitch_limit": tier.daily_pitch_limit,
        "price_inr": tier.price_inr,
        "users_synced": users_synced,
        "message": f"Updated '{tier.name}' tier plan successfully ({users_synced} users synced to {tier.daily_pitch_limit} pitches/day)."
    }


# --- Admin: Cold Outreach Pitches & Delivery Telemetry ---
@app.get("/api/admin/pitches")
def list_pitches_admin(
    filter: str = Query("today"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=5, le=100),
    search: str = Query(""),
    sort_by: str = Query("sent_at"),
    sort_order: str = Query("desc"),
    user_id: Optional[int] = Query(None),
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    """
    Returns verified cold outreach pitches dispatched across all users.
    Supports time filtering (today vs all), search, sorting, and pagination.
    """
    import math
    now_utc = datetime.utcnow()
    today_start = datetime(now_utc.year, now_utc.month, now_utc.day, 0, 0, 0)

    # 1. Base query from OutreachLog
    query = db.query(OutreachLog).options(
        joinedload(OutreachLog.company),
        joinedload(OutreachLog.user)
    )

    # Pre-calculate counts (scoped to one sender when user_id is given)
    count_q = db.query(func.count(OutreachLog.id))
    if user_id is not None:
        query = query.filter(OutreachLog.user_id == user_id)
        count_q = count_q.filter(OutreachLog.user_id == user_id)
    today_count = count_q.filter(OutreachLog.sent_at >= today_start).scalar() or 0
    total_count_all = count_q.scalar() or 0

    if filter == "today":
        query = query.filter(OutreachLog.sent_at >= today_start)

    if search:
        search_term = f"%{search.strip().lower()}%"
        query = query.outerjoin(Company, OutreachLog.company_id == Company.id)\
                     .outerjoin(User, OutreachLog.user_id == User.id)\
                     .filter(
                         or_(
                             func.lower(OutreachLog.recipient_email).like(search_term),
                             func.lower(OutreachLog.subject).like(search_term),
                             func.lower(Company.name).like(search_term),
                             func.lower(Company.domain).like(search_term),
                             func.lower(User.email).like(search_term)
                         )
                     )

    # Sorting
    is_asc = (sort_order.lower() == "asc")
    if sort_by == "sent_at":
        order_col = OutreachLog.sent_at.asc() if is_asc else OutreachLog.sent_at.desc()
    elif sort_by == "recipient":
        order_col = OutreachLog.recipient_email.asc() if is_asc else OutreachLog.recipient_email.desc()
    elif sort_by == "subject":
        order_col = OutreachLog.subject.asc() if is_asc else OutreachLog.subject.desc()
    elif sort_by == "status":
        order_col = OutreachLog.status.asc() if is_asc else OutreachLog.status.desc()
    else:
        order_col = OutreachLog.sent_at.desc()

    total_filtered = query.count()
    records = query.order_by(order_col).offset((page - 1) * page_size).limit(page_size).all()

    # Fallback to ColdPitch table if OutreachLog is empty
    if total_filtered == 0 and total_count_all == 0:
        cp_query = db.query(ColdPitch).options(
            joinedload(ColdPitch.company),
            joinedload(ColdPitch.user)
        )
        if filter == "today":
            cp_query = cp_query.filter(ColdPitch.sent_at >= today_start)
        else:
            cp_query = cp_query.filter(ColdPitch.status == "SENT")

        if search:
            search_term = f"%{search.strip().lower()}%"
            cp_query = cp_query.outerjoin(Company, ColdPitch.company_id == Company.id)\
                               .outerjoin(User, ColdPitch.user_id == User.id)\
                               .filter(
                                   or_(
                                       func.lower(ColdPitch.target_email).like(search_term),
                                       func.lower(ColdPitch.subject_line).like(search_term),
                                       func.lower(Company.name).like(search_term),
                                       func.lower(Company.domain).like(search_term),
                                       func.lower(User.email).like(search_term)
                                   )
                               )

        total_filtered = cp_query.count()
        today_count = db.query(func.count(ColdPitch.id)).filter(ColdPitch.sent_at >= today_start).scalar() or 0
        total_count_all = db.query(func.count(ColdPitch.id)).filter(ColdPitch.status == "SENT").scalar() or 0
        cp_records = cp_query.order_by(ColdPitch.sent_at.desc() if not is_asc else ColdPitch.sent_at.asc()).offset((page - 1) * page_size).limit(page_size).all()

        pitches_list = [
            {
                "id": cp.id,
                "company_id": cp.company_id,
                "company_name": cp.company.name if cp.company else "Unknown",
                "company_domain": cp.company.domain if cp.company else "",
                "company_city": cp.company.city if cp.company else "",
                "recipient_email": cp.target_email or "",
                "sender_email": cp.user.email if cp.user else "System",
                "sender_name": cp.user.name if cp.user else "Admin",
                "subject": cp.subject_line,
                "email_body": cp.email_body or "",
                "delivery_method": cp.delivery_method or "OAUTH_DIRECT",
                "status": cp.status or "SENT",
                "error_message": None,
                "sent_at": ist_text(cp.sent_at or cp.created_at)
            }
            for cp in cp_records
        ]
    else:
        pitches_list = [
            {
                "id": log.id,
                "company_id": log.company_id,
                "company_name": log.company.name if log.company else "Unknown",
                "company_domain": log.company.domain if log.company else "",
                "company_city": log.company.city if log.company else "",
                "recipient_email": log.recipient_email,
                "sender_email": log.user.email if log.user else "System",
                "sender_name": log.user.name if log.user else "Admin",
                "subject": log.subject,
                "email_body": log.email_body or "",
                "delivery_method": log.delivery_method or "GMAIL_OAUTH",
                "status": log.status or "SENT",
                "error_message": log.error_message,
                "sent_at": ist_text(log.sent_at)
            }
            for log in records
        ]

    return {
        "filter": filter,
        "page": page,
        "page_size": page_size,
        "total": total_filtered,
        "today_count": today_count,
        "total_count_all": total_count_all,
        "total_pages": max(1, math.ceil(total_filtered / page_size)),
        "pitches": pitches_list
    }


# --- Master Kill Switch Administration ---
@app.get("/api/admin/system/kill-switch")
def get_kill_switch_status(
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    """Returns the current state of the Subscription & RBAC Kill Switch."""
    return {
        "active": is_subscription_kill_switch_active(db)
    }


@app.post("/api/admin/system/kill-switch")
async def toggle_kill_switch_status(
    request: Request,
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    """
    Toggles the Master Subscription & RBAC Kill Switch.

    Design contract (state preservation):
    - The kill switch is a GLOBAL OVERLAY flag only. It never touches individual
      User.subscription_tier or User.daily_pitch_limit columns.
    - When OFF: each user's real purchased/assigned tier is automatically restored
      because auth_status and get_user_subscription_info always read from the DB row.
    - When ON: all logged-in users are presented as Temp Users (infinite pitches)
      without any DB mutation. Their real tier is preserved in real_subscription_tier.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    new_state = bool(body.get("active", False))
    previous_state = is_subscription_kill_switch_active(db)
    set_subscription_kill_switch(new_state, db)
    return {
        "active": new_state,
        "previous_state": previous_state,
        "state_preserved": True,  # User DB rows are never mutated; real tiers always persist
        "message": (
            "Kill Switch ENABLED. Open-access mode active. All logged-in users "
            "get infinite pitch generation. Subscription UI suppressed. "
            "Individual user tiers are preserved in DB and will be fully restored on disable."
            if new_state else
            "Kill Switch DISABLED. Standard subscription tiers, RBAC, and daily quota limits "
            "restored. Each user's previously purchased/assigned plan is automatically in effect."
        )
    }


# --- Category visibility (admin panel > Categories) ---
# Switching a category off hides it and all of its companies from every
# user-facing screen (see seo_engine.visible_kw_clause). Nothing is deleted.
class CategoryVisibilityRequest(BaseModel):
    slugs: list[str]
    hidden: bool


def _clear_category_dependent_caches() -> None:
    """Drop every cache that could still show companies of a category that was just switched."""
    seo_engine.clear_hidden_categories_cache()
    seo_engine.clear_seo_cache()
    _filter_cache["timestamp"] = 0.0
    _filter_cache["data"] = None
    _dynamic_filter_cache.clear()
    invalidate_admin_metrics_cache()


def _category_visibility_payload(categories: list[dict]) -> dict:
    hidden = [c for c in categories if c["hidden"]]
    return {
        "categories": categories,
        "total_categories": len(categories),
        "hidden_categories": len(hidden),
        "hidden_companies": sum(c["count"] for c in hidden),
        "total_companies": sum(c["count"] for c in categories),
    }


@app.get("/api/admin/categories")
def list_category_visibility(
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    """Every category with its company count and whether users can see it."""
    return _category_visibility_payload(seo_engine.get_category_admin_overview(db))


@app.post("/api/admin/categories/visibility")
def set_category_visibility(
    payload: CategoryVisibilityRequest,
    admin: User = Depends(require_master_admin),
    db: Session = Depends(get_db)
):
    """Show or hide one or more categories (and every company in them) for users."""
    categories = seo_engine.get_category_admin_overview(db)
    known = {c["slug"] for c in categories}
    requested = {s.strip().lower() for s in payload.slugs if s and s.strip()}
    unknown = requested - known
    if not requested or unknown:
        raise HTTPException(
            status_code=400,
            detail=("Unknown category: " + ", ".join(sorted(unknown))) if unknown else "No category given.",
        )

    current = seo_engine.get_hidden_category_slugs(db)
    new_hidden = (current | requested) if payload.hidden else (current - requested)
    new_hidden = seo_engine.set_hidden_categories(db, new_hidden)
    _clear_category_dependent_caches()

    for c in categories:
        c["hidden"] = c["slug"] in new_hidden
    data = _category_visibility_payload(categories)

    changed = [c for c in categories if c["slug"] in requested]
    affected = sum(c["count"] for c in changed)
    label = changed[0]["name"] if len(changed) == 1 else f"{len(changed)} categories"
    data["message"] = (
        f"Hidden {label} ({affected:,} companies) from users."
        if payload.hidden else
        f"Showing {label} ({affected:,} companies) to users again."
    )
    return data



if __name__ == "__main__":
    print("\n[OutreachPilot] Running! Open in browser: http://localhost:8000 or http://127.0.0.1:8000\n")
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)

