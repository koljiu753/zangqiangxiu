from pathlib import Path

import httpx
import pytest

from app.ai_sync import AISyncError, sync_publication
from app.config import Settings


def configured() -> Settings:
    return Settings(Path("unused.db"), "sqlite", None, "production", "admin", (), "http://ai:8002/v1", "service-secret", 3.0)


def test_sync_uses_idempotent_publication_contract(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

    def put(url, **kwargs):
        captured.update(url=url, **kwargs)
        return Response()

    monkeypatch.setattr(httpx, "put", put)
    assert sync_publication("pat_001", True, configured()) == "synchronized"
    assert captured["url"] == "http://ai:8002/v1/internal/references/by-pattern/pat_001/publication"
    assert captured["json"] == {"published": True}
    assert captured["headers"] == {"X-Service-Token": "service-secret"}
    assert captured["timeout"] == 3.0


def test_sync_translates_transport_failures(monkeypatch):
    def fail(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "put", fail)
    with pytest.raises(AISyncError, match="AI synchronization failed"):
        sync_publication("pat_001", True, configured())
