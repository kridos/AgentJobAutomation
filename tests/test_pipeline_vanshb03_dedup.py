import pipeline
from scraper import Listing


def _fake_listing(company: str, role: str) -> Listing:
    return Listing(
        company=company,
        role=role,
        location="Remote",
        link="https://example.com",
        date_posted="2026-01-01",
    )


def test_vanshb03_listing_skipped_when_company_already_seen_in_simplify(monkeypatch, tmp_path):
    monkeypatch.setattr("scraper.scrape", lambda repo, branch: [_fake_listing("Acme Corp", "SWE Intern")])
    monkeypatch.setattr("scraper.scrape_newgrad", lambda branch: [])
    monkeypatch.setattr("scraper.scrape_vanshb03", lambda branch: [_fake_listing("acme corp ", "Backend Intern 🇺🇸")])
    monkeypatch.setattr("gmail_reader.get_recruiter_listings", lambda **kwargs: [])
    monkeypatch.chdir(tmp_path)

    stats = pipeline.run_pipeline(dry_run=True)

    vansh_entries = [l for l in stats["listings"] if l["source"] == "vanshb03"]
    simplify_entries = [l for l in stats["listings"] if l["source"] == "simplify"]
    assert vansh_entries == []
    assert len(simplify_entries) == 1
    assert stats["skipped_duplicate"] >= 1


def test_vanshb03_listing_processed_when_company_not_in_simplify(monkeypatch, tmp_path):
    monkeypatch.setattr("scraper.scrape", lambda repo, branch: [_fake_listing("Acme Corp", "SWE Intern")])
    monkeypatch.setattr("scraper.scrape_newgrad", lambda branch: [])
    monkeypatch.setattr("scraper.scrape_vanshb03", lambda branch: [_fake_listing("Beta Inc", "ML Intern")])
    monkeypatch.setattr("gmail_reader.get_recruiter_listings", lambda **kwargs: [])
    monkeypatch.chdir(tmp_path)

    stats = pipeline.run_pipeline(dry_run=True)

    vansh_companies = [l["company"] for l in stats["listings"] if l["source"] == "vanshb03"]
    assert vansh_companies == ["Beta Inc"]
