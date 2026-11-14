"""
OutreachPilot - Freelancer Portfolio & Training Institute Lead Auditor / Cleaner
File: identify_non_company_leads.py

Identifies non-company websites mistakenly scraped as target B2B companies:
  1. FREELANCER_PORTFOLIO  (e.g., https://amrutratnani.com/) - individual developers,
     designers, marketers, and personal CV/resume/Fiverr/Upwork portfolio pages.
  2. TRAINING_INSTITUTE    (e.g., https://akashsir.com/)    - IT/marketing coaching
     centers, academies, classes, tutorials, bootcamps, colleges, and schools.

Safety-First Design:
  - By default, runs in 100% READ-ONLY audit mode and exports CSV files with full
    evidence (`matched_reasons`, `score`, `confidence`, outreach safety counts, and
    `action_approved`) for review.
  - Database modifications (hard delete or reversible soft-invalid marking) ONLY run
    when explicitly invoked with `--delete-from-csv` + `--confirm-delete` (or
    `--mark-invalid-from-csv` + `--confirm-invalidate`).

Examples:
  # 1. Recommended: Fast DB scan + live HTTP verification of priority candidates -> CSVs
  python identify_non_company_leads.py

  # 2. Deep scan including bare free-hosted sites (.vercel.app, .netlify.app, .grexa.site, etc.)
  python identify_non_company_leads.py --verify-scope all

  # 3. Ultra-fast DB + AI profile scan only (no live HTTP requests)
  python identify_non_company_leads.py --db-only

  # 4. Inspect specific domains directly
  python identify_non_company_leads.py --domains amrutratnani.com,akashsir.com

  # 5. Preview deletion from reviewed CSV without touching the database
  python identify_non_company_leads.py --delete-from-csv var/non_company_audit/all_flagged_non_companies.csv --dry-run

  # 6. Explicitly delete approved rows (`action_approved == YES`) after review
  python identify_non_company_leads.py --delete-from-csv var/non_company_audit/all_flagged_non_companies.csv --confirm-delete

  # 7. Reversible alternative: mark is_invalid=TRUE instead of hard delete
  python identify_non_company_leads.py --mark-invalid-from-csv var/non_company_audit/all_flagged_non_companies.csv --confirm-invalidate
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import func

from clean_db_company_names import clean_company_name
from config import is_safe_public_url
from db import (
    ColdPitch,
    Company,
    CompanyEmail,
    CompanyProfile,
    OutreachLog,
    SessionLocal,
    init_db,
)

DEFAULT_OUT_DIR = Path("var") / "non_company_audit"

# ---------------------------------------------------------------------------
# Signal Definitions & False-Positive Guards
# ---------------------------------------------------------------------------

PORTFOLIO_HOST_SUFFIXES = (
    ".github.io",
    ".vercel.app",
    ".netlify.app",
    ".framer.website",
    ".lovable.app",
    ".my.canva.site",
    ".myportfolio.com",
    ".carrd.co",
    ".about.me",
    ".ai.studio",
    ".chatgpt.site",
    ".free.nf",
    ".rf.gd",
    ".site123.me",
    ".weebly.com",
    ".blogspot.com",
    ".wordpress.com",
    ".wixsite.com",
    ".webflow.io",
    ".grexa.site",
    ".localo.site",
)

EDU_HOST_SUFFIXES = (
    ".edu",
    ".edu.in",
    ".ac.in",
    ".training",
    ".academy",
    ".school",
    ".college",
    ".teachable.com",
    ".thinkific.com",
    ".podia.com",
    ".graphy.com",
    ".classplusapp.com",
)

CORP_LEGAL_RE = re.compile(
    r"\b(?:pvt\.?|ltd\.?|private\s+limited|limited|llp|inc\.?|llc|corp\.?|corporation|gmbh)\b",
    re.I,
)

AGENCY_NOUNS = {
    "pvt", "ltd", "private", "limited", "llp", "inc", "llc", "corp", "corporation",
    "tech", "technologies", "technology", "solutions", "solution", "systems", "system",
    "infotech", "soft", "software", "digital", "media", "marketing", "agency", "agencies",
    "studio", "studios", "labs", "lab", "consultancy", "consulting", "consultants",
    "consultant", "services", "service", "group", "associates", "works", "work",
    "enterprises", "enterprise", "ventures", "venture", "global", "india", "international",
    "networks", "network", "cloud", "data", "apps", "app", "web", "code", "coders",
    "dev", "devs", "design", "designs", "creative", "creatives", "communications",
    "branding", "ads", "seo", "analytics", "pharma", "health", "healthcare", "medical",
    "dental", "clinic", "hospital", "care", "finance", "financial", "capital", "wealth",
    "advisors", "advisers", "tax", "legal", "law", "realty", "estate", "properties",
    "property", "builders", "infra", "logistics", "cargo", "freight", "industries",
    "industrial", "manufacturing", "exports", "imports", "traders", "staffing",
    "recruitment", "manpower", "hr", "bpo", "innovations", "interactive", "dynamics",
    "partners", "partnership", "holdings", "hub", "house", "box", "craft", "crafts",
    "minds", "logic", "byte", "bytes", "pixel", "pixels", "spark", "forge", "wave",
    "edge", "core", "peak", "matrix", "nexus", "ai", "foundation", "trust", "travel",
    "tours", "events", "caterers", "graphics", "printers", "advertising", "pay",
    "ideas", "spaces", "space", "world", "zone", "planet", "online", "express",
    "portal", "news", "samachar", "breaking", "seva", "store", "stores", "shop",
    "bazar", "mart", "hubs", "wings", "catalyst", "mantra", "experts", "home",
    "abroad", "visa", "immigration", "study", "career", "careers", "job", "jobs",
    "resorts", "hotels", "foods", "agro", "energy", "solar", "power", "robotics",
    "automation", "security", "cyber", "ecommerce", "retail", "ventures", "sir",
    "academy", "institute", "school", "college", "classes", "coaching", "training",
    "tutorials", "tuition", "education", "varsity", "campus", "gurukul", "mentor",
    "mentors", "edtech", "learning", "learn", "skill", "skills", "infomatics",
    "developer", "developers", "designer", "designers", "marketer", "marketers",
    "writer", "writers", "community", "society", "digitech", "technovation",
    "resumes", "pioneer", "iim", "iit", "nit", "iiit", "iiitdm", "srmu", "ignou",
    "ahmedabad", "mumbai", "delhi", "pune", "chennai", "bangalore", "bengaluru",
    "hyderabad", "kolkata", "surat", "vadodara", "rajkot", "indore", "jaipur",
    "lucknow", "kanpur", "nagpur", "kochi", "coimbatore", "madurai", "noida",
    "gurgaon", "gurugram", "chandigarh", "ranchi", "patna", "bhopal", "ludhiana",
    "jalandhar", "nashik", "varanasi", "visakhapatnam", "trivandrum", "erode",
    "thrissur", "panaji", "guwahati", "faridabad", "kerala", "gujarat", "maharashtra",
}

COMMON_ENGLISH_BRAND_WORDS = {
    "make", "great", "best", "first", "next", "new", "smart", "fast", "quick",
    "bright", "blue", "green", "red", "white", "black", "gold", "silver", "royal",
    "prime", "pro", "top", "super", "mega", "ultra", "apex", "zenith", "nova",
    "neon", "aura", "vibe", "pulse", "spark", "flow", "grow", "rise", "scale",
    "boost", "click", "lead", "brand", "voice", "verse", "uncut", "cheap",
    "cheapest", "advance", "advance", "right", "real", "true", "pure", "clean",
    "open", "free", "easy", "simple", "modern", "future", "vision", "dream",
    "hope", "star", "sun", "moon", "sky", "ocean", "mountain", "valley", "city",
    "urban", "metro", "local", "national", "united", "all", "one", "two", "three",
    "four", "five", "seven", "ten", "hundred", "thousand", "million", "alpha",
    "beta", "delta", "omega", "sigma", "gamma", "omni", "multi", "poly", "meta",
    "micro", "macro", "nano", "hyper", "cyber", "info", "net", "link", "sync",
    "desk", "base", "dock", "nest", "spot", "point", "line", "path", "way",
    "bridge", "gate", "port", "lane", "street", "road", "park", "plaza", "tower",
    "palace", "crown", "king", "queen", "lion", "tiger", "eagle", "hawk", "wolf",
    "fox", "bear", "owl", "peacock", "lotus", "rose", "pearl", "diamond", "ruby",
    "amber", "jade", "indigo", "crimson", "coral", "ivory", "velvet", "silk",
    "metal", "iron", "steel", "stone", "rock", "wood", "timber", "paper", "ink",
    "pen", "brush", "frame", "lens", "focus", "angle", "view", "sight", "scope",
    "trend", "trends", "style", "mode", "form", "shape", "line", "grid", "node",
    "stack", "layer", "block", "chain", "loop", "wire", "mesh", "pipe", "gear",
    "wheel", "engine", "motor", "drive", "pilot", "crew", "squad", "guild", "club",
    "forum", "circle", "ring", "band", "crew", "team", "unit", "force", "guard",
    "shield", "armor", "sword", "arrow", "spear", "target", "goal", "aim", "win",
    "winner", "victory", "triumph", "pride", "honor", "trust", "faith", "grace",
    "bliss", "joy", "smile", "happy", "lucky", "magic", "wonder", "miracle",
    "secret", "key", "lock", "vault", "safe", "secure", "clear", "solid", "firm",
    "strong", "bold", "brave", "wild", "calm", "wise", "keen", "sharp", "swift",
    "rapid", "flash", "instant", "direct", "exact", "fine", "good", "well", "rich",
    "full", "deep", "high", "tall", "wide", "broad", "vast", "grand", "big",
    "huge", "giant", "tiny", "mini", "short", "long", "young", "fresh", "sweet",
    "warm", "cool", "cold", "hot", "light", "dark", "soft", "hard", "rough",
    "smooth", "flat", "round", "square", "level", "plain", "fair", "just", "kind",
    "real", "able", "ready", "set", "start", "begin", "build", "create", "make",
    "made", "craft", "hand", "mind", "brain", "heart", "soul", "spirit", "life",
    "live", "living", "earth", "land", "world", "globe", "space", "air", "wind",
    "fire", "flame", "water", "rain", "cloud", "storm", "snow", "ice", "tree",
    "leaf", "root", "seed", "fruit", "bloom", "garden", "field", "farm", "harvest",
}

PERSONAL_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "yahoo.co.in", "yahoo.in", "hotmail.com",
    "outlook.com", "live.com", "rediffmail.com", "proton.me", "protonmail.com",
    "icloud.com",
}

# --- TRAINING INSTITUTE PATTERNS ---
INSTITUTE_STRONG_RE = re.compile(
    r"\b(?:"
    r"training\s+(?:institute|cent(?:er|re)|academy|hub|program)"
    r"|computer\s+(?:institute|classes|cent(?:er|re)|education|training)"
    r"|coaching\s+(?:institute|classes|cent(?:er|re)|academy)"
    r"|it\s+(?:training|academy|institute|courses?)"
    r"|software\s+training(?:\s+institute)?"
    r"|(?:coding|ai|data\s+science|full\s*stack|python|java|web)\s+(?:bootcamp|training|courses?|classes)"
    r"|tuition\s+(?:classes|cent(?:er|re)|agency|academy)|home\s+tuitions?"
    r"|polytechnic|university|finishing\s+school"
    r"|students?\s+trained|placement\s+(?:support|assistance)"
    r"|final\s+(?:year|semester)\s+(?:live\s+)?project\s+training"
    r"|offline\s+(?:classroom\s+)?training|job[- ]oriented\s+(?:courses?|training)"
    r")\b",
    re.I,
)

INSTITUTE_MOD_RE = re.compile(
    r"\b(?:academy|institute|bootcamp|classes|tutorials?|coaching|tuitions?|varsity|pathshala|gurukul|shiksha|vidyalaya)\b",
    re.I,
)

INSTITUTE_DOMAIN_TOKEN_RE = re.compile(
    r"(?:academy|institute|classes|coaching|tutorial|training|bootcamp|varsity|tuition|course|edutech|edtech|learners|placement|exam|testprep)",
    re.I,
)

# Teacher "Sir" heuristic (avoids "Dholera SIR", "SIR FINANCIAL", and words like "siraka"/"siren")
SIR_NAME_RE = re.compile(r"\b[A-Z][a-z]{2,15}\s+[Ss]ir\b|(?:\bby\s+[A-Z][a-z]{2,15}\s+sir\b)", re.UNICODE)
SIR_DOMAIN_RE = re.compile(r"^[a-z]{3,15}sir$", re.I)

# False-positive guards for institutes
INSTITUTE_FP_GUARD_RE = re.compile(
    r"\b(?:dholera\s+sir|special\s+investment\s+region|sir\s+financial)\b",
    re.I,
)

# --- FREELANCER / PORTFOLIO PATTERNS ---
FREELANCER_EXPLICIT_RE = re.compile(
    r"\b(?:freelancer|freelancing|freelance\s+(?:developer|designer|marketer|seo|writer|consultant|engineer|web|ui|ux|php|react|node|full[- ]?stack|digital))\b",
    re.I,
)

PERSONAL_PORTFOLIO_RE = re.compile(
    r"\b(?:personal\s+portfolio|developer\s+portfolio|design(?:er)?\s+portfolio|my\s+portfolio|seo\s+portfolio|content\s+portfolio|my\s+resume|download\s+(?:my\s+)?(?:resume|cv)|curriculum\s+vitae)\b",
    re.I,
)

PORTFOLIO_DOMAIN_WORD_RE = re.compile(
    r"(?:portfolio|freelanc(?:er|e)|(?:^|[-_0-9])resume(?:s)?(?:$|[-_0-9]))",
    re.I,
)

FINANCE_OR_CORP_PORTFOLIO_GUARD_RE = re.compile(
    r"\b(?:portfolio\s+management|asset\s+portfolio|investment\s+portfolio|wealth\s+management|pms\b|mutual\s+fund|client\s+portfolio|our\s+portfolio|project\s+portfolio|view\s+portfolio|work\s+portfolio|resume\s+writing|cv\s+writer|resume\s+services?)\b",
    re.I,
)

AGENCY_SELF_DESC_RE = re.compile(
    r"\b(?:we\s+are\s+a\s+(?:leading|full[- ]service|digital|software|web)|our\s+team\s+of|dedicated\s+team|private\s+limited|pvt\.?\s*ltd|board\s+of\s+directors|career\s+openings|open\s+positions)\b",
    re.I,
)

# Live HTML signals
LIVE_FREELANCE_MARKET_RE = re.compile(
    r"(?:hire\s+me\s+on\s+(?:fiverr|upwork|freelancer|toptal)|fiverr\.com/|upwork\.com/freelancers/|freelancer\.com/u/|available\s+for\s+freelance|full[- ]?time\s+(?:professional\s+)?(?:ai\s+)?freelancer|freelance\s+(?:web|app|full[- ]?stack|ai|seo|digital)\s+(?:developer|engineer|designer|consultant))",
    re.I,
)

LIVE_FIRST_PERSON_BIO_RE = re.compile(
    r"(?:\b(?:hello|hi|hey)[,!]?\s+i['’]?m\b|\bi\s+am\s+a\s+(?:freelance|full[- ]?stack|web|ai|software|ui/ux|digital)\b|\bmy\s+resume\b|\bdownload\s+(?:my\s+)?(?:cv|resume)\b|\bexplore\s+my\b|\bmy\s+(?:special\s+)?(?:services?|skills?|work\s+experience)\b|\bdrop\s+(?:me\s+)?a\s+mail\b|\babout\s+me\b)",
    re.I,
)

LIVE_INSTITUTE_TITLE_OR_HERO_RE = re.compile(
    r"(?:training\s+institute|coaching\s+(?:institute|classes|cent(?:er|re))|computer\s+(?:classes|institute|training)|it\s+training\s+(?:in|company|institute)|final\s+year\s+(?:live\s+)?project\s+training|internship\s+training\s+in|book\s+(?:a|your)\s+free\s+demo|start\s+your\s+it\s+career\s+with)",
    re.I,
)

LIVE_INSTITUTE_BODY_RE = re.compile(
    r"\b(?:students?\s+trained|new\s+batch(?:es)?\s+(?:start|starting)|upcoming\s+batch(?:es)?|batch\s+timings?|find\s+courses|all\s+courses|featured\s+(?:it\s+)?courses|course\s+(?:fees?|duration|syllabus|curriculum|certification)|enroll\s+now|admission\s+open|100%\s+(?:job|placement)\s+(?:support|assistance|guarantee)|job[- ]oriented\s+(?:course|training)|classroom\s+training|online\s+&\s+offline\s+(?:training|classes|programs)|faculty\s+training|weekend\s+(?:batch|training)|crash\s+course)\b",
    re.I,
)

LIVE_INSTITUTE_HREF_RE = re.compile(
    r"/(?:courses?|tutorials?|free-courses|batches?|syllabus|curriculum|student-placement|student-review|admissions?|internship-in-|training-in-|demo-class)",
    re.I,
)

LIVE_GENUINE_COMPANY_RE = re.compile(
    r"\b(?:our\s+team|we['’]?re\s+hiring|join\s+our\s+team|open\s+positions|current\s+openings|private\s+limited|pvt\.?\s*ltd\.?|llp|cin\s*:|gstin\s*:|case\s+studies|enterprise\s+clients)\b",
    re.I,
)


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class CompanyRecord:
    id: int
    name: str
    domain: str
    website_url: str
    search_keyword: str
    city: str
    is_enriched: bool
    is_invalid: bool
    profile_industry: str
    profile_summary: str
    profile_detailed: str
    profile_services: str
    emails: list[str] = field(default_factory=list)
    pitch_count: int = 0
    outreach_sent_count: int = 0


@dataclass
class AuditFinding:
    record: CompanyRecord
    inst_score: int = 0
    free_score: int = 0
    inst_reasons: list[str] = field(default_factory=list)
    free_reasons: list[str] = field(default_factory=list)
    needs_live_verify: bool = False
    verify_trigger: str = ""
    live_checked: bool = False
    live_status: str = ""
    live_title: str = ""
    detection_source: str = "DB_RULES"

    @property
    def category_flag(self) -> str:
        has_inst = self.inst_score >= 4
        has_free = self.free_score >= 4
        if has_inst and has_free:
            return "BOTH"
        if has_inst:
            return "TRAINING_INSTITUTE"
        if has_free:
            return "FREELANCER_PORTFOLIO"
        return "NONE"

    @property
    def max_score(self) -> int:
        return max(self.inst_score, self.free_score)

    @property
    def confidence(self) -> str:
        # High confidence requires >= 6 points or strong live confirmation
        s = self.max_score
        if s >= 6:
            return "HIGH"
        if s >= 4:
            return "MEDIUM"
        return "LOW"

    @property
    def all_reasons(self) -> list[str]:
        return self.inst_reasons + self.free_reasons


# ---------------------------------------------------------------------------
# Stage 1: Fast DB & AI-Profile Classifier
# ---------------------------------------------------------------------------

def looks_like_person_name_for_domain(raw_name: str, domain: str) -> bool:
    """
    Detects structurally ambiguous solo-person names matching their domain
    (e.g., 'Amrut Ratnani' <-> 'amrutratnani.com') without false-triggering
    on common English brand phrases like 'Neon Ideas' or 'Wilson Wings'.
    """
    cleaned = clean_company_name(raw_name, domain) or raw_name or ""
    # Strip trailing location qualifiers or bracket notes
    cleaned = re.sub(r"\([^)]*\)", "", cleaned).strip()
    tokens = re.findall(r"[A-Za-z]+", cleaned)
    if not (2 <= len(tokens) <= 3):
        return False
    if any(len(t) < 2 for t in tokens):
        return False

    low_tokens = [t.lower() for t in tokens]
    if set(low_tokens) & AGENCY_NOUNS:
        return False
    # Reject short all-caps acronyms (e.g., IIM, UE, ML, IT) which denote institutions/brands
    if any(t.isupper() and len(t) <= 5 for t in tokens):
        return False
    # Reject generic English verb/noun/process suffixes (keep Indian names like Vyas/Paras/Srinivas intact)
    if any(
        lt.endswith(("ing", "tion", "sion", "ment", "ness", "ity", "ics", "ology", "ies", "crafts", "ideas", "wings"))
        for lt in low_tokens
    ):
        return False
    # If tokens are common English brand words ("Neon Ideas", "Make Pay"), skip
    if all(t in COMMON_ENGLISH_BRAND_WORDS for t in low_tokens) or (low_tokens[0] in COMMON_ENGLISH_BRAND_WORDS and len(tokens) == 2):
        return False
    # If even 1 token is a common generic adjective/noun alongside short name, keep bar slightly stricter:
    # Require >= 8 compacted chars and exact/direct containment inside domain root
    d_root = re.sub(r"[^a-z0-9]", "", (domain or "").lower().split(".")[0])
    name_compact = "".join(low_tokens)
    if len(name_compact) < 8 or not d_root:
        return False
    if name_compact == d_root:
        return True
    # Also match if domain has minor prefix/suffix like hireamrutratnani / amrutratnanidev
    if len(name_compact) >= 10 and name_compact in d_root and (len(d_root) - len(name_compact) <= 6):
        return True
    return False


def evaluate_db_signals(rec: CompanyRecord) -> AuditFinding:
    f = AuditFinding(record=rec)
    raw_name = (rec.name or "").strip()
    clean_nm = clean_company_name(raw_name, rec.domain) or raw_name
    domain = (rec.domain or "").strip().lower()
    d_root = domain.split(".")[0] if "." in domain else domain
    kw = (rec.search_keyword or "").strip()
    ind = (rec.profile_industry or "").strip()
    summ = (rec.profile_summary or "").strip()
    det = (rec.profile_detailed or "").strip()
    srv = (rec.profile_services or "").strip()

    has_corp_suffix = bool(CORP_LEGAL_RE.search(raw_name) or CORP_LEGAL_RE.search(summ))
    has_only_personal_email = bool(rec.emails) and all(
        e.split("@")[-1] in PERSONAL_EMAIL_DOMAINS for e in rec.emails if "@" in e
    )
    has_hr_or_careers_email = any(
        e.split("@")[0].startswith(("hr", "career", "careers", "recruit", "jobs", "talent"))
        for e in rec.emails if "@" in e
    )

    # ---------------- A. TRAINING INSTITUTE SIGNALS ----------------
    fp_sir = bool(INSTITUTE_FP_GUARD_RE.search(raw_name))

    if any(domain.endswith(sfx) for sfx in EDU_HOST_SUFFIXES):
        f.inst_score += 6
        f.inst_reasons.append(f"db_edu_domain_suffix:{domain}")

    if INSTITUTE_STRONG_RE.search(raw_name):
        f.inst_score += 5
        f.inst_reasons.append(f"db_name_strong_edu:{clean_nm[:60]}")
    elif INSTITUTE_MOD_RE.search(raw_name) and not fp_sir:
        # Check for campus false positive handled separately (campus excluded from MOD_RE)
        f.inst_score += 4
        f.inst_reasons.append(f"db_name_edu_kw:{clean_nm[:60]}")

    if (SIR_NAME_RE.search(raw_name) or SIR_DOMAIN_RE.match(d_root)) and not fp_sir:
        f.inst_score += 5
        f.inst_reasons.append(f"db_teacher_sir_pattern:{raw_name[:50]}|{domain}")

    if INSTITUTE_DOMAIN_TOKEN_RE.search(d_root):
        f.inst_score += 3
        f.inst_reasons.append(f"db_domain_edu_token:{d_root}")

    if re.search(r"\b(?:school|college)\b", raw_name, re.I):
        if re.search(
            r"\b(?:high\s+school|public\s+school|polytechnic|nursing\s+college|engineering\s+college|medical\s+college|school\s+of|coding\s+school|hacking\s+school|digital\s+school|design\s+school)\b",
            raw_name,
            re.I,
        ):
            f.inst_score += 5
            f.inst_reasons.append(f"db_school_college:{clean_nm[:50]}")
        else:
            f.inst_score += 3
            f.inst_reasons.append(f"db_name_school_or_college:{clean_nm[:50]}")

    # Profile AI intelligence checks (only for enriched rows)
    if rec.is_enriched or summ:
        profile_blob = f"{ind} | {summ} | {det}"
        if re.search(
            r"\bis\s+(?:a|an)\s+(?:leading\s+|top\s+|premier\s+|comprehensive\s+|online\s+|iso-certified\s+and\s+government-registered\s+)?(?:it|software|computer|coding|ai|digital\s+marketing)?\s*(?:training\s+institute|coaching\s+institute|coaching\s+cent(?:er|re)|ai\s+bootcamp|coding\s+bootcamp)\b",
            summ,
            re.I,
        ):
            f.inst_score += 6
            f.inst_reasons.append("db_profile_explicit_institute_summary")
            f.detection_source = "DB_PROFILE"
        elif INSTITUTE_STRONG_RE.search(profile_blob) or re.search(
            r"\b(?:it\s+training\s+company|software\s+training|courses\s+and\s+certifications|career-oriented\s+programs|hands-on\s+training\s+(?:using|with)|100%\s+offline\s+training)\b",
            profile_blob,
            re.I,
        ):
            f.inst_score += 5
            f.inst_reasons.append("db_profile_training_institute")
            f.detection_source = "DB_PROFILE"
        elif INSTITUTE_MOD_RE.search(ind):
            f.inst_score += 4
            f.inst_reasons.append(f"db_profile_edu_industry:{ind[:45]}")
            f.detection_source = "DB_PROFILE"

        # Counterweight if profile clearly says software dev company & only mentions training marginally
        if (
            f.inst_score > 0
            and "custom software" in ind.lower()
            and "training institute" not in profile_blob.lower()
            and "classes" not in profile_blob.lower()
            and "coaching" not in profile_blob.lower()
            and not re.search(r"\b(?:students?|bootcamp|courses?|academy)\b", summ.lower())
        ):
            f.inst_score -= 2
            f.inst_reasons.append("guard_corporate_it_profile(-2)")

    if has_corp_suffix and f.inst_score > 0:
        # e.g., Pvt Ltd training institutes DO exist ("Refactor Academy Pvt. Ltd."), mild counterweight
        f.inst_score -= 1
        f.inst_reasons.append("guard_corp_suffix_inst(-1)")

    # ---------------- B. FREELANCER / PORTFOLIO SIGNALS ----------------
    is_portfolio_host = any(domain.endswith(sfx) for sfx in PORTFOLIO_HOST_SUFFIXES)
    has_fin_or_corp_portfolio = bool(FINANCE_OR_CORP_PORTFOLIO_GUARD_RE.search(f"{raw_name} {summ}"))

    if FREELANCER_EXPLICIT_RE.search(raw_name):
        # Avoid false-positive agency named "FreelancerX" unless solo signals exist
        if "freelancerx" in raw_name.lower() and not is_portfolio_host:
            f.free_score += 2
            f.free_reasons.append("db_name_ambiguous_freelancerx")
        else:
            f.free_score += 5
            f.free_reasons.append(f"db_name_freelancer:{clean_nm[:60]}")

    if PORTFOLIO_DOMAIN_WORD_RE.search(d_root) and not has_fin_or_corp_portfolio:
        if "freelancerx" not in d_root:
            f.free_score += 4
            f.free_reasons.append(f"db_domain_portfolio_word:{d_root}")

    if PERSONAL_PORTFOLIO_RE.search(raw_name) and not has_fin_or_corp_portfolio:
        f.free_score += 4
        f.free_reasons.append(f"db_name_personal_portfolio:{clean_nm[:60]}")

    if is_portfolio_host:
        f.free_score += 2
        f.free_reasons.append(f"db_portfolio_host:{domain}")

    person_match = looks_like_person_name_for_domain(raw_name, domain)
    if person_match:
        f.free_score += 2
        f.free_reasons.append(f"db_person_name_matches_domain:{clean_nm}")

    # Web developer / designer individual title in DB name (e.g. "Pradyuman web developer")
    if (
        re.search(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\s+(?:web|app|php|laravel|react|seo|ui/?ux|graphic)?\s*(?:developer|designer|marketer)\b", clean_nm, re.I)
        and not has_corp_suffix
    ):
        role_pts = 3 if is_portfolio_host else 2
        f.free_score += role_pts
        f.free_reasons.append(f"db_person_role_title:{clean_nm}")

    if rec.is_enriched or summ:
        profile_blob = f"{ind} | {summ}"
        if FREELANCER_EXPLICIT_RE.search(profile_blob) or re.search(
            r"\b(?:freelance\s+(?:web|app|software|digital|seo|ai|hub)|personal\s+portfolio|solo\s+developer)\b",
            profile_blob,
            re.I,
        ):
            f.free_score += 5
            f.free_reasons.append("db_profile_freelancer")
            f.detection_source = "DB_PROFILE"
        elif person_match and re.search(
            r"^[A-Z][a-z]+\s+[A-Z][a-z]+\s+is\s+(?:a|an)\s+(?:web|ui/ux|full[- ]?stack|ai|software|freelance)",
            summ,
        ):
            f.free_score += 4
            f.free_reasons.append("db_profile_solo_person_bio")
            f.detection_source = "DB_PROFILE"

    if has_only_personal_email and f.free_score >= 2:
        f.free_score += 1
        f.free_reasons.append("db_personal_webmail")

    if has_corp_suffix and f.free_score > 0:
        f.free_score -= 5
        f.free_reasons.append("guard_corp_suffix_free(-5)")
    if has_hr_or_careers_email and f.free_score > 0:
        f.free_score -= 3
        f.free_reasons.append("guard_hr_careers_email(-3)")

    # ---------------- C. QUEUE AMBIGUOUS CANDIDATES FOR LIVE SITE CHECK ----------------
    # Un-enriched rows with partial signals (score 3-5), teacher Sir cues, OR
    # structural person-name==domain matches (like 'Amrut Ratnani' <-> amrutratnani.com).
    if not rec.is_enriched and not summ:
        if 3 <= f.max_score <= 5:
            f.needs_live_verify = True
            f.verify_trigger = f"partial_score({f.max_score})"
        elif person_match and is_portfolio_host:
            f.needs_live_verify = True
            f.verify_trigger = "person_portfolio_host"
        elif person_match:
            f.needs_live_verify = True
            f.verify_trigger = "person_name_domain"
        elif any(r.startswith("db_person_role_title:") for r in f.free_reasons):
            f.needs_live_verify = True
            f.verify_trigger = "person_role_title"
        elif f.inst_score >= 4 and has_corp_suffix:
            f.needs_live_verify = True
            f.verify_trigger = "inst_with_corp_suffix"
        elif ("sir" in raw_name.lower() or SIR_DOMAIN_RE.match(d_root)) and not fp_sir:
            f.needs_live_verify = True
            f.verify_trigger = "sir_pattern"
        elif 2 <= f.max_score < 3:
            # Weak score=2 hits (e.g., bare .vercel.app / .grexa.site) only run in `--verify-scope all`
            f.verify_trigger = "weak_host_only"

    return f


# ---------------------------------------------------------------------------
# Stage 2: Fast Concurrent Live Website Verification (HTML/Links, No LLM)
# ---------------------------------------------------------------------------

def _analyze_live_html(html: str, f: AuditFinding) -> None:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    f.live_title = title[:160]

    meta_parts = [title]
    for m in soup.find_all("meta"):
        prop = (m.get("name") or m.get("property") or "").lower()
        if prop in ("description", "keywords", "og:title", "og:description"):
            content = (m.get("content") or "").strip()
            if content:
                meta_parts.append(content)
    meta_blob = " | ".join(meta_parts)

    hrefs: list[str] = []
    for a in soup.find_all("a", href=True):
        hrefs.append((a.get("href") or "").strip())
    href_blob = " ".join(hrefs)

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    body_text = " ".join(soup.get_text(" ", strip=True).split())[:8000]
    full_blob = f"{meta_blob} || {body_text}"

    has_gen_company = bool(LIVE_GENUINE_COMPANY_RE.search(full_blob))

    # --- Evaluate Live TRAINING_INSTITUTE Evidence ---
    inst_delta = 0
    if LIVE_INSTITUTE_TITLE_OR_HERO_RE.search(meta_blob):
        inst_delta += 5
        f.inst_reasons.append("live_meta_training_institute")
    elif LIVE_INSTITUTE_TITLE_OR_HERO_RE.search(body_text[:2500]):
        inst_delta += 4
        f.inst_reasons.append("live_hero_training_institute")

    course_href_hits = set(LIVE_INSTITUTE_HREF_RE.findall(href_blob.lower()))
    if len(course_href_hits) >= 2:
        pts = min(5, 1 + len(course_href_hits))
        inst_delta += pts
        f.inst_reasons.append(f"live_course_links({','.join(sorted(course_href_hits)[:4])})")
    elif len(course_href_hits) == 1:
        inst_delta += 2
        f.inst_reasons.append(f"live_course_link({next(iter(course_href_hits))})")

    body_edu_hits = {m.lower() for m in LIVE_INSTITUTE_BODY_RE.findall(body_text)}
    if body_edu_hits:
        pts = min(6, len(body_edu_hits) * 2)
        inst_delta += pts
        f.inst_reasons.append(f"live_edu_phrases({len(body_edu_hits)}:{','.join(sorted(body_edu_hits)[:4])})")

    if inst_delta == 0 and has_gen_company and f.inst_score > 0:
        f.inst_score -= 2
        f.inst_reasons.append("live_guard_no_edu_cues_real_company(-2)")
    else:
        f.inst_score += inst_delta

    # --- Evaluate Live FREELANCER_PORTFOLIO Evidence ---
    free_delta = 0
    if LIVE_FREELANCE_MARKET_RE.search(full_blob) or any(
        d in href_blob.lower() for d in ("fiverr.com/", "upwork.com/freelancers/", "freelancer.com/u/")
    ):
        free_delta += 6
        f.free_reasons.append("live_freelance_marketplace_or_bio")

    bio_hits = {m.lower() for m in LIVE_FIRST_PERSON_BIO_RE.findall(full_blob)}
    if len(bio_hits) >= 2:
        pts = min(6, len(bio_hits) * 2)
        free_delta += pts
        f.free_reasons.append(f"live_first_person_portfolio({len(bio_hits)}:{','.join(sorted(bio_hits)[:4])})")
    elif len(bio_hits) == 1:
        free_delta += 2
        f.free_reasons.append(f"live_first_person_cue({next(iter(bio_hits))})")

    if PERSONAL_PORTFOLIO_RE.search(meta_blob) and not FINANCE_OR_CORP_PORTFOLIO_GUARD_RE.search(meta_blob):
        free_delta += 4
        f.free_reasons.append("live_meta_personal_portfolio")

    if free_delta >= 2 and not has_gen_company and not CORP_LEGAL_RE.search(full_blob[:3000]):
        free_delta += 1
        f.free_reasons.append("live_no_corp_or_hiring_structure(+1)")
    elif has_gen_company and free_delta < 5:
        f.free_score -= 3
        f.free_reasons.append("live_guard_corp_team_present(-3)")

    f.free_score += free_delta

    if inst_delta > 0 or free_delta > 0:
        if any(r.startswith("db_") for r in f.all_reasons):
            f.detection_source = "DB+LIVE"
        else:
            f.detection_source = "LIVE_WEBSITE"


def verify_candidates_live(
    findings: list[AuditFinding],
    concurrency: int = 50,
    timeout_sec: float = 7.0,
) -> None:
    """Fetches candidate sites concurrently on worker threads so DNS lookups never stall an event loop."""
    targets = [f for f in findings if f.needs_live_verify]
    if not targets:
        return

    print(
        f"[Stage 2] Verifying {len(targets)} candidate websites live (concurrency={concurrency}, timeout={timeout_sec}s)...",
        flush=True,
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    timeout = httpx.Timeout(timeout_sec, connect=4.5, read=timeout_sec)
    limits = httpx.Limits(max_connections=4, max_keepalive_connections=2)
    thread_local = threading.local()
    clients_lock = threading.Lock()
    created_clients: list[httpx.Client] = []

    def get_client() -> httpx.Client:
        client = getattr(thread_local, "client", None)
        if client is None:
            client = httpx.Client(
                headers=headers,
                limits=limits,
                timeout=timeout,
                follow_redirects=True,
                verify=False,
            )
            thread_local.client = client
            with clients_lock:
                created_clients.append(client)
        return client

    def check_one(f: AuditFinding) -> None:
        rec = f.record
        raw_url = (rec.website_url or "").strip()
        urls: list[str] = []
        if raw_url.startswith(("http://", "https://")):
            urls.append(raw_url)
        if rec.domain:
            naked = f"https://{rec.domain}"
            if naked not in urls:
                urls.append(naked)
            if not raw_url:
                www = f"https://www.{rec.domain}"
                if www not in urls:
                    urls.append(www)
        urls = urls[:2]
        if not urls:
            return

        client = get_client()
        f.live_checked = True
        got_http = False
        for url in urls:
            if not is_safe_public_url(url):
                if not f.live_status:
                    f.live_status = "BLOCKED_UNSAFE_URL"
                continue
            try:
                res = client.get(url)
                got_http = True
                f.live_status = str(res.status_code)
                ctype = (res.headers.get("content-type") or "").lower()
                if res.status_code == 200 and res.text and ("html" in ctype or not ctype):
                    _analyze_live_html(res.text[:300_000], f)
                    break
            except Exception as exc:
                if not got_http:
                    f.live_status = f"ERR:{type(exc).__name__}"

    completed = 0
    t0 = time.time()
    try:
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            futures = [pool.submit(check_one, f) for f in targets]
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception:
                    pass
                completed += 1
                if completed % 250 == 0 or completed == len(targets):
                    print(
                        f"  [Live Verify] {completed}/{len(targets)} checked in {time.time() - t0:.1f}s...",
                        flush=True,
                    )
    finally:
        for client in created_clients:
            try:
                client.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Database Loader & CSV Export
# ---------------------------------------------------------------------------

def load_companies_from_db(
    target_domains: list[str] | None = None,
    include_invalid: bool = False,
) -> list[CompanyRecord]:
    init_db()
    db = SessionLocal()
    try:
        t0 = time.time()
        q = (
            db.query(
                Company.id,
                Company.name,
                Company.domain,
                Company.website_url,
                Company.search_keyword,
                Company.city,
                Company.is_enriched,
                Company.is_invalid,
                CompanyProfile.industry,
                CompanyProfile.summary_short,
                CompanyProfile.detailed_analysis,
                CompanyProfile.services,
            )
            .outerjoin(CompanyProfile, CompanyProfile.company_id == Company.id)
        )
        if target_domains:
            norm_doms = [d.strip().lower().replace("www.", "") for d in target_domains if d.strip()]
            q = q.filter(func.lower(Company.domain).in_(norm_doms))
        elif not include_invalid:
            q = q.filter(Company.is_invalid.is_(False))

        company_rows = q.order_by(Company.id.asc()).all()
        company_ids = [r[0] for r in company_rows]

        emails_map: dict[int, list[str]] = defaultdict(list)
        pitch_counts: dict[int, int] = {}
        log_counts: dict[int, int] = {}

        if target_domains and company_ids:
            for cid, em in db.query(CompanyEmail.company_id, CompanyEmail.email_address).filter(CompanyEmail.company_id.in_(company_ids)).all():
                emails_map[cid].append(em)
            for cid, cnt in db.query(ColdPitch.company_id, func.count(ColdPitch.id)).filter(ColdPitch.company_id.in_(company_ids)).group_by(ColdPitch.company_id).all():
                pitch_counts[cid] = cnt
            for cid, cnt in db.query(OutreachLog.company_id, func.count(OutreachLog.id)).filter(OutreachLog.company_id.in_(company_ids)).group_by(OutreachLog.company_id).all():
                log_counts[cid] = cnt
        elif not target_domains:
            for cid, em in db.query(CompanyEmail.company_id, CompanyEmail.email_address).all():
                emails_map[cid].append(em)
            for cid, cnt in db.query(ColdPitch.company_id, func.count(ColdPitch.id)).group_by(ColdPitch.company_id).all():
                pitch_counts[cid] = cnt
            for cid, cnt in db.query(OutreachLog.company_id, func.count(OutreachLog.id)).group_by(OutreachLog.company_id).all():
                log_counts[cid] = cnt

        records = []
        for r in company_rows:
            cid = r[0]
            srv_str = json.dumps(r[11], ensure_ascii=False) if r[11] else ""
            records.append(
                CompanyRecord(
                    id=cid,
                    name=r[1] or "",
                    domain=r[2] or "",
                    website_url=r[3] or "",
                    search_keyword=r[4] or "",
                    city=r[5] or "",
                    is_enriched=bool(r[6]),
                    is_invalid=bool(r[7]),
                    profile_industry=r[8] or "",
                    profile_summary=r[9] or "",
                    profile_detailed=r[10] or "",
                    profile_services=srv_str,
                    emails=emails_map.get(cid, []),
                    pitch_count=pitch_counts.get(cid, 0),
                    outreach_sent_count=log_counts.get(cid, 0),
                )
            )
        print(f"[Stage 1] Loaded {len(records)} companies from PostgreSQL in {time.time() - t0:.2f}s.", flush=True)
        return records
    finally:
        db.close()


CSV_HEADERS = [
    "company_id",
    "name",
    "domain",
    "website_url",
    "category_flag",
    "confidence",
    "score",
    "detection_source",
    "matched_reasons",
    "search_keyword",
    "city",
    "is_enriched",
    "profile_industry",
    "email_count",
    "emails",
    "pitch_count",
    "outreach_sent_count",
    "live_status",
    "live_title",
    "action_approved",
]


def _finding_to_row(f: AuditFinding) -> dict[str, Any]:
    r = f.record
    return {
        "company_id": r.id,
        "name": r.name,
        "domain": r.domain,
        "website_url": r.website_url or f"https://{r.domain}",
        "category_flag": f.category_flag,
        "confidence": f.confidence,
        "score": f.max_score,
        "detection_source": f.detection_source,
        "matched_reasons": " ; ".join(f.all_reasons),
        "search_keyword": r.search_keyword,
        "city": r.city,
        "is_enriched": r.is_enriched,
        "profile_industry": r.profile_industry,
        "email_count": len(r.emails),
        "emails": ", ".join(r.emails[:5]),
        "pitch_count": r.pitch_count,
        "outreach_sent_count": r.outreach_sent_count,
        "live_status": f.live_status,
        "live_title": f.live_title,
        # Default YES for HIGH confidence with 0 sent emails; REVIEW for MEDIUM or previously contacted rows
        "action_approved": "REVIEW" if (r.outreach_sent_count > 0 or f.confidence != "HIGH") else "YES",
    }


def write_csv_reports(findings: list[AuditFinding], out_dir: Path, min_score: int = 4) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    flagged = [f for f in findings if f.max_score >= min_score and f.category_flag != "NONE"]
    conf_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    flagged.sort(key=lambda f: (conf_rank.get(f.confidence, 9), -f.max_score, f.category_flag, f.record.id))

    inst_rows = [_finding_to_row(f) for f in flagged if f.category_flag in ("TRAINING_INSTITUTE", "BOTH")]
    free_rows = [_finding_to_row(f) for f in flagged if f.category_flag in ("FREELANCER_PORTFOLIO", "BOTH")]
    all_rows = [_finding_to_row(f) for f in flagged]

    def _dump(filename: str, rows: list[dict[str, Any]]) -> str:
        path = out_dir / filename
        with open(path, "w", newline="", encoding="utf-8-sig") as fp:
            writer = csv.DictWriter(fp, fieldnames=CSV_HEADERS)
            writer.writeheader()
            writer.writerows(rows)
        return str(path.resolve())

    paths = {
        "all_csv": _dump("all_flagged_non_companies.csv", all_rows),
        "institutes_csv": _dump("training_institutes.csv", inst_rows),
        "freelancers_csv": _dump("freelancer_portfolios.csv", free_rows),
    }

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "total_scanned": len(findings),
        "total_flagged": len(all_rows),
        "by_category": dict(Counter(r["category_flag"] for r in all_rows)),
        "by_confidence": dict(Counter(r["confidence"] for r in all_rows)),
        "by_action_approved": dict(Counter(r["action_approved"] for r in all_rows)),
        "by_detection_source": dict(Counter(r["detection_source"] for r in all_rows)),
        "contacted_flagged_count": sum(1 for r in all_rows if r["outreach_sent_count"] > 0),
        "files": paths,
    }
    summary_path = out_dir / "audit_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    summary["summary_json"] = str(summary_path.resolve())
    return summary


# ---------------------------------------------------------------------------
# Explicit Deletion / Invalidation Mode
# ---------------------------------------------------------------------------

def _read_ids_from_csv(
    csv_path: Path,
    include_review: bool = False,
    min_confidence: str = "ANY",
) -> list[dict[str, Any]]:
    allowed_actions = {"YES", "Y", "TRUE", "1", "DELETE"}
    if include_review:
        allowed_actions.add("REVIEW")

    selected: list[dict[str, Any]] = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            action = (row.get("action_approved") or "YES").strip().upper()
            conf = (row.get("confidence") or "HIGH").strip().upper()
            if action not in allowed_actions:
                continue
            if min_confidence == "HIGH" and conf != "HIGH":
                continue
            try:
                cid = int(row["company_id"])
            except Exception:
                continue
            selected.append({
                "company_id": cid,
                "domain": row.get("domain", ""),
                "name": row.get("name", ""),
                "category_flag": row.get("category_flag", ""),
                "confidence": conf,
            })
    return selected


def apply_csv_cleanup(
    csv_path: Path,
    mode: str,
    dry_run: bool = False,
    include_review: bool = False,
    min_confidence: str = "ANY",
    include_contacted: bool = False,
    assume_yes: bool = False,
    batch_size: int = 500,
) -> None:
    if not csv_path.exists():
        print(f"ERROR: CSV file not found: {csv_path}")
        sys.exit(1)

    rows = _read_ids_from_csv(csv_path, include_review=include_review, min_confidence=min_confidence)
    if not rows:
        print(f"No eligible rows found in {csv_path} (check action_approved / --include-review / --min-confidence).")
        return

    init_db()
    db = SessionLocal()
    try:
        target_ids = [r["company_id"] for r in rows]
        existing_ids = {
            cid for (cid,) in db.query(Company.id).filter(Company.id.in_(target_ids)).all()
        }
        rows = [r for r in rows if r["company_id"] in existing_ids]
        target_ids = [r["company_id"] for r in rows]

        if not target_ids:
            print("All target IDs in CSV have already been removed from the database.")
            return

        # Contacted safety guard
        contacted_ids = {
            cid for (cid,) in db.query(OutreachLog.company_id).filter(OutreachLog.company_id.in_(target_ids)).distinct().all()
        }
        if contacted_ids and not include_contacted:
            print(f"[Safety Guard] Skipping {len(contacted_ids)} companies with existing OutreachLog history (use --include-contacted to override).")
            rows = [r for r in rows if r["company_id"] not in contacted_ids]
            target_ids = [r["company_id"] for r in rows]

        if not target_ids:
            print("No remaining companies to process after safety filtering.")
            return

        email_cnt = db.query(func.count(CompanyEmail.id)).filter(CompanyEmail.company_id.in_(target_ids)).scalar() or 0
        prof_cnt = db.query(func.count(CompanyProfile.id)).filter(CompanyProfile.company_id.in_(target_ids)).scalar() or 0
        pitch_cnt = db.query(func.count(ColdPitch.id)).filter(ColdPitch.company_id.in_(target_ids)).scalar() or 0
        log_cnt = db.query(func.count(OutreachLog.id)).filter(OutreachLog.company_id.in_(target_ids)).scalar() or 0

        cat_counts = Counter(r["category_flag"] for r in rows)
        print("\n" + "=" * 72)
        print(f" CLEANUP PLAN ({mode.upper()}) — {'DRY RUN (NO DB CHANGES)' if dry_run else 'LIVE EXECUTION'}")
        print("=" * 72)
        print(f" Target companies selected : {len(target_ids)}")
        print(f" Breakdown by category     : {dict(cat_counts)}")
        if mode == "delete":
            print(f" Cascading rows to delete  : emails={email_cnt}, profiles={prof_cnt}, pitches={pitch_cnt}, outreach_logs={log_cnt}")
        else:
            print(" Action                    : Soft-mark is_invalid=TRUE (reversible via /api/companies/bulk-restore)")
        print(" Sample rows:")
        for sample in rows[:10]:
            print(f"   - [{sample['company_id']}] {sample['name']} ({sample['domain']}) [{sample['category_flag']}/{sample['confidence']}]")

        if dry_run:
            print("\nDry run complete. Database was NOT modified.")
            return

        if not assume_yes:
            expected = f"{'DELETE' if mode == 'delete' else 'INVALIDATE'} {len(target_ids)} COMPANIES"
            typed = input(f"\nType `{expected}` exactly to proceed (anything else aborts): ").strip()
            if typed != expected:
                print("Aborted by user. Zero rows modified.")
                return

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        processed = 0
        reason_map = {r["company_id"]: f"Non-Company Audit ({r['category_flag']})" for r in rows}

        for i in range(0, len(target_ids), batch_size):
            batch = target_ids[i : i + batch_size]
            if mode == "delete":
                db.query(CompanyEmail).filter(CompanyEmail.company_id.in_(batch)).delete(synchronize_session=False)
                db.query(CompanyProfile).filter(CompanyProfile.company_id.in_(batch)).delete(synchronize_session=False)
                db.query(ColdPitch).filter(ColdPitch.company_id.in_(batch)).delete(synchronize_session=False)
                db.query(OutreachLog).filter(OutreachLog.company_id.in_(batch)).delete(synchronize_session=False)
                deleted = db.query(Company).filter(Company.id.in_(batch)).delete(synchronize_session=False)
                processed += deleted
            else:
                for cid in batch:
                    db.query(Company).filter(Company.id == cid).update(
                        {
                            Company.is_invalid: True,
                            Company.invalid_at: now,
                            Company.invalid_reason: reason_map[cid],
                        },
                        synchronize_session=False,
                    )
                processed += len(batch)
            db.commit()
            print(f"  Committed {processed}/{len(target_ids)}...", flush=True)

        remaining_valid = db.query(func.count(Company.id)).filter(Company.is_invalid.is_(False)).scalar()
        print(f"\nDone! {mode.upper()} applied to {processed} companies. Remaining valid companies in DB: {remaining_valid}")
        print("Note: The live web app filter cache refreshes automatically within its 300s TTL (or on server restart).")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Main CLI Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="OutreachPilot Non-Company Auditor & Cleaner (Freelancers & Training Institutes)")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Directory for output CSV reports")
    parser.add_argument("--db-only", action="store_true", help="Skip live HTTP verification (fast DB + AI profile rules only)")
    parser.add_argument("--domains", default="", help="Comma-separated specific domains to audit (e.g. amrutratnani.com,akashsir.com)")
    parser.add_argument("--include-invalid", action="store_true", help="Include companies already marked is_invalid=True")
    parser.add_argument("--min-score", type=int, default=4, help="Minimum score threshold for CSV export (default: 4)")
    parser.add_argument("--verify-limit", type=int, default=0, help="Max candidate sites to live-verify (0 = no cap)")
    parser.add_argument("--verify-scope", choices=["priority", "all"], default="priority", help="Which ambiguous candidates to verify live (priority=person/score>=3/sir; all=include bare free-host sites too)")
    parser.add_argument("--concurrency", type=int, default=40, help="Concurrent HTTP connections for live verification")

    # Explicit write/delete flags (never triggered unless explicitly passed)
    parser.add_argument("--delete-from-csv", default="", help="Path to reviewed CSV of companies to permanently delete")
    parser.add_argument("--confirm-delete", action="store_true", help="Required alongside --delete-from-csv to execute hard delete (unless --dry-run)")
    parser.add_argument("--mark-invalid-from-csv", default="", help="Path to reviewed CSV to softly mark is_invalid=True")
    parser.add_argument("--confirm-invalidate", action="store_true", help="Required alongside --mark-invalid-from-csv (unless --dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Preview deletion/invalidation counts without writing to DB")
    parser.add_argument("--include-review", action="store_true", help="Also include rows with action_approved=REVIEW (MEDIUM confidence)")
    parser.add_argument("--min-confidence", choices=["ANY", "HIGH"], default="ANY", help="Restrict deletion/invalidation by confidence")
    parser.add_argument("--include-contacted", action="store_true", help="Allow deleting companies that already have OutreachLog sent emails")
    parser.add_argument("--yes", action="store_true", help="Skip interactive confirmation prompt")

    args = parser.parse_args()

    # Deletion / Invalidation Path
    if args.delete_from_csv:
        if not args.dry_run and not args.confirm_delete:
            print("REFUSED: Deleting companies requires `--confirm-delete` (or use `--dry-run` first to preview).")
            sys.exit(2)
        apply_csv_cleanup(
            Path(args.delete_from_csv),
            mode="delete",
            dry_run=args.dry_run,
            include_review=args.include_review,
            min_confidence=args.min_confidence,
            include_contacted=args.include_contacted,
            assume_yes=args.yes,
        )
        return

    if args.mark_invalid_from_csv:
        if not args.dry_run and not args.confirm_invalidate:
            print("REFUSED: Marking invalid requires `--confirm-invalidate` (or use `--dry-run` first to preview).")
            sys.exit(2)
        apply_csv_cleanup(
            Path(args.mark_invalid_from_csv),
            mode="invalidate",
            dry_run=args.dry_run,
            include_review=args.include_review,
            min_confidence=args.min_confidence,
            include_contacted=args.include_contacted,
            assume_yes=args.yes,
        )
        return

    # Read-Only Audit & CSV Export Path
    target_domains = [d.strip() for d in args.domains.split(",") if d.strip()] if args.domains else None
    records = load_companies_from_db(target_domains=target_domains, include_invalid=args.include_invalid)

    findings = [evaluate_db_signals(r) for r in records]
    if args.verify_scope == "all":
        for f in findings:
            if f.verify_trigger == "weak_host_only":
                f.needs_live_verify = True
    if target_domains:
        # Always verify targeted domains live unless --db-only was passed
        for f in findings:
            f.needs_live_verify = True

    verify_queue = [f for f in findings if f.needs_live_verify]
    if args.verify_limit > 0 and len(verify_queue) > args.verify_limit:
        for f in verify_queue[args.verify_limit :]:
            f.needs_live_verify = False
        verify_queue = verify_queue[: args.verify_limit]

    print(f"[Stage 1] Preliminary DB detections (score>=4): {sum(1 for f in findings if f.max_score >= 4)} | Queued for live check: {len(verify_queue)}", flush=True)

    if not args.db_only and verify_queue:
        verify_candidates_live(findings, concurrency=args.concurrency)

    summary = write_csv_reports(findings, Path(args.out_dir), min_score=args.min_score)

    print("\n" + "=" * 72)
    print(" NON-COMPANY AUDIT COMPLETE (READ-ONLY — ZERO DB CHANGES)")
    print("=" * 72)
    print(f" Total companies scanned : {summary['total_scanned']}")
    print(f" Total non-companies     : {summary['total_flagged']}")
    print(f" By Category             : {summary['by_category']}")
    print(f" By Confidence           : {summary['by_confidence']}")
    print(f" Action Approved Counts  : {summary['by_action_approved']}")
    print(f" Contacted (Safe-Guarded): {summary['contacted_flagged_count']}")
    print(f" Detection Sources       : {summary['by_detection_source']}")
    print("\nGenerated CSV Reports:")
    print(f"  - Master List        : {summary['files']['all_csv']}")
    print(f"  - Training Institutes: {summary['files']['institutes_csv']}")
    print(f"  - Freelancer Sites   : {summary['files']['freelancers_csv']}")
    print(f"  - Summary JSON       : {summary['summary_json']}")


if __name__ == "__main__":
    main()
