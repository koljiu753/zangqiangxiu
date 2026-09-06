"use client";

import Link from "next/link";
import { useActionState, useEffect, useRef, useState } from "react";
import type { CatalogReviewQueueItem, ReviewTask } from "@/types/domain";

export type ReviewAssignmentResult = { id: string; ok: boolean; message: string };
export type ReviewAssignmentState = { ok: boolean; message: string; results: ReviewAssignmentResult[] };
export type ReviewAssignmentAction = (state: ReviewAssignmentState, formData: FormData) => Promise<ReviewAssignmentState>;
export const emptyReviewAssignmentState: ReviewAssignmentState = { ok: false, message: "", results: [] };

function AssignmentFeedback({ state }: { state: ReviewAssignmentState }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { if (state.message) ref.current?.focus(); }, [state]);
  if (!state.message) return null;
  return <div ref={ref} className={state.ok ? "batch-feedback success" : "batch-feedback error"} role={state.ok ? "status" : "alert"} tabIndex={-1}><strong>{state.message}</strong>{state.results.length > 0 && <ul>{state.results.map((item) => <li key={item.id}><code>{item.id}</code><span className={item.ok ? "action-success" : "action-error"}>{item.ok ? "成功" : "失败"}：{item.message}</span></li>)}</ul>}</div>;
}

function SpecialtyCard({ item, task }: { item: CatalogReviewQueueItem; task?: ReviewTask }) {
  const signals = [
    item.lowResolution && `低清晰度${item.width && item.height ? `（${item.width}×${item.height}）` : "（尺寸未知）"}`,
    item.nameNeedsReview && "名称待核",
    item.duplicateName && `重名（${item.duplicateNameCount} 条）`,
    item.categoryNeedsReview && "未分类",
    (item.categorySuggestionCode || item.categorySuggestionLabel) && `分类建议：${item.categorySuggestionLabel || item.categorySuggestionCode}`,
  ].filter(Boolean) as string[];
  return <article className="review-queue-card specialty-card">
    <header><div><span className={`status-pill ${item.status}`}>{item.status}</span><span className="visibility-pill">{item.visibility}</span></div><code>{item.patternId}</code></header>
    <div className="review-queue-heading"><div><p>{item.category || "未分类"}</p><h2>{item.name || "未命名纹样"}</h2></div><span className={`task-state ${task?.state || "unassigned"}`}>{task ? `${task.assignee} · ${task.state}` : "未分配"}</span></div>
    <ul className="specialty-signals">{signals.length ? signals.map((signal) => <li key={signal}>{signal}</li>) : <li className="clear">暂无专项风险信号</li>}</ul>
    <footer><span>{signals.length} 个专项信号</span><div><Link href={`/admin/patterns/${encodeURIComponent(item.patternId)}`}>进入审核详情</Link><Link href={`/admin/patterns/${encodeURIComponent(item.patternId)}/audit`}>审计记录</Link></div></footer>
  </article>;
}

export function ReviewQueueBoard({ items, tasks, csrfToken, assignAction: serverAssignAction }: { items: CatalogReviewQueueItem[]; tasks: ReviewTask[]; csrfToken: string; assignAction: ReviewAssignmentAction }) {
  const [selected, setSelected] = useState<string[]>([]);
  const [state, action, pending] = useActionState(async (previous: ReviewAssignmentState, formData: FormData) => {
    const next = await serverAssignAction(previous, formData);
    const succeeded = new Set(next.results.filter((item) => item.ok).map((item) => item.id));
    if (succeeded.size) setSelected((current) => current.filter((id) => !succeeded.has(id)));
    return next;
  }, emptyReviewAssignmentState);
  const selectedSet = new Set(selected), allSelected = items.length > 0 && selected.length === items.length;
  const selectAllRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (selectAllRef.current) selectAllRef.current.indeterminate = selected.length > 0 && !allSelected; }, [allSelected, selected.length]);
  const toggle = (id: string, checked: boolean) => setSelected((current) => checked ? [...new Set([...current, id])] : current.filter((item) => item !== id));
  return <>
    <section className="review-assignment-panel" aria-label="批量分派审核任务"><header><div><p className="eyebrow">QUEUE ASSIGNMENT</p><h2>批量分派</h2></div><label className="select-all"><input ref={selectAllRef} type="checkbox" checked={allSelected} onChange={(event) => setSelected(event.target.checked ? items.map((item) => item.patternId) : [])}/>全选当前 {items.length} 条</label></header><p className="batch-selection">已选择 <strong>{selected.length}</strong> 条。分派仅建立审核任务，不会更改版权状态或发布记录。</p><form action={action} className="review-assignment-form"><input type="hidden" name="csrfToken" value={csrfToken}/>{selected.map((id) => <input key={id} type="hidden" name="selectedIds" value={id}/>)}<label>审核人<input name="assignee" required maxLength={120} placeholder="输入审核人账号或标识"/></label><button type="submit" disabled={pending || selected.length === 0}>{pending ? "分派中…" : `分派选中 ${selected.length} 条记录`}</button></form><AssignmentFeedback state={state}/></section>
    <section className="review-queue" aria-label="审核候选记录">{items.map((item) => <div className="review-queue-selectable" key={item.patternId}><label className="candidate-select"><input type="checkbox" aria-label={`选择 ${item.name || item.patternId}`} checked={selectedSet.has(item.patternId)} onChange={(event) => toggle(item.patternId, event.target.checked)}/>加入批量分派</label><SpecialtyCard item={item} task={tasks.find((task) => task.patternId === item.patternId)}/></div>)}</section>
  </>;
}
