import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { server } from "@/mocks/server";
import { renderApp } from "./test-utils";

describe("the editable filter chips", () => {
  it("runs the search again with the edited filter", async () => {
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
    await user.click(within(chips).getByRole("button", { name: "Edit Family" }));

    const input = await screen.findByLabelText("Family");
    await user.clear(input);
    await user.type(input, "gate_driver");
    await user.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => expect(searchCalls).toBe(2));
    expect(await screen.findByText("IR2110")).toBeInTheDocument();
    expect(screen.queryByText("IRF3205S")).not.toBeInTheDocument();
  });
});
