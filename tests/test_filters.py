from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.filters import (
    customer_notices,
    latest_per_solicitation,
    posted_within_window,
    window_cutoff,
)


def _notice(
    *,
    notice_id: str,
    sol: str | None,
    posted: date | None,
    collected: datetime | None = None,
    notice_type: str = "o",
    naics: str = "541511",
    set_aside: str = "SBA",
    pop_state: str | None = "WA",
) -> dict:
    return {
        "notice_id": notice_id,
        "solicitation_number": sol,
        "posted_date": posted,
        "collected_at": collected or datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
        "notice_type": notice_type,
        "naics_code": naics,
        "set_aside_code": set_aside,
        "pop_state": pop_state,
        "title": notice_id,
    }


def test_solicitation_number_dedup_keeps_latest_posted_then_collected() -> None:
    older = _notice(
        notice_id="old",
        sol="N0040626Q0513",
        posted=date(2026, 8, 1),
        collected=datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc),
    )
    newer_same_day_earlier_collect = _notice(
        notice_id="mid",
        sol="N0040626Q0513",
        posted=date(2026, 8, 20),
        collected=datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc),
    )
    newest = _notice(
        notice_id="new",
        sol="N0040626Q0513",
        posted=date(2026, 8, 20),
        collected=datetime(2026, 8, 29, 14, 0, tzinfo=timezone.utc),
    )
    other = _notice(
        notice_id="other",
        sol="OTHER-1",
        posted=date(2026, 8, 15),
    )
    blank_a = _notice(
        notice_id="blank-a",
        sol="",
        posted=date(2026, 8, 18),
    )
    blank_b = _notice(
        notice_id="blank-b",
        sol=None,
        posted=date(2026, 8, 19),
    )

    result = latest_per_solicitation(
        [older, newer_same_day_earlier_collect, newest, other, blank_a, blank_b]
    )
    ids = {row["notice_id"] for row in result}
    assert ids == {"new", "other", "blank-a", "blank-b"}
    assert "old" not in ids
    assert "mid" not in ids


def test_ninety_day_window_includes_cutoff_excludes_older() -> None:
    as_of = date(2026, 8, 29)
    cutoff = window_cutoff(as_of, days=90)
    assert cutoff == date(2026, 5, 31)

    assert posted_within_window(cutoff, as_of=as_of) is True
    assert posted_within_window(cutoff - timedelta(days=1), as_of=as_of) is False
    assert posted_within_window(as_of, as_of=as_of) is True
    assert posted_within_window(None, as_of=as_of) is False


def test_customer_query_applies_type_window_dedup_and_proof_filters() -> None:
    as_of = date(2026, 8, 29)
    in_window = as_of - timedelta(days=10)
    stale = as_of - timedelta(days=91)

    rows = [
        _notice(
            notice_id="keep-latest",
            sol="SAME-SOL",
            posted=in_window,
            collected=datetime(2026, 8, 29, 15, 0, tzinfo=timezone.utc),
        ),
        _notice(
            notice_id="drop-amendment",
            sol="SAME-SOL",
            posted=in_window - timedelta(days=2),
        ),
        _notice(
            notice_id="stale-active-yes",
            sol="STALE-1",
            posted=stale,
        ),
        _notice(
            notice_id="award-skipped-already",
            sol="AWARD-1",
            posted=in_window,
            notice_type="a",
        ),
        _notice(
            notice_id="wrong-naics",
            sol="NAICS-1",
            posted=in_window,
            naics="541512",
        ),
        _notice(
            notice_id="wrong-set-aside",
            sol="SA-1",
            posted=in_window,
            set_aside="HZC",
        ),
        _notice(
            notice_id="other-state",
            sol="STATE-1",
            posted=in_window,
            pop_state="CA",
        ),
        _notice(
            notice_id="keep-sources-sought",
            sol="SS-1",
            posted=in_window,
            notice_type="r",
        ),
    ]

    result = customer_notices(
        rows,
        naics_code="541511",
        set_aside_code="SBA",
        pop_state="WA",
        as_of=as_of,
    )
    ids = [row["notice_id"] for row in result]
    assert ids == ["keep-latest", "keep-sources-sought"]
