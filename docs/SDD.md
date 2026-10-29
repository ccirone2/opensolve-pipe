# Software Design Document (SDD)

# OpenSolve Pipe - Web-Based Hydraulic Network Design Tool

**Version:** 0.2.0 (Rebuild baseline)
**Date:** October 2026
**Status:** Aligned with the rebuild decisions D1–D6 in `CLAUDE.md`

---

## 1. Introduction

### 1.1 Purpose

This document describes the software architecture and design for OpenSolve Pipe, a web-based hydraulic network analysis tool. It serves as the bridge between the Product Requirements Document (PRD) and the Technical Specification Document (TSD).

### 1.2 Scope

This document covers:

- System architecture
- Component design
- Data models
- Interface contracts
- Integration patterns

Items marked **(Later)** are outside v1 (PRD §2.3) and are kept here so the v1 design leaves room for them.

### 1.3 References

- PRD: Product Requirements Document v0.2.0
- TSD: Technical Specification Document v0.2.0
- `docs/GOALS.md`: mission, values and priority order (take precedence over everything below)
- `CLAUDE.md`: rebuild decisions D1–D6 (take precedence over this document)

---

## 2. System Architecture

### 2.1 Architecture Style

**Hybrid Client-Server Architecture, stateless server**

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENT (Browser)                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   Panel     │  │   Results   │  │  Schematic Viewer       │  │
│  │  Navigator  │  │   Panel     │  │  (Later)                │  │
│  └──────┬──────┘  └──────┬──────┘  └────────────┬────────────┘  │
│         │                │                      │                │
│  ┌──────┴────────────────┴──────────────────────┴──────────┐    │
│  │                    State Manager                         │    │
│  │      (Port-graph project model, undo/redo, units)        │    │
│  └──────────────────────────┬───────────────────────────────┘    │
│                             │                                    │
│  ┌──────────────────────────┴───────────────────────────────┐    │
│  │        URL Fragment Encoder / Decoder + Migrations        │    │
│  └──────────────────────────────────────────────────────────┘    │
└─────────────────────────────┬───────────────────────────────────┘
                              │ HTTPS (project sent per request,
                              │ never stored)
┌─────────────────────────────┴───────────────────────────────────┐
│                         SERVER (Python)                          │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                  API (FastAPI / REST)                     │    │
│  └───────┬─────────────────────────────────┬────────────────┘    │
│          │                                 │                     │
│  ┌───────┴──────────────┐          ┌───────┴──────┐              │
│  │   Solver Service     │          │   Fluid      │              │
│  │  (own GGA network    │          │   Property   │              │
│  │   solver, `fluids`)  │          │   Service    │              │
│  └──────────────────────┘          └──────────────┘              │
│                                                                  │
│  Later: Version Control Service, Database                       │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Design Rationale

| Decision | Rationale |
|----------|-----------|
| Hybrid architecture | Client handles UI/state; server handles computation |
| Project in URL fragment | Sharing without accounts; the fragment is never sent to the server, so project data is never logged or stored (D3) |
| Port-graph data model | One model for single-path, branching and looped networks; ports carry sizes and elevations (D2) |
| Own network solver | EPANET cannot model flow-dependent tee losses, real fluid properties, component check/relief valves, or NPSH; a Global Gradient Algorithm solver in Python can (D1) |
| SI storage | Display units never alter the model; the solver needs no unit handling (D4) |
| REST API | Simple, well-understood, future API-ready |

### 2.3 Deployment Model

```
┌─────────────────┐     ┌─────────────────┐
│   CDN / Static  │     │   API Server    │
│   Hosting       │     │   (Python)      │
│                 │     │                 │
│  - HTML/CSS/JS  │     │  - FastAPI      │
│  - Assets       │     │  - Solver       │
│                 │     │  - Stateless    │
└─────────────────┘     └─────────────────┘

Later: database for accounts, short links and version history.
```

---

## 3. Component Design

### 3.1 Frontend Components

The frontend is a static SvelteKit site (TSD §2.1, §3.1) with two pages:

- **Home (`/`)** offers a new project (`/p`) and example projects, each a fixed link: the examples have fixed ids and timestamps, and their values are labeled as illustrative. It also explains that the project lives in the link and what the server receives when solving, and shows the disclaimer, the copyright notice, the license, the source code links (this build's, and the calculation server's: `<API>/source`, TSD §11.1) and the third-party licenses link.
- **Project (`/p#<encoded>`)** decodes the fragment (§5.2) and opens the **workspace**, or shows a link error. An empty fragment starts a new project.

The **workspace** (`components/workspace/Workspace.svelte`) has a header, a **Build** pane (the panel navigator, §3.1.1) and a **Results** pane (§3.1.3):

- **Header.** Home link, editable project name, Undo and Redo (labelled with the change they undo or redo), Solve, Share (§3.1.5) and Settings. While a solve runs, Solve shows a spinner and "Solving…" (below 24rem the label is for screen readers only), and **Cancel** ("Cancel solve"; an icon button on phones, like Share and Settings), to its left, aborts it (PRD §4.2); if Cancel has the focus when it goes, Solve takes it. Solve keeps its width whether it is solving or not (below 22.5rem it shows its icon only, so that Cancel fits beside it), so neither button comes in under the pointer where the other was, and the second click of a double click or double tap on either does nothing (a keyboard press is not affected). Settings covers the description, fluid, site elevation and atmospheric-pressure override, display units, the opt-in design checks (a switch per check, its limits and the cited presets, each pair's order read from `x-ordered-fields`; locked in a scenario, as the site and solver are; §4.15) and solver options.
- **Layout.** From 1024 px the two panes are side by side, Build 3/5 of the width (at most 52 rem) by default; on narrow screens they are tabs. A splitter between them (WAI-ARIA window splitter, `role="separator"`, its value Build's share) resizes them by dragging or with ←/→ (5 % steps), Home and End; Enter or a double-click returns to the default. Each pane keeps at least 22 rem and 25 %. The choice is remembered in this browser (`localStorage`), never in the project or its link. The Results tab is marked (icon and text) when the last solve failed, did not converge, has physically invalid flags or is out of date.
- **Notices.** Info notices fade after 6 s; error notices (e.g. a refused edit) stay until dismissed.
- **Keyboard.** Outside text fields, Ctrl/⌘+Z undoes, and Ctrl/⌘+Shift+Z or Ctrl/⌘+Y redoes.
- **Touch and accessibility.** Buttons are at least 44 px tall. Buttons that can become unavailable while focused (Solve, Undo, Redo) use `aria-disabled` so focus stays on them, and tabs follow the WAI-ARIA tabs pattern.

#### 3.1.1 Panel Navigator

**Purpose:** Primary interface for building and editing the hydraulic network. TSD §8.1 has the details.

**Structure** (`components/panel/`):

```
PanelNavigator
├── Breadcrumb                    // the path walked; each step goes back to that component
├── Jump to → JumpToDialog        // every component, with a filter; marks those not connected to the start
├── ComponentPanel                // the current component: type, id, name (edited in place),
│   │                             //   its last-solve results (ResultStrip)
│   ├── ComponentActions          // Add after, Add before, Add branch, Delete
│   │   ├── AddComponentDialog    // at a free port / into a connection / as a branch (tee or wye)
│   │   └── DeleteDialog          // optional "Join A and B" (keep the neighbors connected)
│   ├── Properties tab
│   │   ├── elevation
│   │   ├── per-type form         // forms/: Reservoir, ReferenceNode, AssignedFlow, Branch (tee, wye),
│   │   │                         //   Pump (+ PumpCurveEditor), IsolationValve, CheckValve, ControlValve
│   │   └── PortsEditor           // port sizes and elevations, what each connects to; reservoir ports
│   └── Piping tab → ConnectionPanel
│       ├── port selector         // which port's connection is shown
│       ├── connected port        // from → to, Go to <other end>, Insert component, Add branch,
│       │                         //   Disconnect; PipeSegmentForm per pipe (+ Add pipe segment);
│       │                         //   FittingsEditor
│       └── free port             // add a component here, plug it, remove it (reservoir),
│                                 //   or connect it to a free port elsewhere (close a loop);
│                                 //   at a relief valve's outlet, Discharge to atmosphere (§4.17)
├── Previous: <name>   Next: <name | choose | connect <port> | end of path>
└── PathChooser                   // the ways forward; loops offered as "Jump back to …"
Later: MiniMap
```

An empty project shows "Start the network": choose and add the first component (a boundary is suggested).

**Navigation over the port graph:**

- **Start.** The walk starts at a chosen component. By default this is the first boundary component (a reservoir or reference node), else the first component.
- **Next.** With one way forward, Next goes there. A way forward is a connection of the current component other than the one it was reached by. With several ways (a tee, a multi-port reservoir), or when a way leads back to a component already on the breadcrumb (a loop), the **PathChooser** asks which to take. A loop is offered as a jump back, which cuts the breadcrumb back to that component instead of extending it. With no way forward but a free port, Next opens that port in the Piping tab so it can be connected.
- **Previous** steps back along the breadcrumb, and each breadcrumb step goes back to that component.
- **Jump to** opens any component. If it is on the breadcrumb, the walk goes back to it; otherwise the breadcrumb is rebuilt as the shortest path (fewest connections) from the start. A component not connected to the start begins a new walk.
- **From the results.** Clicking an element in the results (a table row, a flag, an input problem, a topology issue) moves the walk to it as Jump to does, so Previous and Next keep naming its neighbours. For a connection, the walk moves to its `from` component with the connection's piping open.
- **After edits.** After an edit, undo or redo the breadcrumb is cut back to the part that still exists in the project. It comes back if an undo restores it.
- **Edits move the walk.** Each edit action is one undo step, and the walk moves to the change: an added component becomes the current one, and a branch shows its free branch port.

**State** (`state/navigator.svelte.ts`, `NavigatorStore`; `utils/graph.ts`):

```typescript
interface NavigationStep {
  componentId: string;
  viaConnectionId?: string;      // connection used to arrive here (absent for the start)
}

interface NextOption {           // a way forward from the current component
  connection: PipeConnection;
  portId: string;                // port of the current component
  otherId: string;               // component at the other end
  otherPortId: string;
  outgoing: boolean;             // the current component is the connection's 'from' end
  loop: boolean;                 // leads back to a component on the path
  loopIndex?: number;            // its index in the path
}

class NavigatorStore {
  path: NavigationStep[];        // derived: the stored walk, cut to what is valid in the project
  current: Component | undefined;
  options: NextOption[];
  mode: 'component' | 'connection';  // Properties or Piping tab (kept per component)
  activePortId?: string;         // port whose connection the Piping tab shows
  next(): 'moved' | 'choose' | 'none';
  choose(option: NextOption): void;
  previous(): boolean;
  goToStep(index: number): void;
  jumpTo(componentId: string): void;
  follow(connectionId: string): void;
  showConnection(portId: string): void;
  showComponent(): void;
  restart(componentId?: string): void;
}
```

#### 3.1.2 Schematic Viewer (Later)

**Purpose:** Auto-generated process flow diagram for visualization.

**Responsibilities:**

- Render the port graph as a directed graph
- Use simplified custom symbols (not full P&ID)
- Handle click events to open element in Panel Navigator
- Software-defined layout (user cannot drag elements)

**Layout Algorithm:**

- Hierarchical left-to-right or top-to-bottom layout
- Branches shown as parallel paths
- Loops indicated with return arrows

#### 3.1.3 Results Panel

**Purpose:** Display solved network state and analysis outputs (`components/results/ResultsPanel.svelte`). Solving is never blocked (GOALS §4.6). Solve sends the project with `includeSystemCurve: false`: a plain solve meets the PRD §4.2 solve times, and a system curve (a solve per point, for every pump) is fetched only for the pump being viewed (`PumpChart`, CLAUDE.md D10).

The pane shows, top to bottom:

- **Status line**, the only live region: "Solving…", "Last solve: converged", "did not converge" or "no results", plus ", out of date"; after a cancelled solve "Solve cancelled", or "Solve cancelled. Last finished solve: …" when earlier results or an error are shown.
- **Cancelled solve.** A note says the solve was cancelled before it finished, and that what is shown is from an earlier solve, or that there are no results yet. Earlier results and errors keep their current or out-of-date labels; the failed-solve notice then speaks of the last solve that finished.
- **`ResultsStateNotice`.** The results are out of date when the project changed, in a way that can change them, after the solve. Display units, names and metadata do not count. Results kept from an earlier solve after a later one failed are marked too. Both offer Solve again. The notice also appears in the trace view, so values are never shown without it.
- **Errors.**
  - Topology: "The network cannot be solved as connected", with each issue and a link to each component it names. Every code the builder raises is told in the browser with component, port and piping names ("Piping Tank → Pump, pipe 2") and values in the display units (`utils/issue-text.ts`), chosen by the issue's code and ids and the values its message states, never by rewording the message; lists taken from the project (the components sharing a duplicated id, a component's ports) are given only while the error is current, and ids stay where nothing has a name. A pipe size the library does not have is named by the library's NPS designation when it is a size of another schedule, otherwise in inches with as many digits as it takes to differ from every size of its schedule and the library, so the text never names a size the library has (when the message's figures, 6 significant digits, cannot be told from one, its message is shown). The server's message is kept under a closed **Details** ("Calculation server's message: …", `IssueDetail`); an unknown code, or a message not in the form expected, is shown as the server sent it. A piping issue links to that piping and a port issue opens the port. The goal-seek dialog tells its topology issues the same way, and its request errors' lines in names and display units (a port or pipe the element does not have, a result that applies to another kind of element, the smallest tolerance; `requestLineText`).
  - Validation: the problems.
  - Network: the API could not be reached, with a message that the project is safe in the page and its link.
- **`ConvergenceStatus`**: converged or not, the solver's message (with names and display units), iterations, compute time and the calculation-method version. For a solve that did not converge, it links the components the message names (an assigned-flow node no reservoir reaches, and what closes it off), and gives the largest continuity and energy errors, where they are, and which components kept switching state.
- **`MethodVersionNotice`.** Shown when the link was last solved with another calculation-method version. It lists what changed between the two (`GET /api/v1/method-versions`, GOALS §4.3).
- **`FlagsSummary`.** Flags are grouped by severity (physically invalid, warnings, information). Each has an icon and text in display units and names, never color alone, and starts with a link to its element's trace. Long groups show their first flags with "Show all", and a skip button leads past the flags.
- **Inputs to check.** Problems found in the browser that the solver would also report: no fixed-pressure boundary, ports neither connected nor plugged, a control valve still at setpoint 0, and model-rule problems. Each has a Show button into Build.
- **Views** (tabs; a view appears only when it has results):

