import asyncio
import hashlib
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app.config import Settings
from app import evidence_storage


class FakeS3:
    def __init__(self):
        self.put = None

    def put_object(self, **kwargs):
        self.put = kwargs


def settings(tmp_path, max_bytes=1024):
    return Settings(
        database_path=tmp_path / "db", database_backend="sqlite", database_url=None,
        environment="development", admin_token="token", cors_origins=(),
        s3_bucket="bucket", s3_endpoint_url="http://minio", s3_access_key="key",
        s3_secret_key="secret", s3_prefix="test/catalog-evidence", evidence_max_bytes=max_bytes,
    )


def upload(name, content_type, body):
    return UploadFile(BytesIO(body), filename=name, headers=Headers({"content-type": content_type}))


def test_store_upload_validates_magic_size_and_computes_hash(tmp_path, monkeypatch):
    fake = FakeS3()
    monkeypatch.setattr(evidence_storage, "_client", lambda _: fake)
    body = b"%PDF-1.7\nrights evidence"
    result = asyncio.run(evidence_storage.store_upload("pat_001", upload("授权书.pdf", "application/pdf", body), settings(tmp_path)))
    assert result.size_bytes == len(body)
    assert result.checksum_sha256 == hashlib.sha256(body).hexdigest()
    assert result.storage_key.startswith("test/catalog-evidence/pat_001/ev_")
    assert fake.put["Metadata"]["sha256"] == result.checksum_sha256
    assert fake.put["ContentType"] == "application/pdf"


@pytest.mark.parametrize("name,content_type,body,status", [
    ("fake.pdf", "application/pdf", b"not a pdf", 415),
    ("script.exe", "application/octet-stream", b"MZ", 415),
    ("large.png", "image/png", b"\x89PNG\r\n\x1a\n" + b"x" * 20, 413),
])
def test_store_upload_rejects_invalid_files(tmp_path, name, content_type, body, status):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(evidence_storage.store_upload("pat_001", upload(name, content_type, body), settings(tmp_path, 16)))
    assert exc.value.status_code == status
