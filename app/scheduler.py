"""زمان‌بندی انتشار پست، ریلز و استوری.

صاحب پیج در پنل فایل را می‌گذارد و ساعت را خودش انتخاب می‌کند (همین یعنی تأیید صریح و زمان تعیین‌شده)؛
سرور همان ساعت منتشر می‌کند. اگر سرور در آن ساعت خاموش بوده و بیش از LATE_LIMIT گذشته باشد، دیر منتشر
نمی‌کند و «ناموفق» می‌شود (درس استوری‌هایی که دیر رفتند).

اینستاگرام فایل را از یک نشانی عمومی برمی‌دارد: فایل‌ها با نام تصادفی در پوشه‌ی داده ذخیره و از
‎/media/<نام>‎ داده می‌شوند (بدون ورود، ولی نام حدس‌زدنی نیست) و چند روز بعد از انتشار پاک می‌شوند.
"""
import asyncio
import os
import re
import secrets
import time
from pathlib import Path

from . import config, db

SCHEMA = """
CREATE TABLE IF NOT EXISTS scheduled_posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,              -- post | reel | story
  file TEXT NOT NULL,
  caption TEXT NOT NULL DEFAULT '',
  publish_at REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'scheduled',   -- scheduled | publishing | done | failed | canceled
  error TEXT NOT NULL DEFAULT '',
  ig_id TEXT NOT NULL DEFAULT '',
  permalink TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL,
  published_at REAL
);
"""
KINDS = {"post": "پست", "reel": "ریلز", "story": "استوری"}
IMAGE_EXT, VIDEO_EXT = {"jpg", "jpeg"}, {"mp4", "mov"}
MAX_BYTES = int(os.environ.get("UPLOAD_MAX_MB", "100")) * 1024 * 1024
LATE_LIMIT = 45 * 60
KEEP_DAYS = 3
_NAME_RX = re.compile(r"^[a-f0-9]{32}\.(?:jpg|jpeg|mp4|mov)$")


def ensure(c) -> None:
    c.executescript(SCHEMA)


def uploads_dir() -> Path:
    d = Path(config.DB_PATH).parent / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def public_url(name: str) -> str:
    return f"{config.PUBLIC_URL.rstrip('/')}/media/{name}"


def file_path(name: str) -> Path | None:
    """فقط نام‌هایی که خودمان ساخته‌ایم؛ هیچ مسیر دیگری."""
    if not _NAME_RX.fullmatch(name or ""):
        return None
    p = uploads_dir() / name
    return p if p.is_file() else None


async def save_upload(stream, filename: str) -> dict:
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if ext not in IMAGE_EXT | VIDEO_EXT:
        raise ValueError("فقط عکس JPG و ویدیوی MP4 یا MOV پذیرفته می‌شود")
    name = f"{secrets.token_hex(16)}.{ext}"
    path, size = uploads_dir() / name, 0
    try:
        with open(path, "wb") as f:
            async for chunk in stream:
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError(f"حجم فایل بیشتر از {MAX_BYTES // 1024 // 1024} مگابایت است")
                f.write(chunk)
        if not size:
            raise ValueError("فایل خالی است")
    except ValueError:
        path.unlink(missing_ok=True)
        raise
    return {"file": name, "size": size, "video": ext in VIDEO_EXT}


def create(c, kind: str, file: str, caption: str, publish_at: float, now: float | None = None) -> int:
    ensure(c)
    now = now or time.time()
    if kind not in KINDS:
        raise ValueError("نوع محتوا نامعتبر است")
    if not file_path(file):
        raise ValueError("فایل پیدا نشد؛ دوباره انتخابش کنید")
    video = file.rsplit(".", 1)[-1] in VIDEO_EXT
    if kind == "reel" and not video:
        raise ValueError("ریلز باید ویدیو باشد")
    if kind == "post" and video:
        raise ValueError("ویدیو را به‌صورت «ریلز» زمان‌بندی کنید")
    if publish_at < now + 60:
        raise ValueError("زمان انتشار باید دست‌کم یک دقیقه‌ی دیگر باشد")
    if publish_at > now + 60 * 86400:
        raise ValueError("زمان انتشار حداکثر تا ۶۰ روز دیگر")
    if len(caption) > 2200:
        raise ValueError("کپشن بیشتر از ۲۲۰۰ نویسه است")
    cur = c.execute("INSERT INTO scheduled_posts(kind,file,caption,publish_at,created_at) VALUES (?,?,?,?,?)",
                    (kind, file, "" if kind == "story" else caption.strip(), publish_at, now))
    return cur.lastrowid


def listing(c) -> list[dict]:
    ensure(c)
    rows = c.execute("SELECT * FROM scheduled_posts WHERE status IN ('scheduled','publishing') ORDER BY publish_at").fetchall()
    rows += c.execute("SELECT * FROM scheduled_posts WHERE status NOT IN ('scheduled','publishing') "
                      "ORDER BY publish_at DESC LIMIT 20").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["video"] = d["file"].rsplit(".", 1)[-1] in VIDEO_EXT
        d["preview"] = f"/media/{d['file']}" if file_path(d["file"]) else ""
        out.append(d)
    return out


