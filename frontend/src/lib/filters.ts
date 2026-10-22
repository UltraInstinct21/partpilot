import type { LifecycleStatus, ParameterConstraint, SearchFilter } from "@/api/hooks";

export type FilterChipKind = "field" | "constraint";

export type FilterChip = {
  id: string;
  kind: FilterChipKind;
  /** The field name, e.g. `family` or `rds_on`. */
  field: string;
  /** The operator, e.g. `=`, `in`, `lte`. */
  operator: string;
  /** The value as it is displayed on the chip. */
  value: string;
  constraint?: ParameterConstraint;
  constraintIndex?: number;
};

type FieldMeta = { operator: string; label: string; list?: boolean; boolean?: boolean };

export const FIELD_META: Record<string, FieldMeta> = {
  family: { operator: "=", label: "Family" },
  manufacturer: { operator: "=", label: "Manufacturer" },
  manufacturer_in: { operator: "in", label: "Manufacturer", list: true },
  mpn_contains: { operator: "contains", label: "MPN" },
  package: { operator: "=", label: "Package" },
  package_in: { operator: "in", label: "Package", list: true },
  lifecycle_status: { operator: "in", label: "Lifecycle", list: true },
  in_stock: { operator: "=", label: "In stock", boolean: true },
  text: { operator: "contains", label: "Text" },
};

export const CONSTRAINT_OPERATORS: ParameterConstraint["operator"][] = [
  "lt",
  "lte",
  "gt",
  "gte",
  "eq",
  "between",
];

export function describeConstraint(constraint: ParameterConstraint): string {
  const unit = constraint.unit ? ` ${constraint.unit}` : "";
  switch (constraint.operator) {
    case "lt":
      return `< ${constraint.max ?? "-"}${unit}`;
    case "lte":
      return `≤ ${constraint.max ?? "-"}${unit}`;
    case "gt":
      return `> ${constraint.min ?? "-"}${unit}`;
    case "gte":
      return `≥ ${constraint.min ?? "-"}${unit}`;
    case "eq":
      return `= ${constraint.typ ?? constraint.min ?? constraint.max ?? "-"}${unit}`;
    case "between":
      return `${constraint.min ?? "-"} … ${constraint.max ?? "-"}${unit}`;
    default:
      return "";
  }
}

/** Flatten a `SearchFilter` into the editable chips of the search page. */
export function filterToChips(filter: SearchFilter | null | undefined): FilterChip[] {
  if (!filter) return [];
  const chips: FilterChip[] = [];
  const bag = filter as unknown as Record<string, unknown>;

  for (const [key, meta] of Object.entries(FIELD_META)) {
    const raw = bag[key];
    if (raw === null || raw === undefined) continue;
    if (Array.isArray(raw)) {
      if (raw.length === 0) continue;
      chips.push({
        id: key,
        kind: "field",
        field: key,
        operator: meta.operator,
        value: raw.join(", "),
      });
    } else {
      chips.push({
        id: key,
        kind: "field",
        field: key,
        operator: meta.operator,
        value: String(raw),
      });
    }
  }

  const constraints = filter.parameters ?? [];
  constraints.forEach((constraint, index) => {
    chips.push({
      id: `parameter-${index}-${constraint.name}`,
      kind: "constraint",
      field: constraint.name,
      operator: constraint.operator,
      value: describeConstraint(constraint),
      constraint,
      constraintIndex: index,
    });
  });

  return chips;
}

function splitList(raw: string): string[] {
  return raw
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

/** Remove one chip from the filter and return the new filter. */
export function removeChip(filter: SearchFilter, chip: FilterChip): SearchFilter {
  const next = { ...filter } as SearchFilter & Record<string, unknown>;
  if (chip.kind === "field") {
    delete next[chip.field];
    return next;
  }
  const parameters = [...(filter.parameters ?? [])];
  parameters.splice(chip.constraintIndex ?? -1, 1);
  next.parameters = parameters;
  return next;
}

/** Replace the value of a simple field chip. */
export function updateFieldChip(filter: SearchFilter, chip: FilterChip, raw: string): SearchFilter {
  const next = { ...filter } as SearchFilter & Record<string, unknown>;
  const meta = FIELD_META[chip.field];
  const value = raw.trim();

  switch (chip.field) {
    case "manufacturer_in":
      next.manufacturer_in = splitList(value);
      break;
    case "package_in":
      next.package_in = splitList(value);
      break;
    case "lifecycle_status":
      next.lifecycle_status = splitList(value) as LifecycleStatus[];
      break;
    case "in_stock":
      next.in_stock = value === "true" || value === "1" || value === "yes";
      break;
    case "family":
      next.family = value as SearchFilter["family"];
      break;
    case "manufacturer":
      next.manufacturer = value;
      break;
    case "package":
      next.package = value;
      break;
    case "mpn_contains":
      next.mpn_contains = value;
      break;
    case "text":
      next.text = value;
      break;
    default:
      next[chip.field] = value;
      break;
  }

  if (
    meta?.list &&
    Array.isArray(next[chip.field]) &&
    (next[chip.field] as string[]).length === 0
  ) {
    delete next[chip.field];
  }
  return next;
}

/** Replace a parameter constraint chip. */
export function updateConstraintChip(
  filter: SearchFilter,
  chip: FilterChip,
  constraint: ParameterConstraint,
): SearchFilter {
  const parameters = [...(filter.parameters ?? [])];
  const index = chip.constraintIndex ?? 0;
  if (index < 0 || index >= parameters.length) return filter;
  parameters[index] = constraint;
  return { ...filter, parameters };
}

/** Parse a number that the user typed into a constraint input. */
export function parseNumber(raw: string): number | null {
  const value = Number(raw.trim());
  if (raw.trim() === "" || Number.isNaN(value)) return null;
  return value;
}

/** True when the filter carries no constraint at all. */
export function isFilterEmpty(filter: SearchFilter | null | undefined): boolean {
  if (!filter) return true;
  const bag = filter as unknown as Record<string, unknown>;
  const hasField = Object.entries(FIELD_META).some(([key]) => {
    const raw = bag[key];
    if (raw === null || raw === undefined) return false;
    if (Array.isArray(raw)) return raw.length > 0;
    return true;
  });
  const hasConstraints = (filter.parameters ?? []).length > 0;
  return !hasField && !hasConstraints;
}
