import type { AnalysisResult, Pattern, SimilarPattern } from "@/types/domain";

type Fetch = typeof fetch;

type Job = { id: string; status: string; result_id?: string; error_message?: string };
type UploadedAsset = { id: string; capability_token: string };
type RawResult = {
  palette?: Array<{ hex: string }>;
  classification?: { status: string; data?: { label?: string; confidence?: number } };
  similar?: Array<{ asset_id: string; pattern_id?: string; label?: string; score: number }>;
  similarity_algorithm_version?: string;
  warnings?: string[];
};

async function json<T>(fetcher: Fetch, url: string, init?: RequestInit): Promise<T> {
  const response = await fetcher(url, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => undefined) as { detail?: { message?: string } } | undefined;
    throw new Error(payload?.detail?.message || `上游服务请求失败（${response.status}）`);
  }
  return response.json() as Promise<T>;
}

async function patternDetails(
  fetcher: Fetch,
  match: SimilarPattern,
  catalogBaseUrl: string | undefined,
  previewInternal: boolean,
  adminToken: string | undefined,
): Promise<SimilarPattern> {
  if (!match.patternId || !catalogBaseUrl || (previewInternal && !adminToken)) return match;
  const path = previewInternal ? `/admin/patterns/${match.patternId}` : `/patterns/${match.patternId}`;
  try {
    const pattern = await json<Pattern>(fetcher, `${catalogBaseUrl}${path}`, previewInternal
      ? { headers: { "X-Admin-Token": adminToken! } }
      : undefined);
    return {
      ...match,
      name: pattern.name,
      category: pattern.category,
      meaning: pattern.meaning,
      imageUrl: pattern.imageUrl || `/patterns/${encodeURIComponent(match.patternId)}/image`,
    };
  } catch {
    return match;
  }
}

export async function analyzeStudioImage(options: {
  file: File;
  aiBaseUrl: string;
  catalogBaseUrl?: string;
  previewInternal: boolean;
  adminToken?: string;
  aiInternalToken?: string;
  fetcher?: Fetch;
  pollDelayMs?: number;
  maxPolls?: number;
  requestId?: string;
}): Promise<AnalysisResult> {
  const fetcher = options.fetcher ?? fetch;
  const form = new FormData();
  form.append("image", options.file);
  const requestHeaders = options.requestId ? { "X-Request-ID": options.requestId } : undefined;
  const asset = await json<UploadedAsset>(fetcher, `${options.aiBaseUrl}/assets`, { method: "POST", body: form, headers: requestHeaders });
  if (!asset.capability_token) throw new Error("分析服务未返回资源访问凭证");
  const capabilityHeaders = { "X-Asset-Capability": asset.capability_token, ...(options.requestId ? { "X-Request-ID": options.requestId } : {}) };
  const analysisHeaders: Record<string, string> = { "Content-Type": "application/json", ...capabilityHeaders };
  if (options.previewInternal && options.aiInternalToken) analysisHeaders["X-Service-Token"] = options.aiInternalToken;
  const accessHeaders = Object.fromEntries(Object.entries(analysisHeaders).filter(([key]) => key !== "Content-Type"));

  try {
    const job = await json<Job>(fetcher, `${options.aiBaseUrl}/analyses`, {
      method: "POST",
      headers: analysisHeaders,
      body: JSON.stringify({
        asset_id: asset.id,
        tasks: ["palette", "classification", "similar"],
        top_k: 5,
        scope: options.previewInternal ? "internal" : "public",
      }),
    });

    for (let attempt = 0; attempt < (options.maxPolls ?? 40); attempt += 1) {
      const current = await json<Job>(fetcher, `${options.aiBaseUrl}/jobs/${job.id}`, { headers: accessHeaders });
      if (current.status === "failed") throw new Error(current.error_message || "分析任务失败");
      if (current.status === "succeeded" && current.result_id) {
        const raw = await json<RawResult>(fetcher, `${options.aiBaseUrl}/analyses/${current.result_id}`, { headers: accessHeaders });
        const matches = (raw.similar ?? []).map((item) => ({
          assetId: item.asset_id,
          patternId: item.pattern_id,
          label: item.label,
          score: item.score,
        }));
        const similar = await Promise.all(matches.map((match) => patternDetails(
          fetcher, match, options.catalogBaseUrl, options.previewInternal, options.adminToken,
        )));
        return {
          jobId: current.id,
          status: "succeeded",
          label: raw.classification?.status === "available" ? raw.classification.data?.label : undefined,
          confidence: raw.classification?.status === "available" ? raw.classification.data?.confidence : undefined,
          palette: raw.palette?.map((color) => color.hex) ?? [],
          algorithmVersion: raw.similarity_algorithm_version,
          similar,
          warnings: raw.warnings ?? [],
        };
      }
      await new Promise((resolve) => setTimeout(resolve, options.pollDelayMs ?? 250));
    }
    throw new Error("分析任务等待超时，请稍后重试");
  } finally {
    await fetcher(`${options.aiBaseUrl}/assets/${asset.id}`, {
      method: "DELETE",
      headers: capabilityHeaders,
    }).catch(() => undefined);
  }
}
