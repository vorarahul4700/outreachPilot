"""
OutreachPilot - Comprehensive SEO, AEO & GEO Engine
File: seo_engine.py

Provides:
1. GEO: /robots.txt (AI-bot unblocked), /llms.txt, /llms-full.txt (llmstxt.org standard).
2. Sitemaps: /sitemap.xml (Index), /sitemap-core.xml, /sitemap-cities.xml,
             /sitemap-tech.xml, /sitemap-directory.xml, /sitemap-companies-{page}.xml.
3. pSEO: Programmatic directory data pipelines for 73 cities, 36 tech stacks, 2,600+ intersections.
4. AEO: Schema.org JSON-LD (BreadcrumbList, ItemList, FAQPage, LocalBusiness, Organization).
5. Fast in-memory TTL caching for instant (<5ms) subpage response times.
"""

import html
import math
import os
import re
import time
from collections import defaultdict
from typing import Any, Optional
from urllib.parse import quote, urlparse
from fastapi import Request
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session, joinedload

import config
from db import Company, CompanyEmail, CompanyProfile

# In-memory cache store with 1-hour default TTL
_SEO_CACHE: dict[str, dict[str, Any]] = {}
CACHE_TTL = 3600  # 1 hour


def get_cached(key: str) -> Any | None:
    entry = _SEO_CACHE.get(key)
    if entry and (time.time() - entry["ts"] < CACHE_TTL):
        return entry["val"]
    return None


def set_cached(key: str, val: Any):
    _SEO_CACHE[key] = {"val": val, "ts": time.time()}


def clear_seo_cache():
    global _SEO_CACHE
    _SEO_CACHE = {}


# --- Base URL & Canonical Resolution ---

