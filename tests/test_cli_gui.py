from unittest.mock import patch

from automator.cli import build_parser


def test_gui_parses_default_host_and_port():
    parser = build_parser()
    args = parser.parse_args(["gui"])
    assert args.command == "gui"
    assert args.host == "127.0.0.1"
    assert args.port == 8420


def test_gui_parses_custom_host_and_port():
    parser = build_parser()
    args = parser.parse_args(["gui", "--host", "0.0.0.0", "--port", "9000"])
    assert args.host == "0.0.0.0"
    assert args.port == 9000


def test_gui_dispatches_to_run_gui():
    parser = build_parser()
    args = parser.parse_args(["gui", "--port", "9000"])
    with patch("gui.run_gui") as mock_run:
        args.func(args)
    mock_run.assert_called_once_with(host="127.0.0.1", port=9000)
