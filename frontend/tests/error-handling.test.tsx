import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { screen } from "@testing-library/react";
import { server } from "@/mocks/server";
import { renderApp } from "./test-utils";

describe("the error handling", () => {
  it("shows an error toast when a request fails", async () => {
    server.use(
      http.get("*/api/stats", () =>
        HttpResponse.json({ detail: "The statistics are not available." }, { status: 500 }),
      ),
    );

    renderApp("/dashboard");

    expect((await screen.findAllByText("The statistics are not available.")).length).toBeGreaterThan(0);
  });

  it("shows an inline error state when a request fails", async () => {
    server.use(
      http.get("*/api/parts/mosfet-irf3205s", () =>
        HttpResponse.json({ detail: "The part is not available." }, { status: 500 }),
      ),
    );

    renderApp("/parts/mosfet-irf3205s");

    expect((await screen.findAllByRole("alert")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("The part is not available.").length).toBeGreaterThan(0);
  });
});
