# Software Design Document (SDD)

# OpenSolve Pipe - Web-Based Hydraulic Network Design Tool

**Version:** 0.1.0 (Draft)
**Date:** January 2026
**Status:** Skeleton SDD for Development Planning

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

### 1.3 References

- PRD: Product Requirements Document v0.1.0
- TSD: Technical Specification Document v0.1.0

---

## 2. System Architecture

### 2.1 Architecture Style

**Hybrid Client-Server Architecture**

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENT (Browser)                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   Panel     │  │  Schematic  │  │   Results / Export      │  │
│  │  Navigator  │  │   Viewer    │  │      Components         │  │
│  └──────┬──────┘  └──────┬──────┘  └────────────┬────────────┘  │
│         │                │                      │                │
│  ┌──────┴────────────────┴──────────────────────┴──────────┐    │
│  │                    State Manager                         │    │
│  │            (Component Chain Data Model)                  │    │
│  └──────────────────────────┬───────────────────────────────┘    │
│                             │                                    │
│  ┌──────────────────────────┴───────────────────────────────┐    │
│  │              URL Encoder / Decoder                        │    │
│  │         (Serialization & Compression)                     │    │
│  └──────────────────────────┬───────────────────────────────┘    │
└─────────────────────────────┼───────────────────────────────────┘
                              │ HTTPS
┌─────────────────────────────┼───────────────────────────────────┐
│                         SERVER (Python)                          │
│  ┌──────────────────────────┴───────────────────────────────┐    │
│  │                      API Gateway                          │    │
│  │                  (FastAPI / REST)                         │    │
│  └───────┬─────────────────┬─────────────────┬──────────────┘    │
│          │                 │                 │                   │
│  ┌───────┴──────┐  ┌───────┴──────┐  ┌───────┴──────┐           │
│  │   Solver     │  │   Fluid      │  │   Version    │           │
│  │   Service    │  │   Property   │  │   Control    │           │
│  │              │  │   Service    │  │   Service    │           │
│  └───────┬──────┘  └──────────────┘  └───────┬──────┘           │
│          │                                   │                   │
│  ┌───────┴──────┐                    ┌───────┴──────┐           │
│  │ fluids lib   │                    │   Database   │           │
│  │ WNTR/EPANET  │                    │  (optional)  │           │
│  └──────────────┘                    └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Design Rationale

| Decision | Rationale |
|----------|-----------|
| Hybrid architecture | Client handles UI/state; server handles heavy computation |
| URL-encoded state | Enables sharing without accounts; decentralized by default |
| Component chain model | Matches user mental model and panel navigation pattern |
| Python backend | Leverages existing hydraulic libraries (fluids, WNTR) |
| REST API | Simple, well-understood, future API-ready |

### 2.3 Deployment Model

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   CDN / Static  │     │   API Server    │     │   Database      │
│   Hosting       │     │   (Python)      │     │   (Optional)    │
│                 │     │                 │     │                 │
│  - HTML/CSS/JS  │     │  - FastAPI      │     │  - PostgreSQL   │
│  - Assets       │     │  - Solver       │     │  - User data    │
│                 │     │  - Auth         │     │  - Large proj.  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

---

## 3. Component Design

### 3.1 Frontend Components

#### 3.1.1 Panel Navigator

**Purpose:** Primary interface for building and editing the hydraulic network.

**Structure:**

```
PanelNavigator
├── ElementPanel
│   ├── ElementTypeSelector
│   ├── ElementPropertyForm
│   └── ElementActions (add/delete/navigate)
├── PipingPanel
│   ├── FittingsTable
│   ├── PipeMaterialSelector
│   └── PipeDimensionsForm
├── NavigationControls
│   ├── PreviousButton
│   ├── NextButton
│   ├── BranchSelector (for junctions)
│   └── Breadcrumb
└── MiniMap (optional future feature)
```

**State:**

```typescript
interface NavigatorState {
  currentElementId: string;
  navigationPath: string[];  // Breadcrumb trail
  editMode: 'element' | 'upstream_piping' | 'downstream_piping';
}
```

#### 3.1.2 Schematic Viewer

