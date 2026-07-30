import json

import outreach


def _fake_contact(company="Acme Corp", contact_name="Jane Doe", email="jane@acme.com", notes=""):
    return {
        "id": f"{company.lower().replace(' ', '-')}-{contact_name.lower().replace(' ', '-')}",
        "company": company,
        "contact_name": contact_name,
        "contact_email": email,
        "notes": notes,
    }


def test_build_cold_email_prompt_includes_company_and_notes():
    contact = _fake_contact(notes="Met at career fair")
    prompt = outreach._build_cold_email_prompt({"voice": "", "resume_master": ""}, contact)

    assert "Acme Corp" in prompt
    assert "Met at career fair" in prompt


def test_generate_cold_email_returns_ollama_output(monkeypatch):
    monkeypatch.setattr(outreach, "_load_context_files", lambda: {"voice": "", "resume_master": ""})
    monkeypatch.setattr(outreach, "_call_ollama", lambda prompt, **kwargs: "Hi Jane, ...")

    result = outreach.generate_cold_email(_fake_contact())

    assert result == "Hi Jane, ..."


def test_run_outreach_skips_already_processed_contact(monkeypatch, tmp_path):
    contact = _fake_contact()
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [contact])
    monkeypatch.setattr(outreach, "_load_outreach_processed", lambda: {contact["id"]})

    draft_calls = []
    monkeypatch.setattr(outreach, "create_draft", lambda *a, **k: draft_calls.append(1) or True)

    stats = outreach.run_outreach()

    assert draft_calls == []
    assert stats["skipped"] == 1
    assert stats["drafted"] == 0


def test_run_outreach_drafts_pending_contact_and_marks_processed(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    contact = _fake_contact()
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [contact])
    monkeypatch.setattr(outreach, "_load_outreach_processed", lambda: set())
    monkeypatch.setattr(outreach, "generate_cold_email", lambda c, **kwargs: "Hi Jane, I'd love to chat.")
    monkeypatch.setattr(outreach, "validate_outputs", lambda *a, **k: {"passed": True, "violation_count": 0, "categories": [], "violations": []})

    saved_processed = []
    monkeypatch.setattr(outreach, "_save_outreach_processed", lambda processed: saved_processed.append(set(processed)))

    draft_calls = []
    monkeypatch.setattr(outreach, "create_draft", lambda to, subject, body, **kwargs: draft_calls.append((to, subject, body)) or True)

    stats = outreach.run_outreach()

    assert stats["drafted"] == 1
    assert stats["skipped"] == 0
    assert draft_calls[0][0] == "jane@acme.com"
    assert saved_processed[-1] == {contact["id"]}


def test_run_outreach_does_not_mark_processed_when_draft_creation_fails(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    contact = _fake_contact()
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [contact])
    monkeypatch.setattr(outreach, "_load_outreach_processed", lambda: set())
    monkeypatch.setattr(outreach, "generate_cold_email", lambda c, **kwargs: "Hi Jane, I'd love to chat.")
    monkeypatch.setattr(outreach, "validate_outputs", lambda *a, **k: {"passed": True, "violation_count": 0, "categories": [], "violations": []})
    monkeypatch.setattr(outreach, "create_draft", lambda *a, **k: False)

    saved_processed = []
    monkeypatch.setattr(outreach, "_save_outreach_processed", lambda processed: saved_processed.append(set(processed)))

    stats = outreach.run_outreach()

    assert stats["drafted"] == 0
    assert saved_processed == []


def test_run_outreach_does_not_mark_processed_when_validation_fails_twice(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    contact = _fake_contact()
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [contact])
    monkeypatch.setattr(outreach, "_load_outreach_processed", lambda: set())
    monkeypatch.setattr(outreach, "generate_cold_email", lambda c, **kwargs: "bad content")
    monkeypatch.setattr(outreach, "validate_outputs", lambda *a, **k: {"passed": False, "violation_count": 1, "categories": ["x"], "violations": [{"category": "x", "claim": "y", "reason": "z"}]})

    draft_calls = []
    monkeypatch.setattr(outreach, "create_draft", lambda *a, **k: draft_calls.append(1) or True)

    stats = outreach.run_outreach()

    assert draft_calls == []
    assert stats["drafted"] == 0
    assert len(stats["errors"]) == 1


