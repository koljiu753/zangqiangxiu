import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from .config import get_settings
from .db import database, json_value, row_to_dict, timestamp_value
from .schemas import (
    BatchReviewAssignmentRequest,
    BatchReviewDecisionRequest,
    BulkReviewAssignmentRequest,
    ReviewTask,
    ReviewTaskPage,
    ReviewOperationsSummary,
    ReviewAssigneeSummary,
    ReviewOperationsItem,
    ReviewOperationsResponse,
    ReviewWorkflowItem,
    ReviewWorkflowResponse,
)
from .security import require_admin, require_signed_admin


router = APIRouter(prefix="/api/v1/admin/reviews", dependencies=[Depends(require_admin)])


def _task(row) -> ReviewTask:
    keys = row.keys()
    return ReviewTask(
        patternId=row["pattern_id"],
        patternName=row["pattern_name"] if "pattern_name" in keys else None,
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


@router.get("/tasks", response_model=ReviewTaskPage)
def list_review_tasks(
    assignee: str | None = Query(default=None, max_length=200),
    state: str | None = Query(default=None, pattern="^(assigned|approved|rejected|needs_more)$"),
    q: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
) -> ReviewTaskPage:
    clauses, params = ["1=1"], []
    if assignee:
        clauses.append("rt.assignee=?")
        params.append(assignee)
    if state:
        clauses.append("rt.state=?")
        params.append(state)
    if q and q.strip():
        needle = f"%{q.strip().lower()}%"
        clauses.append("(LOWER(p.name) LIKE ? OR LOWER(rt.pattern_id) LIKE ? OR LOWER(rt.assignee) LIKE ?)")
        params.extend([needle, needle, needle])
    where = " AND ".join(clauses)
    with database(get_settings()) as connection:
        total = connection.execute(
            f"SELECT COUNT(*) AS count FROM review_tasks rt JOIN patterns p ON p.id=rt.pattern_id WHERE {where}", params
        ).fetchone()["count"]
        rows = connection.execute(
            f"SELECT rt.*,p.name AS pattern_name FROM review_tasks rt JOIN patterns p ON p.id=rt.pattern_id "
            f"WHERE {where} ORDER BY rt.assigned_at DESC,rt.pattern_id ASC LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
    return ReviewTaskPage(items=[_task(row) for row in rows], page=page, pageSize=page_size,
                          total=total, totalPages=(total + page_size - 1) // page_size)


@router.get("/summary", response_model=ReviewOperationsSummary)
def review_operations_summary() -> ReviewOperationsSummary:
    """Summarize review progress for draft, internal-only patterns."""
    with database(get_settings()) as connection:
        rows = connection.execute(
            "SELECT rt.assignee,rt.state,COUNT(*) AS count FROM patterns p "
            "LEFT JOIN review_tasks rt ON rt.pattern_id=p.id "
            "WHERE p.status='draft' AND p.visibility='internal_only' "
            "GROUP BY rt.assignee,rt.state ORDER BY rt.assignee ASC,rt.state ASC"
        ).fetchall()
    states = {key: 0 for key in ("assigned", "approved", "rejected", "needs_more")}
    unassigned = 0
    grouped: dict[str, dict[str, int]] = {}
    for row in rows:
        count = int(row["count"])
        if row["assignee"] is None:
            unassigned += count
            continue
        assignee = row["assignee"]
        state = row["state"]
        states[state] += count
        grouped.setdefault(assignee, {key: 0 for key in states})[state] += count
    total = unassigned + sum(states.values())
    completed = states["approved"] + states["rejected"] + states["needs_more"]
    assignees = []
    for assignee, counts in sorted(grouped.items()):
        assignee_total = sum(counts.values())
        assignee_completed = counts["approved"] + counts["rejected"] + counts["needs_more"]
        assignees.append(ReviewAssigneeSummary(
            assignee=assignee, total=assignee_total, completed=assignee_completed,
            completionRate=round(assignee_completed * 100 / assignee_total, 2) if assignee_total else 0.0,
            assigned=counts["assigned"], approved=counts["approved"], rejected=counts["rejected"],
            needsMore=counts["needs_more"],
        ))
    return ReviewOperationsSummary(
        total=total, unassigned=unassigned, completed=completed,
        completionRate=round(completed * 100 / total, 2) if total else 0.0,
        assigned=states["assigned"], approved=states["approved"], rejected=states["rejected"],
        needsMore=states["needs_more"], assignees=assignees,
    )


@router.get("/operations", response_model=ReviewOperationsResponse)
def review_operations(
    assignee: str | None = Query(default=None, max_length=200),
    state: str | None = Query(default=None, pattern="^(unassigned|assigned|approved|rejected|needs_more)$"),
    q: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
) -> ReviewOperationsResponse:
    """Combined dashboard contract over every draft, internal-only pattern."""
    summary = review_operations_summary()
    clauses = ["p.status='draft'", "p.visibility='internal_only'"]
    params: list[object] = []
    if assignee:
        clauses.append("rt.assignee=?")
        params.append(assignee)
    if state == "unassigned":
        clauses.append("rt.pattern_id IS NULL")
    elif state:
        clauses.append("rt.state=?")
        params.append(state)
    if q and q.strip():
        needle = f"%{q.strip().lower()}%"
        clauses.append("(LOWER(p.name) LIKE ? OR LOWER(p.id) LIKE ? OR LOWER(COALESCE(rt.assignee,'')) LIKE ?)")
        params.extend([needle, needle, needle])
    where = " AND ".join(clauses)
    with database(get_settings()) as connection:
        total = int(connection.execute(
            f"SELECT COUNT(*) AS count FROM patterns p LEFT JOIN review_tasks rt ON rt.pattern_id=p.id WHERE {where}", params
        ).fetchone()["count"])
        rows = connection.execute(
            "SELECT p.id AS pattern_id,p.name AS pattern_name,rt.assignee,rt.state,rt.assigned_at,"
            "rt.decided_by,rt.decided_at FROM patterns p LEFT JOIN review_tasks rt ON rt.pattern_id=p.id "
            f"WHERE {where} ORDER BY CASE WHEN rt.assigned_at IS NULL THEN 1 ELSE 0 END,"
            "rt.assigned_at DESC,p.id ASC LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
    items = [ReviewOperationsItem(
        patternId=row["pattern_id"], patternName=row["pattern_name"], assignee=row["assignee"],
        state=row["state"] or "unassigned",
        assignedAt=timestamp_value(row["assigned_at"]) if row["assigned_at"] else None,
        decidedBy=row["decided_by"], decidedAt=timestamp_value(row["decided_at"]) if row["decided_at"] else None,
    ) for row in rows]
    return ReviewOperationsResponse(summary=summary, workloads=summary.assignees, items=items,
                                    page=page, pageSize=page_size, total=total,
                                    pages=(total + page_size - 1) // page_size)


@router.post("/batch-assign", response_model=ReviewWorkflowResponse)
def batch_assign(payload: BatchReviewAssignmentRequest, actor: str = Depends(require_signed_admin)) -> ReviewWorkflowResponse:
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


@router.post("/bulk-assign", response_model=ReviewWorkflowResponse)
def bulk_assign_filtered_patterns(
    payload: BulkReviewAssignmentRequest,
    actor: str = Depends(require_signed_admin),
) -> ReviewWorkflowResponse:
    """Assign a bounded caller-filtered ID set without deciding or publishing it."""
    fingerprint = _fingerprint("bulk_assign", payload.model_dump())
    with database(get_settings()) as connection:
        operation = connection.execute(
            "SELECT * FROM review_operations WHERE request_id=?", (payload.requestId,)
        ).fetchone()
        if operation:
            if operation["action"] != "bulk_assign" or operation["fingerprint"] != fingerprint:
                raise HTTPException(status_code=409, detail={
                    "code": "idempotency_conflict",
                    "message": "requestId was already used for a different operation",
                })
            response = ReviewWorkflowResponse.model_validate(json_value(operation["result_json"]))
            for item in response.items:
                item.replayed = True
            return response

        results: list[ReviewWorkflowItem] = []
        for pattern_id in payload.patternIds:
            pattern = connection.execute("SELECT status FROM patterns WHERE id=?", (pattern_id,)).fetchone()
            if pattern is None:
                results.append(ReviewWorkflowItem(patternId=pattern_id, status="failed", code="not_found", message="Pattern not found"))
                continue
            if pattern["status"] != "draft":
                results.append(ReviewWorkflowItem(patternId=pattern_id, status="failed", code="review_not_editable", message="Only draft patterns can enter review"))
                continue
            current = connection.execute("SELECT * FROM review_tasks WHERE pattern_id=?", (pattern_id,)).fetchone()
            before = _task(current).model_dump() if current else None
            if not current or current["assignee"] != payload.assignee or current["state"] != "assigned":
                if current:
                    connection.execute(
                        "UPDATE review_tasks SET assignee=?,state='assigned',decision_note=NULL,assigned_at=CURRENT_TIMESTAMP,decided_by=NULL,decided_at=NULL WHERE pattern_id=?",
                        (payload.assignee, pattern_id),
                    )
                else:
                    connection.execute(
                        "INSERT INTO review_tasks(pattern_id,assignee,state) VALUES (?,?,'assigned')",
                        (pattern_id, payload.assignee),
                    )
                current = connection.execute("SELECT * FROM review_tasks WHERE pattern_id=?", (pattern_id,)).fetchone()
                _audit(connection, pattern_id, "review_bulk_reassigned" if before else "review_bulk_assigned",
                       actor, before, _task(current).model_dump())
            results.append(ReviewWorkflowItem(patternId=pattern_id, status="succeeded", task=_task(current)))

        response = _response(results)
        connection.execute(
            "INSERT INTO review_operations(request_id,action,fingerprint,result_json) VALUES (?,?,?,?)",
            (payload.requestId, "bulk_assign", fingerprint, json.dumps(response.model_dump(), ensure_ascii=False)),
        )
        return response


@router.post("/batch-decide", response_model=ReviewWorkflowResponse)
def batch_decide(payload: BatchReviewDecisionRequest, actor: str = Depends(require_signed_admin)) -> ReviewWorkflowResponse:
    results: list[ReviewWorkflowItem] = []
    for item in payload.items:
        fingerprint = _fingerprint("decide", item.model_dump())
        try:
            if item.decidedBy != actor:
                raise HTTPException(status_code=403, detail={
                    "code": "actor_mismatch",
                    "message": "decidedBy must match the verified actor",
                })
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
                review.update({"issues": item.issues, "reviewedBy": actor, "reviewedAt": reviewed_at})
                connection.execute("UPDATE patterns SET review_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (json.dumps(review, ensure_ascii=False), item.patternId))
                connection.execute(
                    "UPDATE review_tasks SET state=?,decision_note=?,decided_by=?,decided_at=? WHERE pattern_id=?",
                    (item.decision, item.note, actor, reviewed_at, item.patternId),
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
