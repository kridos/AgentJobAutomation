import yc_scraper


def test_scrape_yc_directory_returns_empty_list_on_failure(monkeypatch):
    async def _raise(batches_back):
        raise RuntimeError("page failed to load")

    monkeypatch.setattr(yc_scraper, "_fetch_yc_companies_async", _raise)

    result = yc_scraper.scrape_yc_directory()

    assert result == []


def test_scrape_yc_directory_respects_limit(monkeypatch):
    fake_companies = [{"company": f"Company{i}", "website": f"company{i}.com"} for i in range(100)]

    async def _fake_fetch(batches_back):
        return fake_companies

    monkeypatch.setattr(yc_scraper, "_fetch_yc_companies_async", _fake_fetch)

    result = yc_scraper.scrape_yc_directory(limit=10)

    assert len(result) == 10


def test_scrape_yc_directory_returns_full_list_under_limit(monkeypatch):
    fake_companies = [{"company": "Acme Corp", "website": "acme.com"}]

    async def _fake_fetch(batches_back):
        return fake_companies

    monkeypatch.setattr(yc_scraper, "_fetch_yc_companies_async", _fake_fetch)

    result = yc_scraper.scrape_yc_directory(limit=50)

    assert result == fake_companies
