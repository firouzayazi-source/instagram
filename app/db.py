"""SQLite با حالت WAL. یک اتصال در هر فراخوانی؛ برای یک پیج کافی است."""
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,            -- comment | message
  payload TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',  -- pending | done | error | skipped
  error TEXT,
  created_at REAL NOT NULL,
  processed_at REAL
);
CREATE INDEX IF NOT EXISTS events_status ON events(status, created_at);

CREATE TABLE IF NOT EXISTS rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  priority INTEGER NOT NULL DEFAULT 100,
  channels TEXT NOT NULL,        -- JSON: ["comment","dm"]
  post_scope TEXT NOT NULL,      -- JSON: "all" | ["media_id", ...]
  triggers TEXT NOT NULL,        -- JSON: [{"match":"exact","value":"تقویم"}]
  actions TEXT NOT NULL,         -- JSON: {"public_replies":[],"private_replies":[],"dm_replies":[]}
  advanced TEXT NOT NULL,        -- JSON
  use_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS replies (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL,
  rule_id INTEGER,
  kind TEXT NOT NULL,            -- public | private | dm
  target_id TEXT NOT NULL,
  text TEXT NOT NULL,
  ig_id TEXT,
  ok INTEGER NOT NULL,
  error TEXT,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS user_rule_hits (
  rule_id INTEGER NOT NULL,
  user_id TEXT NOT NULL,
  last_at REAL NOT NULL,
  PRIMARY KEY (rule_id, user_id)
);

CREATE TABLE IF NOT EXISTS followups (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  rule_id INTEGER NOT NULL,          -- ۰ یعنی پیام گروهی از پنل
  user_id TEXT NOT NULL,
  text TEXT NOT NULL,
  due_at REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',  -- pending | done | error
  error TEXT
);
CREATE INDEX IF NOT EXISTS followups_due ON followups(status, due_at);

CREATE TABLE IF NOT EXISTS comments (
  id TEXT PRIMARY KEY,
  media_id TEXT,
  user_id TEXT NOT NULL,
  username TEXT,
  text TEXT NOT NULL,
  parent_id TEXT,
  created_at REAL NOT NULL,
  read INTEGER NOT NULL DEFAULT 0,
  answered INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS comments_created ON comments(created_at DESC);

CREATE TABLE IF NOT EXISTS conversations (
  user_id TEXT PRIMARY KEY,
  username TEXT,
  last_text TEXT,
  last_at REAL NOT NULL,
  read INTEGER NOT NULL DEFAULT 0,
  answered INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  direction TEXT NOT NULL,       -- in | out
  text TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_user ON messages(user_id, created_at);

CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  created_at REAL NOT NULL,
  expires_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS push_subs (
  endpoint TEXT PRIMARY KEY,
  sub TEXT NOT NULL,             -- JSON کامل اشتراک
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);

-- ---------- پاسخ هوشمند ----------
CREATE TABLE IF NOT EXISTS faq (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  question TEXT NOT NULL,
  keywords TEXT NOT NULL DEFAULT '',
  answer TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  hits INTEGER NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS docs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  chars INTEGER NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS doc_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id INTEGER NOT NULL REFERENCES docs(id) ON DELETE CASCADE,
  idx INTEGER NOT NULL,
  text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS doc_chunks_doc ON doc_chunks(doc_id);

CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  storage TEXT NOT NULL DEFAULT '',
  color TEXT NOT NULL DEFAULT '',
  condition TEXT NOT NULL DEFAULT 'new',   -- new | used | stock
  price INTEGER,                           -- تومان؛ خالی یعنی «استعلام»
  in_stock INTEGER NOT NULL DEFAULT 1,
  notes TEXT NOT NULL DEFAULT '',
  enabled INTEGER NOT NULL DEFAULT 1,
  updated_at REAL NOT NULL,
  source TEXT NOT NULL DEFAULT '',         -- '' دستی | site همگام‌شده از سایت
  url TEXT NOT NULL DEFAULT ''             -- لینک محصول در سایت
);

CREATE TABLE IF NOT EXISTS blocked_users (
  user_id TEXT PRIMARY KEY,
  username TEXT,
  reason TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at REAL NOT NULL,
  event_id TEXT,
  channel TEXT NOT NULL,
  user_id TEXT,
  username TEXT,
  input TEXT NOT NULL,
  action TEXT NOT NULL,          -- reply | handoff | ignore | skip | error
  intent TEXT,
  confidence REAL,
  reply TEXT,
  public_reply TEXT,
  handoff_reason TEXT,
  skip_reason TEXT,
  model TEXT,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  cache_read INTEGER NOT NULL DEFAULT 0,
  cache_write INTEGER NOT NULL DEFAULT 0,
  cost REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending',  -- pending | sent | failed | test | none
  error TEXT,
  feedback TEXT,                 -- good | bad
  is_test INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ai_log_created ON ai_log(created_at DESC);

CREATE TABLE IF NOT EXISTS handoffs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at REAL NOT NULL,
  channel TEXT NOT NULL,
  user_id TEXT NOT NULL,
  username TEXT,
  comment_id TEXT,
  text TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  intent TEXT,
  ai_log_id INTEGER,
  status TEXT NOT NULL DEFAULT 'open',     -- open | done
  resolved_at REAL
);
CREATE INDEX IF NOT EXISTS handoffs_status ON handoffs(status, created_at DESC);

-- پرونده‌ی مشتری (CRM): هر نفر در هر کانال یک پرونده
CREATE TABLE IF NOT EXISTS customers (
  id TEXT PRIMARY KEY,                 -- کانال:شناسه، مثل ig:1789...
  channel TEXT NOT NULL,
  user_id TEXT NOT NULL,
  username TEXT,
  name TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL DEFAULT '',
  tags TEXT NOT NULL DEFAULT '[]',
  notes TEXT NOT NULL DEFAULT '',
  first_seen REAL NOT NULL,
  last_seen REAL NOT NULL,
  messages INTEGER NOT NULL DEFAULT 0,
  comments INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS customers_last ON customers(last_seen DESC);

-- ربات برای این گفتگو تا این زمان ساکت است (همکار جواب داده)
CREATE TABLE IF NOT EXISTS human_mode (
  user_id TEXT PRIMARY KEY,
  until REAL NOT NULL
);

-- یادداشت و محصول هر پست یا استوری، تا مغز مرکزی بداند جواب و کامنت درباره‌ی چیست
CREATE TABLE IF NOT EXISTS media_notes (
  media_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL DEFAULT 'post',   -- post | story
  note TEXT NOT NULL DEFAULT '',
  product TEXT NOT NULL DEFAULT '',
  updated_at REAL NOT NULL
);

-- سفارش‌هایی که مشتری در دایرکت ثبت کرده (فروش در دایرکت)
CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  channel TEXT NOT NULL DEFAULT 'ig',
  user_id TEXT NOT NULL,
  username TEXT,
  product TEXT NOT NULL DEFAULT '',
  product_id TEXT NOT NULL DEFAULT '',
  price INTEGER,
  name TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL DEFAULT '',
  city TEXT NOT NULL DEFAULT '',
  address TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'awaiting_payment',  -- awaiting_payment | receipt | confirmed | shipped | done | canceled
  receipt_url TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS orders_created ON orders(created_at DESC);
CREATE INDEX IF NOT EXISTS orders_user ON orders(user_id, created_at DESC);

-- جواب‌هایی که مشتری پسندید و به دانش آفلاین (موتور فهم مشترک) رفت
CREATE TABLE IF NOT EXISTS learned (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  log_id INTEGER NOT NULL,
  channel TEXT NOT NULL,
  question TEXT NOT NULL,
  qnorm TEXT NOT NULL UNIQUE,
  answer TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'learned',   -- learned | undone
  created_at REAL NOT NULL
);

-- حافظه‌ی کوتاه گفتگو: آخرین مدل و بودجه‌ای که مشتری گفته (تا لازم نباشد دوباره بپرسیم)
CREATE TABLE IF NOT EXISTS conv_memo (
  user_id TEXT PRIMARY KEY,
  product TEXT NOT NULL DEFAULT '',
  budget INTEGER NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL
);

-- پیگیری خودکار مشتری ساکت: هر نفر فقط یک بار
CREATE TABLE IF NOT EXISTS auto_followups (
  user_id TEXT PRIMARY KEY,
  sent_at REAL NOT NULL,
  ok INTEGER NOT NULL DEFAULT 1
);

-- گفتگوی سفارش در حال انجام: ربات قدم‌به‌قدم اطلاعات را می‌پرسد
CREATE TABLE IF NOT EXISTS order_flow (
  user_id TEXT PRIMARY KEY,
  step TEXT NOT NULL,
  data TEXT NOT NULL DEFAULT '{}',
  updated_at REAL NOT NULL
);
"""


def init(path: str | None = None) -> None:
    p = Path(path or config.DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    with connect(str(p)) as c:
        c.executescript(SCHEMA)
        _migrate(c)


# ستون‌هایی که بعد از ساخت جدول اضافه شده‌اند؛ پایگاه داده‌ی قدیمی بی‌خطر ارتقا می‌یابد
_COLUMNS = {
    "products": {"source": "TEXT NOT NULL DEFAULT ''", "url": "TEXT NOT NULL DEFAULT ''"},
    "comments": {"hidden": "INTEGER NOT NULL DEFAULT 0", "hidden_reason": "TEXT NOT NULL DEFAULT ''"},
    "messages": {"sender": "TEXT NOT NULL DEFAULT ''"},   # پیام بیرونی: bot | admin
    "ai_log": {"customer_vote": "TEXT NOT NULL DEFAULT ''", "voted_at": "REAL"},   # رضایت مشتری: up | down
}


def _migrate(c) -> None:
    for table, cols in _COLUMNS.items():
        have = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
        for name, decl in cols.items():
            if name not in have:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


@contextmanager
def connect(path: str | None = None):
    c = sqlite3.connect(path or config.DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def add_event(c: sqlite3.Connection, event_id: str, kind: str, payload: dict) -> bool:
    """False اگر رویداد تکراری بود."""
    try:
        c.execute(
            "INSERT INTO events(id, kind, payload, created_at) VALUES (?,?,?,?)",
            (event_id, kind, json.dumps(payload, ensure_ascii=False), time.time()),
        )
        return True
    except sqlite3.IntegrityError:
        return False


def pending_events(c: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    return c.execute(
        "SELECT * FROM events WHERE status='pending' ORDER BY created_at LIMIT ?", (limit,)
    ).fetchall()


def finish_event(c: sqlite3.Connection, event_id: str, status: str, error: str | None = None) -> None:
    c.execute(
        "UPDATE events SET status=?, error=?, processed_at=? WHERE id=?",
        (status, error, time.time(), event_id),
    )


def load_rules(c: sqlite3.Connection) -> list[dict]:
    rows = c.execute("SELECT * FROM rules WHERE enabled=1 ORDER BY priority, id").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("channels", "post_scope", "triggers", "actions", "advanced"):
            d[k] = json.loads(d[k])
        out.append(d)
    return out


def upsert_rule(c: sqlite3.Connection, rule: dict) -> int:
    cols = ("name", "enabled", "priority", "channels", "post_scope", "triggers", "actions", "advanced")
    vals = [
        rule["name"],
        int(rule.get("enabled", True)),
        int(rule.get("priority", 100)),
        json.dumps(rule.get("channels", ["comment"]), ensure_ascii=False),
        json.dumps(rule.get("post_scope", "all"), ensure_ascii=False),
        json.dumps(rule.get("triggers", [{"match": "any"}]), ensure_ascii=False),
        json.dumps(rule.get("actions", {}), ensure_ascii=False),
        json.dumps(rule.get("advanced", {}), ensure_ascii=False),
    ]
    if rule.get("id"):
        c.execute(f"UPDATE rules SET {', '.join(f'{k}=?' for k in cols)} WHERE id=?", [*vals, rule["id"]])
        return rule["id"]
    cur = c.execute(f"INSERT INTO rules({', '.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
    return cur.lastrowid


def bump_rule(c: sqlite3.Connection, rule_id: int) -> int:
    c.execute("UPDATE rules SET use_count=use_count+1 WHERE id=?", (rule_id,))
    return c.execute("SELECT use_count FROM rules WHERE id=?", (rule_id,)).fetchone()[0]


def last_hit(c: sqlite3.Connection, rule_id: int, user_id: str) -> float | None:
    r = c.execute(
        "SELECT last_at FROM user_rule_hits WHERE rule_id=? AND user_id=?", (rule_id, user_id)
    ).fetchone()
    return r[0] if r else None


def record_hit(c: sqlite3.Connection, rule_id: int, user_id: str) -> None:
    c.execute(
        "INSERT INTO user_rule_hits(rule_id,user_id,last_at) VALUES (?,?,?) "
        "ON CONFLICT(rule_id,user_id) DO UPDATE SET last_at=excluded.last_at",
        (rule_id, user_id, time.time()),
    )


def log_reply(c, event_id, rule_id, kind, target_id, text, ig_id=None, ok=True, error=None) -> None:
    c.execute(
        "INSERT INTO replies(event_id,rule_id,kind,target_id,text,ig_id,ok,error,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (event_id, rule_id, kind, target_id, text, ig_id, int(ok), error, time.time()),
    )


def add_followup(c: sqlite3.Connection, rule_id: int, user_id: str, text: str, after_seconds: float) -> None:
    c.execute(
        "INSERT INTO followups(rule_id,user_id,text,due_at) VALUES (?,?,?,?)",
        (rule_id, user_id, text, time.time() + after_seconds),
    )


def due_followups(c: sqlite3.Connection, now: float | None = None) -> list[sqlite3.Row]:
    return c.execute(
        "SELECT * FROM followups WHERE status='pending' AND due_at<=? ORDER BY due_at LIMIT 20",
        (now or time.time(),),
    ).fetchall()


def finish_followup(c: sqlite3.Connection, fid: int, status: str, error: str | None = None) -> None:
    c.execute("UPDATE followups SET status=?, error=? WHERE id=?", (status, error, fid))


# ---------- صندوق کامنت و پیام ----------

def add_comment(c, cid, media_id, user_id, username, text, parent_id=None) -> None:
    c.execute(
        "INSERT OR IGNORE INTO comments(id,media_id,user_id,username,text,parent_id,created_at) VALUES (?,?,?,?,?,?,?)",
        (cid, media_id, user_id, username, text, parent_id, time.time()),
    )


def mark_comment(c, cid, *, read=None, answered=None) -> None:
    if read is not None:
        c.execute("UPDATE comments SET read=? WHERE id=?", (int(read), cid))
    if answered is not None:
        c.execute("UPDATE comments SET answered=? WHERE id=?", (int(answered), cid))


_FILTERS = {"all": "1", "unread": "read=0", "unanswered": "answered=0", "answered": "answered=1"}


def list_comments(c, filt="all", limit=50, before: float | None = None) -> list[dict]:
    where = _FILTERS.get(filt, "1")
    args: list = []
    if before:
        where += " AND created_at<?"
        args.append(before)
    rows = c.execute(f"SELECT * FROM comments WHERE {where} ORDER BY created_at DESC LIMIT ?", [*args, limit])
    return [dict(r) for r in rows]


def add_message(c, mid, user_id, direction, text, created_at=None, sender: str = "") -> None:
    """sender فقط برای پیام بیرونی: bot (ربات) | admin (همکار، از پنل یا خود اپ اینستاگرام)."""
    created_at = created_at or time.time()
    c.execute(
        "INSERT OR IGNORE INTO messages(id,user_id,direction,text,created_at,sender) VALUES (?,?,?,?,?,?)",
        (mid, user_id, direction, text, created_at, sender),
    )
    incoming = direction == "in"
    c.execute(
        "INSERT INTO conversations(user_id,last_text,last_at,read,answered) VALUES (?,?,?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET last_text=excluded.last_text, last_at=excluded.last_at, "
        "read=CASE WHEN excluded.read=0 THEN 0 ELSE read END, answered=excluded.answered",
        (user_id, text, created_at, 0 if incoming else 1, 0 if incoming else 1),
    )


def set_conversation_username(c, user_id, username) -> None:
    c.execute("UPDATE conversations SET username=? WHERE user_id=?", (username, user_id))


def conversation_username(c, user_id) -> str | None:
    r = c.execute("SELECT username FROM conversations WHERE user_id=?", (user_id,)).fetchone()
    return r[0] if r else None


def mark_conversation(c, user_id, *, read=None, answered=None) -> None:
    if read is not None:
        c.execute("UPDATE conversations SET read=? WHERE user_id=?", (int(read), user_id))
    if answered is not None:
        c.execute("UPDATE conversations SET answered=? WHERE user_id=?", (int(answered), user_id))


def list_conversations(c, filt="all", limit=50) -> list[dict]:
    where = _FILTERS.get(filt, "1")
    rows = c.execute(f"SELECT * FROM conversations WHERE {where} ORDER BY last_at DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]


def list_messages(c, user_id, limit=100) -> list[dict]:
    rows = c.execute(
        "SELECT * FROM messages WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (user_id, limit)
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def all_rules(c) -> list[dict]:
    out = []
    for r in c.execute("SELECT * FROM rules ORDER BY priority, id"):
        d = dict(r)
        for k in ("channels", "post_scope", "triggers", "actions", "advanced"):
            d[k] = json.loads(d[k])
        out.append(d)
    return out


def delete_rule(c, rule_id) -> None:
    c.execute("DELETE FROM rules WHERE id=?", (rule_id,))


def set_rule_enabled(c, rule_id, enabled: bool) -> None:
    c.execute("UPDATE rules SET enabled=? WHERE id=?", (int(enabled), rule_id))


def recent_replies(c, limit=30) -> list[dict]:
    return [dict(r) for r in c.execute("SELECT * FROM replies ORDER BY created_at DESC LIMIT ?", (limit,))]


def stats(c) -> dict:
    day = time.time() - 86400
    q = lambda sql, *a: c.execute(sql, a).fetchone()[0]  # noqa: E731
    return {
        "replies_ok_24h": q("SELECT COUNT(*) FROM replies WHERE ok=1 AND created_at>?", day),
        "replies_failed_24h": q("SELECT COUNT(*) FROM replies WHERE ok=0 AND created_at>?", day),
        "comments_24h": q("SELECT COUNT(*) FROM comments WHERE created_at>?", day),
        "comments_unanswered": q("SELECT COUNT(*) FROM comments WHERE answered=0"),
        "conversations_unread": q("SELECT COUNT(*) FROM conversations WHERE read=0"),
        "conversations_unanswered": q("SELECT COUNT(*) FROM conversations WHERE answered=0"),
        "events_pending": q("SELECT COUNT(*) FROM events WHERE status='pending'"),
        "events_error": q("SELECT COUNT(*) FROM events WHERE status='error'"),
        "rules_enabled": q("SELECT COUNT(*) FROM rules WHERE enabled=1"),
        "token_expires_at": float(kv_get(c, "token_expires_at") or 0),
    }


# ---------- نشست و پوش ----------

def add_session(c, token, ttl) -> None:
    now = time.time()
    c.execute("INSERT INTO sessions(token,created_at,expires_at) VALUES (?,?,?)", (token, now, now + ttl))
    c.execute("DELETE FROM sessions WHERE expires_at<?", (now,))


def session_valid(c, token) -> bool:
    r = c.execute("SELECT expires_at FROM sessions WHERE token=?", (token,)).fetchone()
    return bool(r) and r[0] > time.time()


def delete_session(c, token) -> None:
    c.execute("DELETE FROM sessions WHERE token=?", (token,))


def add_push_sub(c, sub: dict) -> None:
    c.execute(
        "INSERT OR REPLACE INTO push_subs(endpoint,sub,created_at) VALUES (?,?,?)",
        (sub["endpoint"], json.dumps(sub), time.time()),
    )


def delete_push_sub(c, endpoint) -> None:
    c.execute("DELETE FROM push_subs WHERE endpoint=?", (endpoint,))


def push_subs(c) -> list[dict]:
    return [json.loads(r[0]) for r in c.execute("SELECT sub FROM push_subs")]


def kv_get(c: sqlite3.Connection, key: str) -> str | None:
    r = c.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return r[0] if r else None


def kv_set(c: sqlite3.Connection, key: str, value: str) -> None:
    c.execute(
        "INSERT INTO kv(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def is_first_message(c, user_id: str) -> bool:
    """اولین پیام ورودی این کاربر همین الان ثبت شده؟ (برای پیام خوش‌آمد)"""
    return c.execute("SELECT COUNT(*) FROM messages WHERE user_id=? AND direction='in'", (user_id,)).fetchone()[0] == 1


def set_human(c, user_id: str, minutes: float) -> None:
    """همکار جواب داد: ربات تا چند دقیقه برای این نفر ساکت می‌ماند (هر جواب تازه از نو می‌شمارد)."""
    if minutes <= 0:
        return
    c.execute("INSERT INTO human_mode(user_id, until) VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET until=excluded.until",
              (user_id, time.time() + minutes * 60))


def human_until(c, user_id: str) -> float:
    r = c.execute("SELECT until FROM human_mode WHERE user_id=?", (user_id,)).fetchone()
    return r[0] if r and r[0] > time.time() else 0.0


def clear_human(c, user_id: str) -> None:
    c.execute("DELETE FROM human_mode WHERE user_id=?", (user_id,))


def media_note(c, media_id: str | None) -> dict:
    if not media_id:
        return {}
    r = c.execute("SELECT * FROM media_notes WHERE media_id=?", (media_id,)).fetchone()
    return dict(r) if r else {}


def set_media_note(c, media_id: str, kind: str, note: str, product: str) -> None:
    c.execute("INSERT INTO media_notes(media_id,kind,note,product,updated_at) VALUES (?,?,?,?,?) "
              "ON CONFLICT(media_id) DO UPDATE SET kind=excluded.kind, note=excluded.note, product=excluded.product, "
              "updated_at=excluded.updated_at", (media_id, kind, note.strip()[:1000], product.strip()[:100], time.time()))
