import { analyzeStudioImage } from "@/lib/studio-analysis";
import { checkStudioLimit, studioClientKey } from "@/lib/studio-rate-limit";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const aiBaseUrl = process.env.AI_API_INTERNAL_BASE_URL?.replace(/\/$/, "");
  if (!aiBaseUrl) return Response.json({ error: "AI 服务尚未配置" }, { status: 503 });
  const maxBytes = Number(process.env.STUDIO_MAX_UPLOAD_BYTES || 10 * 1024 * 1024);
  const declaredLength = Number(request.headers.get("content-length") || 0);
  if (declaredLength > maxBytes + 64 * 1024) {
    return Response.json({ error: "上传图片超过大小限制" }, { status: 413 });
  }
  const rate = checkStudioLimit(studioClientKey(request.headers));
  if (!rate.allowed) {
    return Response.json({ error: "请求过于频繁，请稍后再试" }, {
      status: 429,
      headers: { "Retry-After": String(rate.retryAfterSeconds), "Cache-Control": "no-store" },
    });
  }
  const form = await request.formData();
  const image = form.get("image");
  if (!(image instanceof File) || image.size === 0) {
    return Response.json({ error: "请选择有效图片" }, { status: 400 });
  }
  if (image.size > maxBytes) return Response.json({ error: "上传图片超过大小限制" }, { status: 413 });
  try {
    const result = await analyzeStudioImage({
      file: image,
      aiBaseUrl,
      catalogBaseUrl: process.env.CATALOG_API_INTERNAL_BASE_URL?.replace(/\/$/, ""),
      previewInternal: process.env.STUDIO_PREVIEW_INTERNAL === "true",
      adminToken: process.env.CATALOG_ADMIN_TOKEN,
      aiInternalToken: process.env.AI_INTERNAL_TOKEN,
    });
    return Response.json(result, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "分析服务暂不可用" }, { status: 502 });
  }
}
