import { NextResponse } from "next/server";

const internalBaseUrl = process.env.AI_API_INTERNAL_BASE_URL?.replace(/\/$/, "");
const publicBaseUrl = process.env.NEXT_PUBLIC_AI_API_BASE_URL?.replace(/\/$/, "");
const previewInternal = process.env.CATALOG_PREVIEW_INTERNAL === "true";

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const baseUrl = internalBaseUrl || publicBaseUrl;
  if (!baseUrl) return new NextResponse(null, { status: 404 });

  const scope = previewInternal ? "internal" : "public";
  const token = previewInternal ? process.env.AI_INTERNAL_TOKEN : undefined;
  if (previewInternal && !token) return new NextResponse(null, { status: 404 });
  const headers = token ? { "X-Service-Token": token } : undefined;

  try {
    const referenceResponse = await fetch(
      `${baseUrl}/references/by-pattern/${encodeURIComponent(id)}?scope=${scope}`,
      { cache: "no-store", headers },
    );
    if (!referenceResponse.ok) return new NextResponse(null, { status: 404 });
    const reference = await referenceResponse.json() as { asset_id?: string };
    if (!reference.asset_id) return new NextResponse(null, { status: 404 });

    const imageResponse = await fetch(
      `${baseUrl}/assets/${encodeURIComponent(reference.asset_id)}/content?thumbnail=960&scope=${scope}`,
      { cache: "no-store", headers },
    );
    const contentType = imageResponse.headers.get("content-type") || "";
    if (!imageResponse.ok || !contentType.startsWith("image/")) return new NextResponse(null, { status: 404 });

    return new NextResponse(imageResponse.body, {
      headers: {
        "Content-Type": contentType,
        "Cache-Control": previewInternal ? "private, no-store" : "public, max-age=3600, stale-while-revalidate=86400",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return new NextResponse(null, { status: 404 });
  }
}
