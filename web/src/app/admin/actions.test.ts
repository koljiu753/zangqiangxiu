import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  requireAdmin: vi.fn(),
  bulkAssignReviewTasks: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("@/lib/admin-auth-server", () => ({ requireAdmin: mocks.requireAdmin }));
vi.mock("@/lib/admin-api", () => ({
  assignReviewTask: vi.fn(), bulkAssignReviewTasks: mocks.bulkAssignReviewTasks,
  batchPublishAdminPatterns: vi.fn(), batchReviewAdminPatterns: vi.fn(), decideReviewTask: vi.fn(),
  getAdminPattern: vi.fn(), getReviewTasks: vi.fn(), publishAdminPattern: vi.fn(), updateAdminPattern: vi.fn(),
  updatePatternEvidence: vi.fn(), uploadPatternEvidenceFile: vi.fn(),
}));

import { bulkAssignReviews } from "./actions";

describe("bulkAssignReviews", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.requireAdmin.mockResolvedValue({ subject: "operator-a", role: "reviewer" });
    mocks.bulkAssignReviewTasks.mockResolvedValue({ succeeded: 2, failed: 0, items: [
      { patternId: "pat_001", status: "succeeded", replayed: false },
      { patternId: "pat_002", status: "succeeded", replayed: false },
    ] });
  });

  it("checks CSRF and assigns the selected records with one batch request id", async () => {
    const form = new FormData();
    form.set("csrfToken", "csrf-token");
    form.set("assignee", "专家甲");
    form.append("selectedIds", "pat_001");
    form.append("selectedIds", "pat_002");
    const result = await bulkAssignReviews({ ok: false, message: "", results: [] }, form);
    expect(mocks.requireAdmin).toHaveBeenCalledWith("reviewer", "csrf-token");
    const [payload, actor] = mocks.bulkAssignReviewTasks.mock.calls[0];
    expect(actor).toBe("operator-a");
    expect(payload.patternIds).toEqual(["pat_001", "pat_002"]);
    expect(payload).toMatchObject({ assignee: "专家甲", requestId: expect.stringMatching(/^bulk_assign_/) });
    expect(result).toMatchObject({ ok: true, message: "批量分派：2 条成功，0 条失败" });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/admin/review");
  });

  it("does not call Catalog when CSRF validation fails", async () => {
    mocks.requireAdmin.mockRejectedValue(new Error("CSRF 校验失败"));
    const form = new FormData();
    form.set("csrfToken", "bad-token");
    form.set("assignee", "专家甲");
    form.append("selectedIds", "pat_001");
    await expect(bulkAssignReviews({ ok: false, message: "", results: [] }, form)).resolves.toEqual({ ok: false, message: "CSRF 校验失败", results: [] });
    expect(mocks.bulkAssignReviewTasks).not.toHaveBeenCalled();
  });
});
