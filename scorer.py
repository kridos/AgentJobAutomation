"""
Advanced application quality scorer with detailed breakdowns.
Produces deterministic metadata for requirement match, specificity, conciseness, factual compliance, and tailoring depth.

Scoring Dimensions:
- requirements_match (40%): How well the application covers job posting keywords
- tailoring_depth (20%): How specifically the application addresses the role
- specificity (20%): Presence of metrics, results, and tech details  
- conciseness (10%): Optimal length (resume ~600-700 words, cover ~250-300 words)
- factual_compliance (10%): Freedom from fabricated facts
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

# Action verbs that signal strong, specific achievements
ACTION_VERBS = {
    "built", "developed", "designed", "implemented", "created", "engineered", "architected",
    "optimized", "accelerated", "improved", "reduced", "increased", "achieved", "delivered",
    "deployed", "automated", "integrated", "solved", "pioneered", "led", "managed", "contributed",
    "enhanced", "refactored", "scaled", "diagnosed", "debugged", "analyzed", "evaluated",
}

# Metrics patterns (numbers that show impact)
METRIC_PATTERN = re.compile(r"\b(\d+[\.]?\d*)\s*(%|x|times?|days?|hours?|seconds?|ms|gb|api|requests?|queries?|deployments?|users?|customers?|concurrent|rps|qps)\b", re.IGNORECASE)


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


def _score_requirement_match(combined_text: str, keywords: list[str]) -> tuple[float, list[str], list[str], dict]:
    """
    Score how well the application covers job posting keywords.
    Returns: (score, matched_keywords, missing_keywords, details_dict)
    """
    if not keywords:
        return 50.0, [], [], {"keyword_coverage": 0.0, "total_keywords": 0}

    lowered = combined_text.lower()
    matched = [kw for kw in keywords if kw in lowered]
    missing = [kw for kw in keywords if kw not in lowered]
    
    coverage = len(matched) / len(keywords)
    score = 100.0 * coverage
    
    return score, matched, missing, {
        "keyword_coverage": round(coverage * 100, 1),
        "matched": len(matched),
        "total_keywords": len(keywords),
    }


def _score_tailoring_depth(resume_md: str, job_description: str, listing: dict, keywords: list[str]) -> tuple[float, dict]:
    """
    Score how specifically the application addresses the role requirements.
    Checks for: role name mention, company name context, keyword depth, requirement specificity.
    Returns: (score, details_dict)
    """
    details = {
        "role_mention": 0,
        "company_context": 0,
        "keyword_depth": 0,
        "requirement_specificity": 0,
    }
    
    resume_lower = resume_md.lower()
    jd_lower = job_description.lower()
    
    # Role mention in resume (5-20 points)
    role_keywords = [w for w in listing.get("role", "").lower().split() if len(w) > 2]
    role_matches = sum(1 for rk in role_keywords if rk in resume_lower)
    details["role_mention"] = min(20, role_matches * 5)
    
    # Company mentioned or role-specific context (5-15 points)
    company_slug = listing.get("company", "").lower().replace(" ", "")[:5]
    if company_slug and company_slug in resume_lower.replace(" ", ""):
        details["company_context"] = 15
    elif any(jd_kw in resume_lower for jd_kw in jd_lower.split()[:20]):
        details["company_context"] = 8
    
    # Keyword depth (how many keywords appear multiple times - shows depth)
    keyword_frequency = sum(1 for kw in keywords if resume_lower.count(kw) >= 2)
    details["keyword_depth"] = min(30, keyword_frequency * 5)
    
    # Requirement specificity (does it address needs, not just list skills?)
    requirement_terms = {"need", "require", "must", "skill", "experience", "ability"}
    requirement_count = sum(1 for term in requirement_terms if term in resume_lower)
    details["requirement_specificity"] = min(25, requirement_count * 3)
    
    score = sum(details.values())
    return min(100.0, score), details


def _score_specificity(resume_md: str) -> tuple[float, dict]:
    """
    Score presence of metrics, results, and technical specificity.
    Returns: (score, details_dict)
    """
    bullet_lines = [line.strip() for line in resume_md.splitlines() if line.strip().startswith("-")]
    
    details = {
        "metric_lines": 0,
        "action_verb_lines": 0,
        "tech_detail_lines": 0,
        "total_bullets": len(bullet_lines),
    }
    
    if not bullet_lines:
        return 40.0, details

    for line in bullet_lines:
        line_lower = line.lower()
        
        # Has metrics (numbers with units)
        if METRIC_PATTERN.search(line):
            details["metric_lines"] += 1
        
        # Has action verbs
        if any(verb in line_lower for verb in ACTION_VERBS):
            details["action_verb_lines"] += 1
        
        # Has technical specifics
        if any(term in line_lower for term in KEYWORD_LEXICON):
            details["tech_detail_lines"] += 1

    specific_count = (
        details["metric_lines"] * 2 +  # Weight metrics more
        details["action_verb_lines"] * 1.5 +
        details["tech_detail_lines"] * 1
    )
    
    score = min(100.0, 100.0 * specific_count / (len(bullet_lines) * 3))
    return score, details


def _score_conciseness(resume_md: str, cover_md: str) -> tuple[float, dict]:
    """
    Score optimal length (resume ~600-700 words, cover ~250-300 words).
    Returns: (score, details_dict)
    """
    resume_words = len(resume_md.split())
    cover_words = len(cover_md.split())
    
    # Ideal ranges
    resume_ideal_min, resume_ideal_max = 550, 750
    cover_ideal_min, cover_ideal_max = 200, 350

    # Resume scoring
    if resume_ideal_min <= resume_words <= resume_ideal_max:
        resume_score = 100.0
    elif resume_words < resume_ideal_min:
        resume_score = max(40.0, 100.0 - (resume_ideal_min - resume_words) * 0.5)
    else:  # too long
        resume_score = max(40.0, 100.0 - (resume_words - resume_ideal_max) * 0.15)

    # Cover letter scoring
    if cover_ideal_min <= cover_words <= cover_ideal_max:
        cover_score = 100.0
    elif cover_words < cover_ideal_min:
        cover_score = max(40.0, 100.0 - (cover_ideal_min - cover_words) * 0.3)
    else:  # too long
        cover_score = max(40.0, 100.0 - (cover_words - cover_ideal_max) * 0.2)
    
    overall = (resume_score + cover_score) / 2.0
    
    details = {
        "resume_words": resume_words,
        "resume_score": round(resume_score, 1),
        "cover_words": cover_words,
        "cover_score": round(cover_score, 1),
    }
    
    return max(0.0, min(100.0, overall)), details


def score_application(
    *,
    resume_md: str,
    cover_md: str,
    job_description: str,
    listing: dict,
    validation_result: dict,
) -> dict:
    """
    Comprehensive scoring with detailed breakdowns.
    
    Weights:
    - requirements_match: 40%
    - tailoring_depth: 20%
    - specificity: 20%
    - conciseness: 10%
    - factual_compliance: 10%
    """
    resume_master = _load_resume_master()
    combined_text = f"{resume_md}\n\n{cover_md}"
    keywords = _extract_job_keywords(job_description, resume_master, listing)

    # Score each dimension
    requirement_score, matched, missing, req_details = _score_requirement_match(combined_text, keywords)
    tailoring_score, tailoring_details = _score_tailoring_depth(resume_md, job_description, listing, keywords)
    specificity_score, specificity_details = _score_specificity(resume_md)
    conciseness_score, conciseness_details = _score_conciseness(resume_md, cover_md)

    # Factual compliance
    violations = validation_result.get("violation_count", 0)
    factual_score = 100.0 if validation_result.get("passed", False) else max(0.0, 100.0 - violations * 20.0)

    # Weighted overall score
    overall = (
        0.40 * requirement_score
        + 0.20 * tailoring_score
        + 0.20 * specificity_score
        + 0.10 * conciseness_score
        + 0.10 * factual_score
    )

    # Determine quality tier
    if overall >= 85:
        tier = "A"  # Excellent - highly tailored and specific
    elif overall >= 75:
        tier = "B"  # Good - well tailored with solid specifics
    elif overall >= 65:
        tier = "C"  # Fair - basic match with some tailoring
    elif overall >= 50:
        tier = "D"  # Weak - needs significant improvement
    else:
        tier = "F"  # Poor - generic or missing key requirements

    return {
        "overall": round(overall, 1),
        "tier": tier,
        "scores": {
            "requirements_match": round(requirement_score, 1),
            "tailoring_depth": round(tailoring_score, 1),
            "specificity": round(specificity_score, 1),
            "conciseness": round(conciseness_score, 1),
            "factual_compliance": round(factual_score, 1),
        },
        "details": {
            "requirements_match": req_details,
            "tailoring_depth": tailoring_details,
            "specificity": specificity_details,
            "conciseness": conciseness_details,
            "validation": {
                "passed": validation_result.get("passed", False),
                "violation_count": violations,
                "categories": validation_result.get("categories", []),
            },
        },
        "matched_keywords": matched,
        "missing_keywords": missing,
        "keywords_extracted": keywords,
    }
