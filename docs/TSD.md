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

**File:** `apps/api/src/opensolve_pipe/data/pipe_materials.json`, generated by `apps/api/scripts/generate_pipe_data.py` entirely from `fluids` 1.3.1 calls (a unit test regenerates it and checks the committed file). Never edit it by hand.

| Material id | Schedules | Dimensions source | Roughness source |
|-------------|-----------|-------------------|------------------|
| `carbon_steel` | 10, 20, 30, 40, STD, 60, 80, XS, 100, 120, 140, 160, XXS | ASME B36.10M-2004 via `fluids.piping.nearest_pipe` | Farshad & Rieke (2006) "Carbon steel, bare" via `fluids.friction.roughness_Farshad` |
| `stainless_steel` | 5S, 10S, 40S, 80S | ASME B36.19M-2004 via `fluids.piping.nearest_pipe` | Farshad & Rieke (2006) "Cr13, bare" (13% Cr stainless) |
| `pvc` | 40D1785, 80D1785, 120D1785 | ASTM D1785-15E01 via `fluids.piping.nearest_pipe` | Farshad & Rieke (2006) "Plastic coated", the closest cited plastic surface (no PVC entry exists; stated in the data notes and the trace) |
| `custom` | — | user inner diameter | user roughness |

Each size stores `nps` (designation), `nominalSize` (NPS × 0.0254 m, the stored project value), outer diameter, wall thickness, inner diameter and roughness, all in m; Farshad roughness is diameter dependent and evaluated at each inner diameter. A user `roughness` or `innerDiameter` overrides the library value and is labeled "user" in the trace. HDPE and ductile iron are not in v1: `fluids` has no cited roughness for them (and no ductile-iron dimensions). Never use `fluids`' free-text `material_roughness` lookup: it fuzzy-matches names (e.g. "PVC" → 0.0008 m).

### 4.2 Branch Component Data

Tee and wye losses depend on the flow split and direction, so the solver recomputes them in the outer loop (§5.4). Code: `services/solver/branches.py`.

**Correlations** (Crane TP-410, 2009, as implemented in `fluids.fittings` 1.3.1): `K_branch_diverging_Crane`, `K_run_diverging_Crane`, `K_branch_converging_Crane`, `K_run_converging_Crane`. They cover the two patterns in which the combined flow passes through a **run** port: dividing (combined in at a run port, out through the other run port and the branch) and combining (in through a run port and the branch, out at the other run port). K is referenced to the combined-flow velocity in the run diameter; D_run is the inner diameter of the pipe on the combined port and D_branch that of the branch pipe. The angle is 90° for a tee and the wye's angle (30–60°) for a wye.

| Situation | Treatment | Flag |
|-----------|-----------|------|
| Combined flow through a run port | Crane functions above | — |
| Tee with the combined flow through the branch (flow in through the branch dividing both ways, or both runs combining into the branch) | Darby 3-K `Tee, Through-branch, (as elbow), flanged, (r/D = 1)` (`fluids.fittings.Darby3K`) per path, on that leg's own velocity; the result lists it on the combined-flow velocity, K_Darby·(v_leg/v_c)², so that K·v_c²/(2g) is the path loss | `TEE_PATTERN_FALLBACK` |
| … with a run pipe outside the schedule-40 table `Darby3K` maps diameters to nominal sizes on (`fluids.piping.S40i`, 6.84–875.9 mm; below ~4.5 mm its extrapolated NPS is negative and K complex) | Darby K at the table's nearest end | also `CORRELATION_OUT_OF_RANGE` |
| Wye with the combined flow through `outlet_2` | No cited correlation: not converged | `UNSUPPORTED_FLOW_PATTERN` |
| Wye with the combined flow at `outlet_1` and flow in the lateral (lateral used against its lean; the flow turns 180° − θ) | Crane K at θ | `CORRELATION_OUT_OF_RANGE` |
| β = D_branch/D_run > 1, or the two run pipes differ in diameter | Crane K as computed | `CORRELATION_OUT_OF_RANGE` |
| `lossModel: 'ideal'` | K = 0 on every path (an EPANET-style junction) | — |

The wye's straight run is `inlet`–`outlet_1`; the lateral `outlet_2` leans toward `outlet_1`. Crane's lateral geometry therefore applies with the combined flow at `inlet`. A dead lateral (no flow) is pure run flow in either direction: every Crane wye K at q = 0 is the same at any angle, so it is not flagged.

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

