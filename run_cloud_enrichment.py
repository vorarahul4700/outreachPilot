"""
OutreachPilot - Cloud AI Enrichment Dispatcher
File: run_cloud_enrichment.py

Automated dispatcher that triggers GitHub Action cloud_enrich runs to process
batches of un-enriched companies in Neon PostgreSQL using parallel cloud workers.

Usage:
    python run_cloud_enrichment.py                  # Enriches first 500 companies (5 x 100)
    python run_cloud_enrichment.py --total 500      # Explicit 500 companies
    python run_cloud_enrichment.py --total 200 --batch-size 50
    python run_cloud_enrichment.py --monitor        # Dispatch and monitor live progress
"""

import os
import sys
import time
import argparse
from datetime import datetime
import httpx
from dotenv import load_dotenv

# Ensure UTF-8 output on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from db import SessionLocal, Company, init_db

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = os.getenv("GITHUB_REPOSITORY", "vorarahul4700/outreachPilot")
WORKFLOW_FILE = "cloud_enrich.yml"


def log(msg: str):
    t_str = datetime.now().strftime("%H:%M:%S")
    print(f"[{t_str}] {msg}")


def get_db_stats():
    """Queries current enrichment progress directly from Neon PostgreSQL."""
    init_db()
    db = SessionLocal()
    try:
        total = db.query(Company).filter(Company.is_invalid.is_(False)).count()
        pending = db.query(Company).filter(
            Company.is_invalid.is_(False),
            Company.enrichment_status.in_(["PENDING", "FAILED"])
        ).count()
        in_progress = db.query(Company).filter(
            Company.is_invalid.is_(False),
            Company.enrichment_status == "IN_PROGRESS"
        ).count()
        completed = db.query(Company).filter(
            Company.is_invalid.is_(False),
            Company.enrichment_status == "COMPLETED"
        ).count()
        incomplete = db.query(Company).filter(
            Company.is_invalid.is_(False),
            Company.enrichment_status == "INCOMPLETE"
        ).count()
        return {
            "total": total,
            "pending": pending,
            "in_progress": in_progress,
            "completed": completed,
            "incomplete": incomplete
        }
    except Exception as e:
        log(f"[DB Error] Failed to read database stats: {e}")
        return None
    finally:
        db.close()


def print_stats_table(stats: dict, title: str = "Database Enrichment Status"):
    if not stats:
        return
    print("\n" + "=" * 65)
    print(f"  {title}")
    print("=" * 65)
    print(f"  Total Valid Companies : {stats['total']:,}")
    print(f"  Pending / Need Intel  : {stats['pending']:,}")
    print(f"  In Progress (Active)  : {stats['in_progress']:,}")
    print(f"  Completed / Enriched  : {stats['completed']:,}")
    print(f"  Unresolvable / Incomp : {stats['incomplete']:,}")
    print("=" * 65 + "\n")


def dispatch_enrichment_workflow(batch_size: int = 100, max_attempts: int = 3, run_index: int = 1, total_runs: int = 1) -> bool:
    """Dispatches a single cloud_enrich.yml workflow via GitHub Actions API."""
    if not GITHUB_TOKEN:
        log("[Error] GITHUB_TOKEN is missing from your environment or .env file.")
        return False

    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    payload = {
        "ref": "main",
        "inputs": {
            "batch_size": str(batch_size),
            "max_attempts": str(max_attempts)
        }
    }

    retries = 3
    for attempt in range(1, retries + 1):
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=25)
            if resp.status_code in (200, 204):
                log(f"[OK] Dispatched Run {run_index}/{total_runs} (Target batch: {batch_size} companies, max_attempts={max_attempts})")
                return True
            elif resp.status_code in (403, 429):
                log(f"[RateLimit] HTTP {resp.status_code}. Waiting 30s before retry (attempt {attempt}/{retries})...")
                time.sleep(30)
            else:
                log(f"[Error] HTTP {resp.status_code} on dispatch: {resp.text}")
                return False
        except Exception as e:
            log(f"[Exception] Network error during dispatch: {e}. Retrying in 5s...")
            time.sleep(5)

    return False


