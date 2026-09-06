"""Read-only, provenance-derived queues for catalog data review."""

from collections import Counter
import math
from typing import Any

from fastapi import APIRouter, Depends, Query

from .config import get_settings
from .db import database, row_to_dict
from .review_readiness import MOTIF_LABELS
from .schemas import CatalogReviewQueueItem, CatalogReviewQueuePage, CatalogReviewQueueSummary, ReviewQueueKind
from .security import require_admin


router = APIRouter(prefix="/api/v1/admin/review-queues", dependencies=[Depends(require_admin)])
UNCATEGORIZED = {"", "待分类", "unknown", "未分类"}


def _name_key(value: str) -> str:
    return "".join(value.split()).casefold()


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None


def _suggestion(provenance: dict[str, Any]) -> tuple[str | None, str | None]:
    nested = provenance.get("categorySuggestion")
    nested = nested if isinstance(nested, dict) else {}
    code = nested.get("code") or provenance.get("categorySuggestionCode") or provenance.get("motifCodeDraft") or provenance.get("motif_code_draft")
    label = nested.get("label") or provenance.get("categorySuggestionLabel") or provenance.get("legacyCategory") or provenance.get("legacy_category")
    code = str(code).strip() if code is not None else ""
    label = str(label).strip() if label is not None else ""
    if code and not label:
        label = MOTIF_LABELS.get(code, "")
    if code.casefold() == "unknown" and label in {"", "待分类", "未分类"}:
        return None, None
    return code or None, label or None


def _derived_rows(low_resolution_edge: int) -> list[dict[str, Any]]:
    with database(get_settings()) as connection:
        patterns = [row_to_dict(row) for row in connection.execute("SELECT * FROM patterns ORDER BY id").fetchall()]
    name_counts = Counter(_name_key(row["name"]) for row in patterns if _name_key(row["name"]))
    result = []
    for row in patterns:
        source = row.get("source") if isinstance(row.get("source"), dict) else {}
        provenance = source.get("seedProvenance", {})
        provenance = provenance if isinstance(provenance, dict) else {}
        width, height = _positive_int(provenance.get("width")), _positive_int(provenance.get("height"))
        code, label = _suggestion(provenance)
        key = _name_key(row["name"])
        candidate = provenance.get("candidateName") or provenance.get("candidate_name")
        canonical = provenance.get("canonicalName") or provenance.get("canonical_name")
        risk_flags = provenance.get("riskFlags") or provenance.get("risk_flags") or []
        if isinstance(risk_flags, str):
            risk_flags = risk_flags.split("|")
        name_pending = not row["name"].strip() or (candidate and not canonical) or "name_unverified" in risk_flags or "name_needs_review" in risk_flags
        item = {
            "patternId": row["id"], "name": row["name"], "category": row["category"],
            "imageUrl": row["imageUrl"], "status": row["status"], "visibility": row["visibility"],
            "width": width, "height": height,
            "lowResolution": width is None or height is None or min(width, height) < low_resolution_edge,
            "nameNeedsReview": bool(name_pending), "duplicateName": bool(key and name_counts[key] > 1),
            "duplicateNameCount": name_counts[key] if key else 0,
            "categoryNeedsReview": row["category"].strip().casefold() in UNCATEGORIZED,
            "categorySuggestionCode": code, "categorySuggestionLabel": label,
        }
        result.append(item)
    return result


def _matches(item: dict[str, Any], queue: ReviewQueueKind) -> bool:
    return queue == "all" or {
        "low_resolution": item["lowResolution"], "name_review": item["nameNeedsReview"],
        "duplicate_name": item["duplicateName"], "uncategorized": item["categoryNeedsReview"],
        "category_suggestion": bool(item["categorySuggestionCode"] or item["categorySuggestionLabel"]),
    }.get(queue, False)


@router.get("/summary", response_model=CatalogReviewQueueSummary)
def review_queue_summary(low_resolution_edge: int = Query(256, alias="lowResolutionEdge", ge=1, le=10000)) -> CatalogReviewQueueSummary:
    rows = _derived_rows(low_resolution_edge)
    return CatalogReviewQueueSummary(total=len(rows), lowResolution=sum(x["lowResolution"] for x in rows),
        nameNeedsReview=sum(x["nameNeedsReview"] for x in rows), duplicateName=sum(x["duplicateName"] for x in rows),
        uncategorized=sum(x["categoryNeedsReview"] for x in rows),
        categorySuggestion=sum(bool(x["categorySuggestionCode"] or x["categorySuggestionLabel"]) for x in rows),
        lowResolutionEdge=low_resolution_edge)


@router.get("/patterns", response_model=CatalogReviewQueuePage)
def list_review_queue(queue: ReviewQueueKind = "all", page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100), q: str | None = Query(None, max_length=100),
    suggestion: str | None = Query(None, max_length=100),
    low_resolution_edge: int = Query(256, alias="lowResolutionEdge", ge=1, le=10000)) -> CatalogReviewQueuePage:
    rows = [item for item in _derived_rows(low_resolution_edge) if _matches(item, queue)]
    if q:
        needle = q.casefold()
        rows = [x for x in rows if needle in x["name"].casefold() or needle in x["category"].casefold()]
    if suggestion:
        needle = suggestion.casefold()
        rows = [x for x in rows if needle in (x["categorySuggestionCode"] or "").casefold() or needle in (x["categorySuggestionLabel"] or "").casefold()]
    rows.sort(key=lambda x: (x["name"].casefold(), x["patternId"]))
    total, offset = len(rows), (page - 1) * page_size
    return CatalogReviewQueuePage(items=[CatalogReviewQueueItem.model_validate(x) for x in rows[offset:offset + page_size]],
        page=page, pageSize=page_size, total=total, pages=math.ceil(total / page_size) if total else 0)
