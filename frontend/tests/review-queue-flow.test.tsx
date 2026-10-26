import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderApp } from "./test-utils";

describe("Review queue end-to-end component finalisation flow", () => {
  it("adds parts from the search list, reviews AI tradeoffs, finalizes, and exports BOM", async () => {
    // 1. Start on search page
    const { user } = renderApp("/search");

    // Enter search query to display parts list
    await user.type(screen.getByLabelText("Query"), "mosfet");
    await user.click(screen.getByRole("button", { name: /search/i }));

    // Table rows render with "+ Review" buttons
    const reviewButtons = await screen.findAllByRole("button", { name: /review/i });
    expect(reviewButtons.length).toBeGreaterThan(0);

    // Add first part to Review Queue
    await user.click(reviewButtons[0]);

    // Button updates state to "In Review"
    expect(await screen.findByText("In Review")).toBeInTheDocument();

    // Toolbar shows Review Queue button
    const reviewQueueLink = await screen.findByRole("button", { name: /^review queue \(\d+\)/i });
    expect(reviewQueueLink).toBeInTheDocument();

    // 2. Navigate to Review Queue page
    await user.click(reviewQueueLink);

    // Verify Review Queue header and contents
    expect(await screen.findByRole("heading", { name: /Component Review/i })).toBeInTheDocument();
    expect(screen.getByText("Candidate Components Workspace")).toBeInTheDocument();

    // AI Tradeoff & Finalisation Advisor is active
    expect(screen.getByText("AI Tradeoff & Finalisation Advisor")).toBeInTheDocument();
    expect(await screen.findByText(/Top Pick to Finalize/i)).toBeInTheDocument();

    // 3. Finalize a component
    const finalizeButtons = screen.getAllByRole("button", { name: /finalize/i });
    expect(finalizeButtons.length).toBeGreaterThan(0);
    await user.click(finalizeButtons[0]);

    // 4. Open Export Modal
    const exportBtn = screen.getByRole("button", { name: /export finalised parts/i });
    await user.click(exportBtn);

    // Verify Export Modal options
    expect(await screen.findByText("Export Finalised Bill of Materials")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /download csv/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /download json/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /download report/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /copy tsv/i })).toBeInTheDocument();
  });
});
