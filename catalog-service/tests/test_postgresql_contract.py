from pathlib import Path
from datetime import datetime, timezone
import pytest
from app.config import Settings, validate_settings
from app.db import Connection, POSTGRES_SCHEMA, database, initialize, risk_clauses, timestamp_value
from app.migrate_sqlite_to_postgres import _upsert

def settings(url=None): return Settings(Path("unused.db"), "postgresql", url, "development", "token", ())

def test_postgres_requires_url():
    with pytest.raises(RuntimeError, match="DATABASE_URL"): validate_settings(settings())
    validate_settings(settings("postgresql://example/catalog"))

def test_postgres_schema_contract_uses_jsonb_and_timestamptz():
    assert POSTGRES_SCHEMA.count("JSONB") >= 5
    assert "TIMESTAMPTZ" in POSTGRES_SCHEMA
    assert "id BIGSERIAL PRIMARY KEY" in POSTGRES_SCHEMA

def test_parameter_and_filter_dialect_contract():
    class Raw:
        def execute(self, sql, params): self.call = (sql, params); return self
    raw = Raw(); Connection(raw, "postgresql").execute("SELECT * FROM patterns WHERE id=?", ("p1",))
    assert raw.call == ("SELECT * FROM patterns WHERE id=%s", ("p1",))
    assert "->>'status'" in risk_clauses("postgresql", "ready")[0]

def test_postgres_timestamp_is_serialized_for_api_models():
    value = datetime(2026, 9, 3, 8, 0, tzinfo=timezone.utc)
    assert timestamp_value(value) == "2026-09-03T08:00:00+00:00"

def test_migration_upsert_preserves_ids_and_is_idempotent_sql():
    class Destination:
        def execute(self, sql, params): self.sql, self.params = sql, params
    row = {column: f"v-{column}" for column in ("id", "name")}; destination = Destination()
    _upsert(destination, "patterns", ("id", "name"), row, "id")
    assert "ON CONFLICT (id) DO UPDATE" in destination.sql
    assert destination.params[0] == "v-id"

def test_database_context_rolls_back_on_failure(tmp_path):
    path = tmp_path / "rollback.db"; initialize(path)
    with pytest.raises(RuntimeError):
        with database(path) as connection:
            connection.execute("INSERT INTO patterns(id,name) VALUES(?,?)", ("p1", "temporary"))
            raise RuntimeError("abort")
    with database(path) as connection:
        assert connection.execute("SELECT 1 FROM patterns WHERE id=?", ("p1",)).fetchone() is None
