import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ requireAdmin: vi.fn(), exportAdminPatternsCsv: vi.fn() }));
vi.mock("@/lib/admin-auth-server", () => ({ requireAdmin: mocks.requireAdmin }));
vi.mock("@/lib/admin-api", () => ({ exportAdminPatternsCsv: mocks.exportAdminPatternsCsv }));

describe("governance CSV proxy", () => {
  beforeEach(() => vi.clearAllMocks());

  it("whitelists filters and forwards only safe response headers", async () => {
    mocks.exportAdminPatternsCsv.mockResolvedValue(new Response("csv-body", { headers: {
      "Content-Type": "text/csv; charset=utf-8", "Content-Disposition": "attachment; filename=patterns.csv",
      "X-Exported-Rows": "12", "X-Admin-Token": "must-not-leak", "Set-Cookie": "must-not-leak=1",
    } }));
    const { GET } = await import("./route");
    const response = await GET(new Request("http://localhost/admin/dashboard/export?status=draft&visibility=bad&risk=ready&limit=12&token=leak"));
    expect(mocks.requireAdmin).toHaveBeenCalledWith("reviewer");
    expect(mocks.exportAdminPatternsCsv).toHaveBeenCalledWith({ status: "draft", risk: "ready", limit: 12 });
    expect(await response.text()).toBe("csv-body");
    expect(response.headers.get("x-exported-rows")).toBe("12");
    expect(response.headers.get("x-admin-token")).toBeNull();
    expect(response.headers.get("set-cookie")).toBeNull();
    expect(response.headers.get("cache-control")).toBe("private, no-store");
    expect(response.headers.get("x-content-type-options")).toBe("nosniff");
  });

  it("rejects access before calling Catalog", async () => {
    mocks.requireAdmin.mockRejectedValueOnce(new Error("无权执行此操作"));
    const { GET } = await import("./route");
    const response = await GET(new Request("http://localhost/admin/dashboard/export"));
    expect(response.status).toBe(403);
    expect(mocks.exportAdminPatternsCsv).not.toHaveBeenCalled();
  });
});
