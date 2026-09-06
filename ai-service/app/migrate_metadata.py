"""Idempotently copy AI metadata from SQLite into PostgreSQL.

Usage: python -m app.migrate_metadata --sqlite data/ai-service.sqlite3 --database-url "$DATABASE_URL"
Binary objects are not copied; migrate them separately before switching asset backends.
"""
import argparse
from pathlib import Path

from .storage import PostgreSQLStorage, Storage

TABLES = ("assets", "jobs", "analysis_results", "reference_assets")
KEYS = {"assets": "id", "jobs": "id", "analysis_results": "id", "reference_assets": "asset_id"}


def migrate(source: Storage, destination: PostgreSQLStorage) -> dict[str, int]:
    destination.initialize()
    counts = {}
    for table in TABLES:
        rows = source.all(f"SELECT * FROM {table}")
        for row in rows:
            columns = list(row)
            placeholders = ", ".join("?" for _ in columns)
            column_sql = ", ".join(columns)
            destination.execute(
                f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) "
                f"ON CONFLICT ({KEYS[table]}) DO NOTHING",
                tuple(row[column] for column in columns),
            )
        counts[table] = len(rows)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", type=Path, required=True)
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    source = Storage(args.sqlite.resolve())
    source.initialize()
    print(migrate(source, PostgreSQLStorage(args.database_url)))


if __name__ == "__main__":
    main()
