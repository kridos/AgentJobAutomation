# Auto-flush After Run — Design Spec

## Context

`docs/superpowers/specs/2026-07-29-living-self-profile-design.md` added
`automator log` (quick-capture into `context/recent_updates.md`) and
`automator flush` (manually promote staged entries into permanent
`context/accomplishments.md`). The user wants an opt-in way to skip the
manual `automator flush` step and have it happen automatically at the end
of a successful `automator run`.

## Goal

An opt-in config flag that, when enabled, flushes `recent_updates.md` into
`accomplishments.md` automatically at the end of every non-dry-run
`automator run`, using the exact same non-fatal, best-effort pattern the
pipeline already uses for auto-archiving `processed.json`.

## Non-goals

- Not on by default — off unless explicitly enabled in `config.yaml`.
- No change to `automator flush`'s manual behavior; auto-flush is purely
  an additional trigger point that calls the same existing `flush()`
  function.
- No external-source ingestion (GitHub/LinkedIn/website) — raised during
  brainstorming as a separate, bigger future sub-project, explicitly out
  of scope here.

## Architecture

Mirrors `pipeline.py`'s existing `_auto_archive` function exactly — same
non-fatal try/except style, same call site (the `if not dry_run:` block at
the end of `run_pipeline`), same "opt-in via config" shape already used by
`scoring.enabled` and `research.enabled` in `config.yaml`.

## Components

**`config.yaml`** gains a new top-level section:

```yaml
accomplishments:
  auto_flush_after_run: false  # automatically flush recent_updates.md into accomplishments.md after each successful run
```

**`pipeline.py`** gains `_auto_flush(config: dict) -> None`, defined
immediately after `_auto_archive` (currently at `pipeline.py:57-63`):

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

Called from the same block where `_auto_archive` already runs (currently
`pipeline.py:579-581`):

```python
    if not dry_run:
        _save_processed(processed_path, processed)
        _auto_archive(processed_path)
        _auto_flush(config)
```

`config` is already in scope at this point in `run_pipeline` (loaded via
`config = _load_config()` near the top of the function), so no new
parameter threading is needed.

## Error handling

Identical to `_auto_archive`: any exception from `flush()` is caught,
logged to stderr with a `[pipeline] Auto-flush failed (non-fatal): ...`
message, and never propagates — a flush failure never breaks the pipeline
run itself.

## Testing

`tests/test_pipeline_autoflush.py`:
- `_auto_flush` is a no-op (does not import or call `accomplishments.flush`)
  when the config key is absent or `false`.
- `_auto_flush` calls `accomplishments.flush()` exactly once when
  `accomplishments.auto_flush_after_run` is `true` (monkeypatched, not a
  real flush against the filesystem).
