"""
OutreachPilot - High-Precision Non-Company Entity Filter & Removal Engine
Identifies and invalidates entities that are educational institutes, coaching classes,
academies, universities, tuition centers, or personal portfolios.
Outputs a comprehensive audit CSV log of all excluded entities.
"""

import os
import sys
import re
import csv
import time
from datetime import datetime

# UTF-8 for Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import Company, SessionLocal

# Pattern definitions for non-company entities
NON_COMPANY_PATTERNS = [
    # Academic and coaching terms
    r"\binstitute\b",
    r"\bacadem(?:y|ies)\b",
    r"\bcoaching\b",
    r"\btuition\b",
    r"\bclasses\b",
    r"\bcollege\b",
    r"\buniversity\b",
    r"\bvishwavidyalaya\b",
    r"\bvidyalaya\b",
    r"\bshiksha\b",
    r"\bgurukul\b",
    r"\bpathshala\b",
    r"\bschool\b",
    r"\bielts\b",
    r"\btoefl\b",
    r"\bpte coaching\b",
    r"\bpte classes\b",
    r"\bgmat\b",
    r"\bgre\b",
    r"\bcat coaching\b",
    r"\bgate coaching\b",
    r"\bupsc\b",
    r"\bgpsc\b",
    r"\bspoken english\b",
    r"\bdriving school\b",
    r"\bmusic academy\b",
    r"\bdance academy\b",
    r"\bkarate\b",
    r"\bmartial arts\b",
    r"\bshare market classes\b",
    r"\bstock market classes\b",
    r"\btrading academy\b",
    r"\btrading institute\b",
    # Personal portfolios and free blog subdomains
    r"\bportfolio\b",
    r"\bpersonal site\b",
    r"\bgithub\.io\b",
    r"\bwordpress\.com\b",
    r"\bblogspot\.com\b",
    r"\bwixsite\.com\b",
    r"\bweebly\.com\b",
    r"\bsites\.google\.com\b",
]

NON_COMPANY_REGEX = re.compile("|".join(NON_COMPANY_PATTERNS), re.IGNORECASE)

# Academic / Personal domain suffixes and subdomains
ACADEMIC_DOMAIN_SUFFIXES = (
    ".ac.in",
    ".edu.in",
    ".edu",
    ".res.in",
    ".ernet.in",
    ".gov.in",
    ".nic.in",
)

def is_non_company(name: str, domain: str) -> tuple[bool, str]:
    name_str = (name or "").strip()
    dom_str = (domain or "").strip().lower()

    # Check academic domain suffixes
    for suffix in ACADEMIC_DOMAIN_SUFFIXES:
        if dom_str.endswith(suffix):
            return True, f"Academic/Gov TLD ({suffix})"

    # Check name against regex
    match = NON_COMPANY_REGEX.search(name_str)
    if match:
        term = match.group(0).lower()
        return True, f"Keyword match: '{term}' in name"

    # Check domain against regex (e.g. github.io, blogspot.com, etc.)
    match_dom = NON_COMPANY_REGEX.search(dom_str)
    if match_dom:
        term = match_dom.group(0).lower()
        return True, f"Keyword match: '{term}' in domain"

    # Check domain name part
    dom_core = dom_str.split(".")[0]
    for term in ["academy", "institute", "coaching", "classes", "tuition", "portfolio", "ielts"]:
        if term in dom_core:
            return True, f"Keyword match: '{term}' in domain"

    return False, ""

def run_filter(dry_run: bool = False):
    db = SessionLocal()
    os.makedirs("logs", exist_ok=True)
    csv_path = os.path.join("logs", "removed_non_companies_log.csv")

    print("=" * 70, flush=True)
    print(" OutreachPilot - Non-Company Entity Filter & Audit Engine")
    print(f" Mode: {'DRY RUN' if dry_run else 'LIVE DATABASE PURGE'}")
    print("=" * 70, flush=True)

    # Query all currently valid companies
    q = db.query(Company.id, Company.name, Company.domain, Company.city, Company.source_query).filter(Company.is_invalid == False)
    total_valid = q.count()
    print(f"Scanning {total_valid} valid companies in Neon PostgreSQL...", flush=True)

    batch_size = 5000
    last_id = 0
    flagged_records = []
    
    t0 = time.time()
    scanned = 0

    while True:
        rows = db.query(Company.id, Company.name, Company.domain, Company.city, Company.source_query)\
                 .filter(Company.is_invalid == False, Company.id > last_id)\
                 .order_by(Company.id.asc())\
                 .limit(batch_size)\
                 .all()
        if not rows:
            break

        for row in rows:
            cid, cname, cdom, ccity, cquery = row
            last_id = cid
            scanned += 1

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

        print(f"Scanned {scanned}/{total_valid} companies... (Flagged {len(flagged_records)} so far)", flush=True)

    print(f"\nScan complete in {time.time() - t0:.1f}s.")
    print(f"Total Flagged Non-Company Entities: {len(flagged_records)}", flush=True)

    # Write CSV audit log
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "name", "domain", "city", "source_query", "reason"])
        writer.writeheader()
        writer.writerows(flagged_records)

    print(f"Audit log saved to: {csv_path}", flush=True)

    # If live, update database in chunks
    if not dry_run and flagged_records:
        print("Invalidating records in Neon PostgreSQL...", flush=True)
        flagged_ids = [r["id"] for r in flagged_records]
        now = datetime.utcnow()
        update_chunk_size = 500
        for i in range(0, len(flagged_ids), update_chunk_size):
            chunk = flagged_ids[i:i + update_chunk_size]
            db.query(Company).filter(Company.id.in_(chunk)).update(
                {
                    Company.is_invalid: True,
                    Company.invalid_reason: "Automated Non-Company Filter: Institute / Academy / Coaching / Portfolio / Education",
                    Company.invalid_at: now
                },
                synchronize_session=False
            )
            db.commit()
            print(f"Updated {min(i + update_chunk_size, len(flagged_ids))}/{len(flagged_ids)} records...", flush=True)

        print("Database update complete! Cache invalidation triggered.", flush=True)

    db.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_filter(dry_run=args.dry_run)
