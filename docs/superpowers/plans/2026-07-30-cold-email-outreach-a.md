# Cold Email / Outreach — Sub-project A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `automator outreach add/run/list` — record contacts manually, generate a hallucination-checked cold email per contact and create it as a Gmail draft (never sent), tracking which contacts have already been drafted.

**Architecture:** `gmail_reader.py` gains draft-creation (mirroring its existing dynamic MCP-tool-discovery pattern). A new `outreach.py` owns contact storage, prompt-building, generation, and orchestration, reusing `generator._call_ollama`/`_load_context_files` and `factual_validator.validate_outputs` (called with the email body as both arguments) rather than duplicating them. `automator/cli.py` gains three thin subcommands.

**Tech Stack:** Python 3.10+, PyYAML (already a dependency) for the contacts file, stdlib `json` for processed-tracking — no new dependencies.

## Global Constraints

- Never auto-send — only `create_draft`, never any send-capable MCP tool.
- Every failure (generation, validation, draft creation) must be non-fatal: caught, logged to stderr, added to the run's error list, and the run continues with the next contact.
- A contact is marked processed (added to `outreach_processed.json`) only after a successful draft is created — a failed contact is retried on the next run, not silently dropped.
- `context/outreach_contacts.yaml` is gitignored (personal contact data) and is never auto-deleted — it's the user's own persistent record.
- No new runtime dependencies.

---

### Task 1: Gmail draft creation

**Files:**
- Modify: `gmail_reader.py` (add `_resolve_draft_tool_name`, `create_draft`)
- Test: `tests/test_gmail_draft.py`

**Interfaces:**
- Consumes: `_mcp_call(tool: str, params: dict, mcp_url: str = GMAIL_MCP_URL) -> dict` (existing, unchanged), `_mcp_list_tools(mcp_url: str = GMAIL_MCP_URL) -> list[str]` (existing, unchanged), `_TOOL_NAME_CACHE: dict[str, str]` (existing module-level cache, shared — this task's cache keys are prefixed `"draft|"` to avoid colliding with `_resolve_search_tool_name`'s unprefixed keys).
- Produces: `gmail_reader.create_draft(to: str, subject: str, body: str, mcp_url: str = GMAIL_MCP_URL, tool_name: str = "") -> bool` — consumed by Task 2's `outreach.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gmail_draft.py`:

```python
import gmail_reader


def test_resolve_draft_tool_name_picks_matching_candidate(monkeypatch):
    gmail_reader._TOOL_NAME_CACHE.clear()
    monkeypatch.setattr(gmail_reader, "_mcp_list_tools", lambda mcp_url: ["search_threads", "gmail_create_draft", "other_tool"])

    result = gmail_reader._resolve_draft_tool_name("https://fake-mcp", "")

    assert result == "gmail_create_draft"


def test_resolve_draft_tool_name_falls_back_to_substring_match(monkeypatch):
    gmail_reader._TOOL_NAME_CACHE.clear()
    monkeypatch.setattr(gmail_reader, "_mcp_list_tools", lambda mcp_url: ["search_threads", "compose_draft_message"])

    result = gmail_reader._resolve_draft_tool_name("https://fake-mcp", "")

    assert result == "compose_draft_message"


def test_resolve_draft_tool_name_falls_back_to_default_when_list_fails(monkeypatch):
    gmail_reader._TOOL_NAME_CACHE.clear()

    def _raise(mcp_url):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(gmail_reader, "_mcp_list_tools", _raise)

    result = gmail_reader._resolve_draft_tool_name("https://fake-mcp", "")

    assert result == gmail_reader.DEFAULT_DRAFT_TOOL


def test_create_draft_returns_true_on_success(monkeypatch):
    gmail_reader._TOOL_NAME_CACHE.clear()
    monkeypatch.setattr(gmail_reader, "_mcp_list_tools", lambda mcp_url: ["gmail_create_draft"])
    monkeypatch.setattr(gmail_reader, "_mcp_call", lambda tool, params, mcp_url: {"id": "draft-1"})

    result = gmail_reader.create_draft("jane@acme.com", "Subject", "Body text", "https://fake-mcp")

    assert result is True


def test_create_draft_returns_false_on_failure(monkeypatch):
    gmail_reader._TOOL_NAME_CACHE.clear()
    monkeypatch.setattr(gmail_reader, "_mcp_list_tools", lambda mcp_url: ["gmail_create_draft"])

    def _raise(tool, params, mcp_url):
        raise RuntimeError("MCP error")

    monkeypatch.setattr(gmail_reader, "_mcp_call", _raise)

    result = gmail_reader.create_draft("jane@acme.com", "Subject", "Body text", "https://fake-mcp")

    assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gmail_draft.py -v`
