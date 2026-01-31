---
name: opensolve-pipe-data-model
description: OpenSolve Pipe component chain data model conventions. Use when creating or modifying components, piping segments, or project structures.
---

# OpenSolve Pipe Data Model Skill

## Component Chain Model

The primary data structure is a **component chain**, NOT a node-link graph.

Each component has:

- `id`: unique identifier (format: `{type}-{number}`, e.g., "pump-1")
- `type`: component type enum
- `name`: user-friendly display name
- `elevation`: in project units
- `ports`: array of Port objects (ADR-007)
- `upstreamPiping`: optional PipingSegment
- `downstreamConnections`: array of Connection objects

## Terminology (ADR-006)

**IMPORTANT:** Use "Components" and "Piping" terminology, NOT "Nodes" and "Links":

| Old Term | New Term |
|----------|----------|
| NodeResult | ComponentResult |
| LinkResult | PipingResult |
| node_results | component_results |
| link_results | piping_results |

## Component Categories

Components are organized into three categories:

### Sources (Boundary Conditions)

- `reservoir` - Infinite supply with fixed head
- `tank` - Finite storage with variable level
- `ideal_reference_node` - Fixed pressure boundary condition
- `non_ideal_reference_node` - Pressure-flow curve boundary

### Connections (Flow Distribution)

- `junction` - General connection point with optional demand
- `tee_branch` - 90° fitting with run_inlet, run_outlet, branch ports
- `wye_branch` - Angled fitting (22.5-60°) for smoother flow
- `cross_branch` - Four-way fitting with perpendicular branches
- `plug` - Dead-end boundary condition (zero flow)

### Equipment (Active Components)

- `pump` - Adds head to system
- `valve` - Controls flow/pressure (gate, ball, check, PRV, PSV, FCV)
- `heat_exchanger` - Fixed pressure drop
- `strainer` - Filtration with pressure drop
- `orifice` - Flow restriction
- `sprinkler` - Discharge point with K-factor

## Port-Based Architecture (ADR-007)

Each component has explicit ports for connections:

```typescript
interface Port {
  id: string;                    // e.g., "inlet", "outlet", "branch"
  nominal_size: number;          // Pipe size at port
  direction: PortDirection;      // "inlet" | "outlet" | "bidirectional"
  elevation?: number;            // Port-specific elevation (optional)
}

type PortDirection = "inlet" | "outlet" | "bidirectional";
```

**Port Elevation Inheritance:**

- If `port.elevation` is set, use that value
- Otherwise, inherit from parent component's `elevation`
- Enables accurate modeling of tall equipment (tanks, vertical pumps)

**Port-to-Port Connections:**

```typescript
interface PipeConnection {
  id: string;
  from_component_id: string;
  from_port_id: string;
  to_component_id: string;
  to_port_id: string;
  piping: PipingSegment;
}
```

### Port Factory Functions

Each component type has a port factory:

```typescript
// Sources
createReservoirPorts(nominalSize: number): Port[]     // outlet
createTankPorts(nominalSize: number): Port[]          // inlet, outlet
createReferenceNodePorts(nominalSize: number): Port[] // bidirectional

// Connections
createJunctionPorts(nominalSize: number, numPorts: number): Port[]
createTeePorts(runSize: number, branchSize?: number): Port[]
createWyePorts(runSize: number, branchSize?: number): Port[]
createCrossPorts(mainSize: number, branchSize?: number): Port[]
createPlugPorts(nominalSize: number): Port[]

// Equipment
createPumpPorts(nominalSize: number): Port[]
createValvePorts(nominalSize: number): Port[]
createHeatExchangerPorts(nominalSize: number): Port[]
createStrainerPorts(nominalSize: number): Port[]
createOrificePorts(nominalSize: number): Port[]
createSprinklerPorts(nominalSize: number): Port[]
```

## Protocol-Based Interfaces (ADR-008)

The backend uses Python `typing.Protocol` for type-safe structural contracts:

### HeadSource Protocol

Components that provide fixed head boundary conditions:

```python
@runtime_checkable
class HeadSource(Protocol):
    """Component providing fixed head boundary condition."""

    @property
    def total_head(self) -> float:
        """Total head at this source (elevation + pressure head)."""
        ...
```

