import type { Metadata } from "next";
import Link from "next/link";
import { AdminBatchReview } from "@/components/admin-batch-review";
import { getAdminPatterns } from "@/lib/admin-api";
import { adminPageHref, type AdminListFilters } from "@/lib/admin-bulk";
import { csrfFor, requireAdmin } from "@/lib/admin-auth-server";

export const metadata: Metadata = { title: "运营审核后台" };
export const dynamic = "force-dynamic";

type Query = { status?: string; visibility?: string; risk?: string; page?: string };
type Props = { searchParams: Promise<Query> };

function positivePage(value?: string) {
  const page = Number.parseInt(value || "1", 10);
  return Number.isSafeInteger(page) && page > 0 ? page : 1;
}

export default async function AdminPage({ searchParams }: Props) {
  const principal = await requireAdmin("reviewer");
  const csrfToken = await csrfFor(principal);
  const query = await searchParams;
  const filters: AdminListFilters = { status: query.status, visibility: query.visibility, risk: query.risk };
  const page = positivePage(query.page);
  let result;
  try {
    result = await getAdminPatterns({ ...filters, page });
  } catch (error) {
    return <main className="inner-page"><header className="page-hero"><p className="eyebrow">OPERATIONS REVIEW</p><h1>运营审核后台</h1></header><div className="admin-error" role="alert"><h2>无法连接目录服务</h2><p>{error instanceof Error ? error.message : "未知错误"}</p></div></main>;
  }

  const lastPage = Math.max(result.pages, 1);
  return <main className="inner-page admin-page">
    <header className="page-hero">
      <p className="eyebrow">OPERATIONS REVIEW</p><h1>运营审核后台</h1>
      <p>当前身份：{principal.subject}（{principal.role}）。目录服务会再次执行发布条件校验。</p>
      <Link className="primary-button" href="/admin/review">进入审核工作台</Link>
      <Link className="ghost-button" href="/admin/dashboard">查看数据治理仪表盘</Link>
      <form action="/api/admin/logout" method="post"><button type="submit">退出登录</button></form>
    </header>
    <form className="admin-filters">
      <label>状态<select name="status" defaultValue={filters.status || ""}><option value="">全部</option><option value="draft">draft</option><option value="published">published</option><option value="archived">archived</option></select></label>
      <label>可见性<select name="visibility" defaultValue={filters.visibility || ""}><option value="">全部</option><option value="internal_only">internal_only</option><option value="public">public</option></select></label>
      <label>风险<select name="risk" defaultValue={filters.risk || "any"}><option value="any">全部</option><option value="has_issues">有审核风险</option><option value="rights_unverified">版权未核验</option><option value="ready">满足发布条件</option></select></label>
      <button type="submit">筛选</button>
    </form>
    <p className="result-count">共 {result.total} 条候选记录，当前第 {result.page} / {lastPage} 页</p>
    {result.items.length > 0 && <AdminBatchReview patterns={result.items} csrfToken={csrfToken} canPublish={principal.role === "publisher"} />}
    {result.items.length === 0 && <div className="empty-state"><h2>没有符合条件的记录</h2><p>调整筛选条件或返回上一页后重试。</p></div>}
    <nav className="hero-actions" aria-label="候选记录分页">
      {result.page > 1 ? <Link className="ghost-button" href={adminPageHref(filters, result.page - 1)}>上一页</Link> : <span className="ghost-button" aria-disabled="true">上一页</span>}
      {result.page < result.pages ? <Link className="ghost-button" href={adminPageHref(filters, result.page + 1)}>下一页</Link> : <span className="ghost-button" aria-disabled="true">下一页</span>}
    </nav>
  </main>;
}
