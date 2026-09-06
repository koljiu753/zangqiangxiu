import type { Metadata } from "next";
import Link from "next/link";
import { PatternAuditTimeline } from "@/components/pattern-audit-timeline";
import { getAdminPattern, getPatternAuditLogs } from "@/lib/admin-api";
import { requireAdmin } from "@/lib/admin-auth-server";
import type { AdminPattern, PatternAuditLog } from "@/types/domain";

export const metadata: Metadata = { title: "纹样审计记录" };
export const dynamic = "force-dynamic";

type Props = { params: Promise<{ id: string }> };

export default async function PatternAuditPage({ params }: Props) {
  const principal = await requireAdmin("reviewer");
  const { id } = await params;
  let data: [AdminPattern, PatternAuditLog[]] | undefined;
  let errorMessage: string | undefined;
  try {
    data = await Promise.all([getAdminPattern(id), getPatternAuditLogs(id)]);
  } catch (error) {
    errorMessage = error instanceof Error ? error.message : "未知错误";
  }
  if (!data) {
    return <main className="inner-page admin-page"><nav className="admin-breadcrumb"><Link href="/admin">返回运营审核后台</Link></nav><div className="admin-error" role="alert"><h1>无法读取审计记录</h1><p>{errorMessage}</p></div></main>;
  }
  const [pattern, logs] = data;
  return <main className="inner-page admin-page audit-page">
      <nav className="admin-breadcrumb" aria-label="面包屑"><Link href="/admin">运营审核后台</Link><span>/</span><span>{pattern.name}</span></nav>
      <header className="page-hero"><p className="eyebrow">AUDIT TRAIL</p><h1>审计记录</h1><p>{pattern.name} · {pattern.id} · 当前身份：{principal.subject}（{principal.role}）</p></header>
      <PatternAuditTimeline logs={logs} />
  </main>;
}
