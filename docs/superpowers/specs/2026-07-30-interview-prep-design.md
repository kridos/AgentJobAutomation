# Interview Prep — Design Spec

## Context

No existing code touches interview preparation. This is the next item on
the roadmap set in `docs/superpowers/specs/2026-07-29-automator-cli-design.md`,
from the original brainstorm: "prepare for interviews (using agent and
pulling resources and attaching good problems for it)".

Each processed application already lives at
`output/<date>/<source>/<company-slug>/<role-slug>/` (`pipeline.py:343-357`)
with `listing.json` (company/role/link), `job_description.txt` (the real
posting text, when fetched), `resume.md`, `cover_letter.md`, and
`quality_score.json`. `researcher.py`'s company/role research is generated
in-memory during the original run and discarded — not cached to disk —
so interview prep re-runs it rather than trying to load a cached copy.

## Goal

`automator prep <company>` locates an existing application by company
name, and generates `interview_prep.md` in that application's output
folder: company/role research, likely behavioral and role-specific
questions, resume-bullet-to-STAR-format talking points (hallucination-
checked against your real background), and a curated set of relevant
technical practice problems.

## Non-goals

- Not automatic — this is on-demand, run only once you actually land an
  interview, not generated for every application during `automator run`
  (most applications never reach an interview stage; generating prep
  material for all of them would waste LLM calls).
- No LLM-generated coding problems — practice problems come from a
  bundled, curated, real list (title + topic tags + a lookup link, not
  full copyrighted problem text), matched deterministically by keyword
  overlap with the job description. Consistent with this project's
  existing preference for real data over LLM invention (deterministic
  resume assembly, real scraped job listings, real SMTP verification
  rather than guessed confidence).
- No interview scheduling, calendar integration, or mock-interview
  simulation.

## Architecture

A new `interview_prep.py` module, following the same shape as
`outreach.py`: file-lookup helpers, prompt-building, generation reusing
`generator._call_ollama`/`_load_context_files`, hallucination-checking
via the same `factual_validator.validate_outputs(content, content, listing)`
double-argument reuse trick `outreach.py` already established, and one
orchestration function. A separate `interview_problems.py` module owns
the curated problem list and its deterministic matching — no LLM
involvement, fully unit-testable on its own.

