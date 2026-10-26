import { useState, useEffect } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

type PdfModule = typeof import("react-pdf");

export interface PdfPageProps {
  sourceId: string;
  pageNumber: number;
  pdfUrl?: string | null;
  imageUrl?: string | null;
  rawText?: string | null;
  boundingBox?: { x: number; y: number; width: number; height: number } | null;
  onPageChange?: (newPage: number) => void;
  totalPages?: number | null;
  className?: string;
}

/**
 * Datasheet page viewer supporting PDF rendering via react-pdf or raster image.
 * Features:
 * - Zoom: fit width, 100%, 150%
 * - Page navigation: previous, next, page selector
 * - 2px white outline bounding box for extracted region
 * - Fallback extracted row text display
 * - Zero shadows, 12px Haze surface container
 */
export function PdfPage({
  pageNumber,
  pdfUrl,
  imageUrl,
  rawText,
  boundingBox,
  onPageChange,
  totalPages,
  className,
}: PdfPageProps) {
  const [scale, setScale] = useState<number>(1.0);
  const [zoomMode, setZoomMode] = useState<"fit" | "100" | "150">("fit");
  const [pdfModule, setPdfModule] = useState<PdfModule | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [internalTotalPages, setInternalTotalPages] = useState<number | null>(null);

  const effectiveTotalPages = totalPages ?? internalTotalPages;

  useEffect(() => {
    let cancelled = false;
    import("react-pdf")
      .then((mod) => {
        try {
          mod.pdfjs.GlobalWorkerOptions.workerSrc = new URL(
            "pdfjs-dist/build/pdf.worker.min.mjs",
            import.meta.url,
          ).toString();
        } catch {
          // Worker fallback
        }
        if (!cancelled) setPdfModule(mod);
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleZoom = (mode: "fit" | "100" | "150") => {
    setZoomMode(mode);
    if (mode === "fit") setScale(1.0);
    else if (mode === "100") setScale(1.0);
    else if (mode === "150") setScale(1.5);
  };

  const handlePrev = () => {
    if (pageNumber > 1 && onPageChange) {
      onPageChange(pageNumber - 1);
    }
  };

  const handleNext = () => {
    if ((effectiveTotalPages === null || effectiveTotalPages === undefined || pageNumber < effectiveTotalPages) && onPageChange) {
      onPageChange(pageNumber + 1);
    }
  };

  return (
    <div className={cn("flex flex-col gap-3 rounded-[12px] bg-[#121215] text-white p-4 border border-white/10", className)}>
      {/* Viewer Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 pb-3 text-xs">
        {/* Page Nav */}
        <div className="flex items-center gap-1.5 font-mono">
          <button
            type="button"
            onClick={handlePrev}
            disabled={pageNumber <= 1 || !onPageChange}
            aria-label="Previous page"
            className="rounded-[4px] border border-white/15 p-1 text-zinc-300 hover:bg-white/5 disabled:opacity-30 disabled:pointer-events-none"
          >
            <ChevronLeft className="size-3.5" />
          </button>
          <span className="px-1 text-[13px] font-medium text-white">
            Page {pageNumber} {effectiveTotalPages ? `/ ${effectiveTotalPages}` : ""}
          </span>
          <button
            type="button"
            onClick={handleNext}
            disabled={Boolean(effectiveTotalPages && pageNumber >= effectiveTotalPages) || !onPageChange}
            aria-label="Next page"
            className="rounded-[4px] border border-white/15 p-1 text-zinc-300 hover:bg-white/5 disabled:opacity-30 disabled:pointer-events-none"
          >
            <ChevronRight className="size-3.5" />
          </button>
        </div>

        {/* Zoom Controls */}
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => handleZoom("fit")}
            className={cn(
              "rounded-[4px] px-2 py-0.5 text-[11px] font-medium uppercase border",
              zoomMode === "fit" ? "border-white bg-white text-black" : "border-white/15 bg-white/5 text-zinc-300 hover:bg-white/10",
            )}
          >
            Fit Width
          </button>
          <button
            type="button"
            onClick={() => handleZoom("100")}
            className={cn(
              "rounded-[4px] px-2 py-0.5 text-[11px] font-medium border",
              zoomMode === "100" ? "border-white bg-white text-black" : "border-white/15 bg-white/5 text-zinc-300 hover:bg-white/10",
            )}
          >
            100%
          </button>
          <button
            type="button"
            onClick={() => handleZoom("150")}
            className={cn(
              "rounded-[4px] px-2 py-0.5 text-[11px] font-medium border",
              zoomMode === "150" ? "border-white bg-white text-black" : "border-white/15 bg-white/5 text-zinc-300 hover:bg-white/10",
            )}
          >
            150%
          </button>
        </div>
      </div>

      {/* Page Canvas / Viewport */}
      <div className="relative min-h-[420px] max-h-[640px] overflow-auto bg-black/40 rounded-[8px] p-2 flex items-center justify-center border border-white/5">
        {imageUrl ? (
          <div className="relative inline-block transition-none">
            <img
              src={imageUrl}
              alt={`Datasheet page ${pageNumber}`}
              style={{ transform: `scale(${scale})`, transformOrigin: "top center" }}
              className="max-w-full rounded-[4px] transition-none"
            />
            {boundingBox && (
              <div
                style={{
                  position: "absolute",
                  left: `${boundingBox.x * 100}%`,
                  top: `${boundingBox.y * 100}%`,
                  width: `${boundingBox.width * 100}%`,
                  height: `${boundingBox.height * 100}%`,
                }}
                className="border-2 border-white pointer-events-none"
                aria-label="Extracted table value bounding box"
              />
            )}
          </div>
        ) : pdfUrl && pdfModule && !loadError ? (
          <div className="relative inline-block">
            <pdfModule.Document
              file={pdfUrl}
              onLoadError={() => setLoadError(true)}
              onLoadSuccess={(pdf: { numPages: number }) => setInternalTotalPages(pdf.numPages)}
              loading={<div className="p-8 text-xs font-mono text-zinc-400">Loading datasheet page...</div>}
              error={
                <div className="p-8 text-center text-xs text-zinc-400">
                  The datasheet page could not be loaded. Retry, or open the source URL.
                </div>
              }
            >
              <pdfModule.Page
                pageNumber={pageNumber}
                scale={scale}
                renderTextLayer
                renderAnnotationLayer
                className="border border-white/10 rounded-[4px]"
              />
            </pdfModule.Document>
            {boundingBox && (
              <div
                style={{
                  position: "absolute",
                  left: `${boundingBox.x * 100}%`,
                  top: `${boundingBox.y * 100}%`,
                  width: `${boundingBox.width * 100}%`,
                  height: `${boundingBox.height * 100}%`,
                }}
                className="border-2 border-white pointer-events-none"
              />
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center p-6 text-center text-xs text-zinc-400">
            <p className="font-medium text-white mb-1">Datasheet preview rendering</p>
            <p className="text-[11px] text-zinc-400 max-w-sm mb-4">
              Page {pageNumber} preview is indexed. Verify table text below.
            </p>
          </div>
        )}
      </div>

      {/* Extracted Row Text Display */}
      {rawText && (
        <div className="mt-2 rounded-[6px] border border-white/10 bg-white/5 p-3 text-xs font-mono text-zinc-200">
          <div className="text-[10px] font-sans uppercase font-bold tracking-wider text-zinc-400 mb-1">
            Extracted Datasheet Line:
          </div>
          <div className="whitespace-pre-wrap break-words">{rawText}</div>
        </div>
      )}
    </div>
  );
}
