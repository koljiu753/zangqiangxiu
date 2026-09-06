import "server-only";
import type { AdminPattern, PatternAuditLog, PatternPage, ReviewTask, RightsEvidence } from "@/types/domain";

export type BatchReviewInput = { patternId: string; reviewedBy: string; reviewedAt: string; issues: string[] };
export type BatchOperationResponse = {
  succeeded: number;
  failed: number;
  items: Array<{
    patternId: string;
    status: "succeeded" | "failed";
    code?: string | null;
    message?: string | null;
    pattern?: AdminPattern | null;
  }>;
};

const baseUrl = (process.env.CATALOG_API_INTERNAL_BASE_URL || process.env.NEXT_PUBLIC_CATALOG_API_BASE_URL)?.replace(/\/$/, "");

async function adminRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const token = process.env.CATALOG_ADMIN_TOKEN;
  if (!baseUrl || !token) throw new Error("管理后台服务端环境变量尚未配置");
  const response = await fetch(`${baseUrl}${path}`, { ...init, cache: "no-store", headers: { "Content-Type": "application/json", "X-Admin-Token": token, ...init?.headers } });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string | { errors?: string[]; message?: string } } | null;
    const detail = typeof payload?.detail === "string" ? payload.detail : payload?.detail?.message || payload?.detail?.errors?.join("；");
    throw new Error(detail || `目录服务请求失败（${response.status}）`);
  }
  return response.json() as Promise<T>;
}

async function adminRawRequest(path: string, init?: RequestInit): Promise<Response> {
  const token = process.env.CATALOG_ADMIN_TOKEN;
  if (!baseUrl || !token) throw new Error("管理后台服务端环境变量尚未配置");
  const headers = new Headers(init?.headers);
  headers.set("X-Admin-Token", token);
  const response = await fetch(`${baseUrl}${path}`, { ...init, cache: "no-store", headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string | { code?: string; errors?: string[]; message?: string } } | null;
    const detail = typeof payload?.detail === "string" ? payload.detail : payload?.detail?.message || payload?.detail?.errors?.join("；");
    const messages: Record<string, string> = {
      unsupported_evidence_type: "仅支持 PDF、JPEG 或 PNG 凭证",
      evidence_signature_mismatch: "文件内容与声明的文件类型不一致",
      evidence_file_too_large: "凭证文件不能超过 10 MiB",
      empty_evidence_file: "凭证文件不能为空",
      evidence_limit_reached: "该纹样的凭证数量已达上限",
    };
    const code = typeof payload?.detail === "object" ? payload.detail.code : undefined;
    throw new Error((code && messages[code]) || detail || `目录服务请求失败（${response.status}）`);
  }
  return response;
}

export function getAdminPatterns(filters: { status?: string; visibility?: string; risk?: string; page?: number } = {}) {
  const query = new URLSearchParams({ pageSize: "20", page: String(filters.page || 1) });
  (["status", "visibility", "risk"] as const).forEach((key) => filters[key] && query.set(key, filters[key]));
  return adminRequest<PatternPage<AdminPattern>>(`/admin/patterns?${query}`);
}

export function batchReviewAdminPatterns(items: BatchReviewInput[]) {
  return adminRequest<BatchOperationResponse>("/admin/patterns/batch-review", {
    method: "POST", body: JSON.stringify({ items }),
  });
}

export function batchPublishAdminPatterns(patternIds: string[]) {
  return adminRequest<BatchOperationResponse>("/admin/patterns/batch-publish", {
    method: "POST", body: JSON.stringify({ patternIds }),
  });
}

export function updateAdminPattern(id: string, payload: object) {
  return adminRequest<AdminPattern>(`/admin/patterns/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function getAdminPattern(id: string) {
  return adminRequest<AdminPattern>(`/admin/patterns/${encodeURIComponent(id)}`);
}

export function publishAdminPattern(id: string) {
  return adminRequest<AdminPattern>(`/admin/patterns/${encodeURIComponent(id)}/publish`, { method: "POST" });
}

export function getPatternAuditLogs(id: string) {
  return adminRequest<PatternAuditLog[]>(`/admin/patterns/${encodeURIComponent(id)}/audit-logs`);
}

export type EvidenceUpdateInput = { sourceDescription?: string | null; originClaim?: string | null; rightsStatus?: string | null; rightsOwner?: string | null; rightsLicense?: string | null; evidence?: RightsEvidence[]; verifiedBy?: string | null; verifiedAt?: string | null; verificationNote?: string | null; reviewNote?: string | null };
export type ReviewWorkflowResponse = { succeeded: number; failed: number; items: Array<{ patternId: string; status: "succeeded" | "failed"; code?: string | null; message?: string | null; replayed: boolean; task?: ReviewTask | null }> };

export function updatePatternEvidence(id: string, payload: EvidenceUpdateInput) {
  return adminRequest<AdminPattern>(`/admin/patterns/${encodeURIComponent(id)}/evidence`, { method: "PATCH", body: JSON.stringify(payload) });
}

export async function uploadPatternEvidenceFile(id: string, file: File) {
  const body = new FormData();
  body.set("file", file, file.name);
  const response = await adminRawRequest(`/admin/patterns/${encodeURIComponent(id)}/evidence-files`, { method: "POST", body });
  return response.json() as Promise<AdminPattern>;
}

export function downloadPatternEvidenceFile(patternId: string, evidenceId: string) {
  return adminRawRequest(`/admin/patterns/${encodeURIComponent(patternId)}/evidence-files/${encodeURIComponent(evidenceId)}`);
}

export function getReviewTasks(filters: { assignee?: string; state?: ReviewTask["state"] } = {}) {
  const query = new URLSearchParams();
  if (filters.assignee) query.set("assignee", filters.assignee);
  if (filters.state) query.set("state", filters.state);
  return adminRequest<ReviewTask[]>(`/admin/reviews/tasks${query.size ? `?${query}` : ""}`);
}

export function assignReviewTask(patternId: string, assignee: string, requestId: string) {
  return adminRequest<ReviewWorkflowResponse>("/admin/reviews/batch-assign", { method: "POST", body: JSON.stringify({ items: [{ patternId, assignee, requestId }] }) });
}

export function decideReviewTask(patternId: string, decision: ReviewTask["state"], decidedBy: string, note: string | null, issues: string[], requestId: string) {
  return adminRequest<ReviewWorkflowResponse>("/admin/reviews/batch-decide", { method: "POST", body: JSON.stringify({ items: [{ patternId, decision, decidedBy, note, issues, requestId }] }) });
}
