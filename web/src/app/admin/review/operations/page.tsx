import type { Metadata } from "next";
import Link from "next/link";
import { ReviewOperationsBoard } from "@/components/review-operations-board";
import { getReviewOperations } from "@/lib/admin-api";
import { requireAdmin } from "@/lib/admin-auth-server";
import type { ReviewOperationsState } from "@/types/domain";

export const metadata: Metadata = { title: "审核运营看板" };
export const dynamic = "force-dynamic";
type Query = { assignee?: string; state?: string; q?: string; page?: string };
const states: ReviewOperationsState[] = ["unassigned", "assigned", "approved", "rejected", "needs_more"];
function clean(value?: string) { return value?.trim().slice(0, 100) || undefined; }
function state(value?: string) { return states.includes(value as ReviewOperationsState) ? value as ReviewOperationsState : undefined; }
function page(value?: string) { const parsed = Number.parseInt(value || "1", 10); return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : 1; }
function href(query: Query, target: number) { const params = new URLSearchParams(); if (clean(query.assignee)) params.set("assignee", clean(query.assignee)!); if (state(query.state)) params.set("state", state(query.state)!); if (clean(query.q)) params.set("q", clean(query.q)!); params.set("page", String(target)); return `/admin/review/operations?${params}`; }

export default async function ReviewOperations({ searchParams }: { searchParams: Promise<Query> }) {
  const principal = await requireAdmin("reviewer");
  const query = await searchParams;
  let data;
  try { data = await getReviewOperations({ assignee: clean(query.assignee), state: state(query.state), q: clean(query.q), page: page(query.page) }); }
  catch (error) { return <main className="inner-page admin-page"><nav className="admin-breadcrumb"><Link href="/admin/review">审核工作台</Link></nav><div className="admin-error" role="alert"><h1>无法读取审核运营数据</h1><p>{error instanceof Error ? error.message : "未知错误"}</p></div></main>; }
  const lastPage = Math.max(data.pages, 1);
  return <main className="inner-page admin-page operations-page">
    <nav className="admin-breadcrumb"><Link href="/admin/dashboard">数据治理仪表盘</Link><span>/</span><Link href="/admin/review">审核工作台</Link><span>/</span><strong>运营看板</strong></nav>
    <header className="page-hero"><p className="eyebrow">REVIEW OPERATIONS</p><h1>审核运营看板</h1><p>当前身份：{principal.subject}（{principal.role}）。汇总任务进度与人员负载，所有数据均为只读展示。</p></header>
    <form className="admin-filters" aria-label="筛选审核任务"><label>审核人<input name="assignee" defaultValue={clean(query.assignee) || ""} maxLength={100} placeholder="账号或标识"/></label><label>任务状态<select name="state" defaultValue={state(query.state) || ""}><option value="">全部状态</option><option value="unassigned">未分配</option><option value="assigned">待处理</option><option value="approved">已通过</option><option value="rejected">已拒绝</option><option value="needs_more">需补充</option></select></label><label>纹样搜索<input name="q" defaultValue={clean(query.q) || ""} maxLength={100} placeholder="名称或档案 ID"/></label><button type="submit">更新看板</button></form>
    <ReviewOperationsBoard data={data}/>
    <nav className="hero-actions" aria-label="审核任务分页">{data.page > 1 ? <Link className="ghost-button" href={href(query, data.page - 1)}>上一页</Link> : <span className="ghost-button" aria-disabled="true">上一页</span>}<span>第 {data.page} / {lastPage} 页</span>{data.page < data.pages ? <Link className="ghost-button" href={href(query, data.page + 1)}>下一页</Link> : <span className="ghost-button" aria-disabled="true">下一页</span>}</nav>
  </main>;
}
