import { beforeEach, describe, expect, it, vi } from "vitest";

const requireAdmin = vi.fn();
const downloadPatternEvidenceFile = vi.fn();
vi.mock("@/lib/admin-auth-server", () => ({ requireAdmin }));
vi.mock("@/lib/admin-api", () => ({ downloadPatternEvidenceFile }));

describe("evidence download route", () => {
  beforeEach(() => vi.clearAllMocks());

  it("requires reviewer auth and forwards only safe download headers", async () => {
    downloadPatternEvidenceFile.mockResolvedValue(new Response("pdf", { headers: {
      "Content-Type": "application/pdf", "Content-Disposition": "attachment; filename=test.pdf",
      "X-Checksum-Sha256": "abc", "X-Admin-Token": "must-not-leak",
    } }));
    const { GET } = await import("./route");
    const response = await GET(new Request("http://localhost/download"), { params: Promise.resolve({ id: "pat_1", evidenceId: "ev_1" }) });
    expect(requireAdmin).toHaveBeenCalledWith("reviewer");
    expect(downloadPatternEvidenceFile).toHaveBeenCalledWith("pat_1", "ev_1");
    expect(response.headers.get("content-disposition")).toContain("test.pdf");
    expect(response.headers.get("x-admin-token")).toBeNull();
    expect(response.headers.get("cache-control")).toBe("private, no-store");
    expect(response.headers.get("x-content-type-options")).toBe("nosniff");
    expect(await response.text()).toBe("pdf");
  });

  it("does not call Catalog when the session is unauthorized", async () => {
    requireAdmin.mockRejectedValueOnce(new Error("无权执行此操作"));
    const { GET } = await import("./route");
    const response = await GET(new Request("http://localhost/download"), { params: Promise.resolve({ id: "pat_1", evidenceId: "ev_1" }) });
    expect(response.status).toBe(403);
    expect(downloadPatternEvidenceFile).not.toHaveBeenCalled();
  });
});
