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

As built (`apps/web/package.json`; versions are those in `pnpm-lock.yaml` at v1):

| Layer | Technology | Use |
|-------|------------|-----|
| Framework | **SvelteKit 2** (2.70) / **Svelte 5** (5.57) | Runes mode is forced for every project file (`svelte.config.js` `compilerOptions.runes`); libraries keep their own setting |
| Build | Vite 8, `@sveltejs/vite-plugin-svelte` 7 | Dev server, build and preview |
| Output | `@sveltejs/adapter-static` 3 | Every page is prerendered to static HTML (`routes/+layout.ts`: `prerender = true`); the project page `/p` is rendered in the browser only (`routes/p/+page.ts`: `ssr = false`), because its data is in the fragment. No server code runs for the frontend |
| Language | TypeScript 6 | `strict`, `noUncheckedIndexedAccess` |
| Styling | Tailwind CSS 4 (`@tailwindcss/vite`) | Utilities plus a few component classes (`.btn`, `.input`, `.card`, …) in `src/routes/layout.css`; system fonts, no web fonts or other third-party assets |
| State | Svelte 5 runes classes in `.svelte.ts` modules (`ProjectStore`, `NavigatorStore`, `Workspace`, `LibraryStore`), passed down with `setContext` | §8.1, SDD §3.1.4 |
| API types | `openapi-typescript` 7 | `pnpm gen:types` writes `src/lib/api/openapi.json` (from the API's Pydantic models) and `schema.d.ts`; `types.ts` gives the generated types short names. Never edited by hand |
| Validation | Ajv 8 (JSON Schema 2020-12) | Decoded links checked against the `Project` schema in the generated `openapi.json` (§4.7) |
| Charts | Chart.js 4 | Pump chart only: line chart, linear scales, tooltip and legend registered (`results/chart-setup.ts`), loaded on demand |
| Compression | pako 3 | gzip, level 9 (§4.7) |
| Unit and component tests | Vitest 4, jsdom 27, `@testing-library/svelte` 5, `@testing-library/jest-dom` 6 | §10.3 |
| End-to-end tests | Playwright 1.56.1 (pinned exactly), Chromium | §10.3 |
| Lint and format | ESLint 10 (`typescript-eslint`, `eslint-plugin-svelte`, `eslint-config-prettier`), Prettier 3 (Svelte and Tailwind plugins), `svelte-check` 4 | §9.3 |
| Package manager | pnpm 10 (`packageManager: pnpm@10.28.0`), Node ≥ 22 (`engines`, enforced by `engine-strict=true` in `.npmrc`) | |
| Schematic (Later) | SVG + D3.js | Custom symbols, interactive elements |

The only runtime dependencies are `ajv` (MIT), `chart.js` (MIT) and `pako` (MIT AND Zlib), all compatible with AGPL-3.0-or-later; everything else is a dev dependency. The app makes no network requests other than to the OpenSolve Pipe API (SDD §3.1.4).

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
│   │   │   │   ├── api/
│   │   │   │   │   ├── openapi.json    # Generated: the API's OpenAPI document (pnpm gen:types)
│   │   │   │   │   ├── schema.d.ts     # Generated by openapi-typescript
│   │   │   │   │   ├── types.ts        # Short names for the generated types
│   │   │   │   │   └── client.ts       # API client (fetch), typed errors
│   │   │   │   ├── components/
│   │   │   │   │   ├── Home.svelte     # Home page; SiteFooter.svelte; links.ts (app links, disclaimer)
│   │   │   │   │   ├── workspace/      # Workspace layout, header, Share, project settings, fluid, link errors
│   │   │   │   │   ├── panel/          # Panel navigator: breadcrumb, path chooser, jump-to, component and
│   │   │   │   │   │   │               #   connection panels, add/delete dialogs, ports, pipes, fittings
│   │   │   │   │   │   └── forms/      # One form per component type; pump-curve editor
│   │   │   │   │   ├── results/        # Results pane: status, flags, tables, pump chart, trace view,
│   │   │   │   │   │                   #   methods summary
│   │   │   │   │   └── ui/             # Dialog, Icon (inline SVG), NumberField, SelectField, TextField
│   │   │   │   ├── state/              # Runes stores (*.svelte.ts): project (undo/redo, URL, results),
│   │   │   │   │                       #   navigator, workspace (edit actions), library (API reference data)
│   │   │   │   ├── utils/
│   │   │   │   │   ├── encoding.ts     # URL fragment encode/decode (§4.7)
│   │   │   │   │   ├── migrations.ts   # schemaVersion upgrades (§4.7)
│   │   │   │   │   ├── validate.ts     # Ajv schema check, port-graph and model-rule checks (§4.7)
│   │   │   │   │   ├── model-rules.ts  # Model rules read from openapi.json (x-port-ids, …; §4.7)
│   │   │   │   │   ├── link-error.ts   # Errors from opening a link
│   │   │   │   │   ├── units.ts        # Display-unit conversion and formatting (§6)
│   │   │   │   │   ├── graph.ts        # Port-graph traversal for the navigator (§8.1)
│   │   │   │   │   ├── edit.ts         # Graph edits: add, insert, branch, delete (and join), plug, connect
│   │   │   │   │   ├── factory.ts      # New projects, components and connections; ids
│   │   │   │   │   ├── examples.ts     # Example projects on the home page
│   │   │   │   │   ├── results.ts      # Results tables, flags and element names for display
│   │   │   │   │   ├── trace.ts        # Trace values and the methods text for display
│   │   │   │   │   ├── …               # flag-text, labels, piping, pump-chart, schema-bounds, media, scroll-focus
│   │   │   │   │   └── __fixtures__/   # schema-v<N>.txt (a shared link) and schema-v<N>.json (§4.7)
│   │   │   │   └── testing/            # Unit-test helpers and made-up results (not used by the app)
│   │   │   ├── routes/
│   │   │   │   ├── +layout.ts          # prerender = true
│   │   │   │   ├── +layout.svelte      # Imports layout.css (Tailwind and component classes)
│   │   │   │   ├── +page.svelte        # Home: new project, examples, privacy, disclaimer, license
│   │   │   │   └── p/
│   │   │   │       ├── +page.ts        # ssr = false
│   │   │   │       └── +page.svelte    # Project view; project read from location.hash
│   │   │   ├── app.html                # <meta name="referrer" content="no-referrer">
│   │   │   └── vitest-setup-client.ts  # jest-dom matchers; empty public env; no canvas in jsdom
│   │   ├── static/robots.txt
│   │   ├── scripts/gen-api-types.sh    # pnpm gen:types
│   │   ├── tests/                      # Playwright end-to-end tests (*.e2e.ts)
│   │   ├── playwright.config.ts
│   │   ├── vite.config.ts              # Vite plugins and the Vitest projects (§10.3)
│   │   ├── svelte.config.js            # adapter-static, runes mode
│   │   ├── eslint.config.js, prettier.config.js, tsconfig.json, .npmrc
│   │   ├── package.json
│   │   └── pnpm-lock.yaml
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

The project route is rendered in the browser only (`export const ssr = false` in `p/+page.ts`), since its data is in the fragment. What the page does:

- **Open.** On arrival (`afterNavigate`) and on every `hashchange`, it reads `location.hash` and calls `decodeProject` (§4.7). An empty fragment starts a new project (`createEmptyProject`) and writes its link into the URL. A fragment equal to the one the page last wrote is ignored, so the app's own URL writes do not reload the project.
- **Show.** A decoded project goes into a `Workspace` (a `ProjectStore`, a `LibraryStore` and a `NavigatorStore`, §8.1) rendered by `components/workspace/Workspace.svelte`. A link that cannot be opened shows `LinkErrorView` (§4.7) instead. If a project was already open, that view offers to go back to it, which writes the open project's link back into the URL.
- **Open another link in the same page.** The store loads the new project, with fresh undo history and no results. The walk restarts, the trace view closes and the Build pane is shown.
- **Write pending changes.** URL writes are debounced (§4.7). A pending write is flushed before an in-app navigation (`beforeNavigate`, except Back/Forward), on `pagehide` and when the page becomes hidden. That way, Back after leaving returns to the link with the latest edit.
- **Title.** The document title is `<project name> · OpenSolve Pipe`.

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
// Sketch. In apps/web, Port and PipeConnection are the types generated from the API schema
// (src/lib/api/schema.d.ts, named in types.ts), and new components get their ports from
// createComponent in src/lib/utils/factory.ts: the same port ids and directions, with one
// size for every port, which the user can change per port.

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

Code: `apps/web/src/lib/utils/encoding.ts`, `migrations.ts`, `validate.ts` and `link-error.ts`. The rules are in SDD §5.2.

**Encoding pipeline:**

```
Project object (SI, includes schemaVersion)
    ↓
canonical JSON (object keys sorted at every level, arrays in order; NaN and ±Infinity refused)
    ↓
UTF-8 bytes (TextEncoder)
    ↓
gzip (pako 3, level 9)
    ↓
base64url (URL-safe alphabet, no padding)
    ↓
https://opensolve-pipe.app/p#<encoded>        (the app writes /p#<encoded> on its own origin)
```

**Decoding pipeline:**

```
fragment: surrounding whitespace and a leading '#' removed
    ↓
base64url decode (only A–Z a–z 0–9 - _, and never a length of 1 mod 4)
    ↓
gunzip (pako) → UTF-8 decode (TextDecoder, fatal) → JSON.parse    any failure: LinkError 'corrupt'
    ↓
migrate(raw): from its schemaVersion to CURRENT_SCHEMA_VERSION     not an object or no positive integer
                                                                   schemaVersion: LinkError 'invalid';
                                                                   newer than the app: 'newer_version'
    ↓
parseProject: Ajv against the Project schema in openapi.json,      LinkError 'invalid', with every
fill schema defaults, port-graph reference checks                  problem found
    ↓
Project object
```

**Implementation** (tested: excerpt of `encoding.ts`; `encoding.test.ts`, `fixtures.test.ts`, `migrations.test.ts` and `validate.test.ts` run in Vitest on Node 22, §10.3). The base64url helpers match Node's built-in `base64url` for every length from 0 to 299 bytes and round-trip. Canonical JSON keeps nested fields, does not depend on key order and refuses non-finite numbers. Every example project round-trips. Truncated, damaged, non-gzip, non-JSON and non-UTF-8 links are all reported as corrupt.

```typescript
import { gzip, ungzip } from 'pako';

/** Links longer than this (in characters) may be cut short by some email and chat clients. */
export const URL_LENGTH_WARNING = 8000;

/** JSON with object keys sorted at every level, so equal projects encode identically. */
export function canonicalJson(value: unknown): string {
  return JSON.stringify(value, (key, v: unknown) => {
    if (typeof v === 'number' && !Number.isFinite(v)) {
      throw new TypeError(`Cannot encode the non-finite number ${v} (field "${key}")`);
    }
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      const record = v as Record<string, unknown>;
      return Object.fromEntries(Object.keys(record).sort().map((k) => [k, record[k]]));
    }
    return v;
  });
}

export function toBase64Url(bytes: Uint8Array): string {
  let binary = '';
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function fromBase64Url(text: string): Uint8Array {
  if (!/^[A-Za-z0-9_-]*$/.test(text) || text.length % 4 === 1) {
    throw new SyntaxError('Not a base64url string');
  }
  const b64 = text.replace(/-/g, '+').replace(/_/g, '/');
  const binary = atob(b64 + '==='.slice((b64.length + 3) % 4));
  return Uint8Array.from(binary, (c) => c.charCodeAt(0));
}

export function encodeProject(project: Project): string {
  return toBase64Url(gzip(new TextEncoder().encode(canonicalJson(project)), { level: 9 }));
}

export function decodeProject(encoded: string): Project {
  const text = encoded.trim().replace(/^#/, '');
  if (!text) throw new LinkError('corrupt', CORRUPT_LINK_MESSAGE);
  let raw: unknown;
  try {
    const json = new TextDecoder('utf-8', { fatal: true }).decode(ungzip(fromBase64Url(text)));
    raw = JSON.parse(json);
  } catch {
    throw new LinkError('corrupt', CORRUPT_LINK_MESSAGE);
  }
  const migrated = migrate(raw);
  try {
    return parseProject(migrated);
  } catch (error) {
    if (error instanceof ProjectValidationError) {
      throw new LinkError('invalid', INVALID_PROJECT_MESSAGE, error.problems);
    }
    throw error;
  }
}
```

The module also exports `projectPath(project)` (`/p#<encoded>`), `projectUrl(project, origin = 'https://opensolve-pipe.app')` and `fragmentOf(link)` (the text after the first `#`).

**pako 3.** pako 3 has no default export, and its inflate takes `toText: true` where pako 2 took `{ to: 'string' }`. The code therefore uses the named imports `gzip` and `ungzip` and converts text itself with `TextEncoder` and a fatal `TextDecoder`. As a result, a link whose bytes are not valid UTF-8 is reported as damaged instead of being decoded with replacement characters.

**Non-finite numbers.** `JSON.stringify` writes `NaN` and `±Infinity` as `null`, and such a link would fail validation when opened. `canonicalJson` throws instead, and input fields never store NaN (§6.2).

Do not use `JSON.stringify(project, Object.keys(project).sort())` for canonical ordering: an array replacer filters keys at **every** depth, so nested fields are silently dropped (verified: `{metadata: {name: 'Test'}}` encodes as `{"metadata":{}}`; `encoding.test.ts` checks that nested fields are kept).

**Migrations** (`migrations.ts`, excerpt):

```typescript
/** The project schema version this app writes. Must equal `Project.schemaVersion` in the API. */
export const CURRENT_SCHEMA_VERSION = 1;

/** MIGRATIONS[n] upgrades a project from version n to n + 1. Never remove an entry. */
export const MIGRATIONS: Readonly<Record<number, Migration>> = Object.freeze({});

export function migrate(raw: unknown, migrations = MIGRATIONS, currentVersion = CURRENT_SCHEMA_VERSION): RawProject {
  if (!isRecord(raw)) throw new LinkError('invalid', NOT_A_PROJECT_MESSAGE);
  const from = raw.schemaVersion;
  if (typeof from !== 'number' || !Number.isInteger(from) || from < 1) {
    throw new LinkError('invalid', NOT_A_PROJECT_MESSAGE);
  }
  if (from > currentVersion) {
    throw new LinkError('newer_version', newerVersionMessage(from, currentVersion));
  }
  let project = raw;
  for (let version = from; version < currentVersion; version++) {
    const step = migrations[version];
    if (!step) throw new Error(`No migration from project schema version ${version}`); // a bug, not a bad link
    project = { ...step(project), schemaVersion: version + 1 };
  }
  return project; // not validated here: decodeProject validates
}
```

Tests check that `CURRENT_SCHEMA_VERSION` equals the `schemaVersion` constant in the generated `openapi.json`, and that `MIGRATIONS` is frozen with exactly one entry for each version from 1 to `CURRENT_SCHEMA_VERSION − 1`.

**Validation** (`validate.ts`):

- **Schema.** `schemaProblems` checks the decoded value against the `Project` schema in `src/lib/api/openapi.json`, the document generated from the API's Pydantic models, so the browser checks the same schema as the API. It uses Ajv 8 (`Ajv2020`, `allErrors`, `strict`); `discriminator`, `components` and every `x-` extension in the schemas are declared as annotation keywords. A `oneOf` member (component, fluid) is reported against the schema its tag names (`type`, then `branchType` or `valveType`; fluid `kind`), read from the members of the `Project.components` and `Project.fluid` unions, not against every alternative. Each problem is a sentence that names the element, e.g. `components[0] "R1" › liquidLevel: must be >= 0`.
- **Defaults.** `parseProject` fills in fields the schema gives defaults for, as the API does, so the result satisfies the generated `Project` type.
- **Port graph.** `referenceProblems` checks that ids are unique, that every connection end names an existing component and port, and that each port has at most one connection. A link with any of these problems does not open.
- **Model rules.** `modelRuleProblems` checks the rules the API models enforce in validators, which JSON Schema cannot express: the port ids or count per component type, the pipe size source, fitting parameters and reducer positions, increasing curve flows, the FCV setpoint range, pump-curve references and ids shared by a component and a connection (the API's `DUPLICATE_ID`). The rules come from the schema, never from a copy: `model-rules.ts` reads the models' extensions (`x-port-ids`, `x-port-roles`, `x-port-count`, `x-required-parameters`, `x-reducer-types`, `x-entrance-types`, `x-exit-types`, `x-setpoint-bounds`, SDD §5.1) and the ports bound, and the navigator's port roles, the piping editor, the ports editor and the control-valve form use the same functions. `model-rules.test.ts` fails if the app's rules and the schema's disagree; the API's `test_schema_rules.py` fails if an extension and its validator disagree or `openapi.json` is stale. A link that breaks only these still opens. The results pane lists the problems, and the solver reports them too.

**Link errors** (`link-error.ts`): `LinkError.kind` is `corrupt` ("This link is incomplete or damaged … some email and chat apps cut long links short"), `newer_version` (names both format versions and says to reload for the latest app) or `invalid` (with `problems`). `LinkErrorView` shows the message and up to 20 problems. It offers to go back to the project that was open, to start a new project or to go home.

**Fixture links.** Every released schema version keeps a fixture in `apps/web/src/lib/utils/__fixtures__/`: `schema-v<N>.txt` holds a full shareable link and `schema-v<N>.json` the project it holds. For v1 these are `schema-v1.txt` (`https://opensolve-pipe.app/p#H4sI…`, 1,812 characters) and `schema-v1.json`, a small but complete project. `fixtures.test.ts` checks:

- a fixture pair exists for every version from 1 to `CURRENT_SCHEMA_VERSION`;
- each link decodes to exactly its JSON, migrated and validated, with no model-rule problems;
- `schema-v1.txt` is a full `https://opensolve-pipe.app/p#…` link;
- re-encoding `schema-v1.json` reproduces the link byte for byte, with gzip header XFL = 2 (maximum compression);
- the SHA-256 of the trimmed text of `schema-v1.txt` is pinned to `2f192eee9b2251c0c0f2beacde603a62154f231d9a9121496c000ec9aa3c8954`.

A committed fixture link is never regenerated, even together with its JSON. If the hash test fails, restore the file instead of updating the hash. A schema change needs a new version, a migration and a new fixture (`schema-v2.txt`), never a new `schema-v1.txt`.

**Writing the URL** (`state/project.svelte.ts`, `ProjectStore`):

- Each change replaces the current history entry's URL with `/p#<encoded>` (`history.replaceState`, keeping SvelteKit's state), after a 300 ms debounce, so one link is written per burst of edits.
- `flush()` writes a pending change at once. It runs before Share, before in-app navigation and when the page is hidden (§3.2).
- The full link is `location.origin + '/p#' + encoded`, or `https://opensolve-pipe.app` when the origin is unknown. `urlTooLong` is true when the full link is longer than `URL_LENGTH_WARNING` characters.

---

## 5. Solver Implementation

### 5.1 Overview

One solver handles every topology (D1). Code: `apps/api/src/opensolve_pipe/services/solver/`; entry point `solve_project(project, options) -> SolvedState`.

1. **Validate topology** (`builder.py`): every problem is collected and raised together as `TopologyError(issues)` (HTTP 422): `DUPLICATE_COMPONENT_ID`, `DUPLICATE_CONNECTION_ID`, `DUPLICATE_ID` (an id naming both a component and a connection: results, traces and flags share one id space), `DUPLICATE_PUMP_CURVE_ID`, `UNKNOWN_COMPONENT`, `UNKNOWN_PORT`, `UNKNOWN_PUMP_CURVE`, `UNKNOWN_PIPE_MATERIAL`, `UNKNOWN_PIPE_SCHEDULE`, `UNKNOWN_PIPE_SIZE`, `ROUGHNESS_OUT_OF_RANGE`, `PIPE_SIZE_OUT_OF_RANGE` (a pipe whose resistance coefficients are not finite floating-point numbers, e.g. an inner diameter of 1e-100 m), `SELF_CONNECTION`, `PORT_CONNECTED_TWICE`, `UNCONNECTED_PORT` ("connect it or add a plug") and `NO_FIXED_HEAD` (a connected sub-network without a reservoir or reference node; also an empty project).
2. **Build the solver network** (`builder.py`, `network.py`): one node per component port at the port's effective elevation; one link per `PipeConnection` (its segments in series and its fittings); one link per pump and valve between its port nodes; a branch component adds a center node and three legs (center → port).
3. **Fixed heads:** reservoir ports get H = z + liquidLevel + surfacePressure/(ρg); ideal reference nodes get H = z_port + p/(ρg) (a body of liquid at rest at that pressure).
4. **Solve** with the GGA inner loop (§5.2) inside the outer loop for statuses and branch losses (§5.4).
5. **Map results** (`results.py`) to `SolvedState` (SDD §4.10), with physics flags, the per-element trace and the methods summary (§5.6).

**The nodal unknown is the energy grade line** H = z + p/(ρg) + v²/(2g). Every link's energy equation is H_from − H_to = h(Q), so pump head (an EGL rise) and fitting losses are exact. At a port, v is the velocity in the connected pipe's end segment; static pressure p = ρg(H − z − v²/2g), HGL = H − v²/2g. Boundary ports (reservoirs, reference nodes) report the quiescent boundary (v = 0). EPANET neglects velocity heads, so its nodal head corresponds to our EGL; EPANET comparisons compare EGL and flows.

### 5.2 GGA Core

`gga.py` implements the Global Gradient Algorithm (Todini & Pilati, 1988) generalized from the tested sketch that was in this section (pipes only): links supply h(Q) and dh/dQ (`elements.py`); the Schur-complement system A21·D⁻¹·A12·dH = rhs is assembled with `scipy.sparse` and solved with SuperLU (`splu`, which raises on an exactly singular matrix; `spsolve` only warns, and a warning is subject to process-wide filters that other libraries change — wntr turns this one into an error); flows are back-substituted. A diverging iterate is detected by finiteness checks, with numpy's overflow warnings off (`np.errstate`, thread-safe).

- **Friction** (`friction.py`): laminar Re < 2000, f = 64/Re (exact linear law, finite slope at Q = 0); turbulent Re ≥ 4000, exact Colebrook via `fluids.friction.Clamond` (`colebrook`, default) or Swamee–Jain in the exact form EPANET 2.2 evaluates, 5.74/Re^0.9 (`swamee_jain`, for EPANET comparisons; `fluids.Swamee_Jain_1976` writes 6.97^0.9 = 5.73997 and differs by ~2·10⁻⁶ in f); transition 2000 ≤ Re < 4000, the cubic Hermite interpolation in R = Re/2000 between the laminar value and slope at 2000 and the turbulent formula's value and slope at 4000 — EPANET 2.2's Dunlop polynomial (`hydcoeffs.c` frictionFactor), reproduced to 10⁻¹⁴ in `swamee_jain` mode. Transitional segments are flagged `TRANSITIONAL_FLOW`. Never call `fluids.friction.friction_factor` (it switches to 64/Re at Re 2040 with a 57% jump). Range flags: Swamee–Jain outside 5·10³ ≤ Re ≤ 10⁸ or 10⁻⁶ ≤ ε/D ≤ 0.05; Colebrook above ε/D = 0.05 (`fluids.friction.fmethods`).
- **Newton slopes** include df/dQ. Swamee–Jain differs from exact Colebrook by up to **3.0%** in f within its documented range (probe: Re 5000, ε/D 0.0189).
- **Branch legs carry head offsets** (zero for an ideal tee, the Crane path loss otherwise, §5.4). They are not iterated: each branch's center and port nodes become one head unknown with fixed offsets, and leg flows are rebuilt from continuity after every Newton step. (A Jacobian floor on zero-slope links stalled Newton on a large main feeding small-bore tubing.) `jacobian_slopes` keeps a small positive floor only for zero-slope pumps and valves.
- **Isolated sections** (nodes not connected to a fixed head through open links) are removed before solving; their links carry zero flow and their ports are reported without heads (`ISOLATED_SECTION`, info) — if they can sit at zero flow: their open links' zero-flow heads h(0) (−s²H₀(0) across a running pump, the cracking head across an open check valve, 0 otherwise) must close up around every loop, and no active FCV may force flow around one.
- **Floating sections:** a section that no fixed head reaches but that cannot sit at zero flow (a pump loop behind a closed valve) is solved with one node held at an arbitrary head: its flows and head differences are exact, its pressure level undetermined. Its flows, head losses and pump and valve operating points are reported; its EGLs, pressures, NPSH available and PRV/PSV setpoint checks are not, and `UNDETERMINED_PRESSURE` (warning) names it. (EPANET gives such a loop the heads its closed links leak to it through their 1/CBIG conductance.)
- **Held nodes** (active PRV / PSV): the valve passes exactly the flow of the pipe on its held port, so the continuity row of its other port carries that pipe's flow in the Newton step (a non-symmetric Schur matrix). EPANET lags this flow by one iteration, which converges only linearly, too slowly for 100 iterations when most of the flow returns to the valve around a loop. A held node fixes a head, but its valve's flow is determined only if it can leave towards a fixed head; when the valve's other side reaches no fixed head but through the valve itself (an active PSV as the only anchor of a pump loop), any loop flow holds the setpoint: the inner solve is not attempted and names the valve (the outer loop opens or closes it, as EPANET's badvalve).
- **Initial flows:** 1 ft/s (0.3048 m/s) in every pipe, as EPANET.
- **Convergence:** max |dQ| ≤ tolerance × max |Q| of the current iterate, continuity residual ≤ 10⁻⁹ × max |Q| + 10⁻¹⁴ m³/s at every node and summed over every component's nodes (the balance a user checks from the connection flows, which two port residuals of opposite sign could otherwise double), energy residual ≤ 10⁻⁷ m on every link (residuals of the returned state). `tolerance` and `maxIterations` come from `project.settings.solverOptions`.
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
| PRV / PSV / FCV (active) | fixed outlet static pressure / fixed inlet static pressure / fixed flow | the setpoint head includes the port's velocity head, updated every Newton step; the PRV/PSV flow is the flow of the pipe on its held port, coupled exactly in the Newton step (§5.2) |
| Branch leg | head offset (Crane or Darby path loss) | §4.2, §5.4 |

