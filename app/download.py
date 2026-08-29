"""GET the public Data Services CSV. Follow 303 to S3. Retry 303/5xx with backoff."""

from __future__ import annotations

import email.utils
import logging
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from typing import BinaryIO

from app.constants import CSV_DOWNLOAD_URL, USER_AGENT

log = logging.getLogger(__name__)

RETRY_STATUS = frozenset({303, 429, 500, 502, 503, 504})
REDIRECT_STATUS = frozenset({301, 302, 303, 307, 308})
MAX_ATTEMPTS = 6
INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 32.0
DEFAULT_TIMEOUT_SECONDS = 300


class CsvDownloadError(RuntimeError):
    """The public extract could not be downloaded."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Surface 303 so we can GET the Location ourselves (never HEAD)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def extract_date_from_headers(headers: object) -> date:
    last_modified = None
    getter = getattr(headers, "get", None)
    if callable(getter):
        last_modified = getter("Last-Modified")
    if last_modified:
        try:
            parsed = email.utils.parsedate_to_datetime(last_modified)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.date()
        except (TypeError, ValueError, OverflowError):
            pass
    return datetime.now(timezone.utc).date()


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_NoRedirect)


def _get(url: str, *, timeout: float) -> urllib.response.addinfourl:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/csv,application/octet-stream,*/*",
        },
    )
    return _opener().open(request, timeout=timeout)


def open_csv_stream(
    url: str = CSV_DOWNLOAD_URL,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_attempts: int = MAX_ATTEMPTS,
) -> tuple[BinaryIO, date]:
    """
    GET the extract, following 303 with GET (not HEAD).

    Returns (binary stream, source_extract_date). Caller must close the stream.
    Does not log redirect URLs (S3 signed URLs contain credentials).
    """
    current = url
    delay = INITIAL_BACKOFF_SECONDS
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            log.info("GET public Contract Opportunities CSV (attempt %s)", attempt)
            response = _get(current, timeout=timeout)
            code = getattr(response, "status", None) or response.getcode()
            if code in REDIRECT_STATUS:
                location = response.headers.get("Location")
                response.close()
                if not location:
                    raise CsvDownloadError(f"{code} without Location")
                current = location
                log.info("Following %s to object storage (URL omitted)", code)
                if code in RETRY_STATUS:
                    time.sleep(min(delay, MAX_BACKOFF_SECONDS))
                    delay = min(delay * 2, MAX_BACKOFF_SECONDS)
                continue
            if code in RETRY_STATUS or (code is not None and 500 <= int(code) < 600):
                response.close()
                last_error = CsvDownloadError(f"HTTP {code}")
                log.warning("CSV download HTTP %s; backing off", code)
                time.sleep(min(delay, MAX_BACKOFF_SECONDS))
                delay = min(delay * 2, MAX_BACKOFF_SECONDS)
                current = url
                continue
            if code != 200:
                response.close()
                raise CsvDownloadError(f"HTTP {code} fetching public CSV extract")
            extract_date = extract_date_from_headers(response.headers)
            length = response.headers.get("Content-Length")
            log.info(
                "CSV stream open (content-length=%s, extract_date=%s)",
                length or "unknown",
                extract_date.isoformat(),
            )
            return response, extract_date
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in REDIRECT_STATUS:
                location = exc.headers.get("Location") if exc.headers else None
                try:
                    exc.close()
                except Exception:
                    pass
                if not location:
                    raise CsvDownloadError(f"{exc.code} without Location") from exc
                current = location
                log.info("Following %s to object storage (URL omitted)", exc.code)
                if exc.code in RETRY_STATUS:
                    time.sleep(min(delay, MAX_BACKOFF_SECONDS))
                    delay = min(delay * 2, MAX_BACKOFF_SECONDS)
                continue
            if exc.code in RETRY_STATUS or exc.code >= 500:
                log.warning("CSV download HTTP %s; backing off", exc.code)
                try:
                    exc.close()
                except Exception:
                    pass
                time.sleep(min(delay, MAX_BACKOFF_SECONDS))
                delay = min(delay * 2, MAX_BACKOFF_SECONDS)
                current = url
                continue
            raise CsvDownloadError(f"HTTP {exc.code} fetching public CSV extract") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            last_error = exc
            log.warning("CSV download error; backing off")
            time.sleep(min(delay, MAX_BACKOFF_SECONDS))
            delay = min(delay * 2, MAX_BACKOFF_SECONDS)
            current = url

    raise CsvDownloadError("exhausted retries fetching public CSV extract") from last_error
