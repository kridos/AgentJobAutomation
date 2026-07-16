"""
Main pipeline: scrape → filter → deduplicate → fetch description → research → generate → save.
Sources: SimplifyJobs Summer Internships, SimplifyJobs New-Grad-Positions, crawl4ai job boards (optional), and Gmail recruiter emails.
"""

import json
import re
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

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
        try:
            with open(processed_path, encoding="utf-8-sig") as f:
                data = json.load(f)
            return set(data) if isinstance(data, list) else set(data.keys())
        except (json.JSONDecodeError, ValueError):
            print("[pipeline] processed.json is malformed — starting fresh", file=sys.stderr)
    return set()


def _load_archive_ids() -> dict[str, str]:
    """
    Returns {listing_id: archive_filename} for every ID across all archive files.
    Used to warn the user when a listing was processed in a previous run.
    """
    archive_dir = Path("archive")
    id_to_file: dict[str, str] = {}
    if not archive_dir.exists():
        return id_to_file
    for archive_file in sorted(archive_dir.glob("processed_*.json")):
        try:
            ids = json.loads(archive_file.read_text(encoding="utf-8-sig"))
            for entry in ids:
                id_to_file[entry] = archive_file.name
        except Exception:
            pass
    return id_to_file


def _auto_archive(processed_path: Path) -> None:
    """Archive and clear processed.json at the end of a successful run."""
    from archive_processed import archive
    try:
        archive(clear=True)
    except Exception as e:
        print(f"[pipeline] Auto-archive failed (non-fatal): {e}", file=sys.stderr)


def _save_processed(processed_path: Path, processed: set[str]) -> None:
    with open(processed_path, "w") as f:
        json.dump(sorted(processed), f, indent=2)


