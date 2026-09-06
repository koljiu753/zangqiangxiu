import argparse
import csv
import hashlib
import json
from pathlib import Path

from .config import Settings, get_settings
from .db import database, initialize


def stable_id(row: dict[str, str]) -> str:
    if row.get("pattern_id"):
        return row["pattern_id"]
    identity = f"{row.get('source_system','')}:{row.get('legacy_type','')}:{row.get('legacy_id','')}:{row.get('candidate_name','')}"
    return f"import_{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:20]}"


def infer_ethnicity(row: dict[str, str]) -> str:
    text = f"{row.get('candidate_name','')} {row.get('description','')} {row.get('tags','')}"
    if "羌" in text and "藏" not in text:
        return "羌族"
    if "藏" in text and "羌" not in text:
        return "藏族"
    return "unknown"


def split_values(value: str) -> list[str]:
    return [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]


def import_candidates(csv_path: Path, database_target: Settings | Path) -> tuple[int, int]:
    initialize(database_target)
    inserted = updated = 0
    with csv_path.open("r", encoding="utf-8-sig", newline="") as source, database(database_target) as connection:
        for row in csv.DictReader(source):
            pattern_id = stable_id(row)
            exists = connection.execute("SELECT 1 FROM patterns WHERE id = ?", (pattern_id,)).fetchone()
            values = (
                row.get("candidate_name") or "未命名纹样",
                row.get("category_label") or row.get("motif_code") or row.get("type") or row.get("legacy_type") or "待分类",
                infer_ethnicity(row),
                row.get("meaning") or row.get("description") or "",
                json.dumps(split_values(row.get("color") or ""), ensure_ascii=False),
                row.get("asset_url") or None,
                # Safety invariant: imports never publish, regardless of CSV values.
                "draft",
                "internal_only",
                json.dumps({"system": row.get("source_system") or "csv", "legacyType": row.get("legacy_type") or None, "legacyId": row.get("legacy_id") or None, "originClaim": row.get("origin_claim") or "unknown"}, ensure_ascii=False),
                json.dumps({"status": row.get("rights_status") or "unverified", "owner": None, "license": None}, ensure_ascii=False),
                json.dumps({"issues": split_values((row.get("review_issues") or "").replace("|", ",")), "reviewedBy": None, "reviewedAt": None}, ensure_ascii=False),
            )
            if exists:
                connection.execute("""UPDATE patterns SET name=?,category=?,ethnicity=?,meaning=?,colors_json=?,image_url=?,status=?,visibility=?,source_json=?,rights_json=?,review_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""", (*values, pattern_id))
                updated += 1
            else:
                connection.execute("""INSERT INTO patterns (name,category,ethnicity,meaning,colors_json,image_url,status,visibility,source_json,rights_json,review_json,id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (*values, pattern_id))
                inserted += 1
    return inserted, updated


def main() -> None:
    default_csv = Path(__file__).resolve().parents[2] / "data" / "output" / "clean" / "normalized_candidates.csv"
    parser = argparse.ArgumentParser(description="Import normalized candidates as draft/internal-only records")
    parser.add_argument("csv", nargs="?", type=Path, default=default_csv)
    parser.add_argument("--database", type=Path, help="SQLite path override (otherwise environment settings are used)")
    args = parser.parse_args()
    inserted, updated = import_candidates(args.csv, args.database or get_settings())
    print(f"import complete: inserted={inserted}, updated={updated}, status=draft, visibility=internal_only")


if __name__ == "__main__":
    main()