| View | Content |
|------|---------|
| Summary | Answers first: each pump's operating point and NPSH margin; then the extremes, each with where it is (a link to its trace) and a link to its table sorted on it: lowest static pressure (gauge and absolute) and highest (Nodes), highest velocity (Links), smallest NPSH margin (Pumps, when there are several). Then, closed, the fluid properties as used with their sources and the atmospheric pressure |
| Nodes | Per component port: elevation, pressure (gauge), absolute pressure, velocity, HGL, EGL; a note on the gauge reference and boundary ports |
| Links | Per connection: flow, velocity, head loss, Re, Darcy f, regime. Each row expands to its pipe segments (diameter, length, roughness, velocity, Re, f, friction loss) and fittings (quantity, the K each used, its reference diameter and source, head loss), with the flags about each |
| Pumps | Status, flow, head, speed, efficiency, hydraulic and shaft power, NPSHa, NPSHr, NPSH margin; then the chart (`PumpChart`) of one pump at a time, picked from a list when there are several |
| Valves | Type, state, flow, head loss, pressure drop, K open, K effective, Cv effective, setpoint, setpoint met |
| Relief valves | Only when the solve has relief valves (§4.17): state (closed, partial lift, full lift; a valve the case as solved has locked closed reads "Closed (locked)", since it stays closed at any Δp ÷ set), flow (+ inlet → outlet), capacity (the flow at full lift for this case's fluid), flow ÷ capacity, inlet pressure (gauge), Δp ÷ set (the total-pressure difference over the set), lift, back pressure (gauge), static pressure drop and head loss; "—" for a null value. A valve with no result (a side closed off or on an undetermined level) is listed from its `RELIEF_VALVE_CLOSED` flag as "Closed (no result)". A note says what Δp ÷ set and the capacity are (above 100 % an active valve relieves; a valve locked closed stays closed), that partial lift is a convention and flagged, and why a valve can have no result |
| Equipment | Only when the solve has equipment (§4.14): flow (+ inlet → outlet), flow ÷ rated flow ("—" for a Cv or Kv rating), pressure loss (ρg × head loss), head loss, static pressure drop; differences within the solver's head tolerance read "≈ 0". A note says what the loss and the static drop are, when they are equal, and which columns change sign with the flow |
| Orifices | Only when the solve has orifice plates (§4.16): flow (+ inlet → outlet), permanent loss (ISO 5167-2's, ρg × head loss), differential pressure at the taps ("—" without taps), β, C (the one that sets the loss) and where it came from (ISO 5167-2, held below ISO's lowest Reynolds number, entered, or entered and moved to D and D/2 tappings), the inlet pipe's Re, the vena contracta pressure (gauge; "—" at zero flow and where the pressure level is undetermined), static pressure drop and head loss; differences within the solver's head tolerance read "≈ 0". A note says what the permanent loss, the reading and the static drop are, and which columns change sign with the flow |
| Branches | Tee and wye flow pattern, port flows, K per path, the velocity K is on, path losses, correlation |
| Boundaries | Reservoirs, reference nodes and plugs: EGL, outflow into the network, per port |
| Assigned flows | Per assigned-flow node: direction (demand or supply), the assigned flow as entered, elevation, pressure (gauge), absolute pressure, HGL, with its flags (`BELOW_VAPOR_PRESSURE`) |
| Methods | `MethodsSummary` |

**Tables** (`ResultsTable`):

- one row per element, named in a sticky first column whose button opens the element's trace;
- unit labels under the headings, in the display units, and flags shown inline as badges (`FlagBadge`);
- 4 significant figures, and heads to at least 0.01 m (TSD §6.2);
- names from the current project; a connection's "From → To" from the project its results belong to (the project as sent once they are out of date), so that after a reversal made since the solve the name and the sign of its flow refer to the same ends (`resultsProject` in `utils/results.ts`); the trace's heading, the flags list and a scenario's pipe changes name a connection the same way, as its pipe numbers there are the solve's;
- each table scrolls inside its own box, and long tables render in chunks;
- each column heading sorts the table by the values shown in that column (numbers as numbers, text in natural order, a cell of several values by its largest): ascending, descending, then the table's own order, with `aria-sort` on the sorted column and an arrow beside it; rows without a value stay last and ties keep the table's order;
- **Flagged only** shows the rows with flags, offered when some rows have flags and some do not.

**`PumpChart`.** Chart.js, loaded only when a chart is shown. It draws the pump curve at the operating speed (solid inside the user's data, dashed where extrapolated), the system curve and the operating point, with axes in display units. A data table of the same points sits under the chart; it is the fallback when there is no canvas.
- **Panels** (proposal `pump-chart.md` §4). Below the head, on the same flow axis (one chart, stacked y-axes), a panel for each curve the API sent: efficiency (%), shaft power and NPSH (NPSHr, and NPSHa along the computed system curve from each point's `npshAvailable`), each with its duty value, and a dotted vertical line at the duty through them all. A duty outside the efficiency data is a hollow marker (the solver holds η there). Chips (toggle buttons, `aria-pressed`) show or hide each panel; the hidden ones are remembered in this browser (`localStorage`), never in the project. **Read at flow** (a slider, or the pointer over the chart) draws a vertical line and reads every line shown at that flow, as drawn (linear between the API's samples); it starts at the duty and Escape returns there. Notes under the chart say what the panels show and where they stop: plain-affinity efficiency at another speed, the held efficiency, the largest shaft power over the data (not a non-overloading rating), and the flow where NPSHa falls below NPSHr, read from the drawn lines. The data table adds the efficiency, power and NPSHr curves and an NPSHa column. The image draws the same panels, its plot 150 px taller per panel. No design-practice band (POR, AOR, NPSH margin ratio) or proximity to the BEP is drawn (GOALS §4.6).
- **Curve facts** (proposal `pump-chart.md` §6, slice 2; from `PumpResult`). The best efficiency point, a cross labelled "BEP" on the head panel (and on the efficiency panel), shown by default as a property of the curve (owner's decision 2026-10-26): the duty is not judged against it. The shutoff head, a dash at zero flow (and, when the head points start above zero flow, the start tangent down to it, dashed as the solver extrapolates). Where the head rises with flow, the pump curve underlaid in amber. For a speed-controlled pump, its speed range (a **Speed range** chip, on by default and remembered with the panels): the head curve at its minimum and maximum speeds and the lines of constant efficiency through the BEP and at up to three multiples of 5 % below it (dotted, labelled at the maximum speed; a label that would overlap another is left out). Each fact has a sentence under the chart, in the image too, and its curves a table under it.

- **System curve on demand** (D10). Showing a pump's chart requests its curve, `POST /api/v1/system-curve` with the project exactly as it was solved (`ProjectStore.solvedProject`, never a newer, edited one) and the pump id. The store caches each curve with its solve, sends one request at a time (the server runs one solve per client at a time), drops the cache when a new solve's results arrive, and aborts requests in flight when a solve starts. A curve is only shown with the solve it was computed for.
- **States, shown as they are.** While the curve is computed, the chart says so (`aria-busy`) and offers **Cancel** ("Cancel the system curve", PRD §4.2), which aborts that pump's request only. A failure shows the server's message with **Try again**; a request cancelled by the user or by a newer solve says which and offers to compute it. The buttons are described by the state message; if Cancel has the focus when it goes, the button that replaces it takes it, else the chart, and if that button has the focus when the curve is computed again, Cancel takes it, else the chart. A point without a head (`head: null`: no steady state carries its flow, its head is undetermined, its solve did not converge or it was not computed) is a gap in the line, counted under the chart as having no head, and its row in the data table says why ("Why no head"): told from the point's `reason` and the ids and numbers that come with it (§4.10) with element names, each element's rule chosen by its kind in the project as solved, and values in the display units (`utils/system-curve-text.ts`), with the API's sentence under a closed **Details**; a point whose reason is null or unknown, or whose data does not fit its code, shows the API's sentence. With no point that has a head, no line is drawn and the chart says why.

**`TraceView`** shows how one element's results were obtained (GOALS §4.2). On wide screens it is a side panel over the results, which are inert underneath; on narrow ones it is a bottom-sheet dialog. A connection is headed as its results were solved (`resultsProject`), so its heading names the ends its values refer to. It shows:

- whether the values are current and a solution at all;
- the element's flags, plus network-wide physically invalid flags;
- its result rows;
- the solver's trace (§4.10): inputs with their source badge (User, Default, Library, Computed); equations; correlations and data sources with citations; intermediate values in display units, with the SI value as reported; and notes.

**Show in Build** points the navigator at the element. A deleted element is labelled as such.

**`MethodsSummary`** shows the solve's methods and assumptions (`trace.methods`): sections with items and references, assumptions, and library versions. It reads well on screen and in print. **Copy as text** gives plain text for a report: a heading, the project, the method version, when it was solved, and whether it converged or is out of date. Without clipboard access the text is shown selected.

**Scenarios** (PRD §3.8, CLAUDE.md D15). A project with scenarios gets a case chip in the pane's header ("Base case" or the scenario's name) and the status line names the case ("Last solve of Winter: converged"). Two tabs switch between the active case's results and **Compare cases** (`CompareView`). Every result names its case:

- **`ScenarioCard`**, at the top of a scenario's results: its name, id and description, the changes the server applied (`SolveResponse.scenario`, with base values, in display units, each linking to its element's trace) and those it ignored with the server's reason; for the base case, one line saying it is the network without scenario changes. Each value's field and unit are those of the project as it was solved (a control valve's setpoint is a pressure or a flow by its type then), so a later base edit never relabels the record shown.
- Rows of elements the scenario changed say "changed in this scenario", in every table (Pumps and Links included); the trace view has a case chip and a **Changed by this scenario** block from the response, above the server's notes (whose first note states the change; a pipe's change names its pipe, "Pipe 2 length"); the methods summary shows the server's Scenario section first, and its copied text adds "Case: …".
- A scenario's invalid value (a 400 located at `scenarios.{s}.overrides.{j}`) is shown with the change that set it, with Show and Reset to base; a topology issue on an element a change targets says "Set by this scenario".
- **`CompareView`**: chosen results of every case, the base first, with each scenario's difference from the base under its value (relative only for flow, velocity, pump head, head loss, an equipment item's pressure loss, an orifice plate's flow, permanent loss and differential pressure, a relief valve's flow, power and speed; no tolerance snapping; "Same" only where the values display identically). Each column header gives that case's status and switches to it (the focus goes to its tab); a case that did not converge, was not solved, failed or was not reached by a stopped run shows no values, and values out of date are tinted. A connection's row is named by its ends now, so each case's flow, head loss and largest velocity are read on the connection as it is now (`compareValue`, through `linkReading` in `utils/results.ts`): a case solved before a reversal gives its flow and head loss with the other sign ("Reversed since solved"), one solved before an end moved gives no value where it cannot place one ("Ends changed since solved"), and one solved before the connection's pipes changed gives no largest velocity, nor a flow or head loss when no pipe of it was solved in it or one was solved in another connection ("Pipes changed since solved"). The notice above the table counts the cases Solve all would solve, and names apart those whose solve failed with an error of their own to fix first. A row header opens its element's trace in the active case, and says so and does nothing while that case has no results. Default rows come from the stored project's scenarios (pumps, then each relief valve's flow, state and inlet pressure, then changed elements, an orifice plate's flow and permanent loss among them, assigned flows, the extremes; at most 40, so the limit cuts changed elements first), and `CompareRowsDialog` adds, removes and orders rows. A table on a pane at least 28 rem wide, one card per row below (phones). The rows are page state.
- **`PumpChart`** draws the active case as before and the other solved cases (six cases at most, the active one included) in slate with their own hollow markers and labels: their operating points and their pump curves at another speed by default, their system curves only on request ("Also show the other cases' system curves"), one request at a time with Cancel, over the active curve's flow range, for the cases that are other than the one shown (after a case switch too). Its data table adds the operating points by case.

**Goal seek** (PRD §3.9, CLAUDE.md D16; `workspace/GoalSeekDialog.svelte` and `workspace/goal-seek/`). A **Goal seek** button at the right of the Results pane's header (icon only below 24 rem) and **Use in goal seek** on a trace's "Result values" heading (the element preselected; on phones the trace sheet closes first) open a dialog: two columns from 1024 px (setup left, the result right and sticky), one below, a bottom sheet on phones. It runs on the case shown and names it; its fields are page state, never locked in a scenario.

- **Results to reach** (goal cards: the element and result, Target, Tolerance with the published minimum, a hint with the last solve's value, the sign convention and the default tolerance) and **Inputs to change** (variable cards: the value now, From and To in display units within the field's bounds and each other, default bounds pre-filled), each with an inline New form; choices come from `x-goal-variables` and `x-goal-quantities`, and "(already a goal)" / "(already a variable)" from `x-goal-seek-rules`. A row whose element was deleted, or whose value no longer applies, lapses and blocks Run; while a row names an element, no new element takes its id.
- **Run** is unavailable with its reason until the setup is complete. While a goal seek runs, every Solve, Solve all and Solve now control is unavailable with the reason, the header's Cancel becomes "Cancel goal seek", and the dialog may be closed (a notice gives the outcome).
- **The result** (`GoalSeekResult`): a banner in words and an icon per outcome (met, not reachable, jump, unsolved crossing, no progress, stopped by the cap or the budget, no usable trial, request errors, cancelled), the values found (6 significant digits, the exact SI value in the report), the results reached (reached, target, off by, tolerance, met), the notes worded from their codes, the physically invalid flags at the values found, the trial solves (a table, tab-separated in the report), the methods section and **Copy report**. **Apply to base case** / **Apply to scenario** and **Apply as new scenario** write the exact values as one undo step and solve the case; a scenario run is never applied to the base. A result goes out of date when its case's key changes, and Apply is then unavailable.

**Export** (PRD §3.2.3, CLAUDE.md D17; `components/results/ExportDialog.svelte`, `utils/export/`). An **Export** button left of Goal seek in the Results pane's header (labelled from a 30 rem header, a container query; icon-only, 44 px, below) is shown when there is something to export: the case shown has results on screen, or on Compare cases any case has a response. It is unavailable, with the reason, while a calculation request is in flight (`store.calculating`). Its dialog is a lazily loaded chunk (`utils/export/load.ts`, preloaded at idle when the button first renders; a failed load says to reload the page). It offers Cases (with scenarios: the case shown, or All cases, the default on Compare cases), Format (Excel workbook, the default, or CSV files in one zip), Units (display or SI base units) and Include the project link, and lists the warnings, the contents with row counts, what is left out and the file name, from the same function that makes the file (`buildExport`, which builds no cells). Download, in the dialog's footer and so always in view, has the focus, so Enter, Enter gives the default workbook; a build yields to the page every 500 rows or 64 KiB, shows progress with Cancel after 300 ms, and stops on Cancel, Close or Esc. The choices are page state, reset when another project loads.

- **One rule decides values** (Compare's, `caseResponse`, then convergence): a converged response gives every table, labelled in About, every caption and every row when out of date (with the names, structure and link of the project as solved); a response that did not converge gives its About block, flags, scenario changes and methods only; a failed or not-reached case's earlier response is never used, even when revealed on screen.
- **The file**: About first (the traceability record), Flags, Compare cases (all cases), the element tables one value per cell (pipes, fittings, branch ports and boundary ports as child tables; Equipment, when the case has some, also gives the rating each solve used, Orifice plates, when it has some, the bore and pipe bore each solve used and the coefficients' sources, and Relief valves, when it has some, after Valves, the set, overpressure and capacity each solve used, which the screen's tables leave to the form), pump curves and the system curves already computed, Scenario changes as the server applied them, the goal seek report, Methods and, for one case, the Trace. Every row starts with its case (with scenarios), its solve time and its state. Branch K is always on the combined-flow velocity, as the API reports it.
- **Download image** under each pump chart: the chart drawn again from the screen's own configuration (`utils/pump-chart-config.ts`, in the chart's chunk) at 1600 px wide on white, with a header (pump, case, project, solve time, methods version, an out-of-date line) and a footer (the figure's notes, the disclaimer, the app). It is unavailable, with the reason, while the chart is drawn or a system curve is computed, for a solve that did not converge, for the earlier results shown after a failed solve, and while a calculation runs. The other cases on the chart follow Compare's rule too: a failed or not-reached case is not drawn.
- Files are saved through a Blob URL and an `<a download>` click, revoked after 60 s; the app says "your browser saves it", never "saved".

**Footer** (`SiteFooter`): the disclaimer (GOALS §4.8), the copyright notice, About and privacy, the license (AGPL-3.0-or-later) and the source code, both at the commit the build was made from, the calculation server's source code (`<API>/source`, which redirects to the commit the API runs), and the third-party licenses (TSD §11.1).

**Design checks** (CLAUDE.md D19, §4.15; `components/results/ChecksView.svelte`, `utils/design-checks.ts`). When the solve has check results, a **Checks** view follows Summary: not met, then met, then not evaluated, each naming its element (a link to its results and trace; a connection as solved, as flags name it), its value against its limits in display units, built from the result's numbers (a value that rounds to its limit's text gets more digits, up to 17, and one a unit conversion still makes read as its limit is said to differ "by round-off", so a failure never reads as equal to its limit), its limits' source ("your values", a preset's name, the pump curve's manufacturer data) and the server's message under Details; the presets' citations are listed once below. The Summary shows a **Design checks** card: the counts, the first three not met, and All checks. Checks never mark the Results tab and never change a value. On the pump chart, behind a "Design checks" chip (remembered with the others), the limits as solved (`ProjectStore.solvedProject`): the preferred operating region shaded on the head panel (fractions × Q_BEP at the running speed), the allowable region shaded grey and the larger minimum flow as a dash-dot line through every panel (the curve's manufacturer data × speed), the NPSHa the NPSH margin check requires, max(NPSHr + margin, ratio × NPSHr), dotted along NPSHr, and the motor's rating dashed across the power panel to the chart's largest flow; each in a note under the chart and in the image's footer, only where drawn with the panels shown. Their legend entries hide them, as any dataset's do. The export has a Design checks sheet after Flags (TSD §8.3).

#### 3.1.4 State Manager

**Purpose:** Single source of truth for application state (`state/`, Svelte 5 runes classes provided through context).

**`ProjectStore`** (`project.svelte.ts`):

- **The project.** It holds the port-graph project (SI values). The project is replaced, never mutated, and each stored project is deep-frozen.
- **Changes.** Every change goes through `update(change, label)`. It is applied to a copy and must pass the schema and port-graph checks (`validate.ts`). An invalid change is refused, leaving the project unchanged, so every link the app writes opens again. A change that changes nothing adds no undo step, and `metadata.modified` is updated on each change.
- **Undo and redo** keep up to 100 steps, each with a label, in page memory only. A burst of edits to one field can merge into one step.
- **URL.** The project is written to the URL fragment after a 300 ms debounce, and flushed before sharing and leaving (§5.2). The store keeps the encoded project, the link length and the 8,000-character warning.
- **Results.** It holds the latest solve response, `stale` (by a hydraulic fingerprint of the project without display units, names, metadata or method version), `solving`, `cancelled` and a typed error: topology, validation or network. A newer solve supersedes an older one. A failed solve keeps the previous response, marked stale only if the project changed. `cancelSolve()` aborts the request in flight (the server stops a solve whose client has gone, D10), drops an answer that still arrives and sets `cancelled` (cleared when a solve starts), keeping the response and error shown before with their staleness; a superseded solve, a load, clearing the results and leaving the page abort the request in flight too.
- **System curves.** `solvedProject` is the project as sent for the shown response. `loadSystemCurve(pumpId)` fetches a pump's curve for it (one request at a time) into `systemCurves` (loading, ready, error or cancelled per pump, a cancelled one recording whether a solve or the user cancelled it); `systemCurve(response, pumpId)` returns one only for the response whose results are shown. A new response, a load or clearing the results drops them; a solve starting cancels the requests in flight; `cancelSystemCurve(pumpId)` aborts one pump's request, leaving the others queued.
- **Method version.** After a solve that is current, the project records the solve's `methodVersion` (GOALS §4.3) without an undo step. The version the link was opened with is kept for `MethodVersionNotice`.
- **Scenarios** (PRD §3.8, CLAUDE.md D15). `project` holds the base case and its scenarios; `activeCase` (null: the base) is the case shown, page state that is neither an undo step nor in the link (a link opens on the base case). Results, errors, staleness, `solvedProject` and system curves are kept per case (`results`, `solvedProject` and `systemCurves` read the active case's; `resultsFor(caseId)` any case's). A case's staleness key is the base's hydraulic fingerprint plus that scenario's canonical overrides (`utils/scenarios.ts` `caseKey`): a base edit makes every case out of date, an edit in a scenario only that scenario, a rename none. A scenario's solve sends the whole project with its `scenarioId`. `solveAll()` solves the cases whose results are missing, out of date, cancelled or failed with a network error, the base first, then the scenarios in order, one request at a time from the project as it was when it started; a topology, validation or fluid error stays with its case and the run goes on, a network error stops it (the cases not reached say so, and Solve all resumes with them), and `cancelSolve()` stops it. A solve goes on after a case switch: `solvingCase` names the case in flight, whichever is shown, so the header keeps its spinner and Cancel ("Cancel solving Winter") and the other Solve buttons wait; `casesWithErrors()` lists the cases Solve all skips for an error of their own. A `load()` tells the workspace (`onLoad`), which resets its page state (the trace open, Compare cases and its rows, the manager, Settings). Each undo entry records the case it was made in, and undo and redo show that case again. A base edit runs through `carryChanges` (`utils/scenarios.ts`): a pipe change follows its pipe object through joins, reversals and insertions (`utils/identity.ts`; the store records its copy of the project for every edit as the same pipes, so Build's results follow them too, `linkReading`), a removed pipe takes its changes with it, a deleted element's changes are kept as orphaned, and a valve changed between a pressure valve (PRV, PSV) and an FCV loses its setpoint changes; the result's notes say so. New ids never re-use an id a change targets (`factory.ts` `usedIds`).
- **Goal seek** (PRD §3.9, CLAUDE.md D16). `goalSeek` holds the page's one goal seek (running, cancelled with the result before it, done or failed, with the request and project as sent and the case's key); `runGoalSeek(request, caseId)` posts it, `cancelGoalSeek()` (also called by `cancelSolve()`) aborts it and drops a late answer, and `markGoalSeekApplied` records where its values went. `calculating` (`'solve' | 'solveAll' | 'goalSeek' | null`) is read by every control that starts a request: `solve()` and `solveAll()` send nothing while a goal seek runs, `runGoalSeek()` nothing while a solve or Solve all runs, and only Cancel, `load()` and `dispose()` stop one in flight; system curves wait for it, and one in flight is cancelled when it starts. Its staleness is recomputed on every project change, whether or not any case has results. It never changes the project.

**`Workspace`** (`workspace.svelte.ts`) joins the store, the `LibraryStore`, the `NavigatorStore`, the visible pane, notices and the element open in the trace view. It offers the graph-edit actions (TSD §8.1). Its `project` is the project of the case shown: the base, or the base with the active scenario's changes (`caseProject`), so every form shows and edits that case's values, while names, display units and the navigator read the stored base. In a scenario, `edit()` diffs the edited case against the allow-list (`x-override-fields`): allowed values become the scenario's changes (a value equal to the base's removes its change), names, the project name and description and display units go to the base, and any other difference (topology, a locked value) refuses the whole edit; it is one undo step. Fields are locked by default in a scenario (`ui/field-mode.ts`: read-only and focusable, "Same in every scenario") unless they declare a scenario value (`change`, which draws "Changed", the base value and Reset) or a shared label. Results tables are rebuilt only when the solve, the display units or the labels they use (names, kinds, ports, connection ends) change, not on every edit.

**`LibraryStore`** (`library.svelte.ts`) holds the API's reference data: pipe materials, schedules and sizes and fitting types (`GET /api/v1/library`), built-in fluids and their ranges (`GET /api/v1/fluids`), and the method-version changelog. It loads them once per page. Hydraulic data is never invented in the browser: when the API cannot be reached these stay empty, and the UI offers what needs no data (custom pipes, custom fluids, fittings by id).

**API client** (`api/client.ts`):

