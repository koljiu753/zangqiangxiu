import hashlib
import io

from PIL import Image

INTERNAL_HEADERS = {"X-Service-Token": "test-internal-token"}


def image_bytes(colors=((255, 0, 0), (0, 0, 255))) -> bytes:
    image = Image.new("RGB", (100, 100), colors[0])
    for x in range(50, 100):
        for y in range(100):
            image.putpixel((x, y), colors[1])
    output = io.BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def upload(client, name, colors):
    return client.post(
        "/v1/assets", files={"image": (name, image_bytes(colors), "image/png")}
    ).json()

def capability(asset):
    return {"X-Asset-Capability": asset["capability_token"]}


def test_health(client):
    health = client.get("/health", headers={"X-Request-ID": "ai-health-test"})
    assert health.json() == {"status": "ok", "database": "ok"}
    assert health.headers["X-Request-ID"] == "ai-health-test"
    ready = client.get("/ready")
    assert ready.json() == {
        "status": "ready", "database": "sqlite", "asset_store": "local"
    }
    assert ready.headers["X-Request-ID"]


def test_capabilities_report_only_real_available_features(client):
    capabilities = client.get("/v1/capabilities").json()
    assert capabilities["embedding"] == {
        "available": True,
        "provider": "zhixiu-interpretable-image-feature",
        "model_version": "interpretable-rgbhist4-gray8-v1",
        "semantic": False,
        "dimensions": 128,
    }
    assert capabilities["classification"]["available"] is False
    assert capabilities["generation"]["available"] is False
    assert capabilities["generation"]["api_exposed"] is False


def test_upload_is_validated_hashed_and_deduplicated(client):
    data = image_bytes()
    first = client.post("/v1/assets", files={"image": ("cloth.png", data, "image/png")})
    assert first.status_code == 201
    assert first.json()["sha256"] == hashlib.sha256(data).hexdigest()
    assert (first.json()["width"], first.json()["height"]) == (100, 100)
    second = client.post("/v1/assets", files={"image": ("copy.png", data, "image/png")})
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]


def test_rejects_non_image(client):
    response = client.post("/v1/assets", files={"image": ("bad.png", b"not an image", "image/png")})
    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "INVALID_IMAGE"


def test_real_palette_embedding_and_unconfigured_classification_provider(client):
    uploaded = client.post("/v1/assets", files={"image": ("two.png", image_bytes(), "image/png")}).json()
    created = client.post("/v1/analyses", headers=capability(uploaded), json={
        "asset_id": uploaded["id"], "tasks": ["palette", "embedding", "classification"], "palette_colors": 2
    })
    assert created.status_code == 202
    job = client.get(f"/v1/jobs/{created.json()['id']}", headers=capability(uploaded)).json()
    assert job["status"] == "succeeded"
    result = client.get(f"/v1/analyses/{job['result_id']}", headers=capability(uploaded)).json()
    assert {color["hex"] for color in result["palette"]} == {"#FF0000", "#0000FF"}
    assert abs(sum(color["ratio"] for color in result["palette"]) - 1) < 0.001
    assert result["embedding"]["status"] == "succeeded"
    assert result["embedding"]["provider"] == "zhixiu-interpretable-image-feature"
    assert result["embedding"]["model_version"] == "interpretable-rgbhist4-gray8-v1"
    assert len(result["embedding"]["data"]) == 128
    assert result["classification"]["status"] == "unavailable"
    assert result["classification"]["data"] is None


def test_unknown_asset_and_openapi(client):
    assert client.post("/v1/analyses", json={"asset_id": "missing", "tasks": ["palette"]}).status_code == 401
    schema = client.get("/openapi.json").json()
    assert "/v1/assets" in schema["paths"]
    assert "/v1/analyses/{result_id}" in schema["paths"]