**Purpose:** Auto-generated process flow diagram for visualization.

**Responsibilities:**

- Render component chain as directed graph
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
- Warnings panel (when checks enabled)

#### 3.1.4 State Manager

**Purpose:** Single source of truth for application state.

**Responsibilities:**

- Manage component chain data model
- Track undo/redo history
- Serialize/deserialize for URL encoding
- Sync with server for versioning

### 3.2 Backend Services

#### 3.2.1 Solver Service

**Purpose:** Perform hydraulic network analysis.

**Endpoints:**

```
POST /api/v1/solve
  Request: NetworkModel (serialized component chain)
  Response: SolvedState (flows, pressures, operating points)

POST /api/v1/system-curve
  Request: NetworkModel + flow range
  Response: SystemCurve (flow/head pairs)
```

**Implementation:**

- Simple networks (single path): Direct calculation using fluids library
- Branching/looped networks: Convert to WNTR model, solve with EPANET

#### 3.2.2 Fluid Property Service

**Purpose:** Provide fluid properties for calculations.

**Endpoints:**

```
GET /api/v1/fluids
  Response: List of available fluids

GET /api/v1/fluids/{fluid_id}/properties?temperature={T}
  Response: FluidProperties (density, viscosity, vapor_pressure)

POST /api/v1/fluids/custom
  Request: CustomFluidDefinition
  Response: FluidProperties (validated)
```

**Data Sources:**

- Built-in library (water, glycols, fuels)
- CoolProp or similar for temperature-dependent properties
- User-defined fluids (stored in project state)

#### 3.2.3 Version Control Service

**Purpose:** Git-like versioning for projects.

**Operations:**
| Operation | Description |
|-----------|-------------|
| `commit` | Save current state as new version |
| `branch` | Create named branch from current state |
| `checkout` | Load specific version or branch |
| `merge` | Combine two branches |
| `history` | List all versions with metadata |

**Storage Strategy:**

- Small projects (< 50KB compressed): URL-encoded, no server storage
- Medium projects: Server storage with URL as reference key
- Large projects: Full server storage with account required

---

## 4. Data Models

### 4.1 Component Chain Model

The primary data structure representing the hydraulic network.

```typescript
interface Project {
  id: string;
  metadata: ProjectMetadata;
  settings: ProjectSettings;
  fluid: FluidDefinition;
  components: Component[];
  pumpLibrary: PumpCurve[];
  results?: SolvedState;
}

interface ProjectMetadata {
  name: string;
  description?: string;
  created: DateTime;
  modified: DateTime;
  version: string;
  parentVersion?: string;  // For branching
}

interface ProjectSettings {
  units: UnitPreferences;
  enabledChecks: string[];
  solverOptions: SolverOptions;
}
```

### 4.2 Component Model

The component model uses a **port-based architecture** where each component has a defined number of connection ports, and pipe connections link ports between components.

```typescript
type Component =
  | Reservoir
  | Tank
  | ReferenceNode
  | Branch
  | Plug
  | Pump
  | Valve
  | HeatExchanger
  | Strainer
  | Orifice
  | Sprinkler
  | UserDefinedElement;

interface Port {
  id: string;                    // e.g., "suction", "discharge", "branch"
  nominalSize: number;           // Nominal diameter in project units
  direction: 'inlet' | 'outlet' | 'bidirectional';
  elevation?: number;            // Optional port-specific elevation (inherits from component if not set)
}

interface BaseComponent {
  id: string;
  type: ComponentType;
  name: string;
  elevation: number;  // In project units
  ports: Port[];      // All connection ports for this component

  // Helper method to get effective port elevation
  // Returns port.elevation if set, otherwise returns component elevation
  getPortElevation(portId: string): number;
}

interface PipeConnection {
  id: string;
  fromComponentId: string;
  fromPortId: string;
  toComponentId: string;
  toPortId: string;
  piping: PipingSegment;         // Pipes and fittings in this connection
}

interface PipingSegment {
  pipes: PipeDefinition[];       // One or more pipe segments
  fittings: Fitting[];           // Inline fittings (elbows, reducers, etc.)
}

// Legacy support: Connection interface for simple downstream linkage
interface Connection {
  targetComponentId: string;
  targetPortId?: string;         // Optional, defaults to first available inlet
  piping?: PipingSegment;
}
```

