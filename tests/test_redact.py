from __future__ import annotations

import psycopg

from app.redact import exception_log_name, redact_db_error_text


def test_redact_strips_uri_password_host_ip_and_port() -> None:
    raw = (
        'connection to server at "db.example.invalid" (2001:db8::1), port 5432 failed: '
        "password authentication failed for user "
        '"postgres.example" using postgresql://user:super-secret@db.example.invalid:5432/postgres '
        "DATABASE_URL=postgresql://user:super-secret@203.0.113.10:6543/postgres"
    )
    redacted = redact_db_error_text(raw)
    assert "super-secret" not in redacted
    assert "db.example.invalid" not in redacted
    assert "2001:db8::1" not in redacted
    assert "203.0.113.10" not in redacted
    assert "5432" not in redacted
    assert "6543" not in redacted
    assert "postgresql://" not in redacted
    assert "DATABASE_URL" not in redacted
    assert ":// " not in redacted and "://" not in redacted
    assert "[redacted]" in redacted


def test_redact_ipv4_only_message() -> None:
    redacted = redact_db_error_text(
        "connection to server at 203.0.113.50, port 5432 failed: Network is unreachable"
    )
    assert "203.0.113.50" not in redacted
    assert "5432" not in redacted
    assert "Network is unreachable" in redacted


def test_exception_log_name_for_psycopg() -> None:
    exc = psycopg.OperationalError("connection failed")
    assert exception_log_name(exc) == "psycopg.OperationalError"
    assert exception_log_name(OSError("x")) == "OSError"
