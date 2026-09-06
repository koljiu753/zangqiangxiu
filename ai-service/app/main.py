import hashlib
import hmac
import io
import json
import logging
import secrets
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageOps, UnidentifiedImageError

from .asset_store import create_asset_store
from .config import get_settings, validate_settings
from .palette import extract_palette
from .providers import (
    InterpretableEmbeddingProvider,
    ProviderNotConfigured,
    UnconfiguredClassificationProvider,
    UnconfiguredEmbeddingProvider,
    UnconfiguredGenerationProvider,
)
from .schemas import (
    AnalysisCreate, AnalysisResultResponse, AnalysisTask, AssetResponse, HealthResponse, JobResponse,
    ReferenceCreate, ReferencePublicationUpdate, ReferenceResponse, SearchScope,
)
from .similarity import ALGORITHM_VERSION, extract_feature, similarity
from .storage import create_storage, decode_job, utcnow

ALLOWED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
logger = logging.getLogger(__name__)
_rate_lock = threading.Lock()
_rate_windows: dict[tuple[str, str], tuple[int, int]] = {}


def _is_internal(request: Request, token: str | None) -> bool:
    expected = request.app.state.settings.internal_token
    return bool(expected and token and hmac.compare_digest(token, expected))


def _capability_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def require_asset_access(request: Request, asset_id: str, capability: str | None,
                         service_token: str | None) -> None:
    if _is_internal(request, service_token):
        return
    if not capability or not request.app.state.storage.one(
        "SELECT token_hash FROM asset_capabilities WHERE asset_id=? AND token_hash=?",
        (asset_id, _capability_hash(capability)),
    ):
        raise HTTPException(401, detail={"code": "INVALID_CAPABILITY_TOKEN",
                                         "message": "A valid asset capability token is required"})


def enforce_rate_limit(request: Request, bucket: str, limit: int) -> None:
    if limit == 0:
        raise HTTPException(429, detail={"code": "RATE_LIMITED", "message": "Anonymous access is disabled"},
                            headers={"Retry-After": "60"})
    now, window = int(time.time()), int(time.time()) // 60
    client = request.client.host if request.client else "unknown"
    key = (bucket, client)
    with _rate_lock:
        old_window, count = _rate_windows.get(key, (window, 0))
        if old_window != window:
            count = 0
        if count >= limit:
            retry = max(1, 60 - now % 60)
            raise HTTPException(429, detail={"code": "RATE_LIMITED", "message": "Rate limit exceeded"},
                                headers={"Retry-After": str(retry)})
        _rate_windows[key] = (window, count + 1)


def require_internal_access(request: Request, token: str | None) -> None:
    expected = request.app.state.settings.internal_token
    if not expected:
        raise HTTPException(503, detail={"code": "INTERNAL_ACCESS_NOT_CONFIGURED",
                                         "message": "Internal asset access is not configured"})
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(401, detail={"code": "INVALID_SERVICE_TOKEN",
                                         "message": "A valid service token is required"})


def reference_response(row: dict) -> ReferenceResponse:
    asset_id = row["asset_id"]
    return ReferenceResponse(
        asset_id=asset_id, label=row["label"], pattern_id=row["pattern_id"],
        review_status=row["review_status"], visibility=row["visibility"],
        algorithm_version=row["algorithm_version"],
        feature_dimensions=len(json.loads(row["feature"])), created_at=row["created_at"],
        content_url=f"/v1/assets/{asset_id}/content",
        thumbnail_url=f"/v1/assets/{asset_id}/content?thumbnail=480",
    )


