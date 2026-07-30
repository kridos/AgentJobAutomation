# More Job Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `vanshb03/Summer2027-Internships` (a markdown-pipe-table-formatted GitHub internship list) as a fourth pipeline source, with same-run duplicate-application protection against the overlapping SimplifyJobs source.

**Architecture:** `scraper.py` gains a markdown-pipe-table parser that shares its per-row cell-extraction logic with the existing HTML-table parser via one factored-out helper. `pipeline.py` gains a third scrape source block, positioned after the two SimplifyJobs blocks, with a same-run dedup check against SimplifyJobs company names.

**Tech Stack:** Python 3.10+, stdlib `re`/`subprocess` — no new dependencies.

## Global Constraints

- No new config flag — this source is on by default, same reliability tier as SimplifyJobs, not opt-in like crawl4ai.
- Scrape failures (network error, `gh` CLI error, repo not found) must be non-fatal: caught, logged to stderr, appended to `stats["errors"]`, and the run continues with an empty list for that source.
- `parse_listings`'s existing behavior must be unchanged after the refactor — it's covered indirectly by the full pipeline test suite (44 existing tests) rather than dedicated scraper tests, since none exist yet.
- The same-run dedup check compares normalized (lowercased, whitespace-collapsed) company names only — it does not attempt to match on role text.

---

### Task 1: Markdown pipe-table parser in scraper.py

**Files:**
- Modify: `scraper.py` (refactor `parse_listings`, add `_listing_from_cells`, `_parse_markdown_table_rows`, `parse_markdown_table_listings`, `_resolve_vanshb03_repo`, `scrape_vanshb03`)
- Test: `tests/test_scraper_markdown.py`

**Interfaces:**
- Consumes: `Listing` dataclass (existing, `scraper.py:13-25`, unchanged), `_fetch_readme_raw(repo: str, branch: str = "dev") -> str` (existing, unchanged), `_strip_html(text: str) -> str` (existing, unchanged), `_extract_apply_link(cell: str) -> str` (existing, unchanged).
- Produces: `scraper.parse_markdown_table_listings(readme: str) -> list[Listing]` and `scraper.scrape_vanshb03(branch: str = "dev") -> list[Listing]` — both consumed by Task 2's `pipeline.py` changes. Also produces `scraper._listing_from_cells(cells: list[str], row_raw: str, last_company: str) -> tuple[Listing | None, str]` and `scraper._parse_markdown_table_rows(readme: str) -> list[list[str]]`, used only internally by this task.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scraper_markdown.py`:

```python
import scraper

MARKDOWN_README_FIXTURE = """Some intro text.

| Company | Role | Location | Application/Link | Date Posted |
| ------- | ---- | -------- | ---------------- | ----------- |
| Acme Corp | Software Engineer Intern | Remote | <a href="https://acme.com/apply">Apply</a> | Jul 27 |
| ↳ | Backend Intern | Remote | <a href="https://acme.com/apply2">Apply</a> | Jul 28 |
| Locked Co | Data Intern \U0001F512 | NYC | <a href="https://locked.com/apply">Apply</a> | Jul 20 |
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scraper_markdown.py -v`
Expected: FAIL — `AttributeError: module 'scraper' has no attribute 'parse_markdown_table_listings'` (and similar for `_parse_markdown_table_rows`, `scrape_vanshb03`)

- [ ] **Step 3: Extract the shared per-row cell logic**

In `scraper.py`, immediately after `_extract_apply_link` (currently ending at line 64) and before `parse_listings`, add:

```python
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
```

- [ ] **Step 4: Refactor `parse_listings` to use the shared helper**

In `scraper.py`, replace the entire existing `parse_listings` function body with:

```python
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
```

This preserves identical behavior to the original — every branch (length guard, 🔒 skip, emoji stripping, `↳` continuation, empty-company/role skip) now lives in `_listing_from_cells` instead of being inlined here.

- [ ] **Step 5: Add the markdown pipe-table parser**

