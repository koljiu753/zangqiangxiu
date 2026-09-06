#!/usr/bin/env python3
"""Select up to N auditable MVD candidates from an inventory and emit catalog seeds."""
from __future__ import annotations
import argparse, csv, json, re, uuid
from collections import Counter, defaultdict, deque
from pathlib import Path, PurePosixPath

NS=uuid.UUID("702eb55e-b6ca-4fe1-a68d-409bb97fe20f")
MOTIF={"植物纹样":"plant","动物纹样":"animal","自然纹":"nature","几何纹":"geometry","未命名纹样":"unknown"}

def category(path):
    parts=PurePosixPath(path.replace("\\","/")).parts
    for name in MOTIF:
        if name in parts: return name,MOTIF[name]
    return "未分类","unknown"

def name_from(path):
    stem=PurePosixPath(path).stem
    return re.sub(r"[_-]?副本$","",stem).strip()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("inventory",type=Path); ap.add_argument("--duplicates",type=Path)
    ap.add_argument("--limit",type=int,default=100); ap.add_argument("--output",type=Path,default=Path(__file__).parents[1]/"output"/"mvd")
    args=ap.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    with args.inventory.open(encoding="utf-8-sig",newline="") as f: source=list(csv.DictReader(f))
    duplicate_hashes=set()
    if args.duplicates:
        duplicate_hashes={x["sha256"] for x in json.loads(args.duplicates.read_text(encoding="utf-8"))}
    seen=set(); eligible=[]; rejected=[]
    for r in source:
        reasons=[]
        if not r["mime_type"].startswith("image/"): reasons.append("not_raster_image")
        if not r["width"] or not r["height"]: reasons.append("not_decodable_or_dimensions_unknown")
        if r["sha256"] in seen: reasons.append("duplicate_sha256")
        if reasons: rejected.append({**r,"rejection_reasons":"|".join(reasons)}); continue
        seen.add(r["sha256"]); cat,motif=category(r["source_path"]); candidate=name_from(r["source_path"])
        risks=["source_unverified","rights_unverified","culture_unreviewed"]
        if r["sha256"] in duplicate_hashes: risks.append("exact_duplicate_group")
        if cat in ("未命名纹样","未分类") or "网页介绍并未说明" in candidate: risks.append("name_unverified")
        eligible.append({**r,"legacy_category":cat,"motif_code":motif,"candidate_name":candidate,"risk_flags":"|".join(risks)})
    buckets=defaultdict(deque)
    for r in sorted(eligible,key=lambda x:(x["legacy_category"],x["candidate_name"],x["sha256"])): buckets[r["legacy_category"]].append(r)
    selected=[]; order=sorted(buckets,key=lambda k:(len(buckets[k]),k))
    while len(selected)<args.limit and any(buckets.values()):
        for key in order:
            if buckets[key] and len(selected)<args.limit: selected.append(buckets[key].popleft())
    seeds=[]
    for r in selected:
        pattern_id=str(uuid.uuid5(NS,"pattern|zip|"+r["sha256"])); asset_id=str(uuid.uuid5(NS,"asset|zip|"+r["sha256"]))
        ext=PurePosixPath(r["source_path"]).suffix.lower().lstrip(".") or "bin"
        seeds.append({"pattern_id":pattern_id,"asset_id":asset_id,"canonical_name":"","candidate_name":r["candidate_name"],
          "description":"","origin_claim":"unknown","status":"draft","visibility":"internal_only","source_system":"local_zang_qiang_zip",
          "source_locator":r["source_path"],"original_path":r["source_path"],"source_type":"unknown","object_key":f"original/{r['sha256'][:2]}/{r['sha256']}.{ext}",
          "original_filename":PurePosixPath(r["source_path"]).name,"mime_type":r["mime_type"],"byte_size":int(r["byte_size"]),
          "sha256":r["sha256"],"width":int(r["width"]),"height":int(r["height"]),"motif_code_draft":r["motif_code"],
          "legacy_category":r["legacy_category"],"risk_flags":r["risk_flags"],"legal_basis":"unverified","allow_display":False,
          "allow_download":False,"allow_commercial":False,"allow_ai_training":False,"allow_derivatives":False})
    fields=list(seeds[0]) if seeds else []
    with (args.output/"catalog_seed.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(seeds)
    (args.output/"catalog_seed.json").write_text(json.dumps({"schema_version":"1.0","records":seeds},ensure_ascii=False,indent=2),encoding="utf-8")
    with (args.output/"rejected_candidates.csv").open("w",encoding="utf-8-sig",newline="") as f:
        fields2=list(rejected[0]) if rejected else list(source[0])+["rejection_reasons"] if source else []
        w=csv.DictWriter(f,fieldnames=fields2); w.writeheader(); w.writerows(rejected)
    coverage=dict(sorted(Counter(x["legacy_category"] for x in seeds).items()))
    eligible_coverage=dict(sorted(Counter(x["legacy_category"] for x in eligible).items()))
    risk_counts=Counter(flag for x in seeds for flag in x["risk_flags"].split("|") if flag)
    rejection_counts=Counter(reason for x in rejected for reason in x["rejection_reasons"].split("|") if reason)
    report={"inventory_rows":len(source),"eligible_unique_decodable_images":len(eligible),"selected":len(seeds),"limit":args.limit,
      "eligible_category_counts":eligible_coverage,"category_coverage":coverage,"selected_risk_counts":dict(sorted(risk_counts.items())),
      "rejected_rows":len(rejected),"rejection_reason_counts":dict(sorted(rejection_counts.items())),"all_status_draft":all(x["status"]=="draft" for x in seeds),
      "all_internal_only":all(x["visibility"]=="internal_only" for x in seeds),"all_rights_denied":all(not any(x[k] for k in ("allow_display","allow_download","allow_commercial","allow_ai_training","allow_derivatives")) for x in seeds)}
    (args.output/"mvd_selection_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))

if __name__=="__main__": main()