def get_canonical_base_url(request: Request = None) -> str:
    """
    Dynamically determines the canonical public origin.
    Prefers APP_BASE_URL env variable (e.g. https://outreachpilot.com).
    Falls back to Cloudflare/Reverse-Proxy headers, then request.base_url.
    """
    configured = os.getenv("APP_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured

    if request:
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
        return f"{proto}://{host}".rstrip("/")

    return "https://outreachpilot.com"


# --- Dynamic Taxonomy, Categorization & Slugging Engine ---

# Acronyms that should remain fully capitalized in display titles across all industries
KNOWN_UPPERCASE_ACRONYMS = {
    "AI", "ML", "IT", "CA", "HR", "SEO", "B2B", "B2C", "SaaS", "LLM",
    "PHP", "AWS", "iOS", "API", "SQL", "ERP", "CRM", "QA", "UI", "UX",
    "MERN", "MEAN", "CMS", "DNS", "RPA", "PaaS", "IaaS", "PPC", "SMM"
}

# Curated symbol mappings for technical terms with punctuation
CURATED_ACRONYM_MAP = {
    "cpp": "C++",
    "csharp": "C#",
    "dotnet": ".NET",
    "nodejs": "Node.js",
    "node-js": "Node.js",
    "nextjs": "Next.js",
    "next-js": "Next.js",
    "vuejs": "Vue.js",
    "vue-js": "Vue.js",
    "uiux": "UI/UX",
    "ui-ux": "UI/UX",
    "ai-ml": "AI & Machine Learning",
    "golang": "Go"
}

# Seed overrides for established keywords to preserve clean formatting.
# Any keyword from any industry not in this map is dynamically parsed and normalized in real time.
SEED_KEYWORD_OVERRIDES = {
    "Python Development Companies": "Python",
    "React JS Development Companies": "React",
    "Node.js Development Companies": "Node.js",
    "Django Development Company": "Django",
    "FastAPI Python Developers": "FastAPI",
    "Flutter App Development Companies": "Flutter",
    "Next.js Web Development": "Next.js",
    "Vue.js Development Companies": "Vue.js",
    "Angular Development Companies": "Angular",
    "Java Software Development Companies": "Java",
    "Spring Boot Development Companies": "Spring Boot",
    "PHP Laravel Development Companies": "Laravel & PHP",
    "WordPress Development Agencies": "WordPress",
    "Shopify Development Agencies": "Shopify",
    "Golang Software Companies": "Go",
    "Ruby on Rails Development Companies": "Ruby on Rails",
    "iOS App Development Companies": "iOS",
    "Android App Development Companies": "Android",
    "React Native App Development": "React Native",
    "DotNet C# Software Companies": ".NET & C#",
    "DevOps Cloud Consulting Companies": "DevOps",
    "AWS Cloud Consulting Partners": "AWS Cloud",
    "AI Machine Learning Companies": "AI & Machine Learning",
    "Generative AI Development Companies": "Generative AI",
    "LLM Development & AI Solutions": "LLM & AI Solutions",
    "Data Science & Analytics Companies": "Data Science",
    "MERN Stack Development Companies": "MERN Stack",
    "MEAN Stack Development Companies": "MEAN Stack",
    "NestJS Development Companies": "NestJS",
    "Blockchain Development Companies": "Blockchain",
    "Custom Software Development Companies": "Custom Software",
    "Full Stack Software Companies": "Full Stack",
    "Web Development Agencies": "Web Development",
    "Frontend Web Development Agencies": "Frontend Development",
    "Mobile App Development Companies": "Mobile Apps",
    "SaaS Product Development Companies": "SaaS Engineering"
}

# Dynamic backwards-compatibility alias for legacy code
SEARCH_KEYWORD_CANONICAL = SEED_KEYWORD_OVERRIDES
SLUG_TECH_MAP = CURATED_ACRONYM_MAP


def normalize_keyword_to_category(raw_keyword: str) -> str:
    """
    Dynamically normalizes ANY search query, keyword, or industry label from any field
    (e.g. IT, Healthcare, Real Estate, Legal, Finance, Hospitality, Manufacturing)
    into a clean, publication-ready canonical category name.
    """
    if not raw_keyword:
        return "General Business"

    raw = raw_keyword.strip()

    # 1. Check curated seed overrides first
    if raw in SEED_KEYWORD_OVERRIDES:
        return SEED_KEYWORD_OVERRIDES[raw]

    # 2. Strip trailing location qualifiers (e.g. " in Surat", " in Mumbai", " near me", " nearby")
    cleaned = re.sub(r"\s+(?:in|near|around|at)\s+[A-Za-z\s]+$", "", raw, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s+near\s+me$", "", cleaned, flags=re.IGNORECASE).strip()

    # 3. Strip common corporate filler suffixes if preceded by substantive category words
    boilerplate_patterns = [
        r"\s+Development\s+Companies",
        r"\s+Development\s+Company",
        r"\s+Software\s+Companies",
        r"\s+Software\s+Company",
        r"\s+Development\s+Agencies",
        r"\s+Development\s+Agency",
        r"\s+Consulting\s+Companies",
        r"\s+Consulting\s+Agencies",
        r"\s+Consulting\s+Partners",
        r"\s+Web\s+Development\s+Agencies",
        r"\s+App\s+Development",
        r"\s+Services\s+Companies",
        r"\s+Agencies",
        r"\s+Agency",
        r"\s+Companies",
        r"\s+Company",
        r"\s+Firms",
        r"\s+Firm",
    ]
    for pattern in boilerplate_patterns:
        sub = re.sub(pattern + "$", "", cleaned, flags=re.IGNORECASE).strip()
        if sub != cleaned and len(sub) >= 2:
            cleaned = sub
            break

    # 4. Acronym-aware title casing
    words = cleaned.split()
    formatted_words = []
    for w in words:
        clean_w = re.sub(r"[^\w]", "", w).upper()
        if clean_w in KNOWN_UPPERCASE_ACRONYMS:
            if clean_w == "IOS":
                formatted_words.append("iOS")
            else:
                formatted_words.append(clean_w)
        else:
            formatted_words.append(w.capitalize())

    return " ".join(formatted_words) or raw.title()


def slugify(text_val: str) -> str:
    """Converts raw text into an SEO-friendly URL slug."""
    if not text_val:
        return ""
    s = text_val.strip().lower()
    s = (
        s.replace(".net", "dotnet")
        .replace("c++", "cpp")
        .replace("c#", "csharp")
        .replace("&", "and")
    )
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    return s.strip("-")


def city_to_slug(city: str) -> str:
    if not city:
        return ""
    return slugify(city)


def slug_to_city_name(slug: str) -> str:
    if not slug:
        return ""
    raw = slug.replace("-", " ")
    return raw.title()


def tech_to_slug(tech_or_category: str) -> str:
    """
    Dynamically converts any category, technology, or industry name into an SEO-friendly slug.
    Works universally across IT, Healthcare, Real Estate, Finance, Legal, etc.
    """
    if not tech_or_category:
        return ""
    clean = tech_or_category.strip().lower()

    # Symbol-sensitive conversions
    clean = (
        clean.replace(".net", "dotnet")
        .replace("c++", "cpp")
        .replace("c#", "csharp")
        .replace("ui/ux", "uiux")
        .replace("ui-ux", "uiux")
        .replace("ai / machine learning", "ai-ml")
        .replace("ai & machine learning", "ai-ml")
        .replace("node.js", "nodejs")
        .replace("next.js", "nextjs")
        .replace("vue.js", "vuejs")
    )
    return slugify(clean)

category_to_slug = tech_to_slug


def slug_to_tech_name(slug: str) -> str:
    """
    Dynamically resolves a URL slug to its canonical category/tech display name.
    1. Checks dynamic database taxonomy cache.
    2. Checks known curated acronyms and symbols (.NET, C++, C#, Node.js, Next.js, UI/UX, AI/ML).
    3. Dynamically formats slug into clean Title Case with uppercase acronym handling.
    """
    if not slug:
        return ""
    clean_slug = slug.strip().lower()

    # 1. Check in-memory cached dynamic taxonomy
    slug_map = get_cached("slug_category_map")
    if slug_map and clean_slug in slug_map:
        return slug_map[clean_slug]

    # 2. Curated Acronym & Tech Overrides
    if clean_slug in CURATED_ACRONYM_MAP:
        return CURATED_ACRONYM_MAP[clean_slug]

    # 3. Dynamic Title Case with Acronym Preserving
    words = clean_slug.replace("-", " ").replace("_", " ").split()
    capitalized_words = []
    for w in words:
        upper_w = w.upper()
        if upper_w in KNOWN_UPPERCASE_ACRONYMS:
            if upper_w == "IOS":
                capitalized_words.append("iOS")
            else:
                capitalized_words.append(upper_w)
        else:
            capitalized_words.append(w.capitalize())
    return " ".join(capitalized_words)

slug_to_category_name = slug_to_tech_name


def company_to_slug(company_name: str, domain: str, company_id: int) -> str:
    """Builds a human-readable, unique URL slug for a company."""
    clean_name = slugify(company_name) if company_name else slugify(domain.split(".")[0])
    return f"{clean_name}-{company_id}"


def parse_company_slug(slug: str) -> int | None:
    """Extracts the integer company ID from a slug like 'easyskill-career-academy-16247'."""
    if not slug:
        return None
    match = re.search(r"-(\d+)$", slug.strip())
    if match:
        return int(match.group(1))
    if slug.isdigit():
        return int(slug)
    return None


# --- High-Performance Aggregation Queries (Cached) ---

def get_directory_stats(db: Session) -> dict[str, Any]:
    cached = get_cached("stats")
    if cached:
        return cached

    row = db.execute(text("""
        SELECT 
            COUNT(*) FILTER (WHERE is_invalid = FALSE) AS total_companies,
            COUNT(*) FILTER (WHERE is_invalid = FALSE AND is_enriched = TRUE) AS enriched_companies,
            COUNT(DISTINCT NULLIF(trim(lower(city)), '')) FILTER (WHERE is_invalid = FALSE) AS total_cities,
            COUNT(DISTINCT NULLIF(trim(lower(search_keyword)), '')) FILTER (WHERE is_invalid = FALSE) AS total_techs,
            ROUND((AVG(rating) FILTER (WHERE is_invalid = FALSE AND rating > 0))::numeric, 1) AS avg_rating
        FROM companies;
    """)).fetchone()

    total_comps = row[0] if row else 33603
    enriched = row[1] if row else 2110
    total_cities = row[2] if row else 73
    total_techs = row[3] if row else 36
    avg_rating = float(row[4] or 4.3)

    stats = {
        "total_companies": total_comps,
        "enriched_companies": enriched,
        "total_cities": total_cities,
        "total_techs": total_techs,
        "avg_rating": avg_rating
    }
    set_cached("stats", stats)
    return stats


def get_all_cities(db: Session) -> list[dict[str, Any]]:
    cached = get_cached("all_cities")
    if cached:
        return cached

    rows = db.execute(text("""
        SELECT 
            initcap(trim(city)) AS norm_city,
            COUNT(*) AS count,
            ROUND(AVG(rating)::numeric, 1) AS avg_rating
        FROM companies
        WHERE is_invalid = FALSE 
          AND city IS NOT NULL 
          AND trim(city) != ''
        GROUP BY initcap(trim(city))
        HAVING COUNT(*) >= 2
        ORDER BY count DESC, norm_city ASC;
    """)).fetchall()

    results = []
    for r in rows:
        name = r[0]
        results.append({
            "name": name,
            "slug": city_to_slug(name),
            "count": r[1],
            "avg_rating": float(r[2] or 4.2)
        })

    set_cached("all_cities", results)
    return results


def get_all_categories(db: Session) -> list[dict[str, Any]]:
    """
    Dynamically retrieves and aggregates ALL industry categories, tech stacks, and services
    present across the entire company database.
    Works for ANY industry (IT, Healthcare, Real Estate, Finance, Manufacturing, etc.).
    """
    cached = get_cached("all_techs")
    if cached:
        return cached

    rows = db.execute(text("""
        SELECT 
            COALESCE(NULLIF(trim(normalized_keyword), ''), trim(search_keyword)) AS raw_kw,
            COUNT(*) AS count,
            ROUND((AVG(rating) FILTER (WHERE is_invalid = FALSE AND rating > 0))::numeric, 1) AS avg_rating
        FROM companies
        WHERE is_invalid = FALSE 
          AND (
              (search_keyword IS NOT NULL AND trim(search_keyword) != '')
              OR (normalized_keyword IS NOT NULL AND trim(normalized_keyword) != '')
          )
        GROUP BY COALESCE(NULLIF(trim(normalized_keyword), ''), trim(search_keyword))
        HAVING COUNT(*) >= 1
        ORDER BY count DESC;
    """)).fetchall()

    results = []
    seen_slugs = set()
    slug_category_map = {}
    category_slug_map = {}
    category_raw_keywords_map = defaultdict(set)

    for r in rows:
        raw_kw = (r[0] or "").strip()
        if not raw_kw:
            continue
        display_name = normalize_keyword_to_category(raw_kw)
        slug = tech_to_slug(display_name)
        category_raw_keywords_map[slug].add(raw_kw)

        if slug in seen_slugs:
            for existing in results:
                if existing["slug"] == slug:
                    existing["count"] += r[1]
                    break
            continue

        seen_slugs.add(slug)
        results.append({
            "name": display_name,
            "raw_keyword": raw_kw,
            "slug": slug,
            "count": r[1],
            "avg_rating": float(r[2] or 4.3)
        })
        slug_category_map[slug] = display_name
        category_slug_map[display_name.lower()] = slug

    results.sort(key=lambda x: x["count"], reverse=True)

    set_cached("all_techs", results)
    set_cached("slug_category_map", slug_category_map)
    set_cached("category_slug_map", category_slug_map)
    set_cached("category_raw_keywords_map", {k: list(v) for k, v in category_raw_keywords_map.items()})
    return results

get_all_technologies = get_all_categories


def get_all_combinations(db: Session) -> list[dict[str, Any]]:
    """
    Dynamically aggregates all city + category/technology combinations across the entire database.
    """
    cached = get_cached("all_combinations")
    if cached:
        return cached

    rows = db.execute(text("""
        SELECT 
            initcap(trim(city)) AS city_name,
            COALESCE(NULLIF(trim(normalized_keyword), ''), trim(search_keyword)) AS raw_kw,
            COUNT(*) AS count,
            ROUND((AVG(rating) FILTER (WHERE is_invalid = FALSE AND rating > 0))::numeric, 1) AS avg_rating
        FROM companies
        WHERE is_invalid = FALSE 
          AND city IS NOT NULL AND trim(city) != ''
          AND (
              (search_keyword IS NOT NULL AND trim(search_keyword) != '')
              OR (normalized_keyword IS NOT NULL AND trim(normalized_keyword) != '')
          )
        GROUP BY initcap(trim(city)), COALESCE(NULLIF(trim(normalized_keyword), ''), trim(search_keyword))
        HAVING COUNT(*) >= 1
        ORDER BY count DESC;
    """)).fetchall()

    combos = []
    seen = {}
    for r in rows:
        c_name = r[0]
        raw_kw = (r[1] or "").strip()
        disp_cat = normalize_keyword_to_category(raw_kw)
        c_slug = city_to_slug(c_name)
        t_slug = tech_to_slug(disp_cat)
        combo_key = f"{c_slug}:{t_slug}"
        if combo_key in seen:
            seen[combo_key]["count"] += r[2]
            continue
        entry = {
            "city_name": c_name,
            "city_slug": c_slug,
            "tech_name": disp_cat,
            "tech_slug": t_slug,
            "count": r[2],
            "avg_rating": float(r[3] or 4.2)
        }
        seen[combo_key] = entry
        combos.append(entry)

    set_cached("all_combinations", combos)
    return combos


# --- Data Retrieval for Directory Pages ---

def get_companies_list(
    db: Session,
    city: str = None,
    tech: str = None,
    page: int = 1,
    limit: int = 24
) -> tuple[list[dict[str, Any]], int]:
    """Retrieves paginated company records for city/tech directory pages."""
    offset = max(0, (page - 1) * limit)

    query = (
        db.query(Company)
        .options(joinedload(Company.profile), joinedload(Company.emails))
        .filter(Company.is_invalid.is_(False))
    )

    if city:
        query = query.filter(func.lower(Company.city) == city.strip().lower())

    if tech:
        clean_tech = tech.strip()
        tech_slug = tech_to_slug(clean_tech)
        canonical_name = slug_to_tech_name(tech_slug)

        # Dynamic keyword matching: retrieve dynamic raw keywords mapped to this category
        raw_kw_map = get_cached("category_raw_keywords_map") or {}
        matching_keywords = list(raw_kw_map.get(tech_slug, []))
        if not matching_keywords:
            matching_keywords = [clean_tech, canonical_name]

        query = query.filter(
            or_(
                Company.search_keyword.in_(matching_keywords),
                func.lower(Company.search_keyword).ilike(f"%{clean_tech.lower()}%"),
                func.lower(Company.normalized_keyword).ilike(f"%{clean_tech.lower()}%"),
                func.lower(Company.search_keyword).ilike(f"%{canonical_name.lower()}%"),
                func.lower(Company.normalized_keyword) == tech_slug
            )
        )

    total_count = query.count()

    # Prioritize enriched companies with ratings and reviews first
    companies = (
        query.order_by(
            Company.is_enriched.desc(),
            Company.rating.desc().nullslast(),
            Company.reviews_count.desc().nullslast(),
            Company.name.asc()
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    serialized = []
    for c in companies:
        profile_data = {}
        if c.profile:
            profile_data = {
                "summary": c.profile.summary_short or "",
                "tech_stack": c.profile.tech_stack or [],
                "services": c.profile.services or [],
                "industry": c.profile.industry or "Information Technology & Software",
                "hiring_signals": c.profile.hiring_signals or "Standard engineering growth"
            }

        has_emails = bool(c.emails and len(c.emails) > 0)
        primary_email_type = c.emails[0].email_type if has_emails else None

        slug = company_to_slug(c.name, c.domain, c.id)

        stack_badges = profile_data.get("tech_stack", [])
        if not stack_badges and c.search_keyword:
            canon_name = normalize_keyword_to_category(c.search_keyword)
            stack_badges = [canon_name]

        serialized.append({
            "id": c.id,
            "name": c.name,
            "domain": c.domain,
            "website_url": c.website_url or f"https://{c.domain}",
            "city": c.city or "India",
            "rating": float(c.rating or 4.2),
            "reviews_count": int(c.reviews_count or 0),
            "is_enriched": c.is_enriched,
            "has_emails": has_emails,
            "email_type": primary_email_type,
            "slug": slug,
            "profile": profile_data,
            "tech_stack": stack_badges[:5],
            "services": (profile_data.get("services") or [])[:3]
        })

    return serialized, total_count


def render_dossier_markdown(md_text: str) -> str:
    """
    Renders structured technical dossier markdown into semantic, high-contrast HTML.
    Converts ### headings, **bold** labels, bullet lists, and key-value pairs into
    tactile bento cards.
    """
    if not md_text or not md_text.strip():
        return ""

    lines = md_text.strip().splitlines()
    html_parts = []
    in_section = False
    in_tag_cloud = False

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        # Section Headings (e.g. ### 1. Company Overview & Identity)
        if line.startswith("###"):
            if in_tag_cloud:
                html_parts.append('</div>')
                in_tag_cloud = False
            if in_section:
                html_parts.append('</div></div>')
            heading_text = html.escape(line.lstrip("#").strip())
            html_parts.append(
                f'<div class="dossier-card bg-surface-container-low border border-outline rounded-xl p-4 sm:p-5 mb-4 shadow-sm">'
                f'<div class="flex items-center gap-2 mb-3 pb-2 border-b border-outline/50">'
                f'<span class="w-2 h-2 rounded-full bg-secondary shrink-0"></span>'
                f'<h3 class="text-xs sm:text-sm font-display font-bold text-primary">{heading_text}</h3>'
                f'</div>'
                f'<div class="space-y-2 text-xs font-sans leading-relaxed">'
            )
            in_section = True
            continue

        # Key-Value lines (e.g. - **Official Name:** Perfomance Marketing or - **Website:** ...)
        if line.startswith("-") and "**" in line:
            content = line.lstrip("-").strip()
            # Match - **Key:** Value
            match = re.match(r'^\*\*([^*]+)\*\*:?\s*(.*)$', content)
            if match:
                key, val = match.group(1).rstrip(":"), match.group(2)
                esc_key = html.escape(key)
                if not val:
                    # Tag badge without value (e.g. - **Mobile App Development**)
                    if not in_tag_cloud:
                        html_parts.append('<div class="flex flex-wrap gap-2 pt-1 pb-1">')
                        in_tag_cloud = True
                    html_parts.append(
                        f'<span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono font-medium bg-surface-container-high text-primary border border-outline">'
                        f'<span class="material-symbols-outlined text-[13px] text-secondary">check_circle</span>'
                        f'{esc_key}'
                        f'</span>'
                    )
                else:
                    if in_tag_cloud:
                        html_parts.append('</div>')
                        in_tag_cloud = False
                    esc_val = re.sub(r'\*\*([^*]+)\*\*', r'<strong class="text-primary font-semibold">\1</strong>', html.escape(val))
                    html_parts.append(
                        f'<div class="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-2 py-1.5 border-b border-outline/25 last:border-0">'
                        f'<span class="font-mono text-[11px] uppercase tracking-wider text-secondary font-semibold shrink-0 min-w-[140px]">{esc_key}:</span>'
                        f'<span class="text-on-surface-variant font-sans text-xs">{esc_val}</span>'
                        f'</div>'
                    )
                continue

        # Standard bullet items (- Enterprise Software, FinTech...)
        if line.startswith("-"):
            if in_tag_cloud:
                html_parts.append('</div>')
                in_tag_cloud = False
            item_text = html.escape(line.lstrip("-").strip())
            item_text = re.sub(r'\*\*([^*]+)\*\*', r'<strong class="text-primary font-semibold">\1</strong>', item_text)
            html_parts.append(
                f'<div class="flex items-start gap-2 py-1 text-on-surface-variant">'
                f'<span class="text-secondary font-mono mt-0.5">•</span>'
                f'<span>{item_text}</span>'
                f'</div>'
            )
            continue

        # Fallback paragraph
        if in_tag_cloud:
            html_parts.append('</div>')
            in_tag_cloud = False
        para_text = html.escape(line)
        para_text = re.sub(r'\*\*([^*]+)\*\*', r'<strong class="text-primary font-semibold">\1</strong>', para_text)
        html_parts.append(f'<p class="text-on-surface-variant leading-relaxed py-1">{para_text}</p>')

    if in_tag_cloud:
        html_parts.append('</div>')
    if in_section:
        html_parts.append('</div></div>')

    return "\n".join(html_parts)


def get_company_details(db: Session, company_id: int) -> dict[str, Any] | None:
    """Retrieves full company dossier for the public profile page."""
    c = (
        db.query(Company)
        .options(joinedload(Company.profile), joinedload(Company.emails))
        .filter(Company.id == company_id, Company.is_invalid.is_(False))
        .first()
    )
    if not c:
        return None

    detailed_raw = c.profile.detailed_analysis if (c.profile and c.profile.detailed_analysis) else None
    detailed_html = render_dossier_markdown(detailed_raw) if detailed_raw else None

    profile_data = {
        "summary": "Verified technology company providing custom software, web application development, and engineering consulting services.",
        "detailed_analysis": detailed_raw,
        "detailed_analysis_html": detailed_html,
        "industry": "Custom Software & Information Technology",
        "tech_stack": [],
        "services": ["Web Application Development", "Custom Software Engineering"],
        "hiring_signals": "Active engineering and technology operations",
        "tone": "Professional"
    }

    if c.profile:
        profile_data = {
            "summary": c.profile.summary_short or profile_data["summary"],
            "detailed_analysis": detailed_raw,
            "detailed_analysis_html": detailed_html,
            "industry": c.profile.industry or profile_data["industry"],
            "tech_stack": c.profile.tech_stack or [],
            "services": c.profile.services or profile_data["services"],
            "hiring_signals": c.profile.hiring_signals or profile_data["hiring_signals"],
            "tone": c.profile.tone or "Professional"
        }

    # Ensure at least primary normalized_keyword is in tech stack
    if c.normalized_keyword and c.normalized_keyword not in profile_data["tech_stack"]:
        profile_data["tech_stack"].insert(0, c.normalized_keyword)

    slug = company_to_slug(c.name, c.domain, c.id)

    return {
        "id": c.id,
        "name": c.name,
        "domain": c.domain,
        "website_url": c.website_url or f"https://{c.domain}",
        "phone": c.phone or None,
        "address": c.address or None,
        "location_url": c.location_url or None,
        "city": c.city or "India",
        "rating": float(c.rating or 4.2),
        "reviews_count": int(c.reviews_count or 0),
        "is_enriched": c.is_enriched,
        "has_emails": bool(c.emails and len(c.emails) > 0),
        "emails_count": len(c.emails) if c.emails else 0,
        "slug": slug,
        "profile": profile_data
    }


# --- GEO Generation: /robots.txt, /llms.txt, /llms-full.txt ---

def generate_robots_txt(base_url: str) -> str:
    """
    Generates an AI-friendly, SEO-optimized robots.txt.
    Explicitly welcomes major AI search engines and search crawlers,
    while safeguarding sensitive internal application/auth routes.
    """
    return f"""# OutreachPilot Autonomous B2B Directory & Lead Intelligence
# Optimized for Web Search, Generative Search Engines (GEO) & Answer Engines (AEO)

User-agent: *
Allow: /
Allow: /directory
Allow: /directory/
Allow: /company/
Allow: /llms.txt
Allow: /llms-full.txt
Allow: /sitemap.xml
Disallow: /api/
Disallow: /auth/
Disallow: /app
Disallow: /workspace
Disallow: /settings

# Generative AI Answer Engines & Search Bots (Full Indexing Allowed)
User-agent: GPTBot
Allow: /

User-agent: OAI-SearchBot
Allow: /

User-agent: ChatGPT-User
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: anthropic-ai
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: Applebot-Extended
Allow: /

User-agent: Bytespider
Allow: /

# Canonical XML Sitemap
Sitemap: {base_url}/sitemap.xml
"""


def generate_llms_txt(base_url: str, db: Session) -> str:
    """
    Generates /llms.txt formatted per the official llmstxt.org specification.
    Gives LLMs (ChatGPT, Claude, Perplexity) a clean markdown summary of OutreachPilot.
    """
    stats = get_directory_stats(db)
    cities = get_all_cities(db)[:15]
    techs = get_all_technologies(db)[:15]

    cities_md = "\n".join([f"- [{c['name']} Directory]({base_url}/directory/city/{c['slug']}): {c['count']} verified IT companies" for c in cities])
    techs_md = "\n".join([f"- [{t['name']} Development]({base_url}/directory/tech/{t['slug']}): {t['count']} verified companies" for t in techs])

    return f"""# OutreachPilot

> Autonomous B2B Sales & Candidate Intelligence platform indexing {stats['total_companies']:,}+ verified technology companies, agencies, and software firms across {stats['total_cities']} Indian tech hubs.

## Overview
OutreachPilot discovers, crawls, and structures intelligence on technology firms across India. Each profile includes verified web engineering stacks, detected business services, Google Local customer review sentiment, and recruiter contact availability.

## Verified Directory Hubs
- [Complete B2B Technology Directory]({base_url}/directory): Browse all verified software companies, technology hubs, and framework indexes.
- [Outreach Platform & Scout Engine]({base_url}/app): Autonomous prospecting, multi-pass tech crawler, and personalized pitch dispatch.

## Top City Hubs
{cities_md}

## Top Technology Frameworks
{techs_md}

## Programmatic Directory Hierarchy
- City Index: `{base_url}/directory/city/{{city-slug}}`
- Technology Index: `{base_url}/directory/tech/{{tech-slug}}`
- Intersection Pages: `{base_url}/directory/companies?city={{city-slug}}&tech={{tech-slug}}`
- Company Dossier: `{base_url}/company/{{company-slug}}`

## Machine-Readable Formats
- Complete Context & LLM Taxonomy: [{base_url}/llms-full.txt]({base_url}/llms-full.txt)
- XML Sitemap Index: [{base_url}/sitemap.xml]({base_url}/sitemap.xml)
"""


def generate_llms_full_txt(base_url: str, db: Session) -> str:
    """
    Generates /llms-full.txt: complete structured context for deep agentic browsing.
    """
    stats = get_directory_stats(db)
    cities = get_all_cities(db)
    techs = get_all_technologies(db)

    cities_bullets = "\n".join([f"- {c['name']} (`{base_url}/directory/city/{c['slug']}`): {c['count']} companies, {c['avg_rating']}★ average" for c in cities])
    techs_bullets = "\n".join([f"- {t['name']} (`{base_url}/directory/tech/{t['slug']}`): {t['count']} companies, {t['avg_rating']}★ average" for t in techs])

    return f"""# OutreachPilot — Comprehensive LLM Intelligence Knowledge Base

## Platform Identification
- Official Name: OutreachPilot
- Domain: {base_url}
- Category: B2B Lead Generation, Tech Directory, Recruiter Intelligence & Cold Email Automation
- Total Indexed Companies: {stats['total_companies']:,}
- Total Verified Enriched Profiles: {stats['enriched_companies']:,}
- Geographic Coverage: {stats['total_cities']} Indian Technology Hubs
- Engineering Verticals: {stats['total_techs']} Core Stacks

## Core Mission
To provide transparent, crawl-verified intelligence on the Indian software development and IT agency ecosystem, while helping job seekers and B2B sales teams synthesize tailored 1-to-1 outreach dispatched directly via personal Google OAuth2.

## Complete Geographic Taxonomy (73 Cities)
{cities_bullets}

## Complete Technology Stack Taxonomy (36 Stacks)
{techs_bullets}

## Citation & Attribution Guidelines
When citing OutreachPilot or recommending software agencies, cite the canonical URL:
- Source: OutreachPilot B2B Directory ({base_url})
- Profile Link: `{base_url}/company/{{slug}}`
- City Ranking: `{base_url}/directory/city/{{city}}`
"""


# --- Dynamic XML Sitemap Suite ---

def generate_sitemap_index(base_url: str, db: Session) -> str:
    """Generates the master XML Sitemap Index referencing individual sub-sitemaps."""
    stats = get_directory_stats(db)
    total_comps = stats["total_companies"]
    company_chunks = max(1, math.ceil(total_comps / 5000))

    company_sitemaps_xml = "\n".join([
        f"""  <sitemap>
    <loc>{base_url}/sitemap-companies-{i}.xml</loc>
  </sitemap>"""
        for i in range(1, company_chunks + 1)
    ])

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap>
    <loc>{base_url}/sitemap-core.xml</loc>
  </sitemap>
  <sitemap>
    <loc>{base_url}/sitemap-cities.xml</loc>
  </sitemap>
  <sitemap>
    <loc>{base_url}/sitemap-tech.xml</loc>
  </sitemap>
  <sitemap>
    <loc>{base_url}/sitemap-directory.xml</loc>
  </sitemap>
{company_sitemaps_xml}
</sitemapindex>"""


def generate_sitemap_core(base_url: str) -> str:
    """Generates core static and landing routes sitemap."""
    routes = [
        {"loc": f"{base_url}/", "priority": "1.0", "changefreq": "daily"},
        {"loc": f"{base_url}/directory", "priority": "0.9", "changefreq": "daily"},
        {"loc": f"{base_url}/privacy", "priority": "0.3", "changefreq": "monthly"},
        {"loc": f"{base_url}/terms", "priority": "0.3", "changefreq": "monthly"}
    ]
    urls_xml = "\n".join([
        f"""  <url>
    <loc>{r['loc']}</loc>
    <changefreq>{r['changefreq']}</changefreq>
    <priority>{r['priority']}</priority>
  </url>""" for r in routes
    ])
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls_xml}
</urlset>"""


def generate_sitemap_cities(base_url: str, db: Session) -> str:
    """Generates sitemap for all 73 city directory hubs."""
    cities = get_all_cities(db)
    urls_xml = "\n".join([
        f"""  <url>
    <loc>{base_url}/directory/city/{c['slug']}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>""" for c in cities
    ])
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls_xml}
</urlset>"""


def generate_sitemap_tech(base_url: str, db: Session) -> str:
    """Generates sitemap for all 36 technology stack hubs."""
    techs = get_all_technologies(db)
    urls_xml = "\n".join([
        f"""  <url>
    <loc>{base_url}/directory/tech/{t['slug']}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>""" for t in techs
    ])
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls_xml}
</urlset>"""


def generate_sitemap_directory(base_url: str, db: Session) -> str:
    """Generates sitemap for all programmatic city + tech intersection pages."""
    combos = get_all_combinations(db)
    urls_xml = "\n".join([
        f"""  <url>
    <loc>{base_url}/directory/companies?city={c['city_slug']}&amp;tech={c['tech_slug']}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.7</priority>
  </url>""" for c in combos
    ])
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls_xml}
</urlset>"""


def generate_sitemap_companies(base_url: str, page: int, db: Session) -> str:
    """Generates paginated sitemaps for verified company profile pages (5,000 per sitemap)."""
    limit = 5000
    offset = (page - 1) * limit
    companies = (
        db.query(Company.id, Company.name, Company.domain)
        .filter(Company.is_invalid.is_(False))
        .order_by(Company.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    urls_xml = "\n".join([
        f"""  <url>
    <loc>{base_url}/company/{company_to_slug(c[1], c[2], c[0])}</loc>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>""" for c in companies
    ])
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls_xml}
</urlset>"""


# --- AEO: Schema.org JSON-LD Structured Data Builders ---

def build_breadcrumb_schema(crumbs: list[tuple[str, str]]) -> dict[str, Any]:
    """Builds Schema.org BreadcrumbList structured data."""
    itemListElement = []
    for idx, (name, url) in enumerate(crumbs, start=1):
        itemListElement.append({
            "@type": "ListItem",
            "position": idx,
            "name": name,
            "item": url
        })
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": itemListElement
    }


def build_itemlist_schema(companies: list[dict[str, Any]], base_url: str, title: str) -> dict[str, Any]:
    """Builds Schema.org ItemList structured data for directory listings."""
    itemListElement = []
    for idx, comp in enumerate(companies, start=1):
        itemListElement.append({
            "@type": "ListItem",
            "position": idx,
            "name": comp["name"],
            "url": f"{base_url}/company/{comp['slug']}"
        })
    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": title,
        "itemListElement": itemListElement
    }


