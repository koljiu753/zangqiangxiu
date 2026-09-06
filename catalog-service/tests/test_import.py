import csv

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
