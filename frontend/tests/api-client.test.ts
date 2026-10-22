import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { ApiError, apiGet, apiPost, apiUpload } from "@/api/client";
import { server } from "@/mocks/server";

describe("the API client", () => {
  it("reads a JSON resource", async () => {
    server.use(http.get("*/api/parts/x", () => HttpResponse.json({ part_id: "x" })));
    await expect(apiGet<{ part_id: string }>("/api/parts/x")).resolves.toEqual({ part_id: "x" });
  });

  it("throws a typed error with the detail of the backend", async () => {
    server.use(
      http.get("*/api/parts/x", () =>
        HttpResponse.json({ detail: "part x not found" }, { status: 404 }),
      ),
    );

    await expect(apiGet("/api/parts/x")).rejects.toBeInstanceOf(ApiError);
    await expect(apiGet("/api/parts/x")).rejects.toThrow("part x not found");
  });

  it("sends the body of a POST request", async () => {
    let body: unknown = null;
    server.use(
      http.post("*/api/search", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ total: 0 });
      }),
    );

    await apiPost("/api/search", { query: "mosfet" });
    expect(body).toEqual({ query: "mosfet" });
  });

  it("uploads a file as multipart form data", async () => {
    let received = "";
    server.use(
      http.post("*/api/bom/check", async ({ request }) => {
        const form = await request.formData();
        const file = form.get("file");
        received = file instanceof File ? await file.text() : "";
        return HttpResponse.json({ risk_count: 0 });
      }),
    );

    const file = new File(["mpn\nIRF3205S\n"], "bom.csv", { type: "text/csv" });
    await apiUpload("/api/bom/check", file);
    expect(received).toContain("IRF3205S");
  });
});
