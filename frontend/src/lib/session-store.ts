/**
 * Global In-Memory Session Store for PartPilot.
 *
 * This store maintains feature states across client-side page transitions
 * (React Router navigations) so that NO results, filters, or uploaded data are
 * lost when moving between pages.
 *
 * State lives in memory for the duration of the browser tab session and is
 * reset only when the user hard-refreshes the page.
 */

import type {
  SearchFilter,
  PartSummary,
  WebSearchResult,
  BomCheckResponse,
} from "@/api/hooks";

// ---------------------------------------------------------------------------
// 1. Search State
// ---------------------------------------------------------------------------

export interface SearchSessionState {
  query: string;
  page: number;
  activeFilter: SearchFilter | null;
  customAdvisory: any | null;
  askAiQuery: string;
  streamData: {
    results?: PartSummary[];
    total?: number;
    filter?: SearchFilter;
    filter_explanation?: string;
    web_results?: WebSearchResult[];
    provider_candidates?: PartSummary[];
    ai_advisory?: any;
    took_ms?: number;
    isStreaming?: boolean;
  } | null;
}

const defaultSearchState: SearchSessionState = {
  query: "",
  page: 1,
  activeFilter: null,
  customAdvisory: null,
  askAiQuery: "",
  streamData: null,
};

let searchSession: SearchSessionState = { ...defaultSearchState };

export const searchSessionStore = {
  get: (): SearchSessionState => searchSession,
  set: (updater: Partial<SearchSessionState> | ((prev: SearchSessionState) => SearchSessionState)) => {
    if (typeof updater === "function") {
      searchSession = updater(searchSession);
    } else {
      searchSession = { ...searchSession, ...updater };
    }
  },
  reset: () => {
    searchSession = { ...defaultSearchState };
  },
};

// ---------------------------------------------------------------------------
// 2. BOM Check State
// ---------------------------------------------------------------------------

export interface BomSessionState {
  file: File | null;
  fileName: string | null;
  fileContent: string | null;
  fileError: string | null;
  headers: string[];
  previewRows: string[][];
  mpnCol: string;
  qtyCol: string;
  refCol: string;
  result: BomCheckResponse | null;
  activeStep: number;
  selectedRiskFilter: string;
  manualMatches: Record<string, string>;
}

const defaultBomState: BomSessionState = {
  file: null,
  fileName: null,
  fileContent: null,
  fileError: null,
  headers: [],
  previewRows: [],
  mpnCol: "MPN",
  qtyCol: "Quantity",
  refCol: "Reference",
  result: null,
  activeStep: 1,
  selectedRiskFilter: "all",
  manualMatches: {},
};

let bomSession: BomSessionState = { ...defaultBomState };

export const bomSessionStore = {
  get: (): BomSessionState => bomSession,
  set: (updater: Partial<BomSessionState> | ((prev: BomSessionState) => BomSessionState)) => {
    if (typeof updater === "function") {
      bomSession = updater(bomSession);
    } else {
      bomSession = { ...bomSession, ...updater };
    }
  },
  reset: () => {
    bomSession = { ...defaultBomState };
  },
};

// ---------------------------------------------------------------------------
// 3. Review Queue State
// ---------------------------------------------------------------------------

export interface ReviewSessionState {
  familyFilter: string;
  tierFilter: string;
  reasonFilter: string;
  searchMpn: string;
  selectedIndex: number;
  selectedIds: string[];
}

const defaultReviewState: ReviewSessionState = {
  familyFilter: "all",
  tierFilter: "all",
  reasonFilter: "all",
  searchMpn: "",
  selectedIndex: 0,
  selectedIds: [],
};

let reviewSession: ReviewSessionState = { ...defaultReviewState };

export const reviewSessionStore = {
  get: (): ReviewSessionState => reviewSession,
  set: (updater: Partial<ReviewSessionState> | ((prev: ReviewSessionState) => ReviewSessionState)) => {
    if (typeof updater === "function") {
      reviewSession = updater(reviewSession);
    } else {
      reviewSession = { ...reviewSession, ...updater };
    }
  },
  reset: () => {
    reviewSession = { ...defaultReviewState };
  },
};

// ---------------------------------------------------------------------------
// 4. Part Detail State
// ---------------------------------------------------------------------------

export interface PartDetailSessionState {
  lastTab: Record<string, string>; // part_id -> tab
  onlyLowConfidence: boolean;
  showRejected: boolean;
}

const defaultPartDetailState: PartDetailSessionState = {
  lastTab: {},
  onlyLowConfidence: false,
  showRejected: false,
};

let partDetailSession: PartDetailSessionState = { ...defaultPartDetailState };

export const partDetailSessionStore = {
  get: (): PartDetailSessionState => partDetailSession,
  set: (updater: Partial<PartDetailSessionState> | ((prev: PartDetailSessionState) => PartDetailSessionState)) => {
    if (typeof updater === "function") {
      partDetailSession = updater(partDetailSession);
    } else {
      partDetailSession = { ...partDetailSession, ...updater };
    }
  },
  reset: () => {
    partDetailSession = { ...defaultPartDetailState };
  },
};
