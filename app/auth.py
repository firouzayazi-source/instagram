"""ورود با رمز، نشست کوکی، و قفل بعد از چند تلاش ناموفق."""
import hmac
import secrets
import time

from fastapi import Cookie, HTTPException, Request

from . import config, db

COOKIE = "session"
MAX_FAILS = 5
LOCK_SECONDS = 15 * 60
_fails: dict[str, list] = {}  # ip -> [count, locked_until]


def _ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()


def check_password(request: Request, password: str) -> str:
    """رمز را بررسی می‌کند و توکن نشست برمی‌گرداند؛ وگرنه 401 یا 429."""
    ip = _ip(request)
    count, until = _fails.get(ip, [0, 0])
    if until > time.time():
        raise HTTPException(429, "تلاش زیاد؛ ۱۵ دقیقه بعد دوباره امتحان کنید")
    if not config.PANEL_PASSWORD or not hmac.compare_digest(password.encode(), config.PANEL_PASSWORD.encode()):
        count += 1
        _fails[ip] = [count, time.time() + LOCK_SECONDS if count >= MAX_FAILS else 0]
        raise HTTPException(401, "رمز اشتباه است")
    _fails.pop(ip, None)
    token = secrets.token_urlsafe(32)
    with db.connect() as c:
        db.add_session(c, token, config.SESSION_TTL)
    return token


def require_session(session: str | None = Cookie(default=None, alias=COOKIE)) -> str:
    if not session:
        raise HTTPException(401)
    with db.connect() as c:
        if not db.session_valid(c, session):
            raise HTTPException(401)
    return session
