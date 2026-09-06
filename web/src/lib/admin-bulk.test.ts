import { describe, expect, it } from "vitest";
import { adminPageHref, selectedPatternIds, splitIssues, summarizeBatch } from "./admin-bulk";

describe("admin bulk helpers", () => {
  it("deduplicates and rejects malformed selected ids", () => {
    const form = new FormData();
    form.append("selectedIds", "pat_001"); form.append("selectedIds", "pat_001"); form.append("selectedIds", "../bad");
    expect(selectedPatternIds(form)).toEqual(["pat_001"]);
  });

  it("splits review issues and reports partial failure", () => {
    expect(splitIssues("来源不明，文化待核\n图片待核")).toEqual(["来源不明", "文化待核", "图片待核"]);
    expect(summarizeBatch([{ id: "a", ok: true, message: "ok" }, { id: "b", ok: false, message: "bad" }], "批量更新")).toMatchObject({ ok: false, message: "批量更新：1 条成功，1 条失败" });
  });

  it("preserves filters while changing pages", () => {
    expect(adminPageHref({ status: "draft", visibility: "internal_only", risk: "has_issues" }, 3))
      .toBe("/admin?status=draft&visibility=internal_only&risk=has_issues&page=3");
    expect(adminPageHref({}, 0)).toBe("/admin?page=1");
  });
});
