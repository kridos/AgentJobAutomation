"""
Fetches the full job description from a posting URL.
Tries httpx first (fast), falls back to playwright (JS-heavy sites).
Always non-fatal — returns empty string on any failure.
Run standalone: python3 job_fetcher.py "https://jobs.example.com/123"
"""

import re
import sys
import httpx


_STRIP_TAGS = re.compile(r"<[^>]+>")
_COLLAPSE_WS = re.compile(r"\s{2,}")

_BOILERPLATE = re.compile(
    r"(equal opportunity|cookie policy|privacy policy|javascript|enable js"
    r"|sign in|log in|create account|©\s*\d{4}|all rights reserved"
    r"|powered by|we use cookies)",
    re.IGNORECASE,
)

_JOB_SECTION_HINTS = re.compile(
    r"(responsibilities|qualifications|requirements|what you.ll do"
    r"|about the role|about this role|job description|who you are"
    r"|what we.re looking for|minimum qualifications|preferred qualifications)",
    re.IGNORECASE,
)


def _clean_html(html: str) -> str:
    text = _STRIP_TAGS.sub(" ", html)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">") \
               .replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"')
    text = _COLLAPSE_WS.sub("\n", text)
    return text.strip()


def _extract_relevant_section(text: str, max_chars: int = 4000) -> str:
    """
    Try to find the job-description section of a page.
    Falls back to the first max_chars characters if no section found.
    """
    lines = text.splitlines()
    start = 0
    for i, line in enumerate(lines):
        if _JOB_SECTION_HINTS.search(line):
            start = max(0, i - 2)
            break

    relevant = "\n".join(lines[start:])

    # Filter obvious boilerplate lines
    filtered = [l for l in relevant.splitlines() if not _BOILERPLATE.search(l) and len(l.strip()) > 20]
    result = "\n".join(filtered)
    return result[:max_chars]


def fetch_via_httpx(url: str, timeout: float = 10.0) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    resp = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    return _clean_html(resp.text)


async def fetch_via_playwright(url: str, timeout_ms: int = 15000) -> str:
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)  # let JS render
        content = await page.evaluate("() => document.body.innerText")
        await browser.close()
        return content or ""


def fetch_job_description(url: str, timeout: float = 12.0) -> str:
    """
    Fetch and return a cleaned job description from the posting URL.
    Returns empty string on failure — never raises.
    """
    if not url or not url.startswith("http"):
        return ""

    # Try httpx first
    try:
        raw = fetch_via_httpx(url, timeout=timeout)
        if raw and len(raw) > 200:
            return _extract_relevant_section(raw)
    except Exception as e:
        print(f"[job_fetcher] httpx failed ({url[:60]}...): {e}", file=sys.stderr)

    # Playwright fallback
    try:
        import asyncio
        raw = asyncio.run(fetch_via_playwright(url, timeout_ms=int(timeout * 1000)))
        if raw:
            return _extract_relevant_section(raw)
    except Exception as e:
        print(f"[job_fetcher] playwright failed ({url[:60]}...): {e}", file=sys.stderr)

    return ""


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else ""
    if not url:
        print("Usage: python3 job_fetcher.py <url>")
        sys.exit(1)
    print(f"Fetching: {url}\n")
    desc = fetch_job_description(url)
    print(desc if desc else "No description extracted.")
