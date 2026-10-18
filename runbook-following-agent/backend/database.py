"""Persistent user accounts for Runbook OS.

Production should set DATABASE_URL to a managed PostgreSQL database.
SQLite is a local-development fallback only; do not rely on Render's ephemeral
filesystem for production account persistence.
"""
import hashlib
import os
import secrets
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from datetime import datetime, timezone


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        path = os.getenv("RUNBOOK_LOCAL_DB_PATH", "/tmp/runbook-local-users.db")
        return "sqlite:///" + path
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _database_url()
IS_EPHEMERAL_LOCAL_DB = not bool(os.getenv("DATABASE_URL", "").strip())
_engine_kwargs = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite:///"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "runbook_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


Base.metadata.create_all(engine)


def _hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return "pbkdf2_sha256$310000$%s$%s" % (salt.hex(), derived.hex())


def _verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, rounds, salt_hex, expected = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds)).hex()
        return secrets.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_user(username: str, password: str) -> Optional[dict]:
    from uuid import uuid4
    username = username.strip()
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == username)):
            return None
        user = User(id=str(uuid4()), username=username, password_hash=_hash_password(password))
        db.add(user)
        try:
            db.commit()
        except Exception:
            db.rollback()
            return None
        return {"id": user.id, "username": user.username, "is_active": user.is_active}


def authenticate_user(username: str, password: str) -> Optional[dict]:
    # Always run a PBKDF2 operation for missing usernames to reduce timing leaks.
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username.strip()))
        if not user:
            _verify_password(password, _hash_password("dummy-password"))
            return None
        if not user.is_active or not _verify_password(password, user.password_hash):
            return None
        return {"id": user.id, "username": user.username, "is_active": user.is_active}


def get_user(user_id: str) -> Optional[dict]:
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if not user or not user.is_active:
            return None
        return {"id": user.id, "username": user.username, "is_active": user.is_active}


def registration_enabled() -> bool:
    # Avoid silently putting production user records on an ephemeral filesystem.
    return bool(os.getenv("DATABASE_URL", "").strip()) or os.getenv("RUNBOOK_ALLOW_LOCAL_USER_DB") == "1"
