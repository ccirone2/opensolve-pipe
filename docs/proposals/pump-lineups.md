# Pump lineups: design proposal

**Status: decided** (owner, 2026-11-04), reviewed and revised (2026-11-04, §14); slices L1 (in two steps, L1a and L1b), L2, L3 to build; decision D24. Web only: no model, API, solver or `METHOD_VERSION` change (1.6.0 stays), `schemaVersion` 1. It follows slice 4d of [`pump-groups.md`](pump-groups.md) (D21, merged in `a1cf7b7` with slice 4c), whose "One pump off" block slice L1 replaces.

The design was made in three rounds, all read-only against `main`:
1. **Research** (2026-11-03, against 4d's branch at `8c4ad0b`): a code map of D15 and 4d, API measurements of one-pump-off and k-running cases, and a survey of how other tools and pump guidance treat pump combinations.
2. **Three designs and a recommended plan** (minimal, engineer-first, correctness-first), which the owner accepted on 2026-11-04 with one change (§1.1).
3. **Slice designs** against `a1cf7b7`:
   - one designer for L1 and L3 (the card and the chart);
   - one designer for L2 (the table);
   - then this synthesis.

   The synthesizer checked every disputed claim against the code at `a1cf7b7` and reconciled the two designs into one lineup reader, one naming rule and one set of words. §1.5 lists where they disagreed and what was chosen.
4. **Two reviews and a revision** (2026-11-04): an engineering review (truth, traceability, D13, D15, D17, D21; 20 findings, probes run against the real API) and a web review (UX, phones, accessibility, buildability; 22 findings). The reviser checked each finding against the code at `a1cf7b7`; §14 records each one, its verdict and what changed.

Every choice not marked **O** in §1.4 is the designers' own, reversible under D14.

**Sources**

The measurement scripts and their outputs are kept with the design notes in `/tmp/claude-0/-home-user-opensolve-pipe/ca1a3fad-9c12-5ec7-9b4a-0260b4196220/scratchpad/`, not in the repository. Below, `combos/…` and `lineups/…` are relative to it. The independent tests of §10 reproduce every number this proposal relies on.

- **API measurements** (through `TestClient`, client addresses 203.0.113.x; nothing in the worktrees edited):
  - `combos/measure/`: `ab_one_off` (one pump off, ideal and Crane tees, unequal legs, unequal pumps), `cd_running` (k of N running; each case's group curve and group system curve), `subsets` (all 14 running subsets of four pumps), `fixtures_one_off` (PG1 and the ladder), `f_combinatorics`, `g_timing`; outputs in `out/*.txt` and `out/*.json`; `combos/measure-url.mjs` with `combos/result.json` (link lengths).
  - `lineups/measure/`: `m1_family` (each lineup case's group curve against the base's group system curve; output `out/m1_family.{txt,json}`), `m2_labels`, `m3_labels`, `m4_labels` (label geometry estimated from the measured curves; nothing rendered).
  - The reviews' probes: `lineups/review-eng/probe.py` and `probe2.py` (a pump on behind a closed valve, in series and in a 2 × 2 station; which fields of two equal solves differ), `order_check.py` (the family's order over `m1_family.json`), each with its `.txt`; `lineups/revise/cd_order_check.py` with its `.txt` (the same check over `cd_running.json`).
- **Prototypes:**
  - `lineups/proto-card/lineup.ts` with its tests and `output.txt`: names, the plan, the follow rule and the chart order, run as a scratch vitest against the app's real modules, then deleted from the worktree;
  - `lineups/proto-table/lineup-table.ts` with its tests, `measure.json`, `condenser.json`, `layout.json`, `table.html` and its screenshots, and `lineups/proto-scripts/measure-layout.cjs`: the table's model, link and request sizes, timing, and the layout in Chromium.
- **Test stations** (`combos/measure/common.py`, copied to `lineups/measure/common.py`):
  - an N-leg tee ladder like `derivations_pump_groups.Ladder`, each leg a suction pipe with an elbow, the pump, then a swing check valve and an elbow;
  - a 150 m delivery line to a tank whose level is 20 m above the source's, with a 3 m suction lift;
  - the pumps `curve_a` (`tests/reference/derivations_pumps.py`, a test input with an NPSHr curve);
  - CoolProp water at 20 °C;
  - the best-efficiency flow from `one_off_project`'s illustrative efficiency points, not a datasheet.
- **Practice** (`combos/research-practice.md`; each entry read, or seen only in a search snippet, as marked there):
  - PIPE-FLO's "lineups" (product sheet and release notes, read);
  - AFT/Datacor Fathom's Scenario Manager and multi-scenario pump curves (read);
  - Bentley WaterGEMS/WaterCAD's Pump Curve Combination Editor (docs.bentley.com, read): one column per pump definition, each cell "the number of pumps of that definition that are running";
  - EPANET 2.2's controls and [STATUS] (read);
  - DOE/HI *Improving Pumping System Performance* (2006), Figure 14 "One/Two/Three Pumps Running" against one system curve (read);
  - KSB's lexicon on parallel operation (read);
  - Deppmann on staging and N+1 (read);
  - New Braunfels Utilities' *Lift Station Design Criteria* (2024): "Pump curves shall be plotted for each pump, and each combination of pumps up to firm capacity" (read);
  - Nevada NDEP WTS-14 (read).

  None of these is a hydraulic value; they shape the UI, and the app cites none of them.
- **Code at `a1cf7b7`:**
  - `utils/scenarios.ts`: `scenarioEdit`, `nextOverrides`, `withChange`, `caseKey`, `newScenarioId`, `newScenarioName`, `copyName`, `LIMIT_MESSAGE`, `SCENARIO_NAME_LIMIT`;
  - `utils/pump-group-one-off.ts`: `onePumpOffPlan`, `isOnePumpOff`, `offName`, `memberLabels`, `chartPriority`, `chartKeys`, `restOf`, `runningCombinations`;
  - `utils/pump-groups.ts` (`suggestGroups`, `defaultGroup`), `utils/pump-group-chart.ts`, `utils/pump-chart-config.ts`, `utils/examples.ts` (the condenser example);
  - `state/workspace.svelte.ts` (`edit`, `updateStored`, `fieldChange`, `notify`, the page state) and `state/project.svelte.ts`;
  - `components/workspace/ScenarioManager.svelte` and `ProjectLibrary.svelte` (its tabs), `components/ui/Dialog.svelte`, `SegmentedField.svelte`, `ChangeNote.svelte`, `components/results/PumpGroupChart.svelte` and `PumpsView.svelte`;
  - `models/scenarios.py`, `models/components.py`, `models/base.py`, `services/solver/results.py:812-818`.
- **Project documents:** GOALS §3, §4.2, §4.6, §4.7; CLAUDE.md D3, D6, D10, D11, D13, D14, D15, D17, D21; PRD §3.2.2 and §3.8; [`ui-guide.md`](../ui-guide.md); [`workflow.md`](../workflow.md) §2.

---

## 1. Scope and decisions

### 1.1 The owner's words

The request (2026-11-03):

> "When I have a system with multiple parallel pumps, adding multiple cases with one pump off are kind of the same cases. Right? In this instance it's more interesting to have a scenario for 1 pump off, 2 pumps off, 3... Etc. Even more useful across multiple systems is the ability to create scenarios easily with whatever pump combos desired. How to improve the current implementation?"

The decision (2026-11-04), on the recommended plan (§13):

> "Go with your recommendations; merge both, then build L1 (minus the "every combination", even for <=4 pumps), L2 and L3."

"Both" are PR #260 (slice 4c) and PR #261 (slice 4d), merged into `main` as `a1cf7b7`.

### 1.2 The short answer to "kind of the same cases, right?"

Yes for identical pumps on equal legs with ideal tees. No with the app's default Crane tees (`models/components.py:202-203`), or when the pumps or legs differ. And the more useful family is by number of pumps running: the one-pump-off cases only ever give the "N − 1 running" row. §3 has the measurements.

### 1.3 Decided, not reopened

**By the owner (2026-11-04):**
1. **L1, presets on the Pumps together card:** "By number running" (the default) and "Each pump off" (4d's cases, kept). No "Every combination" preset at any size.
2. **Which pumps stop first:** an editable stop order. By default the last pump listed stops first.
3. **Names:** "2 of 4 running (P3, P4 off)". A name the app made follows later toggles until the user edits it.
4. **`MAX_SCENARIOS` stays 20.** No API change.
5. **Lineups made from a shown scenario:** a later slice.
6. **"The rest differs"** for another system's lineups: left as 4d words it.
7. **L2:** a project-wide pump table in the Scenarios manager:
   - cases × pumps, grouped by station;
   - On/Off toggles written as Build's edit, one undo step each;
   - New lineup;
   - a phone layout.
8. **L3:** each lineup case's own group curve drawn as a labelled line, the classic curve family, with its ring at its crossing with the group system curve. No "k × one pump" curve (D21's owner answer Q2 stands).
9. #261 merged first: done, `main` is `a1cf7b7`.

**Binding rules** (CLAUDE.md):
- D15: a scenario is values only, never topology; at most 20 scenarios, 30 changes each; one undo history.
- D3: page state never in the link.
- D14: `schemaVersion` 1.
- D13: the duty checks guard every "on the curve" claim.
- D10: no number without its source.
- GOALS §4.7: phone and desktop equal.
- `CLAUDE.md` Branches: web-only work on `web/<topic>`.

### 1.4 Decisions

Origin key:
- **O**: the owner (2026-11-04), or the recommended plan the owner accepted;
- **C**: the card and chart designer (L1, L3);
- **T**: the table designer (L2);
- **S**: this synthesis, resolving a disagreement or adding what both designs missed;
- **R**: the reviews (2026-11-04), as the reviser applied them (§14).

Every decision not marked O is reversible under D14.

| # | Decision | Reason | Origin |
|---|---|---|---|
| 1 | A lineup is an ordinary D15 scenario whose changes are pump statuses. No model, API, solver or method change. | `Pump.status` (`"on"`/`"off"`, `models/components.py:283`) is on D15's allow-list; a scenario solve equals the hand edit bit for bit (D15). | O |
| 2 | Two presets on the card: By number running (the default) and Each pump off (4d's). | §1.1. By number running assumes nothing about the pumps and is what the owner asked for. | O |
| 3 | An editable stop order; by default the last pump listed stops first. Page state. | §1.3 item 2. No default is safe: on the Crane station the default gave the smallest NPSH margin at k = 1 and 3 (§3.3), so the choice is shown and editable. | O; page state C |
| 4 | Each case writes `status: off` only for the pumps it stops, in component order. Pumps off in the base get no change and are named as off. | Minimal writing: no change equal to the base. A stable order keeps the staleness key (`scenarios.ts:524-528`) stable. | O |
| 5 | Names `k of N running (A, B off)`. A name the app made follows its pumps until the user renames it. | §1.3 item 3. | O |
| 6 | One reader, `utils/pump-lineups.ts`, for the card, the table and the chart (§4). | One rule for what a case's pumps are, whatever the order of its changes. | C, T, S |
| 7 | One frame of pump groups for names and table columns: the station finder on the base case over every pump, partitioned largest first (§4.2). | A name must be recognisable after a reload and identical whether made on the card, in Build or in the table, so it cannot depend on the card's page state. | S, from T |
| 8 | Labels are project-wide: a pump's name, or "Name (id)" where another pump has its name. | Names and table headers are project-wide. | T |
| 9 | A group's pumps are named by their names, or by their ids for the whole group when its longest possible part does not fit (§4.4). | One form across a family: the condenser example's names push "3 of 6" past the limit, and switching from names at 4 running to ids at 3 reads badly. | T, S |
| 10 | A name never lists part of the pumps that are off. When even ids do not fit, it gives counts (§4.4). | GOALS §4.2. T's "cut to 99 characters + …" was rejected: it hides pumps. | C, S |
| 11 | Lineup names are made within 93 characters: the 100-character name limit less Duplicate's " (copy)". | Duplicate (`copyName`) then never cuts a lineup's pump list. | S |
| 12 | Names follow by a stateless rule (§4.5): base edits, scenario edits, the manager's actions, pump renames, topology changes and any change of the frame, in the same undo step, with a notice. The rule also covers "Scenario n" of an empty scenario and "(copy)" names of the lineup and 4d forms, any number deep. A template name follows whether or not the case has other changes, and then says how many: ` + {n} other changes`. | Stateless: it survives the link, with no flag in the model. C made names follow base edits; T included "Scenario n" and copies. T stopped following once a case had another change, which lets a name go false; S rejects that. The count keeps a case with other changes from wearing a pure lineup's name (R). | C, T, S, R |
| 13 | "The same case" is a fact: equal effective changes (§4.3). L1 uses it to skip a case that exists; L2 uses it for its "Same case as" note. | Equal effective changes give the same project after D15's apply, so the same solve bit for bit. | T, S |
| 14 | A case that stops only pumps carrying no flow in the base is not made. A pump carries flow when it is not off and its flow is above `DUTY_CHECK_FLOOR` (10⁻⁶ m³/s), whatever its state word. | Its duty equals the base's to 2.7 × 10⁻¹² relative (§3.5). The API reports a pump that is on behind a closed valve as `running` at exactly zero flow (§3.5), so the state word alone misses it. This is 4d's idle rule, generalised to D21's own words ("a member on but carrying no flow gets none"). | C, R |
| 15 | Sameness of pumps is never assumed. A sentence states shared curves and speeds, says the choice matters most when few run, and sends the user to the stop order to compare. | On Crane tees same-count cases are up to 2.44 % apart (§3.4), and 4.47 % at one running against 0.82 % at three (§3.3). | O, words C, R |
| 16 | Chart order: one lineup of each count first (most running first), then the other lineups, then the rest; 4d's cap of 6 stays. | With 6 pumps and both presets the six places hold the whole 5-to-1 family. | C |
| 17 | Running combinations gains a line per case read from its solve: carrying flow, on but carrying no flow, off, no result. | It answers "which pumps carry flow" per case without reading every row, and never reads the name. Its words say "carrying flow", never "running", which in a name means switched on (R). | C, R |
| 18 | L2 is a "Pump lineups" tab in the Scenarios manager, shown only with two or more pumps. The manager is extra wide whenever it has the tab. | §1.3 item 7. Measured: 10 pump columns at 1280×800 against 5. A dialog that changed width per tab moved the Cases tab onto the backdrop, where a second click closes the dialog. | O, layout T |
| 19 | Each table cell is one switch in a grid with one Tab stop. A press is Build's own edit through one function, `ws.editScenario`, appended in place as `scenarioEdit` does. | The project JSON is identical to Build's edit. One Tab stop instead of about 240 presses on a 20 × 12 table. | T |
| 20 | Phone: one case at a time with Build's On/Off segments and Changed · Base · Reset. | ui-guide: a table becomes a list on a phone; a two-value choice is a segment. | T |
| 21 | L3 draws another case's group curve only when its station differs inside only in which pumps are switched on. It calls a ring the crossing only when three checks agree (§9.5). | The family is exact for those cases only. D13 guards each claim. | C |
| 22 | Rename notice words, with «» around names in new sentences that list scenarios. | Lineup names hold commas and parentheses. The manager and Share already quote names with «». 4d's own sentences under Each pump off are unchanged. | S |
| 23 | Branches `web/pump-lineups` (L1), `web/pump-lineups-table` (L2), `web/pump-lineups-curves` (L3), built in that order. L1 is built in two verified steps on its branch: L1a (the reader, the names, the follow rule and the one commit path), then L1b (the card's block). | L2 and L3 build on L1's module and both edit `PumpGroupChart.svelte` and `pump-group-one-off.ts`. The follow rule changes behaviour for every project and runs on every edit path, so it is proved before the card uses it (GOALS §6; R). | S, R |
| 24 | Pumps in series, and a group the finder calls parallel that holds a series chain (a 2 × 2 station), are named pump by pump, never `k of N running`. | In series a stopped pump stops its partner (D21), so "1 of 2 running" would name a case where nothing flows. The owner's form is for pumps in parallel, as the request was. | R |
| 25 | While other cases' group curves are drawn, the group chart's y-axis is capped near the pumps' region and the group system curve is cut there, said in the clip note; the readability is measured at 390 × 844 and 320 px before L3 merges. | The group system curve otherwise runs the axis to 200–500 m, leaving the family the bottom 9–23 % of the plot (§9.4). | R |
| 26 | The stop order, the table's active cell, its phone's picked case and the manager's shown tab are derived from stored choices and clamped to what exists; only the user's actions write them. | No effect writes state the view reads, and a Tab stop or a picked case never outlives its row (R). | R |

### 1.5 Where the two designs disagreed

1. **The naming function's shape.**
   - C named one group, the card's members: `lineupName(off, project, memberIds)`.
   - T named every group the scenario changes: `lineupName(project, scenario)` over the finder's partition, parts joined by "; ".
   - **Chosen:** T's shape with C's words (decisions 7 and 9).
   - The card's members are page state. The partition is not, so a name made on the card, in Build or in the table is the same and is still recognised after a reload.
   - **Cost:** when the card's members are not one group of the partition (a subset ticked by hand, or a station the finder does not suggest), names count over the partition's group. For example, a card of [P2, P3] on the ladder's [P1, P2, P3] gives "2 of 3 running (Pump P3 off)". The name is true, and the preview shows it before the add, with one sentence saying which group the names count (§7.7), so the card's "one of these pumps" and the name's "2 of 3" are both explained. In the default case the card's group is the partition's group: `defaultGroup` takes the largest suggestion holding the pump viewed (`pump-groups.ts:489-495`), and the partition takes the largest first.
2. **Tiers per name or per group.**
   - C chose per name: "3 of 6" by names and "1 of 6" by ids in one family.
   - T chose per group.
   - **Chosen:** per group (decision 9).
3. **A name past the limit.**
   - T cut it to 99 characters plus "…".
   - C fell back to ids, then to a count.
   - **Chosen:** C's principle, extended to several groups and to a 93-character budget (decisions 10 and 11).
4. **When a name follows.**
   - C: base and scenario edits, `updateStored`, pump renames; a 4d name follows only its own changes; it follows even with other changes.
   - T: scenario edits only (in `editScenario`); it adds "Scenario n" and "(copy)"; it stops once the case has a non-status change.
   - **Chosen:** C's scope and C's "follow whatever else changed", because T's rule leaves "3 of 4 running (P4 off)" unchanged after a pipe change and a later toggle of P3, which is false. T's extra app-made forms are taken (decision 12). After the review, a template name on a case with other changes also counts them (` + 1 other change`), so it never reads as a pure lineup (§4.4).
5. **The rename notice.**
   - C: "Renamed {from} to {to}: a name the app made follows its pumps until you rename it."
   - T: "«{old}» is now «{new}»: a name the app gave follows its pumps until you rename it."
   - **Chosen:** T's form with C's "made" (§4.5), quoted because names hold commas and colons.
6. **Finding an existing case.**
   - C: a status-only scenario over the members with the same members off.
   - T: equal effective changes.
   - **Chosen:** T's, one function for both (decision 13). They differ only on changes equal to the base value and changes that no longer apply. Neither changes the solve (D15), so T's is the exact fact.
7. **Where the follow runs.** C's three places (`edit`'s base path, `updateStored`, and the scenario path) and T's `editScenario` are one private commit path (§4.5).
8. **The manager's tablist name.** T cited the Project library's tablist as "Views". In the code it is "Library lists" (`ProjectLibrary.svelte:438`), and the workspace's is "View". **Chosen:** "Scenarios view".
9. **The textbook overstatement.** C wrote 2.7–3.6 %. `cd_running.txt` (line 111) gives the exact flow 2.724–3.486 % below k × the one-pump flow. This proposal quotes the file.

---

## 2. Model and API

**None.** A lineup is a D15 scenario whose changes are `component` overrides of a pump's `status`, which is on the allow-list (`models/scenarios.py`, D15). It changes none of the following:
- the models;
- the allow-list;
- `MAX_SCENARIOS` (20, `models/scenarios.py:45`) or `MAX_OVERRIDES` (30, :48);
- `Name` (1–100 characters, `models/base.py:39`);
- the request or response shapes;
- `/solve`, `/system-curve` or `/pump-group-curve`.

`pnpm gen:types` gives no difference.

What the limits allow, measured:
- **Changes per case.** A full lineup of one station needs N − k changes: at most 5 for six pumps and 10 for two stations, within 30 (`f_combinatorics.txt`).
- **Size.** A `status` change is 73 B of JSON. The worst case of 20 scenarios × 12 status changes makes a `/solve` body of 72,382 B, against the 1,000,000 B limit (`lineups/proto-table/measure.json`, condenser example plus a 6-pump station).
- **The link.** It stays far under the 8,000-character warning:

  | Project | Link, no scenarios | Link, 20 lineups | Worst case, 20 × 12 status changes |
  |---|---|---|---|
  | Two 6-pump stations | 1,861 | 2,327 | 2,485 |
  | Condenser example + a 6-pump station | 6,143 | 6,520 | 6,408 |
  | Condenser example alone, its winter case + 19 lineups | 5,409 | 5,696 | — |

  These were measured with the app's own `encodeProject` (`measure.json`, `condenser.json`). The lineups' names in that run were longer than §4.4 makes them, so these are upper bounds.
- **Combinations.** All 63 off-sets of six pumps make a 2,461-character link (`combos/result.json`). The binding limit is `MAX_SCENARIOS`, not the link.
- **Requests.**
  - Solve all sends one request per case, one at a time, under the 60-per-minute limit shared with `/pump-group-curve` (`middleware.py:37-44`).
  - 20 cases and up to 6 other cases' group curves are about 27 requests: one window.
  - Each case took 47–103 ms to solve, 262–614 ms for its group curve and 386–786 ms for its group system curve, so 20 cases take about 6–14 s in sequence (`g_timing.txt`; in-process, 4 CPUs, no network).

**Why no API change:** the owner kept 20 scenarios (§1.3 item 4). A batch endpoint, a stored pump state shared by scenarios and a larger limit are all API changes, and all are Later (§12).

---

## 3. Physics and solver

**None.** Nothing under `apps/api/src` changes, so no solved value can change: `METHOD_VERSION` stays 1.6.0, and no corpus comparison, fuzz profile or corpus check applies (workflow §3, §4; 4d's precedent).

This section records what the measurements say and what the app therefore claims. Every number is the real API's.

### 3.1 Cases with one pump off: when they are the same answer

| Station | Spread of station flow | Spread of rise | The same answer by D6? | Source |
|---|---|---|---|---|
| PG1 (2 pumps, exactly symmetric, ideal tees) | 0 (both 0.04075241500465534 m³/s) | 0 | yes, bit for bit | `fixtures_one_off.txt` |
| N = 3, ideal tees, 1.5 m headers | 0.083 % | 17.7 mm | yes | `ab_one_off.txt` |
| N = 4, ideal tees | 0.136 % | 42.5 mm | yes | `ab_one_off.txt` |
| PG1 on Crane tees | 3.8 % (39.25 vs 40.75 L/s) | 0.325 m | no | `fixtures_one_off.txt` |
| N = 3, Crane tees | 1.63 % | 0.331 m | no | `ab_one_off.txt` |
| N = 4, Crane tees | 0.82 % | 0.246 m | no | `ab_one_off.txt` |
| N = 3, Crane tees, P1's leg one size smaller | 8.52 % | 1.605 m | no | `ab_one_off.txt` |
| Ladder of unlike pumps (P1, P2, P3 off) | 59.1 / 78.2 / 87.2 L/s | — | no | `fixtures_one_off.txt` |

Only the header pipes and the tees make identical pumps on identical legs differ. 4d already draws cases whose duties agree within the duty checks' tolerances as one ring (`dutiesAgree`, `pump-group-chart.ts:345-351`).

### 3.2 By number running

Four identical pumps, ideal tees, the first k running (`cd_running.txt`):

| Running | Station flow | Each pump's flow | NPSH margin |
|---|---|---|---|
| 4 | 86.94 L/s | 0.72 × BEP, 4.71 m from shutoff | 3.97 m |
| 3 | 79.54 L/s | 0.88 × BEP | 3.56 m |
| 2 | 65.53 L/s | 1.09 × BEP | 2.85 m |
| 1 | 39.35 L/s | 1.31 × BEP | 1.98 m |

The one-pump-off cases give only the 3-running row. Runout, the smallest NPSH margin and the largest flow per pump are at k = 1; the smallest margin to shutoff is at k = N.

### 3.3 Which pumps run

From `subsets.txt`, all 14 running subsets of four pumps:

| Station | Spread within one count | Note |
|---|---|---|
| Ideal tees | at most 0.18 % in flow and 43 mm in rise | the first k were the best, by at most 0.18 % |
| Crane tees, k = 1 | 4.47 % | NPSH margin 1.07 m with P1 alone, 1.97 m with P4 alone |
| Crane tees, k = 2 | 1.78 % | — |
| Crane tees, k = 3 | 0.82 % | — |
| Crane tees, P1's leg one size smaller, k = 1 | 22.6 % | P1 alone has an NPSH margin of −0.04 m |
| The same station, k = 2 | 8.5 % | — |

On the Crane station, the default stop order (the last listed stops first, so the first k run) gave the smallest NPSH margin among the subsets at k = 1 and k = 3, and tied for it at k = 2. No default choice of pumps is safe. That is why the stop order is shown and editable.

The choice matters most when few run. On the 4-pump Crane station:

| Running | Station flow over the subsets | Smallest NPSH margin over the subsets |
|---|---|---|
| 3 of 4 | 77.28–77.92 L/s (0.82 %) | 2.84–2.89 m |
| 1 of 4 | 37.62–39.32 L/s (4.47 %) | 1.07–1.97 m |

Each pump off compares only the N − 1 row, where the choice matters least: its cases agreeing says little about one or two running. So the card sends the user to the stop order to compare which run at each count (§7.6), and names Each pump off only for one off.

### 3.4 The curve family

From `lineups/measure/out/m1_family.txt` and `.json`. Each case's group curve is from its own `/pump-group-curve` answer (default request).

- **Shape:**
  - 42 points per curve: 41 even rises from 0 to 45 m, plus the duty's rise, on every station tried, including the ladder of unlike pumps.
  - 19 to 22 of the 42 points have a pump beyond its data.
- **Order:**
  - At every shared rise where the compared flows are above `DUTY_CHECK_FLOOR` (10⁻⁶ m³/s), flows rise strictly with the number running: 0 inversions over the 41 shared rises of N = 4 (Crane and ideal tees) and N = 6 (ideal tees), both presets (`lineups/review-eng/order_check.txt`).
  - At the shutoff rise (45 m) every flow is round-off around zero (10⁻¹⁵ to 10⁻¹⁴ m³/s), and there the order inverts: 4, 2 and 4 inversions on those three stations; Crane's one-running curve has no flow there at all. That is convergence-level noise (D13), not an order.
  - The same holds over `cd_running.json`'s sampled rises: 0 inversions above the floor, 0 to 2 below it on each of five stations (`lineups/revise/cd_order_check.txt`).
  - These stations have identical pumps. Unlike pumps can cross.
- **Same count:**
  - On N = 4 with Crane tees, the four "3 running" curves are up to 2.44 % apart in flow (worst at 43.9 m; 1.6–2.4 % at every rise).
  - The default stop order's "P4 off" is the lowest of them: 162.2 vs 166.2 L/s at a rise of 0.
  - With ideal tees the spread is 0.53 %.
- **Each lineup duty on the base's group system curve:**
  - 2.1 × 10⁻¹⁰ m at the duty's own flow (`cd_running.txt`).
  - Reading that curve by straight lines between its 42 points, at most 0.062 m (N = 6).
  - Each case's own group system curve equals the base's at every one of 41 shared flows, a difference of 0.0 m (`cd_running.txt`; D21 4b proved it for members off).
- **The drawn crossing:** where the drawn lines (each response's 42 points joined by straight lines) cross, against the duty:

  | Station | Flow | Rise |
  |---|---|---|
  | N = 4, Crane tees | 0.036 % | 11.1 mm |
  | N = 4, ideal tees | 0.055 % | 25.1 mm |
  | N = 6, ideal tees | 0.126 % | 40.7 mm |

  All are within D6.
- **The textbook construction:** the exact flow lies below k × the one-pump curve's flow. With all N running:

  | Station | The exact flow is below N × one pump by |
  |---|---|
  | N = 4, ideal tees | 0.326–0.524 % |
  | N = 6, ideal tees | 1.33–2.04 % |
  | N = 4, Crane tees | 2.72–3.49 % |

  (`cd_running.txt`, lines 25, 55 and 111, the k = N rows). For fewer running the gap is smaller: on the N = 4 Crane station 2.58–3.31 % with 3 running and 1.33–1.71 % with 2 (lines 119 and 127). Header and tee losses grow with k. It is not drawn (decision 8 of §1.3).

### 3.5 A pump that carries no flow

The ladder of unlike pumps at speeds 1, 0.93 and 0.8 (`m1_family.json`): P3 is on but carries no flow in the base.
- With P3 off, the duty is the base's to 2.7 × 10⁻¹² relative (0.06681948864486151 against 0.0668194886446843 m³/s): the same answer (D13).
- Its group curve differs: 129.2 vs 172.2 L/s at a rise of 0, because P3 delivers at low rises.

**On, and still no flow.** A pump can carry no flow while the API reports it `running`: the solver keeps its link open at zero flow at its shutoff head (`services/solver/results.py:158`, `RUNNING`, and `:816-817`). The review's probes found three such cases (`lineups/review-eng/probe.txt`, `probe2.txt`):
- in parallel, PB on behind its isolated discharge valve: `running`, 0.0 L/s at 45.0 m;
- in series, PA on with its partner PB off: `running`, 0.0 L/s;
- in a 2 × 2 station, B1 on with its series partner B2 off: `running`, 0.0 L/s.

So the app decides whether a pump carries flow from its flow, never from its state word: a pump **carries flow** when its status is not `off` and `|operatingFlow|` is above `DUTY_CHECK_FLOOR` (10⁻⁶ m³/s, the floor the group chart already uses, `pump-group-chart.ts:1087`). A pump that is on and carries no flow is **idle**, whether its status reads `no_flow` or `running`.

By number running makes no case whose stopped pumps are all idle. A case that stops such a pump with others is made, since it no longer repeats the base.

### 3.6 What the app claims, and what it never claims

**Claimed:**
- That a case's pumps are on or off: inputs, from the project.
- Each case's results: its own solve.
- That a ring lies on its own group curve: only when that case's duty check agrees (D21, D13).
- That a ring is the crossing of its own group curve with this case's group system curve: only under §9.5's three conditions, as 4b's "Group (crossing)" is for the shown case.
- That two cases are the same case: only when their effective changes are equal (§4.3), which gives the same solve bit for bit.

**Never claimed:**
- That pumps are interchangeable. A shared curve and speed is stated as a fact of the inputs, followed by the sentence that which run can still change the answer (§7.6).
- That curves of equal count are one curve.
- That the family is ordered.
- Anything about a "k × one pump" curve.

A shared ring (4d's `dutiesAgree`) and merged curve labels (§9.3) are drawing rules. The words never call them the same answer.

---

## 4. The shared reader: `apps/web/src/lib/utils/pump-lineups.ts` (new, pure)

L1 builds it. L2 and L3 use it. Like 4d's modules, it imports no store.

### 4.1 `pumpLineup`

```ts
export interface PumpLineup {
	/** The pumps read (`pumpIds` that are pumps of `project`), in component order. */
	members: readonly string[];
	/** Members switched off / on in the case: the scenario's status where it sets one, else the base's. */
	off: readonly string[];
	on: readonly string[];
	/** The member statuses the scenario sets, by value (component order). */
	setOff: readonly string[];
	setOn: readonly string[];
	/** Every other change: another pump's status, any other value, a change that no longer applies. */
	other: readonly Override[];
	/** Every change is a member's status, and there is one at least. */
	statusOnly: boolean;
}
export function pumpLineup(
	scenario: Scenario | undefined,
	project: Project,
	pumpIds: readonly string[]
): PumpLineup;
```

**Order-free.** It reads a map from component id to status value, so a case's lineup does not depend on the order of its changes. 4d's cases are found whatever their order, and so is a hand-made `[P1 on, P4 off]` where P1 is on in the base (proto). Every list is in component order.

**What it reads:**
- With `scenario` undefined, it reads the base.
- To read a case as solved, pass `ws.store.caseInputs(caseId)` as `project` with `scenario` undefined. L3 does this.

**Users:**
- **L1:** the card's members (the plan, chart order).
- **L2:** the columns shown (a cell's value, its changed mark, "{n} other changes" = `other.length`).
- **L3:** the card's members in each case as solved (k = `on.length`).

### 4.2 The frame: `lineupGroups`

```ts
export interface LineupGroup { kind: 'parallel' | 'series' | 'mixed' | 'other'; pumpIds: readonly string[] }
export function lineupGroups(project: Project): readonly LineupGroup[];
/** A short key of the frame (each group's kind and pumps), compared before and after an edit (§4.5). */
export function frameKey(groups: readonly LineupGroup[]): string;
```

1. **The finder.** `suggestGroups(project, every pump id)` runs on the base case, with its own valve statuses (`pump-groups.ts:221`). The topology is the same in every case (D15). The finder also reads values: an active PRV or PSV ends a station (`isPressureControl`, `pump-groups.ts:71-78`), so a base edit of a valve's status can change the frame.
2. **Partition.** The finder's suggestions are taken in its order (largest first, then by first pump). A suggestion is kept only when none of its pumps is already taken:
   - the ladder's [P1, P2, P3] beats [P2, P3];
   - a 2 × 2 station gives one group of four.
3. **Kind.** A kept `series` suggestion is `series`. A kept `parallel` suggestion that holds a `series` suggestion (a chain of two or more of its pumps) is `mixed`: the finder calls the 2 × 2 station `parallel` (`pump-groups.test.ts:228-256`) while the API names it `mixed` (`lineups/review-eng/probe.txt` (d)). Every other kept suggestion is `parallel`.
4. **Order.** Groups go by their first pump's component order; pumps within a group keep component order.
5. **Other pumps.** Every pump in no kept group goes last, in component order, as one `other` group. This covers:
   - a lone pump;
   - a station the finder does not suggest;
   - a station of seven or more pumps (`MAX_GROUP_PUMPS` = 6, `pump-groups.ts:27`).

It is memoised on the base's `hydraulicFingerprint`. Measured: the finder takes 3.4–3.8 ms on 12 pumps, and the table's whole model 1.9 ms for 252 cells (`measure.json`).

### 4.3 `sameCase`

```ts
/** The effective changes of a case: each applied change whose value differs from the base's, as canonical JSON. */
export function effectiveChanges(project: Project, scenario: Scenario | undefined): ReadonlySet<string>;
export function sameCase(project: Project, a: Scenario | undefined, b: Scenario | undefined): boolean;
```

**What counts.** A change that no longer applies (D15's `orphaned` or `not_applicable`) and a change equal to the base value change nothing after D15's apply. Equal effective changes therefore give the same project and the same solve bit for bit. The comparison is a set, so order does not matter.

**Users:**
- **L1:** a planned case (its overrides) against each scenario.
- **L2:** the first earlier row with the same effective changes, the base first.

### 4.4 `lineupName`: the one naming rule

```ts
/** The name of `scenario`'s pumps, or null when it changes no pump's status. */
export function lineupName(project: Project, scenario: Scenario): string | null;
export const LINEUP_NAME_BUDGET = SCENARIO_NAME_LIMIT - ' (copy)'.length; // 93
```

**Named pumps.** These are the pumps of the project the scenario sets a `status` for, whatever the value. With none, the result is `null`. Groups are chosen by changes, not by differences from the base, so a later base edit does not take a group out of a name.

**Parts, in frame order:**
- **A `parallel` group** holding a named pump gives:
  - `{k} of {N} running` (N its size, k its members switched on in the case);
  - then ` ({list} off)` when any member is off in the case. The list holds the members off, pumps off in the base included, in component order, joined by ", ".

  With nothing off, the part is `{N} of {N} running`.
- **Each named pump of a `series` or `mixed` group, and of the `other` group,** gives `{label} off` or `{label} on`, from its status in the case. In series a stopped pump stops its partner (D21), so `k of N running` would name a case where nothing flows (decision 24).
- The parts are joined by "; ".
- **Other changes.** When the case has effective changes (§4.3) that are not a pump's `status`, the name ends ` + {n} other change` / ` + {n} other changes`, n their count. A case with other changes then never wears a pure lineup's name, and L1's add cannot make a second scenario of the same name for another case (§7.4). Changes equal to the base value or that no longer apply change nothing, so they are not counted.

**Labels.** `memberLabels` over every pump of the project: the name, or "Name (id)" where another pump has the same name.

**Fitting `LINEUP_NAME_BUDGET`.** The suffix is kept whole (at most ` + 29 other changes`, 19 characters, since a case holds at most 30 changes and one is a pump's status), and the pump parts fit the rest. The first tier whose whole name fits is used:
1. **Per part.**
   - A `parallel` group's members are named by their labels when its longest possible part fits: every member off, `0 of {N} running ({all N labels} off)`. Otherwise every member of that group is named by its id.
   - A pump named on its own (`series`, `mixed` or `other`) is named by its label when `{label} off` fits, else by its id.
2. **Every part by ids.**
3. **Counts per part.**
   - A `parallel` group part: `{k} of {N} running ({m} off)` (or `{N} of {N} running`).
   - The pumps named on their own: one part, `{m} other {pump|pumps} off` and/or `{n} other {pump|pumps} on`, joined by ", ".
4. **One count.** `{k} of {n} pumps running ({m} off)`, over every pump of the groups named and every pump named on its own.

The tiers keep the name honest: it never lists part of the pumps that are off and never names a pump that is on as off. Tiers 3 and 4 list none. They are reached only with ids of about 14 characters or more (the app's ids are short, so only from hand-written JSON) or a case that changes pumps in four or more groups. Then the case's pumps are listed by the table, Running combinations and each pump's State in the Results (§5).

**Examples** (measured on the prototypes):

| Project | Name |
|---|---|
| N = 2 to 6, "Pump Pn" | 28 to 64 characters, all by names: `1 of 6 running (Pump P2, Pump P3, Pump P4, Pump P5, Pump P6 off)` |
| Condenser example ("Condenser water pump CWP-n", 26 characters): its longest part is over the budget | by ids: `3 of 6 running (P4, P5, P6 off)` |
| Two stations | `4 of 6 running (P5, P6 off); 5 of 6 running (Q6 off)` |
| Shared names | `1 of 4 running (Duty pump (P2), Standby (P3), Standby (P4) off)` |
| A standby PB put in service, PA off | `1 of 2 running (Pump PA off)` |
| Nothing off | `4 of 4 running` |
| A tank level changed too | `3 of 4 running (Pump P4 off) + 1 other change` |
| Two pumps in series, PB off | `Pump PB off` |
| A 2 × 2 station (A1, A2 in series beside B1, B2), B2 off | `Pump B2 off` |

"Running" in a name means switched on (§7.7 and §8.2 say so once). A pump can be on and carry no flow; Running combinations shows that, in words that say "carrying flow" (§7.10).

Each pump off keeps 4d's `offName` ("Pump P4 off", "Booster pump (PA) off"; labels over the card's members, `pump-group-one-off.ts:84-107`), unchanged: the plan the owner accepted keeps Each pump off "as built" in 4d (`combos/synthesis.md`), its names included. With both presets the two styles stand side by side ("3 of 4 running (Pump P4 off)" and "Pump P1 off"); each is true, and the second describes its one change against the base.

### 4.5 Names that follow: `followLineupNames`

```ts
export function followLineupNames(
	before: Project,
	after: Project
): { project: Project; renamed: { from: string; to: string }[] };
```

**App-made names.** A name is the app's when it equals one of `appNames(before, S)`:
1. `newScenarioName(before, S.id)` ("Scenario n", n from S's own id), when S has no changes;
2. `lineupName(before, S)`, when S changes a pump's status (with its ` + n other changes` when it has them);
3. when S's status changes are exactly one, setting one pump X off (other changes allowed), 4d's `offName` of X in both forms: `offName(name)` and `offName(name, id)`;
4. a copy of form 2 or 3, any number deep: one of `copyName(x)`, `copyName(copyName(x))`, …, taken until the result stops changing (it does at 100 characters, where `copyName` cuts and so drops an earlier " (copy)"); c ≥ 1 is the number of applications. Duplicating a copy therefore keeps a name that follows.

"Scenario n (copy)" is not app-made: `newScenarioName` takes n from the copy's own id, so "Scenario 2 (copy)" stored as S5 never equals "Scenario 5 (copy)". An empty copy keeps its name until the user renames it.

No flag is stored. A name the user typed is never touched, unless it happens to be one of these very names.

**The rule.** It applies to each scenario present before and after the edit, with the same name in both (a rename in the same edit is the user's and wins), whose name is app-made before. Its new name is:
1. `newScenarioName(after, id)` when S′ changes no pump's status. This covers an empty case, and a case whose last pump change was removed while other changes remain: "Scenario n" claims nothing.
2. Otherwise, when the name was 4d's form for X and S′'s status changes are still exactly X off: the same form with the labels after. Only status changes are compared, so adding a tank level never renames a 4d name. A 4d name follows only a rename of X; a base edit never renames it either, because its name describes its own change against the base, which stays true (4d's names do not carry ` + n other changes`: Each pump off is 4d's as built).
3. Otherwise `lineupName(after, S′)`. A template name thus follows:
   - the case's toggles;
   - its other changes coming and going (the ` + n other changes` count);
   - a base edit of a pump's status (the name describes the whole lineup, and minimal writing means a base edit changes a case's lineup);
   - a pump's rename;
   - a change of the frame (a pump added to a station, or a PRV or PSV inside a station set active or not).
4. When the name was a copy (c levels deep), the new name gets the same c levels of `copyName` only when the edit left S's own status changes as they were (a pump's rename, a base edit, a change of the frame): the copy still copies the same case. When the edit changed S's own status changes, the new name is plain: the copy is now its own case.

A rename is made only when the new name differs.

**The order of edits.** "Scenario 2" given P3 off and then a tank level becomes "3 of 4 running (Pump P3 off)" and then "3 of 4 running (Pump P3 off) + 1 other change". Given the tank level first, it is no longer empty, so "Scenario 2" is no longer app-made and stays. Both names are true: "Scenario n" claims nothing.

**Examples** (prototypes):

| Start | Edit | Result |
|---|---|---|
| "Scenario 1" | presses | "5 of 6 running (P6 off)" → "4 of 6 running (P5, P6 off)" → "4 of 6 running (P5, P6 off); 5 of 6 running (Q1 off)" → back to "Scenario 1" when the three presses are reversed |
| "Pump P1 off" | P2 toggled off too | "2 of 4 running (Pump P1, Pump P2 off)" |
| "Pump P1 off" | a tank level added | unchanged |
| "3 of 4 running (Pump P4 off)" | a tank level added, then removed | "3 of 4 running (Pump P4 off) + 1 other change", then back |
| A template name | a pump renamed "Standby" | "2 of 4 running (Standby, Pump P4 off)" |
| "3 of 4 running (Pump P4 off) (copy) (copy)" | P3 toggled off | "2 of 4 running (Pump P3, Pump P4 off)" |
| "3 of 4 running (Pump P4 off) (copy)" | P3 set off in the base | "2 of 4 running (Pump P3, Pump P4 off) (copy)" |
| "1 of 2 running (Pump PB off)" | a PRV inside the station set active in the base (the group leaves the frame) | "Pump PB off" |
| "My lineup", "Night", "Winter: tower bypassed", "Scenario 3" with a tank-level change, and an empty "Scenario 2 (copy)" | any | never touched |

**Where it runs.** It runs inside the same `store.update` call as the edit, so the rename is part of the edit's undo step. The workspace gets one private commit path, used by:
- `ws.edit`'s base path;
- `ws.editScenario` (§8.6), which `ws.edit`'s scenario path calls;
- `ws.updateStored`: the manager's actions (Remove a change, Duplicate, Move, Delete), each field's Reset, L1's add and goal seek's "as new scenario".

New scenarios are not "present before", so an add or a duplicate renames nothing.

**Cost.** It does nothing unless some scenario's name passes a pattern test for the app-made forms and either the edit changed one of a pump's status (in the base or in a scenario's changes), a pump's name, a scenario's changes or the topology, or the frame changed: `frameKey(lineupGroups(before))` differs from `frameKey(lineupGroups(after))`. The frame is not listed by edit kinds, because the finder reads values too (a PRV or PSV set active, §4.2); `lineupGroups` is memoised on the base's `hydraulicFingerprint`, so the comparison costs a finder run (3.4–3.8 ms on 12 pumps) only when the base's hydraulics changed. Measured: one press with the rule, the finder run twice, took 9.7 ms (`measure.json`).

**The notice** (`renameNotice(renamed)`):
- **One rename:** `«{from}» is now «{to}»: a name the app made follows its pumps until you rename it.`
- **Two:** `Renamed 2 scenarios to match their pumps: «{from}» is now «{to}»; «{from}» is now «{to}». A name the app made follows its pumps until you rename it.`
- **More than two:** `Renamed {n} scenarios to match their pumps, for example «{from}» is now «{to}». A name the app made follows its pumps until you rename it.` One base edit can rename every template case of a station (19 names of up to 93 characters), and the new names are on screen in Scenarios, Compare and the case select.
- **Where it shows:**
  - In Build and on the card, an info notice (`ws.notify`). After a base edit with carry notes, these sentences follow the notes in the same notice.
  - While the Scenarios manager is open, where the workspace notice sits behind the modal (a screen reader does not announce a live region outside a modal dialog), the manager's own status line shows the same words, for an action in either tab (§8.1).

### 4.6 `lineupChartPriority` (replaces 4d's `chartPriority`)

```ts
export function lineupChartPriority(
	keys: readonly { key: string; caseId: CaseId }[],
	project: Project,
	memberIds: readonly string[]
): string[];
```

**This station's lineups** are:
- the base (key `''`) when it is an other case;
- every scenario that is `statusOnly` over the card's members and whose `off` differs from the base's.

Each is counted by `on.length`.

**The order:**
1. The first lineup of each count, most running first, ties in case order.
2. The other lineups, most running first, then case order.
3. Every other case, in case order.

`chartKeys` keeps its rule: unticked cases out, then the first `MAX_GROUP_CASES` = 6.

With "most running first" alone, six pumps with both presets (10 lineups) would fill the six places with "5 running" cases. With this order the first six are 5, 4, 3, 2 and 1 running plus one more (proto).

---

## 5. Traceability

**A lineup name never lists only some of the pumps that are off.** It lists every pump that is off in each `parallel` group it names, or, in tiers 3 and 4, none, with their count (§4.4). It never lists a part. A case with other changes says how many (` + n other changes`). Names are made within 93 characters, so Duplicate's "(copy)" never cuts one. A name the app made follows the case's pumps (§4.5) and every rename is announced, so a stale app-made name does not stand.

4d's "Pump P4 off" names describe one change against the base: they stay true without following, and do not mention a member that is off in the base.

**Every case's pumps can be read whatever its name says:**
- **The ScenarioCard** (the Results pane, for the case shown) lists the server's record of the changes applied: each changed pump's status with its base value, linked to its trace, and the changes ignored (`response.scenario`, D15). It lists changes only; each pump's status in the case is the State column of the Results' pump table.
- **Running combinations** gains one line per case read from that case's solve: which members carry flow, which are on and carry no flow, which are off, which have no result (§7.10). It reads the solve, never the name.
- **The Pump lineups table** (L2) shows each case's status of every pump, marks a case's own changes, and says when two cases are the same case.
- **The trace of each pump** in a case carries D15's "Changed by this scenario" note.

**Compare cases** is unchanged: its columns are the cases by name, its rows each pump's values from each case's solve (`compare.ts`). Lineup names read there as any name.

**A rename that leaves the case current.** A pump's rename makes the follow rule rename a case, but the case stays current: `hydraulicFingerprint` leaves out component names (`project.svelte.ts:426-445`). The server's record of the solve keeps the old name, and two places read it today: the ScenarioCard's heading (`ScenarioCard.svelte:53`) and the export's Methods text (`export/about.ts:607-608`). Any rename does this today; the follow rule makes it happen without the user's hand. So in L1a:
- the ScenarioCard's heading shows the stored name (`ws.caseName`), adding ` (solved as «{old}»)` when the response's name differs;
- the export's Methods text names the case as the other sheets do, by its stored name and id, adding `, solved as «{old}»` when the response's name differs.

**Page state.** The stop order, the preset, the table's tab and its filter are page state: never in the link (D3), reset on load like `pumpGroupOthers`. A link carries only the scenarios, their names and their changes.

**Per slice:**
- **L1:** nothing new in a trace. The card's notes are unchanged except the block's own words (§7) and the ScenarioCard's and Methods' "solved as" (above).
- **L3:**
  - Each drawn curve is that case's `/pump-group-curve` answer, its points exactly (§10.3).
  - The chart's words say which curve is drawn and why another is not (§9.6).
  - The crossing claim is guarded by the duty checks (§9.5).

---

## 6. Scenarios, goal seek, Compare and export

**Scenarios (D15).**
- Lineups are scenarios: Solve all, staleness, undo, Duplicate, Compare and the case menu treat them as any other.
- L1's add writes new scenarios in component order.
- L2's presses go through `scenarioEdit` exactly as Build's segment does: a changed value in its place, a new one appended, one set back to the base removed (`nextOverrides`). The table never reorders existing changes, so it never makes a case out of date without changing it.
- The cost, accepted: turning a pump on and off again leaves the same set of changes in a new order, and the case reads out of date though it is identical. D15 calls its key conservative. Undo restores the exact order and the case reads current again.
- The one behaviour that changes for every project: a scenario still called "Scenario n" with no changes is renamed by its first pump-status edit, in Build too, with the notice (§4.5). This follows decision 3 ("a name the app made follows later toggles"). It ships first, in L1a, with nothing else visible (§7).

**Goal seek (D16).** Unchanged. Its variables are numbers and never a status, so it never changes a lineup. A lineup case it writes into keeps its name, since its pumps are unchanged. "As new scenario" names its own scenario.

**Compare (D15).** Unchanged (§5).

**Export (D17): no new sheet, column or file.** Exactly this reaches the export:
- **The workbook and CSV files.** A lineup is a scenario, so its name appears wherever a case is named: About's case blocks, "Compare cases", each element table per case, and 4c's pump-group sheets, each with the case's name and id ("2 of 4 running (Pump P3, Pump P4 off) (S2)").
- **"Scenario changes"** lists each status change the server applied, with its value and base value (`tables.ts:1723`).
- **The Methods text** names a case by its stored name and id, with `, solved as «{old}»` when a follow rename came after its solve (§5).
- **Group curves.** Each other case's group curve the card computed is already written by 4c's "Group curves" and "Group curve members" sheets as that case's group (D21). L3 draws those same answers and asks for nothing new.
- **The file name.** It carries the case's name when one case is exported. It may shorten a long name, as for any case (`filename.ts`, at most 144 characters); the workbook holds the full name.
- **The group chart's image** (Download image, D17's chart PNG) carries what the card draws:
  - after L3, the curve family, its labels, its legend entry, the frame sentence and the clip note (§9.6);
  - after L1, the new chart order of the rings.
- **Not in the export:**
  - Running combinations and its new line stay on screen only, as in 4d;
  - the stop order, the preset and the table are page state and inputs already in "Scenario changes".

---

## 7. Web, slice L1: the Add cases block

Branch `web/pump-lineups`, in two verified steps (decision 23). Each step runs every gate and is reviewed before the next starts:
- **L1a, the names:** the pure reader of §4 (`pumpLineup`, `lineupGroups`, `sameCase`, `lineupName`, `followLineupNames`, `renameNotice`), the one commit path in `workspace.svelte.ts` that Build's edits already need, the ScenarioCard's and Methods' "solved as" (§5), with their unit and workspace tests. From L1a on, every name the app makes follows.
- **L1b, the card:** the block (§7.1 to §7.9 and §7.11), `lineupPlan`, the stop order, `lineupChartPriority` and the Running combinations line (§7.10), with the fixture, the component, workspace and e2e tests, and the API proof.

### 7.1 Where it sits, and what stays from 4d

The block replaces 4d's "One pump off" section in `PumpGroupChart.svelte` (`:1097-1145`), in the same place:
- under the group table and its footer, above Running combinations;
- drawn while the card shows a station (`stationShown`).

It is extracted to `components/results/PumpLineupsBlock.svelte` (PumpGroupChart is 1,589 lines). It is presentation only: PumpsView computes the plan and makes every change.

**Kept from 4d:**
- the gates and their order;
- each gate's Solve all (gates 4 to 6 show it) and the shared `solveAllReason`;
- the request order and withdrawals;
- "Also show the other cases' station duties" ticked by the add;
- the rings, `dutyClaim`, `restOf`, `sharedRest`;
- Running combinations and the extremes;
- Each pump off's cases, names (`offName`), notice (`addedNotice`) and undo label; its idle skip now tests the flow, as D21 words it (§7.4).

**Replaced:**
- `onePumpOffPlan` becomes `lineupPlan` (§7.4), whose `each` branch is 4d's behaviour;
- `isOnePumpOff` becomes `sameCase`;
- `chartPriority` becomes `lineupChartPriority`;
- the h4 "One pump off" becomes "Add cases", the region's name.

### 7.2 Gates

In 4d's order. The words of gates 1, 2, 3 and 6 change.

| # | When | Words |
|---|---|---|
| 1 | Series | `Cases are added here for pumps in parallel only: in series a stopped pump blocks the line in this app (a stopped pump passing flow is not modelled), so the station would carry no flow.` |
| 2 | Mixed | `Cases are added here for pumps in parallel only; this station is mixed: neither all in parallel nor all in series.` |
| 3 | A scenario shown | `Cases are made from the base case: show the base case to add them. To study {shown} with pumps off, duplicate it in Scenarios and set those pumps off there.` |
| 4 | Base out of date | 4d's: `The base case's results are out of date: solve it again, so the pumps that run are read from the project as it is now.` |
| 5 | Fewer than two on | 4d's: `Needs two or more of these pumps switched on in the base case: {A and B} {is/are} off.` |
| 6 | None carries flow | `No pump of the group carries flow in the base case, so switching pumps off changes nothing.` The test is §3.5's: no member is on with its flow above the floor. |

While a gate holds, only its sentence, Solve all (gates 4 to 6) and, from slice L2 on, the "Pump lineups table…" button (§8.1) show.

### 7.3 The preset control

**The control.** A `SegmentedField` (a two-value choice is a segment group, ui-guide):
- label `Cases to add`;
- options `By number running` and `Each pump off`.

It is shared (never locked in a scenario; the block is gated there anyway).

**Its state.** Page state, `ws.lineupPreset: 'running' | 'each' = 'running'`, reset on load.

**Phone.** At 390 px the two segments fit at about 160 px each (estimated), each 44 px tall: the Results pane is not `.dense`, so `--ctl-h` is 2.75 rem there (`routes/layout.css:17-18, 36-44`).

### 7.4 What each preset makes: `lineupPlan`

**Terms**, all read from the base case's current results (gate 4 guards that):
- **members**: the card's members, in component order;
- **On**: status not `off` (`running` or `no_flow`). A result `off` is exactly an input `off` (`services/solver/results.py:816-818`);
- **base-off**: `off`;
- **carrying flow**: On, with `|operatingFlow|` above `DUTY_CHECK_FLOOR` (§3.5);
- **idle**: On, with `|operatingFlow|` at or below the floor: `no_flow`, or `running` at zero flow behind a closed valve.

**By number running.**
- **The stop order.** `order` is the stop order (§7.5) over On.
- **The cases.** For k = |On| − 1 down to 1, the stopped pumps are `order[0 … |On| − k − 1]`, the first to stop.
- **What each case writes.** `status: off` for its stopped pumps only, in component order whatever the stop order. Base-off pumps get no change and stay off.
- **Its name.** `lineupName` of the case as written, so base-off pumps are named as off: they are off in that case.
- **Idle pumps** are in the stop order like the others. A case whose stopped pumps are all idle is not made (`base_state`, §3.5). A case that stops an idle pump with others is made.

**Each pump off.** 4d's cases: one per member carrying flow in the base, named "{pump} off" by `offName`; idle members are skipped. 4d tested `no_flow` only, so a member `running` at zero flow got a case equal to the base; the flow test makes the skip match D21's own words, "a member on but carrying no flow gets none". 4d's About lists the members carrying flow.

**Existing cases** (both presets). A planned case is `existing` when some scenario is `sameCase` with it (§4.3). The first in case order is named, with its id. This finds:
- 4d's "Pump P4 off" for "3 of 4 running (Pump P4 off)";
- a hand-made `[P1 on, P4 off]`.

A scenario with any other effective change is never a match: "Winter", with P3 and P4 off and a tank level, is not "2 of 4 running".

**A name another case has.** A planned case that is added while some scenario that is not the same case has exactly its name (a user's typed name, or an Each pump off name whose case has gained a tank level) is still added; its preview item says so, with that scenario's id (§7.7).

**Ids.** The first free on the growing project (4d's `newIds`).

**Refusals.** The button is `aria-disabled`, described by the reason shown under it as a hint, as in 4d.
- **By number running, every case existing:** `Every case by number running already exists: {«A», «B» and «C»}.`
- **By number running, existing and base-state cases only:** `Nothing to add: each case by number running already exists or is the base case's state.`
- **Each pump off, nothing to add:** 4d's `Every case with one pump off already exists: {A and B}.`
- **Past 20:** 4d's words, the limit from the schema: `Adding {n} {case|cases} would make {total} scenarios; a project holds at most 20 scenarios.`

**Worked cases**, from the prototype against the real modules (N = 4, members P1 to P4):

| Base | Stop order | Cases |
|---|---|---|
| All running | default P4, P3, P2 | `3 of 4 running (Pump P4 off)` writes [P4]; `2 of 4 running (Pump P3, Pump P4 off)` writes [P3, P4]; `1 of 4 running (Pump P2, Pump P3, Pump P4 off)` writes [P2, P3, P4] |
| All running, S2 = `[P1 on, P4 off]` named "Pump P4 off (hand)" | default | the first is already a scenario, «Pump P4 off (hand)» (S2); the other two are added |
| P4 off | P3, P2, P1 | `2 of 4 running (Pump P3, Pump P4 off)` writes [P3]; `1 of 4 running (Pump P2, Pump P3, Pump P4 off)` writes [P2, P3] |
| P4 idle | default | the first is the base case's state; then [P3, P4] and [P2, P3, P4] |
| All running | P1, P4, P3, P2 | `3 of 4 running (Pump P1 off)`; `2 of 4 running (Pump P1, Pump P4 off)`; `1 of 4 running (Pump P1, Pump P3, Pump P4 off)` |
| 18 scenarios | default | refused: `Adding 3 cases would make 21 scenarios; a project holds at most 20 scenarios.` |

### 7.5 The stop order

**State.** Page state, `ws.pumpStopOrder: readonly string[]`, reset on load, written only by the move buttons and Default order. The order used is derived (decision 26), never written by an effect:

`effectiveOrder = sameSet(ws.pumpStopOrder, On) ? ws.pumpStopOrder : defaultOrder`

- **Default:** On reversed, so the last listed stops first.
- **When a saved order applies:** only while it holds exactly the current On set. Any other change of members, or of statuses in the base, shows the default, with nothing merged; a move then starts from the default. A saved order comes back when the same pumps are on again (after an Undo, say): it is the user's last choice for that set, so that is wanted.
- **Shown** only under By number running.

**Labels.** Every L1 text that names a pump (the stop order's list and summary, the sentence of §7.6, About's base-off sentence, the preview) uses the project-wide labels the names use (decision 8). Only 4d's own text (Each pump off's names and About, Running combinations' rows and its new line) keeps `memberLabels` over the card's members.

**The control.** A native disclosure, closed by default, whose summary says what it holds. The summary names the pumps as the group's names do (§4.4): by labels, or by ids when that group's names use ids, so the condenser example reads `Stop order: P6 first, then P5, P4, P3 and P2; P1 stays on in every case`.
- |On| ≥ 3: `Stop order: {A} first, then {B and C}; {D} stays on in every case`
- |On| = 2: `Stop order: {A} stops; {B} stays on in every case`

Inside it, in order:
1. **The hint:** `The first in this list stops first. The cases below change as you move pumps.`
2. **The list,** `<ol aria-label="Stop order">`, one item per pump, at least 44 px high. Each item holds:
   - its number (from the `<ol>`) and its full label;
   - a muted note: ` (stops first)` for the first, ` (stays on in every case)` for the last, and also ` (carries no flow in the base case)` for an idle pump;
   - two icon-only quiet buttons, at least 44 × 44 px, right-aligned, with an up and a down arrow, each with `data-stop-id="{id}"` and `data-dir="up|down"`:
     - accessible names (`sr-only`) `Stop {name} earlier` and `Stop {name} later`;
     - at an end the button stays focusable with `aria-disabled="true"`, as the manager's Move up/down do, described by `Already the first to stop.` or `Already the last to stop.`.
3. **`Default order`,** a quiet button shown only when the order is not the default, described by `The default: the last pump in the group's list stops first.`

**Keyboard and focus:**
- Tab reaches each button; Enter or Space moves the pump.
- **Focus is put back explicitly after every move.** A keyed `{#each}` does not keep it: for an adjacent swap Svelte 5.57.2 moves one node with `before()` (`node_modules/svelte/src/internal/client/dom/blocks/each.js:540-570`), and for `[A, B, C, D]` to `[A, C, B, D]` it moves B. "Stop C earlier" moves the other node and keeps focus; "Stop B later" moves the focused node, and a node removed and inserted again loses focus to `<body>`. So after each move the handler awaits `tick()` and focuses the same button of the moved pump (`[data-stop-id][data-dir]`), also when the move reached an end, where that button is now `aria-disabled`.
- **Default order** removes itself, so after it focus goes to the first item's `Stop {name} later` button, and the status line says `Default order: {A} stops first.`
- A polite `sr-only` status line says `{name} is now number {i} of {n} to stop.`
- There is no drag: it would be neither keyboard- nor phone-friendly.

**Phone.** The same list: about 176 px for 4 pumps and 264 px for 6 (estimated), hence the closed disclosure. The preview (§7.7) always shows each case's pumps off, so nothing is hidden while it is closed.

### 7.6 The interchangeability sentence (By number running only)

It is read from the base as solved (`groupPumps`: `curveId`, the result's speed and control).

**When the On pumps share one `curveId`, one speed (exactly equal doubles) and none has a control:**

`{A, B and C} have the same pump curve and speed. Which of them run can still change the answer, through the tees and each pump's own piping, most when few run: change the stop order to compare which run at each count; Each pump off compares them with one off.`

**Otherwise:**

`Not all of these pumps have the same pump curve and speed without a speed control, so which of them run can change the answer: the stop order decides which stop first.`

There is no claim of sameness (§3.6), and no claim of difference: two curve ids may hold the same data, and pumps whose inputs differ may still give the same answer. The first sentence points to the stop order, not to Each pump off, because Each pump off covers only N − 1 running, where the choice matters least (§3.3).

### 7.7 About text and preview

**About, By number running.** The first sentence depends on |On|:
- |On| ≥ 3: `Makes one scenario for each number of these pumps running, from {|On| − 1} down to 1: the base case with the pumps that stop first switched off and nothing else changed.`
- |On| = 2: `Makes one scenario with one of these pumps running: the base case with the pump that stops first switched off and nothing else changed.`

Then:
- with base-off pumps: `{A and B} {is|are} off in the base case and {stays|stay} off in every case.`
- always: `In a case's name, running means switched on; Running combinations shows whether each pump carries flow. Other sets of the same number of pumps are not made: change the stop order and add again to compare them.`

**About, Each pump off.** 4d's text, unchanged.

**Preview.** A paragraph `Cases:` with an id, then a `<ul aria-labelledby>`, one item per planned case in plan order:
- added: `{name}`
- added, while another case has its name: `{name}: scenario {id} has this name too but is another case`
- existing: `{name}: already a scenario, «{other}» ({id})`, or `{name}: already a scenario ({id})` when the two names are equal
- base state: `{name}: not made, the base case's state ({A} {carries|carry} no flow in the base case)`

**Which group the names count.** When the card's members are not one group of the frame (a subset ticked by hand, or a station the finder does not suggest; §1.5 item 1), one sentence follows the list: `Names count every pump of the group {P1, P2 and P3}.` (or, when the members fall in no parallel group of the frame, `Names list each pump on its own.`).

Under Each pump off the items are the same kinds. 4d's idle sentence and its "has its case already" sentence move into the items (`{offName}: not made, the base case's state ({name} carries no flow in the base case)` and `{offName}: already a scenario, «{other}» ({id})`).

### 7.8 Add, undo, notice, focus, Solve all

**The button** (`btn`): `Add {n} case` / `Add {n} cases`, or `Add cases` when there is nothing to add (then `aria-disabled`, described by the refusal). Solve all sits beside it with 4d's words.

**One undo step.** `ws.updateStored(draft => withLineupCases(draft, plan.add), label)`:
- `label` is `add cases by number running`, or 4d's `add cases with one pump off`;
- each scenario is `{id, name, overrides}` in component order, with no description;
- Undo removes them all.

**After it:**
- `ws.pumpGroupOthers = true`, as in 4d;
- the notice. By number running: `Added {n} {case|cases} by number running: {«A», «B» and «C»}. Solve all solves every case not yet solved; Undo removes them.` Each pump off: 4d's `addedNotice`;
- focus moves to the block's Solve all (4d's `tick().then(...)`).

**Requests.** Solve all solves each new case. Then the ticked box asks each charted case's group curve, one at a time, as in 4d. Four pumps by number running is 3 solves and 3 group curves.

**Clicks** (counted from the code, not run): Add 3 cases, then Solve all. By hand today the same three cases take about 24 presses and three typed names.

### 7.9 Chart order

§4.6's order and 4d's cap of 6. "Cases on this chart" lists cases in that order and keeps 4d's words. Each number running fits: N − 1 ≤ 5.

### 7.10 Running combinations: the lineup line

**The line.** Each case's group with values gains one line, between its heading and 4d's station line, read from that case's solve:

`{r} of {n} carrying flow: {A and B}; on, carrying no flow: {C}; off: {D}; no result: {E}`

- Each part appears only when it applies; the list after the count only when r > 0.
- r counts members carrying flow by §3.5's test: not `off`, and `|operatingFlow|` above `DUTY_CHECK_FLOOR`. "On, carrying no flow" holds the members that are on at or below the floor, whether their state reads `no_flow` or `running`. Members are named by `memberLabels`, as the table's rows are.
- Example: "2 of 4 carrying flow: Pump P1 and Pump P2; off: Pump P3 and Pump P4".
- New field: `CombinationGroup.lineup: string | null` (null without values).

**The words.** The line never says "running": in a name, running means switched on (the owner's form), and the line answers which pumps carry flow, from the solve. A pump on behind a closed valve reads "Running" in the State column at 0 flow (`pumpStatusLabel`, `results.ts:851`) and "on, carrying no flow" here; the State column's word is outside this proposal (§12). The About sentence names the line (§7.7).

**Order.** Groups keep 4d's order: the shown case first, then case order. The add appends in descending count, so the family reads top down.

### 7.11 Layout

Estimated, not measured in a browser; the build measures it at 1280×800, 390×844 and 320 px, as the ui-guide asks.

**Desktop**, top to bottom:
1. the h4;
2. the segments;
3. the About text (2–3 lines);
4. the sentence (2 lines);
5. the stop-order summary (one 44 px row);
6. the preview (a line per case);
7. the buttons;
8. the refusal;
9. the table button (L2).

About 260 px for four pumps; about 200 px under Each pump off.

**Phone.** The same, stacked, about 330 px for four pumps. Long names wrap (`break-words`) and the buttons wrap (`flex-wrap`).

`tests/build-density.e2e.ts` does not cover the Results card, so no budget changes.

### 7.12 Every new UI string, L1

**Block:**
- `Add cases` (h4, region name)
- `Cases to add`
- `By number running`, `Each pump off`

**Gates:** §7.2 rows 1, 2, 3 and 6.

**About:**
- `Makes one scenario for each number of these pumps running, from {n} down to 1: the base case with the pumps that stop first switched off and nothing else changed.`
- `Makes one scenario with one of these pumps running: the base case with the pump that stops first switched off and nothing else changed.`
- `{A and B} {is|are} off in the base case and {stays|stay} off in every case.`
- `In a case's name, running means switched on; Running combinations shows whether each pump carries flow. Other sets of the same number of pumps are not made: change the stop order and add again to compare them.`

**Sentence:**
- `{A, B and C} have the same pump curve and speed. Which of them run can still change the answer, through the tees and each pump's own piping, most when few run: change the stop order to compare which run at each count; Each pump off compares them with one off.`
- `Not all of these pumps have the same pump curve and speed without a speed control, so which of them run can change the answer: the stop order decides which stop first.`

**Stop order:**
- `Stop order: {A} first, then {B and C}; {D} stays on in every case`
- `Stop order: {A} stops; {B} stays on in every case`
- `The first in this list stops first. The cases below change as you move pumps.`
- the list's name: `Stop order`
- the item notes: ` (stops first)`, ` (stays on in every case)`, ` (carries no flow in the base case)`
- `Stop {name} earlier`, `Stop {name} later`
- `Already the first to stop.`, `Already the last to stop.`
- `Default order`, `The default: the last pump in the group's list stops first.`
- `{name} is now number {i} of {n} to stop.`, `Default order: {A} stops first.`

**Preview:**
- `Cases:`
- `{name}: scenario {id} has this name too but is another case`
- `{name}: already a scenario, «{other}» ({id})`
- `{name}: already a scenario ({id})`
- `{name}: not made, the base case's state ({A} {carries|carry} no flow in the base case)`
- `Names count every pump of the group {P1, P2 and P3}.`, `Names list each pump on its own.`

**Buttons and refusals:**
- `Add {n} case`, `Add {n} cases`, `Add cases`
- `Every case by number running already exists: {«A», «B» and «C»}.`
- `Nothing to add: each case by number running already exists or is the base case's state.`
- 4d's two refusals

**Notices:**
- `Added {n} {case|cases} by number running: {«A», «B» and «C»}. Solve all solves every case not yet solved; Undo removes them.`
- the rename notices of §4.5 (one, two, more than two)

**Undo label:** `add cases by number running`

**Running combinations:** `{r} of {n} carrying flow: {A and B}; on, carrying no flow: {C}; off: {D}; no result: {E}`

**Names:** the templates of §4.4, with ` + {n} other change` / ` + {n} other changes`.

**The ScenarioCard and the export (L1a):** ` (solved as «{old}»)`, `, solved as «{old}»`.

**4d's strings that change** (each test edit traces to one of these; §10):
- the h4 and region name `One pump off` becomes `Add cases`;
- the button `Add cases with one pump off ({n})` becomes `Add {n} case` / `Add {n} cases` (and `Add cases with one pump off` becomes `Add cases`);
- gate 1 `Cases with one pump off are offered for pumps in parallel only: …` becomes §7.2 row 1's words; gate 2 likewise (row 2);
- gate 3 `Cases with one pump off are made from the base case: … To study {shown} with a pump off, duplicate it in Scenarios and set that pump off there.` becomes row 3's words;
- gate 6 `No pump of the group runs in the base case, so switching one off changes nothing.` becomes row 6's words;
- the idle note `{name} carries no flow in the base case, so with it off the base case's state is the same: no case is made for it.` becomes the preview item `{offName}: not made, the base case's state ({name} carries no flow in the base case)`;
- the note `{name} has its case already: {found.name}.` becomes the preview item `{offName}: already a scenario, «{other}» ({id})`.

4d's About, its two refusals, its notice (`addedNotice`) and its undo label `add cases with one pump off` are unchanged.

---

## 8. Web, slice L2: the Pump lineups table

Branch `web/pump-lineups-table`, after L1 merges.

### 8.1 Where it lives, and what opens it

**Tabs.** The Scenarios manager gains a tab row, `Cases ({n})` and `Pump lineups`, only when the project has two or more pumps. Otherwise the manager is exactly as today.
- The tablist follows the Project library's pattern: `role="tablist"` named `Scenarios view`, ← and → between the tabs, each panel a `tabpanel`.
- The Cases panel keeps everything it has, including its current intro paragraph. With the tab row, its "Cases (n)" heading becomes `sr-only` (the tab says it), and after a delete focus goes to the `Cases ({n})` tab, which shows a focus ring; without the tab row the heading stays visible and stays the focus target, as today.
- The long-link warning stays below both panels.
- **The shown tab is derived** (decision 26): `pumps ≥ 2 ? ws.managerTab : 'cases'`. When an Undo takes the project below two pumps while Pump lineups is shown, the tab row goes and Cases shows; focus moves to the dialog's title, and the manager's status line says what the undo did.

**The manager's status line.** One polite `role="status"` line and one `role="alert"` line (`empty:hidden`), outside the tab panels and above the footer, used by both tabs: renames (§4.5), adds, undos and refusals made while the manager is open are said there, because the workspace notice sits behind the modal and fades after 6 s (`Workspace.svelte:50-58`). The Cases tab's actions (Remove a change, Duplicate, Move, Delete) report their renames there too.

**Keys.** The manager handles Ctrl/⌘+Z, Ctrl/⌘+Shift+Z and Ctrl/⌘+Y on its own root (`keydown`, `stopPropagation`), except in a text field, as the workspace's window shortcut does (`Workspace.svelte:67-88`). It calls the same `undo()` and `redo()` functions as the Pump lineups footer's buttons, which write the status line: `ws.#history` only notifies the workspace notice, behind the modal (`workspace.svelte.ts:517-527`), so without this seam the panel could not say what an undo did.

**Width.** With the tab row, the manager is `xl` (64 rem from 1,024 px, 42 rem from 640 px: `Dialog.svelte:62`) on both tabs.
- Measured: `xl` shows 10 pump columns at 1280×800, against 5 at `wide`.
- The width never changes on a tab switch: when it did in the prototype, the Cases tab moved out from under the pointer onto the backdrop, and a second click closed the dialog.
- At `xl` the Cases tab's prose would run to about 140 characters a line, so its intro and the cards' text are capped at `max-w-prose`; the cards themselves stay full width. The 1280×800 measurement (§10.2) includes the Cases tab.
- A project with fewer than two pumps keeps `wide`.

**What opens it:**
1. **The header's Scenarios button, the menu's "Manage scenarios…" and the scenario card's link** open the tab last used: page state `ws.managerTab: 'cases' | 'lineups' = 'cases'`, reset on load. Opened with `managerFocus` set (a scenario's card asked for), it always shows Cases.
2. **The Pumps together card.** A quiet button `Pump lineups table…` sits at the foot of L1's Add cases block whenever the block is drawn, gates included (so in any case shown). It opens the manager on Pump lineups filtered to the card's members: page state `ws.managerPumps = memberIds`, cleared when the manager closes.
3. **Not from the Scenarios menu.** The tab is one press inside "Manage scenarios…", and a menu row must earn its place (ui-guide).

**Title.** The dialog stays "Scenarios". The table's caption (`sr-only`) is `Pumps on or off in each case`.

### 8.2 Desktop and tablet (≥ 640 px): the panel

The panel is `.dense` in both layouts (`class="dense"`, as `CaseMenu.svelte:93` and `SettingsDialog.svelte:94` are): the manager renders outside the Build pane's `.dense` section (`WorkspaceHeader.svelte:398-404`), and `--ctl-h` is 44 px outside it.

Top to bottom, with the chrome above and below the table kept to about three lines so the table holds at least six rows at 1280×800:
1. **The intro** (`text-slate-700`), one paragraph:
   - `Each case's pumps, on or off; in a name, running means switched on. Pressing a cell turns that pump on or off in that case only, the same change as in Build, one undo step each; the base case is changed in Build. {mark} A corner mark is the case's own value; unmarked cells follow the base case.` The mark is the cell's corner triangle, `aria-hidden`.
   - With a `series` or `mixed` group shown, it ends `Pumps in series: one off stops the flow through their line (an off pump passes no flow).` This is true by D21: `status off` is a closed link (`services/solver/status.py:393-397`).
   - Opened from the card, it ends `Only the pumps on the Pumps together card are shown: {A, B and C}.` followed by an inline quiet button `Show every pump`, which clears `ws.managerPumps` and keeps the focus on the table's active cell.
2. **The table** in a scroll box:
   - `scroll-shadow-x`, `overflow-auto`, `overscroll-x-contain`, a rounded border, `max-h-[max(16rem,calc(85dvh-{c}rem))]`. The builder tunes the constant c so that, at 1280×800 with 21 rows and the condenser example's names, the dialog body does not scroll and at least 6 rows are fully visible in the box; an e2e test asserts both.
   - Header rows stick to the top and the case column to the left. `scroll-padding-left` and `scroll-padding-top` keep a focused cell clear of them.
3. **No limit line on this tab:** New lineup is `aria-disabled` and described by the limit (below).

The manager's status and alert lines (§8.1) sit below the panel.

**The footer on this tab** (it wraps on a phone):
- `Undo` (visible word), named `Undo {label}`, or `aria-disabled` and named `Undo` when nothing can be undone;
- `Redo` (visible word), named `Redo {label}`, or `aria-disabled` and named `Redo`, as the header's is (`WorkspaceHeader.svelte:69-70`): on a phone the header's Redo is behind the dialog and there is no keyboard;
- `New lineup` (plus icon), `aria-disabled` when full, with `title` = `LIMIT_TEXT` and `aria-describedby` pointing to an `sr-only` span with the same words (a `title` reaches only the mouse);
- `Done` (primary).

The Cases tab keeps New scenario and Done. New scenario and Duplicate, which share the `aria-disabled` and `title` pattern (`ScenarioManager.svelte:436-444`), gain the same `aria-describedby` in this slice.

### 8.3 Columns: every pump, grouped by station

**The groups** are `lineupGroups(base)` (§4.2), cut to `ws.managerPumps` when filtered (empty groups dropped). The finder never re-runs on a press, since a press changes only `scenarios`.

**The group header row** is shown only with two or more groups. Each header is a `columnheader` with `colspan`, and a 2 px slate divider separates groups. A group's header names its first and last columns, so two stations never read alike (`{A} and {B}` for two pumps, `{first} to {last}` for more, by id):
- `Pumps together, {P1 to P3}` (a `parallel` group);
- `Pumps together, in series, {PA and PB}` (a `series` group);
- `Pumps together, some in series, {A1 to B2}` (a `mixed` group, §4.2);
- `Other pumps`.

The headers never say "in parallel" (the finder's `parallel` may still be mixed in ways it does not see; the API names the arrangement, D21) and never "station".

**The pump header:** the name, wrapping (`text-xs`, `overflow-wrap: anywhere`), with the id under it in mono `text-[11px]`. The id is always shown, since names may use ids (§4.4) and two pumps may share a name. Columns are 5–7 rem; the case column 11–16 rem.

**No sorting.**
- Rows keep the project's scenario order (Move up/down in Cases, the same as the Scenarios menu and Compare).
- Columns keep stations, then the other pumps.

### 8.4 Rows: the cases

**Row 1, the base case,** read-only. Its row header is `Base case` with the note `Set in Build`. Its cells are flat chips, `On` or `Off`, in the switches' colours, with no button look.

**Then each scenario, in order.** The row header (`rowheader`) holds:
- the name (semibold, wrapping) and the id (mono, `text-xs`);
- `Shown` (the Cases cards' teal badge) when it is the case shown;
- notes in `text-xs text-slate-600`, one per line:
  - **`{n} other change` / `{n} other changes`:** `pumpLineup(S, base, columns shown).other.length`. These are the stored changes other than the statuses of the pumps shown: speeds, setpoints, pipes, the fluid, statuses of pumps hidden by the filter, and changes that no longer apply. The note counts what is stored; a name's ` + n other changes` counts only the changes that change the case (§4.4), so the two can differ.
  - **`Same case as «{name}» ({id})` / `Same case as the base case`:** the first earlier row, the base first, that is `sameCase` (§4.3). The id tells two cases of one name apart. It answers the owner's "these are the same cases" where they are, as a fact. A fresh New lineup reads "Same case as the base case" until its first press.

There is no per-row solve state: the Cases tab has the chips, the Results pane says out of date, and it would cost the case column's width.

### 8.5 Cells

**One switch per cell:** `<button type="button" role="switch" aria-checked="{on}">`, 3.5 rem wide and `--ctl-h` tall: 36 px with a mouse and 40 px on touch, because the panel is `.dense` (§8.2; 44 px without it, which the prototype's measured rows did not assume).
- Its text is the state word from the registry, `On` or `Off` (`PUMP_STATUS_LABELS` through `entryFor('Pump', 'status')`), in `<span aria-hidden="true">`.
- On is white with a slate border; Off is `bg-slate-700` with white text, so Off reads down a column.
- The values come from the schema (`schemaChoices('Pump', 'status')`); a unit test fails if they ever stop being exactly `['on', 'off']`.

**Why a switch and not Build's segments here:**
- one state word per cell, readable across 20 × 12 cells;
- 56 px against 76 px: 10 columns instead of about 8;
- one stop for the arrows.

The phone uses Build's segments (§8.10).

**Accessible name:** the visible header words, `aria-labelledby="{pump header span} {case name span}"`, read as "Pump PA Scenario 2". The pump header span holds the label (`memberLabels` over every pump).
- The state is not in the name: the switch announces "on" or "off" itself. A name that changes with every press is announced unreliably.
- The visible "On" or "Off" is the switch's value, not its label. The ui-guide's rule "a control's visible words are part of its accessible name (WCAG 2.5.3)" gains this exception in L2's pattern (§11.2): a switch's state word is its value; its name comes from its row and column headers. A unit test checks that no switch's name contains its state word.

**A case's own change for that pump** (even one equal to the base value, as Build's Changed is) is marked three ways:
- **visibly:** a 2 px teal ring (`ring-2 ring-teal-600 ring-offset-1`, so the focus outline stays free) and a teal corner triangle, a shape, so the mark does not rest on colour alone;
- **for screen readers:** `aria-describedby` points to an `sr-only` span in the cell, `Changed in this scenario. Base value {On|Off}.` (ChangeNote's words);
- **for the mouse:** the same text as the cell's `title`.

**A standby turned on.** A press on a pump off in the base writes `status: on`. The cell then shows On with the mark, described "… Base value Off.". 4d cannot do that.

### 8.6 Pressing a cell: `ws.editScenario`

A press runs `ws.editScenario(scenarioId, (p) => updateComponent(p, pumpId, (c) => ({ ...c, status: next })), label, { quiet: true })`. This is a new public method: `ws.edit`'s scenario branch with the scenario given rather than the shown one (`scenarioEdit`, the structural check, then one stored update through §4.5's commit path). `ws.edit` is refactored to call it, so Build and the table run one function. That gives five properties:
1. **Identical to Build.** The same `scenarioEdit`, the same `updateComponent` change as `RegistryField`'s, the same order and the same name rule. The project JSON is identical (tested, §10.2).
2. **Back to the base value removes the change** (`nextOverrides`). The mark goes, and the row may read "Same case as …".
3. **One undo step per press.**
   - The label is `turn {pump label} {on|off}`, and `editScenario` appends ` in {scenario name}`, using the name after the step, the one on screen: "Undo turn Pump PA off in 3 of 4 running (Pump PA off)". A label with the name before the rename would name a case the user can no longer find.
   - Build's label stays `change pump status in {name}`, with the same rule: `ws.edit`'s scenario path is `editScenario`, so it also names the case after the step. Labels are not part of the project.
   - Like the manager's actions, the step records the case shown, so Undo never switches case for a press made in the table.
4. **The case shown is not changed.** A press in the case shown updates Build's forms and the Results pane at once, and that case reads out of date. The other cases keep their states.
5. **Refusal at 30 changes.**
   - With `quiet`, `editScenario` returns `{ ok: false, message }` and notifies nothing. The manager's alert line shows `Could not turn {pump label} {on|off} in {scenario name}: A scenario holds at most 30 changes.` (`LIMIT_MESSAGE`, in `ws.edit`'s "Could not {label}: " pattern).
   - Build's own refusal words are unchanged.

**Status line after a press.** Nothing when the name stays: the switch announces its state. When the name follows, the §4.5 rename words on the manager's status line.

### 8.7 Keyboard and grid semantics

**Roles.** `role="grid"`, with explicit roles throughout (ui-guide): `rowgroup`, `row`, `columnheader` (with `colspan`, and a `Case` header spanning both header rows when there is a group row), `rowheader` and `gridcell`.

**One Tab stop, roving `tabindex`.** With every switch in the Tab order, a 20 × 12 table would take about 240 presses to reach New lineup.

**Keys:**
- **Tab** enters at the active cell: the first scenario's first pump, or the base row's when there is no scenario. The next Tab leaves the grid.
- **← → ↑ ↓** move between cells, the base row included, with no wrap. At an edge the key does nothing and is not prevented, so the box can still scroll.
- **Home** and **End** go to the row's first and last cell; **Ctrl+Home** and **Ctrl+End** to the grid's first and last.
- **Space** or **Enter** presses a switch.
- The base row's cells are `gridcell`s with `aria-readonly="true"`, focusable themselves.

**The active cell is derived** (decision 26). The panel stores the wanted cell as `(scenario id or base, pump id)`, written only by the keys, a press and New lineup. The cell that holds `tabindex=0` is derived from it and clamped to the current model:
- the wanted row if it still exists, else the nearest remaining row (the next, then the previous), else the base row;
- the wanted column if it is still shown, else the first column.

So when an Undo removes the active cell's row (an undone New lineup) or column (an undone pump), or the filter hides its column, one cell still holds the Tab stop. A stored cell index never outlives its row.

**Scrolling and focus.**
- Moving to a cell calls `scrollIntoView({ block: 'nearest', inline: 'nearest' })`.
- Rows are keyed by scenario id and cells by pump id. That is not enough to keep focus: a keyed reorder moves DOM nodes, and a focused node that is moved loses focus (§7.5). So after a press, an undo or redo, a rename or a filter change made with focus in the grid, the panel awaits `tick()` and focuses the derived active cell.

### 8.8 New lineup

- **What it adds:** `{ id: newScenarioId(project), name: newScenarioName(project, id), overrides: [] }` at the end. It is one undo step labelled `add scenario`, New scenario's label.
- **Its name:** "Scenario n" is app-made, so the first press renames it (§4.5).
- **Its pumps** are the base's, since it has no changes.
- **The case shown:** unchanged, unlike New scenario; here the case is edited in place.
- **Focus:** to the new row's first switch, scrolled into view.
- **Status line:** `Added «{name}», its pumps as in the base case.`
- **When full:** `aria-disabled`, titled and described (`aria-describedby`) by `A project holds at most 20 scenarios.`; a press does nothing.

Rename, describe, move, duplicate and delete stay in the Cases tab. The table's row headers are plain text.

### 8.9 Undo in the panel

`Undo` calls `ws.undo()` and `Redo` calls `ws.redo()`: the last step, whichever it was. Each one's name says which.

**Status line:** `Undid {label}.` or `Redid {label}.`, adding ` Now showing {case words}.` when the case shown changed (a Build edit made in another case). Ctrl/⌘+Z, Ctrl/⌘+Shift+Z and Ctrl/⌘+Y inside the manager go through the manager's own handler (§8.1) to the same functions, so the status line says the same, and focus stays where it was (the derived active cell when it was in the grid).

### 8.10 Phone (< 640 px): one case at a time

The layout is chosen with `mediaQuery('(max-width: 639px)')`, as `PumpChart` does; only one of the two layouts is in the DOM. The panel is `.dense` here too. Top to bottom:
1. **The intro:** `Pick a case, then turn its pumps on or off: the same change as in Build, one undo step each; in a name, running means switched on. The base case is changed in Build.`, with the series and filter sentences as on desktop.
2. **The picker:** a native `<select>` labelled `Case to edit`. It is not "Case", because the Scenarios menu's "Case" changes the case shown and this one does not.
   - Options: `Base case`, then each scenario as `{name} ({changes text})`, the menu's format.
   - The picked case is derived (decision 26): the stored pick while that scenario exists, else the default: the case shown if it is a scenario, else the first scenario, else the base. An Undo that removes the picked scenario therefore falls back to the default.
   - New lineup picks the new case, then focuses the picker and scrolls it into view.
3. **The picked case's line:**
   - a scenario: `Changes go to «{name}» only: {n} of at most 30 changes.`, then its notes (§8.4);
   - the base: `The base case's pumps: change them in Build.`
4. **The pumps,** grouped as on desktop. Each group is a `<fieldset>` whose `<legend>` (`section-title`) has the group's header words; with one group there is no legend.
   - **In a scenario,** each pump is Build's `SegmentedField`:
     - label the pump label; options `On` and `Off` from the schema and the registry;
     - `change` gives ChangeNote's `Changed · Base: {On|Off} · Reset`;
     - Reset presses the base value through the same `editScenario`, so the name rule applies;
     - passing a `change` keeps the field editable whichever case is shown.
   - **The base** is a plain `<dl>`: `{pump label}: {On|Off}`, with no controls.
5. **The manager's status and alert lines, and the footer** (Undo, Redo, New lineup, Done, wrapping), as on desktop.

**Measured on the prototype:** 7 pump rows on the first screen at 390×844 with two-line names, 4 at 320×640, and no sideways page scroll at any size.

### 8.11 What the table claims

**What it says.** Only inputs:
- each case's status of each pump;
- which value is the case's own;
- which cases are the same case (§4.3).

**What it never does:**
- It never says pumps are interchangeable, and never makes a case by itself.
- The grouping is the web's suggestion on the base topology. The API's word on a station is the card's (D21).

**Clicks** (counted from this design, not run): Scenarios, Pump lineups (remembered), New lineup, P3, P4, Done is 6–7 presses with no typing for "2 of 4 running (P3, P4 off)", against about 10 and a typed name today. Each further case is New lineup plus a press per pump.

### 8.12 Every new UI string, L2

**Tabs and table:**
- `Cases ({n})`, `Pump lineups`
- the tablist's name: `Scenarios view`
- `Pumps on or off in each case` (caption)

**Intros and lines:**
- `Each case's pumps, on or off; in a name, running means switched on. Pressing a cell turns that pump on or off in that case only, the same change as in Build, one undo step each; the base case is changed in Build. {mark} A corner mark is the case's own value; unmarked cells follow the base case.`
- `Pick a case, then turn its pumps on or off: the same change as in Build, one undo step each; in a name, running means switched on. The base case is changed in Build.`
- `Only the pumps on the Pumps together card are shown: {A, B and C}.`, `Show every pump`
- `Pumps in series: one off stops the flow through their line (an off pump passes no flow).`
- `A project holds at most 20 scenarios.` (existing; now also the `sr-only` description of New lineup, New scenario and Duplicate when full)

**Headers and rows:**
- `Pumps together, {A and B}`, `Pumps together, {first} to {last}`, `Pumps together, in series, …`, `Pumps together, some in series, …`, `Other pumps`, `Case`
- `Base case`, `Set in Build`, `Shown`
- `{n} other change`, `{n} other changes`
- `Same case as «{name}» ({id})`, `Same case as the base case`

**Cells:**
- `On`, `Off` (registry)
- the name from the visible headers, `{pump label} {case name}`
- `Changed in this scenario. Base value {On|Off}.`

**Footer:** `Undo`, `Undo {label}`, `Redo`, `Redo {label}`, `New lineup`, `Done`

**The manager's status and alert lines:**
- `Added «{name}», its pumps as in the base case.`
- `Undid {label}.`, `Redid {label}.`, ` Now showing {case words}.`
- `Could not turn {pump label} {on|off} in {scenario name}: A scenario holds at most 30 changes.`
- the rename words of §4.5, for an action in either tab

**Undo label:** `turn {pump label} {on|off} in {scenario name}`, the name after the step

**Phone:**
- `Case to edit`, `Base case`, `{name} ({changes text})`
- `Changes go to «{name}» only: {n} of at most 30 changes.`
- `The base case's pumps: change them in Build.`
- `{pump label}: {On|Off}`

**The card's button:** `Pump lineups table…`

---

## 9. Web, slice L3: the curve family on the group chart

Branch `web/pump-lineups-curves`, after L2 merges.

### 9.1 Which other cases' group curves are drawn

Another case's own group curve is drawn when all of these hold:
1. **Its ring is drawn:** on the chart (ticked, within the cap of 6), `state: 'ready'` (a duty, the same station).
2. **Its answer is a group curve,** not 4d's group-system fallback (`v.group.status === 'ready'`). A case refused for an active PRV or PSV inside has none.
3. **This case's own group curve is drawn** (`curve.drawn`: some point with a flow). The family is drawn against the ink curve; without it the chart is 4d's, rings only.
4. **Its station differs from this case's inside only in which members are switched on,** both as solved:
   - `insideOf(project, station)` is added beside `restOf` in `pump-group-one-off.ts`. It holds the station's interior components with the members' `status` removed, the interior connections, the fluid, the settings without `designChecks`, and the library entries used inside;
   - the two cases' `insideOf` fingerprints (`hydraulicFingerprint`, memoised in PumpsView as `shared` is) are equal, and the members' statuses differ.

   This is symmetric. When a lineup case is shown, the base is another case and its 4-running curve is drawn. A case the same inside (same pumps on) has the ink curve as its own, so it is not drawn twice (4d's frame sentence covers it). A case that changes anything else inside (a speed, a setpoint, a valve) is not drawn; that is Later.
5. **Some point has a flow above `DUTY_CHECK_FLOOR`** (10⁻⁶ m³/s). A case with every member off has a curve of zero flow.

k in the labels is `pumpLineup(undefined, caseInputs(caseId), members).on.length`, the members switched on in that case as solved.

**`OtherGroupCase` gains:**

```ts
/** Its own group curve when drawn (L3): the response's points, the members on and their count. */
curve: { points: readonly PumpGroupCurvePoint[]; on: number; of: number } | null;
/** Why its curve is or is not drawn (null: no ring). */
curveState: 'crossing' | 'through' | 'not_through' | 'same_inside' | 'inside_differs' | 'no_group_curve' | 'no_flow' | null;
```

PumpsView passes `inside: 'same' | 'statuses' | 'differs'` per valued case. Stale cases are drawn, as their rings are, named "(out of date)": a curve is that case's last solve, like its ring. Its k is the last solve's, while its name may already have followed a later toggle (§4.5), so every text that pairs a stale case's name with k says `as last solved: {k} running` (§9.6).

**No new request.** Each other case's ready `/pump-group-curve` answer is cached per case and already holds its whole curve (`state/project.svelte.ts:1476`; `models/pump_groups.py:372-374`). 4d reads only its duty.

### 9.2 Style

- **Colour:** slate `GROUP_OTHER` (#475569, `pump-group-chart.ts:109`), the rings' colour.
- **Width:** 1.5 px. The shown group curve stays 2 px ink.
- **Dashes:** solid where every member is inside its data, `[6, 4]` where a member runs beyond it. This is the shown curve's rule (`groupCurveRuns`), so dashes keep one meaning on the chart.
- **Gaps:** where a point has no flow.
- **Drawing order:** `order: 1`, so the shown case's lines and the system curve draw over the family. Rings stay on top (`order: -1`).

There is no colour per case. Same-count curves lie within 2.44 % (about 4 px on a phone), and different counts are about 50 px apart at their ends (m2). Identity comes from the label, the ring on the curve, the tooltip and the table.

### 9.3 Labels on the curves

**Text:**
- desktop and image: `{numbers} · {k} running`, for example "1 · 3 running";
- phone (`compactLabels`, below 640 px): `{k} running`.

**This case's ink curve** is labelled too while any other curve is drawn: `{k} running (this case)` on desktop and image, `{k} running` on a phone, in ink.

**Placement:**
- **Anchor:** the curve's drawn point of largest flow inside the plot. The label is right-aligned 4 px left of it and 4 px above, clamped to the plot's left edge.
- **Merging:** labels of other curves with equal k whose anchors are less than one label width apart merge into one with their numbers joined in ascending order: `1, 4, 5, 6 · 3 running` (`m4_labels.txt` listed them unsorted, "1, 5, 6, 4"). On Crane tees their ends are 3.7–6.6 px apart.
- **Rows:** from left to right, a label that would overlap the one before, a ring's tag, a marker or a member point's label moves up one 14 px row, at most twice (three rows in all).
- **When it still overlaps** after the third row, the label is not drawn. Its curve keeps its identity in the tooltip, the accessible name's list and the data table, and the notes add `Labels of {n} {curve|curves} are left out for space; the data table lists every curve.`

**One pure function.** The placement is `placeCurveLabels(curves: {anchorPx, k, numbers}[], obstacles: {left, right, top, bottom}[], plot: {left, right, top, bottom}, measure: (text: string) => number)` in `pump-group-chart.ts`, returning each label's text and position or none. The chart plugin calls it with Chart.js's pixels and `ctx.measureText`; the unit tests call it with a fixed-width `measure` and m4's anchors, because the unit projects have no canvas (`vitest-setup-client.ts:9-12` returns a null context) and the `server` project no DOM.

**Measured** (estimated geometry from the measured curves, `m4_labels.txt`):
- 0 overlaps between family labels for N = 4 (Crane and ideal tees), the ladder and N = 6, on phone and desktop;
- with two rows only, the N = 6 phone had one overlap (`m3_labels.txt`);
- ring numbers alone on the curves were rejected (`m2_labels.txt`): on a phone the 1-running curve would read "3", its case's number, which reads as three pumps.

These estimates checked label against label in x only. Against the plot's height, the ring tags, the markers and the member labels, the layout is measured in the browser before L3 merges (§9.4, §10.3).

**Ring tags.** A ring whose cases all have their curve drawn is tagged with its numbers only, on every screen and in the image. Its name is in the legend, the notes and the tables. Lineup names are long (46–64 characters for "1 of 4/6 running (…)"), and 4d's desktop tags of three rings 5–11 m apart would overlap. Rings without a drawn curve keep 4d's tags.

### 9.4 The axes

**The rule.** Other cases' curves do not widen the x-axis. When their largest flow passes the largest flow of everything else on the chart, x max becomes that largest flow × 1.05, rounded up to {1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8} × 10ⁿ in display units. "Everything else" is:
- this case's member lines and points;
- its group curve and group system curve;
- the Group point;
- every ring.

The other curves are cut at the plot's edge.

**The effect** (computed from m1's numbers, not rendered):
- With the base shown, nothing changes: every family curve lies inside the base's.
- With "1 of 4 running" shown on the Crane station, its own lines reach 67 L/s and the rings 85.2 L/s, while the base's curve reaches 216 L/s. Uncut, its own content would take about 31 % of the plot's width; cut, x runs to about 90 L/s.

**The y-axis, while the family is drawn** (decision 25). On every measured station the y-axis runs far above the pumps: 184–443 m on the stations of identical pumps and 125 m on the ladder (`m1_family.txt`, maxHead), because 4b's group system curve is computed to 1.2 × the group curve's largest flow at a rise of 0. The pumps' 0–45 m is then the plot's bottom 9–23 %, about 20–50 px on a 390 px phone, which would have to hold up to seven curves, their rings and tags, the member points and three rows of labels. So while any other case's curve is drawn:
- y max is the largest head of everything drawn except the group system curve (the member lines and points, the group curves of this case and the others, the Group point and every ring) × 1.05, rounded up as x is;
- the group system curve is cut at the plot's top edge. Nothing it shows above the shutoff rise can be a crossing: no group curve reaches there;
- the clip note says so (§9.6).

With no other case's curve drawn, the y-axis keeps Chart.js's range, as in 4b and 4d.

**Measured before merge.** The estimates above are not a rendering. L3 merges only after a browser measurement on the `lineups` fixture at 390 × 844 and 320 px, and at desktop width (§10.3): no family label overlapping another label, a ring's tag, a marker or a member label, and the screenshots kept with the slice's record.

### 9.5 What is claimed

**A ring is called the crossing** of its own group curve with this case's group system curve only in state `crossing`, when all three hold:
- its own duty check agrees (D13);
- 4d's claim is `on`: the same rest of the network, a flow above zero, a rise on both sides, and this case's system duty check agrees;
- its curve is drawn.

This parallels 4b's "Group (crossing)" for the shown case. Measured, the drawn lines cross within D6 of each duty (§3.4).

**Otherwise the words are weaker:**
- `through`: the ring is on its drawn curve, with 4d's words for the system curve;
- `not_through`: the drawn curve does not pass through the ring (D13).

**Showing a low-count case.** Its group system curve is sampled only up to 1.2 × its own flows, so rings of bigger counts lie beyond it (`beyond_range`) and are not called crossings, which is true.

### 9.6 Notes, legend, accessible name, tables, image, readout

**The frame sentence.** While a group curve is drawn, this replaces 4d's `otherNotes` sentence exactly:

> `A ring lies on its own case's group curve where that case has one (none with an active PRV or PSV inside) and the station has one state at its rise (D13). Where its case differs from this one inside the station only in which pumps are switched on, and its curve has flow, that curve is drawn in slate and labelled with the number of pumps switched on; where it differs only outside the station, it is the group curve drawn for this case; otherwise it is not drawn. The list below says, for each ring, which.`

4d's other two variants (an active PRV or PSV inside, and "no group curve is drawn here") are unchanged. The per-ring list (below) gives each ring's state, so the frame sentence need not repeat every condition of §9.1.

**The clip note,** after it when §9.4 cut a curve or the group system curve:

> `Other cases' group curves are cut at the chart's right edge, the largest flow of this case's own lines and the rings; the group system curve is cut at the top, above every pump's head; the data tables list all their points.` Each clause appears only when that cut was made.

**The per-ring list** (4d's "Other cases on the chart (slate rings, numbered): …"). Each entry with a state gains `; group curve: {words}`. In the table the words start with a capital.

| State | Words |
|---|---|
| crossing | `drawn ({k} running): it crosses the group system curve at the ring` |
| through | `drawn ({k} running): it passes through the ring` |
| not_through | `drawn ({k} running): it does not pass through the ring (D13)` |
| same_inside | `the same as this case's: the station is the same inside` |
| inside_differs | `not drawn: the station differs inside in more than which pumps are switched on` |
| no_group_curve | `none: an active PRV or PSV inside` |
| no_flow | `not drawn: no flow at any rise` |

For a stale case, `({k} running)` reads `(as last solved: {k} running)`.

**The legend,** on screen and in the image: one new entry, a slate line, `Other cases' group curves (slate; dashed beyond a pump's data)`, 62 characters (today's group entries are at most about 45, `pump-group-chart.ts:484, 495`; a canvas legend item does not wrap). The frame sentence says what the labels give. In the image, Chart.js's `generateLabels` collapses the family's datasets (flag `curveFamily`) into it.

**Each curve's dataset label** (tooltips):
- from 640 px and in the image: `{numbers} · {name}: group curve, {k} running`, for example "1 · 3 of 4 running (Pump P4 off): group curve, 3 running";
- below 640 px: `{numbers} · {k} running: group curve`, since a Chart.js tooltip does not wrap and names reach 93 characters;
- for a stale case, `{k} running` reads `as last solved: {k} running`, and the name keeps 4d's "(out of date)".

**The accessible name** (`groupSummary`):
- each other case's part gains the same `; group curve: …` words;
- then `; other cases' group curves drawn: {1 (3 running), 2 (2 running) and 3 (1 running)}`.

**Tables** (under "Show data table"):
- **"Other cases' station duties"** gains a column `Its group curve`, with the capitalised words. Its row header keeps "(out of date)".
- **A new table after it,** captioned `Other cases' group curves (station's flow at each rise)`:
  - one row group per drawn case, its header `{numbers} · {name}: {k} running` (scope rowgroup; `as last solved: {k} running` for a stale case);
  - columns `Rise ({unit})` | `Flow ({unit})` | `Note`;
  - the duty's rise noted `Its duty's rise (its duty check).`, and a point without flow by its message, as `groupSampleRows` gives;
  - every point listed, those cut from the chart included;
  - the same scrolling region (`max-h-72 overflow-auto`), a list below 640 px as Running combinations is.

**The image** has the same datasets, labels and clip, with desktop text at 14 px on the 800 px plot. Its notes are `groupNoteLines`: the frame sentence, the clip note and the list.

**The readout.** "Read along the curves" stays on this case's group curve. It reads computed samples only, and other cases' rises differ by their own duty's rise.

### 9.7 Every new UI string, L3

**On the curves:**
- labels `{numbers} · {k} running`, `{k} running`, `{k} running (this case)`, merged `{1, 4, 5, 6} · {k} running` (numbers ascending)

**Legend and tooltips:**
- legend `Other cases' group curves (slate; dashed beyond a pump's data)`
- dataset label `{numbers} · {name}: group curve, {k} running`, below 640 px `{numbers} · {k} running: group curve`; stale `as last solved: {k} running`

**Notes:** the frame sentence and the clip note (§9.6), the state words of §9.6 with `as last solved:`, and `Labels of {n} {curve|curves} are left out for space; the data table lists every curve.`

**Tables:**
- column `Its group curve`
- caption `Other cases' group curves (station's flow at each rise)`
- row-group header `{numbers} · {name}: {k} running`
- note `Its duty's rise (its duty check).`

**Accessible name:** `; other cases' group curves drawn: {…}`

---

## 10. Verification plan

Every slice runs every gate (`cd apps/api && uv run python scripts/record_history.py`, workflow §4), with `pnpm gen:types` giving no difference.

**Not run.** Nothing under `apps/api/src` changes, so these do not apply: the corpus comparison, the fuzz profiles and the corpus checks (4d's precedent, D21).

**Fixtures.**
- `apps/api/tests/fixtures/pump_groups_input.py` gains its cases and regenerates `__fixtures__/pump-groups-input.json`, a generated file.
- Each new case carries every scenario's real `/solve`, group curve and group system curve (`scenarioCases`), with the trace trimmed as 4d's are.
- The fixture's size before and after is recorded (4d grew it from 2.04 to 3.44 MB).

**Rules for existing tests.**
- 4d's tests that drove "Add cases with one pump off" drive "Each pump off" with the same assertions. Only the strings listed in §7.12 under "4d's strings that change" are updated, each to its new words, at the same strictness (ui-guide); each test edit names the string it follows.
- An existing test that toggles a pump's status in a scenario still named "Scenario n" now sees the rename. It asserts the rename (decided behaviour, §6) and is never loosened. The `scenarios` e2e names its scenarios ("Pump off"), so it is unaffected.
- **"The same answer bit for bit"** in every API proof below means: the solved values, `solvedState` without its `timestamp` and `trace`, are equal bit for bit, and the trace is equal apart from D15's additions (a "Changed by this scenario" note per changed element and the methods' scenario section, which list the changes in their stored order). `scenario` and `computeTime` are not compared. The review measured exactly these differences between equal solves (`lineups/review-eng/probe.txt` (a), (b)), with `pumpResults` identical.

**The independent tester** writes `apps/api/tests/unit/test_pump_lineups.py`:
- without reading `services/` or the web code;
- metamorphic through `TestClient`, both sides of every comparison the API's answers, with no typed expected numbers;
- from new client addresses registered in `tests/unit/test_client_addresses.py`.

Each slice adds its part.

### 10.1 L1

**Fixture `lineups`:**
- four `curve_a` pumps on Crane tees, CoolProp water (m1's station);
- scenarios exactly as L1 writes them: By number running in the default order, and Each pump off;
- one speed scenario (`inside_differs`) and one tank-level scenario (`same_inside`), for L3.

**Fixture `lineups-closed-leg`** (the review's `probe2.py` station): PA and PB between two ideal tees, a gate valve VB on PB's discharge isolated in the base case, so PB is `running` at 0.0 L/s there; one scenario with PB off. Each with its real solve.

**L1a, unit** (`utils/pump-lineups.test.ts`; every string word for word):
- **`pumpLineup`:**
  - every permutation of a case's changes gives equal lineups;
  - `other` collects non-member changes, another pump's status and changes that no longer apply;
  - a deleted member is dropped;
  - base statuses are read;
  - `statusOnly`.
- **`lineupGroups`:**
  - the condenser example gives one `parallel` group of 6;
  - the ladder gives [P1, P2, P3]; a 2 × 2 station one `mixed` group of 4; two pumps on one chain a `series` group;
  - the pump-transfer example gives Other only;
  - a 7-pump station falls under Other pumps;
  - a PRV inside a station set `active` moves its pumps to Other, and `frameKey` changes;
  - order; memoised (a spy on `suggestGroups` counts 1 across a press).
- **`sameCase`:**
  - any order;
  - a change equal to the base value ignored;
  - a change that no longer applies ignored;
  - another change never matches.
- **`lineupName`:**
  - N = 2 to 6 with default names (exact strings, `proto-card/output.txt`);
  - shared names with ids;
  - the condenser example by ids;
  - a standby on;
  - two groups joined by "; ";
  - other pumps "on" and "off";
  - a `series` and a `mixed` group named pump by pump ("Pump PB off", "Pump B2 off"), never "k of N running";
  - ` + 1 other change` and ` + 2 other changes`; a change equal to the base value or one that no longer applies not counted; the suffix kept whole within 93 characters;
  - nothing off;
  - tiers 2, 3 and 4 each reached;
  - every name ≤ 93 characters over 1,000 seeded random names and ids;
  - no tier ever lists a subset of the pumps off.
- **`followLineupNames`:**
  - a toggle renames;
  - a scenario renamed in the same edit is not followed;
  - a user's name is never touched;
  - a 4d name follows its own toggles and its pump's rename, not a base edit, and not an added non-status change;
  - a template name follows a base status edit, a pump rename and a frame change;
  - a PRV inside a station set active in the base renames a template name ("1 of 2 running (Pump PB off)" to "Pump PB off"), and the renamed case follows the next toggle;
  - a template name gains ` + 1 other change` when a tank level is added and loses it when the change goes;
  - "Scenario n" follows its first press and comes back when the presses are reversed;
  - "Scenario 3" with a tank change stays; an empty "Scenario 2 (copy)" stored as S5 stays;
  - a copy, in both forms, keeps "(copy)" on a pump rename, a base edit and a frame change, and loses it on a toggle of its own pumps;
  - a copy of a copy ("… (copy) (copy)") follows a toggle; a copy cut at 100 characters is recognised;
  - a deleted pump's case becomes "Scenario n";
  - the notice words: one, two, and more than two (the count with one example).

**L1b, unit** (the same file, and `pump-group-one-off.test.ts` for the line):
- **`lineupPlan`:**
  - all six gates with words;
  - By number running for N = 2 to 6: counts, stopped sets, component-order writes whatever the order;
  - base-off pumps named and not written;
  - idle as `base_state`, and a mixed stop made;
  - on `lineups-closed-leg`'s real base: PB, `running` at 0.0 L/s, is idle, so By number running's only case is `base_state` and Each pump off skips PB;
  - existing found in any order and `[P1 on, P4 off]`, named with its id;
  - "Winter" never a match;
  - a planned name another case has: added, with the item's words and that case's id;
  - ids;
  - past 20 with the count, and both nothing-to-add sentences;
  - the derived stop order: kept for the same On set, the default otherwise, and a saved order back when the same set returns;
  - the summary in the group's name tier (ids for the condenser example);
  - the interchangeability sentence both ways (equal doubles; a control makes it the second);
  - the "Names count every pump of the group" sentence for a subset card, and none for the default card;
  - Each pump off: 4d's plan tests moved and kept.
- **`lineupChartPriority`:**
  - N = 6 with both presets gives 5, 4, 3, 2 and 1 running plus one;
  - the base counts when it is another case;
  - a status-only scenario equal to the base is not a lineup.
- **Running combinations' line** on the fixture's real responses: carrying flow, idle (`no_flow`, and `lineups-closed-leg`'s `running` at 0.0 L/s), off and no result; the words never contain "running".

**L1a, workspace** (`testWorkspace`, 4d's fake solver by scenario id):
- in a shown "2 of 4 running (…)" case, Build's P2 Off renames it in the same step with the notice;
- Undo restores both the status and the name; the undo label names the case after the step;
- a case the user renamed does not follow;
- a base status edit renames a template name and not a 4d name;
- a base PRV status edit renames a template name (the frame changed);
- a pump rename follows; the ScenarioCard's heading then reads the new name with ` (solved as «{old}»)`, and the export's Methods text the same (`about.test.ts`).

**L1b, component** (`PumpLineupsBlock.svelte.test.ts`; `PumpGroupOneOff.svelte.test.ts` rewritten against the block with 4d's assertions under Each pump off):
- the segments switch the preset;
- the stop order's buttons move items in both directions: after "Stop … earlier" and after "Stop … later", `document.activeElement` is the same button of the moved pump; at an end it stays there, `aria-disabled`, with its description;
- the status line's words; Default order appears, resets, and moves focus to the first item's "Stop … later" with its status words;
- the summary's words; the preview's item kinds;
- Add's label, `aria-disabled` and refusal; focus on Solve all after Add.

**L1b, workspace** (4d's fake solver by scenario id):
- Add is one undo step and Undo removes every case;
- "Also show" ticked; the notice's words.

**e2e** (`tests/pump-groups.e2e.ts`, desktop 1280×800 and phone 390×844, against the real API, the `lineups` project opened by link):
1. Solve, open the card: a region named "Add cases", By number running checked.
2. The preview shows the three names.
3. Open "Stop order": on desktop by keyboard (Tab to "Stop Pump P1 earlier", Enter three times, then Tab to a "Stop … later" and Enter once), asserting the focused element after each press; on the phone by taps. The preview updates and the status line speaks.
4. Add 3 cases: the notice, Solve all focused, Solve all.
5. Running combinations has 4 groups with their lineup lines, values equal to the intercepted solves in display units; 3 rings.
6. 4d's two flows kept with the same assertions: select "Each pump off", then "Add 2 cases" on the `one-off` project.
7. No sideways scroll; axe clean with the disclosures open.

**Independent API proof** (`test_pump_lineups.py`, L1 part). Stations: the 4-pump Crane station, the 3-pump ladder of unlike pumps with an idle member (m1's), and the two-pump station with PB's discharge valve isolated (`probe2.py`'s).
1. Each case as L1 writes it equals the hand edit (statuses set in the base, no scenarios), the same answer bit for bit as defined above. Cases: k = 3, 2 and 1 in the default order and a reordered one; each pump off; a base-off pump.
2. Reversing each case's change list gives the same answer bit for bit (as defined above).
3. Each lineup duty lies on the base's group system curve within D6, the curve asked at the duty's flow (measured 2.1 × 10⁻¹⁰ m).
4. The idle-only case is the base's answer within D6 (measured 2.7 × 10⁻¹² relative).
5. Each case's group system curve equals the base's at every shared flow (measured 0.0 m).
6. With PB's valve isolated, PB reads `running` with `operatingFlow` 0.0 in the base, and the case with PB off is the base's answer within D6.

### 10.2 L2

**Fixture `two-systems`:**
- two pumps PA and PB between two tees, PB off in the base (a standby);
- separately, the P1–P3 tee ladder;
- a lone pump P9 on a line of its own;
- scenarios "PB in service, PA off", a crossed lineup over both stations, and "Aged pipe" (a pipe change with P2 off);
- each with its real solve.

**Unit** (`utils/lineup-table.test.ts`):
- **Columns:**
  - `two-systems` gives [PA, PB], [P1, P2, P3] and Other [P9];
  - the header row only with two or more groups;
  - the filter.
- **Cell states:**
  - the base value;
  - a case's own value;
  - a change equal to the base still marked;
  - a standby on.
- **Notes:**
  - "{n} other changes", counting statuses hidden by the filter and changes that no longer apply;
  - "Same case as …" via `sameCase`.
- **Schema guard:** `schemaChoices('Pump', 'status')` is exactly `['on', 'off']`, with the registry's labels On and Off.

**Workspace** (`state/lineup-table.test.ts`, the `server` project in Node, `testWorkspace`, a fixed clock):
- **The press equals the Build edit through the store.** Two workspaces run the same sequence (P3 off, P1 off, Q2 off, P3 on, PB on): one through `ws.editScenario`, as the table calls it, one by `setCase` and `ws.editComponent` with the Status segment's change. `canonicalJson(store.project)` and `encodeProject` (the link) are equal. This is repeated on a scenario with an app-made name, where both rename.
- **Back to the base value** removes the change.
- **One undo step per press,** labelled with the name after the step ("turn Pump P3 off in 3 of 4 running (Pump P3 off)"); the case shown is unchanged after Undo.
- **The 31st change** is refused with the exact words, and nothing changes.
- **Staleness** (fake solver):
  - a press in a solved case makes only that case out of date;
  - Undo makes it current again;
  - a round trip without Undo leaves it out of date (the documented cost).

**Component** (`components/workspace/PumpLineups.svelte.test.ts`, jsdom):
- **Identity through the components.** A press in the rendered table and a press of `RegistryField`'s Status segment rendered in a harness, as `PumpsView.svelte.test.ts` does with `testWorkspace`, give the same project JSON.
- **Tabs and width:** no tabs with 0 or 1 pump and the manager stays `wide`; with 2 or more pumps, tabs and `xl`, the tab remembered, Cases when a card is asked for; the panel `.dense`.
- **Grid:** roles, the caption, the group header row with each group's ids; a `mixed` group's header and the series sentence.
- **Switches:** names from the visible headers (`aria-labelledby`), never containing the state word; `aria-checked`, the changed description and `title`; base cells `aria-readonly`.
- **Keys:** arrows, Home/End, Ctrl+Home/End; Tab leaves the grid; Space presses.
- **Focus** kept through a press, an undo, a redo and a rename (`document.activeElement` is the active cell after each).
- **The Tab stop never vanishes:**
  - Undo of New lineup with focus in the grid: Tab still lands in the grid, on the nearest remaining row;
  - an Undo that removes a pump column: the active cell moves to the first column;
  - an Undo to one pump: the tab row goes, Cases shows, focus is on the dialog's title.
- **New lineup:** the name, focus, the status line, the 20 limit with its `aria-describedby`.
- **Undo and Redo:** their names and the status line; Ctrl+Z and Ctrl+Shift+Z from a focused switch give the same status words and keep the focus.
- **The manager's status line** (both tabs): a Remove of a status change in the Cases tab announces the rename there; three renames give the count form.
- **Delete** in the Cases tab with the tab row: focus on the `Cases ({n})` tab.
- **The filter** from the card, and "Show every pump".
- **The alert line** on refusal.
- **Phone** (`matchMedia` stubbed):
  - the picker and its default; an Undo that removes the picked case falls back to the default;
  - the segments with Changed · Base · Reset, and Reset following the name rule;
  - the base list read-only;
  - New lineup picking the new case and focusing the picker.
- **The card** (L1's block test): "Pump lineups table…" opens the manager on Pump lineups, filtered to the members.

**e2e** (`tests/pump-lineups.e2e.ts`, 1280×800 and 390×844, the real API):
1. **The condenser example.**
   - Scenarios → Pump lineups shows 6 columns and the rows "Base case" and "Winter: tower bypassed".
   - The winter case's five status changes (CWP-2 to CWP-6 off, `examples.ts:641-642`) show Off and marked, with "14 other changes".
   - New lineup gives "Scenario 2", "Same case as the base case".
   - Press P6, then P5: "5 of 6 running (P6 off)", then "4 of 6 running (P5, P6 off)" (ids, §4.4).
   - Undo goes back one step; arrows and Space work.
   - Done, Solve all: the case solves with CWP-5 and CWP-6 off in its results.
2. **Identity.** A second page makes the same case by New scenario and Build's Status segments. The two link fragments, decoded, are equal apart from `metadata.modified`.
3. **`two-systems`** (opened by link):
   - the group header row "Pumps together, PA and PB", "Pumps together, P1 to P3", "Other pumps";
   - PB turned on, marked "Base value Off";
   - a crossed lineup named with "; ".
4. **From the card.** "Pump lineups table…" shows the card's pumps only; "Show every pump" shows them all.
5. **Phone.** The picker; segments with Changed · Base · Reset; New lineup selects the new case; no sideways page scroll at 390 px and 320 px.
6. **Layout and axe.** At 1280×800 with 21 rows and the condenser example's names, the dialog body does not scroll and at least 6 rows are fully visible in the table's box. The Cases tab at `xl` is measured too: no prose line longer than `max-w-prose`, and the body's scroll recorded. axe is clean with the tab open, filtered and unfiltered.

**Independent API proof** (L2 part):
1. On `two-systems`, a standby put in service (`[PB on, PA off]`) and a crossed lineup each equal the hand edit, the same answer bit for bit as defined in §10.
2. A scenario whose only changes equal the base values (a pump's `on` where it is on) gives the base's answer, bit for bit as defined in §10 (measured: `pumpResults` identical; the trace gains D15's note and methods section). "Same case as the base case" is therefore a fact about every solved value.
3. Reordering a case's changes gives the same answer bit for bit (as defined in §10).

### 10.3 L3

**Unit** (`pump-group-chart.test.ts`, `pump-group-others.test.ts`, on the `lineups` fixture's real responses):
1. **The drawn points** of each curve equal its response's points in display units, in rise order, split into solid and beyond runs exactly where a member's `beyondData` is true, with gaps at null flows.
2. **Which curves are drawn:**
   - lineup siblings, yes;
   - the base when a lineup is shown, yes;
   - stale, yes, named "(out of date)";
   - `same_inside`, no;
   - `inside_differs` (the speed scenario), no;
   - a PRV or PSV refusal, no;
   - `no_flow`, no;
   - unticked or past the cap, no;
   - this case's curve not drawn, no.
3. **The states:** crossing, through and not_through from duty-check and claim combinations.
4. **Labels** (`placeCurveLabels`, pure, with a fixed-width `measure`):
   - text by view (desktop, phone, image) and this case's label;
   - equal-k ends merged within a label width, numbers ascending, and not otherwise (the ladder's unlike pumps);
   - at most three rows, and m4's placements on its four families;
   - a label that still overlaps after the third row, against a label, a ring's tag, a marker or a member label passed as obstacles, is left out, and the notes' sentence counts it;
   - ring tags numbers-only exactly when every case of the ring has its curve drawn.
5. **The legend:** one new entry of 62 characters; in the image, one entry for the whole family.
6. **The notes:** the frame sentence, the clip note's clauses and the list words, exactly; a stale case's `as last solved: {k} running`.
7. **The accessible name.**
8. **x max:**
   - none set with the base shown;
   - with "1 of 4 running" shown, set from its own lines and rings, nicely rounded;
   - every ring inside it.
9. **y max:**
   - none set while no other case's curve is drawn (4b's and 4d's charts unchanged);
   - with the family drawn, set from every drawn head except the group system curve, nicely rounded, and every ring and point inside it;
   - the group system curve's points above it cut, and the clip note's clause present.
10. **The new table's rows** and the column's words.
11. **`pumpGroupConfig`:**
    - family datasets slate, 1.5 px, dashes as the runs, `order: 1`;
    - tooltip labels per case, the short form below 640 px, and a stale case's `as last solved:`;
    - `forImage` carrying them with full labels.

**Component** (`PumpGroupChart.svelte.test.ts`): the new column; the new table's caption, row groups and phone list classes; the legend entry.

**e2e** (after L1's flow, desktop and phone):
- the chart's accessible name lists the curves;
- the data table shows "Other cases' group curves" with the three cases and each one's 42 rows, equal to the intercepted responses in display units;
- "Download image" works with the family on;
- axe is clean.

**Before merge: the layout measured in the browser** (decision 25). On the `lineups` fixture with the family drawn, at 1280×800, 390×844 and 320 px: screenshots of the chart, and from the drawn labels' boxes no family label overlapping another label, a ring's tag, a marker or a member label, and the pumps' region taking most of the plot's height. The screenshots and the measured boxes are kept in the slice's record (§15). If a label still overlaps, the fallback of §9.3 must be what is drawn.

**Independent API proof** (L3 part, the 4-pump Crane station). It proves what the chart relies on; the drawing is the web's own unit test.
1. Each lineup case's group curve has its duty check agreeing: the ring is on its own curve.
2. Each spans the same 41 rises plus its own duty's (head 0 to the shutoff), so curves can be compared rise by rise.
3. At every shared rise where both compared flows are above 10⁻⁶ m³/s (the duty check's floor), the flows rise strictly with the number running. At the shutoff rise every flow is round-off around zero and the order is not tested there (measured: 0 inversions above the floor, 2 to 4 at 45 m; `lineups/review-eng/order_check.py`). This is a property of identical pumps, not a claim of the web.
4. The four "3 running" curves differ by more than D6 somewhere (measured 2.44 %): not one curve.
5. Straight lines between each curve's 42 points cross the base's group system curve, joined the same way, within D6 of the case's duty (measured at most 0.036 % / 11.1 mm).
6. The ladder's idle-pump case: its group curve differs from the base's while its duty is the base's (D13).

---

## 11. Files to change

### 11.1 L1 (`web/pump-lineups`)

**L1a, new:**
- `apps/web/src/lib/utils/pump-lineups.ts`: §4 (`pumpLineup`, `lineupGroups`, `frameKey`, `effectiveChanges`, `sameCase`, `lineupName`, `followLineupNames`, `renameNotice`);
- `utils/pump-lineups.test.ts` (L1a's part).

**L1a, changed:**
- `state/workspace.svelte.ts`: the one commit path with `followLineupNames` (`edit`, `updateStored`), undo labels naming the case after the step, the comment at :198;
- `components/results/ScenarioCard.svelte`: the heading's stored name and ` (solved as «{old}»)`;
- `utils/export/about.ts`: the Methods text's case name and `, solved as «{old}»`;
- the workspace and `about` tests.

**L1b, new:**
- in `pump-lineups.ts`: `lineupPlan`, `withLineupCases`, `lineupChartPriority`, the block's words;
- `components/results/PumpLineupsBlock.svelte` and its `.svelte.test.ts`;
- `apps/api/tests/unit/test_pump_lineups.py` (the tester's);
- new rows in `tests/unit/test_client_addresses.py`.

**L1b, changed:**
- `utils/pump-group-one-off.ts`:
  - `onePumpOffPlan` becomes the `each` branch of `lineupPlan`, its idle skip by flow;
  - `isOnePumpOff` is replaced by `sameCase`;
  - `chartPriority` is replaced by `lineupChartPriority`;
  - `runningCombinations` gains the lineup line;
  - the module comment.
- `components/results/PumpGroupChart.svelte`: the block.
- `components/results/PumpsView.svelte`: the plan, the add, the preset and order handlers, the props.
- `state/workspace.svelte.ts`: `lineupPreset` and `pumpStopOrder`, reset on load.
- `PumpGroupOneOff.svelte.test.ts`, rewritten.
- `tests/pump-groups.e2e.ts`.
- `apps/api/tests/fixtures/pump_groups_input.py`, with the `lineups` and `lineups-closed-leg` cases, and the regenerated `pump-groups-input.json`.

**Docs:**
- `docs/decisions/D24-pump-lineups.md`, with its rows in `decisions/README.md` and `CLAUDE.md`; its Later list keeps §12.1's items apart, as not built by the owner's choice;
- D21's slice 4d web paragraph: the block is now D24's Add cases, the chart order D24's, and a member "carrying no flow" is read from its flow (§3.5);
- PRD §3.2.2 (the "One pump off" sentence) and §3.8 (one line);
- SDD §3.1.3 (the Pumps together paragraph's "One pump off");
- TSD §10.2 (the new API test file) and §10.3 (web tests and e2e);
- TSD §12: a new "Decided" item for D24, with item 15's one-pump-off sentence pointing to it;
- this proposal's status line and §15;
- `proposals/README.md` (a row);
- `history.md`, `verified-state.md` (by `record_history.py`) and `roadmap.md` ("cases with one pump off of a scenario" becomes "lineups made from a shown scenario").

### 11.2 L2 (`web/pump-lineups-table`)

**New:**
- `utils/lineup-table.ts`: columns from `lineupGroups` with the filter, cell states, notes;
- its test;
- `components/workspace/PumpLineups.svelte` (the panel, the grid, the phone list) and its test;
- `state/lineup-table.test.ts`;
- `tests/pump-lineups.e2e.ts`.

**Changed:**
- `state/workspace.svelte.ts`: `editScenario` (with `quiet`); `ws.edit` refactored onto it with unchanged words; `managerTab` and `managerPumps`;
- `components/workspace/ScenarioManager.svelte`: the tabs and the derived shown tab, `xl`, the Cases prose at `max-w-prose`, each tab's footer, the shared status and alert lines, the undo and redo keys, `aria-describedby` on New scenario and Duplicate when full, focus on the `Cases ({n})` tab after a Delete;
- `PumpLineupsBlock.svelte`: the button;
- `pump_groups_input.py` (the `two-systems` case) and the regenerated JSON;
- `test_pump_lineups.py` (L2 part).

**Docs:**
- D24 (L2's web defaults);
- PRD §3.8;
- SDD (the Scenarios manager's description);
- TSD §10.3;
- `ui-guide.md`, one pattern: "A matrix of toggles is a grid: one Tab stop, arrows between cells; a phone shows one row at a time with segments", with the exception to the 2.5.3 rule: "a switch's state word is its value, not its label; its name comes from its row and column headers";
- this proposal's §15;
- `history.md`.

### 11.3 L3 (`web/pump-lineups-curves`)

**Changed:**
- `utils/pump-group-one-off.ts`: `insideOf`, `sameInside`, `OtherGroupCase.curve` and `curveState`, `OTHER_CURVE_WORDS`; `otherGroupCases` takes `inside` and `on`.
- `utils/pump-group-chart.ts`:
  - `GroupChartData.otherCurves` (per drawn case: numbers, name, k, solid and beyond runs, label pieces);
  - `xMax`;
  - `groupLegend` (+1);
  - `yMax` while the family is drawn, and the group system curve cut at it;
  - `otherNotes` (frame sentence, clip note, list words, the left-out labels sentence) and `groupSummary`;
  - ring `tag` and `short`;
  - a new `otherCurveRows`;
  - `placeCurveLabels`, the pure placement (§9.3).
- `utils/pump-chart-config.ts`, `pumpGroupConfig`: the family datasets, the curve labels drawn where `placeCurveLabels` puts them, `scales.x.max` and `scales.y.max`, the legend collapse, the short tooltip below 640 px.
- `PumpGroupChart.svelte`: the column and the new table.
- `PumpsView.svelte`: the `inside` memo, passing `on`.
- Tests as in §10.3; `test_pump_lineups.py` (L3 part).

**Docs:**
- D24 (L3);
- D21's 4d paragraph: the frame sentence, and "never a crossing" becomes "never a crossing unless D24's three conditions hold" (§9.5);
- SDD §3.1.3;
- TSD §10.3;
- this proposal's §15;
- `history.md`.

**All slices.** Nothing under `apps/api/src`, no generated API type, no `METHOD_VERSION` or `METHOD_CHANGELOG` change.

---

## 12. Later, and not built

### 12.1 Not built (owner, 2026-11-04)

The owner turned these down or chose to leave them. They are not planned work:
- **Every combination**, at any size: removed from L1 "even for <=4 pumps". All subsets fit 20 only up to four pumps (2^N − 2: 2, 6, 14, 30, 62; `f_combinatorics.txt`).
- **Raising `MAX_SCENARIOS`:** the owner kept 20 (an API change).
- **"The rest differs" narrowed** to the station's connected network: the owner chose to leave it as 4d words it. Narrowing it would need an independent D6 proof.

### 12.2 Later

- **Lineups made from a shown scenario** (owner, decision 5), for example aged pipe with 2 of 4 running: flat copies of that scenario with its pumps changed. The card's gate 3 says how to do it by hand meanwhile.
- **Cases crossed across stations:** two 3-pump stations, each keeping one pump running, already make 48 cases (`f_combinatorics.txt`). The table makes any one crossed case by hand.
- **Reusable pump states:**
  - What it is: a named on/off state shared by several scenarios, like Bentley's Initial Settings alternatives or PIPE-FLO's lineups, crossed with other variables (NBU's new and aged pipe at each wet-well level).
  - Why Later: it is a D15 model change and the owner's call.
- **Lead/lag/standby roles and staging:** deferred by D5, pending D11's patent review of US 8,265,911 (`proposals/vfd-pump-modes.md`). A "per pump type" preset that treats pumps as interchangeable from their inputs is not built: the measured spreads reach 22.6 %.
- **Series lineups, a stopped pump passing flow:** no cited loss law (D21).
- **Pump states treated as interchangeable** ("any k running" as one case): never; §3.
- **A batch endpoint:** an API change. A batch was not built or timed.
- **On the chart:**
  - drawing other cases' curves whose station differs inside in other ways (a speed, a setpoint, a valve);
  - capping the group chart's y-axis near the pumps' region on steep systems when no other case's curve is drawn (L3 caps it only while the family is drawn, §9.4);
  - reading other cases' curves in "Read along the curves".
- **Outside this proposal, its own task:** the State column (`pumpStatusLabel`, `results.ts:851`) shows "Running" for a pump that is on and carries no flow behind a closed valve (§3.5). The API could report `no_flow` there, or the label could say "Running (no flow: its line is closed)". Either is a change of its own, with its own proof; L1 reads the flow and does not depend on it.
- **On the card:** a per-case untick in L1's preview (today a case is deleted after the add).
- **In the table:**
  - per-row solve chips and Solve all inside the dialog;
  - renaming;
  - a "merge same cases" action;
  - valve statuses (PIPE-FLO's lineups include valves; the owner asked about pumps).

---

## 13. Questions for the owner

All answered on 2026-11-04 ("Go with your recommendations; merge both, then build L1 (minus the "every combination", even for <=4 pumps), L2 and L3."): each the recommended option, except that "Every combination" was removed at every size.

| # | Question | Options | Answer (2026-11-04) |
|---|---|---|---|
| 0 | PR #261 (4d): merge as is, or rework first? | Merge after #260 (recommended: its cases are valid, and lineups reuse its rings, Running combinations and per-case requests) / rework | Merge both. Done: `main` `a1cf7b7`. |
| 1 | The default preset | By number running (recommended) / Each pump off | By number running |
| — | "Every combination" (2^N − 2 cases), offered up to four pumps | Offer where it fits under 20 (recommended then) / leave out | Left out at every size |
| 2 | Which pumps stop first | Editable, the last listed stops first (recommended) / always the first k running | Editable, the last listed stops first |
| 3 | Names | "2 of 4 running (P3, P4 off)" (recommended) / "2 of 4 running: P1, P2". And: a name the app made follows later toggles until the user edits it (recommended) | Both as recommended |
| 4 | The scenario limit | Keep 20 (recommended) / raise it (an API change) | Keep 20 |
| 5 | Lineups made from a shown scenario | A later slice of flat copies (recommended) / shared pump states (a D15 model change) | A later slice |
| 6 | "The rest differs" for another system's lineups | Leave it (recommended) / narrow it to the station's connected network | Leave it |
| 7 | What to build | L1, L2, L3 | L1 (without Every combination), L2 and L3 |

**No question is open.** Every other choice here is the designers' own and reversible under D14 (§1.4). That includes the naming tiers, the follow rule's reach to "Scenario n" and "(copy)", the table's layout and the chart's labels.

**After the reviews, still none.** No finding needed an owner's decision reopened (§14). Three fixes touch the edges of the owner's answers and are recorded here for the owner to see:
- **Names of pumps in series and of a mixed group** (answer 3): named pump by pump ("Pump PB off"), because "1 of 2 running" would name a case where nothing flows (decision 24). The owner's form stands for pumps in parallel, as the request was.
- **Each pump off** (answer 1, "4d as built"): its names and cases are 4d's; only its idle skip now reads the flow, to match D21's own words ("a member on but carrying no flow gets none"), so a pump on behind a closed valve no longer gets a case equal to the base.
- **A template name on a case with other changes** (answer 3): it keeps following and ends ` + n other changes`, so it never reads as a pure lineup.

---

## 14. Review record

Two reviews ran on 2026-11-04 against `a1cf7b7`, read-only: an engineering review (truth, traceability, D13, D15, D17, D21; its probes through the API's `TestClient`) and a web review (UX, phones, accessibility, buildability). Their notes are kept with the design notes: `lineups/review-eng.md` with `lineups/review-eng/`, and `lineups/review-web.md`. The reviser checked each finding against the code at `a1cf7b7` and the measurement files before changing this text.

Verdicts:
- **Confirmed** means the reviser reproduced the evidence from the code or the files and applied a fix;
- **Answered** means the finding asked a question that this text or the owner's answers already settle.

No finding was refuted, and none needed an owner's decision reopened. §13 records the three fixes that touch the edges of the owner's answers.

### 14.1 Engineering review (2 blockers, 5 major, 13 minor)

| # | Finding | Verdict | What changed |
|---|---|---|---|
| E1 | **Blocker.** The API reports a pump that is on behind a closed valve as `running` at exactly 0 flow, so "running" cannot mean "carries flow" in the Running combinations line, the About sentence or the idle rule. | Confirmed: `results.py:816-817` sets `running` from the solver status alone; the probes give `running, 0.0 L/s` in parallel, in series and in a 2 × 2 station. | §3.5 defines "carries flow" and "idle" by `\|operatingFlow\|` against `DUTY_CHECK_FLOOR`. The line reads `{r} of {n} carrying flow: …` (§7.10), gate 6 says "carries flow" (§7.2), and the idle rule uses the flow test for both presets (§7.4; for Each pump off this matches D21's own words). Decisions 14 and 17 are reworded. New fixture `lineups-closed-leg`, unit cases and API proof 6 (§10.1). The State column's "Running" is listed as its own task (§12.2). |
| E2 | **Blocker.** Names say "k of N running" for pumps in series and for a 2 × 2 station, which the finder calls `parallel`. | Confirmed: `pump-groups.test.ts:228-256`; probe (c) and (d). | `lineupGroups` gains the kind `mixed` for a kept `parallel` group that holds a series chain (§4.2). `series` and `mixed` groups are named pump by pump (§4.4, decision 24). L2's headers read "Pumps together, in series" and "Pumps together, some in series", with the series sentence (§8.2, §8.3). Unit tests for both kinds. |
| E3 | **Major.** A copy of a copy is never recognised, so its name goes false. | Confirmed: `copyName` appends one " (copy)" per call (`scenarios.ts:207`). | `appNames` recognises any number of `copyName` levels, the 100-character cut included, and rule 4 keeps the same number (§4.5). Unit tests for a copy of a copy and a cut copy. |
| E4 | **Major.** A valve's status edit can change the frame without the rule running, so a name stops following. | Confirmed: `isPressureControl` reads `status === 'active'` (`pump-groups.ts:71-78`). | The rule also runs when `frameKey(lineupGroups(before))` differs from `after`'s (§4.2, §4.5). Example row and unit and workspace tests for a PRV set active. Same as W6. |
| E5 | **Major.** A case with other changes keeps a pure lineup name, by order of edits; a 4d name is renamed when a non-status change is added. | Confirmed by tracing §4.5's rules. | A template name ends ` + {n} other change(s)`, counting effective non-status changes, kept within 93 characters (§4.4). 4d forms compare status changes only, in `appNames` and in rule 2, and never take the suffix (Each pump off is 4d's as built). The remaining order-dependence ("Scenario 2" stays when the tank comes first) is stated: both names are true (§4.5). Tests both ways. |
| E6 | **Major.** The interchangeability sentence sends the user to Each pump off, the least sensitive check, and the second sentence overclaims. | Confirmed: `subsets.txt` (0.82 % at 3 of 4, 4.47 % at 1 of 4 on Crane tees). | Both sentences reworded to "can change" and to the stop order (§7.6), the table added to §3.3, decision 15 updated. |
| E7 | **Major (L3).** "Flows rise strictly" is false at the shutoff rise, where every flow is round-off; proof 3 would fail. | Confirmed: `order_check.txt`; the reviser's `cd_order_check.txt` finds the same over `cd_running.json` (0 inversions above the floor). | §3.4 and L3 proof 3 restated over flows above 10⁻⁶ m³/s, citing the saved scripts. |
| E8 | **Minor.** "Bit for bit" proofs leave out fields that differ. | Confirmed: `probe.txt` (a), (b). | One definition in §10 (the solved values without `timestamp` and `trace`; the trace apart from D15's additions); every proof refers to it. |
| E9 | **Minor.** After a rename that leaves the case current, the ScenarioCard's heading and the Methods text keep the old name. | Confirmed: `hydraulicFingerprint` leaves out names; `ScenarioCard.svelte:53` and `export/about.ts:607-608` read the response. | Of the two fixes offered, the one that shows the truth: both name the stored name with "solved as «old»" when they differ (§5, §6, L1a files and tests). |
| E10 | **Minor.** Rule 4 contradicts its test, and "Scenario n (copy)" is never recognised. | Confirmed: `newScenarioName` takes n from the copy's own id. | "Scenario n (copy)" is not app-made, said so (§4.5, decision 12). A copy keeps "(copy)" only when the edit left its own status changes alone; the test names both forms. |
| E11 | **Minor.** §5's headline overclaims; the ScenarioCard lists changes only. | Confirmed: `ScenarioCard.svelte` lists `applied` changes. | Headline "A lineup name never lists only some of the pumps that are off"; 4d's names described as one change against the base; the State column named as every pump's status (§5). |
| E12 | **Minor.** A subset card shows two counts for one case without saying why. | Confirmed (§1.5 item 1's cost). | The preview adds "Names count every pump of the group {…}." (§7.7, §1.5). Same as W16's sixth point. |
| E13 | **Minor.** Words: "runs in every case"; the legend's "pumps running"; unsorted merged numbers; L2 never says "running" means switched on. | Confirmed. | "Stays on in every case" (§7.5); the legend no longer speaks of labels (W18) and the frame sentence says "the number of pumps switched on" (§9.6); numbers ascending (§9.3); L2's intros say it (§8.2, §8.10). |
| E14 | **Minor (L3).** The frame sentence overclaims; D21's "never a crossing" needs updating. | Confirmed: D21 line 31. | The frame sentence adds "and its curve has flow" and points to the per-ring list for the rest (§9.6); L3's docs rewrite D21's words (§11.3). |
| E15 | **Minor (L3).** A stale curve's tooltip pairs the current name with the old count. | Confirmed. | "as last solved: {k} running" in the tooltip, the state words and the table (§9.1, §9.6), with tests. |
| E16 | **Minor.** "Same case as" and "already a scenario" notes should give the id. | Confirmed. | Ids added (§7.4, §7.7, §8.4). |
| E17 | **Minor.** §12 lists the owner's refusals as Later. | Confirmed. | §12.1 "Not built (owner, 2026-11-04)"; D24 keeps them apart (§11.1). |
| E18 | **Minor.** §3.4's "k × one pump" figures are the all-running rows; the curves have 42 points. | Confirmed: `cd_running.txt` lines 25, 55, 111 are k = N. | "With all N running", the k = 3 and 2 figures added (lines 119 and 127), "42 points" (§3.4). |
| E19 | **Minor (L3).** The curve family's readability is unverified: it sits in the plot's bottom 9–23 %. | Confirmed: `m1_family.txt` maxHead 184–443 m. | Both fixes: a y cap while the family is drawn, with the group system curve cut and the clip note extended (§9.4, decision 25), and a browser measurement at 390 × 844, 320 px and desktop as a merge condition (§10.3). Same as W9. |
| E20 | **Minor.** The test-update rule understates which 4d strings change. | Confirmed against `pump-group-one-off.ts` and `PumpGroupChart.svelte:1097-1145`. | §7.12 lists every 4d string that changes; §10's rule refers to it. |

### 14.2 Web review (1 High, 11 Medium or Low–Medium, 10 Low)

| # | Finding | Verdict | What changed |
|---|---|---|---|
| W1 | **High.** "Stop … later" loses focus: a keyed `{#each}` moves the focused node. | Confirmed: Svelte 5.57.2's `reconcile` moves `effect` before `current` (`each.js:540-570`), so for `[A, B, C, D]` to `[A, C, B, D]` it moves B. | §7.5: after each move, `tick()` and an explicit focus on the moved pump's button (`data-stop-id`, `data-dir`); the "keyed by id" reasoning struck. Component and e2e tests press both directions. The same explicit refocus in L2's grid (§8.7). |
| W2 | **Medium.** The L2 cells are 44 px: the manager is outside `.dense`. | Confirmed: `layout.css` sets `--ctl-h` 2.75 rem outside `.dense`; the manager renders from `WorkspaceHeader.svelte:398-404`. | The panel is `.dense` in both layouts (§8.2, §8.5, §8.10); §7.3 corrected to 44 px. |
| W3 | **Medium.** The grid's one Tab stop, the shown tab and the phone's picked case can outlive what an Undo removes. | Confirmed: nothing in the text clamped them. | All three derived and clamped (§8.1, §8.7, §8.10, decision 26); three component tests (§10.2). |
| W4 | **Medium.** Ctrl+Z inside the dialog cannot reach the panel's status line; phones have no Redo there. | Confirmed: the shortcut is on `window` (`Workspace.svelte:67-88`) and `#history` only notifies behind the modal (`workspace.svelte.ts:517-527`). | Of the two seams, the manager's own key handler, calling the same functions as its buttons (§8.1, §8.9); a Redo button in the Pump lineups footer (§8.2); tests from a focused switch. |
| W5 | **Medium.** Rename notices are unbounded, fade after 6 s, and are silent behind the modal. | Confirmed: `Workspace.svelte:50-58`. | More than two renames give a count with one example (§4.5). The manager has one status line for both tabs, so the Cases tab's renames are said inside the dialog (§8.1); a test for a Remove in the Cases tab. |
| W6 | **Medium.** The follow rule's pre-check misses frame changes. | Confirmed (as E4). | As E4. |
| W7 | **Medium.** L1 is too big for one verified slice. | Confirmed: the follow rule changes behaviour for every project. | L1 is built in two verified steps on its branch, L1a (names and the commit path) then L1b (the card), each with its gates and review (§7, §10.1, §11.1, decision 23). The branch and what is built are unchanged. |
| W8 | **Medium.** At 1280×800 the table shows about 4–5 of 21 rows, not 8. | Confirmed as an estimate from `Dialog.svelte` (85 dvh) and the added chrome; not measured. | The legend, the filter and the series sentence fold into the intro; no limit line on this tab (§8.2). The e2e asserts at least 6 rows fully visible and no body scroll (§10.2). |
| W9 | **Medium (L3).** The curve family is crowded on phones; no rule after the third label row. | Confirmed (as E19). | As E19, plus the fallback: a label that still overlaps is left out and the notes count it (§9.3). |
| W10 | **Medium (L3).** The label tests cannot run: Vitest has no canvas. | Confirmed: `vitest-setup-client.ts` returns a null context; the `server` project has no DOM. | The placement is a pure `placeCurveLabels(…, measure)` in `pump-group-chart.ts`, tested with a fixed-width `measure` (§9.3, §10.3, §11.3). |
| W11 | **Low–Medium.** `state/lineup-table.test.ts` runs in Node, where components cannot render. | Confirmed: `vite.config.ts`'s two projects. | The store comparison stays in Node; the component comparison moves to `PumpLineups.svelte.test.ts` (§10.2). |
| W12 | **Low–Medium.** Same-looking names; "(copy)" after a toggle; rule 4 and its test disagree. | Confirmed (with E5 and E10). | The ` + n other changes` count (§4.4); "(copy)" dropped when the case's own status changes change, kept on a pump rename, a base edit or a frame change, since the copy still copies the same case (§4.5); a preview item for a planned name another case has (§7.7). |
| W13 | **Low–Medium.** No focus target after Default order, the phone's New lineup, and a Delete (an `sr-only` heading). | Confirmed. | Default order focuses the first item's "Stop … later" (§7.5); the phone's New lineup focuses the picker (§8.10); a Delete focuses the `Cases ({n})` tab (§8.1). |
| W14 | **Low.** The switches' names leave out the visible "On"/"Off", against the ui-guide's 2.5.3 rule as worded. | Confirmed: `ui-guide.md:45`. | Names from the visible headers by `aria-labelledby`, and the exception recorded in L2's ui-guide pattern (§8.5, §11.2); a test that no name holds the state word. |
| W15 | **Low.** New lineup is `aria-disabled` with only a `title`. | Confirmed: `ScenarioManager.svelte:436-444` does the same today. | `aria-describedby` to an `sr-only` span for New lineup, New scenario and Duplicate (§8.2, §8.8). |
| W16 | **Low.** Ambiguous or overclaiming words (eight points). | Confirmed. | "carrying flow" in the line (§7.10); "Other sets of the same number of pumps…" (§7.7); "can change" (§7.6); "Set in Build" (§8.4); "the same as this case's" (§9.6); group headers with their ids (§8.3); the subset sentence (§7.7); one label source for L1's new text (§7.5). |
| W17 | **Low.** The stop-order summary runs to about 170 characters. | Confirmed. | It uses the group's name tier: ids for the condenser example, 71 characters (§7.5). |
| W18 | **Low (L3).** The legend entry (105 characters) and long tooltips. | Confirmed: today's entries are at most about 45. | Legend `Other cases' group curves (slate; dashed beyond a pump's data)`, 62 characters; below 640 px the tooltip drops the name (§9.6). |
| W19 | **Low.** Two naming styles in one family; does "4d's cases, kept" cover the names? | Answered: the plan the owner accepted says "Each pump off: 4d as built" (`combos/synthesis.md`), its names included. | No change of behaviour; §4.4 states the two styles and why. |
| W20 | **Low.** Undo labels name the case before its rename. | Confirmed. | Labels name the case after the step, in the table and in Build (§8.6); a workspace test. |
| W21 | **Low.** The stop order, the picked case and the active cell must be derived, not written by effects. | Confirmed. | Derived, written only by user actions (§7.5, §8.7, §8.10, decision 26). A saved stop order comes back when the same pumps are on again: accepted and said. |
| W22 | **Low.** The Cases tab gets `xl` unmeasured; lines run to about 140 characters. | Confirmed. | The Cases tab's prose capped at `max-w-prose`; the Cases tab included in the 1280×800 measurement (§8.1, §10.2). |

### 14.3 The reviser's own checks

- `cd_running.json`'s order (E7): `lineups/revise/cd_order_check.py` and `.txt`: 0 inversions above 10⁻⁶ m³/s on five stations, 0 to 2 below it.
- E18's k < N figures were traced to their lines of `cd_running.txt` (119 and 127), now cited in §3.4.
- The 2 × 2 kind, the PRV frame change, `copyName`'s cut, the window shortcut, the 6 s fade, the canvas stub and the two Vitest projects were each read in the code at `a1cf7b7` before the fix was written.

---

## 15. As built

(Empty: each slice records here, numbered, every departure of the build from this text.)
