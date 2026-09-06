import type { PatternAuditLog } from "@/types/domain";

const ACTION_LABELS: Record<string, string> = {
  created: "创建候选",
  updated: "更新资料",
  reviewed: "完成审核",
  published: "发布纹样",
  publish_validation_failed: "发布门禁未通过",
  publish_sync_failed: "AI 同步失败",
};

const FIELD_LABELS: Record<string, string> = {
  name: "名称", category: "分类", ethnicity: "民族", meaning: "文化寓意", colors: "色板",
  imageUrl: "图片", status: "状态", visibility: "可见性", source: "来源", rights: "版权",
  review: "审核", aiSync: "AI 同步",
};

type Change = { field: string; before: unknown; after: unknown };

function stable(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value, Object.keys(value as object).sort());
}

export function auditChanges(log: PatternAuditLog): Change[] {
  const before = log.before ?? {};
  const after = log.after ?? {};
  const ignored = new Set(["id", "createdAt", "updatedAt"]);
  return [...new Set([...Object.keys(before), ...Object.keys(after)])]
    .filter((field) => !ignored.has(field) && stable(before[field]) !== stable(after[field]))
    .map((field) => ({ field, before: before[field], after: after[field] }));
}

function display(value: unknown) {
  const rendered = stable(value);
  return rendered.length > 180 ? `${rendered.slice(0, 177)}…` : rendered;
}

export function PatternAuditTimeline({ logs }: { logs: PatternAuditLog[] }) {
  if (logs.length === 0) return <div className="empty-state"><h2>暂无审计记录</h2><p>此纹样还没有可展示的运营操作。</p></div>;
  return <ol className="audit-timeline">
    {logs.map((log) => {
      const changes = auditChanges(log);
      return <li key={log.id} className={`audit-event action-${log.action}`}>
        <span className="audit-dot" aria-hidden="true" />
        <article>
          <header><div><strong>{ACTION_LABELS[log.action] || log.action}</strong><span>{log.actor}</span></div><time dateTime={log.createdAt}>{new Date(log.createdAt).toLocaleString("zh-CN", { hour12: false })}</time></header>
          {changes.length > 0 ? <dl className="audit-changes">{changes.map((change) => <div key={change.field}><dt>{FIELD_LABELS[change.field] || change.field}</dt><dd><del>{display(change.before)}</del><span aria-hidden="true">→</span><ins>{display(change.after)}</ins></dd></div>)}</dl> : <p className="audit-no-change">操作未产生可见字段变化。</p>}
        </article>
      </li>;
    })}
  </ol>;
}
