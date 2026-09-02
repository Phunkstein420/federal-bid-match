"""CLI and shared helpers for the customer notice query."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from typing import Any

from app.config import MissingEnvError, Settings
from app.constants import DEFAULT_NAICS, DEFAULT_SET_ASIDE_CODE, WINDOW_DAYS
from app.db import connect, fetch_customer_notices, fetch_homepage_notices


def json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"not JSON serializable: {type(value)!r}")


def query_notices(
    *,
    naics: str = DEFAULT_NAICS,
    set_aside: str = DEFAULT_SET_ASIDE_CODE,
    pop_state: str | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    settings = settings or Settings.from_env()
    database_url = settings.require_database_url()
    conn = connect(database_url)
    try:
        return fetch_customer_notices(
            conn,
            naics_code=naics,
            set_aside_code=set_aside,
            pop_state=pop_state,
            window_days=WINDOW_DAYS,
        )
    finally:
        conn.close()


def query_homepage_notices(*, settings: Settings | None = None) -> list[dict[str, Any]]:
    settings = settings or Settings.from_env()
    database_url = settings.require_database_url()
    conn = connect(database_url)
    try:
        return fetch_homepage_notices(
            conn,
            naics_code=DEFAULT_NAICS,
            set_aside_code=DEFAULT_SET_ASIDE_CODE,
        )
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Query customer-ready SAM notices: types o/k/p/r, latest per "
            "solicitation number, posted in the last 90 days."
        )
    )
    parser.add_argument("--naics", default=DEFAULT_NAICS)
    parser.add_argument("--set-aside", default=DEFAULT_SET_ASIDE_CODE, dest="set_aside")
    parser.add_argument("--pop-state", default=None, dest="pop_state")
    args = parser.parse_args(argv)

    try:
        rows = query_notices(
            naics=args.naics,
            set_aside=args.set_aside,
            pop_state=args.pop_state,
        )
    except MissingEnvError as exc:
        print(exc, file=sys.stderr)
        return 2
    print(json.dumps(rows, default=json_default, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
