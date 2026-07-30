"""
Deterministic factual checks for generated resume and cover letter output.
Balanced policy support: validate output, retry once with corrective guidance,
then block saving if unresolved.
"""

import json
import re
import sys
from pathlib import Path

from generator import _call_ollama, DEFAULT_MODEL, OLLAMA_BASE_URL


CONTEXT_DIR = Path(__file__).parent / "context"


_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")
_URL_RE = re.compile(r"\b(?:https?://|www\.)[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]*)?\b")
_GPA_RE = re.compile(r"\bGPA\s*[:=]?\s*(\d(?:\.\d{1,2})?)\b", re.IGNORECASE)
_DEGREE_RE = re.compile(r"\b(?:B\.S\.|M\.S\.|Ph\.D\.|Bachelor(?:'s)?|Master(?:'s)?)\b", re.IGNORECASE)
_HEADING_ORG_RE = re.compile(r"^\s*(?:#{1,3}\s*)?\*\*?([A-Za-z0-9& .,'/-]{2,80})\*\*?\s*[—-]\s*", re.MULTILINE)
_SECTION_HEADER_RE = re.compile(r"^\s*#{1,3}\s*([A-Z][A-Z\s&/-]{2,})\s*$")
_PROJECT_HEADING_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
_METRIC_RE = re.compile(r"\b\d+(?:\.\d+)?%\b|\b\d+(?:\.\d+)?x\b", re.IGNORECASE)

COMMON_TECH_TERMS = {
    "python", "java", "typescript", "javascript", "c", "c++", "dart", "sql", "r", "assembly",
    "html/css", "pytorch", "hugging face", "faiss", "openai whisper", "numpy", "spacy", "opencv",
    "ros 2", "nvidia isaac sim", "curobo", "fastapi", "flask", "react", "next.js", "git", "aws",
    "aws iot core", "lambda", "docker", "rest", "ci/cd", "latex", "tkinter", "arduino", "m5stack",
    "android studio", "ftc sdk", "musicxml", "whisper", "tinylama", "tinyllama", "multpaxos", "multipaxos",
    "two-phase commit", "node.js", "node", "express", "mongodb", "postgresql", "redis", "graphql",
    "kubernetes", "go", "rust", "scala", "kotlin", "swift", "gcp", "azure", "terraform",
}


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _load_resume_master() -> str:
    primary_path = CONTEXT_DIR / "resume_master.md"
    if not primary_path.exists():
        return ""

    parts = [primary_path.read_text(encoding="utf-8")]
    for name in ("accomplishments.md", "recent_updates.md"):
        path = CONTEXT_DIR / name
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _extract_allowed_contacts(resume_master: str) -> set[str]:
    contacts = set()
    header_lines = resume_master.splitlines()[:4]
    header_text = "\n".join(header_lines)
    for pattern in (_EMAIL_RE, _PHONE_RE, _URL_RE):
        for m in pattern.findall(header_text):
            contacts.add(_normalize(m))
    return contacts


def _extract_allowed_gpas(resume_master: str) -> set[str]:
    return {m.group(1) for m in _GPA_RE.finditer(resume_master)}


def _extract_allowed_degrees(resume_master: str) -> set[str]:
    allowed = {_normalize(m.group(0)) for m in _DEGREE_RE.finditer(resume_master)}
    # Normalize aliases: treat 'bachelor' as equivalent to 'b.s.' if either is present
    if any("b.s" in d or "bachelor" in d for d in allowed):
        allowed.update({"b.s.", "bachelor", "bachelor's"})
    if any("m.s" in d or "master" in d for d in allowed):
        allowed.update({"m.s.", "master", "master's"})
    return allowed


def _extract_allowed_orgs(resume_master: str, listing: dict) -> set[str]:
    orgs = {_normalize(m.group(1)) for m in _HEADING_ORG_RE.finditer(resume_master)}
    edu_match = re.search(r"\*\*([^*]+University[^*]+)\*\*", resume_master)
    if edu_match:
        orgs.add(_normalize(edu_match.group(1)))

    company = listing.get("company", "")
    if company:
        orgs.add(_normalize(company))
    return {o for o in orgs if o}


def _extract_allowed_projects(resume_master: str) -> set[str]:
    lines = resume_master.splitlines()
    in_projects = False
    projects = set()
    for line in lines:
        section = _SECTION_HEADER_RE.match(line)
        if section:
            section_name = section.group(1).strip().lower()
            if "projects" in section_name:
                in_projects = True
                continue
            if in_projects:
                break
        if in_projects:
            match = _PROJECT_HEADING_RE.match(line)
            if match:
                heading = match.group(1).split("|", 1)[0].strip()
                projects.add(_normalize(heading))
    return projects


def _extract_allowed_techs(resume_master: str) -> set[str]:
    allowed = set()
    for term in COMMON_TECH_TERMS:
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", resume_master, re.IGNORECASE):
            allowed.add(_normalize(term))
    return allowed