def accessible_reference(storage, asset_id: str, scope: SearchScope) -> dict | None:
    if scope == SearchScope.internal:
        return storage.one("SELECT * FROM reference_assets WHERE asset_id = ?", (asset_id,))
    return storage.one(
        """SELECT * FROM reference_assets WHERE asset_id = ?
           AND review_status = 'approved' AND visibility = 'public'""", (asset_id,),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    validate_settings(settings)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    asset_root = settings.data_dir / ("cache" if settings.asset_backend == "s3" else "uploads")
    asset_store = create_asset_store(settings.asset_backend, asset_root,
                                     bucket=settings.s3_bucket, prefix=settings.s3_prefix,
                                     endpoint_url=settings.s3_endpoint_url, region=settings.s3_region)
    asset_store.initialize()
    storage = create_storage(settings.database_backend, settings.data_dir / "ai-service.sqlite3",
                             settings.database_url)
    storage.initialize()
    app.state.settings = settings
    app.state.storage = storage
    app.state.asset_store = asset_store
    app.state.embedding_provider = InterpretableEmbeddingProvider()
    app.state.classification_provider = UnconfiguredClassificationProvider()
    app.state.generation_provider = UnconfiguredGenerationProvider()
    app.state.recovered_jobs = recover_interrupted_jobs(app)
    with _rate_lock:
        _rate_windows.clear()
    yield


app = FastAPI(
    title="Zhixiu AI Service",
    version="0.1.0",
    description="Real image ingestion and analysis task service. Optional model providers fail explicitly when unconfigured.",
    lifespan=lifespan,
)
_initial_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_initial_settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Idempotency-Key", "X-Service-Token", "X-Asset-Capability"],
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health(request: Request) -> HealthResponse:
    request.app.state.storage.one("SELECT 1 AS ok")
    return HealthResponse(status="ok", database="ok")


@app.get("/ready", tags=["system"])
def ready(request: Request) -> dict[str, str]:
    request.app.state.storage.check()
    request.app.state.asset_store.check()
    return {
        "status": "ready",
        "database": request.app.state.storage.backend,
        "asset_store": request.app.state.asset_store.backend,
    }


@app.get("/v1/capabilities", tags=["system"])
def capabilities(request: Request) -> dict:
    """Describe actual provider availability without claiming unsupported model output."""
    embedding = request.app.state.embedding_provider
    classification = request.app.state.classification_provider
    generation = request.app.state.generation_provider
    return {
        "embedding": {
            "available": not isinstance(embedding, UnconfiguredEmbeddingProvider),
            "provider": embedding.name,
            "model_version": embedding.model_version,
            "semantic": embedding.semantic,
            "dimensions": embedding.dimensions,
        },
        "classification": {
            "available": not isinstance(classification, UnconfiguredClassificationProvider),
            "provider": classification.name,
            "model_version": classification.model_version,
        },
        "generation": {
            "available": not isinstance(generation, UnconfiguredGenerationProvider),
            "provider": generation.name,
            "model_version": generation.model_version,
            "api_exposed": False,
        },
    }


@app.post("/v1/assets", response_model=AssetResponse, status_code=status.HTTP_201_CREATED, tags=["assets"])
async def upload_asset(request: Request, image: UploadFile = File(...),
                       service_token: str | None = Header(default=None, alias="X-Service-Token")) -> AssetResponse:
    settings = request.app.state.settings
    if not _is_internal(request, service_token):
        enforce_rate_limit(request, "upload", settings.anonymous_uploads_per_minute)
    data = await image.read(settings.max_upload_bytes + 1)
    if not data:
        raise HTTPException(400, detail={"code": "EMPTY_FILE", "message": "Image is empty"})
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, detail={"code": "FILE_TOO_LARGE", "message": "Image exceeds upload limit"})
    try:
        with Image.open(io.BytesIO(data)) as parsed:
            parsed.verify()
        with Image.open(io.BytesIO(data)) as parsed:
            image_format = parsed.format
            width, height = parsed.size
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(415, detail={"code": "INVALID_IMAGE", "message": "Unsupported or corrupt image"})
    if image_format not in ALLOWED_FORMATS:
        raise HTTPException(415, detail={"code": "UNSUPPORTED_IMAGE_FORMAT", "message": "Only JPEG, PNG and WebP are accepted"})
    if width * height > settings.max_image_pixels:
        raise HTTPException(413, detail={"code": "TOO_MANY_PIXELS", "message": "Image dimensions exceed safety limit"})

    digest = hashlib.sha256(data).hexdigest()
    storage: Storage = request.app.state.storage
    existing = storage.one("SELECT * FROM assets WHERE sha256 = ?", (digest,))
    capability = secrets.token_urlsafe(32)
    if existing:
        storage.execute("INSERT INTO asset_capabilities(token_hash,asset_id,created_at) VALUES (?,?,?)",
                        (_capability_hash(capability), existing["id"], utcnow()))
        return AssetResponse(**existing, capability_token=capability)

    asset_id = str(uuid.uuid4())
    storage_path = request.app.state.asset_store.put(f"{asset_id}{EXTENSIONS[image_format]}", data)
    created_at = utcnow()
    content_type = ALLOWED_FORMATS[image_format]
    filename = Path(image.filename or f"upload{EXTENSIONS[image_format]}").name
    storage.execute(
        "INSERT INTO assets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (asset_id, digest, filename, content_type, width, height, len(data), storage_path, created_at),
    )
    storage.execute("INSERT INTO asset_capabilities(token_hash,asset_id,created_at) VALUES (?,?,?)",
                    (_capability_hash(capability), asset_id, created_at))
    return AssetResponse(id=asset_id, sha256=digest, filename=filename, content_type=content_type,
                         width=width, height=height, byte_size=len(data), created_at=created_at,
                         capability_token=capability)