**Implementers:** `IdealReferenceNode`, `NonIdealReferenceNode`, `Reservoir`, `Tank`

### HeadLossCalculator Protocol

Components that cause head loss:

```python
@runtime_checkable
class HeadLossCalculator(Protocol):
    """Component that calculates head loss."""

    def calculate_head_loss(
        self,
        flow: float,
        fluid_properties: FluidProperties,
        pipe_diameter: float
    ) -> float:
        """Calculate head loss through component."""
        ...
```

**Implementers:** `ValveComponent`, `HeatExchanger`, `Strainer`, `Orifice`

### HasPorts Protocol

Components with port-based connections:

```python
@runtime_checkable
class HasPorts(Protocol):
    """Component with explicit ports for connections."""

    ports: list[Port]

    def get_port(self, port_id: str) -> Port | None:
        ...

    def get_port_elevation(self, port_id: str) -> float:
        ...
```

### NetworkSolver Protocol

Solver strategies for different network topologies:

```python
@runtime_checkable
class NetworkSolver(Protocol):
    """Strategy for solving hydraulic networks."""

    def can_solve(self, project: Project) -> bool:
        """Check if this solver can handle the network."""
        ...

    def solve(self, project: Project) -> SolvedState:
        """Solve the network and return results."""
        ...
```

**Implementers:** `SimpleSolver` (single-path), `BranchingSolver` (networks)

## Component ID Conventions

Use consistent naming patterns for automatic ID generation:

- **Pumps:** `pump-1`, `pump-2`, ...
- **Valves:** `valve-1`, `valve-2`, ... (or `valve-prv-1` for specific types)
- **Tanks:** `tank-1`, `reservoir-1`, ...
- **Junctions:** `junction-1`, `junction-2`, ...
- **Reference Nodes:** `ref-ideal-1`, `ref-nonideal-1`, ...
- **Branch Fittings:** `tee-1`, `wye-1`, `cross-1`, ...
- **Heat Exchangers:** `hx-1`, `hx-2`, ...
- **Strainers:** `strainer-1`, `strainer-2`, ...
- **Orifices:** `orifice-1`, `orifice-2`, ...
- **Sprinklers:** `sprinkler-1`, `sprinkler-2`, ...
- **Plugs:** `plug-1`, `plug-2`, ...

**Format:** `{type}-{incrementing-number}`

## PipingSegment Structure

```typescript
interface PipingSegment {
  pipe: {
    material: string,           // Reference to materials library (e.g., "carbon_steel")
    nominalDiameter: number,    // Nominal pipe size (e.g., 2.5, 3, 4, 6)
    schedule: string,           // Pipe schedule (e.g., "40", "80", "160")
    length: number,             // Pipe length in project units
    roughness?: number          // Override if user specifies custom roughness
  },
  fittings: Fitting[]           // Array of fittings in this segment
}
```

## Fitting Structure

```typescript
interface Fitting {
  id: string,                   // Reference to fittings library (e.g., "elbow_90_lr")
  name: string,                 // Display name (e.g., "90° Long Radius Elbow")
  quantity: number,             // Number of this fitting in segment
  kFactor?: number,             // User override for K-factor
  equivalentLengthD?: number    // User override for equivalent length (L/D)
}
```

**Notes:**

- If both `kFactor` and `equivalentLengthD` are provided, `kFactor` takes precedence
- If neither is provided, use library default

## Component Types

### Source Components

**Reservoir:**

```typescript
{
  id: "reservoir-1",
  type: "reservoir",
  name: "Supply Tank",
  elevation: 100,              // ft or m
  waterLevel: 150,             // Total head (elevation + static height)
  ports: [{ id: "outlet", nominal_size: 4, direction: "outlet" }],
  downstreamConnections: [...]
}
```

**Tank:**

