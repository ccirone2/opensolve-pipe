# Build density: a field registry, compact rows and budgets CI enforces

**Status: built (2026-10-30), web only, on `web/build-density`; §11 is the as-built record.** No API, model or solver change; `METHOD_VERSION` unchanged (1.6.0). Every layout and tier choice here is a reversible web default under D14; §5 lists each with its reason and the goal it serves, so the owner can reverse any of them. Follows [`ui-ux-refinement.md`](ui-ux-refinement.md), whose §2 method (measure the running app, then act) it reuses for the Build forms, which that proposal never measured.

## 1. Scope

**The owner's request (2026-10-30, quoted in substance).** Not one redesign of the Build panel: the app should stay condensed, structured and quick to scan as features keep adding fields (D18–D23 each did). A future slice should get dense, grouped, consistent UI by declaring a field in one place, and CI should fail when density regresses. Most core information stays visible, especially in Build; inputs sit in tight, organised, grouped sections; secondary detail goes behind progressive disclosure; buttons, menus and toolbars use little vertical space without hiding core items. Decide without asking, by the GOALS order, and record every choice.

**Already decided, not re-opened.** D10 (rules read from the schema and its `x-…` extensions, never copied; "default" labels; privacy), D15 (scenario notes at their field; locked fields), D4 (gauge pressures labelled), GOALS §4.7 (phone and desktop equal), D14 (web defaults reversible), and the existing touch-target assertions in the e2e suite (44 px for the header's and Results' buttons on both projects: kept, §5 D3).

