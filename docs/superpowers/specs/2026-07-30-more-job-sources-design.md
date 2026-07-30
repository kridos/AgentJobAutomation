# More Job Sources — Design Spec

## Context

`pipeline.py` currently pulls listings from three sources: SimplifyJobs
Summer Internships and New-Grad-Positions (both scraped via `scraper.py`'s
HTML `<tr><td>`-table parser, `scraper.py:67-117`), an optional crawl4ai
path (LinkedIn/Glassdoor, disabled by default via `config.yaml`'s
`crawl4ai.enabled`), and Gmail recruiter emails. This is the next item on
the roadmap set in `docs/superpowers/specs/2026-07-29-automator-cli-design.md`.

Research during brainstorming (live `gh api`/`gh search repos` calls,
verified against the actual repo content) found `vanshb03/Summer2027-Internships`
(8.4k stars, updated daily) as the best next addition: same 5-column
layout as SimplifyJobs (Company / Role / Location / Application-Link /
Date Posted), same `↳`-for-repeated-company and `🔒`-for-closed
conventions — but the README uses markdown pipe-tables
(`| Company | Role | ... |`) rather than HTML `<tr><td>` rows, so the
existing parser doesn't match it. Verified live: the repo's README
contains exactly one markdown table, consistently 5 columns across all 149
rows, so there's no risk of a differently-shaped embedded table producing
garbage rows.

Two other candidates (`speedyapply/2027-SWE-College-Jobs` and
`speedyapply/2027-AI-College-Jobs`) were found but use a different column
layout (adds a Salary column, reorders fields) — explicitly deferred to a
follow-up per the scope decision below.

## Goal

Add `vanshb03/Summer2027-Internships` as a fourth listings source, reusing
the existing scrape/filter/dedup/process pipeline, with same-run
duplicate-application protection against the heavily-overlapping
SimplifyJobs source.

## Non-goals

- Not adding `speedyapply/2027-SWE-College-Jobs` or
  `speedyapply/2027-AI-College-Jobs` in this pass — their different
  column layout needs a more flexible column-mapping parser, deferred as
  a follow-up.
- Not building general fuzzy/cross-source dedup infrastructure — the
  same-run company-name dedup added here is scoped specifically to the
  SimplifyJobs↔vanshb03 overlap risk, not a reusable dedup framework.
- Not adding a config toggle to disable this source — it's treated as a
  first-class source at the same reliability tier as SimplifyJobs (a
  maintained, high-star, daily-updated GitHub list), not an
  experimental/fragile one like crawl4ai.

## Architecture

`scraper.py` gains a second parser for markdown pipe-table READMEs,
sharing its per-row cell-extraction logic with the existing HTML-table
parser via one factored-out helper — only the row-splitting front end
differs between the two formats. `pipeline.py` gains a third scrape
source block, positioned after the two existing SimplifyJobs blocks and
before the optional crawl4ai block, with a same-run dedup check against
company names already collected from SimplifyJobs.

## Components

**`scraper.py`:**

```python
def _listing_from_cells(cells: list[str], row_raw: str, last_company: str) -> tuple["Listing | None", str]:
    """Build a Listing from one table row's cells (HTML- or markdown-pipe-sourced).
    Returns (listing_or_none, updated_last_company). Shared by both parsers below."""
```
Extracted from `parse_listings`'s existing body (company/role/location/link/date
extraction, emoji-prefix stripping, `↳`-continuation handling, `🔒`-closed skip,
the `len(cells) < 4` guard). `parse_listings` is refactored to call this helper
per row instead of inlining the logic — behavior is unchanged.

```python
def _parse_markdown_table_rows(readme: str) -> list[list[str]]:
    """Return cell-lists for every markdown pipe-table data row, skipping the
    header row and the '---' separator row."""

def parse_markdown_table_listings(readme: str) -> list[Listing]:
    """Parse markdown pipe-table rows (vanshb03's README format) into Listings,
    via _parse_markdown_table_rows + _listing_from_cells."""

def _resolve_vanshb03_repo() -> str:
    """Try Summer2027-Internships first; fall back to Summer2026-Internships.
    Mirrors _resolve_repo()'s existing year-fallback pattern."""

def scrape_vanshb03(branch: str = "dev") -> list[Listing]:
    """Scrape vanshb03/Summer2027(or 2026)-Internships. Non-fatal: returns []
    and lets the caller catch subprocess.CalledProcessError, matching
    scrape_newgrad's existing error-handling contract."""
```

**`pipeline.py`:**

```python
def _normalize_company(name: str) -> str:
    """Lowercase, collapse whitespace — for same-run duplicate-company detection."""
    return re.sub(r"\s+", " ", name.strip().lower())
```

A new "Source 1C" block, structurally identical to the existing
SimplifyJobs/New-Grad blocks (scrape → catch errors non-fatally → loop →
`processed`-id dedup → preference filter → `_process_listing(...,
source="vanshb03")`), with one additional check inserted before the
preference filter: skip (counted as `stats["skipped_duplicate"]`) if
`_normalize_company(listing.company)` is already present in the set of
normalized company names collected from this run's SimplifyJobs +
New-Grad listings.

## Error handling

Identical to the existing SimplifyJobs/New-Grad sources: a scrape failure
(network error, `gh` CLI error, repo not found) is caught, logged to
stderr, appended to `stats["errors"]`, and the run continues with an empty
listings list for this source — never fatal to the overall pipeline run.

## Testing

`tests/test_scraper_markdown.py`:
- `parse_markdown_table_listings` parses a synthetic fixture reproducing
  the real structure: header row, separator row, a normal data row, a
  `↳`-continuation row (same company as the row above), and a `🔒`-closed
  row (must be excluded from the result).
- `_parse_markdown_table_rows` correctly skips the header and separator
  rows and returns cell-lists for data rows only.

`tests/test_pipeline_vanshb03_dedup.py`:
- Mocks `scrape`, `scrape_newgrad`, and `scrape_vanshb03` so that a
  vanshb03 listing shares a normalized company name (case/whitespace
  differences only) with an already-collected SimplifyJobs listing — the
  vanshb03 listing is skipped and `stats["skipped_duplicate"]` increments.
- A vanshb03 listing whose company does NOT appear among the
  SimplifyJobs/New-Grad listings is processed normally (dispatched to
  `_process_listing`).
