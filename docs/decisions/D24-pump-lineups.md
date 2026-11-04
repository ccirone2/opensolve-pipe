# D24. Pump lineups (owner, 2026-11-04)

Decision D24 of the OpenSolve Pipe decision record ([index](README.md)). Decisions override the specs; `docs/GOALS.md` overrides decisions. Code and tests cite this decision as `CLAUDE.md D24`.

Design proposal: [`pump-lineups.md`](../proposals/pump-lineups.md). Specs: PRD §3.2.2 and §3.8, SDD §3.1.3 and §3.1.4, TSD §10.2, §10.3 and §12 item 18; [`ui-guide.md`](../ui-guide.md) (the grid of toggles).

---

Built from `docs/proposals/pump-lineups.md` (research against D21's slice 4d; three designs and a recommended plan, which the owner accepted on 2026-11-04 with one change; a card-and-chart designer, a table designer and a synthesizer; an engineering review and a web review, 42 findings, applied by a reviser; its §13 holds the owner's answers). Slice L1 was built on `web/pump-lineups` in two verified steps: L1a (the names: the reader, the naming rule, the follow rule, one commit path), reviewed and checked a second time; an independent API proof; then L1b (the card's block), built as a logic half and a UI half and reviewed. The proposal's §15 records every as-built departure of L1a and L1b. L1 replaces 4d's "One pump off" block (D21). Slice L2, the Pump lineups table, was built on `web/pump-lineups-table`: an independent API proof, a logic half and a UI half, then a review (26 findings) and a second check of its fixes (4); §15 records its departures too. L2 started from `web/pump-lineups` at `861b356`, before L1 merged to `main`, and took in that branch's `7118788` and `28931ff` at `f0bdd0e`. Slice L3 is designed and decided, to build.

### Owner's answers

The request (2026-11-03): with several pumps in parallel, cases with one pump off are "kind of the same cases"; more interesting are cases with 1 pump off, 2 pumps off and so on, and scenarios made easily for whatever pump combinations are wanted. The answer (2026-11-04): "Go with your recommendations; merge both, then build L1 (minus the "every combination", even for <=4 pumps), L2 and L3." Each answer is the recommended option of the proposal's §13, except that Every combination is left out at every size:
- two presets on the Pumps together card, By number running (the default) and Each pump off (4d's cases, kept), and no "Every combination" at any size;
- an editable stop order; by default the last pump listed stops first;
- names of the form "2 of 4 running (P3, P4 off)"; a name the app made follows later toggles until the user edits it;
- `MAX_SCENARIOS` stays 20 (no API change);
- lineups made from a shown scenario are a later slice;
- "the rest differs" for another system's lineups stays as 4d words it;
- L2, a project-wide pump table in the Scenarios manager, and L3, each lineup case's own group curve drawn as the classic curve family, with no "k × one pump" curve (D21's answer stands).

*(GOALS §4.2: a case's name says which pumps it switches off, and its results which pumps carry flow.)*

### Model

A lineup is an ordinary D15 scenario whose changes are pump `status` overrides (a `component` target; `status` is on the allow-list, `models/scenarios.py`). Nothing else changes: the models, the allow-list, `MAX_SCENARIOS` (20), `MAX_OVERRIDES` (30), `Name` (1–100 characters), the requests, the responses and every endpoint. `pnpm gen:types` gives no difference and `schemaVersion` stays 1. A case writes `status: off` only for the pumps it stops, in component order; a pump off in the base gets no change. A full lineup of one station needs at most N − 1 changes (5 for six pumps); 20 lineups of two 6-pump stations make a 2,327-character link (proposal §2). The preset (`ws.lineupPreset`, `'running'` by default) and the stop order (`ws.pumpStopOrder`) are page state: not in the link (D3), not an undo step, reset on load.

### The reader and the frame

`apps/web/src/lib/utils/pump-lineups.ts`, pure (it imports no store), is the one reader for the card and the table now, and for the chart later.
- `pumpLineup(scenario, project, pumpIds)` reads a case as a map from pump to status, so the order of its changes never matters; every list is in component order; `statusOnly` when every change is a member's status.
- `lineupGroups(project)`, the frame that names count over: the station finder (`suggestGroups`) on the base case over every pump, its suggestions kept largest first while none of their pumps is already taken. A kept series suggestion is `series`; a kept parallel one that holds a series chain is `mixed` (the finder calls a 2 × 2 station parallel, the API mixed); the rest are `parallel`. Every other pump goes last in one `other` group, among them every pump of a station of more than `MAX_GROUP_PUMPS` (6), taken whole (§15 item 1). It reads the base only, never the card's members, so a name is the same whether made on the card, in Build or in the table, and after a reload. It is memoised on what the finder reads; `frameKey` compares two frames.
- `effectiveChanges` and `sameCase`: the applied changes whose value differs from the base's, as a set of canonical JSON. Equal sets give the same project after D15's apply, so the same solve bit for bit. A change equal to the base value, or one that no longer applies, is not counted.

### Names

`lineupName(project, scenario)` is null when the scenario sets no pump's status. The pumps it names are those the scenario sets a status for, whatever the value. Its parts follow the frame's order, joined by "; ":
- a `parallel` group: `{k} of {N} running`, then ` ({list} off)` when a member is off in the case, listing every member off (pumps off in the base included) in component order;
- each named pump of a `series`, `mixed` or `other` group: `{label} off` or `{label} on`. In series a stopped pump stops its partner (D21), so "1 of 2 running" would name a case where nothing flows;
- ` + {n} other change` or ` + {n} other changes` when the case has effective changes that are not a pump's status.

Labels are project-wide: a pump's name, or "Name (id)" where another pump has that name. A name is made within `LINEUP_NAME_BUDGET`, 93 characters (the 100-character limit less Duplicate's " (copy)"), with the suffix kept whole, by the first tier whose whole name fits:
1. labels per part (a parallel group by its labels only when its longest part, every member off, fits; else by ids);
2. every part by ids;
3. counts per part;
4. one count.

No tier lists only some of the pumps that are off; tiers 3 and 4 list none. "Running" in a name means switched on. Each pump off keeps 4d's names (`offName`: "Pump P4 off", "Booster pump (PA) off" where two members share a name).

### The follow rule

`followLineupNames(before, after)` runs inside `ProjectStore.update`, after the scenario changes carried through a base edit. A rename is therefore part of the edit's undo step, whichever path made it: Build's base and scenario edits, the manager's actions, each Reset, the Add, goal seek's Apply. No flag is stored.

A name is the app's when, for its scenario before the edit, it equals one of:
1. "Scenario n", n from the scenario's own id, when it has no changes;
2. its `lineupName`;
3. 4d's `offName` of X, in both forms, when its status changes are exactly X off;
4. `copyName` of form 2 or 3, any number of levels deep, a copy cut at 100 characters included.

The rule applies to each scenario present before and after the edit with the same name (a rename in the same edit is the user's and wins). The new name is:
- "Scenario n" when the case no longer sets any pump's status;
- 4d's form with the labels after, while its status changes are still exactly X off and X is in a parallel group. A 4d name follows its own toggles and its pump's rename, never a base edit. A name that is also the case's pure lineup name (`lineupName` of its status changes alone) follows the template while X is named on its own, decided before and after the edit (§15 items 2 and 5);
- otherwise `lineupName` after the edit. A template name thus follows the case's toggles, its other changes coming and going, a base edit of a pump's status, a pump's rename and a change of the frame (a PRV or PSV inside a station set active or not).

A copy keeps its " (copy)" levels only when the edit left its own status changes as they were. A name the user typed is never touched. The rule does nothing unless some name passes the app-made pattern and the edit changed a pump's status or name, a scenario's changes or which of them are effective (a base value one of them sets, or whether it still applies), the topology or the frame.

Every rename is said: `«{from}» is now «{to}»: a name the app made follows its pumps until you rename it.`; two renames are both listed, more than two counted with one example. The caller's own sentence comes first, then the carry notes, then the renames, in one notice (§15 item 3). Undo labels name the case after the step.

A rename leaves a case current (`hydraulicFingerprint` leaves out names). So the ScenarioCard's heading, the trace's case chip, the Methods view and the export's Methods text name a case by its stored name. When the solve was made under another name, the heading and the chip add ` (solved as «{old}»)`, and the Methods view's text to copy and the export's Methods text add `, solved as «{old}»` (`solvedCaseWords`).

### The Add cases block (slice L1)

`components/results/PumpLineupsBlock.svelte`, presentation only, sits in the place of 4d's "One pump off" under the group table: an h4 "Add cases" naming its region. `PumpsView.svelte` computes `lineupPlan` and makes every change.
- **Carrying flow** (decision 14): a pump not `off` whose |operatingFlow| is above `DUTY_CHECK_FLOOR` (10⁻⁶ m³/s), whatever its state word (`carriesFlow`). The API reports a pump on behind a closed valve as `running` at exactly zero flow. A pump on and not carrying flow is idle.
- **Gates**, in 4d's order; while one holds, only its sentence shows, with Solve all for gates 4 to 6: pumps in series; a mixed station; a scenario shown ("Cases are made from the base case: …"); the base case out of date; fewer than two members on; no member carrying flow.
- **The presets**, "Cases to add": By number running (the default) and Each pump off.
- **By number running**: for k = |On| − 1 down to 1, the first |On| − k pumps of the stop order are stopped. A case whose stopped pumps are all idle is not made (it is the base case's state); one that stops an idle pump with others is made.
- **Each pump off**: 4d's cases, one per member carrying flow, named by `offName`.
- **Existing cases**: a planned case is found among the scenarios by `sameCase` (in any order of changes, a hand-made `[P1 on, P4 off]` included) and named with its id. A scenario with another effective change never matches. A planned case whose name another case has is still added, and its preview item says so with that case's id.
- **The stop order**: derived, never written by an effect (`effectiveStopOrder`): the saved order while it holds exactly the pumps on, else the pumps on reversed, so the last pump switched on stops first. Only the move buttons and Default order write it. A native disclosure, closed by default, whose summary names the pumps as the names do (ids for the condenser example). Inside it: `<ol aria-label="Stop order">`, items at least 44 px high, two 44 × 44 px buttons per pump ("Stop {name} earlier", "Stop {name} later"; `aria-disabled` and described at an end), the focus put back on the moved pump's button after every move, Default order (the focus then on the first item's "later"), and a polite status line.
- **The interchangeability sentence** (By number running), from the base as solved: pumps sharing one `curveId` and one speed (equal doubles) with no speed control "have the same pump curve and speed. Which of them run can still change the answer, …"; otherwise "Not all of these pumps have the same pump curve and speed without a speed control, …".
- **About and the preview**: what the preset makes, that pumps off in the base stay off, that "running" in a name means switched on, then each planned case with its kind: added; another case has this name; already a scenario, with its name and id; not made, the base case's state, with the idle pumps. When the card's members are not one group of the frame, one sentence says which group the names count.
- **Add**: `Add {n} case` or `Add {n} cases`, refused past 20 scenarios with the count (`aria-disabled`, described by the reason). One undo step (`withLineupCases`; ids S1, S2, … on the growing project; each scenario `{id, name, overrides}` in component order). Then "Also show the other cases' station duties" is ticked, the notice is the step's lead sentence, and the focus moves to the block's Solve all (4d's, with the Scenarios menu's reasons).
- **The chart's order** (`lineupChartPriority`, replacing 4d's `chartPriority`): this station's lineups (the base when it is another case; each status-only scenario over the members whose off set differs from the base's), the first of each count, most running first; then the other lineups, most running first; then every other case. 4d's cap of six stays, so six pumps with both presets chart 5, 4, 3, 2 and 1 running plus one. "Cases on this chart", the ring numbers, the legend, the data table, the image and Running combinations' "ring n" follow it (§15 item 6).
- **Running combinations** gains one line per case, read from that case's solve, never from its name: `{r} of {n} carrying flow: {A and B}; on, carrying no flow: {C}; off: {D}; no result: {E}`. It never says "running".

