# Cold Email / Outreach — Sub-project B: Startup Discovery + Email Guessing — Design Spec

## Context

Sub-project A (`docs/superpowers/specs/2026-07-30-cold-email-outreach-a-design.md`)
built the outreach pipeline end-to-end against a manually-maintained contact
list: `context/outreach_contacts.yaml` → tailored, hallucination-checked
email generation → Gmail draft creation (never sends) → processed
tracking. Its "Future work" section explicitly deferred startup discovery
and email guessing to this sub-project.

This is the next item on the roadmap set in
`docs/superpowers/specs/2026-07-29-automator-cli-design.md`.

## Goal

`automator outreach discover` scrapes a startup directory (Y Combinator's
public company list to start, architected so a second source is a small
follow-up), guesses a plausible contact email per new company using
generic early-stage-startup address patterns, attempts free SMTP-based
verification, and appends new entries to the same
`context/outreach_contacts.yaml` Sub-project A's `run_outreach()` already
consumes — deduped against existing entries by company name. Unverified
guesses stay "unconfirmed" and are never drafted to automatically;
`automator outreach confirm <id> <email>` lets you manually override and
confirm one.

## Non-goals

- No individual founder-name scraping from each company's own YC profile
  page (personalized `first@domain.com`-style guessing). Raised during
  brainstorming as a near-term follow-up, explicitly deferred — this pass
  guesses generic addresses only (`founders@`, `hello@`, `hi@`, `team@`,
  `info@`).
