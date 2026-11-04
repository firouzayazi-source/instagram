"""ثبت کلید سرویس‌های هوش مصنوعی از پنل، مستقیم در ‎/opt/igbot/.env‎ (تنها جای رازهای پروژه).

کلید هیچ‌وقت به پنل برنمی‌گردد؛ فقط «تنظیم شده» و چهار نویسه‌ی آخرش. فایل اتمی و با دسترسی ۶۰۰ نوشته
می‌شود، خط‌های دیگرش دست نمی‌خورد، و کلید تازه بی‌ری‌استارت همان لحظه به کار می‌افتد.
فقط نام‌های فهرست ALLOWED قابل تغییرند (نه توکن اینستاگرام و تلگرام و رمز پنل).
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
    return out


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
    elif name == "CUSTOM_AI_NAME":
        if "\n" in value or len(value) > 60:
            raise ValueError("نام کوتاه‌تر بنویسید")
    elif not _SAFE.match(value):
        raise ValueError("کلید نامعتبر است (فاصله یا نویسه‌ی غیرمجاز دارد، یا خیلی کوتاه است)")
    return value


def set_value(name: str, value: str) -> list[dict]:
    """value خالی یعنی حذف. خطای نوشتن فایل با پیام فارسی و دستور رفعش برمی‌گردد."""
    value = _validate(name, value)
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
    tmp = p.with_name(p.name + ".tmp")
    try:
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        os.replace(tmp, p)
    except OSError as e:
        raise ValueError(f"نوشتن در ‎.env‎ ممکن نشد ({e.strerror}). روی سرور: "
                         "chown igbot:igbot /opt/igbot/.env && chmod 600 /opt/igbot/.env")
    if value:
        os.environ[name] = value
    else:
        os.environ.pop(name, None)
    setattr(config, name, value)
    ai._clients.clear()          # کلاینت‌ها با کلید تازه ساخته شوند
    return status()
