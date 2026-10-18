"""Execution logging to JSON files in backend/logs/."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

from models import LogEntry

LOGS_DIR = Path(__file__).parent / "logs"


def _ensure_logs_dir() -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return LOGS_DIR


def _validate_session_id(session_id: str) -> str:
    """Only canonical UUID session identifiers may address log files."""
    try:
        return str(UUID(session_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Invalid session identifier") from exc


def _session_log_path(session_id: str) -> Path:
    return _ensure_logs_dir() / f"{_validate_session_id(session_id)}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_session_log(session_id: str, filename: str) -> None:
    path = _session_log_path(session_id)
    data = {"session_id": _validate_session_id(session_id), "filename": filename, "created_at": _now_iso(), "entries": []}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def append_log(
    session_id: str, step: int, command: str, status: str, stdout: str = "",
    stderr: str = "", exit_code: Optional[int] = None, execution_time_ms: float = 0,
    message: str = "",
) -> LogEntry:
    entry = LogEntry(
        timestamp=_now_iso(), session_id=_validate_session_id(session_id), step=step,
        command=command, status=status, stdout=stdout, stderr=stderr,
        exit_code=exit_code, execution_time_ms=execution_time_ms, message=message,
    )
    path = _session_log_path(session_id)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {"session_id": _validate_session_id(session_id), "filename": "", "created_at": _now_iso(), "entries": []}
    data["entries"].append(entry.model_dump())
    data["updated_at"] = _now_iso()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return entry


def get_session_logs(session_id: Optional[str] = None) -> list[dict]:
    _ensure_logs_dir()
    if session_id:
        try:
            path = _session_log_path(session_id)
        except ValueError:
            return []
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("entries", [])

    all_entries: list[dict] = []
    for log_file in sorted(LOGS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(log_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for entry in data.get("entries", []):
            entry["filename"] = data.get("filename", "")
            all_entries.append(entry)
    return all_entries


def list_sessions() -> list[dict]:
    _ensure_logs_dir()
    sessions = []
    for log_file in sorted(LOGS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(log_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        sessions.append({
            "session_id": data.get("session_id"), "filename": data.get("filename"),
            "created_at": data.get("created_at"), "entry_count": len(data.get("entries", [])),
        })
    return sessions
