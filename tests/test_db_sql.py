from __future__ import annotations

from app.db import CUSTOMER_QUERY_SQL, UPSERT_SQL


def test_upsert_is_idempotent_on_notice_id() -> None:
    assert "ON CONFLICT (notice_id)" in UPSERT_SQL
    assert "INSERT INTO public.sam_notices" in UPSERT_SQL


def test_customer_sql_uses_window_and_solicitation_dedup() -> None:
    assert "posted_date >= (CURRENT_DATE - %(window_days)s::int)" in CUSTOMER_QUERY_SQL
    assert "COALESCE(NULLIF(solicitation_number, ''), notice_id)" in CUSTOMER_QUERY_SQL
    assert "notice_type IN ('o', 'k', 'p', 'r')" in CUSTOMER_QUERY_SQL
