"""Regression tests for persistent accounts and workspace ownership."""
from uuid import uuid4

import pytest
from fastapi import HTTPException

from database import authenticate_user, create_user
from main import _get_owned_session, _user_runbooks_dir, _sessions


def test_user_accounts_store_password_hashes_and_authenticate():
    username = "test_" + uuid4().hex[:16]
    password = "a-long-test-password-123"
    user = create_user(username, password)
    assert user is not None
    assert user["username"] == username
    assert authenticate_user(username, password)["id"] == user["id"]
    assert authenticate_user(username, "wrong-password") is None
    assert create_user(username, password) is None


def test_user_workspaces_are_separate_from_each_other_and_admin():
    first = _user_runbooks_dir("user:" + str(uuid4()))
    second = _user_runbooks_dir("user:" + str(uuid4()))
    legacy = _user_runbooks_dir("legacy-admin")
    assert first != second
    assert first != legacy
    assert second != legacy


def test_session_state_is_not_visible_to_another_owner():
    session_id = str(uuid4())
    _sessions[session_id] = {"session_id": session_id, "owner_id": "user:owner-a"}
    try:
        assert _get_owned_session(session_id, "user:owner-a")["session_id"] == session_id
        with pytest.raises(HTTPException) as exc:
            _get_owned_session(session_id, "user:owner-b")
        assert exc.value.status_code == 404
    finally:
        _sessions.pop(session_id, None)