@app.get("/v1/assets/{asset_id}", response_model=AssetResponse, tags=["assets"])
def get_asset(asset_id: str, request: Request,
              capability: str | None = Header(default=None, alias="X-Asset-Capability"),
              service_token: str | None = Header(default=None, alias="X-Service-Token")) -> AssetResponse:
    row = request.app.state.storage.one("SELECT * FROM assets WHERE id = ?", (asset_id,))
    if not row:
        raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND", "message": "Asset not found"})
    require_asset_access(request, asset_id, capability, service_token)
    return AssetResponse(**row)


@app.get("/v1/assets/{asset_id}/content", tags=["assets"])
def get_asset_content(
    asset_id: str,
    request: Request,
    scope: SearchScope = SearchScope.public,
    thumbnail: int | None = Query(default=None, ge=64, le=1600),
    service_token: str | None = Header(default=None, alias="X-Service-Token"),
) -> Response:
    if scope == SearchScope.internal:
        require_internal_access(request, service_token)
    storage = request.app.state.storage
    if not accessible_reference(storage, asset_id, scope):
        raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND", "message": "Asset not found"})
    asset = storage.one("SELECT * FROM assets WHERE id = ?", (asset_id,))
    if not asset:
        raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND", "message": "Asset not found"})
    path = request.app.state.asset_store.resolve(asset["storage_path"])
    cache_control = "public, max-age=3600" if scope == SearchScope.public else "private, no-store"
    if thumbnail is None:
        return FileResponse(path, media_type=asset["content_type"], filename=None,
                            headers={"Cache-Control": cache_control, "X-Content-Type-Options": "nosniff"})
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source)
        image.thumbnail((thumbnail, thumbnail))
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGB")
        output = io.BytesIO()
        image.save(output, format="WEBP", quality=82, method=4)
    return Response(content=output.getvalue(), media_type="image/webp",
                    headers={"Cache-Control": cache_control, "X-Content-Type-Options": "nosniff"})


