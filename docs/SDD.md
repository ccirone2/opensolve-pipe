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

#### 3.1.1 Panel Navigator

**Purpose:** Primary interface for building and editing the hydraulic network.

**Structure:**

```
PanelNavigator
├── ComponentPanel
│   ├── ComponentTypeSelector
│   ├── ComponentPropertyForm
│   └── ComponentActions (add before/after, add branch, delete)
├── ConnectionPanel               // piping of a connection at the current component
│   ├── PortSelector              // which port's connection is being edited
│   ├── PipeSegmentsForm          // material, schedule, diameter, length
│   └── FittingsTable
├── NavigationControls
│   ├── PreviousButton
│   ├── NextButton
│   ├── PathChooser               // shown when more than one way forward
│   └── Breadcrumb
└── MiniMap (Later)
```

**Navigation over the port graph:**

- The walk starts at a chosen component (default: the first boundary component, i.e. a reservoir or reference node).
- **Next** follows a connection from the current component to a component not yet on the breadcrumb. If there is more than one candidate (a tee, a multi-port reservoir), the **PathChooser** asks which one to follow.
- **Previous** steps back along the breadcrumb.
- When a loop leads back to a component already on the breadcrumb, Next offers to jump to it rather than extend the path.
- Every component is reachable by choosing paths, or directly from the results tables.

**State:**

```typescript
interface NavigatorState {
  startComponentId: string;
  path: NavigationStep[];        // breadcrumb; last step is the current component
  editMode: 'component' | 'connection';
  activePortId?: string;         // port whose connection is shown in ConnectionPanel
}

interface NavigationStep {
  componentId: string;
  viaConnectionId?: string;      // connection used to arrive here (absent for the start)
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

**Purpose:** Display solved network state and analysis outputs.

**Views:**

- Summary (operating points, key metrics)
- Node table (pressures, HGL, EGL)
- Link table (flows, velocities, head loss)
- Pump curve graph with system curve overlay
- Validity flags (v1): cavitation, pump flow reversal, out-of-range correlations, non-convergence
- Calculation trace per element: inputs, equations, correlations and data sources used
- Methods-and-assumptions summary for the whole project
- Design-check warnings (Later, opt-in)

#### 3.1.4 State Manager

**Purpose:** Single source of truth for application state.

**Responsibilities:**

- Hold the port-graph project model (SI values)
- Track undo/redo history within the session
- Convert between SI and the user's display units at input and display time
- Serialize/deserialize the project to and from the URL fragment, applying schema migrations on load
- Later: sync with the server for accounts and version history

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
  Response: SystemCurve (flow/head pairs)
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

GET /api/v1/fluids/{fluid_id}/properties?temperature={T_K}
  Response: FluidProperties (density, viscosity, vapor_pressure), SI

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

An ideal reference node is modeled like a reservoir: a body of liquid at rest at the given gauge pressure at the port elevation, so its energy grade line is fixed at `z + p/(ρg)`. Velocity head develops in the connecting piping; add entrance or exit fittings to model the transition.

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

```typescript
interface SolvedState {
  converged: boolean;
  iterations: number;
  timestamp: string;             // ISO 8601

  nodeResults: Record<string, NodeResult>;      // keyed by `${componentId}:${portId}`
  linkResults: Record<string, LinkResult>;      // keyed by connection id
  pumpResults: Record<string, PumpResult>;      // keyed by component id
  valveResults: Record<string, ValveResult>;    // keyed by component id
  branchResults: Record<string, BranchResult>;  // keyed by component id

  warnings: Warning[];
}

interface NodeResult {
  pressure: number;              // Pa gauge (static)
  dynamicPressure: number;       // Pa
  totalPressure: number;         // Pa gauge
  hgl: number;                   // m
  egl: number;                   // m
}

interface LinkResult {
  flow: number;                  // m³/s, positive from → to
  velocity: number;              // m/s
  headLoss: number;              // m
  reynoldsNumber: number;
  frictionFactor: number;
}

interface PumpResult {
  operatingFlow: number;         // m³/s
  operatingHead: number;         // m
  npshAvailable: number;         // m
  npshMargin?: number;           // m, if an NPSHr curve is provided
  efficiency?: number;           // fraction, if an efficiency curve is provided
  power?: number;                // W, if an efficiency curve is provided
  systemCurve: FlowHeadPoint[];
}