**Valve K** (`valves.py`) is referenced to the inner diameter of the pipe connected to the valve's inlet port (its end segment). K is used as entered; Cv and Kv are converted with `fluids.fittings.Cv_to_K` / `Kv_to_K` (ISA-75.01.01; K = 1.6·10⁹·D⁴/Kv² with Kv = Cv/1.156…). A unit test derives the Crane form K = c·d⁴/Cv² (d in inches) from the Cv definition and exact unit definitions — c = 890.11 — which matches `fluids` to 7·10⁻¹¹ and the published coefficient 891 to 0.1%. Without a resistance: the Crane default for the valve type (`K_gate_valve_Crane`, `K_ball_valve_Crane`, `K_globe_valve_Crane`, `K_butterfly_valve_Crane(style=0)`, `K_swing_check_valve_Crane`, `K_globe_stop_check_valve_Crane(style=0)`), or an ideal control valve (K = 0 when fully open, stated in the trace). The butterfly valve's multiplier is tabulated for 2"–24" only (fluids docstring; `sizeRange` of the `butterfly_valve` fitting in `data/fittings.json`): a butterfly default or inline fitting outside 2–24 × 0.0254 m is flagged `CORRELATION_OUT_OF_RANGE`.

Links with zero slope (branch legs, K = 0 valves) are merged exactly as head offsets; a small Jacobian floor remains only for pumps with flat curves and for K > 0 valves near zero flow.

