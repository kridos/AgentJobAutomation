"""
Lightweight application quality scorer.
Produces deterministic metadata for requirement match, specificity,
conciseness, and factual compliance.
"""

import re
from pathlib import Path


CONTEXT_DIR = Path(__file__).parent / "context"
STOPWORDS = {
    "about", "across", "after", "also", "an", "and", "any", "are", "build", "building", "can",
    "company", "engineer", "engineering", "for", "from", "have", "intern", "internship", "into",
    "its", "job", "more", "our", "role", "team", "that", "the", "their", "this", "through",
    "using", "will", "with", "you", "your",
}
KEYWORD_LEXICON = {
    "python", "java", "typescript", "javascript", "react", "next.js", "aws", "docker", "sql",
    "rest", "api", "backend", "frontend", "full-stack", "fullstack", "distributed", "systems",
    "machine learning", "ml", "ai", "pytorch", "opencv", "robotics", "ros 2", "fastapi", "flask",
    "c++", "c", "node.js", "go", "rust", "data science", "statistics", "cloud", "testing", "ci/cd",
}
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.#/-]{2,}")


def _load_resume_master() -> str:
    path = CONTEXT_DIR / "resume_master.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _normalize(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip().lower())


def _extract_job_keywords(job_description: str, resume_master: str, listing: dict) -> list[str]:
    keywords = []
    lowered_jd = job_description.lower()
    for term in sorted(KEYWORD_LEXICON):
        if term in lowered_jd:
            keywords.append(term)

    allowed_resume_terms = {_normalize(term) for term in KEYWORD_LEXICON if term in resume_master.lower()}

    if len(keywords) < 5:
        seen = set(keywords)
        for match in WORD_RE.finditer(job_description):
            token = _normalize(match.group(0))
            if token in STOPWORDS or len(token) < 4:
                continue
            if token in seen:
                continue
            seen.add(token)
            keywords.append(token)
            if len(keywords) >= 12:
                break

    if allowed_resume_terms:
        filtered = [kw for kw in keywords if _normalize(kw) in allowed_resume_terms]
        if filtered:
            keywords = filtered

    if not keywords:
        for seed in (listing.get("role", ""), listing.get("company", "")):
            token = _normalize(seed)
            if token and token not in STOPWORDS:
                keywords.append(token)

    return keywords[:12]


def _score_requirement_match(combined_text: str, keywords: list[str]) -> tuple[float, list[str], list[str]]:
    if not keywords:
        return 50.0, [], []

    lowered = combined_text.lower()
    matched = [kw for kw in keywords if kw in lowered]
    missing = [kw for kw in keywords if kw not in lowered]
    score = 100.0 * len(matched) / len(keywords)
    return score, matched, missing


def _score_specificity(resume_md: str) -> float:
    bullet_lines = [line.strip() for line in resume_md.splitlines() if line.strip().startswith("-")]
    if not bullet_lines:
        return 40.0

    specific_count = 0
    for line in bullet_lines:
        has_number = bool(re.search(r"\d", line))
        has_tech = any(term in line.lower() for term in KEYWORD_LEXICON)
        if has_number or has_tech:
            specific_count += 1

    return min(100.0, 100.0 * specific_count / len(bullet_lines))


def _score_conciseness(resume_md: str, cover_md: str) -> float:
    resume_words = len(resume_md.split())
    cover_words = len(cover_md.split())

    resume_score = 100.0 if resume_words <= 700 else max(40.0, 100.0 - (resume_words - 700) * 0.25)
    cover_delta = abs(300 - cover_words)
    cover_score = max(40.0, 100.0 - cover_delta * 0.35)
    return max(0.0, min(100.0, (resume_score + cover_score) / 2.0))


def score_application(
    *,
    resume_md: str,
    cover_md: str,
    job_description: str,
    listing: dict,
    validation_result: dict,
) -> dict:
    resume_master = _load_resume_master()
    combined_text = f"{resume_md}\n\n{cover_md}"
    keywords = _extract_job_keywords(job_description, resume_master, listing)

    requirement_score, matched, missing = _score_requirement_match(combined_text, keywords)
    specificity_score = _score_specificity(resume_md)
    conciseness_score = _score_conciseness(resume_md, cover_md)

    violations = validation_result.get("violation_count", 0)
    factual_score = 100.0 if validation_result.get("passed", False) else max(0.0, 100.0 - violations * 20.0)

    overall = (
        0.40 * requirement_score
        + 0.25 * specificity_score
        + 0.15 * conciseness_score
        + 0.20 * factual_score
    )

    return {
        "overall": round(overall, 1),
        "requirements": round(requirement_score, 1),
        "specificity": round(specificity_score, 1),
        "conciseness": round(conciseness_score, 1),
        "factual_compliance": round(factual_score, 1),
        "matched_keywords": matched,
        "missing_keywords": missing,
    }
