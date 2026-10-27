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
│   │   │   │   │   ├── Home.svelte     # Home page; SiteFooter.svelte; links.ts (app links, disclaimer, legal links)
│   │   │   │   │   ├── workspace/      # Workspace layout, header, Share, project settings, fluid, link errors,
│   │   │   │   │   │                   #   scenario manager and case bar (ScenarioManager, ScenarioBar),
│   │   │   │   │   │                   #   goal seek (GoalSeekDialog, goal-seek/: cards, forms, result)
│   │   │   │   │   ├── panel/          # Panel navigator: breadcrumb, path chooser, jump-to, component and
│   │   │   │   │   │   │               #   connection panels, add/delete dialogs, ports, pipes, fittings
│   │   │   │   │   │   └── forms/      # One form per component type; pump-curve editor
│   │   │   │   │   ├── results/        # Results pane: status, flags, tables, pump chart, trace view,
│   │   │   │   │   │                   #   methods summary, scenario card, Compare cases (§5.7),
│   │   │   │   │   │                   #   ExportDialog (lazily loaded, §8.3); chart-setup.ts (the
│   │   │   │   │   │                   #   chart chunk: Chart.js, its configuration, the chart image)
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
│   │   │   │   │   ├── scenarios.ts    # Scenarios: the client mirror of apply_scenario, edits in a
│   │   │   │   │   │                   #   scenario, changes carried through base edits (§5.7)
│   │   │   │   │   ├── compare.ts      # Compare cases: rows, values and differences from the base
│   │   │   │   │   ├── goal-seek.ts    # Goal seek: catalogues, default bounds, lapses, the request,
│   │   │   │   │   │                   #   words, trial table, report, Apply (§5.7)
│   │   │   │   │   ├── identity.ts     # Which pipe a pipe object is across edits (scenario changes)
│   │   │   │   │   ├── issue-text.ts   # Topology issues in names and display units (server's message kept)
│   │   │   │   │   ├── system-curve-text.ts  # Why a system-curve point has no head, from its reason
│   │   │   │   │   ├── pump-chart.ts   # The pump chart's data and notes (pump-chart-config.ts: its
│   │   │   │   │   │                   #   Chart.js configuration, in the chart chunk)
│   │   │   │   │   ├── export/         # Export (§8.3): input (the snapshot), model, context, tables,
│   │   │   │   │   │                   #   about, units; writers csv, xlsx, zip, yield; filename,
│   │   │   │   │   │                   #   download, load (the lazy dialog), chart-image
│   │   │   │   │   ├── …               # flag-text, labels, piping, schema-bounds, media,
│   │   │   │   │   │                   #   scroll-focus, scenario-problems, json (canonical JSON),
│   │   │   │   │   │                   #   flow-coefficient (Cv and Kv labels and hints)
│   │   │   │   │   └── __fixtures__/   # schema-v<N>.txt (a shared link) and schema-v<N>.json (§4.7);
│   │   │   │   │                       #   scenario-cases.json, goal-seek-cases.json, export-input.json
│   │   │   │   │                       #   (generated by the API, §5.7, §8.3); export-results.xlsx and
│   │   │   │   │                       #   .expected.json (written by the export's fixture test)
│   │   │   │   ├── notices.ts          # Name of the third-party licenses file (§11.1)
│   │   │   │   └── testing/            # Unit-test helpers and made-up results (not used by the app)
│   │   │   ├── plugins/
│   │   │   │   └── third-party-licenses.ts  # Vite plugin: writes third-party-licenses.txt (§11.1)
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
│   │   ├── svelte.config.js            # adapter-static, runes mode, version = the commit (§11.1)
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
│       │       │   ├── goal_seek.py        # POST /api/v1/goal-seek (§5.7)
│       │       │   ├── _common.py          # Shared error responses, the client key
│       │       │   └── fluids.py
│       │       ├── services/
│       │       │   ├── solver/
│       │       │   │   ├── builder.py      # Port graph → solver nodes and links
│       │       │   │   ├── gga.py          # Global Gradient Algorithm core
│       │       │   │   ├── elements.py     # Head-loss laws: pipe, pump, valves, equipment, branches
│       │       │   │   ├── equipment.py    # An equipment item's c from its rating (§4.9)
│       │       │   │   ├── status.py       # Outer loop: check/control valve status, tee K updates
│       │       │   │   ├── npsh.py
│       │       │   │   └── results.py      # Solver output → SolvedState
│       │       │   ├── fluids.py
│       │       │   ├── scenarios.py        # apply_scenario, annotate, solve_case (§5.7)
│       │       │   └── goal_seek.py        # prepare, search, goal_seek_case (§5.7)
│       │       ├── models/
│       │       │   ├── project.py
│       │       │   ├── components.py
│       │       │   ├── results.py
│       │       │   ├── scenarios.py        # Scenario, overrides, the allow-list (x-override-fields)
│       │       │   ├── goal_seek.py        # Variables, goals, results (x-goal-variables, x-goal-quantities)
│       │       │   └── fluids.py
│       │       └── data/
│       │           ├── pipe_materials.json
│       │           ├── fittings.json
│       │           ├── branch_k_factors.json
│       │           └── fluids.json
│       ├── tests/
│       │   ├── reference/              # Benchmark cases (§10.1)
│       │   ├── unit/
│       │   ├── differential/           # EPANET differential test, corpus tools (§10.4)
│       │   └── fixtures/               # Shared projects; scenario_cases.py, goal_seek_cases.py,
│       │                               #   export_input.py (the web's fixtures, §5.7, §8.3)
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

Code: `apps/web/src/lib/utils/encoding.ts`, `migrations.ts`, `validate.ts` and `link-error.ts`. The rules are in SDD §5.2. The project's scenarios (§5.7) are part of it; the key is left out when there are none, so a project without scenarios encodes exactly as before, and the active case is not encoded (a link opens on the base case).

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
- **Model rules.** `modelRuleProblems` checks the rules the API models enforce in validators, which JSON Schema cannot express: the port ids or count per component type, the pipe size source, fitting parameters and reducer positions, increasing curve flows, the FCV setpoint range, ordered fields (a speed-controlled pump's minimum speed below its speed), pump-curve references and ids shared by a component and a connection (the API's `DUPLICATE_ID`). The rules come from the schema, never from a copy: `model-rules.ts` reads the models' extensions (`x-port-ids`, `x-port-roles`, `x-port-count`, `x-required-parameters`, `x-reducer-types`, `x-entrance-types`, `x-exit-types`, `x-setpoint-bounds`, `x-ordered-fields`, SDD §5.1) and the ports bound, and the navigator's port roles, the piping editor, the ports editor and the control-valve form use the same functions. `model-rules.test.ts` fails if the app's rules and the schema's disagree; the API's `test_schema_rules.py` fails if an extension and its validator disagree or `openapi.json` is stale. A link that breaks only these still opens. The results pane lists the problems, and the solver reports them too.

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

### 4.8 Assigned Flow Node

```python
# apps/api/src/opensolve_pipe/models/components.py (beside Plug)

ASSIGNED_FLOW_RANGE = (-FCV_SETPOINT_RANGE[1], FCV_SETPOINT_RANGE[1])  # ±100 m³/s: D11's flow bound


class AssignedFlow(BaseComponent):
    """Fixed flow out of (demand, positive) or into (supply, negative) the network at its port,
    whatever the pressure there, which is a result. Not a fixed-pressure boundary."""

    PORT_IDS = ("port_1",)

    type: Literal["assigned_flow"]
    flow: float = Field(ge=ASSIGNED_FLOW_RANGE[0], le=ASSIGNED_FLOW_RANGE[1])  # m³/s, required
```

`flow` is required: no source gives a default flow. `x-port-ids` and `x-port-roles` are published like every component's (D10). `schemaVersion` stays 1 (an additive component type, nothing deployed before it).

**Solver handling:** like a plug, an assigned-flow node adds no link. Its port becomes a free node whose demand is `flow` (`SolverNode.demand`, set by `builder.py`; 0 at every other node), which enters the GGA's continuity rows as inflow − demand = 0 (`q_demand`, §5.2), the same way a `FIXED_FLOW` link's demand and supply do; `flow = 0` behaves exactly as a plug (same flows, EGLs, pressures and flags: tested, and checked on every fuzz network with a zero flow, §10.4). It is never a fixed head, so it doesn't satisfy `NO_FIXED_HEAD` (§5.1), whose message then says that assigned-flow nodes fix a flow, not a pressure.

