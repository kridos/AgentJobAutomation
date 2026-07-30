# Cold Email / Outreach — Sub-project B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `automator outreach discover` scrapes YC's directory, guesses + SMTP-verifies a generic contact email per new company, and appends unconfirmed-by-default entries to `context/outreach_contacts.yaml`; `automator outreach confirm <id> <email>` lets you manually override/confirm one. `outreach run` never drafts to an unconfirmed contact.

**Architecture:** Two new standalone modules — `email_verify.py` (guessing + free SMTP verification, no dependency on anything else) and `yc_scraper.py` (playwright-based directory scrape, behind a fully-specified sync wrapper whose internal async fetch the implementer must write after inspecting the live page — its real structure could not be verified during design). `outreach.py` gains a `confirmed` field on the contact schema and a pluggable `discover_contacts()` orchestrator that loops over a list of source-scrapers (`_DISCOVERY_SOURCES`) so a second source later is a small addition. `automator/cli.py` gains `outreach discover`/`outreach confirm`.

**Tech Stack:** Python 3.10+, stdlib `subprocess` (`dig` shell-out for MX lookup) and `smtplib` (SMTP handshake), `playwright` (already an optional dependency via the `research` extra, reused here) — no new dependencies.

## Global Constraints

- `outreach run`'s existing never-auto-send guarantee is untouched by this work — this plan only adds discovery/guessing/confirmation, nothing that could send.
- Email verification fails closed: `_verify_email_smtp` returns `False` on any error, timeout, missing MX record, or non-2xx SMTP response — it never assumes an address is valid without an explicit positive signal, and it never raises.
- A contact's `confirmed` field defaults to `True` when absent (backward compatible with Sub-project A's manually-entered contacts). `run_outreach()` skips any contact with `confirmed` explicitly `False`.
- Every scraper (`scrape_yc_directory`, and by extension anything added later to `_DISCOVERY_SOURCES`) is non-fatal: any failure is caught and logged, returning `[]` — `discover_contacts()` continues with the next source rather than crashing.
- No new runtime dependencies.
- `yc_scraper.py`'s internal page-scraping logic cannot be fully pre-specified in this plan (the live page is JS-rendered and its real structure wasn't inspectable during design) — Task 2 includes an explicit live-exploration step before implementation, which is a deliberate, disclosed exception to this project's usual fully-specified-code task style.

---

### Task 1: email_verify.py — guessing + SMTP verification

**Files:**
- Create: `email_verify.py`
- Test: `tests/test_email_verify.py`

**Interfaces:**
- Consumes: nothing from this project (standalone module; uses stdlib `subprocess`, `smtplib` only).
- Produces: `email_verify.guess_and_verify_email(domain: str) -> tuple[str, bool]` — consumed by Task 3's `outreach.py`. Also produces `email_verify._guess_email_candidates(domain: str) -> list[str]`, `email_verify._resolve_mx_host(domain: str) -> str`, and `email_verify._verify_email_smtp(email: str, timeout: float = 5.0) -> bool`, used only internally by this task's own tests and by `guess_and_verify_email`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_email_verify.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_email_verify.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'email_verify'`

- [ ] **Step 3: Create email_verify.py**

Create `email_verify.py`:

```python
"""
Generic-address email guessing + free SMTP-handshake verification for
cold-outreach contact discovery. Standalone — no dependency on
outreach.py or any scraper.
"""

import smtplib
import subprocess
import sys

_GENERIC_PREFIXES = ["founders", "hello", "hi", "team", "info"]


def _guess_email_candidates(domain: str) -> list[str]:
    return [f"{prefix}@{domain}" for prefix in _GENERIC_PREFIXES]


def _resolve_mx_host(domain: str) -> str:
    """Shells out to `dig +short MX <domain>`, returns the lowest-priority
    (i.e. most-preferred) hostname. Returns '' on any failure — never raises."""
    try:
        result = subprocess.run(
            ["dig", "+short", "MX", domain],
            capture_output=True, text=True, timeout=5.0,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return ""
        records = []
        for line in result.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) == 2:
                priority, host = parts
                records.append((int(priority), host.rstrip(".")))
        if not records:
            return ""
        records.sort(key=lambda r: r[0])
        return records[0][1]
    except Exception as e:
        print(f"[email_verify] MX lookup failed for {domain}: {e}", file=sys.stderr)
        return ""


