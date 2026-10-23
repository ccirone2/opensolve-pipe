# Technical Specification Document (TSD)

# OpenSolve Pipe - Web-Based Hydraulic Network Design Tool

**Version:** 0.2.0 (Rebuild baseline)
**Date:** October 2026
**Status:** Aligned with the rebuild decisions D1–D6 in `CLAUDE.md`

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

Code samples are sketches that show intent, unless a section says the code was tested (§4.7, §5.2).

### 1.3 References

- PRD: Product Requirements Document v0.2.0
- SDD: Software Design Document v0.2.0
- `CLAUDE.md`: rebuild decisions D1–D6 (take precedence over this document)

---

## 2. Technology Stack

### 2.1 Frontend

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Framework | **SvelteKit 2 / Svelte 5** (runes) | Excellent performance, smaller bundle size, good mobile support |
| Language | TypeScript | Type safety, better tooling, self-documenting |
| Styling | Tailwind CSS | Utility-first, responsive design, consistent look |
| State | Svelte 5 runes (`$state`, `$derived`) in `.svelte.ts` modules | Built-in, sufficient for the project model |
| Charts | Chart.js | Pump and system curve visualization |
| Compression | pako (gzip) | URL state compression |
| Package manager | pnpm | Fast, strict dependency resolution |
| Schematic (Later) | SVG + D3.js | Custom symbols, interactive elements |

**Alternative Considered:** React with Zustand

- Larger ecosystem but heavier bundle
- Svelte preferred for mobile performance parity

### 2.2 Backend

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Framework | **FastAPI** | Modern Python, async support, auto OpenAPI docs |
| Language | Python 3.12 | Required for hydraulic libraries |
| Project manager | uv | Lockfile, fast installs, one tool for envs and scripts |
| Numerics | NumPy, SciPy | Linear algebra for the network solver (sparse once networks grow) |
| Hydraulics | `fluids` | Colebrook friction, fitting K-factors |
| Validation | Pydantic v2 | FastAPI integration, type coercion |
| Test reference (dev only) | WNTR (EPANET) | Independent results for water-only networks (§10) |

Later: a task queue for long solves, if the 5-second target for medium networks cannot be met synchronously.

### 2.3 Database (Later)

v1 has no database (D3). When accounts, short links and version history arrive:

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Primary | PostgreSQL | Robust, good JSON support for project data |
| Cache | Redis | Rate limiting, sessions |

### 2.4 Infrastructure

| Component | Technology |
|-----------|------------|
| Frontend Hosting | Vercel or Cloudflare Pages |
| Backend Hosting | Railway, Fly.io, or AWS Lambda |
| CDN | Cloudflare |

---

## 3. Project Structure

### 3.1 Monorepo Layout

```
opensolve-pipe/
├── apps/
│   ├── web/                    # SvelteKit frontend (pnpm)
│   │   ├── src/
│   │   │   ├── lib/
│   │   │   │   ├── components/
│   │   │   │   │   ├── panel/          # Panel navigator components
│   │   │   │   │   ├── results/        # Results tables, pump curve chart
│   │   │   │   │   └── ui/             # Generic UI components
│   │   │   │   ├── state/              # Project state (*.svelte.ts, runes)
│   │   │   │   ├── models/             # TypeScript types (generated from OpenAPI where possible)
│   │   │   │   ├── utils/
│   │   │   │   │   ├── encoding.ts     # URL fragment encode/decode
│   │   │   │   │   ├── migrations.ts   # schemaVersion upgrades
│   │   │   │   │   ├── units.ts        # display-unit conversion
│   │   │   │   │   └── graph.ts        # port-graph traversal for the navigator
│   │   │   │   └── api/                # API client
│   │   │   ├── routes/
│   │   │   │   ├── +page.svelte        # Home / empty workspace
│   │   │   │   └── p/
│   │   │   │       └── +page.svelte    # Project view; state read from location.hash
│   │   │   └── app.html
│   │   ├── tests/                      # Playwright end-to-end tests
│   │   ├── svelte.config.js
│   │   └── package.json
│   │
│   └── api/                    # FastAPI backend (uv)
│       ├── src/
│       │   └── opensolve_pipe/
│       │       ├── __init__.py
│       │       ├── main.py             # FastAPI app entry
│       │       ├── routers/
│       │       │   ├── solve.py
│       │       │   └── fluids.py
│       │       ├── services/
│       │       │   ├── solver/
│       │       │   │   ├── builder.py      # Port graph → solver nodes and links
│       │       │   │   ├── gga.py          # Global Gradient Algorithm core
│       │       │   │   ├── elements.py     # Head-loss laws: pipe, pump, valves, branches
│       │       │   │   ├── status.py       # Outer loop: check/control valve status, tee K updates
│       │       │   │   ├── npsh.py
│       │       │   │   └── results.py      # Solver output → SolvedState
│       │       │   └── fluids.py
│       │       ├── models/
│       │       │   ├── project.py
│       │       │   ├── components.py
│       │       │   ├── results.py
│       │       │   └── fluids.py
│       │       └── data/
│       │           ├── pipe_materials.json
│       │           ├── fittings.json
│       │           ├── branch_k_factors.json
│       │           └── fluids.json
│       ├── tests/
│       │   ├── reference/              # Benchmark cases (§10.1)
│       │   └── unit/
│       ├── pyproject.toml
│       ├── uv.lock
│       └── Dockerfile
│
├── docs/
│   ├── PRD.md
│   ├── SDD.md
│   └── TSD.md
│
├── .github/
│   └── workflows/
│       └── ci.yml
│
├── .gitignore
├── CLAUDE.md
└── README.md
```

Directories are created when the code that needs them lands.

### 3.2 Key Files

