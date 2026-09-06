import json

from app import bulk_index


class FakeResponse:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {}
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise RuntimeError(self.error)

    def json(self):
        return self.payload


class FakeClient:
    registrations = []
    registration_headers = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, path, files=None, json=None, headers=None):
        if path == "/v1/assets":
            filename = files["image"][0]
            if filename == "bad.png":
                return FakeResponse(error="upload rejected")
            return FakeResponse({"id": f"asset-{filename}"})
        self.registrations.append(json)
        self.registration_headers.append(headers)
        return FakeResponse(json)


def test_bulk_import_is_safe_idempotent_and_reports_failures(tmp_path, monkeypatch):
    good = tmp_path / "good.png"
    bad = tmp_path / "bad.png"
    good.write_bytes(b"good")
    bad.write_bytes(b"bad")
    manifest = tmp_path / "asset_manifest.json"
    manifest.write_text(json.dumps({"records": [
        {"pattern_id": "p1", "candidate_name": "候选一", "local_path": str(good)},
        {"pattern_id": "p2", "candidate_name": "候选二", "local_path": str(bad)},
    ]}), encoding="utf-8")
    FakeClient.registrations = []
    FakeClient.registration_headers = []
    monkeypatch.setattr(bulk_index.httpx, "Client", FakeClient)

    first = bulk_index.import_manifest(manifest, "http://test", "internal-test-token")
    second = bulk_index.import_manifest(manifest, "http://test", "internal-test-token")
    assert (first["succeeded"], first["failed"]) == (1, 1)
    assert (second["succeeded"], second["failed"]) == (1, 1)
    assert all(item["asset_id"] == "asset-good.png" for item in first["items"] if item["status"] == "succeeded")
    assert FakeClient.registrations[0] == {
        "asset_id": "asset-good.png", "pattern_id": "p1", "label": "候选一",
        "review_status": "draft", "visibility": "internal_only",
    }
    assert FakeClient.registration_headers[0] == {"X-Service-Token": "internal-test-token"}


def test_bulk_import_requires_service_token(tmp_path):
    manifest = tmp_path / "asset_manifest.json"
    manifest.write_text("[]", encoding="utf-8")
    try:
        bulk_index.import_manifest(manifest, "http://test", "")
    except ValueError as exc:
        assert "service token" in str(exc)
    else:
        raise AssertionError("missing service token must be rejected")