**Application lookup:** `automator prep <company>` globs
`output/*/*/<company-slug>/*/listing.json` (company name slugified the
same way `pipeline.py`'s `_slugify` already does). If exactly one match,
proceeds directly. If multiple matches (different dates or roles at the
same company), prints all matches with their paths and dates, and — since
this is a CLI command that should work non-interactively by default —
proceeds with the most recent one, noting which was picked and how to
target a different one (`automator prep <company> --role "<role>"`). If
zero matches, prints a clear error (no application found for that
company — check `automator outreach list`/`processed.json`... actually
just: "run `automator run` first, or check the company name") and exits
non-zero.

## Components

**`interview_problems.py`** (new, no dependency on anything else in this
project):
```python
_PROBLEMS = [
    {"title": "Two Sum", "tags": ["arrays", "hash-map"], "difficulty": "easy",
     "link": "https://leetcode.com/problems/two-sum/"},
    # ... ~75-100 well-known problems, bundled as a Python list literal in
    # this module (title + tags + difficulty + link only — never the full
    # problem statement, which is the source site's content, not ours to
    # redistribute)
]

def match_problems(job_description: str, limit: int = 8) -> list[dict]:
    """Deterministically scores each bundled problem by how many of its
    tags appear as keywords in job_description (case-insensitive
    substring match, mirroring factual_validator.py's existing
    COMMON_TECH_TERMS matching style), returns the top `limit` by score.
    Falls back to a fixed, well-rounded default set (a few problems per
    major topic) when nothing scores above zero, so the output is never
    empty even for a vague or unfetched job description."""
```

**`interview_prep.py`** (new):
```python
def _find_application(company: str, role_hint: str = "") -> Path | None:
    """Globs output/*/*/<company-slug>/*/listing.json for the slugified
    company name, optionally filtered by role_hint (substring match
    against the role in listing.json). Returns the most recent match's
    directory, or None if no match. Prints disambiguation info to stdout
    when multiple matches exist."""

def _build_prep_prompt(context: dict, listing: dict, job_description: str,
                        research_context: str) -> str:
    """Prompt asking for: likely behavioral + role-specific interview
    questions, and resume-bullet-to-STAR-format talking points for those
    questions — grounded strictly in My Background, same HARD RULE
    no-fabrication instructions as the resume/cover-letter/cold-email
    prompts."""

def generate_interview_prep(company: str, role_hint: str = "") -> dict:
    """Orchestrates: find the application, re-run researcher.research(),
    generate the questions+talking-points content, validate it via
    factual_validator.validate_outputs(content, content, listing,
    semantic_check=...) with the same one-corrective-retry pattern
    outreach.py uses, match technical problems via
    interview_problems.match_problems(job_description), assemble and
    save interview_prep.md into the application's output directory.
    Returns {"status": "ok"|"not_found"|"validation_blocked", "path": str|None}."""
```

`interview_prep.md`'s structure: a "## Company Research" section, a
"## Likely Questions & Talking Points" section (the validated LLM
content), and a "## Practice Problems" section (deterministically
generated from `match_problems`'s output, formatted as a markdown list
with title/difficulty/tags/link — no LLM involvement in this section at
all, so it can never fail validation).

**`automator/cli.py`** gains one subcommand:
```
automator prep <company> [--role "<role substring>"]
```
Thin wiring: calls `interview_prep.generate_interview_prep(company, role)`,
prints the result path or a clear error/status message.

## Error handling

- No matching application: `generate_interview_prep` returns
  `{"status": "not_found", "path": None}`; the CLI prints a clear message
  and exits non-zero.
- Research failure: non-fatal, exactly like the existing pipeline —
  `researcher.research()` already returns `""` on any failure, and an
  empty research context just means that section of the prompt is
  omitted (same pattern `generator.py`'s prompt-builders already use for
  optional context blocks).
- Validation failure after one corrective retry: `generate_interview_prep`
  returns `{"status": "validation_blocked", "path": None}` rather than
  saving unvalidated content — mirrors `outreach.py`'s exact
  fail-safe behavior.
- `interview_problems.match_problems` never raises and never returns an
  empty list (falls back to a fixed default set) — the practice-problems
  section is unconditionally present in the output.

## Testing

`tests/test_interview_problems.py`:
- `match_problems` returns problems whose tags overlap with keywords in
  a job description (e.g. a description mentioning "graph traversal"
  returns graph-tagged problems).
- `match_problems` returns the fixed default set when the job description
  has no matching keywords (mocked/synthetic description with no
  technical terms at all).
- `match_problems` respects `limit`.

`tests/test_interview_prep.py`:
- `_find_application` returns the correct directory for a single match
  (using a temp `output/` tree via `tmp_path`/`monkeypatch.chdir`).
- `_find_application` returns the most recent match and doesn't crash
  when multiple dated directories exist for the same company.
- `_find_application` returns `None` when no match exists.
- `generate_interview_prep` returns `{"status": "not_found", ...}` when
  `_find_application` returns `None`, without calling
  `researcher.research` or `generator._call_ollama` (mocked, asserting
  zero calls).
- `generate_interview_prep` returns `{"status": "validation_blocked", ...}`
  and does not write `interview_prep.md` when validation fails twice
  (mocked `validate_outputs` always returning `passed: False`).
- `generate_interview_prep` writes `interview_prep.md` containing all
  three sections (research, questions/talking-points, practice problems)
  on a successful run (mocked generation + validation + matching).

`tests/test_cli_prep.py`:
- `automator prep <company>` dispatches to
  `interview_prep.generate_interview_prep` with the company (and
  `--role` value, when given) and prints the result path or an error
  message matching the returned status.
