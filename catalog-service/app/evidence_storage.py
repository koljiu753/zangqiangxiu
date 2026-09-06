import hashlib
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException, UploadFile

from .config import Settings


ALLOWED_TYPES = {
    "application/pdf": (".pdf",),
    "image/jpeg": (".jpg", ".jpeg"),
    "image/png": (".png",),
}


@dataclass(frozen=True)
class StoredEvidence:
    evidence_id: str
    filename: str
    content_type: str
    size_bytes: int
    storage_key: str
    checksum_sha256: str


def _client(settings: Settings):
    if not all((settings.s3_bucket, settings.s3_access_key, settings.s3_secret_key)):
        raise HTTPException(status_code=503, detail={"code": "evidence_storage_unavailable"})
    return boto3.client(
        "s3", endpoint_url=settings.s3_endpoint_url, region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key, aws_secret_access_key=settings.s3_secret_key,
    )


def _validate_signature(content_type: str, head: bytes) -> bool:
    return (
        (content_type == "application/pdf" and head.startswith(b"%PDF-"))
        or (content_type == "image/jpeg" and head.startswith(b"\xff\xd8\xff"))
        or (content_type == "image/png" and head.startswith(b"\x89PNG\r\n\x1a\n"))
    )


async def store_upload(pattern_id: str, upload: UploadFile, settings: Settings) -> StoredEvidence:
    content_type = (upload.content_type or "").lower()
    suffix = Path(upload.filename or "").suffix.lower()
    if content_type not in ALLOWED_TYPES or suffix not in ALLOWED_TYPES[content_type]:
        raise HTTPException(status_code=415, detail={"code": "unsupported_evidence_type", "allowed": list(ALLOWED_TYPES)})

    body = await upload.read(settings.evidence_max_bytes + 1)
    if not body:
        raise HTTPException(status_code=422, detail={"code": "empty_evidence_file"})
    if len(body) > settings.evidence_max_bytes:
        raise HTTPException(status_code=413, detail={"code": "evidence_file_too_large", "maxBytes": settings.evidence_max_bytes})
    if not _validate_signature(content_type, body[:16]):
        raise HTTPException(status_code=415, detail={"code": "evidence_signature_mismatch"})

    evidence_id = f"ev_{uuid.uuid4().hex}"
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", Path(upload.filename or "evidence").name)[:180]
    key = f"{settings.s3_prefix}/{pattern_id}/{evidence_id}{suffix}"
    digest = hashlib.sha256(body).hexdigest()
    try:
        _client(settings).put_object(
            Bucket=settings.s3_bucket, Key=key, Body=body, ContentType=content_type,
            Metadata={"sha256": digest, "original-filename": safe_name},
        )
    except ClientError as exc:
        raise HTTPException(status_code=502, detail={"code": "evidence_storage_write_failed"}) from exc
    return StoredEvidence(evidence_id, safe_name, content_type, len(body), key, digest)


def fetch_object(storage_key: str, settings: Settings):
    prefix = settings.s3_prefix.rstrip("/") + "/"
    if not storage_key.startswith(prefix) or ".." in storage_key:
        raise HTTPException(status_code=422, detail={"code": "invalid_evidence_storage_key"})
    try:
        return _client(settings).get_object(Bucket=settings.s3_bucket, Key=storage_key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        status_code = 404 if code in {"NoSuchKey", "404"} else 502
        raise HTTPException(status_code=status_code, detail={"code": "evidence_file_not_found" if status_code == 404 else "evidence_storage_read_failed"}) from exc


def delete_object(storage_key: str, settings: Settings) -> None:
    try:
        _client(settings).delete_object(Bucket=settings.s3_bucket, Key=storage_key)
    except ClientError:
        pass
