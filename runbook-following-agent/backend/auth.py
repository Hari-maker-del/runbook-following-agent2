"""Signed bearer tokens for legacy administrator and persistent user accounts."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional

TOKEN_TTL_SECONDS = 60 * 60 * 8


def _admin_configured() -> bool:
    secret = os.getenv("RUNBOOK_AUTH_SECRET", "")
    return bool(os.getenv("RUNBOOK_ADMIN_USERNAME") and os.getenv("RUNBOOK_ADMIN_PASSWORD") and len(secret) >= 32)


def auth_enabled() -> bool:
    try:
        from database import registration_enabled
        accounts_available = registration_enabled()
    except Exception:
        accounts_available = False
    return _admin_configured() or accounts_available


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def authenticate(username: str, password: str) -> bool:
    expected_user = os.getenv("RUNBOOK_ADMIN_USERNAME", "")
    expected_password = os.getenv("RUNBOOK_ADMIN_PASSWORD", "")
    if not _admin_configured() or not isinstance(username, str) or not isinstance(password, str):
        return False
    return secrets.compare_digest(username, expected_user) and secrets.compare_digest(password, expected_password)


def issue_token(subject: str) -> str:
    secret = os.environ["RUNBOOK_AUTH_SECRET"].encode("utf-8")
    payload = _b64(json.dumps({
        "sub": subject,
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _b64(hmac.new(secret, payload.encode("ascii"), hashlib.sha256).digest())
    return payload + "." + signature


def verify_token(token: str) -> Optional[str]:
    if not _admin_configured() or not isinstance(token, str) or token.count(".") != 1:
        # Account-only deployments still need the same signing secret.
        if not os.getenv("RUNBOOK_AUTH_SECRET") or len(os.getenv("RUNBOOK_AUTH_SECRET", "")) < 32:
            return None
    payload, signature = token.split(".", 1) if token.count(".") == 1 else ("", "")
    if not payload:
        return None
    secret = os.environ["RUNBOOK_AUTH_SECRET"].encode("utf-8")
    expected = _b64(hmac.new(secret, payload.encode("ascii"), hashlib.sha256).digest())
    if not secrets.compare_digest(signature, expected):
        return None
    try:
        claims = json.loads(_unb64(payload))
        if not isinstance(claims.get("sub"), str) or not claims["sub"]:
            return None
        if int(claims.get("exp", 0)) <= int(time.time()):
            return None
        if int(claims.get("iat", 0)) > int(time.time()) + 30:
            return None
        return claims["sub"]
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None
