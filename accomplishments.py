"""
Quick-capture and promotion of recent accomplishments into permanent
context. Never writes to context/resume_master.md.
Run standalone: python accomplishments.py "some update" --tags a,b
"""

import shutil
import sys
from datetime import date, datetime
from pathlib import Path


def _recent_updates_path(base_dir: Path) -> Path:
    return base_dir / "context" / "recent_updates.md"


def _accomplishments_path(base_dir: Path) -> Path:
    return base_dir / "context" / "accomplishments.md"


def _archive_dir(base_dir: Path) -> Path:
    return base_dir / "context" / "archive"


def log_entry(text: str, tags: str | None = None, base_dir: Path = Path(".")) -> None:
    text = text.strip()
    if not text:
        raise ValueError("log entry text must not be empty")

    tag_segment = ""
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if tag_list:
            tag_segment = f" [tags: {', '.join(tag_list)}]"

    line = f"- {date.today().isoformat()}{tag_segment} {text}\n"

    path = _recent_updates_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python accomplishments.py \"some update\" [--tags a,b]", file=sys.stderr)
        sys.exit(1)
    text_arg = sys.argv[1]
    tags_arg = None
    if "--tags" in sys.argv:
        tags_arg = sys.argv[sys.argv.index("--tags") + 1]
    log_entry(text_arg, tags=tags_arg)
    print("Logged.")
