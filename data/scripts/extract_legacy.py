#!/usr/bin/env python3
"""Extract candidate records from the two public legacy sites without changing them."""
from __future__ import annotations

import argparse, csv, json, re, urllib.request
from html.parser import HTMLParser
from pathlib import Path

URLS={
 "tianma":"https://raw.githubusercontent.com/Xin-iris/tianmawenku/main/library.html",
 "zhixiu":"https://raw.githubusercontent.com/Xin-iris/zhixiuxiangcun/main/assets/js/pattern-manifest.js",
}

def read_source(value: str) -> str:
    if value.startswith(("http://","https://")):
        req=urllib.request.Request(value,headers={"User-Agent":"zhixiu-data-audit/1.0"})
        with urllib.request.urlopen(req,timeout=30) as r: return r.read().decode("utf-8")
    return Path(value).read_text(encoding="utf-8")

class Cards(HTMLParser):
    def __init__(self): super().__init__(); self.rows=[]; self.current=None; self.capture=None
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag=="article" and "pattern-record" in a.get("class",""):
            self.current={"source_system":"tianmawenku","legacy_type":"crop_card","legacy_id":f"card-{len(self.rows)+1:03d}","candidate_name":"","description":"","tags":a.get("data-tags",""),"asset_url":"assets/img/pattern-breakdown.png","crop_x":"","crop_y":"","crop_w":"","crop_h":"","type":"","meaning":"","color":"","craft":"","rights_status":"unverified"}
        elif self.current and tag=="div" and "source-crop" in a.get("class",""):
            for short,key in (("x","crop_x"),("y","crop_y"),("w","crop_w"),("h","crop_h")): self.current[key]=a.get("data-"+short,"")
        elif self.current and tag in ("h3","p","small"): self.capture=tag
    def handle_data(self,data):
        if self.current and self.capture:
            key="candidate_name" if self.capture=="h3" else "description"
            self.current[key] += (" " if self.current[key] else "") + data.strip()
    def handle_endtag(self,tag):
        if tag==self.capture: self.capture=None
        if tag=="article" and self.current: self.rows.append(self.current); self.current=None; self.capture=None

def js_objects(text):
    rows=[]
    for obj in re.findall(r"\{([^{}]+)\}",text,re.S):
        fields=dict(re.findall(r'(name|url|type|meaning|color|craft)\s*:\s*"([^"]*)"',obj))
        if "name" not in fields or "url" not in fields: continue
        rows.append({"source_system":"zhixiuxiangcun","legacy_type":"manifest_item","legacy_id":f"manifest-{len(rows)+1:03d}","candidate_name":re.sub(r"\.[^.]+$","",fields["name"]),"description":"","tags":"","asset_url":fields["url"],"crop_x":"","crop_y":"","crop_w":"","crop_h":"","type":fields.get("type",""),"meaning":fields.get("meaning",""),"color":fields.get("color",""),"craft":fields.get("craft",""),"rights_status":"unverified"})
    return rows

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--tianma",default=URLS["tianma"]); ap.add_argument("--zhixiu",default=URLS["zhixiu"])
    ap.add_argument("--output",type=Path,default=Path(__file__).parents[1]/"output"/"legacy"); args=ap.parse_args()
    parser=Cards(); parser.feed(read_source(args.tianma)); rows=parser.rows+js_objects(read_source(args.zhixiu))
    args.output.mkdir(parents=True,exist_ok=True); fields=list(rows[0].keys())
    with (args.output/"legacy_candidates.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    by_url={}
    for r in rows: by_url.setdefault((r["source_system"],r["asset_url"]),[]).append(r["legacy_id"])
    report={"total_candidates":len(rows),"tianma_cards":len(parser.rows),"zhixiu_manifest_items":len(rows)-len(parser.rows),"unique_asset_references":len(by_url),"shared_asset_references":{"|".join(k):v for k,v in by_url.items() if len(v)>1}}
    (args.output/"legacy_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))

if __name__=="__main__": main()
