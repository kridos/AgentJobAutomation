import scraper

MARKDOWN_README_FIXTURE = """Some intro text.

| Company | Role | Location | Application/Link | Date Posted |
| ------- | ---- | -------- | ---------------- | ----------- |
| Acme Corp | Software Engineer Intern | Remote | <a href="https://acme.com/apply">Apply</a> | Jul 27 |
| ↳ | Backend Intern | Remote | <a href="https://acme.com/apply2">Apply</a> | Jul 28 |
| Locked Co | Data Intern 🔒 | NYC | <a href="https://locked.com/apply">Apply</a> | Jul 20 |
| Beta Inc | ML Intern | SF, CA | <a href="https://beta.com/apply">Apply</a> | Jul 29 |

More text after table.
"""


def test_parse_markdown_table_listings_extracts_normal_row():
    listings = scraper.parse_markdown_table_listings(MARKDOWN_README_FIXTURE)
    acme = [l for l in listings if l.company == "Acme Corp" and l.role == "Software Engineer Intern"]
    assert len(acme) == 1
    assert acme[0].location == "Remote"
    assert acme[0].link == "https://acme.com/apply"
    assert acme[0].date_posted == "Jul 27"


def test_parse_markdown_table_listings_handles_continuation_row():
    listings = scraper.parse_markdown_table_listings(MARKDOWN_README_FIXTURE)
    backend = [l for l in listings if l.role == "Backend Intern"]
    assert len(backend) == 1
    assert backend[0].company == "Acme Corp"


def test_parse_markdown_table_listings_skips_locked_row():
    listings = scraper.parse_markdown_table_listings(MARKDOWN_README_FIXTURE)
    companies = [l.company for l in listings]
    assert "Locked Co" not in companies


def test_parse_markdown_table_listings_returns_all_open_rows():
    listings = scraper.parse_markdown_table_listings(MARKDOWN_README_FIXTURE)
    assert len(listings) == 3


def test_parse_markdown_table_rows_skips_header_and_separator():
    rows = scraper._parse_markdown_table_rows(MARKDOWN_README_FIXTURE)
    assert len(rows) == 4
    assert rows[0][0] == "Acme Corp"


def test_scrape_vanshb03_returns_empty_list_when_repo_not_found(monkeypatch):
    import subprocess

    def _fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "gh")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    result = scraper.scrape_vanshb03()

    assert result == []
