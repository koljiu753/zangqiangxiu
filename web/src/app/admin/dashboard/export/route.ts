import { exportAdminPatternsCsv, type PatternExportFilters } from "@/lib/admin-api";
import { requireAdmin } from "@/lib/admin-auth-server";

const allowed = {
  status: new Set(["draft", "published", "archived"]),
  visibility: new Set(["internal_only", "public"]),
  risk: new Set(["any", "has_issues", "rights_unverified", "ready"]),
};

export async function GET(request: Request) {
  try {
    await requireAdmin("reviewer");
    const source = new URL(request.url).searchParams;
    const filters: PatternExportFilters = {};
    for (const key of ["status", "visibility", "risk"] as const) {
      const value = source.get(key);
      if (value && allowed[key].has(value)) filters[key] = value;
    }
    const requestedLimit = Number(source.get("limit"));
    if (Number.isInteger(requestedLimit) && requestedLimit >= 1 && requestedLimit <= 5000) filters.limit = requestedLimit;
    const upstream = await exportAdminPatternsCsv(filters);
    const headers = new Headers();
    headers.set("Content-Type", upstream.headers.get("content-type") || "text/csv; charset=utf-8");
    headers.set("Content-Disposition", upstream.headers.get("content-disposition") || 'attachment; filename="zhixiu-patterns.csv"');
    const exportedRows = upstream.headers.get("x-exported-rows");
    if (exportedRows) headers.set("X-Exported-Rows", exportedRows);
    headers.set("Cache-Control", "private, no-store");
    headers.set("X-Content-Type-Options", "nosniff");
    return new Response(upstream.body, { headers });
  } catch (error) {
    const message = error instanceof Error ? error.message : "导出失败";
    const status = message.includes("无权") ? 403 : 502;
    return Response.json({ error: message }, { status, headers: { "Cache-Control": "no-store" } });
  }
}
