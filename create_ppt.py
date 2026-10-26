"""Generate PartPilot feature presentation."""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt
import copy

# ── Palette ────────────────────────────────────────────────────────────────
BLACK      = RGBColor(0x00, 0x00, 0x00)
DARK_SURF  = RGBColor(0x12, 0x12, 0x15)
WHITE      = RGBColor(0xFF, 0xFF, 0xFF)
OFF_WHITE  = RGBColor(0xF4, 0xF4, 0xF5)
BLUE_HEAD  = RGBColor(0x42, 0x61, 0x88)   # twilight blue
SIGNAL_BLU = RGBColor(0x2B, 0x7F, 0xFF)   # signal blue accent
BORDER     = RGBColor(0x2A, 0x2A, 0x30)

SLIDE_W = Inches(13.33)
SLIDE_H = Inches(7.5)

prs = Presentation()
prs.slide_width  = SLIDE_W
prs.slide_height = SLIDE_H

BLANK = prs.slide_layouts[6]   # completely blank

# ── Helpers ────────────────────────────────────────────────────────────────

def add_rect(slide, x, y, w, h, fill=BLACK, alpha=None):
    shape = slide.shapes.add_shape(1, x, y, w, h)   # MSO_SHAPE_TYPE.RECTANGLE = 1
    shape.line.fill.background()
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    return shape


def add_text(slide, text, x, y, w, h,
             size=20, bold=False, color=WHITE,
             align=PP_ALIGN.LEFT, italic=False, wrap=True):
    txb = slide.shapes.add_textbox(x, y, w, h)
    tf  = txb.text_frame
    tf.word_wrap = wrap
    p   = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size  = Pt(size)
    run.font.bold  = bold
    run.font.color.rgb = color
    run.font.italic = italic
    return txb


def bg(slide):
    """Fill the whole slide with black."""
    add_rect(slide, 0, 0, SLIDE_W, SLIDE_H, BLACK)


def heading_bar(slide, label):
    """Thin twilight-blue top bar with section label."""
    bar_h = Inches(0.55)
    add_rect(slide, 0, 0, SLIDE_W, bar_h, DARK_SURF)
    # left accent stripe
    add_rect(slide, 0, 0, Inches(0.06), bar_h, SIGNAL_BLU)
    add_text(slide, label,
             Inches(0.2), Inches(0.05), Inches(12), bar_h - Inches(0.05),
             size=16, bold=True, color=BLUE_HEAD)


def bullet_card(slide, x, y, w, h, title, bullets, title_size=15, bullet_size=12):
    """Dark-surface card with a title and bullet list."""
    card = add_rect(slide, x, y, w, h, DARK_SURF)
    # top accent line
    add_rect(slide, x, y, w, Inches(0.04), SIGNAL_BLU)

    add_text(slide, title,
             x + Inches(0.18), y + Inches(0.12),
             w - Inches(0.3), Inches(0.35),
             size=title_size, bold=True, color=WHITE)

    body_y = y + Inches(0.5)
    body_h = h - Inches(0.55)
    txb = slide.shapes.add_textbox(
        x + Inches(0.18), body_y, w - Inches(0.36), body_h)
    tf = txb.text_frame
    tf.word_wrap = True
    first = True
    for b in bullets:
        if first:
            p = tf.paragraphs[0]
            first = False
        else:
            p = tf.add_paragraph()
        p.space_before = Pt(3)
        run = p.add_run()
        run.text = f"• {b}"
        run.font.size  = Pt(bullet_size)
        run.font.color.rgb = OFF_WHITE


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 1 — Title
# ══════════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(BLANK)
bg(s)

