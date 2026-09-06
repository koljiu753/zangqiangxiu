import { NextRequest, NextResponse } from "next/server";
import { ADMIN_SESSION_COOKIE, getAdminAuthConfiguration, hasRole, readBasicPrincipal, verifySessionToken } from "@/lib/admin-auth";
import { accessLog, REQUEST_ID_HEADER, requestIdFrom } from "@/lib/observability";

const securityHeaders = { "Content-Security-Policy": "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'", "Referrer-Policy": "strict-origin-when-cross-origin", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Permissions-Policy": "camera=(), microphone=(), geolocation=()" };

function secured(response: NextResponse, requestId: string) { Object.entries(securityHeaders).forEach(([name, value]) => response.headers.set(name, value)); response.headers.set(REQUEST_ID_HEADER, requestId); return response; }

export async function proxy(request: NextRequest) {
  const started = Date.now();
  const requestId = requestIdFrom(request.headers);
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set(REQUEST_ID_HEADER, requestId);
  let response: NextResponse;
  if (!request.nextUrl.pathname.startsWith("/admin") || request.nextUrl.pathname === "/admin/login") {
    response = NextResponse.next({ request: { headers: requestHeaders } });
  } else {
  const configuration = getAdminAuthConfiguration();
    if (!configuration && !readBasicPrincipal(request.headers.get("authorization"))) response = new NextResponse("Admin authentication is not securely configured", { status: 503 });
    else {
      const session = await verifySessionToken(request.cookies.get(ADMIN_SESSION_COOKIE)?.value, configuration?.secret);
      const principal = session || readBasicPrincipal(request.headers.get("authorization"));
      response = principal && hasRole(principal, "reviewer")
        ? NextResponse.next({ request: { headers: requestHeaders } })
        : NextResponse.redirect(new URL(`/admin/login?next=${encodeURIComponent(request.nextUrl.pathname + request.nextUrl.search)}`, request.url), 307);
    }
  }
  accessLog({ event: "request.completed", request_id: requestId, method: request.method, path: request.nextUrl.pathname, status: response.status, duration_ms: Date.now() - started });
  return secured(response, requestId);
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
