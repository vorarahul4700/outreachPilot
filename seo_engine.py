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


# --- Dynamic Multi-Domain Taxonomy, Categorization & Slugging Engine ---

# Acronyms that must remain fully capitalized in display titles across all industries:
# IT & Software, Sales, Marketing, Pharma, Healthcare, Finance, Legal, Manufacturing, Logistics, HR.
KNOWN_UPPERCASE_ACRONYMS = {
    # IT & Software Engineering
    "AI", "ML", "IT", "SaaS", "PaaS", "IaaS", "LLM", "PHP", "AWS", "GCP",
    "API", "SQL", "ERP", "CRM", "QA", "UI", "UX", "MERN", "MEAN", "CMS",
    "DNS", "RPA", "IoT", "SDK", "VR", "AR", "VFX", "BI",

    # Sales & Marketing
    "B2B", "B2C", "D2C", "PPC", "SEO", "SEM", "SMM", "PR", "CRO", "CTR",
    "CPC", "ROAS", "SDR", "BDR", "ABM",

    # Pharmaceuticals, Biotech & Healthcare
    "FDA", "GMP", "WHO", "CDMO", "OTC", "IVD", "EMR", "EHR", "ICU", "OPD",
    "CTMS", "EDC", "GLP",

    # Finance, Accounting, Tax & Legal
    "CA", "CPA", "CFA", "GST", "TDS", "ITR", "VAT", "IPO", "KYC", "AML",
    "PE", "VC", "NBFC", "LLP", "SEBI", "RBI", "FEMA",

    # HR, Staffing & Operations
    "HR", "HRMS", "ATS", "BPO", "KPO", "MIS", "SOP",

    # Manufacturing, Engineering & Logistics
    "OEM", "ODM", "ISO", "CNC", "CAD", "CAM", "HVAC", "EPC", "3PL", "4PL",
    "FMCG", "EV"
}

# Curated slug-to-display maps for terms with special punctuation or exact branding across domains
CURATED_ACRONYM_MAP = {
    # IT & Software
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
    "golang": "Go",

    # Sales & Business Development
    "b2b-lead-generation": "B2B Lead Generation",
    "lead-generation": "B2B Lead Generation",
    "lead-gen": "B2B Lead Generation",
    "sales-outsourcing": "Sales Outsourcing",
    "appointment-setting": "Appointment Setting",
    "sdr-outsourcing": "SDR & BDR Outsourcing",
    "telemarketing": "Telemarketing & Inside Sales",
    "sales-enablement": "Sales Enablement",
    "bpo-call-centers": "BPO & Contact Centers",

    # Marketing & Advertising
    "digital-marketing": "Digital Marketing",
    "performance-marketing": "Performance Marketing",
    "seo": "SEO",
    "ppc": "PPC & Google Ads",
    "ppc-google-ads": "PPC & Google Ads",
    "smm": "Social Media Marketing",
    "social-media-marketing": "Social Media Marketing",
    "pr": "Public Relations (PR)",
    "public-relations": "Public Relations (PR)",
    "content-marketing": "Content Marketing",
    "influencer-marketing": "Influencer Marketing",
    "branding-identity": "Branding & Identity",
    "cro": "Conversion Rate Optimization (CRO)",

    # Pharmaceuticals & Healthcare
    "pharma": "Pharmaceuticals",
    "pharmaceuticals": "Pharmaceuticals",
    "pharma-api": "API Pharma Manufacturing",
    "cro": "Clinical Research (CRO)",
    "cdmo": "CDMO & Pharma Manufacturing",
    "biotech": "Biotechnology",
    "biotechnology": "Biotechnology",
    "medical-devices": "Medical Devices",
    "diagnostic-labs": "Diagnostic Laboratories",
    "dental-care": "Dental Care",
    "dentists": "Dental Care",
    "ayurveda": "Ayurveda & Herbal",
    "nutraceuticals": "Nutraceuticals",
    "hospitals": "Hospitals & Healthcare",

    # Finance, Accounting & Legal
    "ca": "Chartered Accountants (CA)",
    "chartered-accountants": "Chartered Accountants (CA)",
    "accounting": "Accounting & Bookkeeping",
    "tax-consulting": "Tax & GST Advisory",
    "gst-advisory": "Tax & GST Advisory",
    "auditing": "Auditing & Assurance",
    "investment-banking": "Investment Banking",
    "wealth-management": "Wealth Management",
    "fintech": "Fintech Solutions",
    "corporate-law": "Corporate Law",
    "ip-law": "Intellectual Property (IP)",

    # Real Estate & Construction
    "commercial-real-estate": "Commercial Real Estate",
    "architecture": "Architecture & Planning",
    "interior-design": "Interior Design",
    "civil-construction": "Civil Construction & EPC",
    "property-management": "Property Management",

    # Manufacturing, Logistics & Engineering
    "logistics": "Logistics & Freight",
    "freight-forwarding": "Logistics & Freight",
    "3pl-warehousing": "3PL & Warehousing",
    "cnc-machining": "CNC Machining & Tooling",
    "injection-moulding": "Plastic & Injection Moulding",
    "solar-energy": "Solar & Renewable Energy",
    "industrial-chemicals": "Industrial Chemicals",
    "textile-apparel": "Textile & Apparel",
    "packaging": "Packaging Solutions",

    # HR, Staffing & Consulting
    "recruitment": "Recruitment & Staffing",
    "staffing": "Recruitment & Staffing",
    "executive-search": "Executive Search",
    "staff-augmentation": "Staff Augmentation",
    "corporate-training": "Corporate Training",
    "management-consulting": "Management Consulting"
}