```typescript
{
  id: "tank-1",
  type: "tank",
  name: "Storage Tank",
  elevation: 50,
  diameter: 10,                // ft or m
  initialLevel: 10,            // ft or m above tank bottom
  minLevel: 2,
  maxLevel: 12,
  ports: [
    { id: "inlet", nominal_size: 4, direction: "inlet", elevation: 55 },
    { id: "outlet", nominal_size: 4, direction: "outlet", elevation: 50 }
  ],
  upstreamPiping: {...},
  downstreamConnections: [...]
}
```

**Ideal Reference Node:**

```typescript
{
  id: "ref-ideal-1",
  type: "ideal_reference_node",
  name: "Fixed Pressure Boundary",
  elevation: 0,
  pressure: 50,                // Fixed pressure (psi or kPa)
  ports: [{ id: "port", nominal_size: 4, direction: "bidirectional" }]
}
// total_head property: elevation + pressure_head
```

**Non-Ideal Reference Node:**

```typescript
{
  id: "ref-nonideal-1",
  type: "non_ideal_reference_node",
  name: "City Water Main",
  elevation: 0,
  flow_pressure_curve: [       // Pressure vs flow relationship
    { flow: 0, pressure: 60 },
    { flow: 100, pressure: 55 },
    { flow: 200, pressure: 45 }
  ],
  ports: [{ id: "port", nominal_size: 4, direction: "bidirectional" }]
}
// total_head property: interpolates pressure at given flow
```

### Connection Components

**Junction:**

```typescript
{
  id: "junction-1",
  type: "junction",
  name: "Branch Point",
  elevation: 50,
  demand: 0,                   // Optional withdrawal (GPM or L/s)
  ports: [
    { id: "port-1", nominal_size: 4, direction: "bidirectional" },
    { id: "port-2", nominal_size: 4, direction: "bidirectional" }
  ],
  upstreamPiping: {...},
  downstreamConnections: [...]
}
```

**Tee Branch:**

```typescript
{
  id: "tee-1",
  type: "tee_branch",
  name: "Tee Fitting",
  elevation: 50,
  ports: [
    { id: "run_inlet", nominal_size: 4, direction: "inlet" },
    { id: "run_outlet", nominal_size: 4, direction: "outlet" },
    { id: "branch", nominal_size: 2, direction: "bidirectional" }  // Reduced size
  ]
}
```

**Wye Branch:**

```typescript
{
  id: "wye-1",
  type: "wye_branch",
  name: "45° Wye",
  elevation: 50,
  branch_angle: 45,            // 22.5 to 60 degrees
  ports: [
    { id: "run_inlet", nominal_size: 4, direction: "inlet" },
    { id: "run_outlet", nominal_size: 4, direction: "outlet" },
    { id: "branch", nominal_size: 4, direction: "bidirectional" }
  ]
}
```

**Cross Branch:**

```typescript
{
  id: "cross-1",
  type: "cross_branch",
  name: "Cross Fitting",
  elevation: 50,
  ports: [
    { id: "main_inlet", nominal_size: 4, direction: "inlet" },
    { id: "main_outlet", nominal_size: 4, direction: "outlet" },
    { id: "branch_a", nominal_size: 2, direction: "bidirectional" },
    { id: "branch_b", nominal_size: 2, direction: "bidirectional" }
  ]
}
```

**Plug:**

```typescript
{
  id: "plug-1",
  type: "plug",
  name: "Dead End",
  elevation: 50,
  ports: [{ id: "port", nominal_size: 4, direction: "inlet" }]
}
// Boundary condition: zero flow
```

### Equipment Components

**Pump:**

```typescript
{
  id: "pump-1",
  type: "pump",
  name: "Primary Pump",
  elevation: 50,
  curve: {
    id: "curve-1",
    name: "Grundfos CR10-5",
    manufacturer: "Grundfos",
    model: "CR10-5",
    rated_speed: 3500,
    points: [
      { flow: 0, head: 150 },
      { flow: 100, head: 145 },
      { flow: 200, head: 130 }
    ],
    efficiency_curve: [        // Optional
      { flow: 0, efficiency: 0 },
      { flow: 100, efficiency: 0.75 },
      { flow: 200, efficiency: 0.65 }
    ]
  },
  operating_mode: "fixed_speed",    // PumpOperatingMode enum
  status: "running",                 // PumpStatus enum
  speed: 1.0,                        // Fraction of rated speed
  control_setpoint: null,            // For controlled modes
  viscosity_correction_enabled: true,
  ports: [
    { id: "inlet", nominal_size: 4, direction: "inlet" },
    { id: "outlet", nominal_size: 4, direction: "outlet" }
  ],
  upstreamPiping: {...},
  downstreamConnections: [...]
}
```

