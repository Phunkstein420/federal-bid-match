from __future__ import annotations

from datetime import date, datetime, timezone

from app.constants import OFFICIAL_NOTICE_URL_TEMPLATE
from app.parse import is_ingest_type, notice_type_code, parse_csv_bytes, row_to_notice
from tests.sample_csv import CSV_HEADERS, FIXED_COLLECTED, FIXED_EXTRACT, csv_row


def _parse(rows: list[str]) -> tuple[int, list[dict]]:
    payload = (CSV_HEADERS + "\n" + "\n".join(rows) + "\n").encode("utf-8")
    return parse_csv_bytes(
        payload,
        source_extract_date=FIXED_EXTRACT,
        collected_at=FIXED_COLLECTED,
    )


def test_csv_parsing_maps_official_headers_and_ignores_csv_link() -> None:
    notice_id = "5bd3ba975744486881126d2e9913c5d4"
    rows_read, notices = _parse(
        [
            csv_row(
                notice_id=notice_id,
                title="Software - Housing Analytics",
                sol="N0040626Q0513",
                posted="2026-08-28",
                type_name="Solicitation",
                extra_link="https://example.invalid/more",
                description="Quoted, multiline\nstill one field.",
            )
        ]
    )
    assert rows_read == 1
    assert len(notices) == 1
    notice = notices[0]
    assert notice["notice_id"] == notice_id
    assert notice["title"] == "Software - Housing Analytics"
    assert notice["solicitation_number"] == "N0040626Q0513"
    assert notice["notice_type"] == "o"
    assert notice["posted_date"] == date(2026, 8, 28)
    assert notice["naics_code"] == "541511"
    assert notice["set_aside_code"] == "SBA"
    assert notice["set_aside"] == "Small Business Set Aside - Total"
    assert (
        notice["agency_path"]
        == "DEPT OF DEFENSE.DEPT OF THE NAVY.NAVSUP FLT LOG CTR PUGET SOUND"
    )
    assert notice["pop_state"] == "WA"
    assert notice["poc_email"] == "jane.doe@example.mil"
    assert notice["official_notice_url"] == OFFICIAL_NOTICE_URL_TEMPLATE.format(
        notice_id=notice_id
    )
    assert "/workspace/contract/" not in notice["official_notice_url"]
    assert notice["description_url"] == "https://example.invalid/more"
    assert notice["resource_links"] == ["https://example.invalid/more"]
    assert notice["is_active"] is True
    assert notice["source_extract_date"] == FIXED_EXTRACT
    assert notice["collected_at"] == FIXED_COLLECTED


def test_csv_parsing_deadline_keeps_offset() -> None:
    _, notices = _parse(
        [
            csv_row(
                notice_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                title="Keep offset",
                sol="SOL-1",
                posted="2026-08-28",
                type_name="Solicitation",
            )
        ]
    )
    deadline = notices[0]["response_deadline"]
    assert deadline is not None
    assert deadline.utcoffset() is not None
    assert deadline.isoformat() == "2026-09-14T15:00:00-04:00"


def test_type_filter_maps_names_and_letters_skips_awards() -> None:
    assert notice_type_code("Solicitation") == "o"
    assert notice_type_code("Combined Synopsis/Solicitation") == "k"
    assert notice_type_code("Presolicitation") == "p"
    assert notice_type_code("Sources Sought") == "r"
    assert notice_type_code("o") == "o"
    assert notice_type_code("Award Notice") is None
    assert notice_type_code("Special Notice") is None
    assert is_ingest_type("Award Notice") is False
    assert is_ingest_type("k") is True

    rows_read, notices = _parse(
        [
            csv_row(
                notice_id="11111111111111111111111111111111",
                title="Sol",
                sol="A",
                posted="2026-08-28",
                type_name="Solicitation",
            ),
            csv_row(
                notice_id="22222222222222222222222222222222",
                title="Combo",
                sol="B",
                posted="2026-08-28",
                type_name="Combined Synopsis/Solicitation",
            ),
            csv_row(
                notice_id="33333333333333333333333333333333",
                title="Pre",
                sol="C",
                posted="2026-08-28",
                type_name="Presolicitation",
            ),
            csv_row(
                notice_id="44444444444444444444444444444444",
                title="SS",
                sol="D",
                posted="2026-08-28",
                type_name="Sources Sought",
            ),
            csv_row(
                notice_id="55555555555555555555555555555555",
                title="Award",
                sol="E",
                posted="2026-08-28",
                type_name="Award Notice",
            ),
            csv_row(
                notice_id="66666666666666666666666666666666",
                title="Special",
                sol="F",
                posted="2026-08-28",
                type_name="Special Notice",
            ),
            csv_row(
                notice_id="77777777777777777777777777777777",
                title="Letter K",
                sol="G",
                posted="2026-08-28",
                type_name="k",
            ),
        ]
    )
    assert rows_read == 7
    types = {n["notice_id"]: n["notice_type"] for n in notices}
    assert types == {
        "11111111111111111111111111111111": "o",
        "22222222222222222222222222222222": "k",
        "33333333333333333333333333333333": "p",
        "44444444444444444444444444444444": "r",
        "77777777777777777777777777777777": "k",
    }
    assert "55555555555555555555555555555555" not in types
    assert "66666666666666666666666666666666" not in types


def test_row_without_notice_id_is_skipped() -> None:
    notice = row_to_notice(
        {
            "NoticeId": "  ",
            "Type": "Solicitation",
            "Title": "Missing id",
        },
        source_extract_date=FIXED_EXTRACT,
        collected_at=FIXED_COLLECTED,
    )
    assert notice is None
