"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { submitAnalysis } from "@/lib/api";
import type { AnalysisResult } from "@/types/domain";

type Stage = "idle" | "uploading" | "analyzing" | "succeeded" | "failed";

export function StudioDemo() {
  const [file, setFile] = useState<File>();
  const [previewUrl, setPreviewUrl] = useState<string>();
  const [stage, setStage] = useState<Stage>("idle");
  const [message, setMessage] = useState("等待上传纹样图片");
  const [result, setResult] = useState<AnalysisResult>();
  const [consented, setConsented] = useState(false);

  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);

  function chooseFile(nextFile?: File) {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(nextFile);
    setPreviewUrl(nextFile ? URL.createObjectURL(nextFile) : undefined);
    setResult(undefined);
    setStage("idle");
    setMessage(nextFile ? `已选择 ${nextFile.name}` : "等待上传纹样图片");
  }

  async function analyze() {
    if (!file) return setMessage("请先选择一张图片。");
    setStage("uploading");
    setResult(undefined);
    setMessage("正在安全上传图片……");
    const analyzingTimer = window.setTimeout(() => {
      setStage("analyzing");
      setMessage("正在提取色彩并检索相似纹样……");
    }, 250);
    try {
      const nextResult = await submitAnalysis(file);
      setResult(nextResult);
      setStage("succeeded");
      setMessage(`分析完成，找到 ${nextResult.similar.length} 个相似候选。`);
    } catch (error) {
      setStage("failed");
      setMessage(error instanceof Error ? error.message : "分析服务暂不可用");
    } finally {
      window.clearTimeout(analyzingTimer);
    }
  }

  const busy = stage === "uploading" || stage === "analyzing";
  return <section aria-label="纹样智能分析">
    <div className="studio-console">
      <div className="upload-zone">
        <span className="scan-line" /><p className="eyebrow">AI PATTERN RECOGNITION</p><h2>上传纹样样本</h2>
        <p>系统会提取真实色板，并在经过权限控制的参考库中检索相似纹样。</p>
        {previewUrl && <div className="studio-preview"><Image src={previewUrl} alt="待分析纹样预览" fill sizes="(max-width: 800px) 90vw, 45vw" unoptimized /></div>}
        <input aria-label="选择纹样图片" type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => chooseFile(event.target.files?.[0])} />
        <label className="upload-consent"><input type="checkbox" checked={consented} onChange={(event) => setConsented(event.target.checked)} />我已阅读并同意<Link href="/privacy">图片处理与隐私说明</Link>，并确认有权上传该图片。</label>
        <button disabled={busy || !consented} onClick={analyze}>{busy ? "分析中…" : stage === "failed" ? "重新分析" : "开始识别"}</button>
      </div>
      <aside><p className="eyebrow">TASK STATUS</p><h3>分析状态</h3><p aria-live="polite" className={`studio-status ${stage}`}>{message}</p><dl>
        <div><dt>安全上传</dt><dd>{stage === "idle" ? "等待" : "已提交"}</dd></div>
        <div><dt>色彩分析</dt><dd>{result ? "已完成" : busy ? "处理中" : "等待"}</dd></div>
        <div><dt>相似检索</dt><dd>{result ? `${result.similar.length} 项` : busy ? "处理中" : "等待"}</dd></div>
      </dl></aside>
    </div>
    {result && <div className="studio-results">
      <header><div><p className="eyebrow">ANALYSIS RESULT</p><h2>可解释分析结果</h2></div>{result.algorithmVersion && <small>算法版本：{result.algorithmVersion}</small>}</header>
      <section className="analysis-summary" aria-label="主色板"><h3>提取主色</h3><div className="analysis-palette">{result.palette.map((color) => <span key={color}><i style={{ backgroundColor: color }} />{color}</span>)}</div></section>
      {!result.label && <p className="studio-notice">分类模型尚未配置；以下内容是基于图像特征的相似候选，不代表文化含义鉴定。</p>}
      {result.warnings.length > 0 && <ul className="studio-warnings">{result.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
      <div className="similar-grid">{result.similar.map((match, index) => <article key={match.assetId} className="similar-card">
        {match.imageUrl && <div className="similar-image"><Image src={match.imageUrl} alt={`${match.name || match.label || "候选"}纹样`} fill sizes="(max-width: 600px) 100vw, 20vw" unoptimized /></div>}
        <span className="similar-rank">TOP {index + 1}</span><strong>{match.name || match.label || "未命名候选"}</strong><b>{(match.score * 100).toFixed(1)}% 相似</b>
        {match.category && <small>{match.category}</small>}{match.meaning && <p>{match.meaning}</p>}
        {match.patternId && <Link href={`/patterns/${encodeURIComponent(match.patternId)}`}>查看纹样详情</Link>}
      </article>)}</div>
      {result.similar.length === 0 && <div className="empty-state"><h3>暂无相似候选</h3><p>公开参考库可能尚无已审核数据，请稍后再试。</p></div>}
    </div>}
  </section>;
}