def _verify_email_smtp(email: str, timeout: float = 5.0) -> bool:
    """SMTP handshake verification: EHLO, MAIL FROM, RCPT TO — never sends
    DATA, never completes a message. Fails closed: any error, timeout, or
    non-2xx response returns False."""
    domain = email.split("@", 1)[-1]
    mx_host = _resolve_mx_host(domain)
    if not mx_host:
        return False

    try:
        with smtplib.SMTP(mx_host, 25, timeout=timeout) as smtp:
            smtp.ehlo_or_helo_if_needed()
            smtp.mail("verify@example.com")
            code, _ = smtp.rcpt(email)
            return 200 <= code < 300
    except Exception as e:
        print(f"[email_verify] SMTP verification failed for {email}: {e}", file=sys.stderr)
        return False


def guess_and_verify_email(domain: str) -> tuple[str, bool]:
    """Tries each generic candidate until one verifies via SMTP.
    Returns (email, True) on first success, or (first_candidate, False)
    if none verify."""
    candidates = _guess_email_candidates(domain)
    for candidate in candidates:
        if _verify_email_smtp(candidate):
            return candidate, True
    return candidates[0], False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_email_verify.py -v`
Expected: 9 tests PASS

- [ ] **Step 5: Run the full test suite as a regression check**

Run: `pytest tests/ -v`
Expected: All tests PASS — `email_verify.py` is a new standalone module, no existing file modified.

- [ ] **Step 6: Commit**

```bash
git add email_verify.py tests/test_email_verify.py
git commit -m "feat: add generic email guessing + free SMTP verification"
```

---

### Task 2: yc_scraper.py — YC directory scraper (live-exploration task)

**Files:**
- Create: `yc_scraper.py`
- Test: `tests/test_yc_scraper.py`

**Interfaces:**
- Consumes: `playwright` (already an optional dependency via `pyproject.toml`'s `research` extra — reuse it, do not add a new dependency).
- Produces: `yc_scraper.scrape_yc_directory(batches_back: int = 2, limit: int = 50) -> list[dict]` (returns `[{"company": str, "website": str}]`) — consumed by Task 3's `outreach.py` via `_DISCOVERY_SOURCES`.

**This task is different from the others in this codebase's plans.** The internal scraping logic for YC's directory could not be verified during design — the page is fully JS-rendered, and a plain HTTP fetch of `https://www.ycombinator.com/companies` returns only page chrome, no company data. You have playwright access in this task; other tasks in this project don't need it because their target pages were already verified. Follow the steps below in order — Step 1 is a genuine research step, not a formality.

- [ ] **Step 1: Explore the live page structure**

Using playwright (a quick throwaway script is fine, e.g. `python -c "..."` or a scratch file you delete before committing — do not commit exploration scratch code), navigate to `https://www.ycombinator.com/companies` with a headless Chromium browser, wait for the page to render (`wait_until="domcontentloaded"` plus a short additional wait for JS, mirroring `job_fetcher.py:73-81`'s existing `fetch_via_playwright` pattern — read that function first, it's the established pattern in this codebase for playwright usage), and inspect the rendered DOM (`page.content()` or `page.evaluate("() => document.body.innerHTML")`).

Specifically determine:
1. **Batch filtering**: is there a URL query parameter (e.g. `?batch=W25`) that filters the directory to a specific batch, or does filtering require interacting with an on-page control (search box, dropdown, checkbox list)? If you find a URL-parameter approach, prefer it — it's far more robust than simulating UI interaction.
2. **Company card structure**: what CSS selector(s) identify each company's "card" or list-item in the rendered DOM? Within each card, what selector gives the company name, and what selector (or attribute, e.g. an `href` or a data attribute) gives the company's website domain?

If you cannot find a reliable batch-filter mechanism after reasonable investigation, that's an acceptable outcome — document it in your report and implement `scrape_yc_directory` to scrape the default (most-recent-first) directory view and rely on `limit` alone to bound the result size, rather than blocking on batch filtering. A working scraper without perfect batch filtering is more valuable than no scraper.

- [ ] **Step 2: Write the failing tests**

These tests exercise `scrape_yc_directory`'s outer contract (non-fatal on failure, respects `limit`) without depending on the real page structure — they mock at the async-fetch boundary, which Step 4 will implement based on your Step 1 findings.

Create `tests/test_yc_scraper.py`:

