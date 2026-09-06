import { analyzeStudioImage } from "@/lib/studio-analysis";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const aiBaseUrl = process.env.AI_API_INTERNAL_BASE_URL?.replace(/\/$/, "");
  if (!aiBaseUrl) return Response.json({ error: "AI 服务尚未配置" }, { status: 503 });
  const form = await request.formData();
  const image = form.get("image");
  if (!(image instanceof File) || image.size === 0) {
    return Response.json({ error: "请选择有效图片" }, { status: 400 });
  }
  try {
    const result = await analyzeStudioImage({
      file: image,
      aiBaseUrl,
      catalogBaseUrl: process.env.CATALOG_API_INTERNAL_BASE_URL?.replace(/\/$/, ""),
      previewInternal: process.env.STUDIO_PREVIEW_INTERNAL === "true",
      adminToken: process.env.CATALOG_ADMIN_TOKEN,
    });
    return Response.json(result, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "分析服务暂不可用" }, { status: 502 });
  }
}
