import importlib
import hashlib
import hmac
import time

from fastapi.testclient import TestClient


def client_for(tmp_path, monkeypatch):
    monkeypatch.setenv("CATALOG_DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CATALOG_ADMIN_TOKEN", "test-token")
    monkeypatch.setenv("CATALOG_ACTOR_SIGNING_SECRET", "actor-secret-that-is-at-least-32-bytes")
    monkeypatch.delenv("CATALOG_DATABASE_URL", raising=False)
    from app import main
    importlib.reload(main)
    return TestClient(main.app)


def signed_headers(method: str, path: str, request_id: str, actor: str = "assignment-manager"):
    timestamp = str(int(time.time()))
    canonical = f"{timestamp}\n{method}\n{path}\n{actor}\n{request_id}"
    signature = hmac.new(b"actor-secret-that-is-at-least-32-bytes", canonical.encode(), hashlib.sha256).hexdigest()
    return {
        "X-Admin-Token": "test-token", "X-Admin-Actor": actor, "X-Admin-Timestamp": timestamp,
        "X-Admin-Signature": signature, "X-Request-ID": request_id,
    }


def sample(pattern_id: str, *, rights="verified"):
    return {
        "id": pattern_id,
        "name": "审核测试纹样",
        "source": {"system": "test"},
        "rights": {"status": rights},
        "review": {"issues": ["待审核"]},
    }


