import { describe, expect, it } from "vitest";
import { auditPageHref } from "./page";

describe("auditPageHref", () => {
  it("preserves every active filter across stable pagination", () => {
    expect(auditPageHref({ actor: "alice", action: "updated", patternId: "pat 1", q: "审核", from: "2026-09-01T00:00", to: "2026-09-06T23:59" }, 3))
      .toBe("/admin/audit?page=3&actor=alice&action=updated&patternId=pat+1&q=%E5%AE%A1%E6%A0%B8&from=2026-09-01T00%3A00&to=2026-09-06T23%3A59");
  });
});
