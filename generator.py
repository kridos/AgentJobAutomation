"""
Generates tailored resume and cover letter via local Ollama.
Run standalone: python generator.py
"""

import httpx
import json
import re
import sys
from pathlib import Path
from typing import Optional


OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5"

CONTEXT_DIR = Path(__file__).parent / "context"


def _load_context_files() -> dict[str, str]:
    files = {
        "resume_master": CONTEXT_DIR / "resume_master.md",
        "voice": CONTEXT_DIR / "voice.md",
        "preferences": CONTEXT_DIR / "preferences.md",
    }
    loaded = {}
    for key, path in files.items():
        if path.exists():
            loaded[key] = path.read_text(encoding="utf-8")
        else:
            print(f"[generator] Warning: {path} not found", file=sys.stderr)
            loaded[key] = ""
    return loaded


def _extract_resume_header(resume_master: str) -> str:
    lines = resume_master.splitlines()
    header_lines = []
    for line in lines:
        if line.strip() == "---":
            break
        header_lines.append(line)
    return "\n".join(header_lines).strip()


def _extract_section(markdown: str, section_name: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(section_name)}\s*$.*?(?=^##\s+[A-Z][A-Z\s&/-]*\s*$|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(markdown)
    return match.group(0).strip() if match else ""


def _replace_section(markdown: str, section_name: str, replacement: str) -> str:
    if not replacement:
        return markdown

    pattern = re.compile(
        rf"^##\s+{re.escape(section_name)}\s*$.*?(?=^##\s+[A-Z][A-Z\s&/-]*\s*$|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    if pattern.search(markdown):
        return pattern.sub(replacement.strip() + "\n\n", markdown, count=1)

    header_match = re.search(r"^---\s*$", markdown, re.MULTILINE)
    if header_match:
        insert_at = header_match.end()
        return markdown[:insert_at] + "\n\n" + replacement.strip() + markdown[insert_at:]

    return replacement.strip() + "\n\n" + markdown.lstrip()


def _select_projects(
    project_names: list[str],
    job_description: str,
    listing: dict,
    model: str,
    base_url: str,
    temperature: float,
) -> list[str]:
    """Ask the model to pick the 2-3 most relevant project names from the canonical list."""
    if not project_names:
        return []
    names_list = "\n".join(f"- {n}" for n in project_names)
    company = listing.get("company", "")
    role = listing.get("role", "")
    prompt = (
        f"You are helping tailor a resume for: {company} — {role}.\n\n"
        f"Available projects:\n{names_list}\n\n"
        f"Job posting (excerpt):\n{job_description[:1500]}\n\n"
        f"Select the 2-3 most relevant project names from the list above for this role. "
        f"Return ONLY the exact project names, one per line, no explanations."
    )
    try:
        raw = _call_ollama(prompt, model=model, base_url=base_url, temperature=temperature, max_tokens=256)
        selected = []
        name_lower = {n.lower(): n for n in project_names}
        for line in raw.splitlines():
            cleaned = line.strip().lstrip("-• ").strip()
            if not cleaned:
                continue
            if cleaned.lower() in name_lower:
                selected.append(name_lower[cleaned.lower()])
            else:
                # fuzzy: pick first project whose name is contained in the response line
                for original_lower, original in name_lower.items():
                    if original_lower in cleaned.lower():
                        selected.append(original)
                        break
            if len(selected) >= 3:
                break
        return selected or project_names[:2]
    except Exception:
        return project_names[:2]


def _assemble_resume(
    resume_master: str,
    listing: dict,
    selected_project_names: list[str],
) -> str:
    """Build the full resume deterministically from canonical sections + selected projects."""
    project_map = _extract_project_map(resume_master)
    header     = _extract_resume_header(resume_master)
    education  = _extract_section(resume_master, "EDUCATION")
    skills     = _extract_section(resume_master, "TECHNICAL SKILLS")
    experience = _extract_section(resume_master, "EXPERIENCE")
    activities = _extract_section(resume_master, "ACTIVITIES & HONORS")

    # Strip [tags: ...] lines from experience bullets
    experience = re.sub(r"^\[tags:.*\]\n?", "", experience, flags=re.MULTILINE)

    projects_blocks = []
    for name in selected_project_names:
        key = re.sub(r"\s+", " ", name.lower())
        block = project_map.get(key, "")
        if block:
            # Strip [tags: ...] metadata lines
            block = re.sub(r"^\[tags:.*\]\n?", "", block, flags=re.MULTILINE)
            projects_blocks.append(block.strip())

    sections = [header.strip(), "---", education.strip(), skills.strip(), experience.strip()]
    if projects_blocks:
        sections.append("## PROJECTS\n\n" + "\n\n".join(projects_blocks))
    if activities:
        sections.append(activities.strip())

    return "\n\n".join(s for s in sections if s) + "\n"


def _extract_project_map(resume_master: str) -> dict[str, str]:
    """Returns {normalized_project_title: full_project_block} from the PROJECTS section."""
    projects_section = _extract_section(resume_master, "PROJECTS")
    if not projects_section:
        return {}

    project_map: dict[str, str] = {}
    current_title: str = ""
    current_lines: list[str] = []
    for line in projects_section.splitlines():
        if line.startswith("### "):
            if current_title:
                project_map[current_title] = "\n".join(current_lines).rstrip()
            raw_title = line[4:].split("|", 1)[0].strip()
            current_title = re.sub(r"\s+", " ", raw_title.lower())
            current_lines = [line]
        elif current_title:
            current_lines.append(line)
    if current_title:
        project_map[current_title] = "\n".join(current_lines).rstrip()
    return project_map


def _apply_canonical_project_bullets(resume_md: str, resume_master: str) -> str:
    """Replace generated project bullet content with canonical text from resume_master.
    The model selects which projects to include; all content comes from the master."""
    project_map = _extract_project_map(resume_master)
    if not project_map:
        return resume_md

    lines = resume_md.splitlines()
    result: list[str] = []
    in_projects = False
    skip_until_next_project_or_section = False
    pending_canonical: list[str] = []

    section_re = re.compile(r"^##\s+([A-Z][A-Z\s&/-]+)\s*$")
    project_re = re.compile(r"^###\s+(.+)$")

    i = 0
    while i < len(lines):
        line = lines[i]
        section_match = section_re.match(line)
        if section_match:
            if pending_canonical:
                result.extend(pending_canonical)
                pending_canonical = []
            in_projects = "PROJECTS" in section_match.group(1).upper()
            skip_until_next_project_or_section = False
            result.append(line)
            i += 1
            continue

        if in_projects:
            proj_match = project_re.match(line)
            if proj_match:
                if pending_canonical:
                    result.extend(pending_canonical)
                    pending_canonical = []
                raw = proj_match.group(1).split("|", 1)[0].strip()
                key = re.sub(r"\s+", " ", raw.lower())
                if key in project_map:
                    pending_canonical = project_map[key].splitlines()
                    skip_until_next_project_or_section = True
                else:
                    # Unknown/fabricated project — skip it and all its content
                    skip_until_next_project_or_section = True
                    pending_canonical = []
                i += 1
                continue

            if skip_until_next_project_or_section:
                i += 1
                continue

        result.append(line)
        i += 1

    if pending_canonical:
        result.extend(pending_canonical)

    return "\n".join(result)


def _call_ollama(
    prompt: str,
    model: str = DEFAULT_MODEL,
    base_url: str = OLLAMA_BASE_URL,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """Call Ollama via its OpenAI-compatible chat completions endpoint."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    resp = httpx.post(
        f"{base_url}/v1/chat/completions",
        json=payload,
        timeout=120.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _build_resume_prompt(
    context: dict,
    listing: dict,
    email_context: str = "",
    research_context: str = "",
    job_description: str = "",
    validation_feedback: str = "",
) -> str:
    company = listing.get("company", "")
    role = listing.get("role", "")
    location = listing.get("location", "")
    link = listing.get("link", "")

    parts = [
        "You are an expert resume writer. Your task is to create a tailored, one-page resume in Markdown format.",
        "",
        f"## Target Role\n**Company:** {company}\n**Role:** {role}\n**Location:** {location}\n**Link:** {link}",
        "",
        "## Canonical Resume Sections (copy these VERBATIM — do not alter)",
        _extract_resume_header(context.get("resume_master", "")),
        "",
        _extract_section(context.get("resume_master", ""), "EDUCATION"),
        "",
        _extract_section(context.get("resume_master", ""), "TECHNICAL SKILLS"),
        "",
        _extract_section(context.get("resume_master", ""), "EXPERIENCE"),
        "",
        "## My Master Resume (select and tailor relevant sections)\n" + context.get("resume_master", ""),
        "",
        "## My Preferences\n" + context.get("preferences", ""),
    ]

    if job_description:
        parts += ["", "## Job Posting (tailor directly to these requirements)\n" + job_description]

    if email_context:
        parts += ["", "## Recruiter Email Context (use to personalize)\n" + email_context]

    if research_context:
        parts += ["", "## Company/Role Research\n" + research_context]

    parts += [
        "",
        "## Instructions",
        "- HARD RULE: Do not invent or alter personal identity details (name, phone, email, links)",
        "- HARD RULE: Do not invent qualifications, degrees, GPA, employers, projects, dates, tools, metrics, awards, or responsibilities",
        "- HARD RULE: If a detail is not explicitly present in My Master Resume or the job listing fields above, omit it",
        "- Copy the Canonical Resume Sections VERBATIM: resume header, EDUCATION, TECHNICAL SKILLS, and EXPERIENCE must appear exactly as given above",
        "- The ONLY section you should tailor to the job posting is PROJECTS — select the 2-3 most relevant projects from My Master Resume",
        "- Mirror keywords and phrases from the Job Posting section above only when those skills, tools, or claims are already in My Master Resume",
        "- Do not add, remove, or reword any bullet in the EXPERIENCE section",
        "- Keep it to one page in Markdown",
        "- Use strong action verbs and quantified impact where possible",
        "- Output ONLY the resume markdown, no preamble or explanation",
    ]

    if validation_feedback:
        parts += [
            "",
            "## Validation Corrections (must fix all)",
            validation_feedback,
            "Revise to remove or correct unsupported claims while preserving role relevance.",
        ]

    return "\n".join(parts)


# Tech terms the cover letter scrub will strip if not in canonical resume
_COVER_SCRUB_TERMS = {
    "gcp", "kubernetes", "postgresql", "mongodb", "redis", "graphql",
    "terraform", "azure", "go", "rust", "scala", "kotlin", "swift",
    "node.js", "node", "express", "elasticsearch", "kafka", "spark",
    "hadoop", "airflow", "dbt", "snowflake", "bigquery", "dynamo",
}


def _scrub_cover_letter(cover_md: str, resume_master: str) -> str:
    """Remove fabricated GPA values and unsupported tech from cover letter."""
    allowed_gpas = {m.group(1) for m in re.finditer(r"\bGPA\s*[:=]?\s*(\d(?:\.\d{1,2})?)\b", resume_master, re.IGNORECASE)}

    def _fix_gpa(m: re.Match) -> str:
        val = m.group(1)
        if val in allowed_gpas:
            return m.group(0)
        if allowed_gpas:
            canonical = sorted(allowed_gpas, key=float)[-1]
            return m.group(0).replace(val, canonical)
        return ""

    cover_md = re.sub(r"\bGPA\s*[:=]?\s*(\d(?:\.\d{1,2})?)\b", _fix_gpa, cover_md, flags=re.IGNORECASE)

    for term in sorted(_COVER_SCRUB_TERMS, key=len, reverse=True):
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", resume_master, re.IGNORECASE):
            continue  # term is actually in master resume — keep it
        cover_md = re.sub(rf"(?<!\w){re.escape(term)}(?!\w)", "", cover_md, flags=re.IGNORECASE)

    cover_md = re.sub(r"[ \t]{2,}", " ", cover_md)
    cover_md = re.sub(r" ([,;.])", r"\1", cover_md)
    return cover_md


def _build_cover_letter_prompt(
    context: dict,
    listing: dict,
    email_context: str = "",
    research_context: str = "",
    job_description: str = "",
    validation_feedback: str = "",
) -> str:
    company = listing.get("company", "")
    role = listing.get("role", "")

    parts = [
        "You are an expert cover letter writer. Write a tailored cover letter in Markdown.",
        "",
        f"## Target Role\n**Company:** {company}\n**Role:** {role}",
        "",
        "## My Voice and Style Guide\n" + context.get("voice", ""),
        "",
        "## My Master Resume (for facts/context)\n" + context.get("resume_master", ""),
        "",
        "## My Preferences\n" + context.get("preferences", ""),
    ]

    if job_description:
        parts += ["", "## Job Posting (reference specific requirements and responsibilities)\n" + job_description]

    if email_context:
        parts += ["", "## Recruiter Email Context\n" + email_context]

    if research_context:
        parts += ["", "## Company/Role Research\n" + research_context]

    parts += [
        "",
        "## Instructions",
        "- HARD RULE: Do not invent or alter personal identity details (name, phone, email, links)",
        "- HARD RULE: Do not invent qualifications, degrees, GPA, employers, projects, dates, tools, metrics, awards, or responsibilities",
        "- HARD RULE: If a detail is not explicitly present in My Master Resume or the job listing fields above, omit it",
        "- HARD RULE: If you mention GPA, use exactly the GPA value from My Master Resume — do not use any other number",
        "- HARD RULE: Do not mention any technology, tool, or framework not listed in My Master Resume TECHNICAL SKILLS section",
        "- Follow my voice guide strictly — match my tone, avoid the phrases I listed to avoid",
        "- 3 short paragraphs max: hook, body (why me + why them), close",
        "- Reference specific requirements or projects from the Job Posting only when they can be supported by My Master Resume",
        "- If recruiter emails exist, subtly acknowledge the relationship",
        "- Output ONLY the cover letter markdown, no preamble or explanation",
    ]

    if validation_feedback:
        parts += [
            "",
            "## Validation Corrections (must fix all)",
            validation_feedback,
            "Revise to remove or correct unsupported claims while preserving role relevance.",
        ]

    return "\n".join(parts)


def generate(
    listing: dict,
    email_context: str = "",
    research_context: str = "",
    job_description: str = "",
    validation_feedback: str = "",
    model: str = DEFAULT_MODEL,
    base_url: str = OLLAMA_BASE_URL,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> tuple[str, str]:
    """
    Returns (resume_md, cover_letter_md) for the given listing.
    """
    context = _load_context_files()

    resume_prompt = _build_resume_prompt(
        context,
        listing,
        email_context,
        research_context,
        job_description,
        validation_feedback,
    )
    cover_prompt = _build_cover_letter_prompt(
        context,
        listing,
        email_context,
        research_context,
        job_description,
        validation_feedback,
    )

    print(f"[generator] Selecting projects for {listing.get('company')}...", flush=True)
    resume_master = context.get("resume_master", "")
    all_project_names = list(_extract_project_map(resume_master).keys())
    # Convert back to display names (title-cased from map keys)
    project_map = _extract_project_map(resume_master)
    display_names = [
        next(line[4:].split("|", 1)[0].strip()
             for line in block.splitlines() if line.startswith("### "))
        for block in project_map.values()
    ]
    selected = _select_projects(display_names, job_description, listing, model, base_url, temperature)
    resume_md = _assemble_resume(resume_master, listing, selected)

    print(f"[generator] Generating cover letter for {listing.get('company')}...", flush=True)
    cover_md = _call_ollama(cover_prompt, model=model, base_url=base_url,
                             temperature=temperature, max_tokens=max_tokens)
    cover_md = _scrub_cover_letter(cover_md, resume_master)

    return resume_md, cover_md


if __name__ == "__main__":
    # Test against a hardcoded listing
    test_listing = {
        "company": "Stripe",
        "role": "Software Engineering Intern",
        "location": "San Francisco, CA",
        "link": "https://stripe.com/jobs",
        "date_posted": "2026-06-01",
        "id": "stripe-software-engineering-intern",
    }
    test_email_context = ""
    test_research = "Stripe builds payment infrastructure. Tech stack: Ruby, Go, Java, TypeScript. Values: API design, reliability, developer experience."

    print("Testing Ollama connection and generation...\n")
    try:
        resume, cover = generate(
            test_listing,
            email_context=test_email_context,
            research_context=test_research,
        )
        print("=== RESUME ===")
        print(resume[:1000])
        print("\n=== COVER LETTER ===")
        print(cover[:1000])
    except httpx.ConnectError:
        print("ERROR: Cannot connect to Ollama at localhost:11434. Is it running?", file=sys.stderr)
        sys.exit(1)
