"""
Two modes:
  1. search_emails(company)       — cross-reference: find emails about a known company
  2. get_recruiter_listings()     — independent source: find recruiter outreach emails
                                    and parse them into Listing objects

Run standalone:
  python3 gmail_reader.py company "Stripe"       # mode 1
  python3 gmail_reader.py listings               # mode 2
"""

import json
import os
import re
import sys
import httpx
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env", override=False)
except ImportError:
    pass

GMAIL_MCP_URL = "https://gmailmcp.googleapis.com/mcp/v1"
DEFAULT_SEARCH_TOOL = "search_threads"
_TOOL_NAME_CACHE: dict[str, str] = {}

# Recruiter email search query for independent sourcing
RECRUITER_QUERY = (
    "(internship OR intern OR co-op OR opportunity OR application OR recruiting) "
    "(role OR position OR opening OR join) "
    "-unsubscribe -newsletter -digest"
)


# ── MCP helpers ──────────────────────────────────────────────────────────────

def _get_auth_headers() -> dict:
    token = os.environ.get("GMAIL_MCP_TOKEN", "").strip()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _mcp_call(tool: str, params: dict, mcp_url: str = GMAIL_MCP_URL) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": params},
    }
    resp = httpx.post(mcp_url, json=payload, headers=_get_auth_headers(), timeout=15.0)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"MCP error: {data['error']}")
    return data.get("result", {})


def _mcp_list_tools(mcp_url: str = GMAIL_MCP_URL) -> list[str]:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {},
    }
    resp = httpx.post(mcp_url, json=payload, headers=_get_auth_headers(), timeout=15.0)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"MCP error: {data['error']}")

    result = data.get("result", {})
    tools = result.get("tools", [])
    return [tool.get("name", "") for tool in tools if isinstance(tool, dict) and tool.get("name")]


def _resolve_search_tool_name(mcp_url: str = GMAIL_MCP_URL, configured_tool: str = "") -> str:
    cache_key = f"{mcp_url}|{configured_tool}"
    if cache_key in _TOOL_NAME_CACHE:
        return _TOOL_NAME_CACHE[cache_key]

    candidates = [
        configured_tool,
        DEFAULT_SEARCH_TOOL,
        "search_emails",
        "gmail_search_emails",
        "gmail.search_emails",
        "gmail_search_threads",
        "gmail.search_threads",
    ]
    candidates = [name for name in candidates if name]

    try:
        tools = _mcp_list_tools(mcp_url)
    except Exception:
        _TOOL_NAME_CACHE[cache_key] = configured_tool or DEFAULT_SEARCH_TOOL
        return _TOOL_NAME_CACHE[cache_key]

    for candidate in candidates:
        if candidate in tools:
            _TOOL_NAME_CACHE[cache_key] = candidate
            return candidate

    for tool in tools:
        lowered = tool.lower()
        if "search" in lowered and ("email" in lowered or "thread" in lowered):
            _TOOL_NAME_CACHE[cache_key] = tool
            return tool

    _TOOL_NAME_CACHE[cache_key] = configured_tool or DEFAULT_SEARCH_TOOL
    return _TOOL_NAME_CACHE[cache_key]


def _parse_mcp_content(result: dict) -> list[dict]:
    emails = []
    for item in result.get("content", []):
        if isinstance(item, dict) and item.get("type") == "text":
            try:
                parsed = json.loads(item["text"])
                if isinstance(parsed, list):
                    emails.extend(parsed)
                elif isinstance(parsed, dict):
                    emails.append(parsed)
            except json.JSONDecodeError:
                emails.append({"raw": item["text"]})
    return emails


# ── Mode 1: cross-reference search ───────────────────────────────────────────

def search_emails(
    company: str,
    max_results: int = 5,
    mcp_url: str = GMAIL_MCP_URL,
    tool_name: str = "",
) -> list[dict]:
    """Find emails in Gmail that mention a specific company."""
    query = f'"{company}" (internship OR recruiting OR opportunity OR application)'
    try:
        resolved_tool = _resolve_search_tool_name(mcp_url, tool_name)
        result = _mcp_call(resolved_tool, {"query": query, "max_results": max_results}, mcp_url=mcp_url)
        return _parse_mcp_content(result)
    except Exception as e:
        print(f"[gmail_reader] Warning: could not search Gmail for '{company}': {e}", file=sys.stderr)
        return []


def format_emails_for_context(emails: list[dict]) -> str:
    if not emails:
        return ""
    lines = ["## Recruiter Emails Found in Gmail\n"]
    for i, email in enumerate(emails, 1):
        subject = email.get("subject", email.get("Subject", ""))
        sender = email.get("from", email.get("From", ""))
        date = email.get("date", email.get("Date", ""))
        snippet = email.get("snippet", email.get("body", ""))[:400]
        lines.append(f"### Email {i}")
        if subject: lines.append(f"**Subject:** {subject}")
        if sender:  lines.append(f"**From:** {sender}")
        if date:    lines.append(f"**Date:** {date}")
        if snippet: lines.append(f"**Preview:** {snippet}")
        lines.append("")
    return "\n".join(lines)


# ── Mode 2: independent recruiter listing extraction ─────────────────────────

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


def get_recruiter_listings(
    max_results: int = 20,
    mcp_url: str = GMAIL_MCP_URL,
    tool_name: str = "",
) -> list[EmailListing]:
    """
    Scan Gmail for recruiter outreach emails and return them as EmailListing objects.
    Each listing contains the full email body as the job description context.
    """
    try:
        resolved_tool = _resolve_search_tool_name(mcp_url, tool_name)
        result = _mcp_call(resolved_tool, {"query": RECRUITER_QUERY, "max_results": max_results}, mcp_url=mcp_url)
        emails = _parse_mcp_content(result)
    except Exception as e:
        print(f"[gmail_reader] Could not fetch recruiter listings: {e}", file=sys.stderr)
        return []

    listings = []
    for email in emails:
        subject = email.get("subject", email.get("Subject", ""))
        sender  = email.get("from", email.get("From", ""))
        date    = email.get("date", email.get("Date", ""))
        body    = email.get("body", email.get("snippet", ""))

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


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "listings"

    if mode == "company" and len(sys.argv) > 2:
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
            print("No recruiter listings found (or Gmail MCP not reachable).")
