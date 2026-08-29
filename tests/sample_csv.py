"""Shared sample CSV matching official Contract Opportunities headers."""

from __future__ import annotations

from datetime import date, datetime, timezone

CSV_HEADERS = (
    "NoticeId,Title,Sol#,Department/Ind.Agency,CGAC,Sub-Tier,FPDS Code,Office,"
    "AAC Code,PostedDate,Type,BaseType,ArchiveType,ArchiveDate,SetASideCode,"
    "SetASide,ResponseDeadLine,NaicsCode,ClassificationCode,PopStreetAddress,"
    "PopCity,PopState,PopZip,PopCountry,Active,AwardNumber,AwardDate,Award$,"
    "Awardee,PrimaryContactTitle,PrimaryContactFullname,PrimaryContactEmail,"
    "PrimaryContactPhone,PrimaryContactFax,SecondaryContactTitle,"
    "SecondaryContactFullname,SecondaryContactEmail,SecondaryContactPhone,"
    "SecondaryContactFax,OrganizationType,State,City,ZipCode,CountryCode,"
    "AdditionalInfoLink,Link,Description"
)

# Bad Link on purpose: ingest must ignore it and use /opp/{id}/view.
BAD_LINK = "https://sam.gov/workspace/contract/opp/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/view"

FIXED_COLLECTED = datetime(2026, 8, 29, 14, 0, tzinfo=timezone.utc)
FIXED_EXTRACT = date(2026, 8, 29)


def csv_row(
    *,
    notice_id: str,
    title: str,
    sol: str,
    posted: str,
    type_name: str,
    set_aside_code: str = "SBA",
    set_aside: str = "Small Business Set Aside - Total",
    naics: str = "541511",
    pop_state: str = "WA",
    active: str = "Yes",
    deadline: str = "2026-09-14T15:00:00-04:00",
    agency: str = "DEPT OF DEFENSE",
    sub: str = "DEPT OF THE NAVY",
    office: str = "NAVSUP FLT LOG CTR PUGET SOUND",
    city: str = "Bremerton",
    zip_code: str = "98314",
    poc_name: str = "Jane Doe",
    poc_email: str = "jane.doe@example.mil",
    poc_phone: str = "360-555-0100",
    extra_link: str = "",
    description: str = "Line one of the description.",
) -> str:
    fields = [
        notice_id,
        title,
        sol,
        agency,
        "017",
        sub,
        "1700",
        office,
        "N00406",
        posted,
        type_name,
        type_name,
        "auto15",
        "2026-12-01",
        set_aside_code,
        set_aside,
        deadline,
        naics,
        "D399",
        "",
        city,
        pop_state,
        zip_code,
        "USA",
        active,
        "",
        "",
        "",
        "",
        "",
        poc_name,
        poc_email,
        poc_phone,
        "",
        "",
        "",
        "",
        "",
        "",
        "OFFICE",
        "WA",
        "Bremerton",
        "98314",
        "USA",
        extra_link,
        BAD_LINK,
        description,
    ]
    quoted = ['"' + f.replace('"', '""') + '"' for f in fields]
    return ",".join(quoted)
