#!/usr/bin/env python3
"""Hash legacy-site asset references and reconcile them with a local inventory."""
from __future__ import annotations
import argparse, csv, hashlib, json, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

RAW_BASE={
 "tianmawenku":"https://raw.githubusercontent.com/Xin-iris/tianmawenku/main/",
 "zhixiuxiangcun":"https://raw.githubusercontent.com/Xin-iris/zhixiuxiangcun/main/",
}

def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"zhixiu-data-reconcile/1.0"})
    with urllib.request.urlopen(req,timeout=45) as response: return response.read()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("inventory",type=Path); ap.add_argument("legacy_candidates",type=Path)
    ap.add_argument("--output",type=Path,default=Path(__file__).parents[1]/"output"/"reconciliation")
    args=ap.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    with args.inventory.open(encoding="utf-8-sig",newline="") as f: local=list(csv.DictReader(f))
    by_hash={}
    for row in local: by_hash.setdefault(row["sha256"],[]).append(row["source_path"])
    with args.legacy_candidates.open(encoding="utf-8-sig",newline="") as f: legacy=list(csv.DictReader(f))
    cache={}; rows=[]
    keys=sorted({(item["source_system"],item["asset_url"]) for item in legacy})
    def load(key):
        try:
            url=urllib.parse.urljoin(RAW_BASE[key[0]],urllib.parse.quote(key[1],safe="/"))
            data=fetch(url); return key,(hashlib.sha256(data).hexdigest(),len(data),url,"")
        except Exception as exc: return key,(None,None,"",f"{type(exc).__name__}: {exc}")
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures=[pool.submit(load,key) for key in keys]
        for future in as_completed(futures):
            key,value=future.result(); cache[key]=value
    for item in legacy:
        key=(item["source_system"],item["asset_url"]); error=""; digest=""; size=""
        digest,size,url,error=cache[key]
        matches=by_hash.get(digest,[]) if digest else []
        rows.append({"source_system":item["source_system"],"legacy_id":item["legacy_id"],"candidate_name":item["candidate_name"],
          "asset_url":item["asset_url"],"resolved_url":url,"remote_sha256":digest or "","remote_byte_size":size or "",
          "local_match_count":len(matches),"local_match_paths":"|".join(matches),"fetch_error":error})
    fields=list(rows[0]) if rows else []
    with (args.output/"legacy_zip_reconciliation.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    unique={k:v for k,v in cache.items()}; successful=[v for v in unique.values() if v[0]]
    summary={"legacy_records":len(legacy),"unique_legacy_asset_references":len(unique),"successfully_hashed":len(successful),
      "failed_fetches":len(unique)-len(successful),"unique_assets_matching_local_zip":len({v[0] for v in successful if v[0] in by_hash}),
      "records_matching_local_zip":sum(1 for r in rows if r["local_match_count"])}
    (args.output/"reconciliation_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))

if __name__=="__main__": main()
