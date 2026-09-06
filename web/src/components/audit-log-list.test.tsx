import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AuditLogList } from "./audit-log-list";

describe("AuditLogList", () => {
  it("renders actor, pattern link and concise before/after summary", () => {
    render(<AuditLogList logs={[{ id: 9, patternId: "pat/一", action: "updated", actor: "reviewer-a", before: { name: "旧名" }, after: { name: "新名" }, createdAt: "2026-09-06T08:00:00Z" }]} />);
    expect(screen.getByText("更新资料")).toBeInTheDocument();
    expect(screen.getByText("reviewer-a")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "pat/一" })).toHaveAttribute("href", "/admin/patterns/pat%2F%E4%B8%80/audit");
    expect(screen.getByText("旧名")).toBeInTheDocument();
    expect(screen.getByText("新名")).toBeInTheDocument();
  });

  it("has a useful empty state", () => {
    render(<AuditLogList logs={[]} />);
    expect(screen.getByRole("heading", { name: "没有符合条件的审计记录" })).toBeInTheDocument();
  });
});
