# History: where things stand

The record of what was built, in which merge, and the numbers the gates gave on the latest verified state. Append a line per merge (newest last in each session block) and replace the verified-state table when the gates are re-run on `main`. [`roadmap.md`](roadmap.md) holds what is still open.

The decisions are in [`decisions/`](decisions/README.md); the design of each feature and its as-built notes in [`proposals/`](proposals/README.md); the method versions in `apps/api/src/opensolve_pipe/services/solver/version.py`.


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
- pump groups (**D21**, #249, merged as `b407676`; `METHOD_VERSION` unchanged): the station that holds pumps run together, its duty and its group curve, `POST /api/v1/pump-group-curve` and the "Pumps together" card (slice 4a of `docs/proposals/pump-chart.md`, built from `docs/proposals/pump-groups.md`);
- the project library (**D22**, #253, merged as `86c40c3`; `METHOD_VERSION` 1.5.0): pipe specs and K, Cv or Kv entries with their sources, referred to by id from pipe segments, valves and inline fittings, built from `docs/proposals/project-library.md`;
- the pressure relief valve (**D23**, `METHOD_VERSION` 1.6.0), built on `b7f09eb` from `docs/proposals/pressure-relief-valve.md` (the owner's answers of 2026-10-28: the linear lift between set and full lift, flagged, shipped as an exception to GOALS §5's Verifiable gate that the owner accepted), then merged with `b407676` (`85fa1aa`: renumbered from D21 to D22, SDD §4.18, TSD §12 item 16) and reviewed with pump groups: a relief valve may sit inside a pump station (its set is a pressure difference), and the review's fixes (a duty without flow keeps the finder's order of S and D, null parallel shares there, the corpus check reads relief valves and orifice plates) are in its proposal's §12, items 53–54; then merged with `86c40c3` (`9c4b2a3`: the project library merged first, so the relief valve was renumbered from D22 to D23, `METHOD_VERSION` 1.5.0 to 1.6.0, SDD §4.19, TSD §4.12, TSD §12 item 17; item 55), and its proofs were run again on that merge against `86c40c3`, with the same counts.

Session 6 (2026-10-29 to 10-30):
- pump groups slice 4b (**D21**, #251, merged as `b067626`; `METHOD_VERSION` unchanged, 1.6.0): the group system curve, `curve: 'system'` of `POST /api/v1/pump-group-curve`, H_sys between the station's outer ports by the pump system curve's own code, on the "Pumps together" card with "Read along the curves"; reference cases PGS1–PGS12 (39 tests), 21 unit tests, the corpus comparison against `b407676` (5,168 identical, no ignores) and, after merging D22 and D23, against `83da77e` (5,189 identical), `pump_group_check` (t1)–(t4) 0 violations (1,001 stations, 800 group system curves with a duty, each of 4,547 pumps alone equal to its `/system-curve` at 49,384 points); proposal `pump-groups.md` §15 records the as-built departures;
- the documentation restructured for progressive disclosure (`0b7e26d`): `CLAUDE.md` 119 KB → 14 KB, the decisions in `docs/decisions/`, this file, `roadmap.md`, `workflow.md`, `library-facts.md`, `deployment.md`, the indexes, and `tests/unit/test_docs.py`; `scripts/record_history.py` refreshes the verified-state block below.

Session 7 (2026-10-30), web only:
- Build density (proposal `docs/proposals/build-density.md`, branch `web/build-density`; `METHOD_VERSION` unchanged): the Build forms measured at both sizes, six disciplines and a red team in `docs/proposals/build-density/`, the field registry (`apps/web/src/lib/utils/field-registry.ts`) with its schema guard, label/value rows, help on focus, one More disclosure per form, a 36/40 px Build control height, compact Build chrome, and `tests/build-density.e2e.ts` enforcing the budgets (core fields on a phone's first screen, chrome ≤ 15 % at 1280×800, edit action counts, axe-core); `docs/adding-a-field.md` for the next slice. Second session (2026-10-31): one label and unit table (scenario notes, goal seek and the export read the registry; the guard covers the allow-lists), a tighter header and compact scenario bar, 400 % zoom scrolling as a page, flags by shape, ports and fittings as rows, a solved pipe size on a phone's first screen. Third session (2026-10-31): adding a component in 2 actions ("Add now"), a two-value status in one tap (segments), a solved pump's first curve point on a phone's first screen, every port's elevation and a fitting's description editable, a boundary's round-off outflow shown as "≈ 0" by the solve's continuity tolerance, and the §3.4 inconsistencies decided. Web gates on the branch: svelte-check, Prettier and ESLint clean; Vitest 1621 passed (121 files); Playwright 202 passed, 14 skipped (per viewport), desktop and mobile. The API gates were not run (no API change).

<!-- verified-state:start -->
Verified state at `9e54d81` (`ccr-efab8cb5-vzm6cg`, 2026-10-30), written by `apps/api/scripts/record_history.py`:

| Area | Result |
|---|---|
| API pytest | 7153 passed |
| API ruff | clean |
| API ruff format | clean |
| API mypy strict | clean |
| API pipe data | clean |
| API relief data | clean |
| Web generated API types | clean |
| Web svelte-check | clean |
| Web Prettier + ESLint | clean |
| Web Vitest | 1576 passed (120 files) |
| Not run this time | Web Playwright (desktop 1280×800 and mobile 390×844, one worker) |
<!-- verified-state:end -->

The proof record below is written by hand with each merge (the script measures only the gates):

**Reference suite** (`apps/api/tests/reference/`): 163 cases, 142 closed-form and 21 run through EPANET 2.2 via WNTR 1.5.0, plus the metamorphic scenario and goal-seek files, the pump-group cases PG1–PG10 (D21) and the project library's tests (D22); 2,955 tests passed. Every component type, fluid and pump control state has at least one case.
- Closed-form cases: worst deviation 9e-7 relative in flow (`psv_open_pump_dead_headed`) and 3.7 µm in EGL (`twin_lines_crane_rung`), unchanged by D18 and D20 (the large-head round-off case agrees to one float64 step at 4·10⁹ m). The equipment cases agree to about 10⁻¹⁶ (Colebrook rated points), 10⁻¹⁰ (Cv and Kv: the suite's water against fluids' constant) and up to 2.8·10⁻⁷ in flow and 2·10⁻⁶ m in EGL (Swamee–Jain, the suite's form against EPANET's, D7). The fourteen closed-form orifice cases agree within 5.7·10⁻¹⁶ in flow and 5.3·10⁻¹⁵ m in EGL (the suite's own transcription of ISO 5167-2 eq. (4) equals fluids' within 10⁻¹³). The eighteen closed-form relief cases agree within 9.8·10⁻¹⁵ in flow and 8.5·10⁻¹⁴ m in EGL (the suite's own band root equals a 60-digit solve within 4·10⁻¹⁵; the solver reproduces the design's measured flows to the digits it prints them, within 3.5·10⁻¹³, their rounding).
- EPANET cases: worst 0.084% in flow and 16.4 mm in EGL on a 19.7 m head (EPANET's g = 32.2 ft/s² bias, 0.17 of the D6 tolerance); the three equipment cases differ by 4.2–4.5·10⁻⁴ in flow (the loop's bypass leg 4.16·10⁻⁴; EPANET's rounded minor-loss constant); the three orifice cases, each plate a GPV whose head-loss curve is its own law, by 1.2·10⁻⁵ to 3.15·10⁻⁴ in flow and up to 1.63 mm in EGL (the pipes' g bias, which the curve does not share); the three relief cases, each valve a GPV whose head-loss curve is its law behind a CV pipe, by 1.0·10⁻⁵ to 1.7·10⁻⁴ in flow.

**Differential test** (TSD §10.4): three profiles of 3,000 random networks against EPANET, `default` (seeds 0–2,999), `flow_control` (10,000–12,999) and `assigned_flow` (20,000–22,999), each with 0 critical seeds; the 1.2.0 class tables in TSD §10.4 are the baseline, and 1.3.0 (D18), 1.4.0 (D20), the project library's 1.5.0 (D22) and the relief valve (D23, measured as 1.5.0 before the library merged and as 1.6.0 on the merge `9c4b2a3`) each left all 9,000 records identical, as did pump groups (D21) and the merge of the relief valve with them. `equipment_check` (TSD §10.4) replaces every active isolation valve of the corpus by an equipment item of the same loss: 1,781 valves, 0 different. `orifice_check` replaces them by orifice plates of the same K, with an entered C (1,464 valves) and on ISO's Reynolds-dependent C (1,698 valves): 0 different, the largest differences 9.3·10⁻¹⁰ of the largest flow and 6.7·10⁻⁶ m. `relief_check` places relief valves on the corpus in three modes with exact answers (323 valves at partial lift, 420 beyond full lift, 803 set to stay closed): 0 different, the largest differences 1.05·10⁻⁹ of the largest flow and 4.47·10⁻⁶ m in the open modes, with projects at zero flow, at a switch or differing in which nodes have results listed and triaged (TSD §10.4). `pump_group_check` checks every group the suggestion rules give and every pair of pumps (4,235 groups, 537 stations) against a second station finder: 0 violations. `library_check` lifts every corpus project into the project library (95,559 pipe specs, 47,329 resistance entries) and solves it again: 0 different in both modes (mode `exact`, each K at its element's bore, bit for bit). The corpus is 5,189 projects.

**Before changing anything, re-run every gate and confirm these numbers:** `cd apps/api && uv run python scripts/record_history.py` runs them all and rewrites the block above ([`workflow.md`](workflow.md) §4; `--skip e2e` for a quick pass, `--dry-run` to print without writing).
