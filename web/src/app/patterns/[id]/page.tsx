import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import { SourceBadge } from "@/components/source-badge";
import { getPattern } from "@/lib/catalog-api";

type Props = { params: Promise<{ id: string }> };

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const { data } = await getPattern(id);
  return data
    ? { title: `${data.name} | 智绣乡村`, description: data.meaning || `查看${data.name}纹样档案` }
    : { title: "纹样未找到 | 智绣乡村" };
}

export default async function PatternDetailPage({ params }: Props) {
  const { id } = await params;
  const result = await getPattern(id);
  const pattern = result.data;
  if (!pattern) notFound();

  const isPreview = result.source === "preview";
  return <main className="inner-page pattern-detail">
    <Link className="detail-back" href="/patterns">← 返回纹样库</Link>
    <SourceBadge source={result.source} />
    {isPreview && <div className="preview-notice"><strong>内部资料预览</strong><span>该纹样尚未通过版权与文化审核，不代表可公开传播或下载。</span></div>}
    <article className="detail-layout">
      <div className="detail-image">
        {pattern.imageUrl ? <Image src={pattern.imageUrl} alt={`${pattern.name}纹样原图`} fill sizes="(max-width: 900px) 100vw, 55vw" priority unoptimized /> : <div className="detail-image-empty">暂无图像</div>}
      </div>
      <div className="detail-copy">
        <p className="eyebrow">PATTERN ARCHIVE</p>
        <h1>{pattern.name}</h1>
        <p className="detail-lead">{pattern.meaning || "该纹样的文化寓意尚待田野调研与专家校核。"}</p>
        <dl className="detail-facts">
          <div><dt>分类</dt><dd>{pattern.category || "待分类"}</dd></div>
          <div><dt>民族</dt><dd>{pattern.ethnicity === "unknown" ? "待核验" : pattern.ethnicity}</dd></div>
          <div><dt>状态</dt><dd>{pattern.status === "published" ? "已发布" : "待审核"}</dd></div>
          <div><dt>来源</dt><dd>{pattern.source?.system || "待补充"}</dd></div>
          <div><dt>版权</dt><dd>{pattern.rights?.status === "verified" ? "已核验" : "未核验"}</dd></div>
          <div><dt>档案号</dt><dd><code>{pattern.id}</code></dd></div>
        </dl>
        {pattern.colors.length > 0 && <section className="detail-palette"><h2>色彩提取</h2><div className="palette">{pattern.colors.map((color) => <i key={color} style={{ background: color }} title={color} />)}</div></section>}
      </div>
    </article>
  </main>;
}
