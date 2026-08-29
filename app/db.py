"""Postgres access for existing public.sam_notices / public.sam_ingest_runs."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.constants import WINDOW_DAYS

log = logging.getLogger(__name__)

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


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url, row_factory=dict_row)


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
