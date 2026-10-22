import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { delay } from "msw";
import { screen } from "@testing-library/react";
import { server } from "@/mocks/server";
import { renderApp } from "./test-utils";

describe("the loading state", () => {
  it("shows a skeleton while the request is pending", async () => {
    server.use(
      http.get("*/api/stats", async () => {
        await delay(200);
        return HttpResponse.json({ parts_total: 1 });
      }),
    );

    renderApp("/dashboard");

    expect(screen.getByTestId("page-skeleton")).toBeInTheDocument();
    expect(await screen.findByText("Parts")).toBeInTheDocument();
    expect(screen.queryByTestId("page-skeleton")).not.toBeInTheDocument();
  });
});