def test_similarity_index_returns_dynamic_ranked_results(client):
    red = upload(client, "red.png", ((255, 0, 0), (220, 0, 0)))
    blue = upload(client, "blue.png", ((0, 0, 255), (0, 0, 220)))
    green = upload(client, "green.png", ((0, 255, 0), (0, 220, 0)))
    query_red = upload(client, "query-red.png", ((250, 5, 5), (210, 5, 5)))
    query_blue = upload(client, "query-blue.png", ((5, 5, 250), (5, 5, 210)))

    for asset, label in ((red, "red reference"), (blue, "blue reference"), (green, "green reference")):
        response = client.post("/v1/references", headers=INTERNAL_HEADERS, json={
            "asset_id": asset["id"], "label": label, "pattern_id": f"pattern-{label}",
            "review_status": "draft", "visibility": "internal_only"
        })
        assert response.status_code == 201
        assert response.json()["feature_dimensions"] == 128
        assert response.json()["algorithm_version"] == "interpretable-rgbhist4-gray8-v1"

    def analyze(asset_id):
        created = client.post("/v1/analyses", headers=INTERNAL_HEADERS, json={
            "asset_id": asset_id, "tasks": ["similar"], "top_k": 2, "scope": "internal"
        })
        job = client.get(f"/v1/jobs/{created.json()['id']}", headers=INTERNAL_HEADERS).json()
        return client.get(f"/v1/analyses/{job['result_id']}", headers=INTERNAL_HEADERS).json()

    red_result = analyze(query_red["id"])
    blue_result = analyze(query_blue["id"])
    assert red_result["similar"][0]["asset_id"] == red["id"]
    assert red_result["similar"][0]["pattern_id"] == "pattern-red reference"
    assert blue_result["similar"][0]["asset_id"] == blue["id"]
    assert red_result["similar"] != blue_result["similar"]
    assert red_result["similar"][0]["score"] > red_result["similar"][1]["score"]
    assert red_result["similarity_algorithm_version"] == "interpretable-rgbhist4-gray8-v1"


