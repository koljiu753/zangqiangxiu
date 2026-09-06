import type { Metadata } from "next";
import Link from "next/link";
import { ReviewQueueCard } from "@/components/review-queue-card";
import { getAdminPatterns, getReviewTasks } from "@/lib/admin-api";
import { adminPageHref, type AdminListFilters } from "@/lib/admin-bulk";
import { requireAdmin } from "@/lib/admin-auth-server";

export const metadata: Metadata = { title: "纹样审核工作台" };
export const dynamic = "force-dynamic";
type Query = { status?: string; visibility?: string; risk?: string; page?: string };
type Props = { searchParams: Promise<Query> };

function positivePage(value?: string) { const page = Number.parseInt(value || "1", 10); return Number.isSafeInteger(page) && page > 0 ? page : 1; }

export default async function ReviewWorkbenchPage({ searchParams }: Props) {
  const principal = await requireAdmin("reviewer");
  const query = await searchParams;
  const filters: AdminListFilters = { status: query.status || "draft", visibility: query.visibility, risk: query.risk || "any" };
  const page = positivePage(query.page);
  let result, tasks;
  try { [result, tasks] = await Promise.all([getAdminPatterns({ ...filters, page }), getReviewTasks()]); }
  catch (error) { return <main className="inner-page admin-page"><div className="admin-error" role="alert"><h1>无法读取审核队列</h1><p>{error instanceof Error ? error.message : "未知错误"}</p></div></main>; }
  const lastPage = Math.max(result.pages, 1);
  return <main className="inner-page admin-page review-workbench">
    <nav className="admin-breadcrumb"><Link href="/admin/dashboard">数据治理仪表盘</Link><span>/</span><strong>审核工作台</strong></nav>
    <header className="page-hero"><p className="eyebrow">REVIEW QUEUE</p><h1>纹样审核工作台</h1><p>当前身份：{principal.subject}（{principal.role}）。先识别阻塞原因，再进入详情补齐资料；发布仍由后端执行最终校验。</p></header>
    <nav className="review-quick-filters" aria-label="审核队列快捷筛选">
      <Link href="/admin/review?status=draft">待审核</Link><Link href="/admin/review?status=draft&risk=rights_unverified">版权待核</Link><Link href="/admin/review?status=draft&risk=has_issues">风险待处理</Link><Link href="/admin/review?status=draft&risk=ready">可发布</Link><Link href="/admin/review?status=published">已发布</Link>
    </nav>
    <form className="admin-filters">
      <label>状态<select name="status" defaultValue={filters.status || ""}><option value="">全部</option><option value="draft">draft</option><option value="published">published</option><option value="archived">archived</option></select></label>
      <label>可见性<select name="visibility" defaultValue={filters.visibility || ""}><option value="">全部</option><option value="internal_only">internal_only</option><option value="public">public</option></select></label>
      <label>阻塞类型<select name="risk" defaultValue={filters.risk || "any"}><option value="any">全部</option><option value="rights_unverified">版权待核</option><option value="has_issues">存在风险项</option><option value="ready">满足发布条件</option></select></label><button type="submit">更新队列</button>
    </form>
    <div className="queue-summary"><strong>{result.total}</strong><span>条记录符合当前条件</span><small>第 {result.page} / {lastPage} 页</small></div>
    {result.items.length ? <section className="review-queue" aria-label="审核候选记录">{result.items.map((pattern) => <ReviewQueueCard pattern={pattern} task={tasks.find((task) => task.patternId === pattern.id)} key={pattern.id} />)}</section> : <div className="empty-state"><h2>当前队列已清空</h2><p>可以切换其他阻塞类型，或返回数据治理仪表盘查看总体进度。</p></div>}
    <nav className="hero-actions" aria-label="审核队列分页">{result.page > 1 ? <Link className="ghost-button" href={adminPageHref(filters, result.page - 1).replace("/admin?", "/admin/review?")}>上一页</Link> : <span className="ghost-button" aria-disabled="true">上一页</span>}{result.page < result.pages ? <Link className="ghost-button" href={adminPageHref(filters, result.page + 1).replace("/admin?", "/admin/review?")}>下一页</Link> : <span className="ghost-button" aria-disabled="true">下一页</span>}</nav>
  </main>;
}