@app.post("/v1/references", response_model=ReferenceResponse, status_code=status.HTTP_201_CREATED, tags=["references"])
def register_reference(
    payload: ReferenceCreate,
    request: Request,
    service_token: str | None = Header(default=None, alias="X-Service-Token"),
) -> ReferenceResponse:
    require_internal_access(request, service_token)
    storage: Storage = request.app.state.storage
    asset = storage.one("SELECT * FROM assets WHERE id = ?", (payload.asset_id,))
    if not asset:
        raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND", "message": "Asset not found"})
    feature = extract_feature(request.app.state.asset_store.resolve(asset["storage_path"]))
    created_at = utcnow()
    storage.execute(
        """INSERT INTO reference_assets(asset_id, label, algorithm_version, feature, created_at,
                                         pattern_id, review_status, visibility)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(asset_id) DO UPDATE SET label=excluded.label,
           algorithm_version=excluded.algorithm_version, feature=excluded.feature,
           pattern_id=excluded.pattern_id, review_status=excluded.review_status,
           visibility=excluded.visibility""",
        (payload.asset_id, payload.label, ALGORITHM_VERSION, json.dumps(feature), created_at,
         payload.pattern_id, payload.review_status.value, payload.visibility.value),
    )
    row = storage.one("SELECT * FROM reference_assets WHERE asset_id = ?", (payload.asset_id,))
    return reference_response(row)


@app.get("/v1/references", response_model=list[ReferenceResponse], tags=["references"])
def list_references(
    request: Request,
    scope: SearchScope = SearchScope.public,
    service_token: str | None = Header(default=None, alias="X-Service-Token"),
) -> list[ReferenceResponse]:
    if scope == SearchScope.internal:
        require_internal_access(request, service_token)
        rows = request.app.state.storage.all("SELECT * FROM reference_assets ORDER BY created_at, asset_id")
    else:
        rows = request.app.state.storage.all(
            """SELECT * FROM reference_assets WHERE review_status = 'approved'
               AND visibility = 'public' ORDER BY created_at, asset_id"""
        )
    return [reference_response(row) for row in rows]


@app.get("/v1/references/by-pattern/{pattern_id}", response_model=ReferenceResponse, tags=["references"])
def get_reference_by_pattern(
    pattern_id: str,
    request: Request,
    scope: SearchScope = SearchScope.public,
    service_token: str | None = Header(default=None, alias="X-Service-Token"),
) -> ReferenceResponse:
    if scope == SearchScope.internal:
        require_internal_access(request, service_token)
        row = request.app.state.storage.one(
            "SELECT * FROM reference_assets WHERE pattern_id = ? ORDER BY created_at, asset_id LIMIT 1",
            (pattern_id,),
        )
    else:
        row = request.app.state.storage.one(
            """SELECT * FROM reference_assets WHERE pattern_id = ?
               AND review_status = 'approved' AND visibility = 'public'
               ORDER BY created_at, asset_id LIMIT 1""", (pattern_id,),
        )
    if not row:
        raise HTTPException(404, detail={"code": "REFERENCE_NOT_FOUND", "message": "Reference not found"})
    response = reference_response(row)
    if scope == SearchScope.internal:
        response.content_url += "?scope=internal"
        response.thumbnail_url += "&scope=internal"
    return response


@app.put(
    "/v1/internal/references/by-pattern/{pattern_id}/publication",
    response_model=ReferenceResponse,
    tags=["references"],
)
def set_reference_publication(
    pattern_id: str,
    payload: ReferencePublicationUpdate,
    request: Request,
    service_token: str | None = Header(default=None, alias="X-Service-Token"),
) -> ReferenceResponse:
    require_internal_access(request, service_token)
    storage = request.app.state.storage
    row = storage.one(
        "SELECT * FROM reference_assets WHERE pattern_id = ? ORDER BY created_at, asset_id LIMIT 1",
        (pattern_id,),
    )
    if not row:
        raise HTTPException(404, detail={"code": "REFERENCE_NOT_FOUND", "message": "Reference not found"})
    review_status = "approved" if payload.published else "draft"
    visibility = "public" if payload.published else "internal_only"
    storage.execute(
        "UPDATE reference_assets SET review_status = ?, visibility = ? WHERE pattern_id = ?",
        (review_status, visibility, pattern_id),
    )
    updated = storage.one("SELECT * FROM reference_assets WHERE asset_id = ?", (row["asset_id"],))
    response = reference_response(updated)
    if not payload.published:
        response.content_url += "?scope=internal"
        response.thumbnail_url += "&scope=internal"
    return response