Expected: FAIL — `AttributeError: module 'gmail_reader' has no attribute '_resolve_draft_tool_name'` (and similar for `create_draft`, `DEFAULT_DRAFT_TOOL`)

- [ ] **Step 3: Add the draft-tool resolver and create_draft**

In `gmail_reader.py`, immediately after the `DEFAULT_SEARCH_TOOL = "search_threads"` line (currently line 28), add:

```python
DEFAULT_DRAFT_TOOL = "create_draft"
```

Then, immediately after `_resolve_search_tool_name` (currently ending at line 115, right before `_parse_mcp_content`), add:

```python
def _resolve_draft_tool_name(mcp_url: str = GMAIL_MCP_URL, configured_tool: str = "") -> str:
    cache_key = f"draft|{mcp_url}|{configured_tool}"
    if cache_key in _TOOL_NAME_CACHE:
        return _TOOL_NAME_CACHE[cache_key]

    candidates = [
        configured_tool,
        DEFAULT_DRAFT_TOOL,
        "gmail_create_draft",
        "gmail.create_draft",
        "draft_email",
        "create_email_draft",
    ]
    candidates = [name for name in candidates if name]

    try:
        tools = _mcp_list_tools(mcp_url)
    except Exception:
        _TOOL_NAME_CACHE[cache_key] = configured_tool or DEFAULT_DRAFT_TOOL
        return _TOOL_NAME_CACHE[cache_key]

    for candidate in candidates:
        if candidate in tools:
            _TOOL_NAME_CACHE[cache_key] = candidate
            return candidate

    for tool in tools:
        if "draft" in tool.lower():
            _TOOL_NAME_CACHE[cache_key] = tool
            return tool

    _TOOL_NAME_CACHE[cache_key] = configured_tool or DEFAULT_DRAFT_TOOL
    return _TOOL_NAME_CACHE[cache_key]
```

At the end of `gmail_reader.py` (after the last function, `get_recruiter_listings`, before the `if __name__ == "__main__":` block if one exists — otherwise at the end of the file), add:

```python
# ── Draft creation ────────────────────────────────────────────────────────

def create_draft(to: str, subject: str, body: str, mcp_url: str = GMAIL_MCP_URL, tool_name: str = "") -> bool:
    """Creates a Gmail draft via MCP. Never sends. Returns True on success,
    False on any failure (caught and logged, never raises)."""
    try:
        resolved_tool = _resolve_draft_tool_name(mcp_url, tool_name)
        _mcp_call(resolved_tool, {"to": to, "subject": subject, "body": body}, mcp_url=mcp_url)
        return True
    except Exception as e:
        print(f"[gmail_reader] Warning: could not create draft for '{to}': {e}", file=sys.stderr)
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_gmail_draft.py -v`
Expected: 5 tests PASS

- [ ] **Step 5: Run the full test suite as a regression check**

Run: `pytest tests/ -v`
Expected: All tests PASS — this task only adds new names to `gmail_reader.py`, no existing function is modified.

- [ ] **Step 6: Commit**

```bash
git add gmail_reader.py tests/test_gmail_draft.py
git commit -m "feat: add Gmail draft creation via MCP"
```

---

### Task 2: outreach.py core pipeline

**Files:**
- Create: `outreach.py`
- Modify: `.gitignore` (add `context/outreach_contacts.yaml`)
- Test: `tests/test_outreach.py`

**Interfaces:**
- Consumes: `gmail_reader.create_draft(to: str, subject: str, body: str, mcp_url: str = ..., tool_name: str = "") -> bool` (Task 1), `generator._call_ollama(prompt: str, model: str = ..., base_url: str = ..., temperature: float = 0.7, max_tokens: int = 4096) -> str` (existing, unchanged), `generator._load_context_files() -> dict[str, str]` (existing, unchanged), `factual_validator.validate_outputs(resume_md: str, cover_md: str, listing: dict, model: str = ..., base_url: str = ..., semantic_check: bool = True) -> dict` (existing, unchanged), `factual_validator.format_validation_feedback(result: dict) -> str` (existing, unchanged), `manual_run._prompt(label: str, default: str = "") -> str` and `manual_run._prompt_multiline(label: str) -> str` (existing, unchanged).
- Produces: `outreach.add_contact_interactive() -> None`, `outreach.run_outreach() -> dict` (returns `{"drafted": int, "skipped": int, "errors": list[str]}`), `outreach.list_outreach_status() -> list[dict]` (returns `[{"company": str, "contact_email": str, "status": "drafted" | "pending"}]`) — all three consumed by Task 3's CLI wiring.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_outreach.py`:

```python
import json

import outreach


def _fake_contact(company="Acme Corp", contact_name="Jane Doe", email="jane@acme.com", notes=""):
    return {
        "id": f"{company.lower().replace(' ', '-')}-{contact_name.lower().replace(' ', '-')}",
        "company": company,
        "contact_name": contact_name,
        "contact_email": email,
        "notes": notes,
    }


def test_build_cold_email_prompt_includes_company_and_notes():
    contact = _fake_contact(notes="Met at career fair")
    prompt = outreach._build_cold_email_prompt({"voice": "", "resume_master": ""}, contact)

    assert "Acme Corp" in prompt
    assert "Met at career fair" in prompt


def test_generate_cold_email_returns_ollama_output(monkeypatch):
    monkeypatch.setattr(outreach, "_load_context_files", lambda: {"voice": "", "resume_master": ""})
    monkeypatch.setattr(outreach, "_call_ollama", lambda prompt, **kwargs: "Hi Jane, ...")

    result = outreach.generate_cold_email(_fake_contact())

    assert result == "Hi Jane, ..."


def test_run_outreach_skips_already_processed_contact(monkeypatch, tmp_path):
    contact = _fake_contact()
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [contact])
    monkeypatch.setattr(outreach, "_load_outreach_processed", lambda: {contact["id"]})

    draft_calls = []
    monkeypatch.setattr(outreach, "create_draft", lambda *a, **k: draft_calls.append(1) or True)

    stats = outreach.run_outreach()

    assert draft_calls == []
    assert stats["skipped"] == 1
    assert stats["drafted"] == 0


def test_run_outreach_drafts_pending_contact_and_marks_processed(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    contact = _fake_contact()
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [contact])
    monkeypatch.setattr(outreach, "_load_outreach_processed", lambda: set())
    monkeypatch.setattr(outreach, "generate_cold_email", lambda c, **kwargs: "Hi Jane, I'd love to chat.")
    monkeypatch.setattr(outreach, "validate_outputs", lambda *a, **k: {"passed": True, "violation_count": 0, "categories": [], "violations": []})

    saved_processed = []
    monkeypatch.setattr(outreach, "_save_outreach_processed", lambda processed: saved_processed.append(set(processed)))

    draft_calls = []
    monkeypatch.setattr(outreach, "create_draft", lambda to, subject, body, **kwargs: draft_calls.append((to, subject, body)) or True)

    stats = outreach.run_outreach()

    assert stats["drafted"] == 1
    assert stats["skipped"] == 0
    assert draft_calls[0][0] == "jane@acme.com"
    assert saved_processed[-1] == {contact["id"]}


def test_run_outreach_does_not_mark_processed_when_draft_creation_fails(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    contact = _fake_contact()
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [contact])
    monkeypatch.setattr(outreach, "_load_outreach_processed", lambda: set())
    monkeypatch.setattr(outreach, "generate_cold_email", lambda c, **kwargs: "Hi Jane, I'd love to chat.")
    monkeypatch.setattr(outreach, "validate_outputs", lambda *a, **k: {"passed": True, "violation_count": 0, "categories": [], "violations": []})
    monkeypatch.setattr(outreach, "create_draft", lambda *a, **k: False)

    saved_processed = []
    monkeypatch.setattr(outreach, "_save_outreach_processed", lambda processed: saved_processed.append(set(processed)))

    stats = outreach.run_outreach()

    assert stats["drafted"] == 0
    assert saved_processed == []


def test_run_outreach_does_not_mark_processed_when_validation_fails_twice(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    contact = _fake_contact()
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [contact])
    monkeypatch.setattr(outreach, "_load_outreach_processed", lambda: set())
    monkeypatch.setattr(outreach, "generate_cold_email", lambda c, **kwargs: "bad content")
    monkeypatch.setattr(outreach, "validate_outputs", lambda *a, **k: {"passed": False, "violation_count": 1, "categories": ["x"], "violations": [{"category": "x", "claim": "y", "reason": "z"}]})

    draft_calls = []
    monkeypatch.setattr(outreach, "create_draft", lambda *a, **k: draft_calls.append(1) or True)

    stats = outreach.run_outreach()

    assert draft_calls == []
    assert stats["drafted"] == 0
    assert len(stats["errors"]) == 1


def test_list_outreach_status_reports_pending_and_drafted(monkeypatch):
    contact_a = _fake_contact(company="Acme Corp", contact_name="Jane Doe", email="jane@acme.com")
    contact_b = _fake_contact(company="Beta Inc", contact_name="Bob Roe", email="bob@beta.com")
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [contact_a, contact_b])
    monkeypatch.setattr(outreach, "_load_outreach_processed", lambda: {contact_a["id"]})

    result = outreach.list_outreach_status()

    statuses = {r["company"]: r["status"] for r in result}
    assert statuses["Acme Corp"] == "drafted"
    assert statuses["Beta Inc"] == "pending"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_outreach.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'outreach'`