**Targets (the owner's).** Core fields visible without scrolling at 390×844; chrome ≤ 15 % of the Build pane at 1280×800; the most common edit per component ≤ 2 actions after opening its panel; axe-core zero violations at both sizes; a new field = one registry entry and its label.

## 2. Method

The app was driven with Playwright at 1280×800 and 390×844 (`measure.cjs`, kept with the findings). A project with one component of every kind (19 types, chained, built by the app's own `createComponent`) and the three examples (solved) were opened, and every Build form was measured: each row of the Build pane's height is classified by what covers it, in the order input > result strip > chrome (buttons, tabs, disclosure rows, links) > label > prose (hints, notes) > whitespace, both for the **first screen** (the pane as shown, scrolled to its top) and for the **whole** form. The y of every field and the scroll needed to reach it were recorded. Six disciplines and a red team then worked in parallel from the running app (screenshots, DOM measurements, computed styles), each writing a findings file kept under [`build-density/`](build-density/findings-cockpit.md) (§4).

## 3. Measurements before the build (`5693197`)

### 3.1 Where the Build pane's first screen went

Share of the first screen, 1280×800 (Build pane 747 px, its scrolling area 633 px) and 390×844 (pane 699 px, area 585 px), unsolved; ranges over the 19 types.

| | Chrome | Whitespace | Hint prose | Labels | Inputs | Result strip (solved) |
|---|---|---|---|---|---|---|
| 1280×800 | 23.6–29.5 % | 25–33 % | 7–20 % | 7–11 % | 18–29 % | 13–26 % |
| 390×844 | 26.9–29.6 % | 24–31 % | 5–19 % | 7–10 % | 19–32 % | 16–24 % |

- **Every control 44 px**, every field 80–84 px (label 20 + 4 + control 44 + gap 12–16) plus its hint, which was **always shown**: 3–17 hints per form, 64–544 px (the relief valve 544 px on a phone).
- **Chrome above the first field**: breadcrumb bar 53 px, kind line + name ~75, component actions 44 (56 on phones, icon above label), Properties/Piping tabs 45, the bottom Previous/Next bar ~60; on a phone also the two-row header (101 px) and the view tabs (44).
- **Elevation first** on every type, before its defining inputs (a gate valve's Status at content y 498–542 on a phone: below the fold).
- **Content height** per form (desktop / phone): pump 1570 / 1874 (2442 / 2818 solved), relief valve 1507 / 1831, equipment 1539 / 1735, orifice 1335 / 1515, valves 1107–1235 / 1203–1435, reservoir 881 / 1113.

### 3.2 The commonest edits (KLM)

Keystroke-Level Model (Card, Moran & Newell 1980): M 1.35 s, P 1.1 s, click or tap BB 0.2 s, K 0.2 s; a scroll counted as one P (a wheel or a flick). From the opened panel:

| Edit | Before: actions, scrolls | Before: KLM | After: actions, scrolls | After: KLM |
|---|---|---|---|---|
| Change a pipe size (pump → Piping → size) | 2 + 1 scroll (desktop y 947 > 686), 2 + 2 scrolls (phone y 1243 > 638) | 7.7 s / 8.8 s | 2, no scroll at either size unsolved (e2e); solved, 1 scroll on a phone | 6.6 s / 7.7 s |
| Switch a valve's status | 1 (desktop), 1 + 1 scroll (phone y 696 > 638) | 3.95 s / 5.05 s | 1, no scroll (e2e) | 3.95 s |
| Edit a pump curve point | 1 + 1 scroll (desktop y 969 > 686), 1 + 2 scrolls (phone y 1305 > 638) | 5.3 s / 6.4 s | 1 + 1 scroll on a phone (the curve table follows the core fields), none on desktop | 4.2 s / 5.3 s |
| Add a component after this one | 3 (Add after, kind, Add) | 7.5 s | 3, the kind first in the dialog; dialog 602 → 490 px (desktop) | 7.5 s |

The pipe size and the valve status are 2 and 1 actions, each now held by an e2e test (`build-density.e2e.ts`). A pump curve point stays 1 action plus a scroll on a phone, and adding a component stays 3 (choosing the kind is the decision; §12).

### 3.3 Content inventory (from `openapi.json` and the examples)

74 field rows over 17 schemas; frequencies counted on the three examples (84 components, 186 ports, 98 pipes, 54 fittings, 2 pump curves, 1 scenario with 19 overrides). The full table, with each field's default, governing decision and reason, is [`build-density/findings-ia.md`](build-density/findings-ia.md). What decided the tiers:

- **Status** is the field cases change most: 18 of the scenario's 19 overrides.
- **Elevation is set, not defaulted**: non-zero on 79 of 84 components (inline valves 27/28, tees 24/24, equipment 13/13). The owner's direction ("core visible") and the data agree that it is core; the data disagree with its place (first): it moved last.
- **Defaults nobody changes**: surface pressure (0 of 12 reservoirs), tee loss model (0/24), cracking pressure (0/6), port elevation (0/186), pipe inner diameter and roughness overrides (0/98), fitting K entered (0/54). These went to More.
- **Fields no example sets** (reference node, plug, assigned flow, wye, orifice, relief valve): tiered from the PRD's user stories and the decisions.

### 3.4 What nobody had noticed (sibling inconsistencies)

From the IA card sort and the red team: "K" is a loss coefficient on valves and fittings but the discharge coefficient on the relief valve; `dischargeCoefficient` has two labels (orifice, relief valve); the source pickers word "default" five ways; of three pressure-difference fields only the relief set pressure's label says "difference"; `angle` is a wye's branch angle and a fitting's bend; optional content used three patterns (two `<details>` styles and Add/Remove buttons); groups were wrapped four ways (fieldset, section with aria-label, h3, h4); six types ended with an always-visible model paragraph and six had none; elevation came first everywhere; `Fitting.description` is in the schema but no form edits it; port elevation is editable only on reservoirs though the equipment help asks for real port elevations.

### 3.5 Where the data disagreed with the direction

- **The problem was weak hierarchy as much as density.** Inputs were only 18–32 % of the first screen; static prose and whitespace together were 35–50 %. Hiding static help until focus and putting labels beside controls did more than smaller controls (§11 table: forms 25–55 % shorter, inputs 30–50 % of the first screen).
- **"Core" includes values that are almost always defaults**, which the owner's "most core info stays visible" would have kept: surface pressure, the tee loss model, cracking pressure. The data put them in More, with their default named in More's summary, so the D10 "default" stays readable without opening it (GOALS §4.2).
- **Chrome was not mainly the toolbars**: on short forms the disclosure rows themselves (More, Ports, About) were chrome on the first screen; they were merged into one (§5 D11).

## 4. The disciplines' contributions (findings files in `build-density/`)

| Discipline | Main findings adopted | Adopted differently or not |
|---|---|---|
| [Control-room (dark cockpit)](build-density/findings-cockpit.md) | Normal state quiet: static help hidden until focus; one-line scenario banner (was 106 / 198 px); a compact result strip; exceptions (warnings, scenario changes, unconnected ports) open their disclosure | "Open only for exceptions, not set values": More opens for set values too, since a value in More is a departure from a cited default (D5); severity shapes for flags and pinned strip: §12 |
| [Property inspector (CAD)](build-density/findings-inspector.md) | Label/value rows, units inside the field box, one "More · n set" disclosure, compact pipe overrides kept and counted; measured savings 60–70 % per form | Compact tables for ports and fittings: §12 |
| [Typography and grid](build-density/findings-typography.md) | 4 px grid; one Build control height token; 16 px input text with tabular figures (iOS zoom); label column 8–10 rem; stack below a 21 rem container, two columns of rows from 44 rem | Its 40 px on every pointer: 36 px for fine pointers to meet the chrome budget (D3) |
| [Information architecture](build-density/findings-ia.md) | The five facets and their order; every tier; elevation core and last; library references are options of their field, not a facet; the inconsistencies of §3.4 | — |
| [Software architecture](build-density/findings-architecture.md) | Registry keyed by the override/goal paths; read existence, bounds, defaults, enums and allow-list from the schema; generic number and choice fields; per-path snippet escape hatch; choices from the schema's `enum`, never copied | Unifying the five label tables (`fieldLabelFor`, `labels.fieldLabel`, three unit switches) with the registry: §12 |
| [Accessibility (WCAG 2.2 AA)](build-density/findings-a11y.md) | axe-core added to the e2e suite (it was not there); native `<summary>` disclosures; help hidden visually but always in `aria-describedby`; breadcrumb focus scrolled into view (2.4.11 failure fixed); pointer-based control height | 400 % zoom (320×256) leaves no room for the form under the fixed bars (1.4.10): §12 |
| [Red team](build-density/findings-redteam-1.md) | Notes (D15 "sets its own value", live velocity, shared curve, "default" texts) split from static help; More's summary says "(default)"; pressures must state gauge; ports never counted as "set"; scroll to the top on Next | §10 lists what remains |

## 5. Decisions (each a reversible web default under D14)

| # | Decision | Reason | Goal served |
|---|---|---|---|
| D1 | A **field registry** (`utils/field-registry.ts`) holds, per schema and field path, the facet, tier, order, label, help and (for plain fields) how it is drawn; everything else is read from `openapi.json` | One place to add a field; no copied rule (D10) | Longevity, usability |
| D2 | A **Vitest guard** fails on a schema field reachable from Build with no entry, an entry the schema lacks, or a pressure that does not state gauge | Density cannot regress silently; D4 cannot be forgotten | Correctness, traceability |
| D3 | **One Build control height**: 36 px for fine pointers, 40 px for touch (`.dense` on the Build pane, `--ctl-h`); the header, Results and other dialogs keep 44 px | 1.5–1.7 × WCAG 2.5.8's 24 px; 36 px was needed for the 15 % chrome budget; existing e2e assertions of 44 px targets outside Build stay true | Usability, accessibility |
| D4 | **Label/value rows**: label in a fixed column (8–10 rem), control beside it, notes under the control; stacked below a 21 rem container (320 px reflow); two columns of rows from 44 rem | −40 % height per field (typography: 80 → 48 px) with no hidden content | Usability |
| D5 | **Help shown on focus** (`help` prop), always in `aria-describedby`; anything about the current value (`hint`: live velocity, shared curve, a "default", warnings, errors, scenario notes) always shown | Static prose was 7–31 % of the pane; the red team showed notes and help must be told apart, not by a class | Usability, traceability |
| D6 | **Five facets**, in this order on every type: Operation, Rating, Size and position, Fittings, Identification; each core facet a titled section | Card sort: holds across all 17 schemas; Operation first since cases change it most | Usability, breadth |
| D7 | **Tiers** as in `field-registry.ts` (core: defining inputs; More: defaults nobody changes in the examples) — surface pressure, tee loss model, orifice C and taps, cracking pressure, pipe overrides, manufacturer data and efficiency curve go to More | Data in §3.3; when close, the tier that hides less (resistance, elevation, NPSHr, wye angle core) | Usability, traceability |
| D8 | **More** is one disclosure per form whose summary names every field it holds, "(default)" for each at its default, and a count ("1 set", "1 changed in this case", "1 to finish"); it opens itself while it holds a set value, a scenario change or base-case note (D15), a pending draft or a port needing attention, and never closes itself | Nothing the user set, and no default, is unknown while it is closed (the auditor's test) | Traceability, usability |
| D9 | **Elevation last** in Size and position, core on every type | 79/84 components set it; it is not what defines a type | Usability |
| D10 | **Plain fields drawn by the registry** (status, valve type, liquid level, surface pressure, reference pressure, wye angle, cracking pressure, elevation); custom fields by the type's form through one `field` snippet; the reservoir's and reference node's forms removed | A plain new field is one entry | Longevity |
| D11 | **Ports and "About this model" inside More**, not in their own disclosures; the type's model paragraph is its "about" | Three disclosure rows were chrome on every short form | Usability |
| D12 | **Build's top bar** holds the path, Previous, Next and Jump to on wide screens (≥ 1024 px); phones keep Previous/Next at the bottom, under the thumb | One chrome row instead of two on desktop; one-hand use on phones | Usability |
| D13 | **Kind · id on the name's row**; the **actions beside the Properties/Piping tabs** (phones: one row of icon + label above them, 40 px, was 56 px) | Two rows saved without hiding an action | Usability |
| D14 | **Result strip** as label/value pairs that wrap (was a grid of stacked label and value) | 97 → 56 px for a pump on desktop; same cells, same notes and flags | Usability |
| D15 | **Scenario banner** one line ("Scenario: name. Changes here are this scenario's…"), Switch to base case as a quiet button | Was 106 / 198 px on every component in a scenario | Usability |
| D16 | **Pump curve editor after the core fields** (the select stays in Rating); manufacturer and model join the manufacturer-data disclosure | The table pushed Elevation off a phone's first screen | Usability |
| D17 | **Add component dialog**: the kind first, then where (one row of options) | The kind is the decision; dialog 602 → 490 px | Usability |
| D18 | **Piping**: one row of port buttons, one row of connection actions (short visible labels on phones, full accessible names), the connection heading inline with its sentence, the pipe overrides counted like More | A pipe size reachable without scrolling on a phone | Usability |
| D19 | A Build panel **opens at its top** on Next, Previous or Jump to | The red team's valve opened scrolled to its ports | Usability |
| D20 | **axe-core in the e2e suite** (`@axe-core/playwright` 4.10.2, MPL-2.0, AGPL-3.0-compatible, a dev dependency, not bundled) | The suite had no axe scan; the owner's target needs one | Accessibility |

## 6. The registry and the density tokens

**Registry** (`apps/web/src/lib/utils/field-registry.ts`): `FIELD_REGISTRY[schema][path] = { facet, tier, label, help?, input?, edit?, whole?, isSet? }`. Paths are the scenario allow-list's (`control.setpoint`, `capacity.letter`, `rating.value`); `model-rules.ts schemaFields(schema)` walks the schema (refs, `anyOf`, `oneOf`, skipping `const` discriminators) to list them, and `schemaChoices` gives a choice's values. `FieldSections.svelte` lays a component out from it; `RegistryField.svelte` draws plain fields. The schemas covered: every member of `Project.components`, `Port`, `PipeDefinition`, `PumpCurve`. [`../adding-a-field.md`](../adding-a-field.md) is the one-page note for the next slice.

**Tokens** (`apps/web/src/routes/layout.css`): `--ctl-h` (44 px default; `.dense` 40 px, 36 px on fine pointers), exposed to Tailwind as `min-h-ctl`/`w-ctl` through `@theme inline` (so the value is read where it applies); `--spacing-label` 10 rem; `.fields` (grid, 8 px row gap, 24 px column gap), `.field` (label column `minmax(8rem, 10rem)`, 12 px gap, notes in column 2), `.fields-pairs` (two columns of rows from a 44 rem container), `.wide`, `.help`, `.more-summary`, `.btn-tight`; inputs `text-base tabular-nums`.

## 7. Header and toolbars

- **Build top bar** (D12): path · Previous · Next · Jump to, 37 px on desktop (was 53 + a 60 px bottom bar).
- **Tabs and actions** (D13): one 37 px row on desktop; on phones one 40 px row of actions above the tabs.
- **The workspace header** keeps its 44 px controls (held by existing e2e tests on both projects) with 2 px around them: 49 px on desktop (was 53), two rows on a phone (95 px, was 101). One row on a phone would need an overflow menu for Library, Share and Settings, which would hide core items; decided against (§11 item 12).
- **The scenario bar** takes the Build pane's compact height (`dense`): 37 px with a mouse, 41 px on touch (was 53).
- **400 % zoom**: below a 20 rem viewport height the workspace scrolls as one page (§11 item 14).

## 8. Verification

- `field-registry.test.ts` (the guard, 39 tests), the existing Vitest suite, `svelte-check`, ESLint and Prettier.
- `tests/build-density.e2e.ts`, at both projects: core fields on a phone's first screen (every type, unsolved; and the solved pump example), chrome ≤ 15 % at 1280×800 (every type and the solved example), a pipe size 2 actions and a valve status 1 action from the panel with no scroll, axe-core (WCAG 2.0/2.1/2.2 A and AA) on four forms with their disclosures open and on Piping.
- The whole e2e suite at both sizes; before/after screenshots and the measurement tables in `build-density/`.

## 9. Files

`apps/web/src/lib/utils/{field-registry.ts,field-registry.test.ts,model-rules.ts}`; `src/lib/components/panel/{FieldSections,RegistryField}.svelte` (new), `ComponentPanel`, `ComponentActions`, `PanelNavigator`, `Breadcrumb`, `ResultStrip`, `ScenarioBanner`, `PortsEditor`, `ConnectionPanel`, `PipeSegmentForm`, `AddComponentDialog`, `ReliefValveFields`, `EquipmentRatingFields`, `OrificeFields`, `ResistanceField`, every `forms/*Form.svelte` (`ReservoirForm` and `ReferenceNodeForm` removed), `PumpCurveEditor`; `ui/{NumberField,SelectField,TextField,Dialog}.svelte`; `workspace/Workspace.svelte`; `routes/layout.css`; `tests/build-density.e2e.ts`; `package.json` (`@axe-core/playwright`).

## 10. The red team's unresolved objections

The red team ran twice: on the app before the build ([pass 1](build-density/findings-redteam-1.md)) and on the built app ([pass 2](build-density/findings-redteam-2.md)). Pass 2 measured the field engineer's task (change the discharge pipe's size, re-solve, close the valve, re-solve) at **10 taps and 0 scrolls** (pass 1: 10 taps, 2 scrolls), and confirmed, with no field focused, the D15 notes in both cases, More opening for a scenario change and a base-case note, "(default)" in More's summary, "Base: 0 kPa(g)", and help in `aria-describedby`. Still standing:

1. **A phone's main loop stays top-heavy** (field engineer): Solve, Undo and Redo are in the header, and Solve switches to Results, so edit → solve → edit is a tap at the top, then the Build tab. Not changed: Solve-to-Results is the decided phone flow (ui-ux-refinement.md §1).
2. ~~Native selects need two taps for a two-value status~~ **resolved** for two-value statuses (§11 item 22); three-value statuses keep the select.
3. ~~A solved connection on a phone~~ **resolved** (§11 item 19), and a solved pump's first curve point (§11 item 23).
4. **The guard is blind under `whole`**: a valve's resistance editor owns its sub-fields (`resistance.kind`, `value`, `id`). Every other union (capacity, rating, control) registers each sub-field.
5. ~~Five label tables~~ **resolved** (§11 item 13): scenario notes, goal seek and the export read labels and units from the registry, and the guard covers the allow-lists. Still by hand: the export's pump table lists its input columns, and `labels.fieldLabel` (the order rule's message, pump fields only).
6. ~~400 % zoom~~ **resolved** (§11 item 14).
7. ~~"Base: Default" without the basis~~ **resolved** in Build (§11 item 16); the shared value text still says "Default", as the export's committed fixture does.
8. ~~Low: round-off outflow; the name note's gutter~~ **resolved** (§11 item 26; the note keeps the form's gutter).
9. ~~Adding a component stays 3 actions~~ **resolved** (§11 item 21).

## 11. As built

Measured with the same script on the built app (`measure.cjs`, before at `5693197`, after on this branch), unsolved unless marked; the "every kind" project's free ports are unplugged there, so the tee and relief valve open More for their unconnected ports (an exception, by design).

| Form | Height desktop | Height phone | Inputs, first screen, desktop | phone | Hint prose, first screen, desktop | phone |
|---|---|---|---|---|---|---|
| Reservoir | 881 → 747 | 1113 → 699 | 23.6 → 27.6 % | 25.2 → 34.3 % | 15.1 → 8.2 % | 11.2 → 11.7 % |
| Pump | 1570 → 826 | 1874 → 1110 | 23.8 → 43.4 % | 28.0 → 34.3 % | 13.0 → 6.8 % | 9.0 → 11.0 % |
| Pump, solved | 2442 → 1454 | 2818 → 1736 | 22.1 → 48.1 % | 18.9 → 36.9 % | 8.4 → 2.3 % | 4.7 → 0.7 % |
| Gate valve | 1107 → 747 | 1203 → 699 | 28.8 → 29.6 % | 31.5 → 34.3 % | 7.1 → 13.7 % | 4.7 → 5.9 % |
| Check valve | 1207 → 747 | 1387 → 699 | 23.6 → 33.7 % | 31.5 → 34.3 % | 16.5 → 11.0 % | 5.9 → 2.6 % |
| Equipment | 1539 → 747 | 1735 → 705 | 23.6 → 33.7 % | 25.2 → 34.3 % | 18.5 → 11.0 % | 13.3 → 4.1 % |
| Orifice | 1335 → 747 | 1515 → 699 | 23.6 → 28.9 % | 25.2 → 28.6 % | 20.1 → 13.3 % | 13.9 → 8.4 % |
| Relief valve | 1507 → 1152 | 1831 → 1469 | 23.6 → 33.7 % | 25.2 → 34.3 % | 16.5 → 15.0 % | 16.6 → 11.2 % |
| Piping, solved | 1601 → 1014 | 1993 → 1438 | 5.9 → 16.9 % | 6.3 → 5.7 % | 7.0 → 21.2 % | 9.9 → 7.3 % |

(747 and 699 px are the pane's own height: those forms now fit without scrolling. A form's "hint prose" can rise where its More opened with the ports list and the model text.)

**Budgets** (`tests/build-density.e2e.ts`, both projects):
- Core fields on a phone's first screen: **met** for all 19 types unsolved and the solved pump example (it failed for the pump's elevation until the curve editor moved after the core fields, D16).
- Chrome at 1280×800: **14.6 %** for every type in its normal state (9.8 % for the solved pump), under 15 %; it was 23.6–29.5 %. It met the budget only once the control height was really applied (below) and the More/Ports/About rows were one (D11). The equipment item's two density buttons enter the density, so they count as inputs (`data-input`), the spec's one stated rule beyond the element type.
- Pipe size 2 actions and valve status 1 action from the panel, no scroll: **met** at both sizes, unsolved and (after item 19) solved. The first curve point on a solved pump needs one scroll on a phone.
- axe-core: **0 violations** on four forms with their disclosures open and on Piping, at both sizes.
- A new field is one entry and its label: **met for plain fields** (`adding-a-field.md`); a field with its own editor adds its branch in the form's snippet; a scenario-changeable field still needs its label in `fieldLabelFor` (§10 item 5).

