import Link from "next/link";

export function SiteHeader() {
  return <header className="site-header"><Link className="brand" href="/"><span className="brand-mark">绣</span><span><strong>智绣乡村</strong><small>ARE LINGXIU</small></span></Link><nav><Link href="/">首页</Link><Link href="/patterns">纹样数据库</Link><Link href="/studio">智绣实验室</Link></nav></header>;
}