```python
import yc_scraper


def test_scrape_yc_directory_returns_empty_list_on_failure(monkeypatch):
    async def _raise(batches_back):
        raise RuntimeError("page failed to load")

    monkeypatch.setattr(yc_scraper, "_fetch_yc_companies_async", _raise)

    result = yc_scraper.scrape_yc_directory()

    assert result == []


def test_scrape_yc_directory_respects_limit(monkeypatch):
    fake_companies = [{"company": f"Company{i}", "website": f"company{i}.com"} for i in range(100)]

    async def _fake_fetch(batches_back):
        return fake_companies

    monkeypatch.setattr(yc_scraper, "_fetch_yc_companies_async", _fake_fetch)

    result = yc_scraper.scrape_yc_directory(limit=10)

    assert len(result) == 10


def test_scrape_yc_directory_returns_full_list_under_limit(monkeypatch):
    fake_companies = [{"company": "Acme Corp", "website": "acme.com"}]

    async def _fake_fetch(batches_back):
        return fake_companies

    monkeypatch.setattr(yc_scraper, "_fetch_yc_companies_async", _fake_fetch)

    result = yc_scraper.scrape_yc_directory(limit=50)

    assert result == fake_companies
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_yc_scraper.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'yc_scraper'`

- [ ] **Step 4: Create yc_scraper.py**

The public sync wrapper is fully specified below — use it exactly as shown. `_fetch_yc_companies_async` is the part you implement based on your Step 1 findings; its docstring states the required contract.

Create `yc_scraper.py`:

```python
"""
Scrapes Y Combinator's public company directory for startup-discovery
cold-outreach targets. The directory is JS-rendered, so this uses
playwright (mirrors job_fetcher.py's fetch_via_playwright pattern).
Run standalone: python yc_scraper.py
"""

import asyncio
import sys


async def _fetch_yc_companies_async(batches_back: int) -> list[dict]:
    """Navigates YC's company directory with playwright and extracts
    company name + website per listing, filtered to the current batch
    plus `batches_back` prior batches where the page structure allows
    reliable batch filtering (falls back to the default directory view,
    most-recent-first, if it does not — see this task's Step 1 findings).
    Returns [{"company": str, "website": str}, ...]. Raises on failure —
    the caller (scrape_yc_directory) is responsible for catching."""
    # Implementation based on Step 1's live-page findings.
    raise NotImplementedError


def scrape_yc_directory(batches_back: int = 2, limit: int = 50) -> list[dict]:
    """Scrapes YC's company directory via playwright, capped at `limit`
    companies. Returns [{"company": str, "website": str}]. Non-fatal:
    returns [] on any failure — network error, timeout, or unexpected
    page structure."""
    try:
        companies = asyncio.run(_fetch_yc_companies_async(batches_back))
        return companies[:limit]
    except Exception as e:
        print(f"[yc_scraper] YC directory scrape failed: {e}", file=sys.stderr)
        return []


if __name__ == "__main__":
    result = scrape_yc_directory()
    print(f"Found {len(result)} companies")
    for c in result[:10]:
        print(f"  {c['company']} — {c['website']}")
```

Replace `_fetch_yc_companies_async`'s `raise NotImplementedError` body with your real implementation, using playwright to navigate, render, and extract company name + website pairs per your Step 1 findings. Keep the function signature (`async def _fetch_yc_companies_async(batches_back: int) -> list[dict]`) and its "raises on failure, caller catches" contract exactly as documented — `scrape_yc_directory`'s try/except already handles all error cases and must not be modified.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_yc_scraper.py -v`
Expected: 3 tests PASS (these test the wrapper's contract via mocking, not the real scrape — they should pass regardless of your Step 4 implementation details, since they mock `_fetch_yc_companies_async` entirely)

- [ ] **Step 6: Sanity-check against the real live page**

Run `python yc_scraper.py` once manually (not as an automated test) and confirm it prints a plausible list of real company names and websites. Include a short sample of the actual output (5-10 companies) in your task report — this is the evidence that Step 4's implementation actually works against the live site, not just against the Step 2 mocks.

- [ ] **Step 7: Run the full test suite as a regression check**

Run: `pytest tests/ -v`
Expected: All tests PASS — `yc_scraper.py` is a new standalone module, no existing file modified.

- [ ] **Step 8: Commit**

```bash
git add yc_scraper.py tests/test_yc_scraper.py
git commit -m "feat: add YC directory scraper for startup discovery"
```

---

### Task 3: outreach.py extensions — confirmed field, discover_contacts, confirm_contact_manual

**Files:**
- Modify: `outreach.py` (add `confirmed` field handling, `_DISCOVERY_SOURCES`, `discover_contacts`, `confirm_contact_manual`; modify `add_contact_interactive`, `run_outreach`, `list_outreach_status`)
- Modify: `config.yaml` (add `outreach.discover` section)
- Test: `tests/test_outreach_discover.py`

**Interfaces:**
- Consumes: `email_verify.guess_and_verify_email(domain: str) -> tuple[str, bool]` (Task 1), `yc_scraper.scrape_yc_directory(batches_back: int = 2, limit: int = 50) -> list[dict]` (Task 2).
- Produces: `outreach.discover_contacts() -> dict` (returns `{"found": int, "added": int, "skipped_duplicate": int}`) and `outreach.confirm_contact_manual(contact_id: str, email: str) -> bool` — both consumed by Task 4's CLI wiring. Also modifies the existing `outreach.run_outreach() -> dict`'s return shape (adds an `"unconfirmed_skipped"` key) and `outreach.list_outreach_status() -> list[dict]`'s per-entry shape (adds a `"confirmed"` key) — Task 4's CLI code must account for both additions.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_outreach_discover.py`:

