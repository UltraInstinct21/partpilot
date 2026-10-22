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
  package?: string;
  lifecycle_status?: string;
  in_stock?: boolean;
  q?: string;
  limit?: number;
  offset?: number;
};

/** `GET /api/parts` - the list of parts with the simple filters. */
export function useParts(params: PartsQuery = {}) {
  return useQuery({
    queryKey: queryKeys.parts(params),
    queryFn: () => apiGet<SearchResponse>("/api/parts", { ...params }),
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
      return apiPost<SearchResponse>("/api/search", body);
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

/** `GET /api/stats` - the dashboard numbers. */
export function useStats() {
  return useQuery({
    queryKey: queryKeys.stats(),
    queryFn: () => apiGet<StatsResponse>("/api/stats"),
  });
}

const TERMINAL_JOB_STATES: Array<JobStatus["state"]> = ["completed", "failed", "cancelled"];

/** `GET /api/jobs/{job_id}` - polled until the job reaches a terminal state. */
export function useJob(jobId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.job(jobId ?? ""),
    queryFn: () => apiGet<JobStatus>(`/api/jobs/${encodeURIComponent(jobId ?? "")}`),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      if (!state) return false;
      return TERMINAL_JOB_STATES.includes(state) ? false : 1000;
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
