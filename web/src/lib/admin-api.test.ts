import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

describe("admin API client", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubEnv("CATALOG_API_INTERNAL_BASE_URL", "http://catalog.test/api/v1");
    vi.stubEnv("CATALOG_ADMIN_TOKEN", "test-token");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("passes backend pagination and filters through to Catalog", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      items: [], page: 3, pageSize: 20, total: 42, pages: 3,
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const { getAdminPatterns } = await import("./admin-api");
    await getAdminPatterns({ status: "draft", visibility: "internal_only", risk: "has_issues", page: 3 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe(
      "http://catalog.test/api/v1/admin/patterns?pageSize=20&page=3&status=draft&visibility=internal_only&risk=has_issues",
    );
  });

  it("uses one Catalog request for each batch operation", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({
      succeeded: 1, failed: 1, items: [],
    }), { status: 200, headers: { "Content-Type": "application/json" } })));
    vi.stubGlobal("fetch", fetchMock);
    const { batchReviewAdminPatterns, batchPublishAdminPatterns } = await import("./admin-api");
    const items = [{ patternId: "pat_001", reviewedBy: "reviewer", reviewedAt: "2026-09-06T00:00:00Z", issues: [] }];
    await batchReviewAdminPatterns(items);
    await batchPublishAdminPatterns(["pat_001", "pat_002"]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toBe("http://catalog.test/api/v1/admin/patterns/batch-review");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ items });
    expect(fetchMock.mock.calls[1][0]).toBe("http://catalog.test/api/v1/admin/patterns/batch-publish");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ patternIds: ["pat_001", "pat_002"] });
  });

  it("keeps evidence and review workflow calls on the server admin client", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ succeeded: 1, failed: 0, items: [] }), { status: 200, headers: { "Content-Type": "application/json" } })));
    vi.stubGlobal("fetch", fetchMock);
    const { updatePatternEvidence, getReviewTasks, assignReviewTask, decideReviewTask } = await import("./admin-api");
    await updatePatternEvidence("pat_001", { sourceDescription: "馆藏采集" });
    await getReviewTasks({ assignee: "专家甲", state: "assigned" });
    await assignReviewTask("pat_001", "专家甲", "assign_request_001");
    await decideReviewTask("pat_001", "approved", "专家甲", "通过", [], "decide_request_001");
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "http://catalog.test/api/v1/admin/patterns/pat_001/evidence",
      "http://catalog.test/api/v1/admin/reviews/tasks?assignee=%E4%B8%93%E5%AE%B6%E7%94%B2&state=assigned",
      "http://catalog.test/api/v1/admin/reviews/batch-assign",
      "http://catalog.test/api/v1/admin/reviews/batch-decide",
    ]);
    for (const call of fetchMock.mock.calls) expect(new Headers(call[1].headers).get("X-Admin-Token")).toBe("test-token");
  });

  it("forwards evidence bytes as multipart without exposing the admin token in form data", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "pat_001" }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const { uploadPatternEvidenceFile } = await import("./admin-api");
    const file = new File(["%PDF-test"], "授权书.pdf", { type: "application/pdf" });
    await uploadPatternEvidenceFile("pat/001", file);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://catalog.test/api/v1/admin/patterns/pat%2F001/evidence-files");
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    const uploaded = (init.body as FormData).get("file") as File;
    expect(uploaded.name).toBe(file.name);
    expect(uploaded.type).toBe(file.type);
    expect(uploaded.size).toBe(file.size);
    expect(Array.from((init.body as FormData).keys())).toEqual(["file"]);
    expect(new Headers(init.headers).get("X-Admin-Token")).toBe("test-token");
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
  });

  it("returns the private evidence response through the server client", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("file-bytes", { status: 200, headers: { "Content-Type": "application/pdf" } }));
    vi.stubGlobal("fetch", fetchMock);
    const { downloadPatternEvidenceFile } = await import("./admin-api");
    const response = await downloadPatternEvidenceFile("pat_001", "ev_001");
    expect(await response.text()).toBe("file-bytes");
    expect(fetchMock.mock.calls[0][0]).toBe("http://catalog.test/api/v1/admin/patterns/pat_001/evidence-files/ev_001");
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get("X-Admin-Token")).toBe("test-token");
  });
});