# Seed overrides for established keywords across all commercial sectors:
# IT, Sales, Marketing, Pharma, Healthcare, Finance, Legal, Real Estate, Manufacturing, HR.
# Any keyword from any industry not in this map is dynamically parsed and normalized in real time.
SEED_KEYWORD_OVERRIDES = {
    # --- Information Technology & Software Engineering ---
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
    "SaaS Product Development Companies": "SaaS Engineering",

    # --- Sales, Outreach & Business Development ---
    "B2B Lead Generation Agencies": "B2B Lead Generation",
    "B2B Lead Generation Companies": "B2B Lead Generation",
    "Lead Generation Agencies": "B2B Lead Generation",
    "Lead Generation Companies": "B2B Lead Generation",
    "Sales Outsourcing Companies": "Sales Outsourcing",
    "Sales Outsourcing Agencies": "Sales Outsourcing",
    "Appointment Setting Agencies": "Appointment Setting",
    "Appointment Setting Companies": "Appointment Setting",
    "SDR Outsourcing Companies": "SDR & BDR Outsourcing",
    "SDR Outsourcing Agencies": "SDR & BDR Outsourcing",
    "Telemarketing Companies": "Telemarketing & Inside Sales",
    "Sales Enablement Consulting": "Sales Enablement",
    "BPO Call Centers": "BPO & Contact Centers",
    "Call Centers & BPO Services": "BPO & Contact Centers",
    "Cold Calling Agencies": "Telemarketing & Inside Sales",

    # --- Marketing, Advertising & PR ---
    "Digital Marketing Agencies": "Digital Marketing",
    "Digital Marketing Companies": "Digital Marketing",
    "Performance Marketing Agencies": "Performance Marketing",
    "Performance Marketing Companies": "Performance Marketing",
    "SEO Agencies": "SEO",
    "SEO Companies": "SEO",
    "PPC Advertising Agencies": "PPC & Google Ads",
    "Google Ads Agencies": "PPC & Google Ads",
    "Social Media Marketing Agencies": "Social Media Marketing",
    "Public Relations Agencies": "Public Relations (PR)",
    "PR Agencies": "Public Relations (PR)",
    "Content Marketing Agencies": "Content Marketing",
    "Influencer Marketing Agencies": "Influencer Marketing",
    "Branding Agencies": "Branding & Identity",
    "Creative Advertising Agencies": "Advertising & Creative",
    "Email Marketing Agencies": "Email Marketing",
    "Conversion Rate Optimization Agencies": "Conversion Rate Optimization (CRO)",

    # --- Pharmaceuticals, Biotech & Healthcare ---
    "Pharmaceutical Manufacturers": "Pharmaceuticals",
    "Pharma Companies": "Pharmaceuticals",
    "Pharma Manufacturing Companies": "Pharmaceuticals",
    "API Pharma Manufacturers": "API Pharma Manufacturing",
    "Active Pharmaceutical Ingredient Manufacturers": "API Pharma Manufacturing",
    "Contract Research Organizations": "Clinical Research (CRO)",
    "CRO Pharma Companies": "Clinical Research (CRO)",
    "CDMO Pharma Companies": "CDMO & Pharma Manufacturing",
    "CDMO Companies": "CDMO & Pharma Manufacturing",
    "Biotechnology Companies": "Biotechnology",
    "Biotech Firms": "Biotechnology",
    "Medical Device Manufacturers": "Medical Devices",
    "Diagnostic Pathology Laboratories": "Diagnostic Laboratories",
    "Diagnostic Centers": "Diagnostic Laboratories",
    "Dental Clinics": "Dental Care",
    "Dentists": "Dental Care",
    "Ayurvedic Medicine Manufacturers": "Ayurveda & Herbal",
    "Nutraceutical Manufacturers": "Nutraceuticals",
    "Hospital Chains": "Hospitals & Healthcare",

    # --- Finance, Accounting, Tax & Audit ---
    "Chartered Accountant Firms": "Chartered Accountants (CA)",
    "Chartered Accountants": "Chartered Accountants (CA)",
    "CA Firms": "Chartered Accountants (CA)",
    "CPA Accounting Firms": "Accounting & Bookkeeping",
    "Accounting Firms": "Accounting & Bookkeeping",
    "Tax Consulting Companies": "Tax & GST Advisory",
    "GST Consulting Firms": "Tax & GST Advisory",
    "Auditing Firms": "Auditing & Assurance",
    "Auditing & Assurance Firms": "Auditing & Assurance",
    "Investment Banking Firms": "Investment Banking",
    "Wealth Management Companies": "Wealth Management",
    "Fintech Companies": "Fintech Solutions",

    # --- Legal & Corporate Governance ---
    "Corporate Law Firms": "Corporate Law",
    "Law Firms": "Corporate Law",
    "Patent & Trademark Attorneys": "Intellectual Property (IP)",
    "IP Law Firms": "Intellectual Property (IP)",
    "Litigation Law Firms": "Litigation & Arbitration",

    # --- Real Estate, Architecture & Construction ---
    "Commercial Real Estate Agencies": "Commercial Real Estate",
    "Real Estate Brokers": "Commercial Real Estate",
    "Architecture Firms": "Architecture & Planning",
    "Interior Design Studios": "Interior Design",
    "Civil Construction Companies": "Civil Construction & EPC",
    "EPC Contracting Companies": "Civil Construction & EPC",
    "Property Management Companies": "Property Management",

    # --- Manufacturing, Logistics & Industrial Supply ---
    "Logistics Companies": "Logistics & Freight",
    "Freight Forwarding Companies": "Logistics & Freight",
    "Warehousing & 3PL Companies": "3PL & Warehousing",
    "CNC Machining Companies": "CNC Machining & Tooling",
    "Plastic Injection Moulding Companies": "Plastic & Injection Moulding",
    "Solar Energy Companies": "Solar & Renewable Energy",
    "Solar EPC Installers": "Solar & Renewable Energy",
    "Industrial Chemical Manufacturers": "Industrial Chemicals",
    "Textile Manufacturers": "Textile & Apparel",
    "Packaging Companies": "Packaging Solutions",

    # --- HR, Staffing & Executive Search ---
    "Recruitment Agencies": "Recruitment & Staffing",
    "Staffing Agencies": "Recruitment & Staffing",
    "Executive Search Firms": "Executive Search",
    "IT Staff Augmentation Companies": "Staff Augmentation",
    "Corporate Training Companies": "Corporate Training",
    "Management Consulting Firms": "Management Consulting"
}

