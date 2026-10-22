import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderApp } from "./test-utils";

describe("the BOM check page", () => {
  it("uploads a CSV and shows the risks", async () => {
    const { user } = renderApp("/bom");

    const file = new File(["mpn,qty\nIRF3205S,10\nUNKNOWN-1,1\n"], "bom.csv", {
      type: "text/csv",
    });

    await user.upload(screen.getByLabelText("BOM file (CSV)"), file);

    expect(await screen.findByText("not_found")).toBeInTheDocument();
    expect(screen.getByText(/No part matches MPN/)).toBeInTheDocument();
    expect(screen.getAllByText("high").length).toBeGreaterThan(0);
  });
});
