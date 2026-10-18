"""
Runbook Following Agent — FastAPI backend.

Provides endpoints to upload, parse, execute, log, and report on Markdown runbooks.
"""

import asyncio
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from allowlist import classify_command
from executor import execute_command
from logger import append_log, create_session_log, get_session_logs, list_sessions
from models import (
    ConfirmRequest,
    ExecutionState,
    PauseResumeRequest,
    ParseRequest,
    RetryRequest,
    RunbookStep,
    StepResult,
    StepStatus,
)
from parser import parse_markdown_file, steps_to_json
from report import generate_pdf_report, generate_report

RUNBOOKS_DIR = Path(__file__).parent / "runbooks"
RUNBOOKS_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = 1_048_576
RUNBOOK_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,119}\.md$", re.IGNORECASE)
DEFAULT_CORS_ORIGINS = (
    "https://runbook-following-agent2.vercel.app,"
    "http://localhost:5173,http://127.0.0.1:5173"
)

app = FastAPI(
    title="Runbook Following Agent",
    description="AI-powered agent for safely executing operational runbooks",
    version="1.0.0",
)

allowed_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    """Add baseline browser security headers to API responses."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    return response

# In-memory execution session store
_sessions: dict[str, dict] = {}
_event_queues: dict[str, asyncio.Queue] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_runbook_path(filename: str) -> Path:
    if not filename or not RUNBOOK_NAME_PATTERN.fullmatch(filename) or Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="Invalid runbook filename")
    workspace = RUNBOOKS_DIR.resolve()
    path = (RUNBOOKS_DIR / filename).resolve()
    try:
        path.relative_to(workspace)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Runbook path must stay inside the runbook workspace") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Runbook '{filename}' not found")
    return path


def _validate_session_id(session_id: str) -> str:
    try:
        return str(uuid.UUID(session_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid session_id") from exc


async def _emit_event(session_id: str, event: dict) -> None:
    """Push an event to SSE subscribers."""
    if session_id in _event_queues:
        await _event_queues[session_id].put(event)


def _upsert_result(session: dict, result: StepResult) -> None:
    """Add a step result, replacing any prior result for the same step.

    Without this, retrying a step or resolving a confirmation would append
    a second StepResult for the same step number instead of replacing the
    old one — leaving stale/duplicate entries in session["results"].
    """
    results = session.setdefault("results", [])
    for i, existing in enumerate(results):
        if existing.step == result.step:
            results[i] = result
            return
    results.append(result)


def _build_execution_state(session: dict) -> ExecutionState:
    total = len(session.get("steps", []))
    current = session.get("current_step_index", 0)
    progress = (current / total * 100) if total else 0

    return ExecutionState(
        session_id=session["session_id"],
        filename=session["filename"],
        status=session["status"],
        current_step=session.get("current_step_num", 0),
        total_steps=total,
        progress_percent=round(progress, 1),
        steps=session.get("steps", []),
        results=session.get("results", []),
        started_at=session.get("started_at"),
        completed_at=session.get("completed_at"),
        pending_confirmation=session.get("pending_confirmation"),
    )


async def _run_step(session_id: str, step: RunbookStep, force: bool = False) -> StepResult:
    """Execute or block a single step based on classification."""
    session = _sessions[session_id]
    classification = classify_command(step.command)

    # Approval may authorize a risky command, never a disallowed one.
    if classification == "disallowed":
        result = StepResult(
            step=step.step,
            command=step.command,
            status=StepStatus.BLOCKED,
            message="Command not on allowlist. Execution blocked for safety.",
        )
        await asyncio.to_thread(
            append_log,
            session_id,
            step.step,
            step.command,
            StepStatus.BLOCKED.value,
            message=result.message,
        )
        step.status = StepStatus.BLOCKED
        return result

    if classification == "risky" and not force:
        result = StepResult(
            step=step.step,
            command=step.command,
            status=StepStatus.WAITING_CONFIRMATION,
            message="Risky command detected. Awaiting user confirmation.",
        )
        session["status"] = "waiting_confirmation"
        session["pending_confirmation"] = {
            "step": step.step,
            "command": step.command,
            "message": "Risky command detected. Continue?",
        }
        await asyncio.to_thread(
            append_log,
            session_id,
            step.step,
            step.command,
            StepStatus.WAITING_CONFIRMATION.value,
            message=result.message,
        )
        step.status = StepStatus.WAITING_CONFIRMATION
        await _emit_event(session_id, {"type": "confirmation_required", "step": step.step, "command": step.command})
        return result

    # Execute the command
    step.status = StepStatus.RUNNING
    await _emit_event(session_id, {"type": "step_start", "step": step.step, "command": step.command})

    output = await asyncio.to_thread(
        execute_command, step.command, str(RUNBOOKS_DIR), allow_risky=force
    )
    status = StepStatus.SUCCESS if output["success"] else StepStatus.FAILED

    result = StepResult(
        step=step.step,
        command=step.command,
        status=status,
        stdout=output["stdout"],
        stderr=output["stderr"],
        exit_code=output["exit_code"],
        execution_time_ms=output["execution_time_ms"],
    )

    await asyncio.to_thread(
        append_log,
        session_id,
        step.step,
        step.command,
        status.value,
        stdout=output["stdout"],
        stderr=output["stderr"],
        exit_code=output["exit_code"],
        execution_time_ms=output["execution_time_ms"],
    )

    step.status = status
    await _emit_event(
        session_id,
        {
            "type": "step_complete",
            "step": step.step,
            "status": status.value,
            "stdout": output["stdout"],
            "stderr": output["stderr"],
            "exit_code": output["exit_code"],
            "execution_time_ms": output["execution_time_ms"],
        },
    )
    return result


async def _execute_session(session_id: str, start_index: int = 0) -> None:
    """Run all steps in a session, respecting pause and confirmation."""
    session = _sessions.get(session_id)
    if not session:
        return

    steps: list[RunbookStep] = session["steps"]
    session["status"] = "running"
    session["started_at"] = session.get("started_at") or _now_iso()

    for idx in range(start_index, len(steps)):
        # Pause check
        while session.get("paused"):
            session["status"] = "paused"
            await asyncio.sleep(0.3)
            if session.get("cancelled"):
                return

        session["status"] = "running"
        session["current_step_index"] = idx
        session["current_step_num"] = steps[idx].step

        step = steps[idx]

        # Skip already completed steps unless retrying
        if step.status == StepStatus.SUCCESS and not session.get("retry_step") == step.step:
            continue

        if session.get("retry_step") == step.step:
            session["retry_step"] = None
            step.status = StepStatus.PENDING

        result = await _run_step(session_id, step)

        if result.status == StepStatus.WAITING_CONFIRMATION:
            session["waiting_at_index"] = idx
            return

        _upsert_result(session, result)

        if result.status == StepStatus.FAILED and not session.get("continue_on_failure"):
            session["status"] = "failed"
            session["completed_at"] = _now_iso()
            await _emit_event(session_id, {"type": "execution_failed", "step": step.step})
            return

    session["status"] = "completed"
    session["completed_at"] = _now_iso()
    session["current_step_index"] = len(steps)
    await _emit_event(session_id, {"type": "execution_complete"})


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------


@app.get("/")
async def root():
    return {"service": "Runbook Following Agent", "status": "running"}


@app.post("/upload")
async def upload_runbook(file: UploadFile = File(...)):
    """Upload a Markdown runbook file."""
    if not file.filename or not RUNBOOK_NAME_PATTERN.fullmatch(file.filename) or Path(file.filename).name != file.filename:
        raise HTTPException(status_code=400, detail="Use a simple .md filename (letters, numbers, spaces, dots, dashes, underscores)")
    safe_name = file.filename
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Runbook upload exceeds the 1 MiB limit")
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Runbook must be UTF-8 encoded Markdown") from exc
    dest = (RUNBOOKS_DIR / safe_name).resolve()
    try:
        dest.relative_to(RUNBOOKS_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid upload destination") from exc
    dest.write_bytes(content)

    return {
        "message": "Runbook uploaded successfully",
        "filename": safe_name,
        "size_bytes": len(content),
    }


@app.post("/parse")
async def parse_runbook(request: ParseRequest):
    """Parse a uploaded runbook into numbered steps."""
    path = _get_runbook_path(request.filename)
    steps = parse_markdown_file(path)
    return {
        "filename": request.filename,
        "steps": steps_to_json(steps),
        "total_steps": len(steps),
        "steps_detail": [s.model_dump() for s in steps],
    }


@app.post("/execute")
async def start_execution(request: dict):
    """
    Start or continue runbook execution.
    Body: { filename, session_id?, start_from_step? }
    """
    filename = request.get("filename")
    if not filename:
        raise HTTPException(status_code=400, detail="filename is required")

    path = _get_runbook_path(filename)
    steps = parse_markdown_file(path)

    session_id = _validate_session_id(request.get("session_id")) if request.get("session_id") else str(uuid.uuid4())
    start_from = request.get("start_from_step", 1)
    if not isinstance(start_from, int) or isinstance(start_from, bool) or start_from < 1:
        raise HTTPException(status_code=400, detail="start_from_step must be a positive integer")

    if session_id in _sessions and _sessions[session_id].get("filename") != filename:
        raise HTTPException(status_code=409, detail="Session belongs to a different runbook")
    if session_id in _sessions and _sessions[session_id].get("status") in {"running", "paused", "waiting_confirmation"}:
        raise HTTPException(status_code=409, detail="Session is already active")
    if session_id not in _sessions:
        await asyncio.to_thread(create_session_log, session_id, filename)
        _sessions[session_id] = {
            "session_id": session_id,
            "filename": filename,
            "steps": steps,
            "results": [],
            "status": "pending",
            "paused": False,
            "current_step_index": 0,
            "current_step_num": 0,
            "continue_on_failure": request.get("continue_on_failure", False),
        }
        _event_queues[session_id] = asyncio.Queue()

    session = _sessions[session_id]

    # Find start index from step number
    start_index = 0
    for i, s in enumerate(steps):
        if s.step >= start_from:
            start_index = i
            break

    session["paused"] = False
    asyncio.create_task(_execute_session(session_id, start_index))

    return {
        "session_id": session_id,
        "message": "Execution started",
        "state": _build_execution_state(session).model_dump(),
    }


@app.post("/execute/confirm")
async def confirm_risky_step(request: ConfirmRequest):
    """Approve or reject a risky command."""
    request.session_id = _validate_session_id(request.session_id)
    session = _sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    pending = session.get("pending_confirmation")
    if not pending or pending.get("step") != request.step:
        raise HTTPException(status_code=400, detail="No pending confirmation for this step")

    step_obj = next((s for s in session["steps"] if s.step == request.step), None)
    if not step_obj:
        raise HTTPException(status_code=404, detail="Step not found")

    session["pending_confirmation"] = None

    if not request.approved:
        result = StepResult(
            step=request.step,
            command=step_obj.command,
            status=StepStatus.SKIPPED,
            message="User declined risky command execution.",
        )
        await asyncio.to_thread(
            append_log,
            request.session_id,
            request.step,
            step_obj.command,
            StepStatus.SKIPPED.value,
            message=result.message,
        )
        step_obj.status = StepStatus.SKIPPED
        _upsert_result(session, result)
        await _emit_event(request.session_id, {"type": "step_skipped", "step": request.step})

        # Continue with next step
        waiting_idx = session.get("waiting_at_index", 0)
        asyncio.create_task(_execute_session(request.session_id, waiting_idx + 1))
        return {"message": "Step skipped", "state": _build_execution_state(session).model_dump()}

    # User approved — force execute
    result = await _run_step(request.session_id, step_obj, force=True)
    _upsert_result(session, result)

    waiting_idx = session.get("waiting_at_index", 0)
    asyncio.create_task(_execute_session(request.session_id, waiting_idx + 1))

    return {"message": "Step executed after confirmation", "result": result.model_dump(), "state": _build_execution_state(session).model_dump()}


@app.post("/execute/pause")
async def pause_execution(request: PauseResumeRequest):
    """Pause an active execution session."""
    session = _sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session["paused"] = True
    session["status"] = "paused"
    await _emit_event(request.session_id, {"type": "paused"})
    return {"message": "Execution paused", "state": _build_execution_state(session).model_dump()}


@app.post("/execute/resume")
async def resume_execution(request: PauseResumeRequest):
    """Resume a paused execution session."""
    session = _sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session["paused"] = False
    current_idx = session.get("current_step_index", 0)
    asyncio.create_task(_execute_session(request.session_id, current_idx))
    await _emit_event(request.session_id, {"type": "resumed"})
    return {"message": "Execution resumed", "state": _build_execution_state(session).model_dump()}


@app.post("/execute/retry")
async def retry_step(request: RetryRequest):
    """Retry a failed step."""
    session = _sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    step_obj = next((s for s in session["steps"] if s.step == request.step), None)
    if not step_obj:
        raise HTTPException(status_code=404, detail="Step not found")

    step_obj.status = StepStatus.PENDING
    session["retry_step"] = request.step
    session["paused"] = False

    step_idx = next(i for i, s in enumerate(session["steps"]) if s.step == request.step)
    asyncio.create_task(_execute_session(request.session_id, step_idx))

    return {"message": f"Retrying step {request.step}", "state": _build_execution_state(session).model_dump()}


@app.get("/execute/state/{session_id}")
async def get_execution_state(session_id: str):
    """Get current execution state for polling."""
    session_id = _validate_session_id(session_id)
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _build_execution_state(session).model_dump()


@app.get("/execute/stream/{session_id}")
async def stream_execution(session_id: str):
    """Server-Sent Events stream for live execution updates."""
    session_id = _validate_session_id(session_id)
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    if session_id not in _event_queues:
        _event_queues[session_id] = asyncio.Queue()

    queue = _event_queues[session_id]

    async def event_generator():
        import json

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("execution_complete", "execution_failed"):
                    break
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/logs")
async def get_logs(session_id: Optional[str] = Query(None)):
    """Return execution logs, optionally filtered by session."""
    if session_id:
        session_id = _validate_session_id(session_id)
        entries = get_session_logs(session_id)
        return {"session_id": session_id, "entries": entries}

    return {"sessions": list_sessions(), "entries": get_session_logs()}


@app.get("/report")
async def get_report(session_id: str = Query(...)):
    """Generate execution report for a session."""
    session_id = _validate_session_id(session_id)
    report = generate_report(session_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found for session")
    return report.model_dump()


@app.get("/report/pdf")
async def download_report_pdf(session_id: str = Query(...)):
    """Download execution report as PDF."""
    session_id = _validate_session_id(session_id)
    pdf_bytes = generate_pdf_report(session_id)
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="Could not generate PDF report")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="runbook-report-{session_id[:8]}.pdf"'},
    )


@app.get("/runbooks")
async def list_runbooks():
    """List uploaded runbook files."""
    files = [
        {"filename": f.name, "size_bytes": f.stat().st_size}
        for f in RUNBOOKS_DIR.glob("*.md")
    ]
    return {"runbooks": files}
