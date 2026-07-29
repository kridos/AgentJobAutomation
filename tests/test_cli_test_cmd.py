import runpy

from automator.cli import build_parser


def test_test_parses_module_and_args():
    parser = build_parser()
    args = parser.parse_args(["test", "gmail", "Google"])
    assert args.command == "test"
    assert args.module == "gmail"
    assert args.module_args == ["Google"]


def test_test_rejects_unknown_module():
    parser = build_parser()
    try:
        parser.parse_args(["test", "not-a-real-module"])
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_cmd_test_dispatches_to_runpy(monkeypatch):
    from automator import cli

    calls = []

    def fake_run_module(name, run_name):
        calls.append((name, run_name))

    monkeypatch.setattr(runpy, "run_module", fake_run_module)
    monkeypatch.setattr(cli, "runpy", runpy)

    parser = build_parser()
    args = parser.parse_args(["test", "gmail", "Google"])
    args.func(args)

    assert calls == [("gmail_reader", "__main__")]
