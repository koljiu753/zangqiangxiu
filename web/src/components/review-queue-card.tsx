import Link from "next/link";
import { getPublishBlockers } from "@/lib/admin-review";
import type { AdminPattern, ReviewTask } from "@/types/domain";

export function ReviewQueueCard({ pattern, task }: { pattern: AdminPattern; task?: ReviewTask }) {
  const blockers = getPublishBlockers(pattern);
  return <article className="review-queue-card">
    <header>
      <div><span className={`status-pill ${pattern.status}`}>{pattern.status}</span><span className="visibility-pill">{pattern.visibility}</span></div>
      <code>{pattern.id}</code>
    </header>
    <div className="review-queue-heading"><div><p>{pattern.category || "未分类"} · {pattern.ethnicity}</p><h2>{pattern.name || "未命名纹样"}</h2></div><div className="queue-state"><strong className={blockers.length ? "queue-blocked" : "queue-ready"}>{blockers.length ? `${blockers.length} 类阻塞` : "可发布"}</strong><span className={`task-state ${task?.state || "unassigned"}`}>{task ? `${task.assignee} · ${task.state}` : "未分配"}</span></div></div>
    {blockers.length ? <ul className="blocker-list">{blockers.map((blocker) => <li key={blocker.code}><strong>{blocker.label}</strong><span>{blocker.detail}</span><small>下一步：{blocker.action}</small></li>)}</ul> : <div className="readiness ready"><strong>发布校验已满足</strong><span>仍会由目录服务在发布时再次校验。</span></div>}
    <footer><span>更新于 {pattern.updatedAt.slice(0, 10)}</span><div><Link href={`/admin/patterns/${encodeURIComponent(pattern.id)}`}>进入审核详情</Link><Link href={`/admin/patterns/${encodeURIComponent(pattern.id)}/audit`}>审计记录</Link></div></footer>
  </article>;
}
