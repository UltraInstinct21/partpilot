import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/mocks/server";
import { renderApp } from "./test-utils";

describe("the redone review queue", () => {
  it("allows reviewing candidate components and viewing AI tradeoffs and recommendations", async () => {
    const { user } = renderApp("/review");

    // Initially when empty, shows load sample candidates
    const loadSampleBtn = await screen.findByRole("button", { name: /load sample candidates/i });
    expect(loadSampleBtn).toBeInTheDocument();
    await user.click(loadSampleBtn);

    // After loading candidates, components and AI advisor appear
    const irfItems = await screen.findAllByText("IRF3205S");
    expect(irfItems.length).toBeGreaterThan(0);
    expect(await screen.findByText("AI Tradeoff & Finalisation Advisor")).toBeInTheDocument();

    // Verify AI Tradeoffs are evaluated
    expect(await screen.findByText(/Conduction Loss vs Switching Loss/i)).toBeInTheDocument();

    // Verify finalize button works
    const finalizeButtons = screen.getAllByRole("button", { name: /finalize/i });
    expect(finalizeButtons.length).toBeGreaterThan(0);
    await user.click(finalizeButtons[0]);

    // Verify export button opens export modal
    const exportBtn = screen.getByRole("button", { name: /export finalised parts/i });
    await user.click(exportBtn);

    expect(await screen.findByText("Export Finalised Bill of Materials")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /download csv/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /download json/i })).toBeInTheDocument();
  });

  it("lists extraction QA values and accepts a decision when on extraction tab", async () => {
    const decisions: string[] = [];
    server.events.on("request:start", ({ request }) => {
      if (
        request.method === "POST" &&
        request.url.includes("/api/review/") &&
        !request.url.includes("advisory") &&
        !request.url.includes("analyze")
      ) {
        decisions.push(request.url);
      }
    });

    const { user } = renderApp("/review?tab=extraction");

    const irfExtraction = await screen.findAllByText("IRF3205S");
    expect(irfExtraction.length).toBeGreaterThan(0);
    const acceptBtns = await screen.findAllByRole("button", { name: /accept/i });
    expect(acceptBtns.length).toBeGreaterThan(0);
    expect(screen.getAllByText(/confidence below the review threshold/).length).toBeGreaterThan(0);

    await user.click(acceptBtns[0]);
    await waitFor(() => expect(decisions.length).toBe(1));
    expect(decisions[0]).toContain("/api/review/");
  });
});
