"""SQLite-backed job store."""
import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "jobs.db"

class JobDB:
    def __init__(self):
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                config TEXT,
                status TEXT DEFAULT 'pending',
                created_at REAL,
                updated_at REAL
            );
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                line TEXT,
                ts REAL
            );
        """)
        self._conn.commit()

    def create_job(self, job_id: str, config: dict) -> dict:
        now = time.time()
        self._conn.execute(
            "INSERT INTO jobs VALUES (?,?,?,?,?)",
            (job_id, json.dumps(config), "pending", now, now)
        )
        self._conn.commit()
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> Optional[dict]:
        row = self._conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["config"] = json.loads(d["config"])
        return d

    def list_jobs(self) -> list:
        rows = self._conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["config"] = json.loads(d["config"])
            result.append(d)
        return result

    def update_status(self, job_id: str, status: str):
        self._conn.execute(
            "UPDATE jobs SET status=?, updated_at=? WHERE id=?",
            (status, time.time(), job_id)
        )
        self._conn.commit()

    def append_log(self, job_id: str, line: str):
        self._conn.execute(
            "INSERT INTO logs (job_id, line, ts) VALUES (?,?,?)",
            (job_id, line, time.time())
        )
        self._conn.commit()

    def get_logs(self, job_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT line FROM logs WHERE job_id=? ORDER BY id",
            (job_id,)
        ).fetchall()
        return [r["line"] for r in rows]
