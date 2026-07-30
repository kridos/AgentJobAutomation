import pipeline


def test_auto_flush_noop_when_disabled(monkeypatch):
    calls = []
    monkeypatch.setattr("accomplishments.flush", lambda: calls.append(1))

    pipeline._auto_flush({})
    pipeline._auto_flush({"accomplishments": {"auto_flush_after_run": False}})

    assert calls == []


def test_auto_flush_calls_flush_when_enabled(monkeypatch):
    calls = []
    monkeypatch.setattr("accomplishments.flush", lambda: calls.append(1))

    pipeline._auto_flush({"accomplishments": {"auto_flush_after_run": True}})

    assert calls == [1]


def test_auto_flush_failure_is_non_fatal(monkeypatch, capsys):
    def _raise():
        raise RuntimeError("boom")

    monkeypatch.setattr("accomplishments.flush", _raise)

    pipeline._auto_flush({"accomplishments": {"auto_flush_after_run": True}})

    captured = capsys.readouterr()
    assert "Auto-flush failed (non-fatal): boom" in captured.err
