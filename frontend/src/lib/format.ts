import type { ParameterValue } from "@/api/hooks";

/** Format a number without a useless trailing `.0`. */
export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  if (Number.isInteger(value)) return String(value);
  return String(Number(value.toFixed(6)));
}

/** `12.5 mOhm` - the value and its unit. */
export function formatValue(value: number | null | undefined, unit?: string | null): string {
  if (value === null || value === undefined) return "-";
  const text = formatNumber(value);
  return unit ? `${text} ${unit}` : text;
}

/** `12.5 mOhm (typ)` - the value with the typical/min/max hint. */
export function formatParameterValue(value: ParameterValue): string {
  if (value.value !== null && value.value !== undefined) {
    return formatValue(value.value, value.unit);
  }
  if (value.value_min !== null && value.value_min !== undefined) {
    return `${formatNumber(value.value_min)} ... ${formatNumber(value.value_max)} ${value.unit ?? ""}`.trim();
  }
  if (value.value_text) return value.value_text;
  return "-";
}

/** `Vgs = 10 V, Tj = 25 °C` - the measurement condition of a value. */
export function formatCondition(condition: unknown): string {
  if (!condition || typeof condition !== "object") return "";
  const entries = Object.entries(condition as Record<string, unknown>);
  if (entries.length === 0) return "";
  return entries
    .map(([key, raw]) => {
      const value = raw && typeof raw === "object" ? JSON.stringify(raw) : String(raw);
      return `${key}: ${value}`;
    })
    .join(", ");
}

/** `T1` - a short, readable name of a parameter. */
export function humanizeParam(name: string): string {
  return name
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toISOString().replace("T", " ").slice(0, 19);
}

/** Escape one CSV cell. */
export function csvCell(value: unknown): string {
  const text = value === null || value === undefined ? "" : String(value);
  if (/[",\n;]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

/** Build a CSV document from a header row and a body. */
export function toCsv(header: string[], rows: unknown[][]): string {
  const lines = [header.map(csvCell).join(",")];
  for (const row of rows) {
    lines.push(row.map(csvCell).join(","));
  }
  return lines.join("\n");
}

/** Trigger a browser download of a text file. */
export function downloadTextFile(filename: string, content: string, mime = "text/csv"): void {
  const blob = new Blob([content], { type: `${mime};charset=utf-8;` });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
