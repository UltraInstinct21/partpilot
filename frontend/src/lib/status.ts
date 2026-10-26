import type { RiskSeverity, ValueStatus } from "@/api/hooks";

// Monochrome status tags (rectangular, 4px radius, no colors)
export const STATUS_CLASS: Record<ValueStatus, string> = {
  accepted: "border border-ink/40 text-ink bg-transparent",
  review: "border border-dashed border-ink/60 text-ink bg-transparent",
  rejected: "bg-ink text-haze border border-ink",
};

export const STATUS_LABEL: Record<ValueStatus, string> = {
  accepted: "Accepted",
  review: "Review",
  rejected: "Rejected",
};

// Monochrome BOM risk severity (no colors)
export const SEVERITY_CLASS: Record<RiskSeverity, string> = {
  info: "border border-ink/20 text-ink/60 bg-transparent",
  low: "border border-ink/40 text-ink bg-transparent",
  medium: "border border-dashed border-ink/60 text-ink bg-transparent",
  high: "border-2 border-ink text-ink font-medium bg-transparent",
  critical: "bg-ink text-haze border border-ink font-semibold",
};

export const SEVERITY_ORDER: RiskSeverity[] = ["info", "low", "medium", "high", "critical"];
