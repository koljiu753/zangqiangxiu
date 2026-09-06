import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReviewOperationsBoard } from "./review-operations-board";

const data = {
  summary: { total: 10, unassigned: 2, assigned: 3, approved: 3, rejected: 1, needsMore: 1, completed: 5, completionRate: 50, assignees: [] },
  workloads: [{ assignee: "reviewer-a", total: 5, assigned: 1, approved: 3, rejected: 0, needsMore: 1, completed: 4, completionRate: 80 }],
  items: [{ patternId: "pat_001", patternName: "祥云纹", assignee: "reviewer-a", state: "needs_more" as const, assignedAt: "2026-09-06T01:00:00Z" }],
  page: 1, pageSize: 20, total: 1, pages: 1,
};

describe("ReviewOperationsBoard", () => {
  it("renders workload, completion progress and linked task details", () => {
    render(<ReviewOperationsBoard data={data}/>);
    expect(screen.getByText("任务总量")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "审核完成率 50.0%" })).toHaveValue(50);
    const workload = screen.getByRole("region", { name: "审核人工作量" });
    expect(within(workload).getByText("reviewer-a")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "祥云纹" })).toHaveAttribute("href", "/admin/patterns/pat_001");
    expect(within(screen.getByRole("region", { name: "任务明细" })).getByText("需补充")).toBeInTheDocument();
  });

  it("shows clear empty states", () => {
    render(<ReviewOperationsBoard data={{ ...data, workloads: [], items: [], total: 0 }}/>);
    expect(screen.getByText("尚无已分配任务。")).toBeInTheDocument();
    expect(screen.getByText("当前筛选条件下没有任务。")).toBeInTheDocument();
  });
});
