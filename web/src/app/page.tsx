import Link from "next/link";
import { getPatterns } from "@/lib/catalog-api";
import { SourceBadge } from "@/components/source-badge";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const patterns = await getPatterns();
  return <main><section className="hero"><div className="hero-orbit orbit-one" /><div className="hero-orbit orbit-two" /><p className="eyebrow">LIVING HERITAGE · DIGITAL FUTURE</p><h1>让千年纹样<br /><em>活在今天</em></h1><p className="hero-intro">从藏羌纹样数据库到智能识别与当代设计转译，构建可检索、可追溯、可持续生长的非遗数字平台。</p><div className="hero-actions"><Link className="primary-button" href="/patterns">探索纹样库</Link><Link className="ghost-button" href="/studio">进入智绣实验室</Link></div></section><section className="home-section"><SourceBadge source={patterns.source} /><div className="section-heading"><div><p className="eyebrow">PATTERN ARCHIVE</p><h2>纹样不止被收藏<br />也被重新理解</h2></div><p>建立来源、寓意、地域、类别和色彩之间的结构化关系，让每一次浏览都成为文化理解的入口。</p></div>{patterns.data.length > 0 ? <div className="featured-grid">{patterns.data.slice(0, 3).map((pattern, index) => <Link href="/patterns" className={`feature-card feature-${index}`} key={pattern.id}><span>{String(index + 1).padStart(2, "0")}</span><div className="mini-motif" /><small>{pattern.category}</small><h3>{pattern.name}</h3><p>{pattern.meaning}</p></Link>)}</div> : <div className="home-empty-state" role="status"><p className="eyebrow">资料审核中</p><h3>公开纹样正在整理</h3><p>首批纹样资料正在进行来源、版权与文化信息审核，通过后将在这里开放浏览。</p><Link className="ghost-button" href="/patterns">前往纹样库查看进度</Link></div>}</section><section className="portal-section"><article><p className="eyebrow">AI RECOGNITION</p><h2>从一张图<br />找到文化线索</h2><p>提交纹样图像，获取类别、主色与相似纹样候选。所有 AI 结果均保留模型版本，并等待人工复核。</p><Link className="primary-button" href="/studio">开始体验</Link></article><div className="portal-visual"><span className="scan-line"/><div className="target-box">纹样识别区域</div></div></section></main>;
}
