// @vitest-environment node
import { afterEach, describe, expect, it } from "vitest";
import { POST } from "./route";
import { resetStudioLimitsForTests } from "@/lib/studio-rate-limit";

const originalAiUrl = process.env.AI_API_INTERNAL_BASE_URL;
const originalPublicAiUrl = process.env.NEXT_PUBLIC_AI_API_BASE_URL;

afterEach(() => {
  resetStudioLimitsForTests();
  if (originalAiUrl === undefined) delete process.env.AI_API_INTERNAL_BASE_URL;
  else process.env.AI_API_INTERNAL_BASE_URL = originalAiUrl;
  if (originalPublicAiUrl === undefined) delete process.env.NEXT_PUBLIC_AI_API_BASE_URL;
  else process.env.NEXT_PUBLIC_AI_API_BASE_URL = originalPublicAiUrl;
});

describe("studio analysis BFF", () => {
  it("fails closed when the internal AI service is not configured", async () => {
    delete process.env.AI_API_INTERNAL_BASE_URL;
    delete process.env.NEXT_PUBLIC_AI_API_BASE_URL;
    const response = await POST(new Request("http://localhost/api/studio/analysis", { method: "POST" }));
    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({ error: "AI 服务尚未配置" });
  });

  it("accepts the legacy public AI URL as a server-side compatibility fallback", async () => {
    delete process.env.AI_API_INTERNAL_BASE_URL;
    process.env.NEXT_PUBLIC_AI_API_BASE_URL = "https://ai.example.test/v1";
    const response = await POST(new Request("http://localhost/api/studio/analysis", { method: "POST", body: new FormData() }));
    expect(response.status).toBe(400);
    await expect(response.json()).resolves.toEqual({ error: "请选择有效图片" });
  });

  it("rejects a request without an image before calling upstream", async () => {
    process.env.AI_API_INTERNAL_BASE_URL = "http://ai:8002/v1";
    const response = await POST(new Request("http://localhost/api/studio/analysis", { method: "POST", body: new FormData() }));
    expect(response.status).toBe(400);
    await expect(response.json()).resolves.toEqual({ error: "请选择有效图片" });
  });

  it("rejects an oversized body before parsing multipart data", async () => {
    process.env.AI_API_INTERNAL_BASE_URL = "http://ai:8002/v1";
    const response = await POST(new Request("http://localhost/api/studio/analysis", {
      method: "POST",
      headers: { "content-length": String(11 * 1024 * 1024) },
    }));
    expect(response.status).toBe(413);
  });
});
