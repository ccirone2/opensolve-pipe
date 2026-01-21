# Technical Specification Document (TSD)

# OpenSolve Pipe - Web-Based Hydraulic Network Design Tool

**Version:** 0.1.0 (Draft)
**Date:** January 2026
**Status:** Skeleton TSD for Development Planning

---

## 1. Introduction

### 1.1 Purpose

This document provides implementation-level technical specifications for OpenSolve Pipe. It translates the architecture defined in the SDD into concrete technologies, file structures, and implementation details.

### 1.2 Scope

This document covers:

- Technology stack selection
- Project structure
- Implementation details
- Data formats and schemas
- Deployment configuration

### 1.3 References

- PRD: Product Requirements Document v0.1.0
- SDD: Software Design Document v0.1.0

---

## 2. Technology Stack

### 2.1 Frontend

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Framework | **SvelteKit** | Excellent performance, smaller bundle size, good mobile support, simpler than React for this use case |
| Language | TypeScript | Type safety, better tooling, self-documenting |
| Styling | Tailwind CSS | Utility-first, responsive design, consistent look |
| State | Svelte stores | Built-in, sufficient for component chain model |
| Charts | Chart.js or Plotly.js | Pump curve visualization |
| Schematic | SVG + D3.js | Custom symbols, interactive elements |
| Compression | pako (gzip) | URL state compression |

**Alternative Considered:** React with Zustand

- Larger ecosystem but heavier bundle
- Svelte preferred for mobile performance parity

### 2.2 Backend

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Framework | **FastAPI** | Modern Python, async support, auto OpenAPI docs |
| Language | Python 3.11+ | Required for hydraulic libraries |
| Hydraulics | fluids, WNTR | Proven libraries, actively maintained |
| Validation | Pydantic | FastAPI integration, type coercion |
| Task Queue | Celery + Redis | Async solve jobs (future, for large networks) |

### 2.3 Database (Optional)

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Primary | **PostgreSQL** | Robust, good JSON support for project data |
| Cache | Redis | Session data, rate limiting, task queue |

**Note:** Database only required when:

- Project exceeds URL-encoding size limit (~50KB compressed)
- User opts for account-based persistence

### 2.4 Infrastructure

| Component | Technology |
|-----------|------------|
| Frontend Hosting | Vercel or Cloudflare Pages |
| Backend Hosting | Railway, Fly.io, or AWS Lambda |
| Database | Supabase (PostgreSQL) or Railway |
| CDN | Cloudflare |

---

## 3. Project Structure

### 3.1 Monorepo Layout

```
opensolve-pipe/
├── apps/
│   ├── web/                    # SvelteKit frontend
│   │   ├── src/
│   │   │   ├── lib/
│   │   │   │   ├── components/
│   │   │   │   │   ├── panel/          # Panel navigator components
│   │   │   │   │   ├── schematic/      # PFD rendering
│   │   │   │   │   ├── results/        # Results display
│   │   │   │   │   ├── forms/          # Input forms
│   │   │   │   │   └── ui/             # Generic UI components
│   │   │   │   ├── stores/             # Svelte stores
│   │   │   │   ├── models/             # TypeScript interfaces
│   │   │   │   ├── utils/              # Helpers, encoding, units
│   │   │   │   └── api/                # API client
│   │   │   ├── routes/
│   │   │   │   ├── +page.svelte        # Home / empty workspace
│   │   │   │   ├── p/
│   │   │   │   │   └── [...encoded]/   # Project view (URL-encoded state)
│   │   │   │   └── api/                # API routes (if using SvelteKit backend)
│   │   │   └── app.html
│   │   ├── static/
│   │   │   └── symbols/                # SVG symbols for schematic
│   │   ├── tests/
│   │   ├── svelte.config.js
│   │   ├── tailwind.config.js
│   │   └── package.json
│   │
│   └── api/                    # FastAPI backend
│       ├── src/
│       │   ├── opensolve_pipe/
│       │   │   ├── __init__.py
│       │   │   ├── main.py             # FastAPI app entry
│       │   │   ├── routers/
│       │   │   │   ├── solve.py
│       │   │   │   ├── fluids.py
│       │   │   │   ├── export.py
│       │   │   │   └── version.py
│       │   │   ├── services/
│       │   │   │   ├── solver/
│       │   │   │   │   ├── simple.py       # Single-path solver
│       │   │   │   │   ├── network.py      # WNTR wrapper
│       │   │   │   │   └── adapter.py      # Component chain → solver
│       │   │   │   ├── fluids.py
│       │   │   │   └── export.py
│       │   │   ├── models/
│       │   │   │   ├── project.py
│       │   │   │   ├── components.py
│       │   │   │   ├── results.py
│       │   │   │   └── fluids.py
│       │   │   ├── data/
│       │   │   │   ├── pipe_materials.json
│       │   │   │   ├── fittings.json
│       │   │   │   └── fluids.json
│       │   │   └── utils/
│       │   │       ├── units.py
│       │   │       └── k_factors.py
│       │   └── tests/
│       ├── pyproject.toml
│       └── Dockerfile
│
├── packages/
│   └── shared/                 # Shared TypeScript types (if needed)
│       ├── src/
│       │   └── models/
│       └── package.json
│
├── docs/
│   ├── PRD.md
│   ├── SDD.md
│   └── TSD.md
│
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── deploy.yml
│
├── docker-compose.yml
├── turbo.json                  # Turborepo config (if using)
└── README.md
```

