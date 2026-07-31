import base64
import json

import httpx

import gmail_reader


class _FakeCreds:
    token = "fake-access-token"

    def __init__(self, valid=True, expired=False, refresh_token="rt"):
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token

    def refresh(self, request):
        self.valid = True
        self.expired = False

    def to_json(self):
        return json.dumps({"token": self.token})


def test_run_oauth_flow_returns_false_when_credentials_json_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gmail_reader, "CREDENTIALS_PATH", tmp_path / "credentials.json")

    result = gmail_reader.run_oauth_flow()

    assert result is False
    assert "credentials.json" in capsys.readouterr().err


def test_load_credentials_returns_none_when_no_token_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gmail_reader, "TOKEN_PATH", tmp_path / "token.json")

    result = gmail_reader._load_credentials()

    assert result is None
    assert "automator gmail auth" in capsys.readouterr().err


def test_load_credentials_refreshes_expired_token(tmp_path, monkeypatch):
    token_path = tmp_path / "token.json"
    token_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(gmail_reader, "TOKEN_PATH", token_path)

    fake_creds = _FakeCreds(valid=False, expired=True)
    monkeypatch.setattr(
        gmail_reader.Credentials, "from_authorized_user_file",
        classmethod(lambda cls, path, scopes: fake_creds),
    )

    result = gmail_reader._load_credentials()

    assert result is fake_creds
    assert result.valid is True
    assert token_path.read_text(encoding="utf-8") == fake_creds.to_json()


def test_auth_headers_returns_none_without_credentials(monkeypatch):
    monkeypatch.setattr(gmail_reader, "_load_credentials", lambda: None)

    assert gmail_reader._auth_headers() is None


def test_auth_headers_returns_bearer_token(monkeypatch):
    monkeypatch.setattr(gmail_reader, "_load_credentials", lambda: _FakeCreds())

    headers = gmail_reader._auth_headers()

    assert headers == {"Authorization": "Bearer fake-access-token"}


def test_search_messages_returns_empty_without_auth(monkeypatch):
    monkeypatch.setattr(gmail_reader, "_auth_headers", lambda: None)

    result = gmail_reader._search_messages("query", 5)

    assert result == []


def test_search_messages_lists_then_fetches_each_message(monkeypatch):
    monkeypatch.setattr(gmail_reader, "_auth_headers", lambda: {"Authorization": "Bearer x"})
    monkeypatch.setattr(gmail_reader, "_list_message_ids", lambda query, max_results, headers: ["m1", "m2"])
    monkeypatch.setattr(
        gmail_reader, "_get_message",
        lambda msg_id, headers: {"subject": f"Subject {msg_id}", "from": "a@b.com", "date": "", "body": "", "snippet": ""},
    )

    result = gmail_reader._search_messages("query", 5)

    assert [m["subject"] for m in result] == ["Subject m1", "Subject m2"]


def test_search_messages_skips_message_that_fails_to_fetch(monkeypatch, capsys):
    monkeypatch.setattr(gmail_reader, "_auth_headers", lambda: {"Authorization": "Bearer x"})
    monkeypatch.setattr(gmail_reader, "_list_message_ids", lambda query, max_results, headers: ["good", "bad"])

    def _fake_get_message(msg_id, headers):
        if msg_id == "bad":
            raise RuntimeError("boom")
        return {"subject": "ok", "from": "", "date": "", "body": "", "snippet": ""}

    monkeypatch.setattr(gmail_reader, "_get_message", _fake_get_message)

    result = gmail_reader._search_messages("query", 5)

    assert len(result) == 1
    assert "Skipping message bad" in capsys.readouterr().err


def test_extract_body_decodes_plain_text_part():
    text = "Hello world"
    encoded = base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")
    payload = {"mimeType": "text/plain", "body": {"data": encoded}}

    assert gmail_reader._extract_body(payload) == text


def test_extract_body_falls_back_to_stripped_html():
    html = "<p>Hello <b>world</b></p>"
    encoded = base64.urlsafe_b64encode(html.encode("utf-8")).decode("ascii")
    payload = {"mimeType": "multipart/alternative", "parts": [
        {"mimeType": "text/html", "body": {"data": encoded}},
    ]}

    result = gmail_reader._extract_body(payload)

    assert "Hello" in result and "world" in result
    assert "<p>" not in result


def test_create_draft_returns_false_without_auth(monkeypatch):
    monkeypatch.setattr(gmail_reader, "_auth_headers", lambda: None)

    result = gmail_reader.create_draft("jane@acme.com", "Subject", "Body text")

    assert result is False


def test_create_draft_returns_true_on_success(monkeypatch):
    monkeypatch.setattr(gmail_reader, "_auth_headers", lambda: {"Authorization": "Bearer x"})
    captured = {}

    def _fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        return httpx.Response(200, json={"id": "draft-1"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(gmail_reader.httpx, "post", _fake_post)

    result = gmail_reader.create_draft("jane@acme.com", "Subject", "Body text")

    assert result is True
    assert captured["url"] == f"{gmail_reader.GMAIL_API_BASE}/drafts"
    raw = captured["json"]["message"]["raw"]
    decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")
    assert "Subject" in decoded
    assert "Body text" in decoded


def test_create_draft_returns_false_on_api_error(monkeypatch):
    monkeypatch.setattr(gmail_reader, "_auth_headers", lambda: {"Authorization": "Bearer x"})

    def _fake_post(url, json, headers, timeout):
        return httpx.Response(400, json={"error": "bad request"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(gmail_reader.httpx, "post", _fake_post)

    result = gmail_reader.create_draft("jane@acme.com", "Subject", "Body text")

    assert result is False
