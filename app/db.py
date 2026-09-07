"""SQLite metadata store. A single writer thread-safety model: FastAPI handlers
and the worker share one connection guarded by a lock, which is plenty for a
single-user/home-server workload."""

import json
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
    transcript_text TEXT,
    summary TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_recordings_device_session
    ON recordings(device_sn, session_id);
CREATE INDEX IF NOT EXISTS idx_recordings_status ON recordings(status);

CREATE TABLE IF NOT EXISTS vocabulary (
    id TEXT PRIMARY KEY,
    term TEXT UNIQUE NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL DEFAULT 'manual',
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS routes (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL,
    action_type TEXT NOT NULL CHECK (action_type IN ('webhook', 'markdown', 'none')),
    action_config TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS router_runs (
    id TEXT PRIMARY KEY,
    recording_id TEXT,
    created_at TEXT,
    model TEXT,
    decision TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_router_runs_recording ON router_runs(recording_id);
-- Browser sessions minted by approving a QR login from the phone. Only the
-- SHA-256 of the token is stored; revoking a row logs that computer out.
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    token_hash TEXT UNIQUE NOT NULL,
    label TEXT,
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    revoked_at TEXT
);
-- Short-lived QR login handshakes: the browser creates one and polls it, the
-- phone approves it, the browser collects the minted token exactly once.
CREATE TABLE IF NOT EXISTS login_requests (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    label TEXT,
    token TEXT,
    approved_at TEXT
);
CREATE TABLE IF NOT EXISTS deliveries (
    id TEXT PRIMARY KEY,
    recording_id TEXT,
    router_run_id TEXT,
    route_id TEXT,
    route_name TEXT,
    status TEXT,
    attempts INTEGER,
    last_error TEXT,
    action_type TEXT,
    action_config TEXT,
    payload TEXT,
    created_at TEXT
);
"""

# Created AFTER column migrations run — an index on a migrated column would
# otherwise fail against a database created before the column existed.
SCHEMA_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_deliveries_recording ON deliveries(recording_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_run ON deliveries(router_run_id);
"""

# Columns added after a table's initial release; applied idempotently at
# startup so existing databases upgrade in place.
MIGRATION_COLUMNS = {
    "recordings": {
        "transcript_text": "TEXT",
        "summary": "TEXT",
        "title": "TEXT",
        "marks": "TEXT",   # JSON list of button-press offsets in seconds
    },
    "vocabulary": {
        "weight": "INTEGER NOT NULL DEFAULT 0",
    },
    "deliveries": {
        "router_run_id": "TEXT",
        "action_type": "TEXT",
        "action_config": "TEXT",
    },
}


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            for table, columns in MIGRATION_COLUMNS.items():
                existing = {r[1] for r in self._conn.execute(f"PRAGMA table_info({table})")}
                for col, coltype in columns.items():
                    if col not in existing:
                        self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
            self._conn.executescript(SCHEMA_INDEXES)
            self._conn.commit()

    def insert_recording(self, **fields) -> str:
        return self._insert("recordings", fields)

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

    def list(
        self,
        limit: int = 100,
        offset: int = 0,
        status: str | None = None,
        query: str | None = None,
    ) -> "list[dict]":
        q = "SELECT * FROM recordings"
        where: list[str] = []
        args: list = []
        if status:
            where.append("status = ?")
            args.append(status)
        if query:
            where.append("(transcript_text LIKE ? OR summary LIKE ? OR filename LIKE ?)")
            like = f"%{query}%"
            args += [like, like, like]
        if where:
            q += " WHERE " + " AND ".join(where)
        q += " ORDER BY uploaded_at DESC LIMIT ? OFFSET ?"
        args += [limit, offset]
        with self._lock:
            rows = self._conn.execute(q, args).fetchall()
        return [dict(r) for r in rows]

    def delete(self, rec_id: str) -> None:
        # Cascade routing history: delivery payload snapshots contain the full
        # transcript, so they must not outlive the recording.
        with self._lock:
            self._conn.execute("DELETE FROM recordings WHERE id = ?", (rec_id,))
            self._conn.execute("DELETE FROM router_runs WHERE recording_id = ?", (rec_id,))
            self._conn.execute("DELETE FROM deliveries WHERE recording_id = ?", (rec_id,))
            self._conn.commit()

    def stats(self) -> dict:
        with self._lock:
            counts = dict(
                self._conn.execute("SELECT status, COUNT(*) FROM recordings GROUP BY status").fetchall()
            )
            totals = self._conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(size_bytes), 0), COALESCE(SUM(duration_s), 0) FROM recordings"
            ).fetchone()
        return {
            "recordings": totals[0],
            "total_bytes": totals[1],
            "total_duration_s": totals[2],
            "by_status": counts,
        }

    def next_pending(self, max_attempts: int) -> dict | None:
        # Fresh jobs (fewest attempts) first, so a failing recording does not
        # starve newer uploads while it burns through its retries.
        return self._one(
            "SELECT * FROM recordings WHERE status IN ('pending', 'failed') "
            "AND attempts < ? ORDER BY attempts ASC, uploaded_at ASC LIMIT 1",
            (max_attempts,),
        )

    def update(self, rec_id: str, **fields) -> None:
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self._lock:
            self._conn.execute(
                f"UPDATE recordings SET {sets} WHERE id = ?", [*fields.values(), rec_id]
            )
            self._conn.commit()

    def list_untitled_done(self) -> "list[dict]":
        """Finished recordings that have a summary but no title yet: the
        startup backfill derives one from the summary (see Transcriber)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, summary, transcript_path FROM recordings "
                "WHERE status = 'done' AND summary IS NOT NULL AND title IS NULL"
            ).fetchall()
        return [dict(r) for r in rows]

    # ── AI routing ────────────────────────────────────────────────────────

    # -- QR login: sessions + login requests ------------------------------------

    def insert_session(self, token_hash: str, label: str | None) -> str:
        return self._insert("sessions", {"token_hash": token_hash, "label": label,
                                         "created_at": utcnow_iso(), "last_used_at": utcnow_iso()})

    def session_by_hash(self, token_hash: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE token_hash = ? AND revoked_at IS NULL", (token_hash,)
            ).fetchone()
        return dict(row) if row else None

    def touch_session(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE sessions SET last_used_at = ? WHERE id = ?", (utcnow_iso(), session_id))
            self._conn.commit()

    def list_sessions(self) -> "list[dict]":
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, label, created_at, last_used_at FROM sessions WHERE revoked_at IS NULL ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def revoke_session(self, session_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL", (utcnow_iso(), session_id)
            )
            self._conn.commit()
            return cur.rowcount > 0

    def insert_login_request(self, req_id: str, expires_at: str, label: str | None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO login_requests (id, created_at, expires_at, status, label) VALUES (?, ?, ?, 'pending', ?)",
                (req_id, utcnow_iso(), expires_at, label),
            )
            self._conn.commit()

    def get_login_request(self, req_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM login_requests WHERE id = ?", (req_id,)).fetchone()
        return dict(row) if row else None

    def approve_login_request(self, req_id: str, token: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE login_requests SET status = 'approved', token = ?, approved_at = ? "
                "WHERE id = ? AND status = 'pending' AND expires_at > ?",
                (token, utcnow_iso(), req_id, utcnow_iso()),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def delete_login_request(self, req_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM login_requests WHERE id = ?", (req_id,))
            self._conn.commit()

    def purge_login_requests(self) -> int:
        """Drop expired handshakes; returns how many pending ones remain (rate cap)."""
        with self._lock:
            self._conn.execute("DELETE FROM login_requests WHERE expires_at <= ?", (utcnow_iso(),))
            n = self._conn.execute("SELECT COUNT(*) FROM login_requests WHERE status = 'pending'").fetchone()[0]
            self._conn.commit()
        return int(n)

    # -- custom vocabulary ---------------------------------------------------

    def list_vocabulary(self) -> "list[dict]":
        with self._lock:
            rows = self._conn.execute("SELECT term, aliases, source, weight FROM vocabulary ORDER BY term COLLATE NOCASE").fetchall()
        out = []
        for r in rows:
            try:
                aliases = json.loads(r["aliases"] or "[]")
            except ValueError:
                aliases = []
            out.append({"term": r["term"], "aliases": aliases, "source": r["source"], "weight": r["weight"] or 0})
        return out

    def replace_vocabulary(self, entries: "list[dict]") -> None:
        """Atomically replace the whole list (the editor saves the full text)."""
        now = utcnow_iso()
        with self._lock:
            self._conn.execute("DELETE FROM vocabulary")
            for e in entries:
                self._conn.execute(
                    "INSERT INTO vocabulary (id, term, aliases, source, weight, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (uuid.uuid4().hex, e["term"], json.dumps(e.get("aliases") or [], ensure_ascii=False),
                     e.get("source") or "manual", int(e.get("weight") or 0), now),
                )
            self._conn.commit()

    def insert_route(self, **fields) -> str:
        return self._insert("routes", fields)

    def get_route(self, route_id: str) -> dict | None:
        return self._one("SELECT * FROM routes WHERE id = ?", (route_id,))

    def get_route_by_name(self, name: str) -> dict | None:
        return self._one("SELECT * FROM routes WHERE name = ?", (name,))

    def list_routes(self, enabled_only: bool = False) -> "list[dict]":
        q = "SELECT * FROM routes"
        if enabled_only:
            q += " WHERE enabled = 1"
        q += " ORDER BY created_at ASC, name ASC"
        with self._lock:
            rows = self._conn.execute(q).fetchall()
        return [dict(r) for r in rows]

    def update_route(self, route_id: str, **fields) -> None:
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self._lock:
            self._conn.execute(
                f"UPDATE routes SET {sets} WHERE id = ?", [*fields.values(), route_id]
            )
            self._conn.commit()

    def delete_route(self, route_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM routes WHERE id = ?", (route_id,))
            self._conn.commit()

    def insert_router_run(self, **fields) -> str:
        return self._insert("router_runs", fields)

    def get_router_run(self, run_id: str) -> dict | None:
        return self._one("SELECT * FROM router_runs WHERE id = ?", (run_id,))

    def list_router_runs(self, limit: int = 50) -> "list[dict]":
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM router_runs ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def router_runs_for_recording(self, recording_id: str) -> "list[dict]":
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM router_runs WHERE recording_id = ? "
                "ORDER BY created_at DESC, rowid DESC",
                (recording_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def insert_delivery(self, **fields) -> str:
        return self._insert("deliveries", fields)

    def get_delivery(self, delivery_id: str) -> dict | None:
        return self._one("SELECT * FROM deliveries WHERE id = ?", (delivery_id,))

    def update_delivery(self, delivery_id: str, **fields) -> None:
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self._lock:
            self._conn.execute(
                f"UPDATE deliveries SET {sets} WHERE id = ?", [*fields.values(), delivery_id]
            )
            self._conn.commit()

    def claim_delivery_retry(self, delivery_id: str) -> bool:
        """Atomically move a failed delivery to 'pending' (incrementing its
        attempt count) so concurrent retries cannot double-execute. Returns
        False when the delivery is not currently 'failed'."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE deliveries SET status = 'pending', attempts = attempts + 1 "
                "WHERE id = ? AND status = 'failed'",
                (delivery_id,),
            )
            self._conn.commit()
        return cur.rowcount == 1

    def deliveries_for_run(self, run_id: str) -> "list[dict]":
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM deliveries WHERE router_run_id = ? "
                "ORDER BY created_at DESC, rowid DESC",
                (run_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def deliveries_for_recording(self, recording_id: str) -> "list[dict]":
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM deliveries WHERE recording_id = ? "
                "ORDER BY created_at DESC, rowid DESC",
                (recording_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def _insert(self, table: str, fields: dict) -> str:
        row_id = fields.pop("id", None) or uuid.uuid4().hex
        fields["id"] = row_id
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        with self._lock:
            self._conn.execute(
                f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(fields.values())
            )
            self._conn.commit()
        return row_id

    def _one(self, q: str, args: tuple) -> dict | None:
        with self._lock:
            row = self._conn.execute(q, args).fetchone()
        return dict(row) if row else None


def utcnow_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