def _load_preferences() -> str:
    p = CONTEXT_DIR / "preferences.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _filter_listing(role: str, company: str, preferences_text: str) -> tuple[bool, str]:
    text = preferences_text.lower()
    role_lower = role.lower()

    blocked_roles = []
    for line in preferences_text.splitlines():
        m = re.match(r".*block.*role.*:(.+)", line, re.IGNORECASE)
        if m:
            blocked_roles.extend([r.strip().lower() for r in m.group(1).split(",")])

    for blocked in blocked_roles:
        if blocked and blocked in role_lower:
            return False, f"role blocked by preferences: {blocked}"

    return True, ""


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _process_listing(
    *,
    listing_id: str,
    config: dict = {},  # noqa: B006
    company: str,
    role: str,
    location: str,
    link: str,
    date_posted: str,
    listing_dict: dict,
    output_dir: Path,
    processed: set[str],
    processed_path: Path,
    ollama_cfg: dict,
    gmail_cfg: dict,
    research_enabled: bool,
    research_timeout: int,
    fetch_descriptions: bool,
    dry_run: bool,
    stats: dict,
    source: str,  # "simplify" or "gmail"
    archive_ids: dict,
    email_context: str = "",
    prefetched_job_description: str = "",
) -> None:
    from generator import generate
    from researcher import research
    from scorer import score_application
    from gmail_reader import search_emails, format_emails_for_context
    from job_fetcher import fetch_job_description
    from factual_validator import validate_outputs, format_validation_feedback

    print(f"\n[{source}] Processing: {company} — {role}", flush=True)

    # --- Archive cross-check ---
    if listing_id in archive_ids:
        archive_file = archive_ids[listing_id]
        print(f"  [archive] ⚠  Already processed in {archive_file}:")
        print(f"             Company:  {company}")
        print(f"             Role:     {role}")
        if location: print(f"             Location: {location}")
        if link:     print(f"             Link:     {link}")
        print(f"  [archive] Skipping. To reprocess, delete this ID from archive/{archive_file}")
        stats["skipped_duplicate"] += 1
        return

    if dry_run:
        print(f"  [dry-run] Would generate for {company}")
        stats["processed"] += 1
        stats["listings"].append({"company": company, "role": role, "source": source, "status": "dry-run"})
        return

    # --- Job description (fetch from posting URL unless already provided) ---
    job_description = prefetched_job_description
    if not job_description and fetch_descriptions and link:
        print(f"  [pipeline] Fetching job description from {link[:60]}...", flush=True)
        job_description = fetch_job_description(link)
        if job_description:
            print(f"  [pipeline] Got {len(job_description)} chars of job description", flush=True)

    # --- Gmail cross-reference (only for SimplifyJobs source) ---
    if not email_context and source == "simplify":
        try:
            emails = search_emails(
                company,
                max_results=gmail_cfg.get("max_results", 5),
                mcp_url=gmail_cfg.get("mcp_url", "https://gmailmcp.googleapis.com/mcp/v1"),
                tool_name=gmail_cfg.get("tool_name", ""),
            )
            email_context = format_emails_for_context(emails)
        except Exception as e:
            print(f"  [pipeline] Gmail search failed: {e}", file=sys.stderr)

    # --- Web research (optional, non-fatal) ---
    research_context = ""
    if research_enabled:
        try:
            research_context = research(company, role, research_timeout)
        except Exception as e:
            print(f"  [pipeline] Research failed (non-fatal): {e}", file=sys.stderr)

    validation_meta = {
        "mode": "balanced",
        "retry_used": False,
        "passed": False,
        "violation_count": 0,
        "categories": [],
        "violations": [],
    }
    score_meta = {
        "overall": 0,
        "requirements": 0,
        "specificity": 0,
        "conciseness": 0,
        "factual_compliance": 0,
        "matched_keywords": [],
        "missing_keywords": [],
    }

    # --- Generate + Validate (balanced policy: one corrective retry) ---
    try:
        resume_md, cover_md = generate(
            listing_dict,
            email_context=email_context,
            research_context=research_context,
            job_description=job_description,
            model=ollama_cfg.get("model", "qwen3:14b"),
            base_url=ollama_cfg.get("base_url", "http://localhost:11434"),
            temperature=ollama_cfg.get("temperature", 0.7),
            max_tokens=ollama_cfg.get("max_tokens", 4096),
        )

        first_validation = validate_outputs(resume_md, cover_md, listing_dict)
        if first_validation.get("passed", False):
            validation_meta.update(first_validation)
        else:
            validation_meta.update(first_validation)
            feedback = format_validation_feedback(first_validation)
            retry_temperature = min(float(ollama_cfg.get("temperature", 0.7)), 0.2)
            print("  [pipeline] Validation failed. Retrying once with corrective guidance...", flush=True)
            resume_md, cover_md = generate(
                listing_dict,
                email_context=email_context,
                research_context=research_context,
                job_description=job_description,
                validation_feedback=feedback,
                model=ollama_cfg.get("model", "qwen3:14b"),
                base_url=ollama_cfg.get("base_url", "http://localhost:11434"),
                temperature=retry_temperature,
                max_tokens=ollama_cfg.get("max_tokens", 4096),
            )
            second_validation = validate_outputs(resume_md, cover_md, listing_dict)
            validation_meta.update(second_validation)
            validation_meta["retry_used"] = True

            if not second_validation.get("passed", False):
                msg = (
                    f"Validation blocked for {company} ({role}): "
                    f"{second_validation.get('violation_count', 0)} unsupported claim(s)"
                )
                print(f"  [pipeline] ERROR: {msg}", file=sys.stderr)
                stats["errors"].append(msg)
                stats["blocked_validation"] += 1
                stats["listings"].append({
                    "company": company,
                    "role": role,
                    "source": source,
                    "location": location,
                    "link": link,
                    "status": "blocked-validation",
                    "validation": validation_meta,
                })
                return
    except Exception as e:
        msg = f"Generation failed for {company}: {e}"
        print(f"  [pipeline] ERROR: {msg}", file=sys.stderr)
        stats["errors"].append(msg)
        return

    score_meta = score_application(
        resume_md=resume_md,
        cover_md=cover_md,
        job_description=job_description,
        listing=listing_dict,
        validation_result=validation_meta,
    )

    # --- Score-threshold quality rewrite (one pass if below threshold) ---
    scoring_cfg = config.get("scoring", {}) if "config" in dir() else {}
    score_threshold = float(ollama_cfg.get("score_rewrite_threshold",
                             scoring_cfg.get("rewrite_threshold", 65.0)))
    if score_meta.get("overall", 100) < score_threshold:
        print(f"  [pipeline] Score {score_meta['overall']:.1f} below threshold {score_threshold:.0f} — rewriting for quality...", flush=True)
        try:
            missing_kws = score_meta.get("missing_keywords", [])
            quality_feedback = ""
            if missing_kws:
                quality_feedback = (
                    f"The application scored low on requirement match. "
                    f"These relevant keywords from the job posting are not yet reflected: {', '.join(missing_kws)}. "
                    f"Incorporate them only if they are genuinely supported by My Master Resume."
                )
            resume_md2, cover_md2 = generate(
                listing_dict,
                email_context=email_context,
                research_context=research_context,
                job_description=job_description,
                validation_feedback=quality_feedback,
                model=ollama_cfg.get("model", "qwen3:14b"),
                base_url=ollama_cfg.get("base_url", "http://localhost:11434"),
                temperature=min(float(ollama_cfg.get("temperature", 0.3)), 0.25),
                max_tokens=ollama_cfg.get("max_tokens", 4096),
            )
            rewrite_validation = validate_outputs(resume_md2, cover_md2, listing_dict)
            if rewrite_validation.get("passed", False):
                resume_md, cover_md = resume_md2, cover_md2
                score_meta = score_application(
                    resume_md=resume_md,
                    cover_md=cover_md,
                    job_description=job_description,
                    listing=listing_dict,
                    validation_result=rewrite_validation,
                )
                validation_meta.update(rewrite_validation)
                score_meta["quality_rewrite"] = True
                print(f"  [pipeline] Quality rewrite accepted — new score {score_meta['overall']:.1f}", flush=True)
            else:
                print(f"  [pipeline] Quality rewrite failed validation — keeping original output", flush=True)
        except Exception as e:
            print(f"  [pipeline] Quality rewrite failed (non-fatal): {e}", file=sys.stderr)

    # --- Save to source-specific subfolder ---
    # Include role slug so multiple roles at the same company don't collide
    company_slug = _slugify(company)
    role_slug    = _slugify(role)[:40]
    company_dir  = output_dir / source / company_slug / role_slug
    company_dir.mkdir(parents=True, exist_ok=True)

    listing_out = dict(listing_dict)
    listing_out["_generation"] = {
        "validation": validation_meta,
        "score": score_meta,
    }

    (company_dir / "resume.md").write_text(resume_md, encoding="utf-8")
    (company_dir / "cover_letter.md").write_text(cover_md, encoding="utf-8")
    (company_dir / "listing.json").write_text(json.dumps(listing_out, indent=2), encoding="utf-8")
    (company_dir / "quality_score.json").write_text(json.dumps(score_meta, indent=2), encoding="utf-8")
    if job_description:
        (company_dir / "job_description.txt").write_text(job_description, encoding="utf-8")

    print(f"  [pipeline] Saved to {company_dir}/", flush=True)
    stats["processed"] += 1
    stats["listings"].append({
        "company": company,
        "role": role,
        "source": source,
        "location": location,
        "link": link,
        "output_dir": str(company_dir),
        "status": "processed",
        "has_job_description": bool(job_description),
        "validation": {
            "passed": validation_meta.get("passed", False),
            "violation_count": validation_meta.get("violation_count", 0),
            "retry_used": validation_meta.get("retry_used", False),
            "categories": validation_meta.get("categories", []),
        },
        "score": {
            "overall": score_meta.get("overall", 0),
            "requirements": score_meta.get("requirements", 0),
            "specificity": score_meta.get("specificity", 0),
            "conciseness": score_meta.get("conciseness", 0),
            "factual_compliance": score_meta.get("factual_compliance", 0),
        },
    })

    processed.add(listing_id)
    _save_processed(processed_path, processed)


