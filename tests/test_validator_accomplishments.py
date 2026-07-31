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


def test_load_resume_master_returns_empty_when_primary_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(factual_validator, "CONTEXT_DIR", tmp_path)
    (tmp_path / "accomplishments.md").write_text("- 2026-06-01 [tags: backend] Reduced API latency by 40%\n", encoding="utf-8")
    (tmp_path / "recent_updates.md").write_text("- 2026-07-29 Pending thing\n", encoding="utf-8")

    combined = factual_validator._load_resume_master()

    assert combined == ""


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


def test_fabricated_percentage_metric_is_flagged(tmp_path, monkeypatch):
    # Regression test: _METRIC_RE previously required a trailing \b after "%",
    # which never matches ("%" is a non-word char, so no boundary follows it
    # when trailing a space or period). That silently made every percentage
    # metric invisible to this check, so a completely fabricated percentage
    # sailed through unflagged. Assert a fabricated one is caught.
    monkeypatch.setattr(factual_validator, "CONTEXT_DIR", tmp_path)
    (tmp_path / "resume_master.md").write_text(
        "# Krish Doshi\nemail@example.com\n",
        encoding="utf-8",
    )

    resume_md = "# Krish Doshi\n\n- Boosted revenue by 75% through automation.\n"
    cover_md = "Dear hiring team,\n\nI am excited to apply for this role.\n"
    listing = {"company": "Acme", "role": "SWE Intern"}

    result = factual_validator.validate_outputs(resume_md, cover_md, listing)

    metric_violations = [v for v in result["violations"] if v["category"] == "metric_claim"]
    assert any("75%" in v["claim"] for v in metric_violations)


def test_candidate_name_from_output_skips_greeting_lines():
    assert factual_validator._candidate_name_from_output("Hi Jane,\n\nI wanted to reach out...") == ""
    assert factual_validator._candidate_name_from_output("Dear Jane,\n\nI wanted to reach out...") == ""


def test_candidate_name_from_output_still_finds_resume_name():
    assert factual_validator._candidate_name_from_output("John Smith\nSoftware Engineer\n") == "John Smith"
