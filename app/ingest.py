"""Download the public SAM.gov CSV and upsert o/k/p/r NAICS 541511 SBA notices."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from uuid import UUID

from app.config import MissingEnvError, Settings
from app.constants import CSV_DOWNLOAD_URL, INGEST_SOURCE_CSV
from app.db import (
    connect,
    finish_ingest_run,
    start_ingest_run,
    upsert_notices,
)
from app.download import CsvDownloadError, open_csv_stream
from app.parse import iter_notices_from_csv, text_stream_from_binary

log = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 500
INGEST_NOTES = "csv ingest types o/k/p/r NAICS 541511 SBA; upsert on notice_id"


def run_ingest(
    *,
    settings: Settings | None = None,
    csv_url: str = CSV_DOWNLOAD_URL,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, int | str]:
    settings = settings or Settings.from_env()
    database_url = settings.require_database_url()

    collected_at = datetime.now(timezone.utc)
    rows_read = 0
    rows_upserted = 0
    run_id: UUID | None = None

    conn = connect(database_url)
    try:
        run_id = start_ingest_run(conn, source=INGEST_SOURCE_CSV, notes=INGEST_NOTES)
        log.info("sam_ingest_runs started id=%s source=csv", run_id)

        stream, extract_date = open_csv_stream(csv_url)
        try:
            text = text_stream_from_binary(stream)
            pending: list[dict] = []
            for rows_read, notice in iter_notices_from_csv(
                text,
                source_extract_date=extract_date,
                collected_at=collected_at,
            ):
                if notice is None:
                    continue
                pending.append(notice)
                if len(pending) >= batch_size:
                    rows_upserted += upsert_notices(conn, pending)
                    pending = []
                    if rows_upserted % (batch_size * 10) == 0:
                        log.info("upserted %s notices so far", rows_upserted)
            if pending:
                rows_upserted += upsert_notices(conn, pending)
        finally:
            stream.close()

        finish_ingest_run(
            conn,
            run_id,
            rows_read=rows_read,
            rows_upserted=rows_upserted,
            status="ok",
            notes=INGEST_NOTES,
        )
        log.info(
            "ingest ok rows_read=%s rows_upserted=%s",
            rows_read,
            rows_upserted,
        )
        return {
            "run_id": str(run_id),
            "rows_read": rows_read,
            "rows_upserted": rows_upserted,
            "status": "ok",
        }
    except Exception as exc:
        status = "error"
        notes = f"{INGEST_NOTES}; error={type(exc).__name__}"
        log.exception("ingest failed")
        if run_id is not None:
            try:
                finish_ingest_run(
                    conn,
                    run_id,
                    rows_read=rows_read,
                    rows_upserted=rows_upserted,
                    status=status,
                    notes=notes,
                )
            except Exception:
                log.exception("failed to record ingest error on sam_ingest_runs")
        raise
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Download the public SAM.gov Contract Opportunities CSV and upsert "
            "o/k/p/r notices with NAICS 541511 and set-aside SBA."
        )
    )
    parser.add_argument(
        "--url",
        default=CSV_DOWNLOAD_URL,
        help="Public Data Services CSV URL (default: official Contract Opportunities extract)",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        run_ingest(csv_url=args.url, batch_size=args.batch_size)
    except MissingEnvError as exc:
        log.error("%s", exc)
        return 2
    except CsvDownloadError as exc:
        log.error("download failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
