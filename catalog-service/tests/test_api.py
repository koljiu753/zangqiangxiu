import importlib
import csv
import io
import pytest
import hashlib
import hmac
import time

from fastapi.testclient import TestClient


def client_for(tmp_path, monkeypatch):
    monkeypatch.setenv("CATALOG_DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CATALOG_ADMIN_TOKEN", "test-token")
    from app import main
    importlib.reload(main)
    return TestClient(main.app)


def sample(name="祥云纹", **overrides):
    payload = {
        "id": "pat_cloud_001",
        "name": name,
        "category": "自然纹",
        "ethnicity": "藏羌共融",
        "meaning": "吉祥流动",
        "colors": ["#d8b76a"],
        "source": {"system": "test"},
        "rights": {"status": "verified"},
        "review": {"issues": []},
    }
    payload.update(overrides)
    return payload


def approve(client, headers, pattern_id, assignee="专家甲"):
    suffix = pattern_id.replace("pat_", "")
    assigned = client.post("/api/v1/admin/reviews/batch-assign", headers=headers, json={"items": [{
        "patternId": pattern_id, "assignee": assignee, "requestId": f"assign-{suffix}"
    }]})
    assert assigned.json()["items"][0]["status"] == "succeeded"
    decided = client.post("/api/v1/admin/reviews/batch-decide", headers=headers, json={"items": [{
        "patternId": pattern_id, "decision": "approved", "decidedBy": assignee,
        "requestId": f"decide-{suffix}", "issues": []
    }]})
    assert decided.json()["items"][0]["status"] == "succeeded"


def signed_headers(method, path, actor="operator-a", timestamp=None, request_id="request-actor-001", secret="actor-secret-that-is-at-least-32-bytes"):
    timestamp = str(timestamp or int(time.time()))
    canonical = f"{timestamp}\n{method}\n{path}\n{actor}\n{request_id}"
    signature = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    return {"X-Admin-Token": "test-token", "X-Admin-Actor": actor, "X-Admin-Timestamp": timestamp,
            "X-Admin-Signature": signature, "X-Request-ID": request_id}


def test_signed_actor_is_audited_and_forged_or_expired_signatures_are_rejected(tmp_path, monkeypatch):
    secret = "actor-secret-that-is-at-least-32-bytes"
    monkeypatch.setenv("CATALOG_ACTOR_SIGNING_SECRET", secret)
    with client_for(tmp_path, monkeypatch) as client:
        path = "/api/v1/admin/patterns"
        created = client.post(path, headers=signed_headers("POST", path, secret=secret), json=sample(id="pat_actor_signed"))
        assert created.status_code == 201
        logs = client.get("/api/v1/admin/patterns/pat_actor_signed/audit-logs", headers={"X-Admin-Token": "test-token"}).json()
        assert logs[0]["actor"] == "operator-a"
        forged = signed_headers("POST", path, secret="wrong-secret-that-is-also-32-bytes")
        assert client.post(path, headers=forged, json=sample(id="pat_actor_forged")).status_code == 401
        expired = signed_headers("POST", path, timestamp=int(time.time()) - 301, secret=secret)
        assert client.post(path, headers=expired, json=sample(id="pat_actor_expired")).status_code == 401


