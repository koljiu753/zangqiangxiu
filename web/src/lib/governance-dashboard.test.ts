import { describe, expect, it } from "vitest";
import { csvCell, patternsCsv } from "./governance-dashboard";
import type { AdminPattern } from "@/types/domain";

const pattern: AdminPattern = {
  id: "pat_001", name: "祥云,纹", category: "自然纹", ethnicity: "藏羌共融", meaning: "吉祥", colors: [], status: "draft", visibility: "internal_only",
  source: { system: "archive", originClaim: "unknown" }, rights: { status: "unverified", owner: "=危险公式" }, review: { issues: ["来源待核"] }, createdAt: "2026-01-01", updatedAt: "2026-01-02",
};

describe("governance dashboard CSV", () => {
  it("quotes values and neutralizes spreadsheet formulas", () => {
    expect(csvCell('a"b')).toBe('"a""b"');
    expect(csvCell("=SUM(A1:A2)")).toBe('"\'=SUM(A1:A2)"');
  });

  it("exports governed fields with a UTF-8 BOM", () => {
    const csv = patternsCsv([pattern]);
    expect(csv.startsWith("\uFEFF")).toBe(true);
    expect(csv).toContain('"祥云,纹"');
    expect(csv).toContain('"\'=危险公式"');
    expect(csv).toContain('"来源待核"');
  });
});