### 4.3 Pipe Definition

```typescript
interface PipeDefinition {
  material: PipeMaterial;
  nominalDiameter: number;
  schedule: string;
  length: number;
  roughness?: number;  // Override calculated roughness

  // Optional liner
  liner?: {
    material: string;
    thickness: number;
  };
}

interface PipeMaterial {
  id: string;
  name: string;
  roughness: number;  // Absolute roughness in consistent units
  schedule: ScheduleData;  // ID/OD lookup table
}
```

### 4.4 Reference Node Model

Reference nodes define pressure boundary conditions for the hydraulic network.

```typescript
interface ReferenceNode extends BaseComponent {
  type: 'reference_node';
  referenceType: 'ideal' | 'non_ideal';
  ports: [Port];  // Single connection port
}

interface IdealReferenceNode extends ReferenceNode {
  referenceType: 'ideal';
  pressure: number;           // Fixed pressure (in project units)
}

interface NonIdealReferenceNode extends ReferenceNode {
  referenceType: 'non_ideal';
  pressureFlowCurve: FlowPressurePoint[];  // Pressure vs flow rate
  maxFlow?: number;           // Maximum flow capacity
}

interface FlowPressurePoint {
  flow: number;
  pressure: number;
}
```

### 4.5 Branch Component Model

Branch components represent fittings where flow splits or combines (tees, wyes, crosses).

```typescript
type BranchType = 'tee' | 'wye' | 'cross' | 'elbow_branch';

interface Branch extends BaseComponent {
  type: 'branch';
  branchType: BranchType;
  ports: Port[];  // 3 ports for tee/wye, 4 for cross
}

interface TeeBranch extends Branch {
  branchType: 'tee';
  orientation: 'through' | 'converging' | 'diverging';
  ports: [
    Port & { id: 'run_inlet' },
    Port & { id: 'run_outlet' },
    Port & { id: 'branch' }
  ];
  // Branch port may have different size than run ports
}

interface WyeBranch extends Branch {
  branchType: 'wye';
  angle: number;  // Angle of wye in degrees (typically 45°)
  ports: [
    Port & { id: 'inlet' },
    Port & { id: 'outlet_1' },
    Port & { id: 'outlet_2' }
  ];
}

interface CrossBranch extends Branch {
  branchType: 'cross';
  ports: [
    Port & { id: 'port_1' },
    Port & { id: 'port_2' },
    Port & { id: 'port_3' },
    Port & { id: 'port_4' }
  ];
}

interface ElbowBranch extends Branch {
  branchType: 'elbow_branch';
  mainAngle: 45 | 90;         // Main elbow angle
  branchAngle: number;        // Branch takeoff angle
  ports: [
    Port & { id: 'inlet' },
    Port & { id: 'outlet' },
    Port & { id: 'branch' }
  ];
}
```

### 4.6 Plug/Cap Model

Plug/Cap components represent closed ends in the piping system with zero flow.

```typescript
interface Plug extends BaseComponent {
  type: 'plug';
  ports: [Port & { id: 'port_1'; direction: 'bidirectional' }];
  // Plug enforces zero flow at this boundary
  // Useful for:
  // - Dead-end branches
  // - Future expansion points
  // - Temporarily closed connections
}
```

### 4.7 Reservoir and Tank Models

Reservoirs and tanks support multiple connection ports with different sizes.

```typescript
interface Reservoir extends BaseComponent {
  type: 'reservoir';
  waterLevel: number;         // Water surface elevation above component elevation
  ports: Port[];              // One or more ports (user-defined)
}

interface Tank extends BaseComponent {
  type: 'tank';
  diameter: number;
  initialLevel: number;
  minLevel: number;
  maxLevel: number;
  ports: Port[];              // One or more ports with different sizes
}
```

### 4.8 Pump Model

