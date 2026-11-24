# Usability: data entry

**Status: built (2026-11-24), web only, on `claude/kind-wozniak-oui7h9`; §10 is the as-built record.** No API, model or solver change; `METHOD_VERSION` unchanged (1.6.1): every change is in what the web app accepts or offers, and no stored or solved value of an existing project changes. Everything here is a reversible web default under D14 except where the owner answered (§1). Follows [`../ui-guide.md`](../ui-guide.md).

## 1. Scope

**The owner's request (2026-11-24).** "Before I work on more features, let's work on improvements to usability." An audit of main at `9093faf` (§2) offered nine items. **The owner's answers (2026-11-24):**

| Question | Answer |
|---|---|
| Which to build | "Fix the small web edits. Also implement number eight and number four; for number four, allow pasting a column of data, or a full table." That is: the field's own unit accepted and Previous/Next names not cut off (the small edits), unit-aware entry in any unit (item 8, `ui-ux-refinement.md` item 11, F9) and pasting points (item 4) |
| New pipes in US units: 30 ft, or 10 m shown as 32.8084 ft | **Round per unit system**: 10 m in SI, 30 ft in US units |

**Already decided, not re-opened.** SI inside, gauge at the edges (D4): gauge ⇄ absolute needs the atmospheric pressure, so a typed value with the wrong mark is refused, never converted by a guess. No uncited numbers (D8): every unit a typed value may carry is a unit of the registry in `utils/units.ts`, whose factors are exact by definition; no factor is added. Privacy (D3): a paste is read in the browser only. Nothing is released (D14): no compatibility shim.

**Not built, the owner's to choose later** (§2): since-last-solve changes, an opt-in auto-solve, a table of every pipe, a command palette and a network map.

## 2. The audit (2026-11-24)

Run at 1280×800 and 390×844 against main `9093faf` with the API: the home page, a new project built from blank (reservoir → pump → reservoir), its solve, number entry, the chiller example and Jump to. What worked: the empty project says what to add first; Inputs to check lists what is missing before a solve; results show on the element (ResultStrip); the phone layout holds.

| # | Finding | Where |
|---|---|---|
| U1 | "100 ft" in a field in ft: "Enter a number". Any unit after the number is refused | `NumberField.svelte`, `units.ts parseNumber` |
| U2 | The navigator's buttons cut the neighbour's name ("Next: conne…", "Previous: Pump…" at 1280 px; "Previous: Reserv…" on a phone), with no tooltip: the name is what the button is for | `PanelNavigator.svelte` |
| U3 | A new pipe in a US project is 10 m: the field shows 32.8084 ft, the Add dialog "32.81 ft"; a plug stub 3.281 ft | `factory.ts`, `edit.ts` |
| U4 | A pump curve is typed one cell at a time; nothing reads a paste | `PointsTable.svelte` |
| U5 | No change since the last solve is shown (`ui-ux-refinement.md` item 7) | Results |
| U6 | Each edit leaves the results out of date until Solve; solves took 0.01–1.2 s | Workspace |
| U7 | A change to every pipe (a schedule) is one connection at a time (PRD §3.3.2, D5 deferred) | Build |
| U8 | Entry in any unit (`ui-ux-refinement.md` item 11, F9) | `NumberField.svelte` |
| U9 | A command palette and a network map (`ui-ux-refinement.md` items 13 and 15; the map D5 deferred) | — |

## 3. Unit-aware entry (U1, U8)

`units.ts parseQuantity(text, category, displayUnit, {gauge, absolute})` reads a number, optionally followed by a unit, with or without a space: "100 ft", "100ft", "3 in", "4\"", "120 gpm", "36 m³/h", "68 °F", "50 psig", "300 kPa(g)", "3 barg".

