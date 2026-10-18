"""Safe subprocess execution for validated runbook commands."""
import platform
import shlex
import subprocess
import time
from pathlib import Path
from typing import Optional

from allowlist import classify_command, get_base_command, validate_command_safe

RUNBOOK_WORKSPACE = Path(__file__).parent / "runbooks"
MAX_OUTPUT_CHARS = 20_000

WINDOWS_COMMAND_MAP: dict[str, str] = {
    "pwd": "cd", "ls": "dir", "date": "echo %date% %time%", "cp": "copy", "mv": "move",
}


def _normalize_command_for_platform(command: str) -> str:
    if platform.system() != "Windows":
        return command
    base = get_base_command(command)
    if base in WINDOWS_COMMAND_MAP:
        mapped = WINDOWS_COMMAND_MAP[base]
        tokens = shlex.split(command)
        if len(tokens) > 1 and " " not in mapped:
            return mapped + " " + " ".join(tokens[1:])
        return mapped
    return command


def _build_subprocess_args(command: str) -> list[str]:
    command = _normalize_command_for_platform(command)
    if platform.system() == "Windows":
        # Windows cmd interprets additional syntax, so the same strict input
        # validation is performed before this compatibility wrapper is used.
        return ["cmd", "/c", command]
    return shlex.split(command)


def execute_command(command: str, cwd: Optional[str] = None, allow_risky: bool = False) -> dict:
    """Execute only commands permitted by the policy and capture bounded output.

    Risky commands must be explicitly approved by the API execution flow. This
    check is repeated here so a caller cannot bypass the policy by calling the
    executor directly.
    """
    command = command.strip()
    is_valid, error = validate_command_safe(command)
    classification = classify_command(command)
    if not is_valid or classification == "disallowed":
        return {
            "stdout": "", "stderr": error or "Command blocked by execution policy.",
            "exit_code": -1, "execution_time_ms": 0, "success": False,
        }
    if classification == "risky" and not allow_risky:
        return {
            "stdout": "", "stderr": "Risky command requires explicit approval.",
            "exit_code": -1, "execution_time_ms": 0, "success": False,
        }

    RUNBOOK_WORKSPACE.mkdir(parents=True, exist_ok=True)
    working_directory = str(Path(cwd).resolve()) if cwd else str(RUNBOOK_WORKSPACE.resolve())
    workspace = RUNBOOK_WORKSPACE.resolve()
    try:
        Path(working_directory).relative_to(workspace)
    except ValueError:
        return {
            "stdout": "", "stderr": "Execution working directory must be inside the runbook workspace.",
            "exit_code": -1, "execution_time_ms": 0, "success": False,
        }

    args = _build_subprocess_args(command)
    start = time.perf_counter()
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, cwd=working_directory,
            timeout=15, shell=False, check=False,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        if len(stdout) > MAX_OUTPUT_CHARS:
            stdout = stdout[:MAX_OUTPUT_CHARS] + "\n[output truncated]"
        if len(stderr) > MAX_OUTPUT_CHARS:
            stderr = stderr[:MAX_OUTPUT_CHARS] + "\n[output truncated]"
        return {
            "stdout": stdout, "stderr": stderr, "exit_code": result.returncode,
            "execution_time_ms": round(elapsed_ms, 2), "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "stdout": "", "stderr": "Command timed out after 15 seconds",
            "exit_code": -1, "execution_time_ms": round(elapsed_ms, 2), "success": False,
        }
    except Exception:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "stdout": "", "stderr": "Command could not be executed by the runbook executor.",
            "exit_code": -1, "execution_time_ms": round(elapsed_ms, 2), "success": False,
        }


def can_auto_execute(command: str) -> bool:
    return classify_command(command) == "safe"


def requires_confirmation(command: str) -> bool:
    return classify_command(command) == "risky"
