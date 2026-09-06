import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from .config import get_settings
from .db import database, json_value, row_to_dict, timestamp_value
from .schemas import (
    BatchReviewAssignmentRequest,
    BatchReviewDecisionRequest,
    ReviewTask,
    ReviewWorkflowItem,
    ReviewWorkflowResponse,
)
from .security import require_admin


router = APIRouter(prefix="/api/v1/admin/reviews", dependencies=[Depends(require_admin)])


def _task(row) -> ReviewTask:
    return ReviewTask(
        patternId=row["pattern_id"],
        assignee=row["assignee"],
        state=row["state"],
        decisionNote=row["decision_note"],
        assignedAt=timestamp_value(row["assigned_at"]),
        decidedBy=row["decided_by"],
        decidedAt=timestamp_value(row["decided_at"]) if row["decided_at"] else None,
    )


def _fingerprint(action: str, item: dict) -> str:
    body = json.dumps({"action": action, **item}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _replay(connection, request_id: str, action: str, fingerprint: str) -> ReviewWorkflowItem | None:
    row = connection.execute("SELECT * FROM review_operations WHERE request_id=?", (request_id,)).fetchone()
    if row is None:
        return None
    if row["action"] != action or row["fingerprint"] != fingerprint:
        raise HTTPException(status_code=409, detail={
            "code": "idempotency_conflict",
            "message": "requestId was already used for a different operation",
        })
    result = json_value(row["result_json"])
    result["replayed"] = True
    return ReviewWorkflowItem.model_validate(result)


def _save(connection, request_id: str, action: str, fingerprint: str, result: ReviewWorkflowItem) -> None:
    connection.execute(
        "INSERT INTO review_operations(request_id,action,fingerprint,result_json) VALUES (?,?,?,?)",
        (request_id, action, fingerprint, json.dumps(result.model_dump(), ensure_ascii=False)),
    )


def _audit(connection, pattern_id: str, action: str, actor: str, before: dict | None, after: dict) -> None:
    connection.execute(
        "INSERT INTO audit_logs(pattern_id,action,actor,before_json,after_json) VALUES (?,?,?,?,?)",
        (pattern_id, action, actor, json.dumps(before, ensure_ascii=False) if before else None,
         json.dumps(after, ensure_ascii=False)),
    )


def _failure(pattern_id: str, exc: Exception) -> ReviewWorkflowItem:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, dict):
            return ReviewWorkflowItem(patternId=pattern_id, status="failed", code=str(detail.get("code", "operation_failed")), message=str(detail.get("message", detail)))
        return ReviewWorkflowItem(patternId=pattern_id, status="failed", code="not_found" if exc.status_code == 404 else "operation_failed", message=str(detail))
    return ReviewWorkflowItem(patternId=pattern_id, status="failed", code="operation_failed", message=str(exc))


def _response(items: list[ReviewWorkflowItem]) -> ReviewWorkflowResponse:
    succeeded = sum(item.status == "succeeded" for item in items)
    return ReviewWorkflowResponse(succeeded=succeeded, failed=len(items) - succeeded, items=items)


@router.get("/tasks", response_model=list[ReviewTask])
def list_review_tasks(
    assignee: str | None = Query(default=None, max_length=200),
    state: str | None = Query(default=None, pattern="^(assigned|approved|rejected|needs_more)$"),
) -> list[ReviewTask]:
    clauses, params = ["1=1"], []
    if assignee:
        clauses.append("assignee=?")
        params.append(assignee)
    if state:
        clauses.append("state=?")
        params.append(state)
    with database(get_settings()) as connection:
        rows = connection.execute(
            f"SELECT * FROM review_tasks WHERE {' AND '.join(clauses)} ORDER BY assigned_at DESC, pattern_id",
            params,
        ).fetchall()
    return [_task(row) for row in rows]


