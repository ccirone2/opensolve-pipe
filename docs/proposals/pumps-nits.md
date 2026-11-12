# Pumps tab nits

**Status: items 1, 2 and 3 and the first part of item 5 (slice 5a) built (2026-11-12), web only, on `web/pumps-nits` (§4 to §8 are the as-built record, §9 the review); item 4's API half built on `ccr-efab8cb5-vzm6cg`; item 4's web half (slice E) and item 5's slices 5b and 5c not built.** No decision. `METHOD_VERSION` unchanged (1.6.0), `schemaVersion` 1, nothing new in the link, no new dependency. The owner answered the plan's three questions on 2026-11-12 (§2). Everything else is the designers' web defaults, reversible under D14. Follows [`../ui-guide.md`](../ui-guide.md).

## 1. Scope

**The owner's request (2026-11-12), verbatim.**

> "Nits. 1- when clicking the buttons to show npsh, efficiency, power the button changes with and usually causes a vertical shift of the buttons when in Mobile view. Find a way to not incur a vertical shift. 2- and the per pump results table, use a colored pill to indicate status.  3- again in the results table, make the default Fields not include in psha and npshr and hydraulic power. 4- add NPSH margin as a ratio and make it a default in the results table. Don't make absolute margin a default. 5- in general, I don't like the use of special characters to designate pumps and groups. These are very confusing to distinguish."

**Already decided, not re-opened.** Every solved value keeps its trace and stays one step away (D10): a field hidden by default is still in the trace and the export. A Fields choice is a per-viewer convenience in this browser's storage, never project data and never in the link (D3, GOALS §4.5). Nothing stored before is migrated (D14). The web app computes no hydraulic value (the header of `utils/results.ts`; D17), so the NPSH margin ratio comes from the API (item 4). Phones and desktops are equal (GOALS §4.7).

**The designers' defaults (the plan's, reversible under D14).**

| Item | Defaults |
|---|---|
| 1 | A checked box when on, an empty box when off (a plain check when on has the same geometry). The tall-window limit is accepted (§4.5). |
| 2 | The state word only in the pill, the qualifier as plain text after it. Green Running, slate Off, red No flow; the pill ignores the row's flags. Borderless. Results per pump only. |
| 3 | Choices stored as departures from the defaults. A "Default fields" button. A Summary link shows the column it sorts by. |
| 4 | An API field. Plain, 4 significant figures. Null where NPSHr = 0. In the export and as a Compare quantity. No goal-seek target. `METHOD_VERSION` unchanged. |
| 5 | "Base" for the base case. Boxed case numbers. Dashed readout rings. The held diamond kept. Six distinct line patterns. No label dropped silently. |

## 2. The owner's answers (2026-11-12)

Each is the plan's recommended option. As the session recorded them, verbatim:

> Q1 nit 5: the chart point shapes go too ('Shapes go too'; slices 5b and 5c); Q2: one case number per case for the whole Pumps tab, 'Base' then 1..n by place in the Scenarios list, every list in that order ('By list place'); Q3: the NPSH ratio everywhere, i.e. Results per pump (margin hidden by default), Summary's per-pump line and its 'Smallest NPSH margin' link, Build's result strip, Compare's default pump row ('Ratio everywhere'; slice E, after the API field merges and the owner redeploys the API).

| Question | Answer |
|---|---|
| Q1. Item 5's reach: do the chart shapes go too, or only the typed characters? | **"Shapes go too"**: the chart point shapes go too (slices 5b and 5c). |
| Q2. Case numbers and the order of the lists | **"By list place"**: one case number per case for the whole Pumps tab, "Base" then 1 to n by place in the Scenarios list, every list in that order. |
| Q3. Should the other default NPSH readings move to the ratio as well? | **"Ratio everywhere"**: the NPSH ratio everywhere, that is Results per pump (the margin hidden by default), the Summary's per-pump line and its "Smallest NPSH margin" link, Build's result strip and Compare's default pump row (slice E, after the API field merges and the owner redeploys the API). |

## 3. The plan in brief

The plan (written against main `673d266`) cut the five nits into eight slices, each to ship on its own with a test that fails first and every gate green:

| Slice | Item | Content | Built |
|---|---|---|---|
| A | 1 | One box mark in both states of a Show chip; `pressChip` holds the chip under the pointer; the data table button's word swap measured, and held to one width if it moves anything | `web/pumps-nits`, `9016510` |
| B | 2 | `pumpStatusParts`, `PUMP_STATUS_TONES` and a `statusCell` snippet in Results per pump | `web/pumps-nits`, `1a4f5ae` |
| C | 3 | `Column.hiddenByDefault` on Hydraulic power, NPSHa and NPSHr; the choice stored as departures; Default fields; the count over the table's own columns; a sort request shows the hidden column it sorts by. NPSH margin stays shown until E | `web/pumps-nits`, `3e45090` |
| D | 4 (API) | `PumpResult.npsh_margin_ratio`, its trace and methods words, unit tests and the corpus comparison | `ccr-efab8cb5-vzm6cg`, `d5b49f9` and its review's `12e087f` (§7) |
| 5a | 5 (part) | Slot-symbol columns out of "Pumps in the group", the Station table and Running combinations; ● out of the duty sentence and the "(shown)" tags; BEP and shutoff in words; slot 3's star stroked in its colour; a guard | `web/pumps-nits`, `defe620` |
| E | 4 (web), 3 | The ratio shown by default and NPSH margin hidden by default, everywhere Q3 names | not built: waits for D to merge and the owner's API redeploy |
| 5b | 5 (part) | Case numbers by place in the Scenarios list (Q2), the same on both charts and in every list; numbered slate rings in place of the pump chart's △ □ ✳ × ▽ | not built |
| 5c | 5 (part) | Pumps as dots in their line's colour, named beside them by one label placer for both charts; the shapes go (Q1) | not built |

The plan gave A, B, C and 5a a branch each (`web/pump-chip-hold`, `web/pump-status-pill`, `web/pump-fields-default`, `web/pump-names-no-marks`). The session built them on one branch, `web/pumps-nits` from main `673d266`, one commit per item, then reviewed the four together and fixed what held in `a0d1b38` (§9).

## 4. Item 1: the chips hold still (slice A)

### 4.1 Measured on main

Two causes, measured in the one-off project (Pump PA, four chips) by the new e2e test on `673d266` (`run-main.log`, 242 soft failures over both projects):

1. **Width.** The check was drawn only on a chip that was on, so a press changed the chip's width by 24 px (a 16 px icon and an 8 px gap) and could rewrap the row: at 1280×800 Design checks off took the row from 96 to 44 px; at 390×844 NPSH off moved it up a line and 255 px sideways; at 320×640 Shaft power off took the row from 148 to 96 px.
2. **Canvas height.** Efficiency, Shaft power and NPSH each make the canvas above the chips a panel taller or shorter (`chartHeightRem`), so every press of one moved the whole row 112 px on a desktop and 96 px on a phone. Chrome's scroll anchoring did not take it up in any run.

### 4.2 As built