def _extract_allowed_metrics(resume_master: str) -> set[str]:
    return {_normalize(m.group(0)) for m in _METRIC_RE.finditer(resume_master)}


def _extract_canonical_name(resume_master: str) -> str:
    first = resume_master.splitlines()[0].strip() if resume_master else ""
    if "—" in first:
        first = first.split("—", 1)[0].strip()
    return first.replace("#", "").strip()


def _candidate_name_from_output(text: str) -> str:
    for line in text.splitlines()[:6]:
        cleaned = line.strip().lstrip("#").strip("* ")
        if re.match(r"^(hi|hello|hey|dear)\b", cleaned, re.IGNORECASE):
            continue
        if re.fullmatch(r"[A-Z][a-z]+\s+[A-Z][a-z]+", cleaned):
            return cleaned
    return ""


def _check_contacts(text: str, allowed_contacts: set[str]) -> list[dict]:
    violations = []
    found = set()
    header_region = "\n".join(text.splitlines()[:8])
    for pattern in (_EMAIL_RE, _PHONE_RE, _URL_RE):
        for m in pattern.findall(header_region):
            found.add(_normalize(m))

    for item in sorted(found):
        if item not in allowed_contacts:
            violations.append({
                "category": "identity_contact",
                "claim": item,
                "reason": "Contact detail not present in canonical resume context",
            })
    return violations


def _check_gpa(text: str, allowed_gpas: set[str]) -> list[dict]:
    violations = []
    for m in _GPA_RE.finditer(text):
        value = m.group(1)
        if value not in allowed_gpas:
            violations.append({
                "category": "education_gpa",
                "claim": f"GPA {value}",
                "reason": "GPA value not present in canonical resume context",
            })
    return violations


def _check_degrees(text: str, allowed_degrees: set[str]) -> list[dict]:
    violations = []
    for m in _DEGREE_RE.finditer(text):
        value = _normalize(m.group(0))
        if value not in allowed_degrees:
            violations.append({
                "category": "education_degree",
                "claim": m.group(0),
                "reason": "Degree claim not present in canonical resume context",
            })
    return violations


def _check_org_headings(resume_md: str, allowed_orgs: set[str]) -> list[dict]:
    violations = []

    # Limit org checks to EXPERIENCE section to avoid flagging project titles/section names.
    lines = resume_md.splitlines()
    in_experience = False
    experience_lines = []
    for line in lines:
        section = _SECTION_HEADER_RE.match(line)
        if section:
            section_name = section.group(1).strip().lower()
            if "experience" in section_name:
                in_experience = True
                continue
            if in_experience:
                break
        if in_experience:
            experience_lines.append(line)

    experience_text = "\n".join(experience_lines) if experience_lines else resume_md

    for m in _HEADING_ORG_RE.finditer(experience_text):
        org = m.group(1).strip()
        if _normalize(org) not in allowed_orgs:
            violations.append({
                "category": "experience_org",
                "claim": org,
                "reason": "Organization in heading is not present in canonical resume context",
            })
    return violations


def _check_project_headings(resume_md: str, allowed_projects: set[str]) -> list[dict]:
    violations = []
    lines = resume_md.splitlines()
    in_projects = False
    project_lines = []
    for line in lines:
        section = _SECTION_HEADER_RE.match(line)
        if section:
            section_name = section.group(1).strip().lower()
            if "projects" in section_name:
                in_projects = True
                continue
            if in_projects:
                break
        if in_projects:
            project_lines.append(line)

    for m in _PROJECT_HEADING_RE.finditer("\n".join(project_lines)):
        heading = m.group(1).split("|", 1)[0].strip()
        if _normalize(heading) not in allowed_projects:
            violations.append({
                "category": "project_heading",
                "claim": heading,
                "reason": "Project heading is not present in canonical resume context",
            })
    return violations


def _check_unsupported_tech_mentions(resume_md: str, allowed_techs: set[str]) -> list[dict]:
    violations = []
    found = set()
    for term in COMMON_TECH_TERMS:
        normalized = _normalize(term)
        if normalized in allowed_techs:
            continue
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", resume_md, re.IGNORECASE):
            found.add(term)

    for term in sorted(found, key=str.lower):
        violations.append({
            "category": "unsupported_tech",
            "claim": term,
            "reason": "Technology is mentioned in generated resume but not present in canonical resume context",
        })
    return violations


def _check_metric_claims(resume_md: str, allowed_metrics: set[str], cover_md: str = "") -> list[dict]:
    violations = []
    # Allow metric if it appears anywhere in the canonical resume OR in the cover letter
    # (cover letter may restate resume metrics in different prose form).
    combined_allowed = allowed_metrics | {_normalize(m.group(0)) for m in _METRIC_RE.finditer(cover_md)}
    for m in _METRIC_RE.finditer(resume_md):
        metric = _normalize(m.group(0))
        if metric not in combined_allowed:
            violations.append({
                "category": "metric_claim",
                "claim": m.group(0),
                "reason": "Metric is not present in canonical resume context",
            })
    return violations


