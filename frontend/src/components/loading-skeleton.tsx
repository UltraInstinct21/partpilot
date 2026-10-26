import { Skeleton } from "@/components/ui/skeleton";
import { ProgressLoadingState } from "@/components/motion-grid-loader";
import { cn } from "@/lib/utils";

export interface PageSkeletonProps {
  className?: string;
  title?: string;
  description?: string;
  progress?: number | null;
}

/** A skeleton block with Motion Grid animation and progress update UI that stands in for a page while it loads. */
export function PageSkeleton({
  className,
  title = "Loading page data…",
  description = "Aggregating components, parameters, and telemetry metrics.",
  progress,
}: PageSkeletonProps) {
  return (
    <div className={cn("space-y-6", className)} data-testid="page-skeleton">
      {/* Motion Grid animation with progress update UI */}
      <ProgressLoadingState
        title={title}
        description={description}
        progress={progress}
        size="lg"
      />

      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-full max-w-xl" />
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      </div>
    </div>
  );
}

export interface TableSkeletonProps {
  rows?: number;
  cols?: number;
  className?: string;
  title?: string;
  description?: string;
  progress?: number | null;
}

/** A skeleton with Motion Grid animation and progress update UI that stands in for a table while it loads. */
export function TableSkeleton({
  rows = 5,
  cols = 5,
  className,
  title = "Loading records…",
  description = "Fetching parametric records and distributor inventory feeds.",
  progress,
}: TableSkeletonProps) {
  return (
    <div className={cn("space-y-4", className)} data-testid="table-skeleton">
      {/* Motion Grid animation with progress update UI */}
      <ProgressLoadingState
        title={title}
        description={description}
        progress={progress}
        size="md"
      />

      {/* Table rows skeleton */}
      <div className="space-y-2">
        {Array.from({ length: rows }).map((_, rowIndex) => (
          <div key={rowIndex} className="flex gap-2">
            {Array.from({ length: cols }).map((__, colIndex) => (
              <Skeleton key={colIndex} className="h-9 flex-1" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
