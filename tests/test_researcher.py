import httpx

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