```python
import outreach


def _fake_contact(company="Acme Corp", email="jane@acme.com", confirmed=True, contact_id=None):
    return {
        "id": contact_id or company.lower().replace(" ", "-"),
        "company": company,
        "contact_name": "",
        "contact_email": email,
        "notes": "",
        "confirmed": confirmed,
    }


def test_discover_contacts_skips_existing_company(monkeypatch):
    monkeypatch.setattr(outreach, "_load_config", lambda: {})
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [_fake_contact(company="Acme Corp")])
    monkeypatch.setattr(
        outreach, "_DISCOVERY_SOURCES",
        [("yc", lambda batches_back, limit: [{"company": "acme corp ", "website": "acme.com"}])],
    )

    saved = []
    monkeypatch.setattr(outreach, "_save_contacts", lambda contacts: saved.append(contacts))

    stats = outreach.discover_contacts()

    assert stats["skipped_duplicate"] == 1
    assert stats["added"] == 0


def test_discover_contacts_adds_new_company_with_verified_email(monkeypatch):
    monkeypatch.setattr(outreach, "_load_config", lambda: {})
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [])
    monkeypatch.setattr(
        outreach, "_DISCOVERY_SOURCES",
        [("yc", lambda batches_back, limit: [{"company": "Beta Inc", "website": "beta.com"}])],
    )
    monkeypatch.setattr(outreach, "guess_and_verify_email", lambda domain: ("hello@beta.com", True))

    saved = []
    monkeypatch.setattr(outreach, "_save_contacts", lambda contacts: saved.append(contacts))

    stats = outreach.discover_contacts()

    assert stats["added"] == 1
    assert saved[-1][0]["contact_email"] == "hello@beta.com"
    assert saved[-1][0]["confirmed"] is True


def test_discover_contacts_adds_new_company_with_unverified_email(monkeypatch):
    monkeypatch.setattr(outreach, "_load_config", lambda: {})
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [])
    monkeypatch.setattr(
        outreach, "_DISCOVERY_SOURCES",
        [("yc", lambda batches_back, limit: [{"company": "Gamma LLC", "website": "gamma.com"}])],
    )
    monkeypatch.setattr(outreach, "guess_and_verify_email", lambda domain: ("founders@gamma.com", False))

    saved = []
    monkeypatch.setattr(outreach, "_save_contacts", lambda contacts: saved.append(contacts))

    stats = outreach.discover_contacts()

    assert stats["added"] == 1
    assert saved[-1][0]["confirmed"] is False


def test_run_outreach_skips_unconfirmed_contact(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    contact = _fake_contact(confirmed=False)
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [contact])
    monkeypatch.setattr(outreach, "_load_outreach_processed", lambda: set())

    gen_calls = []
    monkeypatch.setattr(outreach, "generate_cold_email", lambda c, **kwargs: gen_calls.append(1) or "body")
    draft_calls = []
    monkeypatch.setattr(outreach, "create_draft", lambda *a, **k: draft_calls.append(1) or True)

    stats = outreach.run_outreach()

    assert gen_calls == []
    assert draft_calls == []
    assert stats["unconfirmed_skipped"] == 1
    assert stats["drafted"] == 0


def test_confirm_contact_manual_updates_existing_contact(monkeypatch):
    contact = _fake_contact(email="", confirmed=False, contact_id="acme-corp")
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [contact])

    saved = []
    monkeypatch.setattr(outreach, "_save_contacts", lambda contacts: saved.append(contacts))

    result = outreach.confirm_contact_manual("acme-corp", "real@acme.com")

    assert result is True
    assert saved[-1][0]["contact_email"] == "real@acme.com"
    assert saved[-1][0]["confirmed"] is True


def test_confirm_contact_manual_returns_false_for_unknown_id(monkeypatch):
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [])

    saved = []
    monkeypatch.setattr(outreach, "_save_contacts", lambda contacts: saved.append(contacts))

    result = outreach.confirm_contact_manual("nonexistent", "x@x.com")

    assert result is False
    assert saved == []


def test_list_outreach_status_treats_missing_confirmed_key_as_true(monkeypatch):
    contact = {"id": "old-contact", "company": "Old Co", "contact_email": "old@old.com"}
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [contact])
    monkeypatch.setattr(outreach, "_load_outreach_processed", lambda: set())

    result = outreach.list_outreach_status()

    assert result[0]["confirmed"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_outreach_discover.py -v`
