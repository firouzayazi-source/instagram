"""ورود با رمز، نشست کوکی، قفل ماندگار بعد از چند تلاش ناموفق، و دستگاه‌های شناخته‌شده.

دستگاه: هر مرورگر یا اپ نصب‌شده یک کوکی بلندمدت «device» می‌گیرد (فقط هش آن در پایگاه داده است).
- اولین دستگاهی که با رمز درست وارد شود خودکار «شناخته‌شده» می‌شود.
- با قفل دستگاه روشن (پیش‌فرض)، دستگاه تازه حتی با رمز درست وارد نمی‌شود: «منتظر تأیید» می‌ماند، به تلگرام
  مدیر خبر می‌رود و فقط از یک دستگاه شناخته‌شده (تنظیمات ← دستگاه‌ها) تأیید می‌شود.
- برداشتن دستگاه همه‌ی ورودهای همان دستگاه را باطل می‌کند.
- اگر همه‌ی دستگاه‌ها از دست رفت: روی سرور tools/reset_panel_password.py (رمز تازه و پاک شدن فهرست دستگاه‌ها).
تلاش ناموفق در پایگاه داده شمرده می‌شود و با ری‌استارت صفر نمی‌شود.
"""
import hashlib
import hmac
import re
import secrets
import time

from fastapi import Cookie, HTTPException, Request, Response

from . import config, db

