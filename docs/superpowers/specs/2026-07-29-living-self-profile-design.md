# Living Self-Profile — Design Spec

## Context

`context/resume_master.md` is a single hand-curated markdown file that is
the ground truth for both `generator.py` (which extracts sections from it
and injects the full text into LLM prompts) and `factual_validator.py`
(which regexes it to build allow-lists of contacts, GPA, degrees, orgs,
projects, techs, and metrics — anything a generated resume/cover letter
claims must trace back to this text or it's flagged as a hallucination and
blocked).

The problem: `resume_master.md` only changes when the user manually edits
it, so recent accomplishments (a new project shipped, a new internship
milestone) don't show up in tailored output until the user finds time to
carefully re-edit a document that also has a one-page-fit constraint and
specific tag-based formatting the generator depends on. This sub-project
adds a lightweight capture path for that recent work, without ever putting
`resume_master.md` itself at risk of automated corruption.

This is the second sub-project on the roadmap set up in
`docs/superpowers/specs/2026-07-29-automator-cli-design.md` (after the
`automator` CLI foundation).

## Goal

`automator log "<text>" [--tags a,b]` for a quick, dated capture, and
`automator flush` to move staged captures into a permanent record — both
feeding into resume/cover-letter generation and factual validation without
either automated command ever writing to `resume_master.md`.

## Non-goals

- No automated rewriting of `resume_master.md` itself, ever.
- No LLM-assisted placement/rewriting of flushed entries into Experience or
  Projects sections — that's a bigger, separate future sub-project.
- No staleness nudges, no automated GitHub-activity pulls, no time-windowed
  pruning of the permanent record — out of scope for this pass.

## Architecture

Three markdown files in `context/`, matching the existing flat-file
convention (`resume_master.md`, `voice.md`, `preferences.md` already work
this way):

- **`context/recent_updates.md`** — staging. `automator log` appends dated,
  optionally-tagged one-line entries here. Small and temporary by design.
- **`context/accomplishments.md`** (new) — permanent, append-only.
  `automator flush` moves everything staged in `recent_updates.md` here.
- **`context/resume_master.md`** — completely untouched by this feature.

All three files feed into `generator.py` (so recent and flushed
accomplishments can appear in tailored output) and `factual_validator.py`
(so their content is never flagged as an unsupported claim).

## Components

### `accomplishments.py` (new file, repo root)

Mirrors the existing style of `archive_processed.py` — module-level path
constants, plain functions, no classes.

```python
RECENT_UPDATES_PATH = Path("context/recent_updates.md")
ACCOMPLISHMENTS_PATH = Path("context/accomplishments.md")
ARCHIVE_DIR = Path("context/archive")

def log_entry(text: str, tags: str | None = None) -> None:
    """Append a dated, optionally-tagged entry to recent_updates.md.
    `tags` is the raw comma-separated string from the CLI (e.g. "a, b, c")
    or None; this function splits and strips it internally."""

def flush() -> int:
    """Move all staged entries from recent_updates.md into
    accomplishments.md, archive the flushed content with a timestamp
    (mirroring archive_processed.py's pattern for processed.json), then
    clear recent_updates.md. Returns the count of entries flushed."""
```

**Entry format** (one-line dated bullets):
```
- 2026-07-29 [tags: robotics, ai-ml] Shipped RGB-D fusion pipeline milestone at UW lab
- 2026-07-15 [tags: backend] Migrated Provn's auth service to JWT
```
The `[tags: ...]` segment is omitted entirely when no tags are given.

`log_entry`:
- Rejects empty/whitespace-only `text` (raises `ValueError`; the CLI layer
  turns this into exit code 1 with a message).
- Creates `context/recent_updates.md` if it doesn't exist.
- Splits `tags` on commas and strips whitespace on each tag before
  formatting the `[tags: ...]` segment.

`flush`:
- If `recent_updates.md` doesn't exist or is empty/whitespace-only, prints
  `"Nothing to flush."` and returns `0` — not an error.
