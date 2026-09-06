import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ getPattern: vi.fn() }));
vi.mock("@/lib/catalog-api", () => ({ getPattern: mocks.getPattern }));

import { generateMetadata } from "./page";

describe("pattern detail metadata", () => {
  it("lets the root title template add the site name once", async () => {
    mocks.getPattern.mockResolvedValue({ data: { name: "羊角花纹", meaning: "吉祥" }, source: "live" });
    await expect(generateMetadata({ params: Promise.resolve({ id: "one" }) })).resolves.toMatchObject({ title: "羊角花纹" });
  });

  it("uses a concise missing-pattern title", async () => {
    mocks.getPattern.mockResolvedValue({ data: null, source: "live" });
    await expect(generateMetadata({ params: Promise.resolve({ id: "missing" }) })).resolves.toMatchObject({ title: "纹样未找到" });
  });
});
