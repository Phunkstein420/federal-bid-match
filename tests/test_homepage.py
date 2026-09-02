from __future__ import annotations

from datetime import date

from app.homepage import public_sample_notice, render_homepage, render_sample_section


def test_public_sample_notice_drops_poc_and_non_sam_urls() -> None:
    kept = public_sample_notice(
        {
            "title": "Widget support",
            "posted_date": date(2026, 9, 1),
            "official_notice_url": "https://sam.gov/opp/abc/view",
            "poc_email": "hidden@example.com",
            "poc_name": "Someone",
        }
    )
    assert kept == {
        "title": "Widget support",
        "posted_date": "2026-09-01",
        "official_notice_url": "https://sam.gov/opp/abc/view",
    }
    assert public_sample_notice(
        {
            "title": "Bad link",
            "posted_date": date(2026, 9, 1),
            "official_notice_url": "javascript:alert(1)",
        }
    ) is None
    assert public_sample_notice({"title": "", "posted_date": date(2026, 9, 1)}) is None


def test_render_sample_section_omits_empty() -> None:
    assert render_sample_section([]) == ""
    html = render_homepage([])
    assert "Recent 541511 SBA notices" not in html
    assert "https://buy.stripe.com/14A28r1Khch97A74EOb3q00" in html
    assert "Douglas Magnuson" in html
    assert "Apex" not in html
    assert "free trial" not in html.lower()
