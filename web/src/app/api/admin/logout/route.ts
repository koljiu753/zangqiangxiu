import { NextResponse } from "next/server";
import { ADMIN_SESSION_COOKIE, secureSessionCookie, trustedMutationOrigin } from "@/lib/admin-auth";

export async function POST(request: Request) {
  if (!trustedMutationOrigin(request.url, request.headers.get("origin"), request.headers.get("sec-fetch-site"), process.env.PUBLIC_WEB_ORIGIN)) return new NextResponse("Cross-site logout is not allowed", { status: 403 });
  const response = new NextResponse(null, { status: 303, headers: { Location: "/admin/login" } });
  response.headers.set("Cache-Control", "no-store");
  response.cookies.set(ADMIN_SESSION_COOKIE, "", { httpOnly: true, secure: secureSessionCookie(), sameSite: "strict", expires: new Date(0), path: "/admin" });
  return response;
}
