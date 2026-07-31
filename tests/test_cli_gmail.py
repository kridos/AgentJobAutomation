from automator.cli import build_parser


def test_gmail_auth_dispatches_to_run_oauth_flow_success(monkeypatch):
    monkeypatch.setattr("gmail_reader.run_oauth_flow", lambda: True)

    parser = build_parser()
    args = parser.parse_args(["gmail", "auth"])
    args.func(args)  # should not raise or exit


def test_gmail_auth_exits_nonzero_on_failure(monkeypatch):
    monkeypatch.setattr("gmail_reader.run_oauth_flow", lambda: False)

    parser = build_parser()
    args = parser.parse_args(["gmail", "auth"])

    try:
        args.func(args)
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code != 0
