from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)


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
