# automator CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an installable `automator` CLI with subcommands wrapping the existing pipeline scripts (`run`, `manual`, `archive`, `test`, `gui`-stub), replacing ad-hoc `python <script>.py` invocations.

**Architecture:** A new `automator/cli.py` module holds a thin `argparse` subparser dispatcher. Each subcommand handler does a local import of the existing top-level module (`pipeline`, `manual_run`, `archive_processed`, `scraper`, `gmail_reader`, `generator`, `researcher`) and calls into it — no business logic moves into the CLI package. Packaged via `pyproject.toml` with a `console_scripts` entry point so `pip install -e .` puts `automator` on PATH.

**Tech Stack:** Python 3.10+, stdlib `argparse` + `runpy`, `pytest` (new dev dependency for tests), existing project deps unchanged.

## Global Constraints

- No new runtime dependencies beyond what's already in `requirements.txt` (PyYAML, httpx, APScheduler, python-dotenv). `pytest` is added but only as a `dev` extra, not a runtime dependency.
- `browser-use` / `playwright` stay optional — the CLI package must not hard-require them.
- No natural-language/agent command routing — dispatch is deterministic `argparse` subparsers only.
- Every subcommand handler must only call existing functions; no new pipeline/business logic beyond the explicitly scoped `limit` param on `run_pipeline`.
- `test_crawl4ai.py` and `debug_violations.py` are not wrapped by the CLI and are untouched by this plan.

---

### Task 1: Package skeleton + entry point

**Files:**
- Create: `pyproject.toml`
- Create: `automator/__init__.py`
- Create: `automator/cli.py`
- Test: `tests/test_cli_help.py`

**Interfaces:**
- Produces: `automator.cli.build_parser() -> argparse.ArgumentParser` and `automator.cli.main() -> None`, used by every later task to add subcommands.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_help.py`:

```python
import subprocess
import sys