Expected: FAIL — `AttributeError: module 'outreach' has no attribute 'discover_contacts'` (and similar for `confirm_contact_manual`, `_DISCOVERY_SOURCES`; the `unconfirmed_skipped` test fails with a `KeyError`)

- [ ] **Step 3: Add imports and _DISCOVERY_SOURCES**

In `outreach.py`, change the existing import block:

```python
from generator import _call_ollama, _load_context_files, DEFAULT_MODEL, OLLAMA_BASE_URL
from factual_validator import (
    validate_outputs,
    format_validation_feedback,
    _check_metric_claims,
    _extract_allowed_metrics,
    _load_resume_master,
)
from gmail_reader import create_draft, GMAIL_MCP_URL
```

to:

```python
from generator import _call_ollama, _load_context_files, DEFAULT_MODEL, OLLAMA_BASE_URL
from factual_validator import (
    validate_outputs,
    format_validation_feedback,
    _check_metric_claims,
    _extract_allowed_metrics,
    _load_resume_master,
)
from gmail_reader import create_draft, GMAIL_MCP_URL
from email_verify import guess_and_verify_email
from yc_scraper import scrape_yc_directory
```

Immediately after the `PROCESSED_PATH = ...` line (currently line 30), add:

```python
_DISCOVERY_SOURCES = [("yc", scrape_yc_directory)]  # each entry: (source_name, scraper_fn(batches_back, limit) -> list[dict])
```

- [ ] **Step 4: Add _normalize_company**

Immediately after `_slugify` (currently ending at line 41, right before `_load_contacts`), add:

```python
def _normalize_company(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())
```

- [ ] **Step 5: Set confirmed=True in add_contact_interactive**

In `outreach.py`'s `add_contact_interactive`, change:

```python
    contacts = _load_contacts()
    contacts.append({
        "id": contact_id,
        "company": company,
        "contact_name": contact_name,
        "contact_email": contact_email,
        "notes": notes,
    })
    _save_contacts(contacts)
```

to:

```python
    contacts = _load_contacts()
    contacts.append({
        "id": contact_id,
        "company": company,
        "contact_name": contact_name,
        "contact_email": contact_email,
        "notes": notes,
        "confirmed": True,
    })
    _save_contacts(contacts)
```

- [ ] **Step 6: Add discover_contacts and confirm_contact_manual**

Immediately after `_build_subject` (currently ending at line 176, right before `_validate_email`), add:

```python
def discover_contacts() -> dict:
    """Runs every scraper in _DISCOVERY_SOURCES, dedups against existing
    contacts by normalized company name, guesses+verifies an email per
    new company, and appends new entries to context/outreach_contacts.yaml.
    Returns {"found": int, "added": int, "skipped_duplicate": int}."""
    config = _load_config()
    discover_cfg = config.get("outreach", {}).get("discover", {})
    batches_back = discover_cfg.get("batches_back", 2)
    limit = discover_cfg.get("limit", 50)

    contacts = _load_contacts()
    existing_companies = {_normalize_company(c.get("company", "")) for c in contacts}

    stats = {"found": 0, "added": 0, "skipped_duplicate": 0}

    for source_name, scraper_fn in _DISCOVERY_SOURCES:
        try:
            found = scraper_fn(batches_back=batches_back, limit=limit)
        except Exception as e:
            print(f"[outreach] Discovery source '{source_name}' failed: {e}", file=sys.stderr)
            continue

        stats["found"] += len(found)

        for entry in found:
            company = entry.get("company", "")
            website = entry.get("website", "")
            if not company or not website:
                continue

            if _normalize_company(company) in existing_companies:
                stats["skipped_duplicate"] += 1
                continue

            domain = re.sub(r"^https?://(www\.)?", "", website).rstrip("/").split("/")[0]
            email, confirmed = guess_and_verify_email(domain)

            contact_id = f"{_slugify(company)}-{source_name}"
            contacts.append({
                "id": contact_id,
                "company": company,
                "contact_name": "",
                "contact_email": email,
                "notes": f"Discovered via {source_name}",
                "confirmed": confirmed,
            })
            existing_companies.add(_normalize_company(company))
            stats["added"] += 1

    _save_contacts(contacts)
    return stats


def confirm_contact_manual(contact_id: str, email: str) -> bool:
    """Finds the contact by id, sets contact_email=email and confirmed=True,
    saves. Returns False if contact_id doesn't exist."""
    contacts = _load_contacts()
    for contact in contacts:
        if contact.get("id", "") == contact_id:
            contact["contact_email"] = email
            contact["confirmed"] = True
            _save_contacts(contacts)
            return True
    return False
```

- [ ] **Step 7: Skip unconfirmed contacts in run_outreach**

In `outreach.py`'s `run_outreach`, change:

```python
    stats = {"drafted": 0, "skipped": 0, "errors": []}

    for contact in contacts:
        contact_id = contact.get("id", "")
        company = contact.get("company", "")

        if not contact_id or contact_id in processed:
            stats["skipped"] += 1
            continue

        email_addr = contact.get("contact_email", "")
```

to:

```python
    stats = {"drafted": 0, "skipped": 0, "unconfirmed_skipped": 0, "errors": []}

    for contact in contacts:
        contact_id = contact.get("id", "")
        company = contact.get("company", "")

        if not contact_id or contact_id in processed:
            stats["skipped"] += 1
            continue

        if not contact.get("confirmed", True):
            stats["unconfirmed_skipped"] += 1
            continue

        email_addr = contact.get("contact_email", "")
```

- [ ] **Step 8: Add confirmed field to list_outreach_status**

In `outreach.py`, change:

```python
def list_outreach_status() -> list[dict]:
    """Returns [{"company", "contact_email", "status"}] for every contact.
    status is 'drafted' or 'pending'."""
    contacts = _load_contacts()
    processed = _load_outreach_processed()
    return [
        {
            "company": c.get("company", ""),
            "contact_email": c.get("contact_email", ""),
            "status": "drafted" if c.get("id", "") in processed else "pending",
        }
        for c in contacts
    ]
```

to:

```python
def list_outreach_status() -> list[dict]:
    """Returns [{"company", "contact_email", "status", "confirmed"}] for
    every contact. status is 'drafted' or 'pending'."""
    contacts = _load_contacts()
    processed = _load_outreach_processed()
    return [
        {
            "company": c.get("company", ""),
            "contact_email": c.get("contact_email", ""),
            "status": "drafted" if c.get("id", "") in processed else "pending",
            "confirmed": c.get("confirmed", True),
        }
        for c in contacts
    ]
```

- [ ] **Step 9: Add the config section**

In `config.yaml`, add this new top-level section after the `accomplishments:` block and before `output:`:

```yaml
outreach:
  discover:
    batches_back: 2   # scrape current YC batch + this many prior batches
    limit: 50          # cap new companies added per discover run
```

- [ ] **Step 10: Run tests to verify they pass**

Run: `pytest tests/test_outreach_discover.py -v`
Expected: 7 tests PASS

- [ ] **Step 11: Run the full test suite as a regression check**

Run: `pytest tests/ -v`
Expected: All tests PASS. `run_outreach`'s new `unconfirmed_skipped` stats key and the unconfirmed-skip check are additive — Sub-project A's existing `test_outreach.py` tests all use `confirmed: True` implicitly (via the default `contact.get("confirmed", True)`), since none of those fixtures include a `confirmed` key, so none of them are newly skipped.

- [ ] **Step 12: Commit**