### The Pump lineups table (slice L2)

`components/workspace/PumpLineups.svelte` draws the Scenarios manager's second tab: every case × every pump, on or off. `utils/lineup-table.ts`, pure, holds its model and every word (`LINEUP_TABLE_WORDS`).
- **Tabs** (`ScenarioManager.svelte`): with two pumps or more, a tab row named "Scenarios view", `Cases ({n})` and `Pump lineups`, in the Project library's pattern. The tab shown is derived (`shownManagerTab`): the tab last used (`ws.managerTab`, page state, Cases by default, reset on load) while the project has two pumps or more, else Cases. With the tab row the dialog is `xl` on both tabs and, on a phone, its full 92 dvh (`Dialog`'s `tall`), so a tab switch changes neither its width nor its height. With fewer than two pumps it stays `wide`, its Cases prose as before L2. The Cases view is drawn in one place with or without the tab row, so an undo that adds or removes the row keeps the focus on a Cases control; when the focused control itself goes, the focus moves to the dialog's title (`focusTitle()`, the title focusable only while it holds the focus).
- **Opening it**: the header's Scenarios button and the menu's "Manage scenarios…" open the tab last used; a scenario's card asked for (the results' Review) opens Cases (`ws.openManager`). "Pump lineups table…", a quiet button at the foot of the Add cases block whenever the block is drawn, gates included, opens Pump lineups showing only the card's members (`ws.managerPumps`). `ws.closeManager()` forgets the card asked for and the filter.
- **Columns**: the frame (`lineupGroups` on the base case), cut to the filter, empty groups dropped. A group header row only with two groups or more, each header naming its first and last pumps by id: "Pumps together, PA and PB", "Pumps together, P1 to P3", "Pumps together, in series, …", "Pumps together, some in series, …", "Other pumps". Each pump's header is its project-wide label with its id under it.
- **Rows**: the base case first, read-only, "Set in Build"; then each scenario in the project's order, with its name, its id, "Shown" for the case shown, `{n} other changes` (its stored changes other than the shown pumps' statuses) and `Same case as «{name}» ({id})` or "Same case as the base case" (the first earlier row with equal effective changes, `sameCase`'s rule).
- **Cells**: a scenario's cell is one `<button role="switch" aria-checked>`, 3.5 rem by `--ctl-h`, named by its pump header and case name (`aria-labelledby`), its On or Off word `aria-hidden`. A case's own value, even one equal to the base value, is marked three ways: a teal ring and corner triangle, "Changed in this scenario. Base value On." (`aria-describedby`) and the same `title`. A base cell is a focusable gridcell, `aria-readonly`.
- **A press** is `ws.editScenario(scenarioId, change, label, { quiet: true })`, Build's own Status edit for any case: one undo step labelled `turn {pump label} {on|off} in {scenario name}`, the name after the step; the case shown unchanged; a name the app made follows. `ws.edit`'s scenario path calls `editScenario` too, so Build and the table run one function. A press that would add a 31st change is refused: "Could not turn Pump PA off in {scenario name}: A scenario holds at most 30 changes." on the alert line. A press that changes or removes one of a full case's 30 changes applies.
- **The grid**: `role="grid"` with explicit roles; one Tab stop by roving `tabindex`, on the active cell derived from the cell last wanted and clamped to the table (`activeCell`), so no undo leaves the grid without one. The arrows move with no wrap (a key at an edge is not prevented), Home and End go along the row, Ctrl+Home and Ctrl+End to the grid's ends; Space and Enter are the switch's own. After a press, an undo or redo, a rename or a filter change, the focus goes back to the active cell. The scroll box keeps a focused cell's whole focus ring clear of the sticky header rows, the case column and its own bottom edge.
- **New lineup**: "Scenario n" at the end with no changes, in one step labelled `add scenario`; the case shown unchanged; the focus on its first switch; "Added «{name}», its pumps as in the base case.". At 20 scenarios it is `aria-disabled`, titled and described by "A project holds at most 20 scenarios.", as New scenario and Duplicate now are.
- **Undo and Redo** in the footer, with their words and named by the step, and Ctrl/⌘+Z, Ctrl/⌘+Shift+Z and Ctrl/⌘+Y on the dialog (not in a text field) say "Undid {label}." or "Redid {label}.", with " Now showing {case words}." when the case shown changed (`ws.undoStep()`, `ws.redoStep()`).
- **The manager's lines**: one polite status line and one alert line under both tabs, each message drawn afresh, so the same words twice are said twice. Every table press (`editScenario` with `quiet`) and every Cases action (`ws.updateStoredQuiet`) says its renames or its refusal there, not in the workspace notice behind the modal, in every project.
- **Phone** (below 640 px): one case at a time. "Case to edit", a native select, its case derived (the pick while it exists, else the case shown if it is a scenario, else the first scenario, else the base); "Changes go to «{name}» only: {n} of at most 30 changes."; each pump Build's `SegmentedField` with ChangeNote's Changed · Base · Reset. Reset of a value that differs from the base presses the base value; one equal to it is removed in one step labelled `reset {pump label} in {scenario name}`, as Build's Reset removes it (proposal §15 item 63). The base case is a read-only list. Long names with no spaces wrap.

The table says only inputs: each case's status of each pump, which value is the case's own, and which cases are the same case. It never makes a case by itself and never says pumps are interchangeable; its groups are the web's suggestion on the base topology, and the card's word on a station is the API's (D21).

### What is claimed, and what is never claimed

Claimed: that a case's pumps are on or off (inputs); each case's results (its own solve); that a ring lies on its own group curve, only when that case's duty check agrees (D21, D13); that two cases are the same case, only when their effective changes are equal.

Never claimed: that pumps are interchangeable (a shared curve and speed is stated as a fact of the inputs, followed by "can still change the answer"); that curves of equal count are one curve; that the family is ordered; anything about a "k × one pump" curve. A shared ring (4d's `dutiesAgree`) is a drawing rule; the words never call it the same answer.

### Scenarios, goal seek, Compare, export and design checks

Lineups are scenarios: Solve all, staleness, undo, Duplicate, Compare and the case menu treat them as any other. One behaviour changes for every project: a scenario still called "Scenario n" with no changes is renamed by its first pump-status edit, in Build too, with the notice. Since L2 a second one does: the Scenarios manager's actions say their renames and refusals on the manager's own status and alert lines, not in the workspace notice, also with fewer than two pumps. Goal seek varies numbers, never a status, so it never changes which pumps a case runs. A value its Apply writes into a lineup case is one of the case's changes like any other: where it adds an effective change, a name the app made counts it (` + n other changes`), so "3 of 4 running (Pump P4 off)" becomes "3 of 4 running (Pump P4 off) + 1 other change", the rename said in Apply's notice and part of its undo step (§15 item 32). "As new scenario" names its own scenario. The export gains no sheet, column or file: a lineup is named wherever a case is, its changes are in "Scenario changes", the Methods text names a case by its stored name (with ", solved as «{old}»"), and the group chart's image numbers its rings in the chart's order. Running combinations, the stop order and the preset stay on screen. No D19 design check changes; each case's checks are its own solve's.

### Designers' web defaults (reversible, D14)

Everything above not listed under "Owner's answers": the frame and its kinds, project-wide labels, the naming tiers and the 93-character budget, the ` + n other changes` count, the follow rule's reach to "Scenario n" and to copies, the rename words with «», the gates' words, the stop order's disclosure and buttons, the interchangeability sentence, the preview's kinds, the chart order and the lineup line's words. The block's layout as built: the preset's label above its segments at every width, each segment 169–170 px wide at 390 px and 134–135 px at 320 px ("By number running" wraps to two lines inside its 44 px control); measured closed, 440 px on desktop (the card's content is 454 px wide in the results pane at 1280×800, the card about 480 px) and 504 px on a 390 px phone, against the design's estimates of about 260 and 330 px, most of it §7.12's About and interchangeability sentences, kept whole (§15 items 26 and 28). `tests/build-density.e2e.ts` does not cover the Results card, so no budget changed.

L2's: the tab row and its words, the tab remembered and derived, `xl` with the full-height sheet on a phone, the group headers by their first and last ids (a group the filter cuts to one pump is "Pumps together, PB"), a switch per cell on desktop and its three marks, the base row never "Shown", a filter whose pumps are all gone showing every pump, the Tab stop's clamp (the row now at the wanted row's index, else the last row, else the base) and a pointer focus moving it, New lineup's words, the manager's two lines and their reach (every Cases action, in every project, and never the workspace notice: after Done nothing outside the dialog says a name changed), the phone's picker and its default, the focus after a phone's Reset (its chosen segment) and after Show every pump there (the picker), and the phone's Reset of a change equal to the base value. The table's layout as built: c = 20, so the box is `max-h-[max(16rem,calc(85dvh-20rem))]`; the Pump lineups intro uncapped (two lines at 1280 px) and the Cases prose capped at `max-w-prose` with the tab row; the focus ring's room 8 px past the sticky headers and 3 px at the box's bottom (§15 items 66 and 77). Measured at 1280×800 with 21 rows and the condenser example's names: by the UI half at `944595e`, the dialog 1024 px wide, the box 992 × 360 px, the header rows 73 px and the first four rows 44 or 45 px, 6 rows and all 6 pump columns fully visible; by the second check's probe on its fixed build, the rows 44 to 49 px (49 px for the longest names), the body 504/504 px fresh and 540/540 px after a press that renames, with 6 rows both times. Opened from the card, the body is 552/552 px fresh, and after a press that renames 588 px against the 558 it may take: a 30 px scroll with six rows still in the box, not fixed, since no c keeps both (§15 item 71). On a phone, measured by the UI half with the condenser example: 3 pump rows on the first screen of a case with five changed pumps, 5 with one change and 6 in the base list at 390×844, and 1, 1 and 5 at 320×640, against the prototype's 7 and 4 (§15 item 55).

### Slice L3: designed, to build

- **L3** (branch `web/pump-lineups-curves`, proposal §9): each other case's own group curve drawn on the group chart as a labelled slate line, only when its station differs inside only in which pumps are switched on; its ring called the crossing with the group system curve only when three checks agree (§9.5); the y-axis capped near the pumps' region while the family is drawn, its readability measured at 390 × 844 and 320 px before it merges.

It records its departures in the proposal's §15, and its defaults and proof here.

### Not built (owner, 2026-11-04)

The owner's choices, not planned work (proposal §12.1): "Every combination" at any size (2^N − 2 cases fit 20 only up to four pumps); raising `MAX_SCENARIOS`; narrowing "the rest differs" to the station's connected network (it would need an independent D6 proof).

### Later

Proposal §12.2: lineups made from a shown scenario (the owner's answer 5; gate 3 says how to make one by hand); cases crossed across stations; reusable pump states shared by scenarios (a D15 model change, the owner's call); lead, lag and standby roles and staging (D5, pending D11's patent review); series lineups with a stopped pump passing flow (no cited loss law, D21); a batch endpoint (an API change); on the chart, other cases' curves whose station differs inside in other ways, the y cap without the family, and reading other cases' curves along the curves; a per-case untick in L1's preview; in the table, per-row solve chips, renaming, merging same cases and valve statuses. Never: pump states treated as interchangeable ("any k running" as one case). Its own task, outside D24: the State column reads "Running" for a pump on behind a closed valve at zero flow (`pumpStatusLabel`); L1 reads the flow and does not depend on it.

### Versions

`METHOD_VERSION` stays 1.6.0, with no changelog entry, through L1 and L2. Nothing under `apps/api/src` changes and no generated API type changes, so no solved value can change, and the corpus comparison, the fuzz profiles and the corpus checks do not apply (workflow §3 and §4; D21 slice 4d's precedent).

### Proof

**Measured in the design** through the API (proposal §3; the scripts and outputs are kept with the design notes):
- cases with one pump off are the same answer by D6 only with ideal tees: their station flows spread 0.083 % on three pumps and 0.136 % on four; on Crane tees 1.63 % on three and 0.82 % on four, and 8.52 % with one leg a size smaller;
- by number running on four pumps (Crane tees), the station flow over the subsets of one count spreads 0.82 % at 3 running and 4.47 % at 1 running, the NPSH margin at 1 running is 1.07 m with P1 alone and 1.97 m with P4 alone, and the default stop order gave the smallest margin of its count at 1 and 3 running: hence an editable stop order and no claim of sameness;
- each lineup duty lies on the base's group system curve to 2.1 × 10⁻¹⁰ m at its own flow, and each case's own group system curve equals the base's at 41 shared flows (0.0 m);
- an idle pump switched off repeats the base's duty to 2.7 × 10⁻¹² relative;
- a pump on and carrying no flow reads `running` at 0.0 L/s: in parallel behind its isolated discharge valve, and in series and in a 2 × 2 station with its series partner off.

**API**: `tests/unit/test_pump_lineups.py`, 18 tests by a tester who read neither `services/` nor the web code, metamorphic through the `TestClient` with no typed hydraulic number, on four stations (four pumps on Crane tees, the same with P4 off in the base, a ladder of unlike pumps with an idle member, two pumps with one discharge valve isolated):
1. each case as L1 writes it solves as its hand edit, bit for bit (the solved values; the trace apart from D15's additions);
2. reversing its changes gives the same answer bit for bit;
3. each duty lies on the base's group system curve within D6;
4. the idle-only case is the base's answer within D6;
5. each case's group system curve is the base's;
6. a pump on behind a closed valve reads `running` at zero flow, and the case with it off is the base's answer within D6.

The L1b review's fixer, who had read the web source but not `services/`, made proofs 3 to 6 show that each case's group answer is its own (§15 item 9). The module sends from its own client addresses (10.78.x.x), registered in `test_client_addresses.py` (12 tests).

**Fixture**: `tests/fixtures/pump_groups_input.py` gains `lineups` (four `curve_a` pumps on Crane tees; the cases as L1 writes them by number running and each pump off; S7, a speed, and S8, a tank level, for L3) and `lineups-closed-leg` (PB on behind its isolated discharge valve; PB off), each scenario with its real solve, group curve and group system curve, asked from a second client address. `__fixtures__/pump-groups-input.json`, regenerated, holds 18 cases: 3,439,320 to 7,060,448 bytes.

**Web**, measured at the branch's head:
- `utils/pump-lineups.test.ts`, 88 tests: the reader, the frame, `sameCase`, the names and their tiers (every one of 1,000 seeded random names within 93 characters), the follow rule, the plan with every gate and string, the stop order, `lineupChartPriority`, and 4d's plan tests under Each pump off;
- `state/lineup-names.test.ts`, 8 workspace tests: a rename in the edit's undo step, Undo, a user's name, base edits, a PRV that changes the frame, a pump's rename;
- `PumpLineupsBlock.svelte.test.ts`, 14 component tests: the segments, both move directions with the focus after each press, the ends, Default order, the status words, the preview's kinds, the refusals, the gates, the add in one undo step with its notice and "Also show", each case's lineup line after Solve all, reset on load;
- new: `ScenarioCard.svelte.test.ts` (3), `export/about.test.ts` (2), `ConnectionPanel.svelte.test.ts` (1); one more test each in `PipeSegmentForm.svelte.test.ts` (Use for… in a case whose name the app made says the pipes, then the rename), `state/goal-seek.test.ts` (Apply into a lineup case, §15 item 32), `PumpGroupOneOff.svelte.test.ts` ("Cases on this chart" and the ring numbers in the chart's order) and `utils/pump-group-one-off.test.ts` (each case's lineup line in Running combinations, on the fixture's real answers);
- 4d's tests (`pump-group-one-off.test.ts`, 24: 4d's 32 less its eight plan tests and its `chartPriority` test, which moved to `pump-lineups.test.ts` (the last on `lineupChartPriority`'s order), plus the lineup line's test; `PumpGroupOneOff.svelte.test.ts`, 17; `PumpGroupChart.svelte.test.ts`, 31) drive Each pump off with their assertions. They change only where §7.12 changes a string, the chart's order changes the order of requests or ring numbers, or §7.10's lineup line joins a case's heading in Running combinations, each edit naming its cause (§15 items 6, 18 and 33);
- these eleven files: 221 tests passed;
- e2e, `tests/pump-groups.e2e.ts`: "add cases by number running" on desktop, by keyboard, and on the phone, by taps (the preview; the stop order moved with the focus asserted after each press; Add 3 cases, the notice, Solve all focused; four groups in Running combinations, each lineup line built from its intercepted solve and each running pump's values in display units; three rings in the legend; no sideways scroll; axe clean with the disclosures open); 4d's flows choose Each pump off; the file passed 25 tests, with 1 skipped by design (a phone-only test on desktop).

**API, slice L2**: `test_pump_lineups.py` gains 11 tests, 29 in all, by a tester who read neither `services/` nor the web code, on its own `two_systems` (PA and PB between ideal tees with PB a standby; L1's ladder with P3 on and idle; a lone P9; §15 item 60). Every comparison is bit for bit as the proposal's §10 defines it, with no D6 tolerance:
1. a standby put in service (S1, [PB on, PA off]) and a lineup crossed over both stations (S2, [PB on, P1 off, P3 off]) each solve as their hand edits, and each station's group answer is the hand edit's apart from `scenario`;
2. changes equal to the base values (S4, [P1 on]; S5, every pump at its base status) give the base's answer, and such a change added to a case (S6, S1 plus P1 on) leaves S1's, so "Same case as" holds for every solved value;
3. every order of a case's changes gives the same answer (every order of two or three changes; the reverse and a rotation of S5's six), with D15's notes equal and the Scenario section and record in the order given.

A scratch run of mutants (a different pump in the hand edit, a change left out or swapped) made each proof fail, with 234 to 1,645 differing values each. The module sends from its own addresses, 10.78.x.x.

**Fixture, slice L2**: `two-systems` (PA and PB between Crane tees, PB off in the base; the ladder; P9; S1 "PB in service, PA off", S2 the crossed lineup [PB on, P3 off], S3 "Aged pipe"), each scenario with its real solve, group curve and group system curve, asked from the lineups' address. `pump-groups-input.json` holds 19 cases: 7,060,448 to 8,135,778 bytes.

**Web, slice L2**, measured at the branch's head:
- `utils/lineup-table.test.ts`, 41 tests: the columns on `two-systems`, the header row and the filter; every cell state, a standby on included; the notes (`{n} other changes` counting hidden statuses and changes that no longer apply; "Same case as" agreeing with `sameCase` on every pair); the schema guard (`['on', 'off']` with the registry's On and Off); `lineupReset`; the active cell; the phone's pick; every string;
- `state/lineup-table.test.ts`, 16 workspace tests with a fixed clock and a fake solver: presses through `editScenario` and the same presses through Build's Status segment give equal canonical JSON and links, also where both rename; back to the base value; one undo step per press, labelled with the name after the step; the 31st change refused with the exact words; staleness; `editScenario`'s structural check and its words, quiet and not;
- `PumpLineups.svelte.test.ts`, 34 component tests: a table press and Build's give the same project; the tabs and widths; the grid's roles and names; the keys; the focus through a press, a rename, an undo and a redo; the Tab stop that never vanishes; New lineup and the 20 limit; Undo and Redo; the manager's lines; Delete's focus; the filter; the alert line; the phone;
- `PumpLineupsBlock.svelte.test.ts`, 2 more tests (16): the button opens the manager filtered to the members, and it is drawn under a gate;
- these four files and `PumpGroupOneOff.svelte.test.ts` (17, one assertion edited, §15 item 61): 124 tests passed;
- e2e, `tests/pump-lineups.e2e.ts`, 11 tests on the real API: the condenser example (6 columns, the winter case's marked cells and "14 other changes", New lineup, presses with the names following, Undo, the keys, Solve all) with its link equal to Build's; `two-systems` by link; from the card, filtered then every pump; the phone; the 1280×800 layout and the Cases tab at `xl`; first focus on Close; the focus ring; the phone's sheet on a tab switch; long names; the empty lines; the phone's Reset of a change equal to the base value. axe is clean with the tab open, filtered and unfiltered. At `0b73a8e` its 22 runs gave 16 passed and 6 skipped by design (the phone's tests on desktop, the 1280×800 layout and the focus ring on mobile); one assertion of `tests/pump-groups.e2e.ts` was edited (§15 item 61).

The table's model, `lineupTable` with `activeCell` on 21 rows × 12 pumps (two 6-pump stations), took a median of 1.26 ms and at most 5.54 ms over 21 runs, measured by the logic half.

**Reviews**: L1a's (14 findings) and a second check of its fixes (1); L1b's (12); L2's (26: ten faults in fourteen reports, all fixed but one case of one, the table opened from the card, measured and left as a design choice; five missing tests, written; seven refuted) and a second check of its fixes (4, all fixed). Each confirmed finding was reproduced and fixed with a test that fails before the fix, or, for a missing test, under the mutation it let survive, except the card path of §15 item 71, measured and not fixed (§15 items 1 to 9 and 63 to 77). The suites' totals are in [`verified-state.md`](../verified-state.md).
