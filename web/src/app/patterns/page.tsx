import type { Metadata } from "next";
import { PatternBrowser } from "@/components/pattern-browser";
import { SourceBadge } from "@/components/source-badge";
import { getPatterns } from "@/lib/catalog-api";

export const metadata: Metadata = { title: "纹样数据库" };
export const dynamic = "force-dynamic";
export default async function PatternsPage() { const patterns = await getPatterns(); return <main className="inner-page"><header className="page-hero"><p className="eyebrow">EMBROIDERY PATTERN ARCHIVE</p><h1>藏羌纹样数据库</h1><p>按分类、民族与文化寓意探索纹样。正式数据将由后端审核发布。</p></header><SourceBadge source={patterns.source} /><PatternBrowser patterns={patterns.data} /></main>; }