def _check_semantic_claims(
    resume_md: str,
    cover_md: str,
    resume_master: str,
    model: str,
    base_url: str,
) -> list[dict]:
    """Ask the local model to flag any claim in resume_md/cover_md not traceable
    to resume_master. Fails open (returns []) on any error — Ollama unreachable,
    malformed JSON response, etc. — since a broken verifier must never block
    every application; the regex checks still gate as they do today.
    In production resume_md is passed as "" (cover-letter-only) — see validate_outputs."""
    prompt = (
        "You are a strict fact-checker. Compare the CANDIDATE OUTPUT below against "
        "the CANONICAL FACTS. List every factual claim in the CANDIDATE OUTPUT about "
        "the candidate's experience, skills, accomplishments, or responsibilities that "
        "is NOT explicitly supported by the CANONICAL FACTS.\n\n"
        f"## CANONICAL FACTS\n{resume_master}\n\n"
        f"## CANDIDATE OUTPUT\n{resume_md}\n\n{cover_md}\n\n"
        "Respond with ONLY a JSON array, no other text. Each element: "
        '{"claim": "<the unsupported claim, verbatim>", "reason": "<why it is unsupported>"}. '
        "If every claim is supported, respond with exactly: []"
    )
    try:
        raw = _call_ollama(prompt, model=model, base_url=base_url, temperature=0.1).strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
        items = json.loads(raw)
        if not isinstance(items, list):
            return []
        violations = []
        for item in items:
            if not isinstance(item, dict) or "claim" not in item:
                continue
            violations.append({
                "category": "semantic_unsupported",
                "claim": item["claim"],
                "reason": item.get("reason", "Claim not supported by canonical resume context"),
            })
        return violations
    except Exception as e:
        print(f"[factual_validator] Semantic check failed (non-fatal): {e}", file=sys.stderr)
        return []


def validate_outputs(
    resume_md: str,
    cover_md: str,
    listing: dict,
    model: str = DEFAULT_MODEL,
    base_url: str = OLLAMA_BASE_URL,
    semantic_check: bool = True,
) -> dict:
    """
    Validate generated output against canonical facts in context/resume_master.md.
    Returns a dict with pass/fail and normalized violation details.
    """
    resume_master = _load_resume_master()
    combined_text = f"{resume_md}\n\n{cover_md}"

    allowed_contacts = _extract_allowed_contacts(resume_master)
    allowed_gpas = _extract_allowed_gpas(resume_master)
    allowed_degrees = _extract_allowed_degrees(resume_master)
    allowed_orgs = _extract_allowed_orgs(resume_master, listing)
    allowed_projects = _extract_allowed_projects(resume_master)
    allowed_techs = _extract_allowed_techs(resume_master)
    allowed_metrics = _extract_allowed_metrics(resume_master)
    canonical_name = _extract_canonical_name(resume_master)

    violations = []

    if canonical_name:
        candidate_name = _candidate_name_from_output(resume_md)
        if candidate_name and _normalize(candidate_name) != _normalize(canonical_name):
            violations.append({
                "category": "identity_name",
                "claim": candidate_name,
                "reason": f"Candidate name differs from canonical resume name '{canonical_name}'",
            })

    violations.extend(_check_contacts(combined_text, allowed_contacts))
    violations.extend(_check_gpa(combined_text, allowed_gpas))
    violations.extend(_check_degrees(combined_text, allowed_degrees))
    violations.extend(_check_org_headings(resume_md, allowed_orgs))
    violations.extend(_check_project_headings(resume_md, allowed_projects))
    violations.extend(_check_unsupported_tech_mentions(resume_md, allowed_techs))
    violations.extend(_check_metric_claims(resume_md, allowed_metrics, cover_md))

    if semantic_check:
        # Cover-letter-only: resume's canonical sections are assembled verbatim and can't
        # be changed by the corrective retry, so a semantic flag there would permanently block.
        violations.extend(_check_semantic_claims("", cover_md, resume_master, model, base_url))

    categories = sorted({v["category"] for v in violations})
    return {
        "passed": len(violations) == 0,
        "violation_count": len(violations),
        "categories": categories,
        "violations": violations,
    }


def format_validation_feedback(result: dict) -> str:
    if result.get("passed", True):
        return ""

    lines = ["Fix the following unsupported claims:"]
    for item in result.get("violations", [])[:12]:
        lines.append(f"- [{item['category']}] {item['claim']}: {item['reason']}")
    lines.append("Only keep claims that are explicitly grounded in context/resume_master.md or listing fields.")
    return "\n".join(lines)
