"""
Scrapes SimplifyJobs/Summer2027-Internships README via gh CLI.
Run standalone: python scraper.py
"""

import re
import subprocess
import json
from dataclasses import dataclass, asdict
from typing import Optional


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


def _fetch_readme(repo: str, branch: str = "dev") -> str:
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/readme", "--jq", ".content"],
        capture_output=True,
        text=True,
        check=True,
    )
    import base64
    return base64.b64decode(result.stdout.strip()).decode("utf-8")


def _fetch_readme_raw(repo: str, branch: str = "dev") -> str:
    """Fetch raw README via gh CLI using raw content endpoint."""
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/contents/README.md",
         "-H", "Accept: application/vnd.github.raw+json"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _clean_cell(cell: str) -> str:
    """Strip markdown links, badges, and extra whitespace from a table cell."""
    # Remove markdown links but keep text: [text](url) -> text
    cell = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", cell)
    # Remove HTML tags
    cell = re.sub(r"<[^>]+>", "", cell)
    # Remove badge images
    cell = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", cell)
    return cell.strip()


def _extract_link(cell: str) -> str:
    """Extract the first URL from a markdown cell."""
    m = re.search(r"\[.*?\]\((https?://[^)]+)\)", cell)
    if m:
        return m.group(1)
    m = re.search(r"(https?://\S+)", cell)
    if m:
        return m.group(1)
    return ""


def parse_listings(readme: str) -> list[Listing]:
    listings = []
    in_table = False
    header_passed = False

    for line in readme.splitlines():
        line = line.strip()

        # Detect table rows (must start and end with |)
        if not line.startswith("|") or not line.endswith("|"):
            if in_table and listings:
                # Tables may be separated — keep scanning
                pass
            continue

        cells = [c.strip() for c in line.split("|")[1:-1]]

        # Skip divider rows (e.g. |---|---|)
        if all(re.match(r"^[-: ]+$", c) for c in cells if c):
            header_passed = True
            in_table = True
            continue

        # Skip header rows
        if not header_passed:
            continue

        # Need at least 4 columns: company, role, location, link/date
        if len(cells) < 4:
            continue

        # Skip closed/filled listings (often marked with ~~strikethrough~~ or 🔒)
        raw_line = line
        if "🔒" in raw_line or ("~~" in cells[0] and "~~" in cells[0]):
            continue

        company_raw = cells[0]
        role_raw = cells[1]
        location_raw = cells[2]
        link_raw = cells[3] if len(cells) > 3 else ""
        date_raw = cells[4] if len(cells) > 4 else ""

        # Skip empty company rows (continuation rows)
        company = _clean_cell(company_raw)
        if not company or company in ("↳", ""):
            # Use previous company if this is a sub-listing
            if listings:
                company = listings[-1].company
            else:
                continue

        role = _clean_cell(role_raw)
        location = _clean_cell(location_raw)
        link = _extract_link(link_raw) or _extract_link(role_raw)
        date = _clean_cell(date_raw)

        if not role:
            continue

        listings.append(Listing(
            company=company,
            role=role,
            location=location,
            link=link,
            date_posted=date,
        ))

    return listings


def scrape(repo: str = "SimplifyJobs/Summer2027-Internships", branch: str = "dev") -> list[Listing]:
    readme = _fetch_readme_raw(repo, branch)
    return parse_listings(readme)


if __name__ == "__main__":
    import sys
    repo = "SimplifyJobs/Summer2027-Internships"
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