COOKIE = "session"
DEVICE_COOKIE = "device"
DEVICE_TTL = 5 * 365 * 86400
LOCK_KEY = "device_lock"           # "0" یعنی دستگاه تازه بی‌تأیید وارد می‌شود؛ پیش‌فرض روشن
MAX_FAILS = 5
LOCK_SECONDS = 15 * 60
MIN_PASSWORD = 8                   # به خواست صاحب پیج (۲۳ آبان ۱۴۰۵)

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY,               -- sha256 کوکی دستگاه
  name TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending',   -- trusted | pending | revoked
  created_at REAL NOT NULL,
  last_seen REAL NOT NULL,
  last_ip TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS login_fails (
  ip TEXT PRIMARY KEY,
  count INTEGER NOT NULL DEFAULT 0,
  until REAL NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL
);
"""


def ensure(c) -> None:
    c.executescript(SCHEMA)


def _ip(request: Request) -> str:
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    if ":" in ip:      # IPv6: هر دستگاه یک /64 کامل دارد؛ قفل برای کل همان بازه
        parts = (ip.split("::")[0].split(":") + ["0"] * 4)[:4]
        ip = ":".join(parts) + "::/64"
    return ip


# درخواست‌های ورود پشت‌سرهم بررسی می‌شوند (نه هم‌زمان)، تا با ده‌ها درخواست موازی قفل ۵ تلاش دور زده نشود
import threading  # noqa: E402
_LOGIN_LOCK = threading.Lock()
PASSWORD_RX = re.compile(r"^[A-Za-z0-9!@%^*_+=.,:/?~\-]{8,128}$")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def device_name(ua: str) -> str:
    ua = ua or ""
    os_ = next((n for p, n in ((r"iPhone", "آیفون"), (r"iPad", "آیپد"), (r"Android", "اندروید"), (r"Macintosh|Mac OS", "مک"),
                                (r"Windows", "ویندوز"), (r"Linux", "لینوکس")) if re.search(p, ua)), "دستگاه")
    br = next((n for p, n in ((r"Edg/", "Edge"), (r"CriOS|Chrome/", "Chrome"), (r"FxiOS|Firefox/", "Firefox"),
                               (r"Safari/", "Safari")) if re.search(p, ua)), "")
    return f"{os_} {br}".strip()


# ---------- قفل تلاش ناموفق (ماندگار) ----------

def _check_lock(c, ip: str) -> int:
    r = c.execute("SELECT count, until FROM login_fails WHERE ip=?", (ip,)).fetchone()
    if r and r["until"] > time.time():
        raise HTTPException(429, "تلاش زیاد؛ ۱۵ دقیقه بعد دوباره امتحان کنید")
    return r["count"] if r and r["until"] == 0 else 0


def _fail(c, ip: str, count: int = 0) -> None:
    now = time.time()
    c.execute("INSERT INTO login_fails(ip,count,until,updated_at) VALUES (?,1,0,?) "
              "ON CONFLICT(ip) DO UPDATE SET count=count+1, updated_at=excluded.updated_at", (ip, now))   # افزایش اتمی
    if c.execute("SELECT count FROM login_fails WHERE ip=?", (ip,)).fetchone()[0] >= MAX_FAILS:
        c.execute("UPDATE login_fails SET count=0, until=? WHERE ip=?", (now + LOCK_SECONDS, ip))
    c.execute("DELETE FROM login_fails WHERE updated_at<? AND until<?", (time.time() - 86400, time.time()))


def _password_ok(password: str) -> bool:
    return bool(config.PANEL_PASSWORD) and hmac.compare_digest(password.encode(), config.PANEL_PASSWORD.encode())


def lock_on(c) -> bool:
    return db.kv_get(c, LOCK_KEY) != "0"


def _notify(text: str) -> None:
    try:
        from . import tg_notify
        tg_notify.send(text)
    except Exception:  # noqa: BLE001
        pass


def login(request: Request, password: str, device_token: str | None) -> dict:
    """{"session": توکن یا None، "device": توکن کوکی دستگاه، "status": trusted | pending}
    رمز اشتباه ← 401، تلاش زیاد ← 429، دستگاه برداشته‌شده ← 403."""
    ip, now = _ip(request), time.time()
    with _LOGIN_LOCK, db.connect() as c:
        ensure(c)
        count = _check_lock(c, ip)
        if not _password_ok(password):
            _fail(c, ip, count)
            raise HTTPException(401, "رمز اشتباه است")
        c.execute("DELETE FROM login_fails WHERE ip=?", (ip,))
        token = device_token if device_token and 20 <= len(device_token) <= 200 else secrets.token_urlsafe(32)
        did, name = _hash(token), device_name(request.headers.get("user-agent", ""))
        row = c.execute("SELECT status FROM devices WHERE id=?", (did,)).fetchone()
        status = row["status"] if row else None
        if status == "revoked":
            raise HTTPException(403, "این دستگاه از فهرست دستگاه‌های پنل برداشته شده است")
        if status != "trusted":
            first = not c.execute("SELECT 1 FROM devices WHERE status='trusted'").fetchone()
            status = "trusted" if first or not lock_on(c) else "pending"
            c.execute("INSERT INTO devices(id,name,status,created_at,last_seen,last_ip) VALUES (?,?,?,?,?,?) "
                      "ON CONFLICT(id) DO UPDATE SET status=excluded.status, last_seen=excluded.last_seen, last_ip=excluded.last_ip",
                      (did, name, status, now, now, ip))
            if status == "pending":
                _notify(f"🔐 درخواست ورود به پنل از دستگاه تازه\n{name} · IP {ip}\n\nاگر خودتان هستید: از دستگاه "
                        "شناخته‌شده‌تان پنل ← بیشتر ← حساب و رمز ← دستگاه‌ها ← تأیید. اگر شما نیستید، رمز پنل را عوض کنید.")
                return {"session": None, "device": token, "status": "pending"}
            _notify(f"🔑 ورود به پنل از دستگاه تازه: {name} · IP {ip}" + (" (اولین دستگاه شناخته‌شده)" if first else ""))
        c.execute("UPDATE devices SET last_seen=?, last_ip=? WHERE id=?", (now, ip, did))
        session = secrets.token_urlsafe(32)
        db.add_session(c, session, config.SESSION_TTL)
        c.execute("UPDATE sessions SET device_id=? WHERE token=?", (did, session))
    return {"session": session, "device": token, "status": "trusted"}


def set_device_cookie(response: Response, token: str) -> None:
    response.set_cookie(DEVICE_COOKIE, token, max_age=DEVICE_TTL, httponly=True, secure=config.COOKIE_SECURE,
                        samesite="lax", path="/")


def require_session(request: Request, response: Response,
                    session: str | None = Cookie(default=None, alias=COOKIE),
                    device: str | None = Cookie(default=None, alias=DEVICE_COOKIE)) -> str:
    if not session:
        raise HTTPException(401)
    with db.connect() as c:
        r = c.execute("SELECT expires_at, device_id FROM sessions WHERE token=?", (session,)).fetchone()
        if not r or r["expires_at"] <= time.time():
            raise HTTPException(401)
        if not r["device_id"]:
            # ورودی که پیش از دستگاه‌ها ساخته شده: همین دستگاه شناخته‌شده می‌شود (گوشی صاحب پیج بعد از انتشار)
            ensure(c)
            token = device if device and 20 <= len(device) <= 200 else secrets.token_urlsafe(32)
            did, now = _hash(token), time.time()
            c.execute("INSERT INTO devices(id,name,status,created_at,last_seen,last_ip) VALUES (?,?,'trusted',?,?,?) "
                      "ON CONFLICT(id) DO UPDATE SET status='trusted'",
                      (did, device_name(request.headers.get("user-agent", "")), now, now, _ip(request)))
            c.execute("UPDATE sessions SET device_id=? WHERE token=?", (did, session))
            if token != device:
                set_device_cookie(response, token)
    return session


def current_device(c, session: str) -> str:
    r = c.execute("SELECT device_id FROM sessions WHERE token=?", (session,)).fetchone()
    return (r["device_id"] if r else "") or ""


def touch_device(c, session: str, ip: str) -> None:
    did = current_device(c, session)
    if did:
        c.execute("UPDATE devices SET last_seen=?, last_ip=? WHERE id=?", (time.time(), ip, did))


def devices(c, session: str) -> dict:
    ensure(c)
    cur = current_device(c, session)
    rows = [dict(r) | {"current": r["id"] == cur} for r in
            c.execute("SELECT * FROM devices WHERE status<>'revoked' ORDER BY status='pending' DESC, last_seen DESC")]
    return {"items": rows, "lock": lock_on(c)}


def set_device(c, session: str, did: str, action: str) -> None:
    ensure(c)
    if action == "approve":
        if not c.execute("UPDATE devices SET status='trusted' WHERE id=? AND status='pending'", (did,)).rowcount:
            raise HTTPException(404, "درخواستی برای این دستگاه نیست")
    elif action == "revoke":
        if did == current_device(c, session):
            raise HTTPException(409, "دستگاهی که با آن کار می‌کنید برداشته نمی‌شود؛ از دستگاه دیگر یا با «خروج»")
        c.execute("UPDATE devices SET status='revoked' WHERE id=?", (did,))
        c.execute("DELETE FROM sessions WHERE device_id=?", (did,))
    else:
        raise HTTPException(422, "کار نامعتبر")


def change_password(request: Request, session: str, current: str, new: str) -> None:
    """تغییر رمز پنل از خود پنل: رمز فعلی با همان قفل تلاش ناموفق بررسی می‌شود، رمز تازه در ‎.env‎
    (فقط همان خط، دسترسی ۶۰۰) نوشته و همان لحظه فعال می‌شود، و همه‌ی ورودهای دیگر باطل می‌شوند."""
    from . import secrets_env
    ip = _ip(request)
    with _LOGIN_LOCK, db.connect() as c:
        ensure(c)
        count = _check_lock(c, ip)
        if not _password_ok(current):
            _fail(c, ip, count)
            raise HTTPException(401, "رمز فعلی اشتباه است")
        c.execute("DELETE FROM login_fails WHERE ip=?", (ip,))
    if not PASSWORD_RX.match(new):
        # \ و گیومه و $ در فایل ‎.env‎ با ری‌استارت معنی دیگری می‌گیرند و رمز عملاً عوض می‌شد
        raise HTTPException(422, f"رمز تازه باید دست‌کم {MIN_PASSWORD} نویسه باشد و فقط حرف انگلیسی، عدد و "
                                 "این نشانه‌ها: ! @ % ^ * _ + = . , : / ? ~ -")
    if new == current:
        raise HTTPException(422, "رمز تازه با رمز فعلی یکی است")
    try:
        secrets_env.write_env("PANEL_PASSWORD", new)
    except ValueError as e:
        raise HTTPException(500, str(e))
    with db.connect() as c:
        c.execute("DELETE FROM sessions WHERE token<>?", (session,))   # دستگاه‌های دیگر خارج شوند


def weak_password() -> bool:
    return len(config.PANEL_PASSWORD or "") < MIN_PASSWORD
