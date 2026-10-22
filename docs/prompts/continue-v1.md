# Prompt: Continue OpenSolve Pipe after the v1 build

> Paste everything below the line into a fresh Claude Code session at the repository root.

---

You are continuing **OpenSolve Pipe**, a free, browser-based steady-state hydraulic network analysis tool. The v1 core analysis MVP (CLAUDE.md D5) was built from `docs/prompts/build-v1.md`. It is complete, verified and not yet deployed. Your job is to harden and extend it without ever trading correctness for scope.

## 1. Read first

1. `docs/GOALS.md`: the priority order (correctness → traceability → longevity → accessibility → privacy → usability → breadth) and the feature gates. Every judgment call starts here.
2. `CLAUDE.md`: decisions D1–D10. These record how v1 was actually built and why; treat them as binding.
3. `docs/TSD.md` §4–§5 and §10, and `docs/SDD.md` §4–§5. They describe the implementation as built.
4. `docs/prompts/build-v1.md` §2 (non-negotiables) and §5 (reference-suite rules). They still apply in full.

Precedence when documents disagree: GOALS → CLAUDE.md decisions → PRD → SDD → TSD. If a change contradicts a spec, update the spec in the same commit.

## 2. Where things stand

The history is one commit per milestone: M0 `879f537`, M1 `2f722bf`, M2 `56938ee`, M3 `240652f`, M4 `ca34178`, M5+M6 `2edfde3`, M7 `97232f9`. CI (`.github/workflows/ci.yml`: API, web, e2e and generated-type drift jobs) passed on every one of them.

Verified state at `97232f9`:

| Area | Result |
|---|---|
| API pytest | 2,034 passed; 96% coverage of `opensolve_pipe` |
| API ruff, ruff format, mypy strict | clean |
| Web svelte-check, Prettier + ESLint | clean |
| Web Vitest | 430 passed |
| Web Playwright (desktop 1280×800 and mobile 390×844) | 46 passed, 2 skipped by design |

**Reference suite** (`apps/api/tests/reference/`) has 65 cases: 59 closed-form, 6 run through EPANET 2.2 via WNTR 1.5.0. Every v1 component type and fluid has at least one case.
- Closed-form cases: worst deviation 9e-7 relative in flow and 3.7 µm in EGL.
- EPANET cases: worst deviation 0.084% in flow and 6.9 mm in EGL.

**Differential test:** 3,000 random water networks were compared with EPANET. All of them converge and pass an independent check of mass, energy and status rules. 2,808 agree within D6, the worst at 0.82 of the tolerance. The rest have more than one valid steady state, or EPANET gives no usable answer.

**Before changing anything, re-run every gate and confirm these numbers.**

```bash
cd apps/api && uv sync && uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv run python scripts/generate_pipe_data.py --check
cd ../web && pnpm install && pnpm gen:types && git diff --exit-code -- src/lib/api
pnpm check && pnpm lint && pnpm test && pnpm test:e2e
```

- If the Playwright browsers are preinstalled (`PLAYWRIGHT_BROWSERS_PATH` is set), never run `playwright install`. Playwright is pinned at 1.56.1, which matches Chromium build 1194.
- The e2e suite starts its own API on port 8010 and its own preview on port 4183, so dev servers on 8000 and 5173 can stay up.
- The interactive API docs are served only with `API_DOCS=1`.

## 3. Non-negotiables (unchanged from the build)

- **Never use a number you can't source.** Every coefficient, property and expected test value comes from one of three places: a library function you call and cite, a closed-form derivation written out in the test, or a WNTR/EPANET run. Never type a textbook or Crane value from memory. If a value can't be sourced, leave the feature out and say so.
- **Never weaken a test.** No loosened tolerances, skips or deleted assertions. Expected values are never computed with solver code; the reference suite imports only `opensolve_pipe.models`.
- **Units:** the model, API and solver are SI only. Pressures are gauge, with absolute used only where the physics needs it. Unit conversion happens only in the frontend.
- **Privacy:** no analytics, cookies or third-party requests. Project data travels only in the URL fragment and in request bodies, and is never logged.
- **Physics flags and traceability:** physics flags are on by default. Every result is traceable to its inputs, equations, correlations and cited data. A feature isn't done until its trace exists.
- **New component types** ship with at least one reference case.
- **Shared links must keep opening:** any breaking model change bumps `schemaVersion` and adds a frontend migration in `apps/web/src/lib/utils/migrations.ts`. Every released version keeps a fixture link in `utils/__fixtures__/` that must still decode and solve. That is tested by `tests/unit/test_released_links.py` and `tests/examples.e2e.ts`. Any change that can alter a solved result bumps `METHOD_VERSION` and adds a `METHOD_CHANGELOG` entry in `services/solver/version.py`.
- **Generated files are never edited by hand.** These are `apps/web/src/lib/api/{openapi.json,schema.d.ts}` (from `pnpm gen:types`), `data/pipe_materials.json` (from `scripts/generate_pipe_data.py`), and the reference case JSONs (from `python -m tests.reference.build_closed_form_cases` and `python -m tests.reference.generate_epanet_cases`). Model rules that JSON Schema can't express are published as `x-…` OpenAPI extensions and read by the web app (D10); never copy them by hand.

