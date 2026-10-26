import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@/api/types";
import { apiGet, apiPost, apiUpload } from "./client";

export type PartSummary = components["schemas"]["PartSummary"];
export type PartRecord = components["schemas"]["PartRecord"];
export type ParameterValue = components["schemas"]["ParameterValue"];
export type ParameterSource = components["schemas"]["ParameterSource"];
export type SourcePage = components["schemas"]["SourcePage"];
export type SourceRef = components["schemas"]["SourceRef"];
export type Offer = components["schemas"]["Offer"];
export type SearchFilter = components["schemas"]["SearchFilter"];
export type SearchResponse = components["schemas"]["SearchResponse"];
export type WebSearchResult = {
  title: string;
  url: string;
  snippet?: string;
  scraped_text?: string;
  source?: string;
  offers?: Offer[];
};
export type SearchResponseWithWeb = Omit<
  SearchResponse,
  "web_results" | "provider_candidates" | "search_mode"
> & {
  web_results?: WebSearchResult[];
  provider_candidates?: PartSummary[];
  search_mode?: string;
};
export type SearchRequest = components["schemas"]["SearchRequest"];
export type AlternativeResult = components["schemas"]["AlternativeResult"];
export type BomCheckResponse = components["schemas"]["BomCheckResponse"];
export type ReviewItem = components["schemas"]["ReviewItem"];
export type ReviewDecision = components["schemas"]["ReviewDecision"];
export type ReviewResponse = components["schemas"]["ReviewResponse"];
export type JobRequest = components["schemas"]["JobRequest"];
export type JobStatus = components["schemas"]["JobStatus"];
export type StatsResponse = components["schemas"]["StatsResponse"];
export type LifecycleStatus = components["schemas"]["LifecycleStatus"];
export type ValueStatus = components["schemas"]["ValueStatus"];
export type RiskSeverity = components["schemas"]["RiskSeverity"];
export type ExtractionMethod = components["schemas"]["ExtractionMethod"];
export type ParameterConstraint = components["schemas"]["ParameterConstraint"];
export type Family = components["schemas"]["Family"];
export type PartDetail = PartRecord;

export const queryKeys = {
  parts: (params: Record<string, unknown>) => ["parts", params] as const,
  part: (partId: string) => ["part", partId] as const,
  parameterSource: (partId: string, paramId: string) =>
    ["parameter-source", partId, paramId] as const,
  sourcePage: (sourceId: string, page: number) => ["source-page", sourceId, page] as const,
  search: (query: string, filter: SearchFilter | null) => ["search", query, filter] as const,
  alternatives: (partId: string) => ["alternatives", partId] as const,
  reviewQueue: () => ["review-queue"] as const,
  stats: () => ["stats"] as const,
  job: (jobId: string) => ["job", jobId] as const,
};

/* ------------------------------------------------------------------ */
/* Queries                                                             */
/* ------------------------------------------------------------------ */

export type PartsQuery = {
  family?: components["schemas"]["Family"];
  manufacturer?: string;
  manufacturers?: string;
  package?: string;
  packages?: string;
  lifecycle_status?: string;
  in_stock?: boolean;
  q?: string;
  limit?: number;
  offset?: number;
};

/** `GET /api/parts` - the list of parts with the simple filters. */
export function useParts(params: PartsQuery = {}, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.parts(params),
    queryFn: () => apiGet<SearchResponse>("/api/parts", { ...params }),
    ...options,
  });
}

/** `GET /api/parts/{part_id}` - one part with every value. */
export function usePart(partId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.part(partId ?? ""),
    queryFn: () => apiGet<PartRecord>(`/api/parts/${encodeURIComponent(partId ?? "")}`),
    enabled: Boolean(partId),
  });
}

/** Several parts at once. Used by the compare page. */
export function usePartsList(partIds: string[]) {
  return useQueries({
    queries: partIds.map((partId) => ({
      queryKey: queryKeys.part(partId),
      queryFn: () => apiGet<PartRecord>(`/api/parts/${encodeURIComponent(partId)}`),
    })),
  });
}

