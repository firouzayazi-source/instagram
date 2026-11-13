"""ثبت کلید سرویس‌های هوش مصنوعی از پنل، مستقیم در ‎/opt/igbot/.env‎ (تنها جای رازهای پروژه).

کلید هیچ‌وقت به پنل برنمی‌گردد؛ فقط «تنظیم شده» و چهار نویسه‌ی آخرش. فایل درجا و با دسترسی ۶۰۰ نوشته
می‌شود، خط‌های دیگرش دست نمی‌خورد، و کلید تازه بی‌ری‌استارت همان لحظه به کار می‌افتد.
فقط نام‌های فهرست allowed() قابل تغییرند: کلید سرویس‌های هوش مصنوعی و پل Composio (نه توکن اینستاگرام و تلگرام و رمز پنل).
"""
import os
import re
from pathlib import Path

from . import ai, config


def env_path() -> Path:
    return Path(os.environ.get("IGBOT_ENV_FILE") or (config.ROOT / ".env"))


def allowed() -> dict:
    """نام متغیر ← برچسب. کلید هر سرویس، به‌علاوه‌ی آدرس و نام سرویس دلخواه."""
    out = {p["key"]: p["label"] for p in ai.PROVIDERS.values()}
    out.update({"CUSTOM_AI_BASE_URL": "آدرس سرویس دلخواه", "CUSTOM_AI_NAME": "نام سرویس دلخواه"})
    out.update(COMPOSIO)
    return out




# پل موقت Composio برای خواندن آمار اینستاگرام (تحلیل محتوا) تا اتصال اپ Meta خود پروژه
COMPOSIO = {"COMPOSIO_API_KEY": "کلید Composio (آمار اینستاگرام)",
            "COMPOSIO_ACCOUNT_ID": "شناسه‌ی اتصال اینستاگرام در Composio (فقط برای کلید ak_)",
            "COMPOSIO_USER_ID": "شناسه‌ی کاربر در Composio (اختیاری، فقط برای کلید ak_)"}
_ID = re.compile(r"^[A-Za-z0-9_.:@-]{2,120}$")


_SAFE = re.compile(r"^[\x21-\x7e]{8,300}$")          # کلید: نویسه‌های چاپی بی‌فاصله
_URL = re.compile(r"^(https://[^\s]+|http://(?:127\.0\.0\.1|localhost)(?::\d+)?(?:/[^\s]*)?)$")


def _current(name: str) -> str:
    return (getattr(config, name, "") or os.environ.get(name, "") or "").strip()


def status() -> list[dict]:
    out = []
    for name, label in allowed().items():
        v = _current(name)
        secret = name.endswith("_KEY")
        out.append({"name": name, "label": label, "set": bool(v), "secret": secret,
                    "hint": (f"…{v[-4:]}" if secret and len(v) > 8 else ("" if secret else v))})
    return out


def _validate(name: str, value: str) -> str:
    value = (value or "").strip()
    if name not in allowed():
        raise ValueError("این مقدار از پنل تغییر نمی‌کند")
    if not value:
        return ""
    if name == "CUSTOM_AI_BASE_URL":
        if not _URL.match(value) or len(value) > 300:
            raise ValueError("آدرس باید با https:// شروع شود (یا http:// فقط برای همین سرور)")
    elif name in ("COMPOSIO_ACCOUNT_ID", "COMPOSIO_USER_ID"):
        if not _ID.match(value):
            raise ValueError("شناسه فقط حرف لاتین، عدد و - _ . : @ دارد")
    elif name == "CUSTOM_AI_NAME":
        if "\n" in value or len(value) > 60:
            raise ValueError("نام کوتاه‌تر بنویسید")
    elif not _SAFE.match(value):
        raise ValueError("کلید نامعتبر است (فاصله یا نویسه‌ی غیرمجاز دارد، یا خیلی کوتاه است)")
    return value


def set_value(name: str, value: str) -> list[dict]:
    """value خالی یعنی حذف. خطای نوشتن فایل با پیام فارسی و دستور رفعش برمی‌گردد."""
    value = _validate(name, value)
    write_env(name, value)
    ai._clients.clear()          # کلاینت‌ها با کلید تازه ساخته شوند
    return status()


def write_env(name: str, value: str) -> None:
    """فقط خط همین نام در ‎.env‎ عوض می‌شود و همان لحظه در برنامه هم فعال می‌شود. بی‌اعتبارسنجی؛
    صدازننده مسئول است (set_value برای کلیدها، auth.change_password برای رمز پنل)."""
    p = env_path()
    try:
        lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    except OSError as e:
        raise ValueError(f"فایل ‎.env‎ خوانده نشد: {e.strerror}")
    out, done = [], False
    for ln in lines:
        if re.match(rf"^\s*{re.escape(name)}\s*=", ln):
            if value and not done:
                out.append(f"{name}={value}")
            done = True
            continue
        out.append(ln)
    if value and not done:
        out.append(f"{name}={value}")
    data = ("\n".join(out) + "\n").encode("utf-8")
    try:
        # درجا نوشته می‌شود، نه فایل موقت + جابه‌جایی: سرویس فقط اجازه‌ی نوشتن در خود این فایل را دارد
        # (پوشه‌ی برنامه فقط‌خواندنی است). فایل کوچک است و با fsync یکجا روی دیسک می‌رود.
        fd = os.open(str(p), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            os.ftruncate(fd, 0)
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.chmod(p, 0o600)
    except OSError as e:
        hint = ("سرویس igbot هنوز به‌روز نشده؛ روی سرور: bash /opt/igbot/deploy/deploy.sh"
                if e.errno == 30 else "روی سرور: chown igbot:igbot /opt/igbot/.env && chmod 600 /opt/igbot/.env")
        raise ValueError(f"نوشتن در ‎.env‎ ممکن نشد ({e.strerror}). {hint}")
    if value:
        os.environ[name] = value
    else:
        os.environ.pop(name, None)
    setattr(config, name, value)
