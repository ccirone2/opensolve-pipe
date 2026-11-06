# The Pumps tab below the pump chart: sections, one way through, every feature kept

**Status: Accepted by the owner (2026-11-05); S0 and S1 built (§15), S2 to S8 and A1 to build.** The owner's words: "Start the build. I accept the recommendations to the questions." §12 records each answer and the slice it lands in. Web on `web/pumps-layout` (S0) and `web/pumps-layout-chart` (S1, stacked on it), plus one small API branch, A1 (§9), for the server's words: no model or solver change, no solved value changed, `METHOD_VERSION` stays 1.6.0, `schemaVersion` stays 1, nothing new in the link, no new dependency. Every placement here is a designers' web default, reversible under D14; the four answers of §12 are the owner's. The audit (§2) measured and read main's content at `3da7bae` with the re-tick fix of `web/cases-on-chart-retick` (`untickedAfter`), which changes no layout. That fix has been on main since PR #265 (`2f5e1e3`). S0's record (§15) measures main at `2f5e1e3` against this branch, and S1's measures it against `web/pumps-layout-chart` at `88fafd2`. Revised the same day for an accessibility review and a design review, each finding checked against the code (§14 records where each landed), and again for the owner's answers, which cut the card's text further (S3's ring notes, S5's extremes) and settle S6b, S8 and A1. Follows [`ui-ux-refinement.md`](ui-ux-refinement.md) and [`build-density.md`](build-density.md): measure the running app, act, then hold the result in a test.

## 1. Scope

**The owner's request (2026-11-05), in the owner's words:** "i love all the features in Results under the Pumps tab, but everything from below the pump chart and down is very unrefined from a UI/UX perspective. it just looks patched together and needs to be structured in a way that the user can navigate and manipulate the features without getting confused by poor, unstructured formatting."

Read as: **keep every feature; restructure how they are presented, navigated and manipulated.** In scope is everything from the pump chart's canvas down, in `PumpsView.svelte`, `PumpChart.svelte`, `PumpGroupChart.svelte` and `PumpLineupsBlock.svelte` (`apps/web/src/lib/components/results/`): the chips, the readout, the notes, the system curve's states, the other cases, the data table and the image of the pump chart; and the whole Pumps together card, with its members, group chart, notes, tables, Read along the curves, Add cases, the other cases' station duties, the curve family, Running combinations and the extremes. Out of scope: the Results per pump table above (it gains only a visible heading, "Results per pump"), what the canvases draw (the label collisions are the owner's open items 107 and 108; the owner added the pump chart's to item 107, §12), and the server's words but one: A1 (§9) takes "(CLAUDE.md D13)" out of four server sentences.

**Already decided, not re-opened** (§8 lists each): GOALS §3, §4.2, §4.5, §4.6 and §4.7; D3, D10, D13, D15, D17, D19, D21 and D24 with their owner's answers; the pump chart's owner decision on the best efficiency point; the owner's table rules of 2026-10-31 (`build-density.md` §14 to §18).

**Aim.** The method of the precedents, progressive disclosure: the answer and the next action shown, the depth (traces, methods, tables) one step away, never removed. Concretely:

1. one section anatomy, repeated for both charts;
2. a heading for every part, and one sticky way through the tab;
3. every control beside what it changes, before the thing it reveals;
4. answers, warnings and flags visible, and marked;
5. reference text one step away, in a disclosure that says what it holds.

## 2. How this was found