```bash
git add outreach.py config.yaml tests/test_outreach_discover.py
git commit -m "feat: add discover_contacts/confirm_contact_manual, skip unconfirmed contacts in run_outreach"
```

---

### Task 4: CLI wiring — outreach discover/confirm + packaging

**Files:**
- Modify: `automator/cli.py` (add `outreach discover`/`outreach confirm` subcommands, update `outreach list`/`outreach run` output)
- Modify: `pyproject.toml:14-18` (add `"yc_scraper"`, `"email_verify"` to `py-modules`)
- Modify: `README.md` (add discover/confirm usage examples)
- Test: `tests/test_cli_outreach_discover.py`

**Interfaces:**
- Consumes: `outreach.discover_contacts() -> dict`, `outreach.confirm_contact_manual(contact_id: str, email: str) -> bool` (Task 3), `outreach.run_outreach() -> dict` (now includes `"unconfirmed_skipped"`, Task 3), `outreach.list_outreach_status() -> list[dict]` (now includes `"confirmed"`, Task 3).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_outreach_discover.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli_outreach_discover.py -v`
Expected: FAIL — `argparse` errors for `discover`/`confirm` (not recognized subcommands), and `test_outreach_run_shows_unconfirmed_skipped_count`/`test_outreach_list_shows_confirmed_status` fail on missing text in output

- [ ] **Step 3: Add the CLI handlers**

In `automator/cli.py`, immediately after `_cmd_outreach_add` (currently ending at line 90, right before `_cmd_outreach_run`), add:

```python
def _cmd_outreach_discover(args: argparse.Namespace) -> None:
    from outreach import discover_contacts

    stats = discover_contacts()
    print(f"\nDone. Found: {stats['found']} | Added: {stats['added']} | Skipped duplicates: {stats['skipped_duplicate']}")