def test_configurable_cors(client):
    response = client.options(
        "/v1/assets",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_public_scope_excludes_internal_and_unapproved_references(client):
    internal = upload(client, "internal.png", ((255, 0, 0), (220, 0, 0)))
    public_draft = upload(client, "draft.png", ((0, 255, 0), (0, 220, 0)))
    public_approved = upload(client, "approved.png", ((0, 0, 255), (0, 0, 220)))
    query = upload(client, "query.png", ((5, 5, 250), (5, 5, 210)))
    for asset, review_status, visibility, pattern_id in (
        (internal, "draft", "internal_only", "p-internal"),
        (public_draft, "draft", "public", "p-draft"),
        (public_approved, "approved", "public", "p-approved"),
    ):
        assert client.post("/v1/references", headers=INTERNAL_HEADERS, json={
            "asset_id": asset["id"], "pattern_id": pattern_id,
            "review_status": review_status, "visibility": visibility,
        }).status_code == 201

    created = client.post("/v1/analyses", headers=capability(query), json={
        "asset_id": query["id"], "tasks": ["similar"]
    }).json()
    job = client.get(f"/v1/jobs/{created['id']}", headers=capability(query)).json()
    result = client.get(f"/v1/analyses/{job['result_id']}", headers=capability(query)).json()
    assert [match["pattern_id"] for match in result["similar"]] == ["p-approved"]


def test_reference_lookup_and_asset_content_enforce_visibility(client):
    internal = upload(client, "internal.png", ((255, 0, 0), (220, 0, 0)))
    public = upload(client, "public.png", ((0, 0, 255), (0, 0, 220)))
    assert client.post("/v1/references", headers=INTERNAL_HEADERS, json={
        "asset_id": internal["id"], "pattern_id": "p-internal",
        "review_status": "draft", "visibility": "internal_only",
    }).status_code == 201
    assert client.post("/v1/references", headers=INTERNAL_HEADERS, json={
        "asset_id": public["id"], "pattern_id": "p-public",
        "review_status": "approved", "visibility": "public",
    }).status_code == 201

    assert client.get("/v1/references/by-pattern/p-internal").status_code == 404
    assert client.get(f"/v1/assets/{internal['id']}/content").status_code == 404
    assert client.get("/v1/references/by-pattern/p-internal?scope=internal").status_code == 401
    headers = {"X-Service-Token": "test-internal-token"}
    mapping = client.get("/v1/references/by-pattern/p-internal?scope=internal", headers=headers)
    assert mapping.status_code == 200
    assert mapping.json()["asset_id"] == internal["id"]
    assert mapping.json()["content_url"].endswith("?scope=internal")

    original = client.get(f"/v1/assets/{internal['id']}/content?scope=internal", headers=headers)
    assert original.status_code == 200
    assert original.headers["content-type"] == "image/png"
    assert original.headers["cache-control"] == "private, no-store"
    thumbnail = client.get(f"/v1/assets/{internal['id']}/content?scope=internal&thumbnail=64", headers=headers)
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"] == "image/webp"
    with Image.open(io.BytesIO(thumbnail.content)) as image:
        assert max(image.size) <= 64

    public_mapping = client.get("/v1/references/by-pattern/p-public")
    assert public_mapping.status_code == 200
    public_image = client.get(public_mapping.json()["thumbnail_url"])
    assert public_image.status_code == 200
    assert public_image.headers["cache-control"] == "public, max-age=3600"


def test_reference_list_defaults_to_public_and_internal_requires_token(client):
    internal = upload(client, "list-internal.png", ((255, 0, 0), (220, 0, 0)))
    public = upload(client, "list-public.png", ((0, 0, 255), (0, 0, 220)))
    for asset, review_status, visibility in (
        (internal, "draft", "internal_only"), (public, "approved", "public")
    ):
        assert client.post("/v1/references", headers=INTERNAL_HEADERS, json={
            "asset_id": asset["id"], "pattern_id": f"pattern-{asset['id']}",
            "review_status": review_status, "visibility": visibility,
        }).status_code == 201
    assert [item["asset_id"] for item in client.get("/v1/references").json()] == [public["id"]]
    assert client.get("/v1/references?scope=internal").status_code == 401
    response = client.get("/v1/references?scope=internal",
                          headers={"X-Service-Token": "test-internal-token"})
    assert {item["asset_id"] for item in response.json()} == {internal["id"], public["id"]}


def test_public_cannot_register_or_self_publish_reference(client):
    asset = upload(client, "untrusted-reference.png", ((200, 30, 30), (180, 20, 20)))
    payload = {
        "asset_id": asset["id"],
        "pattern_id": "untrusted-pattern",
        "review_status": "approved",
        "visibility": "public",
    }
    unauthorized = client.post("/v1/references", json=payload)
    assert unauthorized.status_code == 401
    assert client.app.state.storage.one(
        "SELECT asset_id FROM reference_assets WHERE asset_id = ?", (asset["id"],)
    ) is None
    assert client.post("/v1/references", headers=INTERNAL_HEADERS, json=payload).status_code == 201


def test_internal_analysis_creation_job_and_result_require_token(client):
    asset = upload(client, "private-analysis.png", ((30, 30, 200), (20, 20, 180)))
    payload = {"asset_id": asset["id"], "tasks": ["embedding"], "scope": "internal"}
    assert client.post("/v1/analyses", json=payload).status_code == 401

    created = client.post("/v1/analyses", headers=INTERNAL_HEADERS, json=payload)
    assert created.status_code == 202
    job_id = created.json()["id"]
    assert client.get(f"/v1/jobs/{job_id}").status_code == 401
    protected_job = client.get(f"/v1/jobs/{job_id}", headers=INTERNAL_HEADERS)
    assert protected_job.status_code == 200
    result_id = protected_job.json()["result_id"]
    assert client.get(f"/v1/analyses/{result_id}").status_code == 401
    assert client.get(f"/v1/analyses/{result_id}", headers=INTERNAL_HEADERS).status_code == 200


def test_internal_publication_sync_is_authorized_idempotent_and_reversible(client):
    asset = upload(client, "publication.png", ((180, 20, 20), (160, 10, 10)))
    assert client.post("/v1/references", headers=INTERNAL_HEADERS, json={
        "asset_id": asset["id"], "pattern_id": "pattern-publication",
    }).status_code == 201
    path = "/v1/internal/references/by-pattern/pattern-publication/publication"
    headers = {"X-Service-Token": "test-internal-token"}

    assert client.put(path, json={"published": True}).status_code == 401
    missing = client.put(
        "/v1/internal/references/by-pattern/missing/publication",
        headers=headers, json={"published": True},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "REFERENCE_NOT_FOUND"

    first = client.put(path, headers=headers, json={"published": True})
    second = client.put(path, headers=headers, json={"published": True})
    assert first.status_code == second.status_code == 200
    assert first.json()["review_status"] == second.json()["review_status"] == "approved"
    assert first.json()["visibility"] == second.json()["visibility"] == "public"
    assert client.get("/v1/references/by-pattern/pattern-publication").status_code == 200

    withdrawn = client.put(path, headers=headers, json={"published": False})
    assert withdrawn.status_code == 200
    assert withdrawn.json()["review_status"] == "draft"
    assert withdrawn.json()["visibility"] == "internal_only"
    assert "scope=internal" in withdrawn.json()["thumbnail_url"]
    assert client.get("/v1/references/by-pattern/pattern-publication").status_code == 404


def test_failed_job_can_be_authorized_and_idempotently_retried(client):
    asset = upload(client, "retry.png", ((90, 10, 10), (80, 5, 5)))
    storage = client.app.state.storage
    original = storage.one("SELECT storage_path FROM assets WHERE id = ?", (asset["id"],))["storage_path"]
    storage.execute("UPDATE assets SET storage_path = ? WHERE id = ?", ("missing.png", asset["id"]))
    created = client.post("/v1/analyses", headers=capability(asset), json={"asset_id": asset["id"], "tasks": ["palette"]})
    job_id = created.json()["id"]
    assert client.get(f"/v1/jobs/{job_id}", headers=capability(asset)).json()["status"] == "failed"

    retry_path = f"/v1/internal/jobs/{job_id}/retry"
    assert client.post(retry_path).status_code == 401
    storage.execute("UPDATE assets SET storage_path = ? WHERE id = ?", (original, asset["id"]))
    retried = client.post(retry_path, headers={"X-Service-Token": "test-internal-token"})
    assert retried.status_code == 200
    assert client.get(f"/v1/jobs/{job_id}", headers=capability(asset)).json()["status"] == "succeeded"
    repeated = client.post(retry_path, headers={"X-Service-Token": "test-internal-token"})
    assert repeated.status_code == 200
    assert repeated.json()["status"] == "succeeded"


def test_job_stats_are_internal_and_include_all_states(client):
    path = "/v1/internal/jobs/stats"
    assert client.get(path).status_code == 401
    response = client.get(path, headers={"X-Service-Token": "test-internal-token"})
    assert response.status_code == 200
    assert set(response.json()["jobs"]) == {"pending", "running", "succeeded", "failed"}
    assert isinstance(response.json()["recovered_on_startup"], int)


def test_interrupted_job_is_recovered_from_persistent_state(client):
    from app.main import recover_interrupted_jobs

    asset = upload(client, "recover.png", ((20, 120, 20), (10, 100, 10)))
    created = client.post("/v1/analyses", headers=capability(asset), json={"asset_id": asset["id"], "tasks": ["embedding"]})
    job_id = created.json()["id"]
    storage = client.app.state.storage
    result_id = client.get(f"/v1/jobs/{job_id}", headers=capability(asset)).json()["result_id"]
    storage.execute("DELETE FROM analysis_results WHERE id = ?", (result_id,))
    storage.execute(
        "UPDATE jobs SET status='running', progress=40, result_id=NULL WHERE id = ?", (job_id,)
    )

    assert recover_interrupted_jobs(client.app) == 1
    recovered = client.get(f"/v1/jobs/{job_id}", headers=capability(asset)).json()
    assert recovered["status"] == "succeeded"
    result = client.get(f"/v1/analyses/{recovered['result_id']}", headers=capability(asset)).json()
    assert result["embedding"]["model_version"] == "interpretable-rgbhist4-gray8-v1"
