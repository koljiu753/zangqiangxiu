import Link from "next/link";
import type { ReviewOperationsPage, ReviewOperationsState } from "@/types/domain";

const stateLabels: Record<ReviewOperationsState, string> = { unassigned: "未分配", assigned: "待处理", approved: "已通过", rejected: "已拒绝", needs_more: "需补充" };

export function ReviewOperationsBoard({ data }: { data: ReviewOperationsPage }) {
  const metrics = [
    ["任务总量", data.summary.total], ["未分配", data.summary.unassigned], ["待处理", data.summary.assigned],
    ["已通过", data.summary.approved], ["已拒绝", data.summary.rejected], ["需补充", data.summary.needsMore],
  ] as const;
  return <>
    <section className="operations-metrics" aria-label="审核任务指标">
      {metrics.map(([label, value]) => <article key={label}><span>{label}</span><strong>{value}</strong></article>)}
      <article className="completion-metric"><span>完成率</span><strong>{data.summary.completionRate.toFixed(1)}%</strong><progress max="100" value={data.summary.completionRate} aria-label={`审核完成率 ${data.summary.completionRate.toFixed(1)}%`}/></article>
    </section>
    <section className="operations-section" aria-labelledby="workload-title"><header><div><p className="eyebrow">WORKLOAD</p><h2 id="workload-title">审核人工作量</h2></div><span>{data.workloads.length} 位审核人</span></header>
      {data.workloads.length ? <div className="table-scroll"><table><thead><tr><th scope="col">审核人</th><th scope="col">总量</th><th scope="col">待处理</th><th scope="col">通过</th><th scope="col">拒绝</th><th scope="col">需补充</th><th scope="col">完成率</th></tr></thead><tbody>{data.workloads.map((row) => <tr key={row.assignee}><th scope="row">{row.assignee}</th><td>{row.total}</td><td>{row.assigned}</td><td>{row.approved}</td><td>{row.rejected}</td><td>{row.needsMore}</td><td>{row.completionRate.toFixed(1)}%</td></tr>)}</tbody></table></div> : <p className="operations-empty">尚无已分配任务。</p>}
    </section>
    <section className="operations-section" aria-labelledby="task-table-title"><header><div><p className="eyebrow">TASK REGISTER</p><h2 id="task-table-title">任务明细</h2></div><span>共 {data.total} 条</span></header>
      {data.items.length ? <div className="table-scroll"><table><thead><tr><th scope="col">纹样</th><th scope="col">状态</th><th scope="col">审核人</th><th scope="col">分派时间</th><th scope="col">决定人</th><th scope="col">决定时间</th></tr></thead><tbody>{data.items.map((item) => <tr key={item.patternId}><th scope="row"><Link href={`/admin/patterns/${encodeURIComponent(item.patternId)}`}>{item.patternName || item.patternId}</Link><small>{item.patternName ? item.patternId : ""}</small></th><td><span className={`task-state ${item.state}`}>{stateLabels[item.state]}</span></td><td>{item.assignee || "—"}</td><td>{formatTime(item.assignedAt)}</td><td>{item.decidedBy || "—"}</td><td>{formatTime(item.decidedAt)}</td></tr>)}</tbody></table></div> : <p className="operations-empty">当前筛选条件下没有任务。</p>}
    </section>
  </>;
}

function formatTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "—" : new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Shanghai" }).format(date);
}
