import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/mocks/server";
import { renderApp } from "./test-utils";

describe("the review queue", () => {
  it("lists the values that wait for a decision", async () => {
    renderApp("/review");

    expect(await screen.findByText("IRF3205S")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /accept/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/confidence below the review threshold/).length).toBeGreaterThan(0);
  });

  it("sends the decision when the accept button is pressed", async () => {
    const decisions: string[] = [];
    server.events.on("request:start", ({ request }) => {
      if (request.method === "POST" && request.url.includes("/api/review/")) {
        decisions.push(request.url);
      }
    });

    const { user } = renderApp("/review");

    const accept = (await screen.findAllByRole("button", { name: /accept/i }))[0];
    await user.click(accept);

    await waitFor(() => expect(decisions.length).toBe(1));
    expect(decisions[0]).toContain("/api/review/");
  });
});