**Departures from §5:**
1. **The compact height first did nothing.** Tailwind's `@theme` resolved `--spacing-ctl: var(--ctl-h)` once on `:root`, so `.dense` changed nothing until it became `@theme inline`; found by the chrome budget, which kept failing at 44 px controls.
2. **Help floats instead of pushing.** Shown in the flow, it moved the Add button of a dialog when the field lost focus, and four equipment e2e flows that hold "the first click adds it" failed; it is now an overlay under the field with `pointer-events: none`, so nothing moves (a11y findings asked for exactly this).
3. **Ports and About went into More** (D11) after measuring three disclosure rows as chrome on short forms; the Ports region keeps its name ("Ports") for the tests and screen readers.
4. **The Breadcrumb's focus** is scrolled into view (`focusin`), the a11y review's 2.4.11 failure.
5. **One e2e locator re-scoped**: `pump-system.e2e.ts` reads the Pump curve select from the Build panel instead of the "Pump curve" region, since the select now sits in Rating (D16); the assertion (its value is C1) is unchanged.
6. **The density spec's fixture plugs every free port**, so its panels show their normal state; unconnected ports open More by design (§5 D8), and their chrome is the exception being raised.
7. **Not built in the timebox** (roadmap §4): the workspace header and scenario bar, compact port and fitting tables, one label table.
8. **The scenario banner is one line on phones too** ([second red-team pass](build-density/findings-redteam-2.md)): at 390 px it wrapped to ~160 px and pushed a valve's second scenario change under the bottom bar; its explanation is now for screen readers only below 640 px.
9. **A valve's default resistance is spelled out under its select** ("Default: Crane TP-410 K, full bore and fully open, at the connected size."), since a phone's native select cut it to "…full bore and f" (D10).
10. **The action labels wrap inside their buttons below 360 px** (they ran past them at 320 px).
11. **The density fixture gives control valves a setpoint**, as a user would: a setpoint of 0 raises a warning (an exception), and with the default-resistance line it pushed a PRV's and a PSV's elevation off a phone's first screen, which the spec caught.

