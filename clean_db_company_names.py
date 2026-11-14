"""
OutreachPilot - High-Speed Database Company Name Sanitation Engine
File: clean_db_company_names.py

Scans all 33,600+ companies in Neon PostgreSQL using primary key indexing
and cleans names by removing SEO taglines, marketing slogans, and delimiters.
(e.g., 'iRoid Solutions - Best IT company in India | Android & iOS App Development' -> 'iRoid Solutions')
"""

import os
import re
import sys
import time

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import Company, SessionLocal, init_db

SEO_KEYWORDS = {
    "best", "top", "leading", "company in", "agency in", "solutions in", "services in",
    "development company", "software development", "app development", "mobile app",
    "web design", "website development", "digital marketing", "seo agency", "seo services",
    "it solutions", "it company", "it services", "it training", "classes in", "courses in",
    "institute in", "data science", "data analyst", "full stack", "python training",
    "java classes", "training institute", "corporate upskilling", "english speaking",
    "accounting and taxation", "career counselling", "study abroad", "experts in",
    "blockchain development", "magento development", "ecommerce development",
    "application, website", "global software", "ai integrated", "drone services",
    "certified computer", "home", "homepage", "welcome to", "official website",
    "software outsourcing", "consulting company", "consultancy services"
}

LEGAL_SUFFIXES = {"pvt", "ltd", "private", "limited", "llp", "inc", "llc", "corp"}


def clean_company_name(raw_name: str, domain: str = "") -> str:
    """
    Intelligently extracts the actual corporate company name from a title string,
    removing SEO marketing slogans, city locations, and service taglines.
    """
    if not raw_name or not isinstance(raw_name, str):
        return ""
    
    name = raw_name.strip()
    
    # Delimiter regex that preserves internal hyphens like G-TEC or Wi-Fi
    sep_pattern = r'\s+[-–—]\s+|[-–—]\s+|\s+[-–—]|\s*[|:•·]\s*|\s*::\s*'
    parts = [p.strip() for p in re.split(sep_pattern, name) if p.strip()]
    
    if len(parts) <= 1:
        parts = [p.strip() for p in re.split(r'\s*[|]\s*', name) if p.strip()]
        if len(parts) <= 1:
            return name
        
    clean_domain = re.sub(r'^(?:https?://)?(?:www\.)?', '', (domain or "").lower()).split('/')[0]
    domain_compact = re.sub(r'[^a-z0-9]', '', clean_domain)
    
    scored_parts = []
    for part in parts:
        score = 0
        p_lower = part.lower()
        p_words = [w for w in re.findall(r'[a-z0-9]+', p_lower) if len(w) >= 2]
        
        # 1. Heavily penalize SEO buzzwords & service slogans
        for kw in SEO_KEYWORDS:
            if kw in p_lower:
                score -= 10
                
        # 2. Reward domain overlap
        part_compact = re.sub(r'[^a-z0-9]', '', p_lower)
        if part_compact and (part_compact in domain_compact or domain_compact in part_compact):
            score += 20
        else:
            sig_matches = [w for w in p_words if len(w) >= 4 and w in domain_compact and w not in ('best', 'tech', 'soft', 'solu')]
            if sig_matches:
                score += 5 * len(sig_matches)
            
        # 3. Reward corporate legal entity suffixes
        if set(p_words) & LEGAL_SUFFIXES:
            score += 8
            
        # 4. Prefer concise company names (typically 1 to 5 words)
        word_count = len(part.split())
        if 1 <= word_count <= 5:
            score += 5
        elif word_count > 7:
            score -= (word_count - 5) * 3
            
        scored_parts.append((score, part))
        
    scored_parts.sort(key=lambda x: x[0], reverse=True)
    best_candidate = scored_parts[0][1]
    
    # Strip leading/trailing punctuation or quotes
    best_candidate = re.sub(r'^[\s\-_|:•·"\'«»“”]+|[\s\-_|:•·"\'«»“”]+$', '', best_candidate).strip()
    return best_candidate or name


def run_name_cleanup(dry_run: bool = False, chunk_size: int = 1000):
    init_db()
    db = SessionLocal()
    
    t0 = time.time()
    print("=" * 70, flush=True)
    print(" OutreachPilot - High-Speed Company Name Sanitation Engine", flush=True)
    print(f" Mode: {'DRY RUN (Preview Only)' if dry_run else 'LIVE MIGRATION (Writing to Neon PostgreSQL)'}", flush=True)
    print("=" * 70, flush=True)
    
    total_companies = db.query(Company.id).count()
    print(f"Scanning {total_companies} total companies using primary-key chunks...\n", flush=True)
    
    last_id = 0
    total_scanned = 0
    total_cleaned = 0
    delimiters = [' - ', ' | ', ' : ', ' – ', ' — ', ' • ', ' · ', '|']
    
    while True:
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
        total_scanned += len(rows)
        
        updates = []
        for cid, cname, cdomain in rows:
            if not cname:
                continue
            if any(d in cname for d in delimiters):
                cleaned = clean_company_name(cname, cdomain)
                if cleaned and cleaned != cname:
                    updates.append({"id": cid, "name": cleaned})
                    total_cleaned += 1
                    if total_cleaned <= 15 or total_cleaned % 500 == 0:
                        print(f"[{total_cleaned}] {cdomain}:", flush=True)
                        print(f"    BEFORE: {cname}", flush=True)
                        print(f"    AFTER : {cleaned}", flush=True)
                        
        if not dry_run and updates:
            for attempt in range(3):
                try:
                    db.bulk_update_mappings(Company, updates)
                    db.commit()
                    break
                except Exception as e:
                    db.rollback()
                    if attempt == 2:
                        print(f"Failed to commit batch updates at ID {last_id}: {e}", flush=True)
                    time.sleep(1)
                    
        print(f"Scanned {total_scanned}/{total_companies} (Cleaned {total_cleaned} so far)...", flush=True)
        
    db.close()
    elapsed = time.time() - t0
    print("\n" + "=" * 70, flush=True)
    print(" NAME SANITATION COMPLETE", flush=True)
    print(f" Total Records Scanned    : {total_scanned}", flush=True)
    print(f" Successfully Cleaned     : {total_cleaned}", flush=True)
    print(f" Elapsed Time             : {elapsed:.1f}s", flush=True)
    print("=" * 70, flush=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Clean company names in Neon PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without saving to DB")
    parser.add_argument("--chunk-size", type=int, default=1000, help="Query chunk size")
    args = parser.parse_args()
    
    run_name_cleanup(dry_run=args.dry_run, chunk_size=args.chunk_size)
