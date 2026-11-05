"""ورود با رمز، نشست کوکی، و قفل بعد از چند تلاش ناموفق."""
import hmac
import secrets
import time

from fastapi import Cookie, HTTPException, Request

from . import config, db

COOKIE = "session"
MAX_FAILS = 5
LOCK_SECONDS = 15 * 60
MIN_PASSWORD = 4          # به خواست صاحب پیج؛ قفل ۵ تلاش ناموفق جلوی حدس زدن را می‌گیرد
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


def change_password(request: Request, session: str, current: str, new: str) -> None:
    """تغییر رمز پنل از خود پنل: رمز فعلی با همان قفل تلاش ناموفق بررسی می‌شود، رمز تازه در ‎.env‎
    (فقط همان خط، دسترسی ۶۰۰) نوشته و همان لحظه فعال می‌شود، و همه‌ی ورودهای دیگر باطل می‌شوند."""
    from . import secrets_env
    ip = _ip(request)
    count, until = _fails.get(ip, [0, 0])
    if until > time.time():
        raise HTTPException(429, "تلاش زیاد؛ ۱۵ دقیقه بعد دوباره امتحان کنید")
    if not config.PANEL_PASSWORD or not hmac.compare_digest(current.encode(), config.PANEL_PASSWORD.encode()):
        count += 1
        _fails[ip] = [count, time.time() + LOCK_SECONDS if count >= MAX_FAILS else 0]
        raise HTTPException(401, "رمز فعلی اشتباه است")
    _fails.pop(ip, None)
    if len(new) < MIN_PASSWORD or len(new) > 128 or any(ch.isspace() for ch in new):
        raise HTTPException(422, f"رمز تازه باید دست‌کم {MIN_PASSWORD} نویسه و بدون فاصله باشد")
    if new == current:
        raise HTTPException(422, "رمز تازه با رمز فعلی یکی است")
    try:
        secrets_env.write_env("PANEL_PASSWORD", new)
    except ValueError as e:
        raise HTTPException(500, str(e))
    with db.connect() as c:
        c.execute("DELETE FROM sessions WHERE token<>?", (session,))   # دستگاه‌های دیگر خارج شوند


# ---------- ورود با گوگل (فقط ایمیل‌های مجاز) ----------
# دکمه‌ی گوگل در مرورگر یک «ID token» می‌دهد؛ اینجا خود گوگل (tokeninfo) درستی و مقصدش را تأیید می‌کند.
GOOGLE_TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


def google_config() -> dict:
    import os
    cid = (getattr(config, "GOOGLE_CLIENT_ID", "") or os.environ.get("GOOGLE_CLIENT_ID", "")).strip()
    raw = (getattr(config, "LOGIN_EMAILS", "") or os.environ.get("LOGIN_EMAILS", "")).strip()
    emails = {e.strip().lower() for e in raw.split(",") if e.strip()}
    return {"client_id": cid, "emails": emails, "enabled": bool(cid and emails)}


async def google_login(request: Request, credential: str, transport=None) -> str:
    import httpx
    ip = _ip(request)
    count, until = _fails.get(ip, [0, 0])
    if until > time.time():
        raise HTTPException(429, "تلاش زیاد؛ ۱۵ دقیقه بعد دوباره امتحان کنید")
    g = google_config()
    if not g["enabled"]:
        raise HTTPException(409, "ورود با گوگل هنوز تنظیم نشده")

    def fail(msg: str):
        n = count + 1
        _fails[ip] = [n, time.time() + LOCK_SECONDS if n >= MAX_FAILS else 0]
        raise HTTPException(401, msg)

    if not credential or len(credential) > 4096:
        fail("ورود با گوگل ناموفق بود")
    try:
        async with httpx.AsyncClient(timeout=10, transport=transport) as h:
            r = await h.get(GOOGLE_TOKENINFO, params={"id_token": credential})
        info = r.json() if r.status_code == 200 else {}
    except Exception:  # noqa: BLE001
        raise HTTPException(502, "گوگل در دسترس نبود؛ با رمز وارد شوید")
    ok = (info.get("aud") == g["client_id"] and info.get("iss") in GOOGLE_ISSUERS
          and str(info.get("email_verified")).lower() == "true" and int(info.get("exp") or 0) > time.time())
    if not ok:
        fail("ورود با گوگل ناموفق بود")
    if (info.get("email") or "").lower() not in g["emails"]:
        fail("این ایمیل اجازه‌ی ورود به پنل ندارد")
    _fails.pop(ip, None)
    token = secrets.token_urlsafe(32)
    with db.connect() as c:
        db.add_session(c, token, config.SESSION_TTL)
    return token
