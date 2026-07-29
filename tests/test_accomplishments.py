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


def test_log_entry_rejects_empty_text(tmp_path):
    with pytest.raises(ValueError):
        log_entry("   ", base_dir=tmp_path)


class _FixedDate:
    @staticmethod
    def today():
        return _FIXED_DATE


from datetime import date as _real_date
_FIXED_DATE = _real_date(2026, 7, 29)
