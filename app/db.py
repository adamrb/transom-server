"""SQLite metadata store. A single writer thread-safety model: FastAPI handlers
and the worker share one connection guarded by a lock, which is plenty for a
single-user/home-server workload."""

import sqlite3
import threading
import time
import uuid
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS recordings (
    id TEXT PRIMARY KEY,
    device_sn TEXT,
    session_id INTEGER,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    size_bytes INTEGER NOT NULL,
    duration_s REAL,
    started_at TEXT,
    source TEXT,
    uploaded_at TEXT NOT NULL,
    audio_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    transcript_path TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_recordings_device_session
    ON recordings(device_sn, session_id);
CREATE INDEX IF NOT EXISTS idx_recordings_status ON recordings(status);
"""

COLUMNS = [
    "id", "device_sn", "session_id", "filename", "sha256", "size_bytes",
    "duration_s", "started_at", "source", "uploaded_at", "audio_path",
    "status", "attempts", "transcript_path", "error",
]


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def insert_recording(self, **fields) -> str:
        rec_id = fields.pop("id", None) or uuid.uuid4().hex
        fields["id"] = rec_id
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        with self._lock:
            self._conn.execute(
                f"INSERT INTO recordings ({cols}) VALUES ({marks})", list(fields.values())
            )
            self._conn.commit()
        return rec_id

    def find_by_sha256(self, sha256: str) -> dict | None:
        return self._one("SELECT * FROM recordings WHERE sha256 = ?", (sha256,))

    def find_by_session(self, device_sn: str, session_id: int) -> dict | None:
        return self._one(
            "SELECT * FROM recordings WHERE device_sn = ? AND session_id = ? "
            "ORDER BY uploaded_at DESC LIMIT 1",
            (device_sn, session_id),
        )

    def get(self, rec_id: str) -> dict | None:
        return self._one("SELECT * FROM recordings WHERE id = ?", (rec_id,))

    def list(self, limit: int = 100, offset: int = 0, status: str | None = None) -> list[dict]:
        q = "SELECT * FROM recordings"
        args: list = []
        if status:
            q += " WHERE status = ?"
            args.append(status)
        q += " ORDER BY uploaded_at DESC LIMIT ? OFFSET ?"
        args += [limit, offset]
        with self._lock:
            rows = self._conn.execute(q, args).fetchall()
        return [dict(r) for r in rows]

    def next_pending(self, max_attempts: int) -> dict | None:
        return self._one(
            "SELECT * FROM recordings WHERE status IN ('pending', 'failed') "
            "AND attempts < ? ORDER BY uploaded_at ASC LIMIT 1",
            (max_attempts,),
        )

    def update(self, rec_id: str, **fields) -> None:
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self._lock:
            self._conn.execute(
                f"UPDATE recordings SET {sets} WHERE id = ?", [*fields.values(), rec_id]
            )
            self._conn.commit()

    def _one(self, q: str, args: tuple) -> dict | None:
        with self._lock:
            row = self._conn.execute(q, args).fetchone()
        return dict(row) if row else None


def utcnow_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
