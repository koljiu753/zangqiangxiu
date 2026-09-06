import type { Metadata } from "next";
import Link from "next/link";
import { bulkAssignReviews } from "@/app/admin/actions";
import { ReviewQueueBoard } from "@/components/review-queue-board";
import { getReviewQueuePatterns, getReviewQueueSummary, getReviewTasks } from "@/lib/admin-api";
import { csrfFor, requireAdmin } from "@/lib/admin-auth-server";
import type { ReviewQueueKind } from "@/types/domain";

export const metadata: Metadata = { title: "纹样审核工作台" };
export const dynamic = "force-dynamic";
type Query = { queue?: string; q?: string; suggestion?: string; page?: string };
type Props = { searchParams: Promise<Query> };
const queueKinds: ReviewQueueKind[] = ["all", "low_resolution", "name_review", "duplicate_name", "uncategorized", "category_suggestion"];
function positivePage(value?: string) { const page = Number.parseInt(value || "1", 10); return Number.isSafeInteger(page) && page > 0 ? page : 1; }
function queueKind(value?: string): ReviewQueueKind { return queueKinds.includes(value as ReviewQueueKind) ? value as ReviewQueueKind : "all"; }
function pageHref(query: Query, page: number) { const params = new URLSearchParams(); params.set("queue", queueKind(query.queue)); params.set("page", String(page)); if (query.q) params.set("q", query.q); if (query.suggestion) params.set("suggestion", query.suggestion); return `/admin/review?${params}`; }

export default async function ReviewWorkbenchPage({ searchParams }: Props) {
  const principal = await requireAdmin("reviewer");
  const csrfToken = await csrfFor(principal);
  const query = await searchParams, queue = queueKind(query.queue), page = positivePage(query.page);
  let result, tasks, summary;
  try { [result, tasks, summary] = await Promise.all([getReviewQueuePatterns({ queue, page, q: query.q, suggestion: query.suggestion }), getReviewTasks(), getReviewQueueSummary()]); }
  catch (error) { return <main className="inner-page admin-page"><div className="admin-error" role="alert"><h1>无法读取审核队列</h1><p>{error instanceof Error ? error.message : "未知错误"}</p></div></main>; }
  const filters: Array<{ key: ReviewQueueKind; label: string; count: number }> = [
    { key: "all", label: "全部", count: summary.total }, { key: "low_resolution", label: "低清晰度", count: summary.lowResolution },
    { key: "name_review", label: "名称待核", count: summary.nameNeedsReview }, { key: "duplicate_name", label: "重名", count: summary.duplicateName },
    { key: "uncategorized", label: "未分类", count: summary.uncategorized }, { key: "category_suggestion", label: "有分类建议", count: summary.categorySuggestion },
  ];
  const lastPage = Math.max(result.pages, 1);
  return <main className="inner-page admin-page review-workbench">
    <nav className="admin-breadcrumb"><Link href="/admin/dashboard">数据治理仪表盘</Link><span>/</span><strong>审核工作台</strong><span>/</span><Link href="/admin/review/operations">运营看板</Link><span>/</span><Link href="/admin/audit">审计日志</Link></nav>
    <header className="page-hero"><p className="eyebrow">SPECIALTY REVIEW QUEUES</p><h1>纹样审核工作台</h1><p>当前身份：{principal.subject}（{principal.role}）。专项信号由目录来源数据派生，用于分流处理，不会自动修改或发布档案。</p></header>
    <nav className="review-quick-filters" aria-label="专项审核队列">{filters.map((filter) => <Link aria-current={queue === filter.key ? "page" : undefined} href={`/admin/review?queue=${filter.key}`} key={filter.key}>{filter.label}<strong>{filter.count}</strong></Link>)}</nav>
    <form className="admin-filters"><input type="hidden" name="queue" value={queue}/><label>名称或分类<input name="q" defaultValue={query.q || ""} maxLength={100} placeholder="搜索当前专项"/></label><label>分类建议<input name="suggestion" defaultValue={query.suggestion || ""} maxLength={100} placeholder="建议编码或名称"/></label><button type="submit">更新队列</button></form>
    <div className="queue-summary"><strong>{result.total}</strong><span>条记录符合当前专项条件</span><small>第 {result.page} / {lastPage} 页 · 低清晰度阈值 {summary.lowResolutionEdge}px</small></div>
    {result.items.length ? <ReviewQueueBoard items={result.items} tasks={tasks} csrfToken={csrfToken} assignAction={bulkAssignReviews}/> : <div className="empty-state"><h2>当前队列已清空</h2><p>可以切换其他专项，或调整搜索条件。</p></div>}
    <nav className="hero-actions" aria-label="审核队列分页">{result.page > 1 ? <Link className="ghost-button" href={pageHref(query, result.page - 1)}>上一页</Link> : <span className="ghost-button" aria-disabled="true">上一页</span>}{result.page < result.pages ? <Link className="ghost-button" href={pageHref(query, result.page + 1)}>下一页</Link> : <span className="ghost-button" aria-disabled="true">下一页</span>}</nav>
  </main>;
}
