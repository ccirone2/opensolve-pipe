# Prompt: Build OpenSolve Pipe v1 in one run

> **Historical record.** This is the prompt v1 was built from (2026-10-21, milestones M0–M7). It is kept as the record of the build; its "decisions already made" (§3) and its reading list are superseded by `docs/decisions/` and `CLAUDE.md`, and its non-negotiables now live in `CLAUDE.md` (Rules) and `docs/workflow.md`. Do not paste it into a session; use `continue-v1.md`.

> Paste everything below the line into a fresh Claude Code session at the repository root.

---

You are building **OpenSolve Pipe v1** — a free, browser-based steady-state hydraulic network analysis tool — from an empty codebase, in one continuous run. The repository contains only specifications. Work autonomously through every milestone below; do not stop to ask questions. When a decision is genuinely ambiguous, make the choice that best follows `docs/GOALS.md`, record it (see *Recording decisions*), and continue.

## 1. Read first, in this order

1. `docs/GOALS.md` — mission, values, priority order, feature gates. This outranks everything else.
2. `CLAUDE.md` — rebuild decisions D1–D6, conventions, tooling, license.
3. `docs/PRD.md` — what to build. Build only items marked **v1**; everything marked **Later** is out of scope.
4. `docs/SDD.md` — architecture, data models, API contracts.
5. `docs/TSD.md` — stack, layout, the tested GGA solver sketch (§5.2), encoding code (§4.7), test strategy (§10).

Precedence when they disagree: GOALS → CLAUDE.md decisions → PRD → SDD → TSD. If you find a conflict, follow the higher document and fix the lower one in the same commit.

## 2. Non-negotiables

- **Correctness first.** Never trade it for scope, speed or polish. A smaller v1 that is verified beats a larger one that isn't.
- **No invented numbers.** Every coefficient, correlation, property value and expected test result must come from a source you actually have: a library function you call (and cite in code), a closed-form derivation written out in the test, or a WNTR/EPANET run. **Never type a "textbook" or "Crane example" value from memory.** If you can't source a value, leave the feature out and say so in the final report.
- **Never weaken a test to make it pass.** No loosened tolerances, skipped tests or deleted assertions. If a reference case fails, fix the code, or remove the feature from v1 and report it.
- **SI everywhere** in the model, API and solver; unit conversion only in the frontend (D4). Pressures are gauge; absolute only where physics needs it.
- **Privacy:** no analytics, tracking, cookies or logging of project contents. The project lives in the URL fragment (`/p#…`) and is never stored on the server.
- **Traceability is part of "done":** every solved element exposes the inputs, equations, correlations and data sources behind its result.
- **Physics flags on by default** (cavitation, flow reversal through a pump, outside a correlation's validated range, non-convergence). Design-practice checks are Later.
- Stay inside v1 scope (PRD §2.3). Do not build Later items, even partially.

## 3. Decisions already made for the open questions

These resolve TSD §12 so you don't have to. Implement them, then move each from "open" to "decided" in TSD §12 and add it to CLAUDE.md.

| Question | Decision |
|----------|----------|
| Tee/wye K-factors | Use the Crane TP-410 tee correlations implemented in `fluids.fittings`: `K_branch_diverging_Crane`, `K_run_diverging_Crane`, `K_branch_converging_Crane`, `K_run_converging_Crane`. Read their docstrings for argument meaning, reference velocity and validity range; flag results outside that range. Wyes use the same functions with the `angle` argument where supported; if a wye case isn't covered, leave wyes out of v1 and report it. |
| Fitting K-factors | Prefer the Crane functions in `fluids.fittings` (e.g. `ft_Crane`, `bend_rounded_Crane`, `K_gate_valve_Crane`, `K_ball_valve_Crane`, `K_swing_check_valve_Crane`) over hand-entered values. TSD §4.5 values become fallbacks only if a function doesn't exist. |
| Fluid properties | CoolProp: `Water` (IAPWS-95) for water; `INCOMP::MEG` and `INCOMP::MPG` for ethylene/propylene glycol solutions. Expose only the concentration and temperature ranges CoolProp supports for those fluids; cite the CoolProp fluid and its underlying reference in the data file and trace. Pin the CoolProp version. |
| Transition zone, 2000 ≤ Re < 4000 | Use EPANET 2.2's cubic interpolation between laminar and turbulent friction factors (Dunlop's method, as described in the EPANET 2.2 manual) and cite it. Flag results in this range as "transitional flow". |
| Pump curve fitting | Monotone piecewise cubic (`scipy.interpolate.PchipInterpolator`) through the user's points. Outside the curve's flow range, extrapolate linearly from the end segment and flag "operating outside the pump curve". Speed changes use the affinity laws. |
| Control-valve status oscillation | Cap the outer loop at 30 iterations; on oscillation return `converged: false` and name the oscillating components. |

## 4. Milestones

Work through these in order. Each milestone ends with all quality gates green (§6) and one commit. Do not start the next milestone with a red gate.

**M0 — Scaffolding**
- `apps/api`: uv project, Python 3.12, `src/` layout, FastAPI, Pydantic v2, NumPy, SciPy, `fluids`, CoolProp; dev: pytest, ruff, mypy, httpx, WNTR. `license = "AGPL-3.0-or-later"`, `license-files = ["LICENSE"]` (copy the root LICENSE into `apps/api/`).
- `apps/web`: SvelteKit 2 + Svelte 5 (runes), TypeScript, Tailwind, Vitest, Playwright, ESLint, Prettier, pako, Chart.js; pnpm; `"license": "AGPL-3.0-or-later"`.
- `.github/workflows/ci.yml` running every gate in §6 for both apps.
- `/health` endpoint and a placeholder home page, both tested.

