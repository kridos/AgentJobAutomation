import httpx

import generator


def test_call_ollama_uses_native_api_with_explicit_num_ctx(monkeypatch):
    captured_request = {}

    def fake_post(url, json, timeout):
        captured_request["url"] = url
        captured_request["json"] = json
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "hello"}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(generator.httpx, "post", fake_post)

    result = generator._call_ollama("a prompt", model="qwen3:14b", temperature=0.3, max_tokens=2048)

    assert result == "hello"
    assert captured_request["url"] == f"{generator.OLLAMA_BASE_URL}/api/chat"
    options = captured_request["json"]["options"]
    assert options["num_ctx"] == generator.DEFAULT_NUM_CTX
    assert options["num_predict"] == 2048
    assert options["temperature"] == 0.3


def test_load_context_files_includes_new_keys_defaulting_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(generator, "CONTEXT_DIR", tmp_path / "context")

    loaded = generator._load_context_files()

    assert loaded["recent_updates"] == ""
    assert loaded["accomplishments"] == ""
    # No missing-file warning for these two optional files
    captured = capsys.readouterr()
    assert "recent_updates.md" not in captured.err
    assert "accomplishments.md" not in captured.err


def test_build_resume_prompt_includes_accomplishments_when_present():
    context = {
        "resume_master": "# Test Resume\n",
        "voice": "",
        "preferences": "",
        "recent_updates": "- 2026-07-29 Pending thing\n",
        "accomplishments": "- 2026-06-01 Permanent thing\n",
    }
    listing = {"company": "Acme", "role": "SWE Intern", "location": "Remote", "link": ""}

    prompt = generator._build_resume_prompt(context, listing)

    assert "## Recent Accomplishments" in prompt
    assert "Permanent thing" in prompt
    assert "## Pending Updates" in prompt
    assert "Pending thing" in prompt


def test_build_resume_prompt_omits_blocks_when_empty():
    context = {
        "resume_master": "# Test Resume\n",
        "voice": "",
        "preferences": "",
        "recent_updates": "",
        "accomplishments": "",
    }
    listing = {"company": "Acme", "role": "SWE Intern", "location": "Remote", "link": ""}

    prompt = generator._build_resume_prompt(context, listing)

    assert "## Recent Accomplishments" not in prompt
    assert "## Pending Updates" not in prompt
