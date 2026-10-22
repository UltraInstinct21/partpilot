# PartPilot Frontend - HANDOFF (agent H-frontend)

WP7 / FR-11, FR-12, FR-13, FR-14, FR-15, NFR-04.
Branch: `agent/h-frontend`. Worktree: `/home/sarthi/Projects/partpilot-wt/h-frontend`.

## What exists

A complete React 19 + Vite 8 + Tailwind v4 + shadcn/ui frontend for the PartPilot
API. The frontend never talks to a distributor API or an LLM (NFR-07): every
request goes to the PartPilot backend under `/api/...` (or to the MSW mock,
which serves exactly the same paths).

| Layer | Files | What it does |
| --- | --- | --- |
| API | `src/api/client.ts` | `apiGet`, `apiPost`, `apiUpload`. Throws `ApiError` with the `detail` of the backend. |
| API | `src/api/query-client.ts` | One `QueryClient`. **Every** failed request raises a `sonner` error toast (global `QueryCache`/`MutationCache` `onError`). |
| API | `src/api/hooks.ts` | One hook per endpoint: `useParts`, `usePart`, `usePartsList`, `useParameterSource`, `useSourcePage`, `useSearch`, `useAlternatives`, `useBomCheck`, `useReviewQueue`, `useReviewDecision`, `useStartExtractionJob`, `useJob` (polls until the job is terminal), `useStats`. |
| Shell | `src/main.tsx`, `src/App.tsx`, `src/routes.tsx`, `src/components/app-providers.tsx`, `src/components/app-nav.tsx` | React Router 7, `QueryClientProvider`, `ThemeProvider` (next-themes, needed by the shadcn `sonner`), `TooltipProvider`, `Toaster`. The MSW worker is started before the first render when `VITE_USE_MOCKS === "true"`. |
| Pages | `src/pages/*.tsx` | Search, part detail, compare, BOM check, review queue, dashboard. |
| Components | `src/components/*.tsx` | Badges, filter chips, source viewer sheet, react-pdf document, skeletons, error state. |
| Helpers | `src/lib/*.ts` | Formatters, filter/chip logic, confidence + lifecycle colours, table features, compare rules. |

## Route map

| Route | Page | Endpoint(s) |
| --- | --- | --- |
| `/` | Search | `POST /api/search` |
| `/parts/:partId` | Part detail (tabs: Specs / Offers / Alternatives) | `GET /api/parts/{id}`, `GET /api/parts/{id}/alternatives`, `POST /api/jobs/extract`, `GET /api/jobs/{id}` |
| `/compare` | Compare (2-4 parts, `?parts=id1,id2`) | `GET /api/parts`, `GET /api/parts/{id}` |
| `/bom` | BOM check | `POST /api/bom/check` (multipart) |
| `/review` | Review queue | `GET /api/review`, `POST /api/review/{param_id}` |
| `/dashboard` | Dashboard | `GET /api/stats` |

## Component inventory

| Component | File | Notes |
| --- | --- | --- |
| `ConfidenceBadge` | `src/components/confidence-badge.tsx` | green >= 0.75, yellow >= 0.5, red < 0.5 (`data-confidence` attribute). |
| `LifecycleBadge` | `src/components/lifecycle-badge.tsx` | active / nrnd / obsolete / unknown (`data-lifecycle`). |
| `StatusBadge`, `SeverityBadge` | `src/components/status-badge.tsx` | accepted/review/rejected and info/low/medium/high/critical. |
| `FilterChips` | `src/components/filter-chips.tsx` | Editable chips of the executed `SearchFilter`. Removing or editing a chip re-runs the search **with the edited filter**, so the LLM is not called again. |
| `SourceViewer` | `src/components/source-viewer.tsx` | `Sheet` with the value + full provenance on the left and the datasheet page on the right (FR-12). |
| `SourceDocument` | `src/components/source-document.tsx` | `react-pdf` `Document`/`Page`. The worker is configured with `new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url)`. It degrades gracefully and never crashes. |
| `AppNav`, `AppProviders` | `src/components/app-nav.tsx`, `app-providers.tsx` | Shell. |
| `PageSkeleton`, `TableSkeleton`, `ErrorState` | `src/components/loading-skeleton.tsx`, `error-state.tsx` | Loading and error state of every request. |
| `Checkbox` | `src/components/ui/checkbox.tsx` | **Added by hand** with the already installed `radix-ui` package (no new dependency, `package.json` untouched). |

## How to run

