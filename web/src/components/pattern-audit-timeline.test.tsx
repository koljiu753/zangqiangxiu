import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { auditChanges, PatternAuditTimeline } from "./pattern-audit-timeline";
import type { PatternAuditLog } from "@/types/domain";

const log: PatternAuditLog = {
  id: 2,
  patternId: "pat_001",
  action: "updated",
  actor: "reviewer-a",
  before: { id: "pat_001", name: "旧名称", status: "draft", updatedAt: "old" },
  after: { id: "pat_001", name: "新名称", status: "draft", updatedAt: "new" },
  createdAt: "2026-09-04T09:30:00+08:00",
};

describe("PatternAuditTimeline", () => {
  it("shows translated action, actor and changed fields only", () => {
    render(<PatternAuditTimeline logs={[log]} />);
    expect(screen.getByText("更新资料")).toBeInTheDocument();
    expect(screen.getByText("reviewer-a")).toBeInTheDocument();
    expect(screen.getByText("旧名称")).toBeInTheDocument();
    expect(screen.getByText("新名称")).toBeInTheDocument();
    expect(auditChanges(log).map((item) => item.field)).toEqual(["name"]);
  });

  it("renders failure actions and empty history clearly", () => {
    const failure = { ...log, id: 3, action: "publish_sync_failed", before: {}, after: { error: "AI offline" } };
    const { rerender } = render(<PatternAuditTimeline logs={[failure]} />);
    expect(screen.getByText("AI 同步失败")).toBeInTheDocument();
    expect(screen.getByText("AI offline")).toBeInTheDocument();
    rerender(<PatternAuditTimeline logs={[]} />);
    expect(screen.getByText("暂无审计记录")).toBeInTheDocument();
  });
});
