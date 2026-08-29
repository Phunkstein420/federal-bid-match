from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from urllib.error import HTTPError

from app.download import CsvDownloadError, extract_date_from_headers, open_csv_stream


class _FakeHeaders(dict):
    def get(self, key, default=None):  # noqa: ANN001
        for candidate, value in self.items():
            if candidate.lower() == key.lower():
                return value
        return default


class _FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, *, status: int = 200, headers: dict | None = None):
        super().__init__(body)
        self.status = status
        self.headers = _FakeHeaders(headers or {"Content-Length": str(len(body))})

    def getcode(self) -> int:
        return self.status


def test_extract_date_from_last_modified() -> None:
    headers = _FakeHeaders({"Last-Modified": "Sat, 29 Aug 2026 06:00:00 GMT"})
    assert extract_date_from_headers(headers).isoformat() == "2026-08-29"


def test_open_csv_stream_follows_303_then_retries_5xx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.download.time.sleep", lambda _seconds: None)
    calls: list[str] = []

    def _get(url: str, *, timeout: float):  # noqa: ARG001
        calls.append(url)
        if url.endswith("/extract"):
            raise HTTPError(
                url,
                303,
                "See Other",
                _FakeHeaders({"Location": "https://s3.example/file.csv"}),
                fp=None,
            )
        s3_hits = [u for u in calls if u.startswith("https://s3.example")]
        if url.startswith("https://s3.example") and len(s3_hits) == 1:
            raise HTTPError(url, 503, "Unavailable", _FakeHeaders(), fp=None)
        return _FakeResponse(b"NoticeId\n", status=200)

    with patch("app.download._get", side_effect=_get):
        stream, extract_date = open_csv_stream("https://sam.example/extract")
        assert stream.read() == b"NoticeId\n"
        stream.close()
    assert extract_date is not None
    assert calls[0].endswith("/extract")
    assert any(u.startswith("https://s3.example") for u in calls)


def test_open_csv_stream_gives_up_after_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.download.time.sleep", lambda _seconds: None)

    def _get(url: str, *, timeout: float):  # noqa: ARG001
        raise HTTPError(url, 500, "Boom", _FakeHeaders(), fp=None)

    with patch("app.download._get", side_effect=_get):
        with pytest.raises(CsvDownloadError):
            open_csv_stream("https://sam.example/extract", max_attempts=3)
