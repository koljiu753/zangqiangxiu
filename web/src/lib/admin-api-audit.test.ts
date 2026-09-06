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
    expect(fetcher).toHaveBeenCalledWith(
      "http://catalog:8001/api/v1/admin/patterns/pat%2F%E4%B8%80/audit-logs",
      expect.objectContaining({ cache: "no-store", headers: expect.objectContaining({ "X-Admin-Token": "secret" }) }),
    );
  });
});
