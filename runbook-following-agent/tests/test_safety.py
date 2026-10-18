"""Regression tests for runbook parsing and command safety classification."""

from allowlist import classify_command, contains_risky_pattern, validate_command_safe
from parser import parse_markdown_content


def test_empty_and_shell_injection_commands_are_disallowed():
    assert classify_command("") == "disallowed"
    assert classify_command("   ") == "disallowed"
    for command in (
        "echo hello; whoami",
        "echo hello && whoami",
        "echo $(whoami)",
        "echo $HOME",
        "cat file.txt > output.txt",
        "echo hello | cat",
    ):
        assert classify_command(command) == "disallowed", command


def test_known_read_only_commands_are_safe():
    for command in ("pwd", "whoami", "date", "ls", "echo hello"):
        assert classify_command(command) == "safe", command


def test_unlisted_commands_are_disallowed():
    for command in ("python -c print(1)", "curl https://example.com", "pip install requests"):
        assert classify_command(command) == "disallowed", command


def test_risky_patterns_use_word_boundaries():
    assert contains_risky_pattern("rm -rf temp")
    assert contains_risky_pattern("sudo systemctl stop service")
    assert not contains_risky_pattern("confirm firmware terminal")


def test_safe_validator_rejects_empty_and_shell_metacharacters():
    assert validate_command_safe("pwd") == (True, "")
    valid, reason = validate_command_safe("echo ok && whoami")
    assert not valid
    assert "forbidden" in reason.lower()


def test_parser_sorts_steps_and_ignores_duplicate_step_numbers():
    content = """
# Maintenance
3. date
1. pwd
1. rm -rf temp
2. echo ready
"""
    steps = parse_markdown_content(content)
    assert [step.step for step in steps] == [1, 2, 3]
    assert [step.command for step in steps] == ["rm -rf temp", "echo ready", "date"]
    assert steps[0].risk_level == "risky"
    assert steps[1].risk_level == "safe"


def test_parser_marks_shell_injection_as_disallowed():
    steps = parse_markdown_content("1. echo hello; whoami")
    assert len(steps) == 1
    assert steps[0].risk_level == "disallowed"


def test_parser_ignores_non_step_lines_and_empty_content():
    assert parse_markdown_content("# Runbook\nSome description\n") == []
    assert parse_markdown_content("") == []
