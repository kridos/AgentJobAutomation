"""
Cold-email outreach: generate a tailored, hallucination-checked email per
contact in context/outreach_contacts.yaml and create it as a Gmail draft
(never sent). Tracks which contacts have already been drafted.
Run standalone: python outreach.py
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

import yaml

from generator import _call_ollama, _load_context_files, DEFAULT_MODEL, OLLAMA_BASE_URL
from factual_validator import validate_outputs, format_validation_feedback
from gmail_reader import create_draft, GMAIL_MCP_URL


CONFIG_PATH = Path(__file__).parent / "config.yaml"
CONTEXT_DIR = Path(__file__).parent / "context"
CONTACTS_PATH = CONTEXT_DIR / "outreach_contacts.yaml"
PROCESSED_PATH = Path(__file__).parent / "outreach_processed.json"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _load_contacts() -> list[dict]:
    if not CONTACTS_PATH.exists():
        return []
    with open(CONTACTS_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, list) else []


def _save_contacts(contacts: list[dict]) -> None:
    CONTACTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONTACTS_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(contacts, f, sort_keys=False, allow_unicode=True)


def _load_outreach_processed() -> set[str]:
    if PROCESSED_PATH.exists():
        try:
            with open(PROCESSED_PATH, encoding="utf-8-sig") as f:
                data = json.load(f)
            return set(data) if isinstance(data, list) else set()
        except (json.JSONDecodeError, ValueError):
            print("[outreach] outreach_processed.json is malformed — starting fresh", file=sys.stderr)
    return set()


def _save_outreach_processed(processed: set[str]) -> None:
    with open(PROCESSED_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(processed), f, indent=2)


def _save_outreach_output(contact: dict, body: str) -> None:
    today = date.today().isoformat()
    company_slug = _slugify(contact.get("company", "unknown"))
    output_dir = Path("output") / today / "outreach" / company_slug
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "email.md").write_text(body, encoding="utf-8")
    (output_dir / "contact.json").write_text(json.dumps(contact, indent=2), encoding="utf-8")


def add_contact_interactive() -> None:
    from manual_run import _prompt, _prompt_multiline

    print("\n=== Add Outreach Contact ===\n")
    company = _prompt("Company name")
    contact_name = _prompt("Contact name (optional)")
    contact_email = _prompt("Contact email")
    notes = _prompt_multiline("Notes (optional — how you found them, what to mention):")

    if not company or not contact_email:
        print("Company and contact email are required.")
        sys.exit(1)

    contact_id = f"{_slugify(company)}-{_slugify(contact_name or contact_email)}"

    contacts = _load_contacts()
    contacts.append({
        "id": contact_id,
        "company": company,
        "contact_name": contact_name,
        "contact_email": contact_email,
        "notes": notes,
    })
    _save_contacts(contacts)

    print(f"\n[outreach] Added {company} ({contact_email}) to {CONTACTS_PATH}")


def _build_cold_email_prompt(context: dict, contact: dict, validation_feedback: str = "") -> str:
    company = contact.get("company", "")
    contact_name = contact.get("contact_name", "")
    notes = contact.get("notes", "")

    parts = [
        "You are writing a short, genuine cold outreach email to a potential employer, "
        "expressing interest in internship/full-time opportunities.",
        "",
        f"## Target\n**Company:** {company}\n**Contact:** {contact_name}",
        "",
        "## My Voice and Style Guide\n" + context.get("voice", ""),
        "",
        "## My Background (for facts/context)\n" + context.get("resume_master", ""),
    ]

    if context.get("accomplishments"):
        parts += ["", "## Recent Accomplishments (permanent record — integrate if genuinely relevant)\n" + context["accomplishments"]]

    if context.get("recent_updates"):
        parts += ["", "## Pending Updates (not yet reviewed — integrate if genuinely relevant)\n" + context["recent_updates"]]

    if notes:
        parts += ["", "## Notes About This Contact (use to personalize)\n" + notes]

    parts += [
        "",
        "## Instructions",
        "- HARD RULE: Do not invent or alter personal identity details (name, phone, email, links)",
        "- HARD RULE: Do not invent qualifications, degrees, GPA, employers, projects, dates, tools, metrics, awards, or responsibilities",
        "- HARD RULE: If a detail is not explicitly present in My Background above, omit it",
        "- Follow my voice guide strictly — match my tone, avoid the phrases I listed to avoid",
        "- Keep it SHORT: 3-5 sentences max, this is a cold email not a cover letter",
        "- Be specific about why this company, using the notes above if provided",
        "- End with a clear, low-friction ask (e.g. a quick call, or simply asking about openings)",
        "- Output ONLY the email body text, no subject line, no preamble, no explanation",
    ]

    if validation_feedback:
        parts += [
            "",
            "## Validation Corrections (must fix all)",
            validation_feedback,
            "Revise to remove or correct unsupported claims while preserving genuine interest and personalization.",
        ]

    return "\n".join(parts)


def generate_cold_email(
    contact: dict,
    validation_feedback: str = "",
    model: str = DEFAULT_MODEL,
    base_url: str = OLLAMA_BASE_URL,
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> str:
    context = _load_context_files()
    prompt = _build_cold_email_prompt(context, contact, validation_feedback)
    return _call_ollama(prompt, model=model, base_url=base_url, temperature=temperature, max_tokens=max_tokens).strip()


def _build_subject(contact: dict) -> str:
    company = contact.get("company", "")
    return f"Quick question about opportunities at {company}"


def run_outreach() -> dict:
    config = _load_config()
    ollama_cfg = config.get("ollama", {})
    gmail_cfg = config.get("gmail", {})

    model = ollama_cfg.get("model", "qwen3:14b")
    base_url = ollama_cfg.get("base_url", "http://localhost:11434")
    temperature = ollama_cfg.get("temperature", 0.7)
    mcp_url = gmail_cfg.get("mcp_url", GMAIL_MCP_URL)
    tool_name = gmail_cfg.get("tool_name", "")

    contacts = _load_contacts()
    processed = _load_outreach_processed()

    stats = {"drafted": 0, "skipped": 0, "errors": []}

    for contact in contacts:
        contact_id = contact.get("id", "")
        company = contact.get("company", "")

        if not contact_id or contact_id in processed:
            stats["skipped"] += 1
            continue

        email_addr = contact.get("contact_email", "")
        if not email_addr:
            msg = f"No contact_email for {company} ({contact_id}) — skipping"
            print(f"[outreach] {msg}", file=sys.stderr)
            stats["errors"].append(msg)
            continue

        try:
            body = generate_cold_email(contact, model=model, base_url=base_url, temperature=temperature)
            validation = validate_outputs(body, body, contact, model=model, base_url=base_url)

            if not validation.get("passed", False):
                feedback = format_validation_feedback(validation)
                retry_temp = min(float(temperature), 0.2)
                print(f"[outreach] Validation failed for {company}. Retrying once...", flush=True)
                body = generate_cold_email(contact, validation_feedback=feedback, model=model, base_url=base_url, temperature=retry_temp)
                validation = validate_outputs(body, body, contact, model=model, base_url=base_url)

                if not validation.get("passed", False):
                    msg = f"Validation blocked for {company} ({contact_id}): {validation.get('violation_count', 0)} unsupported claim(s)"
                    print(f"[outreach] ERROR: {msg}", file=sys.stderr)
                    stats["errors"].append(msg)
                    continue
        except Exception as e:
            msg = f"Generation failed for {company} ({contact_id}): {e}"
            print(f"[outreach] ERROR: {msg}", file=sys.stderr)
            stats["errors"].append(msg)
            continue

        subject = _build_subject(contact)
        try:
            drafted = create_draft(email_addr, subject, body, mcp_url=mcp_url, tool_name=tool_name)
        except Exception as e:
            drafted = False
            msg = f"Draft creation failed for {company} ({contact_id}): {e}"
            print(f"[outreach] ERROR: {msg}", file=sys.stderr)
            stats["errors"].append(msg)

        if not drafted:
            continue

        _save_outreach_output(contact, body)
        processed.add(contact_id)
        _save_outreach_processed(processed)
        stats["drafted"] += 1

    return stats


def list_outreach_status() -> list[dict]:
    """Returns [{"company", "contact_email", "status"}] for every contact.
    status is 'drafted' or 'pending'."""
    contacts = _load_contacts()
    processed = _load_outreach_processed()
    return [
        {
            "company": c.get("company", ""),
            "contact_email": c.get("contact_email", ""),
            "status": "drafted" if c.get("id", "") in processed else "pending",
        }
        for c in contacts
    ]


if __name__ == "__main__":
    stats = run_outreach()
    print(f"\nDrafted: {stats['drafted']} | Skipped: {stats['skipped']} | Errors: {len(stats['errors'])}")