- [ ] **Step 3: Create outreach.py**

Create `outreach.py`:

```python
"""
Cold-email outreach: generate a tailored, hallucination-checked email per
contact in context/outreach_contacts.yaml and create it as a Gmail draft
(never sent). Tracks which contacts have already been drafted.
Run standalone: python outreach.py
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

import yaml

from generator import _call_ollama, _load_context_files, DEFAULT_MODEL, OLLAMA_BASE_URL
from factual_validator import validate_outputs, format_validation_feedback
from gmail_reader import create_draft, GMAIL_MCP_URL


CONFIG_PATH = Path(__file__).parent / "config.yaml"
CONTEXT_DIR = Path(__file__).parent / "context"
CONTACTS_PATH = CONTEXT_DIR / "outreach_contacts.yaml"
PROCESSED_PATH = Path(__file__).parent / "outreach_processed.json"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _load_contacts() -> list[dict]:
    if not CONTACTS_PATH.exists():
        return []
    with open(CONTACTS_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, list) else []


def _save_contacts(contacts: list[dict]) -> None:
    CONTACTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONTACTS_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(contacts, f, sort_keys=False, allow_unicode=True)


def _load_outreach_processed() -> set[str]:
    if PROCESSED_PATH.exists():
        try:
            with open(PROCESSED_PATH, encoding="utf-8-sig") as f:
                data = json.load(f)
            return set(data) if isinstance(data, list) else set()
        except (json.JSONDecodeError, ValueError):
            print("[outreach] outreach_processed.json is malformed — starting fresh", file=sys.stderr)
    return set()


def _save_outreach_processed(processed: set[str]) -> None:
    with open(PROCESSED_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(processed), f, indent=2)


def _save_outreach_output(contact: dict, body: str) -> None:
    today = date.today().isoformat()
    company_slug = _slugify(contact.get("company", "unknown"))
    output_dir = Path("output") / today / "outreach" / company_slug
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "email.md").write_text(body, encoding="utf-8")
    (output_dir / "contact.json").write_text(json.dumps(contact, indent=2), encoding="utf-8")


def add_contact_interactive() -> None:
    from manual_run import _prompt, _prompt_multiline

    print("\n=== Add Outreach Contact ===\n")
    company = _prompt("Company name")
    contact_name = _prompt("Contact name (optional)")
    contact_email = _prompt("Contact email")
    notes = _prompt_multiline("Notes (optional — how you found them, what to mention):")

    if not company or not contact_email:
        print("Company and contact email are required.")
        sys.exit(1)

    contact_id = f"{_slugify(company)}-{_slugify(contact_name or contact_email)}"

    contacts = _load_contacts()
    contacts.append({
        "id": contact_id,
        "company": company,
        "contact_name": contact_name,
        "contact_email": contact_email,
        "notes": notes,
    })
    _save_contacts(contacts)

    print(f"\n[outreach] Added {company} ({contact_email}) to {CONTACTS_PATH}")


def _build_cold_email_prompt(context: dict, contact: dict, validation_feedback: str = "") -> str:
    company = contact.get("company", "")
    contact_name = contact.get("contact_name", "")
    notes = contact.get("notes", "")

    parts = [
        "You are writing a short, genuine cold outreach email to a potential employer, "
        "expressing interest in internship/full-time opportunities.",
        "",
        f"## Target\n**Company:** {company}\n**Contact:** {contact_name}",
        "",
        "## My Voice and Style Guide\n" + context.get("voice", ""),
        "",
        "## My Background (for facts/context)\n" + context.get("resume_master", ""),
    ]

    if context.get("accomplishments"):
        parts += ["", "## Recent Accomplishments (permanent record — integrate if genuinely relevant)\n" + context["accomplishments"]]

    if context.get("recent_updates"):
        parts += ["", "## Pending Updates (not yet reviewed — integrate if genuinely relevant)\n" + context["recent_updates"]]

    if notes:
        parts += ["", "## Notes About This Contact (use to personalize)\n" + notes]

    parts += [
        "",
        "## Instructions",
        "- HARD RULE: Do not invent or alter personal identity details (name, phone, email, links)",
        "- HARD RULE: Do not invent qualifications, degrees, GPA, employers, projects, dates, tools, metrics, awards, or responsibilities",
        "- HARD RULE: If a detail is not explicitly present in My Background above, omit it",
        "- Follow my voice guide strictly — match my tone, avoid the phrases I listed to avoid",
        "- Keep it SHORT: 3-5 sentences max, this is a cold email not a cover letter",
        "- Be specific about why this company, using the notes above if provided",
        "- End with a clear, low-friction ask (e.g. a quick call, or simply asking about openings)",
        "- Output ONLY the email body text, no subject line, no preamble, no explanation",
    ]

    if validation_feedback:
        parts += [
            "",
            "## Validation Corrections (must fix all)",
            validation_feedback,
            "Revise to remove or correct unsupported claims while preserving genuine interest and personalization.",
        ]

    return "\n".join(parts)


def generate_cold_email(
    contact: dict,
    validation_feedback: str = "",
    model: str = DEFAULT_MODEL,
    base_url: str = OLLAMA_BASE_URL,
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> str:
    context = _load_context_files()
    prompt = _build_cold_email_prompt(context, contact, validation_feedback)
    return _call_ollama(prompt, model=model, base_url=base_url, temperature=temperature, max_tokens=max_tokens).strip()


def _build_subject(contact: dict) -> str:
    company = contact.get("company", "")
    return f"Quick question about opportunities at {company}"


def run_outreach() -> dict:
    config = _load_config()
    ollama_cfg = config.get("ollama", {})
    gmail_cfg = config.get("gmail", {})

    model = ollama_cfg.get("model", "qwen3:14b")
    base_url = ollama_cfg.get("base_url", "http://localhost:11434")
    temperature = ollama_cfg.get("temperature", 0.7)
    mcp_url = gmail_cfg.get("mcp_url", GMAIL_MCP_URL)
    tool_name = gmail_cfg.get("tool_name", "")

    contacts = _load_contacts()
    processed = _load_outreach_processed()

    stats = {"drafted": 0, "skipped": 0, "errors": []}

    for contact in contacts:
        contact_id = contact.get("id", "")
        company = contact.get("company", "")

        if not contact_id or contact_id in processed:
            stats["skipped"] += 1
            continue

        email_addr = contact.get("contact_email", "")
        if not email_addr:
            msg = f"No contact_email for {company} ({contact_id}) — skipping"
            print(f"[outreach] {msg}", file=sys.stderr)
            stats["errors"].append(msg)
            continue

        try:
            body = generate_cold_email(contact, model=model, base_url=base_url, temperature=temperature)
            validation = validate_outputs(body, body, contact, model=model, base_url=base_url)

            if not validation.get("passed", False):
                feedback = format_validation_feedback(validation)
                retry_temp = min(float(temperature), 0.2)
                print(f"[outreach] Validation failed for {company}. Retrying once...", flush=True)
                body = generate_cold_email(contact, validation_feedback=feedback, model=model, base_url=base_url, temperature=retry_temp)
                validation = validate_outputs(body, body, contact, model=model, base_url=base_url)

                if not validation.get("passed", False):
                    msg = f"Validation blocked for {company} ({contact_id}): {validation.get('violation_count', 0)} unsupported claim(s)"
                    print(f"[outreach] ERROR: {msg}", file=sys.stderr)
                    stats["errors"].append(msg)
                    continue
        except Exception as e:
            msg = f"Generation failed for {company} ({contact_id}): {e}"
            print(f"[outreach] ERROR: {msg}", file=sys.stderr)
            stats["errors"].append(msg)
            continue

        subject = _build_subject(contact)
        try:
            drafted = create_draft(email_addr, subject, body, mcp_url=mcp_url, tool_name=tool_name)
        except Exception as e:
            drafted = False
            msg = f"Draft creation failed for {company} ({contact_id}): {e}"
            print(f"[outreach] ERROR: {msg}", file=sys.stderr)
            stats["errors"].append(msg)

        if not drafted:
            continue

        _save_outreach_output(contact, body)
        processed.add(contact_id)
        _save_outreach_processed(processed)
        stats["drafted"] += 1

    return stats


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


if __name__ == "__main__":
    stats = run_outreach()
    print(f"\nDrafted: {stats['drafted']} | Skipped: {stats['skipped']} | Errors: {len(stats['errors'])}")
```

