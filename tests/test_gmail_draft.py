import gmail_reader


def test_resolve_draft_tool_name_picks_matching_candidate(monkeypatch):
    gmail_reader._TOOL_NAME_CACHE.clear()
    monkeypatch.setattr(gmail_reader, "_mcp_list_tools", lambda mcp_url: ["search_threads", "gmail_create_draft", "other_tool"])

    result = gmail_reader._resolve_draft_tool_name("https://fake-mcp", "")

    assert result == "gmail_create_draft"


def test_resolve_draft_tool_name_falls_back_to_substring_match(monkeypatch):
    gmail_reader._TOOL_NAME_CACHE.clear()
    monkeypatch.setattr(gmail_reader, "_mcp_list_tools", lambda mcp_url: ["search_threads", "compose_draft_message"])

    result = gmail_reader._resolve_draft_tool_name("https://fake-mcp", "")

    assert result == "compose_draft_message"


def test_resolve_draft_tool_name_falls_back_to_default_when_list_fails(monkeypatch):
    gmail_reader._TOOL_NAME_CACHE.clear()

    def _raise(mcp_url):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(gmail_reader, "_mcp_list_tools", _raise)

    result = gmail_reader._resolve_draft_tool_name("https://fake-mcp", "")

    assert result == gmail_reader.DEFAULT_DRAFT_TOOL


def test_resolve_draft_tool_name_excludes_unsafe_substring_match(monkeypatch):
    gmail_reader._TOOL_NAME_CACHE.clear()
    monkeypatch.setattr(gmail_reader, "_mcp_list_tools", lambda mcp_url: ["send_draft"])

    result = gmail_reader._resolve_draft_tool_name("https://fake-mcp", "")

    assert result != "send_draft"
    assert result == gmail_reader.DEFAULT_DRAFT_TOOL


def test_create_draft_returns_true_on_success(monkeypatch):
    gmail_reader._TOOL_NAME_CACHE.clear()
    monkeypatch.setattr(gmail_reader, "_mcp_list_tools", lambda mcp_url: ["gmail_create_draft"])
    monkeypatch.setattr(gmail_reader, "_mcp_call", lambda tool, params, mcp_url: {"id": "draft-1"})

    result = gmail_reader.create_draft("jane@acme.com", "Subject", "Body text", "https://fake-mcp")

    assert result is True


def test_create_draft_returns_false_on_failure(monkeypatch):
    gmail_reader._TOOL_NAME_CACHE.clear()
    monkeypatch.setattr(gmail_reader, "_mcp_list_tools", lambda mcp_url: ["gmail_create_draft"])

    def _raise(tool, params, mcp_url):
        raise RuntimeError("MCP error")

    monkeypatch.setattr(gmail_reader, "_mcp_call", _raise)

    result = gmail_reader.create_draft("jane@acme.com", "Subject", "Body text", "https://fake-mcp")

    assert result is False
