import type { RiskSeverity, ValueStatus } from "@/api/hooks";

export const STATUS_CLASS: Record<ValueStatus, string> = {
  accepted: "bg-green-100 text-green-800 border-green-300 dark:bg-green-900/40 dark:text-green-200",
  review:
    "bg-yellow-100 text-yellow-800 border-yellow-300 dark:bg-yellow-900/40 dark:text-yellow-200",
  rejected: "bg-red-100 text-red-800 border-red-300 dark:bg-red-900/40 dark:text-red-200",
};

export const STATUS_LABEL: Record<ValueStatus, string> = {
  accepted: "Accepted",
  review: "Review",
  rejected: "Rejected",
};

export const SEVERITY_CLASS: Record<RiskSeverity, string> = {
  info: "bg-muted text-muted-foreground border-border",
  low: "bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-900/40 dark:text-blue-200",
  medium:
    "bg-yellow-100 text-yellow-800 border-yellow-300 dark:bg-yellow-900/40 dark:text-yellow-200",
  high: "bg-orange-100 text-orange-800 border-orange-300 dark:bg-orange-900/40 dark:text-orange-200",
  critical: "bg-red-100 text-red-800 border-red-300 dark:bg-red-900/40 dark:text-red-200",
};

export const SEVERITY_ORDER: RiskSeverity[] = ["info", "low", "medium", "high", "critical"];
