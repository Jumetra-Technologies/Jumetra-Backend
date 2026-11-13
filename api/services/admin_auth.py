"""The admin portal's password and sessions.

The password is checked here, never in the website: anything in the
website's code can be read by anyone who opens it. What's stored is a scrypt
hash, ``HHIP_ADMIN_PASSWORD_HASH`` when it's set, otherwise ``DEFAULT_HASH``.
To change the password, set that variable to the output of::

    python -m api.services.admin_auth 'the new password'

A right password gets a token that lasts ``SESSION_MINUTES`` and names an
``admin_sessions`` row, so signing out ends it at once. Wrong passwords lock
out: ``MAX_FAILURES_PER_ADDRESS`` from one address, or ``MAX_FAILURES_TOTAL``
from everywhere, in ``LOCKOUT_MINUTES``, and the next try waits until the
oldest of them is that old. The counts are in the database, so every server
instance sees the same ones.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from sqlalchemy import func, select, true
from sqlalchemy.orm import Session

from database.models import AdminSession, AdminSignInAttempt

SESSION_MINUTES = 30
LOCKOUT_MINUTES = 15
MAX_FAILURES_PER_ADDRESS = 5
MAX_FAILURES_TOTAL = 30

# scrypt of the password set on 6 Nov 2026. Replace it with HHIP_ADMIN_PASSWORD_HASH in production.
DEFAULT_HASH = "scrypt:16384:8:1:pefyMlYr3OKNsfoJAA+kSg==:dRmabFtFbfY5MhDG6ZKGAf967g+aAbTdpAA5XlA+zVM="


def hash_password(password: str, *, salt: Optional[bytes] = None, n: int = 16384, r: int = 8, p: int = 1) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32)
    # Colons, not dollar signs: the hash goes in the function's .env file, where $ would be read as a variable.
    return f"scrypt:{n}:{r}:{p}:{base64.b64encode(salt).decode()}:{base64.b64encode(digest).decode()}"


class AdminNotConfigured(RuntimeError):
    """A deployed server has no HHIP_ADMIN_PASSWORD_HASH of its own."""


def on_a_server() -> bool:
    """Running deployed: Render sets RENDER, Cloud Functions/Cloud Run set K_SERVICE."""
    return bool(os.environ.get("RENDER") or os.environ.get("K_SERVICE")) or os.environ.get("HHIP_ENV", "").lower() == "production"


def password_hash() -> str:
    """The admin password's hash. DEFAULT_HASH is in this repository, so a deployed server
    refuses it (audit N-4): anyone with the code could try passwords against it offline."""
    configured = os.environ.get("HHIP_ADMIN_PASSWORD_HASH", "").strip()
    if configured:
        return configured
    if on_a_server():
        raise AdminNotConfigured("Set HHIP_ADMIN_PASSWORD_HASH on the server to use the admin portal.")
    return DEFAULT_HASH


def check_password(password: str, stored: Optional[str] = None) -> bool:
    stored = stored or password_hash()
    try:
        scheme, n, r, p, salt, digest = stored.replace("$", ":").split(":")
        if scheme != "scrypt":
            return False
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(base64.b64decode(digest)))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, base64.b64decode(digest))


def retry_after(session: Session, ip_hash: str, now: datetime) -> int:
    """Seconds until another try is allowed, or 0 now."""
    window = now - timedelta(minutes=LOCKOUT_MINUTES)
    for where, limit in ((AdminSignInAttempt.ip_hash == ip_hash, MAX_FAILURES_PER_ADDRESS), (true(), MAX_FAILURES_TOTAL)):
        q = select(AdminSignInAttempt.at).where(AdminSignInAttempt.ok.is_(False), AdminSignInAttempt.at >= window, where).order_by(AdminSignInAttempt.at.desc()).limit(limit)
        recent = list(session.scalars(q))
        if len(recent) >= limit:
            oldest = recent[-1] if recent[-1].tzinfo else recent[-1].replace(tzinfo=timezone.utc)
            return max(1, int((oldest + timedelta(minutes=LOCKOUT_MINUTES) - now).total_seconds()) + 1)
    return 0


def sign_in(session: Session, *, password: str, ip_hash: str, secret: str, now: Optional[datetime] = None) -> tuple[Optional[str], Optional[datetime], int]:
    """(token, expires, 0) on success; (None, None, 0) for a wrong password; (None, None, seconds) while locked out."""
    now = now or datetime.now(timezone.utc)
    wait = retry_after(session, ip_hash, now)
    if wait:
        return None, None, wait
    ok = check_password(password, password_hash())
    session.add(AdminSignInAttempt(at=now, ip_hash=ip_hash, ok=ok))
    if not ok:
        session.commit()
        return None, None, 0
    expires = now + timedelta(minutes=SESSION_MINUTES)
    row = AdminSession(created_at=now, expires_at=expires, ip_hash=ip_hash)
    session.add(row)
    session.commit()
    token = jwt.encode({"sub": "admin", "typ": "admin", "jti": row.id, "exp": expires}, secret, algorithm="HS256")
    return token, expires, 0


def session_for(session: Session, token: str, secret: str, now: Optional[datetime] = None) -> Optional[AdminSession]:
    """The live admin session this token names, or None."""
    now = now or datetime.now(timezone.utc)
    try:
        # Expiry is checked against `now` below (and the row's own expiry), not the library's clock.
        claims = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_exp": False, "require": ["exp"]})
    except jwt.PyJWTError:
        return None
    if claims.get("typ") != "admin" or claims.get("sub") != "admin":
        return None
    if datetime.fromtimestamp(int(claims["exp"]), timezone.utc) <= now:
        return None
    row = session.get(AdminSession, claims.get("jti", ""))
    if row is None or row.revoked_at is not None:
        return None
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    return row if expires > now else None


def failures_since(session: Session, since: datetime) -> int:
    return session.scalar(select(func.count()).select_from(AdminSignInAttempt).where(AdminSignInAttempt.ok.is_(False), AdminSignInAttempt.at >= since)) or 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m api.services.admin_auth 'password'")
    print(hash_password(sys.argv[1]))