```bash
cd frontend
npm run dev            # real backend on 127.0.0.1:8000 through the Vite proxy
VITE_USE_MOCKS=true npm run dev   # MSW in the browser, no backend needed
npm test               # vitest run  (14 files, 26 tests)
npm run lint           # eslint
npm run format:check   # prettier
npm run typecheck      # tsc -b
npm run build          # tsc -b && vite build
```

Definition of done, all green:

```
npx vitest run                                   14 files / 26 tests passed
npx eslint .                                     clean (0 problems)
npx prettier --check "src/**/*.{ts,tsx,css,json}" clean
npx tsc -b                                       no type errors
npx vite build                                   ok (the pdf worker is emitted as an asset)
```

## Tests

`frontend/tests/` (14 files, 26 cases). The MSW node server from
`src/test/setup.ts` is used automatically by `vite.config.ts`.

| File | Covers |
| --- | --- |
| `search-page.test.tsx` | results of the mock, filter chips, removing a chip re-runs the search |
| `filter-chips.test.tsx` | editing a chip re-runs the search with the edited filter |
| `confidence-badge.test.tsx` | green / yellow / red classes |
| `lifecycle-badge.test.tsx` | active / nrnd / obsolete / unknown |
| `part-detail-page.test.tsx` | spec table with unit and condition, lifecycle badge, extraction job |
| `source-viewer.test.tsx` | the sheet opens next to the value and does not crash |
| `bom-check-page.test.tsx` | CSV upload and a risk row |
| `review-queue-page.test.tsx` | the rows and the accept decision |
| `review-queue-correction.test.tsx` | the correction dialog (zod validation) |
| `compare-page.test.tsx` | two parts side by side |
| `dashboard-page.test.tsx` | the stats and the chart containers |
| `error-handling.test.tsx` | error toast and inline error state |
| `loading-state.test.tsx` | the skeleton while a request is pending |
| `api-client.test.ts` | typed errors, JSON body, multipart upload |

## Known gaps and assumptions about the frozen contract

1. **The page of an API source does not exist in the mock.** The seed parts
   carry the source id `api-digikey-<mpn>`, but the page fixtures use
   `pdf-synthetic-mosfet`. `GET /api/sources/{id}/page/{n}` therefore answers
   `404` for the seed parts. The source viewer shows the value and the full
   provenance and an inline error for the page instead of a crash. With a real
   PDF source (`source.type === "pdf"`) the `react-pdf` renderer is used and
   the page text is shown under it.
2. **The multipart body is assembled by hand** in `src/api/client.ts`. jsdom's
   `FormData` and the `fetch` of Node do not agree on the body, and the request
   never reaches the server. The body that is built now is a standard
   `multipart/form-data` body with the field name `file` and is accepted by
   FastAPI and by the frozen mock.
3. **`src/test/setup.ts` was extended** (it is inside my write access): stubs
   for `matchMedia` and `ResizeObserver` (needed by `next-themes` and
   `recharts`) and the `File` class of Node instead of the one of jsdom
   (needed by the multipart parser of Node). See
   `docs/CHANGE_REQUESTS/h-frontend-1.md`.
4. **TanStack Table v9** is used with the new API (`useTable`,
   `tableFeatures`, `createColumnHelper`, `createSortedRowModel`). The v8 API
   is deprecated in v9.
5. **No pagination or virtualisation.** The search returns at most 50 rows, the
   compare page at most 4 parts. Both are limits of the plan, not bugs.
6. **The result of an extraction job is not displayed.** The job is started
   from the part detail page and its state and progress are shown; the
   extracted values are not rendered yet.
7. **The filter chips cover every field of the `SearchFilter` schema**
   (`family`, `manufacturer`, `manufacturer_in`, `mpn_contains`, `package`,
   `package_in`, `lifecycle_status`, `in_stock`, `text` and the `parameters`
   constraints). A field that the backend adds later would be ignored by the
   chip list.
8. **The colours of the charts** come from `--chart-1 … --chart-5` of
   `src/index.css`, which are grey in the frozen theme.
9. The `Offer` table has no "currency" column; the currency is shown with the
   price. `lead_time_days` is empty in the mock.

## Notes for the reviewer

* No secret, key or token exists in the frontend (`src/api/client.ts` only
  talks to `/api/...`).
* `frontend/src/api/types.ts` and `frontend/src/mocks/` were **not** modified.
* `frontend/package.json`, `vite.config.ts`, `tsconfig*.json` and
  `components.json` were **not** modified.
