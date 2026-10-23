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

POST /api/v1/goal-seek                  (Later)
  Request: Project + GoalSeekRequest (§4.13), optional scenario id
  Response: GoalSeekResult + SolvedState at the found values
```

`/solve` and `/system-curve` take an optional scenario id (Later, §4.12); the server applies that scenario's overrides to the base before building the network, so the solver only ever sees a plain project.

**Implementation:** one Global Gradient Algorithm (Todini–Pilati) solver for every topology — the same core method EPANET uses — implemented in Python with Darcy–Weisbach/Colebrook friction from the `fluids` library. See TSD §5. It adds what EPANET lacks:

- Flow-split-dependent K-factors at tees and wyes (outer iteration)
- Real fluid density, viscosity and vapor pressure
- Check, stop-check, PRV, PSV and FCV as components with status logic
- NPSH available at every pump suction
- Later: VFD setpoint control, pressure relief valves, non-ideal reference nodes

Preconditions checked before solving (topology errors): at least one fixed-pressure boundary (reservoir or ideal reference node) per connected sub-network, where assigned-flow nodes do not count; every port connected or explicitly plugged; no connection between incompatible ports.

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

**Units:** every numeric field is stored in SI — m, m³/s, Pa, K, kg/m³, Pa·s, m²/s. Pressures are stored as **gauge** Pa; absolute pressure is derived using the project's atmospheric pressure. Elevations are measured from the project datum. The frontend converts to and from the user's display units; the backend never sees display units.

Models are plain JSON-serializable data (no methods, no `Map`s), because they travel in URLs and API requests.

### 4.1 Project Model

```typescript
interface Project {
  schemaVersion: number;          // integer; bumped on every breaking change, see §5.2
  methodVersion: string;          // calculation-method version the project was last solved with;
                                  // used to explain result changes when an old link is reopened (GOALS §4.3)
  id: string;
  metadata: ProjectMetadata;
  settings: ProjectSettings;
  fluid: FluidDefinition;
  components: Component[];
  connections: PipeConnection[];  // edges of the port graph
  pumpLibrary: PumpCurve[];
  scenarios?: Scenario[];         // Later (§4.12); adding it bumps schemaVersion
}

interface ProjectMetadata {
  name: string;
  description?: string;
  created: string;                // ISO 8601
  modified: string;               // ISO 8601
}

interface ProjectSettings {
  units: UnitPreferences;         // display only
  siteElevation: number;          // m above sea level
  atmosphericPressure?: number;   // Pa absolute; overrides the standard-atmosphere value
  solverOptions: SolverOptions;
  enabledChecks: string[];        // Later (design checks)
}
```

Solved results are not part of `Project` and are not stored in the URL; they are recomputed by solving.

### 4.2 Component Model

The component model uses a **port-based architecture**: each component has a defined set of connection ports, and pipe connections link ports between components.

```typescript
type Component =
  | Reservoir
  | ReferenceNode
  | AssignedFlow
  | Branch
  | Plug
  | Pump
  | Valve;
  // Later: Tank, HeatExchanger, Strainer, Orifice, Sprinkler, UserDefinedElement, ThreeWayValve

interface Port {
  id: string;                    // e.g., "suction", "discharge", "branch"
  nominalSize: number;           // nominal diameter, m
  direction: 'inlet' | 'outlet' | 'bidirectional';
  elevation?: number;            // m; inherits the component elevation if not set
}

interface BaseComponent {
  id: string;
  type: ComponentType;
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
  pipes: PipeDefinition[];       // one or more pipe segments, in order from → to
  fittings: Fitting[];           // inline fittings (elbows, reducers, inline valves)
}
```

A port's effective elevation is `port.elevation ?? component.elevation`; this is a helper function, not a field.

Positive flow in a `PipeConnection` runs from `from` to `to`.

### 4.3 Pipe Definition

```typescript
interface PipeDefinition {
  materialId: string;            // key into the pipe materials library
  schedule: string;
  nominalSize: number;           // m (nominal), resolved to an inner diameter from the library
  length: number;                // m
  roughness?: number;            // m; overrides the material roughness
}

interface PipeMaterial {
  id: string;
  name: string;
  roughness: number;             // absolute roughness, m
  schedules: ScheduleData;       // OD/wall lookup, mm in the data file (TSD §4.1)
}
```

### 4.4 Reference Node Model

Reference nodes define pressure boundary conditions for the hydraulic network.

```typescript
interface ReferenceNode extends BaseComponent {
  type: 'reference_node';
  referenceType: 'ideal' | 'non_ideal';
  ports: [Port];                 // single connection port
}

interface IdealReferenceNode extends ReferenceNode {
  referenceType: 'ideal';
  pressure: number;              // Pa gauge, fixed
}

// Later
interface NonIdealReferenceNode extends ReferenceNode {
  referenceType: 'non_ideal';
  pressureFlowCurve: FlowPressurePoint[];
  maxFlow?: number;              // m³/s
}

