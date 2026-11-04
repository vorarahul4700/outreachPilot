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

import math
import os
import re
import time
from typing import Any
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


# --- Bidirectional Slug & Normalization Dictionaries ---

SLUG_TECH_MAP = {
    "python": "Python",
    "react": "React",
    "reactjs": "React",
    "react-js": "React",
    "nodejs": "Node.js",
    "node-js": "Node.js",
    "node": "Node.js",
    "dotnet": ".NET",
    "dot-net": ".NET",
    "flutter": "Flutter",
    "java": "Java",
    "django": "Django",
    "fastapi": "FastAPI",
    "laravel": "Laravel",
    "php": "PHP",
    "angular": "Angular",
    "vue": "Vue.js",
    "vuejs": "Vue.js",
    "nextjs": "Next.js",
    "next-js": "Next.js",
    "ios": "iOS",
    "android": "Android",
    "aws": "AWS",
    "devops": "DevOps",
    "wordpress": "WordPress",
    "shopify": "Shopify",
    "golang": "Go",
    "go": "Go",
    "ruby": "Ruby on Rails",
    "rails": "Ruby on Rails",
    "uiux": "UI/UX",
    "ui-ux": "UI/UX",
    "ai-ml": "AI / Machine Learning",
    "ai": "AI / Machine Learning",
    "machine-learning": "AI / Machine Learning",
    "salesforce": "Salesforce",
    "qa-testing": "QA & Software Testing",
    "qa": "QA & Software Testing",
    "cpp": "C++",
    "csharp": "C#",
    "sql": "SQL / Databases",
    "mern": "MERN Stack",
    "mean": "MEAN Stack"
}

TECH_TO_SLUG_MAP = {
    "python": "python",
    "react": "react",
    "node.js": "nodejs",
    "nodejs": "nodejs",
    ".net": "dotnet",
    "flutter": "flutter",
    "java": "java",
    "django": "django",
    "fastapi": "fastapi",
    "laravel": "laravel",
    "php": "php",
    "angular": "angular",
    "vue.js": "vue",
    "vue": "vue",
    "next.js": "nextjs",
    "nextjs": "nextjs",
    "ios": "ios",
    "android": "android",
    "aws": "aws",
    "devops": "devops",
    "wordpress": "wordpress",
    "shopify": "shopify",
    "go": "golang",
    "golang": "golang",
    "ruby on rails": "ruby",
    "ruby": "ruby",
    "ui/ux": "uiux",
    "ai / machine learning": "ai-ml",
    "salesforce": "salesforce",
    "qa & software testing": "qa-testing",
    "c++": "cpp",
    "c#": "csharp",
    "sql / databases": "sql",
    "mern stack": "mern",
    "mean stack": "mean"
}


