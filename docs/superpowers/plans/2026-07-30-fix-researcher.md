# Fix researcher.py Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `researcher.py`'s broken `browser-use` agentic path (calls `Agent(llm=None, ...)`, which fails) with a working, fully local DuckDuckGo-search-then-Ollama-summarize pipeline, keeping the exact same public `research()` signature and non-fatal contract.

**Architecture:** Two new small, independently-testable functions inside `researcher.py` — `_search_duckduckgo` (httpx fetch + text cleanup, reusing `job_fetcher._clean_html`) and `_summarize_research` (one call to `generator._call_ollama`) — replace the entire browser-use/playwright code path. `research()` orchestrates both synchronously; no `asyncio` needed anymore.

**Tech Stack:** Python 3.10+, `httpx` (already a dependency), reuses existing `job_fetcher.py` and `generator.py` functions — no new dependencies. Removes `browser-use` from the project.

## Global Constraints

- `research(company: str, role: str, timeout_seconds: int = 30) -> str` keeps its exact current signature and contract: never raises, returns `""` on any failure. `pipeline.py`'s call site (`pipeline.py:185`, `research(company, role, research_timeout)`) must need zero changes.
- No new runtime dependencies — this task only reuses `httpx` (already present), `job_fetcher._clean_html`, and `generator._call_ollama`.
- `browser-use` is removed from `pyproject.toml`'s `research` extra; `playwright` stays (still required by `job_fetcher.py`'s JS-fallback path).
- A search result under ~100 characters is treated as "no usable results" — skip the Ollama summarization call entirely rather than summarizing near-nothing.

---

### Task 1: Rewrite researcher.py + dependency cleanup

**Files:**
- Modify: `researcher.py` (full rewrite of the implementation, same public API)
- Modify: `pyproject.toml:14`
- Modify: `README.md:8`
- Test: `tests/test_researcher.py`

