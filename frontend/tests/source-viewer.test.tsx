import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderApp } from "./test-utils";

describe("the source viewer", () => {
  it("opens as a side panel next to the value and does not crash", async () => {
    const { user } = renderApp("/parts/mosfet-irf3205s");

    const viewSource = (await screen.findAllByRole("button", { name: "View source" }))[0];
    await user.click(viewSource);

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(screen.getByText(/Source of/)).toBeInTheDocument();

    // The value and its provenance are shown.
    expect(screen.getByText("0.012 ohm")).toBeInTheDocument();
    expect(screen.getByText("https://example.invalid/api/IRF3205S")).toBeInTheDocument();

    // The datasheet page section is rendered. The mock has no rendered page for
    // this source, so the panel shows a message instead of crashing.
    expect(screen.getByText(/Datasheet page 1/)).toBeInTheDocument();
  });
});
