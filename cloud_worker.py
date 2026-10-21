"""
OutreachPilot - Cloud Scouting & AI Enrichment Worker
File: cloud_worker.py
Executed inside GitHub Actions Cloud Runner with 7 GB RAM and unthrottled networking.
Combines Google Maps Scouting + Automatic Deep AI Enrichment into a single background job.
"""

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime

from db import (
    Company,
    CompanyEmail,
    CompanyProfile,
    ScoutJob,
    SessionLocal,
    init_db
)
from enricher import deep_enrich_company
from scraper_engine import GoogleScraper, is_genuine_company_domain


def log_job(db, job_id: int, msg: str, progress: int = None, live_card: dict = None):
    """Updates job progress and logs in Neon database in real-time"""
    print(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {msg}")
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
    job.status_message = f"Starting Cloud Worker for '{keyword}' in '{city}'..."
    db.commit()

    log_job(db, job_id, f"Cloud Runner initialized (7 GB RAM). Scouting Google for '{keyword}' in '{city}' (Pages: {max_pages})...", 10)

    try:
        def on_scraper_log(msg: str, progress: int = None):
            log_job(db, job_id, msg, progress)

        # Initialize Google Scraper Engine (Headless Chrome in Ubuntu container) with live log callback
        scraper = GoogleScraper(headless=True, max_workers=10, log_callback=on_scraper_log)
        log_job(db, job_id, "Launching Headless Chromium browser engine...", 15)

        # Scrape Google Local listings
        scraped_raw = scraper.scrape(
            keyword=keyword,
            city=city,
            max_pages=max_pages,
            gl="in",
            hl="en"
        )

        total_scraped = len(scraped_raw)
        log_job(db, job_id, f"Google Scouting finished. Discovered {total_scraped} potential company listings.", 50)

        # Filter genuine company listings
        valid_items = []
        for item in scraped_raw:
            c_name = (item.get("name") or "").strip()
            c_dom = (item.get("domain") or "").strip().lower()
            if c_name and c_dom and is_genuine_company_domain(c_dom):
                valid_items.append(item)

        total_scraped = len(valid_items)
        log_job(db, job_id, f"Google Scouting finished. Discovered {total_scraped} genuine company listings.", 50)

        # Refresh database session after prolonged browser scraping to avoid Neon timeout
        try:
            db.close()
        except Exception:
            pass
        db = SessionLocal()
        job = db.query(ScoutJob).filter(ScoutJob.id == job_id).first()

        # Batch-register all companies in Neon DB first (fast & deadlock-free)
        company_records = []
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
                        source_query=f"{keyword} {city}".strip()
                    )
                    db.add(company)
                    db.commit()
                    db.refresh(company)
                company_records.append((company.id, c_name, c_dom))
            except Exception as reg_err:
                try:
                    db.rollback()
                    db.close()
                    db = SessionLocal()
                    company = db.query(Company).filter(Company.domain == c_dom).first()
                    if company:
                        company_records.append((company.id, c_name, c_dom))
                except Exception:
                    pass

        # High-Speed Concurrent AI Enrichment (4 parallel workers)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        sem = asyncio.Semaphore(4)
        completed_count = 0
        lock = asyncio.Lock()

        async def enrich_worker_task(comp_id: int, comp_name: str, comp_domain: str, index: int):
            nonlocal completed_count
            async with sem:
                worker_db = SessionLocal()
                try:
                    pct = int(50 + (index / max(1, total_scraped) * 45))
                    log_job(worker_db, job_id, f"[{index}/{total_scraped}] Deep AI Enriching: {comp_name} ({comp_domain})...", pct)
                    
                    # Crawl website + Groq LLM analysis
                    enrich_res = await deep_enrich_company(comp_id, worker_db, force_refresh=False)
                    
                    # Read verified contact data
                    company = worker_db.query(Company).filter(Company.id == comp_id).first()
                    emails = worker_db.query(CompanyEmail).filter(CompanyEmail.company_id == comp_id).all() if company else []
                    profile = worker_db.query(CompanyProfile).filter(CompanyProfile.company_id == comp_id).first() if company else None

                    card_data = {
                        "id": comp_id,
                        "name": comp_name,
                        "domain": comp_domain,
                        "website_url": company.website_url if company else "",
                        "phone": company.phone if company else "",
                        "address": company.address if company else "",
                        "rating": company.rating if company else 0.0,
                        "reviews_count": company.reviews_count if company else 0,
                        "is_enriched": company.is_enriched if company else False,
                        "emails": [e.email_address for e in emails],
                        "primary_email": emails[0].email_address if emails else None,
                        "industry": profile.industry if profile else "Technology",
                        "tech_stack": profile.tech_stack if profile else []
                    }

                    async with lock:
                        completed_count += 1
                        current_pct = int(50 + (completed_count / max(1, total_scraped) * 45))

                    log_job(worker_db, job_id, f"✓ Successfully enriched & verified: {comp_name} ({len(emails)} emails found)", current_pct, live_card=card_data)
                    return True
                except Exception as enrich_err:
                    print(f"[Enrich Warning] Failed for {comp_domain}: {enrich_err}")
                    return False
                finally:
                    worker_db.close()

        tasks = [
            enrich_worker_task(cid, cname, cdom, i)
            for i, (cid, cname, cdom) in enumerate(company_records, 1)
        ]
        results = loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
        enriched_count = sum(1 for r in results if r is True)
        
        job = db.query(ScoutJob).filter(ScoutJob.id == job_id).first()
        if job:
            job.total_enriched = enriched_count
            job.status_message = f"Scouting & AI Enrichment Completed! {len(job.results or [])} verified companies ready."
            job.updated_at = datetime.utcnow()
            db.commit()

        log_job(db, job_id, f"All tasks completed successfully! Total {len(job.results or [])} companies saved to database.", 100)

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
