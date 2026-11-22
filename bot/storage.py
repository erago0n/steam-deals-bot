"""Tiny SQLite store: posted deals (de-duplication) and a key/value cache."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path


class PostedDeals:
    def __init__(self, path: str | Path = "data/deals.db") -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS posted (key TEXT PRIMARY KEY, posted_at INTEGER NOT NULL)"
        )
        self._db.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self._db.commit()

    # --- posted deals ---
    def is_posted(self, key: str) -> bool:
        row = self._db.execute("SELECT 1 FROM posted WHERE key = ?", (key,)).fetchone()
        return row is not None

    def mark_posted(self, key: str) -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO posted (key, posted_at) VALUES (?, ?)", (key, int(time.time()))
        )
        self._db.commit()

    def forget_older_than(self, days: int = 30) -> int:
        """Drop old rows so a game can be posted again in a future sale."""
        cutoff = int(time.time()) - days * 86400
        cur = self._db.execute("DELETE FROM posted WHERE posted_at < ?", (cutoff,))
        self._db.commit()
        return cur.rowcount

    # --- cache (e.g. Steam app id -> CheapShark game id) ---
    def get(self, key: str) -> str | None:
        row = self._db.execute("SELECT value FROM cache WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set(self, key: str, value: str) -> None:
        self._db.execute("INSERT OR REPLACE INTO cache (key, value) VALUES (?, ?)", (key, value))
        self._db.commit()

    def close(self) -> None:
        self._db.close()
