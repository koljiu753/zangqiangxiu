import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createHmac } from "node:crypto";

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

  it("loads dashboard metrics from the single Catalog stats endpoint", async () => {
    const payload = { total: 10, statuses: { draft: 8, published: 2 }, rightsStatuses: {}, reviewRisk: { hasIssues: 1, rightsUnverified: 8 }, ready: 1, categories: [] };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const { getCatalogStats } = await import("./admin-api");
    await expect(getCatalogStats()).resolves.toEqual(payload);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("http://catalog.test/api/v1/admin/patterns/stats");
  });

  it("loads specialty queue summary and filtered server pagination", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ items: [], page: 2, pageSize: 20, total: 21, pages: 2 }), { status: 200, headers: { "Content-Type": "application/json" } })));
    vi.stubGlobal("fetch", fetchMock);
    const { getReviewQueueSummary, getReviewQueuePatterns } = await import("./admin-api");
    await getReviewQueueSummary();
    await getReviewQueuePatterns({ queue: "category_suggestion", page: 2, q: "云", suggestion: "plant" });
    expect(fetchMock.mock.calls[0][0]).toBe("http://catalog.test/api/v1/admin/review-queues/summary");
    expect(fetchMock.mock.calls[1][0]).toBe("http://catalog.test/api/v1/admin/review-queues/patterns?queue=category_suggestion&page=2&pageSize=20&q=%E4%BA%91&suggestion=plant");
  });

  it("proxies Catalog CSV export filters through the server client", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("csv", { status: 200, headers: { "Content-Type": "text/csv" } }));
    vi.stubGlobal("fetch", fetchMock);
    const { exportAdminPatternsCsv } = await import("./admin-api");
    await exportAdminPatternsCsv({ status: "draft", visibility: "internal_only", risk: "has_issues", limit: 250 });
    expect(fetchMock.mock.calls[0][0]).toBe("http://catalog.test/api/v1/admin/patterns/export.csv?status=draft&visibility=internal_only&risk=has_issues&limit=250");
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get("X-Admin-Token")).toBe("test-token");
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

  it("signs the authenticated operator and request id for mutations", async () => {
    const secret = "actor-secret-that-is-at-least-32-bytes";
    vi.stubEnv("CATALOG_ACTOR_SIGNING_SECRET", secret);
    vi.setSystemTime(new Date("2026-09-06T00:00:00Z"));
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ succeeded: 1, failed: 0, items: [] }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const { batchPublishAdminPatterns } = await import("./admin-api");
    await batchPublishAdminPatterns(["pat_001"], "operator-a");
    const headers = new Headers(fetchMock.mock.calls[0][1].headers);
    const timestamp = headers.get("X-Admin-Timestamp")!;
    const requestId = headers.get("X-Request-ID")!;
    const canonical = `${timestamp}\nPOST\n/api/v1/admin/patterns/batch-publish\noperator-a\n${requestId}`;
    expect(headers.get("X-Admin-Actor")).toBe("operator-a");
    expect(headers.get("X-Admin-Signature")).toBe(createHmac("sha256", secret).update(canonical).digest("hex"));
  });

  it("keeps evidence and review workflow calls on the server admin client", async () => {
    vi.stubEnv("CATALOG_ACTOR_SIGNING_SECRET", "actor-secret-that-is-at-least-32-bytes");
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ succeeded: 1, failed: 0, items: [] }), { status: 200, headers: { "Content-Type": "application/json" } })));
    vi.stubGlobal("fetch", fetchMock);
    const { updatePatternEvidence, getReviewTasks, assignReviewTask, bulkAssignReviewTasks, decideReviewTask } = await import("./admin-api");
    await updatePatternEvidence("pat_001", { sourceDescription: "馆藏采集" });
    await getReviewTasks({ assignee: "专家甲", state: "assigned" });
    await assignReviewTask("pat_001", "reviewer-a", "assign_request_001", "operator-a");
    await bulkAssignReviewTasks({ patternIds: ["pat_002"], assignee: "reviewer-b", requestId: "bulk_assign_request_002" }, "operator-a");
    await decideReviewTask("pat_001", "approved", "operator-a", "通过", [], "decide_request_001", "operator-a");
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "http://catalog.test/api/v1/admin/patterns/pat_001/evidence",
      "http://catalog.test/api/v1/admin/reviews/tasks?assignee=%E4%B8%93%E5%AE%B6%E7%94%B2&state=assigned",
      "http://catalog.test/api/v1/admin/reviews/batch-assign",
      "http://catalog.test/api/v1/admin/reviews/bulk-assign",
      "http://catalog.test/api/v1/admin/reviews/batch-decide",
    ]);
    expect(JSON.parse(fetchMock.mock.calls[3][1].body)).toEqual({ patternIds: ["pat_002"], assignee: "reviewer-b", requestId: "bulk_assign_request_002" });
    for (const index of [2, 3, 4]) expect(new Headers(fetchMock.mock.calls[index][1].headers).get("X-Admin-Actor")).toBe("operator-a");
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