#### Frontend Entry: `apps/web/src/routes/p/+page.svelte`

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { project, loadFromHash } from '$lib/state/project.svelte';
  import PanelNavigator from '$lib/components/panel/PanelNavigator.svelte';
  import ResultsPanel from '$lib/components/results/ResultsPanel.svelte';

  let viewMode = $state<'panel' | 'results'>('panel');

  // The project lives in the fragment, which is only available in the browser.
  onMount(() => {
    loadFromHash(location.hash.slice(1));
    const onHashChange = () => loadFromHash(location.hash.slice(1));
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  });
</script>

<main class="h-screen flex flex-col">
  <header class="h-14 border-b flex items-center px-4">
    <!-- Project name, solve button, share button, view toggle -->
  </header>

  <div class="flex-1 flex overflow-hidden">
    {#if viewMode === 'panel'}
      <PanelNavigator />
    {:else}
      <ResultsPanel />
    {/if}
  </div>
</main>
```

The project route is rendered client-side only (`export const ssr = false` in `p/+page.ts`), since its data is in the fragment.

#### Backend Entry: `apps/api/src/opensolve_pipe/main.py`

```python
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import fluids, solve

app = FastAPI(
    title="OpenSolve Pipe API",
    description="Hydraulic network analysis API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(solve.router, prefix="/api/v1", tags=["solve"])
app.include_router(fluids.router, prefix="/api/v1", tags=["fluids"])


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}
```

---

## 4. Data Specifications

All project and API values are SI (D4; SDD §4). Library data files also use SI or dimensionless values, except where a published standard is in other units (pipe dimensions in mm, as published in ASME B36.10M). Every library entry carries a `source`.

### 4.0 Port-Based Connection Architecture

**TypeScript:**

```typescript
// apps/web/src/lib/models/ports.ts

export interface Port {
  id: string;
  nominalSize: number;      // m
  direction: 'inlet' | 'outlet' | 'bidirectional';
  elevation?: number;       // m; defaults to the component elevation
}

export interface PipeConnection {
  id: string;
  fromComponentId: string;
  fromPortId: string;
  toComponentId: string;
  toPortId: string;
  piping: PipingSegment;
}

export function createPumpPorts(suctionSize: number, dischargeSize: number): Port[] {
  return [
    { id: 'suction', nominalSize: suctionSize, direction: 'inlet' },
    { id: 'discharge', nominalSize: dischargeSize, direction: 'outlet' }
  ];
}

export function createTeePorts(runSize: number, branchSize: number): Port[] {
  return [
    { id: 'run_inlet', nominalSize: runSize, direction: 'bidirectional' },
    { id: 'run_outlet', nominalSize: runSize, direction: 'bidirectional' },
    { id: 'branch', nominalSize: branchSize, direction: 'bidirectional' }
  ];
}

export function createReservoirPorts(sizes: number[]): Port[] {
  return sizes.map((size, i) => ({
    id: `port_${i + 1}`,
    nominalSize: size,
    direction: 'bidirectional' as const
  }));
}
```

**Python:**

```python
# apps/api/src/opensolve_pipe/models/ports.py

from enum import StrEnum

from pydantic import BaseModel, Field


class PortDirection(StrEnum):
    INLET = "inlet"
    OUTLET = "outlet"
    BIDIRECTIONAL = "bidirectional"


class Port(BaseModel):
    id: str
    nominal_size: float = Field(gt=0, description="Nominal diameter, m")
    direction: PortDirection
    elevation: float | None = Field(default=None, description="m above datum")


class PipeConnection(BaseModel):
    id: str
    from_component_id: str
    from_port_id: str
    to_component_id: str
    to_port_id: str
    piping: "PipingSegment"
```

The API uses camelCase JSON (`alias_generator=to_camel`) so it matches the TypeScript models; Python code uses snake_case.

### 4.1 Pipe Materials Library

**File:** `apps/api/src/opensolve_pipe/data/pipe_materials.json`

Dimensions are stored as outside diameter and wall thickness in mm, as published; the inner diameter is derived (`id = od − 2·wall`). Roughness is absolute, in m.

```json
{
  "materials": [
    {
      "id": "carbon_steel",
      "name": "Carbon Steel",
      "roughness_m": 4.6e-5,
      "roughness_source": "Moody (1944), commercial steel",
      "dimensions_source": "ASME B36.10M",
      "schedules": {
        "40": {
          "2.5": { "od_mm": 73.0, "wall_mm": 5.16 },
          "3":   { "od_mm": 88.9, "wall_mm": 5.49 },
          "4":   { "od_mm": 114.3, "wall_mm": 6.02 },
          "6":   { "od_mm": 168.3, "wall_mm": 7.11 },
          "8":   { "od_mm": 219.1, "wall_mm": 8.18 }
        },
        "80": {
          "2.5": { "od_mm": 73.0, "wall_mm": 7.01 },
          "3":   { "od_mm": 88.9, "wall_mm": 7.62 },
          "4":   { "od_mm": 114.3, "wall_mm": 8.56 }
        }
      }
    },
    { "id": "stainless_steel", "name": "Stainless Steel", "roughness_m": 1.5e-5, "dimensions_source": "ASME B36.19M", "schedules": {} },
    { "id": "pvc", "name": "PVC", "roughness_m": 1.5e-6, "schedules": {} },
    { "id": "hdpe", "name": "HDPE", "roughness_m": 7.0e-6, "sdr_series": {} },
    { "id": "ductile_iron", "name": "Ductile Iron", "roughness_m": 2.5e-4, "classes": {} }
  ]
}
```

Schedule keys are NPS designations (inches). The project stores the nominal size in m; the UI maps it to and from the NPS/DN designation the user picks.

### 4.2 Branch Component Data

**File:** `apps/api/src/opensolve_pipe/data/branch_k_factors.json`

Tee and wye losses depend on the flow split and direction, so the solver recomputes branch K-factors in an outer loop (§5.4).

Baseline values for **equal-diameter** standard tees, from Crane TP-410 (f_T is the fully turbulent friction factor for the connected pipe):

| Path | K |
|------|---|
| Flow through run | 20 · f_T |
| Flow through branch | 60 · f_T |

These fixed values ignore the flow ratio and the branch/run diameter ratio. Before implementation, choose a published correlation that covers flow ratio, diameter ratio, and diverging vs converging flow, and record it with its source in the data file. Candidates: Idelchik, *Handbook of Hydraulic Resistance*; Miller, *Internal Flow Systems* (1990); the `fluids` library's tee/wye functions (check which correlation each implements). Until then, the Crane values are used and flagged in results as "flow-ratio independent".

Wye K-factors follow the same rule: no value is used without a cited source. Cross and elbow-with-branch are Later.

**Python Model:**

```python
# apps/api/src/opensolve_pipe/models/branch.py

from typing import Literal

from pydantic import BaseModel

from .ports import Port


class Branch(BaseModel):
    id: str
    type: Literal["branch"] = "branch"
    name: str
    elevation: float  # m
    branch_type: Literal["tee", "wye"]  # Later: "cross", "elbow_branch"
    ports: list[Port]


class TeeBranch(Branch):
    branch_type: Literal["tee"] = "tee"


class WyeBranch(Branch):
    branch_type: Literal["wye"] = "wye"
    angle: float = 45.0  # degrees
```

### 4.3 Reference Node Data

```python
# apps/api/src/opensolve_pipe/models/reference_node.py

from typing import Literal

from pydantic import BaseModel

from .ports import Port


class IdealReferenceNode(BaseModel):
    id: str
    type: Literal["reference_node"] = "reference_node"
    reference_type: Literal["ideal"] = "ideal"
    name: str
    elevation: float  # m
    pressure: float  # Pa gauge
    ports: list[Port]  # exactly one


# Later: NonIdealReferenceNode with pressure_flow_curve and max_flow
```

### 4.4 Plug/Cap Component

```python
# apps/api/src/opensolve_pipe/models/plug.py

from typing import Literal

from pydantic import BaseModel

from .ports import Port


class Plug(BaseModel):
    id: str
    type: Literal["plug"] = "plug"
    name: str
    elevation: float  # m
    ports: list[Port]  # exactly one, id "port_1"
```

**Solver handling:** a plug adds no link. Its port becomes a node with zero demand and only one connection, so the connection's flow is zero and its pressure follows from the rest of the network. Use cases: dead-end branches, future expansion points, capped tee branches.

### 4.5 Fittings Library (Crane TP-410 Based)

**File:** `apps/api/src/opensolve_pipe/data/fittings.json`

Inline fittings only; tees are Branch components (§4.2). `L_over_D` fittings use K = (L/D) · f_T.

```json
{
  "fittings": [
    { "id": "elbow_90_lr", "name": "90° Long Radius Elbow", "category": "elbow", "k_method": "L_over_D", "L_over_D": 20, "notes": "r/D = 1.5", "source": "Crane TP-410" },
    { "id": "elbow_90_sr", "name": "90° Short Radius Elbow", "category": "elbow", "k_method": "L_over_D", "L_over_D": 30, "notes": "r/D = 1.0", "source": "Crane TP-410" },
    { "id": "elbow_45", "name": "45° Elbow", "category": "elbow", "k_method": "L_over_D", "L_over_D": 16, "source": "Crane TP-410" },
    { "id": "gate_valve", "name": "Gate Valve (Fully Open)", "category": "valve", "k_method": "L_over_D", "L_over_D": 8, "source": "Crane TP-410" },
    { "id": "ball_valve", "name": "Ball Valve (Fully Open)", "category": "valve", "k_method": "L_over_D", "L_over_D": 3, "source": "Crane TP-410" },
    { "id": "butterfly_valve", "name": "Butterfly Valve (Fully Open)", "category": "valve", "k_method": "K_fixed", "K": 0.35, "source": "TBD — Crane gives size-dependent L/D; replace with that" },
    { "id": "check_valve_swing", "name": "Swing Check Valve", "category": "valve", "k_method": "L_over_D", "L_over_D": 50, "source": "Crane TP-410" },
    { "id": "entrance_sharp", "name": "Pipe Entrance (Sharp-Edged)", "category": "entrance_exit", "k_method": "K_fixed", "K": 0.5, "source": "Crane TP-410" },
    { "id": "entrance_rounded", "name": "Pipe Entrance (Rounded)", "category": "entrance_exit", "k_method": "K_fixed", "K": 0.04, "notes": "r/d ≥ 0.15", "source": "Crane TP-410" },
    { "id": "exit", "name": "Pipe Exit", "category": "entrance_exit", "k_method": "K_fixed", "K": 1.0, "source": "Crane TP-410" }
  ]
}
```

### 4.6 Fluids Library

**File:** `apps/api/src/opensolve_pipe/data/fluids.json`

Each temperature-dependent fluid names its property source; the implementation calls or tabulates exactly that source.

```json
{
  "fluids": [
    {
      "id": "water",
      "name": "Water",
      "type": "temperature_dependent",
      "property_source": "IAPWS-95 (via the iapws or CoolProp package; pick one and pin it)",
      "temperature_range_K": [273.16, 373.15]
    },
    {
      "id": "ethylene_glycol",
      "name": "Ethylene Glycol (aqueous)",
      "type": "temperature_and_concentration_dependent",
      "concentration_range_pct": [10, 60],
      "property_source": "ASHRAE Handbook — Fundamentals, glycol tables"
    },
    {
      "id": "propylene_glycol",
      "name": "Propylene Glycol (aqueous)",
      "type": "temperature_and_concentration_dependent",
      "concentration_range_pct": [10, 60],
      "property_source": "ASHRAE Handbook — Fundamentals, glycol tables"
    }
  ]
}
```

User-defined fluids are stored in the project:

```json
{ "type": "custom", "name": "Process liquid", "density": 1050, "dynamicViscosity": 0.004, "vaporPressure": 3200 }
```

(kg/m³, Pa·s, Pa absolute.) Fuels are Later.

### 4.7 URL Encoding

**Encoding pipeline:**

```
Project object (SI, includes schemaVersion)
    ↓
canonical JSON (keys sorted at every level)
    ↓
pako.gzip (level 9)
    ↓
base64url (URL-safe, no padding)
    ↓
https://opensolve-pipe.app/p#<encoded>
```

**Decoding pipeline:**

```
location.hash (without '#')
    ↓
base64url decode → pako.ungzip → JSON.parse
    ↓
migrate(project) — apply migrations from its schemaVersion to CURRENT_SCHEMA_VERSION
    ↓
validate against the current schema
    ↓
Project object
```

**Implementation** (tested; the base64url helpers and canonical JSON were checked in Node 22 against Node's built-in base64url for all lengths 0–299 bytes and a 200 KB payload):

```typescript
// apps/web/src/lib/utils/encoding.ts

import pako from 'pako';
import { migrate } from './migrations';

export const URL_LENGTH_WARNING = 8000;

/** JSON with object keys sorted at every level, so equal projects encode identically. */
export function canonicalJson(value: unknown): string {
  return JSON.stringify(value, (_key, v) =>
    v && typeof v === 'object' && !Array.isArray(v)
      ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, v[k]]))
      : v
  );
}

