import { useState } from "react";
import { ExternalLink, Copy, Check, Flag } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { ConfidenceMeter } from "@/components/domain/confidence-meter";
import { StatusTag } from "@/components/domain/status-tag";
import { PdfPage } from "@/components/domain/pdf-page";
import { TableSkeleton } from "@/components/loading-skeleton";
import { MotionGridLoader } from "@/components/motion-grid-loader";
import {
  useParameterSource,
  useSourcePage,
  useDecideReview,
  type ParameterValue,
} from "@/api/hooks";
import { formatCondition, formatDate, formatValue, humanizeParam } from "@/lib/format";
import { toast } from "@/components/ui/toast";

export interface SourceViewerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  partId: string;
  paramId: string;
  value?: ParameterValue;
  triggerRef?: React.RefObject<HTMLButtonElement | null>;
}

export function SourceViewer({
  open,
  onOpenChange,
  partId,
  paramId,
  value,
  triggerRef,
}: SourceViewerProps) {
  const [copiedValue, setCopiedValue] = useState(false);
  const [copiedHash, setCopiedHash] = useState(false);

  const sourceQuery = useParameterSource(open ? partId : undefined, open ? paramId : undefined);
  const source = sourceQuery.data?.source;
  const sourceValue = sourceQuery.data?.value ?? value;
  const isPdf = source?.type === "pdf" && Boolean(sourceValue?.page);
  const pageNumber = sourceValue?.page ?? 1;

  const pageQuery = useSourcePage(
    open && isPdf ? source?.source_id : undefined,
    open && isPdf ? pageNumber : undefined,
  );
  const pageData = pageQuery.data;

  const decideReview = useDecideReview();

  // Restore focus to trigger button when closed
  const handleOpenChange = (nextOpen: boolean) => {
    onOpenChange(nextOpen);
    if (!nextOpen && triggerRef?.current) {
      setTimeout(() => triggerRef.current?.focus(), 50);
    }
  };

  const handleCopyValue = () => {
    if (!sourceValue) return;
    const text = `${sourceValue.name}: ${formatValue(sourceValue.value, sourceValue.unit)}`;
    navigator.clipboard.writeText(text).catch(() => {});
    setCopiedValue(true);
    setTimeout(() => setCopiedValue(false), 1500);
  };

  const handleCopyHash = () => {
    if (!source?.file_hash) return;
    navigator.clipboard.writeText(source.file_hash).catch(() => {});
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 1500);
  };

  const handleFlagValue = () => {
    if (!paramId) return;
    decideReview.mutate(
      {
        paramId,
        decision: {
          action: "reject",
          note: "Flagged from Source Viewer by engineering review",
        },
      },
      {
        onSuccess: () => {
          toast("Value flagged and sent to review queue");
        },
        onError: () => {
          toast.error("Could not flag value. Review endpoint failed.");
        },
      },
    );
  };

  const paramDisplayName = sourceValue?.name ? humanizeParam(sourceValue.name) : "the value";

  return (
    <Sheet open={open} onOpenChange={handleOpenChange}>
      <SheetContent
        side="right"
        className="w-full sm:max-w-[50vw] overflow-y-auto bg-[#121215] text-white p-6 rounded-l-[12px] border-l border-white/10 shadow-none flex flex-col justify-between"
      >
        <div className="space-y-6">
          {/* Sheet Header */}
          <SheetHeader className="p-0 border-0">
            <SheetTitle className="font-heading text-lg font-semibold text-white">
              Source of {paramDisplayName}
            </SheetTitle>
            <SheetDescription className="text-xs text-zinc-400 font-sans">
              Datasheet provenance and verified extraction region.
            </SheetDescription>
          </SheetHeader>

          {/* Top Value Summary Card */}
          {sourceQuery.isLoading && (
            <TableSkeleton
              rows={2}
              cols={3}
              title="Loading source provenance…"
              description="Locating bounding box coordinates and extracted text snippets."
            />
          )}

          {sourceValue && (
            <div className="rounded-[8px] border border-white/10 bg-white/5 p-4 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-base font-semibold text-white">
                    {formatValue(sourceValue.value, sourceValue.unit)}
                  </span>
                  {sourceValue.unit && (
                    <span className="font-mono text-xs text-zinc-400">{sourceValue.unit}</span>
                  )}
                  <StatusTag status={sourceValue.status ?? "unknown"} type="value" />
                </div>

                <div className="flex items-center gap-3">
                  <div
                    data-confidence={
                      (sourceValue.confidence ?? 0) >= 0.9
                        ? "high"
                        : (sourceValue.confidence ?? 0) >= 0.7
                          ? "medium"
                          : "low"
                    }
                  >
                    <ConfidenceMeter confidence={sourceValue.confidence} surface="dark" />
                  </div>
                  <button
                    type="button"
                    onClick={handleCopyValue}
                    aria-label="Copy extracted value"
                    className="inline-flex items-center gap-1 rounded-[4px] border border-white/15 bg-white/5 px-2 py-1 text-xs text-zinc-300 hover:text-white hover:bg-white/10"
                  >
                    {copiedValue ? (
                      <Check className="size-3 text-white" />
                    ) : (
                      <Copy className="size-3" />
                    )}
                    <span>{copiedValue ? "Copied" : "Copy value"}</span>
                  </button>
                </div>
              </div>

              {sourceValue.condition && Object.keys(sourceValue.condition).length > 0 && (
                <div className="text-xs font-mono text-zinc-300 bg-black/40 p-2 rounded-[4px] border border-white/10">
                  Condition: {formatCondition(sourceValue.condition)}
                </div>
              )}

              <div className="flex flex-wrap items-center gap-3 text-xs font-mono text-zinc-400">
                <span>
                  Method: {sourceValue.method ? sourceValue.method.toUpperCase() : "TIER 1"}
                </span>
                {sourceValue.page && <span>Page: {sourceValue.page}</span>}
              </div>
            </div>
          )}

          {/* Datasheet Page Body */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-mono uppercase font-bold tracking-wider text-zinc-400">
                Datasheet page {pageNumber}
              </h3>
            </div>

            {isPdf && source ? (
              <PdfPage
                sourceId={source.source_id}
                pageNumber={pageNumber}
                pdfUrl={source.type === "pdf" ? source.url : undefined}
                imageUrl={pageData?.image_url}
                rawText={sourceValue?.raw_text || pageData?.text}
                totalPages={source.page_count}
                className="border-white/10 bg-[#121215]"
              />
            ) : (
              <div className="rounded-[8px] border border-white/10 bg-white/5 p-6 text-xs text-zinc-300 font-mono space-y-3">
                <div className="flex items-center gap-2 text-white font-semibold">
                  <span>Distributor API Extraction Provenance</span>
                </div>
                <p className="text-zinc-400 text-xs font-sans leading-relaxed">
                  This parameter was extracted directly from the verified supplier feed (
                  {source?.type?.toUpperCase() ?? "API"}). No PDF datasheet page is associated with
                  this value.
                </p>
                {sourceValue?.raw_text && (
                  <div className="p-3 bg-black/40 rounded border border-white/10 text-xs font-mono text-zinc-200">
                    <span className="text-[10px] text-zinc-500 uppercase block mb-1">
                      Raw Ingested Text:
                    </span>
                    {sourceValue.raw_text}
                  </div>
                )}
                {source?.url && (
                  <div className="pt-2 text-xs">
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-white underline hover:text-zinc-300 inline-flex items-center gap-1"
                    >
                      <span>Verify on supplier site</span>
                      <ExternalLink className="size-3" />
                    </a>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Footer with Provenance Metadata & Flag Button */}
        {source && (
          <div className="mt-8 pt-4 border-t border-white/10 text-xs font-mono space-y-3">
            <div className="flex flex-col gap-1.5 text-zinc-400">
              <div className="flex items-center justify-between gap-2 overflow-hidden">
                <span className="shrink-0 text-zinc-500">Source URL:</span>
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="truncate text-white underline underline-offset-2 hover:text-zinc-300 flex items-center gap-1"
                >
                  <span className="truncate">{source.url}</span>
                  <ExternalLink className="size-3 shrink-0" />
                </a>
              </div>

              <div className="flex items-center justify-between gap-2">
                <span className="text-zinc-500">Fetched:</span>
                <span className="text-white">{formatDate(source.fetched_at)}</span>
              </div>

              {source.file_hash && (
                <div className="flex items-center justify-between gap-2">
                  <span className="text-zinc-500">SHA-256:</span>
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-zinc-300 text-[11px]">
                      {source.file_hash.slice(0, 8)}...
                    </span>
                    <button
                      type="button"
                      onClick={handleCopyHash}
                      title="Copy full SHA-256 hash"
                      className="p-0.5 text-zinc-400 hover:text-white"
                    >
                      {copiedHash ? <Check className="size-3" /> : <Copy className="size-3" />}
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Action Buttons */}
            <div className="pt-2 flex items-center justify-end">
              <button
                type="button"
                onClick={handleFlagValue}
                disabled={decideReview.isPending}
                aria-label="Flag this value for human review"
                className="inline-flex items-center gap-1.5 rounded-[8px] border border-white/20 bg-white/5 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:text-white hover:bg-white/10 active:bg-white/15 transition-none"
              >
                {decideReview.isPending ? (
                  <MotionGridLoader size="xs" variant="default" />
                ) : (
                  <Flag className="size-3.5" />
                )}
                <span>{decideReview.isPending ? "Flagging…" : "Flag this value"}</span>
              </button>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
