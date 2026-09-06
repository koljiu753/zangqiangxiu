import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AdminPattern } from "@/types/domain";

vi.mock("@/app/admin/actions", () => ({
  bulkUpdatePatterns: vi.fn(), bulkPublishPatterns: vi.fn(), savePattern: vi.fn(), publishPattern: vi.fn(),
}));

import { AdminBatchReview } from "./admin-batch-review";

const pattern: AdminPattern = {
  id: "pat_001", name: "祥云纹", category: "自然纹", ethnicity: "藏羌共融", meaning: "吉祥", colors: [], status: "draft", visibility: "internal_only",
  source: { system: "test", originClaim: "unknown" }, rights: { status: "unverified" }, review: { issues: ["来源待核"] }, createdAt: "2026-01-01", updatedAt: "2026-01-01",
};

describe("AdminBatchReview", () => {
  it("selects candidates and never defaults rights to verified", () => {
    const { container } = render(<AdminBatchReview patterns={[pattern]} csrfToken="csrf" canPublish />);
    fireEvent.click(screen.getByRole("checkbox", { name: "选择 祥云纹" }));
    expect(container.querySelector(".batch-selection")).toHaveTextContent("已选择 1 条");
    expect(screen.getByRole("button", { name: "审核选中记录" })).toBeEnabled();
    expect(container.querySelector('input[name="bulkReviewedBy"]')).not.toBeInTheDocument();
    expect(screen.getByText(/登录会话自动记录/)).toBeInTheDocument();
    expect(container.querySelector('select[name="bulkRightsStatus"]')).not.toBeInTheDocument();
    expect(container.querySelectorAll('input[name="selectedIds"][value="pat_001"]')).toHaveLength(2);
  });

  it("keeps bulk publish disabled for reviewers", () => {
    render(<AdminBatchReview patterns={[pattern]} csrfToken="csrf" canPublish={false} />);
    fireEvent.click(screen.getByRole("checkbox", { name: "选择 祥云纹" }));
    expect(screen.getAllByRole("button", { name: "需要发布员权限" })).toHaveLength(2);
    screen.getAllByRole("button", { name: "需要发布员权限" }).forEach((button) => expect(button).toBeDisabled());
  });
});
