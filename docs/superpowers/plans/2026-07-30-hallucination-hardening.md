# Hallucination Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an LLM-based semantic verification pass to `factual_validator.py` that catches fabricated claims the existing fixed regex categories (contacts/GPA/degree/org/project/tech/metric) can't enumerate, wired into the existing balanced-mode retry/block flow with zero control-flow changes.

**Architecture:** One new function, `_check_semantic_claims`, calls the local Ollama model (via `generator._call_ollama`, reused as-is) to compare generated output against canonical context and return unsupported claims as JSON. `validate_outputs()` calls it alongside the existing regex checks, gated by a new opt-in-by-default `semantic_check` parameter that `pipeline.py` threads from a new `config.yaml` flag.

**Tech Stack:** Python 3.10+, stdlib `json` for parsing, reuses `generator._call_ollama` — no new dependencies.

## Global Constraints

- `_check_semantic_claims` never raises — any error (Ollama unreachable, malformed JSON, unexpected shape) is caught and it returns `[]` ("fails open"). The existing regex checks in `validate_outputs()` must be completely unaffected by this function failing.
- No changes to `pipeline.py`'s retry/blocking control flow (`pipeline.py:207-265`) — the new check only adds violations into the same dict shape `format_validation_feedback()` already consumes.
- `validate_outputs()`'s new `model`/`base_url`/`semantic_check` parameters must all be optional with defaults, so any existing caller that doesn't pass them keeps working unchanged.
- `config.yaml`'s new `validation.semantic_check` key defaults to `true` when read via `.get(..., True)` — matches the spec's "opt-in-by-default" framing (on unless explicitly disabled).

---

### Task 1: Semantic verifier in factual_validator.py + config flag + pipeline wiring

**Files:**
- Modify: `factual_validator.py` (add imports, `_check_semantic_claims`, extend `validate_outputs`)
- Modify: `pipeline.py:220`, `pipeline.py:239`, `pipeline.py:301` (pass new params to the 3 `validate_outputs` call sites)
- Modify: `config.yaml` (add `semantic_check: true` under the existing `validation:` block)
- Test: `tests/test_factual_validator_semantic.py`

**Interfaces:**
- Consumes: `generator._call_ollama(prompt: str, model: str = ..., base_url: str = ..., temperature: float = 0.7, max_tokens: int = 4096) -> str` (existing, unchanged), `generator.DEFAULT_MODEL` and `generator.OLLAMA_BASE_URL` constants (existing, unchanged).
- Produces: `factual_validator._check_semantic_claims(resume_md: str, cover_md: str, resume_master: str, model: str, base_url: str) -> list[dict]` and `factual_validator.validate_outputs(resume_md: str, cover_md: str, listing: dict, model: str = DEFAULT_MODEL, base_url: str = OLLAMA_BASE_URL, semantic_check: bool = True) -> dict` — both are used only within this task; no other task depends on them.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_factual_validator_semantic.py`:

```python
import json

import factual_validator


def test_semantic_claims_parses_valid_json_violations(monkeypatch):
    monkeypatch.setattr(
        factual_validator, "_call_ollama",
        lambda prompt, **kwargs: json.dumps(
            [{"claim": "Led a team of 5 engineers", "reason": "Not mentioned in resume_master"}]
        ),
    )

    result = factual_validator._check_semantic_claims(
        "resume text", "cover text", "canonical facts", "qwen3:14b", "http://localhost:11434"
    )

    assert result == [{
        "category": "semantic_unsupported",
        "claim": "Led a team of 5 engineers",
        "reason": "Not mentioned in resume_master",
    }]


def test_semantic_claims_returns_empty_on_clean_pass(monkeypatch):
    monkeypatch.setattr(factual_validator, "_call_ollama", lambda prompt, **kwargs: "[]")

    result = factual_validator._check_semantic_claims(
        "resume text", "cover text", "canonical facts", "qwen3:14b", "http://localhost:11434"
    )

    assert result == []


def test_semantic_claims_strips_markdown_code_fence(monkeypatch):
    monkeypatch.setattr(
        factual_validator, "_call_ollama",
        lambda prompt, **kwargs: '```json\n[{"claim": "Invented metric", "reason": "No source"}]\n```',
    )

    result = factual_validator._check_semantic_claims(
        "resume text", "cover text", "canonical facts", "qwen3:14b", "http://localhost:11434"
    )

    assert result == [{
        "category": "semantic_unsupported",
        "claim": "Invented metric",
        "reason": "No source",
    }]


