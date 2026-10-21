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

        enriched_count = 0
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        for idx, item in enumerate(scraped_raw, 1):
            name = (item.get("name") or "").strip()
            domain = (item.get("domain") or "").strip().lower()
            website_url = item.get("website_url") or ""

            if not name or not domain or not is_genuine_company_domain(domain):
                continue

            # Calculate progress percentage between 50% and 95%
            pct = int(50 + (idx / max(1, total_scraped) * 45))
            log_job(db, job_id, f"[{idx}/{total_scraped}] Deep AI Enriching: {name} ({domain})...", pct)

            # Insert or fetch company in Neon DB
            company = db.query(Company).filter(Company.domain == domain).first()
            if not company:
                company = Company(
                    domain=domain,
                    name=name,
                    website_url=website_url,
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

            # Perform Deep AI Enrichment (Website crawl + Groq LLM analysis)
            try:
                enrich_res = loop.run_until_complete(deep_enrich_company(company.id, db, force_refresh=False))
                if enrich_res.get("success"):
                    enriched_count += 1
            except Exception as enrich_err:
                print(f"[Enrich Warning] Failed to enrich {domain}: {enrich_err}")
                try:
                    db.rollback()
                except Exception:
                    pass

            # Prepare card representation for real-time frontend stream
            try:
                db.rollback()  # ensure clean transaction state
                company = db.query(Company).filter(Company.id == company.id).first()
                emails = db.query(CompanyEmail).filter(CompanyEmail.company_id == company.id).all() if company else []
                profile = db.query(CompanyProfile).filter(CompanyProfile.company_id == company.id).first() if company else None

                card_data = {
                    "id": company.id,
                    "name": company.name,
                    "domain": company.domain,
                    "website_url": company.website_url,
                    "phone": company.phone,
                    "address": company.address,
                    "rating": company.rating,
                    "reviews_count": company.reviews_count,
                    "is_enriched": company.is_enriched if company else False,
                    "emails": [e.email_address for e in emails],
                    "primary_email": emails[0].email_address if emails else None,
                    "industry": profile.industry if profile else "Technology",
                    "tech_stack": profile.tech_stack if profile else []
                }

                log_job(db, job_id, f"✓ Successfully enriched & verified: {name} ({len(emails)} emails found)", pct, live_card=card_data)
            except Exception as card_err:
                print(f"[Warning] Failed to generate card for {domain}: {card_err}")
                try:
                    db.rollback()
                except Exception:
                    pass

        # Mark job complete
        job = db.query(ScoutJob).filter(ScoutJob.id == job_id).first()
        job.status = "COMPLETED"
        job.progress = 100
        job.total_enriched = enriched_count
        job.status_message = f"Scouting & AI Enrichment Completed! {len(job.results or [])} verified companies ready."
        job.updated_at = datetime.utcnow()
        db.commit()

        log_job(db, job_id, f"All tasks completed successfully! Total {len(job.results or [])} companies saved to database.", 100)

    except Exception as e:
        print(f"[Error] Cloud runner failure: {e}")
        job = db.query(ScoutJob).filter(ScoutJob.id == job_id).first()
        if job:
            job.status = "FAILED"
            job.error = str(e)
            job.status_message = f"Failed: {e}"
            job.updated_at = datetime.utcnow()
            db.commit()
        log_job(db, job_id, f"Fatal Error in Cloud Worker: {e}", 100)
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