- **One mark in both states.** Each chip leads with one 16 px `aria-hidden` mark: `Icon name="box-check"` in blue-700 on the filled chip when on, `Icon name="box"` in slate-500 on the outlined chip when off (4.76:1 on white, the plan's figure). A press changes no chip's size, and each chip keeps its old on-width (116.2, 130.6, 89.0 and 148.4 px), so the default wrap is unchanged: 3 rows (148 px) at 320×640 and 2 (96 px) at 390×844 and 1280×800 in the one-off. The words, the accessible names and `aria-pressed` are unchanged.
- **The chip held under the pointer.** `pressChip` (`PumpChart.svelte`) reads the chip's top, toggles the panel, waits a tick and scrolls the chip's scroller by what the chip moved, as `switchOverlay` already did. A press from the keyboard is held the same way.
- **The data table buttons, one width.** The plan asked for the "Show data table" / "Hide data table" swap to be measured. "Show data table" was 125.34 px and "Hide data table" 118.88, so each press moved Download image beside it 6.47 px at 1280×800 and 390×844 on both charts; at 320×640 Download image sat under the button (a 92 px row) and did not move, and no row rewrapped (`run-table-main.log`). Both charts' buttons now stack the two words in one grid cell (`data-table-words`), the word not said `invisible` and `aria-hidden`: 125.34 px in both states, 0 px moved.

Departures from the plan:

1. The group chart's data table button got the same fix; the plan named only the pump chart's, but measured, the group chart's moved Download image 6.5 px too.
2. The Tab-stop probe in `pumps-layout.e2e.ts` (`cardPart`) found the group's data table button by its `textContent`, which now holds both words, so the condenser and lineups view tests counted 80 stops against a budget of 20. It now reads the button's words without the `aria-hidden` one, at the same exact match: 18, 17 and 17 stops in the condenser (1280×800, 390×844, 320×640) and 16, 15 and 15 in the lineups, as before. The one-off keeps 15.
3. `PumpChart.svelte.test.ts`'s `toHaveTextContent('Hide data table')` would now always pass, since both words are in the button; it asserts the words in sight exactly (`wordsInSight`).
4. The e2e test drops the design's light and dark loop (the app has no dark theme) and adds a keyboard press at each size.

### 4.3 Failing first, and proof

- **"Nits item 1: no press of a Show chip moves a chip, its row or the slider under it, by pointer or key, at 1280, 390 and 320 px"** (`tests/pumps-layout.e2e.ts`). Each chip pressed off in turn, then on, then a panel chip off and on from the keyboard, and once with the canvas's top at the pane's top. It asserts the row's height unchanged, every chip's top, left and width and the slider's top within 0.5 px, and the chip still the element at the point pressed. It failed on `673d266` on both projects as §4.1 says. Each half was then run alone: the mark alone left the tops, the slider and the point failing (the canvas, `run-half-mark-only.log`); the scroll alone left the widths, lefts and row heights (`run-half-scroll-only.log`). With both it passes, every measure moving 0 px.
- **"Nits item 1: neither chart's Show data table, pressed to Hide data table and back, moves itself or Download image beside it, or rewraps their row, at 1280, 390 and 320 px".** It failed on `673d266` on the button's width at every size and on Download image's left at 1280 and 390 px.
- **Vitest, moved at the same strictness or stronger.** `PumpChart.svelte.test.ts`'s chip test counted one svg when on and none when off; it now checks the mark's count, place, slot, shape and tone in both states, and presses back on. The data table button's test checks the words in sight and that both words share one grid cell, the one not said invisible and `aria-hidden`. `PumpGroupChart.svelte.test.ts`'s actions test reads the button's text without its hidden word. These failed on `673d266`.
- **Unchanged and passing:** `PumpChart.svelte.test.ts:815-841` ("shows a chip per panel with data, hides one on press, and remembers it"), `pump-chart.e2e.ts`, `design-checks.e2e.ts:39`, `pump-chart-facts.e2e.ts`, `pump-system.e2e.ts`, `pump-control.e2e.ts:95`, `pump-groups.e2e.ts:194` and `:862`, and the pumps-layout tests that press a data table button. No budget moved: the pump chart's Show data table sits 196, 248 and 196 px below its canvas at 1280×800 (condenser, one-off, lineups; budget 300) and 308 at 390×844 (400); the group chart's 304 and 180 at 1280×800 (600) and 320 and 236 at 390×844 (900).

### 4.4 The pane at its end (review PUMPS-NITS-B1)

At the end of the Results pane, pressing Shaft power or NPSH off still moved the chips down. Hiding a panel takes its note below the row as well as its panel above it, so the pane's range shrinks by both; the browser pulls the pane back to its new end, and `scrollTop` cannot go further, so the row stayed lower by the note. Efficiency, with no note below the row, did not move. On main the same off presses moved the same amounts, and every on press there moved the row 112 px, where on the branch it moved 0 (the reviewer's measure), so this was not a regression, but it was the one place where the nit was still not met.

