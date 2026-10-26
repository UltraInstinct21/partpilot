import { cn } from "@/lib/utils";
import type { LifecycleStatus, ValueStatus, RiskSeverity } from "@/api/hooks";

export interface StatusTagProps {
  status: LifecycleStatus | ValueStatus | RiskSeverity | string;
  type?: "lifecycle" | "value" | "risk" | "generic";
  className?: string;
}

/**
 * Rectangular status tag (4px radius, 13px text, never a pill).
 * Strict monochrome encoding per DESIGN.md:
 * - Active: solid outline
 * - NRND: dashed outline
 * - Obsolete: inverted (Ink fill, Haze text)
 * - Unknown: outline with muted text
 */
export function StatusTag({ status, type = "lifecycle", className }: StatusTagProps) {
  const norm = String(status).toLowerCase();

  let style = "border border-ink/40 text-ink bg-transparent";
  let label = norm.toUpperCase();

  if (type === "lifecycle" || norm === "active" || norm === "nrnd" || norm === "obsolete" || norm === "unknown") {
    switch (norm) {
      case "active":
        style = "border border-ink/40 text-ink bg-transparent";
        label = "Active";
        break;
      case "nrnd":
        style = "border border-dashed border-ink/60 text-ink bg-transparent";
        label = "NRND";
        break;
      case "obsolete":
        style = "bg-ink text-haze border border-ink";
        label = "Obsolete";
        break;
      case "unknown":
      default:
        style = "border border-ink/20 text-ink/50 bg-transparent";
        label = "Unknown";
        break;
    }
  } else if (type === "value" || norm === "accepted" || norm === "review" || norm === "rejected") {
    switch (norm) {
      case "accepted":
        style = "border border-ink/40 text-ink bg-transparent";
        label = "Accepted";
        break;
      case "review":
        style = "border border-dashed border-ink/60 text-ink bg-transparent";
        label = "Awaiting review";
        break;
      case "rejected":
        style = "bg-ink text-haze border border-ink";
        label = "Rejected";
        break;
      default:
        style = "border border-ink/20 text-ink bg-transparent";
        label = norm;
    }
  } else if (type === "risk") {
    switch (norm) {
      case "critical":
        style = "bg-ink text-haze border border-ink font-semibold";
        label = "Critical";
        break;
      case "high":
        style = "border-2 border-ink text-ink font-medium bg-transparent";
        label = "High";
        break;
      case "medium":
        style = "border border-dashed border-ink/60 text-ink bg-transparent";
        label = "Medium";
        break;
      case "low":
        style = "border border-ink/40 text-ink bg-transparent";
        label = "Low";
        break;
      case "info":
      default:
        style = "border border-ink/20 text-ink/60 bg-transparent";
        label = "Info";
        break;
    }
  }

  return (
    <span
      data-status={norm}
      className={cn(
        "inline-flex items-center justify-center rounded-[4px] px-2 py-0.5 text-[13px] leading-tight font-medium uppercase tracking-wider select-none",
        style,
        className,
      )}
    >
      {label}
    </span>
  );
}
