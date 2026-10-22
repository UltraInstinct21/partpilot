import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConfidenceBadge } from "@/components/confidence-badge";

describe("the confidence badge", () => {
  it("is green for a high confidence", () => {
    render(<ConfidenceBadge confidence={0.92} />);
    const badge = screen.getByText("92%");
    expect(badge.className).toContain("bg-green-100");
    expect(badge).toHaveAttribute("data-confidence", "high");
  });

  it("is yellow for a medium confidence", () => {
    render(<ConfidenceBadge confidence={0.6} />);
    const badge = screen.getByText("60%");
    expect(badge.className).toContain("bg-yellow-100");
    expect(badge).toHaveAttribute("data-confidence", "medium");
  });

  it("is red for a low confidence", () => {
    render(<ConfidenceBadge confidence={0.4} />);
    const badge = screen.getByText("40%");
    expect(badge.className).toContain("bg-red-100");
    expect(badge).toHaveAttribute("data-confidence", "low");
  });
});
