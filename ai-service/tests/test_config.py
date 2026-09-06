import pytest

from app.config import Settings, validate_settings


def test_postgres_requires_database_url(tmp_path):
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        validate_settings(Settings(data_dir=tmp_path, database_backend="postgresql"))


def test_production_s3_endpoint_requires_https(tmp_path):
    settings = Settings(data_dir=tmp_path, asset_backend="s3", environment="production",
                        s3_bucket="assets", s3_endpoint_url="http://storage.internal")
    with pytest.raises(RuntimeError, match="HTTPS"):
        validate_settings(settings)