**File:** `apps/api/src/opensolve_pipe/data/fittings.json`. Inline fittings only; tees and wyes are branch components (§4.2). Each fitting type names exactly one `fluids.fittings` function and its fixed arguments; the solver evaluates that call at the reference pipe's inner diameter. A user `kOverride` always wins (SDD §6.2) and is labeled "user".

| Type | `fluids` 1.3.1 call | K referenced to |
|------|---------------------|-----------------|
| elbow_90_lr / elbow_90_sr / elbow_45_lr / elbow_45_sr | `bend_rounded_Crane(Di, 90 or 45, bend_diameters=1.5 or 1.0)` | pipe |
| elbow_90_threaded / elbow_45_threaded | `bend_rounded(Di, 90 or 45, method='Crane standard')` | pipe |
| bend | `bend_rounded_Crane(Di, angle, bend_diameters=radiusRatio)` (r/D outside [1, 20] flagged) | pipe |
| entrance_sharp / entrance_rounded / entrance_projecting | `entrance_sharp(method='Crane')` / `entrance_rounded(Di, rc, method='Crane')` / `entrance_distance(Di, method='Crane')` | pipe |
| exit | `exit_normal()` | pipe |
| reducer_sudden | contraction `contraction_sharp(D_large, D_small, method='Crane')`; expansion `diffuser_sharp(D_small, D_large)` — chosen from the flow direction | smaller pipe |
| reducer_conical | contraction `contraction_conical_Crane(D_large, D_small, angle)`; expansion `diffuser_conical(D_small, D_large, angle, method='Crane')` | smaller pipe |
| gate / ball / globe / butterfly / plug valve | `K_gate_valve_Crane(D, D, 0)`, `K_ball_valve_Crane(D, D, 0)`, `K_globe_valve_Crane(D, D)`, `K_butterfly_valve_Crane(D, style=0)`, `K_plug_valve_Crane(D, D, 0, style=0)` | pipe |
| swing_check_valve / lift_check_valve | `K_swing_check_valve_Crane(D, angled=True)` / `K_lift_check_valve_Crane(D, D, angled=True)` (angled pattern; use a custom K for straight patterns) | pipe |
| custom | `kOverride` | pipe |

Crane valve and fitting K values use Crane's fully turbulent friction factor `ft_Crane(D)` and are documented as invalid in laminar flow; every library fitting in a segment with Re < 2000 is flagged `CORRELATION_OUT_OF_RANGE`.

### 4.6 Fluids Library

Code: `services/fluids.py`. Properties come from **CoolProp 8.0.0** (pinned, MIT) and every value records its source (`FluidProperties.sources`).

| Fluid id | CoolProp fluid | Property models | Range | Vapor pressure |
|----------|----------------|-----------------|-------|----------------|
| `water` | `Water` (HEOS) | IAPWS-95 EOS (Wagner & Pruß 2002); viscosity Huber et al. (2009) | 273.16 K < T ≤ 473.15 K; at 101 325 Pa below the normal boiling point, saturated liquid above it | saturation pressure from the EOS |
| `ethylene_glycol` | `INCOMP::MEG` | Melinder (2010) fits; mass fraction x | x and T limits queried from CoolProp (`fraction_min/max`, `Tmax`); T must be above the solution's freezing point (`T_freeze`) | not defined by CoolProp |
| `propylene_glycol` | `INCOMP::MPG` | Melinder (2010) | as above | not defined |

Density, dynamic viscosity and vapor pressure can each be overridden (labeled "user"). Glycol solutions have no vapor pressure in CoolProp, so NPSH available needs a user value; without one the solve flags `NO_VAPOR_PRESSURE` and reports no NPSHa. Out-of-range inputs raise `FluidError` (HTTP 400). Custom fluids carry density, dynamic viscosity and an optional vapor pressure:

