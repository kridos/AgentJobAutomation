from automator.cli import build_parser


def test_manual_parses():
    parser = build_parser()
    args = parser.parse_args(["manual"])
    assert args.command == "manual"


def test_archive_default_clears():
    parser = build_parser()
    args = parser.parse_args(["archive"])
    assert args.command == "archive"
    assert args.clear is True


def test_archive_keep_flag():
    parser = build_parser()
    args = parser.parse_args(["archive", "--keep"])
    assert args.clear is False
