import Link from "next/link";
import { auditChanges } from "@/components/pattern-audit-timeline";
import type { PatternAuditLog } from "@/types/domain";

const ACTION_LABELS: Record<string, string> = {
  created: "创建候选", updated: "更新资料", reviewed: "完成审核", published: "发布纹样",
  assigned: "分派审核", review_assigned: "分派审核", review_reassigned: "改派审核",
  review_bulk_assigned: "批量分派", review_bulk_reassigned: "批量改派",
  review_approved: "审核通过", review_rejected: "审核驳回", review_needs_more: "要求补充",
  publish_validation_failed: "发布门禁未通过", publish_sync_failed: "AI 同步失败",
};

function valueSummary(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  const text = typeof value === "object" ? JSON.stringify(value) : String(value);
  return text.length > 90 ? `${text.slice(0, 87)}…` : text;
}

export function AuditLogList({ logs }: { logs: PatternAuditLog[] }) {
  if (!logs.length) return <div className="empty-state"><h2>没有符合条件的审计记录</h2><p>调整筛选条件或时间范围后重试。</p></div>;
  return <ol className="global-audit-list">
    {logs.map((log) => {
      const changes = auditChanges(log);
      return <li key={log.id}>
        <article>
          <header>
            <div><strong>{ACTION_LABELS[log.action] || log.action}</strong><span className="audit-actor">{log.actor}</span></div>
            <time dateTime={log.createdAt}>{new Date(log.createdAt).toLocaleString("zh-CN", { hour12: false })}</time>
          </header>
          <p className="audit-pattern"><span>纹样</span><Link href={`/admin/patterns/${encodeURIComponent(log.patternId)}/audit`}>{log.patternId}</Link></p>
          {changes.length ? <ul className="audit-summary" aria-label="变更摘要">{changes.slice(0, 4).map((change) => <li key={change.field}><strong>{change.field}</strong><del>{valueSummary(change.before)}</del><span aria-hidden="true">→</span><ins>{valueSummary(change.after)}</ins></li>)}{changes.length > 4 && <li className="audit-more">另有 {changes.length - 4} 个字段发生变化</li>}</ul> : <p className="audit-no-change">操作未产生可见字段变化。</p>}
        </article>
      </li>;
    })}
  </ol>;
}