def run_pipeline(dry_run: bool = False) -> dict:
    config = _load_config()

    ollama_cfg   = config.get("ollama", {})
    scraper_cfg  = config.get("scraper", {})
    gmail_cfg    = config.get("gmail", {})
    research_cfg = config.get("research", {})
    output_cfg   = config.get("output", {})

    fetch_descriptions = output_cfg.get("fetch_job_descriptions", True)
    research_enabled   = research_cfg.get("enabled", True)
    research_timeout   = research_cfg.get("timeout_seconds", 30)

    output_base    = Path(output_cfg.get("base_dir", "output"))
    processed_path = Path(output_cfg.get("processed_file", "processed.json"))
    today          = date.today().isoformat()
    output_dir     = output_base / today
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

    processed        = _load_processed(processed_path)
    archive_ids      = _load_archive_ids()
    preferences_text = _load_preferences()

    if archive_ids:
        print(f"[pipeline] Loaded {len(archive_ids)} IDs from archives for cross-check", flush=True)

    common_args = dict(
        processed=processed,
        processed_path=processed_path,
        ollama_cfg=ollama_cfg,
        gmail_cfg=gmail_cfg,
        research_enabled=research_enabled,
        research_timeout=research_timeout,
        fetch_descriptions=fetch_descriptions,
        dry_run=dry_run,
        stats=stats,
        output_dir=output_dir,
        archive_ids=archive_ids,
        config=config,
    )

    # ── Source 1: SimplifyJobs ────────────────────────────────────────────────
    print("[pipeline] Scraping SimplifyJobs listings...", flush=True)
    from scraper import scrape, scrape_newgrad
    repo   = scraper_cfg.get("repo", "")
    branch = scraper_cfg.get("branch", "dev")
    try:
        listings = scrape(repo, branch)
        stats["found"] += len(listings)
        print(f"[pipeline] Found {len(listings)} SimplifyJobs internship listings", flush=True)
    except Exception as e:
        msg = f"Scraper failed: {e}"
        print(f"[pipeline] ERROR: {msg}", file=sys.stderr)
        stats["errors"].append(msg)
        listings = []

    for listing in listings:
        if listing.id in processed:
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
            source="simplify",
            **common_args,
        )

    # ── Source 1B: SimplifyJobs New-Grad-Positions ─────────────────────────────
    print("[pipeline] Scraping SimplifyJobs New-Grad-Positions...", flush=True)
    try:
        newgrad_listings = scrape_newgrad(branch)
        stats["found"] += len(newgrad_listings)
        print(f"[pipeline] Found {len(newgrad_listings)} new grad listings", flush=True)
    except Exception as e:
        msg = f"New-Grad scraper failed: {e}"
        print(f"[pipeline] ERROR: {msg}", file=sys.stderr)
        stats["errors"].append(msg)
        newgrad_listings = []

    for listing in newgrad_listings:
        if listing.id in processed:
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
            source="simplify",
            **common_args,
        )

    # ── Source 2: crawl4ai job boards ────────────────────────────────────────
    crawl4ai_enabled = config.get("crawl4ai", {}).get("enabled", False)
    if crawl4ai_enabled:
        print("\n[pipeline] Scraping additional job boards (crawl4ai)...", flush=True)
        try:
            from crawl4ai_scraper import scrape_async_wrapper
            crawl4ai_limits = config.get("crawl4ai", {}).get("limits", {})
            crawl4ai_listings = scrape_async_wrapper(limits=crawl4ai_limits)
            stats["found"] += len(crawl4ai_listings)
            print(f"[pipeline] Found {len(crawl4ai_listings)} crawl4ai listings", flush=True)
        except ImportError:
            print("[pipeline] crawl4ai not installed — skipping. Run: pip install crawl4ai", file=sys.stderr)
            crawl4ai_listings = []
        except Exception as e:
            print(f"[pipeline] crawl4ai scrape failed (non-fatal): {e}", file=sys.stderr)
            crawl4ai_listings = []
        
        for listing in crawl4ai_listings:
            if listing.id in processed:
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
                source="crawl4ai",
                **common_args,
            )

    # ── Source 3: Gmail recruiter emails ─────────────────────────────────────
    print("\n[pipeline] Scanning Gmail for recruiter listings...", flush=True)
    from gmail_reader import get_recruiter_listings
    try:
        gmail_listings = get_recruiter_listings(
            max_results=gmail_cfg.get("recruiter_scan_limit", 30),
            mcp_url=gmail_cfg.get("mcp_url", "https://gmailmcp.googleapis.com/mcp/v1"),
            tool_name=gmail_cfg.get("tool_name", ""),
        )
        stats["found"] += len(gmail_listings)
        print(f"[pipeline] Found {len(gmail_listings)} Gmail recruiter listing(s)", flush=True)
    except Exception as e:
        print(f"[pipeline] Gmail scan failed (non-fatal): {e}", file=sys.stderr)
        gmail_listings = []

    for gl in gmail_listings:
        if gl.id in processed:
            stats["skipped_duplicate"] += 1
            continue
        passes, reason = _filter_listing(gl.role, gl.company, preferences_text)
        if not passes:
            print(f"[pipeline] Skipping Gmail listing {gl.company} — {reason}")
            stats["skipped_filter"] += 1
            continue
        # Email body IS the job description — no need to fetch a URL
        email_context = (
            f"**Recruiter:** {gl.sender_email}\n"
            f"**Subject:** {gl.subject}\n"
            f"**Date:** {gl.date}\n"
        )
        _process_listing(
            listing_id=gl.id,
            company=gl.company,
            role=gl.role,
            location="",
            link="",
            date_posted=gl.date,
            listing_dict=asdict(gl),
            source="gmail",
            email_context=email_context,
            prefetched_job_description=gl.body,
            **common_args,
        )

    # ── Final save + summary ──────────────────────────────────────────────────
    if not dry_run:
        _save_processed(processed_path, processed)
        _auto_archive(processed_path)

    _write_summary(output_dir, stats)
    return stats


