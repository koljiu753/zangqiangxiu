import "server-only";
import { cookies, headers } from "next/headers";
import { ADMIN_SESSION_COOKIE, createCsrfToken, getAdminAuthConfiguration, hasRole, readBasicPrincipal, verifyCsrfToken, verifySessionToken, type AdminRole } from "@/lib/admin-auth";

export async function getAdminPrincipal() {
  const [cookieStore, headerStore] = await Promise.all([cookies(), headers()]);
  const configuration = getAdminAuthConfiguration();
  return await verifySessionToken(cookieStore.get(ADMIN_SESSION_COOKIE)?.value, configuration?.secret) || readBasicPrincipal(headerStore.get("authorization"));
}

export async function requireAdmin(required: AdminRole, csrfToken?: string) {
  const principal = await getAdminPrincipal();
  if (!principal || !hasRole(principal, required)) throw new Error("无权执行此操作");
  if (csrfToken !== undefined && !await verifyCsrfToken(csrfToken, principal, getAdminAuthConfiguration()?.secret)) throw new Error("安全校验失败，请刷新页面后重试");
  return principal;
}

export async function csrfFor(principal: NonNullable<Awaited<ReturnType<typeof getAdminPrincipal>>>) {
  const secret = getAdminAuthConfiguration()?.secret;
  if (!secret) throw new Error("认证密钥尚未配置");
  return createCsrfToken(principal, secret);
}
