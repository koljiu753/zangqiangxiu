import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from .config import Settings

SQLITE_SCHEMA = """CREATE TABLE IF NOT EXISTS patterns (id TEXT PRIMARY KEY,name TEXT NOT NULL,category TEXT NOT NULL DEFAULT '',ethnicity TEXT NOT NULL DEFAULT 'unknown',meaning TEXT NOT NULL DEFAULT '',colors_json TEXT NOT NULL DEFAULT '[]',image_url TEXT,status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','archived')),visibility TEXT NOT NULL DEFAULT 'internal_only' CHECK(visibility IN ('internal_only','public')),source_json TEXT NOT NULL DEFAULT '{}',rights_json TEXT NOT NULL DEFAULT '{}',review_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP); CREATE INDEX IF NOT EXISTS idx_patterns_public ON patterns(status,visibility); CREATE INDEX IF NOT EXISTS idx_patterns_category ON patterns(category); CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT,pattern_id TEXT NOT NULL,action TEXT NOT NULL,actor TEXT NOT NULL,before_json TEXT,after_json TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP); CREATE INDEX IF NOT EXISTS idx_audit_pattern ON audit_logs(pattern_id,created_at DESC); CREATE INDEX IF NOT EXISTS idx_audit_actor_created ON audit_logs(actor,created_at DESC); CREATE INDEX IF NOT EXISTS idx_audit_action_created ON audit_logs(action,created_at DESC); CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at DESC);"""
POSTGRES_SCHEMA = """CREATE TABLE IF NOT EXISTS patterns (id TEXT PRIMARY KEY,name TEXT NOT NULL,category TEXT NOT NULL DEFAULT '',ethnicity TEXT NOT NULL DEFAULT 'unknown',meaning TEXT NOT NULL DEFAULT '',colors_json JSONB NOT NULL DEFAULT '[]'::jsonb,image_url TEXT,status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','archived')),visibility TEXT NOT NULL DEFAULT 'internal_only' CHECK(visibility IN ('internal_only','public')),source_json JSONB NOT NULL DEFAULT '{}'::jsonb,rights_json JSONB NOT NULL DEFAULT '{}'::jsonb,review_json JSONB NOT NULL DEFAULT '{}'::jsonb,created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP); CREATE INDEX IF NOT EXISTS idx_patterns_public ON patterns(status,visibility); CREATE INDEX IF NOT EXISTS idx_patterns_category ON patterns(category); CREATE TABLE IF NOT EXISTS audit_logs (id BIGSERIAL PRIMARY KEY,pattern_id TEXT NOT NULL,action TEXT NOT NULL,actor TEXT NOT NULL,before_json JSONB,after_json JSONB,created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP); CREATE INDEX IF NOT EXISTS idx_audit_pattern ON audit_logs(pattern_id,created_at DESC); CREATE INDEX IF NOT EXISTS idx_audit_actor_created ON audit_logs(actor,created_at DESC); CREATE INDEX IF NOT EXISTS idx_audit_action_created ON audit_logs(action,created_at DESC); CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at DESC);"""

SQLITE_SCHEMA += """ CREATE TABLE IF NOT EXISTS review_tasks (pattern_id TEXT PRIMARY KEY REFERENCES patterns(id) ON DELETE CASCADE,assignee TEXT NOT NULL,state TEXT NOT NULL CHECK(state IN ('assigned','approved','rejected','needs_more')),decision_note TEXT,assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,decided_by TEXT,decided_at TEXT); CREATE INDEX IF NOT EXISTS idx_review_tasks_assignee_state ON review_tasks(assignee,state); CREATE TABLE IF NOT EXISTS review_operations (request_id TEXT PRIMARY KEY,action TEXT NOT NULL,fingerprint TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);"""
POSTGRES_SCHEMA += """ CREATE TABLE IF NOT EXISTS review_tasks (pattern_id TEXT PRIMARY KEY REFERENCES patterns(id) ON DELETE CASCADE,assignee TEXT NOT NULL,state TEXT NOT NULL CHECK(state IN ('assigned','approved','rejected','needs_more')),decision_note TEXT,assigned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,decided_by TEXT,decided_at TIMESTAMPTZ); CREATE INDEX IF NOT EXISTS idx_review_tasks_assignee_state ON review_tasks(assignee,state); CREATE TABLE IF NOT EXISTS review_operations (request_id TEXT PRIMARY KEY,action TEXT NOT NULL,fingerprint TEXT NOT NULL,result_json JSONB NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP);"""

