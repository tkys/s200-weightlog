"""SQLite storage: weigh-ins (with outlier status), day notes, settings."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from s200 import analysis
from s200.mibeacon import Reading

STATUSES = ("ok", "outlier", "merged")

# Each entry migrates user_version i -> i + 1.
MIGRATIONS = [
    """
    CREATE TABLE IF NOT EXISTS readings (
        id          INTEGER PRIMARY KEY,
        ts          INTEGER NOT NULL,
        profile_id  INTEGER NOT NULL,
        weight_kg   REAL    NOT NULL,
        received_at INTEGER NOT NULL,
        UNIQUE (ts, profile_id)
    );
    """,
    """
    ALTER TABLE readings ADD COLUMN status TEXT NOT NULL DEFAULT 'ok';
    ALTER TABLE readings ADD COLUMN reason TEXT;
    ALTER TABLE readings ADD COLUMN manual INTEGER NOT NULL DEFAULT 0;
    CREATE TABLE day_notes (
        date TEXT PRIMARY KEY,
        note TEXT NOT NULL DEFAULT '',
        tags TEXT NOT NULL DEFAULT '[]'
    );
    CREATE TABLE settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
]

SETTING_KEYS = ("height_cm", "goal_kg", "start_kg")
COLUMNS = "id, ts, profile_id, weight_kg, status, reason, manual"


class Store:
    def __init__(self, path: str | Path):
        # The scanner callback and the HTTP server threads share this connection.
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self._migrate()

    def _migrate(self) -> None:
        with self.lock:
            version = self.conn.execute("PRAGMA user_version").fetchone()[0]
            if version == 0 and self._has_table("readings"):
                version = 1  # v1 databases predate user_version
            for i in range(version, len(MIGRATIONS)):
                self.conn.executescript(
                    f"BEGIN; {MIGRATIONS[i]} PRAGMA user_version = {i + 1}; COMMIT;"
                )

    def _has_table(self, name: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        return row is not None

    # --- readings ----------------------------------------------------------

    def add(self, reading: Reading) -> bool:
        """Insert a reading as-is. Returns False if it was already stored.

        The scale re-broadcasts the same weigh-in many times, so (ts, profile_id)
        is the dedupe key.
        """
        return self.ingest(reading, classify=False) is not None

    def ingest(self, reading: Reading, classify: bool = True) -> dict | None:
        """Store a new weigh-in and classify it. None if it was a duplicate.

        Classification: an outlier vs. the user's trend is kept but excluded;
        otherwise earlier ok weigh-ins within the merge window become "merged".
        """
        with self.lock, self.conn:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO readings (ts, profile_id, weight_kg, received_at)"
                " VALUES (?, ?, ?, ?)",
                (reading.timestamp, reading.profile_id, reading.weight_kg, int(time.time())),
            )
            if cur.rowcount != 1:
                return None
            new_id = cur.lastrowid
            if classify:
                rows = self.list(profile_id=reading.profile_id)
                history = [
                    (r["ts"], r["weight_kg"])
                    for r in rows
                    if r["status"] == "ok" and r["id"] != new_id
                ]
                reason = analysis.detect_outlier(history, reading.timestamp, reading.weight_kg)
                if reason:
                    self._set_status(new_id, "outlier", reason, manual=False)
                else:
                    for rid in analysis.merge_targets(rows, reading.timestamp):
                        self._set_status(rid, "merged", "直後に測り直したため統合", manual=False)
            return self.get(new_id)

    def get(self, reading_id: int) -> dict | None:
        row = self.conn.execute(
            f"SELECT {COLUMNS} FROM readings WHERE id = ?", (reading_id,)
        ).fetchone()
        return _row(row) if row else None

    def list(
        self, profile_id: int | None = None, since: int | None = None, only_ok: bool = False
    ) -> list[dict]:
        sql = f"SELECT {COLUMNS} FROM readings WHERE 1=1"
        args: list = []
        if profile_id is not None:
            sql += " AND profile_id = ?"
            args.append(profile_id)
        if since is not None:
            sql += " AND ts >= ?"
            args.append(since)
        if only_ok:
            sql += " AND status = 'ok'"
        sql += " ORDER BY ts"
        with self.lock:
            return [_row(r) for r in self.conn.execute(sql, args)]

    def set_status(self, reading_id: int, status: str) -> dict | None:
        """User override: include or exclude a reading. Auto-classification won't touch it again."""
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        with self.lock, self.conn:
            reason = "手動で除外" if status != "ok" else None
            self._set_status(reading_id, status, reason, manual=True)
            return self.get(reading_id)

    def _set_status(self, reading_id: int, status: str, reason: str | None, manual: bool) -> None:
        self.conn.execute(
            "UPDATE readings SET status = ?, reason = ?, manual = ? WHERE id = ?",
            (status, reason, int(manual), reading_id),
        )

    # --- day notes ---------------------------------------------------------

    def get_note(self, day: str) -> dict:
        with self.lock:
            row = self.conn.execute(
                "SELECT date, note, tags FROM day_notes WHERE date = ?", (day,)
            ).fetchone()
        return _note(row) if row else {"date": day, "note": "", "tags": []}

    def list_notes(self, start: str | None = None, end: str | None = None) -> list[dict]:
        sql = "SELECT date, note, tags FROM day_notes WHERE 1=1"
        args: list = []
        if start:
            sql += " AND date >= ?"
            args.append(start)
        if end:
            sql += " AND date <= ?"
            args.append(end)
        with self.lock:
            return [_note(r) for r in self.conn.execute(sql + " ORDER BY date", args)]

    def put_note(self, day: str, note: str, tags: list[str]) -> dict:
        tags = [t.strip() for t in tags if t.strip()]
        with self.lock, self.conn:
            if not note.strip() and not tags:
                self.conn.execute("DELETE FROM day_notes WHERE date = ?", (day,))
            else:
                self.conn.execute(
                    "INSERT INTO day_notes (date, note, tags) VALUES (?, ?, ?)"
                    " ON CONFLICT(date) DO UPDATE SET note = excluded.note, tags = excluded.tags",
                    (day, note, json.dumps(tags, ensure_ascii=False)),
                )
        return self.get_note(day)

    # --- settings ----------------------------------------------------------

    def get_settings(self, defaults: dict | None = None) -> dict:
        out = {k: (defaults or {}).get(k) for k in SETTING_KEYS}
        with self.lock:
            for row in self.conn.execute("SELECT key, value FROM settings"):
                if row["key"] in SETTING_KEYS:
                    out[row["key"]] = json.loads(row["value"])
        return out

    def put_settings(self, values: dict) -> None:
        with self.lock, self.conn:
            for key, value in values.items():
                if key not in SETTING_KEYS:
                    raise ValueError(f"unknown setting: {key}")
                if value is not None and not isinstance(value, int | float):
                    raise ValueError(f"{key} must be a number or null")
                self.conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?)"
                    " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, json.dumps(value)),
                )

    def snapshot(self, path: str | Path) -> None:
        """Write a consistent copy of the database to `path` (for backups)."""
        dest = sqlite3.connect(str(path))
        try:
            with self.lock:
                self.conn.backup(dest)
        finally:
            dest.close()

    def close(self) -> None:
        self.conn.close()


def _row(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["manual"] = bool(d["manual"])
    return d


def _note(row: sqlite3.Row) -> dict:
    return {"date": row["date"], "note": row["note"], "tags": json.loads(row["tags"])}
