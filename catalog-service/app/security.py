from secrets import compare_digest
import hashlib
import hmac
import time

from fastapi import Header, HTTPException, Request, status
from .config import get_settings


def _authenticate_admin(
    request: Request,
    x_admin_token: str | None,
    x_admin_actor: str | None,
    x_admin_timestamp: str | None,
    x_admin_signature: str | None,
    x_request_id: str | None,
    require_signature: bool = False,
) -> str:
    settings = get_settings()
    expected = settings.admin_token
    if not x_admin_token or not compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")
    signed = (x_admin_actor, x_admin_timestamp, x_admin_signature, x_request_id)
    if not any(signed) and not require_signature:
        return "service-admin"
    if not all(signed) or not settings.actor_signing_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid actor signature")
    if not x_admin_actor.strip() or len(x_admin_actor) > 200 or len(x_request_id) > 100:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid actor signature")
    try:
        timestamp = int(x_admin_timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid actor signature") from exc
    if abs(int(time.time()) - timestamp) > 300:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired actor signature")
    canonical = f"{x_admin_timestamp}\n{request.method.upper()}\n{request.url.path}\n{x_admin_actor}\n{x_request_id}"
    expected_signature = hmac.new(settings.actor_signing_secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    if not compare_digest(x_admin_signature, expected_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid actor signature")
    return x_admin_actor


def require_admin(
    request: Request,
    x_admin_token: str | None = Header(default=None),
    x_admin_actor: str | None = Header(default=None),
    x_admin_timestamp: str | None = Header(default=None),
    x_admin_signature: str | None = Header(default=None),
    x_request_id: str | None = Header(default=None),
) -> str:
    return _authenticate_admin(request, x_admin_token, x_admin_actor, x_admin_timestamp,
                               x_admin_signature, x_request_id)


def require_signed_admin(
    request: Request,
    x_admin_token: str | None = Header(default=None),
    x_admin_actor: str | None = Header(default=None),
    x_admin_timestamp: str | None = Header(default=None),
    x_admin_signature: str | None = Header(default=None),
    x_request_id: str | None = Header(default=None),
) -> str:
    """Authenticate an administrator and require a verified, attributable actor."""
    return _authenticate_admin(request, x_admin_token, x_admin_actor, x_admin_timestamp,
                               x_admin_signature, x_request_id, require_signature=True)
