import { CircleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { describeError } from "@/api/client";

/** The inline error state of a failed request. */
export function ErrorState({
  title = "The request failed",
  error,
  onRetry,
  className,
}: {
  title?: string;
  error?: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={`flex flex-col items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-4 ${className ?? ""}`}
    >
      <div className="flex items-center gap-2 font-medium text-destructive">
        <CircleAlert className="size-4" />
        {title}
      </div>
      {error !== undefined && (
        <p className="text-sm text-muted-foreground">{describeError(error)}</p>
      )}
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
