# Auto-flush After Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An opt-in config flag that auto-flushes `context/recent_updates.md` into `context/accomplishments.md` at the end of a successful `automator run`, mirroring the existing auto-archive-on-run pattern.

**Architecture:** One new function `_auto_flush(config: dict) -> None` in `pipeline.py`, placed immediately after the existing `_auto_archive`, called from the same non-dry-run block. Reads a new `accomplishments.auto_flush_after_run` key from `config.yaml` (default `false`).

**Tech Stack:** Python 3.10+, stdlib only — no new dependencies.

## Global Constraints

- No new runtime dependencies.
- Auto-flush is opt-in: defaults to `false` when the config key is absent.
- Auto-flush must never run during a dry run (`dry_run=True`).
- A flush failure must be non-fatal — caught, logged to stderr, and never propagate — matching `_auto_archive`'s exact error-handling style.

---

### Task 1: `_auto_flush` in pipeline.py + config flag

**Files:**
- Modify: `config.yaml`
- Modify: `pipeline.py:57-63` (add `_auto_flush` after `_auto_archive`)
- Modify: `pipeline.py:579-581` (call `_auto_flush` in the non-dry-run block)
- Test: `tests/test_pipeline_autoflush.py`

**Interfaces:**
- Produces: `_auto_flush(config: dict) -> None` — imports `accomplishments.flush` lazily, matching `_auto_archive`'s lazy-import style (`from archive_processed import archive` inside the function body). No other task in this plan depends on this function since this is the only task.

- [ ] **Step 1: Write the failing test**

Create `tests/test_pipeline_autoflush.py`:

```python
import pipeline


def test_auto_flush_noop_when_disabled(monkeypatch):
    calls = []
    monkeypatch.setattr("accomplishments.flush", lambda: calls.append(1))

    pipeline._auto_flush({})
    pipeline._auto_flush({"accomplishments": {"auto_flush_after_run": False}})

    assert calls == []


def test_auto_flush_calls_flush_when_enabled(monkeypatch):
    calls = []
    monkeypatch.setattr("accomplishments.flush", lambda: calls.append(1))

    pipeline._auto_flush({"accomplishments": {"auto_flush_after_run": True}})

    assert calls == [1]


def test_auto_flush_failure_is_non_fatal(monkeypatch, capsys):
    def _raise():
        raise RuntimeError("boom")

    monkeypatch.setattr("accomplishments.flush", _raise)

    pipeline._auto_flush({"accomplishments": {"auto_flush_after_run": True}})

    captured = capsys.readouterr()
    assert "Auto-flush failed (non-fatal): boom" in captured.err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline_autoflush.py -v`
Expected: FAIL — `AttributeError: module 'pipeline' has no attribute '_auto_flush'`

- [ ] **Step 3: Add the config flag**

In `config.yaml`, add this new top-level section after the `research:` block and before `output:`:

```yaml
accomplishments:
  auto_flush_after_run: false  # automatically flush recent_updates.md into accomplishments.md after each successful run
```

- [ ] **Step 4: Add `_auto_flush` to pipeline.py**

In `pipeline.py`, immediately after the existing `_auto_archive` function (currently ending at line 63, right before `def _save_processed`), add:

```python
def _auto_flush(config: dict) -> None:
    """Flush recent_updates.md into accomplishments.md at the end of a successful run, if enabled."""
    if not config.get("accomplishments", {}).get("auto_flush_after_run", False):
        return
    from accomplishments import flush
    try:
        flush()
    except Exception as e:
        print(f"[pipeline] Auto-flush failed (non-fatal): {e}", file=sys.stderr)
```

- [ ] **Step 5: Call `_auto_flush` from `run_pipeline`**

In `pipeline.py`, find this block (currently around line 579-581):

```python
    if not dry_run:
        _save_processed(processed_path, processed)
        _auto_archive(processed_path)
```

Replace it with:

```python
    if not dry_run:
        _save_processed(processed_path, processed)
        _auto_archive(processed_path)
        _auto_flush(config)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_pipeline_autoflush.py -v`
Expected: 3 tests PASS

- [ ] **Step 7: Run the full test suite as a regression check**

Run: `pytest tests/ -v`
Expected: All tests PASS (this task only adds a new function and one new call site inside an existing `if not dry_run:` block — no existing behavior changes when the new config key is absent, which `config.yaml`'s existing structure guarantees for anyone not yet on this version of the file)

- [ ] **Step 8: Commit**

```bash
git add config.yaml pipeline.py tests/test_pipeline_autoflush.py
git commit -m "feat: add opt-in auto-flush of recent_updates.md after successful runs"
```

---

## Self-Review Notes

- **Spec coverage:** Config flag → Step 3. `_auto_flush` function (non-fatal error handling, opt-in default, lazy import) → Step 4. Call site inside the `if not dry_run:` block (never runs on dry run) → Step 5. Testing (no-op when disabled, calls flush when enabled, failure is non-fatal) → Step 1.
- **Placeholder scan:** none found — every step has complete code.
- **Type consistency:** `_auto_flush(config: dict) -> None` matches how `_auto_archive(processed_path: Path) -> None` is already called and defined in the same file — same style, same non-fatal try/except pattern, same lazy import.
- Single-task plan: the spec is small enough (one function, one config key, one call site) that splitting further would just add reviewer overhead without a meaningful independent-approval boundary — Task Right-Sizing calls for folding config/scaffolding into the task whose deliverable needs it, which is exactly this case.