@app.post("/v1/analyses", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED, tags=["analysis"])
def create_analysis(
    payload: AnalysisCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    service_token: str | None = Header(default=None, alias="X-Service-Token"),
    capability: str | None = Header(default=None, alias="X-Asset-Capability"),
) -> JobResponse:
    if payload.scope == SearchScope.internal:
        require_internal_access(request, service_token)
    else:
        require_asset_access(request, payload.asset_id, capability, service_token)
        enforce_rate_limit(request, "analysis", request.app.state.settings.anonymous_analyses_per_minute)
    storage: Storage = request.app.state.storage
    if not storage.one("SELECT id FROM assets WHERE id = ?", (payload.asset_id,)):
        raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND", "message": "Asset not found"})
    queued = storage.one("SELECT COUNT(*) AS count FROM jobs WHERE status IN ('pending','running')")["count"]
    if request.app.state.settings.max_queued_jobs and queued >= request.app.state.settings.max_queued_jobs:
        raise HTTPException(429, detail={"code": "QUEUE_FULL", "message": "Analysis queue is full"},
                            headers={"Retry-After": "5"})
    job_id = str(uuid.uuid4())
    now = utcnow()
    tasks = [task.value for task in payload.tasks]
    storage.execute(
        "INSERT INTO jobs VALUES (?, 'analysis', 'pending', ?, ?, ?, 0, NULL, NULL, NULL, ?, ?)",
        (job_id, payload.asset_id, json.dumps(tasks),
         json.dumps({"palette_colors": payload.palette_colors, "top_k": payload.top_k,
                     "scope": payload.scope.value}), now, now),
    )
    background_tasks.add_task(run_analysis, request.app, job_id)
    return JobResponse(**decode_job(storage.one("SELECT * FROM jobs WHERE id = ?", (job_id,))))


def recover_interrupted_jobs(application: FastAPI) -> int:
    """Recover durable jobs left incomplete by a terminated single service instance."""
    storage = application.state.storage
    now = utcnow()
    storage.execute(
        """UPDATE jobs SET status='pending', progress=0, error_code=NULL,
           error_message=NULL, updated_at=? WHERE status='running'""",
        (now,),
    )
    rows = storage.all("SELECT id FROM jobs WHERE status='pending' ORDER BY created_at, id")
    for row in rows:
        run_analysis(application, row["id"])
    if rows:
        logger.info("Recovered %d interrupted analysis job(s)", len(rows))
    return len(rows)