- **Endpoints.** `solve` (with `includeSystemCurve: false` unless asked; `scenarioId` in the body for a scenario only, so a base request is the request without scenarios), `systemCurve` (likewise), `goalSeek` (likewise; a 404 `NOT_FOUND` becomes a `NotFoundError`, a `ValidationError` that keeps its issues), `getLibrary`, `getFluids`, `fluidProperties` (`POST /api/v1/fluids/properties` with a `FluidDefinition`) and `methodVersions` (§5.1).
- **Requests.** It sends only what each request needs, with `credentials: 'omit'`, `referrerPolicy: 'no-referrer'` and a 60 s timeout (kept when the caller also passes an abort signal). Project data, the fluid included, travels only in request bodies: no URL carries a project value. Error responses become typed errors: `TopologyError` (422 `TOPOLOGY_ERROR`), `ValidationError` (the other 4xx envelopes: the request is about the project) and `NetworkError` (no answer, a timeout, or a 429 or 5xx, with the server's message when it sent the envelope, e.g. `SERVER_BUSY` while it is still solving a request just cancelled).
- **No other traffic.** No other network requests are made: no analytics, cookies, web fonts or third-party assets. The pages set `<meta name="referrer" content="no-referrer">`.

**Units.** Values are converted between SI and the display units only at input (`NumberField`) and display (formatters), TSD §6.

**Storage.** Nothing is kept in browser storage. History is the undo stack of the open page plus the links the user keeps.

Later: sync with the server for accounts and version history.

#### 3.1.5 Sharing

- **Share** (`workspace/ShareButton.svelte`) first writes any pending URL change, then copies the full link (the page's origin + `/p#<encoded>`) to the clipboard. Its dialog shows the link selected for copying by hand when the clipboard is unavailable, the link's length in characters, and a warning when it exceeds 8,000 characters. It also explains that the project is in the part after `#`, which browsers do not send to any server, and that edits make a new link while this one keeps opening this version. For a project with scenarios it adds that the link holds the base case and its scenarios and opens on the base case (the active case is not in the link), naming the scenario being viewed.
- **Link errors** (`workspace/LinkErrorView.svelte`): a link that cannot be opened shows why (damaged, newer version, or not a valid project, with the problems listed) and what to do. The options are to go back to the open project if there is one, to start a new project, or to go home.

### 3.2 Backend Services

The server is stateless: every request carries the project it needs, and nothing is persisted.

#### 3.2.1 Solver Service

**Purpose:** Perform hydraulic network analysis.

**Endpoints:**

```
POST /api/v1/solve
  Request: Project (port graph, SI), optional scenario id
  Response: SolvedState (flows, pressures, operating points), the scenario applied (or null)

POST /api/v1/system-curve
  Request: Project + pump id + flow range, optional scenario id
  Response: SystemCurve (flow/head pairs: the pump replaced by each fixed flow, §4.10), the
            scenario applied (or null)

POST /api/v1/goal-seek
  Request: Project + 1-4 variables + as many goals (§4.13), optional scenario id
  Response: GoalSeekResult (values found, goals, every evaluation, notes, methods) + SolvedState
            at the values found (or null), the scenario applied (or null)
```

`/solve`, `/system-curve` and `/goal-seek` take an optional scenario id (`scenarioId`, §4.12); the server applies that scenario's overrides to the base before building the network (`services/scenarios.py`, TSD §5.7), so the solver only ever sees a plain project. A request without one is solved exactly as a project without scenarios. Solving all scenarios is one independent request per case; there is no batch endpoint. A goal seek is one request of many full solves (`services/goal_seek.py`, TSD §5.7), each `solve_project` of the case with the variables written on top; the solver itself is unchanged.

**Implementation:** one Global Gradient Algorithm (Todini–Pilati) solver for every topology — the same core method EPANET uses — implemented in Python with Darcy–Weisbach/Colebrook friction from the `fluids` library. See TSD §5. It adds what EPANET lacks:

- Flow-split-dependent K-factors at tees and wyes (outer iteration)
- Real fluid density, viscosity and vapor pressure
- Check, stop-check, PRV, PSV and FCV as components with status logic
- NPSH available at every pump suction
- Speed-controlled (VFD) pumps holding a flow setpoint (§4.8, CLAUDE.md D11)
- Equipment rated by a datasheet pressure drop at a flow, with its fluid's density, or by a Cv or Kv (§4.14, CLAUDE.md D18)
- Orifice plates with ISO 5167-2's Reynolds-dependent discharge coefficient and permanent pressure loss, a meter's reading at its taps and a flashing check at the vena contracta (§4.16, CLAUDE.md D20)
- Liquid pressure relief valves: closed below a set pressure difference, the lift rising linearly (a convention, flagged) to API 520's liquid capacity at full lift, with the check valve's status rule on the set (§4.17, CLAUDE.md D21)
- Later: VFD pressure and differential-pressure control, balanced-bellows and pilot relief valves, gas relief, non-ideal reference nodes

Preconditions checked before solving (topology errors): at least one fixed-pressure boundary (reservoir or ideal reference node) per connected sub-network, where assigned-flow nodes do not count; every port connected or explicitly plugged; no connection between incompatible ports; a speed-controlled pump's curve gives one speed per head (`CONTROLLED_PUMP_CURVE`) and its setpoint is one some speed up to its maximum can hold (`CONTROLLED_PUMP_SETPOINT`, §4.8); an equipment item's rating gives a finite, positive loss coefficient (`EQUIPMENT_RATING_OUT_OF_RANGE`, §4.14); an orifice plate's bore is smaller than its inlet pipe's and its discharge coefficient cannot exceed 1 at any flow (`ORIFICE_OUT_OF_RANGE`, §4.16); a relief valve's law is representable in floating point, and its set is at least ASME VIII's 15 psi where its overpressure is ASME's default (`RELIEF_VALVE_OUT_OF_RANGE`, §4.17).

WNTR/EPANET is used only in the test suite, as a reference for water-only networks.

#### 3.2.2 Fluid Property Service

**Purpose:** Provide fluid properties for calculations.

**Endpoints:**

```
GET /api/v1/fluids
  Response: List of available fluids

POST /api/v1/fluids/properties
  Request: FluidDefinition (built-in at its state, with overrides, or custom), SI
  Response: FluidProperties as the solver will use them (the web app's request)

GET /api/v1/fluids/{fluid_id}/properties?temperature={T_K}
  Response: FluidProperties (density, viscosity, vapor_pressure), SI; for API users (the
  query string can appear in intermediaries' logs)

POST /api/v1/fluids/custom
  Request: CustomFluidDefinition (SI)
  Response: FluidProperties (validated)
```

**Data Sources:**

- Built-in library (water, ethylene glycol, propylene glycol; fuels Later). The property source is chosen per fluid and cited in the data file (TSD §4.6).
- User-defined fluids (stored in project state)

#### 3.2.3 Version Control Service (Later)

**Purpose:** Git-like versioning for projects, once accounts and storage exist.

**Operations:**
| Operation | Description |
|-----------|-------------|
| `commit` | Save current state as new version |
| `branch` | Create named branch from current state |
| `checkout` | Load specific version or branch |
| `merge` | Combine two branches |
| `history` | List all versions with metadata |

In v1, each edited state is simply a new link (PRD §4.4–4.5); there is no server-side history.

---

## 4. Data Models

**Source of truth:** the Pydantic models in `apps/api/src/opensolve_pipe/models/`. The frontend types in `apps/web/src/lib/api/schema.d.ts` are generated from the OpenAPI schema (`pnpm gen:types`); never hand-write duplicates. The TypeScript below is a readable summary.

**Units:** every numeric field is stored in SI — m, m³/s, Pa, K, kg/m³, Pa·s, m²/s. Pressures are stored as **gauge** Pa; absolute pressure is derived using the project's atmospheric pressure. Elevations are measured from the project datum. The frontend converts to and from the user's display units; the backend never sees display units. The one exception is a valve's `FlowCoefficient` (§4.9).

Models are plain JSON-serializable data (no methods, no `Map`s), because they travel in URLs and API requests. JSON is camelCase; unknown fields are rejected. Identifiers match `^[A-Za-z0-9_-]{1,64}$` (no `:`, so node keys `componentId:portId` are unambiguous).

### 4.1 Project Model

```typescript
interface Project {
  schemaVersion: 1;               // integer; bumped on every breaking change, see §5.2
  methodVersion: string;          // calculation-method version the project was last solved with
                                  // ('' if never); used to explain result changes (GOALS §4.3)
  id: string;
  metadata: ProjectMetadata;
  settings: ProjectSettings;
  fluid: FluidDefinition;
  components: Component[];
  connections: PipeConnection[];  // edges of the port graph
  pumpLibrary: PumpCurve[];
  scenarios?: Scenario[];         // at most 20, §4.12; omitted when there are none
}

interface ProjectMetadata {
  name: string;
  description?: string;
  created: string;                // ISO 8601
  modified: string;               // ISO 8601
}

interface ProjectSettings {
  units: UnitPreferences;         // display only (TSD §6)
  siteElevation: number;          // m above sea level, -500..9000
  atmosphericPressure?: number;   // Pa absolute; overrides the standard-atmosphere value
  solverOptions: SolverOptions;
  designChecks?: DesignChecks;    // opt-in design checks (§4.15); omitted when none is on
}

interface SolverOptions {         // options that change results travel with the project
  frictionMethod: 'colebrook' | 'swamee_jain';  // swamee_jain = EPANET's approximation
  maxIterations: number;          // Newton iterations per network solve (default 100)
  tolerance: number;              // largest flow change / largest flow (default 1e-9)
}
```

Solved results are not part of `Project` and are not stored in the URL; they are recomputed by solving.

### 4.1.1 Fluid Definition

```typescript
type FluidDefinition = BuiltinFluid | CustomFluid;

interface BuiltinFluid {
  kind: 'builtin';
  fluidId: 'water' | 'ethylene_glycol' | 'propylene_glycol';
  temperature: number;            // K
  concentration?: number;         // glycol mass fraction 0–1 (glycols only)
  overrides?: { density?: number; dynamicViscosity?: number; vaporPressure?: number };
}

interface CustomFluid {
  kind: 'custom';
  name: string;
  temperature?: number;           // K, informational
  density: number;                // kg/m³
  dynamicViscosity: number;       // Pa·s
  vaporPressure?: number;         // Pa absolute; needed for NPSH available
}
```

Built-in properties come from CoolProp (TSD §4.6). Each resolved value records whether it came from the library or a user override.

### 4.2 Component Model

The component model uses a **port-based architecture**: each component has a defined set of connection ports, and pipe connections link ports between components.

```typescript
type Component =
  | Reservoir | IdealReferenceNode | AssignedFlow | Plug
  | TeeBranch | WyeBranch
  | Pump
  | IsolationValve | CheckValve | ControlValve
  | Equipment                      // heat exchanger side, coil, strainer, filter (§4.14)
  | Orifice                        // orifice plate: restriction orifice or flow meter (§4.16)
  | ReliefValve;                   // pressure relief valve, conventional, liquid service (§4.17)
  // Later: Tank, NonIdealReferenceNode, CrossBranch, ElbowBranch, Sprinkler,
  // UserDefinedElement, ThreeWayValve, other orifice plates, nozzles and venturis,
  // balanced-bellows and pilot relief valves

interface Port {
  id: string;                    // e.g., "suction", "discharge", "branch"
  nominalSize: number;           // m (NPS inches × 0.0254); default size for new connections
  direction: 'inlet' | 'outlet' | 'bidirectional';
  elevation?: number;            // m; inherits the component elevation if not set
}

interface BaseComponent {
  id: string;
  type: 'reservoir' | 'reference_node' | 'plug' | 'assigned_flow' | 'branch' | 'pump' | 'valve'
      | 'equipment' | 'orifice' | 'relief_valve';
  name: string;
  elevation: number;             // m above project datum
  ports: Port[];
}

interface PipeConnection {
  id: string;
  fromComponentId: string;
  fromPortId: string;
  toComponentId: string;
  toPortId: string;
  piping: PipingSegment;         // pipes and fittings in this connection
}

interface PipingSegment {
  pipes: PipeDefinition[];       // one or more pipe segments, in series, in order from → to
  fittings: Fitting[];           // inline fittings (elbows, reducers, entrances, inline valves)
}
```

The union is discriminated by `type`, refined by `branchType` for branches and `valveType` for valves. A port's effective elevation is `port.elevation ?? component.elevation`; this is a helper function, not a field. Positive flow in a `PipeConnection` runs from `from` to `to`. The solver uses the inner diameter of the connected pipe at a port, not the port's nominal size.

### 4.3 Pipe Definition and Fittings

```typescript
interface PipeDefinition {
  materialId: string;            // key into the pipe materials library, or 'custom'
  schedule?: string;             // library schedule, e.g. '40', '80', '10S', '40D1785'
  nominalSize?: number;          // m (NPS inches × 0.0254), resolved to an inner diameter
  innerDiameter?: number;        // m; required for 'custom', otherwise overrides the library
  length: number;                // m
  roughness?: number;            // m; required for 'custom', otherwise overrides the library
}

interface Fitting {
  type: FittingType;
  quantity: number;              // integer ≥ 1
  pipeIndex: number;             // pipe segment the fitting sits in (its velocity is the reference);
                                 // a reducer sits between pipeIndex and pipeIndex + 1
  kOverride?: number;            // user K (priority 1, §6.2); required for 'custom'
  angle?: number;                // degrees: bend angle, or a conical reducer's included angle
  radiusRatio?: number;          // r/D: bend radius, or rounded-entrance radius
  description?: string;
}

type FittingType =
  | 'elbow_90_lr' | 'elbow_90_sr' | 'elbow_45_lr' | 'elbow_45_sr'   // welded/flanged, r/D 1.5 or 1
  | 'elbow_90_threaded' | 'elbow_45_threaded' | 'bend'             // bend: angle + radiusRatio
  | 'entrance_sharp' | 'entrance_rounded' | 'entrance_projecting' | 'exit'
  | 'reducer_sudden' | 'reducer_conical'                           // contraction or expansion by flow direction
  | 'gate_valve' | 'ball_valve' | 'globe_valve' | 'butterfly_valve' | 'plug_valve'
  | 'swing_check_valve' | 'lift_check_valve'                       // inline: loss only, no check action
  | 'custom';
```

Each fitting type maps to exactly one cited correlation (TSD §4.5). The pipe materials library (TSD §4.1) holds dimensions and roughness with their sources.

### 4.4 Reference Node Model

Reference nodes define pressure boundary conditions for the hydraulic network.

```typescript
interface IdealReferenceNode extends BaseComponent {
  type: 'reference_node';
  referenceType: 'ideal';
  pressure: number;              // Pa gauge, fixed
  ports: [Port];                 // exactly one
}

// Later: NonIdealReferenceNode with pressureFlowCurve and maxFlow
```

An ideal reference node is modeled like a reservoir: a body of liquid at rest at the given gauge pressure at the port elevation, so its energy grade line is fixed at `z + p/(ρg)`. Velocity head develops in the connecting piping; add entrance or exit fittings to model the transition. The solver applies no entrance or exit loss of its own. The web app gives new piping at a reservoir the cited default (GOALS §4.1): a sharp-edged entrance where the piping leaves the reservoir in the expected flow direction (its `from` end), an exit where it arrives (its `to` end). Both are ordinary fittings, shown and removable in the piping, and piping at a reservoir without one says that no such loss is applied.

### 4.5 Branch Component Model

Branch components represent fittings where flow splits or combines.

```typescript
interface TeeBranch extends BaseComponent {
  type: 'branch';
  branchType: 'tee';
  lossModel: 'crane' | 'ideal';  // ideal: no fitting loss, as EPANET models junctions
  ports: [ {id: 'run_inlet'}, {id: 'run_outlet'}, {id: 'branch'} ];
}

interface WyeBranch extends BaseComponent {
  type: 'branch';
  branchType: 'wye';
  angle: number;                 // degrees between the angled leg and the run, 30–60 (the
                                 // Crane range); the leg leans toward outlet_1
  lossModel: 'crane' | 'ideal';
  ports: [ {id: 'inlet'}, {id: 'outlet_1'}, {id: 'outlet_2'} ];  // inlet–outlet_1: straight run;
                                                                 // outlet_2: angled leg
}
// Later: CrossBranch (4 ports), ElbowBranch
```

Whether flow is diverging or converging is a solver result, not an input; port names do not constrain flow direction. Losses follow TSD §5.4.

A wye's orientation does matter: its angled leg (`outlet_2`) leans toward `outlet_1`, so flow from `inlet` turns through `angle` into it. Crane's lateral data cover the combined flow through `inlet`, dividing into the run and the lateral or combining from them. With the combined flow through `outlet_1` and flow in the lateral, the lateral's flow turns through 180° − `angle`, outside the data: the solver evaluates K at `angle` and flags CORRELATION_OUT_OF_RANGE. Draw a wye with its inlet on the side the lateral leans away from.

### 4.6 Plug/Cap Model

```typescript
interface Plug extends BaseComponent {
  type: 'plug';
  ports: [Port & { id: 'port_1' }];
  // Zero-flow boundary: dead-end branches, future expansion points, closed connections.
}
```

### 4.7 Reservoir Model

```typescript
interface Reservoir extends BaseComponent {
  type: 'reservoir';
  liquidLevel: number;           // m above the component elevation
  surfacePressure: number;       // Pa gauge on the liquid surface (0 = open to atmosphere)
  ports: Port[];                 // one or more ports (user-defined)
}
// Later: Tank (variable level, extended-period analysis)
```

Every port of a reservoir sees the same energy grade line, `z + liquidLevel + surfacePressure/(ρg)`. A port above the liquid surface is flagged.

### 4.8 Pump Model

```typescript
interface Pump extends BaseComponent {
  type: 'pump';
  curveId: string;               // key into project.pumpLibrary
  speed: number;                 // fraction of the curve's rated speed, 0 < s ≤ 1; a
                                 // speed-controlled pump's maximum speed
  status: 'on' | 'off';          // off = closed; a running pump never passes reverse flow
  control?: PumpControl;         // speed control (VFD, CLAUDE.md D11); omitted = fixed speed
  ports: [ {id: 'suction'}, {id: 'discharge'} ];
  // Later: pressure and differential-pressure control modes, viscosityCorrection
}

interface PumpControl {
  mode: 'flow';                  // required; slices 2-3 add pressure modes
  setpoint: number;              // m³/s through the pump, suction -> discharge, 0 < Q ≤ 100
  minSpeed: number;              // lowest speed, 0 < minSpeed < speed (x-ordered-fields); no default
}

interface PumpCurve {
  id: string;
  name: string;
  manufacturer?: string;
  model?: string;
  points: FlowHeadPoint[];                    // ≥ 3 points, flows strictly increasing (m³/s, m)
  efficiencyCurve?: FlowEfficiencyPoint[];    // m³/s, fraction 0–1
  npshrCurve?: FlowNpshrPoint[];              // m³/s, m
  // Manufacturer data at rated speed, read only by the design checks (§4.15), never the solve:
  allowableOperatingRegion?: { flowMin: number; flowMax: number };  // m³/s, 0 ≤ flowMin < flowMax
  minimumContinuousStableFlow?: number;       // m³/s > 0
  minimumThermalFlow?: number;                // m³/s > 0
  motorRatedPower?: number;                   // W, (0, 1e8]
}
```

**Speed-controlled pump (flow setpoint, CLAUDE.md D11; design: `docs/proposals/vfd-pump-modes.md`).** The drive varies the speed s within [minSpeed, speed] to hold Q_set. While a speed in [s_lo, speed] can, the pump is a fixed-flow link in the network solve and s is the unique root of s² H₀(Q_set/s) = EGL_d − EGL_s on [s_lo, speed], where that head rises with speed (s_lo = max(minSpeed, Q_set/x_mono), TSD §5.4; it exceeds minSpeed only when Q_set/minSpeed lies beyond x_mono on the curve's end tangent, where head falls as speed rises, which no stable flow controller holds); above that band it runs as the fixed-speed pump at `speed`, below it at `minSpeed` (it keeps running), and at zero flow it closes and re-opens as the fixed-speed pump at `speed`. The rules are those of TSD §5 (A0–C1). A controlled pump's curve must have 2H₀(x) − xH₀′(x) > 0 for 0 ≤ x ≤ its largest point flow, so that the speed root is unique (one speed per head at a flow; on a drooping curve this does not make the operating state unique, TSD §5.4); otherwise the project has the topology issue `CONTROLLED_PUMP_CURVE` (422). On a curve that passes, a setpoint Q_set ≥ speed × x_mono (x_mono: twice the flow at which the curve's falling end tangent reaches zero head), at which the head s² H₀(Q_set/s) falls as the speed rises at every speed of the drive, so that no speed controls the flow, is the topology issue `CONTROLLED_PUMP_SETPOINT` (422), whose message gives the bound speed × x_mono. `minSpeed < speed` is a model rule (400), published as the `x-ordered-fields` extension. Results (§4.10): `PumpResult.speed` is the speed the pump runs at (solved, or the limit), its curve, range, efficiency η₀(Q/s), NPSHr and power are at that speed, and `PumpResult.control` = {mode, setpoint, state: 'active' | 'max_speed' | 'min_speed' | 'no_flow' | 'off', setpointAchieved} (null for a fixed-speed pump). At a limit or with no flow and off its setpoint by more than Qtol, the pump is flagged `PUMP_SETPOINT_NOT_MET` (info). A system curve replaces the viewed pump's control by the fixed flow; other controlled pumps that are on keep regulating; the default range uses `speed`.

### 4.9 Valve Models

```typescript
// Valve resistance exactly as the user entered it
interface FlowCoefficient {
  kind: 'K' | 'Cv' | 'Kv';       // K: dimensionless; Cv: US gpm at 1 psi; Kv: m³/h at 1 bar
  value: number;
}

interface IsolationValve extends BaseComponent {
  type: 'valve';
  valveType: 'gate' | 'ball' | 'butterfly' | 'globe';
  status: 'active' | 'isolated';             // isolated = closed
  resistance?: FlowCoefficient;              // at the actual opening; default: Crane full-open K
  ports: [ {id: 'inlet'}, {id: 'outlet'} ];
}

interface CheckValve extends BaseComponent {
  type: 'valve';
  valveType: 'check' | 'stop_check';
  status: 'active' | 'locked_open' | 'locked_closed';
  resistance?: FlowCoefficient;              // when open; default: Crane swing / globe stop-check K
  crackingPressure: number;                  // Pa, default 0
}

interface ControlValve extends BaseComponent {
  type: 'valve';
  valveType: 'prv' | 'psv' | 'fcv';  // Later: 'pdcv' (differential-pressure control)
  status: 'active' | 'failed_open' | 'failed_closed';
  setpoint: number;              // prv: static gauge Pa at the outlet port; psv: at the inlet port;
                                 // fcv: m³/s; Later, pdcv: Pa, inlet minus outlet static pressure
  resistance?: FlowCoefficient;  // fully open loss; default: ideal valve (no loss when wide open)
}
```

**Flow coefficients:** manufacturers publish valve capacity as Cv (US gpm at 1 psi ΔP) or Kv (m³/h at 1 bar ΔP), both defined for water. `FlowCoefficient` stores the value in the user's own convention — the one documented exception to SI storage, because Cv and Kv are defined quantities rather than units — and the solver converts it to a loss coefficient K at the inner diameter of the pipe connected to the valve inlet (TSD §5.3).

**v1 limits:** an isolation valve has no `position` field and a control valve has no Cv-vs-position curve, because no cited opening characteristic is available (GOALS §4.1); enter the resistance at the actual opening instead. Position-dependent models are Later. A check valve, when open, loses `Δp_crack/(ρg) + K·v²/(2g)`; it closes when the pressure difference falls below the cracking pressure or the flow would reverse.

### 4.10 Solved State

The solver's output (`models/results.py`; the OpenAPI schema is the contract, and the frontend types are generated from it). All values SI; pressures gauge unless the name says absolute; heads from the project datum. `egl` is the solver's nodal unknown (EGL = z + p/ρg + v²/2g) and `hgl = egl − v²/2g`, with v the velocity in the pipe connected at the port (0 at reservoir and reference-node ports).

```typescript
interface SolvedState {
  converged: boolean;              // false: every result map is empty (§8.2); trace and flags remain
  methodVersion: string;           // calculation-method version (GOALS §4.3)
  timestamp: string;               // ISO 8601, UTC
  fluid: FluidProperties;          // properties as used, with the source of each
  atmosphericPressure: number;     // Pa absolute, as used
  nodeResults: Record<string, NodeResult>;         // `${componentId}:${portId}`; ports with a head only
  linkResults: Record<string, LinkResult>;         // connection id (every connection)
  pumpResults: Record<string, PumpResult>;         // component id
  valveResults: Record<string, ValveResult>;       // component id
  equipmentResults: Record<string, EquipmentResult>; // component id; {} without equipment (§4.14)
  orificeResults: Record<string, OrificeResult>;     // component id; {} without orifice plates (§4.16)
  reliefValveResults: Record<string, ReliefValveResult>; // component id; {} without relief valves (§4.17)
  branchResults: Record<string, BranchResult>;     // tee / wye id
  boundaryResults: Record<string, BoundaryResult>; // reservoir, reference node, plug, assigned-flow node id
  flags: Flag[];
  designChecks: DesignCheckResult[]; // opt-in design checks (§4.15); [] without checks or not converged
  convergence: ConvergenceReport;  // iterations, largest residuals and where (value null when not finite: the iteration diverged), oscillating ids, message
  trace: Trace;                    // per-element trace + methods summary
}

interface NodeResult { componentId; portId; elevation; velocity; pressure; absolutePressure;
                       dynamicPressure; totalPressure; hgl; egl }
interface LinkResult { flow; velocity; headLoss /* EGL(from) − EGL(to) */; frictionHeadLoss;
                       fittingsHeadLoss; reynoldsNumber; frictionFactor; flowRegime;
                       segments: SegmentResult[]; fittings: FittingResult[] }  // top-level v, Re, f: first segment
interface SegmentResult { index; innerDiameter; length; roughness; velocity; reynoldsNumber;
                          frictionFactor; flowRegime: 'none' | 'laminar' | 'transitional' | 'turbulent'; headLoss }
interface FittingResult { index; type; quantity; k /* one fitting */; referenceDiameter; headLoss; source }
interface PumpResult { status: 'running' | 'off' | 'no_flow'; speed /* the speed it runs at: set, solved or limit */;
                       control: PumpControlResult | null /* null: fixed speed (§4.8) */; operatingFlow; operatingHead /* EGL rise */;
                       inCurveRange; hydraulicPower; efficiency | null; shaftPower | null;
                       npshAvailable | null; npshRequired | null; npshMargin | null; suctionAbsolutePressure | null;
                       curve: CurvePoint[] /* at speed */;
                       efficiencyCurve: {flow, efficiency}[] | null /* η₀(Q/s) over the efficiency points × s */;
                       npshrCurve: {flow, npshr}[] | null /* s² NPSHr₀(Q/s) over the NPSHr points × s */;
                       powerCurve: {flow, shaftPower}[] | null /* ρgQH/η where head and efficiency points both reach */;
                       bestEfficiencyPoint: {flow, efficiency, head, headExtrapolated} | null /* η₀'s largest value strictly inside its points, at speed */;
                       shutoffHead: {head, extrapolated} /* s² H₀(0) */;
                       risingHeadRanges: {flowMin, flowMax}[] /* dH/dQ > 0 within the head points, at speed */;
                       speedCurves: {limit: 'min' | 'max', speed, curve: CurvePoint[]}[] /* speed-controlled pumps */;
                       isoEfficiencyLines: {efficiency, best, ratedFlow, points: CurvePoint[]}[] /* likewise, with a BEP */;
                       systemCurve: CurvePoint[] | null }
interface PumpControlResult { mode: 'flow'; setpoint /* m³/s */;
                              state: 'active' | 'max_speed' | 'min_speed' | 'no_flow' | 'off'; setpointAchieved: boolean | null }
interface ValveResult { valveType; state: 'open' | 'closed' | 'active'; flow; headLoss; pressureDrop; kOpen;
                        referenceDiameter /* inlet pipe */; kEffective | null; cvEffective | null;
                        setpoint | null; setpointAchieved | null }
interface EquipmentResult { flow /* + inlet → outlet */; flowRatio | null /* Q/Q_r, signed; null: Cv or Kv */;
                            headLoss /* EGL(inlet) − EGL(outlet) */; pressureLoss /* ρg·headLoss */;
                            pressureDrop /* static, inlet − outlet, as a valve's */; rating /* as used */ }
interface OrificeResult { flow /* + inlet → outlet */; headLoss /* EGL(inlet) − EGL(outlet) */;
                          pressureLoss /* ρg·headLoss: ISO 5167-2's permanent pressure loss */;
                          pressureDrop /* static, inlet − outlet, as a valve's */;
                          differentialPressure | null /* a meter's reading at its taps, signed as the flow; null: no taps */;
                          venaContractaPressure | null /* gauge, at the outflow port's elevation; null: zero flow, floating */;
                          beta; pipeDiameter /* D, the inlet pipe's end segment */; boreDiameter /* d, as used */;
                          reynoldsNumber /* Re_D in the inlet pipe */; dischargeCoefficient /* C_L, at D and D/2 tappings */;
                          coefficientSource: 'iso_5167_2' | 'entered'; coefficientReynoldsNumber | null /* Re_eff */;
                          tapCoefficientRatio | null /* r, an entered C moved from corner or flange taps */;
                          lossCoefficient /* K on the inlet pipe's velocity */; taps | null;
                          meterDischargeCoefficient | null /* C_M, the C in the reading; null: no taps */ }
interface ReliefValveResult { state: 'closed' | 'partial_lift' | 'full_lift';
                              flow /* + inlet → outlet; within Qtol below 0 at its switch, closed */;
                              lift /* x, 0 to 1 */; headLoss /* EGL(inlet) − EGL(outlet) */;
                              totalPressureDifference /* Δp_t = ρg(headLoss − (z_in − z_out)), what the law reads */;
                              pressureDrop /* static, inlet − outlet, as a valve's */;
                              inletPressure | null; backPressure | null /* gauge; null: floating */;
                              setPressure /* Δp_s */; setRatio /* Δp_t/Δp_s */;
                              overpressure; overpressureSource: 'asme_default' | 'user';
                              fullLiftPressureDifference /* Δp_f */; fullLiftFlow /* Q_f */; flowRatio /* Q/Q_f */;
                              capacity /* as used: kind, letter?, area, dischargeCoefficient, overpressure?, coveringLetter? */;
                              reynoldsNumber | null /* API's, on the orifice; null: zero flow */ }
interface BranchResult { branchType; lossModel; pattern; combinedPortId | null;
                         portFlows /* positive into the component */; kFactors /* per path, on v_c */;
                         pathHeadLosses; referenceVelocity /* v_c */; correlation; inCorrelationRange }
interface BoundaryResult { type: 'reservoir' | 'reference_node' | 'plug' | 'assigned_flow'; egl;
                           outflow /* into the network; an assigned-flow node: −flow, as solved */; portOutflows }
```

Elements in a section closed off from every fixed-pressure boundary carry no flow and have no head: their ports are absent from `nodeResults`, and their pump, valve, equipment, orifice, relief valve, branch or boundary result is absent (flagged `ISOLATED_SECTION`).

A section that no fixed-pressure boundary reaches but that cannot sit at zero flow (a pump loop behind a closed valve) carries a determined flow at an undetermined pressure level: its connection, pump, valve, equipment, orifice, relief valve and branch results are reported (flows, head losses, pump head and power, an equipment item's, orifice plate's or relief valve's static pressure drop, a difference that does not depend on the section's level, an orifice plate's reading, and a relief valve's lift and total-pressure difference), its ports are absent from `nodeResults`, `PumpResult.npshAvailable` and `suctionAbsolutePressure` are null, an orifice plate's `venaContractaPressure` and a relief valve's `inletPressure` and `backPressure` are null, a PRV/PSV there has `setpointAchieved: null`, and an element between it and another head has no result (an active relief valve there raises `RELIEF_VALVE_CLOSED`, §4.17). It is flagged `UNDETERMINED_PRESSURE` (`details.componentIds`). Such a section can hold assigned-flow nodes only if their flows sum to zero; a part that no fixed-pressure boundary reaches and whose assigned flows do not balance has no steady state, so the solve is not converged (`NOT_CONVERGED`), its message naming the nodes with their flows and the elements closed around them (§4.11).

**System curve** (`PumpResult.systemCurve`, filled for every running pump when `SolveOptions.includeSystemCurve`): `systemCurvePoints` flows from 0 to 1.2 × the curve's largest flow × s; at each, the pump is replaced by that fixed flow, whatever its own speed control, and the network solved (other pumps keep running, other speed-controlled pumps keep regulating, valves follow their rules, an active relief valve starting each point open, §4.17); head = EGL(discharge) − EGL(suction). For a speed-controlled pump s is its `speed`, the maximum speed (§4.8). Every point whose flow passes with a determined head has that head (TSD §5.6); points without one are left out (`POST /system-curve` reports each with its reason, §5.1): no way through, no steady state that carries the flow, an undetermined head (a side of the pump on a free pressure level, or a control valve in series at its switch), or no convergence. The web app solves without it and fetches one pump's curve from `POST /system-curve` when its chart is shown (§3.1.3, D10).

**System-curve point** (`POST /system-curve`, `models/api.py`): each point says why it has no head twice, in words (`message`, with element ids and SI values) and as data (`reason` and the fields after it), built in `system_curve.py` from the same values, so the two always agree; a point with a head has `''`, null and empty lists.

```typescript
interface SystemCurvePoint {
  flow: number;                    // m³/s through the pump, suction → discharge
  head: number | null;             // EGL(discharge) − EGL(suction), m; null: see reason and message
  converged: boolean;              // true when the point has a head
  message: string;                 // why it has no head, in words ('' with a head)
  npshAvailable: number | null;    // m, NPSHa at the suction at this flow, as the solve's; null without a head,
                                   // a vapor pressure, or a determined suction pressure level
  reason: SystemCurveReason | null;
  componentIds: string[];          // the pumps and valves the message names, in its order (not_converged:
                                   // /solve's oscillatingComponents, maybe none; the message can name more)
  assignedFlowNodeIds: string[];   // beyond_limit, below_floor: the assigned-flow nodes counted, in id order
  limitFlow: number | null;        // m³/s. beyond_limit: the most the pump can pass (negative: it would
                                   // have to pass −limitFlow in reverse); below_floor: the least it must pass
  passedFlow: number | null;       // m³/s. beyond_limit, below_floor: what componentIds pass that way together
  openHead: number | null;         // m. valve_at_switch: the head across the pump with the valve fully open
  openHeadBound: 'lower' | 'upper' | null;  // valve_at_switch: any head at or above ('lower') or at or below it
  startsTried: ('solve' | 'previous_point' | 'initial' | 'initial_open')[];  // no_steady_state_found
}
type SystemCurveReason =
  | 'no_way_through'        // a side reaches no fixed head nor the other side through elements that can open
  | 'beyond_limit'          // every way from discharge back to suction passes componentIds (TSD §5.6)
  | 'below_floor'           // with the assigned flows, the pump must pass at least limitFlow
  | 'no_steady_state_found' // from every start the status rules close componentIds (maybe none)
  | 'free_level'            // a side carries flow but no fixed head reaches it
  | 'closed_off'            // componentIds (maybe none) close off a side; nothing fixes its pressure
  | 'valve_at_switch'       // the control valve componentIds[0] sits at its switch
  | 'not_converged'         // componentIds: the outer loop's oscillatingComponents (as /solve's), maybe none
  | 'not_computed';         // the request's time budget ran out first
```

Without assigned flows `passedFlow` equals `limitFlow`. For `not_converged`, `componentIds` are what `/solve` reports as `convergence.oscillatingComponents` for that solve: the controls and branches the outer loop names as oscillating, still changing or over-controlled, maybe none. Everything else the outer loop's message names is in the message only: the assigned-flow nodes of a part no fixed head reaches, with their flows (`assignedFlowNodeIds` stays empty), the elements closed around that part, and a wye in a flow pattern with no cited correlation. For `not_computed`, the budget is in the message only. `solve` (the network's own solve) appears only in a solve's own curves (`includeSystemCurve`), whose points the API does not return. The web app tells the reason with names and display units and keeps the message under Details (§3.1.3); a null or unknown reason, or data that does not fit its code, shows the message.

**Flags** (GOALS §4.6, on by default) — `Flag {code, severity, message, componentId, connectionId, portId, details}`. A message names a connection's pipes and fittings as the app numbers them, from 1 ("connection 'L1' pipe 2: …", "fitting 1 (bend)"); `details.segmentIndex` and `details.fittingIndex` are 0-based indexes into `piping.pipes` and `piping.fittings`. Each code has one severity:

| Severity | Codes |
|---|---|
| `invalid` (physically invalid) | `NOT_CONVERGED` (network-wide; `details.componentIds` names oscillating elements; `details.maxContinuityResidualAt` and `maxEnergyResidualAt` name the node and the link of the largest residual beyond its stop tolerance, and are absent where none is, TSD §5.2), `CAVITATION`, `BELOW_VAPOR_PRESSURE` (at a port; on a reservoir's surface; on an orifice plate at its vena contracta, `details.venaContractaAbsolutePressure`, §4.16; on a relief valve while it relieves, at its outlet, `details.backAbsolutePressure`, §4.17), `PUMP_FLOW_REVERSAL`, `UNSUPPORTED_FLOW_PATTERN`, `PORT_ABOVE_LIQUID_LEVEL` |
| `warning` (unreliable or incomplete) | `CORRELATION_OUT_OF_RANGE` (friction ranges, Crane K in laminar flow, tee/wye ranges, table limits; equipment in reverse flow, or with laminar flow in a connected pipe, §4.14; an orifice plate outside ISO 5167-2's bore, pipe, β or Reynolds-number range, with an outlet pipe of another bore, in reverse flow, or laminar with an entered C, `details.limit` naming which, §4.16; a relief valve relieving short of full lift, `limit: 'partial_lift'`, or with a viscous liquid, `limit: 'viscosity'`, §4.17), `PUMP_OUTSIDE_CURVE` (`details.curve`: head, efficiency or npshr), `TRANSITIONAL_FLOW`, `TEE_PATTERN_FALLBACK`, `UNDETERMINED_PRESSURE` (on the pump or FCV driving the flow; `details.componentIds`: the section), `NPSH_NOT_CHECKED` (a running pump with an NPSHr curve whose NPSH available cannot be computed because the fluid has no vapor pressure: cavitation is not checked) |
| `info` (state) | `NO_VAPOR_PRESSURE` (network-wide), `CHECK_VALVE_CLOSED`, `RELIEF_VALVE_OPEN` (a relief valve at full lift; `details`: flow, totalPressureDifference, setRatio, flowRatio), `RELIEF_VALVE_CLOSED` (an active relief valve closed with a closed-off or floating side, which has no result; `details`: side, section, setHead, setPressure, pressureLimit where the other side has a head, §4.17), `CONTROL_VALVE_SETPOINT_NOT_MET`, `PUMP_SETPOINT_NOT_MET` (a speed-controlled pump at a speed limit or with no flow, off its setpoint; `details`: state, setpoint, flow, speed, minSpeed, maxSpeed), `ISOLATED_SECTION` (`details.componentIds`) |

Every other flag names exactly one component (and port, where it applies) or one connection.

**Trace** (GOALS §4.2; `services/solver/trace.py`): `Trace {elements: Record<id, ElementTrace>, methods: MethodsSummary}`, with one `ElementTrace` for every component and every connection, converged or not:

```typescript
interface ElementTrace {
  elementId: string;
  elementType: 'pipe_connection' | 'reservoir' | 'reference_node' | 'plug' | 'assigned_flow' | 'tee'
             | 'wye' | 'pump' | 'isolation_valve' | 'check_valve' | 'control_valve' | 'equipment'
             | 'orifice' | 'relief_valve';
  inputs: { name; value: number | string | boolean | null; unit; source: 'user' | 'default' | 'library' | 'computed' }[];
  equations: string[];                         // plain text, every symbol defined
  correlations: { name; citation }[];          // e.g. the fluids call and Crane TP-410 (2009)
  dataSources: { name; citation }[];           // pipe standard, roughness source, CoolProp + reference, p_atm
  intermediates: { name; value: number; unit }[];  // values the solver produced (Re, f, K, v, ΔH, q, NPSHa terms…)
  notes: string[];                             // regime, state and the rule that set it, assumptions, flags
}
```

- **Sources.** `user`: entered (a field set to a value other than its default); `default`: a field holding its model default, whether left out or sent with that value, as the frontend sends every field (e.g. pump speed 1, fitting quantity 1, loss model 'crane'); `library`: pipe tables, correlations, CoolProp, standard constants; `computed`: derived from other inputs (ν = μ/ρ).
- **Units** are SI strings the frontend converts: `m`, `m²` (to the area unit, the square of the diameter unit: a pipe's or a relief valve's area), `m³/s`, `m/s`, `Pa(g)`, `Pa(a)`, `Pa (difference)`, `kg/m³`, `Pa·s`, `W`; `''` for dimensionless values; others (`m²/s`, `m/s²`, `°`, `K`, `US gpm/psi^0.5`, `m³/h/bar^0.5`, `s²/m⁵` for an equipment item's loss coefficient c, `Pa^1.5·s/m³` for a relief valve's band coefficient R and `s/m²` for its slope dh/dQ) are shown as reported. No trace value is a bare `Pa`.
- **Intermediates restate the results** (same numbers as the result fields) or follow from them by the listed equations (v = Q/A; NPSHa = (EGL_s − z_s) + (p_atm − p_vap)/ρg), so a trace never disagrees with the tables.
- **Numbering.** Pipes and fittings are numbered from 1, as in the app ("Pipe 2 Reynolds number Re", "Fitting 1 (reducer_sudden) position: between pipes 1 and 2"); so are pump-curve points ("Head curve point 4").
- **Content per element type.** Pipe connection: per segment material, schedule/NPS or custom, D and ε with their sources, L, A, v, Re, ε/D, f, regime note with the friction formula and its range, h_f; per fitting type, quantity, K with its fluids call and citation (or "user"), reference diameter, h_j; totals and the EGLs at both ends. Reservoir / reference node: boundary head equation and its inputs, outflow, port pressures, p_atm; the statement that no entrance or exit loss is applied at the boundary unless the connection has an entrance or exit fitting (with the web app's defaults at reservoirs: a sharp-edged entrance and an exit), then, per port, the entrance and exit fittings its connection's piping has. Plug: closed-end equations, EGL and pressure. Assigned-flow node: the flow as entered with its sign convention, elevations, the continuity equation at the port with the inflow and its residual (also on an undetermined pressure level), EGL, velocity, velocity head, HGL, static and absolute pressure, and a note that it is not a pressure boundary (§4.11). Tee / wye: loss model, angle, port pipe diameters, pattern, port flows, Q_c, q, β, K per path (Crane or Darby call), v_c, path losses, range / fallback notes. Pump: curve points, fit (PCHIP) and extrapolation, speed and affinity laws, operating point, shutoff head, efficiency and power, NPSHa terms (p_atm and its source, p_vap and its source, z_s, EGL_s, velocity head), NPSHr and margin, status reason, "no viscosity correction applied", the system curve when computed. Valves: resistance as entered (K, Cv, Kv with the ISA conversion) or the Crane default with its call, or the ideal control valve; D_ref; K; both port elevations, the velocities and static pressures at both ports (so Δp follows from the trace); cracking head (active check valves only: a locked valve's law has none); status reason (the user setting, or the EPANET 2.2 rule that holds the state written as the inequality that holds, with its solved values); control valves add the setpoint, H_set with its velocity head, hml, K_eff and Cv_eff. Equipment (§4.14): the rating as entered (source `user`), the port elevations and the connected pipes' bores; c with its equation (h_r = ΔP_r/(ρ_r g), c = h_r/Q_r²; or K from `Cv_to_K` / `Kv_to_K` at a 1 m bore, c = K/(2gA²), with its equivalent rated point ΔP₁ at Q₁ and ρ_w); Q, Q/Q_r, the velocities and Re in the connected pipes' end segments, the EGLs, the head loss as solved and by the law, ρgh, the density ratio, both static pressures and each term of the static-drop identity; notes on the rated drop's definition, the density ratio in words, the viscosity limit, and reverse or laminar flow with the inequality that set the flag. Orifice plate (§4.16): the bore (source `user`), the discharge coefficient (entered, `user`, with its definition: ISO 5167-2 eq. (1)'s C at the plate's taps, not α = C/√(1 − β⁴); or ISO 5167-2's, `default`), the taps (or none, `default`), D with its pipe source, the fluid, g and the port elevations; the equations (β, Re_D, eq. (4) as ISO writes it with L1 and L2′, the hold Re_eff = max(Re_D, Re_lo) with Re_lo's rule, the move C_L = C_e·r, K(C) in the cancellation-free form, h = K v\|v\|/2g, the reading, p_vc, the static pressure at each port and the static-drop identity); the correlations (ISO 5167-2:2003's Reader-Harris/Gallagher equation, its pressure-loss relation and eq. (1), through fluids); intermediates β, 1 − β, A, v, Re_D, Re_lo (and the taps'), Re_eff, (19000β/Re)^0.8, each term of eq. (4) at D and D/2 tappings and at the plate's taps, C_L, C_M, r, the jet ratio μ = C_L/√(1 − β⁴(1 − C_L²)) (≤ 1), K, h by the law and as solved, ρgh, Δp and Δϖ/Δp, both static pressures, p_vc gauge and absolute against p_v, and each term of the static-drop identity; and, marked not used, the K the meter's own C would give and Reader-Harris et al. 2019's C and K at L2′ = 0.125; notes on one loss per plate and the named departures, ε = 1, the plate and installation assumed to meet ISO 5167-2, d and D at flowing conditions, the recovered outlet pressure (about 6 D downstream), an entered C as entered and as moved, the vena contracta at the outflow port's elevation, the continuous Re_lo, and each flag's inequality. Relief valve (§4.17): the set (`user`) with its reading, the overpressure (ASME's `default`, with the 3 psi floor where it applies, or a certified one, `user`), the capacity (a letter's area from `data/api526_orifices.json` and Kd 0.65, `library`, labelled preliminary; an effective area with its covering letter, or a certified area and rated K, `user`), the status, ρ, μ, g, the port elevations and the inlet and outlet bores; the equations (Δp_t and its identity with the EGL drop, the lift, the full-lift equation and API's 11.78 form with its +6.09×10⁻⁵, h_set, the band cubic and its root, Δp_f, Q_f, the static pressure at each port and the static-drop identity); intermediates C, R, Q_f, Δp_t, x, setRatio, flowRatio, the slope, Re, the Kv API 520 10E would give (not applied), the head loss by the law (only while it relieves) and as solved, and, marked not used, the difference and flow by the static and the stagnation readings and, with a back pressure, the gauge-set overpressure that would put full lift at the in-situ relieving pressure; the inequality that set its state; notes on the conventional valve (back pressure adds to its opening pressure; it opens on the static difference, where a check valve's cracking pressure reads the EGL difference), the three named departures, what the certification does not bound, Kw = Kc = Kv = 1, no blowdown, liquid-full outlet piping, and each flag's inequality. Tee / wye and pump traces give their port elevations and port pressures too; a built-in fluid's temperature (and glycol mass fraction) is an input of every trace that uses its properties.
- **No result.** An element in a closed-off section, or every element of a solve that did not converge, keeps its inputs, equations and sources, with a note saying why it has no values. An element in a section with an undetermined pressure level (`UNDETERMINED_PRESSURE`) keeps its flows and head differences, with a note saying why its EGLs and pressures are missing.

**Methods summary** (`MethodsSummary {methodVersion, sections[{title, items, references}], assumptions, libraries}`; `services/solver/methods.py`): sections Network solution (GGA, Todini & Pilati 1988, tolerances, this solve's iterations; assigned-flow nodes, only when the project has one: nodal demands as EPANET's junction demands, the no-steady-state cases), Pipe friction, Minor losses, Branches, Pumps (PCHIP, affinity laws, no viscosity correction, system curves; with assigned-flow nodes, the cut's bounds that count them, Gale 1957), Valves, Relief valves (only when the project has a relief valve: the law and its three named departures, the default overpressure and its 15 psi scope, the three capacity kinds and the rule never to mix them, the status rule, the closed start and the system-curve start, the opening reading, the flags and refusals, Kw, Kc and Kv not applied; API 520 and API 526 via fluids, Pentair TP-V300, Simscape, AFT, EPANET 2.2 and CLAUDE.md D21), Equipment (only when the project has equipment: the law and the rated drop's definition, density scaling, the Cv/Kv conversion when an item is rated by one, reverse and laminar flow flagged, the zero-flow Jacobian floor, viscosity not corrected; ISA-75.01.01 and Silverberg & Darby), Orifices (only when the project has an orifice plate: the law and ISO 5167-2's pressure-loss relation, the C at D and D/2 tappings for every plate with the named departures and their sizes, the hold below ISO's lowest Reynolds number, the refusal where C could exceed 1, a meter's reading at its taps, the vena-contracta flashing check, ISO's limits, the outlet bore and reverse flow flagged, the zero-flow Jacobian floor, ε = 1; with an entered C, its definition, its move from corner or flange taps and its laminar flag; ISO 5167-2:2003 via fluids, Reader-Harris et al. 2019, Deltares WANDA and Rennels & Hudson), Fluid properties, Atmosphere and NPSH, Conventions (SI, gauge, EGL vs HGL, datum, flow signs); global assumptions (steady, incompressible, isothermal, single-phase, quiescent boundaries, no entrance or exit loss at a boundary without an entrance or exit fitting and the web app's default fittings at reservoirs, pump integral check, check-valve model, ideal control-valve default; with relief valves, conventional spring-loaded valves in liquid service lifting linearly, a convention, from the set to full lift, with API 520's liquid capacity equation on the total-pressure difference; with equipment, constant-K losses scaled with flow² and density, viscosity not corrected; with orifice plates, ISO 5167-2 geometry and installation and its permanent pressure loss with the C at D and D/2 tappings (or an entered one), for a single-phase liquid); libraries with versions (opensolve-pipe, fluids, CoolProp, numpy, scipy). Written to be pasted into a deliverable.

### 4.11 Assigned Flow Model

```typescript
interface AssignedFlow extends BaseComponent {
  type: 'assigned_flow';
  flow: number;                  // m³/s, within ±100, required (no default);
                                 // positive = leaving the network (demand), negative = entering it (supply)
  ports: [Port & { id: 'port_1' }];
}
```

The node fixes the flow at its port whatever the pressure there; the pressure is a result (`NodeResult`), not an input. A flow of 0 behaves exactly as a plug. An assigned-flow node is not a fixed-pressure boundary (§3.2.1), so a sub-network with no reservoir or reference node is still `NO_FIXED_HEAD`, whose message says so.

- **Results.** Its port has a `NodeResult` like any port: EGL, the connected pipe's velocity, HGL, static and absolute pressure, with `BELOW_VAPOR_PRESSURE` when the absolute pressure is below the vapor pressure (or ≤ 0 Pa without one). Its `BoundaryResult` (type `assigned_flow`) gives the EGL and `outflow` = −flow, as solved. On an undetermined pressure level it has neither; the flow in its connection is still reported.
- **No steady state.** Where no reservoir or reference node reaches the node through open elements (a valve closed or a pump stopped on its only path), its part carries assigned flows only if they sum to zero (then a floating section, `UNDETERMINED_PRESSURE`). Otherwise the closed elements around it whose rules would open are re-opened, and with none the solve is not converged: the message names each node with its flow and each element closed around it with the reason (CLAUDE.md D12). A flow control that alone feeds assigned flows follows its status rules: an FCV fed less than its setpoint is open (`CONTROL_VALVE_SETPOINT_NOT_MET`), a speed-controlled pump fed another flow runs at a speed limit (`PUMP_SETPOINT_NOT_MET`); a flow equal to the setpoint (over-controlled), more than an FCV's setpoint, or reverse flow through a one-way element has no determined steady state, and the solve is not converged, naming the control and the nodes.
- **Trace.** The flow as entered with the sign convention, the port's elevation, EGL, velocity head, HGL, static and absolute pressure, and the continuity equation at the port with its residual (§4.10); a note that it is not a pressure boundary, stating when a part no fixed head reaches carries its flow (only with balanced assigned flows, at an undetermined level; a zero flow is a closed end). A floating section that holds assigned flows is flagged `UNDETERMINED_PRESSURE` with flow passing through it, its assigned-flow nodes and their flows named as its drivers. The convergence report's `oscillatingComponents` lists elements with a status, never an assigned-flow node, which the message names.
- **System curves.** The forced-flow bound counts assigned flows as fixed supplies and demands, and they can also set a least forced flow (a demand on the discharge side that a one-way element keeps every fixed head from feeding): points beyond either bound have no steady state, and say so; a pump side that reaches only assigned-flow nodes has no point with a head (TSD §5.6).

Solver mapping: TSD §4.8.

### 4.12 Scenario Model

A scenario is a named case of the project: the base project with some of its values overridden (PRD §3.8; CLAUDE.md D15; design: `docs/proposals/scenario-manager.md`).

```typescript
interface Scenario {
  id: string;                    // Identifier, unique among the project's scenarios (own namespace)
  name: string;                  // 1-100 characters; need not be unique
  description?: string | null;   // at most 500 characters
  overrides: Override[];         // at most 30; at most one per value (order never matters)
}

type Override = ComponentOverride | PipeOverride | ProjectOverride;   // discriminated by `kind`

interface ComponentOverride {
  kind: 'component';
  componentId: string;
  field: 'status' | 'speed' | 'control.setpoint' | 'setpoint' | 'resistance'
       | 'liquidLevel' | 'surfacePressure' | 'pressure' | 'flow'
       | 'rating' | 'rating.pressureLoss' | 'rating.flow' | 'rating.density' | 'rating.value'
       | 'boreDiameter' | 'dischargeCoefficient'    // orifice plate, §4.16
       | 'setPressure' | 'capacity' | 'capacity.letter' | 'capacity.area'
       | 'capacity.dischargeCoefficient' | 'capacity.overpressure';   // relief valve, §4.17
  value: JsonValue;              // SI, checked as the target field's own type when applied
}

interface PipeOverride {
  kind: 'pipe';
  connectionId: string;
  pipeIndex: number;             // 0-based into piping.pipes, as Fitting.pipeIndex (0-99)
  field: 'spec' | 'length';
  value: JsonValue;
}

interface ProjectOverride {
  kind: 'project';
  field: 'fluid' | 'fluid.temperature';
  value: JsonValue;
}
```

- **Addressing: a field allow-list** (TSD §12, decided). `field` is a camelCase dotted path relative to the target, and the fields each target type takes are data in `models/scenarios.py`, published as `x-override-fields` on the `Scenario` schema (§5.1):

| Target | Fields | Value |
|--------|--------|-------|
| `Reservoir` | `liquidLevel`, `surfacePressure` | m; Pa(g) |
| `IdealReferenceNode` | `pressure` | Pa(g) |
| `AssignedFlow` | `flow` | m³/s, signed (§4.11) |
| `Pump` | `status`, `speed`, `control.setpoint` | `on`/`off`; a fraction (with flow control, the maximum, above `minSpeed`); m³/s (only on a pump with flow control) |
| `IsolationValve`, `CheckValve` | `status`, `resistance` | the type's status literal; a `FlowCoefficient` or null (the cited default) |
| `ControlValve` | `status`, `resistance`, `setpoint` | as above; Pa(g) for a PRV or PSV, m³/s for an FCV |
| `Equipment` | `rating`; `rating.pressureLoss`, `rating.flow`, `rating.density` (held by a `RatedPoint`); `rating.value` (held by a `RatedFlowCoefficient`) | a whole `EquipmentRating` (§4.14, either kind); Pa, a difference (trace unit `Pa (difference)`); m³/s; kg/m³; the Cv or Kv as entered (labelled by the item's kind) |
| `Orifice` | `boreDiameter`, `dischargeCoefficient` | m (a second plate); a number, the C at the plate's taps (a calibrated plate), or null for ISO 5167-2's C (§4.16), written "ISO 5167-2's (the default)". The taps are installation and not listed |
| `ReliefValve` | `status`, `setPressure`, `capacity`; `capacity.letter` (held by an `Api526Orifice`); `capacity.area` (held by an `EffectiveOrifice` or a `CertifiedOrifice`: `x-override-fields` lists both in `holders`); `capacity.dischargeCoefficient`, `capacity.overpressure` (held by a `CertifiedOrifice`) | `active`/`locked_closed`; Pa, a difference (trace unit `Pa (difference)`); a whole capacity (§4.17, any kind), written "API 526 J (0.000830321 m²), Kd 0.65 (preliminary)", "API 520 effective area 0.000447071 m², Kd 0.65 (preliminary)" or "certified area 0.00025 m², rated coefficient 0.7, overpressure 0.08"; a letter D to T; m² (an effective area or an actual area, labelled by the valve's kind); a fraction; a fraction, or null for ASME's default, written "ASME's 10 % or 3 psi (the default)". A base switch between kinds leaves the other kind's values `not_applicable` |
| `Plug`, `TeeBranch`, `WyeBranch` | none | |
| `PipeDefinition` | `spec`, `length` | `{materialId, schedule?, nominalSize?, innerDiameter?, roughness?}`, which replaces all five keys (a spec without `innerDiameter` drops a bore override); m |
| `Project` | `fluid`, `fluid.temperature` | a whole `FluidDefinition`; K, for a built-in fluid only |

- **Rules on every request** (400, by index only): `kind` and `field` from the lists above, `pipeIndex` and the list lengths within their bounds, no two overrides of one value of one target, no override of a value together with a part of it (`fluid` with `fluid.temperature`, an equipment item's `rating` with `rating.flow`, a relief valve's `capacity` with `capacity.area`), and unique scenario ids. Only the requested scenario's values are checked, when it is applied: a scenario with a bad value never blocks the base or another scenario.
- **Applied** (TSD §5.7): the base's JSON with each value written at its target and `scenarios` dropped, validated as a project. Its solve is the solve of that project edited by hand, bit for bit.
- **Ignored, not lost.** An override whose component, connection or pipe is not in the project is `orphaned`; one whose target has no such value (a status on a reservoir, `control.setpoint` on a pump without flow control, `fluid.temperature` on a custom fluid, `rating.flow` on an item rated by a Cv or Kv, `rating.value` on one rated by a point, `capacity.area` on a relief valve sized by a letter, `capacity.dischargeCoefficient` on one with an effective area) is `not_applicable`. Both are kept in the scenario, reported in the response and the methods summary, and ignored; neither raises a flag.
- **Values only.** Overrides never change components, connections, ports or pipe counts (PRD §3.8).

Results (`SolveResponse.scenario`, `SystemCurveResponse.scenario`; null for the base project):

```typescript
interface ScenarioResult {
  id: string; name: string; description: string | null;
  overrides: OverrideResult[];   // every override, in the scenario's order
}

interface OverrideResult {
  index: number;                 // 0-based into the scenario's overrides
  override: Override;            // as given
  state: 'applied' | 'orphaned' | 'not_applicable';
  value: JsonValue;              // the value used, as validated, SI (null unless applied)
  baseValue: JsonValue;          // the base project's value (an unset field gives its default)
  unit: string;                  // trace unit of value and baseValue ('' for none)
  message: string;               // why it was not applied ('' when applied)
}
```

A scenario solve's methods summary (§4.10) starts with a **Scenario** section (the scenario, how many overrides were applied, each applied one with its base value, each ignored one with the reason), and the trace of each component or connection an applied override changes starts with a note naming the scenario and the change. Trace input sources stay `user` and `default`. A whole rating is written in these texts as "Cv 120" or "50000 Pa at 0.015 m³/s, 999.103 kg/m³", never as a raw object. `METHOD_VERSION` is unchanged: applying a scenario changes inputs, not calculations.

### 4.13 Goal Seek Model

Built in v1 (PRD §3.9, CLAUDE.md D16; design and its as-built notes: `docs/proposals/goal-seek.md`). Models: `models/goal_seek.py`; envelopes in `models/api.py`. Nothing is added to `Project`: the setup and the result are the request's and the response's only.

```typescript
interface GoalSeekRequest {      // POST /api/v1/goal-seek
  project: Project;
  scenarioId?: string | null;    // run on this scenario: the variables are written on top of its values
  variables: GoalVariable[];     // 1-4
  goals: Goal[];                 // as many as variables
}

type GoalVariable = ComponentVariable | PipeVariable | ProjectVariable;   // discriminated by `kind`

interface ComponentVariable {    // addressed as a ComponentOverride (§4.12)
  kind: 'component';
  componentId: string;
  field: 'speed' | 'control.setpoint' | 'setpoint' | 'resistance'
       | 'liquidLevel' | 'surfacePressure' | 'pressure' | 'flow'
       | 'rating.pressureLoss' | 'rating.flow' | 'rating.density' | 'rating.value'   // equipment, §4.14
       | 'boreDiameter' | 'dischargeCoefficient'    // orifice plate, §4.16
       | 'setPressure' | 'capacity.area' | 'capacity.dischargeCoefficient'
       | 'capacity.overpressure';   // relief valve, §4.17
  coefficient?: 'K' | 'Cv' | 'Kv';   // resistance only (required there): resistance = {kind, value}
  lower: number;                 // SI, finite, within the field's own bounds; lower < upper
  upper: number;
}

interface PipeVariable { kind: 'pipe'; connectionId: string; pipeIndex: number; field: 'length'; lower: number; upper: number; }
interface ProjectVariable { kind: 'project'; field: 'fluid.temperature'; lower: number; upper: number; }

interface Goal {
  quantity: 'port_pressure' | 'link_flow' | 'link_velocity' | 'link_head_loss'
          | 'pump_flow' | 'pump_head' | 'pump_npsh_available' | 'pump_npsh_margin'
          | 'valve_flow' | 'valve_pressure_drop'
          | 'equipment_flow' | 'equipment_pressure_loss' | 'equipment_pressure_drop'
          | 'orifice_flow' | 'orifice_pressure_loss' | 'orifice_differential_pressure'
          | 'orifice_pressure_drop'
          | 'relief_valve_flow' | 'relief_valve_pressure_drop'
          | 'boundary_outflow';
  elementId: string;             // the component or connection
  portId?: string;               // port_pressure only (required there)
  target: number;                // SI, in the quantity's unit, |target| <= 1e8
  tolerance?: number;            // SI; omitted: max(0.5 % of |target|, the quantity's floor)
}

interface GoalSeekResponse {
  success: boolean;              // result.met
  result: GoalSeekResult;
  solvedState: SolvedState | null;   // the reported evaluation's own solve, annotated; null when none is usable
  computeTime: number;
  scenario: ScenarioResult | null;   // as /solve reports it (§4.12)
}

interface GoalSeekResult {
  met: boolean;                  // every goal within its tolerance at the reported evaluation
  stopReason: 'met_at_start' | 'met' | 'not_reachable' | 'jump' | 'unsolved_crossing'
            | 'no_progress' | 'evaluation_limit' | 'time_budget' | 'no_usable_evaluation';
  message: string;               // why it stopped, SI
  method: 'scan_brent' | 'least_squares';
  methodVersion: string;         // the solves' METHOD_VERSION
  evaluationLimit: number;       // 60 for one variable, 20(n + 1) for n
  timeBudget: number;            // s
  reportedEvaluation: number | null;
  variables: { index; variable; label; unit; scale: 'linear' | 'log'; start;
               startSource: 'case' | 'clipped' | 'middle'; caseValue;
               baseValue;                        // null where the base holds no such value (an item rated otherwise)
               value: number | null; atBound: 'lower' | 'upper' | null;
               override: Override | null;        // the scenario override that applies `value`
               replacedOverride: number | null }[];  // scenario run: the override whose value it replaced
  goals: { index; goal; label; unit; tolerance; toleranceSource: 'user' | 'default';
           value: number | null; residual: number | null; met: boolean; message;
           evaluatedMin: number | null; evaluatedMax: number | null }[];
  evaluations: { index; purpose: 'start' | 'scan' | 'root' | 'probe' | 'minimize' | 'step' | 'slope';
                 variableValues: number[]; outcome: 'usable' | 'not_converged' | 'no_value'
                 | 'topology_error' | 'fluid_error' | 'not_computed'; goalValues; residuals;
                 message; seconds; stateChanges: StateChange[] }[];
  notes: { code; message; variables; goals; evaluations; variableValues; goalValues;
           stateChanges }[];     // other_crossing, met_range, jump, unsolved_crossing, sensitive, …
  methods: MethodsSection;       // the "Goal seek" section, also first in solvedState's methods
}
```

- **Variables** are the numeric values of the scenario allow-list (§4.12), derived from it (`GOAL_COMPONENT_FIELDS`, `GOAL_PIPE_FIELDS`, `GOAL_PROJECT_FIELDS`; statuses, a pipe's `spec`, the whole `fluid` and an equipment item's whole `rating` are `NOT_VARIABLES`), published as `x-goal-variables`: by target schema, each field's bounding schema (for an equipment item's values, the rating member that holds them, `RatedPoint` or `RatedFlowCoefficient`), the path to the number, its scale (log for `length`, `resistance`, `rating.pressureLoss`, `rating.flow`, `rating.value` and an orifice plate's `boreDiameter`; `rating.density` and an orifice plate's `dischargeCoefficient` are linear) and a resistance's coefficients. A rating value the case's item does not hold (a Cv's `rating.flow`) is 400 `VARIABLE_NOT_APPLICABLE`: a goal seek varies a rating in the kind entered. `lower < upper` is published as `x-ordered-fields` on each variable schema. The search starts at the case's value (clipped into the bounds; a resistance the case does not hold in that coefficient, and an orifice plate's discharge coefficient on ISO 5167-2's default, start at the middle of the bounds on the variable's scale). An orifice plate's bore and discharge coefficient also meet a topology rule (β < 1 and C ≤ 1, §4.16), so the network is built at each bound of such a variable, with the other values as the case holds them: its `ORIFICE_OUT_OF_RANGE` there is a 400 `VALIDATION_ERROR` located by index ("body.variables.0.upper: the orifice's bore is not smaller than its inlet pipe's inner diameter"), the plate in `componentIds` and no id or value in the text. For one such variable alone the rule is monotone in that value, so the two builds prove every trial builds; with a bore and a coefficient varied together, or a bore on an entered coefficient moved from corner or flange taps, a refused trial is an unusable trial. A relief valve's `setPressure` (linear), `capacity.area` (log; an effective or a certified area), `capacity.dischargeCoefficient` and `capacity.overpressure` (linear; a certified capacity's) are variables; its whole `capacity` and `capacity.letter` are `NOT_VARIABLES` (size a valve by varying an effective area). A value the case's capacity kind does not hold is 400 `VARIABLE_NOT_APPLICABLE`, and a certified case on ASME's default overpressure starts at the middle of the bounds. They meet `RELIEF_VALVE_OUT_OF_RANGE` (§4.17), so the network is built at each of their bounds too, its refusal there a 400 located by index with no id or value ("the relief valve's set pressure is below ASME VIII's scope, 15 psi (103421 Pa), at this bound, …"); each of its tests is monotone in each of these values alone, so the two builds prove every trial builds. The scope refusal at a set's bound does not count where the same valve's overpressure is also a variable: every trial then writes an overpressure. With an effective area the Goal seek section names the API 526 letter covering the area found (fluids `API520_round_size`).
- **Goals** read the field the results tables and Compare show (`nodeResults[c:p].pressure`, `linkResults[id].flow`, the largest \|velocity\| of the connection and its segments, `headLoss`, `pumpResults[id].operatingFlow`, `operatingHead`, `npshAvailable`, `npshMargin`, `valveResults[id].flow`, `pressureDrop`, `equipmentResults[id].flow`, `pressureLoss`, `pressureDrop`, `orificeResults[id].flow`, `pressureLoss`, `differentialPressure`, `pressureDrop`, `reliefValveResults[id].flow`, `pressureDrop`, `boundaryResults[id].outflow`), published as `x-goal-quantities` with each quantity's unit, target schemas, port flag, default-tolerance rule (0.5 % of the target, at least 0.01 m of head, ×ρg of the case fluid for pressures, 10⁻⁶ m³/s for flows, 10⁻³ m/s for velocity) and smallest user tolerance (max(10⁻⁶ \|target\|, 0.1 Pa, 10⁻⁵ m, 10⁻⁹ m³/s or 10⁻⁶ m/s), which never depends on the fluid), and what it needs (`vaporPressure`, `npshrCurve`, and `taps` for an orifice plate's differential pressure: 400 `GOAL_NOT_APPLICABLE` on a plate without taps, whose taps no scenario changes). An assigned-flow node's outflow is its input and is not a goal. The request's list rules (`sameLength`, `uniqueBy`) are published as `x-goal-seek-rules`.
- **The values found are never applied by the server.** Each variable's `override`, written into the base at its path or upserted into the scenario by target and field, reproduces `solvedState` bit for bit (apart from `timestamp` and the annotation text). A value varied inside a whole value that the scenario overrides (a temperature inside a whole `fluid`, an equipment item's rated values inside a whole `rating`, a relief valve's values inside a whole `capacity`) is returned as that whole value holding every value found, read from the reported evaluation's case, so the overrides of two values of one rating are equal and any one of them reproduces the state; the Scenario section's mark names the values replaced ("the values found take the place of its rated pressure drop and rated flow").
- **Traceability.** `solvedState` starts its methods summary with a "Goal seek" section (the case, the method with its constants and citations, each variable and goal with its tolerance's source, why the search stopped, the notes), and each varied element's trace with a note; in a scenario run the Scenario section marks the overrides a variable replaced. No flags are added. `METHOD_VERSION` is unchanged and named.

### 4.14 Equipment Model

One side of a heat exchanger, a coil, a strainer, a filter or any other passive element whose datasheet gives its pressure drop at a flow (PRD §3.1.2; CLAUDE.md D18; design and its as-built notes: `docs/proposals/equipment-pressure-drop.md`). Model: `models/components.py`.

```typescript
interface Equipment extends BaseComponent {
  type: 'equipment';
  rating: EquipmentRating;       // required, no default
  ports: [ {id: 'inlet'}, {id: 'outlet'} ];
}

type EquipmentRating = RatedPoint | RatedFlowCoefficient;   // discriminated by `kind`

interface RatedPoint {
  kind: 'point';
  pressureLoss: number;          // Pa, a difference, (0, 1e8]: the datasheet drop at `flow`, as the
                                 // loss of total pressure inlet → outlet, without the ports' static head
  flow: number;                  // m³/s, (0, 100], inlet → outlet (a mass-flow rating ṁ_r: ṁ_r/ρ_r)
  density: number;               // kg/m³, (0, 3e4]: the fluid the datasheet is rated with
}

interface RatedFlowCoefficient { // FlowCoefficient (§4.9) narrowed to Cv and Kv, stored as entered
  kind: 'Cv' | 'Kv';             // Cv: US gpm of water at 1 psi; Kv: m³/h of water at 1 bar
  value: number;                 // (0, 1e7]
}
```

The element has no status and no type field: it always passes flow, valves isolate or bypass it, and its name says what it is. Every field is required: no source gives a default rating, and a water default left in place would silently mis-scale a coil or an exchanger rated on another fluid. A K alone is not a kind, since it means nothing without the bore it refers to (Later). An unknown kind, a K included, is 400 `VALIDATION_ERROR` with the type `invalid_rating`, which never quotes it; each value's only rule bounds that value, so the union needs no `x-` extension (the schema's `oneOf` and each member's `kind`, a `const` or an `enum`, state it).

- **Law.** h = EGL(inlet) − EGL(outlet) = c·Q\|Q\|. A rated point: c = ΔP_r/(ρ_r g Q_r²), so h(Q_r) = ΔP_r/(ρ_r g) and the pressure loss at the solved density ρ is ΔP_r (ρ/ρ_r)(Q/Q_r)². A Cv or Kv is a rated point on water by definition (1 psi at Cv US gpm, 1 bar at Kv m³/h): c = K/(2gA²) with the valves' conversion (§4.9; fluids `Cv_to_K` / `Kv_to_K`), the same on every bore, so no pipe diameter is needed, and its pressure loss is (ρ/ρ_w) × 1 psi × (Q/Cv gpm)² with ρ_w = 999.297 kg/m³. This is ISA-75.01.01 eq. (1) at constant C, the high-Re limit of Darby's 3-K method.
- **The rated drop is a loss, not a static difference.** It is the dissipative loss (friction and form) of total pressure between the ports, without the static head of their elevation difference. The ports keep their real elevations and each port's static pressure follows D7 with the velocity in its connected pipe, so the static drop reported is ρgh + ρg(z_out − z_in) + ρ(v_out² − v_in²)/2; resizing a pipe beside the element never changes its loss. A datasheet's static drop S between nozzles at different elevations or bores is entered as S − ρ_r g (z_out − z_in) − ρ_r (v_out² − v_in²)/2.
- **Results** (`SolvedState.equipmentResults`, §4.10): flow, `flowRatio` (null for a Cv or Kv, which has no rated flow), `headLoss`, `pressureLoss` (ρg × head loss: the rating scaled to the solved flow and density, the datasheet comparison), `pressureDrop` (static, inlet minus outlet, what gauges read) and the `rating` used, after any scenario or goal-seek trial. Each port has its `NodeResult`. A closed-off element has no result; one in a floating section has its flow and differences.
- **Flags.** `CORRELATION_OUT_OF_RANGE` (warning) when the flow runs outlet → inlet (the symmetric law is used; no datasheet rates reverse flow; the message has no numbers), and when the end segment of a connected pipe is laminar, 0 < Re < 2000, the lower of the two (as a valve's Cv or Kv). Viscosity is not corrected, and there is no flag for a flow far from the rating.
- **Topology.** `EQUIPMENT_RATING_OUT_OF_RANGE` (422, listed after the other issues, the element in `componentIds` and its rating quoted) when c is not a finite positive double, or its computation divides by zero or overflows inside the bounds (ρ_r = Q_r = 10⁻³⁰⁰; a Cv of 10⁻¹⁷⁰).
- **Scenarios and goal seek** (§4.12, §4.13): the whole `rating` and its four values are overridable; a value the item's kind does not hold is `not_applicable`; the four values are goal-seek variables and the whole rating is not; three goals read `flow`, `pressureLoss` and `pressureDrop`.
- **Trace and methods** (§4.10): a trace per element; an "Equipment" methods section and one assumption only when the project has equipment. `METHOD_VERSION` 1.3.0 adds the element; projects without equipment are unchanged in every value (TSD §10.4).

Solver mapping: TSD §4.9.

### 4.15 Design Check Model

Opt-in design practice (CLAUDE.md D19; `docs/proposals/design-checks.md`; `models/design_checks.py`, `services/design_checks.py`). A check is on when its object is present in `ProjectSettings.designChecks`; every limit is user data, and a preset only fills limits in, labelled with its source. Checks are computed by the API from a converged solved state, never in the solver: they change no solved value, status or flag (GOALS §4.6), and `METHOD_VERSION` does not change.

```typescript
interface DesignChecks {
  npshMargin?: { minimumMargin?: number /* m, [0, 100] */; minimumRatio?: number /* [1, 10] */; source: CheckSource };
  operatingRegion?: { preferredMin?: number; preferredMax?: number /* fractions of Q_BEP, (0, 5], min < max */; source: CheckSource };
  pipeVelocity?: { minimum?: number /* m/s, [0, 100] */; maximum?: number /* (0, 100], min < max */; source: CheckSource };
}
type CheckSource = { kind: 'user' } | { kind: 'preset'; preset: 'api610_por' | 'hi961_2012_general' };
// narrowed per check: npshMargin's preset is 'hi961_2012_general', operatingRegion's 'api610_por',
// pipeVelocity's source is { kind: 'user' } only

interface DesignCheckResult {
  check: 'npsh_margin' | 'operating_region' | 'allowable_region' | 'minimum_flow' | 'motor_power' | 'pipe_velocity';
  componentId: string | null;    // the pump
  connectionId: string | null;   // the connection (pipe_velocity)
  outcome: 'pass' | 'fail' | 'not_evaluated';
  value: number | null;          // SI; null: not evaluated
  pipeIndex: number | null;      // pipe_velocity: the pipe whose velocity is the value (0-based)
  pipesOutside: number[];        // pipe_velocity: the pipes outside the limits (0-based)
  limits: { min: number | null; max: number | null };  // SI
  unit: string;                  // 'm', '1', 'm³/s', 'W', 'm/s'
  source: string;                // 'user', 'manufacturer data (user)' or the preset's citation
  message: string;               // the inequality that set the outcome (6 significant digits, or as many
                                 // more as tell a value from its limit), or 'not evaluated: <why>'
}
```

The ordered pairs (and `PumpCurve.allowableOperatingRegion`'s) are model rules (400), published as `x-ordered-fields`; the presets, with their values and citations, as `x-design-check-presets` on `DesignChecks` (the web reads both: its fields take each pair's other end as a bound). Each check's `source` takes only its own presets (`npshMargin`: `hi961_2012_general`; `operatingRegion`: `api610_por`; `pipeVelocity`: the user's values only), and a preset source holds exactly the preset's values, every other limit unset; otherwise 400, never quoting the values, so a result never cites a standard for limits it does not give. A `designChecks` with no check present is no checks: it is left out of the dump and adds no methods section.

| Check | Passes when | Not evaluated when |
|---|---|---|
| `npsh_margin` | NPSHa ≥ max(NPSHr + margin, ratio × NPSHr), for the limits set | the pump is off or held at zero flow; no limit set; no NPSHr curve; no NPSHa |
| `operating_region` | preferredMin ≤ Q/Q_BEP ≤ preferredMax, Q_BEP the best efficiency point at the running speed (§4.10) | not running; no limit set; no best efficiency point (no efficiency curve, or its largest value at an end of its data) |
| `allowable_region` | flowMin ≤ Q/s ≤ flowMax (rated-speed equivalent flow, affinity laws) | listed only for a running pump whose curve has the data |
| `minimum_flow` | Q/s ≥ the larger of the minimum continuous stable and thermal flows | likewise |
| `motor_power` | P_shaft ≤ motorRatedPower (no service-factor margin) | no shaft power (no efficiency curve) |
| `pipe_velocity` | minimum ≤ \|v\| ≤ maximum in every pipe of the connection | no limit set |

The manufacturer-data checks run with `operating_region`. Results are listed per pump in component order (its checks in the table's order), then per connection in project order; a solve that did not converge has none. The methods summary ends with a "Design checks" section (each check, its limits, the presets' citations as references) only when a check is on. Presets (each cited through the secondary source that quotes it, the standard itself not read): `api610_por`, API 610's preferred operating region 0.7–1.2 of Q_BEP; `hi961_2012_general`, ANSI/HI 9.6.1-2012 "General", ratio 1.1 or 1.0 m, the greater. No velocity preset.

### 4.16 Orifice Model

A square-edged concentric orifice plate: a restriction orifice (a minimum-flow bypass, a balancing leg) or an orifice flow meter (PRD §3.1.2; CLAUDE.md D20; design and its as-built notes: `docs/proposals/orifice-plate.md`). Model: `models/components.py`; law: `services/solver/orifice.py`.

```typescript
interface Orifice extends BaseComponent {
  type: 'orifice';
  boreDiameter: number;          // m, (0, 10], required, no default: ISO 5167-2's d at the flowing temperature;
                                 // smaller than the inlet pipe's inner diameter (a topology issue otherwise)
  dischargeCoefficient?: number | null;  // (0, 1]; absent: ISO 5167-2's Reader-Harris/Gallagher C at the
                                 // solved flow (the default); a number: ISO 5167-2 eq. (1)'s C at the plate's
                                 // taps (at D and D/2 tappings without taps), held at every flow; not the flow
                                 // coefficient α = C/√(1 − β⁴)
  taps?: 'corner' | 'flange' | 'd_and_d_2' | null;  // a meter's pressure taps; absent: no taps, no reading
  ports: [ {id: 'inlet'}, {id: 'outlet'} ];
}
```

The plate has no status (valves isolate it). D is the inner diameter of the inlet pipe's end segment at the inlet port, as a valve's reference diameter (§4.9), and β = d/D; the plate's geometry does not depend on the flow direction. A value out of its bounds or an unknown tap set is 400 `VALIDATION_ERROR` at its field, never quoting it; each value's only model rule bounds it, so there is no new `x-` extension. A restriction known only by a Cv, a Kv or a pressure drop at a flow is an equipment item (§4.14).

- **Law.** h = EGL(inlet) − EGL(outlet) = K(C_L)·v\|v\|/(2g), v = Q/(πD²/4), with K(C) = (S/(Cβ²) − 1)², S = √(1 − β⁴(1 − C²)): ISO 5167-2's pressure-loss relation Δϖ = (S − Cβ²)/(S + Cβ²)·Δp over ρv²/2 (fluids `discharge_coefficient_to_K`), computed as K = u², u = (1 − β⁴)/(Cβ²(S + Cβ²)), 1 − β⁴ = (1 − β)(1 + β)(1 + β²) and 1 − β = (D − d)/D, so it keeps its digits as β → 1. It is Borda–Carnot's (1/(μβ²) − 1)² with the jet ratio μ = C/S.
- **The C that sets the loss, C_L, is the C at D and D/2 tappings for every plate, whatever its taps** (one loss per plate, the owner's answer of 2026-10-27): ISO 5167-2:2003 eq. (4), the Reader-Harris/Gallagher equation (fluids `C_Reader_Harris_Gallagher`), at Re_eff = max(Re_D, Re_lo), Re_D = 4ρ\|Q\|/(πDμ) in the inlet pipe; or an entered C_e moved to D and D/2 tappings, C_L = C_e·r, r = C_ISO(D and D/2, Re_eff)/C_ISO(taps, Re_eff), for corner or flange taps, and C_L = C_e without taps or at D and D/2 taps. Re_lo, ISO's lowest Reynolds number, is max(5000, 16000β²) at corner and D and D/2 tappings (ISO's limit made continuous at β 0.56) and max(5000, 170000β²D) at flange tappings (D in m); below it C is held at its value there and flagged, so fluids is never called at zero flow or below Re 5000, and h is exactly c·Q\|Q\| near zero flow. The slope is exact: dh/dQ holds dK/dC = −2K(1/C + β²/S) and eq. (4)'s analytic dC/dRe (0 where C is held). Named departures, stated in the methods summary and the trace at their largest over ISO 5167-2's range (D 50 mm–1 m, β 0.1–0.75, Re_D from Re_lo up): ISO's relation read with a meter's own C (a K up to 6.14 % higher at corner and 6.34 % at flange tappings, at β 0.75 as Re_D grows, flange on a 1 m pipe; a flow up to 2.94 % and 3.03 % lower where the plate takes the whole head); Reader-Harris et al. 2019's C with the downstream pressure at L2′ = 0.125 (a K 0.063–1.24 % lower, a flow up to 0.63 % higher); the continuous Re_lo.
- **A meter's reading** (`differentialPressure`, Pa, a difference) is ISO 5167-2 eq. (1) solved for Δp with ε = 1 (a liquid): (1 − β⁴)/(C_M²β⁴)·ρv\|v\|/2, signed as the flow, C_M ISO's C at the plate's own taps (held at their own Re_lo) or the entered C as entered; null without taps. It does not act on the network.
- **The vena contracta** (`venaContractaPressure`, gauge): p_vc = p_up + ρg(z_up − z_down) − (1 − β⁴)/(C_L²β⁴)·ρv²/2, p_up the static pressure of the port the flow enters (D7) and z_down the elevation of the port it leaves by (Deltares WANDA's choice). Below the vapor pressure, or at or below 0 Pa absolute for a fluid without one, it raises `BELOW_VAPOR_PRESSURE` (invalid) on the component, `details` {venaContractaAbsolutePressure, vaporPressure}: a flashing jet chokes the flow, so the flow solved is too high. Null and unchecked at zero flow and in a floating section; incipient cavitation is not checked.
- **Static pressures** follow D7 at each port with the velocity in its connected pipe, so the static drop is ρgh + ρg(z_out − z_in) + ρ(v_out² − v_in²)/2 and the outlet port's pressure is the recovered one (about 6 D downstream).
- **Results** (`SolvedState.orificeResults`, §4.10): the flow, the losses, the reading and p_vc above, and the values the solve used (β, D, d, Re_D, C_L and its source, Re_eff, r, K, the taps and C_M), after any scenario or goal-seek trial. Each port has its `NodeResult`. A closed-off plate has no result; one in a floating section has its flow, head differences, reading, K and C, and a null p_vc.
- **Flags** (`CORRELATION_OUT_OF_RANGE`, warning, on the component, one per inequality broken, `details.limit` naming it, the numbers in SI): wherever eq. (4) is used (ISO's C, or an entered C moved from corner or flange taps), `boreDiameter` (d < 12.5 mm), `pipeDiameter` (D < 50 mm or > 1000 mm), `beta` (β < 0.1 or > 0.75; ISO 5167-2's limits as fluids documents them) and `reynoldsNumber` (0 < Re_D below Re_lo, `details` {value, lower, meterLower}); for every plate, `outletDiameter` (the outlet pipe's end-segment bore differs from D: the relation assumes recovery in the inlet's bore) and `reverseFlow` (the flow runs outlet → inlet; the loss is taken as for forward flow at the same flow rate); with an entered C, `laminar` (0 < Re_D < 2000, as a valve's Cv). The geometric and outlet flags are known before solving and raised by the builder. The plate and its installation (edge, thickness, straight lengths, roughness) are assumed to meet ISO 5167-2 and are not checked.
- **Topology.** `ORIFICE_OUT_OF_RANGE` (422, listed after the other issues, one per plate, the plate in `componentIds`, quoting d, D, β and the bound broken), for a plate the law cannot represent at any flow, naming the first rule it breaks: (a) β ≥ 1; (b) eq. (4), where it is used, can exceed 1: at D and D/2 tappings on ISO's C, where it sets the loss (C ≤ 1 is a jet no larger than the bore; above it K falls below the sudden expansion from the bore, physically impossible), or where it serves only the reading or the move, at the plate's corner or flange taps for ISO's meter reading or at either tap set in the ratio of an entered C's move (eq. (4) then extrapolated far beyond ISO's range, its largest C there being below 0.7, on which the reading or the move would rest); the text says which, with a remedy that works for that plate, and offers an entered C only without taps or at D and D/2 taps, where it is used as entered. On ISO's C this refuses β from about 0.970 (0.97025 from D 71.12 mm, at most 0.9706 on smaller pipes), and with flange taps on a pipe below about 55 mm, where eq. (4) at the flange tappings is the bound, from a lower β (0.969 at D 52.5 mm, 0.963 at 40.9 mm, 0.930 at 15.8 mm); (c) an entered C moved from corner or flange taps can exceed 1 (C_e·r_max > 1); (d) K/(2gA²) at the smallest C_L is not a finite positive double. Each extreme over Re ∈ [Re_lo, ∞) is a closed-form bound (each Re-dependent term of eq. (4) at whichever end makes the bound safe), so the refusal does not depend on the fluid.
- **Scenarios and goal seek** (§4.12, §4.13): `boreDiameter` and `dischargeCoefficient` (null for ISO's) are overridable and goal-seek variables (the bore on a log scale, the C linear, the C at the plate's taps as entered); the taps are not. Four goals read `flow`, `pressureLoss`, `differentialPressure` (a plate with taps) and `pressureDrop`.
- **Trace and methods** (§4.10): a trace per plate (with the Borda–Carnot bound (1/β² − 1)², K at C = 1, cited to Rennels and Hudson); an "Orifices" methods section after Equipment and one assumption only when the project has a plate. None of the design checks (§4.15) applies to the plate. `METHOD_VERSION` 1.4.0 adds the element; projects without orifice plates are unchanged in every value (TSD §10.4).

Solver mapping: TSD §4.10.

### 4.17 Relief Valve Model

A conventional spring-loaded pressure relief valve in liquid service: overpressure protection on a pump's discharge, a vessel or a line, discharging to atmosphere or to a return (PRD §3.1.2; CLAUDE.md D21; design and its as-built notes: `docs/proposals/pressure-relief-valve.md`). Model: `models/components.py`; law: `services/solver/relief.py`; data: `data/api526_orifices.json`.

```typescript
interface ReliefValve extends BaseComponent {
  type: 'relief_valve';
  setPressure: number;           // Pa, a difference, (0, 1e8], required, no default: the static pressure
                                 // difference, inlet minus outlet, at which it starts to open
  capacity: Api526Orifice | EffectiveOrifice | CertifiedOrifice;   // required, no default; by `kind`
  status?: 'active' | 'locked_closed';   // default 'active'; locked closed: gagged, or blocked
  ports: [ {id: 'inlet'}, {id: 'outlet'} ];
}
interface Api526Orifice { kind: 'api526'; letter: 'D' | 'E' | 'F' | 'G' | 'H' | 'J' | 'K' | 'L' | 'M' | 'N' | 'P' | 'Q' | 'R' | 'T' }
interface EffectiveOrifice { kind: 'effective'; area: number }   // m², (0, 78.54]: an API 520 effective area
interface CertifiedOrifice { kind: 'certified';
  area: number;                  // m², (0, 78.54]: the valve's actual orifice area, from its certification
  dischargeCoefficient: number;  // (0, 1]: its rated coefficient for liquid (ASME's K, 0.9 × the measured one)
  overpressure?: number | null;  // (0, 1]: its full-lift overpressure, a fraction of the set; absent: ASME's
}
```

The set is a difference because a conventional valve's spring sees one: discharging to atmosphere at the valve's elevation it is the gauge set pressure (an outlet pipe rising or falling to its open end adds its liquid-full static head); against a constant back pressure it is the bench setting, the set minus that back pressure, and back pressure built up by the flow raises the inlet pressure at which it relieves. A letter or an effective area takes API 520's effective coefficient of discharge, Kd = 0.65, and ASME's overpressure, labelled preliminary; a certified capacity takes its own area and rated coefficient, and its own overpressure or ASME's. The three kinds are never mixed. An out-of-bounds value, an unknown letter or an unknown kind is 400 `VALIDATION_ERROR` at its field, never quoting it (an unknown kind `invalid_capacity`); each value's only model rule bounds it. API 526's areas, Kd, ASME's fraction and floor and the 15 psi scope are published as `x-relief-data` on the `ReliefValve` schema (§5.1), read from `data/api526_orifices.json`, which `scripts/generate_relief_data.py` writes from fluids 1.3.1 (`--check` keeps it current). Not EPANET's PSV; its menu entry is "Pressure relief valve (API 520, liquids)", id prefix `RV`.

- **Overpressure** op: ASME VIII's liquid certification overpressure, max(0.10, 3 psi/Δp_s), 3 psi = 20,684.27 Pa (the default, `overpressureSource: 'asme_default'`), cited only for a set of at least 15 psi = 103,421.36 Pa, where it lies in [0.1, 0.2]; or a certified capacity's own (`user`). It is taken on the set difference (named in the methods summary and the trace).
- **Law.** Δp_t = ρg(h − (z_in − z_out)), h = EGL(inlet) − EGL(outlet): the total-pressure difference between the ports. The lift x = clip((Δp_t − Δp_s)/(op·Δp_s), 0, 1) rises linearly from the set to full lift at Δp_f = Δp_s(1 + op), a convention (Simscape, AFT), not the cited characteristic (Pentair TP-V300 Fig. 4-12); Q = x·Kd·A·√(2Δp_t/ρ), API 520's liquid capacity equation in exact SI with Kw = Kc = Kv = 1. On the EGL, h(Q) = h_set + (Δp(Q) − Δp_s)/(ρg), h_set = Δp_s/(ρg) + z_in − z_out; in the band u = √Δp is the largest real root of u³ − Δp_s·u − RQ = 0, R = op·Δp_s/(Kd·A·√(2/ρ)), and from Q_f = Kd·A·√(2Δp_f/ρ) on Δp = ρQ²/(2(Kd·A)²). h is continuous and strictly increasing, with a finite positive slope at zero flow.
- **Status.** EPANET 2.2's check-valve rule (cvstatus) with the cracking head h_set: at zero flow it opens once the static difference p_in − p_out exceeds Δp_s by ρg·Htol, and it closes on reverse flow beyond Qtol. Every closed-off, free-level, disconnected-section and system-curve rule applies to it as to a check valve. A solve starts an active valve closed; a system-curve point starts it open (the pump there is a fixed flow); `locked_closed` stays closed.
- **Results** (`SolvedState.reliefValveResults`, §4.10): the state, flow, lift, head loss, total-pressure difference, static drop, inlet and back pressures, the set, setRatio, the overpressure and its source, Δp_f, Q_f, flowRatio, the capacity used (with an effective area's covering API 526 letter, fluids `API520_round_size`) and API's Reynolds number on the orifice. Each port has its `NodeResult`. A valve with a closed-off or floating side has no result; one inside a floating section has its flow, lift and differences, and null pressures.
- **Flags.** `RELIEF_VALVE_OPEN` (info) at full lift; `CORRELATION_OUT_OF_RANGE` (warning, `details.limit` `partial_lift`) relieving short of it; `RELIEF_VALVE_CLOSED` (info) on an active valve closed with a closed-off or floating side, its message naming the levels of that side at which this valve stays closed (the other elements around the section can narrow which of them are steady states); `BELOW_VAPOR_PRESSURE` (invalid) on the component while it relieves with the outlet's absolute static pressure below the vapor pressure (at or below 0 Pa for a fluid without one), outside a floating section; `CORRELATION_OUT_OF_RANGE` (warning, `viscosity`) while it relieves at μ ≥ 0.1 Pa·s, with the Kv API 520 10E would give (not applied).
- **Topology.** `RELIEF_VALVE_OUT_OF_RANGE` (422, listed after `ORIFICE_OUT_OF_RANGE`, one per valve, quoting its values with the basis and a remedy): Kd·A, its square, Q_f, R or the band root's scale 2Δp_s√(Δp_s/3) is not a finite positive normal double at the case fluid's density (each a value the law uses or divides by); or the set is below 15 psi and the overpressure would be ASME's default (a letter, an effective area, or a certified capacity without an overpressure): enter the certified capacity with its overpressure. No refusal on geometry.
- **Discharge to atmosphere** is topology: the outlet pipe ends at a reference node at 0 kPa(g). The web's "Discharge to atmosphere" at a relief valve's free outlet adds one at the outlet port's elevation, through 1 m of pipe sized to the port with an exit fitting, as one undo step; its friction is solved as built-up back pressure.
- **Scenarios and goal seek** (§4.12, §4.13): `status`, `setPressure`, the whole `capacity` and its values are overridable; the set, the area, the rated coefficient and the overpressure are goal-seek variables, and two goals read `flow` and `pressureDrop`. Sizing is goal seek on an effective area for the inlet at the relieving pressure.
- **Trace and methods** (§4.10): a trace per valve; a "Relief valves" methods section after Valves and one assumption only when the project has a relief valve. None of the design checks (§4.15) applies to the valve. `METHOD_VERSION` 1.5.0 adds the element; projects without relief valves are unchanged in every value (TSD §10.4).

Solver mapping: TSD §4.11.

---

## 5. Interface Contracts

### 5.1 REST API Specification

All request and response values are SI; JSON is camelCase. The OpenAPI schema (`/openapi.json`, exported by `python -m opensolve_pipe.openapi`) is the contract; the frontend types are generated from it, and the frontend reads its validation from it too: the JSON Schema bounds, and the model rules JSON Schema cannot express, which the models publish as extensions:

| Extension | On | Meaning |
|-----------|----|---------|
| `x-port-ids` | each component schema with fixed ports | The exact port ids of the type |
| `x-port-roles` | the same | Each named port's role (`inlet` / `outlet`) in the type's forward flow direction (pump suction → discharge, valve, equipment, orifice plate and relief valve inlet → outlet, a branch's dividing pattern); it orients new connections, the solver decides the flow |
| `x-port-count` | `IdealReferenceNode` | The exact number of ports where the ids are free |
| `x-required-parameters` | `Fitting` | Fields each fitting type needs (`bend`: `angle`, `radiusRatio`; …) |
| `x-reducer-types`, `x-entrance-types`, `x-exit-types` | `Fitting` | Fittings between two pipes; fittings for the loss where flow leaves or enters a body of liquid |
| `x-setpoint-bounds` | `ControlValve` | Setpoint bounds by valve type where they differ from the field's (`fcv`: a flow, 0–100 m³/s) |
| `x-ordered-fields` | `Pump`; `ComponentVariable`, `PipeVariable`, `ProjectVariable`; `OperatingRegionCheck`, `PipeVelocityCheck`, `AllowableOperatingRegion` | Pairs of fields (dotted camelCase paths, `lower`, `upper`, `strict`) whose values must be ordered, lower < upper when strict, checked when both are present: a speed-controlled pump's `control.minSpeed` < `speed` (CLAUDE.md D11); a goal-seek variable's `lower` < `upper` (D16); a design check's `preferredMin` < `preferredMax` and `minimum` < `maximum`, and a pump curve's allowable `flowMin` < `flowMax` (D19) |
| `x-design-check-presets` | `DesignChecks` | The cited presets (§4.15): each one's `id`, the `check` it fills, its `values` and its `citation`, which the Settings preset buttons write and the results' sources name (D19) |
| `x-override-fields` | `Scenario` | The scenario allow-list (§4.12): by target schema (every component schema, `PipeDefinition`, `Project`), each field a scenario may override, with the schema that holds its value (whose property gives its bounds) and its camelCase `path` from the target, or the `keys` of a group replaced together (a pipe's `spec`); a value several members of a union hold also lists every holder schema in `holders` (a relief valve's `capacity.area`: `EffectiveOrifice`, `CertifiedOrifice`), and applies where the target holds any of them |
| `x-goal-variables` | `GoalSeekRequest` | The goal-seek variables (§4.13): by target schema (every component schema, `PipeDefinition`, `Project`), each numeric field of the allow-list with the `schema` whose property bounds its number, the camelCase `path` from the target to it, its `scale` (`linear` or `log`) and, for a resistance, its `coefficients` |
| `x-goal-quantities` | `GoalSeekRequest` | The goal quantities (§4.13): each one's `unit`, the `targets` schemas its `elementId` may name, whether it takes a `port`, the default tolerance (`relativeTolerance` and `floor`: a head floor applies to a pressure through ρg of the case fluid), the smallest user tolerance (`minimum`: `relative` and `absolute`, independent of the fluid) and what the case `needs` |
| `x-relief-data` | `ReliefValve` | The relief valve's cited data (§4.17), from `data/api526_orifices.json`: `api526Areas` (letter → effective area, m²), `effectiveDischargeCoefficient` (0.65), `asmeOverpressureFraction` (0.10), `asmeOverpressureFloor` (3 psi in Pa) and `asmeMinimumSetPressure` (15 psi in Pa), which the form's letter list, the default overpressure and goal seek's default set bound read |
| `x-goal-seek-rules` | `GoalSeekRequest` | The request's list rules: `sameLength` (as many goals as variables) and `uniqueBy` (the keys on which two variables, or two goals, must differ; an absent key counts as null) |

The validators enforce exactly what the extensions state (`tests/unit/test_schema_rules.py`), which also fails while the frontend's copy of the schema (`apps/web/src/lib/api/openapi.json`, `pnpm gen:types`) is out of date.

| Method and path | Request | Response |
|-----------------|---------|----------|
| `POST /api/v1/solve` | `{project, scenarioId?, options: {includeSystemCurve, systemCurvePoints}}` | `SolveResponse {success, solvedState, computeTime, scenario}`; with `scenarioId`, that scenario of the project is solved and `scenario` lists every override with its state, the value used and the base value (§4.12; null for the base project) |
| `POST /api/v1/system-curve` | `{project, scenarioId?, pumpId, flowMin, flowMax?, numPoints}` | `SystemCurveResponse {pumpId, flowRange, points[{flow, head \| null, converged, message, npshAvailable, reason, componentIds, assignedFlowNodeIds, limitFlow, passedFlow, openHead, openHeadBound, startsTried}], converged[], scenario}`, of the scenario when `scenarioId` is given: the pump replaced by each fixed flow, other pumps running; default flows 0 to 1.2 × the curve's largest flow × s. `converged` is true for a point with a head; a point without one says why in `message` and the same as data in `reason` with the ids and numbers the message quotes (§4.10). The web app's pump chart uses it for the pump being viewed, with the project as solved (D10) |
| `POST /api/v1/goal-seek` | `{project, scenarioId?, variables[1-4], goals[as many]}` (§4.13) | `GoalSeekResponse {success, result, solvedState, computeTime, scenario}`: the values found, each goal's achieved value and met status, why the search stopped, every evaluation, the notes and the "Goal seek" methods section, with the solved state at the values found; a goal not met is 200 with `success` false. At most one goal seek runs in the worker pool at a time |
| `GET /api/v1/fluids` | — | `FluidListResponse {fluids: FluidInfo[]}`: temperature and concentration ranges queried from CoolProp, glycol `freezingPoints` (the lower temperature bound depends on the concentration), vapor-pressure availability, source, notes |
| `POST /api/v1/fluids/properties` | `FluidDefinition` (a `BuiltinFluid` with its temperature, concentration and overrides, or a `CustomFluid`) | `FluidPropertiesResponse {fluid (the built-in id, or 'custom'), properties: FluidProperties}`: the properties as the solver will use them. The fluid travels in the body, which is never logged; the web app uses this endpoint |
| `GET /api/v1/fluids/{id}/properties?temperature=&concentration=` | — | `FluidPropertiesResponse`, for a built-in fluid without overrides. For API users: the server's access log keeps only the path, but the query values (a project's fluid state) travel in the URL, where proxies, CDNs and other intermediaries may log them |
| `POST /api/v1/fluids/custom` | `CustomFluid` | `FluidPropertiesResponse` |
| `GET /api/v1/library` | — | `LibraryResponse {materials (schedules, sizes, dimensions, roughness, sources), fittings (correlation call, reference diameter, source)}` |
| `GET /api/v1/method-versions` | — | `MethodVersionsResponse {current, versions[{version, date, changes}]}` |
| `GET /api/v1/about` | — | `AboutResponse {name, version, methodVersion, commit, source, license, licenseUrl}`: the commit the server was built from (null when the image records none) and its source and license links (AGPL-3.0 §13; TSD §11.2) |
| `GET /source` | — | 302 to the source code of that commit (the repository when none is recorded); the web app's footer and home page link it |
| `GET /` | — | 302 to `/api/v1/about` (not in the schema) |
| `GET /health` | — | `{status: "healthy"}` |

Solver options that change results (`frictionMethod`, `maxIterations`, `tolerance`) live in `project.settings.solverOptions`, so a link always reproduces its results; request `options` only control extras such as system curves.

#### 5.1.1 Solve Network

```yaml
POST /api/v1/solve
Request:  { "project": <Project>, "options": { "includeSystemCurve": true, "systemCurvePoints": 41 } }
          # + "scenarioId": "S2" to solve that scenario of the project (§4.12)

200 OK:   { "success": true, "solvedState": <SolvedState>, "computeTime": 0.012, "scenario": null }
          # with scenarioId: "scenario": { "id": "S2", "name": …, "overrides": [ <OverrideResult>, … ] }
          # non-convergence is also 200, with success = false and solvedState.converged = false

422:      { "success": false, "error": "TOPOLOGY_ERROR",
            "message": "The network cannot be solved: 2 topology issue(s).",
            "issues": [ { "code": "NO_FIXED_HEAD", "message": "...", "componentIds": ["P1"], "connectionIds": [] } ] }
```

#### 5.1.2 Errors

Every error uses `ErrorResponse {success: false, error, message, issues[]}`:

| Status | `error` | When |
|--------|---------|------|
| 400 | `VALIDATION_ERROR` | Request fails the schema, or its body is not readable JSON; one issue per problem with its field path (submitted values are never echoed: no input values, tags or ids in messages, an unknown key is reported as `(unknown field)`, and a location inside a scenario override's `value`, whose keys are the submitter's, stops at `value`); also an empty system-curve flow range (`EMPTY_FLOW_RANGE`) |
| 400 | `VALIDATION_ERROR` (scenario) | A value of the requested scenario that its target rejects: one issue per problem, located at `body.project.scenarios.{s}.overrides.{j}.value…` (a rule of a whole component or pipe once, at the override whose value it rejects), with the target in `componentIds` / `connectionIds`, the schema's own message and never the value; a pipe spec with a key outside its five is `invalid_pipe_spec` |
| 400 | `FLUID_ERROR` | Temperature or concentration outside the property source's range; for a scenario, "Scenario S2: …" |
| 400 | `VALIDATION_ERROR` (goal seek) | Checked after the scenario, the case fluid and unknown elements: a variable or goal that does not apply to the case (`VARIABLE_NOT_APPLICABLE`, `GOAL_NOT_APPLICABLE`), NPSH data the case lacks (`NPSH_DATA_MISSING`), a tolerance below its smallest (`TOLERANCE_TOO_SMALL`); after the case's topology, a bound its field or an object rule rejects (the schema's own error type and message, at `body.variables.{i}.lower` or `.upper`). Every problem listed, located by index; the element's id only in `componentIds` / `connectionIds`, never in a message, and never a submitted value |
| 404 | `NOT_FOUND` | Unknown scenario id ("the project has no scenario 'S9'", checked first); unknown pump id for a system curve (checked after the scenario's values, before the topology); a goal seek's unknown component, connection, pipe or port ("Goal seek: N unknown element(s).", every one listed with its id named, after the scenario and the case fluid); unknown route |
| 405 | `METHOD_NOT_ALLOWED` | Wrong HTTP method for the route (`Allow` header lists the right one) |
| 413 | `PAYLOAD_TOO_LARGE` | Body over 1 MB |
| 422 | `TOPOLOGY_ERROR` | Port graph cannot be solved (§3.2.1); every issue listed. For a scenario, the issues of its effective project, with the message "Scenario S2 cannot be solved: N topology issue(s)." (a scenario is named by its id only: its name is a submitted value) |
| 429 | `RATE_LIMITED` | More than 60 solve, system-curve or goal-seek requests per minute from one client (`Retry-After`; a goal seek counts as one) |
| 500 | `INTERNAL_ERROR` | An unexpected failure (logged by type and route only); carries the CORS headers like every error |
| 503 | `SERVER_BUSY` / `TIMEOUT` | The solve pool is full, or this client already has a solve running and one waiting, or a goal seek is already in the pool (one at a time, refused at once) (`Retry-After`); the request's 45 s budget ran out (§7.2; a goal seek only when its first evaluation does not finish: later it stops with the best evaluation so far, 200 `time_budget`) |

#### 5.1.3 Get Fluid Properties

```yaml
POST /api/v1/fluids/properties
Request: { "kind": "builtin", "fluidId": "water", "temperature": 293.15 }
# GET /api/v1/fluids/water/properties?temperature=293.15 answers the same (its query may be logged
# by intermediaries)
200 OK: { "fluid": "water",
          "properties": { "name": "Water", "temperature": 293.15, "density": …, "dynamicViscosity": …,
                          "kinematicViscosity": …, "vaporPressure": …,
                          "sources": { "density": { "origin": "library", "citation": "CoolProp … IAPWS-95 …" }, … } } }
```

#### 5.1.4 Export Results (browser, CLAUDE.md D17)

There is no export endpoint: the design's `POST /api/v1/export` is dropped, not deferred. The results workbook, the CSV files and the pump chart image are made in the browser from the solve responses (and system curves and goal seek) the page already holds (§3.1.3, *Export*), so the project and its results are not sent a second time only to be formatted, and the server gains no CPU, worker or 503 path. The export makes no request; the methods version and library versions of each solve come from its response, and the calculation server's source from the page's configuration (`<API>/source`). A case with equipment gets an Equipment table after Valves, holding each item's results and the rating its solve used (`EquipmentResult.rating`, so a scenario's rating is read without applying the scenario), and About lines on its sign, its flow ratio and the Cv or Kv as entered; a file without equipment is unchanged. A case with orifice plates gets an Orifice plates table after Equipment, holding each plate's results, where its C came from ("ISO 5167-2", "ISO 5167-2 (held)", "Entered" or "Entered, moved to D and D/2", with the Reynolds number C was evaluated at and the tap ratio r as numbers), its taps and meter C, and the bore and pipe bore its solve used (`OrificeResult.boreDiameter`, `pipeDiameter`), and About lines on its sign and on its pressure differences read "≈ 0"; a file without orifice plates is unchanged. A case with relief valves gets a Relief valves table after Valves, holding each valve's results (a valve with no result as "Closed (no result)" from its `RELIEF_VALVE_CLOSED` flag, and a valve locked closed in the case as solved as "Closed (locked)", there and in Compare cases), and the set, overpressure and its source, and capacity its solve used (how it is given, its area, Kd and covering letter, `ReliefValveResult.capacity`), and About lines on its sign, its fractions (Δp ÷ set, lift, flow ÷ capacity) and the area unit; a file without relief valves is unchanged.

### 5.2 URL State Encoding

**Format:** `https://opensolve-pipe.app/p#{encoded_state}`. The app writes `/p#{encoded_state}` on its own origin, and Share copies the link with the page's origin.

The project travels in the URL **fragment** (after `#`). Browsers never send the fragment to the server, so project data does not appear in server, host or CDN logs. Code and tests: TSD §4.7.

**Encoding process** (`encodeProject`):

1. Serialize the project to canonical JSON. Object keys are sorted at every level and arrays keep their order, so equal projects give identical links. A non-finite number (NaN, ±Infinity) is refused rather than written as `null`.
2. Encode as UTF-8 and compress with gzip at level 9 (pako).
3. Encode as base64url (URL-safe alphabet, no padding).

**Decoding process** (`decodeProject`):

1. Trim the text and remove a leading `#`.
2. Decode base64url strictly, then gunzip, decode UTF-8 strictly and parse JSON. Any failure means a **corrupt** link.
3. Read `schemaVersion` and apply the migrations in order up to the current version. A value that is not an object with a positive integer `schemaVersion` is **invalid** ("does not contain an OpenSolve Pipe project"). A version newer than the app is **newer_version**.
4. Validate against the current `Project` schema, taken from the OpenAPI document generated from the API models and checked with Ajv. Then fill in schema defaults and check the port graph (unique ids, connection ends that exist, one connection per port). Any problem makes the link **invalid**, with every problem listed as a sentence that names the element.
5. Solver-level model rules (port ids per component type, pipe size source, fitting parameters, increasing curve flows, pump-curve references) do not stop a link from opening. The results pane lists them, and the solver reports them too.

**Writing links:**

- Every accepted edit, undo or redo rewrites the current history entry's fragment with `history.replaceState`, after a 300 ms debounce.
- Pending writes are flushed before Share, before an in-app navigation and when the page is hidden, so Back returns to the latest version.
- Links are copy-on-write: a link copied earlier keeps opening the project as it was then.
- Each accepted edit changes the project, including `metadata.modified`, so it makes a new link.
- Undo and redo history lives only in the open page. Nothing is kept in browser storage.

**Rules:**

- **Longevity** (from the first stable release the owner declares, CLAUDE.md D14; until then the model and the link format may change without a migration). A link from any released `schemaVersion` must always open. Breaking model changes bump `schemaVersion` (in the API models and in the frontend's `CURRENT_SCHEMA_VERSION`, which a test keeps equal) and add a migration. Migrations are never removed. Each released version keeps a fixture link that a test decodes and pins by SHA-256 (TSD §4.7).
- **Newer links.** A link from a newer `schemaVersion` than the app knows shows a clear error, not a partial load. The error names both format versions and asks the user to reload for the latest app.
- **Failed links.** A link that cannot be opened shows a page saying what went wrong (damaged, newer version, or not a valid project with up to 20 problems listed) and what to do. The options are to go back to the open project, to start a new project, or to go home. It never opens a partial project.
- **Length.** When the full link exceeds 8,000 characters, the Share dialog warns that some email and chat clients may cut it short.
- **Results.** The link holds the project, not results. The calculation-method version of its last solve (`methodVersion`) is recorded so a later solve with another version can say what changed (GOALS §4.3).
- **No server fallback** in v1 (Later: short links backed by storage).

**Example** (the start of the schema-v1 fixture link):

```
https://opensolve-pipe.app/p#H4sIAAAAAAACA7VX227bOBD9FWGeZVdS7Kyj13S7...
```

---

## 6. Integration Patterns

### 6.1 Solver Integration

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────────────┐
│ Port-graph  │ --> │ Network builder  │ --> │ GGA solver           │
│ Project     │     │ (validate, ports │     │ (Newton on heads and │
│ (SI)        │     │  → nodes, conns  │     │  flows; outer loops  │
└─────────────┘     │  → links)        │     │  for tee K and valve │
                    └──────────────────┘     │  status)             │
                                             └──────────┬───────────┘
                                                        │
                                             ┌──────────┴───────────┐
                                             │ Results mapper       │
                                             │ (→ SolvedState)      │
                                             └──────────────────────┘

Test only: the same networks are converted to WNTR/EPANET to check water results.
```

### 6.2 K-Factor Resolution

Priority order for fitting K-factors:

1. User-specified value (if provided)
2. Crane TP-410 correlation (if available for fitting type)
3. Fluids library default
4. Error if no value available

Every library value and correlation cites its source in the data file.

```python
def resolve_k_factor(fitting: Fitting, inner_diameter: float, re: float) -> float:
    if fitting.user_k_factor is not None:
        return fitting.user_k_factor

    if crane_available(fitting.type):
        return crane_k_factor(fitting, inner_diameter, re)

    if fluids_available(fitting.type):
        return fluids_k_factor(fitting, inner_diameter, re)

    raise ValueError(f"No K-factor available for {fitting.type}")
```

---

## 7. Security Considerations

### 7.1 Input Validation

- All numeric inputs bounded to physical ranges
- String inputs sanitized (component names, etc.)
- Request bodies up to 1 MB (`PAYLOAD_TOO_LARGE` beyond, whether or not the client declares a length). A project has at most 1,000 components and 2,000 connections, which fits in 1 MB at the sizes the frontend writes (about 230–310 bytes per component, 225–275 per connection); a project with long names or many fittings per connection reaches the byte limit sooner, which is then the effective limit. The largest such project with 20 scenarios of 30 overrides each (a whole fluid and 29 pipe specs, a 100-character name and a 500-character description) still fits (980,353 bytes; `test_project_bounds_fit_the_body_limit`).
- Decoded URL projects validated against the schema before use
- Later: file uploads (CSV, Excel) validated

### 7.2 Rate Limiting

- Solve requests: 60/minute per client (unauthenticated), a client being an IPv4 address or an IPv6 /64 network, since a host chooses and rotates the last 64 bits of its IPv6 address (TSD §11.2, "The key"); a 429 carries `Retry-After`. Behind the hosting platform's proxy the client IP is the proxy's unless uvicorn trusts the proxy's `X-Forwarded-For` (`FORWARDED_ALLOW_IPS` set to the proxy's address range, TSD §11.2); without it all users share one bucket.
- Solver work (`workers.py`): solves run in a pool of 2 worker threads holding at most 6 solves (running or waiting for a thread); a client's solves (the same key as the rate limit's) run one at a time, a second waiting for the first (a user solving again before the last result came back); a third concurrent solve from one client, or any solve when the pool is full, is refused at once with 503 `SERVER_BUSY`. Each request has a 45 s wall-clock budget from its arrival (below the frontend's 60 s timeout), checked at every Newton and outer iteration: a solve that runs out returns 503 `TIMEOUT`, and system-curve points not reached are reported as not computed (`reason` `not_computed`, and `message`), the solve itself kept. A goal seek is one request under the same budget: at most one is in the pool at a time (counted until its work stops; another is refused at once with 503 `SERVER_BUSY`), so a plain solve always has a worker, and a goal seek whose budget runs out after its first evaluation returns the best evaluation so far (`time_budget`). A client that disconnects cancels its solve. `computeTime` is the solver's own time in the worker, without waiting for it.
- Later: authenticated users get higher limits based on tier

### 7.3 Data Privacy

- v1 stores no project data on the server
- Projects in links travel in the URL fragment and are never sent to or logged by the server
- Solve and system-curve requests carry the project in the request body, and the fluid-properties request the fluid definition; request bodies are not logged. The web app puts no project value in a URL (`GET /fluids/{id}/properties` carries one in its query string; it stays for API users, §5.1)
- A scenario travels in the request body with its project, and its id in the body only; error messages name a scenario by its id, never by its name or values
- The access log keeps neither the client address nor query strings; uvicorn's trace-level ASGI records (which carry the request scope) are dropped; an unexpected error is logged by exception type and route only (its message can carry project values)
- Later: stored projects encrypted at rest

---

## 8. Error Handling Strategy

### 8.1 Error Categories

| Category | HTTP Code | User Action |
|----------|-----------|-------------|
| Validation Error | 400 | Fix input |
| Topology Error | 422 | Fix model connections (e.g., add a fixed-pressure boundary) |
| Convergence Failure | 200* | Review model, try simpler case |
| Server Error | 500 | Retry / Report |

*Convergence failure returns 200 with `converged: false` in response.

### 8.2 Convergence Failure Handling

v1: return `converged: false`, no results, and the largest continuity and energy residuals with the elements they occur at, those of the inner solve the message describes (TSD §5.2).

Later: last iteration state and suggested troubleshooting steps.

---

## 9. Extensibility Points

### 9.1 Component Types

New components can be added by:

1. Defining the TypeScript interface and the Pydantic model
2. Adding its head-loss law (h and dh/dQ) and any status logic to the solver
3. Adding UI panel for configuration
4. Adding at least one reference test case (TSD §10)
5. Later: adding a schematic symbol

### 9.2 Fluid Library

New fluids can be added via:

1. Built-in library extension (code change, with a cited source)
2. User-defined fluids (runtime, per-project)
3. Future: Global fluid database (user submissions)

### 9.3 Design Checks

Three checks are built (§4.15, CLAUDE.md D19). A new check is: an optional object in `DesignChecks` with its limits (bounded, ordered pairs in `x-ordered-fields`) and a `source`; an evaluator in `services/design_checks.py` that reads only the solved state and the project and returns `DesignCheckResult`s (a new `check` id) with the inequality in the message; a line in the "Design checks" methods section; and on the web its switch and fields in Settings, its wording from the result's numbers (`utils/design-checks.ts`) and, where it has one, its mark on the pump chart. A preset needs a cited source, labelled as read. Later: code-compliance libraries (NFPA 13, NFPA 20, ASME B31.1) and user-defined check libraries (PRD §5.5).

### 9.4 API (Future)

Architecture designed to support public API:

- All solver functionality exposed via REST
- Authentication via API keys
- Rate limiting per key
- Webhook support for async solves

---

## 10. Performance Considerations

### 10.1 Client-Side

- Lazy loading of UI components
- Virtual scrolling for large tables
- Debounced state serialization to the URL

### 10.2 Server-Side

- Stateless design for horizontal scaling
- Caching of fluid properties
- Sparse linear algebra once networks exceed ~100 components

### 10.3 Benchmarks (Targets)

| Operation | Target |
|-----------|--------|
| Page load (cold) | < 2s |
| Page load (cached) | < 500ms |
| Solve (simple) | < 1s |
| Solve (medium) | < 5s |
| URL encode/decode | < 100ms |

---

*End of SDD*
