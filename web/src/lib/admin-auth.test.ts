// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { configuredRole, createCsrfToken, createSessionToken, getAdminAuthConfiguration, hasRole, secureSessionCookie, trustedMutationOrigin, verifyCsrfToken, verifySessionToken } from "./admin-auth";

const secret = "test-secret-that-is-long-enough-for-hmac";

afterEach(() => vi.unstubAllEnvs());

describe("admin authentication boundary", () => {
  it("round-trips a signed session", async () => {
    const token = await createSessionToken("operator", "reviewer", secret);
    expect(await verifySessionToken(token, secret)).toMatchObject({ subject: "operator", role: "reviewer" });
  });

  it("rejects tampered and expired sessions", async () => {
    const token = await createSessionToken("operator", "publisher", secret);
    expect(await verifySessionToken(`${token}x`, secret)).toBeNull();
    expect(await verifySessionToken(await createSessionToken("operator", "publisher", secret, -1), secret)).toBeNull();
  });

  it("enforces role ordering", () => {
    expect(hasRole({ subject: "a", role: "reviewer", expiresAt: 1 }, "publisher")).toBe(false);
    expect(hasRole({ subject: "a", role: "publisher", expiresAt: 1 }, "reviewer")).toBe(true);
  });

  it("binds CSRF tokens to the principal", async () => {
    const principal = { subject: "operator", role: "publisher" as const, expiresAt: 123 };
    const token = await createCsrfToken(principal, secret);
    expect(await verifyCsrfToken(token, principal, secret)).toBe(true);
    expect(await verifyCsrfToken(token, { ...principal, subject: "other" }, secret)).toBe(false);
  });

  it("allows insecure cookies only through an explicit local override", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("AUTH_COOKIE_SECURE", "true");
    expect(secureSessionCookie()).toBe(true);
    vi.stubEnv("AUTH_COOKIE_SECURE", "false");
    expect(secureSessionCookie()).toBe(false);
  });

  it("fails closed for invalid roles and weak production credentials", () => {
    expect(configuredRole("unexpected")).toBe("reviewer");
    vi.stubEnv("ADMIN_UI_USER", "operator");
    vi.stubEnv("ADMIN_UI_PASSWORD", "short");
    vi.stubEnv("AUTH_SESSION_SECRET", secret);
    vi.stubEnv("ADMIN_UI_ROLE", "publisher");
    expect(getAdminAuthConfiguration()).toBeNull();
    vi.stubEnv("ADMIN_UI_PASSWORD", "a-long-local-password");
    expect(getAdminAuthConfiguration()).toMatchObject({ user: "operator", role: "publisher" });
  });

  it("rejects cross-site mutations", () => {
    expect(trustedMutationOrigin("https://example.test/api", "https://evil.test", "cross-site")).toBe(false);
    expect(trustedMutationOrigin("https://example.test/api", "https://example.test", "same-origin")).toBe(true);
    expect(trustedMutationOrigin("http://web:3000/api", "https://public.example", "same-origin", "https://public.example")).toBe(true);
    expect(trustedMutationOrigin("http://web:3000/api", "https://evil.test", "same-origin", "https://public.example")).toBe(false);
  });
});
