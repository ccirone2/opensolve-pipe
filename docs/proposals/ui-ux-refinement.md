# Web UI/UX refinement: opportunities

**Status: Tier 1 (items 1–5, and editing an element's name in place) built** (2026-10-25 and 2026-10-26; §5 records where the build departs from this text); the other items are proposals, nothing decided. Written against `7babcc6`. Web app only: no API, model or solver change is needed for anything here except where an item says so. Every item is a reversible web default under D14 unless it is marked **owner** (it touches a decision or a GOALS value).

**Aim.** Keep the interface clean and calm for a first-time user, and let a working engineer go from "build" to "trust and sign off" with fewer trips between panes. The method throughout is progressive disclosure: show the answer and the next action, keep the depth (traces, methods, tables) one step away, never removed.

**How this was found.** The app was run locally (API + `pnpm dev`) and driven with Playwright at 1280×800 and 390×844 through the home page, an example, solve, every results view, the pump chart, a trace, the Build forms and each dialog; the components were read where a screenshot raised a question. An axe-core 4.10.2 scan (WCAG 2.0/2.1 A and AA plus best practice) of the home page, the workspace and the solved workspace found **no violations** at either size, so the items below are about flow and density, not conformance.

---

## 1. What works well (keep it)

- The panel navigator with Prev/Next labels that name the neighbour, the breadcrumb, and Jump to (with a filter).
- Results views that appear only when the network has that kind of element (`availableViews`).
- Flags grouped by severity, each starting with a link to its element, long groups collapsed, a skip link past them.
- Trace → "Show in Build" and "Use in goal seek": the results already link back to inputs.
- On phones, Build and Results are tabs, the Results tab carries the state (error, invalid, out of date), and solve switches to Results.

---

## 2. Measured friction

| # | Observation | Where |
|---|---|---|
| F1 | Before the first row of any results table, the pane shows the project description, a convergence card and seven view pills (two rows). Measured on the first example, the first row of the Nodes, Links and Pumps tables starts 63 % of the way down a 1280×800 viewport and 73–74 % down a 390×844 one. "Converged" is also already in the pane header ("Last solve: converged"). | `ResultsPanel.svelte` |
| F2 | On desktop the results pane gets 2/5 of the width (`lg:flex-[2]` vs `lg:flex-[3]`), so at 1280 px the tables are wider than their 478 px box (Nodes 897 px, Pumps 950 px, Links 608 px) and scroll sideways, while Build has room to spare. | `Workspace.svelte:173–183` |
| F3 | Scenarios and Goal seek are offered on an empty, unsolved project. | `WorkspaceHeader.svelte`, `ResultsPanel.svelte` |
| F4 | The fluid and its temperature, which drive every result, live in Settings next to solver tolerances and units. | `SettingsDialog.svelte` |
| F5 | After opening a trace (which moves Build to that element), the navigator restarts the path there: on the series pump of the first example "Previous" is disabled and Next reads "Next: choose". | `navigator.svelte.ts` |
| F6 | Build shows no solved values. Checking what an edit did means switching to Results (a tab change on phones), finding the element, then switching back. | `ComponentPanel.svelte`, `ConnectionPanel.svelte` |
| F7 | Summary opens with the fluid's properties (inputs) before any answer about the network. | `SummaryView.svelte` |
| F8 | Results tables cannot be sorted or filtered; finding the lowest pressure in a 100-node network means scanning. | `ResultsTable.svelte` |
| F9 | Number fields accept a bare number in the display unit only; "50 psi" in a kPa field is rejected. | `utils/units.ts` `parseNumber` |
| F10 | The pump chart draws head against flow only, though `PumpCurve` carries `efficiencyCurve` and `npshrCurve`. | `PumpChart.svelte` |
| F11 | The only keyboard shortcuts are undo and redo. | `Workspace.svelte:56` |
| F12 | Closing the tab without keeping the link loses the project unless it is found again in browser history. | (no persistence by design, D3) |
| F13 | The current element's name shows three times: the breadcrumb, the heading, and a Name field in Properties. (Found by the owner, 2026-10-26.) | `ComponentPanel.svelte` |

---

## 3. Opportunities

Ordered by value for cost. "Cheap" means one component and its tests.

### Tier 1: cheap, clear wins

1. **Slim the results header (F1).** Fold the project description into a one-line disclosure ("About this project ▸"); merge the convergence card into the pane header line (✓ Converged · 6 iterations · method 1.2.0, the full text on expand); keep the card only when the solve did not converge or failed. On phones, put the views in one horizontally scrolling row of pills. Target: the first table row in the top third of the viewport at both sizes.
2. **Show analysis tools when they can act (F3).** Goal seek appears once there is a successful solve; Scenarios stays reachable (it is useful before a solve) but on an empty project sits in an overflow menu. Nothing is removed, it just arrives when it is useful.
3. **A fluid chip in the header (F4).** "Water · 20 °C" next to the project name opens the Fluid section directly; Settings keeps site, units and an "Advanced: solver" disclosure for friction method, iterations and tolerance.
4. **Keep direction after a jump (F5).** When Build moves to an element from a trace, Jump to or a flag, seed the path with the last solve's flow direction (else the ports' suction/inlet → discharge/outlet roles), so Previous and Next name neighbours as they would after walking there.
**Added to Tier 1 by the owner (2026-10-26): edit an element's name in place (F13)**, as the project name is edited, instead of in a Name field in Properties.

5. **Keyboard for the frequent actions (F11).** Ctrl/⌘+Enter solves, Esc cancels a running solve, Alt+←/→ walk Previous/Next, "?" lists the shortcuts. Invisible to someone who never uses them.

