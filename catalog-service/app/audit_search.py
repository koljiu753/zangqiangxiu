import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from .config import get_settings
from .db import database, json_value, scalar, timestamp_value
from .schemas import AuditLog, AuditLogPage
from .security import require_admin


router = APIRouter(prefix="/api/v1/admin/audit-logs", tags=["admin-audit"])


def _database_timestamp(value: datetime) -> str:
    """Use one UTC representation that SQLite and PostgreSQL can both compare."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f+00:00")


def _utc_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _audit_log(row) -> AuditLog:
    return AuditLog(
        id=row["id"],
        patternId=row["pattern_id"],
        action=row["action"],
        actor=row["actor"],
        before=json_value(row["before_json"]) if row["before_json"] else None,
        after=json_value(row["after_json"]) if row["after_json"] else None,
        createdAt=timestamp_value(row["created_at"]),
    )


@router.get("", response_model=AuditLogPage, dependencies=[Depends(require_admin)])
def search_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    actor: str | None = Query(default=None, min_length=1, max_length=200),
    action: str | None = Query(default=None, min_length=1, max_length=200),
    pattern_id: str | None = Query(default=None, alias="patternId", min_length=1, max_length=100),
    q: str | None = Query(default=None, min_length=1, max_length=100),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
) -> AuditLogPage:
    if from_ and to and _utc_datetime(from_) > _utc_datetime(to):
        raise HTTPException(status_code=422, detail={"code": "invalid_audit_range", "message": "from must not be later than to"})

    clauses: list[str] = ["1=1"]
    params: list[object] = []
    for column, value in (("actor", actor), ("action", action), ("pattern_id", pattern_id)):
        if value:
            clauses.append(f"{column} = ?")
            params.append(value)
    if q:
        escaped = q.lower().replace("!", "!!").replace("%", "!%").replace("_", "!_")
        clauses.append("(LOWER(actor) LIKE ? ESCAPE '!' OR LOWER(action) LIKE ? ESCAPE '!' OR LOWER(pattern_id) LIKE ? ESCAPE '!')")
        params.extend([f"%{escaped}%"] * 3)
    if from_:
        clauses.append("created_at >= ?")
        params.append(_database_timestamp(from_))
    if to:
        clauses.append("created_at <= ?")
        params.append(_database_timestamp(to))

    where = " AND ".join(clauses)
    settings = get_settings()
    with database(settings) as connection:
        total = int(scalar(connection.execute(f"SELECT COUNT(*) FROM audit_logs WHERE {where}", params).fetchone()))
        rows = connection.execute(
            f"SELECT * FROM audit_logs WHERE {where} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
    return AuditLogPage(
        items=[_audit_log(row) for row in rows],
        page=page,
        pageSize=page_size,
        total=total,
        pages=math.ceil(total / page_size) if total else 0,
    )
