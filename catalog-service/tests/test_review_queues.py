import importlib
import json
import sqlite3

from fastapi.testclient import TestClient


def client_for(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setenv("CATALOG_DATABASE_PATH", str(path))
    monkeypatch.setenv("CATALOG_ADMIN_TOKEN", "test-token")
    from app import main
    importlib.reload(main)
    return path, TestClient(main.app)


def insert(path, pattern_id, name, category, provenance, *, rights="unverified", review=None):
    with sqlite3.connect(path) as connection:
        connection.execute("""INSERT INTO patterns
            (id,name,category,status,visibility,source_json,rights_json,review_json)
            VALUES(?,?,?,'draft','internal_only',?,?,?)""",
            (pattern_id, name, category, json.dumps({"seedProvenance": provenance}),
             json.dumps({"status": rights}), json.dumps(review or {"issues": ["待审核"]})))


def test_review_queue_summary_filters_pagination_and_auth(tmp_path, monkeypatch):
    path, client = client_for(tmp_path, monkeypatch)
    headers = {"X-Admin-Token": "test-token"}
    with client:
        insert(path, "pat_queue_1", " 云纹 ", "待分类", {"width": 120, "height": 400,
            "candidateName": "云纹候选", "motifCodeDraft": "nature"})
        insert(path, "pat_queue_2", "云纹", "自然纹", {"width": 800, "height": 600,
            "categorySuggestion": {"code": "geometry", "label": "几何"}})
        insert(path, "pat_queue_3", "羊角纹", "动物纹", {"width": 600, "height": 600})
        insert(path, "pat_queue_4", "未知纹", "待分类", {"width": 600, "height": 600,
            "categorySuggestion": {"code": "unknown", "label": "待分类"}})

        assert client.get("/api/v1/admin/review-queues/summary").status_code == 401
        summary = client.get("/api/v1/admin/review-queues/summary", headers=headers).json()
        assert summary == {"total": 4, "lowResolution": 1, "nameNeedsReview": 1,
            "duplicateName": 2, "uncategorized": 2, "categorySuggestion": 2,
            "lowResolutionEdge": 256}

        duplicate = client.get("/api/v1/admin/review-queues/patterns?queue=duplicate_name&pageSize=1", headers=headers).json()
        assert duplicate["total"] == 2 and duplicate["pages"] == 2 and len(duplicate["items"]) == 1
        suggested = client.get("/api/v1/admin/review-queues/patterns?queue=category_suggestion&suggestion=几何", headers=headers).json()
        assert [item["patternId"] for item in suggested["items"]] == ["pat_queue_2"]
        assert suggested["items"][0]["category"] == "自然纹"


def test_review_queues_are_read_only_and_missing_dimensions_are_low_resolution(tmp_path, monkeypatch):
    path, client = client_for(tmp_path, monkeypatch)
    headers = {"X-Admin-Token": "test-token"}
    with client:
        insert(path, "pat_queue_safe", "待核纹样", "", {"motif_code_draft": "plant"},
               rights="verified", review={"issues": []})
        with sqlite3.connect(path) as connection:
            before = connection.execute("SELECT * FROM patterns WHERE id='pat_queue_safe'").fetchone()
        item = client.get("/api/v1/admin/review-queues/patterns?queue=low_resolution", headers=headers).json()["items"][0]
        assert item["width"] is None and item["height"] is None
        assert item["categorySuggestionLabel"] == "植物"
        with sqlite3.connect(path) as connection:
            after = connection.execute("SELECT * FROM patterns WHERE id='pat_queue_safe'").fetchone()
            audit_count = connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        assert before == after and audit_count == 0
