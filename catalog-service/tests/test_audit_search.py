import importlib

from fastapi.testclient import TestClient


def client_for(tmp_path, monkeypatch):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("CATALOG_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("CATALOG_ADMIN_TOKEN", "test-token")
    monkeypatch.setenv("CATALOG_ACTOR_SIGNING_SECRET", "actor-secret-that-is-at-least-32-bytes")
    from app import main
    importlib.reload(main)
    return TestClient(main.app), database_path


def seed_audits(database_path):
    from app.db import database
    rows = [
        ("pat_alpha", "created", "alice", None, '{"name":"A"}', "2026-01-01 09:00:00"),
        ("pat_beta", "updated", "bob", '{"name":"B"}', '{"name":"B2"}', "2026-01-02 09:00:00"),
        ("pat_alpha", "published", "alice", None, '{"status":"published"}', "2026-01-02 09:00:00"),
        ("pat_percent", "updated", "percent%actor", None, '{}', "2026-01-03 09:00:00"),
    ]
    with database(database_path) as connection:
        connection.raw.executemany(
            "INSERT INTO audit_logs(pattern_id,action,actor,before_json,after_json,created_at) VALUES(?,?,?,?,?,?)",
            rows,
        )


def test_global_audit_search_requires_admin_and_has_stable_pagination(tmp_path, monkeypatch):
    client, database_path = client_for(tmp_path, monkeypatch)
    with client:
        seed_audits(database_path)
        assert client.get("/api/v1/admin/audit-logs").status_code == 401
        headers = {"X-Admin-Token": "test-token"}
        first = client.get("/api/v1/admin/audit-logs?page=1&pageSize=2", headers=headers).json()
        second = client.get("/api/v1/admin/audit-logs?page=2&pageSize=2", headers=headers).json()
        assert (first["total"], first["pages"], first["page"], first["pageSize"]) == (4, 2, 1, 2)
        assert [item["patternId"] for item in first["items"]] == ["pat_percent", "pat_alpha"]
        assert [item["patternId"] for item in second["items"]] == ["pat_beta", "pat_alpha"]
        assert first["items"][1]["after"] == {"status": "published"}


def test_global_audit_search_filters_and_treats_q_wildcards_literally(tmp_path, monkeypatch):
    client, database_path = client_for(tmp_path, monkeypatch)
    with client:
        seed_audits(database_path)
        headers = {"X-Admin-Token": "test-token"}
        by_fields = client.get(
            "/api/v1/admin/audit-logs?actor=alice&action=published&patternId=pat_alpha",
            headers=headers,
        ).json()
        assert by_fields["total"] == 1
        assert by_fields["items"][0]["action"] == "published"

        broad = client.get("/api/v1/admin/audit-logs?q=ALPHA", headers=headers).json()
        assert broad["total"] == 2
        literal = client.get("/api/v1/admin/audit-logs?q=%25", headers=headers).json()
        assert literal["total"] == 1
        assert literal["items"][0]["actor"] == "percent%actor"

        ranged = client.get(
            "/api/v1/admin/audit-logs?from=2026-01-02T00:00:00Z&to=2026-01-02T23:59:59Z",
            headers=headers,
        ).json()
        assert ranged["total"] == 2
        assert client.get(
            "/api/v1/admin/audit-logs?from=2026-01-03T00:00:00Z&to=2026-01-02T00:00:00Z",
            headers=headers,
        ).status_code == 422


def test_audit_search_indexes_are_initialized_for_sqlite(tmp_path, monkeypatch):
    client, database_path = client_for(tmp_path, monkeypatch)
    with client:
        from app.db import database
        with database(database_path) as connection:
            indexes = {row["name"] for row in connection.execute("PRAGMA index_list('audit_logs')").fetchall()}
        assert {"idx_audit_actor_created", "idx_audit_action_created", "idx_audit_created"} <= indexes
