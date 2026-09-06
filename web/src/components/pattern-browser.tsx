"use client";

import { useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import type { Pattern } from "@/types/domain";

export function PatternBrowser({ patterns }: { patterns: Pattern[] }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("全部");
  const categories = ["全部", ...new Set(patterns.map((item) => item.category))];
  const filtered = useMemo(() => patterns.filter((item) => (category === "全部" || item.category === category) && `${item.name}${item.meaning}${item.ethnicity}`.toLowerCase().includes(query.toLowerCase())), [patterns, query, category]);
  return <><div className="filter-bar"><label><span>检索纹样</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="名称、寓意或民族" /></label><div className="chips">{categories.map((item) => <button className={category === item ? "active" : ""} onClick={() => setCategory(item)} key={item}>{item}</button>)}</div></div><p className="result-count">共展示 {filtered.length} 个纹样</p><div className="pattern-grid">{filtered.map((pattern, index) => <Link className="pattern-card" href={`/patterns/${encodeURIComponent(pattern.id)}`} key={pattern.id}><div className={`pattern-art motif-${index % 6}`}>{pattern.imageUrl ? <Image src={pattern.imageUrl} alt={`${pattern.name}纹样`} fill sizes="(max-width: 800px) 100vw, 33vw" unoptimized /> : <span aria-hidden="true" />}</div><div className="pattern-copy"><small>{pattern.ethnicity} · {pattern.category}</small><h2>{pattern.name}</h2><p>{pattern.meaning || "文化信息待补充"}</p><div className="palette">{pattern.colors.map((color) => <i key={color} style={{ background: color }} title={color} />)}</div><b>查看纹样档案 →</b></div></Link>)}</div>{filtered.length === 0 && <div className="empty-state"><h2>没有匹配的纹样</h2><p>换一个关键词或分类试试。</p></div>}</>;
}
