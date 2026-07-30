"""Command allowlist and risky-command detection."""

import re
import shlex
from typing import Literal

# Commands that may be executed automatically after validation
ALLOWLIST: set[str] = {
    "pwd",
    "ls",
    "mkdir",
    "cp",
    "mv",
    "cat",
    "echo",
    "whoami",
    "date",
}

# Substrings/patterns that require explicit user confirmation before execution
RISKY_PATTERNS: list[str] = [
    "rm",
    "shutdown",
    "reboot",
    "kill",
    "sudo",
    "chmod",
    "systemctl stop",
    "format",
]

# Word-boundary versions of RISKY_PATTERNS, compiled once. Using \b prevents
# false positives like "term"/"confirm"/"firmware" matching the "rm" pattern,
# or "pseudo" matching "sudo".
RISKY_PATTERN_REGEXES: list[re.Pattern] = [
    re.compile(r"\b" + re.escape(pattern) + r"\b") for pattern in RISKY_PATTERNS
]

# Characters that indicate shell injection attempts
FORBIDDEN_SHELL_CHARS = re.compile(r"[;&|`$<>]")


def get_base_command(command: str) -> str:
    """Extract the base command token from a command string."""
    command = command.strip()
    if not command:
        return ""
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    return tokens[0].lower() if tokens else ""


def contains_risky_pattern(command: str) -> bool:
    """Return True if the command matches any risky pattern as a whole word."""
    lower = command.lower().strip()
    for pattern_re in RISKY_PATTERN_REGEXES:
        if pattern_re.search(lower):
            return True
    return False


def validate_command_safe(command: str) -> tuple[bool, str]:
    """
    Validate that a command string does not contain shell injection vectors.
    Returns (is_valid, error_message).
    """
    command = command.strip()
    if not command:
        return False, "Empty command"

    if FORBIDDEN_SHELL_CHARS.search(command):
        return False, "Command contains forbidden shell metacharacters"

    # Reject command substitution even if regex missed edge cases
    if "$(" in command or "${" in command:
        return False, "Command substitution is not allowed"

    return True, ""


def classify_command(command: str) -> Literal["safe", "risky", "disallowed"]:
    """
    Classify a command as safe (auto-run), risky (needs confirmation),
    or disallowed (not in allowlist and not explicitly risky).
    """
    is_valid, reason = validate_command_safe(command)
    if not is_valid:
        return "disallowed"

    base = get_base_command(command)
    if not base:
        return "disallowed"

    if contains_risky_pattern(command):
        return "risky"

    if base in ALLOWLIST:
        return "safe"

    return "disallowed"
