"""
Scrapes SimplifyJobs/Summer2026-Internships README via gh CLI.
The README uses HTML <table> rows, not markdown pipes.
Run standalone: python3 scraper.py
"""

import re
import subprocess
import json
from dataclasses import dataclass, asdict


@dataclass
class Listing:
    company: str
    role: str
    location: str
    link: str
    date_posted: str
    id: str = ""

    def __post_init__(self):
        if not self.id:
            slug = re.sub(r"[^a-z0-9]+", "-", f"{self.company}-{self.role}".lower()).strip("-")
            self.id = slug


def _fetch_readme_raw(repo: str, branch: str = "dev") -> str:
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/contents/README.md",
         "-H", "Accept: application/vnd.github.raw+json"],
        capture_output=True,
        check=True,  # bytes mode — no text=True, avoids Windows cp1252 decode errors
    )
    return result.stdout.decode("utf-8", errors="replace")


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode common entities."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()


def _extract_link(cell: str) -> str:
    """Return the first href from an <a> tag, or the first https URL."""
    m = re.search(r'href="(https?://[^"]+)"', cell)
    if m:
        return m.group(1)
    m = re.search(r"(https?://\S+)", cell)
    if m:
        return m.group(1)
    return ""


def _extract_apply_link(cell: str) -> str:
    """Prefer a direct application link over Simplify tracking links."""
    # Grab all hrefs
    hrefs = re.findall(r'href="(https?://[^"]+)"', cell)
    for href in hrefs:
        # Skip Simplify's own tracking links
        if "simplify.jobs" not in href:
            return href
    return hrefs[0] if hrefs else ""


def _listing_from_cells(cells: list[str], row_raw: str, last_company: str) -> tuple["Listing | None", str]:
    """Build a Listing from one table row's cells (HTML- or markdown-pipe-sourced).
    Returns (listing_or_none, updated_last_company). Shared by both table parsers."""
    if len(cells) < 4 or "🔒" in row_raw:
        return None, last_company

    company_cell, role_cell, location_cell, link_cell = cells[0], cells[1], cells[2], cells[3]
    date_cell = cells[4] if len(cells) > 4 else ""

    company = _strip_html(company_cell)
    company = re.sub(r"^[\U0001F300-\U0001FFFF\s]+", "", company).strip()

    if company in ("↳", "") or not company:
        company = last_company
    else:
        last_company = company

    role = _strip_html(role_cell)
    location = _strip_html(location_cell)
    link = _extract_apply_link(link_cell)
    date = _strip_html(date_cell)

    if not company or not role:
        return None, last_company

    return Listing(company=company, role=role, location=location, link=link, date_posted=date), last_company


def parse_listings(readme: str) -> list[Listing]:
    """Parse HTML <tr><td> rows from the SimplifyJobs README."""
    listings = []
    last_company = ""

    rows = re.findall(r"<tr>(.*?)</tr>", readme, re.DOTALL | re.IGNORECASE)

    for row in rows:
        cells = re.findall(r"<td>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        listing, last_company = _listing_from_cells(cells, row, last_company)
        if listing:
            listings.append(listing)

    return listings


def _parse_markdown_table_rows(readme: str) -> list[list[str]]:
    """Return cell-lists for every markdown pipe-table data row, skipping the
    header row and the '---' separator row."""
    rows = []
    for line in readme.splitlines():
        line = line.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells:
            continue
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
            continue  # separator row
        if cells[0].strip().lower() == "company":
            continue  # header row
        rows.append(cells)
    return rows


def parse_markdown_table_listings(readme: str) -> list[Listing]:
    """Parse markdown pipe-table rows (vanshb03's README format) into Listings."""
    listings = []
    last_company = ""
    for cells in _parse_markdown_table_rows(readme):
        row_raw = " ".join(cells)
        listing, last_company = _listing_from_cells(cells, row_raw, last_company)
        if listing:
            listings.append(listing)
    return listings


def _resolve_repo() -> str:
    """Try 2027 repo first; fall back to 2026 if it doesn't exist yet."""
    for repo in [
        "SimplifyJobs/Summer2027-Internships",
        "SimplifyJobs/Summer2026-Internships",
    ]:
        try:
            _fetch_readme_raw(repo)
            print(f"[scraper] Using repo: {repo}")
            return repo
        except subprocess.CalledProcessError:
            continue
    raise RuntimeError("Neither Summer2027 nor Summer2026 repo found on GitHub.")


def _resolve_vanshb03_repo() -> str:
    """Try Summer2027 first; fall back to Summer2026 if it doesn't exist yet."""
    for repo in [
        "vanshb03/Summer2027-Internships",
        "vanshb03/Summer2026-Internships",
    ]:
        try:
            _fetch_readme_raw(repo)
            print(f"[scraper] Using vanshb03 repo: {repo}")
            return repo
        except subprocess.CalledProcessError:
            continue
    raise RuntimeError("Neither vanshb03 Summer2027 nor Summer2026 repo found on GitHub.")


def scrape_vanshb03(branch: str = "dev") -> list[Listing]:
    """Scrape vanshb03/Summer-Internships (markdown pipe-table format)."""
    try:
        repo = _resolve_vanshb03_repo()
        readme = _fetch_readme_raw(repo, branch)
        return parse_markdown_table_listings(readme)
    except (subprocess.CalledProcessError, RuntimeError) as e:
        print(f"[scraper] vanshb03 repo not found: {e}")
        return []


def scrape(repo: str = "", branch: str = "dev") -> list[Listing]:
    if not repo:
        repo = _resolve_repo()
    readme = _fetch_readme_raw(repo, branch)
    return parse_listings(readme)


def scrape_newgrad(branch: str = "dev") -> list[Listing]:
    """Scrape SimplifyJobs/New-Grad-Positions repo (entry-level full-time roles)."""
    try:
        readme = _fetch_readme_raw("SimplifyJobs/New-Grad-Positions", branch)
        return parse_listings(readme)
    except subprocess.CalledProcessError as e:
        print(f"[scraper] New-Grad-Positions repo not found: {e}")
        return []


if __name__ == "__main__":
    import sys
    print("Fetching listings (auto-detecting repo year)...", flush=True)
    try:
        listings = scrape()
        print(f"Found {len(listings)} listings\n")
        for l in listings[:10]:
            print(json.dumps(asdict(l), indent=2))
        if len(listings) > 10:
            print(f"... and {len(listings) - 10} more")
    except subprocess.CalledProcessError as e:
        print(f"gh CLI error: {e.stderr}", file=sys.stderr)
        sys.exit(1)