- [ ] **Step 4: Add outreach_contacts.yaml to .gitignore**

In `.gitignore`, add this line after the existing `*.json` line:

```
context/outreach_contacts.yaml
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_outreach.py -v`
Expected: 7 tests PASS

- [ ] **Step 6: Run the full test suite as a regression check**

Run: `pytest tests/ -v`
Expected: All tests PASS — `outreach.py` is a new module; no existing file is modified except `.gitignore`.

- [ ] **Step 7: Commit**

```bash
git add outreach.py .gitignore tests/test_outreach.py
git commit -m "feat: add outreach.py core pipeline (contacts, generation, validation, drafting)"
```

---

### Task 3: CLI wiring

**Files:**
- Modify: `automator/cli.py` (add `outreach add`/`outreach run`/`outreach list` subcommands)
- Modify: `pyproject.toml:14-17` (add `"outreach"` to `py-modules`)
- Modify: `README.md:57` (add outreach usage examples)
- Test: `tests/test_cli_outreach.py`

**Interfaces:**
- Consumes: `outreach.add_contact_interactive() -> None`, `outreach.run_outreach() -> dict`, `outreach.list_outreach_status() -> list[dict]` (all from Task 2, exact signatures above).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_outreach.py`:

```python
from automator.cli import build_parser


