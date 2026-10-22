/**
 * MSW handlers for the PartPilot API.
 *
 * These mirror `backend/tools/mock_api.py` exactly. The frontend never calls a
 * distributor API or an LLM directly (NFR-07); everything comes from here or
 * from the real backend through the same paths.
 */
import { http, HttpResponse } from "msw";
import {
  buildReviewQueue,
  buildStats,
  findPart,
  guessFilter,
  matchFilter,
  pageSamples,
  parts as allParts,
  toParameterValues,
  toSummary,
} from "./data";

const API = "*/api";

export const handlers = [
  http.get(`${API}/parts`, ({ request }) => {
    const url = new URL(request.url);
    const filter: Record<string, unknown> = {};
    const family = url.searchParams.get("family");
    const manufacturer = url.searchParams.get("manufacturer");
    const pkg = url.searchParams.get("package");
    const lifecycle = url.searchParams.get("lifecycle_status");
    const q = url.searchParams.get("q");
    if (family) filter.family = family;
    if (manufacturer) filter.manufacturer = manufacturer;
    if (pkg) filter.package = pkg;
    if (lifecycle) filter.lifecycle_status = lifecycle.split(",").map((s) => s.trim());
    if (q) filter.text = q;

    const limit = Number(url.searchParams.get("limit") ?? 50);
    const offset = Number(url.searchParams.get("offset") ?? 0);
    const matched = matchFilter(filter);
    return HttpResponse.json({
      query: q,
      filter,
      results: matched.slice(offset, offset + limit).map(toSummary),
      total: matched.length,
      limit,
      offset,
      took_ms: 4,
      filter_explanation: "Fixture backed mock result.",
      llm_used: false,
    });
  }),

  http.post(`${API}/search`, async ({ request }) => {
    const payload = (await request.json()) as {
      query: string;
      filter?: Record<string, unknown>;
      limit?: number;
      offset?: number;
    };
    const filter = payload.filter ?? guessFilter(payload.query);
    const limit = payload.limit ?? 50;
    const offset = payload.offset ?? 0;
    const matched = matchFilter(filter);
    return HttpResponse.json({
      query: payload.query,
      filter,
      results: matched.slice(offset, offset + limit).map(toSummary),
      total: matched.length,
      limit,
      offset,
      took_ms: 7,
      filter_explanation: `Mock filter for '${payload.query}'.`,
      llm_used: false,
    });
  }),

  http.get(`${API}/parts/:partId`, ({ params }) => {
    const part = findPart(String(params.partId));
    if (!part) {
      return HttpResponse.json({ detail: `part ${params.partId} not found` }, { status: 404 });
    }
    const offers = (part.offers ?? []).map((offer) => ({
      part_id: part.part_id,
      distributor: offer.distributor,
      sku: offer.sku,
      stock: offer.stock,
      unit_price: offer.unit_price,
      currency: offer.currency,
      price_breaks: [{ quantity: 1, price: offer.unit_price }],
      fetched_at: "2026-10-01T09:30:00Z",
      url: offer.url,
    }));
    return HttpResponse.json({
      ...part,
      parameters: toParameterValues(part),
      offers,
      updated_at: "2026-10-01T09:30:00Z",
    });
  }),

  http.get(`${API}/parts/:partId/sources/:paramId`, ({ params }) => {
    const part = findPart(String(params.partId));
    if (!part) {
      return HttpResponse.json({ detail: `part ${params.partId} not found` }, { status: 404 });
    }
    const value = toParameterValues(part).find((v) => v.param_id === params.paramId);
    if (!value) {
      return HttpResponse.json({ detail: `param ${params.paramId} not found` }, { status: 404 });
    }
    return HttpResponse.json({
      value,
      source: {
        source_id: value.source_id,
        url: `https://example.invalid/api/${part.mpn}`,
        type: "api",
        fetched_at: "2026-10-01T09:30:00Z",
        file_hash: null,
        distributor: "DigiKey",
      },
      page_url: `/api/sources/${value.source_id}/page/${value.page}`,
      page_text: null,
    });
  }),

  http.get(`${API}/sources/:sourceId/page/:n`, ({ params, request }) => {
    const format = new URL(request.url).searchParams.get("format") ?? "meta";
    const sourceId = String(params.sourceId);
    const page = Number(params.n);
    const sample = pageSamples.find((s) => s.source_id === sourceId);
    if (!sample) {
      return HttpResponse.json({ detail: `source ${sourceId} not found` }, { status: 404 });
    }
    if (format === "image") {
      return new HttpResponse(new Uint8Array(), { headers: { "Content-Type": "image/png" } });
    }
    return HttpResponse.json({
      source_id: sourceId,
      page,
      width: 595,
      height: 842,
      text: sample.text,
      image_url: `/api/sources/${sourceId}/page/${page}?format=image`,
      is_image_only: Boolean(sample.is_image_only),
    });
  }),

  http.get(`${API}/parts/:partId/alternatives`, ({ params, request }) => {
    const part = findPart(String(params.partId));
    if (!part) {
      return HttpResponse.json({ detail: `part ${params.partId} not found` }, { status: 404 });
    }
    const url = new URL(request.url);
    const limit = Number(url.searchParams.get("limit") ?? 10);
    const all = allParts.filter((p) => p.family === part.family && p.part_id !== part.part_id);
    const same = all.filter((p) => p.package === part.package);
    const candidates = (same.length > 0 ? same : all).slice(0, limit);
    return HttpResponse.json(
      candidates.map((candidate, index) => ({
        part: toSummary(candidate),
        score: Number((1 - index * 0.1).toFixed(3)),
        rank: index + 1,
        reason: "Lower Rds(on) and lower total gate charge.",
        rejected: false,
        rejection_reason: null,
        differences: {
          rds_on: {
            reference: part.parameters.rds_on?.value ?? null,
            candidate: candidate.parameters.rds_on?.value ?? null,
          },
        },
      })),
    );
  }),

  http.get(`${API}/review`, () => HttpResponse.json(buildReviewQueue())),

  http.post(`${API}/review/:paramId`, async ({ params, request }) => {
    const payload = (await request.json()) as { action?: "accept" | "correct" | "reject" };
    const action = payload.action ?? "accept";
    const status = action === "reject" ? "rejected" : "accepted";
    return HttpResponse.json({
      param_id: String(params.paramId),
      status,
      message: `Value ${action}ed.`,
      item: null,
    });
  }),

  http.post(`${API}/bom/check`, async ({ request }) => {
    const contentType = request.headers.get("content-type") ?? "";
    let text = "";
    let filename: string | null = null;
    if (contentType.includes("multipart/form-data")) {
      const form = await request.formData();
      const file = form.get("file");
      if (file && typeof file !== "string") {
        filename = (file as File).name;
        text = await (file as File).text();
      }
    } else {
      const payload = (await request.json()) as { content?: string; filename?: string };
      text = payload.content ?? "";
      filename = payload.filename ?? null;
    }
    return HttpResponse.json(buildBomResponse(text, filename));
  }),

  http.post(`${API}/jobs/extract`, async ({ request }) => {
    const payload = (await request.json().catch(() => ({}))) as { part_id?: string };
    return HttpResponse.json(
      {
        job_id: "job-0001",
        kind: "extract",
        state: "queued",
        progress: 0,
        total: 1,
        message: "Queued.",
        part_id: payload.part_id ?? null,
        source_id: null,
        result: null,
        error: null,
        created_at: "2026-10-01T09:30:00Z",
        updated_at: "2026-10-01T09:30:00Z",
      },
      { status: 202 },
    );
  }),

  http.get(`${API}/jobs/:jobId`, ({ params }) =>
    HttpResponse.json({
      job_id: String(params.jobId),
      kind: "extract",
      state: "completed",
      progress: 1,
      total: 1,
      message: "Done.",
      part_id: null,
      source_id: null,
      result: {},
      error: null,
      created_at: "2026-10-01T09:30:00Z",
      updated_at: "2026-10-01T09:30:00Z",
    }),
  ),

  http.get(`${API}/stats`, () => HttpResponse.json(buildStats())),
];

