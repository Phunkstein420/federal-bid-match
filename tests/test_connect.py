from __future__ import annotations

import socket
from typing import Any

import pytest

from app.db import connect, ipv4_connect_params, resolve_ipv4_hostaddr

DIRECT_URL = "postgresql://user:pass@db.example.invalid:5432/postgres"
POOLER_URL = (
    "postgresql://user.project:pass@aws-0-ca-central-1.pooler.supabase.com:6543/postgres"
)
IPV4 = "203.0.113.10"


def _a_record(host: str, ipv4: str = IPV4):
    def fake_getaddrinfo(
        name: str,
        port: Any,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ):
        assert name == host
        assert family == socket.AF_INET
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ipv4, 0)),
        ]

    return fake_getaddrinfo


def test_resolve_prefers_ipv4_a_records(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _a_record("db.example.invalid"))
    assert resolve_ipv4_hostaddr("db.example.invalid") == IPV4


def test_ipv4_params_for_direct_and_pooler_uris(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(
        name: str,
        port: Any,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ):
        assert family == socket.AF_INET
        mapping = {
            "db.example.invalid": "203.0.113.10",
            "aws-0-ca-central-1.pooler.supabase.com": "203.0.113.20",
        }
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (mapping[name], 0)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert ipv4_connect_params(DIRECT_URL) == {"hostaddr": "203.0.113.10"}
    assert ipv4_connect_params(POOLER_URL) == {"hostaddr": "203.0.113.20"}


def test_ipv6_only_hostname_does_not_rewrite_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_aaaa_a_records(*_args: Any, **_kwargs: Any):
        raise socket.gaierror(socket.EAI_NONAME, "no A records")

    monkeypatch.setattr(socket, "getaddrinfo", no_aaaa_a_records)
    assert ipv4_connect_params(DIRECT_URL) == {}
    assert ipv4_connect_params(POOLER_URL) == {}


def test_connect_passes_original_url_and_ipv4_hostaddr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    monkeypatch.setattr(socket, "getaddrinfo", _a_record("db.example.invalid"))

    def fake_connect(conninfo: str, **kwargs: Any):
        seen["conninfo"] = conninfo
        seen["kwargs"] = kwargs

        class _Conn:
            pass

        return _Conn()

    monkeypatch.setattr("app.db.psycopg.connect", fake_connect)
    connect(DIRECT_URL)
    assert seen["conninfo"] is DIRECT_URL
    assert seen["conninfo"] == DIRECT_URL
    assert seen["kwargs"]["hostaddr"] == IPV4
    assert "password" not in seen["kwargs"]
    assert "@" in seen["conninfo"]  # original URI kept; not a rewritten host-only string


def test_connect_pooler_uri_also_gets_ipv4_hostaddr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        _a_record("aws-0-ca-central-1.pooler.supabase.com", "198.51.100.7"),
    )

    def fake_connect(conninfo: str, **kwargs: Any):
        seen["conninfo"] = conninfo
        seen["kwargs"] = kwargs

        class _Conn:
            pass

        return _Conn()

    monkeypatch.setattr("app.db.psycopg.connect", fake_connect)
    connect(POOLER_URL)
    assert seen["conninfo"] == POOLER_URL
    assert seen["kwargs"]["hostaddr"] == "198.51.100.7"
    assert "pooler.supabase.com" in seen["conninfo"]


def test_ipv4_literal_host_used_as_hostaddr() -> None:
    url = "postgresql://user:pass@203.0.113.5:5432/postgres"
    assert ipv4_connect_params(url) == {"hostaddr": "203.0.113.5"}


def test_ipv4_helpers_do_not_embed_userinfo() -> None:
    params = ipv4_connect_params("postgresql://user:super-secret@203.0.113.5:5432/postgres")
    dumped = repr(params)
    assert "super-secret" not in dumped
    assert "user" not in dumped
