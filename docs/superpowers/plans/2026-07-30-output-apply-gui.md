# Output/Apply Streamlining + GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `automator gui` starts a local dashboard (applications list/detail
with apply-status tracking, outreach status, interview prep viewer) built
entirely from files `automator run`/`outreach`/`prep` already produce.

**Architecture:** A data-only `applications.py` module (glob `output/`,
read/write small JSON files, no HTTP) and an `gui.py` HTTP layer built on
stdlib `http.server` that renders small hand-written HTML templates over
that data plus the existing `outreach.list_outreach_status()`. `automator
gui` in `automator/cli.py` wires it up.

**Tech Stack:** Python stdlib only (`http.server`, `html`, `urllib.parse`,
`pathlib`, `json`) — no new dependency.

## Global Constraints

- The server binds to `127.0.0.1` only — no auth, single local user. (spec: Non-goals)
- No new runtime dependency — stdlib `http.server`, not Flask or any templating library. (spec: Architecture)
- The GUI never edits resume/cover letter/prep content, and never triggers `automator run`/`outreach discover`/`outreach run`/`prep`. (spec: Non-goals)
- Every piece of resume/cover-letter/job-description/prep text rendered into HTML MUST pass through `html.escape()` before interpolation — this is LLM-generated text being rendered as HTML, and skipping escaping is a stored-XSS hole. (spec: Architecture)
- Application status is one of exactly `"applied"`, `"skipped"`, `"pending"`, defaulting to `"pending"` when no `status.json` exists yet. (spec: Architecture)
- `app_id` is the four-segment relative path `date/source/company_slug/role_slug` (matching `pipeline.py`'s existing `_slugify`, which uses underscores, not hyphens) and contains literal `/` characters — route handlers must treat it as "everything after the known prefix," not a single path segment. (spec: Architecture)

---

### Task 1: `applications.py` — data layer

**Files:**
- Create: `applications.py`
- Test: `tests/test_applications.py`

**Interfaces:**
- Produces:
  - `list_applications() -> list[dict]` — each dict has keys `id`, `company`, `role`, `source`, `date`, `score`, `status`, `has_prep`.
  - `get_application(app_id: str) -> dict | None` — same keys as one entry from `list_applications()`, plus `resume_md`, `cover_md`, `job_description` (each `""` if the file is missing).
  - `set_application_status(app_id: str, status: str) -> bool` — `True` on success, `False` if `status` isn't one of `applied`/`skipped`/`pending` or `app_id` doesn't resolve to a real application directory (no `listing.json` there).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_applications.py`:

```python
import json
from pathlib import Path

import applications


def _seed_app(date="2026-07-01", source="simplify", company="Acme Corp",
              role="SWE Intern", company_slug="acme_corp", role_slug="swe_intern",
              score=85, write_score=True):
    app_dir = Path("output") / date / source / company_slug / role_slug
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "listing.json").write_text(
        json.dumps({"company": company, "role": role}), encoding="utf-8"
    )
    if write_score:
        (app_dir / "quality_score.json").write_text(
            json.dumps({"overall": score}), encoding="utf-8"
        )
    (app_dir / "resume.md").write_text("# Resume\n- Did a thing\n", encoding="utf-8")
    (app_dir / "cover_letter.md").write_text("Dear team,\n\nHello.\n", encoding="utf-8")
    app_id = f"{date}/{source}/{company_slug}/{role_slug}"
    return app_dir, app_id


