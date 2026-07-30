import subprocess

import email_verify


def test_guess_email_candidates_returns_generic_prefixes():
    result = email_verify._guess_email_candidates("acme.com")

    assert "founders@acme.com" in result
    assert "hello@acme.com" in result
    assert "hi@acme.com" in result
    assert "team@acme.com" in result
    assert "info@acme.com" in result


def test_resolve_mx_host_parses_dig_output(monkeypatch):
    class _FakeResult:
        returncode = 0
        stdout = "10 mail1.acme.com.\n20 mail2.acme.com.\n"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeResult())

    result = email_verify._resolve_mx_host("acme.com")

    assert result == "mail1.acme.com"


def test_resolve_mx_host_returns_empty_when_dig_fails(monkeypatch):
    class _FakeResult:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeResult())

    result = email_verify._resolve_mx_host("acme.com")

    assert result == ""


def test_resolve_mx_host_returns_empty_on_exception(monkeypatch):
    def _raise(*a, **k):
        raise FileNotFoundError("dig not found")

    monkeypatch.setattr(subprocess, "run", _raise)

    result = email_verify._resolve_mx_host("acme.com")

    assert result == ""


def test_verify_email_smtp_returns_true_on_accepted_rcpt(monkeypatch):
    monkeypatch.setattr(email_verify, "_resolve_mx_host", lambda domain: "mail.acme.com")

    class _FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def ehlo_or_helo_if_needed(self): pass
        def mail(self, addr): pass
        def rcpt(self, addr): return (250, b"OK")

    monkeypatch.setattr("smtplib.SMTP", _FakeSMTP)

    result = email_verify._verify_email_smtp("founders@acme.com")

    assert result is True


def test_verify_email_smtp_returns_false_on_rejected_rcpt(monkeypatch):
    monkeypatch.setattr(email_verify, "_resolve_mx_host", lambda domain: "mail.acme.com")

    class _FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def ehlo_or_helo_if_needed(self): pass
        def mail(self, addr): pass
        def rcpt(self, addr): return (550, b"No such user")

    monkeypatch.setattr("smtplib.SMTP", _FakeSMTP)

    result = email_verify._verify_email_smtp("nonexistent@acme.com")

    assert result is False


def test_verify_email_smtp_returns_false_when_no_mx_host(monkeypatch):
    monkeypatch.setattr(email_verify, "_resolve_mx_host", lambda domain: "")

    result = email_verify._verify_email_smtp("founders@acme.com")

    assert result is False


def test_verify_email_smtp_returns_false_on_connection_exception(monkeypatch):
    monkeypatch.setattr(email_verify, "_resolve_mx_host", lambda domain: "mail.acme.com")

    class _RaisingSMTP:
        def __init__(self, *a, **k):
            raise ConnectionRefusedError("refused")

    monkeypatch.setattr("smtplib.SMTP", _RaisingSMTP)

    result = email_verify._verify_email_smtp("founders@acme.com")

    assert result is False


def test_guess_and_verify_email_returns_first_verified(monkeypatch):
    monkeypatch.setattr(
        email_verify, "_verify_email_smtp",
        lambda email: email == "hello@acme.com",
    )

    email, confirmed = email_verify.guess_and_verify_email("acme.com")

    assert email == "hello@acme.com"
    assert confirmed is True


def test_guess_and_verify_email_returns_first_candidate_when_none_verify(monkeypatch):
    monkeypatch.setattr(email_verify, "_verify_email_smtp", lambda email: False)

    email, confirmed = email_verify.guess_and_verify_email("acme.com")

    assert email == "founders@acme.com"
    assert confirmed is False