**Pump Operating Modes:**

```typescript
type PumpOperatingMode =
  | "fixed_speed"           // Runs at constant speed
  | "variable_speed"        // VFD adjusts speed to maintain curve
  | "controlled_pressure"   // VFD maintains discharge pressure setpoint
  | "controlled_flow"       // VFD maintains flow setpoint
  | "off";                  // Pump is off
```

**Pump Status:**

```typescript
type PumpStatus =
  | "running"       // Pump is running
  | "off_check"     // Off, check valve prevents backflow
  | "off_no_check"  // Off, allows backflow
  | "locked_out";   // Administratively disabled
```

**Valve:**

```typescript
{
  id: "valve-prv-1",
  type: "valve",
  valveType: "prv",            // "gate", "ball", "check", "prv", "psv", "fcv"
  name: "Pressure Reducing Valve",
  elevation: 50,
  model: "simplified",         // "simplified" or "detailed"
  setpoint: 60,                // Target pressure (psi or kPa)
  status: "active",            // ValveStatus enum
  ports: [
    { id: "inlet", nominal_size: 4, direction: "inlet" },
    { id: "outlet", nominal_size: 4, direction: "outlet" }
  ],
  upstreamPiping: {...},
  downstreamConnections: [...]
}
```

**Valve Status:**

```typescript
type ValveStatus =
  | "active"        // Normal operation
  | "isolated"      // Closed for isolation
  | "failed_open"   // Failure mode - stuck open
  | "failed_closed" // Failure mode - stuck closed
  | "locked_open";  // Administratively locked open
```

**Heat Exchanger:**

```typescript
{
  id: "hx-1",
  type: "heat_exchanger",
  name: "Plate HX",
  elevation: 50,
  pressure_drop: 5,            // Fixed pressure drop (psi or kPa)
  ports: [
    { id: "inlet", nominal_size: 4, direction: "inlet" },
    { id: "outlet", nominal_size: 4, direction: "outlet" }
  ],
  upstreamPiping: {...},
  downstreamConnections: [...]
}
// Implements HeadLossCalculator protocol
```

## Solver Results

### Enhanced Pump Results

```typescript
interface PumpResult {
  component_id: string;
  operating_flow: number;
  operating_head: number;
  efficiency?: number;
  power?: number;
  npsh_available?: number;
  npsh_margin?: number;
  status: PumpStatus;
  actual_speed: number;                          // Actual speed (may differ from setpoint)
  viscosity_correction_applied: boolean;
  viscosity_correction_factors?: ViscosityCorrectionFactors;
}

interface ViscosityCorrectionFactors {
  c_q: number;   // Flow correction per ANSI/HI 9.6.7
  c_h: number;   // Head correction
  c_eta: number; // Efficiency correction
}
```

### Control Valve Results

```typescript
interface ControlValveResult {
  component_id: string;
  valve_type: string;
  status: ValveStatus;
  setpoint: number;
  actual_value: number;
  position: number;            // 0-100% open
  pressure_drop: number;
}
```

### Solved State

```typescript
interface SolvedState {
  success: boolean;
  component_results: Record<string, ComponentResult>;
  piping_results: Record<string, PipingResult>;
  pump_results: Record<string, PumpResult>;
  control_valve_results: Record<string, ControlValveResult>;
  warnings: Warning[];
  solve_time_ms: number;
}
```

## Validation Rules

1. **Every component must have unique id**
   - No duplicate IDs in component array
   - IDs must follow naming convention

2. **Reservoir/Tank must be at start or end of chain**
   - Reservoir typically at start (infinite source)
   - Tank typically at end (discharge point)

3. **Pump must have at least one downstream connection**
   - Cannot be a dead end
   - Must pump to somewhere

