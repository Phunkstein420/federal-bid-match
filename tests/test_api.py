from __future__ import annotations

import logging
from datetime import date

import psycopg
from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)


BROWSER_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"

REQUIRED_HOMEPAGE_PHRASES = (
    "Federal Bid Match",
    "$99",
    "per month",
    "Recurring",
    "SAM.gov",
    "NAICS",
    "8(a)",
    "WOSB",
    "HUBZone",
    "SDVOSB",
    "small business",
    "Official notice links only",
    "source of truth",
    "We do not guarantee completeness",
    "We do not write proposals",
    "We are not affiliated with GSA, SAM.gov, or SBA",
    "541511",
    "Douglas Magnuson",
    "Subscribe / $99 month checkout",
    "https://buy.stripe.com/14A28r1Khch97A74EOb3q00",
)

FORBIDDEN_HOMEPAGE_PHRASES = (
    "Apex Data Systems",
    "RapidAPI",
    "occupancy",
    "LLC",
    "DATABASE_URL",
    "SAM_API_KEY",
    "API_KEY",
    "Apex",
    "free trial",
    "Free trial",
    "poc_email",
    "poc_phone",
    "poc_name",
)


def test_root_serves_html_to_browsers() -> None:
    response = client.get("/", headers={"Accept": BROWSER_ACCEPT})
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    for phrase in REQUIRED_HOMEPAGE_PHRASES:
        assert phrase in body
    for phrase in FORBIDDEN_HOMEPAGE_PHRASES:
        assert phrase not in body
    assert "<img" not in body.lower()
    assert "href=\"#\"" not in body
    assert "Checkout link coming" not in body
    assert body.count("https://buy.stripe.com/14A28r1Khch97A74EOb3q00") == 1
    assert body.count("buy.stripe.com") == 1


def test_root_serves_html_by_default() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Federal Bid Match" in response.text
    assert "Douglas Magnuson" in response.text


def test_root_omits_sample_notices_when_db_unavailable() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Recent 541511 SBA notices" not in response.text
    assert "https://buy.stripe.com/14A28r1Khch97A74EOb3q00" in response.text


def test_root_shows_live_sample_notices(monkeypatch) -> None:  # noqa: ANN001
    rows = [
        {
            "title": "Alpha software support",
            "posted_date": date(2026, 9, 1),
            "official_notice_url": "https://sam.gov/opp/aaa/view",
            "poc_email": "hidden@example.com",
        },
        {
            "title": "Bravo maintenance",
            "posted_date": date(2026, 8, 30),
            "official_notice_url": "https://sam.gov/opp/bbb/view",
        },
        {
            "title": "Charlie development",
            "posted_date": date(2026, 8, 29),
            "official_notice_url": "https://sam.gov/opp/ccc/view",
        },
    ]
    monkeypatch.setattr("app.api.query_homepage_notices", lambda **_kwargs: rows)
    response = client.get("/")
    assert response.status_code == 200
    body = response.text
    assert "Recent 541511 SBA notices" in body
    assert "Alpha software support" in body
    assert "href=\"https://sam.gov/opp/aaa/view\"" in body
    assert "2026-09-01" in body
    assert "Bravo maintenance" in body
    assert "Charlie development" in body
    assert "hidden@example.com" not in body
    assert "poc_email" not in body
    assert "https://buy.stripe.com/14A28r1Khch97A74EOb3q00" in body
    assert "Douglas Magnuson" in body
    assert "free trial" not in body.lower()


def test_root_escapes_sample_notice_title(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        "app.api.query_homepage_notices",
        lambda **_kwargs: [
            {
                "title": "<script>alert(1)</script>",
                "posted_date": date(2026, 9, 1),
                "official_notice_url": "https://sam.gov/opp/safe/view",
            }
        ],
    )
    response = client.get("/")
    body = response.text
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body


def test_root_omits_samples_when_db_errors(monkeypatch, caplog) -> None:  # noqa: ANN001
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:super-secret@db.example.invalid:5432/postgres",
    )

    def boom(*_args, **_kwargs):  # noqa: ANN001
        raise psycopg.OperationalError(
            'connection to server at "db.example.invalid" (2001:db8::1), '
            "port 5432 failed: Network is unreachable"
        )

    monkeypatch.setattr("app.query.connect", boom)
    with caplog.at_level(logging.WARNING, logger="app.api"):
        response = client.get("/")
    assert response.status_code == 200
    body = response.text
    assert "Recent 541511 SBA notices" not in body
    assert "super-secret" not in body
    assert "DATABASE_URL" not in body
    assert "https://buy.stripe.com/14A28r1Khch97A74EOb3q00" in body
    assert "Federal Bid Match" in body
    logged = caplog.text
    assert "super-secret" not in logged
    assert "db.example.invalid" not in logged


def test_root_json_for_api_clients() -> None:
    response = client.get("/", headers={"Accept": "application/json"})
    assert response.status_code == 200
    assert response.json() == {
        "name": "federal-bid-match",
        "health": "/health",
        "notices": "/notices requires X-Api-Key",
    }
    assert "DATABASE_URL" not in response.text
    assert "SAM_API_KEY" not in response.text
    assert "=" not in response.text


def test_health_is_public() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_notices_requires_api_key(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("API_KEY", "test-key")
    denied = client.get("/notices")
    assert denied.status_code == 401
    wrong = client.get("/notices", headers={"X-Api-Key": "nope"})
    assert wrong.status_code == 401


def test_notices_db_error_does_not_leak_url(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:super-secret@db.example.invalid/postgres")

    def boom(*_args, **_kwargs):  # noqa: ANN001
        raise OSError("Network is unreachable")

    monkeypatch.setattr("app.query.connect", boom)
    response = client.get("/notices", headers={"X-Api-Key": "test-key"})
    assert response.status_code == 503
    body = response.text
    assert "super-secret" not in body
    assert "DATABASE_URL" not in body
    assert response.json() == {"detail": "database unavailable"}


def test_notices_db_error_logs_redacted_warning(monkeypatch, caplog) -> None:  # noqa: ANN001
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:super-secret@db.example.invalid:5432/postgres",
    )

    def boom(*_args, **_kwargs):  # noqa: ANN001
        raise psycopg.OperationalError(
            'connection to server at "db.example.invalid" (2001:db8::1), '
            "port 5432 failed: Network is unreachable"
        )

    monkeypatch.setattr("app.query.connect", boom)
    with caplog.at_level(logging.WARNING, logger="app.api"):
        response = client.get("/notices", headers={"X-Api-Key": "test-key"})
    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}
    logged = caplog.text
    assert "psycopg.OperationalError" in logged
    assert "super-secret" not in logged
    assert "db.example.invalid" not in logged
    assert "2001:db8::1" not in logged
    assert "5432" not in logged
    assert "postgresql://" not in logged
    assert "DATABASE_URL=" not in logged
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings
