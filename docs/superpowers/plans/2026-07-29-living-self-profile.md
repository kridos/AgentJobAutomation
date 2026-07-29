# Living Self-Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `automator log`/`automator flush` for quick-capturing recent accomplishments into a staging file and later promoting them into a permanent record, both feeding tailored generation and factual validation without `context/resume_master.md` ever being auto-edited.

**Architecture:** A new `accomplishments.py` module (mirroring `archive_processed.py`'s style) owns two plain functions — `log_entry` and `flush` — operating on two new context files (`context/recent_updates.md` staging, `context/accomplishments.md` permanent). `automator/cli.py` gets two thin subcommands wrapping them. `generator.py` and `factual_validator.py` each get small, additive changes to read the two new files alongside the existing three context files.

**Tech Stack:** Python 3.10+, stdlib only (`pathlib`, `datetime`, `shutil`) — no new dependencies.

## Global Constraints

- No new runtime dependencies.
- `context/resume_master.md` is never written to by any code added in this plan.
- `log_entry` and `flush` are file I/O only — no network or LLM calls, so no error handling is needed beyond what's explicitly specified (empty-text rejection, empty-flush no-op).
- Entry format is exactly: `- YYYY-MM-DD [tags: a, b] text` with the tags segment omitted entirely when no tags are given.
- `_load_resume_master()` in `factual_validator.py` must concatenate `resume_master.md` first, then `accomplishments.md`, then `recent_updates.md` — in that order, since existing code (`_extract_canonical_name`, `_extract_allowed_contacts`) reads the first line / first 4 lines and depends on `resume_master.md`'s content being at the start of the combined string.

---

### Task 1: `accomplishments.py` module — `log_entry`

**Files:**
- Create: `accomplishments.py`
- Test: `tests/test_accomplishments.py`

**Interfaces:**
- Produces: `log_entry(text: str, tags: str | None = None, base_dir: Path = Path(".")) -> None` — raises `ValueError` on empty/whitespace `text`. Writes to `<base_dir>/context/recent_updates.md`. `base_dir` defaults to the current directory (matching how `archive_processed.py` already uses bare relative paths like `Path("processed.json")`), and exists as a parameter solely so tests can point it at a `tmp_path` without touching the real `context/` directory.

- [ ] **Step 1: Write the failing test**

Create `tests/test_accomplishments.py`:

```python
from pathlib import Path

import pytest

from accomplishments import log_entry


def test_log_entry_writes_dated_line_with_tags(tmp_path, monkeypatch):
    monkeypatch.setattr("accomplishments.date", _FixedDate)
    log_entry("Shipped RGB-D fusion milestone", tags="robotics, ai-ml", base_dir=tmp_path)

    content = (tmp_path / "context" / "recent_updates.md").read_text(encoding="utf-8")
    assert content == "- 2026-07-29 [tags: robotics, ai-ml] Shipped RGB-D fusion milestone\n"


def test_log_entry_writes_dated_line_without_tags(tmp_path, monkeypatch):
    monkeypatch.setattr("accomplishments.date", _FixedDate)
    log_entry("Migrated auth service to JWT", base_dir=tmp_path)

    content = (tmp_path / "context" / "recent_updates.md").read_text(encoding="utf-8")
    assert content == "- 2026-07-29 Migrated auth service to JWT\n"


def test_log_entry_appends_to_existing_file(tmp_path, monkeypatch):
    monkeypatch.setattr("accomplishments.date", _FixedDate)
    log_entry("First entry", base_dir=tmp_path)
    log_entry("Second entry", base_dir=tmp_path)

    content = (tmp_path / "context" / "recent_updates.md").read_text(encoding="utf-8")
    assert content == "- 2026-07-29 First entry\n- 2026-07-29 Second entry\n"


def test_log_entry_rejects_empty_text(tmp_path):
    with pytest.raises(ValueError):
        log_entry("   ", base_dir=tmp_path)


class _FixedDate:
    @staticmethod
    def today():
        return _FIXED_DATE


from datetime import date as _real_date
_FIXED_DATE = _real_date(2026, 7, 29)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_accomplishments.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'accomplishments'`

- [ ] **Step 3: Write minimal implementation**

Create `accomplishments.py`:

```python
"""
Quick-capture and promotion of recent accomplishments into permanent
context. Never writes to context/resume_master.md.
Run standalone: python accomplishments.py "some update" --tags a,b
"""

import shutil
import sys
from datetime import date, datetime
from pathlib import Path


def _recent_updates_path(base_dir: Path) -> Path:
    return base_dir / "context" / "recent_updates.md"


def _accomplishments_path(base_dir: Path) -> Path:
    return base_dir / "context" / "accomplishments.md"


def _archive_dir(base_dir: Path) -> Path:
    return base_dir / "context" / "archive"


def log_entry(text: str, tags: str | None = None, base_dir: Path = Path(".")) -> None:
    text = text.strip()
    if not text:
        raise ValueError("log entry text must not be empty")

    tag_segment = ""
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if tag_list:
            tag_segment = f" [tags: {', '.join(tag_list)}]"

    line = f"- {date.today().isoformat()}{tag_segment} {text}\n"

    path = _recent_updates_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python accomplishments.py \"some update\" [--tags a,b]", file=sys.stderr)
        sys.exit(1)
    text_arg = sys.argv[1]
    tags_arg = None
    if "--tags" in sys.argv:
        tags_arg = sys.argv[sys.argv.index("--tags") + 1]
    log_entry(text_arg, tags=tags_arg)
    print("Logged.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_accomplishments.py -v`
Expected: 4 tests PASS (the `flush` tests don't exist yet — only the 4 `log_entry` tests from Step 1 run at this point)

- [ ] **Step 5: Commit**

```bash
git add accomplishments.py tests/test_accomplishments.py
git commit -m "feat: add log_entry for quick-capturing recent accomplishments"
```

---

### Task 2: `accomplishments.py` — `flush`

**Files:**
- Modify: `accomplishments.py`
- Modify: `tests/test_accomplishments.py`

**Interfaces:**
- Consumes: `_recent_updates_path`, `_accomplishments_path`, `_archive_dir` from Task 1.
- Produces: `flush(base_dir: Path = Path(".")) -> int` — returns the count of entries (non-blank lines) flushed. `0` if there was nothing to flush.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_accomplishments.py`:

```python
from accomplishments import flush


def test_flush_moves_staged_entries_to_accomplishments(tmp_path):
    recent_path = tmp_path / "context" / "recent_updates.md"
    recent_path.parent.mkdir(parents=True)
    recent_path.write_text(
        "- 2026-07-15 [tags: backend] Migrated Provn's auth service to JWT\n"
        "- 2026-07-29 [tags: robotics] Shipped RGB-D fusion milestone\n",
        encoding="utf-8",
    )

    count = flush(base_dir=tmp_path)

    assert count == 2
    accomplishments_content = (tmp_path / "context" / "accomplishments.md").read_text(encoding="utf-8")
    assert "Migrated Provn's auth service to JWT" in accomplishments_content
    assert "Shipped RGB-D fusion milestone" in accomplishments_content
    assert recent_path.read_text(encoding="utf-8") == ""


def test_flush_archives_staged_content(tmp_path):
    recent_path = tmp_path / "context" / "recent_updates.md"
    recent_path.parent.mkdir(parents=True)
    recent_path.write_text("- 2026-07-29 Some entry\n", encoding="utf-8")

    flush(base_dir=tmp_path)

    archive_dir = tmp_path / "context" / "archive"
    archive_files = list(archive_dir.glob("recent_updates_*.md"))
    assert len(archive_files) == 1
    assert archive_files[0].read_text(encoding="utf-8") == "- 2026-07-29 Some entry\n"


def test_flush_appends_to_existing_accomplishments(tmp_path):
    context_dir = tmp_path / "context"
    context_dir.mkdir()
    (context_dir / "accomplishments.md").write_text("- 2026-06-01 Old entry\n", encoding="utf-8")
    (context_dir / "recent_updates.md").write_text("- 2026-07-29 New entry\n", encoding="utf-8")

    flush(base_dir=tmp_path)

    content = (context_dir / "accomplishments.md").read_text(encoding="utf-8")
    assert content == "- 2026-06-01 Old entry\n- 2026-07-29 New entry\n"


def test_flush_nothing_staged_returns_zero(tmp_path):
    count = flush(base_dir=tmp_path)

    assert count == 0
    assert not (tmp_path / "context" / "accomplishments.md").exists()
    assert not (tmp_path / "context" / "archive").exists()


def test_flush_empty_file_returns_zero(tmp_path):
    recent_path = tmp_path / "context" / "recent_updates.md"
    recent_path.parent.mkdir(parents=True)
    recent_path.write_text("   \n", encoding="utf-8")

    count = flush(base_dir=tmp_path)

    assert count == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_accomplishments.py -v`
Expected: FAIL — `ImportError: cannot import name 'flush' from 'accomplishments'`

- [ ] **Step 3: Implement `flush`**

Add to `accomplishments.py` (after `log_entry`, before the `if __name__ ==` block):

```python
def flush(base_dir: Path = Path(".")) -> int:
    recent_path = _recent_updates_path(base_dir)

    if not recent_path.exists():
        print("Nothing to flush.")
        return 0

    staged = recent_path.read_text(encoding="utf-8")
    lines = [line for line in staged.splitlines() if line.strip()]
    if not lines:
        print("Nothing to flush.")
        return 0

    accomplishments_path = _accomplishments_path(base_dir)
    accomplishments_path.parent.mkdir(parents=True, exist_ok=True)
    with open(accomplishments_path, "a", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")

    archive_dir = _archive_dir(base_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = archive_dir / f"recent_updates_{timestamp}.md"
    shutil.copy2(recent_path, archive_path)

    recent_path.write_text("", encoding="utf-8")

    print(f"Flushed {len(lines)} entr{'y' if len(lines) == 1 else 'ies'} to {accomplishments_path}")
    return len(lines)
```

Update the `if __name__ ==` block at the bottom of `accomplishments.py` to also support a `flush` mode:

```python
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python accomplishments.py \"some update\" [--tags a,b]", file=sys.stderr)
        print("       python accomplishments.py flush", file=sys.stderr)
        sys.exit(1)
    if sys.argv[1] == "flush":
        flush()
    else:
        text_arg = sys.argv[1]
        tags_arg = None
        if "--tags" in sys.argv:
            tags_arg = sys.argv[sys.argv.index("--tags") + 1]
        log_entry(text_arg, tags=tags_arg)
        print("Logged.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_accomplishments.py -v`
Expected: 9 tests PASS (4 from Task 1 + 5 from this task)

- [ ] **Step 5: Commit**

```bash
git add accomplishments.py tests/test_accomplishments.py
git commit -m "feat: add flush to promote staged entries into accomplishments.md"
```

---

### Task 3: `automator log` and `automator flush` subcommands

**Files:**
- Modify: `automator/cli.py`
- Test: `tests/test_cli_log_flush.py`

**Interfaces:**
- Consumes: `accomplishments.log_entry(text: str, tags: str | None = None) -> None` and `accomplishments.flush() -> int` from Tasks 1-2 (called with default `base_dir`, i.e. relative to wherever `automator` is invoked from — matching how `archive_processed.archive()` is already called with no path override in `_cmd_archive`).
- Produces: nothing consumed by later tasks in this plan.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_log_flush.py`:

```python
from automator.cli import build_parser


def test_log_parses_text_and_tags():
    parser = build_parser()
    args = parser.parse_args(["log", "Shipped a thing", "--tags", "backend,ai-ml"])
    assert args.command == "log"
    assert args.text == "Shipped a thing"
    assert args.tags == "backend,ai-ml"


def test_log_parses_without_tags():
    parser = build_parser()
    args = parser.parse_args(["log", "Shipped a thing"])
    assert args.text == "Shipped a thing"
    assert args.tags is None


def test_flush_parses():
    parser = build_parser()
    args = parser.parse_args(["flush"])
    assert args.command == "flush"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_log_flush.py -v`
Expected: FAIL — `argument command: invalid choice: 'log'`

- [ ] **Step 3: Add the subcommands**

In `automator/cli.py`, add these two handlers after `_cmd_archive` (before the `_TEST_MODULES` dict):

```python
def _cmd_log(args: argparse.Namespace) -> None:
    from accomplishments import log_entry

    try:
        log_entry(args.text, tags=args.tags)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print("Logged.")


def _cmd_flush(args: argparse.Namespace) -> None:
    from accomplishments import flush

    flush()
```

In `build_parser()`, add these two subparsers after the `archive_p` block and before the `test_p` block:

```python
    log_p = subparsers.add_parser("log", help="Quick-capture a recent accomplishment")
    log_p.add_argument("text", help="What you did, in your own words")
    log_p.add_argument("--tags", default=None, help="Comma-separated tags, e.g. backend,ai-ml")
    log_p.set_defaults(func=_cmd_log)

    flush_p = subparsers.add_parser("flush", help="Promote staged accomplishments into the permanent record")
    flush_p.set_defaults(func=_cmd_flush)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_log_flush.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add automator/cli.py tests/test_cli_log_flush.py
git commit -m "feat: add automator log and flush subcommands"
```

---

### Task 4: Wire recent accomplishments into `generator.py`

**Files:**
- Modify: `generator.py:20-31` (`_load_context_files`)
- Modify: `generator.py` (`_build_resume_prompt` and `_build_cover_letter_prompt`)
- Test: `tests/test_generator_context.py`

**Interfaces:**
- Produces: `_load_context_files()` return dict gains two keys, `"recent_updates"` and `"accomplishments"`, both defaulting to `""` with no stderr warning when the file is missing (unlike the three existing keys, which do warn).

- [ ] **Step 1: Write the failing test**

Create `tests/test_generator_context.py`:

```python
import generator


def test_load_context_files_includes_new_keys_defaulting_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(generator, "CONTEXT_DIR", tmp_path / "context")

    loaded = generator._load_context_files()

    assert loaded["recent_updates"] == ""
    assert loaded["accomplishments"] == ""
    # No missing-file warning for these two optional files
    captured = capsys.readouterr()
    assert "recent_updates.md" not in captured.err
    assert "accomplishments.md" not in captured.err


def test_build_resume_prompt_includes_accomplishments_when_present():
    context = {
        "resume_master": "# Test Resume\n",
        "voice": "",
        "preferences": "",
        "recent_updates": "- 2026-07-29 Pending thing\n",
        "accomplishments": "- 2026-06-01 Permanent thing\n",
    }
    listing = {"company": "Acme", "role": "SWE Intern", "location": "Remote", "link": ""}

    prompt = generator._build_resume_prompt(context, listing)

    assert "## Recent Accomplishments" in prompt
    assert "Permanent thing" in prompt
    assert "## Pending Updates" in prompt
    assert "Pending thing" in prompt


def test_build_resume_prompt_omits_blocks_when_empty():
    context = {
        "resume_master": "# Test Resume\n",
        "voice": "",
        "preferences": "",
        "recent_updates": "",
        "accomplishments": "",
    }
    listing = {"company": "Acme", "role": "SWE Intern", "location": "Remote", "link": ""}

    prompt = generator._build_resume_prompt(context, listing)

    assert "## Recent Accomplishments" not in prompt
    assert "## Pending Updates" not in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_generator_context.py -v`
Expected: FAIL — `KeyError: 'recent_updates'` (or assertion failure on missing keys)

- [ ] **Step 3: Update `_load_context_files`**

In `generator.py`, replace the `_load_context_files` function (currently at lines 20-31):

```python
def _load_context_files() -> dict[str, str]:
    files = {
        "resume_master": CONTEXT_DIR / "resume_master.md",
        "voice": CONTEXT_DIR / "voice.md",
        "preferences": CONTEXT_DIR / "preferences.md",
    }
    optional_files = {
        "recent_updates": CONTEXT_DIR / "recent_updates.md",
        "accomplishments": CONTEXT_DIR / "accomplishments.md",
    }
    loaded = {}
    for key, path in files.items():
        if path.exists():
            loaded[key] = path.read_text(encoding="utf-8")
        else:
            print(f"[generator] Warning: {path} not found", file=sys.stderr)
            loaded[key] = ""
    for key, path in optional_files.items():
        loaded[key] = path.read_text(encoding="utf-8") if path.exists() else ""
    return loaded
```

- [ ] **Step 4: Update `_build_resume_prompt` and `_build_cover_letter_prompt`**

In `_build_resume_prompt`, find this block:

```python
    if job_description:
        parts += ["", "## Job Posting (tailor directly to these requirements)\n" + job_description]

    if email_context:
        parts += ["", "## Recruiter Email Context (use to personalize)\n" + email_context]

    if research_context:
        parts += ["", "## Company/Role Research\n" + research_context]
```

Add these two blocks immediately before the `if job_description:` line:

```python
    if context.get("accomplishments"):
        parts += ["", "## Recent Accomplishments (permanent record — integrate if genuinely relevant)\n" + context["accomplishments"]]

    if context.get("recent_updates"):
        parts += ["", "## Pending Updates (not yet reviewed — integrate if genuinely relevant)\n" + context["recent_updates"]]

```

In `_build_cover_letter_prompt`, find this block:

```python
    if job_description:
        parts += ["", "## Job Posting (reference specific requirements and responsibilities)\n" + job_description]

    if email_context:
        parts += ["", "## Recruiter Email Context\n" + email_context]
```

Add the same two blocks immediately before the `if job_description:` line in this function too:

```python
    if context.get("accomplishments"):
        parts += ["", "## Recent Accomplishments (permanent record — integrate if genuinely relevant)\n" + context["accomplishments"]]

    if context.get("recent_updates"):
        parts += ["", "## Pending Updates (not yet reviewed — integrate if genuinely relevant)\n" + context["recent_updates"]]

```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_generator_context.py -v`
Expected: 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add generator.py tests/test_generator_context.py
git commit -m "feat: surface recent accomplishments and pending updates in generation prompts"
```

---

### Task 5: Wire recent accomplishments into `factual_validator.py`

**Files:**
- Modify: `factual_validator.py:39-41` (`_load_resume_master`)
- Test: `tests/test_validator_accomplishments.py`

**Interfaces:**
- Consumes: nothing from earlier tasks in this plan (this task only touches `factual_validator.py`, which is independent of `generator.py`/`cli.py`/`accomplishments.py`).
- Produces: `_load_resume_master()` now returns the concatenation of `resume_master.md`, `accomplishments.md`, `recent_updates.md` (in that order) instead of just `resume_master.md`. No other function signature in `factual_validator.py` changes.

- [ ] **Step 1: Write the failing test**

Create `tests/test_validator_accomplishments.py`:

```python
import factual_validator


def test_load_resume_master_includes_accomplishments_and_recent_updates(tmp_path, monkeypatch):
    monkeypatch.setattr(factual_validator, "CONTEXT_DIR", tmp_path)
    (tmp_path / "resume_master.md").write_text("# Test Resume\nline2\n", encoding="utf-8")
    (tmp_path / "accomplishments.md").write_text("- 2026-06-01 Permanent thing\n", encoding="utf-8")
    (tmp_path / "recent_updates.md").write_text("- 2026-07-29 Pending thing\n", encoding="utf-8")

    combined = factual_validator._load_resume_master()

    assert combined.startswith("# Test Resume\nline2\n")
    assert "Permanent thing" in combined
    assert "Pending thing" in combined


def test_load_resume_master_handles_missing_optional_files(tmp_path, monkeypatch):
    monkeypatch.setattr(factual_validator, "CONTEXT_DIR", tmp_path)
    (tmp_path / "resume_master.md").write_text("# Test Resume\n", encoding="utf-8")

    combined = factual_validator._load_resume_master()

    assert combined == "# Test Resume\n"


def test_metric_only_in_accomplishments_not_flagged(tmp_path, monkeypatch):
    # _extract_allowed_metrics runs a global regex over the combined text (not
    # gated to a specific section), so this is a realistic case: a percentage
    # mentioned only in a flat accomplishments.md bullet, with no matching
    # section structure required, unlike project/org headings which are
    # section-gated and wouldn't be picked up from a flat bullet log entry.
    monkeypatch.setattr(factual_validator, "CONTEXT_DIR", tmp_path)
    (tmp_path / "resume_master.md").write_text(
        "# Krish Doshi\nemail@example.com\n",
        encoding="utf-8",
    )
    (tmp_path / "accomplishments.md").write_text(
        "- 2026-06-01 [tags: backend] Reduced API latency by 40% using caching\n",
        encoding="utf-8",
    )

    # Note: cover_md deliberately does NOT restate the metric — _check_metric_claims
    # also allows any metric appearing in cover_md itself, which would make this
    # test pass even without the fix. The metric must be validated against the
    # combined resume_master/accomplishments/recent_updates text alone.
    resume_md = "# Krish Doshi\n\n- Reduced API latency by 40% using caching\n"
    cover_md = "Dear hiring team,\n\nI am excited to apply for this role.\n"
    listing = {"company": "Acme", "role": "SWE Intern"}

    result = factual_validator.validate_outputs(resume_md, cover_md, listing)

    metric_violations = [v for v in result["violations"] if v["category"] == "metric_claim"]
    assert metric_violations == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_validator_accomplishments.py -v`
Expected: FAIL — `test_load_resume_master_includes_accomplishments_and_recent_updates` fails because `combined` only contains `resume_master.md`'s content.

- [ ] **Step 3: Update `_load_resume_master`**

In `factual_validator.py`, replace the `_load_resume_master` function (currently at lines 39-41):

```python
def _load_resume_master() -> str:
    parts = []
    for name in ("resume_master.md", "accomplishments.md", "recent_updates.md"):
        path = CONTEXT_DIR / name
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_validator_accomplishments.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Run the full test suite as a regression check**

Run: `pytest tests/ -v`
Expected: All tests PASS (the concatenation order — `resume_master.md` first — preserves `_extract_canonical_name`'s and `_extract_allowed_contacts`'s existing behavior, since both only read from the start of the string)

- [ ] **Step 6: Commit**

```bash
git add factual_validator.py tests/test_validator_accomplishments.py
git commit -m "feat: treat accomplishments.md and recent_updates.md as allowed-fact sources"
```

---

## Self-Review Notes

- **Spec coverage:** `accomplishments.py` module (`log_entry`/`flush`) → Tasks 1-2. CLI subcommands → Task 3. Generator wiring (two new context keys, two new prompt blocks in both prompt builders) → Task 4. Validator wiring (`_load_resume_master` concatenation, in the order the spec requires) → Task 5. Error handling (empty-text rejection, empty-flush no-op) → Task 1 Step 3 and Task 2 Step 3. Archiving on flush → Task 2. Testing → one test file per task plus a full-suite regression run in Task 5.
- **Placeholder scan:** none found — every step has complete code.
- **Type consistency:** `log_entry(text: str, tags: str | None = None, base_dir: Path = Path("."))` is defined in Task 1 and called identically (with `base_dir` overridden only in tests) in Task 3's `_cmd_log`. `flush(base_dir: Path = Path(".")) -> int` is defined in Task 2 and called identically in Task 3's `_cmd_flush`. `_load_context_files()`'s new keys (`recent_updates`, `accomplishments`) match exactly what Task 4's prompt-builder changes read via `context.get(...)`.