### 3.2 Key Files

#### Frontend Entry: `apps/web/src/routes/+page.svelte`

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { projectStore } from '$lib/stores/project';
  import PanelNavigator from '$lib/components/panel/PanelNavigator.svelte';
  import SchematicViewer from '$lib/components/schematic/SchematicViewer.svelte';
  import ResultsPanel from '$lib/components/results/ResultsPanel.svelte';

  let viewMode: 'panel' | 'schematic' | 'results' = 'panel';
</script>

<main class="h-screen flex flex-col">
  <header class="h-14 border-b flex items-center px-4">
    <!-- Navigation, project name, solve button -->
  </header>

  <div class="flex-1 flex overflow-hidden">
    {#if viewMode === 'panel'}
      <PanelNavigator />
    {:else if viewMode === 'schematic'}
      <SchematicViewer on:elementClick={(e) => openPanel(e.detail.id)} />
    {:else}
      <ResultsPanel />
    {/if}
  </div>
</main>
```

#### Backend Entry: `apps/api/src/opensolve_pipe/main.py`

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import solve, fluids, export, version

app = FastAPI(
    title="OpenSolve Pipe API",
    description="Hydraulic network analysis API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(solve.router, prefix="/api/v1", tags=["solve"])
app.include_router(fluids.router, prefix="/api/v1", tags=["fluids"])
app.include_router(export.router, prefix="/api/v1", tags=["export"])
app.include_router(version.router, prefix="/api/v1", tags=["version"])


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

---

## 4. Data Specifications

### 4.0 Port-Based Connection Architecture

The network uses a port-based architecture where components have defined connection ports, and pipe connections link ports between components.

**TypeScript Implementation:**

```typescript
// apps/web/src/lib/models/ports.ts

export interface Port {
  id: string;
  nominalSize: number;
  direction: 'inlet' | 'outlet' | 'bidirectional';
}

export interface PipeConnection {
  id: string;
  fromComponentId: string;
  fromPortId: string;
  toComponentId: string;
  toPortId: string;
  piping?: PipingSegment;
}

// Port factory functions for each component type
export function createPumpPorts(suctionSize: number, dischargeSize: number): Port[] {
  return [
    { id: 'suction', nominalSize: suctionSize, direction: 'inlet' },
    { id: 'discharge', nominalSize: dischargeSize, direction: 'outlet' }
  ];
}

export function createBranchPorts(branchType: BranchType, sizes: number[]): Port[] {
  switch (branchType) {
    case 'tee':
      return [
        { id: 'run_inlet', nominalSize: sizes[0], direction: 'inlet' },
        { id: 'run_outlet', nominalSize: sizes[1], direction: 'outlet' },
        { id: 'branch', nominalSize: sizes[2], direction: 'bidirectional' }
      ];
    case 'cross':
      return sizes.map((size, i) => ({
        id: `port_${i + 1}`,
        nominalSize: size,
        direction: 'bidirectional' as const
      }));
    // ... other branch types
  }
}

export function createReservoirPorts(portConfigs: { size: number }[]): Port[] {
  return portConfigs.map((config, i) => ({
    id: `port_${i + 1}`,
    nominalSize: config.size,
    direction: 'bidirectional' as const
  }));
}
```

**Python Implementation:**

```python
# apps/api/src/opensolve_pipe/models/ports.py

from pydantic import BaseModel
from typing import Literal, List
from enum import Enum

class PortDirection(str, Enum):
    INLET = "inlet"
    OUTLET = "outlet"
    BIDIRECTIONAL = "bidirectional"

class Port(BaseModel):
    id: str
    nominal_size: float  # in project units
    direction: PortDirection

class PipeConnection(BaseModel):
    id: str
    from_component_id: str
    from_port_id: str
    to_component_id: str
    to_port_id: str
    piping: "PipingSegment | None" = None
```

### 4.1 Pipe Materials Library

**File:** `apps/api/src/opensolve_pipe/data/pipe_materials.json`

```json
{
  "materials": [
    {
      "id": "carbon_steel",
      "name": "Carbon Steel",
      "roughness_mm": 0.046,
      "roughness_in": 0.0018,
      "schedules": {
        "40": {
          "2.5": { "od_in": 2.875, "id_in": 2.469, "wall_in": 0.203 },
          "3": { "od_in": 3.500, "id_in": 3.068, "wall_in": 0.216 },
          "4": { "od_in": 4.500, "id_in": 4.026, "wall_in": 0.237 },
          "6": { "od_in": 6.625, "id_in": 6.065, "wall_in": 0.280 },
          "8": { "od_in": 8.625, "id_in": 7.981, "wall_in": 0.322 }
        },
        "80": {
          "2.5": { "od_in": 2.875, "id_in": 2.323, "wall_in": 0.276 },
          "3": { "od_in": 3.500, "id_in": 2.900, "wall_in": 0.300 },
          "4": { "od_in": 4.500, "id_in": 3.826, "wall_in": 0.337 }
        }
      }
    },
    {
      "id": "stainless_steel",
      "name": "Stainless Steel",
      "roughness_mm": 0.015,
      "roughness_in": 0.0006,
      "schedules": { }
    },
    {
      "id": "pvc",
      "name": "PVC",
      "roughness_mm": 0.0015,
      "roughness_in": 0.00006,
      "schedules": { }
    },
    {
      "id": "hdpe",
      "name": "HDPE",
      "roughness_mm": 0.007,
      "roughness_in": 0.00028,
      "sdr_series": {
        "11": { },
        "17": { }
      }
    },
    {
      "id": "ductile_iron",
      "name": "Ductile Iron",
      "roughness_mm": 0.25,
      "roughness_in": 0.01,
      "classes": { }
    },
    {
      "id": "grp",
      "name": "GRP (Fiberglass)",
      "roughness_mm": 0.01,
      "roughness_in": 0.0004,
      "pressure_classes": { }
    }
  ]
}
```

### 4.2 Branch Component Data

**File:** `apps/api/src/opensolve_pipe/data/branch_k_factors.json`

Branch components use flow-dependent K-factors based on Crane TP-410 and Miller (1990).

```json
{
  "tee": {
    "diverging": {
      "run_to_run": "K = 20 * f_T",
      "run_to_branch": "K = 60 * f_T * (1 + 3.6 * (Db/Dr)^2)"
    },
    "converging": {
      "run_to_run": "K = 20 * f_T",
      "branch_to_run": "K = 60 * f_T"
    }
  },
  "wye_45": {
    "diverging": {
      "inlet_to_outlet": "K = 16 * f_T",
      "inlet_to_branch": "K = 30 * f_T"
    }
  },
  "cross": {
    "notes": "K-factors depend on flow distribution; use WNTR for complex cases"
  },
  "elbow_branch": {
    "main_flow": "K = standard elbow K",
    "branch_flow": "K = 60 * f_T"
  }
}
```

**Python Model:**

```python
# apps/api/src/opensolve_pipe/models/branch.py

from pydantic import BaseModel
from typing import Literal, List
from .ports import Port

class Branch(BaseModel):
    id: str
    type: Literal["branch"] = "branch"
    name: str
    elevation: float
    branch_type: Literal["tee", "wye", "cross", "elbow_branch"]
    ports: List[Port]

class TeeBranch(Branch):
    branch_type: Literal["tee"] = "tee"
    orientation: Literal["through", "converging", "diverging"] = "diverging"

class WyeBranch(Branch):
    branch_type: Literal["wye"] = "wye"
    angle: float = 45.0  # degrees

class CrossBranch(Branch):
    branch_type: Literal["cross"] = "cross"

class ElbowBranch(Branch):
    branch_type: Literal["elbow_branch"] = "elbow_branch"
    main_angle: Literal[45, 90] = 90
    branch_angle: float = 90.0
```

### 4.3 Reference Node Data

**Python Model:**

```python
# apps/api/src/opensolve_pipe/models/reference_node.py

from pydantic import BaseModel
from typing import Literal, List, Optional
from .ports import Port

class FlowPressurePoint(BaseModel):
    flow: float  # in project units
    pressure: float  # in project units

class ReferenceNode(BaseModel):
    id: str
    type: Literal["reference_node"] = "reference_node"
    name: str
    elevation: float
    reference_type: Literal["ideal", "non_ideal"]
    ports: List[Port]  # Single port

class IdealReferenceNode(ReferenceNode):
    reference_type: Literal["ideal"] = "ideal"
    pressure: float  # Fixed pressure at this node

class NonIdealReferenceNode(ReferenceNode):
    reference_type: Literal["non_ideal"] = "non_ideal"
    pressure_flow_curve: List[FlowPressurePoint]
    max_flow: Optional[float] = None
```

### 4.4 Plug/Cap Component

Plug/Cap components represent closed ends (dead legs) with zero flow boundary conditions.

**Python Model:**

```python
# apps/api/src/opensolve_pipe/models/plug.py

from pydantic import BaseModel
from typing import Literal, List
from .ports import Port

class Plug(BaseModel):
    id: str
    type: Literal["plug"] = "plug"
    name: str
    elevation: float
    ports: List[Port]  # Single port with zero flow

    def __init__(self, **data):
        # Plug always has exactly one port
        if "ports" not in data:
            data["ports"] = [Port(
                id="port_1",
                nominal_size=data.get("nominal_size", 4.0),
                direction="bidirectional"
            )]
        super().__init__(**data)
```

**Solver Handling:**

In the solver, a Plug component enforces:

- Flow = 0 at the connected port
- Pressure is calculated based on the connected pipe network
- Head loss through the plug is undefined (no flow path)

**Use Cases:**

- Dead-end branches in distribution systems
- Future expansion points (valve + plug)
- Temporary closures during maintenance modeling
- Capped tee branches

### 4.5 Fittings Library (Crane TP-410 Based)

**File:** `apps/api/src/opensolve_pipe/data/fittings.json`

```json
{
  "fittings": [
    {
      "id": "elbow_90_lr",
      "name": "90° Long Radius Elbow",
      "category": "elbow",
      "k_method": "L_over_D",
      "L_over_D": 20,
      "notes": "r/D = 1.5"
    },
    {
      "id": "elbow_90_sr",
      "name": "90° Short Radius Elbow",
      "category": "elbow",
      "k_method": "L_over_D",
      "L_over_D": 30,
      "notes": "r/D = 1.0"
    },
    {
      "id": "elbow_45",
      "name": "45° Elbow",
      "category": "elbow",
      "k_method": "L_over_D",
      "L_over_D": 16
    },
    {
      "id": "tee_through",
      "name": "Tee (Flow Through Run)",
      "category": "tee",
      "k_method": "L_over_D",
      "L_over_D": 20
    },
    {
      "id": "tee_branch",
      "name": "Tee (Flow Into Branch)",
      "category": "tee",
      "k_method": "L_over_D",
      "L_over_D": 60
    },
    {
      "id": "gate_valve",
      "name": "Gate Valve (Fully Open)",
      "category": "valve",
      "k_method": "L_over_D",
      "L_over_D": 8
    },
    {
      "id": "ball_valve",
      "name": "Ball Valve (Fully Open)",
      "category": "valve",
      "k_method": "L_over_D",
      "L_over_D": 3
    },
    {
      "id": "butterfly_valve",
      "name": "Butterfly Valve (Fully Open)",
      "category": "valve",
      "k_method": "K_fixed",
      "K": 0.35
    },
    {
      "id": "check_valve_swing",
      "name": "Swing Check Valve",
      "category": "valve",
      "k_method": "L_over_D",
      "L_over_D": 50
    },
    {
      "id": "entrance_sharp",
      "name": "Pipe Entrance (Sharp-Edged)",
      "category": "entrance_exit",
      "k_method": "K_fixed",
      "K": 0.5
    },
    {
      "id": "entrance_rounded",
      "name": "Pipe Entrance (Rounded)",
      "category": "entrance_exit",
      "k_method": "K_fixed",
      "K": 0.04
    },
    {
      "id": "exit",
      "name": "Pipe Exit",
      "category": "entrance_exit",
      "k_method": "K_fixed",
      "K": 1.0
    },
    {
      "id": "strainer_basket",
      "name": "Basket Strainer (Clean)",
      "category": "strainer",
      "k_method": "K_fixed",
      "K": 2.0,
      "notes": "Typical value; verify with manufacturer"
    }
  ]
}
```

### 4.3 Fluids Library

**File:** `apps/api/src/opensolve_pipe/data/fluids.json`

```json
{
  "fluids": [
    {
      "id": "water",
      "name": "Water",
      "type": "temperature_dependent",
      "property_source": "IAPWS",
      "temperature_range": { "min_C": 0, "max_C": 100 }
    },
    {
      "id": "ethylene_glycol_30",
      "name": "Ethylene Glycol (30%)",
      "type": "temperature_dependent",
      "concentration_percent": 30,
      "property_source": "ASHRAE"
    },
    {
      "id": "propylene_glycol_30",
      "name": "Propylene Glycol (30%)",
      "type": "temperature_dependent",
      "concentration_percent": 30,
      "property_source": "ASHRAE"
    },
    {
      "id": "diesel",
      "name": "Diesel Fuel",
      "type": "fixed",
      "properties": {
        "density_kg_m3": 850,
        "kinematic_viscosity_m2_s": 3.0e-6,
        "vapor_pressure_Pa": 500
      }
    },
    {
      "id": "gasoline",
      "name": "Gasoline",
      "type": "fixed",
      "properties": {
        "density_kg_m3": 750,
        "kinematic_viscosity_m2_s": 0.6e-6,
        "vapor_pressure_Pa": 55000
      }
    }
  ]
}
```

### 4.4 URL Encoding Schema

**Encoding Pipeline:**

```
Project Object
    ↓
JSON.stringify (deterministic key ordering)
    ↓
pako.gzip (compression level 9)
    ↓
base64url encode (URL-safe, no padding)
    ↓
URL: https://opensolve-pipe.app/p/{encoded}
```

**Decoding Pipeline:**

```
URL parameter
    ↓
base64url decode
    ↓
pako.ungzip
    ↓
JSON.parse
    ↓
Validate against schema
    ↓
Project Object
```

**Size Thresholds:**

| Compressed Size | Storage Strategy |
|-----------------|------------------|
| < 2,000 bytes | URL-only (fits in most URL limits) |
| 2,000 - 50,000 bytes | URL with server fallback key |
| > 50,000 bytes | Server storage required |

**Implementation:**

```typescript
// apps/web/src/lib/utils/encoding.ts

import pako from 'pako';

const BASE64_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';

export function encodeProject(project: Project): string {
  const json = JSON.stringify(project, Object.keys(project).sort());
  const compressed = pako.gzip(json, { level: 9 });
  return base64urlEncode(compressed);
}

export function decodeProject(encoded: string): Project {
  const compressed = base64urlDecode(encoded);
  const json = pako.ungzip(compressed, { to: 'string' });
  return JSON.parse(json) as Project;
}

function base64urlEncode(data: Uint8Array): string {
  let result = '';
  for (let i = 0; i < data.length; i += 3) {
    const chunk = (data[i] << 16) | ((data[i + 1] || 0) << 8) | (data[i + 2] || 0);
    result += BASE64_CHARS[(chunk >> 18) & 63];
    result += BASE64_CHARS[(chunk >> 12) & 63];
    result += i + 1 < data.length ? BASE64_CHARS[(chunk >> 6) & 63] : '';
    result += i + 2 < data.length ? BASE64_CHARS[chunk & 63] : '';
  }
  return result;
}
```

---

## 5. Solver Implementation

### 5.1 Simple Solver (Single Path)

For networks with no branches, use direct calculation.

**File:** `apps/api/src/opensolve_pipe/services/solver/simple.py`

```python
"""
Simple solver for single-path networks (no branches).
Uses fluids library for head loss calculations.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
import numpy as np
from scipy.interpolate import interp1d
from scipy.optimize import brentq

from fluids.friction import friction_factor
from ...models.project import Project, Component, PipingSegment
from ...models.results import SolvedState, NodeResult, LinkResult, PumpResult
from .k_factors import resolve_k_factor


@dataclass
class SimpleSolverOptions:
    max_iterations: int = 100
    tolerance: float = 0.001
    flow_range: Tuple[float, float] = (0.001, 1000)  # GPM


def solve_simple_network(
    project: Project,
    options: SimpleSolverOptions = SimpleSolverOptions()
) -> SolvedState:
    """
    Solve a single-path network (pump → components → endpoint).

    Algorithm:
    1. Generate system curve by calculating total head loss at various flows
    2. Interpolate pump curve
    3. Find intersection (operating point)
    4. Calculate all node/link values at operating point
    """

    # Extract components in order
    components = get_ordered_components(project)
    pump = find_pump(components)

    if pump is None:
        raise ValueError("No pump found in network")

    # Build pump curve interpolator
    pump_curve = build_pump_curve(pump)

    # Generate system curve
    flows, system_heads = generate_system_curve(
        project, components, options.flow_range
    )

    # Find operating point
    operating_point = find_operating_point(
        pump_curve, flows, system_heads, options.flow_range
    )

    if operating_point is None:
        return SolvedState(converged=False, iterations=0)

    # Calculate full results at operating point
    return calculate_results(
        project, components, operating_point, pump_curve, flows, system_heads
    )


def calculate_head_loss(
    piping: PipingSegment,
    flow_gpm: float,
    fluid_props: FluidProperties
) -> float:
    """Calculate head loss through a piping segment."""

    if flow_gpm <= 0:
        return 0.0

    pipe = piping.pipe

    # Convert units
    flow_cfs = flow_gpm / 448.831
    area_ft2 = np.pi * (pipe.inner_diameter_ft / 2) ** 2
    velocity_fps = flow_cfs / area_ft2

    # Reynolds number
    Re = velocity_fps * pipe.inner_diameter_ft / fluid_props.kinematic_viscosity_ft2s

    # Friction factor (Colebrook)
    relative_roughness = pipe.roughness_ft / pipe.inner_diameter_ft
    f = friction_factor(Re=Re, eD=relative_roughness)

    # Darcy-Weisbach pipe loss
    h_pipe = f * (pipe.length_ft / pipe.inner_diameter_ft) * (velocity_fps ** 2) / (2 * 32.174)

    # Fitting losses
    k_total = sum(
        resolve_k_factor(fitting, pipe.inner_diameter_in, f)
        for fitting in piping.fittings
    )
    h_fittings = k_total * (velocity_fps ** 2) / (2 * 32.174)

    return h_pipe + h_fittings
```

### 5.2 Network Solver (WNTR Wrapper)

For branching/looped networks, convert to WNTR model.

**File:** `apps/api/src/opensolve_pipe/services/solver/network.py`

```python
"""
Network solver for complex topologies using WNTR/EPANET.
"""

import wntr
from ...models.project import Project
from ...models.results import SolvedState
from .adapter import component_chain_to_wntr, wntr_results_to_solved_state


def solve_network(project: Project) -> SolvedState:
    """
    Solve a branching/looped network using WNTR.

    Algorithm:
    1. Convert component chain to WNTR WaterNetworkModel
    2. Run EPANET simulation
    3. Convert results back to SolvedState format
    """

    # Convert our data model to WNTR
    wn = component_chain_to_wntr(project)

    # Run simulation
    sim = wntr.sim.EpanetSimulator(wn)

    try:
        results = sim.run_sim()
        return wntr_results_to_solved_state(results, project)
    except Exception as e:
        return SolvedState(
            converged=False,
            iterations=0,
            error=str(e)
        )
```

### 5.3 Solver Adapter (Component Chain → WNTR)

**File:** `apps/api/src/opensolve_pipe/services/solver/adapter.py`

```python
"""
Adapter to convert OpenSolve Pipe component chain to WNTR model.
"""

import wntr
from ...models.project import Project, Component


def component_chain_to_wntr(project: Project) -> wntr.network.WaterNetworkModel:
    """
    Convert an OpenSolve Pipe project to a WNTR WaterNetworkModel.

    Mapping:
    - Reservoir/Tank → WNTR Reservoir or Tank
    - Junction → WNTR Junction
    - Pump → WNTR Pump
    - Piping segments → WNTR Pipes with equivalent minor loss
    - Valves → WNTR Valves or Pipes with K factor
    """

    wn = wntr.network.WaterNetworkModel()

    # Set fluid properties
    # Note: WNTR uses default water properties; custom fluids need workaround

    # First pass: create all nodes
    for component in project.components:
        if component.type == 'reservoir':
            wn.add_reservoir(
                component.id,
                base_head=component.elevation + component.water_level
            )
        elif component.type == 'tank':
            wn.add_tank(
                component.id,
                elevation=component.elevation,
                init_level=component.initial_level,
                min_level=component.min_level,
                max_level=component.max_level,
                diameter=component.diameter
            )
        elif component.type == 'junction':
            wn.add_junction(
                component.id,
                base_demand=component.demand or 0,
                elevation=component.elevation
            )
        # Add implicit junctions for other components
        elif component.type in ['pump', 'valve', 'heat_exchanger']:
            # Create upstream and downstream junction nodes
            wn.add_junction(f"{component.id}_up", elevation=component.elevation)
            wn.add_junction(f"{component.id}_down", elevation=component.elevation)

    # Second pass: create links (pipes, pumps, valves)
    for component in project.components:
        for conn in component.downstream_connections:
            target = conn.target_component_id
            piping = conn.piping

            # Add pipe for piping segment
            if piping:
                pipe_id = f"pipe_{component.id}_to_{target}"
                wn.add_pipe(
                    pipe_id,
                    start_node=get_downstream_node(component),
                    end_node=get_upstream_node(project.get_component(target)),
                    length=piping.pipe.length_ft * 0.3048,  # Convert to meters
                    diameter=piping.pipe.inner_diameter_ft * 0.3048,
                    roughness=piping.pipe.roughness_ft * 1000,  # Convert to mm
                    minor_loss=calculate_total_k(piping.fittings)
                )

    # Add pumps
    for component in project.components:
        if component.type == 'pump':
            wn.add_pump(
                component.id,
                start_node=f"{component.id}_up",
                end_node=f"{component.id}_down",
                pump_type='HEAD',
                pump_parameter=build_wntr_pump_curve(component.curve, wn)
            )

    return wn
```

---

## 6. Unit Conversion System

### 6.1 Unit Registry

**File:** `apps/api/src/opensolve_pipe/utils/units.py`

```python
"""
Unit conversion system supporting mixed units.
"""

from enum import Enum
from typing import Dict, Tuple
from dataclasses import dataclass


class UnitCategory(Enum):
    LENGTH = "length"
    PRESSURE = "pressure"
    FLOW = "flow"
    VELOCITY = "velocity"
    VISCOSITY = "viscosity"
    DENSITY = "density"
    TEMPERATURE = "temperature"


# Conversion factors to SI base units
UNIT_CONVERSIONS: Dict[str, Tuple[UnitCategory, float, float]] = {
    # Length: to meters
    "m": (UnitCategory.LENGTH, 1.0, 0),
    "ft": (UnitCategory.LENGTH, 0.3048, 0),
    "in": (UnitCategory.LENGTH, 0.0254, 0),
    "mm": (UnitCategory.LENGTH, 0.001, 0),

    # Pressure: to Pascals
    "Pa": (UnitCategory.PRESSURE, 1.0, 0),
    "kPa": (UnitCategory.PRESSURE, 1000.0, 0),
    "psi": (UnitCategory.PRESSURE, 6894.76, 0),
    "bar": (UnitCategory.PRESSURE, 100000.0, 0),
    "ft_H2O": (UnitCategory.PRESSURE, 2989.07, 0),
    "m_H2O": (UnitCategory.PRESSURE, 9806.65, 0),

    # Flow: to m³/s
    "m3/s": (UnitCategory.FLOW, 1.0, 0),
    "L/s": (UnitCategory.FLOW, 0.001, 0),
    "GPM": (UnitCategory.FLOW, 6.309e-5, 0),
    "m3/h": (UnitCategory.FLOW, 1/3600, 0),

    # Velocity: to m/s
    "m/s": (UnitCategory.VELOCITY, 1.0, 0),
    "ft/s": (UnitCategory.VELOCITY, 0.3048, 0),

    # Temperature: to Kelvin (with offset)
    "K": (UnitCategory.TEMPERATURE, 1.0, 0),
    "C": (UnitCategory.TEMPERATURE, 1.0, 273.15),
    "F": (UnitCategory.TEMPERATURE, 5/9, 255.372),
}


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """Convert a value between compatible units."""

    from_cat, from_factor, from_offset = UNIT_CONVERSIONS[from_unit]
    to_cat, to_factor, to_offset = UNIT_CONVERSIONS[to_unit]

    if from_cat != to_cat:
        raise ValueError(f"Cannot convert {from_unit} to {to_unit}: incompatible categories")

    # Convert to SI base, then to target
    si_value = value * from_factor + from_offset
    return (si_value - to_offset) / to_factor


@dataclass
class UnitPreferences:
    """User's preferred units for display and input."""
    length: str = "ft"
    diameter: str = "in"
    pressure: str = "psi"
    head: str = "ft_H2O"
    flow: str = "GPM"
    velocity: str = "ft/s"
    temperature: str = "F"
```

---

## 7. API Endpoints

### 7.1 Solve Endpoint

**File:** `apps/api/src/opensolve_pipe/routers/solve.py`

```python
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Tuple
import asyncio

from ..models.project import Project
from ..models.results import SolvedState
from ..services.solver import solve_project

router = APIRouter()


class SolveRequest(BaseModel):
    project: Project
    options: Optional[SolveOptions] = None


class SolveOptions(BaseModel):
    max_iterations: int = 100
    tolerance: float = 0.001
    include_system_curve: bool = True
    flow_range: Tuple[float, float] = (0, 500)
    flow_unit: str = "GPM"


class SolveResponse(BaseModel):
    success: bool
    solved_state: Optional[SolvedState] = None
    compute_time: float
    error: Optional[str] = None


@router.post("/solve", response_model=SolveResponse)
async def solve_network(request: SolveRequest) -> SolveResponse:
    """
    Solve a hydraulic network and return results.
    """
    import time
    start = time.perf_counter()

    try:
        result = await asyncio.to_thread(
            solve_project,
            request.project,
            request.options or SolveOptions()
        )

        return SolveResponse(
            success=result.converged,
            solved_state=result,
            compute_time=time.perf_counter() - start
        )

    except Exception as e:
        return SolveResponse(
            success=False,
            error=str(e),
            compute_time=time.perf_counter() - start
        )


@router.post("/system-curve")
async def generate_system_curve(
    project: Project,
    flow_min: float = 0,
    flow_max: float = 500,
    num_points: int = 51
) -> List[Tuple[float, float]]:
    """
    Generate system curve without finding operating point.
    Returns list of (flow, head) pairs.
    """
    # Implementation
    pass
```

---

## 8. Frontend Components

### 8.1 Panel Navigator

**File:** `apps/web/src/lib/components/panel/PanelNavigator.svelte`

```svelte
<script lang="ts">
  import { projectStore, currentElement, navigationPath } from '$lib/stores/project';
  import ElementPanel from './ElementPanel.svelte';
  import PipingPanel from './PipingPanel.svelte';
  import NavigationControls from './NavigationControls.svelte';

  type EditMode = 'element' | 'upstream' | 'downstream';
  let editMode: EditMode = 'element';

  function navigateToElement(elementId: string) {
    currentElement.set(elementId);
    editMode = 'element';
  }

  function addElementAfter() {
    // Open element type selector, then insert
  }

  function addElementBefore() {
    // Open element type selector, then insert
  }
</script>

<div class="flex flex-col h-full bg-gray-50">
  <!-- Breadcrumb navigation -->
  <nav class="px-4 py-2 bg-white border-b">
    {#each $navigationPath as pathElement, i}
      <button
        class="text-blue-600 hover:underline"
        on:click={() => navigateToElement(pathElement.id)}
      >
        {pathElement.name}
      </button>
      {#if i < $navigationPath.length - 1}
        <span class="mx-2 text-gray-400">→</span>
      {/if}
    {/each}
  </nav>

  <!-- Mode tabs -->
  <div class="flex border-b bg-white">
    <button
      class="px-4 py-2 {editMode === 'element' ? 'border-b-2 border-blue-500' : ''}"
      on:click={() => editMode = 'element'}
    >
      Element
    </button>
    <button
      class="px-4 py-2 {editMode === 'upstream' ? 'border-b-2 border-blue-500' : ''}"
      on:click={() => editMode = 'upstream'}
    >
      Upstream Piping
    </button>
    <button
      class="px-4 py-2 {editMode === 'downstream' ? 'border-b-2 border-blue-500' : ''}"
      on:click={() => editMode = 'downstream'}
    >
      Downstream Piping
    </button>
  </div>

  <!-- Main panel content -->
  <div class="flex-1 overflow-y-auto p-4">
    {#if editMode === 'element'}
      <ElementPanel element={$projectStore.getComponent($currentElement)} />
    {:else if editMode === 'upstream'}
      <PipingPanel
        piping={$projectStore.getComponent($currentElement)?.upstreamPiping}
        direction="upstream"
      />
    {:else}
      <PipingPanel
        piping={$projectStore.getComponent($currentElement)?.downstreamConnections[0]?.piping}
        direction="downstream"
      />
    {/if}
  </div>

  <!-- Navigation controls -->
  <NavigationControls
    on:previous={() => navigateToPrevious()}
    on:next={() => navigateToNext()}
    on:addBefore={addElementBefore}
    on:addAfter={addElementAfter}
  />
</div>
```

### 8.2 Schematic Symbols

**Location:** `apps/web/static/symbols/`

SVG symbols for schematic rendering:

```
symbols/
├── pump.svg
├── reservoir.svg
├── tank.svg
├── junction.svg
├── valve-gate.svg
├── valve-ball.svg
├── valve-check.svg
├── valve-prv.svg
├── valve-fcv.svg
├── heat-exchanger.svg
├── strainer.svg
├── orifice.svg
└── sprinkler.svg
```

**Symbol Design Guidelines:**

- Simplified, recognizable shapes (not full P&ID complexity)
- Consistent 48x48 viewBox
- Single stroke color (#333) for easy theming
- Clear connection points (left/right for flow)

---

## 9. Development Setup

### 9.1 Prerequisites

```bash
# Node.js 18+
node --version  # v18.x or higher

# Python 3.11+
python --version  # 3.11 or higher

# Package managers
npm --version
pip --version
```

### 9.2 Local Development

```bash
# Clone repository
git clone https://github.com/your-org/opensolve-pipe.git
cd opensolve-pipe

# Install frontend dependencies
cd apps/web
npm install

# Install backend dependencies
cd ../api
pip install -e ".[dev]"

# Start development servers
# Terminal 1: Frontend
cd apps/web
npm run dev

# Terminal 2: Backend
cd apps/api
uvicorn opensolve_pipe.main:app --reload --port 8000
```

### 9.3 Docker Development

```yaml
# docker-compose.yml
version: '3.8'

services:
  web:
    build: ./apps/web
    ports:
      - "5173:5173"
    volumes:
      - ./apps/web/src:/app/src
    environment:
      - PUBLIC_API_URL=http://localhost:8000

  api:
    build: ./apps/api
    ports:
      - "8000:8000"
    volumes:
      - ./apps/api/src:/app/src
    environment:
      - ENVIRONMENT=development

  db:
    image: postgres:15
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_USER=opensolve_pipe
      - POSTGRES_PASSWORD=dev_password
      - POSTGRES_DB=opensolve_pipe
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

---

## 10. Testing Strategy

### 10.1 Backend Tests

```python
# apps/api/tests/test_solver.py

import pytest
from opensolve_pipe.services.solver import solve_simple_network
from opensolve_pipe.models.project import Project
from tests.fixtures import simple_pump_system


def test_simple_pump_system_converges(simple_pump_system):
    """Test that a basic pump-pipe-tank system solves correctly."""
    result = solve_simple_network(simple_pump_system)

    assert result.converged
    assert result.pump_results['pump-1'].operating_flow > 0
    assert result.pump_results['pump-1'].operating_head > 0


def test_system_curve_shape(simple_pump_system):
    """System curve should be monotonically increasing with flow."""
    result = solve_simple_network(simple_pump_system)

    curve = result.pump_results['pump-1'].system_curve
    for i in range(1, len(curve)):
        assert curve[i].head >= curve[i-1].head


@pytest.mark.parametrize("pipe_diameter,expected_flow_range", [
    (2.5, (100, 200)),
    (3.0, (150, 300)),
    (4.0, (250, 450)),
])
def test_pipe_size_affects_flow(simple_pump_system, pipe_diameter, expected_flow_range):
    """Larger pipes should result in higher operating flow."""
    simple_pump_system.set_discharge_diameter(pipe_diameter)
    result = solve_simple_network(simple_pump_system)

    flow = result.pump_results['pump-1'].operating_flow
    assert expected_flow_range[0] < flow < expected_flow_range[1]
```

### 10.2 Frontend Tests

```typescript
// apps/web/src/lib/utils/encoding.test.ts

import { describe, it, expect } from 'vitest';
import { encodeProject, decodeProject } from './encoding';
import { createEmptyProject } from '../stores/project';

describe('Project encoding', () => {
  it('should round-trip a simple project', () => {
    const project = createEmptyProject();
    project.metadata.name = 'Test Project';

    const encoded = encodeProject(project);
    const decoded = decodeProject(encoded);

    expect(decoded.metadata.name).toBe('Test Project');
  });

  it('should produce URL-safe strings', () => {
    const project = createEmptyProject();
    const encoded = encodeProject(project);

    expect(encoded).toMatch(/^[A-Za-z0-9_-]+$/);
  });

  it('should compress effectively', () => {
    const project = createEmptyProject();
    const json = JSON.stringify(project);
    const encoded = encodeProject(project);

    // Compressed should be smaller than raw JSON
    expect(encoded.length).toBeLessThan(json.length);
  });
});
```

---

## 11. Deployment

### 11.1 Frontend (Vercel)

```json
// apps/web/vercel.json
{
  "buildCommand": "npm run build",
  "outputDirectory": ".svelte-kit/cloudflare",
  "framework": "sveltekit"
}
```

### 11.2 Backend (Railway)

```toml
# apps/api/railway.toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "Dockerfile"

[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicyType = "ON_FAILURE"
```

### 11.3 Environment Variables

```bash
# Frontend (.env)
PUBLIC_API_URL=https://api.opensolve-pipe.app

# Backend (.env)
ENVIRONMENT=production
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
CORS_ORIGINS=https://opensolve-pipe.app
```

---

## 12. Open Implementation Questions

1. **Schematic layout algorithm:** Which library for auto-layout? (dagre, elkjs, custom?)

2. **Version control storage:** Use git under the hood, or custom versioning in PostgreSQL?

3. **Real-time collaboration (future):** WebSockets, or polling with conflict resolution?

4. **Pump curve digitization (future):** Use existing library, or train custom model?

---

*End of TSD*
