"""Idempotently copy a catalog SQLite database into PostgreSQL."""
import argparse
import sqlite3
from pathlib import Path

from .config import Settings, get_settings, validate_settings
from .db import database, initialize

PATTERN_COLUMNS = ("id","name","category","ethnicity","meaning","colors_json","image_url","status","visibility","source_json","rights_json","review_json","created_at","updated_at")
AUDIT_COLUMNS = ("id","pattern_id","action","actor","before_json","after_json","created_at")

def _upsert(connection, table: str, columns: tuple[str, ...], row: sqlite3.Row, key: str) -> None:
    updates = ",".join(f"{column}=EXCLUDED.{column}" for column in columns if column != key)
    placeholders = ",".join("?" for _ in columns)
    connection.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders}) ON CONFLICT ({key}) DO UPDATE SET {updates}", tuple(row[column] for column in columns))

def migrate(source: Path, target: Settings) -> tuple[int, int]:
    if target.database_backend != "postgresql": raise ValueError("migration target must use PostgreSQL")
    validate_settings(target); initialize(target)
    source_connection = sqlite3.connect(source); source_connection.row_factory = sqlite3.Row
    try:
        patterns = source_connection.execute("SELECT * FROM patterns ORDER BY id").fetchall()
        audits = source_connection.execute("SELECT * FROM audit_logs ORDER BY id").fetchall()
        with database(target) as destination:
            for row in patterns: _upsert(destination, "patterns", PATTERN_COLUMNS, row, "id")
            for row in audits: _upsert(destination, "audit_logs", AUDIT_COLUMNS, row, "id")
            destination.execute("SELECT setval(pg_get_serial_sequence('audit_logs','id'), COALESCE((SELECT MAX(id) FROM audit_logs), 1), EXISTS(SELECT 1 FROM audit_logs))")
        return len(patterns), len(audits)
    finally: source_connection.close()

def main() -> None:
    parser = argparse.ArgumentParser(description="Idempotently migrate Catalog SQLite data to PostgreSQL")
    parser.add_argument("--source", type=Path, default=get_settings().database_path)
    args = parser.parse_args(); target = get_settings()
    patterns, audits = migrate(args.source, target)
    print(f"migration complete: patterns={patterns}, audit_logs={audits}")

if __name__ == "__main__": main()
