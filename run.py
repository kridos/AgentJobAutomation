"""
Entrypoint for the internship automation pipeline.

  python run.py            — run once
  python run.py --dry-run  — scrape and filter only, no generation
  python run.py --schedule — run every 24h via APScheduler
"""

import argparse
import sys


def _run_once(dry_run: bool = False) -> None:
    from pipeline import run_pipeline
    stats = run_pipeline(dry_run=dry_run)
    print(f"\nDone. Processed: {stats['processed']} | Skipped: {stats['skipped_duplicate']} duplicates, "
          f"{stats['skipped_filter']} filtered | Errors: {len(stats['errors'])}")
    if stats["errors"]:
        for e in stats["errors"]:
            print(f"  ERROR: {e}", file=sys.stderr)


def _run_scheduled(interval_hours: int = 24) -> None:
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        print("APScheduler not installed. Run: pip install APScheduler", file=sys.stderr)
        sys.exit(1)

    print(f"Starting scheduler — running pipeline every {interval_hours}h. Press Ctrl+C to stop.\n")
    _run_once()  # Run immediately on start

    scheduler = BlockingScheduler()
    scheduler.add_job(_run_once, "interval", hours=interval_hours, id="pipeline")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nScheduler stopped.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Internship automation pipeline")
    parser.add_argument("--schedule", action="store_true", help="Run on a 24h schedule")
    parser.add_argument("--dry-run", action="store_true", help="Scrape and filter only, skip generation")
    parser.add_argument("--interval-hours", type=int, default=24, help="Schedule interval in hours (default: 24)")
    args = parser.parse_args()

    if args.schedule:
        _run_scheduled(interval_hours=args.interval_hours)
    else:
        _run_once(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
