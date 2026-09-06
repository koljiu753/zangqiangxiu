"use server";

import { revalidatePath } from "next/cache";
import { assignReviewTask, batchPublishAdminPatterns, batchReviewAdminPatterns, bulkAssignReviewTasks, decideReviewTask, getAdminPattern, getReviewTasks, publishAdminPattern, updateAdminPattern, updatePatternEvidence, uploadPatternEvidenceFile } from "@/lib/admin-api";
import { requireAdmin } from "@/lib/admin-auth-server";
import { selectedPatternIds, splitIssues, summarizeBatch, type BatchActionState } from "@/lib/admin-bulk";
import type { ReviewAssignmentState } from "@/components/review-queue-board";

export type AdminActionState = { ok: boolean; message: string };

export async function savePattern(_: AdminActionState, formData: FormData): Promise<AdminActionState> {
  let principal;
  try { principal = await requireAdmin("reviewer", String(formData.get("csrfToken") || "")); }
  catch (error) { return { ok: false, message: error instanceof Error ? error.message : "无权执行此操作" }; }
  const id = String(formData.get("id") || "");
  if (!id) return { ok: false, message: "缺少纹样 ID" };
  const issues = String(formData.get("issues") || "").split(/[|,，\n]/).map((item) => item.trim()).filter(Boolean);
  try {
    const current = await getAdminPattern(id);
    await updateAdminPattern(id, {
      name: String(formData.get("name") || "").trim(),
      category: String(formData.get("category") || "").trim(),
      meaning: String(formData.get("meaning") || "").trim(),
      rights: { ...current.rights, status: String(formData.get("rightsStatus") || "unverified"), owner: String(formData.get("rightsOwner") || "").trim() || null, license: String(formData.get("rightsLicense") || "").trim() || null },
      review: { ...current.review, issues, reviewedBy: principal.subject, reviewedAt: issues.length ? null : new Date().toISOString() },
    }, principal.subject);
    revalidatePath("/admin");
    return { ok: true, message: "候选资料已保存" };
  } catch (error) { return { ok: false, message: error instanceof Error ? error.message : "保存失败" }; }
}

export async function bulkUpdatePatterns(_: BatchActionState, formData: FormData): Promise<BatchActionState> {
  let principal;
  try { principal = await requireAdmin("reviewer", String(formData.get("csrfToken") || "")); }
  catch (error) { return { ok: false, message: error instanceof Error ? error.message : "无权执行此操作", results: [] }; }
  const ids = selectedPatternIds(formData);
  if (!ids.length) return { ok: false, message: "请至少选择一条候选记录", results: [] };
  if (ids.length > 50) return { ok: false, message: "单次最多分派 50 条候选记录", results: [] };

  const reviewedBy = principal.subject;
  const issueMode = String(formData.get("bulkIssueMode") || "replace");
  if (!["replace", "clear"].includes(issueMode)) return { ok: false, message: "风险项操作无效", results: [] };
  const issues = splitIssues(formData.get("bulkIssues"));
  if (issueMode === "replace" && !issues.length) return { ok: false, message: "覆盖风险项时请至少填写一项", results: [] };
  try {
    const reviewedAt = new Date().toISOString();
    const response = await batchReviewAdminPatterns(ids.map((patternId) => ({
      patternId, reviewedBy, reviewedAt, issues: issueMode === "clear" ? [] : issues,
    })), principal.subject);
    const results = response.items.map((item) => ({
      id: item.patternId,
      ok: item.status === "succeeded",
      message: item.status === "succeeded" ? "已审核" : item.message || item.code || "审核失败",
    }));
    revalidatePath("/admin");
    return summarizeBatch(results, "批量审核");
  } catch (error) {
    return { ok: false, message: error instanceof Error ? error.message : "批量审核失败", results: [] };
  }
}

export async function bulkPublishPatterns(_: BatchActionState, formData: FormData): Promise<BatchActionState> {
  let principal;
  try { principal = await requireAdmin("publisher", String(formData.get("csrfToken") || "")); }
  catch (error) { return { ok: false, message: error instanceof Error ? error.message : "无权执行此操作", results: [] }; }
  const ids = selectedPatternIds(formData);
  if (!ids.length) return { ok: false, message: "请至少选择一条候选记录", results: [] };
  try {
    const response = await batchPublishAdminPatterns(ids, principal.subject);
    const results = response.items.map((item) => ({
      id: item.patternId,
      ok: item.status === "succeeded",
      message: item.status === "succeeded" ? "已发布" : item.message || item.code || "发布失败",
    }));
    revalidatePath("/admin"); revalidatePath("/patterns"); revalidatePath("/");
    return summarizeBatch(results, "批量发布");
  } catch (error) {
    return { ok: false, message: error instanceof Error ? error.message : "批量发布失败", results: [] };
  }
}

export async function publishPattern(_: AdminActionState, formData: FormData): Promise<AdminActionState> {
  let principal;
  try { principal = await requireAdmin("publisher", String(formData.get("csrfToken") || "")); }
  catch (error) { return { ok: false, message: error instanceof Error ? error.message : "无权执行此操作" }; }
  const id = String(formData.get("id") || "");
  try {
    await publishAdminPattern(id, principal.subject);
    revalidatePath("/admin"); revalidatePath("/patterns"); revalidatePath("/");
    return { ok: true, message: "已通过安全校验并公开发布" };
  } catch (error) { return { ok: false, message: error instanceof Error ? error.message : "发布失败" }; }
}

function field(formData: FormData, name: string) { return String(formData.get(name) || "").trim(); }
function refreshReview(id: string) { revalidatePath("/admin/review"); revalidatePath(`/admin/patterns/${id}`); revalidatePath("/admin/dashboard"); }

