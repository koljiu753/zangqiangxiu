import json
from pathlib import Path

from fastapi import FastAPI


SERVICE_ROOT = Path(__file__).resolve().parents[1]


def test_vercel_entrypoint_exports_fastapi_app() -> None:
    from api.index import app

    assert isinstance(app, FastAPI)
    assert app.title == "Zhixiu Pattern Catalog"


def test_vercel_config_routes_every_path_to_entrypoint() -> None:
    config = json.loads((SERVICE_ROOT / "vercel.json").read_text(encoding="utf-8"))
    assert config["rewrites"] == [{"source": "/(.*)", "destination": "/api/index"}]
    assert config["functions"]["api/index.py"]["maxDuration"] == 300


def test_production_validation_is_not_bypassed(monkeypatch) -> None:
    from app.config import get_settings, validate_settings

    monkeypatch.setenv("CATALOG_ENVIRONMENT", "production")
    monkeypatch.setenv("CATALOG_ADMIN_TOKEN", "dev-only-change-me")
    try:
        validate_settings(get_settings())
    except RuntimeError as exc:
        assert "CATALOG_ADMIN_TOKEN" in str(exc)
    else:
        raise AssertionError("Production accepted the development admin token")