```typescript
interface Pump extends BaseComponent {
  type: 'pump';
  curve: PumpCurve;
  speed: number;  // Fraction of rated speed (1.0 = 100%)
  status: 'on' | 'off';
  npshr?: NPSHRCurve;  // Optional NPSH required curve
  ports: [
    Port & { id: 'suction'; direction: 'inlet' },
    Port & { id: 'discharge'; direction: 'outlet' }
  ];
}

interface PumpCurve {
  id: string;
  name: string;
  manufacturer?: string;
  model?: string;
  points: FlowHeadPoint[];
  efficiencyCurve?: FlowEfficiencyPoint[];  // Optional
}

interface FlowHeadPoint {
  flow: number;
  head: number;
}
```

### 4.9 Valve Models

```typescript
interface Valve extends BaseComponent {
  type: 'valve';
  valveType: ValveType;
  model: 'simplified' | 'detailed';
  ports: [
    Port & { id: 'inlet'; direction: 'inlet' },
    Port & { id: 'outlet'; direction: 'outlet' }
  ];
}

type ValveType =
  | 'gate'
  | 'ball'
  | 'butterfly'
  | 'globe'
  | 'check'
  | 'stop_check'
  | 'prv'    // Pressure Reducing
  | 'psv'    // Pressure Sustaining
  | 'fcv'    // Flow Control
  | 'relief';

// Simplified model (auto-sized)
interface SimplifiedControlValve extends Valve {
  model: 'simplified';
  setpoint: number;  // Pressure or flow depending on type
}

// Detailed model (user-specified Cv)
interface DetailedControlValve extends Valve {
  model: 'detailed';
  setpoint: number;
  cvCurve: CvPoint[];  // Cv vs position
  position?: number;   // Optional fixed position
}
```

### 4.10 Solved State

```typescript
interface SolvedState {
  converged: boolean;
  iterations: number;
  timestamp: DateTime;

  nodeResults: Map<string, NodeResult>;
  linkResults: Map<string, LinkResult>;       // Results for pipe connections
  pumpResults: Map<string, PumpResult>;
  branchResults: Map<string, BranchResult>;   // Flow split/combine results

  warnings: Warning[];
}

interface NodeResult {
  componentId: string;
  pressure: number;        // Static pressure
  dynamicPressure: number;
  totalPressure: number;
  hgl: number;             // Hydraulic grade line
  egl: number;             // Energy grade line
}

interface LinkResult {
  componentId: string;
  flow: number;
  velocity: number;
  headLoss: number;
  reynoldsNumber: number;
  frictionFactor: number;
}

interface PumpResult {
  componentId: string;
  operatingFlow: number;
  operatingHead: number;
  npshAvailable: number;
  npshMargin?: number;     // If NPSH required provided
  efficiency?: number;      // If efficiency curve provided

  systemCurve: FlowHeadPoint[];
}

interface BranchResult {
  componentId: string;
  portFlows: Map<string, number>;      // Flow through each port (positive = into component)
  totalHeadLoss: number;               // Head loss across the branch fitting
  kFactors: Map<string, number>;       // Calculated K-factor for each flow path
}
```

---

## 5. Interface Contracts

### 5.1 REST API Specification

#### 5.1.1 Solve Network

```yaml
POST /api/v1/solve
Content-Type: application/json

Request:
{
  "project": <Project>,
  "options": {
    "maxIterations": 100,
    "tolerance": 0.001,
    "includeSystemCurve": true,
    "flowRange": [0, 500]  // GPM, for system curve
  }
}

Response (200 OK):
{
  "success": true,
  "solvedState": <SolvedState>,
  "computeTime": 0.234  // seconds
}

Response (422 Unprocessable):
{
  "success": false,
  "error": "TOPOLOGY_ERROR",
  "message": "Disconnected component: J-003",
  "details": { ... }
}
```

#### 5.1.2 Get Fluid Properties

```yaml
GET /api/v1/fluids/water/properties?temperature=68&temperatureUnit=F

Response (200 OK):
{
  "fluid": "water",
  "temperature": { "value": 68, "unit": "F" },
  "properties": {
    "density": { "value": 62.32, "unit": "lb/ft³" },
    "kinematicViscosity": { "value": 1.08e-5, "unit": "ft²/s" },
    "dynamicViscosity": { "value": 6.73e-4, "unit": "lb/(ft·s)" },
    "vaporPressure": { "value": 0.339, "unit": "psia" }
  }
}
```

