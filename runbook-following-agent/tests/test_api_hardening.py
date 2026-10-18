"""API boundary regression tests for input and session validation."""
import uuid

import pytest
from fastapi import HTTPException

from main import (
    DEFAULT_CORS_ORIGINS,
    MAX_UPLOAD_BYTES,
    RUNBOOK_NAME_PATTERN,
    _get_runbook_path,
    _validate_session_id,
    app,
)


def test_runbook_names_are_simple_markdown_filenames():
    assert RUNBOOK_NAME_PATTERN.fullmatch("sample-maintenance.md")
    assert RUNBOOK_NAME_PATTERN.fullmatch("Runbook 01.MD")
    for filename in ("../secret.md", ".env.md", "folder/runbook.md", "runbook.txt", "x" * 130 + ".md"):
        assert not RUNBOOK_NAME_PATTERN.fullmatch(filename)


def test_runbook_lookup_rejects_path_traversal():
    with pytest.raises(HTTPException) as exc:
        _get_runbook_path("../outside.md")
    assert exc.value.status_code == 400


def test_session_ids_must_be_uuid_values():
    expected = str(uuid.uuid4())
    assert _validate_session_id(expected) == expected
    with pytest.raises(HTTPException) as exc:
        _validate_session_id("../../logs/other")
    assert exc.value.status_code == 400


def test_upload_limit_is_one_mib_and_cors_has_no_wildcard():
    assert MAX_UPLOAD_BYTES == 1_048_576
    assert "*" not in DEFAULT_CORS_ORIGINS
    cors = next(m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware")
    assert "*" not in cors.kwargs["allow_origins"]
    assert cors.kwargs["allow_credentials"] is False