export function encodeProject(project: Project): string {
  return toBase64Url(pako.gzip(canonicalJson(project), { level: 9 }));
}

export function decodeProject(encoded: string): Project {
  const json = pako.ungzip(fromBase64Url(encoded), { to: 'string' });
  return migrate(JSON.parse(json));
}

function toBase64Url(bytes: Uint8Array): string {
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function fromBase64Url(s: string): Uint8Array {
  const b64 = s.replace(/-/g, '+').replace(/_/g, '/');
  const bin = atob(b64 + '==='.slice((b64.length + 3) % 4));
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}
```

Do not use `JSON.stringify(project, Object.keys(project).sort())` for canonical ordering: an array replacer filters keys at **every** depth, so nested fields are silently dropped (verified: `{metadata: {name: 'Test'}}` encodes as `{"metadata":{}}`).

**Migrations:**

```typescript
// apps/web/src/lib/utils/migrations.ts

export const CURRENT_SCHEMA_VERSION = 1;

// MIGRATIONS[n] upgrades a project from version n to n + 1. Never remove an entry.
const MIGRATIONS: Record<number, (p: any) => any> = {};

export function migrate(raw: any): Project {
  let p = raw;
  const from = p.schemaVersion;
  if (!Number.isInteger(from) || from < 1) throw new Error('Not an OpenSolve Pipe project link');
  if (from > CURRENT_SCHEMA_VERSION) throw new Error('This link was made with a newer version of OpenSolve Pipe');
  for (let v = from; v < CURRENT_SCHEMA_VERSION; v++) {
    p = { ...MIGRATIONS[v](p), schemaVersion: v + 1 };
  }
  return validateProject(p);
}
```

Every released schema version keeps a fixture link in `apps/web/src/lib/utils/__fixtures__/`; a test decodes each one.

### 4.8 Assigned Flow Node

```python
# apps/api/src/opensolve_pipe/models/assigned_flow.py

from typing import Literal

from pydantic import BaseModel, Field

from .ports import Port


class AssignedFlow(BaseModel):
    id: str
    type: Literal["assigned_flow"] = "assigned_flow"
    name: str
    elevation: float  # m
    flow: float = Field(description="m³/s; positive leaves the network, negative enters it")
    ports: list[Port]  # exactly one, id "port_1"
```

**Solver handling:** like a plug, an assigned-flow node adds no link. Its port becomes a node whose demand is `flow`, passed straight into the GGA `demands` (§5.2); `flow = 0` behaves exactly as a plug. It never enters `fixed_heads`, so it doesn't satisfy the boundary check in §5.1. After each outer-loop status update (§5.4), any node with a nonzero demand that has no open path to a fixed head is reported as disconnected (EPANET's "system disconnected" condition) instead of being solved, because the head matrix would be singular.

---

## 5. Solver Implementation

### 5.1 Overview

One solver handles every topology (D1). Pipeline:

1. **Validate topology** (`builder.py`): at least one fixed-pressure boundary per connected sub-network; every port connected or plugged; ports referenced by connections exist. Failures raise `TOPOLOGY_ERROR` (HTTP 422).
2. **Build the solver network** (`builder.py`): each component port becomes a solver node at the port's elevation. Each `PipeConnection` becomes one pipe link (pipe segments in series combined; fitting K-factors summed into `k_minor`, all referenced to that connection's velocity). Each two-port component (pump, valve) becomes a link between its two port nodes. Each branch component becomes short zero-length links from a central node to each port node, carrying the branch K-factor for that path.
3. **Fixed heads and demands:** reservoir ports get H = component elevation + liquid level + surface pressure / (ρg). Ideal reference nodes get H = elevation + p_gauge / (ρg). Assigned-flow ports get a demand equal to their flow (§4.8); every other node's demand is zero.
4. **Solve** with the GGA inner loop (§5.2) inside the status/K outer loop (§5.4).
5. **Map results** (`results.py`) to `SolvedState`: per port node pressure = ρg(H − z) gauge; per connection flow, velocity, head loss, Re, f; pump operating points and NPSH (§5.5).

### 5.2 GGA Core

The Global Gradient Algorithm (Todini & Pilati, 1988) solves energy balance on every link and continuity at every node by Newton's method, eliminating flows so each iteration solves one symmetric positive-definite system for heads.

**Tested sketch** (`apps/api/src/opensolve_pipe/services/solver/gga.py`, pipes only). This code was run against:

- a reservoir-to-reservoir pipe: reproduces the 20 m head difference to 1e-6 m in 11 iterations
- a 6-pipe looped network: mass balance closes to 1e-9 m³/s, energy balance on every pipe to 1e-6 m, 8 iterations
- the same network in WNTR/EPANET 2.2: with `method="swamee_jain"`, flows within 0.10% and heads within 8 mm; with exact Colebrook, flows within 0.26% and heads within 33 mm
- a network with no boundary: raises `TOPOLOGY_ERROR`

```python
from dataclasses import dataclass
from typing import Literal

import numpy as np
from fluids.friction import Swamee_Jain_1976, friction_factor

G = 9.80665  # m/s²
FrictionMethod = Literal["colebrook", "swamee_jain"]


@dataclass
class Pipe:
    start: str
    end: str
    length: float  # m
    diameter: float  # m, inner
    roughness: float  # m, absolute
    k_minor: float = 0.0  # sum of fitting K-factors on this run


def pipe_headloss(
    p: Pipe, q: float, nu: float, method: FrictionMethod = "colebrook"
) -> tuple[float, float]:
    """Return (h, dh/dQ) in m and s/m² for flow q in m³/s. h carries the sign of q."""
    area = np.pi * p.diameter**2 / 4
    re = max(abs(q) / area * p.diameter / nu, 1e-9)
    if re < 2000:
        f = 64 / re
    elif method == "colebrook":
        f = friction_factor(Re=re, eD=p.roughness / p.diameter)  # exact Colebrook
    else:
        f = Swamee_Jain_1976(Re=re, eD=p.roughness / p.diameter)  # EPANET's approximation
    r = (f * p.length / p.diameter + p.k_minor) / (2 * G * area**2)
    # Newton slope ignores df/dQ; the floor keeps the matrix non-singular at Q = 0.
    return r * q * abs(q), max(2 * r * abs(q), 1e-8)


@dataclass
class GgaResult:
    heads: dict[str, float]  # m, unknown nodes only
    flows: list[float]  # m³/s, same order as the input pipes
    iterations: int
    converged: bool


def solve_gga(
    pipes: list[Pipe],
    fixed_heads: dict[str, float],  # m, at reservoirs / ideal reference nodes
    demands: dict[str, float],  # m³/s leaving the network at a node
    nu: float,  # m²/s
    method: FrictionMethod = "colebrook",
    tol: float = 1e-10,
    max_iter: int = 100,
) -> GgaResult:
    if not fixed_heads:
        raise ValueError("TOPOLOGY_ERROR: network needs at least one fixed-pressure boundary")
    nodes = sorted({n for p in pipes for n in (p.start, p.end)} - fixed_heads.keys())
    idx = {n: i for i, n in enumerate(nodes)}
    nl, nj = len(pipes), len(nodes)

    a12 = np.zeros((nl, nj))  # link-node incidence: -1 at start, +1 at end
    h0 = np.zeros(nl)  # contribution of fixed heads (A10 · H0)
    for k, p in enumerate(pipes):
        for node, sign in ((p.start, -1.0), (p.end, 1.0)):
            if node in idx:
                a12[k, idx[node]] = sign
            else:
                h0[k] += sign * fixed_heads[node]
    q_dem = np.array([demands.get(n, 0.0) for n in nodes])

    q = np.full(nl, 1e-3)
    heads = np.zeros(nj)
    for it in range(1, max_iter + 1):
        losses = [pipe_headloss(p, qi, nu, method) for p, qi in zip(pipes, q, strict=True)]
        h, d = (np.array(col) for col in zip(*losses, strict=True))
        energy = h + a12 @ heads + h0  # h(Q) − (H_start − H_end)
        cont = a12.T @ q - q_dem  # inflow − demand at each node
        dinv = 1 / d
        # Schur complement: solve for head corrections, then back-substitute flows.
        lhs = a12.T @ (dinv[:, None] * a12)
        dh = np.linalg.solve(lhs, cont - a12.T @ (dinv * energy)) if nj else np.zeros(0)
        dq = -dinv * (energy + a12 @ dh)
        heads += dh
        q += dq
        if np.abs(dq).max() < tol and np.abs(cont).max(initial=0.0) < tol:
            return GgaResult({n: heads[idx[n]] for n in nodes}, list(q), it, True)
    return GgaResult({n: heads[idx[n]] for n in nodes}, list(q), max_iter, False)
```

**Notes for the production version:**

- Generalize `Pipe` to a `Link` protocol whose `headloss(q) → (h, dh/dq)` is supplied by each element type (§5.3).
- Use `scipy.sparse` and a sparse Cholesky/`spsolve` once networks exceed ~100 nodes.
- `fluids.friction_factor` defaults to an exact Colebrook solution. EPANET's Darcy–Weisbach uses the Swamee–Jain approximation, which differs from Colebrook by up to **2.8%** in f over Re 5·10³–10⁷ and e/D 10⁻⁶–5·10⁻² (measured). The `swamee_jain` option exists only so EPANET reference tests compare network algorithms rather than friction formulas.
- Laminar (Re < 2000) uses f = 64/Re. Between 2000 and 4000, decide and document a transition rule (EPANET interpolates); add a reference case in that range.

### 5.3 Element Head-Loss Laws

Every link supplies h(Q) and dh/dQ, with h positive in the direction of positive Q.

| Element | h(Q) | Notes |
|---------|------|-------|
| Pipe connection | (f·L/D + ΣK) · Q\|Q\| / (2gA²) | §5.2; ΣK from fittings, resolved per SDD §6.2 |
| Pump (on) | −s² · H_curve(Q / s) | affinity laws at speed ratio s; curve fitted through the user's points (monotone cubic interpolation, or a quadratic fit when there are ≤ 3 points) |
| Pump (off) | closed | link removed from the system for that iteration |
| Isolation valve | K(position) · Q\|Q\| / (2gA²) | isolated → closed |
| Check / stop-check | open: K · Q\|Q\| / (2gA²); closed when Q would reverse or ΔH < cracking head | status set in the outer loop |
| PRV / PSV / FCV | active: fixes downstream pressure / upstream pressure / flow; else open or closed | status logic as EPANET's (Rossman, EPANET 2.2 manual), run in the outer loop |
| PDCV (Later) | active: fixes inlet minus outlet pressure; else open or closed | EPANET's PBV is the closest reference for its active state |
| Branch path | K_path(flow split) · Q\|Q\| / (2gA_ref²) | K from §4.2, updated in the outer loop |

**Cv/Kv to K** for a valve whose connected inner diameter gives flow area A (m²):

```
Kv = 0.865 · Cv
K  = 2.592·10⁹ · A² / Kv²
```

Derived from Kv's definition (m³/h of water at 1 bar ΔP). It agrees with Crane's K = 891·d⁴/Cv² (d in inches) to within 0.2% (checked at 2, 4 and 8 in).

### 5.4 Outer Loop: Status and Branch K-Factors

```
repeat (max 30):
    solve GGA with current link statuses and branch K-factors
    update check-valve, pump-off and control-valve statuses from the solved Q and H
    update branch K-factors from the solved flow split and directions
until no status changed and max |ΔK| < 1e-4
```

If statuses oscillate between two states, stop and return `converged: false` with the oscillating components named in the residual report (SDD §8.2).

### 5.5 NPSH Available

At each pump suction port (elevation z_s):

```
p_abs   = p_gauge(suction) + p_atm
NPSHa   = p_abs / (ρg) + v_s² / (2g) − p_vap / (ρg)
NPSH margin = NPSHa − NPSHr(Q)      (when an NPSHr curve is given)
```

p_atm comes from the project's site elevation via the standard atmosphere, unless overridden:

```
p_atm = 101 325 · (1 − 2.25577·10⁻⁵ · z)^5.25588   [Pa, z in m]
```

(Values checked: 101 325 Pa at 0 m, 89 875 Pa at 1 000 m.)

### 5.6 Scenarios and Goal Seek (Later)

Both sit outside the network solver, so §5.1–5.5 don't change.

**Scenarios** (`services/scenarios.py`): `apply_scenario(project, scenario_id) → Project` copies the base, applies each override after validating its field against the allow-list and the field's Pydantic type, and returns a plain `Project` for the builder. Orphaned overrides are returned as warnings. Solving all scenarios is one independent solve per scenario.

**Goal seek** (`services/goal_seek.py`): an outer loop that sets the variables, runs the full solve (§5.1) and reads the goal results.

- One variable: bracketed root finding on `goal(x) − target` with `scipy.optimize.brentq` over the variable's bounds. If the sign doesn't change across the bounds, minimize |residual| with `scipy.optimize.minimize_scalar(method="bounded")` and report the goal as not met.
- Several variables: `scipy.optimize.least_squares` with bounds and a finite-difference Jacobian (each step costs n + 1 solves), residuals scaled by each goal's tolerance.
- A non-converged inner solve at any trial point fails the run with that point named, rather than being used as a residual.

---

## 6. Unit Conversion System

Conversions happen only in the frontend, at input and display (D4). The backend and the stored project use SI.

### 6.1 Unit Registry

**File:** `apps/web/src/lib/utils/units.ts`

```typescript
export type UnitCategory =
  | 'length' | 'diameter' | 'pressure' | 'head' | 'flow'
  | 'velocity' | 'density' | 'viscosity' | 'temperature';

// value_SI = value · factor + offset
const UNITS: Record<string, { category: UnitCategory; factor: number; offset?: number }> = {
  // Length / diameter / head → m
  m: { category: 'length', factor: 1 },
  ft: { category: 'length', factor: 0.3048 },
  in: { category: 'length', factor: 0.0254 },
  mm: { category: 'length', factor: 0.001 },

  // Pressure → Pa (gauge or absolute is tracked by the field, not the unit)
  Pa: { category: 'pressure', factor: 1 },
  kPa: { category: 'pressure', factor: 1000 },
  bar: { category: 'pressure', factor: 100000 },
  psi: { category: 'pressure', factor: 6894.757 },

  // Flow → m³/s
  'm3/s': { category: 'flow', factor: 1 },
  'L/s': { category: 'flow', factor: 0.001 },
  'm3/h': { category: 'flow', factor: 1 / 3600 },
  gpm: { category: 'flow', factor: 6.30902e-5 },

  // Velocity → m/s
  'm/s': { category: 'velocity', factor: 1 },
  'ft/s': { category: 'velocity', factor: 0.3048 },

  // Temperature → K
  K: { category: 'temperature', factor: 1 },
  C: { category: 'temperature', factor: 1, offset: 273.15 },
  F: { category: 'temperature', factor: 5 / 9, offset: 255.3722 }
};

export function toSI(value: number, unit: string): number {
  const u = UNITS[unit];
  return value * u.factor + (u.offset ?? 0);
}

export function fromSI(value: number, unit: string): number {
  const u = UNITS[unit];
  return (value - (u.offset ?? 0)) / u.factor;
}
```

Pressure expressed as head of liquid (ft or m of fluid) is converted with the project fluid's density (p = ρ·g·h), not a fixed water factor.

### 6.2 Unit Preferences and Pressure Reference

```typescript
export interface UnitPreferences {
  length: string;       // 'ft'
  diameter: string;     // 'in'
  pressure: string;     // 'psi'
  head: string;         // 'ft'
  flow: string;         // 'gpm'
  velocity: string;     // 'ft/s'
  temperature: string;  // 'F'
}
```

Pressure inputs and outputs are gauge and labeled as such (e.g. "psig", "kPa(g)"). Absolute values are shown only where they are meaningful (NPSH, vapor pressure) and labeled "psia" / "kPa(a)".

---

## 7. API Endpoints

### 7.1 Solve Endpoint

**File:** `apps/api/src/opensolve_pipe/routers/solve.py`

```python
import asyncio
import time

from fastapi import APIRouter
from pydantic import BaseModel

from ..models.project import Project
from ..models.results import SolvedState
from ..services.solver import TopologyError, solve_project

router = APIRouter()


class SolveOptions(BaseModel):
    max_iterations: int = 100
    tolerance: float = 1e-6
    include_system_curve: bool = True
    flow_range: tuple[float, float] | None = None  # m³/s; default derived from the pump curves


class SolveRequest(BaseModel):
    project: Project
    options: SolveOptions = SolveOptions()


class SolveResponse(BaseModel):
    success: bool
    solved_state: SolvedState | None = None
    compute_time: float
    error: str | None = None
    message: str | None = None


@router.post("/solve", response_model=SolveResponse)
async def solve_network(request: SolveRequest) -> SolveResponse:
    start = time.perf_counter()
    # TopologyError is mapped to HTTP 422 by an exception handler in main.py.
    result = await asyncio.to_thread(solve_project, request.project, request.options)
    return SolveResponse(
        success=result.converged,
        solved_state=result,
        compute_time=time.perf_counter() - start,
    )


@router.post("/system-curve")
async def system_curve(
    project: Project, pump_id: str, flow_min: float = 0.0, flow_max: float | None = None,
    num_points: int = 51,
) -> list[tuple[float, float]]:
    """System curve seen by one pump: (flow m³/s, head m) pairs."""
    ...
```

---

## 8. Frontend Components

### 8.1 Panel Navigator

**File:** `apps/web/src/lib/components/panel/PanelNavigator.svelte`

The navigator walks the port graph (SDD §3.1.1). Graph helpers live in `$lib/utils/graph.ts`:

```typescript
// apps/web/src/lib/utils/graph.ts

/** Connections attached to a component, with the component at the other end. */
export function neighbors(project: Project, componentId: string) {
  return project.connections.flatMap((c) =>
    c.fromComponentId === componentId ? [{ connection: c, otherId: c.toComponentId }] :
    c.toComponentId === componentId ? [{ connection: c, otherId: c.fromComponentId }] :
    []
  );
}

/** Ways forward from the end of the path: neighbors not already on it. */
export function nextOptions(project: Project, path: NavigationStep[]) {
  const visited = new Set(path.map((s) => s.componentId));
  const current = path[path.length - 1].componentId;
  return neighbors(project, current).filter((n) => !visited.has(n.otherId));
}
```

```svelte
<script lang="ts">
  import { project } from '$lib/state/project.svelte';
  import { nextOptions } from '$lib/utils/graph';
  import ComponentPanel from './ComponentPanel.svelte';
  import ConnectionPanel from './ConnectionPanel.svelte';
  import PathChooser from './PathChooser.svelte';

  let { start }: { start: string } = $props();

  let path = $state<NavigationStep[]>([{ componentId: start }]);
  let editMode = $state<'component' | 'connection'>('component');
  let current = $derived(path[path.length - 1].componentId);
  let options = $derived(nextOptions(project, path));
  let choosing = $state(false);

  function next() {
    if (options.length === 1) go(options[0]);
    else if (options.length > 1) choosing = true;  // ask which branch to follow
  }

  function go(option: { connection: PipeConnection; otherId: string }) {
    path = [...path, { componentId: option.otherId, viaConnectionId: option.connection.id }];
    choosing = false;
    editMode = 'component';
  }

  function previous() {
    if (path.length > 1) path = path.slice(0, -1);
  }
</script>

<div class="flex flex-col h-full">
  <nav class="px-4 py-2 border-b overflow-x-auto whitespace-nowrap">
    {#each path as step, i (step.componentId)}
      <button class="hover:underline" onclick={() => (path = path.slice(0, i + 1))}>
        {project.components.find((c) => c.id === step.componentId)?.name}
      </button>
      {#if i < path.length - 1}<span class="mx-2">→</span>{/if}
    {/each}
  </nav>

  <div class="flex-1 overflow-y-auto p-4">
    {#if editMode === 'component'}
      <ComponentPanel componentId={current} />
    {:else}
      <ConnectionPanel componentId={current} />
    {/if}
  </div>

  {#if choosing}
    <PathChooser {options} onchoose={go} oncancel={() => (choosing = false)} />
  {/if}

  <footer class="flex justify-between p-2 border-t">
    <button onclick={previous} disabled={path.length === 1}>← Prev</button>
    <button onclick={next} disabled={options.length === 0}>Next →</button>
  </footer>
</div>
```

### 8.2 Schematic Symbols (Later)

**Location:** `apps/web/static/symbols/`

**Symbol Design Guidelines:**

- Simplified, recognizable shapes (not full P&ID complexity)
- Consistent 48x48 viewBox
- `currentColor` stroke for theming
- Connection points match port ids

---

## 9. Development Setup

### 9.1 Prerequisites

- [uv](https://docs.astral.sh/uv/) (installs and manages Python 3.12)
- Node.js 22 LTS or later
- pnpm (`corepack enable`)

### 9.2 Local Development

```bash
git clone https://github.com/ccirone2/opensolve-pipe.git
cd opensolve-pipe

# Backend → http://localhost:8000
cd apps/api
uv sync
uv run uvicorn opensolve_pipe.main:app --reload --port 8000

# Frontend → http://localhost:5173 (second terminal)
cd apps/web
pnpm install
pnpm dev
```

### 9.3 Quality Checks

```bash
# apps/api
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy src

# apps/web
pnpm test        # Vitest
pnpm check       # svelte-check
pnpm lint        # ESLint + Prettier
pnpm test:e2e    # Playwright
```

No Docker, database or Redis is needed for v1 development.

---

## 10. Testing Strategy

### 10.1 Reference Test Suite (D6)

**Location:** `apps/api/tests/reference/`

Each case is a data file (the project in API JSON, plus expected results and the source of those results) and is run by one parameterized test.

| Source | Use |
|--------|-----|
| Closed-form hand calculations | Single pipes, series and parallel pipes, reservoir-to-reservoir flow, pump on a single pipe |
| Crane TP-410 and textbook worked examples | Fittings, pumps, NPSH; each case cites the example it reproduces |
| WNTR/EPANET (dev dependency) | Water-only branching and looped networks; the solver runs with `method="swamee_jain"` so EPANET's friction approximation does not count as error |
| Assigned-flow node | Closed-form: reservoir → pipe → assigned flow, pressure at the node from Darcy–Weisbach; EPANET: the same node as a junction demand in a looped network |
| Goal seek (Later) | Closed-form inverses: reservoir level for a target flow through one pipe; pump speed ratio for a target duty point via the affinity laws |

**Pass criteria:** flows, heads and pressures within 0.5% of the reference, or 0.01 m of head, whichever is looser; mass balance closes at every node to the solver tolerance. Every new component type ships with at least one reference case.

```python
# apps/api/tests/reference/test_reference_cases.py

import json
from pathlib import Path

import pytest

from opensolve_pipe.models.project import Project
from opensolve_pipe.services.solver import solve_project

CASES = sorted(Path(__file__).parent.glob("cases/*.json"))


def close(actual: float, expected: float, abs_tol: float) -> bool:
    return abs(actual - expected) <= max(0.005 * abs(expected), abs_tol)


@pytest.mark.parametrize("case_path", CASES, ids=lambda p: p.stem)
def test_reference_case(case_path: Path) -> None:
    case = json.loads(case_path.read_text())
    result = solve_project(Project.model_validate(case["project"]))

    assert result.converged
    for link_id, expected in case["expected"]["flows"].items():
        assert close(result.link_results[link_id].flow, expected, abs_tol=1e-6)
    for node_id, expected in case["expected"]["heads"].items():
        assert close(result.node_results[node_id].hgl, expected, abs_tol=0.01)
```

### 10.2 Backend Unit Tests

- Element laws: h(Q) and dh/dQ for each element type, including Q = 0 and reverse flow
- Cv/Kv → K conversion against Crane's formula
- Topology validation errors
- Status logic: check valves close on reverse flow; PRV/PSV/FCV switch between active/open/closed correctly
- Standard atmosphere and NPSH available

### 10.3 Frontend Tests

```typescript
// apps/web/src/lib/utils/encoding.test.ts

import { describe, it, expect } from 'vitest';
import { canonicalJson, decodeProject, encodeProject } from './encoding';
import { createEmptyProject } from '../state/project.svelte';

describe('Project encoding', () => {
  it('round-trips a project, including nested fields', () => {
    const project = createEmptyProject();
    project.metadata.name = 'Test Project';
    expect(decodeProject(encodeProject(project))).toEqual(project);
  });

  it('produces URL-safe strings', () => {
    expect(encodeProject(createEmptyProject())).toMatch(/^[A-Za-z0-9_-]+$/);
  });

  it('encodes independently of key order', () => {
    expect(canonicalJson({ b: 1, a: { d: 2, c: 3 } })).toBe(canonicalJson({ a: { c: 3, d: 2 }, b: 1 }));
  });

  it('rejects links from a newer schema version', () => {
    const future = { ...createEmptyProject(), schemaVersion: 999 };
    expect(() => decodeProject(encodeProject(future))).toThrow(/newer version/);
  });
});
```

Also: one test per fixture link in `__fixtures__/` (every released schema version still decodes), unit conversion round-trips, graph traversal (`nextOptions` at tees and loops), and Playwright flows for create → solve → share → reopen on desktop and mobile viewports.

---

## 11. Deployment

### 11.1 Frontend

SvelteKit with the adapter for the chosen host (`@sveltejs/adapter-vercel` or `@sveltejs/adapter-cloudflare`); no extra build configuration file is needed.

### 11.2 Backend (Railway or Fly.io)

```dockerfile
# apps/api/Dockerfile
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
CMD ["uv", "run", "--no-sync", "uvicorn", "opensolve_pipe.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Pin the uv image tag to a specific version when this is implemented. Health check: `GET /health`.

### 11.3 Environment Variables

```bash
# Frontend
PUBLIC_API_URL=https://api.opensolve-pipe.app

# Backend
ENVIRONMENT=production
CORS_ORIGINS=https://opensolve-pipe.app
```

---

## 12. Open Implementation Questions

1. **Tee and wye K correlation:** which published correlation covers flow ratio, diameter ratio and direction (§4.2)?
2. **Water property package:** `iapws` or CoolProp for IAPWS-95 (§4.6)?
3. **Transition-zone friction (Re 2000–4000):** what rule, and is it a user option (§5.2)?
4. **Pump curve fitting:** monotone cubic vs polynomial; behavior beyond the last curve point (§5.3).
5. **Control-valve status oscillation:** damping strategy if EPANET-style status logic oscillates (§5.4).
6. **Schematic layout algorithm (Later):** dagre, elkjs, or custom?
7. **Version storage (Later):** git under the hood, or custom versioning in PostgreSQL?
8. **Scenario override addressing (Later):** a field allow-list (§5.6) or JSON Pointer paths? The allow-list is safer; pointers are more general.
9. **Three-way valve characteristic (Later):** which published Cv-vs-position data (linear, equal-percentage, per path) to cite?

---

*End of TSD*
