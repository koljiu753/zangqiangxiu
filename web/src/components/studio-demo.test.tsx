import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StudioDemo } from "./studio-demo";

describe("StudioDemo", () => {
  beforeEach(() => {
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:preview") });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  });

  it("shows preview, palette and enriched Top 5 results", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      jobId: "job-1", status: "succeeded", palette: ["#AABBCC"], algorithmVersion: "rgb-v1", warnings: ["模型未配置"],
      similar: [{ assetId: "asset-1", patternId: "pattern-1", label: "候选", name: "万字纹", category: "几何纹", meaning: "吉祥", score: .912 }],
    }), { status: 200 })));
    render(<StudioDemo />);
    fireEvent.change(screen.getByLabelText("选择纹样图片"), { target: { files: [new File(["image"], "sample.png", { type: "image/png" })] } });
    expect(screen.getByAltText("待分析纹样预览")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "开始识别" }));
    await waitFor(() => expect(screen.getByText("万字纹")).toBeInTheDocument());
    expect(screen.getByText("91.2% 相似")).toBeInTheDocument();
    expect(screen.getByText("#AABBCC")).toBeInTheDocument();
    expect(screen.getByText("算法版本：rgb-v1")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看纹样详情" })).toHaveAttribute("href", "/patterns/pattern-1");
  });

  it("offers retry after an analysis error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "AI 暂不可用" }), { status: 502 })));
    render(<StudioDemo />);
    fireEvent.change(screen.getByLabelText("选择纹样图片"), { target: { files: [new File(["x"], "x.png", { type: "image/png" })] } });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "开始识别" }));
    await waitFor(() => expect(screen.getByText("AI 暂不可用")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "重新分析" })).toBeInTheDocument();
  });
});
