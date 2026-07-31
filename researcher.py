"""
Web research on company + role: DuckDuckGo search + local Ollama summarization.
Fully local, no paid APIs, no browser automation.
Wrapped in try/except — failures are non-fatal.
Run standalone: python researcher.py "Stripe" "Software Engineering Intern"
"""

import sys

import httpx

from generator import _call_ollama, DEFAULT_MODEL, OLLAMA_BASE_URL
from job_fetcher import _clean_html

_MIN_RESULT_LENGTH = 100


def _search_duckduckgo(query: str, timeout: float) -> str:
    """Fetch DuckDuckGo's HTML-only search results for `query`, cleaned of tags.
    Returns '' on any failure — never raises."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        resp = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return _clean_html(resp.text)
    except Exception as e:
        print(f"[researcher] DuckDuckGo search failed: {e}", file=sys.stderr)
        return ""


def _summarize_research(company: str, role: str, raw_text: str, model: str, base_url: str) -> str:
    """Summarize raw search-result text into markdown bullets via the local
    Ollama model. Returns '' if the Ollama call fails — never raises."""
    prompt = (
        f"Here are raw web search results about {company}, relevant to a "
        f"{role} internship application:\n\n{raw_text[:5000]}\n\n"
        f"Summarize into concise markdown bullet points covering: main tech "
        f"stack, recent projects or engineering blog posts, company culture "
        f"and values, and what they look for in interns. Only include what "
        f"the search results actually support — if something isn't covered, "
        f"leave it out rather than guessing or fabricating."
    )
    try:
        return _call_ollama(prompt, model=model, base_url=base_url, temperature=0.2).strip()
    except Exception as e:
        print(f"[researcher] Ollama summarization failed: {e}", file=sys.stderr)
        return ""


def research(
    company: str,
    role: str,
    timeout_seconds: int = 30,
    model: str = DEFAULT_MODEL,
    base_url: str = OLLAMA_BASE_URL,
) -> str:
    """
    Research company + role for internship context.
    Returns a markdown string, or empty string if research fails.
    Never raises — always safe to call.
    """
    query = f"{company} {role} internship tech stack engineering culture"
    raw_text = _search_duckduckgo(query, timeout=timeout_seconds)

    if len(raw_text) < _MIN_RESULT_LENGTH:
        return ""

    summary = _summarize_research(company, role, raw_text, model, base_url)
    if not summary:
        return ""

    return f"## Company Research: {company}\n{summary}"


if __name__ == "__main__":
    company = sys.argv[1] if len(sys.argv) > 1 else "Stripe"
    role = sys.argv[2] if len(sys.argv) > 2 else "Software Engineering Intern"
    print(f"Researching {company} for role: {role}\n")
    result = research(company, role)
    if result:
        print(result)
    else:
        print("No research results (DuckDuckGo search or Ollama may be unavailable).")
