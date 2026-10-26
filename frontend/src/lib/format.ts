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

/** Parameter electrical symbols and scientific designations. */
export const PARAM_SYMBOLS: Record<string, { symbol: string; label: string; category: string }> = {
  vds_max: {
    symbol: "V(BR)DSS",
    label: "Drain-Source Breakdown Voltage",
    category: "Maximum Ratings",
  },
  id_continuous: { symbol: "ID", label: "Continuous Drain Current", category: "Maximum Ratings" },
  vgs_max: { symbol: "VGS(max)", label: "Gate-Source Voltage Limit", category: "Maximum Ratings" },
  max_junction_temp: {
    symbol: "Tj(max)",
    label: "Max Operating Junction Temp",
    category: "Maximum Ratings",
  },
  rds_on: {
    symbol: "RDS(on)",
    label: "Static Drain-Source On-Resistance",
    category: "Static Characteristics",
  },
  vgs_threshold: {
    symbol: "VGS(th)",
    label: "Gate Threshold Voltage",
    category: "Static Characteristics",
  },
  total_gate_charge_qg: {
    symbol: "Qg",
    label: "Total Gate Charge",
    category: "Dynamic Characteristics",
  },
  gate_drain_charge_qgd: {
    symbol: "Qgd",
    label: "Gate-Drain Miller Charge",
    category: "Dynamic Characteristics",
  },
  input_capacitance_ciss: {
    symbol: "Ciss",
    label: "Input Capacitance",
    category: "Dynamic Characteristics",
  },
  output_capacitance_coss: {
    symbol: "Coss",
    label: "Output Capacitance",
    category: "Dynamic Characteristics",
  },
  reverse_recovery_qrr: {
    symbol: "Qrr",
    label: "Body Diode Reverse Recovery",
    category: "Dynamic Characteristics",
  },
  thermal_resistance: {
    symbol: "RthJC",
    label: "Thermal Resistance Junction-to-Case",
    category: "Thermal & Mechanical",
  },
  package: { symbol: "PKG", label: "Package Footprint Outline", category: "Thermal & Mechanical" },

  // Gate driver parameters
  supply_voltage_min: {
    symbol: "VCC(min)",
    label: "Minimum Supply Voltage",
    category: "Operating Conditions",
  },
  supply_voltage_max: {
    symbol: "VCC(max)",
    label: "Maximum Supply Voltage",
    category: "Operating Conditions",
  },
  peak_source_current: {
    symbol: "IO+",
    label: "Peak Output Source Current",
    category: "Output Stage",
  },
  peak_sink_current: { symbol: "IO-", label: "Peak Output Sink Current", category: "Output Stage" },
  propagation_delay: {
    symbol: "tpd",
    label: "Propagation Delay",
    category: "Switching Characteristics",
  },
  rise_time: { symbol: "tr", label: "Output Rise Time", category: "Switching Characteristics" },
  fall_time: { symbol: "tf", label: "Output Fall Time", category: "Switching Characteristics" },
  channel_count: {
    symbol: "Channels",
    label: "Independent Gate Driver Channels",
    category: "Architecture",
  },
};

/** Engineering SI scaled display for electrical parameters. */
export function formatEngineeringUnits(name: string, value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  if (name === "rds_on") {
    if (value < 1) {
      return `${(value * 1000).toFixed(1)} mΩ`;
    }
    return `${value.toFixed(2)} Ω`;
  }
  if (name.includes("charge") || name === "reverse_recovery_qrr") {
    // Value in Coulombs -> nC
    return `${(value * 1e9).toFixed(1)} nC`;
  }
  if (name.includes("capacitance")) {
    // Value in Farads -> pF or nF
    if (value < 1e-9) {
      return `${(value * 1e12).toFixed(0)} pF`;
    }
    return `${(value * 1e9).toFixed(2)} nF`;
  }
  if (name === "propagation_delay" || name === "rise_time" || name === "fall_time") {
    // Seconds to ns
    if (value < 1e-6) {
      return `${(value * 1e9).toFixed(0)} ns`;
    }
    return `${(value * 1e6).toFixed(1)} µs`;
  }
  if (name.includes("voltage") || name.includes("vds") || name.includes("vgs")) {
    return `${value} V`;
  }
  if (name.includes("current") || name === "id_continuous") {
    return `${value} A`;
  }
  if (name === "max_junction_temp") {
    return `${value} °C`;
  }
  if (name === "thermal_resistance") {
    return `${value} °C/W`;
  }
  return String(value);
}

/** Calculate Figure of Merit: RDS(on) * Qg in mOhm * nC. */
export function calculateFOM(rdsOnOhm?: number | null, qgCoulombs?: number | null): number | null {
  if (!rdsOnOhm || !qgCoulombs) return null;
  const rdsMilliOhm = rdsOnOhm * 1000;
  const qgNanoCoulombs = qgCoulombs * 1e9;
  return Math.round(rdsMilliOhm * qgNanoCoulombs);
}

/** Format distributor name nicely. */
export function formatDistributorName(distributor: string): string {
  const lower = distributor.toLowerCase();
  if (lower.includes("element14")) return "element14 India";
  if (lower.includes("robu")) return "Robu.in (India)";
  if (lower.includes("evelta")) return "Evelta (India)";
  if (lower.includes("digikey")) return "DigiKey";
  if (lower.includes("mouser")) return "Mouser";
  if (lower.includes("nexar") || lower.includes("octopart")) return "Nexar";
  return distributor.charAt(0).toUpperCase() + distributor.slice(1);
}

/** Format currency price with appropriate regional symbol. */
export function formatCurrencyPrice(
  price: number | null | undefined,
  currency: string = "USD",
): string {
  if (price === null || price === undefined) return "-";
  const curr = (currency || "USD").toUpperCase();
  if (curr === "INR") {
    return `₹${price.toFixed(2)}`;
  }
  if (curr === "EUR") {
    return `€${price.toFixed(2)}`;
  }
  if (curr === "GBP") {
    return `£${price.toFixed(2)}`;
  }
  return `$${price.toFixed(2)}`;
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

/** Build a CSV document from a header row and a body, or from a list of records. */
export function toCsv(
  headerOrRows: string[] | Record<string, unknown>[],
  rows?: unknown[][],
): string {
  if (rows !== undefined && Array.isArray(headerOrRows)) {
    const lines = [(headerOrRows as string[]).map(csvCell).join(",")];
    for (const row of rows) {
      lines.push(row.map(csvCell).join(","));
    }
    return lines.join("\n");
  }
  const objRows = headerOrRows as Record<string, unknown>[];
  if (!objRows || objRows.length === 0) return "";
  const header = Object.keys(objRows[0] ?? {});
  const lines = [header.map(csvCell).join(",")];
  for (const row of objRows) {
    lines.push(header.map((key) => csvCell(row[key])).join(","));
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