def run_enrichment_dispatch(total_companies: int = 500, batch_size: int = 100, max_attempts: int = 3, delay: float = 3.0, monitor: bool = False):
    """
    Splits the target company total into optimal cloud runner batches and dispatches
    GitHub Actions workflows, avoiding collisions via Neon Postgres SKIP LOCKED.
    """
    log("Checking Neon PostgreSQL database status...")
    initial_stats = get_db_stats()
    print_stats_table(initial_stats, "Neon DB Status Before Dispatch")

    if not initial_stats or initial_stats["pending"] == 0:
        log("No pending companies found that require enrichment. Exiting.")
        return 0

    # Clamp total to available pending companies
    target_count = min(total_companies, initial_stats["pending"])
    batch_size = max(10, min(batch_size, 200))
    total_runs = (target_count + batch_size - 1) // batch_size

    print(f"=======================================================")
    print(f"  [START] Dispatching Cloud AI Enrichment for {target_count} Companies")
    print(f"  Total Workflow Runs : {total_runs} runners")
    print(f"  Batch Size per Run  : {batch_size} companies")
    print(f"  Repository Target   : {REPO}")
    print(f"=======================================================\n")

    dispatched = 0
    remaining = target_count

    for i in range(1, total_runs + 1):
        current_batch = min(batch_size, remaining)
        success = dispatch_enrichment_workflow(
            batch_size=current_batch,
            max_attempts=max_attempts,
            run_index=i,
            total_runs=total_runs
        )
        if success:
            dispatched += 1
            remaining -= current_batch
            if i < total_runs:
                time.sleep(delay)
        else:
            log(f"[Failed] Could not dispatch run {i}/{total_runs}")

    print("\n" + "=" * 65)
    print(f"  [DISPATCH COMPLETE] Successfully launched {dispatched}/{total_runs} cloud enrichment workflows!")
    print(f"  Targeted Companies : ~{target_count} records")
    print("=" * 65 + "\n")

    if monitor:
        monitor_progress(initial_stats["completed"], target_count)

    return dispatched


def monitor_progress(starting_completed: int, target_gain: int, poll_interval: int = 15, timeout_minutes: int = 30):
    """Monitors Neon DB live to show completed company enrichment progression."""
    log(f"Starting live progress monitor (polling every {poll_interval}s, timeout={timeout_minutes}m)...")
    start_time = time.time()
    max_duration = timeout_minutes * 60

    while time.time() - start_time < max_duration:
        time.sleep(poll_interval)
        stats = get_db_stats()
        if not stats:
            continue
        gained = stats["completed"] - starting_completed
        active = stats["in_progress"]
        percent = min(100.0, (max(0, gained) / max(1, target_gain)) * 100.0)
        elapsed_sec = int(time.time() - start_time)
        elapsed_str = f"{elapsed_sec // 60}m {elapsed_sec % 60}s"

        log(f"[Progress {elapsed_str}] Completed: +{gained}/{target_gain} ({percent:.1f}%) | Active In-Progress: {active} | Total Pending: {stats['pending']}")

        if gained >= target_gain and active == 0:
            log(f"[SUCCESS] Target enrichment of {target_gain} companies reached!")
            break

    final_stats = get_db_stats()
    print_stats_table(final_stats, "Neon DB Final Status After Enrichment")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OutreachPilot Cloud AI Enrichment Dispatcher")
    parser.add_argument("--total", type=int, default=500, help="Total companies to enrich (default: 500)")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size per GitHub Actions runner (default: 100)")
    parser.add_argument("--max-attempts", type=int, default=3, help="Max crawl attempts before incomplete (default: 3)")
    parser.add_argument("--delay", type=float, default=3.0, help="Seconds delay between workflow dispatches (default: 3.0)")
    parser.add_argument("--monitor", action="store_true", help="Monitor live progress in DB until finished")
    args = parser.parse_args()

    run_enrichment_dispatch(
        total_companies=args.total,
        batch_size=args.batch_size,
        max_attempts=args.max_attempts,
        delay=args.delay,
        monitor=args.monitor
    )