def test_semantic_claims_fails_open_on_malformed_json(monkeypatch):
    monkeypatch.setattr(factual_validator, "_call_ollama", lambda prompt, **kwargs: "not json at all")

    result = factual_validator._check_semantic_claims(
        "resume text", "cover text", "canonical facts", "qwen3:14b", "http://localhost:11434"
    )

    assert result == []


def test_semantic_claims_fails_open_on_exception(monkeypatch):
    def _raise(prompt, **kwargs):
        raise RuntimeError("Ollama not running")

    monkeypatch.setattr(factual_validator, "_call_ollama", _raise)

    result = factual_validator._check_semantic_claims(
        "resume text", "cover text", "canonical facts", "qwen3:14b", "http://localhost:11434"
    )

    assert result == []


def test_validate_outputs_skips_semantic_check_when_disabled(monkeypatch):
    calls = []
    monkeypatch.setattr(factual_validator, "_load_resume_master", lambda: "")
    monkeypatch.setattr(factual_validator, "_check_semantic_claims", lambda *a, **k: calls.append(1) or [])

    result = factual_validator.validate_outputs("resume", "cover", {}, semantic_check=False)

    assert calls == []
    assert result["passed"] is True


def test_validate_outputs_includes_semantic_violations_when_enabled(monkeypatch):
    monkeypatch.setattr(factual_validator, "_load_resume_master", lambda: "")
    monkeypatch.setattr(
        factual_validator, "_check_semantic_claims",
        lambda *a, **k: [{"category": "semantic_unsupported", "claim": "X", "reason": "Y"}],
    )

    result = factual_validator.validate_outputs("resume", "cover", {}, semantic_check=True)

    assert result["passed"] is False
    assert result["violation_count"] == 1
    assert "semantic_unsupported" in result["categories"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_factual_validator_semantic.py -v`
Expected: FAIL — `AttributeError: module 'factual_validator' has no attribute '_call_ollama'` (and similar for `_check_semantic_claims`, and a `TypeError` for the unexpected `semantic_check` kwarg on `validate_outputs`)

- [ ] **Step 3: Add imports to factual_validator.py**

At the top of `factual_validator.py`, change:

```python
import re
from pathlib import Path
```

to:

```python
import json
import re
import sys
from pathlib import Path

from generator import _call_ollama, DEFAULT_MODEL, OLLAMA_BASE_URL
```

- [ ] **Step 4: Add `_check_semantic_claims`**

In `factual_validator.py`, immediately after `_check_metric_claims` and before `validate_outputs`, add:

```python
def _check_semantic_claims(
    resume_md: str,
    cover_md: str,
    resume_master: str,
    model: str,
    base_url: str,
) -> list[dict]:
    """Ask the local model to flag any claim in resume_md/cover_md not traceable
    to resume_master. Fails open (returns []) on any error — Ollama unreachable,
    malformed JSON response, etc. — since a broken verifier must never block
    every application; the regex checks still gate as they do today."""
    prompt = (
        "You are a strict fact-checker. Compare the CANDIDATE OUTPUT below against "
        "the CANONICAL FACTS. List every factual claim in the CANDIDATE OUTPUT about "
        "the candidate's experience, skills, accomplishments, or responsibilities that "
        "is NOT explicitly supported by the CANONICAL FACTS.\n\n"
        f"## CANONICAL FACTS\n{resume_master}\n\n"
        f"## CANDIDATE OUTPUT\n{resume_md}\n\n{cover_md}\n\n"
        "Respond with ONLY a JSON array, no other text. Each element: "
        '{"claim": "<the unsupported claim, verbatim>", "reason": "<why it is unsupported>"}. '
        "If every claim is supported, respond with exactly: []"
    )
    try:
        raw = _call_ollama(prompt, model=model, base_url=base_url, temperature=0.1).strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
        items = json.loads(raw)
        if not isinstance(items, list):
            return []
        violations = []
        for item in items:
            if not isinstance(item, dict) or "claim" not in item:
                continue
            violations.append({
                "category": "semantic_unsupported",
                "claim": item["claim"],
                "reason": item.get("reason", "Claim not supported by canonical resume context"),
            })
        return violations
    except Exception as e:
        print(f"[factual_validator] Semantic check failed (non-fatal): {e}", file=sys.stderr)
        return []
```

- [ ] **Step 5: Extend `validate_outputs`**

In `factual_validator.py`, change the `validate_outputs` signature from:

```python
def validate_outputs(resume_md: str, cover_md: str, listing: dict) -> dict:
```

to:

```python
def validate_outputs(
    resume_md: str,
    cover_md: str,
    listing: dict,
    model: str = DEFAULT_MODEL,
    base_url: str = OLLAMA_BASE_URL,
    semantic_check: bool = True,
) -> dict:
```

Then, immediately before the line `categories = sorted({v["category"] for v in violations})`, add:

```python
    if semantic_check:
        violations.extend(_check_semantic_claims(resume_md, cover_md, resume_master, model, base_url))

```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_factual_validator_semantic.py -v`
Expected: 7 tests PASS

- [ ] **Step 7: Add the config flag**

In `config.yaml`, change:

```yaml
validation:
  mode: "balanced"        # warn-only | balanced
  retry_count: 1           # balanced mode uses one corrective retry
```

to:

```yaml
validation:
  mode: "balanced"        # warn-only | balanced
  retry_count: 1           # balanced mode uses one corrective retry
  semantic_check: true    # LLM-based check for fabrications the regex checks can't enumerate
```

- [ ] **Step 8: Wire pipeline.py's 3 call sites**

In `pipeline.py`, change (currently at line 220):

```python
        first_validation = validate_outputs(resume_md, cover_md, listing_dict)
```

to:

```python
        first_validation = validate_outputs(
            resume_md, cover_md, listing_dict,
            model=ollama_cfg.get("model", "qwen3:14b"),
            base_url=ollama_cfg.get("base_url", "http://localhost:11434"),
            semantic_check=config.get("validation", {}).get("semantic_check", True),
        )
```

Change (currently at line 239):

```python
            second_validation = validate_outputs(resume_md, cover_md, listing_dict)
```

to:

```python
            second_validation = validate_outputs(
                resume_md, cover_md, listing_dict,
                model=ollama_cfg.get("model", "qwen3:14b"),
                base_url=ollama_cfg.get("base_url", "http://localhost:11434"),
                semantic_check=config.get("validation", {}).get("semantic_check", True),
            )
```

Change (currently at line 301):

```python
            rewrite_validation = validate_outputs(resume_md2, cover_md2, listing_dict)
```

to:

```python
            rewrite_validation = validate_outputs(
                resume_md2, cover_md2, listing_dict,
                model=ollama_cfg.get("model", "qwen3:14b"),
                base_url=ollama_cfg.get("base_url", "http://localhost:11434"),
                semantic_check=config.get("validation", {}).get("semantic_check", True),
            )
```

`config` and `ollama_cfg` are already in scope at all three call sites — both are parameters of the enclosing `_process_listing` function (`pipeline.py:108-131`).

- [ ] **Step 9: Run the full test suite as a regression check**

Run: `pytest tests/ -v`
Expected: All tests PASS. `generator.py` is unchanged (only consumed, not modified), and no other file imports `factual_validator.validate_outputs` with positional-only assumptions that would break from the new optional keyword parameters.

- [ ] **Step 10: Commit**

```bash
git add factual_validator.py pipeline.py config.yaml tests/test_factual_validator_semantic.py
git commit -m "feat: add LLM semantic verification pass to factual_validator"
```

---

## Self-Review Notes

- **Spec coverage:** Architecture (semantic check alongside regex, opt-in-by-default) → Steps 3-5, 7. Components (`_check_semantic_claims` signature and fail-open behavior, `validate_outputs`'s new optional params) → Steps 4-5. Config flag → Step 7. Pipeline wiring at all 3 call sites → Step 8. Error handling (fails open, regex checks unaffected) → Step 4's try/except and the fact that `_check_semantic_claims` is additive to the existing `violations` list, never gating it. Testing (all 6 bullet points from the spec's Testing section, plus a markdown-fence-stripping case since `_check_semantic_claims`'s implementation needs it to be robust to models that ignore the "ONLY a JSON array" instruction) → Step 1's 7 tests.
- **Placeholder scan:** none found — every step has complete code.
- **Type consistency:** `_check_semantic_claims(resume_md: str, cover_md: str, resume_master: str, model: str, base_url: str) -> list[dict]` and `validate_outputs(..., model: str = DEFAULT_MODEL, base_url: str = OLLAMA_BASE_URL, semantic_check: bool = True) -> dict` are used identically across the test file, the implementation, and `pipeline.py`'s call sites. Confirmed `config` and `ollama_cfg` are already parameters in scope at `pipeline.py`'s 3 call sites (`_process_listing`'s signature at `pipeline.py:108-131`) — no new parameter threading needed there.
- Single-task plan: one cohesive change (one new function, one extended function signature, one config key, three call-site updates) with one clear independently-testable deliverable — splitting further would add reviewer overhead without a meaningful separate-approval boundary, consistent with Task Right-Sizing guidance.