**Second session (2026-10-31): the remaining objectives.**

12. **Header and scenario bar** (§7): the header 2 px tighter on each side of its 44 px controls; the scenario bar at the compact Build height. An overflow menu for the phone header was decided against: it would hide Library, Share and Settings, and "hide less" breaks the tie.
13. **One label and unit table.** `fieldLabelFor` reads the registry (a label may be a function of the element, given none when the element is gone); the scenario value text, the export's change unit and goal seek's variable unit read a number's `unit` from the registry, keeping only the cases with their own wording (an assigned flow's direction, a resistance's coefficient, a whole rating or capacity, a default's text). The guard fails when a field on the scenario or goal-seek allow-list has no entry, or a number goal seek varies has no unit. A new scenario-changeable plain field is now one entry.
14. **400 % zoom** (WCAG 1.4.10): below a 20 rem viewport height (`short:` variant) the workspace scrolls as one page; the form is reached by scrolling, never sideways (an e2e test at 320×256).
15. **Severity by shape**: an invalid flag and a failed solve's tab marker are an octagon, a warning a triangle (cockpit findings §3).
16. **The base case's default named** where a scenario replaced a valve's default resistance ("The base case's default: Crane TP-410 K, …"), beside the change note's "Base: Default".
17. **Ports and fittings as rows, not cards**: a port's "Edit piping" on its name row; a fitting's fields as label/value rows (FittingsEditor), its source kept.
18. **Phone Piping**: the component's own actions stay with Properties on a phone (Piping has the connection's); **the pump curve's name follows its points** (identification last).
19. **The connection's actions follow its pipes**, and the "Pipes" heading is for screen readers only when there is one pipe (its card says "Pipe 1"): solved, on a phone, with both result strips shown, the pipe size is now on the first screen (y 760 of 656 before this item; an e2e test holds it). A pump curve's first point is still one scroll below on a phone (y 729 of 656; was 1305 of 638 before the build).
20. **Measured after the second session**: header 49 px desktop / 95 px phone (was 53 / 101), scenario bar 41 / 45 px (was 53 / 53).

