from __future__ import annotations
import json, re, sqlite3, threading
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS items(
  id TEXT PRIMARY KEY, origin TEXT NOT NULL, seq INTEGER NOT NULL, lamport INTEGER NOT NULL,
  created REAL NOT NULL, kind TEXT NOT NULL, mime TEXT NOT NULL, size INTEGER NOT NULL,
  sha256 TEXT NOT NULL, text TEXT, pinned INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL, direction TEXT NOT NULL, peer TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(text, content='items', content_rowid='rowid');
CREATE TRIGGER IF NOT EXISTS items_ai AFTER INSERT ON items BEGIN
  INSERT INTO items_fts(rowid, text) VALUES (new.rowid, new.text); END;
CREATE TRIGGER IF NOT EXISTS items_ad AFTER DELETE ON items BEGIN
  INSERT INTO items_fts(items_fts, rowid, text) VALUES('delete', old.rowid, old.text); END;
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS outbox(item_id TEXT, peer TEXT, PRIMARY KEY(item_id, peer));
"""
FIELDS = ("id", "origin", "seq", "lamport", "created", "kind", "mime", "size", "sha256", "text")


class History:
    def __init__(self, path: Path | str) -> None:
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.executescript(SCHEMA)

    # --- items
    def add(self, item: dict[str, Any], direction: str, status: str, peer: str | None = None) -> bool:
        with self.lock:
            cur = self.db.execute(
                "INSERT OR IGNORE INTO items(id,origin,seq,lamport,created,kind,mime,size,sha256,text,status,direction,peer)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (*[item[f] for f in FIELDS], status, direction, peer))
            self.db.commit()
            return cur.rowcount == 1

    def has(self, item_id: str) -> bool:
        with self.lock:
            return self.db.execute("SELECT 1 FROM items WHERE id=?", (item_id,)).fetchone() is not None

    def get(self, item_id: str) -> dict[str, Any] | None:
        with self.lock:
            r = self.db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
            return dict(r) if r else None

    def set_status(self, item_id: str, status: str) -> None:
        with self.lock:
            self.db.execute("UPDATE items SET status=? WHERE id=?", (status, item_id))
            self.db.commit()

    def search(self, q: str = "", limit: int = 200) -> list[dict[str, Any]]:
        toks = re.findall(r"\w+", q)
        with self.lock:
            if toks:
                match = " ".join(f'"{t}"*' for t in toks)
                rows = self.db.execute(
                    "SELECT i.* FROM items i JOIN items_fts f ON f.rowid=i.rowid WHERE items_fts MATCH ?"
                    " ORDER BY i.pinned DESC, i.created DESC LIMIT ?", (match, limit)).fetchall()
            else:
                rows = self.db.execute("SELECT * FROM items ORDER BY pinned DESC, created DESC LIMIT ?",
                                       (limit,)).fetchall()
            return [dict(r) for r in rows]

    def set_pinned(self, item_id: str, pinned: bool) -> None:
        with self.lock:
            self.db.execute("UPDATE items SET pinned=? WHERE id=?", (int(pinned), item_id))
            self.db.commit()

    def delete(self, item_id: str) -> None:
        with self.lock:
            self.db.execute("DELETE FROM items WHERE id=?", (item_id,))
            self.db.execute("DELETE FROM outbox WHERE item_id=?", (item_id,))
            self.db.commit()

    def clear(self) -> None:
        with self.lock:
            self.db.execute("DELETE FROM items WHERE pinned=0")
            self.db.execute("DELETE FROM outbox WHERE item_id NOT IN (SELECT id FROM items)")
            self.db.commit()

    def prune(self, keep: int) -> None:
        with self.lock:
            self.db.execute("DELETE FROM items WHERE pinned=0 AND id NOT IN "
                            "(SELECT id FROM items ORDER BY created DESC LIMIT ?)", (keep,))
            self.db.execute("DELETE FROM outbox WHERE item_id NOT IN (SELECT id FROM items)")
            self.db.commit()

    # --- kv state
    def kv(self, k: str, default: Any = None) -> Any:
        with self.lock:
            r = self.db.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
            return json.loads(r["v"]) if r else default

    def kv_set(self, k: str, v: Any) -> None:
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (k, json.dumps(v)))
            self.db.commit()

    # --- durable outbox
    def outbox_add(self, item_id: str, peer: str) -> None:
        with self.lock:
            self.db.execute("INSERT OR IGNORE INTO outbox VALUES(?,?)", (item_id, peer))
            self.db.commit()

    def outbox_remove(self, item_id: str, peer: str) -> None:
        with self.lock:
            self.db.execute("DELETE FROM outbox WHERE item_id=? AND peer=?", (item_id, peer))
            self.db.commit()

    def outbox_items(self, peer: str) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.db.execute("SELECT i.* FROM outbox o JOIN items i ON i.id=o.item_id WHERE o.peer=?",
                                   (peer,)).fetchall()
            return [dict(r) for r in rows]
