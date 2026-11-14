import asyncio
import json
import re
import threading
import time
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

_AI_SEMAPHORE = threading.Semaphore(1)

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

try:
    from curl_cffi.requests import AsyncSession as CffiAsyncSession
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

from ai_agent import analyze_company
from clean_db_company_names import clean_company_name
from config import is_safe_public_url
from db import Company, CompanyEmail, CompanyProfile

SUBPAGE_PATTERNS = [
    "/contact", "/contact-us", "/contactus", "/reach-us",
    "/about", "/about-us", "/aboutus", "/team", "/company",
    "/careers", "/career", "/jobs", "/join-us", "/join", "/portfolio",
    "/services", "/our-services", "/projects"
]

EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
    re.IGNORECASE
)

IGNORED_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js",
    ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3", ".pdf", ".zip"
)

IGNORED_DOMAINS = {
    "example.com", "domain.com", "email.com", "sentry.io",
    "wixpress.com", "wordpress.org", "schema.org", "w3.org", "google.com"
}


def clean_email(email_str: str) -> str | None:
    """Validates and sanitizes email strings"""
    email = email_str.strip().lower()
    if any(email.endswith(ext) for ext in IGNORED_EXTENSIONS):
        return None
    if "@" not in email:
        return None
    domain = email.split("@")[-1]
    if domain in IGNORED_DOMAINS or len(domain.split(".")) < 2:
        return None
    return email


RECRUITMENT_PREFIX_KEYWORDS = (
    "hr", "hiring", "recruit", "recruiter", "recruiting", "recruitment",
    "talent", "career", "careers", "job", "jobs", "work", "join", "people"
)


def is_recruitment_email(email_str: str) -> bool:
    """Checks whether an email address is specifically an HR/recruitment/hiring address."""
    if not email_str or "@" not in email_str:
        return False
    prefix = email_str.split("@")[0].lower()
    return any(k in prefix for k in RECRUITMENT_PREFIX_KEYWORDS)


def classify_email(email_str: str) -> str:
    """Classifies email purpose (hr, careers, contact, info, general)"""
    prefix = email_str.split("@")[0].lower()
    if any(k in prefix for k in ["hr", "hiring", "recruit", "talent"]):
        return "hr"
    if any(k in prefix for k in ["career", "job", "work", "join", "people"]):
        return "careers"
    if any(k in prefix for k in ["info", "contact", "hello", "support", "sales"]):
        return "contact"
    return "general"


def filter_and_prioritize_emails(email_set: set[str] | list[str]) -> list[tuple[str, str, bool]]:
    """
    Processes a collection of found emails for a company.

    Rule:
    If ANY email is an HR/recruitment/careers/jobs email (e.g. hr@, recruit@, careers@, jobs@),
    EXCLUDE all other non-recruitment emails (info@, sales@, contact@, support@, etc.)
    and keep ONLY the HR/recruitment emails.

    If NO HR/recruitment email is found, retain all valid emails.

    Returns a list of (email_address, email_type, is_primary) tuples, ordered with the best
    contact email first.
    """
    valid_emails = set()
    for e in email_set:
        c = clean_email(e)
        if c:
            valid_emails.add(c)

    if not valid_emails:
        return []

    hr_emails = [e for e in valid_emails if is_recruitment_email(e)]

    # If ANY HR or recruitment email is found, exclude everything else and keep ONLY HR/recruitment emails
    candidates = hr_emails if hr_emails else list(valid_emails)

    # Ranking hierarchy:
    # 1. Exact hr@, hr.*, hr-*
    # 2. recruit*, recruiter*, recruiting*, recruitment*
    # 3. hiring*, talent*, people*
    # 4. career*, careers*, job*, jobs*, work*, join*
    # 5. contact*, hello*
    # 6. info*, others
    def rank_key(em: str) -> tuple[int, str]:
        prefix = em.split("@")[0].lower()
        if prefix == "hr" or prefix.startswith(("hr.", "hr-", "hr_")):
            return (1, em)
        if any(prefix.startswith(k) for k in ("recruit", "recruiter", "recruiting", "recruitment")):
            return (2, em)
        if any(prefix.startswith(k) for k in ("hiring", "talent", "people")):
            return (3, em)
        if any(prefix.startswith(k) for k in ("career", "job", "work", "join")):
            return (4, em)
        if any(prefix.startswith(k) for k in ("contact", "hello")):
            return (5, em)
        return (6, em)

    sorted_candidates = sorted(candidates, key=rank_key)

    result = []
    for idx, em in enumerate(sorted_candidates):
        result.append((em, classify_email(em), idx == 0))
    return result


