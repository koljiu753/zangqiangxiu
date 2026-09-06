import "server-only";

import { demoPatterns } from "@/lib/demo-data";
import { ApiError } from "@/lib/api";
import type { Pattern, PatternPage, WithSource } from "@/types/domain";

const publicBaseUrl = process.env.NEXT_PUBLIC_CATALOG_API_BASE_URL?.replace(/\/$/, "");
const internalBaseUrl = process.env.CATALOG_API_INTERNAL_BASE_URL?.replace(/\/$/, "");
const allowDemo = process.env.NEXT_PUBLIC_ALLOW_DEMO_FALLBACK !== "false";
const previewInternal = process.env.CATALOG_PREVIEW_INTERNAL === "true";

export async function getPatterns(): Promise<WithSource<Pattern[]>> {
  try {
    const baseUrl = internalBaseUrl || publicBaseUrl;
    if (!baseUrl) throw new ApiError("未配置 Catalog API 地址");

    if (previewInternal) {
      const token = process.env.CATALOG_ADMIN_TOKEN;
      if (!token) throw new ApiError("内部预览缺少 Catalog 管理令牌");
      const response = await fetch(`${baseUrl}/admin/patterns?pageSize=100`, {
        cache: "no-store",
        headers: { "X-Admin-Token": token },
      });
      if (!response.ok) throw new ApiError(`Catalog 内部预览请求失败（${response.status}）`, response.status);
      const payload = await response.json() as PatternPage<Pattern>;
      return { data: withImageRoutes(payload.items), source: "preview" };
    }

    const response = await fetch(`${baseUrl}/patterns`, { cache: "no-store" });
    if (!response.ok) throw new ApiError(`Catalog 请求失败（${response.status}）`, response.status);
    const payload = await response.json() as Pattern[] | PatternPage<Pattern>;
    return { data: withImageRoutes(Array.isArray(payload) ? payload : payload.items), source: "api" };
  } catch (error) {
    if (!allowDemo) throw error;
    return { data: demoPatterns, source: "demo" };
  }
}

function withImageRoutes(patterns: Pattern[]): Pattern[] {
  return patterns.map((pattern) => ({
    ...pattern,
    imageUrl: pattern.imageUrl || `/patterns/${encodeURIComponent(pattern.id)}/image`,
  }));
}

export async function getPattern(id: string): Promise<WithSource<Pattern | null>> {
  try {
    const baseUrl = internalBaseUrl || publicBaseUrl;
    if (!baseUrl) throw new ApiError("未配置 Catalog API 地址");
    const path = previewInternal ? `/admin/patterns/${encodeURIComponent(id)}` : `/patterns/${encodeURIComponent(id)}`;
    const token = previewInternal ? process.env.CATALOG_ADMIN_TOKEN : undefined;
    if (previewInternal && !token) throw new ApiError("内部预览缺少 Catalog 管理令牌");
    const response = await fetch(`${baseUrl}${path}`, {
      cache: "no-store",
      headers: token ? { "X-Admin-Token": token } : undefined,
    });
    if (response.status === 404) return { data: null, source: previewInternal ? "preview" : "api" };
    if (!response.ok) throw new ApiError(`Catalog 纹样详情请求失败（${response.status}）`, response.status);
    const pattern = await response.json() as Pattern;
    return { data: withImageRoutes([pattern])[0], source: previewInternal ? "preview" : "api" };
  } catch (error) {
    if (!allowDemo) throw error;
    return { data: demoPatterns.find((pattern) => pattern.id === id) || null, source: "demo" };
  }
}