```json
{ "kind": "custom", "name": "Process liquid", "density": 1050, "dynamicViscosity": 0.004, "vaporPressure": 3200 }
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

---

## 5. Solver Implementation

### 5.1 Overview

One solver handles every topology (D1). Code: `apps/api/src/opensolve_pipe/services/solver/`; entry point `solve_project(project, options) -> SolvedState`.

1. **Validate topology** (`builder.py`): every problem is collected and raised together as `TopologyError(issues)` (HTTP 422): `DUPLICATE_COMPONENT_ID`, `DUPLICATE_CONNECTION_ID`, `DUPLICATE_PUMP_CURVE_ID`, `UNKNOWN_COMPONENT`, `UNKNOWN_PORT`, `UNKNOWN_PUMP_CURVE`, `UNKNOWN_PIPE_MATERIAL`, `UNKNOWN_PIPE_SCHEDULE`, `UNKNOWN_PIPE_SIZE`, `ROUGHNESS_OUT_OF_RANGE`, `SELF_CONNECTION`, `PORT_CONNECTED_TWICE`, `UNCONNECTED_PORT` ("connect it or add a plug") and `NO_FIXED_HEAD` (a connected sub-network without a reservoir or reference node; also an empty project).
2. **Build the solver network** (`builder.py`, `network.py`): one node per component port at the port's effective elevation; one link per `PipeConnection` (its segments in series and its fittings); one link per pump and valve between its port nodes; a branch component adds a center node and three legs (center → port).
3. **Fixed heads:** reservoir ports get H = z + liquidLevel + surfacePressure/(ρg); ideal reference nodes get H = z_port + p/(ρg) (a body of liquid at rest at that pressure).
4. **Solve** with the GGA inner loop (§5.2) inside the outer loop for statuses and branch losses (§5.4).
5. **Map results** (`results.py`) to `SolvedState` (SDD §4.10), with physics flags.

**The nodal unknown is the energy grade line** H = z + p/(ρg) + v²/(2g). Every link's energy equation is H_from − H_to = h(Q), so pump head (an EGL rise) and fitting losses are exact. At a port, v is the velocity in the connected pipe's end segment; static pressure p = ρg(H − z − v²/2g), HGL = H − v²/2g. Boundary ports (reservoirs, reference nodes) report the quiescent boundary (v = 0). EPANET neglects velocity heads, so its nodal head corresponds to our EGL; EPANET comparisons compare EGL and flows.

### 5.2 GGA Core

`gga.py` implements the Global Gradient Algorithm (Todini & Pilati, 1988) generalized from the tested sketch that was in this section (pipes only): links supply h(Q) and dh/dQ (`elements.py`); the Schur-complement system A21·D⁻¹·A12·dH = rhs is assembled and solved with `scipy.sparse` (`spsolve`); flows are back-substituted.

- **Friction** (`friction.py`): laminar Re < 2000, f = 64/Re (exact linear law, finite slope at Q = 0); turbulent Re ≥ 4000, exact Colebrook via `fluids.friction.Clamond` (`colebrook`, default) or Swamee–Jain in the exact form EPANET 2.2 evaluates, 5.74/Re^0.9 (`swamee_jain`, for EPANET comparisons; `fluids.Swamee_Jain_1976` writes 6.97^0.9 = 5.73997 and differs by ~2·10⁻⁶ in f); transition 2000 ≤ Re < 4000, the cubic Hermite interpolation in R = Re/2000 between the laminar value and slope at 2000 and the turbulent formula's value and slope at 4000 — EPANET 2.2's Dunlop polynomial (`hydcoeffs.c` frictionFactor), reproduced to 10⁻¹⁴ in `swamee_jain` mode. Transitional segments are flagged `TRANSITIONAL_FLOW`. Never call `fluids.friction.friction_factor` (it switches to 64/Re at Re 2040 with a 57% jump). Range flags: Swamee–Jain outside 5·10³ ≤ Re ≤ 10⁸ or 10⁻⁶ ≤ ε/D ≤ 0.05; Colebrook above ε/D = 0.05 (`fluids.friction.fmethods`).
- **Newton slopes** include df/dQ. Swamee–Jain differs from exact Colebrook by up to **3.0%** in f within its documented range (probe: Re 5000, ε/D 0.0189).
- **Branch legs carry head offsets** (zero for an ideal tee, the Crane path loss otherwise, §5.4). They are not iterated: each branch's center and port nodes become one head unknown with fixed offsets, and leg flows are rebuilt from continuity after every Newton step. (A Jacobian floor on zero-slope links stalled Newton on a large main feeding small-bore tubing.) `jacobian_slopes` keeps a small positive floor only for zero-slope pumps and valves.
- **Isolated sections** (nodes not connected to a fixed head through open links) are removed before solving; their links carry zero flow and their ports are reported without heads (`ISOLATED_SECTION`, info).
- **Initial flows:** 1 ft/s (0.3048 m/s) in every pipe, as EPANET.
- **Convergence:** max |dQ| ≤ tolerance × max |Q| of the current iterate, continuity residual ≤ 10⁻⁹ × max |Q| + 10⁻¹⁴ m³/s at every node, energy residual ≤ 10⁻⁷ m on every link (residuals of the returned state). `tolerance` and `maxIterations` come from `project.settings.solverOptions`.
- **Reported zero flow:** flows below 10⁻¹² × max |Q| + 10⁻¹⁴ m³/s, and links in dead-end trees (zero by continuity), are reported as exactly 0.

### 5.3 Element Head-Loss Laws

Every link supplies h(Q) and dh/dQ, with h positive in the direction of positive Q (an EGL drop).

| Element | h(Q) | Notes |
|---------|------|-------|
| Pipe connection | Σ f·(L/D)·v\|v\|/(2g) + Σ K·v\|v\|/(2g) | §5.2; fittings §4.5 |
| Pump (on) | −s²·H₀(Q/s) | `pumps.py`: H₀ is a monotone piecewise cubic (`scipy.interpolate.PchipInterpolator`) through the user's points; beyond them, a straight line with the end slope; affinity laws at speed ratio s. Efficiency η₀(Q/s) (held at its end values outside its points) and NPSHr = s²·NPSHr₀(Q/s) (extrapolated like the head curve, never below 0). Operating outside the curve's flow range flags `PUMP_OUTSIDE_CURVE`. No viscosity correction is applied (HI 9.6.7 is Later); the trace says so. |
| Pump (off / no flow) | closed | |
| Isolation valve | K·Q\|Q\|/(2gA²) | isolated → closed |
| Check / stop-check (open) | Δp_crack/(ρg) + K·Q\|Q\|/(2gA²) | status in the outer loop |
| PRV / PSV / FCV (active) | fixed outlet static pressure / fixed inlet static pressure / fixed flow | the setpoint head includes the port's velocity head, updated every Newton step; the PRV/PSV flow is EPANET's lagged balance flow |
| Branch leg | head offset (Crane or Darby path loss) | §4.2, §5.4 |

**Valve K** (`valves.py`) is referenced to the inner diameter of the pipe connected to the valve's inlet port (its end segment). K is used as entered; Cv and Kv are converted with `fluids.fittings.Cv_to_K` / `Kv_to_K` (ISA-75.01.01; K = 1.6·10⁹·D⁴/Kv² with Kv = Cv/1.156…). A unit test derives the Crane form K = c·d⁴/Cv² (d in inches) from the Cv definition and exact unit definitions — c = 890.11 — which matches `fluids` to 7·10⁻¹¹ and the published coefficient 891 to 0.1%. Without a resistance: the Crane default for the valve type (`K_gate_valve_Crane`, `K_ball_valve_Crane`, `K_globe_valve_Crane`, `K_butterfly_valve_Crane(style=0)`, `K_swing_check_valve_Crane`, `K_globe_stop_check_valve_Crane(style=0)`), or an ideal control valve (K = 0 when fully open, stated in the trace). The butterfly valve's multiplier is tabulated for 2"–24" only (fluids docstring; `sizeRange` of the `butterfly_valve` fitting in `data/fittings.json`): a butterfly default or inline fitting outside 2–24 × 0.0254 m is flagged `CORRELATION_OUT_OF_RANGE`.

Links with zero slope (branch legs, K = 0 valves) are merged exactly as head offsets; a small Jacobian floor remains only for pumps with flat curves and for K > 0 valves near zero flow.

### 5.4 Outer Loop: Statuses and Branch Losses

`status.py`:

```
repeat (max 30):
    solve GGA with current statuses and branch losses
    update pump, check-valve and PRV/PSV/FCV statuses (EPANET 2.2 rules, hydstatus.c)
    update branch losses from the solved split (Crane K, tangent in the split)
