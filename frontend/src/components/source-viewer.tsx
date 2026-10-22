import { ExternalLink } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ConfidenceBadge } from "@/components/confidence-badge";
import { StatusBadge } from "@/components/status-badge";
import { SourceDocument } from "@/components/source-document";
import { ErrorState } from "@/components/error-state";
import { TableSkeleton } from "@/components/loading-skeleton";
import { useParameterSource, useSourcePage } from "@/api/hooks";
import type { ParameterValue } from "@/api/hooks";
import { formatCondition, formatDate, formatValue } from "@/lib/format";

/**
 * The source viewer (FR-12).
 *
 * It shows the datasheet page NEXT TO the value it produced, together with
 * the full provenance: source, page, method, confidence and status.
 */
export function SourceViewer({
  open,
  onOpenChange,
  partId,
  paramId,
  value,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  partId: string;
  paramId: string;
  value?: ParameterValue;
}) {
  const sourceQuery = useParameterSource(open ? partId : undefined, open ? paramId : undefined);
  const source = sourceQuery.data?.source;
  const sourceValue = sourceQuery.data?.value ?? value;
  const pageNumber = sourceValue?.page ?? 1;

  const pageQuery = useSourcePage(
    open ? source?.source_id : undefined,
    open ? pageNumber : undefined,
  );
  const page = pageQuery.data;

  const isPdf = source?.type === "pdf" || (source?.url ?? "").toLowerCase().endsWith(".pdf");

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-4xl">
        <SheetHeader>
          <SheetTitle>Source of {sourceValue?.name ?? "the value"}</SheetTitle>
          <SheetDescription>
            The page of the datasheet that produced this value, with its provenance.
          </SheetDescription>
        </SheetHeader>

        <div className="grid gap-6 px-4 pb-6 md:grid-cols-2">
          {/* The value and its provenance */}
          <section className="space-y-3" aria-label="Value and provenance">
            <h3 className="text-sm font-semibold">Value</h3>
            {sourceQuery.isLoading && <TableSkeleton rows={3} cols={2} />}
            {sourceQuery.isError && (
              <ErrorState
                title="The source could not be loaded"
                error={sourceQuery.error}
                onRetry={() => void sourceQuery.refetch()}
              />
            )}
            {sourceValue && (
              <div className="rounded-lg border border-border p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{sourceValue.name}</span>
                  <span className="font-mono text-lg tabular-nums">
                    {formatValue(sourceValue.value, sourceValue.unit)}
                  </span>
                  <ConfidenceBadge confidence={sourceValue.confidence} />
                  <StatusBadge status={sourceValue.status} />
                </div>
                {sourceValue.condition !== undefined &&
                  sourceValue.condition !== null &&
                  Object.keys(sourceValue.condition).length > 0 && (
                    <p className="mt-2 text-sm text-muted-foreground">
                      Condition: {formatCondition(sourceValue.condition)}
                    </p>
                  )}
                {sourceValue.raw_text && (
                  <p className="mt-1 font-mono text-xs text-muted-foreground">
                    {sourceValue.raw_text}
                  </p>
                )}
              </div>
            )}

            {source && (
              <>
                <Separator />
                <h3 className="text-sm font-semibold">Provenance</h3>
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                  <dt className="text-muted-foreground">Source</dt>
                  <dd className="flex items-center gap-2">
                    <Badge variant="secondary">{source.type}</Badge>
                    {source.distributor && <span>{source.distributor}</span>}
                  </dd>
                  <dt className="text-muted-foreground">Page</dt>
                  <dd>{pageNumber}</dd>
                  <dt className="text-muted-foreground">Method</dt>
                  <dd>{sourceValue?.method ?? "-"}</dd>
                  <dt className="text-muted-foreground">Fetched</dt>
                  <dd>{formatDate(source.fetched_at)}</dd>
                  <dt className="text-muted-foreground">URL</dt>
                  <dd className="break-all">
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="inline-flex items-center gap-1 underline"
                    >
                      {source.url}
                      <ExternalLink className="size-3" />
                    </a>
                  </dd>
                  {source.file_hash && (
                    <>
                      <dt className="text-muted-foreground">Hash</dt>
                      <dd className="break-all font-mono text-xs">{source.file_hash}</dd>
                    </>
                  )}
                </dl>
              </>
            )}
          </section>

          {/* The datasheet page */}
          <section className="space-y-3" aria-label="Datasheet page">
            <h3 className="text-sm font-semibold">Datasheet page {pageNumber}</h3>
            {pageQuery.isLoading && <TableSkeleton rows={4} cols={1} />}
            {pageQuery.isError && (
              <ErrorState
                title="The page could not be loaded"
                error={pageQuery.error}
                onRetry={() => void pageQuery.refetch()}
              />
            )}
            {page && (
              <div className="space-y-3" data-testid="source-page">
                <p className="text-xs text-muted-foreground">
                  {page.width ?? "?"} × {page.height ?? "?"} px
                  {page.is_image_only ? " · scanned page without a text layer" : ""}
                </p>
                {page.image_url ? (
                  // The API renders the page as a PNG. This always works, also
                  // when the PDF itself is on a server the browser may not
                  // reach (the vendor site).
                  <img
                    src={page.image_url}
                    alt={`Page ${pageNumber} of the datasheet`}
                    className="max-h-72 w-auto border border-border"
                    data-testid="source-page-image"
                  />
                ) : isPdf && source ? (
                  <SourceDocument file={source.url} pageNumber={pageNumber} />
                ) : (
                  <div className="rounded-lg border border-border p-3">
                    <p className="text-sm text-muted-foreground">
                      The extracted text of the page is shown below. The page image is
                      rendered by the API when the source is a stored PDF.
                    </p>
                  </div>
                )}
                {page.text && (
                  <pre
                    className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-muted/40 p-3 font-mono text-xs"
                    data-testid="source-page-text"
                  >
                    {page.text}
                  </pre>
                )}
              </div>
            )}
          </section>
        </div>
      </SheetContent>
    </Sheet>
  );
}