export async function saveEvidence(_: AdminActionState, formData: FormData): Promise<AdminActionState> {
  let principal;
  try { principal = await requireAdmin("reviewer", field(formData, "csrfToken")); }
  catch (error) { return { ok: false, message: error instanceof Error ? error.message : "无权执行此操作" }; }
  const id = field(formData, "id");
  if (!id) return { ok: false, message: "缺少纹样 ID" };
  const candidate = formData.get("evidenceFile");
  const file = candidate instanceof File && candidate.size > 0 ? candidate : null;
  if (file && file.size > 10 * 1024 * 1024) return { ok: false, message: "凭证文件不能超过 10 MiB" };
  if (file && !["application/pdf", "image/jpeg", "image/png"].includes(file.type.toLowerCase())) return { ok: false, message: "仅支持 PDF、JPEG 或 PNG 凭证" };
  const rightsStatus = field(formData, "rightsStatus") || null;
  try {
    await updatePatternEvidence(id, { sourceDescription: field(formData, "sourceDescription") || null, originClaim: field(formData, "originClaim") || null, rightsStatus, rightsOwner: field(formData, "rightsOwner") || null, rightsLicense: field(formData, "rightsLicense") || null, verifiedBy: rightsStatus === "verified" ? principal.subject : null, verifiedAt: rightsStatus === "verified" ? new Date().toISOString() : null, verificationNote: field(formData, "verificationNote") || null, reviewNote: field(formData, "reviewNote") || null }, principal.subject);
  } catch (error) { return { ok: false, message: error instanceof Error ? error.message : "核验资料保存失败" }; }
  if (file) {
    try { await uploadPatternEvidenceFile(id, file, principal.subject); }
    catch (error) {
      refreshReview(id);
      const message = error instanceof Error ? error.message : "凭证上传失败";
      return { ok: false, message: `核验资料已保存，但凭证上传失败：${message}` };
    }
  }
  refreshReview(id); return { ok: true, message: file ? "核验资料与凭证文件已安全保存" : "核验资料已保存" };
}

export async function assignReview(_: AdminActionState, formData: FormData): Promise<AdminActionState> {
  let principal;
  try { principal = await requireAdmin("reviewer", field(formData, "csrfToken")); }
  catch (error) { return { ok: false, message: error instanceof Error ? error.message : "无权执行此操作" }; }
  const id = field(formData, "id"), assignee = field(formData, "assignee");
  if (!id || !assignee) return { ok: false, message: "纹样 ID 与审核人均不能为空" };
  try { const response = await assignReviewTask(id, assignee, `assign_${crypto.randomUUID()}`, principal.subject); const item = response.items[0]; if (!item || item.status === "failed") throw new Error(item?.message || "分配失败"); refreshReview(id); return { ok: true, message: `已分配给 ${assignee}` }; }
  catch (error) { return { ok: false, message: error instanceof Error ? error.message : "分配失败" }; }
}

export async function bulkAssignReviews(_: ReviewAssignmentState, formData: FormData): Promise<ReviewAssignmentState> {
  let principal;
  try { principal = await requireAdmin("reviewer", field(formData, "csrfToken")); }
  catch (error) { return { ok: false, message: error instanceof Error ? error.message : "无权执行此操作", results: [] }; }
  const ids = selectedPatternIds(formData);
  if (!ids.length) return { ok: false, message: "请至少选择一条候选记录", results: [] };
  const assignee = field(formData, "assignee");
  if (!assignee) return { ok: false, message: "审核人不能为空", results: [] };
  if (assignee.length > 120) return { ok: false, message: "审核人标识不能超过 120 个字符", results: [] };
  try {
    const response = await bulkAssignReviewTasks({ patternIds: ids, assignee, requestId: `bulk_assign_${crypto.randomUUID()}` }, principal.subject);
    const results = response.items.map((item) => ({ id: item.patternId, ok: item.status === "succeeded", message: item.status === "succeeded" ? `已分配给 ${assignee}` : item.message || item.code || "分配失败" }));
    revalidatePath("/admin/review");
    revalidatePath("/admin/dashboard");
    return summarizeBatch(results, "批量分派");
  } catch (error) { return { ok: false, message: error instanceof Error ? error.message : "批量分派失败", results: [] }; }
}

export async function decideReview(_: AdminActionState, formData: FormData): Promise<AdminActionState> {
  let principal;
  try { principal = await requireAdmin("reviewer", field(formData, "csrfToken")); }
  catch (error) { return { ok: false, message: error instanceof Error ? error.message : "无权执行此操作" }; }
  const id = field(formData, "id");
  const decision = field(formData, "decision") as "approved" | "rejected" | "needs_more";
  if (!id || !["approved", "rejected", "needs_more"].includes(decision)) return { ok: false, message: "审核决定无效" };
  const tasks = await getReviewTasks();
  const task = tasks.find((item) => item.patternId === id);
  if (!task) return { ok: false, message: "请先分配审核任务" };
  if (task.assignee !== principal.subject) return { ok: false, message: `该任务已分配给 ${task.assignee}，当前身份不能代为审核` };
  const issues = splitIssues(formData.get("decisionIssues"));
  if (decision === "approved" && issues.length) return { ok: false, message: "通过审核时不能保留风险项" };
  if (decision !== "approved" && !issues.length) return { ok: false, message: "退回或拒绝时必须填写风险项" };
  try { const response = await decideReviewTask(id, decision, principal.subject, field(formData, "decisionNote") || null, issues, `decide_${crypto.randomUUID()}`, principal.subject); const item = response.items[0]; if (!item || item.status === "failed") throw new Error(item?.message || "提交决定失败"); refreshReview(id); return { ok: true, message: "审核决定已记录" }; }
  catch (error) { return { ok: false, message: error instanceof Error ? error.message : "提交决定失败" }; }
}