def extract_emails_and_text_from_html(html: str, base_url: str) -> dict[str, Any]:
    """
    Extracts candidate emails and high-signal readable text from HTML content.
    Extracts JSON-LD structured schemas, page meta tags, OpenGraph descriptions,
    headings, and visible text to ensure maximum intelligence extraction even from
    SPAs (React/Next.js/Vue) and lazy-loaded websites.
    """
    if not html or not isinstance(html, str):
        return {"emails": [], "clean_text": ""}

    soup = BeautifulSoup(html, "html.parser")
    found_emails: set[str] = set()
    snippets: list[str] = []

    # 1. Search mailto links across entire DOM
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("mailto:"):
            raw_mail = href.split(":", 1)[1].split("?")[0]
            cleaned = clean_email(raw_mail)
            if cleaned:
                found_emails.add(cleaned)

    # 2. Extract JSON-LD structured data (BEFORE decomposing scripts!)
    for script in soup.find_all("script", type=lambda t: t and "ld+json" in t.lower()):
        try:
            raw_json = script.string or script.get_text()
            if raw_json:
                data = json.loads(raw_json.strip())
                items = data if isinstance(data, list) else [data]
                if isinstance(data, dict) and "@graph" in data:
                    items = data["@graph"]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    desc = item.get("description") or item.get("disambiguatingDescription")
                    if desc and isinstance(desc, str):
                        snippets.append(f"Structured Description: {desc.strip()}")
                    srv = item.get("hasOfferCatalog") or item.get("makesOffer") or item.get("knowsAbout")
                    if srv:
                        snippets.append(f"Services: {str(srv)[:300]}")
                    em = item.get("email")
                    if em and isinstance(em, str):
                        c = clean_email(em)
                        if c:
                            found_emails.add(c)
        except Exception:
            pass

    # 3. Extract Head Metadata & OpenGraph
    title_el = soup.find("title")
    if title_el and title_el.get_text(strip=True):
        snippets.append(f"Title: {title_el.get_text(strip=True)}")

    for meta in soup.find_all("meta"):
        prop = (meta.get("property") or meta.get("name") or "").lower()
        content = meta.get("content", "").strip()
        if not content:
            continue
        if prop in ("description", "og:description", "twitter:description"):
            snippets.append(f"Meta Description: {content}")
        elif prop in ("keywords", "og:title"):
            snippets.append(f"Meta {prop}: {content}")

    # 4. Search raw text for emails in common attributes
    for el in soup.find_all(attrs={"data-email": True}):
        c = clean_email(el["data-email"])
        if c:
            found_emails.add(c)

    # 5. Remove non-content tags
    for tag in soup(["script", "style", "svg", "noscript", "iframe"]):
        tag.decompose()

    # 6. Extract visible body text
    body_text = soup.get_text(separator=" ", strip=True)
    for match in EMAIL_REGEX.findall(body_text):
        cleaned = clean_email(match)
        if cleaned:
            found_emails.add(cleaned)

    meta_prefix = " | ".join(snippets)
    full_text = f"{meta_prefix} {body_text}".strip()

    return {
        "emails": list(found_emails),
        "clean_text": full_text[:6000]
    }


