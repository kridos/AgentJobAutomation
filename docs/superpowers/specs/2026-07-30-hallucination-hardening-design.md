# Hallucination Hardening — Design Spec

## Context

`factual_validator.py` already validates generated resume/cover-letter output
against `context/resume_master.md` (plus `accomplishments.md` and
`recent_updates.md`), but every check is a fixed regex category: contact
details, GPA, degree, organization headings, project headings, unsupported
tech terms, and metric claims. `pipeline.py` runs this validator after
generation and, in balanced mode, retries once with corrective feedback
before blocking the application if violations remain
(`pipeline.py:220-260`).

The resume itself is already close to fully deterministic —
`generator._assemble_resume` copies the header, EDUCATION, TECHNICAL
SKILLS, and EXPERIENCE sections verbatim from `resume_master.md` and only
lets the model choose which 2-3 canonical PROJECTS blocks to include. The
cover letter is the real exposure: free-form prose whose factual claims
(responsibilities, accomplishments, phrasing of real projects) are only
checked against the fixed regex categories above. A fabricated claim that
doesn't match one of those shapes — an invented "led a team of 5", a
misdescribed accomplishment, an embellished responsibility — passes
through unnoticed today.

This is the next item on the roadmap set in
`docs/superpowers/specs/2026-07-29-automator-cli-design.md`.

## Goal

Catch fabrications that don't fit the existing fixed regex categories, in
both the resume and cover letter, by adding an LLM-based semantic
verification pass alongside (not replacing) the existing regex checks.

## Non-goals

- Not replacing any existing regex check — all current categories
  (contacts, GPA, degree, org, project, tech, metric) stay exactly as they
  are.
- Not restructuring `resume_master.md` into structured facts (YAML/JSON)
  in this pass. Raised as a fallback if the semantic pass proves too loose
  — see Future Work.
- Not changing `pipeline.py`'s retry/blocking control flow — the new check
  plugs into the existing `validate_outputs()` → `format_validation_feedback()`
  → corrective-retry loop by producing violations in the same shape the
  rest of the file already uses.

## Architecture

Add one new function, `_check_semantic_claims`, to `factual_validator.py`.
It asks the local Ollama model (via `generator._call_ollama`, reused as-is)
to compare the generated resume+cover-letter text against the canonical
context and return a strict JSON array of unsupported claims. This runs
inside the existing `validate_outputs()` alongside the regex checks, so
every call site in `pipeline.py` gets the new coverage automatically with
no control-flow changes.

The check is opt-in-by-default via a new `validation.semantic_check` flag
in `config.yaml`, mirroring the existing `validation.mode` /
`validation.retry_count` keys.

## Components

**`factual_validator.py`** gains:

```python
def _check_semantic_claims(
    resume_md: str,
    cover_md: str,
    resume_master: str,
    model: str,
    base_url: str,
) -> list[dict]:
    """Ask the local model to flag any claim in resume_md/cover_md not
    traceable to resume_master. Fails open (returns []) on any error —
    Ollama unreachable, malformed JSON response, etc. — since a broken
    verifier must never block every application; the regex checks still
    gate as they do today."""
```

- Prompt includes the combined resume+cover text and the full canonical
  context (`resume_master` — already the concatenation of
  `resume_master.md` + `accomplishments.md` + `recent_updates.md` per
  `_load_resume_master()`), and asks for ONLY a JSON array of
  `{"claim": "...", "reason": "..."}` objects, `[]` if every claim is
  supported.
- Calls `generator._call_ollama(prompt, model=model, base_url=base_url,
  temperature=0.1)` — low temperature since this is a verification task,
  not creative writing.
- Wrapped in `try/except`: any exception (connection error, timeout,
  `json.JSONDecodeError`, unexpected response shape) is caught, a warning
  is printed to stderr, and `[]` is returned.
- Each parsed item becomes a violation dict:
  `{"category": "semantic_unsupported", "claim": item["claim"], "reason":
  item.get("reason", "Claim not supported by canonical resume context")}`.

**`validate_outputs()`** gains two new optional parameters,
`model: str = ""` and `base_url: str = ""`, defaulting to
`generator.DEFAULT_MODEL` / `generator.OLLAMA_BASE_URL` when not supplied.
It calls `_check_semantic_claims` only when
`config.yaml`'s `validation.semantic_check` is enabled — since
`factual_validator.py` doesn't currently load `config.yaml` itself, the
enabled/disabled decision is made by the caller: `validate_outputs` gains
a third optional parameter `semantic_check: bool = True`, and skips the
call entirely when `False`.

**`pipeline.py`**'s 3 existing `validate_outputs(...)` call sites
(`pipeline.py:220`, `239`, `301`) pass through
`model=ollama_cfg.get("model", "qwen3:14b")`,
`base_url=ollama_cfg.get("base_url", "http://localhost:11434")`, and
`semantic_check=config.get("validation", {}).get("semantic_check", True)`
— the same config values already used for generation, so the verifier
judges claims against the same model tier as production, and respects the
new opt-out flag.

**`config.yaml`**'s `validation:` block gains:

```yaml
validation:
  mode: "balanced"
  retry_count: 1
  semantic_check: true   # LLM-based check for fabrications regex can't enumerate
```

## Error handling

`_check_semantic_claims` fails open: any error returns `[]`, never raises,
and never blocks the pipeline on its own. The existing regex checks are
unaffected by this function's failure — they run independently in
`validate_outputs()` and still gate the balanced-mode retry/block decision
as they do today. This means a broken or unavailable Ollama server
degrades hallucination coverage back to regex-only, rather than blocking
every application outright.

## Testing

`tests/test_factual_validator_semantic.py` (new):
- `_check_semantic_claims` returns parsed violation dicts when
  `_call_ollama` is mocked to return valid JSON with unsupported claims.
- `_check_semantic_claims` returns `[]` when `_call_ollama` is mocked to
  return `[]` (clean pass).
- `_check_semantic_claims` returns `[]` (fails open) when `_call_ollama` is
  mocked to return malformed JSON.
- `_check_semantic_claims` returns `[]` (fails open) when `_call_ollama` is
  mocked to raise an exception.
- `validate_outputs(..., semantic_check=False)` never calls
  `_check_semantic_claims` (mock call-count assertion).
- `validate_outputs(..., semantic_check=True)` includes
  `_check_semantic_claims`'s violations in the combined `violations` list
  and `categories` (mocked, no real Ollama server required).

No real Ollama server is required for any test — matching the existing
mocking style in `tests/test_researcher.py`.

## Future work (explicitly out of scope here)

If the semantic verifier proves too loose (misses real fabrications) or
too noisy (flags genuinely-supported claims too often) in practice, the
next step is restructuring `resume_master.md` into explicit structured
facts (YAML/JSON) that generation and verification can both check against
directly, rather than relying on free-text entailment by the same class of
model doing the generating. Raised during brainstorming as the fallback if
this pass doesn't work well enough.