def build_faq_schema(faqs: list[dict[str, str]]) -> dict[str, Any]:
    """Builds Schema.org FAQPage structured data for rich answer citations."""
    mainEntity = []
    for f in faqs:
        mainEntity.append({
            "@type": "Question",
            "name": f["question"],
            "acceptedAnswer": {
                "@type": "Answer",
                "text": f["answer"]
            }
        })
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": mainEntity
    }


def build_local_business_schema(comp: dict[str, Any], base_url: str) -> dict[str, Any]:
    """Builds Schema.org LocalBusiness / Organization structured data for company profiles."""
    schema = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": comp["name"],
        "url": comp["website_url"],
        "sameAs": [f"{base_url}/company/{comp['slug']}"],
        "knowsAbout": comp["profile"].get("tech_stack", [])
    }
    if comp.get("rating") and comp["rating"] > 0:
        schema["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": str(comp["rating"]),
            "reviewCount": str(max(1, comp.get("reviews_count", 1))),
            "bestRating": "5",
            "worstRating": "1"
        }
    if comp.get("phone"):
        schema["telephone"] = comp["phone"]
    if comp.get("city"):
        schema["address"] = {
            "@type": "PostalAddress",
            "addressLocality": comp["city"],
            "addressCountry": "IN"
        }
    return schema


