"""Postgres access for existing public.sam_notices / public.sam_ingest_runs."""

from __future__ import annotations

import logging
import re
import socket
from collections.abc import Sequence
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.constants import WINDOW_DAYS

log = logging.getLogger(__name__)

# Dotted-quad only. DNS names must never be passed to IP-literal parsers.
_IPV4_DOTTED = re.compile(r"\A\d{1,3}(?:\.\d{1,3}){3}\Z")


def _hostname_from_url(database_url: str) -> str | None:
    """Host only. Never log or return userinfo."""
    if "://" not in database_url:
        return None
    return urlparse(database_url).hostname


def _as_ipv4_literal(host: str) -> str | None:
    """Parse a dotted IPv4 literal. Hostnames return None (no exception)."""
    if not host or not _IPV4_DOTTED.fullmatch(host):
        return None
    try:
        socket.inet_pton(socket.AF_INET, host)
    except OSError:
        return None
    return host


def _is_ipv6_literal(host: str) -> bool:
    if not host or ":" not in host:
        return False
    try:
        socket.inet_pton(socket.AF_INET6, host.strip("[]"))
    except OSError:
        return False
    return True


def resolve_ipv4_hostaddr(host: str) -> str | None:
    """A-record or IPv4 literal. IPv6-only names return None (no exception)."""
    if not host:
        return None
    literal = host.strip("[]")
    ipv4 = _as_ipv4_literal(literal)
    if ipv4:
        return ipv4
    if _is_ipv6_literal(literal):
        return None
    try:
        answers = socket.getaddrinfo(
            host,
            None,
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )
    except OSError:
        return None
    for family, _type, _proto, _canon, sockaddr in answers:
        if family == socket.AF_INET and sockaddr and sockaddr[0]:
            return sockaddr[0]
    return None


def ipv4_connect_params(database_url: str) -> dict[str, str]:
    """
    libpq hostaddr when an IPv4 address exists.

    Does not rewrite the URI. Does not raise on DNS hostnames (including
    IPv6-only names). Never treats a hostname as an IP literal.
    """
    try:
        host = _hostname_from_url(database_url)
        if not host:
            return {}
        ipv4 = resolve_ipv4_hostaddr(host)
        if not ipv4:
            return {}
        return {"hostaddr": ipv4}
    except Exception:
        return {}


def connect(database_url: str) -> psycopg.Connection:
    """
    Connect using DATABASE_URL as given (direct :5432 or pooler :6543).

    Prefers IPv4 via hostaddr so IPv4-only networks (e.g. Render) do not
    attempt an unreachable AAAA. Does not rewrite, log, or print the URI.
    """
    return psycopg.connect(
        database_url,
        row_factory=dict_row,
        prepare_threshold=None,
        **ipv4_connect_params(database_url),
    )


NOTICE_COLUMNS = (
    "notice_id",
    "title",
    "solicitation_number",
    "notice_type",
    "posted_date",
    "response_deadline",
    "naics_code",
    "set_aside",
    "set_aside_code",
    "classification_code",
    "agency_path",
    "pop_city",
    "pop_state",
    "pop_zip",
    "poc_name",
    "poc_email",
    "poc_phone",
    "description_url",
    "resource_links",
    "official_notice_url",
    "source_extract_date",
    "collected_at",
    "is_active",
)

_INSERT_PLACEHOLDERS = ", ".join(f"%({name})s" for name in NOTICE_COLUMNS)
_INSERT_COLS = ", ".join(NOTICE_COLUMNS)
_UPDATE_SET = ", ".join(
    f"{name} = EXCLUDED.{name}" for name in NOTICE_COLUMNS if name != "notice_id"
)

UPSERT_SQL = f"""
INSERT INTO public.sam_notices ({_INSERT_COLS})
VALUES ({_INSERT_PLACEHOLDERS})
ON CONFLICT (notice_id) DO UPDATE SET {_UPDATE_SET}
"""

INSERT_RUN_SQL = """
INSERT INTO public.sam_ingest_runs (source, status, notes)
VALUES (%(source)s, %(status)s, %(notes)s)
RETURNING id
"""

FINISH_RUN_SQL = """
UPDATE public.sam_ingest_runs
SET finished_at = %(finished_at)s,
    rows_read = %(rows_read)s,
    rows_upserted = %(rows_upserted)s,
    status = %(status)s,
    notes = %(notes)s
WHERE id = %(id)s
"""

