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
  rule_id INTEGER NOT NULL,
  user_id TEXT NOT NULL,
  text TEXT NOT NULL,
  due_at REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',  -- pending | done | error
  error TEXT
);
CREATE INDEX IF NOT EXISTS followups_due ON followups(status, due_at);

CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def init(path: str | None = None) -> None:
    p = Path(path or config.DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    with connect(str(p)) as c:
        c.executescript(SCHEMA)


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


def kv_get(c: sqlite3.Connection, key: str) -> str | None:
    r = c.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return r[0] if r else None


def kv_set(c: sqlite3.Connection, key: str, value: str) -> None:
    c.execute(
        "INSERT INTO kv(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
