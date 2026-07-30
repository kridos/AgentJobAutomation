from automator.cli import build_parser


def test_log_parses_text_and_tags():
    parser = build_parser()
    args = parser.parse_args(["log", "Shipped a thing", "--tags", "backend,ai-ml"])
    assert args.command == "log"
    assert args.text == "Shipped a thing"
    assert args.tags == "backend,ai-ml"


def test_log_parses_without_tags():
    parser = build_parser()
    args = parser.parse_args(["log", "Shipped a thing"])
    assert args.text == "Shipped a thing"
    assert args.tags is None


def test_flush_parses():
    parser = build_parser()
    args = parser.parse_args(["flush"])
    assert args.command == "flush"
