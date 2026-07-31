"""
Lists generated applications from output/, and tracks per-application
apply status (applied/skipped/pending) in status.json alongside each
application's generated files. Pure data layer — no HTTP here.
Run standalone: python applications.py
"""

import json
import sys
from pathlib import Path

_VALID_STATUSES = {"applied", "skipped", "pending"}


def _read_json(path: Path) -> tuple[dict | None, bool]:
    """Returns (data, ok). ok is False when the file exists but is malformed."""
    if not path.exists():
        return {}, True
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, False
    if not isinstance(data, dict):
        return None, False
    return data, True


def list_applications() -> list[dict]:
    output_base = Path("output")
    if not output_base.exists():
        return []

    apps = []
    for listing_path in output_base.glob("*/*/*/*/listing.json"):
        app_dir = listing_path.parent
        app_id = "/".join(app_dir.parts[-4:])

        listing, ok = _read_json(listing_path)
        if not ok:
            print(f"[applications] skipping {listing_path}: malformed JSON", file=sys.stderr)
            continue

        score, ok = _read_json(app_dir / "quality_score.json")
        if not ok:
            print(f"[applications] skipping {app_dir / 'quality_score.json'}: malformed JSON", file=sys.stderr)
            continue

        status_data, ok = _read_json(app_dir / "status.json")
        if not ok:
            print(f"[applications] skipping {app_dir / 'status.json'}: malformed JSON", file=sys.stderr)
            continue
        status = status_data.get("status", "pending")
        if status not in _VALID_STATUSES:
            status = "pending"

        date, source, company_slug, role_slug = app_dir.parts[-4:]
        apps.append({
            "id": app_id,
            "company": listing.get("company", company_slug),
            "role": listing.get("role", role_slug),
            "source": source,
            "date": date,
            "score": score.get("overall", 0),
            "status": status,
            "link": listing.get("link", ""),
            "has_prep": (app_dir / "interview_prep.md").exists(),
        })

    apps.sort(key=lambda a: a["id"], reverse=True)
    return apps


def get_application(app_id: str) -> dict | None:
    apps = {a["id"]: a for a in list_applications()}
    if app_id not in apps:
        return None

    app = dict(apps[app_id])
    app_dir = Path("output") / app_id
    for field, filename in (("resume_md", "resume.md"), ("cover_md", "cover_letter.md"),
                             ("job_description", "job_description.txt")):
        path = app_dir / filename
        app[field] = path.read_text(encoding="utf-8") if path.exists() else ""
    return app


def set_application_status(app_id: str, status: str) -> bool:
    if status not in _VALID_STATUSES:
        return False
    known_ids = {a["id"] for a in list_applications()}
    if app_id not in known_ids:
        return False
    app_dir = Path("output") / app_id
    (app_dir / "status.json").write_text(json.dumps({"status": status}, indent=2), encoding="utf-8")
    return True


if __name__ == "__main__":
    for app in list_applications():
        print(f"{app['status']:8} {app['date']} {app['company']} — {app['role']}")
