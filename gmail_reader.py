"""
Searches Gmail via the MCP server for recruiter emails matching a company name.
Run standalone: python gmail_reader.py "Google"
"""

import json
import sys
import httpx
from typing import Optional


GMAIL_MCP_URL = "https://gmailmcp.googleapis.com/mcp/v1"


def _mcp_call(tool: str, params: dict, mcp_url: str = GMAIL_MCP_URL) -> dict:
    """Call a Gmail MCP tool and return the result."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool,
            "arguments": params,
        },
    }
    resp = httpx.post(
        f"{mcp_url}",
        json=payload,
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"MCP error: {data['error']}")
    return data.get("result", {})


def search_emails(
    company: str,
    max_results: int = 5,
    mcp_url: str = GMAIL_MCP_URL,
) -> list[dict]:
    """
    Search Gmail for emails mentioning the company.
    Returns a list of email summary dicts with subject, from, snippet, date.
    """
    query = f'"{company}" (internship OR recruiting OR opportunity OR application)'
    try:
        result = _mcp_call(
            "search_emails",
            {"query": query, "max_results": max_results},
            mcp_url=mcp_url,
        )
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
    except Exception as e:
        print(f"[gmail_reader] Warning: could not search Gmail for '{company}': {e}", file=sys.stderr)
        return []


def format_emails_for_context(emails: list[dict]) -> str:
    """Format email list into a context string for the LLM."""
    if not emails:
        return ""
    lines = ["## Recruiter Emails Found in Gmail\n"]
    for i, email in enumerate(emails, 1):
        subject = email.get("subject", email.get("Subject", ""))
        sender = email.get("from", email.get("From", ""))
        date = email.get("date", email.get("Date", ""))
        snippet = email.get("snippet", email.get("body", ""))[:300]
        lines.append(f"### Email {i}")
        if subject:
            lines.append(f"**Subject:** {subject}")
        if sender:
            lines.append(f"**From:** {sender}")
        if date:
            lines.append(f"**Date:** {date}")
        if snippet:
            lines.append(f"**Preview:** {snippet}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    company = sys.argv[1] if len(sys.argv) > 1 else "Google"
    print(f"Searching Gmail for emails about '{company}'...\n")
    emails = search_emails(company)
    if emails:
        print(f"Found {len(emails)} email(s):\n")
        print(format_emails_for_context(emails))
    else:
        print("No emails found (or Gmail MCP not reachable).")
