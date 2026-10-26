import { getConfidenceTier, getConfidenceSegments } from "@/lib/constants";
import { cn } from "@/lib/utils";

export interface ConfidenceMeterProps {
  confidence: number | null | undefined;
  showValue?: boolean;
  showLabel?: boolean;
  surface?: "haze" | "dark";
  className?: string;
}

/**
 * 4-segment monochrome confidence meter conforming strictly to DESIGN.md.
 * Encodes confidence without color using a 4-segment gauge, numeric value, and text label.
 * High: >= 0.90 (4 segments)
 * Medium: 0.70 - 0.89 (3 segments)
 * Low: < 0.70 (1-2 segments)
 */
export function ConfidenceMeter({
  confidence,
  showValue = true,
  showLabel = true,
  surface = "haze",
  className,
}: ConfidenceMeterProps) {
  const tier = getConfidenceTier(confidence);
  const filledCount = getConfidenceSegments(confidence);
  const formattedScore =
    confidence !== null && confidence !== undefined && !Number.isNaN(confidence)
      ? confidence.toFixed(2)
      : "-";

  const label =
    tier === "high" ? "High" : tier === "medium" ? "Medium" : tier === "low" ? "Low" : "Unknown";

  const isDark = surface === "dark";

  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 font-mono text-[13px] leading-none select-none",
        isDark ? "text-white" : "text-ink",
        className,
      )}
      title={`Confidence score: ${formattedScore} (${label})`}
      aria-label={`Confidence: ${label} (${formattedScore})`}
    >
      {/* 4-segment monochrome meter */}
      <div className="flex items-center gap-[2px]" aria-hidden="true">
        {[1, 2, 3, 4].map((seg) => {
          const filled = seg <= filledCount;
          return (
            <div
              key={seg}
              className={cn(
                "w-[4px] h-[10px] rounded-[1px] transition-none",
                filled
                  ? isDark
                    ? "bg-white"
                    : "bg-ink"
                  : isDark
                    ? "border border-white/30 bg-transparent"
                    : "border border-ink/20 bg-transparent",
              )}
            />
          );
        })}
      </div>

      {/* Numeric value */}
      {showValue && (
        <span className={cn("text-[13px] font-medium", isDark ? "text-white" : "text-ink")}>
          {formattedScore}
        </span>
      )}

      {/* Text label */}
      {showLabel && (
        <span
          className={cn(
            "text-[11px] uppercase tracking-wider",
            isDark ? "text-zinc-400" : "text-zinc-500",
          )}
        >
          {label}
        </span>
      )}
    </div>
  );
}