In `scraper.py`, immediately after `parse_listings` and before `_resolve_repo`, add:

```python
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
```

- [ ] **Step 6: Add the vanshb03 repo resolver and scrape function**

In `scraper.py`, immediately after `_resolve_repo` (currently ending at line 132) and before `scrape`, add:

```python
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
    except subprocess.CalledProcessError as e:
        print(f"[scraper] vanshb03 repo not found: {e}")
        return []
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_scraper_markdown.py -v`
Expected: 6 tests PASS

- [ ] **Step 8: Run the full test suite as a regression check**

Run: `pytest tests/ -v`
Expected: All existing tests still PASS — `parse_listings`'s refactor must not change its observable behavior for any existing caller.

- [ ] **Step 9: Commit**

```bash
git add scraper.py tests/test_scraper_markdown.py
git commit -m "feat: add markdown pipe-table parser and vanshb03 scraper"
```

---

### Task 2: Wire vanshb03 into pipeline.py with same-run dedup

**Files:**
- Modify: `pipeline.py:104-106` (add `_normalize_company` after `_slugify`)
- Modify: `pipeline.py:513-515` (insert new Source 1C block between the New-Grad block and the crawl4ai block)
- Test: `tests/test_pipeline_vanshb03_dedup.py`

**Interfaces:**
- Consumes: `scraper.scrape_vanshb03(branch: str = "dev") -> list[Listing]` (from Task 1). `_process_listing(...)`, `_filter_listing(...)`, `_limit_hit()`, `common_args`, `listings`, `newgrad_listings`, `processed`, `preferences_text`, `stats` — all existing names already in scope inside `run_pipeline` at the point this block is inserted.
- Produces: `_normalize_company(name: str) -> str`, used only within this task's new block.

- [ ] **Step 1: Write the failing test**

Create `tests/test_pipeline_vanshb03_dedup.py`. This follows the existing
convention in `tests/test_pipeline_limit.py`: run with `dry_run=True` and
`monkeypatch.chdir(tmp_path)`, and let the real `_process_listing` /
`_filter_listing` execute — `dry_run=True` makes `_process_listing` record
a `{"company", "role", "source", "status": "dry-run"}` entry into
`stats["listings"]` and return immediately, without any LLM/Gmail/research
calls, so no further mocking is needed.

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline_vanshb03_dedup.py -v`
Expected: FAIL on both tests — `pipeline.py` doesn't call `scrape_vanshb03` yet, so no `"source": "vanshb03"` entries are ever added to `stats["listings"]`. The first test fails on `assert stats["skipped_duplicate"] >= 1` (nothing from this source runs, so nothing gets deduped). The second test fails on `assert vansh_companies == ["Beta Inc"]` (the list is empty).

- [ ] **Step 3: Add `_normalize_company`**

In `pipeline.py`, immediately after `_slugify` (currently ending at line 105) and before `_process_listing`, add:

```python
def _normalize_company(name: str) -> str:
    """Lowercase, collapse whitespace — for same-run duplicate-company detection."""
    return re.sub(r"\s+", " ", name.strip().lower())
```

- [ ] **Step 4: Insert the Source 1C block**

In `pipeline.py`, find the boundary between the end of the New-Grad loop and the start of the crawl4ai section (currently):

```python
        _process_listing(
            listing_id=listing.id,
            company=listing.company,
            role=listing.role,
            location=listing.location,
            link=listing.link,
            date_posted=listing.date_posted,
            listing_dict=asdict(listing),
            source="simplify",
            **common_args,
        )

    # ── Source 2: crawl4ai job boards ────────────────────────────────────────
```

(this exact `_process_listing(...)` call closes the New-Grad loop — it's the second occurrence of this block in the file, immediately followed by the `# ── Source 2` comment)

Replace it with:

```python
        _process_listing(
            listing_id=listing.id,
            company=listing.company,
            role=listing.role,
            location=listing.location,
            link=listing.link,
            date_posted=listing.date_posted,
            listing_dict=asdict(listing),
            source="simplify",
            **common_args,
        )

    # ── Source 1C: vanshb03 Summer Internships ─────────────────────────────
    if _limit_hit():
        vansh_listings = []
    else:
        print("[pipeline] Scraping vanshb03 Summer Internships...", flush=True)
        try:
            from scraper import scrape_vanshb03
            vansh_listings = scrape_vanshb03(branch)
            stats["found"] += len(vansh_listings)
            print(f"[pipeline] Found {len(vansh_listings)} vanshb03 listings", flush=True)
        except Exception as e:
            msg = f"vanshb03 scraper failed: {e}"
            print(f"[pipeline] ERROR: {msg}", file=sys.stderr)
            stats["errors"].append(msg)
            vansh_listings = []

    simplify_companies_seen = {_normalize_company(l.company) for l in listings + newgrad_listings}

    for listing in vansh_listings:
        if _limit_hit():
            break
        if listing.id in processed:
            stats["skipped_duplicate"] += 1
            continue
        if _normalize_company(listing.company) in simplify_companies_seen:
            stats["skipped_duplicate"] += 1
            continue
        passes, reason = _filter_listing(listing.role, listing.company, preferences_text)
        if not passes:
            print(f"[pipeline] Skipping {listing.company} — {reason}")
            stats["skipped_filter"] += 1
            continue
        _process_listing(
            listing_id=listing.id,
            company=listing.company,
            role=listing.role,
            location=listing.location,
            link=listing.link,
            date_posted=listing.date_posted,
            listing_dict=asdict(listing),
            source="vanshb03",
            **common_args,
        )

    # ── Source 2: crawl4ai job boards ────────────────────────────────────────
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_pipeline_vanshb03_dedup.py -v`
Expected: 2 tests PASS

- [ ] **Step 6: Run the full test suite as a regression check**

Run: `pytest tests/ -v`
Expected: All tests PASS. The new block only adds a new loop after the existing New-Grad loop and before the existing crawl4ai block — no existing control flow is altered, and `vansh_listings` defaults to `[]` when `_limit_hit()` is already true, matching the New-Grad block's existing pattern.

- [ ] **Step 7: Commit**

```bash
git add pipeline.py tests/test_pipeline_vanshb03_dedup.py
git commit -m "feat: wire vanshb03 into pipeline with same-run company dedup"
```

---

## Self-Review Notes

- **Spec coverage:** Shared cell-extraction helper (`_listing_from_cells`) → Task 1 Steps 3-4. Markdown pipe-table parser (`_parse_markdown_table_rows`, `parse_markdown_table_listings`) → Task 1 Step 5. Year-fallback resolver and scrape function (`_resolve_vanshb03_repo`, `scrape_vanshb03`) → Task 1 Step 6. Pipeline wiring as a third source → Task 2 Step 4. Same-run company dedup → Task 2 Steps 3-4. Error handling (non-fatal scrape failures) → Task 1 Step 6's try/except in `scrape_vanshb03` and Task 2 Step 4's try/except around the `scrape_vanshb03` call. No new config flag → confirmed no `config.yaml` changes anywhere in this plan. Testing (both test files' bullet points from the spec) → Task 1 Step 1's 6 tests, Task 2 Step 1's 2 tests.
- **Placeholder scan:** none found — every step has complete code.
- **Type consistency:** `scrape_vanshb03(branch: str = "dev") -> list[Listing]` is defined in Task 1 and consumed identically in Task 2 (both the pipeline wiring and the dedup test's monkeypatch target `scraper.scrape_vanshb03`). `_listing_from_cells`'s `tuple[Listing | None, str]` return is unpacked identically (`listing, last_company = ...`) in both `parse_listings` and `parse_markdown_table_listings`. `_normalize_company(name: str) -> str` matches its one call site's usage in Task 2 Step 4.
- **Task ordering:** Task 2 depends on Task 1's `scrape_vanshb03` existing — sequential, not parallelizable, which subagent-driven-development handles naturally (one implementer at a time, in plan order).
