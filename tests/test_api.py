from __future__ import annotations

import logging

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
