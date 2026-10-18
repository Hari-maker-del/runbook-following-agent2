"""Authentication token and credential verification tests."""
import time

from auth import authenticate, auth_enabled, issue_token, verify_token


def configure(monkeypatch):
    monkeypatch.setenv("RUNBOOK_ADMIN_USERNAME", "operator")
    monkeypatch.setenv("RUNBOOK_ADMIN_PASSWORD", "a-strong-test-password")
    monkeypatch.setenv("RUNBOOK_AUTH_SECRET", "s" * 48)


def test_auth_disabled_without_all_required_settings(monkeypatch):
    for key in ("RUNBOOK_ADMIN_USERNAME", "RUNBOOK_ADMIN_PASSWORD", "RUNBOOK_AUTH_SECRET"):
        monkeypatch.delenv(key, raising=False)
    assert not auth_enabled()
    assert not authenticate("operator", "anything")


def test_credentials_are_compared_and_token_round_trips(monkeypatch):
    configure(monkeypatch)
    assert auth_enabled()
    assert authenticate("operator", "a-strong-test-password")
    assert not authenticate("operator", "wrong")
    assert not authenticate("intruder", "a-strong-test-password")
    token = issue_token("operator")
    assert verify_token(token) == "operator"


def test_tampered_token_is_rejected(monkeypatch):
    configure(monkeypatch)
    token = issue_token("operator")
    payload, signature = token.split(".")
    assert verify_token(payload + "." + signature[:-1] + ("A" if signature[-1] != "A" else "B")) is None


def test_expired_token_is_rejected(monkeypatch):
    configure(monkeypatch)
    import auth
    original = auth.TOKEN_TTL_SECONDS
    monkeypatch.setattr(auth, "TOKEN_TTL_SECONDS", -1)
    token = issue_token("operator")
    assert verify_token(token) is None
    monkeypatch.setattr(auth, "TOKEN_TTL_SECONDS", original)


def test_short_signing_secret_does_not_enable_auth(monkeypatch):
    monkeypatch.setenv("RUNBOOK_ADMIN_USERNAME", "operator")
    monkeypatch.setenv("RUNBOOK_ADMIN_PASSWORD", "password")
    monkeypatch.setenv("RUNBOOK_AUTH_SECRET", "too-short")
    assert not auth_enabled()
    assert verify_token("anything.anything") is None
