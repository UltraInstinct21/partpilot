import { Badge } from "@/components/ui/badge";
import type { RiskSeverity, ValueStatus } from "@/api/hooks";
import { SEVERITY_CLASS, STATUS_CLASS, STATUS_LABEL } from "@/lib/status";
import { cn } from "@/lib/utils";

/** The validation status of a single value. */
export function StatusBadge({
  status,
  className,
}: {
  status?: ValueStatus | null;
  className?: string;
}) {
  const key: ValueStatus = status ?? "review";
  return (
    <Badge
      variant="outline"
      data-status={key}
      className={cn("font-medium", STATUS_CLASS[key], className)}
    >
      {STATUS_LABEL[key]}
    </Badge>
  );
}

/** The severity badge of a BOM risk. */
export function SeverityBadge({
  severity,
  className,
}: {
  severity?: RiskSeverity | null;
  className?: string;
}) {
  const key: RiskSeverity = severity ?? "info";
  return (
    <Badge
      variant="outline"
      data-severity={key}
      className={cn("font-medium capitalize", SEVERITY_CLASS[key], className)}
    >
      {key}
    </Badge>
  );
}
