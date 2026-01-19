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
- `upstreamPiping`: optional PipingSegment
- `downstreamConnections`: array of Connection objects

## Component ID Conventions

Use consistent naming patterns for automatic ID generation:

- **Pumps:** `pump-1`, `pump-2`, ...
- **Valves:** `valve-1`, `valve-2`, ... (or `valve-prv-1` for specific types)
- **Tanks:** `tank-1`, `reservoir-1`, ...
- **Junctions:** `junction-1`, `junction-2`, ...
- **Heat Exchangers:** `hx-1`, `hx-2`, ...
- **Strainers:** `strainer-1`, `strainer-2`, ...
- **Orifices:** `orifice-1`, `orifice-2`, ...
- **Sprinklers:** `sprinkler-1`, `sprinkler-2`, ...

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

### Node Types (Boundary Conditions)

**Reservoir:**
```typescript
{
  id: "reservoir-1",
  type: "reservoir",
  name: "Supply Tank",
  elevation: 100,              // ft or m
  waterLevel: 150,             // Total head (elevation + static height)
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
  upstreamPiping: {...},
  downstreamConnections: [...]
}
```

**Junction:**
```typescript
{
  id: "junction-1",
  type: "junction",
  name: "Branch Point",
  elevation: 50,
  demand: 0,                   // Optional withdrawal (GPM or L/s)
  upstreamPiping: {...},
  downstreamConnections: [     // Multiple connections for branching
    { targetComponentId: "pipe-2", piping: {...} },
    { targetComponentId: "pipe-3", piping: {...} }
  ]
}
```

### Link Types (Active Components)

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
    points: [
      { flow: 0, head: 150 },
      { flow: 100, head: 145 },
      { flow: 200, head: 130 },
      // ... more points
    ],
    efficiencyCurve?: [...]    // Optional
  },
  speed: 1.0,                  // Fraction of rated speed (1.0 = 100%)
  status: "on",                // "on" or "off"
  npshr?: [...],               // Optional NPSH required curve
  upstreamPiping: {...},
  downstreamConnections: [...]
}
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
  upstreamPiping: {...},
  downstreamConnections: [...]
}
```

**Heat Exchanger:**
```typescript
{
  id: "hx-1",
  type: "heat_exchanger",
  name: "Plate HX",
  elevation: 50,
  pressureDrop: 5,             // Fixed pressure drop (psi or kPa)
  upstreamPiping: {...},
  downstreamConnections: [...]
}
```

## Connection Structure

```typescript
interface Connection {
  targetComponentId: string,   // ID of downstream component
  piping: PipingSegment        // Piping between this component and target
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

4. **Branching requires Junction component**
   - Junction has multiple downstream connections
   - Each branch modeled explicitly

5. **Loops must have at least one pump**
   - Cannot have loop without active component
   - Network solver handles loop balancing

6. **Piping segments must reference valid materials/fittings**
   - Material ID must exist in `pipe_materials.json`
   - Fitting ID must exist in `fittings.json`

7. **Physical constraints**
   - Elevations must be positive (or allow negative with datum reference)
   - Pipe lengths must be positive
   - Diameters must be positive
   - Flow rates must be non-negative (negative = reverse flow)

## Solver Conversion

### Simple Solver (Single Path)
- Walks component chain in order
- Calculates head loss cumulatively
- Finds operating point by intersecting pump and system curves

### Network Solver (Branching/Looped)
- Converts component chain to WNTR node-link graph
- Nodes: Reservoirs, Tanks, Junctions (implicit nodes created at pumps/valves)
- Links: Pipes (with equivalent K for fittings), Pumps, Valves
- WNTR/EPANET solves for pressures and flows

## Adding New Component Types

When adding a new component type, follow these steps:

1. **Add to ComponentType enum**
   ```typescript
   type ComponentType =
     | "reservoir"
     | "tank"
     | "junction"
     | "pump"
     | "valve"
     | "heat_exchanger"
     | "strainer"          // ← New type
     | ...
   ```

2. **Create interface extending BaseComponent**
   ```typescript
   interface Strainer extends BaseComponent {
     type: "strainer";
     meshSize: number;        // Mesh opening size
     cleanPressureDrop: number;  // Clean pressure drop
     dirtyPressureDrop: number;  // Dirty pressure drop (for warnings)
   }
   ```

3. **Add to solver adapter**
   - `simple.py`: Add component handling in chain walker
   - `network.py`: Add conversion to WNTR equivalent

4. **Add UI panel**
   - `apps/web/src/lib/components/panel/StrainerPanel.svelte`

5. **Add schematic symbol**
   - `apps/web/static/symbols/strainer.svg`

6. **Update data schema**
   - Add to `apps/api/src/opensolve_pipe/models/components.py`
   - Add to `apps/web/src/lib/models/components.ts`

7. **Document in this skill file**
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
      downstreamConnections: [
        {
          targetComponentId: "pump-1",
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
      speed: 1.0,
      status: "on",
      upstreamPiping: null,  // Connected via reservoir's downstream
      downstreamConnections: [
        {
          targetComponentId: "tank-1",
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
      upstreamPiping: null,  // Connected via pump's downstream
      downstreamConnections: []
    }
  ]
}
```

## Common Patterns

### Parallel Pumps
```typescript
{
  id: "junction-1",
  type: "junction",
  name: "Pump Suction Header",
  downstreamConnections: [
    { targetComponentId: "pump-1", piping: {...} },
    { targetComponentId: "pump-2", piping: {...} }
  ]
},
// Both pumps discharge to junction-2
```

### Series Pumps
```typescript
// pump-1 → piping → pump-2 → piping → tank
```

### Bypass Loop
```typescript
{
  id: "junction-1",
  downstreamConnections: [
    { targetComponentId: "hx-1", piping: {...} },      // Main path
    { targetComponentId: "valve-bypass", piping: {...} } // Bypass path
  ]
}
// Both paths rejoin at junction-2
```

## Best Practices

1. **Keep component chains simple for MVP**
   - Start with single-path systems
   - Add branching in Phase 2

2. **Use descriptive names**
   - IDs are programmatic (`pump-1`)
   - Names are user-facing (`"Primary Circulation Pump"`)

3. **Store piping with downstream connection**
   - Piping belongs to the connection, not the component
   - Makes chain traversal cleaner

4. **Validate early**
   - Check component chain validity before solving
   - Provide clear error messages

5. **Preserve user intent**
   - Don't auto-modify user's component chain
   - Warn about issues, don't silently fix

6. **Handle edge cases**
   - Zero-length pipes (K-factors only)
   - Closed valves (infinite K or disconnect)
   - Empty tanks (warning, don't crash)
