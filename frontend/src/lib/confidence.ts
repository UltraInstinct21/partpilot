export type ConfidenceLevel = "high" | "medium" | "low" | "unknown";

/**
 * The confidence bands are the ones of the project plan (section 6.2):
 * green >= 0.75, yellow >= 0.5, red < 0.5.
 */
export function confidenceLevel(confidence: number | null | undefined): ConfidenceLevel {
  if (confidence === null || confidence === undefined || Number.isNaN(confidence)) {
    return "unknown";
  }
  if (confidence >= 0.75) return "high";
  if (confidence >= 0.5) return "medium";
  return "low";
}

export const CONFIDENCE_CLASS: Record<ConfidenceLevel, string> = {
  high: "bg-green-100 text-green-800 border-green-300 dark:bg-green-900/40 dark:text-green-200",
  medium:
    "bg-yellow-100 text-yellow-800 border-yellow-300 dark:bg-yellow-900/40 dark:text-yellow-200",
  low: "bg-red-100 text-red-800 border-red-300 dark:bg-red-900/40 dark:text-red-200",
  unknown: "bg-muted text-muted-foreground border-border",
};
