import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PatternBrowser } from "./pattern-browser";
import { demoPatterns } from "@/lib/demo-data";

describe("PatternBrowser", () => {
  it("filters patterns by search text", () => {
    render(<PatternBrowser patterns={demoPatterns} />);
    fireEvent.change(screen.getByPlaceholderText("名称、寓意或民族"), { target: { value: "莲花" } });
    expect(screen.getByText("莲花宝相纹")).toBeInTheDocument();
    expect(screen.queryByText("山河牛角纹")).not.toBeInTheDocument();
  });

  it("shows an empty state", () => {
    render(<PatternBrowser patterns={demoPatterns} />);
    fireEvent.change(screen.getByPlaceholderText("名称、寓意或民族"), { target: { value: "不存在的纹样" } });
    expect(screen.getByText("没有匹配的纹样")).toBeInTheDocument();
  });

  it("links a pictured card to its archive detail", () => {
    render(<PatternBrowser patterns={[{ ...demoPatterns[0], imageUrl: "/patterns/demo-cloud/image" }]} />);
    expect(screen.getByRole("link", { name: /祥云瑞气纹/ })).toHaveAttribute("href", "/patterns/demo-cloud");
    expect(screen.getByRole("img", { name: "祥云瑞气纹纹样" })).toHaveAttribute("src", "/patterns/demo-cloud/image");
  });
});
