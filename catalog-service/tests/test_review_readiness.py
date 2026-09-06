import csv
import json

from app.db import database, initialize
from app.review_readiness import apply_verified_sources, build_report, write_reports


FIELDS = ["pattern_id", "candidate_name", "canonical_name", "original_path", "source_locator", "object_key", "sha256", "byte_size", "width", "height", "motif_code_draft", "legacy_category", "risk_flags"]


def seed_file(path):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader()
        writer.writerow({"pattern_id": "p2", "candidate_name": "云纹", "original_path": "zip/a/y.png", "source_locator": "zip/a/y.png", "object_key": f"original/bb/{'b' * 64}.png", "sha256": "b" * 64, "byte_size": "20", "width": "500", "height": "500", "motif_code_draft": "nature"})
        writer.writerow({"pattern_id": "p1", "candidate_name": "云纹", "original_path": "zip/a/x.png", "source_locator": "zip/a/x.png", "object_key": f"original/aa/{'a' * 64}.png", "sha256": "a" * 64, "byte_size": "10", "width": "120", "height": "300", "motif_code_draft": "geometry", "risk_flags": "source_unverified"})


def add_pattern(db, pattern_id="p1"):
    initialize(db)
    with database(db) as connection:
        connection.execute("INSERT INTO patterns(id,name,category,source_json,rights_json,status,visibility) VALUES(?,?,?,?,?,?,?)", (pattern_id, "旧名", "待分类", json.dumps({"system": "csv"}), json.dumps({"status": "unverified"}), "draft", "internal_only"))


def test_report_is_deterministic_and_flags_review_risks(tmp_path):
    seed, db = tmp_path / "seed.csv", tmp_path / "db.sqlite"
    seed_file(seed); add_pattern(db)
    rows = build_report(seed, db)
    assert [row["pattern_id"] for row in rows] == ["p1", "p2"]
    assert rows[0]["category_suggestion_label"] == "几何"
    assert rows[0]["low_resolution"] is True
    assert rows[0]["name_needs_review"] is True
    assert rows[0]["duplicate_name_group"] is True
    assert "database_record_missing" in rows[1]["risk_flags"]
    first = write_reports(rows, tmp_path / "out")[1].read_bytes()
    second = write_reports(build_report(seed, db), tmp_path / "out")[1].read_bytes()
    assert first == second


def test_apply_only_merges_source_and_is_idempotent(tmp_path):
    seed, db = tmp_path / "seed.csv", tmp_path / "db.sqlite"
    seed_file(seed); add_pattern(db)
    rows = build_report(seed, db)
    assert apply_verified_sources(rows, db) == 1
    assert apply_verified_sources(rows, db) == 0
    with database(db) as connection:
        pattern = dict(connection.execute("SELECT * FROM patterns WHERE id='p1'").fetchone())
        logs = connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
    assert pattern["status"] == "draft" and pattern["visibility"] == "internal_only"
    assert json.loads(pattern["rights_json"]) == {"status": "unverified"}
    assert pattern["category"] == "待分类"
    provenance = json.loads(pattern["source_json"])["seedProvenance"]
    assert provenance["sha256"] == "a" * 64
    assert provenance["candidateName"] == "云纹"
    assert "canonicalName" not in provenance
    assert provenance["categorySuggestion"] == {"code": "geometry", "label": "几何"}
    assert "name_needs_review" in provenance["riskFlags"]
    assert logs == 1


def test_apply_skips_unverifiable_provenance(tmp_path):
    seed, db = tmp_path / "seed.csv", tmp_path / "db.sqlite"
    seed_file(seed); add_pattern(db)
    rows = build_report(seed, db)
    rows[0]["object_key"] = "original/not-the-hash.png"
    assert apply_verified_sources(rows, db) == 0
    with database(db) as connection:
        source = json.loads(connection.execute("SELECT source_json FROM patterns WHERE id='p1'").fetchone()[0])
    assert source == {"system": "csv"}