def cancel(c, pid: int) -> bool:
    ensure(c)
    return c.execute("UPDATE scheduled_posts SET status='canceled' WHERE id=? AND status='scheduled'", (pid,)).rowcount > 0


async def publish(ig, row, wait: float = 5, tries: int = 72) -> tuple[str, str]:
    """ساخت ظرف رسانه ← صبر تا آماده شود ← انتشار. (شناسه، لینک)"""
    url, video = public_url(row["file"]), row["file"].rsplit(".", 1)[-1] in VIDEO_EXT
    body = {"video_url": url} if video else {"image_url": url}
    if row["kind"] == "story":
        body["media_type"] = "STORIES"
    elif row["kind"] == "reel":
        body["media_type"] = "REELS"
    if row["kind"] != "story" and row["caption"]:
        body["caption"] = row["caption"]
    cid = (await ig._post(f"{ig.user_id}/media", json=body))["id"]
    for _ in range(tries if video else 12):
        st = (await ig._get(cid, fields="status_code")).get("status_code", "")
        if st == "FINISHED":
            break
        if st in ("ERROR", "EXPIRED"):
            raise RuntimeError("اینستاگرام فایل را نپذیرفت (قالب، اندازه یا مدت ویدیو را بررسی کنید)")
        await asyncio.sleep(wait)
    else:
        raise RuntimeError("آماده شدن فایل در اینستاگرام بیش از حد طول کشید")
    mid = (await ig._post(f"{ig.user_id}/media_publish", json={"creation_id": cid}))["id"]
    try:
        link = (await ig._get(mid, fields="permalink")).get("permalink", "")
    except Exception:  # noqa: BLE001
        link = ""
    return mid, link


async def run_due(ig, now: float | None = None, wait: float = 5) -> int:
    """هر چه زمانش رسیده منتشر می‌کند. خروجی: تعداد منتشرشده."""
    from . import tg_notify
    now = now or time.time()
    with db.connect() as c:
        ensure(c)
        due = c.execute("SELECT * FROM scheduled_posts WHERE status='scheduled' AND publish_at<=? ORDER BY publish_at",
                        (now,)).fetchall()
        for r in due:      # پیش از هر کار بیرونی علامت می‌خورد تا هرگز دو بار منتشر نشود
            late = now - r["publish_at"] > LATE_LIMIT
            c.execute("UPDATE scheduled_posts SET status=?, error=? WHERE id=?",
                      ("failed" if late else "publishing", "زمان انتشار گذشته بود؛ دیر منتشر نشد" if late else "", r["id"]))
    done = 0
    for r in due:
        if now - r["publish_at"] > LATE_LIMIT:
            tg_notify.send(f"⚠️ {KINDS[r['kind']]} زمان‌بندی‌شده منتشر نشد: زمانش گذشته بود.")
            continue
        try:
            mid, link = await publish(ig, r, wait=wait)
            with db.connect() as c:
                c.execute("UPDATE scheduled_posts SET status='done', ig_id=?, permalink=?, published_at=? WHERE id=?",
                          (mid, link, time.time(), r["id"]))
                if r["kind"] != "story":
                    db.bind_next_post(c, mid, time.time())
            tg_notify.send(f"✅ {KINDS[r['kind']]} زمان‌بندی‌شده منتشر شد.\n{link}".strip())
            done += 1
        except Exception as e:  # noqa: BLE001
            with db.connect() as c:
                c.execute("UPDATE scheduled_posts SET status='failed', error=? WHERE id=?", (str(e)[:300], r["id"]))
            tg_notify.send(f"⚠️ {KINDS[r['kind']]} زمان‌بندی‌شده منتشر نشد.\n{str(e)[:200]}")
    return done


def cleanup(now: float | None = None) -> int:
    """فایل‌هایی که دیگر به زمان‌بندی بازی وصل نیستند و چند روز از عمرشان گذشته."""
    now = now or time.time()
    with db.connect() as c:
        ensure(c)
        keep = {r[0] for r in c.execute("SELECT file FROM scheduled_posts WHERE status IN ('scheduled','publishing') "
                                        "OR COALESCE(published_at, created_at)>?", (now - KEEP_DAYS * 86400,))}
    n = 0
    for p in uploads_dir().iterdir():
        if p.name not in keep and now - p.stat().st_mtime > 86400:
            p.unlink(missing_ok=True)
            n += 1
    return n


async def loop(ig, stop: asyncio.Event, interval: float = 30) -> None:
    with db.connect() as c:      # انتشاری که وسطش سرویس ری‌استارت شد: معلوم نیست رفته یا نه؛ دوباره نمی‌فرستیم
        ensure(c)
        c.execute("UPDATE scheduled_posts SET status='failed', error='سرویس وسط انتشار ری‌استارت شد؛ پیج را نگاه کنید' "
                  "WHERE status='publishing'")
    last_clean = 0.0
    while not stop.is_set():
        try:
            await run_due(ig)
            if time.time() - last_clean > 6 * 3600:
                last_clean = time.time()
                cleanup()
        except Exception as e:  # noqa: BLE001
            print("scheduler failed:", e)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