**Third session (2026-10-31): the open items closed.**

21. **Adding a component in 2 actions**: the Add dialog leads with "Add now" buttons (up to four kinds this placement takes and that need no value first: the kinds added last in this page, then common ones); a press adds that kind (Add after, then the kind). Kinds that ask for a value first stay in the list, where their fields are. The list and Add are unchanged, so the e2e suite's dialog flows still hold.
22. **One-tap status**: a two-value choice drawn by the registry (a pump's and an isolation valve's status) is a pair of segments (`SegmentedField`, a radio group) with the select's scenario behaviour: locked read-only with "Same in every scenario", "Changed" with the base value and Reset, the base case's "sets its own value". Three-value statuses keep the select (their labels do not fit three segments on a phone). Five places in four tests that drove those two statuses as selects now drive the radios (`Scenarios.svelte.test.ts`, `scenarios.e2e.ts` twice, `relief.e2e.ts`'s blocked discharge, the density spec), each assertion kept (the value, the description, Reset, editable in a scenario). Each radio covers its whole segment (a transparent full-size input), so the segment is its target.
23. **A solved pump's first curve point on a phone's first screen** (y 788 of 795; was 1305 of 638 before the build): the result strip's label/value pairs share its title's line (two lines on a phone, was three), the gaps between a form's sections are 8 px, the Control note's empty live region is out of the grid, and the curve table's rows are 1 px apart. An e2e test holds it.
24. **Every port's elevation is editable** (it was on reservoirs only, while the equipment help asks for ports at their real elevations); the ports are in More, so it costs nothing in the normal state.
25. **A fitting's description** is shown and edited (last in its row, identification), so one a link holds is never invisible; the `Fitting` schema joins the registry and its guard.
26. **A boundary's round-off outflow** (−8.9×10⁻¹³ L/s on the bypassed basin) shows as "≈ 0" with the exact value in its note, by the solve's own continuity test (API `solver/gga.py` CONTINUITY_RTOL × the largest boundary flow + CONTINUITY_ATOL), as heads already do with HEAD_NOISE; the Boundaries table and the strip read the same cell.
27. **Decided, not changed** (the §3.4 inconsistencies): "K" is the loss coefficient (Crane) on valves and fittings and ASME's rated coefficient of discharge on a relief valve, each its source's symbol, and the relief label spells it out ("Rated coefficient of discharge (K)"); the orifice's "Discharge coefficient" (ISO 5167-2's C) and the relief valve's are different quantities under one field name, each labelled by its standard; the five wordings of "default" each name their basis (D10) — unifying them would change cited text in scenario notes and the export's committed fixture for no gain in correctness; pressure differences carry no "(g)" (D4), which is what marks them, and only the relief set pressure says "(difference)" because it is compared with gauge setpoints elsewhere; `angle` is scoped by its row (a wye's "Branch angle", a fitting's "Angle").
28a. **The density fixture's pump has the pump example's curve**: without one, its "needs a curve" box (an exception, with its buttons) pushed the pump's chrome to 19.3 % once the form's gaps tightened; normal state, as for the plugged ports and the setpoints (items 6, 11).
28. **The export's pump table** lists solved results from the API response (D17), not Build inputs; a new Build input reaching the workbook is a results-contract change for that slice, not a density one. Decided as by design; `adding-a-field.md` says so.