interface FlowPressurePoint {
  flow: number;                  // m³/s
  pressure: number;              // Pa gauge
}
```

### 4.5 Branch Component Model

Branch components represent fittings where flow splits or combines.

```typescript
type BranchType = 'tee' | 'wye' | 'cross' | 'elbow_branch';   // cross, elbow_branch: Later

interface Branch extends BaseComponent {
  type: 'branch';
  branchType: BranchType;
  ports: Port[];
}

interface TeeBranch extends Branch {
  branchType: 'tee';
  ports: [
    Port & { id: 'run_inlet' },
    Port & { id: 'run_outlet' },
    Port & { id: 'branch' }
  ];
  // Branch port may have a different size than the run ports.
  // Whether flow is diverging or converging is a solver result, not an input.
}

interface WyeBranch extends Branch {
  branchType: 'wye';
  angle: number;                 // degrees (typically 45)
  ports: [
    Port & { id: 'inlet' },
    Port & { id: 'outlet_1' },
    Port & { id: 'outlet_2' }
  ];
}

// Later
interface CrossBranch extends Branch {
  branchType: 'cross';
  ports: [
    Port & { id: 'port_1' },
    Port & { id: 'port_2' },
    Port & { id: 'port_3' },
    Port & { id: 'port_4' }
  ];
}

// Later
interface ElbowBranch extends Branch {
  branchType: 'elbow_branch';
  mainAngle: 45 | 90;
  branchAngle: number;           // degrees
  ports: [
    Port & { id: 'inlet' },
    Port & { id: 'outlet' },
    Port & { id: 'branch' }
  ];
}
```

The tee's diverging/converging behavior is determined from the solved flow directions at each outer iteration, so the user does not set an orientation.

### 4.6 Plug/Cap Model

Plug/Cap components represent closed ends in the piping system with zero flow.

```typescript
interface Plug extends BaseComponent {
  type: 'plug';
  ports: [Port & { id: 'port_1'; direction: 'bidirectional' }];
  // Enforces zero flow at this boundary. Used for dead-end branches,
  // future expansion points, and temporarily closed connections.
}
```

### 4.7 Reservoir and Tank Models

```typescript
interface Reservoir extends BaseComponent {
  type: 'reservoir';
  liquidLevel: number;           // m above the component elevation
  surfacePressure: number;       // Pa gauge on the liquid surface (0 = open to atmosphere)
  ports: Port[];                 // one or more ports (user-defined)
}

// Later: variable-level tank (meaningful for extended-period analysis)
interface Tank extends BaseComponent {
  type: 'tank';
  diameter: number;              // m
  initialLevel: number;          // m
  minLevel: number;              // m
  maxLevel: number;              // m
  ports: Port[];
}
```

### 4.8 Pump Model

```typescript
interface Pump extends BaseComponent {
  type: 'pump';
  curveId: string;               // key into project.pumpLibrary
  speed: number;                 // fraction of rated speed (1.0 = 100%), fixed in v1
  status: 'on' | 'off';          // off = closed, no reverse flow
  ports: [
    Port & { id: 'suction'; direction: 'inlet' },
    Port & { id: 'discharge'; direction: 'outlet' }
  ];
  // Later: controlMode ('fixed' | 'pressure' | 'flow'), setpoint, viscosityCorrection
}

interface PumpCurve {
  id: string;
  name: string;
  manufacturer?: string;
  model?: string;
  points: FlowHeadPoint[];                    // m³/s, m
  efficiencyCurve?: FlowEfficiencyPoint[];    // m³/s, fraction 0–1
  npshrCurve?: FlowHeadPoint[];               // m³/s, m
}

interface FlowHeadPoint {
  flow: number;                  // m³/s
  head: number;                  // m
}
```

### 4.9 Valve Models

```typescript
interface Valve extends BaseComponent {
  type: 'valve';
  valveType: ValveType;
  ports: [
    Port & { id: 'inlet'; direction: 'inlet' },
    Port & { id: 'outlet'; direction: 'outlet' }
  ];
}

type ValveType =
  | 'gate' | 'ball' | 'butterfly' | 'globe'   // isolation / throttling
  | 'check' | 'stop_check'                    // one-way
  | 'prv' | 'psv' | 'fcv'                     // control
  | 'pdcv'                                    // Later: differential-pressure control
  | 'relief';                                 // Later

// Valve resistance exactly as the user entered it (see note below)
interface FlowCoefficient {
  kind: 'K' | 'Cv' | 'Kv';       // K: dimensionless; Cv: US gpm at 1 psi; Kv: m³/h at 1 bar
  value: number;
}

interface IsolationValve extends Valve {
  valveType: 'gate' | 'ball' | 'butterfly' | 'globe';
  status: 'active' | 'isolated';
  position: number;              // fraction open, 0–1
  resistance: FlowCoefficient;   // at full open
}