@router.post("/batch-assign", response_model=ReviewWorkflowResponse)
def batch_assign(payload: BatchReviewAssignmentRequest, actor: str = Depends(require_admin)) -> ReviewWorkflowResponse:
    results: list[ReviewWorkflowItem] = []
    for item in payload.items:
        fingerprint = _fingerprint("assign", item.model_dump())
        try:
            with database(get_settings()) as connection:
                replayed = _replay(connection, item.requestId, "assign", fingerprint)
                if replayed:
                    results.append(replayed)
                    continue
                pattern = connection.execute("SELECT status FROM patterns WHERE id=?", (item.patternId,)).fetchone()
                if pattern is None:
                    raise HTTPException(status_code=404, detail="Pattern not found")
                if pattern["status"] != "draft":
                    raise HTTPException(status_code=409, detail={"code": "review_not_editable", "message": "Only draft patterns can enter review"})
                current = connection.execute("SELECT * FROM review_tasks WHERE pattern_id=?", (item.patternId,)).fetchone()
                before = _task(current).model_dump() if current else None
                if not current or current["assignee"] != item.assignee or current["state"] != "assigned":
                    if current:
                        connection.execute(
                            "UPDATE review_tasks SET assignee=?,state='assigned',decision_note=NULL,assigned_at=CURRENT_TIMESTAMP,decided_by=NULL,decided_at=NULL WHERE pattern_id=?",
                            (item.assignee, item.patternId),
                        )
                    else:
                        connection.execute("INSERT INTO review_tasks(pattern_id,assignee,state) VALUES (?,?,'assigned')", (item.patternId, item.assignee))
                    current = connection.execute("SELECT * FROM review_tasks WHERE pattern_id=?", (item.patternId,)).fetchone()
                    _audit(connection, item.patternId, "review_reassigned" if before else "review_assigned", actor, before, _task(current).model_dump())
                task = _task(current)
                result = ReviewWorkflowItem(patternId=item.patternId, status="succeeded", task=task)
                _save(connection, item.requestId, "assign", fingerprint, result)
            results.append(result)
        except Exception as exc:
            results.append(_failure(item.patternId, exc))
    return _response(results)


@router.post("/batch-decide", response_model=ReviewWorkflowResponse)
def batch_decide(payload: BatchReviewDecisionRequest, actor: str = Depends(require_admin)) -> ReviewWorkflowResponse:
    results: list[ReviewWorkflowItem] = []
    for item in payload.items:
        fingerprint = _fingerprint("decide", item.model_dump())
        try:
            if item.decision == "approved" and item.issues:
                raise HTTPException(status_code=422, detail={"code": "invalid_review_decision", "message": "Approved reviews cannot contain issues"})
            if item.decision != "approved" and not item.issues:
                raise HTTPException(status_code=422, detail={"code": "invalid_review_decision", "message": "Rejected or needs-more decisions require at least one issue"})
            with database(get_settings()) as connection:
                replayed = _replay(connection, item.requestId, "decide", fingerprint)
                if replayed:
                    results.append(replayed)
                    continue
                pattern_row = connection.execute("SELECT * FROM patterns WHERE id=?", (item.patternId,)).fetchone()
                if pattern_row is None:
                    raise HTTPException(status_code=404, detail="Pattern not found")
                if pattern_row["status"] != "draft":
                    raise HTTPException(status_code=409, detail={"code": "review_not_editable", "message": "Only draft patterns can be reviewed"})
                task_row = connection.execute("SELECT * FROM review_tasks WHERE pattern_id=?", (item.patternId,)).fetchone()
                if task_row is None:
                    raise HTTPException(status_code=409, detail={"code": "review_not_assigned", "message": "Assign a reviewer before recording a decision"})
                if task_row["assignee"] != item.decidedBy:
                    raise HTTPException(status_code=403, detail={"code": "reviewer_mismatch", "message": "Only the assigned reviewer may record the decision"})
                before_pattern = row_to_dict(pattern_row)
                before_task = _task(task_row).model_dump()
                reviewed_at = datetime.now(timezone.utc).isoformat()
                review = dict(before_pattern.get("review") or {})
                review.update({"issues": item.issues, "reviewedBy": item.decidedBy, "reviewedAt": reviewed_at})
                connection.execute("UPDATE patterns SET review_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (json.dumps(review, ensure_ascii=False), item.patternId))
                connection.execute(
                    "UPDATE review_tasks SET state=?,decision_note=?,decided_by=?,decided_at=? WHERE pattern_id=?",
                    (item.decision, item.note, item.decidedBy, reviewed_at, item.patternId),
                )
                task_row = connection.execute("SELECT * FROM review_tasks WHERE pattern_id=?", (item.patternId,)).fetchone()
                task = _task(task_row)
                after_pattern = row_to_dict(connection.execute("SELECT * FROM patterns WHERE id=?", (item.patternId,)).fetchone())
                _audit(connection, item.patternId, f"review_{item.decision}", actor,
                       {"pattern": before_pattern, "task": before_task}, {"pattern": after_pattern, "task": task.model_dump()})
                result = ReviewWorkflowItem(patternId=item.patternId, status="succeeded", task=task)
                _save(connection, item.requestId, "decide", fingerprint, result)
            results.append(result)
        except Exception as exc:
            results.append(_failure(item.patternId, exc))
    return _response(results)
