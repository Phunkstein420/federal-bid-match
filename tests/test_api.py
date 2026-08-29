from __future__ import annotations

import logging

import psycopg
from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)


def test_root_is_public() -> None:
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body == {
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