- **Which units.** Every unit of the field's quantity in the registry: a length, a diameter and a head take m, mm, ft and in; a pressure Pa, kPa, MPa, bar and psi; the other categories their registry lists. A head typed as a pressure ("50 psi") is refused: converting needs the density. A dimensionless field takes no unit.
- **Spellings.** The registry's label and id, plus the spellings engineers type (`SPELLINGS`: feet, inch, ", ', gal/min, usgpm, lpm, cmh, m3/hr, fps, degF, pcf, cp, bhp, sq in…), matched without regard to case except where case tells two things apart (`EXACT_SPELLINGS`): MPa (mega) from mPa·s (milli), m and mm from M and MM ("million" in US practice), K (kelvin) from k ("thousand"). A unit in the wrong case is refused with the right one: "“mpa”: mind the capitals, “MPa”."
- **Gauge and absolute (D4).** A gauge field takes "psig", "kPa(g)", "barg" or the bare unit; an absolute field "psia", "kPa(a)", "bara" or the bare unit. A value with the other mark is refused ("This is a gauge pressure (psig): an absolute value needs the atmospheric pressure subtracted first."); a pressure difference (a check valve's cracking pressure, a relief valve's set pressure, a rated pressure drop) takes no mark.
- **Shown.** The field stores the SI value and shows it in its own unit; a value typed in another unit is followed by "Converted from 12 m." (in the field's description) until the next keystroke. The bounds are checked on the converted value.
- **Unchanged.** A bare number is the field's unit, as before; text that is not a number keeps its message. A comma is not read ("1,5": decimal mark or thousands separator).

## 4. The navigator's names (U2)

On wide screens the walk's two buttons take 55 % of the bar (they shrank with their text before, so a short name left them narrow and a long one was cut), and the breadcrumb, which scrolls, takes the rest. "Previous" and "Next" are in each button's accessible name ("Previous: Reservoir R1", "Next: connect discharge") but not shown beside the name: the arrows say which way, and the name gets the room. A name still too long is whole in the button's tooltip. On phones the same buttons fill the bottom bar.

## 5. Round default lengths (U3)

`factory.ts defaultPipeLength(units)` and `shortPipeLength(units)`: 10 m and 1 m where lengths show in m or mm, 30 ft (9.144 m) and 3 ft (0.9144 m) where they show in ft or in (the owner's answer). They are the lengths a new connection, an added pipe segment, an insertion's downstream half, a plug stub and an open discharge are given; no existing pipe changes, and the schema has no default length, so no "default" label is involved. A project that changes its units keeps its pipes; only new ones follow.

## 6. Paste a column or a table (U4)

`utils/paste-points.ts readPastedPoints` reads a paste into any cell of a curve's points table (the head curve, efficiency and NPSHr):

- **One value** (no tab, one line): the field takes it as typed text, so "300 gpm" pastes as before.
- **A column** fills the column pasted into, from that row down, adding rows as needed; the other column is kept.
- **Two columns** fill both, from that row down, whichever cell was pasted into.
- **Separators.** Tabs (a spreadsheet's copy) when the text has any; otherwise runs of spaces or semicolons (a data sheet copied from a PDF). Commas are refused: a comma can be a decimal mark, a thousands separator or a list, and guessing could store a value 1,000 times off.
- **Headings.** A first row that does not start with a number is a heading; a unit in brackets at a heading's end ("Flow (m3/h)", "Head [m]") is that column's unit, converted as typed entry is (§3); a heading without a unit means the table's display unit. A cell may carry its own unit (tab-separated).
- **Point numbers.** A first column numbered 1, 2, 3… beside two data columns (this table copied, or a data sheet) is dropped.
- **All or nothing.** One cell that does not read, one out of the schema's bounds, a heading whose unit is not of the column's quantity, ragged rows, more than two columns, or more rows than the table takes (50): nothing is pasted, and the line under the table says why, with the row and the column ("Nothing was pasted: row 2, flow, “abc”: Enter a number, e.g. 12.5 or 1.2e-3.").
- **Said.** After a paste the line under the table says what it read ("Pasted 4 points: flow in m³/h, head in m."), a polite live region; the next edit of a cell clears it. Before any paste it says that a column or a table can be pasted. When the paste completes a new pump's curve, the curve is saved and its table replaced; the note carries over (`bind:pasted`).

## 7. Verification

Vitest: `units.test.ts` (every rule of §3, expected values the unit definitions restated, not the registry), `NumberField.svelte.test.ts` (own unit, another unit with its note, the gauge refusal, bounds on the converted value), `paste-points.test.ts` (every rule of §6), `PointsTable.svelte.test.ts` (a table into an empty curve, a column into one column, a bad cell, a single value left to the field, the hint), `edit.test.ts` (the lengths of §5, written as 30 × 0.3048 and 3 × 0.3048), `PanelNavigator.svelte.test.ts` (unchanged, the accessible names). Playwright: `tests/data-entry.e2e.ts` on desktop and phone against the real API (a new US project: 30 ft in the Add dialog and the suction pipe, Previous and Next not cut off, a metric table pasted into the new curve and converted, "12 m" in a ft field converted and said, "14.7 psia" refused in a gauge field and "2 psig" taken, solved), and the four e2e flows that read the navigator's text (now the name, with the full accessible name checked too). The whole suites at both sizes.

## 8. Files

`apps/web/src/lib/utils/units.ts` (`parseQuantity`, `SPELLINGS`, `EXACT_SPELLINGS`), `utils/paste-points.ts` (new), `utils/factory.ts` (`defaultPipeLength`, `shortPipeLength`), `utils/edit.ts`, `utils/piping.ts` (`addPipe`'s length), `components/ui/NumberField.svelte` (units, the conversion note, `onpaste`), `components/panel/PointsTable.svelte` (paste, its note), `components/panel/forms/PumpCurveEditor.svelte` (the note kept), `components/panel/PanelNavigator.svelte`, `ConnectionPanel.svelte`, `AddComponentDialog.svelte`; tests beside each, and `tests/data-entry.e2e.ts`.

## 9. Later

- The remaining audit items U5–U7 and U9 (§2), for the owner.
- Paste a table of more than two columns into a pump's curves at once (flow, head, efficiency, NPSHr): the efficiency and NPSHr tables have their own flows, so it needs a rule for which rows go where.
- Typed units on a phone: fields that take no negative value open the decimal keypad (`inputmode="decimal"`), which has no letters, so a unit is typed only where the field allows negatives; paste works everywhere.
- Gauge ⇄ absolute converted through the project's atmospheric pressure, shown, rather than refused.
- The home page's How it works shots show the navigator's old text ("Next: Discharge isol…"); retaken by hand when next due (`landing-page.md` §7).

## 10. As built

1. **§4, accessible names.** First built as visually hidden "Previous: " and "Next: " spans; the accessible-name computation trims a span's trailing space, so the names read "Next:Transfer pump". Each button carries `aria-label` instead, which contains the visible name (WCAG 2.5.3).
2. **§6, the note kept.** The first e2e run found the note gone after a paste that completed a new curve: saving it replaces the new-curve table with the saved curve's. The note is bindable, and `PumpCurveEditor` holds the head curve's across the swap.
3. **§3, "0x10".** Read as 0 followed by a unit it does not know, and refused as such ("“x10” is not a unit this field takes"), not with the not-a-number message; refused either way.
