# Cold Email / Outreach — Sub-project A: Manual List to Drafts — Design Spec

## Context

This is the next item on the roadmap set in
`docs/superpowers/specs/2026-07-29-automator-cli-design.md`. No existing
code touches outbound cold-emailing or startup discovery —
`gmail_reader.py` is currently read-only (`search_emails`,
`get_recruiter_listings`), and there is no cold-email content path, no
send/draft capability, and no place to track outreach targets.

Given the full scope discussed during brainstorming (manual-list input, a
dedicated startup-discovery scraper, email guessing with SMTP
verification, content generation, and Gmail draft creation), this was
split into two sequential sub-projects. This spec covers **Sub-project A**
only: prove the whole pipeline end-to-end against a list you maintain
yourself, with a known-good contact email for every entry. Sub-project B
(startup discovery + email guessing/verification) builds on top of this
once A is working.

## Goal

`automator outreach add` lets you record a company/contact/email/notes
entry. `automator outreach run` generates a tailored, hallucination-checked
cold email for each un-processed entry and creates it as a Gmail draft
(never auto-sent), then marks the entry processed so reruns don't
re-draft it. `automator outreach list` shows plain-text status
(pending/drafted) for what's been reached out to.

## Non-goals

- No email guessing or SMTP verification — every contact email in this
  pass is one you provided directly. Deferred to Sub-project B.
- No startup-discovery scraper — deferred to Sub-project B.
- No auto-send — drafts only, created in Gmail, always reviewed and sent
  by hand. This was an explicit requirement, not a simplification.
- No GUI — `automator outreach list` is a plain-text CLI view. The GUI
  sub-project (roadmap item 9, not yet built) will later read the same
  underlying data (`context/outreach_contacts.yaml` +
  `outreach_processed.json`) and add visual presentation on top; nothing
  here needs to change when that happens.
- No attachments (resume/portfolio) on the draft.

## Architecture

A new `outreach.py` module owns the outreach-specific pipeline —
prompt-building, generation, validation, and orchestration — reusing
existing building blocks rather than duplicating them:

- **Generation** reuses `generator._call_ollama` and
  `generator._load_context_files()` (voice, resume_master, preferences,
  accomplishments, recent_updates) exactly as the resume/cover-letter path
  does, with a new, outreach-specific prompt (short, tailored ask about
  opportunities at the company — not a formal cover letter).
