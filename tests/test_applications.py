import json
from pathlib import Path

import applications


def _seed_app(date="2026-07-01", source="simplify", company="Acme Corp",
              role="SWE Intern", company_slug="acme_corp", role_slug="swe_intern",
              score=85, write_score=True):
    app_dir = Path("output") / date / source / company_slug / role_slug
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "listing.json").write_text(
        json.dumps({"company": company, "role": role}), encoding="utf-8"
    )
    if write_score:
        (app_dir / "quality_score.json").write_text(
            json.dumps({"overall": score}), encoding="utf-8"
        )
    (app_dir / "resume.md").write_text("# Resume\n- Did a thing\n", encoding="utf-8")
    (app_dir / "cover_letter.md").write_text("Dear team,\n\nHello.\n", encoding="utf-8")
    app_id = f"{date}/{source}/{company_slug}/{role_slug}"
    return app_dir, app_id


def test_list_applications_defaults_to_pending_and_reads_score(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_app()

    apps = applications.list_applications()

    assert len(apps) == 1
    app = apps[0]
    assert app["company"] == "Acme Corp"
    assert app["role"] == "SWE Intern"
    assert app["source"] == "simplify"
    assert app["date"] == "2026-07-01"
    assert app["score"] == 85
    assert app["status"] == "pending"
    assert app["has_prep"] is False


def test_list_applications_skips_malformed_listing_but_keeps_others(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    bad_dir, _ = _seed_app(company="Bad Co", company_slug="bad_co", role_slug="intern")
    (bad_dir / "listing.json").write_text("{not json", encoding="utf-8")
    _seed_app(company="Good Co", company_slug="good_co", role_slug="intern")

    apps = applications.list_applications()

    assert len(apps) == 1
    assert apps[0]["company"] == "Good Co"
    assert "malformed" in capsys.readouterr().err


def test_get_application_returns_none_for_unknown_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_app()

    assert applications.get_application("nope/nope/nope/nope") is None


def test_get_application_reads_file_contents_and_blank_job_description(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _, app_id = _seed_app()

    app = applications.get_application(app_id)

    assert app["resume_md"] == "# Resume\n- Did a thing\n"
    assert app["cover_md"] == "Dear team,\n\nHello.\n"
    assert app["job_description"] == ""


def test_set_application_status_round_trips(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _, app_id = _seed_app()

    ok = applications.set_application_status(app_id, "applied")

    assert ok is True
    apps = {a["id"]: a for a in applications.list_applications()}
    assert apps[app_id]["status"] == "applied"


def test_set_application_status_rejects_invalid_status_and_unknown_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _, app_id = _seed_app()

    assert applications.set_application_status(app_id, "bogus") is False
    assert applications.set_application_status("nope/nope/nope/nope", "applied") is False
