"""
Local, single-user web dashboard exposing the same functionality as the
`automator` CLI: reviewing/generating applications, outreach, interview
prep, and logging accomplishments. Binds to 127.0.0.1 only — no auth, not
meant to be exposed beyond the local machine.
Run standalone: python gui.py
"""

import html
import threading
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
    "form.block{display:block;margin:1rem 0;}"
    "form.block label{display:block;margin-top:0.5rem;}"
    "form.block input[type=text],form.block input[type=email],form.block textarea"
    "{width:100%;max-width:32rem;box-sizing:border-box;}"
    ".banner{padding:0.75rem;margin-bottom:1rem;background:#eef;border:1px solid #99c;}"
    ".banner.busy{background:#ffe;border-color:#cc9;}"
    "</style>"
)


# ---------------------------------------------------------------------------
# Background job runner — actions that scrape or call an LLM run on a
# thread so the single-threaded HTTPServer stays responsive. Only one job
# runs at a time; a second trigger is rejected rather than queued.
# ---------------------------------------------------------------------------
_jobs_lock = threading.Lock()
_job_status: dict[str, dict] = {}


def _start_job(name: str, fn, *args) -> bool:
    """Runs fn(*args) on a background thread under key `name`. Returns False
    (without starting) if a job is already running."""
    with _jobs_lock:
        if _job_status.get(name, {}).get("running"):
            return False
        _job_status[name] = {"running": True, "message": f"{name} started..."}

    def _worker():
        try:
            result = fn(*args)
            message = str(result) if result is not None else f"{name} finished."
        except Exception as e:
            message = f"{name} failed: {e}"
        with _jobs_lock:
            _job_status[name] = {"running": False, "message": message}

    threading.Thread(target=_worker, daemon=True).start()
    return True


def _jobs_banner() -> str:
    with _jobs_lock:
        items = list(_job_status.items())
    if not items:
        return ""
    parts = []
    for name, s in items:
        cls = "banner busy" if s["running"] else "banner"
        parts.append(f'<div class="{cls}">[{html.escape(name)}] {html.escape(s["message"])}</div>')
    return "".join(parts)


def _layout(title: str, body: str) -> str:
    safe_title = html.escape(title)
    return (
        f"<!doctype html><html><head><title>{safe_title}</title>{_STYLE}</head><body>"
        '<nav><a href="/">Applications</a><a href="/outreach">Outreach</a>'
        '<a href="/log">Log</a><a href="/help">Help</a></nav>'
        f"<h1>{safe_title}</h1>{_jobs_banner()}{body}</body></html>"
    )


def _safe_link(url: str) -> str:
    """Returns url if it's http(s), else "" — hrefs can carry javascript:
    XSS that plain html.escape() doesn't neutralize, so scheme-check first."""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return ""


def _render_applications_list() -> str:
    apps = list_applications()
    controls = (
        '<form class="block" method="POST" action="/run">'
        '<label>Limit (optional) <input type="text" name="limit" size="4"></label>'
        '<label><input type="checkbox" name="dry_run" value="1"> Dry run (scrape/filter only)</label>'
        '<button type="submit">Run pipeline</button>'
        "</form>"
        '<form method="POST" action="/archive">'
        '<button type="submit">Archive processed.json</button>'
        "</form>"
        '<a href="/manual">Manual entry &rarr;</a>'
    )
    if not apps:
        return controls + "<p>No applications yet — run the pipeline above, or run <code>automator run</code>.</p>"
    rows = []
    for a in apps:
        app_id = html.escape(a["id"])
        prep = f'<a href="/prep/{app_id}">view</a>' if a["has_prep"] else (
            f'<form method="POST" action="/prep/{app_id}"><button type="submit">generate</button></form>'
        )
        link = _safe_link(a.get("link", ""))
        apply_link = f'<a href="{html.escape(link)}" target="_blank" rel="noopener">apply</a>' if link else "-"
        rows.append(
            f'<tr><td><a href="/applications/{app_id}">{html.escape(a["company"])}</a></td>'
            f'<td>{html.escape(a["role"])}</td><td>{html.escape(a["date"])}</td>'
            f'<td>{html.escape(str(a["score"]))}</td><td>{html.escape(a["status"])}</td>'
            f'<td>{prep}</td><td>{apply_link}</td></tr>'
        )
    table = (
        "<table><tr><th>Company</th><th>Role</th><th>Date</th><th>Score</th>"
        "<th>Status</th><th>Prep</th><th>Apply</th></tr>" + "".join(rows) + "</table>"
    )
    return controls + table