### Tier 2: close the build → result loop

6. **Results in context (F6).** A compact strip at the top of each component and connection panel once results exist: for a pump, flow, head, NPSH margin; for a connection, flow, velocity, head loss; flag icons; "Trace". Out-of-date values are greyed with the existing "out of date" wording. On a connection, the velocity sits beside the pipe size picker, which is where it is needed when sizing. This is the item that most changes the experience on phones.
7. **"Since the last solve" deltas.** Keep the previous response in memory (not in the link) and show the change of each headline value after a re-solve (pump flow +4.1 %, lowest pressure −12 kPa). It answers the commonest question in iterative design (PRD US-004) without setting up a scenario; Scenarios remain the tool for named, shared cases.
8. **Summary that answers first (F7).** Lead with the exceptions (flags, already there) and the extremes, each linked to its element: operating point of each pump, lowest static pressure and where, highest velocity and where, smallest NPSH margin and where. Fluid properties move into a disclosure ("Fluid: Water at 20 °C ▸").
9. **Sortable, filterable tables (F8).** Sort by any column; a "Flagged only" toggle; the Summary extremes link to the sorted table. Matters most at 100+ components.
10. **A wider results pane when wanted (F2).** A draggable divider or a "Focus results" toggle that gives Results 3/5 of the width; the choice remembered in `localStorage` (a per-browser convenience, not project data).

### Tier 3: ideas from other fields

11. **Unit-aware entry (F9; from Mathcad/SMath and calculator search).** Accept "50 psi", "3 in", "120 gpm", "68 °F" in any field of the matching category; convert to SI, show "= 344.7 kPa(g)" under the field, keep the display unit. Correctness rule: a pressure field accepts gauge or absolute units only as the field states, and "psia" in a gauge field is converted through the project's atmospheric pressure with the conversion shown, or rejected; never silently guessed.
12. **Pump chart layers (F10; from manufacturers' curve sheets).** Off by default, as chips under the chart: efficiency curve (secondary axis) and NPSHr against NPSHa. A BEP marker and the ANSI/HI 9.6.3 preferred operating region are design-practice checks, so they belong only behind the opt-in design checks of PRD §5 (GOALS §4.6), not in this change.
13. **Command palette (from code editors).** Ctrl/⌘+K: jump to any element by name or id, add a component after the current one, solve, open settings, switch case, change unit preset. One searchable entry point for experts; the visible UI stays as it is.
14. **Recent projects on this device (F12; owner, GOALS §4.5).** A short list of recent links on the home page, kept in `localStorage`, never sent anywhere, with "Forget all". Nothing leaves the browser, but it is storage of project data the owner should decide on.
15. **A read-only network map (owner, D5 defers the schematic).** The navigator is a keyhole; engineers check networks on a diagram. A layered layout (Sugiyama-style, e.g. dagre, MIT; check the licence before adding) of components and connections, coloured by a result (pressure, velocity) with flags marked, each element opening its panel. It is the largest item here and the one with the most altitude; it waits for the owner because D5 defers the auto-generated schematic.

---

## 4. Suggested order

Tier 1 (items 1–5) as one small change with e2e updates on desktop and phone; then item 6, which carries the most value; then 8 and 9 together (they share the extremes); then 7, 10–13 as separate slices; 14 and 15 only after an owner decision.

Each slice is done when its Vitest and Playwright flows pass at both sizes, axe stays clean, and nothing a trace or the methods summary shows is removed or hidden by default where it was visible before without a disclosure that names it.

---

## 5. Tier 1 as built

Measured as in F1, the first table row now starts 48 % down a 1280×800 viewport (was 63 %) and 53–54 % down a 390×844 one (was 73–74 %); an e2e flow holds it under 55 % at both sizes. axe-core stays clean. Departures from §3:

- **Item 1.** The description is open while there are no results (a shared link's context) and one line with a toggle once there are; the convergence card is one quiet line when converged and the red card otherwise. The view pills are one sideways-scrolling row below 1024 px only: at 1024 px and above the pane is too narrow for seven pills in one row, and a mouse user cannot easily scroll a row sideways, so they still wrap there (item 10 is the fix).
- **Item 2.** Goal seek and Scenarios appear once the network has a component (Scenarios also while the project has scenarios), not after a first solve: the goal-seek design opens its dialog without a solve (goal-seek.md §6.2).
- **Item 3.** The fluid chip is shown from 1024 px only. Below that, at 390, 640 and 768 px, even a temperature-only chip took the project name's room or truncated to nothing; there the fluid stays in Settings and first in the Summary. Settings already kept the convergence options in an "advanced" disclosure, so nothing else moved.
- **Item 4.** A click in the results moves the walk with `jumpTo` (back along the walk, else the shortest path from its start), the rule Jump to already followed, instead of seeding it with the solved flow direction; SDD §3.1.1 and TSD §8 are updated.
- **Item 5.** Only Ctrl/⌘+Enter (solve) is added. Alt+←/→ is the browser's Back and Forward, and a shortcut list for one shortcut is not worth a dialog: the Solve button names it in its tooltip and `aria-keyshortcuts`.
- **Editing the name in place (F13).** The name is a borderless field in the panel's header, styled as the heading was, and stored on Enter or leaving the field, as the project name is; Properties has no Name field. The heading stays for structure and focus, visually hidden (as the workspace's h1 is), and when focus moves to it (after a delete, a case switch or Show in Build) the header shows the focus ring, so a keyboard user sees where focus is. The breadcrumb is unchanged: it also shows a walk of one step (hiding it there was built, then reverted at the owner's word, 2026-10-26).
