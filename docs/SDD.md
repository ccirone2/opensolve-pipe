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

- **Home (`/`)** offers a new project (`/p`) and example projects, each a fixed link: the examples have fixed ids and timestamps, and their values are labeled as illustrative. It also explains that the project lives in the link and what the server receives when solving, and shows the disclaimer, the license and the source code link.
- **Project (`/p#<encoded>`)** decodes the fragment (§5.2) and opens the **workspace**, or shows a link error. An empty fragment starts a new project.

The **workspace** (`components/workspace/Workspace.svelte`) has a header, a **Build** pane (the panel navigator, §3.1.1) and a **Results** pane (§3.1.3):

- **Header.** Home link, editable project name, Undo and Redo (labelled with the change they undo or redo), Solve, Share (§3.1.5) and Settings. Settings covers the description, fluid, site elevation and atmospheric-pressure override, display units and solver options.
- **Layout.** From 1024 px the two panes are side by side; on narrow screens they are tabs. The Results tab is marked (icon and text) when the last solve failed, did not converge, has physically invalid flags or is out of date.
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
├── ComponentPanel                // the current component: type, id, name
│   ├── ComponentActions          // Add after, Add before, Add branch, Delete
│   │   ├── AddComponentDialog    // at a free port / into a connection / as a branch (tee or wye)
│   │   └── DeleteDialog          // optional "Join A and B" (keep the neighbors connected)
│   ├── Properties tab
│   │   ├── name, elevation
│   │   ├── per-type form         // forms/: Reservoir, ReferenceNode, Branch (tee, wye),
│   │   │                         //   Pump (+ PumpCurveEditor), IsolationValve, CheckValve, ControlValve
│   │   └── PortsEditor           // port sizes and elevations, what each connects to; reservoir ports
│   └── Piping tab → ConnectionPanel
│       ├── port selector         // which port's connection is shown
│       ├── connected port        // from → to, Go to <other end>, Insert component, Add branch,
│       │                         //   Disconnect; PipeSegmentForm per pipe (+ Add pipe segment);
│       │                         //   FittingsEditor
│       └── free port             // add a component here, plug it, remove it (reservoir),
│                                 //   or connect it to a free port elsewhere (close a loop)
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
- **From the results.** Clicking an element in the results (a table row, a flag, an input problem, a topology issue) starts the walk there. For a connection, the walk starts at its `from` component with the connection's piping open.
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

- **Status line**, the only live region: "Solving…", "Last solve: converged", "did not converge" or "no results", plus ", out of date".
- **`ResultsStateNotice`.** The results are out of date when the project changed, in a way that can change them, after the solve. Display units, names and metadata do not count. Results kept from an earlier solve after a later one failed are marked too. Both offer Solve again. The notice also appears in the trace view, so values are never shown without it.
- **Errors.**
  - Topology: "The network cannot be solved as connected", with each issue and a link to each component it names.
  - Validation: the problems.
  - Network: the API could not be reached, with a message that the project is safe in the page and its link.
- **`ConvergenceStatus`**: converged or not, the solver's message, iterations, compute time and the calculation-method version. For a solve that did not converge, it gives the largest continuity and energy errors, where they are, and which components kept switching state.
- **`MethodVersionNotice`.** Shown when the link was last solved with another calculation-method version. It lists what changed between the two (`GET /api/v1/method-versions`, GOALS §4.3).
- **`FlagsSummary`.** Flags are grouped by severity (physically invalid, warnings, information). Each has an icon and text in display units and names, never color alone, and starts with a link to its element's trace. Long groups show their first flags with "Show all", and a skip button leads past the flags.
- **Inputs to check.** Problems found in the browser that the solver would also report: no fixed-pressure boundary, ports neither connected nor plugged, a control valve still at setpoint 0, and model-rule problems. Each has a Show button into Build.
- **Views** (tabs; a view appears only when it has results):

