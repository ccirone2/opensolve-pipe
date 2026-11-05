# The Pumps tab below the pump chart: sections, one way through, every feature kept

**Status: Proposed, for the owner (2026-11-05). Nothing is built.** Web only, on `web/pumps-layout`: no API, model or solver change, `METHOD_VERSION` stays 1.6.0, `schemaVersion` stays 1, nothing new in the link, no new dependency. Every placement here is a designers' web default, reversible under D14, except the four questions in §12, which are the owner's. Measured and read against main's content at `3da7bae`; the branch adds only the re-tick fix of `web/cases-on-chart-retick` (`untickedAfter`), which changes no layout. Follows [`ui-ux-refinement.md`](ui-ux-refinement.md) and [`build-density.md`](build-density.md): measure the running app, act, then hold the result in a test.

## 1. Scope

**The owner's request (2026-11-05), in the owner's words:** "i love all the features in Results under the Pumps tab, but everything from below the pump chart and down is very unrefined from a UI/UX perspective. it just looks patched together and needs to be structured in a way that the user can navigate and manipulate the features without getting confused by poor, unstructured formatting."

Read as: **keep every feature; restructure how they are presented, navigated and manipulated.** In scope is everything from the pump chart's canvas down, in `PumpsView.svelte`, `PumpChart.svelte`, `PumpGroupChart.svelte` and `PumpLineupsBlock.svelte` (`apps/web/src/lib/components/results/`): the chips, the readout, the notes, the system curve's states, the other cases, the data table and the image of the pump chart; and the whole Pumps together card, with its members, group chart, notes, tables, Read along the curves, Add cases, the other cases' station duties, the curve family, Running combinations and the extremes. Out of scope: the Results per pump table above (it gains only a visually hidden heading), what the canvases draw (the label collisions are the owner's open items 107 and 108), and the server's words.

**Already decided, not re-opened** (§8 lists each): GOALS §3, §4.2, §4.5, §4.6 and §4.7; D3, D10, D13, D15, D17, D19, D21 and D24 with their owner's answers; the pump chart's owner decision on the best efficiency point; the owner's table rules of 2026-10-31 (`build-density.md` §14 to §18).

**Aim.** The method of the precedents, progressive disclosure: the answer and the next action shown, the depth (traces, methods, tables) one step away, never removed. Concretely:

1. one section anatomy, repeated for both charts;
2. a heading for every part, and one sticky way through the tab;
3. every control beside what it changes, before the thing it reveals;
4. answers, warnings and flags visible, and marked;
5. reference text one step away, in a disclosure that says what it holds.

## 2. How this was found

