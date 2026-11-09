"""
OutreachPilot - Cloud Scouting & Autonomous Neon DB Queue Worker
File: cloud_worker.py
Executed inside GitHub Actions Cloud Runners.
Operates in two modes:
  1. Autonomous Queue Consumer Mode (Default):
     Atomically claims and processes QUEUED ScoutJobs directly from Neon DB
     using PostgreSQL 'SELECT ... FOR UPDATE SKIP LOCKED'.
     Allows 5-20 parallel GitHub runners to chew through hundreds of queued
     jobs simultaneously with zero collisions and zero duplicate scraping.
     Zero local computer uptime required.
  2. Single-Target Worker Mode:
     Scouts a specific job_id or keyword/city on demand.

All scraping runs in 'All Pages Mode' (crawls through all available Google
Local search pagination until results are exhausted).
"""

import argparse
import os
import sys
import time
from datetime import datetime

# Prevent Windows console UnicodeEncodeError ('charmap' codec) on checkmarks or emojis
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from db import Company, ScoutJob, SessionLocal, init_db
from scraper_engine import GoogleScraper, is_genuine_company_domain


def log_job(db, job_id: int, msg: str, progress: int = None, live_card: dict = None):
    """Updates job progress and logs in Neon database in real-time"""
    t_str = datetime.utcnow().strftime("%H:%M:%S")
    try:
        print(f"[{t_str}] [Job #{job_id}] {msg}")
    except Exception:
        try:
            print(f"[{t_str}] [Job #{job_id}] {msg.encode('ascii', 'replace').decode('ascii')}")
        except Exception:
            pass
    try:
        job = db.query(ScoutJob).filter(ScoutJob.id == job_id).first()
        if not job:
            return

        current_logs = list(job.logs or [])
        current_logs.append(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {msg}")
        # Keep latest 100 log lines to avoid payload bloat
        if len(current_logs) > 100:
            current_logs = current_logs[-100:]
        job.logs = current_logs
        job.status_message = str(msg)[:500]

        if progress is not None:
            job.progress = min(100, max(0, progress))

        if live_card:
            current_results = list(job.results or [])
            if not any(r.get("domain") == live_card.get("domain") for r in current_results):
                current_results.append(live_card)
            job.results = current_results
            job.total_found = len(current_results)

        job.updated_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        print(f"[Warning] Failed to update job log: {e}")
        try:
            db.rollback()
        except Exception:
            pass


def execute_scout_job(job_id: int, auto_enrich: bool = False) -> bool:
    """
    Executes a single scout job in All Pages Mode:
    - Scrapes all available pagination until Google listings are exhausted.
    - Filters genuine company domains.
    - Saves companies to Neon DB.
    - Updates ScoutJob status to COMPLETED.
    """
    db = SessionLocal()
    init_db()

    job = db.query(ScoutJob).filter(ScoutJob.id == job_id).first()
    if not job:
        print(f"[Error] ScoutJob #{job_id} not found in database.")
        db.close()
        return False

    keyword = job.keyword
    city = job.city or ""

    job.status = "RUNNING"
    job.progress = 5
    job.status_message = f"Scouting all available pages for '{keyword}' in '{city}'..."
    job.updated_at = datetime.utcnow()
    db.commit()

    log_job(db, job_id, f"Scouting initiated for '{keyword}' in '{city}' (All Pages Mode)...", 10)

    try:
        def on_scraper_log(msg: str, progress: int = None):
            log_job(db, job_id, msg, progress)

        scraper = GoogleScraper(headless=True, max_workers=10, log_callback=on_scraper_log)
        log_job(db, job_id, "Connecting to live Google Maps search...", 15)

        # Scrape all available pages until Google has no more listings (max_pages=0)
        scraped_raw = scraper.scrape(
            keyword=keyword,
            city=city,
            max_pages=0,
            gl="in",
            hl="en"
        )

        total_scraped = len(scraped_raw)
        log_job(db, job_id, f"Google Local search complete across all pages. Located {total_scraped} candidate business locations.", 45)

        # Filter genuine company listings
        valid_items = []
        for item in scraped_raw:
            c_name = (item.get("name") or "").strip()
            c_dom = (item.get("domain") or "").strip().lower()
            if c_name and c_dom and is_genuine_company_domain(c_dom):
                valid_items.append(item)

        total_valid = len(valid_items)
        log_job(db, job_id, f"Domain verification: Identified {total_valid} verified businesses with working official websites.", 55)

        # Refresh database session after prolonged browser scraping to avoid Neon timeout
        try:
            db.close()
        except Exception:
            pass
        db = SessionLocal()
        job = db.query(ScoutJob).filter(ScoutJob.id == job_id).first()

        # Batch-register all companies in Neon DB with PENDING status
        registered_cards = []
        for item in valid_items:
            c_dom = item["domain"].strip().lower()
            c_name = item["name"].strip()
            try:
                company = db.query(Company).filter(Company.domain == c_dom).first()
                if not company:
                    company = Company(
                        domain=c_dom,
                        name=c_name,
                        website_url=item.get("website_url") or "",
                        phone=item.get("phone") or "",
                        address=item.get("address") or "",
                        location_url=item.get("location_url") or "",
                        rating=item.get("rating") or 0.0,
                        reviews_count=item.get("reviews_count") or 0,
                        search_keyword=keyword,
                        city=city,
                        source_query=f"{keyword} {city}".strip(),
                        enrichment_status="PENDING",
                        enrichment_attempts=0
                    )
                    db.add(company)
                    db.commit()
                    db.refresh(company)

                card_data = {
                    "id": company.id,
                    "name": company.name,
                    "domain": company.domain,
                    "website_url": company.website_url or "",
                    "phone": company.phone or "",
                    "address": company.address or "",
                    "rating": company.rating or 0.0,
                    "reviews_count": company.reviews_count or 0,
                    "is_enriched": company.is_enriched or False,
                    "enrichment_status": company.enrichment_status or "PENDING",
                    "emails": [],
                    "primary_email": None,
                    "industry": "Pending AI Enrichment",
                    "tech_stack": []
                }
                registered_cards.append(card_data)
            except Exception:
                try:
                    db.rollback()
                    db.close()
                    db = SessionLocal()
                except Exception:
                    pass

        # Update ScoutJob in Neon DB
        job = db.query(ScoutJob).filter(ScoutJob.id == job_id).first()
        if job:
            job.status = "COMPLETED"
            job.progress = 100
            job.total_found = len(registered_cards)
            job.results = registered_cards
            job.status_message = f"Scouting completed! Discovered {len(registered_cards)} verified businesses across all pages. Background AI Enrichment active."
            job.updated_at = datetime.utcnow()
            db.commit()

        log_job(db, job_id, f"Scouting finished! Saved {len(registered_cards)} verified companies to directory.", 100)

        # Trigger decoupled cloud_enrich.yml workflow via GitHub Actions API only if requested
        if auto_enrich:
            gh_token = os.environ.get("GITHUB_TOKEN")
            gh_repo = os.environ.get("GITHUB_REPOSITORY", "vorarahul4700/outreachPilot")
            if gh_token:
                try:
                    import httpx
                    dispatch_url = f"https://api.github.com/repos/{gh_repo}/actions/workflows/cloud_enrich.yml/dispatches"
                    headers = {
                        "Authorization": f"Bearer {gh_token}",
                        "Accept": "application/vnd.github.v3+json"
                    }
                    resp = httpx.post(dispatch_url, json={"ref": "main"}, headers=headers, timeout=10)
                    if resp.status_code in (200, 204):
                        log_job(db, job_id, "Initiated AI analysis: inspecting websites, tech stacks, and recruiter contacts.")
                except Exception as trig_err:
                    log_job(db, job_id, f"Note: could not auto-dispatch cloud_enrich ({trig_err}).")
        return True

    except Exception as e:
        print(f"[Error] Job #{job_id} failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        try:
            db.close()
            db = SessionLocal()
            job = db.query(ScoutJob).filter(ScoutJob.id == job_id).first()
            if job:
                job.status = "FAILED"
                job.error = str(e)
                job.status_message = f"Failed: {e}"
                job.updated_at = datetime.utcnow()
                db.commit()
            log_job(db, job_id, f"Fatal Error in Cloud Worker: {e}", 100)
        except Exception:
            pass
        return False
    finally:
        try:
            db.close()
        except Exception:
            pass


def claim_next_queued_job(domain_filter: str = None, city_filter: str = None) -> int:
    """
    Atomically claims the next QUEUED ScoutJob from Neon DB using SELECT ... FOR UPDATE SKIP LOCKED.
    Returns the job_id, or None if no queued jobs are available.
    """
    db = SessionLocal()
    try:
        query = db.query(ScoutJob).filter(ScoutJob.status == "QUEUED")
        if city_filter and city_filter.strip():
            query = query.filter(ScoutJob.city.ilike(f"%{city_filter.strip()}%"))
        if domain_filter and domain_filter.strip():
            query = query.filter(ScoutJob.keyword.ilike(f"%{domain_filter.strip()}%"))

        job = query.order_by(ScoutJob.id.asc()).with_for_update(skip_locked=True).first()
        if not job:
            return None

        job_id = job.id
        job.status = "RUNNING"
        job.progress = 5
        job.status_message = f"Claimed by Cloud Runner. Preparing search for '{job.keyword}' in '{job.city}'..."
        job.updated_at = datetime.utcnow()
        db.commit()
        return job_id
    except Exception as e:
        print(f"[Error] Failed to claim next queued job: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return None
    finally:
        try:
            db.close()
        except Exception:
            pass


def run_queue_consumer(
    batch_size: int = 30,
    domain_filter: str = None,
    city_filter: str = None,
    auto_enrich: bool = False,
    runner_id: str = "1"
):
    """
    Autonomous Queue Consumer:
    Continuously claims and processes QUEUED jobs from Neon DB until batch_size
    is reached or no QUEUED jobs remain.
    """
    print(f"\n=======================================================")
    print(f"[Runner-{runner_id}] OutreachPilot Autonomous Queue Consumer Started")
    print(f"  • Batch Budget : {batch_size} jobs")
    print(f"  • Domain Filter: {domain_filter or 'All Queued Domains'}")
    print(f"  • City Filter  : {city_filter or 'All Indian Cities'}")
    print(f"  • Pagination   : All Pages Mode (No max page limit)")
    print(f"=======================================================\n")

    init_db()
    processed_count = 0

    while processed_count < batch_size:
        job_id = claim_next_queued_job(domain_filter=domain_filter, city_filter=city_filter)
        if not job_id:
            print(f"[Runner-{runner_id}] No more QUEUED jobs available in Neon DB matching criteria.")
            break

        print(f"\n>>> [Runner-{runner_id}] Processing Job #{job_id} ({processed_count + 1}/{batch_size}) <<<")
        success = execute_scout_job(job_id=job_id, auto_enrich=auto_enrich)
        processed_count += 1
        print(f">>> [Runner-{runner_id}] Finished Job #{job_id} (Status: {'SUCCESS' if success else 'FAILED'}) <<<\n")

        # Brief pause between jobs to be gentle on Google and connection pools
        time.sleep(2)

    print(f"\n=======================================================")
    print(f"[Runner-{runner_id}] Queue Consumer batch completed: Processed {processed_count} jobs.")
    print(f"=======================================================\n")


def run_single_worker(job_id: int, keyword: str, city: str, auto_enrich: bool = False):
    """Directly executes a single scout job by ID or keyword/city"""
    init_db()
    if not job_id or job_id <= 0:
        db = SessionLocal()
        print(f"[Notice] ScoutJob #{job_id} not provided. Auto-creating ScoutJob in Neon DB...")
        job = ScoutJob(
            keyword=keyword,
            city=city,
            max_pages=0,
            status="RUNNING",
            progress=5,
            status_message=f"Scouting all pages for '{keyword}' in '{city}'...",
            logs=[f"[{datetime.utcnow().strftime('%H:%M:%S')}] Single-target worker initiated (All Pages Mode)."],
            results=[]
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
        db.close()

    execute_scout_job(job_id=job_id, auto_enrich=auto_enrich)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OutreachPilot Cloud Worker & Neon DB Queue Consumer")
    parser.add_argument("--mode", type=str, default="queue", choices=["queue", "single"],
                        help="Execution mode: 'queue' (consumes Neon DB scout_jobs) or 'single' (specific job)")
    parser.add_argument("--batch-size", type=int, default=30,
                        help="Max jobs to process per runner in queue mode (default: 30)")
    parser.add_argument("--domain", type=str, default="",
                        help="Optional domain keyword filter for queue mode (e.g. pharma, marketing, it)")
    parser.add_argument("--city", type=str, default="",
                        help="Target city (filter for queue, or exact city for single mode)")
    parser.add_argument("--keyword", type=str, default="",
                        help="Search keyword (used in single mode)")
    parser.add_argument("--job-id", type=int, default=0,
                        help="ScoutJob ID in Neon DB (used in single mode, 0 to auto-create)")
    parser.add_argument("--runner-id", type=str, default="1",
                        help="Identifier for this runner in GitHub Actions parallel matrix")
    parser.add_argument("--max-pages", type=int, default=0,
                        help="Deprecated / ignored - all runs now scrape all available pages")
    parser.add_argument("--auto-enrich", action="store_true", default=False,
                        help="Automatically trigger cloud_enrich after scout")

    args = parser.parse_args()

    # Determine mode: if keyword or job-id is explicitly passed and mode is not explicitly 'queue'
    effective_mode = args.mode
    if (args.job_id > 0 or args.keyword.strip()) and args.mode != "queue":
        effective_mode = "single"

    if effective_mode == "single":
        kw = args.keyword.strip() or "IT Companies"
        ct = args.city.strip()
        run_single_worker(
            job_id=args.job_id,
            keyword=kw,
            city=ct,
            auto_enrich=args.auto_enrich
        )
    else:
        run_queue_consumer(
            batch_size=args.batch_size,
            domain_filter=args.domain.strip() or None,
            city_filter=args.city.strip() or None,
            auto_enrich=args.auto_enrich,
            runner_id=args.runner_id
        )
