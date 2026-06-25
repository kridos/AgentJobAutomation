"""
Manually generate a resume and cover letter for a job you found yourself.
Paste the job description directly into the console.

Run: python manual_run.py
"""

import json
import sys
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path

import yaml


CONFIG_PATH = Path(__file__).parent / "config.yaml"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def _prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{label}{suffix}: ").strip()
    return val if val else default


def _prompt_multiline(label: str) -> str:
    print(f"{label}")
    print("(Paste the text, then press Enter twice on a blank line when done)")
    lines = []
    blank_count = 0
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "":
            blank_count += 1
            if blank_count >= 2:
                break
            lines.append("")
        else:
            blank_count = 0
            lines.append(line)
    return "\n".join(lines).strip()


def _slugify(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def run_manual() -> None:
    config   = _load_config()
    ollama   = config.get("ollama", {})
    output   = config.get("output", {})

    print("\n=== Manual Job Entry ===\n")
    print("Fill in the details for the role you found. Press Enter to skip optional fields.\n")

    company     = _prompt("Company name")
    role        = _prompt("Role / job title")
    location    = _prompt("Location (optional)")
    link        = _prompt("Job posting URL (optional)")
    date_posted = _prompt("Date posted (optional)", default=date.today().isoformat())

    print()
    job_description = _prompt_multiline("Job description / posting text:")

    print()
    extra_context = _prompt_multiline("Any extra context? (recruiter notes, referral info, etc. — optional):")

    if not company or not role:
        print("Company and role are required.")
        sys.exit(1)

    listing_dict = {
        "company":     company,
        "role":        role,
        "location":    location,
        "link":        link,
        "date_posted": date_posted,
        "id":          f"manual-{_slugify(company)}-{_slugify(role)}",
        "source":      "manual",
    }

    print(f"\n[manual] Generating for {company} — {role}...")

    from generator import generate
    try:
        resume_md, cover_md = generate(
            listing_dict,
            email_context=extra_context,
            research_context="",
            job_description=job_description,
            model=ollama.get("model", "qwen3:14b"),
            base_url=ollama.get("base_url", "http://localhost:11434"),
            temperature=ollama.get("temperature", 0.7),
            max_tokens=ollama.get("max_tokens", 4096),
        )
    except Exception as e:
        print(f"Generation failed: {e}", file=sys.stderr)
        sys.exit(1)

    today      = date.today().isoformat()
    output_dir = Path(output.get("base_dir", "output")) / today / "manual" / _slugify(company)

    # Handle multiple roles at the same company
    role_slug  = _slugify(role)[:40]
    output_dir = output_dir / role_slug
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "resume.md").write_text(resume_md, encoding="utf-8")
    (output_dir / "cover_letter.md").write_text(cover_md, encoding="utf-8")
    (output_dir / "listing.json").write_text(json.dumps(listing_dict, indent=2), encoding="utf-8")
    if job_description:
        (output_dir / "job_description.txt").write_text(job_description, encoding="utf-8")

    print(f"\n[manual] Done! Files saved to: {output_dir}")
    print(f"  resume.md")
    print(f"  cover_letter.md")


if __name__ == "__main__":
    run_manual()
