"""
Generic-address email guessing + free SMTP-handshake verification for
cold-outreach contact discovery. Standalone — no dependency on
outreach.py or any scraper.
"""

import smtplib
import sys

import dns.resolver

_GENERIC_PREFIXES = ["founders", "hello", "hi", "team", "info"]


def _guess_email_candidates(domain: str) -> list[str]:
    return [f"{prefix}@{domain}" for prefix in _GENERIC_PREFIXES]


def _resolve_mx_host(domain: str) -> str:
    """Looks up MX records for domain, returns the lowest-priority (i.e.
    most-preferred) hostname. Returns '' on any failure — never raises."""
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=5.0)
        best = min(answers, key=lambda r: r.preference)
        return str(best.exchange).rstrip(".")
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
