import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/mocks/server";
import { renderApp } from "./test-utils";

describe("the correction dialog of the review queue", () => {
  it("validates the value and sends the correction", async () => {
    const decisions: string[] = [];
    server.events.on("request:start", ({ request }) => {
      if (request.method === "POST" && request.url.includes("/api/review/")) {
        decisions.push(request.url);
      }
    });

    const { user } = renderApp("/review");

    const correct = (await screen.findAllByRole("button", { name: /correct/i }))[0];
    await user.click(correct);

    const input = await screen.findByLabelText("Correct value");
    await user.type(input, "not a number");
    await user.click(screen.getByRole("button", { name: /save the correction/i }));

    expect(await screen.findByText("The value must be a number")).toBeInTheDocument();
    expect(decisions.length).toBe(0);

    await user.clear(input);
    await user.type(input, "42");
    await user.click(screen.getByRole("button", { name: /save the correction/i }));

    await waitFor(() => expect(decisions.length).toBe(1));
  });
});
