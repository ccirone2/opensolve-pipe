> Discipline findings for [`../build-density.md`](../build-density.md), written 2026-10-30 against the running app before the build (`5693197`). Paths under `/tmp/claude-0/` are the reviewer's scratch evidence, not kept. The proposal's §4 says what was adopted.

# Build panel as a property inspector: measurements and row/section anatomy

Measured on the running app (script: scratchpad `insp.cjs`; tall tab-panel shots, unscrolled, in `shots/inspector-{desktop,mobile}-{P1curve,P1new,RV1,E1,O1,P1piping,fittings}.png`). Desktop tab panel is 735 px wide, mobile 366 px.

## 1. What a field costs now
A bare field is **label 20 + 4 + control 44 + grid gap 16 = 84 px**. A static hint adds 4 + 16 px per line: 20–100 px desktop, 20–160 px mobile. On desktop, `sm:grid-cols-2` pairs fields, but each row is as tall as its longer hint (Elevation + Status = 104, Rated dp + flow = 168). Repeated rows are cards: **a port costs 222 px** (name, size select, a 2-line hint, an "Edit piping" button), **a fitting costs 298–434 px desktop and 330–498 mobile**, and **a curve point costs 48 px**.

| Tab panel (Properties incl. ports; Piping for the pipe) | now D / M | (a) rows 40/44 + hints on focus | (b) unit inside | (c) collapsed sections | (d) tables | all, D / M |
|---|---|---|---|---|---|---|
| Pump with curve (P1, pump-transfer) | 1977 / 2301 | 4 op. fields 224→160 / 428→176 | 0 px; +29–57 px width | Efficiency, NPSHr, Mfr data → 32 each (now 300, 300, 44) | ports 484→136; points 48→36 | **~820 / ~950 (−59 %)** |
| Relief valve RV1 | 1156 / 1468 | 5 fields + subhead 656→232 / 968→260 | 0; kPa box 42 px | 2 static model paragraphs (112 / 224 px) → 32 | ports 484→136 / 508→184 | **~425 / ~510 (−63 %)** |
| Equipment E1 | 1188 / 1372 | 5 fields 688→232 / 872→260 | 0; kg/m³ box 57 px | — | ports as above | **~390 / ~470 (−66 %)** |
| Orifice O1 | 984 / 1152 | 4 fields + Cd fieldset 484→208 / 652→232 | 0; mm 42 px | — | ports as above | **~350 / ~425 (−64 %)** |
| Pipe card (discharge L2) | 594 / 770 | Material/Sched/Size/Length 4 rows 160 / 176 (+16 for the velocity note) | m, mm | Overrides is already 44 (keep) | resolved ID/roughness block 140/236 → 2 read-only rows + 1-line source = 112 / 120 | **~410 / ~455 (−31 / −41 %)** |
| Fittings, 3 (basin outlet, condenser) | 1166 / 1306 | — | — | library-entry block (4 lines) → 1 line | row: type ‖ qty ‖ 🗑, then row: K choice + 1-line K source = ~96 / ~120 per fitting | **~350 / ~430 (−70 %)** |

What each technique does on its own: **(a)** a bare field goes from 84 to 40 px (desktop) or 44 px (mobile), −48 to −52 %. Measured against the desktop's paired rows it is −23 % on bare fields; most of the rest comes from moving static hints to focus. **(b)** saves no height: it gives the value 29–57 px of width back, which is what makes (a) fit at 390 px, where the value column is about 214 px. **(c)** puts n fields behind a 32 px header. **(d)** is the largest single gain, because ports and fittings are rendered as forms inside cards.

## 2. Row anatomy (recommended)
- **Grid.** `grid-template-columns: var(--label-w) minmax(0,1fr)` with `--label-w: clamp(7.5rem, 36%, 11rem)`. When the container is narrower than 20 rem, the label stacks above the value (container query, so the form reflows at 320 px).
- **Label column.**
  - Text: `text-sm` with a 16 px line height, at most 2 lines. "Allowable operating region, lowest flow" wraps to 2 lines, and 2 × 16 still fits a 36 px row.
  - Alignment: top-aligned with `padding-top: calc((var(--ctl-h) - 16px)/2)`.
  - Second line, free when the label is 1 line: a state word in `text-[11px]`, either `default` (D10) or a teal `Changed`.
