"""
Main pipeline: scrape → filter → deduplicate → research → generate → save.
"""

import json
import re
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Optional

import yaml


CONFIG_PATH = Path(__file__).parent / "config.yaml"
CONTEXT_DIR = Path(__file__).parent / "context"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def _load_processed(processed_path: Path) -> set[str]:
    if processed_path.exists():
        with open(processed_path) as f:
            data = json.load(f)
        return set(data) if isinstance(data, list) else set(data.keys())
    return set()


def _save_processed(processed_path: Path, processed: set[str]) -> None:
    with open(processed_path, "w") as f:
        json.dump(sorted(processed), f, indent=2)


def _load_preferences() -> str:
    p = CONTEXT_DIR / "preferences.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _filter_listing(listing, preferences_text: str) -> tuple[bool, str]:
    """
    Basic filter against preferences.md.
    Returns (passes, reason_if_skipped).
    Extend this with smarter parsing as your preferences.md grows.
    """
    text = preferences_text.lower()
    role_lower = listing.role.lower()
    location_lower = listing.location.lower()

    # Parse blocked keywords from preferences
    blocked_roles = []
    for line in preferences_text.splitlines():
        m = re.match(r".*block.*role.*:(.+)", line, re.IGNORECASE)
        if m:
            blocked_roles.extend([r.strip().lower() for r in m.group(1).split(",")])

    for blocked in blocked_roles:
        if blocked and blocked in role_lower:
            return False, f"role blocked by preferences: {blocked}"

    # Check remote preference
    if "remote only" in text and "remote" not in location_lower:
        # Soft filter — don't block, just note
        pass

    return True, ""


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def run_pipeline(dry_run: bool = False) -> dict:
    config = _load_config()

    ollama_cfg = config.get("ollama", {})
    scraper_cfg = config.get("scraper", {})
    gmail_cfg = config.get("gmail", {})
    research_cfg = config.get("research", {})
    output_cfg = config.get("output", {})

    output_base = Path(output_cfg.get("base_dir", "output"))
    processed_path = Path(output_cfg.get("processed_file", "processed.json"))
    today = date.today().isoformat()
    output_dir = output_base / today
    output_dir.mkdir(parents=True, exist_ok=True)

    stats = {
        "date": today,
        "found": 0,
        "skipped_duplicate": 0,
        "skipped_filter": 0,
        "processed": 0,
        "errors": [],
        "listings": [],
    }

    # --- Step 1: Scrape ---
    print("[pipeline] Scraping listings...", flush=True)
    from scraper import scrape
    repo = scraper_cfg.get("repo", "SimplifyJobs/Summer2027-Internships")
    branch = scraper_cfg.get("branch", "dev")
    try:
        listings = scrape(repo, branch)
    except Exception as e:
        msg = f"Scraper failed: {e}"
        print(f"[pipeline] ERROR: {msg}", file=sys.stderr)
        stats["errors"].append(msg)
        _write_summary(output_dir, stats)
        return stats

    stats["found"] = len(listings)
    print(f"[pipeline] Found {len(listings)} listings", flush=True)

    # --- Step 2: Load processed set ---
    processed = _load_processed(processed_path)

    # --- Step 3: Load preferences ---
    preferences_text = _load_preferences()

    # --- Step 4: Process each new listing ---
    from gmail_reader import search_emails, format_emails_for_context
    from generator import generate
    from researcher import research

    research_enabled = research_cfg.get("enabled", True)
    research_timeout = research_cfg.get("timeout_seconds", 30)

    for listing in listings:
        listing_id = listing.id

        # Dedup check
        if listing_id in processed:
            stats["skipped_duplicate"] += 1
            continue

        # Filter check
        passes, reason = _filter_listing(listing, preferences_text)
        if not passes:
            print(f"[pipeline] Skipping {listing.company} — {reason}")
            stats["skipped_filter"] += 1
            processed.add(listing_id)
            continue

        print(f"\n[pipeline] Processing: {listing.company} — {listing.role}", flush=True)

        if dry_run:
            print(f"  [dry-run] Would generate for {listing.company}")
            stats["processed"] += 1
            processed.add(listing_id)
            stats["listings"].append({"company": listing.company, "role": listing.role, "status": "dry-run"})
            continue

        # --- Gmail search ---
        email_context = ""
        try:
            emails = search_emails(
                listing.company,
                max_results=gmail_cfg.get("max_results", 5),
                mcp_url=gmail_cfg.get("mcp_url", "https://gmailmcp.googleapis.com/mcp/v1"),
            )
            email_context = format_emails_for_context(emails)
        except Exception as e:
            print(f"[pipeline] Gmail search failed: {e}", file=sys.stderr)

        # --- Web research (optional, non-fatal) ---
        research_context = ""
        if research_enabled:
            try:
                research_context = research(listing.company, listing.role, research_timeout)
            except Exception as e:
                print(f"[pipeline] Research failed (non-fatal): {e}", file=sys.stderr)

        # --- Generate ---
        try:
            resume_md, cover_md = generate(
                asdict(listing),
                email_context=email_context,
                research_context=research_context,
                model=ollama_cfg.get("model", "qwen2.5"),
                base_url=ollama_cfg.get("base_url", "http://localhost:11434"),
                temperature=ollama_cfg.get("temperature", 0.7),
                max_tokens=ollama_cfg.get("max_tokens", 4096),
            )
        except Exception as e:
            msg = f"Generation failed for {listing.company}: {e}"
            print(f"[pipeline] ERROR: {msg}", file=sys.stderr)
            stats["errors"].append(msg)
            continue

        # --- Save outputs ---
        company_slug = _slugify(listing.company)
        company_dir = output_dir / company_slug
        company_dir.mkdir(parents=True, exist_ok=True)

        (company_dir / "resume.md").write_text(resume_md, encoding="utf-8")
        (company_dir / "cover_letter.md").write_text(cover_md, encoding="utf-8")
        (company_dir / "listing.json").write_text(
            json.dumps(asdict(listing), indent=2), encoding="utf-8"
        )

        print(f"[pipeline] Saved to {company_dir}/", flush=True)
        stats["processed"] += 1
        stats["listings"].append({
            "company": listing.company,
            "role": listing.role,
            "location": listing.location,
            "link": listing.link,
            "output_dir": str(company_dir),
            "status": "processed",
        })

        # Mark processed immediately after successful save
        processed.add(listing_id)
        _save_processed(processed_path, processed)

    # Final save of processed set
    _save_processed(processed_path, processed)

    # --- Write summary ---
    _write_summary(output_dir, stats)
    return stats


def _write_summary(output_dir: Path, stats: dict) -> None:
    lines = [
        f"# Pipeline Run Summary — {stats['date']}",
        "",
        f"- **Listings found:** {stats['found']}",
        f"- **Duplicates skipped:** {stats['skipped_duplicate']}",
        f"- **Filtered out:** {stats['skipped_filter']}",
        f"- **Processed:** {stats['processed']}",
        f"- **Errors:** {len(stats['errors'])}",
        "",
    ]

    if stats["listings"]:
        lines.append("## Processed Listings\n")
        for item in stats["listings"]:
            status = item.get("status", "processed")
            lines.append(f"- **{item['company']}** — {item.get('role', '')} [{status}]")
            if item.get("link"):
                lines.append(f"  - Link: {item['link']}")
            if item.get("output_dir"):
                lines.append(f"  - Output: `{item['output_dir']}`")
        lines.append("")

    if stats["errors"]:
        lines.append("## Errors\n")
        for err in stats["errors"]:
            lines.append(f"- {err}")

    summary_path = output_dir / "summary.md"
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[pipeline] Summary written to {summary_path}", flush=True)
