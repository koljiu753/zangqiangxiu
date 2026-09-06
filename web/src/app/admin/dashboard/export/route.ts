import { getAdminPatterns } from "@/lib/admin-api";
import { requireAdmin } from "@/lib/admin-auth-server";
import { patternsCsv } from "@/lib/governance-dashboard";

export async function GET() {
  try {
    await requireAdmin("reviewer");
    const first = await getAdminPatterns({ page: 1 });
    const remaining = await Promise.all(Array.from({ length: Math.max(first.pages - 1, 0) }, (_, index) => getAdminPatterns({ page: index + 2 })));
    const csv = patternsCsv([first, ...remaining].flatMap((page) => page.items));
    return new Response(csv, { headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="zhixiu-governance-${new Date().toISOString().slice(0, 10)}.csv"`,
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff",
    } });
  } catch (error) {
    const message = error instanceof Error ? error.message : "导出失败";
    const status = message.includes("无权") ? 403 : 502;
    return Response.json({ error: message }, { status, headers: { "Cache-Control": "no-store" } });
  }
}
