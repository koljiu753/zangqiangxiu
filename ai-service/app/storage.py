import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    backend = "sqlite"
    def __init__(self, db_path: Path):
        self.db_path = db_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY, sha256 TEXT NOT NULL UNIQUE, filename TEXT NOT NULL,
                    content_type TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
                    byte_size INTEGER NOT NULL, storage_path TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL, asset_id TEXT,
                    requested_tasks TEXT NOT NULL, parameters TEXT NOT NULL, progress INTEGER NOT NULL,
                    result_id TEXT, error_code TEXT, error_message TEXT, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL, FOREIGN KEY(asset_id) REFERENCES assets(id)
                );
                CREATE TABLE IF NOT EXISTS analysis_results (
                    id TEXT PRIMARY KEY, job_id TEXT NOT NULL UNIQUE, asset_id TEXT NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id), FOREIGN KEY(asset_id) REFERENCES assets(id)
                );
                CREATE TABLE IF NOT EXISTS reference_assets (
                    asset_id TEXT PRIMARY KEY, label TEXT, algorithm_version TEXT NOT NULL,
                    feature TEXT NOT NULL, created_at TEXT NOT NULL, pattern_id TEXT,
                    review_status TEXT NOT NULL DEFAULT 'draft',
                    visibility TEXT NOT NULL DEFAULT 'internal_only',
                    FOREIGN KEY(asset_id) REFERENCES assets(id)
                );
                CREATE TABLE IF NOT EXISTS asset_capabilities (
                    token_hash TEXT PRIMARY KEY, asset_id TEXT NOT NULL, created_at TEXT NOT NULL,
                    FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_asset_capabilities_asset ON asset_capabilities(asset_id);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(reference_assets)")}
            for name, declaration in (
                ("pattern_id", "TEXT"),
                ("review_status", "TEXT NOT NULL DEFAULT 'draft'"),
                ("visibility", "TEXT NOT NULL DEFAULT 'internal_only'"),
            ):
                if name not in columns:
                    db.execute(f"ALTER TABLE reference_assets ADD COLUMN {name} {declaration}")

    def check(self) -> None:
        if self.one("SELECT 1 AS ok") != {"ok": 1}:
            raise RuntimeError("database readiness probe failed")

    def one(self, sql: str, parameters: tuple = ()) -> dict | None:
        with self.connect() as db:
            row = db.execute(sql, parameters).fetchone()
        return dict(row) if row else None

    def execute(self, sql: str, parameters: tuple = ()) -> None:
        with self.connect() as db:
            db.execute(sql, parameters)

    def execute_count(self, sql: str, parameters: tuple = ()) -> int:
        """Execute a mutation and return affected rows for atomic job claiming."""
        with self.connect() as db:
            cursor = db.execute(sql, parameters)
            return cursor.rowcount

    def all(self, sql: str, parameters: tuple = ()) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(sql, parameters).fetchall()
        return [dict(row) for row in rows]

    def delete_asset_cascade(self, asset_id: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM analysis_results WHERE asset_id=?", (asset_id,))
            db.execute("DELETE FROM jobs WHERE asset_id=?", (asset_id,))
            db.execute("DELETE FROM asset_capabilities WHERE asset_id=?", (asset_id,))
            db.execute("DELETE FROM reference_assets WHERE asset_id=?", (asset_id,))
            db.execute("DELETE FROM assets WHERE id=?", (asset_id,))


POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
 id TEXT PRIMARY KEY, sha256 TEXT NOT NULL UNIQUE, filename TEXT NOT NULL,
 content_type TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
 byte_size INTEGER NOT NULL, storage_path TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL, asset_id TEXT REFERENCES assets(id),
 requested_tasks TEXT NOT NULL, parameters TEXT NOT NULL, progress INTEGER NOT NULL,
 result_id TEXT, error_code TEXT, error_message TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS analysis_results (
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id),
 asset_id TEXT NOT NULL REFERENCES assets(id), payload TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reference_assets (
 asset_id TEXT PRIMARY KEY REFERENCES assets(id), label TEXT, algorithm_version TEXT NOT NULL,
 feature TEXT NOT NULL, created_at TEXT NOT NULL, pattern_id TEXT,
 review_status TEXT NOT NULL DEFAULT 'draft', visibility TEXT NOT NULL DEFAULT 'internal_only');
CREATE TABLE IF NOT EXISTS asset_capabilities (
 token_hash TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
 created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_asset_capabilities_asset ON asset_capabilities(asset_id);
"""


class PostgreSQLStorage:
    backend = "postgresql"

    def __init__(self, database_url: str):
        if not database_url:
            raise RuntimeError("PostgreSQL database URL is required")
        self.database_url = database_url

    @contextmanager
    def connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("Install psycopg[binary] to use PostgreSQL") from exc
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                yield cursor
            connection.commit()

    @staticmethod
    def _sql(sql: str) -> str:
        return sql.replace("?", "%s")

    def initialize(self) -> None:
        with self.connect() as db:
            db.execute(POSTGRES_SCHEMA)
            # Idempotently upgrades databases created by the earlier prototype.
            db.execute("ALTER TABLE reference_assets ADD COLUMN IF NOT EXISTS pattern_id TEXT")
            db.execute("ALTER TABLE reference_assets ADD COLUMN IF NOT EXISTS review_status TEXT NOT NULL DEFAULT 'draft'")
            db.execute("ALTER TABLE reference_assets ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'internal_only'")

    def check(self) -> None:
        if self.one("SELECT 1 AS ok") != {"ok": 1}:
            raise RuntimeError("database readiness probe failed")

    def one(self, sql: str, parameters: tuple = ()) -> dict | None:
        with self.connect() as db:
            db.execute(self._sql(sql), parameters)
            row = db.fetchone()
        return dict(row) if row else None

    def execute(self, sql: str, parameters: tuple = ()) -> None:
        with self.connect() as db:
            db.execute(self._sql(sql), parameters)

    def execute_count(self, sql: str, parameters: tuple = ()) -> int:
        """Execute a mutation and return affected rows for atomic job claiming."""
        with self.connect() as db:
            cursor = db.execute(self._sql(sql), parameters)
            return cursor.rowcount

    def all(self, sql: str, parameters: tuple = ()) -> list[dict]:
        with self.connect() as db:
            db.execute(self._sql(sql), parameters)
            rows = db.fetchall()
        return [dict(row) for row in rows]

    def delete_asset_cascade(self, asset_id: str) -> None:
        with self.connect() as db:
            for sql in ("DELETE FROM analysis_results WHERE asset_id=?", "DELETE FROM jobs WHERE asset_id=?",
                        "DELETE FROM asset_capabilities WHERE asset_id=?", "DELETE FROM reference_assets WHERE asset_id=?",
                        "DELETE FROM assets WHERE id=?"):
                db.execute(self._sql(sql), (asset_id,))


def create_storage(backend: str, sqlite_path: Path, database_url: str | None = None):
    if backend == "sqlite":
        return Storage(sqlite_path)
    if backend == "postgresql":
        return PostgreSQLStorage(database_url or "")
    raise RuntimeError(f"Unsupported database backend: {backend}")


def decode_job(row: dict) -> dict:
    value = dict(row)
    value["requested_tasks"] = json.loads(value["requested_tasks"])
    return value
