import { afterEach, describe, expect, it } from "vitest";
import { checkStudioLimit, resetStudioLimitsForTests, studioClientKey } from "./studio-rate-limit";

afterEach(() => {
  resetStudioLimitsForTests();
  delete process.env.STUDIO_REQUESTS_PER_MINUTE;
  delete process.env.ADMIN_TRUST_PROXY;
});

describe("studio request limiting", () => {
  it("returns retry timing after the configured allowance", () => {
    process.env.STUDIO_REQUESTS_PER_MINUTE = "2";
    expect(checkStudioLimit("client", 1_000).allowed).toBe(true);
    expect(checkStudioLimit("client", 1_001).allowed).toBe(true);
    expect(checkStudioLimit("client", 1_002)).toEqual({ allowed: false, retryAfterSeconds: 60 });
  });

  it("only trusts forwarded addresses behind an explicitly trusted proxy", () => {
    const headers = new Headers({ "x-forwarded-for": "203.0.113.8, 10.0.0.1" });
    expect(studioClientKey(headers)).toBe("direct");
    process.env.ADMIN_TRUST_PROXY = "true";
    expect(studioClientKey(headers)).toBe("203.0.113.8");
  });
});