4. **Branching requires appropriate component**
   - Junction, TeeBranch, WyeBranch, or CrossBranch
   - Each branch modeled explicitly via ports

5. **Loops must have at least one pump**
   - Cannot have loop without active component
   - Network solver handles loop balancing

6. **Piping segments must reference valid materials/fittings**
   - Material ID must exist in `pipe_materials.json`
   - Fitting ID must exist in `fittings.json`

7. **Port connections must be compatible**
   - Port sizes should match or use reducers
   - Inlet connects to outlet (direction check)

8. **Controlled pump modes require setpoints**
   - `controlled_pressure` and `controlled_flow` need `control_setpoint`

9. **Physical constraints**
   - Elevations must be positive (or allow negative with datum reference)
   - Pipe lengths must be positive
   - Diameters must be positive
   - Flow rates must be non-negative (negative = reverse flow)

## Solver Conversion

### Simple Solver (Single Path)

- Walks component chain in order
- Calculates head loss cumulatively
- Uses HeadLossCalculator protocol for components
- Finds operating point by intersecting pump and system curves

### Network Solver (Branching/Looped)

- Converts component chain to WNTR node-link graph
- Uses SolverRegistry to select appropriate strategy
- Components: Uses protocol checks (HeadSource, HeadLossCalculator)
- WNTR/EPANET solves for pressures and flows

## Adding New Component Types

When adding a new component type, follow these steps:

1. **Add to ComponentType enum**

   ```typescript
   type ComponentType =
     | "reservoir"
     | "tank"
     | "ideal_reference_node"
     | "non_ideal_reference_node"
     | "junction"
     | "tee_branch"
     | "wye_branch"
     | "cross_branch"
     | "plug"
     | "pump"
     | "valve"
     | "heat_exchanger"
     | "strainer"
     | "orifice"
     | "sprinkler"
   ```

2. **Create interface extending BaseComponent**

   ```typescript
   interface NewComponent extends BaseComponent {
     type: "new_component";
     ports: Port[];
     // Component-specific properties
   }
   ```

3. **Implement protocols if applicable**
   - `HeadSource` for boundary conditions
   - `HeadLossCalculator` for components causing head loss
   - `HasPorts` for port-based connections

4. **Add port factory function**

   ```typescript
   export function createNewComponentPorts(size: number): Port[] {
     return [
       { id: 'inlet', nominal_size: size, direction: 'inlet' },
       { id: 'outlet', nominal_size: size, direction: 'outlet' }
     ];
   }
   ```

5. **Add to solver adapter**
   - `simple.py`: Add component handling in chain walker
   - `network.py`: Add conversion to WNTR equivalent
   - Use protocol checks where applicable

6. **Add UI panel**
   - `apps/web/src/lib/components/panel/NewComponentPanel.svelte`

7. **Add schematic symbol**
   - `apps/web/static/symbols/new_component.svg`

8. **Update data schema**
   - Add to `apps/api/src/opensolve_pipe/models/components.py`
   - Add to `apps/web/src/lib/models/components.ts`

9. **Document in this skill file**
   - Add to component types section
   - Add validation rules if applicable

## Example: Simple Single-Path System