## 4. Verified library facts

Several of these were not obvious, so don't rediscover them. Re-verify any of them against the installed package docstrings or source before relying on it.

**fluids 1.3.1**
- `friction_factor()` switches hard to 64/Re at Re 2040. The solver uses its own regimes (`services/solver/friction.py`) and never calls it.
- The Crane tee and wye functions:
  - cover only a combined flow through a run port;
  - give K on the combined-flow velocity in the run diameter;
  - do no input validation;
  - are piecewise in the flow ratio q (steps at q = 0.4, 0.5 and 0.6) and discontinuous in angle (at 60° and 75°).
- No other tee correlation exists in `fluids`. Darby 3-K has single-path tee entries only.
- `material_roughness()` fuzzy-matches free text: "PVC" returns 0.0008 m. Never use it.
- `nearest_pipe(Di=…)` returns the next size up, not the nearest.

**CoolProp 8.0.0**
- `INCOMP::MEG` and `INCOMP::MPG` take a mass fraction from 0 to 0.6 and define no saturation pressure.
- Above the saturation temperature, water silently returns vapor properties. `services/fluids.py` handles this.

**EPANET 2.2 (WNTR 1.5.0)**
- g = 32.2 ft/s², which gives a 0.08% head-loss bias.
- The water viscosity VISCOS is 1.02193344e-6 m²/s.
- The minor-loss constant is rounded to 0.02517.
- Results come back as float32.
- WNTR takes D-W roughness in metres.
- Use GPM INP units and `accuracy=1e-5` with `headerror`/`flowchange`. `ACCURACY` below 1e-5 is silently clamped.
- Multi-point pump curves are piecewise linear, so use collinear points to match PCHIP.
- PRV and PSV settings are heads without velocity head; our setpoints are static pressures. `generate_epanet_cases.py` converts between them by iterating.

## 5. How to work

These methods made v1 trustworthy.

- **Split implementation from reference-writing.** For any solver or physics change, have one agent implement while a second, independent agent writes the reference cases from first principles without reading `services/`. Then integrate: on any mismatch, find the root cause, never the tolerance. Then run adversarial reviews (physics, and the reference suite's independence), then fix with a test that fails before the fix.
- **Re-run the differential test against EPANET after any status-logic change.** The v1 fuzzer was lost with the build container. Rebuild it from `tests/reference/generate_epanet_cases.py` and `tests/reference/free_levels.py`, and treat any converged result that fails the independent check as critical.
- **Use workflow agents carefully.** With 4 CPUs a workflow runs about 2 agents at a time. Give parallel agents disjoint directories, and tell them not to run `ruff format` or Prettier outside their own paths. If the usage limit stops a workflow, resume it with `resumeFromRunId`, but first check the tree, because a stopped agent may have left edits half done.
- **Commit one change set at a time, each with every gate green.** Use conventional-commit messages that state what was verified. Develop on the branch the session assigns, push only to it, never force-push, and open a PR only if asked.

## 6. Open work, in priority order

Pass each item through the GOALS §5 gates first, and stop to ask the owner where a choice is theirs to make.

1. **Deployment** (owner decision: pick hosts first).
   - Web: adapter-static, served from the domain root, with `PUBLIC_API_URL` set at build time.
   - API: uvicorn with `--proxy-headers` and `FORWARDED_ALLOW_IPS` set to the host's proxy range, so the per-client rate limit isn't shared by all users. Set `CORS_ORIGINS` and leave `API_DOCS` unset.
   - Write the hosting setup into TSD §11 and the README, and keep hosting cost near zero (GOALS §4.4).
2. **Tee and wye coverage.** Patterns where the combined flow passes through the branch currently use a Darby 3-K per-path fallback for tees, and wyes report not converged.
   - Implement a flow-split correlation (e.g. Idelchik, *Handbook of Hydraulic Resistance*; Miller, *Internal Flow Systems*) only from a source you actually have in hand. Encode it as cited, versioned data and give it reference cases. Otherwise leave it as it is.
   - Bump `METHOD_VERSION`.
3. **System-curve speed.** One 41-point curve takes about 3–4 s on a 99-component network.
   - Options: fewer or adaptive points, progressive rendering, or reusing the solve's factorization. Keep curve points exact solves; never interpolate between them silently.
4. **Long Crane-tee ladders.** Above about 800 components they can exceed the 45 s request budget. Profile `services/solver/status.py`'s hold/release passes.
5. **Reference case for the K step-hold.** Add a closed-form case where a Crane K is held at the mean across a correlation step; today that's covered by unit tests only.
6. **The "default" label.** A value equal to its documented default is labelled "default" even when the user typed it (D10). If the owner wants the distinction, it needs a model marker plus a schema migration.
7. **After that, deferred scope** (D5 list: VFD modes, HI viscosity correction, relief valves, export, and so on). Each item goes through the GOALS gates and the D5 order, one verified slice at a time, each with reference cases and traces.

## 7. Report

End every session with:
- the gate results, with counts;
- reference-suite changes and their worst deviations;
- anything left out or limited, and why;
- decisions recorded and spec changes made;
- known issues.

Report failures plainly, with their output. Don't describe anything as working that you haven't run.