| View | Content |
|------|---------|
| Summary | Fluid properties as used with their sources, atmospheric pressure, each pump's operating point, lowest pressure (gauge and absolute), highest velocity |
| Nodes | Per component port: elevation, pressure (gauge), absolute pressure, velocity, HGL, EGL; a note on the gauge reference and boundary ports |
| Links | Per connection: flow, velocity, head loss, Re, Darcy f, regime. Each row expands to its pipe segments (diameter, length, roughness, velocity, Re, f, friction loss) and fittings (quantity, the K each used, its reference diameter and source, head loss), with the flags about each |
| Pumps | Status, flow, head, speed, efficiency, hydraulic and shaft power, NPSHa, NPSHr, NPSH margin; then the chart (`PumpChart`) of one pump at a time, picked from a list when there are several |
| Valves | Type, state, flow, head loss, pressure drop, K open, K effective, Cv effective, setpoint, setpoint met |
| Branches | Tee and wye flow pattern, port flows, K per path, the velocity K is on, path losses, correlation |
| Boundaries | Reservoirs, reference nodes and plugs: EGL, outflow into the network, per port |
| Methods | `MethodsSummary` |

**Tables** (`ResultsTable`):

- one row per element, named in a sticky first column whose button opens the element's trace;
- unit labels under the headings, in the display units, and flags shown inline as badges (`FlagBadge`);
- 4 significant figures, and heads to at least 0.01 m (TSD §6.2);
- each table scrolls inside its own box, and long tables render in chunks.