### 5.4 Outer Loop: Statuses and Branch Losses

`status.py`:

```
repeat (max 30 counted; iterations that only hold or release zero-flow branch legs are not counted):
    solve GGA with current statuses and branch losses
    update pump, check-valve and PRV/PSV/FCV statuses (EPANET 2.2 rules, hydstatus.c)
    update branch losses from the solved split (Crane K, tangent in the split)
until no status changed and branch K changed by < 1e-4
```

- **Pumps:** a running pump whose head rise would exceed s²·H₀(0) cannot deliver: its integral check holds zero flow (status `no_flow`, flag `PUMP_FLOW_REVERSAL`). A no-flow pump with one side closed off (a closed discharge check valve or foot valve) is reported dead-headed: head s²·H₀(0), the closed-off side's EGL the other side's ± s²·H₀(0); with both sides closed off it has no result but keeps its flag.
- **Check valves:** close when the flow would reverse or the head difference falls below the cracking head; reopen above it (EPANET `cvstatus` extended with the cracking head). Closed → `CHECK_VALVE_CLOSED` (info).
- **PRV/PSV/FCV:** EPANET 2.2 `prvstatus`/`psvstatus`/`fcvstatus` translated to EGL. Differences from EPANET: an FCV closes on reverse flow (EPANET lets it pass as an open valve); an active FCV opens once the head across it is below its fully open loss at the setpoint, K_open·Q_set²/(2gA²) (EPANET waits for a reverse head, which leaves a valve with a resistance "throttling" with a K below its fully open K); an active state with no solution falls back first to the states the valve rules give at that solve's last finite iterate within 10 iterations (EPANET 2.2 applies the PRV/PSV rules at every iteration, so a valve whose setting cannot hold leaves its active state before the iteration diverges), then to open, then closed, one valve at a time. A PRV or PSV inside a closed-off or floating section, or closed between two such sections, compares its setpoint with their free levels: it closes on reverse flow, and otherwise these valves keep their states if one set of levels holds them all while the closed elements around the sections stay closed (each valve state holds on a union of regions of difference constraints, below; the choices are enumerated, up to 4,096 Bellman–Ford tests). If none does, the fewest elements are let go, the PRVs and PSVs first, then the closed elements, preferring a result not already solved: at levels that hold the others, each takes the state its rule gives there, except that a PRV or PSV that cannot be active (the side it draws from or delivers to reaches no fixed head) closes if it was open and opens if it was closed. Not at setpoint → `CONTROL_VALVE_SETPOINT_NOT_MET` (info).
- **Closed-off sections:** a section cut off by closed elements (the pipe between a pump and a check valve that closed in the same pass) has no head, so its neighbours' rules cannot test it. The closed elements around it are re-tested against the heads it can take at zero flow: each stays closed only for some head (a pump while the far side is more than s²·H₀(0) above the near side, a check valve while its forward head is at most its cracking head, an FCV while it has no forward head, a PRV/PSV per its CLOSED rule), which are difference constraints between section heads; a negative cycle (Bellman–Ford) means no head keeps them all closed, and the elements on it are re-opened. A floating section is tested the same way, its heads the solved relative heads plus a free level. A pump, check valve or FCV with both ports in one such section follows its rules with the section's heads (a pump held at no flow inside a closed-off loop sees no head across it there and re-opens). EPANET avoids the question by keeping a 1/CBIG conductance across closed links.
- **Branches:** the Crane K is linearized in the flow split around the last split and re-centered each iteration (lagging the whole loss made Newton diverge on manifolds of short taps), and the leg's own-flow dependence enters the Jacobian. A leg whose flow reverses and reverses back (patterns A, B, A in successive updates) is held at zero flow while its head lies between the two patterns' zero-flow limits (facing legs of a rung are held as a pair, released one at a time). These holds and releases change a finite active set (each branch is held at most twice per solve), so the iterations that make them are not counted against the 30: in a long Crane-tee ladder the rung legs join the reversals a few at a time, and the counted iterations stay at a handful while the total grows with length. Where the split alternates across a step of a Crane correlation (a split at which the fluids function switches formula, q = 0.4, 0.5 or 0.6, and K actually jumps by more than 1e-4 at that β and angle) while pump and valve statuses stay the same, K is held at the mean of the fluids values at the two splits (both reported in the trace) and flagged, until the solved split leaves the interval between them or a status changes; elsewhere the K update is under-relaxed.
- **Oscillation:** statuses that change together can step over the state that holds them all (a PSV and a pump, each rule reacting to the other's previous state). The first time pump and valve statuses return to a state already solved, the loop goes back to the state just solved and from then on changes one status per outer iteration (the first, by component id, that leads to a state not yet tried). A state repeated after that ends the loop with `converged: false`, the oscillating components named in the convergence report, and `NOT_CONVERGED`.

### 5.5 NPSH Available

`npsh.py`. At each pump suction port (elevation z_s, EGL H_s):

```
NPSHa = (H_s − z_s) + (p_atm − p_vap)/(ρg)      = absolute static head + velocity head − vapor head
NPSH margin = NPSHa − NPSHr(Q)                     (when an NPSHr curve is given; < 0 flags CAVITATION)
```

p_atm is `settings.atmosphericPressure` when set, else `fluids.atmosphere.ATMOSPHERE_1976(siteElevation).P` (US Standard Atmosphere 1976; 101 325 Pa at 0 m, 89 876 Pa at 1 000 m). Any node whose absolute static pressure is below the vapor pressure (or ≤ 0 Pa when none is known) is flagged `BELOW_VAPOR_PRESSURE`; a reservoir surface below its vapor pressure (a boiling tank) is flagged too.

### 5.6 Trace, Methods Summary and System Curves

- **Trace** (`trace.py`, shape in SDD §4.10; pipes, fittings and curve points numbered from 1 as in the app, `labels.py`): built after the results from the values the solver used, one `ElementTrace` per component and connection — inputs with their source (user / default / library / computed), equations as plain text, correlations and data sources with citations, intermediates (restating the result fields, or following from them by the listed equations) and notes (regime, state and the rule behind it, assumptions, flags). Unit strings are the ones `apps/web/src/lib/utils/trace.ts` converts (`Pa(g)`, `Pa(a)`, `Pa (difference)`, never bare `Pa`). Elements with no result (closed off, or a solve that did not converge) keep inputs, equations and sources with a note.
- **Methods summary** (`methods.py`): one `MethodsSummary` per solve — sections Network solution, Pipe friction, Minor losses, Branches, Pumps, Valves, Fluid properties, Atmosphere and NPSH, Conventions; global assumptions; library versions (opensolve-pipe, fluids, CoolProp, numpy, scipy) and `METHOD_VERSION`. Every number in it is a solver constant or a value of the solve.
- **System curve** (`system_curve.py`): at each flow the pump's link becomes a `FIXED_FLOW` link (`run_outer_loop(..., forced_flows={pump: Q})`; the pump takes no part in the status rules, every other element follows its own), and H_sys(Q) = EGL(discharge) − EGL(suction). Default flows 0 … 1.2 × the curve's largest flow × s. A point whose solve does not converge, or whose forced flow has no way through (a side reaching no fixed head), has no head. `POST /api/v1/system-curve` returns every point with `converged` and a message; `SolveOptions.includeSystemCurve` fills `PumpResult.systemCurve` of each running pump with its converged points. The web app solves with `includeSystemCurve: false` and requests one pump's curve when its chart is shown (CLAUDE.md D10, SDD §3.1.3); every pump's trace carries the H_sys definition (`trace.SYSTEM_CURVE_EQUATION`), and a solve that computes the curves adds a note on how many points were solved. Closed-form tests: `tests/reference/test_system_curves.py` (single line, series and parallel pumps with the other pump running).
- **Flag severities** are fixed per code (`flags.FLAG_SEVERITY`); `make_flag` rejects a mismatch, and `tests/unit/test_flags_audit.py` checks each GOALS §4.6 condition.

---

## 6. Unit Conversion System

Conversions happen only in the frontend, where a value is typed in or shown (D4). The backend, the stored project and the URL use SI. Changing a unit preference changes nothing that is stored except `settings.units`, and does not make results out of date (SDD §3.1.4).

### 6.1 Unit Registry

**File:** `apps/web/src/lib/utils/units.ts` (tested in `units.test.ts`). Each unit has `value_SI = value × factor + offset`, `toSI(value, unit)` and `fromSI(value, unit)` apply it, and an unknown unit id throws a `RangeError`.

Every factor is exact by definition. The sources are NIST SP 811 (2008), Appendix B, and the international yard and pound agreement (1959): 1 ft = 0.3048 m, 1 in = 0.0254 m and 1 lb = 0.45359237 kg. The pound-force uses standard gravity, g_n = 9.80665 m/s² (3rd CGPM, 1901). The US gallon is 231 in³, the mechanical horsepower is 550 ft·lbf/s and the poise is 0.1 Pa·s. The code builds each factor from these constants; it does not use rounded decimals.

| Unit id | Label | SI unit | Factor (offset) |
|---------|-------|---------|-----------------|
| `m`, `mm`, `ft`, `in` | m, mm, ft, in | m | 1; 10⁻³; 0.3048; 0.0254 |
| `Pa`, `kPa`, `MPa`, `bar` | Pa, kPa, MPa, bar | Pa | 1; 10³; 10⁶; 10⁵ |
| `psi` | psi | Pa | lbf/in² = 0.45359237 × 9.80665 / 0.0254² = 6 894.757 293 168… |
| `m3/s`, `m3/h`, `L/s`, `L/min` | m³/s, m³/h, L/s, L/min | m³/s | 1; 1/3600; 10⁻³; 10⁻³/60 |
| `gpm` | gpm | m³/s | US gal/min = 231 × 0.0254³ / 60 = 6.309 019 64 × 10⁻⁵ |
| `m/s`, `ft/s` | m/s, ft/s | m/s | 1; 0.3048 |
| `K` | K | K | 1 |
| `C` | °C | K | 1 (offset 273.15) |
| `F` | °F | K | 5/9 (offset 459.67 × 5/9), i.e. K = (°F + 459.67) × 5/9 |
| `kg/m3`, `lb/ft3` | kg/m³, lb/ft³ | kg/m³ | 1; 0.45359237 / 0.3048³ = 16.018 463 37… |
| `Pa.s`, `mPa.s`, `cP` | Pa·s, mPa·s, cP | Pa·s | 1; 10⁻³; 10⁻³ |
| `W`, `kW`, `hp` (display only) | W, kW, hp | W | 1; 10³; 550 × 0.3048 × 4.4482216152605 = 745.699 871 58… |
| `''`, `%`, `deg` (fixed) | (none), %, ° | — | 1; 0.01 (a stored fraction shown as a percentage); 1 |

Head is a length (m or ft of the flowing liquid) with the length factors. The app never shows a pressure as a head of liquid, so no conversion depends on density. Gauge and absolute are not units: converting between them needs the atmospheric pressure, which only the solver applies (D4). The solver reports both where both are meaningful (`NodeResult.pressure` and `absolutePressure`).

**Trace values** (`utils/trace.ts`) are converted by their unit string alone:

- `m`, `m³/s`, `m/s`, `kg/m³`, `Pa·s` and `W` go to the display unit. A value in `m` is shown in the diameter, head or length unit according to its name.
- `Pa(g)` is shown as gauge and `Pa(a)` as absolute; `Pa (difference)` has no marker.
- A bare `Pa` is shown with "(reference not stated)", unless its name states the reference or names a difference.
- `K` and anything else are shown as reported, because a kelvin value may be a temperature or a temperature difference.

Where the display differs from the SI value, the trace view shows the SI value as reported too.

### 6.2 Unit Preferences and Pressure Reference

`UnitPreferences` is the generated API type (`settings.units`, schema `UnitPreferences`). Its enums are exactly the unit ids above, and `units.test.ts` checks that `CATEGORY_UNITS` matches them:

| Category | Unit ids (API enum) | SI preset (API default) | Imperial preset |
|----------|--------------------|-------------------------|-----------------|
| `length` (lengths and elevations) | `m`, `mm`, `ft`, `in` | `m` | `ft` |
| `diameter` (pipe diameter and roughness) | `mm`, `m`, `in` | `mm` | `in` |
| `pressure` | `Pa`, `kPa`, `MPa`, `bar`, `psi` | `kPa` | `psi` |
| `head` | `m`, `ft` | `m` | `ft` |
| `flow` | `m3/s`, `m3/h`, `L/s`, `L/min`, `gpm` | `L/s` | `gpm` |
| `velocity` | `m/s`, `ft/s` | `m/s` | `ft/s` |
| `temperature` | `K`, `C`, `F` | `C` | `F` |
| `density` | `kg/m3`, `lb/ft3` | `kg/m3` | `lb/ft3` |
| `viscosity` | `Pa.s`, `mPa.s`, `cP` | `mPa.s` | `cP` |

Project settings offer the SI and Imperial (US customary) presets and a unit per category. A mix of the two is shown as "mixed". Power has no preference: `displayUnit('power', prefs)` is `hp` when flow is shown in `gpm`, otherwise `kW`. Fractions (efficiency) are shown in `%` and angles in `°`.

**Gauge and absolute labels.** Every pressure input and output is gauge (D4), and `unitLabel(category, unit, {gauge | absolute})` marks the reference:

| Unit | Gauge | Absolute |
|------|-------|----------|
| `psi` | `psig` | `psia` |
| `Pa`, `kPa`, `MPa`, `bar` | `Pa(g)`, `kPa(g)`, `MPa(g)`, `bar(g)` | `Pa(a)`, `kPa(a)`, `MPa(a)`, `bar(a)` |

- **Gauge:** reservoir surface pressure, reference-node pressure, PRV/PSV setpoints and the node pressure column.
- **Absolute:** the atmospheric-pressure override and the value used, vapor pressure (fluid settings, override and summary), the node absolute-pressure column, and the absolute pressures in flag texts.
- **Differences** (valve pressure drop, `Pa (difference)` in traces) have no marker.

The nodes view explains that gauge pressure is relative to the atmosphere at the site (the value used, shown absolute) and absolute pressure is relative to vacuum. NPSH available, required and margin are heads, shown in the head unit.

**Display and input.**

- **Results.** `formatResultNumber` shows 4 significant figures. Heads, elevations and lengths get at least 0.01 m resolution, or finer where 4 significant figures are finer (D6 checks heads to 0.01 m). Very small or large numbers are written as `2.555×10⁻⁶`. A missing value is shown as `—`, and head differences below the solver's energy tolerance are shown as `≈ 0`.
- **Spacing.** `formatValue` puts a space before the unit symbol, except for the degree of angle (NIST SP 811 §7.2).
- **Inputs.** `NumberField` shows the stored SI value in the display unit to 6 significant figures. When its text is changed, it parses the text with `parseNumber` (an optional sign, decimals and an exponent; anything else, including an empty string, is `null`, so NaN is never produced), converts it to SI and checks the schema bounds (`schema-bounds.ts`, read from `openapi.json`). It then stores the SI value. Text left as shown stores nothing, so a value is never rounded to its display. An empty optional field stores `null`.

---

## 7. API Endpoints

### 7.1 Solve and System-Curve Endpoints

**File:** `apps/api/src/opensolve_pipe/routers/solve.py` (request and response models in `models/api.py`; SDD §5.1).

```python
@router.post("/solve", response_model=SolveResponse, responses=_ERRORS)
async def solve_network(request: SolveRequest) -> SolveResponse:
    start = time.perf_counter()
    # TopologyError -> 422 and FluidError -> 400 by exception handlers in main.py.
    state = await asyncio.to_thread(solve_project, request.project, request.options)
    return SolveResponse(success=state.converged, solved_state=state,
                         compute_time=time.perf_counter() - start)


@router.post("/system-curve", response_model=SystemCurveResponse, responses={**_ERRORS, 404: ...})
async def system_curve_endpoint(request: SystemCurveRequest) -> SystemCurveResponse:
    # PumpNotFoundError -> 404 NOT_FOUND, FlowRangeError -> 400 VALIDATION_ERROR (main.py).
    curve = await asyncio.to_thread(system_curve, request.project, request.pump_id,
                                    flow_min=request.flow_min, flow_max=request.flow_max,
                                    num_points=request.num_points)
    ...  # one SystemCurvePoint {flow, head | None, converged, message} per flow
```

`SolveOptions {includeSystemCurve = true, systemCurvePoints = 41}` only adds system curves; options that change results live in `project.settings.solverOptions`. The curves cost a network solve per point for every running pump, so a solve that asks for them can miss the PRD §4.2 solve times a plain solve meets: the web app always sends `includeSystemCurve: false` and fetches the curve of the pump being viewed from `/system-curve`, with the project exactly as solved, one request at a time, cached with that solve (`ProjectStore.loadSystemCurve`, CLAUDE.md D10).

**Fluid properties** (`routers/fluids.py`): `POST /api/v1/fluids/properties` takes a `FluidDefinition` in the body (the union the project's `fluid` uses) and returns `FluidPropertiesResponse`, overrides applied; the web app uses it, so no fluid value is ever in a URL. `GET /api/v1/fluids/{id}/properties?temperature=&concentration=` stays for API users; its query values can appear in intermediaries' logs (SDD §5.1).

---

## 8. Frontend Components

### 8.1 Panel Navigator

The navigator walks the port graph one component at a time (SDD §3.1.1). The code is in four places:

- `src/lib/utils/graph.ts`: pure graph helpers, which never modify the project.
- `src/lib/state/navigator.svelte.ts`: `NavigatorStore`, the walk.
- `src/lib/state/workspace.svelte.ts`: `Workspace`, the edit actions, each of which also moves the walk.
- `src/lib/components/panel/`: the UI.

**Graph helpers** (`graph.ts`, excerpt):

```typescript
/** One step of the navigator's breadcrumb. */
export interface NavigationStep {
  componentId: string;
  viaConnectionId?: string; // connection used to arrive here (absent for the start)
}

/** A connection attached to a component, seen from that component. */
export interface Neighbor {
  connection: PipeConnection;
  portId: string;      // port of this component
  otherId: string;     // component at the other end
  otherPortId: string;
  outgoing: boolean;   // this component is the connection's 'from' end
}

/** A way forward from the end of the navigator's path. */
export interface NextOption extends Neighbor {
  loop: boolean;       // leads back to a component already on the path
  loopIndex?: number;  // for a loop: index in the path of that component
}

/**
 * Ways forward: connections of the current component other than the one used to arrive.
 * Those leading to a component already on the path are loop options (jump back).
 * Connections from the current component back to itself are not options.
 */
export function nextOptions(project: Project, path: readonly NavigationStep[]): NextOption[] {
  const current = path[path.length - 1];
  if (!current) return [];
  const index = new Map<string, number>();
  path.forEach((step, i) => index.set(step.componentId, i));
  return neighbors(project, current.componentId)
    .filter((n) => n.connection.id !== current.viaConnectionId && n.otherId !== current.componentId)
    .map((n) => {
      const loopIndex = index.get(n.otherId);
      return loopIndex === undefined ? { ...n, loop: false } : { ...n, loop: true, loopIndex };
    });
}
```

The other helpers:

- `neighbors` lists a component's connections in its port order.
- `defaultStart` is the first reservoir or reference node, else the first component.
- `reachable` and `pathTo` are breadth-first: `pathTo` gives the fewest connections from the start as navigator steps.
- `validPathPrefix` is the longest prefix of a path that is still valid: every component exists and each step's connection joins it to the previous one.
- `freePorts`, `connectionAtPort` and `otherEnd` are port lookups.
- `portRole` gives a port's flow role: `in` or `out` from its direction or standard name, `any` for boundaries and plugs. It only orients new connections; the solver decides the actual flow direction.

**Navigator state** (`NavigatorStore`):

| Member | Meaning |
|--------|---------|
| `path` | The breadcrumb. It is derived from the stored walk on every read: the stored walk is cut to `validPathPrefix` in the current project, or replaced by a new walk from `defaultStart` when nothing of it is left. After an edit, undo or redo the path is cut back to what still exists, and it comes back if an undo restores it |
| `current`, `startId`, `arrivalConnectionId` | The last step's component, the first step, and the connection the walk arrived by |
| `options` | `nextOptions(project, path)` |
| `mode` | `'component'` (Properties tab) or `'connection'` (Piping tab), remembered only for the component it was chosen on |
| `activePortId`, `activeConnection` | The port whose connection the Piping tab shows: the chosen one, else the first port other than the arrival port |
| `next()` | One way forward that is not a loop: take it and return `'moved'`. Several ways, or any loop: return `'choose'` (the UI opens the path chooser). None: return `'none'` |
| `choose(option)` | Extend the path. A loop option instead cuts the path back to `loopIndex` (jump back) |
| `previous()`, `goToStep(i)` | Step back one step, or back to breadcrumb step `i` |
| `jumpTo(id)` | Go back along the path if the component is on it; else follow the shortest path from the start (`pathTo`); else start a new walk at it (a part not connected to the start) |
| `follow(connectionId)` | Go along a connection of the current component (the arrival connection steps back) |
| `showConnection(portId)`, `showComponent()`, `restart(id?)`, `setPath(steps)` | Switch tab and port, start a new walk (default start), or replace the walk |

**UI** (`components/panel/`):

- **`PanelNavigator.svelte`** has a breadcrumb row with a **Jump to** button, the current component's `ComponentPanel`, and a bottom bar.
  - **Previous** shows the previous component's name.
  - **Next** shows what it will do: the next component's name, "choose" (several ways or a loop), "connect *port*" (no way forward but a free port, which Next opens in the Piping tab) or "end of path" (disabled).
  - An empty project shows "Start the network" with a choice of first component (`Workspace.addStandalone`).
- **`Breadcrumb.svelte`**: each step is a button back to that component; its tooltip names the connection used to arrive. The row scrolls to keep the last step in view.
- **`PathChooser.svelte`** is the "Which way from *X*?" dialog. Each way forward shows the component, its type, port → port and the connection id. A separate list, "Loops back to the path", offers each loop as "Jump back to *Y*".
- **`JumpToDialog.svelte`** lists every component, with a filter by name, id or type when there are more than six. Components not connected to the start are marked "not connected to the start".
- **`ComponentPanel.svelte`** shows the type and id, and the name as the heading, then `ComponentActions` and two tabs:
  - **Properties**: name, elevation, the per-type form (`forms/`: reservoir, reference node, tee/wye, pump with `PumpCurveEditor`, isolation, check and control valves), and `PortsEditor` (port sizes, elevations, connections; reservoirs add and remove ports). A port's size is only the default for new piping: a connected port names the pipe size the solver uses, and a port size that differs from it is flagged with an offer to resize the pipe.
  - **Piping**: `ConnectionPanel`.
- **`ComponentActions.svelte`**: Add after, Add before, Add branch and Delete. Add before and Add branch are disabled, with the reason given, when the component has no connection.
- **`AddComponentDialog.svelte`** has three modes:
  - at a free port (after);
  - into one of the component's connections (before: by default the connection the walk arrived by);
  - as a branch (a tee or wye inserted into a connection).
- **`DeleteDialog.svelte`**: when `joinPlan` allows it, offers "Join *A* and *B*" (checked by default); otherwise says which connections go and which ports become free. It notes the delete can be undone.
- **`ConnectionPanel.svelte`** starts with port buttons. A connected port shows its connection: from and to (positive flow runs this way), Go to *other end*, Insert component, Add branch and Disconnect, then a `PipeSegmentForm` per segment (with Add pipe segment) and `FittingsEditor`. A pipe segment shows the inner diameter and roughness the solver uses: overrides, else the library size entry (roughness is per size). `FittingsEditor` labels an entrance or exit at a reservoir end, and at a reservoir end with neither it says no such loss is applied and offers both. A free port offers to add a component there, plug it, remove it (a reservoir with more than one port) or connect it to a free port elsewhere, for example to close a loop.

**Edit actions** (`Workspace`). Graph operations are pure functions in `utils/edit.ts`. Each action is one undo step, and an edit that would make the project invalid is refused with an error notice. After each one the walk moves to where the change is:

| Action | What it does |
|--------|--------------|
| `addStandalone(kind)` | Adds the first component (or a separate one) and starts the walk there |
| `addAfter(id, port, kind)` | Adds a component at a free port: same elevation, a default connection of one carbon-steel schedule 40 pipe 10 m long, sized to the port. The connection runs with the expected flow: the new component is upstream when the port receives flow (a pump suction, a valve inlet). At a reservoir end it gets the default loss (`withReservoirLosses`): a sharp-edged entrance where it leaves the reservoir, an exit where it arrives. The walk extends to it |
| `insert(connectionId, kind)` (Add before, Insert component) | Splits the connection (pumps, valves, tees and wyes). A connection drawn against the flow is first turned around, piping reversed. The upstream half keeps the connection id and all its piping. The downstream half is new: one 1 m pipe like the last segment, plus any exit fittings. In the arrival connection the new component takes the place before the current one; in any other it comes after |
| `addBranch(connectionId, 'tee' \| 'wye')` | Inserts a tee or wye with its run in line and shows the Piping tab on its free branch port |
| `remove(id, join)` | Deletes the component. **Join** is possible (`joinPlan`) when exactly two ports are connected, or exactly two to something other than a plug, and its other ports are free or plugged. The two connections then become one: it keeps the upstream connection's id, has both sides' pipes in series in flow order, and offsets the fitting indices; plugs on the other ports are removed with their stubs. Without join, its connections are removed and the ports at their other ends become free. If the start component was deleted, the walk restarts at a former neighbor |
| `plug(id, port)` | Closes a free port with a plug on a 1 m stub sized to the port, at the port's elevation |
| `connect(from, to)` | Connects two free ports, oriented with the expected flow, with the default entrance or exit at a reservoir end |
| `disconnect(connectionId)` | Removes a connection, leaving both ports free |

**From the results.** Clicking a row or flag in the results opens that element's trace and restarts the walk at it. For a connection, the walk starts at its `from` component with the connection's piping open. The trace view's **Show in Build** does the same and switches to the Build pane.

**Keyboard.** Outside text fields, Ctrl/⌘+Z undoes, and Ctrl/⌘+Shift+Z or Ctrl/⌘+Y redoes.

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
- Node.js 22 or later (`engines` in `apps/web/package.json`; `engine-strict=true` makes pnpm refuse older versions)
- pnpm 10 (`corepack enable` picks up `packageManager: pnpm@10.28.0`)
- For end-to-end tests, a Playwright Chromium: `pnpm exec playwright install chromium` once per machine (CI adds `--with-deps`). Skip this where browsers are preinstalled (`PLAYWRIGHT_BROWSERS_PATH`)

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

- **API URL.** The web app calls the API at `PUBLIC_API_URL` (read from `$env/dynamic/public`), default `http://localhost:8000`. The API allows the origins in `CORS_ORIGINS`, default `http://localhost:5173`.
- **API docs.** The API always serves its schema at `/openapi.json`. FastAPI's interactive pages (`/docs`, `/redoc`) load their scripts, styles, fonts and icon from third parties (jsDelivr, Google Fonts, fastapi.tiangolo.com), so they are served only when `API_DOCS=1` (development; CLAUDE.md D10, GOALS §4.5).
- **API types.** After changing the API's Pydantic models, run `pnpm gen:types` in `apps/web`. It regenerates `src/lib/api/openapi.json` (via `uv run python -m opensolve_pipe.openapi`) and `src/lib/api/schema.d.ts`; never edit either by hand. CI fails if they are not current.
- **Static build.** `pnpm build` writes the prerendered site to `apps/web/build/` (`index.html`, `p.html`, `_app/`), and `pnpm preview` serves it. A static build fixes `PUBLIC_API_URL` when it is built (`_app/env.js`).

### 9.3 Quality Checks

```bash
# apps/api
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy src

# apps/web
pnpm check       # svelte-kit sync && svelte-check --tsconfig ./tsconfig.json
pnpm lint        # prettier --check . && eslint .
pnpm test        # vitest --run (unit and component tests, §10.3)
pnpm test:e2e    # playwright test (builds and previews the site, starts the API with uv, §10.3)
```

CI (`.github/workflows/ci.yml`) runs `pnpm check`, `pnpm lint` and `pnpm test` with a frozen lockfile. In a separate job it checks that the generated API types are current (`pnpm gen:types && git diff --exit-code -- src/lib/api`) and runs `pnpm test:e2e`.

No Docker, database or Redis is needed for v1 development.

---

## 10. Testing Strategy

### 10.1 Reference Test Suite (D6)

**Location:** `apps/api/tests/reference/`. Each case in `cases/*.json` holds `name`, `description`, `source` (exactly where the expected values came from), `project` (API JSON) and `expected`: `fluid` (density, viscosity, optionally `vaporPressure`, null where the property source has none), `flows` per connection, `egl` per `componentId:portId` (every port except those in an isolated section), and optionally `pressures` (gauge static), `atmosphericPressure`, `pumps` (status, operating flow and head, NPSH available / required / margin), `valves` (state) and `flags`. One parameterized test (`test_reference_cases.py`) solves every case.

| Source | Use | Generator |
|--------|-----|-----------|
| Closed-form derivations | Single pipes (turbulent, laminar, transitional), fittings, series and parallel pipes, reducers in both directions, plugged branches, pressurized reservoirs and reference nodes, library pipe + built-in water | `derivations.py` (first principles: Darcy–Weisbach with `fluids.friction.Colebrook` — the Lambert-W solution, a different code path from the solver's Clamond — or 64/Re; fitting K from the cited `fluids.fittings` functions; SciPy `brentq`/`fsolve`) |
| Closed-form derivations (M4 differential test) | A PSV open beside a dead-headed pump (a status cycle), a PRV inside a pump loop anchored by a no-flow pipe (the lagged PRV flow); floating sections — a pump loop behind an isolated valve, an active FCV in such a loop, a pump re-opening inside a closed-off loop, a PSV as a loop's only anchor, a PRV in a loop whose level a closed FCV bounds, the system curve of a pump in such a loop (`test_floating_sections.py`, not case files: a floating section has no EGLs); the differential networks themselves (`tests/unit/data/differential`, `test_differential_regressions.py`), checked with the independent laws and, where sections report no heads, with `free_levels.py` (one set of section levels must hold every pump and valve state) | `derivations_status.py`, `test_floating_sections.py`, `free_levels.py` |
| Closed-form derivations (M3) | Pumps (single, reduced speed, beyond the curve, above shutoff, off, series, parallel, a pump and check valve re-opened after a control valve's first solve), isolation valves (Crane defaults, Cv, Kv, K, an isolated section), check valves (cracking pressure, reverse, below cracking, locked open in reverse flow, stop-check locked closed), PRV/PSV/FCV (active, open, closed, an FCV limited by its own open loss, failed open, failed closed), Crane tees and wyes (diverging, converging, dead branch, bullhead fallback, an ideal wye, a reversed lateral), glycols, overrides, NPSH and a siphon | `derivations_pumps.py`, `derivations_valves.py`, `derivations_branches.py`, `derivations_fluids.py`, sharing `element_laws.py` (component laws and status rules written from their definitions) and `line.py` (one-segment lines with fittings) |
| WNTR/EPANET (dev dependency) | Water-only looped networks; networks with a pump, a PRV, a PSV and an FCV | `generate_epanet_cases.py` (WNTR 1.5.0 EpanetSimulator = EPANET 2.2.0) |

`closed_form.py` lists every closed-form generator and `build_closed_form_cases.py` writes their files.

Rules: expected values are never computed with solver code (the suite imports only `opensolve_pipe.models`); `test_derivations_current.py` re-runs every derivation and WNTR run and fails if a JSON is stale; `test_derivation_checks.py` checks each derived solution independently (`network_check.py`): energy and mass balance, every component law in its expected state, the expected states against the status rules, and a whole-network `fsolve` that must reproduce each closed-form case.

**EPANET runs:** solver in `swamee_jain` mode; custom fluid with EPANET's water viscosity VISCOS = 1.1·10⁻⁵ ft²/s = 1.02193344·10⁻⁶ m²/s (`types.h`); ideal tees as junctions; D-W roughness passed to WNTR in metres; GPM INP units; accuracy 10⁻⁵, headerror 10⁻⁹ ft, flowchange 10⁻¹² gpm. Known biases, all far inside the criteria: EPANET uses g = 32.2 ft/s² (0.08% in head loss), a rounded minor-loss constant 0.02517 (0.01%), the GPM unit constant (−3.8·10⁻⁷) and float32 results. EPANET multi-point pump curves are piecewise linear, so pump cases use collinear points (PCHIP then coincides). EPANET's PRV/PSV setting is a head without velocity head, ours a static pressure, so the generator iterates setting = p_set/(ρg) + v²/(2g), v from the previous EPANET run in the pipe on the held port, until it changes by < 10⁻¹² m. An active EPANET FCV keeps a 1/CBIG conductance (CBIG = 10⁸, `fcvcoeff`) and settles at q_set + Δh/CBIG in ft and cfs (about 10⁻⁶ relative); the self-checks allow for that leak. The generator also lists the warning flags the pipes' friction regimes call for at the EPANET flows (`TRANSITIONAL_FLOW`) and refuses a pipe whose Reynolds number sits within 1% of a regime bound or outside Swamee–Jain's documented range.

**Pass criteria:** flows within 0.5% of the reference (floor 10⁻⁹ m³/s), EGL within 0.5% or 0.01 m (whichever is looser), and the EGL difference across every connection likewise; pressures within 0.5% or ρg·0.01 m; pump operating values and NPSH within 0.5% or 0.01 m; the expected pump statuses and valve states; ports with no expected EGL (an isolated section) must have no head, and a valve there with no result must be named by an `ISOLATED_SECTION` flag; every expected flag must be present, and warning and invalid flags are exhaustive (each one raised must be expected with its code and element; info flags may appear unlisted); mass balance checked independently from the link results at every component, plus the solver's own continuity residual. Every new component type ships with at least one reference case.

**Differential test against EPANET (M4, not part of the suite):** 3,000 random branched and looped networks with every v1 element, solved by both in `swamee_jain` mode and compared with the criteria above; every converged result of ours was also checked independently (energy on every connection, each pump and valve law in its state, continuity at every component, the status rules, and, where sections report no heads, one set of section levels holding every state, `free_levels.py`). The defects it found are fixed and their networks kept as regression tests (`tests/unit/data/differential`, `test_differential_regressions.py`, `test_floating_sections.py`, `derivations_status.py`). The remaining differences are not defects: our documented departures (FCV semantics, a control valve with no fixed head on one side closed); EPANET's 1/CBIG conductance across closed links, which gives zero-flow sections heads and floating loops a pressure level; more than one valid steady state (the head of a zero-flow section, a loop whose level lets a PRV or PSV be either open or closed, an open valve passing reverse flow within EPANET's flow tolerance, EPANET's g = 32.2 ft/s² amplified in a narrow pipe carrying the difference of two large flows); and EPANET answers that break mass balance or its own status rules when its setting iteration does not settle.

### 10.2 Backend Unit Tests

- Element laws: h(Q) and dh/dQ for each element type, including Q = 0 and reverse flow
- Cv/Kv → K conversion against Crane's formula
- Topology validation errors
- Status logic: check valves close on reverse flow; PRV/PSV/FCV switch between active/open/closed correctly
- Standard atmosphere and NPSH available

### 10.3 Frontend Tests

**Unit and component tests: Vitest** (`vite.config.ts`, `pnpm test`). `expect.requireAssertions` is on, so a test that asserts nothing fails. There are two projects:

| Project | Environment | Files |
|---------|-------------|-------|
| `client` | jsdom, `@testing-library/svelte` (`svelteTesting()` plugin), setup `src/vitest-setup-client.ts` | `src/**/*.svelte.test.ts`: components, and runes stores that need effects |
| `server` | Node | every other `src/**/*.test.ts` |

The setup file loads the jest-dom matchers and gives `$env/dynamic/public` an empty environment, so the API URL falls back to its default; tests mock `fetch` or pass a fake solver. jsdom has no canvas, so `getContext` returns `null` quietly, as in a browser without canvas support, and the pump chart shows its data table. Shared helpers are in `src/lib/testing/`. Their solve results are made-up inputs to exercise the display, never hydraulic results.

What the tests cover:

- **Encoding and links** (`utils/encoding.test.ts`, `fixtures.test.ts`, `migrations.test.ts`, `validate.test.ts`; §4.7):
  - base64url matches Node's for 0–299 bytes;
  - canonical JSON keeps nested fields, does not depend on key order and refuses non-finite numbers;
  - every example and the fixture round-trip, and encoding is deterministic;
  - corrupt, newer-version and invalid links each raise their `LinkError` kind;
  - each fixture link decodes to its JSON and is pinned by SHA-256;
  - migrations and the schema version match the API;
  - schema problems are readable sentences, schema defaults are filled in, and reference and model-rule checks find their problems.
- **Units** (`utils/units.test.ts`): every unit round-trips; conversions are exact (psi = lbf/in², gpm = 231 in³/min, temperatures by definition); the preference lists equal the API enums; presets, gauge and absolute labels, formatting, and parsing that never returns NaN.
- **Graph and navigator** (`utils/graph.test.ts`, `state/navigator.svelte.test.ts`, `utils/edit.test.ts`): `nextOptions` at chains, tees, loops and multi-port reservoirs; shortest paths and valid path prefixes; the walk through edits, undo and redo; insertion before and after; every graph edit, with delete and join, keeping the project valid.
- **Project store** (`state/project.test.ts`, `project.svelte.test.ts`):
  - undo and redo (merged bursts, depth 100), and invalid changes refused;
  - a debounced URL write, and copy-on-write links;
  - the 8,000-character warning;
  - stale results by hydraulic fingerprint (display units, names and metadata do not count), and superseded solves;
  - typed solve errors, and the method version recorded without an undo step.
- **API client** (`api/client.test.ts`): requests carry only the project and options, with no credentials or referrer; a solve asks for no system curve; fluid properties are posted with the fluid in the body; no request URL carries a value; error responses map to typed errors; cancellation and the timeout work without `AbortSignal.any` (newer than the build target), and no listener is left on the caller's signal.
- **Model rules** (`utils/model-rules.test.ts`): the component, port, fitting and setpoint rules the app applies are the schema's extensions and bounds, the validator knows every extension keyword, and the API's `DUPLICATE_ID` rule is mirrored.
- **System curves** (`state/project.test.ts`, `PumpChart.svelte.test.ts`, `ResultsViews.svelte.test.ts`): a curve is requested for the project as solved, once per solve, one request at a time; a new solve drops the cache and cancels requests in flight, and a late answer for an older solve is dropped; the chart shows the loading state, failures with Try again, cancellations and points without a head; the Pumps view shows one pump at a time.
- **Components** (`*.svelte.test.ts`): Home, the workspace, Share, fluid settings, `NumberField`, valve resistance, the control-valve form, component actions, the panel navigator, the results panel, its views and states, and the pump chart.
- **Results display** (`utils/results.test.ts`, `trace.test.ts`, `flag-text.test.ts`, `pump-chart.test.ts`): tables, flags, traces and the methods text, and chart data in display units.

**End-to-end tests: Playwright** (`playwright.config.ts`, `pnpm test:e2e`). Tests are `tests/*.e2e.ts`, with shared helpers in `tests/support.ts`. Selectors use accessible roles and names. They run against the real API and the production build:

- **Servers.** The config starts the API (`uv run uvicorn opensolve_pipe.main:app --port 8010` in `apps/api`, with `CORS_ORIGINS=http://localhost:4183`) and the site (`pnpm build && pnpm preview --port 4183 --strictPort`, with `PUBLIC_API_URL=http://localhost:8010`); the ports are in `tests/servers.ts`. Outside CI it reuses servers already running on those ports. They are not the development ports (API 8000, Vite 5173 and 4173), so a development API, whose CORS allows only the dev app, is never reused.
- **Projects.** Every test runs twice, on Chromium (Playwright's `Desktop Chrome` device):
  - `desktop`: 1280 × 800;
  - `mobile`: 390 × 844, `isMobile`, `hasTouch`, device scale factor 3.
  Narrow-screen checks skip the desktop project.
- **Policy.** Tests run fully parallel with no retries, and `test.only` is forbidden in CI. A trace is kept for each failure, and CI uploads `apps/web/test-results/` (the traces) when the job fails.

The flows in `tests/` at the time of writing:

- **`home`**: the home page renders.
- **`navigator`**: each home-page example opens from its link at its start component, and Next walks on. A shared link opens the project directly, and edits make a new link. A damaged link explains what happened.
- **`pump-system`**: a pump system is built from a new project through the UI, solved, read, shared and reopened; the reopened link shows the same results. The solve asks for no system curve; showing the pump requests its curve once, for exactly the project solved, and the operating point lies on it; the chart says how the curve was computed and opens the pump's trace, which defines it. The page runs without `AbortSignal.any`, as in the oldest browsers of Vite's default build target (`baseline-widely-available`, e.g. Safari 16.4), since Vite does not polyfill APIs. The test also checks that the page made requests only to the app's and the API's origins.
- **`gravity-branch`**: a gravity-fed branched network with no pump is built through the navigator. Both branches flow, and their flows add up.
- **`topology-error`**: networks the solver cannot solve as connected (no reservoir; an unconnected tee branch) list the API's topology issues with names, each linking back to its components, and solve once fixed.
- **`examples`**: each home-page example, opened from its link and solved unmodified, converges with no flag. Each released schema version's fixture link (`src/lib/utils/__fixtures__/schema-vN.txt`), opened on the test origin, decodes, migrates and converges (the API suite solves the current version's fixture too, `tests/unit/test_released_links.py`).
- **`results`**: a pipe-only network is opened from a link, solved and shared, and the shared link gives the same results. Results tables fit the screen and scroll inside their own box. A connection of several pipes shows each pipe's velocity and Re.
- **`workspace`**: an edit made just before leaving by an in-app link is in the link that Back returns to. The fluid settings show the API's calculated properties, requested by POST with the fluid in the body; no request URL carries a query string. The workspace fits 320 px without sideways scrolling, and on a phone in landscape the header is one row. Keyboard focus stays on Solve and Undo when they become unavailable. Escape in an edited number field of a dialog reverts the field, not the dialog.

---

## 11. Deployment

### 11.1 Frontend

`@sveltejs/adapter-static`: `pnpm build` writes a fully prerendered static site to `apps/web/build/`, which any static host or CDN can serve (§2.4). No frontend server code runs. Requirements on the host:

- It must serve `p.html` for `/p` (the default `trailingSlash: 'never'` output) and `index.html` for `/`.
- It must serve the site from the domain root, because links are root-relative (`paths.relative: false` in `svelte.config.js`).
- `PUBLIC_API_URL` must be set at build time; it is written into `_app/env.js`.

The fragment never reaches the host, so the host's logs never hold project data.

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
CMD ["uv", "run", "--no-sync", "uvicorn", "opensolve_pipe.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
```

Pin the uv image tag to a specific version when this is implemented. Health check: `GET /health`.

Both platforms put an edge proxy in front of the app, so the TCP peer is the proxy. Set `FORWARDED_ALLOW_IPS` (uvicorn reads it) to the platform's proxy address range, so that uvicorn takes the client address from the proxy's `X-Forwarded-For`: the rate limit and the per-client solve limit key on it (SDD §7.2), and without it every user shares one bucket. Never set it to `*` where clients can reach the app directly, or they can choose their own address. Run uvicorn at its default log level: the app drops client addresses and query strings from the access log and uvicorn's trace-level ASGI records (`logging_privacy.py`), and responses of 1 kB or more are gzip-compressed by the app itself.

### 11.3 Environment Variables

```bash
# Frontend (read when the static site is built; default http://localhost:8000)
PUBLIC_API_URL=https://api.opensolve-pipe.app

# Backend
ENVIRONMENT=production
CORS_ORIGINS=https://opensolve-pipe.app
FORWARDED_ALLOW_IPS=<the platform proxy's address range>   # §11.2
# API_DOCS=1 would serve /docs and /redoc, which load third-party assets: development only (§9.2)
```

---

## 12. Implementation Questions

**Decided** (recorded in `CLAUDE.md` D7–D9):

1. **Tee and wye K correlation:** Crane TP-410 functions in `fluids.fittings`; Darby 3-K fallback for tees with the combined flow through the branch; uncovered wye patterns are not converged (§4.2).
2. **Water property package:** CoolProp 8.0.0, `Water` = IAPWS-95; glycols `INCOMP::MEG`/`MPG` (§4.6).
3. **Transition-zone friction (Re 2000–4000):** EPANET 2.2's Dunlop cubic, flagged as transitional; not a user option (§5.2).
4. **Pump curve fitting:** PCHIP through the user's points, straight end-slope extrapolation outside them (flagged), affinity laws (§5.3).
5. **Control-valve status oscillation:** at most 30 counted outer iterations (holding or releasing zero-flow branch legs is not counted, §5.4); once statuses cycle, one status changes per iteration; a repeated state after that returns `converged: false` naming the oscillating components (§5.4).

**Open (Later):**

1. **Schematic layout algorithm:** dagre, elkjs, or custom?
2. **Version storage:** git under the hood, or custom versioning in PostgreSQL?

*End of TSD*
