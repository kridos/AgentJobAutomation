# Fix researcher.py — Design Spec

## Context

`researcher.py` is currently broken: `_research_async` constructs a
`browser_use.Agent(llm=None, ...)`, and browser-use requires a real LLM
object to drive its agentic browsing decisions. Calling it with `llm=None`
fails, which is silently swallowed by the outer `try/except` in
`research()`, so every research call today falls through to the
Google-search-scrape Playwright fallback — itself fragile (Google
aggressively blocks headless scraping) and low quality (it dumps raw,
untruncated-by-relevance page text rather than anything summarized).

This is the next item on the roadmap set in
`docs/superpowers/specs/2026-07-29-automator-cli-design.md`: several
planned features (job research quality, cold-email outreach, interview
prep) will want to reuse a working research capability, so it needs to
work before they're built on top of it.

## Goal

A working, fully local `research(company: str, role: str, timeout_seconds:
int = 30) -> str` that returns markdown-formatted research on a company —
tech stack, recent projects, culture, what they look for in interns — with
the exact same public signature and "never raises, returns `''` on
failure" contract it already has, so `pipeline.py`'s call site needs zero
changes.

## Non-goals

- No agentic multi-step browsing (browser-use or otherwise) in this pass.
  Raised during brainstorming as a future upgrade — see Future Work below.
- No new paid API dependency — stays consistent with the project's
  "zero paid APIs, local Ollama" approach.
- No change to `pipeline.py`, `config.yaml`'s `research:` section, or any
  other caller — this is an internal rewrite of `researcher.py` only.

## Architecture

Replace the broken `browser-use` agentic path with a deterministic
two-step pipeline, entirely synchronous (no `asyncio` needed):

1. **Search** — query DuckDuckGo's HTML-only search endpoint
   (`https://html.duckduckgo.com/html/`) via plain `httpx.get`. This
   endpoint is server-rendered HTML with no JavaScript requirement, and is
   far less aggressive about blocking headless/bot traffic than Google's
   search results page (the previous fallback's target).
2. **Summarize** — feed the cleaned search-result text to the local Ollama
   model via `generator._call_ollama` (already exists, already used for
   resume/cover-letter generation), asking for a concise markdown summary
   of tech stack, recent projects/blog mentions, culture/values, and what
   the company looks for in interns.

This drops the `browser-use` dependency from the project rather than
adding anything, and reuses two patterns already established elsewhere in
the codebase: `job_fetcher.py`'s httpx-with-realistic-headers fetch style,
and `generator.py`'s Ollama-calling helper.

## Components

All within `researcher.py`:

```python
def _search_duckduckgo(query: str, timeout: float) -> str:
    """Fetch DuckDuckGo's HTML search results for `query`, cleaned of tags.
    Returns '' on any failure (network error, non-200 response, etc.)."""

def _summarize_research(company: str, role: str, raw_text: str) -> str:
    """Summarize raw search-result text into markdown bullets via the
    local Ollama model. Returns '' if the Ollama call fails."""

def research(company: str, role: str, timeout_seconds: int = 30) -> str:
    """Unchanged public signature and contract: never raises, returns ''
    on any failure. Orchestrates _search_duckduckgo then
    _summarize_research, wraps a non-empty result in the existing
    '## Company Research: {company}' header."""
```

`_search_duckduckgo` reuses `job_fetcher._clean_html` for HTML-to-text
cleanup rather than duplicating that regex logic, and builds its request
with the same realistic `User-Agent` header `job_fetcher.fetch_via_httpx`
already sends.

`_summarize_research` imports `generator._call_ollama` and calls it with a
prompt built from the raw search text, explicitly instructing the model
not to fabricate details beyond what the raw text actually supports — the
same "don't hallucinate" posture the rest of the pipeline already takes
seriously (`factual_validator.py`).

## Error handling

Each step guards independently, preserving `research()`'s existing
"optional, never breaks the pipeline" contract:

- `_search_duckduckgo` catches any `httpx` exception and returns `""`.
- `research()` checks the search result length before bothering to
  summarize: if the cleaned text is under ~100 characters (effectively "no
  usable results" — a captcha page, a block page, or a genuinely empty
  result set), it skips the Ollama call entirely and returns `""` rather
  than spending an LLM call summarizing near-nothing.
- `_summarize_research` catches any exception from `_call_ollama` (Ollama
  not running, connection refused, etc.) and returns `""`.
- `research()` itself never raises under any of these conditions — every
  failure path returns `""`, matching today's behavior exactly.

`timeout_seconds` governs the `_search_duckduckgo` httpx request's
timeout. The Ollama summarization call uses `generator._call_ollama`'s
own existing internal timeout (120 seconds, unchanged) since summarization
latency is bounded by the local Ollama server's own responsiveness, not
something this caller needs to separately tune.

## Cleanup

- `pyproject.toml`'s `[project.optional-dependencies].research` drops
  `browser-use>=0.1.0`, keeping only `playwright>=1.40.0` (still required
  by `job_fetcher.py`'s JS-rendering fallback path — unrelated to this
  change, not removed).
- `README.md`'s comment referencing the `research` extra
  (`# dev extra is only needed to run the test suite; research extra
  pulls in browser-use/playwright`) updates to drop the `browser-use`
  mention.

## Testing

`tests/test_researcher.py`:
- `_search_duckduckgo` returns cleaned text on a mocked successful httpx
  response, and `""` on a mocked httpx exception — no real network call.
- `_summarize_research` returns the mocked `_call_ollama` return value on
  success, and `""` when `_call_ollama` is mocked to raise — no real
  Ollama server required.
- `research()` returns `""` when `_search_duckduckgo` is mocked to return
  `""` (search failure path).
- `research()` returns `""` when `_search_duckduckgo` is mocked to return
  a short string under the length threshold (too-short-to-summarize path),
  without calling `_summarize_research` (verified via a mock call-count
  assertion).
- `research()` returns the expected `"## Company Research: {company}\n..."`
  wrapped output when both steps succeed (both mocked).

## Future work (explicitly out of scope here)

An optional upgrade path where the research step can click through to a
company's actual careers page or engineering blog via agentic browsing
(e.g. browser-use wired to a real local LLM), falling back to today's
search-and-summarize approach if that doesn't work or isn't configured.
Raised during brainstorming as a good next step once this simpler baseline
is solid and proven reliable.
