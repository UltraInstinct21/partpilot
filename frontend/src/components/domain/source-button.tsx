import { FileText } from "lucide-react";
import { cn } from "@/lib/utils";

export interface SourceButtonProps {
  page?: number | null;
  sourceId?: string | null;
  method?: string | null;
  onClick: () => void;
  className?: string;
  disabled?: boolean;
}

/**
 * Button linking a value directly to its datasheet provenance page.
 * Strictly adheres to 8px radius and ghost button style on Haze or Dark surfaces.
 */
export function SourceButton({
  page,
  sourceId,
  method,
  onClick,
  className,
  disabled = false,
}: SourceButtonProps) {
  const hasPage = page !== null && page !== undefined && page > 0;
  const label = hasPage ? `p. ${page}` : "Source";

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || (!sourceId && !hasPage)}
      title={
        hasPage
          ? `View provenance on datasheet page ${page} (Tier: ${method ?? "unknown"})`
          : "View value provenance"
      }
      aria-label={`Open datasheet page ${page ?? ""}`}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[8px] border border-ink/20 bg-transparent px-2.5 py-1 text-[13px] font-mono font-medium text-ink hover:bg-ink/5 active:bg-ink/10 focus-visible:outline-2 focus-visible:outline-ink disabled:opacity-40 disabled:pointer-events-none transition-none select-none",
        className,
      )}
    >
      <FileText className="size-3.5 stroke-[1.5]" />
      <span>{label}</span>
    </button>
  );
}
