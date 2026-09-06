"use client";

import { useActionState } from "react";
import Link from "next/link";
import type { AdminPattern } from "@/types/domain";
import { publishPattern, savePattern, type AdminActionState } from "@/app/admin/actions";
import { getPublishReadiness } from "@/lib/admin-review";
import { AdminPatternPreview } from "@/components/admin-pattern-preview";

const initial: AdminActionState = { ok: false, message: "" };

export function AdminPatternCard({ pattern, csrfToken, canPublish, selected = false, onSelectedChange }: { pattern: AdminPattern; csrfToken: string; canPublish: boolean; selected?: boolean; onSelectedChange?: (checked: boolean) => void }) {
  const [saveState, saveAction, savePending] = useActionState(savePattern, initial);
  const [publishState, publishAction, publishPending] = useActionState(publishPattern, initial);
  const { ready, risks } = getPublishReadiness(pattern);
  return <article className="admin-card">
    <header><div className="admin-card-heading">{onSelectedChange && <label className="candidate-select"><input type="checkbox" checked={selected} onChange={(event) => onSelectedChange(event.target.checked)} aria-label={`选择 ${pattern.name}`} /><span>选择</span></label>}<span className={`status-pill ${pattern.status}`}>{pattern.status}</span><span className="visibility-pill">{pattern.visibility}</span></div><div className="admin-card-links"><code>{pattern.id}</code>{onSelectedChange && <Link href={`/admin/patterns/${encodeURIComponent(pattern.id)}`}>审核详情</Link>}<Link href={`/admin/patterns/${encodeURIComponent(pattern.id)}/audit`}>查看审计</Link></div></header>
    <AdminPatternPreview patternId={pattern.id} name={pattern.name} />
    <div className={ready ? "readiness ready" : "readiness blocked"} role="status"><strong>{ready ? "可发布" : "存在发布风险"}</strong><span>{ready ? "名称、版权和审核项均通过" : risks.join(" · ")}</span></div>
    <form action={saveAction} className="admin-form"><input type="hidden" name="id" value={pattern.id}/><input type="hidden" name="csrfToken" value={csrfToken}/><label>名称<input name="name" defaultValue={pattern.name} required /></label><label>分类<input name="category" defaultValue={pattern.category}/></label><label className="wide">文化寓意<textarea name="meaning" defaultValue={pattern.meaning}/></label><label>版权状态<select name="rightsStatus" defaultValue={pattern.rights.status}><option value="unverified">unverified</option><option value="pending">pending</option><option value="verified">verified</option><option value="rejected">rejected</option></select></label><label>权利人<input name="rightsOwner" defaultValue={pattern.rights.owner || ""}/></label><label>授权依据<input name="rightsLicense" defaultValue={pattern.rights.license || ""}/></label><label>最近审核身份<input value={pattern.review.reviewedBy || "尚未审核"} disabled title="审核身份由登录会话自动记录"/></label><label className="wide">风险项（逗号或换行分隔）<textarea name="issues" defaultValue={pattern.review.issues.join("\n")}/></label><div className="form-actions"><button disabled={savePending} type="submit">{savePending ? "保存中…" : "保存审核资料"}</button><span className={saveState.ok ? "action-success" : "action-error"} aria-live="polite">{saveState.message}</span></div></form>
    <form action={publishAction} className="publish-form"><input type="hidden" name="id" value={pattern.id}/><input type="hidden" name="csrfToken" value={csrfToken}/><button disabled={!canPublish || publishPending || pattern.status === "published"} type="submit">{publishPending ? "发布中…" : pattern.status === "published" ? "已发布" : canPublish ? "审核通过并发布" : "需要发布员权限"}</button><span className={publishState.ok ? "action-success" : "action-error"} aria-live="polite">{publishState.message}</span></form>
  </article>;
}
