import { describe, expect, it } from "vitest";
import { getPublishBlockers, getPublishReadiness } from "./admin-review";
import type { AdminPattern } from "@/types/domain";

const base: AdminPattern = {
  id: "pat_001", name: "祥云纹", category: "自然纹", ethnicity: "藏羌共融", meaning: "吉祥", colors: [],
  status: "draft", visibility: "internal_only", source: { system: "test", originClaim: "unknown" },
  rights: { status: "verified" }, review: { issues: [] }, createdAt: "2026-01-01", updatedAt: "2026-01-01",
};

describe("getPublishReadiness", () => {
  it("accepts only a named, verified, issue-free record", () => expect(getPublishReadiness(base)).toEqual({ ready: true, risks: [] }));
  it("reports every blocking risk", () => {
    const result = getPublishReadiness({ ...base, name: " ", rights: { status: "unverified" }, review: { issues: ["来源不明"] } });
    expect(result.ready).toBe(false);
    expect(result.risks).toEqual(["缺少名称", "版权未核验", "1 项风险未清零"]);
  });
});

describe("getPublishBlockers", () => {
  it("provides actionable detail for every blocker", () => {
    const blockers = getPublishBlockers({ ...base, name: "", rights: { status: "pending" }, review: { issues: ["来源待复核", "图片模糊"] } });
    expect(blockers.map((item) => item.code)).toEqual(["missing_name", "rights_unverified", "review_issues"]);
    expect(blockers[1]).toMatchObject({ label: "版权未核验", detail: "当前版权状态：pending。", action: "核验权利人与授权依据" });
    expect(blockers[2].detail).toBe("来源待复核；图片模糊");
  });
});
