import type { AdminPattern } from "@/types/domain";

export type GovernanceStats = {
  total: number;
  draft: number;
  published: number;
  rightsUnverified: number;
  hasIssues: number;
  ready: number;
};

export function csvCell(value: unknown) {
  const raw = value == null ? "" : String(value);
  const safe = /^[=+\-@]/.test(raw) ? `'${raw}` : raw;
  return `"${safe.replace(/"/g, '""')}"`;
}

export function patternsCsv(patterns: AdminPattern[]) {
  const rows = patterns.map((pattern) => [
    pattern.id, pattern.name, pattern.category, pattern.ethnicity, pattern.status, pattern.visibility,
    pattern.rights.status, pattern.rights.owner, pattern.rights.license, pattern.review.reviewedBy,
    pattern.review.issues.join(" | "), pattern.source.system, pattern.updatedAt,
  ]);
  return "\uFEFF" + [["ID", "名称", "分类", "民族", "状态", "可见性", "版权状态", "权利人", "授权依据", "审核人", "风险项", "来源系统", "更新时间"], ...rows]
    .map((row) => row.map(csvCell).join(",")).join("\r\n");
}
