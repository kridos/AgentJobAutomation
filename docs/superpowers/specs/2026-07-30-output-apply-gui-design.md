# Output/Apply Streamlining + GUI — Design Spec

## Context

The last item on the roadmap set in
`docs/superpowers/specs/2026-07-29-automator-cli-design.md`. `automator run`
already generates a resume, cover letter, quality score, and (on demand,
per `automator prep`) interview prep material into
`output/<date>/<source>/<company-slug>/<role-slug>/`. `automator outreach`
already tracks cold-outreach contacts in `context/outreach_contacts.yaml`
with a `list_outreach_status()` reader. None of this has a review surface
beyond manually browsing folders — there's no way to see "what have I
already applied to" without opening every `listing.json`, and no place to
record that you applied. `automator/cli.py` already reserves a `gui`
subcommand (`_cmd_gui`, currently prints "GUI not built yet").

## Goal

`automator gui` starts a local, single-user web dashboard (binds to
`127.0.0.1` only) with three read-mostly views built entirely from
existing on-disk data:

- **Applications** — every generated application, with company/role/date/
  quality score/status, a detail page showing the generated resume, cover
  letter, and job description, and a button to mark it `applied` or
  `skipped`.
- **Outreach** — the existing cold-outreach contact list and draft status,
  read-only.
- **Interview Prep** — for applications that have prep material generated,
  a link to view it.

## Non-goals

- No auto-submitting applications on company sites — every job site is
  different and this project's stance throughout has been to keep humans
  in the loop for anything that leaves the local machine unreviewed.
  "Streamlining" here means killing the "which folders have I already
  handled" friction, not automating the click-apply step itself.
- No editing resume/cover letter/prep content from the GUI — those stay
  plain `.md` files, edited with any text editor if a tweak is needed.
  The GUI is a review/status surface, not an authoring tool.
- No triggering `automator run`, `automator outreach discover/run`, or
  `automator prep` from the GUI — those remain CLI actions. The GUI reads
  what those commands already produced.
- No auth/multi-user support — this is a local dashboard for one person on
  their own machine, consistent with the project's local-only tooling
  posture throughout (no cloud dependency, no new external service).
- No new runtime dependency — built on Python's stdlib `http.server`,
  matching the project's established preference for stdlib/free tooling
  (`dig` for MX lookups, raw SMTP handshake for email verification,
  `subprocess`+`gh` for GitHub reads) over adding a web framework for what
  is ultimately a handful of list/detail pages.

## Architecture

Two new modules:

**`applications.py`** — no GUI dependency, fully unit-testable on its own,
following the same shape as `outreach.py`'s status-listing functions and
`interview_prep.py`'s `_find_application`:

```python
def list_applications() -> list[dict]:
    """Globs output/*/*/*/*/listing.json, returns one dict per application:
    {id, company, role, source, date, output_dir, score (overall from
    quality_score.json), status ('applied'|'skipped'|'pending'),
    has_prep (bool, sibling interview_prep.md exists)}.
    id is the relative path string (date/source/company-slug/role-slug),
    stable and URL-safe enough to route on directly."""

def get_application(app_id: str) -> dict | None:
    """Loads one application's full detail: the list_applications() fields
    plus resume_md, cover_md, job_description (each "" if the file is
    missing — job_description.txt is already optional in the pipeline)."""

def set_application_status(app_id: str, status: str) -> bool:
    """status must be one of 'applied', 'skipped', 'pending'. Writes
    {"status": status} to status.json inside that application's output
    directory. Returns False (no write) for an unknown app_id or invalid
    status value; True on success."""
```

Status defaults to `"pending"` when `status.json` doesn't exist yet — no
migration needed for applications generated before this feature existed.

`app_id` is the four-segment relative path (`date/source/company-slug/
role-slug`) and contains literal `/` characters, so `output/` + `app_id`
reconstructs the directory directly. In routes, `app_id` is therefore
everything after the fixed prefix (e.g. everything after
`/applications/`), not a single path segment — the route handler splits
on the known prefix, not on `/`.

**`gui.py`** — the HTTP layer, kept separate from `applications.py` so the
data functions stay testable without spinning up a server:

```python
def build_server(host: str = "127.0.0.1", port: int = 8420) -> HTTPServer:
    """Constructs the stdlib HTTPServer with a request handler covering:
    GET  /                          -> applications list page
    GET  /applications/<id>         -> application detail page
    POST /applications/<id>/status  -> body 'status=applied'|'skipped'|'pending',
                                        redirects back to detail page
    GET  /outreach                  -> outreach list page (list_outreach_status())
    GET  /prep/<id>                 -> renders that application's interview_prep.md
                                        (404 page if has_prep is False)
    Unmatched paths -> 404.
    """

def run_gui(host: str = "127.0.0.1", port: int = 8420) -> None:
    """build_server(...).serve_forever(), with a startup print of the URL."""
```

