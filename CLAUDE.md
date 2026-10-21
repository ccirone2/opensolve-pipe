# OpenSolve Pipe — Claude Context Guide

Free, browser-based tool for steady-state hydraulic analysis of pressurized pipe networks. No install, shareable by URL, equal priority on desktop and mobile.

**Status:** Fresh rebuild. The repo currently holds only the specs; no application code yet.

---

## Source documents and precedence

| Doc | Role |
|-----|------|
| `docs/GOALS.md` | Mission, values, priority order, feature gates — read first for any judgment call |
| `docs/PRD.md` | What to build and for whom |
| `docs/SDD.md` | Architecture, data models, API contracts |
| `docs/TSD.md` | Concrete stack, file layout, code sketches |

The specs are at v0.2.0 (rebuild baseline) and reflect the decisions below. Items marked **Later** are outside v1. Code samples are sketches, except those the TSD marks as tested.

**Precedence when they disagree:** `docs/GOALS.md` → this file's *Rebuild decisions* section → PRD → SDD → TSD. If a spec conflicts with a decision below, follow the decision and update the spec in the same change.

**Priority order for trade-offs** (GOALS §3): correctness → traceability → longevity → accessibility → privacy → usability → breadth.

---

## Rebuild decisions (override the specs)

### D1. Solver: own Python network solver
- Implement a Global Gradient Algorithm (Todini–Pilati, the method EPANET uses) in `apps/api`, with Darcy–Weisbach + Colebrook friction from the `fluids` library.
- One solver for every topology (single-path, branching, looped). The TSD's separate "simple solver" and WNTR wrapper (TSD §5) are dropped.
- The solver must handle what EPANET cannot: flow-split-dependent tee/wye K-factors, real fluid properties (density, viscosity, vapor pressure), check valves and other valves as components, and NPSH available. Later: VFD setpoint control, relief valves.
- Gravity-fed and pressure-fed systems with no pump are valid inputs.
- Every network, including closed loops, needs at least one fixed-pressure boundary (reservoir or ideal reference node). Report a topology error when one is missing.
- WNTR/EPANET is a **test-only** dependency, used as a reference for water-only cases.

### D2. Data model: port graph is canonical
- Components have typed ports, and `PipeConnection`s are edges between two ports (SDD §4.2). `Project` has `components[]` and `connections[]`.
- The "component chain" (`upstreamPiping`, `downstreamConnections`, the legacy `Connection` type) is **removed**.
- The panel navigator derives Prev/Next by walking the graph from a chosen start component. At a branch it asks the user which path to take, and the breadcrumb records the path taken.
- `Project` carries an integer `schemaVersion`. Shared URLs live forever, so the decoder upgrades old versions through ordered migrations. Never break decoding of a released version.

### D3. Sharing: URL fragment only in v1
- The encoded project goes in the URL fragment: `https://opensolve-pipe.app/p#<encoded>`. The fragment is never sent to the server, so project data is never logged.
- Encoding: canonical JSON → gzip (pako) → base64url, no padding.
- v1 has no accounts, no database and no server-side storage. History is in-browser undo/redo plus the URLs a user keeps.
- Warn when the encoded URL exceeds 8,000 characters; some chat and email clients truncate long links.
- Deferred: short links, accounts, branch and merge (PRD §4.4–4.5, SDD §3.2.3).

### D4. Units: SI everywhere internally, gauge pressure at the edges
- Project data is stored in SI (m, m³/s, Pa, K, kg/m³, Pa·s). Unit preferences only affect input and display; changing them never changes stored values. This replaces "in project units" throughout SDD §4 and TSD §4.
- Users enter and see pressures as **gauge**. Each project has a `siteElevation` (m), from which atmospheric pressure is computed with the standard atmosphere and can be overridden. The solver uses absolute pressure wherever physics needs it (NPSH, vapor-pressure checks).
- Elevations are measured from a single project datum.

### D5. v1 scope: core analysis MVP
**In v1:**
- Branching and looped networks
- Reservoir, ideal reference node, tee, wye, plug/cap
- Pipes with fittings
- Fixed-speed pumps (on/off)
- Isolation valves (gate, ball, butterfly, globe) and check valves
- PRV, PSV and FCV
- Water, ethylene/propylene glycol and user-defined fluids
- NPSH available and margin
- Panel navigator, results tables and the pump/system curve chart
- URL sharing

**Deferred:** VFD and controlled-pressure/controlled-flow pump modes; HI viscosity correction; relief valves; non-ideal reference nodes; cross and elbow-branch fittings; tanks with levels; sprinklers, orifices, heat exchangers, strainers and user-defined elements; fuels in the fluid library; the auto-generated schematic; CSV/XLSX/PNG export; table entry and CSV pump-curve import; design checks; cost estimation.

### D6. Correctness: reference test suite
- `apps/api/tests/reference/` holds benchmark cases: Crane TP-410 and textbook worked examples, closed-form hand calculations, and EPANET runs for water-only networks.
- Pass criteria: flows, heads and pressures within 0.5% of the reference, or 0.01 m of head, whichever is looser. Mass balance must close at every node to the solver tolerance.
- Any change to solver or loss-coefficient code must keep the whole suite green. A new component type ships with at least one reference case.