**M1 — Data model**
- Pydantic models for everything in SDD §4 that is in v1 scope, with camelCase JSON aliases, SI field docs and physical bounds. `schemaVersion = 1`; `methodVersion` from a single constant in the solver package.
- Generate the frontend TypeScript types from the FastAPI OpenAPI schema (e.g. `openapi-typescript`) with a script; do not hand-write duplicates.

**M2 — Solver core**
- Start from the tested GGA sketch in TSD §5.2. Generalize it to a link protocol returning `(h, dh/dQ)`; move to `scipy.sparse` when it's simple to do so.
- Network builder (TSD §5.1): port graph → solver nodes and links; topology validation with clear `TOPOLOGY_ERROR` messages.
- Pipes with fittings, reservoirs, ideal reference nodes, plugs.
- Reference suite infrastructure (TSD §10.1) with first cases: single pipe (closed-form), series and parallel pipes (closed-form), reservoir-to-reservoir, and two looped water networks compared to WNTR/EPANET (solver in `swamee_jain` mode).

**M3 — Components and fluids**
- Pumps (fixed speed, on/off, affinity laws), isolation valves, check and stop-check valves, PRV/PSV/FCV with status logic, tees and wyes with the outer K-factor loop (TSD §5.3–5.4).
- Cv/Kv → K conversion (TSD §5.3), with a unit test against Crane's formula.
- Fluids: water, MEG, MPG via CoolProp; user-defined fluids.
- NPSH available and margin (TSD §5.5); standard atmosphere from site elevation.
- Reference cases for every component: closed-form where possible (e.g. pump on a single pipe: solve the pump curve and system curve intersection independently in the test), WNTR/EPANET for water networks with pumps, PRVs, PSVs and FCVs.

**M4 — API, traceability and flags**
- `POST /api/v1/solve`, `POST /api/v1/system-curve`, `GET /api/v1/fluids`, `GET /api/v1/fluids/{id}/properties`, `POST /api/v1/fluids/custom` per SDD §5. 422 for topology errors via an exception handler.
- Per-element trace in `SolvedState`: inputs used, equations (as text), correlation names, data sources, intermediate values (Re, f, K, velocity). Design the shape, then document it in SDD §4.10.
- Methods-and-assumptions summary for the whole solve.
- Physics flags (§2).

**M5 — Frontend core**
- Project state in `.svelte.ts` modules with undo/redo.
- URL fragment encoding exactly as TSD §4.7 (canonical JSON, pako, base64url), migrations module, fixture link for schema v1, 8,000-character warning.
- Unit conversion (TSD §6) with SI/Imperial/mixed preferences; gauge labels.
- Panel navigator walking the port graph (SDD §3.1.1, TSD §8.1): component and connection panels, path chooser at branches, breadcrumb, add before/after, add branch, delete.

**M6 — Results and sharing**
- Results tables (nodes, links, pumps, valves, branches) in display units.
- Pump curve with system curve and operating point (Chart.js).
- Trace view per element and the methods summary.
- Physics flags shown inline.
- Share button (copy link), new link on every edit, reopening a link restores the project.
- About/disclaimer text from README ("engineering aid… without warranty").

**M7 — End-to-end and finish**
- Playwright flows at desktop (1280×800) and mobile (390×844) viewports: build a pump system → solve → read results → share → reopen link → same results. Plus a gravity-fed branched network and a topology-error case.
- Update README development instructions to match reality; update the specs wherever implementation forced a change.

## 5. Reference suite rules

- Each case is a JSON file: project, expected results, and a `source` field saying exactly where the expected values came from (the derivation in the test file, or "WNTR <version> EpanetSimulator").
- Closed-form expected values are computed in the test from first principles, independent of solver code. Never compute expected values with the solver.
- Pass criteria (D6): flows, heads and pressures within 0.5% or 0.01 m head, whichever is looser; mass balance closes at every node.
- Every v1 component type has at least one case. A component without a passing case is not in v1.

## 6. Quality gates (run before every commit)

```bash
# apps/api
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy src            # strict for opensolve_pipe

# apps/web
pnpm check && pnpm lint && pnpm test
pnpm test:e2e              # from M7, or earlier once flows exist
```

If Playwright browsers are preinstalled in the environment (e.g. `PLAYWRIGHT_BROWSERS_PATH` is set), use them; do not run `playwright install`.

## 7. Recording decisions

- Architectural choices (anything another developer would need to know): add to CLAUDE.md's decisions section with a one-line rationale tied to GOALS.
- Spec changes forced by implementation: edit the spec in the same commit.
- Library data: cite the source next to the value, in code or the data file.

## 8. Git

- Work on a branch named `build/v1` (create it from the current branch).
- One commit per milestone, conventional-commit style (`feat(api): …`, `feat(web): …`), message stating what was verified.
- Push the branch at the end. Do not push to `main`, force-push, or open a pull request.

## 9. Final report

End with a report containing:

1. Milestones completed, with gate results (test counts, coverage, lint and type-check status).
2. The reference suite: number of cases per component type, worst-case deviation per comparison source.
3. Every v1 feature you left out or limited, and why (e.g., no citable data).
4. Every decision you recorded, and every spec change you made.
5. Known issues and suggested next steps.

Report failures plainly with output. Do not describe anything as working that you have not run.
