from automator.cli import build_parser


def test_outreach_add_dispatches_to_add_contact_interactive(monkeypatch):
    calls = []
    monkeypatch.setattr("outreach.add_contact_interactive", lambda: calls.append(1))

    parser = build_parser()
    args = parser.parse_args(["outreach", "add"])
    args.func(args)

    assert calls == [1]


def test_outreach_run_dispatches_to_run_outreach(monkeypatch, capsys):
    monkeypatch.setattr("outreach.run_outreach", lambda: {"drafted": 2, "skipped": 1, "unconfirmed_skipped": 0, "errors": []})

    parser = build_parser()
    args = parser.parse_args(["outreach", "run"])
    args.func(args)

    captured = capsys.readouterr()
    assert "Drafted: 2" in captured.out
    assert "Skipped: 1" in captured.out


def test_outreach_list_prints_status(monkeypatch, capsys):
    monkeypatch.setattr(
        "outreach.list_outreach_status",
        lambda: [{"company": "Acme Corp", "contact_email": "jane@acme.com", "status": "pending", "confirmed": True}],
    )

    parser = build_parser()
    args = parser.parse_args(["outreach", "list"])
    args.func(args)

    captured = capsys.readouterr()
    assert "Acme Corp" in captured.out
    assert "pending" in captured.out


def test_outreach_list_handles_empty_list(monkeypatch, capsys):
    monkeypatch.setattr("outreach.list_outreach_status", lambda: [])

    parser = build_parser()
    args = parser.parse_args(["outreach", "list"])
    args.func(args)

    captured = capsys.readouterr()
    assert "No outreach contacts yet" in captured.out
