import type { Metadata } from "next";
import Link from "next/link";
import { getCatalogStats } from "@/lib/admin-api";
import { requireAdmin } from "@/lib/admin-auth-server";
import { toGovernanceStats, type GovernanceStats } from "@/lib/governance-dashboard";

export const metadata: Metadata = { title: "数据治理仪表盘" };
export const dynamic = "force-dynamic";

const cards: Array<{ key: keyof GovernanceStats; label: string; note: string; href: string }> = [
  { key: "total", label: "全部档案", note: "当前目录收录总量", href: "/admin" },
  { key: "draft", label: "草稿", note: "待整理与审核", href: "/admin?status=draft" },
  { key: "published", label: "已发布", note: "已通过公开校验", href: "/admin?status=published" },
  { key: "rightsUnverified", label: "版权未核验", note: "需补充授权依据", href: "/admin?risk=rights_unverified" },
  { key: "hasIssues", label: "存在风险", note: "有未清零的审核项", href: "/admin?risk=has_issues" },
  { key: "ready", label: "可发布", note: "满足当前发布条件", href: "/admin?risk=ready" },
];

export default async function AdminDashboardPage() {
  const principal = await requireAdmin("reviewer");
  let stats: GovernanceStats | null = null;
  let loadError = "";
  try {
    stats = toGovernanceStats(await getCatalogStats());
  } catch (error) { loadError = error instanceof Error ? error.message : "未知错误"; }

  if (!stats) return <main className="inner-page admin-page"><nav className="admin-breadcrumb"><Link href="/admin">返回运营审核后台</Link></nav><div className="admin-error" role="alert"><h1>无法读取治理统计</h1><p>{loadError}</p></div></main>;
  return <main className="inner-page admin-page governance-page">
    <nav className="admin-breadcrumb" aria-label="后台导航"><Link href="/admin">运营审核</Link><span>/</span><strong>数据治理仪表盘</strong></nav>
    <header className="page-hero"><p className="eyebrow">DATA GOVERNANCE</p><h1>数据治理仪表盘</h1><p>当前身份：{principal.subject}（{principal.role}）。指标为当前目录实时统计，风险项可能彼此重叠。</p></header>
    <section className="governance-grid" aria-label="治理指标">{cards.map((card) => <Link href={card.href} className={`governance-card metric-${card.key}`} key={card.key}><small>{card.label}</small><strong>{stats![card.key]}</strong><span>{card.note} →</span></Link>)}</section>
    <section className="governance-actions"><article><p className="eyebrow">REVIEW QUEUE</p><h2>审核工作台</h2><p>按版权、风险与可发布状态分流候选记录，逐条处理发布阻塞原因。</p><Link className="primary-button" href="/admin/review">进入审核队列</Link></article><article><p className="eyebrow">REVIEW OPERATIONS</p><h2>审核运营看板</h2><p>查看任务完成率、审核人工作量和各状态任务明细，及时识别积压。</p><Link className="ghost-button" href="/admin/review/operations">查看运营数据</Link></article><article><p className="eyebrow">AUDIT TRAIL</p><h2>全局审计日志</h2><p>按操作者、动作、纹样和时间范围追溯目录治理操作，查看变更前后摘要。</p><Link className="ghost-button" href="/admin/audit">查询审计记录</Link></article><article><p className="eyebrow">AI CONSISTENCY</p><h2>AI 一致性抽检</h2><p>上传代表性纹样，检查分类、色彩与相似档案候选，作为人工治理的辅助证据。</p><Link className="ghost-button" href="/studio">进入一致性抽检</Link></article><article><p className="eyebrow">CONTROLLED EXPORT</p><h2>导出审核清单</h2><p>CSV 由服务端生成，包含版权、风险、来源和审核字段，不会暴露 Catalog 管理令牌。</p><a className="primary-button" href="/admin/dashboard/export">导出 CSV</a></article></section>
  </main>;
}