def test_batch_assignment_is_partial_audited_and_idempotent(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        headers = {"X-Admin-Token": "test-token"}
        client.post("/api/v1/admin/patterns", headers=headers, json=sample("pat_review_flow_1"))
        payload = {"items": [
            {"patternId": "pat_review_flow_1", "assignee": "专家甲", "requestId": "assign-flow-001"},
            {"patternId": "pat_missing_flow", "assignee": "专家甲", "requestId": "assign-flow-002"},
        ]}
        assert client.post("/api/v1/admin/reviews/batch-assign", json=payload).status_code == 401
        first = client.post("/api/v1/admin/reviews/batch-assign", headers=headers, json=payload).json()
        assert (first["succeeded"], first["failed"]) == (1, 1)
        assert first["items"][0]["task"]["state"] == "assigned"
        assert first["items"][1]["code"] == "not_found"

        replay = client.post("/api/v1/admin/reviews/batch-assign", headers=headers, json={"items": payload["items"][:1]}).json()
        assert replay["items"][0]["replayed"] is True
        logs = client.get("/api/v1/admin/patterns/pat_review_flow_1/audit-logs", headers=headers).json()
        assert [item["action"] for item in logs] == ["review_assigned", "created"]

        conflict = client.post("/api/v1/admin/reviews/batch-assign", headers=headers, json={"items": [{
            "patternId": "pat_review_flow_1", "assignee": "专家乙", "requestId": "assign-flow-001"
        }]}).json()
        assert conflict["items"][0]["code"] == "idempotency_conflict"


def test_decision_requires_assignee_and_controls_review_risk(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        headers = {"X-Admin-Token": "test-token"}
        client.post("/api/v1/admin/patterns", headers=headers, json=sample("pat_review_flow_2"))
        unassigned = client.post("/api/v1/admin/reviews/batch-decide", headers=headers, json={"items": [{
            "patternId": "pat_review_flow_2", "decision": "approved", "decidedBy": "专家甲",
            "requestId": "decide-flow-001", "issues": []
        }]}).json()
        assert unassigned["items"][0]["code"] == "review_not_assigned"

        client.post("/api/v1/admin/reviews/batch-assign", headers=headers, json={"items": [{
            "patternId": "pat_review_flow_2", "assignee": "专家甲", "requestId": "assign-flow-003"
        }]})
        mismatch = client.post("/api/v1/admin/reviews/batch-decide", headers=headers, json={"items": [{
            "patternId": "pat_review_flow_2", "decision": "approved", "decidedBy": "专家乙",
            "requestId": "decide-flow-002", "issues": []
        }]}).json()
        assert mismatch["items"][0]["code"] == "reviewer_mismatch"

        approved_payload = {"items": [{
            "patternId": "pat_review_flow_2", "decision": "approved", "decidedBy": "专家甲",
            "note": "内容核验通过", "requestId": "decide-flow-003", "issues": []
        }]}
        approved = client.post("/api/v1/admin/reviews/batch-decide", headers=headers, json=approved_payload).json()
        assert approved["items"][0]["task"]["state"] == "approved"
        assert approved["items"][0]["task"]["decisionNote"] == "内容核验通过"
        replay = client.post("/api/v1/admin/reviews/batch-decide", headers=headers, json=approved_payload).json()
        assert replay["items"][0]["replayed"] is True
        pattern = client.get("/api/v1/admin/patterns/pat_review_flow_2", headers=headers).json()
        assert pattern["review"]["issues"] == []
        assert pattern["review"]["reviewedBy"] == "专家甲"
        tasks = client.get("/api/v1/admin/reviews/tasks?assignee=专家甲&state=approved", headers=headers).json()
        assert [task["patternId"] for task in tasks] == ["pat_review_flow_2"]
        logs = client.get("/api/v1/admin/patterns/pat_review_flow_2/audit-logs", headers=headers).json()
        assert [item["action"] for item in logs] == ["review_approved", "review_assigned", "created"]


def test_reject_and_needs_more_require_findings_and_do_not_change_rights(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        headers = {"X-Admin-Token": "test-token"}
        client.post("/api/v1/admin/patterns", headers=headers, json=sample("pat_review_flow_3", rights="unverified"))
        client.post("/api/v1/admin/reviews/batch-assign", headers=headers, json={"items": [{
            "patternId": "pat_review_flow_3", "assignee": "专家甲", "requestId": "assign-flow-004"
        }]})
        invalid = client.post("/api/v1/admin/reviews/batch-decide", headers=headers, json={"items": [{
            "patternId": "pat_review_flow_3", "decision": "needs_more", "decidedBy": "专家甲",
            "requestId": "decide-flow-004", "issues": []
        }]}).json()
        assert invalid["items"][0]["code"] == "invalid_review_decision"

        decided = client.post("/api/v1/admin/reviews/batch-decide", headers=headers, json={"items": [{
            "patternId": "pat_review_flow_3", "decision": "needs_more", "decidedBy": "专家甲",
            "requestId": "decide-flow-005", "issues": ["缺少版权授权书"]
        }]}).json()
        assert decided["items"][0]["task"]["state"] == "needs_more"
        pattern = client.get("/api/v1/admin/patterns/pat_review_flow_3", headers=headers).json()
        assert pattern["rights"]["status"] == "unverified"
        assert pattern["review"]["issues"] == ["缺少版权授权书"]
        publish = client.post("/api/v1/admin/patterns/pat_review_flow_3/publish", headers=headers)
        assert publish.status_code == 422


def test_published_pattern_cannot_reenter_review(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        headers = {"X-Admin-Token": "test-token"}
        payload = sample("pat_review_flow_4")
        payload["review"] = {"issues": []}
        client.post("/api/v1/admin/patterns", headers=headers, json=payload)
        client.post("/api/v1/admin/reviews/batch-assign", headers=headers, json={"items": [{
            "patternId": "pat_review_flow_4", "assignee": "专家甲", "requestId": "assign-flow-006"
        }]})
        client.post("/api/v1/admin/reviews/batch-decide", headers=headers, json={"items": [{
            "patternId": "pat_review_flow_4", "decision": "approved", "decidedBy": "专家甲",
            "requestId": "decide-flow-006", "issues": []
        }]})
        assert client.post("/api/v1/admin/patterns/pat_review_flow_4/publish", headers=headers).status_code == 200
        response = client.post("/api/v1/admin/reviews/batch-assign", headers=headers, json={"items": [{
            "patternId": "pat_review_flow_4", "assignee": "专家甲", "requestId": "assign-flow-005"
        }]}).json()
        assert response["items"][0]["code"] == "review_not_editable"


def test_bulk_assign_requires_signature_is_bounded_idempotent_and_assignment_only(tmp_path, monkeypatch):
    path = "/api/v1/admin/reviews/bulk-assign"
    with client_for(tmp_path, monkeypatch) as client:
        admin = {"X-Admin-Token": "test-token"}
        for pattern_id in ("pat_bulk_safe_1", "pat_bulk_safe_2"):
            client.post("/api/v1/admin/patterns", headers=admin, json=sample(pattern_id))
        payload = {
            "patternIds": ["pat_bulk_safe_1", "pat_missing_bulk", "pat_bulk_safe_2"],
            "assignee": "专家丙", "requestId": "bulk-safe-001",
        }
        assert client.post(path, headers=admin, json=payload).status_code == 401

        headers = signed_headers("POST", path, "http-request-bulk-001")
        first = client.post(path, headers=headers, json=payload)
        assert first.status_code == 200
        assert (first.json()["succeeded"], first.json()["failed"]) == (2, 1)
        assert all(item.get("task", {}).get("state") == "assigned" for item in first.json()["items"] if item["status"] == "succeeded")

        replay = client.post(path, headers=signed_headers("POST", path, "http-request-bulk-002"), json=payload)
        assert replay.status_code == 200
        assert all(item["replayed"] for item in replay.json()["items"])
        conflict = client.post(path, headers=signed_headers("POST", path, "http-request-bulk-003"), json={
            **payload, "patternIds": ["pat_bulk_safe_1"]
        })
        assert conflict.status_code == 409

        pattern = client.get("/api/v1/admin/patterns/pat_bulk_safe_1", headers=admin).json()
        assert pattern["status"] == "draft"
        assert pattern["visibility"] == "internal_only"
        assert pattern["review"]["issues"] == ["待审核"]
        logs = client.get("/api/v1/admin/patterns/pat_bulk_safe_1/audit-logs", headers=admin).json()
        assert logs[0]["action"] == "review_bulk_assigned"
        assert logs[0]["actor"] == "assignment-manager"

        duplicate = client.post(path, headers=signed_headers("POST", path, "http-request-bulk-004"), json={
            "patternIds": ["pat_bulk_safe_1", "pat_bulk_safe_1"], "assignee": "专家丙", "requestId": "bulk-safe-002"
        })
        assert duplicate.status_code == 422
        oversized = client.post(path, headers=signed_headers("POST", path, "http-request-bulk-005"), json={
            "patternIds": [f"pat_bulk_{index:03d}" for index in range(51)], "assignee": "专家丙", "requestId": "bulk-safe-003"
        })
        assert oversized.status_code == 422