The API and the built web app were run locally and driven with Playwright (the e2e suite's Chromium) at 1280×800 and 390×844, in three states:

1. **one-off** (`pump-groups-input.json`): 2 pumps and 4 scenarios, after Solve all (5 solves), Pumps tab with defaults: the card closed, no data table, every chip on.
2. **lineups** (the same fixture): 4 pumps on Crane tees and 8 scenarios, after Solve all (9 solves). The card open, "Also show the other cases' station duties" ticked (6 rings, the curve family drawn), every disclosure at or below the chart opened (5 of 5) and both data tables shown.
3. **condenser** (the example "Chiller plant condenser water system"): 6 pumps and 1 scenario. The card open, Add 5 cases by number running, then the block's Solve all (7 solves in all). The station duties ticked by the add (6 rings), the disclosures at their defaults, no data table.

For each view the probe recorded:

- the heading and landmark outline;
- every paragraph's text and type size;
- every control and its distance below the nearest chart above it;
- the Tab order;
- each box that scrolls sideways;
- the repeated phrases;
- the accessibility snapshot and a full-height screenshot.

The components were read where a screenshot raised a question. Three designers then each drew a whole restructure from the measurements, three judges scored them, and this proposal is the winner with the judges' grafts (§11).

### 2.1 The numbers

At 1280×800 the Results pane's Pumps tab is **480 px wide** (the default split) with a **666 px** scroll area. At 390×844 it is 366 px wide with a 620 px scroll area. So a desktop gets the same single narrow column as a phone.

| View | Size | Height below the pump canvas | Screens of the pane | Paragraphs (words) | Controls | Tab stops | Headings below the chart |
|---|---|---|---|---|---|---|---|
| one-off, defaults | 1280×800 | 859 px | 1.3 | 10 (243) | 14 | 14 | 1 |
| one-off, defaults | 390×844 | 1,095 px | 1.8 | 10 (243) | 14 | 14 | 1 |
| lineups, everything open | 1280×800 | 12,391 px | 18.6 | 54 (3,210) | 57 | 69 | 3 |
| lineups, everything open | 390×844 | 18,044 px | 29.1 | 54 (3,210) | 57 | 69 | 3 |
| condenser, after Add cases | 1280×800 | 8,356 px | 12.5 | 28 (1,409) | 50 | 51 | 3 |
| condenser, after Add cases | 390×844 | 11,673 px | 18.8 | 28 (1,409) | 50 | 51 | 3 |

**Where things sit**, in px below their own chart's canvas:

| Element | one-off 1280 | one-off 390 | lineups 1280 | lineups 390 | condenser 1280 | condenser 390 |
|---|---|---|---|---|---|---|
| Pump chart: "Also show the other cases' system curves" | +642 | +878 | +674 | +826 | +706 | +842 |
| Pump chart: Show data table, Download image | +716 | +952 | +748 | +900 | +780 | +916 |
| Group chart: "Read along the curves" | — | — | +280 | +328 | +356 | +468 |
| Group chart: "Cases on this chart" | — | — | +438 | — | +562 | +750 to +970 |
| Group chart: the checkbox that reveals it, under it | — | — | +730 | +898 | +834 | +1,022 |
| Group chart: Add cases ("Cases to add") | — | — | +4,598 | — | +2,668 | +3,208 |
| Group chart: its Show data table, Download image | — | — | +7,416 | +11,729 | +6,481 | +9,658 |

**Other measurements:**

- **The card.**
  - Height when open: 7,503 px (condenser, desktop), 10,282 (lineups, desktop) and 14,983 (lineups, phone).
  - Its blocks in the condenser (desktop): members 320, Also found 176, the figure 2,544, the group table 365, the station 50, Add cases 624, Running combinations 2,524, the extremes 678 and the toolbar 44.
  - The station's first value is 3,522 px into the open card.
  - In Tab order, the card's header is stop 15 (condenser) and 23 (lineups), Add cases stop 46 and 57, and the group's data-table button stop 50 and 61: 35 and 38 stops past the header.
- **The pump chart's data table** inserts 1,320 px (desktop) or 2,036 px (phone): five fixed 288 px boxes, each scrolling about 1,241 px inside the scrolling pane. Lineups has 13 Tab stops on scroll boxes.
- **Type.**
  - 52 of the 54 paragraphs are 12 px.
  - The h3 "Pumps together" is 14 px, the size of both figcaptions.
  - The h4 "Add cases" is 12 px, smaller than its own field label "Cases to add" (14 px).
- **Walls of notes.**
  - 13 consecutive paragraphs with no heading or control: 845 to 925 words, 1,056 to 1,196 px on desktop and 1,360 to 1,532 px on a phone.
  - The longest single notes run to 230 to 248 words.
  - Each methods disclosure is 10 paragraphs of 820 to 870 words, and the two share 8 identical sentences.
- **Sideways.**
  - The page never scrolls sideways.
  - In the condenser, the Results pane's own scroller does, at both sizes: the four "Also found" buttons do not wrap and reach 558 to 1,207 px in a 480 or 366 px tab. `tests/pump-groups.e2e.ts` checks only `document.documentElement`, so CI misses it.

### 2.2 The commonest actions (KLM)

The Keystroke-Level Model (Card, Moran & Newell 1980), with `build-density.md` §3.2's constants: M 1.35 s, P 1.1 s, a press 0.2 s, and a scroll counted as one P (a wheel or a flick) per pane height. "After" values are estimates from §5's layout, to be measured in each slice (§9).

| Action (condenser) | Before | Before (KLM) | After (estimate) | After (KLM) |
|---|---|---|---|---|
| Read the station's duty after opening the card, desktop | 5 scrolls (3,522 px into the card) | 6.85 s | on the first screen (about +300 px) | 1.35 s |
| From the group chart to its data table, desktop | 10 scrolls (+6,481 px), point, press | 13.65 s | 1 scroll (about +400 px), point, press | 3.75 s |
| The same, phone | 16 scrolls (+9,658 px), point, press | 20.25 s | 2 scrolls (about +700 px), point, press | 4.85 s |
| From the group chart to Add cases, desktop | 4 scrolls (+2,668 px), point, press | 7.05 s | the nav's "Add cases" pill (point, press), then point, press | 3.95 s |
| Find the smallest NPSH margin over the cases, desktop | 9 scrolls to the extremes (+5,791 px), then read 18 lines | 11.25 s and the reading | the nav's "Running combinations" pill, then the extremes grouped by pump | 2.65 s and the reading |

## 3. What works well (keep it)

- **Every value is traceable** (GOALS §4.2): each pump's trace, both methods disclosures with their references, the server's own sentence under Details wherever the app rewords one, and the system curve's method sentence.
- **The screen and the image say the same thing.** One words function per chart (`chartNotes`, `groupNotes` and `groupNoteLines`) feeds the screen and the PNG footer, and the export's group words are checked word for word against the card's helpers. A layout change can move markup without the image or the workbook drifting.
- **Physics flagged by default** (GOALS §4.6): FlagIcon by severity, and the red icon with "physically invalid:" on invalid cells and extremes. Refusals are given in words with the members still drawn.
- **The requests are well behaved** (D10): one at a time, on demand, cancelled by a solve or a goal seek. Each has its Cancel and its retry, and the focus passes between them.
- **The readouts** are native range inputs whose value text carries the reading, with Escape and "Back to the duty".
- **The case is named on every result** (D15): the captions, "(shown)", "(out of date)" and the amber stale tint.
- **The default view is compact.** The one-off project shows 859 px below the chart with the card closed, and the closed card names its members. The disorder appears once the card is open and scenarios exist.
- **The components are presentation only.** PumpsView computes every value and makes every request (`PumpsView.svelte:376–692`); the card and the block take props. So the restructure moves markup without touching a request effect.
- **On phones**, Running combinations and "Other cases' group curves" already read as lists, and the page never scrolls sideways.

## 4. Measured friction

High first; within a severity, in the order an engineer meets them. The ids in the last column are the audit's two problem lists (U for usability, X for accessibility and structure). `.svelte` paths are under `apps/web/src/lib/components/results/`, `.ts` paths under `apps/web/src/lib/utils/`, `routes/` under `apps/web/src/` and `services/` under `apps/api/src/opensolve_pipe/`.

| # | Sev. | Observation (measured) | Where | Ids |
|---|---|---|---|---|
| F1 | high | Nothing below the pump chart has a heading. Everything from the canvas down is one flat run of siblings in one `<figure>` (chips, slider, up to about 18 notes, the case list, the toolbar, up to 6 tables). The card body is one column of more than 15 blocks. Three headings in 12,391 px; a screen-reader user gets 3 heading stops in 18 screens, and about 15 region landmarks that are mostly data tables. | `PumpChart.svelte:485–975`; `PumpGroupChart.svelte:595–1679` | U-P01, X-P01, X-P04, X-P05, X-P41 |
| F2 | high | The open card runs 7,503 to 14,983 px (11 to 24 screens) with no section, collapse or way back. The card's toggle, the view row and the case tabs all scroll out of view. | card; `ResultsPanel.svelte:963` | U-P03, X-P17, X-P55 |
| F3 | high | The group chart's Show data table and Download image sit 6,481 to 11,729 px below the chart, after Add cases, Running combinations and the extremes, and its tables open there. Download image reads as belonging to the extremes. | `PumpGroupChart.svelte:1319–1350` | U-P04, X-P11, X-P53 |
| F4 | high | Physics flags sit in a last column, off-screen to the right: the group table scrolls to 1,052 to 1,200 px, Running combinations to 764 to 899 px. A phone shows only Pump and State. Rows swell to about 100 px for a reason out of view, and the flag text is only in a tooltip and sr-only, so touch users never read it. | `pump-group-chart.ts:1741–1767`; `PumpGroupChart.svelte:1105–1115, 1274–1284` | U-P05, X-P35 |
| F5 | high | The decisive results come last, as fine print. In the condenser the extremes give "physically invalid" and NPSH margins of −4.934 to −1.334 m, as 18 lines of 12 px prose (658 px) at the foot of the card. Nothing at the top says any case is invalid. | `PumpGroupChart.svelte:1295–1316` | U-P06, X-P38 |
| F6 | high | Warnings and request states look like the routine notes. "25 of 42 group-system-curve points have no rise" and "The group system curve has no rise at the duty's flow …" are plain slate paragraphs in the 13-paragraph run. The pump chart's system-curve state sits among the notes. | `PumpGroupChart.svelte:903–905, 950–956`; `PumpChart.svelte:580–616` | U-P07, X-P07 |
| F7 | high | Passive explanation comes before the controls: up to 1,532 px of 12 px prose between "Also show…" and the tables, and 6 to 9 notes between the pump chart's readout and its case list. | as F6 | U-P08, X-P06 |
| F8 | high | Two case pickers on one tab with near-identical names, "Cases on the chart" and "Cases on this chart", follow different rules: caps of 5 and 6 others, glyphs against rings, scenario order against ring order, and component state against page state. | `PumpChart.svelte:639–674`; `PumpGroupChart.svelte:745–783` | U-P10, X-P19 |
| F9 | high | Controls come out of order. "Cases on this chart" is drawn above the checkbox that reveals it (+438 against +730 px), so ticking the box moves it 260 to 290 px. Pressing Add cases ticks a checkbox about 2,000 px higher. | `PumpGroupChart.svelte:745–800`; `PumpsView.svelte:742–753` | U-P13, X-P13 |
| F10 | high | The "Also found" buttons do not wrap (`.btn` has `whitespace-nowrap`), so the Results pane scrolls sideways at 1280 and at 390. The four labels are cut where they differ, and none says it replaces the ticked pumps. | `routes/layout.css:57`; `PumpGroupChart.svelte:633–644` | U-P15, X-P32 |
| F11 | high | Tables follow viewport breakpoints in a 480 px pane. The pump chart's curve grid goes two-up at 225 px a column, while Running combinations stays a wide table scrolling sideways on a desktop. | `PumpChart.svelte:851`; `PumpGroupChart.svelte:1158` | X-P34 |
| F12 | high | A readout is never on screen with its curve: the pump canvas is 624 px of a 666 px pane. On a phone the group readout is +468 px below a 256 px canvas, behind a 452 px legend. | `PumpChart.svelte:523–571`; `PumpGroupChart.svelte:698–741` | X-P12 |
| F13 | medium | Type runs against the outline. The h4 is smaller than its own label. The h3 is the size of the captions. The h5 "Extremes…" follows the Add cases section, so heading navigation files it under the editing form. Notes switch between two slate tones with no meaning. | `PumpLineupsBlock.svelte:135`; `PumpGroupChart.svelte:1297` | U-P02, X-P02, X-P03 |
| F14 | medium | The same facts appear two or three times. The ring list (230 to 248 words) restates every row of "Other cases' station duties". The two methods share 8 sentences. The figcaption and the legend name every member again. The "Operating point" sentence repeats the readout. | `pump-group-chart.ts:1337–1419` | U-P09, X-P08, X-P25 |
| F15 | medium | The opened card starts with setup: in the condenser, 464 px of six one-per-row checkboxes, a hint, four Also found buttons and a 100 px caption come before any value. | `PumpGroupChart.svelte:596–656` | U-P14, X-P33 |
| F16 | medium | Add cases, the one control that changes the project, sits mid-card between the group table and Running combinations. After its job is done it stays 624 to 883 px: greyed Add and Solve all, five "already a scenario" lines and a refusal naming them again. | `PumpGroupChart.svelte:1138–1141` | U-P19, X-P14, X-P15 |
| F17 | medium | Requests' progress, Cancel and retry are stacked away from what they belong to. The pump chart's states are not announced, and its overlay status is inserted already filled. Retry words and layouts differ by request. | `PumpChart.svelte:580–616, 692–707`; `PumpGroupChart.svelte:804–939` | U-P40, X-P16, X-P29, X-P51 |
| F18 | medium | Disclosures follow four patterns and do not say what they hold. The card header and both data-table toggles are custom buttons. Two "Show data table" and two "Details" have the same names. The closed card names only its members. | `PumpGroupChart.svelte:579–593, 1321–1331`; `PumpChart.svelte:712–720` | U-P17, X-P26, X-P27, X-P28 |
| F19 | medium | Fixed help is always on screen: the select's sentence, the server-finder hint, the read-along hint, both cost hints, and Add cases' About and interchangeability text. The ui-guide says static help shows on focus. | `PumpsView.svelte:851`; `PumpGroupChart.svelte:628–631, 737–740` | U-P18, X-P46 |
| F20 | medium | Links, disclosures, actions and toggles all look like small blue text. The Show chips look like the action buttons; on and off are hard to tell apart on a phone. | `PumpChart.svelte:510–521` | U-P16, X-P47 |
| F21 | medium | Why a control is unavailable is never on screen: Solve all, both Download image buttons and Compute them again keep the reason in `title` and sr-only. Capped checkboxes look enabled. | `PumpLineupsBlock.svelte:236–249`; `PumpChart.svelte:728–735` | U-P20, X-P45, X-P24 |
| F22 | medium | The card's tables are hand-built, with no Sort, Fields or Flagged only, unlike Results per pump above them. At phone width they get three treatments: a sideways table, a squeezed five-column table and a list. | `PumpGroupChart.svelte:1026–1294` | U-P21, U-P22, X-P36, X-P37, X-P39, X-P44 |
| F23 | medium | Small scroll boxes sit inside the scrolling pane: a scroll trap on touch and 13 extra Tab stops. Some have no edge shadow. Running combinations' group lines are cut at the box's edge. | `PumpChart.svelte:805–941` | U-P23, U-P24, X-P40 |
| F24 | medium | Cases come in three orders (the pump chart's list, the rings, Running combinations). Ring numbers read like pump counts ("1 · 5 of 6 running"). Markers disagree between the list and the chart (☆ against ✳; □ and ▢ alike) and change as cases are unticked. | `pump-chart.ts:815–821`; `PumpsView.svelte:801` | U-P11, U-P27, X-P20, X-P21, X-P22 |
| F25 | medium | Cases that draw nothing take chart slots. "Pump P1 off" on P1's chart takes one of 5, so three cases that would draw are disabled. | `PumpsView.svelte:226–240` | U-P12, X-P23 |
| F26 | medium | Text points to hidden or distant places without a link: "the data table says why", "see Running combinations", "Results → Checks", "on its pump chart above". | notes | U-P28, X-P18, X-P49 |
| F27 | medium | The legends differ. The pump chart's is inside the canvas and mouse-only. The group's is an HTML list taller than its chart on a phone (452 against 256 px), naming every member again. | `pump-chart-config.ts:704–722`; `PumpGroupChart.svelte:671–692` | U-P32, X-P30, X-P31 |
| F28 | medium | The readouts are run-on 12 px sentences: six values on the pump chart, 5 to 7 lines with six pumps on the group chart. | `PumpGroupChart.svelte:736` | U-P34 |
| F29 | medium | The Pump chart select also changes the card's default members, and no text says so. | `PumpsView.svelte:340` | U-P37 |
| F30 | medium | Content shifts while requests run: rings join the legend one case at a time, and state rows come and go above the notes. | `pump-group-chart.ts:723–801` | X-P52 |
| F31 | medium | Direct labels overlap near the duty on both charts. Items 107 and 108 cover only the group chart's. | canvases | U-P31, X-P56 |
| F32 | medium | Nothing introduces the cards' different words: operating point against station duty, head against rise, carrying flow against running. | notes | U-P42 |
| F33 | low | Small faults: the pump chart's data table lists other cases' curves before the shown case's; Speed has no unit and "100 %" wraps; the duty sentence splits when a Details opens; units differ between the summary and the server's sentences. | `PumpChart.svelte:763–850`; `PumpGroupChart.svelte:1402–1423` | U-P26, U-P35, X-P42, X-P43 |
| F34 | low | Internal ids reach users: "(D13)" six times in the condenser's notes, and "(CLAUDE.md D13)" in the server's methods text. | `pump-group-chart.ts:131`; `services/pump_groups.py:1454` | U-P29, X-P09 |
| F35 | low | A wording bug: "Not on the chart: Pump P1 at 90 % speed (not on the chart (unticked under Cases on this chart))". | `pump-group-chart.ts:1413` | U-P30, X-P10 |
| F36 | low | The inline "Trace of {pump}" button (44 px) leaves a gap in the middle of its sentence. | `PumpChart.svelte:622–627` | U-P33, X-P48 |
| F37 | low | Case names and the stop order use pump ids ("P6 off") where every other line says "Condenser water pump CWP-6". | `pump-lineups.ts` | U-P36 |
| F38 | low | View choices are kept for different lengths: chips per browser, the pump chart's unticks until a pump switch, the card's until a reload, the data tables never. The "(shown)" item looks like a checkbox without its box, and member labels move on tick. | `PumpChart.svelte:173, 642`; `PumpGroupChart.svelte:617` | U-P38, U-P39, X-P50, X-P54 |
| F39 | low | No layout budget guards the Results card (`tests/build-density.e2e.ts` has none), so each slice added height unchecked. | `tests/` | X-P57 |

## 5. The recommended structure

### 5.1 One anatomy for both charts

Each chart is built the same way, top to bottom:

1. its **title** (the figcaption, which is also the image title);
2. the **canvas**;
3. the **reading controls**: the Show chips (pump chart), the slider and its readout;
4. one **request strip**: each request's state on one line, with its own Cancel or retry beside it, and the warnings about the curve, marked;
5. the **legend** (the group chart; the pump chart's stays inside its canvas);
6. the **actions**: Show data table and Download image, with the unavailable reason visible;
7. the **data region**, which opens right there;
8. the **notes about the values**, always shown, warnings and checks first, marked;
9. the **reference** disclosures, each naming what it holds;
10. the **other cases**, under their own heading: the switch first, then the list it reveals, its progress, its notes.

The card adds two plain sections around its chart, **Station** before it and **Running combinations** after it. Between them sits **Add cases**, a framed panel, as the one part that changes the project.

### 5.2 Type and marks

- **Headings.**
  - h3: 16 px semibold.
  - h4: 14 px semibold, with a rule above.
  - h5: `.section-title`, 12 px small caps.
  - Legends and field labels inside a section: 12 px medium, so no label outranks its heading.
- **Answers:** 14 px with tabular figures. These are the station's values, the readouts, Running combinations' lead and the extremes.
- **Notes:** 12 px in one tone (slate-700). Help and reference text is slate-600.
- **Marks**, from the ui-guide's status lines: ⚠ for a warning, ✓ for a check that agrees, ⬣ for a request that failed, a spinner while one runs.
  - **Placement.** A warning mark is `role="img"` named "Warning" and sits beside its sentence's `<p>`, never inside it, so the sentence's text and its test anchors are unchanged. Plain notes carry no mark.
  - **Design checks.** Their limits never get one: they are design practice, never a flag (D19).

### 5.3 Top to bottom, every element placed

The Pumps tabpanel (`PumpsView.svelte`'s `space-y-4` column), the same order at every width.

**0. The section nav** (new; §5.4). Shown with the Pumps together card, that is with two or more pumps with results.

**1. Results per pump.** Unchanged: the ResultsTable and its note. A visually hidden h3 "Results per pump" is added before it, as the nav's target and the outline's first stop.

**2. Pump chart** (`div.card`, `data-pump-chart`; shown when a pump has a result)

- **Header row.** The h3 "Pump chart" (tabindex −1). With more than one pump, the select sits beside it, labelled by the h3, so its name stays "Pump chart". Its sentence ("The pump and system curves of one pump at a time; …") becomes `help`, shown on focus. Below a 21 rem container the select drops under the heading.
- **The figure** (attributes unchanged), with the figcaption "Pump and system curves: {pump}, {case}".
  - **In place of the canvas when needed:** the chunk-failure alert or "The chart cannot be drawn in this browser. The table below lists its points." Either forces the data region open and hides the chips, the slider and the actions, as today.
  - **The canvas** (`role="img"` with its summary; the Chart.js legend inside it). Its legend click stays: it is how a design-check mark is hidden (`pump-chart-config.ts:211–212`).
  - **Reading.**
    - The group "Show": chips Efficiency, Shaft power, NPSH, Speed range and Design checks, drawn as toggle chips (a ✓ and a fill when pressed, an outline when not; `aria-pressed`; remembered per browser as today).
    - Then "Read at flow" with "Back to the duty".
    - Then the readout "At the duty 21.58 L/s: Pump head 40.33 m, System head 40.34 m, …". It is 14 px label and value pairs with the same text (the separators visually hidden), not live.
    - This is the order `pump-chart.md` §4.1 gives.
  - **The strip** (nothing when idle).
    - **Pump state.** First, the pump note: "This pump is off: …" or "This pump is held at zero flow by its check …".
    - **The system curve's row.** One always-present `role="status"` span (empty when idle) holds its state, with the button beside it:
      - spinner "Computing the system curve for this solve…" [Cancel] (named "Cancel the system curve");
      - ⬣ "The system curve could not be computed: {message}" [Try again];
      - "The system curve has not been computed for this solve." or "…was not computed: you cancelled it." (and the goal-seek and new-solve variants), with [Compute the system curve], described by the sentence.
    - **Missing heads.** ⚠ "No point of the system curve has a head …" or "N of 41 system-curve points have no head: …".
    - **Focus.** The Cancel to Try again or Compute handover (`PumpChart.svelte:353–370`, with the figure as fallback) is unchanged.
  - **Actions** (one line, wrapping at 270 px; `export.md` §5.5).
    - [Show data table] or [Hide data table]: same names, `aria-expanded`, `aria-controls`, now also described by the figcaption, so the two charts' buttons are told apart.
    - [⤓ Download image]: same name, `data-chart-image` and reasons. While it is unavailable, its reason shows beside it as 12 px text: the same element its `aria-describedby` already points to.
  - **The data region** (when shown, or forced). The case shown first:
    - "Operating point: x L/s at y m" or "Held at zero flow: …" stays its first line, since the table is the chart's long description (`pump-chart.md` §4.4).
    - "Operating points by case" (Case, Flow, Head, Speed (%), State; bare numbers under "Speed (%)"; a list below 640 px).
    - The grid of the shown case's tables, two-up only from a 40 rem container: "Pump curve at …", "System curve" (with NPSHa, and Why no head with its Details), the efficiency, shaft power, NPSHr and speed-range curves.
    - Last, each other case's "System curve, {case}".
    - Every box gets `scroll-shadow-x`. From S7, each curve table is its own disclosure, "{caption} ({n} points)", full height when open.
  - **Notes about the values** (always shown, words from `chartNotes`, unchanged), in this order:
    - ⚠ each rising-head range;
    - ⚠ "NPSHa falls below NPSHr at about … the pump would cavitate beyond that flow.";
    - the best efficiency point or none, the shutoff head and the speed range;
    - the panels' notes;
    - "Dashed: the pump curve extrapolated beyond its data …";
    - then the method sentence, visible: "System curve: the network of this solve, solved again … minus the EGL at the suction." It ends with "Trace of {pump}" as an inline link: a button styled as a link, same name, no 44 px block, under WCAG 2.5.8's inline exception, as the refusals' element names already are (D10: "its method note links the pump's trace").
    - With the Design checks chip on: a small label "Design-check limits drawn", each limit note without a mark, and the closing sentence, followed by [Go to Checks]. That button switches the Results view to Checks and focuses its tab.
  - **h4 "Other cases on the pump chart"** (with scenarios and another case with a result for this pump; inside the figure, so every figure-scoped test still finds it):
    - The fieldset "Cases on the chart", with "● {case} (shown)" as a static tag (same words; not a 44 px row with no box).
    - One 44 px checkbox per other case: the marker in a fixed-width column, the name, " (out of date)". They sit in an auto-fill grid (13 rem minimum: two columns in a 480 px pane, one on a phone).
    - A ticked case in which this pump is off or carries no flow says so beside its box, outside the label: "(off in this case: no point drawn)". From S8 such a case takes no slot.
    - Capped boxes look unavailable (greyed, a not-allowed cursor), stay `aria-disabled`, and are described by "At most 6 cases at once.".
    - Then the checkbox "Also show the other cases' system curves", with its cost sentence **kept visible**: on touch, focus comes only with the tap that starts about 41 solves.
    - Then, beside it, its always-present status "Computing system curves: 1 of 3…" with [Cancel] (named "Cancel the other cases' system curves").

**3. Pumps together** (`section.card`, `data-pumps-together`, a region named by its heading; two or more pumps with results; closed by default, D21)

- **The h3** holding the toggle button "Pumps together", with "(members)" while closed: kept, a recorded departure (§6.4 item 13).
  - While closed, a second, muted line describes the button (`aria-describedby`, so its name still starts "Pumps together"): "The station's duty, the group curve, each pump's share and cases with fewer pumps running", plus "; Running combinations" with scenarios.
- **Members.**
  - The fieldset "Pumps in the group" as a grid (13 rem minimum; names wrap; the slot symbol's column reserved, so a label never moves on tick).
  - "At most 6 pumps in a group." when capped.
  - "The calculation server finds the part of the network …" becomes `help` on focus, still the fieldset's description.
  - While the members are the default suggestion: "Suggested for {pump}, the pump on the pump chart above; tick pumps to choose your own."
  - The other suggestions:
    - one: its "Also found: …" button, wrapping (`whitespace-normal`, left-aligned);
    - two or more: a disclosure "Other groups found: {n}" holding them;
    - either way described by "Showing a group found replaces the pumps ticked."
- **When the card has no values:** the unavailable sentence (not converged, not the latest, Solve all stopped, the latest solve failed) replaces everything below. With no member ticked: "Tick the pumps to see together."
- **h4 "Station"** (tabindex −1). Its answer first:
  - **The refusal**, when refused, visible (`data-group-refusal`): the bold sentence and the list "Why they do not form a station" or "Why the group curve is not defined", with element names as buttons and each "Details".
  - **The dl "The station"** at 14 px with the values in bold: "Station flow, into the station at {S}", "Rise from {S} to {D}", and in series "Lost in the piping between the pumps". It is still the only `<dl>` on a card without scenarios.
  - **The region and table "The pumps in the group[, {case}]"** (`scroll-shadow-x`).
    - Columns as today except the last Flags column. Each flagged row is followed by a **flag line**, ResultsTable's own row-notes pattern (`ResultsTable.svelte:470–474`): sticky to the box's visible width (`w-[100cqw]`), `data-row-notes`, `data-label="Flags"`. It holds each flag as FlagBadge's tinted pill followed by **its text, visible** at 12 px.
    - The tints come from a small `flagTone(severity)` beside `SEVERITY_LABELS`, since FlagBadge reads the workspace and the card's unit tests mount none.
    - The sticky Pump names wrap at 12 rem.
    - Below 640 px the table reads as a list (Running combinations' classes, explicit roles kept), with the flag line under the pump's name.
  - "The share of each pump and its loss on the way come with the group curve." while it is pending.
- **h4 "Group chart"** (tabindex −1).
  - **The figure** (attributes unchanged), with the figcaption "{members} in parallel|in series[, {case}][ (out of date)]".
  - **In place of the canvas when needed:** the alert or the cannot-be-drawn note. Otherwise the canvas (`groupSummary`).
  - **Reading.** "Read along the curves" with "Back to the duty" and Escape. Its hint "Steps over the group curve's samples, …" becomes `help` on focus. The readout (`data-group-readout`, same text) is 14 px pump and value pairs, in two columns from a 26 rem container and one pair per line on a phone.
  - **The strip.** One always-present `role="status"` span holds the curves' states (texts unchanged), each with its button beside it on the same line:
    - the group curve: Computing… [Cancel the group curve] · ⬣ … [Try again] · cancelled or not computed [Compute the group curve];
    - the group system curve: [Cancel the group system curve] · [Try the group system curve again] · [Compute the group system curve];
    - other state lines, with ⚠ where they qualify the answer ("n of m group-curve points have no flow …", "n of m group-system-curve points have no rise …", "No group curve for this case: …", "No group system curve: …"); "Tick two pumps or more to compute their group curve." plain.
    - The focus handovers (`PumpGroupChart.svelte:415–454`) are unchanged.
  - **The legend** ("Legend", entries unchanged), two columns from a 26 rem container.
  - **Actions:** [Show data table] (described by the figcaption) and [⤓ Download image] (name, `data-chart-image` and reasons unchanged, the reason visible).
  - **The data region** (`#data`), opened here, in this order:
    1. "Each pump's point (flow through it)";
    2. the duty sentence split into two paragraphs, each with its own Details: "● Group duty (station's flow): …; Duty check: …" and "System duty check: …";
    3. "Group curve (station's flow at each rise)";
    4. "Group system curve (…)";
    5. "Other cases' station duties" (a list below 640 px);
    6. "Other cases' group curves (…)" after it (`pump-lineups.md` §9.6).
  - **Notes about the values** (words from `groupNotes`, unchanged), in this order:
    - ✓ or ⚠ the duty check (with its Details and "Several steady states can exist …" when it disagrees);
    - ✓ or ⚠ the system duty check (with its Details);
    - the frame ("Pump curves and points are at each pump's flanges. … At the duty Pump P1 loses 1.931 m, …");
    - the member notes;
    - the dashed note.
  - **Reference**, three native disclosures with `.more-summary`, closed:
    - "How to read this chart: the axes, the group system curve, each pump's own system curve" holds the axes note, the system note and the own-system-curves note, with [Go to the pump chart];
    - "How the group curve is computed" (or "How this curve is computed", as today);
    - "How the group system curve is computed".
  - **h5 "Other cases on the group chart"** (with scenarios and a station shown):
    - **The switch, first:** "Also show the other cases' station duties", with its cost sentence kept visible.
    - **While it is off:** the one line "Other cases' station duties are not on the chart: tick “Also show …” to compute them (n other cases with results)."
    - **While it is on:** under it, the fieldset "Cases on this chart":
      - "● {case} (shown)" as a tag;
      - checkboxes "○ n · {name} (out of date)", the ring and number in a reserved column, in `lineupChartPriority` order;
      - capped boxes greyed, with "At most 6 other cases at once.".
    - **Progress:** an always-present `role="status"` "Computing the other cases' station duties: k of n…" with [Cancel] beside it ("Cancel the other cases' station duties").
    - **When some were not computed:** "Not every other case's station duty was computed: see Running combinations." with [Compute them again] (its unavailable reason visible) and [Go to Running combinations].
    - **The ring notes, visible:** the ring frame and `OTHER_CURVES_FRAME`, the clip note, `DUTY_CLAIM_RULE`, the ring list "Other cases on the chart (slate rings, numbered): …", "Not on the chart: …", and "Labels of n curves are left out for space; …".
- **h4 "Add cases"** (`PumpLineupsBlock`; the region "Add cases", `data-add-cases`; while a station is shown).
  - **The panel.** It is framed and tinted (a border, `bg-slate-50`), with the tag "Changes the project" beside the heading, outside it, so the heading's name stays "Add cases".
  - **While a gate holds:** only its sentence, Solve all (gates 4 to 6) and "Pump lineups table…" (D24 §7.2).
  - **When every planned case exists** (and none was refused for the cap of 20):
    - ✓ "The {n} cases {by number running | with each pump off} exist: {S1, S2 and S3}.";
    - [▶ Solve all (n)] with its reason visible when it is unavailable;
    - a disclosure "Cases to add: {By number running | Each pump off}, all {n} made" holding the full form, the refused Add and the refusal among it;
    - "Pump lineups table…" at the foot.
  - **Otherwise, D24 §7.11's order:**
    1. the segments "Cases to add" (label 12 px);
    2. About;
    3. the interchangeability sentence;
    4. the stop order's disclosure;
    5. the "Cases:" preview;
    6. the names line;
    7. new: "In the names, P6 is Condenser water pump CWP-6, …", only when some member's name does not contain its id;
    8. [Add n cases] [▶ Solve all (n)] with visible reasons;
    9. the refusal;
    10. "Pump lineups table…".
  - **After an Add:** "Now ticked: “Also show the other cases' station duties” (Group chart)." The focus still moves to the block's Solve all (D24 §7.8).
  - The sr-only polite status (`data-stop-status`) is unchanged.
- **h4 "Running combinations"** (tabindex −1; with scenarios and a station shown).
  - **The lead** (14 px; ⚠ when a case has a warning or a physically invalid value): "{n} cases, {k | none} physically invalid[, {w} with warnings], {m | none} out of date." For the lineups fixture: "9 cases, none physically invalid, 1 with warnings, none out of date."
  - **h5 "Extremes over these cases (current results)"**, now nested under the table it summarises.
    - The dl "Extremes over these cases" keeps its element and every word. Its lines are grouped by pump: the pump's name once as a visible label, `aria-hidden`, while each term keeps "Pump P1, largest flow" with the name visually hidden after the first. It is 14 px, with the red icon and "physically invalid:" where invalid.
    - Then "Not counted (out of date): …".
  - **The region and table "Running combinations"** (`data-running-combinations`; its caption visually hidden beside the h4, still its name; `scroll-shadow-x`).
    - **Order:** the case shown, then the cases in ring order (`lineupChartPriority`), then the cases without a ring.
    - **Group heading lines:** "{name} (shown)(out of date) · ring n", the lineup line and the station line, each sticky to the box's visible width, so they wrap in view.
    - **Pump names** become trace buttons, as in the group table.
    - **Flags:** a flag line under a flagged pump's row, as in the group table, keeping `data-label="Flags"`.
    - **Invalid and stale:** invalid cells marked, stale groups amber.
    - **Phones:** a list below 640 px with no "Flags None" line ("None" stays sr-only).

Nothing comes after the card.

### 5.4 The section nav

The tab gets one way through, built on the ui-guide's sideways pill row.

- **Markup and place.** A `nav` named "Pumps view sections", sticky at the top of the Results pane's scroller, white, with a rule under it. It is 52 px tall: 44 px pills and 8 px of padding, 7.8 % of the desktop pane and 8.4 % of a phone's, inside the ui-guide's 15 % chrome rule.
- **When.** Shown with the Pumps together card. A project with one pump has no card, and no nav.
- **Pills.**
  - Always: "Per pump", "Pump chart" and "Pumps together".
  - While the card is open: "Station", "Group chart", "Add cases" (while the block is drawn) and "Running combinations" (with scenarios and a station).
  - **Marks.** A pill gets ⚠ (with sr-only "has warnings") when its section holds a physics flag of warning or invalid severity, a physically invalid value, a refusal or a request error. Never for a design check (D19), never for a note.
- **One Tab stop.**
  - The Tab stop is the current pill, else the first; ←, →, Home and End move between pills.
  - Enter or Space scrolls the section's heading under the nav (`scroll-margin-top` is the nav's height plus 8 px) and focuses it (tabindex −1).
- **Buttons, never links.** The URL fragment is the project (D3), so a `href="#…"` would replace it; a test asserts `location.hash` unchanged after every press.
- **Where you are.** `aria-current="location"` marks the pill whose heading was passed last. An IntersectionObserver on the scroller sets it, paused while the Pumps tabpanel is hidden (ResultsPanel keeps visited views mounted).
- **Focus never hidden.** While the Pumps tab is shown, the scroller gets `scroll-padding-top` equal to the nav's height, so a focused control is never covered (WCAG 2.4.11). Other views keep none.
- **One shared component.** The wheel that scrolls the row sideways, the edge shadows and the current pill scrolled into view are the view row's (`ResultsPanel.svelte:458–476, 960–990`), made a shared component in S2.
- **Considered and dropped:**
  - Read blocks sticky to the pane's foot. With the nav they would cover about 130 px of a 620 px phone pane, over the canvas they read (WCAG 2.4.11). The readouts sit directly under their canvas instead.
  - Segmented sub-views of the card. They would hide Running combinations' flags behind a tab by default and break reading the chart against its tables.

### 5.5 Phones

Below 640 px (366 px at 390×844, 288 px at 320) the order and every control are the same; only the layout changes.

- **The nav** is one sideways-scrolling row of 44 px pills with edge shadows, sticky at the pane's top. The current pill is scrolled into view.
- **Grids and lists** follow their container, not the viewport. `@container` goes on the grids, the legend and the member grid only, never on an ancestor of a ResultsTable, a Dialog or a sheet, since layout containment would trap their fixed-position sheets. So the members, the case lists and the legend go one per row, and the curve tables one column.
- **Chips** wrap to two rows, and "on" is a ✓ as well as a colour.
- **Readouts** put one pair per line.
- **The strip:** a status line's button wraps under its sentence, and stays next to it in the reading order.
- **Actions:** Download image drops under Show data table at 270 px or less, with its visible reason under it.
- **Tables read as lists:** "Operating points by case", "The pumps in the group" (flag line under the name) and "Other cases' station duties", as Running combinations and "Other cases' group curves" already do.
- **Add cases:** the segments stay one row (D24's measured 169 px segments). Its fold puts the done state in about four lines.
- **Help on focus** floats under its control (`.field .help`).
- **Sideways scroll:** none for the page or the pane's scroller at 390 and 320 px, asserted.

### 5.6 Wireframes

Desktop, 1280×800, Results pane about 480 px, lineups fixture after Solve all, the card open, station duties ticked, every other disclosure at its default.

```
▓ = the sticky section nav   [ ] control   ▸ closed disclosure   ░ the action panel
┌────────────────────────────────────────────────────────────┐
│▓ Per pump  Pump chart  Pumps together  Station  Group ch› ▓│ one row, sideways, 1 Tab stop
│  (h3, sr-only) Results per pump  [ResultsTable, unchanged] │
│┌──────────────────────────────────────────────────────────┐│
││ Pump chart (h3)   [ Pump P1                           ▾ ]││ select named by the h3
││ Pump and system curves: Pump P1, Base case               ││ figcaption = image title
││ ┌──────────────────────────────────────────────────────┐ ││
││ │ head · η · P · NPSH panels  (Chart.js legend inside) │ ││ canvas, unchanged
││ └──────────────────────────────────────────────────────┘ ││
││ Show (✓ Efficiency) (✓ Shaft power) (✓ NPSH)             ││ toggle chips
││ Read at flow ━━━━━━━━━━━━━●━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ││
││ At the duty 21.58 L/s:  Pump head 40.33 m                ││ 14 px pairs
││   System head 40.34 m  Efficiency 69.41 %  Shaft po…     ││
││ ◌ Computing the system curve for this solve…   [Cancel]  ││ strip: only while needed
││ [Show data table]  [⤓ Download image]                    ││ ≈ +150 px (today +748)
││ ⚠ NPSHa falls below NPSHr at about 39.41 L/s (read …     ││ notes, warnings first
││ Best efficiency point (+): 74 % at 30 L/s and 35.5 m, …  ││
││ Shutoff head (–): 45 m.                                  ││
││ Shaft power ρgQH/η … the largest there is 15.1 kW at …   ││
││ System curve: the network of this solve, solved again …  ││ method stays visible,
││ … minus the EGL at the suction. Trace of Pump P1         ││ Trace an inline link
││ ── Other cases on the pump chart ─────────────── h4 ──── ││
││ Cases on the chart   ( ● Base case (shown) )             ││
││ [✓] △ 3 of 4 running (Pump   [✓] □ 2 of 4 running (Pump  ││ two columns
││       P4 off)                      P3, Pump P4 off)      ││
││ [✓] ✳ 1 of 4 running (…)     [✓] × Pump P2 off           ││
││ [✓] ▽ Pump P3 off            [ ] Pump P1 at 90 % (grey)  ││
││ [ ] Delivery tank 5 m higher (grey)                      ││
││ Off in this case (nothing drawn): Pump P1 off            ││ S8: takes no slot
││ At most 6 cases at once.                                 ││
││ [ ] Also show the other cases' system curves             ││
││     Each is computed on request, … about 41 solves …     ││ cost stays visible
│└──────────────────────────────────────────────────────────┘│
│┌─ ▾ Pumps together ───────────────────────────── h3 ──────┐│
││ Pumps in the group                                       ││
││ [✓] ▲ Pump P1          [✓] ■ Pump P2                     ││ grid, symbol column kept
││ [✓] ★ Pump P3          [✓] × Pump P4                     ││
││ Suggested for Pump P1, the pump on the pump chart above… ││
││ ▸ Other groups found: 2                                  ││
││ ── Station ───────────────────────────────────── h4 ──── ││
││ Station flow, into the station at Tee TS1 (run inlet)    ││ the answer first, 14 px
││                                              85.23 L/s   ││
││ Rise from Tee TS1 (run inlet) to Tee TD1 (…)   38.41 m   ││
││ The pumps in the group, Base case          [scrolls → ▒] ││
││  Pump        State    Speed  Flow   Share  Head  Lost …  ││
││  ▲ Pump P1   Running  100    21.58  25.32  40.34 1.931   ││
││  ■ Pump P2   Running  100    20.8   24.4   40.68 2.271   ││
││ ── Group chart ───────────────────────────────── h4 ──── ││
││ Pump P1, Pump P2, Pump P3 and Pump P4 in parallel, Base  ││
││ ┌──────────────── group canvas, 18 rem ────────────────┐ ││
││ └──────────────────────────────────────────────────────┘ ││
││ Read along the curves ━━━━━━━━━━━━━━━━━━━━━━━━━━━●━━━━━━ ││
││ At a rise of 38.41 m:  Pump P1 21.58 L/s  Pump P2 20.8 … ││
││ ◌ Computing the group system curve for this solve…[Cancel]│ strip, while needed
││ Legend, two columns                                      ││
││ [Show data table]  [⤓ Download image]                    ││ ≈ +400 px (today +7,416)
││ ✓ At the duty's rise the group curve gives the solve's … ││ checks first, marked
││ ✓ At the duty's flow the group system curve gives …      ││
││ Pump curves and points are at each pump's flanges. …     ││
││ ▸ How to read this chart: the axes, the group system cu… ││ reference, one step away
││ ▸ How the group curve is computed                        ││
││ ▸ How the group system curve is computed                 ││
││ OTHER CASES ON THE GROUP CHART                      h5   ││
││ [✓] Also show the other cases' station duties            ││ the switch first …
││     Each case's station duty is computed on request, …   ││
││ Cases on this chart   ( ● Base case (shown) )            ││ … the list under it
││ [✓] ○ 1 · 3 of 4 running …   [✓] ○ 2 · 2 of 4 running …  ││
││ Each numbered slate ring is another case's station duty… ││ ring notes stay visible
││ Other cases on the chart (slate rings, numbered): 1 · …  ││
││░ Add cases ────────────────── Changes the project ── h4 ░││ framed action panel
││░ ✓ The 3 cases by number running exist: S1, S2 and S3.  ░││ folded once done
││░ [▶ Solve all]  Every case's results are current.       ░││ reason visible
││░ ▸ Cases to add: By number running, all 3 made          ░││
││░ [Pump lineups table…]                                  ░││
││ ── Running combinations ──────────────────────── h4 ──── ││
││ ⚠ 9 cases, none physically invalid, 1 with warnings,     ││ the lead, first
││   none out of date.                                      ││
││ EXTREMES OVER THESE CASES (CURRENT RESULTS)         h5   ││
││ Pump P1  largest flow         37.95 L/s in 1 of 4 runn…  ││ grouped by pump
││          largest shaft power  15.05 kW in 1 of 4 runni…  ││
││          smallest NPSH margin 1.065 m in 1 of 4 running… ││
││ ┌ Running combinations ──────────────────── scrolls → ┐  ││
││ │ Base case (shown)                                   │  ││ lines wrap in view
││ │ 4 of 4 carrying flow: Pump P1, Pump P2, Pump P3 …   │  ││
││ │ ▲ Pump P1 → Running 100 21.58 40.34 12.28 3.327 Yes │  ││
││ │ 3 of 4 running (Pump P4 off) · ring 1  …            │  ││ ring order
││ │ Pump P1 at 90 % speed                               │  ││
││ │ ▲ Pump P1 → Running 90 5.471 36.09 3.866 5.045 Yes  │  ││
││ │  [⚠ Warning] The operating flow (5.471 L/s) is out- │  ││ flag line at the
││ │   side its efficiency curve: the efficiency is held…│  ││ visible width
││ └─────────────────────────────────────────────────────┘  ││
│└──────────────────────────────────────────────────────────┘│
```

Phone, 390×844: tab 366 px, scroll area 620 px; the same order.

```
┌──────────────────────────────────────┐
│▓ Per pump  Pump chart  Pumps tog… › ▓│ sideways row
│┌─ Pump chart ──────────────── h3 ───┐│
││ [ Pump P1                       ▾ ]││ select under the h3
││ Pump and system curves: Pump P1,   ││
││ Base case                          ││
││ ┌── canvas 544 px, legend inside ─┐││
││ └─────────────────────────────────┘││
││ Show (✓ Efficiency) (✓ Shaft power)││ chips wrap
││      (✓ NPSH)                      ││
││ Read at flow ━━━━━━━●━━━━━━━━━━━━━ ││
││ At the duty 21.58 L/s:             ││ one pair per line
││ Pump head 40.33 m                  ││
││ System head 40.34 m                ││
││ Efficiency 69.41 % …               ││
││ [Show data table]                  ││ ≈ +250 px
││ [⤓ Download image]                 ││
││ ⚠ NPSHa falls below NPSHr at …     ││
││ Best efficiency point (+): 74 % …  ││
││ System curve: the network … Trace  ││
││ of Pump P1                         ││
││ ── Other cases on the pump chart ─ ││ h4
││ ( ● Base case (shown) )            ││
││ [✓] △ 3 of 4 running (Pump P4 off) ││ one per row
││ [✓] □ 2 of 4 running (Pump P3, …)  ││
││ [ ] Also show the other cases'     ││
││     system curves                  ││
││     Each is computed on request …  ││
│└────────────────────────────────────┘│
│┌─ ▾ Pumps together ────────── h3 ───┐│
││ [✓] ▲ Pump P1                      ││ one per row
││ [✓] ■ Pump P2   …                  ││
││ ▸ Other groups found: 2            ││
││ ── Station ──────────────── h4 ─── ││
││ Station flow, into the station at  ││
││ Tee TS1 (run inlet): 85.23 L/s     ││
││ Rise from Tee TS1 (…) to Tee TD1   ││
││ (…): 38.41 m                       ││
││ ▲ Pump P1                          ││ the group table as a list
││   State Running  Speed (%) 100     ││
││   Flow (L/s) 21.58 Share (%) 25.32 ││
││ ── Group chart ──────────── h4 ─── ││
││ ┌── group canvas, 16 rem ────────┐ ││
││ └────────────────────────────────┘ ││
││ Read along the curves ━━━━━●━━━━━━ ││
││ At a rise of 38.41 m:              ││
││ Pump P1 21.58 L/s                  ││ one pair per line
││ Pump P2 20.8 L/s  …                ││
││ Legend, one column                 ││
││ [Show data table]                  ││ ≈ +700 px (today +9,658)
││ [⤓ Download image]                 ││
││ ✓ ✓ the duty checks; notes         ││
││ ▸ How to read this chart: …        ││
││ ▸ How the group curve is computed  ││
││ ▸ How the group system curve is …  ││
││ OTHER CASES ON THE GROUP CHART  h5 ││
││ [✓] Also show the other cases'     ││
││     station duties                 ││
││ [✓] ○ 1 · 3 of 4 running (Pump P4  ││
││       off)  …                      ││
││░ Add cases   Changes the project  ░││
││░ ✓ The 3 cases by number running  ░││
││░   exist: S1, S2 and S3.          ░││
││░ [▶ Solve all]                    ░││
││░ Every case's results are current.░││
││░ ▸ Cases to add: By number        ░││
││░   running, all 3 made            ░││
││░ [Pump lineups table…]            ░││
││ ── Running combinations ─── h4 ─── ││
││ ⚠ 9 cases, none physically invalid,││
││   1 with warnings, none out of date││
││ EXTREMES …                      h5 ││
││ Pump P1                            ││
││  largest flow 37.95 L/s in 1 of 4  ││
││  running (Pump P2, Pump P3, …)     ││
││ list: a block per case, per pump;  ││
││ no "Flags None" lines              ││
│└────────────────────────────────────┘│
└──────────────────────────────────────┘
```

### 5.7 What it should measure (estimates; each budget set from the build, as build-density did)

| Measure | Before | After (estimate) | Budget, in `tests/pumps-layout.e2e.ts` |
|---|---|---|---|
| The pane's scroller scrolls sideways (condenser, 1280 and 390) | yes | no | none at 1280×800, 390×844, 320×640 (S0) |
| Pump canvas to its Show data table | +716 to +952 px | about +150 (desktop), +250 (phone) | ≤ 300 px (S1) |
| Group canvas to its Show data table | +6,481 to +11,729 px | about +400 (desktop), +700 (phone) | ≤ 600 / 900 px (S2) |
| Card header to the station's first value (condenser) | 3,522 px | about +300 (desktop), +450 (phone) | ≤ 400 / 600 px (S3) |
| Headings below the chart (with scenarios and a station) | 3 | 9 | the outline, in order (S2) |
| Longest run of notes without a heading or control | 13 paragraphs, 925 words | 6 paragraphs | ≤ 7 paragraphs (S3) |
| Tab stops from the card header to the group's Show data table (condenser) | 35 | about 18 | ≤ 20 (S3) |
| Open card, condenser after Add cases (desktop) | 7,503 px | about 5,800 px | measured + 10 % (S5) |
| Scroll-region Tab stops, lineups, everything open | 13 | ≤ 3 | ≤ 3 (S7) |

The card gets about a quarter shorter. Running combinations stays open because it carries flags (GOALS §4.6), and it stays the card's longest block (about 2,100 px in the condenser). The headings and the nav carry most of the gain, and S6b (§12, question 2) carries the rest.

## 6. What moves, and what words change

### 6.1 What moves

| Element | Today | Proposed | Why |
|---|---|---|---|
| Pump chart's system-curve state, Cancel, retry | among the notes, after the readout | the strip under the reading controls, one line each, one live region | F6, F17 |
| Pump chart's method sentence and "Trace of {pump}" | among the first notes, a 44 px button splitting it | the last value note, visible; Trace an inline link | F36; D10 |
| Pump chart's Show data table, Download image | after the notes and the case controls (+716 to +952) | under the strip (about +150) | F3, F7 |
| "Operating points by case" and the case shown's curve tables | other cases' system curves first | the case shown first, other cases last | F33 |
| "Cases on the chart" and its overlay checkbox | after the notes, beside nothing | under the h4 "Other cases on the pump chart", at the figure's end | F1, F8 |
| Members, "Also found" | 6 rows and 4 unwrapped buttons | a two-column grid; "Other groups found: n" with two or more; wrapping | F10, F15 |
| The station (dl), the group table | after the figure and its notes (3,522 px in) | the first section, "Station" | F15 |
| The group's Show data table, Download image, data tables | the card's foot (+6,481 to +11,729) | under the group chart's legend (about +400) | F3 |
| The duty checks | in the run of notes | the first notes of the group chart, ✓ or ⚠ | F6 |
| The axes, system and own-system-curves notes | in the run of notes | "How to read this chart: …" | F7, F14 |
| "Also show the other cases' station duties" | under the list it reveals | above it, first under the h5 | F9 |
| Other cases' progress, Cancel, retry | three blocks inside the figure | beside their checkbox, under the h5 | F17 |
| Add cases | between the group table and Running combinations | after the group chart, framed, folded when done | F16 |
| Extremes | an h5 after Running combinations, filed under Add cases | the h5 under h4 "Running combinations", before its table | F5, F13 |
| Flags (group table, Running combinations) | the last column, off-screen | a flag line under each flagged row, at the visible width | F4 |
| Running combinations' cases | the shown, then scenario order | the shown, then ring order, then the rest | F24 |

### 6.2 New words

Every new word below is screen-only, except the S8 items at the end, which the image footer carries too. The export carries none.

- **Headings.**
  - h3 "Pump chart" and the visually hidden h3 "Results per pump".
  - h4 "Other cases on the pump chart", "Station", "Group chart" and "Running combinations".
  - h5 "Other cases on the group chart".
  - "Add cases" and "Extremes over these cases (current results)" are unchanged.
  - The fieldset legends "Cases on the chart" and "Cases on this chart" stay (`scenario-manager.md` §6.13, D24 §7.9; pinned by tests). The headings over them now say which chart each list changes.
- **The nav.**
  - Its name: "Pumps view sections".
  - Its pills: "Per pump", "Pump chart", "Pumps together", "Station", "Group chart", "Add cases" and "Running combinations".
  - "has warnings", sr-only, on a marked pill.
- **The card.**
  - The closed card's line: "The station's duty, the group curve, each pump's share and cases with fewer pumps running[; Running combinations]".
  - "Suggested for {pump}, the pump on the pump chart above; tick pumps to choose your own."
  - "Other groups found: {n}"
  - "Showing a group found replaces the pumps ticked."
- **The group chart's reference:** "How to read this chart: the axes, the group system curve, each pump's own system curve".
- **Add cases.**
  - "Changes the project"
  - "The {n} cases {by number running | with each pump off} exist: {ids}."
  - "Cases to add: {By number running | Each pump off}, all {n} made"
  - "In the names, {id} is {name}, …"
  - "Now ticked: “Also show the other cases' station duties” (Group chart)."
- **Running combinations:** the lead "{n} cases, {k | none} physically invalid[, {w} with warnings], {m | none} out of date."
- **The pump chart.**
  - "Design-check limits drawn"
  - "(off in this case: no point drawn)"
  - "Speed (%)" in place of "Speed", with bare numbers in "Operating points by case".
- **Buttons:** "Go to Checks", "Go to the pump chart" and "Go to Running combinations". They are buttons that focus a heading or switch the Results view, never touching the fragment.
- **S7:** "{table caption} ({n} points)".
- **Made visible, same words:** the unavailable reasons of Solve all, both Download image buttons and Compute them again, and the flag text after each badge.
- **Moved to help on focus, same words:** the select's sentence, "The calculation server finds …" and "Steps over the group curve's samples, …".
- **S8 only** (the image footer changes with them through the same helpers; the workbook carries none, since `utils/export/tables.ts` imports only the table helpers from `pump-group-chart.ts`):
  - "Not on the chart: X (not on the chart (unticked under Cases on this chart))" becomes "Not on the chart: X (unticked under Cases on this chart)". This one is in S0, as a bug fix.
  - The ☆ text glyph becomes ✳ (what Chart.js's `star` draws), and `rectRounded` (▢) gives way to ▽.
  - "Off in this case (nothing drawn): {names}", one line under the pump chart's case list, replaces S1's "(off in this case: no point drawn)" once such a case takes no slot.
  - "(D13)" becomes plain words, if the owner agrees (§12, question 3).

### 6.3 Words kept exactly

- **The words functions:** every `chartNotes`, `groupNotes` and `groupNoteLines` line, except the S0 fix.
- **Captions and titles:** both figcaptions (the image titles).
- **Buttons.**
  - "Show data table" and "Hide data table".
  - "Download image" and its accessible names.
  - Every Cancel, Try again and Compute name, "Try the group system curve again" and "Compute them again".
  - "Trace of {pump}", "Back to the duty" and "Pump lineups table…".
- **Checkboxes:** "Also show the other cases' system curves" and "… station duties", with their cost sentences.
- **Sliders:** "Read at flow" and "Read along the curves".
- **D24's block:** every string (`LINEUP_BLOCK_WORDS`, `STOP_ORDER_WORDS`, `LINEUP_TABLE_WORDS`).
- **Server and claim words:** the refusals, the methods, the server's sentences under Details, and Running combinations' lineup and station lines.

### 6.4 Recorded designers' defaults this changes

Each change is recorded with its reason in the named record, in the same change as its slice:

1. **The card's order:** members, Station, Group chart, Add cases, Running combinations. This changes D21's paragraph, and D24 §7.1, which puts Add cases "under the group table and its footer". It now sits after the group chart, still above Running combinations.
2. **The group chart's data table and image** sit under its legend (D21; `pump-groups.md` §6.5–§6.6).
3. **The notes are regrouped on screen:** curve warnings in the strip, the duty checks first, reference in disclosures, the ring notes under their h5. The image footer keeps `groupNoteLines`' and `chartNotes`' order (`pump-groups.md` §6.4; `export.md` §3.4). A new test (§10) proves every footer line is still on screen.
4. **Flags as a flag line,** not a last column, on screen (`pump-groups.md` §6.5; D24 §7.10). The image and the export have no flags column.
5. **Running combinations in ring order** after the case shown (D21 4d keeps "the shown first"; D24 §7.10).
6. **The extremes grouped by pump,** before the table (D21 4d).
7. **Add cases** framed, folded when done, with the "Now ticked" and id lines (D24 §7.11–§7.12; D24's measured block of 440 and 504 px is re-measured).
8. **Help on focus** for three hints (D21 4a and 4b; the select).
9. **"Also found"** behind "Other groups found: n" with two suggestions or more (D21).
10. **"Also show … station duties"** before "Cases on this chart" (D21 4d).
11. **Two live regions on the card,** one for the curves and one for the other cases, where 4d has one.
12. **The section nav,** a new pattern for `ui-guide.md`.
13. **The card header stays an h3 holding a button.** This departs from the ui-guide's "disclosures are native `<summary>`": a heading inside `<summary>` is flattened by some screen readers, the body is rendered only when open, and about 35 test drives use the button.
14. **The pump chart's Trace link inline** in its sentence (WCAG 2.5.8's inline exception), and "Speed (%)".

## 7. Keyboard and accessibility

**Heading outline**, with scenarios and a station shown:

- h2 Results
  - h3 Results per pump (visually hidden)
  - h3 Pump chart
    - h4 Other cases on the pump chart
  - h3 Pumps together
    - h4 Station
    - h4 Group chart
      - h5 Other cases on the group chart
    - h4 Add cases
    - h4 Running combinations
      - h5 Extremes over these cases (current results)

That is 9 heading stops below the chart, against 3 today. The extremes now nest under the table they summarise. The new sections are plain `div`s with headings, not landmarks. The regions that stay are the ones tests pin: "Pumps together", "Add cases" and the named scroll boxes (fewer after S7).

**Tab order** follows the visual order:

1. the nav (one stop);
2. Results per pump;
3. the select;
4. the chips;
5. Read at flow and Back to the duty;
6. the strip's button;
7. Show data table and Download image (the data boxes when open);
8. the Trace link;
9. Go to Checks;
10. the case boxes and the overlay box;
11. the card's toggle;
12. the members and "Other groups found";
13. the group table's names;
14. Read along the curves;
15. the strip's buttons;
16. the group's Show data table and Download image;
17. the notes' Details;
18. the reference summaries;
19. the station-duties box and its list;
20. Add cases;
21. Running combinations' box and its names.

The group's Show data table is about 18 stops from the card's header, against 35 today (condenser). From the nav, Add cases is the arrows and Enter, and its first control is the next Tab.

**Keys.**

- The nav: ←, →, Home and End; Enter or Space jumps and focuses the heading.
- The sliders keep Escape (back to the duty) and their `aria-valuetext`.
- Disclosures open with Enter and Space (native `<summary>`).
- The stop order keeps its focus restoration after each move and after Default order.
- After Add, the focus moves to the block's Solve all, as today.

**Live regions.**

- **Pump chart:** two always-present polite regions, one for its system curve in the strip and one for the other cases' curves beside their checkbox. The first progress message is now announced (F17).
- **Card:** two, one for its curves in the strip and one for the other cases' duties under the h5.
- Each region's visible text is the region itself, so nothing is read twice.
- The readouts stay not live.
- `data-stop-status` stays polite.

**Focus.**

- The Cancel and retry handovers are unchanged, with each figure as the fallback.
- The nav's targets are headings with tabindex −1 and `scroll-margin-top`.
- `scroll-padding-top` keeps a focused control clear of the nav (WCAG 2.4.11).
- The "Go to" buttons move the focus the same way.
- Nothing touches `location.hash` (D3).

**Disclosures.**

- New and existing ones are native `<details>` with `.more-summary`, and each summary says what it holds.
- None closes itself. The Add cases fold is a state the block reaches after its own Add, with the focus on Solve all, which stays visible.
- A data region is forced open when its chart cannot be drawn.
- The card header and the two data-table toggles stay buttons with `aria-expanded` and `aria-controls` (§6.4 item 13), and each toggle is now described by its chart's caption.

**Names and marks.**

- Visible words stay part of every name (WCAG 2.5.3); the nav's pills are named by their words.
- Toggle chips keep `aria-pressed`, with the ✓ `aria-hidden`.
- Capped boxes stay focusable and `aria-disabled`, now look unavailable, and are described by their cap.
- Disabled reasons are visible text, still in `aria-describedby`.
- Colour never carries meaning alone: FlagBadge pairs its icon with the severity word, and the flag text is now visible.
- "physically invalid:" stays sr-only beside the red icon.

**Targets.**

- At least 44 px for the pills, chips, case and member rows, summaries, the stop-order buttons and the toolbar.
- The Trace link and the refusals' element names are inline links (WCAG 2.5.8's exception).
- No page or pane sideways scroll at 1280, 390 or 320 px; text reflows at 320 px.

**Proof.** axe-core (WCAG 2.0, 2.1 and 2.2 A and AA) runs clean on `[data-pumps-together]` and on the pump chart's section, at both sizes, with every disclosure open. The scans open only closed summaries (`details:not([open]) > summary`), so they never close one.

## 8. What stays exactly as decided

- **GOALS §3:** correctness, then traceability, then usability. A tidier layout never hides, drops or blurs a correctness or traceability item.
- **GOALS §4.2 and D10:** every value traceable. The methods stay, both disclosures with their references. The server's sentence stays under Details wherever the app rewords one. The system curve's method sentence stays visible, with its link to the pump's trace.
- **GOALS §4.5 and D3:** nothing new in the link. View choices are kept per browser only (S7's data-table choice, in try/catch). The nav and the "Go to" buttons never touch the fragment.
- **GOALS §4.6, D19 and PRD §4.1:** flags shown by default, now more visible. Refusals stay visible. Design checks stay opt-in, their limits behind the "Design checks" chip, never a verdict on the chart and never a ⚠.
- **GOALS §4.7:** every feature on both sizes, each in its own layout.
- **D10, system curves on demand:** one at a time, each with its loading state, Cancel, Try again, Compute and its points' reasons, never shown with another solve's results. The owner's 2026-10-23 rule stands: every point without a head says why, in words and as data.
- **D13:** the claim words (`DUTY_CLAIM_RULE`, `OTHER_CURVES_FRAME`, "Several steady states can exist") are unchanged, and visible by default. Their "(D13)" is §12's question 3.
- **D14:** every placement here is reversible.
- **D15:** the case is named on every result. The pump chart shows other cases' points and curves, their system curves only on request. The case shown, the members, the preset, the stop order, "Also show" and the unticked cases are page state.
- **D17:**
  - Download image stays under each pump chart and on the card, unavailable with its reasons by one rule. The PNG is drawn from the screen's configuration.
  - Its footer words come from the same functions, and S1 to S7 change none of them.
  - Running combinations, the extremes, the stop order and the preset stay on screen only.
  - The export's 38 word-for-word tests and the committed workbook are untouched.
- **D21, the owner's answers** (2026-10-28, `pump-groups.md` §13):
  - The station's curves are defined between S and D.
  - No composite curve.
  - Groups are page state, never stored.
  - No trim or ISO 9906 inputs.
- **D21, kept behaviours:**
  - The card under the pump chart, closed by default, shown with two or more pumps with results.
  - At most six members; "Also found".
  - One request at a time.
  - The group system curve in orange.
  - The refusal in words with the members drawn; "Read along the curves".
- **D24, the owner's answers** (2026-11-04):
  - The two presets on the card, By number running first.
  - No "Every combination".
  - The editable stop order with its default, and the name form.
  - `MAX_SCENARIOS` 20.
  - The Pump lineups table in the manager, linked from the block's foot.
  - The curve family.
- **The pump chart, the owner** (2026-10-26): the best efficiency point is shown by default; no % of BEP flow; no bands without the design checks.
- **The owner's table rules** (2026-10-31, `build-density.md` §14–§18): they apply where S6 makes a table a ResultsTable. Any departure goes back to the owner.
- **Open owner items, not settled here:**
  - items 55, 71, 107 and 108 of `pump-lineups.md` §15;
  - the bypass mirror (roadmap §2).
  - §12's question 4 adds the pump chart's labels to item 107.

## 9. Slices

Each slice is a verified web slice on `web/pumps-layout`, merged only when:

- Vitest passes, with the component tests named;
- the whole Playwright suite passes at 1280×800 and 390×844;
- axe is clean with every disclosure open;
- its budgets in `tests/pumps-layout.e2e.ts` hold;
- it has been measured in the browser at 1280×800, 390×844 and 320×640 with the audit's probe;
- its as-built record (before and after numbers, screenshots, numbered departures) is in this proposal.

One PR per slice, or a stacked series as build-density did.

- **S0. No sideways scroll, measured.**
  - **The fixes:**
    - The "Also found" buttons wrap (`whitespace-normal`, `text-left`, auto height) and carry "Showing a group found replaces the pumps ticked.".
    - The "not on the chart (not on the chart (…))" wording is fixed.
  - **The tests:**
    - `noSidewaysScroll` also asserts the Results pane's scroller. It fails today in the condenser, so it is strengthened with the fix.
    - New `tests/pumps-layout.e2e.ts` holds the probe, adapted from the audit's `measure.mjs`, and records the before numbers.
  - **The record:** the before screenshots go to `docs/proposals/pumps-results-layout/`.
  - **Proof:** `utils/pump-group-others.test.ts`'s two exact sentences updated to the fixed sentence; the chart-image footer tests; the whole e2e suite.
- **S1. Pump chart** (`PumpsView`, `PumpChart`; markup and CSS; `chartNotes` untouched).
  - **Headings:** the h3 and the select named by it with its help; the visually hidden h3 "Results per pump".
  - **Reading:** toggle chips; the readout as pairs.
  - **The strip:** its always-present status, Cancel and retry on one line.
  - **Actions:** visible image reasons, and the caption as the toggles' description.
  - **The data region:** the case shown first, the 40 rem container grid, scroll shadows, "Speed (%)" and a list on phones.
  - **The notes:**
    - warnings first and marked, from a small pure helper over the same data, so no word and no footer changes;
    - the method sentence with its inline Trace;
    - "Design-check limits drawn" with Go to Checks.
  - **Other cases:** the h4 with the tag, the grid, the capped look, "(off in this case: no point drawn)", and the overlay status always present.
  - **Budget:** Show data table ≤ 300 px below the canvas.
  - **Tests:** the words-on-screen guard (§10) for `chartNotes`.
  - **Proof:** PumpChart, PumpChartChunk and PumpsView tests; design-checks, pump-chart, pump-chart-facts, pump-system, pump-control, scenarios, cancel and export e2e; chart-image tests unchanged.
- **S2. The card's shell, order and nav.** `PumpGroupChart` is split into section components (station, group chart, other cases, comparison), presentation only, with the same props, so its tests mount it unchanged. PumpsView's request effects are untouched.
  - **The card:** the closed card's line; the type scale; the h4 wrappers in the new order.
  - **The group chart:** its toolbar and `#data` moved under it.
  - **The nav:** the shared pill row, `aria-current`, the ⚠ marks and `scroll-padding-top`.
  - **The axe loop** fixed to open only closed summaries.
  - **Budgets:** the group canvas to its Show data table; the outline; one Tab stop; `location.hash` unchanged.
- **S3. Station and Group chart.**
  - **Members:** the grid, the suggestion line and "Other groups found".
  - **The station:** the answer before the group table; the group table's flag lines (with `flagTone`) and its list on phones.
  - **The group chart:**
    - the strip with Cancel beside its sentence (focus refs and `$effect.pre` kept);
    - the readout as pairs;
    - the legend two-up;
    - the duty checks marked and first;
    - "How to read this chart"; the methods' `.more-summary`.
  - **Other cases:** the h5, the switch first, its own status, the visible retry reason, Go to Running combinations, and the ring notes visible.
  - **The data region:** the duty sentence split.
  - **Budgets:** the station within 400 / 600 px; the longest run of notes; Tab stops to the group's data table.
  - **Tests:** the words-on-screen guard for `groupNoteLines`.
  - **Proof:** PumpGroupChart, PumpGroupView and PumpGroupOneOff tests; pump-groups e2e; the export's word-for-word tests unchanged.
- **S4. Add cases** (`PumpLineupsBlock`).
  - **The block:** the panel with its tag; the h4 at 14 px and its label at 12; the folded done state; Solve all's visible reason.
  - **New lines:** the id mapping and "Now ticked".
  - **D24 §7.11's order** is kept in the full form.
  - **Proof:** PumpLineupsBlock tests; pump-lineups and pump-groups e2e (the focus still on the block's Solve all after Add); axe with the stop order and the fold open.
- **S5. Running combinations.**
  - **New:** the lead, from a pure helper over `runningCombinations`.
  - **The extremes** grouped by pump (still the dl, same text).
  - **Order:** the shown case, then ring order.
  - **Lines and names:** sticky group lines; flag lines; names as trace buttons; no "Flags None" lines on phones; "Other cases' station duties" a list on phones.
  - **Budget:** the open card's height.
  - **Proof:** PumpGroupOneOff and PumpGroupChart tests; pump-groups e2e at both sizes.
- **S6. The owner's table rules.**
  - **S6a:** "The pumps in the group" becomes a ResultsTable (sort, Fields, Flagged only, a list below 640 px, its flag lines).
  - **S6b:** only on the owner's yes (§12, question 2).
- **S7. Data without scroll traps.**
  - In both data regions, each curve table becomes a disclosure "{caption} ({n} points)", full height when open, opened by default when the chart cannot be drawn.
  - Whether each chart's data table is shown is remembered per browser (try/catch).
  - **Budget:** scroll-region Tab stops ≤ 3.
- **S8. Cases and words** (touches the PNG footer).
  - **Markers:** the glyphs match the chart (✳, ▽), fixed by case while five other cases or fewer are drawn.
  - **Slots:** a case in which the viewed pump is off takes no slot ("Off in this case (nothing drawn): …").
  - **On the owner's yes:** the "(D13)" words (question 3) and the shared unticked cases (question 1).
  - **Proof:** chart-image tests; the export's word-for-word tests; `fixture.test.ts`; the API's `test_web_export_groups_fixture.py` run as a check.
- **Records, with each slice:**
  - the D17, D19, D21 and D24 "Designers' web defaults" paragraphs and the specs named in §6.4;
  - `ui-guide.md`: the section anatomy, the section nav that never touches the fragment, one strip per chart, and cost hints kept visible;
  - a `history.md` line naming `web/pumps-layout` or the PR;
  - `verified-state.md` by `scripts/record_history.py`;
  - `roadmap.md` trimmed.

## 10. Test impact

**No test is weakened.** Every pinned name, role, hook and word stays satisfiable, or moves with the same assertion. Scopes move only from a figure to the section that now holds the control, never wider. Where an element moves into a closed disclosure, the test gains an "open it" step first.

- **jsdom and Playwright on closed disclosures.** jest-dom's `toBeVisible` and Playwright both treat content inside a closed `<details>` as hidden, while `getByRole` may still find it. So each moved element gets the open step in both suites, and a help-on-focus hint gets an e2e step that it is hidden, then shown on focus. That is stronger than today, since jsdom has no CSS.
- **Estimate:** about 50 assertions in about 15 files follow a moved element, and about 30 tests are new. Each slice's PR lists every old assertion beside its new one, as `build-density.md` §11 item 22 did.

**Kept as they are** (the grafts in §11 were chosen partly for this):

- **Methods and Trace.** `figure.getByText(/System curve: the network/)` stays visible in design-checks, pump-chart, pump-chart-facts and export e2e, since the method sentence stays visible. "Trace of {pump}" keeps its role and name.
- **Pump chart.** Both charts' "Show data table" keep their name (34 uses across e2e and unit tests), "Cases on the chart" stays inside the figure, and "Operating points by case" keeps its name (`scenarios.e2e.ts:220–226`).
- **The extremes** stay a `<dl>` with the same text (`PumpGroupChart.svelte.test.ts:1369–1376`, `pump-groups.e2e.ts:632`, `PumpGroupOneOff.svelte.test.ts:906`).
- **Single elements and levels.** `card.locator('dl')` still finds one `<dl>` without scenarios (`pump-groups.e2e.ts:175, 226`), `card.getByRole('figure')` still finds one figure, and the heading "Add cases" stays at level 4.
- **Rings.** The ring list and the claim rules stay visible, so their tests are unchanged.

**Assertions that follow a moved element, by slice:**

- **S0.**
  - `noSidewaysScroll` (`pump-groups.e2e.ts:133`) also asserts the pane's scroller: stronger.
  - `pump-group-others.test.ts:304, 1287` expect the fixed sentence, exactly.
- **S1.**
  - `PumpChart.svelte.test.ts:677` finds the method paragraph by a class (`p.text-slate-600`) the tone change removes. It reads the same paragraph by a data hook, with the same equality to `request.notes.method`.
  - `:742` finds the readout by `div.space-y-1`; it moves to `data-pump-readout`, with the same texts.
  - Tests reading the data region's tables by position read them by their names.
- **S2.**
  - `pump-groups.e2e.ts:731` clicks every summary, which would close the self-opened ones. It opens only closed ones, as `:897` and `:1021` already do: stronger.
- **S3.**
  - The "Also found" clicks (7 uses) open "Other groups found" first when there are two.
  - The group table's Flags reads (the `rowOf` helper at `pump-groups.e2e.ts:66–75`; `PumpGroupChart.svelte.test.ts:422–437`) read the flag line under the pump's row: the same text, and "None" becomes the absence of a flag line.
  - `getByRole('status')` on the card (5 uses) is scoped to its section, since the card now has two regions; the texts are the same.
  - The tests of the axes, system and own-system-curve notes (about 7) open "How to read this chart" first.
  - Tests expecting the duty sentence as one paragraph expect the same two texts in two.
  - The hints' `toHaveAccessibleDescription` checks (`:929`, `:1191`) are unchanged.
- **S4.**
  - Tests that read the refused "Add cases" or the refusal after every case exists (`PumpLineupsBlock.svelte.test.ts:444, 645`; `PumpGroupChart.svelte.test.ts:1099`; the done states in pump-lineups and pump-groups e2e) open "Cases to add: …" first.
  - Solve all and the focus on it after Add are unchanged.
  - The two tests that assert no `<details>` under Each pump off (`:207`, `:673`) run with cases left to add, where the block has no fold; this is checked when S4 is built.
- **S5.**
  - Running combinations' group order (`PumpGroupChart.svelte.test.ts:1336`; `PumpGroupOneOff.svelte.test.ts`'s `groups[1]` and `groups[4]`) is re-indexed to ring order, with the same exact strings.
  - The Flags cell reads (`pump-groups.e2e.ts:630`; `PumpGroupChart.svelte.test.ts:1349, 1363`, `cells.at(-1)`) read the flag line following the pump's row, keeping `data-label="Flags"` and `toContainText('Warning')`.
- **S6.** About 10 to 16 group-table reads follow the ResultsTable's headings (sort buttons inside them, the same names) and its flag lines.
- **S7.** About 20 curve-table assertions open their table's disclosure first.
- **S8.** The chart-image tests on the marker set and the footer move to the new glyphs; the other words follow question 3 only.

**New tests:**

- **Budgets** (`tests/pumps-layout.e2e.ts`, at 1280×800, 390×844 and 320×640, on one-off, lineups with everything open and condenser after Add cases): every budget in §5.7.
- **The nav:**
  - one Tab stop, the arrows, Home and End;
  - `aria-current` follows the scroll;
  - a press focuses its heading under the nav, not covered;
  - the ⚠ marks;
  - `location.hash` unchanged.
- **Words on screen:** every `chartNotes` and `groupNoteLines` line appears on screen word for word, visible or inside a named disclosure. `DUTY_CLAIM_RULE`, `OTHER_CURVES_FRAME`, a duty check that disagrees or is not known, and the no-head and no-rise lines are visible by default.
- **Order:** "Cases on this chart" comes after its checkbox, in the DOM and on screen.
- **Pump chart:** the strip's status is present while idle and speaks on loading; the off-in-this-case note.
- **The card:** the capped look; the visible disabled reasons; the suggestion line; "Other groups found".
- **Add cases:** the fold and "Now ticked".
- **Running combinations:** the lead's counts.
- **Flags:** the flag text visible in both card tables, inside the box's visible rectangle at both sizes.
- **axe:** clean with every new disclosure open.

## 11. The three designs, and why this one

Three designers each drew a whole restructure from the measurements. Three judges scored them on six criteria out of 10; build risk is scored so that higher is safer.

| Design | Judge | Clarity | Consistency | Phone | Accessibility | Traceability | Build risk | Sum |
|---|---|---|---|---|---|---|---|---|
| **Four questions, in reading order** (the basis here) | 1 | 8 | 7 | 6.5 | 8 | 8 | 4 | 41.5 |
| | 2 | 8 | 7 | 7.5 | 8 | 8 | 5 | 43.5 |
| | 3 | 8 | 7.5 | 7 | 8 | 8 | 5 | 43.5 |
| **One section anatomy and a sticky section nav** | 1 | 8.5 | 7.5 | 8 | 8 | 7 | 5 | 44 |
| | 2 | 8 | 6.5 | 8 | 7.5 | 6.5 | 4 | 40.5 |
| | 3 | 8.5 | 5.5 | 8.5 | 8 | 7 | 4 | 41.5 |
| **Least change: one band order per chart, headed sections** | 1 | 6 | 7 | 5 | 7 | 8.5 | 8.5 | 42 |
| | 2 | 6 | 8.5 | 5.5 | 7 | 8.5 | 8 | 43.5 |
| | 3 | 6 | 8.5 | 6 | 7 | 8.5 | 8.5 | 44.5 |

**The pick.** Two of the three judges named **Four questions** the winner.

- **The sums.** They put Least change first (130, against 128.5 and 126), but most of its lead is build risk (25 against 14).
- **The owner's dimensions.** On clarity, phone, accessibility and traceability, Four questions leads (95, against 89 for the section nav and 80 for Least change).
- **The deciding reason.** Least change fixes the structure but not navigation, the owner's central complaint: the card shrinks only about 8 %, with no way through and the same two case lists on a phone's 18 screens.

**What Four questions brought:**

- the station's answer before setup;
- Add cases folded once done;
- a lead count of the invalid cases before the extremes;
- the cost hints kept visible;
- "Go to" buttons beside notes that point elsewhere;
- the suggestion and id lines;
- the pinned names kept.

**Grafted from the section-nav design** (all three judges asked for parts of it):

- the nav as one Tab stop with roving focus, `aria-current`, ⚠ marks and `scroll-padding-top`, and as the only sticky element;
- the plain section names that match the captions ("Pump chart", "Station", "Group chart", "Running combinations");
- the visible flag text after each badge;
- every card table as a list on phones without waiting for ResultsTable;
- "Now ticked: …" after an Add;
- Add cases as a framed panel tagged "Changes the project";
- the ring order in S5;
- "Speed (%)";
- the words-on-screen guard test.

**Grafted from Least change:**

- the flag line held to the visible width, ResultsTable's own pattern, with `flagTone`, in S3 and S5 rather than after S6;
- the method sentence and its Trace link kept visible;
- the ring list kept visible;
- "(off in this case: no point drawn)" as an early, image-neutral step;
- the before numbers and the budget test first.

**Not taken from the winner:**

- **Read blocks sticky to the pane's foot.** They would cover the canvas on a 620 px phone pane (WCAG 2.4.11).
- **The legend click switched off.** It is the built way to hide a design-check mark (`pump-chart-config.ts:211–212`, `:595`); syncing it with the chips is Later.
- **The same heading words over both case lists** ("Other cases on this chart"). They kept the confusion F8 measured, so each heading now names its chart.
- **The extremes as a term and value grid.** They stay the dl, grouped by pump.

**Not taken from the section-nav design:**

- **Renaming the pinned legends** "Cases on the chart" and "Cases on this chart" (`scenario-manager.md` §6.13, D24 §7.9) and "Show data table" to "Show data table (n tables)". That is 34 exact uses, and the count changes while overlays arrive.
- **The chips above the chart,** a departure from `pump-chart.md` §4.1.
- **Add cases moved to the card's end,** away from D24 §7.1's place above Running combinations.
- **The method sentence, the Trace link and the case lists behind closed disclosures.**
- **The "Operating point" sentence moved out of the data region,** the chart's long description.

## 12. Questions for the owner

1. **One choice of cases for both charts?**
   - **Today.** "Cases on the chart" (the pump chart) and "Cases on this chart" (the card) hold the same cases with different rules. The first is reset on a pump change and capped at 5 others; the second is page state, capped at 6.
   - **The proposal.** One set of unticked cases for the tab, as page state: unticking a case under either list unticks it under both. Each chart keeps its own cap, order and markers. The pump chart's list no longer resets when the pump changes.
   - **Recommended: yes.** A user who hides a case on one chart expects it hidden on the other (F8). It changes how D15's and D21's case choices persist, so it is yours to decide. It would land in S8.
2. **Running combinations as a sortable table (S6b)?**
   - **The proposal.** It becomes a ResultsTable: Flagged only and Fields in its grouped form. A sort turns it into one flat table with a Case column, and clearing the sort brings the case groups back.
   - **Recommended: yes.** It meets your 2026-10-31 rules (sort by any field, a Fields menu, a list on phones). It finds the worst case in one press (sort by NPSH margin), and it stays the card's longest block without it.
3. **May "(D13)" become plain words?**
   - **Where it appears.** "(D13)" is in the web's notes and Running combinations' station lines (six times in the condenser example). "(CLAUDE.md D13)" is in the server's methods text. Users cannot open either.
   - **Recommended: yes.** Use the words it stands for ("several steady states can exist; this is the one the solve found"). The web words change in S8, with the image footer through the same helpers. The server's methods words change on their own branch: an API change with no solved value and no `METHOD_VERSION` affected.
4. **Add the pump chart's labels to item 107?**
   - **What overlaps.** The pump chart's direct labels overlap near the duty: "Pump PB off" over "Delivery tank 5 m higher", "3 of 4 running" over "BEP", and a label cut at the right edge. Items 107 and 108 cover only the group chart's.
   - **Recommended: yes.** Add them to item 107, and settle every collision rule for both charts together. This proposal moves no label and settles neither item.

## 13. Later

- An HTML legend for the pump chart, with keyboard toggles synced to the chips; the in-canvas legend's click stays until then.
- The ring list split into one line per ring. That needs a parts helper for `groupNotes.others` in the same words and the same footer order.
- Links inside note sentences, which needs helpers that return tokens.
- Curve tables on one flow grid, so pump and system heads read on one row.
- The terms introduced once: operating point and station duty, head and rise, carrying flow and running.
- Collapsible h4 sections remembered per browser, if the structured card still reads long.
- The card remembered open per browser. It stays closed on each load (D21), since opening asks for the group curve and the group system curve, about 82 solves of the station.
