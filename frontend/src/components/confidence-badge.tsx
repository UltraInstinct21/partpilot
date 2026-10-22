import { Badge } from "@/components/ui/badge";
import { CONFIDENCE_CLASS, confidenceLevel } from "@/lib/confidence";
import { cn } from "@/lib/utils";

/** Green, yellow or red badge for the confidence of a value. */
export function ConfidenceBadge({
  confidence,
  className,
}: {
  confidence?: number | null;
  className?: string;
}) {
  const level = confidenceLevel(confidence);
  const label =
    confidence === null || confidence === undefined
      ? "no data"
      : `${Math.round(confidence * 100)}%`;
  return (
    <Badge
      variant="outline"
      data-confidence={level}
      title={`Confidence ${label} (${level})`}
      className={cn("font-mono tabular-nums", CONFIDENCE_CLASS[level], className)}
    >
      {label}
    </Badge>
  );
}
