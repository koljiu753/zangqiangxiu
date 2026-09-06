import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ReviewWorkflowPanel } from "./review-workflow-panel";
import type { AdminPattern } from "@/types/domain";

vi.mock("@/app/admin/actions", () => ({
  saveEvidence: vi.fn(), assignReview: vi.fn(), decideReview: vi.fn(),
}));

const pattern: AdminPattern = {
  id: "pat/001", name: "测试纹样", category: "几何", ethnicity: "unknown", meaning: "",
  colors: [], status: "draft", visibility: "internal_only",
  source: { system: "archive", originClaim: "馆藏", description: "来源说明" },
  rights: { status: "pending", evidence: [{ id: "ev/001", filename: "授权书.pdf", contentType: "application/pdf", sizeBytes: 2048, storageKey: "private/key", checksumSha256: "a".repeat(64) }] },
  review: { issues: [] }, createdAt: "2026-01-01", updatedAt: "2026-01-01",
};

describe("ReviewWorkflowPanel evidence upload", () => {
  it("uses a constrained real file input and a safe internal download link", () => {
    const { container } = render(<ReviewWorkflowPanel pattern={pattern} csrfToken="csrf" />);
    const file = container.querySelector('input[name="evidenceFile"]') as HTMLInputElement;
    expect(file.type).toBe("file");
    expect(file.accept).toContain("application/pdf");
    expect(file.accept).toContain("image/png");
    expect(screen.getByRole("link", { name: "安全下载" })).toHaveAttribute("href", "/admin/patterns/pat%2F001/evidence/ev%2F001");
    expect(screen.queryByText("private/key")).not.toBeInTheDocument();
    expect(container.querySelector('input[name="evidenceStorageKey"]')).toBeNull();
    expect(screen.getByText(/2.0 KiB/)).toBeInTheDocument();
  });

  it("requires an explicit decision and record-specific confirmation", () => {
    render(<ReviewWorkflowPanel pattern={pattern} task={{ patternId: pattern.id, assignee: "专家甲", state: "assigned", assignedAt: "2026-09-06" }} csrfToken="csrf" />);
    const decision = screen.getByRole("combobox", { name: "审核决定" });
    const submit = screen.getByRole("button", { name: "确认并记录审核决定" });
    expect(decision).toHaveValue("");
    expect(submit).toBeDisabled();
    fireEvent.change(decision, { target: { value: "approved" } });
    expect(screen.getByText(/我确认对记录/)).toHaveTextContent("测试纹样");
    expect(screen.getByText(/我确认对记录/)).toHaveTextContent("通过");
    expect(submit).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: /我确认对记录/ }));
    expect(submit).toBeEnabled();
    fireEvent.change(decision, { target: { value: "rejected" } });
    expect(submit).toBeDisabled();
  });
});
