"""Safe subprocess execution for validated runbook commands."""

import platform
import shlex
import subprocess
import time
from typing import Optional

from allowlist import classify_command, get_base_command, validate_command_safe

# Map Unix runbook commands to Windows equivalents when needed
WINDOWS_COMMAND_MAP: dict[str, str] = {
    "pwd": "cd",
    "ls": "dir",
    "date": "echo %date% %time%",
    "cp": "copy",
    "mv": "move",
}


def _normalize_command_for_platform(command: str) -> str:
    """Translate common Unix commands for Windows execution."""
    if platform.system() != "Windows":
        return command

    base = get_base_command(command)
    if base in WINDOWS_COMMAND_MAP:
        mapped = WINDOWS_COMMAND_MAP[base]
        # Preserve arguments for commands like "ls -la" -> "dir -la" or
        # "cp a.txt b.txt" -> "copy a.txt b.txt". Commands whose mapped form
        # is itself multiple words (e.g. "echo %date% %time%") take no
        # runbook arguments, so they're returned unchanged.
        try:
            tokens = shlex.split(command)
        except ValueError:
            tokens = command.split()
        if len(tokens) > 1 and " " not in mapped:
            return mapped + " " + " ".join(tokens[1:])
        return mapped
    return command


def _build_subprocess_args(command: str) -> list[str]:
    """Build argument list for subprocess without shell when possible."""
    command = _normalize_command_for_platform(command)
    system = platform.system()

    if system == "Windows":
        return ["cmd", "/c", command]

    return shlex.split(command)


def execute_command(command: str, cwd: Optional[str] = None) -> dict:
    """
    Execute a single validated command and capture output metrics.
    Only call this after allowlist/risky classification and user approval.
    """
    command = command.strip()
    is_valid, error = validate_command_safe(command)
    if not is_valid:
        return {
            "stdout": "",
            "stderr": error,
            "exit_code": -1,
            "execution_time_ms": 0,
            "success": False,
        }

    args = _build_subprocess_args(command)
    start = time.perf_counter()

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=120,
            shell=False,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "exit_code": result.returncode,
            "execution_time_ms": round(elapsed_ms, 2),
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "stdout": "",
            "stderr": "Command timed out after 120 seconds",
            "exit_code": -1,
            "execution_time_ms": round(elapsed_ms, 2),
            "success": False,
        }
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "stdout": "",
            "stderr": str(exc),
            "exit_code": -1,
            "execution_time_ms": round(elapsed_ms, 2),
            "success": False,
        }


def can_auto_execute(command: str) -> bool:
    """Return True if command is on the allowlist and safe to auto-run."""
    return classify_command(command) == "safe"


def requires_confirmation(command: str) -> bool:
    """Return True if command is risky and needs user confirmation."""
    return classify_command(command) == "risky"