- No second discovery source built in this pass. `discover_contacts()` is
  architected to loop over a list of source-scrapers so adding one later
  (e.g. a different accelerator's portfolio) is a small follow-up, mirroring
  how `vanshb03` was added as SimplifyJobs' second job source — but only YC
  is implemented here.
- No GUI. `automator outreach list` gains a plain-text confirmed/unconfirmed
  column; the eventual GUI sub-project reads the same data.
- Still never sends — `outreach run`'s draft-only, never-auto-send
  guarantee from Sub-project A is unchanged and untouched by this work.
- No paid email-verification API — SMTP-handshake verification only,
  accepted as free but imperfect (many providers, including
  Gmail/Workspace, accept all `RCPT TO` probes regardless of validity —
  "catch-all" domains will falsely verify).

## Architecture

Three new small units, each independently testable:

1. **`yc_scraper.py`** — scrapes YC's company directory. The directory is
   fully JS-rendered client-side (verified during brainstorming: a plain
   HTTP fetch returns no company data, only page chrome), so this reuses
   `job_fetcher.py`'s established playwright-fallback pattern rather than
   `scraper.py`'s httpx-based approach. Unlike the job scrapers, this
   sub-project could not verify the real page structure/selectors during
   design (no browser access in this session) — the implementing subagent
   will need playwright access and must inspect the live page to find the
   real batch-filter mechanism and company-card structure before writing
   the parser, rather than working from pre-specified selectors. This is
   a genuine, disclosed risk: the task may need more implementer judgment
   and iteration than this project's other scraper tasks have.

2. **`email_verify.py`** — email guessing and SMTP-based verification, with
   no dependency on `outreach.py` or the discovery scraper (usable
   standalone, testable in isolation).

3. **`outreach.py` extensions** — a `confirmed` field on the contact
   schema, a pluggable `discover_contacts()` orchestrator, and a manual
   confirm/override function — plus `run_outreach()` skipping unconfirmed
   contacts.

## Components

**`yc_scraper.py`:**
```python
def scrape_yc_directory(batches_back: int = 2, limit: int = 50) -> list[dict]:
    """Scrapes YC's company directory via playwright, filtered to the
    current batch plus `batches_back` prior batches, capped at `limit`
    companies. Returns [{"company": str, "website": str}]. Non-fatal:
    returns [] on any failure (matches scraper.py/researcher.py's
    established contract)."""
```

**`email_verify.py`:**
```python
_GENERIC_PREFIXES = ["founders", "hello", "hi", "team", "info"]

def _guess_email_candidates(domain: str) -> list[str]:
    """Returns [f"{prefix}@{domain}" for prefix in _GENERIC_PREFIXES]."""

def _resolve_mx_host(domain: str) -> str:
    """Shells out to `dig +short MX <domain>`, parses the lowest-priority
    hostname. Returns '' on any failure (dig not found, no MX records,
    timeout) — never raises."""

def _verify_email_smtp(email: str, timeout: float = 5.0) -> bool:
    """Resolves the domain's MX host, then an SMTP handshake (EHLO,
    MAIL FROM with a dummy sender, RCPT TO the candidate address) —
    never sends DATA, never completes an actual message. Returns True
    only on an explicit 2xx acceptance response. Fails closed: any
    error, timeout, non-2xx response, or missing MX record returns
    False — this function never raises and never assumes an address is
    valid without an explicit positive signal."""

def guess_and_verify_email(domain: str) -> tuple[str, bool]:
    """Tries each candidate from _guess_email_candidates via
    _verify_email_smtp, in order. Returns (email, True) on the first
    verified success. If none verify, returns (first_candidate, False)."""
```

**`outreach.py`** gains:
```python
_DISCOVERY_SOURCES = [("yc", scrape_yc_directory)]  # each entry: (source_name, scraper_fn)

def discover_contacts() -> dict:
    """Runs every scraper in _DISCOVERY_SOURCES, dedups results against
    contacts already in context/outreach_contacts.yaml (by normalized
    company name), guesses+verifies an email per new company via
    email_verify.guess_and_verify_email, and appends new entries
    (confirmed=True if SMTP-verified, confirmed=False otherwise).
    Returns {"found": int, "added": int, "skipped_duplicate": int}."""

def confirm_contact_manual(contact_id: str, email: str) -> bool:
    """Finds the contact by id, sets contact_email=email and
    confirmed=True, saves. Returns False if contact_id doesn't exist
    (caller prints an error), True on success."""
```

Contact schema gains `confirmed: bool` — absent key defaults to `True`
(backward-compatible with Sub-project A's manually-entered contacts,
which are inherently trustworthy since a human typed them).
`add_contact_interactive` explicitly sets `confirmed: True` on new
entries it creates.

`run_outreach()` gains one new skip condition, checked alongside the
existing already-processed check: a contact with `confirmed` explicitly
`False` is skipped (new `stats["unconfirmed_skipped"]` counter) — it is
never drafted to until confirmed, either by a future `discover_contacts()`
run's SMTP verification succeeding on a re-guess, or by
`confirm_contact_manual`.

`list_outreach_status()` gains a `confirmed: bool` field per entry
alongside the existing `status` (drafted/pending) field.

**`config.yaml`** gains:
```yaml
outreach:
  discover:
    batches_back: 2   # scrape current YC batch + this many prior batches
    limit: 50          # cap new companies added per discover run
```

**`automator/cli.py`** gains:
- `outreach discover` — calls `outreach.discover_contacts()`, prints
  found/added/skipped-duplicate.
- `outreach confirm <id> <email>` — calls
  `outreach.confirm_contact_manual(id, email)`, prints success or "contact
  id not found" on failure.
- `outreach list`'s existing print loop is extended to show the confirmed
  status alongside drafted/pending.

## Error handling

- `scrape_yc_directory` is non-fatal like every other scraper in this
  codebase: any failure (playwright error, page-structure change,
  timeout) is caught and logged, returning `[]` — `discover_contacts()`
  continues with zero new companies from that source rather than crashing.
- `_verify_email_smtp` fails closed on every error path — DNS failure,
  connection refused, timeout, non-2xx SMTP response — always returning
  `False`, never raising. An unverifiable address stays `confirmed: False`
  and simply sits pending review, which is the safe default given
  `run_outreach()` never drafts to unconfirmed contacts.
- `confirm_contact_manual` returns `False` (not an exception) for an
  unknown `contact_id`, letting the CLI print a clean error.

## Testing

`tests/test_email_verify.py`:
- `_guess_email_candidates` returns the 5 generic prefixes at the given
  domain.
- `_resolve_mx_host` parses a mocked `dig` subprocess output correctly,
  and returns `""` when the subprocess fails or returns no records
  (mocked, no real DNS lookup).
- `_verify_email_smtp` returns `True` on a mocked SMTP session that
  responds 250 to `RCPT TO`, and `False` on a mocked non-2xx response,
  a mocked connection exception, and when `_resolve_mx_host` returns `""`
  (no real network connection in any test).
- `guess_and_verify_email` returns the first candidate that verifies
  (mocked), or the first candidate with `False` when none verify.

`tests/test_yc_scraper.py`:
- `scrape_yc_directory` returns `[]` and doesn't raise when the
  underlying playwright call is mocked to fail — the specific
  page-interaction tests depend on what the implementer discovers about
  the real page structure, so this task's test coverage will be finalized
  during implementation rather than fully specified here (consistent with
  the Architecture section's disclosed research risk).

`tests/test_outreach_discover.py`:
- `discover_contacts` skips a scraped company whose normalized name
  already exists in `context/outreach_contacts.yaml` (mocked contacts +
  mocked scraper source).
- `discover_contacts` adds a new company with `confirmed=True` when the
  mocked `guess_and_verify_email` returns a verified result, and
  `confirmed=False` when it returns unverified.
- `run_outreach` skips a contact with `confirmed: False` and increments
  `stats["unconfirmed_skipped"]`, without calling `generate_cold_email`
  or `create_draft`.
- `confirm_contact_manual` updates an existing contact's email and sets
  `confirmed=True`; returns `False` for an unknown id without modifying
  the contacts file.
- A contact with no `confirmed` key (Sub-project A's existing schema)
  is treated as confirmed (backward compatibility).

## Future work (explicitly out of scope here)

Individual founder-name scraping from each YC company's own profile page,
for personalized (rather than generic) email guessing — raised during
brainstorming as the natural next enhancement once generic-address
guessing is proven working. A second discovery source beyond YC, added as
one more entry in `_DISCOVERY_SOURCES` plus its own scraper function.