Screenshots: `build-density/before-*.png` and `after-*.png` (the solved pump at 1280×800 and 390×844, the solved gate valve and the relief valve on a phone, Piping on both, the Add dialog, the equipment form; the after set as of the second session), and `after-zoom-320x256.png` (400 % zoom).

## 12. Later

- The strip kept in view when it gains a flag after a solve (cockpit §4).
- Segments for three-value choices where their labels fit (a check valve's status on desktop).
- The export's input columns from the registry, if the owner wants Build inputs in the results workbook (D17).

## 13. The owner's four requests (2026-10-31)

Quoted in substance: (1) keep the footer's links on one line, after the copyright where they fit, else all together on the next line, compact; (2) condense Project settings, with reference information one step away, as the fluid properties are in Results; (3) make US units the default, and make the units choice easy to find in Settings; (4) move the case bar's functions under the Scenarios menu: the bar offers little and uses screen.

1. **Footer** (`SiteFooter.svelte`): the five links are one unbreakable group after the copyright (1.5 spacing, tight tracking): at 1280×800 they follow it on its line (the Results pane is 480 px; the line needs 470 px); at 390 and 320 px they are all on the next line together. Below 360 px, if a font made them wider than the line, they may wrap rather than overflow.
2. **Project settings** (`SettingsDialog.svelte`, `FluidSettings.svelte`), in this order: **Units** first (a two-segment SI / US customary choice and one line on what units do; the nine per-quantity units behind "Per quantity: ft, in, psi, …", open when mixed), **Fluid** (its fields as rows; the calculated properties behind "Calculated properties: 62.29 lb/ft³, 1.002 cP", their values in the summary and their sources inside, as Results shows the fluid; the overrides as before), **Site** (two rows, their explanations on focus), **Project** (the description), **Solver** (friction, and "Convergence (advanced): 100 iterations, tolerance 1e-9"), **Design checks** last behind "Design checks: opt-in, all off" (open while any is on). Section titles are small caps; controls take the compact Build height; the scenario note is one line.
3. **US customary by default** (`factory.ts DEFAULT_UNITS`): a new project starts in ft, in, psi, gpm, °F, lb/ft³, cP. Unchanged, on purpose: the three examples stay in SI, the units they were published with, so their links and numbers stay the same (GOALS §4.3); a link without units still fills the schema's defaults (the API model's: SI), so an old link shows what it did; the model, the API and the solver stay SI (D4). Tests that type SI values open an SI project; `home.e2e.ts` checks that New project starts in US units and that SI is the first choice in Settings, one tap away.
4. **The Scenarios menu replaces the case bar** (`CaseMenu.svelte`, from `ScenarioBar.svelte`): once the project has scenarios, the header's Scenarios button opens a small menu under it with the Case select, where edits go, Solve all, its progress line and Manage scenarios…; with none, the button opens the manager as before. Choosing a case closes the menu; a Solve all that runs to its end closes it, a cancelled or stopped one keeps it open with its line saying so; Escape or a press outside closes it. The button is teal while a scenario is shown, with "Case shown: …" as its tooltip, and a spinner while Solve all runs; the header says the run's progress to screen readers while the menu is closed. The case shown is still named where it matters: the Build pane's one-line note in a scenario, the Results pane, Solve's name. One row of every screen (41–45 px) is given back. D15's web defaults and TSD §3.1 are updated.

