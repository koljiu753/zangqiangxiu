import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

describe("getAuditLogs", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.resetModules(); delete process.env.CATALOG_API_INTERNAL_BASE_URL; delete process.env.CATALOG_ADMIN_TOKEN; });

  it("keeps filters server-side and disables caching", async () => {
    process.env.CATALOG_API_INTERNAL_BASE_URL = "http://catalog:8001/api/v1";
    process.env.CATALOG_ADMIN_TOKEN = "secret";
    const payload = { items: [], page: 2, pageSize: 20, total: 0, pages: 0 };
    const fetcher = vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 }));
    vi.stubGlobal("fetch", fetcher);
    const { getAuditLogs } = await import("./admin-api");
    await expect(getAuditLogs({ actor: "alice", action: "updated", patternId: "pat_1", q: "source", from: "2026-09-01T00:00", to: "2026-09-06T23:59", page: 2 })).resolves.toEqual(payload);
    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("/admin/audit-logs?");
    expect(url).toContain("actor=alice");
    expect(url).toContain("patternId=pat_1");
    expect(url).toContain("page=2");
    expect(init.cache).toBe("no-store");
    expect(new Headers(init.headers).get("X-Admin-Token")).toBe("secret");
  });
});