def _render_application_detail(app: dict) -> str:
    app_id = html.escape(app["id"])
    buttons = "".join(
        f'<form method="POST" action="/applications/{app_id}/status">'
        f'<input type="hidden" name="status" value="{s}">'
        f'<button type="submit">{s}</button></form>'
        for s in ("applied", "skipped", "pending")
    )
    link = _safe_link(app.get("link", ""))
    apply_link = (
        f'<p><a href="{html.escape(link)}" target="_blank" rel="noopener">Apply on company site &rarr;</a></p>'
        if link else ""
    )
    prep_link = (
        f'<p><a href="/prep/{app_id}">View interview prep &rarr;</a></p>' if app["has_prep"]
        else f'<form method="POST" action="/prep/{app_id}"><button type="submit">Generate interview prep</button></form>'
    )
    jd = html.escape(app["job_description"]) or "(not fetched)"
    return (
        f'<p>Status: <strong>{html.escape(app["status"])}</strong> | Score: {html.escape(str(app["score"]))}</p>'
        f"{apply_link}"
        f"<p>{buttons}</p>"
        f"{prep_link}"
        f'<h2>Resume</h2><pre>{html.escape(app["resume_md"])}</pre>'
        f'<h2>Cover Letter</h2><pre>{html.escape(app["cover_md"])}</pre>'
        f"<h2>Job Description</h2><pre>{jd}</pre>"
    )


def _render_manual_form() -> str:
    return (
        '<form class="block" method="POST" action="/manual">'
        '<label>Company name <input type="text" name="company" required></label>'
        '<label>Role / job title <input type="text" name="role" required></label>'
        '<label>Location (optional) <input type="text" name="location"></label>'
        '<label>Job posting URL (optional) <input type="text" name="link"></label>'
        '<label>Date posted (optional) <input type="text" name="date_posted" placeholder="YYYY-MM-DD"></label>'
        '<label>Job description / posting text <textarea name="job_description" rows="8"></textarea></label>'
        '<label>Extra context (recruiter notes, referral info, etc.) '
        '<textarea name="extra_context" rows="4"></textarea></label>'
        '<button type="submit">Generate</button>'
        "</form>"
    )


def _render_outreach_list() -> str:
    contacts = list_outreach_status()
    controls = (
        '<form method="POST" action="/outreach/discover"><button type="submit">Discover new contacts (YC)</button></form>'
        '<form method="POST" action="/outreach/run"><button type="submit">Run outreach (draft emails)</button></form>'
    )
    add_form = (
        '<h2>Add contact</h2>'
        '<form class="block" method="POST" action="/outreach/add">'
        '<label>Company name <input type="text" name="company" required></label>'
        '<label>Contact name (optional) <input type="text" name="contact_name"></label>'
        '<label>Contact email <input type="email" name="contact_email" required></label>'
        '<label>Notes (optional) <textarea name="notes" rows="3"></textarea></label>'
        '<button type="submit">Add</button>'
        "</form>"
    )
    if not contacts:
        return controls + add_form + "<p>No outreach contacts yet.</p>"
    rows = []
    for c in contacts:
        confirm_cell = (
            "yes" if c["confirmed"] else
            f'<form method="POST" action="/outreach/confirm">'
            f'<input type="hidden" name="contact_id" value="{html.escape(c["id"])}">'
            f'<input type="email" name="email" placeholder="confirm email" required>'
            f'<button type="submit">confirm</button></form>'
        )
        rows.append(
            f'<tr><td>{html.escape(c["company"])}</td><td>{html.escape(c["contact_email"])}</td>'
            f'<td>{html.escape(c["status"])}</td><td>{confirm_cell}</td></tr>'
        )
    table = (
        "<table><tr><th>Company</th><th>Email</th><th>Status</th><th>Confirmed</th></tr>"
        + "".join(rows) + "</table>"
    )
    return controls + table + add_form


