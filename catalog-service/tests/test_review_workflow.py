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
        mutation_headers = signed_headers("POST", "/api/v1/admin/reviews/batch-assign", "http-assign-001")
        client.post("/api/v1/admin/patterns", headers=headers, json=sample("pat_review_flow_1"))
        payload = {"items": [
            {"patternId": "pat_review_flow_1", "assignee": "专家甲", "requestId": "assign-flow-001"},
            {"patternId": "pat_missing_flow", "assignee": "专家甲", "requestId": "assign-flow-002"},
        ]}
        assert client.post("/api/v1/admin/reviews/batch-assign", json=payload).status_code == 401
        assert client.post("/api/v1/admin/reviews/batch-assign", headers=headers, json=payload).status_code == 401
        first = client.post("/api/v1/admin/reviews/batch-assign", headers=mutation_headers, json=payload).json()
        assert (first["succeeded"], first["failed"]) == (1, 1)
        assert first["items"][0]["task"]["state"] == "assigned"
        assert first["items"][1]["code"] == "not_found"

        replay = client.post("/api/v1/admin/reviews/batch-assign", headers=signed_headers("POST", "/api/v1/admin/reviews/batch-assign", "http-assign-002"), json={"items": payload["items"][:1]}).json()
        assert replay["items"][0]["replayed"] is True
        logs = client.get("/api/v1/admin/patterns/pat_review_flow_1/audit-logs", headers=headers).json()
        assert [item["action"] for item in logs] == ["review_assigned", "created"]
        assert logs[0]["actor"] == "assignment-manager"

        conflict = client.post("/api/v1/admin/reviews/batch-assign", headers=signed_headers("POST", "/api/v1/admin/reviews/batch-assign", "http-assign-003"), json={"items": [{
            "patternId": "pat_review_flow_1", "assignee": "专家乙", "requestId": "assign-flow-001"
        }]}).json()
        assert conflict["items"][0]["code"] == "idempotency_conflict"


