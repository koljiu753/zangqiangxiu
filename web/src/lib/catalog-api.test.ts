// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("catalog demo fallback", () => {
  it("fails closed when the API and explicit demo opt-in are absent", async () => {
    vi.stubEnv("NEXT_PUBLIC_CATALOG_API_BASE_URL", "");
    vi.stubEnv("CATALOG_API_INTERNAL_BASE_URL", "");
    vi.stubEnv("NEXT_PUBLIC_ALLOW_DEMO_FALLBACK", "");
    const { getPatterns } = await import("./catalog-api");

    await expect(getPatterns()).rejects.toThrow("未配置 Catalog API 地址");
  });

  it("returns visibly sourced demo data only after explicit opt-in", async () => {
    vi.stubEnv("NEXT_PUBLIC_CATALOG_API_BASE_URL", "");
    vi.stubEnv("CATALOG_API_INTERNAL_BASE_URL", "");
    vi.stubEnv("NEXT_PUBLIC_ALLOW_DEMO_FALLBACK", "true");
    const { getPatterns } = await import("./catalog-api");

    const result = await getPatterns();
    expect(result.source).toBe("demo");
    expect(result.data.length).toBeGreaterThan(0);
  });
});
