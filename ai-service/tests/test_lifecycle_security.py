import hashlib

from fastapi.testclient import TestClient

from test_api import INTERNAL_HEADERS, capability, image_bytes, upload


def test_capability_is_only_returned_raw_and_protects_metadata_job_and_result(client):
    asset = upload(client, "private.png", ((1, 2, 3), (4, 5, 6)))
    assert len(asset["capability_token"]) >= 32
    stored = client.app.state.storage.one(
        "SELECT token_hash FROM asset_capabilities WHERE asset_id=?", (asset["id"],)
    )["token_hash"]
    assert stored == hashlib.sha256(asset["capability_token"].encode()).hexdigest()
    assert stored != asset["capability_token"]
    assert client.get(f"/v1/assets/{asset['id']}").status_code == 401
    assert client.get(f"/v1/assets/{asset['id']}", headers=capability(asset)).status_code == 200
    created = client.post("/v1/analyses", headers=capability(asset), json={
        "asset_id": asset["id"], "tasks": ["palette"]
    })
    assert created.status_code == 202
    job_id = created.json()["id"]
    assert client.get(f"/v1/jobs/{job_id}").status_code == 401
    job = client.get(f"/v1/jobs/{job_id}", headers=capability(asset)).json()
    assert client.get(f"/v1/analyses/{job['result_id']}").status_code == 401
    assert client.get(f"/v1/analyses/{job['result_id']}", headers=INTERNAL_HEADERS).status_code == 200


def test_delete_cascades_and_reference_assets_are_protected(client):
    asset = upload(client, "delete.png", ((11, 12, 13), (14, 15, 16)))
    created = client.post("/v1/analyses", headers=capability(asset), json={
        "asset_id": asset["id"], "tasks": ["palette"]
    }).json()
    result_id = client.get(f"/v1/jobs/{created['id']}", headers=capability(asset)).json()["result_id"]
    assert client.delete(f"/v1/assets/{asset['id']}", headers=capability(asset)).status_code == 200
    assert client.app.state.storage.one("SELECT id FROM assets WHERE id=?", (asset["id"],)) is None
    assert client.app.state.storage.one("SELECT id FROM jobs WHERE id=?", (created["id"],)) is None
    assert client.app.state.storage.one("SELECT id FROM analysis_results WHERE id=?", (result_id,)) is None

    reference = upload(client, "reference.png", ((21, 22, 23), (24, 25, 26)))
    assert client.post("/v1/references", headers=INTERNAL_HEADERS,
                       json={"asset_id": reference["id"]}).status_code == 201
    assert client.delete(f"/v1/assets/{reference['id']}", headers=capability(reference)).status_code == 409
    assert client.delete(f"/v1/assets/{reference['id']}", headers=INTERNAL_HEADERS).status_code == 200


def test_cleanup_is_internal_dry_run_then_execute(client):
    asset = upload(client, "expired.png", ((31, 32, 33), (34, 35, 36)))
    client.app.state.storage.execute(
        "UPDATE assets SET created_at='2000-01-01T00:00:00+00:00' WHERE id=?", (asset["id"],)
    )
    assert client.post("/v1/internal/cleanup").status_code == 401
    dry = client.post("/v1/internal/cleanup?dry_run=true", headers=INTERNAL_HEADERS).json()
    assert dry["matched"] == 1 and dry["deleted"] == 0
    done = client.post("/v1/internal/cleanup?dry_run=false", headers=INTERNAL_HEADERS).json()
    assert done["deleted"] == 1


def test_anonymous_upload_rate_limit_returns_retry_after(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIXIU_AI_DATA_DIR", str(tmp_path / "limited"))
    monkeypatch.setenv("ZHIXIU_AI_INTERNAL_TOKEN", "test-internal-token")
    monkeypatch.setenv("ZHIXIU_AI_ANON_UPLOADS_PER_MINUTE", "1")
    from app.main import app
    with TestClient(app) as limited:
        assert limited.post("/v1/assets", files={"image": ("one.png", image_bytes(), "image/png")}).status_code == 201
        denied = limited.post("/v1/assets", files={"image": ("two.png", image_bytes(((1,1,1),(2,2,2))), "image/png")})
        assert denied.status_code == 429
        assert int(denied.headers["Retry-After"]) >= 1


def test_analysis_rate_limit_and_queue_capacity(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIXIU_AI_DATA_DIR", str(tmp_path / "analysis-limited"))
    monkeypatch.setenv("ZHIXIU_AI_INTERNAL_TOKEN", "test-internal-token")
    monkeypatch.setenv("ZHIXIU_AI_ANON_ANALYSES_PER_MINUTE", "1")
    monkeypatch.setenv("ZHIXIU_AI_MAX_QUEUED_JOBS", "1")
    from app.main import app
    with TestClient(app) as limited:
        asset = upload(limited, "analysis.png", ((41, 42, 43), (44, 45, 46)))
        first = limited.post("/v1/analyses", headers=capability(asset), json={
            "asset_id": asset["id"], "tasks": ["palette"]
        })
        assert first.status_code == 202
        denied = limited.post("/v1/analyses", headers=capability(asset), json={
            "asset_id": asset["id"], "tasks": ["palette"]
        })
        assert denied.status_code == 429 and "Retry-After" in denied.headers

        # Internal calls bypass the anonymous rate bucket, but not global queue pressure.
        limited.app.state.storage.execute(
            "UPDATE jobs SET status='pending' WHERE id=?", (first.json()["id"],)
        )
        full = limited.post("/v1/analyses", headers=INTERNAL_HEADERS, json={
            "asset_id": asset["id"], "tasks": ["palette"], "scope": "internal"
        })
        assert full.status_code == 429
        assert full.json()["detail"]["code"] == "QUEUE_FULL"
