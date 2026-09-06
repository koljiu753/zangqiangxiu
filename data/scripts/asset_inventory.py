#!/usr/bin/env python3
"""Create a non-destructive asset inventory for a directory or ZIP archive."""
from __future__ import annotations

import argparse, csv, hashlib, io, json, mimetypes, struct, zipfile
from collections import defaultdict
from pathlib import Path, PurePosixPath

SYSTEM_PARTS = {"__MACOSX", ".DS_Store"}

def normalized_zip_name(name: str) -> str:
    """Repair UTF-8 names stored without the ZIP language flag (common in older macOS archives)."""
    try:
        repaired=name.encode("cp437").decode("utf-8")
        return repaired if any("\u4e00" <= c <= "\u9fff" for c in repaired) else name
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name

def ignored(name: str) -> bool:
    p = PurePosixPath(name.replace("\\", "/"))
    return any(x in SYSTEM_PARTS or x.startswith("._") for x in p.parts)

def dimensions(data: bytes):
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data.startswith(b"\xff\xd8"):
        stream = io.BytesIO(data); stream.read(2)
        while True:
            b = stream.read(1)
            if not b: break
            if b != b"\xff": continue
            marker = stream.read(1)
            while marker == b"\xff": marker = stream.read(1)
            if marker in (b"\xd8", b"\xd9"): continue
            raw = stream.read(2)
            if len(raw) < 2: break
            length = struct.unpack(">H", raw)[0]
            if marker and marker[0] in {0xC0,0xC1,0xC2,0xC3,0xC5,0xC6,0xC7,0xC9,0xCA,0xCB,0xCD,0xCE,0xCF}:
                segment = stream.read(length - 2)
                if len(segment) >= 5:
                    h, w = struct.unpack(">HH", segment[1:5]); return w, h
                break
            stream.seek(length - 2, 1)
    return None, None

def records(source: Path):
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as zf:
            for info in zf.infolist():
                name=normalized_zip_name(info.filename)
                if info.is_dir() or ignored(name): continue
                data = zf.read(info)
                yield name.replace("\\", "/"), data
    elif source.is_dir():
        for path in sorted(p for p in source.rglob("*") if p.is_file()):
            rel = path.relative_to(source).as_posix()
            if not ignored(rel): yield rel, path.read_bytes()
    else:
        raise SystemExit(f"Unsupported input: {source}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("--output", type=Path, default=Path(__file__).parents[1] / "output" / "inventory")
    args = ap.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    rows=[]; groups=defaultdict(list)
    for name, data in records(args.source):
        sha=hashlib.sha256(data).hexdigest(); w,h=dimensions(data)
        row={"source_path":name,"byte_size":len(data),"sha256":sha,
             "mime_type":mimetypes.guess_type(name)[0] or "application/octet-stream",
             "width":w or "","height":h or ""}
        rows.append(row); groups[sha].append(name)
    with (args.output/"assets.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=rows[0].keys() if rows else ["source_path","byte_size","sha256","mime_type","width","height"])
        writer.writeheader(); writer.writerows(rows)
    duplicates=[{"sha256":k,"count":len(v),"paths":v} for k,v in groups.items() if len(v)>1]
    summary={"source":str(args.source.resolve()),"business_files":len(rows),"unique_sha256":len(groups),
             "exact_duplicate_groups":len(duplicates),"exact_duplicate_files":sum(x["count"] for x in duplicates)}
    (args.output/"duplicates.json").write_text(json.dumps(duplicates,ensure_ascii=False,indent=2),encoding="utf-8")
    (args.output/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))

if __name__ == "__main__": main()
