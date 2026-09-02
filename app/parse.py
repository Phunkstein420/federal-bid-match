"""Map SAM.gov Contract Opportunities CSV rows onto sam_notices columns."""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterable, Iterator, Mapping
from datetime import date, datetime, timezone
from typing import Any, BinaryIO, TextIO

from app.constants import (
    DEFAULT_NAICS,
    DEFAULT_SET_ASIDE_CODE,
    INGEST_NOTICE_TYPES,
    OFFICIAL_NOTICE_URL_TEMPLATE,
    TYPE_NAME_TO_CODE,
)

_WS = re.compile(r"\s+")


def official_notice_url(notice_id: str) -> str:
    return OFFICIAL_NOTICE_URL_TEMPLATE.format(notice_id=notice_id.strip())


def normalize_type_key(raw: str | None) -> str:
    if not raw:
        return ""
    return _WS.sub(" ", raw.strip().lower())


def notice_type_code(raw: str | None) -> str | None:
    """Return o/k/p/r or None if the row is not ingestable (awards, etc.)."""
    key = normalize_type_key(raw)
    if not key:
        return None
    return TYPE_NAME_TO_CODE.get(key)


def is_ingest_type(raw: str | None) -> bool:
    code = notice_type_code(raw)
    return code in INGEST_NOTICE_TYPES


def matches_ingest_naics_and_set_aside(
    naics_code: str | None,
    set_aside_code: str | None,
) -> bool:
    """Production ingest slice: NAICS 541511 and set-aside SBA only."""
    naics = (naics_code or "").strip()
    set_aside = (set_aside_code or "").strip().upper()
    return naics == DEFAULT_NAICS and set_aside == DEFAULT_SET_ASIDE_CODE


def blank_to_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_posted_date(raw: str | None) -> date | None:
    text = blank_to_none(raw)
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def parse_deadline(raw: str | None) -> datetime | None:
    text = blank_to_none(raw)
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        posted = parse_posted_date(text)
        if posted is None:
            return None
        return datetime(posted.year, posted.month, posted.day, tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def parse_active(raw: str | None) -> bool:
    text = (raw or "").strip().lower()
    if text in {"yes", "y", "true", "1"}:
        return True
    if text in {"no", "n", "false", "0"}:
        return False
    # Default to True when Active is blank so we do not drop otherwise valid notices.
    return True


def agency_path_from_row(row: Mapping[str, str]) -> str | None:
    parts: list[str] = []
    for key in ("Department/Ind.Agency", "Sub-Tier", "Office"):
        value = blank_to_none(row.get(key))
        if value:
            parts.append(value)
    return ".".join(parts) or None


def resource_links_from_row(row: Mapping[str, str]) -> list[str] | None:
    links: list[str] = []
    extra = blank_to_none(row.get("AdditionalInfoLink"))
    if extra:
        links.append(extra)
    return links or None


def row_to_notice(
    row: Mapping[str, str],
    *,
    source_extract_date: date,
    collected_at: datetime,
) -> dict[str, Any] | None:
    """Return a sam_notices dict, or None if the row should be skipped."""
    notice_id = blank_to_none(row.get("NoticeId"))
    if not notice_id:
        return None
    notice_type = notice_type_code(row.get("Type"))
    if notice_type not in INGEST_NOTICE_TYPES:
        return None
    naics_code = blank_to_none(row.get("NaicsCode"))
    set_aside_code = blank_to_none(row.get("SetASideCode"))
    if not matches_ingest_naics_and_set_aside(naics_code, set_aside_code):
        return None

    description_url = blank_to_none(row.get("AdditionalInfoLink"))
    links = resource_links_from_row(row)

    return {
        "notice_id": notice_id,
        "title": blank_to_none(row.get("Title")),
        "solicitation_number": blank_to_none(row.get("Sol#")),
        "notice_type": notice_type,
        "posted_date": parse_posted_date(row.get("PostedDate")),
        "response_deadline": parse_deadline(row.get("ResponseDeadLine")),
        "naics_code": naics_code,
        "set_aside": blank_to_none(row.get("SetASide")),
        "set_aside_code": set_aside_code,
        "classification_code": blank_to_none(row.get("ClassificationCode")),
        "agency_path": agency_path_from_row(row),
        "pop_city": blank_to_none(row.get("PopCity")),
        "pop_state": blank_to_none(row.get("PopState")),
        "pop_zip": blank_to_none(row.get("PopZip")),
        "poc_name": blank_to_none(row.get("PrimaryContactFullname")),
        "poc_email": blank_to_none(row.get("PrimaryContactEmail")),
        "poc_phone": blank_to_none(row.get("PrimaryContactPhone")),
        "description_url": description_url,
        "resource_links": links,
        "official_notice_url": official_notice_url(notice_id),
        "source_extract_date": source_extract_date,
        "collected_at": collected_at,
        "is_active": parse_active(row.get("Active")),
    }


def iter_csv_rows(text_stream: TextIO) -> Iterator[dict[str, str]]:
    reader = csv.DictReader(text_stream)
    for row in reader:
        yield {k: (v if v is not None else "") for k, v in row.items()}


def iter_notices_from_csv(
    text_stream: TextIO,
    *,
    source_extract_date: date,
    collected_at: datetime,
) -> Iterator[tuple[int, dict[str, Any] | None]]:
    """Yield (1-based data row number, notice-or-None) for every CSV data row."""
    for index, row in enumerate(iter_csv_rows(text_stream), start=1):
        yield index, row_to_notice(
            row,
            source_extract_date=source_extract_date,
            collected_at=collected_at,
        )


def parse_csv_bytes(
    data: bytes,
    *,
    source_extract_date: date,
    collected_at: datetime,
) -> tuple[int, list[dict[str, Any]]]:
    """Parse a complete CSV payload. Returns (rows_read, ingestible notices)."""
    text = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8-sig", errors="replace", newline="")
    rows_read = 0
    notices: list[dict[str, Any]] = []
    for rows_read, notice in iter_notices_from_csv(
        text,
        source_extract_date=source_extract_date,
        collected_at=collected_at,
    ):
        if notice is not None:
            notices.append(notice)
    return rows_read, notices


def text_stream_from_binary(binary: BinaryIO) -> TextIO:
    return io.TextIOWrapper(binary, encoding="utf-8-sig", errors="replace", newline="")


def dumps_resource_links(links: list[str] | None) -> str | None:
    if not links:
        return None
    return json.dumps(links)


def batched(items: Iterable[Any], size: int) -> Iterator[list[Any]]:
    batch: list[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch
