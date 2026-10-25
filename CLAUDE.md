# OpenSolve Pipe — Claude Context Guide

Free, browser-based tool for steady-state hydraulic analysis of pressurized pipe networks. No install, shareable by URL, equal priority on desktop and mobile.

**Status:** v1 (core analysis MVP, D5) is implemented: `apps/api` (FastAPI, own GGA solver, reference suite) and `apps/web` (SvelteKit). Not yet deployed.

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
- Every network, including closed loops, needs at least one fixed-pressure boundary (reservoir or ideal reference node). Report a topology error when one is missing. Assigned-flow nodes fix a flow, not a pressure, so they never count as that boundary.
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
- Reservoir, ideal reference node, assigned-flow node (fixed demand or supply), tee, wye, plug/cap
- Pipes with fittings
- Fixed-speed pumps (on/off), and speed-controlled pumps holding a flow setpoint (D11, slice 1)
- Isolation valves (gate, ball, butterfly, globe) and check valves
- PRV, PSV and FCV
- Water, ethylene/propylene glycol and user-defined fluids
- NPSH available and margin
- Panel navigator, results tables and the pump/system curve chart
- URL sharing

**Deferred:** speed-controlled pumps holding a discharge pressure (slice 2) or a differential pressure (slice 3), suction-pressure control, remote control nodes, mass-flow setpoints, overspeed, sleep at low demand, lead/lag stations and reduced-speed efficiency corrections (D11); HI viscosity correction; relief valves; three-way valves; the differential-pressure mode for control valves; scenario manager; goal seek; non-ideal reference nodes; cross and elbow-branch fittings; tanks with levels; sprinklers, orifices, heat exchangers, strainers and user-defined elements; fuels in the fluid library; the auto-generated schematic; CSV/XLSX/PNG export; table entry and CSV pump-curve import; design checks; cost estimation.

### D6. Correctness: reference test suite
- `apps/api/tests/reference/` holds benchmark cases: Crane TP-410 and textbook worked examples, closed-form hand calculations, and EPANET runs for water-only networks.
- Pass criteria: flows, heads and pressures within 0.5% of the reference, or 0.01 m of head, whichever is looser. Mass balance must close at every node to the solver tolerance. A speed-controlled pump's speed (D11) must be within 0.5% (relative) of the reference, and the head it implies, s²H₀(Q/s), within 0.01 m of the reference head.
- Any change to solver or loss-coefficient code must keep the whole suite green. A new component type ships with at least one reference case.

### D7. Solver formulation (M2)
- The nodal unknown is the **energy grade line** (EGL = z + p/ρg + v²/2g), so pump head and fitting losses enter exactly; HGL and static pressure are derived with the velocity in the connected pipe. Reservoirs and reference nodes are quiescent boundaries (v = 0). EPANET neglects velocity heads, so EPANET comparisons compare our EGL with its heads. *(Correctness; GOALS §4.1.)*
- Transition zone 2000 ≤ Re < 4000: EPANET 2.2's Dunlop cubic (Hermite in Re/2000 between laminar and the turbulent formula in use), flagged `TRANSITIONAL_FLOW`. `swamee_jain` mode uses EPANET's exact 5.74/Re^0.9 form so EPANET tests compare network algorithms, not friction formulas.
- Branch legs are imposed exactly as head offsets on a merged head unknown, not iterated with a Jacobian floor (a floor stalled Newton on large mains feeding small tubing).
- Unknown pipe materials, schedules or sizes are topology issues, reported together with the other topology problems.
- **Stop test and flag (METHOD_VERSION 1.2.0, change set C0b):** a link's energy residual passes at 10⁻⁷ m + 4ε·max(\|H_start\|, \|H_end\|, \|h\|), ε = 2⁻⁵², since 10⁻⁷ m alone is below one unit in the last place of heads from 2²⁹ m and inner solves at large heads stalled at that round-off floor; the `NOT_CONVERGED` flag names a residual's location only where that residual exceeds its stop tolerance, and where the status updates keep returning to a failed state it reports the residuals of the solve its message describes (proposal `vfd-slice2-discharge-pressure.md` §2.11.10; TSD §5.2, §10.4). *(Correctness and traceability; GOALS §3, §4.2.)*

### D8. Cited data only (M2)
- Pipe dimensions come from `fluids.piping` (ASME B36.10M, B36.19M, ASTM D1785) and roughness from Farshad & Rieke (2006) via `fluids`, generated into `data/pipe_materials.json` by a script. Materials without both cited dimensions and roughness (HDPE, ductile iron) are not in v1; users can enter a custom pipe. Never use `fluids`' fuzzy free-text roughness lookup. *(GOALS §4.1.)*
- Fitting K values come from one named `fluids.fittings` Crane function per fitting type (`data/fittings.json`); a user K overrides it and is labeled as user data.

