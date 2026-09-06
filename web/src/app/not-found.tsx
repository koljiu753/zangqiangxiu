import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "页面未找到" };

export default function NotFound() {
  return <main className="inner-page not-found-page"><section className="not-found-card"><p className="eyebrow">PAGE NOT FOUND · 404</p><h1>这个页面不存在</h1><p>你访问的地址可能已变更，也可能暂时不可用。可以返回首页，或继续浏览纹样资料。</p><div className="hero-actions"><Link className="primary-button" href="/patterns">返回纹样库</Link><Link className="ghost-button" href="/">返回首页</Link></div></section></main>;
}
