from app.storage import PostgreSQLStorage, Storage, create_storage


def test_storage_factory_keeps_sqlite_default(tmp_path):
    storage = create_storage("sqlite", tmp_path / "db.sqlite3")
    assert isinstance(storage, Storage)


def test_postgres_placeholder_translation():
    assert PostgreSQLStorage._sql("SELECT * FROM assets WHERE id = ?") == \
        "SELECT * FROM assets WHERE id = %s"


def test_postgres_requires_url(tmp_path):
    try:
        create_storage("postgresql", tmp_path / "unused", "")
    except RuntimeError as exc:
        assert "URL" in str(exc)
    else:
        raise AssertionError("missing URL must fail")
