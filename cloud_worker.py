"""
OutreachPilot - Cloud Scouting & AI Enrichment Worker
File: cloud_worker.py
Executed inside GitHub Actions Cloud Runner with 7 GB RAM and unthrottled networking.
Combines Google Maps Scouting + Automatic Deep AI Enrichment into a single background job.
"""

import argparse
import os
import sys
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
        print(f"[{t_str}] {msg}")
    except Exception:
        try:
            print(f"[{t_str}] {msg.encode('ascii', 'replace').decode('ascii')}")
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
            # Avoid duplicate cards in results preview
            if not any(r.get("domain") == live_card.get("domain") for r in current_results):
                current_results.append(live_card)
            job.results = current_results
            job.total_found = len(current_results)

        job.updated_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        print(f"[Warning] Failed to update job log: {e}")
        db.rollback()


def run_worker(job_id: int, keyword: str, city: str, max_pages: int):
    """Main execution function for cloud scouting and AI enrichment"""
    db = SessionLocal()
    init_db()

    job = db.query(ScoutJob).filter(ScoutJob.id == job_id).first()
    if not job:
        print(f"[Error] ScoutJob #{job_id} not found in database.")
        sys.exit(1)

    job.status = "RUNNING"
    job.progress = 5
    job.status_message = f"Scouting verified companies for '{keyword}' in '{city}'..."
    db.commit()

    log_job(db, job_id, f"Scouting initiated for '{keyword}' in '{city}' (Pages: {max_pages})...", 10)

    try:
        def on_scraper_log(msg: str, progress: int = None):
            log_job(db, job_id, msg, progress)

        # Initialize Google Scraper Engine with live log callback
        scraper = GoogleScraper(headless=True, max_workers=10, log_callback=on_scraper_log)
        log_job(db, job_id, "Connecting to live Google Maps search...", 15)

        # Scrape Google Local listings
        scraped_raw = scraper.scrape(
            keyword=keyword,
            city=city,
            max_pages=max_pages,
            gl="in",
            hl="en"
        )

        total_scraped = len(scraped_raw)
        log_job(db, job_id, f"Google Local search complete. Located {total_scraped} candidate business locations.", 45)

        # Filter genuine company listings
        valid_items = []
        for item in scraped_raw:
            c_name = (item.get("name") or "").strip()
            c_dom = (item.get("domain") or "").strip().lower()
            if c_name and c_dom and is_genuine_company_domain(c_dom):
                valid_items.append(item)

        total_scraped = len(valid_items)
        log_job(db, job_id, f"Domain verification: Identified {total_scraped} verified businesses with working official websites.", 55)

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
            job.status_message = f"Scouting completed! Discovered {len(registered_cards)} verified businesses. Background AI Enrichment active."
            job.updated_at = datetime.utcnow()
            db.commit()

        log_job(db, job_id, f"Scouting finished! Saved {len(registered_cards)} verified companies to directory.", 100)

        # Trigger decoupled cloud_enrich.yml workflow via GitHub Actions API
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
                else:
                    log_job(db, job_id, f"Dispatched cloud_enrich trigger (Status {resp.status_code}).")
            except Exception as trig_err:
                log_job(db, job_id, f"Note: cloud_enrich will trigger via workflow_run/cron ({trig_err}).")
        else:
            log_job(db, job_id, "Scout finished! cloud_enrich will run automatically on workflow_run completion and 30-min cron.")

    except Exception as e:
        print(f"[Error] Cloud runner failure: {e}")
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
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OutreachPilot Cloud Worker")
    parser.add_argument("--job-id", type=int, required=True, help="Job ID in Neon DB")
    parser.add_argument("--keyword", type=str, default="IT Companies", help="Search keyword")
    parser.add_argument("--city", type=str, default="", help="Target city")
    parser.add_argument("--max-pages", type=int, default=2, help="Max pages to scrape")
    args = parser.parse_args()

    run_worker(
        job_id=args.job_id,
        keyword=args.keyword,
        city=args.city,
        max_pages=args.max_pages
    )
