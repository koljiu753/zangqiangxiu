import { NextRequest, NextResponse } from "next/server";
import { ADMIN_SESSION_COOKIE, createSessionToken, getAdminAuthConfiguration, secureSessionCookie, trustedMutationOrigin } from "@/lib/admin-auth";
import { checkLoginLimit, clearLoginFailures, loginClientKey, recordLoginFailure } from "@/lib/login-rate-limit";

async function equal(left: string, right: string) {
  const [a, b] = await Promise.all([crypto.subtle.digest("SHA-256", new TextEncoder().encode(left)), crypto.subtle.digest("SHA-256", new TextEncoder().encode(right))]);
  let difference = 0;
  const first = new Uint8Array(a); const second = new Uint8Array(b);
  first.forEach((value, index) => { difference |= value ^ second[index]; });
  return difference === 0;
}

export async function POST(request: NextRequest) {
  if (!trustedMutationOrigin(request.url, request.headers.get("origin"), request.headers.get("sec-fetch-site"), process.env.PUBLIC_WEB_ORIGIN)) return new NextResponse("Cross-site login is not allowed", { status: 403 });
  const form = await request.formData();
  const username = String(form.get("username") || ""); const password = String(form.get("password") || "");
  const configuration = getAdminAuthConfiguration();
  if (!configuration) return new NextResponse("Admin authentication is not securely configured", { status: 503 });
  const key = loginClientKey(request.headers, username);
  const limit = checkLoginLimit(key);
  if (!limit.allowed) return new NextResponse("Too many login attempts", { status: 429, headers: { "Retry-After": String(limit.retryAfterSeconds), "Cache-Control": "no-store" } });
  if (!await equal(username, configuration.user) || !await equal(password, configuration.password)) {
    const failed = recordLoginFailure(key);
    if (!failed.allowed) return new NextResponse("Too many login attempts", { status: 429, headers: { "Retry-After": String(failed.retryAfterSeconds), "Cache-Control": "no-store" } });
    return new NextResponse(null, { status: 303, headers: { Location: "/admin/login?error=invalid", "Cache-Control": "no-store" } });
  }
  clearLoginFailures(key);
  const destination = String(form.get("next") || "/admin");
  const response = new NextResponse(null, { status: 303, headers: { Location: destination.startsWith("/admin") ? destination : "/admin" } });
  response.headers.set("Cache-Control", "no-store");
  response.cookies.set(ADMIN_SESSION_COOKIE, await createSessionToken(username, configuration.role, configuration.secret), { httpOnly: true, secure: secureSessionCookie(), sameSite: "strict", path: "/admin", maxAge: 8 * 60 * 60 });
  return response;
}