/** `GET /api/parts/{part_id}/sources/{param_id}` - the provenance of one value. */
export function useParameterSource(partId: string | undefined, paramId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.parameterSource(partId ?? "", paramId ?? ""),
    queryFn: () =>
      apiGet<ParameterSource>(
        `/api/parts/${encodeURIComponent(partId ?? "")}/sources/${encodeURIComponent(paramId ?? "")}`,
      ),
    enabled: Boolean(partId && paramId),
  });
}

/** `GET /api/sources/{source_id}/page/{n}` - the page metadata and text. */
export function useSourcePage(sourceId: string | undefined, page: number | undefined) {
  return useQuery({
    queryKey: queryKeys.sourcePage(sourceId ?? "", page ?? 0),
    queryFn: () =>
      apiGet<SourcePage>(`/api/sources/${encodeURIComponent(sourceId ?? "")}/page/${page ?? 1}`),
    enabled: Boolean(sourceId && page && page > 0),
  });
}

export type SearchInput = {
  query: string;
  /** When present the backend does NOT call the LLM (the filter is reused). */
  filter?: SearchFilter | null;
  limit?: number;
  offset?: number;
};

export type StreamSearchEvent = {
  type: "filter" | "local_results" | "web_results" | "discovered_results" | "advisory" | "done";
  query?: string;
  filter?: SearchFilter;
  filter_explanation?: string | null;
  results?: PartSummary[];
  web_results?: WebSearchResult[];
  provider_candidates?: PartSummary[];
  ai_advisory?: any;
  search_mode?: string;
  total?: number;
  took_ms?: number;
  llm_used?: boolean;
};

export function streamSearch(
  query: string,
  onEvent: (event: StreamSearchEvent) => void,
  limit = 50,
  offset = 0,
  signal?: AbortSignal,
): Promise<void> {
  if (typeof EventSource === "undefined") {
    return apiPost<SearchResponseWithWeb>("/api/search", { query, limit, offset }, signal)
      .then((data) => {
        onEvent({
          type: "local_results",
          results: data.results,
          total: data.total,
          filter: data.filter,
          filter_explanation: data.filter_explanation,
          web_results: data.web_results,
          provider_candidates: data.provider_candidates,
          ai_advisory: data.ai_advisory,
          took_ms: data.took_ms,
        });
        onEvent({ type: "done", total: data.total, took_ms: data.took_ms });
      })
      .catch((err) => {
        onEvent({ type: "error" as any, error: err?.message || "Search request failed" } as any);
      });
  }
  const url = `/api/search/stream?q=${encodeURIComponent(query)}&limit=${limit}&offset=${offset}`;
  return new Promise((resolve) => {
    const es = new EventSource(url);
    if (signal) {
      signal.addEventListener("abort", () => {
        es.close();
        resolve();
      });
    }
    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as StreamSearchEvent;
        onEvent(data);
        if (data.type === "done") {
          es.close();
          resolve();
        }
      } catch {
        // ignore parse error
      }
    };
    es.onerror = () => {
      es.close();
      onEvent({ type: "error" as any, error: "Search stream interrupted or rate limited" } as any);
      resolve();
    };
  });
}

/**
 * `POST /api/search`.
 *
 * The filter is part of the query key, so editing a chip re-runs the search
 * with the edited filter and the LLM is not called a second time.
 */
export function useSearch(input: SearchInput | null | undefined) {
  return useQuery({
    queryKey: queryKeys.search(input?.query ?? "", input?.filter ?? null),
    queryFn: () => {
      const body: SearchRequest = {
        query: input?.query ?? "",
        filter: input?.filter ?? null,
        limit: input?.limit ?? 50,
        offset: input?.offset ?? 0,
      };
      return apiPost<SearchResponseWithWeb>("/api/search", body);
    },
    enabled: Boolean(input),
  });
}

/** `GET /api/parts/{part_id}/alternatives` - the ranked alternatives. */
export function useAlternatives(partId: string | undefined, limit = 10) {
  return useQuery({
    queryKey: queryKeys.alternatives(partId ?? ""),
    queryFn: () =>
      apiGet<AlternativeResult[]>(`/api/parts/${encodeURIComponent(partId ?? "")}/alternatives`, {
        limit,
      }),
    enabled: Boolean(partId),
  });
}

