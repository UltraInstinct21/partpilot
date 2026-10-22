import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/** A skeleton block that stands in for a page while it loads. */
export function PageSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("space-y-4", className)} data-testid="page-skeleton">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-4 w-full max-w-xl" />
      <div className="space-y-2">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    </div>
  );
}

/** A skeleton that stands in for a table while it loads. */
export function TableSkeleton({
  rows = 5,
  cols = 5,
  className,
}: {
  rows?: number;
  cols?: number;
  className?: string;
}) {
  return (
    <div className={cn("space-y-2", className)} data-testid="table-skeleton">
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div key={rowIndex} className="flex gap-2">
          {Array.from({ length: cols }).map((__, colIndex) => (
            <Skeleton key={colIndex} className="h-9 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}
