import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReviewQueueCard } from "./review-queue-card";
import type { AdminPattern } from "@/types/domain";

const pattern: AdminPattern = {
  id: "pat_001", name: "祥云纹", category: "自然纹", ethnicity: "藏羌共融", meaning: "吉祥", colors: [],
  status: "draft", visibility: "internal_only", source: { system: "test", originClaim: "unknown" },
  rights: { status: "unverified" }, review: { issues: ["来源待复核"] }, createdAt: "2026-01-01", updatedAt: "2026-09-06T10:00:00Z",
};

describe("ReviewQueueCard", () => {
  it("shows blocker reasons, next actions, and review routes", () => {
    render(<ReviewQueueCard pattern={pattern} />);
    expect(screen.getByText("2 类阻塞")).toBeInTheDocument();
    expect(screen.getByText("版权未核验")).toBeInTheDocument();
    expect(screen.getByText("下一步：核验权利人与授权依据")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "进入审核详情" })).toHaveAttribute("href", "/admin/patterns/pat_001");
    expect(screen.getByRole("link", { name: "审计记录" })).toHaveAttribute("href", "/admin/patterns/pat_001/audit");
  });

  it("shows readiness when the record has no blockers", () => {
    render(<ReviewQueueCard pattern={{ ...pattern, rights: { status: "verified" }, review: { issues: [] } }} />);
    expect(screen.getByText("可发布")).toBeInTheDocument();
    expect(screen.getByText("发布校验已满足")).toBeInTheDocument();
  });

  it("shows review assignment and task state", () => {
    render(<ReviewQueueCard pattern={pattern} task={{ patternId: pattern.id, assignee: "专家甲", state: "assigned", assignedAt: "2026-09-06" }} />);
    expect(screen.getByText("专家甲 · assigned")).toBeInTheDocument();
  });
});
