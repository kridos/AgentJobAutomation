from dataclasses import asdict

import pipeline
from scraper import Listing


def _fake_listing(i: int) -> Listing:
    return Listing(
        company=f"Company{i}",
        role="Software Engineering Intern",
        location="Remote",
        link=f"https://example.com/{i}",
        date_posted="2026-01-01",
    )


def test_run_pipeline_stops_at_limit(monkeypatch, tmp_path):
    fake_listings = [_fake_listing(i) for i in range(5)]

    monkeypatch.setattr("scraper.scrape", lambda repo, branch: fake_listings)
    monkeypatch.setattr("scraper.scrape_newgrad", lambda branch: [])
    monkeypatch.setattr("scraper.scrape_vanshb03", lambda branch: [])
    monkeypatch.setattr("gmail_reader.get_recruiter_listings", lambda **kwargs: [])
    monkeypatch.chdir(tmp_path)

    stats = pipeline.run_pipeline(dry_run=True, limit=2)

    assert stats["processed"] == 2


def test_run_pipeline_limit_zero_processes_none(monkeypatch, tmp_path):
    fake_listings = [_fake_listing(i) for i in range(5)]

    monkeypatch.setattr("scraper.scrape", lambda repo, branch: fake_listings)
    monkeypatch.setattr("scraper.scrape_newgrad", lambda branch: [])
    monkeypatch.setattr("scraper.scrape_vanshb03", lambda branch: [])
    monkeypatch.setattr("gmail_reader.get_recruiter_listings", lambda **kwargs: [])
    monkeypatch.chdir(tmp_path)

    stats = pipeline.run_pipeline(dry_run=True, limit=0)

    assert stats["processed"] == 0


def test_run_pipeline_no_limit_processes_all(monkeypatch, tmp_path):
    fake_listings = [_fake_listing(i) for i in range(3)]

    monkeypatch.setattr("scraper.scrape", lambda repo, branch: fake_listings)
    monkeypatch.setattr("scraper.scrape_newgrad", lambda branch: [])
    monkeypatch.setattr("scraper.scrape_vanshb03", lambda branch: [])
    monkeypatch.setattr("gmail_reader.get_recruiter_listings", lambda **kwargs: [])
    monkeypatch.chdir(tmp_path)

    stats = pipeline.run_pipeline(dry_run=True, limit=None)

    assert stats["processed"] == 3