def _render_log_page() -> str:
    from accomplishments import _recent_updates_path

    log_form = (
        '<form class="block" method="POST" action="/log">'
        '<label>What did you do? <input type="text" name="text" required></label>'
        '<label>Tags (optional, comma-separated) <input type="text" name="tags" placeholder="backend,ai-ml"></label>'
        '<button type="submit">Log</button>'
        "</form>"
        '<form method="POST" action="/flush"><button type="submit">Flush staged entries to permanent record</button></form>'
    )
    recent_path = _recent_updates_path(Path(__file__).parent)
    staged = recent_path.read_text(encoding="utf-8") if recent_path.exists() else ""
    staged_block = f"<h2>Staged entries</h2><pre>{html.escape(staged) or '(none)'}</pre>"
    return log_form + staged_block


def _render_help_page() -> str:
    from automator.cli import build_parser

    return f"<pre>{html.escape(build_parser().format_help())}</pre>"


class _Handler(BaseHTTPRequestHandler):
    def _send_html(self, status: int, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def _not_found(self, message: str = "Not found.") -> None:
        self._send_html(404, _layout("Not Found", f"<p>{message}</p>"))

    def _host_header_valid(self) -> bool:
        expected = f"{self.server.gui_host}:{self.server.gui_port}"
        # Loopback tools are commonly addressed as either 127.0.0.1 or
        # localhost regardless of the bind host, so accept both.
        allowed = {expected, f"localhost:{self.server.gui_port}"}
        return self.headers.get("Host", "") in allowed

    def _read_form(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length).decode("utf-8")
        parsed = parse_qs(raw_body)
        return {k: v[0] for k, v in parsed.items()}

    def do_GET(self) -> None:
        if not self._host_header_valid():
            self._send_html(403, _layout("Forbidden", "<p>Invalid Host header.</p>"))
            return
        try:
            path = self.path
            if path == "/":
                self._send_html(200, _layout("Applications", _render_applications_list()))
            elif path == "/manual":
                self._send_html(200, _layout("Manual Entry", _render_manual_form()))
            elif path == "/outreach":
                self._send_html(200, _layout("Outreach", _render_outreach_list()))
            elif path == "/log":
                self._send_html(200, _layout("Log", _render_log_page()))
            elif path == "/help":
                self._send_html(200, _layout("Help", _render_help_page()))
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
                app = get_application(app_id)
                if app is None:
                    self._not_found("No such application.")
                    return
                prep_path = Path("output") / app_id / "interview_prep.md"
                if not prep_path.exists():
                    self._not_found(
                        'No interview prep generated yet. Use the "Generate interview prep" button on the application page.'
                    )
                    return
                body = f"<pre>{html.escape(prep_path.read_text(encoding='utf-8'))}</pre>"
                self._send_html(200, _layout("Interview Prep", body))
            else:
                self._not_found()
        except Exception:
            self._send_html(500, _layout("Server Error", "<p>An unexpected error occurred.</p>"))

    def do_POST(self) -> None:
        if not self._host_header_valid():
            self._send_html(403, _layout("Forbidden", "<p>Invalid Host header.</p>"))
            return
        try:
            path = self.path
            if path.startswith("/applications/") and path.endswith("/status"):
                app_id = path[len("/applications/"):-len("/status")]
                form = self._read_form()
                if set_application_status(app_id, form.get("status", "")):
                    self._redirect(f"/applications/{app_id}")
                else:
                    self._send_html(400, _layout("Bad Request", "<p>Invalid status or unknown application.</p>"))
                return

            if path == "/run":
                from pipeline import run_pipeline

                form = self._read_form()
                dry_run = form.get("dry_run") == "1"
                limit_raw = form.get("limit", "").strip()
                limit = int(limit_raw) if limit_raw.isdigit() else None

                def _run():
                    stats = run_pipeline(dry_run=dry_run, limit=limit)
                    return (
                        f"Processed: {stats['processed']} | Skipped: {stats['skipped_duplicate']} duplicates, "
                        f"{stats['skipped_filter']} filtered | Errors: {len(stats['errors'])}"
                    )

                if not _start_job("run", _run):
                    self._send_html(409, _layout("Busy", "<p>A pipeline run is already in progress.</p>"))
                    return
                self._redirect("/")
                return

            if path == "/archive":
                from archive_processed import archive

                if not _start_job("archive", lambda: archive() or "Archived."):
                    self._send_html(409, _layout("Busy", "<p>Another job is already running.</p>"))
                    return
                self._redirect("/")
                return

            if path == "/manual":
                from manual_run import submit_manual_entry

                form = self._read_form()
                try:
                    company = form.get("company", "")
                    role = form.get("role", "")

                    def _submit():
                        out_dir = submit_manual_entry(
                            company, role,
                            form.get("location", ""), form.get("link", ""),
                            form.get("date_posted", ""), form.get("job_description", ""),
                            form.get("extra_context", ""),
                        )
                        return f"Saved to {out_dir}"

                    if not _start_job("manual", _submit):
                        self._send_html(409, _layout("Busy", "<p>Another job is already running.</p>"))
                        return
                except Exception as e:
                    self._send_html(400, _layout("Bad Request", f"<p>{html.escape(str(e))}</p>"))
                    return
                self._redirect("/")
                return

            if path == "/log":
                from accomplishments import log_entry

                form = self._read_form()
                try:
                    log_entry(form.get("text", ""), tags=form.get("tags") or None)
                except ValueError as e:
                    self._send_html(400, _layout("Bad Request", f"<p>{html.escape(str(e))}</p>"))
                    return
                self._redirect("/log")
                return

            if path == "/flush":
                from accomplishments import flush

                flush()
                self._redirect("/log")
                return

            if path == "/outreach/add":
                from outreach import add_contact

                form = self._read_form()
                try:
                    add_contact(
                        form.get("company", ""), form.get("contact_email", ""),
                        form.get("contact_name", ""), form.get("notes", ""),
                    )
                except ValueError as e:
                    self._send_html(400, _layout("Bad Request", f"<p>{html.escape(str(e))}</p>"))
                    return
                self._redirect("/outreach")
                return

            if path == "/outreach/confirm":
                from outreach import confirm_contact_manual

                form = self._read_form()
                confirm_contact_manual(form.get("contact_id", ""), form.get("email", ""))
                self._redirect("/outreach")
                return

            if path == "/outreach/discover":
                from outreach import discover_contacts

                def _discover():
                    stats = discover_contacts()
                    return f"Found: {stats['found']} | Added: {stats['added']} | Skipped duplicates: {stats['skipped_duplicate']}"

                if not _start_job("outreach-discover", _discover):
                    self._send_html(409, _layout("Busy", "<p>Another job is already running.</p>"))
                    return
                self._redirect("/outreach")
                return

            if path == "/outreach/run":
                from outreach import run_outreach

                def _run_outreach():
                    stats = run_outreach()
                    return (
                        f"Drafted: {stats['drafted']} | Skipped: {stats['skipped']} | "
                        f"Unconfirmed: {stats['unconfirmed_skipped']} | Errors: {len(stats['errors'])}"
                    )

                if not _start_job("outreach-run", _run_outreach):
                    self._send_html(409, _layout("Busy", "<p>Another job is already running.</p>"))
                    return
                self._redirect("/outreach")
                return

            if path.startswith("/prep/"):
                from interview_prep import generate_interview_prep

                app_id = path[len("/prep/"):]
                app = get_application(app_id)
                if app is None:
                    self._not_found("No such application.")
                    return
                company, role = app["company"], app["role"]

                def _prep():
                    result = generate_interview_prep(company, role_hint=role)
                    return f"Interview prep for {company}: {result['status']}"

                if not _start_job("prep", _prep):
                    self._send_html(409, _layout("Busy", "<p>Another job is already running.</p>"))
                    return
                self._redirect(f"/applications/{app_id}")
                return

            self._not_found()
        except Exception:
            self._send_html(500, _layout("Server Error", "<p>An unexpected error occurred.</p>"))

    def log_message(self, format, *args):
        pass


def build_server(host: str = "127.0.0.1", port: int = 8420) -> HTTPServer:
    server = HTTPServer((host, port), _Handler)
    # Configured host/port (not the possibly-0 requested port) so the
    # handler can validate the Host header against what we're actually
    # bound to — guards against DNS rebinding / cross-origin requests.
    server.gui_host = host
    server.gui_port = server.server_address[1]
    return server


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
