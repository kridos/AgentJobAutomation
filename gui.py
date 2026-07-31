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
            f'<td>{html.escape(str(a["score"]))}</td><td>{html.escape(a["status"])}</td><td>{prep}</td></tr>'
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
        f'<p>Status: <strong>{html.escape(app["status"])}</strong> | Score: {html.escape(str(app["score"]))}</p>'
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
        f'<td>{html.escape(c["status"])}</td><td>{html.escape(str(c["confirmed"]))}</td></tr>'
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

    def _host_header_valid(self) -> bool:
        expected = f"{self.server.gui_host}:{self.server.gui_port}"
        # Loopback tools are commonly addressed as either 127.0.0.1 or
        # localhost regardless of the bind host, so accept both.
        allowed = {expected, f"localhost:{self.server.gui_port}"}
        return self.headers.get("Host", "") in allowed

    def do_GET(self) -> None:
        if not self._host_header_valid():
            self._send_html(403, _layout("Forbidden", "<p>Invalid Host header.</p>"))
            return
        try:
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
                app = get_application(app_id)
                if app is None:
                    self._not_found("No such application.")
                    return
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
