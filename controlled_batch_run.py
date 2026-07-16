from dataclasses import asdict
from datetime import date
from pathlib import Path

from pipeline import (
    _filter_listing,
    _load_archive_ids,
    _load_config,
    _load_preferences,
    _load_processed,
    _process_listing,
)
from scraper import scrape


BATCH_SIZE = 5


def main() -> None:
    config = _load_config()
    ollama_cfg = config.get("ollama", {})
    scraper_cfg = config.get("scraper", {})
    gmail_cfg = config.get("gmail", {})
    research_cfg = config.get("research", {})
    output_cfg = config.get("output", {})

    fetch_descriptions = output_cfg.get("fetch_job_descriptions", True)
    research_enabled = research_cfg.get("enabled", True)
    research_timeout = research_cfg.get("timeout_seconds", 30)

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
        "blocked_validation": 0,
        "processed": 0,
        "errors": [],
        "listings": [],
    }

    processed = _load_processed(processed_path)
    archive_ids = _load_archive_ids()
    preferences_text = _load_preferences()

    repo = scraper_cfg.get("repo", "")
    branch = scraper_cfg.get("branch", "dev")
    all_listings = scrape(repo, branch)
    stats["found"] = len(all_listings)

    selected = []
    for listing in all_listings:
        if listing.id in processed or listing.id in archive_ids:
            continue
        passes, _ = _filter_listing(listing.role, listing.company, preferences_text)
        if not passes:
            continue
        selected.append(listing)
        if len(selected) >= BATCH_SIZE:
            break

    print(f"[controlled] Found {len(all_listings)} listings total; selected {len(selected)} for execution")
    if not selected:
        print("[controlled] No eligible listings available for this batch")
        return

    common_args = dict(
        processed=processed,
        processed_path=processed_path,
        ollama_cfg=ollama_cfg,
        gmail_cfg=gmail_cfg,
        research_enabled=research_enabled,
        research_timeout=research_timeout,
        fetch_descriptions=fetch_descriptions,
        dry_run=False,
        stats=stats,
        output_dir=output_dir,
        archive_ids=archive_ids,
    )

    for listing in selected:
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

    print("\n[controlled] Batch summary")
    print(
        f"processed={stats['processed']} "
        f"blocked_validation={stats['blocked_validation']} "
        f"errors={len(stats['errors'])}"
    )
    for item in stats["listings"]:
        status = item.get("status", "")
        company = item.get("company", "")
        role = item.get("role", "")
        validation = item.get("validation", {})
        print(
            f"- {company} | {role} | status={status} "
            f"| violations={validation.get('violation_count', 0)} "
            f"| retry={validation.get('retry_used', False)}"
        )


if __name__ == "__main__":
    main()
