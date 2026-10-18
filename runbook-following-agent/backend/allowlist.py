"""Command allowlist and risky-command detection.

Commands are always launched without a shell. Risky approval is not a way to
override the allowlist: commands outside the supported command set stay blocked.
"""
import re
import shlex
from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal

ALLOWLIST: set[str] = {
    "pwd", "ls", "mkdir", "cp", "mv", "cat", "echo", "whoami", "date",
}
RISKY_PATTERNS: list[str] = [
    "rm", "shutdown", "reboot", "kill", "sudo", "chmod", "systemctl stop", "format",
]
RISKY_PATTERN_REGEXES: list[re.Pattern] = [
    re.compile(r"\b" + re.escape(pattern) + r"\b") for pattern in RISKY_PATTERNS
]
FORBIDDEN_SHELL_CHARS = re.compile(r"[;&|\x60$<>]")
# These can affect the host or service, not just the runbook workspace.
NEVER_EXECUTE_BASES = {"sudo", "shutdown", "reboot", "systemctl", "format", "kill", "chmod"}


def get_tokens(command: str) -> list[str]:
    """Parse a command into tokens; malformed quoting is rejected."""
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return []


def get_base_command(command: str) -> str:
    """Extract the base command token from a command string."""
    tokens = get_tokens(command.strip())
    return tokens[0].lower() if tokens else ""


def contains_risky_pattern(command: str) -> bool:
    """Return True if the command matches any risky pattern as a whole word."""
    lower = command.lower().strip()
    return any(pattern_re.search(lower) for pattern_re in RISKY_PATTERN_REGEXES)


def validate_command_safe(command: str) -> tuple[bool, str]:
    """Reject shell syntax, malformed quoting, and paths escaping the workspace."""
    command = command.strip()
    if not command:
        return False, "Empty command"
    if FORBIDDEN_SHELL_CHARS.search(command):
        return False, "Command contains forbidden shell metacharacters"

    tokens = get_tokens(command)
    if not tokens:
        return False, "Command has invalid quoting or no executable"

    # Commands run with the runbooks directory as their working directory.
    # Do not allow absolute paths, parent traversal, or Windows drive/UNC paths.
    for token in tokens[1:]:
        posix_path = PurePosixPath(token)
        windows_path = PureWindowsPath(token)
        if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
            return False, "Absolute paths are not allowed; use paths inside the runbook workspace"
        if ".." in posix_path.parts or ".." in windows_path.parts:
            return False, "Parent-directory traversal is not allowed"

    return True, ""


def classify_command(command: str) -> Literal["safe", "risky", "disallowed"]:
    """Classify a command as auto-run, confirmation-required, or blocked."""
    is_valid, _ = validate_command_safe(command)
    if not is_valid:
        return "disallowed"

    base = get_base_command(command)
    if not base or base in NEVER_EXECUTE_BASES:
        return "disallowed"
    if base not in ALLOWLIST and not contains_risky_pattern(command):
        return "disallowed"
    if contains_risky_pattern(command):
        # rm is the only destructive command retained for explicit confirmation;
        # it is confined to relative paths in the runbook workspace.
        if base != "rm":
            return "disallowed"
        tokens = get_tokens(command)
        if any(token in {"--no-preserve-root", "--preserve-root"} for token in tokens):
            return "disallowed"
        targets = [token for token in tokens[1:] if not token.startswith("-")]
        if not targets:
            return "disallowed"
        return "risky"
    return "safe"
