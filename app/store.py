"""SQLite storage for incoming comments/DMs, their drafts, and a small key-value table."""

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kind          TEXT NOT NULL,              -- 'comment' | 'dm'
    ext_id        TEXT NOT NULL UNIQUE,       -- comment id or message mid
    sender_id     TEXT NOT NULL,
    username      TEXT NOT NULL DEFAULT '',
    text          TEXT NOT NULL DEFAULT '',
    media_id      TEXT NOT NULL DEFAULT '',
    media_caption TEXT NOT NULL DEFAULT '',
    received_at   REAL NOT NULL,
    status        TEXT NOT NULL DEFAULT 'new', -- new | pending | sent | skipped | hidden | failed
    category      TEXT NOT NULL DEFAULT '',
    draft         TEXT NOT NULL DEFAULT '',
    note          TEXT NOT NULL DEFAULT '',
    tg_message_id INTEGER,
    error         TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS dm_history (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    peer_id TEXT NOT NULL,
    role    TEXT NOT NULL,                    -- 'them' | 'me'
    text    TEXT NOT NULL,
    ts      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS dm_history_peer ON dm_history (peer_id, id);
CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass
class Item:
    id: int
    kind: str
    ext_id: str
    sender_id: str
    username: str
    text: str
    media_id: str
    media_caption: str
    received_at: float
    status: str
    category: str
    draft: str
    note: str
    tg_message_id: int | None
    error: str


class Store:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._db.execute(sql, params)
            self._db.commit()
            return cur

    # items
    def add_item(self, *, kind: str, ext_id: str, sender_id: str, username: str = "", text: str = "",
                 media_id: str = "", received_at: float | None = None) -> Item | None:
        """Insert a new item. Returns None if this ext_id was already seen (webhook retries)."""
        cur = self._exec(
            "INSERT OR IGNORE INTO items (kind, ext_id, sender_id, username, text, media_id, received_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (kind, ext_id, sender_id, username, text, media_id, received_at or time.time()),
        )
        if cur.rowcount == 0:
            return None
        return self.get_item(cur.lastrowid)

    def get_item(self, item_id: int) -> Item | None:
        row = self._exec("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        return Item(**dict(row)) if row else None

    def update_item(self, item_id: int, **fields) -> None:
        cols = ", ".join(f"{k} = ?" for k in fields)
        self._exec(f"UPDATE items SET {cols} WHERE id = ?", (*fields.values(), item_id))

    # DM history
    def add_dm(self, peer_id: str, role: str, text: str, ts: float | None = None) -> None:
        self._exec("INSERT INTO dm_history (peer_id, role, text, ts) VALUES (?, ?, ?, ?)",
                   (peer_id, role, text, ts or time.time()))

    def dm_history(self, peer_id: str, limit: int = 10) -> list[tuple[str, str]]:
        rows = self._exec(
            "SELECT role, text FROM dm_history WHERE peer_id = ? ORDER BY id DESC LIMIT ?",
            (peer_id, limit),
        ).fetchall()
        return [(r["role"], r["text"]) for r in reversed(rows)]

    # key-value
    def get(self, key: str, default: str | None = None) -> str | None:
        row = self._exec("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set(self, key: str, value: str) -> None:
        self._exec("INSERT INTO kv (key, value) VALUES (?, ?) "
                   "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    def delete(self, key: str) -> None:
        self._exec("DELETE FROM kv WHERE key = ?", (key,))
