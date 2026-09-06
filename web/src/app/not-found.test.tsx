import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import NotFound, { metadata } from "./not-found";
import PatternNotFound, { metadata as patternMetadata } from "./patterns/[id]/not-found";

describe("not found pages", () => {
  it("renders the global Chinese recovery page inside a main landmark", () => {
    const { container } = render(<NotFound />);
    expect(container.querySelector("main")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "这个页面不存在" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "返回纹样库" })).toHaveAttribute("href", "/patterns");
    expect(screen.getByRole("link", { name: "返回首页" })).toHaveAttribute("href", "/");
    expect(metadata.title).toBe("页面未找到");
  });

  it("renders pattern-specific guidance without duplicating the site title", () => {
    render(<PatternNotFound />);
    expect(screen.getByRole("heading", { name: "没有找到这个纹样" })).toBeInTheDocument();
    expect(patternMetadata.title).toBe("纹样未找到");
  });
});
