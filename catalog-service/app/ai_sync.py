import httpx

from .config import Settings
from .observability import current_request_id


class AISyncError(RuntimeError):
    pass


def sync_publication(pattern_id: str, published: bool, settings: Settings) -> str:
    """Idempotently align one AI reference with the Catalog publication state."""
    if not settings.ai_internal_base_url:
        if settings.environment == "production":
            raise AISyncError("AI synchronization is not configured")
        return "not_configured"
    if not settings.ai_service_token:
        raise AISyncError("AI service token is not configured")
    url = f"{settings.ai_internal_base_url}/internal/references/by-pattern/{pattern_id}/publication"
    try:
        headers = {"X-Service-Token": settings.ai_service_token}
        if current_request_id():
            headers["X-Request-ID"] = current_request_id()
        response = httpx.put(
            url,
            json={"published": published},
            headers=headers,
            timeout=settings.ai_sync_timeout_seconds,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise AISyncError(f"AI synchronization failed: {exc}") from exc
    return "synchronized"
