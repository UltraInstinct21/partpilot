import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderApp } from "./test-utils";

describe("the dashboard", () => {
  it("shows the statistics and the charts", async () => {
    const { container } = renderApp("/dashboard");

    expect(await screen.findByText("Parts")).toBeInTheDocument();
    expect(screen.getByText("30")).toBeInTheDocument();
    expect(screen.getByText("86%")).toBeInTheDocument();

    const charts = container.querySelectorAll('[data-slot="chart"]');
    expect(charts.length).toBeGreaterThanOrEqual(3);
  });
});
