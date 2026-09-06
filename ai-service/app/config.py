from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_backend: str = "sqlite"
    asset_backend: str = "local"
    environment: str = "development"
    max_upload_bytes: int = 10 * 1024 * 1024
    max_image_pixels: int = 25_000_000
    palette_colors: int = 5
    cors_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")
    database_url: str | None = None
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None
    s3_region: str | None = None
    s3_prefix: str = "ai-assets"
    internal_token: str | None = None
    anonymous_uploads_per_minute: int = 30
    anonymous_analyses_per_minute: int = 60
    max_queued_jobs: int = 100
    anonymous_asset_ttl_hours: int = 24


def get_settings() -> Settings:
    default_data = Path(__file__).resolve().parents[1] / "data"
    origins = tuple(
        origin.strip()
        for origin in os.getenv(
            "ZHIXIU_AI_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",")
        if origin.strip()
    )
    return Settings(
        data_dir=Path(os.getenv("ZHIXIU_AI_DATA_DIR", default_data)).resolve(),
        database_backend=os.getenv("ZHIXIU_AI_DATABASE_BACKEND", "sqlite").strip().lower(),
        asset_backend=os.getenv("ZHIXIU_AI_ASSET_BACKEND", "local").strip().lower(),
        environment=os.getenv("ZHIXIU_AI_ENVIRONMENT", "development").strip().lower(),
        max_upload_bytes=int(os.getenv("ZHIXIU_AI_MAX_UPLOAD_BYTES", 10 * 1024 * 1024)),
        max_image_pixels=int(os.getenv("ZHIXIU_AI_MAX_IMAGE_PIXELS", 25_000_000)),
        cors_origins=origins,
        database_url=os.getenv("ZHIXIU_AI_DATABASE_URL"),
        s3_bucket=os.getenv("ZHIXIU_AI_S3_BUCKET"),
        s3_endpoint_url=os.getenv("ZHIXIU_AI_S3_ENDPOINT_URL"),
        s3_region=os.getenv("ZHIXIU_AI_S3_REGION"),
        s3_prefix=os.getenv("ZHIXIU_AI_S3_PREFIX", "ai-assets").strip("/"),
        internal_token=os.getenv("ZHIXIU_AI_INTERNAL_TOKEN"),
        anonymous_uploads_per_minute=int(os.getenv("ZHIXIU_AI_ANON_UPLOADS_PER_MINUTE", "30")),
        anonymous_analyses_per_minute=int(os.getenv("ZHIXIU_AI_ANON_ANALYSES_PER_MINUTE", "60")),
        max_queued_jobs=int(os.getenv("ZHIXIU_AI_MAX_QUEUED_JOBS", "100")),
        anonymous_asset_ttl_hours=int(os.getenv("ZHIXIU_AI_ANON_ASSET_TTL_HOURS", "24")),
    )


def validate_settings(settings: Settings) -> None:
    if settings.database_backend not in {"sqlite", "postgresql"}:
        raise RuntimeError("ZHIXIU_AI_DATABASE_BACKEND must be 'sqlite' or 'postgresql'")
    if settings.database_backend == "postgresql" and not settings.database_url:
        raise RuntimeError("ZHIXIU_AI_DATABASE_URL is required for PostgreSQL")
    if settings.asset_backend not in {"local", "s3"}:
        raise RuntimeError("ZHIXIU_AI_ASSET_BACKEND must be 'local' or 's3'")
    if settings.asset_backend == "s3" and not settings.s3_bucket:
        raise RuntimeError("ZHIXIU_AI_S3_BUCKET is required for S3 storage")
    if (settings.environment == "production" and settings.s3_endpoint_url
            and not settings.s3_endpoint_url.startswith("https://")):
        raise RuntimeError("Production S3 endpoints must use HTTPS")
    if settings.environment == "production" and not settings.internal_token:
        raise RuntimeError("ZHIXIU_AI_INTERNAL_TOKEN is required in production")
    for name in ("anonymous_uploads_per_minute", "anonymous_analyses_per_minute",
                 "max_queued_jobs", "anonymous_asset_ttl_hours"):
        if getattr(settings, name) < 0:
            raise RuntimeError(f"{name} must be non-negative")
