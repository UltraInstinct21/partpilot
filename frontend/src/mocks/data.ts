/**
 * Fixture data for the PartPilot mock server.
 *
 * The data is a copy of `contracts/fixtures/**` so the browser mock and the
 * standalone mock API (`make mock-api`) serve the same thing.
 */
import seedParts from "./fixtures/seed_parts.json";
import page01 from "./fixtures/page_01.json";
import page02 from "./fixtures/page_02.json";
import page03 from "./fixtures/page_03.json";
import page04 from "./fixtures/page_04.json";
import page05 from "./fixtures/page_05.json";

export type SeedOffer = {
  distributor: string;
  sku: string | null;
  stock: number | null;
  unit_price: number | null;
  currency: string;
  url: string | null;
};

export type SeedPart = {
  part_id: string;
  mpn: string;
  manufacturer: string;
  family: "mosfet" | "gate_driver";
  package: string | null;
  lifecycle_status: "active" | "nrnd" | "obsolete" | "unknown";
  datasheet_url: string | null;
  description: string | null;
  source_ids: string[];
  offers: SeedOffer[];
  parameters: Record<
    string,
    { value: number | null; unit: string | null; condition: Record<string, unknown> }
  >;
};

export const parts = (seedParts as unknown as { parts: SeedPart[] }).parts;

export const pageSamples = [page01, page02, page03, page04, page05] as Array<{
  source_id: string;
  family: string;
  page: number;
  title: string;
  text: string;
  tables: Array<{ bbox: number[]; rows: string[][] }>;
  is_image_only?: boolean;
}>;

const NOW = "2026-10-01T09:30:00Z";

export function toSummary(part: SeedPart) {
  const keys =
    part.family === "mosfet"
      ? ["vds_max", "id_continuous", "rds_on", "total_gate_charge_qg"]
      : ["supply_voltage_min", "supply_voltage_max", "peak_source_current", "propagation_delay"];
  const key_parameters: Record<string, number | null> = {};
  for (const key of keys) key_parameters[key] = part.parameters[key]?.value ?? null;
  const offers = part.offers ?? [];
  return {
    part_id: part.part_id,
    mpn: part.mpn,
    manufacturer: part.manufacturer,
    family: part.family,
    package: part.package,
    lifecycle_status: part.lifecycle_status,
    datasheet_url: part.datasheet_url,
    description: part.description,
    key_parameters,
    offers_count: offers.length,
    total_stock: offers.reduce((sum, offer) => sum + (offer.stock ?? 0), 0) || null,
    score: null,
  };
}

export function toParameterValues(part: SeedPart) {
  return Object.entries(part.parameters).map(([name, spec]) => ({
    param_id: `param-${part.mpn.toLowerCase()}-${name}`,
    part_id: part.part_id,
    name,
    value: spec.value,
    value_min: null,
    value_typ: spec.value,
    value_max: null,
    unit: spec.unit,
    condition: spec.condition,
    source_id: `api-digikey-${part.mpn.toLowerCase()}`,
    page: 1,
    method: "tier1",
    confidence: spec.value === null ? 0.6 : 0.92,
    status: spec.value === null ? "review" : "accepted",
    raw_text: `${name} = ${spec.value ?? ""} ${spec.unit ?? ""}`.trim(),
    value_text: `${spec.value ?? ""} ${spec.unit ?? ""}`.trim(),
  }));
}

export function findPart(partId: string) {
  return parts.find((p) => p.part_id === partId);
}

/** Deterministic stand-in for the LLM filter builder used by the mock. */
export function guessFilter(query: string) {
  const text = query.toLowerCase();
  const filter: Record<string, unknown> = {};
  if (text.includes("mosfet")) filter.family = "mosfet";
  else if (text.includes("driver")) filter.family = "gate_driver";

  const vds = text.match(/(\d+(?:\.\d+)?)\s*v\b/);
  if (vds) {
    filter.parameters = [
      ...((filter.parameters as unknown[]) ?? []),
      { name: "vds_max", unit: "V", min: null, max: Number(vds[1]), typ: null, operator: "lte" },
    ];
  }
  const rds = text.match(/rds\(?on\)?\s*(?:below|under|<)?\s*(\d+(?:\.\d+)?)\s*(m|milli)?/);
  if (rds) {
    filter.parameters = [
      ...((filter.parameters as unknown[]) ?? []),
      {
        name: "rds_on",
        unit: rds[2] ? "mohm" : "ohm",
        min: null,
        max: Number(rds[1]),
        typ: null,
        operator: "lte",
      },
    ];
  }
  return filter;
}

