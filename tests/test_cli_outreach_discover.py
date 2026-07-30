import pytest

from automator.cli import build_parser


def test_outreach_discover_dispatches_to_discover_contacts(monkeypatch, capsys):
    monkeypatch.setattr("outreach.discover_contacts", lambda: {"found": 5, "added": 3, "skipped_duplicate": 2})

    parser = build_parser()
    args = parser.parse_args(["outreach", "discover"])
    args.func(args)

    captured = capsys.readouterr()
    assert "Found: 5" in captured.out
    assert "Added: 3" in captured.out


def test_outreach_confirm_dispatches_to_confirm_contact_manual_success(monkeypatch, capsys):
    monkeypatch.setattr("outreach.confirm_contact_manual", lambda contact_id, email: True)

    parser = build_parser()
    args = parser.parse_args(["outreach", "confirm", "acme-corp", "real@acme.com"])
    args.func(args)

    captured = capsys.readouterr()
    assert "Confirmed acme-corp" in captured.out


def test_outreach_confirm_exits_nonzero_on_unknown_id(monkeypatch):
    monkeypatch.setattr("outreach.confirm_contact_manual", lambda contact_id, email: False)

    parser = build_parser()
    args = parser.parse_args(["outreach", "confirm", "nonexistent", "x@x.com"])

    with pytest.raises(SystemExit):
        args.func(args)


def test_outreach_list_shows_confirmed_status(monkeypatch, capsys):
    monkeypatch.setattr(
        "outreach.list_outreach_status",
        lambda: [{"company": "Acme Corp", "contact_email": "jane@acme.com", "status": "pending", "confirmed": False}],
    )

    parser = build_parser()
    args = parser.parse_args(["outreach", "list"])
    args.func(args)

    captured = capsys.readouterr()
    assert "unconfirmed" in captured.out


def test_outreach_run_shows_unconfirmed_skipped_count(monkeypatch, capsys):
    monkeypatch.setattr(
        "outreach.run_outreach",
        lambda: {"drafted": 1, "skipped": 0, "unconfirmed_skipped": 2, "errors": []},
    )

    parser = build_parser()
    args = parser.parse_args(["outreach", "run"])
    args.func(args)

    captured = capsys.readouterr()
    assert "Unconfirmed" in captured.out
    assert "2" in captured.out
