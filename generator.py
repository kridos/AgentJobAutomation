"""
Generates tailored resume and cover letter via local Ollama.
Run standalone: python generator.py
"""

import httpx
import json
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
        "## My Master Resume (select and tailor relevant sections)\n" + context.get("resume_master", ""),
        "",
        "## My Preferences\n" + context.get("preferences", ""),
    ]

    if email_context:
        parts += ["", "## Recruiter Email Context (use to personalize)\n" + email_context]

    if research_context:
        parts += ["", "## Company/Role Research\n" + research_context]

    parts += [
        "",
        "## Instructions",
        "- Select only experience and projects tagged for this type of role",
        "- Tailor every bullet to the company's tech stack and values (use the research context above)",
        "- Keep it to one page in Markdown",
        "- Use strong action verbs and quantified impact where possible",
        "- Output ONLY the resume markdown, no preamble or explanation",
    ]

    return "\n".join(parts)


def _build_cover_letter_prompt(
    context: dict,
    listing: dict,
    email_context: str = "",
    research_context: str = "",
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

    if email_context:
        parts += ["", "## Recruiter Email Context\n" + email_context]

    if research_context:
        parts += ["", "## Company/Role Research\n" + research_context]

    parts += [
        "",
        "## Instructions",
        "- Follow my voice guide strictly — match my tone, avoid the phrases I listed to avoid",
        "- 3 short paragraphs max: hook, body (why me + why them), close",
        "- Reference specific things about the company from the research context",
        "- If recruiter emails exist, subtly acknowledge the relationship",
        "- Output ONLY the cover letter markdown, no preamble or explanation",
    ]

    return "\n".join(parts)


def generate(
    listing: dict,
    email_context: str = "",
    research_context: str = "",
    model: str = DEFAULT_MODEL,
    base_url: str = OLLAMA_BASE_URL,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> tuple[str, str]:
    """
    Returns (resume_md, cover_letter_md) for the given listing.
    """
    context = _load_context_files()

    resume_prompt = _build_resume_prompt(context, listing, email_context, research_context)
    cover_prompt = _build_cover_letter_prompt(context, listing, email_context, research_context)

    print(f"[generator] Generating resume for {listing.get('company')}...", flush=True)
    resume_md = _call_ollama(resume_prompt, model=model, base_url=base_url,
                              temperature=temperature, max_tokens=max_tokens)

    print(f"[generator] Generating cover letter for {listing.get('company')}...", flush=True)
    cover_md = _call_ollama(cover_prompt, model=model, base_url=base_url,
                             temperature=temperature, max_tokens=max_tokens)

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
