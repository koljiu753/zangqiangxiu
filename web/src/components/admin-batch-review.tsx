"use client";

import { useActionState, useState } from "react";
import { bulkPublishPatterns, bulkUpdatePatterns } from "@/app/admin/actions";
import { AdminPatternCard } from "@/components/admin-pattern-card";
import { emptyBatchState, type BatchActionState } from "@/lib/admin-bulk";
import type { AdminPattern } from "@/types/domain";

function SelectedInputs({ ids }: { ids: string[] }) {
  return <>{ids.map((id) => <input key={id} type="hidden" name="selectedIds" value={id} />)}</>;
}

function BatchResults({ state }: { state: BatchActionState }) {
  if (!state.message) return null;
  return <div className={state.ok ? "batch-feedback success" : "batch-feedback error"} role="status">
    <strong>{state.message}</strong>
    {state.results.length > 0 && <ul>{state.results.map((item) => <li key={item.id}><code>{item.id}</code><span className={item.ok ? "action-success" : "action-error"}>{item.ok ? "成功" : "失败"}：{item.message}</span></li>)}</ul>}
  </div>;
}

export function AdminBatchReview({ patterns, csrfToken, canPublish }: { patterns: AdminPattern[]; csrfToken: string; canPublish: boolean }) {
  const [selected, setSelected] = useState<string[]>([]);
  const [updateState, updateAction, updatePending] = useActionState(bulkUpdatePatterns, emptyBatchState);
  const [publishState, publishAction, publishPending] = useActionState(bulkPublishPatterns, emptyBatchState);
  const selectedSet = new Set(selected);
  const allSelected = patterns.length > 0 && selected.length === patterns.length;
  const toggle = (id: string, checked: boolean) => setSelected((current) => checked ? [...new Set([...current, id])] : current.filter((item) => item !== id));

  return <>
    <section className="batch-panel" aria-label="批量审核">
      <header><div><p className="eyebrow">BATCH REVIEW</p><h2>批量审核</h2></div><label className="select-all"><input type="checkbox" checked={allSelected} onChange={(event) => setSelected(event.target.checked ? patterns.map((item) => item.id) : [])} />全选当前 {patterns.length} 条</label></header>
      <p className="batch-selection">已选择 <strong>{selected.length}</strong> 条。发布仍会逐条执行目录服务的版权和风险校验。</p>
      <form action={updateAction} className="batch-form">
        <input type="hidden" name="csrfToken" value={csrfToken} /><SelectedInputs ids={selected} />
        <p className="wide">审核身份将由当前登录会话自动记录，不能在表单中代填。</p>
        <label>风险项处理<select name="bulkIssueMode" defaultValue="replace"><option value="replace">用下方内容覆盖</option><option value="clear">确认清空</option></select></label>
        <label className="wide">新风险项<textarea name="bulkIssues" placeholder="多项用逗号或换行分隔" /></label>
        <div className="batch-actions"><button type="submit" disabled={updatePending || selected.length === 0}>{updatePending ? "审核中…" : "审核选中记录"}</button><span>版权资料仍需在单条记录中独立核验。</span></div>
      </form>
      <BatchResults state={updateState} />
      <form action={publishAction} className="batch-publish-form">
        <input type="hidden" name="csrfToken" value={csrfToken} /><SelectedInputs ids={selected} />
        <button type="submit" disabled={!canPublish || publishPending || selected.length === 0}>{publishPending ? "发布中…" : canPublish ? "批量发布选中记录" : "需要发布员权限"}</button>
      </form>
      <BatchResults state={publishState} />
    </section>
    <div className="admin-list">{patterns.map((pattern) => <AdminPatternCard pattern={pattern} csrfToken={csrfToken} canPublish={canPublish} selected={selectedSet.has(pattern.id)} onSelectedChange={(checked) => toggle(pattern.id, checked)} key={pattern.id}/>)}</div>
  </>;
}
