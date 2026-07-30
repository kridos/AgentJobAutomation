"""
Scrapes Y Combinator's public company directory for startup-discovery
cold-outreach targets. The directory is JS-rendered, so this uses
playwright (mirrors job_fetcher.py's fetch_via_playwright pattern).
Run standalone: python yc_scraper.py
"""

import asyncio
import sys

# YC's directory page fetches its company data client-side from an
# Algolia index (YCCompany_production) rather than rendering it server-side.
# Each hit already carries name/slug/website/batch, so we intercept that
# XHR instead of scraping the JS-rendered DOM (see task-2-report.md).
_SEASON_ORDER = {"Winter": 0, "Spring": 1, "Summer": 2, "Fall": 3}


def _batch_sort_key(batch_name: str) -> tuple[int, int]:
    """Sorts 'Season Year' batch names chronologically (most recent last
    when sorted ascending). Unparseable/unspecified batches sort first
    (oldest) so they never get mistaken for the current batch."""
    parts = batch_name.split()
    if len(parts) == 2 and parts[0] in _SEASON_ORDER and parts[1].isdigit():
        return (int(parts[1]), _SEASON_ORDER[parts[0]])
    return (-1, -1)


async def _fetch_yc_companies_async(batches_back: int) -> list[dict]:
    """Navigates YC's company directory with playwright and extracts
    company name + website per listing, filtered to the current batch
    plus `batches_back` prior batches where the page structure allows
    reliable batch filtering (falls back to the default directory view,
    most-recent-first, if it does not — see this task's Step 1 findings).
    Returns [{"company": str, "website": str}, ...]. Raises on failure —
    the caller (scrape_yc_directory) is responsible for catching."""
    from playwright.async_api import async_playwright

    hits: list[dict] = []

    async def _on_response(response):
        if response.request.method != "POST" or "algolia" not in response.url.lower():
            return
        try:
            data = await response.json()
        except Exception:
            return
        results = data.get("results") or []
        for result in results:
            page_hits = result.get("hits") or []
            if page_hits and "name" in page_hits[0]:
                hits.extend(page_hits)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        page.on("response", _on_response)
        await page.goto(
            "https://www.ycombinator.com/companies",
            timeout=20000,
            wait_until="domcontentloaded",
        )
        await page.wait_for_timeout(4000)  # let JS render + fire its Algolia XHR
        await browser.close()

    if not hits:
        raise RuntimeError("no company data captured from YC directory (Algolia response missing)")

    batches_present = sorted(
        {h.get("batch") for h in hits if h.get("batch")},
        key=_batch_sort_key,
        reverse=True,
    )
    selected_batches = set(batches_present[: batches_back + 1])

    filtered = [h for h in hits if h.get("batch") in selected_batches and h.get("website")]
    filtered.sort(key=lambda h: h.get("launched_at") or 0, reverse=True)

    return [{"company": h["name"], "website": h["website"]} for h in filtered]


def scrape_yc_directory(batches_back: int = 2, limit: int = 50) -> list[dict]:
    """Scrapes YC's company directory via playwright, capped at `limit`
    companies. Returns [{"company": str, "website": str}]. Non-fatal:
    returns [] on any failure — network error, timeout, or unexpected
    page structure."""
    try:
        companies = asyncio.run(_fetch_yc_companies_async(batches_back))
        return companies[:limit]
    except Exception as e:
        print(f"[yc_scraper] YC directory scrape failed: {e}", file=sys.stderr)
        return []


if __name__ == "__main__":
    result = scrape_yc_directory()
    print(f"Found {len(result)} companies")
    for c in result[:10]:
        print(f"  {c['company']} — {c['website']}")
