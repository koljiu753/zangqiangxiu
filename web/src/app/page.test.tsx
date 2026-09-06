import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ getPatterns: vi.fn() }));
vi.mock("@/lib/catalog-api", () => ({ getPatterns: mocks.getPatterns }));

import HomePage from "./page";

describe("HomePage", () => {
  beforeEach(() => mocks.getPatterns.mockReset());

  it("shows review guidance instead of an empty featured grid", async () => {
    mocks.getPatterns.mockResolvedValue({ data: [], source: "live" });
    const { container } = render(await HomePage());

    expect(screen.getByRole("status")).toHaveTextContent("资料审核中");
    expect(screen.getByText("公开纹样正在整理")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "前往纹样库查看进度" })).toHaveAttribute("href", "/patterns");
    expect(container.querySelector(".featured-grid")).not.toBeInTheDocument();
  });
});
