"""Argparse-based dispatcher for the automator CLI."""

import argparse
import runpy
import sys


def _print_run_summary(stats: dict) -> None:
    print(
        f"\nDone. Processed: {stats['processed']} | Skipped: {stats['skipped_duplicate']} duplicates, "
        f"{stats['skipped_filter']} filtered | Errors: {len(stats['errors'])}"
    )
    if stats["errors"]:
        for e in stats["errors"]:
            print(f"  ERROR: {e}", file=sys.stderr)


def _cmd_run(args: argparse.Namespace) -> None:
    if args.schedule:
        _cmd_run_scheduled(args)
        return

    from pipeline import run_pipeline

    stats = run_pipeline(dry_run=args.dry_run, limit=args.limit)
    _print_run_summary(stats)


def _cmd_run_scheduled(args: argparse.Namespace) -> None:
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        print("APScheduler not installed. Run: pip install APScheduler", file=sys.stderr)
        sys.exit(1)

    from pipeline import run_pipeline

    def _run_and_report() -> None:
        stats = run_pipeline(dry_run=args.dry_run, limit=args.limit)
        _print_run_summary(stats)

    print(f"Starting scheduler — running pipeline every {args.interval_hours}h. Press Ctrl+C to stop.\n")
    _run_and_report()

    scheduler = BlockingScheduler()
    scheduler.add_job(
        _run_and_report,
        "interval",
        hours=args.interval_hours,
        id="pipeline",
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nScheduler stopped.")


def _cmd_manual(args: argparse.Namespace) -> None:
    from manual_run import run_manual

    run_manual()


def _cmd_archive(args: argparse.Namespace) -> None:
    from archive_processed import archive

    archive(clear=args.clear)


_TEST_MODULES = {
    "scraper": "scraper",
    "gmail": "gmail_reader",
    "generator": "generator",
    "researcher": "researcher",
}


def _cmd_test(args: argparse.Namespace) -> None:
    module_name = _TEST_MODULES[args.module]
    old_argv = sys.argv
    sys.argv = [module_name] + args.module_args
    try:
        runpy.run_module(module_name, run_name="__main__")
    finally:
        sys.argv = old_argv


def _cmd_gui(args: argparse.Namespace) -> None:
    print("GUI not built yet — coming in a later update")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="automator", description="Internship automation pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_p = subparsers.add_parser("run", help="Run the pipeline")
    run_p.add_argument("--dry-run", action="store_true", help="Scrape and filter only, skip generation")
    run_p.add_argument("--schedule", action="store_true", help="Run on a recurring schedule")
    run_p.add_argument("--interval-hours", type=int, default=24, help="Schedule interval in hours (default: 24)")
    run_p.add_argument("--limit", type=int, default=None, help="Stop after processing N listings")
    run_p.set_defaults(func=_cmd_run)

    manual_p = subparsers.add_parser("manual", help="Manually enter a single job listing")
    manual_p.set_defaults(func=_cmd_manual)

    archive_p = subparsers.add_parser("archive", help="Archive processed.json")
    archive_p.add_argument(
        "--keep", dest="clear", action="store_false", default=True,
        help="Archive without clearing processed.json (default: clear)",
    )
    archive_p.set_defaults(func=_cmd_archive)

    test_p = subparsers.add_parser("test", help="Run a module's self-test")
    test_p.add_argument("module", choices=sorted(_TEST_MODULES))
    test_p.add_argument("module_args", nargs="*", help="Extra args passed to the module's self-test")
    test_p.set_defaults(func=_cmd_test)

    gui_p = subparsers.add_parser("gui", help="Launch the GUI (not yet implemented)")
    gui_p.set_defaults(func=_cmd_gui)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