Rules the solver assumed before nodal demands, and how they changed (the code's docstrings name each):

- **Dead-end trees** (`results.dead_end_links`): a free node with no demand and one open link passes no flow. A node with a nonzero assigned flow is never pruned, nor is the path from it to the rest of the network, which carries its flow.
- **Isolated sections** (§5.2, `gga.circulating_parts`) are removed only if they can sit at zero flow; a part holding a nonzero assigned flow cannot. A part that no fixed head reaches through open links and whose assigned flows sum to zero (to the continuity tolerance, `gga.assigned_balance`) is a floating section, solved with its flows and head differences and flagged `UNDETERMINED_PRESSURE`. Otherwise no steady state carries them (EPANET's "system disconnected"): the part is *disconnected* (`GgaResult.disconnected_sections`), left out of the inner solve while the rest is solved. The outer loop then re-opens the closed elements around it whose status rules open as its level runs away, down with a net demand and up with a net supply (`status.disconnected_openings`: a pump, check valve or FCV opens when the part is on the side its flow would run to, never against its one-way rule; a PRV or PSV by its rule at that level), all together, or each alone when that state was already solved. With none, the solve ends not converged, and the message names each node with its flow and each element closed around the part with the reason it is closed: the status the user set, a side with no fixed head, or its status rule. Elements with a port in the part keep their states while it is not solved (the rules have no heads there), and `zero_flow_openings` takes no constraint from an element beside it.
- **Flow controls feeding assigned flows** (`gga._fed_message`, `status._over_controlled`, `status._assigned_flow_note`): a control in a fixed mode (an active FCV, PRV or PSV, or a speed-controlled pump holding its setpoint) whose side is a part that no fixed head reaches but that holds assigned flows is not starved: the flows it and the nodes fix meet there with nothing to fix a pressure, so the inner solve is not attempted and names them, with the net flow they fix (`GgaResult.undetermined_nodes`, `undetermined_imbalance`). The status rules then decide, as D11 does for two flow controls in series (integrator's decision, D12): an FCV fed demand below its setpoint ends fully open, passing the demand (`CONTROL_VALVE_SETPOINT_NOT_MET`); a speed-controlled pump fed another flow runs at its maximum speed (below the setpoint) or its minimum speed (above it), flagged `PUMP_SETPOINT_NOT_MET`; a flow the control never passes (more than an FCV's setpoint, or reverse flow through an FCV or pump) has no steady state and ends not converged, naming the control and the nodes; a flow equal to the setpoint (within Qtol) leaves the control's throttling or speed and the pressure between them undetermined (over-controlled) and ends not converged, naming them, whichever path the solve takes (a limit carrying exactly the setpoint, statuses cycling, or the control closed by the failed-state fallback with the nodes left disconnected); that state is not unique rather than missing, so the message gives the over-control alone, with no disconnected report or closing rule.
- **Results:** the port is a free port node: EGL, velocity (the connected pipe's end segment), HGL, static and absolute pressure, and `BELOW_VAPOR_PRESSURE` as at any port; the boundary result gives the EGL and the outflow, −flow as solved; the mass-balance residual subtracts the demand. A node in a floating section has no head and no boundary result; a disconnected one makes the solve not converged.
- **Trace** (`trace._assigned_flow_trace`, SDD §4.11): the flow as entered with its sign convention, elevations, fluid, g and p_atm; the continuity equation at the port with Q_in and its residual (also when the pressure level is undetermined); EGL, velocity, velocity head, HGL, static and absolute pressure; a note that it is not a pressure boundary, which states when a part no fixed head reaches carries a nonzero flow (only if its assigned flows sum to zero, then at an undetermined level; otherwise not converged) and that a zero flow there is a closed end, and, at flow 0, that it behaves as a plug. A floating section that holds assigned flows has flow passing through it, not only circulating: its `UNDETERMINED_PRESSURE` flag and the floating notes of its elements say so, and the flag names the nodes with their flows among its drivers (`results.floating_flags`, `TraceInputs.assigned_floating`). Not-converged reports name assigned-flow nodes in the message only: `ConvergenceReport.oscillating_components` lists elements with a status.
- **Methods summary:** only when the project has an assigned-flow node, one item in Network solution citing EPANET 2.2 (junction demands), and a sentence in the Pumps section's system-curve item on the bounds that count assigned flows, citing Gale (1957) there (§5.6).

### 4.9 Equipment

```python
# apps/api/src/opensolve_pipe/models/components.py (after ControlValve)

class RatedPoint(CamelModel):
    kind: Literal["point"]
    pressure_loss: float = Field(gt=0, le=RATED_PRESSURE_LOSS_MAX)  # Pa (a difference), 1e8
    flow: float = Field(gt=0, le=FCV_SETPOINT_RANGE[1])               # m³/s, 100
    density: float = Field(gt=0, le=RATED_DENSITY_MAX)               # kg/m³, 3e4


class RatedFlowCoefficient(FlowCoefficient):                         # value in (0, 1e7]
    kind: Literal["Cv", "Kv"]


EquipmentRating = Annotated[
    Annotated[RatedPoint, Tag("point")] | Annotated[RatedFlowCoefficient, Tag("coefficient")],
    Discriminator(_rating_tag, custom_error_type="invalid_rating",
                  custom_error_message="unknown rating kind (expected 'point', 'Cv' or 'Kv')"),
]


class Equipment(BaseComponent):
    PORT_IDS = ("inlet", "outlet")
    PORT_ROLES = {"inlet": "inlet", "outlet": "outlet"}

    type: Literal["equipment"]
    rating: EquipmentRating  # required, no default
```

The bounds are ones the model already had: a PRV/PSV setpoint's and a gauge pressure's maximum, D11's flow bound, a custom fluid's density and a valve's flow coefficient (`FLOW_COEFFICIENT_MAX`). The callable discriminator, as `FluidDefinition`'s, gives an unknown kind (a K included) an error that never quotes it. `x-port-ids` and `x-port-roles` are published like every component's; the union needs no other extension. `schemaVersion` stays 1 (an additive type, D14).

**Solver handling** (`services/solver/equipment.py`, `builder.py`, `elements.py`; proposal `equipment-pressure-drop.md` §3.4):

- **c once.** `equipment_law(rating, g) → EquipmentLaw` computes, in this order: for a rated point h_r = ΔP_r/(ρ_r g), then c = h_r/Q_r²; for a Cv or Kv, K = `valves.k_from_coefficient(rating, 1.0)` (fluids `Cv_to_K` / `Kv_to_K`) and c = K/(2gA²) with A the area of a 1 m bore. K ∝ D⁴ makes K/A² the same on every bore, so the element needs no pipe; its c equals a valve's on any bore to round-off, not bit for bit (at most 6 ulp over 300,000 draws, proposal §3.1; the unit tests compare at 2×10⁻¹⁵ relative). The law also keeps the coefficient's equivalent rated point for the trace: ΔP₁ = 1 psi at Q₁ = Cv US gpm (1 bar at Kv m³/h), on water of density ρ_w = ΔP₁/(g c Q₁²), which comes out of fluids' conversion as 999.29744568 kg/m³ (no fluids constant is copied).
- **The link.** One `LinkKind.EQUIPMENT` link inlet → outlet with `QuadraticLossLaw(c)`: h = c·Q\|Q\|, dh/dQ = 2c\|Q\| (a class of its own rather than `ValveLaw`, so the valves' arithmetic stays exactly as it was); its initial flow is 1 ft/s in the inlet pipe, as a valve's (EPANET 2.2 `initlinkflow`). It has no status, so it is always NORMAL: the status rules, the closed-off, floating and zero-flow logic and `system_curve.flow_limit` treat it as open both ways, like a pipe, and `gga.py`, `status.py` and `system_curve.py` do not change. At Q = 0 the GGA floors its slope in the Jacobian only, as for every link that is not a pipe (`gga.JACOBIAN_FLOOR_RELATIVE`); the law stays exact.
- **Topology.** `_unrepresentable_equipment`, after `_unrepresentable_valves`: an element whose c is not a finite positive double, or whose computation raises `ZeroDivisionError` or `OverflowError` inside the bounds (ρ_r = Q_r = 10⁻³⁰⁰; a Cv of 10⁻¹⁷⁰; a Kv of 10⁻¹⁶⁰), is `EQUIPMENT_RATING_OUT_OF_RANGE`, naming the element and quoting its rating. c is monotone in each rating value, so it stays finite and positive between two values where it is; a goal-seek trial that still meets the issue (several values at extremes together) is an unusable trial, a topology error at those values (§5.7), never a residual.
- **Results** (`results.equipment_result`): from the solved EGLs and the inlet → outlet flow: `headLoss` = EGL_in − EGL_out, `pressureLoss` = ρg·headLoss, `pressureDrop` = p_in − p_out with each static pressure by D7 (v in the connected pipe's end segment), `flowRatio` = Q/Q_r (null for a Cv or Kv) and the `rating` used. An element closed off, or beside a floating section, has no result (`heads_of` gives NaN); one inside a floating section has its flow and differences. The map is `{}` when the solve did not converge.
- **Flags** (`CORRELATION_OUT_OF_RANGE`, warning): a reported flow below 0 (the zero-flow rounding makes a flow within it exactly 0), with a message without numbers and `details` {flow, ratedFlow for a rated point}; and laminar flow, 0 < Re < `RE_LAMINAR_MAX` (2000) in the end segment of the inlet or outlet pipe, whichever has the lower Re (`EquipmentData.laminar_pipe`, shared by the results and the trace), with `details` {reynoldsNumber}. Both may come together.
- **Trace** (`trace._equipment_trace`, element type `equipment`, SDD §4.10): the rating as entered (source `user`), the port elevations, the connected pipes' inner diameters, the fluid and g; the equations; the correlation (ISA-75.01.01-2007 eq. (1) at constant K, Silverberg & Darby 1999) and the data sources (the rating as user data; for a Cv or Kv the valves' fluids conversion); intermediates c (`s²/m⁵`), h_r or the equivalent rated point with ρ_w, Q/Q_r, each port's velocity v = Q/A once, signed as the flow, and Re, the EGLs, the head loss as solved and by the law, ρgh, ρ/ρ_r, the ports' static pressures, and each term of the static-drop identity (ρgh, ρg(z_out − z_in), ρ(v_out² − v_in²)/2); notes on the rated drop's definition, the Cv/Kv rating, the viscosity limit, the density ratio in words, and reverse and laminar flow with their inequalities.
- **Methods summary:** only when the project has equipment, a section "Equipment" after "Valves" (the law and the rated drop's definition; density scaling; the Cv/Kv conversion only when an element is rated by one; reverse and laminar flow flagged; the zero-flow Jacobian floor; viscosity not corrected, with Blasius' ρ^0.75 μ^0.25 Q^1.75 as its size), with references `ISA_75` and `DARBY`, and one assumption ("Equipment losses scale with the square of the flow and with density from one rated point, a Cv or a Kv (constant K); viscosity is not corrected."). Nothing else in the summary changes (unit-tested).

---

## 5. Solver Implementation

### 5.1 Overview

One solver handles every topology (D1). Code: `apps/api/src/opensolve_pipe/services/solver/`; entry point `solve_project(project, options) -> SolvedState`.

1. **Validate topology** (`builder.py`): every problem is collected and raised together as `TopologyError(issues)` (HTTP 422): `DUPLICATE_COMPONENT_ID`, `DUPLICATE_CONNECTION_ID`, `DUPLICATE_ID` (an id naming both a component and a connection: results, traces and flags share one id space), `DUPLICATE_PUMP_CURVE_ID`, `UNKNOWN_COMPONENT`, `UNKNOWN_PORT`, `UNKNOWN_PUMP_CURVE`, `UNKNOWN_PIPE_MATERIAL`, `UNKNOWN_PIPE_SCHEDULE`, `UNKNOWN_PIPE_SIZE`, `ROUGHNESS_OUT_OF_RANGE`, `PIPE_SIZE_OUT_OF_RANGE` (a pipe whose resistance coefficients are not finite floating-point numbers, e.g. an inner diameter of 1e-100 m), `VALVE_RESISTANCE_OUT_OF_RANGE` (a valve whose K on its inlet pipe's diameter, or K/(2gA²), is not a finite floating-point number, e.g. a Cv of 1e-170, which made the conversion divide by zero), `EQUIPMENT_RATING_OUT_OF_RANGE` (an equipment item whose loss coefficient c is not a finite positive floating-point number, or whose computation divides by zero or overflows, §4.9), `SELF_CONNECTION`, `PORT_CONNECTED_TWICE`, `UNCONNECTED_PORT` ("connect it or add a plug"), `NO_FIXED_HEAD` (a connected sub-network without a reservoir or reference node; also an empty project), `CONTROLLED_PUMP_CURVE` (a speed-controlled pump whose curve does not give one speed per head, §5.4) and `CONTROLLED_PUMP_SETPOINT` (on a curve that passes that test, a flow setpoint that no speed up to the maximum can hold: Q_set ≥ s_max·x_mono, §5.4).
2. **Build the solver network** (`builder.py`, `network.py`): one node per component port at the port's effective elevation; one link per `PipeConnection` (its segments in series and its fittings); one link per pump, valve and equipment item between its port nodes; a branch component adds a center node and three legs (center → port).
3. **Fixed heads and demands:** reservoir ports get H = z + liquidLevel + surfacePressure/(ρg); ideal reference nodes get H = z_port + p/(ρg) (a body of liquid at rest at that pressure). Assigned-flow ports get a demand equal to their flow (§4.8); every other port's demand is zero.
4. **Solve** with the GGA inner loop (§5.2) inside the outer loop for statuses and branch losses (§5.4).
5. **Map results** (`results.py`) to `SolvedState` (SDD §4.10), with physics flags, the per-element trace and the methods summary (§5.6).

**The nodal unknown is the energy grade line** H = z + p/(ρg) + v²/(2g). Every link's energy equation is H_from − H_to = h(Q), so pump head (an EGL rise) and fitting losses are exact. At a port, v is the velocity in the connected pipe's end segment; static pressure p = ρg(H − z − v²/2g), HGL = H − v²/2g. Boundary ports (reservoirs, reference nodes) report the quiescent boundary (v = 0). EPANET neglects velocity heads, so its nodal head corresponds to our EGL; EPANET comparisons compare EGL and flows.

### 5.2 GGA Core

`gga.py` implements the Global Gradient Algorithm (Todini & Pilati, 1988) generalized from the tested sketch that was in this section (pipes only): links supply h(Q) and dh/dQ (`elements.py`); the Schur-complement system A21·D⁻¹·A12·dH = rhs is assembled with `scipy.sparse` and solved with SuperLU (`splu`, which raises on an exactly singular matrix; `spsolve` only warns, and a warning is subject to process-wide filters that other libraries change — wntr turns this one into an error); flows are back-substituted. A diverging iterate is detected by finiteness checks, with numpy's overflow warnings off (`np.errstate`, thread-safe).

- **Friction** (`friction.py`): laminar Re < 2000, f = 64/Re (exact linear law, finite slope at Q = 0); turbulent Re ≥ 4000, exact Colebrook via `fluids.friction.Clamond` (`colebrook`, default) or Swamee–Jain in the exact form EPANET 2.2 evaluates, 5.74/Re^0.9 (`swamee_jain`, for EPANET comparisons; `fluids.Swamee_Jain_1976` writes 6.97^0.9 = 5.73997 and differs by ~2·10⁻⁶ in f); transition 2000 ≤ Re < 4000, the cubic Hermite interpolation in R = Re/2000 between the laminar value and slope at 2000 and the turbulent formula's value and slope at 4000 — EPANET 2.2's Dunlop polynomial (`hydcoeffs.c` frictionFactor), reproduced to 10⁻¹⁴ in `swamee_jain` mode. Transitional segments are flagged `TRANSITIONAL_FLOW`. Never call `fluids.friction.friction_factor` (it switches to 64/Re at Re 2040 with a 57% jump). Range flags: Swamee–Jain outside 5·10³ ≤ Re ≤ 10⁸ or 10⁻⁶ ≤ ε/D ≤ 0.05; Colebrook above ε/D = 0.05 (`fluids.friction.fmethods`).
- **Newton slopes** include df/dQ. Swamee–Jain differs from exact Colebrook by up to **3.0%** in f within its documented range (probe: Re 5000, ε/D 0.0189).
- **Branch legs carry head offsets** (zero for an ideal tee, the Crane path loss otherwise, §5.4). They are not iterated: each branch's center and port nodes become one head unknown with fixed offsets, and leg flows are rebuilt from continuity after every Newton step. (A Jacobian floor on zero-slope links stalled Newton on a large main feeding small-bore tubing.) `jacobian_slopes` keeps a small positive floor only for zero-slope pumps and valves.
- **Isolated sections** (nodes not connected to a fixed head through open links) are removed before solving; their links carry zero flow and their ports are reported without heads (`ISOLATED_SECTION`, info) — if they can sit at zero flow: their open links' zero-flow heads h(0) (−s²H₀(0) across a running pump, the cracking head across an open check valve, 0 otherwise) must close up around every loop, no active FCV may force flow around one, and no nonzero assigned flow may lie in one (§4.8).
- **Floating sections:** a section that no fixed head reaches but that cannot sit at zero flow (a pump loop behind a closed valve) is solved with one node held at an arbitrary head: its flows and head differences are exact, its pressure level undetermined. Its flows, head losses and pump and valve operating points are reported; its EGLs, pressures, NPSH available and PRV/PSV setpoint checks are not, and `UNDETERMINED_PRESSURE` (warning) names it. (EPANET gives such a loop the heads its closed links leak to it through their 1/CBIG conductance.) A section holding assigned flows floats only if they sum to zero; otherwise it is *disconnected*, left out of the inner solve (no heads, no flows) while the rest of the network is solved, and the outer loop re-opens an element around it or ends not converged, naming its nodes (§4.8, §5.4). A failed inner solve's message names a disconnected part too.
- **Held nodes** (active PRV / PSV): the valve passes exactly the flow of the pipe on its held port, so the continuity row of its other port carries that pipe's flow in the Newton step (a non-symmetric Schur matrix). EPANET lags this flow by one iteration, which converges only linearly, too slowly for 100 iterations when most of the flow returns to the valve around a loop. A held node fixes a head, but its valve's flow is determined only if it can leave towards a fixed head; when the valve's other side reaches no fixed head but through the valve itself (an active PSV as the only anchor of a pump loop), any loop flow holds the setpoint: the inner solve is not attempted and names the valve (the outer loop opens or closes it, as EPANET's badvalve).
- **Initial flows:** 1 ft/s (0.3048 m/s) in every pipe, as EPANET.
- **Convergence:** max |dQ| ≤ tolerance × max |Q| of the current iterate, continuity residual (inflow − demand) ≤ 10⁻⁹ × max |Q| + 10⁻¹⁴ m³/s at every node and summed over every component's nodes (the balance a user checks from the connection flows, which two port residuals of opposite sign could otherwise double), energy residual |h(Q) − (H_start − H_end)| ≤ 10⁻⁷ m + 4ε·max(\|H_start\|, \|H_end\|, \|h(Q)\|) on every link, ε = 2⁻⁵², the machine epsilon of double precision (residuals of the returned state). `tolerance` and `maxIterations` come from `project.settings.solverOptions`. The 4ε term (`gga.energy_tolerances`, METHOD_VERSION 1.2.0; proposal `vfd-slice2-discharge-pressure.md` §2.11.10 fix (b)) allows for the round-off of the heads the residual subtracts: from 2²⁹ m (about 5.4·10⁸ m) one unit in the last place of a head exceeds 10⁻⁷ m, and up to 1.1.0 an inner solve whose iterates reached such heads stalled at that floor until its iteration limit and was treated as failed (in the corpus, 27 main solves and 57 system-curve solves, §10.4). It exceeds 10⁻⁷ m only where that largest magnitude exceeds 10⁻⁷ m / 4ε, about 1.13·10⁸ m (8.9·10⁻¹³ m at 10³ m of head), and the methods summary states it.
- **Not converged:** the result carries `NOT_CONVERGED` and the convergence report (the largest residuals and where they lie). The flag's `maxContinuityResidualAt` and `maxEnergyResidualAt` name the node and the link of the largest residual that exceeds its stop tolerance above (a residual that is not finite always does, though its tolerance is infinite too where the iteration overflowed; the node and link are then the convergence report's), and are absent where none does: a residual within its tolerance, or exactly 0 (where the largest is the first node or link), says nothing about why the solve failed. Where the status and branch-loss updates keep returning to a state whose inner solve failed, the flag and the convergence report give the residuals of that solve, which the message describes, not those of the last solve (METHOD_VERSION 1.2.0, fix (a)).
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
| PDCV (active, Later) | fixed difference of inlet and outlet static pressure | EPANET 2.2's PBV is the closest reference for the active state; its status rules need their own derivation |
| PRV / PSV / FCV (active) | fixed outlet static pressure / fixed inlet static pressure / fixed flow | the setpoint head includes the port's velocity head, updated every Newton step; the PRV/PSV flow is the flow of the pipe on its held port, coupled exactly in the Newton step (§5.2) |
| Equipment | c·Q\|Q\|, c = ΔP_r/(ρ_r g Q_r²), or K/(2gA²) of its Cv or Kv | §4.9: `QuadraticLossLaw`; no status; constant K (ISA-75.01.01 eq. (1), the high-Re limit of Darby's 3-K) |
| Branch leg | head offset (Crane or Darby path loss) | §4.2, §5.4 |

**Valve K** (`valves.py`) is referenced to the inner diameter of the pipe connected to the valve's inlet port (its end segment). K is used as entered; Cv and Kv are converted with `fluids.fittings.Cv_to_K` / `Kv_to_K` (ISA-75.01.01; K = 1.6·10⁹·D⁴/Kv² with Kv = Cv/1.156…). A unit test derives the Crane form K = c·d⁴/Cv² (d in inches) from the Cv definition and exact unit definitions — c = 890.11 — which matches `fluids` to 7·10⁻¹¹ and the published coefficient 891 to 0.1%. Without a resistance: the Crane default for the valve type (`K_gate_valve_Crane`, `K_ball_valve_Crane`, `K_globe_valve_Crane`, `K_butterfly_valve_Crane(style=0)`, `K_swing_check_valve_Crane`, `K_globe_stop_check_valve_Crane(style=0)`), or an ideal control valve (K = 0 when fully open, stated in the trace). The butterfly valve's multiplier is tabulated for 2"–24" only (fluids docstring; `sizeRange` of the `butterfly_valve` fitting in `data/fittings.json`): a butterfly default or inline fitting outside 2–24 × 0.0254 m is flagged `CORRELATION_OUT_OF_RANGE`.

**Equipment c** (`equipment.py`, §4.9). A rated point: h_r = ΔP_r/(ρ_r g), c = h_r/Q_r², so ρgh = ΔP_r (ρ/ρ_r)(Q/Q_r)\|Q/Q_r\| at the solved density ρ, which cancels out of h. A Cv or Kv: the K of `Cv_to_K` / `Kv_to_K` at a 1 m bore, c = K/(2gA²). With K = 1.6·10⁹·D⁴/Kv² and A = πD²/4 the bore cancels: c = 1.28·10¹⁰/(π² g Kv²) = 1.32248132708·10⁸/Kv² s²/m⁵, and 1.76758281804·10⁸/Cv² (Kv = Cv/1.1560992283536566). By the definition (Kv m³/h of water at 1 bar), c = 10⁵·3600²/(ρ_w g Kv²); the two agree when ρ_w = 101.25π² = 999.297445610 kg/m³, fluids' water at 60 °F (its docstring prints 999.29744568, 7·10⁻¹¹ apart), and fluids' Cv constant equals 1/(gal·60·√(bar/psi)) to 1.9·10⁻¹⁶. So a Cv or Kv is the rated point 1 psi at Cv US gpm, or 1 bar at Kv m³/h, on that water (proposal `equipment-pressure-drop.md` §3.1; the reference suite derives its own c from CoolProp's water at 60 °F, 3.1·10⁻¹⁰ apart, as it does for valves).

Links with zero slope (branch legs, K = 0 valves) are merged exactly as head offsets; a small Jacobian floor remains only for pumps with flat curves, and for K > 0 valves and equipment near zero flow.

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
- **Speed-controlled pumps, flow setpoint** (CLAUDE.md D11; design and owner's answers in `docs/proposals/vfd-pump-modes.md`). With F(s, Q) = s²·H₀(Q/s), H = EGL_d − EGL_s, F_min/F_max = F(s_min/s_max, Q_set), F_lo = F(s_lo, Q_set) with s_lo = max(s_min, Q_set/x_mono) below s_max (a setpoint that would put it at s_max is rejected, below; `pumps.bracket_low` still caps it at s_max as a guard; F(·, Q_set) rises on [s_lo, s_max], so F_lo is the least head the pump gives at Q_set there, and F_lo = F_min when s_lo = s_min) and S_min/S_max = F(s_min/s_max, 0), the first rule that holds wins (`status.flow_pump_status`):

  | State (solver) | Inner-solve link | Rule |
  |---|---|---|
  | active (ACTIVE) | `FIXED_FLOW(Q_set)` | A0 → max if the GGA starves it (a side reaches no fixed head; a controller seeing no flow runs to maximum speed); A1 → max if H > F_max + Htol; A2 → min if H < F_lo − Htol |
  | max_speed (OPEN) | its own law, `PumpLaw(curve, s_max)` | X1 → active once Q ≥ Q_set (EPANET 2.2 `fcvstatus`); X2 `pumpstatus` at S_max |
  | min_speed (MIN_SPEED) | `LinkState(NORMAL, law=PumpLaw(curve, s_min))` | N1 → active once Q ≤ Q_set; N2 `pumpstatus` at S_min (closes only on a rising stretch) |
  | no_flow (CLOSED) | closed | C1 `pumpstatus` at S_max: re-opens at maximum speed once H ≤ S_max |

  Speed recovery (after convergence, active only): s_lo = max(s_min, Q_set/x_mono), Ĥ = clamp(H, F(s_lo, Q_set), F_max) (a change of at most Htol by A1/A2), s* the root of F(s, Q_set) = Ĥ on [s_lo, s_max] by `scipy.optimize.brentq` (xtol 1e-14, rtol 4ε; Brent 1973). It is exact, not an approximation: the speed enters only the pump's own head row, so the Newton system with s as an unknown is block-triangular and the flows and heads are those of the fixed-flow solve (EPANET 2.2's FAQ substitute for "a pump of a specific flow"). Uniqueness (`pumps.speed_uniqueness`, at build time): dF/ds = s·ψ(Q/s) with ψ(x) = 2H₀(x) − x·H₀′(x); ψ > 0 must hold on [0, x_last], checked exactly on each PCHIP cubic piece (a cubic in t: its least value at the ends or a root of a quadratic) and on the linear start tangent, else `CONTROLLED_PUMP_CURVE` naming the pump, the curve and the flow interval; beyond x_last the end tangent gives ψ > 0 up to x_mono = 2x₀ (x₀ its zero-head flow) when it falls, unbounded otherwise. On a curve that passes, a setpoint Q_set ≥ s_max·x_mono is `CONTROLLED_PUMP_SETPOINT` (`builder.validate_topology`, after the ψ test; owner's decision of 2026-10-23, §12): Q_set/s then lies beyond x_mono at every s ≤ s_max, where F(·, Q_set) falls as the speed rises, so no speed in the drive's range controls the flow, and two limit states (max_speed by A1, and s_min passing more than Q_set) could both satisfy the rules, the result depending on the solve's path. The message names the pump, the setpoint, the maximum speed, the curve, x_mono and the bound s_max·x_mono (`:.6g`), which the web app reads from it. The quotient form Q_set/x_mono ≥ s_max is rejected too: one ulp below the bound the division can round up to s_max, which would bring back s_lo = s_max; so every accepted setpoint builds with s_lo < s_max. An end tangent that does not fall (x_mono infinite) never triggers it. s_lo > s_min only when Q_set/s_min lies beyond x_mono: F(·, Q_set) then falls on [s_min, s_lo], where raising the speed lowers the flow (at a fixed system, dQ/ds has the sign of ∂F/∂s), a stretch no stable flow controller holds, so A2 tests F_lo, not F_min. For F_lo ≤ H(Q_set) < F_min the pump at s_min passing more than Q_set also satisfies N1/N2 (a drive saturated at its minimum): the solve starts active and A2 keeps it active in that band, but a pump that other statuses' changes bring to minimum speed there stays at it. The ψ test guarantees a unique speed root, not a unique operating state: on a drooping curve (head rising from H₀(0) to a peak) F(σ, ·) does not fall with Q everywhere, and X2, N2 and C1 close the pump against s²·H₀(0) as v1 closes a fixed pump, so a running state whose head exceeds that is not found: at maximum speed the result is no flow (`PUMP_FLOW_REVERSAL`, invalid), at minimum speed N2 closes against S_min while C1 re-opens against S_max and the solve ends not converged (§12: kept, the owner's decision). Every rule compares flows and head differences only, so the closed-off and floating-section logic (`closed_off_sections`, `zero_flow_openings`, `_level_changes`) applies unchanged, with a CLOSED controlled pump bounded as a fixed pump at s_max. Fallbacks: `_check_changes` applies A1/A2 at a failed solve's early iterate; `_open_bad_valves` tries open (maximum speed), then — for options holding a pump only, with their valves left active — minimum speed, then closed, so a valve-only network takes the v1 option sequence. Two flow controls in series holding the same flow (two controlled pumps, or one and an FCV, with equal setpoints) leave the pressure between them undetermined: a converged state with a controlled pump at a limit, or an open FCV, at its setpoint flow (within Qtol or the GGA's flow resolution) is re-tested with it active, and if the GGA then finds the pressure between it and a flow control undetermined, with a controlled pump among them, the solve is reported not converged naming them (whichever side rounding left the exact X1/N1 and FCV comparisons on); valve-only networks are not concerned. When the statuses of such controls cycle instead, or their fallbacks return to states already solved, the same test, with the cycling flow controls held at their setpoints together, finds the pressure between them undetermined and the message says so (`status._equal_setpoints_note`: equal setpoints, a controlled pump among them). Results: speed s* (active), s_max (max_speed, no_flow), s_min (min_speed); curve, range, η₀(Q/s), NPSHr and power at that speed; `PumpResult.control`; `PUMP_SETPOINT_NOT_MET` (info) at a limit or with no flow off the setpoint by more than Qtol. No new tolerance (Htol, Qtol). Tests: `tests/unit/test_speed_control.py` (uniqueness against dense sampling, the setpoint bound at ±10⁻⁹ and ±10⁻⁶ relative on linear and PCHIP curves and the quotient form's invariant s_lo < s_max, the closed-form speed, law override identity, fallback sequences, the A2 bound F_lo, metamorphic M1/M2; M1 on a line with one steady state, since where several states satisfy every rule a controlled and a fixed solve may reach different ones, proposal §7.3), `test_status_rules.py` (the rule table at the tolerance edges), and in the reference suite `tests/reference/test_pump_control.py` (the bound s_max·x_mono from the end tangent of SciPy's PCHIP, derived in the test: rejected at 1 + 10⁻⁶ of it with the owner's message, solved at 1 − 10⁻⁶ in a state that keeps the rules; the ψ test first; end tangents that do not fall never rejected).
- **Check valves:** close when the flow would reverse or the head difference falls below the cracking head; reopen above it (EPANET `cvstatus` extended with the cracking head). Closed → `CHECK_VALVE_CLOSED` (info).
- **PRV/PSV/FCV:** EPANET 2.2 `prvstatus`/`psvstatus`/`fcvstatus` translated to EGL. Differences from EPANET: an FCV closes on reverse flow (EPANET lets it pass as an open valve); an active FCV opens once the head across it is below its fully open loss at the setpoint, K_open·Q_set²/(2gA²) (EPANET waits for a reverse head, which leaves a valve with a resistance "throttling" with a K below its fully open K); an active state with no solution falls back first to the states the valve rules give at that solve's last finite iterate within 10 iterations (EPANET 2.2 applies the PRV/PSV rules at every iteration, so a valve whose setting cannot hold leaves its active state before the iteration diverges), then to open, then closed, one valve at a time. A PRV or PSV inside a closed-off or floating section, or closed between two such sections, compares its setpoint with their free levels: it closes on reverse flow, and otherwise these valves keep their states if one set of levels holds them all while the closed elements around the sections stay closed (each valve state holds on a union of regions of difference constraints, below; the choices are enumerated, up to 4,096 Bellman–Ford tests). If none does, the fewest elements are let go, the PRVs and PSVs first, then the closed elements, preferring a result not already solved: at levels that hold the others, each takes the state its rule gives there, except that a PRV or PSV that cannot be active (the side it draws from or delivers to reaches no fixed head) closes if it was open and opens if it was closed. Not at setpoint → `CONTROL_VALVE_SETPOINT_NOT_MET` (info).
- **Closed-off sections:** a section cut off by closed elements (the pipe between a pump and a check valve that closed in the same pass) has no head, so its neighbours' rules cannot test it. The closed elements around it are re-tested against the heads it can take at zero flow: each stays closed only for some head (a pump while the far side is more than s²·H₀(0) above the near side, a check valve while its forward head is at most its cracking head, an FCV while it has no forward head, a PRV/PSV per its CLOSED rule), which are difference constraints between section heads; a negative cycle (Bellman–Ford) means no head keeps them all closed, and the elements on it are re-opened. A floating section is tested the same way, its heads the solved relative heads plus a free level. A pump, check valve or FCV with both ports in one such section follows its rules with the section's heads (a pump held at no flow inside a closed-off loop sees no head across it there and re-opens). EPANET avoids the question by keeping a 1/CBIG conductance across closed links.
- **Disconnected sections** (assigned flows that do not sum to zero where no fixed head reaches, §4.8): their level would run away, down with a net demand and up with a net supply. The closed elements around one are tested at that level (`disconnected_openings`: a pump, check valve or FCV opens when the section is on the side its flow would run to, a demand beyond its outlet or a supply at its inlet, never against its one-way rule; a PRV or PSV takes the state its rule gives there, open when the other side's head is unknown and its flow could run toward the section), and those that open are re-opened together, or one at a time when that state was already solved. Elements with a port in the section keep their states, and `zero_flow_openings` takes no constraint from an element beside it. With none to open, the solve ends not converged, and the message names each assigned-flow node of the section with its flow and each element closed around it with the reason (the status the user set, a side with no fixed head, or its rule). EPANET 2.2 reaches the same state through its 1/CBIG conductance across closed links, by which a cut-off demand's heads run away until its rules open them, or reports the system disconnected.
- **Flow controls feeding assigned flows** (§4.8): a control in a fixed mode beside a part that no fixed head reaches but that holds assigned flows makes the inner solve name both, unsolved; its rules then take it to a limit (an FCV open below its setpoint, a speed-controlled pump at a speed limit). A converged state in which a control at its limit alone feeds assigned-flow nodes taking exactly its setpoint is over-controlled (`_over_controlled`: not converged, naming them), and a solve that ends not converged for another reason (statuses cycling, the outer-iteration limit, an inner solve that fails) starts its message with the reason when a flow control alone feeds assigned flows equal to its setpoint, or ones it never passes (more than an FCV's setpoint, or reverse flow) (`_assigned_flow_note`). Networks without assigned flows keep every message.
- **Branches:** the Crane K is linearized in the flow split around the last split and re-centered each iteration (lagging the whole loss made Newton diverge on manifolds of short taps), and the leg's own-flow dependence enters the Jacobian. A leg whose flow reverses and reverses back (patterns A, B, A in successive updates) is held at zero flow while its head lies between the two patterns' zero-flow limits (facing legs of a rung are held as a pair, released one at a time). These holds and releases change a finite active set (each branch is held at most twice per solve), so the iterations that make them are not counted against the 30: in a long Crane-tee ladder the rung legs join the reversals a few at a time, and the counted iterations stay at a handful while the total grows with length. Every branch starts as an ideal junction (zero losses); each outer update then takes the pattern and the fluids K values at the solved split, as a tangent in q about it. Where the split alternates across a step of a Crane correlation (a split at which the fluids function switches formula, q = 0.4, 0.5 or 0.6, and K actually jumps by more than 1e-4 at that β and angle), K swings between two values. Once the alternation has settled — K is back within 1e-4 (`K_TOL`) of its value two updates before while still changing by more than that, in the same pattern, and pump and valve statuses have stayed the same for the last three solves — the two latest splits are the 2-cycle of the update. Every path's K (the run path's too) is then held, constant in q, at the mean of the fluids values at those two splits (both reported in the trace and in the flag's `details`), and flagged `CORRELATION_OUT_OF_RANGE`, until the solved split leaves the interval between them or a status changes. A K that alternates the same way with no step between the two splits (or while statuses change) is under-relaxed instead: K halfway between the value the leg used and the fluids value at the solved split, the slope kept. The 2-cycle does not depend on the starting point (the held result agrees to about 1e-10 from different warm starts), and to second order it is the pair of splits each side's formula gives when carried across the step (reference case `wye_crane_step_hold`).
- **Oscillation:** statuses that change together can step over the state that holds them all (a PSV and a pump, each rule reacting to the other's previous state). The first time pump and valve statuses return to a state already solved, in a cycle with a step that changed several of them, the loop changes one status per outer iteration from then on (the first, by component id, that leads to a state not yet tried): it goes back to the state just solved when the step closing the cycle changed several, and on into the state it repeats when that step changed one (the cycle's steps that changed several are then split as they come round again). A state reached again in that mode goes back to the latest state where the rules asked for several changes and takes another of them, the first by component id that leads to pump and valve statuses not yet reached (chronological backtracking, within the 30 counted iterations). A cycle whose steps each changed one status, or a state reached again with no such change left, ends the loop with `converged: false`, the oscillating components named in the convergence report, and `NOT_CONVERGED`.

### 5.5 NPSH Available

`npsh.py`. At each pump suction port (elevation z_s, EGL H_s):

```
NPSHa = (H_s − z_s) + (p_atm − p_vap)/(ρg)      = absolute static head + velocity head − vapor head
NPSH margin = NPSHa − NPSHr(Q)                     (when an NPSHr curve is given; < 0 flags CAVITATION)
```

p_atm is `settings.atmosphericPressure` when set, else `fluids.atmosphere.ATMOSPHERE_1976(siteElevation).P` (US Standard Atmosphere 1976; 101 325 Pa at 0 m, 89 876 Pa at 1 000 m). Any node whose absolute static pressure is below the vapor pressure (or ≤ 0 Pa when none is known) is flagged `BELOW_VAPOR_PRESSURE`; a reservoir surface below its vapor pressure (a boiling tank) is flagged too.

### 5.6 Trace, Methods Summary and System Curves

- **Trace** (`trace.py`, shape in SDD §4.10; pipes, fittings and curve points numbered from 1 as in the app, `labels.py`): built after the results from the values the solver used, one `ElementTrace` per component and connection — inputs with their source (user / default / library / computed), equations as plain text, correlations and data sources with citations, intermediates (restating the result fields, or following from them by the listed equations) and notes (regime, state and the rule behind it, assumptions, flags). Unit strings are the ones `apps/web/src/lib/utils/trace.ts` converts (`Pa(g)`, `Pa(a)`, `Pa (difference)`, never bare `Pa`). Elements with no result (closed off, or a solve that did not converge) keep inputs, equations and sources with a note.
- **Methods summary** (`methods.py`): one `MethodsSummary` per solve — sections Network solution, Pipe friction, Minor losses, Branches, Pumps, Valves, Equipment (only with equipment, §4.9), Fluid properties, Atmosphere and NPSH, Conventions; global assumptions; library versions (opensolve-pipe, fluids, CoolProp, numpy, scipy) and `METHOD_VERSION`. Every number in it is a solver constant or a value of the solve.
- **System curve** (`system_curve.py`): at each flow the pump's link becomes a `FIXED_FLOW` link (`run_outer_loop(..., forced_flows={pump: Q})`; the pump takes no part in the status rules, every other element follows its own), and H_sys(Q) = EGL(discharge) − EGL(suction). A speed-controlled pump's own control is replaced by the forced flow, so H_sys is defined as for any pump; other speed-controlled pumps that are on keep regulating (an off one stays closed, and no trace says it regulates), and a warm start copies their statuses (MIN_SPEED included, its law following from it). Default flows 0 … 1.2 × the curve's largest flow × s (a speed-controlled pump's `speed`, its maximum). Every point whose forced flow passes with a determined head reports that head (owner's decision of 2026-10-23, §12). Each point starts from the previous converged one (statuses, branch losses and flows; the first from the solve when the solve computes the curves, from the initial state for `POST /api/v1/system-curve`), and one that does not converge from there is solved again from the initial state. A point that still has no head while the forced flow has a way through (`has_way_through`: each side of the pump reaches a fixed head, or the other side, through links that no status set by the user closes) is solved again from the initial state, if it did not start there, and then from it with the active control valves open (`initial_controls(open_valves=True)`, the state EPANET 2.2's badvalve gives a valve it takes out of its active state); the first of these solves that gives a head, or finds a control valve in series at its switch (an undetermined head, below), is used and the next point continues from it, and with none the point keeps its first result. A flowing point whose flow exceeds what every way from the pump's discharge back to its suction can pass that way is not solved again, since no steady state carries it (`flow_limit`, by the max-flow min-cut theorem, Ford and Fulkerson 1956): the reservoirs and reference nodes are joined in one node, which supplies the net assigned flow Σd; assigned flows are fixed demands and supplies, so a flow with them exists only if no node set holds more net supply than the capacity leaving it (Gale, D., "A theorem on flows in networks", Pacific Journal of Mathematics 7(2), 1957, 1073-1082): a demand on the pump's side of a cut that no fixed head reaches takes part of the forced flow, and one beyond it adds to what the cut must pass, so a cut's bound is its capacity plus Σ_{d in S} d − [fixed heads in S]·Σd for the discharge's side S (minus that for the suction's side), and the message beyond it names the assigned-flow nodes counted (a bound below zero, where the assigned flows there need more than the cut passes, says that the pump would have to pass that flow in reverse, so no forced flow, zero included, has a steady state); read the other way, the same condition bounds the forced flow from below (`FlowLimit.floor`): Q ≥ Σ_{d in S} d − [fixed heads in S]·Σd − the capacity into S for the nodes S that reach the discharge through unlimited ways, and Q ≥ [fixed heads in T]·Σd − Σ_{d in T} d − the capacity out of T for the nodes T the suction reaches so (each with the pump's other port outside it and a limited element across it; the larger is the floor, computed only with assigned flows, the one case where it can be above zero), so a point below the floor (a demand on the discharge side that a check valve keeps every fixed head from feeding, or a supply on the suction side that one keeps from draining) is not solved again either, and its message names the elements across that cut with their rules, the assigned-flow nodes counted and the least flow the pump must pass; an FCV the rules govern passes at most its setpoint forwards and nothing in reverse (`fcv_status`), a check valve, PRV, PSV or pump they govern nothing in reverse, and every other element any flow either way, or none where a status the user set closes it; of the two cuts tried (the nodes the discharge reaches through unlimited ways, and those that reach the suction so) the smaller bounds the flow, with a margin of Qtol per element across it and the GGA's continuity tolerance per node on its side. A point whose flow is that limit or the floor, within the same margin, still without a head, is solved once more for each FCV across the cut, with that FCV held open (`run_outer_loop(..., held_open=...)`, as `failed_open` holds it) and every other element following its rules from the initial state (`_held_open_switch`): every steady state there passes each FCV of the cut at its setpoint, where `fcv_status` turns an open FCV active as soon as its solved flow reaches its setpoint (with no tolerance) and an active one beside the forced flow is starved, so from every ordinary start a series FCV could end closed at its own setpoint flow, depending on rounding and on the point before (a setpoint the default range samples, such as 0.018 m³/s, which `numpy.linspace` gives as 0.018000000000000002). If the network carries the flow with a determined head with the FCV held open, and the FCV passes its setpoint, the FCV is at its switch and the head is tested as below; otherwise (a PRV beyond the FCV that passes nothing) the point keeps its result. Both starts are needed: a series FCV, PRV or PSV that starts active (in the initial state, or after a point where it held its setpoint) sees no fixed head between it and the forced flow, is starved and closed (`gga`), and leaves a closed-off section between it and the pump. Before, the zero-flow point closed it that way, every later point inherited the closed valve, and each was reported as having no way through, which was not true. From the initial state the status rules open the valve again at every flowing point below its switch, but at zero flow nothing drives it open, so only the open start finds the head at zero flow behind a series FCV or PRV, or with a series PSV (measured on the reference and unit-test series networks with the open start disabled: every flowing point keeps its head, and only the zero-flow point loses it). The same retries give a head to a zero-flow point whose start (the network's own solve) left a check valve or another pump closed around a side of the pump: at zero flow the element may also be open, and that state, which a start from the initial state reaches, determines the head (before, such a point reported no way through). A point without a head says which of these it is (`system_curve._message`): **no way through** (no other start is tried); **no steady state carries it**, beyond the cut's limit or below its floor, naming the elements across the cut and the rule of each (a series FCV above its setpoint, a check valve facing the pump) and the assigned-flow nodes counted; **no steady state found**, naming the elements the status rules close around the pump's sides and the rule of each (a PRV whose outlet side needs more than its setting, a PSV whose inlet would fall below it, elements no cut shows); an **undetermined head**: a side of the pump on a free level (closed off at zero flow, or carrying flow with no fixed head; before, a zero-flow point there reported a head against the solver's arbitrary reference level), or a control valve in series at its switch (an FCV passing exactly its setpoint within Qtol or the GGA's flow resolution, open or held open at the cut's limit, a PRV outlet or PSV inlet at its setting within Htol), where the valve could also hold the flow throttled with any higher head, confirmed by re-testing it active with the GGA's undetermined-pressure test, and stated with the open-valve head as the bound of the heads (`_head_side`): their floor for a valve that draws from the discharge's part of the network or delivers into the suction's (in series), their ceiling for one that delivers into the discharge's part or draws from the suction's (beside the pump, with an assigned flow there, as at a floor set by an FCV); or **not converged**, with the outer loop's message. Each case is also given as data (`PointReason`, built where its message is, from the same values, so a message's text is unchanged and the two agree; `SystemCurvePoint.reason` and the fields after it, SDD §4.10): its code (`no_way_through`, `beyond_limit`, `below_floor`, `no_steady_state_found`, `free_level`, `closed_off`, `valve_at_switch`, `not_converged`, or `not_computed` for a point the budget did not reach), the pumps and valves the message names in its order (for `not_converged`, the outer loop's `oscillating_components`, as `/solve` reports them, maybe none: the elements closed around a part no fixed head reaches, its assigned-flow nodes and an unsupported wye are in its message only), the assigned-flow nodes a bound counts, the cut's bound and what its elements pass (`limitFlow`, `passedFlow`: equal without assigned flows), the open-valve head and which side of it the heads lie (`openHead`, `openHeadBound`: 'lower' for "at or above", 'upper' for "at or below"), and the starts tried (`startsTried`). The web app words them with names and display units (`utils/system-curve-text.ts`, SDD §3.1.3). A side of the pump that reaches assigned-flow nodes but no fixed head (a pump whose only outlet is a demand) carries a steady state only at the flow they fix, and there its head is undetermined, so none of its points has a head: each is not converged, and its message names the nodes and the flows that the forced flow and they fix (the inner solve's, §4.8); a forced flow of zero leaves them disconnected, which the message says (`has_way_through` counts no assigned-flow node as a way through). In series, an FCV passes a forced flow below its setpoint fully open (so H_sys(0) is the static difference) and none above it, and a PRV passes a flow fully open while the outlet EGL the downstream pipe imposes is below its setting and none once it is above; only the switch flow itself is undetermined. A curve whose every point has a head costs one solve per point, as before. A point without a head while the flow has a way through costs up to two more solves from the initial state, each about as long as the network's own solve, and a point at the cut's limit one more per FCV of the cut. Over the corpus (§10.4; 4 CPUs, 3 workers) the solves with their system curves took 688 s, against 555 s before (1,555 s without the cut's limit): the 1,357 projects with a point without a head 1.25 times as long at the median and at most 16.4 times (`unit_seed2237`, 0.36 s to 5.9 s for its pumps' 41-point curves), the other 2,763 as long as before. The 41-point curve of a Crane-tee ladder's pump through a series FCV set at 30 % of the range (20 to 206 components) takes 0.9 s to 14.8 s, against 0.3 s to 2.5 s before, when no point had a head (41.4 s at 100 components and the 45 s budget at 206 without the cut's limit). A large network with many points without a head below the limit can still reach a request's 45 s budget; the points not reached then say "not computed" (CLAUDE.md D10). `POST /api/v1/system-curve` returns every point with `converged`, a message and its reason as data; `SolveOptions.includeSystemCurve` fills `PumpResult.systemCurve` of each running pump with its points that have a head, and its trace note counts those without one. The web app solves with `includeSystemCurve: false` and requests one pump's curve when its chart is shown (CLAUDE.md D10, SDD §3.1.3); every pump's trace carries the H_sys definition (`trace.SYSTEM_CURVE_EQUATION`), and a solve that computes the curves adds a note on how many points were solved. Closed-form tests: `tests/reference/test_system_curves.py` (single line, series and parallel pumps with the other pump running; a pump whose way out is an FCV or PRV in series, fixed-speed and flow-controlled, over the default 41 points with H_sys = H_R2 − H_R1 at zero flow and the open-valve heads below the switch flow, no steady state above it, and an undetermined head at the switch flow, requested on its own and after points below it, whose message names the valve and the open-valve head as its floor; FCV setpoints of 0.012, 0.018 and 0.024 m³/s on the default range's grid). Unit tests: `tests/unit/test_system_curve_points.py` (a series FCV on either side of the pump, at its setpoint flow exactly, one ulp above and within Qtol either side, on its own and after a point below it; an FCV ahead of a PRV that passes nothing, whose setpoint flow has no steady state; a PRV below and above its setting, a PSV before the pump, a side on a free level, the flow limit of a series FCV and of a check valve facing the pump, and the solves per point); `tests/unit/test_system_curve_reasons.py` (a network for each reason, derived by hand: its code, every field and the whole message, warm and cold starts, and the endpoint's camelCase fields: empty ones on a point that has a head, the open head and its bound at an FCV's switch, the starts tried behind a PRV, two FCVs of a cut in the message's order, and a not-converged point whose `componentIds` are empty, as `/solve`'s `oscillatingComponents` are, while its message names the check valve closed around an assigned flow).
- **Flag severities** are fixed per code (`flags.FLAG_SEVERITY`); `make_flag` rejects a mismatch, and `tests/unit/test_flags_audit.py` checks each GOALS §4.6 condition.

### 5.7 Scenarios and Goal Seek

Both sit outside the network solver, so §5.1–5.6 don't change. Both are built: scenarios (CLAUDE.md D15; design and measurements: `docs/proposals/scenario-manager.md`) and goal seek (D16; design, measurements and as-built notes: `docs/proposals/goal-seek.md`).

**Scenarios** (`models/scenarios.py`, `services/scenarios.py`; models in SDD §4.12):

- **Allow-list.** `COMPONENT_FIELDS` (every class of the `Component` union, `{}` for none), `PIPE_FIELDS` and `PROJECT_FIELDS` map each overridable field to an `Overridable` (the snake_case path from the target, the model that must hold its last attribute, the keys of a group, its trace unit, which for a control valve's setpoint depends on its type, and its label, which for an equipment item's `rating.value` is its Cv or Kv). The same data generates `x-override-fields`, and its numeric values are what goal seek varies (SDD §4.13). An equipment item's `rating` is a whole value, as the `fluid` is: its four values are held by the union member of their kind (`RatedPoint`, `RatedFlowCoefficient`), so the holder test makes a value of the other kind `not_applicable` (with the reason in `MISSING_HOLDER`) and `overlap_problems` refuses a rating with one of its values. `_clean` drops the union's tag from a validation error's location, as it drops the fluid's kind, so a bad rating value is matched to its override; `value_text` writes a whole rating as "Cv 120" or "50000 Pa at 0.015 m³/s, 999.103 kg/m³".
- **`apply_scenario(project, scenario_id) → AppliedScenario`** (the effective `project`, plain, without `scenarios`, and one `AppliedOverride` per override): (1) find the scenario, else `ScenarioNotFoundError` (404); (2) dump the base with `exclude_unset=True` and drop `scenarios`; (3) resolve each override against the base: its target (a component by id, a connection by id and the pipe index, or the project; missing: `orphaned`), its field in the target type's table (absent: `not_applicable`) and the holder of its last attribute (a pump's `control`, a `BuiltinFluid`; missing: `not_applicable`), and record the base value; (4) write each applied value, raw, at its location (a `spec` first removes all five spec keys; a spec with another key is `invalid_pipe_spec`); (5) `Project.model_validate`: every model rule checks the scenario's values. A `ValidationError` is mapped to the overrides whose written location contains the error's (after dropping the union tags pydantic inserts after a component index and after `fluid`), one issue per pair, `body.project.scenarios.{s}.overrides.{j}.value{.subpath}: {msg}`; an error of an object-level validator (a location the written values lie inside: `minSpeed` below `speed`, an FCV's setpoint bound, a custom pipe's bore) is one issue, as in the hand-edited project, at the override(s) whose base value clears it (the project validated again with that override left out), or at every override of the object when no single one does, `body.project.scenarios.{s}.overrides.{j}: {msg}`; with `msg` the schema's own (never the input; an unknown key's name is replaced by `(unknown field)`), and raised as `ScenarioOverrideError` (400). The result equals the project whose JSON was edited by hand, `fields_set` included (trace sources depend on them), so the scenario's solve is that project's solve bit for bit; the order of overrides cannot change it, since a scenario sets each value at most once and they are resolved against the base.
- **`solve_case(project, options, scenario_id)`** applies the scenario and solves the effective project with `solve_project`, mapping its `TopologyError` and `FluidError` to `ScenarioTopologyError` (422) and `ScenarioFluidError` (400), whose messages name the scenario by id; `annotate` then adds the scenario's text in one place: a first methods section **Scenario** (§5.6; its opening sentence, the description, each applied override with its base value and each ignored one with its reason, citing D15) and one first note in the trace of each component or connection an applied override changes. Every other field of the solved state is the solve of the effective project. `system_curve_case` does the same for `/system-curve`, checking the scenario (404), then its values (400), then the pump (404), then topology and the fluid.
- **Base path unchanged.** The routers call `solve_project` / `system_curve` exactly as before when the request has no `scenarioId`; `Project.scenarios` is left out of every dump when empty (`exclude_if`), so stored cases and corpus dumps do not change, and nothing under `services/solver/` reads it.
- **Solve all** is one independent request per case, sent one after another by the web app; each has its own 45 s budget. There is no batch endpoint.
- **Web mirror.** `utils/scenarios.ts` applies a scenario in the browser for display and editing only (the forms show the case's values; results always show the server's record, `SolveResponse.scenario`). `tests/fixtures/scenario_cases.py` generates `apps/web/src/lib/utils/__fixtures__/scenario-cases.json` with the real `apply_scenario` (applied, invalid, not-found and rejected cases), `pnpm gen:types` regenerates it with `openapi.json`, `tests/unit/test_scenario_cases.py` fails while it is stale, and `utils/scenarios.test.ts` runs the mirror on every case.
- **Bounds** (measured at the largest project, SDD §7.1): 20 scenarios, 30 overrides each, a 500-character description, `pipeIndex` below `MAX_PIPES` = 100.

**Goal seek** (`models/goal_seek.py`, `services/goal_seek.py`, `routers/goal_seek.py`; models in SDD §4.13): an outer loop that writes the variables into the case, runs the full solve (§5.1) and reads the goal results. Nothing under `services/solver/` changed.

- **Checks** (`prepare(request) → Prepared`, in this order, no solve): the scenario (`apply_scenario`: 404, then 400 for its values); the case's fluid (`fluid_properties`: 400, `ScenarioFluidError` for a scenario); every variable and goal resolved against the case, the variables with the scenario service's planner (`plan_override`; `orphaned` → 404 `NOT_FOUND`, `not_applicable` → 400 in goal seek's own words), then 404 for every unknown component, connection, pipe or port (`GoalSeekNotFoundError`, ids named) and 400 for every input that does not apply, NPSH data missing or a tolerance below its smallest (`GoalSeekInputError`, by index, ids only in `componentIds` / `connectionIds`); the case's topology (`build_network`: 422, `ScenarioTopologyError` for a scenario); the bounds: each bound written into the case (the other variables at the case's values) and validated, 400 at `body.variables.{i}.lower` / `.upper` with the schema's message. Every model rule on these values bounds one value (the field bounds, `minSpeed < speed`, the FCV range; tested), so these 2n checks prove every trial in the box validates. Topology and fluid errors at trial values (`CONTROLLED_PUMP_SETPOINT` at a low speed, a temperature beyond CoolProp's range) are not request errors: those trials are unusable.
- **One evaluation.** The case is dumped once (`exclude_unset`, `scenarios` dropped); a trial deep-copies the dump, writes each value at its location (a resistance as `{kind: coefficient, value}`, a temperature inside the fluid, an equipment item's value inside its rating), `Project.model_validate`s it and runs `solve_project(trial, None)`: cold, without system curves, exactly `/solve`'s state with `includeSystemCurve: false`. It is usable when the solve converged and every goal has a value (`goal_value`: the published field, or no value with the reason); otherwise `not_converged`, `no_value`, `topology_error` or `fluid_error`. Each records the element states (pump status and control state, valve state, branch pattern) with their flows; a change counts only for an element that carries more than 10⁻⁶ m³/s in one of the two states (D13). Only the current best evaluation's `SolvedState` is kept.
- **The map.** Each variable is searched in u ∈ [0, 1], linear in x, or in log x for `length` and `resistance`; u ≤ 0 gives exactly `lower`, u ≥ 1 exactly `upper`, u0 exactly the start, every other trial is clamped into the bounds (`Axis`); where the ratio upper/lower overflows (a lower bound below about 10⁻³⁰², which a length's field allows) the log map is computed in log x, exp(ln lower + u (ln upper − ln lower)), the same map, and every other range keeps the formula lower · (upper/lower)^u bit for bit (as built). The start is the case's value, clipped into the bounds, or the middle of the bounds on the log scale for a resistance the case does not hold in that coefficient.
- **The search** (`search`, the pure core, tested with synthetic evaluators). Scaled residuals r = (value − target)/tolerance; met at |r| ≤ 1, stop at max |r| ≤ 0.1. The reported evaluation is the least usable one by (tier, distance from the start in u, index) for tiers 0 and 1 and (2, Σ r², distance, index) for tier 2, each r rounded to 10⁻³ of its tolerance in that cost (as built: round-off never picks a value on a plateau). A start that meets every goal stops at once (`met_at_start`). One variable (`scan_brent`): the start, the 9 values k/8 coarse to fine (0, 1, ½, ¼, ¾, ⅛, …), Brent's method (`brentq`, xtol 10⁻¹⁰ of u) in the sign change nearest the start, failed solves inside a bracket probed for up to 4 rounds, a bracket that closes with both sides more than one tolerance away a `jump`, one separated only by failed solves an `unsolved_crossing`, each giving way to the next bracket; with no sign change, the closest value on a plateau (the run of neighbouring values tied with it within 10⁻³ of a tolerance, as built), at a bound or by `minimize_scalar` (bounded, xatol 10⁻⁵) between the best value's neighbours, a sign change among the values it solves then searched as the scan's are (as built). Several variables (`least_squares`): dogbox on r in v = u − u0 (bounds (−u0, 1 − u0), so the first trust region spans each range) with goal seek's own forward-difference Jacobian (10⁻⁶ of u, backward at an upper bound or when the forward trial is unusable, one solve per variable), ftol = xtol = gtol = 10⁻¹⁰, started from the start or, when the start is unusable, from the first usable of the middle of the bounds and each variable's 9 scan values with the others at their starts (as built: from an unusable start every slope step is unusable too, and the Jacobian is zero); an unusable evaluation is a penalty residual (max(1000, 10 × the largest |r|) in every goal); an ending not met is diagnosed from the last Jacobian's known columns (`slope_unknown`, `variable_no_effect`, `variables_collinear`, `goal_no_effect`). The stop reason follows the reported evaluation: met whenever it meets every goal.
- **Limits.** 60 evaluations for one variable, 20(n + 1) for n, inside the request's 45 s budget: an evaluation after the first starts only while 1.5 × the slowest so far + 1 s remains; a deadline inside an evaluation makes it `not_computed`, and the response is 200 with the best evaluation so far (`time_budget`); only the first evaluation's deadline is 503 `TIMEOUT`; a cancellation always propagates. `workers.MAX_GOAL_SEEKS` = `SOLVE_WORKERS − 1` (1) goal seeks are in the pool at once, counted until their work stops; another is refused at once with 503 `SERVER_BUSY`, so a plain solve always has a worker. `/api/v1/goal-seek` is rate-limited with `/solve` and `/system-curve`.
- **Result.** `goal_seek_case` builds `GoalSeekResult` (every evaluation with its purpose and outcome, each variable with its start, source, value and the `override` that applies it, each goal with its tolerance's source, the structured notes) and annotates the reported evaluation's state: a first methods section **Goal seek** (the case, the method with every constant and its citations: Brent 1973, Voglis and Lagaris 2004, Dennis and Schnabel 1983, SciPy, D16; each variable and goal; why it stopped; the notes; the rule that picks the value reported), then the scenario's text with each override a variable replaced marked and its opening naming the goal seek's values as the exception (`annotate(state, applied, replaced, goal_seek=True, parts=…)`; the mark of a whole value whose parts were varied names them, "the values found take the place of its rated pressure drop and rated flow", and the fluid's keeps `REPLACED_TEMPERATURE`), and one first note in each varied element's trace. A variable inside a whole value the scenario overrides (`_Var.whole`: `fluid` or `rating`) gets that whole value as its `override`, read from the reported evaluation's dump (`Prepared.written(xs)`, every variable written), so two values of one rating get equal overrides holding both; the fluid's override is the same as before, bit for bit. A rating value the case's item does not hold is `VARIABLE_NOT_APPLICABLE`, with the reason ("the equipment is rated by a Cv in this case (rating.pressureLoss applies to a rated point)"; the id only in `componentIds`, D16). Messages give SI numbers to 6 significant digits, or as many more as it takes for the two ends of a bracket or range to differ (the web's texts too, in display units), and number evaluations from 1, as the app numbers its trials (D10); data indexes stay 0-based. Deterministic: the same request gives the same evaluations, values and messages, apart from `seconds`, `computeTime` and `timestamp`, except a run stopped by time.
- **Web.** `utils/goal-seek.ts` (catalogues read from `x-goal-variables` and `x-goal-quantities`, default bounds, lapses, `toRequest`, words for every stop reason and note code, the trial table, the report, `applyToCase` and `asNewScenario`), `GoalSeekDialog.svelte` with `goal-seek/` (goal and variable cards and forms, the result). The store (`state/project.svelte.ts`) runs one goal seek at a time (`runGoalSeek`, `cancelGoalSeek`, `goalSeek`), and every Solve control reads one getter, `calculating`; a result goes out of date by its case's key, recomputed on every change. While the setup names an element, new elements never take its id (`factory.ts`, `edit.ts`). `tests/fixtures/goal_seek_cases.py` generates `utils/__fixtures__/goal-seek-cases.json` with the real trial builder and goal reader (`pnpm gen:types`; `test_goal_seek_cases.py` fails while it is stale), and the web's Apply and Compare readers are tested on it.


### 5.8 Design Checks

Opt-in design practice (CLAUDE.md D19; design and as-built notes: `docs/proposals/design-checks.md`; models in SDD §4.15), outside the network solver: the network's build, solve and results (`builder.py`, `gga.py`, `status.py`, `results.py`) read neither the checks nor the pump curve's manufacturer data, and `solve_project` adds the checks to the state they built.

- **Models** (`models/design_checks.py`): `DesignChecks` (`npsh_margin`, `operating_region`, `pipe_velocity`, each optional, each with a `source` discriminated on `kind`), on `ProjectSettings.design_checks` (left out of every dump when None, `exclude_if`, so corpus dumps and links without checks do not change); `PRESETS`, published by `DesignChecks`'s `json_schema_extra` as `x-design-check-presets`; the ordered pairs' validators and `x-ordered-fields` (`ordered_fields_extra`, also on `AllowableOperatingRegion` in `models/pumps.py`). `DesignCheckResult` is an `OutputModel`.
- **Evaluation** (`services/design_checks.py`). `solve_project` ends with `_with_design_checks(project, state)`: `evaluate(project, state)` (empty without checks or when the state did not converge) and, when a check is on, `methods_section(project)` appended last to the methods summary. Per pump (component order) `_npsh` then `_region` (which adds the manufacturer-data checks, at Q/s, for a running pump whose curve has them); then `_velocity` per link result in connection order. Every value is the solved state's (`PumpResult.npshAvailable`, `npshRequired`, `operatingFlow`, `speed`, `bestEfficiencyPoint`, `shaftPower`; each segment's \|velocity\|); every comparison is a plain inequality on doubles, a value equal to its limit passing. Equal minimum continuous stable and thermal flows name the stable one (the chart's note too). Messages give numbers in SI to 6 significant digits, or as many more (up to 17) as tell the value from a limit it is not equal to (`_digits`), and number pipes from 1. Each check's `source` is narrowed to its own presets (velocity: the user's only), and `_preset_values` refuses a preset source on any other values; a `DesignChecks` with no check present is normalized to None by `ProjectSettings`.
- **Scenarios and goal seek** apply as for any project: the checks are not scenario values, so a scenario's solve checks the case's state with the project's limits, and a goal seek's reported state carries its own checks.
- **Web** (`utils/design-checks.ts`): titles, unit categories, outcome groups, `checkText` (the words from the result's numbers in display units, with as many significant figures, 4 to 10, as tell a value from a limit it is not equal to) and source labels; `DesignChecksSettings.svelte`; `ChecksView.svelte` and the Summary card; `checkOverlays` in `utils/pump-chart.ts` (the limits in display units from the project as solved) with `checkDatasets` and the `checkMarks` plugin in `utils/pump-chart-config.ts`; the export's `designChecksTable`.

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
    ...  # one SystemCurvePoint {flow, head | None, converged, message, reason and its data} per flow
    #     (routers/solve.py _point; SDD §4.10)
```

Both requests take an optional `scenarioId` (body only): without it the router calls `solve_project` / `system_curve` as above; with it, `solve_case` / `system_curve_case` (§5.7), and the response's `scenario` lists every override as applied or ignored (null for the base). `SolveOptions {includeSystemCurve = true, systemCurvePoints = 41}` only adds system curves; options that change results live in `project.settings.solverOptions`. The curves cost a network solve per point for every running pump, so a solve that asks for them can miss the PRD §4.2 solve times a plain solve meets: the web app always sends `includeSystemCurve: false` and fetches the curve of the pump being viewed from `/system-curve`, with the project exactly as solved, one request at a time, cached with that solve (`ProjectStore.loadSystemCurve`, CLAUDE.md D10).

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
- **`ComponentPanel.svelte`** shows the type and id, and the name in a field edited in place (as the project name is; stored on Enter or leaving the field, shared by every case) with the heading visually hidden behind it for structure and focus, its key results from the last solve (`ResultStrip`, below), then `ComponentActions` and two tabs:
  - **Properties**: elevation, the per-type form (`forms/`: reservoir, reference node, assigned-flow node (direction and flow, no default: `AssignedFlowForm` with `AssignedFlowFields`), tee/wye, pump with `PumpCurveEditor`, isolation, check and control valves, equipment (`EquipmentForm` with `EquipmentRatingFields`: Rated by, then the rated pressure drop, flow and fluid density with the *Water at 15 °C* and *This case's fluid* buttons, or the Cv or Kv with the valves' hints from `utils/flow-coefficient.ts`; a kind picked without its values is pending and the stored rating applies until they are entered)), and `PortsEditor` (port sizes, elevations, connections; reservoirs add and remove ports). A port's size is only the default for new piping: a connected port names the pipe size the solver uses, and a port size that differs from it is flagged with an offer to resize the pipe.
  - **Piping**: `ConnectionPanel`.
- **`ComponentActions.svelte`**: Add after, Add before, Add branch and Delete. Add before and Add branch are disabled, with the reason given, when the component has no connection.
- **`AddComponentDialog.svelte`** has three modes:
  - at a free port (after);
  - into one of the component's connections (before: by default the connection the walk arrived by);
  - as a branch (a tee or wye inserted into a connection).

  A kind with no default for a value (`factory.ENTRY_KINDS`: an assigned-flow node's flow, an equipment item's rating) asks for it first (`NewComponentFields`; `factory.missingEntries` gives one error per empty field, shown at that field, when Add is pressed), here, in every mode but branch (equipment is an inline kind, so Add before and Insert offer it and `ws.insert` takes the entered values), and in the first-component and free-port forms. The equipment density buttons read the fluid's properties through `library.fluidProperties` (the POST of D10) and write the exact number returned as user data: built-in water at 288.15 K, or the case fluid. Its error goes on the first keystroke in the field (`NumberField`'s `oninput`), and in those forms a flow of 0 has its note in the field's hint, not on a line of its own: a field stores what was typed when it loses focus, which the press on an Add button below it does, so nothing may change size then, or the button moves before the release and the click is lost (e2e `assigned-flow`). The dialog's hint names the reservoir loss of the direction the connection will have (`edit.addsUpstream`), the entered flow's for an assigned-flow node.
- **`DeleteDialog.svelte`**: when `joinPlan` allows it, offers "Join *A* and *B*" (checked by default); otherwise says which connections go and which ports become free. It notes the delete can be undone.
- **`ResultStrip.svelte`** (results in context, proposal `ui-ux-refinement.md` item 6) shows an element's key results from the last solve of the case shown, so checking an edit needs no trip to the Results pane. The values are the results tables' own cells (`utils/results.ts` `elementSummary`): a connection's flow, velocity and head loss; a pump's status, flow, head and NPSH margin; a valve's state, flow and pressure drop; an equipment item's flow, flow ÷ rated flow (left out for a Cv or Kv) and pressure loss; a tee's or wye's port flows; a boundary's outflow; otherwise the port pressure. Values the solve has none of are left out. Then come the element's flags (two, and how many more are in the trace) and **Trace**, which opens its results and trace without moving the navigator (on narrow screens from the Results pane, where the trace is shown). Nothing is shown before a first solve, or after a failed solve of the current project. After edits the values stay, marked "Out of date: solve again". A solve that did not converge shows no values, only that it did not converge, and an element the solve did not have says so. After a structural edit of a connection since the solve (a reversal, an insertion, a join, pipes added and removed), its values are read on it as it is now (`linkReading`, below): its flow and head loss in its current direction (the other sign after a reversal), each pipe's velocity under the pipe's number now, its pipes' flags renumbered; what cannot be placed is left out, and a note says what reads otherwise and what is left out ("Reversed since the last solve: …", "Its ends changed since the last solve: …", "No velocity from the last solve for pipe 2: …"), with the flags it cannot place counted as in the trace. Each strip is a labelled group, "Last solve: *element*" (not a region: two per panel would add landmarks).
- **`linkReading`** (`utils/results.ts`) reads a solve's values of a connection on it as it is now, for Build's strip and pipe hints and for Compare cases. Pipes are found by identity, never by position: the store records its copy of the project for every edit as the same pipes (`identity.ts` `markProjectCopy`, the mechanism scenario changes follow pipes by), and a pipe's sign comes from an end it shares with the connection it was solved in (every edit keeps a pipe on the same side of each end it keeps), else from the order of the pipes they share, else it is unknown. The connection is the one solved between the same two ports (either way round) while it joins them and holds pipes solved in it and none solved in another connection: ids are given first free, so a new connection can take a solved id and its ends, and only its pipes tell it apart. The flow is known while it is that connection, or holds pipes solved in it and none solved elsewhere (an end moved by an insertion); the head loss only while it is that connection; the largest velocity (Compare) only while its pipes are exactly the pipes solved in it; fittings only while every pipe is in its place and the fittings are as solved. Current results read as solved. Goal seek's Apply records its copy of the project as the same pipes too (`applyToCase`).
- **`ConnectionPanel.svelte`** starts with port buttons. A connected port shows its connection: from and to (positive flow runs this way), its key results from the last solve (`ResultStrip`), Go to *other end*, Insert component, Add branch and Disconnect, then a `PipeSegmentForm` per segment (with Add pipe segment) and `FittingsEditor`. A pipe segment shows the inner diameter and roughness the solver uses: overrides, else the library size entry (roughness is per size). Its velocity at the last solve is the size's hint (a custom pipe's inner diameter's), marked out of date after edits: that pipe's own, found by identity (`solvedPipe`, through `linkReading`), with the sign of the connection's direction now; a pipe added since, or one whose direction is not known, has none. `FittingsEditor` labels an entrance or exit at a reservoir end, and at a reservoir end with neither it says no such loss is applied and offers both. A free port offers to add a component there, plug it, remove it (a reservoir with more than one port) or connect it to a free port elsewhere, for example to close a loop.

**Edit actions** (`Workspace`). Graph operations are pure functions in `utils/edit.ts`. Each action is one undo step, and an edit that would make the project invalid is refused with an error notice. After each one the walk moves to where the change is:

| Action | What it does |
|--------|--------------|
| `addStandalone(kind)` | Adds the first component (or a separate one) and starts the walk there |
| `addAfter(id, port, kind)` | Adds a component at a free port: same elevation, a default connection of one carbon-steel schedule 40 pipe 10 m long, sized to the port. The connection runs with the expected flow (`addsUpstream`, `flowRole`): the new component is upstream when the port receives flow (a pump suction, a valve inlet, an assigned-flow demand), or when the port takes either direction (a reservoir port) and the new component only delivers flow (an assigned-flow supply, whose entered sign sets its role). At a reservoir end it gets the default loss (`withReservoirLosses`): a sharp-edged entrance where it leaves the reservoir, an exit where it arrives. The walk extends to it |
| `insert(connectionId, kind)` (Add before, Insert component) | Splits the connection (pumps, valves, tees and wyes). A connection drawn against the flow is first turned around, piping reversed. The upstream half keeps the connection id and all its piping. The downstream half is new: one 1 m pipe like the last segment, plus any exit fittings. In the arrival connection the new component takes the place before the current one; in any other it comes after |
| `addBranch(connectionId, 'tee' \| 'wye')` | Inserts a tee or wye with its run in line and shows the Piping tab on its free branch port |
| `remove(id, join)` | Deletes the component. **Join** is possible (`joinPlan`) when exactly two ports are connected, or exactly two to something other than a plug, and its other ports are free or plugged. The two connections then become one: it keeps the upstream connection's id, has both sides' pipes in series in flow order, and offsets the fitting indices; plugs on the other ports are removed with their stubs. Without join, its connections are removed and the ports at their other ends become free. If the start component was deleted, the walk restarts at a former neighbor |
| `plug(id, port)` | Closes a free port with a plug on a 1 m stub sized to the port, at the port's elevation |
| `connect(from, to)` | Connects two free ports, oriented with the expected flow (an assigned-flow node's by its entered sign), with the default entrance or exit at a reservoir end |
| `disconnect(connectionId)` | Removes a connection, leaving both ports free |

**From the results.** Clicking a row or flag in the results opens that element's trace and moves the walk to it with `jumpTo`, so Previous and Next keep naming its neighbours (before, the walk restarted at the element, which left Previous unavailable and Next asking which way). For a connection, the walk moves to its `from` component with the connection's piping open. The trace view's **Show in Build** does the same and switches to the Build pane.

**Keyboard.** Outside text fields, Ctrl/⌘+Z undoes, and Ctrl/⌘+Shift+Z or Ctrl/⌘+Y redoes. Ctrl/⌘+Enter solves the case shown from anywhere in the workspace but a dialog (in a field, its Enter stores the value first); the Solve button names the shortcut in its tooltip and `aria-keyshortcuts`.

### 8.2 Schematic Symbols (Later)

**Location:** `apps/web/static/symbols/`

**Symbol Design Guidelines:**

- Simplified, recognizable shapes (not full P&ID complexity)
- Consistent 48x48 viewBox
- `currentColor` stroke for theming
- Connection points match port ids

### 8.3 Export (CLAUDE.md D17)

Design: `docs/proposals/export.md` (§12 records the build). Export is made in the browser from the solve responses, system curves and goal seek the page holds (SDD §3.1.3, §5.1.4): no request, no endpoint, nothing computed but Compare's differences, unavailable while `store.calculating` is set.

**Modules** (`src/lib/utils/export/`):

| Module | What it does |
|---|---|
| `input.ts` | `exportInput(ws, options, now)`: the snapshot taken at the click, from the workspace's public getters: `now` and `utcOffsetMinutes` (−`getTimezoneOffset()`), the build commit, `serverSourceHref()`, the origin, the current project, display units and library names, and each exported case (its status, its response by Compare's rule `caseResponse`, staleness, the project as sent, the case as solved, its system curves), Compare's rows, the finished goal seek and the link's recorded methods version |
| `model.ts` | `buildExport(input)`: the bundle (sheets with their row counts and rows as iterables built on the fly, what is left out, warnings, file name, zip folder, README lines); pure and deterministic: no clock, time zone, environment or build constant is read |
| `context.ts` | Per case `hasValues` (the response converged) and `stale`, which decide everything; the project its names come from (current, or as sent when out of date) and its structure (the case as solved); the ready system curves (`readyCurves`, one rule for the System curves sheet, About and the dialog); captions (the Goal seek sheet's from its own run and staleness), warnings, omissions |
| `tables.ts` | Flags, Nodes, Links, Pipes, Fittings, Pumps, Pump curves, System curves, Valves, Design checks (only when a case has check results, after Flags: one row per result in the screen's order, the value and limits in the row's Unit, the screen's words in the file's units with fractions in % and powers in kW as the app's sentences give them, the server's message and source as reported), Equipment (only when a case has equipment: the results, then Rated by, the rated pressure drop (loss), rated flow and rated fluid density, or the flow coefficient as entered, from `EquipmentResult.rating`), Branches, Branch ports, Boundaries, Boundary ports, Assigned flows, Scenario changes (`changeCategory`: a rated drop is a pressure difference, a rated flow a flow, a rated density a density; a whole rating and a Cv or Kv are exact text, "Cv 120"), Compare cases, Trace |
| `about.ts` | About (the record of the file), `README.txt`, the project links (each encoding cached per project), the Methods (`methodsText`) and Goal seek (`goalSeekReport`) documents; with an Equipment sheet only, About's equipment flow sign, flow ÷ rated flow in the fractions' unit row (and, in an SI file, as a signed ratio with no unit, 1 at the rated flow, not a 0–1 fraction), equipment pressure differences in the ≈ 0 line, and a Cv or Kv as entered in every unit system (a file without equipment has neither the sheet nor these lines) |
| `units.ts` | `SI_BASE_UNITS`, `exportUnit`: the display units, or SI base units with power in W and fractions 0–1 |
| `csv.ts`, `xlsx.ts`, `zip.ts`, `yield.ts` | The writers and the cooperative scheduler |
| `filename.ts`, `download.ts` | Local times from `now` and the offset, file names (§3.5 of the design), `saveBlob` |
| `load.ts` | The memoized `import()` of `components/results/ExportDialog.svelte`, its idle preload when the Export button first renders, and the reload message for a chunk that fails to load (a redeploy or a dropped connection; Chromium keeps a failed module, so only a reload fetches it again) |
| `chart-image.ts` | `chartImageCaption`, `renderChartImage`, `downloadChartImage`: in the chart chunk (`components/results/chart-setup.ts` re-exports it with `pumpChartConfig` from `utils/pump-chart-config.ts`), so the image is drawn from the screen's own configuration |

**Data contract.** One value per cell; every number is the API's double converted by `fromSI`, never rounded (in SI mode the API's own value); a null is an empty cell; booleans are boolean cells; every row carries the API's ids and names, its case (`Case id`, `Case`, with scenarios), `Solved at` (`SolvedState.timestamp`) and `Results` (Current, Out of date, Did not converge, Did not converge, out of date); rows follow the screen tables' own order (a column sort or **Flagged only** on screen does not change the file); words are the app's labels; units are in the headers (`Label [unit]`), or in a `Unit` column where they vary by row. Child tables (Pipes, Fittings, Branch ports, Boundary ports) hold what the screen packs into one cell. Branch K is on the combined-flow velocity (`referenceVelocity`), the Darby fallback included. Compare cases names a connection by its ends now, as the Compare tab does, so a case's connection values are read on it as it is now (`compareValue`, through `linkReading`): solved before a reversal, its flow and head loss have the other sign (About's "Sign: Compare cases" names them); solved before an end moved, what cannot be placed is an empty cell, listed under "Not in this file" and in the dialog. A converged response gives every table; one that did not converge gives About, Flags, Scenario changes and Methods; a failed or not-reached case's earlier response is never used. The Trace is in single-case files only; Compare cases in All-cases files of two or more cases.

**CSV.** RFC 4180: comma, CRLF after every line, a quote only where needed, UTF-8 with a BOM, numbers as `String(n)` (`-0` as `0`), `TRUE`/`FALSE`. A text cell beginning with `= + - @`, TAB or CR gets a leading `'`; numbers and JSON number literals never do. The zip holds one folder, `results {YYYY-MM-DD HHmm}`, with `README.txt` first (how to open the files under a comma-decimal setting), then `about.csv` and the files in sheet order; `methods.txt` and `goal-seek.txt` are UTF-8 with CRLF.

**XLSX** (an ECMA-376 subset written by `xlsx.ts`): content types, relationships, `docProps/core.xml` (title as plain XML text, creator "OpenSolve Pipe", W3CDTF created time; never the link), the workbook with each sheet's `_xlnm._FilterDatabase` and `_xlnm.Print_Titles` (`$1:$3`), minimal styles (bold caption, bold wrapped headers), shared strings, and one worksheet per sheet: the caption in A1, row 2 blank, headers in row 3, panes frozen at A4 (`state="frozen"`), `<sheetFormatPr defaultRowHeight="15"/>`, column widths `clamp(longest of the header and the first 200 rows + 2, 8, 60)`, an autofilter on `A3:` the last cell. Shared strings are XML-escaped, cleared of the characters XML 1.0 forbids, with every underscore that begins a literal `_xHHHH_` written `_x005F_` (overlapping sequences included) and CR written `&#13;`, and cut to 32,767 characters (a longer project link is replaced by a note; `about.csv` holds it whole). No formulas, hyperlinks, number formats, themes or charts.

**ZIP** (`zip.ts`, PKWARE APPNOTE 6.3 subset, for both formats): pako's raw `Deflate` at level 3 in 64 KiB chunks kept as `Blob` parts; UTF-8 names (flag 0x0800); the DOS time of the export's local time; CRC-32 (0xEDB88320); no data descriptors; no ZIP64 (more than 65,535 entries or 4 GiB is refused).

**Building.** On the main thread: the writers yield through a `MessageChannel` every 500 rows or 64 KiB, check the `AbortSignal` at each yield, and report progress per sheet; no Web Worker (the notices plugin does not read worker bundles, §11.1).

**PNG.** The chart drawn again off screen from `pumpChartConfig(…, {forImage: true})`, 800 × 440 CSS px at 2×, on an opaque white composite canvas 1600 px wide with a header (title, project, solve time with its offset, methods version, an out-of-date line) and a footer (`chartNotes`, the other cases, the disclaimer, the app), encoded with `toBlob`; no metadata chunks.

**Bundle.** The export is a lazily loaded chunk of 22.3 KB gzip, preloaded at idle when the Export button first renders, plus 1.1 KB shared with the chart chunk (download and file names). The initial `/p` download grew by 2.7 KB gzip (gzip -9 of `p.html`'s scripts with their static imports and its CSS, 256,834 → 259,521 B after the review fixes: the button and loader, the shared chunk the lazy import splits off, the image button and the Links naming), inside the design's 3 KB; the chart chunk grew by 2.6 KB (the image renderer and the configuration). No runtime dependency was added: `third-party-licenses.txt` lists the same 11 packages. The equipment element (CLAUDE.md D18) grew the initial `/p` download by 7.0 KB gzip (the same measure against `3da03c1`, 268,627 → 275,656 B): 3.2 KB in the shared chunk that holds the bundled `openapi.json` (the Equipment and rating schemas with their descriptions) and the model utilities, 3.0 KB in the `/p` page node (the form, the Add surfaces and the Equipment view), 0.8 KB in a utilities chunk and 27 B of CSS; its design set no budget. The export chunk grew by 0.7 KB (22,638 → 23,320 B gzip -9: the Equipment sheet and About lines). `third-party-licenses.txt` is byte-identical.

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

- **API URL.** The web app calls the API at `PUBLIC_API_URL` (read from `$env/dynamic/public`), default `http://localhost:8000`. The API allows the origins in `CORS_ORIGINS`, default `http://localhost:5173`, and those `CORS_ORIGIN_REGEX` matches (default none; §11.3).
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

**Location:** `apps/api/tests/reference/`. Each case in `cases/*.json` holds `name`, `description`, `source` (exactly where the expected values came from), `project` (API JSON) and `expected`: `fluid` (density, viscosity, optionally `vaporPressure`, null where the property source has none), `flows` per connection, `egl` per `componentId:portId` (every port except those in an isolated section), and optionally `pressures` (gauge static), `atmosphericPressure`, `pumps` (status, operating flow and head, NPSH available / required / margin), `valves` (state), `equipment` (flow, flowRatio, headLoss, pressureLoss, pressureDrop and the rating echoed) and `flags`. One parameterized test (`test_reference_cases.py`) solves every case.

| Source | Use | Generator |
|--------|-----|-----------|
| Closed-form derivations | Single pipes (turbulent, laminar, transitional), fittings, series and parallel pipes, reducers in both directions, plugged branches, pressurized reservoirs and reference nodes, library pipe + built-in water | `derivations.py` (first principles: Darcy–Weisbach with `fluids.friction.Colebrook` — the Lambert-W solution, a different code path from the solver's Clamond — or 64/Re; fitting K from the cited `fluids.fittings` functions; SciPy `brentq`/`fsolve`) |
| Closed-form derivations (M4 differential test) | A PSV open beside a dead-headed pump (a status cycle), a PRV inside a pump loop anchored by a no-flow pipe (the lagged PRV flow); floating sections — a pump loop behind an isolated valve, an active FCV in such a loop, a pump re-opening inside a closed-off loop, a PSV as a loop's only anchor, a PRV in a loop whose level a closed FCV bounds, the system curve of a pump in such a loop (`test_floating_sections.py`, not case files: a floating section has no EGLs); the differential networks themselves (`tests/unit/data/differential`, `test_differential_regressions.py`), checked with the independent laws and, where sections report no heads, with `free_levels.py` (one set of section levels must hold every pump and valve state) | `derivations_status.py`, `test_floating_sections.py`, `free_levels.py` |
| Closed-form derivations (M3) | Pumps (single, reduced speed, beyond the curve, above shutoff, off, series, parallel, a pump and check valve re-opened after a control valve's first solve), isolation valves (Crane defaults, Cv, Kv, K, an isolated section), check valves (cracking pressure, reverse, below cracking, locked open in reverse flow, stop-check locked closed), PRV/PSV/FCV (active, open, closed, an FCV limited by its own open loss, failed open, failed closed), Crane tees and wyes (diverging, converging, dead branch, bullhead fallback, an ideal wye, a reversed lateral, a wye whose split has no self-consistent value at a correlation step: K held at the mean across it, with the held pair of splits checked against the derived 2-cycle), glycols, overrides, NPSH and a siphon | `derivations_pumps.py`, `derivations_valves.py`, `derivations_branches.py`, `derivations_fluids.py`, sharing `element_laws.py` (component laws and status rules written from their definitions) and `line.py` (one-segment lines with fittings) |
| WNTR/EPANET (dev dependency) | Water-only looped networks; networks with a pump, a PRV, a PSV and an FCV | `generate_epanet_cases.py` (WNTR 1.5.0 EpanetSimulator = EPANET 2.2.0) |
| Assigned-flow node | Closed-form (12 cases): a demand and a supply at the end of a dead-end line, a demand below the vapor pressure (water at 70 °C), behind a check valve with a cracking pressure, through an FCV set above it (open, setpoint not met), fed by a fixed-speed pump (NPSH), by a flow-controlled pump at its maximum and at its minimum speed, on a Crane tee's branch between two reservoirs, on an ideal tee fed from both ends, a supply feeding an equal demand with a reservoir only setting the level, and a zero flow in a plug's place (the plug case's values); EPANET (2 cases): a gravity loop with two demands and a supply, a pump feeding a loop whose only outlets are demands, each node a junction whose base demand is its flow (demand-driven, no pattern; each run checks EPANET's reported demand); scenarios through the solver and the API (18 tests): `NO_FIXED_HEAD`, nodes cut off by an isolated valve, a stopped pump or a check valve (not converged, naming the node; a zero flow there is a plug), floating sections with balanced and unbalanced flows, FCVs and flow-controlled pumps feeding a demand (below, at and above the setpoint), zero flow as a plug, system curves with a demand between the pump and a reservoir (41 points against the closed form), before a check valve, and as the pump's only outlet, and the node's results, trace and methods summary | `derivations_assigned_flow.py`, `generate_epanet_cases.py`, `test_assigned_flow_scenarios.py` |
| Round-off floor of the energy stop test (C0b, METHOD_VERSION 1.2.0) | Closed-form (2 cases): a supply into an ideal tee drained to two reservoirs through narrow lines 1,000 and 800 km long, which puts the tee and the supply near 4·10⁹ m of head, where float64 heads are 2⁻²¹ m (4.8·10⁻⁷ m) apart and, whatever order the residual's terms are summed in, no float64 state brings every link within 10⁻⁷ m (guarded: one binade, Sterbenz's lemma), so 1.1.0 cannot converge; and its twin at ordinary heads, where the two tests agree | `derivations_round_off.py` |
| Scenarios (CLAUDE.md D15) | Metamorphic, not case files (`test_scenarios.py`, written from the proposal and the specs without reading `services/`): every reference case and 17 corpus-like networks (3 `default`, 4 `flow_control` and 4 `assigned_flow` fuzz seeds, 5 unit-test data networks, a library-pipe ladder), each with seeded scenarios (every kind of allow-list value it has, a mixed one with ignored overrides and the embedded system curves, one of ignored overrides only, one restating base values). A scenario's `POST /api/v1/solve` and `/system-curve` must equal the solve of the project edited by hand, bit for bit, apart from the timestamp, `computeTime`, the `scenario` record (checked field by field) and the scenario's own methods section and notes; the restating scenario must equal the base; errors must be the hand-edited project's, with the scenario's id; each of the 23 overridable kinds (18 before equipment's five) moves some reference case beyond D6; a project with scenarios but no `scenarioId` gives exactly the plain project's response; orphaned, not-applicable and invalid overrides, malformed scenarios, an unknown id and the order of the checks; the published `x-override-fields` | `scenario_patch.py` (an independent JSON patcher) |
| Goal seek (CLAUDE.md D16) | Closed-form inverses through `POST /api/v1/goal-seek`, not case files (`test_goal_seek.py`, written from the design and the specs without reading `services/`; each derivation computed when the test runs, under a second): a reservoir level for a flow through one pipe, turbulent (G1), laminar (G2) and with entrance and exit losses in water (G3); a pump speed for a duty flow (G4), a discharge pressure (G5) and a head loss (G24), on a linear curve by the affinity laws; a PRV setpoint for a flow (G6); an assigned flow for its port's pressure (G7); two levels for two flows at an ideal tee (G8); a pipe length (G9, log scale); a gate valve's Cv (G10, log; G10b on its Crane default, a middle start); a reference-node pressure for its outflow (G11); the water temperature for an NPSH margin of 0 (G12); an FCV setpoint for its outlet pressure (G13); two pump speeds for two pump flows (G14); a level through a check valve that starts closed (G17, its state change named); a level on a scenario whose override it replaces (G19); a surface pressure for the largest velocity of a two-pipe connection (G20); a flow setpoint for a controlled pump's head (G21); a level for NPSH available (G22); a valve K for its pressure drop (G23, log); for equipment (D18), its rated pressure drop, rated flow and rated fluid density for its flow (G25–G27: 64,383.9768 Pa, 0.0132186579 m³/s, 775.89384 kg/m³), a reservoir level for its static pressure drop and for its pressure loss (G28, G29: two goals a reader of the wrong field misses by more than 20 %), a Cv for its flow on glycol (G30, 81.0723929515) and a Kv for its pressure loss (G31, 84.1004736267), and two values under a scenario's whole rating (G32: both overrides one whole rating holding both values found, each reproducing the state, the marks naming both values); a rating value of the other kind and a whole rating refused. Outcome cases: a target beyond the upper bound (G15, `not_reachable` at the bound in 10 evaluations), a controlled pump's setpoint crossed between its maximum- and minimum-speed states with no steady state between (G16, `unsolved_crossing`), a start that already meets the goal (G18, `met_at_start`). Each met case at the default tolerance (the forward model at the value found within the tolerance plus D6) and at the smallest (the value found within D6 of the inverse, or the forward model within D6 of the target for a length, Cv, K or temperature); every response's rules (§3.2 order, tolerances, caps, bounds, notes) and its `override` applied through `/solve` bit for bit; a case for every variable field and goal quantity the models' Literals list | `derivations_goal_seek.py` |
| Equipment (CLAUDE.md D18) | Closed-form (12 cases, written without reading `services/`, the element's c from the suite's own laws: `element_laws.equipment_coefficient`, `equipment_k`, `equipment_head`, with a Cv's or Kv's c from the suite's CoolProp water at 60 °F): the solve giving back the datasheet (`equipment_rated_point`: Q = Q_r, static drop 50,000 Pa), a line (`equipment_line`), density scaling (a metamorphic pair at 1,100 kg/m³, and 30 % MEG at 5 °C), reverse flow (flagged), ports at different elevations and bores pinning every term of the static-drop identity (`equipment_ports_differ`), a loop of two ideal tees, an assigned demand behind the element, the definition of Kv (`equipment_kv_definition`: Q = Kv m³/h at 1 bar), a Cv on glycol (no vapor pressure), a suction strainer lowering NPSHa (4.0103 m against 5.1868 m without it), and laminar flow in a connected pipe (flagged, Re about 1,190); EPANET (3 cases: a line, a loop and a Cv-rated line, each element a TCV of K = 2gA²c on the inlet pipe's bore between junctions at the port elevations, with the equipment results and port pressures derived from EPANET's flows and heads); system curves through an element on a pump's discharge and as a suction strainer, H_sys = Δz + Σh_line + cQ\|Q\| at every point (`test_system_curves.py`); `network_check` treats the element as always open with residual h_in − h_out − K·v²/2g on the inlet bore, so its `fsolve` self-check covers every case; `test_derivation_checks.py` checks c on every bore, the Cv/Kv constants against fluids within 3.2·10⁻¹⁰, the result definitions, the flag rule and the proposal's printed values (within 2·10⁻⁷) | `derivations_equipment.py`, `generate_epanet_cases.py`, `element_laws.py` |

`closed_form.py` lists every closed-form generator and `build_closed_form_cases.py` writes their files.

Rules: expected values are never computed with solver code (the suite imports only `opensolve_pipe.models`); `test_derivations_current.py` re-runs every derivation and WNTR run and fails if a JSON is stale; `test_derivation_checks.py` checks each derived solution independently (`network_check.py`): energy and mass balance, every component law in its expected state, the expected states against the status rules, and a whole-network `fsolve` that must reproduce each closed-form case. Its energy and head bounds are the larger of their fixed values (10⁻¹¹ m, 10⁻⁹ m) and float64's resolution of the equation, 4ε × its largest head or loss (`network_check.energy_round_off`), which exceeds them only in `round_off_large_heads` (elsewhere at most 6.2·10⁻¹⁴ m).

**EPANET runs:** solver in `swamee_jain` mode; custom fluid with EPANET's water viscosity VISCOS = 1.1·10⁻⁵ ft²/s = 1.02193344·10⁻⁶ m²/s (`types.h`); ideal tees as junctions; D-W roughness passed to WNTR in metres; GPM INP units; accuracy 10⁻⁵, headerror 10⁻⁹ ft, flowchange 10⁻¹² gpm. Known biases, all far inside the criteria: EPANET uses g = 32.2 ft/s² (0.08% in head loss), a rounded minor-loss constant 0.02517 (0.01%), the GPM unit constant (−3.8·10⁻⁷) and float32 results. EPANET multi-point pump curves are piecewise linear, so pump cases use collinear points (PCHIP then coincides). EPANET's PRV/PSV setting is a head without velocity head, ours a static pressure, so the generator iterates setting = p_set/(ρg) + v²/(2g), v from the previous EPANET run in the pipe on the held port, until it changes by < 10⁻¹² m. An active EPANET FCV keeps a 1/CBIG conductance (CBIG = 10⁸, `fcvcoeff`) and settles at q_set + Δh/CBIG in ft and cfs (about 10⁻⁶ relative); the self-checks allow for that leak. The generator also lists the warning flags the pipes' friction regimes call for at the EPANET flows (`TRANSITIONAL_FLOW`) and refuses a pipe whose Reynolds number sits within 1% of a regime bound or outside Swamee–Jain's documented range. An assigned-flow node is a junction at its port's elevation whose base demand is its flow (WNTR writes it in GPM; demand-driven analysis, `demand_model="DDA"`, no pattern), and each run checks that EPANET reports that demand. An equipment item is a TCV between two junctions at its ports' elevations, with the inlet pipe's end-segment diameter, setting K_E = 2gA²c (for a Cv or Kv, the K of that coefficient on the inlet bore, as an isolation valve with it is mapped), minor loss 0, written by WNTR to 11 significant digits; EPANET's TCV loss is 0.999077 of ours (its 0.02517 against 8/(gπ²) = 0.0251933 at our g), which `network_check.EPANET_MODEL.k_scale` models, and its flows come out 4.2–4.5·10⁻⁴ (relative) above ours (4.47·10⁻⁴ on the lines; in the loop 4.33·10⁻⁴ in the main, 4.45·10⁻⁴ in the element's leg and 4.16·10⁻⁴ in the bypass). Heads along a path whose flow a demand fixes are not pinned by reservoirs, so EPANET's g moves them by up to 16.4 mm (0.08 % of the 20 m lost on the way to the pumped network's far demand); like the pump and FCV cases, these cases' self-check against our model uses half the D6 criterion (`test_derivation_checks.py`).

**Pass criteria:** flows within 0.5% of the reference (floor 10⁻⁹ m³/s), EGL within 0.5% or 0.01 m (whichever is looser), and the EGL difference across every connection likewise; pressures within 0.5% or ρg·0.01 m; pump operating values and NPSH within 0.5% or 0.01 m; the expected pump statuses and valve states; ports with no expected EGL (an isolated section) must have no head, and a valve there with no result must be named by an `ISOLATED_SECTION` flag; every expected flag must be present, and warning and invalid flags are exhaustive (each one raised must be expected with its code and element; info flags may appear unlisted); mass balance checked independently from the link results at every component (at an assigned-flow node the net inflow equals its flow), plus the solver's own continuity residual. Every new component type ships with at least one reference case.

**Differential test against EPANET (M4, not part of the suite):** 3,000 random branched and looped networks with every v1 element, solved by both in `swamee_jain` mode and compared with the criteria above; every converged result of ours was also checked independently (energy on every connection, each pump and valve law in its state, continuity at every component, the status rules, and, where sections report no heads, one set of section levels holding every state, `free_levels.py`). The defects it found are fixed and their networks kept as regression tests (`tests/unit/data/differential`, `test_differential_regressions.py`, `test_floating_sections.py`, `derivations_status.py`). The remaining differences are not defects: our documented departures (FCV semantics, a control valve with no fixed head on one side closed); EPANET's 1/CBIG conductance across closed links, which gives zero-flow sections heads and floating loops a pressure level; more than one valid steady state (the head of a zero-flow section, a loop whose level lets a PRV or PSV be either open or closed, an open valve passing reverse flow within EPANET's flow tolerance, EPANET's g = 32.2 ft/s² amplified in a narrow pipe carrying the difference of two large flows); and EPANET answers that break mass balance or its own status rules when its setting iteration does not settle.

### 10.2 Backend Unit Tests

- Element laws: h(Q) and dh/dQ for each element type, including Q = 0 and reverse flow
- Cv/Kv → K conversion against Crane's formula
- Topology validation errors
- Status logic: check valves close on reverse flow; PRV/PSV/FCV switch between active/open/closed correctly
- Standard atmosphere and NPSH available
- Assigned-flow nodes (`test_assigned_flow.py`): the model and its bounds; closed forms of dead ends and a mid-line demand; a zero flow identical to a plug; the topology message; disconnected, floating and dead-end handling in the inner solve, the status rules beside a disconnected section (`disconnected_openings`, `_runaway_status`, `_border_constraints`), flow controls feeding assigned flows (over-controlled, open, at a speed limit, and the not-converged note when the control cannot pass them); the system-curve bounds (`flow_limit`: the limit with assigned flows, a limit below zero and its message, the floor below which no steady state carries a flow and no other start is tried, and the undetermined head at the floor); results, trace (its cut-off note, the floating flag and notes of a section with balanced flows), methods summary and changelog line; over-controlled messages without a disconnected report, and convergence reports that name no assigned-flow node as switching state
- System-curve reasons (`test_system_curve_reasons.py`): a network for each code, derived by hand, with its ids in the message's order, the assigned-flow nodes counted, the cut's numbers (a reverse limit, a floor), the open-valve head on either side of a valve at its switch and the starts tried (cold, warm, after a point), each checked with the whole message; the outer loop's components for a point not converged, and none, as `/solve` reports, where the message names a check valve closed around an assigned flow; points past the time budget not computed; the endpoint's camelCase fields: null and empty on a point with a head, and `openHead`, `openHeadBound`, `startsTried` and two `componentIds` in the message's order as the endpoint sends them
- Scenarios (D15; `test_scenario_models.py`, `test_apply_scenario.py`, `test_scenario_solve.py`, `test_api_scenarios.py`, `test_scenario_cases.py`): the allow-list covers every component class, its paths and holders exist, its Literals and `x-override-fields` state exactly it; structural rejections (a value set twice, a value with a part of it, duplicate ids, a field of another kind, an unknown kind, `pipeIndex` 100, lists over their bounds) never echo a value; every allow-list entry lands at its target and nothing else changes (`fields_set` included); a spec replaces all five keys; orphaned and not-applicable overrides with their messages; invalid values reported together, located, without echo; order independence over seeded shuffles; the metamorphic, base-invariance, equal-to-base and physics checks (a level shift moves every head by Δ and leaves flows unchanged, a temperature gives `fluid_properties` at that temperature, one of two equal parallel pumps off gives the single-pump closed form) against an independent patcher (`scenario_patch.py`); the API's 404, 400, 422 and fluid errors and their order; the body limit with 20 × 30 overrides (`test_api_robustness.py`); a scenario request logs nothing of its body (`test_logging_privacy.py`); the web's shared fixture is current, to round-off (`tests/fixtures/round_off.py`: the solver's last bits differ between CPUs). `tests/differential/test_scenario_check_smoke.py` runs `scenario_check` on the reference cases and 25 seeds of each fuzz profile.
- Goal seek (D16; `test_goal_seek_models.py`, `test_goal_seek_search.py`, `test_goal_seek_service.py`, `test_api_goal_seek.py`, `test_goal_seek_cases.py`): the variable tables are exactly the allow-list's numeric values and every other entry is in `NOT_VARIABLES`, no validator of a holder reads two variable fields, and the published `x-goal-variables`, `x-goal-quantities`, `x-goal-seek-rules` and the variables' `x-ordered-fields` state exactly the tables, validators and tolerance functions; every request rule is rejected without echoing a value (`NaN` and `Infinity` included); the pure search on synthetic evaluators: the map (no trial outside the bounds, the ends and the start exact, a log map whose lower bound is subnormal), the scan order, met, met at the start and a clipped start, several answers, not reachable at a bound, on a plateau (the run of neighbouring tied values) and inside, a sign change the closest-value search finds, a closest-value search cut short, jumps (with a zero-flow label flip beside a real switch), the next bracket after a jump, gaps probed (exactly 4 rounds) and unsolved crossings, a closed bracket with one side within the tolerance, several variables from starts near the bounds and from an unusable start, the diagnosis notes, the backward slope retry, the `sensitive` note's own rounding, the caps, the budget and cancellation, determinism and the reported order; the service: every variable on every target type, not-applicable inputs (400 without ids in messages) and unknown elements (404, all named), each quantity's reader, missing values, the default tolerances with the case density, the bounds pre-check before any solve, the order of the checks, scenarios (`replacedOverride` and the marks), and the metamorphic bit-identity of the override applied to the base, into the scenario and as a new scenario; the endpoint, its errors, the goal-seek admission limit, the time budget and the rate limit; a goal-seek request logs nothing of its body (`test_logging_privacy.py`); the body limit with 4 variables and 4 goals (`test_api_robustness.py`); the web's shared fixture is current, to round-off (`tests/fixtures/round_off.py`). `tests/differential/test_goal_seek_check_smoke.py` runs `goal_seek_check` (§10.4).
- Export's fixtures (D17; `test_export_input.py`, `test_web_export_fixture.py`): the web's export input (`__fixtures__/export-input.json`, real API responses from `tests/fixtures/export_input.py`) holds the cases the design names and is current; the committed workbook the web's writer made from it (`__fixtures__/export-results.xlsx`) is read by openpyxl 3.1.5 (MIT, dev group only) and `zipfile`, independently of the web's code: the parts, content types and zip records; the document properties; every sheet's caption, headers, frozen pane, autofilter, print titles, styles and widths; every number cell equal to a fresh `POST /api/v1/solve` of its case, bit for bit, through the test's own column-to-field map; K·v_ref²/2g equal to each branch path's loss; shared strings decoded as ST_Xstring (`_x0041_`, a CR and a formula-like name back exactly, as text); numbers written as JavaScript's `String(n)`; About's sentences, disclaimer and source link, and its project link decoding to the project exported; the Equipment sheet (`expected_equipment()`, written from the design without reading the web's code) and, only in a file that has it, About's equipment lines
- Equipment (D18; `test_equipment.py`, `test_equipment_cases.py`): the law odd with slope 0 at 0 and refusing a c that is not finite and positive; the builder's one link and c for each kind, a Cv's or Kv's c equal to the closed form and to the valve path on several bores within 2·10⁻¹⁵ relative; `EQUIPMENT_RATING_OUT_OF_RANGE` with the other issues (the conversion's `ZeroDivisionError` and `OverflowError` included) and the smallest coefficients that still build; the published ports and a K refused without quoting it; the element against a gate valve of the same loss; the result's definitions and the static-drop identity; zero flow between equal heads and at a dead end; no result between isolated valves, flows in a floating pump loop; a system curve adding cQ²; each flag and both together; the trace of each kind; the methods section and assumption, the only additions to a summary; in scenarios and goal seek, the whole rating and its values, the holder rule, the error locations inside the union, the value texts, the three goals, a value of the other kind, a value under a scenario's whole rating and two values of one rating with the marks that name them, checked against the independent patcher or hand-edited projects
- Stop test and flag (METHOD_VERSION 1.2.0): the energy tolerance per link against its definition, 1 and 2 units in the last place at 7·10⁸ m accepted and 10⁻⁶ m rejected, 1.1.0's verdicts where the allowance is negligible, and a residual that is not finite exceeding even an infinite tolerance (`test_energy_stop_test.py`); a network near 1.4·10⁹ m of head that converges to Hagen–Poiseuille (`test_gga.py`); the `NOT_CONVERGED` flag naming no location when every residual is within its tolerance, the residual that exceeds when one does, the convergence report's link where the iteration diverged, and the failed-state exit's residuals matching its message (`test_not_converged_flag.py`)

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
  - typed solve errors, and the method version recorded without an undo step;
  - Cancel (PRD §4.2): `cancelSolve()` aborts the request, a late answer or failure is dropped, and the earlier response and error keep their staleness; a superseded solve, a load and clearing the results abort the request in flight; `cancelSystemCurve(pumpId)` aborts that pump's request, drops its late answer and leaves the queue running.
- **API client** (`api/client.test.ts`): requests carry only the project and options, with no credentials or referrer; a solve asks for no system curve; fluid properties are posted with the fluid in the body; no request URL carries a value; error responses map to typed errors (a 429 or 5xx envelope, such as `SERVER_BUSY`, to a network error with the server's message, not to a rejected project); cancellation and the timeout work without `AbortSignal.any` (newer than the build target), and no listener is left on the caller's signal.
- **Model rules** (`utils/model-rules.test.ts`): the component, port, fitting and setpoint rules the app applies are the schema's extensions and bounds, the validator knows every extension keyword, and the API's `DUPLICATE_ID` rule is mirrored.
- **System curves** (`state/project.test.ts`, `PumpChart.svelte.test.ts`, `ResultsViews.svelte.test.ts`): a curve is requested for the project as solved, once per solve, one request at a time; a new solve drops the cache and cancels requests in flight, and a late answer for an older solve is dropped; the chart shows the loading state with Cancel, failures with Try again, cancellations (by the user or by a newer solve) and points without a head (said to have no head, not no solution), and moves the focus from Cancel to the button that computes the curve again and back; the Pumps view shows one pump at a time. Why a point has no head (`utils/system-curve-text.test.ts`, `pump-chart.test.ts`, `PumpChart.svelte.test.ts`): every reason code told from its data with names and in both unit systems, each element's rule by its kind in the project as solved, the API's sentence kept as the row's Details, and the sentence as sent for a null or unknown code, an unknown kind, a missing number or no starts.
- **Assigned-flow nodes** (`utils/assigned-flow.test.ts`, `AssignedFlowForm.svelte.test.ts`, `AssignedFlowResults.svelte.test.ts`, and cases in the factory, encoding, graph, results, flag-text and issue-text tests): no default flow (Add asks for it, the factory refuses a node without one); direction and magnitude stored as one signed SI value that round-trips exactly, with the schema's bounds; a supply set to 0 stays a supply; the node ends a walk like a plug and is no boundary; the Assigned flows view (the flow as entered), its trace and `BELOW_VAPOR_PRESSURE` text; a connection made at a reservoir runs with the entered flow (a supply into it, with the exit; a demand out of it, with the entrance), in `addComponentAtPort`, `connectPorts` and the Add after hint (`edit.test.ts`, `FittingsEditor.svelte.test.ts`); a disconnected node's message with names and units, and links to the components it names.
- **Components** (`*.svelte.test.ts`): Home, the workspace, Share, fluid settings, `NumberField`, valve resistance, the control-valve form, component actions, the panel navigator, the results panel, its views and states, and the pump chart.
- **Results display** (`utils/results.test.ts`, `trace.test.ts`, `flag-text.test.ts`, `pump-chart.test.ts`): tables, flags, traces and the methods text, and chart data in display units; `linkReading` after a value edit, a reversal, an insertion, a join, pipes added and removed, an id used again with other ends and with the solved ends, and an end swap that kept the pipe order; and, in `ResultStrip`, `ResultsAsSolved`, `GoalSeek` and `compare` tests, the strip, the pipe hints, a goal card and Compare cases reading a connection as it is now while the trace, the flags list, a scenario's pipe changes and an out-of-date goal seek name it as solved.
- **Pump chart curve facts** (`utils/pump-chart-facts.test.ts`): the facts in display units, the start tangent down to an extrapolated shutoff head, the notes (the speed range only while shown, why no BEP is marked), and the datasets (on the head axis, the rising stretch under the pump curve, one legend entry for the iso lines, the BEP on the efficiency axis too).
- **Pump chart panels** (`utils/pump-chart-panels.test.ts`, `PumpChart.svelte.test.ts`; proposal `pump-chart.md`): a panel for each curve the API sent (none for duty NPSH values alone), each curve and duty value in display units (US units with hp), a duty outside the efficiency data held, none for an off pump; reading a line between samples and never outside them or across a gap; the first flow where NPSHa falls below NPSHr; the readout of the panels shown; the panels' notes; the stacked axes (head on top, each dataset on its panel's axis) and the image's taller plot; chips that hide a panel, remembered in this browser, and the slider's readout and its value text.
- **Topology issues** (`utils/issue-text.test.ts`): issues told with names; `CONTROLLED_PUMP_CURVE` and `CONTROLLED_PUMP_SETPOINT` with the curve, flow interval or setpoint bound read from the server's message and shown in display units (exponent form, a curve name containing the bound's text; the bound rounded toward zero, `units.formatNumberTowardZero`, so that a setpoint below the value shown is below it), and the server's message when its form differs, the curve is not the pump's, the pump has no flow control or the error is out of date; every other code the builder raises (duplicate ids, unknown components and ports, self-connections, ports connected twice, unknown pipe materials, schedules and sizes, roughness, pipe size and valve resistance out of range) told with names (a size the library lacks never rounded onto one it has: the server's messages for 0.050802 m, 0.914401 m and 1.016002 m, and for 1.0160011 m, whose figures are NPS 40, kept as sent), "Piping A → B, pipe N" and values in display units, lists from the project only while the error is current, the server's message kept as `detail`, a message not in the anchored form or an unknown code kept as sent, piping links, and the library's material names and NPS designations (`issueTextOptions`); in `ResultsPanel.svelte.test.ts` a piping issue whose link opens that connection, and in `GoalSeek.svelte.test.ts` a topology issue, a piping issue with the library's material name whose link, named by the piping, opens that connection, and a not-found line. Goal-seek request lines (`goal-seek.test.ts`, `requestLineText`): a missing port or pipe, a result for another kind of element and the smallest tolerance in names and display units, ids kept for elements the project does not have.
- **Scenarios** (`utils/scenarios.test.ts`, `state/scenarios.test.ts`, `utils/compare.test.ts`, `components/workspace/Scenarios.svelte.test.ts`, `components/workspace/ScenarioCases.svelte.test.ts`, `model-rules.test.ts`): the client mirror on every case of the API-generated fixture (`__fixtures__/scenario-cases.json`); edits in a scenario sorted into changes, shared labels and refusals (a material change is one `spec` change, a temperature-only change a `fluid.temperature` change, typing the base value back clears the change, topology and locked edits are refused, the 30-change bound); pipe changes following their pipes through every graph edit (a distinct length marks each pipe), a removed pipe's changes removed and a deleted connection's kept; the valve-type rule, flow control removed and the fluid made custom; `newId` never re-using an overridden id; results, staleness, system curves and errors per case, Solve all (skipped cases, order, snapshot, a case's own error against a network stop, Cancel, resume), undo and redo switching case; a project without scenarios encoding and solving exactly as before; Compare rows, differences, the "Same" rule and the relative-percent policy; every allow-listed value of every component type editable in a scenario, locked fields read-only and focusable; the manager, the scenario card, the trace block and the chart's other cases; across cases (`ScenarioCases`): Compare's default rows after results were shown, no values for a failed or not-reached case, the notice and the bar's reason with a case's own error, row headers without results and the focus after a column header, a solve of another case cancellable after a switch, the focus during and after Solve all, one live region for its progress, a long case name, the overlay curves after a switch, page state reset on load, group notes describing composite values, and the record shown as solved (units, pipe numbers, Pumps and Links marked); an element's rule placed at the value it rejects (`scenarioProblems`), and a fluid's values in its text.
- **Goal seek** (`utils/goal-seek.test.ts`, `state/goal-seek.test.ts`, `components/workspace/GoalSeek.svelte.test.ts`, `client.test.ts`, `model-rules.test.ts`, and cases in the factory, edit and scenarios tests): the catalogues read from `x-goal-variables` and `x-goal-quantities`; default bounds per row; the tolerance field's minimum; reserved ids and lapses; Run's reasons; the request; words for every stop reason and note code; the trial table and the report; Apply to the case and as a new scenario, checked against the API's trial projects in the shared fixture, with the Compare readers giving the API's goal values; the store's one request at a time (a solve refused during a goal seek and the reverse, `cancelSolve()` cancelling it, curves waiting), staleness on a never-solved project and after undo; the dialog, every Solve control during a goal seek, the trace's entry and the client's `NotFoundError`.
- **Export** (D17; `utils/export/*.test.ts`, `ExportDialog.svelte.test.ts`, `ResultsPanel.svelte.test.ts`, `PumpChart.svelte.test.ts`, `PumpChartChunk.svelte.test.ts`, `PumpsView.svelte.test.ts`, `pump-chart*.test.ts`, `results*.test.ts`): the writers against exact contents (the CSV dialect and its formula guard, JSON number literals unguarded; CRC-32 against `node:zlib`, every entry inflated back, UTF-8 names, local DOS times, the refusals; every XLSX part's exact XML, the frozen pane, `sheetFormatPr`, `_xHHHH_` and CR, the 32,767 cut, sheet names; file names under NFC, whitespace, reserved, bidi and zero-width characters, grapheme cuts, the 147-character cap with the longest path Extract All proposes within 215 characters, and two time zones); the model against oracles over the shared fixture (`__fixtures__/export-input.json`): every SI number cell the API's own double and every display cell `fromSI` of it, through a column-to-field map written in the test; every column of the Flags sheet and every row of the Trace sheet against the API flag and trace; the screen tables' keys, order, fields and categories, with the departures named; K·v²/2g equal to each branch path's loss (the Darby fallback included); Methods, Goal seek and About's disclaimer; the states on a real store with a fake solver (not converged, current or out of date; out of date; names and structure as solved after a reversal and a re-used id; the Case columns; All cases; failed, not reached and not solved cases; the project links, a 1.1.0 link solved under 1.2.0, the link left out, a link longer than a cell; Compare cases equal to `compareCells`, and a connection read on it as it is now after a reversal and an insertion; system-curve reasons equal to the chart table's; boundary ports; bytes independent of `TZ`, `PUBLIC_API_URL` and the build); the committed workbook equal to the writer's bytes and typed cells (`UPDATE_FIXTURES=1` rewrites it); the dialog (choices, defaults by tab, warnings, contents, focus, progress after 300 ms, Cancel, Close and Esc, errors, one build at a time), the button (shown only with something to export, unavailable while calculating, its name, the chunk preloaded once, a failed load's message), the chart's Download image (each unavailable reason, the caption, the chunk's load failure), the other cases on the chart by Compare's rule, and the Links table naming a connection from the project its results belong to (a reversal, a rename, a join, undo and redo).
- **Equipment** (D18; `utils/equipment.test.ts`, `export/equipment.test.ts`, `forms/EquipmentForm.svelte.test.ts`, `results/EquipmentResults.svelte.test.ts`, and cases in the factory, edit, model-rules, schema-bounds, scenarios, goal-seek, compare and issue-text tests; `testing/helpers.ts` `enteredFor(kind)` gives the loops over every kind their entered values): no default rating (one error per empty field, cleared on input); the rating union read from the schema (`ratingSchemaName`); the form's accessible names ("Rated pressure drop (kPa)", never "(g)"), exact SI storage, the density buttons' exact doubles, a Cv stored as entered and a pending kind that keeps the stored rating; the Equipment table, "—" for a coefficient's flow ratio, the view only with equipment, the strip; in a scenario one raw change for the whole rating, a value change within the base's kind and one whole change for a change of kind, never a value with a part of it, and a base switch between Cv and Kv removing `rating.value` changes; goal seek's default bounds, the values the kind holds, the notices naming each value found by its variable; the Equipment sheet against the API's values; and an exhaustiveness test: every numeric field of `x-override-fields` and `x-goal-variables` has a label, a value text with its unit, an export category and a variable spec, a coefficient written with its kind ("Cv 80").
- **Cancel in the workspace** (`Workspace.svelte.test.ts`, `ResultsState.svelte.test.ts`): the header's Cancel during a solve, before Solve, the second click of a double click on either ignored (not a keyboard press), the status line and labels after a cancelled solve, and the focus returning to Solve.

**End-to-end tests: Playwright** (`playwright.config.ts`, `pnpm test:e2e`). Tests are `tests/*.e2e.ts`, with shared helpers in `tests/support.ts`. Selectors use accessible roles and names. They run against the real API and the production build:

- **One worker.** Every test's browser reaches the one API from the same address, and the API solves one request per client address at a time (CLAUDE.md D10), so the suite runs in one Playwright worker; with two, tests that solved at the same moment failed with `SERVER_BUSY` (CI run 39726631693).
- **Its own API entry point.** For the same reason the suite's API is `apps/api/tests/e2e_app.py`: the shipped app with the per-client rate limit on solves and system curves (60 a minute, SDD §7.2) raised. On a fast runner the suite sent more than 60 such requests a minute and its last tests got 429 `RATE_LIMITED` (CI run 40004435327). Everything else is as shipped (`tests/unit/test_e2e_app.py`); the rate limit is tested in `tests/unit`.
- **Servers.** The config starts the API (`uv run uvicorn opensolve_pipe.main:app --port 8010` in `apps/api`, with `CORS_ORIGINS=http://localhost:4183`) and the site (`pnpm build && pnpm preview --port 4183 --strictPort`, with `PUBLIC_API_URL=http://localhost:8010`); the ports are in `tests/servers.ts`. Outside CI it reuses servers already running on those ports. They are not the development ports (API 8000, Vite 5173 and 4173), so a development API, whose CORS allows only the dev app, is never reused.
- **Projects.** Every test runs twice, on Chromium (Playwright's `Desktop Chrome` device):
  - `desktop`: 1280 × 800;
  - `mobile`: 390 × 844, `isMobile`, `hasTouch`, device scale factor 3.
  Narrow-screen checks skip the desktop project.
- **Policy.** Tests run fully parallel with no retries, and `test.only` is forbidden in CI. A trace is kept for each failure, and CI uploads `apps/web/test-results/` (the traces) when the job fails.

The flows in `tests/` at the time of writing:

- **`home`**: the home page renders.
- **`navigator`**: each home-page example opens from its link at its start component, and Next walks on. A shared link opens the project directly, and edits make a new link. A damaged link explains what happened.
- **`pump-chart`**: after a solve of the pump example, its chart has the efficiency, shaft-power and NPSH panels (chips pressed, named in the chart's description) once the system curve is computed; the readout at the duty gives the Pumps table's efficiency and an NPSHa; Home on the slider reads at zero flow and Escape returns to the duty; hiding Shaft power drops its panel and its table, the data table has the efficiency curve and an NPSHa column, the page does not scroll sideways, and after a reload and a solve the panel is still hidden.
- **`pump-chart-facts`**: the pump example with a flow control (minimum speed 50 %): the chart's description names the best efficiency point (70 %) and the speed range from 50 % to 100 % with lines of constant efficiency; the notes give the BEP, the shutoff head and the speed range with the levels 65, 60 and 55 %; the data table has the minimum-speed curve; the Speed range chip hides the range, its note and its tables; no sideways scrolling.
- **`pump-system`**: a pump system is built from a new project through the UI, solved, read, shared and reopened; the reopened link shows the same results. The solve asks for no system curve; showing the pump requests its curve once, for exactly the project solved, and the operating point lies on it; the chart says how the curve was computed and opens the pump's trace, which defines it. The page runs without `AbortSignal.any`, as in the oldest browsers of Vite's default build target (`baseline-widely-available`, e.g. Safari 16.4), since Vite does not polyfill APIs. The test also checks that the page made requests only to the app's and the API's origins. A second test opens the pump-transfer example in US units with an FCV named "Flow limiter" at 15 L/s: the first point without a head is `beyond_limit` with that FCV and 15 L/s, its "Why no head" cell says so in names and gpm, Details opens to the API's sentence, and the page does not scroll sideways.
- **`gravity-branch`**: a gravity-fed branched network with no pump is built through the navigator. Both branches flow, and their flows add up.
- **`topology-error`**: networks the solver cannot solve as connected (no reservoir; an unconnected tee branch) list the API's topology issues with names, each linking back to its components, with the server's message under a closed Details, and solve once fixed.
- **`examples`**: each home-page example, opened from its link and solved unmodified, converges with no flag. Each released schema version's fixture link (`src/lib/utils/__fixtures__/schema-vN.txt`), opened on the test origin, decodes, migrates and converges (the API suite solves the current version's fixture too, `tests/unit/test_released_links.py`).
- **`results`**: a pipe-only network is opened from a link, solved and shared, and the shared link gives the same results. Results tables fit the screen and scroll inside their own box. A connection of several pipes shows each pipe's velocity and Re.
- **`pump-control`**: a pump switched to flow control is solved, its speed and state read in the table and chart, shared and reopened; a flow control completed after an undo is solved; a controlled pump's `CONTROLLED_PUMP_CURVE` issue is told with its names, and in the server's words once the pump has another curve; a setpoint beyond its curve's bound is rejected (`CONTROLLED_PUMP_SETPOINT`) and told with its names and the bound, 80 L/s, derived in the test from SciPy's documented PCHIP end-slope rule.
- **`cancel`**: with the solve and system-curve requests held by `page.route`, Cancel aborts each (`net::ERR_ABORTED`); the app says so, keeps and labels the earlier results (out of date once the project changed), works from the keyboard with the focus returning to Solve (and, for the system curve, going from Cancel to Compute or Try again and back), solves and computes again on request, and the header fits while a solve runs, on both projects' screens and at 320 px and 640 px; a double click or double tap on Solve does not cancel the solve, nor one on Cancel start another, Solve keeping its place and size with Cancel to its left.
- **`assigned-flow`**: reservoir → pipe → a 5 L/s demand built through the UI (Add first asks for the flow), solved and its node pressure read, switched to a supply and solved again, then shared and reopened with the same results; each solve checks EGL(R1) − EGL(AF1) against the head loss shown, and the pressure against ρg·20 m (below for the demand, above for the supply). A flow typed in the first-component and free-port forms without Enter, after the "Enter the flow" error and as 0, is added by the first click on Add.
- **`scenarios`**: on the pump-transfer example, a scenario is created, a value changed in it (Changed, the base value, Reset) and set again, locked values are read-only and focusable, and Switch to base case works; one case and all cases are solved, Compare shows the differences (cards on the phone) and Choose results adds a row, and the pump chart shows the other cases' operating points and an on-demand system curve with Cancel; Solve all is cancelled and resumed with only the missing cases; the link holds the scenarios and opens on the base case; a deleted component's changes no longer apply and undo restores them, switching case; a scenario value a base edit made invalid is reported, rejected by the server at its change and reset to base; a long case name fits Solve and the case bar during Solve all on both screens.
- **`goal-seek`**: on the pump-transfer example, a goal (the discharge valve's flow, 15 L/s) and a variable (the pump's speed) set up from the Results header, met and applied to the base case (the Links table shows the value reached; Undo restores the speed); a target out of reach (the closest at the upper bound, Apply still offered, every trial listed); Cancel in the dialog and in the header with the request held; a run on a scenario applied as a new scenario (never to the base); out of date after an edit and current again after Undo, with Solve now unavailable during a held run; the trace's Use in goal seek; no sideways scroll, and the Result heading focused on phones.
- **`export`**: on the pump-transfer example, the default workbook downloaded with Enter's focus on Download, named by the design's pattern, its parts listed and the suction pressure written as `String(n)` of the intercepted response converted to kPa; the CSV zip in SI base units (`README.txt` first in one `results {time}` folder, a BOM, CRLF, the response's own double); a project with a scenario solved with Solve all and exported from Compare cases as all cases (Compare cases and Case columns, no Trace); the pump chart's PNG (its signature, 1600 px wide, an opaque first pixel, read from its IDAT with `node:zlib`); Export unavailable with its reason during a held solve, an out-of-date workbook that says so (the dialog opening with its warning, Format and the focused Download, in the footer, in view on desktop and phone), and a recorded response marked not converged giving no Nodes sheet, "(not converged)" in its name and no image; on the phone a bottom sheet with Download reachable and focused, the icon-only button 44 px wide and no sideways scroll. From each click to its download no request is made but a GET of the app's own `/_app/immutable/` chunk without a query. Names are ASCII (Chromium saves a non-ASCII name as "download" with `LANG` unset).
- **`results-in-context`**: after a solve of the pump example, the pump's strip in Build shows the flow and head the Pumps table shows, the discharge connection's strip the Links table's velocity, and its pipe's size the same velocity as its hint. An edit marks the strip out of date, and Ctrl+Enter brings it up to date with the new table values. Trace opens the trace, with no sideways scrolling.
- **`pane-split`**: on desktop, after a solve of the pump example, dragging the splitter far left stops where Build keeps 22 rem and widens Results so the Links table, which scrolls sideways at the default split, fits, with no sideways page scrolling; the split survives a reload, ← and → step it, and Enter restores the default and forgets it. A phone has no splitter.
- **`summary-tables`**: after a solve of the gravity example, the Summary's link from the lowest static pressure shows Nodes sorted lowest first with that place in the first row, the link from the highest velocity shows Links sorted highest first with that connection first, and a column heading sorts ascending then descending, with no sideways scrolling.
- **`equipment`**: reservoir → pipe → an equipment item → pipe → reservoir built through the UI, Add after asking for the rating (three errors, then 35 kPa at 10 L/s with *This case's fluid*), solved, its table, strip and trace (sources User) read, shared and reopened with the same table; Add before inserting one into a line, the rating asked for and the first click landing on Add; as the first component, a density typed over a button's note, the first click on Add adding it; two scenarios, a dirty strainer (one change of the rated pressure drop) and another vendor's Cv 80 (one whole-rating change, after the pending-kind warning), solved all, Compare's default rows and the export dialog's Equipment sheet with a row per case.
- **`workspace`**: an edit made just before leaving by an in-app link is in the link that Back returns to. The fluid settings show the API's calculated properties, requested by POST with the fluid in the body; no request URL carries a query string. The workspace fits 320 px without sideways scrolling, and on a phone in landscape the header is one row. Keyboard focus stays on Solve and Undo when they become unavailable. Escape in an edited number field of a dialog reverts the field, not the dialog. Ctrl+Enter solves, and the first row of a results table then starts in the upper 55 % of the screen with the description folded to one line; an empty project offers no Scenarios or Goal seek until it has a component; from 1024 px the header's fluid chip opens the settings on the Fluid field.

**By hand, once before release and whenever the export's writer changes** (design §7.4; record the result here): the fixture workbook opened without a repair prompt in Excel 365 (Windows, macOS, web), Numbers (macOS, iOS), Google Sheets and LibreOffice, with its frozen headers, filter and print titles, and Ctrl+T in Excel selecting from row 3; the CSV zip under a comma-decimal setting (LibreOffice with German (Germany) in Text Import, and Excel with German regional settings: a double-clicked CSV, then `README.txt`'s Data › From Text/CSV steps, its wording corrected to the menus found); Windows' Extract All with names at the length caps; iPhone Safari (the prompt, Files › Downloads, Excel and Numbers, Share › Save Image); Android Chrome; one in-app browser. *Recorded:* 2026-10-26, by the owner on an Android phone: the workbook downloaded and opened in Excel for Android with no repair prompt, its headers frozen and its filters working; the pump chart's Download image saved the PNG. *Not yet recorded:* Excel 365 (Windows, macOS, web), Numbers, Google Sheets and LibreOffice opened by hand; print titles and Ctrl+T; the CSV zip, on Android and under a comma-decimal setting; Windows' Extract All; iPhone Safari; an in-app browser. openpyxl, pandas and LibreOffice (headless) have read the files.

### 10.4 Differential Test and Corpus Comparison

**Location:** `apps/api/tests/differential/`. Command-line tools, run from `apps/api`, outside the reference suite. pytest collects `test_fuzz_smoke.py` and `test_harness.py` (unit checks of these tools). Nothing is written into the repository unless an output directory there is named: each EPANET run works in its own temporary directory, which also holds the scratch files EPANET makes in its working directory.

| Module | What it does |
|--------|--------------|
| `generator.py` | `generate(seed)`: a random branched or looped network meant to have an exact EPANET equivalent for every element: reservoirs, ideal reference nodes, ideal tees and wyes, plugs, custom pipes in 1–3 segments with custom K fittings, pumps with collinear curves from Q = 0, isolation valves, check valves (cracking pressure 0), PRV, PSV and FCV, with random statuses and setpoints. A connection can still end up as the inlet of two active check valves (class `unsupported`). `swamee_jain` mode with EPANET's water viscosity (§10.1). The network depends only on the seed and the profile. Profiles (`--profile`): `default`, the network above, whose draws are frozen (the baseline below, the corpus and the smoke test's pinned classes depend on them); and `flow_control` (proposal `vfd-pump-modes.md` §7.4; documented seeds 10,000–12,999), the default network of the seed plus 0–2 flow-controlled pumps (D11) drawn from a second generator, `Random("flow_control:<seed>")`, after every default draw. An existing pump gets a control, or a new pump with its own collinear curve is inserted in a connection (mostly one left when dead ends are pruned, so it can carry flow), sometimes in series with the previous one and then sometimes with an equal setpoint (no determined state, proposal §4.6), unless that setpoint is at or beyond the new pump's maximum speed × x_mono, which the API rejects (`CONTROLLED_PUMP_SETPOINT`, §5.4): the pump then keeps its own drawn setpoint, decided after the draws so that no other seed's network changes (five seeds changed: 10,443, 10,532, 11,131, 11,253 and 12,108, the only ones of the 3,000 whose networks the API now rejects). Setpoint log-uniform from 0.001 to 1.2 × the curve's largest flow at the maximum speed, minimum speed 0.1–0.9 × the maximum, so that all five control states occur; and `assigned_flow` (§4.8; documented seeds 20,000–22,999), the default network of the seed plus 0–4 assigned-flow nodes drawn from a third generator, `Random("assigned_flow:<seed>")`, after every default draw (the default and `flow_control` projects of all 3,000 seeds of each are byte-identical to those before the profile). A node takes a plug's place at a free tee or wye port, keeping its dead-end connection, or ends a new dead-end connection from a new ideal tee inserted in a connection (mostly one left when dead ends are pruned). One node in four is fed through a flow control in its dead end (an FCV or a flow-controlled pump), facing its flow four times in five, at the control's setpoint two times in five (over-controlled) or 0.3–3 times it. Otherwise the flow is a log-uniform 0.02–2 m/s in the node's narrowest segment: a demand two times in three, a supply one in four, zero one in twelve, and one free node in five balances the previous one. |
| `epanet_model.py` | The project as an EPANET 2.2 model (WNTR INP, run through the toolkit in double precision), with the mapping and PRV/PSV setting iteration of §10.1. An active check valve is merged into its one-segment inlet pipe as an EPANET CV pipe. Elements can be pinned to a state. If EPANET cannot balance at headerror 10⁻⁹ ft and flowchange 10⁻¹² gpm, looser pairs are tried. An element with no exact equivalent raises `UnsupportedError`. EPANET has no speed control, so a flow-controlled pump that is on stands for the state our solver reports (`control_pins`, proposal §7.4): active → the EPANET 2.2 FAQ substitute for a pump of a specific flow (the pump CLOSED, a demand of Q_set at its suction junction and −Q_set at its discharge junction, https://usepa.github.io/EPANET2.2/13_questions.html); max_speed / min_speed → OPEN at SPEED = its maximum / minimum speed, under EPANET's own pump rules; no_flow → CLOSED. One we report without a result runs at its maximum speed (rule A0), or CLOSED when it is held at no flow with both sides closed off (its flags kept). An assigned-flow node is a junction at its port's elevation whose base demand is its flow (positive out of the network; demand-driven analysis); the INP writes it in GPM to 11 significant digits. |
| `checks.py` | The comparison with the D6 criteria: those of §10.1, with a flow also accepted within the flow that 0.01 m of head loss gives in that connection (0.01 m divided by dh/dQ) and within twice the bound of the flow EPANET's closed links leak (1/CBIG conductance). `fuzz --strict` drops the head-equivalent floor. Also the independent checks of a solution: continuity at every component; energy on every connection; each pump and valve law in its state; the status rules, written from EPANET 2.2 in EGL form with the departures of §5.4; and, for sections reported without heads, that one set of heads keeps every state. Closed-off sections are tested at zero flow, floating sections with the relative heads the laws give at the reported flows, and PRV/PSV borders by exact enumeration of their regions. Every pump and valve reported without a result, which the checks above skip, must have none by the rule of SDD §4.10 and §5.4 above (`missing_result_problems`): no flow through it (the continuity tolerance), a port without a head, not both ports in one floating section (one headless section carrying flow, or two that one `UNDETERMINED_PRESSURE` flag names together), not a pump that is on with one side at a head and the other closed off (it is reported dead-headed), and named, for each port without a head, by the flag that says why (`UNDETERMINED_PRESSURE` where that port's section carries flow, `ISOLATED_SECTION` where it carries none). `missing_result_check.py` (below) measures it by deleting results, and the three profiles re-run with this check give the class tables below unchanged, none critical. The checks read only the solver's results, never its internals. A flow-controlled pump's state is its control state; its rules (`rule_flow_pump`: A1/A2, X1/X2, N1/N2, C1) are written from the state machine of proposal §4.5 alone, A2 on F(s_lo, Q_set) with s_lo = max(s_min, Q_set/x_mono) at most s_max (`element_laws.stable_min_speed`, §5.4) (a flow within 10⁻⁹ relative of Q_set is Q_set in X1 and N1, so a limit state carrying its setpoint, as in series with another flow control holding the same flow, is not valid), its law in each state from §4.4 (active Q = Q_set, a fixed flow; at a speed limit the fixed-speed pump at that speed), the band of A1/A2 bounds an active one beside a headless section, and `control_problems` checks the reported control: the status of each state, the speed (s_max at max_speed and no_flow, s_min at min_speed; active within [s_lo, s_max], where F(·, Q_set) rises and has one root, allowing 10⁻¹² relative rounding below s_lo, with \|s²·H₀(Q_set/s) − H\| ≤ Htol), and `PUMP_SETPOINT_NOT_MET` and `setpointAchieved` as §2.5 defines them. An active pump's speed is compared with the one EPANET's head rise H_e implies (closed form for the generator's linear curves, s = [bQ + √(b²Q² + 4aH)]/(2a), proposal §4.7) within 0.5 % (owner's answer Q6), and the head our speed implies at Q_set with H_e by the D6 head criterion (0.5 % or 0.01 m, whichever is looser), as every head loss here, not by Q6's 0.01 m alone, which is the reference suite's test against a derived head. H_e carries EPANET's constants: at the flows the setpoint fixes, EPANET's friction losses are 8.1·10⁻⁴ lower than ours (g = 32.2 ft/s² = 9.81456 m/s² against 9.80665, `hydcoeffs.c`) and its minor losses 9.2·10⁻⁴ lower (the 0.02517 factor, `input1.c`), so H_e differs from our head rise by 8.1–9.2·10⁻⁴ of those losses whatever H is, and a flat 0.01 m fails once they pass 11–12 m. The FAQ substitute's closed pump also leaks Δh/CBIG past Q_set, which adds to that where Q_set is small (3.9·10⁻⁴ of Q_set at seed 10,353, where H_e differs by 1.9·10⁻³ of the 32.1 m of loss on the pump's path). In the `flow_control` run below, 36 of the 163 comparisons exceed 0.01 m, up to 0.077 m (seed 11,975, H_e = 37.3 m) and 0.069 m (10,709, H_e = 44.5 m); the largest relative difference is 3.65·10⁻³ (12,846: 0.0069 m on H_e = 1.90 m), inside the D6 tolerance by a factor of 1.45. Criticality does not rest on this comparison: the self-check's `control_problems` holds our speed to Htol against our own head rise. Assigned-flow nodes: continuity takes their flows as demands. `assigned_flow_expectations` finds, from the project alone, the networks with no steady state: a part no fixed head reaches whose net assigned flow exceeds what the one-way elements across its boundary can pass (check valves, PRV, PSV and running pumps nothing backwards, an active FCV at most its setpoint; `disconnected` when only statically closed elements cross, else `no_flow_path`), found from a minimum cut (max-flow min-cut theorem, Ford and Fulkerson 1956) and checked on its own with a margin of Qtol per element; or a part, with no active PRV or PSV, whose only crossing elements are flow controls that continuity forces to their setpoints (`over_controlled`). `undetermined_heads`: every reported head reaches a fixed head through elements that tie heads in their reported state, or is a port an active PRV/PSV holds (every profile; no failure in the 5,996 converged default and `flow_control` networks). `assigned_flow_problems`: boundary result (outflow = its connection's flow, −flow within the continuity tolerance), HGL, static and absolute pressure, and `BELOW_VAPOR_PRESSURE` exactly when the absolute pressure is below the vapor pressure, or ≤ 0 Pa without one. |
| `missing_result_check.py` | The deletion scan of `missing_result_problems`, which alone stands between a result the solver drops and a seed the fuzz passes: for every converged network of a profile's seeds, the result as solved must not be reported, and each pump and valve result deleted in turn must be (`no result for <id>`, since the solver gave a result there). It counts the deletions by kind and by the element's ports without a head and exits with status 1 when a deletion is not reported or a result as solved is. Over the three profiles' 9,000 seeds: 7,778 converged networks (3,000, 2,996 and 1,782), none reported as solved, and 33,975 deletions (11,921, 14,265 and 7,789), every one reported: pumps with no port without a head 8,339, one 601, two 437; valves with none 23,862, two 736 (no valve result here has exactly one); 35–43 s per profile. `test_missing_result_check_smoke.py` runs 25 seeds of each profile, which reach all five of those places, and requires a check that reports nothing, or that reports a result as solved, to fail the scan. |
| `state_search.py` | For a network our solver did not converge on: every combination of pinned pump and valve states, the first 729 (`--limit` from the command line), solved and kept if it passes the checks. Like `fuzz`, the command line also counts the states that give every port a head. A flow-controlled pump is pinned over its four states (proposal §7.4): max_speed and min_speed as the fixed-speed pump at that speed, no_flow as the pump off, and active with its speed range widened to (0.001, 1], the original range enforced by the check of rules A1/A2. `control_search` (`--controls`) pins only the flow-controlled pumps, every other element following the solver's rules. Valid solutions are distinct when a flow differs, or an EGL at a port of a connection with flow, by more than D6. A distinct solution only puts more of the network at rest than another when it has flow in fewer connections, all of which the other has flow in, and agrees with it there (flows and EGLs, by D6): a pump held closed with valves closed around it at heads that keep them closed (D9), the rest unchanged. Two distinct solutions of which neither does that differ in flowing state and are *multiple*: they flow in the same connections in other amounts, or each in a connection the other has at rest, or one in a subset of the other's connections with other flows or heads there. A valid state also has every reported head determined and the assigned-flow nodes' results right. |
| `fuzz.py` | The driver: generates (`--profile`), solves with both, compares, checks and classifies each seed (classes below). With flow-controlled pumps every EPANET run stands for our states, the control checks join the self-check, and every converged network is searched over its controlled pumps' states (`control_search` in the record): multiple valid solutions are written to `findings/control_multiple_states`, alternatives that only put more at rest to `findings/control_rest_alternatives`; the class is not changed. With assigned-flow nodes, a network the project shows to have no steady state must not converge. It is classed `no_steady_state` when the message states an expected reason (names a node of the part; for over-control, the controls and "undetermined"), else `no_steady_state_other_message`; EPANET's run is recorded only and no state search is made. A project with a zero assigned flow is solved again with plugs in those places and must match bit for bit, converged or not (a difference fails the self-check). A non-default record names its `profile`. |
| `classes.py` | The class names and `is_critical`. |
| `stats.py` | A summary of a run: counts per class, and the largest \|Δ\|/tolerance per metric and element kind over the agreeing networks (with flow-controlled pumps: `speed` and `speed_head` of kind `flow_pump`, their final states, and the control-search counts; with assigned-flow nodes: the nodes by sign, the networks without a steady state by reason and class, and those not converged with no expected reason). |
| `networks.py` | Fixed corpus networks: Crane-tee ladders, and a step-hold probe wye (45°, β² = 0.25) scanned over six R3 levels across the q = 0.4 step. The reference case `wye_crane_step_hold` is a different network; it is in the corpus separately as `ref_wye_crane_step_hold`. |
| `corpus.py` | Solves every project of the corpus with system curves and dumps each `SolvedState` to `<name>.json`. The corpus is the reference-case projects and the unit-test data networks (41-point curves), six ladders, the step-hold probe wye at six levels, and fuzz seeds 0–2,999 (11-point curves): 3,092 projects before speed control; since then the flow-controlled reference cases and the `flow_control` profile's seeds 10,000–10,999 (`fuzzfc_<seed>`, 11-point curves), 4,120; and since then the 14 assigned-flow reference cases and the `assigned_flow` profile's seeds 20,000–20,999 (`fuzzaf_<seed>`, 11-point curves), 5,134; and since then the two round-off reference cases (C0b), 5,136; and since then the 15 equipment reference cases (D18), 5,151 in all. |
| `compare.py` | Compares two dumps exactly (JSON equality, `timestamp` ignored). It reports identical and different projects, projects missing from either side, and for each difference the number of numeric differences and the largest relative one. Exit status 1 when a project differs. `--ignore PATH` (repeatable) leaves out the values at a path, whatever they are: dict keys and list indices from the root separated by `.`, each segment an `fnmatch` pattern (`*` is any one key or index), the whole path at its depth, a key present on one side only included. `--ignore-null PATH` (repeatable, the same paths) leaves out a value only where it is null or absent on both sides and compares it as usual elsewhere, so a new field that must be null in results that do not use it is checked to be null. `--ignore-empty PATH` (repeatable, the same paths, D18) leaves out a value only where it is `{}`, `[]` or absent on both sides (null is not empty), so a new map that must be empty in projects that do not use it is checked to be empty. Each path's count of values left out, and in how many projects, is printed after the totals, so an ignore broader than intended shows. The within-tolerance mode counts `equipmentResults` flows as element flows and judges `pressureLoss` as a pressure. |
| `scenario_check.py` | The scenario check over the corpus (CLAUDE.md D15): for every corpus project a scenario drawn with `Random("scenario:<name>")` (1–6 overrides over the (target, field) pairs the project has, values near the base ones, one outside its bounds in about one project in ten, plus 0–2 orphaned or not-applicable overrides), checked against an independent JSON patcher (`tests/unit/scenario_patch.py`): (a) the effective project and the override states equal the patcher's, `fields_set` included, and a value the models reject is rejected by both; (b) the scenario's solve equals `annotate` of the hand-edited project's solve bit for bit, errors compared as issue lists or messages; (c) the base solve of the project with its scenario equals the plain project's; (d) every 20th project with a running pump (`--curve-every`) has the same system-curve points as the hand-edited and the plain project. Exit status 1 on any difference; `--out` writes every record. `test_scenario_check_smoke.py` runs the reference cases and 25 seeds of each fuzz profile. On equipment (D18) the patcher holds the five rating fields with the holder rule, a not-applicable override is a value of the other rating kind, and `OUT_OF_BOUNDS` has a bad value for each (a whole rating of kind K, among them). |
| `goal_seek_check.py` | The goal-seek check over the corpus (CLAUDE.md D16, proposal `goal-seek.md` §7.4), written against the published schema and talking to the app only through HTTP (in process): for every project and n = 1 to 4, a request drawn with `Random("goalseek:<name>:<n>")` (a field kind uniformly among the numeric allow-list values the case has, then a target; bounds around the case's value, log-uniform widths for log variables, a clipped start in about one draw in ten; goals among the case's results that have values; targets the goal values at a seeded interior point (60 %), near the start (15 %), pushed far beyond (20 %) or the case's own (5 %), kept only if the case misses a target by more than 10 tolerances; one goal in five with a user tolerance), on a seeded scenario on every 10th project, run twice. Checks: (a) only documented statuses; (b) the response matches its schema; (c) the two runs are identical but for `seconds`, `computeTime` and `timestamp` (unless stopped by time); (d) the variables' overrides, applied with the independent patcher (`tests/unit/scenario_patch.py`, into the base or the scenario) and solved through `/solve`, give `solvedState` bit for bit outside the annotation; (e) the caps and the time budget; (f) the claims agree with the evaluations listed (goal values, met and success, default tolerances, the reported order, stop reasons, every note's data); (g) bounds, starts and the override's target; (h) spot checks of evaluations solved again through `/solve`. Exit status 1 on any violation; `--repro` writes each violating draw. It records the stop reasons and met rates per n and target kind, evaluation counts and the rates of jumps, unsolved crossings, time-budget stops and unusable evaluations. `test_goal_seek_check_smoke.py` runs the reference cases and 10 seeds of each fuzz profile, 17 falsified responses that must be caught, a pinned jump and unsolved crossing, values tied at both bounds (no plateau), and a time-budget stop with a `not_computed` evaluation that must pass. Which values a component offers comes from the published holder schemas (`holds()`: a pump's `control.setpoint` only with control, an equipment item's rating values only of its kind); under a whole value the scenario overrides (a fluid, a rating), check (g) expects that whole value from the reported evaluation's case with every variable written, and the smoke test catches an override that loses a value found. |
| `equipment_check.py` | The equipment check over the corpus (CLAUDE.md D18, proposal `equipment-pressure-drop.md` §7.4, in place of a fuzz profile): for every project with an active isolation valve, solve it, then replace every such valve that has a result by an equipment item on the same ports and elevations, and solve again. A valve rated by a Cv or Kv becomes an item rated by the same Cv or Kv (the coefficient path end to end); any other valve becomes a rated point with ρ_r drawn uniform in 800–1,200 kg/m³ (per valve, in component order, from one `Random("equipment:<name>")` per project), Q_r = A_ref × 1 m/s and ΔP_r = ρ_r K_open (1 m/s)²/2, from the valve's `kOpen` and `referenceDiameter`, so c = K_open/(2gA_ref²) up to rounding (one whose ΔP_r would pass 10⁸ Pa is kept). Checks (D13): (a) the same convergence; (b) every flow, EGL and static pressure within D6, or listed apart when different only at zero flow; (c) each item's flow and head loss within D6 of its valve's; (d) in the item's own result `pressureLoss` = ρg·`headLoss` and `pressureDrop` equal to the static-drop identity, to round-off (a port in a floating section by `head_bound`). It also records, with no threshold, the largest flow and head differences and how many items carry flow or lose more than 0.01 m: in dead legs and at tiny losses a wrong law stays within D6, and these numbers show it (the smoke test, `test_equipment_check_smoke.py`, proves they catch a c 1.21 times too large). Exit status 1 on any difference. |

**Commands** (from `apps/api`; times are wall-clock on 4 CPUs with 3 workers):

```bash
uv run python -m tests.differential.fuzz 0 3000 --workers 3 --out /tmp/fuzz   # about 3 min
uv run python -m tests.differential.stats /tmp/fuzz
uv run python -m tests.differential.corpus /tmp/corpus --workers 3             # about 4 min
uv run python -m tests.differential.compare /tmp/corpus-before /tmp/corpus
uv run python -m tests.differential.state_search SEED     # valid states of one network
uv run python -m tests.differential.generator SEED        # one network's project JSON
uv run python -m tests.differential.fuzz 10000 13000 --workers 3 --profile flow_control --out /tmp/fuzzfc  # 10 min
uv run python -m tests.differential.state_search SEED --profile flow_control --controls
uv run python -m tests.differential.generator SEED --profile flow_control
uv run python -m tests.differential.fuzz 20000 23000 --workers 3 --profile assigned_flow --out /tmp/fuzzaf  # about 12 min
uv run python -m tests.differential.state_search SEED --profile assigned_flow
uv run python -m tests.differential.missing_result_check 0 3000 --workers 3   # under 1 min; likewise
#   10000 13000 --profile flow_control and 20000 23000 --profile assigned_flow
uv run python -m tests.differential.scenario_check --workers 4            # scenarios, about 5 min
uv run python -m tests.differential.goal_seek_check --workers 4 --sample 200  # goal seek, about 6 min
uv run python -m tests.differential.equipment_check --workers 4           # equipment (D18)
```

`fuzz` writes `results/<seed>.json` (one record per seed) and `findings/<class>/<seed>.json` (a reproducer: the project JSON, both solutions and the diagnosis inputs) to `--out`, a new temporary directory by default. It prints that directory and the critical seeds, and exits with status 1 if there are any. `--strict` compares flows to 0.5% or 10⁻⁷ m³/s without the head-equivalent floor (0.01 m divided by dh/dQ), which accepts almost any flow in a short, large pipe. `corpus` writes each dump to a `.tmp` file and renames it into place, so an interrupted run leaves no partial dump. It refuses an output directory that already holds dumps, because they may come from another commit; `--resume` continues an interrupted run there and reuses every existing file as it is, whatever commit wrote it. `--only PREFIX` selects projects by name, and `--dry-run` prints the solver package and corpus tree it would use. `compare` reports a file it cannot read or parse as unreadable, and counts it as different. The smoke test classifies seeds 0–49 with the real EPANET run, and the `flow_control` seeds 10,000–10,024 (which must also reach all five control states, with no multiple valid solutions over their controlled pumps' states) and 11,738, 12,703 and 12,773, whose statuses cycle (`CYCLE_CLASSES`, below), and the `assigned_flow` seeds 20,000–20,024 with 20,025 and 20,035 (`ASSIGNED_FLOW_CLASSES`, `ASSIGNED_FLOW_EXTRA`), which together reach every expected reason, an agreeing demand and supply, and a zero flow; with `test_harness.py` it adds about 30 s to `uv run pytest`.

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
| `no_steady_state` | The project alone shows no steady state (assigned flows with no flow pattern, or forcing flow controls to their setpoints); ours did not converge and its message states that reason. |
| `no_steady_state_other_message` | As above, but the message states another reason; to be reviewed. |
| `ours_exception`, `gen_error`, `harness_error` | Our solver, the generator or the harness raised. A harness error is, for example, EPANET failing in a re-run with pins, or the EPANET library failing to load. Its record keeps what was computed before, `self_check` included. |

Every converged result of ours is also checked before EPANET runs. A failure is stored in the record's `self_check`, which a `harness_error` record keeps, and in `findings/self_check_failed`. That is the same check that makes a class `a_ours_invalid`, so a seed is **critical** (`classes.is_critical`) when its `self_check` is non-empty or its class is `a_ours_invalid`: a converged result of ours that fails the independent checks. For each seed in its range, the smoke test asserts that our solver converged, that EPANET ran, that the seed is not critical, and that its class is the one pinned in the test. The classes are deterministic (the same under PYTHONHASHSEED 0 and 12345, in both profiles), so a changed class is a change in our solver's or EPANET's behaviour, to be reviewed before the pinned class is updated. With flow-controlled pumps the self-check includes their rules, laws and reported control (`checks.py` above). EPANET stands for the state we report for each, so a wrong state of ours shows in the self-check, not as a state difference, and EPANET's solution under that state must also keep our rules (else class `review`); the control search (`state_search.py` above) pins the controlled pumps over their states and reports whether more than one combination gives a valid solution (`multiple`); it does not compare those solutions with the state we report, which the self-check covers.

**Seeds 0–2,999** (3,000 networks, 40,736 components, 43,600 connections; METHOD_VERSION 1.2.0, and 1.3.0 record for record, D18): pass 1,859; documented 534; state_only_zero_flow 262; pass_ep_unbalanced 127; b_stagnant_heads 81; epanet_unbalanced 42; epanet_failed 29; ours_verified_by_pinned_epanet 27; unsupported 13; b_multiple_steady_states 10; d_no_converged_reference 9; review 3; state_only 2; harness_error 1; e_epanet_invalid 1. None is critical. The largest \|Δ\|/tolerance in the agreeing networks is 0.817 (EGL at a pump port). The `flow_control` profile and the speed-control solver left every one of these records unchanged (re-run after both: the same classes, records and diagnoses), and so did the owner's decisions of 2026-10-23 (§12: re-run, the same classes) and the assigned-flow node (D12: re-run, the same class table, none critical, largest \|Δ\|/tolerance 0.817). C0b's energy stop test (1.2.0) moved two records (1,446 documented → pass, 2,522 b_stagnant_heads → pass; 1.1.0: pass 1,857, documented 535, b_stagnant_heads 82), with the same largest \|Δ\|/tolerance (below).

**`flow_control` seeds 10,000–12,999** (3,000 networks, 43,922 components, 46,724 connections; 2,710 with a flow-controlled pump; METHOD_VERSION 1.2.0, and 1.3.0 record for record, D18): pass 1,765; documented 464; state_only_zero_flow 302; pass_ep_unbalanced 148; epanet_unbalanced 84; b_stagnant_heads 83; epanet_failed 66; ours_verified_by_pinned_epanet 22; d_no_converged_reference 20; b_multiple_steady_states 17; review 11; unsupported 11; ours_not_converged 4; e_epanet_invalid 2; state_only 1. None is critical. Our final states of the controlled pumps: max_speed 1,952 (most at zero flow, dead-ended, rule A0), min_speed 741, isolated 508, no_flow 444, active 183, off 167. (At 1.1.0, before C0b moved ten records between classes, below: pass 1,764; documented 466; state_only_zero_flow 300; pass_ep_unbalanced 149; b_stagnant_heads 86; epanet_unbalanced 83; ours_verified_by_pinned_epanet 21; review 10; the controlled pumps max_speed 1,956, isolated 505, no_flow 442, off 168. The rest of this paragraph was measured at 1.1.0.) (Re-run after `CONTROLLED_PUMP_SETPOINT`: the classes, the comparisons and the control search are those above; of the five seeds whose generated network changed, each keeps its class, and only 11,131's PU4, which kept its own setpoint instead of a copy beyond its bound, changed state, from max_speed (1,957 before) to min_speed (740 before).) 163 active pumps were compared with EPANET's FAQ substitute: largest \|Δ\|/tolerance 0.339 for the speed and 0.691 for the head it implies (seed 12,846); over all comparisons, 0.979 (EGL at a controlled pump's port). The control search covered 2,587 converged networks: seven (10,927; 11,037; 11,285; 11,307; 12,159; 12,419; 12,630) have distinct valid solutions that differ in flowing state, and 32 have alternatives that only put more of the network at rest. In each of the seven a controlled pump is at a speed limit in one solution (running, or at zero flow dead-ended at its shutoff head) and closed in the other, with valves around it in other states and other flows or heads where both solutions have flow. That is the multiplicity of v1's status rules rather than of the control: with those pumps fixed at that speed and searched over running and closed, the same search finds the same solutions, also multiple. (Six of the seven have flow in a subset of the other solution's connections; a count that compared only which connections carry flow, not their flows, filed them with the alternatives at rest.) The 4 not converged hold two flow controls in series with equal setpoints (no determined state, proposal §4.6). In three networks (11,738, 12,703, 12,773) outer iterations change several statuses at once and the cycle closes on a step that changes a single status; they converge in the single-change mode (§5.4), 12,703 after going back to a state with a change not yet taken (from PRV4 open and PU5 at maximum speed the rules move PU5 to active and PRV4 to closed together, while the valid state changes PU5 alone), to the state the brute-force search finds valid in 11,738 and 12,703 (12,773's state, which passes the checks and agrees with EPANET under the documented departures, lies beyond the first 729 of its 15,552 combinations), and are pinned in the smoke test (`CYCLE_CLASSES`). The same seeds in the default profile (the base networks without the added pumps, run for this comparison: pass 1,869; documented 485; state_only_zero_flow 265; pass_ep_unbalanced 109; b_stagnant_heads 75; epanet_failed 63; epanet_unbalanced 62; ours_verified_by_pinned_epanet 28; d_no_converged_reference 15; unsupported 11; b_multiple_steady_states 10; review 4; e_epanet_invalid 2; harness_error 1; state_only 1; none critical, none not converged): every one of the 290 networks that got no controlled pump has the same class in both profiles. Of the others, apart from the 4 not converged above, the classes that differ from the base network's are EPANET's (unbalanced, failed with runH error 110, or a pinned solution that breaks a status rule, `review`, 8) or v1's documented zero-flow and FCV departures, which a pump's changed flows bring into play: in 107 of the 165 new `state_only_zero_flow` (93 of them with no other difference) a controlled pump dead-ended at maximum speed (rule A0, running at zero flow) is one that EPANET reports closed, as it does a fixed pump against a plug; the 14 new `b_multiple_steady_states` differ in valves and check valves, with the controlled pumps in the same states.

**`assigned_flow` seeds 20,000–22,999** (3,000 networks, 51,009 components, 53,929 connections; 5,518 assigned-flow nodes in 2,775 networks: 3,639 demands, 1,590 supplies, 289 zero; METHOD_VERSION 1.2.0, and 1.3.0 record for record, D18): no_steady_state 1,161; pass 1,101; documented 315; b_stagnant_heads 217; state_only_zero_flow 74; ours_not_converged 32; epanet_unbalanced 17; pass_ep_unbalanced 17; b_multiple_steady_states 13; epanet_failed 11; no_steady_state_other_message 9; both_unconverged 8; e_epanet_invalid 8; d_no_converged_reference 6; ours_verified_by_pinned_epanet 6; unsupported 4; review 1. None is critical. (At 1.1.0: no_steady_state 1,160, no_steady_state_other_message 10; C0b moved 22,410, below.) The same seeds in the default profile (the base networks without the nodes, run for this comparison: pass 1,892; documented 511; state_only_zero_flow 238; b_stagnant_heads 113; pass_ep_unbalanced 98; epanet_unbalanced 46; epanet_failed 35; ours_verified_by_pinned_epanet 21; d_no_converged_reference 16; b_multiple_steady_states 13; unsupported 10; e_epanet_invalid 7; none critical, none not converged): every one of the 225 networks that got no assigned-flow node has the same class in both profiles. The classes, explained:
- **No steady state by the project (1,170: disconnected 153, no_flow_path 789, over_controlled 363; a network can have several).** Our solver converges on none. 1,161 messages state an expected reason (`no_steady_state`). The other 9 (`no_steady_state_other_message`) state another reason that also holds in the statuses the solve ends in: another node of the network disconnected, or fed through an FCV it cannot pass (20,029; 20,075; 20,223; 20,733; 20,787; 21,885; 22,448; 22,647; 22,809). 22,410 was the tenth at 1.1.0; at 1.2.0 its solve takes another path and its message states the expected over-control (C0b, below). In the over-controlled ones, the expected reason (a node fed only by a control at its setpoint, whatever the heads) is not the one reported. Three seeds (21,845, 22,316, 22,647) reported only a failed inner solve (the open state's heads, up to 4·10⁹ m, are beyond float64's resolution at the 10⁻⁷ m energy tolerance), and two (21,598, 22,809) only the outer-iteration limit, before the integrator's change: a failed inner solve's message now names a disconnected part, and every not-converged message starts with the reason when one flow control alone feeds assigned flows that it never passes or that equal its setpoint (§5.4). EPANET is no reference for these networks: it "balances" most of them with warnings (4: 419, 5: 337, 6: 157; none: 73), is unbalanced in 153, and fails with runH error 110 in 26 (5 unsupported).
- **Not converged with no expected reason (48: ours_not_converged 32, both_unconverged 8, epanet_failed 7, unsupported 1).** Each message names an assigned-flow node and why no steady state carries it in the statuses the solve ends in: a part cut off by a PRV, PSV, check valve or pump that its rule closes at the heads the rest of the network fixes (a PSV whose inlet would fall below its setting, a PRV whose outlet side needs more than its setting, a pump facing more than its shutoff head), or an FCV or pump it can only reach through against its rule. These reasons depend on heads, which the project-alone check cannot see. The state search finds no valid fully determined state in any of the 40 it searches: exhaustively in 28 (at most 729 combinations), in the first 729 of the other 12. The other 8 stop before the search. 28 of the 48 are `pass` in the default profile (none of its networks fails to converge): the added nodes make them infeasible.
- **Agreeing (`pass` 1,101, `documented` 315, `pass_ep_unbalanced` 17, `ours_verified_by_pinned_epanet` 6).** The largest \|Δ\|/tolerance is 0.998 (EGL at a check-valve port, seed 21,990); at assigned-flow ports 0.995 (EGL, 20,591) and 0.047 (flow). Eight converged networks hold balanced assigned flows in a floating section flagged `UNDETERMINED_PRESSURE`, and all pass. The 278 networks with a zero assigned flow (195 converged) solve identically with plugs in their places.
- **`b_stagnant_heads` (217; 180 not in that class in the default profile).** Flows agree and both solutions pass the checks; EPANET's 1/CBIG conductance across closed links carries part of an assigned flow. In 104 of the 180, a demand drawn through the generator's narrowest pipes needs head losses of 10³ to 10⁸ m (physically meaningless, flagged `BELOW_VAPOR_PRESSURE` by ours), across which a closed link leaks a large flow (Δh/CBIG). In the other 76 the open path to a small demand carries almost no flow (10⁻⁷ m³/s), so the leak moves its heads by 1 to 2.5 cm, just beyond D6. The flows agree within the leak's bound.
- **EPANET-side or v1's documented multiplicity**, as in the other profiles: `state_only_zero_flow` 74, `b_multiple_steady_states` 13, `epanet_failed` 4 more (ours converged), `epanet_unbalanced` 17, `e_epanet_invalid` 8, `d_no_converged_reference` 6, `unsupported` 3 more (two check valves on one connection), `review` 1 (EPANET's solution keeps the laws but breaks its own status rules).
- **Flow-controlled pumps in the dead ends** (619 networks): our final states are max_speed 85, min_speed 77 and no result 527 (in networks that do not converge, mostly over-controlled), and none active, since each pump's flow is the node's. The control search finds no network with more than one valid state over them.

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

**Speed-controlled pumps, slice 1 (proposal §7.5).** The change adds `control` to every pump result, null for a pump without speed control, and stamps `METHOD_VERSION` 1.1.0, so it is compared with exactly those paths left out, `control` only where it is null or absent (a control result on a pump of the old corpus is a difference):

```bash
uv run python -m tests.differential.compare "$OUT/before" "$OUT/after" \
  --ignore-null 'pumpResults.*.control' --ignore methodVersion --ignore trace.methods.methodVersion
```

Before = `15dbd1a` (the solver of `cd715ba`), after = the slice-1 working tree (the same two dumps compared again with `--ignore-null`): identical 3,092, different 0; the ignores left out 2,577 `control` values, null or absent on both sides, in 1,688 projects and the method version in each of the 3,092 (top level and methods summary). The 24 flow-controlled reference cases and the 1,000 `fuzzfc_` networks are "missing in A".

**Assigned-flow node (D12).** It changes no result of a project without one, and no method version, so the comparison has no ignores. Before = `c03217c`, after = the assigned-flow working tree: identical 4,120, different 0 (every solved value, flag, message, trace, methods summary and system-curve point). The 14 assigned-flow reference cases and the 1,000 `fuzzaf_` networks are "missing in A". The before dump took 676 s with 2 workers, the after dump 795 s with 3 (5,134 projects).

**Round-off-aware energy test and flag locations (C0b, METHOD_VERSION 1.2.0; proposal `vfd-slice2-discharge-pressure.md` §2.11.10, criteria B1–B8).** Before = `7d843be` (1.1.0) with the two `round_off_*` reference cases copied in, after = the C0b working tree: 5,136 projects with system curves, dumped at default settings and with `--solver-options tolerance=1e-13,max_iterations=1000` (criterion 7's settings, "tight"), compared exactly and with `--within-tolerance` (`--fixed-point` for the tight dumps) with `methodVersion`, `trace.methods.methodVersion`, `convergence` and `trace.methods.sections.0.items.4` ignored, and methods item 1 checked byte for byte instead of compared. An instrumented copy of each tree recorded both energy verdicts at every iterate of every inner solve. Dumps took 214 s and 215 s at default settings, 319 s and 243 s tight (4 workers). The scripts and the per-project lists behind every count below (each project not converged, by name with its message and reason; the changed states, curve points and fuzz records) are named, with their paths, in the proposal's §2.11.10 (*Measured at C0b's build*), and so is the corpus re-run after the build's review, which reproduced every count of B1–B5 and B7 below.
- **Changed verdicts (B1).** 75 projects have an iterate where the rest of the stop test passes and the two energy tests disagree: 2,313 iterates in 55 main solves and 4,829 in 109 system-curve solves (26 projects) on 1.1.0's path, at iterates whose largest head or loss is at least 1.6·10⁷ m. At 1.1.0, 27 main and 57 system-curve inner solves fail at that floor; at 1.2.0 none does. The other 5,061 projects are identical but for methods item 1 and, in the results not converged, the flag locations and the failed-state reports below; 9 of the 75 are identical too.
- **Flags (B2).** The 384 projects that converge in neither version (383 `fuzzaf_`, `fuzzfc_10070`) keep their messages. 379 of their flags named both residual locations at 1.1.0 and 5 none; at 1.2.0 none names one. The 17 that end in the failed-state exit report that solve's residuals (in all 17 a solve that was not attempted: 0, with no element).
- **States and convergence (B3).** 9 projects end in another valid state, each changed element carrying exactly 0 m³/s on every side that reports it: `fuzz_1446` (FCV4 closed → open), `fuzz_2522`, `fuzz_586`, `fuzzaf_20131`, `fuzzfc_10660` and `fuzzfc_10931` (elements that lose their results: an isolated section), `fuzzfc_10302`, `fuzzfc_10535` and `fuzzfc_10775` (elements that gain one; `fuzzfc_10775`'s PU10 also goes from no_flow to running, at 0 m³/s); both states of each pass the fuzz harness's self-check. `round_off_large_heads` converges in 5 iterations, to its closed form (1.1.0 stopped at 100, with 2.61·10⁻⁷ m at L1): the only change in convergence; with its own (Colebrook) friction the harness's law check is empty. 55 main solves take fewer Newton iterations (118,333 → 116,092 in the corpus), none more. System curves: `fuzz_2530` PU7 10 → 11 points, `fuzz_686` PU7 9 → 11; no count falls.
- **Corpus (B4).** Default: identical 4,715, within tolerance 30, different 391 (379 by flag locations, the 9 states, the 2 point counts, `round_off_large_heads`), with no number present on both sides out of tolerance (worst \|Δ\|/tolerance: flow 3.96·10⁻⁵, `fuzzfc_10775`; head 3.66·10⁻⁶, 3.7·10⁻¹² m; system-curve head 0.336, `fuzz_2777` PU11, 3.4·10⁻⁹ relative) but 11 flag numbers of `fuzzaf_20131`, compared by list index after its state change shifts the flags (worst 1.97·10⁷ of tolerance, an absolute pressure); matched flag by flag (by code, element and port), the 27 numbers of the 25 flags it has in both agree within 8.5·10⁻¹⁵ relative, at both settings. Tight: identical 4,730, within tolerance 15, different 391 (378 by flag locations; 10 states, the 9 and `fuzz_2903`, both of its states self-checked; the 2 point counts; `round_off_large_heads`). Every number of the projects converged in both is within criterion 7's tolerances (worst flow 0.040, head 3.7·10⁻⁴, system-curve head 0.035 of tolerance) but, here too, 11 flag numbers of `fuzzaf_20131`, compared by list index (matched by flag, within 8.5·10⁻¹⁵ relative, as above). Not converged in either, with the same messages: the same 384 at both settings (default: no steady state carries the assigned flows in the statuses reached 273, a flow control and assigned flows fixing the same flow 93, the failed-state exit 17, statuses oscillating 1; tight: 275, 91, 17, 1; each by name with its message and reason in the lists named above). Converged in one only: `round_off_large_heads` (1.2.0).
- **Methods (B5).** Methods item 1 of all 5,136 summaries is 1.1.0's item, one space and the energy-test sentence, byte for byte (pinned in `test_methods.py`).
- **Fuzz (B6), 9,000 seeds per tree.** 0 critical and every self-check empty in both trees, but 13 records change class, so the class tables are not unchanged: default 1,446 (documented → pass) and 2,522 (b_stagnant_heads → pass); `flow_control` 10,302 and 12,176 (pass_ep_unbalanced → epanet_unbalanced), 10,535 (pass → epanet_unbalanced), 10,660 (epanet_unbalanced → ours_verified_by_pinned_epanet), 10,775 (documented → state_only_zero_flow), 10,931 (b_stagnant_heads → review), 11,430 and 11,726 (b_stagnant_heads and documented → pass), 11,897 (b_stagnant_heads → state_only_zero_flow), 12,259 (epanet_unbalanced → pass_ep_unbalanced); `assigned_flow` 22,410 (no_steady_state_other_message → no_steady_state). 43 more records change within their class (14 default, of which 2,952 differs only in the file path of its harness error's traceback; 16 `flow_control`; 13 `assigned_flow`). Every changed record but 2,952 has a changed verdict on 1.1.0's main-solve path. Our states change in 20 records, each changed element at exactly 0 m³/s wherever it has a result (12,176's PU11 has no result in either tree: isolated at 1.1.0, held at no flow with both sides closed off at 1.2.0, which changes the EPANET run's pins); the not-converged messages of 21,606, 21,631, 21,845 and 22,410 change with the path (22,410's now states the expected over-control). The class changes follow from those zero-flow states and that message: EPANET's runs and comparisons follow our states, and neither solution fails a check. Under CLAUDE.md D13 (owner, 2026-10-25) these are the same answers (every change at zero flow, or a message), so they are accepted; the class tables of 1.2.0 are the baseline from here.
- **System curves (B7).** At default settings 47 points of 15 pumps change: 3 gain a head (`fuzz_2530` PU7, `fuzz_686` PU7 twice), none loses one, 43 move by at most 3.4·10⁻⁹ relative, and one, `fuzz_281` PU8 at zero flow, goes from 3.6·10⁻¹⁵ m to 0. At criterion 7's settings 21 points of 7 pumps change, the same 3 gain a head, and the others move by at most 3.5·10⁻¹³ relative.
- **Suites (B8).** The API suite passes, 3,690 tests (the D6 reference suite with both `round_off_*` cases, the unit tests, the differential harness's checks). Run on 1.1.0's solver (`7d843be`'s `src` with this tree's tests), 10 fail: the four flag tests that 1.1.0 cannot pass (no location where every residual is within its tolerance, on the line and on the branch; no node once continuity closes after a Newton step; the failed-state exit's residuals), the large-head test of `test_gga.py`, the two methods tests, and `round_off_large_heads` in the reference suite and in two trace checks of `test_trace.py` (it does not converge, so it has no results); `test_energy_stop_test.py` does not import (1.1.0 has no `energy_tolerances` or `_largest_exceeding`). Three flag tests pass in both, as controls: the node whose continuity residual exceeds its tolerance and the only link whose energy residual does (1.1.0's largest residual is the one that exceeds there), and the link where the iteration diverged (1.1.0 named it too; the test guards against the infinite tolerance the round-off allowance gives there).

**Scenario manager (D15).** It changes no result of a project without scenarios and no method version, and nothing under `services/solver/`, so the comparison has no ignores. Before = `4ccdf9f` (`git archive` into `/dev/shm`, solved with this tree's environment and `PYTHONPATH` set to that tree), after = the scenario-manager working tree: 5,136 projects with system curves, identical 5,136, different 0. `scenario_check` over the same corpus: 0 different (4,693 scenarios solved, 4,348 of them converged and 345 not, each equal to the hand-edited project's solve; 443 with a value rejected by both the service and the hand-edited project; 120 system curves equal).

**Goal seek (D16).** It changes no result of any project and no method version, and nothing under `services/solver/`, so the comparison has no ignores. Before = `bdbc868` (`git archive` into `/dev/shm`, solved with this tree's environment and `PYTHONPATH` set to that tree; 812 s with 3 workers), after = the goal-seek working tree (808 s): 5,136 projects with system curves, identical 5,136, different 0. `scenario_check` over the same corpus (the scenario service's planner and writer renamed for goal seek): 0 different (4,693 solved, 443 invalid in both, 120 system curves). `goal_seek_check` (51 min with 4 workers, every n = 1–4 per project): 2,136 of the corpus's 5,136 projects, every non-fuzz one (110 reference cases, 14 unit-test networks, 6 ladders, 6 step-hold wyes) and seeded samples (`--sample`) of 1,200 of the 3,000 `fuzz_`, 400 of the 1,000 `fuzzfc_` and 400 of the 1,000 `fuzzaf_` networks; the other 3,000 fuzz networks were run afterwards (below). 156 cases did not converge (skipped); of 7,920 draws, 6,413 ran (1,492 skipped because the case already came within 10 tolerances of a target, 15 without a usable target). **0 violations** (6 at first, in 3 draws: the `met_range` text, fixed at integration and re-run, proposal §12). Met: n = 1 63.8 % (701 of 1,098), n = 2 72.2 %, n = 3 76.1 %, n = 4 75.9 %; by target kind interior 95.4 %, near 98.5 %, far 0.5 % (mostly unreachable by construction), the case's own values 94.0 % (238 `met_at_start`). Evaluations (median / p90 / max): n = 1 10 / 12 / 26, n = 2 6 / 10 / 60, n = 3 9 / 17 / 80, n = 4 11 / 27 / 100. Stop reasons: met 4,430, met_at_start 238, no_progress 1,299, not_reachable 396, evaluation_limit 47 (0.73 %), time_budget 1, unsolved_crossing 1, no_usable_evaluation 1, jump 0; draws with an unusable evaluation 0.67 %; the largest `computeTime` 42.3 s (a ladder). 46 draws (0.7 %; 8 by more than 0.01 of the range, at most 0.33) report an unmet evaluation farther from the start than one whose cost agrees to 10⁻⁹ but whose residuals, rounded to 10⁻³ of their tolerances, do not (the as-built tie rule, §5.7; before it, 32 of the 562 draws of a 200-project sample reported a plateau value round-off chose, up to 1.2 of the range from the start). **After the review fixes** (proposal §12 items 35–46; the same selection re-run, 51 min): **0 violations**, and 4 of the 6,413 draws differ from the run above: two several-variable draws whose start is unusable are now searched from a usable point (`fuzzaf_20055`, n = 4: met in 19 evaluations instead of stopping at the cap; `fuzzaf_20245`, n = 3: `no_progress` instead of `no_usable_evaluation`), a one-variable draw whose closest-value search straddled the target is now solved by Brent (`fuzz_2683`: met at 10⁻⁷ instead of 0.18 tolerances, 27 evaluations instead of 26, the new n = 1 maximum), and a ladder stopped by time took 49 evaluations instead of 47 (machine-dependent, §5.7). Met n = 4 1,460; interior 95.4 %; evaluation_limit 46. The corpus comparison against `bdbc868` again gave 5,136 identical, 0 different, no ignores, and `scenario_check` 0 different (4,693 solved, 443 invalid in both, 120 system curves). **The rest of the corpus** (at `f1b44c2`; `--sample K --complement` with each profile's sample size, the 1,800 `fuzz_`, 600 `fuzzfc_` and 600 `fuzzaf_` networks the samples left out; 81 min with 2 workers): **0 violations**. 231 cases did not converge (skipped); of 11,076 draws, 8,869 ran (2,192 skipped near the targets, 15 without a usable target). Met: n = 1 62.9 % (922 of 1,466), n = 2 71.3 %, n = 3 72.6 %, n = 4 75.2 %; interior 94.8 %, near 98.0 %, far 0.2 %, the case's own values 96.3 % (343 `met_at_start`). Evaluations (median / p90 / max) as above but for n = 1's maximum, 35 (`fuzz_1338`: Brent's bracket nearest the start closes on a steep, solved state change and meets the target there; the other crossing is noted). Stop reasons: met 5,977, met_at_start 343, no_progress 1,941, not_reachable 544, evaluation_limit 64 (0.72 %), time_budget 0, unsolved_crossing 0, no_usable_evaluation 0, jump 0; draws with an unusable evaluation 0.58 %; the largest `computeTime` 8.7 s (`fuzzaf_20169`, n = 4, at the cap of 100). One interior target is reported not reachable (`fuzzaf_20330`, n = 1: the flow equals the target only on a band of reservoir levels between two scan points, with the same residual sign on both sides; the design's "a crossing narrower than the scan's steps can be missed"). 41 noise ties (4 by more than 0.01 of the range, at most 0.34, `fuzz_975`, n = 2). **The whole corpus** (the 5,136 projects of the review fixes' run and this one): 387 cases did not converge; of 18,996 draws, 15,282 ran; **0 violations**. Met: n = 1 63.3 % (1,623 of 2,564), n = 2 71.7 %, n = 3 74.1 %, n = 4 75.5 %; by target kind interior 95.1 % (8,400 of 8,835), near 98.2 %, far 0.3 %, the case's own values 95.4 % (581 `met_at_start`). Evaluations (median / p90 / max): n = 1 10 / 12 / 35, n = 2 6 / 10 / 60, n = 3 9 / 17 / 80, n = 4 11 / 27 / 100. Stop reasons: met 10,408, met_at_start 581, no_progress 3,241, not_reachable 940, evaluation_limit 110 (0.72 %), time_budget 1, unsolved_crossing 1, no_usable_evaluation 0, jump 0; draws with an unusable evaluation 0.62 %; the largest `computeTime` 42.4 s (`ladder_100_1_crane_True`, n = 3, stopped by time); 87 noise ties (0.57 %; 12 by more than 0.01 of the range, at most 0.34).

**Pump chart curves** (proposal `pump-chart.md` §6, slice 1). `PumpResult` gains `efficiencyCurve`, `npshrCurve` and `powerCurve`, sampled at 41 flows by `PumpCurveModel.sample_efficiency`, `sample_npsh_required` and `sample_shaft_power` with the functions the duty values use (η₀(Q/s), held only outside its points, so not within them; s² NPSHr₀(Q/s); ρgQ·H(Q)/η(Q) over the flows the head and efficiency points both reach, × s), and `SystemCurvePoint` gains `npshAvailable`, `npsh.npsh_available` of the point's suction EGL (null without a head, a vapor pressure, or a determined suction level; `system_curve_points(..., p_atm=...)`). No solved value, flag, trace, message or method version changes (`METHOD_VERSION` stays 1.2.0). Before = `bbafbff`, after = the working tree, dumped as for the reasons below: the corpus dumps are identical 5,136, different 0, with `--ignore 'pumpResults.*.efficiencyCurve'` and likewise `npshrCurve` and `powerCurve` (4,935 values in 2,957 projects each; non-null: 5, 46 and 5 pumps), and the `POST /api/v1/system-curve` points of every pump of every corpus project (cold, no budget, the router's point mapping) are identical 5,136, different 0, with `--ignore 'pumps.*.points.*.npshAvailable'` (70,192 values in 3,482 projects; 697 points have an NPSHa, each with a head). Unit tests (`tests/unit/test_pump_chart_curves.py`, values derived with SciPy's PCHIP, the affinity laws and Darcy–Weisbach/Colebrook) check every sample at full and reduced speed, the duty on the curves, nulls without data or an overlap, an off pump's curves at its set speed, NPSHa at every point of a single line, NPSHa at the duty flow equal to the solve's (to 10⁻⁶ m), null NPSHa without a vapor pressure, and the endpoint's and the solve's JSON.

**Pump curve facts** (proposal `pump-chart.md` §6, slice 2). `PumpResult` gains `bestEfficiencyPoint`, `shutoffHead`, `risingHeadRanges`, `speedCurves` and `isoEfficiencyLines` (`services/solver/curve_facts.py`): extrema and sign changes found from the derivative's roots on each PCHIP piece (as `speed_uniqueness` does), every value the interpolant's own, at the running speed; a BEP only where η₀'s largest value is strictly inside its points; iso-efficiency levels the multiples of 5 % below the BEP (up to three), each through every rated-speed flow where η₀ equals it (a point at exactly that level included), over 11 speeds from the minimum to the maximum. The pump trace gains the BEP's equation and values, a note per rising range and, for a speed-controlled pump, the iso-efficiency equation. Before = `3a01b94`, after = the working tree: the corpus dumps are identical 5,136, different 0, with the five new fields and the traces' `equations`, `intermediates` and `notes` ignored; the traces were then checked apart: of 454,866 lists, 8 changed, each by insertions only, all of the new kinds (5 BEP equations, 2 × 3 BEP values, 1 rising note). In the corpus 2 pumps have a BEP, 2 an extrapolated shutoff head, 1 a rising range, 1,269 speed curves and none iso-efficiency lines (the fuzz pumps' curves are straight and have no efficiency curve), so `tests/unit/test_pump_curve_facts.py` adds closed-form checks (SciPy's PCHIP, its derivative's roots, brentq and the affinity laws) and a property check of 300 seeded random curves against a dense scan (BEP the largest efficiency inside the points, rising ranges where the slope is positive and none elsewhere, iso crossings on their level).

**Design checks** (CLAUDE.md D19, proposal `design-checks.md` §6). `ProjectSettings.designChecks`, the pump curve's manufacturer data and `SolvedState.designChecks` are new; nothing else changes. Before = `1c1e3a8`, after = the working tree: the corpus dumps are identical 5,151, different 0, with `--ignore-empty designChecks` (5,151 empty lists; no corpus project has checks, so no methods section is added). `tests/differential/design_checks_check.py` then solves every corpus project twice (pump curves without an efficiency or NPSHr curve given one, in both solves, as test inputs), without and with every check on (HI 9.6.1-2012 "General", API 610's 0.7–1.2, 0.5–3 m/s) and each pump curve given manufacturer data: 5,151 projects, 0 different; the two solved states equal in every value but for the checks and their methods section, and every result equal to the one re-derived from the solved state's JSON by a second implementation of the rules (check, element, outcome, value, limits, pipes, unit and source exactly; the message's comparison words and, for a fail, compared numbers that differ in their text); 384 solves not converged (with no results). Run again after the review's fixes: the same counts, 0 different. Outcomes over the corpus (pass / fail / not evaluated): NPSH margin 14 / 4 / 4,918 (most fuzz fluids have no vapor pressure, so no NPSHa); operating region 182 / 3,867 / 887; allowable region 500 / 3,550 / 0; minimum flow 758 / 3,292 / 0; motor power 3,945 / 105 / 0; pipe velocity 5,560 / 65,223 / 0. `test_design_checks_check_smoke.py` runs the reference cases, the unit-test data networks and 70 fuzz seeds, requires a pass and a fail of every check, and catches falsified results (an outcome, value, limit, pipes, unit or message changed, a result dropped or reordered) and a solved value changed with the checks on.

**System-curve reasons.** `SystemCurvePoint` gains `reason` and seven fields of ids and numbers (SDD §4.10), built beside each message in `system_curve.py` from the same values: no message's text changes, nor any method version. Before = `f1b44c2` (`git archive` into `/dev/shm`, solved with this tree's environment and `PYTHONPATH` set to that tree), after = the working tree, both dumped side by side with 2 workers each (4 CPUs): the corpus dumps (250 s each) are identical 5,136, different 0, with no ignores. Those dumps hold a solve's own curves, whose points without a head are left out, so the `POST /api/v1/system-curve` response of every pump of every corpus project was dumped too, cold as the endpoint solves it and without the request's budget (41 points, 11 for the fuzz networks; the router's own point mapping; 348 s and 340 s), and compared with the eight new fields left out (`--ignore 'pumps.*.points.*.reason'` and likewise `componentIds`, `assignedFlowNodeIds`, `limitFlow`, `passedFlow`, `openHead`, `openHeadBound`, `startsTried`): identical 5,136, different 0, so every flow, head, `converged` value and message of the 70,192 points (6,152 curves of 3,482 projects) is unchanged; each ignore left out 70,192 values in 3,482 projects. Every reason agrees with its message (the code's opening words, the ids in the message's order, the assigned-flow nodes, the numbers as `:.6g` prints them, the starts, and `''`, null and empty fields on a point with a head): 0 disagreements. Codes: a head 31,404, `beyond_limit` 23,311, `no_way_through` 7,168, `not_converged` 5,484, `no_steady_state_found` 1,751 (starts tried: the last converged point's solution, the initial state and its control valves open 1,746; without the open start 5), `closed_off` 654, `below_floor` 397, `free_level` 22, `valve_at_switch` 1, `not_computed` 0 (no budget).

**Equipment pressure drop (D18, METHOD_VERSION 1.3.0).** The change adds `equipmentResults` to every solved state, `{}` without equipment, and stamps 1.3.0, so it is compared with exactly those paths left out. Before = `3da03c1` (a worktree solved with this tree's environment and `PYTHONPATH` set to that tree, as for D15–D17; it read METHOD_VERSION 1.2.0), after = the equipment working tree, both with system curves (4 min 33 s and 4 min 27 s, 2 workers):

```bash
uv run python -m tests.differential.compare "$OUT/before" "$OUT/after" \
  --ignore-empty equipmentResults --ignore methodVersion --ignore trace.methods.methodVersion
```

Identical 5,136, different 0; `--ignore-empty` left out 5,136 values in 5,136 projects (the empty map on both sides), and each version path 5,136. The 15 equipment reference cases are only in the after dump ("missing in A"), and every project of both dumps solved. On the branch's corpus (5,151 projects, the new cases included):

- **`scenario_check`:** 0 different (4,707 scenarios solved, 4,362 converged and 345 not; 444 with a value rejected by both; 121 system curves equal). The 15 equipment cases: 14 solved and converged, 1 invalid in both, 71 overrides.
- **`equipment_check`:** 0 different. 1,632 projects hold active isolation valves: 1,414 checked, and 218 whose valves have no result; 3,519 hold none. Of 2,047 valves, 1,781 were replaced (1,316 by a rated point, 218 by a Cv, 247 by a Kv), 266 have no result and 0 were kept; 1,044 of the items carry flow, 326 lose more than 0.01 m and 533 run in reverse flow (flagged). 0 not converged, 0 different only at zero flow. Largest differences: flow 7.77·10⁻¹⁰ of the largest flow (`unit_rich1090`), head 6.39·10⁻⁷ m (`fuzzaf_20730`). Checked per kind of project: reference 3, unit-test 4, `fuzz_` 907, `fuzzfc_` 299, `fuzzaf_` 201.
- **Fuzz:** the three class tables above, unchanged, 0 critical. Run again on `3da03c1` and compared record by record (every field but the time): 9,000 identical, so no converged solve is left not converged.
- **`missing_result_check`:** equal to the baseline (converged 3,000, 2,996 and 1,782; deletions 11,921, 14,265 and 7,789, every one reported).
- **`goal_seek_check`** over the whole corpus (`--workers 4`, 78 min, on `a374ef0`, before the merge of `main`'s pump-chart panels, which change no goal-seek code): 5,151 projects (4,766 checked, 385 whose case did not converge), 480 run on a scenario: 19,064 draws, 15,405 ran, **0 violations**, 0 errors; 72.1 % of the goals met, 94.9 % of those drawn from values the network gives inside the bounds (as D16's 95.1 %); the largest `computeTime` 43.1 s. A first sample (every non-fuzz project and seeded fuzz samples, 1,151 projects, 3,561 goal seeks) gave 0 violations too. The equipment cases: 15 checked, 2 on a scenario, 60 draws (met 39, met at the start 1, no_progress 12, evaluation_limit 5, not_reachable 3, in the sample), reaching all four rating values, all three goals and values under a scenario's whole rating.

---

## 11. Deployment

The owner chose the hosts on 2026-10-22: the web app on **Cloudflare Pages** (static) and the API on **Google Cloud Run**. Both are deployed (owner, 2026-10-25; Pages builds production from `main`), and a deployment is not a stable release (CLAUDE.md D14). This section records the configuration and the reasons for it; the README's *Deployment* section lists the owner's steps. Provider facts come from the pages linked at the end of the section, read on 2026-10-22. Prices and limits change, so check them again before deploying.

### 11.1 Frontend (Cloudflare Pages)

`@sveltejs/adapter-static`: `pnpm build` writes a fully prerendered static site to `apps/web/build/` (22 files, 0.9 MB for v1). No frontend server code runs. The host must do three things:

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
| Preview branch control | Custom branches, include `web/*` (owner, 2026-10-25) | A hosted look at web-only changes before they merge (CLAUDE.md *Tooling*). Previews are public `*.pages.dev` URLs ([previews][cf-preview]): `<commit hash>.<project>.pages.dev` and `<branch alias>.<project>.pages.dev`, the alias the branch name lowercased with every other character a hyphen. The API allows their origins through `CORS_ORIGIN_REGEX` (§11.3). Only `web/*` builds, since each build counts against the monthly limit ([branch control][cf-branch]) |

**Response headers.** `apps/web/static/_headers` is copied into the build. Pages applies it and does not serve it ([headers][cf-headers]):
- `Referrer-Policy: no-referrer` on every response, matching what `app.html` and the API client already set. Pages' default is `strict-origin-when-cross-origin` ([serving][cf-serving]).
- `X-Frame-Options: DENY` and `Content-Security-Policy: frame-ancestors 'none'`, because the app is never framed. These are Cloudflare's own hardening example ([headers][cf-headers]). There is no script CSP, because the prerendered pages carry an inline start-up script.
- `/` and `/p` get Pages' default `Cache-Control: public, max-age=0, must-revalidate` plus `no-transform`. With `no-transform`, a Cloudflare zone can't rewrite the pages to inject a script; Cloudflare documents this for the Web Analytics beacon ([Web Analytics][cf-wa]).
- `/_app/immutable/*` (content-hashed) gets `public, max-age=31536000, immutable`, the same header SvelteKit's own preview server sends (`@sveltejs/kit/src/exports/vite/preview/index.js`). `_app/env.js` and `_app/version.json` keep the default revalidation, so a rebuild reaches browsers on their next load.

Checked with `wrangler pages dev` 4.149.0 on a build made with `PUBLIC_API_URL` set:
- All four rules parsed and applied, and `/_headers` was not served.
- An unknown path got `index.html`.

**Legal notices** (AGPL-3.0-or-later; the licenses of the bundled packages):
- **Source of this version.** AGPL-3.0 §13 requires offering users of a network service the source of the version they use. `svelte.config.js` takes the commit being built from `CF_PAGES_COMMIT_SHA`, which Pages sets in every build ([build configuration][cf-build]), else from `git rev-parse HEAD`, and passes it as SvelteKit's `version.name`. `links.ts` reads it from `$app/environment` and links the source to `…/tree/<commit>` and the license to `…/blob/<commit>/LICENSE`. A build without git gets SvelteKit's default version (a timestamp) and links to the repository.
- **Source of the calculation server.** The API is built and deployed on its own (§11.2) and may run another commit than the site, so the footer and the home page also link `<PUBLIC_API_URL>/source`, which the API redirects (302) to the commit it was built from (`links.ts` `serverSourceHref`). Nothing is requested until the link is followed.
- **Third-party licenses.** The MIT, BSD-3-Clause and Zlib licenses of the bundled packages require their notices with every copy, and the minifier strips them from the JavaScript. `src/plugins/third-party-licenses.ts`, a Vite plugin, reads the npm packages of every module in the client build's chunks, plus Tailwind (generated into the CSS), and writes their license texts to `third-party-licenses.txt` at the site root. It reads the bundle, not `package.json`: the Svelte and SvelteKit runtimes are dev dependencies but ship, and a dependency that is never imported does not. A bundled package without a license field or file fails the build. For v1 it lists 11 packages, all MIT except fast-uri (BSD-3-Clause) and pako (MIT AND Zlib); the export (§8.3) added none, and its lazily loaded chunk is read like every other chunk. The plugin does not read Web Worker bundles (`worker.plugins`): a worker added later must run it there too, or its packages' notices are missing.
- **Copyright.** The footer and the home page show `Copyright © 2026 Chris Cirone`, with the license and the no-warranty disclaimer: the "Appropriate Legal Notices" an interactive interface must display (AGPL-3.0 §0, §5d).

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
- Limits: 500 builds a month, one at a time, 20 minutes each; 20,000 files per site; 25 MiB per file; 100 `_headers` rules ([limits][cf-limits]). The site uses 22 files and 4 rules.

### 11.2 Backend (Google Cloud Run)

**Image.** `apps/api/Dockerfile` is built from `apps/api`. `.dockerignore` keeps the build context to `pyproject.toml`, `uv.lock`, `LICENSE` and `src/`, with the Dockerfile and `.dockerignore` (57 files, 0.9 MiB).
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

**Client address behind Google's front end.** The rate limit and the per-client solve limit count a client by a key made from its address (SDD §7.2), which the app sees only through `X-Forwarded-For`.
- **The container never sees the client directly.** Cloud Run terminates TLS and proxies each request to the container over HTTP/1, so the container's TCP peer is Google's proxy ([container contract][gc-contract]).
- **Where the client's address is in the header: observed, not documented.** Google documents `X-Forwarded-For` for its load balancers and for Cloud Run functions, not for Cloud Run's own front end.
  - Google's load balancers append two addresses, the client's and then "the IP address of the load balancer's forwarding rule", and "the load balancer does not verify any IP addresses that precede" those two ([load balancing][gc-lb]). The Cloud Run functions header reference shows `X-Forwarded-For: clientIp, proxy1Ip, proxy2Ip` ([headers][gc-fn-headers]). If Cloud Run's front end worked like that, the right-most entry would be a Google address, not the client's, so these pages don't support the image's setting.
  - For requests straight to a `*.run.app` URL, two sources put the client's address last. A header dump from August 2023 shows a single entry, `X-Forwarded-For: 1.2.3.4` ([header dump][run-xff-dump]). Google's own Cloud Run sample was fixed in December 2023 by setting Express's `trust proxy` to `1` ([sample fix][gc-sample-fix]), and that setting takes the right-most entry of `X-Forwarded-For` as the client ([Express][express-proxy]).
  - Google doesn't document the proxy's own source address on Cloud Run either. A report from October 2026 found 169.254.169.126, a link-local address ([report][gh-report]).
  - The §11.4 check tests both observations after every deployment.
- **How uvicorn picks the client.** uvicorn 0.54 (`ProxyHeadersMiddleware`) reads `X-Forwarded-For` only when the TCP peer is in `FORWARDED_ALLOW_IPS`, and then takes the right-most entry that is not in the list. With `*` it takes the left-most entry, which the client writes itself.
- **What the image sets.** `FORWARDED_ALLOW_IPS` lists every block that IANA's special-purpose registries mark as not globally reachable and that a host can hold ([IPv4][iana4], [IPv6][iana6]): `127.0.0.0/8`, `::1`, `169.254.0.0/16`, `fe80::/10`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `100.64.0.0/10` and `fc00::/7` (RFC 1122, 4291, 3927, 1918, 6598, 4193).
  - Whichever of these addresses the proxy uses is trusted.
  - No client on the internet can connect from one of them.
  - So, with the client's address last in the header (above), it is the right-most entry outside the list, and uvicorn makes it the request's client.
- **The key** (`client_key` in `middleware.py`). The rate limiter passes it on as the request's client, and the solve route hands that to the pool (`workers.py`), so both limits count clients the same way:
  - An IPv4 address is its own key.
  - An IPv6 address is keyed by its /64 network (`2001:db8:1:2::/64`). The last 64 bits are the interface identifier ([RFC 4291][rfc4291] §2.5.1), which the host chooses: it makes new random ones over time ([RFC 8981][rfc8981] §3.4), and networks are recommended to let it form new addresses without asking, for example by giving it a /64 of its own ([RFC 7934][rfc7934] §8). Keyed by the whole address, one host could take any number of buckets and pool slots. `*.run.app` hosts answer over IPv6 too: a lookup on 2026-10-22 returned 8 AAAA records, such as `2600:1900:4240:200::`.
  - An IPv4-mapped IPv6 address (`::ffff:198.51.100.7`, [RFC 4291][rfc4291] §2.5.5.2) is keyed as its IPv4 address.
  - Anything that isn't an address (no client, a forwarded value that doesn't parse) shares one key, `unknown`.
  - Not covered: a site given more than a /64 (the registries encourage /56 blocks for end sites, [RFC 6177][rfc6177] §1) has a key per /64, and a client with many IPv4 addresses has a key per address.
  - The key holds an address or a prefix, so it stays in memory and is never logged.
- **Checked locally** with the exact command, where the TCP peer is 127.0.0.1 and `X-Forwarded-For` is sent as the front end would send it:
  - After 60 requests from one client, the 61st got 429.
  - Another client got 400, so it has its own bucket.
  - The first client putting its own entry first (`198.51.100.99, <client>` or `10.1.2.3, <client>`) still got 429.
  - With `FORWARDED_ALLOW_IPS='*'`, the client-written entry escaped the limit (400).
  - After 60 requests from `2001:db8:1:2::1`, both `2001:db8:1:2::2` and `2001:db8:1:2:dead:beef:1234:5678` got 429 (same /64), and `2001:db8:1:3::1` got 400.
  - The access log held no client address and no query string.
- **After deploying, run the check in §11.4**, because Google documents neither the proxy's address nor where its front end puts the client's address. If the check shows one shared bucket, find out why with the echo service below before changing anything. Don't add the load balancers' "request source ranges" `35.191.0.0/16` and `130.211.0.0/22`: the page lists them as the sources of Google Front End traffic to instance-group and zonal NEG backends, and for serverless NEGs, the backend type through which a load balancer reaches Cloud Run, it says only that "Google's production network handles packet routing" ([load balancing][gc-lb]). They are not the address a front end writes into the header either.
- **Finding out why every user shares one bucket.** Deploy the same image as a separate, private service that runs `forwarded_for_echo` (`middleware.py`). It answers each request with its TCP peer and its `X-Forwarded-For` as they arrived, and logs nothing:
  ```bash
  gcloud run deploy xff-echo --image "$IMAGE" --no-allow-unauthenticated --max-instances=1 \
    --service-account=opensolve-pipe-api@PROJECT_ID.iam.gserviceaccount.com \
    --command=/app/.venv/bin/uvicorn \
    --args=opensolve_pipe.middleware:forwarded_for_echo,--host=0.0.0.0,--port=8080,--no-proxy-headers,--no-access-log
  ECHO=$(gcloud run services describe xff-echo --format='value(status.url)')
  for family in -4 -6; do   # -6 only where this machine has IPv6
    curl -s "$family" -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
      -H 'X-Forwarded-For: 203.0.113.7' "$ECHO"
  done
  gcloud run services delete xff-echo
  ```
  - Only accounts allowed to invoke the service get an answer ([authenticating][gc-dev-auth]). Port 8080 is where Cloud Run sends requests unless configured ([container contract][gc-contract]). Its request log is dropped by the same `_Default` exclusion as the API's (below).
  - **`peer` outside the image's blocks:** uvicorn ignored the header, so every request was keyed by the proxy's address. Add the peer addresses you see to `FORWARDED_ALLOW_IPS`; Google publishes no range for them.
  - **More than one entry after `203.0.113.7`:** the front end appended its own address after yours, as the load balancers append their forwarding rule's address, and uvicorn keyed every user on it. Add the entries after your own address to `FORWARDED_ALLOW_IPS`, with the API host's other A and AAAA records (`dig +short A <api-host>`, `dig +short AAAA <api-host>`), since a client may connect to any of them. No client connects from those addresses.
  - **Exactly one entry after `203.0.113.7`, and `peer` inside the blocks:** the header is as assumed, so look for another proxy in front of the API (next item).
  - Then set the list with `gcloud run services update opensolve-pipe-api --update-env-vars='^;^FORWARDED_ALLOW_IPS=<the image's list>,<additions>'` and run §11.4 again.
- **Put no other proxy in front of the API** (a Cloudflare-proxied hostname, a load balancer) without revisiting this list. Each proxy appends its own address, which would become every user's key. A Cloudflare proxy would also terminate TLS and see the project data in request bodies.
- **Use the API's `*.run.app` URL as `PUBLIC_API_URL`.** Cloud Run's own domain mapping is in Preview and "not recommended for production services". The alternative is a load balancer, which costs money and appends its own address ([custom domains][gc-domains]).

**Service settings.** Each value comes from the code, from measurement or from Google's documentation:

| Setting | Value | Why |
|---|---|---|
| Region | `us-central1`, or another Tier 1 region near the users | The free tier is applied at Tier 1 (us-central1) prices ([pricing][gc-price]) |
| CPU | 1 | Two solve threads (`SOLVE_WORKERS`) hold the GIL most of the time, so they need about one core. Cloud Run warns that a single-threaded app on several vCPUs leaves them idle and skews CPU-based scaling ([concurrency][gc-concurrency]) |
| Memory | 1 GiB | See the measured peaks below. 512 MiB (the default and the gen2 minimum) leaves too little headroom ([memory][gc-memory]). An instance over its limit is terminated, and every request still on it ends with a 500 ([container contract][gc-contract]). 1 vCPU allows up to 4 GiB |
| Concurrency | 20 | Above the 12 requests the app can hold open, so that the app, not Cloud Run, answers overload (see below). The gcloud default is 80 per vCPU ([concurrency][gc-concurrency]) |
| Request timeout | 60 s | The frontend's own timeout (`DEFAULT_TIMEOUT_MS`). The solve budget is 45 s from the request's arrival, and Cloud Run counts container start-up inside its timeout ([container contract][gc-contract]). The default is 300 s ([timeout][gc-timeout]) |
| Minimum instances | 0 | Idle instances that aren't minimum instances cost nothing ([pricing][gc-price]). The cost is a cold start once Cloud Run has shut the idle instance down, which can take up to 15 idle minutes ([autoscaling][gc-scaling]). A cold start took about 5 s here to import the app, 3.3–4.0 s of it CoolProp |
| Maximum instances | 1 at first | The in-memory limits (60 solves a minute per client, one solve at a time) hold exactly only within one instance, and one instance bounds the CPU and memory charges, though not request fees or outbound data (§11.5). Raise it when traffic needs it, and revisit the concurrency then |
| Billing | request-based (the default) | CPU is allocated only while requests are handled ([container contract][gc-contract]), and a solve runs only inside its request |
| Startup CPU boost | the default (on) | Extra CPU during start-up, billed only then ([CPU][gc-cpu]) |
| Ingress, authentication | all; unauthenticated allowed | A public API for the web app |
| Service account | a dedicated one with no roles | The API calls no Google API |
| `CORS_ORIGINS` | the site's origins | §11.3 |
| `CORS_ORIGIN_REGEX` | the site's Pages previews | §11.3 |

**Measured** on one 2.8 GHz Xeon core here; Cloud Run's vCPU may be slower.
- **Memory:** peak RSS was 302 MB for one solve of the largest network the schema allows (999 components, 1,494 connections, Crane tees) and 456 MB with the pool full (6 such solves, 2 running).
- **Speed:** that network solved in 8.5 s alone and in about 21 s two at a time. Of 7 sent at once:
  - 4 finished within 42 s;
  - 2 ran out of the 45 s budget (503 `TIMEOUT` at 45.8 s);
  - 1 was refused (503 `SERVER_BUSY`).
- **Small networks:** the pump example solved in 0.05 s.
- **Response size:** gzip took the largest response from 16.4 MB to 0.47 MB.

**Concurrency: why 20.** Cloud Run's concurrency caps every request on the instance, GETs and CORS preflights included. The app's own limits count only solves.
- **What the app holds open: at most 12 requests.** `MAX_SOLVES_IN_FLIGHT` (6) solves sit in the pool, and behind each a client may have one more waiting for its turn (`MAX_WAITING_PER_CLIENT` = 1, `workers.py`). Each can last up to the 45 s budget. The app answers every other request at once: a further solve with 503 `SERVER_BUSY`, which carries the CORS headers and `Retry-After: 5`, and a GET within milliseconds.
- **At 6, Cloud Run answered instead of the app.** With maximum instances 1 no other instance can start. A 7th request pends "for up to 3.5 times average startup time of container instances of this service, or 10 seconds, whichever is greater", and then "the request fails with a 429 error code" ([autoscaling][gc-scaling]). Google lists "a long request processing time" among the causes ([troubleshooting][gc-trouble]). Three users each solving a large network again before the first result came back were enough, and the 7th request could be another user's page load. Cloud Run sends that 429 without reaching the container, so it has none of the app's CORS headers. The browser can't read it, and the web app reports the server as unreachable (`client.ts`).
- **Why not the default 80: memory.** A request the app refuses still holds its body and its parsed project until it is answered.
  - Largest-size solve bodies (1,000 components, 2,000 connections, 0.87 MB) arriving at once peaked at 451 MB RSS for 20 and at 741 MB for 40, against 164 MB idle: about 14.5 MB per request. A parsed project waiting for its turn holds about 9 MB.
  - At 20, a full pool (456 MB, above), 6 waiting and 8 arriving come to about 0.63 GB of the 1 GiB limit. At 80 the same estimate is about 1.5 GB, and an instance over its limit is terminated with every request on it ([container contract][gc-contract]).
- **What no value prevents.** Cloud Run lowers an instance's concurrency by 1 each time its CPU use over the past second exceeds 90% ([autoscaling][gc-scaling], adaptive concurrency tuning), and two solve threads keep one vCPU near 100%. After about 8 s of long solves the limit can reach the 12 requests the app holds, and Cloud Run's 429 is possible again. A larger value only delays that, at the memory cost above.

**Logs.**
- **Cloud Run's request log would undo the app's log privacy.** Cloud Run writes a request log entry for every request automatically. Its `httpRequest` holds the client's address (`remoteIp`) and the full URL with its query string ([logging][gc-logging], [LogEntry][gc-logentry]), which would undo `logging_privacy.py` (SDD §7.3).
- **Exclude it from the project's `_Default` sink:** `gcloud logging sinks update _Default --add-exclusion='name=no-run-request-logs,filter=LOG_ID("run.googleapis.com/requests")'`. Cloud Logging still receives excluded entries but doesn't store them ([routing][gc-routing]).
- **Usage counts stay available.** Request counts remain available as Cloud Run's request-count metric ([monitoring][gc-monitoring]), and Google Cloud metrics cost nothing ([pricing][gc-obs-price]). The container log (the app's access log, without addresses) is kept.

**Build and images.**
- **Build** from GitHub, at a commit on its `main` branch, from anywhere (no checkout needed, e.g. Cloud Shell):
  ```bash
  SHA=$(git ls-remote https://github.com/ccirone2/opensolve-pipe refs/heads/main | cut -f1)
  curl -fsSL "https://raw.githubusercontent.com/ccirone2/opensolve-pipe/$SHA/apps/api/cloudbuild.yaml" -o /tmp/cloudbuild.yaml
  gcloud builds submit https://github.com/ccirone2/opensolve-pipe --git-source-revision="$SHA" \
    --git-source-dir=apps/api --config=/tmp/cloudbuild.yaml \
    --substitutions="_IMAGE=$IMAGE,_SOURCE_COMMIT=$SHA"
  ```
  Cloud Build fetches that commit and runs the build in its `apps/api` (gcloud sends the repository URL, `dir` and `revision` as the build's `gitSource`; the config file is read locally, so it is fetched at the same commit: a relative `--config=apps/api/cloudbuild.yaml` fails outside a checkout with "Unable to read file", as it did in Cloud Shell on 2026-10-26), so the image is exactly the public source it links: no uncommitted or unpushed change can reach it, and a commit on `main` stays reachable (a feature branch's commit can disappear when the branch is squash-merged and deleted). `docker build` applies `.dockerignore` to that directory, so the image holds what it did before. `cloudbuild.yaml` builds the Dockerfile with the commit as the `SOURCE_COMMIT` build argument and pushes the image to Artifact Registry. Cloud Build checks `mirror.gcr.io` before Docker Hub ([cache][gc-mirror]). `--tag` cannot pass a build argument (gcloud then runs its own `docker build` step, and `--tag` and `--config` exclude each other), hence the config file. Neither substitution has a default, so Cloud Build refuses a build that leaves one out unless `ALLOW_LOOSE` is set, as it is for builds started by a trigger ([substitutions][gc-subst]); and the step refuses a commit that is not a full 40-character lowercase hash (an empty value, from `git rev-parse` outside a checkout, or a short one), which `tests/unit/test_source.py` runs under Cloud Build's substitution rules. Not run in Cloud Build here (no credentials): gcloud's own loader parses the config, gcloud's source (`submit_util.py`) shows the `gitSource` request, and the §11.4 source check confirms each deployment.
- **Source of this version (AGPL-3.0 §13).** The Dockerfile's last stage turns the build argument into `ENV SOURCE_COMMIT`. The server (`source.py`) records it when it is a full 40-character commit and reports it at `GET /api/v1/about`; `GET /source` redirects (302) to `…/tree/<commit>`, and the web app links there (§11.1); `GET /` redirects to `/api/v1/about`, for someone who opens the API's address. An image built without it (a plain `docker build`) records no commit and links to the repository. Checked on an image built from this Dockerfile, with and without the argument: `/api/v1/about` gave the commit and `/source` its tree, else `null` and the repository.
- **A build from a local directory** (`gcloud builds submit apps/api --ignore-file=.dockerignore --config=… --substitutions=…`) uploads the working tree, which can differ from the commit it names, so it is not used for deployment. `--ignore-file` matters there: without it, gcloud uploads everything in `apps/api` that its default rules don't skip, a local `.venv` included: 23,222 files and 996 MiB here, against 57 files and 0.9 MiB with it (2026-10-25, with `cloudbuild.yaml` left out by `.dockerignore`). This was checked with gcloud's own file chooser (`gcloud meta list-files-for-upload` on a copy whose `.gcloudignore` is the `.dockerignore`).
- **Build and deploy are separate commands.** `gcloud run deploy --source` takes no ignore file and writes a `.gcloudignore` into the source directory.
- **Permissions:** in projects where default service accounts don't get Editor automatically, Cloud Build's default service account needs `roles/run.builder` ([deploying from source][gc-source]).
- **Cleanup:** the repository's cleanup policy deletes every image except the 3 most recent. Google's keep policies only "keep artifacts that would be deleted according to the specifications of your delete policy", and an artifact that matches both is kept ([cleanup][gc-ar-cleanup]). So the policy pairs a Delete rule that matches every image (`tagState: any`, its only condition) with a Keep rule for the 3 most recent versions (`mostRecentVersions.keepCount: 3`). A Delete rule limited by age (`olderThan: 30d`) would keep every younger image, however many deployments there were. Artifact Registry applies policies in a periodic background job, and changes take effect "within approximately one day" ([cleanup][gc-ar-cleanup]). Each image is about 0.12 GiB compressed (120 MiB measured, below), so 3 fit the 0.5 GiB of free storage (§11.5).

**Checked here: the image, built and run (session 3).**
- **Build.** The session's TLS-intercepting proxy needs its certificate inside the build containers, so the check built a copy of the build context whose Dockerfile differs from `apps/api/Dockerfile` only by two lines in the build stage (`COPY` the proxy's CA file, `ENV SSL_CERT_FILE` to it), with `docker build --network host`. The runtime stage copies only `/app/.venv` from the build stage, so neither line reaches the image: it holds no CA file and no proxy or TLS variables. Cloud Build needs neither line.
- **Size.** 544 MB unpacked, 120 MiB as the gzipped `docker save` of every layer (the base image included); the virtual environment is 271 MiB. Three images fit the 0.5 GiB of free storage (§11.5).
- **Run.** `docker run` with the image's own command: uid 10001, `/app` not writable; `/health` answered 5.8 s after `docker run`; `/docs` and `/redoc` 404, `/openapi.json` 200; a 3 MB body 413; `docker stop` (SIGTERM) shut down cleanly in 0.8 s with exit code 0.
- **Same results.** All 94 reference cases solved in the container gave responses identical to the same cases solved in-process from the working tree (Python 3.12.3), apart from `computeTime` and `solvedState.timestamp`.
- **Client keys and logs**, through Docker's port mapping, whose source address (172.17.0.1) is in `FORWARDED_ALLOW_IPS`, so the container read `X-Forwarded-For` as it would behind Google's proxy: 60 invalid bodies from `203.0.113.7, 203.0.113.50` gave 400, the 61st 429, and 429 again with the client's own entry rewritten (`192.0.2.1, 203.0.113.50`); `203.0.113.51` gave 400; after 60 requests from `2001:db8:1:2::1`, `2001:db8:1:2::ffff` (the same /64) gave 429 and `2001:db8:1:3::1` gave 400. The access log held no address and no query string.
- **End to end.** The whole Playwright suite (§10, desktop and mobile) ran against the container on the e2e port: 52 passed, 2 skipped by design.
- Not checked here: everything in §11.4, which tests Google's front end itself and so needs a deployment. It is run after each deployment, the first (the owner's, 2026-10-25) included; no result of it is recorded here.

### 11.3 Environment Variables

```bash
# Frontend: Cloudflare Pages build variables, read when the static site is built
# (PUBLIC_API_URL defaults to http://localhost:8000)
PUBLIC_API_URL=https://opensolve-pipe-api-<project-number>.us-central1.run.app   # §11.2, no trailing slash
NODE_VERSION=22.22.0
PNPM_VERSION=10.28.0

# Backend: Cloud Run service (Cloud Run sets PORT)
CORS_ORIGINS=https://<pages-project>.pages.dev   # comma-separated; add a custom domain's origin when there is one
CORS_ORIGIN_REGEX=https://[a-z0-9-]+[.]<pages-project>[.]pages[.]dev   # optional: the Pages previews (§11.1)
# FORWARDED_ALLOW_IPS is set in the image (§11.2); override it only after the §11.4 check
# API_DOCS=1 would serve /docs and /redoc, which load third-party assets: development only (§9.2)
```

`CORS_ORIGIN_REGEX` allows, besides `CORS_ORIGINS`, every origin it matches whole (Starlette's `fullmatch`; `main.cors_settings`): the previews' hostnames change with each branch and commit, so no list can name them. `[a-z0-9-]+` is one DNS label, so `a.b.<project>.pages.dev`, another project and any longer host (`….pages.dev.example`) are refused (`tests/unit/test_health.py`); `[.]` is a literal dot that needs no escaping in a shell or gcloud. Only the owner's Pages project deploys under `<project>.pages.dev`, and a preview runs this repository's code, so it sends what the site sends; previews are still public, so they take the API's rate limits like any client. Unset or blank, no regex applies; one that does not compile stops the server at start-up. The API reads no other variable (the old `ENVIRONMENT=production` was never read). With gcloud, a value that contains commas needs another delimiter: `--update-env-vars='^;^CORS_ORIGINS=https://a.pages.dev,https://example.org'` (`gcloud topic escaping`).

### 11.4 Checks After Each Deployment

1. **Health and docs:** `curl https://<api>/health` returns `{"status":"healthy"}`, and `/docs` returns 404 (`API_DOCS` is unset).
2. **Source:** `curl -s https://<api>/api/v1/about` names the commit that was built (`$SHA`, §11.2); `curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' https://<api>/source` prints `302 https://github.com/ccirone2/opensolve-pipe/tree/$SHA`, and that page opens. (The routes answer GET only: `curl -I` sends HEAD and gets 405.)
3. **Client address (§11.2)**, while maximum instances is 1. The body `{}` is rejected before any solve, so the check costs nothing:
   ```bash
   API=https://<api>
   hit() { curl -s -o /dev/null -w '%{http_code}\n' -H 'content-type: application/json' --data '{}' "$@" "$API/api/v1/solve"; }
   for i in $(seq 60); do hit -4 > /dev/null; done   # 60 invalid bodies: 400 each, counted by the rate limit
   hit -4                                            # 429: this client's minute is used up
   hit -4 -H 'X-Forwarded-For: 203.0.113.7'          # 429: an entry the client writes does not change its key
   ```
   - Where this machine has IPv6, repeat the three steps with `-6`; IPv6 has its own bucket. Then, if the machine has a second global address in the same /64 (`ip -6 addr show scope global` often lists a stable and a temporary one), `hit -6 --interface <that address>` should also return 429, because the key is the /64.
   - Then, within the same minute, run `hit` from another network (another machine, or this one on a phone's hotspot). It should return 400; 429 means every user shares one bucket (§11.2 says how to find out why).
4. **Logs:** in Logs Explorer, `LOG_ID("run.googleapis.com/requests")` shows nothing newer than the exclusion. The container log has lines like `- - "POST /api/v1/solve HTTP/1.1" 400`, with no addresses.
5. **Site**, on a desktop browser and on a phone:
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
| Cloud Run, request-based billing (per billing account) | 180,000 vCPU-s, 360,000 GiB-s, 2 million requests ([pricing][gc-price]) | $0.000024 per vCPU-s, $0.0000025 per GiB-s, $0.40 per million requests (us-central1). Requests are billed only when they reach the container ([pricing][gc-price]) |
| Outbound data from Cloud Run to the internet (Premium Tier, which Cloud Run uses, [pricing][gc-price]) | 1 GiB within North America ([pricing][gc-price]) | Per GiB, from us-central1: $0.12 to North America, Europe and Asia except Korea and Indonesia, $0.11 beyond 1 TiB a month, and beyond 10 TiB $0.08 to North America or $0.085 to Europe and Asia; for the first TiB, $0.19 to Australia, Indonesia, Korea, South America and Saudi Arabia and $0.23 to China ([network pricing][gc-net-price]) |
| Cloud Build | 2,500 build-minutes, e2-standard-2 ([pricing][gc-cb-price]) | $0.006 per minute |
| Artifact Registry storage | 0.5 GiB ([pricing][gc-ar-price]) | $0.000136986 per GiB-hour (about $0.10 per GiB-month) |
| Cloud Logging storage | 50 GiB per project ([pricing][gc-obs-price]) | $0.50 per GiB |

- **The free tier covers 50 instance-hours of active time a month.** At 1 vCPU and 1 GiB, an instance costs $0.0000265 per second while it handles requests. The vCPU allowance (180,000 s) is the one that runs out first.
- **Ordinary use stays at $0.** A typical solve keeps the instance active for well under a second (0.05 s for the pump example).
- **Maximum instances 1 bounds CPU and memory at about $64 a month.** That is a month of non-stop use (730 h) after the free tier: 2,448,000 vCPU-s × $0.000024 plus 2,268,000 GiB-s × $0.0000025.
- **It does not bound request fees or outbound data.** Both are charged per request and per byte, however many instances run ([pricing][gc-price]).
  - Only `/api/v1/solve`, `/api/v1/system-curve` and `/api/v1/goal-seek` are rate limited (`RATE_LIMITED_PATHS`), and only per client, so nothing in the app caps the total. The GET endpoints are cheap to serve and large: `/api/v1/library` is 78,221 bytes without gzip (11,010 with it), and `/openapi.json` 102,984 (20,178 with it).
  - Measured here on 2026-10-22 (one core, 20 keep-alive connections, image command): one instance served `/api/v1/library` without gzip at 855 requests/s, 66.9 MB/s.
  - Kept up for a month, that is about 2.2 billion requests (about $900 in request fees) and about 164,000 GiB out (about $13,400 at the North America rates, more elsewhere). At first-tier prices it accrues about $28 an hour.
  - The instance's throughput is therefore the only bound in the app's own setup, and it lies far above any budget. Not done: a per-client limit on the GET endpoints, or serving the library and fluid lists from the static site, would lower it.
- **So set a spend cap; it is the bound that matters.** An alerts-only Cloud Billing budget doesn't cap spending ([budgets][gc-budgets]). A spend cap budget on the project and Cloud Run pauses new Cloud Run usage for the rest of the month once its amount is reached ([spend caps][gc-spend-cap]).
  - It covers outbound data: a spend cap is set on one service, Cloud Run's service id is 152E-C115-5142 ([spend caps][gc-spend-cap]), and Google's SKU list files Cloud Run's internet data transfer ("Cloud Run Network Internet Data Transfer Out …") under that same service ([SKU group][gc-sku-egress]). The spend-cap page itself names services, not SKUs.
  - It is not exact: "the enforcement of spend caps isn't instant and any cost overages are billed as normal", and in-flight requests are "processed to completion, accruing charges as applicable" ([spend caps][gc-spend-cap]).
  - Set it at whatever monthly amount the owner accepts, knowing that the API stops when it triggers.

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
[run-xff-dump]: https://sharats.me/posts/tale-of-two-forwarded-headers/
[gc-sample-fix]: https://github.com/GoogleCloudPlatform/nodejs-docs-samples/pull/3586
[express-proxy]: https://expressjs.com/en/guide/behind-proxies.html
[gh-report]: https://github.com/zkproofport/proofport-relay/issues/4
[rfc4291]: https://www.rfc-editor.org/rfc/rfc4291
[rfc8981]: https://www.rfc-editor.org/rfc/rfc8981
[rfc7934]: https://www.rfc-editor.org/rfc/rfc7934
[rfc6177]: https://www.rfc-editor.org/rfc/rfc6177
[gc-dev-auth]: https://docs.cloud.google.com/run/docs/authenticating/developers
[iana4]: https://www.iana.org/assignments/iana-ipv4-special-registry/
[iana6]: https://www.iana.org/assignments/iana-ipv6-special-registry/
[gc-domains]: https://docs.cloud.google.com/run/docs/mapping-custom-domains
[gc-price]: https://cloud.google.com/run/pricing
[gc-concurrency]: https://docs.cloud.google.com/run/docs/about-concurrency
[gc-memory]: https://docs.cloud.google.com/run/docs/configuring/services/memory-limits
[gc-timeout]: https://docs.cloud.google.com/run/docs/configuring/request-timeout
[gc-scaling]: https://docs.cloud.google.com/run/docs/about-instance-autoscaling
[gc-trouble]: https://docs.cloud.google.com/run/docs/troubleshooting
[gc-cpu]: https://docs.cloud.google.com/run/docs/configuring/services/cpu
[gc-logging]: https://docs.cloud.google.com/run/docs/logging
[gc-logentry]: https://docs.cloud.google.com/logging/docs/reference/v2/rest/v2/LogEntry
[gc-routing]: https://docs.cloud.google.com/logging/docs/routing/overview
[gc-monitoring]: https://docs.cloud.google.com/run/docs/monitoring
[gc-obs-price]: https://cloud.google.com/stackdriver/pricing
[gc-mirror]: https://docs.cloud.google.com/artifact-registry/docs/pull-cached-dockerhub-images
[gc-subst]: https://docs.cloud.google.com/build/docs/configuring-builds/substitute-variable-values
[gc-source]: https://docs.cloud.google.com/run/docs/deploying-source-code
[gc-ar-cleanup]: https://docs.cloud.google.com/artifact-registry/docs/repositories/cleanup-policy
[gc-ar-price]: https://cloud.google.com/artifact-registry/pricing
[gc-cb-price]: https://cloud.google.com/build/pricing
[gc-budgets]: https://docs.cloud.google.com/billing/docs/how-to/budgets
[gc-spend-cap]: https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps
[gc-net-price]: https://cloud.google.com/vpc/network-pricing
[gc-sku-egress]: https://cloud.google.com/skus/sku-groups/network-egress

---

## 12. Implementation Questions

**Decided** (recorded in `CLAUDE.md` D7–D9, D11, D12 and D15–D18):

1. **Tee and wye K correlation:** Crane TP-410 functions in `fluids.fittings`; Darby 3-K fallback for tees with the combined flow through the branch; uncovered wye patterns are not converged (§4.2).
2. **Water property package:** CoolProp 8.0.0, `Water` = IAPWS-95; glycols `INCOMP::MEG`/`MPG` (§4.6).
3. **Transition-zone friction (Re 2000–4000):** EPANET 2.2's Dunlop cubic, flagged as transitional; not a user option (§5.2).
4. **Pump curve fitting:** PCHIP through the user's points, straight end-slope extrapolation outside them (flagged), affinity laws (§5.3).
5. **Control-valve status oscillation:** at most 30 counted outer iterations (holding or releasing zero-flow branch legs is not counted, §5.4); once statuses cycle after a step that changed several, one status changes per iteration, and a state reached again goes back to the latest several-change state for a change not yet taken; with none left it returns `converged: false` naming the oscillating components (§5.4).
6. **Speed-controlled pumps, slice 1 (flow setpoint):** the setpoint is imposed as a fixed flow and the speed recovered by Brent's method, exact by the block-triangular argument; uniqueness of the speed root by the exact ψ test on the PCHIP pieces (`CONTROLLED_PUMP_CURVE` otherwise), the root sought on [s_lo, s_max] where F(·, Q_set) rises and rule A2 bounded by F(s_lo, Q_set); at a limit the pump is the fixed pump at that speed (the link's own law at s_max, a `LinkState.law` override at s_min); rules A0–C1 with EPANET's Htol and Qtol; minimum speed required with no default; `speed` is the maximum (≤ 1); no sleep at low demand; plain affinity efficiency; `schemaVersion` 1; `METHOD_VERSION` 1.1.0 (§5.4; CLAUDE.md D11). Slices 2 (discharge pressure) and 3 (differential pressure) are designed in `docs/proposals/vfd-pump-modes.md` §4.10 and are Later.
7. **A flow setpoint beyond the curve even at maximum speed** (owner's decision, 2026-10-23; was open item 5): Q_set ≥ s_max·x_mono is invalid input, the topology issue `CONTROLLED_PUMP_SETPOINT` (422, listed with every other issue), checked after the ψ test on a curve that passes it, with the owner's message naming the bound s_max·x_mono. No speed in the drive's range controls such a flow, and the two limit states that can both satisfy the rules there made the result depend on the solve's path. The quotient form Q_set/x_mono ≥ s_max is rejected too, so that s_lo < s_max in floating point (§5.4). The web app tells the issue with names and display units (`utils/issue-text.ts`). The `flow_control` fuzz profile no longer copies an equal setpoint at or beyond the new pump's bound (five seeds changed, §10.4). In `METHOD_VERSION` 1.1.0 (unreleased).
8. **System curves through a series FCV, PRV or PSV** (owner's decision, 2026-10-23; was open item 4): every point whose forced flow passes with a determined head reports that head. A point that has no head after its warm start, while the flow has a way through, is solved again from the initial state, and then from it with the active control valves open (EPANET 2.2's badvalve state: from the initial state the status rules open a series valve again at every flowing point below its switch, but at zero flow an active valve beside the forced flow is starved and closed again, so a cold retry alone leaves no head at zero flow behind a series FCV, PRV or PSV); the first solve with a head, or that finds a control valve in series at its switch, is used and the next point continues from it, and with none the warm result is kept; a flowing point beyond what every way between the pump's sides can pass that way (a cut of FCVs at their setpoints and one-way elements against the flow, max-flow min-cut) is not solved again, since no steady state carries it, and a point at that limit is solved with each FCV of the cut held open, to find whether it is at its switch (a setpoint that the requested flows sample, where rounding in the FCV rule decided the message before). A point at a control valve's switch (an FCV passing exactly its setpoint, a PRV outlet or PSV inlet at its setting) has no head, since the valve could also hold the flow throttled with any higher head, as has a side of the pump on a free level (before, a zero-flow point there reported a head against the solver's arbitrary reference level). Each point without a head says which of no way through, no steady state, undetermined head or not converged it is (§5.6). Curves that had a head at every point are unchanged; the cost is up to two extra solves for each point without a head within the cut's limit, and one per FCV of the cut at its limit (§5.6: the corpus's solves with curves took 688 s against 555 s before). In `METHOD_VERSION` 1.1.0 (unreleased).

9. **Assigned-flow node** (owner's PR #229, built as CLAUDE.md D12): a nodal demand in the GGA, never a fixed head. A part that no fixed head reaches holds assigned flows only if they sum to zero (floating, flagged); otherwise it is disconnected: the closed elements around it whose rules open as its level runs away are re-opened, and with none the solve is not converged, naming the nodes and why each element around them is closed. A flow control that alone feeds assigned flows follows its status rules (integrator's decision, replacing §4.8's earlier "a different setpoint has no solution"): an FCV open below its setpoint, a speed-controlled pump at a speed limit; no steady state above an FCV's setpoint or against a one-way element, and an equal setpoint over-controlled, both not converged and named. System curves bound the forced flow with the assigned flows by Gale's (1957) supply–demand condition, from above and from below (§5.6).

10. **Scenario override addressing** (was open item 4; built as CLAUDE.md D15): a field allow-list, not JSON Pointer paths. Every overridable value is named, typed and checked against its target's own Pydantic field and validators when the scenario is applied, and a pointer could have reached ids, ports or curve points. The list is PRD §3.8's, mapped onto the models (`models/scenarios.py`, published as `x-override-fields`, §5.7); pipe material, schedule, size and bore/roughness overrides are one `spec` value, the fluid is `fluid` (whole) or `fluid.temperature`, and an equipment item's rating is `rating` (whole) or one of its four values (D18). Adding a value is a one-line change to the list.

11. **Goal seek's search, caps and tolerances** (built as CLAUDE.md D16, design `docs/proposals/goal-seek.md`): every evaluation is the full solve of the case with the variables written on top; one variable by a 9-point scan and Brent's method (TSD's earlier sketch of bounds plus Brent found none of the second answers D13 asks to report), several by dogbox least squares in coordinates shifted to the start with goal seek's own forward-difference Jacobian; unusable trials are gaps or penalty residuals rather than failing the run (the earlier sketch's rule, replaced on measurement: failures come in regions a search can avoid); caps of 60 and 20(n + 1) evaluations inside the one 45 s budget; default tolerances from D6 with designers' floors for flow (10⁻⁶ m³/s) and velocity (10⁻³ m/s), and fixed smallest tolerances that do not depend on the fluid; at most one goal seek in the worker pool (§5.7).

12. **Export in the browser** (built as CLAUDE.md D17, design `docs/proposals/export.md`): SDD's `POST /api/v1/export` is dropped, not deferred: the files are made in the browser from the responses the page holds, so nothing is sent a second time and the server gains no path. Our own CSV, SpreadsheetML and ZIP writers on the bundled pako (fflate 0.8.3, MIT, the documented fallback behind the same interface), no Web Worker; one rule for values (Compare's, then convergence: a solve that did not converge gives no values); names from the project the results belong to, structure as solved; every row names its case, solve time and state; a lazily loaded chunk with an initial-download budget of 3 KB gzip (§8.3).

13. **Equipment pressure drop** (owner's request and answers of 2026-10-26, built as CLAUDE.md D18, design `docs/proposals/equipment-pressure-drop.md`): one component, `equipment`, for every passive element given by its datasheet, with no type field and no status; a required rating, a union of a rated point (pressure drop, flow and the rating fluid's density, all required: the owner chose two one-click density buttons over a water default) and a Cv or Kv (the owner's choice to include them now; a K needs its bore and stays Later); the constant-K law c·Q\|Q\| on the EGL, the rated drop being the loss of total pressure without the ports' static head (§4.9); viscosity not corrected, with reverse flow and laminar flow in a connected pipe flagged; every rating value in the scenario allow-list and a goal-seek variable, the whole rating not a variable; three goals and Compare rows; `METHOD_VERSION` 1.3.0; an exact valve-equivalence check over the corpus (`equipment_check`, §10.4) instead of a new fuzz profile, which stays Later until the element gains behaviour an open valve does not have.

**Open (Later):**

1. **Schematic layout algorithm:** dagre, elkjs, or custom?
2. **Version storage:** git under the hood, or custom versioning in PostgreSQL?
3. **Drooping pump curves (known v1 limitation):** a curve whose head rises from H₀(0) to a peak is accepted (v1 checks only that its flows increase; a speed-controlled pump's curve must also pass the ψ test, which makes the speed root unique, not the operating state), but the closing rule tests the head across the pump against s²·H₀(0) (EPANET 2.2 `pumpstatus`), not the curve's peak. A running state whose head lies between them is then not found: the pump is held at no flow (`PUMP_FLOW_REVERSAL`, invalid), or a speed-controlled pump at minimum speed cycles between N2 (closing against S_min) and C1 (re-opening against S_max) and the solve ends not converged (§5.4). EPANET 2.2 rejects such curves (error 227, invalid head curve). The owner decided on 2026-10-23 to keep this v1 behaviour, documented here, in D11 and in §5.4; the options for later are to reject such curves, or to close against s²·max H₀ (a method change for fixed pumps too).
4. **Three-way valve characteristic:** which published Cv-vs-position data (linear, equal-percentage, per path) to cite?
5. **Slow convergence of an active PRV whose outlet path loses about one velocity head (known v1 limitation):** the velocity head in an active PRV's setpoint head is taken from the previous iteration, which converges at about 1/r per iteration, r the loss beyond the outlet port in velocity heads of the outlet pipe. A PRV on a short spool with an exit into a tank, or a short spool into a tee and a main, can end not converged at the default 100 iterations although an active state exists; a higher `maxIterations` converges it, and the result is never a wrong converged state. An exact Newton step for this term (proposal `vfd-slice2-discharge-pressure.md` §2.2, §2.11) was designed and measured but shelved by the owner (2026-10-25, D13).

*End of TSD*