**Interfaces:**
- Consumes: `job_fetcher._clean_html(html: str) -> str` (existing, unchanged) and `generator._call_ollama(prompt: str, model: str = DEFAULT_MODEL, base_url: str = OLLAMA_BASE_URL, temperature: float = 0.7, max_tokens: int = 4096) -> str` (existing, unchanged).
- Produces: `researcher.research(company: str, role: str, timeout_seconds: int = 30) -> str` — identical signature to what already exists; no other task or file depends on the two new private helper functions below (they're internal to this rewrite).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_researcher.py`:

```python
import httpx
import pytest

import researcher


def test_search_duckduckgo_returns_cleaned_text_on_success(monkeypatch):
    class _FakeResponse:
        text = "<html><body><p>Acme builds widgets.</p></body></html>"
        def raise_for_status(self):
            pass

    def _fake_get(url, **kwargs):
        assert "duckduckgo.com" in url
        assert kwargs["params"] == {"q": "Acme SWE Intern"}
        return _FakeResponse()

    monkeypatch.setattr(httpx, "get", _fake_get)

    result = researcher._search_duckduckgo("Acme SWE Intern", timeout=10.0)

    assert "Acme builds widgets." in result


def test_search_duckduckgo_returns_empty_on_httpx_error(monkeypatch):
    def _fake_get(url, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", _fake_get)

    result = researcher._search_duckduckgo("Acme SWE Intern", timeout=10.0)

    assert result == ""


def test_summarize_research_returns_ollama_output_on_success(monkeypatch):
    monkeypatch.setattr(
        "researcher._call_ollama",
        lambda prompt, **kwargs: "- Uses Python and Go\n- Values ownership",
    )

    result = researcher._summarize_research("Acme", "SWE Intern", "raw search text here")

    assert result == "- Uses Python and Go\n- Values ownership"


def test_summarize_research_returns_empty_on_ollama_failure(monkeypatch):
    def _raise(prompt, **kwargs):
        raise RuntimeError("Ollama not running")

    monkeypatch.setattr("researcher._call_ollama", _raise)

    result = researcher._summarize_research("Acme", "SWE Intern", "raw search text here")

    assert result == ""


def test_research_returns_empty_when_search_fails(monkeypatch):
    monkeypatch.setattr(researcher, "_search_duckduckgo", lambda query, timeout: "")

    result = researcher.research("Acme", "SWE Intern", timeout_seconds=10)

    assert result == ""


def test_research_skips_summarize_when_search_result_too_short(monkeypatch):
    calls = []
    monkeypatch.setattr(researcher, "_search_duckduckgo", lambda query, timeout: "too short")
    monkeypatch.setattr(researcher, "_summarize_research", lambda *a, **k: calls.append(1) or "should not be called")

    result = researcher.research("Acme", "SWE Intern", timeout_seconds=10)

    assert result == ""
    assert calls == []


def test_research_returns_wrapped_summary_on_success(monkeypatch):
    monkeypatch.setattr(
        researcher, "_search_duckduckgo",
        lambda query, timeout: "a" * 200,  # long enough to pass the length guard
    )
    monkeypatch.setattr(
        researcher, "_summarize_research",
        lambda company, role, raw_text: "- Uses Python and Go\n- Values ownership",
    )

    result = researcher.research("Acme", "SWE Intern", timeout_seconds=10)

    assert result == "## Company Research: Acme\n- Uses Python and Go\n- Values ownership"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_researcher.py -v`
Expected: FAIL — `AttributeError: module 'researcher' has no attribute '_search_duckduckgo'` (and similar for the other new names)

- [ ] **Step 3: Replace researcher.py's contents**

Replace the entire contents of `researcher.py` with:

```python
"""
Web research on company + role: DuckDuckGo search + local Ollama summarization.
Fully local, no paid APIs, no browser automation.
Wrapped in try/except — failures are non-fatal.
Run standalone: python researcher.py "Stripe" "Software Engineering Intern"
"""

import sys

import httpx

from generator import _call_ollama
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


def _summarize_research(company: str, role: str, raw_text: str) -> str:
    """Summarize raw search-result text into markdown bullets via the local
    Ollama model. Returns '' if the Ollama call fails — never raises."""
    prompt = (
        f"Here are raw web search results about {company}, relevant to a "
        f"{role} internship application:\n\n{raw_text[:3000]}\n\n"
        f"Summarize into concise markdown bullet points covering: main tech "
        f"stack, recent projects or engineering blog posts, company culture "
        f"and values, and what they look for in interns. Only include what "
        f"the search results actually support — if something isn't covered, "
        f"leave it out rather than guessing or fabricating."
    )
    try:
        return _call_ollama(prompt).strip()
    except Exception as e:
        print(f"[researcher] Ollama summarization failed: {e}", file=sys.stderr)
        return ""


def research(company: str, role: str, timeout_seconds: int = 30) -> str:
    """
    Research company + role for internship context.
    Returns a markdown string, or empty string if research fails.
    Never raises — always safe to call.
    """
    query = f"{company} {role} internship tech stack engineering culture"
    raw_text = _search_duckduckgo(query, timeout=timeout_seconds)

    if len(raw_text) < _MIN_RESULT_LENGTH:
        return ""

    summary = _summarize_research(company, role, raw_text)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_researcher.py -v`
Expected: 7 tests PASS

- [ ] **Step 5: Remove browser-use from pyproject.toml**

In `pyproject.toml`, change line 14 from:

```toml
research = ["browser-use>=0.1.0", "playwright>=1.40.0"]
```

to:

```toml
research = ["playwright>=1.40.0"]
```

- [ ] **Step 6: Update README.md's research-extra comment**

In `README.md`, change line 8 from:

```
# dev extra is only needed to run the test suite; research extra pulls in browser-use/playwright
```

to:

```
# dev extra is only needed to run the test suite; research extra pulls in playwright (used as a fallback for JS-heavy job pages)
```

- [ ] **Step 7: Run the full test suite as a regression check**

Run: `pytest tests/ -v`
Expected: All tests PASS (no other file imports from `researcher.py`'s removed browser-use code path — `pipeline.py` only calls the unchanged `research(company, role, research_timeout)` signature)

- [ ] **Step 8: Commit**

```bash
git add researcher.py pyproject.toml README.md tests/test_researcher.py
git commit -m "fix: replace broken browser-use research path with DuckDuckGo search + Ollama summarization"
```

---

## Self-Review Notes

- **Spec coverage:** Architecture (search step + summarize step, synchronous, no asyncio) → Step 3. Components (`_search_duckduckgo`, `_summarize_research`, `research()` orchestration) → Step 3. Error handling (each step's independent failure guard, the ~100-char length threshold) → Step 3's `_MIN_RESULT_LENGTH` constant and the try/except blocks in both helper functions. Cleanup (pyproject.toml, README.md) → Steps 5-6. Testing (all 5 bullet points from the spec's Testing section) → Step 1's 7 tests map directly: search success/failure, summarize success/failure, research empty-on-search-failure, research skips-summarize-when-too-short (with a call-count assertion proving `_summarize_research` was never invoked), research wrapped-success-output.
- **Placeholder scan:** none found — every step has complete code.
- **Type consistency:** `research(company: str, role: str, timeout_seconds: int = 30) -> str` is unchanged from the existing signature (verified against the current file read during brainstorming) — `pipeline.py:185`'s call site (`research(company, role, research_timeout)`) requires no modification. `_search_duckduckgo(query: str, timeout: float) -> str` and `_summarize_research(company: str, role: str, raw_text: str) -> str` are used identically in both the test file and the implementation.
- Single-task plan: this is one cohesive rewrite of one file (plus two one-line touch-ups it directly requires) with one clear independently-testable deliverable — splitting further would add reviewer overhead without a meaningful separate-approval boundary, consistent with Task Right-Sizing guidance.