def run_analysis(application: FastAPI, job_id: str) -> None:
    storage: Storage = application.state.storage
    claimed = storage.execute_count(
        """UPDATE jobs SET status='running', progress=10, error_code=NULL,
           error_message=NULL, updated_at=? WHERE id=? AND status='pending'""",
        (utcnow(), job_id),
    )
    if claimed != 1:
        return
    job = storage.one("SELECT * FROM jobs WHERE id = ?", (job_id,))
    try:
        asset = storage.one("SELECT * FROM assets WHERE id = ?", (job["asset_id"],))
        tasks = json.loads(job["requested_tasks"])
        parameters = json.loads(job["parameters"])
        payload: dict = {"palette": None, "embedding": None, "classification": None,
                         "similar": None, "similarity_algorithm_version": None, "warnings": []}
        image_path = application.state.asset_store.resolve(asset["storage_path"])
        if AnalysisTask.palette.value in tasks:
            payload["palette"] = extract_palette(image_path, parameters["palette_colors"])
        if AnalysisTask.similar.value in tasks:
            query_feature = extract_feature(image_path)
            if parameters.get("scope", "public") == "internal":
                references = storage.all(
                    """SELECT asset_id, label, pattern_id, algorithm_version, feature
                       FROM reference_assets WHERE asset_id != ?""", (job["asset_id"],))
            else:
                references = storage.all(
                    """SELECT asset_id, label, pattern_id, algorithm_version, feature
                       FROM reference_assets
                       WHERE asset_id != ? AND visibility = 'public' AND review_status = 'approved'""",
                    (job["asset_id"],),
                )
            compatible = [row for row in references if row["algorithm_version"] == ALGORITHM_VERSION]
            matches = [
                {"asset_id": row["asset_id"], "label": row["label"], "pattern_id": row["pattern_id"],
                 "score": similarity(query_feature, json.loads(row["feature"]))}
                for row in compatible
            ]
            payload["similar"] = sorted(matches, key=lambda item: (-item["score"], item["asset_id"]))[
                : parameters.get("top_k", 5)
            ]
            payload["similarity_algorithm_version"] = ALGORITHM_VERSION
            if not compatible:
                payload["warnings"].append("No compatible reference assets are registered")
        for task_name, provider, method_name in (
            (AnalysisTask.embedding.value, application.state.embedding_provider, "embed"),
            (AnalysisTask.classification.value, application.state.classification_provider, "classify"),
        ):
            if task_name not in tasks:
                continue
            try:
                data = getattr(provider, method_name)(image_path)
                payload[task_name] = {"status": "succeeded", "provider": provider.name,
                                      "model_version": provider.model_version, "data": data}
            except ProviderNotConfigured as exc:
                payload[task_name] = {"status": "unavailable", "provider": provider.name, "reason": str(exc)}
                payload["warnings"].append(str(exc))
        result_id = str(uuid.uuid4())
        created_at = utcnow()
        storage.execute("INSERT INTO analysis_results VALUES (?, ?, ?, ?, ?)",
                        (result_id, job_id, job["asset_id"], json.dumps(payload), created_at))
        storage.execute("UPDATE jobs SET status='succeeded', progress=100, result_id=?, updated_at=? WHERE id=?",
                        (result_id, utcnow(), job_id))
    except Exception as exc:
        logger.exception("Analysis job %s failed", job_id)
        storage.execute("UPDATE jobs SET status='failed', progress=100, error_code='ANALYSIS_FAILED', error_message=?, updated_at=? WHERE id=?",
                        (str(exc), utcnow(), job_id))


@app.get("/v1/internal/jobs/stats", tags=["jobs"])
def job_stats(
    request: Request,
    service_token: str | None = Header(default=None, alias="X-Service-Token"),
) -> dict:
    require_internal_access(request, service_token)
    rows = request.app.state.storage.all(
        "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status"
    )
    counts = {item: 0 for item in ("pending", "running", "succeeded", "failed")}
    counts.update({row["status"]: row["count"] for row in rows})
    return {"jobs": counts, "recovered_on_startup": request.app.state.recovered_jobs}


@app.post("/v1/internal/jobs/{job_id}/retry", response_model=JobResponse, tags=["jobs"])
def retry_job(
    job_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    service_token: str | None = Header(default=None, alias="X-Service-Token"),
) -> JobResponse:
    require_internal_access(request, service_token)
    storage = request.app.state.storage
    row = storage.one("SELECT * FROM jobs WHERE id = ?", (job_id,))
    if not row:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": "Job not found"})
    if row["status"] == "failed":
        storage.execute(
            """UPDATE jobs SET status='pending', progress=0, result_id=NULL,
               error_code=NULL, error_message=NULL, updated_at=? WHERE id=?""",
            (utcnow(), job_id),
        )
        background_tasks.add_task(run_analysis, request.app, job_id)
    elif row["status"] == "pending":
        background_tasks.add_task(run_analysis, request.app, job_id)
    return JobResponse(**decode_job(storage.one("SELECT * FROM jobs WHERE id = ?", (job_id,))))


