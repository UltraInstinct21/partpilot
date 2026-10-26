import { useMemo, useState, useEffect } from "react";
import { Link, useSearchParams, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  Search,
  SlidersHorizontal,
  Download,
  Eye,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  RotateCcw,
  Sparkles,
  Cpu,
  Send,
  MessageSquare,
  ExternalLink,
  ListPlus,
  ClipboardList,
  Check,
} from "lucide-react";
import { toast } from "@/components/ui/toast";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { FilterChips } from "@/components/domain/filter-chips";
import { ConfidenceMeter } from "@/components/domain/confidence-meter";
import { StatusTag } from "@/components/domain/status-tag";
import { TableSkeleton } from "@/components/loading-skeleton";
import { MotionGridLoader, InlineProgressLoader } from "@/components/motion-grid-loader";
import { useSearch, useParts, useStats, queryKeys, streamSearch } from "@/api/hooks";
import type {
  ParameterConstraint,
  SearchFilter,
  Family,
  LifecycleStatus,
  PartRecord,
  PartSummary,
  SearchResponseWithWeb,
  WebSearchResult,
} from "@/api/hooks";
import { apiGet, apiPost } from "@/api/client";
import { useCompareSelection } from "@/lib/compare-store";
import { useReviewQueueStore } from "@/lib/review-queue-store";
import { searchSessionStore } from "@/lib/session-store";
import { downloadTextFile, toCsv, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

export function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { isSelected, togglePart, selectedParts } = useCompareSelection();
  const {
    isInQueue,
    toggleItem: toggleReviewItem,
    addItem: addReviewItem,
    totalCount: reviewQueueCount,
  } = useReviewQueueStore();
  const statsQuery = useStats();

  const manufacturers = useMemo(() => {
    const set = new Set<string>();
    if (statsQuery.data?.parts_by_manufacturer) {
      for (const m of Object.keys(statsQuery.data.parts_by_manufacturer)) {
        if (!m.includes("Synthetic") && m.trim()) set.add(m.trim());
      }
    }
    return Array.from(set).sort();
  }, [statsQuery.data]);

  // URL and Session state synchronization
  const savedSearch = searchSessionStore.get();
  const initialQuery = searchParams.get("q") ?? (savedSearch.query || "");
  const [queryInput, setQueryInput] = useState(initialQuery);
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const [askAiQuery, setAskAiQuery] = useState(() => savedSearch.askAiQuery || "");
  const [isAskingAi, setIsAskingAi] = useState(false);
  const [customAdvisory, setCustomAdvisory] = useState<any>(() => savedSearch.customAdvisory);
  const [isAdvisoryCollapsed, setIsAdvisoryCollapsed] = useState(false);
  const [showTradeoffs, setShowTradeoffs] = useState(false);

  useEffect(() => {
    if (!searchParams.get("q") && savedSearch.query) {
      setSearchParams({ q: savedSearch.query, page: String(savedSearch.page || 1) }, { replace: true });
    }
  }, []);

  const handleAskAi = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const prompt = askAiQuery.trim() || initialQuery.trim();
    if (!prompt) return;
    setIsAskingAi(true);
    try {
      const adv = await apiPost<any>("/api/search/advise", { query: prompt });
      setCustomAdvisory(adv);
      searchSessionStore.set({ customAdvisory: adv, askAiQuery: prompt });
    } catch (err) {
      console.error("AI Advisor error:", err);
    } finally {
      setIsAskingAi(false);
    }
  };

  // Column visibility saved in localStorage inside try/catch
  const [visibleColumns, setVisibleColumns] = useState<Record<string, boolean>>(() => {
    try {
      const saved = localStorage.getItem("partpilot_column_visibility");
      if (saved) return JSON.parse(saved);
    } catch {}
    return {
      select: true,
      mpn: true,
      manufacturer: true,
      family: true,
      package: true,
      lifecycle: true,
      vds: true,
      id: true,
      rds_on: true,
      qg: true,
      stock: true,
      confidence: true,
      review: true,
    };
  });

  const [colMenuOpen, setColMenuOpen] = useState(false);

  useEffect(() => {
    try {
      localStorage.setItem("partpilot_column_visibility", JSON.stringify(visibleColumns));
    } catch {}
  }, [visibleColumns]);

  const urlPage = parseInt(searchParams.get("page") || "1", 10);
  const pageSize = 25;
  const offset = (urlPage - 1) * pageSize;

  // Active filter state
  const [activeFilter, setActiveFilter] = useState<SearchFilter | null>(() => savedSearch.activeFilter);

  const hasQuery = Boolean(initialQuery.trim());

  // Search request payload (when query is present)
  // Progressive streaming search state (zero-wait local results + streaming web candidates)
  const [streamData, setStreamData] = useState<{
    results?: PartSummary[];
    total?: number;
    filter?: SearchFilter;
    filter_explanation?: string;
    web_results?: WebSearchResult[];
    provider_candidates?: PartSummary[];
    ai_advisory?: any;
    search_mode?: string;
    took_ms?: number;
    isStreaming?: boolean;
  } | null>(() => {
    if (savedSearch.query && (savedSearch.query === initialQuery || !initialQuery)) {
      return savedSearch.streamData;
    }
    return null;
  });

  useEffect(() => {
    if (!hasQuery || activeFilter) {
      return;
    }

    // Preserve existing results across page switching
    const currentSaved = searchSessionStore.get();
    if (
      currentSaved.query === initialQuery &&
      currentSaved.streamData?.results &&
      currentSaved.streamData.results.length > 0 &&
      !currentSaved.streamData.isStreaming
    ) {
      if (!streamData) {
        setStreamData(currentSaved.streamData);
      }
      return;
    }

    const ac = new AbortController();
    setStreamData({ isStreaming: true });

    void streamSearch(
      initialQuery,
      (ev) => {
        setStreamData((prev) => {
          const next = { ...(prev ?? {}), isStreaming: ev.type !== "done" };
          if (ev.filter) next.filter = ev.filter;
          if (ev.filter_explanation) next.filter_explanation = ev.filter_explanation;
          if (ev.results) next.results = ev.results;
          if (ev.total !== undefined) next.total = ev.total;
          if (ev.web_results) next.web_results = ev.web_results;
          if (ev.provider_candidates) next.provider_candidates = ev.provider_candidates;
          if (ev.ai_advisory) next.ai_advisory = ev.ai_advisory;
          if (ev.search_mode) next.search_mode = ev.search_mode;
          if (ev.took_ms !== undefined) next.took_ms = ev.took_ms;
          searchSessionStore.set({ streamData: next, query: initialQuery, page: urlPage });
          return next;
        });
      },
      pageSize,
      offset,
      ac.signal,
    );

    return () => ac.abort();
  }, [hasQuery, initialQuery, activeFilter, pageSize, offset]);

  // Search request payload (when query is present with direct filter edits)
  const searchRequest = useMemo(() => {
    if (!hasQuery || !activeFilter) {
      return null;
    }
    return {
      query: initialQuery,
      filter: activeFilter,
      limit: pageSize,
      offset,
    };
  }, [hasQuery, initialQuery, activeFilter, offset, pageSize]);

  const searchQuery = useSearch(searchRequest);

  // Catalogue browsing query (when no search query is present)
  const catalogueQuery = useParts(
    {
      limit: pageSize,
      offset,
      family: activeFilter?.family ? (activeFilter.family as any) : undefined,
      in_stock: activeFilter?.in_stock ?? undefined,
      package:
        activeFilter?.package_in && activeFilter.package_in.length === 1
          ? activeFilter.package_in[0]
          : (activeFilter?.package ?? undefined),
      packages:
        activeFilter?.package_in && activeFilter.package_in.length > 1
          ? activeFilter.package_in.join(",")
          : undefined,
      manufacturer:
        activeFilter?.manufacturer_in && activeFilter.manufacturer_in.length === 1
          ? activeFilter.manufacturer_in[0]
          : (activeFilter?.manufacturer ?? undefined),
      manufacturers:
        activeFilter?.manufacturer_in && activeFilter.manufacturer_in.length > 1
          ? activeFilter.manufacturer_in.join(",")
          : undefined,
      lifecycle_status:
        activeFilter?.lifecycle_status && activeFilter.lifecycle_status.length > 0
          ? activeFilter.lifecycle_status.join(",")
          : undefined,
    },
    { enabled: !hasQuery },
  );

  const isStreamingActive = Boolean(hasQuery && !activeFilter && streamData);
  const data = isStreamingActive
    ? {
        results: streamData?.results ?? [],
        total: streamData?.total ?? 0,
        filter: streamData?.filter,
        filter_explanation: streamData?.filter_explanation,
        web_results: streamData?.web_results ?? [],
        provider_candidates: streamData?.provider_candidates ?? [],
        ai_advisory: streamData?.ai_advisory,
        took_ms: streamData?.took_ms,
        search_mode: streamData?.search_mode ?? "catalogue",
      }
    : (hasQuery ? searchQuery.data : catalogueQuery.data);

  const isFetching = isStreamingActive
    ? Boolean(streamData?.isStreaming)
    : (hasQuery ? searchQuery.isFetching : catalogueQuery.isFetching);

  const isLoading = isStreamingActive
    ? Boolean(streamData?.isStreaming && (!streamData?.results || streamData.results.length === 0))
    : (hasQuery ? searchQuery.isLoading : catalogueQuery.isLoading);

  const isError = hasQuery && activeFilter ? searchQuery.isError : catalogueQuery.isError;
  const error = hasQuery && activeFilter ? searchQuery.error : catalogueQuery.error;

  const activeQuery = {
    isFetching,
    isLoading,
    isError,
    error,
    refetch: hasQuery ? searchQuery.refetch : catalogueQuery.refetch,
  };

  const webData = data as SearchResponseWithWeb | undefined;
  const webResults: WebSearchResult[] = webData?.web_results ?? [];
  const providerCandidates = webData?.provider_candidates ?? [];

  const results = useMemo(() => {
    const list = [...(data?.results ?? [])];
    const seenMpns = new Set(list.map((p) => p.mpn.toUpperCase()));

    for (const cand of providerCandidates) {
      if (!cand.mpn || seenMpns.has(cand.mpn.toUpperCase())) continue;
      seenMpns.add(cand.mpn.toUpperCase());
      list.push(cand);
    }

    for (const web of webResults) {
      if (!web.title && !web.url) continue;
      const text = `${web.title ?? ""} ${web.snippet ?? ""}`.toUpperCase();
      const tokens = text.match(/\b[A-Z0-9]+(?:[-/][A-Z0-9]+)+\b|\b[A-Z0-9]{3,24}\b/g) || [];
      const mpnCandidate = tokens.find(
        (t) => /[A-Z]/.test(t) && /\d/.test(t) && t.length >= 3 && t.length <= 24
      );
      if (!mpnCandidate || seenMpns.has(mpnCandidate.toUpperCase())) continue;
      seenMpns.add(mpnCandidate.toUpperCase());

      let family: Family = "general";
      const lower = text.toLowerCase();
      if (lower.includes("mosfet") || lower.includes("fet")) family = "mosfet";
      else if (lower.includes("gate driver") || lower.includes("gate-driver")) family = "gate_driver";
      else if (lower.includes("mcu") || lower.includes("microcontroller")) family = "mcu";

      let manufacturer = "Web Discovered";
      if (lower.includes("infineon")) manufacturer = "Infineon";
      else if (lower.includes("texas instruments") || lower.includes("ti.com")) manufacturer = "Texas Instruments";
      else if (lower.includes("stmicroelectronics") || lower.includes("st.com")) manufacturer = "STMicroelectronics";
      else if (lower.includes("vishay")) manufacturer = "Vishay Siliconix";
      else if (lower.includes("onsemi") || lower.includes("on semi")) manufacturer = "onsemi";
      else if (lower.includes("nexperia")) manufacturer = "Nexperia";
      else if (lower.includes("microchip")) manufacturer = "Microchip Technology";

      const key_parameters: Record<string, number | null> = {};
      const vMatch = lower.match(/\b(\d+(?:\.\d+)?)\s*v(?:olts?)?\b/);
      if (vMatch) key_parameters["vds_max"] = parseFloat(vMatch[1]);
      const iMatch = lower.match(/\b(\d+(?:\.\d+)?)\s*a\b/);
      if (iMatch) key_parameters["id_continuous"] = parseFloat(iMatch[1]);
      const rMatch = lower.match(/\b(\d+(?:\.\d+)?)\s*(?:m[oO]hm|mΩ)\b/);
      if (rMatch) key_parameters["rds_on"] = parseFloat(rMatch[1]) / 1000;

      let pkg: string | null = null;
      const pkgMatch = text.match(/\b(TO-220|TO-263|TO-252|SOIC-?8|SO-?8|D2PAK|SuperSO8)\b/i);
      if (pkgMatch) pkg = pkgMatch[1];

      const slug = mpnCandidate.toLowerCase().replace(/[^a-z0-9]+/g, "-");
      const offersCount = web.offers?.length ?? 0;
      const totalStock = web.offers?.reduce((acc, o) => acc + (o.stock ?? 0), 0) ?? null;

      list.push({
        part_id: `web-${family}-${slug}`,
        mpn: mpnCandidate,
        manufacturer,
        family,
        package: pkg,
        lifecycle_status: offersCount > 0 ? "active" : "unknown",
        datasheet_url: web.url,
        description: web.snippet || web.title,
        key_parameters,
        offers_count: offersCount,
        total_stock: totalStock,
        score: 0.85,
      });
    }
    return list;
  }, [data?.results, webResults, providerCandidates]);

  const total = Math.max(data?.total ?? 0, results.length);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  // Sync query input when URL param changes
  useEffect(() => {
    setQueryInput(initialQuery);
  }, [initialQuery]);

  // Decoupled filter reference to prevent duplicate queries on first load
  const currentFilter = activeFilter ?? data?.filter ?? null;

  // Pre-fetch row detail on hover (50ms cache)
  const handleRowPrefetch = (partId: string) => {
    void queryClient.prefetchQuery({
      queryKey: queryKeys.part(partId),
      queryFn: () => apiGet<PartRecord>(`/api/parts/${encodeURIComponent(partId)}`),
      staleTime: 50_000,
    });
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = queryInput.trim();
    if (!trimmed) return;
    searchSessionStore.reset();
    setActiveFilter(null);
    setStreamData(null);
    setSearchParams({ q: trimmed, page: "1" });
  };

  const handlePageChange = (newPage: number) => {
    if (newPage < 1 || newPage > totalPages) return;
    searchSessionStore.set({ page: newPage });
    setSearchParams({ q: initialQuery, page: String(newPage) });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleFilterChange = (newFilter: SearchFilter) => {
    setActiveFilter(newFilter);
    searchSessionStore.set({ activeFilter: newFilter });
    setSearchParams({ q: initialQuery, page: "1" });
  };

  const handleRemoveChip = (key: string) => {
    if (!currentFilter) return;
    const next = { ...currentFilter };
    if (key === "family") delete next.family;
    else if (key === "manufacturer_in") delete next.manufacturer_in;
    else if (key === "package_in") delete next.package_in;
    else if (key === "lifecycle_status") delete next.lifecycle_status;
    else if (key === "in_stock") delete next.in_stock;
    else if (next.parameters) {
      next.parameters = next.parameters.filter((p) => p.name !== key);
      if (next.parameters.length === 0) delete next.parameters;
    }
    handleFilterChange(next);
  };

  const handleFamilyChange = (family: Family | "all") => {
    const next: SearchFilter = { ...(currentFilter ?? {}) };
    if (family === "all") delete next.family;
    else next.family = family;
    handleFilterChange(next);
  };

  const handleManufacturerToggle = (mfr: string) => {
    const next: SearchFilter = { ...(currentFilter ?? {}) };
    const current = next.manufacturer_in ?? [];
    if (current.includes(mfr)) {
      next.manufacturer_in = current.filter((m) => m !== mfr);
      if (next.manufacturer_in.length === 0) delete next.manufacturer_in;
    } else {
      next.manufacturer_in = [...current, mfr];
    }
    handleFilterChange(next);
  };

  const handlePackageToggle = (pkg: string) => {
    const next: SearchFilter = { ...(currentFilter ?? {}) };
    const current = next.package_in ?? [];
    if (current.includes(pkg)) {
      next.package_in = current.filter((p) => p !== pkg);
      if (next.package_in.length === 0) delete next.package_in;
    } else {
      next.package_in = [...current, pkg];
    }
    handleFilterChange(next);
  };

  const handleLifecycleToggle = (status: LifecycleStatus) => {
    const next: SearchFilter = { ...(currentFilter ?? {}) };
    const current = next.lifecycle_status ?? [];
    if (current.includes(status)) {
      next.lifecycle_status = current.filter((s) => s !== status);
      if (next.lifecycle_status.length === 0) delete next.lifecycle_status;
    } else {
      next.lifecycle_status = [...current, status];
    }
    handleFilterChange(next);
  };

  const handleParamRangeToggle = (
    paramName: string,
    min: number | undefined,
    max: number | undefined,
    unit: string,
  ) => {
    const next: SearchFilter = { ...(currentFilter ?? {}) };
    const currentParams = [...(next.parameters ?? [])].filter((p) => p.name !== paramName);

    const existing = (next.parameters ?? []).find((p) => p.name === paramName);
    const isSame = existing && existing.min === min && existing.max === max;

    if (!isSame && (min !== undefined || max !== undefined)) {
      let operator: ParameterConstraint["operator"] = "between";
      if (min !== undefined && max === undefined) operator = "gte";
      else if (min === undefined && max !== undefined) operator = "lte";

      currentParams.push({
        name: paramName,
        min,
        max,
        unit,
        operator,
      });
    }

    if (currentParams.length > 0) {
      next.parameters = currentParams;
    } else {
      delete next.parameters;
    }
    handleFilterChange(next);
  };

  const handleInStockToggle = (inStock: boolean) => {
    const next: SearchFilter = { ...(currentFilter ?? {}) };
    if (!inStock) delete next.in_stock;
    else next.in_stock = true;
    handleFilterChange(next);
  };

  // CSV Export for visible columns
  const handleExportCsv = () => {
    if (results.length === 0) return;
    const rows = results.map((part) => {
      const record: Record<string, unknown> = {};
      if (visibleColumns.mpn) record["MPN"] = part.mpn;
      if (visibleColumns.manufacturer) record["Manufacturer"] = part.manufacturer;
      if (visibleColumns.family) record["Family"] = part.family;
      if (visibleColumns.package) record["Package"] = part.package ?? "";
      if (visibleColumns.lifecycle) record["Lifecycle"] = part.lifecycle_status ?? "";
      if (visibleColumns.stock) record["Stock"] = part.total_stock ?? 0;
      if (visibleColumns.confidence) record["Confidence"] = part.score ?? "";
      if (visibleColumns.vds) record["Vds (V)"] = part.key_parameters?.vds_max ?? "";
      if (visibleColumns.id) record["Id (A)"] = part.key_parameters?.id_continuous ?? "";
      if (visibleColumns.rds_on) record["Rds(on) (Ω)"] = part.key_parameters?.rds_on ?? "";
      if (visibleColumns.qg) record["Qg (C)"] = part.key_parameters?.total_gate_charge_qg ?? "";
      return record;
    });

    const csv = toCsv(rows);
    downloadTextFile(`partpilot-export-${Date.now()}.csv`, csv, "text/csv;charset=utf-8;");
  };

  const isMosfetOnly = currentFilter?.family === "mosfet";
  const isDriverOnly = currentFilter?.family === "gate_driver";
  const advisory = customAdvisory || webData?.ai_advisory;

  return (
    <div className="space-y-8 w-full">
      {/* Search Header on Top - Clean, unboxed */}
      <div className="space-y-4 pb-6 border-b border-white/10">
        {activeQuery.isFetching && (
          <InlineProgressLoader
            label="Searching catalogue and scraping live sources…"
          />
        )}
        <form onSubmit={handleSearchSubmit} className="w-full">
          <label htmlFor="search-input" className="sr-only">
            Query
          </label>
          <div className="relative flex flex-col sm:flex-row items-stretch sm:items-center gap-2 rounded-[8px] border border-white/15 bg-white/[0.03] p-1.5 focus-within:border-white/35 transition-colors">
            <div className="flex items-center flex-1 px-3 py-1">
              <Search className="size-4 text-zinc-400 mr-2.5 shrink-0" />
              <input
                id="search-input"
                aria-label="Query"
                type="text"
                value={queryInput}
                onChange={(e) => setQueryInput(e.target.value)}
                placeholder="Search by engineering description (e.g. 100 V N-channel MOSFET, Rds(on) < 5 mΩ)..."
                className="w-full bg-transparent font-sans text-sm text-white placeholder:text-zinc-500 outline-none"
              />
            </div>
            <button
              type="submit"
              disabled={!queryInput.trim() || activeQuery.isFetching}
              className="rounded-[6px] bg-white px-5 py-2 text-xs font-medium text-black hover:bg-zinc-200 active:bg-zinc-300 transition-none whitespace-nowrap disabled:opacity-40 cursor-pointer"
            >
              Search
            </button>
          </div>
        </form>

        {/* "Understood as" filter chip rail */}
        {currentFilter && (
          <div className="pt-2">
            <FilterChips
              filter={currentFilter}
              explanation={data?.filter_explanation}
              onChange={handleFilterChange}
              surface="dark"
            />
          </div>
        )}
      </div>

      <div className="flex flex-col lg:flex-row items-start gap-8 w-full">
        {/* Mobile Filter Button */}
        <div className="lg:hidden w-full flex justify-between items-center">
          <Sheet open={mobileFiltersOpen} onOpenChange={setMobileFiltersOpen}>
            <SheetTrigger asChild>
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded-[8px] border border-white/20 bg-white/5 px-3 py-1.5 text-xs text-white"
              >
                <SlidersHorizontal className="size-3.5" />
                <span>Filters</span>
              </button>
            </SheetTrigger>
            <SheetContent
              side="left"
              className="w-[320px] bg-black text-white p-6 border-r border-white/10 overflow-y-auto"
            >
              <SheetHeader className="p-0 border-0 mb-4">
                <SheetTitle className="font-heading text-base font-semibold text-white">
                  Filter Components
                </SheetTitle>
              </SheetHeader>
              <FilterRailContent
                activeFilter={currentFilter}
                manufacturers={manufacturers}
                onFamilyChange={handleFamilyChange}
                onMfrToggle={handleManufacturerToggle}
                onPackageToggle={handlePackageToggle}
                onLifecycleToggle={handleLifecycleToggle}
                onParamRangeToggle={handleParamRangeToggle}
                onInStockToggle={handleInStockToggle}
              />
            </SheetContent>
          </Sheet>

          <span className="text-xs font-mono text-zinc-400">
            {total} component{total === 1 ? "" : "s"}
          </span>
        </div>

        {/* Desktop Filter Rail (Clean, border-r separation without outer card box) */}
        <aside className="hidden lg:block w-72 shrink-0 pr-8 lg:border-r border-white/10 space-y-6">
          <div className="flex items-center justify-between border-b border-white/10 pb-3">
            <span className="font-mono text-xs uppercase font-bold tracking-wider text-white">
              Filter Rail
            </span>
            {currentFilter && Object.keys(currentFilter).length > 0 && (
              <button
                type="button"
                onClick={() => handleFilterChange({})}
                className="text-[11px] font-mono text-zinc-400 hover:text-white underline cursor-pointer"
              >
                Reset all
              </button>
            )}
          </div>

          <FilterRailContent
            activeFilter={currentFilter}
            manufacturers={manufacturers}
            onFamilyChange={handleFamilyChange}
            onMfrToggle={handleManufacturerToggle}
            onPackageToggle={handlePackageToggle}
            onLifecycleToggle={handleLifecycleToggle}
            onParamRangeToggle={handleParamRangeToggle}
            onInStockToggle={handleInStockToggle}
          />
        </aside>

        {/* Results Area (Unboxed, clean table with divider lines) */}
        <div className="flex-1 min-w-0 space-y-6">
          {/* Header Controls: Count, Column Visibility, CSV Export */}
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-3">
            <div className="font-mono text-xs text-zinc-400">
              <span className="font-semibold text-white">{total}</span> part{total === 1 ? "" : "s"}{" "}
              indexed
              {data?.took_ms !== undefined && (
                <span className="ml-1.5 opacity-60">({data.took_ms} ms)</span>
              )}
              {webData && (
                <span className="ml-2 rounded border border-white/15 bg-white/5 px-1.5 py-0.5 text-[10px] font-mono text-zinc-300 uppercase tracking-wider">
                  {webData.search_mode === "catalogue" ? "Indexed only" : "Live discovery merged"}
                </span>
              )}
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              {/* Add Selected to Review Queue */}
              {selectedParts.length > 0 && (
                <button
                  type="button"
                  onClick={() => {
                    let added = 0;
                    for (const sel of selectedParts) {
                      const foundPart = results.find((r) => r.part_id === sel.id) || {
                        part_id: sel.id,
                        mpn: sel.mpn,
                      };
                      if (!isInQueue(foundPart.part_id)) {
                        addReviewItem(foundPart);
                        added++;
                      }
                    }
                    if (added === 0 && selectedParts.length > 0) {
                      toast.info("Selected parts are already in your Review Queue.");
                    }
                  }}
                  className="inline-flex items-center gap-1.5 rounded-full border border-white/20 bg-white/10 px-3.5 py-1 text-xs text-white hover:bg-white/20 font-medium transition-colors"
                >
                  <ListPlus className="size-3.5" />
                  <span>Add {selectedParts.length} to Review</span>
                </button>
              )}

              {/* Review Queue Link */}
              {reviewQueueCount > 0 && (
                <button
                  type="button"
                  onClick={() => navigate("/review")}
                  className="inline-flex items-center gap-1.5 rounded-full border border-white/20 bg-white/10 px-3.5 py-1 text-xs text-white hover:bg-white/15 font-medium transition-colors"
                >
                  <ClipboardList className="size-3.5 text-zinc-300" />
                  <span>Review Queue ({reviewQueueCount})</span>
                  <ChevronRight className="size-3" />
                </button>
              )}

              {/* Column Visibility Menu */}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setColMenuOpen(!colMenuOpen)}
                  aria-label="Toggle visible columns"
                  className="inline-flex items-center gap-1.5 rounded-[8px] border border-white/15 bg-white/5 px-2.5 py-1 text-xs text-zinc-300 hover:text-white hover:bg-white/10"
                >
                  <Eye className="size-3.5" />
                  <span>Columns</span>
                </button>

                {colMenuOpen && (
                  <div className="absolute right-0 mt-1 w-48 rounded-[8px] border border-white/15 bg-[#18181c] p-2 text-xs shadow-none z-50 space-y-1">
                    <div className="font-mono uppercase text-[10px] font-bold text-zinc-400 px-2 py-1">
                      Toggle Columns
                    </div>
                    {Object.keys(visibleColumns).map((col) => (
                      <label
                        key={col}
                        className="flex items-center gap-2 px-2 py-1 rounded-[4px] hover:bg-white/5 cursor-pointer font-mono text-[11px] text-zinc-300 hover:text-white"
                      >
                        <input
                          type="checkbox"
                          checked={visibleColumns[col]}
                          onChange={(e) =>
                            setVisibleColumns({ ...visibleColumns, [col]: e.target.checked })
                          }
                          className="size-3.5 rounded-[2px]"
                        />
                        <span className="capitalize">{col.replace("_", " ")}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>

              {/* Client-side CSV Export */}
              <button
                type="button"
                onClick={handleExportCsv}
                aria-label="Export visible columns as CSV"
                className="inline-flex items-center gap-1.5 rounded-[8px] border border-white/15 bg-white/5 px-2.5 py-1 text-xs text-zinc-300 hover:text-white hover:bg-white/10"
              >
                <Download className="size-3.5" />
                <span>Export CSV</span>
              </button>
            </div>
          </div>

          {/* AI Engineering Advisor & Component Recommendations (Clean insight block) */}
          {advisory && (
            <section
              aria-label="Engineering recommendations and advisor"
              className="border-l-2 border-white/35 pl-5 py-4 my-2 text-xs font-sans space-y-4 bg-white/[0.02] rounded-r-[8px]"
            >
              {/* Header */}
              <div className="flex items-center justify-between gap-3 border-b border-white/10 pb-3">
                <div className="flex items-center gap-2">
                  <Sparkles className="size-4 text-zinc-300" />
                  <span className="font-medium text-sm text-white tracking-tight">
                    AI Engineering Advisor
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => setIsAdvisoryCollapsed((prev) => !prev)}
                  className="inline-flex items-center gap-1 text-[11px] text-zinc-400 hover:text-white transition-colors cursor-pointer"
                  aria-expanded={!isAdvisoryCollapsed}
                >
                  <span>{isAdvisoryCollapsed ? "Show details" : "Collapse"}</span>
                  {isAdvisoryCollapsed ? (
                    <ChevronDown className="size-3.5" />
                  ) : (
                    <ChevronUp className="size-3.5" />
                  )}
                </button>
              </div>

              {/* If collapsed, show a single clean summary line */}
              {isAdvisoryCollapsed ? (
                <p className="text-zinc-400 text-xs line-clamp-1">
                  {advisory.verdict || advisory.summary}
                </p>
              ) : (
                <>
                  {/* Key Takeaway / Verdict */}
                  {advisory.verdict && (
                    <div className="py-2 space-y-1 border-b border-white/5">
                      <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 font-semibold">
                        Key Takeaway
                      </div>
                      <p className="text-xs text-zinc-200 leading-relaxed">
                        {advisory.verdict}
                      </p>
                    </div>
                  )}

                  {/* Summary */}
                  {advisory.summary && (
                    <p className="text-zinc-400 text-xs leading-relaxed">
                      {advisory.summary}
                    </p>
                  )}

                  {/* Recommendations Grid */}
                  {advisory.recommendations && advisory.recommendations.length > 0 && (
                    <div className="space-y-2.5">
                      <div className="flex items-center justify-between text-[11px] uppercase tracking-wider text-zinc-400 font-semibold">
                        <div className="flex items-center gap-1.5">
                          <Cpu className="size-3 text-zinc-400" />
                          <span>Recommended Parts</span>
                        </div>
                        <span className="text-[10px] font-sans lowercase text-zinc-500 font-normal">
                          {advisory.recommendations.length} options evaluated
                        </span>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                        {advisory.recommendations.map((rec: any, idx: number) => (
                          <div
                            key={idx}
                            className="rounded-[8px] border border-white/10 bg-white/[0.02] p-3.5 space-y-2.5 hover:border-white/20 transition-colors flex flex-col justify-between"
                          >
                            <div className="space-y-1.5">
                              <div className="flex items-start justify-between gap-2">
                                <div>
                                  <div className="font-mono font-medium text-white text-xs">
                                    {rec.mpn}
                                  </div>
                                  <div className="text-[11px] text-zinc-300 font-medium mt-0.5">
                                    {rec.title}
                                  </div>
                                </div>
                                <div className="flex items-center gap-1.5">
                                  <button
                                    type="button"
                                    onClick={() => {
                                      const existing = results.find(
                                        (r) => r.mpn.toLowerCase() === rec.mpn.toLowerCase(),
                                      );
                                      const partCandidate = existing || {
                                        part_id: `rec-${rec.mpn.toLowerCase().replace(/[^a-z0-9]/g, "-")}`,
                                        mpn: rec.mpn,
                                        manufacturer: "AI Recommended",
                                        family: "general",
                                        description: rec.title || rec.why_choose,
                                      };
                                      toggleReviewItem(partCandidate);
                                    }}
                                    className={cn(
                                      "text-[11px] border px-3 py-0.5 rounded-full transition-colors inline-flex items-center gap-1",
                                      isInQueue(`rec-${rec.mpn.toLowerCase().replace(/[^a-z0-9]/g, "-")}`) ||
                                        results.some(
                                          (r) =>
                                            r.mpn.toLowerCase() === rec.mpn.toLowerCase() &&
                                            isInQueue(r.part_id),
                                        )
                                        ? "border-white/30 bg-white/15 text-white"
                                        : "border-white/15 bg-white/5 hover:bg-white/10 text-zinc-300 hover:text-white",
                                    )}
                                    title="Add to Review Queue for final evaluation"
                                  >
                                    <ListPlus className="size-3" />
                                    <span>Review</span>
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setQueryInput(rec.mpn);
                                      setSearchParams({ q: rec.mpn });
                                    }}
                                    className="text-[11px] border border-white/15 bg-white/5 hover:bg-white/10 text-zinc-300 hover:text-white px-2 py-0.5 rounded transition-colors"
                                    title={`Filter table by ${rec.mpn}`}
                                  >
                                    Filter
                                  </button>
                                </div>
                              </div>

                              <p className="text-xs text-zinc-400 leading-relaxed">
                                {rec.why_choose}
                              </p>
                            </div>

                            {((rec.pros && rec.pros.length > 0) || (rec.cons && rec.cons.length > 0)) && (
                              <div className="flex flex-wrap gap-1.5 pt-1 border-t border-white/5">
                                {rec.pros?.slice(0, 2).map((pro: string, pIdx: number) => (
                                  <span
                                    key={pIdx}
                                    className="text-[10px] bg-white/5 border border-white/10 text-zinc-300 px-2 py-0.5 rounded"
                                  >
                                    {pro}
                                  </span>
                                ))}
                                {rec.cons && rec.cons.length > 0 && (
                                  <span className="text-[10px] bg-white/[0.02] border border-white/10 text-zinc-400 px-2 py-0.5 rounded">
                                    {rec.cons[0]}
                                  </span>
                                )}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Tradeoffs & Substitutes */}
                  {(advisory.tradeoffs ||
                    (advisory.substitutes && advisory.substitutes.length > 0)) && (
                    <div className="border-t border-white/10 pt-2.5">
                      <button
                        type="button"
                        onClick={() => setShowTradeoffs((prev) => !prev)}
                        className="flex items-center justify-between w-full py-1 text-left text-xs text-zinc-400 hover:text-white transition-colors"
                        aria-expanded={showTradeoffs}
                      >
                        <span className="font-semibold text-[11px] uppercase tracking-wider">
                          Tradeoffs & Alternatives
                        </span>
                        <span className="text-[11px] text-zinc-400 flex items-center gap-1">
                          {showTradeoffs ? "Hide" : "Show"}
                          {showTradeoffs ? (
                            <ChevronUp className="size-3.5" />
                          ) : (
                            <ChevronDown className="size-3.5" />
                          )}
                        </span>
                      </button>

                      {showTradeoffs && (
                        <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4 pt-1 text-xs">
                          {advisory.tradeoffs && (
                            <div className="space-y-2 rounded-[8px] border border-white/10 bg-white/[0.02] p-3">
                              <span className="block text-[10px] uppercase font-mono tracking-wider text-zinc-400 font-semibold">
                                Design Tradeoffs
                              </span>
                              {advisory.tradeoffs.performance_vs_power && (
                                <p className="text-zinc-400 leading-relaxed">
                                  <span className="text-zinc-200 font-medium">Power vs Compute:</span>{" "}
                                  {advisory.tradeoffs.performance_vs_power}
                                </p>
                              )}
                              {advisory.tradeoffs.sourcing_and_lead_time && (
                                <p className="text-zinc-400 leading-relaxed">
                                  <span className="text-zinc-200 font-medium">Supply & Sourcing:</span>{" "}
                                  {advisory.tradeoffs.sourcing_and_lead_time}
                                </p>
                              )}
                            </div>
                          )}

                          {advisory.substitutes && advisory.substitutes.length > 0 && (
                            <div className="space-y-2 rounded-[8px] border border-white/10 bg-white/[0.02] p-3">
                              <span className="block text-[10px] uppercase font-mono tracking-wider text-zinc-400 font-semibold">
                                Cross Alternatives
                              </span>
                              <div className="space-y-2">
                                {advisory.substitutes.map((sub: any, sIdx: number) => (
                                  <div key={sIdx} className="text-zinc-400 leading-relaxed">
                                    <span className="font-mono text-zinc-200 font-medium">
                                      {sub.mpn}
                                    </span>
                                    : {sub.description}{" "}
                                    <span className="text-zinc-500">({sub.tradeoff})</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Ask AI Input */}
                  <form
                    onSubmit={handleAskAi}
                    className="pt-3 border-t border-white/10 flex items-center gap-2"
                  >
                    <div className="relative flex-1">
                      <MessageSquare className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-zinc-500" />
                      <input
                        type="text"
                        placeholder="Ask engineering question (e.g., 'Which one has lowest sleep current?')..."
                        value={askAiQuery}
                        onChange={(e) => setAskAiQuery(e.target.value)}
                        className="w-full pl-8 pr-3 py-1.5 bg-white/5 border border-white/15 rounded-[6px] text-xs text-white placeholder:text-zinc-500 focus:outline-none focus:border-white/40"
                      />
                    </div>
                    <button
                      type="submit"
                      disabled={isAskingAi || (!askAiQuery.trim() && !initialQuery.trim())}
                      className="inline-flex items-center gap-1.5 rounded-[6px] bg-white px-3 py-1.5 text-xs font-medium text-black hover:bg-zinc-200 disabled:opacity-40 transition-colors shrink-0"
                    >
                      {isAskingAi ? (
                        <>
                          <MotionGridLoader size="xs" variant="default" />
                          <span>Thinking...</span>
                        </>
                      ) : (
                        <>
                          <Send className="size-3" />
                          <span>Ask AI</span>
                        </>
                      )}
                    </button>
                  </form>
                </>
              )}
            </section>
          )}

          {/* Error Message */}
          {activeQuery.isError && (
            <div className="rounded-[8px] border border-white/20 bg-white/5 p-4 text-xs font-mono flex items-start justify-between gap-3">
              <div className="flex items-start gap-2">
                <AlertTriangle className="size-4 shrink-0 text-white mt-0.5" />
                <div>
                  <div className="font-semibold text-white">Search request failed</div>
                  <div className="text-zinc-400 mt-0.5">{activeQuery.error?.message}</div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => void activeQuery.refetch()}
                className="rounded-[6px] border border-white/20 bg-white/10 px-2.5 py-1 text-xs text-white hover:bg-white/20 flex items-center gap-1"
              >
                <RotateCcw className="size-3" />
                Retry
              </button>
            </div>
          )}

          {/* Loading Skeleton */}
          {activeQuery.isLoading && <TableSkeleton rows={8} cols={7} />}

          {/* Empty State */}
          {!activeQuery.isLoading && results.length === 0 && (
            <div className="py-16 text-center text-xs text-zinc-400 space-y-4">
              <p className="text-sm font-medium text-white">No parts match these filters.</p>
              <div className="flex flex-wrap items-center justify-center gap-2">
                {currentFilter?.family && (
                  <button
                    type="button"
                    onClick={() => handleRemoveChip("family")}
                    className="rounded-full border border-white/20 px-3 py-1 text-xs text-zinc-300 hover:bg-white/10"
                  >
                    Remove family: {currentFilter.family}
                  </button>
                )}
                {currentFilter?.manufacturer_in?.map((mfr: string) => (
                  <button
                    key={mfr}
                    type="button"
                    onClick={() => handleManufacturerToggle(mfr)}
                    className="rounded-full border border-white/20 px-3 py-1 text-xs text-zinc-300 hover:bg-white/10"
                  >
                    Remove {mfr}
                  </button>
                ))}
                {currentFilter?.parameters?.map((p: ParameterConstraint) => (
                  <button
                    key={p.name}
                    type="button"
                    onClick={() => handleRemoveChip(p.name)}
                    className="rounded-full border border-white/20 px-3 py-1 text-xs text-zinc-300 hover:bg-white/10"
                  >
                    Remove {p.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Results Table (TanStack Table, clean separation without heavy outer box) */}
          {!activeQuery.isLoading && results.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-sans border-b border-white/10">
                {/* Sticky Header with Units */}
                <thead className="sticky top-0 bg-black text-[11px] font-mono uppercase tracking-wider text-zinc-400 border-b border-white/15 select-none">
                  <tr>
                    {visibleColumns.select && <th className="px-3 py-2.5 w-8"></th>}
                    {visibleColumns.mpn && <th className="px-3 py-2.5">MPN</th>}
                    {visibleColumns.manufacturer && <th className="px-3 py-2.5">Manufacturer</th>}
                    {visibleColumns.family && <th className="px-3 py-2.5">Family</th>}
                    {/* MOSFET Columns */}
                    {(isMosfetOnly || !currentFilter?.family) && visibleColumns.vds && (
                      <th className="px-3 py-2.5 font-mono">Vds (V)</th>
                    )}
                    {(isMosfetOnly || !currentFilter?.family) && visibleColumns.id && (
                      <th className="px-3 py-2.5 font-mono">Id (A)</th>
                    )}
                    {(isMosfetOnly || !currentFilter?.family) && visibleColumns.rds_on && (
                      <th className="px-3 py-2.5 font-mono">Rds(on) (mΩ)</th>
                    )}
                    {(isMosfetOnly || !currentFilter?.family) && visibleColumns.qg && (
                      <th className="px-3 py-2.5 font-mono">Qg (nC)</th>
                    )}
                    {/* Gate Driver Columns */}
                    {isDriverOnly && (
                      <>
                        <th className="px-3 py-2.5 font-mono">Vcc (V)</th>
                        <th className="px-3 py-2.5 font-mono">Iout (A)</th>
                        <th className="px-3 py-2.5 font-mono">tpd (ns)</th>
                        <th className="px-3 py-2.5 font-mono">Channels</th>
                      </>
                    )}
                    {visibleColumns.package && <th className="px-3 py-2.5">Package</th>}
                    {visibleColumns.lifecycle && <th className="px-3 py-2.5">Status</th>}
                    {visibleColumns.stock && (
                      <th className="px-3 py-2.5 text-right font-mono">Stock</th>
                    )}
                    {visibleColumns.confidence && (
                      <th className="px-3 py-2.5 text-right">Confidence</th>
                    )}
                    {visibleColumns.review && (
                      <th className="px-3 py-2.5 text-center">Review Queue</th>
                    )}
                  </tr>
                </thead>

                <tbody className="divide-y divide-white/5">
                  {results.map((part) => {
                    const checked = isSelected(part.part_id);
                    return (
                      <tr
                        key={part.part_id}
                        onMouseEnter={() => handleRowPrefetch(part.part_id)}
                        className={cn(
                          "hover:bg-white/[0.04] transition-none cursor-pointer",
                          checked && "bg-white/[0.06]",
                        )}
                        onClick={() => navigate(`/parts/${part.part_id}`)}
                      >
                        {/* Checkbox */}
                        {visibleColumns.select && (
                          <td className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => togglePart({ id: part.part_id, mpn: part.mpn })}
                              aria-label={`Select ${part.mpn} for comparison`}
                              className="size-4 rounded-[3px] border-white/20 bg-white/5 text-white cursor-pointer"
                            />
                          </td>
                        )}

                        {/* MPN */}
                        {visibleColumns.mpn && (
                          <td className="px-3 py-2.5 font-mono font-medium text-white">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <Link
                                to={`/parts/${part.part_id}`}
                                className="text-white underline underline-offset-2 hover:text-zinc-300"
                                onClick={(e) => e.stopPropagation()}
                              >
                                {part.mpn}
                              </Link>
                              {(part.part_id.startsWith("web-") || part.part_id.startsWith("api-")) && (
                                <span className="inline-flex items-center rounded-full bg-white/10 px-1.5 py-0.5 text-[9px] font-mono text-zinc-300 border border-white/20 uppercase tracking-wide">
                                  Live
                                </span>
                              )}
                              {part.datasheet_url && (
                                <a
                                  href={part.datasheet_url}
                                  target="_blank"
                                  rel="noreferrer"
                                  onClick={(e) => e.stopPropagation()}
                                  className="text-zinc-500 hover:text-zinc-300 transition-colors inline-flex items-center ml-0.5"
                                  title="Open datasheet or source"
                                >
                                  <ExternalLink className="size-3" />
                                </a>
                              )}
                            </div>
                          </td>
                        )}

                        {/* Manufacturer */}
                        {visibleColumns.manufacturer && (
                          <td className="px-3 py-2.5 text-zinc-300">{part.manufacturer}</td>
                        )}

                        {/* Family */}
                        {visibleColumns.family && (
                          <td className="px-3 py-2.5 font-mono text-[11px] text-zinc-400 capitalize">
                            {part.family}
                          </td>
                        )}

                        {/* Vds (V) */}
                        {(isMosfetOnly || !currentFilter?.family) && visibleColumns.vds && (
                          <td className="px-3 py-2.5 font-mono text-zinc-200">
                            {formatNumber(part.key_parameters?.vds_max)}
                          </td>
                        )}

                        {/* Id (A) */}
                        {(isMosfetOnly || !currentFilter?.family) && visibleColumns.id && (
                          <td className="px-3 py-2.5 font-mono text-zinc-200">
                            {formatNumber(part.key_parameters?.id_continuous)}
                          </td>
                        )}

                        {/* Rds(on) (mΩ) */}
                        {(isMosfetOnly || !currentFilter?.family) && visibleColumns.rds_on && (
                          <td className="px-3 py-2.5 font-mono text-zinc-200">
                            {part.key_parameters?.rds_on !== undefined &&
                            part.key_parameters?.rds_on !== null
                              ? (part.key_parameters.rds_on * 1000).toFixed(1)
                              : "-"}
                          </td>
                        )}

                        {/* Qg (nC) */}
                        {(isMosfetOnly || !currentFilter?.family) && visibleColumns.qg && (
                          <td className="px-3 py-2.5 font-mono text-zinc-200">
                            {part.key_parameters?.total_gate_charge_qg !== undefined &&
                            part.key_parameters?.total_gate_charge_qg !== null
                              ? (part.key_parameters.total_gate_charge_qg * 1e9).toFixed(1)
                              : "-"}
                          </td>
                        )}

                        {/* Driver Columns */}
                        {isDriverOnly && (
                          <>
                            <td className="px-3 py-2.5 font-mono text-zinc-200">
                              {formatNumber(part.key_parameters?.supply_voltage_max)}
                            </td>
                            <td className="px-3 py-2.5 font-mono text-zinc-200">
                              {formatNumber(part.key_parameters?.peak_source_current)}
                            </td>
                            <td className="px-3 py-2.5 font-mono text-zinc-200">
                              {part.key_parameters?.propagation_delay !== undefined &&
                              part.key_parameters?.propagation_delay !== null
                                ? (part.key_parameters.propagation_delay * 1e9).toFixed(0)
                                : "-"}
                            </td>
                            <td className="px-3 py-2.5 font-mono text-zinc-200">
                              {formatNumber(part.key_parameters?.channel_count)}
                            </td>
                          </>
                        )}

                        {/* Package */}
                        {visibleColumns.package && (
                          <td className="px-3 py-2.5 font-mono text-[11px] text-zinc-400">
                            {part.package ?? "-"}
                          </td>
                        )}

                        {/* Lifecycle Status */}
                        {visibleColumns.lifecycle && (
                          <td className="px-3 py-2.5">
                            <StatusTag
                              status={part.lifecycle_status ?? "unknown"}
                              type="lifecycle"
                            />
                          </td>
                        )}

                        {/* Stock */}
                        {visibleColumns.stock && (
                          <td className="px-3 py-2.5 text-right font-mono text-zinc-200">
                            {part.total_stock ? part.total_stock.toLocaleString() : "0"}
                          </td>
                        )}

                        {/* Confidence Meter */}
                        {visibleColumns.confidence && (
                          <td className="px-3 py-2.5 text-right">
                            <ConfidenceMeter confidence={part.score} surface="dark" />
                          </td>
                        )}

                        {/* Review Queue Action */}
                        {visibleColumns.review && (
                          <td className="px-3 py-2.5 text-center" onClick={(e) => e.stopPropagation()}>
                            <button
                              type="button"
                              onClick={() => toggleReviewItem(part)}
                              aria-label={
                                isInQueue(part.part_id)
                                  ? `Remove ${part.mpn} from review queue`
                                  : `Add ${part.mpn} to review queue`
                              }
                              className={cn(
                                "inline-flex items-center gap-1 px-3 py-1 rounded-full text-[11px] font-medium border transition-colors",
                                isInQueue(part.part_id)
                                  ? "border-white/30 bg-white/15 text-white hover:bg-white/20"
                                  : "border-white/15 bg-white/5 text-zinc-300 hover:text-white hover:bg-white/10",
                              )}
                            >
                              {isInQueue(part.part_id) ? (
                                <>
                                  <Check className="size-3 text-white" />
                                  <span>In Review</span>
                                </>
                              ) : (
                                <>
                                  <ListPlus className="size-3" />
                                  <span>+ Review</span>
                                </>
                              )}
                            </button>
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between border-t border-white/10 pt-3 text-xs font-mono">
              <span className="text-zinc-400">
                Page {urlPage} of {totalPages}
              </span>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => handlePageChange(urlPage - 1)}
                  disabled={urlPage <= 1}
                  className="rounded-[4px] border border-white/20 p-1.5 hover:bg-white/10 text-white disabled:opacity-30 disabled:pointer-events-none"
                >
                  <ChevronLeft className="size-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => handlePageChange(urlPage + 1)}
                  disabled={urlPage >= totalPages}
                  className="rounded-[4px] border border-white/20 p-1.5 hover:bg-white/10 text-white disabled:opacity-30 disabled:pointer-events-none"
                >
                  <ChevronRight className="size-3.5" />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const ALL_COMPREHENSIVE_FAMILIES: { id: Family | "all"; label: string }[] = [
  { id: "all", label: "All Categories" },
  { id: "mosfet" as Family, label: "Power MOSFETs" },
  { id: "gate_driver" as Family, label: "Gate Drivers" },
  { id: "mcu" as Family, label: "Microcontrollers" },
  { id: "opamp" as Family, label: "Op-Amps" },
  { id: "regulator" as Family, label: "Regulators / PMIC" },
  { id: "diode" as Family, label: "Diodes & Rectifiers" },
  { id: "sensor" as Family, label: "Sensors & MEMS" },
  { id: "transceiver" as Family, label: "Transceivers" },
  { id: "passive" as Family, label: "Passives" },
  { id: "general" as Family, label: "General ICs" },
];

const POPULAR_PACKAGES = [
  "TO-220AB",
  "SuperSO8",
  "PowerPAK SO-8",
  "D2PAK",
  "DPAK",
  "SOIC-8",
  "SOT-23",
  "SOT-23-6",
  "SOT-223",
  "TO-247",
  "DIP-8",
  "QFN",
  "TO-92",
];

const VOLTAGE_RANGES = [
  { label: "< 30V", min: undefined, max: 30, unit: "V" },
  { label: "30V – 60V", min: 30, max: 60, unit: "V" },
  { label: "60V – 100V", min: 60, max: 100, unit: "V" },
  { label: "100V – 250V", min: 100, max: 250, unit: "V" },
  { label: "250V – 650V", min: 250, max: 650, unit: "V" },
  { label: "> 650V", min: 650, max: undefined, unit: "V" },
];

const CURRENT_RANGES = [
  { label: "< 2A", min: undefined, max: 2, unit: "A" },
  { label: "2A – 10A", min: 2, max: 10, unit: "A" },
  { label: "10A – 50A", min: 10, max: 50, unit: "A" },
  { label: "50A – 100A", min: 50, max: 100, unit: "A" },
  { label: "> 100A", min: 100, max: undefined, unit: "A" },
];

const RDSON_RANGES = [
  { label: "< 5 mΩ", min: undefined, max: 0.005, unit: "ohm" },
  { label: "5 – 20 mΩ", min: 0.005, max: 0.02, unit: "ohm" },
  { label: "20 – 100 mΩ", min: 0.02, max: 0.1, unit: "ohm" },
  { label: "> 100 mΩ", min: 0.1, max: undefined, unit: "ohm" },
];

const LIFECYCLE_OPTIONS: { id: LifecycleStatus; label: string }[] = [
  { id: "active" as LifecycleStatus, label: "Active" },
  { id: "nrnd" as LifecycleStatus, label: "NRND" },
  { id: "obsolete" as LifecycleStatus, label: "Obsolete" },
];

function FilterRailContent({
  activeFilter,
  manufacturers,
  onFamilyChange,
  onMfrToggle,
  onPackageToggle,
  onLifecycleToggle,
  onParamRangeToggle,
  onInStockToggle,
}: {
  activeFilter: SearchFilter | null;
  manufacturers: string[];
  onFamilyChange: (family: Family | "all") => void;
  onMfrToggle: (mfr: string) => void;
  onPackageToggle: (pkg: string) => void;
  onLifecycleToggle: (status: LifecycleStatus) => void;
  onParamRangeToggle: (
    paramName: string,
    min: number | undefined,
    max: number | undefined,
    unit: string,
  ) => void;
  onInStockToggle: (inStock: boolean) => void;
}) {
  const currentFamily = activeFilter?.family ?? "all";
  const selectedMfrs = activeFilter?.manufacturer_in ?? [];
  const selectedPackages = activeFilter?.package_in ?? [];
  const selectedLifecycle = activeFilter?.lifecycle_status ?? [];
  const inStock = Boolean(activeFilter?.in_stock);
  const activeParams = activeFilter?.parameters ?? [];

  const [mfrSearch, setMfrSearch] = useState("");
  const filteredMfrs = useMemo(() => {
    if (!mfrSearch.trim()) return manufacturers;
    const q = mfrSearch.toLowerCase().trim();
    return manufacturers.filter((m) => m.toLowerCase().includes(q));
  }, [manufacturers, mfrSearch]);

  const activeVdsParam = activeParams.find((p) => p.name === "vds_max" || p.name === "supply_voltage_max");
  const activeIdParam = activeParams.find((p) => p.name === "id_continuous" || p.name === "peak_source_current");
  const activeRdsonParam = activeParams.find((p) => p.name === "rds_on");

  return (
    <div className="space-y-6 text-xs font-sans">
      {/* 1. Component Family (Comprehensive) */}
      <div>
        <label className="block text-[11px] uppercase tracking-wider font-mono text-zinc-400 mb-2 font-semibold">
          Component Family ({ALL_COMPREHENSIVE_FAMILIES.length})
        </label>
        <div className="flex flex-wrap gap-1.5">
          {ALL_COMPREHENSIVE_FAMILIES.map((fam) => {
            const isSelected = fam.id === "all" ? currentFamily === "all" : currentFamily === fam.id;
            return (
              <button
                key={fam.id}
                type="button"
                onClick={() => onFamilyChange(fam.id as any)}
                className={cn(
                  "rounded-full px-2.5 py-1 text-[11px] font-medium transition-all border cursor-pointer",
                  isSelected
                    ? "bg-white text-black font-semibold border-white"
                    : "border-white/10 bg-white/5 text-zinc-300 hover:text-white hover:bg-white/10",
                )}
              >
                {fam.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* 2. Package / Footprint Filter */}
      <div className="pt-4 border-t border-white/10">
        <div className="flex items-center justify-between mb-2">
          <label className="block text-[11px] uppercase tracking-wider font-mono text-zinc-400 font-semibold">
            Package / Footprint
          </label>
          {selectedPackages.length > 0 && (
            <span className="text-[10px] font-mono text-emerald-400">
              {selectedPackages.length} selected
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {POPULAR_PACKAGES.map((pkg) => {
            const isSelected = selectedPackages.includes(pkg);
            return (
              <button
                key={pkg}
                type="button"
                onClick={() => onPackageToggle(pkg)}
                className={cn(
                  "rounded-full px-2.5 py-1 text-[11px] font-mono transition-all border cursor-pointer",
                  isSelected
                    ? "bg-white text-black font-semibold border-white"
                    : "border-white/10 bg-white/5 text-zinc-300 hover:text-white hover:bg-white/10",
                )}
              >
                {pkg}
              </button>
            );
          })}
        </div>
      </div>

      {/* 3. Voltage Rating Range Filter */}
      <div className="pt-4 border-t border-white/10">
        <label className="block text-[11px] uppercase tracking-wider font-mono text-zinc-400 mb-2 font-semibold">
          Breakdown Voltage (Vds / Vcc)
        </label>
        <div className="flex flex-wrap gap-1.5">
          {VOLTAGE_RANGES.map((v) => {
            const isSelected =
              activeVdsParam && activeVdsParam.min === v.min && activeVdsParam.max === v.max;
            return (
              <button
                key={v.label}
                type="button"
                onClick={() =>
                  onParamRangeToggle(
                    currentFamily === "gate_driver" ? "supply_voltage_max" : "vds_max",
                    v.min,
                    v.max,
                    v.unit,
                  )
                }
                className={cn(
                  "rounded-full px-2.5 py-1 text-[11px] font-mono transition-all border cursor-pointer",
                  isSelected
                    ? "bg-white text-black font-semibold border-white"
                    : "border-white/10 bg-white/5 text-zinc-300 hover:text-white hover:bg-white/10",
                )}
              >
                {v.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* 4. Current Rating Range Filter */}
      {(currentFamily === "all" || currentFamily === "mosfet" || currentFamily === "gate_driver") && (
        <div className="pt-4 border-t border-white/10">
          <label className="block text-[11px] uppercase tracking-wider font-mono text-zinc-400 mb-2 font-semibold">
            Continuous Current (Id / Iout)
          </label>
          <div className="flex flex-wrap gap-1.5">
            {CURRENT_RANGES.map((c) => {
              const isSelected =
                activeIdParam && activeIdParam.min === c.min && activeIdParam.max === c.max;
              return (
                <button
                  key={c.label}
                  type="button"
                  onClick={() =>
                    onParamRangeToggle(
                      currentFamily === "gate_driver" ? "peak_source_current" : "id_continuous",
                      c.min,
                      c.max,
                      c.unit,
                    )
                  }
                  className={cn(
                    "rounded-full px-2.5 py-1 text-[11px] font-mono transition-all border cursor-pointer",
                    isSelected
                      ? "bg-white text-black font-semibold border-white"
                      : "border-white/10 bg-white/5 text-zinc-300 hover:text-white hover:bg-white/10",
                  )}
                >
                  {c.label}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* 5. On-Resistance (Rds_on) for MOSFETs */}
      {(currentFamily === "all" || currentFamily === "mosfet") && (
        <div className="pt-4 border-t border-white/10">
          <label className="block text-[11px] uppercase tracking-wider font-mono text-zinc-400 mb-2 font-semibold">
            On-Resistance (Rds_on)
          </label>
          <div className="flex flex-wrap gap-1.5">
            {RDSON_RANGES.map((r) => {
              const isSelected =
                activeRdsonParam && activeRdsonParam.min === r.min && activeRdsonParam.max === r.max;
              return (
                <button
                  key={r.label}
                  type="button"
                  onClick={() => onParamRangeToggle("rds_on", r.min, r.max, r.unit)}
                  className={cn(
                    "rounded-full px-2.5 py-1 text-[11px] font-mono transition-all border cursor-pointer",
                    isSelected
                      ? "bg-white text-black font-semibold border-white"
                      : "border-white/10 bg-white/5 text-zinc-300 hover:text-white hover:bg-white/10",
                  )}
                >
                  {r.label}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* 6. Lifecycle Status Filter */}
      <div className="pt-4 border-t border-white/10">
        <label className="block text-[11px] uppercase tracking-wider font-mono text-zinc-400 mb-2 font-semibold">
          Lifecycle Status
        </label>
        <div className="flex flex-wrap gap-1.5">
          {LIFECYCLE_OPTIONS.map((lc) => {
            const isSelected = selectedLifecycle.includes(lc.id);
            return (
              <button
                key={lc.id}
                type="button"
                onClick={() => onLifecycleToggle(lc.id)}
                className={cn(
                  "rounded-full px-2.5 py-1 text-[11px] font-medium transition-all border cursor-pointer",
                  isSelected
                    ? "bg-white text-black font-semibold border-white"
                    : "border-white/10 bg-white/5 text-zinc-300 hover:text-white hover:bg-white/10",
                )}
              >
                {lc.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* 7. Searchable Manufacturers List */}
      <div className="pt-4 border-t border-white/10">
        <div className="flex items-center justify-between mb-2">
          <label className="block text-[11px] uppercase tracking-wider font-mono text-zinc-400 font-semibold">
            Manufacturers
          </label>
          {selectedMfrs.length > 0 && (
            <span className="text-[10px] font-mono text-emerald-400">
              {selectedMfrs.length} selected
            </span>
          )}
        </div>

        {/* Quick Search */}
        <input
          type="text"
          value={mfrSearch}
          onChange={(e) => setMfrSearch(e.target.value)}
          placeholder="Filter manufacturers..."
          className="w-full mb-2.5 px-2.5 py-1 rounded-[4px] border border-white/15 bg-white/5 font-mono text-[11px] text-white placeholder:text-zinc-500 focus:outline-none focus:border-white/35"
        />

        <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
          {filteredMfrs.map((mfr) => {
            const isChecked = selectedMfrs.includes(mfr);
            return (
              <label
                key={mfr}
                className="flex items-center gap-2 cursor-pointer hover:text-white select-none text-[12px] text-zinc-300"
              >
                <input
                  type="checkbox"
                  checked={isChecked}
                  onChange={() => onMfrToggle(mfr)}
                  className="size-3.5 rounded-[3px] border-white/20 bg-white/5 text-white"
                />
                <span className={isChecked ? "font-medium text-white truncate" : "text-zinc-400 truncate"}>
                  {mfr}
                </span>
              </label>
            );
          })}
          {filteredMfrs.length === 0 && (
            <div className="text-[11px] text-zinc-500 py-2">No matching manufacturer</div>
          )}
        </div>
      </div>

      {/* 8. Sourcing & Inventory */}
      <div className="pt-4 border-t border-white/10">
        <label className="flex items-center gap-2 cursor-pointer select-none text-xs text-zinc-300">
          <input
            type="checkbox"
            checked={inStock}
            onChange={(e) => onInStockToggle(e.target.checked)}
            className="size-3.5 rounded-[3px] border-white/20 bg-white/5 text-white"
          />
          <span className="font-medium text-white">In stock only</span>
        </label>
      </div>
    </div>
  );
}
