"""
Run a larger batch of 25+ listings to test pipeline at scale.
"""
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


BATCH_SIZE = 25  # Larger batch for scale testing


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

    print(f"[larger_batch] Found {len(all_listings)} listings total; selected {len(selected)} for execution")
    if not selected:
        print("[larger_batch] No eligible listings available for this batch")
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

    for i, listing in enumerate(selected, 1):
        role_safe = listing.role.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
        company_safe = listing.company.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
        print(f"\n[{i}/{len(selected)}] Processing: {company_safe} | {role_safe}")
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

    print("\n" + "="*80)
    print("[larger_batch] Batch summary")
    print("="*80)
    print(
        f"processed={stats['processed']} "
        f"blocked_validation={stats['blocked_validation']} "
        f"errors={len(stats['errors'])}"
    )

    violation_counts = {}
    for item in stats["listings"]:
        status = item.get("status", "")
        company = item.get("company", "").encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
        role = item.get("role", "").encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
        validation = item.get("validation", {})
        violations = validation.get("violation_count", 0)
        retry_used = validation.get("retry_used", False)
        
        if violations not in violation_counts:
            violation_counts[violations] = 0
        violation_counts[violations] += 1
        
        print(
            f"- {company:30s} | {role:40s} | violations={violations} | retry={retry_used}"
        )

    print("\n[larger_batch] Violation distribution:")
    for count in sorted(violation_counts.keys()):
        freq = violation_counts[count]
        print(f"  {count} violations: {freq} listings")


if __name__ == "__main__":
    main()