- **Validation** reuses `factual_validator.validate_outputs` as-is, by
  calling it with the generated email body passed as *both* the
  `resume_md` and `cover_md` arguments:
  `validate_outputs(email_body, email_body, contact_dict, model=..., base_url=...)`.
  Every existing check — contacts, GPA, degree, unsupported tech,
  metric claims, identity name, and the semantic verifier added in the
  hallucination-hardening sub-project — runs against the email body with
  zero new validator code. (The org-heading and project-heading checks
  look for markdown-heading patterns that plain prose emails won't
  contain, so they're harmless no-ops here, not a gap.)
- **Drafting** is a new `create_draft(to, subject, body, mcp_url,
  tool_name) -> bool` function in `gmail_reader.py`, using the exact same
  dynamic-tool-discovery pattern `_resolve_search_tool_name` already uses
  for search: a candidate-name list tried first, then a substring-match
  fallback (`"draft" in tool.lower()`) against the live `tools/list`
  response. This can't be verified against the real Gmail MCP server
  during design (no live OAuth session available) — it needs a real test
  once built, same as the rest of `gmail_reader.py`'s resolver pattern
  already does in production.

## Components

**`context/outreach_contacts.yaml`** (new, gitignored):
```yaml
- id: acme-corp-jane-doe
  company: "Acme Corp"
  contact_name: "Jane Doe"
  contact_email: "jane@acmecorp.com"
  notes: "Met at career fair, mentioned they're hiring backend interns"
```
Hand-editable or appended to via `automator outreach add`. Never
auto-deleted — this is your own persistent record, same spirit as
`context/recent_updates.md`.

**`outreach_processed.json`** (new, gitignored via the existing `*.json`
rule): a JSON list of contact IDs already drafted, mirroring
`processed.json`'s existing shape and purpose. Checked before generating,
so reruns skip already-drafted contacts.

**`outreach.py`** (new):
```python
def _build_cold_email_prompt(context: dict, contact: dict) -> str:
    """Short, tailored cold-outreach email prompt — company/contact-specific,
    not a job-posting-specific cover letter."""

def generate_cold_email(contact: dict, model: str, base_url: str, temperature: float, max_tokens: int) -> str:
    """Loads context, builds the prompt, calls _call_ollama, returns the email body."""

def run_outreach(config: dict) -> dict:
    """Reads context/outreach_contacts.yaml, skips IDs already in
    outreach_processed.json, generates + validates + drafts each pending
    contact, marks processed, returns run stats (drafted/skipped/errors)."""
```

**`gmail_reader.py`** gains:
```python
def _resolve_draft_tool_name(mcp_url: str = GMAIL_MCP_URL, configured_tool: str = "") -> str:
    """Mirrors _resolve_search_tool_name's candidate-list-then-substring-match pattern."""

def create_draft(to: str, subject: str, body: str, mcp_url: str = GMAIL_MCP_URL, tool_name: str = "") -> bool:
    """Creates a Gmail draft via MCP. Never sends. Returns True on success,
    False on any failure (caught and logged, never raises)."""
```

**`automator/cli.py`** gains three subcommands:
- `outreach add` — interactive prompts (mirrors `manual_run.py`'s
  `_prompt` style) for company/contact name/email/notes, appends to
  `context/outreach_contacts.yaml`.
- `outreach run` — calls `outreach.run_outreach()`, prints a summary
  (drafted/skipped/errors), mirroring `_print_run_summary`'s existing
  shape.
- `outreach list` — reads the contacts file + processed file, prints each
  entry's plain-text status (pending / drafted).

Each successfully drafted contact also gets a local copy saved to
`output/<date>/outreach/<company_slug>/email.md`, mirroring
`manual_run.py`'s existing per-entry save pattern — your own record even
though the authoritative copy lives in Gmail Drafts.

## Error handling

Matches the existing pipeline's non-fatal philosophy throughout:
- A single contact's generation or draft-creation failure (Ollama down,
  Gmail MCP error, no draft-capable tool found) is caught, logged to
  stderr, and added to the run's error list — it does not crash `outreach
  run`, and that contact is *not* marked processed, so it's retried on the
  next run.
- A contact that fails hallucination validation (mirrors the pipeline's
  balanced-mode retry: one corrective retry, then skip if still failing)
  is skipped with an error logged, not marked processed, and not drafted
  with unvalidated content.

## Testing

`tests/test_outreach.py`:
- `_build_cold_email_prompt` produces a prompt containing the contact's
  company name and notes.
- `generate_cold_email` returns `_call_ollama`'s output (mocked).
- `run_outreach` skips a contact whose ID is already in
  `outreach_processed.json` (mocked file).
- `run_outreach` drafts a pending contact (mocked `create_draft` returns
  `True`), marks it processed, and does not re-draft on a second call.
- `run_outreach` does not mark a contact processed when `create_draft`
  returns `False` (mocked failure) or when validation fails after the
  corrective retry.

`tests/test_gmail_draft.py`:
- `_resolve_draft_tool_name` picks a candidate name present in the mocked
  tool list; falls back to substring match when no candidate matches;
  falls back to a safe default when the tool list itself is unavailable
  — mirrors `_resolve_search_tool_name`'s existing three-tier test
  coverage pattern (no dedicated tests currently exist for
  `_resolve_search_tool_name` either, so this task establishes the first
  coverage for this dynamic-resolution pattern in the file).
- `create_draft` returns `True` on a mocked successful MCP call, `False`
  (never raises) on a mocked MCP failure.

`tests/test_cli_outreach.py`:
- `automator outreach add` (with mocked `input()`) appends a correctly
  shaped entry to a temp `context/outreach_contacts.yaml`.
- `automator outreach run` and `automator outreach list` dispatch to
  `outreach.run_outreach()` / the list-status function respectively
  (mocked), matching the existing CLI test style in
  `tests/test_cli_manual_archive.py`.

## Future work (explicitly out of scope here — Sub-project B)

A dedicated startup-discovery scraper (source TBD, likely a public
directory) feeding the same `context/outreach_contacts.yaml` shape, plus
email-guessing from name + company domain with SMTP-handshake-based
verification (accepted as free but imperfect — many mail providers,
including Gmail/Workspace, accept all `RCPT TO` probes regardless of
validity). Guessed-but-unconfirmed emails get a manual-override field so a
hand-entered email is always treated as confirmed. `automator outreach
list`'s plain-text output gets a confirmed/unconfirmed status column,
which the eventual GUI sub-project will present with the green-highlight
visual treatment discussed during brainstorming.
