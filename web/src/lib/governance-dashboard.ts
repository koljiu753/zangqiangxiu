import type { CatalogStats } from "@/lib/admin-api";

export type GovernanceStats = {
  total: number;
  draft: number;
  published: number;
  rightsUnverified: number;
  hasIssues: number;
  ready: number;
};

export function toGovernanceStats(stats: CatalogStats): GovernanceStats {
  return {
    total: stats.total,
    draft: stats.statuses.draft || 0,
    published: stats.statuses.published || 0,
    rightsUnverified: stats.reviewRisk.rightsUnverified,
    hasIssues: stats.reviewRisk.hasIssues,
    ready: stats.ready,
  };
}