### D9. Component models (M3; resolves TSD §12)
- **Tees and wyes:** Crane TP-410 correlations in `fluids.fittings` (`K_branch/run_diverging/converging_Crane`) on the combined-flow velocity. They cover only a combined flow through a run port: a tee with the combined flow through its branch uses Darby 3-K "Tee, through-branch (as elbow)" per path and is flagged; a wye in that pattern has no cited correlation and is reported as not converged. The wye's lateral leans toward `outlet_1`. `lossModel: 'ideal'` gives EPANET-style junctions. *(GOALS §4.1: no uncited K.)*
- **Fluids:** CoolProp 8.0.0 (pinned): `Water` (IAPWS-95), `INCOMP::MEG`/`INCOMP::MPG` (Melinder 2010) within CoolProp's queried ranges. Glycols have no vapor pressure in CoolProp, so NPSH needs a user value (flagged otherwise).
- **Pump curves:** monotone piecewise cubic (`scipy.interpolate.PchipInterpolator`), straight end-slope extrapolation (flagged), affinity laws for speed. No viscosity correction (Later); the trace states it.
- **Valves:** default K from the Crane function for the valve type at the inlet pipe's diameter; Cv/Kv via `fluids` (ISA-75.01.01). No position-dependent K and no control-valve Cv curve in v1 (no cited characteristic); control valves default to ideal (zero loss when wide open). PRV/PSV setpoints are static pressures at the valve port.
- **Status logic:** EPANET 2.2 rules translated to EGL, at most 30 outer iterations that change statuses or branch K (iterations that only hold or release a zero-flow tee leg are bounded separately), oscillation → `converged: false` naming the components. Deliberate departures from EPANET: an FCV closes on reverse flow and opens when the head across it is below its fully open loss; closed elements around a closed-off section are re-tested (difference constraints) so a pump and check valve that close together can reopen.

### D10. API, traceability and limits (M4, M7)
- Every solved element carries a trace (inputs with their source, equations, correlations and data sources with citations, intermediates, notes stating the inequality that set its state); a methods-and-assumptions summary accompanies every solve. A value equal to a field's documented default is labeled "default". *(GOALS §4.2.)*
- A section with no path to a fixed head but with a running pump circulates: it is solved with an arbitrary reference head and reported with flows and head differences only, flagged `UNDETERMINED_PRESSURE`. PRV/PSV flows are coupled exactly in the Newton step (no lag).
- Solves run in a small worker pool (one solve per client at a time, bounded queue → 503 `SERVER_BUSY`) with a 45 s budget per request; abandoned requests are cancelled. The web app's Cancel, on a running solve and on a system curve being computed (PRD §4.2), aborts the request and says so; what was shown before stays, labelled current or out of date as before, and a late answer is dropped. Responses are gzip-compressed. *(Accessibility at near-zero hosting cost, GOALS §4.4.)*
- Privacy: request bodies are never logged; the access log drops query strings and client addresses; request-validation errors (`VALIDATION_ERROR`) never echo submitted values (SDD §5.1.2), while fluid-range, topology and not-found errors name the value or id at fault so it can be fixed (responses go only to the requester and are never logged). The interactive API docs (`/docs`, `/redoc`) load assets from third-party CDNs, so they are served only with `API_DOCS=1` (development); the schema is always at `/openapi.json`. The web app sends project data (fluid included) only in request bodies: `POST /api/v1/fluids/properties` takes a `FluidDefinition`; the `GET /fluids/{id}/properties?…` form stays for API users, though intermediaries may log its query. *(GOALS §4.5.)*
- System curves on demand (M7): the 41-point curves of every pump cost a solve per point and break the PRD §4.2 solve times, which a plain solve meets. The web app solves with `includeSystemCurve: false`; the pump chart fetches the curve of the pump being viewed from `POST /api/v1/system-curve`, for the exact project that was solved, one request at a time, cached with that solve and dropped by the next. It shows the loading state (with Cancel), failures, cancellations and points without a head; a curve is never shown with another solve's results. Every point whose forced flow passes with a determined head reports it (owner's decision 2026-10-23): a point that has no head after its warm start, while the flow has a way through, is solved again from the initial state and from it with the active control valves open, the first head found, or the finding that a control valve in series is at its switch, being used (with none, its first result is kept), unless its flow exceeds what every way between the pump's sides can pass that way (a cut of FCVs at their setpoints and one-way elements against the flow: no steady state carries it); a point at that limit is also solved with each FCV of the cut held open, to find whether it is at its switch; a point without a head says whether the flow has no way through, no steady state carries it, its head is undetermined (a side on a free level, or a control valve in series at its switch) or its solve did not converge (TSD §5.6). Every pump's trace defines the system curve (H_sys), and the chart says how the curve shown was computed and links to that trace. *(Usability without trading correctness, GOALS §3.)*
- Boundaries add no entrance or exit loss unless the connection has an entrance or exit fitting; the methods summary and each reservoir and reference-node trace say so, with the web app's default fittings at reservoirs (sharp entrance, exit). Traces, flags and topology issues number a connection's pipes and fittings from 1, as the app does; data indexes (`pipeIndex`, `segmentIndex`, `fittingIndex`) stay 0-based. *(GOALS §4.2.)*
- Model rules JSON Schema cannot express are published from the Pydantic models as OpenAPI extensions (`x-port-ids`, `x-port-roles`, `x-port-count`, `x-required-parameters`, `x-reducer-types`, `x-entrance-types`, `x-exit-types`, `x-setpoint-bounds`, `x-ordered-fields`); the web app reads them, with the schema's bounds, from the generated `openapi.json` (`utils/model-rules.ts`) instead of copying them, and an API test fails while that copy is stale.
- Topology problems are 422 with every issue listed; validation and fluid-range errors 400; all errors share one envelope.

