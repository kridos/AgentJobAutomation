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