async def enrich_company_offline(
    company_meta: dict[str, Any],
    on_step: Any = None
) -> dict[str, Any]:
    """
    Pure offline enrichment pipeline:
    Takes in-memory company_meta dict (id, name, domain, website_url, phone),
    crawls website + subpages using curl_cffi / chrome120, extracts and filters emails,
    cleans company name, scans regex tech & service catalog, and synthesizes AI profile.
    ZERO database connections are opened or required during this call.
    """
    t_start = time.time()
    company_id_val = company_meta.get("id")
    company_name_val = company_meta.get("name", "")
    company_domain_val = (company_meta.get("domain") or "").strip().lower()
    company_website_url_val = company_meta.get("website_url", "")

    # Sanitize company name immediately
    cleaned_name = clean_company_name(company_name_val, company_domain_val) or company_name_val

    # Determine crawl target
    if company_website_url_val and is_safe_public_url(company_website_url_val):
        target_url = company_website_url_val.split("?")[0].rstrip("/")
        base_clean = target_url
    elif company_domain_val:
        base_clean = f"https://{company_domain_val}"
        target_url = base_clean
    else:
        target_url = ""
        base_clean = ""

    all_emails: set[str] = set()
    aggregated_text: list[str] = []

    if on_step:
        on_step(f"Crawling {company_domain_val or cleaned_name}...")

    t_crawl_start = time.time()
    if is_safe_public_url(target_url):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        sub_paths = ["/about-us", "/about", "/services", "/our-services", "/portfolio", "/projects", "/contact-us", "/contact", "/careers"]
        seen_targets = {target_url}
        candidate_urls = [target_url]
        for sub in sub_paths:
            full_sub = f"{base_clean}{sub}"
            if full_sub not in seen_targets and is_safe_public_url(full_sub):
                seen_targets.add(full_sub)
                candidate_urls.append(full_sub)
                if len(candidate_urls) >= 7:
                    break
        urls_to_crawl = [u for u in candidate_urls if is_safe_public_url(u)]

        async def crawl_with_session(session, urls, redirect_kw="follow_redirects"):
            async def fetch_one(url: str):
                # Follow redirects MANUALLY so every hop is re-validated against the
                # SSRF guard. Auto-following (follow_redirects/allow_redirects=True)
                # would let a crawled page 3xx-redirect into localhost, a private
                # subnet, or cloud metadata (169.254.169.254) after the initial check.
                try:
                    current = url
                    for _ in range(4):  # cap redirect chain
                        if not is_safe_public_url(current):
                            return None
                        res = await asyncio.wait_for(
                            session.get(current, timeout=10.0, **{redirect_kw: False}),
                            timeout=12.0,
                        )
                        if res.status_code in (301, 302, 303, 307, 308):
                            loc = res.headers.get("location") or res.headers.get("Location")
                            if not loc:
                                return None
                            current = urljoin(current, loc)
                            continue
                        if res.status_code == 200 and res.text:
                            return extract_emails_and_text_from_html(res.text, current)
                        return None
                except Exception:
                    pass
                return None

            try:
                return await asyncio.wait_for(
                    asyncio.gather(*[fetch_one(u) for u in urls], return_exceptions=True),
                    timeout=18.0
                )
            except Exception:
                return []

        crawl_results = []
        if HAS_CURL_CFFI:
            try:
                async with CffiAsyncSession(impersonate="chrome120", headers=headers, verify=False) as session:
                    crawl_results = await crawl_with_session(session, urls_to_crawl, redirect_kw="allow_redirects")
            except Exception:
                crawl_results = []

        # Fallback to httpx if curl_cffi yielded nothing
        has_any_text = any(isinstance(r, dict) and r.get("clean_text") for r in crawl_results)
        if not has_any_text:
            client_timeout = httpx.Timeout(10.0, connect=5.0, read=8.0, write=5.0, pool=5.0)
            limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
            try:
                # follow_redirects stays False at the client level; crawl_with_session
                # follows redirects manually and re-validates each hop (SSRF guard).
                async with httpx.AsyncClient(headers=headers, timeout=client_timeout, limits=limits, follow_redirects=False, verify=False) as client:
                    crawl_results = await crawl_with_session(client, urls_to_crawl, redirect_kw="follow_redirects")
            except Exception:
                pass

        # Try www. fallback if still empty
        has_any_text = any(isinstance(r, dict) and r.get("clean_text") for r in crawl_results)
        if not has_any_text and company_domain_val and not company_domain_val.startswith("www."):
            www_url = f"https://www.{company_domain_val}"
            if is_safe_public_url(www_url):
                try:
                    if HAS_CURL_CFFI:
                        async with CffiAsyncSession(impersonate="chrome120", headers=headers, verify=False) as session:
                            res = await asyncio.wait_for(session.get(www_url, timeout=8.0, allow_redirects=False), timeout=10.0)
                            if res.status_code == 200 and res.text:
                                crawl_results.append(extract_emails_and_text_from_html(res.text, www_url))
                except Exception:
                    pass

        for r in crawl_results:
            if isinstance(r, dict):
                all_emails.update(r.get("emails", []))
                if r.get("clean_text"):
                    aggregated_text.append(r["clean_text"])

    crawl_elapsed = time.time() - t_crawl_start
    combined_text = " ".join(aggregated_text)
    ranked_emails = filter_and_prioritize_emails(all_emails)
    email_records = [{"email": em, "type": etype, "is_primary": is_prim} for em, etype, is_prim in ranked_emails]

    if on_step:
        on_step(f"Website crawled ({len(combined_text)} chars, {len(email_records)} emails in {crawl_elapsed:.1f}s). Generating AI intelligence dossier...")

    # AI Analysis (serialized via semaphore to prevent CPU/inference thrashing)
    t_ai_start = time.time()
    def _run_ai_serialized():
        with _AI_SEMAPHORE:
            return analyze_company(
                company_name=cleaned_name,
                domain=company_domain_val,
                scraped_text=combined_text
            )

    ai_profile_data = await asyncio.to_thread(_run_ai_serialized)
    ai_elapsed = time.time() - t_ai_start

    has_intel = bool(
        not ai_profile_data.get("skipped") and
        len(combined_text.strip()) >= 60 and (
            (ai_profile_data.get("detailed_analysis") and len(str(ai_profile_data["detailed_analysis"]).strip()) > 50 and "No Readable Website Content Detected" not in str(ai_profile_data["detailed_analysis"])) or
            (ai_profile_data.get("summary") and len(str(ai_profile_data["summary"]).strip()) > 30) or
            (ai_profile_data.get("tech_stack") and len(ai_profile_data["tech_stack"]) > 0)
        )
    )

    status_tag = "COMPLETED" if has_intel else "INCOMPLETE"

    return {
        "success": True,
        "company_id": company_id_val,
        "name": cleaned_name,
        "domain": company_domain_val,
        "status": status_tag,
        "is_enriched": has_intel,
        "emails": email_records,
        "profile": {
            "summary_short": ai_profile_data.get("summary", ""),
            "detailed_analysis": ai_profile_data.get("detailed_analysis", ""),
            "industry": ai_profile_data.get("industry", ""),
            "tech_stack": ai_profile_data.get("tech_stack", []),
            "services": ai_profile_data.get("services", []),
            "hiring_signals": ai_profile_data.get("hiring_signals", ""),
            "tone": ai_profile_data.get("tone", "Professional")
        },
        "crawl_chars": len(combined_text),
        "email_count": len(email_records),
        "crawl_time": round(crawl_elapsed, 2),
        "ai_time": round(ai_elapsed, 2),
        "total_time": round(time.time() - t_start, 2)
    }