def _cmd_outreach_confirm(args: argparse.Namespace) -> None:
    from outreach import confirm_contact_manual

    if confirm_contact_manual(args.contact_id, args.email):
        print(f"Confirmed {args.contact_id} — {args.email}")
    else:
        print(f"No contact found with id '{args.contact_id}'", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 4: Update _cmd_outreach_run's summary line**

In `automator/cli.py`, change `_cmd_outreach_run`:

```python
def _cmd_outreach_run(args: argparse.Namespace) -> None:
    from outreach import run_outreach

    stats = run_outreach()
    print(f"\nDone. Drafted: {stats['drafted']} | Skipped: {stats['skipped']} | Errors: {len(stats['errors'])}")
    if stats["errors"]:
        for e in stats["errors"]:
            print(f"  ERROR: {e}", file=sys.stderr)
```

to:

```python
def _cmd_outreach_run(args: argparse.Namespace) -> None:
    from outreach import run_outreach

    stats = run_outreach()
    print(
        f"\nDone. Drafted: {stats['drafted']} | Skipped: {stats['skipped']} | "
        f"Unconfirmed (held back): {stats['unconfirmed_skipped']} | Errors: {len(stats['errors'])}"
    )
    if stats["errors"]:
        for e in stats["errors"]:
            print(f"  ERROR: {e}", file=sys.stderr)
```

- [ ] **Step 5: Update _cmd_outreach_list to show confirmed status**

In `automator/cli.py`, change `_cmd_outreach_list`:

```python
def _cmd_outreach_list(args: argparse.Namespace) -> None:
    from outreach import list_outreach_status

    statuses = list_outreach_status()
    if not statuses:
        print("No outreach contacts yet. Add one with: automator outreach add")
        return
    for s in statuses:
        print(f"[{s['status']:8}] {s['company']} — {s['contact_email']}")
```

to:

```python
def _cmd_outreach_list(args: argparse.Namespace) -> None:
    from outreach import list_outreach_status

    statuses = list_outreach_status()
    if not statuses:
        print("No outreach contacts yet. Add one with: automator outreach add")
        return
    for s in statuses:
        confirmed_label = "confirmed" if s["confirmed"] else "unconfirmed"
        print(f"[{s['status']:8}] [{confirmed_label:11}] {s['company']} — {s['contact_email']}")
```

- [ ] **Step 6: Register the discover and confirm subcommands**

In `automator/cli.py`'s `build_parser()`, immediately after `outreach_list_p` block (currently ending around line 176, right before the `return parser` for the `outreach` block — check the exact end of the `outreach_list_p.set_defaults(func=_cmd_outreach_list)` line), add:

```python
    outreach_discover_p = outreach_sub.add_parser("discover", help="Discover new startup contacts (YC directory)")
    outreach_discover_p.set_defaults(func=_cmd_outreach_discover)

    outreach_confirm_p = outreach_sub.add_parser("confirm", help="Manually confirm/override a contact's email")
    outreach_confirm_p.add_argument("contact_id", help="The contact's id (see `automator outreach list`)")
    outreach_confirm_p.add_argument("email", help="The email address to set and confirm")
    outreach_confirm_p.set_defaults(func=_cmd_outreach_confirm)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_cli_outreach_discover.py -v`
Expected: 5 tests PASS

- [ ] **Step 8: Add new modules to pyproject.toml's py-modules**

In `pyproject.toml`, change:

```toml
py-modules = [
    "pipeline", "generator", "researcher", "scraper", "gmail_reader",
    "job_fetcher", "factual_validator", "scorer", "archive_processed",
    "manual_run", "crawl4ai_scraper", "accomplishments", "outreach",
]
```

to:

```toml
py-modules = [
    "pipeline", "generator", "researcher", "scraper", "gmail_reader",
    "job_fetcher", "factual_validator", "scorer", "archive_processed",
    "manual_run", "crawl4ai_scraper", "accomplishments", "outreach",
    "yc_scraper", "email_verify",
]
```

- [ ] **Step 9: Update README.md usage section**

In `README.md`, change:

```
# Show outreach contact status
automator outreach list
```

to:

```
# Show outreach contact status (drafted/pending, confirmed/unconfirmed)
automator outreach list

# Discover new startup contacts from YC's directory (guesses + SMTP-verifies emails)
automator outreach discover

# Manually confirm/override a discovered contact's email
automator outreach confirm <contact-id> <email>
```

- [ ] **Step 10: Run the full test suite as a regression check**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 11: Commit**

```bash
git add automator/cli.py pyproject.toml README.md tests/test_cli_outreach_discover.py
git commit -m "feat: wire outreach discover/confirm into the automator CLI"
```

---

## Self-Review Notes

- **Spec coverage:** Email guessing + SMTP verification (fails closed, generic prefixes, `dig`-based MX lookup) → Task 1. YC scraper with disclosed live-exploration risk → Task 2. `confirmed` field/backward compatibility, pluggable `_DISCOVERY_SOURCES`, `discover_contacts`, `confirm_contact_manual`, `run_outreach` skipping unconfirmed contacts, `list_outreach_status`'s new field, config section → Task 3. CLI subcommands, packaging, docs → Task 4. Non-goals (no second source built, no founder-name scraping, no GUI, no auto-send) → confirmed no task builds any of these. Testing sections from the spec (all 4 test files' bullet points) → each task's Step 1.
- **Placeholder scan:** Task 2's `_fetch_yc_companies_async` contains a deliberate `raise NotImplementedError` body — this is the one disclosed exception in this plan (per the spec's Architecture section and this plan's Global Constraints), not an oversight; every other step in every task has complete, ready-to-use code.
- **Type consistency:** `guess_and_verify_email(domain: str) -> tuple[str, bool]` (Task 1) is imported and called identically in Task 3's `discover_contacts`. `scrape_yc_directory(batches_back: int = 2, limit: int = 50) -> list[dict]` (Task 2) matches `_DISCOVERY_SOURCES`' call convention in Task 3 (`scraper_fn(batches_back=batches_back, limit=limit)`) and the test fixtures' lambda signatures (`lambda batches_back, limit: [...]`) in both Task 3's and Task 4's tests. `discover_contacts() -> dict` and `confirm_contact_manual(contact_id: str, email: str) -> bool` (Task 3) match their Task 4 CLI call sites and test mocks exactly. `run_outreach()`'s and `list_outreach_status()`'s modified return shapes (`unconfirmed_skipped`, `confirmed`) are consistent between Task 3's implementation and Task 4's CLI code/tests.
- **Task ordering:** Task 3 depends on Task 1's `guess_and_verify_email` and Task 2's `scrape_yc_directory`; Task 4 depends on Task 3's three new/modified functions — sequential, matching subagent-driven-development's one-implementer-at-a-time execution. Tasks 1 and 2 are mutually independent and could in principle run in either order, but the plan lists Task 1 first since it carries no research risk and establishes a fully-specified precedent before Task 2's exploratory task.
