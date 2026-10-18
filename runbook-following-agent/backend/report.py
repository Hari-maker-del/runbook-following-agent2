"""Generate execution reports and PDF exports."""

import io
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from models import ReportSummary, StepResult, StepStatus
from logger import _session_log_path

LOGS_DIR = Path(__file__).parent / "logs"


def _parse_timestamp(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def generate_report(session_id: str, owner_id: str = "legacy-admin") -> Optional[ReportSummary]:
    """Build a report summary from session log data."""
    path = _session_log_path(session_id, owner_id)
    if not path.exists():
        return None

    data = json.loads(path.read_text(encoding="utf-8"))
    raw_entries = data.get("entries", [])

    # A step can be logged more than once (e.g. "waiting_confirmation" then
    # its final "skipped"/"success"/"failed" state after the user responds,
    # or "failed" then a later "success" after a retry). Keep only the most
    # recent log entry per step so counts reflect one status per step.
    latest_by_step: dict[int, dict] = {}
    for entry in raw_entries:
        latest_by_step[entry.get("step", 0)] = entry
    entries = [latest_by_step[step] for step in sorted(latest_by_step)]

    successful = failed = blocked = skipped = 0
    total_time_ms = 0.0
    step_results: list[StepResult] = []

    for entry in entries:
        status = entry.get("status", "")
        total_time_ms += entry.get("execution_time_ms", 0)

        try:
            step_status = StepStatus(status)
        except ValueError:
            step_status = StepStatus.FAILED

        step_results.append(
            StepResult(
                step=entry.get("step", 0),
                command=entry.get("command", ""),
                status=step_status,
                stdout=entry.get("stdout", ""),
                stderr=entry.get("stderr", ""),
                exit_code=entry.get("exit_code"),
                execution_time_ms=entry.get("execution_time_ms", 0),
                message=entry.get("message", ""),
            )
        )

        if status == StepStatus.SUCCESS.value:
            successful += 1
        elif status == StepStatus.FAILED.value:
            failed += 1
        elif status in (StepStatus.BLOCKED.value, StepStatus.WAITING_CONFIRMATION.value):
            blocked += 1
        elif status == StepStatus.SKIPPED.value:
            skipped += 1

    total_steps = len(entries)
    # Use the full (non-deduped) log for the execution time span, since a
    # retry's final entry can be logged later than other steps despite
    # having a lower step number.
    all_timestamps = sorted(e.get("timestamp") for e in raw_entries if e.get("timestamp"))
    started_at = all_timestamps[0] if all_timestamps else data.get("created_at")
    completed_at = all_timestamps[-1] if all_timestamps else data.get("updated_at")

    duration_ms = total_time_ms
    if started_at and completed_at:
        start_dt = _parse_timestamp(started_at)
        end_dt = _parse_timestamp(completed_at)
        if start_dt and end_dt:
            duration_ms = max(duration_ms, (end_dt - start_dt).total_seconds() * 1000)

    if failed > 0:
        overall = "failed"
    elif blocked > 0:
        overall = "blocked"
    elif successful == total_steps and total_steps > 0:
        overall = "success"
    elif total_steps == 0:
        overall = "empty"
    else:
        overall = "partial"

    return ReportSummary(
        session_id=session_id,
        filename=data.get("filename", ""),
        total_steps=total_steps,
        successful=successful,
        failed=failed,
        blocked=blocked,
        skipped=skipped,
        execution_duration_ms=round(duration_ms, 2),
        overall_status=overall,
        started_at=started_at,
        completed_at=completed_at,
        steps=step_results,
    )


def generate_pdf_report(session_id: str, owner_id: str = "legacy-admin") -> Optional[bytes]:
    """Generate a PDF report for download."""
    summary = generate_report(session_id, owner_id)
    if not summary:
        return None

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        return None

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        textColor=colors.HexColor("#38bdf8"),
        spaceAfter=12,
    )
    body = styles["Normal"]

    elements = [
        Paragraph("Runbook Execution Report", title_style),
        Spacer(1, 0.2 * inch),
        Paragraph(f"<b>Session:</b> {summary.session_id}", body),
        Paragraph(f"<b>Runbook:</b> {summary.filename}", body),
        Paragraph(f"<b>Overall Status:</b> {summary.overall_status.upper()}", body),
        Spacer(1, 0.3 * inch),
    ]

    summary_data = [
        ["Total Steps", str(summary.total_steps)],
        ["Successful", str(summary.successful)],
        ["Failed", str(summary.failed)],
        ["Blocked", str(summary.blocked)],
        ["Skipped", str(summary.skipped)],
        ["Duration (ms)", f"{summary.execution_duration_ms:.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[2.5 * inch, 3 * inch])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#334155")),
                ("PADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    elements.append(summary_table)
    elements.append(Spacer(1, 0.4 * inch))
    elements.append(Paragraph("<b>Step Details</b>", styles["Heading2"]))
    elements.append(Spacer(1, 0.15 * inch))

    for step in summary.steps:
        elements.append(
            Paragraph(
                f"Step {step.step}: <font face='Courier'>{step.command}</font> — "
                f"<b>{step.status.value}</b> ({step.execution_time_ms}ms)",
                body,
            )
        )
        if step.stdout:
            elements.append(Paragraph(f"<font size='8' color='#94a3b8'>stdout: {step.stdout[:200]}</font>", body))
        if step.stderr:
            elements.append(Paragraph(f"<font size='8' color='#f87171'>stderr: {step.stderr[:200]}</font>", body))
        elements.append(Spacer(1, 0.1 * inch))

    doc.build(elements)
    return buffer.getvalue()
