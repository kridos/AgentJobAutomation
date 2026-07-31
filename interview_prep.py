"""
Generates hallucination-checked interview prep material for an existing
application: company/role research, likely questions with STAR-format
resume talking points, and curated technical practice problems.
Run standalone: python interview_prep.py "Acme Corp"
"""

import json
import re
import sys
from pathlib import Path

import yaml

from generator import _call_ollama, _load_context_files, DEFAULT_MODEL, OLLAMA_BASE_URL
from factual_validator import (
    validate_outputs,
    format_validation_feedback,
    _check_metric_claims,
    _extract_allowed_metrics,
    _load_resume_master,
)
from researcher import research
from interview_problems import match_problems


CONFIG_PATH = Path(__file__).parent / "config.yaml"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _find_application(company: str, role_hint: str = "") -> Path | None:
    """Globs output/*/*/<company-slug>/*/listing.json for the slugified
    company name, optionally filtered by role_hint (substring match
    against listing.json's role field). Returns the most recent match's
    directory, or None if no match. Prints disambiguation info when
    multiple matches exist."""
    company_slug = _slugify(company)
    output_base = Path("output")
    if not output_base.exists():
        return None

    matches = []
    for listing_path in output_base.glob(f"*/*/{company_slug}/*/listing.json"):
        try:
            listing = json.loads(listing_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if role_hint and role_hint.lower() not in listing.get("role", "").lower():
            continue
        matches.append(listing_path.parent)

    if not matches:
        return None

    matches.sort(key=lambda p: p.parts[1] if len(p.parts) > 1 else "", reverse=True)

    if len(matches) > 1:
        print(f"[interview_prep] Found {len(matches)} matching applications for '{company}':", flush=True)
        for m in matches:
            print(f"  {m}", flush=True)
        print(f"[interview_prep] Using most recent: {matches[0]}", flush=True)

    return matches[0]


def _build_prep_prompt(
    context: dict,
    listing: dict,
    job_description: str,
    research_context: str,
    validation_feedback: str = "",
) -> str:
    company = listing.get("company", "")
    role = listing.get("role", "")

    parts = [
        "You are an interview-prep coach helping a candidate prepare for a real upcoming interview.",
        "",
        f"## Target\n**Company:** {company}\n**Role:** {role}",
        "",
        "## My Background (for facts/context)\n" + context.get("resume_master", ""),
    ]

    if context.get("accomplishments"):
        parts += ["", "## Recent Accomplishments\n" + context["accomplishments"]]

    if job_description:
        parts += ["", "## Job Posting\n" + job_description]

    if research_context:
        parts += ["", "## Company/Role Research\n" + research_context]

    parts += [
        "",
        "## Instructions",
        "- HARD RULE: Do not invent or alter personal identity details (name, phone, email, links)",
        "- HARD RULE: Do not invent qualifications, degrees, GPA, employers, projects, dates, tools, metrics, awards, or responsibilities",
        "- HARD RULE: If a detail is not explicitly present in My Background above, omit it",
        "- Write 6-10 likely interview questions: a mix of behavioral and role-specific technical/situational questions, tailored to the job posting and company research above",
        "- For each question, write a brief STAR-format (Situation/Task/Action/Result) talking point using ONLY real experience from My Background — if no real experience genuinely fits a question, say so explicitly rather than inventing one",
        "- Output ONLY markdown: a '## Likely Questions & Talking Points' heading followed by the questions and talking points, no preamble or explanation",
    ]

    if validation_feedback:
        parts += [
            "",
            "## Validation Corrections (must fix all)",
            validation_feedback,
            "Revise to remove or correct unsupported claims while preserving the question/talking-point structure.",
        ]

    return "\n".join(parts)


def _validate_prep_content(content: str, listing: dict, model: str, base_url: str, semantic_check: bool = True) -> dict:
    """Validate interview-prep content. Passes '' as the resume_md argument
    to validate_outputs so the resume-shaped checks (org headings, project
    headings, unsupported tech, identity name) — which misfire on prep
    content's STAR-format headings and legitimate tech discussion — become
    harmless no-ops, while contact/GPA/degree checks and the semantic
    verifier (both cover_md-scoped) keep working. Supplements with a
    genuine metric check against the REAL canonical resume's metrics,
    since validate_outputs' own metric check is a no-op when resume_md
    is empty."""
    validation = validate_outputs("", content, listing, model=model, base_url=base_url, semantic_check=semantic_check)

    resume_master = _load_resume_master()
    allowed_metrics = _extract_allowed_metrics(resume_master)
    metric_violations = _check_metric_claims(content, allowed_metrics)

    if metric_violations:
        violations = validation.get("violations", []) + metric_violations
        validation["violations"] = violations
        validation["violation_count"] = len(violations)
        validation["categories"] = sorted(set(validation.get("categories", [])) | {"metric_claim"})
        validation["passed"] = False

    return validation


def generate_interview_prep(company: str, role_hint: str = "") -> dict:
    """Orchestrates: find the application, research the company, generate
    + validate questions/talking-points, match technical problems, save
    interview_prep.md. Returns {"status": "ok"|"not_found"|"validation_blocked"|"generation_failed",
    "path": str|None}."""
    app_dir = _find_application(company, role_hint)
    if app_dir is None:
        return {"status": "not_found", "path": None}

    listing = json.loads((app_dir / "listing.json").read_text(encoding="utf-8"))

    job_description = ""
    jd_path = app_dir / "job_description.txt"
    if jd_path.exists():
        job_description = jd_path.read_text(encoding="utf-8")

    config = _load_config()
    ollama_cfg = config.get("ollama", {})
    research_cfg = config.get("research", {})
    model = ollama_cfg.get("model", "qwen3:14b")
    base_url = ollama_cfg.get("base_url", "http://localhost:11434")
    temperature = ollama_cfg.get("temperature", 0.7)
    semantic_check = config.get("validation", {}).get("semantic_check", True)

    research_context = ""
    if research_cfg.get("enabled", True):
        try:
            research_context = research(
                listing.get("company", company), listing.get("role", ""),
                research_cfg.get("timeout_seconds", 30),
                model=model, base_url=base_url,
            )
        except Exception as e:
            print(f"[interview_prep] Research failed (non-fatal): {e}", file=sys.stderr)

    context = _load_context_files()

    try:
        content = _call_ollama(
            _build_prep_prompt(context, listing, job_description, research_context),
            model=model, base_url=base_url, temperature=temperature,
        ).strip()

        validation = _validate_prep_content(content, listing, model, base_url, semantic_check)

        if not validation.get("passed", False):
            feedback = format_validation_feedback(validation)
            retry_temp = min(float(temperature), 0.2)
            print(f"[interview_prep] Validation failed. Retrying once...", flush=True)
            content = _call_ollama(
                _build_prep_prompt(context, listing, job_description, research_context, validation_feedback=feedback),
                model=model, base_url=base_url, temperature=retry_temp,
            ).strip()
            validation = _validate_prep_content(content, listing, model, base_url, semantic_check)

            if not validation.get("passed", False):
                msg = f"Validation blocked: {validation.get('violation_count', 0)} unsupported claim(s)"
                print(f"[interview_prep] ERROR: {msg}", file=sys.stderr)
                return {"status": "validation_blocked", "path": None}
    except Exception as e:
        msg = f"Generation failed: {e}"
        print(f"[interview_prep] ERROR: {msg}", file=sys.stderr)
        return {"status": "generation_failed", "path": None}

    problems = match_problems(job_description or listing.get("role", ""))
    problems_md = "\n".join(
        f"- **{p['title']}** ({p['difficulty']}, {', '.join(p['tags'])}) — {p['link']}"
        for p in problems
    )

    research_section = f"{research_context}\n\n" if research_context else ""
    full_md = f"{research_section}{content}\n\n## Practice Problems\n{problems_md}\n"

    output_path = app_dir / "interview_prep.md"
    output_path.write_text(full_md, encoding="utf-8")

    return {"status": "ok", "path": str(output_path)}


if __name__ == "__main__":
    company_arg = sys.argv[1] if len(sys.argv) > 1 else "Stripe"
    result = generate_interview_prep(company_arg)
    print(result)
