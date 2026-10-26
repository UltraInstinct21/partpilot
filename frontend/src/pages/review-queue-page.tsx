import { useMemo, useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { toast } from "@/components/ui/toast";
import {
  Check,
  CheckCircle2,
  SlidersHorizontal,
  ExternalLink,
  Download,
  Sparkles,
  Layers,
  FileText,
  Trash2,
  ChevronRight,
  Copy,
  Search,
  Send,
  Cpu,
  ShieldCheck,
  FileSpreadsheet,
  FileCode,
  ClipboardCheck,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ConfidenceMeter } from "@/components/domain/confidence-meter";
import { PdfPage } from "@/components/domain/pdf-page";
import { TableSkeleton } from "@/components/loading-skeleton";
import { MotionGridLoader } from "@/components/motion-grid-loader";
import {
  useReviewDecision,
  useReviewQueue,
  useReviewAdvisory,
  type ReviewItem,
  type ReviewAdvisoryResponse,
} from "@/api/hooks";
import { useReviewQueueStore, type ReviewQueueItem } from "@/lib/review-queue-store";
import { reviewSessionStore } from "@/lib/session-store";
import { humanizeParam, downloadTextFile, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/* Export Helpers                                                     */
/* ------------------------------------------------------------------ */

function generateBomCsv(items: ReviewQueueItem[]): string {
  const headers = [
    "Reference Designator",
    "MPN",
    "Manufacturer",
    "Subsystem",
    "Family",
    "Package",
    "Lifecycle",
    "Stock",
    "Unit Price",
    "Currency",
    "Status",
    "Notes",
  ];
  const rows = items.map((item) => [
    `"${item.referenceDesignator || ""}"`,
    `"${item.mpn}"`,
    `"${item.manufacturer}"`,
    `"${item.targetSubsystem || ""}"`,
    `"${item.family}"`,
    `"${item.package || ""}"`,
    `"${item.lifecycle_status || ""}"`,
    item.stock ?? 0,
    item.price ?? 0,
    `"${item.currency || "USD"}"`,
    `"${item.status}"`,
    `"${(item.notes || "").replace(/"/g, '""')}"`,
  ]);
  return [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
}

function generateBomTsv(items: ReviewQueueItem[]): string {
  const headers = [
    "Designator",
    "MPN",
    "Manufacturer",
    "Subsystem",
    "Package",
    "Lifecycle",
    "Stock",
    "Price",
    "Status",
  ];
  const rows = items.map((item) => [
    item.referenceDesignator || "",
    item.mpn,
    item.manufacturer,
    item.targetSubsystem || "",
    item.package || "",
    item.lifecycle_status || "",
    item.stock ?? 0,
    item.price ? `${item.price} ${item.currency || "USD"}` : "-",
    item.status,
  ]);
  return [headers.join("\t"), ...rows.map((r) => r.join("\t"))].join("\n");
}

function generateBomMarkdownReport(
  items: ReviewQueueItem[],
  advisory?: ReviewAdvisoryResponse | null,
): string {
  const dateStr = new Date().toISOString().split("T")[0];
  const finalized = items.filter((i) => i.status === "finalized");

  let md = `# PartPilot Hardware Design Review & Production BOM Sign-Off\n\n`;
  md += `**Date:** ${dateStr}  \n`;
  md += `**Total Queued Candidates:** ${items.length}  \n`;
  md += `**Finalized Components:** ${finalized.length} / ${items.length}  \n`;
  md += `**BOM Readiness Score:** ${advisory?.bom_readiness_score ?? (finalized.length === items.length ? 100 : 85)}%  \n\n`;

  if (advisory?.executive_summary) {
    md += `## Executive Summary\n${advisory.executive_summary}\n\n`;
  }
  if (advisory?.overall_recommendation) {
    md += `## Overall Engineering Recommendation\n${advisory.overall_recommendation}\n\n`;
  }

  md += `## Production Bill of Materials\n\n`;
  md += `| Designator | MPN | Manufacturer | Subsystem | Package | Lifecycle | Stock | Est. Price | Status |\n`;
  md += `| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n`;
  for (const item of items) {
    md += `| ${item.referenceDesignator || "-"} | **${item.mpn}** | ${item.manufacturer} | ${item.targetSubsystem || "-"} | ${item.package || "-"} | ${item.lifecycle_status || "-"} | ${item.stock?.toLocaleString() ?? 0} | ${item.price ? `$${item.price.toFixed(2)}` : "-"} | ${item.status === "finalized" ? "APPROVED" : "CANDIDATE"} |\n`;
  }
  md += `\n`;

  if (advisory?.tradeoffs && advisory.tradeoffs.length > 0) {
    md += `## Evaluated Technical Tradeoffs\n\n`;
    for (const t of advisory.tradeoffs) {
      md += `### ${t.dimension}\n`;
      md += `${t.analysis}\n`;
      if (t.advantage_mpn) {
        md += `*Advantage Pick:* **${t.advantage_mpn}**\n\n`;
      }
    }
  }

  if (advisory?.engineering_suggestions && advisory.engineering_suggestions.length > 0) {
    md += `## Hardware Implementation & Verification Notes\n\n`;
    for (const s of advisory.engineering_suggestions) {
      md += `- ${s}\n`;
    }
    md += `\n`;
  }

  md += `---\n*Generated by PartPilot Hardware Parametric RAG Platform*\n`;
  return md;
}

/* ------------------------------------------------------------------ */
/* Extraction Parameter QA Sub-system (FR-10 Backward Compatibility)   */
/* ------------------------------------------------------------------ */

const correctionSchema = z.object({
  value: z
    .string()
    .min(1, "A value is required")
    .refine((raw) => !Number.isNaN(Number(raw)), "The value must be a number"),
});

type CorrectionValues = z.infer<typeof correctionSchema>;

/* ------------------------------------------------------------------ */
/* Main Review Queue Page                                              */
/* ------------------------------------------------------------------ */

export function ReviewQueuePage() {
  const [searchParams, setSearchParams] = useSearchParams();

  // Tab: "final" (BOM Review & Finalisation) vs "extraction" (Datasheet QA)
  const tabParam = searchParams.get("tab");
  const currentTab = tabParam === "extraction" ? "extraction" : "final";

  const setTab = (tab: "final" | "extraction") => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("tab", tab);
      return next;
    });
  };

  // Review Store for Component Finalisation
  const {
    items: queuedParts,
    finalizedItems,
    finalizedCount,
    totalCount: queuedCount,
    finalizeItem,
    unfinalizeItem,
    removeItem: removeQueuedPart,
    updateItemMeta,
    finalizeAll,
    clearQueue,
    loadSampleCandidates,
  } = useReviewQueueStore();

  // AI Advisory Mutation
  const advisoryMutation = useReviewAdvisory();
  const [designPriority, setDesignPriority] = useState<
    "balanced" | "efficiency" | "cost" | "thermal" | "supply"
  >("balanced");
  const [customAiPrompt, setCustomAiPrompt] = useState("");
  const [advisoryData, setAdvisoryData] = useState<ReviewAdvisoryResponse | null>(null);
  const [exportModalOpen, setExportModalOpen] = useState(false);
  const [exportOnlyFinalized, setExportOnlyFinalized] = useState(false);

  // Auto-fetch or refresh AI advice when queued parts change
  useEffect(() => {
    if (queuedParts.length === 0) {
      setAdvisoryData(null);
      return;
    }

    advisoryMutation.mutate(
      {
        parts: queuedParts.map((p) => ({
          mpn: p.mpn,
          manufacturer: p.manufacturer,
          family: p.family,
          package: p.package,
          lifecycle_status: p.lifecycle_status,
          parameters: p.parameters,
          stock: p.stock,
          price: p.price,
          currency: p.currency,
        })),
        priority: designPriority,
        custom_query: customAiPrompt.trim() || undefined,
      },
      {
        onSuccess: (res) => setAdvisoryData(res),
        onError: (err) => console.error("Review advisory failed:", err),
      },
    );
  }, [queuedParts.length, designPriority]);

  const handleRunAiAnalysis = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (queuedParts.length === 0) return;
    advisoryMutation.mutate(
      {
        parts: queuedParts.map((p) => ({
          mpn: p.mpn,
          manufacturer: p.manufacturer,
          family: p.family,
          package: p.package,
          lifecycle_status: p.lifecycle_status,
          parameters: p.parameters,
          stock: p.stock,
          price: p.price,
          currency: p.currency,
        })),
        priority: designPriority,
        custom_query: customAiPrompt.trim() || undefined,
      },
      {
        onSuccess: (res) => {
          setAdvisoryData(res);
          toast.success("AI engineering analysis updated");
        },
      },
    );
  };

  // Export handlers
  const exportItems = exportOnlyFinalized ? finalizedItems : queuedParts;

  const handleDownloadCsv = () => {
    const csv = generateBomCsv(exportItems);
    downloadTextFile("partpilot_final_bom.csv", csv);
    toast.success(`Exported ${exportItems.length} components as CSV`);
  };

  const handleDownloadJson = () => {
    const payload = {
      title: "PartPilot Hardware BOM Export",
      exported_at: new Date().toISOString(),
      bom_readiness_score: advisoryData?.bom_readiness_score ?? 90,
      total_components: exportItems.length,
      finalized_components: finalizedCount,
      components: exportItems,
      ai_advisory: advisoryData,
    };
    downloadTextFile("partpilot_final_bom.json", JSON.stringify(payload, null, 2));
    toast.success(`Exported BOM package as JSON`);
  };

  const handleDownloadMarkdown = () => {
    const md = generateBomMarkdownReport(exportItems, advisoryData);
    downloadTextFile("partpilot_design_review_report.md", md);
    toast.success("Exported engineering design review report as Markdown");
  };

  const handleCopyTsv = () => {
    const tsv = generateBomTsv(exportItems);
    navigator.clipboard.writeText(tsv).then(() => {
      toast.success("BOM copied to clipboard (ready for spreadsheet paste)");
    });
  };

  /* ------------------------------------------------------------------ */
  /* Extraction Parameter QA State (FR-10)                              */
  /* ------------------------------------------------------------------ */
  const queueQuery = useReviewQueue();
  const decision = useReviewDecision();
  const savedReview = reviewSessionStore.get();
  const [correcting, setCorrecting] = useState<ReviewItem | null>(null);
  const [selectedIndex, setSelectedIndex] = useState<number>(() => savedReview.selectedIndex || 0);
  const familyFilter = savedReview.familyFilter || "all";
  const tierFilter = savedReview.tierFilter || "all";
  const reasonFilter = savedReview.reasonFilter || "all";
  const searchMpn = savedReview.searchMpn || "";

  const rawExtractionItems = useMemo(() => queueQuery.data ?? [], [queueQuery.data]);
  const extractionItems = useMemo(() => {
    return rawExtractionItems.filter((item) => {
      if (familyFilter !== "all" && item.family !== familyFilter) return false;
      if (tierFilter !== "all" && item.method !== tierFilter) return false;
      if (reasonFilter === "disagreement") {
        const hasDisagreement = item.reasons?.some((r) => r.toLowerCase().includes("disagree"));
        if (!hasDisagreement) return false;
      } else if (reasonFilter === "confidence") {
        const hasLowConf = item.reasons?.some((r) => r.toLowerCase().includes("confidence"));
        if (!hasLowConf) return false;
      }
      if (searchMpn.trim()) {
        const query = searchMpn.toLowerCase().trim();
        const matchesMpn = item.mpn.toLowerCase().includes(query);
        const matchesMfr = item.manufacturer.toLowerCase().includes(query);
        const matchesParam = item.name.toLowerCase().includes(query);
        if (!matchesMpn && !matchesMfr && !matchesParam) return false;
      }
      return true;
    });
  }, [rawExtractionItems, familyFilter, tierFilter, reasonFilter, searchMpn]);

  const selectedExtractionItem = extractionItems[selectedIndex] ?? extractionItems[0] ?? null;

  const handleAcceptParam = (item: ReviewItem) => {
    decision.mutate(
      { paramId: item.param_id, decision: { action: "accept" } },
      {
        onSuccess: () => {
          toast.success(`${humanizeParam(item.name)} accepted`);
        },
      },
    );
  };

  const handleRejectParam = (item: ReviewItem) => {
    decision.mutate(
      { paramId: item.param_id, decision: { action: "reject" } },
      {
        onSuccess: () => {
          toast.success(`${humanizeParam(item.name)} rejected`);
        },
      },
    );
  };

  const handleCorrectParam = (item: ReviewItem, value: number, unit?: string, note?: string) => {
    decision.mutate(
      {
        paramId: item.param_id,
        decision: {
          action: "correct",
          value,
          unit: unit || item.unit,
          note: note ? `Note: ${note}` : undefined,
        },
      },
      {
        onSuccess: () => {
          setCorrecting(null);
          toast.success(`${humanizeParam(item.name)} corrected to ${value}`);
        },
      },
    );
  };

  // Correction form
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors: formErrors },
  } = useForm<CorrectionValues>({
    resolver: zodResolver(correctionSchema),
    defaultValues: { value: "" },
  });

  useEffect(() => {
    if (correcting) {
      reset({ value: correcting.value != null ? String(correcting.value) : "" });
    }
  }, [correcting, reset]);

  return (
    <div className="relative space-y-8 w-full max-w-[1280px] mx-auto pb-16">
      {/* Ambient background glow matching Air theme */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-32 left-1/2 -translate-x-1/2 w-[900px] h-[340px] bg-gradient-to-b from-white/[0.06] via-white/[0.02] to-transparent blur-3xl opacity-60"
      />

      {/* Atmospheric Header & View Switcher */}
      <div className="relative z-10 flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-white/10 pb-6">
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs font-mono text-zinc-400">
            <Link to="/search" className="hover:text-white transition-colors">
              1. Search
            </Link>
            <ChevronRight className="size-3 text-zinc-600" />
            <Link to="/compare" className="hover:text-white transition-colors">
              2. Compare
            </Link>
            <ChevronRight className="size-3 text-zinc-600" />
            <span className="text-white font-medium">3. Final Review</span>
          </div>

          <h1 className="font-heading text-3xl sm:text-4xl md:text-5xl font-medium tracking-tight text-white leading-tight">
            Component Review &amp;{" "}
            <span className="font-cursive italic font-normal text-white text-4xl sm:text-5xl md:text-6xl text-white/90">
              finalisation
            </span>
          </h1>

          <p className="font-sans text-xs sm:text-sm text-zinc-300 max-w-2xl leading-relaxed">
            The final step before manufacturing. Triage candidate parts, evaluate AI tradeoffs and
            recommendations, assign reference designators, and export your approved BOM.
          </p>
        </div>

        {/* Fluid Pill View Switcher */}
        <div className="inline-flex items-center rounded-full bg-white/[0.04] p-1 border border-white/10 backdrop-blur-md self-start md:self-auto shrink-0 shadow-none">
          <button
            type="button"
            onClick={() => setTab("final")}
            className={cn(
              "rounded-full px-4 py-2 text-xs font-medium transition-all flex items-center gap-2 select-none",
              currentTab === "final"
                ? "bg-white text-black font-semibold shadow-sm"
                : "text-zinc-400 hover:text-white",
            )}
          >
            <Layers className="size-3.5" />
            <span>Component Finalisation</span>
            {queuedCount > 0 && (
              <span
                className={cn(
                  "rounded-full px-1.5 py-0.2 text-[10px] font-mono",
                  currentTab === "final"
                    ? "bg-black/15 text-black font-bold"
                    : "bg-white/10 text-zinc-300",
                )}
              >
                {queuedCount}
              </span>
            )}
          </button>

          <button
            type="button"
            onClick={() => setTab("extraction")}
            className={cn(
              "rounded-full px-4 py-2 text-xs font-medium transition-all flex items-center gap-2 select-none",
              currentTab === "extraction"
                ? "bg-white text-black font-semibold shadow-sm"
                : "text-zinc-400 hover:text-white",
            )}
          >
            <ShieldCheck className="size-3.5" />
            <span>Extraction QA</span>
            {rawExtractionItems.length > 0 && (
              <span
                className={cn(
                  "rounded-full px-1.5 py-0.2 text-[10px] font-mono",
                  currentTab === "extraction"
                    ? "bg-black/15 text-black font-bold"
                    : "bg-white/10 text-zinc-300",
                )}
              >
                {rawExtractionItems.length}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* =================================================================== */}
      {/* TAB 1: COMPONENT REVIEW & FINALISATION (AIR THEMED WORKSPACE)        */}
      {/* =================================================================== */}
      {currentTab === "final" && (
        <div className="space-y-8 relative z-10">
          {/* Floating Glass Telemetry & Actions Ribbon */}
          <div className="rounded-[20px] border border-white/10 bg-white/[0.03] backdrop-blur-xl p-5 sm:p-6 flex flex-col lg:flex-row lg:items-center justify-between gap-6 transition-all">
            {/* Organic Stat Metrics with Hairline Dividers */}
            <div className="flex flex-wrap items-center gap-6 sm:gap-8 text-xs font-sans">
              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">
                  Queued Candidates
                </div>
                <div className="text-xl sm:text-2xl font-mono font-medium text-white mt-0.5">
                  {queuedCount}
                </div>
              </div>

              <div className="h-8 w-px bg-white/10 hidden sm:block" />

              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">
                  Finalized for BOM
                </div>
                <div className="text-xl sm:text-2xl font-mono font-medium text-white mt-0.5 flex items-center gap-1.5">
                  <span>{finalizedCount}</span>
                  <span className="text-zinc-500 text-sm font-normal">/ {queuedCount}</span>
                </div>
              </div>

              <div className="h-8 w-px bg-white/10 hidden sm:block" />

              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">
                  BOM Readiness
                </div>
                <div className="text-xl sm:text-2xl font-mono font-medium text-white mt-0.5">
                  {advisoryData?.bom_readiness_score ?? (queuedCount > 0 ? (finalizedCount === queuedCount ? 100 : 85) : 0)}%
                </div>
              </div>

              <div className="h-8 w-px bg-white/10 hidden sm:block" />

              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">
                  Est. BOM Unit Cost
                </div>
                <div className="text-xl sm:text-2xl font-mono font-medium text-zinc-200 mt-0.5">
                  ${queuedParts.reduce((acc, p) => acc + (p.price || 0), 0).toFixed(2)}
                </div>
              </div>
            </div>

            {/* Floating Action Buttons */}
            <div className="flex items-center gap-2.5 flex-wrap">
              <Link
                to="/search"
                className="inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-white/[0.04] px-4 py-2 text-xs font-medium text-zinc-300 hover:text-white hover:bg-white/10 hover:border-white/25 transition-all"
              >
                <Search className="size-3.5 text-zinc-400" />
                <span>+ Find parts</span>
              </Link>

              {queuedCount > 0 && (
                <>
                  <button
                    type="button"
                    onClick={finalizeAll}
                    disabled={finalizedCount === queuedCount}
                    className="inline-flex items-center gap-1.5 rounded-full border border-white/20 bg-white/10 px-4 py-2 text-xs font-medium text-white hover:bg-white/20 disabled:opacity-40 transition-all"
                  >
                    <CheckCircle2 className="size-3.5" />
                    <span>Finalize All ({queuedCount})</span>
                  </button>

                  <button
                    type="button"
                    onClick={clearQueue}
                    className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-transparent px-3 py-2 text-xs text-zinc-500 hover:text-red-400 hover:border-red-400/30 transition-all"
                    title="Clear queue"
                  >
                    <Trash2 className="size-3.5" />
                    <span className="hidden sm:inline">Clear</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setExportModalOpen(true)}
                    className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-2 text-xs font-semibold text-black hover:bg-zinc-200 hover:shadow-lg transition-all"
                  >
                    <Download className="size-3.5" />
                    <span>Export Finalised Parts</span>
                  </button>
                </>
              )}
            </div>
          </div>

          {/* Empty State */}
          {queuedCount === 0 && (
            <div className="rounded-[24px] border border-white/10 bg-white/[0.02] backdrop-blur-xl p-12 sm:p-16 text-center space-y-5">
              <div className="mx-auto size-16 rounded-full border border-white/15 bg-white/5 flex items-center justify-center text-zinc-300 shadow-inner">
                <Layers className="size-7 stroke-[1.5]" />
              </div>
              <div className="space-y-2 max-w-md mx-auto">
                <h3 className="font-heading text-lg font-medium text-white">
                  Your Review Queue is Empty
                </h3>
                <p className="text-xs sm:text-sm text-zinc-400 leading-relaxed font-sans">
                  Shortlist parts from the parametric catalog. Once added, PartPilot AI will evaluate
                  conduction and switching tradeoffs, package thermals, and supply availability.
                </p>
              </div>
              <div className="flex items-center justify-center gap-3 pt-2">
                <Link
                  to="/search"
                  className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-2.5 text-xs font-medium text-black hover:bg-zinc-200 transition-all"
                >
                  <Search className="size-3.5" />
                  <span>Browse Components</span>
                </Link>
                <button
                  type="button"
                  onClick={loadSampleCandidates}
                  className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/[0.04] px-5 py-2.5 text-xs font-medium text-zinc-200 hover:text-white hover:bg-white/10 transition-all"
                >
                  <Cpu className="size-3.5 text-zinc-400" />
                  <span>Load Sample Candidates</span>
                </button>
              </div>
            </div>
          )}

          {/* AI TRADEOFF & RECOMMENDATION ADVISOR (AIR GLASS STUDIO) */}
          {queuedCount > 0 && (
            <section
              aria-label="AI Engineering Advisor and Tradeoff Synthesis"
              className="rounded-[24px] border border-white/10 bg-gradient-to-b from-white/[0.04] via-white/[0.02] to-transparent backdrop-blur-2xl p-6 sm:p-8 space-y-6 relative overflow-hidden"
            >
              {/* Header with Priority Pills */}
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-5 border-b border-white/10 pb-5">
                <div className="flex items-center gap-3">
                  <div className="size-9 rounded-full bg-white/10 border border-white/15 flex items-center justify-center text-white shrink-0">
                    <Sparkles className="size-4 text-white" />
                  </div>
                  <div>
                    <h2 className="font-heading text-base font-medium text-white flex items-center gap-2">
                      <span>AI Tradeoff &amp; Finalisation Advisor</span>
                      {advisoryMutation.isPending && (
                        <MotionGridLoader size="xs" />
                      )}
                    </h2>
                    <p className="text-xs text-zinc-400">
                      Evaluating {queuedCount} candidates across conduction FOM, packaging thermals, and multi-distributor supply.
                    </p>
                  </div>
                </div>

                {/* Priority Selector Pills */}
                <div className="flex items-center gap-1.5 flex-wrap">
                  {(
                    [
                      { id: "balanced", label: "Balanced" },
                      { id: "efficiency", label: "Efficiency" },
                      { id: "cost", label: "Lowest Cost" },
                      { id: "supply", label: "Supply Security" },
                      { id: "thermal", label: "Thermal Max" },
                    ] as const
                  ).map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => setDesignPriority(p.id)}
                      className={cn(
                        "rounded-full px-3.5 py-1 text-xs font-sans transition-all border",
                        designPriority === p.id
                          ? "border-white bg-white text-black font-semibold shadow-sm"
                          : "border-white/10 bg-white/[0.03] text-zinc-400 hover:text-white hover:bg-white/10",
                      )}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Executive Summary & Spotlight Recommendation */}
              {advisoryData && (
                <div className="grid grid-cols-1 md:grid-cols-12 gap-5">
                  {/* Summary Card */}
                  <div className="md:col-span-8 rounded-[18px] border border-white/[0.08] bg-white/[0.02] p-5 sm:p-6 space-y-3 flex flex-col justify-between">
                    <div className="space-y-2">
                      <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 font-semibold flex items-center gap-1.5">
                        <Cpu className="size-3 text-zinc-300" />
                        <span>Architectural Analysis</span>
                      </div>
                      <p className="text-xs sm:text-sm text-zinc-300 leading-relaxed font-sans">
                        {advisoryData.executive_summary}
                      </p>
                    </div>

                    <div className="pt-3 border-t border-white/5 flex items-start gap-2.5 text-xs text-zinc-200 font-medium">
                      <CheckCircle2 className="size-4 shrink-0 text-white mt-0.5" />
                      <span className="leading-relaxed">{advisoryData.overall_recommendation}</span>
                    </div>
                  </div>

                  {/* Top Pick Spotlight Card */}
                  {advisoryData.candidate_evaluations && advisoryData.candidate_evaluations[0] && (
                    <div className="md:col-span-4 rounded-[18px] border border-white/20 bg-gradient-to-br from-white/[0.08] to-white/[0.02] p-5 sm:p-6 space-y-4 flex flex-col justify-between">
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="rounded-full bg-white/10 text-white border border-white/20 px-2.5 py-0.5 text-[10px] font-mono font-medium">
                            Top Pick to Finalize
                          </span>
                        </div>
                        <div className="font-mono text-base font-semibold text-white">
                          {advisoryData.candidate_evaluations[0].mpn}
                        </div>
                        <p className="text-xs text-zinc-300 leading-relaxed font-sans">
                          {advisoryData.candidate_evaluations[0].verdict}
                        </p>
                      </div>

                      {/* Finalize button inside AI card */}
                      {(() => {
                        const topMpn = advisoryData.candidate_evaluations[0].mpn;
                        const matchPart = queuedParts.find(
                          (p) => p.mpn.toLowerCase() === topMpn.toLowerCase(),
                        );
                        if (!matchPart) return null;
                        const isFinal = matchPart.status === "finalized";
                        return (
                          <button
                            type="button"
                            onClick={() =>
                              isFinal ? unfinalizeItem(matchPart.id) : finalizeItem(matchPart.id)
                            }
                            className={cn(
                              "w-full rounded-full py-2 text-xs font-semibold flex items-center justify-center gap-2 transition-all",
                              isFinal
                                ? "border border-white/30 bg-white/20 text-white hover:bg-white/30"
                                : "bg-white text-black hover:bg-zinc-200",
                            )}
                          >
                            <Check className="size-3.5" />
                            <span>{isFinal ? "Part is Finalized" : "Finalize This Part"}</span>
                          </button>
                        );
                      })()}
                    </div>
                  )}
                </div>
              )}

              {/* Tradeoff Breakdown Matrix */}
              {advisoryData?.tradeoffs && advisoryData.tradeoffs.length > 0 && (
                <div className="space-y-3 pt-2">
                  <div className="text-[11px] font-mono uppercase tracking-wider text-zinc-400 font-semibold flex items-center gap-2">
                    <SlidersHorizontal className="size-3.5 text-zinc-400" />
                    <span>Evaluated Design Tradeoffs</span>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
                    {advisoryData.tradeoffs.map((t, idx) => (
                      <div
                        key={idx}
                        className="rounded-[16px] border border-white/[0.08] bg-white/[0.02] p-4 space-y-2 hover:border-white/20 transition-all"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-medium text-xs text-white">
                            {t.dimension}
                          </span>
                          {t.advantage_mpn && (
                            <span className="font-mono text-[10px] text-white bg-white/10 border border-white/20 px-2 py-0.5 rounded-full">
                              {t.advantage_mpn}
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-zinc-400 leading-relaxed font-sans">
                          {t.analysis}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Engineering Suggestions & Hardware Verification */}
              {advisoryData?.engineering_suggestions &&
                advisoryData.engineering_suggestions.length > 0 && (
                  <div className="rounded-[16px] border border-white/[0.08] bg-white/[0.02] p-4 sm:p-5 space-y-2.5">
                    <div className="text-[11px] font-mono uppercase tracking-wider text-zinc-400 font-semibold flex items-center gap-2">
                      <ShieldCheck className="size-3.5 text-white" />
                      <span>Hardware Implementation Notes</span>
                    </div>
                    <ul className="space-y-1.5 text-xs text-zinc-300 font-sans">
                      {advisoryData.engineering_suggestions.map((sug, sIdx) => (
                        <li key={sIdx} className="flex items-start gap-2">
                          <span className="text-zinc-500 font-mono mt-0.5">•</span>
                          <span>{sug}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

              {/* Seamless Floating Ask AI Bar */}
              <form
                onSubmit={handleRunAiAnalysis}
                className="relative rounded-full border border-white/15 bg-white/[0.03] p-1.5 pl-5 flex items-center gap-2 focus-within:border-white/35 backdrop-blur-md transition-all"
              >
                <input
                  type="text"
                  placeholder="Ask AI advisor a tradeoff question (e.g. 'Compare thermal dissipation at 20A continuous')..."
                  value={customAiPrompt}
                  onChange={(e) => setCustomAiPrompt(e.target.value)}
                  className="w-full bg-transparent text-xs text-white placeholder:text-zinc-500 focus:outline-none font-sans"
                />
                <button
                  type="submit"
                  disabled={advisoryMutation.isPending}
                  className="rounded-full bg-white px-5 py-2 text-xs font-semibold text-black hover:bg-zinc-200 disabled:opacity-40 transition-all shrink-0 flex items-center gap-1.5"
                >
                  {advisoryMutation.isPending ? (
                    <>
                      <MotionGridLoader size="xs" variant="default" />
                      <span>Analyzing...</span>
                    </>
                  ) : (
                    <>
                      <Send className="size-3" />
                      <span>Evaluate</span>
                    </>
                  )}
                </button>
              </form>
            </section>
          )}

          {/* CANDIDATE COMPONENTS WORKSPACE (AIR THEMED TABLE / LIST) */}
          {queuedCount > 0 && (
            <div className="space-y-4">
              <div className="flex items-center justify-between text-xs px-1">
                <div className="font-heading text-sm font-medium text-white flex items-center gap-2">
                  <span>Candidate Components Workspace</span>
                  <span className="text-zinc-500 font-normal">
                    ({queuedCount} part{queuedCount !== 1 ? "s" : ""})
                  </span>
                </div>
                <span className="text-zinc-400 text-xs hidden sm:inline">
                  Assign designators, edit subsystems, or finalize for BOM sign-off.
                </span>
              </div>

              <div className="overflow-x-auto rounded-[20px] border border-white/10 bg-white/[0.02] backdrop-blur-xl">
                <table className="w-full text-left text-xs font-sans">
                  <thead className="bg-white/[0.03] text-[11px] font-mono uppercase tracking-wider text-zinc-400 border-b border-white/10 select-none">
                    <tr>
                      <th className="px-4 py-3.5 w-12 text-center">Status</th>
                      <th className="px-4 py-3.5">MPN / Manufacturer</th>
                      <th className="px-4 py-3.5">Designator</th>
                      <th className="px-4 py-3.5">Subsystem</th>
                      <th className="px-4 py-3.5">Key Parameters</th>
                      <th className="px-4 py-3.5">Package</th>
                      <th className="px-4 py-3.5 text-right font-mono">Stock</th>
                      <th className="px-4 py-3.5 text-right font-mono">Price</th>
                      <th className="px-4 py-3.5 text-center">Action</th>
                    </tr>
                  </thead>

                  <tbody className="divide-y divide-white/5">
                    {queuedParts.map((item) => {
                      const isFinal = item.status === "finalized";
                      return (
                        <tr
                          key={item.id}
                          className={cn(
                            "hover:bg-white/[0.03] transition-colors",
                            isFinal && "bg-white/[0.04]",
                          )}
                        >
                          {/* Status Finalize Toggle */}
                          <td className="px-4 py-4 text-center">
                            <button
                              type="button"
                              onClick={() =>
                                isFinal ? unfinalizeItem(item.id) : finalizeItem(item.id)
                              }
                              title={isFinal ? "Marked as Finalized (Click to unfinalize)" : "Click to finalize for BOM"}
                              className={cn(
                                "size-6 rounded-full border flex items-center justify-center transition-all mx-auto",
                                isFinal
                                  ? "border-white bg-white text-black font-bold"
                                  : "border-white/20 bg-white/5 text-transparent hover:border-white/40",
                              )}
                            >
                              <Check className={cn("size-3.5", isFinal ? "opacity-100" : "opacity-0")} />
                            </button>
                          </td>

                          {/* MPN & Mfr */}
                          <td className="px-4 py-4">
                            <div className="font-mono font-medium text-white flex items-center gap-1.5 flex-wrap">
                              <Link
                                to={`/parts/${item.id}`}
                                className="text-white underline underline-offset-2 hover:text-zinc-300"
                              >
                                {item.mpn}
                              </Link>
                              {item.datasheet_url && (
                                <a
                                  href={item.datasheet_url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-zinc-500 hover:text-zinc-300"
                                  title="Open datasheet"
                                >
                                  <ExternalLink className="size-3" />
                                </a>
                              )}
                            </div>
                            <div className="text-[11px] text-zinc-400 mt-0.5">
                              {item.manufacturer} • <span className="capitalize">{item.family}</span>
                            </div>
                          </td>

                          {/* Reference Designator Input */}
                          <td className="px-4 py-4">
                            <input
                              type="text"
                              value={item.referenceDesignator || ""}
                              placeholder="e.g. Q1"
                              onChange={(e) =>
                                updateItemMeta(item.id, { referenceDesignator: e.target.value })
                              }
                              className="w-18 bg-white/5 border border-white/10 rounded-full px-3 py-1 font-mono text-xs text-white focus:outline-none focus:border-white/30 text-center"
                            />
                          </td>

                          {/* Subsystem Input */}
                          <td className="px-4 py-4">
                            <input
                              type="text"
                              value={item.targetSubsystem || ""}
                              placeholder="e.g. Power Stage"
                              onChange={(e) =>
                                updateItemMeta(item.id, { targetSubsystem: e.target.value })
                              }
                              className="w-36 bg-white/5 border border-white/10 rounded-full px-3 py-1 text-xs text-white focus:outline-none focus:border-white/30"
                            />
                          </td>

                          {/* Key Parameters */}
                          <td className="px-4 py-4">
                            <div className="flex flex-wrap gap-1.5 max-w-xs">
                              {Object.entries(item.parameters || {})
                                .slice(0, 3)
                                .map(([key, val]) => (
                                  <span
                                    key={key}
                                    className="inline-flex items-center gap-1 bg-white/5 border border-white/10 px-2 py-0.5 rounded-full text-[10px] font-mono text-zinc-300"
                                  >
                                    <span className="text-zinc-500">{humanizeParam(key)}:</span>
                                    <span>{typeof val === "number" ? formatNumber(val) : String(val)}</span>
                                  </span>
                                ))}
                            </div>
                          </td>

                          {/* Package & Lifecycle */}
                          <td className="px-4 py-4 font-mono text-[11px] text-zinc-300">
                            <div>{item.package || "-"}</div>
                            <div className="text-[10px] text-zinc-500 uppercase mt-0.5">
                              {item.lifecycle_status || "ACTIVE"}
                            </div>
                          </td>

                          {/* Stock */}
                          <td className="px-4 py-4 text-right font-mono text-zinc-300">
                            {item.stock ? item.stock.toLocaleString() : "-"}
                          </td>

                          {/* Price */}
                          <td className="px-4 py-4 text-right font-mono text-zinc-200">
                            {item.price ? `$${item.price.toFixed(2)}` : "-"}
                          </td>

                          {/* Row Actions */}
                          <td className="px-4 py-4 text-center">
                            <div className="flex items-center justify-center gap-2">
                              <button
                                type="button"
                                onClick={() =>
                                  isFinal ? unfinalizeItem(item.id) : finalizeItem(item.id)
                                }
                                className={cn(
                                  "rounded-full px-3 py-1 text-xs font-medium border transition-all",
                                  isFinal
                                    ? "border-white/30 bg-white/20 text-white"
                                    : "border-white/15 bg-white/5 text-zinc-300 hover:text-white hover:bg-white/10",
                                )}
                              >
                                {isFinal ? "Finalized" : "Finalize"}
                              </button>
                              <button
                                type="button"
                                onClick={() => removeQueuedPart(item.id)}
                                className="text-zinc-500 hover:text-red-400 transition-colors p-1"
                                title="Remove component from queue"
                              >
                                <Trash2 className="size-3.5" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* =================================================================== */}
      {/* TAB 2: EXTRACTION QA QUEUE (DATASHEET PARAMETER AUDIT - FR-10)      */}
      {/* =================================================================== */}
      {currentTab === "extraction" && (
        <div className="space-y-6 relative z-10">
          <div className="rounded-[18px] border border-white/10 bg-white/[0.02] backdrop-blur-md p-4 text-xs font-sans text-zinc-300 flex items-center justify-between gap-4">
            <div>
              <span className="font-semibold text-white">Datasheet Extraction Audit Queue: </span>
              Low-confidence parameters flagged during multi-tier PDF extraction waiting for human verification.
            </div>
            <div className="text-zinc-400 font-mono text-[11px]">
              {extractionItems.length} parameter{extractionItems.length !== 1 ? "s" : ""} pending triage
            </div>
          </div>

          {queueQuery.isLoading && <TableSkeleton rows={6} cols={6} />}

          {!queueQuery.isLoading && extractionItems.length === 0 && (
            <div className="rounded-[20px] border border-white/10 bg-white/[0.02] backdrop-blur-xl p-12 text-center space-y-3">
              <CheckCircle2 className="size-8 text-white mx-auto" />
              <div className="font-heading font-medium text-white">Extraction Queue Clean</div>
              <p className="text-xs text-zinc-400 max-w-sm mx-auto">
                No low-confidence parameter discrepancies currently flagged.
              </p>
            </div>
          )}

          {!queueQuery.isLoading && extractionItems.length > 0 && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Table side (7 cols) */}
              <div className="lg:col-span-7 overflow-x-auto rounded-[20px] border border-white/10 bg-white/[0.02] backdrop-blur-xl">
                <table className="w-full text-left text-xs font-sans">
                  <thead className="bg-white/[0.03] text-[11px] font-mono uppercase tracking-wider text-zinc-400 border-b border-white/10 select-none">
                    <tr>
                      <th className="px-4 py-3">MPN</th>
                      <th className="px-4 py-3">Parameter</th>
                      <th className="px-4 py-3 font-mono">Value</th>
                      <th className="px-4 py-3 text-right">Confidence</th>
                      <th className="px-4 py-3 text-center">Decision</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5 font-mono">
                    {extractionItems.map((item, idx) => {
                      const isRowSelected = selectedExtractionItem?.param_id === item.param_id;
                      return (
                        <tr
                          key={item.param_id}
                          onClick={() => setSelectedIndex(idx)}
                          className={cn(
                            "cursor-pointer hover:bg-white/[0.04] transition-colors",
                            isRowSelected && "bg-white/[0.08]",
                          )}
                        >
                          <td className="px-4 py-3 font-medium text-white">{item.mpn}</td>
                          <td className="px-4 py-3 text-zinc-300 font-sans">{humanizeParam(item.name)}</td>
                          <td className="px-4 py-3 text-zinc-200">
                            {item.value != null ? `${item.value} ${item.unit || ""}` : item.raw_text || "-"}
                          </td>
                          <td className="px-4 py-3 text-right">
                            <ConfidenceMeter confidence={item.confidence} surface="dark" />
                          </td>
                          <td className="px-4 py-3 text-center" onClick={(e) => e.stopPropagation()}>
                            <div className="flex items-center justify-center gap-1.5">
                              <button
                                type="button"
                                onClick={() => handleAcceptParam(item)}
                                className="px-2.5 py-1 rounded-full text-[11px] border border-white/20 bg-white/5 text-zinc-200 hover:text-white hover:bg-white/10 transition-all"
                              >
                                Accept
                              </button>
                              <button
                                type="button"
                                onClick={() => setCorrecting(item)}
                                className="px-2.5 py-1 rounded-full text-[11px] border border-white/20 bg-white/5 text-zinc-200 hover:text-white hover:bg-white/10 transition-all"
                              >
                                Correct
                              </button>
                              <button
                                type="button"
                                onClick={() => handleRejectParam(item)}
                                className="px-2.5 py-1 rounded-full text-[11px] border border-white/20 bg-white/5 text-zinc-400 hover:text-red-400 hover:bg-white/10 transition-all"
                              >
                                Reject
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Inspection Preview side (5 cols) */}
              <div className="lg:col-span-5 rounded-[20px] border border-white/10 bg-white/[0.02] backdrop-blur-xl p-5 space-y-4">
                {selectedExtractionItem ? (
                  <>
                    <div className="flex items-center justify-between border-b border-white/10 pb-3">
                      <div>
                        <div className="font-mono text-sm font-semibold text-white">
                          {selectedExtractionItem.mpn}
                        </div>
                        <div className="text-xs text-zinc-400">
                          {humanizeParam(selectedExtractionItem.name)}
                        </div>
                      </div>
                      <span className="text-[10px] font-mono uppercase bg-white/10 text-zinc-300 border border-white/20 px-2.5 py-0.5 rounded-full">
                        Confidence below the review threshold
                      </span>
                    </div>

                    {selectedExtractionItem.reasons && selectedExtractionItem.reasons.length > 0 && (
                      <div className="rounded-[14px] border border-white/10 bg-white/[0.02] p-3 text-xs text-zinc-300 space-y-1">
                        <div className="text-[10px] font-mono uppercase text-zinc-500">Triage Reason</div>
                        {selectedExtractionItem.reasons.map((r, i) => (
                          <div key={i}>{r}</div>
                        ))}
                      </div>
                    )}

                    {selectedExtractionItem.source_id && selectedExtractionItem.page && (
                      <div className="space-y-1.5">
                        <div className="text-[10px] font-mono uppercase text-zinc-500">Datasheet Source</div>
                        <PdfPage
                          sourceId={selectedExtractionItem.source_id}
                          pageNumber={selectedExtractionItem.page}
                        />
                      </div>
                    )}
                  </>
                ) : (
                  <div className="text-xs text-zinc-500 py-12 text-center">
                    Select a parameter row to inspect source provenance.
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* =================================================================== */}
      {/* EXPORT FINALISED PARTS MODAL DIALOG (AIR THEMED GLASS MODAL)        */}
      {/* =================================================================== */}
      <Dialog open={exportModalOpen} onOpenChange={setExportModalOpen}>
        <DialogContent className="max-w-2xl bg-[#121215]/95 backdrop-blur-2xl text-white border border-white/15 p-7 rounded-[24px] shadow-2xl space-y-6">
          <DialogHeader className="space-y-1.5">
            <DialogTitle className="font-heading text-xl font-medium text-white flex items-center gap-2.5">
              <Download className="size-5 text-white" />
              <span>Export Finalised Bill of Materials</span>
            </DialogTitle>
            <DialogDescription className="text-xs sm:text-sm text-zinc-400 leading-relaxed">
              Download production-ready BOM exports or copy formatted tables for EDA tools (Altium, KiCad) and distributors.
            </DialogDescription>
          </DialogHeader>

          {/* Scope Selector Ribbon */}
          <div className="flex items-center gap-4 p-3.5 rounded-full border border-white/10 bg-white/[0.03] text-xs">
            <span className="font-mono text-zinc-400 pl-2">Export Scope:</span>
            <label className="flex items-center gap-2 cursor-pointer text-zinc-300 hover:text-white">
              <input
                type="radio"
                name="exportScope"
                checked={!exportOnlyFinalized}
                onChange={() => setExportOnlyFinalized(false)}
                className="size-3.5"
              />
              <span>All Candidates ({queuedCount})</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-zinc-300 hover:text-white">
              <input
                type="radio"
                name="exportScope"
                checked={exportOnlyFinalized}
                onChange={() => setExportOnlyFinalized(true)}
                className="size-3.5"
              />
              <span>Finalized Only ({finalizedCount})</span>
            </label>
          </div>

          {/* Export Format Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5 text-xs">
            {/* CSV */}
            <div className="rounded-[18px] border border-white/10 bg-white/[0.02] p-5 space-y-3 flex flex-col justify-between hover:border-white/20 transition-all">
              <div className="space-y-1.5">
                <div className="font-mono font-medium text-sm text-white flex items-center gap-2">
                  <FileSpreadsheet className="size-4 text-white" />
                  <span>Production BOM (.csv)</span>
                </div>
                <p className="text-zinc-400 text-xs leading-relaxed font-sans">
                  Standard format with Reference Designator, MPN, Manufacturer, Subsystem, Package, Stock, and Price.
                </p>
              </div>
              <button
                type="button"
                onClick={handleDownloadCsv}
                className="w-full mt-2 inline-flex items-center justify-center gap-2 rounded-full bg-white px-4 py-2 font-medium text-black hover:bg-zinc-200 transition-all"
              >
                <Download className="size-3.5" />
                <span>Download CSV</span>
              </button>
            </div>

            {/* Markdown Report */}
            <div className="rounded-[18px] border border-white/10 bg-white/[0.02] p-5 space-y-3 flex flex-col justify-between hover:border-white/20 transition-all">
              <div className="space-y-1.5">
                <div className="font-mono font-medium text-sm text-white flex items-center gap-2">
                  <FileText className="size-4 text-white" />
                  <span>Design Review (.md)</span>
                </div>
                <p className="text-zinc-400 text-xs leading-relaxed font-sans">
                  Complete hardware design sign-off document including BOM table, AI tradeoffs, and implementation checklist.
                </p>
              </div>
              <button
                type="button"
                onClick={handleDownloadMarkdown}
                className="w-full mt-2 inline-flex items-center justify-center gap-2 rounded-full border border-white/20 bg-white/5 px-4 py-2 font-medium text-white hover:bg-white/10 transition-all"
              >
                <Download className="size-3.5" />
                <span>Download Report</span>
              </button>
            </div>

            {/* JSON Package */}
            <div className="rounded-[18px] border border-white/10 bg-white/[0.02] p-5 space-y-3 flex flex-col justify-between hover:border-white/20 transition-all">
              <div className="space-y-1.5">
                <div className="font-mono font-medium text-sm text-white flex items-center gap-2">
                  <FileCode className="size-4 text-white" />
                  <span>Manufacturing (.json)</span>
                </div>
                <p className="text-zinc-400 text-xs leading-relaxed font-sans">
                  Machine-readable JSON schema containing extracted parameters, supplier offers, and AI sign-off audit data.
                </p>
              </div>
              <button
                type="button"
                onClick={handleDownloadJson}
                className="w-full mt-2 inline-flex items-center justify-center gap-2 rounded-full border border-white/20 bg-white/5 px-4 py-2 font-medium text-white hover:bg-white/10 transition-all"
              >
                <Download className="size-3.5" />
                <span>Download JSON</span>
              </button>
            </div>

            {/* Copy Clipboard */}
            <div className="rounded-[18px] border border-white/10 bg-white/[0.02] p-5 space-y-3 flex flex-col justify-between hover:border-white/20 transition-all">
              <div className="space-y-1.5">
                <div className="font-mono font-medium text-sm text-white flex items-center gap-2">
                  <ClipboardCheck className="size-4 text-white" />
                  <span>Copy TSV to Clipboard</span>
                </div>
                <p className="text-zinc-400 text-xs leading-relaxed font-sans">
                  Tab-separated text ready to paste directly into Google Sheets, Microsoft Excel, or Altium BOM managers.
                </p>
              </div>
              <button
                type="button"
                onClick={handleCopyTsv}
                className="w-full mt-2 inline-flex items-center justify-center gap-2 rounded-full border border-white/20 bg-white/5 px-4 py-2 font-medium text-white hover:bg-white/10 transition-all"
              >
                <Copy className="size-3.5" />
                <span>Copy TSV</span>
              </button>
            </div>
          </div>

          <DialogFooter className="pt-2">
            <button
              type="button"
              onClick={() => setExportModalOpen(false)}
              className="rounded-full border border-white/20 px-5 py-2 text-xs text-zinc-300 hover:text-white hover:bg-white/10 transition-all"
            >
              Done
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Parameter Correction Dialog (FR-10) */}
      <Dialog open={Boolean(correcting)} onOpenChange={(open) => !open && setCorrecting(null)}>
        <DialogContent className="max-w-md bg-[#121215]/95 backdrop-blur-2xl text-white border border-white/15 p-6 rounded-[20px] shadow-2xl">
          <DialogHeader>
            <DialogTitle className="font-heading text-base font-semibold text-white">
              Correct Parameter Value
            </DialogTitle>
            <DialogDescription className="text-xs text-zinc-400">
              Provide the verified numerical value from the component datasheet.
            </DialogDescription>
          </DialogHeader>

          {correcting && (
            <form
              onSubmit={handleSubmit((data) =>
                handleCorrectParam(correcting, Number(data.value), correcting.unit || undefined),
              )}
              className="space-y-4 pt-2"
            >
              <div className="space-y-1">
                <div className="text-xs text-zinc-400 font-mono">
                  {correcting.mpn} • {humanizeParam(correcting.name)}
                </div>
                <label htmlFor="correct-val" className="block text-xs font-medium text-zinc-200">
                  Correct value
                </label>
                <div className="flex items-center gap-2">
                  <Input
                    id="correct-val"
                    {...register("value")}
                    placeholder="Enter numeric value"
                    className="bg-white/5 border-white/20 text-white font-mono text-xs rounded-full px-4"
                    autoFocus
                  />
                  {correcting.unit && (
                    <span className="text-xs font-mono text-zinc-400 shrink-0">
                      {correcting.unit}
                    </span>
                  )}
                </div>
                {formErrors.value && (
                  <p className="text-[11px] text-red-400 mt-1">{formErrors.value.message}</p>
                )}
              </div>

              <DialogFooter className="pt-2 flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setCorrecting(null)}
                  className="rounded-full border border-white/20 px-4 py-1.5 text-xs text-zinc-400 hover:text-white transition-all"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded-full bg-white px-5 py-1.5 text-xs font-semibold text-black hover:bg-zinc-200 transition-all"
                >
                  Save the correction
                </button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
