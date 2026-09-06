import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

describe("getPatternAuditLogs", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
    delete process.env.CATALOG_API_INTERNAL_BASE_URL;
    delete process.env.CATALOG_ADMIN_TOKEN;
  });

  it("reads the encoded admin audit endpoint without caching", async () => {
    process.env.CATALOG_API_INTERNAL_BASE_URL = "http://catalog:8001/api/v1";
    process.env.CATALOG_ADMIN_TOKEN = "secret";
    const fetcher = vi.fn(async () => new Response(JSON.stringify([]), { status: 200 }));
    vi.stubGlobal("fetch", fetcher);
    const { getPatternAuditLogs } = await import("./admin-api");
    await expect(getPatternAuditLogs("pat/一")).resolves.toEqual([]);
    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://catalog:8001/api/v1/admin/patterns/pat%2F%E4%B8%80/audit-logs");
    expect(init.cache).toBe("no-store");
    expect(new Headers(init.headers).get("X-Admin-Token")).toBe("secret");
  });
});
