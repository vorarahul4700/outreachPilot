import asyncio
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from ai_agent import analyze_company
from config import is_safe_public_url
from db import Company, CompanyEmail, CompanyProfile

SUBPAGE_PATTERNS = [
    "/contact", "/contact-us", "/contactus", "/reach-us",
    "/about", "/about-us", "/aboutus", "/team", "/company",
    "/careers", "/career", "/jobs", "/join-us", "/join"
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
    """Extracts candidate emails and clean readable text from HTML content"""
    soup = BeautifulSoup(html, "html.parser")

    # Remove script, style, and svg tags
    for tag in soup(["script", "style", "svg", "noscript", "iframe"]):
        tag.decompose()

    found_emails: set[str] = set()

    # 1. Search in mailto links
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("mailto:"):
            raw_mail = href.split(":", 1)[1].split("?")[0]
            cleaned = clean_email(raw_mail)
            if cleaned:
                found_emails.add(cleaned)

    # 2. Search raw text with Regex
    text = soup.get_text(separator=" ", strip=True)
    for match in EMAIL_REGEX.findall(text):
        cleaned = clean_email(match)
        if cleaned:
            found_emails.add(cleaned)

    return {
        "emails": list(found_emails),
        "clean_text": text[:5000]
    }


async def deep_enrich_company(
    company_id: int,
    db: Session,
    force_refresh: bool = False
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

    # 2. Parallel Crawl Company Website (Homepage + Subpages simultaneously)
    base_clean = f"https://{company.domain}" if company.domain else (company.website_url.split("?")[0].rstrip("/") if company.website_url else "")
    target_url = base_clean or company.website_url

    all_emails: set[str] = set()
    aggregated_text: list[str] = []

    # SSRF Protection: strictly verify target_url is a legitimate public destination
    if is_safe_public_url(target_url):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

        candidate_urls = [target_url] + [f"{base_clean}{sub}" for sub in ["/contact", "/about", "/careers"]]
        urls_to_crawl = [u for u in candidate_urls if is_safe_public_url(u)]

        client_timeout = httpx.Timeout(connect=2.5, read=3.5, write=2.5, pool=2.5)
        async with httpx.AsyncClient(headers=headers, timeout=client_timeout, follow_redirects=True, verify=True) as client:
            async def fetch_page(url: str):
                try:
                    res = await client.get(url)
                    if res.status_code == 200:
                        return extract_emails_and_text_from_html(res.text, url)
                except Exception:
                    pass
                return None

            crawl_results = await asyncio.gather(*[fetch_page(u) for u in urls_to_crawl], return_exceptions=True)
            for r in crawl_results:
                if isinstance(r, dict):
                    all_emails.update(r.get("emails", []))
                    if r.get("clean_text"):
                        aggregated_text.append(r["clean_text"])

    combined_text = " ".join(aggregated_text)

    # 3. Analyze with AI Agent (executed in threadpool to prevent blocking async loop)
    ai_profile_data = await asyncio.to_thread(
        analyze_company,
        company_name=company.name,
        domain=company.domain,
        scraped_text=combined_text
    )

    # 4. Save to PostgreSQL Database
    if force_refresh:
        db.query(CompanyEmail).filter(CompanyEmail.company_id == company.id).delete()
        db.query(CompanyProfile).filter(CompanyProfile.company_id == company.id).delete()

    ranked_emails = filter_and_prioritize_emails(all_emails)
    email_records = []
    for em, etype, is_prim in ranked_emails:
        c_email = CompanyEmail(
            company_id=company.id,
            email_address=em,
            email_type=etype,
            is_primary=is_prim
        )
        db.add(c_email)
        email_records.append({"email": em, "type": etype, "is_primary": is_prim})

    c_profile = CompanyProfile(
        company_id=company.id,
        summary_short=ai_profile_data.get("summary", ""),
        detailed_analysis=ai_profile_data.get("detailed_analysis", ""),
        industry=ai_profile_data.get("industry", ""),
        tech_stack=ai_profile_data.get("tech_stack", []),
        services=ai_profile_data.get("services", []),
        hiring_signals=ai_profile_data.get("hiring_signals", ""),
        tone=ai_profile_data.get("tone", "Professional")
    )
    db.add(c_profile)

    company.is_enriched = True
    db.commit()

    return {
        "success": True,
        "cached": False,
        "company_id": company.id,
        "company_name": company.name,
        "domain": company.domain,
        "emails": email_records,
        "profile": ai_profile_data
    }
