import type { AdminPattern } from "@/types/domain";

export type PublishBlocker = {
  code: "missing_name" | "rights_unverified" | "review_issues";
  label: string;
  detail: string;
  action: string;
};

export function getPublishBlockers(pattern: AdminPattern): PublishBlocker[] {
  const blockers: PublishBlocker[] = [];
  if (!pattern.name.trim()) blockers.push({ code: "missing_name", label: "名称缺失", detail: "档案没有可公开展示的名称。", action: "补充名称" });
  if (pattern.rights.status !== "verified") blockers.push({
    code: "rights_unverified",
    label: "版权未核验",
    detail: `当前版权状态：${pattern.rights.status || "unknown"}。`,
    action: "核验权利人与授权依据",
  });
  if (pattern.review.issues.length > 0) blockers.push({
    code: "review_issues",
    label: `${pattern.review.issues.length} 项风险未清零`,
    detail: pattern.review.issues.join("；"),
    action: "处理并清空风险项",
  });
  return blockers;
}

export function getPublishReadiness(pattern: AdminPattern) {
  const risks = getPublishBlockers(pattern).map((blocker) => blocker.code === "missing_name" ? "缺少名称" : blocker.label);
  return { ready: risks.length === 0, risks };
}