- **Fix.** `pressChip` holds what the scroll could not take as room at the chart figure's foot (`tail`, a `padding-bottom` where the note was), then scrolls by it. Each press sets it anew. A scroll listener trims it as it goes out of sight below the pane, so nothing in view moves. If even that cannot hold the chip (a pane too short to scroll), none is kept.
- **Failing first.** "Nits item 1, the pane at its end: no press of a Show chip moves a chip, its row or the slider under it, though a panel's note below the row goes with its panel, at 1280×800 and 1280×1000" (desktop only: on a phone the row is never in view at the pane's end; the test is skipped there with that reason). On the transfer example at 1280×800 and the condenser example at 1280×1000, the pane scrolled to its end before each press, each chip off and on, Shaft power off and on from the keyboard. On `defe620` (`b1-before.log`): on the transfer example Shaft power off moved the row 274 → 330 px after Efficiency off and 274 → 310 from the keyboard, with nothing under the point pressed, and NPSH off +20 px; on the condenser Shaft power off 260 → 332 px and NPSH off a further +56, both with nothing at the point, and 260 → 312 from the keyboard. After (`b1-after.log`): every press 0 px, the chip at the point, and the figure's padding back to 0 px once the pane is scrolled to its top.

### 4.5 Limits, recorded and not fixed

- **The pane's end.** After an off press at the pane's end, a blank band no taller than the note removed (36 px for Shaft power's note on the transfer example, the reviewer's measure) stays at the chart's foot until it is scrolled out of sight or another chip is pressed.
- **A tall window at the pane's top.** On a window taller than about 985 px, with a one-pump project scrolled to the very top, hiding a panel can still lift the row by up to 112 px less the pane's `scrollTop` (the plan's figure): the pane cannot scroll above its top.
- **WebKit was not run.** Playwright here is Chromium only. The fix uses only `scrollTop`, `getBoundingClientRect` and a scroll listener.

## 5. Item 2: a coloured pill for each pump's status (slice B)

### 5.1 As built

- **The pill.** In Results per pump each Status cell draws the pump's state word in a borderless rounded pill, then any qualifier as plain text: "[Running] (holding flow setpoint)", "[No flow] (system head above shutoff)". The pill is `inline-block rounded-full px-2 align-top text-xs leading-5 font-medium whitespace-nowrap`, with `data-status-pill`: no border, no icon and no glyph, so it never reads as a flag pill or a control, and no padding above or below, so it sits on the row's 20 px line.
- **The words unchanged everywhere.** `pumpStatusParts(result, flags)` (`utils/results.ts`) gives the state (the API's `PumpResult.status`, or `unknown`), the word and the qualifier; `pumpStatusLabel` joins the two, so the export, Compare, the Summary, the group tables, the trace and Build's strip keep their words, and the cell's text is the label word for word.
- **Tones by the state alone** (`PUMP_STATUS_TONES`, beside `flagTone`): Running `bg-green-200 text-green-900` (7.49:1), Off `bg-slate-200 text-slate-700` (8.40:1), No flow `bg-red-200 text-red-950` (11.14:1), and slate for a status the app does not know. No flow is red because the API always flags a `no_flow` pump `PUMP_FLOW_REVERSAL` invalid. A running pump short of its setpoint stays green, since the API flags it at info and amber would invent a severity. The row's flags never change the tint: a cavitating pump keeps a green pill above its red flag line. Colour is never alone; the word carries the state.
- **Where.** `PumpsView.svelte` passes the per-pump `ResultsTable` a `statusCell` snippet as its `cellContent`, which draws the pill for Status and every other cell as ResultsTable does, so the `Table` and `Cell` types are unchanged. The group table's State column and Running combinations keep plain words (§10).

Departures from the plan: the qualifier is `''`, not null, when there is none; the pill and its qualifier sit in one `span.min-w-0`, so on a phone the qualifier wraps after the pill inside the flex cell; "no row grows" is checked against a clone of each row with its status as plain text, not a recorded baseline.

### 5.2 Measured

In the built app (`pumps-layout.e2e.ts`, the controlled, dead-headed and off fixtures):

| Size | Rows | Status line | Box |
|---|---|---|---|
| 1280×800 | 48 and 49 px, each its plain-text twin's | the pill 20 px tall, a 12 px font on a 20 px line, at the cell's top | 9 px more to scroll sideways: 1,271 → 1,280 (controlled), 1,140 → 1,149 (dead-headed), 950 → 959 (off) |
| 390×844 | 120 and 143, 120 and 121, 120 and 99 px, each its twin's | 20 px, one line | 364 px, no sideways scroll |
| 320×640 | 142, 165, 142, 141, 142 and 99 px, each its twin's | 20 px, but the dead-headed Pump PB's 40 px ("[No flow] (system head above" / "shutoff)"), as its twin | 294 px, no sideways scroll |

Axe's color-contrast rule passed every pill (2 of 2 in each view and size), none incomplete, and `axeClean` was clean over the whole tab at each size. The three tints are three distinct fills.

### 5.3 Failing first, and proof

- `results.test.ts`: `pumpStatusParts` for all 11 labels (word, qualifier and state) and `PUMP_STATUS_TONES` for its four states failed on `9016510` (`pumpStatusParts` not a function; the tones undefined). A third new test, the parts joined equal to `pumpStatusLabel` and to the table's cell, passed there, as it pins today's words.
- `ResultsViews.svelte.test.ts`: three pumps (one holding a setpoint, one off, one with no flow), each Status cell one `data-status-pill` holding only its word, its tone and shape classes, no border or vertical padding, and the cell's text the label exactly. It failed on `9016510`, finding no pill.
- **"Nits item 2: each pump's status a pill of its state word on its row's 20 px line, tinted by the state, no row grown and nothing sideways, axe clean with the pills' contrast checked, at 1280, 390 and 320 px"** (`pumps-layout.e2e.ts`) failed on both projects on `9016510` with no pill to find, and passes on the change.
- Unchanged and passing, since the cell's text is the same: `pump-system.e2e.ts:208-212`, `pump-control.e2e.ts:157` and `:227`, `pump-lineups.e2e.ts:395-399`, and the one-off view test, whose axe scan now covers the pill. The related Vitest files: 238 tests in 9 files.

## 6. Item 3: Results per pump hides Hydraulic power, NPSHa and NPSHr by default (slice C)

### 6.1 As built

- **Defaults are declared.** `Column` gains `hiddenByDefault?: true`, and `pumpTable` sets it on `hydraulicPower`, `npshAvailable` and `npshRequired`. NPSH margin stays shown until slice E. The trace view and the export read every column, so each value stays one step away. Build's result strip shows a pump's status, flow, head and NPSH margin, as before (`SUMMARY_COLUMNS.Pump`), and its Trace button opens the trace. A cavitating pump's CAVITATION flag still states NPSHa, NPSHr and the margin.
- **What is stored is the user's departure from the defaults**, under the same key as before (`opensolve-pipe:results-fields:{fieldsKey ?? caption}`). A JSON array is the columns the user hid, the format from before, so a choice stored then is read unchanged and the defaults apply to every column it never named (nothing migrated, D14); it is still written while no default-hidden column is shown. `{"hidden":[…],"shown":[…]}` is written once one is. A choice equal to the defaults removes the key. A key for a column the table lacks now (Control, there only with a speed-controlled pump) is kept by a box's press, never counted or offered.
- **The menu.** Show all shows every column (it stores the defaults as shown; on a table without defaults it removes the key, as before). Default fields, offered on a table with defaults while the choice differs from them, forgets the choice. Each moves the focus to the first box before it goes.
- **The count** counts the table's own hidden columns, defaults included: "Fields (7 of 10), Results per pump", "Fields (8 of 11)" with a Control column. This fixes the roadmap's stale count: a Control remembered as hidden read "Fields (10 of 10), Results per pump" in a solve with no speed-controlled pump.
- **A sort request shows the hidden column it sorts by.** A request from outside the table (the Summary's links) that names a hidden column shows it first, stored as if its box were checked, before the rule that drops a sort on a hidden column. Before, "Pumps, smallest first" silently lost its sort once NPSH margin had been hidden.

Departures from the plan:

1. Default fields is offered only on a table that has defaults, which keeps every other table exactly as before.
2. Every write cleans the stored choice: a hidden entry for a default-hidden column and a shown entry for any other column of the table are dropped, so "a choice equal to the defaults removes the key" holds for an older array that names NPSHa too. Keys of columns the table lacks are kept by a box's press; Show all and Default fields write the choice from scratch, so they drop such a key (seen in the integration check).
3. The desktop table measured 959 → 710 px, against the plan's estimate of about 596 from 950.
4. The S6 review test's name for Results per pump's Fields moved to "Fields (7 of 10), Results per pump", at the same exact match; the plan had listed it as unchanged.

### 6.2 Measured

The per-pump section on phones (the view tests' recorded outline, before → after):

| View | 390×844 | 320×640 |
|---|---|---|
| One-off | 329 → 241 px | 373 → 329 px |
| Lineups | 659 → 483 | 747 → 659 |
| Condenser | 989 → 725 | 1,121 → 923 |

At 1280×800 the heights are unchanged, and the condenser's table is 959 → 710 px wide in its 478 px box, so it still scrolls sideways and the S6 press tests still press its numeric headings. The new test's own log, defaults against every field shown: the off fixture 201 against 245 px high at 390×844 and 201 against 267 at 320×640, 710 against 959 px wide at 1280×800; the controlled fixture 245 against 289, 289 against 333, and 1,031 against 1,280. The view tests (one-off, lineups, condenser) log the same 134 measurements before and after; only the pump canvas's top and the outline's y values move up on phones, and no test asserts on them, so no budget moved and none was tightened.

### 6.3 Failing first, and proof

Eleven Vitest tests failed on `1a4f5ae` (`vitest-fail-first.log`), each for its reason: six new ResultsTable tests on a synthetic table with defaults (nothing stored; a checked box's stored object; Show all and Default fields with the focus; an older stored array; a stored Control with no Control column, which read "Fields (2 of 2)" where no count was due; a sort request on a hidden column), the new SummarySort test ("Pumps, smallest first" with NPSH margin hidden by a stored choice found no NPSH margin heading), the new ResultsViews test of the default headings and "Fields (7 of 10), Results per pump" with every value still in the trace, an existing ResultsViews test's new assertion "Fields (8 of 11), Results per pump", and two new `results.test.ts` tests (the hint on exactly the three keys, and a guard that no other table sets it). A seventh new ResultsTable test, a table without defaults offering no Default fields and its Show all removing the key, passed there by design: it pins the old behaviour. So item 3 adds eleven Vitest tests, ten of which failed first. `3e45090`'s message says "Eleven new Vitest tests failed first"; the log above is the count.

**"Nits item 3: Results per pump opens without Hydraulic power, NPSHa and NPSHr, Fields counting them; a box shows one, remembered after a reload; Default fields hides it again; the table narrower and a phone's list shorter, at 1280, 390 and 320 px"** (`pumps-layout.e2e.ts`, the off, controlled and condenser projects) failed on both projects against a build of the code before the change, at Fields' name, and passes now. Unchanged and passing: ResultsTable's "keeps the Fields choice under the key given, whatever the caption", "Fields gives the focus back to its button when its menu closes from inside it, and Show all keeps it inside the menu (A11Y-S6-2)" and "two tables' Fields and 'Sort by' have names of their own" (`ResultsTable.svelte.test.ts:173`, `:700` and `:732` at the branch's head), SummarySort's "chooses the fields shown from its Fields menu, remembered in this browser" (`SummarySort.svelte.test.ts:152`), the other tables' Fields keys in `PumpGroupChart.svelte.test.ts`, the S5 trace test, item 2's pill test, `summary-tables`, `pump-control`, `pump-system` and `pump-lineups`.

### 6.4 The review's findings on item 3

- **PUMPS-NITS-A1, fixed.** A Summary link's request was applied again whenever its view was drawn anew after a new solve or a case switch: `ResultsPanel` kept `sortRequests` for its whole life while each new `ResultsTable` started from request 0, so a column the user hid after the link came back, sorted, and the hide was lost from storage. Two new tests in `SummarySort.svelte.test.ts` (Nodes, lowest first, and Pumps, smallest first: the link pressed, the column unchecked, a new solve from the Summary, the tab pressed) failed on `defe620` with the header drawn again and sorted ascending. The fix: `ResultsPanel` drops its sort requests when a new solve arrives, as it already drops the views it keeps drawn. A request now lasts only for the solve it was made on: after a new solve, a view that was not on screen comes back unsorted when its tab is pressed (on main the stale request sorted it again). A view still drawn keeps its sort.
- **PUMPS-NITS-A2, fixed.** On a phone, the default count "(7 of 10)" took 54 px from the Sort by field beside Fields, so "NPSH margin (m)" (115 px of text) and "Shaft power (kW)" (116 px) were cut at 360 and 320 px, against S6's TBL-4 rule that the field chosen shows whole down to 320 px (`pumps-results-layout.md` §15 item 183). The item 3 e2e test now walks every Sort by field, and the Summary's "Pumps, smallest first", at 390×844, 360×740 and 320×640 on its three projects; on `defe620` it failed on the condenser with 98 and 102 px of room at 360 and 320 (`a2-before.log`; that run also failed the off fixture on the test's own count of Sort by's fields, written `> 5` there and `≥ 5` since, the off fixture having five). The fix: below 640 px, while a sort is on, Fields' count is for screen readers only, as the word "Sort" already is; the button's name keeps the count. Room for the chosen field's text on the condenser: 128, 98 and 102 → 186, 156 and 160 px at 390, 360 and 320 (`a2-after.log`; 130, 100 and 104 → the same on the controlled fixture).
- **PUMPS-NITS-B2, refused.** The note under Results per pump still explains NPSH available, which item 3 hides by default. The skeptic refuted it as a defect: the note explains a quantity, not a column, and is still true; the plan gives the table's note to slice E, whose own planned words also name default-hidden quantities; main already had the same state for any user who hid NPSHa; and "Fields (7 of 10)" stands right above the table. Slice E rewords the note (§7).

## 7. Item 4: the NPSH margin ratio

### 7.1 The API half (slice D, on `ccr-efab8cb5-vzm6cg`)

Built on main `673d266` as `d5b49f9`, with its review's fixes in `12e087f` and its records on that branch; not on `web/pumps-nits`, since a `web/` branch leaves `apps/api` alone. Each pump's result gains `npshMarginRatio` (`PumpResult.npsh_margin_ratio`): NPSHa / NPSHr where both are known, NPSHr > 0 and the quotient is finite, and null otherwise (no NPSHr curve, a pump off or at no flow, no vapor pressure, an undetermined suction, NPSHr of 0, or a quotient that is not finite). Where a ratio is given it is below 1 exactly where the margin is negative and CAVITATION is raised. **A null ratio is no sign of a safe margin:** a running pump with NPSHr of 0 and a negative NPSHa cavitates and has no ratio; the corpus has one, `unit_rich1090` PU2 (NPSHa −2.521 m, NPSHr 0, margin −2.521 m). The trace gains the ratio's equation (with an NPSHr curve), its value, and a note where NPSHa and NPSHr are both known but there is no ratio (NPSHr of 0, or a quotient that is not finite), and the methods item "Atmosphere and NPSH" one clause. No solved value, flag or method version changed: the corpus comparison gave identical 5,189, different 0, with the new field and the trace and methods insertions ignored and then checked apart. The definition, the unit tests and the proof are in TSD §5.5, §10.2 and §10.4 as written on that branch.

### 7.2 The web half (slice E), not built

It waits for that branch to merge and for the owner to redeploy the API: a Pages preview runs against the deployed API, which would give null in every ratio cell until then. Under Q3 it shows the ratio by default everywhere: Results per pump gains "NPSH margin ratio" after NPSH margin, shown by default, and NPSH margin becomes hidden by default ("Fields (7 of 11)", 8 of 12 with Control); the Summary's per-pump line and its "Smallest NPSH margin" with its "Pumps, smallest first" link move to the ratio together, since the smallest margin and the smallest ratio can belong to different pumps; Build's result strip and Compare's default pump row too. The absolute margin stays one step away (Fields, the trace, the export, Compare's quantities). Where the ratio is null and the margin negative, E shows the margin or a cavitation cue, not only "—" (the API review's finding). E rewords the note under Results per pump (review B2). E also adds the export's Pumps column and Compare's quantity; a goal-seek target on the ratio is Later (D16).

## 8. Item 5: no special characters for pumps and the group

### 8.1 Slice 5a, as built

The part that needed no answer from the owner:

- **A pump is its name** in "Pumps in the group", the Station table and Running combinations: the slot symbol and the 1 rem column kept for it (`w-4`) are gone from the members' labels and both tables' name snippets, so each name starts right after its box or at its row header's edge. `ResultsTable.svelte`'s comments no longer describe a slot symbol.
- **No ● in sentences or tags.** The duty sentence starts "Group duty (station's flow): …", and both "(shown)" tags read "Base case (shown)" (`PumpChart.svelte`, `PumpGroupOthers.svelte`).
- **Marks named in words.** The pump chart's fact notes (`factNotes`, on screen and in the image) read "Best efficiency point (BEP): …", BEP being the cross's label on the chart, and "Shutoff head (the dash at zero flow): …", in place of "(+)" and "(–)".
- **Slot 3's star stroked in its colour.** Chart.js strokes `star` and fills no area, and the group chart stroked it white (`crossed` covered only `cross` and `crossRot`), so it could not be seen on white or in the image's legend. `crossed` now includes `star`, stroked in its slot colour at 3 px, until 5c replaces the members' marks.
- **The guard.** `designators()` (`testing/helpers.ts`) finds the characters of the Geometric Shapes (U+25A0–25FF), Miscellaneous Symbols and Dingbats (U+2600–27BF) and Miscellaneous Symbols and Arrows (U+2B00–2BFF) blocks, a mark in parentheses ("(+)", "(–)"), and a lone × or + in an `aria-hidden` span. It is asserted in the component tests that draw each place.
- **The budget.** `NAME_INSET = 8` (`tests/pumps-layout.e2e.ts`): a name's words start at most 8 px into its row header in the group table and Running combinations, and at most 8 px after its box in "Pumps in the group", at every size.

Left for 5b and 5c, unchanged: the charts' canvases, the legends (the HTML legend's ▲ ■ ●), the pump chart's case markers (△ □ ✳ × ▽), the ring list's ○, the "Each pump's point" table and the image footers' cases notes. The slot data stays for 5c: the group table rows' `style` (a `GROUP_SLOTS` entry, its colour and `symbol`) and `HELD_SYMBOL`, which the "Each pump's point" table reads; `GROUP_SLOTS.symbol`, `HELD_SYMBOL` and `STATION_SYMBOL`, which the HTML legend reads (`groupLegend`); and `CombinationRow.style`, which nothing on screen reads now (only `pump-group-one-off.test.ts` asserts it).

Departures from the plan: the guard is a shared helper asserted inside the existing component tests rather than one new render; `pump-chart-facts.e2e.ts` pinned "(+)" and "(–)", which the plan's list did not name, so it moved too; ResultsTable's synthetic name snippet in its own test lost its ▲.

### 8.2 Measured

- **Name insets** (the condenser and lineups views at 1280×800, 390×844 and 320×640): in "Pumps in the group" 32 → 8 px after the box; in the group table and Running combinations 28 → 8 px into the row header. The 40-character names test reads 8 px at every size too.
- **The view tests** log the same 146 measurements before and after but for the insets and the paragraph word counts, which rise by 6 for the fact notes' words. No card height, station position, legend or other budget moved.
- **The lineups at 1280×800:** the group table's and Running combinations' boxes are 20 px narrower (`scrollWidth` 1,001 → 981 and 671 → 651 px). Phone row and list heights are unchanged.
- **The reviewer's census** of the Pumps tab against main, with every disclosure, both data tables and the card open: "Pumps in the group" 2, 4 and 6 designator hits → 0 in the projects it opened, the Station table 2, 4 and 6 → 0, Running combinations 10, 36 and 6 → 0.

### 8.3 Failing first, and proof

On `3e45090` 18 Vitest tests in 7 of the 8 touched files failed (`vitest-fail-first.log`), 17 of them each on what it pins: the new stroke test in `pump-chart-config.test.ts` ("Pump P3's star: expected '#ffffff' to be '#2a78d6'"); the guards in the members (▲ ■, and ▲ ■ ★ ▢ × + with six slots), Running combinations (▲ ■), the Station table (▲ ■ ★), the duty sentence and both "(shown)" tags (●) and `factNotes` ("(+)"); `PumpGroupView`'s "■ Pump P2"; the new `chart-image.test.ts` test of the BEP and shutoff sentences, on screen and in the image; and the old "(+)" and "(–)" words in three more `chart-image.test.ts` tests, `pump-chart-facts.test.ts` and `pump-chart.test.ts`. The 18th, untouched ("says, closed, what opening it shows"), timed out at 5 s while the machine was loaded and passes on every rerun. Every assertion that pinned a removed character moved to the new words at the same strictness, each naming nit 5; the slot-column checks became stricter (a label has exactly its box and its name; a row header holds no `aria-hidden` or `w-4` element).

On the old build with the new tests (`run-e2e-before.log`) 6 of 8 e2e runs failed: `pump-chart-facts.e2e.ts` on both projects (no BEP words), and the condenser and lineups view tests on both projects on `NAME_INSET` alone (32 and 28 px). The one-off passed: its card is closed. After: 16 of 16 passed (the three view tests, the long-names, group-table, Running-combinations and S5-review tests, and `pump-chart-facts`), the 8 touched Vitest files 285 tests and 29 related files 484.

### 8.4 Slices 5b and 5c, not built

- **5b, case numbers by list place (Q2).** One number per case for the whole Pumps tab: "Base", then 1 to n by place in the Scenarios list, the same on both charts and in every list, table, heading and image, moved by no tick, solve, member change or case shown; every list in that order, Running combinations still putting the case shown first, and D24's lineup priority choosing only what the group chart draws and its cap. The pump chart's other cases become numbered slate rings in place of △ □ ✳ × ▽ (Q1), the number in a small box; the readout rings dashed. It replaces D24 L3's order rule and the "own order" half of the owner's 2026-11-05 answer 2.
- **5c, pumps as named dots (Q1).** Each member's point a dot in its line's colour, named beside it, members on one line sharing its colour, six distinct line patterns; the group point the word "Group"; the held diamond kept in its slot colour; one label placer for both charts, which names a label it leaves out in the notes and settles the point-label half of roadmap item 107; the legend's member entries gone; the swatches from one mark spec. It replaces D21's "dashes and markers" and D15's hollow case markers.

## 9. Review record (2026-11-12)

Two reviewers read the branch at `defe620`, each from its own angle; a skeptic then checked each finding against the plan, the ui-guide and main, reproducing it where it held. 4 findings: 3 held and were fixed in `a0d1b38`, each with a test that failed on `defe620` first; 1 refuted.

| Finding | Item | Verdict | Where |
|---|---|---|---|
| PUMPS-NITS-A1: a Summary link's sort request replayed on a view drawn anew, undoing a later hide | 3 | holds, fixed | §6.4 |
| PUMPS-NITS-A2: the default count cut a phone's chosen sort field at 360 and 320 px | 3 | holds, fixed | §6.4 |
| PUMPS-NITS-B1: at the pane's end, an off press still moved the chips by the note removed | 1 | holds, fixed | §4.4 |
| PUMPS-NITS-B2: the per-pump note explains NPSHa, hidden by default | 3 | refuted | §6.4 |

The reviewers also found, and recorded as fine: no loosened tolerance, budget, timeout or skip in `git diff 673d266` of the tests; the chips moving 0 px over 624 presses at every other position (row centred, under the pinned nav, at the viewport's foot, the canvas at the pane's top; by pointer, Space and Enter); the pill's words equal to the old label for all 11 labels; every stored-choice form, a corrupt one and a throwing `localStorage` handled.

**Gates at `a0d1b38`** (from `apps/web`): `pnpm check` 849 files, 0 errors, 0 warnings; `pnpm lint` clean; `pnpm test` 139 files, 2,320 tests (2,301 at main, `verified-state.md`; +17 by the four items, +2 by A1); and the e2e files `pumps-layout`, `pump-chart`, `pump-chart-facts`, `pump-groups`, `summary-tables` and `design-checks` on both projects, 98 passed, 0 failed, 8 skipped (each skip a test for the other project, the new pane-end test on mobile among them; 20.8 min). At `defe620`, before the review, `pnpm gen:types` left no diff and 15 e2e files that read the Pumps tab passed on both projects (93 passed and 10 skipped on desktop, 94 and 9 on mobile). WebKit was not run.

## 10. Later

Found while planning, not one of the five nits:

- A suction-side dead-head reads "discharge closed off": `PUMP_FLOW_REVERSAL`'s details do not carry the side. An API detail and web words.
- The status pill in the group table's State column and in Running combinations, which use the same helper; after 5a, designed against the narrower name column.
- A goal-seek target on the NPSH margin ratio (D16).