def test_list_applications_defaults_to_pending_and_reads_score(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_app()

    apps = applications.list_applications()

    assert len(apps) == 1
    app = apps[0]
    assert app["company"] == "Acme Corp"
    assert app["role"] == "SWE Intern"
    assert app["source"] == "simplify"
    assert app["date"] == "2026-07-01"
    assert app["score"] == 85
    assert app["status"] == "pending"
    assert app["has_prep"] is False


def test_list_applications_skips_malformed_listing_but_keeps_others(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    bad_dir, _ = _seed_app(company="Bad Co", company_slug="bad_co", role_slug="intern")
    (bad_dir / "listing.json").write_text("{not json", encoding="utf-8")
    _seed_app(company="Good Co", company_slug="good_co", role_slug="intern")

    apps = applications.list_applications()

    assert len(apps) == 1
    assert apps[0]["company"] == "Good Co"
    assert "malformed" in capsys.readouterr().err


def test_get_application_returns_none_for_unknown_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_app()

    assert applications.get_application("nope/nope/nope/nope") is None


def test_get_application_reads_file_contents_and_blank_job_description(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _, app_id = _seed_app()

    app = applications.get_application(app_id)

    assert app["resume_md"] == "# Resume\n- Did a thing\n"
    assert app["cover_md"] == "Dear team,\n\nHello.\n"
    assert app["job_description"] == ""


def test_set_application_status_round_trips(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _, app_id = _seed_app()

    ok = applications.set_application_status(app_id, "applied")

    assert ok is True
    apps = {a["id"]: a for a in applications.list_applications()}
    assert apps[app_id]["status"] == "applied"


def test_set_application_status_rejects_invalid_status_and_unknown_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _, app_id = _seed_app()

    assert applications.set_application_status(app_id, "bogus") is False
    assert applications.set_application_status("nope/nope/nope/nope", "applied") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_applications.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'applications'`

- [ ] **Step 3: Write `applications.py`**

```python
"""
Lists generated applications from output/, and tracks per-application
apply status (applied/skipped/pending) in status.json alongside each
application's generated files. Pure data layer — no HTTP here.
Run standalone: python applications.py
"""

import json
import sys
from pathlib import Path

_VALID_STATUSES = {"applied", "skipped", "pending"}


def _read_json(path: Path) -> tuple[dict | None, bool]:
    """Returns (data, ok). ok is False when the file exists but is malformed."""
    if not path.exists():
        return {}, True
    try:
        return json.loads(path.read_text(encoding="utf-8")), True
    except (json.JSONDecodeError, OSError):
        return None, False


def list_applications() -> list[dict]:
    output_base = Path("output")
    if not output_base.exists():
        return []

    apps = []
    for listing_path in output_base.glob("*/*/*/*/listing.json"):
        app_dir = listing_path.parent
        app_id = "/".join(app_dir.parts[-4:])

        listing, ok = _read_json(listing_path)
        if not ok:
            print(f"[applications] skipping {listing_path}: malformed JSON", file=sys.stderr)
            continue

        score, ok = _read_json(app_dir / "quality_score.json")
        if not ok:
            print(f"[applications] skipping {app_dir / 'quality_score.json'}: malformed JSON", file=sys.stderr)
            continue

        status_data, ok = _read_json(app_dir / "status.json")
        if not ok:
            print(f"[applications] skipping {app_dir / 'status.json'}: malformed JSON", file=sys.stderr)
            continue
        status = status_data.get("status", "pending")
        if status not in _VALID_STATUSES:
            status = "pending"

        date, source, company_slug, role_slug = app_dir.parts[-4:]
        apps.append({
            "id": app_id,
            "company": listing.get("company", company_slug),
            "role": listing.get("role", role_slug),
            "source": source,
            "date": date,
            "score": score.get("overall", 0),
            "status": status,
            "has_prep": (app_dir / "interview_prep.md").exists(),
        })

    apps.sort(key=lambda a: a["id"], reverse=True)
    return apps


def get_application(app_id: str) -> dict | None:
    apps = {a["id"]: a for a in list_applications()}
    if app_id not in apps:
        return None

    app = dict(apps[app_id])
    app_dir = Path("output") / app_id
    for field, filename in (("resume_md", "resume.md"), ("cover_md", "cover_letter.md"),
                             ("job_description", "job_description.txt")):
        path = app_dir / filename
        app[field] = path.read_text(encoding="utf-8") if path.exists() else ""
    return app


def set_application_status(app_id: str, status: str) -> bool:
    if status not in _VALID_STATUSES:
        return False
    app_dir = Path("output") / app_id
    if not (app_dir / "listing.json").exists():
        return False
    (app_dir / "status.json").write_text(json.dumps({"status": status}, indent=2), encoding="utf-8")
    return True


if __name__ == "__main__":
    for app in list_applications():
        print(f"{app['status']:8} {app['date']} {app['company']} — {app['role']}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_applications.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Add to `pyproject.toml`'s `py-modules`**

In `pyproject.toml`, add `"applications"` and `"gui"` to the `py-modules`
list now (both new top-level modules for this plan — adding both here
avoids a second edit in Task 3):

```toml
py-modules = [
    "pipeline", "generator", "researcher", "scraper", "gmail_reader",
    "job_fetcher", "factual_validator", "scorer", "archive_processed",
    "manual_run", "crawl4ai_scraper", "accomplishments", "outreach",
    "yc_scraper", "email_verify", "interview_prep", "interview_problems",
    "applications", "gui",
]
```

- [ ] **Step 6: Commit**

```bash
git add applications.py tests/test_applications.py pyproject.toml
git commit -m "feat: add applications.py data layer for the GUI dashboard"
```

---

### Task 2: `gui.py` — HTTP layer

**Files:**
- Create: `gui.py`
- Test: `tests/test_gui.py`

**Interfaces:**
- Consumes: `applications.list_applications`, `applications.get_application`, `applications.set_application_status` (Task 1); `outreach.list_outreach_status() -> list[dict]` with keys `company`, `contact_email`, `status`, `confirmed` (already implemented in `outreach.py`).
- Produces:
  - `build_server(host: str = "127.0.0.1", port: int = 8420) -> http.server.HTTPServer`
  - `run_gui(host: str = "127.0.0.1", port: int = 8420) -> None`

**Routes:**
- `GET /` — applications list
- `GET /applications/<id>` — application detail + status buttons
- `POST /applications/<id>/status` — body `status=applied|skipped|pending`, 303 redirect back to detail on success, 400 on invalid status/unknown id
- `GET /outreach` — outreach contact list (read-only)
- `GET /prep/<id>` — renders `interview_prep.md` if present, 404 otherwise
- Anything else — 404

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gui.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gui.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui'`

- [ ] **Step 3: Write `gui.py`**

```python
"""
Local, single-user web dashboard for reviewing generated applications,
outreach contacts, and interview prep material. Binds to 127.0.0.1 only —
no auth, not meant to be exposed beyond the local machine.
Run standalone: python gui.py
"""

import html
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from applications import list_applications, get_application, set_application_status
from outreach import list_outreach_status

_STYLE = (
    "<style>"
    "body{font-family:sans-serif;margin:2rem;}"
    "table{border-collapse:collapse;width:100%;}"
    "th,td{border:1px solid #ccc;padding:0.5rem;text-align:left;}"
    "nav a{margin-right:1rem;}"
    "pre{white-space:pre-wrap;background:#f5f5f5;padding:1rem;}"
    "form{display:inline;margin-right:0.5rem;}"
    "</style>"
)


def _layout(title: str, body: str) -> str:
    safe_title = html.escape(title)
    return (
        f"<!doctype html><html><head><title>{safe_title}</title>{_STYLE}</head><body>"
        '<nav><a href="/">Applications</a><a href="/outreach">Outreach</a></nav>'
        f"<h1>{safe_title}</h1>{body}</body></html>"
    )


def _render_applications_list() -> str:
    apps = list_applications()
    if not apps:
        return "<p>No applications yet — run <code>automator run</code> first.</p>"
    rows = []
    for a in apps:
        app_id = html.escape(a["id"])
        prep = f'<a href="/prep/{app_id}">view</a>' if a["has_prep"] else "-"
        rows.append(
            f'<tr><td><a href="/applications/{app_id}">{html.escape(a["company"])}</a></td>'
            f'<td>{html.escape(a["role"])}</td><td>{html.escape(a["date"])}</td>'
            f'<td>{a["score"]}</td><td>{html.escape(a["status"])}</td><td>{prep}</td></tr>'
        )
    return (
        "<table><tr><th>Company</th><th>Role</th><th>Date</th><th>Score</th>"
        "<th>Status</th><th>Prep</th></tr>" + "".join(rows) + "</table>"
    )


def _render_application_detail(app: dict) -> str:
    app_id = html.escape(app["id"])
    buttons = "".join(
        f'<form method="POST" action="/applications/{app_id}/status">'
        f'<input type="hidden" name="status" value="{s}">'
        f'<button type="submit">{s}</button></form>'
        for s in ("applied", "skipped", "pending")
    )
    jd = html.escape(app["job_description"]) or "(not fetched)"
    return (
        f'<p>Status: <strong>{html.escape(app["status"])}</strong> | Score: {app["score"]}</p>'
        f"<p>{buttons}</p>"
        f'<h2>Resume</h2><pre>{html.escape(app["resume_md"])}</pre>'
        f'<h2>Cover Letter</h2><pre>{html.escape(app["cover_md"])}</pre>'
        f"<h2>Job Description</h2><pre>{jd}</pre>"
    )


def _render_outreach_list() -> str:
    contacts = list_outreach_status()
    if not contacts:
        return "<p>No outreach contacts yet.</p>"
    rows = "".join(
        f'<tr><td>{html.escape(c["company"])}</td><td>{html.escape(c["contact_email"])}</td>'
        f'<td>{html.escape(c["status"])}</td><td>{c["confirmed"]}</td></tr>'
        for c in contacts
    )
    return (
        "<table><tr><th>Company</th><th>Email</th><th>Status</th><th>Confirmed</th></tr>"
        + rows + "</table>"
    )


class _Handler(BaseHTTPRequestHandler):
    def _send_html(self, status: int, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _not_found(self, message: str = "Not found.") -> None:
        self._send_html(404, _layout("Not Found", f"<p>{message}</p>"))

    def do_GET(self) -> None:
        path = self.path
        if path == "/":
            self._send_html(200, _layout("Applications", _render_applications_list()))
        elif path == "/outreach":
            self._send_html(200, _layout("Outreach", _render_outreach_list()))
        elif path.startswith("/applications/"):
            app_id = path[len("/applications/"):]
            app = get_application(app_id)
            if app is None:
                self._not_found("No such application.")
                return
            title = f'{app["company"]} — {app["role"]}'
            self._send_html(200, _layout(title, _render_application_detail(app)))
        elif path.startswith("/prep/"):
            app_id = path[len("/prep/"):]
            prep_path = Path("output") / app_id / "interview_prep.md"
            if not prep_path.exists():
                self._not_found(
                    f'No interview prep generated yet. Run <code>automator prep</code> for this application.'
                )
                return
            body = f"<pre>{html.escape(prep_path.read_text(encoding='utf-8'))}</pre>"
            self._send_html(200, _layout("Interview Prep", body))
        else:
            self._not_found()

    def do_POST(self) -> None:
        path = self.path
        if path.startswith("/applications/") and path.endswith("/status"):
            app_id = path[len("/applications/"):-len("/status")]
            length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(length).decode("utf-8")
            status = parse_qs(raw_body).get("status", [""])[0]
            if set_application_status(app_id, status):
                self.send_response(303)
                self.send_header("Location", f"/applications/{app_id}")
                self.end_headers()
            else:
                self._send_html(400, _layout("Bad Request", "<p>Invalid status or unknown application.</p>"))
            return
        self._not_found()

    def log_message(self, format, *args):
        pass


def build_server(host: str = "127.0.0.1", port: int = 8420) -> HTTPServer:
    return HTTPServer((host, port), _Handler)


def run_gui(host: str = "127.0.0.1", port: int = 8420) -> None:
    server = build_server(host, port)
    print(f"[gui] Serving on http://{host}:{port}/ — Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run_gui()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_gui.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add gui.py tests/test_gui.py
git commit -m "feat: add gui.py stdlib HTTP dashboard for applications/outreach/prep"
```

---

### Task 3: Wire `automator gui` into the CLI

**Files:**
- Modify: `automator/cli.py:153-155` (`_cmd_gui`), `automator/cli.py:234-235` (`gui_p` parser)
- Modify: `tests/test_cli_gui.py` (replace stub-only assertions)
- Modify: `README.md` (add `automator gui` usage)

**Interfaces:**
- Consumes: `gui.run_gui(host: str, port: int) -> None` (Task 2)

- [ ] **Step 1: Write the failing test**

Replace the full contents of `tests/test_cli_gui.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_gui.py -v`
Expected: FAIL — `test_gui_parses_default_host_and_port` fails with
`AttributeError: 'Namespace' object has no attribute 'host'` (the `gui`
subparser doesn't accept `--host`/`--port` yet), and
`test_gui_dispatches_to_run_gui` fails because `_cmd_gui` doesn't call
`gui.run_gui`.

- [ ] **Step 3: Update `_cmd_gui` and the `gui` subparser**

In `automator/cli.py`, replace the stub `_cmd_gui` (currently at
lines 153-155):

```python
def _cmd_gui(args: argparse.Namespace) -> None:
    from gui import run_gui

    run_gui(host=args.host, port=args.port)
```

Replace the `gui_p` block (currently at lines 234-235):

```python
    gui_p = subparsers.add_parser("gui", help="Launch the local applications/outreach/prep dashboard")
    gui_p.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    gui_p.add_argument("--port", type=int, default=8420, help="Port to bind (default: 8420)")
    gui_p.set_defaults(func=_cmd_gui)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli_gui.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: PASS, all tests including Tasks 1 and 2's new tests.

- [ ] **Step 6: Add `automator gui` usage to README.md**

Find the section documenting `automator prep` usage in `README.md` (added
during the interview-prep sub-project) and add a similar block after it:

```markdown
### Review applications and mark status

```bash
automator gui
```

Starts a local dashboard at http://127.0.0.1:8420/ — browse generated
applications (resume, cover letter, job description), mark each as
applied/skipped/pending, view outreach contact status, and view generated
interview prep material. Local-only (binds to 127.0.0.1); does not submit
applications or trigger generation — run `automator run`/`outreach`/`prep`
for that.
```
```

- [ ] **Step 7: Commit**

```bash
git add automator/cli.py tests/test_cli_gui.py README.md
git commit -m "feat: wire automator gui into the CLI"
```

---

## Self-Review Notes

**Spec coverage:** Applications list/detail/status (Task 1 + Task 2 routes)
✅, outreach view (Task 2, reuses `outreach.list_outreach_status`) ✅, prep
view (Task 2) ✅, `automator gui` CLI wiring with `--host`/`--port` (Task 3)
✅, XSS-safety via `html.escape` (Task 2, tested explicitly) ✅, malformed-
file resilience (Task 1, tested explicitly) ✅, `pyproject.toml` py-modules
update (Task 1 Step 5, both new modules added together) ✅, README update
(Task 3 Step 6) ✅. No spec requirement found without a task.

**Placeholder scan:** none found — every step has runnable code.

**Fixed during self-review:** an earlier draft of Task 2's `gui.py` had a
redundant, buggy module-level `_render_prep` helper (leftover from before
prep-rendering was inlined into `do_GET`) with a dead, unreachable branch.
Removed it from the plan entirely rather than describing removing it —
`do_GET` is the only place prep rendering happens.

**Type consistency:** `app_id` is a `str` everywhere (Task 1's
`list_applications`/`get_application`/`set_application_status`, Task 2's
route handlers, Task 3's CLI args are unrelated `host`/`port`). `status`
is always one of the three string literals. `list_outreach_status()`'s
return shape (`company`, `contact_email`, `status`, `confirmed`) matches
what `_render_outreach_list` in Task 2 reads — verified against the
existing `outreach.py:list_outreach_status` implementation.