def test_cli_help_runs():
    result = subprocess.run(
        [sys.executable, "-m", "automator.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "automator" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_help.py -v`
Expected: FAIL — `No module named automator`

- [ ] **Step 3: Write minimal implementation**

Create `automator/__init__.py` (empty file).

Create `automator/cli.py`:

```python
"""Argparse-based dispatcher for the automator CLI."""

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="automator", description="Internship automation pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
```

Create `pyproject.toml`:

```toml
[project]
name = "automator"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "PyYAML>=6.0",
    "httpx>=0.25.0",
    "APScheduler>=3.10.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = ["pytest>=7.0"]

[project.scripts]
automator = "automator.cli:main"

[tool.setuptools]
py-modules = [
    "pipeline", "generator", "researcher", "scraper", "gmail_reader",
    "job_fetcher", "factual_validator", "scorer", "archive_processed",
    "manual_run", "crawl4ai_scraper",
]
packages = ["automator"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

- [ ] **Step 4: Install and run test to verify it passes**

Run: `pip install -e ".[dev]"`
Run: `pytest tests/test_cli_help.py -v`
Expected: PASS

Note: `build_parser()` currently has no subparsers with `func` set, so bare `automator` (no args) will error with "the following arguments are required: command" — that's correct argparse behavior and will be exercised properly once Task 2+ add real subcommands.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml automator/__init__.py automator/cli.py tests/test_cli_help.py
git commit -m "feat: add automator CLI package skeleton with entry point"
```

---

### Task 2: `run` subcommand + `--limit` on the pipeline

**Files:**
- Modify: `pipeline.py` (add `limit` parameter to `run_pipeline`)
- Modify: `automator/cli.py` (add `run` subcommand)
- Test: `tests/test_pipeline_limit.py`
- Test: `tests/test_cli_run.py`

**Interfaces:**
- Consumes: `automator.cli.build_parser()` from Task 1.
- Produces: `pipeline.run_pipeline(dry_run: bool = False, limit: int | None = None) -> dict` — later tasks (scheduler kwargs) rely on this exact signature.

- [ ] **Step 1: Write the failing test for the pipeline limit**

Create `tests/test_pipeline_limit.py`:

```python
from dataclasses import asdict

import pipeline
from scraper import Listing


def _fake_listing(i: int) -> Listing:
    return Listing(
        company=f"Company{i}",
        role="Software Engineering Intern",
        location="Remote",
        link=f"https://example.com/{i}",
        date_posted="2026-01-01",
    )


def test_run_pipeline_stops_at_limit(monkeypatch, tmp_path):
    fake_listings = [_fake_listing(i) for i in range(5)]

    monkeypatch.setattr("scraper.scrape", lambda repo, branch: fake_listings)
    monkeypatch.setattr("scraper.scrape_newgrad", lambda branch: [])
    monkeypatch.setattr("gmail_reader.get_recruiter_listings", lambda **kwargs: [])
    monkeypatch.chdir(tmp_path)

    stats = pipeline.run_pipeline(dry_run=True, limit=2)

    assert stats["processed"] == 2


def test_run_pipeline_no_limit_processes_all(monkeypatch, tmp_path):
    fake_listings = [_fake_listing(i) for i in range(3)]

    monkeypatch.setattr("scraper.scrape", lambda repo, branch: fake_listings)
    monkeypatch.setattr("scraper.scrape_newgrad", lambda branch: [])
    monkeypatch.setattr("gmail_reader.get_recruiter_listings", lambda **kwargs: [])
    monkeypatch.chdir(tmp_path)

    stats = pipeline.run_pipeline(dry_run=True, limit=None)

    assert stats["processed"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline_limit.py -v`
Expected: FAIL — `run_pipeline() got an unexpected keyword argument 'limit'`

- [ ] **Step 3: Implement the limit in `pipeline.py`**

In `pipeline.py`, change the `run_pipeline` signature:

```python
def run_pipeline(dry_run: bool = False, limit: int | None = None) -> dict:
```

Immediately after `stats = {...}` is built (before `processed = _load_processed(processed_path)`), add:

```python
    def _limit_hit() -> bool:
        return limit is not None and stats["processed"] >= limit
```

After each of the four `_process_listing(...)` calls inside their respective `for` loops (the SimplifyJobs loop, the New-Grad loop, the crawl4ai loop, and the Gmail loop), add a break check. For example, the SimplifyJobs loop becomes:

```python
    for listing in listings:
        if listing.id in processed:
            stats["skipped_duplicate"] += 1
            continue
        passes, reason = _filter_listing(listing.role, listing.company, preferences_text)
        if not passes:
            print(f"[pipeline] Skipping {listing.company} — {reason}")
            stats["skipped_filter"] += 1
            continue
        _process_listing(
            listing_id=listing.id,
            company=listing.company,
            role=listing.role,
            location=listing.location,
            link=listing.link,
            date_posted=listing.date_posted,
            listing_dict=asdict(listing),
            source="simplify",
            **common_args,
        )
        if _limit_hit():
            break
```

Apply the same `if _limit_hit(): break` line at the end of the New-Grad loop, the crawl4ai loop, and the Gmail loop bodies (same indentation level as the loop's other statements, right after the `_process_listing(...)` call in each).

Additionally, guard entry into each subsequent source section so a reached limit skips further scraping. Wrap the New-Grad section, the crawl4ai section, and the Gmail section each with a leading guard. For example, before the New-Grad section comment block, add:

```python
    # ── Source 1B: SimplifyJobs New-Grad-Positions ─────────────────────────────
    if _limit_hit():
        newgrad_listings = []
    else:
        print("[pipeline] Scraping SimplifyJobs New-Grad-Positions...", flush=True)
        try:
            newgrad_listings = scrape_newgrad(branch)
            stats["found"] += len(newgrad_listings)
            print(f"[pipeline] Found {len(newgrad_listings)} new grad listings", flush=True)
        except Exception as e:
            msg = f"New-Grad scraper failed: {e}"
            print(f"[pipeline] ERROR: {msg}", file=sys.stderr)
            stats["errors"].append(msg)
            newgrad_listings = []
```

Apply the same `if _limit_hit(): <listings> = []` short-circuit pattern to the crawl4ai section (skip the `if crawl4ai_enabled:` block entirely when the limit is already hit) and the Gmail section (skip the `get_recruiter_listings` call when the limit is already hit).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pipeline_limit.py -v`
Expected: PASS

- [ ] **Step 5: Write the failing CLI test**

Create `tests/test_cli_run.py`:

```python
from automator.cli import build_parser


def test_run_parses_flags():
    parser = build_parser()
    args = parser.parse_args(["run", "--dry-run", "--limit", "5"])
    assert args.command == "run"
    assert args.dry_run is True
    assert args.limit == 5
    assert args.schedule is False
    assert args.interval_hours == 24


def test_run_defaults():
    parser = build_parser()
    args = parser.parse_args(["run"])
    assert args.dry_run is False
    assert args.limit is None
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest tests/test_cli_run.py -v`
Expected: FAIL — `argument command: invalid choice: 'run'` (no `run` subparser exists yet)

- [ ] **Step 7: Add the `run` subcommand to `automator/cli.py`**

Replace the contents of `automator/cli.py` with:

```python
"""Argparse-based dispatcher for the automator CLI."""

import argparse
import sys


def _cmd_run(args: argparse.Namespace) -> None:
    from pipeline import run_pipeline

    if args.schedule:
        _cmd_run_scheduled(args)
        return

    stats = run_pipeline(dry_run=args.dry_run, limit=args.limit)
    print(
        f"\nDone. Processed: {stats['processed']} | Skipped: {stats['skipped_duplicate']} duplicates, "
        f"{stats['skipped_filter']} filtered | Errors: {len(stats['errors'])}"
    )
    if stats["errors"]:
        for e in stats["errors"]:
            print(f"  ERROR: {e}", file=sys.stderr)


def _cmd_run_scheduled(args: argparse.Namespace) -> None:
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        print("APScheduler not installed. Run: pip install APScheduler", file=sys.stderr)
        sys.exit(1)

    from pipeline import run_pipeline

    print(f"Starting scheduler — running pipeline every {args.interval_hours}h. Press Ctrl+C to stop.\n")
    run_pipeline(dry_run=args.dry_run, limit=args.limit)

    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_pipeline,
        "interval",
        hours=args.interval_hours,
        kwargs={"dry_run": args.dry_run, "limit": args.limit},
        id="pipeline",
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nScheduler stopped.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="automator", description="Internship automation pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_p = subparsers.add_parser("run", help="Run the pipeline")
    run_p.add_argument("--dry-run", action="store_true", help="Scrape and filter only, skip generation")
    run_p.add_argument("--schedule", action="store_true", help="Run on a recurring schedule")
    run_p.add_argument("--interval-hours", type=int, default=24, help="Schedule interval in hours (default: 24)")
    run_p.add_argument("--limit", type=int, default=None, help="Stop after processing N listings")
    run_p.set_defaults(func=_cmd_run)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/test_cli_run.py tests/test_cli_help.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add pipeline.py automator/cli.py tests/test_pipeline_limit.py tests/test_cli_run.py
git commit -m "feat: add automator run subcommand with --limit support"
```

---

### Task 3: `manual` and `archive` subcommands

**Files:**
- Modify: `automator/cli.py`
- Test: `tests/test_cli_manual_archive.py`

**Interfaces:**
- Consumes: `automator.cli.build_parser()` from Task 2 (adds two more subparsers to the same parser).
- Produces: `_cmd_manual`, `_cmd_archive` handlers — no other task depends on their internals.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_manual_archive.py`:

```python
from automator.cli import build_parser


def test_manual_parses():
    parser = build_parser()
    args = parser.parse_args(["manual"])
    assert args.command == "manual"


def test_archive_default_clears():
    parser = build_parser()
    args = parser.parse_args(["archive"])
    assert args.command == "archive"
    assert args.clear is True


def test_archive_keep_flag():
    parser = build_parser()
    args = parser.parse_args(["archive", "--keep"])
    assert args.clear is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_manual_archive.py -v`
Expected: FAIL — `argument command: invalid choice: 'manual'`

- [ ] **Step 3: Add the subcommands**

In `automator/cli.py`, add these two handler functions near `_cmd_run`:

```python
def _cmd_manual(args: argparse.Namespace) -> None:
    from manual_run import run_manual

    run_manual()


def _cmd_archive(args: argparse.Namespace) -> None:
    from archive_processed import archive

    archive(clear=args.clear)
```

In `build_parser()`, after the `run_p` block and before `return parser`, add:

```python
    manual_p = subparsers.add_parser("manual", help="Manually enter a single job listing")
    manual_p.set_defaults(func=_cmd_manual)

    archive_p = subparsers.add_parser("archive", help="Archive processed.json")
    archive_p.add_argument(
        "--keep", dest="clear", action="store_false", default=True,
        help="Archive without clearing processed.json (default: clear)",
    )
    archive_p.set_defaults(func=_cmd_archive)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_manual_archive.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add automator/cli.py tests/test_cli_manual_archive.py
git commit -m "feat: add automator manual and archive subcommands"
```

---

### Task 4: `test` subcommand (dispatches existing module self-tests)

**Files:**
- Modify: `automator/cli.py`
- Test: `tests/test_cli_test_cmd.py`

**Interfaces:**
- Consumes: `automator.cli.build_parser()` from Task 3.
- Produces: `_cmd_test` handler and the `_TEST_MODULES` mapping (`{"scraper": "scraper", "gmail": "gmail_reader", "generator": "generator", "researcher": "researcher"}`) — final task (README updates) references these exact subcommand names in its usage examples.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_test_cmd.py`:

```python
import runpy

from automator.cli import build_parser


def test_test_parses_module_and_args():
    parser = build_parser()
    args = parser.parse_args(["test", "gmail", "Google"])
    assert args.command == "test"
    assert args.module == "gmail"
    assert args.module_args == ["Google"]


def test_test_rejects_unknown_module():
    parser = build_parser()
    try:
        parser.parse_args(["test", "not-a-real-module"])
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_cmd_test_dispatches_to_runpy(monkeypatch):
    from automator import cli

    calls = []

    def fake_run_module(name, run_name):
        calls.append((name, run_name))

    monkeypatch.setattr(runpy, "run_module", fake_run_module)
    monkeypatch.setattr(cli, "runpy", runpy)

    parser = build_parser()
    args = parser.parse_args(["test", "gmail", "Google"])
    args.func(args)

    assert calls == [("gmail_reader", "__main__")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_test_cmd.py -v`
Expected: FAIL — `argument command: invalid choice: 'test'`

- [ ] **Step 3: Add the `test` subcommand**

In `automator/cli.py`, add `import runpy` to the top imports, then add near the other handlers:

```python
_TEST_MODULES = {
    "scraper": "scraper",
    "gmail": "gmail_reader",
    "generator": "generator",
    "researcher": "researcher",
}


def _cmd_test(args: argparse.Namespace) -> None:
    module_name = _TEST_MODULES[args.module]
    old_argv = sys.argv
    sys.argv = [module_name] + args.module_args
    try:
        runpy.run_module(module_name, run_name="__main__")
    finally:
        sys.argv = old_argv
```

In `build_parser()`, add before `return parser`:

```python
    test_p = subparsers.add_parser("test", help="Run a module's self-test")
    test_p.add_argument("module", choices=sorted(_TEST_MODULES))
    test_p.add_argument("module_args", nargs="*", help="Extra args passed to the module's self-test")
    test_p.set_defaults(func=_cmd_test)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_test_cmd.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add automator/cli.py tests/test_cli_test_cmd.py
git commit -m "feat: add automator test subcommand"
```

---

### Task 5: `gui` stub subcommand

**Files:**
- Modify: `automator/cli.py`
- Test: `tests/test_cli_gui.py`

**Interfaces:**
- Consumes: `automator.cli.build_parser()` from Task 4.
- Produces: nothing consumed by later tasks — this is the last subcommand.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_gui.py`:

```python
import io
from contextlib import redirect_stdout

from automator.cli import build_parser


def test_gui_parses():
    parser = build_parser()
    args = parser.parse_args(["gui"])
    assert args.command == "gui"


def test_gui_prints_stub_message():
    parser = build_parser()
    args = parser.parse_args(["gui"])
    buf = io.StringIO()
    with redirect_stdout(buf):
        args.func(args)
    assert "not built yet" in buf.getvalue()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_gui.py -v`
Expected: FAIL — `argument command: invalid choice: 'gui'`

- [ ] **Step 3: Add the `gui` subcommand**

In `automator/cli.py`, add:

```python
def _cmd_gui(args: argparse.Namespace) -> None:
    print("GUI not built yet — coming in a later update")
```

In `build_parser()`, add before `return parser`:

```python
    gui_p = subparsers.add_parser("gui", help="Launch the GUI (not yet implemented)")
    gui_p.set_defaults(func=_cmd_gui)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_gui.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add automator/cli.py tests/test_cli_gui.py
git commit -m "feat: add automator gui stub subcommand"
```

---

### Task 6: Remove duplicate batch scripts, update README

**Files:**
- Delete: `controlled_batch_run.py`
- Delete: `larger_batch_run.py`
- Modify: `README.md`
- Test: `tests/test_cli_help.py` (rerun as regression check, no new test needed — this task is docs/deletion only)

**Interfaces:**
- Consumes: all subcommands from Tasks 2–5 (this task only documents/removes, adds nothing new).

- [ ] **Step 1: Delete the duplicate scripts**

```bash
git rm controlled_batch_run.py larger_batch_run.py
```

- [ ] **Step 2: Update README.md usage section**

Replace the `## Setup` and `## Usage` sections of `README.md` with:

```markdown
## Setup

```bash
pip install -e ".[dev]"
playwright install chromium
```

Make sure Ollama is running with your model pulled:
```bash
ollama serve
ollama pull qwen2.5
```

Authenticate the `gh` CLI:
```bash
gh auth login
```

## Usage

```bash
# Run once
automator run

# Dry run — scrape and filter only, no generation
automator run --dry-run

# Stop after N listings (replaces the old controlled_batch_run.py / larger_batch_run.py scripts)
automator run --limit 5

# Run on a 24h schedule
automator run --schedule

# Custom schedule interval
automator run --schedule --interval-hours 12

# Manually enter a single job listing
automator manual

# Archive processed.json (clears it by default)
automator archive
automator archive --keep   # archive without clearing

# GUI (not yet implemented)
automator gui
```
```

Also replace the `## Testing Individual Modules` section with:

```markdown
## Testing Individual Modules

```bash
automator test scraper                    # test scraping
automator test gmail Google                # test Gmail MCP
automator test generator                   # test Ollama generation
automator test researcher Stripe "SWE Intern"  # test web research
```
```

- [ ] **Step 3: Run the full test suite as a regression check**

Run: `pytest tests/ -v`
Expected: All tests PASS (no test referenced the deleted scripts).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: switch README to automator CLI usage, remove duplicate batch scripts"
```

---

## Self-Review Notes

- **Spec coverage:** Packaging/entry point → Task 1. Command dispatch → Tasks 1–5. `run --limit` (replacing the two batch scripts) → Task 2 + Task 6. `manual`/`archive` → Task 3. `test <module>` → Task 4. `gui` stub → Task 5. README updates → Task 6. Error handling (ImportError guard for APScheduler) → carried over verbatim in Task 2. Testing → one test file per task, plus `test_cli_help.py` as final regression check.
- **Placeholder scan:** none found — every step has complete code.
- **Type consistency:** `run_pipeline(dry_run, limit)` signature introduced in Task 2 is reused identically in `_cmd_run` and `_cmd_run_scheduled`. `_TEST_MODULES` defined once in Task 4 and referenced only there (Task 6 only documents the subcommand names, not the dict).
