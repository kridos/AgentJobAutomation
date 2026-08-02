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


def _cmd_log(args: argparse.Namespace) -> None:
    from accomplishments import log_entry

    try:
        log_entry(args.text, tags=args.tags)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print("Logged.")


def _cmd_flush(args: argparse.Namespace) -> None:
    from accomplishments import flush

    flush()


def _cmd_outreach_add(args: argparse.Namespace) -> None:
    from outreach import add_contact_interactive

    add_contact_interactive()


def _cmd_outreach_discover(args: argparse.Namespace) -> None:
    from outreach import discover_contacts

    stats = discover_contacts()
    print(f"\nDone. Found: {stats['found']} | Added: {stats['added']} | Skipped duplicates: {stats['skipped_duplicate']}")


def _cmd_outreach_confirm(args: argparse.Namespace) -> None:
    from outreach import confirm_contact_manual

    if confirm_contact_manual(args.contact_id, args.email):
        print(f"Confirmed {args.contact_id} — {args.email}")
    else:
        print(f"No contact found with id '{args.contact_id}'", file=sys.stderr)
        sys.exit(1)


def _cmd_outreach_run(args: argparse.Namespace) -> None:
    from outreach import run_outreach

    stats = run_outreach()
    print(
        f"\nDone. Drafted: {stats['drafted']} | Skipped: {stats['skipped']} | "
        f"Unconfirmed (held back): {stats['unconfirmed_skipped']} | Errors: {len(stats['errors'])}"
    )
    if stats["errors"]:
        for e in stats["errors"]:
            print(f"  ERROR: {e}", file=sys.stderr)


def _cmd_outreach_list(args: argparse.Namespace) -> None:
    from outreach import list_outreach_status

    statuses = list_outreach_status()
    if not statuses:
        print("No outreach contacts yet. Add one with: automator outreach add")
        return
    for s in statuses:
        confirmed_label = "confirmed" if s["confirmed"] else "unconfirmed"
        print(f"[{s['status']:8}] [{confirmed_label:11}] {s['company']} — {s['contact_email']}")


def _cmd_gmail_auth(args: argparse.Namespace) -> None:
    from gmail_reader import run_oauth_flow

    if not run_oauth_flow():
        sys.exit(1)


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
    from gui import run_gui

    run_gui(host=args.host, port=args.port)


def _cmd_prep(args: argparse.Namespace) -> None:
    from interview_prep import generate_interview_prep

    result = generate_interview_prep(args.company, role_hint=args.role or "")

    if result["status"] == "ok":
        print(f"Interview prep saved to: {result['path']}")
    elif result["status"] == "not_found":
        print(f"No application found for '{args.company}'. Run `automator run` first, or check the company name.", file=sys.stderr)
        sys.exit(1)
    elif result["status"] == "validation_blocked":
        print("Interview prep generation blocked by validation — unsupported claims could not be resolved after retry.", file=sys.stderr)
        sys.exit(1)
    elif result["status"] == "generation_failed":
        print("Interview prep generation failed — check that Ollama is running.", file=sys.stderr)
        sys.exit(1)


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

    log_p = subparsers.add_parser("log", help="Quick-capture a recent accomplishment")
    log_p.add_argument("text", help="What you did, in your own words")
    log_p.add_argument("--tags", default=None, help="Comma-separated tags, e.g. backend,ai-ml")
    log_p.set_defaults(func=_cmd_log)

    flush_p = subparsers.add_parser("flush", help="Promote staged accomplishments into the permanent record")
    flush_p.set_defaults(func=_cmd_flush)

    outreach_p = subparsers.add_parser("outreach", help="Cold-email outreach")
    outreach_sub = outreach_p.add_subparsers(dest="outreach_command", required=True)

    outreach_add_p = outreach_sub.add_parser("add", help="Manually add an outreach contact")
    outreach_add_p.set_defaults(func=_cmd_outreach_add)

    outreach_run_p = outreach_sub.add_parser("run", help="Generate and draft emails for pending contacts")
    outreach_run_p.set_defaults(func=_cmd_outreach_run)

    outreach_list_p = outreach_sub.add_parser("list", help="Show outreach contact status")
    outreach_list_p.set_defaults(func=_cmd_outreach_list)

    outreach_discover_p = outreach_sub.add_parser("discover", help="Discover new startup contacts (YC directory)")
    outreach_discover_p.set_defaults(func=_cmd_outreach_discover)

    outreach_confirm_p = outreach_sub.add_parser("confirm", help="Manually confirm/override a contact's email")
    outreach_confirm_p.add_argument("contact_id", help="The contact's id (see `automator outreach list`)")
    outreach_confirm_p.add_argument("email", help="The email address to set and confirm")
    outreach_confirm_p.set_defaults(func=_cmd_outreach_confirm)

    gmail_p = subparsers.add_parser("gmail", help="Gmail API setup")
    gmail_sub = gmail_p.add_subparsers(dest="gmail_command", required=True)

    gmail_auth_p = gmail_sub.add_parser("auth", help="One-time OAuth login (requires credentials.json)")
    gmail_auth_p.set_defaults(func=_cmd_gmail_auth)

    prep_p = subparsers.add_parser("prep", help="Generate interview prep material for an application")
    prep_p.add_argument("company", help="Company name (matches an existing application in output/)")
    prep_p.add_argument("--role", default="", help="Filter by role substring when multiple applications match")
    prep_p.set_defaults(func=_cmd_prep)

    test_p = subparsers.add_parser("test", help="Run a module's self-test")
    test_p.add_argument("module", choices=sorted(_TEST_MODULES))
    test_p.add_argument("module_args", nargs="*", help="Extra args passed to the module's self-test")
    test_p.set_defaults(func=_cmd_test)

    gui_p = subparsers.add_parser("gui", help="Launch the local applications/outreach/prep dashboard")
    gui_p.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    gui_p.add_argument("--port", type=int, default=8420, help="Port to bind (default: 8420)")
    gui_p.set_defaults(func=_cmd_gui)

    help_p = subparsers.add_parser("help", help="Show this help message")
    help_p.set_defaults(func=lambda args: parser.print_help())

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
