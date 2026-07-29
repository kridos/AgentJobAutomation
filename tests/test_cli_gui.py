import io
from contextlib import redirect_stdout

from automator.cli import build_parser


def test_gui_parses():
    parser = build_parser()
    args = parser.parse_args(["gui"])
    assert args.command == "gui"


def test_gui_prints_stub_message():
    parser = build_parser()
    args = parser.parse_args(["gui"])
    buf = io.StringIO()
    with redirect_stdout(buf):
        args.func(args)
    assert "not built yet" in buf.getvalue()