interface CheckValve extends Valve {
  valveType: 'check' | 'stop_check';
  status: 'active' | 'locked_open' | 'locked_closed';
  resistance: FlowCoefficient;   // when open
  crackingPressure: number;      // Pa
}

interface ControlValve extends Valve {
  valveType: 'prv' | 'psv' | 'fcv';
  status: 'active' | 'failed_open' | 'failed_closed';
  setpoint: number;              // Pa gauge (prv: downstream, psv: upstream) or m³/s (fcv)
                                 // Later, pdcv: Pa pressure drop, inlet minus outlet
  model: 'simplified' | 'detailed';
  cvCurve?: CvPoint[];           // detailed model: flow coefficient vs position
}
```

**Flow coefficients:** manufacturers publish valve capacity as Cv (US gpm at 1 psi ΔP) or Kv (m³/h at 1 bar ΔP), both defined for water. `FlowCoefficient` stores the value in the user's own convention — the one documented exception to SI storage, because Cv and Kv are defined quantities rather than units — and the solver converts it to a loss coefficient K for the connected inner diameter (TSD §5.3).

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

### 4.11 Assigned Flow Model

```typescript
interface AssignedFlow extends BaseComponent {
  type: 'assigned_flow';
  flow: number;                  // m³/s; positive = leaving the network (demand),
                                 // negative = entering it (supply)
  ports: [Port & { id: 'port_1'; direction: 'bidirectional' }];
}
```

The pressure at the port is a result (`NodeResult`), not an input. An assigned-flow node is not a fixed-pressure boundary (§3.2.1). Solver mapping: TSD §4.8.

### 4.12 Scenario Model (Later)

```typescript
interface Scenario {
  id: string;
  name: string;
  description?: string;
  overrides: Override[];         // applied in order on top of the base project
}

interface Override {
  target: { kind: 'component' | 'connection' | 'fluid'; id?: string };
  field: string;                 // camelCase field name on the target, from an allow-list
  value: unknown;                // SI, validated as the field's own type
}
```

Overrides may change values only, never topology (PRD §3.8). An override whose target no longer exists (the base component was deleted) is kept, reported as orphaned and ignored, so the user can see and remove it.

### 4.13 Goal Seek Model (Later)

```typescript
interface GoalSeekRequest {
  variables: GoalVariable[];
  goals: Goal[];                 // same length as variables
  maxIterations?: number;        // outer iterations, default 50
}

interface GoalVariable {
  target: Override['target'];
  field: string;                 // same allow-list as scenario overrides
  lower: number;                 // SI bounds
  upper: number;
}

interface Goal {
  result: 'pressure' | 'flow' | 'pumpHead' | 'npshMargin' | 'velocity';
  key: string;                   // NodeResult / LinkResult / PumpResult key (§4.10)
  target: number;                // SI
  tolerance?: number;            // SI; default from D6 (0.5% or 0.01 m of head)
}

interface GoalSeekResult {
  converged: boolean;
  iterations: number;
  values: Record<string, number>;          // variable values found, keyed by `${id}.${field}`
  achieved: { goal: Goal; value: number; residual: number; met: boolean }[];
}
```

---

## 5. Interface Contracts

### 5.1 REST API Specification

All request and response values are SI. The frontend converts to display units.

#### 5.1.1 Solve Network

```yaml
POST /api/v1/solve
Content-Type: application/json

Request:
{
  "project": <Project>,
  "options": {
    "maxIterations": 100,
    "tolerance": 1e-6,
    "includeSystemCurve": true,
    "flowRange": [0, 0.03]        // m³/s, for system curve
  }
}

Response (200 OK):
{
  "success": true,
  "solvedState": <SolvedState>,
  "computeTime": 0.234           // seconds
}

Response (422 Unprocessable):
{
  "success": false,
  "error": "TOPOLOGY_ERROR",
  "message": "No fixed-pressure boundary in the sub-network containing PUMP-1",
  "details": { ... }
}
```

#### 5.1.2 Get Fluid Properties

```yaml
GET /api/v1/fluids/water/properties?temperature=293.15

Response (200 OK):
{
  "fluid": "water",
  "temperature": 293.15,               // K
  "properties": {
    "density": 998.2,                  // kg/m³
    "dynamicViscosity": 1.002e-3,      // Pa·s
    "kinematicViscosity": 1.004e-6,    // m²/s
    "vaporPressure": 2339              // Pa absolute
  },
  "source": "IAPWS-95"
}
```

#### 5.1.3 Export Results (Later)

```yaml
POST /api/v1/export
Content-Type: application/json

Request:
{
  "project": <Project>,
  "solvedState": <SolvedState>,
  "format": "xlsx",  // or "csv"
  "units": <UnitPreferences>
}

Response (200 OK):
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="opensolve_pipe_results.xlsx"
<binary data>
```

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