def test_decision_requires_assignee_and_controls_review_risk(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        headers = {"X-Admin-Token": "test-token"}
        client.post("/api/v1/admin/patterns", headers=headers, json=sample("pat_review_flow_2"))
        decision_path = "/api/v1/admin/reviews/batch-decide"
        assignment_path = "/api/v1/admin/reviews/batch-assign"
        assert client.post(decision_path, headers=headers, json={"items": [{
            "patternId": "pat_review_flow_2", "decision": "approved", "decidedBy": "reviewer-a",
            "requestId": "unsigned-decision", "issues": []
        }]}).status_code == 401
        unassigned = client.post(decision_path, headers=signed_headers("POST", decision_path, "http-decide-001", "reviewer-a"), json={"items": [{
            "patternId": "pat_review_flow_2", "decision": "approved", "decidedBy": "reviewer-a",
            "requestId": "decide-flow-001", "issues": []
        }]}).json()
        assert unassigned["items"][0]["code"] == "review_not_assigned"

        client.post(assignment_path, headers=signed_headers("POST", assignment_path, "http-assign-004", "reviewer-a"), json={"items": [{
            "patternId": "pat_review_flow_2", "assignee": "reviewer-a", "requestId": "assign-flow-003"
        }]})
        mismatch = client.post(decision_path, headers=signed_headers("POST", decision_path, "http-decide-002", "reviewer-a"), json={"items": [{
            "patternId": "pat_review_flow_2", "decision": "approved", "decidedBy": "专家乙",
            "requestId": "decide-flow-002", "issues": []
        }]}).json()
        assert mismatch["items"][0]["code"] == "actor_mismatch"

        approved_payload = {"items": [{
            "patternId": "pat_review_flow_2", "decision": "approved", "decidedBy": "reviewer-a",
            "note": "内容核验通过", "requestId": "decide-flow-003", "issues": []
        }]}
        approved = client.post(decision_path, headers=signed_headers("POST", decision_path, "http-decide-003", "reviewer-a"), json=approved_payload).json()
        assert approved["items"][0]["task"]["state"] == "approved"
        assert approved["items"][0]["task"]["decisionNote"] == "内容核验通过"
        assert approved["items"][0]["task"]["decidedBy"] == "reviewer-a"
        replay = client.post(decision_path, headers=signed_headers("POST", decision_path, "http-decide-004", "reviewer-a"), json=approved_payload).json()
        assert replay["items"][0]["replayed"] is True
        pattern = client.get("/api/v1/admin/patterns/pat_review_flow_2", headers=headers).json()
        assert pattern["review"]["issues"] == []
        assert pattern["review"]["reviewedBy"] == "reviewer-a"
        tasks = client.get("/api/v1/admin/reviews/tasks?assignee=reviewer-a&state=approved", headers=headers).json()
        assert [task["patternId"] for task in tasks] == ["pat_review_flow_2"]
        logs = client.get("/api/v1/admin/patterns/pat_review_flow_2/audit-logs", headers=headers).json()
        assert [item["action"] for item in logs] == ["review_approved", "review_assigned", "created"]
        assert logs[0]["actor"] == "reviewer-a"


def test_reject_and_needs_more_require_findings_and_do_not_change_rights(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        headers = {"X-Admin-Token": "test-token"}
        client.post("/api/v1/admin/patterns", headers=headers, json=sample("pat_review_flow_3", rights="unverified"))
        assignment_path = "/api/v1/admin/reviews/batch-assign"
        decision_path = "/api/v1/admin/reviews/batch-decide"
        client.post(assignment_path, headers=signed_headers("POST", assignment_path, "http-assign-005", "reviewer-a"), json={"items": [{
            "patternId": "pat_review_flow_3", "assignee": "reviewer-a", "requestId": "assign-flow-004"
        }]})
        invalid = client.post(decision_path, headers=signed_headers("POST", decision_path, "http-decide-005", "reviewer-a"), json={"items": [{
            "patternId": "pat_review_flow_3", "decision": "needs_more", "decidedBy": "reviewer-a",
            "requestId": "decide-flow-004", "issues": []
        }]}).json()
        assert invalid["items"][0]["code"] == "invalid_review_decision"

        decided = client.post(decision_path, headers=signed_headers("POST", decision_path, "http-decide-006", "reviewer-a"), json={"items": [{
            "patternId": "pat_review_flow_3", "decision": "needs_more", "decidedBy": "reviewer-a",
            "requestId": "decide-flow-005", "issues": ["缺少版权授权书"]
        }]}).json()
        assert decided["items"][0]["task"]["state"] == "needs_more"
        pattern = client.get("/api/v1/admin/patterns/pat_review_flow_3", headers=headers).json()
        assert pattern["rights"]["status"] == "unverified"
        assert pattern["review"]["issues"] == ["缺少版权授权书"]
        publish = client.post("/api/v1/admin/patterns/pat_review_flow_3/publish", headers=headers)
        assert publish.status_code == 422


def test_content_changes_invalidate_completed_review_decisions(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        from app import main
        from app.evidence_storage import StoredEvidence

        headers = {"X-Admin-Token": "test-token"}
        cases = [
            ("pat_invalidate_approved", "approved", [], "profile"),
            ("pat_invalidate_rejected", "rejected", ["名称存疑"], "rights"),
            ("pat_invalidate_needs_more", "needs_more", ["缺少凭证"], "upload"),
        ]
        assignment_path = "/api/v1/admin/reviews/batch-assign"
        decision_path = "/api/v1/admin/reviews/batch-decide"
        reviewer = "reviewer-a"
        for index, (pattern_id, decision, issues, change_kind) in enumerate(cases):
            assert client.post("/api/v1/admin/patterns", headers=headers, json=sample(pattern_id)).status_code == 201
            client.post(assignment_path, headers=signed_headers("POST", assignment_path, f"http-assign-invalidate-{index}", reviewer), json={"items": [{
                "patternId": pattern_id, "assignee": reviewer, "requestId": f"assign-invalidate-{index}"
            }]})
            decided = client.post(decision_path, headers=signed_headers("POST", decision_path, f"http-decide-invalidate-{index}", reviewer), json={"items": [{
                "patternId": pattern_id, "decision": decision, "decidedBy": reviewer,
                "requestId": f"decide-invalidate-{index}", "issues": issues,
            }]}).json()
            assert decided["items"][0]["task"]["state"] == decision

            if change_kind == "profile":
                response = client.patch(f"/api/v1/admin/patterns/{pattern_id}", headers=headers, json={"name": "修改后的名称"})
            elif change_kind == "rights":
                response = client.patch(f"/api/v1/admin/patterns/{pattern_id}/evidence", headers=headers, json={"rightsOwner": "新权利人"})
            else:
                async def fake_store(_pattern_id, _upload, _settings):
                    return StoredEvidence("ev_invalidate", "proof.pdf", "application/pdf", 9, "test/proof.pdf", "a" * 64)

                monkeypatch.setattr(main, "store_upload", fake_store)
                response = client.post(
                    f"/api/v1/admin/patterns/{pattern_id}/evidence-files", headers=headers,
                    files={"file": ("proof.pdf", b"%PDF-test", "application/pdf")},
                )
            assert response.status_code == 200
            task = client.get(f"/api/v1/admin/reviews/tasks?assignee={reviewer}&state=assigned", headers=headers).json()
            reset = next(item for item in task if item["patternId"] == pattern_id)
            assert reset["decisionNote"] is None
            assert reset["decidedBy"] is None
            assert reset["decidedAt"] is None
            logs = client.get(f"/api/v1/admin/patterns/{pattern_id}/audit-logs", headers=headers).json()
            assert logs[0]["action"] == "review_invalidated"
            assert logs[0]["before"]["state"] == decision
            assert logs[0]["after"]["state"] == "assigned"


def test_noop_evidence_update_does_not_invalidate_review(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        headers = {"X-Admin-Token": "test-token"}
        pattern_id = "pat_invalidate_noop"
        assignment_path = "/api/v1/admin/reviews/batch-assign"
        decision_path = "/api/v1/admin/reviews/batch-decide"
        reviewer = "reviewer-a"
        client.post("/api/v1/admin/patterns", headers=headers, json=sample(pattern_id))
        client.post(assignment_path, headers=signed_headers("POST", assignment_path, "http-assign-invalidate-noop", reviewer), json={"items": [{
            "patternId": pattern_id, "assignee": reviewer, "requestId": "assign-invalidate-noop"
        }]})
        client.post(decision_path, headers=signed_headers("POST", decision_path, "http-decide-invalidate-noop", reviewer), json={"items": [{
            "patternId": pattern_id, "decision": "approved", "decidedBy": reviewer,
            "requestId": "decide-invalidate-noop", "issues": [],
        }]})
        response = client.patch(f"/api/v1/admin/patterns/{pattern_id}/evidence", headers=headers, json={"rightsStatus": "verified"})
        assert response.status_code == 200
        tasks = client.get(f"/api/v1/admin/reviews/tasks?assignee={reviewer}&state=approved", headers=headers).json()
        assert any(item["patternId"] == pattern_id for item in tasks)
        logs = client.get(f"/api/v1/admin/patterns/{pattern_id}/audit-logs", headers=headers).json()
        assert all(item["action"] != "review_invalidated" for item in logs)


def test_publish_rechecks_approval_after_ai_sync_and_compensates(tmp_path, monkeypatch):
    monkeypatch.setenv("CATALOG_AI_INTERNAL_BASE_URL", "http://ai:8002/v1")
    monkeypatch.setenv("CATALOG_AI_SERVICE_TOKEN", "service-secret")
    with client_for(tmp_path, monkeypatch) as client:
        from app import main

        headers = {"X-Admin-Token": "test-token"}
        pattern_id = "pat_publish_review_race"
        reviewer = "reviewer-a"
        assignment_path = "/api/v1/admin/reviews/batch-assign"
        decision_path = "/api/v1/admin/reviews/batch-decide"
        client.post("/api/v1/admin/patterns", headers=headers, json={
            **sample(pattern_id), "review": {"issues": []},
        })
        client.post(assignment_path, headers=signed_headers("POST", assignment_path, "http-assign-publish-race", reviewer), json={"items": [{
            "patternId": pattern_id, "assignee": reviewer, "requestId": "assign-publish-race",
        }]})
        client.post(decision_path, headers=signed_headers("POST", decision_path, "http-decide-publish-race", reviewer), json={"items": [{
            "patternId": pattern_id, "decision": "approved", "decidedBy": reviewer,
            "requestId": "decide-publish-race", "issues": [],
        }]})
        calls = []

        def fake_sync(sync_pattern_id, published, settings):
            calls.append((sync_pattern_id, published))
            if published:
                with main.database(settings) as connection:
                    connection.execute("UPDATE review_tasks SET state='assigned' WHERE pattern_id=?", (pattern_id,))
            return "synchronized"

        monkeypatch.setattr(main, "sync_publication", fake_sync)
        response = client.post(f"/api/v1/admin/patterns/{pattern_id}/publish", headers=headers)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "review_changed_during_publish"
        assert calls == [(pattern_id, True), (pattern_id, False)]
        pattern = client.get(f"/api/v1/admin/patterns/{pattern_id}", headers=headers).json()
        assert pattern["status"] == "draft"
        assert pattern["visibility"] == "internal_only"


def test_published_pattern_cannot_reenter_review(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        headers = {"X-Admin-Token": "test-token"}
        payload = sample("pat_review_flow_4")
        payload["review"] = {"issues": []}
        client.post("/api/v1/admin/patterns", headers=headers, json=payload)
        assignment_path = "/api/v1/admin/reviews/batch-assign"
        decision_path = "/api/v1/admin/reviews/batch-decide"
        client.post(assignment_path, headers=signed_headers("POST", assignment_path, "http-assign-006", "reviewer-a"), json={"items": [{
            "patternId": "pat_review_flow_4", "assignee": "reviewer-a", "requestId": "assign-flow-006"
        }]})
        client.post(decision_path, headers=signed_headers("POST", decision_path, "http-decide-007", "reviewer-a"), json={"items": [{
            "patternId": "pat_review_flow_4", "decision": "approved", "decidedBy": "reviewer-a",
            "requestId": "decide-flow-006", "issues": []
        }]})
        assert client.post("/api/v1/admin/patterns/pat_review_flow_4/publish", headers=headers).status_code == 200
        response = client.post(assignment_path, headers=signed_headers("POST", assignment_path, "http-assign-007", "reviewer-a"), json={"items": [{
            "patternId": "pat_review_flow_4", "assignee": "reviewer-a", "requestId": "assign-flow-005"
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