### D11. Speed-controlled pumps (VFD), slice 1: flow setpoint
Design and owner's answers: `docs/proposals/vfd-pump-modes.md`.
- **Model.** `Pump.control = {mode: "flow", setpoint, minSpeed}`; omitted means fixed speed. The setpoint is the volumetric flow through the pump, suction → discharge, 0 < Q_set ≤ 100 m³/s. For a controlled pump `speed` is the maximum speed (≤ 1). `minSpeed` is required, with no default, and `minSpeed < speed` is a model rule (400) published as `x-ordered-fields`. *(GOALS §4.1: no tool or paper cites a default minimum speed; §4.2: the field's meaning is stated, not inferred.)*
- **Solve.** F(s, Q) = s²H₀(Q/s) rises with speed on [s_lo, speed], s_lo = max(minSpeed, Q_set/x_mono) (below `speed`: see the setpoint rule under *Uniqueness*). While a speed there holds Q_set, F(s_lo, Q_set) − Htol ≤ EGL_d − EGL_s ≤ F(speed, Q_set) + Htol, the pump is a fixed-flow link (EPANET 2.2's "pump of a specific flow": a demand at the suction, a supply at the discharge), and its speed is recovered afterwards as the unique root of F(s, Q_set) = EGL_d − EGL_s on [s_lo, speed] by Brent's method. This is exact: the speed enters only the pump's own head equation. s_lo exceeds minSpeed only when Q_set/minSpeed lies beyond x_mono on the curve's end tangent, where head falls as speed rises: no stable flow controller holds that stretch. There, for a head at Q_set between F(s_lo, Q_set) and F(minSpeed, Q_set), the pump at minSpeed passing more than Q_set is a steady state too (a drive saturated at its minimum); the solve starts active and does not leave that state for a head in that band. A setpoint with Q_set/`speed` itself beyond x_mono is rejected (*Uniqueness*): no speed in the range would be on a rising stretch, and two limit states (max_speed by rule A1, and minSpeed passing more than Q_set) could both satisfy the rules, so the result would depend on the solve's path. *(GOALS §4.1: exact, and checkable in closed form and by EPANET.)*
- **Uniqueness.** A controlled pump's curve must have ψ = 2H₀ − xH₀′ > 0 on [0, x_last], checked exactly on the PCHIP pieces; otherwise `CONTROLLED_PUMP_CURVE` (422). On a curve that passes, a setpoint Q_set ≥ `speed` × x_mono (x_mono: twice the flow at which the curve's falling end tangent reaches zero head; infinite, so never reached, when the end tangent does not fall) is `CONTROLLED_PUMP_SETPOINT` (422, with every other issue; owner's decision 2026-10-23), as is Q_set/x_mono ≥ `speed`, the same test in quotient form, so that s_lo < `speed` in floating point too. Drooping curves that pass are accepted. The test guarantees a unique speed root (one speed per head at a flow), not a unique operating state: on a drooping curve the limit rules close the pump against s²H₀(0), as v1 closes a fixed pump, so a running state with a head above that is not found (no flow, flagged invalid; or, at minSpeed, not converged). EPANET 2.2 rejects such curves (error 227); the owner kept this v1 behaviour, documented (2026-10-23, TSD §12). *(GOALS §3: a speed that is not unique would be an arbitrary answer.)*
- **Limits.** Above the band the pump runs as the fixed-speed pump at `speed` (the link's own law, bit-identical), below it at `minSpeed` (a per-solve `LinkState.law` override), and it keeps running at low demand (no sleep). The setpoint is then not held: `PUMP_SETPOINT_NOT_MET` (info). At zero flow it closes and re-opens as the fixed-speed pump at `speed`. Re-solved as that fixed pump, a network gives the same result where it has one steady state that satisfies every rule; where it has several (v1's zero-flow multiplicity, D9), the two solves may reach different ones, since their iterations differ (proposal §7.3, M1). *(GOALS §4.6: a pump at a limit is a valid state, flagged as information.)*
- **Status rules.** A0 (starved → maximum speed), A1/A2 (Htol band on F(s_max, Q_set) and F(s_lo, Q_set)), X1/N1 (back to regulating once the flow reaches the setpoint, EPANET 2.2 fcvstatus), X2/N2/C1 (EPANET 2.2 pumpstatus at the limit speed). They compare flows and head differences only, so the closed-off and floating-section logic applies unchanged; the fallbacks add a minimum-speed step between open and closed, and valve-only networks keep the v1 option sequence. Two flow controls in series holding the same flow (equal setpoints, the pressure between them undetermined) are reported as not converged, naming them, with a message that says the pressure between them is undetermined (over-controlled) whether the solve ends at a limit carrying the setpoint or with statuses cycling. No new tolerance: Htol and Qtol. *(GOALS §3: correctness over convergence.)*
- **Results and traces.** `PumpResult.speed` is the speed the pump runs at, and curve, range, efficiency (plain affinity, η₀(Q/s), no Sârbu–Borza correction), NPSHr and power are at that speed; `PumpResult.control` gives the mode, setpoint, state (active, max_speed, min_speed, no_flow, off) and whether the setpoint is achieved. The trace states the inequality that set the state, the speed root and its residual, s_lo, x_mono and the uniqueness margin; the methods summary describes speed control only when a project uses it. *(GOALS §4.2.)*
- **System curves.** The viewed pump's control is replaced by the fixed flow (H_sys as for any pump); other controlled pumps that are on keep regulating, and warm starts carry their statuses; the default range uses `speed` (the maximum). *(GOALS §4.2: one definition of H_sys.)*
- **Versions.** `schemaVersion` stays 1 (nothing deployed before slice 1); `METHOD_VERSION` 1.1.0, whose changelog says that the flows, heads, pressures, statuses and speeds of projects without speed control are unchanged, proven by the corpus comparison (TSD §10.4: every such value identical, with `pumpResults.*.control` null or absent, `compare --ignore-null`); their methods summary changes in the sentence on the outer loop's new oscillation fallback, which can also let a solve that did not converge before converge (none in the corpus or the fuzz), and in the Pumps section's system-curve item, which every summary has (with a pump or not) and whose references gain Ford–Fulkerson (the owner's system-curve decision, D10). The owner's decisions of 2026-10-23 (the setpoint rule above, and system-curve points solved again from other starts, D10) are in the same unreleased 1.1.0, each with a changelog line. *(GOALS §4.3: a controlled-pump result names a method version that has speed control.)*

### D12. Assigned-flow node
Added to v1 by the owner (PR #229; D5). Specs: SDD §4.11, TSD §4.8.
- **Model.** `AssignedFlow`, type `assigned_flow`, one port `port_1`, a required `flow` in m³/s within ±100 (D11's flow bound): positive is a demand leaving the network, negative a supply entering it. It has no default flow, and `flow = 0` behaves exactly as a plug. `schemaVersion` stays 1 (an additive type, nothing deployed). *(GOALS §4.1: no source cites a default flow.)*
- **Solve.** The port is a free node whose demand is the flow, entering the GGA's continuity rows as a `FIXED_FLOW` link's demand and supply do. It is never a fixed head, so D1's boundary rule holds, and `NO_FIXED_HEAD` says why. A dead-end branch to a nonzero flow carries it.
- **No steady state.** A part that no fixed head reaches can hold assigned flows only if they sum to zero (to the continuity tolerance); it then floats (flows solved, `UNDETERMINED_PRESSURE`). Otherwise it is disconnected (EPANET's "system disconnected"): it is left out of the inner solve, and the closed elements around it whose rules open as its level runs away (down with a net demand, up with a net supply) are re-opened. With none to open, the solve is not converged, naming the nodes with their flows and each element closed around them with the reason: the user's status, a side with no fixed head, or its rule.
- **Flow controls feeding assigned flows.** The status rules decide, as D11 does for two flow controls in series. This corrects the first text of TSD §4.8 (PR #229), which said that any different setpoint has no solution: the independent reference cases derive a valid steady state for an FCV set above the demand and for a flow-controlled pump fed another flow. An FCV fed less than its setpoint ends fully open (`CONTROL_VALVE_SETPOINT_NOT_MET`), and a speed-controlled pump fed another flow runs at its maximum or minimum speed (`PUMP_SETPOINT_NOT_MET`). More than an FCV's setpoint, or reverse flow through an FCV or pump, has no steady state; an equal setpoint is over-controlled. Both end not converged, naming the control and the nodes, whichever path the solve takes. *(GOALS §3: correctness over convergence.)*
- **System curves.** `flow_limit` counts assigned flows as fixed supplies and demands (Gale 1957: a flow exists only if no node set holds more net supply than its cut passes), which bounds the forced flow from above and, where only the pump can feed a demand or drain a supply, from below: points outside the bounds have no steady state and are not solved again. A pump side that reaches only assigned-flow nodes has no point with a head: the one flow they fix leaves its head undetermined.
- **Traceability.** The port has a node result like any port (EGL, HGL, static and absolute pressure, `BELOW_VAPOR_PRESSURE`), and the boundary result's outflow is −flow. The trace gives the flow with its sign convention and the continuity at the port. The methods summary mentions assigned flows only when a project has one (EPANET, Gale). *(GOALS §4.2.)*
- **Versions and proof.** Added in `METHOD_VERSION` 1.1.0 (unreleased), with a changelog line: projects without assigned-flow nodes are unchanged in every solved value, trace, message and system-curve point (corpus comparison against `c03217c`: 4,120 projects identical, 0 different, no ignores; TSD §10.4). Reference: 12 closed-form cases, 2 EPANET cases and 18 scenario tests; fuzz profile `assigned_flow` (TSD §10.4). *(GOALS §4.3.)*

### D13. Same answer, different answer (owner, 2026-10-25)
- **Two results are the same answer** when every flow, head and pressure agrees within D6's tolerance (0.5 % or 0.01 m of head, whichever is looser). Below that, differences are not regressions and need no owner decision: iteration counts and paths, convergence-level noise, and which state label (closed, open, isolated, no flow) an element carrying zero flow gets, or which of several such zero-flow states a solve reports.
- **What matters is a significantly different solution:** two valid states whose flows, heads or pressures differ beyond D6. Where the solver finds one it says so (not converged, naming the elements, as D11 does for over-control). Finding every such state is not a v1 goal.
- **Accepting a solver change:** the reference suite green (D6); in the corpus and the three fuzz profiles 0 critical seeds and no converged solve left not converged; every other value within D6 of the previous version or changed only at zero flow; anything beyond that named and explained in `METHOD_CHANGELOG`. No change-specific acceptance criteria are negotiated with the owner. *(GOALS §3: correctness is about answers, not labels.)*
- **Shelved by this rule (2026-10-25):** C1 (an exact Newton step for an active PRV's velocity-head term) and its redesign, kept in `docs/proposals/vfd-slice2-discharge-pressure.md` §2.2 and §2.11 as a record (the slow lag is TSD §12 open item 6); and slice 2 itself: that proposal's design and the owner's answers to its §13 questions are provisional notes, not decisions, to be revisited with a simpler design under this rule.

---

## Spec notes

The specs reflect D1–D13; TSD §12 lists the decided implementation questions and the open (Later) ones.

- **EPANET comparisons (TSD §5.2, §10.1):** EPANET's friction formula (Swamee–Jain) differs from exact Colebrook by up to 3.0% in f (measured), so EPANET reference tests run the solver with `frictionMethod = "swamee_jain"`.

---

## Layout

```
apps/
  api/   FastAPI backend (Python, uv)   src/opensolve_pipe/{routers,services/solver,models,data}
                                        tests/{unit,reference}   scripts/
  web/   SvelteKit frontend (pnpm)      src/lib/{api,components,state,utils,testing}   tests/ (Playwright)
docs/    GOALS, PRD, SDD, TSD, prompts/
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
| Infra | None until needed: no Turborepo, Postgres or Redis in v1; Docker only for the API's Cloud Run image (`apps/api/Dockerfile`, TSD §11.2) |

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
