"""Pydantic models for the Runbook Following Agent API."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    WAITING_CONFIRMATION = "waiting_confirmation"


class RunbookStep(BaseModel):
    step: int
    command: str
    status: StepStatus = StepStatus.PENDING
    risk_level: str = "safe"  # safe | risky | disallowed


class ParseRequest(BaseModel):
    filename: str


class ExecuteRequest(BaseModel):
    filename: str
    start_from_step: int = 1
    session_id: Optional[str] = None


class ConfirmRequest(BaseModel):
    session_id: str
    step: int
    approved: bool


class RetryRequest(BaseModel):
    session_id: str
    step: int


class PauseResumeRequest(BaseModel):
    session_id: str


class StepResult(BaseModel):
    step: int
    command: str
    status: StepStatus
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    execution_time_ms: float = 0
    message: str = ""


class ExecutionState(BaseModel):
    session_id: str
    filename: str
    status: str  # running | paused | waiting_confirmation | completed | failed
    current_step: int = 0
    total_steps: int = 0
    progress_percent: float = 0
    steps: list[RunbookStep] = Field(default_factory=list)
    results: list[StepResult] = Field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    pending_confirmation: Optional[dict] = None


class LogEntry(BaseModel):
    timestamp: str
    session_id: str
    step: int
    command: str
    status: str
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    execution_time_ms: float = 0
    message: str = ""


class ReportSummary(BaseModel):
    session_id: str
    filename: str
    total_steps: int
    successful: int
    failed: int
    blocked: int
    skipped: int
    execution_duration_ms: float
    overall_status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    steps: list[StepResult] = Field(default_factory=list)