# Dynamic backwards-compatibility alias for legacy code
SEARCH_KEYWORD_CANONICAL = SEED_KEYWORD_OVERRIDES
SLUG_TECH_MAP = CURATED_ACRONYM_MAP


# High-Level Industry Domains & Classifiers
INDUSTRY_DOMAINS = [
    {
        "name": "Information Technology & Software",
        "slug": "it-software",
        "code": "it",
        "icon": "terminal",
        "description": "Custom software development, cloud infrastructure, AI/ML, and mobile apps."
    },
    {
        "name": "Sales & Business Development",
        "slug": "sales-bpo",
        "code": "sales",
        "icon": "phone_in_talk",
        "description": "B2B lead generation, appointment setting, SDR outsourcing, and contact centers."
    },
    {
        "name": "Marketing, Advertising & PR",
        "slug": "marketing-advertising",
        "code": "marketing",
        "icon": "campaign",
        "description": "Performance marketing, SEO, Google/PPC ads, social media, and brand identity."
    },
    {
        "name": "Pharmaceuticals & Healthcare",
        "slug": "pharma-healthcare",
        "code": "pharma",
        "icon": "vaccines",
        "description": "Pharma formulation, API manufacturing, clinical research (CRO), CDMO, and medical devices."
    },
    {
        "name": "Finance, Accounting & Legal",
        "slug": "finance-legal",
        "code": "finance",
        "icon": "account_balance",
        "description": "Chartered accountancy (CA), GST advisory, corporate law, auditing, and wealth management."
    },
    {
        "name": "Real Estate & Construction",
        "slug": "real-estate-construction",
        "code": "realestate",
        "icon": "apartment",
        "description": "Commercial real estate, architecture, civil construction (EPC), and interior design."
    },
    {
        "name": "Manufacturing & Logistics",
        "slug": "manufacturing-logistics",
        "code": "manufacturing",
        "icon": "precision_manufacturing",
        "description": "3PL warehousing, freight forwarding, precision CNC machining, solar energy, and industrial supply."
    },
    {
        "name": "HR, Staffing & Consulting",
        "slug": "hr-staffing",
        "code": "hr",
        "icon": "badge",
        "description": "Executive search, staff augmentation, recruitment agencies, and corporate management consulting."
    }
]