def test_validate_email_flags_metric_not_in_canonical_resume(monkeypatch):
    monkeypatch.setattr(outreach, "_load_resume_master", lambda: "# Jane Doe\nSoftware Engineer\n")
    monkeypatch.setattr(outreach, "validate_outputs", lambda *a, **k: {"passed": True, "violation_count": 0, "categories": [], "violations": []})

    result = outreach._validate_email("I cut latency by 3x at my last job.", _fake_contact(), "model", "http://base")

    assert result["passed"] is False
    assert "metric_claim" in result["categories"]


def test_run_outreach_honors_semantic_check_config_false(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    contact = _fake_contact()
    monkeypatch.setattr(outreach, "_load_config", lambda: {"validation": {"semantic_check": False}})
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [contact])
    monkeypatch.setattr(outreach, "_load_outreach_processed", lambda: set())
    monkeypatch.setattr(outreach, "generate_cold_email", lambda c, **kwargs: "Hi Jane, I'd love to chat.")
    monkeypatch.setattr(outreach, "create_draft", lambda *a, **k: True)
    monkeypatch.setattr(outreach, "_save_outreach_processed", lambda processed: None)

    validate_calls = []

    def _fake_validate_email(body, contact, model, base_url, semantic_check=True):
        validate_calls.append(semantic_check)
        return {"passed": True, "violation_count": 0, "categories": [], "violations": []}

    monkeypatch.setattr(outreach, "_validate_email", _fake_validate_email)

    outreach.run_outreach()

    assert validate_calls == [False]


def test_add_contact_interactive_appends_well_formed_entry(monkeypatch, tmp_path):
    contacts_path = tmp_path / "contacts.yaml"
    monkeypatch.setattr(outreach, "CONTACTS_PATH", contacts_path)
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [])

    prompts = iter(["Acme Corp", "Jane Doe", "jane@acme.com"])
    monkeypatch.setattr("manual_run._prompt", lambda label, default="": next(prompts))
    monkeypatch.setattr("manual_run._prompt_multiline", lambda label: "Met at career fair")

    saved = []
    monkeypatch.setattr(outreach, "_save_contacts", lambda contacts: saved.append(contacts))

    outreach.add_contact_interactive()

    assert len(saved[-1]) == 1
    entry = saved[-1][0]
    assert entry["company"] == "Acme Corp"
    assert entry["contact_name"] == "Jane Doe"
    assert entry["contact_email"] == "jane@acme.com"
    assert entry["notes"] == "Met at career fair"
    assert entry["id"] == "acme-corp-jane-doe"


def test_add_contact_interactive_exits_when_company_missing(monkeypatch):
    prompts = iter(["", "Jane Doe", "jane@acme.com"])
    monkeypatch.setattr("manual_run._prompt", lambda label, default="": next(prompts))
    monkeypatch.setattr("manual_run._prompt_multiline", lambda label: "")

    import pytest
    with pytest.raises(SystemExit):
        outreach.add_contact_interactive()


def test_add_contact_interactive_exits_when_email_missing(monkeypatch):
    prompts = iter(["Acme Corp", "Jane Doe", ""])
    monkeypatch.setattr("manual_run._prompt", lambda label, default="": next(prompts))
    monkeypatch.setattr("manual_run._prompt_multiline", lambda label: "")

    import pytest
    with pytest.raises(SystemExit):
        outreach.add_contact_interactive()


def test_list_outreach_status_reports_pending_and_drafted(monkeypatch):
    contact_a = _fake_contact(company="Acme Corp", contact_name="Jane Doe", email="jane@acme.com")
    contact_b = _fake_contact(company="Beta Inc", contact_name="Bob Roe", email="bob@beta.com")
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [contact_a, contact_b])
    monkeypatch.setattr(outreach, "_load_outreach_processed", lambda: {contact_a["id"]})

    result = outreach.list_outreach_status()

    statuses = {r["company"]: r["status"] for r in result}
    assert statuses["Acme Corp"] == "drafted"
    assert statuses["Beta Inc"] == "pending"
