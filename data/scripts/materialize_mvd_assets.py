#!/usr/bin/env python3
"""Safely materialize MVD originals from a ZIP and create internal-only thumbnails."""
from __future__ import annotations
import argparse, csv, hashlib, io, json, os, re, zipfile
from pathlib import Path, PurePosixPath
from PIL import Image, ImageOps
from asset_inventory import normalized_zip_name

HEX64=re.compile(r"^[0-9a-f]{64}$")

def sha256(data): return hashlib.sha256(data).hexdigest()

def safe_member(name):
    if not name or "\x00" in name or "\\" in name: return False
    p=PurePosixPath(name)
    return not p.is_absolute() and ".." not in p.parts and not re.match(r"^[A-Za-z]:",name)

def write_exact(path: Path, data: bytes, expected_hash: str):
    if sha256(data)!=expected_hash: raise ValueError("source_hash_mismatch")
    if path.exists():
        if sha256(path.read_bytes())!=expected_hash: raise FileExistsError("existing_target_hash_mismatch")
        return "existing_verified"
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with path.open("xb") as f: f.write(data)
    except FileExistsError:
        if sha256(path.read_bytes())!=expected_hash: raise FileExistsError("concurrent_target_hash_mismatch")
        return "existing_verified"
    return "created"

def thumbnail(data: bytes, max_size: int):
    with Image.open(io.BytesIO(data)) as image:
        image.load(); image=ImageOps.exif_transpose(image)
        image.thumbnail((max_size,max_size),Image.Resampling.LANCZOS)
        if image.mode not in ("RGB","RGBA"): image=image.convert("RGBA" if "transparency" in image.info else "RGB")
        out=io.BytesIO(); image.save(out,"WEBP",quality=82,method=6)
        return out.getvalue(),image.width,image.height

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("zip_path",type=Path); ap.add_argument("catalog_seed",type=Path)
    ap.add_argument("--output",type=Path,default=Path(__file__).parents[1]/"output"/"mvd"); ap.add_argument("--thumbnail-size",type=int,default=512)
    args=ap.parse_args()
    if not 64<=args.thumbnail_size<=2048: raise SystemExit("thumbnail-size must be between 64 and 2048")
    original_dir=args.output/"assets"/"original"; thumb_dir=args.output/"assets"/"thumbnails"
    original_dir.mkdir(parents=True,exist_ok=True); thumb_dir.mkdir(parents=True,exist_ok=True)
    with args.catalog_seed.open(encoding="utf-8-sig",newline="") as f: seeds=list(csv.DictReader(f))
    with zipfile.ZipFile(args.zip_path) as zf:
        members={}
        for info in zf.infolist():
            if info.is_dir(): continue
            members.setdefault(normalized_zip_name(info.filename).replace("\\","/"),[]).append(info)
        manifest=[]
        for seed in seeds:
            source=seed.get("original_path") or seed.get("source_locator") or ""; expected=(seed.get("sha256") or "").lower()
            row={"pattern_id":seed.get("pattern_id",""),"asset_id":seed.get("asset_id",""),"candidate_name":seed.get("candidate_name",""),
              "original_path":source,"status":"error","visibility":"internal_only","original_relative_path":"","original_sha256":"",
              "original_byte_size":"","original_width":"","original_height":"","thumbnail_relative_path":"","thumbnail_sha256":"",
              "thumbnail_byte_size":"","thumbnail_width":"","thumbnail_height":"","processing_action":"","processing_error":""}
            try:
                if seed.get("status")!="draft" or seed.get("visibility")!="internal_only": raise ValueError("unsafe_seed_state")
                if not safe_member(source): raise ValueError("unsafe_original_path")
                if not HEX64.fullmatch(expected): raise ValueError("invalid_expected_sha256")
                if len(members.get(source,[]))!=1: raise ValueError("zip_member_missing_or_ambiguous")
                data=zf.read(members[source][0]); actual=sha256(data)
                if actual!=expected: raise ValueError("source_hash_mismatch")
                ext=PurePosixPath(source).suffix.lower() or ".bin"; original_name=expected+ext
                original_path=original_dir/original_name; action=write_exact(original_path,data,expected)
                thumb_data,tw,th=thumbnail(data,args.thumbnail_size); thumb_hash=sha256(thumb_data); thumb_path=thumb_dir/(expected+".webp")
                thumb_action=write_exact(thumb_path,thumb_data,thumb_hash)
                with Image.open(io.BytesIO(data)) as im: ow,oh=im.size
                row.update({"status":"materialized","original_relative_path":original_path.relative_to(args.output).as_posix(),"original_sha256":actual,
                  "original_byte_size":len(data),"original_width":ow,"original_height":oh,"thumbnail_relative_path":thumb_path.relative_to(args.output).as_posix(),
                  "thumbnail_sha256":thumb_hash,"thumbnail_byte_size":len(thumb_data),"thumbnail_width":tw,"thumbnail_height":th,
                  "processing_action":f"original:{action};thumbnail:{thumb_action}"})
            except Exception as exc: row["processing_error"]=f"{type(exc).__name__}:{exc}"
            manifest.append(row)
    fields=list(manifest[0]) if manifest else []
    with (args.output/"asset_manifest.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(manifest)
    payload={"schema_version":"1.0","visibility":"internal_only","records":manifest}
    (args.output/"asset_manifest.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    summary={"seed_records":len(seeds),"materialized":sum(x["status"]=="materialized" for x in manifest),
      "errors":sum(x["status"]=="error" for x in manifest),"unique_original_hashes":len({x["original_sha256"] for x in manifest if x["original_sha256"]}),
      "unique_thumbnail_hashes":len({x["thumbnail_sha256"] for x in manifest if x["thumbnail_sha256"]})}
    (args.output/"materialization_report.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))
    if summary["errors"]: raise SystemExit(2)

if __name__=="__main__": main()
