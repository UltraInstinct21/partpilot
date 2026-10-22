import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderApp } from "./test-utils";

describe("the compare page", () => {
  it("shows two to four parts side by side", async () => {
    const { user } = renderApp("/compare");

    const checkboxes = await screen.findAllByRole("checkbox");
    expect(checkboxes.length).toBeGreaterThan(1);

    await user.click(checkboxes[0]);
    await user.click(checkboxes[1]);

    expect(await screen.findByText("Side by side")).toBeInTheDocument();

    // One row per parameter, one column per part.
    const headers = screen.getAllByRole("columnheader");
    expect(headers.length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByRole("row").length).toBeGreaterThan(2);
  });
});