def test_health(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        health = client.get("/health", headers={"X-Request-ID": "catalog-health-test"})
        assert health.json() == {"status": "ok"}
        assert health.headers["X-Request-ID"] == "catalog-health-test"
        ready = client.get("/ready")
        assert ready.json() == {"status": "ready", "database": "sqlite"}
        assert ready.headers["X-Request-ID"]


def test_production_rejects_default_admin_token(tmp_path, monkeypatch):
    monkeypatch.setenv("CATALOG_DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CATALOG_ENVIRONMENT", "production")
    monkeypatch.setenv("CATALOG_ADMIN_TOKEN", "dev-only-change-me")
    from app import main
    importlib.reload(main)
    try:
        with TestClient(main.app):
            pass
    except RuntimeError as exc:
        assert "must be overridden" in str(exc)
    else:
        raise AssertionError("production must reject the development admin token")


def test_public_list_hides_drafts_and_filters(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        headers = {"X-Admin-Token": "test-token"}
        assert client.post("/api/v1/admin/patterns", headers=headers, json=sample()).status_code == 201
        assert client.get("/api/v1/patterns").json()["total"] == 0
        approve(client, headers, "pat_cloud_001")
        response = client.post("/api/v1/admin/patterns/pat_cloud_001/publish", headers=headers)
        assert response.status_code == 200
        page = client.get("/api/v1/patterns?q=祥云&category=自然纹&pageSize=5").json()
        assert page["total"] == 1
        assert page["items"][0]["name"] == "祥云纹"
        assert page["items"][0]["source"]["system"] == "test"


def test_detail_is_public_only(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        headers = {"X-Admin-Token": "test-token"}
        client.post("/api/v1/admin/patterns", headers=headers, json=sample())
        assert client.get("/api/v1/patterns/pat_cloud_001").status_code == 404


def test_admin_token_and_safe_import(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        assert client.post("/api/v1/admin/patterns", json=sample()).status_code == 401
        payload = sample(id="pat_import_001", status="published", visibility="public")
        response = client.post("/api/v1/admin/patterns/import", headers={"X-Admin-Token": "test-token"}, json=[payload])
        assert response.status_code == 200
        assert response.json()[0]["status"] == "draft"
        assert response.json()[0]["visibility"] == "internal_only"
        assert client.get("/api/v1/patterns").json()["total"] == 0


def test_publish_rejects_rights_and_review_risks(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        headers = {"X-Admin-Token": "test-token"}
        blocked = sample(id="pat_blocked_001", rights={"status": "unverified"}, review={"issues": ["rights_unverified"]})
        assert client.post("/api/v1/admin/patterns", headers=headers, json=blocked).status_code == 201
        rejected = client.post("/api/v1/admin/patterns/pat_blocked_001/publish", headers=headers)
        assert rejected.status_code == 422
        assert rejected.json()["detail"]["code"] == "publish_validation_failed"
        crossed = client.patch("/api/v1/admin/patterns/pat_blocked_001", headers=headers, json={"visibility": "public"})
        assert crossed.status_code == 409
        assert crossed.json()["detail"]["code"] == "invalid_publication_transition"


def test_admin_filters_safe_publish_and_audit(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        headers = {"X-Admin-Token": "test-token"}
        client.post("/api/v1/admin/patterns", headers=headers, json=sample(id="pat_ready_001"))
        approve(client, headers, "pat_ready_001")
        ready = client.get("/api/v1/admin/patterns?status=draft&visibility=internal_only&risk=ready", headers=headers)
        assert ready.status_code == 200
        assert ready.json()["total"] == 1
        assert client.get("/api/v1/admin/patterns/pat_ready_001", headers=headers).status_code == 200
        published = client.post("/api/v1/admin/patterns/pat_ready_001/publish", headers=headers)
        assert published.status_code == 200
        assert published.json()["status"] == "published"
        assert published.json()["visibility"] == "public"
        logs = client.get("/api/v1/admin/patterns/pat_ready_001/audit-logs", headers=headers).json()
        assert [item["action"] for item in logs] == ["published", "review_approved", "review_assigned", "created"]


def test_batch_review_records_explicit_findings_without_changing_rights(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        headers = {"X-Admin-Token": "test-token"}
        client.post("/api/v1/admin/patterns", headers=headers, json=sample(id="pat_review_001", rights={"status": "unverified"}))
        response = client.post("/api/v1/admin/patterns/batch-review", headers=headers, json={"items": [
            {"patternId": "pat_review_001", "reviewedBy": "专家甲", "reviewedAt": "2026-09-04T09:00:00+08:00", "issues": ["版权材料待补"]},
            {"patternId": "pat_missing_001", "reviewedBy": "专家甲", "reviewedAt": "2026-09-04T09:00:00+08:00", "issues": []},
        ]})
        assert response.status_code == 200
        assert (response.json()["succeeded"], response.json()["failed"]) == (1, 1)
        reviewed = response.json()["items"][0]["pattern"]
        assert reviewed["review"]["issues"] == ["版权材料待补"]
        assert reviewed["rights"]["status"] == "unverified"
        logs = client.get("/api/v1/admin/patterns/pat_review_001/audit-logs", headers=headers).json()
        assert logs[0]["action"] == "reviewed"


def test_batch_publish_is_partial_retryable_and_syncs_ai(tmp_path, monkeypatch):
    monkeypatch.setenv("CATALOG_AI_INTERNAL_BASE_URL", "http://ai:8002/v1")
    monkeypatch.setenv("CATALOG_AI_SERVICE_TOKEN", "service-secret")
    with client_for(tmp_path, monkeypatch) as client:
        from app import main
        calls = []

        def fake_sync(pattern_id, published, settings):
            calls.append((pattern_id, published, settings.ai_service_token))
            if pattern_id == "pat_retry_001" and len([call for call in calls if call[0] == pattern_id]) == 1:
                raise main.AISyncError("temporary outage")
            return "synchronized"

        monkeypatch.setattr(main, "sync_publication", fake_sync)
        headers = {"X-Admin-Token": "test-token"}
        client.post("/api/v1/admin/patterns", headers=headers, json=sample(id="pat_ready_batch"))
        client.post("/api/v1/admin/patterns", headers=headers, json=sample(id="pat_blocked_batch", rights={"status": "unverified"}))
        client.post("/api/v1/admin/patterns", headers=headers, json=sample(id="pat_retry_001"))
        approve(client, headers, "pat_ready_batch")
        approve(client, headers, "pat_retry_001")

        first = client.post("/api/v1/admin/patterns/batch-publish", headers=headers, json={"patternIds": [
            "pat_ready_batch", "pat_blocked_batch", "pat_retry_001"
        ]}).json()
        assert (first["succeeded"], first["failed"]) == (1, 2)
        assert [item["code"] for item in first["items"]] == [None, "publish_validation_failed", "ai_sync_failed"]
        assert ("pat_blocked_batch", True, "service-secret") not in calls
        assert client.get("/api/v1/patterns/pat_retry_001").status_code == 404

        retry = client.post("/api/v1/admin/patterns/batch-publish", headers=headers, json={"patternIds": ["pat_retry_001"]}).json()
        assert retry["succeeded"] == 1
        assert client.get("/api/v1/patterns/pat_retry_001").status_code == 200
        logs = client.get("/api/v1/admin/patterns/pat_retry_001/audit-logs", headers=headers).json()
        assert [item["action"] for item in logs] == ["published", "publish_sync_failed", "review_approved", "review_assigned", "created"]


def test_patch_cannot_cross_publication_boundary_and_create_cannot_bypass_publish(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        headers = {"X-Admin-Token": "test-token"}
        bypass = client.post("/api/v1/admin/patterns", headers=headers, json=sample(
            id="pat_bypass_create", status="published", visibility="public"
        ))
        assert bypass.status_code == 409
        assert bypass.json()["detail"]["code"] == "invalid_publication_transition"
        client.post("/api/v1/admin/patterns", headers=headers, json=sample(id="pat_bypass_patch"))
        crossed = client.patch("/api/v1/admin/patterns/pat_bypass_patch", headers=headers, json={"status": "published", "visibility": "public"})
        assert crossed.status_code == 409
        assert crossed.json()["detail"]["code"] == "invalid_publication_transition"
        assert client.patch("/api/v1/admin/patterns/pat_bypass_patch", headers=headers, json={"status": "archived"}).status_code == 200


def test_publish_requires_approved_review_task(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        headers = {"X-Admin-Token": "test-token"}
        client.post("/api/v1/admin/patterns", headers=headers, json=sample(id="pat_needs_task"))
        response = client.post("/api/v1/admin/patterns/pat_needs_task/publish", headers=headers)
        assert response.status_code == 422
        assert "审核任务必须为 approved" in response.json()["detail"]["errors"]


def test_withdraw_syncs_ai_before_catalog_and_audits(tmp_path, monkeypatch):
    monkeypatch.setenv("CATALOG_AI_INTERNAL_BASE_URL", "http://ai:8002/v1")
    monkeypatch.setenv("CATALOG_AI_SERVICE_TOKEN", "service-secret")
    with client_for(tmp_path, monkeypatch) as client:
        from app import main
        calls = []
        monkeypatch.setattr(main, "sync_publication", lambda pattern_id, published, settings: calls.append((pattern_id, published)) or "synchronized")
        headers = {"X-Admin-Token": "test-token"}
        client.post("/api/v1/admin/patterns", headers=headers, json=sample(id="pat_withdraw_ok"))
        approve(client, headers, "pat_withdraw_ok")
        client.post("/api/v1/admin/patterns/pat_withdraw_ok/publish", headers=headers)
        withdrawn = client.post("/api/v1/admin/patterns/pat_withdraw_ok/withdraw", headers=headers)
        assert withdrawn.status_code == 200
        assert (withdrawn.json()["status"], withdrawn.json()["visibility"]) == ("draft", "internal_only")
        assert calls == [("pat_withdraw_ok", True), ("pat_withdraw_ok", False)]
        assert client.get("/api/v1/patterns/pat_withdraw_ok").status_code == 404
        logs = client.get("/api/v1/admin/patterns/pat_withdraw_ok/audit-logs", headers=headers).json()
        assert logs[0]["action"] == "withdrawn"


def test_withdraw_db_failure_compensates_ai(tmp_path, monkeypatch):
    monkeypatch.setenv("CATALOG_AI_INTERNAL_BASE_URL", "http://ai:8002/v1")
    monkeypatch.setenv("CATALOG_AI_SERVICE_TOKEN", "service-secret")
    with client_for(tmp_path, monkeypatch) as client:
        from app import main
        from app.db import Connection
        calls = []
        monkeypatch.setattr(main, "sync_publication", lambda pattern_id, published, settings: calls.append((pattern_id, published)) or "synchronized")
        headers = {"X-Admin-Token": "test-token"}
        client.post("/api/v1/admin/patterns", headers=headers, json=sample(id="pat_withdraw_compensate"))
        approve(client, headers, "pat_withdraw_compensate")
        client.post("/api/v1/admin/patterns/pat_withdraw_compensate/publish", headers=headers)
        original_execute = Connection.execute
        def fail_withdraw(connection, sql, params=()):
            if "SET status='draft', visibility='internal_only'" in sql:
                raise RuntimeError("database write failed")
            return original_execute(connection, sql, params)
        monkeypatch.setattr(Connection, "execute", fail_withdraw)
        with pytest.raises(RuntimeError, match="database write failed"):
            client.post("/api/v1/admin/patterns/pat_withdraw_compensate/withdraw", headers=headers)
        assert calls[-2:] == [("pat_withdraw_compensate", False), ("pat_withdraw_compensate", True)]


def test_admin_governance_stats_cover_status_rights_risks_ready_and_category_top(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        headers = {"X-Admin-Token": "test-token"}
        assert client.get("/api/v1/admin/patterns/stats").status_code == 401
        client.post("/api/v1/admin/patterns", headers=headers, json=sample(id="pat_stats_ready", category="几何纹"))
        approve(client, headers, "pat_stats_ready")
        client.post("/api/v1/admin/patterns", headers=headers, json=sample(
            id="pat_stats_risk", category="自然纹", rights={"status": "unverified"}, review={"issues": ["版权待核"]}
        ))
        client.post("/api/v1/admin/patterns", headers=headers, json=sample(id="pat_stats_archived", category="几何纹", status="archived"))
        stats = client.get("/api/v1/admin/patterns/stats?categoryTop=1", headers=headers)
        assert stats.status_code == 200
        assert stats.json() == {
            "total": 3,
            "statuses": {"draft": 2, "published": 0, "archived": 1},
            "rightsStatuses": {"verified": 2, "unverified": 1},
            "reviewRisk": {"hasIssues": 1, "rightsUnverified": 1},
            "ready": 1,
            "categories": [{"category": "几何纹", "count": 2}],
        }


def test_csv_export_reuses_filters_has_limit_and_prevents_formula_injection(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        headers = {"X-Admin-Token": "test-token"}
        client.post("/api/v1/admin/patterns", headers=headers, json=sample(
            id="pat_export_risk", name="=HYPERLINK(\"https://evil\")", meaning=" @SUM(1+1)",
            rights={"status": "unverified"}, review={"issues": ["=cmd"]},
        ))
        client.post("/api/v1/admin/patterns", headers=headers, json=sample(id="pat_export_safe"))
        assert client.get("/api/v1/admin/patterns/export.csv").status_code == 401
        response = client.get("/api/v1/admin/patterns/export.csv?risk=rights_unverified&limit=1", headers=headers)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert response.headers["content-disposition"] == 'attachment; filename="zhixiu-patterns.csv"'
        assert response.headers["x-exported-rows"] == "1"
        assert response.content.startswith(b"\xef\xbb\xbf")
        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
        assert len(rows) == 1
        assert rows[0]["id"] == "pat_export_risk"
        assert rows[0]["name"].startswith("'=")
        assert rows[0]["meaning"].startswith("'")
        assert rows[0]["reviewIssues"].startswith("[")  # JSON arrays are data, not executable formulas.
        assert client.get("/api/v1/admin/patterns/export.csv?limit=5001", headers=headers).status_code == 422


def test_evidence_update_merges_metadata_and_is_audited(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        headers = {"X-Admin-Token": "test-token"}
        client.post("/api/v1/admin/patterns", headers=headers, json=sample(
            id="pat_evidence_001", source={"system": "legacy", "legacyId": "42"},
            rights={"status": "unverified", "owner": "原权利人"},
        ))
        response = client.patch("/api/v1/admin/patterns/pat_evidence_001/evidence", headers=headers, json={
            "sourceDescription": "由传承人口述并经馆藏目录交叉核对",
            "originClaim": "四川阿坝",
            "rightsStatus": "verified",
            "rightsLicense": "CC BY-NC 4.0",
            "evidence": [{
                "id": "ev_001", "filename": "授权书.pdf", "contentType": "application/pdf",
                "sizeBytes": 2048, "storageKey": "evidence/pat_evidence_001/auth.pdf",
                "checksumSha256": "a" * 64,
            }],
            "verifiedBy": "专家甲", "verifiedAt": "2026-09-06T10:00:00+08:00",
            "verificationNote": "授权书信息一致", "reviewNote": "允许用于非商业展示",
        })
        assert response.status_code == 200
        item = response.json()
        assert item["source"]["system"] == "legacy"
        assert item["source"]["legacyId"] == "42"
        assert item["source"]["description"].startswith("由传承人")
        assert item["rights"]["owner"] == "原权利人"
        assert item["rights"]["evidence"][0]["storageKey"].startswith("evidence/")
        assert item["review"]["note"] == "允许用于非商业展示"
        logs = client.get("/api/v1/admin/patterns/pat_evidence_001/audit-logs", headers=headers).json()
        assert logs[0]["action"] == "evidence_updated"


def test_public_api_redacts_evidence_locations_and_internal_notes(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        headers = {"X-Admin-Token": "test-token"}
        payload = sample(id="pat_public_evidence")
        payload["rights"].update({
            "evidence": [{"id": "ev_secret", "filename": "授权书.pdf", "storageKey": "private/auth.pdf"}],
            "verificationNote": "身份证号等敏感信息已核验",
        })
        payload["review"] = {"issues": [], "note": "内部审核意见"}
        assert client.post("/api/v1/admin/patterns", headers=headers, json=payload).status_code == 201
        approve(client, headers, "pat_public_evidence")
        assert client.post("/api/v1/admin/patterns/pat_public_evidence/publish", headers=headers).status_code == 200
        admin = client.get("/api/v1/admin/patterns/pat_public_evidence", headers=headers).json()
        assert admin["rights"]["evidence"][0]["storageKey"] == "private/auth.pdf"
        public = client.get("/api/v1/patterns/pat_public_evidence").json()
        assert public["rights"]["evidence"] == []
        assert public["rights"]["verificationNote"] is None
        assert public["review"]["note"] is None


def test_evidence_validation_and_published_rights_regression_are_rejected(tmp_path, monkeypatch):
    with client_for(tmp_path, monkeypatch) as client:
        headers = {"X-Admin-Token": "test-token"}
        client.post("/api/v1/admin/patterns", headers=headers, json=sample(id="pat_verified_public"))
        approve(client, headers, "pat_verified_public")
        assert client.post("/api/v1/admin/patterns/pat_verified_public/publish", headers=headers).status_code == 200
        invalid = client.patch("/api/v1/admin/patterns/pat_verified_public/evidence", headers=headers, json={
            "evidence": [{"id": "x", "filename": "bad.pdf", "checksumSha256": "not-a-hash"}]
        })
        assert invalid.status_code == 422
        regression = client.patch("/api/v1/admin/patterns/pat_verified_public/evidence", headers=headers, json={
            "rightsStatus": "unverified"
        })
        assert regression.status_code == 422
        assert regression.json()["detail"]["code"] == "publish_validation_failed"


def test_real_evidence_upload_and_controlled_download(tmp_path, monkeypatch):
    from app.evidence_storage import StoredEvidence

    with client_for(tmp_path, monkeypatch) as client:
        from app import main
        headers = {"X-Admin-Token": "test-token"}
        assert client.post("/api/v1/admin/patterns", headers=headers, json=sample(id="pat_file_001")).status_code == 201

        async def fake_store(pattern_id, upload, settings):
            assert pattern_id == "pat_file_001"
            assert await upload.read() == b"%PDF-test"
            return StoredEvidence("ev_file_001", "auth.pdf", "application/pdf", 9,
                                  "test/catalog-evidence/pat_file_001/ev_file_001.pdf", "a" * 64)

        class Body:
            def iter_chunks(self, chunk_size):
                yield b"%PDF-test"

        monkeypatch.setattr(main, "store_upload", fake_store)
        monkeypatch.setattr(main, "fetch_object", lambda key, settings: {"Body": Body(), "ContentLength": 9})
        response = client.post(
            "/api/v1/admin/patterns/pat_file_001/evidence-files", headers=headers,
            files={"file": ("auth.pdf", b"%PDF-test", "application/pdf")},
        )
        assert response.status_code == 200
        evidence = response.json()["rights"]["evidence"][0]
        assert evidence["id"] == "ev_file_001"
        assert evidence["checksumSha256"] == "a" * 64
        assert client.get("/api/v1/admin/patterns/pat_file_001/evidence-files/ev_file_001").status_code == 401
        downloaded = client.get("/api/v1/admin/patterns/pat_file_001/evidence-files/ev_file_001", headers=headers)
        assert downloaded.status_code == 200
        assert downloaded.content == b"%PDF-test"
        assert downloaded.headers["cache-control"] == "private, no-store"
        assert downloaded.headers["x-checksum-sha256"] == "a" * 64
        logs = client.get("/api/v1/admin/patterns/pat_file_001/audit-logs", headers=headers).json()
        assert logs[0]["action"] == "evidence_file_uploaded"