### D7. Solver formulation (M2)
- The nodal unknown is the **energy grade line** (EGL = z + p/ρg + v²/2g), so pump head and fitting losses enter exactly; HGL and static pressure are derived with the velocity in the connected pipe. Reservoirs and reference nodes are quiescent boundaries (v = 0). EPANET neglects velocity heads, so EPANET comparisons compare our EGL with its heads. *(Correctness; GOALS §4.1.)*
- Transition zone 2000 ≤ Re < 4000: EPANET 2.2's Dunlop cubic (Hermite in Re/2000 between laminar and the turbulent formula in use), flagged `TRANSITIONAL_FLOW`. `swamee_jain` mode uses EPANET's exact 5.74/Re^0.9 form so EPANET tests compare network algorithms, not friction formulas.
- Branch legs are imposed exactly as head offsets on a merged head unknown, not iterated with a Jacobian floor (a floor stalled Newton on large mains feeding small tubing).
- Unknown pipe materials, schedules or sizes are topology issues, reported together with the other topology problems.

### D8. Cited data only (M2)
- Pipe dimensions come from `fluids.piping` (ASME B36.10M, B36.19M, ASTM D1785) and roughness from Farshad & Rieke (2006) via `fluids`, generated into `data/pipe_materials.json` by a script. Materials without both cited dimensions and roughness (HDPE, ductile iron) are not in v1; users can enter a custom pipe. Never use `fluids`' fuzzy free-text roughness lookup. *(GOALS §4.1.)*
- Fitting K values come from one named `fluids.fittings` Crane function per fitting type (`data/fittings.json`); a user K overrides it and is labeled as user data.

---

## Open spec items

The specs (v0.2.0) reflect D1–D6. These items are still open; see TSD §12 for the full list.

- **Tee and wye K-factors (TSD §4.2):** being implemented in M3 with the Crane TP-410 correlations in `fluids.fittings`. Never use a loss coefficient without a cited source.
- **EPANET comparisons (TSD §5.2, §10.1):** EPANET's friction formula (Swamee–Jain) differs from exact Colebrook by up to 3.0% in f (measured), so EPANET reference tests run the solver with `frictionMethod = "swamee_jain"`.

---

## Planned layout

```
apps/
  api/   FastAPI backend (Python, uv)   src/opensolve_pipe/{routers,services/solver,models,data,utils}
  web/   SvelteKit frontend (pnpm)      src/lib/{components,stores,models,utils,api}
docs/    PRD, SDD, TSD
```

Add directories when the code that needs them lands; don't scaffold empty ones.

---

## Tooling

| Area | Choice |
|------|--------|
| Python | 3.12, managed with **uv** (`uv sync`, `uv run …`); commit `uv.lock` |
| Python quality | ruff (lint + format), mypy (strict on `opensolve_pipe`), pytest |
| Frontend | SvelteKit 2 / Svelte 5 runes, TypeScript, Tailwind, **pnpm** |
| Frontend quality | ESLint, Prettier, `svelte-check`, Vitest, Playwright |
| Infra | None until needed: no Turborepo, Docker, Postgres or Redis in v1 |

Commands, once the apps exist:

```bash
# backend
cd apps/api && uv sync
uv run uvicorn opensolve_pipe.main:app --reload --port 8000
uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy src

# frontend
cd apps/web && pnpm install
pnpm dev                                   # http://localhost:5173
pnpm test && pnpm check && pnpm lint
```

---

## Conventions

- Backend calculates in SI only. Convert units in the frontend at input/display, never inside the solver.
- Pydantic models are the API source of truth. Generate frontend types from the OpenAPI schema rather than hand-writing duplicates.
- Hydraulic data (pipe schedules, roughness, K-factors, fluid properties) lives in versioned JSON under `apps/api/src/opensolve_pipe/data/`, with a source citation per entry.
- Results-first UI: always solve. Flag physically invalid results by default (cavitation, pump flow reversal, outside a correlation's range, non-convergence); design-practice checks are opt-in (GOALS §4.6).
- Traceability: every result must be traceable to its inputs, equations, correlations and cited data (GOALS §4.2). A feature isn't done until its traceability output exists.
- No analytics, tracking or cookies; never log project contents (GOALS §4.5).
- AI-written code meets the same bar as any other: hydraulic correctness is proven by the reference suite, not by review alone (GOALS §7.2).
- Keep it simple: build the v1 scope (D5) before anything deferred.

---

## License

The project is licensed **AGPL-3.0-or-later** (full text in `LICENSE`). Use that exact SPDX identifier everywhere license metadata is declared:

- `apps/api/pyproject.toml`: `license = "AGPL-3.0-or-later"` and `license-files = ["LICENSE"]` (PEP 639; copy or symlink the root `LICENSE` into `apps/api/`)
- `apps/web/package.json`: `"license": "AGPL-3.0-or-later"`

Check new dependencies for licenses compatible with AGPL-3.0 before adding them.