/* ------------------------------------------------------------------ */
/* helpers                                                             */
/* ------------------------------------------------------------------ */

function buildBomResponse(text: string, filename: string | null) {
  const lines = text.split(/\r?\n/).filter((line) => line.trim().length > 0);
  if (lines.length === 0) {
    return {
      filename,
      total_lines: 0,
      matched_lines: 0,
      unmatched_lines: 0,
      risk_count: 0,
      highest_severity: null,
      lines: [],
      risks: [],
      took_ms: 2,
    };
  }
  const header = lines[0].split(/[,;\t]/).map((h) => h.trim().toLowerCase());
  const mpnIndex = Math.max(
    0,
    header.findIndex((h) => ["mpn", "part number", "partnumber", "mfr part number"].includes(h)),
  );
  const qtyIndex = header.findIndex((h) => ["qty", "quantity", "quantity ordered"].includes(h));
  const mfrIndex = header.findIndex((h) => ["manufacturer", "mfr", "mfr name"].includes(h));

  const outLines: Record<string, unknown>[] = [];
  const risks: Record<string, unknown>[] = [];
  let matched = 0;
  lines.slice(1).forEach((row, index) => {
    const cells = row.split(/[,;\t]/).map((c) => c.trim());
    const mpn = cells[mpnIndex] ?? cells[0] ?? "";
    const quantity = qtyIndex >= 0 && cells[qtyIndex] ? Number(cells[qtyIndex]) || 1 : 1;
    const manufacturer = mfrIndex >= 0 ? cells[mfrIndex] : undefined;
    const part = allParts.find(
      (p) =>
        p.mpn.toLowerCase() === mpn.toLowerCase() &&
        (!manufacturer || p.manufacturer.toLowerCase().includes(manufacturer.toLowerCase())),
    );
    const lineRisks: Record<string, unknown>[] = [];
    if (!part) {
      lineRisks.push({
        code: "not_found",
        severity: "high",
        message: `No part matches MPN '${mpn}'.`,
        part_id: null,
        mpn,
        suggestion: "Check the manufacturer part number.",
      });
    } else {
      matched += 1;
      if (part.lifecycle_status === "obsolete") {
        lineRisks.push({
          code: "obsolete",
          severity: "critical",
          message: `${mpn} is obsolete.`,
          part_id: part.part_id,
          mpn,
          suggestion: "Use the alternatives list.",
        });
      } else if (part.lifecycle_status === "nrnd") {
        lineRisks.push({
          code: "nrnd",
          severity: "medium",
          message: `${mpn} is NRND (not recommended for new designs).`,
          part_id: part.part_id,
          mpn,
          suggestion: "Plan a migration.",
        });
      }
      if (part.lifecycle_status !== "active") {
        lineRisks.push({
          code: "single_source",
          severity: "low",
          message: `${mpn} is only offered by one distributor in the cache.`,
          part_id: part.part_id,
          mpn,
          suggestion: "Qualify a second source.",
        });
      }
    }
    risks.push(...lineRisks);
    outLines.push({
      line_number: index + 2,
      mpn,
      quantity,
      manufacturer: manufacturer ?? null,
      matched_part_id: part?.part_id ?? null,
      matched: Boolean(part),
      risks: lineRisks,
    });
  });

  const order = ["info", "low", "medium", "high", "critical"];
  const severities = risks.map((r) => String(r.severity));
  const highest = severities.length
    ? severities.reduce((a, b) => (order.indexOf(a) >= order.indexOf(b) ? a : b))
    : null;
  return {
    filename,
    total_lines: outLines.length,
    matched_lines: matched,
    unmatched_lines: outLines.length - matched,
    risk_count: risks.length,
    highest_severity: highest,
    lines: outLines,
    risks,
    took_ms: 3,
  };
}
