import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIXIU_AI_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ZHIXIU_AI_INTERNAL_TOKEN", "test-internal-token")
    from app.main import app
    with TestClient(app) as test_client:
        yield test_client
