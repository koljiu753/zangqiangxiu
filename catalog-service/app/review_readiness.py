"""Build a deterministic, safe review-preparation report from the MVD seed."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .config import Settings, get_settings
from .db import database, json_value


REPORT_FIELDS = (
    "pattern_id", "database_match", "database_name", "database_category",
    "candidate_name", "canonical_name", "original_path", "source_locator",
    "object_key", "sha256", "byte_size", "width", "height",
    "category_suggestion_code", "category_suggestion_label", "low_resolution",
    "name_needs_review", "duplicate_name_group", "duplicate_hash_group",
    "risk_flags",
)

MOTIF_LABELS = {
    "plant": "植物", "animal": "动物", "nature": "自然天象", "geometry": "几何",
    "symbol": "文字符号", "object_religious": "器物宗教", "composite": "复合",
    "unknown": "待分类",
}


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except ValueError:
        return None


def _name_key(value: str) -> str:
    return "".join(value.split()).casefold()


def _provenance_is_verifiable(row: dict[str, Any]) -> bool:
    digest = str(row.get("sha256") or "").lower()
    locator = str(row.get("source_locator") or "")
    original = str(row.get("original_path") or "")
    object_key = str(row.get("object_key") or "")
    return bool(
        re.fullmatch(r"[0-9a-f]{64}", digest)
        and locator and locator == original
        and digest in object_key
        and all(isinstance(row.get(key), int) and row[key] > 0 for key in ("byte_size", "width", "height"))
    )


def build_report(seed_path: Path, database_target: Settings | Path, low_res_edge: int = 256) -> list[dict[str, Any]]:
    """Return seed-order-independent rows. This function never changes the database."""
    with seed_path.open("r", encoding="utf-8-sig", newline="") as handle:
        seeds = list(csv.DictReader(handle))

    db_rows: dict[str, dict[str, Any]] = {}
    with database(database_target) as connection:
        for row in connection.execute("SELECT id,name,category,source_json FROM patterns").fetchall():
            item = dict(row)
            item["source"] = json_value(item.pop("source_json"))
            db_rows[item["id"]] = item

    name_counts = Counter(
        _name_key((row.get("canonical_name") or row.get("candidate_name") or "").strip())
        for row in seeds
        if (row.get("canonical_name") or row.get("candidate_name") or "").strip()
    )
    hash_counts = Counter(row.get("sha256", "").strip().lower() for row in seeds if row.get("sha256", "").strip())
    rows: list[dict[str, Any]] = []
    for seed in seeds:
        pattern_id = seed.get("pattern_id", "").strip()
        current = db_rows.get(pattern_id)
        candidate = seed.get("candidate_name", "").strip()
        canonical = seed.get("canonical_name", "").strip()
        display_name = canonical or candidate
        width, height = _int(seed.get("width")), _int(seed.get("height"))
        digest = seed.get("sha256", "").strip().lower()
        name_needs_review = not canonical or "name_unverified" in seed.get("risk_flags", "").split("|")
        low_resolution = width is None or height is None or min(width, height) < low_res_edge
        duplicate_name = bool(display_name and name_counts[_name_key(display_name)] > 1)
        duplicate_hash = bool(digest and hash_counts[digest] > 1)
        risks = {flag for flag in seed.get("risk_flags", "").split("|") if flag}
        if low_resolution: risks.add("low_resolution")
        if name_needs_review: risks.add("name_needs_review")
        if duplicate_name: risks.add("duplicate_name_group")
        if duplicate_hash: risks.add("duplicate_hash_group")
        if current is None: risks.add("database_record_missing")
        code = seed.get("motif_code_draft", "").strip() or "unknown"
        report_row = {
            "pattern_id": pattern_id,
            "database_match": current is not None,
            "database_name": current["name"] if current else "",
            "database_category": current["category"] if current else "",
            "candidate_name": candidate,
            "canonical_name": canonical,
            "original_path": seed.get("original_path", "").strip(),
            "source_locator": seed.get("source_locator", "").strip(),
            "object_key": seed.get("object_key", "").strip(),
            "sha256": digest,
            "byte_size": _int(seed.get("byte_size")), "width": width, "height": height,
            "category_suggestion_code": code,
            "category_suggestion_label": MOTIF_LABELS.get(code, seed.get("legacy_category", "").strip() or "待分类"),
            "low_resolution": low_resolution,
            "name_needs_review": name_needs_review,
            "duplicate_name_group": duplicate_name,
            "duplicate_hash_group": duplicate_hash,
            "risk_flags": "|".join(sorted(risks)),
        }
        if not _provenance_is_verifiable(report_row):
            risks.add("source_provenance_invalid")
            report_row["risk_flags"] = "|".join(sorted(risks))
        rows.append(report_row)
    return sorted(rows, key=lambda row: (row["pattern_id"], row["sha256"]))


def apply_verified_sources(rows: list[dict[str, Any]], database_target: Settings | Path, actor: str = "review-readiness") -> int:
    """Merge only verifiable seed provenance into source_json; never update workflow or rights."""
    changed = 0
    with database(database_target) as connection:
        for row in rows:
            if not _provenance_is_verifiable(row):
                continue
            existing = connection.execute("SELECT source_json FROM patterns WHERE id=?", (row["pattern_id"],)).fetchone()
            if existing is None:
                continue
            before = json_value(existing["source_json"] if hasattr(existing, "keys") else existing[0])
            source = dict(before or {})
            verified = {
                "locator": row["source_locator"], "originalPath": row["original_path"],
                "objectKey": row["object_key"], "sha256": row["sha256"],
                "byteSize": row["byte_size"], "width": row["width"], "height": row["height"],
            }
            verified = {key: value for key, value in verified.items() if value not in (None, "")}
            source["seedProvenance"] = verified
            if source == before:
                continue
            connection.execute("UPDATE patterns SET source_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (json.dumps(source, ensure_ascii=False, sort_keys=True), row["pattern_id"]))
            connection.execute(
                "INSERT INTO audit_logs(pattern_id,action,actor,before_json,after_json) VALUES(?,?,?,?,?)",
                (row["pattern_id"], "review_readiness_source_backfill", actor, json.dumps(before, ensure_ascii=False, sort_keys=True), json.dumps(source, ensure_ascii=False, sort_keys=True)),
            )
            changed += 1
    return changed


def write_reports(rows: list[dict[str, Any]], output: Path) -> tuple[Path, Path]:
    output.mkdir(parents=True, exist_ok=True)
    csv_path, json_path = output / "review_readiness.csv", output / "review_readiness.json"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_FIELDS)
        writer.writeheader(); writer.writerows(rows)
    summary = {
        "record_count": len(rows),
        "risk_counts": dict(sorted(Counter(flag for row in rows for flag in row["risk_flags"].split("|") if flag).items())),
        "records": rows,
    }
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return csv_path, json_path


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Generate the MVD data-review readiness report (dry-run by default)")
    parser.add_argument("--seed", type=Path, default=root / "data/output/mvd/catalog_seed.csv")
    parser.add_argument("--output", type=Path, default=root / "data/output/mvd/review-readiness")
    parser.add_argument("--database", type=Path, help="SQLite path override (otherwise environment settings are used)")
    parser.add_argument("--low-res-edge", type=int, default=256)
    parser.add_argument("--apply", action="store_true", help="Backfill verified source provenance only")
    args = parser.parse_args()
    if args.low_res_edge <= 0: parser.error("--low-res-edge must be positive")
    target = args.database or get_settings()
    rows = build_report(args.seed, target, args.low_res_edge)
    csv_path, json_path = write_reports(rows, args.output)
    changed = apply_verified_sources(rows, target) if args.apply else 0
    print(f"review readiness: records={len(rows)}, applied={changed}, mode={'apply' if args.apply else 'dry-run'}, csv={csv_path}, json={json_path}")


if __name__ == "__main__":
    main()
