"""Render the public product page. Sample notices are live DB rows or omitted."""

from __future__ import annotations

from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import Any

HOMEPAGE_PATH = Path(__file__).resolve().parent / "static" / "index.html"
SAMPLE_MARKER = "<!-- SAMPLE_NOTICES -->"
OFFICIAL_URL_PREFIX = "https://sam.gov/"


def _posted_date_text(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        text = value.strip()
        return text[:10] if text else None
    return None


def public_sample_notice(row: dict[str, Any]) -> dict[str, str] | None:
    """Keep title, posted_date, official_notice_url. Drop POC and anything else."""
    title = str(row.get("title") or "").strip()
    url = str(row.get("official_notice_url") or "").strip()
    posted = _posted_date_text(row.get("posted_date"))
    if not title or not posted or not url.startswith(OFFICIAL_URL_PREFIX):
        return None
    return {
        "title": title,
        "posted_date": posted,
        "official_notice_url": url,
    }


def render_sample_section(rows: list[dict[str, Any]]) -> str:
    samples = [item for item in (public_sample_notice(row) for row in rows) if item]
    if not samples:
        return ""
    items: list[str] = []
    for sample in samples:
        href = escape(sample["official_notice_url"], quote=True)
        title = escape(sample["title"], quote=True)
        posted = escape(sample["posted_date"], quote=True)
        items.append(
            "<li>"
            f'<a href="{href}">{title}</a>'
            f' <time datetime="{posted}">{posted}</time>'
            "</li>"
        )
    return (
        '<section class="samples">\n'
        "      <h2>Recent 541511 SBA notices</h2>\n"
        "      <ul>\n        "
        + "\n        ".join(items)
        + "\n      </ul>\n"
        "    </section>"
    )


def render_homepage(rows: list[dict[str, Any]] | None = None) -> str:
    template = HOMEPAGE_PATH.read_text(encoding="utf-8")
    return template.replace(SAMPLE_MARKER, render_sample_section(rows or []), 1)