# large headline
add_text(s, "PartPilot",
         Inches(0.6), Inches(1.6), Inches(12), Inches(1.8),
         size=72, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

add_text(s, "AI-Assisted Component Data Mining",
         Inches(0.6), Inches(3.3), Inches(12), Inches(0.7),
         size=28, bold=False, color=BLUE_HEAD, align=PP_ALIGN.CENTER, italic=True)

add_text(s, "Power MOSFETs  ·  Gate Drivers  ·  Parametric Search  ·  BOM Risk",
         Inches(0.6), Inches(4.1), Inches(12), Inches(0.5),
         size=16, color=OFF_WHITE, align=PP_ALIGN.CENTER)

# bottom course label
add_rect(s, 0, SLIDE_H - Inches(0.55), SLIDE_W, Inches(0.55), DARK_SURF)
add_text(s, "Web Data Mining  ·  R5CO4201T  ·  Study Project",
         Inches(0), SLIDE_H - Inches(0.52), SLIDE_W, Inches(0.5),
         size=13, color=RGBColor(0x66, 0x66, 0x77), align=PP_ALIGN.CENTER)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 2 — What PartPilot Does (overview)
# ══════════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(BLANK)
bg(s)
heading_bar(s, "Overview — What PartPilot Does")

steps = [
    ("1  Collect", "Pulls part data from DigiKey, Nexar (Octopart) and Mouser APIs simultaneously."),
    ("2  Download", "Fetches datasheet PDFs with robots.txt compliance, 1 s delay, and SHA-256 hashing."),
    ("3  Extract", "Three-tier pipeline: table parser → LLM (JSON schema) → vision model. Higher tier only when the lower fails."),
    ("4  Validate", "Unit conversion (pint), range checks, cross-check against API values, confidence scoring."),
    ("5  Store", "Every value saved with source file, page, tier, condition, confidence, and status."),
    ("6  Serve", "FastAPI backend + React frontend: NL search, part detail, source viewer, review queue, BOM check, dashboard."),
]

card_w = Inches(3.9)
card_h = Inches(1.55)
gap    = Inches(0.22)
row1_y = Inches(0.75)
row2_y = row1_y + card_h + gap
start_x = Inches(0.28)

for i, (title, desc) in enumerate(steps):
    col = i % 3
    row = i // 3
    x = start_x + col * (card_w + gap)
    y = row1_y if row == 0 else row2_y
    bullet_card(s, x, y, card_w, card_h, title, [desc], title_size=14, bullet_size=11)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 3 — Architecture
# ══════════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(BLANK)
bg(s)
heading_bar(s, "System Architecture — 9-Module Pipeline")

modules = [
    "Collector\n(DigiKey · Nexar · Mouser)",
    "Raw Store\n(PDFs + JSON cache)",
    "Extractor\n(Tier 1 · 2 · 3)",
    "Validator\n(units · ranges · cross-check)",
    "Database\n(SQLite + vector index)",
    "Services\n(search · alts · BOM)",
    "API Layer\n(FastAPI)",
    "Review Queue\n(low-confidence values)",
    "Frontend\n(React + shadcn/ui)",
]

box_w = Inches(1.3)
box_h = Inches(0.85)
gap_x = Inches(0.12)
start_x = Inches(0.28)
y_mid   = Inches(2.5)

for i, mod in enumerate(modules):
    x = start_x + i * (box_w + gap_x)
    add_rect(s, x, y_mid, box_w, box_h, DARK_SURF)
    add_rect(s, x, y_mid, box_w, Inches(0.04), SIGNAL_BLU)
    add_text(s, mod, x + Inches(0.05), y_mid + Inches(0.08),
             box_w - Inches(0.1), box_h - Inches(0.1),
             size=9, bold=False, color=OFF_WHITE, align=PP_ALIGN.CENTER)
    # arrow (except last)
    if i < len(modules) - 1:
        arr_x = x + box_w + Inches(0.01)
        add_text(s, "→", arr_x, y_mid + Inches(0.28),
                 gap_x, Inches(0.3), size=10, color=SIGNAL_BLU, align=PP_ALIGN.CENTER)

# extraction tier detail
tier_y = Inches(4.0)
tiers = [
    ("Tier 1 — Rules",    "Table parser + regex\nAlways runs first"),
    ("Tier 2 — LLM",      "LangChain + JSON schema\nActivates on Tier 1 failure"),
    ("Tier 3 — Vision",   "Vision model on page image\nFallback for image-only tables"),
]
tw = Inches(3.9)
tx = Inches(0.28)
for i, (t, d) in enumerate(tiers):
    bullet_card(s, tx + i*(tw + Inches(0.3)), tier_y, tw, Inches(1.5), t, [d],
                title_size=13, bullet_size=11)

add_text(s, "Extraction Tiers — cost-efficient cascading fallback",
         Inches(0.28), tier_y - Inches(0.35), Inches(8), Inches(0.3),
         size=12, bold=True, color=BLUE_HEAD)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 4 — Data Collection & Extraction
# ══════════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(BLANK)
bg(s)
heading_bar(s, "Feature 1 — Data Collection & Extraction")

col_w = Inches(6.2)
col_h = Inches(6.2)
gap   = Inches(0.3)
ly    = Inches(0.7)
lx    = Inches(0.28)
rx    = lx + col_w + gap

bullet_card(s, lx, ly, col_w, Inches(2.4), "Multi-Source Collection", [
    "DigiKey v4 API — parameters, price, stock, lifecycle, datasheet links",
    "Nexar GraphQL — provider-first discovery, similar parts",
    "Mouser API — second price/stock source and cross-check",
    "OAuth 2.0 token refresh, retry with back-off, per-host rate limiter",
    "Raw JSON responses cached with date stamp",
    "300+ parts seeded across power MOSFETs and gate drivers",
], bullet_size=11)

bullet_card(s, lx, ly + Inches(2.6), col_w, Inches(2.4), "Datasheet Download", [
    "robots.txt checked for every host before first request",
    "1-second delay between requests, clear User-Agent with contact address",
    "File validated as real PDF, saved with SHA-256 hash in filename",
    "Scanned (image-only) PDFs flagged for Tier 3 vision extraction",
    "Source record written: URL, fetch timestamp, hash, type",
    "90 %+ PDF coverage target",
], bullet_size=11)

bullet_card(s, rx, ly, col_w, Inches(2.4), "Tier 1 — Table Parser & Regex", [
    "pdfplumber identifies Electrical Characteristics / Absolute Max Ratings pages",
    "Header and symbol columns parsed; rows matched via name_map table",
    "Min / typ / max values and test conditions read with regex",
    "Page number and method tag written with every value",
    "Failed fields passed to Tier 2 (no value is silently dropped)",
], bullet_size=11)

bullet_card(s, rx, ly + Inches(2.6), col_w, Inches(2.4), "Tier 2 & 3 — LangChain Chains", [
    "init_chat_model — provider swappable via config (OpenAI, Anthropic, Google)",
    ".with_structured_output(PydanticSchema) — zero hallucination by design",
    "Only relevant pages sent — context window and cost controlled",
    "SQLiteCache — identical inputs reuse the saved answer",
    "Tier 3 renders the page as an image; vision model fills remaining gaps",
    "token count + cost logged to llm_calls table per call",
], bullet_size=11)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 5 — Validation & Provenance
# ══════════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(BLANK)
bg(s)
heading_bar(s, "Feature 2 — Validation & Provenance")

cards = [
    ("Unit Conversion", [
        "All values normalised to SI base units via pint",
        "Supports voltage (V), current (A), resistance (Ω), charge (C/nC), time (ns/µs)",
        "Mis-matched units caught before storage",
    ]),
    ("Range Validation", [
        "Per-field allowed ranges defined for every MOSFET and gate-driver parameter",
        "Values outside range set to status = rejected with reason string",
        "min ≤ typ ≤ max ordering enforced",
    ]),
    ("API Cross-Check", [
        "Each extracted value compared against the distributor API value",
        "Tolerance window configurable per field",
        "Discrepancy sets status = review and raises confidence penalty",
    ]),
    ("Confidence Scoring", [
        "Score derived from: tier used, range pass, API match, condition completeness",
        "Three bands: high (green), medium (yellow), low (red) — shown as badge in UI",
        "Low-confidence values automatically queued for human review",
    ]),
    ("Provenance Storage", [
        "Every value stores: source file, page number, tier, condition (JSON), confidence, status",
        "Source Viewer opens the exact datasheet page beside the value in a slide-over panel",
        "SHA-256 hash detects datasheet changes between re-runs",
    ]),
    ("Review Queue", [
        "Low-confidence and cross-check failures surface in /review page",
        "Accept / Correct / Reject with keyboard shortcuts (j/k/a/x/c)",
        "Corrections feed back into name_map and prompt improvements",
        "8-second undo toast for accidental decisions",
    ]),
]

cw = Inches(4.1)
ch = Inches(2.0)
gx = Inches(0.22)
gy = Inches(0.22)
sx = Inches(0.28)
sy = Inches(0.75)

for i, (t, b) in enumerate(cards):
    col = i % 3
    row = i // 3
    x = sx + col * (cw + gx)
    y = sy + row * (ch + gy)
    bullet_card(s, x, y, cw, ch, t, b, title_size=13, bullet_size=10)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 6 — Natural-Language Search
# ══════════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(BLANK)
bg(s)
heading_bar(s, "Feature 3 — Natural-Language Parametric Search")

# query example box
add_rect(s, Inches(0.6), Inches(0.75), Inches(12.1), Inches(0.75), DARK_SURF)
add_rect(s, Inches(0.6), Inches(0.75), Inches(0.06), Inches(0.75), SIGNAL_BLU)
add_text(s, '🔍  "100 V N-channel MOSFET, Rds(on) below 5 mΩ, in stock"',
         Inches(0.8), Inches(0.8), Inches(11.5), Inches(0.65),
         size=16, bold=True, color=WHITE, italic=True)

cards = [
    ("Filter Builder Chain", [
        "LangChain chain converts free-text query into a structured JSON filter",
        "Filter validated against Pydantic schema before DB query",
        "LLM never chooses rows — only builds the filter; DB always picks results",
        "Deterministic regex fallback when LLM endpoint is unreachable",
    ]),
    ("Editable Filter Chips", [
        "Parsed filters shown as interactive chips in the UI",
        "Each chip supports operators: =, ≥, ≤, in",
        "Chips can be removed or edited inline without re-typing the query",
        "Debounced at 300 ms — live results as the user types",
    ]),
    ("Search Results Table", [
        "TanStack Table with custom sort indicators",
        "Columns: MPN, Manufacturer, Package, Lifecycle, key parameters",
        "CSV export for offline use",
        "Compare tray — select 2–4 parts and jump to side-by-side compare",
    ]),
    ("Performance & Safety", [
        "Target: answer in ≤ 5 seconds (NFR-04)",
        "LLM result cached in SQLiteCache — repeat queries are instant",
        "Rate limiter on /api/search — protects LLM quota",
        "API keys never reach the browser (NFR-02, NFR-07)",
    ]),
]

cw = Inches(6.2)
ch = Inches(2.35)
gx = Inches(0.3)
gy = Inches(0.22)
sx = Inches(0.28)
sy = Inches(1.65)

for i, (t, b) in enumerate(cards):
    col = i % 2
    row = i // 2
    x = sx + col * (cw + gx)
    y = sy + row * (ch + gy)
    bullet_card(s, x, y, cw, ch, t, b, title_size=13, bullet_size=11)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 7 — Part Detail & Source Viewer
# ══════════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(BLANK)
bg(s)
heading_bar(s, "Feature 4 — Part Detail & Source Viewer")

left_cards = [
    ("Part Detail Page  (/parts/:id)", [
        "Header: lifecycle badge (Active / NRND / Obsolete), family, MPN",
        "Direct action buttons: Compare, Alternatives, Datasheet",
        "Grouped parameter tables: Absolute Max, Electrical, Thermal, Package",
        "Discrepancy icon when extracted value differs from distributor data",
        "Provenance button on each value — opens Source Viewer",
    ]),
    ("Tabs — Offers & Alternatives", [
        "Offers tab: stock level, pricing tiers, lead time from all distributors",
        "Alternatives tab: pin-compatible drop-ins with parameter deltas",
        "Alternative explanation generated by LangChain (e.g. 'lower Rds(on), higher Qg')",
        "Hard rules filter alternatives that fail critical specs (e.g. lower Vds)",
    ]),
]

right_cards = [
    ("Source Viewer Panel", [
        "50 % width slide-over sheet (zero shadows, dark surface)",
        "react-pdf canvas renders exact datasheet page",
        "2-px bounding-box highlight around the extracted region",
        "Provenance metadata: source URL, fetch timestamp, SHA-256 hash",
        "'Flag this value' dispatches directly to the review queue",
    ]),
    ("Confidence Badges", [
        "Every parameter displays a colour-coded badge: green / yellow / red",
        "Badge reflects tier used + range pass + API match + condition presence",
        "Tooltip shows numeric confidence score and status reason",
        "Rejected values shown with a strike-through and reason label",
    ]),
]

cw = Inches(6.2)
ch = Inches(2.55)
gy = Inches(0.22)
sy = Inches(0.75)

for i, (t, b) in enumerate(left_cards):
    bullet_card(s, Inches(0.28), sy + i*(ch + gy), cw, ch, t, b, title_size=13, bullet_size=11)

for i, (t, b) in enumerate(right_cards):
    bullet_card(s, Inches(6.82), sy + i*(ch + gy), cw, ch, t, b, title_size=13, bullet_size=11)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 8 — BOM Check & Alternatives
# ══════════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(BLANK)
bg(s)
heading_bar(s, "Feature 5 — BOM Risk Check & Alternative Finder")

cards = [
    ("BOM Upload Workflow", [
        "Stepper UI: Upload CSV → Map Columns → Risk Audit",
        "5 MiB client-side file validation, drag-and-drop dropzone",
        "Sample demo BOM loader for quick demonstration",
        "Column mapper: assign MPN, Quantity, Reference Designator dynamically",
        "10-row preview table before analysis",
    ]),
    ("Risk Audit Results", [
        "Flags: Obsolete part, NRND, Low stock, Single-source risk",
        "Summary statistics bar + severity filter pills",
        "Detailed risk audit log per line item",
        "Manual catalog replacement picker for parts not yet indexed",
        "POST /api/bom/check — backend processes CSV, returns risk table JSON",
    ]),
    ("Alternative Part Finder", [
        "Ranks parts in the same family and package by weighted parameter distance",
        "Hard rules: never suggest a part with lower Vds or Id rating",
        "Stock and lifecycle status added to ranking",
        "One-sentence LangChain explanation per alternative (trade-off summary)",
        "GET /api/parts/{id}/alternatives — top-N ranked results",
    ]),
    ("Lifecycle Tracking", [
        "Status per part: Active · NRND · End-of-Life · Obsolete",
        "Status sourced from DigiKey and Nexar lifecycle fields",
        "Lifecycle badge shown on Part Detail header and search results",
        "BOM check automatically flags NRND and obsolete line items",
    ]),
]

cw = Inches(6.2)
ch = Inches(2.65)
gx = Inches(0.3)
gy = Inches(0.22)
sx = Inches(0.28)
sy = Inches(0.75)

for i, (t, b) in enumerate(cards):
    col = i % 2
    row = i // 2
    x = sx + col * (cw + gx)
    y = sy + row * (ch + gy)
    bullet_card(s, x, y, cw, ch, t, b, title_size=13, bullet_size=11)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 9 — Evaluation & Dashboard
# ══════════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(BLANK)
bg(s)
heading_bar(s, "Feature 6 — Evaluation Framework & Dashboard")

left_cards = [
    ("Gold Set & Metrics", [
        "80 hand-labelled parts, 5+ manufacturers, 10–15 fields each",
        "20 % of labels independently verified — inter-annotator agreement recorded",
        "eval/metrics.py: field accuracy, cost per datasheet, latency stats",
        "eval/gold_set.py: loader, validator, agreement report",
    ]),
    ("6 Experiments (WP8)", [
        "Exp 1: Tier 1 vs Tier 2 (text) vs Tier 2 (tables) vs Tier 3 — accuracy, cost, time",
        "Exp 2: Tiered use vs 'always best tier' — cost saved at same accuracy",
        "Exp 3: Validation on vs off — wrong values stopped",
        "Exp 4: NL search vs keyword search — query success on 30 queries",
        "Exp 5: Alternative finder vs expert opinion — Precision@3",
        "Exp 6: Accuracy by manufacturer",
    ]),
]

right_cards = [
    ("Platform Dashboard  (/dashboard)", [
        "KPI cards: total parts, coverage %, mean confidence, LLM cost",
        "Recharts: parts per family, values by status, LLM token usage, accuracy per family",
        "Strict monochrome palette — no coloured fills",
        "Accessible 'View as table' toggle for every chart",
        "Data served from GET /api/stats",
    ]),
    ("Extraction Jobs  (/jobs)", [
        "Start new extraction with MPN + family; zod-validated form",
        "Job status table: progress bar, state badges, message logs",
        "Real-time polling every 3 s while jobs run",
        "Job restart button for failed extractions",
        "BackgroundTasks in FastAPI — no request blocking",
    ]),
]

cw = Inches(6.2)
ch = Inches(2.55)
gy = Inches(0.22)
sy = Inches(0.75)

for i, (t, b) in enumerate(left_cards):
    bullet_card(s, Inches(0.28), sy + i*(ch + gy), cw, ch, t, b, title_size=13, bullet_size=10)

for i, (t, b) in enumerate(right_cards):
    bullet_card(s, Inches(6.82), sy + i*(ch + gy), cw, ch, t, b, title_size=13, bullet_size=10)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 10 — Tech Stack
# ══════════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(BLANK)
bg(s)
heading_bar(s, "Tech Stack")

stack = [
    ("Backend", [
        "Python 3.12, FastAPI, Uvicorn",
        "LangChain (langchain-core, provider packages)",
        "pdfplumber, PyMuPDF — PDF parsing",
        "pint — unit conversion",
        "SQLAlchemy + SQLite — database + vector index",
        "httpx + tenacity — HTTP with retry",
        "pytest — 765 tests, 100 % passing",
    ]),
    ("LangChain Chains", [
        "init_chat_model — provider-agnostic",
        ".with_structured_output(Pydantic) — typed extraction",
        "InMemoryRateLimiter, .with_retry()",
        "SQLiteCache — cost & latency reduction",
        "langchain-huggingface embeddings",
        "FAISS / Chroma vector store",
        "Supports OpenAI, Anthropic, Google, any OpenAI-compat. endpoint",
    ]),
    ("Frontend", [
        "React 18, TypeScript, Vite",
        "shadcn/ui + Tailwind CSS",
        "TanStack Query + TanStack Table",
        "react-pdf (pdf.js) — in-browser datasheet viewer",
        "Recharts — dashboard charts",
        "MSW (Mock Service Worker) for dev mocks",
        "Vitest + React Testing Library — 26 tests, 100 % passing",
    ]),
    ("Infrastructure", [
        "Docker Compose: backend :8000, frontend :5173, mock :8001",
        "nginx proxies /api to backend — frontend never hits APIs directly",
        "GitHub Actions CI — lint + test on every PR",
        "Makefile: setup · run-api · run-web · mock-api · test · lint",
        "data/ volume — PDFs and DB survive container restarts",
        "Bundle size: 125.98 kB gzip (target < 250 kB)",
    ]),
]

cw = Inches(3.1)
ch = Inches(6.0)
gx = Inches(0.22)
sx = Inches(0.28)
sy = Inches(0.72)

for i, (t, b) in enumerate(stack):
    x = sx + i * (cw + gx)
    bullet_card(s, x, sy, cw, ch, t, b, title_size=13, bullet_size=10)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 11 — Requirements Coverage
# ══════════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(BLANK)
bg(s)
heading_bar(s, "Requirements Coverage")

fr_items = [
    "FR-01  Collect from ≥ 2 APIs",
    "FR-02  Download datasheet PDFs",
    "FR-03  Extract ≥ 12 MOSFET fields (13 implemented)",
    "FR-04  Extract ≥ 10 gate-driver fields (13 implemented)",
    "FR-05  Save test condition with each value",
    "FR-06  Convert all values to standard units",
    "FR-07  Reject out-of-range values",
    "FR-08  Cross-check extracted vs API value",
    "FR-09  Store source, page, confidence per value",
    "FR-10  Review queue for low-confidence values",
    "FR-11  Natural-language search",
    "FR-12  Show datasheet page beside each value",
    "FR-13  Ranked alternative parts list",
    "FR-14  BOM CSV upload + risk table",
    "FR-15  Lifecycle status per part",
]

nfr_items = [
    "NFR-01  Obey API rate limits",
    "NFR-02  Keys stay on the server",
    "NFR-03  LLM cannot hallucinate values",
    "NFR-04  Search answers in ≤ 5 seconds",
    "NFR-05  Extraction cost within budget",
    "NFR-06  README + comprehensive tests",
    "NFR-07  Frontend never calls distributor API or LLM",
]

bullet_card(s, Inches(0.28), Inches(0.72), Inches(7.8), Inches(6.2),
            "Functional Requirements (15 / 15)", fr_items,
            title_size=14, bullet_size=11)

bullet_card(s, Inches(8.4), Inches(0.72), Inches(4.6), Inches(3.2),
            "Non-Functional Requirements (7 / 7)", nfr_items,
            title_size=14, bullet_size=11)

# test badge
add_rect(s, Inches(8.4), Inches(4.1), Inches(4.6), Inches(2.8), DARK_SURF)
add_rect(s, Inches(8.4), Inches(4.1), Inches(4.6), Inches(0.04), SIGNAL_BLU)
add_text(s, "✅  Test Verification",
         Inches(8.6), Inches(4.2), Inches(4.2), Inches(0.4),
         size=14, bold=True, color=WHITE)
test_lines = [
    "Backend pytest:  765 / 765 tests PASS",
    "Frontend Vitest: 26 / 26 tests PASS  (14 suites)",
    "Coverage: collectors · extraction · validation",
    "           search · alternatives · BOM · API",
]
txb = s.shapes.add_textbox(Inches(8.6), Inches(4.65), Inches(4.2), Inches(2.1))
tf = txb.text_frame; tf.word_wrap = True
first = True
for line in test_lines:
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    first = False
    p.space_before = Pt(4)
    r = p.add_run(); r.text = f"• {line}"
    r.font.size = Pt(11); r.font.color.rgb = OFF_WHITE


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 12 — Ethics & Security
# ══════════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(BLANK)
bg(s)
heading_bar(s, "Ethics, Security & Responsible Use")

cards = [
    ("API Compliance", [
        "Official APIs used before any scraping",
        "robots.txt checked for every new host",
        "Rate limits respected: DigiKey 120/min, Mouser 30/min, Nexar 1000/month",
        "1-second delay between all requests",
        "Clear User-Agent with team contact address",
    ]),
    ("Data Integrity", [
        "SHA-256 hash detects datasheet changes",
        "Date and URL recorded for every download",
        "Extracted facts stored; full datasheets not republished",
        "Study-only licence — not for commercial use",
        "No personal data collected at any point",
    ]),
    ("LLM Safety", [
        "LLM cannot hallucinate — structured output with Pydantic schema",
        "Prompt rules: 'Return null if value not in text'",
        "Page text treated as data only — prompt injection mitigated",
        "Every LLM call cached and logged with token count + cost",
        "Human review queue as final safety net",
    ]),
    ("Security", [
        "API keys in .env only — never in Git, browser, or LLM prompts",
        "Frontend calls only /api/* — nginx proxies to backend",
        "File upload limited to 5 MiB; MIME type validated",
        "CORS restricted to frontend origin",
        "Pydantic validates every API input",
    ]),
]

cw = Inches(6.2)
ch = Inches(2.7)
gx = Inches(0.3)
gy = Inches(0.22)
sx = Inches(0.28)
sy = Inches(0.75)

for i, (t, b) in enumerate(cards):
    col = i % 2
    row = i // 2
    x = sx + col * (cw + gx)
    y = sy + row * (ch + gy)
    bullet_card(s, x, y, cw, ch, t, b, title_size=13, bullet_size=11)


# ══════════════════════════════════════════════════════════════════════════
# SLIDE 13 — Summary
# ══════════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(BLANK)
bg(s)
heading_bar(s, "Summary")

add_text(s, "TRACE EVERY NUMBER.",
         Inches(0.6), Inches(0.85), Inches(12), Inches(1.0),
         size=44, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

summary = [
    ("Data Collection",      "3 distributor APIs  ·  300+ parts  ·  90 %+ PDF coverage"),
    ("3-Tier Extraction",    "Rules → LLM → Vision  ·  Cost-gated cascade  ·  13 fields per part"),
    ("Validation",           "Unit conversion  ·  Range checks  ·  API cross-check  ·  Confidence scores"),
    ("Provenance",           "Source file + page + tier + condition stored for every single value"),
    ("NL Search",            "Free-text to structured filter  ·  Editable chips  ·  ≤ 5 s response"),
    ("Part Tooling",         "Source Viewer  ·  Alternatives  ·  Side-by-side Compare"),
    ("BOM Risk Check",       "Upload CSV  ·  Map columns  ·  Obsolescence + supply risk table"),
    ("Review Queue",         "Human-in-the-loop triage  ·  Keyboard shortcuts  ·  Optimistic undo"),
    ("Evaluation",           "80-part gold set  ·  6 experiments  ·  Charts + failure analysis"),
    ("Quality",              "791 tests (100 % passing)  ·  CI/CD  ·  Docker  ·  < 250 kB bundle"),
]

row_h = Inches(0.45)
sy = Inches(2.0)
for i, (label, detail) in enumerate(summary):
    y = sy + i * row_h
    # label
    add_rect(s, Inches(0.5), y + Inches(0.04), Inches(2.2), row_h - Inches(0.08), DARK_SURF)
    add_text(s, label, Inches(0.6), y + Inches(0.05), Inches(2.1), row_h,
             size=11, bold=True, color=SIGNAL_BLU)
    # detail
    add_text(s, detail, Inches(2.85), y + Inches(0.05), Inches(10.1), row_h,
             size=11, color=OFF_WHITE)

# bottom bar
add_rect(s, 0, SLIDE_H - Inches(0.55), SLIDE_W, Inches(0.55), DARK_SURF)
add_text(s, "PartPilot  ·  Web Data Mining Mini Project R5CO4201T  ·  MIT Licence",
         Inches(0), SLIDE_H - Inches(0.52), SLIDE_W, Inches(0.5),
         size=12, color=RGBColor(0x55, 0x55, 0x66), align=PP_ALIGN.CENTER)


# ── Save ───────────────────────────────────────────────────────────────────
out = "/home/sarthi/Projects/ds-project-rag/PartPilot_Features.pptx"
prs.save(out)
print(f"Saved → {out}")
