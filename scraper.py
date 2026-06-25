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
        text=True,
        check=True,
    )
    return result.stdout


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


def parse_listings(readme: str) -> list[Listing]:
    """Parse HTML <tr><td> rows from the SimplifyJobs README."""
    listings = []

    # Extract all <tr> blocks
    rows = re.findall(r"<tr>(.*?)</tr>", readme, re.DOTALL | re.IGNORECASE)

    for row in rows:
        # Extract <td> cells
        cells = re.findall(r"<td>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        if len(cells) < 4:
            continue

        company_cell = cells[0]
        role_cell = cells[1]
        location_cell = cells[2]
        link_cell = cells[3]
        date_cell = cells[4] if len(cells) > 4 else ""

        # Skip closed listings (🔒 appears in the row)
        if "🔒" in row:
            continue

        company = _strip_html(company_cell)
        # Remove emoji prefixes like 🔥
        company = re.sub(r"^[\U0001F300-\U0001FFFF\s]+", "", company).strip()

        role = _strip_html(role_cell)
        location = _strip_html(location_cell)
        link = _extract_apply_link(link_cell)
        date = _strip_html(date_cell)

        if not company or not role:
            continue

        listings.append(Listing(
            company=company,
            role=role,
            location=location,
            link=link,
            date_posted=date,
        ))

    return listings


def scrape(repo: str = "SimplifyJobs/Summer2026-Internships", branch: str = "dev") -> list[Listing]:
    readme = _fetch_readme_raw(repo, branch)
    return parse_listings(readme)


if __name__ == "__main__":
    import sys
    repo = "SimplifyJobs/Summer2026-Internships"
    print(f"Fetching listings from {repo}...", flush=True)
    try:
        listings = scrape(repo)
        print(f"Found {len(listings)} listings\n")
        for l in listings[:10]:
            print(json.dumps(asdict(l), indent=2))
        if len(listings) > 10:
            print(f"... and {len(listings) - 10} more")
    except subprocess.CalledProcessError as e:
        print(f"gh CLI error: {e.stderr}", file=sys.stderr)
        sys.exit(1)