/** `GET /api/review` - the values that wait for a human decision. */
export function useReviewQueue() {
  return useQuery({
    queryKey: queryKeys.reviewQueue(),
    queryFn: () => apiGet<ReviewItem[]>("/api/review"),
  });
}

/** `GET /api/stats` - the dashboard numbers (1 minute staleTime). */
export function useStats() {
  return useQuery({
    queryKey: queryKeys.stats(),
    queryFn: () => apiGet<StatsResponse>("/api/stats"),
    staleTime: 60 * 1000,
  });
}

const TERMINAL_JOB_STATES: Array<JobStatus["state"]> = ["completed", "failed", "cancelled"];

/** `GET /api/jobs/{job_id}` - polled until the job reaches a terminal state (0 staleTime). */
export function useJob(jobId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.job(jobId ?? ""),
    queryFn: () => apiGet<JobStatus>(`/api/jobs/${encodeURIComponent(jobId ?? "")}`),
    enabled: Boolean(jobId),
    staleTime: 0,
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      if (!state) return false;
      return TERMINAL_JOB_STATES.includes(state) ? false : 3000;
    },
  });
}

/* ------------------------------------------------------------------ */
/* Mutations                                                           */
/* ------------------------------------------------------------------ */

/** `POST /api/bom/check` - upload a BOM CSV and get the risk table. */
export function useBomCheck() {
  return useMutation({
    mutationFn: (file: File) => apiUpload<BomCheckResponse>("/api/bom/check", file),
  });
}

export interface ReviewCandidateEvaluation {
  mpn: string;
  status_recommendation: "RECOMMENDED_FINAL" | "SUITABLE_ALTERNATE" | "CAUTION";
  verdict: string;
  pros: string[];
  cons: string[];
  best_used_for: string;
}

export interface ReviewTradeoff {
  dimension: string;
  analysis: string;
  advantage_mpn?: string | null;
}

export interface ReviewAdvisoryResponse {
  executive_summary: string;
  overall_recommendation: string;
  candidate_evaluations: ReviewCandidateEvaluation[];
  tradeoffs: ReviewTradeoff[];
  engineering_suggestions: string[];
  bom_readiness_score: number;
}

export interface ReviewAdvisoryRequest {
  parts: Array<{
    mpn: string;
    manufacturer?: string;
    family?: string;
    package?: string;
    lifecycle_status?: string;
    parameters?: Record<string, any>;
    stock?: number;
    price?: number;
    currency?: string;
  }>;
  priority?: "balanced" | "efficiency" | "cost" | "thermal" | "supply";
  custom_query?: string | null;
}

/** `POST /api/review/advisory` - AI tradeoffs and recommendations for queued candidates. */
export function useReviewAdvisory() {
  return useMutation({
    mutationFn: (body: ReviewAdvisoryRequest) =>
      apiPost<ReviewAdvisoryResponse>("/api/review/advisory", body),
  });
}

/** `POST /api/review/{param_id}` - accept, correct or reject one value. */
export function useReviewDecision() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ paramId, decision }: { paramId: string; decision: ReviewDecision }) =>
      apiPost<ReviewResponse>(`/api/review/${encodeURIComponent(paramId)}`, decision),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.reviewQueue() });
      void queryClient.invalidateQueries({ queryKey: ["part"] });
    },
  });
}

export const useDecideReview = useReviewDecision;
export const useJobStatus = useJob;

/** `POST /api/jobs/extract` - start a background extraction job. */
export function useStartExtractionJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: JobRequest = {}) => apiPost<JobStatus>("/api/jobs/extract", body),
    onSuccess: (job) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.job(job.job_id) });
    },
  });
}

/** `POST /api/parts/{part_id}/datasheet` - fetch and cache the real PDF. */
export function useDownloadDatasheet() {
  return useMutation({
    mutationFn: (partId: string) =>
      apiPost<SourceRef>(`/api/parts/${encodeURIComponent(partId)}/datasheet`),
  });
}
