// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { checkLoginLimit, clearLoginFailures, loginClientKey, recordLoginFailure, resetLoginLimitsForTests } from "./login-rate-limit";

afterEach(() => { resetLoginLimitsForTests(); vi.unstubAllEnvs(); });

describe("login rate limiter", () => {
  it("blocks the fifth failed attempt and can clear a successful identity", () => {
    for (let count = 0; count < 4; count += 1) expect(recordLoginFailure("direct:operator", 1_000).allowed).toBe(true);
    expect(recordLoginFailure("direct:operator", 1_000).allowed).toBe(false);
    expect(checkLoginLimit("direct:operator", 1_001).retryAfterSeconds).toBeGreaterThan(0);
    clearLoginFailures("direct:operator");
    expect(checkLoginLimit("direct:operator", 1_001).allowed).toBe(true);
  });

  it("trusts forwarded addresses only with the explicit proxy setting", () => {
    const headers = new Headers({ "x-forwarded-for": "203.0.113.8, 10.0.0.1" });
    expect(loginClientKey(headers, "Admin")).toBe("direct:admin");
    vi.stubEnv("ADMIN_TRUST_PROXY", "true");
    expect(loginClientKey(headers, "Admin")).toBe("203.0.113.8:admin");
  });
});