async def deep_enrich_company(
    company_id: int,
    db: Session,
    force_refresh: bool = False,
    on_step: Any = None
) -> dict[str, Any]:
    """
    Enriches a company by crawling its website + subpages and extracting
    contact emails and an AI profile. Caches results permanently in PostgreSQL.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return {"error": "Company not found", "success": False}

    # 1. Check if already enriched in DB (Smart Caching)
    if company.is_enriched and not force_refresh:
        existing_profile = db.query(CompanyProfile).filter(CompanyProfile.company_id == company.id).first()
        existing_emails = db.query(CompanyEmail).filter(CompanyEmail.company_id == company.id).all()
        return {
            "success": True,
            "cached": True,
            "company_id": company.id,
            "company_name": company.name,
            "domain": company.domain,
            "emails": [{"email": e.email_address, "type": e.email_type, "is_primary": e.is_primary} for e in existing_emails],
            "profile": {
                "summary": existing_profile.summary_short if existing_profile else "",
                "detailed_analysis": existing_profile.detailed_analysis if existing_profile else "",
                "industry": existing_profile.industry if existing_profile else "",
                "tech_stack": existing_profile.tech_stack if existing_profile else [],
                "services": existing_profile.services if existing_profile else [],
                "tone": existing_profile.tone if existing_profile else "Professional"
            } if existing_profile else {}
        }

    company_meta = {
        "id": company.id,
        "name": company.name,
        "domain": company.domain,
        "website_url": company.website_url,
        "phone": company.phone
    }

    # Release connection before network crawl & AI
    try:
        db.rollback()
    except Exception:
        pass

    # Run pure offline crawl & AI analysis
    res = await enrich_company_offline(company_meta, on_step=on_step)

    # Save to PostgreSQL
    if on_step:
        on_step("AI analysis complete. Saving intelligence and emails to Neon DB...")

    from db import SessionLocal
    save_db = db
    for attempt in range(1, 4):
        try:
            target_company = save_db.query(Company).filter(Company.id == company.id).first()
            if not target_company:
                return {"error": "Company not found", "success": False}

            if res.get("name"):
                target_company.name = res["name"]

            if force_refresh:
                save_db.query(CompanyEmail).filter(CompanyEmail.company_id == company.id).delete()
                save_db.query(CompanyProfile).filter(CompanyProfile.company_id == company.id).delete()

            for em in res.get("emails", []):
                save_db.add(CompanyEmail(
                    company_id=company.id,
                    email_address=em["email"],
                    email_type=em.get("type", "general"),
                    is_primary=em.get("is_primary", False)
                ))

            p_data = res.get("profile", {})
            if res.get("is_enriched") and (p_data.get("summary_short") or p_data.get("detailed_analysis")):
                save_db.add(CompanyProfile(
                    company_id=company.id,
                    summary_short=p_data.get("summary_short", ""),
                    detailed_analysis=p_data.get("detailed_analysis", ""),
                    industry=p_data.get("industry", ""),
                    tech_stack=p_data.get("tech_stack", []),
                    services=p_data.get("services", []),
                    hiring_signals=p_data.get("hiring_signals", ""),
                    tone=p_data.get("tone", "Professional")
                ))

            target_company.is_enriched = res.get("is_enriched", False)
            target_company.enrichment_status = res.get("status", "INCOMPLETE")
            target_company.last_enriched_at = datetime.utcnow()
            save_db.commit()
            break
        except Exception as save_err:
            try:
                save_db.rollback()
            except Exception:
                pass
            if attempt == 3:
                raise save_err
            try:
                save_db.close()
            except Exception:
                pass
            save_db = SessionLocal()
            await asyncio.sleep(0.5)

    return res