def _write_summary(output_dir: Path, stats: dict) -> None:
    simplify_items = [l for l in stats["listings"] if l.get("source") == "simplify"]
    gmail_items    = [l for l in stats["listings"] if l.get("source") == "gmail"]
    processed_items = [l for l in stats["listings"] if l.get("status") == "processed"]

    avg_overall = 0.0
    avg_requirements = 0.0
    if processed_items:
        avg_overall = sum(item.get("score", {}).get("overall", 0) for item in processed_items) / len(processed_items)
        avg_requirements = sum(item.get("score", {}).get("requirements", 0) for item in processed_items) / len(processed_items)

    lines = [
        f"# Pipeline Run Summary — {stats['date']}",
        "",
        f"- **Total found:** {stats['found']}",
        f"- **Duplicates skipped:** {stats['skipped_duplicate']}",
        f"- **Filtered out:** {stats['skipped_filter']}",
        f"- **Blocked by validation:** {stats['blocked_validation']}",
        f"- **Processed:** {stats['processed']}",
        f"- **Errors:** {len(stats['errors'])}",
        f"- **Average quality score:** {avg_overall:.1f}",
        f"- **Average requirement match:** {avg_requirements:.1f}",
        "",
    ]

    if simplify_items:
        lines.append(f"## SimplifyJobs ({len(simplify_items)} processed)\n")
        for item in simplify_items:
            status = item.get("status", "processed")
            jd = " ✓ job desc" if item.get("has_job_description") else ""
            score = item.get("score", {}).get("overall", 0)
            lines.append(f"- **{item['company']}** — {item.get('role', '')} [{status}] score={score:.1f}{jd}")
            if item.get("link"): lines.append(f"  - {item['link']}")
        lines.append("")

    if gmail_items:
        lines.append(f"## Gmail Recruiter Emails ({len(gmail_items)} processed)\n")
        for item in gmail_items:
            status = item.get("status", "processed")
            score = item.get("score", {}).get("overall", 0)
            lines.append(f"- **{item['company']}** — {item.get('role', '')} [{status}] score={score:.1f}")
        lines.append("")

    if stats["errors"]:
        lines.append("## Errors\n")
        for err in stats["errors"]:
            lines.append(f"- {err}")

    summary_path = output_dir / "summary.md"
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[pipeline] Summary written to {summary_path}", flush=True)
