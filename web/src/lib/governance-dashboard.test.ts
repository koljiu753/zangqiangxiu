import { describe, expect, it } from "vitest";
import { toGovernanceStats } from "./governance-dashboard";

describe("governance dashboard stats", () => {
  it("maps the Catalog aggregate without recomputing list data", () => {
    expect(toGovernanceStats({ total: 12, statuses: { draft: 7, published: 5 }, rightsStatuses: { verified: 5 }, reviewRisk: { hasIssues: 3, rightsUnverified: 7 }, ready: 2, categories: [] })).toEqual({
      total: 12, draft: 7, published: 5, rightsUnverified: 7, hasIssues: 3, ready: 2,
    });
  });

  it("defaults missing status buckets to zero", () => {
    const result = toGovernanceStats({ total: 0, statuses: {}, rightsStatuses: {}, reviewRisk: { hasIssues: 0, rightsUnverified: 0 }, ready: 0, categories: [] });
    expect(result.draft).toBe(0);
    expect(result.published).toBe(0);
  });
});