/**
 * The factor from a datasheet unit to the canonical unit.
 *
 * The seed fixture stores canonical SI base units (see docs/CONTRACTS.md), so
 * a constraint that arrives in a datasheet unit has to be converted before it
 * is compared. The real API does the same in the database layer.
 */
const UNIT_FACTORS: Record<string, number> = {
  mohm: 1e-3,
  kohm: 1e3,
  uohm: 1e-6,
  nC: 1e-9,
  uC: 1e-6,
  pF: 1e-12,
  nF: 1e-9,
  ns: 1e-9,
  us: 1e-6,
  mV: 1e-3,
  mA: 1e-3,
};

export function toCanonical(value: number | null, unit: string | null): number | null {
  if (value === null || !unit) return value;
  const factor = UNIT_FACTORS[unit];
  return factor === undefined ? value : value * factor;
}

export function matchFilter(filter: Record<string, unknown>) {
  let result = [...parts];
  if (filter.family) result = result.filter((p) => p.family === filter.family);
  if (filter.manufacturer) result = result.filter((p) => p.manufacturer === filter.manufacturer);
  if (filter.mpn_contains)
    result = result.filter((p) =>
      p.mpn.toLowerCase().includes(String(filter.mpn_contains).toLowerCase()),
    );
  if (filter.package) result = result.filter((p) => p.package === filter.package);
  const lifecycle = filter.lifecycle_status as string[] | undefined;
  if (lifecycle?.length) result = result.filter((p) => lifecycle.includes(p.lifecycle_status));
  if (filter.text) {
    const needle = String(filter.text).toLowerCase();
    result = result.filter(
      (p) =>
        p.mpn.toLowerCase().includes(needle) ||
        p.manufacturer.toLowerCase().includes(needle) ||
        (p.description ?? "").toLowerCase().includes(needle),
    );
  }
  const constraints = (filter.parameters ?? []) as Array<{
    name: string;
    unit?: string | null;
    min?: number | null;
    max?: number | null;
  }>;
  for (const constraint of constraints) {
    const lower = toCanonical(constraint.min ?? null, constraint.unit ?? null);
    const upper = toCanonical(constraint.max ?? null, constraint.unit ?? null);
    result = result.filter((p) => {
      const spec = p.parameters[constraint.name];
      if (!spec || spec.value === null) return false;
      const value = Number(spec.value);
      if (lower !== null && value < lower) return false;
      if (upper !== null && value > upper) return false;
      return true;
    });
  }
  return result;
}

export function buildStats() {
  const byFamily: Record<string, number> = {};
  const byLifecycle: Record<string, number> = {};
  const byManufacturer: Record<string, number> = {};
  for (const part of parts) {
    byFamily[part.family] = (byFamily[part.family] ?? 0) + 1;
    byLifecycle[part.lifecycle_status] = (byLifecycle[part.lifecycle_status] ?? 0) + 1;
    byManufacturer[part.manufacturer] = (byManufacturer[part.manufacturer] ?? 0) + 1;
  }
  const totalParams = parts.reduce((sum, p) => sum + Object.keys(p.parameters).length, 0);
  return {
    parts_total: parts.length,
    parts_by_family: byFamily,
    parts_by_lifecycle: byLifecycle,
    parts_by_manufacturer: byManufacturer,
    parameters_total: totalParams,
    values_by_status: { accepted: Math.round(totalParams * 0.86), review: 42, rejected: 9 },
    values_by_method: { tier1: Math.round(totalParams * 0.8), tier2: 38, tier3: 5, api: 20 },
    review_pending: 42,
    sources_total: parts.length * 2,
    coverage_pct: 86,
    mean_confidence: 0.88,
    llm_calls_total: 128,
    llm_tokens_in: 412000,
    llm_tokens_out: 96000,
    llm_cost_total: 3.42,
    avg_cost_per_datasheet: 0.11,
    accuracy: { mosfet: 0.91, gate_driver: 0.84 },
    generated_at: NOW,
  };
}

export function buildReviewQueue() {
  const items: Record<string, unknown>[] = [];
  for (const part of parts.slice(0, 6)) {
    for (const value of toParameterValues(part)) {
      if (value.status !== "review") continue;
      items.push({
        ...value,
        mpn: part.mpn,
        manufacturer: part.manufacturer,
        family: part.family,
        confidence: 0.62,
        reasons: ["confidence below the review threshold"],
        created_at: NOW,
      });
    }
  }
  return items;
}

export const MOCK_NOW = NOW;
