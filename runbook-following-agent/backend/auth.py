"""Environment-configured authentication for Runbook OS.

Set RUNBOOK_ADMIN_USERNAME, RUNBOOK_ADMIN_PASSWORD, and RUNBOOK_AUTH_SECRET
(at least 32 characters) on the backend to enable bearer-token authentication.
No credentials or signing secrets are bundled in source control.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional

TOKEN_TTL_SECONDS = 60 * 60 * 8


def auth_enabled() -> bool:
    secret = os.getenv("RUNBOOK_AUTH_SECRET", "")
    return bool(
        os.getenv("RUNBOOK_ADMIN_USERNAME")
        and os.getenv("RUNBOOK_ADMIN_PASSWORD")
        and len(secret) >= 32
    )


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def authenticate(username: str, password: str) -> bool:
    expected_user = os.getenv("RUNBOOK_ADMIN_USERNAME", "")
    expected_password = os.getenv("RUNBOOK_ADMIN_PASSWORD", "")
    if not auth_enabled() or not isinstance(username, str) or not isinstance(password, str):
        return False
    return secrets.compare_digest(username, expected_user) and secrets.compare_digest(password, expected_password)


def issue_token(username: str) -> str:
    secret = os.environ["RUNBOOK_AUTH_SECRET"].encode("utf-8")
    payload = _b64(json.dumps({
        "sub": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _b64(hmac.new(secret, payload.encode("ascii"), hashlib.sha256).digest())
    return payload + "." + signature


def verify_token(token: str) -> Optional[str]:
    if not auth_enabled() or not isinstance(token, str) or token.count(".") != 1:
        return None
    payload, signature = token.split(".", 1)
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
