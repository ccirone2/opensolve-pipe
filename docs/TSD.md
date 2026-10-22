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
| Frontend Hosting | Cloudflare Pages, static (§11.1; chosen 2026-10-22) |
| Backend Hosting | Google Cloud Run, one container image (§11.2; chosen 2026-10-22) |
| CDN | Cloudflare (Pages' own) |

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

1. **Validate topology** (`builder.py`): every problem is collected and raised together as `TopologyError(issues)` (HTTP 422): `DUPLICATE_COMPONENT_ID`, `DUPLICATE_CONNECTION_ID`, `DUPLICATE_ID` (an id naming both a component and a connection: results, traces and flags share one id space), `DUPLICATE_PUMP_CURVE_ID`, `UNKNOWN_COMPONENT`, `UNKNOWN_PORT`, `UNKNOWN_PUMP_CURVE`, `UNKNOWN_PIPE_MATERIAL`, `UNKNOWN_PIPE_SCHEDULE`, `UNKNOWN_PIPE_SIZE`, `ROUGHNESS_OUT_OF_RANGE`, `PIPE_SIZE_OUT_OF_RANGE` (a pipe whose resistance coefficients are not finite floating-point numbers, e.g. an inner diameter of 1e-100 m), `SELF_CONNECTION`, `PORT_CONNECTED_TWICE`, `UNCONNECTED_PORT` ("connect it or add a plug"), `NO_FIXED_HEAD` (a connected sub-network without a reservoir or reference node; also an empty project) and `CONTROLLED_PUMP_CURVE` (a speed-controlled pump whose curve does not give one speed per head, §5.4).
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
- **Speed without changing results:** the inner loop evaluates all branch-leg offsets and their own-flow slopes as arrays (`elements.HeadOffsetArrays`) and walks the offset groups one depth level at a time (`gga.GroupLevels`), with the same floating-point operations in the same order as the per-element laws, so the results are bit-identical (unit-tested against the scalar laws). The outer loop decides a Crane branch that does not change from its fluids K values alone (`branches.path_k`) and builds the leg laws only when they change. Measured on Crane-tee ladders (4 CPUs, no load): a 99-component network's 41-point system curve in 1.6 s (2.8 s before), the 1,000-component limit solved in 4.9 s (10.7 s), and an 805-component curve in 11.6 s (26.8 s). Such a change is checked by solving a corpus (every reference case, the unit-test networks, 3,000 random networks with system curves, Crane ladders) before and after and comparing every reported value.

### 5.3 Element Head-Loss Laws

Every link supplies h(Q) and dh/dQ, with h positive in the direction of positive Q (an EGL drop).

| Element | h(Q) | Notes |
|---------|------|-------|
| Pipe connection | Σ f·(L/D)·v\|v\|/(2g) + Σ K·v\|v\|/(2g) | §5.2; fittings §4.5 |
| Pump (on) | −s²·H₀(Q/s) | `pumps.py`: H₀ is a monotone piecewise cubic (`scipy.interpolate.PchipInterpolator`) through the user's points; beyond them, a straight line with the end slope; affinity laws at speed ratio s. Efficiency η₀(Q/s) (held at its end values outside its points) and NPSHr = s²·NPSHr₀(Q/s) (extrapolated like the head curve, never below 0). Operating outside the curve's flow range flags `PUMP_OUTSIDE_CURVE`. No viscosity correction is applied (HI 9.6.7 is Later); the trace says so. |
| Pump (speed-controlled, flow setpoint) | fixed flow Q_set while regulating; −s_max²·H₀(Q/s_max) or −s_min²·H₀(Q/s_min) at a speed limit | D11, §5.4: the regulating pump is a `FIXED_FLOW` link like an active FCV; at s_max it runs on its own law (the fixed pump's), at s_min on a per-solve law override (`LinkState.law`, read through `network.law_of`) |
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
- **Speed-controlled pumps, flow setpoint** (CLAUDE.md D11; design and owner's answers in `docs/proposals/vfd-pump-modes.md`). With F(s, Q) = s²·H₀(Q/s), H = EGL_d − EGL_s, F_min/F_max = F(s_min/s_max, Q_set) and S_min/S_max = F(s_min/s_max, 0), the first rule that holds wins (`status.flow_pump_status`):

  | State (solver) | Inner-solve link | Rule |
  |---|---|---|
  | active (ACTIVE) | `FIXED_FLOW(Q_set)` | A0 → max if the GGA starves it (a side reaches no fixed head; a controller seeing no flow runs to maximum speed); A1 → max if H > F_max + Htol; A2 → min if H < F_min − Htol |
  | max_speed (OPEN) | its own law, `PumpLaw(curve, s_max)` | X1 → active once Q ≥ Q_set (EPANET 2.2 `fcvstatus`); X2 `pumpstatus` at S_max |
  | min_speed (MIN_SPEED) | `LinkState(NORMAL, law=PumpLaw(curve, s_min))` | N1 → active once Q ≤ Q_set; N2 `pumpstatus` at S_min (closes only on a rising stretch) |
  | no_flow (CLOSED) | closed | C1 `pumpstatus` at S_max: re-opens at maximum speed once H ≤ S_max |

  Speed recovery (after convergence, active only): s_lo = max(s_min, Q_set/x_mono), Ĥ = clamp(H, F(s_lo, Q_set), F_max) (a change of at most Htol by A1/A2), s* the root of F(s, Q_set) = Ĥ on [s_lo, s_max] by `scipy.optimize.brentq` (xtol 1e-14, rtol 4ε; Brent 1973). It is exact, not an approximation: the speed enters only the pump's own head row, so the Newton system with s as an unknown is block-triangular and the flows and heads are those of the fixed-flow solve (EPANET 2.2's FAQ substitute for "a pump of a specific flow"). Uniqueness (`pumps.speed_uniqueness`, at build time): dF/ds = s·ψ(Q/s) with ψ(x) = 2H₀(x) − x·H₀′(x); ψ > 0 must hold on [0, x_last], checked exactly on each PCHIP cubic piece (a cubic in t: its least value at the ends or a root of a quadratic) and on the linear start tangent, else `CONTROLLED_PUMP_CURVE` naming the pump, the curve and the flow interval; beyond x_last the end tangent gives ψ > 0 up to x_mono = 2x₀ (x₀ its zero-head flow) when it falls, unbounded otherwise. Every rule compares flows and head differences only, so the closed-off and floating-section logic (`closed_off_sections`, `zero_flow_openings`, `_level_changes`) applies unchanged, with a CLOSED controlled pump bounded as a fixed pump at s_max. Fallbacks: `_check_changes` applies A1/A2 at a failed solve's early iterate; `_open_bad_valves` tries open (maximum speed), then — for options holding a pump only, with their valves left active — minimum speed, then closed, so a valve-only network takes the v1 option sequence. Two flow controls in series holding the same flow (two controlled pumps, or one and an FCV, with equal setpoints) leave the pressure between them undetermined: a converged state with a controlled pump at a limit, or an open FCV, at its setpoint flow (within Qtol or the GGA's flow resolution) is re-tested with it active, and if the GGA then finds the pressure between it and a flow control undetermined, with a controlled pump among them, the solve is reported not converged naming them (whichever side rounding left the exact X1/N1 and FCV comparisons on); valve-only networks are not concerned. Results: speed s* (active), s_max (max_speed, no_flow), s_min (min_speed); curve, range, η₀(Q/s), NPSHr and power at that speed; `PumpResult.control`; `PUMP_SETPOINT_NOT_MET` (info) at a limit or with no flow off the setpoint by more than Qtol. No new tolerance (Htol, Qtol). Tests: `tests/unit/test_speed_control.py` (uniqueness against dense sampling, the closed-form speed, law override identity, fallback sequences, metamorphic M1/M2), `test_status_rules.py` (the rule table at the tolerance edges).
- **Check valves:** close when the flow would reverse or the head difference falls below the cracking head; reopen above it (EPANET `cvstatus` extended with the cracking head). Closed → `CHECK_VALVE_CLOSED` (info).
- **PRV/PSV/FCV:** EPANET 2.2 `prvstatus`/`psvstatus`/`fcvstatus` translated to EGL. Differences from EPANET: an FCV closes on reverse flow (EPANET lets it pass as an open valve); an active FCV opens once the head across it is below its fully open loss at the setpoint, K_open·Q_set²/(2gA²) (EPANET waits for a reverse head, which leaves a valve with a resistance "throttling" with a K below its fully open K); an active state with no solution falls back first to the states the valve rules give at that solve's last finite iterate within 10 iterations (EPANET 2.2 applies the PRV/PSV rules at every iteration, so a valve whose setting cannot hold leaves its active state before the iteration diverges), then to open, then closed, one valve at a time. A PRV or PSV inside a closed-off or floating section, or closed between two such sections, compares its setpoint with their free levels: it closes on reverse flow, and otherwise these valves keep their states if one set of levels holds them all while the closed elements around the sections stay closed (each valve state holds on a union of regions of difference constraints, below; the choices are enumerated, up to 4,096 Bellman–Ford tests). If none does, the fewest elements are let go, the PRVs and PSVs first, then the closed elements, preferring a result not already solved: at levels that hold the others, each takes the state its rule gives there, except that a PRV or PSV that cannot be active (the side it draws from or delivers to reaches no fixed head) closes if it was open and opens if it was closed. Not at setpoint → `CONTROL_VALVE_SETPOINT_NOT_MET` (info).
- **Closed-off sections:** a section cut off by closed elements (the pipe between a pump and a check valve that closed in the same pass) has no head, so its neighbours' rules cannot test it. The closed elements around it are re-tested against the heads it can take at zero flow: each stays closed only for some head (a pump while the far side is more than s²·H₀(0) above the near side, a check valve while its forward head is at most its cracking head, an FCV while it has no forward head, a PRV/PSV per its CLOSED rule), which are difference constraints between section heads; a negative cycle (Bellman–Ford) means no head keeps them all closed, and the elements on it are re-opened. A floating section is tested the same way, its heads the solved relative heads plus a free level. A pump, check valve or FCV with both ports in one such section follows its rules with the section's heads (a pump held at no flow inside a closed-off loop sees no head across it there and re-opens). EPANET avoids the question by keeping a 1/CBIG conductance across closed links.
- **Branches:** the Crane K is linearized in the flow split around the last split and re-centered each iteration (lagging the whole loss made Newton diverge on manifolds of short taps), and the leg's own-flow dependence enters the Jacobian. A leg whose flow reverses and reverses back (patterns A, B, A in successive updates) is held at zero flow while its head lies between the two patterns' zero-flow limits (facing legs of a rung are held as a pair, released one at a time). These holds and releases change a finite active set (each branch is held at most twice per solve), so the iterations that make them are not counted against the 30: in a long Crane-tee ladder the rung legs join the reversals a few at a time, and the counted iterations stay at a handful while the total grows with length. Every branch starts as an ideal junction (zero losses); each outer update then takes the pattern and the fluids K values at the solved split, as a tangent in q about it. Where the split alternates across a step of a Crane correlation (a split at which the fluids function switches formula, q = 0.4, 0.5 or 0.6, and K actually jumps by more than 1e-4 at that β and angle), K swings between two values. Once the alternation has settled — K is back within 1e-4 (`K_TOL`) of its value two updates before while still changing by more than that, in the same pattern, and pump and valve statuses have stayed the same for the last three solves — the two latest splits are the 2-cycle of the update. Every path's K (the run path's too) is then held, constant in q, at the mean of the fluids values at those two splits (both reported in the trace and in the flag's `details`), and flagged `CORRELATION_OUT_OF_RANGE`, until the solved split leaves the interval between them or a status changes. A K that alternates the same way with no step between the two splits (or while statuses change) is under-relaxed instead: K halfway between the value the leg used and the fluids value at the solved split, the slope kept. The 2-cycle does not depend on the starting point (the held result agrees to about 1e-10 from different warm starts), and to second order it is the pair of splits each side's formula gives when carried across the step (reference case `wye_crane_step_hold`).
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
- **System curve** (`system_curve.py`): at each flow the pump's link becomes a `FIXED_FLOW` link (`run_outer_loop(..., forced_flows={pump: Q})`; the pump takes no part in the status rules, every other element follows its own), and H_sys(Q) = EGL(discharge) − EGL(suction). A speed-controlled pump's own control is replaced by the forced flow, so H_sys is defined as for any pump; other speed-controlled pumps keep regulating, and a warm start copies their statuses (MIN_SPEED included, its law following from it). Default flows 0 … 1.2 × the curve's largest flow × s (a speed-controlled pump's `speed`, its maximum). A point whose solve does not converge, or whose forced flow has no way through (a side reaching no fixed head), has no head. `POST /api/v1/system-curve` returns every point with `converged` and a message; `SolveOptions.includeSystemCurve` fills `PumpResult.systemCurve` of each running pump with its converged points. The web app solves with `includeSystemCurve: false` and requests one pump's curve when its chart is shown (CLAUDE.md D10, SDD §3.1.3); every pump's trace carries the H_sys definition (`trace.SYSTEM_CURVE_EQUATION`), and a solve that computes the curves adds a note on how many points were solved. Closed-form tests: `tests/reference/test_system_curves.py` (single line, series and parallel pumps with the other pump running).
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
| Closed-form derivations (M3) | Pumps (single, reduced speed, beyond the curve, above shutoff, off, series, parallel, a pump and check valve re-opened after a control valve's first solve), isolation valves (Crane defaults, Cv, Kv, K, an isolated section), check valves (cracking pressure, reverse, below cracking, locked open in reverse flow, stop-check locked closed), PRV/PSV/FCV (active, open, closed, an FCV limited by its own open loss, failed open, failed closed), Crane tees and wyes (diverging, converging, dead branch, bullhead fallback, an ideal wye, a reversed lateral, a wye whose split has no self-consistent value at a correlation step: K held at the mean across it, with the held pair of splits checked against the derived 2-cycle), glycols, overrides, NPSH and a siphon | `derivations_pumps.py`, `derivations_valves.py`, `derivations_branches.py`, `derivations_fluids.py`, sharing `element_laws.py` (component laws and status rules written from their definitions) and `line.py` (one-segment lines with fittings) |
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

### 10.4 Differential Test and Corpus Comparison

**Location:** `apps/api/tests/differential/`. Command-line tools, run from `apps/api`, outside the reference suite. pytest collects `test_fuzz_smoke.py` and `test_harness.py` (unit checks of these tools). Nothing is written into the repository unless an output directory there is named: each EPANET run works in its own temporary directory, which also holds the scratch files EPANET makes in its working directory.

| Module | What it does |
|--------|--------------|
| `generator.py` | `generate(seed)`: a random branched or looped network meant to have an exact EPANET equivalent for every element: reservoirs, ideal reference nodes, ideal tees and wyes, plugs, custom pipes in 1–3 segments with custom K fittings, pumps with collinear curves from Q = 0, isolation valves, check valves (cracking pressure 0), PRV, PSV and FCV, with random statuses and setpoints. A connection can still end up as the inlet of two active check valves (class `unsupported`). `swamee_jain` mode with EPANET's water viscosity (§10.1). The network depends only on the seed and the profile. Profiles (`--profile`): `default`, the network above, whose draws are frozen (the baseline below, the corpus and the smoke test's pinned classes depend on them); and `flow_control` (proposal `vfd-pump-modes.md` §7.4; documented seeds 10,000–12,999), the default network of the seed plus 0–2 flow-controlled pumps (D11) drawn from a second generator, `Random("flow_control:<seed>")`, after every default draw. An existing pump gets a control, or a new pump with its own collinear curve is inserted in a connection (mostly one left when dead ends are pruned, so it can carry flow), sometimes in series with the previous one and then sometimes with an equal setpoint (no determined state, proposal §4.6). Setpoint log-uniform from 0.001 to 1.2 × the curve's largest flow at the maximum speed, minimum speed 0.1–0.9 × the maximum, so that all five control states occur. |
| `epanet_model.py` | The project as an EPANET 2.2 model (WNTR INP, run through the toolkit in double precision), with the mapping and PRV/PSV setting iteration of §10.1. An active check valve is merged into its one-segment inlet pipe as an EPANET CV pipe. Elements can be pinned to a state. If EPANET cannot balance at headerror 10⁻⁹ ft and flowchange 10⁻¹² gpm, looser pairs are tried. An element with no exact equivalent raises `UnsupportedError`. EPANET has no speed control, so a flow-controlled pump that is on stands for the state our solver reports (`control_pins`, proposal §7.4): active → the EPANET 2.2 FAQ substitute for a pump of a specific flow (the pump CLOSED, a demand of Q_set at its suction junction and −Q_set at its discharge junction, https://usepa.github.io/EPANET2.2/13_questions.html); max_speed / min_speed → OPEN at SPEED = its maximum / minimum speed, under EPANET's own pump rules; no_flow → CLOSED. One we report without a result runs at its maximum speed (rule A0), or CLOSED when it is held at no flow with both sides closed off (its flags kept). |
| `checks.py` | The comparison with the D6 criteria: those of §10.1, with a flow also accepted within the flow that 0.01 m of head loss gives in that connection (0.01 m divided by dh/dQ) and within twice the bound of the flow EPANET's closed links leak (1/CBIG conductance). `fuzz --strict` drops the head-equivalent floor. Also the independent checks of a solution: continuity at every component; energy on every connection; each pump and valve law in its state; the status rules, written from EPANET 2.2 in EGL form with the departures of §5.4; and, for sections reported without heads, that one set of heads keeps every state. Closed-off sections are tested at zero flow, floating sections with the relative heads the laws give at the reported flows, and PRV/PSV borders by exact enumeration of their regions. The checks read only the solver's results, never its internals. A flow-controlled pump's state is its control state; its rules (`rule_flow_pump`: A1/A2, X1/X2, N1/N2, C1) are written from the state machine of proposal §4.5 alone (a flow within 10⁻⁹ relative of Q_set is Q_set in X1 and N1, so a limit state carrying its setpoint, as in series with another flow control holding the same flow, is not valid), its law in each state from §4.4 (active Q = Q_set, a fixed flow; at a speed limit the fixed-speed pump at that speed), the band of A1/A2 bounds an active one beside a headless section, and `control_problems` checks the reported control: the status of each state, the speed (s_max at max_speed and no_flow, s_min at min_speed; active within [s_min, s_max] with \|s²·H₀(Q_set/s) − H\| ≤ Htol), and `PUMP_SETPOINT_NOT_MET` and `setpointAchieved` as §2.5 defines them. An active pump's speed is compared with the one EPANET's head rise H_e implies (closed form for the generator's linear curves, s = [bQ + √(b²Q² + 4aH)]/(2a), proposal §4.7) within 0.5 % (owner's answer Q6), and the head our speed implies at Q_set with H_e by the D6 head criterion (0.5 % or 0.01 m, whichever is looser), as every head loss here: Q6's 0.01 m alone is the reference suite's test against a derived head, while EPANET's own constants (g = 32.2 ft/s², the 0.02517 minor-loss factor) move its head differences by a few 10⁻⁴ relative (0.015 m across a 46 m pump, flow_control seed 10,062). |
| `state_search.py` | For a network our solver did not converge on: every combination of pinned pump and valve states, the first 729 (`--limit` from the command line), solved and kept if it passes the checks. Like `fuzz`, the command line also counts the states that give every port a head. A flow-controlled pump is pinned over its four states (proposal §7.4): max_speed and min_speed as the fixed-speed pump at that speed, no_flow as the pump off, and active with its speed range widened to (0.001, 1], the original range enforced by the check of rules A1/A2. `control_search` (`--controls`) pins only the flow-controlled pumps, every other element following the solver's rules. Valid solutions are distinct when a flow differs, or an EGL at a port of a connection with flow, by more than D6; distinct ones that differ in flowing state (flow in the same connections in other amounts, or each in a connection the other has at rest) are *multiple*, while the others only put more of the network at rest (a pump held closed with valves closed around it at heads that keep them closed, D9). |
| `fuzz.py` | The driver: generates (`--profile`), solves with both, compares, checks and classifies each seed (classes below). With flow-controlled pumps every EPANET run stands for our states, the control checks join the self-check, and every converged network is searched over its controlled pumps' states (`control_search` in the record): multiple valid solutions are written to `findings/control_multiple_states`, alternatives that only put more at rest to `findings/control_rest_alternatives`; the class is not changed. A non-default record names its `profile`. |
| `classes.py` | The class names and `is_critical`. |
| `stats.py` | A summary of a run: counts per class, and the largest \|Δ\|/tolerance per metric and element kind over the agreeing networks (with flow-controlled pumps: `speed` and `speed_head` of kind `flow_pump`, their final states, and the control-search counts). |
| `networks.py` | Fixed corpus networks: Crane-tee ladders, and a step-hold probe wye (45°, β² = 0.25) scanned over six R3 levels across the q = 0.4 step. The reference case `wye_crane_step_hold` is a different network; it is in the corpus separately as `ref_wye_crane_step_hold`. |
| `corpus.py` | Solves every project of the corpus with system curves and dumps each `SolvedState` to `<name>.json`. The corpus is the reference-case projects and the unit-test data networks (41-point curves), six ladders, the step-hold probe wye at six levels, and fuzz seeds 0–2,999 (11-point curves): 3,092 projects before speed control; since then the flow-controlled reference cases and the `flow_control` profile's seeds 10,000–10,999 (`fuzzfc_<seed>`, 11-point curves), 4,116 in all. |
| `compare.py` | Compares two dumps exactly (JSON equality, `timestamp` ignored). It reports identical and different projects, projects missing from either side, and for each difference the number of numeric differences and the largest relative one. Exit status 1 when a project differs. `--ignore PATH` (repeatable) leaves out the values at a path: dict keys and list indices from the root separated by `.`, each segment an `fnmatch` pattern (`*` is any one key or index), the whole path at its depth, a key present on one side only included. Each pattern's count of values left out, and in how many projects, is printed after the totals, so an ignore broader than intended shows. |

**Commands** (from `apps/api`; times are wall-clock on 4 CPUs with 3 workers):

```bash
uv run python -m tests.differential.fuzz 0 3000 --workers 3 --out /tmp/fuzz   # about 3 min
uv run python -m tests.differential.stats /tmp/fuzz
uv run python -m tests.differential.corpus /tmp/corpus --workers 3             # about 3 min
uv run python -m tests.differential.compare /tmp/corpus-before /tmp/corpus
uv run python -m tests.differential.state_search SEED     # valid states of one network
uv run python -m tests.differential.generator SEED        # one network's project JSON
uv run python -m tests.differential.fuzz 10000 13000 --workers 3 --profile flow_control --out /tmp/fuzzfc  # 10 min
uv run python -m tests.differential.state_search SEED --profile flow_control --controls
uv run python -m tests.differential.generator SEED --profile flow_control
```

`fuzz` writes `results/<seed>.json` (one record per seed) and `findings/<class>/<seed>.json` (a reproducer: the project JSON, both solutions and the diagnosis inputs) to `--out`, a new temporary directory by default. It prints that directory and the critical seeds, and exits with status 1 if there are any. `--strict` compares flows to 0.5% or 10⁻⁷ m³/s without the head-equivalent floor (0.01 m divided by dh/dQ), which accepts almost any flow in a short, large pipe. `corpus` writes each dump to a `.tmp` file and renames it into place, so an interrupted run leaves no partial dump. It refuses an output directory that already holds dumps, because they may come from another commit; `--resume` continues an interrupted run there and reuses every existing file as it is, whatever commit wrote it. `--only PREFIX` selects projects by name, and `--dry-run` prints the solver package and corpus tree it would use. `compare` reports a file it cannot read or parse as unreadable, and counts it as different. The smoke test classifies seeds 0–49 with the real EPANET run, and the `flow_control` seeds 10,000–10,024 (which must also reach all five control states, with no multiple valid solutions over their controlled pumps' states); it adds about 25 s to `uv run pytest`.

**Classes** (`status` in a fuzz record; "the checks" are the independent checks above):

| Class | Meaning |
|-------|---------|
| `pass` | Flows, head losses, EGLs and pump and valve states agree. |
| `documented` | They agree once EPANET is pinned where our documented departures apply: an FCV that closes on reverse flow (EPANET's XFCV passes it), an FCV that opens below its fully open loss, and a PRV/PSV that EPANET reports XPRESSURE (no fixed head on one side) held in our state. |
| `pass_ep_unbalanced` | EPANET does not balance in 200 trials, but its last iterate agrees with ours, states included. |
| `ours_verified_by_pinned_epanet` | EPANET does not balance, even with our FCV semantics. EPANET with every pump at no flow and every valve open or closed pinned to our state (running pumps and active control valves left to EPANET's rules) does balance, and its numbers agree with ours, which checks our element laws in our states. |
| `epanet_unbalanced` | As above, but the pinned run does not balance or disagrees: there is no balanced EPANET reference. |
| `state_only` | The numbers agree, but a state differs. |
| `state_only_zero_flow` | As `state_only`, and every element whose state differs carries no more than EPANET's Qtol or its closed-link leak (a state at zero flow). |
| `a_ours_invalid` | The numbers differ and our result fails the checks. **Critical.** |
| `d_no_converged_reference` | The numbers differ, ours passes the checks, and EPANET with our FCV semantics does not balance. |
| `b_stagnant_heads` | Only EGLs differ, and both solutions pass the checks (EPANET's within its tolerances). This is the free level of a zero-flow section, which EPANET's 1/CBIG conductance across closed links fixes. |
| `b_multiple_steady_states` | Flows or head losses differ, and both solutions pass the checks. |
| `e_epanet_invalid` | The numbers differ, ours passes the checks, and EPANET's solution breaks continuity, energy or an element law. |
| `review` | The numbers differ, ours passes the checks, and EPANET's solution keeps the laws but breaks its status rules. |
| `unsupported` | An element has no exact EPANET equivalent (in seeds 0–2,999: a connection that is the inlet of two check valves). |
| `epanet_failed` | The first EPANET run returned an EPANET error (in seeds 0–2,999: `runH` error 110, the equations cannot be solved). Any other exception in that run is a harness error. |
| `ours_not_converged`, `both_unconverged` | Our solver did not converge; EPANET balanced or did not. The suffix `_valid_state_exists` means `state_search` found a state that passes the checks with every port headed. |
| `ours_exception`, `gen_error`, `harness_error` | Our solver, the generator or the harness raised. A harness error is, for example, EPANET failing in a re-run with pins, or the EPANET library failing to load. Its record keeps what was computed before, `self_check` included. |

Every converged result of ours is also checked before EPANET runs. A failure is stored in the record's `self_check`, which a `harness_error` record keeps, and in `findings/self_check_failed`. That is the same check that makes a class `a_ours_invalid`, so a seed is **critical** (`classes.is_critical`) when its `self_check` is non-empty or its class is `a_ours_invalid`: a converged result of ours that fails the independent checks. For each seed in its range, the smoke test asserts that our solver converged, that EPANET ran, that the seed is not critical, and that its class is the one pinned in the test. The classes are deterministic (the same under PYTHONHASHSEED 0 and 12345, in both profiles), so a changed class is a change in our solver's or EPANET's behaviour, to be reviewed before the pinned class is updated. With flow-controlled pumps the self-check includes their rules, laws and reported control (`checks.py` above). EPANET stands for the state we report for each, so a wrong state of ours shows in the self-check, not as a state difference, and EPANET's solution under that state must also keep our rules (else class `review`); the control search (`state_search.py` above) checks that the state is the only valid one.

**Seeds 0–2,999** (3,000 networks, 40,736 components, 43,600 connections): pass 1,857; documented 535; state_only_zero_flow 262; pass_ep_unbalanced 127; b_stagnant_heads 82; epanet_unbalanced 42; epanet_failed 29; ours_verified_by_pinned_epanet 27; unsupported 13; b_multiple_steady_states 10; d_no_converged_reference 9; review 3; state_only 2; harness_error 1; e_epanet_invalid 1. None is critical. The largest \|Δ\|/tolerance in the agreeing networks is 0.817 (EGL at a pump port). The `flow_control` profile and the speed-control solver left every one of these records unchanged (re-run after both: the same classes, records and diagnoses).

**`flow_control` seeds 10,000–12,999** (3,000 networks, 43,922 components, 46,724 connections; 2,710 with a flow-controlled pump): pass 1,762; documented 465; state_only_zero_flow 300; pass_ep_unbalanced 149; b_stagnant_heads 86; epanet_unbalanced 83; epanet_failed 66; ours_verified_by_pinned_epanet 21; d_no_converged_reference 20; b_multiple_steady_states 17; unsupported 11; review 10; ours_not_converged 5; e_epanet_invalid 2; ours_not_converged_valid_state_exists 2; state_only 1. None is critical. Our final states of the controlled pumps: max_speed 1,955 (most at zero flow, dead-ended, rule A0), min_speed 740, isolated 509, no_flow 441, active 182, off 168. 162 active pumps were compared with EPANET's FAQ substitute: largest \|Δ\|/tolerance 0.339 for the speed and 0.691 for the head it implies (seed 12,846); over all comparisons, 0.979 (EGL at a controlled pump's port). The control search covered 2,584 converged networks: one (11,037) has distinct valid solutions that differ in flowing state, the zero-flow multiplicity of v1 rather than of the control (a pump at maximum speed dead-ended at its shutoff head, or closed with its section's level free, which a PSV beside it compares with; the same with the pumps fixed at that speed), and 38 have alternatives that only put more of the network at rest. Of the 7 not converged, 4 hold two flow controls in series with equal setpoints (no determined state, proposal §4.6), 1 (12,773) has no valid fully determined state among the 729 combinations searched, and 2 (11,738; 12,703) have one that the solver's fallbacks did not reach. In both, outer iterations change several statuses at once and the cycle closes on a step that changes a single status, so the single-change fallback (`_one_change`), which starts only when the step closing a cycle changes several, is never tried (12,703: from PRV4 open and PU5 at maximum speed, the rules move PU5 to active and PRV4 to closed together, while the valid state changes PU5 alone); not converged is the fail-safe result. The same seeds in the default profile (the base networks without the added pumps, run for this comparison: pass 1,869; documented 485; state_only_zero_flow 265; pass_ep_unbalanced 109; b_stagnant_heads 75; epanet_failed 63; epanet_unbalanced 62; ours_verified_by_pinned_epanet 28; d_no_converged_reference 15; unsupported 11; b_multiple_steady_states 10; review 4; e_epanet_invalid 2; harness_error 1; state_only 1; none critical, none not converged): every one of the 290 networks that got no controlled pump has the same class in both profiles. Of the others, apart from the 7 not converged above, the classes that differ from the base network's are EPANET's (unbalanced, failed with runH error 110, or a pinned solution that breaks a status rule, `review`, 8) or v1's documented zero-flow and FCV departures, which a pump's changed flows bring into play: in 107 of the 165 new `state_only_zero_flow` (93 of them with no other difference) a controlled pump dead-ended at maximum speed (rule A0, running at zero flow) is one that EPANET reports closed, as it does a fixed pump against a plug; the 14 new `b_multiple_steady_states` differ in valves and check valves, with the controlled pumps in the same states.

**Before/after comparison of a solver change.** Dump the corpus from each tree and compare. `corpus` solves with the `opensolve_pipe` that is importable and reads the corpus from its own tree. Run it from inside a tree's `apps/api`, with that tree's project, so both come from the same tree. It refuses to run if `opensolve_pipe` is imported from another tree. From the repository root:

```bash
REPO=$(git rev-parse --show-toplevel)
BEFORE=/tmp/osp-before                          # outside the repository
OUT=$(mktemp -d)                                # new and empty for every comparison
git worktree add --detach "$BEFORE" HEAD        # the commit to compare against
# or, without a worktree: mkdir -p "$BEFORE" && git archive HEAD apps/api | tar -x -C "$BEFORE"
cd "$BEFORE/apps/api"
uv run --project "$BEFORE/apps/api" python -m tests.differential.corpus "$OUT/before" --dry-run
uv run --project "$BEFORE/apps/api" python -m tests.differential.corpus "$OUT/before" --workers 3
cd "$REPO/apps/api"
uv run python -m tests.differential.corpus "$OUT/after" --workers 3
uv run python -m tests.differential.compare "$OUT/before" "$OUT/after"
git worktree remove "$BEFORE"                   # --force if tests/differential was copied in
# (with git archive instead: rm -rf "$BEFORE")
```

The dry run prints `solver: $BEFORE/apps/api/src/opensolve_pipe`. The first `uv run` in a new tree creates its `.venv`, with that tree's `src` installed in editable mode. A tree from a commit older than `tests/differential` needs that directory copied in before the first `corpus` run (`cp -r "$REPO/apps/api/tests/differential" "$BEFORE/apps/api/tests/"`). The copied tools import `tests/reference` and `tests/unit/helpers` from that tree. A reference case added since the "before" commit shows up as "missing in A".

**Speed-controlled pumps, slice 1 (proposal §7.5).** The change adds `control` (null) to every pump result and stamps `METHOD_VERSION` 1.1.0, so it is compared with exactly those paths left out:

```bash
uv run python -m tests.differential.compare "$OUT/before" "$OUT/after" \
  --ignore 'pumpResults.*.control' --ignore methodVersion --ignore trace.methods.methodVersion
```

Before = `15dbd1a` (the solver of `cd715ba`), after = the slice-1 working tree: identical 3,092, different 0; the ignores left out 2,577 `control` values in 1,688 projects and the method version in each of the 3,092 (top level and methods summary). The 24 flow-controlled reference cases and the 1,000 `fuzzfc_` networks are "missing in A".

---

## 11. Deployment

The owner chose the hosts on 2026-10-22: the web app on **Cloudflare Pages** (static) and the API on **Google Cloud Run**. Nothing is deployed yet. This section records the configuration and the reasons for it; the README's *Deployment* section lists the owner's steps. Provider facts come from the pages linked at the end of the section, read on 2026-10-22. Prices and limits change, so check them again before deploying.

### 11.1 Frontend (Cloudflare Pages)

`@sveltejs/adapter-static`: `pnpm build` writes a fully prerendered static site to `apps/web/build/` (21 files, 0.9 MB for v1). No frontend server code runs. The host must do three things:

- **Serve `p.html` for `/p` and `index.html` for `/`** (the default `trailingSlash: 'never'` output). Pages serves an HTML file whose path matches the route, and it redirects `/p.html` to `/p`. With no top-level `404.html`, any other path gets `index.html` (Pages' SPA mode) ([serving][cf-serving]). In `wrangler pages dev`, `/p/` also redirected to `/p` (308), and Chromium kept the fragment across both redirects, so those links still open.
- **Serve the site from the domain root**, because links are root-relative (`paths.relative: false` in `svelte.config.js`). Use the project's `*.pages.dev` hostname or a custom domain, never a subpath.
- **Set `PUBLIC_API_URL` at build time.** The build writes it into `_app/env.js`, so changing it needs a new build.

Project settings (Git integration: Workers & Pages → Create → Pages → connect the repository):

| Setting | Value | Why |
|---|---|---|
| Production branch | `main` | |
| Framework preset | None | Pages' SvelteKit preset expects `adapter-cloudflare` and its `.svelte-kit/cloudflare` output ([build configuration][cf-build]) |
| Root directory | `apps/web` | The app's `package.json` and `pnpm-lock.yaml` are here; the root directory is for monorepos ([build configuration][cf-build]) |
| Build command | `pnpm build` | |
| Build output directory | `build` | adapter-static's output |
| Variable `PUBLIC_API_URL` | the API's URL (§11.2), no trailing slash | Written into `_app/env.js` |
| Variable `NODE_VERSION` | `22.22.0` | The Node the repository's checks run on. The v3 build image defaults to 22.16.0, ignores `engines`, and may move minor versions without notice ([build image][cf-image]) |
| Variable `PNPM_VERSION` | `10.28.0` | `packageManager` in `package.json`. The v3 image defaults to pnpm 10.11.1 and reads neither the lockfile's version nor `engines` ([build image][cf-image]) |
| Build watch paths | include `apps/web/*` | Skips builds for commits that touch only the API or the docs ([watch paths][cf-watch]). The generated `src/lib/api/openapi.json` lives under `apps/web` |
| Preview branch control | None | Previews are public `*.pages.dev` URLs ([previews][cf-preview]). The API's CORS doesn't allow their origins, so they couldn't solve, and each build counts against the monthly limit ([branch control][cf-branch]) |

**Response headers.** `apps/web/static/_headers` is copied into the build. Pages applies it and does not serve it ([headers][cf-headers]):
- `Referrer-Policy: no-referrer` on every response, matching what `app.html` and the API client already set. Pages' default is `strict-origin-when-cross-origin` ([serving][cf-serving]).
- `X-Frame-Options: DENY` and `Content-Security-Policy: frame-ancestors 'none'`, because the app is never framed. These are Cloudflare's own hardening example ([headers][cf-headers]). There is no script CSP, because the prerendered pages carry an inline start-up script.
- `/` and `/p` get Pages' default `Cache-Control: public, max-age=0, must-revalidate` plus `no-transform`. With `no-transform`, a Cloudflare zone can't rewrite the pages to inject a script; Cloudflare documents this for the Web Analytics beacon ([Web Analytics][cf-wa]).
- `/_app/immutable/*` (content-hashed) gets `public, max-age=31536000, immutable`, the same header SvelteKit's own preview server sends (`@sveltejs/kit/src/exports/vite/preview/index.js`). `_app/env.js` and `_app/version.json` keep the default revalidation, so a rebuild reaches browsers on their next load.

Checked with `wrangler pages dev` 4.149.0 on a build made with `PUBLIC_API_URL` set:
- All four rules parsed and applied, and `/_headers` was not served.
- An unknown path got `index.html`.

**Privacy** (GOALS §4.5): no analytics, no cookies, and no requests to third parties.
- **Pages Web Analytics stays off.** Under Pages project → Metrics, don't enable Web Analytics: enabling it adds a JavaScript beacon to the site on the next deployment ([Pages Web Analytics][cf-wa-pages]).
- **On a custom domain whose zone is on Cloudflare, keep off the zone features that inject scripts or set cookies:**
  - Web Analytics' automatic setup, which is on by default for proxied sites that used Browser Insights ([Web Analytics][cf-wa]).
  - Bot Fight Mode, which sets the `__cf_bm` cookie, and JavaScript detections and challenges, which set `cf_clearance` ([cookies][cf-cookies]).
  - Email Address Obfuscation, which is on from sign-up and injects `email-decode.min.js` ([obfuscation][cf-email]).
  - Any other feature that rewrites HTML.

  `no-transform` is a second line of defence for the two pages, not a substitute for these settings.
- **Checked against the local emulation** with the API running from the exact image command, in Chromium at desktop (1280×800) and mobile (390×844) sizes. Opening the released `schema-v1` link and solving made 14 requests to the site's origin and 3 to the API's, and nothing else. The solve converged with a gzip response, and there were no cookies, no `Set-Cookie` and nothing in `localStorage`. Repeat this on the real site after each deployment (§11.4).
- The fragment never reaches Cloudflare, so the host never holds project data. Like any host, Cloudflare sees visitors' addresses in order to serve the files.

**Cost:** the Free plan.
- Requests for static assets are free and unlimited ([pricing][cf-price]).
- Limits: 500 builds a month, one at a time, 20 minutes each; 20,000 files per site; 25 MiB per file; 100 `_headers` rules ([limits][cf-limits]). The site uses 21 files and 4 rules.

### 11.2 Backend (Google Cloud Run)

**Image.** `apps/api/Dockerfile` is built from `apps/api`. `.dockerignore` keeps the build context to `pyproject.toml`, `uv.lock`, `LICENSE` and `src/` (54 files, 0.8 MiB).
- **Base images**, pinned by version and digest:
  - `ghcr.io/astral-sh/uv:0.11.32`, the uv of the `uv_build` constraint.
  - `python:3.12.15-slim-trixie` (Debian 13).

  To update one, change its tag and digest together (`docker buildx imagetools inspect <image:tag>` prints the digest).
- **Build stage:** `uv sync --locked --no-dev` installs exactly the runtime dependencies in `uv.lock` (no pytest, mypy or WNTR) and fails if the lock is stale. The app is then installed as a regular, non-editable package with its data files (read through `importlib.resources`). Bytecode is compiled at build time, for faster cold starts.
- **Runtime stage:** only the virtual environment, owned by root and run by an unprivileged user (uid 10001, no home, no shell).
- **Command:** `exec uvicorn opensolve_pipe.main:app --host 0.0.0.0 --port "${PORT}" --proxy-headers`.
  - Cloud Run injects `PORT` (8080 by default) and requires the server to listen on 0.0.0.0 ([container contract][gc-contract]). The image defaults to `PORT=8080` so that `docker run` works too.
  - One process per instance, because the rate limit and the solve pool are in-process state (`middleware.py`, `workers.py`).
  - `exec` makes uvicorn PID 1, so it receives the SIGTERM that Cloud Run sends 10 s before SIGKILL ([container contract][gc-contract]).
  - uvicorn runs at its default log level. The app drops client addresses and query strings from the access log and from uvicorn's trace-level ASGI records (`logging_privacy.py`), and it gzip-compresses responses of 1 kB or more itself.
- **Health check:** `GET /health`. Cloud Run's default TCP startup probe is enough.

**Client address behind Google's front end.** The rate limit and the per-client solve limit key on the client's address (SDD §7.2), which the app sees only through `X-Forwarded-For`.
- **The container never sees the client directly.** Cloud Run terminates TLS and proxies each request to the container over HTTP/1, so the container's TCP peer is Google's proxy ([container contract][gc-contract]).
- **Google's front end appends the client's address to `X-Forwarded-For` and does not check what comes before it.**
  - For Google's load balancers the header becomes `[<supplied-value>,]<client-ip>,<load-balancer-ip>`, and "the load balancer does not verify any IP addresses that precede" those two ([load balancing][gc-lb]).
  - The Cloud Run functions header reference shows `X-Forwarded-For: clientIp, proxy1Ip, proxy2Ip` ([headers][gc-fn-headers]).
  - Google doesn't document the proxy's own source address on Cloud Run. A report from October 2026 found 169.254.169.126, a link-local address ([report][gh-report]).
- **How uvicorn picks the client.** uvicorn 0.54 (`ProxyHeadersMiddleware`) reads `X-Forwarded-For` only when the TCP peer is in `FORWARDED_ALLOW_IPS`, and then takes the right-most entry that is not in the list. With `*` it takes the left-most entry, which the client writes itself.
- **What the image sets.** `FORWARDED_ALLOW_IPS` lists every block that IANA's special-purpose registries mark as not globally reachable and that a host can hold ([IPv4][iana4], [IPv6][iana6]): `127.0.0.0/8`, `::1`, `169.254.0.0/16`, `fe80::/10`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `100.64.0.0/10` and `fc00::/7` (RFC 1122, 4291, 3927, 1918, 6598, 4193).
  - Whichever of these addresses the proxy uses is trusted.
  - No client on the internet can connect from one of them.
  - So the address the front end appends is the right-most entry outside the list, and it becomes the key.
- **Checked locally** with the exact command, where the TCP peer is 127.0.0.1 and `X-Forwarded-For` is sent as the front end would send it:
  - After 60 requests from one client, the 61st got 429.
  - Another client got 400, so it has its own bucket.
  - The first client putting its own entry first (`198.51.100.99, <client>` or `10.1.2.3, <client>`) still got 429.
  - With `FORWARDED_ALLOW_IPS='*'`, the client-written entry escaped the limit (400).
  - The access log held no client address and no query string.
- **After deploying, run the check in §11.4**, because Google doesn't document the proxy's address. If the check shows one shared bucket, the proxy's address is outside these blocks. Then add Google's front-end source ranges, `35.191.0.0/16` and `130.211.0.0/22` ([load balancing][gc-lb], "Request source ranges"), and run the check again.
- **Put no other proxy in front of the API** (a Cloudflare-proxied hostname, a load balancer) without revisiting this list. Each proxy appends its own address, which would become every user's key. A Cloudflare proxy would also terminate TLS and see the project data in request bodies.
- **Use the API's `*.run.app` URL as `PUBLIC_API_URL`.** Cloud Run's own domain mapping is in Preview and "not recommended for production services". The alternative is a load balancer, which costs money and appends its own address ([custom domains][gc-domains]).

**Service settings.** Each value comes from the code, from measurement or from Google's documentation:

| Setting | Value | Why |
|---|---|---|
| Region | `us-central1`, or another Tier 1 region near the users | The free tier is applied at Tier 1 (us-central1) prices ([pricing][gc-price]) |
| CPU | 1 | Two solve threads (`SOLVE_WORKERS`) hold the GIL most of the time, so they need about one core. Cloud Run warns that a single-threaded app on several vCPUs leaves them idle and skews CPU-based scaling ([concurrency][gc-concurrency]) |
| Memory | 1 GiB | See the measured peaks below. 512 MiB (the default and the gen2 minimum) leaves too little headroom ([memory][gc-memory]). An instance over its limit is terminated, and every request still on it ends with a 500 ([container contract][gc-contract]). 1 vCPU allows up to 4 GiB |
| Concurrency | 6 | `MAX_SOLVES_IN_FLIGHT`: Cloud Run starts another instance, or queues, instead of sending a 7th request that the pool would refuse with `SERVER_BUSY`. The gcloud default is 80 per vCPU ([concurrency][gc-concurrency]) |
| Request timeout | 60 s | The frontend's own timeout (`DEFAULT_TIMEOUT_MS`). The solve budget is 45 s from the request's arrival, and Cloud Run counts container start-up inside its timeout ([container contract][gc-contract]). The default is 300 s ([timeout][gc-timeout]) |
| Minimum instances | 0 | Idle instances that aren't minimum instances cost nothing ([pricing][gc-price]). The cost is a cold start once Cloud Run has shut the idle instance down, which can take up to 15 idle minutes ([autoscaling][gc-scaling]). A cold start took about 5 s here to import the app, 3.3–4.0 s of it CoolProp |
| Maximum instances | 1 at first | The in-memory limits (60 solves a minute per client, one solve at a time) hold exactly only within one instance, and one instance bounds the bill (§11.5). Raise it when traffic needs it |
| Billing | request-based (the default) | CPU is allocated only while requests are handled ([container contract][gc-contract]), and a solve runs only inside its request |
| Startup CPU boost | the default (on) | Extra CPU during start-up, billed only then ([CPU][gc-cpu]) |
| Ingress, authentication | all; unauthenticated allowed | A public API for the web app |
| Service account | a dedicated one with no roles | The API calls no Google API |
| `CORS_ORIGINS` | the site's origins | §11.3 |

**Measured** on one 2.8 GHz Xeon core here; Cloud Run's vCPU may be slower.
- **Memory:** peak RSS was 302 MB for one solve of the largest network the schema allows (999 components, 1,494 connections, Crane tees) and 456 MB with the pool full (6 such solves, 2 running).
- **Speed:** that network solved in 8.5 s alone and in about 21 s two at a time. Of 7 sent at once:
  - 4 finished within 42 s;
  - 2 ran out of the 45 s budget (503 `TIMEOUT` at 45.8 s);
  - 1 was refused (503 `SERVER_BUSY`).
- **Small networks:** the pump example solved in 0.05 s.
- **Response size:** gzip took the largest response from 16.4 MB to 0.47 MB.

**Logs.**
- **Cloud Run's request log would undo the app's log privacy.** Cloud Run writes a request log entry for every request automatically. Its `httpRequest` holds the client's address (`remoteIp`) and the full URL with its query string ([logging][gc-logging], [LogEntry][gc-logentry]), which would undo `logging_privacy.py` (SDD §7.3).
- **Exclude it from the project's `_Default` sink:** `gcloud logging sinks update _Default --add-exclusion='name=no-run-request-logs,filter=LOG_ID("run.googleapis.com/requests")'`. Cloud Logging still receives excluded entries but doesn't store them ([routing][gc-routing]).
- **Usage counts stay available.** Request counts remain available as Cloud Run's request-count metric ([monitoring][gc-monitoring]), and Google Cloud metrics cost nothing ([pricing][gc-obs-price]). The container log (the app's access log, without addresses) is kept.

**Build and images.**
- **Build:** `gcloud builds submit apps/api --ignore-file=.dockerignore --tag …` builds the Dockerfile in Cloud Build and pushes the image to Artifact Registry. Cloud Build checks `mirror.gcr.io` before Docker Hub ([cache][gc-mirror]).
- **`--ignore-file` matters.** Without it, gcloud uploads everything in `apps/api` that its default rules don't skip, a local `.venv` included: 23,222 files and 996 MiB here, against 54 files and 0.8 MiB with it. This was checked with gcloud's own file chooser.
- **Build and deploy are separate commands.** `gcloud run deploy --source` takes no ignore file and writes a `.gcloudignore` into the source directory.
- **Permissions:** in projects where default service accounts don't get Editor automatically, Cloud Build's default service account needs `roles/run.builder` ([deploying from source][gc-source]).
- **Cleanup:** a cleanup policy keeps the 3 most recent images ([cleanup][gc-ar-cleanup]). Each image is about 0.1 GiB compressed, estimated from the virtual environment (271 MiB; 79 MiB gzipped) plus the base image.

**Not checked here: building the image.**
- Docker ran in this session, but the build containers couldn't reach PyPI through the session's TLS-intercepting proxy, and they weren't given its certificate.
- Everything before the downloads ran: both pinned base images resolved by digest, uv found the image's Python 3.12.15, and `--locked` accepted `uv.lock`.
- The image's contents were checked another way. The same `uv sync --locked --no-dev --no-editable` went into a fresh virtual environment, which was then run with the image's exact command and environment, including `HOME=/nonexistent` (nothing needs to write to a home directory).
- The runtime stage's user setup and environment were also built on their own, with a stand-in for uvicorn. The command runs as uid 10001 and as PID 1, and it takes `PORT` from the environment (8080 by default). `/app` is not writable.
- The first `gcloud builds submit` is therefore the image's first full build.

### 11.3 Environment Variables

```bash
# Frontend: Cloudflare Pages build variables, read when the static site is built
# (PUBLIC_API_URL defaults to http://localhost:8000)
PUBLIC_API_URL=https://opensolve-pipe-api-<project-number>.us-central1.run.app   # §11.2, no trailing slash
NODE_VERSION=22.22.0
PNPM_VERSION=10.28.0

# Backend: Cloud Run service (Cloud Run sets PORT)
CORS_ORIGINS=https://<pages-project>.pages.dev   # comma-separated; add a custom domain's origin when there is one
# FORWARDED_ALLOW_IPS is set in the image (§11.2); override it only after the §11.4 check
# API_DOCS=1 would serve /docs and /redoc, which load third-party assets: development only (§9.2)
```

The API reads no other variable (the old `ENVIRONMENT=production` was never read). With gcloud, a value that contains commas needs another delimiter: `--update-env-vars='^;^CORS_ORIGINS=https://a.pages.dev,https://example.org'` (`gcloud topic escaping`).

### 11.4 Checks After Each Deployment

1. **Health and docs:** `curl https://<api>/health` returns `{"status":"healthy"}`, and `/docs` returns 404 (`API_DOCS` is unset).
2. **Client address (§11.2)**, while maximum instances is 1. The body `{}` is rejected before any solve, so the check costs nothing:
   ```bash
   API=https://<api>
   hit() { curl -s -o /dev/null -w '%{http_code}\n' -H 'content-type: application/json' --data '{}' "$@" "$API/api/v1/solve"; }
   for i in $(seq 60); do hit > /dev/null; done   # 60 invalid bodies: 400 each, counted by the rate limit
   hit                                            # 429: this client's minute is used up
   hit -H 'X-Forwarded-For: 203.0.113.7'          # 429: an entry the client writes does not change its key
   ```
   Then, within the same minute, run `hit` from another network (another machine, or this one on a phone's hotspot). It should return 400; 429 means every user shares one bucket.
3. **Logs:** in Logs Explorer, `LOG_ID("run.googleapis.com/requests")` shows nothing newer than the exclusion. The container log has lines like `- - "POST /api/v1/solve HTTP/1.1" 400`, with no addresses.
4. **Site**, on a desktop browser and on a phone:
   - Open the home page's example and solve.
   - Requests go only to the site and to the API, and Application → Storage shows no cookies.
   - The page source of `/` and `/p` has no `cloudflareinsights` or `email-decode` script.
   - `curl -sI https://<site>/p` shows the `_headers` values.

### 11.5 Cost

Free tiers and prices in USD, read on 2026-10-22:

| Item | Free each month | Beyond that |
|---|---|---|
| Cloudflare Pages: static requests and bandwidth | Unlimited ([pricing][cf-price]) | — |
| Cloudflare Pages: builds | 500 ([limits][cf-limits]) | Free plan limit |
| Cloud Run, request-based billing (per billing account) | 180,000 vCPU-s, 360,000 GiB-s, 2 million requests ([pricing][gc-price]) | $0.000024 per vCPU-s, $0.0000025 per GiB-s, $0.40 per million requests (us-central1) |
| Outbound data from Cloud Run | 1 GiB within North America ([pricing][gc-price]) | Google Cloud networking prices |
| Cloud Build | 2,500 build-minutes, e2-standard-2 ([pricing][gc-cb-price]) | $0.006 per minute |
| Artifact Registry storage | 0.5 GiB ([pricing][gc-ar-price]) | $0.000136986 per GiB-hour (about $0.10 per GiB-month) |
| Cloud Logging storage | 50 GiB per project ([pricing][gc-obs-price]) | $0.50 per GiB |

- **The free tier covers 50 instance-hours of active time a month.** At 1 vCPU and 1 GiB, an instance costs $0.0000265 per second while it handles requests. The vCPU allowance (180,000 s) is the one that runs out first.
- **Ordinary use stays at $0.** A typical solve keeps the instance active for well under a second (0.05 s for the pump example).
- **Worst case with maximum instances 1: about $64 a month.** That is a month of non-stop use (730 h) after the free tier: 2,448,000 vCPU-s × $0.000024 plus 2,268,000 GiB-s × $0.0000025, plus any requests beyond 2 million.
- **Budgets:** an alerts-only Cloud Billing budget doesn't cap spending ([budgets][gc-budgets]). A spend cap budget on the project and Cloud Run pauses new Cloud Run usage for the rest of the month once its amount is reached. Cloud Run is an eligible service ([spend caps][gc-spend-cap]). Set one at whatever monthly amount the owner accepts, knowing that the API stops when it triggers.

[cf-serving]: https://developers.cloudflare.com/pages/configuration/serving-pages/
[cf-build]: https://developers.cloudflare.com/pages/configuration/build-configuration/
[cf-image]: https://developers.cloudflare.com/pages/configuration/build-image/
[cf-watch]: https://developers.cloudflare.com/pages/configuration/build-watch-paths/
[cf-preview]: https://developers.cloudflare.com/pages/configuration/preview-deployments/
[cf-branch]: https://developers.cloudflare.com/pages/configuration/branch-build-controls/
[cf-headers]: https://developers.cloudflare.com/pages/configuration/headers/
[cf-limits]: https://developers.cloudflare.com/pages/platform/limits/
[cf-price]: https://developers.cloudflare.com/pages/functions/pricing/
[cf-wa-pages]: https://developers.cloudflare.com/pages/how-to/web-analytics/
[cf-wa]: https://developers.cloudflare.com/web-analytics/get-started/
[cf-cookies]: https://developers.cloudflare.com/fundamentals/reference/policies-compliances/cloudflare-cookies/
[cf-email]: https://developers.cloudflare.com/waf/tools/scrape-shield/email-address-obfuscation/
[gc-contract]: https://docs.cloud.google.com/run/docs/container-contract
[gc-lb]: https://docs.cloud.google.com/load-balancing/docs/https
[gc-fn-headers]: https://docs.cloud.google.com/functions/docs/reference/headers
[gh-report]: https://github.com/zkproofport/proofport-relay/issues/4
[iana4]: https://www.iana.org/assignments/iana-ipv4-special-registry/
[iana6]: https://www.iana.org/assignments/iana-ipv6-special-registry/
[gc-domains]: https://docs.cloud.google.com/run/docs/mapping-custom-domains
[gc-price]: https://cloud.google.com/run/pricing
[gc-concurrency]: https://docs.cloud.google.com/run/docs/about-concurrency
[gc-memory]: https://docs.cloud.google.com/run/docs/configuring/services/memory-limits
[gc-timeout]: https://docs.cloud.google.com/run/docs/configuring/request-timeout
[gc-scaling]: https://docs.cloud.google.com/run/docs/about-instance-autoscaling
[gc-cpu]: https://docs.cloud.google.com/run/docs/configuring/services/cpu
[gc-logging]: https://docs.cloud.google.com/run/docs/logging
[gc-logentry]: https://docs.cloud.google.com/logging/docs/reference/v2/rest/v2/LogEntry
[gc-routing]: https://docs.cloud.google.com/logging/docs/routing/overview
[gc-monitoring]: https://docs.cloud.google.com/run/docs/monitoring
[gc-obs-price]: https://cloud.google.com/stackdriver/pricing
[gc-mirror]: https://docs.cloud.google.com/artifact-registry/docs/pull-cached-dockerhub-images
[gc-source]: https://docs.cloud.google.com/run/docs/deploying-source-code
[gc-ar-cleanup]: https://docs.cloud.google.com/artifact-registry/docs/repositories/cleanup-policy
[gc-ar-price]: https://cloud.google.com/artifact-registry/pricing
[gc-cb-price]: https://cloud.google.com/build/pricing
[gc-budgets]: https://docs.cloud.google.com/billing/docs/how-to/budgets
[gc-spend-cap]: https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps

---

## 12. Implementation Questions

**Decided** (recorded in `CLAUDE.md` D7–D9 and D11):

1. **Tee and wye K correlation:** Crane TP-410 functions in `fluids.fittings`; Darby 3-K fallback for tees with the combined flow through the branch; uncovered wye patterns are not converged (§4.2).
2. **Water property package:** CoolProp 8.0.0, `Water` = IAPWS-95; glycols `INCOMP::MEG`/`MPG` (§4.6).
3. **Transition-zone friction (Re 2000–4000):** EPANET 2.2's Dunlop cubic, flagged as transitional; not a user option (§5.2).
4. **Pump curve fitting:** PCHIP through the user's points, straight end-slope extrapolation outside them (flagged), affinity laws (§5.3).
5. **Control-valve status oscillation:** at most 30 counted outer iterations (holding or releasing zero-flow branch legs is not counted, §5.4); once statuses cycle, one status changes per iteration; a repeated state after that returns `converged: false` naming the oscillating components (§5.4).
6. **Speed-controlled pumps, slice 1 (flow setpoint):** the setpoint is imposed as a fixed flow and the speed recovered by Brent's method, exact by the block-triangular argument; uniqueness by the exact ψ test on the PCHIP pieces (`CONTROLLED_PUMP_CURVE` otherwise); at a limit the pump is the fixed pump at that speed (the link's own law at s_max, a `LinkState.law` override at s_min); rules A0–C1 with EPANET's Htol and Qtol; minimum speed required with no default; `speed` is the maximum (≤ 1); no sleep at low demand; plain affinity efficiency; `schemaVersion` 1; `METHOD_VERSION` 1.1.0 (§5.4; CLAUDE.md D11). Slices 2 (discharge pressure) and 3 (differential pressure) are designed in `docs/proposals/vfd-pump-modes.md` §4.10 and are Later.

**Open (Later):**

1. **Schematic layout algorithm:** dagre, elkjs, or custom?
2. **Version storage:** git under the hood, or custom versioning in PostgreSQL?

*End of TSD*
