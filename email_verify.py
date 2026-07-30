"""
Generic-address email guessing + free SMTP-handshake verification for
cold-outreach contact discovery. Standalone — no dependency on
outreach.py or any scraper.
"""

import smtplib
import subprocess
import sys

_GENERIC_PREFIXES = ["founders", "hello", "hi", "team", "info"]


def _guess_email_candidates(domain: str) -> list[str]:
    return [f"{prefix}@{domain}" for prefix in _GENERIC_PREFIXES]


def _resolve_mx_host(domain: str) -> str:
    """Shells out to `dig +short MX <domain>`, returns the lowest-priority
    (i.e. most-preferred) hostname. Returns '' on any failure — never raises."""
    try:
        result = subprocess.run(
            ["dig", "+short", "MX", domain],
            capture_output=True, text=True, timeout=5.0,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return ""
        records = []
        for line in result.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) == 2:
                priority, host = parts
                records.append((int(priority), host.rstrip(".")))
        if not records:
            return ""
        records.sort(key=lambda r: r[0])
        return records[0][1]
    except Exception as e:
        print(f"[email_verify] MX lookup failed for {domain}: {e}", file=sys.stderr)
        return ""


def _verify_email_smtp(email: str, timeout: float = 5.0) -> bool:
    """SMTP handshake verification: EHLO, MAIL FROM, RCPT TO — never sends
    DATA, never completes a message. Fails closed: any error, timeout, or
    non-2xx response returns False."""
    domain = email.split("@", 1)[-1]
    mx_host = _resolve_mx_host(domain)
    if not mx_host:
        return False

    try:
        with smtplib.SMTP(mx_host, 25, timeout=timeout) as smtp:
            smtp.ehlo_or_helo_if_needed()
            smtp.mail("verify@example.com")
            code, _ = smtp.rcpt(email)
            return 200 <= code < 300
    except Exception as e:
        print(f"[email_verify] SMTP verification failed for {email}: {e}", file=sys.stderr)
        return False


def guess_and_verify_email(domain: str) -> tuple[str, bool]:
    """Tries each generic candidate until one verifies via SMTP.
    Returns (email, True) on first success, or (first_candidate, False)
    if none verify."""
    candidates = _guess_email_candidates(domain)
    for candidate in candidates:
        if _verify_email_smtp(candidate):
            return candidate, True
    return candidates[0], False
