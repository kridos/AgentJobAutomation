"""
Archives the current processed.json to /archive/ with a timestamp, then clears it.
Run: python archive_processed.py
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROCESSED_PATH = Path("processed.json")
ARCHIVE_DIR    = Path("archive")


def archive(clear: bool = True) -> None:
    if not PROCESSED_PATH.exists():
        print("processed.json not found — nothing to archive.")
        return

    try:
        with open(PROCESSED_PATH, encoding="utf-8-sig") as f:
            data = json.load(f)
        count = len(data)
    except (json.JSONDecodeError, ValueError):
        data  = []
        count = 0

    ARCHIVE_DIR.mkdir(exist_ok=True)
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = ARCHIVE_DIR / f"processed_{timestamp}.json"
    shutil.copy2(PROCESSED_PATH, archive_path)
    print(f"Archived {count} entries → {archive_path}")

    if clear:
        PROCESSED_PATH.write_text("[]", encoding="utf-8")
        print("processed.json cleared.")

    # Show all archives
    archives = sorted(ARCHIVE_DIR.glob("processed_*.json"))
    print(f"\nAll archives ({len(archives)}):")
    for a in archives:
        try:
            entries = len(json.loads(a.read_text(encoding="utf-8")))
        except Exception:
            entries = "?"
        marker = " ← just saved" if a == archive_path else ""
        print(f"  {a.name}  ({entries} entries){marker}")


def list_archives() -> None:
    archives = sorted(ARCHIVE_DIR.glob("processed_*.json"))
    if not archives:
        print("No archives found.")
        return
    for a in archives:
        try:
            ids = json.loads(a.read_text(encoding="utf-8"))
            print(f"\n{a.name} — {len(ids)} entries")
            for entry in ids[:5]:
                print(f"  {entry}")
            if len(ids) > 5:
                print(f"  ... and {len(ids) - 5} more")
        except Exception as e:
            print(f"{a.name} — unreadable: {e}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "archive"
    if cmd == "list":
        list_archives()
    elif cmd == "archive":
        archive(clear=True)
    elif cmd == "archive-keep":
        archive(clear=False)
    else:
        print("Usage: python archive_processed.py [archive | archive-keep | list]")
