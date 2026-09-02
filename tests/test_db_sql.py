from __future__ import annotations

from app.db import CUSTOMER_QUERY_SQL, HOMEPAGE_SAMPLE_SQL, UPSERT_SQL


def test_upsert_is_idempotent_on_notice_id() -> None:
    assert "ON CONFLICT (notice_id)" in UPSERT_SQL
    assert "INSERT INTO public.sam_notices" in UPSERT_SQL


def test_customer_sql_uses_window_and_solicitation_dedup() -> None:
    assert "posted_date >= (CURRENT_DATE - %(window_days)s::int)" in CUSTOMER_QUERY_SQL
    assert "COALESCE(NULLIF(solicitation_number, ''), notice_id)" in CUSTOMER_QUERY_SQL
    assert "notice_type IN ('o', 'k', 'p', 'r')" in CUSTOMER_QUERY_SQL


def test_homepage_sample_sql_is_public_541511_sba_slice() -> None:
    assert "is_active IS TRUE" in HOMEPAGE_SAMPLE_SQL
    assert "naics_code = %(naics_code)s" in HOMEPAGE_SAMPLE_SQL
    assert "set_aside_code = %(set_aside_code)s" in HOMEPAGE_SAMPLE_SQL
    assert "COALESCE(NULLIF(solicitation_number, ''), notice_id)" in HOMEPAGE_SAMPLE_SQL
    assert "ORDER BY posted_date DESC NULLS LAST, collected_at DESC" in HOMEPAGE_SAMPLE_SQL
    assert "LIMIT 3" in HOMEPAGE_SAMPLE_SQL
    assert "SELECT title, posted_date, official_notice_url" in HOMEPAGE_SAMPLE_SQL
    for secret_col in ("poc_name", "poc_email", "poc_phone"):
        assert secret_col not in HOMEPAGE_SAMPLE_SQL
