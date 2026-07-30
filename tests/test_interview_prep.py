import json
from pathlib import Path

import interview_prep


def _write_application(date: str, source: str, company_slug: str, role_slug: str, role: str = "Software Engineer Intern", job_description: str = "") -> Path:
    app_dir = Path("output") / date / source / company_slug / role_slug
    app_dir.mkdir(parents=True, exist_ok=True)
    listing = {"company": "Acme Corp", "role": role, "location": "Remote", "link": "https://acme.com", "date_posted": date, "id": f"{company_slug}-{role_slug}"}
    (app_dir / "listing.json").write_text(json.dumps(listing), encoding="utf-8")
    if job_description:
        (app_dir / "job_description.txt").write_text(job_description, encoding="utf-8")
    return app_dir


def test_find_application_returns_single_match(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    expected = _write_application("2026-07-01", "simplify", "acme_corp", "swe_intern")

    result = interview_prep._find_application("Acme Corp")

    assert result == expected


def test_find_application_returns_most_recent_of_multiple_matches(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_application("2026-01-01", "simplify", "acme_corp", "swe_intern")
    newest = _write_application("2026-07-01", "simplify", "acme_corp", "ml_intern")

    result = interview_prep._find_application("Acme Corp")

    assert result == newest


def test_find_application_returns_none_when_no_match(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = interview_prep._find_application("Nonexistent Co")

    assert result is None


def test_generate_interview_prep_returns_not_found_without_generation_calls(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(interview_prep, "_find_application", lambda company, role_hint="": None)

    research_calls = []
    monkeypatch.setattr(interview_prep, "research", lambda *a, **k: research_calls.append(1) or "")
    ollama_calls = []
    monkeypatch.setattr(interview_prep, "_call_ollama", lambda *a, **k: ollama_calls.append(1) or "")

    result = interview_prep.generate_interview_prep("Nonexistent Co")

    assert result == {"status": "not_found", "path": None}
    assert research_calls == []
    assert ollama_calls == []


def test_generate_interview_prep_blocks_on_repeated_validation_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app_dir = _write_application("2026-07-01", "simplify", "acme_corp", "swe_intern")
    monkeypatch.setattr(interview_prep, "_find_application", lambda company, role_hint="": app_dir)
    monkeypatch.setattr(interview_prep, "research", lambda *a, **k: "")
    monkeypatch.setattr(interview_prep, "_load_context_files", lambda: {"resume_master": "", "voice": "", "preferences": "", "accomplishments": "", "recent_updates": ""})
    monkeypatch.setattr(interview_prep, "_call_ollama", lambda *a, **k: "bad content")
    monkeypatch.setattr(
        interview_prep, "validate_outputs",
        lambda *a, **k: {"passed": False, "violation_count": 1, "categories": ["x"], "violations": [{"category": "x", "claim": "y", "reason": "z"}]},
    )

    result = interview_prep.generate_interview_prep("Acme Corp")

    assert result == {"status": "validation_blocked", "path": None}
    assert not (app_dir / "interview_prep.md").exists()


def test_generate_interview_prep_returns_generation_failed_on_ollama_exception(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app_dir = _write_application("2026-07-01", "simplify", "acme_corp", "swe_intern")
    monkeypatch.setattr(interview_prep, "_find_application", lambda company, role_hint="": app_dir)
    monkeypatch.setattr(interview_prep, "research", lambda *a, **k: "")
    monkeypatch.setattr(interview_prep, "_load_context_files", lambda: {"resume_master": "", "voice": "", "preferences": "", "accomplishments": "", "recent_updates": ""})

    def _raise(*a, **k):
        raise RuntimeError("Ollama not running")

    monkeypatch.setattr(interview_prep, "_call_ollama", _raise)

    result = interview_prep.generate_interview_prep("Acme Corp")

    assert result == {"status": "generation_failed", "path": None}
    assert not (app_dir / "interview_prep.md").exists()


def test_generate_interview_prep_writes_all_sections_on_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app_dir = _write_application("2026-07-01", "simplify", "acme_corp", "swe_intern", job_description="graphs and dynamic programming")
    monkeypatch.setattr(interview_prep, "_find_application", lambda company, role_hint="": app_dir)
    monkeypatch.setattr(interview_prep, "research", lambda *a, **k: "Acme Corp builds widgets.")
    monkeypatch.setattr(interview_prep, "_load_context_files", lambda: {"resume_master": "", "voice": "", "preferences": "", "accomplishments": "", "recent_updates": ""})
    monkeypatch.setattr(interview_prep, "_call_ollama", lambda *a, **k: "## Likely Questions & Talking Points\n- Q: Why Acme?")
    monkeypatch.setattr(interview_prep, "validate_outputs", lambda *a, **k: {"passed": True, "violation_count": 0, "categories": [], "violations": []})
    monkeypatch.setattr(interview_prep, "match_problems", lambda job_description, limit=8: [{"title": "Number of Islands", "tags": ["graphs"], "difficulty": "medium", "link": "https://leetcode.com/problems/number-of-islands/"}])

    result = interview_prep.generate_interview_prep("Acme Corp")

    assert result["status"] == "ok"
    content = (app_dir / "interview_prep.md").read_text(encoding="utf-8")
    assert "Acme Corp builds widgets." in content
    assert "Likely Questions & Talking Points" in content
    assert "Number of Islands" in content
    assert "## Practice Problems" in content