**`PumpChart`.** Chart.js, loaded only when a chart is shown. It draws the pump curve at the operating speed (solid inside the user's data, dashed where extrapolated), the system curve and the operating point, with axes in display units. A data table of the same points sits under the chart; it is the fallback when there is no canvas.

- **System curve on demand** (D10). Showing a pump's chart requests its curve, `POST /api/v1/system-curve` with the project exactly as it was solved (`ProjectStore.solvedProject`, never a newer, edited one) and the pump id. The store caches each curve with its solve, sends one request at a time (the server runs one solve per client at a time), drops the cache when a new solve's results arrive, and aborts requests in flight when a solve starts. A curve is only shown with the solve it was computed for.
- **States, shown as they are.** While the curve is computed, the chart says so (`aria-busy`). A failure shows the server's message with **Try again**; a request cancelled by a newer solve offers to compute it. A point the API could not solve (`head: null`) is a gap in the line, counted under the chart, and its row in the data table gives the API's reason; with no point solved, no line is drawn and the chart says why.

**`TraceView`** shows how one element's results were obtained (GOALS §4.2). On wide screens it is a side panel over the results, which are inert underneath; on narrow ones it is a bottom-sheet dialog. It shows:

- whether the values are current and a solution at all;
- the element's flags, plus network-wide physically invalid flags;
- its result rows;
- the solver's trace (§4.10): inputs with their source badge (User, Default, Library, Computed); equations; correlations and data sources with citations; intermediate values in display units, with the SI value as reported; and notes.

**Show in Build** points the navigator at the element. A deleted element is labelled as such.

**`MethodsSummary`** shows the solve's methods and assumptions (`trace.methods`): sections with items and references, assumptions, and library versions. It reads well on screen and in print. **Copy as text** gives plain text for a report: a heading, the project, the method version, when it was solved, and whether it converged or is out of date. Without clipboard access the text is shown selected.

**Footer** (`SiteFooter`): the disclaimer (GOALS §4.8), About and privacy, the license (AGPL-3.0-or-later) and the source code.

Later: design-check warnings (opt-in).

#### 3.1.4 State Manager

**Purpose:** Single source of truth for application state (`state/`, Svelte 5 runes classes provided through context).

**`ProjectStore`** (`project.svelte.ts`):

- **The project.** It holds the port-graph project (SI values). The project is replaced, never mutated, and each stored project is deep-frozen.
- **Changes.** Every change goes through `update(change, label)`. It is applied to a copy and must pass the schema and port-graph checks (`validate.ts`). An invalid change is refused, leaving the project unchanged, so every link the app writes opens again. A change that changes nothing adds no undo step, and `metadata.modified` is updated on each change.
- **Undo and redo** keep up to 100 steps, each with a label, in page memory only. A burst of edits to one field can merge into one step.
- **URL.** The project is written to the URL fragment after a 300 ms debounce, and flushed before sharing and leaving (§5.2). The store keeps the encoded project, the link length and the 8,000-character warning.
- **Results.** It holds the latest solve response, `stale` (by a hydraulic fingerprint of the project without display units, names, metadata or method version), `solving` and a typed error: topology, validation or network. A newer solve supersedes an older one. A failed solve keeps the previous response, marked stale only if the project changed.
- **System curves.** `solvedProject` is the project as sent for the shown response. `loadSystemCurve(pumpId)` fetches a pump's curve for it (one request at a time) into `systemCurves` (loading, ready, error or cancelled per pump); `systemCurve(response, pumpId)` returns one only for the response whose results are shown. A new response, a load or clearing the results drops them; a solve starting cancels the requests in flight.
- **Method version.** After a solve that is current, the project records the solve's `methodVersion` (GOALS §4.3) without an undo step. The version the link was opened with is kept for `MethodVersionNotice`.

**`Workspace`** (`workspace.svelte.ts`) joins the store, the `LibraryStore`, the `NavigatorStore`, the visible pane, notices and the element open in the trace view. It offers the graph-edit actions (TSD §8.1). Results tables are rebuilt only when the solve, the display units or the labels they use (names, kinds, ports, connection ends) change, not on every edit.

**`LibraryStore`** (`library.svelte.ts`) holds the API's reference data: pipe materials, schedules and sizes and fitting types (`GET /api/v1/library`), built-in fluids and their ranges (`GET /api/v1/fluids`), and the method-version changelog. It loads them once per page. Hydraulic data is never invented in the browser: when the API cannot be reached these stay empty, and the UI offers what needs no data (custom pipes, custom fluids, fittings by id).

**API client** (`api/client.ts`):

- **Endpoints.** `solve` (with `includeSystemCurve: false` unless asked), `systemCurve`, `getLibrary`, `getFluids`, `fluidProperties` (`POST /api/v1/fluids/properties` with a `FluidDefinition`) and `methodVersions` (§5.1).
- **Requests.** It sends only what each request needs, with `credentials: 'omit'`, `referrerPolicy: 'no-referrer'` and a 60 s timeout (kept when the caller also passes an abort signal). Project data, the fluid included, travels only in request bodies: no URL carries a project value. Error responses become typed errors (`TopologyError`, `ValidationError`, `NetworkError`).
- **No other traffic.** No other network requests are made: no analytics, cookies, web fonts or third-party assets. The pages set `<meta name="referrer" content="no-referrer">`.

**Units.** Values are converted between SI and the display units only at input (`NumberField`) and display (formatters), TSD §6.

**Storage.** Nothing is kept in browser storage. History is the undo stack of the open page plus the links the user keeps.

Later: sync with the server for accounts and version history.

#### 3.1.5 Sharing

- **Share** (`workspace/ShareButton.svelte`) first writes any pending URL change, then copies the full link (the page's origin + `/p#<encoded>`) to the clipboard. Its dialog shows the link selected for copying by hand when the clipboard is unavailable, the link's length in characters, and a warning when it exceeds 8,000 characters. It also explains that the project is in the part after `#`, which browsers do not send to any server, and that edits make a new link while this one keeps opening this version.
- **Link errors** (`workspace/LinkErrorView.svelte`): a link that cannot be opened shows why (damaged, newer version, or not a valid project, with the problems listed) and what to do. The options are to go back to the open project if there is one, to start a new project, or to go home.

### 3.2 Backend Services

The server is stateless: every request carries the project it needs, and nothing is persisted.

#### 3.2.1 Solver Service

**Purpose:** Perform hydraulic network analysis.

**Endpoints:**

```
POST /api/v1/solve
  Request: Project (port graph, SI)
  Response: SolvedState (flows, pressures, operating points)

POST /api/v1/system-curve
  Request: Project + pump id + flow range
  Response: SystemCurve (flow/head pairs: the pump replaced by each fixed flow, §4.10)
```

**Implementation:** one Global Gradient Algorithm (Todini–Pilati) solver for every topology — the same core method EPANET uses — implemented in Python with Darcy–Weisbach/Colebrook friction from the `fluids` library. See TSD §5. It adds what EPANET lacks:

- Flow-split-dependent K-factors at tees and wyes (outer iteration)
- Real fluid density, viscosity and vapor pressure
- Check, stop-check, PRV, PSV and FCV as components with status logic
- NPSH available at every pump suction
- Later: VFD setpoint control, pressure relief valves, non-ideal reference nodes

Preconditions checked before solving (topology errors): at least one fixed-pressure boundary (reservoir or ideal reference node) per connected sub-network; every port connected or explicitly plugged; no connection between incompatible ports.

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
  // Later: enabledChecks (design checks)
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
  | Reservoir | IdealReferenceNode | Plug
  | TeeBranch | WyeBranch
  | Pump
  | IsolationValve | CheckValve | ControlValve;
  // Later: Tank, NonIdealReferenceNode, CrossBranch, ElbowBranch, ReliefValve, HeatExchanger,
  // Strainer, Orifice, Sprinkler, UserDefinedElement

interface Port {
  id: string;                    // e.g., "suction", "discharge", "branch"
  nominalSize: number;           // m (NPS inches × 0.0254); default size for new connections
  direction: 'inlet' | 'outlet' | 'bidirectional';
  elevation?: number;            // m; inherits the component elevation if not set
}

interface BaseComponent {
  id: string;
  type: 'reservoir' | 'reference_node' | 'plug' | 'branch' | 'pump' | 'valve';
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
  speed: number;                 // fraction of the curve's rated speed, 0 < s ≤ 1, fixed in v1
  status: 'on' | 'off';          // off = closed; a running pump never passes reverse flow
  ports: [ {id: 'suction'}, {id: 'discharge'} ];
  // Later: controlMode ('fixed' | 'pressure' | 'flow'), setpoint, viscosityCorrection
}

interface PumpCurve {
  id: string;
  name: string;
  manufacturer?: string;
  model?: string;
  points: FlowHeadPoint[];                    // ≥ 3 points, flows strictly increasing (m³/s, m)
  efficiencyCurve?: FlowEfficiencyPoint[];    // m³/s, fraction 0–1
  npshrCurve?: FlowNpshrPoint[];              // m³/s, m
}
```

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
  valveType: 'prv' | 'psv' | 'fcv';
  status: 'active' | 'failed_open' | 'failed_closed';
  setpoint: number;              // prv: static gauge Pa at the outlet port; psv: at the inlet port;
                                 // fcv: m³/s
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
  branchResults: Record<string, BranchResult>;     // tee / wye id
  boundaryResults: Record<string, BoundaryResult>; // reservoir, reference node, plug id
  flags: Flag[];
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
interface PumpResult { status: 'running' | 'off' | 'no_flow'; speed; operatingFlow; operatingHead /* EGL rise */;
                       inCurveRange; hydraulicPower; efficiency | null; shaftPower | null;
                       npshAvailable | null; npshRequired | null; npshMargin | null; suctionAbsolutePressure | null;
                       curve: CurvePoint[] /* at speed */; systemCurve: CurvePoint[] | null }
interface ValveResult { valveType; state: 'open' | 'closed' | 'active'; flow; headLoss; pressureDrop; kOpen;
                        referenceDiameter /* inlet pipe */; kEffective | null; cvEffective | null;
                        setpoint | null; setpointAchieved | null }
interface BranchResult { branchType; lossModel; pattern; combinedPortId | null;
                         portFlows /* positive into the component */; kFactors /* per path, on v_c */;
                         pathHeadLosses; referenceVelocity /* v_c */; correlation; inCorrelationRange }
interface BoundaryResult { type: 'reservoir' | 'reference_node' | 'plug'; egl; outflow; portOutflows }
```

Elements in a section closed off from every fixed-pressure boundary carry no flow and have no head: their ports are absent from `nodeResults`, and their pump, valve, branch or boundary result is absent (flagged `ISOLATED_SECTION`).

A section that no fixed-pressure boundary reaches but that cannot sit at zero flow (a pump loop behind a closed valve) carries a determined flow at an undetermined pressure level: its connection, pump, valve and branch results are reported (flows, head losses, pump head and power), its ports are absent from `nodeResults`, `PumpResult.npshAvailable` and `suctionAbsolutePressure` are null, a PRV/PSV there has `setpointAchieved: null`, and an element between it and another head has no result. It is flagged `UNDETERMINED_PRESSURE` (`details.componentIds`).

**System curve** (`PumpResult.systemCurve`, filled for every running pump when `SolveOptions.includeSystemCurve`): `systemCurvePoints` flows from 0 to 1.2 × the curve's largest flow × s; at each, the pump is replaced by that fixed flow and the network solved (other pumps keep running, valves follow their rules); head = EGL(discharge) − EGL(suction). Points whose solve does not converge are left out (`POST /system-curve` reports them, §5.1). The web app solves without it and fetches one pump's curve from `POST /system-curve` when its chart is shown (§3.1.3, D10).

**Flags** (GOALS §4.6, on by default) — `Flag {code, severity, message, componentId, connectionId, portId, details}`. A message names a connection's pipes and fittings as the app numbers them, from 1 ("connection 'L1' pipe 2: …", "fitting 1 (bend)"); `details.segmentIndex` and `details.fittingIndex` are 0-based indexes into `piping.pipes` and `piping.fittings`. Each code has one severity:

| Severity | Codes |
|---|---|
| `invalid` (physically invalid) | `NOT_CONVERGED` (network-wide; `details.componentIds` names oscillating elements), `CAVITATION`, `BELOW_VAPOR_PRESSURE`, `PUMP_FLOW_REVERSAL`, `UNSUPPORTED_FLOW_PATTERN`, `PORT_ABOVE_LIQUID_LEVEL` |
| `warning` (unreliable or incomplete) | `CORRELATION_OUT_OF_RANGE` (friction ranges, Crane K in laminar flow, tee/wye ranges, table limits), `PUMP_OUTSIDE_CURVE` (`details.curve`: head, efficiency or npshr), `TRANSITIONAL_FLOW`, `TEE_PATTERN_FALLBACK`, `UNDETERMINED_PRESSURE` (on the pump or FCV driving the flow; `details.componentIds`: the section), `NPSH_NOT_CHECKED` (a running pump with an NPSHr curve whose NPSH available cannot be computed because the fluid has no vapor pressure: cavitation is not checked) |
| `info` (state) | `NO_VAPOR_PRESSURE` (network-wide), `CHECK_VALVE_CLOSED`, `CONTROL_VALVE_SETPOINT_NOT_MET`, `ISOLATED_SECTION` (`details.componentIds`) |

Every other flag names exactly one component (and port, where it applies) or one connection.

**Trace** (GOALS §4.2; `services/solver/trace.py`): `Trace {elements: Record<id, ElementTrace>, methods: MethodsSummary}`, with one `ElementTrace` for every component and every connection, converged or not:

```typescript
interface ElementTrace {
  elementId: string;
  elementType: 'pipe_connection' | 'reservoir' | 'reference_node' | 'plug' | 'tee' | 'wye' | 'pump'
             | 'isolation_valve' | 'check_valve' | 'control_valve';
  inputs: { name; value: number | string | boolean | null; unit; source: 'user' | 'default' | 'library' | 'computed' }[];
  equations: string[];                         // plain text, every symbol defined
  correlations: { name; citation }[];          // e.g. the fluids call and Crane TP-410 (2009)
  dataSources: { name; citation }[];           // pipe standard, roughness source, CoolProp + reference, p_atm
  intermediates: { name; value: number; unit }[];  // values the solver produced (Re, f, K, v, ΔH, q, NPSHa terms…)
  notes: string[];                             // regime, state and the rule that set it, assumptions, flags
}
```

- **Sources.** `user`: entered (a field set to a value other than its default); `default`: a field holding its model default, whether left out or sent with that value, as the frontend sends every field (e.g. pump speed 1, fitting quantity 1, loss model 'crane'); `library`: pipe tables, correlations, CoolProp, standard constants; `computed`: derived from other inputs (ν = μ/ρ).
- **Units** are SI strings the frontend converts: `m`, `m³/s`, `m/s`, `Pa(g)`, `Pa(a)`, `Pa (difference)`, `kg/m³`, `Pa·s`, `W`; `''` for dimensionless values; others (`m²`, `m²/s`, `m/s²`, `°`, `K`, `US gpm/psi^0.5`) are shown as reported. No trace value is a bare `Pa`.
- **Intermediates restate the results** (same numbers as the result fields) or follow from them by the listed equations (v = Q/A; NPSHa = (EGL_s − z_s) + (p_atm − p_vap)/ρg), so a trace never disagrees with the tables.
- **Numbering.** Pipes and fittings are numbered from 1, as in the app ("Pipe 2 Reynolds number Re", "Fitting 1 (reducer_sudden) position: between pipes 1 and 2"); so are pump-curve points ("Head curve point 4").
- **Content per element type.** Pipe connection: per segment material, schedule/NPS or custom, D and ε with their sources, L, A, v, Re, ε/D, f, regime note with the friction formula and its range, h_f; per fitting type, quantity, K with its fluids call and citation (or "user"), reference diameter, h_j; totals and the EGLs at both ends. Reservoir / reference node: boundary head equation and its inputs, outflow, port pressures, p_atm; the statement that no entrance or exit loss is applied at the boundary unless the connection has an entrance or exit fitting (with the web app's defaults at reservoirs: a sharp-edged entrance and an exit), then, per port, the entrance and exit fittings its connection's piping has. Plug: closed-end equations, EGL and pressure. Tee / wye: loss model, angle, port pipe diameters, pattern, port flows, Q_c, q, β, K per path (Crane or Darby call), v_c, path losses, range / fallback notes. Pump: curve points, fit (PCHIP) and extrapolation, speed and affinity laws, operating point, shutoff head, efficiency and power, NPSHa terms (p_atm and its source, p_vap and its source, z_s, EGL_s, velocity head), NPSHr and margin, status reason, "no viscosity correction applied", the system curve when computed. Valves: resistance as entered (K, Cv, Kv with the ISA conversion) or the Crane default with its call, or the ideal control valve; D_ref; K; both port elevations, the velocities and static pressures at both ports (so Δp follows from the trace); cracking head (active check valves only: a locked valve's law has none); status reason (the user setting, or the EPANET 2.2 rule that holds the state written as the inequality that holds, with its solved values); control valves add the setpoint, H_set with its velocity head, hml, K_eff and Cv_eff. Tee / wye and pump traces give their port elevations and port pressures too; a built-in fluid's temperature (and glycol mass fraction) is an input of every trace that uses its properties.
- **No result.** An element in a closed-off section, or every element of a solve that did not converge, keeps its inputs, equations and sources, with a note saying why it has no values. An element in a section with an undetermined pressure level (`UNDETERMINED_PRESSURE`) keeps its flows and head differences, with a note saying why its EGLs and pressures are missing.

**Methods summary** (`MethodsSummary {methodVersion, sections[{title, items, references}], assumptions, libraries}`; `services/solver/methods.py`): sections Network solution (GGA, Todini & Pilati 1988, tolerances, this solve's iterations), Pipe friction, Minor losses, Branches, Pumps (PCHIP, affinity laws, no viscosity correction, system curves), Valves, Fluid properties, Atmosphere and NPSH, Conventions (SI, gauge, EGL vs HGL, datum, flow signs); global assumptions (steady, incompressible, isothermal, single-phase, quiescent boundaries, no entrance or exit loss at a boundary without an entrance or exit fitting and the web app's default fittings at reservoirs, pump integral check, check-valve model, ideal control-valve default); libraries with versions (opensolve-pipe, fluids, CoolProp, numpy, scipy). Written to be pasted into a deliverable.

---

## 5. Interface Contracts

### 5.1 REST API Specification

All request and response values are SI; JSON is camelCase. The OpenAPI schema (`/openapi.json`, exported by `python -m opensolve_pipe.openapi`) is the contract; the frontend types are generated from it, and the frontend reads its validation from it too: the JSON Schema bounds, and the model rules JSON Schema cannot express, which the models publish as extensions:

| Extension | On | Meaning |
|-----------|----|---------|
| `x-port-ids` | each component schema with fixed ports | The exact port ids of the type |
| `x-port-roles` | the same | Each named port's role (`inlet` / `outlet`) in the type's forward flow direction (pump suction → discharge, valve inlet → outlet, a branch's dividing pattern); it orients new connections, the solver decides the flow |
| `x-port-count` | `IdealReferenceNode` | The exact number of ports where the ids are free |
| `x-required-parameters` | `Fitting` | Fields each fitting type needs (`bend`: `angle`, `radiusRatio`; …) |
| `x-reducer-types`, `x-entrance-types`, `x-exit-types` | `Fitting` | Fittings between two pipes; fittings for the loss where flow leaves or enters a body of liquid |
| `x-setpoint-bounds` | `ControlValve` | Setpoint bounds by valve type where they differ from the field's (`fcv`: a flow, 0–100 m³/s) |

The validators enforce exactly what the extensions state (`tests/unit/test_schema_rules.py`), which also fails while the frontend's copy of the schema (`apps/web/src/lib/api/openapi.json`, `pnpm gen:types`) is out of date.

| Method and path | Request | Response |
|-----------------|---------|----------|
| `POST /api/v1/solve` | `{project, options: {includeSystemCurve, systemCurvePoints}}` | `SolveResponse {success, solvedState, computeTime}` |
| `POST /api/v1/system-curve` | `{project, pumpId, flowMin, flowMax?, numPoints}` | `SystemCurveResponse {pumpId, flowRange, points[{flow, head \| null, converged, message}], converged[]}`: the pump replaced by each fixed flow, other pumps running; default flows 0 to 1.2 × the curve's largest flow × s. The web app's pump chart uses it for the pump being viewed, with the project as solved (D10) |
| `GET /api/v1/fluids` | — | `FluidListResponse {fluids: FluidInfo[]}`: temperature and concentration ranges queried from CoolProp, glycol `freezingPoints` (the lower temperature bound depends on the concentration), vapor-pressure availability, source, notes |
| `POST /api/v1/fluids/properties` | `FluidDefinition` (a `BuiltinFluid` with its temperature, concentration and overrides, or a `CustomFluid`) | `FluidPropertiesResponse {fluid (the built-in id, or 'custom'), properties: FluidProperties}`: the properties as the solver will use them. The fluid travels in the body, which is never logged; the web app uses this endpoint |
| `GET /api/v1/fluids/{id}/properties?temperature=&concentration=` | — | `FluidPropertiesResponse`, for a built-in fluid without overrides. For API users: the server's access log keeps only the path, but the query values (a project's fluid state) travel in the URL, where proxies, CDNs and other intermediaries may log them |
| `POST /api/v1/fluids/custom` | `CustomFluid` | `FluidPropertiesResponse` |
| `GET /api/v1/library` | — | `LibraryResponse {materials (schedules, sizes, dimensions, roughness, sources), fittings (correlation call, reference diameter, source)}` |
| `GET /api/v1/method-versions` | — | `MethodVersionsResponse {current, versions[{version, date, changes}]}` |
| `GET /health` | — | `{status: "healthy"}` |

Solver options that change results (`frictionMethod`, `maxIterations`, `tolerance`) live in `project.settings.solverOptions`, so a link always reproduces its results; request `options` only control extras such as system curves.

#### 5.1.1 Solve Network

```yaml
POST /api/v1/solve
Request:  { "project": <Project>, "options": { "includeSystemCurve": true, "systemCurvePoints": 41 } }

200 OK:   { "success": true, "solvedState": <SolvedState>, "computeTime": 0.012 }
          # non-convergence is also 200, with success = false and solvedState.converged = false

422:      { "success": false, "error": "TOPOLOGY_ERROR",
            "message": "The network cannot be solved: 2 topology issue(s).",
            "issues": [ { "code": "NO_FIXED_HEAD", "message": "...", "componentIds": ["P1"], "connectionIds": [] } ] }
```

#### 5.1.2 Errors

Every error uses `ErrorResponse {success: false, error, message, issues[]}`:

| Status | `error` | When |
|--------|---------|------|
| 400 | `VALIDATION_ERROR` | Request fails the schema, or its body is not readable JSON; one issue per problem with its field path (submitted values are never echoed: no input values, tags or ids in messages, and an unknown key is reported as `(unknown field)`); also an empty system-curve flow range (`EMPTY_FLOW_RANGE`) |
| 400 | `FLUID_ERROR` | Temperature or concentration outside the property source's range |
| 404 | `NOT_FOUND` | Unknown pump id for a system curve (checked before the topology); unknown route |
| 405 | `METHOD_NOT_ALLOWED` | Wrong HTTP method for the route (`Allow` header lists the right one) |
| 413 | `PAYLOAD_TOO_LARGE` | Body over 1 MB |
| 422 | `TOPOLOGY_ERROR` | Port graph cannot be solved (§3.2.1); every issue listed |
| 429 | `RATE_LIMITED` | More than 60 solve or system-curve requests per minute from one client (`Retry-After`) |
| 500 | `INTERNAL_ERROR` | An unexpected failure (logged by type and route only); carries the CORS headers like every error |
| 503 | `SERVER_BUSY` / `TIMEOUT` | The solve pool is full, or this client already has a solve running and one waiting (`Retry-After`); the request's 45 s budget ran out (§7.2) |

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

#### 5.1.4 Export Results (Later)

`POST /api/v1/export` (CSV/XLSX) is Later.

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

- **Longevity.** A link from any released `schemaVersion` must always open. Breaking model changes bump `schemaVersion` (in the API models and in the frontend's `CURRENT_SCHEMA_VERSION`, which a test keeps equal) and add a migration. Migrations are never removed. Each released version keeps a fixture link that a test decodes and pins by SHA-256 (TSD §4.7).
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
- Request bodies up to 1 MB (`PAYLOAD_TOO_LARGE` beyond, whether or not the client declares a length). A project has at most 1,000 components and 2,000 connections, which fits in 1 MB at the sizes the frontend writes (about 230–310 bytes per component, 225–275 per connection); a project with long names or many fittings per connection reaches the byte limit sooner, which is then the effective limit.
- Decoded URL projects validated against the schema before use
- Later: file uploads (CSV, Excel) validated

### 7.2 Rate Limiting

- Solve requests: 60/minute per IP (unauthenticated); a 429 carries `Retry-After`. Behind the hosting platform's proxy the client IP is the proxy's unless uvicorn trusts the proxy's `X-Forwarded-For` (`FORWARDED_ALLOW_IPS` set to the proxy's address range, TSD §11.2); without it all users share one bucket.
- Solver work (`workers.py`): solves run in a pool of 2 worker threads holding at most 6 solves (running or waiting for a thread); a client IP's solves run one at a time, a second waiting for the first (a user solving again before the last result came back); a third concurrent solve from one client, or any solve when the pool is full, is refused at once with 503 `SERVER_BUSY`. Each request has a 45 s wall-clock budget from its arrival (below the frontend's 60 s timeout), checked at every Newton and outer iteration: a solve that runs out returns 503 `TIMEOUT`, and system-curve points not reached are reported as not computed (`message`), the solve itself kept. A client that disconnects cancels its solve. `computeTime` is the solver's own time in the worker, without waiting for it.
- Later: authenticated users get higher limits based on tier

### 7.3 Data Privacy

- v1 stores no project data on the server
- Projects in links travel in the URL fragment and are never sent to or logged by the server
- Solve and system-curve requests carry the project in the request body, and the fluid-properties request the fluid definition; request bodies are not logged. The web app puts no project value in a URL (`GET /fluids/{id}/properties` carries one in its query string; it stays for API users, §5.1)
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

v1: return `converged: false`, no results, and the largest flow and continuity residuals with the components they occur at.

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

### 9.3 Design Checks (Later)

Check library is data-driven:

```typescript
interface DesignCheck {
  id: string;
  name: string;
  category: 'velocity' | 'pressure' | 'npsh' | 'code' | 'custom';
  description: string;
  evaluate: (state: SolvedState, project: Project) => CheckResult[];
}
```

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
