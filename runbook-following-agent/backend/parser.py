"""Parse Markdown runbooks into numbered execution steps."""

import re
from pathlib import Path

from models import RunbookStep
from allowlist import classify_command


# Matches lines like "1. pwd" or "1) ls -la"
NUMBERED_STEP_PATTERN = re.compile(
    r"^\s*(\d+)\s*[\.\)]\s*(.+?)\s*$",
    re.MULTILINE,
)


def parse_markdown_content(content: str) -> list[RunbookStep]:
    """Extract numbered steps from Markdown content."""
    steps: list[RunbookStep] = []
    seen_steps: set[int] = set()

    for match in NUMBERED_STEP_PATTERN.finditer(content):
        step_num = int(match.group(1))
        command = match.group(2).strip()

        # Skip empty commands and duplicate step numbers
        if not command or step_num in seen_steps:
            continue

        seen_steps.add(step_num)
        risk = classify_command(command)
        steps.append(
            RunbookStep(
                step=step_num,
                command=command,
                risk_level=risk,
            )
        )

    steps.sort(key=lambda s: s.step)
    return steps


def parse_markdown_file(filepath: Path) -> list[RunbookStep]:
    """Read and parse a Markdown runbook file."""
    content = filepath.read_text(encoding="utf-8")
    return parse_markdown_content(content)


def steps_to_json(steps: list[RunbookStep]) -> list[dict]:
    """Serialize steps to plain JSON-compatible dicts."""
    return [{"step": s.step, "command": s.command} for s in steps]
