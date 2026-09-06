import { describe, expect, it, vi } from "vitest";
import { analyzeStudioImage } from "./studio-analysis";

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("analyzeStudioImage", () => {
  it("uses internal scope on preview and enriches explainable matches", async () => {
    const fetcher = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/assets")) return response({ id: "asset-query" }, 201);
      if (url.endsWith("/analyses") && init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toMatchObject({ scope: "internal", top_k: 5 });
        return response({ id: "job-1" }, 202);
      }
      if (url.endsWith("/jobs/job-1")) return response({ id: "job-1", status: "succeeded", result_id: "result-1" });
      if (url.endsWith("/analyses/result-1")) return response({
        palette: [{ hex: "#AABBCC" }], classification: { status: "unavailable" },
        similar: [{ asset_id: "asset-ref", pattern_id: "pattern-1", label: "候选", score: .91 }],
        similarity_algorithm_version: "rgb-v1", warnings: ["classification unavailable"],
      });
      if (url.endsWith("/admin/patterns/pattern-1")) {
        expect((init?.headers as Record<string, string>)["X-Admin-Token"]).toBe("secret");
        return response({ id: "pattern-1", name: "万字纹", category: "几何纹", ethnicity: "藏族", meaning: "吉祥", colors: [], status: "draft" });
      }
      throw new Error(`unexpected ${url}`);
    }) as typeof fetch;
    const result = await analyzeStudioImage({ file: new File(["x"], "x.png"), aiBaseUrl: "http://ai/v1", catalogBaseUrl: "http://catalog/api/v1", previewInternal: true, adminToken: "secret", fetcher, pollDelayMs: 0 });
    expect(result.algorithmVersion).toBe("rgb-v1");
    expect(result.similar[0]).toMatchObject({ patternId: "pattern-1", name: "万字纹", score: .91 });
  });

  it("keeps production searches public and reports timeout", async () => {
    const fetcher = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/assets")) return response({ id: "asset-query" }, 201);
      if (url.endsWith("/analyses") && init?.method === "POST") {
        expect(JSON.parse(String(init.body)).scope).toBe("public");
        return response({ id: "job-2" }, 202);
      }
      return response({ id: "job-2", status: "running" });
    }) as typeof fetch;
    await expect(analyzeStudioImage({ file: new File(["x"], "x.png"), aiBaseUrl: "http://ai/v1", previewInternal: false, fetcher, pollDelayMs: 0, maxPolls: 1 })).rejects.toThrow("等待超时");
  });
});
