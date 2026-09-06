import { downloadPatternEvidenceFile } from "@/lib/admin-api";
import { requireAdmin } from "@/lib/admin-auth-server";

export const dynamic = "force-dynamic";

type Context = { params: Promise<{ id: string; evidenceId: string }> };

export async function GET(_: Request, { params }: Context) {
  try {
    await requireAdmin("reviewer");
    const { id, evidenceId } = await params;
    const upstream = await downloadPatternEvidenceFile(id, evidenceId);
    const headers = new Headers();
    for (const name of ["content-type", "content-length", "content-disposition", "x-checksum-sha256"]) {
      const value = upstream.headers.get(name);
      if (value) headers.set(name, value);
    }
    headers.set("Cache-Control", "private, no-store");
    headers.set("X-Content-Type-Options", "nosniff");
    return new Response(upstream.body, { status: 200, headers });
  } catch (error) {
    const message = error instanceof Error ? error.message : "凭证下载失败";
    const status = message.includes("无权") ? 403 : message.includes("not found") || message.includes("未找到") ? 404 : 502;
    return Response.json({ error: message }, { status, headers: { "Cache-Control": "no-store" } });
  }
}
