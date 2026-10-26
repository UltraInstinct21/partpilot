# PartPilot Project Handoff

PartPilot is a production-ready web platform for electronics engineers to search parametric component data, verify datasheet provenance for every extracted value, compare components side-by-side, evaluate Bill-of-Materials (BOM) supply and obsolescence risk, and triage AI-extracted values in a human-in-the-loop review queue.

---

## 1. Quick Start Commands

### Frontend Development
```bash
cd frontend
npm install
npm run dev
```
Runs the Vite development server with MSW (Mock Service Worker) mocks enabled by default.

### Frontend Unit & Component Tests
```bash
cd frontend
npm test
```
Executes all 14 test suites and 26 test cases via Vitest and React Testing Library.

### Frontend Production Build
```bash
cd frontend
npm run build
```
Type-checks via `tsc -b` and compiles client assets with Vite. Main bundle gzip size is **125.98 kB** (target limit: < 250 kB).

### Backend Test Suite
```bash
cd backend
.venv/bin/pytest backend/tests
```
Runs the complete backend test suite across data collection, extraction, validation, search, alternatives, BOM risk evaluation, and FastAPI endpoints (**765 tests passing in ~27 seconds**).

---

## 2. Design System Adherence ("Air" Style with Dark Grey Surfaces)

The user interface adheres strictly to the design rules with a refined dark grey palette:

- **Theme:** Dark mode only (`color-scheme: dark`). No theme toggle.
- **Color Tokens:**
  - Canvas: `#000000` (Base dark void)
  - Dark Grey Surfaces: `#121215` (Sleek dark surfaces for cards, tables, inputs, dialogs, and sheets)
  - Whiteout / Text: `#ffffff` & `#f4f4f5` (Primary text and high-contrast labels on dark surfaces)
  - Borders: `rgba(255, 255, 255, 0.10)` to `rgba(255, 255, 255, 0.15)` (Subtle outlines for depth without elevation)
  - Twilight Blue: `#426188` (Headings on dark only)
  - Signal Blue: `#2b7fff` (Text links only, never used as button or chart fills)
- **Strict Non-Negotiables:**
  - **Zero Shadows:** `shadow-none` enforced across all components, sheets, and dialogs.
  - **Zero Box Outlines in Feature Section:** The "Built for hardware engineers" landing page section uses an editorial, open 3-column layout without boxes or emojis.
  - **Full Available Width:** The layout dynamically expands to the full available viewport width (`w-full px-4 sm:px-6 lg:px-8`) across all pages.
  - **Liquid Glass Floating Dock:** The topbar navigation is styled as a fixed floating liquid glass dock powered by React Bits `<GlassSurface>` (`fixed top-3 sm:top-4 inset-x-0 z-50 flex justify-center`), floating directly above the landing page background image and content with WebGL/SVG chromatic dispersion and backdrop refraction.
  - **Background Images:** Uses `bg1.jpeg` and `bg2.jpeg` from the public folder as the hero backdrop on the landing page, seamlessly underflowing the floating glass dock and fading smoothly into the black canvas.
  - **Zero Gradients:** Gradients are restricted solely to the landing page backdrop fade into the `#000000` canvas.
  - **Strict Radii:** Inputs `4px`, buttons `8px`, cards `12px`, images `11px`, pills `9999px` (toggle chips only).
  - **Zero Em Dashes:** Automated scanners confirm 0 occurrences of em dashes (`—` / `\u2014`) across all code and UI text.
  - **No Authentication:** All routes are public and open.

---

## 3. Architecture & Route Implementation

### 1. Home (`/`)
- Atmospheric full-bleed hero with Anton 900 display headline, Caveat italic accent ("source"), and natural language search field.
- Seamless backdrop using `public/bg1.jpeg` and `public/bg2.jpeg` extending from the top edge of the viewport underneath the floating liquid glass dock, with a smooth gradient fading into the black canvas below.
- Live platform telemetry row (parts indexed, datasheets attached, pending review items) rendered as dark grey `#121215` cards with `border-white/10`.
- Editorial "Built for hardware engineers" 3-column section: strictly boxless, cardless, and emoji-free.
- Compressed display statement: `TRACE EVERY NUMBER.`

### 2. Parametric Search (`/search`)
- Natural-language query parser debounced at 300ms.
- "Understood as" filter chips row with popover operators (`=`, `>=`, `<=`, `in`) and direct chip removal.
- Filter rail (Family segmented control, manufacturer multi-select, package, lifecycle status, stock toggle, parameter range sliders with text inputs).
- TanStack Table within Haze card, custom sort indicators, CSV export, and compare tray integration.

### 3. Part Detail (`/parts/:id`)
- Header card with lifecycle badge, family, and direct action buttons (Compare, Alternatives, Datasheet).
- Grouped parameter tables (Absolute Maximum Ratings, Electrical Characteristics, Thermal, Package).
- Discrepancy indicator icons when extracted values differ from distributor data.
- Provenance buttons opening the Source Viewer.
- Offers tab (stock, pricing tiers, lead time) and Alternatives tab (pin-compatible drop-in replacements with parameter deltas).