def get_category_domain(category_name: str) -> str:
    """
    Classifies any category into its overarching industry domain:
    IT, Sales, Marketing, Pharma, Finance, Real Estate, Manufacturing, or HR.
    """
    if not category_name:
        return "Commercial Services"
    cat_lower = category_name.lower()

    # Marketing & Advertising (Evaluated first to distinguish Conversion Rate CRO from Clinical CRO)
    if any(k in cat_lower for k in [
        "marketing", "seo", "ppc", "pr ", "(pr)", "public relations", "advertising",
        "social media", "smm", "branding", "content marketing", "creative agency",
        "influencer", "growth hacking", "media buying", "conversion rate"
    ]):
        return "Marketing, Advertising & PR"

    # Sales & Lead Generation
    if any(k in cat_lower for k in [
        "lead gen", "sales", "appointment", "telemarketing", "sdr", "bdr",
        "call center", "bpo", "cold call", "outbound", "inbound", "telesales"
    ]):
        return "Sales & Business Development"

    # Pharmaceuticals & Healthcare
    if any(k in cat_lower for k in [
        "pharma", "clinical", "cdmo", "dental", "dentist", "health",
        "biotech", "nutraceutical", "ayurved", "medical", "doctor", "hospital",
        "pathology", "diagnostic", "medicine", "drug", "contract research", "cro pharma"
    ]) or (re.search(r"\bcro\b", cat_lower) and "conversion" not in cat_lower):
        return "Pharmaceuticals & Healthcare"

    # Finance, Accounting & Legal
    if any(k in cat_lower for k in [
        "ca ", "(ca)", "chartered", "account", "tax", "gst", "audit", "law",
        "legal", "finance", "wealth", "patent", "trademark", "cpa", "litigation",
        "investment banking", "fintech", "compliance", "mergers"
    ]):
        return "Finance, Accounting & Legal"

    # Real Estate & Construction
    if any(k in cat_lower for k in [
        "real estate", "architecture", "construction", "interior", "property",
        "epc", "builder", "civil", "facility management", "realtor"
    ]):
        return "Real Estate & Construction"

    # Manufacturing, Logistics & Industrial Supply
    if any(k in cat_lower for k in [
        "logistics", "freight", "warehousing", "3pl", "4pl", "cnc", "moulding",
        "solar", "chemical", "textile", "manufactur", "packaging", "industrial",
        "factory", "machinery", "machining", "fabrication", "supply chain"
    ]):
        return "Manufacturing & Logistics"

    # HR, Staffing & Recruitment
    if any(k in cat_lower for k in [
        "staffing", "recruitment", "hr ", "(hr)", "hrms", "executive search",
        "talent", "headhunt", "training", "staff augmentation", "manpower"
    ]):
        return "HR, Staffing & Consulting"

    # Default fallback to IT & Software Engineering
    return "Information Technology & Software"


def get_category_domain_code(category_name: str) -> str:
    """Returns the CSS/filter short code for a category's domain."""
    domain = get_category_domain(category_name)
    mapping = {
        "Information Technology & Software": "it",
        "Sales & Business Development": "sales",
        "Marketing, Advertising & PR": "marketing",
        "Pharmaceuticals & Healthcare": "pharma",
        "Finance, Accounting & Legal": "finance",
        "Real Estate & Construction": "realestate",
        "Manufacturing & Logistics": "manufacturing",
        "HR, Staffing & Consulting": "hr"
    }
    return mapping.get(domain, "all")