until no status changed and branch K changed by < 1e-4
```

- **Pumps:** a running pump whose head rise would exceed s²·H₀(0) cannot deliver: its integral check holds zero flow (status `no_flow`, flag `PUMP_FLOW_REVERSAL`). A no-flow pump with one side closed off (a closed discharge check valve or foot valve) is reported dead-headed: head s²·H₀(0), the closed-off side's EGL the other side's ± s²·H₀(0); with both sides closed off it has no result but keeps its flag.
- **Check valves:** close when the flow would reverse or the head difference falls below the cracking head; reopen above it (EPANET `cvstatus` extended with the cracking head). Closed → `CHECK_VALVE_CLOSED` (info).
- **PRV/PSV/FCV:** EPANET 2.2 `prvstatus`/`psvstatus`/`fcvstatus` translated to EGL. Differences from EPANET: an FCV closes on reverse flow (EPANET lets it pass as an open valve); an active FCV opens once the head across it is below its fully open loss at the setpoint, K_open·Q_set²/(2gA²) (EPANET waits for a reverse head, which leaves a valve with a resistance "throttling" with a K below its fully open K); an active state with no solution falls back to open, then closed, one valve at a time. Not at setpoint → `CONTROL_VALVE_SETPOINT_NOT_MET` (info).
- **Closed-off sections:** a section cut off by closed elements (the pipe between a pump and a check valve that closed in the same pass) has no head, so its neighbours' rules cannot test it. The closed elements around it are re-tested against the heads it can take at zero flow: each stays closed only for some head (a pump while the far side is more than s²·H₀(0) above the near side, a check valve while its forward head is at most its cracking head, an FCV while it has no forward head, a PRV/PSV per its CLOSED rule), which are difference constraints between section heads; a negative cycle (Bellman–Ford) means no head keeps them all closed, and the elements on it are re-opened. EPANET avoids the question by keeping a 1/CBIG conductance across closed links.
- **Branches:** the Crane K is linearized in the flow split around the last split and re-centered each iteration (lagging the whole loss made Newton diverge on manifolds of short taps), and the leg's own-flow dependence enters the Jacobian. A leg whose flow would flip direction is held at zero flow while its head lies between the two patterns' zero-flow limits (facing legs of a rung are held as a pair, released one at a time). Where the split sits at a step of the Crane correlation (q = 0.4, 0.5, 0.6), K is held at the mean of the two sides and flagged; elsewhere the K update is under-relaxed.
- **Oscillation:** a repeated status/pattern state ends the loop with `converged: false`, the oscillating components named in the convergence report, and `NOT_CONVERGED`.

### 5.5 NPSH Available

`npsh.py`. At each pump suction port (elevation z_s, EGL H_s):

```
NPSHa = (H_s − z_s) + (p_atm − p_vap)/(ρg)      = absolute static head + velocity head − vapor head
NPSH margin = NPSHa − NPSHr(Q)                     (when an NPSHr curve is given; < 0 flags CAVITATION)
```

p_atm is `settings.atmosphericPressure` when set, else `fluids.atmosphere.ATMOSPHERE_1976(siteElevation).P` (US Standard Atmosphere 1976; 101 325 Pa at 0 m, 89 876 Pa at 1 000 m). Any node whose absolute static pressure is below the vapor pressure (or ≤ 0 Pa when none is known) is flagged `BELOW_VAPOR_PRESSURE`; a reservoir surface below its vapor pressure (a boiling tank) is flagged too.

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

**Location:** `apps/api/tests/reference/`. Each case in `cases/*.json` holds `name`, `description`, `source` (exactly where the expected values came from), `project` (API JSON) and `expected`: `fluid` (density, viscosity, optionally `vaporPressure`, null where the property source has none), `flows` per connection, `egl` per `componentId:portId` (every port except those in an isolated section), and optionally `pressures` (gauge static), `atmosphericPressure`, `pumps` (status, operating flow and head, NPSH available / required / margin), `valves` (state) and `flags`. One parameterized test (`test_reference_cases.py`) solves every case.

| Source | Use | Generator |
|--------|-----|-----------|
| Closed-form derivations | Single pipes (turbulent, laminar, transitional), fittings, series and parallel pipes, reducers in both directions, plugged branches, pressurized reservoirs and reference nodes, library pipe + built-in water | `derivations.py` (first principles: Darcy–Weisbach with `fluids.friction.Colebrook` — the Lambert-W solution, a different code path from the solver's Clamond — or 64/Re; fitting K from the cited `fluids.fittings` functions; SciPy `brentq`/`fsolve`) |
| Closed-form derivations (M3) | Pumps (single, reduced speed, beyond the curve, above shutoff, off, series, parallel, a pump and check valve re-opened after a control valve's first solve), isolation valves (Crane defaults, Cv, Kv, K, an isolated section), check valves (cracking pressure, reverse, below cracking, locked open in reverse flow, stop-check locked closed), PRV/PSV/FCV (active, open, closed, an FCV limited by its own open loss, failed open, failed closed), Crane tees and wyes (diverging, converging, dead branch, bullhead fallback, an ideal wye, a reversed lateral), glycols, overrides, NPSH and a siphon | `derivations_pumps.py`, `derivations_valves.py`, `derivations_branches.py`, `derivations_fluids.py`, sharing `element_laws.py` (component laws and status rules written from their definitions) and `line.py` (one-segment lines with fittings) |
| WNTR/EPANET (dev dependency) | Water-only looped networks; networks with a pump, a PRV, a PSV and an FCV | `generate_epanet_cases.py` (WNTR 1.5.0 EpanetSimulator = EPANET 2.2.0) |

`closed_form.py` lists every closed-form generator and `build_closed_form_cases.py` writes their files.

Rules: expected values are never computed with solver code (the suite imports only `opensolve_pipe.models`); `test_derivations_current.py` re-runs every derivation and WNTR run and fails if a JSON is stale; `test_derivation_checks.py` checks each derived solution independently (`network_check.py`): energy and mass balance, every component law in its expected state, the expected states against the status rules, and a whole-network `fsolve` that must reproduce each closed-form case.

**EPANET runs:** solver in `swamee_jain` mode; custom fluid with EPANET's water viscosity VISCOS = 1.1·10⁻⁵ ft²/s = 1.02193344·10⁻⁶ m²/s (`types.h`); ideal tees as junctions; D-W roughness passed to WNTR in metres; GPM INP units; accuracy 10⁻⁵, headerror 10⁻⁹ ft, flowchange 10⁻¹² gpm. Known biases, all far inside the criteria: EPANET uses g = 32.2 ft/s² (0.08% in head loss), a rounded minor-loss constant 0.02517 (0.01%), the GPM unit constant (−3.8·10⁻⁷) and float32 results. EPANET multi-point pump curves are piecewise linear, so pump cases use collinear points (PCHIP then coincides). EPANET's PRV/PSV setting is a head without velocity head, ours a static pressure, so the generator iterates setting = p_set/(ρg) + v²/(2g), v from the previous EPANET run in the pipe on the held port, until it changes by < 10⁻¹² m. An active EPANET FCV keeps a 1/CBIG conductance (CBIG = 10⁸, `fcvcoeff`) and settles at q_set + Δh/CBIG in ft and cfs (about 10⁻⁶ relative); the self-checks allow for that leak. The generator also lists the warning flags the pipes' friction regimes call for at the EPANET flows (`TRANSITIONAL_FLOW`) and refuses a pipe whose Reynolds number sits within 1% of a regime bound or outside Swamee–Jain's documented range.

**Pass criteria:** flows within 0.5% of the reference (floor 10⁻⁹ m³/s), EGL within 0.5% or 0.01 m (whichever is looser), and the EGL difference across every connection likewise; pressures within 0.5% or ρg·0.01 m; pump operating values and NPSH within 0.5% or 0.01 m; the expected pump statuses and valve states; ports with no expected EGL (an isolated section) must have no head, and a valve there with no result must be named by an `ISOLATED_SECTION` flag; every expected flag must be present, and warning and invalid flags are exhaustive (each one raised must be expected with its code and element; info flags may appear unlisted); mass balance checked independently from the link results at every component, plus the solver's own continuity residual. Every new component type ships with at least one reference case.

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

## 12. Implementation Questions

**Decided** (recorded in `CLAUDE.md` D7–D9):

1. **Tee and wye K correlation:** Crane TP-410 functions in `fluids.fittings`; Darby 3-K fallback for tees with the combined flow through the branch; uncovered wye patterns are not converged (§4.2).
2. **Water property package:** CoolProp 8.0.0, `Water` = IAPWS-95; glycols `INCOMP::MEG`/`MPG` (§4.6).
3. **Transition-zone friction (Re 2000–4000):** EPANET 2.2's Dunlop cubic, flagged as transitional; not a user option (§5.2).
4. **Pump curve fitting:** PCHIP through the user's points, straight end-slope extrapolation outside them (flagged), affinity laws (§5.3).
5. **Control-valve status oscillation:** at most 30 outer iterations; a repeated state returns `converged: false` naming the oscillating components (§5.4).

**Open (Later):**

1. **Schematic layout algorithm:** dagre, elkjs, or custom?
2. **Version storage:** git under the hood, or custom versioning in PostgreSQL?

*End of TSD*
