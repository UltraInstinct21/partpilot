import { useState, useMemo, useRef, useEffect } from "react";
import { useParams, useSearchParams, Link, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { FileText, Download, Scale, ArrowLeft, PlayCircle, ListPlus, Check } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import { StatusTag } from "@/components/domain/status-tag";
import { ConfidenceMeter } from "@/components/domain/confidence-meter";
import { SourceViewer } from "@/components/source-viewer";
import { ErrorState } from "@/components/error-state";
import { PageSkeleton } from "@/components/loading-skeleton";
import { MotionGridLoader } from "@/components/motion-grid-loader";
import {
  usePart,
  useAlternatives,
  useStartExtractionJob,
  useDownloadDatasheet,
  useJob,
  queryKeys,
  type ParameterValue,
} from "@/api/hooks";
import { useCompareSelection } from "@/lib/compare-store";
import { useReviewQueueStore } from "@/lib/review-queue-store";
import { partDetailSessionStore } from "@/lib/session-store";
import {
  formatDate,
  formatValue,
  humanizeParam,
  formatCondition,
  formatNumber,
  formatDistributorName,
  formatCurrencyPrice,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import { downloadFileWithProgress } from "@/api/client";
import { toast } from "@/components/ui/toast";

// Standard engineering metadata for parameter symbols
const PARAM_SYMBOLS: Record<string, { symbol: string; group: string }> = {
  vds_max: { symbol: "V(BR)DSS", group: "Absolute maximum ratings" },
  id_continuous: { symbol: "ID", group: "Absolute maximum ratings" },
  vgs_max: { symbol: "VGS", group: "Absolute maximum ratings" },
  power_dissipation_pd: { symbol: "Ptot", group: "Absolute maximum ratings" },
  junction_temp_tj_max: { symbol: "Tj max", group: "Thermal characteristics" },
  thermal_resistance_rthjc: { symbol: "RthJC", group: "Thermal characteristics" },
  thermal_resistance_rthja: { symbol: "RthJA", group: "Thermal characteristics" },
  rds_on: { symbol: "RDS(on)", group: "Electrical characteristics" },
  gate_threshold_vgs_th: { symbol: "VGS(th)", group: "Electrical characteristics" },
  total_gate_charge_qg: { symbol: "Qg", group: "Electrical characteristics" },
  gate_source_charge_qgs: { symbol: "Qgs", group: "Electrical characteristics" },
  gate_drain_charge_qgd: { symbol: "Qgd", group: "Electrical characteristics" },
  input_capacitance_ciss: { symbol: "Ciss", group: "Electrical characteristics" },
  output_capacitance_coss: { symbol: "Coss", group: "Electrical characteristics" },
  reverse_recovery_time_trr: { symbol: "trr", group: "Electrical characteristics" },
  // Drivers
  supply_voltage_max: { symbol: "VCC(max)", group: "Absolute maximum ratings" },
  peak_source_current: { symbol: "IO+", group: "Electrical characteristics" },
  peak_sink_current: { symbol: "IO-", group: "Electrical characteristics" },
  propagation_delay: { symbol: "tpd", group: "Electrical characteristics" },
  channel_count: { symbol: "Channels", group: "Package & configuration" },
};

export function PartDetailPage() {
  const { id: paramId, partId } = useParams<{ id?: string; partId?: string }>();
  const id = paramId || partId;
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { isSelected, togglePart } = useCompareSelection();
  const { isInQueue, toggleItem: toggleReviewItem } = useReviewQueueStore();

  // Tab synchronization in URL
  const activeTab = searchParams.get("tab") || "specs";

  const handleTabChange = (newTab: string) => {
    setSearchParams({ tab: newTab });
  };

  const activeId = id ?? "";
  const partQuery = usePart(activeId);
  const part = partQuery.data;

  const alternativesQuery = useAlternatives(part?.part_id);
  const startJob = useStartExtractionJob();
  const downloadDatasheet = useDownloadDatasheet();

  // Selected parameter for Source Viewer Sheet
  const [selectedParam, setSelectedParam] = useState<ParameterValue | null>(null);
  const [sourceViewerOpen, setSourceViewerOpen] = useState(false);
  const sourceButtonRef = useRef<HTMLButtonElement | null>(null);

  // Filter toggles in specs tab (persisted in session)
  const savedDetail = partDetailSessionStore.get();
  const [onlyLowConfidence, setOnlyLowConfidence] = useState(() => savedDetail.onlyLowConfidence);
  const [showRejected, setShowRejected] = useState(() => savedDetail.showRejected);

  useEffect(() => {
    partDetailSessionStore.set({ onlyLowConfidence, showRejected });
  }, [onlyLowConfidence, showRejected]);

  // Background extraction job state
  const [jobId, setJobId] = useState<string | null>(null);
  const [downloadProgress, setDownloadProgress] = useState<number | null>(null);
  const jobQuery = useJob(jobId ?? undefined);
  const queryClient = useQueryClient();
  const jobState = jobQuery.data?.state;

  useEffect(() => {
    if (jobState === "completed") {
      void queryClient.invalidateQueries({ queryKey: queryKeys.part(activeId) });
      void queryClient.invalidateQueries({ queryKey: ["part"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.reviewQueue() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.stats() });
    }
  }, [jobState, activeId, queryClient]);

  const handleStartExtraction = () => {
    if (!part) return;
    startJob.mutate(
      { part_id: part.part_id },
      {
        onSuccess: (job) => {
          setJobId(job.job_id);
          toast.success("Extraction job started");
        },
        onError: (err: any) => {
          toast.error(err?.message || "Failed to start extraction job");
        },
      },
    );
  };

  const handleDownloadDatasheet = () => {
    if (!part) return;
    setDownloadProgress(0);
    downloadDatasheet.mutate(part.part_id, {
      onSuccess: async (source) => {
        try {
          await downloadFileWithProgress(
            `/api/sources/${encodeURIComponent(source.source_id)}/file`,
            `${part.mpn}-datasheet.pdf`,
            setDownloadProgress,
          );
          toast.success("Datasheet downloaded");
        } catch {
          setDownloadProgress(null);
          toast.error("The cached datasheet could not be downloaded.");
          return;
        }
        window.setTimeout(() => setDownloadProgress(null), 800);
      },
      onError: () => setDownloadProgress(null),
    });
  };

  const handleOpenSource = (param: ParameterValue, triggerEl?: HTMLButtonElement | null) => {
    sourceButtonRef.current = triggerEl ?? null;
    setSelectedParam(param);
    setSourceViewerOpen(true);
  };

  // Filtered and Grouped specs
  const parameters = useMemo(() => {
    let list = part?.parameters ?? [];
    if (onlyLowConfidence) {
      list = list.filter((p) => (p.confidence ?? 1.0) < 0.7);
    }
    if (!showRejected) {
      list = list.filter((p) => p.status !== "rejected");
    }
    return list;
  }, [part?.parameters, onlyLowConfidence, showRejected]);

  const groupedSpecs = useMemo(() => {
    const groups: Record<string, ParameterValue[]> = {
      "Absolute maximum ratings": [],
      "Electrical characteristics": [],
      "Thermal characteristics": [],
      "Package & configuration": [],
    };

    for (const p of parameters) {
      const meta = PARAM_SYMBOLS[p.name];
      const groupName = meta?.group || "Electrical characteristics";
      if (!groups[groupName]) {
        groups[groupName] = [];
      }
      groups[groupName].push(p);
    }

    return groups;
  }, [parameters]);

  // Loading Skeleton State
  if (partQuery.isPending) {
    return (
      <PageSkeleton
        title="Loading component specifications…"
        description="Fetching parametric values, live distributor offers, and datasheet references."
      />
    );
  }

  // Error State
  if (partQuery.isError) {
    return (
      <div className="py-12 w-full">
        <ErrorState
          title="Component could not be loaded"
          error={partQuery.error}
          onRetry={() => void partQuery.refetch()}
        />
      </div>
    );
  }

  // Not Found State
  if (!part) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh] text-center px-4 w-full">
        <div className="rounded-[12px] bg-[#121215] text-white p-8 max-w-md w-full border border-white/10 shadow-none">
          <div className="font-mono text-3xl font-bold mb-2">404</div>
          <h1 className="font-heading text-lg font-medium text-white mb-2">Component not found</h1>
          <p className="text-xs text-zinc-400 mb-6">
            The component ID &quot;{activeId}&quot; could not be located in the silicon index.
          </p>
          <Link
            to="/search"
            className="inline-flex items-center justify-center gap-2 rounded-[8px] bg-white px-4 py-2 text-xs font-medium text-black hover:bg-zinc-200 transition-none"
          >
            <span>Return to parametric search</span>
          </Link>
        </div>
      </div>
    );
  }

  const compared = isSelected(part.part_id);
  const inReview = isInQueue(part.part_id);
  const firstSourceParam = parameters.find((p) => p.source_id && p.page) || parameters[0];

  return (
    <div className="space-y-6 w-full">
      {/* Top back navigation */}
      <div>
        <Link
          to="/search"
          className="inline-flex items-center gap-1.5 rounded-[8px] px-2.5 py-1 text-xs text-zinc-400 hover:text-white hover:bg-white/5 transition-none select-none"
        >
          <ArrowLeft className="size-3.5" />
          <span>Back to search</span>
        </Link>
      </div>

      {/* Header (Clean, unboxed with hairline separator) */}
      <header className="space-y-6 pb-6 border-b border-white/10">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="font-heading text-3xl font-semibold tracking-tight text-white">
                {part.mpn}
              </h1>
              <StatusTag status={part.lifecycle_status ?? "unknown"} type="lifecycle" />
              <span className="rounded-[4px] border border-white/20 bg-white/5 px-2 py-0.5 text-xs font-mono uppercase text-zinc-300">
                {part.family}
              </span>
              {part.package && (
                <span className="rounded-[4px] border border-white/20 bg-white/5 px-2 py-0.5 text-xs font-mono text-zinc-300">
                  {part.package}
                </span>
              )}
            </div>

            <p className="text-xs text-zinc-400 font-sans max-w-2xl leading-relaxed">
              <span className="font-medium text-white">{part.manufacturer}</span>
              {part.description ? ` : ${part.description}` : ""}
            </p>
          </div>

          {/* Action Buttons */}
          <div className="flex flex-wrap items-center gap-2">
            {firstSourceParam && (
              <button
                type="button"
                onClick={() => handleOpenSource(firstSourceParam)}
                className="inline-flex items-center gap-1.5 rounded-[8px] border border-white/15 bg-white/5 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:text-white hover:bg-white/10 transition-none"
              >
                <FileText className="size-3.5" />
                <span>
                  {firstSourceParam.page ? "Open datasheet page" : "View source provenance"}
                </span>
              </button>
            )}

            {part.datasheet_url && (
              <button
                type="button"
                onClick={handleDownloadDatasheet}
                disabled={downloadDatasheet.isPending || downloadProgress !== null}
                className="inline-flex items-center gap-1.5 rounded-[8px] border border-white/15 bg-white/5 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:text-white hover:bg-white/10 disabled:opacity-50 transition-none"
              >
                {downloadDatasheet.isPending || downloadProgress !== null ? (
                  <MotionGridLoader size="xs" variant="default" />
                ) : (
                  <Download className="size-3.5" />
                )}
                <span>
                  {downloadDatasheet.isPending
                    ? "Preparing datasheet…"
                    : downloadProgress !== null
                      ? `Downloading ${downloadProgress}%`
                      : "Download datasheet"}
                </span>
              </button>
            )}

            {downloadProgress !== null && (
              <div className="basis-full max-w-xs space-y-1.5" aria-live="polite">
                <div className="flex justify-between items-center text-[10px] font-mono text-zinc-400">
                  <span className="flex items-center gap-1.5">
                    <MotionGridLoader size="xs" />
                    Datasheet stream
                  </span>
                  <span className="text-zinc-200 font-semibold">{downloadProgress}%</span>
                </div>
                <Progress value={downloadProgress} className="h-1.5 bg-white/10" />
              </div>
            )}

            <button
              type="button"
              onClick={() => toggleReviewItem(part)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-4 py-1.5 text-xs font-medium transition-all",
                inReview
                  ? "border-white/30 bg-white/20 text-white"
                  : "border-white/15 bg-white/5 text-zinc-300 hover:text-white hover:bg-white/10",
              )}
            >
              {inReview ? <Check className="size-3.5 text-white" /> : <ListPlus className="size-3.5" />}
              <span>{inReview ? "In Review Queue" : "Add to Review Queue"}</span>
            </button>

            <button
              type="button"
              onClick={() => togglePart({ id: part.part_id, mpn: part.mpn })}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-[8px] border px-3 py-1.5 text-xs font-medium transition-none",
                compared
                  ? "border-white bg-white/20 text-white"
                  : "border-white/15 bg-white/5 text-zinc-300 hover:text-white hover:bg-white/10",
              )}
            >
              <Scale className="size-3.5" />
              <span>{compared ? "Remove compare" : "Add to compare"}</span>
            </button>

            <button
              type="button"
              onClick={() => handleTabChange("alternatives")}
              className="inline-flex items-center gap-1.5 rounded-[8px] border border-white/15 bg-white/5 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:text-white hover:bg-white/10 transition-none"
            >
              <span>Find alternatives</span>
            </button>

            <button
              type="button"
              onClick={handleStartExtraction}
              disabled={startJob.isPending}
              aria-label="Start extraction"
              className="inline-flex items-center gap-1.5 rounded-[8px] bg-white px-3 py-1.5 text-xs font-medium text-black hover:bg-zinc-200 disabled:opacity-40 transition-none"
            >
              {startJob.isPending ? (
                <MotionGridLoader size="xs" variant="default" />
              ) : (
                <PlayCircle className="size-3.5" />
              )}
              <span>{startJob.isPending ? "Starting…" : "Start extraction"}</span>
            </button>
          </div>
        </div>

        {/* Live Extraction Job Progress Feedback */}
        {jobId && (
          <div className="rounded-[8px] border border-white/15 bg-white/5 p-4 text-xs font-mono space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <MotionGridLoader size="xs" />
                <span className="font-semibold text-white">Extraction Job {jobId}</span>
              </div>
              <StatusTag status={jobQuery.data?.state ?? "queued"} type="generic" />
            </div>
            <div className="text-[11px] text-zinc-400">
              {jobQuery.data?.message || "Running extraction pipeline..."}
            </div>
            {jobQuery.data?.progress !== undefined && (
              <div className="space-y-1">
                <Progress
                  value={
                    jobQuery.data.total ? (jobQuery.data.progress / jobQuery.data.total) * 100 : 25
                  }
                  className="h-1.5 bg-white/10"
                />
                <div className="flex justify-between text-[10px] text-zinc-500">
                  <span>Processed: {jobQuery.data.progress} / {jobQuery.data.total ?? 1}</span>
                  <span>{jobQuery.data.total ? Math.round((jobQuery.data.progress / jobQuery.data.total) * 100) : 25}%</span>
                </div>
              </div>
            )}
          </div>
        )}
      </header>

      {/* Tabs (State in URL): Specs, Offers, Alternatives, History */}
      <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-4 w-full">
        <TabsList className="rounded-full border border-white/15 bg-white/5 p-1 select-none">
          <TabsTrigger
            value="specs"
            className="rounded-full px-4 py-1.5 text-xs font-medium data-[state=active]:bg-white data-[state=active]:text-black text-zinc-400 transition"
          >
            Specs
          </TabsTrigger>
          <TabsTrigger
            value="offers"
            className="rounded-full px-4 py-1.5 text-xs font-medium data-[state=active]:bg-white data-[state=active]:text-black text-zinc-400 transition"
          >
            Offers ({part.offers?.length ?? 0})
          </TabsTrigger>
          <TabsTrigger
            value="alternatives"
            className="rounded-full px-4 py-1.5 text-xs font-medium data-[state=active]:bg-white data-[state=active]:text-black text-zinc-400 transition"
          >
            Alternatives
          </TabsTrigger>
          <TabsTrigger
            value="history"
            className="rounded-full px-4 py-1.5 text-xs font-medium data-[state=active]:bg-white data-[state=active]:text-black text-zinc-400 transition"
          >
            History
          </TabsTrigger>
        </TabsList>

        {/* Tab 1: Specs */}
        <TabsContent value="specs" className="space-y-6 w-full">
          {/* Specs Toggles */}
          <div className="flex flex-wrap items-center justify-between gap-3 text-xs border-b border-white/10 pb-3">
            <div className="flex flex-wrap items-center gap-4">
              <label className="flex items-center gap-1.5 text-zinc-300 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={onlyLowConfidence}
                  onChange={(e) => setOnlyLowConfidence(e.target.checked)}
                  className="size-3.5 rounded-[2px] border-white/20 bg-white/5 text-white"
                />
                <span>Only low confidence (&lt; 0.70)</span>
              </label>

              <label className="flex items-center gap-1.5 text-zinc-300 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={showRejected}
                  onChange={(e) => setShowRejected(e.target.checked)}
                  className="size-3.5 rounded-[2px] border-white/20 bg-white/5 text-white"
                />
                <span>Show rejected values</span>
              </label>
            </div>

            <span className="font-mono text-zinc-500 text-[11px]">
              {parameters.length} parameters extracted
            </span>
          </div>

          {/* Grouped Specs Tables (Unboxed, clean divider separation) */}
          <div className="space-y-8 w-full">
            {Object.entries(groupedSpecs).map(([groupTitle, items]) => {
              if (items.length === 0) return null;
              return (
                <div key={groupTitle} className="space-y-3">
                  <h3 className="font-mono text-xs uppercase font-bold tracking-wider text-zinc-400 border-b border-white/10 pb-2">
                    {groupTitle}
                  </h3>
                  <div className="overflow-x-auto border-b border-white/10">
                    <table className="w-full text-left text-xs font-sans">
                      <thead className="bg-white/[0.02] text-[11px] font-mono uppercase text-zinc-400 border-b border-white/10">
                        <tr>
                          <th className="px-3 py-2">Parameter</th>
                          <th className="px-3 py-2 font-mono">Min</th>
                          <th className="px-3 py-2 font-mono">Typ</th>
                          <th className="px-3 py-2 font-mono">Max</th>
                          <th className="px-3 py-2 font-mono">Unit</th>
                          <th className="px-3 py-2">Conditions</th>
                          <th className="px-3 py-2 text-right">Confidence</th>
                          <th className="px-3 py-2 text-right">Source</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5">
                        {items.map((p) => {
                          const meta = PARAM_SYMBOLS[p.name];
                          const displayName = humanizeParam(p.name);
                          const condText = formatCondition(p.condition);
                          const isAwaiting = p.status === "review";

                          return (
                            <tr key={p.param_id || p.name} className="hover:bg-white/[0.04]">
                              <td className="px-3 py-2 font-medium text-white">
                                <div className="flex items-center gap-1.5">
                                  <span>{displayName}</span>
                                  {isAwaiting && (
                                    <span className="rounded-[4px] border border-dashed border-white/30 px-1 py-0.2 text-[10px] font-mono text-zinc-400">
                                      Awaiting review
                                    </span>
                                  )}
                                </div>
                                {meta?.symbol && (
                                  <div className="font-mono text-[11px] text-zinc-500">
                                    {meta.symbol}
                                  </div>
                                )}
                              </td>
                              <td className="px-3 py-2 font-mono text-zinc-300">
                                {p.value_min !== null && p.value_min !== undefined
                                  ? formatNumber(p.value_min)
                                  : "-"}
                              </td>
                              <td className="px-3 py-2 font-mono text-zinc-200">
                                {formatValue(p.value ?? p.value_typ, p.unit)}
                              </td>
                              <td className="px-3 py-2 font-mono text-zinc-300">
                                {p.value_max !== null && p.value_max !== undefined
                                  ? formatNumber(p.value_max)
                                  : "-"}
                              </td>
                              <td className="px-3 py-2 font-mono text-zinc-400">{p.unit ?? "-"}</td>
                              <td className="px-3 py-2 text-zinc-400 text-[11px] max-w-xs truncate">
                                {condText || "-"}
                              </td>
                              <td className="px-3 py-2 text-right">
                                <div
                                  data-confidence={
                                    (p.confidence ?? 0) >= 0.9
                                      ? "high"
                                      : (p.confidence ?? 0) >= 0.7
                                        ? "medium"
                                        : "low"
                                  }
                                >
                                  <ConfidenceMeter confidence={p.confidence} surface="dark" />
                                </div>
                              </td>
                              <td className="px-3 py-2 text-right">
                                <button
                                  type="button"
                                  onClick={(e) => handleOpenSource(p, e.currentTarget)}
                                  aria-label="View source"
                                  className="rounded-[6px] border border-white/15 bg-white/5 px-2 py-1 font-mono text-[11px] text-zinc-300 hover:text-white hover:bg-white/10"
                                >
                                  {p.page ? `p. ${p.page}` : "View source"}
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            })}
          </div>
        </TabsContent>

        {/* Tab 2: Offers */}
        <TabsContent value="offers" className="space-y-4 w-full">
          <div className="space-y-4 w-full">
            <div className="overflow-x-auto border-b border-white/10">
              <table className="w-full text-left text-xs font-sans">
                <thead className="bg-white/[0.02] text-[11px] font-mono uppercase text-zinc-400 border-b border-white/10">
                  <tr>
                    <th className="px-3 py-2">Distributor</th>
                    <th className="px-3 py-2">SKU</th>
                    <th className="px-3 py-2 font-mono">Stock</th>
                    <th className="px-3 py-2 font-mono">Unit Price</th>
                    <th className="px-3 py-2">Currency</th>
                    <th className="px-3 py-2">Updated</th>
                    <th className="px-3 py-2 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {(part.offers ?? []).map((offer, idx) => (
                    <tr key={idx} className="hover:bg-white/[0.04]">
                      <td className="px-3 py-2 font-medium text-white">
                        {formatDistributorName(offer.distributor)}
                      </td>
                      <td className="px-3 py-2 font-mono text-[11px] text-zinc-400">
                        {offer.sku ?? "-"}
                      </td>
                      <td className="px-3 py-2 font-mono text-zinc-300">
                        {offer.stock ? offer.stock.toLocaleString() : "0"} units
                      </td>
                      <td className="px-3 py-2 font-mono text-white font-semibold">
                        {formatCurrencyPrice(offer.unit_price, offer.currency)}
                      </td>
                      <td className="px-3 py-2 font-mono text-zinc-400">
                        {offer.currency || "USD"}
                      </td>
                      <td className="px-3 py-2 text-zinc-500 text-[11px]">
                        {offer.fetched_at ? formatDate(offer.fetched_at) : "Recent"}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {offer.url ? (
                          <a
                            href={offer.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-white underline hover:text-zinc-300 text-xs"
                          >
                            Buy
                          </a>
                        ) : (
                          "-"
                        )}
                      </td>
                    </tr>
                  ))}
                  {(part.offers ?? []).length === 0 && (
                    <tr>
                      <td colSpan={7} className="px-3 py-8 text-center text-xs text-zinc-500">
                        No distributor offers recorded for this component.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="pt-2 text-[11px] text-zinc-500 font-sans">
              Prices and stock levels are sourced from distributor APIs and authorized web channels.
            </div>
          </div>
        </TabsContent>

        {/* Tab 3: Alternatives */}
        <TabsContent value="alternatives" className="space-y-4 w-full">
          <div className="space-y-4 w-full">
            <div className="text-xs text-zinc-400 border-b border-white/10 pb-3 flex items-center justify-between">
              <span>
                Ranked drop-in and functional alternatives matching electrical ratings and package.
              </span>
              <span className="font-mono text-[11px] text-zinc-500">
                {(alternativesQuery.data ?? []).filter((a) => !a.rejected || (a.score && a.score > 0)).length} alternatives computed
              </span>
            </div>

            <div className="divide-y divide-white/10">
              {(alternativesQuery.data ?? [])
                .filter((alt) => !alt.rejected || (alt.score && alt.score > 0))
                .map((alt) => (
                  <div
                    key={alt.part.part_id}
                    className="py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-white/[0.02] px-2 rounded-[6px] transition-colors"
                  >
                    <div className="space-y-1.5 flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-xs font-bold text-white bg-white/10 px-1.5 py-0.5 rounded">
                          #{alt.rank}
                        </span>
                        <Link
                          to={`/parts/${alt.part.part_id}`}
                          className="font-mono font-medium text-white hover:underline underline-offset-2"
                        >
                          {alt.part.mpn}
                        </Link>
                        <span className="text-zinc-400 text-xs">{alt.part.manufacturer}</span>
                        <StatusTag status={alt.part.lifecycle_status ?? "unknown"} type="lifecycle" />
                        {alt.score && alt.score > 0 && (
                          <span className="font-mono text-[11px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-1.5 py-0.2 rounded">
                            {Math.round(alt.score)}% match
                          </span>
                        )}
                        {alt.part.package && (
                          <span className="font-mono text-[11px] text-zinc-500">
                            {alt.part.package}
                          </span>
                        )}
                      </div>

                      <p className="text-xs text-zinc-300 font-sans">
                        {alt.reason || "Compatible pinout and package outline."}
                      </p>

                      {alt.differences && Object.keys(alt.differences).length > 0 && (
                        <div className="flex flex-wrap gap-2 text-[10px] font-mono text-zinc-400 pt-0.5">
                          {Object.entries(alt.differences).slice(0, 3).map(([key, diff]) => (
                            <span key={key} className="bg-white/5 border border-white/10 px-1.5 py-0.5 rounded">
                              {key}: {diff.candidate !== undefined && diff.candidate !== null ? diff.candidate : "-"}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        type="button"
                        onClick={() => navigate(`/parts/${alt.part.part_id}`)}
                        className="rounded-[6px] border border-white/15 bg-white/5 px-3 py-1 text-xs text-zinc-300 hover:text-white hover:bg-white/10 cursor-pointer"
                      >
                        Inspect
                      </button>
                      <button
                        type="button"
                        onClick={() => navigate(`/compare?ids=${part.part_id},${alt.part.part_id}`)}
                        className="rounded-[6px] border border-white/15 bg-white/5 px-3 py-1 text-xs text-zinc-300 hover:text-white hover:bg-white/10 cursor-pointer"
                      >
                        Compare
                      </button>
                    </div>
                  </div>
                ))}
              {(alternativesQuery.data ?? []).filter((a) => !a.rejected || (a.score && a.score > 0)).length === 0 && (
                <div className="py-12 text-center text-xs text-zinc-500 font-mono">
                  No direct alternatives computed for this component yet.
                </div>
              )}
            </div>
          </div>
        </TabsContent>

        {/* Tab 4: History */}
        <TabsContent value="history" className="space-y-4 w-full">
          <div className="space-y-4 text-xs font-mono w-full">
            <h3 className="font-bold text-sm uppercase text-white border-b border-white/10 pb-2">
              Datasheet Provenance & Extraction History
            </h3>
            <div className="space-y-2">
              {part.source_ids?.map((sid) => (
                <div key={sid} className="rounded-[6px] border border-white/10 bg-white/[0.02] p-3">
                  <div className="font-semibold text-white">Source ID: {sid}</div>
                  <div className="text-[11px] text-zinc-400 mt-1">
                    Indexed under local content-addressable storage
                  </div>
                </div>
              ))}
            </div>
          </div>
        </TabsContent>
      </Tabs>

      {/* Embedded Provenance Source Viewer Sheet */}
      {selectedParam && (
        <SourceViewer
          open={sourceViewerOpen}
          onOpenChange={setSourceViewerOpen}
          partId={part.part_id}
          paramId={selectedParam.param_id || selectedParam.name}
          value={selectedParam}
          triggerRef={sourceButtonRef}
        />
      )}
    </div>
  );
}
