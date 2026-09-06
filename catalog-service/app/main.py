import csv
import io
import json
import math
import uuid
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from .config import get_settings, validate_settings
from .ai_sync import AISyncError, sync_publication
from .db import check_database, database, initialize, json_value, risk_clauses, row_to_dict, scalar, timestamp_value
from .schemas import (AuditLog, BatchOperationItem, BatchOperationResponse, BatchPublishRequest,
                      BatchReviewRequest, CatalogStats, CategoryCount, EvidenceUpdate, Pattern, PatternCreate,
                      PatternPage, PatternUpdate, ReviewRiskStats)
from .security import require_admin
from .review_workflow import router as review_workflow_router
from .evidence_storage import delete_object, fetch_object, store_upload


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    validate_settings(settings)
    initialize(settings)
    yield


app = FastAPI(title="Zhixiu Pattern Catalog", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_settings().cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)
app.include_router(review_workflow_router)


def ensure_publishable(item: dict) -> None:
    if item.get("status") != "published" and item.get("visibility") != "public":
        return
    issues = item.get("review", {}).get("issues", [])
    rights_status = item.get("rights", {}).get("status")
    errors = []
    if not str(item.get("name", "")).strip():
        errors.append("名称不能为空")
    if rights_status != "verified":
        errors.append("版权状态必须为 verified")
    if issues:
        errors.append("审核风险项必须清零")
    if errors:
        raise HTTPException(status_code=422, detail={"code": "publish_validation_failed", "errors": errors})


def write_audit(connection, pattern_id: str, action: str, before: dict | None, after: dict | None) -> None:
    connection.execute(
        "INSERT INTO audit_logs(pattern_id,action,actor,before_json,after_json) VALUES (?,?,?,?,?)",
        (pattern_id, action, "development-admin", json.dumps(before, ensure_ascii=False) if before else None, json.dumps(after, ensure_ascii=False) if after else None),
    )


