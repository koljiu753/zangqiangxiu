#!/usr/bin/env python3
"""Normalize extracted candidates and produce review queues; never edits its input."""
import argparse, csv, json, re
from collections import defaultdict
from pathlib import Path

def clean(value): return re.sub(r"\s+"," ",value or "").strip()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("input",type=Path)
    ap.add_argument("--output",type=Path,default=Path(__file__).parents[1]/"output"/"clean")
    args=ap.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    with args.input.open(encoding="utf-8-sig",newline="") as f: source=list(csv.DictReader(f))
    rows=[]; refs=defaultdict(list)
    for r in source:
        r={k:clean(v) for k,v in r.items()}; r["candidate_name"]=re.sub(r"^\d+\.\s*","",r["candidate_name"])
        r["origin_claim"]="generated" if "/generated/" in r["asset_url"] else "unknown"
        r["status"]="draft"; r["visibility"]="private"
        issues=[]
        if not r["candidate_name"]: issues.append("missing_name")
        if r["rights_status"]!="verified": issues.append("rights_unverified")
        if r["legacy_type"]=="crop_card" and not all(r[k] for k in ("crop_x","crop_y","crop_w","crop_h")): issues.append("crop_or_whole_image_review")
        r["review_issues"]="|".join(issues); rows.append(r); refs[(r["source_system"],r["asset_url"])].append(r)
    for same in refs.values():
        if len(same)>1:
            for r in same: r["review_issues"] += ("|" if r["review_issues"] else "")+"shared_asset_reference"
    fields=list(rows[0].keys()) if rows else []
    with (args.output/"normalized_candidates.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    queue=[r for r in rows if r["review_issues"]]
    (args.output/"review_queue.json").write_text(json.dumps(queue,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"rows":len(rows),"needs_review":len(queue)},ensure_ascii=False))

if __name__=="__main__": main()