HTML is generated with small `str.format`/f-string templates in `gui.py`
(no Jinja, no new dependency) with `html.escape()` applied to every piece
of user/LLM-generated text before interpolation (resume/cover letter
content, company/role names) — these values were never meant to be
trusted as markup, and skipping escaping would be a stored-XSS hole in a
tool that renders LLM output. A minimal shared CSS block (inline
`<style>` in a layout helper) keeps the three views visually consistent
without a static-asset pipeline.

**`automator/cli.py`** changes:

```python
def _cmd_gui(args: argparse.Namespace) -> None:
    from gui import run_gui
    run_gui(host=args.host, port=args.port)
```

`gui_p` gains `--host` (default `127.0.0.1`) and `--port` (default `8420`)
optional arguments. The existing `test_cli_gui.py` stub test (asserting
"not built yet") gets replaced — see Testing below.

## Data flow

- **Applications list/detail:** pure reads over `output/**/listing.json`,
  `quality_score.json`, `resume.md`, `cover_letter.md`,
  `job_description.txt`, plus the one small `status.json` this feature
  introduces.
- **Status mark:** the only write path in the whole feature — one POST
  writes one small JSON file inside the application's own directory. No
  shared state file, no locking concerns (single user, sequential
  requests via stdlib `http.server`'s default single-threaded handling).
- **Outreach view:** delegates entirely to `outreach.list_outreach_status()`
  — no new outreach code, no new file format.
- **Interview prep view:** reads the `interview_prep.md` file already
  written by `automator prep` into the same application directory
  `interview_prep.py` already resolves via its `_find_application` glob
  pattern; `applications.py` reuses that same glob pattern to detect
  `has_prep` rather than introducing a second way to name application
  directories.

## Error handling

- Missing `output/` directory entirely: `list_applications()` returns `[]`
  (mirrors every other empty-input case in this codebase); the GUI shows
  "No applications yet — run `automator run` first."
- Malformed `listing.json`/`quality_score.json`/`status.json` for one
  application: that single entry is skipped with a `[gui] skipping
  <path>: malformed JSON` stderr print, not a crash — one bad file must
  not take down the whole dashboard, consistent with `pipeline.py`'s
  existing `_load_processed` malformed-file handling.
- `set_application_status` with an id that doesn't resolve to a real
  directory, or a status value outside the three allowed: returns `False`,
  no file written; the HTTP handler responds 400.
- Requesting `/prep/<id>` for an application with no `interview_prep.md`:
  404 page with a message pointing at `automator prep <company>`.
- Port already in use: `run_gui` lets the `OSError` propagate with
  Python's normal traceback — this is a local dev tool, not a service
  that needs a custom retry/port-scan story.

## Testing

`tests/test_applications.py`:
- `list_applications` returns one entry per `listing.json` found under a
  temp `output/` tree (`tmp_path`/`monkeypatch.chdir`, matching
  `interview_prep.py`'s existing test pattern), with `status` defaulting
  to `"pending"` when no `status.json` exists.
- `list_applications` skips an entry with malformed JSON rather than
  raising, and still returns the other valid entries.
- `get_application` returns `None` for an unknown id.
- `get_application` returns `""` for `job_description` when
  `job_description.txt` is absent.
- `set_application_status` writes `status.json` with the given status and
  is reflected in a subsequent `list_applications()` call.
- `set_application_status` returns `False` and writes nothing for an
  invalid status value or unknown id.

`tests/test_gui.py`:
- `build_server` on an ephemeral port (`port=0`, then read
  `server.server_address[1]`), exercised via `http.client.HTTPConnection`
  in-process:
  - `GET /` returns 200 and includes a known seeded application's company
    name.
  - `GET /applications/<id>` returns 200 with resume content, 404 for an
    unknown id.
  - `POST /applications/<id>/status` with `status=applied` returns a
    redirect and a following `GET` shows the updated status; invalid
    status value returns 400.
  - `GET /outreach` returns 200 (mock `outreach.list_outreach_status` to
    avoid a real `context/outreach_contacts.yaml` dependency).
  - `GET /prep/<id>` returns 200 when `interview_prep.md` exists, 404 when
    it doesn't.
  - A resume/cover-letter string containing `<script>` is rendered escaped
    (`&lt;script&gt;`), not literally — the XSS-safety check for the one
    place this project renders LLM output as HTML.

`tests/test_cli_gui.py` (replaces the existing stub-only test):
- `automator gui` parses `--host`/`--port` and dispatches to
  `gui.run_gui` with them (mocked, asserting call args — no real server
  started in this test).