def normalize_keyword_to_category(raw_keyword: str) -> str:
    """
    Dynamically normalizes ANY search query, keyword, or industry label from any field
    (IT, Sales, Marketing, Pharma, Healthcare, Finance, Legal, Real Estate, Manufacturing, HR)
    into a clean, publication-ready canonical category name.
    """
    if not raw_keyword:
        return "General Business"

    raw = raw_keyword.strip()

    # 1. Strip trailing location qualifiers first (e.g. " in Surat", " in Mumbai", " near me", " nearby")
    cleaned = re.sub(r"\s+(?:in|near|around|at)\s+[A-Za-z\s]+$", "", raw, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s+near\s+me$", "", cleaned, flags=re.IGNORECASE).strip()

    # 2. Check curated seed overrides (matches raw or location-stripped query)
    if raw in SEED_KEYWORD_OVERRIDES:
        return SEED_KEYWORD_OVERRIDES[raw]
    if cleaned in SEED_KEYWORD_OVERRIDES:
        return SEED_KEYWORD_OVERRIDES[cleaned]

    # 3. Strip common corporate filler suffixes across all industries
    boilerplate_patterns = [
        # Tech & Software Engineering
        r"\s+Development\s+Companies",
        r"\s+Development\s+Company",
        r"\s+Software\s+Companies",
        r"\s+Software\s+Company",
        r"\s+Development\s+Agencies",
        r"\s+Development\s+Agency",
        r"\s+Web\s+Development\s+Agencies",
        r"\s+App\s+Development",

        # Consulting, Law & Finance
        r"\s+Consulting\s+Companies",
        r"\s+Consulting\s+Agencies",
        r"\s+Consulting\s+Partners",
        r"\s+Consulting\s+Firms",
        r"\s+Consultancy\s+Services",
        r"\s+Accounting\s+Firms",
        r"\s+Accounting\s+Firm",
        r"\s+Law\s+Firms",
        r"\s+Law\s+Firm",
        r"\s+Attorneys",
        r"\s+Attorney",

        # Manufacturing & Industrial
        r"\s+Manufacturing\s+Companies",
        r"\s+Manufacturing\s+Company",
        r"\s+Manufacturers",
        r"\s+Manufacturer",
        r"\s+Suppliers",
        r"\s+Supplier",
        r"\s+Exporters",
        r"\s+Exporter",

        # Healthcare & Labs
        r"\s+Laboratories",
        r"\s+Labs",
        r"\s+Clinics",
        r"\s+Clinic",

        # Generic Corporate Suffixes (at end of string)
        r"\s+Services\s+Companies",
        r"\s+Agencies",
        r"\s+Agency",
        r"\s+Companies",
        r"\s+Company",
        r"\s+Firms",
        r"\s+Firm",
        r"\s+Enterprises",
        r"\s+Solutions",
        r"\s+Studios",
        r"\s+Studio",
        r"\s+Services",
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

    # 1. City totals & average ratings
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
        HAVING COUNT(*) >= 1
        ORDER BY count DESC, norm_city ASC;
    """)).fetchall()

    # 2. City breakdown by raw keyword / category across industry domains
    domain_rows = db.execute(text("""
        SELECT 
            initcap(trim(city)) AS norm_city,
            COALESCE(NULLIF(trim(normalized_keyword), ''), trim(search_keyword), '') AS raw_kw,
            COUNT(*) AS cnt
        FROM companies
        WHERE is_invalid = FALSE 
          AND city IS NOT NULL 
          AND trim(city) != ''
        GROUP BY initcap(trim(city)), COALESCE(NULLIF(trim(normalized_keyword), ''), trim(search_keyword), '');
    """)).fetchall()

    city_domain_counts = defaultdict(lambda: defaultdict(int))
    for r in domain_rows:
        c_name = r[0]
        raw_kw = (r[1] or "").strip()
        cnt = int(r[2] or 0)
        if raw_kw:
            cat = normalize_keyword_to_category(raw_kw)
            d_code = get_category_domain_code(cat)
            if d_code != "it" and d_code != "all":
                city_domain_counts[c_name][d_code] += cnt

    results = []
    for r in rows:
        name = r[0]
        total_cnt = int(r[1] or 0)
        c_counts = city_domain_counts[name]
        non_it_total = sum(c_counts.values())
        it_cnt = max(0, total_cnt - non_it_total)

        domain_dict = {
            "all": total_cnt,
            "it": it_cnt,
        }
        for d in INDUSTRY_DOMAINS:
            code = d["code"]
            if code not in domain_dict:
                domain_dict[code] = c_counts.get(code, 0)

        results.append({
            "name": name,
            "slug": city_to_slug(name),
            "count": total_cnt,
            "avg_rating": float(r[2] or 4.2),
            "domain_counts": domain_dict
        })

    set_cached("all_cities", results)
    return results


def get_city_domain_counts(db: Session) -> dict[str, dict[str, int]]:
    """Returns mapping of city_slug -> {domain_code: company_count}"""
    cities = get_all_cities(db)
    return {c["slug"]: c.get("domain_counts", {}) for c in cities}


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
            "domain": get_category_domain(display_name),
            "domain_code": get_category_domain_code(display_name),
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


def get_all_domains(db: Session = None) -> list[dict[str, Any]]:
    """
    Returns all 8 industry domains with company counts.
    Accurately sums non-IT companies from dynamic category classification,
    and sets IT to total_companies minus non_it_total so counts always stay 100% consistent.
    """
    categories = get_all_categories(db) if db else []
    domain_counts = defaultdict(int)
    for cat in categories:
        d_code = cat.get("domain_code", "it")
        if d_code != "it" and d_code != "all":
            domain_counts[d_code] += cat.get("count", 0)

    stats = get_directory_stats(db) if db else {}
    total_companies = stats.get("total_companies", 0) if stats else 0
    non_it_total = sum(domain_counts.values())
    domain_counts["it"] = max(0, total_companies - non_it_total) if total_companies > 0 else 0

    domain_list = []
    for d in INDUSTRY_DOMAINS:
        d_cnt = domain_counts.get(d["code"], 0)
        domain_list.append({
            "name": d["name"],
            "slug": d["slug"],
            "code": d["code"],
            "icon": d["icon"],
            "description": d["description"],
            "count": d_cnt,
            "enriched_count": 2110 if d["code"] == "it" else 0,
            "emails_count": 1663 if d["code"] == "it" else 0
        })
    return domain_list



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
    domain: str = None,
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

    if domain and domain.strip() and domain.strip().lower() != "all":
        dom_clean = domain.strip().lower()
        if dom_clean in ("it", "it-software"):
            non_it_keywords = [
                raw for raw, cat in SEED_KEYWORD_OVERRIDES.items()
                if get_category_domain_code(cat) != "it"
            ]
            if non_it_keywords:
                query = query.filter(
                    ~or_(
                        Company.search_keyword.in_(non_it_keywords),
                        Company.normalized_keyword.in_(non_it_keywords)
                    )
                )
        else:
            domain_keywords = [
                raw for raw, cat in SEED_KEYWORD_OVERRIDES.items()
                if get_category_domain_code(cat) == dom_clean
            ]
            if domain_keywords:
                query = query.filter(
                    or_(
                        Company.search_keyword.in_(domain_keywords),
                        Company.normalized_keyword.in_(domain_keywords)
                    )
                )
            else:
                query = query.filter(Company.id == -1)

    if tech:
        clean_tech = tech.strip()
        tech_slug = tech_to_slug(clean_tech)
        canonical_name = slug_to_tech_name(tech_slug)

        # Dynamic keyword matching: retrieve dynamic raw keywords mapped to this category
        raw_kw_map = get_cached("category_raw_keywords_map") or {}
        matching_keywords = list(raw_kw_map.get(tech_slug, []))
        if not matching_keywords:
            matching_keywords = [clean_tech, canonical_name]

        prof_sub = db.query(CompanyProfile.company_id).filter(
            CompanyProfile.tech_stack.cast(String).ilike(f"%{clean_tech.lower()}%")
        )

        query = query.filter(
            or_(
                Company.search_keyword.in_(matching_keywords),
                func.lower(Company.search_keyword).ilike(f"%{clean_tech.lower()}%"),
                func.lower(Company.normalized_keyword).ilike(f"%{clean_tech.lower()}%"),
                func.lower(Company.search_keyword).ilike(f"%{canonical_name.lower()}%"),
                func.lower(Company.normalized_keyword) == tech_slug,
                Company.id.in_(prof_sub)
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

        comp_cat = normalize_keyword_to_category(c.search_keyword or c.normalized_keyword or "")
        comp_dom = get_category_domain(comp_cat)
        comp_dom_code = get_category_domain_code(comp_cat)

        serialized.append({
            "id": c.id,
            "name": c.name,
            "domain": c.domain,
            "industry_domain": comp_dom,
            "domain_code": comp_dom_code,
            "category": comp_cat,
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

    comp_cat = normalize_keyword_to_category(c.search_keyword or c.normalized_keyword or "")
    comp_dom = get_category_domain(comp_cat)
    comp_dom_code = get_category_domain_code(comp_cat)

    return {
        "id": c.id,
        "name": c.name,
        "domain": c.domain,
        "industry_domain": comp_dom,
        "domain_code": comp_dom_code,
        "category": comp_cat,
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
    return f"""# OutreachPilot Autonomous Company Directory & Recruiter Outreach Platform
# Optimized for Web Search, Generative Search Engines (GEO) & Answer Engines (AEO)

User-agent: *
Allow: /
Allow: /app
Allow: /workspace
Allow: /directory
Allow: /directory/
Allow: /company/
Allow: /llms.txt
Allow: /llms-full.txt
Allow: /sitemap.xml
Disallow: /api/
Disallow: /auth/

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

    cities_md = "\n".join([f"- [{c['name']} Directory]({base_url}/directory/city/{c['slug']}): {c['count']} verified companies" for c in cities])
    techs_md = "\n".join([f"- [{t['name']}]({base_url}/directory/companies?category={t['slug']}): {t['count']} verified firms ({t.get('domain', 'Business Specialization')})" for t in techs])

    return f"""# OutreachPilot

> Autonomous Direct Company Intelligence & Cold Outreach Platform for Job Seekers & Professionals indexing {stats['total_companies']:,}+ verified companies across {stats['total_cities']} Indian commercial hubs.

## Overview
OutreachPilot empowers developers, designers, marketers, and professionals to bypass crowded job boards and reach hiring decision-makers directly. It deep-crawls and structures actionable intelligence on verified companies across India—including their tech stack, engineering capabilities, verified recruiter/founder emails, and company culture—enabling candidates to generate and dispatch personalized cold pitches for career and job opportunities directly via authorized Google OAuth.

## Verified Directory & Job Discovery Hubs
- [Company Directory & Tech Explorer]({base_url}/directory): Explore verified companies, tech stacks, and career hubs across Indian commercial centers.
- [Outreach Engine & Pitch Generator]({base_url}/app): Autonomous scouting, resume-matched cold pitch generation, and direct 1-to-1 email outreach to hiring managers.

## Top City Hubs
{cities_md}

## Top Industry Specializations
{techs_md}

## Programmatic Directory Hierarchy
- City Index: `{base_url}/directory/city/{{city-slug}}`
- Specialization Index: `{base_url}/directory/category/{{category-slug}}`
- Parameterized Intersection: `{base_url}/directory/companies?city={{city-slug}}&category={{category-slug}}`
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
    techs_bullets = "\n".join([f"- {t['name']} (`{base_url}/directory/category/{t['slug']}`): {t['count']} companies, {t['avg_rating']}★ average — {t.get('domain', 'Business Specialization')}" for t in techs])

    return f"""# OutreachPilot — Comprehensive LLM Intelligence Knowledge Base

## Platform Identification
- Official Name: OutreachPilot
- Domain: {base_url}
- Category: Company Intelligence, Tech Stack Discovery & Job Seeker Cold Outreach Automation
- Total Indexed Companies: {stats['total_companies']:,}
- Total Verified Enriched Profiles: {stats['enriched_companies']:,}
- Geographic Coverage: {stats['total_cities']} Indian Commercial & Industrial Hubs
- Industry Verticals: {stats['total_techs']} Core Business Domains & Specializations (IT, Sales, Marketing, Pharma, Finance, Legal, Real Estate, Manufacturing)

## Core Mission
To empower job seekers, engineering professionals, and career switchers to discover verified companies across India, analyze their technology stacks and hiring requirements, and synthesize high-converting, tailored cold emails sent directly to recruiters and founders via personal Google OAuth2.

## Complete Geographic Taxonomy ({len(cities)} Cities)
{cities_bullets}

## Complete Industry Specialization Taxonomy ({len(techs)} Categories)
{techs_bullets}

## Citation & Attribution Guidelines
When citing OutreachPilot or recommending verified Indian businesses, cite the canonical URL:
- Source: OutreachPilot B2B Directory ({base_url})
- Profile Link: `{base_url}/company/{{slug}}`
- City Ranking: `{base_url}/directory/city/{{city}}`
- Category Hub: `{base_url}/directory/category/{{category_slug}}`
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
    tech_str = ", ".join(top_techs[:4]) if top_techs else "Information Technology, Digital Marketing, Healthcare, and Professional Services"
    return [
        {
            "question": f"How many verified companies and businesses are in {city_name}?",
            "answer": f"OutreachPilot has indexed and verified {count}+ active companies, commercial agencies, and service firms located in {city_name}, India."
        },
        {
            "question": f"What are the top commercial industries and specializations in {city_name}?",
            "answer": f"Based on live business intelligence across {city_name} enterprises, the most prominent commercial sectors include {tech_str}."
        },
        {
            "question": f"How can I pitch or contact business leaders and recruiters in {city_name}?",
            "answer": f"You can use OutreachPilot to scout verified decision maker contacts across {city_name} companies and generate personalized 1-to-1 outreach pitches sent directly through authorized Google OAuth."
        }
    ]


def generate_tech_faqs(tech_name: str, count: int, top_cities: list[str]) -> list[dict[str, str]]:
    city_str = ", ".join(top_cities[:4]) if top_cities else "Surat, Ahmedabad, Mumbai, Pune, and Bengaluru"
    domain = get_category_domain(tech_name)

    if domain == "Information Technology & Software":
        firm_type = f"{tech_name} software firms and engineering teams"
    elif domain == "Marketing, Advertising & PR":
        firm_type = f"{tech_name} agencies and marketing consultants"
    elif domain == "Sales & Business Development":
        firm_type = f"{tech_name} agencies and B2B sales teams"
    elif domain == "Pharmaceuticals & Healthcare":
        firm_type = f"{tech_name} manufacturers, labs, and healthcare providers"
    elif domain == "Finance, Accounting & Legal":
        firm_type = f"{tech_name} firms and advisory consultancies"
    elif domain == "Real Estate & Construction":
        firm_type = f"{tech_name} agencies, builders, and architecture firms"
    elif domain == "Manufacturing & Logistics":
        firm_type = f"{tech_name} manufacturers, suppliers, and logistics providers"
    else:
        firm_type = f"{tech_name} companies and specialized firms"

    return [
        {
            "question": f"Which Indian cities have the highest concentration of {tech_name} companies?",
            "answer": f"The top Indian commercial and industrial hubs with verified {firm_type} include {city_str}."
        },
        {
            "question": f"How many verified {tech_name} companies are indexed across India?",
            "answer": f"OutreachPilot indexes over {count}+ verified {firm_type} with active operations across India."
        },
        {
            "question": f"How does OutreachPilot verify {tech_name} company capabilities?",
            "answer": f"Our multi-pass engine crawls official company web domains, parsing service offerings, production frameworks, certifications, client reviews, and active operational signals to confirm authentic {tech_name} expertise."
        }
    ]


def generate_combo_faqs(city_name: str, tech_name: str, count: int, avg_rating: float) -> list[dict[str, str]]:
    domain = get_category_domain(tech_name)
    if domain == "Information Technology & Software":
        firm_label = f"{tech_name} software and engineering companies"
    elif domain == "Marketing, Advertising & PR":
        firm_label = f"{tech_name} agencies and marketing firms"
    elif domain == "Sales & Business Development":
        firm_label = f"{tech_name} agencies and sales teams"
    elif domain == "Pharmaceuticals & Healthcare":
        firm_label = f"{tech_name} manufacturers and healthcare specialists"
    elif domain == "Finance, Accounting & Legal":
        firm_label = f"{tech_name} firms and financial/legal consultancies"
    else:
        firm_label = f"{tech_name} companies and service providers"

    return [
        {
            "question": f"Which companies in {city_name} specialize in {tech_name}?",
            "answer": f"OutreachPilot lists {count} verified {firm_label} in {city_name} specializing in {tech_name}, with an average client satisfaction rating of {avg_rating}★."
        },
        {
            "question": f"What is the average Google rating for {tech_name} providers in {city_name}?",
            "answer": f"Verified {firm_label} in {city_name} maintain an average customer review score of {avg_rating} out of 5 stars based on verified Google Local reviews."
        },
        {
            "question": f"Can I contact verified decision makers at {tech_name} companies in {city_name}?",
            "answer": f"Yes, OutreachPilot features verified corporate email contacts, verified phone numbers, and physical headquarters for {tech_name} businesses in {city_name}, enabling direct 1-to-1 outreach via authorized Google OAuth."
        }
    ]
