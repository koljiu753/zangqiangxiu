import type { Metadata } from "next";
import Link from "next/link";
import { AuditLogList } from "@/components/audit-log-list";
import { getAuditLogs, type AuditLogFilters } from "@/lib/admin-api";
import { requireAdmin } from "@/lib/admin-auth-server";

export const metadata: Metadata = { title: "全局审计日志" };
export const dynamic = "force-dynamic";

type Query = { actor?: string; action?: string; patternId?: string; q?: string; from?: string; to?: string; page?: string };
type Props = { searchParams: Promise<Query> };

function positivePage(value?: string) {
  const page = Number.parseInt(value || "1", 10);
  return Number.isSafeInteger(page) && page > 0 ? page : 1;
}

export function auditPageHref(filters: AuditLogFilters, page: number) {
  const params = new URLSearchParams({ page: String(page) });
  (["actor", "action", "patternId", "q", "from", "to"] as const).forEach((key) => {
    const value = filters[key]?.trim();
    if (value) params.set(key, value);
  });
  return `/admin/audit?${params}`;
}

export default async function AuditLogsPage({ searchParams }: Props) {
  const principal = await requireAdmin("reviewer");
  const query = await searchParams;
  const filters: AuditLogFilters = {
    actor: query.actor, action: query.action, patternId: query.patternId, q: query.q,
    from: query.from, to: query.to, page: positivePage(query.page),
  };
  let result;
  try { result = await getAuditLogs(filters); }
  catch (error) { return <main className="inner-page admin-page"><nav className="admin-breadcrumb"><Link href="/admin/dashboard">数据治理仪表盘</Link><span>/</span><strong>审计日志</strong></nav><div className="admin-error" role="alert"><h1>无法读取审计日志</h1><p>{error instanceof Error ? error.message : "未知错误"}</p></div></main>; }

  const lastPage = Math.max(result.pages, 1);
  return <main className="inner-page admin-page global-audit-page">
    <nav className="admin-breadcrumb" aria-label="后台导航"><Link href="/admin/dashboard">数据治理仪表盘</Link><span>/</span><strong>审计日志</strong><span>/</span><Link href="/admin/review">审核工作台</Link></nav>
    <header className="page-hero"><p className="eyebrow">AUDIT TRAIL</p><h1>全局审计日志</h1><p>当前身份：{principal.subject}（{principal.role}）。集中查询目录变更、审核与发布操作，记录按发生时间和序号稳定倒序展示。</p></header>
    <form className="admin-filters audit-filters">
      <label>综合搜索<input name="q" defaultValue={filters.q || ""} maxLength={100} placeholder="操作者、动作或纹样 ID" /></label>
      <label>操作者<input name="actor" defaultValue={filters.actor || ""} maxLength={200} placeholder="精确账号" /></label>
      <label>动作<input name="action" defaultValue={filters.action || ""} maxLength={200} placeholder="例如 updated" /></label>
      <label>纹样 ID<input name="patternId" defaultValue={filters.patternId || ""} maxLength={100} placeholder="精确 ID" /></label>
      <label>开始时间<input name="from" type="datetime-local" defaultValue={filters.from || ""} /></label>
      <label>结束时间<input name="to" type="datetime-local" defaultValue={filters.to || ""} /></label>
      <div className="audit-filter-actions"><button type="submit">查询日志</button><Link href="/admin/audit">清除筛选</Link></div>
    </form>
    <div className="queue-summary" role="status"><strong>{result.total}</strong><span>条审计记录</span><small>第 {result.page} / {lastPage} 页 · 每页 {result.pageSize} 条</small></div>
    <AuditLogList logs={result.items} />
    <nav className="hero-actions" aria-label="审计日志分页">
      {result.page > 1 ? <Link className="ghost-button" href={auditPageHref(filters, result.page - 1)}>上一页</Link> : <span className="ghost-button" aria-disabled="true">上一页</span>}
      {result.page < result.pages ? <Link className="ghost-button" href={auditPageHref(filters, result.page + 1)}>下一页</Link> : <span className="ghost-button" aria-disabled="true">下一页</span>}
    </nav>
  </main>;
}
