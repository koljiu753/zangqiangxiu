"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";

type PreviewStatus = "loading" | "ready" | "unavailable";

export function AdminPatternPreview({ patternId, name }: { patternId: string; name: string }) {
  const [status, setStatus] = useState<PreviewStatus>("loading");
  const imageUrl = `/patterns/${encodeURIComponent(patternId)}/image`;

  return <section className={`admin-pattern-preview ${status}`} aria-label={`${name}图片预览`}>
    <div className="admin-preview-canvas">
      {status !== "unavailable" && <Image src={imageUrl} alt={`${name}审核预览`} fill sizes="(max-width: 700px) 100vw, 360px" unoptimized onLoad={() => setStatus("ready")} onError={() => setStatus("unavailable")} />}
      {status === "loading" && <span className="admin-preview-state" role="status">图片加载中…</span>}
      {status === "unavailable" && <div className="admin-preview-empty" role="status"><strong>暂无可预览图片</strong><span>素材未关联、不可读或尚未完成入库。</span></div>}
    </div>
    <footer><span className={`preview-status ${status}`}>{status === "loading" ? "加载中" : status === "ready" ? "图片可用" : "无图"}</span><Link href={`/patterns/${encodeURIComponent(patternId)}`} target="_blank">打开档案 ↗</Link></footer>
  </section>;
}
