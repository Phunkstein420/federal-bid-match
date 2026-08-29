"""Redact credentials and network coordinates from driver errors before logging."""

from __future__ import annotations

import re

_REDACTED = "[redacted]"

_URI = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s\"']+")
_USERINFO = re.compile(r"(?i)\b[\w.%+-]+:[^@\s/]+@")
_PASSWORD_ASSIGN = re.compile(r"(?i)\b(?:password|passwd|pwd|pass)\s*[:=]\s*\S+")
_DATABASE_URL = re.compile(r"(?i)\bDATABASE_URL\b(?:\s*[:=]\s*\S+)?")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6 = re.compile(r"(?i)\[?(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}\]?(?:%\w+)?")
_FQDN = re.compile(
    r"\b(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}\b"
)
_PORT = re.compile(
    r"(?i)\bport\s+\d{1,5}\b|:(?:6553[0-5]|655[0-2]\d|65[0-4]\d{2}|6[0-4]\d{3}|[1-5]?\d{1,4})\b"
)


def redact_db_error_text(text: str) -> str:
    """Strip userinfo, passwords, URIs, hosts, IPs, and ports. Never keep a URI shape."""
    if not text:
        return _REDACTED
    out = text
    out = _URI.sub(_REDACTED, out)
    out = _USERINFO.sub(_REDACTED, out)
    out = _PASSWORD_ASSIGN.sub(_REDACTED, out)
    out = _DATABASE_URL.sub(_REDACTED, out)
    out = _IPV6.sub(_REDACTED, out)
    out = _IPV4.sub(_REDACTED, out)
    out = _FQDN.sub(_REDACTED, out)
    out = _PORT.sub(_REDACTED, out)
    if "://" in out:
        return "connection failed: [redacted]"
    out = re.sub(r"[\"']\s*[\"']", "", out)
    out = re.sub(r"\(\s*\)", "", out)
    out = re.sub(r"\s{2,}", " ", out).strip(" :,-")
    return out or "connection failed: [redacted]"


def exception_log_name(exc: BaseException) -> str:
    name = type(exc).__name__
    module = type(exc).__module__ or ""
    if module.startswith("psycopg"):
        return f"psycopg.{name}"
    return name
