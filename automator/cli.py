"""Argparse-based dispatcher for the automator CLI."""

import argparse
import sys


def _cmd_run(args: argparse.Namespace) -> None:
    from pipeline import run_pipeline

    if args.schedule:
        _cmd_run_scheduled(args)
        return

    stats = run_pipeline(dry_run=args.dry_run, limit=args.limit)
    print(
        f"\nDone. Processed: {stats['processed']} | Skipped: {stats['skipped_duplicate']} duplicates, "
        f"{stats['skipped_filter']} filtered | Errors: {len(stats['errors'])}"
    )
    if stats["errors"]:
        for e in stats["errors"]:
            print(f"  ERROR: {e}", file=sys.stderr)


def _cmd_run_scheduled(args: argparse.Namespace) -> None:
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        print("APScheduler not installed. Run: pip install APScheduler", file=sys.stderr)
        sys.exit(1)

    from pipeline import run_pipeline

    print(f"Starting scheduler — running pipeline every {args.interval_hours}h. Press Ctrl+C to stop.\n")
    run_pipeline(dry_run=args.dry_run, limit=args.limit)

    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_pipeline,
        "interval",
        hours=args.interval_hours,
        kwargs={"dry_run": args.dry_run, "limit": args.limit},
        id="pipeline",
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nScheduler stopped.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="automator", description="Internship automation pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_p = subparsers.add_parser("run", help="Run the pipeline")
    run_p.add_argument("--dry-run", action="store_true", help="Scrape and filter only, skip generation")
    run_p.add_argument("--schedule", action="store_true", help="Run on a recurring schedule")
    run_p.add_argument("--interval-hours", type=int, default=24, help="Schedule interval in hours (default: 24)")
    run_p.add_argument("--limit", type=int, default=None, help="Stop after processing N listings")
    run_p.set_defaults(func=_cmd_run)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