def _publish_pattern(pattern_id: str) -> Pattern:
    settings = get_settings()
    with database(settings) as connection:
        row = connection.execute("SELECT * FROM patterns WHERE id = ?", (pattern_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Pattern not found")
        before = row_to_dict(row)
        review_task = connection.execute("SELECT state FROM review_tasks WHERE pattern_id = ?", (pattern_id,)).fetchone()
    candidate = {**before, "status": "published", "visibility": "public"}
    try:
        ensure_publishable(candidate)
        if review_task is None or review_task["state"] != "approved":
            raise HTTPException(status_code=422, detail={"code": "publish_validation_failed", "errors": ["审核任务必须为 approved"]})
    except HTTPException as exc:
        with database(settings) as connection:
            write_audit(connection, pattern_id, "publish_validation_failed", before, {"detail": exc.detail})
        raise

    try:
        sync_status = sync_publication(pattern_id, True, settings)
    except AISyncError as exc:
        with database(settings) as connection:
            write_audit(connection, pattern_id, "publish_sync_failed", before, {"error": str(exc)})
        raise HTTPException(status_code=502, detail={"code": "ai_sync_failed", "message": str(exc)}) from exc

    try:
        with database(settings) as connection:
            connection.execute("UPDATE patterns SET status='published', visibility='public', updated_at=CURRENT_TIMESTAMP WHERE id=?", (pattern_id,))
            after = row_to_dict(connection.execute("SELECT * FROM patterns WHERE id = ?", (pattern_id,)).fetchone())
            write_audit(connection, pattern_id, "published", before, {**after, "aiSync": sync_status})
    except Exception:
        if sync_status == "synchronized":
            try:
                sync_publication(pattern_id, False, settings)
            except AISyncError:
                pass
        raise
    return Pattern.model_validate(after)


def _withdraw_pattern(pattern_id: str) -> Pattern:
    """Withdraw public content from AI first, then Catalog; compensate AI if the DB write fails."""
    settings = get_settings()
    with database(settings) as connection:
        row = connection.execute("SELECT * FROM patterns WHERE id = ?", (pattern_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Pattern not found")
        before = row_to_dict(row)
    if before["status"] != "published" or before["visibility"] != "public":
        raise HTTPException(status_code=409, detail={"code": "invalid_publication_transition", "message": "Only published public patterns can be withdrawn"})
    try:
        sync_status = sync_publication(pattern_id, False, settings)
    except AISyncError as exc:
        with database(settings) as connection:
            write_audit(connection, pattern_id, "withdraw_sync_failed", before, {"error": str(exc)})
        raise HTTPException(status_code=502, detail={"code": "ai_sync_failed", "message": str(exc)}) from exc
    try:
        with database(settings) as connection:
            connection.execute("UPDATE patterns SET status='draft', visibility='internal_only', updated_at=CURRENT_TIMESTAMP WHERE id=?", (pattern_id,))
            after = row_to_dict(connection.execute("SELECT * FROM patterns WHERE id = ?", (pattern_id,)).fetchone())
            write_audit(connection, pattern_id, "withdrawn", before, {**after, "aiSync": sync_status})
    except Exception:
        if sync_status == "synchronized":
            try:
                sync_publication(pattern_id, True, settings)
            except AISyncError:
                pass
        raise
    return Pattern.model_validate(after)


def _failure_detail(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, HTTPException):
        if isinstance(exc.detail, dict):
            return str(exc.detail.get("code", "operation_failed")), str(exc.detail.get("message") or exc.detail.get("errors") or exc.detail)
        return "not_found" if exc.status_code == 404 else "operation_failed", str(exc.detail)
    return "operation_failed", str(exc)


def _filtered_where(status_filter: str | None, visibility: str | None, risk: str | None) -> tuple[str, list[object]]:
    clauses, params = ["1=1"], []
    if status_filter:
        clauses.append("status = ?")
        params.append(status_filter)
    if visibility:
        clauses.append("visibility = ?")
        params.append(visibility)
    clauses.extend(risk_clauses(get_settings().database_backend, risk))
    return " AND ".join(clauses), params


def _csv_safe(value: object) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if text.startswith(("\t", "\r", "\n")) or text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _public_pattern(item: dict) -> Pattern:
    """Remove internal evidence locations and reviewer notes from public responses."""
    public_item = {**item, "rights": {**item.get("rights", {}), "evidence": [], "verificationNote": None}}
    public_item["review"] = {**item.get("review", {}), "note": None}
    return Pattern.model_validate(public_item)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    settings = get_settings()
    check_database(settings)
    return {"status": "ready", "database": settings.database_backend}


@app.get("/api/v1/patterns", response_model=PatternPage)
def list_patterns(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    q: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None, max_length=100),
) -> PatternPage:
    clauses = ["status = 'published'", "visibility = 'public'"]
    params: list[object] = []
    if q:
        clauses.append("(name LIKE ? OR meaning LIKE ? OR category LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])
    if category:
        clauses.append("category = ?")
        params.append(category)
    where = " AND ".join(clauses)
    offset = (page - 1) * page_size
    with database(get_settings()) as connection:
        total = scalar(connection.execute(f"SELECT COUNT(*) FROM patterns WHERE {where}", params).fetchone())
        rows = connection.execute(
            f"SELECT * FROM patterns WHERE {where} ORDER BY updated_at DESC, id LIMIT ? OFFSET ?",
            [*params, page_size, offset],
        ).fetchall()
    return PatternPage(items=[_public_pattern(row_to_dict(row)) for row in rows], page=page, pageSize=page_size, total=total, pages=math.ceil(total / page_size) if total else 0)


@app.get("/api/v1/patterns/{pattern_id}", response_model=Pattern)
def get_pattern(pattern_id: str) -> Pattern:
    with database(get_settings()) as connection:
        row = connection.execute("SELECT * FROM patterns WHERE id = ? AND status = 'published' AND visibility = 'public'", (pattern_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Pattern not found")
    return _public_pattern(row_to_dict(row))


@app.post("/api/v1/admin/patterns", response_model=Pattern, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
def create_pattern(payload: PatternCreate) -> Pattern:
    item = payload.model_dump()
    if item["status"] == "published" or item["visibility"] == "public":
        raise HTTPException(status_code=409, detail={"code": "invalid_publication_transition", "message": "Create as non-public content, then use the publish endpoint"})
    pattern_id = item.pop("id") or f"pat_{uuid.uuid4().hex}"
    with database(get_settings()) as connection:
        try:
            connection.execute(
                """INSERT INTO patterns (id,name,category,ethnicity,meaning,colors_json,image_url,status,visibility,source_json,rights_json,review_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pattern_id, item["name"], item["category"], item["ethnicity"], item["meaning"], json.dumps(item["colors"], ensure_ascii=False), item["imageUrl"], item["status"], item["visibility"], json.dumps(item["source"], ensure_ascii=False), json.dumps(item["rights"], ensure_ascii=False), json.dumps(item["review"], ensure_ascii=False)),
            )
        except Exception as exc:
            if "UNIQUE constraint" in str(exc) or getattr(exc, "sqlstate", None) == "23505":
                raise HTTPException(status_code=409, detail="Pattern id already exists") from exc
            raise
        row = connection.execute("SELECT * FROM patterns WHERE id = ?", (pattern_id,)).fetchone()
        created = row_to_dict(row)
        write_audit(connection, pattern_id, "created", None, created)
    return Pattern.model_validate(created)


@app.post("/api/v1/admin/patterns/import", response_model=list[Pattern], dependencies=[Depends(require_admin)])
def import_patterns(payload: list[PatternCreate]) -> list[Pattern]:
    """Small JSON import endpoint. Imported rows are always draft/internal-only."""
    if len(payload) > 500:
        raise HTTPException(status_code=413, detail="Import is limited to 500 records")
    imported = []
    for item in payload:
        safe_item = item.model_copy(update={"status": "draft", "visibility": "internal_only"})
        imported.append(create_pattern(safe_item))
    return imported


@app.patch("/api/v1/admin/patterns/{pattern_id}", response_model=Pattern, dependencies=[Depends(require_admin)])
def update_pattern(pattern_id: str, payload: PatternUpdate) -> Pattern:
    changes = payload.model_dump(exclude_unset=True)
    mapping = {"imageUrl": "image_url", "colors": "colors_json", "source": "source_json", "rights": "rights_json", "review": "review_json"}
    json_fields = {"colors", "source", "rights", "review"}
    with database(get_settings()) as connection:
        current_row = connection.execute("SELECT * FROM patterns WHERE id = ?", (pattern_id,)).fetchone()
        if not current_row:
            raise HTTPException(status_code=404, detail="Pattern not found")
        before = row_to_dict(current_row)
        combined = {**before, **changes}
        if ("status" in changes or "visibility" in changes) and (
            before["status"] == "published" or before["visibility"] == "public"
            or combined["status"] == "published" or combined["visibility"] == "public"
        ):
            raise HTTPException(status_code=409, detail={"code": "invalid_publication_transition", "message": "Use the dedicated publish or withdraw endpoint"})
        ensure_publishable(combined)
        if changes:
            assignments, values = [], []
            for key, value in changes.items():
                assignments.append(f"{mapping.get(key, key)} = ?")
                values.append(json.dumps(value, ensure_ascii=False) if key in json_fields else value)
            assignments.append("updated_at = CURRENT_TIMESTAMP")
            connection.execute(f"UPDATE patterns SET {', '.join(assignments)} WHERE id = ?", [*values, pattern_id])
        row = connection.execute("SELECT * FROM patterns WHERE id = ?", (pattern_id,)).fetchone()
        after = row_to_dict(row)
        write_audit(connection, pattern_id, "updated", before, after)
    return Pattern.model_validate(after)


@app.patch("/api/v1/admin/patterns/{pattern_id}/evidence", response_model=Pattern, dependencies=[Depends(require_admin)])
def update_pattern_evidence(pattern_id: str, payload: EvidenceUpdate) -> Pattern:
    """Merge source, rights evidence and review notes without replacing unrelated JSON fields."""
    changes = payload.model_dump(exclude_unset=True)
    with database(get_settings()) as connection:
        current_row = connection.execute("SELECT * FROM patterns WHERE id = ?", (pattern_id,)).fetchone()
        if not current_row:
            raise HTTPException(status_code=404, detail="Pattern not found")
        before = row_to_dict(current_row)
        source, rights, review = dict(before["source"]), dict(before["rights"]), dict(before["review"])
        source_mapping = {"sourceDescription": "description", "originClaim": "originClaim"}
        rights_mapping = {
            "rightsStatus": "status", "rightsOwner": "owner", "rightsLicense": "license",
            "evidence": "evidence", "verifiedBy": "verifiedBy", "verifiedAt": "verifiedAt",
            "verificationNote": "verificationNote",
        }
        for key, target in source_mapping.items():
            if key in changes:
                source[target] = changes[key]
        for key, target in rights_mapping.items():
            if key in changes:
                rights[target] = changes[key]
        if "reviewNote" in changes:
            review["note"] = changes["reviewNote"]
        candidate = {**before, "source": source, "rights": rights, "review": review}
        ensure_publishable(candidate)
        connection.execute(
            "UPDATE patterns SET source_json=?, rights_json=?, review_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (json.dumps(source, ensure_ascii=False), json.dumps(rights, ensure_ascii=False), json.dumps(review, ensure_ascii=False), pattern_id),
        )
        after = row_to_dict(connection.execute("SELECT * FROM patterns WHERE id = ?", (pattern_id,)).fetchone())
        write_audit(connection, pattern_id, "evidence_updated", before, after)
    return Pattern.model_validate(after)


@app.post("/api/v1/admin/patterns/{pattern_id}/evidence-files", response_model=Pattern,
          dependencies=[Depends(require_admin)])
async def upload_evidence_file(pattern_id: str, file: UploadFile = File(...)) -> Pattern:
    """Store a validated private object and atomically attach its server-issued metadata."""
    settings = get_settings()
    with database(settings) as connection:
        row = connection.execute("SELECT * FROM patterns WHERE id = ?", (pattern_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Pattern not found")
    if len(row_to_dict(row)["rights"].get("evidence") or []) >= 100:
        raise HTTPException(status_code=409, detail={"code": "evidence_limit_reached", "maxFiles": 100})

    stored = await store_upload(pattern_id, file, settings)
    try:
        with database(settings) as connection:
            current_row = connection.execute("SELECT * FROM patterns WHERE id = ?", (pattern_id,)).fetchone()
            if current_row is None:
                raise HTTPException(status_code=404, detail="Pattern not found")
            before = row_to_dict(current_row)
            rights = dict(before["rights"])
            evidence = list(rights.get("evidence") or [])
            evidence.append({
                "id": stored.evidence_id, "filename": stored.filename, "contentType": stored.content_type,
                "sizeBytes": stored.size_bytes, "storageKey": stored.storage_key,
                "checksumSha256": stored.checksum_sha256,
            })
            rights["evidence"] = evidence
            connection.execute(
                "UPDATE patterns SET rights_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (json.dumps(rights, ensure_ascii=False), pattern_id),
            )
            after = row_to_dict(connection.execute("SELECT * FROM patterns WHERE id = ?", (pattern_id,)).fetchone())
            write_audit(connection, pattern_id, "evidence_file_uploaded", before, after)
    except Exception:
        delete_object(stored.storage_key, settings)
        raise
    return Pattern.model_validate(after)


@app.get("/api/v1/admin/patterns/{pattern_id}/evidence-files/{evidence_id}",
         dependencies=[Depends(require_admin)])
def download_evidence_file(pattern_id: str, evidence_id: str) -> StreamingResponse:
    """Proxy a private evidence object only after admin authorization and metadata lookup."""
    settings = get_settings()
    with database(settings) as connection:
        row = connection.execute("SELECT * FROM patterns WHERE id = ?", (pattern_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Pattern not found")
    pattern = row_to_dict(row)
    evidence = next((item for item in pattern["rights"].get("evidence", []) if item.get("id") == evidence_id), None)
    if not evidence or not evidence.get("storageKey"):
        raise HTTPException(status_code=404, detail="Evidence file not found")
    stored = fetch_object(evidence["storageKey"], settings)
    filename = str(evidence.get("filename") or "evidence").replace('"', "_").replace("\r", "_").replace("\n", "_")
    ascii_filename = filename.encode("ascii", "ignore").decode() or "evidence"
    response_headers = {
        "Content-Disposition": f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{quote(filename)}',
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "X-Checksum-Sha256": str(evidence.get("checksumSha256") or ""),
    }
    content_length = evidence.get("sizeBytes") or stored.get("ContentLength")
    if content_length is not None:
        response_headers["Content-Length"] = str(content_length)
    return StreamingResponse(
        stored["Body"].iter_chunks(chunk_size=64 * 1024),
        media_type=evidence.get("contentType") or "application/octet-stream",
        headers=response_headers,
    )


@app.get("/api/v1/admin/patterns", response_model=PatternPage, dependencies=[Depends(require_admin)])
def list_admin_patterns(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    visibility: str | None = Query(default=None),
    risk: str | None = Query(default=None, pattern="^(any|has_issues|rights_unverified|ready)$"),
) -> PatternPage:
    where, params = _filtered_where(status_filter, visibility, risk)
    offset = (page - 1) * page_size
    with database(get_settings()) as connection:
        total = scalar(connection.execute(f"SELECT COUNT(*) FROM patterns WHERE {where}", params).fetchone())
        rows = connection.execute(f"SELECT * FROM patterns WHERE {where} ORDER BY updated_at DESC, id LIMIT ? OFFSET ?", [*params, page_size, offset]).fetchall()
    return PatternPage(items=[Pattern.model_validate(row_to_dict(row)) for row in rows], page=page, pageSize=page_size, total=total, pages=math.ceil(total / page_size) if total else 0)


@app.get("/api/v1/admin/patterns/stats", response_model=CatalogStats, dependencies=[Depends(require_admin)])
def catalog_stats(category_top: int = Query(10, alias="categoryTop", ge=0, le=50)) -> CatalogStats:
    settings = get_settings()
    with database(settings) as connection:
        total = scalar(connection.execute("SELECT COUNT(*) FROM patterns").fetchone())
        status_rows = connection.execute("SELECT status, COUNT(*) AS count FROM patterns GROUP BY status").fetchall()
        rows = [row_to_dict(row) for row in connection.execute("SELECT * FROM patterns").fetchall()]
        approved_ids = {row["pattern_id"] for row in connection.execute("SELECT pattern_id FROM review_tasks WHERE state='approved'").fetchall()}
        category_rows = connection.execute(
            "SELECT category, COUNT(*) AS count FROM patterns GROUP BY category ORDER BY count DESC, category LIMIT ?",
            (category_top,),
        ).fetchall() if category_top else []
    statuses = {"draft": 0, "published": 0, "archived": 0}
    statuses.update({row["status"]: row["count"] for row in map(dict, status_rows)})
    rights_statuses: dict[str, int] = {}
    has_issues = ready = 0
    for row in rows:
        rights_status = str(row.get("rights", {}).get("status") or "unknown")
        rights_statuses[rights_status] = rights_statuses.get(rights_status, 0) + 1
        issues = row.get("review", {}).get("issues") or []
        has_issues += bool(issues)
        ready += bool(str(row.get("name", "")).strip() and rights_status == "verified" and not issues and row["id"] in approved_ids)
    return CatalogStats(
        total=total,
        statuses=statuses,
        rightsStatuses=rights_statuses,
        reviewRisk=ReviewRiskStats(hasIssues=has_issues, rightsUnverified=total - rights_statuses.get("verified", 0)),
        ready=ready,
        categories=[CategoryCount(category=(row["category"] or "未分类"), count=row["count"]) for row in map(dict, category_rows)],
    )


@app.get("/api/v1/admin/patterns/export.csv", dependencies=[Depends(require_admin)])
def export_patterns_csv(
    status_filter: str | None = Query(default=None, alias="status"),
    visibility: str | None = Query(default=None),
    risk: str | None = Query(default=None, pattern="^(any|has_issues|rights_unverified|ready)$"),
    limit: int = Query(1000, ge=1, le=5000),
) -> Response:
    where, params = _filtered_where(status_filter, visibility, risk)
    with database(get_settings()) as connection:
        rows = connection.execute(
            f"SELECT * FROM patterns WHERE {where} ORDER BY updated_at DESC, id LIMIT ?", [*params, limit]
        ).fetchall()
    columns = [
        "id", "name", "category", "ethnicity", "meaning", "colors", "imageUrl", "status", "visibility",
        "sourceSystem", "sourceLegacyType", "sourceLegacyId", "sourceOriginClaim", "rightsStatus", "rightsOwner",
        "rightsLicense", "reviewIssues", "reviewedBy", "reviewedAt", "createdAt", "updatedAt",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for raw in rows:
        item = row_to_dict(raw)
        source, rights, review = item["source"], item["rights"], item["review"]
        flat = {**item,
            "sourceSystem": source.get("system"), "sourceLegacyType": source.get("legacyType"),
            "sourceLegacyId": source.get("legacyId"), "sourceOriginClaim": source.get("originClaim"),
            "rightsStatus": rights.get("status"), "rightsOwner": rights.get("owner"), "rightsLicense": rights.get("license"),
            "reviewIssues": review.get("issues", []), "reviewedBy": review.get("reviewedBy"), "reviewedAt": review.get("reviewedAt"),
        }
        writer.writerow({column: _csv_safe(flat.get(column)) for column in columns})
    body = ("\ufeff" + output.getvalue()).encode("utf-8")
    return Response(content=body, media_type="text/csv", headers={
        "Content-Disposition": 'attachment; filename="zhixiu-patterns.csv"',
        "Cache-Control": "no-store",
        "X-Exported-Rows": str(len(rows)),
    })


@app.get("/api/v1/admin/patterns/{pattern_id}", response_model=Pattern, dependencies=[Depends(require_admin)])
def get_admin_pattern(pattern_id: str) -> Pattern:
    with database(get_settings()) as connection:
        row = connection.execute("SELECT * FROM patterns WHERE id = ?", (pattern_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Pattern not found")
    return Pattern.model_validate(row_to_dict(row))


@app.post("/api/v1/admin/patterns/{pattern_id}/publish", response_model=Pattern, dependencies=[Depends(require_admin)])
def publish_pattern(pattern_id: str) -> Pattern:
    return _publish_pattern(pattern_id)


@app.post("/api/v1/admin/patterns/{pattern_id}/withdraw", response_model=Pattern, dependencies=[Depends(require_admin)])
def withdraw_pattern(pattern_id: str) -> Pattern:
    return _withdraw_pattern(pattern_id)


@app.post("/api/v1/admin/patterns/batch-review", response_model=BatchOperationResponse, dependencies=[Depends(require_admin)])
def batch_review(payload: BatchReviewRequest) -> BatchOperationResponse:
    results: list[BatchOperationItem] = []
    settings = get_settings()
    for item in payload.items:
        try:
            with database(settings) as connection:
                row = connection.execute("SELECT * FROM patterns WHERE id = ?", (item.patternId,)).fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Pattern not found")
                before = row_to_dict(row)
                review = {"issues": item.issues, "reviewedBy": item.reviewedBy, "reviewedAt": item.reviewedAt}
                connection.execute("UPDATE patterns SET review_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (json.dumps(review, ensure_ascii=False), item.patternId))
                after = row_to_dict(connection.execute("SELECT * FROM patterns WHERE id = ?", (item.patternId,)).fetchone())
                write_audit(connection, item.patternId, "reviewed", before, after)
            results.append(BatchOperationItem(patternId=item.patternId, status="succeeded", pattern=Pattern.model_validate(after)))
        except Exception as exc:
            code, message = _failure_detail(exc)
            results.append(BatchOperationItem(patternId=item.patternId, status="failed", code=code, message=message))
    succeeded = sum(result.status == "succeeded" for result in results)
    return BatchOperationResponse(succeeded=succeeded, failed=len(results) - succeeded, items=results)


@app.post("/api/v1/admin/patterns/batch-publish", response_model=BatchOperationResponse, dependencies=[Depends(require_admin)])
def batch_publish(payload: BatchPublishRequest) -> BatchOperationResponse:
    results: list[BatchOperationItem] = []
    seen: set[str] = set()
    for pattern_id in payload.patternIds:
        if pattern_id in seen:
            results.append(BatchOperationItem(patternId=pattern_id, status="failed", code="duplicate_pattern_id", message="Duplicate pattern id in batch"))
            continue
        seen.add(pattern_id)
        try:
            pattern = _publish_pattern(pattern_id)
            results.append(BatchOperationItem(patternId=pattern_id, status="succeeded", pattern=pattern))
        except Exception as exc:
            code, message = _failure_detail(exc)
            results.append(BatchOperationItem(patternId=pattern_id, status="failed", code=code, message=message))
    succeeded = sum(result.status == "succeeded" for result in results)
    return BatchOperationResponse(succeeded=succeeded, failed=len(results) - succeeded, items=results)


@app.get("/api/v1/admin/patterns/{pattern_id}/audit-logs", response_model=list[AuditLog], dependencies=[Depends(require_admin)])
def get_audit_logs(pattern_id: str) -> list[AuditLog]:
    with database(get_settings()) as connection:
        rows = connection.execute("SELECT * FROM audit_logs WHERE pattern_id=? ORDER BY id DESC", (pattern_id,)).fetchall()
    return [AuditLog(id=row["id"], patternId=row["pattern_id"], action=row["action"], actor=row["actor"], before=json_value(row["before_json"]) if row["before_json"] else None, after=json_value(row["after_json"]) if row["after_json"] else None, createdAt=timestamp_value(row["created_at"])) for row in rows]

