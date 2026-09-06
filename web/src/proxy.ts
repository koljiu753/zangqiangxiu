import { NextRequest, NextResponse } from "next/server";
import { ADMIN_SESSION_COOKIE, getAdminAuthConfiguration, hasRole, readBasicPrincipal, verifySessionToken } from "@/lib/admin-auth";

const securityHeaders = { "Content-Security-Policy": "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'", "Referrer-Policy": "strict-origin-when-cross-origin", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Permissions-Policy": "camera=(), microphone=(), geolocation=()" };

function secured(response: NextResponse) { Object.entries(securityHeaders).forEach(([name, value]) => response.headers.set(name, value)); return response; }

export async function proxy(request: NextRequest) {
  if (request.nextUrl.pathname === "/admin/login") return secured(NextResponse.next());
  const configuration = getAdminAuthConfiguration();
  if (!configuration && !readBasicPrincipal(request.headers.get("authorization"))) return secured(new NextResponse("Admin authentication is not securely configured", { status: 503 }));
  const session = await verifySessionToken(request.cookies.get(ADMIN_SESSION_COOKIE)?.value, configuration?.secret);
  const principal = session || readBasicPrincipal(request.headers.get("authorization"));
  if (principal && hasRole(principal, "reviewer")) return secured(NextResponse.next());
  const next = encodeURIComponent(request.nextUrl.pathname + request.nextUrl.search);
  return secured(NextResponse.redirect(new URL(`/admin/login?next=${next}`, request.url), 307));
}

export const config = { matcher: ["/admin/:path*"] };
