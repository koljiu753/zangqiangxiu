import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DesignWorkbench } from "./design-workbench";

describe("DesignWorkbench", () => {
  it("updates the composed preview when choices change", () => {
    render(<DesignWorkbench />);
    fireEvent.click(screen.getByRole("button", { name: "雪山晨光" }));
    fireEvent.click(screen.getByRole("button", { name: "羊角守护" }));
    fireEvent.click(screen.getByRole("button", { name: "帆布包" }));
    expect(screen.getByText("羊角守护 · 雪山晨光")).toBeInTheDocument();
    expect(screen.getByText("应用：帆布包")).toBeInTheDocument();
  });
});
