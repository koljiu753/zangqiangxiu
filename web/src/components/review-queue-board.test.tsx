import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ReviewQueueBoard } from "./review-queue-board";
import type { CatalogReviewQueueItem, ReviewTask } from "@/types/domain";

const items: CatalogReviewQueueItem[] = [
  { patternId: "pat_001", name: "祥云纹", category: "自然纹", status: "draft", visibility: "internal_only", width: 120, height: 180, lowResolution: true, nameNeedsReview: false, duplicateName: false, duplicateNameCount: 1, categoryNeedsReview: false },
  { patternId: "pat_002", name: "羊角纹", category: "未分类", status: "draft", visibility: "internal_only", lowResolution: false, nameNeedsReview: true, duplicateName: true, duplicateNameCount: 2, categoryNeedsReview: true, categorySuggestionCode: "animal", categorySuggestionLabel: "动物纹" },
];
const tasks: ReviewTask[] = [{ patternId: "pat_001", assignee: "专家甲", state: "assigned", assignedAt: "2026-09-06" }];

describe("ReviewQueueBoard", () => {
  it("selects only requested ids and renders derived specialty signals", () => {
    const action = vi.fn(async () => ({ ok: true, message: "已分派", results: [] }));
    const { container } = render(<ReviewQueueBoard items={items} tasks={tasks} csrfToken="csrf-token" assignAction={action}/>);
    fireEvent.click(screen.getByRole("checkbox", { name: "选择 祥云纹" }));
    expect(screen.getByRole("checkbox", { name: "全选当前 2 条" })).toHaveProperty("indeterminate", true);
    expect(container.querySelector(".batch-selection")).toHaveTextContent("已选择 1 条");
    expect(container.querySelectorAll('input[name="selectedIds"]')).toHaveLength(1);
    expect(container.querySelector('input[name="selectedIds"]')).toHaveValue("pat_001");
    expect(screen.getByText("低清晰度（120×180）")).toBeInTheDocument();
    expect(screen.getByText("分类建议：动物纹")).toBeInTheDocument();
    expect(screen.getByText("专家甲 · assigned")).toBeInTheDocument();
  });

  it("selects and clears the current server page", () => {
    const action = vi.fn(async () => ({ ok: true, message: "已分派", results: [] }));
    const { container } = render(<ReviewQueueBoard items={items} tasks={tasks} csrfToken="csrf-token" assignAction={action}/>);
    const selectAll = screen.getByRole("checkbox", { name: "全选当前 2 条" });
    fireEvent.click(selectAll);
    expect(container.querySelectorAll('input[name="selectedIds"]')).toHaveLength(2);
    fireEvent.click(selectAll);
    expect(container.querySelectorAll('input[name="selectedIds"]')).toHaveLength(0);
    expect(screen.getByRole("button", { name: "分派选中 0 条记录" })).toBeDisabled();
  });

  it("clears only successfully assigned selections and focuses partial-failure feedback", async () => {
    const action = vi.fn(async () => ({ ok: false, message: "批量分派：1 条成功，1 条失败", results: [
      { id: "pat_001", ok: true, message: "已分派" }, { id: "pat_002", ok: false, message: "记录不可分派" },
    ] }));
    const { container } = render(<ReviewQueueBoard items={items} tasks={tasks} csrfToken="csrf-token" assignAction={action}/>);
    fireEvent.click(screen.getByRole("checkbox", { name: "全选当前 2 条" }));
    fireEvent.change(screen.getByRole("textbox", { name: "审核人" }), { target: { value: "专家乙" } });
    fireEvent.click(screen.getByRole("button", { name: "分派选中 2 条记录" }));
    await waitFor(() => expect(action).toHaveBeenCalled());
    await waitFor(() => expect(container.querySelectorAll('input[name="selectedIds"]')).toHaveLength(1));
    expect(container.querySelector('input[name="selectedIds"]')).toHaveValue("pat_002");
    const feedback = await screen.findByRole("alert");
    expect(feedback).toHaveFocus();
    expect(feedback).toHaveTextContent("1 条成功，1 条失败");
  });
});