- Otherwise: appends the full staged content to `accomplishments.md`
  (creating it if needed), copies the flushed content to
  `context/archive/recent_updates_<timestamp>.md`, clears
  `recent_updates.md`, and returns the number of entries (lines) flushed.

### `automator/cli.py` additions

Two more thin subcommands, following the exact pattern `manual`/`archive`
already use — lazy import, call straight into `accomplishments.py`, no
logic in `cli.py` itself:

```
automator log "<text>" [--tags a,b,c]
automator flush
```

### `generator.py` changes

`_load_context_files()` gains two more keys, defaulting to `""` with **no**
missing-file warning (unlike `resume_master`/`voice`/`preferences`, these
two are expected to be empty/absent for a new user):

```python
"recent_updates": CONTEXT_DIR / "recent_updates.md",
"accomplishments": CONTEXT_DIR / "accomplishments.md",
```

At the same two injection points where `resume_master` full text is already
dropped into the raw prompt (`_build_resume_prompt` and
`_build_cover_letter_prompt`), two more blocks are added — each entirely
omitted from the prompt when the corresponding context value is empty:

```python
if context.get("accomplishments"):
    parts += ["", "## Recent Accomplishments (permanent record — integrate if genuinely relevant)\n" + context["accomplishments"]]

if context.get("recent_updates"):
    parts += ["", "## Pending Updates (not yet reviewed — integrate if genuinely relevant)\n" + context["recent_updates"]]
```

### `factual_validator.py` changes

`_load_resume_master()` changes from loading just `resume_master.md` to
concatenating all three files in this exact order — `resume_master.md`
first, so the existing `_extract_canonical_name` (reads line 0) and
`_extract_allowed_contacts` (reads the first 4 lines) continue to work
unchanged:

```python
def _load_resume_master() -> str:
    parts = []
    for name in ("resume_master.md", "accomplishments.md", "recent_updates.md"):
        path = CONTEXT_DIR / name
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)
```

Every existing `_extract_allowed_*` function receives this combined string
unchanged — no other code in `factual_validator.py` needs to change, since
they already just regex whatever text they're handed.

## Error handling

All new code is file I/O only — no network or LLM calls, so no error
handling beyond what's listed above is needed:
- `log_entry` with empty/whitespace text → `ValueError`, CLI reports and
  exits 1.
- `flush` with nothing staged → prints a message, returns `0`, exit 0.

## Testing

`tests/test_accomplishments.py`:
- `log_entry` appends the correctly formatted line, with and without tags,
  to a `tmp_path`-based `recent_updates.md` (monkeypatch the module's path
  constants).
- `log_entry` raises `ValueError` on empty/whitespace text.
- `flush` moves staged content into `accomplishments.md`, writes an
  archive copy, and clears `recent_updates.md`.
- `flush` on an empty/missing `recent_updates.md` returns `0` and doesn't
  create `accomplishments.md` or an archive file.

`tests/test_cli_log_flush.py` (parsing only, matching the existing CLI test
style):
- `automator log "text" --tags a,b` parses to the right handler/args.
- `automator flush` parses to the right handler.

Generator and validator changes get small additions to their respective
test coverage:
- A test confirming `_build_resume_prompt`/`_build_cover_letter_prompt`
  include the "Recent Accomplishments" / "Pending Updates" blocks when
  those context values are non-empty, and omit them when empty.
- A test confirming a claim present only in `accomplishments.md` (not in
  `resume_master.md`) is not flagged as a violation by
  `factual_validator.validate_outputs`.

## Future work (explicitly out of scope here)

Using `resume_master.md` plus the accomplishments log together to
auto-draft a template resume, or LLM-assisted integration of flushed
entries into proper Experience/Project bullets — raised during
brainstorming as a bigger idea worth revisiting as its own sub-project
once this simpler capture-and-flush loop is in place.
