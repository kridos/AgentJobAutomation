"""
Debug script: shows exact violations for a single named company/role.
Usage: python debug_violations.py "Later" "Software Development Co-op"
       python debug_violations.py "Palo Alto Networks" "Software Engineer Intern"
"""
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from pipeline import (
    _filter_listing,
    _load_archive_ids,
    _load_config,
    _load_preferences,
    _load_processed,
)
from scraper import scrape
from job_fetcher import fetch_job_description
from generator import generate, _load_context_files
from factual_validator import validate_outputs


def main():
    target_company = sys.argv[1] if len(sys.argv) > 1 else ""
    target_role    = sys.argv[2] if len(sys.argv) > 2 else ""

    config = _load_config()
    ollama_cfg  = config.get("ollama", {})
    scraper_cfg = config.get("scraper", {})
    output_cfg  = config.get("output", {})

    processed  = _load_processed(Path(output_cfg.get("processed_file", "processed.json")))
    archive_ids = _load_archive_ids()
    prefs      = _load_preferences()

    repo   = scraper_cfg.get("repo", "")
    branch = scraper_cfg.get("branch", "dev")

    listing = None
    for item in scrape(repo, branch):
        if item.id in processed or item.id in archive_ids:
            continue
        if target_company and target_company.lower() not in item.company.lower():
            continue
        if target_role and target_role.lower() not in item.role.lower():
            continue
        passes, _ = _filter_listing(item.role, item.company, prefs)
        if passes:
            listing = item
            break

    if not listing:
        print(f"No eligible listing found matching '{target_company}' / '{target_role}'")
        return

    print(f"\nDebugging: {listing.company} — {listing.role}")
    print(f"Link: {listing.link}\n")

    job_description = fetch_job_description(listing.link) if listing.link else ""
    print(f"Job description: {len(job_description)} chars\n")

    resume_md, cover_md = generate(
        asdict(listing),
        job_description=job_description,
        model=ollama_cfg.get("model", "qwen3:14b"),
        base_url=ollama_cfg.get("base_url", "http://localhost:11434"),
        temperature=ollama_cfg.get("temperature", 0.3),
        max_tokens=ollama_cfg.get("max_tokens", 4096),
    )

    result = validate_outputs(resume_md, cover_md, asdict(listing))
    print(f"Passed: {result['passed']}  Violations: {result['violation_count']}")
    for v in result.get("violations", []):
        print(f"  [{v['category']}] {v['claim']!r}: {v['reason']}")

    print("\n--- ALL SECTION HEADERS IN GENERATED RESUME ---")
    for line in resume_md.splitlines():
        if line.startswith("#"):
            print(repr(line))

    print("\n--- FULL RESUME ---")
    print(resume_md[:3000])


if __name__ == "__main__":
    main()