```typescript
{
  id: "project-1",
  metadata: {...},
  settings: {...},
  fluid: { id: "water", temperature: 68 },
  components: [
    {
      id: "reservoir-1",
      type: "reservoir",
      name: "Supply Reservoir",
      elevation: 0,
      waterLevel: 100,
      ports: [{ id: "outlet", nominal_size: 4, direction: "outlet" }],
      downstreamConnections: [
        {
          targetComponentId: "pump-1",
          targetPortId: "inlet",
          piping: {
            pipe: {
              material: "carbon_steel",
              nominalDiameter: 4,
              schedule: "40",
              length: 20
            },
            fittings: [
              { id: "entrance_rounded", name: "Pipe Entrance", quantity: 1 }
            ]
          }
        }
      ]
    },
    {
      id: "pump-1",
      type: "pump",
      name: "Main Pump",
      elevation: 0,
      curve: {...},
      operating_mode: "fixed_speed",
      status: "running",
      speed: 1.0,
      ports: [
        { id: "inlet", nominal_size: 4, direction: "inlet" },
        { id: "outlet", nominal_size: 4, direction: "outlet" }
      ],
      upstreamPiping: null,
      downstreamConnections: [
        {
          targetComponentId: "tank-1",
          targetPortId: "inlet",
          piping: {
            pipe: {
              material: "carbon_steel",
              nominalDiameter: 4,
              schedule: "40",
              length: 100
            },
            fittings: [
              { id: "elbow_90_lr", name: "90° Elbow", quantity: 3 },
              { id: "gate_valve", name: "Gate Valve", quantity: 1 }
            ]
          }
        }
      ]
    },
    {
      id: "tank-1",
      type: "tank",
      name: "Elevated Tank",
      elevation: 50,
      diameter: 10,
      initialLevel: 10,
      minLevel: 2,
      maxLevel: 12,
      ports: [
        { id: "inlet", nominal_size: 4, direction: "inlet", elevation: 55 },
        { id: "outlet", nominal_size: 4, direction: "outlet", elevation: 50 }
      ],
      upstreamPiping: null,
      downstreamConnections: []
    }
  ]
}
```

## Common Patterns

### Parallel Pumps

```typescript
// Use junction or tee to split flow
{
  id: "junction-1",
  type: "junction",
  name: "Pump Suction Header",
  ports: [
    { id: "inlet", nominal_size: 6, direction: "inlet" },
    { id: "outlet-1", nominal_size: 4, direction: "outlet" },
    { id: "outlet-2", nominal_size: 4, direction: "outlet" }
  ],
  downstreamConnections: [
    { targetComponentId: "pump-1", targetPortId: "inlet", piping: {...} },
    { targetComponentId: "pump-2", targetPortId: "inlet", piping: {...} }
  ]
}
// Both pumps discharge to junction-2
```

### Series Pumps

```typescript
// pump-1 → piping → pump-2 → piping → tank
```

### Bypass Loop with Tee

```typescript
{
  id: "tee-1",
  type: "tee_branch",
  name: "HX Bypass Tee",
  ports: [
    { id: "run_inlet", nominal_size: 4, direction: "inlet" },
    { id: "run_outlet", nominal_size: 4, direction: "outlet" },
    { id: "branch", nominal_size: 4, direction: "outlet" }
  ],
  downstreamConnections: [
    { targetComponentId: "hx-1", targetPortId: "inlet", piping: {...} },
    { targetComponentId: "valve-bypass", targetPortId: "inlet", piping: {...} }
  ]
}
// Both paths rejoin at tee-2
```

### Dead End with Plug

```typescript
{
  id: "plug-1",
  type: "plug",
  name: "Future Connection",
  elevation: 50,
  ports: [{ id: "port", nominal_size: 2, direction: "inlet" }]
}
// Zero flow boundary condition
```

## Best Practices

1. **Use port-based connections for clarity**
   - Explicit port IDs prevent connection errors
   - Port elevations enable accurate static head

2. **Implement protocols for new components**
   - HeadSource for boundaries
   - HeadLossCalculator for equipment
   - Enables solver to handle automatically

3. **Keep component chains simple for MVP**
   - Start with single-path systems
   - Add branching with explicit branch components

4. **Use descriptive names**
   - IDs are programmatic (`pump-1`)
   - Names are user-facing (`"Primary Circulation Pump"`)

5. **Store piping with downstream connection**
   - Piping belongs to the connection, not the component
   - Include target port ID for explicit routing

6. **Validate early**
   - Check component chain validity before solving
   - Validate port compatibility
   - Provide clear error messages

7. **Preserve user intent**
   - Don't auto-modify user's component chain
   - Warn about issues, don't silently fix

8. **Handle edge cases**
   - Zero-length pipes (K-factors only)
   - Closed valves (infinite K or disconnect)
   - Empty tanks (warning, don't crash)
   - Controlled pumps at limits (clamp, warn)

## Related ADRs

- **ADR-006:** Components/Piping terminology (replaces Nodes/Links)
- **ADR-007:** Port-based architecture with elevation inheritance
- **ADR-008:** Protocol-based interfaces for type-safe contracts
