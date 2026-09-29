"""Case PDF export (PROJECT_PLAN.md Phase 5.4). WeasyPrint's native libs
(Pango/Cairo/GDK-PixBuf) aren't installed on this dev machine, which is
exactly the degrade-gracefully path export.py is built for - so
render_case_pdf's ExportUnavailableError branch is exercised for real here,
and _render_html (the pure HTML-building part) is tested directly."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from backend.app.services.onboarding.export import ExportUnavailableError, _render_html, render_case_pdf

CASE = SimpleNamespace(id=7, tier="review", state="PENDING_L1", decision=None)
HIT = SimpleNamespace(matched_name="Jane Doe", composite_score=82, disposition="pending", disposition_reason=None)
NOTE = SimpleNamespace(body="Reviewed and escalated")
EVENT = SimpleNamespace(created_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC), event_type="ASSIGNED")


def test_render_html_includes_case_and_hit_details():
    html = _render_html(CASE, [HIT], [NOTE], [EVENT])
    assert "Case 7" in html
    assert "Jane Doe" in html
    assert "82" in html
    assert "Reviewed and escalated" in html
    assert "ASSIGNED" in html


def test_render_html_handles_empty_lists():
    html = _render_html(CASE, [], [], [])
    assert "Case 7" in html
    assert "<table" in html


def test_render_html_shows_pending_when_no_decision_yet():
    html = _render_html(CASE, [], [], [])
    assert "pending" in html


def test_render_case_pdf_raises_export_unavailable_when_weasyprint_native_libs_missing():
    try:
        import weasyprint  # noqa: F401

        pytest.skip("weasyprint's native libraries are installed in this environment")
    except OSError:
        pass  # expected in this dev environment; continue to exercise the real error path

    with pytest.raises(ExportUnavailableError, match="native libraries"):
        render_case_pdf(CASE, [HIT], [NOTE], [EVENT])