def test_outreach_add_dispatches_to_add_contact_interactive(monkeypatch):
    calls = []
    monkeypatch.setattr("outreach.add_contact_interactive", lambda: calls.append(1))

    parser = build_parser()
    args = parser.parse_args(["outreach", "add"])
    args.func(args)

    assert calls == [1]


def test_outreach_run_dispatches_to_run_outreach(monkeypatch, capsys):
    monkeypatch.setattr("outreach.run_outreach", lambda: {"drafted": 2, "skipped": 1, "errors": []})

    parser = build_parser()
    args = parser.parse_args(["outreach", "run"])
    args.func(args)

    captured = capsys.readouterr()
    assert "Drafted: 2" in captured.out
    assert "Skipped: 1" in captured.out


def test_outreach_list_prints_status(monkeypatch, capsys):
    monkeypatch.setattr(
        "outreach.list_outreach_status",
        lambda: [{"company": "Acme Corp", "contact_email": "jane@acme.com", "status": "pending"}],
    )

    parser = build_parser()
    args = parser.parse_args(["outreach", "list"])
    args.func(args)

    captured = capsys.readouterr()
    assert "Acme Corp" in captured.out
    assert "pending" in captured.out


def test_outreach_list_handles_empty_list(monkeypatch, capsys):
    monkeypatch.setattr("outreach.list_outreach_status", lambda: [])

    parser = build_parser()
    args = parser.parse_args(["outreach", "list"])
    args.func(args)

    captured = capsys.readouterr()
    assert "No outreach contacts yet" in captured.out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli_outreach.py -v`
Expected: FAIL — `argparse.ArgumentError` / `SystemExit` since `outreach` isn't a recognized subcommand yet

- [ ] **Step 3: Add the CLI handlers**

In `automator/cli.py`, immediately after `_cmd_flush` (currently ending at line 84, right before the `_TEST_MODULES` dict) add:

```python
def _cmd_outreach_add(args: argparse.Namespace) -> None:
    from outreach import add_contact_interactive

    add_contact_interactive()


def _cmd_outreach_run(args: argparse.Namespace) -> None:
    from outreach import run_outreach

    stats = run_outreach()
    print(f"\nDone. Drafted: {stats['drafted']} | Skipped: {stats['skipped']} | Errors: {len(stats['errors'])}")
    if stats["errors"]:
        for e in stats["errors"]:
            print(f"  ERROR: {e}", file=sys.stderr)