CUSTOMER_QUERY_SQL = """
WITH filtered AS (
    SELECT *
    FROM public.sam_notices
    WHERE notice_type IN ('o', 'k', 'p', 'r')
      AND posted_date >= (CURRENT_DATE - %(window_days)s::int)
      AND naics_code = %(naics_code)s
      AND set_aside_code = %(set_aside_code)s
      AND (
          %(pop_state)s::text IS NULL
          OR pop_state = %(pop_state)s
      )
),
ranked AS (
    SELECT
        filtered.*,
        ROW_NUMBER() OVER (
            PARTITION BY COALESCE(NULLIF(solicitation_number, ''), notice_id)
            ORDER BY posted_date DESC NULLS LAST, collected_at DESC
        ) AS rn
    FROM filtered
)
SELECT
    notice_id,
    title,
    solicitation_number,
    notice_type,
    posted_date,
    response_deadline,
    naics_code,
    set_aside,
    set_aside_code,
    classification_code,
    agency_path,
    pop_city,
    pop_state,
    pop_zip,
    poc_name,
    poc_email,
    poc_phone,
    description_url,
    resource_links,
    official_notice_url,
    source_extract_date,
    collected_at,
    is_active
FROM ranked
WHERE rn = 1
ORDER BY posted_date DESC NULLS LAST, collected_at DESC
"""

# Public homepage samples only. No POC, no API fields.
HOMEPAGE_SAMPLE_SQL = """
WITH ranked AS (
    SELECT
        title,
        posted_date,
        collected_at,
        official_notice_url,
        ROW_NUMBER() OVER (
            PARTITION BY COALESCE(NULLIF(solicitation_number, ''), notice_id)
            ORDER BY posted_date DESC NULLS LAST, collected_at DESC
        ) AS rn
    FROM public.sam_notices
    WHERE is_active IS TRUE
      AND naics_code = %(naics_code)s
      AND set_aside_code = %(set_aside_code)s
)
SELECT title, posted_date, official_notice_url
FROM ranked
WHERE rn = 1
ORDER BY posted_date DESC NULLS LAST, collected_at DESC
LIMIT 3
"""


def _bind_notice(notice: dict[str, Any]) -> dict[str, Any]:
    bound = dict(notice)
    links = bound.get("resource_links")
    if links is None:
        bound["resource_links"] = None
    else:
        bound["resource_links"] = Jsonb(links)
    return bound


def upsert_notices(
    conn: psycopg.Connection,
    notices: Sequence[dict[str, Any]],
) -> int:
    if not notices:
        return 0
    with conn.cursor() as cur:
        cur.executemany(UPSERT_SQL, [_bind_notice(n) for n in notices])
    conn.commit()
    return len(notices)


def start_ingest_run(
    conn: psycopg.Connection,
    *,
    source: str,
    notes: str | None = None,
) -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            INSERT_RUN_SQL,
            {"source": source, "status": "running", "notes": notes},
        )
        row = cur.fetchone()
    conn.commit()
    if row is None:
        raise RuntimeError("failed to insert sam_ingest_runs row")
    return row["id"]


def finish_ingest_run(
    conn: psycopg.Connection,
    run_id: UUID,
    *,
    rows_read: int,
    rows_upserted: int,
    status: str,
    notes: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            FINISH_RUN_SQL,
            {
                "id": run_id,
                "finished_at": datetime.now(timezone.utc),
                "rows_read": rows_read,
                "rows_upserted": rows_upserted,
                "status": status,
                "notes": notes,
            },
        )
    conn.commit()


def fetch_customer_notices(
    conn: psycopg.Connection,
    *,
    naics_code: str,
    set_aside_code: str,
    pop_state: str | None = None,
    window_days: int = WINDOW_DAYS,
) -> list[dict[str, Any]]:
    params = {
        "naics_code": naics_code,
        "set_aside_code": set_aside_code,
        "pop_state": pop_state,
        "window_days": window_days,
    }
    with conn.cursor() as cur:
        cur.execute(CUSTOMER_QUERY_SQL, params)
        rows = list(cur.fetchall())
    return rows


def fetch_homepage_notices(
    conn: psycopg.Connection,
    *,
    naics_code: str,
    set_aside_code: str,
) -> list[dict[str, Any]]:
    params = {
        "naics_code": naics_code,
        "set_aside_code": set_aside_code,
    }
    with conn.cursor() as cur:
        cur.execute(HOMEPAGE_SAMPLE_SQL, params)
        rows = list(cur.fetchall())
    return [
        {
            "title": row["title"],
            "posted_date": row["posted_date"],
            "official_notice_url": row["official_notice_url"],
        }
        for row in rows
    ]
