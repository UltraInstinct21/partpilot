# Design Decisions: PartPilot Frontend

## 1. Visual Token System

The design strictly implements the "Air" visual system defined in `DESIGN.md`.

### Color Tokens

| Name | Hex / Value | CSS Variable / Token | Role |
| :--- | :--- | :--- | :--- |
| Canvas | `#000000` | `--color-black-void` / `bg-canvas` | Base application background behind all sections |
| Whiteout | `#ffffff` | `--color-whiteout` / `text-whiteout` | Primary text on dark surfaces, 1px hairline borders on dark |
| Haze | `#f5f5f5` | `--color-haze` / `bg-haze` | Card surfaces, inputs, light button fills (light islands on dark) |
| Ink | `#1b1b1b` | `--color-ink` / `text-ink` | Body and heading text on light surfaces, button borders on Haze |
| Twilight Blue | `#426188` | `--color-twilight-blue` / `text-twilight-blue` | Heading text on dark backgrounds only (cool, desaturated steel blue) |
| Signal Blue | `#2b7fff` | `--color-signal-blue` / `text-signal-blue` | Text links and link underlines only. Never button, background, or chart fill |

### Surface Hierarchy & Borders

- **Canvas (Level 0):** `#000000`. Base dark canvas.
- **Haze Cards (Level 1):** `#f5f5f5`. Content cards, tables, inputs, and sheets (light islands on dark).
- **Whiteout (Level 2):** `#ffffff`. Elevated form elements and focus outlines.
- **Borders:** Exactly 1px width.
  - On dark surfaces: `rgba(255, 255, 255, 0.2)`
  - On Haze surfaces: `rgba(0, 0, 0, 0.1)`
- **Shadows:** Strictly zero shadows (`shadow-none` across all components). Elevation is conveyed solely via flat background contrast and 1px borders.
- **Gradients:** Strictly zero gradients across all elements, backgrounds, and charts.

### Border Radii

- **Inputs & Selects:** `4px` (`rounded-[4px]`)
- **Buttons:** `8px` (`rounded-[8px]`)
- **Cards, Sheets & Dialogs:** `12px` (`rounded-[12px]`)
- **Images:** `11px` (`rounded-[11px]`)
- **Pills (toggle & filter chips only):** `9999px` (`rounded-full`)
- **Tags (status labels):** Rectangular with `4px` radius (`rounded-[4px]`). Never a pill.
- **No other radius** is permitted.

### Typography Scale & Font Roles

- **Control (Inter):** Primary interface typeface.
  - Weight 500: UI labels, navigation, buttons, table headers, and links.
  - Weight 400: Long-form prose and descriptions only.
- **Control Compressed (Anton):** Weight 900, uppercase. Used exactly once on the Home page display statement: `TRACE EVERY NUMBER.`
- **Control Cursive (Caveat):** Weight 500 italic. Used for exactly one italic word in the home hero headline: *"source"*.
- **Scale:**
  - Caption: 13px (line-height 1.5)
  - Body: 16px (line-height 1.5)
  - Subheading: 20px (line-height 1.4)
  - Heading: 32px (line-height 1.1)
  - Heading-lg: 56px (line-height 1.0)
  - Display: 259px scaled down smoothly via `clamp()` on mobile.

### Deliberate Typography Deviation for Data Density

- Standard prose and form inputs remain strictly at 16px to prevent iOS auto-zoom and maintain readability.
- Compact data table cells, filter chips, and status tags are adapted to 14px (with 13px for unit symbols and secondary timestamps) to support engineering parametric density.

---

## 2. Status & Confidence Encoding Without Color

In accordance with strict accessibility guidelines and the monochrome design rules, color alone never carries meaning.

1. **Confidence Meter:**
   - Visual: 4-segment monochrome stepped bar (empty/filled black segments on Haze, white segments on dark).
   - Numeric: Exact score formatted as decimal (e.g. `0.95`).
   - Text label:
     - `High` at 0.90 or above.
     - `Medium` at 0.70 to 0.89.
     - `Low` below 0.70.
   - Thresholds are stored centrally in `frontend/src/lib/constants.ts`.

2. **Lifecycle Tags:**
   - `Active`: Solid 1px outline (`border border-ink/40 text-ink`).
   - `NRND`: Dashed 1px outline (`border border-dashed border-ink/60 text-ink`).
   - `Obsolete`: Inverted style (`bg-ink text-haze`).
   - `Unknown`: Muted 1px outline with reduced opacity text.
   - Every tag explicitly spells out the full word (never an icon only).

