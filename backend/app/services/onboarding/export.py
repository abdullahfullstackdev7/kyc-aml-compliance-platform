"""Case export to PDF for regulators. See PROJECT_PLAN.md Phase 5.4.

Requires WeasyPrint's native dependencies (Pango, Cairo, GDK-PixBuf), which
ship in the project's Docker image (infra/) but are not always present on a
bare developer machine; callers should catch ExportUnavailableError and
surface a clear message rather than a raw import failure.
"""

from __future__ import annotations

from backend.app.models.cases import Case, CaseEvent, CaseNote
from backend.app.models.screening import ScreeningHit


class ExportUnavailableError(Exception):
    pass


def render_case_pdf(
    case: Case, hits: list[ScreeningHit], notes: list[CaseNote], events: list[CaseEvent]
) -> bytes:
    try:
        from weasyprint import HTML
    except OSError as exc:
        raise ExportUnavailableError(
            "PDF export requires WeasyPrint's native libraries (Pango/Cairo/GDK-PixBuf), "
            "not installed in this environment"
        ) from exc

    html = _render_html(case, hits, notes, events)
    return HTML(string=html).write_pdf()


def _render_html(
    case: Case, hits: list[ScreeningHit], notes: list[CaseNote], events: list[CaseEvent]
) -> str:
    hit_rows = "".join(
        f"<tr><td>{h.matched_name}</td><td>{h.composite_score}</td>"
        f"<td>{h.disposition}</td><td>{h.disposition_reason or ''}</td></tr>"
        for h in hits
    )
    note_rows = "".join(f"<li>{n.body}</li>" for n in notes)
    event_rows = "".join(
        f"<li>{e.created_at.isoformat() if e.created_at else ''} - {e.event_type}</li>"
        for e in events
    )

    return f"""
    <html>
    <head><meta charset="utf-8"><title>Case {case.id}</title></head>
    <body>
      <h1>SentinelKYC Case Report</h1>
      <p>Case ID: {case.id} | Tier: {case.tier} | State: {case.state} | Decision: {case.decision or "pending"}</p>
      <h2>Screening Hits</h2>
      <table border="1" cellpadding="4">
        <tr><th>Matched Name</th><th>Score</th><th>Disposition</th><th>Reason</th></tr>
        {hit_rows}
      </table>
      <h2>Notes</h2>
      <ul>{note_rows}</ul>
      <h2>Timeline</h2>
      <ul>{event_rows}</ul>
      <p><em>Demonstration environment. All customer, client and financial records are
      synthetic. Sanctions data is sourced from the U.S. Department of the Treasury.</em></p>
    </body>
    </html>
    """
