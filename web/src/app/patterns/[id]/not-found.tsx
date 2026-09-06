import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "纹样未找到" };

export default function PatternNotFound() {
  return <main className="inner-page not-found-page"><section className="not-found-card"><p className="eyebrow">PATTERN NOT FOUND · 404</p><h1>没有找到这个纹样</h1><p>该纹样可能尚未公开、正在审核，或档案地址已经变更。</p><div className="hero-actions"><Link className="primary-button" href="/patterns">返回纹样库</Link><Link className="ghost-button" href="/">返回首页</Link></div></section></main>;
}
