"use client";

import { useActionState } from "react";
import { assignReview, decideReview, saveEvidence, type AdminActionState } from "@/app/admin/actions";
import type { AdminPattern, ReviewTask } from "@/types/domain";

const initial: AdminActionState = { ok: false, message: "" };
function Feedback({ state }: { state: AdminActionState }) { return <span className={state.ok ? "action-success" : "action-error"} aria-live="polite">{state.message}</span>; }

export function ReviewWorkflowPanel({ pattern, task, csrfToken }: { pattern: AdminPattern; task?: ReviewTask; csrfToken: string }) {
  const [evidenceState, evidenceAction, evidencePending] = useActionState(saveEvidence, initial);
  const [assignState, assignAction, assignPending] = useActionState(assignReview, initial);
  const [decisionState, decisionAction, decisionPending] = useActionState(decideReview, initial);
  const evidence = pattern.rights.evidence || [];
  return <section className="workflow-panel">
    <article><header><p className="eyebrow">EVIDENCE</p><h2>来源与权利凭证</h2></header>
      {evidence.length ? <ul className="evidence-list">{evidence.map((item) => <li key={item.id}><strong>{item.filename}</strong><span>{item.contentType || "类型未知"}{item.sizeBytes != null ? ` · ${formatBytes(item.sizeBytes)}` : ""}</span>{item.storageKey ? <a href={`/admin/patterns/${encodeURIComponent(pattern.id)}/evidence/${encodeURIComponent(item.id)}`}>安全下载</a> : <small>{item.url ? "历史外部凭证（不可代理下载）" : "文件尚未入库"}</small>}</li>)}</ul> : <p className="workflow-empty">尚未上传凭证文件。</p>}
      <form action={evidenceAction} className="workflow-form"><input type="hidden" name="id" value={pattern.id}/><input type="hidden" name="csrfToken" value={csrfToken}/>
        <label className="wide">来源说明<textarea name="sourceDescription" defaultValue={pattern.source.description || ""}/></label><label className="wide">来源主张<input name="originClaim" defaultValue={pattern.source.originClaim}/></label>
        <label>版权状态<select name="rightsStatus" defaultValue={pattern.rights.status}><option value="unverified">unverified</option><option value="pending">pending</option><option value="verified">verified</option><option value="rejected">rejected</option></select></label><label>权利人<input name="rightsOwner" defaultValue={pattern.rights.owner || ""}/></label><label>授权依据<input name="rightsLicense" defaultValue={pattern.rights.license || ""}/></label><label>最近核验身份<input value={pattern.rights.verifiedBy || "尚未核验"} disabled title="核验身份由登录会话自动记录"/></label><label>核验时间<input value={pattern.rights.verifiedAt?.slice(0, 16) || "保存为 verified 时自动记录"} disabled/></label><label className="wide">核验说明<textarea name="verificationNote" defaultValue={pattern.rights.verificationNote || ""}/></label><label className="wide">内部审核备注<textarea name="reviewNote" defaultValue={pattern.review.note || ""}/></label>
        <fieldset className="wide"><legend>上传一份新凭证（可选）</legend><label className="evidence-upload">选择文件<input name="evidenceFile" type="file" accept="application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png"/><small>支持 PDF、JPEG、PNG，单个文件不超过 10 MiB。文件类型、大小与 SHA-256 均由服务端校验和生成。</small></label></fieldset>
        <div className="form-actions wide"><button disabled={evidencePending}>{evidencePending ? "保存中…" : "保存来源与核验资料"}</button><Feedback state={evidenceState}/></div>
      </form>
    </article>
    <article><header><p className="eyebrow">REVIEW TASK</p><h2>审核任务</h2></header>
      {task ? <dl className="task-summary"><div><dt>审核人</dt><dd>{task.assignee}</dd></div><div><dt>状态</dt><dd><span className={`task-state ${task.state}`}>{task.state}</span></dd></div><div><dt>分配时间</dt><dd>{task.assignedAt}</dd></div>{task.decisionNote && <div><dt>决定说明</dt><dd>{task.decisionNote}</dd></div>}</dl> : <p className="workflow-empty">尚未分配审核任务。</p>}
      <form action={assignAction} className="inline-workflow-form"><input type="hidden" name="id" value={pattern.id}/><input type="hidden" name="csrfToken" value={csrfToken}/><label>分配或改派给<input name="assignee" defaultValue={task?.assignee || ""} required/></label><button disabled={assignPending}>{assignPending ? "分配中…" : task ? "重新分配" : "分配任务"}</button><Feedback state={assignState}/></form>
      {task && pattern.status === "draft" && <form action={decisionAction} className="workflow-form decision-form"><input type="hidden" name="id" value={pattern.id}/><input type="hidden" name="csrfToken" value={csrfToken}/><label>审核决定<select name="decision" defaultValue="approved"><option value="approved">通过</option><option value="needs_more">退回补充</option><option value="rejected">拒绝</option></select></label><label className="wide">决定说明<textarea name="decisionNote"/></label><label className="wide">风险项（退回/拒绝时必填）<textarea name="decisionIssues" placeholder="多项用逗号或换行分隔"/></label><div className="form-actions wide"><button disabled={decisionPending}>{decisionPending ? "提交中…" : "记录审核决定"}</button><Feedback state={decisionState}/></div></form>}
    </article>
  </section>;
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / 1024 / 1024).toFixed(1)} MiB`;
}
