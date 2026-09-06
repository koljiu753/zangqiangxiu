import json
import logging
import re
import time
import uuid
from contextvars import ContextVar

from fastapi import Request

REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
logger = logging.getLogger("zhixiu.access")


def current_request_id() -> str | None:
    return _request_id.get()


async def request_observability(request: Request, call_next):
    supplied = request.headers.get(REQUEST_ID_HEADER)
    request_id = supplied if supplied and _SAFE_REQUEST_ID.fullmatch(supplied) else str(uuid.uuid4())
    token = _request_id.set(request_id)
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
    except Exception as exc:
        logger.exception(json.dumps({"level": "error", "event": "request.failed", "service": "catalog", "request_id": request_id, "method": request.method, "path": request.url.path, "error_type": type(exc).__name__}, separators=(",", ":")))
        raise
    finally:
        logger.info(json.dumps({"level": "info", "event": "request.completed", "service": "catalog", "request_id": request_id, "method": request.method, "path": request.url.path, "status": status_code, "duration_ms": round((time.perf_counter() - started) * 1000, 2)}, separators=(",", ":")))
        _request_id.reset(token)
