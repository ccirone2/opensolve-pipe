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
| Change a pipe size (pump → Piping → size) | 2 + 1 scroll (desktop y 947 > 686), 2 + 2 scrolls (phone y 1243 > 638) | 7.7 s / 8.8 s | 2, no scroll at either size (e2e) | 6.6 s |
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
- **The workspace header and the scenario bar are unchanged** (53 px desktop, 101 px phone; scenario bar 53 px): the header's buttons are held at 44 px by existing e2e tests on both projects, and two 44 px rows are what a phone needs for eight header controls without an overflow menu, which would hide core items (Undo, Share). §12 has the measured options.

## 8. Verification

- `field-registry.test.ts` (the guard, 39 tests), the existing Vitest suite, `svelte-check`, ESLint and Prettier.
- `tests/build-density.e2e.ts`, at both projects: core fields on a phone's first screen (every type, unsolved; and the solved pump example), chrome ≤ 15 % at 1280×800 (every type and the solved example), a pipe size 2 actions and a valve status 1 action from the panel with no scroll, axe-core (WCAG 2.0/2.1/2.2 A and AA) on four forms with their disclosures open and on Piping.
- The whole e2e suite at both sizes; before/after screenshots and the measurement tables in `build-density/`.

## 9. Files

`apps/web/src/lib/utils/{field-registry.ts,field-registry.test.ts,model-rules.ts}`; `src/lib/components/panel/{FieldSections,RegistryField}.svelte` (new), `ComponentPanel`, `ComponentActions`, `PanelNavigator`, `Breadcrumb`, `ResultStrip`, `ScenarioBanner`, `PortsEditor`, `ConnectionPanel`, `PipeSegmentForm`, `AddComponentDialog`, `ReliefValveFields`, `EquipmentRatingFields`, `OrificeFields`, `ResistanceField`, every `forms/*Form.svelte` (`ReservoirForm` and `ReferenceNodeForm` removed), `PumpCurveEditor`; `ui/{NumberField,SelectField,TextField,Dialog}.svelte`; `workspace/Workspace.svelte`; `routes/layout.css`; `tests/build-density.e2e.ts`; `package.json` (`@axe-core/playwright`).

## 10. The red team's unresolved objections

1. **A phone's main loop stays top-heavy** (field engineer): Solve, Undo and Redo are in the header, and Solve switches to Results, so edit → solve → edit is a tap at the top, then the Build tab. Not changed: Solve-to-Results is the decided phone flow (ui-ux-refinement.md §1).
2. **Native selects need two taps** for a two-value status. Not changed: a segmented control for 2–3 values is a candidate (§12).
3. **A solved connection on a phone**: with the connection's result strip shown, the pipe size sits below the first screen (one scroll); the budget test is unsolved.
4. **The guard is blind under `whole`**: a valve's resistance editor owns its sub-fields (`resistance.kind`, `value`, `id`). Every other union (capacity, rating, control) registers each sub-field.
5. **Five label tables** remain (`scenarios.ts fieldLabelFor`, `labels.fieldLabel`, the unit switches of goal seek, scenarios and export): a new scenario-changeable field still needs its label there, and a missing unit there shows silently as dimensionless (§12).
6. **400 % zoom** (320×256) leaves no room for the form under the fixed header and tabs (WCAG 1.4.10), as before this build.

## 11. As built

<!-- AS-BUILT -->

## 12. Later

- Unify the label tables with the registry: `fieldLabelFor` reads the registry (keeping its 9 callers), `labels.fieldLabel` becomes `inSentence(fieldLabelFor(…))`, and the three unit switches read a `unit` from the entry, with the guard extended to the allow-list's keys (architecture findings §1).
- Compact tables for ports and fittings (inspector: ports 484 → 136 px, fittings −70 %), and a segmented control for 2–3-value choices.
- Severity by shape as well as colour for flags in the strip, and the strip kept in view when it gains a flag after a solve (cockpit §3–4).
- The workspace header on phones in one 44 px row (it would need an overflow menu for Library, Share and Settings: an owner's call, since it hides core items) and a 40 px scenario bar.
- A layout for 400 % zoom (bars that scroll with the page below a 30 rem height).
- Fix the inconsistencies of §3.4 one by one (labels for K, "difference", "default").