## 14. Results tables as lists on phones (owner, 2026-10-31)

Quoted in substance: the results tables are good on desktop, but on mobile a list like the Summary is preferred for every other view, still sortable by a chosen field.

- **Below 640 px every results table reads as a list** (`ResultsTable.svelte`, all twelve views): each row is a block headed by the element's name (the same button to its results and trace), its values as label and value pairs that wrap ("Flow (L/s) 18.98 · Velocity (m/s) 3.981 · …", the label from the column, the value as the table shows it), its flags and its "Pipes and fittings" under them. Nothing scrolls sideways; the list flows with the pane instead of scrolling in its own box. From 640 px the table is as it was.
- **Sorting on a phone**: a "Sort by" field lists every sortable column (with its unit) and "Table order", and a direction button (Ascending: lowest first / Descending: highest first) beside it; it is the table's one sort state (a field chosen sorts ascending first, as a heading does), so the Summary's "Nodes, lowest first" links and a heading's sort show in it, and Flagged only works as before.
- **Semantics kept**: the table carries explicit roles (table, rowgroup, row, columnheader, rowheader, cell), since a CSS layout that unmakes a table can unmake its semantics in some browsers; the column headings stay for screen readers (visually hidden), with `aria-sort`. The e2e suite's table reads work unchanged on phones; the one flow that clicked a heading on a phone uses "Sort by" there (`summary-tables.e2e.ts`), and a component test covers the field and its direction.