SEARCH_KEYWORD_CANONICAL = {
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


def slugify(text_val: str) -> str:
    """Converts raw text into an SEO-friendly URL slug."""
    if not text_val:
        return ""
    s = text_val.strip().lower()
    s = s.replace(".net", "dotnet").replace("c++", "cpp").replace("c#", "csharp")
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


def tech_to_slug(tech: str) -> str:
    if not tech:
        return ""
    clean = tech.strip().lower()
    if clean in TECH_TO_SLUG_MAP:
        return TECH_TO_SLUG_MAP[clean]
    return slugify(clean)


def slug_to_tech_name(slug: str) -> str:
    if not slug:
        return ""
    clean = slug.strip().lower()
    if clean in SLUG_TECH_MAP:
        return SLUG_TECH_MAP[clean]
    # Check canonical dictionary
    for raw, canonical in SEARCH_KEYWORD_CANONICAL.items():
        if slugify(canonical) == clean:
            return canonical
    return slug.replace("-", " ").title()


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


def get_all_technologies(db: Session) -> list[dict[str, Any]]:
    cached = get_cached("all_techs")
    if cached:
        return cached

    rows = db.execute(text("""
        SELECT 
            search_keyword AS raw_tech,
            COUNT(*) AS count,
            ROUND(AVG(rating)::numeric, 1) AS avg_rating
        FROM companies
        WHERE is_invalid = FALSE 
          AND search_keyword IS NOT NULL 
          AND trim(search_keyword) != ''
        GROUP BY search_keyword
        HAVING COUNT(*) >= 5
        ORDER BY count DESC;
    """)).fetchall()

    results = []
    seen_slugs = set()
    for r in rows:
        raw_tech = r[0].strip()
        display_name = SEARCH_KEYWORD_CANONICAL.get(raw_tech, raw_tech)
        slug = tech_to_slug(display_name)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        results.append({
            "name": display_name,
            "raw_keyword": raw_tech,
            "slug": slug,
            "count": r[1],
            "avg_rating": float(r[2] or 4.3)
        })

    set_cached("all_techs", results)
    return results


def get_all_combinations(db: Session) -> list[dict[str, Any]]:
    cached = get_cached("all_combinations")
    if cached:
        return cached

    rows = db.execute(text("""
        SELECT 
            initcap(trim(city)) AS city_name,
            search_keyword,
            COUNT(*) AS count,
            ROUND(AVG(rating)::numeric, 1) AS avg_rating
        FROM companies
        WHERE is_invalid = FALSE 
          AND city IS NOT NULL AND trim(city) != ''
          AND search_keyword IS NOT NULL AND trim(search_keyword) != ''
        GROUP BY initcap(trim(city)), search_keyword
        HAVING COUNT(*) >= 1
        ORDER BY count DESC;
    """)).fetchall()

    combos = []
    seen = set()
    for r in rows:
        c_name = r[0]
        raw_tech = r[1].strip()
        disp_tech = SEARCH_KEYWORD_CANONICAL.get(raw_tech, raw_tech)
        c_slug = city_to_slug(c_name)
        t_slug = tech_to_slug(disp_tech)
        combo_key = f"{c_slug}:{t_slug}"
        if combo_key in seen:
            continue
        seen.add(combo_key)
        combos.append({
            "city_name": c_name,
            "city_slug": c_slug,
            "tech_name": disp_tech,
            "tech_slug": t_slug,
            "count": r[2],
            "avg_rating": float(r[3] or 4.2)
        })

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
        tech_slug = tech_to_slug(tech)
        # Find all raw search keywords mapped to this tech
        matching_keywords = [
            raw for raw, canonical in SEARCH_KEYWORD_CANONICAL.items()
            if slugify(canonical) == tech_slug or tech_slug in slugify(canonical)
        ]
        if not matching_keywords:
            matching_keywords = [tech]

        query = query.filter(
            or_(
                Company.search_keyword.in_(matching_keywords),
                func.lower(Company.search_keyword).ilike(f"%{tech.strip().lower()}%"),
                func.lower(Company.normalized_keyword) == tech.strip().lower()
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
            canon_name = SEARCH_KEYWORD_CANONICAL.get(c.search_keyword, c.search_keyword.replace(" Development Companies", ""))
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

    profile_data = {
        "summary": "Verified technology company providing custom software, web application development, and engineering consulting services.",
        "detailed_analysis": None,
        "industry": "Custom Software & Information Technology",
        "tech_stack": [],
        "services": ["Web Application Development", "Custom Software Engineering"],
        "hiring_signals": "Active engineering and technology operations",
        "tone": "Professional"
    }

    if c.profile:
        profile_data = {
            "summary": c.profile.summary_short or profile_data["summary"],
            "detailed_analysis": c.profile.detailed_analysis or None,
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
- Intersection Pages: `{base_url}/directory/companies/{{city-slug}}/{{tech-slug}}`
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
    <loc>{base_url}/directory/companies/{c['city_slug']}/{c['tech_slug']}</loc>
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