The API (the e2e suite's app, `apps/api/tests/e2e_app.py`) and the web app on Vite's dev server were run locally and driven with Playwright (the e2e suite's Chromium) at 1280×800 and 390×844, in three states. The dev server's layout is the build's, but S0's `tests/pumps-layout.e2e.ts` records the before numbers again on the e2e build (`pnpm build && pnpm preview`), and the budgets are set from those.

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

The Keystroke-Level Model (Card, Moran & Newell 1980), with `build-density.md` §3.2's constants: M 1.35 s, P 1.1 s, a press 0.2 s, and a scroll counted as one P (a wheel or a flick) per pane height. "After" values are estimates from §5's layout, to be measured in each slice (§9). In a 454 px tab the nav shows about four of its seven buttons; it keeps the current one and the next in view (§5.4), so reaching a button two or more past the current one costs a sideways scroll, one more P.

| Action (condenser) | Before | Before (KLM) | After (estimate) | After (KLM) |
|---|---|---|---|---|
| Read the station's duty after opening the card, desktop | 5 scrolls (3,522 px into the card) | 6.85 s | on the first screen (about +300 px) | 1.35 s |
| From the group chart to its data table, desktop | 10 scrolls (+6,481 px), point, press | 13.65 s | 1 scroll (about +400 px), point, press | 3.75 s |
| The same, phone | 16 scrolls (+9,658 px), point, press | 20.25 s | 2 scrolls (about +700 px), point, press | 4.85 s |
| From the group chart to Add cases, desktop | 4 scrolls (+2,668 px), point, press | 7.05 s | the nav's "Add cases" button, the next after "Group chart" and so in view (point, press), then point, press | 3.95 s (measured in S2 and S4) |
| Find the smallest NPSH margin over the cases, desktop, from the group chart | 9 scrolls to the extremes (+5,791 px), then read 18 lines | 11.25 s and the reading | the nav scrolled sideways (P), its "Running combinations" button, then the extremes table's "Smallest NPSH margin" column: six values, one per pump, each on its cell's first line | 3.75 s and the reading (measured in S2 and S5; the condenser's table is 711 px in the mock, so its last rows may need one scroll more) |

## 3. What works well (keep it)

- **Every value is traceable** (GOALS §4.2): each pump's trace, both methods disclosures with their references, the server's own sentence under Details wherever the app rewords one, and the system curve's method sentence.
- **The screen and the image say the same thing.** One words function per chart (`chartNotes`, `groupNotes` and `groupNoteLines`) feeds the screen and the PNG footer, and the export's group words are checked word for word against the card's helpers. A layout change can move markup without the image or the workbook drifting.
- **Physics flagged by default** (GOALS §4.6): FlagIcon by severity, and a red icon on invalid values: with a visually hidden "physically invalid:" in Running combinations' cells, and with "physically invalid" in the extremes' words. (That icon is today the warning triangle drawn red, `Icon name="alert"`; S5 makes it the invalid octagon, §5.3.) Refusals are given in words with the members still drawn.
- **The requests are well behaved** (D10): one at a time, on demand, cancelled by a solve or a goal seek. Each has its Cancel and its retry, and the focus passes between them.
- **The readouts** are native range inputs whose value text carries the reading, with Escape and "Back to the duty". On the group chart that button hands the focus back to the slider as it goes; the pump chart's does not (F40).
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
| F25 | medium | Cases with no operating point take chart slots. "Pump P1 off" on P1's chart takes one of 5 and, with the other cases' system curves off, draws nothing, so three cases that would draw are disabled. (With those curves on, its system curve is drawn: `pump-chart-config.ts:476–490`.) | `PumpsView.svelte:226–258` | U-P12, X-P23 |
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
| F40 | low | The pump chart's "Back to the duty" removes itself when pressed and moves no focus, so the keyboard focus falls to the page. The group chart's moves it to its slider, and its test says so (`PumpGroupChart.svelte.test.ts:917–923`); the pump chart's test (`PumpChart.svelte.test.ts:753`) asserts nothing about focus. Found by the accessibility review. | `PumpChart.svelte:546–551` | A11Y-03 |

## 5. The recommended structure

### 5.1 One anatomy for both charts

Each chart is built the same way, top to bottom:

1. its **title** (the figcaption, which is also the image title);
2. the **canvas**;
3. the **reading controls**: the Show chips (pump chart), the slider and its readout;
4. one **request strip**: one line per request drawn on this chart, its state first and its own Cancel, Try again or Compute after it, then the lines about the curve's coverage (points without a head or a rise), plain;
5. the **legend** (the group chart; the pump chart's stays inside its canvas);
6. the **actions**: Show data table and Download image, with any lasting unavailable reason visible;
7. the **notes about the values**, always shown, the facts that qualify the reading and the checks first;
8. the **reference** disclosures, each naming what it holds;
9. the **data region**, which opens here, after the notes and the reference, so opening it never pushes a note or a check away from its chart; the toggle's `aria-controls` points at it;
10. the **other cases**, under their own heading: the switch first, then the list it reveals, its progress and its notes, with their reference ("How to read the rings") before the ring list on the group chart, since what it holds introduces the list ("The list below says, for each ring, which", §5.3).

The card adds two plain sections around its chart, **Station** before it and **Running combinations** after it. Between them sits **Add cases**, a framed panel, as the one part that changes the project. The group curve's request line heads Station rather than the group chart's strip, since the station's shares and losses wait for it too (§5.3).

### 5.2 Type and marks

- **Headings.**
  - h3: 16 px semibold.
  - h4: 14 px semibold, with a rule above.
  - h5: `.section-title`, 12 px small caps.
  - Legends and field labels inside a section: 12 px medium, so no label outranks its heading.
- **Answers:** 14 px with tabular figures. These are the station's values, the readouts and Running combinations' lead. The extremes table stays 12 px, as today's lines are, each value in medium weight on its cell's first line (§5.3, §5.7).
- **Notes:** 12 px in one tone (slate-700). Help and reference text is slate-600.
- **Marks** say only the severities the app already gives; none is new (GOALS §4.6):
  - **A physics flag** shows FlagIcon by its severity. Where a mark stands for one, it is `role="img"` named by the worst severity present: the red octagon named "Physically invalid", the amber alert named "Warning". ⚠ never stands for an invalid value.
  - **A request that failed:** ⬣ with its sentence. **A request running:** the spinner, `motion-safe:animate-spin`.
  - **A check that agrees:** ✓, `aria-hidden`, since its sentence says so. A check that does not agree, or is not known, gets no mark: it is not a flag, and its sentence says what it found.
  - **No mark on a fact.** The rising-head ranges are "named in a note as a fact … It is not a flag" (`pump-chart.md` §10, slice 2 as built), and the canvas's amber underlay already ties the note to the curve. The NPSHa note reads the drawn lines beyond the duty; it is not the solve's cavitation flag. The coverage lines ("n of 41 system-curve points have no head …") state what the request returned. None of them gets a mark.
  - **Placement.** A mark is its own element before its sentence's `<p>`, never inside it, so the sentence's text and its test anchors are unchanged.
  - **Design checks.** Their limits never get one: they are design practice, never a flag (D19).
- **Tags** that are not controls ("(shown)", "Changes the project") have no border and no pill radius: `rounded bg-slate-100 px-1.5 text-xs text-slate-700` for "(shown)", plain `text-xs text-slate-600` for "Changes the project". The rounded, bordered, 44 px shape is for controls only (F20).

### 5.3 Top to bottom, every element placed

The Pumps tabpanel (`PumpsView.svelte`'s `space-y-4` column), the same order at every width.

**Markup rules for every section** (the static mock drawn for this proposal follows them, and a slice built from it must too):

- A fieldset's `<legend>` is its first child, so the group keeps its name ("Cases on the chart" is pinned by `PumpsView.svelte.test.ts:97` and `scenarios.e2e.ts:220`; "Cases on this chart" by `PumpGroupChart.svelte.test.ts:1177` and `PumpGroupOneOff.svelte.test.ts:624`).
- A tag beside a heading is the heading's sibling, in a `div.flex.flex-wrap.items-center.gap-2`, never inside it; a region stays labelled by its heading alone.
- Every glyph (✓, ›, chevrons, case markers) is an `aria-hidden` element, the app's `Icon` where one exists, never CSS `::before` text, which Chromium puts into accessible names.
- Controls stay `.btn` (or a native control in a 44 px row) at `min-h-ctl`, 44 px: the chips, the strip's buttons, the summaries.
- Every chevron that turns gets `motion-reduce:transition-none`, as `SummaryView.svelte:266` and `FieldSections.svelte:130` have; today `PumpGroupChart.svelte:587, 973, 1000`, `PumpLineupsBlock.svelte:154` and `IssueDetail.svelte:16` lack it.
- A request's live line is an always-present `<span aria-live="polite" aria-atomic="true">`, the first child of its row, empty when idle; its button comes after it, outside it, described by it. It is not `role="status"`: an always-present status in the tab would make the pane-wide `resultsPane(page).getByRole('status')` match two elements (`tests/cancel.e2e.ts:55`, and `solveConverged` at `tests/support.ts:119`, which `pump-chart.e2e.ts:61` calls with the Pumps tab shown). `data-stop-status` already works this way (`PumpLineupsBlock.svelte:259`). No live line has an `aria-busy` ancestor: each figure's `aria-busy` moves to its canvas wrapper, the part that is redrawn.

**0. The section nav** (new; §5.4). Shown with the Pumps together card, that is with two or more pumps with results. It is the tabpanel's first child: static there, and pinned to the pane's top only once the pump canvas has scrolled out.

**1. Results per pump.** The ResultsTable and its note, unchanged, under a new **visible** h3 "Results per pump" (16 px semibold, tabindex −1, the nav's target), so the table gets the visible title every other section has. Its visually hidden caption stays.

**2. Pump chart** (`div.card`, `data-pump-chart`; shown when a pump has a result)

- **Header row.** The h3 "Pump chart" (tabindex −1). With more than one pump, the select sits beside it, labelled by the h3, so its name stays "Pump chart". Its sentence ("The pump and system curves of one pump at a time; each system curve is computed when its pump is shown.") stays a visible hint under the row: a choice starts a system curve, so it is a cost hint, kept visible like the other two; as floating help it would also cover the figcaption that names the pump just chosen. Below a 21 rem container the select drops under the heading.
- **The figure** (attributes unchanged but `aria-busy`, which moves to the canvas wrapper), with the figcaption "Pump and system curves: {pump}, {case}".
  - **In place of the canvas when needed:** the chunk-failure alert or "The chart cannot be drawn in this browser. The table below lists its points." Either forces the data region open and hides the chips, the slider and the actions, as today.
  - **The canvas** (`role="img"` with its summary and, now, `aria-busy`; the Chart.js legend inside it). Its legend click stays: it is how a design-check mark is hidden (`pump-chart-config.ts:211–212`).
  - **Reading.**
    - The group "Show": chips Efficiency, Shaft power, NPSH, Speed range and Design checks, drawn as toggle chips: `.btn` at 44 px, a fill and an `<Icon name="check">` (an `aria-hidden` svg, no text) when pressed, an outline when not; `aria-pressed`; remembered per browser as today. The chips' text stays "Efficiency", "Shaft power", … exactly (`PumpChart.svelte.test.ts:716–720`).
    - Then "Read at flow" with "Back to the duty". Pressing the button removes it, so the focus moves to the slider, as on the group chart: the slider is bound (`bind:this={readSlider}`) and the handler is `() => { cursor = null; void tick().then(() => readSlider?.focus()); }` (F40). Escape stays.
    - Then the readout: one `<p data-pump-readout>`, not live, "At the duty 21.58 L/s: Pump head 40.33 m, System head 40.34 m, …". Each pair is an inline `whitespace-nowrap` span "label value unit" at 14 px and the ", " separators are visually hidden, so its text is unchanged and `pump-chart.e2e.ts:30–44`, which find it as a `<p>` and read it with a regex, stay as they are.
    - This is the order `pump-chart.md` §4.1 gives.
  - **The strip** (nothing visible when idle), one row per line:
    - **Pump state.** First, the pump note: "This pump is off: …" or "This pump is held at zero flow by its check …" (plain).
    - **The system curve's line** (`{id}-curve-state`), with its button after it:
      - spinner "Computing the system curve for this solve…" [Cancel] (named "Cancel the system curve");
      - ⬣ "The system curve could not be computed: {message}" [Try again];
      - "The system curve has not been computed for this solve." or "…was not computed: you cancelled it." (and the goal-seek and new-solve variants), with [Compute the system curve].
    - **Coverage.** "No point of the system curve has a head …" or "N of 41 system-curve points have no head: …", a plain `<p>` after the line, no mark (§5.2).
    - **Focus.** The Cancel to Try again or Compute handover (`PumpChart.svelte:353–370`, with the figure as fallback) is unchanged.
  - **Actions** (one line, wrapping at 270 px; `export.md` §5.5).
    - [Show data table] or [Hide data table]: same visible words, `aria-expanded`, `aria-controls`. The name gains a visually hidden suffix, `Show data table<span class="sr-only"> of the pump chart</span>`, so the two charts' buttons differ in screen-reader lists, rotors and voice control's numbering (F18). WCAG 2.5.3 holds: the visible words start the name.
    - [⤓ Download image]: same name, `data-chart-image` and reasons. A lasting reason (the image's own `unavailable`) shows beside it as 12 px text, the element its `aria-describedby` already points to. The passing ones ("Wait until the system curve is computed, or cancel it.", "The chart is being drawn.") stay visually hidden and in its `title`: the strip already shows the request, and `drawn` is reset on every rebuild (`PumpChart.svelte:391`, `:439–441`), so a visible reason would flash and move the line on every chip, untick or case change.
  - **Notes about the values** (always shown, words from `chartNotes`, unchanged), in this order:
    - each rising-head range, and "NPSHa falls below NPSHr at about … the pump would cavitate beyond that flow.", first and unmarked (§5.2);
    - the best efficiency point or none, the shutoff head and the speed range;
    - the panels' notes;
    - "Dashed: the pump curve extrapolated beyond its data …";
    - then the method sentence, visible: "System curve: the network of this solve, solved again … minus the EGL at the suction." It ends with "Trace of {pump}" as an inline link: a button styled as a link, same name, no 44 px block, under WCAG 2.5.8's inline exception, as the refusals' element names already are (D10: "its method note links the pump's trace").
    - With the Design checks chip on: a small label "Design-check limits drawn", each limit note without a mark, and the closing sentence, followed by [Go to Checks]. That button switches the Results view to Checks and focuses its tab.
  - **The data region** (when shown, or forced; after the notes, §5.1). The case shown first:
    - "Operating point: x L/s at y m" or "Held at zero flow: …" moves to its top: today it follows "Operating points by case" and the other cases' system curves (`PumpChart.svelte:743–850`). The table is the chart's long description (`pump-chart.md` §4.4).
    - "Operating points by case" (Case, Flow, Head, Speed (%), State; bare numbers under "Speed (%)"; a list below 640 px).
    - The grid of the shown case's tables, two-up only from a 40 rem container: "Pump curve at …", "System curve" (with NPSHa, and Why no head with its Details), the efficiency, shaft power, NPSHr and speed-range curves.
    - Last, each other case's "System curve, {case}".
    - Every box gets `scroll-shadow-x`, and is a Tab stop only while it overflows (§5.7). From S7 each curve table is its own disclosure, "{caption} ({n} points)", full height when open, and open by default when its Why no head column has entries, so the reasons the chart's note points to ("the data table says why", `pump-chart.ts:894`) stay one press away (D10's owner rule).
  - **h4 "Other cases on the pump chart"** (with scenarios and another case with a result for this pump; inside the figure, so every figure-scoped test still finds it):
    - The fieldset "Cases on the chart", its legend the first child. "{case} (shown)" is the first item of the case grid, a tag (same words; not a 44 px row with no box).
    - One 44 px checkbox per other case: the marker in a fixed-width column, the name, " (out of date)". They sit in an auto-fill grid (13 rem minimum: two columns in a 480 px pane, one on a phone).
    - A case in which this pump is off (`result.status === 'off'`) says so beside its box, outside the label: "(off in this case: no operating point)". The note's id joins the box's `aria-describedby` (with the cap's id when both apply), so a screen-reader user who ticks it hears that it draws no point. A pump held at zero flow has its point drawn, so it gets no note. From S8 an off case takes no slot while the other cases' system curves are off (§9).
    - Capped boxes: the checkbox greyed (`opacity-45` on the input), `cursor-not-allowed` on the row, and the name kept at slate-600 (7.6:1), since it is what the user reads to decide which case to untick. They stay focusable, `aria-disabled`, and described by the visible "At most 6 cases at once.".
    - Then the checkbox "Also show the other cases' system curves", with its cost sentence **kept visible**: on touch, focus comes only with the tap that starts about 41 solves.
    - Then its line, "Computing system curves: 1 of 3…", with [Cancel] after it (named "Cancel the other cases' system curves").
- **"Back to the sections"** (while the nav is shown): a button visually hidden until focused, after the card's last control. It focuses the nav's current button.

**3. Pumps together** (`section.card`, `data-pumps-together`, a region named by its heading; two or more pumps with results; closed by default, D21)

- **The h3** holding the toggle button "Pumps together", with "(members)" while closed: kept, a recorded departure (§6.4 item 13). The nav's "Pumps together" button focuses this toggle, not the h3: its name starts "Pumps together" and it carries `aria-expanded`.
  - While closed, a second, muted line describes the button (`aria-describedby`, so its name still starts "Pumps together"): "The station's duty, the group curve, each pump's share and cases with fewer pumps running", plus "; Running combinations" with scenarios.
- **Members.**
  - The fieldset "Pumps in the group" as a grid (13 rem minimum; names wrap; the slot symbol's column reserved, so a label never moves on tick).
  - "At most 6 pumps in a group." when capped.
  - "The calculation server finds the part of the network …" stays a visible hint and becomes the fieldset's description: new `aria-describedby` on the fieldset, which has none today (`PumpGroupChart.svelte:596–632`).
  - While the members are the default suggestion: "Suggested for {pump}, the pump on the pump chart above; tick pumps to choose your own."
  - The other suggestions:
    - one: its "Also found: …" button, wrapping (`whitespace-normal`, left-aligned);
    - two or more: a disclosure "Other groups found: {n}" holding them;
    - either way described by "Showing a group found replaces the pumps ticked."
- **When the card has no values:** the unavailable sentence (not converged, not the latest, Solve all stopped, the latest solve failed) replaces everything below. With no member ticked: "Tick the pumps to see together." No section below the members is drawn then, so the nav has none of their buttons (§5.4).
- **h4 "Station"** (tabindex −1). Its answer first:
  - **The group curve's line** (`{id}-curve-state`), moved here from the figure because the station's shares and losses wait for it as the chart does, with its button after it: spinner "Computing the group curve…" [Cancel the group curve] · ⬣ "…" [Try again] · cancelled or not computed [Compute the group curve]. While it is pending, "The share of each pump and its loss on the way come with the group curve." follows it. The focus handovers (`PumpGroupChart.svelte:415–454`) are unchanged.
  - **The refusal**, when refused, visible (`data-group-refusal`): the bold sentence and the list "Why they do not form a station" or "Why the group curve is not defined", with element names as buttons and each "Details".
  - **The dl "The station"** at 14 px with the values in bold: "Station flow, into the station at {S}", "Rise from {S} to {D}", and in series "Lost in the piping between the pumps". It is the only `<dl>` on the card, now with scenarios too, since the extremes become a table (S5).
  - **The region and table "The pumps in the group[, {case}]"** (`scroll-shadow-x`; a size container, §5.5).
    - Columns as today except the last Flags column. Each flagged row is followed by a **flag line**, ResultsTable's own row-notes pattern (`ResultsTable.svelte:470–474`): sticky to the box's visible width (`w-[100cqw]`), `data-row-notes`, `data-label="Flags"`.
    - The line starts with a visually hidden "{pump}, flags:", so table navigation, which reads the one-cell row without its pump, names it. Then each flag: a tinted pill with only its icon and severity word (no visually hidden copy, no `title`), followed by **its text, visible** at 12 px. The sentence is read once.
    - The tints come from a small `flagTone(severity)` beside `SEVERITY_LABELS`, since FlagBadge reads the workspace and the card's unit tests mount none.
    - The sticky Pump names wrap at 12 rem.
    - Below 640 px the table reads as a list (Running combinations' classes, explicit roles kept), with the flag line under the pump's name.
- **h4 "Group chart"** (tabindex −1).
  - **The figure** (attributes unchanged but `aria-busy`, moved to the canvas wrapper and set while any of its curves loads), with the figcaption "{members} in parallel|in series[, {case}][ (out of date)]".
  - **In place of the canvas when needed:** the alert or the cannot-be-drawn note. Otherwise the canvas (`groupSummary`).
  - **Reading.** "Read along the curves" with "Back to the duty" and Escape. The readout (`data-group-readout`, same text) is 14 px pump and value pairs, in two columns from a 26 rem container and one pair per line on a phone. The pairs come from a new `parts` on `GroupReadoutSample` whose joining equals its `text` (tested), with visually hidden ", " separators, so `pump-groups.e2e.ts:362`'s exact text still holds. Its hint "Steps over the group curve's samples, …" stays a visible hint after the readout, as today, and the slider's description: as floating help it would cover the readout for as long as the slider has focus, and Escape, which would dismiss it (WCAG 1.4.13), already means "Back to the duty".
  - **The strip**, one row per line:
    - the group system curve's line (`{id}-system-state`) with its button after it: [Cancel the group system curve] · [Try the group system curve again] · [Compute the group system curve];
    - the coverage lines, plain `<p>`s (texts unchanged): "n of m group-curve points have no flow …", "n of m group-system-curve points have no rise …", "No group curve for this case: …", "No group system curve: …"; "Tick two pumps or more to compute their group curve.".
    - The focus handovers are unchanged.
  - **The legend** ("Legend", entries unchanged; `pump-groups.e2e.ts` reads them at :266, :294, :475, :638, :727, :889 and :960): the symbol entries (members, rings) two-up from an 18 rem container, the line entries one per row, so on a phone it is no taller than its canvas (F27; §5.7).
  - **Actions:** [Show data table] (named "Show data table of the group chart" by the same visually hidden suffix) and [⤓ Download image] (name, `data-chart-image` and reasons unchanged; a lasting reason visible, the passing ones as on the pump chart, `PumpGroupChart.svelte:475, 532–533`).
  - **Notes about the values** (words from `groupNotes`, unchanged), in this order:
    - the duty check (with its Details and "Several steady states can exist …" when it disagrees): ✓ when it agrees, no mark otherwise;
    - the system duty check (with its Details), the same way;
    - the frame ("Pump curves and points are at each pump's flanges. … At the duty Pump P1 loses 1.931 m, …");
    - the member notes;
    - the dashed note.
    - Each Details' summary gains a visually hidden subject, `Details<span class="sr-only"> of the duty check</span>`, "… of the system duty check", and so on, through an optional `subject` on IssueDetail; its other callers (ResultsPanel, GoalSeekResult) are unchanged.
  - **Reference**, three native disclosures with `.more-summary`, closed:
    - "How to read this chart: the axes, the group system curve, each pump's own system curve" holds the axes note, the system note and the own-system-curves note, with [Go to the pump chart];
    - "How the group curve is computed" (or "How this curve is computed", as today);
    - "How the group system curve is computed".
  - **The data region** (`#data`, after the reference, §5.1), in this order:
    1. "Each pump's point (flow through it)";
    2. the duty sentence split into two paragraphs, each with its own Details: "● Group duty (station's flow): …; Duty check: …" and "System duty check: …";
    3. "Group curve (station's flow at each rise)";
    4. "Group system curve (…)";
    5. "Other cases' station duties" (a list below 640 px), which today comes before the group-curve tables (`PumpGroupChart.svelte:1424–1572` before `:1573–1674`);
    6. "Other cases' group curves (…)" after it (`pump-lineups.md` §9.6).
  - **h5 "Other cases on the group chart"** (with scenarios and a station shown):
    - **The switch, first:** "Also show the other cases' station duties", with its cost sentence kept visible.
    - **While it is off:** the one line "Other cases' station duties are not on the chart: tick “Also show …” to compute them (n other cases with results)."
    - **While it is on:** under it, the fieldset "Cases on this chart", its legend the first child:
      - "{case} (shown)" as a tag, the grid's first item;
      - checkboxes "○ n · {name} (out of date)", the ring and number in a reserved column after the box (2.5 rem in the mock), in `lineupChartPriority` order;
      - capped boxes as on the pump chart, with "At most 6 other cases at once.".
    - **Progress:** its line (`{id}-others-state`), "Computing the other cases' station duties: k of n…", with [Cancel] after it ("Cancel the other cases' station duties").
    - **When some were not computed:** "Not every other case's station duty was computed: see Running combinations." with [Compute them again] (a lasting reason visible) and [Go to Running combinations].
    - **The ring notes, cut** (the owner's answer 1, §12). Today they are one run of up to six `<p>`s (`PumpGroupChart.svelte:957–960`) from `otherNotes` (`utils/pump-group-chart.ts:1337–1421`): the frame paragraph, the clip note, `DUTY_CLAIM_RULE`, the ring list, "Not on the chart: …" and the left-out count. In the lineups mock that run is 6 paragraphs, 568 words and 660 px at 480 px (§5.7). They split by what each does.
      - **Visible, since they qualify this chart's reading:**
        - the clip note, "Other cases' group curves are cut at the chart's right edge, …; the group system curve is cut at the top, …" (`clipNote`, `:1292–1304`): what is drawn is not every point;
        - the ring list, one line per ring (below);
        - "Not on the chart: …" (`:1410–1417`; its doubled words fixed in S0): which cases have no ring, and why;
        - "Labels of n curves are left out for space; the data table lists every curve." (`labelsLeftOutNote`, `:1307–1311`): some drawn curves carry no label.
      - **One step away, in a closed native disclosure** with `.more-summary`, "How to read the rings":
        - the frame paragraph (`:1361–1394`), in whichever of its four forms applies: what a ring is (the station's flow and rise, not a pump's point), what that flow and rise are in parallel or in series, where each pump's own values are, and which group curve a ring lies on (`OTHER_CURVES_FRAME` while the family is drawn, `:1284–1285`; the other three forms at `:1388`, `:1390` and `:1391`);
        - `DUTY_CLAIM_RULE` (`:130–131`), while a group system curve is drawn (`:1398`): when a ring is called a point of the group system curve shown.
        - **Its summary** says what it holds: "How to read the rings: what a ring is, which curve it lies on" while it holds the frame alone, and "How to read the rings: what a ring is, which curve it lies on, when it is called a point of the group system curve" while it holds the rule too. The longer is 114 characters: 2 lines (44 px) at 480 px, 3 (60 px) at 366 px and 4 (80 px) at 288 px in the mock.
        - It is drawn only while a ring is on the chart, and the frame exists exactly then: a ring needs a station (the card's `others` are empty without one, `PumpGroupChart.svelte:290–292`, the same station `otherNotes` is given), so the frame's condition, `cases.length && station` (`:1361`), holds whenever a ring does. The rule needs a drawn group system curve as well (`:1398`), whose points come only with a duty (`services/pump_groups.py:1776–1777`). So the disclosure holds the frame alone or the frame and the rule, never the rule alone, and those are its two summaries.
        - It never opens itself: it holds no warning and nothing the user set (ui-guide).
        - Each ring's own claim stays on its visible line ("Yes: the same rest of the network", "Not said: …"), so the answer for a ring never needs the disclosure; only the rule behind the answer does.
        - The PRV or PSV form says "the station has no group curve, so none is drawn here"; the Station section's refusal says it visibly too ("Why the group curve is not defined", §5.3 Station).
      - **On screen, in this order:**
        1. the clip note;
        2. "How to read the rings", closed;
        3. the ring list's lead and its `<ul>`;
        4. "Not on the chart: …";
        5. the left-out count.
      - **Why the disclosure comes before the list.** The frame's family form ends "The list below says, for each ring, which." (`OTHER_CURVES_FRAME`), kept word for word (§6.3), so the disclosure must come before the list for that sentence to be true when it is opened. The summary's last clause, "when it is called a point of the group system curve", then comes before the first "Yes: the same rest of the network", the answer to it, as the rule comes before the list in today's notes (`otherNotes`: frame, clip, rule, list, `:1361–1409`). The list has no control, so the Tab order is unchanged (§7).
      - **The ring list, one line per ring.**
        - A `<p>` lead, "Other cases on the chart (slate rings, numbered):", whose id names a `<ul>` (`aria-labelledby`). The list's name is the lead, so it is told apart from the "Legend" list.
        - One `<li>` per ring number, in number order. Its text is exactly that ring's entry in today's sentence (`:1399–1409`), for example "1 · 3 of 4 running (Pump P4 off), 77.28 L/s at a rise of 35.21 m: Yes: the same rest of the network; group curve: drawn (3 running): it crosses the group system curve at the ring". The "; " between entries and the closing "." are not drawn: the items separate the entries.
        - **Its look.** The ring glyph (`OTHER_SYMBOL`, ○, in `GROUP_OTHER` slate, `aria-hidden`) and the number "1 ·" sit in a reserved 2.25 rem column, as S3 reserves one for them in the case list ("Cases on this chart", above; today both are inline in the label, `PumpGroupChart.svelte:770–774`), so every line's words start at one edge. Then the case's name in medium weight (slate-900), the line's lead; then ", {flow} at a rise of {rise}: {claim}[; group curve: {words}]" in the regular weight. All 12 px, slate-700. A space follows the number column, so the item's text without its `aria-hidden` glyph is the entry, word for word.
        - Measured in the mock: a ring's line wraps to 3 text lines (48 px) at 480 px, 4 (64 px) at 366 px and 5 or 6 (80 to 96 px) at 288 px.
      - **The parts helper.** A new pure `otherNoteParts` gives the same notes as named parts: `off` (the one line while the duties are not asked for), `frame`, `clip`, `claim`, `rings` (`{ lead, items }`, each item `{ number, name, at, words, text }` with `text` = `${number} · ${name}, ${at}: ${words}`), `notOn` and `leftOut`. `otherNotes` becomes `otherNoteLines(otherNoteParts(…))`, which joins them in today's order, the ring list as `${lead} ${items.map((i) => i.text).join('; ')}.` (tested). So `groupNotes(…).others` and `groupNoteLines` keep every word, and the image's footer keeps the frame, the rule and the ring list as one sentence: the owner's "The downloaded image keeps its current words". `GroupNotes` gains `otherParts`, which only the screen reads. The chart's accessible name (`groupSummary`, `:1694–1702`) has its own ring words, each claim in brackets, and is not touched.
- **h4 "Add cases"** (`PumpLineupsBlock`; the region "Add cases", `data-add-cases`; while a station is shown).
  - **The panel.** It is framed and tinted (a border, `bg-slate-50`). Its header is a `div.flex.flex-wrap.items-center.gap-2` holding the h4 and, as a sibling, the plain tag "Changes the project"; the region keeps `aria-labelledby` on the h4 alone, so its name stays "Add cases" (`PumpLineupsBlock.svelte.test.ts:111`).
  - **While a gate holds:** only its sentence, Solve all (gates 4 to 6) and "Pump lineups table…" (D24 §7.2), as today.
  - **Otherwise, one structure in every state.** No control moves from one branch of the markup to another, so a control in use keeps the focus. D24 §7.11's order is kept:
    1. the segments "Cases to add" (label 12 px), outside any disclosure;
    2. one native disclosure, `data-lineup-plan`, holding About, the interchangeability sentence, the stop order's own disclosure (now `data-stop-order`), the "Cases:" preview (with its "already a scenario (S1)" lines), the frame line, the names line and, new, "In the names, P6 is Condenser water pump CWP-6, …" (only when some member's name does not contain its id). Its summary says what it holds: "The plan: {n} cases {by number running | with each pump off}: {k} to add", or ": all {n} made", or ": {e} made, {b} not made (the base case's state)";
    3. one row: [Add n cases] (`aria-disabled` with its refusal when nothing is left to add) and the single [▶ Solve all (n)], `bind:this={solveAllButton}`, in every state. Solve all appears exactly once in the block;
    4. the refusal, visible as today. With every planned case made it is D24's own line and names them ("Every case by number running already exists: «…», «…» and «…»."), so no second line repeats it;
    5. Solve all's lasting reason, visible ("Every case's results are current.");
    6. "Pump lineups table…".
  - **The fold.** The plan disclosure is drawn closed only when every planned case exists, `plan.add.length === 0 && plan.existing.length > 0` (an add refused for the cap of 20 still has cases to add, so it never folds; a plan of base-state cases only is not done either). It is drawn open otherwise, opens itself whenever cases come to remain (another preset, a scenario deleted), and is never closed by code: after the user's own Add it stays as the user left it (ui-guide: a disclosure never closes itself). Folded, the block is the segments, the plan's summary, the row, the refusal and the table button.
  - **After an Add** that ticked it: the visible line "Now ticked: “Also show the other cases' station duties” (Group chart)." The same sentence is written into `data-stop-status`, the block's polite live line, since the focus moves to the block's Solve all (D24 §7.8) and would not pass the line.
- **h4 "Running combinations"** (tabindex −1; with scenarios and a station shown).
  - **The lead** (14 px): "{n} cases: {v} with current results ({k | none} physically invalid, {w | none} with warnings), {m | none} out of date, {f | none} without results."
    - v counts the cases with current results, m those whose results are out of date, f those with none (failed, not reached, not solved): v + m + f = n.
    - k and w count over the v current cases, as the extremes do: k the cases where a member has a flag of severity invalid, w those where a member has one of severity warning and none invalid. A design check is never a warning (D19); an info flag counts in neither.
    - Its mark is the worst severity among them: the red octagon named "Physically invalid", or the amber alert named "Warning"; none when k and w are both none.
    - For the lineups fixture: "9 cases: 9 with current results (none physically invalid, 1 with warnings), none out of date, none without results."
  - **h5 "Extremes over these cases (current results)"**, now nested under the section it summarises. Under it the extremes are **a table, one row per pump and one column per measure** (the owner's answer 1, §12).
    - **What it holds.** Today's dl (`PumpGroupChart.svelte:1295–1317`) holds three measures per member, from `combinationExtremes` (`utils/pump-group-one-off.ts:799–861`, its measures at `:813–817`): largest flow, largest shaft power and smallest NPSH margin. It holds no other measure. So the table has four columns: "Pump", "Largest flow", "Largest shaft power" and "Smallest NPSH margin". Its rows are the members in component order, as today (`:807–810`), each named as today's term names it ("Booster pump (PA)" where two share a name, `memberLabels`).
    - **Each cell** holds today's dd words for its pump and measure, exactly: the value ("40.75 L/s"), then "in {case}", the qualifiers "; beyond its curve data" and "; physically invalid" where they apply, and the coverage "(over k of n cases; no value in m)".
      - The value is on the cell's first line in medium weight (slate-900); the rest follows under it, 12 px, slate-600.
      - Where that case has an invalid flag for that pump, the red octagon comes before the value: `<FlagIcon severity="invalid" class="inline size-3.5" />` (`aria-hidden`, as every `Icon` is), in place of today's red `alert` (`:1304–1307`), which is the warning triangle (`Icon.svelte:86–88`; the octagon is `Icon.svelte:89–92`), as §5.2 requires. The words keep "physically invalid". Today's dd has no sr-only "physically invalid:"; that is in Running combinations' cells (`PumpGroupChart.svelte:1258–1260`), which keep it and whose red `alert` (`:1257`) becomes the same octagon in S5.
      - "no case gives one" fills its cell alone, with no value line.
    - **Markup, as the card's other tables:**
      - a box with `overflow-x-auto scroll-shadow-x` and an inline-size container (`@container`), with no `tabindex` in S5: from 26 rem it does not overflow (the mock: no sideways scroll at 454 or 416 px, with the fixtures' names and with a 40-character unbroken name), and S7's measured rule (a Tab stop only while a box overflows) then covers it, since today's boxes take a `tabindex` whatever their width and `utils/scroll-focus.ts` measures height only;
      - `<table role="table">` with explicit roles throughout, Running combinations' pattern (`:1153–1161`), so the list form keeps its semantics;
      - `<caption class="sr-only">Extremes over these cases</caption>`, today's `aria-label` words, so the table's name is the dl's; the visible h5 heads it;
      - a header row of `<th scope="col">`; each row's pump a `<th scope="row">`, sticky at the left (`sticky left-0`, white, a right border), wrapping at 12 rem (`max-w-48`) as the group table's names do, with `overflow-wrap: break-word` (Tailwind's `wrap-break-word`), so an unbroken name wraps inside its 12 rem rather than running over the next column. Measured in the mock, the fixtures' columns and heights are unchanged by it at every width. `overflow-wrap: anywhere` was tried and dropped: it lowers the column's min-content width, so the condenser's pump column narrows from 88 to 64 px at 454 px and breaks "Condenser" inside the word;
      - each `<td>` with `data-label` set to its column's header, as Running combinations' cells have.
    - **The list below 26 rem** of the box's width (the readouts' breakpoint, §5.5): the same `<table>` restyled as a block per pump headed by its name in semibold, then one line per measure, its header drawn from the cell's `data-label` as `::before` content (`@max-[26rem]:before:content-[attr(data-label)]`, slate-600), Running combinations' pattern (`PumpGroupChart.svelte:1254`), never an element, so the cell's text (`textContent`, what `toHaveText` reads) is today's words at every width, and the cell's words after it on the same line. It is a label, not a glyph, so the markup rules' ban on `::before` text does not apply; Chromium puts it into the cell's accessible name on a phone, as it does for Running combinations' cells today. The header row is visually hidden (`@max-[26rem]:sr-only`, as Running combinations' `thead` is `max-sm:sr-only`); the roles stay. At the default desktop split the box is 454 px wide, so it is a table; on a phone (340 px) and at 320 px (262 px) it is a list.
    - **Why 26 rem, measured in the mock** (the condenser's six pumps): the table is 711 px at 454 px and 807 px at 416 px, the list 706 and 770 px there. At 340 px the table would be 983 px against the list's 834, with its columns 81 to 90 px wide. So from 26 rem the table is within 37 px of the list, and below it 149 px taller.
    - **Its height against today's dl, measured.** The mock's copy of today's dl reproduces the app's: 662 px against the 658 measured (condenser, 454 px; §5.7).
      - In the condenser the table is **taller**: 711 px, against 662 for today's dl and 670 for the dl grouped by pump that the proposal had. Its measure columns are 110 to 131 px wide, so each cell's case and coverage wrap to as many as 6 lines under the value, and the rows are 89 to 121 px.
      - In the lineups project (four pumps) it is **shorter**: 387 px, against 394 and 442.
      - It is still the better read for what the extremes are for. The six smallest NPSH margins (−4.934 to 2.04 m) are one column, each on its cell's first line; the dl spreads them over lines 3, 6, 9, 12, 15 and 18 of 18.
      - The value on a line of its own costs 16 px over the same words run on (695 px in the condenser), and keeps every value at its cell's top edge. That is the form chosen.
    - Then "Not counted (out of date): …", as today.
  - **The region and table "Running combinations"** (`data-running-combinations`; its caption visually hidden beside the h4, still its name; `scroll-shadow-x`; a size container, §5.5).
    - **Order:** the case shown, then the other cases with values in `lineupChartPriority` order (PumpsView's `chartOrdered`, `PumpsView.svelte:450–455`), then the cases without values in case order. A case's place does not depend on whether it is ticked under "Cases on this chart" or on whether "Also show …" is on, so neither reorders the table. "· ring n" stays a label.
    - **Group heading lines:** "{name} (shown)(out of date) · ring n", the lineup line and the station line, each sticky to the box's visible width, so they wrap in view.
    - **Pump names** become trace buttons **only in the shown case's group** (`group.shown`). A trace opens for the case shown (`ws.inspect` takes no case, `workspace.svelte.ts:1137`; `ResultsPanel.svelte:506`), so a button in another case's group would show the shown case's trace beside that case's values (GOALS §4.2, D10, D15). Other groups keep plain row headers; a case-aware trace is Later (§13).
    - **Flags:** a flag line under a flagged pump's row, as in the group table, keeping `data-label="Flags"`.
    - **Invalid and stale:** invalid cells marked, stale groups amber.
    - **Phones:** a list below 640 px with no "Flags None" line ("None" stays sr-only).
- **"Back to the sections"**, visually hidden until focused, after the card's last control.

Nothing comes after the card.

### 5.4 The section nav

The tab gets one way through, built on the ui-guide's sideways row.

- **Markup.** `<nav aria-label="Pumps view sections">` holds a visible lead word, "Go to", and `<div role="toolbar" aria-labelledby="{lead}" aria-orientation="horizontal">` with one button per section. A toolbar, unlike a plain row of buttons, tells keyboard and screen-reader users that the arrow keys move between its buttons (the APG toolbar pattern).
- **Look.** It sits under the Results view row, a `tablist` of filled, rounded pills (`ResultsPanel.svelte:963–990`), and must not look like it: quiet `rounded-md` buttons with no fill, the current one marked by a 2 px blue-700 underline and semibold, never filled.
- **Size.** Buttons at `min-h-ctl` (44 px), `px-2`, 14 px. The scrolling element has `py-1`, so the focus ring (2 px at a 2 px offset) is never clipped (see "One shared component"), with a 1 px rule under the nav: about 53 px at the default text size, all in rem, so it grows with text zoom.
- **Place.** The tabpanel's first child, above Results per pump, static there. It is pinned (`sticky -top-4 z-[35]`, white) only while both of these hold:
  - the pump chart's canvas (or what stands in its place) has scrolled out above the scroller's top, seen by an IntersectionObserver. While the pump chart is in view the nav is not over it, so at the default desktop split the whole 624 px canvas still fits the 666 px pane (F12);
  - the nav takes at most 15 % of the scroller's `clientHeight`, the ui-guide's chrome rule: about 8 % of the 666 px desktop pane and 8.5 % of a 620 px phone pane. A landscape phone (844×390, a pane of about 280 px, so about 19 %) and the `short:` variant (320×256 at 400 % zoom, where the workspace scrolls as one page, `Workspace.svelte:204`) keep it static.
  - `-top-4` cancels the scroller's `py-4` (`ResultsPanel.svelte:683`), as ResultsTable's Fields sheet uses `-top-2` in its `p-2` (`ResultsTable.svelte:303, 314`); with `top-0` it would stick 16 px low and content would scroll visibly above it. `z-[35]` puts it above ResultsTable's sticky header cells (z-20 and z-30, `ResultsTable.svelte:379, 390`) and the group tables' row headers (z-10, `PumpGroupChart.svelte:1046, 1075`), none of which is in a stacking context of its own, and below the Fields sheet (z-50).
- **When.** Shown with the Pumps together card. A project with one pump has no card, and no nav.
- **Buttons from what is drawn.** Each section registers its target on mount and unregisters it on destroy, through a small context PumpsView provides. PumpsView keeps them in document order, and the toolbar draws one button per registered target:
  - "Per pump", "Pump chart" and "Pumps together" while those are drawn;
  - "Station" and "Group chart" only while the card shows its values, never with the unavailable sentence or with no member ticked;
  - "Add cases" while the block is drawn, "Running combinations" while that section is.
- **Targets.** The section's heading (tabindex −1), except "Pumps together", whose target is the card's toggle button, so the press lands on the control and its expanded state is announced.
- **One Tab stop.**
  - ←, →, Home and End move between the buttons.
  - The Tab stop is the button last focused while the focus is in the toolbar, else the current one, else the first.
  - When the buttons change (the card closed, the last member unticked, a solve that fails, the scenarios removed), the stop is clamped: the same section if its button is still there, else the nearest earlier one.
  - While the focus is in the toolbar, the observer below moves `aria-current` only, never `tabindex`.
- **A press.** Enter or Space scrolls the target to the top, `target.scrollIntoView({ block: 'start', behavior: reduced ? 'auto' : 'smooth' })` with `reduced` from `matchMedia('(prefers-reduced-motion: reduce)')`, then `target.focus({ preventScroll: true })`, so the focus causes no second jump. Targets below the pump chart have `scroll-margin-top: calc(var(--pumps-nav-h) + 0.5rem)`. "Per pump" and "Pump chart" have 0.5 rem, since the nav is static when they are in view.
- **Buttons, never links.** The URL fragment is the project (D3), so a `href="#…"` would replace it; a test asserts `location.hash` unchanged after every press.
- **Marks.** A button carries its section's worst mark, by §5.2's severities: the red octagon for an invalid flag or a physically invalid value, else the amber alert for a warning flag, else ⬣ for a refusal or a failed request. A visually hidden text follows the label and starts with a comma, so it never runs into it: ", has physically invalid values", ", has warnings", ", has a refusal" or ", a request failed". Never for a design check (D19), never for a note. One pure helper, `sectionMark`, gives the icon and the words.
- **Where you are.** `aria-current="location"` marks the button whose target was passed last. An IntersectionObserver on the scroller (its top margin the nav's height) sets it, paused while the Pumps tabpanel is hidden (ResultsPanel keeps visited views mounted). When it changes, only the toolbar row scrolls (`row.scrollTo({ left, behavior })`), keeping the current button and the next one in view. It never calls `scrollIntoView`, which scrolls every scrollable ancestor and would move the pane or cut off a scroll already running.
- **Focus never hidden.** `--pumps-nav-h` comes from a ResizeObserver on the nav, never a px constant, so text zoom follows. While the nav is pinned, the scroller has `scroll-padding-top: var(--pumps-nav-h)`, so a focused control is never covered (WCAG 2.4.11); while it is static, none. Other views keep none.
- **The way back.** Each card ends with "Back to the sections", a button visually hidden until focused (`sr-only focus:not-sr-only`), which focuses the nav's current button. From the foot of Running combinations the nav is then one Tab away, not dozens of Shift+Tab.
- **One shared component.** The wheel that scrolls a row sideways, the edge shadows and the keep-in-view are the view row's (`ResultsPanel.svelte:458–483, 960–990`), made a shared row component in S2. It puts `py-1` on its scrolling element, since `overflow-x: auto` also clips vertically and the view row has no block padding: today a focused pill's ring is drawn only at its sides. The view row adopts it with `-my-1`, so its layout does not move, and its keep-in-view becomes the same row-only scroll.
- **Considered and dropped:**
  - A nav pinned all the time. 53 px over a 666 px pane leaves 613 px, so the 624 px pump canvas could never be seen whole at the default split: F12 made worse.
  - The nav in the pane's non-scrolling header row. That row is every view's; a Pumps-only row there is chrome every view pays for.
  - A compact 36 px row for a mouse. Results holds 44 px targets (ui-guide), and the pinning rule already keeps the nav off the pump chart.
  - Read blocks sticky to the pane's foot. They would cover about 130 px of a 620 px phone pane, over the canvas they read (WCAG 2.4.11). The readouts sit directly under their canvas instead.
  - Segmented sub-views of the card. They would hide Running combinations' flags behind a tab by default and break reading the chart against its tables.
  - A plain `nav` of buttons with a roving stop: nothing would tell users that the arrows apply.

### 5.5 Phones

Below 640 px (366 px at 390×844, 288 px at 320) the order and every control are the same; only the layout changes.

- **The nav** is one sideways-scrolling row of 44 px buttons with edge shadows, pinned by §5.4's rule: in portrait at 390×844 it pins; in landscape and under `short:` it stays static at the tab's top.
- **Grids and lists** follow their container, not the viewport. These, and only these, are containers (`@container`):
  - the pump chart's header-row wrapper (the select drops under the h3 below 21 rem);
  - the two readout wrappers (pairs two-up from 26 rem);
  - the extremes' box (a table from 26 rem, a list below it, S5);
  - the pump chart's data-grid wrapper (two-up from 40 rem);
  - the group legend (symbol entries two-up from 18 rem);
  - the member grid and the two case grids;
  - the group table's and Running combinations' scroll boxes, as size containers, so their flag lines and group lines can be `w-[100cqw]` as ResultsTable's box is (`ResultsTable.svelte:361–363`). Without that, `100cqw` would resolve against the small viewport (1,280 px on a desktop) and overflow the 452 px box. Neither holds a fixed-position descendant.
  - Never a card, and never an ancestor of a ResultsTable, a Dialog or a sheet: layout containment would trap a fixed-position sheet (ResultsTable's Fields sheet is `max-sm:fixed`, `ResultsTable.svelte:304`, and S6 puts a ResultsTable in the card). An e2e guard asserts that no ancestor of a "Fields shown in …" group has a computed `container-type` other than `normal`.
- So the members, the case lists and the legend's symbol entries go one or two per row as their container allows, and the curve tables one column.
- **Chips** wrap to two rows, and "on" is a ✓ as well as a colour.
- **Readouts** put one pair per line.
- **The strip:** a line's button wraps under its sentence, and stays next to it in the reading order.
- **Actions:** Download image drops under Show data table at 270 px or less, with its visible reason under it.
- **Tables read as lists:** "Operating points by case", "The pumps in the group" (flag line under the name) and "Other cases' station duties", as Running combinations and "Other cases' group curves" already do. The extremes table reads as a list below its box's 26 rem: a block per pump, a line per measure (§5.3).
- **The ring list** keeps one line per ring at every width; a ring's line wraps to 4 text lines (64 px) at 366 px and 5 or 6 (80 to 96 px) at 288 px (the mock).
- **Add cases:** the segments stay one row (D24's measured 169 px segments). Folded, the block is about six lines.
- **Hints** stay visible text; nothing floats over a phone's narrow column.
- **Sideways scroll:** none for the page or the pane's scroller at 390 and 320 px, asserted.

### 5.6 Wireframes

Desktop, 1280×800, Results pane about 480 px, lineups fixture after Solve all, the card open, station duties ticked, every other disclosure at its default.

```
▓ = the section nav   [ ] control   ▸ closed disclosure   ░ the action panel   ┄ a live line (empty when idle)
⚠ = the amber alert icon of a warning flag (an invalid one would be the red octagon)
┌────────────────────────────────────────────────────────────┐
│ (Summary)(Nodes)(Links)(Pumps)… ← Results view: tablist    │ filled pills, unchanged
│▓ Go to  Per pump  Pump chart  Pumps together  Station  G› ▓│ toolbar, 1 Tab stop; static
│                                                            │ here, pinned once the pump
│ Results per pump (h3)                                      │ canvas has scrolled out
│  [ResultsTable, unchanged]                                 │
│┌──────────────────────────────────────────────────────────┐│
││ Pump chart (h3)   [ Pump P1                           ▾ ]││ select named by the h3
││ The pump and system curves of one pump at a time; each … ││ cost hint, visible
││ Pump and system curves: Pump P1, Base case               ││ figcaption = image title
││ ┌──────────────────────────────────────────────────────┐ ││
││ │ head · η · P · NPSH panels  (Chart.js legend inside) │ ││ canvas (aria-busy here)
││ └──────────────────────────────────────────────────────┘ ││
││ Show [✓ Efficiency] [✓ Shaft power] [✓ NPSH]             ││ toggle chips, 44 px
││ Read at flow ━━━━━━━━━━━━━●━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ││
││ At the duty 21.58 L/s:  Pump head 40.33 m                ││ 14 px pairs, one <p>
││   System head 40.34 m  Efficiency 69.41 %  Shaft po…     ││
││ ┄ ◌ Computing the system curve for this solve… [Cancel]  ││ strip: only while needed
││ [Show data table]  [⤓ Download image]                    ││ ≈ +190 px idle (today +748)
││ NPSHa falls below NPSHr at about 39.41 L/s (read …       ││ notes: facts first,
││ Best efficiency point (+): 74 % at 30 L/s and 35.5 m, …  ││ unmarked
││ Shutoff head (–): 45 m.                                  ││
││ Shaft power ρgQH/η … the largest there is 15.1 kW at …   ││
││ System curve: the network of this solve, solved again …  ││ method stays visible,
││ … minus the EGL at the suction. Trace of Pump P1         ││ Trace an inline link
││ (data region here when shown: after the notes)           ││
││ ── Other cases on the pump chart ─────────────── h4 ──── ││
││ Cases on the chart                                       ││ legend, the fieldset's
││ Base case (shown)                                        ││ first child; a plain tag
││ [✓] △ 3 of 4 running (Pump   [✓] □ 2 of 4 running (Pump  ││ two columns
││       P4 off)                      P3, Pump P4 off)      ││
││ [✓] ✳ 1 of 4 running (…)     [✓] × Pump P2 off           ││
││ [✓] ▽ Pump P3 off            [▒] Pump P1 at 90 %         ││ capped: the box greyed,
││ [▒] Delivery tank 5 m higher                             ││ the name readable
││ Off in this case (no operating point): Pump P1 off       ││ S8: takes no slot
││ At most 6 cases at once.                                 ││
││ [ ] Also show the other cases' system curves             ││
││     Each is computed on request, … about 41 solves …     ││ cost stays visible
││ ┄                                                        ││ its live line
│└──────────────────────────────────────────────────────────┘│
│┌─ ▾ Pumps together ───────────────────────────── h3 ──────┐│
││ Pumps in the group                                       ││
││ [✓] ▲ Pump P1          [✓] ■ Pump P2                     ││ grid, symbol column kept
││ [✓] ★ Pump P3          [✓] × Pump P4                     ││
││ The calculation server finds the part of the network …   ││ the fieldset's description
││ Suggested for Pump P1, the pump on the pump chart above… ││
││ ▸ Other groups found: 2                                  ││
││ ── Station ───────────────────────────────────── h4 ──── ││
││ ┄ ◌ Computing the group curve…  [Cancel]                 ││ the group curve's line
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
││ Steps over the group curve's samples, each pump's flow … ││ reading hint, visible
││ ┄ ◌ Computing the group system curve for this… [Cancel]  ││ strip, while needed
││ ▲ Pump P1   ■ Pump P2      ── Group curve (station's …)  ││ legend: symbols two-up,
││ ★ Pump P3   × Pump P4      ── Group system curve (…)     ││ lines one per row
││ [Show data table]  [⤓ Download image]                    ││ ≈ +450 px (today +7,416)
││ ✓ At the duty's rise the group curve gives the solve's … ││ checks first
││ ✓ At the duty's flow the group system curve gives …      ││
││ Pump curves and points are at each pump's flanges. …     ││
││ ▸ How to read this chart: the axes, the group system cu… ││ reference, one step away
││ ▸ How the group curve is computed                        ││
││ ▸ How the group system curve is computed                 ││
││ (data region here when shown: after the reference)       ││
││ OTHER CASES ON THE GROUP CHART                      h5   ││
││ [✓] Also show the other cases' station duties            ││ the switch first …
││     Each case's station duty is computed on request, …   ││
││ Cases on this chart                                      ││ … the list under it
││ Base case (shown)                                        ││
││ [✓] ○ 1 · 3 of 4 running …   [✓] ○ 2 · 2 of 4 running …  ││
││ ┄                                                        ││ its live line
││ The group system curve is cut at the top, above every …  ││ the clip note, visible
││ ▸ How to read the rings: what a ring is, which curve it  ││ closed, before the list:
││   lies on, when it is called a point of the group …      ││ the frame, DUTY_CLAIM_RULE
││ Other cases on the chart (slate rings, numbered):        ││ the lead names the list
││ ○ 1 · 3 of 4 running (Pump P4 off), 77.28 L/s at a rise  ││ one line per ring: glyph
││       of 35.21 m: Yes: the same rest of the network; …   ││ and number in a reserved
││ ○ 2 · 2 of 4 running (Pump P3, Pump P4 off), 63.29 L/s … ││ column, the name medium
││ … rings 3 to 6, one line each …                          ││
││ Not on the chart: Pump P1 at 90 % speed (unticked …      ││ visible
││░ Add cases (h4)   Changes the project                   ░││ framed action panel
││░ Cases to add  ( By number running | Each pump off )    ░││ segments, always first
││░ ▸ The plan: 3 cases by number running: all 3 made      ░││ folded once every case exists
││░ [Add cases]  [▶ Solve all]                             ░││ one row, one Solve all
││░ Every case by number running already exists: «3 of 4  ░││ D24's refusal, visible,
││░   running (Pump P4 off)», «2 of 4 running (…)» and …   ░││ names the cases
││░ Every case's results are current.                      ░││ Solve all's reason
││░ [Pump lineups table…]                                  ░││
││ ── Running combinations ──────────────────────── h4 ──── ││
││ ⚠ 9 cases: 9 with current results (none physically       ││ the lead, first; its mark
││   invalid, 1 with warnings), none out of date, none …    ││ is the worst severity
││ EXTREMES OVER THESE CASES (CURRENT RESULTS)         h5   ││
││ ┌ Pump  ┬ Largest flow ┬ Largest shaft ┬ Smallest NPSH ┐ ││ a table: a row per pump,
││ │       │              │ power         │ margin        │ ││ a column per measure
││ │ Pump  │ 37.95 L/s    │ 15.05 kW      │ 1.065 m       │ ││ the value first, medium
││ │ P1    │ in 1 of 4    │ in 1 of 4     │ in 1 of 4     │ ││ the case and coverage
││ │       │ running (…)  │ running (…)   │ running (…)   │ ││ under it, slate-600
││ │ … Pump P2 to Pump P4, a row each …                   │ ││ 12 px; 387 px tall
││ └──────────────────────────────────────────────────────┘ ││
││ ┌ Running combinations ──────────────────── scrolls → ┐  ││
││ │ Base case (shown)                                   │  ││ lines wrap in view
││ │ 4 of 4 carrying flow: Pump P1, Pump P2, Pump P3 …   │  ││
││ │ ▲ Pump P1 → Running 100 21.58 40.34 12.28 3.327 Yes │  ││ names: trace buttons,
││ │ 3 of 4 running (Pump P4 off) · ring 1  …            │  ││ shown case only
││ │ ▲ Pump P1   Running 100 26.13 37.95 13.33 2.835 Yes │  ││ priority order
││ │ … rings 2 to 6 …                                    │  ││
││ │ Pump P1 at 90 % speed                               │  ││
││ │ ▲ Pump P1   Running 90 5.471 36.09 3.866 5.045 Yes  │  ││
││ │  [⚠ Warning] The operating flow (5.471 L/s) is out- │  ││ flag line at the
││ │   side its efficiency curve: the efficiency is held…│  ││ visible width
││ └─────────────────────────────────────────────────────┘  ││
││ (Back to the sections: shown only when focused)          ││
│└──────────────────────────────────────────────────────────┘│
```

Phone, 390×844: tab 366 px, scroll area 620 px; the same order.

```
┌──────────────────────────────────────┐
│ (Summary)(Nodes)(Links)(Pumps)…      │ Results view
│▓ Go to  Per pump  Pump chart  Pum… › ▓│ sideways toolbar
│ Results per pump (h3)                │
│┌─ Pump chart ──────────────── h3 ───┐│
││ [ Pump P1                       ▾ ]││ select under the h3
││ The pump and system curves of one  ││ cost hint
││ pump at a time; …                  ││
││ Pump and system curves: Pump P1,   ││
││ Base case                          ││
││ ┌── canvas 544 px, legend inside ─┐││
││ └─────────────────────────────────┘││
││ Show [✓ Efficiency] [✓ Shaft power]││ chips wrap
││      [✓ NPSH]                      ││
││ Read at flow ━━━━━━━●━━━━━━━━━━━━━ ││
││ At the duty 21.58 L/s:             ││ one pair per line
││ Pump head 40.33 m                  ││
││ System head 40.34 m                ││
││ Efficiency 69.41 % …               ││
││ [Show data table]                  ││ ≈ +300 px (+400 with
││ [⤓ Download image]                 ││ the strip)
││ NPSHa falls below NPSHr at …       ││
││ Best efficiency point (+): 74 % …  ││
││ System curve: the network … Trace  ││
││ of Pump P1                         ││
││ ── Other cases on the pump chart ─ ││ h4
││ Cases on the chart                 ││
││ Base case (shown)                  ││
││ [✓] △ 3 of 4 running (Pump P4 off) ││ one per row
││ [✓] □ 2 of 4 running (Pump P3, …)  ││
││ [ ] Also show the other cases'     ││
││     system curves                  ││
││     Each is computed on request …  ││
│└────────────────────────────────────┘│
│┌─ ▾ Pumps together ────────── h3 ───┐│
││ [✓] ▲ Pump P1                      ││ one per row
││ [✓] ■ Pump P2   …                  ││
││ The calculation server finds …     ││
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
││ Steps over the group curve's …     ││
││ ▲ Pump P1        ■ Pump P2         ││ legend: symbols two-up,
││ ── Group curve (station's flow)    ││ no taller than the canvas
││ [Show data table]                  ││ ≈ +750 px (today +9,658)
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
││ ▸ How to read the rings: what a    ││ closed, before the list
││   ring is, which curve it lies …   ││
││ Other cases on the chart (slate    ││ the lead names the list
││ rings, numbered):                  ││
││ ○ 1 · 3 of 4 running (Pump P4      ││ one line per ring,
││       off), 77.28 L/s at a rise …  ││ 64 px each
││░ Add cases                        ░││
││░ Changes the project              ░││
││░ (By number running|Each pump off)░││
││░ ▸ The plan: 3 cases by number    ░││
││░   running: all 3 made            ░││
││░ [Add cases] [▶ Solve all]        ░││
││░ Every case by number running …   ░││
││░ [Pump lineups table…]            ░││
││ ── Running combinations ─── h4 ─── ││
││ ⚠ 9 cases: 9 with current results  ││
││   (none physically invalid, 1 with ││
││   warnings), none out of date, …   ││
││ EXTREMES …                      h5 ││
││ Pump P1                            ││ the table as a list below
││ Largest flow 37.95 L/s in 1 of 4   ││ 26 rem: a block per pump,
││ running (Pump P2, Pump P3, …)      ││ a line per measure
││ Largest shaft power 15.05 kW in …  ││
││ list: a block per case, per pump;  ││
││ no "Flags None" lines              ││
│└────────────────────────────────────┘│
└──────────────────────────────────────┘
```

### 5.7 What it should measure (estimates; each budget set from the build, as build-density did)

The estimates for "after" come from the static mock of §5.3, which draws the strips as if a request ran (about 94 px on a desktop, 110 to 118 on a phone); the budgets are measured idle, after the requests, at 1280×800 and 390×844. At 320×640 the budget test asserts no sideways scroll, the nav's rule and the outline only: each slice records its 320 numbers in its as-built record, and a 320 budget is added where one proves useful.

| Measure | Before | After (estimate) | Budget, in `tests/pumps-layout.e2e.ts` |
|---|---|---|---|
| The pane's scroller scrolls sideways (condenser, 1280, 390 and 320) | yes | no | none at 1280×800, 390×844, 320×640 (S0) |
| Pump canvas to its Show data table | +716 to +952 px | about +190 (desktop) and +320 (phone) idle; +280 and +430 with the strip | ≤ 300 px at 1280×800, ≤ 400 px at 390×844 (S1) |
| Group canvas to its Show data table | +6,481 to +11,729 px | about +500 (desktop) and +600 (phone) idle | ≤ 600 / 900 px (S2) |
| The group legend's height, lineups, 390×844 | 452 px under a 256 px canvas | about 330 px (its words are pinned, so with six rings it stays taller than its canvas) | measured in S3 + 10 %, and ≤ 452 px (S3) |
| Card header to the station's first value (condenser) | 3,522 px | about +300 (desktop), +450 (phone) | ≤ 400 / 600 px (S3) |
| Headings below the pump canvas (with scenarios and a station) | 3 | 8 (10 in the tab) | the outline, in order (S2) |
| Longest run of notes without a heading or control | 13 paragraphs, 925 words | 4 in the card (the group chart's checks and notes, 139 words in the lineups mock) and 5 in the tab (the pump chart's notes, 134 words). Before the owner's answer 1 the mock's longest was the ring notes: 6 paragraphs, 568 words, 660 px | ≤ 5 in the card, ≤ 6 in the tab (S3) |
| The ring notes under "Other cases on the group chart", desktop (lineups; condenser) | 656; 600 px | about 456; 402 px (the mock: three short notes, a line of 48 px per ring, the summary 44 px), and 466 px in the condenser after S8's W8 (the mock with W7 to W9: four of its six ring lines grow from 48 to 64 px; the lineups' rings hold no "(D13)") | lineups measured in S3 + 10 %; condenser ≤ 513 px at 1280×800 (the mock's after-S8 466 px + 10 %), set in S3 and unchanged by S8 (S3) |
| The extremes with their h5, condenser (desktop; phone) | 678; 886 px | about 731; 854 px (the mock: the table 711 px, the list 834 px, plus 20 for the h5) | measured in S5 + 10 %, and their box never scrolls sideways at 1280×800 (S5) |
| Tab stops from the card header to the group's Show data table (condenser) | 35 | about 18 | ≤ 20 (S3) |
| Open card, condenser after Add cases (desktop) | 7,503 px | about 5,650 px: the first estimate's 5,900 without its 100 px for the grouped dl's name lines, then the ring notes 194 px shorter (596 against 402 px in the mock at 454 px) and the extremes table 49 px taller than today's dl (711 against 662 px; 658 measured) | measured + 10 % (S5) |
| Scroll-region Tab stops, lineups, everything open | 13 | the boxes that still overflow (at least 3 at 1280: the group table, Running combinations, the group curve's table) | each focusable box overflows, and the count is the one measured after S7 (S7) |
| The nav | — | pinned at 1280×800 and 390×844 once the pump canvas has scrolled out, about 8 % of the pane | static, or ≤ 15 % of the scroller's height, at 844×390 and 320×256; the pump canvas fits whole under the tab's top at 1280×800; after Tab and Shift+Tab through the card no focused element's rect meets the nav's (S2) |

The card gets about a quarter shorter. Running combinations stays open because it carries flags (GOALS §4.6), and it stays the card's longest block (about 2,100 px in the condenser). The headings and the nav carry most of the gain, and S6b carries the rest.

**Measured for the owner's answer 1** (2026-11-05). The static mock was extended with both changes and rendered in Chromium at the three pane widths: 480 px (the card's content 454 px), 366 px (340 px) and 288 px, the tab at 320×640 (262 px). A measuring page draws the condenser's and the lineups' extremes and ring notes in each form, with the words of the audit's accessibility snapshots. The mock's copies of today's forms reproduce the app: the condenser's dl is 662 px against 658 measured, its ring notes 596 px against 600, and their paragraphs 208, 112, 240 and 16 px, as measured. axe (WCAG 2.0 to 2.2 A and AA, and the table, list and heading rules) is clean in all three columns. The extremes' table rules (`td-has-header`, `th-has-data-cells`, `scope-attr-valid`) run in all three: the phone and narrow columns draw the list as §5.3's restyled native `<table>`, its header row visually hidden and each line's header `::before` content from `data-label`, so they test the phone form's header association too (the first rendering drew that list with `div` roles, on which axe runs no table rule). Heights in px:

| What | 480 px pane | 366 px pane | 288 px pane |
|---|---|---|---|
| Ring notes, lineups (S0's words): today; after | 634; 456 | 826; 584 | 1,066; 780 |
| Ring notes, condenser: today; after | 596; 402 | 788; 546 | 1,012; 678 |
| Ring notes, condenser, after S8's W7 to W9 (the lineups' are unchanged) | 466 | 610 | 806 |
| One ring's line | 48 | 64 | 80 to 96 |
| The "How to read the rings" summary | 44 | 60 | 80 |
| Extremes, condenser: today's dl; grouped dl; table; list | 662; 670; **711**; 706 | 870; 798; 983; **834** | 1,078; 1,006; 1,273, scrolling sideways; **1,026** |
| Extremes, lineups: today's dl; grouped dl; table; list | 394; 442; **387**; 434 | 442; 490; 501; **498** | 570; 586; 695; **610** |
| Extremes table rows, condenser; lineups | 121 four times, 89 twice; 105, 89, 89, 73 | (list) | (list) |
| The open card in the lineups mock: before the answer; after | 5,065; 4,836 | 7,298; 7,084 | (none); 8,704 |
| Words visible in the card, lineups mock: before; after | 1,046; 761 | 1,053; 768 | 768 |

In bold, the form each width gets. At 416 px the condenser's table is 807 px and its list 770, the lineups' 421 and 482. The list with each measure's header above its words, the other phone form tried, is 984 to 1,256 px in the condenser, so the header stays on the line.

## 6. What moves, and what words change

### 6.1 What moves

| Element | Today | Proposed | Why |
|---|---|---|---|
| Pump chart's system-curve state, Cancel, retry | among the notes, after the readout | the strip under the reading controls, one row per request, each with its own live line | F6, F17 |
| Pump chart's method sentence and "Trace of {pump}" | among the first notes, a 44 px button splitting it | the last value note, visible; Trace an inline link | F36; D10 |
| Pump chart's Show data table, Download image | after the notes and the case controls (+716 to +952) | under the strip (about +190 idle) | F3, F7 |
| Both charts' data regions | the pump chart's right under its toolbar; the group's at the card's foot | after their chart's notes (and the group's reference), so a shown table never pushes a note or a check away from its chart | F3, Aim 4 |
| "Operating point…" sentence of the pump chart's data region | after "Operating points by case" and the other cases' system curves (`PumpChart.svelte:743–850`) | the region's first line | F33; `pump-chart.md` §4.4 |
| "Operating points by case" and the case shown's curve tables | other cases' system curves first | the case shown first, other cases last | F33 |
| "Cases on the chart" and its overlay checkbox | after the notes, beside nothing | under the h4 "Other cases on the pump chart", at the figure's end | F1, F8 |
| Members, "Also found" | 6 rows and 4 unwrapped buttons | a two-column grid; "Other groups found: n" with two or more; wrapping | F10, F15 |
| The station (dl), the group table | after the figure and its notes (3,522 px in) | the first section, "Station" | F15 |
| The group curve's state, Cancel, retry | the card's one live region, inside the figure | the head of Station, which waits for it as the chart does | F17 |
| The group legend | right under the canvas (`PumpGroupChart.svelte:670–692`) | after the reading controls and the strip (`:698` onwards today), so the readout sits under its canvas | F12, F27 |
| The group's Show data table, Download image | the card's foot (+6,481 to +11,729) | under the group chart's legend (about +500 idle) | F3 |
| The group's "Other cases' station duties" and "Other cases' group curves" tables | before the group-curve tables (`PumpGroupChart.svelte:1424–1572` before `:1573–1674`) | after them, the shown case's tables first | F33 |
| The duty checks | in the run of notes | the first notes of the group chart, ✓ when they agree | F6 |
| The axes, system and own-system-curves notes | in the run of notes | "How to read this chart: …" | F7, F14 |
| "Also show the other cases' station duties" | under the list it reveals | above it, first under the h5 | F9 |
| Other cases' progress, Cancel, retry | three blocks inside the figure | beside their checkbox, under the h5 | F17 |
| The rings' frame paragraph and `DUTY_CLAIM_RULE` | in the run of notes, visible | "How to read the rings: …", a closed disclosure before the ring list, after the clip note | F7, F14; the owner's answer 1 |
| The ring list | one sentence of 230 to 248 words | a lead and one line per ring | F14; the owner's answer 1 |
| Add cases | between the group table and Running combinations | after the group chart, framed; its details in one disclosure, folded once every case exists | F16 |
| Extremes | an h5 after Running combinations, filed under Add cases; 18 lines of a dl | the h5 under h4 "Running combinations", before its table; a table of one row per pump and one column per measure, a list below 26 rem | F5, F13; the owner's answer 1 |
| Flags (group table, Running combinations) | the last column, off-screen | a flag line under each flagged row, at the visible width | F4 |
| Running combinations' cases | the shown, then scenario order | the shown, then the cases with values in `lineupChartPriority` order, then the rest, ticked or not | F24 |

Tests that read a data region by order are listed with their slice in §10 (S1 and S3).

### 6.2 New words

Every new word below is screen-only, except the S0 fix and S8's items at the end, which the image footer carries too. The export carries none of the web's words; A1's server words reach it (the last list).

- **Headings.**
  - h3 "Results per pump" (visible) and h3 "Pump chart".
  - h4 "Other cases on the pump chart", "Station", "Group chart" and "Running combinations".
  - h5 "Other cases on the group chart".
  - "Add cases" and "Extremes over these cases (current results)" are unchanged.
  - The fieldset legends "Cases on the chart" and "Cases on this chart" stay (`scenario-manager.md` §6.13, D24 §7.9; pinned by tests). The headings over them now say which chart each list changes.
- **The nav.**
  - Its name, "Pumps view sections", and its toolbar's visible label, "Go to".
  - Its buttons: "Per pump", "Pump chart", "Pumps together", "Station", "Group chart", "Add cases" and "Running combinations".
  - Visually hidden, after a marked button's label: ", has physically invalid values", ", has warnings", ", has a refusal" or ", a request failed".
  - "Back to the sections", the visually hidden button at each card's end.
- **The card.**
  - The closed card's line: "The station's duty, the group curve, each pump's share and cases with fewer pumps running[; Running combinations]".
  - "Suggested for {pump}, the pump on the pump chart above; tick pumps to choose your own."
  - "Other groups found: {n}"
  - "Showing a group found replaces the pumps ticked."
  - Visually hidden, at the start of a flag line: "{pump}, flags:".
- **The group chart's reference:** "How to read this chart: the axes, the group system curve, each pump's own system curve".
- **The other cases on the group chart (S3; the owner's answer 1):**
  - the rings' disclosure: "How to read the rings: what a ring is, which curve it lies on", and ", when it is called a point of the group system curve" while it holds `DUTY_CLAIM_RULE`;
  - the ring list's lead keeps its words, "Other cases on the chart (slate rings, numbered):", and is now also the list's name; each line is its ring's entry, word for word, without the "; " and the closing ".".
- **The extremes (S5; the owner's answer 1):** the column headers "Pump", "Largest flow", "Largest shaft power" and "Smallest NPSH margin", which are also the list's line labels on phones; the table's visually hidden caption "Extremes over these cases" is today's `aria-label`. The cells are today's words.
- **Add cases.**
  - "Changes the project"
  - The plan's summary: "The plan: {n} cases {by number running | with each pump off}: {k} to add", ": all {n} made", or ": {e} made, {b} not made (the base case's state)".
  - "In the names, {id} is {name}, …"
  - "Now ticked: “Also show the other cases' station duties” (Group chart)." (also written to `data-stop-status`).
- **Running combinations:** the lead "{n} cases: {v} with current results ({k | none} physically invalid, {w | none} with warnings), {m | none} out of date, {f | none} without results."
- **The pump chart.**
  - "Design-check limits drawn"
  - "(off in this case: no operating point)"
  - "Speed (%)" in place of "Speed", with bare numbers in "Operating points by case".
- **Names, visually hidden suffixes:** "Show data table" and "Hide data table" gain " of the pump chart" or " of the group chart"; each Details on the Pumps tab gains " of {what it details}" ("of the duty check", "of the system duty check", "of the point at {flow}", "of {reason}").
- **Buttons:** "Go to Checks", "Go to the pump chart" and "Go to Running combinations". They are buttons that focus a heading or switch the Results view, never touching the fragment.
- **S7:** "{table caption} ({n} points)".
- **Made visible, same words:** the lasting unavailable reasons of Solve all, both Download image buttons and Compute them again (the passing ones stay visually hidden and in `title`, §5.3), and the flag text after each badge.
- **Kept visible, same words** (no help on focus on this tab): the select's sentence, "The calculation server finds …" (now also the fieldset's description) and "Steps over the group curve's samples, …".
- **S0, a bug fix:** "Not on the chart: X (not on the chart (unticked under Cases on this chart))" becomes "Not on the chart: X (unticked under Cases on this chart)". It is fixed in `otherNotes` (`utils/pump-group-chart.ts:1406–1413`) for the unticked state only; `o.words` (`utils/pump-group-one-off.ts:492`) keeps "not on the chart (unticked under Cases on this chart)", which Running combinations' station line (`PumpsView.svelte:816`) and a cell of "Other cases' station duties" (`PumpGroupChart.svelte:1480–1482`) show and where it reads right. The image footer follows the fix through the same helper.
- **S8 only** (the image footer changes with them through the same helpers; the workbook carries none, since `utils/export/tables.ts` imports only the table helpers from `pump-group-chart.ts`):
  - The ☆ text glyph becomes ✳ (what Chart.js's `star` draws), and `rectRounded` (▢) gives way to ▽.
  - "Off in this case (no operating point): {names}", one line under the pump chart's case list while the other cases' system curves are off, for the cases that then take no slot.
  - "(D13)" in plain words (the owner's answer 4), W1 to W9 below.
- **"(D13)" and "(CLAUDE.md D13)" in plain words** (the owner's answer 4). The rule: where the sentence already says it in words, the citation goes; where it does not, the owner's words take its place, "several steady states can exist; {what} is the one the solve found". No other word changes.
  - **Found by** `grep -rn "D13" apps/web/src apps/api/src/opensolve_pipe`. Its other hits are code comments and docstrings (`PumpGroupChart.svelte:34`, `utils/pump-group-one-off.ts:15, 557`, `utils/compare.ts:12`, `Home.svelte:61`, `services/pump_groups.py:51`, `services/goal_seek.py:393`) and one OpenAPI description, `StateChange`'s "(one that carries flow in at least one of them, D13)" (`models/goal_seek.py:682`, generated into `api/openapi.json:8404` and `api/schema.d.ts:3924`), which the app never shows. They keep their citations, as CLAUDE.md's conventions ask of code. The rest are the tests that pin W1 to W9 (§10 S8) and two test titles that name the decision (`pump-group-system.test.ts:359`, `PumpGroupChart.svelte.test.ts:850`), the fixtures A1 regenerates (§9 A1), and spreadsheet cell references ("D13", "D130" to "D139") in the expected workbooks' JSON.
  - **The web's, in S8.** Each also reaches the image's footer through the same helper; none reaches the workbook.

    | # | Where | Shown in | Today | After |
    |---|---|---|---|---|
    | W1 | `utils/pump-group-chart.ts:1211`, the duty check that disagrees | the group chart's notes, visible, after the check's sentence (`PumpGroupChart.svelte:943–949`) | "Several steady states can exist (D13); the point is the one the solve found." | "Several steady states can exist; the point is the one the solve found." |
    | W2 | `:1513`, the system duty check that disagrees | the same, after the system check's sentence (`:950–956`) | the same as W1 | the same as W1 |
    | W3 | `:130–131`, `DUTY_CLAIM_RULE` | "How to read the rings" | "…; the curve is drawn through sampled points, each the state the system curve's starts find (D13)." | "…; the curve is drawn through sampled points, each the state the system curve's starts find." |
    | W4 | `:1284–1285`, `OTHER_CURVES_FRAME` | "How to read the rings" | "… and the station has one state at its rise (D13). Where its case differs …" | "… and the station has one state at its rise. Where its case differs …" |
    | W5 | `:1388`, the frame with a group curve and no family | "How to read the rings" | "… and the station has one state at its rise (D13): the curve drawn here when …" | "… and the station has one state at its rise: the curve drawn here when …" |
    | W6 | `:1391`, the frame with no group curve drawn | "How to read the rings" | "… and the station has one state at its rise (D13); no group curve is drawn here." | "… and the station has one state at its rise; no group curve is drawn here." |
    | W7 | `utils/pump-group-one-off.ts:235`, `DUTY_CLAIM_WORDS.zero_flow` | a ring's line; the chart's accessible name; the claim cell of "Other cases' station duties" (`PumpGroupChart.svelte:1474`); Running combinations' station line (`PumpsView.svelte:817–823`) | "Not said: at zero station flow the rest can hold more than one state (D13)" | "Not said: at zero station flow the rest can hold more than one state" |
    | W8 | `:238`, `DUTY_CLAIM_WORDS.shown_duty` | the same four places; in the condenser's ring list four times | "Not said: this case's own duty is not on the curve (D13)" | "Not said: this case's own duty is not on the curve (several steady states can exist; the duty is the one the solve found)" |
    | W9 | `:347`, `OTHER_CURVE_WORDS.not_through` | a ring's line; the accessible name; the "Its group curve" cell, capitalised (`PumpGroupChart.svelte:1476`) | "drawn ({k} running): it does not pass through the ring (D13)" | "drawn ({k} running): it does not pass through the ring (several steady states can exist; the ring is the one the solve found)" |

  - **The server's, in A1** (§9). Each sentence already says it in words ("more than one steady state", "another steady state", "several steady states"), so only the citation goes.

    | # | Where | Shown in | Today | After |
    |---|---|---|---|---|
    | A1a | `services/pump_groups.py:1451–1456`, the duty check that disagrees | the duty check's Details in the notes (`PumpGroupChart.svelte:945–947`) and in the data region (`:1413–1415`); the group curve's methods, as "Duty check: {message}." (`pump_groups.py:2043`), so "How the group curve is computed" (`PumpGroupChart.svelte:981`) and the workbook's Methods sheet; the Pump groups sheet's duty check column (`utils/export/tables.ts:800`) | "… The station has more than one steady state at this rise (CLAUDE.md D13); the group curve is the branch through the one the station alone reaches" | "… The station has more than one steady state at this rise; the group curve is the branch through the one the station alone reaches" |
    | A1b | `:1489–1495`, the system duty check whose first start leaves the rise undetermined | the system duty check's Details (`PumpGroupChart.svelte:952–954`, `:1418–1420`); the group system curve's methods, "System duty check: {message}." (`pump_groups.py:2068`), so "How the group system curve is computed" and the Methods sheet; the Pump groups sheet (`utils/export/tables.ts:803`) | "… with a rise of {h} m (more than 0.5 % or 0.01 m apart; CLAUDE.md D13)" | "… with a rise of {h} m (more than 0.5 % or 0.01 m apart)" |
    | A1c | `:1497–1502`, the system duty check that disagrees | the same as A1b | "… the rest of the network has more than one steady state at this flow (CLAUDE.md D13); the group system curve is the one its solve reaches" | "… the rest of the network has more than one steady state at this flow; the group system curve is the one its solve reaches" |
    | A1d | `:2039–2040`, the group curve's methods item "Points: …" | "How the group curve is computed" (`PumpGroupChart.svelte:981`); the workbook's Methods sheet, through `groupMethodsLines` (`utils/pump-group-chart.ts:2092–2100`) written by `utils/export/about.ts:593` | "Where a station has several steady states at a rise (CLAUDE.md D13), a point is the one its solve reaches from there." | "Where a station has several steady states at a rise, a point is the one its solve reaches from there." |

### 6.3 Words kept exactly

- **The words functions:** every `chartNotes`, `groupNotes` and `groupNoteLines` line, except the S0 fix and S8's W1 to W9; `o.words` entirely but W7 and W8, which it carries for a ring. The rings' cut (S3) and the extremes' table (S5) change no word: `otherNoteLines` joins S3's parts into today's lines (tested), and the cells are today's values.
- **Captions and titles:** both figcaptions (the image titles).
- **Buttons.**
  - The visible words "Show data table" and "Hide data table" (their names gain the suffix above).
  - "Download image" and its accessible names.
  - Every Cancel, Try again and Compute name, "Try the group system curve again" and "Compute them again".
  - "Trace of {pump}", "Back to the duty" and "Pump lineups table…".
- **Checkboxes:** "Also show the other cases' system curves" and "… station duties", with their cost sentences.
- **Sliders:** "Read at flow" and "Read along the curves", and both readouts' text.
- **D24's block:** every string (`LINEUP_BLOCK_WORDS`, `STOP_ORDER_WORDS`, `LINEUP_TABLE_WORDS`), the refusals included.
- **The legend's entries.**
- **Server and claim words:** the refusals, the methods, the server's sentences under Details, and Running combinations' lineup and station lines, except A1's four citations and W7 and W8 in the station lines.
- **The image:** its footer keeps every line and its order, `groupNoteLines` and `chartNotes` as today, the ring list one sentence (the owner's "The downloaded image keeps its current words"), except S0's fix and S8's W1 to W9.

### 6.4 Recorded designers' defaults this changes

Each change is recorded with its reason in the named record, in the same change as its slice:

1. **The card's order:** members, Station, Group chart, Add cases, Running combinations. This changes D21's paragraph, and D24 §7.1, which puts Add cases "under the group table and its footer". It now sits after the group chart, still above Running combinations.
2. **The group chart's data table and image:** the actions under its legend, the tables after its notes and reference (D21; `pump-groups.md` §6.5–§6.6). The pump chart's tables move after its notes the same way (`pump-chart.md` §4.4).
3. **The notes are regrouped on screen:** the coverage lines in the strip, the duty checks first, reference in disclosures, the ring notes under their h5 with what a ring is one step away (item 17). The image footer keeps `groupNoteLines`' and `chartNotes`' order (`pump-groups.md` §6.4; `export.md` §3.4). A new test (§10) proves every footer line is still on screen.
4. **Flags as a flag line,** not a last column, on screen, its text visible and read once (`pump-groups.md` §6.5; D24 §7.10). The image and the export have no flags column.
5. **Running combinations in `lineupChartPriority` order** after the case shown, whether a case is ticked or not (D21 4d keeps "the shown first"; D24 §7.10). Ring numbers stay labels.
6. **The extremes as a table,** one row per pump and one column per measure, a list below 26 rem, before Running combinations' table (D21 4d; the owner's answer 1). D21 4d's "the extremes over the current cases stay on screen" holds.
7. **Add cases** framed, its details in one disclosure that folds once every case exists, with the "Now ticked" and id lines (D24 §7.11–§7.12; D24's measured block of 440 and 504 px is re-measured).
8. **No help on focus on this tab.** The three hints the first draft moved there stay visible: the select's and the two checkboxes' are cost hints, the slider's would float over its own readout where Escape is taken, and Safari does not focus a checkbox or a range input on a tap or click, so their help would never show there (`ui-guide.md` gains the rule: help on focus only for text fields and selects, never over a control's own output, never where Escape is taken, never for a cost). This is a departure from the ui-guide's "static help shows on focus" (F19), recorded with that reason.
9. **"Also found"** behind "Other groups found: n" with two suggestions or more (D21).
10. **"Also show … station duties"** before "Cases on this chart" (D21 4d).
11. **Three live lines on the card** (the group curve in Station, the group system curve in the strip, the other cases under the h5), where 4d has one region, and two on the pump chart; each `aria-live`, none a `role="status"`.
12. **The section nav,** a new pattern for `ui-guide.md`: a toolbar in a `nav`, pinned only when it covers nothing being read, built from what is drawn, never touching the fragment.
13. **The card header stays an h3 holding a button.** This departs from the ui-guide's "disclosures are native `<summary>`": a heading inside `<summary>` is flattened by some screen readers, the body is rendered only when open, and about 35 test drives use the button.
14. **The pump chart's Trace link inline** in its sentence (WCAG 2.5.8's inline exception), and "Speed (%)".
15. **Marks only for the app's own severities** (§5.2): no ⚠ on a fact or a check, the invalid red octagon never shown as ⚠. Two places that draw the warning triangle in red for an invalid value today take the octagon (`FlagIcon severity="invalid"`) in S5: the extremes' values (`PumpGroupChart.svelte:1304–1307`) and Running combinations' marked cells (`:1257`, which keep their sr-only "physically invalid:").
16. **Names told apart by visually hidden suffixes** ("Show data table of the pump chart", "Details of the duty check"), the visible words unchanged.
17. **What a ring is, one step away** (S3; the owner's answer 1). On screen the frame paragraph and `DUTY_CLAIM_RULE` go inside "How to read the rings", drawn after the clip note and before the ring list; the clip note, the ring list (one line per ring), "Not on the chart" and the left-out count stay visible. The image's footer is unchanged. No decided rule says these notes must be shown rather than said: D13 has none (`decisions/D13-same-answer.md`), and neither have D21's or D24's owner's answers. The words that place them are designers' web defaults (D21's "Designers' web defaults (reversible, D14)", `D21-pump-groups.md:27`; D24's "Everything above not listed under 'Owner's answers'", `D24-pump-lineups.md:128`). The owner's answer changes these paragraphs, each updated in S3's records:
    - D21's slice 4d paragraph (`D21-pump-groups.md:31`): "the notes say a ring is the station's point, … and the list says which for each ring". On screen the notes now say it inside "How to read the rings", and the list is one line per ring.
    - D24's curve-family Words bullet (`D24-pump-lineups.md:112`): "the frame sentence replaces 4d's (`OTHER_CURVES_FRAME`); the clip note follows it". On screen the clip note now comes first, then the disclosure holding the frame, then the list.
    - D24's L3 paragraph (`D24-pump-lineups.md:132`): "the clip note a line of its own after the frame, the left-out sentence last". On screen: the clip note first, then "How to read the rings" with the frame, then the list, the left-out sentence last; the image as built. `pump-lineups.md` §15 item 92 is an as-built record of the image's order and stays as it is.
    - This proposal's own first draft, whose §8 and §10 had the frame and the rule "visible by default".

## 7. Keyboard and accessibility

**Heading outline**, with scenarios and a station shown:

- h2 Results
  - h3 Results per pump
  - h3 Pump chart
    - h4 Other cases on the pump chart
  - h3 Pumps together
    - h4 Station
    - h4 Group chart
      - h5 Other cases on the group chart
    - h4 Add cases
    - h4 Running combinations
      - h5 Extremes over these cases (current results)

That is 10 headings in the tab, 8 of them below the pump canvas, against 3 today. The extremes now nest under the section they summarise. The new sections are plain `div`s with headings, not landmarks. The regions that stay are the ones tests pin: "Pumps together", "Add cases" and the named scroll boxes (fewer after S7). The nav is the tab's one new landmark.

**Tab order** follows the visual order:

1. the nav's toolbar (one stop);
2. Results per pump;
3. the select;
4. the chips;
5. Read at flow and Back to the duty;
6. the strip's button;
7. Show data table and Download image;
8. the Trace link;
9. Go to Checks;
10. the pump chart's data boxes, when open and overflowing;
11. the case boxes, the overlay box and its Cancel;
12. "Back to the sections" (shown when focused);
13. the card's toggle;
14. the members and "Other groups found";
15. the group curve's button, at the head of Station;
16. the group table's names;
17. Read along the curves;
18. the strip's button;
19. the group's Show data table and Download image;
20. the notes' Details;
21. the reference summaries;
22. the group's data boxes, when open and overflowing;
23. the station-duties box, its list and its Cancel, then "How to read the rings";
24. Add cases: the segments, the plan's summary (and the stop order inside it), Add, Solve all, the table button;
25. the extremes' box only while it overflows (from S7; it has no Tab stop in S5, and from 26 rem it does not overflow, as measured), then Running combinations' box and the shown case's names;
26. "Back to the sections".

The group's Show data table is about 18 stops from the card's header, against 35 today (condenser). From the nav, Add cases is the arrows and Enter, and its first control is the next Tab; from the card's foot the nav is one Tab, through "Back to the sections".

**Keys.**

- The nav's toolbar: ←, →, Home and End; Enter or Space jumps and focuses the target.
- The sliders keep Escape (back to the duty) and their `aria-valuetext`.
- Disclosures open with Enter and Space (native `<summary>`).
- The stop order keeps its focus restoration after each move and after Default order.
- After Add, the focus moves to the block's Solve all, as today.

**Live regions.**

- **Pump chart:** two always-present polite lines, one for its system curve in the strip and one for the other cases' system curves beside their checkbox. The first progress message is now announced (F17).
- **Card:** three, one for the group curve at the head of Station, one for the group system curve in the strip, and one for the other cases' duties under the h5.
- Each is an `aria-live="polite" aria-atomic="true"` span, the first child of its row, holding no button; its button follows it, described by it. None is `role="status"`, so a pane-wide `getByRole('status')` still finds the Results header's alone (§5.3).
- No live line has a busy ancestor: `aria-busy` moves from both figures to their canvas wrappers, the part that is redrawn (ARIA 1.2 lets assistive technology hold back changes inside a busy element).
- Coverage lines and warnings are plain paragraphs, outside any live line.
- The readouts stay not live.
- `data-stop-status` stays polite, and also carries "Now ticked: …" after an Add.

**Focus.**

- The Cancel and retry handovers are unchanged, with each figure as the fallback.
- **"Back to the duty" on the pump chart:** the focus returns to the slider as the button goes (F40), as on the group chart.
- The nav's targets are headings with tabindex −1 and `scroll-margin-top`, except "Pumps together", which focuses the card's toggle; a press scrolls first and then focuses with `preventScroll`.
- The nav's Tab stop is clamped when its buttons change, so it never points at a button that is gone.
- `scroll-padding-top` keeps a focused control clear of the pinned nav (WCAG 2.4.11).
- "Back to the sections" focuses the nav's current button.
- The "Go to" buttons move the focus the same way.
- Add cases keeps one structure in every state, so no control in use is destroyed and drawn again elsewhere.
- Nothing touches `location.hash` (D3).

**Disclosures.**

- New and existing ones are native `<details>` with `.more-summary`, and each summary says what it holds; their chevrons are `aria-hidden` elements with `motion-reduce:transition-none`.
- None closes itself. Add cases' plan opens itself while cases remain to add and is drawn closed only when the block is drawn with every case made; after the user's own Add it stays as left.
- A data region is forced open when its chart cannot be drawn; from S7 a curve table whose Why no head column has entries is open by default.
- The card header and the two data-table toggles stay buttons with `aria-expanded` and `aria-controls` (§6.4 item 13).

**Names and marks.**

- Visible words stay part of every name (WCAG 2.5.3); the nav's buttons are named by their words, then their mark's visually hidden words after a comma.
- Toggle chips keep `aria-pressed`; their ✓ is an `aria-hidden` svg, so their text and names are unchanged.
- Capped boxes stay focusable and `aria-disabled`, look unavailable by their box only, keep their names at 4.5:1 or more, and are described by their cap.
- An off case's note is in its box's description.
- Disabled reasons that last are visible text, still in `aria-describedby`.
- Colour never carries meaning alone: a flag line shows the icon, the severity word and the flag's text once; a lead or button mark is named by its severity.
- The two "Show data table" buttons and the tab's "Details" are told apart by visually hidden suffixes (F18).
- "physically invalid:" stays sr-only beside the red icon in Running combinations' cells. The extremes' cells keep a red icon before the value and "physically invalid" in their words, as today. In both the icon becomes the invalid octagon (S5; §6.4 item 15), so shape as well as colour tells an invalid value from a warning's amber triangle.
- The extremes' list on phones takes each line's header from `data-label` as `::before` content, so a cell's text is the same at every width and its accessible name gains its header there, as Running combinations' cells do.
- The extremes table has a caption (its name), column headers and row headers, so a screen reader reads each cell with its pump and its measure; on phones the same roles stay under the list layout.
- The ring list is a list named by its lead; each line's glyph is `aria-hidden`, so a line reads as its ring's entry, word for word.

**Targets.**

- At least 44 px for the nav's buttons, the chips, the strip's buttons, case and member rows, summaries, the stop-order buttons and the toolbar.
- The Trace link and the refusals' element names are inline links (WCAG 2.5.8's exception).
- No page or pane sideways scroll at 1280, 390 or 320 px; text reflows at 320 px.

**Motion.** Every scroll the app starts reads `prefers-reduced-motion`: `behavior: 'auto'` when it is set, `'smooth'` otherwise. Spinners are `motion-safe:animate-spin`; chevrons have `motion-reduce:transition-none`. `ui-guide.md` gains the rule.

**Proof.**

- axe-core (WCAG 2.0, 2.1 and 2.2 A and AA) runs clean on the whole Pumps tabpanel (`[role=tabpanel][id$="-panel-pumps"]`, the nav included) at 1280×800, 390×844 and 320×640, with every disclosure open. The scans open only closed summaries (`details:not([open]) > summary`), so they never close one.
- A second scan of the same scope runs `.withRules(['heading-order', 'landmark-unique'])`, which the suite's tags leave out.
- The outline test of §5.7 holds the order above.

## 8. What stays exactly as decided

- **GOALS §3:** correctness, then traceability, then usability. A tidier layout never hides, drops or blurs a correctness or traceability item.
- **GOALS §4.2 and D10:** every value traceable. The methods stay, both disclosures with their references. The server's sentence stays under Details wherever the app rewords one. The system curve's method sentence stays visible, with its link to the pump's trace.
- **GOALS §4.5 and D3:** nothing new in the link. View choices are kept per browser only (S7's data-table choice, in try/catch). The nav and the "Go to" buttons never touch the fragment.
- **GOALS §4.6, D19 and PRD §4.1:** flags shown by default, now more visible. Refusals stay visible. Design checks stay opt-in, their limits behind the "Design checks" chip, never a verdict on the chart and never a ⚠.
- **GOALS §4.7:** every feature on both sizes, each in its own layout.
- **D10, system curves on demand:** one at a time, each with its loading state, Cancel, Try again, Compute and its points' reasons, never shown with another solve's results. The owner's 2026-10-23 rule stands: every point without a head says why, in words and as data.
- **D13:** results that agree within D6 are the same answer; nothing here changes a claim. The claim words (`DUTY_CLAIM_RULE`, `OTHER_CURVES_FRAME`, "Several steady states can exist", each ring's claim) keep every word but "(D13)", which becomes plain words (S8, A1; the owner's answer 4). Each ring's claim and every duty check that disagrees or is not known stay visible; the rule behind the rings' claims is one press away in "How to read the rings" (the owner's answer 1; §6.4 item 17).
- **D14:** every placement here is reversible.
- **D15:** the case is named on every result. The pump chart shows other cases' points and curves, their system curves only on request. The case shown, the members, the preset, the stop order, "Also show" and the unticked cases are page state.
- **D17:**
  - Download image stays under each pump chart and on the card, unavailable with its reasons by one rule. The PNG is drawn from the screen's configuration.
  - Its footer words come from the same functions. S1 to S7 change none of them; S0's fix and S8 change the ones §6.2 names.
  - Running combinations, the extremes, the stop order and the preset stay on screen only.
  - The export's 38 word-for-word tests (`utils/export/pump-groups.test.ts`, counted by `vitest list`) and the committed workbooks are untouched by S0 to S8. A1 changes the server's words they read: they reach the workbook's Pump groups and Methods sheets, so A1 regenerates the fixtures with their own commands and commits `export-pump-groups.xlsx` again (§9 A1).
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
  - The owner added the pump chart's overlapping labels to item 107 (§12); this work moves no label.

## 9. Slices

Each slice but A1 is a verified web slice on `web/pumps-layout`; A1 is an API slice on its own branch, with its own proof (below). A web slice is merged only when:

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
    - The "not on the chart (not on the chart (…))" wording is fixed in `otherNotes` only (§6.2).
  - **The tests:**
    - New `tests/pumps-layout.e2e.ts` holds the probe, adapted from the audit's `measure.mjs`, records the before numbers on the e2e build, and holds the **failing-first test**: the condenser example, its card open, its Results pane's scroller asserted not to scroll sideways at 1280×800, 390×844 and 320×640. It fails on main (the audit measured the scroller scrolling sideways at both sizes), and the slice record shows that failure.
    - `noSidewaysScroll` (`pump-groups.e2e.ts:133`) also asserts the pane's scroller. Its callers load fixtures whose scroller does not scroll sideways today, so it passes before and after; it is a stronger guard, not the failing-first test.
  - **The record:** the before screenshots go to `docs/proposals/pumps-results-layout/`.
  - **Proof:** `utils/pump-group-others.test.ts:304, 1287`'s two exact sentences updated to the fixed sentence; `o.words`' tests unchanged (`pump-group-one-off.test.ts:399`, `PumpGroupChart.svelte.test.ts:1172`); the chart-image footer tests; the whole e2e suite.
- **S1. Pump chart** (`PumpsView`, `PumpChart`; markup and CSS; `chartNotes` untouched).
  - **Headings:** the visible h3 "Results per pump"; the h3 "Pump chart" and the select named by it, its sentence kept visible.
  - **Reading:** toggle chips with an `Icon` check; "Back to the duty" handing the focus to the slider (F40); the readout as pairs in one `<p data-pump-readout>`.
  - **The strip:** its always-present `aria-live` line with its button after it; `aria-busy` moved to the canvas wrapper.
  - **Actions:** lasting image reasons visible, passing ones hidden; the names' visually hidden suffix.
  - **The notes:** facts first, unmarked, from a small pure helper over the same data, so no word and no footer changes; the method sentence with its inline Trace; "Design-check limits drawn" with Go to Checks.
  - **The data region:** after the notes; "Operating point…" first; the case shown first; the 40 rem container grid; scroll shadows; "Speed (%)"; a list on phones; the Details' suffixes.
  - **Other cases:** the h4; the legend first; the tag; the grid; the capped look; "(off in this case: no operating point)" for `status === 'off'`, in the box's description; the overlay line always present.
  - **Motion:** the chevrons and the spinner.
  - **Budget:** Show data table ≤ 300 px below the canvas at 1280×800, ≤ 400 px at 390×844.
  - **Tests:** the words-on-screen guard (§10) for `chartNotes`; §10's S1 list.
  - **Proof:** PumpChart, PumpChartChunk and PumpsView tests; design-checks, pump-chart, pump-chart-facts, pump-system, pump-control, scenarios, cancel and export e2e; chart-image tests unchanged.
- **S2. The card's shell, order and nav.** `PumpGroupChart` is split into section components (station, group chart, other cases, comparison), presentation only, with the same props, so its tests mount it unchanged. PumpsView's request effects are untouched.
  - **The card:** the closed card's line; the type scale; the h4 wrappers in the new order; the toggle's chevron.
  - **The group chart:** its toolbar under its legend and `#data` after its reference.
  - **The nav:** §5.4 whole: the toolbar and its lead word; its look; buttons from registered targets; the clamped Tab stop; the press with `preventScroll`; `aria-current` and the row-only scroll; the pinning rule (`sticky -top-4 z-[35]`, the canvas observer, the 15 % test, `short:`); `--pumps-nav-h` and `scroll-padding-top`; the marks from `sectionMark`; "Back to the sections".
  - **The shared row component,** with `py-1` on its scrolling element; the view row adopts it with `-my-1`.
  - **The axe loop** fixed to open only closed summaries, its scope the whole tabpanel, and the second scan.
  - **Budgets:** the group canvas to its Show data table; the nav's; the outline; one Tab stop; `location.hash` unchanged.
  - **Proof:** PumpGroupChart, PumpGroupView and PumpsView tests; `ResultsPanel.svelte.test.ts` and `ResultsViews.svelte.test.ts`, since the view row becomes the shared component, and every e2e test that changes the view through `resultsView` (`tests/support.ts`); pump-groups e2e.
- **S3. Station and Group chart.**
  - **Members:** the grid, the hint as the fieldset's description, the suggestion line and "Other groups found".
  - **The station:** the group curve's line at its head; the answer before the group table; the group table's flag lines (with `flagTone`, read once, named by their pump) and its list on phones; the box a size container.
  - **The group chart:**
    - the strip with the group system curve's line and its button (focus refs and `$effect.pre` kept); `aria-busy` moved to the canvas wrapper;
    - the readout as pairs from `parts`, its hint visible after it;
    - the legend's layout;
    - the duty checks first, ✓ when they agree; "How to read this chart"; the methods' `.more-summary`; the Details' suffixes.
  - **Other cases:** the h5, the switch first, its own line, the visible lasting retry reason and Go to Running combinations.
  - **The ring notes cut** (§5.3; the owner's answer 1):
    - `otherNoteParts` and `otherNoteLines` in `utils/pump-group-chart.ts`, so `otherNotes`, `groupNotes` and `groupNoteLines` return every word as today (tested), and `GroupNotes.otherParts` for the screen;
    - visible: the clip note, the ring list (its lead naming a list, one line per ring, the glyph and number in a reserved column, the name in medium weight), "Not on the chart" and the left-out count;
    - "How to read the rings: …", closed, after the clip note and before the ring list, holding the frame paragraph and `DUTY_CLAIM_RULE`, its summary naming what it holds.
  - **The data region:** after the reference; the duty sentence split; the other cases' tables after the group-curve tables.
  - **Budgets:** the station within 400 / 600 px; the longest run of notes; the ring notes' height (the condenser's set from S8's words, §5.7); Tab stops to the group's data table; the legend's height.
  - **Tests:** the words-on-screen guard for `groupNoteLines`; §10's S3 list.
  - **Records:** with the rest of §6.4, its item 17: D21's 4d paragraph, and D24's Words bullet and L3 paragraph.
  - **Proof:** PumpGroupChart, PumpGroupView and PumpGroupOneOff tests; `utils/pump-group-others.test.ts` with the parts' test, its pinned lines unchanged; pump-groups e2e; the chart-image tests and the export's word-for-word tests unchanged.
- **S4. Add cases** (`PumpLineupsBlock`).
  - **The block:** the panel with its tag beside the h4; the h4 at 14 px and its label at 12; one structure in every state (§5.3): the segments, the plan disclosure, the one row with the one Solve all, the refusal, Solve all's lasting reason, the table button; the fold rule.
  - **New lines:** the plan's summary, the id mapping and "Now ticked" (visible and in `data-stop-status`).
  - **D24 §7.11's order** is kept.
  - **Proof:** PumpLineupsBlock tests; pump-lineups and pump-groups e2e (the focus still on the block's Solve all after Add); axe with the stop order and the plan open.
- **S5. Running combinations.**
  - **New:** the lead, from a pure helper over `runningCombinations`, its mark by the worst severity.
  - **The extremes as a table** (§5.3; the owner's answer 1):
    - `combinationExtremes` also returns the table from the same values: its columns ("Largest flow", "Largest shaft power", "Smallest NPSH margin", from each measure's `what`), and a row per member with its name and a cell per measure, `{ amount, rest, invalid }`. `amount` is the formatted value, null for "no case gives one"; `${amount} ${rest}` equals the line's `value`, and the row's name and the column's words make the line's `term` (tested). `lines` stay, so its unit tests stand.
    - The table: the caption "Extremes over these cases", the column and row headers, the sticky row header (`max-w-48 wrap-break-word`), `data-label`s, the value on its cell's first line, the red octagon (`FlagIcon severity="invalid"`) in place of today's red triangle.
    - The box an inline-size container with `scroll-shadow-x` and no `tabindex` (S7's measured rule covers it); the list below 26 rem, its line headers `::before` content from `data-label`.
    - Running combinations' marked cells take the same octagon, keeping their sr-only "physically invalid:".
  - **Order:** the shown case, then `lineupChartPriority` order, then the cases without values.
  - **Lines and names:** the box a size container; sticky group lines; flag lines; names as trace buttons in the shown case's group only; no "Flags None" lines on phones; "Other cases' station duties" a list on phones.
  - **Budget:** the open card's height; the extremes' height, with no sideways scroll of their box at 1280×800, also with a 40-character unbroken pump name.
  - **Proof:** PumpGroupOneOff and PumpGroupChart tests, with the extremes' three assertions moved to headers and cells (§10 S5); `utils/pump-group-one-off.test.ts`'s extremes tests unchanged; pump-groups e2e at both sizes; axe's table rules on the extremes.
- **S6. The owner's table rules.**
  - **S6a:** "The pumps in the group" becomes a ResultsTable (sort, Fields, Flagged only, a list below 640 px). ResultsTable gains an optional flag-line snippet prop, which S6a fills with the `flagTone` pills and their visible text, so the visible flag text of S3 wins over ResultsTable's FlagBadge in the card, and the card's unit tests still mount no workspace. Every other ResultsTable keeps its FlagBadges.
  - **S6b:** Running combinations becomes a ResultsTable (the owner's answer 3): Flagged only and Fields in its grouped form; a sort turns it into one flat table with a Case column, and clearing the sort brings the case groups back. It keeps S5's order while unsorted, its flag lines through S6a's snippet prop, its trace buttons in the shown case's rows only, and a list below 640 px.
    - **Proof:** ResultsTable, PumpGroupChart and PumpGroupOneOff tests; pump-groups e2e at both sizes; §10's S6 list.
- **S7. Data without scroll traps.**
  - In both data regions, each curve table becomes a disclosure "{caption} ({n} points)", full height when open; opened by default when the chart cannot be drawn, and when its reason column has entries (the system curve's `systemMissing` over 0, or group-system-curve rows without a rise).
  - A scroll box is a Tab stop (`tabindex="0"`, a named region) only while it overflows, measured on both axes by a ResizeObserver, as `utils/scroll-focus.ts` does for height; today `PumpChart.svelte:749, 809, 858, 893, 945` and `PumpGroupChart.svelte:1033, 1149, 1359, 1432, 1498, 1579, 1639` set it whatever their width.
  - Whether each chart's data table is shown is remembered per browser (try/catch).
  - **Budget:** every focusable box overflows; the count is the one measured after S7.
- **S8. Cases and words** (touches the PNG footer).
  - **Markers:** the glyphs match the chart (✳, ▽), fixed by case while five other cases or fewer are drawn.
  - **Slots:** a case in which the viewed pump is off takes no slot while "Also show the other cases' system curves" is off, when it would draw nothing; the line "Off in this case (no operating point): …" names it. While the system curves are on it keeps its slot, since its system curve is drawn. Requests are made only while they are on, so no request changes. Switching them on can put a drawn case past the cap; its box then shows the cap, as any capped case does, and a test pins it.
  - **One choice of cases** (the owner's answer 2):
    - one set of the cases the user unticked, as page state, shared by "Cases on the chart" and "Cases on this chart": unticking a case under either list unticks it under both. Today the card's set is page state (`ws.pumpGroupUnticked`, `PumpsView.svelte:672–682`), and the pump chart's is the chart's own (`PumpChart.svelte:131–132`), remade on a pump switch by `{#key viewed.key}` (`PumpsView.svelte:868`) and emptied at `:864`;
    - what `untickedAfter` adds (`utils/pump-chart.ts:724–742`), the cases past a list's cap at that moment, stays each chart's own, page state per chart, never shared: the caps (5 and 6 other cases) and the orders differ, so sharing it would untick rings the user never touched;
    - each chart keeps its own cap, order and markers;
    - the pump chart's list no longer resets when the pump changes.
    - **Records:** D15's designers' paragraph (`D15-scenario-manager.md:23–25`, where the pump chart shows other cases) and D21's 4d paragraph ("Cases on this chart", `D21-pump-groups.md:31`) gain the shared unticks and the list kept over a pump switch, the owner's answer 2.
  - **"(D13)" in plain words** (the owner's answer 4): W1 to W9 of §6.2, after A1 has merged, so the server's words and the web's change in two steps, each proven on its own.
  - **Proof:** chart-image tests; the unit and component tests that pin W1 to W9, moved to the new words exactly (§10 S8); the export's word-for-word tests; `fixture.test.ts`; the API's `test_web_export_groups_fixture.py` run as a check; the shared unticks' tests (§10); `pumps-layout.e2e.ts`'s ring-notes budget passes unchanged (§5.7).
- **A1. The server's words** (the owner's answer 4; an API branch, not `web/…`, as CLAUDE.md's Branches rule asks, for example `api/pumps-plain-words`; merged before S8).
  - **The change:** A1a to A1d of §6.2, four strings in `services/pump_groups.py` (`:1451–1456`, `:1489–1495`, `:1497–1502`, `:2039–2040`), each losing "(CLAUDE.md D13)" or "; CLAUDE.md D13"; no other word, value, field or model changes.
  - **The checks that read the words:** the corpus check's branch for a system duty check that disagrees (`tests/differential/pump_group_check.py:2052`) keys on "CLAUDE.md D13" today; it keys on "steady state" instead. The branch is reached only with a rise and a disagreement (`pump_group_check.py:2045–2052`), so by the two messages of `pump_groups.py:1489–1502`, and both hold the words: "another steady state" (`:1492–1493`) and "more than one steady state" (`:1500`). The message without a rise, whose point message can say "no steady state …", is counted earlier and never reaches it. So the check is as strict as today's. Its smoke test's message (`tests/differential/test_pump_group_check_smoke.py:1064–1067`) takes the new words, with the same assertion. `tests/unit/test_pump_groups.py:1286` ("another steady state, found from another start") holds as it is.
  - **The fixtures, regenerated by their own commands, never by hand:** `pnpm gen:types` (`apps/web/scripts/gen-api-types.sh`) rewrites `export-input.json` (2 of today's citations) and `pump-groups-input.json` (30) from the real API; `openapi.json` and `schema.d.ts` come out unchanged, since no model changes (`git diff --exit-code -- src/lib/api`). Then `UPDATE_FIXTURES=1 pnpm exec vitest run src/lib/utils/export/fixture.test.ts` (`fixture.test.ts:12`) rewrites `export-pump-groups.xlsx` and `export-pump-groups.expected.json` (2), both committed; `export-results.xlsx` and its expected JSON hold none of the words and stay byte-identical.
  - **Proof:**
    - `fixture.test.ts` without `UPDATE_FIXTURES`: both workbooks byte for byte;
    - `uv run pytest tests/unit/test_web_export_groups_fixture.py tests/unit/test_web_export_fixture.py`, which read the workbooks back with openpyxl;
    - the export's 38 word-for-word tests (`utils/export/pump-groups.test.ts`) and the card's tests that read the fixture's messages (Details, the methods disclosures);
    - the API's unit and reference tests for pump groups (`tests/unit/test_pump_groups.py`, `tests/reference/test_pump_groups.py`), the differential smoke tests, and `pump_group_check` over the corpus with its counts unchanged;
    - `grep -rn "CLAUDE.md D13" apps/api/src` empty.
  - **`METHOD_VERSION` stays 1.6.0:** no solved value changes. The strings are messages and methods text, not results, and CLAUDE.md bumps the version only for "any change that can alter a solved value". The corpus comparison is not run: its dumps are `/solve`'s solved states (TSD §10.4, `corpus.py`), which hold none of these strings. `schemaVersion` stays 1.
  - **Records:** a `history.md` line; `verified-state.md` by `scripts/record_history.py`.
- **Records, with each slice:**
  - the D17, D19, D21 and D24 "Designers' web defaults" paragraphs and the specs named in §6.4 (S3's item 17 among them);
  - `ui-guide.md`: the section anatomy, the section nav (a toolbar, pinned only when it covers nothing being read, never touching the fragment), one strip per chart with its live lines, cost hints kept visible and where help on focus fits, tags drawn unlike controls, and reduced motion;
  - a `history.md` line naming `web/pumps-layout` or the PR;
  - `verified-state.md` by `scripts/record_history.py`;
  - `roadmap.md` trimmed.

## 10. Test impact

**No test is weakened.** Every pinned name, role, hook and word stays satisfiable, or moves with the same assertion. Scopes move only from a figure to the section that now holds the control, never wider. Where an element moves into a closed disclosure, the test gains an "open it" step first. Where a name gains a visually hidden suffix, the test takes the new exact name, which is the same strength.

- **jsdom and Playwright on closed disclosures.** jest-dom's `toBeVisible` and Playwright both treat content inside a closed `<details>` as hidden, while `getByRole` may still find it. So each moved element gets the open step in both suites.
- **Estimate:** about 70 assertions in about 18 files follow a moved element or a new name, and about 45 tests are new. Each slice's PR lists every old assertion beside its new one, as `build-density.md` §11 item 22 did.

**Kept as they are** (the grafts in §11 were chosen partly for this):

- **Methods and Trace.** `figure.getByText(/System curve: the network/)` stays visible in design-checks, pump-chart, pump-chart-facts and export e2e, since the method sentence stays visible. "Trace of {pump}" keeps its role and name.
- **Pump chart.** "Cases on the chart" stays inside the figure and keeps its name (the legend the fieldset's first child), and "Operating points by case" keeps its name (`scenarios.e2e.ts:220–226`). The chips' text (`PumpChart.svelte.test.ts:716–720`) and the readout's text and element (`pump-chart.e2e.ts:30–44`) are unchanged.
- **Single elements and levels.** `card.locator('dl')` still finds one `<dl>` without scenarios (`pump-groups.e2e.ts:175, 226`), and now with scenarios too, since the extremes are a table (S5); `card.getByRole('figure')` still finds one figure, and the heading "Add cases" stays at level 4 and names its region alone (`PumpLineupsBlock.svelte.test.ts:111`).
- **Rings and the legend.** The legend's entries stay visible with the same words. No screen test reads the frame, `DUTY_CLAIM_RULE` or the ring list today (`grep` over `src/**/*.svelte.test.ts` and `tests/*.e2e.ts`): the rings' words are read only in the chart's accessible name (`PumpGroupOneOff.svelte.test.ts:717–735`, `PumpGroupChart.svelte.test.ts:1398`, `pump-groups.e2e.ts:645–657, 950–957`), which S3 does not touch; "Not on the chart" through `card().textContent` (`PumpGroupOneOff.svelte.test.ts:339, 384`) and its absence (`PumpGroupChart.svelte.test.ts:1453`), which still hold; and the left-out sentence, which stays visible (`PumpGroupChart.svelte.test.ts:1696–1701`). The words themselves are pinned by `groupNotes`' unit tests (`pump-group-others.test.ts`, `pump-group-one-off.test.ts:298`), which S3 leaves as they are.
- **The Results header's status.** No live line on the tab is `role="status"`, so `resultsPane(page).getByRole('status')` (`cancel.e2e.ts:55, 250`; `solveConverged` at `support.ts:119`, called with the Pumps tab shown by `pump-chart.e2e.ts:61`) still finds one element.
- **The hints' descriptions** (`PumpGroupChart.svelte.test.ts:929, 1191`) are unchanged: the hints stay where they are described from.

**Assertions that follow a moved element or a new name, by slice:**

- **S0.**
  - `noSidewaysScroll` (`pump-groups.e2e.ts:133`) also asserts the pane's scroller: stronger.
  - `pump-group-others.test.ts:304, 1287` expect the fixed sentence, exactly. `pump-group-one-off.test.ts:399` and `PumpGroupChart.svelte.test.ts:1172` keep `o.words` as they are.
- **S1.**
  - `PumpChart.svelte.test.ts:677` finds the method paragraph by a class (`p.text-slate-600`) the tone change removes. It reads the same paragraph by a data hook, with the same equality to `request.notes.method`.
  - `:742` finds the readout by `div.space-y-1`; it reads `[data-pump-readout]`, with the same texts.
  - `aria-busy` moves from the figure to its canvas wrapper (`getByRole('img')`), the same assertion: `cancel.e2e.ts:235, 250, 279`; `PumpChart.svelte.test.ts:168, 178, 272`.
  - The overlay progress, `scenarios.e2e.ts:239` (`figure.getByRole('status').filter({ hasText: 'Computing system curves' })`), reads the line by its hook with `toHaveAttribute('aria-live', 'polite')` and the same text.
  - The pump chart's "Show data table" name queries take "Show data table of the pump chart": `PumpChart.svelte.test.ts` (8 queries; `:121`'s `toHaveTextContent('Hide data table')` still holds), and, given the full name so they stay as specific, `pump-chart-facts.e2e.ts:38`, `scenarios.e2e.ts:221`, `pump-system.e2e.ts:220, 234` (Hide), `:339`, `pump-chart.e2e.ts:51` and `pump-control.e2e.ts:177`.
  - The Why no head "Details": `PumpChart.svelte.test.ts:428` and `pump-system.e2e.ts:360` (`getByText('Details', { exact: true })`) read the summary by its new text. `topology-error.e2e.ts:113` and `home.e2e.ts:94` are other screens' Details, unchanged.
  - Tests reading the data region's tables by position read them by their names.
  - New: "Back to the duty" moves the focus to the slider, the same test as `PumpGroupChart.svelte.test.ts:917–923`.
- **S2.**
  - `pump-groups.e2e.ts:731` clicks every summary, which would close the self-opened ones. It opens only closed ones, as `:897` and `:1021` already do, and scans the whole tabpanel: stronger.
  - `ResultsPanel.svelte.test.ts` and `ResultsViews.svelte.test.ts` keep their view-row assertions on the shared component.
- **S3.**
  - The "Also found" clicks (7 uses) open "Other groups found" first when there are two.
  - The group table's Flags reads (the `rowOf` helper at `pump-groups.e2e.ts:66–75`; `PumpGroupChart.svelte.test.ts:422–437`) read the flag line under the pump's row: the same text, and "None" becomes the absence of a flag line.
  - `getByRole('status')` on the card (`PumpGroupChart.svelte.test.ts:242, 745, 1208`; `PumpGroupOneOff.svelte.test.ts:326, 426`) reads each request's line by its hook, with `toHaveAttribute('aria-live', 'polite')` and the same texts. `PumpGroupOneOff.svelte.test.ts:334`'s `toBe('')` ("nothing is computed for the other cases … and nothing says so") reads the other cases' line, where it still holds while the group system curve's line says it was cancelled.
  - `aria-busy` moves to the canvas wrapper: `PumpGroupChart.svelte.test.ts:241, 259, 750, 759, 1211, 1471`.
  - The axes, system and own-system-curve notes, read by exactly three tests (`pump-groups.e2e.ts:311–314`, `PumpGroupChart.svelte.test.ts:730–734` and `:955`), open "How to read this chart" first.
  - Tests expecting the duty sentence as one paragraph expect the same two texts in two.
  - The group chart's "Show data table" name queries take "Show data table of the group chart": `PumpGroupChart.svelte.test.ts` (8), `PumpGroupOneOff.svelte.test.ts` (2) and `pump-groups.e2e.ts:182, 322, 391, 435, 659, 730, 965`. With the 8 of S1 that is the 32 "Show data table" uses and the 2 "Hide data table" uses there are.
  - `pump-groups.e2e.ts:362` (the readout's exact text) is unchanged; new: `parts` joined equal `text`.
  - New: the members' fieldset has the server-finder hint as its accessible description.
  - The rings: no screen assertion moves (Kept, above). The words-on-screen guard reads the ring list as its lead and its items, and opens "How to read the rings" for the frame and the rule.
- **S4.**
  - `PumpLineupsBlock.svelte.test.ts`'s `details()` helper (`:126`, `block().querySelector('details')`, 10 uses) would now find the plan's disclosure first. It reads `[data-stop-order]`, the stop order's own disclosure, with the same assertions; `:638`'s `document.querySelector('details > summary')` reads the stop order's summary the same way.
  - `:207` asserts no `<details>` under Each pump off; it asserts no stop order (`[data-stop-order]`) there, which is what it tests. `:673` (a gate) is unchanged: under a gate the block has no plan.
  - Tests that draw the block with every case made (`PumpGroupChart.svelte.test.ts:1099`; the done states that pump-lineups and pump-groups e2e load) open "The plan: …" before reading the preview. A test after the user's own Add (`PumpLineupsBlock.svelte.test.ts:444`, `PumpGroupOneOff.svelte.test.ts:900–902`) needs no open step: the plan stays as it was.
  - Solve all and the focus on it after Add are unchanged.
  - New: exactly one button named `/^Solve all/` in each state (`getAllByRole`); after a preset change with the plan open, the focus is still on the chosen segment; after Add, `data-stop-status` holds "Now ticked: …".
- **S5.**
  - Running combinations' group order (`PumpGroupChart.svelte.test.ts:1336–1343`; `PumpGroupOneOff.svelte.test.ts:757–764` and `:820–828`) is re-indexed to `lineupChartPriority` order, with the same exact strings. `PumpGroupChart.svelte.test.ts:1347–1350` (`rows` of the held group has length 3, `rows[2]` is PB, which carries an Invalid flag) gains a flag line after each flagged pump's row: the count becomes 3 plus the flagged rows (PB's Invalid flag at least), and PB's row is found by its row header rather than by index. `groups[1]` and `groups[4]` at `:1367` and `:1371` follow the new order.
  - The Flags cell reads (`pump-groups.e2e.ts:630`; `PumpGroupChart.svelte.test.ts:1349, 1363`, `cells.at(-1)`) read the flag line following the pump's row, keeping `data-label="Flags"` and `toContainText('Warning')` / `'Invalid'`.
  - Tests that press a pump's name in Running combinations do so in the shown case's group; new: another case's group has no trace button.
  - **The extremes**, from dt and dd reads to header and cell reads, each with the same exact text:
    - `PumpGroupChart.svelte.test.ts:1369–1376`. `getByLabelText('Extremes over these cases')` with `tagName` "DL" becomes `getByRole('table', { name: 'Extremes over these cases' })` with `tagName` "TABLE". The heading's visibility is unchanged. `toHaveTextContent('Pump PA, largest flow: 40.75 L/s in Held (synthetic); beyond its curve data (over 2 of 2 cases)')`, a match inside the whole dl, becomes: in the row whose row header is "Pump PA", the cell under the column header "Largest flow" has exactly the text "40.75 L/s in Held (synthetic); beyond its curve data (over 2 of 2 cases)". The pump and the measure are pinned by the two headers instead of the term's words, and the cell is pinned whole: stronger. `:1377` ("Not counted (out of date): Pump PB off.") is unchanged.
    - `PumpGroupOneOff.svelte.test.ts:906–914`. The six dt texts, one per pump and measure in order, become three assertions that together pin the same six pairs: the row headers, `['Booster pump (PA)', 'Booster pump (PB)']`, the twins still told apart by their ids; the column headers, `['Pump', 'Largest flow', 'Largest shaft power', 'Smallest NPSH margin']`; and, for each body row, its cells' `data-label`s, `rows.map((r) => within(r).getAllByRole('cell').map((c) => c.dataset.label))` equal to `[['Largest flow', 'Largest shaft power', 'Smallest NPSH margin'], [the same]]`, with every cell's text not empty. So a row that lacks a measure, or has a cell under the wrong column or an empty one, fails, as a missing dt fails today.
    - `pump-groups.e2e.ts:632–634`. `card.getByLabel('Extremes over these cases')` with `toContainText(/Pump PA, largest flow: [\d.]+ L\/s in Pump PB off; beyond its curve data/)` becomes `card.getByRole('table', { name: 'Extremes over these cases' })`, the row with the row header "Pump PA", its `[data-label="Largest flow"]` cell with `toHaveText(/^[\d.]+ L\/s in Pump PB off; beyond its curve data/)`: the same pattern, anchored at the cell's start. At 390×844 the list keeps the roles and the `data-label`s, and draws each line's header as `::before` content, which `textContent` leaves out, so the same query and the anchored pattern hold at both sizes.
- **S6.** About 10 to 16 group-table reads follow the ResultsTable's headings (sort buttons inside them, the same names) and its flag lines. The card's tests keep mounting no workspace, since its flag lines come through the snippet prop. In S6b Running combinations' reads do the same; S5's order assertions hold while it is unsorted.
- **S7.** About 20 curve-table assertions open their table's disclosure first, except where the table is open by default.
- **S8.**
  - The chart-image tests on the marker set and the footer move to the new glyphs.
  - The tests that pin W1 to W9 take the new words exactly, each keeping its equality or its pattern: `pump-group-one-off.test.ts:292, 295` (`DUTY_CLAIM_WORDS`), `:298` (`DUTY_CLAIM_RULE`), `:1314, 1325` (`not_through`); `pump-group-chart.test.ts:414` and `pump-group-system.test.ts:371` (W1, W2); `pump-group-others.test.ts:157, 255, 494, 684` (the frame and the claim words); `PumpGroupChart.svelte.test.ts:869, 1398`; `PumpGroupOneOff.svelte.test.ts:732, 747`. No e2e test holds "(D13)".
  - No test pins today's reset of the pump chart's unticks on a pump switch: the two component tests that switch the pump (`ResultsViews.svelte.test.ts:581, 589` and `:649`) read no case list, and `PumpsView.svelte.test.ts:107`'s re-tick test stays on one pump. So no assertion moves for the owner's answer 2; its new behaviour gets its own tests (below).
- **A1.**
  - `tests/differential/pump_group_check.py:2052` keys on "steady state" in place of "CLAUDE.md D13", and `test_pump_group_check_smoke.py:1064–1067` takes the new message; the same assertions (§9 A1).
  - The fixture-driven web tests read the regenerated messages; none types "CLAUDE.md D13" (`grep -rln "CLAUDE.md D13" apps/web/src` finds only the three fixtures' JSON: `export-input.json`, `pump-groups-input.json` and `export-pump-groups.expected.json`).

**New tests:**

- **Budgets** (`tests/pumps-layout.e2e.ts`, at 1280×800 and 390×844, and the sideways, nav and outline checks at 320×640, 844×390 and 320×256, on one-off, lineups with everything open and condenser after Add cases): every budget in §5.7.
- **The nav:**
  - one Tab stop, the arrows, Home and End; the toolbar role, unlike the view row's tablist;
  - with the stop on "Group chart", close the card, untick every member and Tab into the nav: the focus lands on a button that exists;
  - with the card's unavailable sentence shown, no "Station" or "Group chart" button exists;
  - `aria-current` follows the scroll;
  - a press, with the keyboard, focuses its target under the nav, not covered: `document.activeElement` has a non-zero box inside the scroller's visible area, and "Pumps together" lands on the toggle;
  - with `page.emulateMedia({ reducedMotion: 'reduce' })`, after a press `document.getAnimations()` is empty and the target's top is the nav's bottom plus its margin;
  - a focused button's ring (its rect grown by 4 px) lies inside the row's `clientHeight`;
  - "Back to the sections" focuses the current button;
  - the marks, from `sectionMark` (a unit test with the four inputs), and the condenser's Running combinations lead named "Physically invalid";
  - `location.hash` unchanged.
- **Containers:** no ancestor of a "Fields shown in …" group has a `container-type` other than `normal`.
- **Words on screen:** every `chartNotes` and `groupNoteLines` line appears on screen word for word, visible or inside a named disclosure; the ring list as its lead and its lines, which `otherNoteLines` joins back into the footer's sentence. A duty check that disagrees or is not known, each ring's claim, the clip note, "Not on the chart", the left-out count and the no-head and no-rise lines are visible by default; `DUTY_CLAIM_RULE` and the frame paragraph are inside "How to read the rings".
- **The rings' parts** (S3, a unit test in `pump-group-others.test.ts`): for every state the file covers (the four frame forms, the clip note's clauses, the off line, the left-out count, a stale case, the base unticked), `otherNoteLines(otherNoteParts(…))` equals today's lines, word for word; `${lead} ${items.map((i) => i.text).join('; ')}.` equals the ring list line; each item's `text` is `${number} · ${name}, ${at}: ${words}`.
- **The rings on screen** (S3): "How to read the rings" closed by default, its summary naming what it holds (the frame alone, and the frame with the rule); with no station shown (the group curve not ready and the group system curve without a duty) no ring and no disclosure, so the rule never comes without the frame (§5.3); in DOM order the clip note, then the disclosure, then the list's lead and the list (`compareDocumentPosition`), so the frame's "The list below" is true; the list named by its lead, one item per ring in number order, each item's text without its `aria-hidden` glyph equal to its part's `text`; the disclosure absent with no ring on the chart.
- **The extremes table** (S5): `combinationExtremes`' table against its `lines` (each row's name and column's words make the line's `term`, each cell's `${amount} ${rest}` its `value`, "no case gives one" with no amount); the table's caption, headers and row headers; the octagon (FlagIcon's invalid icon) in exactly the invalid cells and no triangle in any, and the same in Running combinations' marked cells; the list below 26 rem with the same roles and `data-label`s, and each cell's text the same as at 1280×800 (its header is `::before` content); at 1280×800 the box does not scroll sideways, with the fixture's names and with a 40-character unbroken pump name, and has no `tabindex` (e2e).
- **One choice of cases** (S8): an untick under "Cases on the chart" unticks that case under "Cases on this chart", and the reverse, and every other ring stays; the cases past one list's cap at an untick stay unticked on that chart only; the pump chart keeps its unticks over a pump switch.
- **Running combinations as a ResultsTable** (S6b): a sort by NPSH margin flattens it into one table with a Case column, its first row the smallest margin; clearing the sort brings the case groups back in S5's order; Fields hides a column in both forms; Flagged only keeps the flagged rows with their flag lines.
- **Order:** "Cases on this chart" comes after its checkbox, in the DOM and on screen.
- **Live lines:** each exists while idle, has no `[aria-busy="true"]` ancestor and holds no button; it speaks on loading.
- **Pump chart:** the off-in-this-case note, as the box's description (`toHaveAccessibleDescription` contains "off in this case: no operating point"), only for an off pump.
- **The card:** the capped look; the visible lasting reasons; the suggestion line; "Other groups found".
- **Add cases:** the fold rule (closed only with `add` empty and `existing` not), one Solve all, the focus kept, "Now ticked" in the live line.
- **Running combinations:** the lead's counts, each one tested, a failed case among them; the order, unchanged by an untick and by the switch; trace buttons in the shown case's group only.
- **Flags:** the flag text visible in both card tables, inside the box's visible rectangle at both sizes; the flag line's text holds the flag sentence exactly once and starts with its pump.
- **axe:** clean with every new disclosure open, over the whole tabpanel, and the heading-order and landmark-unique scan; the extremes table under the table rules (`td-has-header`, `th-has-data-cells`, `scope-attr-valid`), at both sizes.

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

- the nav as one Tab stop with roving focus, `aria-current`, marks and `scroll-padding-top`, and as the only sticky element (since the review a toolbar, pinned only once the pump canvas has scrolled out, its marks by severity; §14);
- the plain section names that match the captions ("Pump chart", "Station", "Group chart", "Running combinations");
- the visible flag text after each badge;
- every card table as a list on phones without waiting for ResultsTable;
- "Now ticked: …" after an Add;
- Add cases as a framed panel tagged "Changes the project";
- one stable order for Running combinations in S5 (since the review `lineupChartPriority` order rather than ring numbers, which change on an untick; §14);
- "Speed (%)";
- the words-on-screen guard test.

**Grafted from Least change:**

- the flag line held to the visible width, ResultsTable's own pattern, with `flagTone`, in S3 and S5 rather than after S6;
- the method sentence and its Trace link kept visible;
- the ring list kept visible (since the owner's answer 1, one line per ring, with what a ring is behind "How to read the rings");
- the off-in-this-case note as an early, image-neutral step (since the review "(off in this case: no operating point)", for an off pump only);
- the before numbers and the budget test first.

**Not taken from the winner:**

- **Read blocks sticky to the pane's foot.** They would cover the canvas on a 620 px phone pane (WCAG 2.4.11).
- **The legend click switched off.** It is the built way to hide a design-check mark (`pump-chart-config.ts:211–212`, `:595`); syncing it with the chips is Later.
- **The same heading words over both case lists** ("Other cases on this chart"). They kept the confusion F8 measured, so each heading now names its chart.
- **The extremes as a term and value grid.** The draft kept the dl, grouped by pump; the owner then chose a table, one row per pump and one column per measure (§12, answer 1), which §5.3 measures against the dl.

**Not taken from the section-nav design:**

- **Renaming the pinned legends** "Cases on the chart" and "Cases on this chart" (`scenario-manager.md` §6.13, D24 §7.9) and "Show data table" to "Show data table (n tables)". That is 32 "Show data table" and 2 "Hide data table" uses, and the count changes while overlays arrive; the names are told apart by a visually hidden suffix instead, the visible words unchanged.
- **The chips above the chart,** a departure from `pump-chart.md` §4.1.
- **Add cases moved to the card's end,** away from D24 §7.1's place above Running combinations.
- **The method sentence, the Trace link and the case lists behind closed disclosures.**
- **The "Operating point" sentence moved out of the data region,** the chart's long description.

## 12. Answered by the owner (2026-11-05)

The owner's words: "Start the build. I accept the recommendations to the questions." The questions were put in the order below, each with its recommendation, and each answer is that recommendation. Question 1 is new since the reviews; questions 2 to 4 are this section's first three as first written, and its old fourth was settled with them.

| # | The question | The answer | Lands in |
|---|---|---|---|
| 1 | Cut the card's text further than the proposal? | Yes | S3 (the ring notes), S5 (the extremes) |
| 2 | One choice of cases for both charts? | Yes | S8 |
| 3 | Running combinations as a sortable table? | Yes | S6b |
| 4 | "(D13)" in plain words, web and server? | Yes | A1 (the server's words), then S8 (the web's) |
| — | The pump chart's overlapping labels onto item 107? | Yes | roadmap item 107; no slice moves a label |

1. **The further cut.**
   - **Asked.** Put the explanation of the other cases' rings behind a disclosure, "How to read the rings". Give each ring its own line instead of one long sentence. Show the extremes as a small table, one row per pump and one column per measure. The downloaded image keeps its current words. Recommended: yes.
   - **Built as** §5.3 designs it. The clip note, the ring list, "Not on the chart" and the left-out count stay visible, since they qualify this chart's reading; the frame and `DUTY_CLAIM_RULE` go into the closed "How to read the rings", drawn before the ring list that the frame introduces. The ring list's lines come from a parts helper whose join is today's sentence, so the image and every words test keep their words. The extremes table has the three measures today's dl holds, the value on each cell's first line, and a list below a 26 rem box.
   - **Measured** (§5.7): the lineups' ring notes 634 → 456 px and the condenser's 596 → 402 px at 480 px; the condenser's extremes 711 px as a table against 662 for today's dl (taller, said in §5.3), the lineups' 387 against 394.
   - **Records:** §6.4 item 17 (D21's 4d paragraph, D24's Words bullet and L3 paragraph) and item 6.
2. **One choice of cases for both charts.**
   - **Today.** "Cases on the chart" (the pump chart) and "Cases on this chart" (the card) hold the same cases with different rules. The first is reset on a pump change and capped at 5 others, in scenario order; the second is page state, capped at 6, in `lineupChartPriority` order. On this branch an untick on either list also stores every case then past that list's cap (`untickedAfter`, `utils/pump-chart.ts:724–742`), so the place it leaves stays free.
   - **Asked.** One shared set of the cases the user unticked, as page state: unticking a case under either list unticks that case under both. What `untickedAfter` adds, the cases past a list's cap at that moment, stays each chart's own, page state per chart, never shared: the two lists have different caps and orders, so sharing it would untick on the group chart rings the user never touched. Each chart keeps its own cap, order and markers. The pump chart's list no longer resets when the pump changes. Recommended: yes, since a user who hides a case on one chart expects it hidden on the other (F8), and only that case.
   - **Lands in S8**, with a test that an untick on the pump chart leaves every other ring on the group chart (§10). It changes how D15's and D21's case choices persist; S8's records say so.
3. **Running combinations as a sortable table (S6b).**
   - **Asked.** It becomes a ResultsTable: Flagged only and Fields in its grouped form. A sort turns it into one flat table with a Case column, and clearing the sort brings the case groups back. Recommended: yes. It meets the owner's 2026-10-31 rules (sort by any field, a Fields menu, a list on phones), and it finds the worst case in one press (sort by NPSH margin).
   - **Lands in S6b**, after S6a, with its tests (§10).
4. **"(D13)" in plain words.**
   - **Asked.** "(D13)" is in the web's notes and Running combinations' station lines (six times in the condenser's notes); "(CLAUDE.md D13)" is in the server's words (`services/pump_groups.py:1454, 1494, 1500, 2039`). Users cannot open either. Use the words it stands for, "several steady states can exist; this is the one the solve found", web and server. Recommended: yes.
   - **Lands in A1, then S8.** §6.2 lists every place, W1 to W9 on the web and A1a to A1d on the server, each with its words in context. A1 is a small API branch that changes no solved value, so `METHOD_VERSION` stays 1.6.0. It regenerates the export's fixtures with their own commands and commits `export-pump-groups.xlsx` again, since the server's words reach the workbook's Pump groups and Methods sheets (`utils/export/tables.ts:800, 803`; `utils/export/about.ts:593`). S8 then changes the web's words, which also reach the image's footer.
5. **The pump chart's labels.**
   - **Asked.** The pump chart's direct labels overlap near the duty: "Pump PB off" over "Delivery tank 5 m higher" and cut at the right edge (one-off, 1280×800), "3 of 4 running" over "BEP" (lineups), "Winter: tower bypassed" over "BEP" (condenser). Items 107 and 108 covered only the group chart's. Add them to item 107 and settle every collision rule for both charts together. Recommended: yes.
   - **Lands in** `roadmap.md`'s item 107, with the group chart's. This work moves no label and settles neither item.

## 13. Later

- An HTML legend for the pump chart, with keyboard toggles synced to the chips; the in-canvas legend's click stays until then.
- Links inside note sentences, which needs helpers that return tokens.
- Curve tables on one flow grid, so pump and system heads read on one row.
- The terms introduced once: operating point and station duty, head and rise, carrying flow and running.
- Collapsible h4 sections remembered per browser, if the structured card still reads long.
- A trace that opens for any case, so Running combinations' names can be trace buttons in every case's group, not only the shown case's (§5.3).
- A shorter group legend on a phone: with six rings and the curve family it stays taller than its 16 rem canvas while its words are pinned (§5.7).
- Help on focus for checkboxes and sliders, if a pattern is found that shows it on a tap in Safari and never covers the control's own output.
- The card remembered open per browser. It stays closed on each load (D21), since opening asks for the group curve and the group system curve, about 82 solves of the station.

## 14. Review record (2026-11-05)

An accessibility review (A11Y-01 to A11Y-22) and a design review (R1 to R32) read the first draft against the code. Each finding was checked against main's content and the branch; every one held, in whole or in part. Where a finding offered two fixes, the one taken is named.

| Finding | Held | Where it landed |
|---|---|---|
| A11Y-01 nav targets that may not exist | yes | §5.4: buttons from registered targets, the clamped stop, the observer never moves `tabindex`, "Pumps together" focuses the toggle; §10 tests |
| A11Y-02 a hidden heading as a focus target | yes | the visible h3 "Results per pump" (§5.3 item 1) |
| A11Y-03 "Back to the duty" drops the focus | yes | F40; S1; §7 Focus; a unit test |
| A11Y-04 the fold re-parents controls; two Solve all | yes | §5.3 Add cases: one structure, one plan disclosure, one Solve all, the fold rule; S4 tests |
| A11Y-05 help on focus where it does not fit | yes; the select's sentence also stays visible, since it is a cost hint and its help would cover the figcaption the review names | §5.3, §6.2, §6.4 item 8; no help on focus on this tab |
| A11Y-06 the live regions cannot be built as written | yes | one live line per request, its button outside, `aria-busy` on the canvas wrapper (§5.3 markup rules, §7), as `aria-live` lines per R5 |
| A11Y-07 invalid values marked and named as warnings | yes | §5.2 marks by the app's severities; the lead and `sectionMark` |
| A11Y-08 the mock's names and targets | yes | the mock corrected and re-rendered; §5.3 markup rules |
| A11Y-09, R28 the extremes' markup | yes | §5.3: first the name inside the dts, no new child in the dl; since the owner's answer 1 a table with a caption, column headers and row headers (S5) |
| A11Y-10 the nav's size, offset, stacking and short screens | yes | §5.4 Place and Focus never hidden; §5.7 nav budget |
| A11Y-11 the shared row clips the ring | yes | §5.4 One shared component (`py-1`, `-my-1`); a test |
| A11Y-12 reduced motion | yes | §5.4 A press, Where you are; §7 Motion; markup rules |
| A11Y-13 flags read twice | yes | §5.3 flag line: read once, named by its pump |
| A11Y-14 the off note not tied to its box | yes | §5.3, in the box's description |
| A11Y-15 capped names at 2.9:1 | yes | §5.3: only the box greyed, the name at slate-600 |
| A11Y-16 duplicate names | yes; the visually hidden suffix, not a description | §5.3 Actions and notes; §6.2; §10 lists the 32 "Show data table", 2 "Hide data table" and 2 "Details" uses that follow |
| A11Y-17 the axe scope and rules | yes | §7 Proof |
| A11Y-18, R19 no cue for the arrows; no way back | yes; R19's names (a toolbar labelled "Go to" in the `nav`) | §5.4 Markup, Look, The way back |
| A11Y-19 "Now ticked" not announced | yes | `data-stop-status` carries it (§5.3, §7) |
| A11Y-20 the phone legend taller than its canvas | in part: with its words pinned and six rings it stays taller (the corrected mock: about 330 px under a 256 px canvas) | §5.3 legend layout; §5.7 budget measured + 10 % and ≤ 452 px; §13 Later |
| A11Y-21 tags shaped like controls | yes | §5.2 Tags |
| A11Y-22, R12 containers | yes | §5.5, the list of containers; an e2e guard |
| R1 trace buttons in other cases' groups | yes | §5.3: the shown case's group only; §13 |
| R2 "no point drawn" false; S8's slot change | yes; the slot kept while the system curves are on | §5.3, §6.2, S8, F25 corrected |
| R3 facts turned into warnings | yes, and extended to the coverage lines and to checks that disagree | §5.2 No mark on a fact |
| R4 the nav hides part of the pump canvas | yes; pinned only once the canvas has scrolled out | §5.4 Place; §5.7 |
| R5 an always-present status breaks pane-wide queries | yes; `aria-live` lines | §5.3 markup rules; §10 Kept |
| R6 a shared untick set against `untickedAfter` | yes | §12 item 2 (the first draft's question 1); S8 |
| R7 the lead's counts | yes | §5.3 the lead, its definitions |
| R8 ResultsTable's badge against visible flag text | yes; a snippet prop | S6a; §10 S6 |
| R9 S1 assertions on the chips and readout | yes | §5.3 Reading; §10 Kept |
| R10 the group readout, a row count, two citations | yes | `parts`; §10 S3 and S5 |
| R11 ring order reorders the table | yes | `lineupChartPriority` order (§5.3, §6.4 item 5) |
| R13 one budget for every size | yes | §5.7 per size; 320 for the sideways, nav and outline checks |
| R14 scroll-region Tab stops | yes | S7: a Tab stop only while overflowing |
| R15 the data region above the notes | yes; the region after the notes | §5.1, §5.3, §6.1 |
| R16 the fold undefined for mixed plans | yes; the ✓ line dropped, since D24's refusal already names the cases | §5.3 The fold; §10 S4 |
| R17 the doubled words' source | yes; fixed in `otherNotes` only | §6.2 S0 |
| R18 the server-finder hint is no description today | yes | the fieldset's `aria-describedby` (§5.3) |
| R20 a passing reason would flash | yes | §5.3 Actions |
| R21 the KLM rows | yes | §2.2; the next button kept in view |
| R22 the heading count | yes | §5.7, §7 |
| R23 the dev server | yes | §2 |
| R24 the test counts | yes | §10 |
| R25 the extremes grow | yes; kept at 12 px | §5.2, §5.7 |
| R26 question 3's cost | yes | §12 item 4 (the first draft's question 3); §8 D17; §9 A1 |
| R27 three moves not listed | yes | §6.1 |
| R29 why-no-head reasons two presses away | yes | S7: such a table open by default |
| R30 S2's proof | yes | S2 Proof |
| R31 not a failing-first test | yes | S0: the condenser test in `tests/pumps-layout.e2e.ts` |
| R32 the group curve's state far from what waits for it | yes | §5.3 Station; §7 Live regions |

The `ui-guide.md` rules these call for (help on focus, tags, the nav, reduced motion) are written when the slices that build them land (§9, Records), since the guide records built patterns.

After this record the owner answered §12 (2026-11-05). The answers changed S3 (the ring notes), S5 (the extremes), S6b and S8, and added A1; S0 and S1 are as reviewed. No finding above was re-opened by them. A11Y-09 and R28 (the extremes' markup) now apply to the table: its caption, headers and row headers replace the dl's terms, and axe's table rules replace its definition-list rules (§7, §10).

**Review of the owner's answers** (2026-11-05). A design review (its R1 to R8, not the first review's R1 to R32 above) and a fidelity review (F1 to F11, not §4's friction ids) read the revision against the code and the mock. Each was checked against the code; all but one held. The mock was re-rendered with the ones that touch it, and its checks re-run: every height in §5.7 is unchanged, axe is clean in all three columns, and the extremes' table rules now run in the phone columns too.

| Finding | Held | Where it landed |
|---|---|---|
| design R1, the frame's "The list below" drawn after the list | yes | §5.1 item 10, §5.3 (the order on screen: the clip note, "How to read the rings", the list), §5.6, §6.1, §6.4 item 17, §9 S3, §10, the mock |
| design R2, the warning triangle for invalid values | yes | §3, §5.3, §6.4 item 15, §7, §9 S5, §10: the octagon (`FlagIcon severity="invalid"`) in the extremes and Running combinations' marked cells; the mock |
| design R3, S8's words past the ring notes' budget | yes; measured 402 → 466 px. W8's repeated parenthesis is answer 4's rule and stays | §5.7: the condenser's budget ≤ 513 px, set in S3; S8's Proof |
| design R4, fidelity F1, the moved extremes assertion weaker | yes | §10 S5: each row's cells' `data-label`s and texts |
| design R5, the phone list's header as an element | yes | §5.3 and §10: `::before` content from `data-label`; the mock |
| design R6, a rule-only state of the disclosure | no: a ring needs a station (`PumpGroupChart.svelte:290–292`), so the frame exists whenever a ring does, and the rule needs a group system curve, which has points only with a duty (`services/pump_groups.py:1776–1777`) | §5.3 says why there are two summaries, not three; §10 tests that no ring and no disclosure are drawn without a station |
| design R7, axe's table rules never ran on the phone list | yes; the mock redrawn rather than the claim reworded | the mock's phone list is the restyled native `<table>`; §5.7 |
| design R8, the extremes' box between S5 and S7 | yes, with `overflow-wrap: break-word` in place of `anywhere`, which narrows the condenser's pump column to 64 px and breaks "Condenser" inside the word (measured) | §5.3, §7 item 25, §9 S5, §10: no `tabindex` until S7, the 40-character name check |
| fidelity F2 to F11 (a grep, a quotation, a citation, 114 characters, 37 px, the 5,650 px base, two pump switches, line numbers, the D13 hits, §3) | yes. For F4 the ring list cites S3's design; its column is not the case list's width (2.25 rem against 2.5 rem after a checkbox, as the mock draws them) | §3, §5.3, §5.7, §6.2, §9 A1, §10 |

## 15. As built

Each slice records its items here, numbered on from the slice before: each departure of the build from this text, each number of this text its measurement corrects, what it leaves or changes for a later slice, and the screenshots it commits. Its measurements, its failing-first test and its proof follow its items.

**S0, as built** (`b1c3756` on `web/pumps-layout`; measured at `e701931`, which adds only docs: the owner's answers in this text and their review, and the matching lines in the proposals index and the roadmap; no code):

1. **The "Also found" buttons' classes** (§9 S0). Each takes `whitespace-normal`, `text-left` and auto height, as §9 says, and also `py-1.5` and `wrap-anywhere`. `py-1.5` is what the app's other wrapping buttons take (`PortsEditor.svelte:206`, `FittingsEditor.svelte:286, 293`, `ProjectLibrary.svelte:552`). `wrap-anywhere` is `ProjectLibrary.svelte:552`'s: a pump name with no spaces breaks instead of overflowing. `.btn`'s `min-h-ctl`, 44 px in the Results pane, stays. `ui-guide.md` gains the pattern.
2. **Where the sentence sits** (§5.3 Members leaves it open). "Showing a group found replaces the pumps ticked." is a `.hint` paragraph after the buttons. Each button's `aria-describedby` points to it, so a screen reader hears it with every button, and the screen shows it once per card. It is shown whenever a group is offered, one or more (§5.3: "either way"). The buttons and the sentence share one wrapper. `alsoFound` stays bound to the row of buttons, so `showSuggestion`'s focus handover is unchanged. "Other groups found: {n}" is S3's.
3. **The doubled words, fixed where §6.2 says.** `otherNotes` gives an unticked case "unticked under Cases on this chart"; `o.words` is unchanged. The fix keeps its own literal, not a constant shared with `utils/pump-group-one-off.ts`: `utils/pump-group-chart.ts` imports only types from that module, and a shared value would make a runtime import cycle. Tests pin both strings exactly. The image footer takes the fixed line through `groupNoteLines`. No footer test pinned the old words, so none changed. The workbook carries no words about the other cases and is unchanged.
4. **Every view is held to the rule, and the lineups failed it too.** §5.7 row 1 names only the condenser; the new file holds the one-off and lineups views to it as well. On main the lineups view scrolled sideways at 320×640: "Also found: Pump P2, Pump P3 and Pump P4" reached 332 px in a 296 px tab, and the pane's scroller held 344 px in 320. The audit measured only 1280×800 and 390×844, so §2.1 does not record it. The same fix covers it.
5. **320×640 is a resize, not a project.** In the `mobile` project each test checks at 390×844, then resizes the page to 320×640 and checks again, as `pump-lineups.e2e.ts:568` does. The sideways assertions are `expect.soft`, so one run reports every size. The file has 3 tests, 6 with the two projects. A run of it took 2.9 to 3.0 min on one worker.
6. **The probe, adapted from `measure.mjs`** (§2, §9 S0). It differs in four ways:
   - the pane's scroller is the first ancestor of the "Results view" row whose `overflow-y` is `auto` or `scroll` (`resultsScroller`, `tests/support.ts`), with no condition that it overflows, so it is found even when the tab is short;
   - sideways is strict, `scrollWidth ≤ clientWidth`, where the audit allowed 1 px;
   - the repeated-phrase counts are dropped, and the count of headings below the chart is added;
   - the screens are taken at CSS pixels.

   Each run prints one line per view and size, and attaches the numbers to the test as JSON. With `PUMPS_LAYOUT_RECORD` set to a directory, it also writes there the numbers, the accessibility snapshot and the pane's screens from the pump canvas down: the before and after record of a slice.
7. **The views' flows** (§2). The condenser example is opened by its link (`exampleProject('condenser-water')`, encoded as `build-density.e2e.ts` does), not from the home page. The condenser test also asserts 7 solves in all, and the block's Solve all unavailable at the end.
8. **Tests beyond §9's list.** `noSidewaysScroll` (`pump-groups.e2e.ts:134–143`) also asserts that the pane's scroller is found. `PumpGroupChart.svelte.test.ts` gains one test (35 tests → 36): the sentence appears once; each "Also found" button has it as its accessible description and carries `btn`, `whitespace-normal` and `text-left`; with no group offered there is no sentence.
9. **How the before numbers were measured** (§2, §9 S0). The new file's probe ran in record mode in a scratch worktree of main at `2f5e1e3`, with three files of this branch copied in: `tests/pumps-layout.e2e.ts`, `tests/support.ts` (which differs from main's only by `resultsScroller`) and `tests/pump-groups.e2e.ts`, for the before run of its stronger `noSidewaysScroll`. Playwright started the API and the app from that tree, on the e2e build (`pnpm build && pnpm preview`). The after numbers are this branch's, on the same build. The numbers of record come from the e2e config, whose `mobile` project runs at device scale factor 3. The five committed before screenshots (item 15) are crops of that run's screens, taken at CSS pixels. A second measurement after the review, of main in a fresh worktree and of this branch at `e701931`, gave the same numbers in all nine views and sizes, the outline, Tab-stop and paragraph lists included. That measurement also ran main and this branch with every project at device scale factor 1, and a focus probe of the wrapped buttons on this branch at the same scale. Item 14 reads their screens, which are not committed.
10. **§2.1 against the e2e build.** The condenser at 390×844 measures 11,687 px below the pump canvas, not 11,673, so the area below it is 18.9 screens of 620 px (11,687 / 620 = 18.85), not 18.8. Its group chart's Show data table sits at +9,672, not +9,658. §2.1's two numbers are what the build gives at device scale factor 1; at 3, Running combinations is 14 px taller (4,855 against 4,841). Every other number of §2.1's two tables, of its card and of its walls of notes matches the e2e build.
11. **§5.7 row 4's "Before" is the condenser's.** "The group legend's height, lineups, 390×844: 452 px" is the condenser's legend at 390×844, as is F27's 452. The lineups' legend measures 312 px there, on main and on this branch; the audit's own record says 312 too. Row 4 is S3's budget, so S3 sets it from its own measurement of both views.
12. **§5.7's mock heights for the ring notes, against the build.** With S0's words the lineups' ring notes measure 640 px at 1280×800 (main 656), 832 at 390×844 (main 848) and 1,040 at 320×640 (main 1,040). The mock gives 634, 826 and 1,066. The mock's narrowest pane is 288 px wide; the build's at 320×640 is 296. The lineups' "Not on the chart" line goes from 48 to 32 px at 1280×800 and from 64 to 48 at 390×844. At 320×640 it stays 64 px, four lines with "chart)." alone on the last, so the fix saves no height there.
13. **S0 moves the baselines of S2, S3 and S5.** §5.7's "Before" column is main's. Wrapped, the condenser's four buttons and the new sentence take 276 px at 1280×800, 336 at 390×844 and 452 at 320×640; before, the buttons took 176, cut off at the pane's edge. So, in the condenser:
    - the card header to the station's first value: 3,522 → 3,622 px at 1280×800, 4,050 → 4,210 at 390×844, 4,618 → 4,894 at 320×640;
    - the open card: 7,503 → 7,603 px at 1280×800.

    The lineups' two buttons and the sentence take 108 px at 1280×800 and 390×844 and 134 at 320×640 (88 before). Its figure is 16 px shorter at 1280×800 and 390×844, from the "Not on the chart" line. So, in the lineups:
    - the group canvas to its Show data table (S2's row): +7,416 → +7,400 px at 1280×800 and +11,729 → +11,713 at 390×844, so the row's "Before" is now +6,481 to +11,713; the condenser's is unchanged, +6,481 at 1280×800 and +9,672 at 390×844 (item 10);
    - the ring notes (S3's row): 656 → 640 px at 1280×800 (item 12).

    S3's "Other groups found: {n}" takes the height back wherever two groups or more are found, which is both views.
14. **What the after screenshots show,** for S3, which rebuilds the members (§5.3):
    - the condenser's four buttons read as a block of blue names, 2 to 6 lines each; two of them differ only in their last words;
    - the quiet button's `px-2` starts each button's text 8 px right of the hint above, the new sentence and the figcaption (805 against 797 px at 1280×800; 33 against 25 on the phones);
    - the row has `gap-x-2` only, so stacked buttons touch: at 1280×800 a focused button's 2 px outline, at its 2 px offset, overlaps the next button's box by 4 px;
    - the sentence comes after the buttons, so a sighted reader meets them before learning what one does; at 320×640 it leaves "ticked." alone on a second line;
    - nothing is clipped: every button wraps inside the card, and the focus ring is whole at 320×640.
15. **The screenshots committed** (§9 S0, the record). Five crops of the before state, at CSS pixels, in [`pumps-results-layout/`](pumps-results-layout/), each under 120 KB:
    - the condenser's card from its top, with the four buttons cut off at the pane's edge: [`before-condenser-1280x800-card.png`](pumps-results-layout/before-condenser-1280x800-card.png) (512 × 717), [`before-condenser-390x844-card.png`](pumps-results-layout/before-condenser-390x844-card.png) (390 × 733) and [`before-condenser-320x640-card.png`](pumps-results-layout/before-condenser-320x640-card.png) (320 × 749);
    - the lineups' card from its top at 320×640, its first button cut off: [`before-lineups-320x640-card.png`](pumps-results-layout/before-lineups-320x640-card.png) (320 × 485);
    - the one-off view from the pump canvas down at 1280×800: [`before-one-off-1280x800.png`](pumps-results-layout/before-one-off-1280x800.png) (512 × 867).

    The full-length before and after images were stitched from the probe's screens by a script outside the repository, and are not committed.

**S0, measured** on the e2e build in Chromium, main `2f5e1e3` → this branch. The pane is 480 px wide with a scroller of 512 × 666 px at 1280×800, 366 with 390 × 620 at 390×844, and 296 with 320 × 416 at 320×640, in every view. "Holds" is the scroller's `scrollWidth` in its `clientWidth`. "Sticking out" counts the shown elements below the pump canvas, outside any inner box that scrolls or clips sideways (`overflow-x` `auto`, `scroll` or `hidden`), whose box passes the tab's edge by more than 1 px. Heights in px. A cell with one value is the same before and after.

| View | Size | Holds | Sticking out | Below the pump canvas | Open card | Paragraphs (words) | Controls | Tab stops |
|---|---|---|---|---|---|---|---|---|
| condenser, after Add cases | 1280×800 | 1,223 in 512 → 512 in 512 | 4 → 0 | 8,356 → 8,456 | 7,503 → 7,603 | 28 (1,409) → 29 (1,417) | 50 | 51 |
| condenser, after Add cases | 390×844 | 1,219 in 390 → 390 in 390 | 4 → 0 | 11,687 → 11,847 | 10,698 → 10,858 | 28 (1,409) → 29 (1,417) | 50 | 51 |
| condenser, after Add cases | 320×640 | 1,219 in 320 → 320 in 320 | 4 → 0 | 14,329 → 14,605 | 13,164 → 13,440 | 28 (1,409) → 29 (1,417) | 50 | 51 |
| lineups, everything open | 1280×800 | 512 in 512 | 0 | 12,391 → 12,395 | 10,282 → 10,286 | 54 (3,210) → 55 (3,210) | 57 | 69 |
| lineups, everything open | 390×844 | 390 in 390 | 0 | 18,044 → 18,048 | 14,983 → 14,987 | 54 (3,210) → 55 (3,210) | 57 | 69 |
| lineups, everything open | 320×640 | 344 in 320 → 320 in 320 | 1 → 0 | 21,222 → 21,268 | 17,765 → 17,811 | 54 (3,210) → 55 (3,210) | 57 | 69 |
| one-off, defaults | 1280×800 | 512 in 512 | 0 | 859 | closed | 10 (243) | 14 | 14 |
| one-off, defaults | 390×844 | 390 in 390 | 0 | 1,095 | closed | 10 (243) | 14 | 14 |
| one-off, defaults | 320×640 | 320 in 320 | 0 | 1,295 | closed | 10 (243) | 14 | 14 |

- **What sticks out on main:** in the condenser, the four "Also found" buttons, their right edges at 558, 774, 991 and 1,207 px; in the lineups at 320×640, "Also found: Pump P2, Pump P3 and Pump P4", from 13 to 332 px.
- **The page** never scrolls sideways, in any view at any size, before or after.
- **Unchanged:** the headings below the pump canvas (3 in the condenser and the lineups, 1 in the one-off), the outline and the Tab-stop list in each view; every position on the pump chart; the inner boxes that scroll sideways inside the tab (lineups 3, 2 and 4; condenser 2, 1 and 1); the one-off view, identical at every size.
- **The words:** the condenser gains the new sentence's 8 words; in the lineups the fix removes 8 words and the sentence adds 8.

**S0, the failing-first test.** `tests/pumps-layout.e2e.ts` on main's code failed 3 tests and passed 3 (2.6 min). The assertions that failed, from the run's output, each error's message, expected and received on one line:

```
Error: the width the Results pane's scroller holds, 3-condenser at 1280x800   Expected: <= 512   Received: 1223
Error: the width the Results pane's scroller holds, 3-condenser at 390x844    Expected: <= 390   Received: 1219
Error: the width the Results pane's scroller holds, 3-condenser at 320x640    Expected: <= 320   Received: 1219
Error: the width the Results pane's scroller holds, 2-lineups at 320x640      Expected: <= 320   Received: 344
```

Every other check passed: the one-off view at every size, and the lineups at 1280×800 and 390×844. The second measurement of main gave the same three failures (3.1 min). On this branch the file passes, 6 tests (3.0 min).

**S0, proof** (from `apps/web`):

- `pnpm check`: 832 files, 0 errors, 0 warnings. `pnpm lint`: Prettier and ESLint clean.
- Vitest, the whole suite once: 134 files, 2,013 tests passed (136.8 s), none timed out. The files the slice touches or that read its words: `PumpGroupChart.svelte.test.ts`, `pump-group-others.test.ts`, `pump-group-one-off.test.ts`, `pump-group-chart.test.ts`, `PumpGroupOneOff.svelte.test.ts` and `PumpGroupView.svelte.test.ts`, 175 tests. The image and the export: `chart-image.test.ts`, `export/pump-groups.test.ts`, `export/fixture.test.ts` and `pump-group-system.test.ts`, 81 tests, none changed.
- The assertions moved, each to the fixed sentence exactly, with the same `toEqual` over the whole notes: `pump-group-others.test.ts:304`, "Not on the chart: Both pumps off (not on the chart (unticked under Cases on this chart))." → "Not on the chart: Both pumps off (unticked under Cases on this chart)."; `:1287`, the same change for `NAMES.S7` and `NAMES.S8`. `o.words` is unchanged, and so are the tests that hold it: `pump-group-one-off.test.ts:399`, which pins it, and the synthetic `o.words` given as input at `PumpGroupChart.svelte.test.ts:1204` (which was `:1172`) and at `pump-group-others.test.ts:297`, the input of `:304`.
- E2E, on one worker. On this branch: `tests/pumps-layout.e2e.ts` 6 passed. On main's code and on this branch: `tests/pump-groups.e2e.ts` 27 passed and 1 skipped (the phone-only test on desktop), with the stronger `noSidewaysScroll`.
- Not run in this slice: the whole Playwright suite and axe with every disclosure open, which §9 asks before a web slice is merged.
- Nothing under `apps/api/src` changed. `METHOD_VERSION` stays 1.6.0 and `schemaVersion` 1.

**S0, after its review** (2 findings, both refuted; nothing changed). A review of the slice's tests made two findings. A check of each against this text, `ui-guide.md`, the decisions and GOALS found neither a fault of S0: the build holds what §9 S0 asks. Each names a check a later slice may add:

- No e2e test asserts that the "Also found" buttons are drawn, so once S3 puts them behind "Other groups found", the condenser test could pass without them. The lineups view still guards them: it opens every closed disclosure, so it would open "Other groups found" (two groups) and fail at 320×640 on a button that does not wrap. The unit tests pin the buttons and their names, and §10 S3 opens the disclosure first in the moved tests.
- No test tells the sentence visible from visually hidden. It is a `.hint` (`routes/layout.css:89`), so it is visible. jsdom has no Tailwind CSS, and `toBeVisible` cannot tell `sr-only` text from shown text, for this hint or any other.

**S1, as built** (`web/pumps-layout-chart`; the build `e40cdec`, the header, the reading controls, the strip, the actions and the notes, and `bab2ba0`, the data region, the other cases and the heading "Results per pump"; the review's fixes `54dcb6d` and `a0c8e3e`; measured at `88fafd2`, whose code is `a0c8e3e`'s):

16. **Its own branch** (§9). S1 is on `web/pumps-layout-chart`, stacked on `web/pumps-layout`, so S0 could take its review and its records while S1 was built. S0's code came in by fast-forward at `b1c3756`; its later commits came by the merges `22014a3` and `88fafd2`, which add only docs.
17. **The select is native** (§5.3 item 2). PumpsView draws a `<select class="input pr-8">`, `aria-labelledby` the h3 and `aria-describedby` its sentence, in place of SelectField, which draws a label of its own. So its name comes from the h3 and its description from the visible sentence. The h3 "Pump chart" (16 px semibold, tabindex −1) is drawn with one pump too; the select and its sentence only with more than one. The row is a container: the select sits beside the h3 from 21 rem and under it below.
18. **The heading "Results per pump"** (§5.3 item 1). The h3 (16 px semibold, tabindex −1) and the table share a `space-y-2` div (`data-pump-table`), not a landmark. The table keeps its visually hidden caption, its name. Its note stays a sibling in the tab's column, so its 16 px gap after the table is unchanged.
19. **The chips** (§5.3 Reading). Pressed: `border-blue-700 bg-blue-50 text-blue-900`, with a 16 px `Icon name="check"` before the word (`aria-hidden`, as every `Icon` is). Not pressed: `.btn`'s own slate-300 outline on white. The "Show" label is 12 px medium. The words are unchanged.
20. **The readout** (§5.3 Reading, §5.5). One `<p data-pump-readout>`, laid out as a grid in a container: the lead "At the duty {flow}:" on a row of its own, then the pairs one per row below 26 rem and two per row from it. Each pair is `whitespace-nowrap` at 14 px, its label slate-600 and its value medium. §5.3 drew inline pairs that wrap; the mock wraps them freely.
    - The hidden separators stay ",&nbsp;", today's text, not ", ". Svelte trims a plain space at the end of the `sr-only` span, and ESLint's `svelte/no-useless-mustaches` forbids `{', '}`.
    - Chromium's accessibility tree puts a space before each hidden comma ("22.76 m , System head"), as it did for today's flex items. The text content and the slider's `aria-valuetext` are unchanged.
21. **The strip takes no room while idle** (§5.3 The strip: "nothing visible when idle"). Its wrapper (`data-pump-strip`) is `sr-only` while it has nothing to show, not an empty row. So it adds no gap to the figure's column, and its live line stays in the accessibility tree.
22. **A request line's mark is inside its live span** (§5.2 Placement against §5.3's markup rules). The spinner or the ⬣ (`Icon name="octagon"`) is the span's first element, before its words, so the span stays its row's first child. §5.2 puts a mark before its sentence's element, which here would come before the row's first child. The span is `inline-flex items-start` and the 14 px icon `mt-px`, so the mark sits at the sentence's first line however it wraps (the review's L2). S3's request lines are to take the same rule.
23. **Cancel is described by its line** (§5.3 markup rules: "described by it"). Before S1 only the button that computes again had `aria-describedby`.
24. **A line mounted as its request starts holds back its words** (§7 Live regions; the review's A11Y-1). PumpsView mounts the chart in the update that starts its system curve: when the Pumps tab opens, and when a pump is chosen (`{#key viewed.key}`). A polite line inserted already speaking is not announced, so F17 was still open on those two paths.
    - Each live line now shows its progress words only from the second animation frame after the chart mounts (`linesDrawn`), so it is drawn empty first. A one-frame hold was tried: both new unit tests fail on it.
    - Only progress waits. A failed or cancelled state present at mount shows at once.
    - Cancel and Try again are not held back, so the focus handovers are unchanged.
    - The other cases' line follows the same rule.
25. **`aria-busy` with no canvas** (§5.3 item 2). It is the canvas wrapper's, as §5.3 says. Where the chart's chunk failed to load or the chart cannot be drawn there is no canvas, so nothing in the figure is busy while the curve loads; before S1 the figure was. The live line still says the wait (the review's STRUCT-2, refuted).
26. **The data table button's hidden suffix** (§5.3 Actions). It is `<span class="sr-only">of the pump chart</span>` after a space outside it, not `<span class="sr-only"> of the pump chart</span>`, so every name computation keeps the space. The names are "Show data table of the pump chart" and "Hide data table of the pump chart"; the visible words are unchanged.
27. **Download image and its reason are one item** (§5.3 Actions, §5.5; the review's L3). §5.3 puts a lasting reason "beside it". In the wrapping row it fell under Show data table at every viewport width measured from 390 to 1,440 px, in the notes' type, so it read as the first note.
    - Now the button and its reason share one item of the actions row (`flex flex-1 flex-wrap`). The reason sits beside the button where it fits on the line, else under the button, never under Show data table. At 1280×800 and 390×844 it goes under.
    - A lasting reason, now visible, is no longer also the button's `title`. The passing ones, "Wait until the system curve is computed, or cancel it." and "The chart is being drawn.", stay `sr-only` and in `title`.
28. **One tone for the notes** (§5.2). Every note is slate-700, the method sentence included. Before S1 the method, the dashed note, the facts, the panels' notes and the limits were slate-600. "Trace of {pump}" is a button drawn as an inline link: underlined, with no `min-h-11` and no padding.
29. **The design-check limits** (§5.3 Notes). "Design-check limits drawn" is a 12 px medium `<p>` heading its block (`data-pump-checks`): the limit notes, the closing sentence, then Go to Checks.
    - Go to Checks is drawn only when the solve has design-check results, since the Checks view exists only then, and only where ResultsPanel hands PumpsView its `showView` (the new `onview`). It shows Checks and focuses its tab.
    - Where no canvas is drawn the block still shows, with the chip hidden, as the limit notes did before S1 (the review's STRUCT-1, refuted).
30. **The notes' order comes from `valueNotes`** (§9 S1: "a small pure helper over the same data"). It sorts chartNotes' own sentences into the screen's groups. It finds the first group by building those sentences again with `risingNote` and `npshCrossingNote`, which were taken out of `factNotes` and `panelNotes` with the same words. chartNotes' output and order are unchanged, so the image's footer is too (`imageNoteLines`).
31. **"Operating points by case"** (§5.3 The data region).
    - It takes Running combinations' pattern: explicit ARIA roles, `data-label` cells and a list below 640 px, its box `max-sm:overflow-visible`. It keeps `tabindex="0"`, as today; S7 makes a box a Tab stop only while it overflows.
    - The bare number under "Speed (%)" is made at its source: `otherCasesData`'s `row.speed` lost its " %". Only this table reads it; the image's footer and the export do not.
    - On a phone a row leaves out its "—" cells, as every list does (ui-guide, Phones), so an off case's row reads "State Off" alone.
32. **The shown case's tables are one column at the desktop split** (§5.5, F11). They go two-up only from a 40 rem container. So the lineups' pump card with the tables open is taller at 1280×800: 2,093 → 2,742 px below the canvas.
33. **The Details' subject in another case's table** (§6.2). The shown case's Why no head Details are named "Details of the point at {flow} {unit}". Another case's are "Details of the point at {flow} {unit}, {case}": the other cases' curves share the shown curve's flow grid, so their names would repeat. `IssueDetail` gains an optional `subject`; its other callers are unchanged.
34. **The tag keeps its ●** (§5.3 Other cases). It reads "● {case} (shown)": the `aria-hidden` ● is the chart's filled operating-point marker. The mock dropped it. The words are unchanged.
35. **The case grid is no container** (§5.5). `grid-cols-[repeat(auto-fill,minmax(13rem,1fr))]` needs none, so the page has one container fewer than §5.5 allows.
36. **The off note sits under the name** (§5.3: "beside its box"). "(off in this case: no operating point)" is a `<p>` in the box's grid item, under its name and outside its label. In a 13 rem column it wraps to two lines, so it cannot share the box's line. Its id comes before the cap's in `aria-describedby`.
37. **The overlay's cost is indented under its label** (`pl-6 -mt-1`, 12 px slate-600), as in the mock, rather than `.hint` at the box's edge. The other cases' live-line row is `sr-only` while idle, as the strip is.
38. **Hooks for the tests:** `data-pump-chart` (the card), `data-pump-table`, `data-pump-readout`, `data-pump-strip`, `data-pump-notes`, `data-pump-method`, `data-pump-checks`, `data-pump-data`, `data-pump-others`, `data-overlay-row` and `data-overlay-state`.
39. **Reduced motion reaches IssueDetail's other callers.** Its chevron's `motion-reduce:transition-none` applies wherever it is drawn: the topology issues in Results, the goal-seek result and the Pumps together card. The two spinners are `motion-safe:animate-spin`.
40. **How §10's S1 list was met.**
    - `PumpChart.svelte.test.ts:428` (§10: "read the summary by its new text") needed no change. `getByText('Details')` matches the summary's own text node, which is still "Details". The summary's full name is now asserted after it.
    - No test read the data region's tables by position, so none moved for the new order.
    - S1's browser checks run inside S0's three view tests, at each size, with soft assertions. Their titles gain "; the pump chart holds its budget".
    - The words-on-screen guard (§10) is a unit test, since it needs chartNotes' own input, which an e2e test cannot build. Its helpers, `outOfSight` and `wordsInSight`, are in `src/lib/testing/helpers.ts`, for S3's guard too.
41. **§5.7 row 2, measured.** The estimate was about +190 px idle on a desktop and +320 on a phone. Measured: +196 px in the lineups and the condenser and +248 in the one-off at 1280×800, and +308 in all three at 390×844. At 320×640: +308 (lineups, condenser) and +360 (one-off).
42. **§5.5's "Chips wrap to two rows", measured.** Each pressed chip is 24 px wider for its check.
    - Three chips (lineups, condenser): one row at 1280×800, two at 390×844 and 320×640. On main: one, one and two.
    - Four chips (the one-off, with Design checks): two rows at 1280×800, "Design checks" alone on the second; two at 390×844; three at 320×640 (148 px). On main: one, two and two.
    - The review's L1 drew the mock's chips at these widths and got the same rows, so it was refuted (below).
43. **§5.7 row 7's "5 in the tab", measured.** The pump chart's notes are one run of 9 paragraphs and 197 words in the one-off (324 px at 1280×800), 6 and 142 in the lineups, and 5 and 136 in the condenser. "Design-check limits drawn" is a `<p>`, so it does not break the run. As built, the one-off fails S3's "≤ 6 in the tab"; S3 settles it when it sets that budget.
44. **What the after screenshots show,** for the later slices and the owner (deviceScaleFactor 1):
    - At 390×844 in the condenser, the select beside the h3 shows "Condenser water pump" and cuts "CWP-1", the only part that tells the six pumps apart. On main it was full width under its label and showed the whole name. At 320×640 both cut it to "Condenser water pump CW".
    - Wrapped chips start under the word "Show", not under the first chip, since the label is an item of the same row.
    - The default view grew. In the one-off with the card closed, the area below the pump canvas is 859 → 1,096 px at 1280×800 (+28 %), 1,095 → 1,308 at 390×844 and 1,295 → 1,488 at 320×640. The wrapped chips, the readout (128 px against 80 at 1280×800) and the other cases' section (309 px against 188 on main: its h4, its rule, the tag and 44 px rows) account for 221 px of the 237 at 1280×800. No budget holds the pump card's height.
    - With the lineups' data table open, the other cases come after the data region: "Also show the other cases' system curves" is at +2,663 px at 1280×800 (+674 on main), +3,129 at 390×844 and +3,301 at 320×640. That is §5.1's order; S7's table disclosures shorten the region.
    - In the case grid at 1280×800, long names leave one word alone on a line ("off)", "P4 off)"), and a two-line off note makes the rows uneven.
    - At 320×640 the overlay's cost sentence sits right against the second line of its label.
    - In "Operating points by case" at 1280×800, "Flow (L/s)", "Head (m)" and "Speed (%)" each wrap to two lines, between the word and the unit, and long case names wrap to three.
    - For S8: the list's ☆ against the chart's ✳; □ and ▢ alike; in the one-off, Pump PA's two off cases take two of the chart's five other-case slots and draw no point (F25). The canvas labels' collisions are the owner's items 107 and 108 (§12).
45. **S1 changes nothing on the card.** Against S0's after record, every position on the Pumps together card, its height, its station and its Tab stops are unchanged.
46. **The screenshots committed** (the record). Three crops of the one-off view after S1, from the pump canvas down to the tab's end, at CSS pixels (deviceScaleFactor 1), in 64 colours, each under 45 KB, in [`pumps-results-layout/`](pumps-results-layout/):
    - [`after-one-off-1280x800.png`](pumps-results-layout/after-one-off-1280x800.png) (512 × 1104), beside S0's [`before-one-off-1280x800.png`](pumps-results-layout/before-one-off-1280x800.png) (512 × 867);
    - [`after-one-off-390x844.png`](pumps-results-layout/after-one-off-390x844.png) (390 × 1316);
    - [`after-one-off-320x640.png`](pumps-results-layout/after-one-off-320x640.png) (320 × 1496).

    They were cut from screens stitched by a script outside the repository, as S0's were. The full before and after images of all nine views are not committed.

**S1, measured** on the e2e build in Chromium, main `2f5e1e3` → this branch at `88fafd2`, by `tests/pumps-layout.e2e.ts` in record mode. In every view the pane is 480 px wide with a scroller of 512 × 666 px at 1280×800, 366 with 390 × 620 at 390×844, and 296 with 320 × 416 at 320×640, as for S0. The pump canvas is 624 px tall at 1280×800 and 544 at the two phone sizes, unchanged. Heights and positions in px, each below its own chart's canvas. "Show data table" is S1's budget, ≤ 300 at 1280×800 and ≤ 400 at 390×844 (§5.7 row 2); none at 320×640. A cell with one value is the same before and after.

| View | Size | Show data table | Below the pump canvas | Pump card below its canvas | Headings below | Paragraphs (words) | Controls | Tab stops |
|---|---|---|---|---|---|---|---|---|
| condenser, after Add cases | 1280×800 | 780 → 196 | 8,356 → 8,453 | 837 → 834 | 3 → 4 | 28 (1,409) → 29 (1,417) | 50 | 51 |
| condenser, after Add cases | 390×844 | 916 → 308 | 11,687 → 11,976 | 973 → 1,102 | 3 → 4 | 28 (1,409) → 29 (1,417) | 50 | 51 |
| condenser, after Add cases | 320×640 | 1,048 → 308 | 14,329 → 14,694 | 1,149 → 1,238 | 3 → 4 | 28 (1,409) → 29 (1,417) | 50 | 51 |
| lineups, everything open | 1280×800 | 748 → 196 | 12,391 → 13,044 | 2,093 → 2,742 | 3 → 4 | 54 (3,210) → 56 (3,217) | 57 | 69 |
| lineups, everything open | 390×844 | 900 → 308 | 18,044 → 18,227 | 3,045 → 3,224 | 3 → 4 | 54 (3,210) → 56 (3,217) | 57 | 69 |
| lineups, everything open | 320×640 | 1,092 → 308 | 21,222 → 21,223 | 3,441 → 3,396 | 3 → 4 | 54 (3,210) → 56 (3,217) | 57 | 69 |
| one-off, defaults | 1280×800 | 716 → 248 | 859 → 1,096 | 773 → 1,010 | 1 → 2 | 10 (243) → 13 (260) | 14 → 15 | 14 → 15 |
| one-off, defaults | 390×844 | 952 → 308 | 1,095 → 1,308 | 1,009 → 1,222 | 1 → 2 | 10 (243) → 13 (260) | 14 → 15 | 14 → 15 |
| one-off, defaults | 320×640 | 1,108 → 360 | 1,295 → 1,488 | 1,209 → 1,402 | 1 → 2 | 10 (243) → 13 (260) | 14 → 15 | 14 → 15 |

- **The budget holds** in every view at both sizes, with 52 px to spare at the least (the one-off at 1280×800).
- **Download image** is beside Show data table at 1280×800 and 390×844. At 320×640 it drops under it: one-off 1,152 → 408, lineups 1,136 → 356, condenser 1,092 → 356.
- **"Also show the other cases' system curves"** moves down, since the other cases now come last: one-off 642 → 931, 878 → 1,127 and 1,018 → 1,307; lineups, its data table open, 674 → 2,663, 826 → 3,129 and 1,002 → 3,301; condenser 706 → 755, 842 → 1,007 and 958 → 1,143 (at 1280×800, 390×844 and 320×640).
- **"Below the pump canvas" counts the Pumps together card too,** and the card's part of the change is S0's (item 13; S1 changes none, item 45): the condenser's card is 100, 160 and 276 px taller, the lineups' 4, 4 and 46. The rest is the pump card's.
- **Sideways.** Neither the page nor the pane's scroller scrolls sideways in any view at any size, as after S0. Nothing sticks out of the tab. The inner boxes that scroll sideways: lineups 3, 2 and 4 → 3, since at 320×640 "Operating points by case" is a list and no longer scrolls (303 px in 268 before); condenser 2, 1 and 1. No box of the pump chart scrolls sideways.
- **The outline,** in every view and size: h3 "Results per pump" and h3 "Pump chart", above the canvas, neither there on main; h4 "Other cases on the pump chart" in the figure, the group "Cases on the chart" under it; then h3 "Pumps together …". Outline entries below the canvas: 4 → 5, 48 → 49 and 24 → 25.
- **The Tab order** below the canvas follows §7: the chips, Read at flow, Show data table and Download image, Trace of {pump}, Go to Checks (the one-off), the data boxes while open, the case boxes and the overlay box, then the card's toggle. Before S1, Trace and the case boxes came before Show data table, Download image and the data boxes. The one-off gains Go to Checks (14 → 15 stops); the lineups keep 69 and the condenser 51. Stops on scroll regions: 0, 13 and 2, unchanged.
- **The longest run of notes:** the one-off's, the pump chart's, 9 paragraphs, 220 → 197 words, 396 → 324 px at 1280×800. The card's run of 13 is unchanged: 837 words in the lineups (845 on main, S0's fix) and 925 in the condenser.
- **The pump figure's blocks** at 1280×800 in the one-off: the chips 44 → 96, the reading 80 → 128, the actions 44, the notes 372 and the other cases 309 (on main the fieldset, 108, and the overlay box, 80).
- **The scale factor.** These are the numbers of record, from the e2e config, whose `mobile` project runs at deviceScaleFactor 3. A run of both builds at 1 gives the same pump chart numbers; only Running combinations differs, as S0's item 10 found.
- **Two commit messages differ from the measurement.** `bab2ba0` gives 308 px at 320×640 in every view; the one-off's is 360, its chips three rows. `e40cdec` gives the pump example's "748 before, §2.1"; 748 is §2.1's lineups at 1280×800, and the pump example is not one of the three views.

**S1, failing first.** No run of the budget checks on main's code is recorded; main's numbers, 716 to 780 px at 1280×800 and 900 to 952 at 390×844, are over the budget in every view. Each fix of the review has a test that failed before it:

- The four new browser tests, run on this branch with `PumpChart.svelte` as it was before the fixes: 6 of 8 failed. The live-line test failed on desktop and phone ("the line inserted, the Pumps tab opened"). The mark test failed at 1280×800 (8.5 px off the first line's middle) and 390×844 (16.5 px). The reason test failed at 1280×800 and 390×844. The notes test passed, since the product showed those notes; with the rising-head and coverage notes hidden in a build, it failed on desktop and phone.
- Vitest: the four live-line tests (two new, two changed in `ResultsViews.svelte.test.ts`) failed on the old code, each finding the progress words where it expected an empty line. So did the mark's and the reason's new class assertions.
- Each change to the product that the review named fails a test: the guard's lines filtered off the screen (3 cases), the notes `hidden` or `max-sm:sr-only` (9 of 9 cases), the off note, the cap, the overlay's cost, the lasting reason and the select's sentence each `max-sm:sr-only` or `sr-only`, the held line moved after the tables, `scroll-shadow-x` taken off the panels' boxes, and the hold cut to one frame. The second check's case, a note's words in a hidden span inside a visible `<p>`, fails 1 test; every note so wrapped fails 9, the limits alone 2. Each change was undone after its run.

**S1, proof** (from `apps/web`, at `a0c8e3e` unless named):

- `pnpm check`: 832 files, 0 errors, 0 warnings. `pnpm lint`: Prettier and ESLint clean.
- Vitest, the whole suite once: 134 files, 2,048 tests passed, none timed out (S0: 2,013). The files S1 changes, counted by running them before and after: `PumpChart.svelte.test.ts` 23 → 52, `ResultsViews.svelte.test.ts` 22 → 23, `ChecksView.svelte.test.ts` 7 → 8 and `utils/pump-chart.test.ts` 16 → 20: 35 new tests. Unchanged and passing: `PumpsView.svelte.test.ts` (6), `PumpChartChunk.svelte.test.ts` (1), `export/chart-image.test.ts` (14), `pump-chart-facts.test.ts` (4), `pump-chart-panels.test.ts` (9), `pump-chart-checks.test.ts` (10) and `pump-chart-config.test.ts` (2).
- E2E, on one worker, one command at a time. At `54dcb6d`, the eight files of §9 S1's proof (`design-checks`, `pump-chart`, `pump-chart-facts`, `pump-system`, `pump-control`, `scenarios`, `cancel` and `export`) and `pumps-layout`, in one command: 74 passed and 2 skipped, the phone-only tests at `cancel.e2e.ts:114` and `export.e2e.ts:335` on the desktop project. At `a0c8e3e`, `pumps-layout`, `pump-system` and `scenarios`: 32 passed. At `88fafd2`, `tests/pumps-layout.e2e.ts` alone: 14 passed (3.2 min), the run of record. The file has 7 tests (3 in S0), 14 with the two projects.
- axe-core (WCAG 2.0 to 2.2 A and AA), at `bab2ba0`, by a probe outside the suite: 0 violations over `[data-pump-chart]` with its data table shown, the other cases' curves computed and every Details opened, in the one-off (10 tables, 2 off notes) and the lineups (11 tables, 3 capped boxes, 1 off note), at 1280×800, 390×844 and 320×640. `heading-order` and `landmark-unique` over the whole Pumps tabpanel: 0. It was not run again after the review's fixes, which change classes and wrap Download image and its reason in one `div`.
- Not run in this slice: the whole Playwright suite, and axe in the suite with every disclosure open, which §9 asks before a web slice is merged.
- Nothing under `apps/api/src` changed. `METHOD_VERSION` stays 1.6.0 and `schemaVersion` 1.

**S1, the assertions that moved.** Each old assertion beside its new one, base `web/pumps-layout` → this branch; none is looser:

- `PumpChart.svelte.test.ts:117` → `:137`, `:246` → `:271`, `:332` → `:360`, `:342` → `:370`, `:372` → `:404`, `:423` → `:457`, `:476` → `:520` and `:575` → `:621`: `getByRole('button', { name: 'Show data table' })` → `getByRole('button', { name: 'Show data table of the pump chart' })`, Testing Library's exact match on the whole new name. `:121` → `:141`, `toHaveTextContent('Hide data table')`, is unchanged and holds.
- `PumpChart.svelte.test.ts:168` → `:192`: `expect(screen.getByRole('figure')).toHaveAttribute('aria-busy', 'true')` → `expect(screen.getByRole('img')).toHaveAttribute('aria-busy', 'true')`. `:178` → `:202` and `:272` → `:300`: the same, with `'false'`. The test of `:272` ("offers Cancel while the system curve is computed…") gains `withCanvas()` (`:279`), since with no canvas nothing carries `aria-busy` (item 25).
- `PumpChart.svelte.test.ts:167` → `:188–190` and `:348` → `:377–379`: `expect(screen.getByText('Computing the system curve for this solve…')).toBeInTheDocument()` → `expect(await screen.findByText('Computing the system curve for this solve…')).toBeInTheDocument()`: the same exact text, which the line now says from the second frame after the mount (item 24).
- `PumpChart.svelte.test.ts:574–576` → `:620–622`: `expect(button().parentElement).toBe(screen.getByRole('button', { name: 'Show data table' }).parentElement)` → `expect(button().parentElement!.parentElement).toBe(screen.getByRole('button', { name: 'Show data table of the pump chart' }).parentElement)`: Download image is in its own item of the same row (item 27).
- `PumpChart.svelte.test.ts:677` → `:723`: `document.querySelector('figure p.text-slate-600:not([id])')` → `document.querySelector('figure [data-pump-method]')`: the same paragraph, with the same equality to `request.notes.method`.
- `PumpChart.svelte.test.ts:742` → `:788–789`: `slider.closest('div.space-y-1')!.querySelector('p')!.textContent!` → `screen.getByRole('figure').querySelector('[data-pump-readout]')!.textContent!`. Every text assertion on it is unchanged.
- `PumpChart.svelte.test.ts:428` → `:463`: `within(details).getByText('Details')`, unchanged. Added after it (`:464–471`): the gpm arithmetic, 0.02 / (231 × 0.0254³ / 60) = 317.006, the summary's whole text "Details of the point at 317 gpm" and its `sr-only` suffix.
- `ResultsViews.svelte.test.ts:499` → `:502–504` and `:587` → `:630`: `expect(panel.getByText('Computing the system curve for this solve…')).toBeInTheDocument()` → the strip's live line asserted empty first (`toBe('')`), then `expect(await panel.findByText('Computing the system curve for this solve…')).toBe(line)`: the same text, on that same element.
- `ResultsViews.svelte.test.ts:582–584` → `:622–624`: `expect(panel.getByRole('figure', { name: 'Pump and system curves: Booster pump' })).toBeInTheDocument()` → `const boosterFigure = panel.getByRole('figure', { name: 'Pump and system curves: Booster pump' })`, which throws if the figure is missing; its line is then asserted empty (`:626–627`).
- `cancel.e2e.ts:235, 250, 279` → `:236, 251, 280`: `expect(chart).toHaveAttribute('aria-busy', …)` → `expect(chart.getByRole('img')).toHaveAttribute('aria-busy', …)`, with the same values, `'true'`, `'false'` and `'true'`.
- `pump-chart-facts.e2e.ts:38`, `pump-chart.e2e.ts:51`, `pump-control.e2e.ts:177`, `scenarios.e2e.ts:221` and `pump-system.e2e.ts:220, 339`: `{ name: 'Show data table' }` → `{ name: 'Show data table of the pump chart' }`. `pump-system.e2e.ts:234`: `{ name: 'Hide data table' }` → `{ name: 'Hide data table of the pump chart' }`. Playwright matches a name as a substring, so the old names would still have matched; the full names are more specific.
- `pump-system.e2e.ts:360` → `:361–363`: `why.getByText('Details', { exact: true })` → `` why.getByText(`Details of the point at ${sig4(point.flow / GPM)} gpm`, { exact: true }) ``: still exact, on a more specific name.
- `scenarios.e2e.ts:239` → `:240–242`: `figure.getByRole('status').filter({ hasText: 'Computing system curves' })` → `figure.locator('[data-overlay-state]')` with `toHaveAttribute('aria-live', 'polite')`, then the same `toHaveText('Computing system curves: 1 of 2…')`. `:247` → `:250–253`: `await expect(progress).toHaveCount(0)` → `await expect(progress).toHaveText('')`, and the button "Cancel the other cases' system curves" `toHaveCount(0)`: the line stays and says nothing, and its Cancel is gone.
- `pumps-layout.e2e.ts:81, 93–97` → `:82, 95`, S0's `settle`: "busy" was a `figure` with `aria-busy="true"`; it is now any element in the tab with `aria-busy="true"`, so it catches the canvas wrapper and still the group chart's figure. The three view tests' titles gain "; the pump chart holds its budget" (`:770, 778, 784` → `:943, 951, 980`).

**S1, after its review** (15 findings: 9 held and were fixed in `54dcb6d`, each with a test that failed before its fix; 6 refuted; a second check of the fixes made 1 finding, fixed in `a0c8e3e`). Each finding was checked against this text, `ui-guide.md`, the decisions and GOALS.

- **Held and fixed:**
  - A11Y-1 (major): the system curve's line was inserted already saying "Computing…" when the tab opened and when a pump was chosen, so F17 was still open there. Item 24.
  - L2: the failed request's mark was centred on its wrapped sentence. Item 22.
  - L3: the lasting image reason wrapped under Show data table, in the notes' type. Item 27.
  - words-1: the words-on-screen guard never read five chartNotes lines: the speed range, the efficiency at another speed, no best efficiency point marked, an extrapolated shutoff head, and NPSHa still to come. It now passes `speedShown` and has three more cases (6 → 9), each naming the lines it must read.
  - MUT-1 (major): the guard took a note hidden by `display: none` (Tailwind's `hidden`) as on screen, and no browser test read the rising-head, NPSHa-crossing or coverage lines. `outOfSight` now reads every hiding class at any breakpoint; the browser checks give every note and hint a box of its own at each size; a new browser test reads those three lines.
  - MUT-2: the "visible" checks on the off note, the cap, the overlay's cost and the lasting reason passed with `max-sm:sr-only`. Each also asserts `outOfSight` false, and the browser checks measure their boxes.
  - MUT-3: the select's cost sentence could be made `sr-only` unseen. The same two checks now hold it.
  - MUT-5: nothing held "Held at zero flow: …" at the top of the data region. A new test does.
  - MUT-6: "every box shades its edges" read 4 boxes. A new test reads all 9 of a speed-controlled pump with every panel.
- **Refuted,** each with what a later slice may add:
  - STRUCT-1: the limits' label and Go to Checks show where no canvas is drawn. §5.3 keeps the notes there, and the verdicts are in Checks either way (item 29).
  - STRUCT-2: no `aria-busy` where no canvas is drawn. §5.3 and §7 move it to the canvas wrapper and ask nothing of a stand-in (item 25).
  - L1: the chips take a row more. The mock's chips give the same rows at every width, and the check is §5.3's answer to F20 (item 42).
  - MUT-4: no test pins the strip's order. One of the two orders it named cannot be seen (the coverage line and a request line never show together); the other was correct and untested before S1. §10 asks for neither.
  - MUT-7: no test that the notes carry no mark. The notes are plain, and §10 asks that test of S5's tables only.
  - MUT-8: no test of the reduced-motion classes. §10 asks none; the app's other spinners and chevrons have none.
- **The second check:** S1-FIX-1, the guard read a paragraph's whole text, so a note's words in a hidden span inside a visible `<p>` still passed. `wordsInSight` reads only the words in sight, and the guard has a test of its own. Left as seen: the checks that find a hint or a reason by its id test that element alone, so its words in a hidden child would still pass; the checks that find one by its text do not have that gap.
