from automator.cli import build_parser


def test_run_parses_flags():
    parser = build_parser()
    args = parser.parse_args(["run", "--dry-run", "--limit", "5"])
    assert args.command == "run"
    assert args.dry_run is True
    assert args.limit == 5
    assert args.schedule is False
    assert args.interval_hours == 24


def test_run_defaults():
    parser = build_parser()
    args = parser.parse_args(["run"])
    assert args.dry_run is False
    assert args.limit is None
