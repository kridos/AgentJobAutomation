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


def log_entry(text: str, tags: str | None = None, base_dir: Path = Path(__file__).parent) -> None:
    text = text.strip().replace("\n", " ")
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


# ponytail: at-least-once flush — a crash between the accomplishments
# append and clearing recent_updates.md could duplicate an entry on
# retry. No data loss. Add read-time dedup if this ever bites.
def flush(base_dir: Path = Path(__file__).parent) -> int:
    recent_path = _recent_updates_path(base_dir)

    if not recent_path.exists():
        print("Nothing to flush.")
        return 0

    staged = recent_path.read_text(encoding="utf-8")
    lines = [line for line in staged.splitlines() if line.strip()]
    if not lines:
        print("Nothing to flush.")
        return 0

    accomplishments_path = _accomplishments_path(base_dir)
    accomplishments_path.parent.mkdir(parents=True, exist_ok=True)
    with open(accomplishments_path, "a", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")

    archive_dir = _archive_dir(base_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = archive_dir / f"recent_updates_{timestamp}.md"
    shutil.copy2(recent_path, archive_path)

    recent_path.write_text("", encoding="utf-8")

    print(f"Flushed {len(lines)} entr{'y' if len(lines) == 1 else 'ies'} to {accomplishments_path}")
    return len(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python accomplishments.py \"some update\" [--tags a,b]", file=sys.stderr)
        print("       python accomplishments.py flush", file=sys.stderr)
        sys.exit(1)
    if sys.argv[1] == "flush":
        flush()
    else:
        text_arg = sys.argv[1]
        tags_arg = None
        if "--tags" in sys.argv:
            tags_arg = sys.argv[sys.argv.index("--tags") + 1]
        log_entry(text_arg, tags=tags_arg)
        print("Logged.")