3. **Disagreement Detection:**
   - When extracted datasheet value differs from distributor API value, a distinct split icon (`AlertTriangle` / `Layers`) appears with an accessible tooltip showing both values side by side.

4. **Error Handling:**
   - Monochrome warning alert icon, clear descriptive sentence, 1px border. No red fills or text.

---

## 3. Wireframes

### Search Page (/search)

```text
+---------------------------------------------------------------------------------+
| TOP BAR: PartPilot [Search] [Compare] [BOM] [Review] [Jobs] [Dashboard]   [Cmd+K]|
+---------------------------------------------------------------------------------+
| Natural Language Search: [ 100V N-channel MOSFET, Rds(on) < 5mOhm             ] |
| Understood As: (family: mosfet) [x]  (vds_max >= 100V) [x]  [+ Add filter]       |
+-------------------+-------------------------------------------------------------+
| FILTER RAIL (280) | RESULTS TABLE (Haze Card, 12px radius, no shadow)           |
| Family:           | MPN        | Mfr     | Vds  | Id   | Rds(on) | Stock | Conf   |
| [MOSFET][Driver]  |------------+---------+------+------+---------+-------+--------|
| Package:          | BSC030N08N | Infineon| 80V  | 100A | 3.0 mO  | 1,200 | [||||] |
| [x] TO-220        | IRF3205S   | Infineon| 55V  | 110A | 8.0 mO  | 850   | [||||] |
| Lifecycle:        | CSD19536KTT| TI      | 100V | 100A | 2.7 mO  | 4,500 | [||||] |
| [x] Active        |------------+---------+------+------+---------+-------+--------|
| In stock only [x] | < 1 - 25 of 142 >                                [Export CSV] |
+-------------------+-------------------------------------------------------------+
```

### Part Detail Page (/parts/:id)

```text
+---------------------------------------------------------------------------------+
| [<- Back to Search]                                                             |
| HEADER CARD (Haze, 12px radius):                                                |
| BSC030N08NS5                    [Active]                                        |
| Infineon Technologies . Power MOSFET . PG-TDSON-8                               |
| [Open Datasheet Page]   [Add to Compare]   [Find Alternatives]                  |
+---------------------------------------------------------------------------------+
| TABS: [ Specs ] [ Offers ] [ Alternatives ] [ History ]                         |
+---------------------------------------------------------------------------------+
| SPECS TABLE (Haze Card, 12px radius, no shadow):                                |
| Parameter                     | Min  | Typ   | Max  | Unit | Condition  | Source|
|-------------------------------+------+-------+------+------+------------+-------|
| Drain-Source Voltage V(BR)DSS | 80   | -     | -    | V    | ID=250uA   | [p. 1]|
| Static Drain-Source RDS(on)   | -    | 2.5   | 3.0  | mOhm | VGS=10V    | [p. 2]|
| Total Gate Charge Qg          | -    | 46    | 58   | nC   | VDD=40V    | [p. 3]|
+---------------------------------------------------------------------------------+
```

### Review Queue (/review)

```text
+---------------------------------------------------------------------------------+
| TOP BAR                                                            42 items left|
+--------------------------------------+------------------------------------------+
| QUEUE TABLE (45%):                   | INSPECTION & DECISION PANEL (55%):       |
| Part      | Param    | Val   | Conf  | Part: BSC030N08NS5                       |
|-----------+----------+-------+-------| Param: Total Gate Charge Qg              |
| BSC030N08 | Qg       | 46 nC | 0.65  | Extracted: 46 nC  | API: 58 nC           |
| IRF3205S  | Rds(on)  | 8 mO  | 0.58  | Reason: Disagreement with DigiKey        |
| NCP51820  | tpd      | 50 ns | 0.62  | [Datasheet PDF Page 3 Preview]           |
|           |          |       |       |------------------------------------------|
| Filter: [All Families] [All Tiers]   | Value: [ 46.0     ] Unit: [ nC       v ] |
|                                      | [Accept (Haze)] [Correct & Accept] [Rej] |
| Keyboard: j/k move, a accept, x rej  | Undo available for 8s                    |
+--------------------------------------+------------------------------------------+
```
