"""SQLite storage for weigh-ins."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from s200.mibeacon import Reading

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id          INTEGER PRIMARY KEY,
    ts          INTEGER NOT NULL,
    profile_id  INTEGER NOT NULL,
    weight_kg   REAL    NOT NULL,
    received_at INTEGER NOT NULL,
    UNIQUE (ts, profile_id)
);
"""


class Store:
    def __init__(self, path: str | Path):
        # The scanner callback and the HTTP server run on different threads.
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def add(self, reading: Reading) -> bool:
        """Insert a reading. Returns False if it was already stored.

        The scale re-broadcasts the same weigh-in many times, so (ts, profile_id)
        is the dedupe key.
        """
        with self.conn:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO readings (ts, profile_id, weight_kg, received_at)"
                " VALUES (?, ?, ?, ?)",
                (reading.timestamp, reading.profile_id, reading.weight_kg, int(time.time())),
            )
        return cur.rowcount == 1

    def list(self, profile_id: int | None = None, since: int | None = None) -> list[dict]:
        sql = "SELECT ts, profile_id, weight_kg FROM readings WHERE 1=1"
        args: list[int] = []
        if profile_id is not None:
            sql += " AND profile_id = ?"
            args.append(profile_id)
        if since is not None:
            sql += " AND ts >= ?"
            args.append(since)
        sql += " ORDER BY ts"
        return [dict(row) for row in self.conn.execute(sql, args)]

    def close(self) -> None:
        self.conn.close()
