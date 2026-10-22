import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { LifecycleBadge } from "@/components/lifecycle-badge";

describe("the lifecycle badge", () => {
  it("is green for an active part", () => {
    render(<LifecycleBadge status="active" />);
    const badge = screen.getByText("Active");
    expect(badge.className).toContain("bg-green-100");
    expect(badge).toHaveAttribute("data-lifecycle", "active");
  });

  it("is yellow for an NRND part", () => {
    render(<LifecycleBadge status="nrnd" />);
    const badge = screen.getByText("NRND");
    expect(badge.className).toContain("bg-yellow-100");
  });

  it("is red for an obsolete part", () => {
    render(<LifecycleBadge status="obsolete" />);
    const badge = screen.getByText("Obsolete");
    expect(badge.className).toContain("bg-red-100");
  });

  it("is grey for an unknown part", () => {
    render(<LifecycleBadge status="unknown" />);
    const badge = screen.getByText("Unknown");
    expect(badge.className).toContain("bg-muted");
  });
});
