# Prompt: Continue OpenSolve Pipe after the v1 build

> Paste everything below the line into a fresh Claude Code session at the repository root.

---

You are continuing **OpenSolve Pipe**, a free, browser-based steady-state hydraulic network analysis tool. The v1 core analysis MVP (CLAUDE.md D5) was built from `docs/prompts/build-v1.md`. It is complete and verified, and deployed by the owner (2026-10-25; not a stable release, D14). Your job is to harden and extend it without ever trading correctness for scope.

## 1. Read first

1. `docs/GOALS.md`: the priority order (correctness → traceability → longevity → accessibility → privacy → usability → breadth) and the feature gates. Every judgment call starts here.
2. `CLAUDE.md`: decisions D1–D22. These record how v1 was actually built and why; treat them as binding.
3. `docs/TSD.md` §4–§5 and §10, and `docs/SDD.md` §4–§5. They describe the implementation as built.
4. `docs/prompts/build-v1.md` §2 (non-negotiables) and §5 (reference-suite rules). They still apply in full.

Precedence when documents disagree: GOALS → CLAUDE.md decisions → PRD → SDD → TSD. If a change contradicts a spec, update the spec in the same commit.

## 2. Where things stand

The history is one commit per milestone: M0 `879f537`, M1 `2f722bf`, M2 `56938ee`, M3 `240652f`, M4 `ca34178`, M5+M6 `2edfde3`, M7 `97232f9`. After v1: `f1ada11` (this prompt), `cd715ba` (solver speed with bit-identical results; the step-hold reference case), `95effa5` and `239dd40` (the differential test and corpus comparison moved into the repo, then hardened after an adversarial review), the VFD design proposal in `docs/proposals/` (`15dbd1a`), then speed-controlled pumps slice 1 (`0fbe7cc` model contract, `35bbcff` feature and deployment preparation, `ff9a8f3` fixes from a six-dimension adversarial review plus an outer-loop oscillation fallback) and `f65b8c6` (the e2e suite in one worker: two workers raced into the API's one-solve-per-client rule). CI (`.github/workflows/ci.yml`: API, web, e2e and generated-type drift jobs) passed on each of them except `239dd40`, whose e2e failure was that race.

Session 3 (2026-10-23 to 10-25) added, each with every gate green and CI passing:
- `f9d402b`: the API image built and run locally (TSD §11.2);
- `b9b997f`: the owner's decisions on TSD §12's open items (a flow setpoint no speed can hold is `CONTROLLED_PUMP_SETPOINT`; system curves solved again from other starts, with truthful messages; drooping curves kept) and Cancel for solves and curves in the web app;
- `a805821`: the e2e suite against `apps/api/tests/e2e_app.py`, the app with its rate limit raised (CI hit 429);
- `d78a8ef`: the assigned-flow node, added to v1 by the owner (D12);
- `e6845f1`: corpus tools (`compare.py --within-tolerance`, `corpus.py --solver-options`);
- `7d5338a`: METHOD_VERSION 1.2.0 (a round-off-aware energy stop test and the `NOT_CONVERGED` flag rule) and **D13**, the owner's same-answer rule;
- design records, not built: `docs/proposals/vfd-slice2-discharge-pressure.md` (slice 2 and C1, shelved by D13).

Session 4 (2026-10-25 to 10-26) added, each from a design proposal in `docs/proposals/` with its as-built record:
- `4ccdf9f`: **D14**, deployed is not stable;
- `3eaf6ca`: the scenario manager (D15); `6d60ad4` and `e0dff4b`: the API offers the source of the commit it runs (AGPL-3.0 §13);
- `d700ba1`: goal seek (D16); `7babcc6`: a valve resistance the solver cannot represent is a topology issue;
- `490e057`: system-curve reasons and topology issues in names and display units;
- `bbafbff`: export (D17);
- the UI/UX refinement PRs (proposal `ui-ux-refinement.md`): results near the top (#231), results in context in Build (#235), the Summary and sortable tables (#236), the splitter (#238), the breadcrumb (#242), and `1b9e7ec` (#241: a solve's connection values read on the connection as it is now);
- `3da03c1` (#240): the fuzz check that a pump or valve without a result has none by the documented rule;
- the equipment pressure-drop element (**D18**, `METHOD_VERSION` 1.3.0), built on `3da03c1` from `docs/proposals/equipment-pressure-drop.md` (`2014c6e`, #245).

Session 5 (2026-10-26 to 10-28) added, each from a design proposal in `docs/proposals/` with its as-built record:
- the pump chart's panels (#239, merged on 2026-10-26) and curve facts (#244: best efficiency point, shutoff head, rising head, speed range; proposal `pump-chart.md`);
- opt-in design checks (**D19**, #247, merged as `b6e2088`; `METHOD_VERSION` unchanged): NPSH margin, the pump's operating region with its manufacturer data, pipe velocity;
- the orifice plate (**D20**, `METHOD_VERSION` 1.4.0, #248), built on `b6e2088` from `docs/proposals/orifice-plate.md`;
- the pressure relief valve (**D22**, `METHOD_VERSION` 1.5.0), built on `b7f09eb` from `docs/proposals/pressure-relief-valve.md` (the owner's answers of 2026-10-28: the linear lift between set and full lift, flagged, shipped as an exception to GOALS §5's Verifiable gate that the owner accepted).

Verified state with the pressure relief valve (D22):

| Area | Result |
|---|---|
| API pytest | 6,482 passed |
| API ruff, ruff format, mypy strict, pipe data, relief data | clean |
| Web svelte-check, Prettier + ESLint | clean (764 files) |
| Web Vitest | 1,298 passed (99 files) |
| Web Playwright (desktop 1280×800 and mobile 390×844, one worker) | 163 passed (the three `relief` flows on each), 7 skipped by design (each a check for the other viewport) |

**Reference suite** (`apps/api/tests/reference/`): 163 cases, 142 closed-form and 21 run through EPANET 2.2 via WNTR 1.5.0, plus the metamorphic scenario and goal-seek files; 2,673 tests passed. Every component type, fluid and pump control state has at least one case.
- Closed-form cases: worst deviation 9e-7 relative in flow (`psv_open_pump_dead_headed`) and 3.7 µm in EGL (`twin_lines_crane_rung`), unchanged by D18 and D20 (the large-head round-off case agrees to one float64 step at 4·10⁹ m). The equipment cases agree to about 10⁻¹⁶ (Colebrook rated points), 10⁻¹⁰ (Cv and Kv: the suite's water against fluids' constant) and up to 2.8·10⁻⁷ in flow and 2·10⁻⁶ m in EGL (Swamee–Jain, the suite's form against EPANET's, D7). The fourteen closed-form orifice cases agree within 5.7·10⁻¹⁶ in flow and 5.3·10⁻¹⁵ m in EGL (the suite's own transcription of ISO 5167-2 eq. (4) equals fluids' within 10⁻¹³). The eighteen closed-form relief cases agree within 9.8·10⁻¹⁵ in flow and 8.5·10⁻¹⁴ m in EGL (the suite's own band root equals a 60-digit solve within 4·10⁻¹⁵; the solver reproduces the design's measured flows to the digits it prints them, within 3.5·10⁻¹³, their rounding).
- EPANET cases: worst 0.084% in flow and 16.4 mm in EGL on a 19.7 m head (EPANET's g = 32.2 ft/s² bias, 0.17 of the D6 tolerance); the three equipment cases differ by 4.2–4.5·10⁻⁴ in flow (the loop's bypass leg 4.16·10⁻⁴; EPANET's rounded minor-loss constant); the three orifice cases, each plate a GPV whose head-loss curve is its own law, by 1.2·10⁻⁵ to 3.15·10⁻⁴ in flow and up to 1.63 mm in EGL (the pipes' g bias, which the curve does not share); the three relief cases, each valve a GPV whose head-loss curve is its law behind a CV pipe, by 1.0·10⁻⁵ to 1.7·10⁻⁴ in flow.

**Differential test** (TSD §10.4): three profiles of 3,000 random networks against EPANET, `default` (seeds 0–2,999), `flow_control` (10,000–12,999) and `assigned_flow` (20,000–22,999), each with 0 critical seeds; the 1.2.0 class tables in TSD §10.4 are the baseline, and 1.3.0 (D18), 1.4.0 (D20) and 1.5.0 (D22) left all 9,000 records identical. `equipment_check` (TSD §10.4) replaces every active isolation valve of the corpus by an equipment item of the same loss: 1,781 valves, 0 different. `orifice_check` replaces them by orifice plates of the same K, with an entered C (1,464 valves) and on ISO's Reynolds-dependent C (1,698 valves): 0 different, the largest differences 9.3·10⁻¹⁰ of the largest flow and 6.7·10⁻⁶ m. `relief_check` places relief valves on the corpus in three modes with exact answers (323 valves at partial lift, 420 beyond full lift, 803 set to stay closed): 0 different, the largest differences 1.05·10⁻⁹ of the largest flow and 4.47·10⁻⁶ m in the open modes, with projects at zero flow, at a switch or differing in which nodes have results listed and triaged (TSD §10.4). The corpus is 5,189 projects.

**Before changing anything, re-run every gate and confirm these numbers.**

```bash
cd apps/api && uv sync && uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv run python scripts/generate_pipe_data.py --check && uv run python scripts/generate_relief_data.py --check
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
- **Shared links must keep opening, from the first stable release (D14: the app is deployed but not stable, so until the owner declares a release the model may change without migrations, and the schema-v1 fixture follows the model):** then any breaking model change bumps `schemaVersion` and adds a frontend migration in `apps/web/src/lib/utils/migrations.ts`. Every released version keeps a fixture link in `utils/__fixtures__/` that must still decode and solve. That is tested by `tests/unit/test_released_links.py` and `tests/examples.e2e.ts`. Any change that can alter a solved result bumps `METHOD_VERSION` and adds a `METHOD_CHANGELOG` entry in `services/solver/version.py`.
- **Generated files are never edited by hand.** These are `apps/web/src/lib/api/{openapi.json,schema.d.ts}` (from `pnpm gen:types`), `data/pipe_materials.json` (from `scripts/generate_pipe_data.py`), `data/api526_orifices.json` (from `scripts/generate_relief_data.py`), and the reference case JSONs (from `python -m tests.reference.build_closed_form_cases` and `python -m tests.reference.generate_epanet_cases`). Model rules that JSON Schema can't express are published as `x-…` OpenAPI extensions and read by the web app (D10); never copy them by hand.

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
- **Re-run the differential test against EPANET after any status-logic change:** `uv run python -m tests.differential.fuzz 0 3000 --workers 3` (about 3 minutes on 4 CPUs), then `python -m tests.differential.stats <out dir>`. Any critical seed (a converged result that fails the independent checks) is a bug; the class table at `95effa5` is in TSD §10.4.
- **Prove that a speed or refactoring change leaves results unchanged:** dump the corpus with the code before and after (`tests.differential.corpus`, from a `git worktree` of the old commit and from the working tree) and compare them (`tests.differential.compare`): every reported value must be identical. If a value changes, it is a method change: bump `METHOD_VERSION` and say why in `METHOD_CHANGELOG`. TSD §10.4 has the exact commands.
- **Use workflow agents carefully.** With 4 CPUs a workflow runs about 2 agents at a time. Give parallel agents disjoint directories, and tell them not to run `ruff format` or Prettier outside their own paths. If the usage limit stops a workflow, resume it with `resumeFromRunId`, but first check the tree, because a stopped agent may have left edits half done.
- **Commit one change set at a time, each with every gate green.** Use conventional-commit messages that state what was verified. Develop on the branch the session assigns, push only to it, never force-push, and open a PR only if asked.

## 6. Open work, in priority order

Pass each item through the GOALS §5 gates first. **Apply D13 (the same-answer rule) to every solver change: never take a question about zero-flow labels, iteration paths or convergence-level differences to the owner.** Ask the owner only about product choices: what to build, and behaviour a user would see.

1. **Deployment: done by the owner (2026-10-25)** on Cloudflare Pages and Google Cloud Run (TSD §11; §11.4 lists the checks to run after each deployment). It is not a stable release (D14): until the owner declares one, the model, links, API and methods may change without migrations.
2. **Tee and wye coverage:** blocked on a source the owner supplies (Idelchik's AEC translation and Bassett et al. 2001 are not readable here; Gardel 1957, *Bulletin technique de la Suisse romande* 83, is on e-periodica behind a human-verification page, and may cover only the patterns already built).
3. **Next feature: the owner's choice.** The scenario manager (D15), goal seek (D16), export (D17), the equipment element (D18), design checks (D19), the orifice plate (D20) and the liquid pressure relief valve (D22) are built. Candidates, in the PRD's order: HI viscosity correction (needs a source in hand), equipment's Later items (`docs/proposals/equipment-pressure-drop.md` §9: a K on a stated diameter, a head or mass-flow rating, a pressure-drop curve, a viscosity correction, which needs geometry or a cited correlation per type, and an `equipment` fuzz profile once the element gains behaviour an open valve does not have), the orifice plate's Later items (`docs/proposals/orifice-plate.md` §9: other plate types, nozzles and venturis, a low-Reynolds-number C, which needs a cited correlation over the β range, choked flow and an incipient-cavitation design check, gases, a Cv or Kv on the orifice), the relief valve's Later items (`docs/proposals/pressure-relief-valve.md` §9: balanced-bellows and pilot valves, which need level-dependent status rules; pop action and blowdown, whose second steady state D13 requires to be reported; a manufacturer's lift or pressure–flow curve; API 520's Kv, Kw and Kc and non-certified valves, each once read in API 520; relief design checks, each once its standard is read; gas, steam and two-phase relief; the check valve's cracking pressure on the static difference, a method change with its D13 corpus cost), and goal seek's Later items (PRD §3.9; `docs/proposals/goal-seek.md` §10: saved setups, a start value, more goals, a coefficient select, more than one goal seek in the pool). Each ships as one verified slice with reference cases and traces.
4. **Shelved (D13):** speed-controlled pumps slice 2 (discharge pressure) and C1 (an exact Newton step for an active PRV's velocity-head term). Their design and measurements are in `docs/proposals/vfd-slice2-discharge-pressure.md`; the owner's answers there are provisional notes. Revisit with a simpler design under D13 if the owner asks for slice 2 again. The PRV slow lag is TSD §12's open item "Slow convergence of an active PRV" (open item 5).
5. **Decided and done:** the owner's TSD §12 decisions of 2026-10-23 (setpoint rule, system curves, drooping curves kept, Cancel); the "default" label rule (D10); the scenario manager (D15); goal seek (D16, TSD §12 item 11); export (D17, TSD §12 item 12; its by-hand checks, TSD §10.3: the workbook in Excel for Android and the chart image on Android are recorded, the rest is still to do); the equipment element (D18, TSD §12 item 13; `goal_seek_check` for 1.3.0 over the whole corpus: 5,151 projects, 15,405 goal seeks, 0 violations); design checks (D19); the orifice plate (D20, TSD §12 item 14; `goal_seek_check` for 1.4.0 over the whole corpus: 5,166 projects, 15,462 goal seeks, 0 violations); the pressure relief valve (D22, TSD §12 item 16; `goal_seek_check` for 1.5.0 over the whole corpus: 5,189 projects, 15,558 goal seeks, 0 violations).
6. **Known gaps, closed:** a pump or valve reported without a result must have none by the documented rule (`checks.missing_result_problems`, measured by `missing_result_check.py`, TSD §10.4); the pump chart words system-curve messages with names and display units (`utils/system-curve-text.ts`).

## 7. Report

End every session with:
- the gate results, with counts;
- reference-suite changes and their worst deviations;
- anything left out or limited, and why;
- decisions recorded and spec changes made;
- known issues.

Report failures plainly, with their output. Don't describe anything as working that you haven't run.