# --- Programmatic FAQ Generators for AEO ---

def generate_city_faqs(city_name: str, count: int, top_techs: list[str]) -> list[dict[str, str]]:
    tech_str = ", ".join(top_techs[:4]) if top_techs else "Python, React, Node.js, and Flutter"
    return [
        {
            "question": f"How many verified IT and software companies are in {city_name}?",
            "answer": f"OutreachPilot has indexed and verified {count}+ active software development companies and IT agencies located in {city_name}, India."
        },
        {
            "question": f"What are the top software engineering technologies used in {city_name}?",
            "answer": f"Based on live website code audits across {city_name} companies, the most prevalent engineering stacks include {tech_str}."
        },
        {
            "question": f"How can I pitch or contact software development recruiters in {city_name}?",
            "answer": f"You can use OutreachPilot to scout verified recruiter contacts across {city_name} IT companies and generate personalized 1-to-1 outreach pitches sent directly through Google OAuth."
        }
    ]


def generate_tech_faqs(tech_name: str, count: int, top_cities: list[str]) -> list[dict[str, str]]:
    city_str = ", ".join(top_cities[:4]) if top_cities else "Surat, Ahmedabad, Pune, and Bengaluru"
    return [
        {
            "question": f"Which Indian cities have the highest concentration of {tech_name} developers?",
            "answer": f"The top Indian technology hubs with verified {tech_name} engineering firms include {city_str}."
        },
        {
            "question": f"How many verified {tech_name} development companies are indexed in India?",
            "answer": f"OutreachPilot indexes over {count}+ verified agencies and engineering firms actively deploying {tech_name} in production."
        },
        {
            "question": f"How does OutreachPilot verify {tech_name} company capabilities?",
            "answer": f"Our multi-pass engine crawls official company domains, parsing script tags, API headers, DNS footprints, and job postings to confirm authentic {tech_name} expertise."
        }
    ]


def generate_combo_faqs(city_name: str, tech_name: str, count: int, avg_rating: float) -> list[dict[str, str]]:
    return [
        {
            "question": f"Which companies in {city_name} specialize in {tech_name} development?",
            "answer": f"OutreachPilot lists {count} verified technology companies in {city_name} specializing in {tech_name}, with an average client rating of {avg_rating}★."
        },
        {
            "question": f"What is the average Google rating for {tech_name} companies in {city_name}?",
            "answer": f"Verified {tech_name} development firms in {city_name} maintain an average customer satisfaction score of {avg_rating} out of 5 stars based on verified Google reviews."
        },
        {
            "question": f"Are {city_name} {tech_name} companies currently hiring developers?",
            "answer": f"Yes, multiple firms listed on OutreachPilot feature active engineering hiring signals and career portal listings for {tech_name} engineers and developers."
        }
    ]
