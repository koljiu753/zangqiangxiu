#!/usr/bin/env python3
"""Inventory pages, visible copy and local assets in legacy static-site repos."""
from __future__ import annotations
import argparse, csv, hashlib, json, re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

TEXT_TAGS = {"title", "h1", "h2", "h3", "p", "li"}
HIGH_RISK = re.compile(r"(版权|授权|收益|销售|订单|准确率|识别率|国家级|传承人|专利|软著|万元|%|区块链)")

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.stack=[]; self.texts=[]; self.assets=[]
    def handle_starttag(self, tag, attrs):
        values=dict(attrs)
        if tag in TEXT_TAGS: self.stack.append((tag, []))
        if tag in {"img", "source", "video", "audio"} and values.get("src"): self.assets.append((tag, values["src"]))
        if tag == "link" and values.get("href"): self.assets.append((tag, values["href"]))
    def handle_data(self, data):
        if self.stack: self.stack[-1][1].append(data)
    def handle_endtag(self, tag):
        if self.stack and self.stack[-1][0] == tag:
            active, pieces=self.stack.pop(); value=" ".join(" ".join(pieces).split())
            if value: self.texts.append((active, value))

def local_asset(page, raw_ref, root):
    ref=unquote(urlsplit(raw_ref).path)
    if not ref or raw_ref.startswith(("http://", "https://", "//", "data:", "#")): return "external", None
    candidate=(page.parent/ref).resolve()
    try: candidate.relative_to(root.resolve())
    except ValueError: return "outside_repo", None
    return ("present" if candidate.is_file() else "missing"), candidate

def write_csv(path, rows, fields):
    with path.open("w",encoding="utf-8-sig",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields); writer.writeheader(); writer.writerows(rows)

def audit(repos, output):
    pages=[]; texts=[]; refs=[]
    for site, root in repos.items():
        for page in sorted(root.glob("*.html")):
            parser=PageParser(); parser.feed(page.read_text(encoding="utf-8")); rel=page.relative_to(root).as_posix()
            heading=next((v for t,v in parser.texts if t=="h1"),""); title=next((v for t,v in parser.texts if t=="title"),"")
            pages.append({"source_system":site,"source_page":rel,"title":title,"primary_heading":heading,
                "text_block_count":len(parser.texts),"asset_reference_count":len(parser.assets),
                "migration_status":"candidate","visibility":"internal_only","review_status":"draft"})
            for index,(tag,value) in enumerate(parser.texts,1):
                risk="claim_review_required" if HIGH_RISK.search(value) else "editorial_review_required"
                texts.append({"source_system":site,"source_page":rel,"block_id":f"{rel}#text-{index:03d}",
                    "html_tag":tag,"text":value,"risk":risk,"migration_status":"candidate",
                    "visibility":"internal_only","review_status":"draft"})
            for index,(tag,raw_ref) in enumerate(parser.assets,1):
                state,asset_path=local_asset(page,raw_ref,root)
                digest=hashlib.sha256(asset_path.read_bytes()).hexdigest() if state=="present" and asset_path else ""
                refs.append({"source_system":site,"source_page":rel,"reference_id":f"{rel}#asset-{index:03d}",
                    "html_tag":tag,"raw_reference":raw_ref,"resolution_status":state,
                    "repository_path":asset_path.relative_to(root).as_posix() if state=="present" and asset_path else "",
                    "sha256":digest,"rights_status":"unverified","visibility":"internal_only","review_status":"draft"})
    output.mkdir(parents=True,exist_ok=True)
    write_csv(output/"page_manifest.csv",pages,list(pages[0])); write_csv(output/"text_candidates.csv",texts,list(texts[0])); write_csv(output/"asset_references.csv",refs,list(refs[0]))
    report={"sites":list(repos),"pages":len(pages),"text_candidates":len(texts),
        "claim_review_required":sum(r["risk"]=="claim_review_required" for r in texts),"asset_references":len(refs),
        "unique_resolved_asset_hashes":len({r["sha256"] for r in refs if r["sha256"]}),
        "asset_resolution":dict(Counter(r["resolution_status"] for r in refs)),
        "publication_defaults":{"visibility":"internal_only","review_status":"draft","rights_status":"unverified"}}
    (output/"content_audit_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return report

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--tianma",type=Path,required=True); parser.add_argument("--zhixiu",type=Path,required=True)
    parser.add_argument("--output",type=Path,default=Path(__file__).parents[1]/"output"/"legacy-content"); args=parser.parse_args()
    repos={"tianmawenku":args.tianma,"zhixiuxiangcun":args.zhixiu}
    for name,path in repos.items():
        if not path.is_dir(): parser.error(f"{name} repository directory does not exist: {path}")
    print(json.dumps(audit(repos,args.output),ensure_ascii=False))

if __name__=="__main__": main()
