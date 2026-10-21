"""
OutreachPilot - Cloud AI Enrichment & Auto-Healing Worker
File: cloud_enrich.py

Executed as a decoupled GitHub Actions background job and automated cron.
Claims batches of pending/failed company URLs from Neon PostgreSQL,
executes high-speed parallel website crawling + Groq AI analysis using multi-account key pool,
and auto-heals failed records up to 3 attempts (marking unresolvable URLs as INCOMPLETE).
"""

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime

# Prevent Windows console UnicodeEncodeError on emojis/checkmarks
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from db import Company, CompanyEmail, CompanyProfile, SessionLocal, init_db
from enricher import deep_enrich_company
import config


def log(msg: str):
    t_str = datetime.utcnow().strftime("%H:%M:%S")
    try:
        print(f"[{t_str}] {msg}")
    except Exception:
        try:
            print(f"[{t_str}] {msg.encode('ascii', 'replace').decode('ascii')}")
        except Exception:
            pass


def run_enrichment_pipeline(batch_size: int = 60, max_attempts: int = 3, target_domain: str = None):
    """Claims pending/failed companies and enriches them in parallel using multi-account pool."""
    init_db()
    db = SessionLocal()

    try:
        query = db.query(Company).filter(
            Company.is_invalid == False
        )

        if target_domain:
            query = query.filter(Company.domain == target_domain.strip().lower())
        else:
            query = query.filter(
                Company.enrichment_status.in_(["PENDING", "FAILED"]),
                Company.enrichment_attempts < max_attempts
            ).order_by(Company.created_at.desc())

        pending_companies = query.limit(batch_size).all()
        total_items = len(pending_companies)

        if total_items == 0:
            log("No pending or failed companies found in database. All records are up to date!")
            return

        log(f"Found {total_items} companies requiring AI enrichment (Batch Size: {batch_size}, Max Attempts: {max_attempts}).")

        # Mark claimed batch as IN_PROGRESS and bump attempts count
        company_targets = []
        for comp in pending_companies:
            comp.enrichment_status = "IN_PROGRESS"
            comp.enrichment_attempts = (comp.enrichment_attempts or 0) + 1
            company_targets.append({
                "id": comp.id,
                "name": comp.name,
                "domain": comp.domain,
                "attempts": comp.enrichment_attempts
            })
        db.commit()
        db.close()

        # Multi-Account Concurrency Configuration
        concurrency = getattr(config, "GROQ_CONCURRENCY", 4)
        active_keys = getattr(config, "GROQ_API_KEYS", [])
        pool_mode = f"Multi-Account Pool ({len(active_keys)} accounts, {concurrency} parallel workers)" if getattr(config, "IS_MULTI_GROQ", False) else f"Single Account ({concurrency} workers)"
        log(f"Launching parallel enrichment via {pool_mode}...")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        sem = asyncio.Semaphore(concurrency)
        success_count = 0
        failed_count = 0
        incomplete_count = 0
        lock = asyncio.Lock()

        async def enrich_single(comp_data: dict, idx: int):
            nonlocal success_count, failed_count, incomplete_count
            c_id = comp_data["id"]
            c_name = comp_data["name"]
            c_domain = comp_data["domain"]
            attempts = comp_data["attempts"]

            async with sem:
                worker_db = SessionLocal()
                try:
                    log(f"[{idx}/{total_items}] Enriching (Attempt {attempts}/{max_attempts}): {c_name} ({c_domain})...")
                    res = await deep_enrich_company(c_id, worker_db, force_refresh=True)

                    c_obj = worker_db.query(Company).filter(Company.id == c_id).first()
                    if c_obj:
                        c_obj.is_enriched = True
                        c_obj.enrichment_status = "COMPLETED"
                        c_obj.last_enriched_at = datetime.utcnow()
                        worker_db.commit()

                    async with lock:
                        success_count += 1
                    emails_count = len(res.get("emails", [])) if isinstance(res, dict) else 0
                    log(f"[{idx}/{total_items}] [OK] Completed: {c_name} ({c_domain}) - {emails_count} verified emails")
                    return True
                except Exception as err:
                    log(f"[{idx}/{total_items}] [FAIL] Failed {c_domain}: {err}")
                    try:
                        worker_db.rollback()
                        c_obj = worker_db.query(Company).filter(Company.id == c_id).first()
                        if c_obj:
                            if attempts >= max_attempts:
                                c_obj.enrichment_status = "INCOMPLETE"
                                async with lock:
                                    incomplete_count += 1
                                log(f"[{idx}/{total_items}] [MAX REACHED] Marked {c_domain} as INCOMPLETE after {attempts} attempts.")
                            else:
                                c_obj.enrichment_status = "FAILED"
                                async with lock:
                                    failed_count += 1
                            worker_db.commit()
                    except Exception as db_err:
                        log(f"[DB Error] Could not update failure status for {c_domain}: {db_err}")
                    return False
                finally:
                    try:
                        worker_db.close()
                    except Exception:
                        pass

        tasks = [enrich_single(c, i) for i, c in enumerate(company_targets, 1)]
        loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))

        log("=" * 60)
        log(f"Enrichment Pipeline Completed:")
        log(f"  Total Processed: {total_items}")
        log(f"  Successfully Enriched: {success_count}")
        log(f"  Failed (Will Retry on Next Cron): {failed_count}")
        log(f"  Permanently Incomplete: {incomplete_count}")
        log("=" * 60)

    except Exception as e:
        log(f"[Fatal Error] Pipeline crashed: {e}")
        sys.exit(1)
    finally:
        try:
            db.close()
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OutreachPilot AI Enrichment Pipeline")
    parser.add_argument("--batch-size", type=int, default=60, help="Max companies to claim per run")
    parser.add_argument("--max-attempts", type=int, default=3, help="Max attempts before marking INCOMPLETE")
    parser.add_argument("--domain", type=str, default=None, help="Target specific domain")
    args = parser.parse_args()

    run_enrichment_pipeline(
        batch_size=args.batch_size,
        max_attempts=args.max_attempts,
        target_domain=args.domain
    )
