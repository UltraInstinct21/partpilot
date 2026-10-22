import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { server } from "@/mocks/server";
import { renderApp } from "./test-utils";

describe("the search page", () => {
  it("shows the parts of the mock and the filter chips", async () => {
    const { user } = renderApp("/");

    await user.type(screen.getByLabelText("Query"), "mosfet 100V");
    await user.click(screen.getByRole("button", { name: /search/i }));

    expect(await screen.findByText("IRF3205S")).toBeInTheDocument();

    const chips = await screen.findByTestId("filter-chips");
    expect(within(chips).getByText("Family")).toBeInTheDocument();
    expect(within(chips).getByText("mosfet")).toBeInTheDocument();
    expect(within(chips).getByText("vds_max")).toBeInTheDocument();
  });

  it("runs the search again when a chip is removed", async () => {
    let searchCalls = 0;
    server.events.on("request:start", ({ request }) => {
      if (request.method === "POST" && request.url.endsWith("/api/search")) {
        searchCalls += 1;
      }
    });

    const { user } = renderApp("/");
    await user.type(screen.getByLabelText("Query"), "mosfet");
    await user.click(screen.getByRole("button", { name: /search/i }));

    expect(await screen.findByText("IRF3205S")).toBeInTheDocument();
    await waitFor(() => expect(searchCalls).toBe(1));

    const chips = await screen.findByTestId("filter-chips");
    await user.click(within(chips).getByRole("button", { name: "Remove Family" }));

    await waitFor(() => expect(searchCalls).toBe(2));
    expect(await screen.findByText("IR2110")).toBeInTheDocument();

    const updated = await screen.findByTestId("filter-chips");
    expect(within(updated).queryByText("Family")).not.toBeInTheDocument();
  });
});
