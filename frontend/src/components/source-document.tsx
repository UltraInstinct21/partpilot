import { useEffect, useState } from "react";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

type PdfModule = typeof import("react-pdf");

/**
 * Renders one page of a datasheet PDF with react-pdf.
 *
 * The component degrades gracefully: when react-pdf cannot be loaded or the
 * PDF cannot be parsed, a short message is shown instead of a crash. The
 * caller always shows the extracted page text next to it.
 */
export function SourceDocument({
  file,
  pageNumber,
  className,
}: {
  file: string;
  pageNumber: number;
  className?: string;
}) {
  const [pdfModule, setPdfModule] = useState<PdfModule | null>(null);
  const [failed, setFailed] = useState(false);

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
          // The worker URL cannot be built here. react-pdf uses its default worker.
        }
        if (!cancelled) setPdfModule(mod);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (failed || !pdfModule) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="pdf-unavailable">
        The datasheet page is not available as a PDF in this environment.
      </p>
    );
  }

  const Document = pdfModule.Document;
  const Page = pdfModule.Page;

  return (
    <div className={className}>
      <Document
        file={file}
        onLoadError={() => setFailed(true)}
        loading={<p className="text-sm text-muted-foreground">Loading the datasheet…</p>}
        error={
          <p className="text-sm text-muted-foreground" data-testid="pdf-unavailable">
            The datasheet page could not be rendered.
          </p>
        }
      >
        <Page pageNumber={pageNumber} renderTextLayer renderAnnotationLayer />
      </Document>
    </div>
  );
}
