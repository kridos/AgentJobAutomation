import outreach


def _fake_contact(company="Acme Corp", email="jane@acme.com", confirmed=True, contact_id=None):
    return {
        "id": contact_id or company.lower().replace(" ", "-"),
        "company": company,
        "contact_name": "",
        "contact_email": email,
        "notes": "",
        "confirmed": confirmed,
    }


def test_discover_contacts_skips_existing_company(monkeypatch):
    monkeypatch.setattr(outreach, "_load_config", lambda: {})
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [_fake_contact(company="Acme Corp")])
    monkeypatch.setattr(
        outreach, "_DISCOVERY_SOURCES",
        [("yc", lambda batches_back, limit: [{"company": "acme corp ", "website": "acme.com"}])],
    )

    saved = []
    monkeypatch.setattr(outreach, "_save_contacts", lambda contacts: saved.append(contacts))

    stats = outreach.discover_contacts()

    assert stats["skipped_duplicate"] == 1
    assert stats["added"] == 0


def test_discover_contacts_adds_new_company_with_verified_email(monkeypatch):
    monkeypatch.setattr(outreach, "_load_config", lambda: {})
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [])
    monkeypatch.setattr(
        outreach, "_DISCOVERY_SOURCES",
        [("yc", lambda batches_back, limit: [{"company": "Beta Inc", "website": "beta.com"}])],
    )
    monkeypatch.setattr(outreach, "guess_and_verify_email", lambda domain: ("hello@beta.com", True))

    saved = []
    monkeypatch.setattr(outreach, "_save_contacts", lambda contacts: saved.append(contacts))

    stats = outreach.discover_contacts()

    assert stats["added"] == 1
    assert saved[-1][0]["contact_email"] == "hello@beta.com"
    assert saved[-1][0]["confirmed"] is True


def test_discover_contacts_adds_new_company_with_unverified_email(monkeypatch):
    monkeypatch.setattr(outreach, "_load_config", lambda: {})
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [])
    monkeypatch.setattr(
        outreach, "_DISCOVERY_SOURCES",
        [("yc", lambda batches_back, limit: [{"company": "Gamma LLC", "website": "gamma.com"}])],
    )
    monkeypatch.setattr(outreach, "guess_and_verify_email", lambda domain: ("founders@gamma.com", False))

    saved = []
    monkeypatch.setattr(outreach, "_save_contacts", lambda contacts: saved.append(contacts))

    stats = outreach.discover_contacts()

    assert stats["added"] == 1
    assert saved[-1][0]["confirmed"] is False


def test_discover_contacts_survives_bad_entry_and_saves_good_ones(monkeypatch):
    monkeypatch.setattr(outreach, "_load_config", lambda: {})
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [])
    monkeypatch.setattr(
        outreach, "_DISCOVERY_SOURCES",
        [("yc", lambda batches_back, limit: [
            {"company": "Bad Co", "website": "bad.com"},
            {"company": "Good Co", "website": "good.com"},
        ])],
    )

    def fake_guess_and_verify(domain):
        if domain == "bad.com":
            raise RuntimeError("SMTP blew up")
        return ("hello@good.com", True)

    monkeypatch.setattr(outreach, "guess_and_verify_email", fake_guess_and_verify)

    saved = []
    monkeypatch.setattr(outreach, "_save_contacts", lambda contacts: saved.append(contacts))

    stats = outreach.discover_contacts()

    assert stats["added"] == 1
    assert saved  # _save_contacts was still called
    companies = [c["company"] for c in saved[-1]]
    assert "Good Co" in companies
    assert "Bad Co" not in companies


def test_run_outreach_skips_unconfirmed_contact(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    contact = _fake_contact(confirmed=False)
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [contact])
    monkeypatch.setattr(outreach, "_load_outreach_processed", lambda: set())

    gen_calls = []
    monkeypatch.setattr(outreach, "generate_cold_email", lambda c, **kwargs: gen_calls.append(1) or "body")
    draft_calls = []
    monkeypatch.setattr(outreach, "create_draft", lambda *a, **k: draft_calls.append(1) or True)

    stats = outreach.run_outreach()

    assert gen_calls == []
    assert draft_calls == []
    assert stats["unconfirmed_skipped"] == 1
    assert stats["drafted"] == 0


def test_confirm_contact_manual_updates_existing_contact(monkeypatch):
    contact = _fake_contact(email="", confirmed=False, contact_id="acme-corp")
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [contact])

    saved = []
    monkeypatch.setattr(outreach, "_save_contacts", lambda contacts: saved.append(contacts))

    result = outreach.confirm_contact_manual("acme-corp", "real@acme.com")

    assert result is True
    assert saved[-1][0]["contact_email"] == "real@acme.com"
    assert saved[-1][0]["confirmed"] is True


def test_confirm_contact_manual_returns_false_for_unknown_id(monkeypatch):
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [])

    saved = []
    monkeypatch.setattr(outreach, "_save_contacts", lambda contacts: saved.append(contacts))

    result = outreach.confirm_contact_manual("nonexistent", "x@x.com")

    assert result is False
    assert saved == []


def test_list_outreach_status_treats_missing_confirmed_key_as_true(monkeypatch):
    contact = {"id": "old-contact", "company": "Old Co", "contact_email": "old@old.com"}
    monkeypatch.setattr(outreach, "_load_contacts", lambda: [contact])
    monkeypatch.setattr(outreach, "_load_outreach_processed", lambda: set())

    result = outreach.list_outreach_status()

    assert result[0]["confirmed"] is True