- **Value column.** Control height is `--ctl-h` (36 px fine pointer, 40 px coarse). Numeric inputs are capped at `max-w-48` (12 rem; 6 significant digits plus the suffix), so desktop has no 575 px number boxes. Selects and text fields take `1fr`. Long-option selects (fitting type, curve, material) use a **wide row**: the label sits above, the control spans both columns.
- **Unit suffix.** Inside the box, right-aligned, `text-xs text-slate-500`. Input `padding-right` = suffix width + 8 px. A click on the suffix focuses the input. Keep NumberField's `aria-label="… (kPa)"`. Gauge and absolute pressures show `kPa(g)` and `kPa(a)` in the suffix.
- **Notes.** One stack under the control, in the value column only (`col-start-2`), `text-xs`, in this order:
  1. error (`role=alert`)
  2. warning
  3. scenario note on **one 20 px line**: `[Changed] Base 2.50 m · Reset`. Reset is a text button with a 24 px minimum target. Keep the 2 px teal input border.
  4. "set by Winter, Peak"
  5. static hint, shown only on `:focus-within`, always in `aria-describedby`
- **Composite (mode select plus dependents).** This covers Control → setpoint/min speed, Rated by → rated values, Capacity given by → letter, Cd source → C. The dependent rows indent 12 px under the select, with a 2 px left rule (Blender sub-properties). One ChangeNote serves the group, as OrificeForm's fieldset does now.

## 3. Section header anatomy
- **Element.** `<h3><button aria-expanded aria-controls>`, 32 px tall (40 px coarse), the full width of the row. Use this rather than `<summary>` when the header carries actions such as "Remove curve" or "Add": the action buttons must sit outside the toggle.
- **Contents.** Chevron (16 px, rotates 90° when open), then the title (`text-sm font-semibold`), then a count (`text-xs text-slate-600`, tabular numerals): `· 2 set`, `· 3 points`, `· 2 ports`. A section that holds a warning or error adds a right-aligned amber/red icon with its count.
- **Keyboard.** Tab reaches the header. Enter or Space toggles it. No roving arrow keys (APG disclosure). Focus stays on the header.
- **Auto-open.** Always when the section holds an error, a warning or a scenario change. When it holds set values whose count the header cannot summarise (overrides). A collapsed curve whose header reads "· 3 points" stays collapsed. The open/closed state per section type goes in localStorage (a per-viewer convenience).
- **"n set".** The number of fields whose value is present and differs from the schema default read from openapi.json, never a copied default.

## 4. Tables for repeated rows
- `thead` 24 px with the unit in the header, rows of `--ctl-h`, and 2 px row spacing. A 24 px `#` column, a 32 px trash button, and a full-width quiet "+ Add point" button as the last row.
- **Ports:** `Port | Size ▾ | → Connected to X` (the link replaces "Edit piping"). The size hint moves to focus. The size-mismatch warning and its "Make the pipe NPS 4" fix become a full-width row under the port.
- **Fittings:** two lines per fitting. Line 1: type (wide) ‖ qty (64 px) ‖ 🗑. Line 2: the K choice, then a K source of at most one line with an expander. The citation stays visible (D8/D10).

## 5. Keep: these are already inspector-grade
- **PipeSegmentForm's Overrides.** A `<details>` that opens when an override is set, with the placeholder "From the library" in empty inputs (blank means inherit, like Figma's mixed/inherited values). Add the "· n set" count to it.
- **The pump's "Manufacturer data (optional)" disclosure,** collapsed when empty.
- **PointsTable's `compact` cells.** Units sit in the column header, and the hidden labels ("Point 1 flow") keep the table accessible. Only the rows need to get shorter.
- **NumberField's commit model.** Enter or blur commits, Escape reverts, there is no rounding to the display, and the unit is in `aria-label`. Onshape and KiCad behave the same way.
- **Scenario-locked fields:** read-only but still focusable, with a lock icon and "Same in every scenario". **ChangeNote's Base + Reset** (squeeze it to one line).
- **The library pipe-spec `<dl>`,** which is already a label/value grid. Make it the pattern for resolved, read-only values (inner diameter, roughness, Cv → K).
- **The port mismatch warning with its one-click fix.**

**Fix along the way:**
- Elevation comes first in every form (move it to the end of Geometry).
- RV1 has two always-visible model paragraphs (112 / 224 px); move them to a collapsed "About this model".
- The "Capacity" subheading repeats "Capacity given by".
- The desktop's two-column pairing breaks reading order and makes row heights uneven; one label/value column is denser *and* linear.
