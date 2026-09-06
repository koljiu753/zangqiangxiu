"""Idempotently upload and register MVD reference images through the public API."""

import argparse
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

import httpx


def load_records(manifest_path: Path) -> list[dict[str, Any]]:
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = document.get("records", document) if isinstance(document, dict) else document
    if not isinstance(records, list):
        raise ValueError("Manifest must be a list or an object containing a records list")
    return records


def resolve_image(record: dict[str, Any], manifest_path: Path) -> Path:
    raw = (
        record.get("local_path") or record.get("source_path") or record.get("file_path")
        or record.get("original_relative_path")
    )
    if not raw and isinstance(record.get("asset"), dict):
        raw = record["asset"].get("local_path") or record["asset"].get("source_path")
    if not raw:
        raise ValueError("Record has no local_path/source_path/file_path/original_relative_path")
    path = Path(raw)
    if not path.is_absolute():
        path = (manifest_path.parent / path).resolve()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    return path


def import_manifest(
    manifest_path: Path, base_url: str, service_token: str, timeout: float = 60
) -> dict[str, Any]:
    if not service_token:
        raise ValueError("A service token is required to register internal references")
    records = load_records(manifest_path)
    report: dict[str, Any] = {"manifest": str(manifest_path), "total": len(records),
                              "succeeded": 0, "failed": 0, "items": []}
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout) as client:
        for index, record in enumerate(records):
            pattern_id = record.get("pattern_id")
            item = {"index": index, "pattern_id": pattern_id, "status": "failed"}
            try:
                image_path = resolve_image(record, manifest_path)
                mime = record.get("mime_type") or mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
                with image_path.open("rb") as stream:
                    upload = client.post("/v1/assets", files={"image": (image_path.name, stream, mime)})
                upload.raise_for_status()
                asset_id = upload.json()["id"]
                registration = client.post("/v1/references", headers={"X-Service-Token": service_token}, json={
                    "asset_id": asset_id,
                    "pattern_id": pattern_id,
                    "label": record.get("candidate_name"),
                    # MVD names and rights remain unreviewed by design.
                    "review_status": "draft",
                    "visibility": "internal_only",
                })
                registration.raise_for_status()
                item.update(status="succeeded", asset_id=asset_id)
                report["succeeded"] += 1
            except Exception as exc:
                item["error"] = f"{type(exc).__name__}: {exc}"
                report["failed"] += 1
            report["items"].append(item)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("../data/output/mvd/asset_manifest.json"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--report", type=Path, default=Path("data/mvd_index_report.json"))
    parser.add_argument("--service-token", default=os.getenv("ZHIXIU_AI_INTERNAL_TOKEN"))
    args = parser.parse_args()
    report = import_manifest(args.manifest.resolve(), args.base_url, args.service_token)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("total", "succeeded", "failed")}, ensure_ascii=False))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