#### 5.1.3 Export Results

```yaml
POST /api/v1/export
Content-Type: application/json

Request:
{
  "project": <Project>,
  "solvedState": <SolvedState>,
  "format": "xlsx",  // or "csv"
  "includeSchematic": true
}

Response (200 OK):
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="opensolve_pipe_results.xlsx"
<binary data>
```

### 5.2 URL State Encoding

**Format:** `https://opensolve-pipe.app/p/{encoded_state}`

**Encoding Process:**

1. Serialize project to JSON
2. Compress with gzip
3. Encode as base64url (URL-safe base64)
4. If > 2000 characters, store server-side and use short reference key

**Example:**

```
https://opensolve-pipe.app/p/H4sIAAAAAAAAA6tWKkktLlGyUlAqS...
```

---

## 6. Integration Patterns

### 6.1 Solver Integration

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Component  │ --> │  Network    │ --> │   Solver    │
│   Chain     │     │  Converter  │     │  Adapter    │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                    ┌──────────────────────────┼──────────────────────────┐
                    │                          │                          │
              ┌─────┴─────┐            ┌───────┴───────┐          ┌───────┴───────┐
              │  Simple   │            │    WNTR /     │          │    Future:    │
              │  Solver   │            │    EPANET     │          │    Custom     │
              │ (fluids)  │            │               │          │    Solver     │
              └───────────┘            └───────────────┘          └───────────────┘
                   │                          │
                   │    Single path,          │    Branching,
                   │    no branches           │    looped networks
                   │                          │
```

### 6.2 K-Factor Resolution

Priority order for fitting K-factors:

1. User-specified value (if provided)
2. Crane TP-410 correlation (if available for fitting type)
3. Fluids library default
4. Error if no value available

```python
def resolve_k_factor(fitting: Fitting, pipe: PipeDefinition, Re: float) -> float:
    if fitting.user_k_factor is not None:
        return fitting.user_k_factor

    if crane_available(fitting.type):
        return crane_k_factor(fitting, pipe.inner_diameter, Re)

    if fluids_available(fitting.type):
        return fluids_k_factor(fitting, pipe.inner_diameter, Re)

    raise ValueError(f"No K-factor available for {fitting.type}")
```

---

## 7. Security Considerations

### 7.1 Input Validation

- All numeric inputs bounded to physical ranges
- String inputs sanitized (component names, etc.)
- File uploads (CSV, Excel) scanned and validated

### 7.2 Rate Limiting

- Solve requests: 60/minute per IP (unauthenticated)
- Authenticated users: Higher limits based on tier

### 7.3 Data Privacy

- No project data stored without user consent
- URL-encoded projects are ephemeral (not server-logged)
- Stored projects encrypted at rest

---

## 8. Error Handling Strategy

### 8.1 Error Categories

| Category | HTTP Code | User Action |
|----------|-----------|-------------|
| Validation Error | 400 | Fix input |
| Topology Error | 422 | Fix model connections |
| Convergence Failure | 200* | Review model, try simpler case |
| Server Error | 500 | Retry / Report |

*Convergence failure returns 200 with `converged: false` in response.

### 8.2 Convergence Failure Handling

Current behavior (per PRD): Return null results with clear indication of failure.

Future enhancement: Provide diagnostic information:

- Last iteration state
- Components with largest residuals
- Suggested troubleshooting steps

---

## 9. Extensibility Points

### 9.1 Component Types

New components can be added by:

1. Defining TypeScript interface extending `BaseComponent`
2. Adding solver adapter for the component type
3. Adding UI panel for configuration
4. Adding schematic symbol

### 9.2 Fluid Library

New fluids can be added via:

1. Built-in library extension (code change)
2. User-defined fluids (runtime, per-project)
3. Future: Global fluid database (user submissions)

### 9.3 Design Checks

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
- Debounced state serialization

### 10.2 Server-Side

- Solver request queuing for fairness
- Caching of fluid properties
- Stateless design for horizontal scaling

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
