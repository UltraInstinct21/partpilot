import { Badge } from "@/components/ui/badge";
import type { LifecycleStatus } from "@/api/hooks";
import { LIFECYCLE_CLASS, LIFECYCLE_LABEL } from "@/lib/lifecycle";
import { cn } from "@/lib/utils";

/** The lifecycle badge of a part (FR-15). */
export function LifecycleBadge({
  status,
  className,
}: {
  status?: LifecycleStatus | null;
  className?: string;
}) {
  const key: LifecycleStatus = status ?? "unknown";
  return (
    <Badge
      variant="outline"
      data-lifecycle={key}
      title={`Lifecycle status: ${LIFECYCLE_LABEL[key]}`}
      className={cn("font-medium", LIFECYCLE_CLASS[key], className)}
    >
      {LIFECYCLE_LABEL[key]}
    </Badge>
  );
}