## 15. The Results header, and fields to show (owner, 2026-10-31)

Quoted in substance, from a phone screenshot with the Results pane's top circled: this area is unrefined and needs improvement; and make the fields shown in the results tables and lists selectable from a drop-down, for customization.

- **One compact header row** (`ResultsPanel.svelte`): the status with a mark beside it (✓ converged, ⚠ out of date, ⬣ did not converge or failed, a spinner while solving; the words unchanged, "Last solve of Base case: converged"), then Export and Goal seek, icon-only in a narrow pane (Goal seek below 26 rem). The "Results" title is for screen readers on phones, where the view tab already says Results; the case chip is gone, since the status and the case tabs name the case. The case tabs are 36 px (were 44). On a 412 px phone the header went from three lines (≈ 105 px) to one (44 px).
- **No base-case line**: "Base case: the network as built, without scenario changes. Compare cases" repeated the case tabs right above it; a scenario keeps its card (its changes, linked to their traces). The component test of that line's button now checks the tabs instead.
- **Fields** (`ResultsTable.svelte`, every results view): a "Fields" button beside Sort by opens a menu of the table's columns, each a checkbox with its unit; unchecked columns leave the table and the phone's list (and Sort by), the element's name always stays, "Fields (8 of 12)" says a choice is in force, "Show all" forgets it. Remembered in this browser per table (`localStorage`, a per-viewer convenience: never project data, never in the link; in try/catch, so a private window just forgets). A sort on a column hidden since returns to the table's order.
- **A phone's row leaves out "—"** (a value the element has none of, such as an isolation valve's setpoint): the screenshot's rows carried four of them each. They are out of sight only (screen-reader-only), so each row keeps its cells, in order, for screen readers and for the table reads of the e2e suite.
- **Tests**: a component test of the Fields menu (hide, remembered, Show all); `export.e2e.ts`'s phone check that the title keeps its width beside Export now checks that the status line stays on one line (the title is screen-reader-only on phones).
