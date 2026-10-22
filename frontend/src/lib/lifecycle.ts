import type { LifecycleStatus } from "@/api/hooks";

export const LIFECYCLE_CLASS: Record<LifecycleStatus, string> = {
  active: "bg-green-100 text-green-800 border-green-300 dark:bg-green-900/40 dark:text-green-200",
  nrnd: "bg-yellow-100 text-yellow-800 border-yellow-300 dark:bg-yellow-900/40 dark:text-yellow-200",
  obsolete: "bg-red-100 text-red-800 border-red-300 dark:bg-red-900/40 dark:text-red-200",
  unknown: "bg-muted text-muted-foreground border-border",
};

export const LIFECYCLE_LABEL: Record<LifecycleStatus, string> = {
  active: "Active",
  nrnd: "NRND",
  obsolete: "Obsolete",
  unknown: "Unknown",
};
