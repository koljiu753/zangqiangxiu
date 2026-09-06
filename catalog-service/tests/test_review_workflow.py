import importlib

from fastapi.testclient import TestClient


def client_for(tmp_path, monkeypatch):
    monkeypatch.setenv("CATALOG_DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CATALOG_ADMIN_TOKEN", "test-token")
    monkeypatch.delenv("CATALOG_DATABASE_URL", raising=False)
    from app import main
    importlib.reload(main)
    return TestClient(main.app)


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
