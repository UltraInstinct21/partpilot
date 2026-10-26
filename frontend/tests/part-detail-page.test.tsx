import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderApp } from "./test-utils";

describe("the part detail page", () => {
  it("shows every value with its unit, condition and confidence", async () => {
    renderApp("/parts/mosfet-irf3205s");

    expect(await screen.findByRole("heading", { name: "IRF3205S" })).toBeInTheDocument();

    expect(await screen.findByText("Rds On")).toBeInTheDocument();
    expect(screen.getByText("0.012 ohm")).toBeInTheDocument();
    expect(screen.getAllByText("ohm").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Vgs: 10 V/).length).toBeGreaterThan(0);

    // The lifecycle badge of the part (FR-15).
    expect(screen.getByText("Active")).toBeInTheDocument();

    // The confidence badge of a value.
    const confidences = document.querySelectorAll("[data-confidence]");
    expect(confidences.length).toBeGreaterThan(0);
  });

  it("starts an extraction job and shows its state", async () => {
    const { user } = renderApp("/parts/mosfet-irf3205s");

    const start = await screen.findByRole("button", { name: /start extraction/i });
    await user.click(start);

    expect(await screen.findByText(/Job job-0001/)).toBeInTheDocument();
  });

  it("provides an option to see the datasheet in the site and switches to the datasheet viewer tab", async () => {
    const { user } = renderApp("/parts/mosfet-irf3205s");

    // Option in action buttons to view datasheet in the site
    const viewDatasheetBtn = await screen.findByRole("button", { name: /view datasheet in site/i });
    expect(viewDatasheetBtn).toBeInTheDocument();

    // Click "View datasheet in site"
    await user.click(viewDatasheetBtn);

    // Datasheet viewer tab is displayed
    expect(await screen.findByText(/IRF3205S Technical Datasheet/i)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Datasheet" })).toHaveAttribute("data-state", "active");

    // Interactive Viewer and Full PDF Document controls are available
    expect(screen.getByRole("button", { name: "Interactive Viewer" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Full PDF Document" })).toBeInTheDocument();
  });
});
