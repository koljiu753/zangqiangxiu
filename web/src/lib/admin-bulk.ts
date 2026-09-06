export type BatchItemResult = { id: string; ok: boolean; message: string };
export type BatchActionState = { ok: boolean; message: string; results: BatchItemResult[] };

const ID_PATTERN = /^[a-zA-Z0-9][a-zA-Z0-9_-]{2,99}$/;
export const emptyBatchState: BatchActionState = { ok: false, message: "", results: [] };

export type AdminListFilters = { status?: string; visibility?: string; risk?: string };

export function adminPageHref(filters: AdminListFilters, page: number) {
  const query = new URLSearchParams();
  (["status", "visibility", "risk"] as const).forEach((key) => filters[key] && query.set(key, filters[key]));
  query.set("page", String(Math.max(1, Math.floor(page))));
  return `/admin?${query}`;
}

export function selectedPatternIds(formData: FormData) {
  return [...new Set(formData.getAll("selectedIds").map(String).map((id) => id.trim()).filter((id) => ID_PATTERN.test(id)))].slice(0, 100);
}

export function splitIssues(value: FormDataEntryValue | null) {
  return String(value || "").split(/[|,，\n]/).map((item) => item.trim()).filter(Boolean);
}

export function summarizeBatch(results: BatchItemResult[], verb: string): BatchActionState {
  const succeeded = results.filter((item) => item.ok).length;
  const failed = results.length - succeeded;
  return { ok: failed === 0 && succeeded > 0, message: `${verb}：${succeeded} 条成功，${failed} 条失败`, results };
}
