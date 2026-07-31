"""
Real Gmail API integration (OAuth 2.0 installed-app flow).
Two read modes:
  1. search_emails(company)       — cross-reference: find emails about a known company
  2. get_recruiter_listings()     — independent source: find recruiter outreach emails
                                    and parse them into Listing objects
Plus create_draft() — creates a Gmail draft. Never sends (the send endpoint
is never called anywhere in this file).

One-time setup: create a Google Cloud project, enable the Gmail API, create
an OAuth 2.0 Client ID of type "Desktop app", and save its downloaded JSON
as credentials.json in the repo root (gitignored). Then run
`automator gmail auth` (or `python3 gmail_reader.py auth`) once to log in —
this opens a browser for Google's consent screen and saves a refreshable
token to token.json (also gitignored). Every later run refreshes it silently.

Run standalone:
  python3 gmail_reader.py auth                    # one-time OAuth login
  python3 gmail_reader.py company "Stripe"         # mode 1
  python3 gmail_reader.py listings                 # mode 2
"""

import base64
import json
import re
import sys
from dataclasses import dataclass, asdict
from email.mime.text import MIMEText
from pathlib import Path

import httpx
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

CREDENTIALS_PATH = Path(__file__).parent / "credentials.json"
TOKEN_PATH = Path(__file__).parent / "token.json"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

# Recruiter email search query for independent sourcing
RECRUITER_QUERY = (
    "(internship OR intern OR co-op OR opportunity OR application OR recruiting) "
    "(role OR position OR opening OR join) "
    "-unsubscribe -newsletter -digest"
)


# ── OAuth ─────────────────────────────────────────────────────────────────

def run_oauth_flow() -> bool:
    """One-time interactive OAuth login. Opens a browser for the Google
    consent screen, saves a refreshable token to TOKEN_PATH. Returns False
    (with a clear message) if credentials.json is missing."""
    if not CREDENTIALS_PATH.exists():
        print(
            f"[gmail_reader] {CREDENTIALS_PATH} not found. Create an OAuth "
            "Desktop app client in Google Cloud Console (with the Gmail API "
            "enabled) and save its downloaded JSON as credentials.json here first.",
            file=sys.stderr,
        )
        return False
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    print(f"[gmail_reader] Saved credentials to {TOKEN_PATH}")
    return True


def _load_credentials() -> Credentials | None:
    """Loads and refreshes the saved OAuth token. Returns None (with a clear
    message) on any failure — never raises."""
    if not TOKEN_PATH.exists():
        print("[gmail_reader] No saved Gmail credentials — run `automator gmail auth` first.", file=sys.stderr)
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        if not creds.valid:
            print("[gmail_reader] Gmail credentials invalid — run `automator gmail auth` again.", file=sys.stderr)
            return None
        return creds
    except (RefreshError, ValueError, OSError) as e:
        print(f"[gmail_reader] Could not load/refresh Gmail credentials: {e}", file=sys.stderr)
        return None


def _auth_headers() -> dict | None:
    creds = _load_credentials()
    if creds is None:
        return None
    return {"Authorization": f"Bearer {creds.token}"}


# ── Message fetching + parsing ───────────────────────────────────────────

def _list_message_ids(query: str, max_results: int, headers: dict) -> list[str]:
    resp = httpx.get(
        f"{GMAIL_API_BASE}/messages",
        params={"q": query, "maxResults": max_results},
        headers=headers,
        timeout=15.0,
    )
    resp.raise_for_status()
    return [m["id"] for m in resp.json().get("messages", [])]