class Connection:
    """DB-API compatibility layer; application SQL keeps portable question-mark parameters."""
    def __init__(self, raw: Any, backend: str): self.raw, self.backend = raw, backend
    def execute(self, sql: str, params=()): return self.raw.execute(sql.replace("?", "%s") if self.backend == "postgresql" else sql, params)
    def commit(self): self.raw.commit()
    def rollback(self): self.raw.rollback()
    def close(self): self.raw.close()

def connect(target: Settings | Path) -> Connection:
    if isinstance(target, Path): backend, path, url = "sqlite", target, None
    else: backend, path, url = target.database_backend, target.database_path, target.database_url
    if backend == "sqlite":
        path.parent.mkdir(parents=True, exist_ok=True); raw = sqlite3.connect(path, timeout=10); raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA foreign_keys = ON"); raw.execute("PRAGMA journal_mode = WAL"); raw.execute("PRAGMA busy_timeout = 10000")
    else:
        import psycopg
        from psycopg.rows import dict_row
        # Transaction poolers (including Supabase's transaction mode) can
        # reuse a server connection whose prepared-statement namespace was
        # populated by another client. Keep statements unprepared so the
        # adapter works with both direct PostgreSQL and pooled connections.
        raw = psycopg.connect(url, row_factory=dict_row, connect_timeout=10, prepare_threshold=None)
    return Connection(raw, backend)

@contextmanager
def database(target: Settings | Path) -> Iterator[Connection]:
    connection = connect(target)
    try:
        yield connection; connection.commit()
    except Exception:
        connection.rollback(); raise
    finally: connection.close()

def initialize(target: Settings | Path) -> None:
    with database(target) as connection:
        schema = POSTGRES_SCHEMA if connection.backend == "postgresql" else SQLITE_SCHEMA
        connection.raw.executescript(schema) if connection.backend == "sqlite" else connection.execute(schema)

def scalar(row: Any) -> Any: return next(iter(row.values())) if isinstance(row, dict) else row[0]

def check_database(target: Settings | Path) -> None:
    with database(target) as connection:
        if scalar(connection.execute("SELECT 1 AS ok").fetchone()) != 1: raise RuntimeError("database readiness probe failed")

def json_value(value: Any) -> Any: return json.loads(value) if isinstance(value, str) else value

def timestamp_value(value: Any) -> str: return value.isoformat() if hasattr(value, "isoformat") else str(value)

def row_to_dict(row: Any) -> dict:
    result = dict(row); result["colors"] = json_value(result.pop("colors_json")); result["imageUrl"] = result.pop("image_url")
    result["source"] = json_value(result.pop("source_json")); result["rights"] = json_value(result.pop("rights_json")); result["review"] = json_value(result.pop("review_json"))
    result["createdAt"] = timestamp_value(result.pop("created_at")); result["updatedAt"] = timestamp_value(result.pop("updated_at")); return result

def risk_clauses(backend: str, risk: str | None) -> list[str]:
    approved = "EXISTS (SELECT 1 FROM review_tasks rt WHERE rt.pattern_id = patterns.id AND rt.state = 'approved')"
    expressions = ({"has_issues":"jsonb_array_length(COALESCE(review_json->'issues','[]'::jsonb)) > 0","rights_unverified":"COALESCE(rights_json->>'status','') != 'verified'","ready":f"TRIM(name) != '' AND rights_json->>'status' = 'verified' AND jsonb_array_length(COALESCE(review_json->'issues','[]'::jsonb)) = 0 AND {approved}"} if backend == "postgresql" else {"has_issues":"json_array_length(json_extract(review_json, '$.issues')) > 0","rights_unverified":"COALESCE(json_extract(rights_json, '$.status'), '') != 'verified'","ready":f"TRIM(name) != '' AND json_extract(rights_json, '$.status') = 'verified' AND json_array_length(json_extract(review_json, '$.issues')) = 0 AND {approved}"})
    return [expressions[risk]] if risk in expressions else []
