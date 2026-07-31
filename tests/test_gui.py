import json
import threading
from http.client import HTTPConnection
from pathlib import Path

import gui


def _seed_app(date="2026-07-01", source="simplify", company="Acme Corp",
              role="SWE Intern", company_slug="acme_corp", role_slug="swe_intern",
              resume_md="# Resume\n", with_prep=False):
    app_dir = Path("output") / date / source / company_slug / role_slug
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "listing.json").write_text(
        json.dumps({"company": company, "role": role}), encoding="utf-8"
    )
    (app_dir / "quality_score.json").write_text(json.dumps({"overall": 90}), encoding="utf-8")
    (app_dir / "resume.md").write_text(resume_md, encoding="utf-8")
    (app_dir / "cover_letter.md").write_text("Dear team,\n", encoding="utf-8")
    if with_prep:
        (app_dir / "interview_prep.md").write_text("## Company Research\nStuff.\n", encoding="utf-8")
    return f"{date}/{source}/{company_slug}/{role_slug}"


def _running_server():
    server = gui.build_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _get(server, path):
    conn = HTTPConnection("127.0.0.1", server.server_address[1])
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read().decode("utf-8")
    conn.close()
    return resp.status, body


def _post(server, path, form_body):
    conn = HTTPConnection("127.0.0.1", server.server_address[1])
    conn.request("POST", path, body=form_body,
                  headers={"Content-Type": "application/x-www-form-urlencoded"})
    resp = conn.getresponse()
    body = resp.read().decode("utf-8")
    conn.close()
    return resp.status, resp.getheader("Location"), body


def test_root_lists_seeded_application(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_app()
    server = _running_server()
    try:
        status, body = _get(server, "/")
        assert status == 200
        assert "Acme Corp" in body
    finally:
        server.shutdown()
        server.server_close()


def test_application_detail_shows_resume_and_404_for_unknown(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app_id = _seed_app()
    server = _running_server()
    try:
        status, body = _get(server, f"/applications/{app_id}")
        assert status == 200
        assert "# Resume" in body

        status, _ = _get(server, "/applications/nope/nope/nope/nope")
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()


def test_post_status_updates_and_rejects_invalid_value(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app_id = _seed_app()
    server = _running_server()
    try:
        status, location, _ = _post(server, f"/applications/{app_id}/status", "status=applied")
        assert status == 303
        assert location == f"/applications/{app_id}"

        _, body = _get(server, f"/applications/{app_id}")
        assert "applied" in body

        status, _, _ = _post(server, f"/applications/{app_id}/status", "status=bogus")
        assert status == 400
    finally:
        server.shutdown()
        server.server_close()


def test_outreach_view_renders_contacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        gui, "list_outreach_status",
        lambda: [{"company": "Startup Co", "contact_email": "a@startup.co",
                   "status": "drafted", "confirmed": True}],
    )
    server = _running_server()
    try:
        status, body = _get(server, "/outreach")
        assert status == 200
        assert "Startup Co" in body
    finally:
        server.shutdown()
        server.server_close()


def test_prep_view_and_404_when_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with_prep = _seed_app(with_prep=True)
    without_prep = _seed_app(company="No Prep Co", company_slug="no_prep_co", role_slug="intern")
    server = _running_server()
    try:
        status, body = _get(server, f"/prep/{with_prep}")
        assert status == 200
        assert "Company Research" in body

        status, _ = _get(server, f"/prep/{without_prep}")
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()


def test_resume_content_is_html_escaped(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app_id = _seed_app(resume_md="<script>alert(1)</script>")
    server = _running_server()
    try:
        _, body = _get(server, f"/applications/{app_id}")
        assert "<script>alert(1)</script>" not in body
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
    finally:
        server.shutdown()
        server.server_close()