interface ValveResult {
  state: 'active' | 'open' | 'closed';  // solved state of a status-changing valve
  setpointAchieved?: boolean;
  position?: number;             // fraction open (detailed model)
}

interface BranchResult {
  portFlows: Record<string, number>;   // m³/s, positive = into the component
  totalHeadLoss: number;               // m
  kFactors: Record<string, number>;    // K for each flow path
}
```

---

## 5. Interface Contracts

### 5.1 REST API Specification

All request and response values are SI; JSON is camelCase. The OpenAPI schema (`/openapi.json`, exported by `python -m opensolve_pipe.openapi`) is the contract; the frontend types are generated from it.

| Method and path | Request | Response |
|-----------------|---------|----------|
| `POST /api/v1/solve` | `{project, options: {includeSystemCurve, systemCurvePoints}}` | `SolveResponse {success, solvedState, computeTime}` |
| `POST /api/v1/system-curve` | `{project, pumpId, flowMin, flowMax?, numPoints}` | `SystemCurveResponse {pumpId, points, converged[]}` |
| `GET /api/v1/fluids` | — | `FluidListResponse {fluids: FluidInfo[]}` (ranges, vapor-pressure availability, source) |
| `GET /api/v1/fluids/{id}/properties?temperature=&concentration=` | — | `FluidPropertiesResponse {fluid, properties: FluidProperties}` |
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
| 400 | `VALIDATION_ERROR` | Request fails the schema; one issue per problem with its field path (submitted values are never echoed) |
| 400 | `FLUID_ERROR` | Temperature or concentration outside the property source's range |
| 404 | `NOT_FOUND` | Unknown pump id for a system curve |
| 413 | `PAYLOAD_TOO_LARGE` | Body over 1 MB |
| 422 | `TOPOLOGY_ERROR` | Port graph cannot be solved (§3.2.1); every issue listed |
| 429 | `RATE_LIMITED` | More than 60 solve or system-curve requests per minute from one client |

#### 5.1.3 Get Fluid Properties

```yaml
GET /api/v1/fluids/water/properties?temperature=293.15
200 OK: { "fluid": "water",
          "properties": { "name": "Water", "temperature": 293.15, "density": …, "dynamicViscosity": …,
                          "kinematicViscosity": …, "vaporPressure": …,
                          "sources": { "density": { "origin": "library", "citation": "CoolProp … IAPWS-95 …" }, … } } }
```

#### 5.1.4 Export Results (Later)

`POST /api/v1/export` (CSV/XLSX) is Later.

### 5.2 URL State Encoding

**Format:** `https://opensolve-pipe.app/p#{encoded_state}`

The project travels in the URL **fragment** (after `#`). Browsers never send the fragment to the server, so project data does not appear in server or CDN logs.

**Encoding Process:**

1. Serialize the project to canonical JSON (keys sorted at every level)
2. Compress with gzip
3. Encode as base64url (URL-safe base64, no padding)

**Decoding Process:**

1. base64url decode → gunzip → JSON parse
2. Read `schemaVersion`; apply migrations in order up to the current version
3. Validate against the current schema

**Rules:**

- A link from any released `schemaVersion` must always open. Breaking model changes bump `schemaVersion` and add a migration; migrations are never removed.
- A link from a newer `schemaVersion` than the app knows shows a clear error, not a partial load.
- When the full URL exceeds 8,000 characters, the UI warns that some email and chat clients may truncate it.
- No server-side fallback in v1 (Later: short links backed by storage).

**Example:**

```
https://opensolve-pipe.app/p#H4sIAAAAAAAAA6tWKkktLlGyUlAqS...
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
- Request size limit on solve requests
- Decoded URL projects validated against the schema before use
- Later: file uploads (CSV, Excel) validated

### 7.2 Rate Limiting

- Solve requests: 60/minute per IP (unauthenticated)
- Later: authenticated users get higher limits based on tier

### 7.3 Data Privacy

- v1 stores no project data on the server
- Projects in links travel in the URL fragment and are never sent to or logged by the server
- Solve requests carry the project in the request body; request bodies are not logged
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