def _cmd_outreach_list(args: argparse.Namespace) -> None:
    from outreach import list_outreach_status

    statuses = list_outreach_status()
    if not statuses:
        print("No outreach contacts yet. Add one with: automator outreach add")
        return
    for s in statuses:
        print(f"[{s['status']:8}] {s['company']} — {s['contact_email']}")
```

- [ ] **Step 4: Register the outreach subcommands**

In `automator/cli.py`'s `build_parser()`, immediately after the `flush_p` block (currently ending at line 136, right before the `test_p` block), add:

```python
    outreach_p = subparsers.add_parser("outreach", help="Cold-email outreach")
    outreach_sub = outreach_p.add_subparsers(dest="outreach_command", required=True)

    outreach_add_p = outreach_sub.add_parser("add", help="Manually add an outreach contact")
    outreach_add_p.set_defaults(func=_cmd_outreach_add)

    outreach_run_p = outreach_sub.add_parser("run", help="Generate and draft emails for pending contacts")
    outreach_run_p.set_defaults(func=_cmd_outreach_run)

    outreach_list_p = outreach_sub.add_parser("list", help="Show outreach contact status")
    outreach_list_p.set_defaults(func=_cmd_outreach_list)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_cli_outreach.py -v`
Expected: 4 tests PASS

- [ ] **Step 6: Add outreach to pyproject.toml's py-modules**

In `pyproject.toml`, change:

```toml
py-modules = [
    "pipeline", "generator", "researcher", "scraper", "gmail_reader",
    "job_fetcher", "factual_validator", "scorer", "archive_processed",
    "manual_run", "crawl4ai_scraper", "accomplishments",
]
```

to:

```toml
py-modules = [
    "pipeline", "generator", "researcher", "scraper", "gmail_reader",
    "job_fetcher", "factual_validator", "scorer", "archive_processed",
    "manual_run", "crawl4ai_scraper", "accomplishments", "outreach",
]
```

- [ ] **Step 7: Update README.md usage section**

In `README.md`, change:

```
# Manually enter a single job listing
automator manual

# Quick-capture a recent accomplishment
```

to:

```
# Manually enter a single job listing
automator manual

# Add a cold-outreach contact
automator outreach add

# Generate + draft cold emails for pending contacts (creates Gmail drafts, never sends)
automator outreach run

# Show outreach contact status
automator outreach list

# Quick-capture a recent accomplishment
```

- [ ] **Step 8: Run the full test suite as a regression check**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 9: Commit**

```bash
git add automator/cli.py pyproject.toml README.md tests/test_cli_outreach.py
git commit -m "feat: wire outreach add/run/list into the automator CLI"
```

---

## Self-Review Notes

- **Spec coverage:** Draft creation with dynamic tool discovery → Task 1. Contacts file + processed tracking + prompt building + generation + validation reuse (email body as both `resume_md`/`cover_md` args) + corrective retry + output saving → Task 2. CLI subcommands + packaging + docs → Task 3. Non-fatal error handling at every stage (generation, validation, draft creation) → Task 2's `run_outreach` try/except blocks, tested by Step 1's failure-path tests. `.gitignore` for the contacts file → Task 2 Step 4. Testing sections from the spec (gmail draft tool resolution 3-tier coverage, outreach core pipeline including the mark-processed-only-on-success guarantee, CLI dispatch) → Task 1/2/3 Step 1 tests respectively.
- **Placeholder scan:** none found — every step has complete code.
- **Type consistency:** `create_draft(to: str, subject: str, body: str, mcp_url: str = GMAIL_MCP_URL, tool_name: str = "") -> bool` (Task 1) is imported and called identically in Task 2's `run_outreach`. `run_outreach() -> dict` and `list_outreach_status() -> list[dict]` (Task 2) are called identically in Task 3's CLI handlers and match the shapes asserted in Task 3's tests (`stats['drafted']`, `stats['skipped']`, `stats['errors']`; `s['status']`, `s['company']`, `s['contact_email']`). `add_contact_interactive() -> None` (Task 2) matches its Task 3 call site exactly.
- **Task ordering:** Task 2 depends on Task 1's `create_draft`; Task 3 depends on Task 2's three public functions — sequential, matching subagent-driven-development's one-implementer-at-a-time execution.
