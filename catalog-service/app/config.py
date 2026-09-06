from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path
    database_backend: str
    database_url: str | None
    environment: str
    admin_token: str
    cors_origins: tuple[str, ...]
    ai_internal_base_url: str | None = None
    ai_service_token: str | None = None
    ai_sync_timeout_seconds: float = 5.0
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_prefix: str = "development/catalog-evidence"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    evidence_max_bytes: int = 10 * 1024 * 1024
    actor_signing_secret: str | None = None


def get_settings() -> Settings:
    base = Path(__file__).resolve().parents[1]
    origins = os.getenv("CATALOG_CORS_ORIGINS", "http://localhost:3000")
    return Settings(
        database_path=Path(os.getenv("CATALOG_DATABASE_PATH", base / "catalog.db")),
        database_backend=os.getenv("CATALOG_DATABASE_BACKEND", "sqlite").strip().lower(),
        database_url=os.getenv("CATALOG_DATABASE_URL"),
        environment=os.getenv("CATALOG_ENVIRONMENT", "development").strip().lower(),
        admin_token=os.getenv("CATALOG_ADMIN_TOKEN", "dev-only-change-me"),
        cors_origins=tuple(item.strip() for item in origins.split(",") if item.strip()),
        actor_signing_secret=os.getenv("CATALOG_ACTOR_SIGNING_SECRET", "").strip() or None,
        ai_internal_base_url=os.getenv("CATALOG_AI_INTERNAL_BASE_URL", "").strip().rstrip("/") or None,
        ai_service_token=os.getenv("CATALOG_AI_SERVICE_TOKEN", "").strip() or None,
        ai_sync_timeout_seconds=float(os.getenv("CATALOG_AI_SYNC_TIMEOUT_SECONDS", "5")),
        s3_bucket=os.getenv("CATALOG_S3_BUCKET", "").strip() or None,
        s3_endpoint_url=os.getenv("CATALOG_S3_ENDPOINT_URL", "").strip() or None,
        s3_region=os.getenv("CATALOG_S3_REGION", "us-east-1").strip(),
        s3_prefix=os.getenv("CATALOG_S3_PREFIX", "development/catalog-evidence").strip().strip("/"),
        s3_access_key=os.getenv("CATALOG_S3_ACCESS_KEY", "").strip() or None,
        s3_secret_key=os.getenv("CATALOG_S3_SECRET_KEY", "").strip() or None,
        evidence_max_bytes=int(os.getenv("CATALOG_EVIDENCE_MAX_BYTES", str(10 * 1024 * 1024))),
    )


def validate_settings(settings: Settings) -> None:
    if settings.database_backend not in {"sqlite", "postgresql"}:
        raise RuntimeError("CATALOG_DATABASE_BACKEND must be 'sqlite' or 'postgresql'")
    if settings.database_backend == "postgresql" and not settings.database_url:
        raise RuntimeError("CATALOG_DATABASE_URL is required for PostgreSQL")
    if settings.environment == "production" and (len(settings.admin_token) < 32 or settings.admin_token.startswith(("dev-only", "change-me"))):
        raise RuntimeError("CATALOG_ADMIN_TOKEN must be overridden with a random value of at least 32 characters in production")
    if settings.environment == "production" and (not settings.actor_signing_secret or len(settings.actor_signing_secret) < 32):
        raise RuntimeError("CATALOG_ACTOR_SIGNING_SECRET must be at least 32 characters in production")
    if settings.environment == "production" and (not settings.ai_internal_base_url or not settings.ai_service_token):
        raise RuntimeError("CATALOG_AI_INTERNAL_BASE_URL and CATALOG_AI_SERVICE_TOKEN are required in production")
    if settings.ai_sync_timeout_seconds <= 0:
        raise RuntimeError("CATALOG_AI_SYNC_TIMEOUT_SECONDS must be positive")
    if settings.evidence_max_bytes <= 0:
        raise RuntimeError("CATALOG_EVIDENCE_MAX_BYTES must be positive")
    if settings.environment == "production" and not all((settings.s3_bucket, settings.s3_access_key, settings.s3_secret_key)):
        raise RuntimeError("CATALOG_S3_BUCKET, CATALOG_S3_ACCESS_KEY and CATALOG_S3_SECRET_KEY are required in production")
