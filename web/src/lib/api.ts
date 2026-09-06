import type { AnalysisResult } from "@/types/domain";

export class ApiError extends Error {
  constructor(message: string, readonly status?: number) { super(message); }
}

export async function submitAnalysis(file: File): Promise<AnalysisResult> {
  const form = new FormData();
  form.append("image", file);
  const response = await fetch("/api/studio/analysis", { method: "POST", body: form });
  const payload = await response.json().catch(() => undefined) as AnalysisResult | { error?: string } | undefined;
  if (!response.ok) throw new ApiError(payload && "error" in payload ? payload.error || "分析服务暂不可用" : "分析服务暂不可用", response.status);
  return payload as AnalysisResult;
}
