import csv
import json

from app.db import database
from app.import_csv import import_candidates


def test_csv_import_forces_private_draft(tmp_path):
    source = tmp_path / "items.csv"
    fields = ["source_system", "legacy_type", "legacy_id", "candidate_name", "description", "tags", "asset_url", "type", "meaning", "color", "rights_status", "origin_claim", "status", "visibility", "review_issues"]
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow({"source_system": "legacy", "legacy_type": "card", "legacy_id": "1", "candidate_name": "测试纹", "status": "published", "visibility": "public", "review_issues": "rights_unverified|needs_review"})
    target = tmp_path / "catalog.db"
    assert import_candidates(source, target) == (1, 0)
    with database(target) as connection:
        row = connection.execute("SELECT status, visibility FROM patterns").fetchone()
    assert tuple(row) == ("draft", "internal_only")


def test_mvd_catalog_seed_fields_are_preserved_without_publishing(tmp_path):
    source = tmp_path / "catalog_seed.csv"
    fields = ["pattern_id", "asset_id", "candidate_name", "description", "origin_claim", "status", "visibility", "source_system", "source_locator", "object_key", "original_filename", "mime_type", "byte_size", "sha256", "motif_code_draft", "legacy_category", "risk_flags", "legal_basis", "allow_display", "allow_download", "allow_commercial", "allow_ai_training", "allow_derivatives"]
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow({"pattern_id": "pattern-1", "asset_id": "asset-1", "candidate_name": "测试纹", "status": "published", "visibility": "public", "source_system": "archive", "source_locator": "item/1", "object_key": "objects/1.png", "original_filename": "1.png", "mime_type": "image/png", "byte_size": "42", "sha256": "abc", "motif_code_draft": "animal", "legacy_category": "动物纹样", "risk_flags": "source_unverified|rights_unverified", "legal_basis": "unverified", "allow_display": "False", "allow_download": "True", "allow_commercial": "False", "allow_ai_training": "False", "allow_derivatives": "False"})
    target = tmp_path / "catalog.db"
    assert import_candidates(source, target) == (1, 0)
    with database(target) as connection:
        row = connection.execute("SELECT category,status,visibility,source_json,rights_json,review_json FROM patterns").fetchone()
    source_data, rights, review = (json.loads(row[index]) for index in (3, 4, 5))
    assert tuple(row[:3]) == ("动物纹样", "draft", "internal_only")
    assert source_data == {"system": "archive", "legacyType": None, "legacyId": None, "originClaim": "unknown", "sourceLocator": "item/1", "assetId": "asset-1", "objectKey": "objects/1.png", "originalFilename": "1.png", "mimeType": "image/png", "byteSize": 42, "sha256": "abc"}
    assert rights["status"] == "unverified"
    assert rights["allowDisplay"] is False
    assert rights["allowDownload"] is True
    assert review["issues"] == ["source_unverified", "rights_unverified"]
