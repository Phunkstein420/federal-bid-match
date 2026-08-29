"""Customer-facing notice filters: ingest types, 90-day window, latest per Sol#."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.constants import INGEST_NOTICE_TYPES, WINDOW_DAYS


def as_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


def window_cutoff(as_of: date | datetime, *, days: int = WINDOW_DAYS) -> date:
    return as_date(as_of) - timedelta(days=days)


def posted_within_window(
    posted_date: date | None,
    *,
    as_of: date | datetime,
    days: int = WINDOW_DAYS,
) -> bool:
    if posted_date is None:
        return False
    return posted_date >= window_cutoff(as_of, days=days)


def _sort_key(notice: dict[str, Any]) -> tuple[date, datetime]:
    posted = notice.get("posted_date") or date.min
    collected = notice.get("collected_at") or datetime.min.replace(tzinfo=timezone.utc)
    if isinstance(collected, datetime) and collected.tzinfo is None:
        collected = collected.replace(tzinfo=timezone.utc)
    return (posted, collected)


def solicitation_group_key(notice: dict[str, Any]) -> str:
    """Amendments share a Sol#; blank Sol# stays unique per notice_id."""
    sol = (notice.get("solicitation_number") or "").strip()
    if sol:
        return sol
    return notice["notice_id"]


def latest_per_solicitation(notices: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for notice in notices:
        key = solicitation_group_key(notice)
        previous = best.get(key)
        if previous is None or _sort_key(notice) > _sort_key(previous):
            best[key] = notice
    return list(best.values())


def customer_notices(
    notices: Sequence[dict[str, Any]],
    *,
    naics_code: str,
    set_aside_code: str,
    pop_state: str | None = None,
    as_of: date | datetime | None = None,
    window_days: int = WINDOW_DAYS,
) -> list[dict[str, Any]]:
    """Default query: o/k/p/r, last 90 days, latest row per solicitation_number."""
    as_of = as_of or datetime.now(timezone.utc)
    naics_code = naics_code.strip()
    set_aside_code = set_aside_code.strip()
    state = pop_state.strip().upper() if pop_state else None

    filtered: list[dict[str, Any]] = []
    for notice in notices:
        if notice.get("notice_type") not in INGEST_NOTICE_TYPES:
            continue
        if notice.get("naics_code") != naics_code:
            continue
        if notice.get("set_aside_code") != set_aside_code:
            continue
        if state and (notice.get("pop_state") or "").upper() != state:
            continue
        if not posted_within_window(
            notice.get("posted_date"),
            as_of=as_of,
            days=window_days,
        ):
            continue
        filtered.append(notice)

    latest = latest_per_solicitation(filtered)
    latest.sort(key=_sort_key, reverse=True)
    return latest
