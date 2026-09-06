import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/image", () => ({ default: function MockImage({ fill, unoptimized, ...props }: React.ImgHTMLAttributes<HTMLImageElement> & { fill?: boolean; unoptimized?: boolean }) { void fill; void unoptimized; return React.createElement("img", props); } }));
import { AdminPatternPreview } from "./admin-pattern-preview";

describe("AdminPatternPreview", () => {
  it("loads through the safe pattern image proxy and reports readiness", () => {
    render(<AdminPatternPreview patternId="pat_001" name="祥云纹" />);
    const image = screen.getByRole("img", { name: "祥云纹审核预览" });
    expect(image.getAttribute("src")).toMatch(/\/patterns\/pat_001\/image$/);
    expect(screen.getByText("图片加载中…")).toBeInTheDocument();
    fireEvent.load(image);
    expect(screen.getByText("图片可用")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /打开档案/ })).toHaveAttribute("href", "/patterns/pat_001");
  });

  it("shows a stable empty state when the proxy has no image", () => {
    render(<AdminPatternPreview patternId="missing" name="待核纹样" />);
    fireEvent.error(screen.getByRole("img", { name: "待核纹样审核预览" }));
    expect(screen.getByText("暂无可预览图片")).toBeInTheDocument();
    expect(screen.getByText("无图")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
