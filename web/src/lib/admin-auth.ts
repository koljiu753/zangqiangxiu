export const ADMIN_SESSION_COOKIE = "zhixiu_admin_session";
export type AdminRole = "reviewer" | "publisher";
export type AdminPrincipal = { subject: string; role: AdminRole; expiresAt: number };
export type AdminAuthConfiguration = { user: string; password: string; secret: string; role: AdminRole };

const encoder = new TextEncoder();
const roleRank: Record<AdminRole, number> = { reviewer: 1, publisher: 2 };

function base64url(bytes: Uint8Array) {
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function decodeBase64url(value: string) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  return Uint8Array.from(atob(normalized), (character) => character.charCodeAt(0));
}

async function signature(value: string, secret: string) {
  const key = await crypto.subtle.importKey("raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return base64url(new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(value))));
}

function constantTimeEqual(left: string, right: string) {
  const length = Math.max(left.length, right.length);
  let difference = left.length ^ right.length;
  for (let index = 0; index < length; index += 1) difference |= (left.charCodeAt(index) || 0) ^ (right.charCodeAt(index) || 0);
  return difference === 0;
}

export function configuredRole(value = process.env.ADMIN_UI_ROLE): AdminRole { return value === "publisher" ? "publisher" : "reviewer"; }
export function hasRole(principal: AdminPrincipal, required: AdminRole) { return roleRank[principal.role] >= roleRank[required]; }
export function basicAuthAllowed() { return process.env.ADMIN_ALLOW_BASIC_AUTH === "true" || (process.env.NODE_ENV !== "production" && process.env.ADMIN_ALLOW_BASIC_AUTH !== "false"); }
export function secureSessionCookie() { return process.env.NODE_ENV === "production" && process.env.AUTH_COOKIE_SECURE !== "false"; }

export function getAdminAuthConfiguration(): AdminAuthConfiguration | null {
  const user = process.env.ADMIN_UI_USER?.trim();
  const password = process.env.ADMIN_UI_PASSWORD || "";
  const secret = process.env.AUTH_SESSION_SECRET || "";
  const rawRole = process.env.ADMIN_UI_ROLE || "reviewer";
  const placeholders = /^(change-me|dev-only|password|admin123)/i;
  if (!user || user.length > 128 || password.length < 12 || secret.length < 32 || placeholders.test(password) || placeholders.test(secret) || !["reviewer", "publisher"].includes(rawRole)) return null;
  return { user, password, secret, role: configuredRole(rawRole) };
}

export function trustedMutationOrigin(requestUrl: string, origin: string | null, fetchSite: string | null, publicOrigin?: string) {
  if (fetchSite === "cross-site") return false;
  if (!origin) return true;
  try {
    const supplied = new URL(origin).origin;
    const allowed = [new URL(requestUrl).origin];
    if (publicOrigin) allowed.push(new URL(publicOrigin).origin);
    return allowed.includes(supplied);
  }
  catch { return false; }
}

export async function createSessionToken(subject: string, role: AdminRole, secret: string, lifetimeSeconds = 8 * 60 * 60) {
  const payload = base64url(encoder.encode(JSON.stringify({ sub: subject, role, exp: Math.floor(Date.now() / 1000) + lifetimeSeconds })));
  return `${payload}.${await signature(payload, secret)}`;
}

export async function verifySessionToken(token: string | undefined, secret: string | undefined): Promise<AdminPrincipal | null> {
  if (!token || !secret) return null;
  const [payload, providedSignature, extra] = token.split(".");
  if (!payload || !providedSignature || extra || !constantTimeEqual(await signature(payload, secret), providedSignature)) return null;
  try {
    const parsed = JSON.parse(new TextDecoder().decode(decodeBase64url(payload))) as { sub?: unknown; role?: unknown; exp?: unknown };
    if (typeof parsed.sub !== "string" || (parsed.role !== "reviewer" && parsed.role !== "publisher") || typeof parsed.exp !== "number" || parsed.exp <= Date.now() / 1000) return null;
    return { subject: parsed.sub, role: parsed.role, expiresAt: parsed.exp };
  } catch { return null; }
}

export async function createCsrfToken(principal: AdminPrincipal, secret: string) { return signature(`csrf:${principal.subject}:${principal.role}:${principal.expiresAt}`, secret); }
export async function verifyCsrfToken(token: string, principal: AdminPrincipal, secret: string | undefined) { return Boolean(secret) && constantTimeEqual(token, await createCsrfToken(principal, secret!)); }

export function readBasicPrincipal(authorization: string | null): AdminPrincipal | null {
  if (!basicAuthAllowed() || !authorization?.startsWith("Basic ")) return null;
  try {
    const [user, password] = atob(authorization.slice(6)).split(":", 2);
    if (!user || user !== process.env.ADMIN_UI_USER || password !== process.env.ADMIN_UI_PASSWORD) return null;
    return { subject: user, role: configuredRole(), expiresAt: 0 };
  } catch { return null; }
}
