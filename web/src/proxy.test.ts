// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "./proxy";

afterEach(() => vi.unstubAllEnvs());

describe("admin proxy redirects", () => {
  it("creates a valid absolute login redirect and preserves the requested path", async () => {
    vi.stubEnv("AUTH_SESSION_SECRET", "test-secret-that-is-long-enough-for-hmac");
    vi.stubEnv("ADMIN_UI_USER", "admin");
    vi.stubEnv("ADMIN_UI_PASSWORD", "configured-password");
    vi.stubEnv("ADMIN_UI_ROLE", "publisher");
    const response = await proxy(new NextRequest("http://localhost:3000/admin?risk=ready"));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "http://localhost:3000/admin/login?next=%2Fadmin%3Frisk%3Dready",
    );
    expect(response.headers.get("x-request-id")).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("preserves a valid request id on public requests", async () => {
    const response = await proxy(new NextRequest("http://localhost:3000/", {
      headers: { "X-Request-ID": "browser-flow-42" },
    }));
    expect(response.status).toBe(200);
    expect(response.headers.get("x-request-id")).toBe("browser-flow-42");
  });
});