### 4. Source Viewer (`SourceViewer` Component)
- 50% desktop slide-over sheet (`Sheet`) with zero shadows.
- Embedded `react-pdf` canvas with raster fallback and 2px bounding box highlight around the extracted region.
- Provenance metadata (source URL, fetch timestamp, SHA-256 hash copy button).
- "Flag this value" action button dispatching to the review queue.

### 5. Side-by-Side Compare (`/compare`)
- Compares 2 to 4 parts across common parameters.
- Sticky headers with lifecycle badges and remove triggers.
- "Best in row" indicator badges and condition discrepancy warnings.
- Persistent compare tray persisting selections in `localStorage`.

### 6. BOM Risk Check (`/bom`)
- Powered by React Bits `<Stepper>` & `<Step>` workflow:
  1. **Upload CSV**: 5 MiB client-side validation, file drag-and-drop dropzone, sample demo BOM loader.
  2. **Map Columns**: Dynamic column assignment (MPN, Quantity, Reference Designator) and 10-row preview table.
  3. **Risk Audit**: Obsolescence & supply risk analysis table, summary statistics, severity filter pills, detailed risk audit log, and manual catalog replacement picker for unindexed components.

### 7. Quality Review Queue (`/review`)
- Split layout: 45% table on left, 55% inspection and triage panel on right (collapses to Sheet under 1024px).
- Table columns: Part, Parameter, Extracted value, API value, Tier, Confidence meter, Reason flagged, Actions.
- Right inspection panel: Side-by-side values, embedded `PdfPage`, and decision form.
- Keyboard shortcuts: `j`/`k` to navigate rows, `a` to accept, `x` to reject, `c` to correct.
- Optimistic update toast with an 8-second "Undo" button.
- Bulk accept action with count confirmation dialog for verified matching parameters.
- Empty state linking to `/jobs`.

### 8. Extraction Jobs (`/jobs`)
- New extraction dialog with zod validation for MPN and family parameters.
- Job status table with progress bar, state badges, message logs, and job restart button.
- Real-time polling every 3 seconds while background jobs run.

### 9. Platform Intelligence Dashboard (`/dashboard`)
- KPI summary cards (Total parts, Coverage %, Mean confidence, LLM cost).
- Strictly monochrome charts powered by Recharts (parts per family, values by status, LLM tokens, accuracy per family).
- Accessible "View as table" toggle buttons for every chart.

---

## 4. React Bits Component Integrations

The frontend integrates premium, open-source React Bits components configured with dark themes, strict zero-shadow styling, and responsive full-width behavior:

1. **`<AnimatedList />`** (`frontend/src/components/react-bits/AnimatedList.tsx`):
   - Integrated into **Filter Chips** (`frontend/src/components/domain/filter-chips.tsx`) for the operator and value picker popover.
   - Integrated into **Command Palette** (`frontend/src/components/command-palette.tsx`) for fast keyboard navigation across matched electronic parts and system actions.
   - Configured with keyboard arrow navigation, pop animation, dark frosted surface styling, and `@hugeicons/react` iconography.

2. **`<GlassSurface />`** (`frontend/src/components/react-bits/GlassSurface.tsx`):
   - Integrated into the **Topbar Liquid Glass Dock** (`frontend/src/components/app-nav.tsx`).
   - Renders a responsive, floating glass dock with WebGL chromatic dispersion, dynamic light reflection, and backdrop blur.
   - Includes graceful fallback for headless and jsdom environments.

3. **`<Stepper />` & `<Step />`** (`frontend/src/components/react-bits/Stepper.tsx`):
   - Integrated into the **BOM Risk Check** (`frontend/src/pages/bom-check-page.tsx`).
   - Replaced static wizard indicators with an interactive, spring-animated stepper managing Upload CSV, Map Columns, and Risk Audit stages.
   - Supports bi-directional step navigation, synchronized state with upload and analysis hooks, and zero elevation styling.

---

## 5. Test Verification Status

| Test Suite | Tests Passing | Status |
| :--- | :--- | :--- |
| `frontend/tests/api-client.test.ts` | 4 / 4 | PASS |
| `frontend/tests/bom-check-page.test.tsx` | 1 / 1 | PASS |
| `frontend/tests/compare-page.test.tsx` | 1 / 1 | PASS |
| `frontend/tests/confidence-badge.test.tsx` | 3 / 3 | PASS |
| `frontend/tests/dashboard-page.test.tsx` | 1 / 1 | PASS |
| `frontend/tests/error-handling.test.tsx` | 2 / 2 | PASS |
| `frontend/tests/filter-chips.test.tsx` | 1 / 1 | PASS |
| `frontend/tests/lifecycle-badge.test.tsx` | 4 / 4 | PASS |
| `frontend/tests/loading-state.test.tsx` | 1 / 1 | PASS |
| `frontend/tests/part-detail-page.test.tsx` | 2 / 2 | PASS |
| `frontend/tests/review-queue-correction.test.tsx` | 1 / 1 | PASS |
| `frontend/tests/review-queue-page.test.tsx` | 2 / 2 | PASS |
| `frontend/tests/search-page.test.tsx` | 2 / 2 | PASS |
| `frontend/tests/source-viewer.test.tsx` | 1 / 1 | PASS |
| **Frontend Total** | **26 / 26 (14 test files)** | **100% PASS** |
| **Backend Total** (`pytest backend/tests`) | **765 / 765** | **100% PASS** |
