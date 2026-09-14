import json
from pathlib import Path

from fastapi import FastAPI


SERVICE_ROOT = Path(__file__).resolve().parents[1]


def test_vercel_entrypoint_exports_fastapi_app() -> None:
    from api.index import app

    assert isinstance(app, FastAPI)
    assert app.title == "Zhixiu AI Service"


def test_vercel_config_routes_every_path_to_entrypoint() -> None:
    config = json.loads((SERVICE_ROOT / "vercel.json").read_text(encoding="utf-8"))
    assert config["rewrites"] == [{"source": "/(.*)", "destination": "/api/index"}]
    assert config["functions"]["api/index.py"]["maxDuration"] == 300


def test_production_validation_still_requires_internal_token(monkeypatch) -> None:
    from app.config import get_settings, validate_settings

    monkeypatch.setenv("ZHIXIU_AI_ENVIRONMENT", "production")
    monkeypatch.delenv("ZHIXIU_AI_INTERNAL_TOKEN", raising=False)
    try:
        validate_settings(get_settings())
    except RuntimeError as exc:
        assert "ZHIXIU_AI_INTERNAL_TOKEN" in str(exc)
    else:
        raise AssertionError("Production accepted a missing internal token")