@app.get("/v1/jobs/{job_id}", response_model=JobResponse, tags=["jobs"])
def get_job(
    job_id: str,
    request: Request,
    service_token: str | None = Header(default=None, alias="X-Service-Token"),
    capability: str | None = Header(default=None, alias="X-Asset-Capability"),
) -> JobResponse:
    row = request.app.state.storage.one("SELECT * FROM jobs WHERE id = ?", (job_id,))
    if not row:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": "Job not found"})
    if json.loads(row["parameters"]).get("scope") == SearchScope.internal.value:
        require_internal_access(request, service_token)
    else:
        require_asset_access(request, row["asset_id"], capability, service_token)
    return JobResponse(**decode_job(row))


@app.get("/v1/analyses/{result_id}", response_model=AnalysisResultResponse, tags=["analysis"])
def get_analysis(
    result_id: str,
    request: Request,
    service_token: str | None = Header(default=None, alias="X-Service-Token"),
    capability: str | None = Header(default=None, alias="X-Asset-Capability"),
) -> AnalysisResultResponse:
    row = request.app.state.storage.one(
        """SELECT analysis_results.*, jobs.parameters AS job_parameters
           FROM analysis_results JOIN jobs ON jobs.id = analysis_results.job_id
           WHERE analysis_results.id = ?""",
        (result_id,),
    )
    if not row:
        raise HTTPException(404, detail={"code": "RESULT_NOT_FOUND", "message": "Analysis result not found"})
    if json.loads(row["job_parameters"]).get("scope") == SearchScope.internal.value:
        require_internal_access(request, service_token)
    else:
        require_asset_access(request, row["asset_id"], capability, service_token)
    payload = json.loads(row["payload"])
    return AnalysisResultResponse(id=row["id"], job_id=row["job_id"], asset_id=row["asset_id"],
                                  created_at=row["created_at"], **payload)


@app.delete("/v1/assets/{asset_id}", tags=["assets"])
def delete_asset(asset_id: str, request: Request,
                 capability: str | None = Header(default=None, alias="X-Asset-Capability"),
                 service_token: str | None = Header(default=None, alias="X-Service-Token")) -> dict:
    storage = request.app.state.storage
    asset = storage.one("SELECT * FROM assets WHERE id=?", (asset_id,))
    if not asset:
        raise HTTPException(404, detail={"code": "ASSET_NOT_FOUND", "message": "Asset not found"})
    require_asset_access(request, asset_id, capability, service_token)
    if not _is_internal(request, service_token) and storage.one(
        "SELECT asset_id FROM reference_assets WHERE asset_id=?", (asset_id,)
    ):
        raise HTTPException(409, detail={"code": "REFERENCE_ASSET_PROTECTED",
                                         "message": "Registered reference assets cannot be deleted anonymously"})
    request.app.state.asset_store.delete(asset["storage_path"])
    storage.delete_asset_cascade(asset_id)
    return {"deleted": True, "asset_id": asset_id}


@app.post("/v1/internal/cleanup", tags=["system"])
def cleanup_assets(request: Request, dry_run: bool = Query(default=True),
                   service_token: str | None = Header(default=None, alias="X-Service-Token")) -> dict:
    require_internal_access(request, service_token)
    cutoff = (datetime.now(timezone.utc) - timedelta(
        hours=request.app.state.settings.anonymous_asset_ttl_hours)).isoformat()
    rows = request.app.state.storage.all(
        """SELECT a.* FROM assets a WHERE a.created_at < ?
           AND NOT EXISTS (SELECT 1 FROM reference_assets r WHERE r.asset_id=a.id)""", (cutoff,)
    )
    if not dry_run:
        for asset in rows:
            request.app.state.asset_store.delete(asset["storage_path"])
            request.app.state.storage.delete_asset_cascade(asset["id"])
    return {"dry_run": dry_run, "ttl_hours": request.app.state.settings.anonymous_asset_ttl_hours,
            "matched": len(rows), "deleted": 0 if dry_run else len(rows),
            "asset_ids": [row["id"] for row in rows]}
