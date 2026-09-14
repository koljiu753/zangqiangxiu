import { analyzeStudioImage } from "@/lib/studio-analysis";
import { checkStudioLimit, studioClientKey } from "@/lib/studio-rate-limit";
import { errorLog, REQUEST_ID_HEADER, requestIdFrom } from "@/lib/observability";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const requestId = requestIdFrom(request.headers);
  const responseHeaders = { "Cache-Control": "no-store", [REQUEST_ID_HEADER]: requestId };
  const aiBaseUrl = (
    process.env.AI_API_INTERNAL_BASE_URL || process.env.NEXT_PUBLIC_AI_API_BASE_URL
  )?.replace(/\/$/, "");
  if (!aiBaseUrl) return Response.json({ error: "AI 服务尚未配置" }, { status: 503, headers: responseHeaders });
  const maxBytes = Number(process.env.STUDIO_MAX_UPLOAD_BYTES || 10 * 1024 * 1024);
  const declaredLength = Number(request.headers.get("content-length") || 0);
  if (declaredLength > maxBytes + 64 * 1024) {
    return Response.json({ error: "上传图片超过大小限制" }, { status: 413, headers: responseHeaders });
  }
  const rate = checkStudioLimit(studioClientKey(request.headers));
  if (!rate.allowed) {
    return Response.json({ error: "请求过于频繁，请稍后再试" }, {
      status: 429,
      headers: { ...responseHeaders, "Retry-After": String(rate.retryAfterSeconds) },
    });
  }
  const form = await request.formData();
  const image = form.get("image");
  if (!(image instanceof File) || image.size === 0) {
    return Response.json({ error: "请选择有效图片" }, { status: 400, headers: responseHeaders });
  }
  if (image.size > maxBytes) return Response.json({ error: "上传图片超过大小限制" }, { status: 413, headers: responseHeaders });
  try {
    const result = await analyzeStudioImage({
      file: image,
      aiBaseUrl,
      catalogBaseUrl: process.env.CATALOG_API_INTERNAL_BASE_URL?.replace(/\/$/, ""),
      previewInternal: process.env.STUDIO_PREVIEW_INTERNAL === "true",
      adminToken: process.env.CATALOG_ADMIN_TOKEN,
      aiInternalToken: process.env.AI_INTERNAL_TOKEN,
      requestId,
    });
    return Response.json(result, { headers: responseHeaders });
  } catch (error) {
    errorLog({ event: "request.failed", request_id: requestId, method: "POST", path: "/api/studio/analysis", error_type: error instanceof Error ? error.name : "UnknownError" });
    return Response.json({ error: error instanceof Error ? error.message : "分析服务暂不可用" }, { status: 502, headers: responseHeaders });
  }
}