def _extract_header(headers_list: list[dict], name: str) -> str:
    for h in headers_list:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _decode_part_data(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _extract_body(payload: dict) -> str:
    """Walks a Gmail API message payload, preferring text/plain, falling
    back to a stripped text/html part (including nested multipart parts)."""
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if mime_type == "text/plain" and body_data:
        return _decode_part_data(body_data)

    html_fallback = ""
    for part in payload.get("parts", []) or []:
        part_mime = part.get("mimeType", "")
        part_data = part.get("body", {}).get("data", "")
        if part_mime == "text/plain" and part_data:
            return _decode_part_data(part_data)
        if part_mime == "text/html" and part_data and not html_fallback:
            html_fallback = _decode_part_data(part_data)
        elif part.get("parts"):
            nested = _extract_body(part)
            if nested:
                return nested

    if html_fallback:
        return re.sub(r"<[^>]+>", " ", html_fallback)

    if mime_type == "text/html" and body_data:
        return re.sub(r"<[^>]+>", " ", _decode_part_data(body_data))

    return ""


def _get_message(msg_id: str, headers: dict) -> dict:
    resp = httpx.get(
        f"{GMAIL_API_BASE}/messages/{msg_id}",
        params={"format": "full"},
        headers=headers,
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json()
    payload = data.get("payload", {})
    msg_headers = payload.get("headers", [])
    return {
        "subject": _extract_header(msg_headers, "Subject"),
        "from": _extract_header(msg_headers, "From"),
        "date": _extract_header(msg_headers, "Date"),
        "body": _extract_body(payload),
        "snippet": data.get("snippet", ""),
    }


def _search_messages(query: str, max_results: int) -> list[dict]:
    """Real two-step Gmail search: list message IDs, then fetch each in full.
    Fails soft — a missing/invalid token or a search-level error returns [];
    a single message that fails to fetch is skipped, not fatal to the batch."""
    headers = _auth_headers()
    if headers is None:
        return []
    try:
        ids = _list_message_ids(query, max_results, headers)
    except Exception as e:
        print(f"[gmail_reader] Gmail search failed: {e}", file=sys.stderr)
        return []

    messages = []
    for msg_id in ids:
        try:
            messages.append(_get_message(msg_id, headers))
        except Exception as e:
            print(f"[gmail_reader] Skipping message {msg_id}: {e}", file=sys.stderr)
    return messages


# ── Mode 1: cross-reference search ───────────────────────────────────────

def search_emails(company: str, max_results: int = 5) -> list[dict]:
    """Find emails in Gmail that mention a specific company."""
    query = f'"{company}" (internship OR recruiting OR opportunity OR application)'
    return _search_messages(query, max_results)


def format_emails_for_context(emails: list[dict]) -> str:
    if not emails:
        return ""
    lines = ["## Recruiter Emails Found in Gmail\n"]
    for i, email in enumerate(emails, 1):
        subject = email.get("subject", "")
        sender = email.get("from", "")
        date = email.get("date", "")
        snippet = email.get("snippet", email.get("body", ""))[:400]
        lines.append(f"### Email {i}")
        if subject: lines.append(f"**Subject:** {subject}")
        if sender:  lines.append(f"**From:** {sender}")
        if date:    lines.append(f"**Date:** {date}")
        if snippet: lines.append(f"**Preview:** {snippet}")
        lines.append("")
    return "\n".join(lines)


# ── Mode 2: independent recruiter listing extraction ─────────────────────

@dataclass
class EmailListing:
    company: str
    role: str
    sender_email: str
    subject: str
    body: str
    date: str
    id: str = ""

    def __post_init__(self):
        if not self.id:
            slug = re.sub(r"[^a-z0-9]+", "-", f"gmail-{self.company}-{self.role}".lower()).strip("-")
            self.id = slug


def _extract_company_from_email(subject: str, sender: str, body: str) -> str:
    """Best-effort company extraction from email metadata."""
    # Try sender domain: recruiter@stripe.com → Stripe
    domain_match = re.search(r"@([\w-]+)\.(com|io|ai|co|org|net)", sender)
    if domain_match:
        domain = domain_match.group(1)
        # Skip known email platforms
        if domain.lower() not in ("gmail", "outlook", "yahoo", "hotmail", "greenhouse",
                                   "lever", "workday", "ashby", "jobvite", "icims", "smartrecruiters"):
            return domain.replace("-", " ").title()

    # Try "at <Company>" or "from <Company>" in subject/body
    for pattern in [
        r"\bat\s+([A-Z][A-Za-z0-9\s&.]+?)(?:\s*[,!.?]|$)",
        r"\bfrom\s+([A-Z][A-Za-z0-9\s&.]+?)(?:\s*[,!.?]|$)",
        r"\b([A-Z][A-Za-z0-9]+(?:\s[A-Z][A-Za-z0-9]+)?)\s+(?:is\s+)?(?:hiring|recruiting|internship)",
    ]:
        m = re.search(pattern, subject + " " + body[:500])
        if m:
            return m.group(1).strip()

    return ""


def _extract_role_from_email(subject: str, body: str) -> str:
    """Best-effort role extraction from subject/body."""
    role_patterns = [
        r"(?:position|role|opening|opportunity)\s*(?:for|:)\s*([^\n,.!?]{5,60})",
        r"(?:intern|internship|co-op)\s+(?:in|for|as|[-–])\s+([^\n,.!?]{5,50})",
        r"(software engineer(?:ing)? intern(?:ship)?)",
        r"((?:SWE|ML|AI|data\s+science|backend|frontend|fullstack)\s+intern(?:ship)?)",
    ]
    text = subject + "\n" + body[:1000]
    for pat in role_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()

    # Fallback: use subject line cleaned up
    subject_clean = re.sub(r"^(re:|fwd?:|fw:)\s*", "", subject, flags=re.IGNORECASE).strip()
    return subject_clean[:80] if subject_clean else "Internship"


def get_recruiter_listings(max_results: int = 20) -> list[EmailListing]:
    """
    Scan Gmail for recruiter outreach emails and return them as EmailListing objects.
    Each listing contains the full email body as the job description context.
    """
    emails = _search_messages(RECRUITER_QUERY, max_results)

    listings = []
    for email in emails:
        subject = email.get("subject", "")
        sender  = email.get("from", "")
        date    = email.get("date", "")
        body    = email.get("body", "") or email.get("snippet", "")

        company = _extract_company_from_email(subject, sender, body)
        role    = _extract_role_from_email(subject, body)

        if not company or not role:
            continue

        listings.append(EmailListing(
            company=company,
            role=role,
            sender_email=sender,
            subject=subject,
            body=body[:6000],  # keep full body for LLM context
            date=date,
        ))

    return listings


# ── Draft creation ────────────────────────────────────────────────────────

def create_draft(to: str, subject: str, body: str) -> bool:
    """Creates a Gmail draft via the real Gmail API. Never sends — the send
    endpoint is never called anywhere in this file. Returns True on success,
    False on any failure (caught and logged, never raises)."""
    headers = _auth_headers()
    if headers is None:
        return False
    try:
        message = MIMEText(body)
        message["To"] = to
        message["Subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        resp = httpx.post(
            f"{GMAIL_API_BASE}/drafts",
            json={"message": {"raw": raw}},
            headers=headers,
            timeout=15.0,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[gmail_reader] Warning: could not create draft for '{to}': {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "listings"

    if mode == "auth":
        run_oauth_flow()

    elif mode == "company" and len(sys.argv) > 2:
        company = sys.argv[2]
        print(f"Searching Gmail for emails about '{company}'...\n")
        emails = search_emails(company)
        print(format_emails_for_context(emails) if emails else "No emails found.")

    else:
        print("Scanning Gmail for recruiter emails...\n")
        listings = get_recruiter_listings()
        if listings:
            print(f"Found {len(listings)} recruiter listing(s):\n")
            for l in listings:
                print(json.dumps(asdict(l), indent=2, default=str))
        else:
            print("No recruiter listings found (or Gmail not authenticated — run `python3 gmail_reader.py auth`).")
