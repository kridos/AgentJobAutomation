from pathlib import Path

import pytest

from accomplishments import log_entry


def test_log_entry_writes_dated_line_with_tags(tmp_path, monkeypatch):
    monkeypatch.setattr("accomplishments.date", _FixedDate)
    log_entry("Shipped RGB-D fusion milestone", tags="robotics, ai-ml", base_dir=tmp_path)

    content = (tmp_path / "context" / "recent_updates.md").read_text(encoding="utf-8")
    assert content == "- 2026-07-29 [tags: robotics, ai-ml] Shipped RGB-D fusion milestone\n"


def test_log_entry_writes_dated_line_without_tags(tmp_path, monkeypatch):
    monkeypatch.setattr("accomplishments.date", _FixedDate)
    log_entry("Migrated auth service to JWT", base_dir=tmp_path)

    content = (tmp_path / "context" / "recent_updates.md").read_text(encoding="utf-8")
    assert content == "- 2026-07-29 Migrated auth service to JWT\n"


def test_log_entry_appends_to_existing_file(tmp_path, monkeypatch):
    monkeypatch.setattr("accomplishments.date", _FixedDate)
    log_entry("First entry", base_dir=tmp_path)
    log_entry("Second entry", base_dir=tmp_path)

    content = (tmp_path / "context" / "recent_updates.md").read_text(encoding="utf-8")
    assert content == "- 2026-07-29 First entry\n- 2026-07-29 Second entry\n"


def test_log_entry_sanitizes_newlines(tmp_path, monkeypatch):
    monkeypatch.setattr("accomplishments.date", _FixedDate)
    log_entry("line one\nline two", base_dir=tmp_path)

    content = (tmp_path / "context" / "recent_updates.md").read_text(encoding="utf-8")
    assert content == "- 2026-07-29 line one line two\n"


def test_log_entry_rejects_empty_text(tmp_path):
    with pytest.raises(ValueError):
        log_entry("   ", base_dir=tmp_path)


class _FixedDate:
    @staticmethod
    def today():
        return _FIXED_DATE


from datetime import date as _real_date
_FIXED_DATE = _real_date(2026, 7, 29)


from accomplishments import flush


def test_flush_moves_staged_entries_to_accomplishments(tmp_path):
    recent_path = tmp_path / "context" / "recent_updates.md"
    recent_path.parent.mkdir(parents=True)
    recent_path.write_text(
        "- 2026-07-15 [tags: backend] Migrated Provn's auth service to JWT\n"
        "- 2026-07-29 [tags: robotics] Shipped RGB-D fusion milestone\n",
        encoding="utf-8",
    )

    count = flush(base_dir=tmp_path)

    assert count == 2
    accomplishments_content = (tmp_path / "context" / "accomplishments.md").read_text(encoding="utf-8")
    assert "Migrated Provn's auth service to JWT" in accomplishments_content
    assert "Shipped RGB-D fusion milestone" in accomplishments_content
    assert recent_path.read_text(encoding="utf-8") == ""


def test_flush_archives_staged_content(tmp_path):
    recent_path = tmp_path / "context" / "recent_updates.md"
    recent_path.parent.mkdir(parents=True)
    recent_path.write_text("- 2026-07-29 Some entry\n", encoding="utf-8")

    flush(base_dir=tmp_path)

    archive_dir = tmp_path / "context" / "archive"
    archive_files = list(archive_dir.glob("recent_updates_*.md"))
    assert len(archive_files) == 1
    assert archive_files[0].read_text(encoding="utf-8") == "- 2026-07-29 Some entry\n"


def test_flush_appends_to_existing_accomplishments(tmp_path):
    context_dir = tmp_path / "context"
    context_dir.mkdir()
    (context_dir / "accomplishments.md").write_text("- 2026-06-01 Old entry\n", encoding="utf-8")
    (context_dir / "recent_updates.md").write_text("- 2026-07-29 New entry\n", encoding="utf-8")

    flush(base_dir=tmp_path)

    content = (context_dir / "accomplishments.md").read_text(encoding="utf-8")
    assert content == "- 2026-06-01 Old entry\n- 2026-07-29 New entry\n"


def test_flush_nothing_staged_returns_zero(tmp_path):
    count = flush(base_dir=tmp_path)

    assert count == 0
    assert not (tmp_path / "context" / "accomplishments.md").exists()
    assert not (tmp_path / "context" / "archive").exists()


def test_flush_empty_file_returns_zero(tmp_path):
    recent_path = tmp_path / "context" / "recent_updates.md"
    recent_path.parent.mkdir(parents=True)
    recent_path.write_text("   \n", encoding="utf-8")

    count = flush(base_dir=tmp_path)

    assert count == 0
