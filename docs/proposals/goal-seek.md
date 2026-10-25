# Goal seek: design proposal

**Status: design, not built** (2026-10-25; becomes CLAUDE.md D16). This design was written on 2026-10-25 against `e0dff4b` (D14) by a design workflow. Three designers worked from different angles: one on the model and API, one on the numerics (with measurements), and one on the web UX (with layout measurements). A synthesizer merged their designs into this one, checked every disputed claim against the code, and ran the checks marked **S** in §3.11. §1.3 lists where the designs disagreed and why this design chose as it did. Two reviewers (numerics, and web and API) then raised 23 issues; a reviser checked each against the code and by experiment (rows marked **R** in §3.11) and revised the design. §11 lists every issue, its verdict and what changed.

The owner said "Go" to goal seek on 2026-10-25. It moves from Deferred into v1. The owner and the workflow had already decided these points, which were not re-opened:
- **Variables.** The variables are the numeric values of the scenario allow-list (D15), addressed exactly as scenario overrides are (target + field). User bounds lie within each field's own bounds.
- **Goals.** There are as many goals as variables (PRD §3.9).
- **Evaluations.** Every evaluation is the full network solve, never an approximation.
- **Unreachable targets.** An unreachable target gives the closest achievable value, with the goal flagged as not met. It is never clamped silently.
- **The model.** The result never changes the model. The user applies the values to the base or to a scenario.
- **The case.** Goal seek runs on the base or on a scenario (`scenarioId`). Its variables are written on top of that scenario's values.
- **The solver.** Nothing under `services/solver/` changes, and every solve stays bit-identical (a corpus comparison proves it).
- **Requests.** One goal seek is one request in the existing worker pool, under the one 45 s budget, cancelled by the web's existing Cancel.
- **Privacy** as D10: bodies are never logged, `VALIDATION_ERROR` never echoes a value, and errors name ids.
- **Traceability** (GOALS §4.2): every evaluation is recorded, the method is named and cited, and the result states the tolerances and why the search stopped.
- **Other rules.** Desktop and mobile are equal (GOALS §4.7). Generated files are never hand-edited (`pnpm gen:types`). No test is weakened.

Every other choice in this document is the designers' own. Each is a simple default chosen to serve working engineers, reversible under D14, and not escalated to the owner. §1.2 marks the origin of each, and §10 lists those the owner may want to revisit.

Sources:
- PRD §2.3, §2.4, §3.8, §3.9; SDD §3.2.1, §4.12, §4.13, §5.1; TSD §5.7, §10.1, §10.4, §12; GOALS §3, §4.2, §4.3, §4.7; CLAUDE.md D5, D6, D10–D15; `docs/proposals/scenario-manager.md`.
- Code read: `models/{scenarios,components,fluids,piping,results,api,base}.py`, `services/scenarios.py`, `services/solver/{__init__,budget,methods,trace,version}.py`, `routers/solve.py`, `workers.py`, `middleware.py`; web `state/{project,workspace}.svelte.ts`, `components/{workspace,results,ui}/*`, `utils/{compare,scenarios,model-rules,schema-bounds,units,results}.ts`, `api/client.ts`.
- The designers' prototypes and logs are in the design workflow's scratchpad (`goalseek/design-{api,numerics,web}/`, not committed). Numerics: `scan.py`, `strategies.py`, `strategies_n*.py`, `prototype*.py`, `timing.py`, `budget.py`, `fd_noise.py`, `determinism.py`, `closed_form_check.py`. API: `proto_gs.py`, `corpus_gs.py`, `time_solves.py`, `bitident.py`. Web: `proto-fit*.mjs`, `header-fit.mjs`, `example-scan.mjs`.

---

## 1. Scope and decisions

### 1.1 Scope

This slice builds PRD §3.9:
- **Variables and goals.** The user picks 1 to 4 **variables**: numeric inputs from the scenario allow-list, each with lower and upper bounds. The user picks as many **goals**: a result of an element, each with a target and a tolerance.
- **The search.** `POST /api/v1/goal-seek` finds the variable values that bring the goals to their targets. Every evaluation is a full solve of the case (the base, or a scenario) with the variables written on top. The response lists every evaluation, the values found, each goal's achieved value, residual and met status, why the search stopped, and the full solved state at the values found.
- **Applying.** The web shows the result and lets the user apply the exact values to the case it ran on, or as a new scenario, as one undo step.

**Not in this slice (Later, §10):**
- A goal-seek setup saved in the project or the link.
- A user-given start value, and a user-set evaluation limit.
- Streamed progress during a run.
- Goals on network extremes (lowest pressure, highest velocity), absolute pressure, HGL and EGL, efficiency, power and statuses.
- Applying a scenario run's values to the base.
- A global or multi-start search for several variables.
- More than 4 variables.

### 1.2 Decisions

Origin key:
- **O**: decided before design (the owner's "Go" and the workflow's decided list).
- **A**: API designer.
- **N**: numerics designer.
- **W**: web designer.
- **S**: synthesizer, either resolving a disagreement or adding what the designs missed.
- **R**: reviser, after the design review (§11; the issue's id in brackets).

| # | Decision | Reason | Origin |
|---|---|---|---|
| 1 | Variables are the numeric values of the scenario allow-list, addressed as overrides are (target + field). User bounds lie within each field's own bounds. | Decided before design. One list for scenarios and goal seek (D15 decision 13). | O |
| 2 | The variable fields: reservoir `liquidLevel` and `surfacePressure`; reference-node `pressure`; assigned `flow`; pump `speed` and `control.setpoint`; control-valve `setpoint`; a valve's `resistance` (one flow coefficient); a pipe's `length`; `fluid.temperature`. Every `status`, a pipe's `spec` and the whole `fluid` are not variables (`NOT_VARIABLES`, each with its reason). The variable tables are derived from the allow-list, and a test fails when the allow-list gains a numeric value that the variable list lacks. | Every allow-list entry whose value is a number. A status is discrete, a spec is a library choice replaced as a group, and a fluid is an object. | A |
| 3 | A resistance variable names its `coefficient` (`K`, `Cv` or `Kv`). It writes `resistance = {kind: coefficient, value: x}`, whatever the case holds. The web sends the kind the case's valve has, or K when the valve has no resistance (its default: Crane's K for an isolation or check valve, ideal, K = 0, for a control valve). | "What Cv passes 20 L/s?" is the sizing question. A valve on its default has no number to vary. What is applied is a plain scenario `resistance` value. | A (field), W (kind), R (W-R8: a control valve's default is ideal) |
| 4 | Bounds are required, finite SI numbers with `lower < upper`. There is no start field. The search starts at the case's value, clipped into the bounds. A resistance that the case holds in another form (its default, or another kind) starts at the middle of its bounds on its scale (x at u = 1/2, §3.1). | "From my current design" is what the user asks. The web has no use for a start; the API designer's optional start is a reversible addition (§10). | A (bounds), S (no start) |
| 5 | Before any solve, each bound is written into the case (the other variables at their starts) and the project is validated. A field bound or an object rule (`minSpeed < speed`, the FCV range) gives 400 at `body.variables.{i}.lower` or `.upper`, with the schema's message. Every model rule on these values bounds one value, so these 2n checks prove that every trial in the box validates, and §3.1's map never leaves the box. A topology or fluid error at a trial value (`CONTROLLED_PUMP_SETPOINT` at a low speed, a temperature beyond CoolProp's range) is not a request error: that trial is unusable, and the search goes around it. | The field's own validators enforce "within each field's own bounds": one mechanism. Measured: failures form regions at the ends of the range (99 of 1,204 scans), and searches with a failed point were still met (§3.11). A 422 at a bound would make the user find the limit by hand. | N, A (pre-check), S (box argument); R (N-N1: the map) |
| 6 | Each variable is searched in a scaled coordinate u ∈ [0, 1]: linear in x, except `length` and `resistance`, which are linear in log x (both are > 0 by their field bounds). The map back to x is exact where it matters: u = 0 gives `lower`, u = 1 gives `upper` and the start's u gives the start's own x, bit for bit; every other trial is clamped into [lower, upper] (§3.1). | A 9-point scan of a K over [0.01, 10⁵] needs log spacing. The API designer's linear-versus-log comparison measured Brent alone, without a scan. The plain formula leaves the box: at u = 1 a log map gives 10000000.000000006 for an upper bound of 10⁷, which the field rejects (R, §3.11). | N, over A; R (N-N1, W-R3: the exact map) |
| 7 | Goals are 11 results, named as Compare rows name them (D15): a port's static pressure; a connection's flow, largest velocity and head loss; a pump's flow, head, NPSHa and NPSH margin; a valve's flow and pressure drop; a reservoir's or reference node's outflow. A goal is `{quantity, elementId, portId?, target, tolerance?}`, with snake_case API names mapped 1:1 to Compare's ids. Each reads one published `SolvedState` field. | One vocabulary in the app for "a result of an element": the picker, labels, units and readers already exist and are tested. The value achieved is the value the results tables show. | W (catalogue), A (fields), S (names) |
| 8 | At most 4 variables, and as many goals. | PRD §3.9. Measured up to n = 4: cost grows about linearly, and singular problems grow more common. | O, A, N |
| 9 | The default tolerance is max(0.5 % × \|target\|, floor). The floors are ρg × 0.01 m for pressures (ρ of the case fluid at its own temperature, fixed before the search); 0.01 m for head loss, pump head and NPSH; 10⁻⁶ m³/s for flows; 10⁻³ m/s for velocity. A user tolerance must be > 0 and at least max(10⁻⁶ × \|target\|, the quantity's minimum): 0.1 Pa for pressures, 10⁻⁵ m for heads, 10⁻⁹ m³/s for flows, 10⁻⁶ m/s for velocity (`x-goal-quantities`). | D6 and D13: within D6, two results are the same answer. The floors keep a target of zero meetable (measured: zero-flow targets met with \|Q\| ≤ 8×10⁻⁹ m³/s). D6 has no flow floor of its own, so the flow and velocity floors are designers' defaults, and the methods text says so. The minimum stays far above the measured noise (≤ 6×10⁻⁹ of a default tolerance). It is a fixed number per quantity (a thousandth of the floor, with ρg taken as 10⁴ N/m³ for pressures), so the web checks it at the field before Run. | A, N; R (W-R15: no density in the minimum; W-R10: sources) |
| 10 | A goal is **met** when \|achieved − target\| ≤ its tolerance at the reported evaluation. The search stops at the first evaluation where every goal is within a tenth of its tolerance. It stops at once when the start already meets every goal. | Measured: with the margin, 362 of 364 met values stay met when rounded to 6 significant digits, for about one more solve. A start that meets a goal is the same answer (D13): nothing to change. | N (margin), A (met), S (start) |
| 11 | **One variable.** Solve the start, then always a 9-point scan of the bounds. A scan point within a tenth of the tolerance ends the search (the one nearest the start). Otherwise, run Brent's method (`brentq`, xtol 10⁻¹⁰ of the range) in the bracket nearest the start; if it ends at a jump or an unsolved crossing, try the next bracket. With no bracket, report the closest value: at a bound, on a plateau, or refined by `minimize_scalar` (bounded). | Measured on 360 reachable targets: all met, median 10 solves (p90 11, max 16). The scan finds 15 of the 16 problems with more than one answer; bounds plus Brent finds 0 of them in a median 4 solves. Trying the next bracket is the synthesizer's addition: a crossing nearest the start that is a jump should not hide a true root further away. | N, S (next bracket) |
| 12 | **Several variables.** `least_squares(method="dogbox")` on the residuals divided by their tolerances, in u shifted to the start (v = u − u0, bounds (−u0, 1 − u0), v0 = 0). Goal seek supplies a forward-difference Jacobian itself: a step of 10⁻⁶ in u, backward at the upper bound, one solve per variable; a step whose trial is unusable is retried backward. ftol = xtol = gtol = 10⁻¹⁰. | Measured against trf: n = 2, 67 of 68 met in a median 7 solves against 13; n = 3, 69 of 70 against 67, 13 solves against 21; n = 4, 46 of 50 against 45, 16 against 26. trf moves a start that lies on a bound 10⁻¹⁰ inside; dogbox does not (S, SciPy 1.18.1). With our own Jacobian, every solve is recorded with its purpose and counted. Dogbox's first trust radius is max \|v0\| (1 when v0 = 0): unshifted, a start near the lower bounds (u0 = 0.024, an ordinary reservoir level) makes it tiny; shifted, a linear problem is met in 4 solves from every start (R, §3.11). | N (method), A (own Jacobian), over A's trf; R (N-N3: shift; N-N6: retry) |
| 13 | **Unusable evaluations.** An evaluation is unusable when its solve did not converge, a goal has no value in that state, or the trial raises a topology or fluid error. It is never used as a residual. With one variable it is a gap: brackets form between usable neighbours, and a gap inside a bracket is probed for up to 4 rounds. With several, a slope step is first retried backward; otherwise it counts as a penalty residual (10 times the largest \|r\| seen, at least 1000 tolerances, in every goal). A Jacobian column without a usable step is never used to explain an ending. A run fails only when no evaluation is usable. | TSD §5.7's sketch ("fail the run naming the point") is replaced on measurement. Failures come in regions, interior single points are rare (8 runs in 1,204 scans), and searches with a failed point were still met. Measured, the penalty beat stopping (69 against 68 met at n = 3). A penalty column is 10⁹ tolerances per unit of u: it froze the search at a failure edge (2 of 400 met, against 400 of 400 with the backward retry) and made the diagnosis call independent variables collinear (R, §3.11). | N, over A and TSD; R (N-N6) |
| 14 | **Discontinuities.** Brent closing its bracket (10⁻¹⁰ of u) with both sides more than one tolerance away is a **jump**. The result gives the two values, the goal on each side, and the elements whose state differs (only elements that carry flow on one side or both, D13). A crossing that only failed solves separate is an **unsolved crossing**, given with the solve's message. Neither is ever met. | It says what happened and why: a status or correlation switch (4.7 % of scans), or no steady state between the two sides (an over-controlled flow control). A coarser resolution would call steep continuous crossings jumps: next to a check valve opening (real solve), a root lies 5×10⁻⁷ of u from the switch with −3 and +3 tolerances across 10⁻⁶ of u (R, §3.11). | N, A; R (N-N2, W-R13) |
| 15 | **Several values meeting a goal** are reported where found: another bracket, another met scan point, a met range, or a goal met without crossing its target. They are never searched for. For several variables, the methods text says the search is local. | D13. | O, N, A |
| 16 | **Caps.** At most 60 evaluations for one variable, and 20(n + 1) for n variables (60, 80 or 100). These are server constants, not a request field. On top of them is the one 45 s budget: an evaluation starts only while 1.5 times the slowest so far plus 1 s remains. A deadline inside an evaluation marks it "not computed". The response is then 200 with the best evaluation so far, stop reason `evaluation_limit` or `time_budget`. 503 `TIMEOUT` comes only when the first evaluation does not finish. | Measured: a met one-variable search takes at most 16 solves, and met several-variable searches stay under 20(n + 1) but for 1 of 50 at n = 4. Closing a jump to 10⁻¹⁰ of u takes a median 32 solves (p90 39, max 50): under a cap of 40, 1,690 of 2,000 synthetic jumps ended at the cap, unexplained; under 60, 2,000 of 2,000 are classified, and 1,996 of 2,000 also meet a root in the next bracket (R, §3.11). A cap that counts solves stops at the same point on every machine. Best-so-far follows the system curve's precedent ("not computed"). | N (caps), A, W (best so far), over A's `maxEvaluations` field; R (N-N2: 60 for one variable) |
| 17 | **Deterministic.** There is no randomness, evaluations are cached by their exact values, and the order is fixed. The reported evaluation is the least by one total order (§3.2). Only a run cut short by time depends on the machine, and its message says so. | Measured: 366 of 366 prototype runs repeated identically, and solved states are identical under 5 hash seeds. | A, N |
| 18 | **Each evaluation** is `solve_project(trial, None)`: cold, with no system curves, which is exactly what `/solve` returns with `includeSystemCurve: false`. The trial is the case dumped once (`exclude_unset`, `scenarios` dropped), with the values written at their resolved locations, then `Project.model_validate`. | Measured: this equals the scenario with the variables inserted as overrides, in models, `fields_set` and solves. So applying the values and solving reproduces the reported state. Dumping once saves about 25 % of an evaluation at 999 components. | A, N |
| 19 | **Response.** `GoalSeekResponse {success, result, solvedState, computeTime, scenario}`. `solvedState` is the reported evaluation's own solve, annotated, or null when none is usable. `result` holds the stop reason (a code and a sentence), the method and the solves' method version, the limits, every variable with the override that applies it, every goal, every evaluation, structured notes (codes plus data plus a sentence) and the methods section. | PRD §3.9's output, in one request. The web words codes with names and display units; API users read the sentences. | A, W (codes), N (fields) |
| 20 | **The server never applies the values.** Each variable carries `override`: the scenario override that sets the value found (for a temperature inside a scenario's whole-fluid override, that fluid with the temperature replaced). Applied and solved, it gives `solvedState` bit for bit, apart from `timestamp` and the annotation text. In a scenario run each variable also carries `replacedOverride`: the index of the scenario override whose value it took the place of, or null. | The web applies it with its existing `withChange` and `makeOverride`. A metamorphic test proves the claim. The response's `scenario` record states each override's value as the scenario sets it; `replacedOverride` says, in the structured result, which of those values the reported solve did not use (GOALS §4.2). | A, S; R (W-R7) |
| 21 | **Traceability.** A methods section **Goal seek** comes first in `solvedState` (and is `result.methods`): the case, the method with its constants and citations, each variable and goal, why the search stopped, and the notes. One first note goes in each varied element's trace. In a scenario, the Scenario section marks each override that a variable replaces. No new flags. | GOALS §4.2, in D15's pattern: text added in one place, after the solve. A goal not met is not physics. Without the marking, the Scenario section would state a value the solve did not use. | A, S (marking) |
| 22 | `METHOD_VERSION` stays 1.2.0, and the result names it. The search has no version label of its own: its methods section states the method, every constant (§3.10) and the citations. | Every evaluation is the unchanged 1.2.0 solve. GOALS §4.3 is about a project's results, and goal seek leaves those to `METHOD_VERSION`: applied values are ordinary inputs. A label whose changelog no endpoint publishes would tell a reader nothing, and it had to be bumped by hand; the methods text says what the search did. | A; R (W-R11, over N's `GOAL_SEEK_VERSION`) |
| 23 | **Errors, in this order.** Request 400 → scenario 404 or 400 (as `/solve`) → case fluid 400 → unknown element, port or pipe 404 (all listed, ids named) → inputs 400 (a variable or goal that does not apply, NPSH data missing, a tolerance below its minimum; by index, with ids only in `componentIds` and `connectionIds`, never in a message) → case topology 422 → bounds 400 → the search, always 200. | D10 and D15's precedents: SDD §5.1.2 allows no ids in a `VALIDATION_ERROR` message. The case must solve as `/solve` would. Values found inside the search are never request errors. | A, S; R (W-R2) |
| 24 | `POST /api/v1/goal-seek` (`routers/goal_seek.py`) calls `run_solve`: one budget, the per-client turn and the pool bound unchanged. At most `SOLVE_WORKERS − 1` (1) goal seeks are in the pool at once; another gets 503 `SERVER_BUSY` with `Retry-After`. The path is added to the rate-limited paths. | Decided before design. A goal seek can hold a worker for 45 s; two would hold both, and a plain solve queued behind them would run out of its own budget, which counts from arrival. One worker stays free for solves. `middleware.RATE_LIMITED_PATHS` lists only `/solve` and `/system-curve` today (S, checked). | O, A, S; R (W-R4: the admission limit) |
| 25 | **Web: a dialog**, `xl` with two columns from 1024 px (setup left, result right and sticky), one column below, and a bottom sheet on phones. It opens from a **Goal seek** button in the Results pane header and from **Use in goal seek** in a trace. It is not in the workspace header. | Measured: the workspace header has no room at 640–1023 px (the project name falls to 26 px, and at 768 px the page scrolls 83 px sideways). The results are where the question arises. Two columns keep set-up, run and read on one screen. | W |
| 26 | Goal seek runs on the case shown (the case bar's), as Solve does. A result keeps its own case. | One case selector in the app. | W |
| 27 | **One calculation request at a time per page.** While a goal seek runs, every Solve, Solve all and Solve now control is unavailable with the reason (one store getter, `calculating`), the store refuses a solve, the header's Cancel becomes "Cancel goal seek", and system curves wait. Only Cancel stops a goal seek. The dialog may be closed during a run; a notice gives the outcome. | D10: one solve per client. No accidental cancellations: seven controls in five components start a solve today, and each computes its own busy test (R, checked). A 45 s run does not trap the user in a modal. | W; R (W-R5) |
| 28 | **Apply** is offered only where it reproduces the network solved. A base run applies to the base, or as a new scenario. A scenario run applies to that scenario, or as a new scenario (its changes plus the values). A scenario run is never applied to the base. Apply writes the exact floats, is one undo step, and solves the case at once. It is offered when goals are not met, so the closest values can be applied. | PRD §3.9: the user applies the values. Values found with a scenario's changes would give other results in the base. Measured: rounding to 4 digits moved 15 L/s to 15.00076 L/s. | O, W |
| 29 | A result goes **out of date** by the case staleness key (D15), recomputed on every project change whether or not any case has results. Apply is then unavailable, with the reason. Undo back to the run's project makes it current again. | The key results already use. Names and units never make it stale. A project opened from a link has no results, and goal seek needs none. | W; R (W-R1) |
| 30 | The setup and the last result are **page state** only: not in the project, not in the link, and reset when a project is loaded. While the setup names an element, a new element never takes its id. Apply as new scenario writes a description stating the question. | The answer travels as ordinary inputs. There is no model change and no link growth, consistent with Compare rows and the active case. Ids are reserved as D15 reserves the ids that scenario changes name, so a row never moves to another element. | W, A; R (W-R12, W-R11) |
| 31 | **Default bounds** come from a web table, always shown and editable; the request always carries bounds. A resistance on its Crane default (an isolation or check valve) has default bounds centred (geometrically) on the last solve's `kOpen`, so its middle start is the case's own K; an ideal control valve (K = 0) gets 0.01 to 100. | The ranges follow the numerics designer's scans. The API needs no defaults. A log range cannot be centred on 0. | W, S (centring); R (W-R8) |
| 32 | Fields in the goal-seek dialog are never locked in a scenario (`provideFieldMode({scenario: false})`). | They are page state, not project values. `NumberField` locks by default in a scenario. | W |

### 1.3 Where the designs disagreed

1. **One-variable search.** The API designer solved the start and both bounds, then Brent (median 4 solves). The numerics designer always scans 9 points first (median 10). This design scans (decision 11). It finds the second answer that D13 asks to report in 15 of 16 cases (against 0), handles failed bounds and plateaus without extra rules, and costs about 6 solves more: about 8 s more on a 205-component network, inside the budget.
2. **Several variables.** trf with `x_scale` set to the bound widths (A) against dogbox in normalized u (N). Dogbox was measured faster and at least as successful at every n (decision 12). The synthesizer checked in SciPy 1.18.1 that trf moves a start lying on a bound inside (`make_strictly_feasible`) and dogbox does not. The API designer's own forward-difference Jacobian is kept: it records every solve with its purpose and counts it, which SciPy's `max_nfev` does not.
3. **Unusable trials.** A, following TSD §5.7, stops the search at an unusable evaluation outside the one-variable sampling. N goes around it (gaps and probes; penalty residuals). This design takes N's rule (decision 13); the measurements show failures in regions that a search can avoid.
4. **Topology at a bound.** A runs `build_network` at every bound and returns 422. N validates only. This design validates only (decision 5): a `CONTROLLED_PUMP_SETPOINT` region at low speeds is a gap the search avoids, not a limit the user must compute.
5. **Stop rule.** A stops when every goal is within its tolerance; N stops at a tenth of it. This design stops at a tenth (decision 10), with "met" still meaning within the tolerance. A start within the tolerance stops at once, so "nothing to change" never costs a search.
6. **Caps.** A: `maxEvaluations` in the request, default 100 (5–500). N: fixed caps of 40 and 20(n + 1). This design uses fixed caps (decision 16), 60 for one variable after the review (§11, N-N2). The web sends none, and fixed caps keep runs deterministic and comparable. A request field is reversible (§10).
7. **Method label.** A keeps `METHOD_VERSION` and adds nothing; N adds a goal-seek version. The synthesis added it; after the review this design takes A's choice (decision 22): no endpoint would publish the label's changelog, the label had to be bumped by hand, and the methods section already states every constant of the search (§11, W-R11).
8. **Goal vocabulary.** A had six quantities with per-type addressing (`componentId` + `portId`, `elementId`, `connectionId` + `pipeIndex`) and a signed velocity per pipe. W reused Compare's eleven rows `{quantity, elementId, portId}`, with velocity as the largest in the connection. This design takes W's set and addressing (decision 7), with snake_case API names. The velocity goal is therefore a magnitude; the web hint says to use a flow goal to target zero or a direction.
9. **Request shape.** W nested the setup (`{project, goalSeek: {variables, goals}}`); A kept it flat like `SolveRequest`. This design is flat, so errors locate at `body.variables.{i}` and `body.goals.{j}`.
10. **Start value.** A allowed an optional `start`; N and W used the case's value. This design has no start field (decision 4).
11. **Resistance start.** N started a default resistance at the start solve's `kOpen`, which needs an extra solve before the search and a trial that is not the case. This design starts at the middle of the bounds on the log scale, and the web centres default bounds on `kOpen` (decision 31): the same start, with no special case in the API.
12. **Applying to the base from a scenario run.** A offered it (and said the case would not change); W did not. This design does not (decision 28).
13. **Jump without state change.** N reports any closed bracket as a jump; A separates `discontinuity` from `resolution`. Within a sign change, both sides more than one tolerance away implies a change of more than 2 tolerances, so A's `resolution` case cannot occur at Brent's end. This design has one stop reason, `jump`. Its message says whether elements changed state there, or whether the crossing is steeper than the search resolves.

---

## 2. Model

New `models/goal_seek.py`: variables, goals, the derived tables, constants and result models. The request and response envelopes go in `models/api.py`.

### 2.1 Variables

The tables are derived from `COMPONENT_FIELDS`, `PIPE_FIELDS` and `PROJECT_FIELDS` (`models/scenarios.py`): every entry whose value is a float, plus `resistance` through `FlowCoefficient.value`. A unit test fails when an entry is in neither the variable tables nor `NOT_VARIABLES`.

| Target | `field` | Number written | Unit | Field's own bounds (schema) | Rules checked at the bounds | Scale |
|---|---|---|---|---|---|---|
| Reservoir | `liquidLevel` | `liquidLevel` | m | [0, 1000] | — | linear |
| Reservoir | `surfacePressure` | `surfacePressure` | Pa(g) | [−1e5, 1e8] | — | linear |
| IdealReferenceNode | `pressure` | `pressure` | Pa(g) | [−1e5, 1e8] | — | linear |
| AssignedFlow | `flow` | `flow` | m³/s | [−100, 100] | — (0 behaves as a plug, D12) | linear |
| Pump | `speed` | `speed` | — | (0, 1] | with control: `speed` > `control.minSpeed` (`x-ordered-fields`); labelled "maximum speed ratio" (D11) | linear |
| Pump (speed-controlled) | `control.setpoint` | `control.setpoint` | m³/s | (0, 100] | holder `PumpControl` (a fixed pump: 400, not applicable) | linear |
| ControlValve | `setpoint` | `setpoint` | Pa(g) (PRV, PSV), m³/s (FCV) | [−1e5, 1e8] | FCV [0, 100] (`x-setpoint-bounds`) | linear |
| IsolationValve, CheckValve, ControlValve | `resistance` | `resistance = {kind: coefficient, value: x}` | the coefficient (no unit) | `FlowCoefficient.value` (0, 1e7] | `coefficient` required | log |
| PipeDefinition | `length` | `length` | m | (0, 1e6] | — | log |
| Project | `fluid.temperature` | `fluid.temperature` | K | (0, 1000] | holder `BuiltinFluid` (a custom fluid: 400, not applicable) | linear |

- **Not variables** (`NOT_VARIABLES`):
  - `status`: "discrete: set it in a scenario and compare cases";
  - `spec`: "a library choice replaced as a group, not a number";
  - `fluid`: "a whole definition; vary its temperature".

  Plug, tee and wye have no variables.
- **One value each.** Every model rule on these values bounds one value: the field bounds, `minSpeed < speed` and the FCV range. So validating the 2n projects with one variable at a bound and the others at their starts proves that every point of the box validates (decision 5), provided no trial leaves the box: the map of §3.1 guarantees that. `test_goal_seek_models.py` checks that no validator of an allow-list holder reads two variable fields.
- **Topology and fluid rules are not bounds.** `CONTROLLED_PUMP_SETPOINT` (422 for `/solve`) depends on `speed` and `control.setpoint` together, and CoolProp's temperature range on the concentration. A trial that violates one is unusable (§3.6).

```python
MAX_GOAL_VARIABLES = 4

VariableComponentField = Literal["speed", "control.setpoint", "setpoint", "resistance",
                                 "liquidLevel", "surfacePressure", "pressure", "flow"]
VariablePipeField = Literal["length"]
VariableProjectField = Literal["fluid.temperature"]
Coefficient = Literal["K", "Cv", "Kv"]   # FlowCoefficient.kind

@dataclass(frozen=True)
class Variable:
    """How goal seek varies one allow-list value."""
    entry: Overridable                    # the allow-list entry (path, holder, unit, label)
    number: tuple[str, ...] = ()          # from the entry's value to the number: () or ("value",)
    schema: type[BaseModel] | None = None # the model whose property bounds the number (None: entry's)
    scale: Literal["linear", "log"] = "linear"

GOAL_COMPONENT_FIELDS: dict[type[BaseComponent], dict[str, Variable]]   # every class, {} if none
GOAL_PIPE_FIELDS: dict[str, Variable]
GOAL_PROJECT_FIELDS: dict[str, Variable]
NOT_VARIABLES: dict[str, str]             # field -> why it is not a variable

class _Bounds(CamelModel):
    ORDERED_FIELDS: ClassVar[tuple[tuple[str, str], ...]] = (("lower", "upper"),)
    """lower < upper, published as x-ordered-fields on each variable schema (D10)."""
    lower: float = Field(allow_inf_nan=False,
        description="SI, within the field's own bounds (x-goal-variables); below upper")
    upper: float = Field(allow_inf_nan=False, description="SI, within the field's own bounds")
    # model validator: "lower must be below upper"

class ComponentVariable(_Bounds):
    kind: Literal["component"]
    component_id: Identifier
    field: VariableComponentField
    coefficient: Coefficient | None = Field(default=None,
        description="resistance only (required there): the flow coefficient varied")

class PipeVariable(_Bounds):
    kind: Literal["pipe"]
    connection_id: Identifier
    pipe_index: int = Field(ge=0, le=MAX_PIPES - 1, description="0-based, as overrides")
    field: VariablePipeField

class ProjectVariable(_Bounds):
    kind: Literal["project"]
    field: VariableProjectField

GoalVariable = Annotated[
    Annotated[ComponentVariable, Tag("component")] | Annotated[PipeVariable, Tag("pipe")]
    | Annotated[ProjectVariable, Tag("project")],
    Discriminator(_override_tag, custom_error_type="invalid_variable",   # reused: never quotes the tag
        custom_error_message="unknown variable kind (expected 'component', 'pipe' or 'project')"),
]
```

`allow_inf_nan=False` matters here: FastAPI's JSON parser accepts `NaN` and `Infinity`, and a float field without bounds would let them through.

### 2.2 Goals

| `quantity` | Element (`elementId`) | `portId` | Value read | Sign | Unit | Floor of the default tolerance |
|---|---|---|---|---|---|---|
| `port_pressure` | any component | required | `nodeResults["c:p"].pressure` | static, gauge | Pa(g) | ρg × 0.01 m |
| `link_flow` | a connection | — | `linkResults[id].flow` | from → to | m³/s | 10⁻⁶ m³/s |
| `link_velocity` | a connection | — | max of \|`velocity`\| and every \|`segments[k].velocity`\| | magnitude (≥ 0) | m/s | 10⁻³ m/s |
| `link_head_loss` | a connection | — | `linkResults[id].headLoss` | EGL(from) − EGL(to) | m | 0.01 m |
| `pump_flow` | a pump | — | `pumpResults[id].operatingFlow` | suction → discharge | m³/s | 10⁻⁶ m³/s |
| `pump_head` | a pump | — | `pumpResults[id].operatingHead` | EGL rise | m | 0.01 m |
| `pump_npsh_available` | a pump | — | `pumpResults[id].npshAvailable` | — | m | 0.01 m |
| `pump_npsh_margin` | a pump whose curve has `npshrCurve` | — | `pumpResults[id].npshMargin` | NPSHa − NPSHr | m | 0.01 m |
| `valve_flow` | an isolation, check or control valve | — | `valveResults[id].flow` | inlet → outlet | m³/s | 10⁻⁶ m³/s |
| `valve_pressure_drop` | a valve | — | `valveResults[id].pressureDrop` | inlet minus outlet, static | Pa (difference) | ρg × 0.01 m |
| `boundary_outflow` | a reservoir or reference node | — | `boundaryResults[id].outflow` | out of the boundary, into the network | m³/s | 10⁻⁶ m³/s |

- **Compare's readers.** The readers are exactly Compare's (`utils/compare.ts` `QUANTITIES`): `portPressure`, `linkFlow`, `linkVelocity`, `linkHeadLoss`, `pumpFlow`, `pumpHead`, `pumpNpsha`, `pumpNpshMargin`, `valveFlow`, `valvePressureDrop`, `boundaryOutflow`. The shared fixture (§7.5) proves that the API and the web read the same values.
- **No value.** A goal has no value, and its evaluation is unusable, when the published field it reads is null or the element's or node's result is absent, and for every goal of a solve that did not converge. For example:
  - a port in a closed-off or floating section (no node result);
  - an element with no result;
  - NPSH available without a vapor pressure, or in a floating section (`npshAvailable` null);
  - the NPSH margin of a pump that carries no flow (`npshMargin` null: NPSHr is evaluated only for a running pump). NPSH available keeps its value at zero flow, as the results tables and Compare show it.
- **Not goals in v1:**
  - an assigned-flow node's outflow, which is its input (−flow): vary it instead;
  - a plug's outflow (always 0);
  - the rest of §1.1's Later list.
- **Default tolerance.** The relative part is 0.5 %. The floor is in head for pressures and pressure drops, converted with ρ of the case fluid at the case's own temperature (`fluid_properties(case.fluid).density`, once, before the search), so the tolerance stays fixed while the temperature varies. The methods text states that ρ (§5.4).
- **Smallest user tolerance.** max(10⁻⁶ × \|target\|, the quantity's minimum), with fixed minima that do not depend on the fluid: 0.1 Pa for pressures and pressure drops, 10⁻⁵ m for heads, 10⁻⁹ m³/s for flows and 10⁻⁶ m/s for velocity. They are a thousandth of the floors, with ρg taken as 10⁴ N/m³ for pressures, and are published in `x-goal-quantities`, so the web checks them at the field.

```python
GoalQuantity = Literal["port_pressure", "link_flow", "link_velocity", "link_head_loss",
                       "pump_flow", "pump_head", "pump_npsh_available", "pump_npsh_margin",
                       "valve_flow", "valve_pressure_drop", "boundary_outflow"]
RELATIVE_TOLERANCE = 0.005     # D6
HEAD_FLOOR = 0.01              # m, D6 (pressures as ρg·0.01 m)
FLOW_FLOOR = 1.0e-6            # m³/s, designers' default (D16); also the zero-flow line of §3.1 step 6
VELOCITY_FLOOR = 1.0e-3        # m/s, designers' default (D16)
MIN_TOLERANCE_RELATIVE = 1.0e-6
MIN_TOLERANCE = {"pressure": 0.1, "head": 1.0e-5, "flow": 1.0e-9, "velocity": 1.0e-6}  # SI

class Goal(CamelModel):
    quantity: GoalQuantity
    element_id: Identifier = Field(description="The component or connection (x-goal-quantities)")
    port_id: Identifier | None = Field(default=None, description="port_pressure only (required)")
    target: float = Field(ge=-1.0e8, le=1.0e8, description="SI, in the quantity's unit")
    tolerance: float | None = Field(default=None, gt=0, le=1.0e8, description=(
        "SI; omitted: max(0.5 % of |target|, the quantity's floor); at least max(1e-6 |target|, "
        "the quantity's minimum in x-goal-quantities)"))
```

### 2.3 Request (`models/api.py`)

| Field | Type | Unit | Validation |
|---|---|---|---|
| `project` | `Project` | SI | as for `/solve` |
| `scenarioId` | `Identifier \| null` | — | optional; unknown: 404 (as `/solve`) |
| `variables` | `GoalVariable[]` | — | 1 to 4 |
| `variables[i].kind`, target ids, `field` | as an override | — | discriminator and Literals |
| `variables[i].coefficient` | `'K' \| 'Cv' \| 'Kv'` | — | required for `resistance`, absent otherwise |
| `variables[i].lower`, `.upper` | number | SI (§2.1) | finite, `lower < upper`, within the field's own bounds (§4.2 step 7) |
| `goals` | `Goal[]` | — | as many as `variables` |
| `goals[j].quantity`, `.elementId`, `.portId` | §2.2 | — | `portId` required for `port_pressure`, absent otherwise |
| `goals[j].target` | number | the quantity's | −1e8 to 1e8 |
| `goals[j].tolerance` | number \| null | the quantity's | > 0, ≤ 1e8; at least max(10⁻⁶ × \|target\|, the quantity's minimum) (§2.2; checked in §4.2 step 5) |

```python
class GoalSeekRequest(CamelModel):
    model_config = ConfigDict(json_schema_extra=_goal_seek_schema_extra)
    # x-goal-variables, x-goal-quantities, x-goal-seek-rules (§2.4)
    project: Project
    scenario_id: Identifier | None = Field(default=None, description=_GOAL_SEEK_SCENARIO_DESCRIPTION)
    variables: list[GoalVariable] = Field(min_length=1, max_length=MAX_GOAL_VARIABLES)
    goals: list[Goal] = Field(min_length=1, max_length=MAX_GOAL_VARIABLES,
                              description="As many as variables (PRD §3.9)")
    # model validator, by index only:
    #   "as many goals as variables (PRD §3.9)"
    #   "variables {i} and {j} vary the same value"            (same target and field)
    #   "goals {i} and {j} read the same result"               (same quantity, element and port)
    #   "variables {i}: coefficient applies to resistance only" / "variables {i}: resistance needs a coefficient"
    #   "goals {j}: port_pressure needs portId" / "goals {j}: portId applies to port_pressure only"
```

SDD §4.13's sketch is replaced:
- The nested target becomes a flat union, as D15 did for overrides.
- `result` plus `key` becomes `quantity`, `elementId` and `portId`.
- `maxIterations` is dropped: the caps are server constants (§3.8), and the solve is the unit of cost.

### 2.4 Published rules (on the `GoalSeekRequest` schema)

**`x-goal-variables`**, by target schema (every component schema, `PipeDefinition`, `Project`). Each variable field gives the schema whose property bounds the number, the camelCase path from the target to the number, its scale and, for a resistance, its coefficients. The web combines it with the property bounds, `x-setpoint-bounds` and `x-ordered-fields`, as the forms do.

```json
{"Pump": {"speed": {"schema": "Pump", "path": ["speed"], "scale": "linear"},
          "control.setpoint": {"schema": "PumpControl", "path": ["control", "setpoint"], "scale": "linear"}},
 "ControlValve": {"setpoint": {"schema": "ControlValve", "path": ["setpoint"], "scale": "linear"},
                  "resistance": {"schema": "FlowCoefficient", "path": ["resistance", "value"],
                                 "scale": "log", "coefficients": ["K", "Cv", "Kv"]}},
 "PipeDefinition": {"length": {"schema": "PipeDefinition", "path": ["length"], "scale": "log"}},
 "Project": {"fluid.temperature": {"schema": "BuiltinFluid", "path": ["fluid", "temperature"], "scale": "linear"}},
 "Plug": {}, "TeeBranch": {}, "WyeBranch": {}, "...": "every component schema"}
```

**`x-goal-quantities`**, by quantity: its unit, the schemas it may name, whether it takes a port, the default-tolerance rule and what it needs.

```json
{"port_pressure": {"unit": "Pa(g)", "targets": ["Reservoir", "...every component schema"], "port": true,
                   "relativeTolerance": 0.005, "floor": {"head": 0.01},
                   "minimum": {"relative": 1e-6, "absolute": 0.1}},
 "link_flow": {"unit": "m³/s", "targets": ["PipeConnection"], "port": false,
               "relativeTolerance": 0.005, "floor": {"flow": 1e-6},
               "minimum": {"relative": 1e-6, "absolute": 1e-9}},
 "link_velocity": {"unit": "m/s", "targets": ["PipeConnection"], "floor": {"velocity": 0.001}, "...": ""},
 "pump_npsh_available": {"unit": "m", "targets": ["Pump"], "floor": {"head": 0.01}, "needs": ["vaporPressure"]},
 "pump_npsh_margin": {"unit": "m", "targets": ["Pump"], "floor": {"head": 0.01},
                      "needs": ["vaporPressure", "npshrCurve"]},
 "valve_pressure_drop": {"unit": "Pa (difference)", "targets": ["IsolationValve", "CheckValve", "ControlValve"],
                         "floor": {"head": 0.01}},
 "boundary_outflow": {"unit": "m³/s", "targets": ["Reservoir", "IdealReferenceNode"], "floor": {"flow": 1e-6}},
 "...": "every quantity"}
```

- A head floor applies to a pressure through ρg of the case fluid. The `minimum` is absolute, in the quantity's unit, and never depends on the fluid. The web words the rules from this extension, enforces the minimum at the Tolerance field (it moves with the target), and never copies its numbers.

**`x-ordered-fields`** on `ComponentVariable`, `PipeVariable` and `ProjectVariable`: `[{"lower": "lower", "upper": "upper", "strict": true}]`, the existing extension (`models/components.py`), so the web's From and To bounds come from `orderedBounds` as a pump's minimum and maximum speeds do.

**`x-goal-seek-rules`** on `GoalSeekRequest`, the request validator's list rules:

```json
{"sameLength": [["variables", "goals"]],
 "uniqueBy": {"variables": ["kind", "componentId", "connectionId", "pipeIndex", "field"],
              "goals": ["quantity", "elementId", "portId"]}}
```

A key absent from an item counts as null. The web's Run reasons 3 and 6 and the "(already a goal)" and "(already a variable)" marks read these instead of copying the rules (D10).

- `test_schema_rules.py` checks every extension against the tables, the validators and the default-tolerance function: for each `uniqueBy` key list, two items equal on those keys are rejected and two that differ on any one of them are accepted. It keeps failing while `apps/web/src/lib/api/openapi.json` is stale (`pnpm gen:types`).

### 2.5 Request rules (400 `VALIDATION_ERROR`, by index, never a value)

Request validation rejects:
- an unknown `kind` or `quantity`, through custom discriminator and literal messages that never quote the input;
- a `field` outside its Literal;
- list lengths outside 1–4, or unequal;
- `lower ≥ upper`;
- `coefficient` missing for a resistance, or given for another field;
- `portId` missing for a port pressure, or given for another quantity;
- duplicate variables or goals;
- a target or tolerance outside its schema bounds;
- non-finite numbers (`NaN`, `Infinity`).

Unknown keys are reported as "(unknown field)", as for every request. A sentinel test proves that no message quotes a submitted value.

### 2.6 Response (`models/goal_seek.py`; envelope in `models/api.py`)

```python
GoalSeekStop = Literal["met_at_start", "met", "not_reachable", "jump", "unsolved_crossing",
                       "no_progress", "evaluation_limit", "time_budget", "no_usable_evaluation"]
Purpose = Literal["start", "scan", "root", "probe", "minimize", "step", "slope"]
Outcome = Literal["usable", "not_converged", "no_value", "topology_error", "fluid_error", "not_computed"]
NoteCode = Literal["other_crossing", "met_range", "met_without_crossing", "closest_at_bound",
                   "closest_on_plateau", "closest_inside", "jump", "unsolved_crossing",
                   "state_changes", "start_clipped", "unusable_evaluations", "goal_no_effect",
                   "variable_no_effect", "variables_collinear", "slope_unknown", "sensitive"]

class StateChange(OutputModel):
    element_id: str
    aspect: Literal["pump_status", "pump_control", "valve_state", "branch_pattern"]
    before: str | None          # null: the element has no result in that state
    after: str | None

class GoalSeekEvaluation(OutputModel):
    index: int                  # 0-based; 0 is the start
    purpose: Purpose
    variable_values: list[float]          # SI, in the variables' order
    outcome: Outcome
    goal_values: list[float | None]       # SI; null where the state has no value
    residuals: list[float | None]         # goal value - target, SI
    message: str                          # why it is not usable ('' when usable)
    seconds: float                        # inside the worker
    state_changes: list[StateChange]      # against the start's states, elements with flow only (§3.1)

class VariableResult(OutputModel):
    index: int
    variable: GoalVariable                # as given
    label: str                            # "maximum speed ratio of pump P1", "flow coefficient Cv of valve V1"
    unit: str                             # trace unit ('' for none)
    scale: Literal["linear", "log"]
    start: float
    start_source: Literal["case", "clipped", "middle"]
    case_value: JsonValue                 # the case's value of the field (a resistance: its FlowCoefficient or null)
    base_value: JsonValue                 # the base project's value (equal to case_value for a base run)
    value: float | None                   # at the reported evaluation (null: none usable)
    at_bound: Literal["lower", "upper"] | None   # value == lower or upper exactly (§3.1's map)
    override: Override | None             # applies `value` (§4.4); null when value is null
    replaced_override: int | None         # scenario run: the index in the scenario's overrides
                                          # whose value this one took the place of (§4.4)

class GoalResult(OutputModel):
    index: int
    goal: Goal                            # as given
    label: str                            # "static pressure at port outlet of tee T3"
    unit: str                             # 'Pa(g)', 'Pa (difference)', 'm³/s', 'm/s', 'm'
    tolerance: float
    tolerance_source: Literal["user", "default"]
    value: float | None
    residual: float | None
    met: bool
    message: str                          # why there is no value ('' otherwise)
    evaluated_min: float | None           # over the usable evaluations
    evaluated_max: float | None

class GoalSeekNote(OutputModel):
    code: NoteCode
    message: str                          # SI sentence (§5.3)
    variables: list[int]; goals: list[int]; evaluations: list[int]
    variable_values: list[float]; goal_values: list[float]
    state_changes: list[StateChange]

class GoalSeekResult(OutputModel):
    met: bool                             # every goal met at the reported evaluation
    stop_reason: GoalSeekStop
    message: str                          # §5.2
    method: Literal["scan_brent", "least_squares"]
    method_version: str                   # the solves' METHOD_VERSION (1.2.0)
    evaluation_limit: int                 # 60, or 20(n + 1)
    time_budget: float                    # s (workers.REQUEST_BUDGET_S)
    reported_evaluation: int | None
    variables: list[VariableResult]
    goals: list[GoalResult]
    evaluations: list[GoalSeekEvaluation]
    notes: list[GoalSeekNote]
    methods: MethodsSection               # the "Goal seek" section, also first in solvedState

class GoalSeekResponse(OutputModel):      # models/api.py
    success: bool                         # result.met
    result: GoalSeekResult
    solved_state: SolvedState | None      # the reported evaluation's own solve, annotated (§5.4)
    compute_time: float                   # seconds in the worker
    scenario: ScenarioResult | None       # the case's scenario as stored, as /solve reports it;
                                          # an override named by a variable's replacedOverride
                                          # was not used: the value found took its place
```

Payload:
- **Evaluations:** at most 100, about 300 B each at n = 4.
- **`solvedState`:** the size of one `/solve` response. Measured at 205 components: 3.59 MB raw, 127 KB gzipped. Responses are gzip-compressed (D10).
- **Other states:** the states of other evaluations are never returned.

---

## 3. Algorithm (`services/goal_seek.py`)

### 3.1 One evaluation

1. **Before the search.** Dump the case once: `case.model_dump(mode="json", exclude_unset=True)`, `scenarios` dropped. The case is the base, or `apply_scenario(project, scenarioId).project`. Resolve each variable's location with the scenario service's planner (§4.4).
2. **The map from u to x.** Each variable has its scale (§2.1), its bounds and its start x0 with u0 (§3.2):
   - u ≤ 0 gives exactly `lower`, u ≥ 1 exactly `upper`, and u = u0 exactly x0;
   - otherwise x = lower + u (upper − lower), or lower · (upper/lower)^u on a log scale, clamped into [lower, upper];
   - u0 is the inverse map of x0, clamped into [0, 1]; a start clipped to a bound has u0 = 0 or 1, and a `middle` start is u0 = 1/2 with x0 the map's own x(1/2), so the scan's k = 4 point is the start;
   - with several variables the search runs in v = u − u0 (§3.4): v at its lower bound −u0 gives u = 0, at its upper bound 1 − u0 gives u = 1, and v = 0 gives u0, each by comparison with the bound, not by arithmetic.

   So no trial leaves the bounds, evaluation 0 is the case's own value bit for bit, and a scan point equal to the start (a clipped or `middle` start) and least squares' first call are cache hits. Without these rules the plain formula gives 10000000.000000006 at u = 1 for an upper bound of 10⁷ (the resistance maximum), which `FlowCoefficient` rejects, and misses x0 by an ulp for most log starts (R, §3.11). `at_bound` is the value equal to `lower` or `upper`.
3. **The trial.** For a trial x (a tuple of SI values, cached by exact value), deep-copy the dump. Write each number at its location: a resistance as `{kind: coefficient, value: x}`, a temperature inside the case's fluid. Then `Project.model_validate` the copy.
4. **The solve.** `state = solve_project(trial, None)`: cold, with no system curves. It is exactly `/solve`'s state with `includeSystemCurve: false`, the web's request. A `TopologyError` or `FluidError` makes the evaluation unusable, with outcome `topology_error` or `fluid_error` and the issues' messages. A `ValidationError` cannot occur once the bounds have passed, since the map never leaves them (§2.1, tested); one would be an internal error (500), never a gap.
5. **The goals.** Read the goal values (§2.2). An evaluation is usable when the solve converged and every goal has a value; otherwise its outcome is `not_converged` or `no_value`, with the reason.
6. **States.** Record a compact map of element states with their flows: each pump's `status` and `control.state` (with `operatingFlow`), each valve's `state` (with `flow`), each branch's `pattern` (with `portFlows`). `state_changes` lists the differences from the start's map (from the first evaluation with a solved state, normally the start), counting an element only when it carries flow in one of the two states: some flow of the element above `FLOW_FLOOR` (10⁻⁶ m³/s) in magnitude. A label that changes while the element carries no flow in either state (closed, isolated, no flow) is not a change (D13).
7. **Keep one state.** Only the current best evaluation's `SolvedState` is kept in memory, by the order of §3.2.
8. **The budget.** It is checked before each evaluation (§3.8), and inside the solver at every Newton iteration, as for `/solve`.

**Measured:** writing on top of the case equals the scenario with the variables inserted as overrides, in models, `fields_set` and solves. A value equal to a field's default is labelled `default` by value (`trace._given`), so removing a change equal to the base does not change a trace either.

### 3.2 Tolerances, scaled residuals and the reported evaluation

- **Scaled residuals.** r_j = (g_j − t_j)/tol_j. Goal j is met when |r_j| ≤ 1. The stop rule is max_j |r_j| ≤ 0.1 (`STOP_FRACTION`).
- **Tiers.** A usable evaluation is in:
  - tier 0 when max |r_j| ≤ 0.1;
  - tier 1 when max |r_j| ≤ 1;
  - tier 2 otherwise.
- **The reported evaluation** is the least usable evaluation by this total order:
  - tier 0 and tier 1: (tier, d, index);
  - tier 2: (2, Σ r_j², d, index);

  where d is the Euclidean distance in scaled coordinates u from the start. Every path below therefore reports what it says without keeping more than one state:
  - among met values, the one nearest the current design;
  - otherwise the closest by the least-squares cost, the nearest to the start on ties, then the earliest.
- **The start.** For each variable, the start is the case's value clipped into the bounds (`case`, or `clipped` with the note `start_clipped`). A resistance the case does not hold in the variable's kind starts at the middle of its bounds in u, the geometric mean as the map computes it, x(1/2) (`middle`).
- **Evaluation 0.** It solves the start. If it is tier 0 or tier 1, the search stops:
  - `met_at_start` when every start is the case's own value;
  - otherwise `met`.

### 3.3 One variable (`method: "scan_brent"`)

1. **Scan.** Solve the 9 points u = k/8, k = 0…8 (the bounds and 7 interior points), always all 9, coarse to fine: 0, 1, 1/2, 1/4, 3/4, 1/8, 3/8, 5/8, 7/8. A point equal to the start is a cache hit. Cost: 10 solves at most. A complete scan has the same points in any order; this order makes a scan that the time budget cuts short still span the bounds.
2. **Met points.** If any evaluation is tier 0, stop: the reported one is the tier-0 evaluation nearest the start. When two or more evaluations meet the goal (tier ≤ 1), the note `met_range` gives how many and the range they span.
3. **Brackets.** Sort the usable evaluations by u. Every adjacent pair whose residuals have opposite signs is a bracket. A bracket with an unusable evaluation between its ends is a bracket with a gap. Order the brackets by distance from the start (0 when the start is an end), then by lower u.
4. **Brent.** Run `scipy.optimize.brentq(f, a, b, xtol=1e-10, rtol=4ε, maxiter=200)` in u, in the first bracket (a bracket with a gap starts at step 5). f solves, raises an internal stop at tier 0, and raises a gap at an unusable evaluation.
   - **Tier 0:** stop.
   - **The bracket closes** (xtol) and the closest pair of usable evaluations with opposite signs is more than one tolerance away on both sides: a **jump** (note `jump`: the two values, the goal on each side and the elements whose state differs, §3.1 step 6). Otherwise the best side meets the goal (tier 1), with the `sensitive` note where it applies (§5.3). Closing a jump costs about 30 solves (bisection from 1/8 to 10⁻¹⁰ of u); the cap of 60 leaves room for it and the next bracket (§3.8).
   - **A gap.** Step 5.
5. **Gap probes.** For up to 4 rounds (`PROBE_ROUNDS`):
   1. Take the unusable run inside the bracket and its nearest usable neighbours on each side (from every evaluation so far).
   2. Solve the two midpoints in u between the run's ends and those neighbours.
   3. If a gap-free pair with opposite signs appears, resume Brent there.

   After 4 rounds without one, the result is an **unsolved crossing**: note `unsolved_crossing`, with the closest usable values on each side and the unusable evaluation's outcome and message.
6. **Next bracket.** When a bracket ends at a jump or an unsolved crossing, the next bracket in the same order is tried, while evaluations remain. Its note stays.
7. **Other brackets.** Every bracket not solved gets a note `other_crossing`: "also crosses between a and b".
8. **No bracket.** Take the best usable evaluation b by §3.2.
   - **Plateau.** If two or more usable evaluations tie with b within 10⁻³ of a tolerance in every goal (`PLATEAU_TIE`), note `closest_on_plateau` with the tied range. No extra solve.
   - **A bound.** If b is a bound, note `closest_at_bound`. No extra solve.
   - **Inside.** Otherwise run `scipy.optimize.minimize_scalar(φ, bounds=(u_left, u_right), method="bounded", options={"xatol": 1e-5})` on φ(u) = |r(u)| between b's neighbours, stopping at tier 0. An unusable evaluation gives the penalty (§3.6). Note `closest_inside`.

   This establishes only that the residual does not change sign among the values solved: a goal could cross its target twice between two scan points (§3.7). The messages say what was solved (§5.2).
9. **No usable evaluation** at all: `no_usable_evaluation`, `solvedState` null.
10. **The stop reason** is derived after the reported evaluation is chosen (§3.2), by §3.5's rule: a reported evaluation that meets every goal gives `met` whichever path ended the search (with `met_without_crossing` when it is not an end of a solved sign change), and `jump`, `unsolved_crossing` and `not_reachable` are given only when it does not.

Typical cost: 1 + 9 + 1 to 3 solves.

### 3.4 Several variables (`method: "least_squares"`)

- **Start.** x0 = the starts of §3.2, solved as evaluation 0. A start on a bound stays there: dogbox accepts it.
- **Coordinates shifted to the start.** The search runs in v = u − u0, with bounds (−u0, 1 − u0) and v0 = 0, mapped to x by §3.1 step 2. SciPy 1.18.1's dogbox sets its first trust radius to max_j \|v0_j\| (`dogbox.py` line 175), and to 1 when that is 0. In u itself, a start near the lower bound of every variable (an ordinary case: a reservoir level of 0.5 m in [0, 20.5 m] is u0 = 0.024) gives a tiny first radius, and the search spends solves growing it: 13 solves instead of 4 at u0 = 0.05 on a linear problem, 40 at u0 = (10⁻⁴, 0). Shifted, the first radius spans each whole range, and the linear problem is met in 4 solves from every start (R, §3.11).
- **Call.** `scipy.optimize.least_squares(fun, v0, jac=jac, bounds=(-u0, 1 - u0), method="dogbox", x_scale=1.0, ftol=1e-10, xtol=1e-10, gtol=1e-10)`:
  - `fun(v)` returns r, the residuals scaled by their tolerances. It is cached by x, and it stops the search at tier 0. Its first call is v0 = 0, the start: a cache hit.
  - `jac(v)` is forward differences with h = 10⁻⁶ (`JACOBIAN_STEP`) in each v_j, backward where v_j + h > 1 − u0_j: one solve per variable, purpose `slope`. A step whose trial is unusable is retried once in the other direction (one more solve, also `slope`). A column with no usable step uses the penalty (§3.6) and is marked unknown.
  - An unusable evaluation of `fun` returns the penalty vector (§3.6).
  - Goal seek counts every solve against the cap itself: SciPy's `max_nfev` does not count a Jacobian's solves (checked in SciPy 1.18.1's documentation).
- **Ending.** If `least_squares` returns by its own tests and the reported evaluation is not met: `no_progress`. A diagnosis from the last Jacobian J (tolerances per unit of u), on its known columns only, follows:
  - **A variable whose slope is unknown:** a column with no usable step. Note `slope_unknown`, naming the variable and the unusable evaluations; it is never called `variable_no_effect` or `variables_collinear`. A penalty column is about 10⁹ tolerances per unit of u, which made two independent variables (true σ_min/σ_max = 0.81) look collinear at 1.3×10⁻⁷ (R, §3.11).
  - **A variable that moves no goal:** a known column j with max_i |J_ij| < 0.1. Across its whole range, at this slope, it would change no goal by a tenth of its tolerance. Note `variable_no_effect`.
  - **Variables that act as one:** σ_min/σ_max < 10⁻⁴ among the remaining known columns (10 times the measured finite-difference error of 9.2×10⁻⁶). The note `variables_collinear` names the variables with |v_j| ≥ 0.3 in the right singular vector of σ_min, for example one reservoir's level and its surface pressure.
  - **A goal that did not move:** no usable evaluation moved goal j by more than 10⁻³ of its tolerance. Note `goal_no_effect`.
- **Several answers.** The search is local. The methods text says so; finding other answers is not a goal (D13).

### 3.5 Stop reasons and `met`

The stop reason is derived after the reported evaluation is chosen (§3.2):
1. `no_usable_evaluation` when no evaluation is usable;
2. `evaluation_limit` or `time_budget` when the cap or the budget stopped the search, with `met` from the reported evaluation;
3. otherwise, when the reported evaluation meets every goal: `met_at_start` when it is evaluation 0 and the case's own values, else `met`. A path that ended at a jump or an unsolved crossing keeps its note;
4. otherwise the path's reason: `not_reachable`, `jump`, `unsolved_crossing` or `no_progress`.

So `success` is true only with `met_at_start`, `met`, `evaluation_limit` or `time_budget`, and a message never says that no value meets a goal while the reported evaluation meets it.

| `stopReason` | When | `met` |
|---|---|---|
| `met_at_start` | Evaluation 0 is the case itself and meets every goal | true |
| `met` | The reported evaluation meets every goal (the stop rule was reached, or a path ended with a met evaluation, wherever it lies) | true |
| `not_reachable` | One variable, no bracket, and the reported evaluation does not meet the goal | false |
| `jump` | One variable: no evaluation meets the goal, and the first bracket tried ended at a jump | false |
| `unsolved_crossing` | One variable: no evaluation meets the goal, and the first bracket tried ended at an unsolved crossing | false |
| `no_progress` | Several variables: `least_squares` ended by its own tests and no evaluation meets every goal | false |
| `evaluation_limit` | The cap was reached | from the reported evaluation |
| `time_budget` | The budget ran out (§3.8) | from the reported evaluation |
| `no_usable_evaluation` | No evaluation was usable | false |

`success` = `result.met`.

### 3.6 Unusable evaluations

- **Never a residual.** Each one is recorded with its outcome and message.
- **One variable.** A gap. Brackets form only between usable neighbours, and a gap inside a bracket is probed (§3.3 step 5). For `minimize_scalar`, and for several variables, it counts as a penalty: P = max(1000, 10 × the largest |r_j| among usable evaluations so far) in every component (`PENALTY_FLOOR`, `PENALTY_FACTOR`). The cost is then above any usable point's, so the trust region shrinks.
- **A slope step.** An unusable slope step is first retried in the other direction (§3.4); only a column with no usable step takes the penalty, and it is never used to explain an ending. Measured with the root 0.05–0.3 behind a failure edge and the start at the edge (a forward step crosses it): without the retry 2 of 400 met (338 `no_progress`, 60 at the cap); with it 400 of 400 in 5 solves (R, §3.11).
- **The note.** `unusable_evaluations` counts them and names the first.
- **Request errors.** Only the case's own topology and fluid errors (422 and 400) are request errors (§4.2).

### 3.7 Discontinuities and several answers

- **Status changes are mostly kinks.** Measured over 1,120 refined status-change intervals: 82 % continuous (kinks only), 5.5 % value jumps of more than a tolerance, 6 % converged on one side only, and 6 % with a goal defined on one side only. Brent handles kinks; the scan's brackets keep it on usable ground.
- **Jumps** come from a Crane tee's Darby fallback (5–18 tolerances), a Crane correlation step (1–3), a flow-controlled pump's limit band (5–40), an over-control switch (25–160) and a drooping-curve reversal (200). The result never calls such a crossing met. It names the switching elements from the two sides' state maps, counting only elements that carry flow on one side or both (§3.1 step 6). With no such element changing state, the message says that the crossing is steeper than 10⁻¹⁰ of the range resolves. The resolution stays at 10⁻¹⁰: at 10⁻⁶, a continuous crossing beside a check valve's opening would be called a jump (R, §3.11).
- **No steady state between two states.** Checked by the synthesizer: a flow-controlled pump feeding an assigned demand (the `assigned_flow_flow_pump_max_speed` network, setpoint 20 L/s). It runs at its maximum speed for a demand below the setpoint and at its minimum above. The port pressure falls from 260.9 kPa(g) to 9.6 kPa(g) across 20 L/s ± 10⁻⁷ m³/s. Within about ±10⁻⁸ m³/s of the setpoint the solve does not converge (over-controlled, D12).

  Running this section's rule on it gave an unsolved crossing after 34 evaluations: 10 scan, 16 Brent and 8 probes. The closest usable values were 0.0199999876 and 0.0200000125 m³/s. It is reference case G16.
- **Several answers (D13).** One variable: the bracket nearest the start is solved, and every other bracket, met point and met range is noted. Measured, the targets that a series crosses more than once: none for 97.1 % of moving series, a band of at most one tolerance for 1.8 %, and more than 10 tolerances for 0.4 %.

### 3.8 Caps, time budget, cancellation

- **Caps** (`EVALUATIONS_ONE = 60`, `EVALUATIONS_PER_VARIABLE = 20`): 60 for one variable, and 20(n + 1) for n (60, 80 or 100), counting every solve. Measured for met searches: one variable at most 16; n = 2 at most 16, n = 3 at most 35, n = 4 p90 32 with 1 of 50 at the cap. The one-variable cap is sized for a jump: start, scan and Brent closing a jump bracket to 10⁻¹⁰ of u take a median 42 solves (p90 49, max 59), 44 (p90 51) with a root met in the next bracket. At 40, 1,690 of 2,000 synthetic jumps ended at the cap without being named, and the next bracket was never searched; at 60, 2,000 of 2,000 are named and 1,996 of 2,000 meet the next root. The prototype's 6 jump targets on real networks took 32–40 solves, the same at either cap (R, §3.11). At the cap the stop reason is `evaluation_limit`.
- **Budget.** The request's 45 s budget from `workers.run_solve` covers everything, waiting for a worker included. Before every evaluation after the first, the search starts it only while the remaining time is at least 1.5 × the slowest evaluation so far + 1 s (`TIME_FACTOR`, `TIME_RESERVE_S`: room for the response's serialization, 0.2 s at the largest project). Otherwise the stop reason is `time_budget`.
- **A deadline inside a solve.** A `SolveDeadlineError` in evaluation k ≥ 1 records it as `not_computed` ("not computed: the request's time budget of 45 s ran out") with stop reason `time_budget`. In evaluation 0, or before it, it propagates: 503 `TIMEOUT`, as for `/solve`.
- **Cancellation.** `SolveCancelledError` always propagates (the client has gone).

**What fits in 45 s** (numerics, this container; the median time per solve). Under the rule above, at t seconds per solve the k-th evaluation (from 0) starts only while k·t ≤ 45 − 1.5t − 1, so a search of m evaluations fits while (m + 0.5)·t ≤ 44: a typical 12-evaluation one-variable search up to about 3.5 s per solve, the start and the scan (10) up to about 4.2 s. The "evaluations" column counts what the rule starts (R, N-N8):

| Network | Per solve | Evaluations started | One variable (about 12) | n = 2 (median 7, p90 11) |
|---|---|---|---|---|
| ≤ 31 components | 13–106 ms | 414–3,384 | fits | fits |
| Crane ladder, 99 components | 0.58 s | 75 | fits (met in 10 solves, 4.1 s) | fits |
| Crane ladder, 205 components | 1.40 s | 30 | fits (10 solves, 9.8 s in the prototype's run) | fits |
| Crane ladder, 499 components | 4.40 s | 9 | budget binds: the best of 9 evaluations (the start and 8 scan points; at the prototype's 3.28 s per solve, 12 start and it met in 10 solves, 33.6 s) | fits at the median (7 solves, 31 s); binds at p90 |
| Ideal ladder, 999 components | 1.62 s | 26 | fits (10 solves, 17.0 s) | fits |
| Crane ladder, 999 components | 11.4 s | 3 | budget binds (the start and the two bounds, not met) | budget binds |

### 3.9 Determinism

- There is no randomness: every evaluation is a cold solve, and the scan order, `brentq`, `minimize_scalar` and dogbox are deterministic. Evaluations are cached by exact values, and ties are broken by index.
- The same request gives identical evaluations, values and messages, apart from `seconds`, `computeTime` and `timestamp`.
- The exception is a run stopped by `time_budget`, whose stopping point depends on the machine. Its message says so.

### 3.10 Constants (`services/goal_seek.py`)

| Constant | Value | Where from |
|---|---|---|
| `SCAN_INTERVALS` | 8 (9 points, solved coarse to fine) | N: K = 4 finds 11 of 16 multi-root problems, 8 finds 15, 16 finds 16 at twice the cost; R (N-N8): the order |
| `STOP_FRACTION` | 0.1 | N: +1 solve; 362 of 364 stay met at 6 digits |
| `BRACKET_XTOL` | 10⁻¹⁰ of u | N: steep continuous crossings beside jumps are met at this resolution; R (N-N2): at 10⁻⁶ a crossing beside a check valve's opening would be called a jump |
| `BRENT_MAXITER` | 200 | backstop; the cap binds first |
| `MINIMIZE_XATOL` | 10⁻⁵ of u | N: 10⁻¹² wasted 30+ solves converging onto a bound |
| `PROBE_ROUNDS` | 4 | N; S (G16: 8 probes) |
| `PLATEAU_TIE` | 10⁻³ of a tolerance | N |
| `JACOBIAN_STEP` | 10⁻⁶ of u | N: relative error median 1.0×10⁻⁶, max 9.2×10⁻⁶; round-off dominates below 10⁻⁸ |
| `LSQ_TOLERANCE` | 10⁻¹⁰ (ftol, xtol, gtol) | N |
| `PENALTY_FACTOR`, `PENALTY_FLOOR` | 10, 1000 tolerances | N |
| `EVALUATIONS_ONE`, `EVALUATIONS_PER_VARIABLE` | 60; 20 per variable + 20 | N; R (N-N2): 60 for one variable, sized for a jump |
| `TIME_FACTOR`, `TIME_RESERVE_S` | 1.5, 1 s | N |
| `NO_EFFECT`, `COLLINEAR` | 0.1 tolerance per range; 10⁻⁴ | S, from N's noise measurements |
| `FLOW_FLOOR` (state changes) | 10⁻⁶ m³/s: an element with no flow above it in either state has no state change | R (W-R13), the flow tolerance floor (D13) |
| `SIGNIFICANT_DIGITS` | 6: the `sensitive` note rounds the value found to 6 significant digits in SI and tests that difference (§5.3) | N; R (N-N5): the rounding itself, not a relative constant |
| `MAX_GOAL_SEEKS` (`workers.py`) | `SOLVE_WORKERS − 1` = 1 goal seek in the pool at once | R (W-R4) |

The methods section states every one of these constants (§5.4), so a result is traceable to the search that produced it without a version label (decision 22).

### 3.11 Measurements

All were taken on the design container (4 CPUs, often at a load average of about 4), at `METHOD_VERSION` 1.2.0. Times are pessimistic.

| Measurement | Result | By |
|---|---|---|
| Plain solve, 936 corpus projects, 2 workers | median 50 ms, p95 160 ms, p99 287 ms, max 1.92 s (205 components) | A |
| Solve cost by size | 13–23 ms (3–8 components), 47–106 ms (15–31), 0.58 s (99, Crane), 1.40 s (205), 4.40 s (499), 1.62 s (999 ideal: apply 0.39 s, state and trace 1.12 s), 11.4 s (999 Crane: outer loop 9.7 s) | N |
| Trial build (deep copy of the dump + validate) | median about 1 ms, max 63 ms under load; unloaded at 205 components: validate 14 ms, `build_network` 34 ms | A |
| Response sizes | `SolvedState` 3.59 MB raw / 127 KB gzip at 205 components; 1.72 MB / 79 KB at 99; 16 MB before gzip at 999 (0.2 s to serialize, 0.1 s to parse the body) | A, N |
| Scans | 1,204 scans of 41 points over 12 variable families, 67,260 solves: 94.6 % converged, 5.4 % did not, 7 `CONTROLLED_PUMP_SETPOINT`, 3 fluid errors; failures in regions (99 scans at an end or throughout; 8 interior runs) | N |
| Shape of 23,082 moving goal series | 94.8 % monotone, 3.4 % one turning point, 1.9 % several; 26.9 % with a plateau, 7.4 % with a gap | N |
| One variable, 360 reachable targets (solves to tier 0: median / p90 / max) | bounds + brentq 4/8/16 (0 of 16 multi-root found); scan K=4 6/8/13 (11); **scan K=8 10/11/16 (15)**; K=16 18/19/22 (16); secant from the start met only 337 | N |
| Prototype, one variable, 180 problems run twice | reachable 180/180 met (11/12/14); unreachable 0 met, correctly (10/10/32; 61 on a plateau); jump targets: 1 jump, 5 unsolved crossings, at most 40 solves (the same at a cap of 60, R); 366/366 runs identical | N |
| Several variables, reachable (met; solves median / p90 / max) | dogbox n=2 67/68 (7/11/16), n=3 69/70 (13/21/35), n=4 46/50 (16/32/100); trf n=2 67/68 (13/19/28), n=3 67/70 (21/33/80), n=4 45/50 (26/66/100); Broyden and damped Newton stalled in 6–24 % | N |
| Several variables, unreachable (one target moved 1,000 tolerances), dogbox | n=2 9/21/60, n=3 24/71/80, n=4 30/70/100 solves; trf about twice | N |
| trf on corpus draws (A's prototype, cap 100) | n=1–4 met 98.8 %, 96.7 %, 97.3 %, 97.0 %; n=4 met in p99 56 evaluations; 9 of 595 at the cap | A |
| Noise and finite differences | goal over x(1 + j·10⁻¹³) spreads by median 1.3×10⁻¹⁰, max 5.5×10⁻⁹ of a tolerance; forward differences at 10⁻⁶ of the range: relative error median 1.0×10⁻⁶, p90 4.4×10⁻⁶, max 9.2×10⁻⁶ | N |
| Rounding a met value | 6 digits: 2 of 364 no longer met (p99 0.01 tolerance); 4 digits: 4 of 364 (p99 1.45). Pump-transfer example: exact 15.0000000069 L/s, 6 digits 14.999987, 4 digits 15.000764 | N, W |
| Zero targets | zero-flow targets met with \|Q\| from 2×10⁻¹⁰ to 8×10⁻⁹ m³/s in 12–18 solves | N |
| Determinism | the base solved twice identical in all 1,204 scans; 45 projects × 5 `PYTHONHASHSEED` values identical (SHA-256 of the state) | N |
| Bit-identity of the trial | the case dump with values written equals the scenario with the variables as overrides: models, `fields_set` and solves (a pump fixture with a scenario overriding speed, the whole fluid and a level; variables speed, temperature inside the fluid, a Cv and a length) | A; N on a scenario |
| Closed-form inverses | R1's level for 0.02 m³/s: 6.51143499 m against 6.511434137 m (12 solves); pump speed for 0.01/0.02/0.025 m³/s: \|Δs\| 3.5×10⁻⁷, 1.5×10⁻⁶, 2.6×10⁻⁵; speed for 230/280 kPa: \|Δs\| 2.7×10⁻⁶, 8.2×10⁻⁶; a two-variable duty point met in 10 solves | N |
| Controlled pump across its setpoint (G16) | 260.9 → 9.6 kPa(g) across 20 L/s; not converged within at least ±10⁻⁹ m³/s, converged at ±10⁻⁷; §3.3 on it: unsolved crossing after 34 evaluations | S |
| SciPy 1.18.1 | dogbox keeps a start on a bound, trf moves it 10⁻¹⁰ inside; `max_nfev` excludes Jacobian evaluations | S |
| Rate limiting | `RATE_LIMITED_PATHS = ("/api/v1/solve", "/api/v1/system-curve")`: goal seek must be added | S |
| Coordinate map (N-N1, W-R3) | the plain log map at u = 1 exceeds an upper bound of 10⁷ in 19,555 of 20,000 random lower bounds (10⁶: 653), falls below `lower` at u = 0 in 33 %, and misses the start in 69 % of log round trips (0.6 % linear); `FlowCoefficient` rejects its 10000000.000000006. §3.1's map: 0 of 1,300,000 trials outside the bounds, ends and start exact in 100,000 of 100,000 ranges (linear and log, field maxima included), the middle start equal to the scan's k = 4 point in 10,000 of 10,000; dogbox in shifted coordinates calls v0 = 0 first | R (review's `mapping.py`; `reviser/mapping_fix.py`) |
| Closing a jump (N-N2) | brentq at xtol 10⁻¹⁰ from a 1/8 bracket around a step: median 32 solves (p90 39, max 50); with the start and scan, 1,690 of 2,000 exceed 40. Cap 60: 2,000 of 2,000 named, 1,996 of 2,000 also meet a root in the next bracket (median 44 solves). The prototype's 6 jump targets on real networks: 32–40 solves, outcomes identical at caps 40 and 60. The review's next-bracket case: `evaluation_limit` at 40; met after 41 at 60 | R (review's `brent_jump.py`, `next_bracket.py`; `reviser/cap60.py`, `jumps_cap60.py`, `next_bracket_cap60.py`) |
| A steep continuous crossing at a switch (N-N2) | real solves of `check_valve_cracking_pressure`, R2's level over [0, 20.5] m: the valve closes at 14.2847682215 m (u = 0.6968); the flow on the open side is continuous, 6.0×10⁻⁶ m³/s at 10⁻⁶ of u from the switch and 5.7×10⁻⁵ at 10⁻⁵ (linear at laminar flows). A target of 2.98×10⁻⁶ m³/s has its root 5×10⁻⁷ of u from the switch, with residuals of −3.0 and +3.0 tolerances at the ends of a 10⁻⁶ bracket whose states differ: a 10⁻⁶ jump rule would call it a jump | R (`reviser/cv_opening.py`) |
| Dogbox's first trust radius (N-N3) | a linear two-variable problem, solves to tier 0: u0 = 0 or 0.5: 4; 0.05: 13; 0.01: 22; 0.001: 31; (10⁻⁴, 0): 40. Shifted to the start: 4 from every start. A nonlinear one: 16–49 unshifted, at most 16 shifted | R (review's `dogbox_radius.py`, `dogbox_shift.py`) |
| Penalty columns (N-N6) | 300 problems whose root lies where trials fail: 12 end `no_progress`, all 12 with a false `variables_collinear` (σ_min/σ_max 1.3×10⁻⁷ against a true 0.81); diagnosing known columns only: no false note. 400 problems starting at a failure edge with the root 0.05–0.3 behind: penalty column 2 met (338 `no_progress`, 60 at the cap); backward retry 400 met in 5 solves | R (review's `penalty_diag*.py`; `reviser/penalty_fix*.py`) |
| Rounding to 6 digits (N-N5) | relative change up to 4.97×10⁻⁶, above 5×10⁻⁷ for 61 % of values (0.1000004 → 0.1: 4×10⁻⁶) | R (review's `rounding.py`) |
| Web and API code (W-R1, W-R5, W-R8, W-R9, W-R12, W-R14) | `#restale` returns when no case has results (`project.svelte.ts` 673–675); seven controls in five components start a solve, each with its own busy test (`CompareView` 86, `ResultsStateNotice` 20, `ResultsPanel` 394 and 627, `WorkspaceHeader` 55, `ScenarioBar` 27), "Solve now" with none; a control valve without a resistance is ideal, `kOpen` 0 (`valves.py` 17–18); `npshAvailable` is computed at zero flow, `npshMargin` only for a running pump (`results.py` 723, 786–791); `newId` takes the first unused id and reserves only scenario-named ids (`factory.ts` 174–201); every non-topology 4xx becomes a `ValidationError` (`client.ts` 247–257) | R |

---

## 4. API

### 4.1 Endpoint (`routers/goal_seek.py`, new)

```python
@router.post("/goal-seek", response_model=GoalSeekResponse,
             responses={**_ERRORS, 404: {"model": ErrorResponse,
                                         "description": "Unknown scenario, element, port or pipe"}})
async def goal_seek_endpoint(request: GoalSeekRequest, http: Request) -> GoalSeekResponse:
    """Find the variable values that bring the goals to their targets (PRD §3.9). Every
    evaluation is a full solve of the case (the base or scenarioId) with the variables written on
    top. A goal not met is 200 with success = false; computeTime is the worker's time."""
    outcome, seconds = await run_solve(http, _client(http), goal_seek_case, request)
    return GoalSeekResponse(success=outcome.result.met, result=outcome.result,
                            solved_state=outcome.state, compute_time=seconds,
                            scenario=outcome.scenario)
```

`_ERRORS` and `_client` move from `routers/solve.py` to a shared `routers/_common.py`, unchanged.

### 4.2 Order of checks and errors (`goal_seek_case`)

1. **Request validation.** 400 `VALIDATION_ERROR` (§2.5).
2. **Scenario** (`scenarioId` given): `apply_scenario`. An unknown id gives 404 "the project has no scenario 'S9'"; invalid values give 400 `ScenarioOverrideError`. Both are exactly as for `/solve`.
3. **The case fluid.** `fluid_properties(case.fluid)`: 400 `FLUID_ERROR` (`ScenarioFluidError` names the scenario id).
4. **Targets.** Every variable and goal is resolved against the case. An unknown component, connection, pipe index or port gives **404** `NOT_FOUND`, "Goal seek: N unknown element(s).", with one issue per problem. Each issue carries its ids in `componentIds` and `connectionIds`:
   - `body.variables.0: the project has no component P9`
   - `body.goals.1: component T3 has no port 'branch'`
   - `body.variables.2: connection L3 has 1 pipe, no pipe 3`
5. **Inputs.** **400** `VALIDATION_ERROR`, "Goal seek: N input problem(s).", every problem listed. As SDD §5.1.2 requires of every `VALIDATION_ERROR`, no message holds an id or a submitted value: each issue carries the element's id in `componentIds` or `connectionIds` and names the element by its kind:
   - **A variable whose target lacks the value:**
     - "body.variables.0: a reservoir has no speed ratio to vary";
     - "body.variables.1: the pump has no speed control in this case (control.setpoint applies to a speed-controlled pump)";
     - "body.variables.2: the fluid is a custom fluid, whose properties do not depend on its temperature".
   - **A goal on the wrong element:** "body.goals.0: pump_head applies to a pump, not a tee".
   - **An excluded outflow:** "body.goals.0: an assigned-flow node's outflow is its input (−flow): vary it instead".
   - **NPSH data missing:**
     - "body.goals.1: NPSH needs the fluid's vapor pressure; the case's fluid has none (set one as a property override)";
     - "body.goals.1: the NPSH margin needs an NPSHr curve on the pump's curve".
   - **A user tolerance below its minimum:** "body.goals.0.tolerance: below the smallest this search resolves (10⁻⁶ of the target's magnitude, or {minimum} {unit}, whichever is larger)", with the quantity's published minimum (§2.2), a constant. The message has no numbers from the request.
6. **The case's topology.** `build_network(case, fluid)`: 422 `TOPOLOGY_ERROR`, exactly as for `/solve` (`ScenarioTopologyError` names the scenario).
7. **Bounds.** No solve runs. For each variable i and each of `lower` and `upper`, the bound is written (the other variables at their starts) and validated. Errors are collected as 400 at `body.variables.{i}.lower` or `.upper` with the schema's own message: "Input should be less than or equal to 1", or "Value error, minSpeed must be below speed (the maximum speed of a speed-controlled pump)". Topology and fluid errors at a bound are not checked here (§3.6).
8. **The search.** From here the response is always 200 (§3), except for 503 `TIMEOUT` when the first evaluation does not finish, and a cancellation.

**Exceptions**, with handlers in `main.py`:

| Exception | Status |
|---|---|
| `GoalSeekNotFoundError(LookupError)` | 404 with issues |
| `GoalSeekInputError(ValueError)` | 400 with issues |

The case's topology and fluid errors reuse `TopologyError` / `ScenarioTopologyError` and `FluidError` / `ScenarioFluidError` and their handlers. 503 `SERVER_BUSY`, 429 and 413 behave as for `/solve`.

**Measured cost of steps 3 to 7:** under 0.4 s at 205 components with n = 4.

### 4.3 Worker pool, budget, rate limit

- **One request, one budget.** One goal seek is one `run_solve` call: one 45 s budget from arrival, the per-client turn (a second request waits, a third is refused) and `MAX_SOLVES_IN_FLIGHT` unchanged. It holds one of the 2 workers for at most 45 s, as a large solve does.
- **One goal seek in the pool.** `workers.py` counts goal seeks from their submission to the end of their work (released in `run_solve`'s `finished` callback, as `_submitted` is, so a cancelled one counts until it has stopped). It admits at most `MAX_GOAL_SEEKS = SOLVE_WORKERS − 1` (1), checked where `MAX_SOLVES_IN_FLIGHT` is; another gets 503 `SERVER_BUSY` with `Retry-After` at once, without waiting. Without it, two clients' goal seeks would hold both workers for up to 45 s, and a third client's 50 ms solve, whose budget counts from its arrival, would wait behind them and fail with 503 `TIMEOUT`. A plain solve always has a worker that no goal seek holds. System curves, which can also run long on large networks, are unchanged (§9).
- **Rate limit.** `/api/v1/goal-seek` is added to `RATE_LIMITED_PATHS`. One goal seek counts as one request.
- **Cancellation.** A client that disconnects (the web's Cancel aborts the request) cancels the run at its next check: before the next evaluation, or inside the solver.

### 4.4 Scenarios

- **The case.** The case is `apply_scenario(project, scenarioId).project`, and the variables are written on top of it. A variable that the scenario overrides starts at the scenario's value (`caseValue`), with `baseValue` the base's.
- **Shared code.** `services/scenarios.py` exposes its planner and writer for goal seek: `plan_override(project, index, override)` and `write_override(data, plan)`, renamed from `_plan` and `_write` with the same behaviour, plus the labels, units and `COMPONENT_NAMES`. Goal seek builds a `ComponentOverride`, `PipeOverride` or `ProjectOverride` for each variable, plans it against the case, and maps the planner's states:
  - `orphaned` → 404 (§4.2 step 4), whose messages may name ids (D10);
  - `not_applicable` → 400 (step 5), with goal seek's own messages ("in this case", not "in the base project") and without ids: the planner's `MISSING_HOLDER` texts format the id, so goal seek words its own (§4.2 step 5) and puts the id in `componentIds`.

  `apply_scenario`'s behaviour and messages stay identical, and its tests are unchanged.
- **`override`** sets the value found, ready to apply:
  - for a component: `{kind: "component", componentId, field, value: x}`, a resistance with `{kind, value}` as its value;
  - for a pipe: `{kind: "pipe", connectionId, pipeIndex, field: "length", value: x}`;
  - for the fluid: `{kind: "project", field: "fluid.temperature", value: x}`. When the case's scenario overrides the whole fluid, it is `{kind: "project", field: "fluid", value: <that fluid with temperature x>}` instead, since a scenario never holds both (D15).

  Upserted into a scenario by (target, field), or written into the base at its path, it reproduces the trial (§6.10).
- **The scenario record.** The response's `scenario` is the case's `ScenarioResult` as stored, as `/solve` reports it (orphaned and not-applicable overrides included), so `/solve`'s model is unchanged. Its `value` for an override is the scenario's. Where a variable replaced that value, the variable's `replacedOverride` gives the override's index: for a component, pipe or project override with the variable's target and field, and for a whole-fluid override that holds the temperature varied (the value found replaces its temperature only). The field's description says so, and the methods text marks the override (§5.4).

### 4.5 Privacy

- **Nothing new is logged.** The body is never logged (middleware), and the scenario id, variables and goals travel only in the body.
- **Validation errors.** `VALIDATION_ERROR` messages locate by index and use the schema's messages or goal seek's fixed texts; ids go only in `componentIds` and `connectionIds` (SDD §5.1.2).
- **Other errors.** 404 messages name ids (D10). Topology and fluid errors name the value or id at fault, as for `/solve`. A scenario is named by id only in errors.
- **Results** go only to the requester. The project's own names appear in results (the methods section), never in error messages.

---

## 5. Results, traces and methods text

Every number in a message is SI and written `:.6g` with its unit. Labels use ids, as the Scenario section does. The web words codes itself, with names and display units (§6.9). An unknown code shows the API's sentence.

### 5.1 Labels

- **Variables** (from `override_label`, `COMPONENT_NAMES` and `pipe_name`):
  - "liquid level of reservoir R1";
  - "surface pressure of reservoir R1";
  - "pressure of reference node RN1";
  - "assigned flow of assigned-flow node AF1";
  - "speed ratio of pump P1", or "maximum speed ratio of pump P1" for a speed-controlled pump;
  - "flow setpoint of pump P1";
  - "setpoint of control valve V2";
  - "resistance coefficient K of check valve CV1", or "flow coefficient Cv of gate valve V1" (Kv the same);
  - "length of connection L3, pipe 1";
  - "fluid temperature".
- **Goals:**
  - "static pressure at port outlet of tee T3";
  - "flow in connection L1";
  - "largest velocity in connection L1";
  - "head loss in connection L1";
  - "flow through pump P1";
  - "head of pump P1";
  - "NPSH available at pump P1";
  - "NPSH margin of pump P1";
  - "flow through valve V1";
  - "pressure drop across valve V1";
  - "outflow of reservoir R1".

### 5.2 Messages (`result.message`, by stop reason)

| Stop reason | Message |
|---|---|
| `met_at_start` | "The case already meets every goal: nothing to change." |
| `met` | "Every goal is met, after {k} evaluations." |
| `not_reachable`, at a bound | "Goal {j} is not met: at none of the {k} values of {variable} solved across the bounds (8 equal steps{ in log x}) does its residual change sign, and the closest, {g}, is at the {lower \| upper} bound, {x} (target {t}). A crossing between two solved values is not excluded." |
| `not_reachable`, on a plateau | "Goal {j} is not met: it stays at {g} for {variable} from {a} to {b} (the results do not change there); at none of the {k} values solved across the bounds (8 equal steps{ in log x}) does its residual change sign, and none comes closer to the target {t}. A crossing between two solved values is not excluded." |
| `not_reachable`, inside | "Goal {j} is not met: at none of the {k} values of {variable} solved across the bounds (8 equal steps{ in log x}) does its residual change sign; the closest it comes to the target {t} is {g}, at {x}, a minimum of the residual's magnitude between solved values. A crossing between two solved values is not excluded." |
| `jump`, with state changes | "Goal {j} jumps across its target between {variable} {x1} and {x2}, from {g1} to {g2} ({changes}), so no value there meets it; the closest value solved, {g} at {x}, is reported." |
| `jump`, without | "Goal {j} jumps across its target between {variable} {x1} and {x2}, from {g1} to {g2}, with no element that carries flow changing state there: the crossing is steeper than this search resolves (10⁻¹⁰ of the range); the closest value solved, {g} at {x}, is reported." |
| `unsolved_crossing` | "Goal {j} crosses its target only between {variable} {a} and {b}, where the solve {does not converge: {message} \| is rejected: {message} \| has no value of the goal: {message}}; the closest solved value is reported." |
| `no_progress` | "The goals are not all met: the least-squares search from this start ended at its own tests with residuals of {r1, …} tolerances; the closest point found is reported. The search is local: values elsewhere in the bounds are not excluded." |
| `evaluation_limit` | "Stopped after {cap} evaluations, the limit for {n} variable(s); {every goal is met \| the closest evaluation so far is reported}." |
| `time_budget` | "The request's time budget of 45 s ran out after {k} evaluations; {every goal is met \| the closest evaluation so far is reported}. A run stopped by time can differ from one run to the next." |
| `no_usable_evaluation` | "No evaluation gave a usable result (the first: {message}); narrow the bounds, or check the case's own solve." |

Here {changes} is, for example, "pump P1 control max_speed → min_speed; valve CV1 closed → open", and lists only elements that carry flow in one of the two states (§3.1 step 6). {k} counts the usable values solved. The `jump`, `unsolved_crossing` and `not_reachable` messages appear only when no evaluation meets the goal (§3.5).

### 5.3 Notes (`result.notes`, repeated in the methods section)

| Code | Data | Message |
|---|---|---|
| `other_crossing` | goals, `variableValues` [a, b] | "Goal {j} also crosses its target between {variable} {a} and {b} (not solved); narrow the bounds to that range to find that value." |
| `met_range` | `variableValues` [a, b], `evaluations` (the met ones) | "{m} of the values of {variable} solved, from {a} to {b}, meet the goals; the one reported is the nearest the start among those within a tenth of the tolerance, or, with none, among those within it." |
| `met_without_crossing` | goals | "Goal {j} is met at a value where its residual does not change sign (no crossing of the target was solved there): values near it may meet it too." |
| `closest_at_bound`, `closest_on_plateau`, `closest_inside` | variables, goals, values | the data of §5.2's three `not_reachable` messages |
| `jump` | `variableValues` [x1, x2], `goalValues` [g1, g2], `stateChanges` | §5.2's jump message (kept when a later bracket meets the goal) |
| `unsolved_crossing` | `variableValues` [a, b], `evaluations` [the unusable one] | §5.2's message |
| `state_changes` | `stateChanges` (start → reported) | "At the values found, these elements' states differ from the start: {changes}." (elements that carry flow in one of the two states, §3.1 step 6) |
| `start_clipped` | variables, `variableValues` [case value] | "{Variable}: the case's value {v} lies outside the bounds; the search started at the {lower \| upper} bound." |
| `unusable_evaluations` | `evaluations` | "{k} of {m} evaluations gave no usable result (the first, evaluation {i}: {message}); the search went around them." |
| `goal_no_effect` | goals | "Goal {j} did not change at any evaluation (by more than 10⁻³ of its tolerance): no variable moves it here." |
| `variable_no_effect` | variables | "{Variable} moves no goal near the point reported (across its whole range, at this slope, by less than a tenth of a tolerance)." |
| `variables_collinear` | variables | "{Variables} change the goals in the same proportion near the point reported: vary one of them, or choose goals they affect differently." |
| `slope_unknown` | variables, `evaluations` (the unusable slope steps) | "{Variable}: its effect on the goals near the point reported is unknown, because its slope trials gave no usable result (evaluation {i}: {message}); the search could not use it there." |
| `sensitive` | variables, goals, `evaluations` [the two whose difference gave the slope], `variableValues` [x, round6(x)], `goalValues` [the estimated change] | "Goal {j} is sensitive to {variable}: apply the value found exactly (rounded to 6 significant digits, {x6}, it moves the goal by about {Δg}, more than its tolerance {tol})." |

`sensitive` is noted when |∂g_j/∂x_i| × |round6(x_i) − x_i| > tol_j, where round6 rounds the value found to 6 significant digits in SI, as the messages write it (`SIGNIFICANT_DIGITS`). The test uses the value's own rounding, which changes a value by up to 5×10⁻⁶ of itself (leading digit 1) and by more than 5×10⁻⁷ for 61 % of values, so no constant stands in for it (R, N-N5). The slope comes from the final bracket's two ends (one variable) or from the last Jacobian's column and its base point (several), named in `evaluations`, and the note costs no solve. The web shows display units, which round the same digits except for temperatures in °C or °F; its wording names no number.

### 5.4 The "Goal seek" methods section

It is the first section of `solvedState.trace.methods`, before "Scenario" and the solver's sections, and it is also `result.methods`. Its items:

1. **Opening.** For the base: "Goal seek on the base case of this project: {n} variable(s) were varied within their bounds to bring {n} goal(s) to their targets. Each evaluation is a full network solve of the case with the variables set to trial values, by the methods in the sections below; nothing is approximated. The values found are not applied to the project: every result below is of the case with them, and applying them gives these results."

   For a scenario, the opening names the case: "Goal seek on scenario '{name}' (id {id}) of this project: …". After "nothing is approximated." it adds: "The variables are written on top of the scenario's values: where the scenario sets a variable's value, the value found takes its place." Then: "The values found are not applied …".
2. **Method, one variable.** "Method (one variable): the case's value, clipped into the bounds, is solved first, then the 9 values that divide the bounds into 8 equal steps ({linearly | in log x}), solved coarse to fine (the bounds, the middle, then the quarters and eighths). A value within a tenth of the tolerance ends the search, the one nearest the start when several are. Otherwise, where the residual (the goal's value minus its target) changes sign between neighbouring solved values, Brent's method (scipy.optimize.brentq, xtol 10⁻¹⁰ of the range) searches the bracket nearest the start and stops at the first value within a tenth of the tolerance; a bracket that closes with both sides more than one tolerance from the target is a jump, and a bracket that ends at a jump or at failed solves gives way to the next. With no sign change among the values solved, the closest value is reported: at a bound, on a plateau (values within 10⁻³ of a tolerance of each other), or refined by Brent's bounded minimization of the residual's magnitude (scipy.optimize.minimize_scalar, xatol 10⁻⁵ of the range) between the closest value's neighbours. A crossing narrower than the scan's steps can be missed."
3. **Method, several variables.** "Method ({n} variables): the case's values, clipped into the bounds, are solved first; then a trust-region least-squares search (scipy.optimize.least_squares, method 'dogbox') minimizes the sum of the squared residuals, each divided by its goal's tolerance, within the bounds, with each variable scaled to its range ({names} in log x) and measured from the start, so that the first trust region spans each whole range, a forward-difference Jacobian (a step of 10⁻⁶ of each scaled range, one solve per variable, taken backward at an upper bound or when the forward trial gives no usable result) and ftol = xtol = gtol = 10⁻¹⁰. It stops at the first evaluation where every goal is within a tenth of its tolerance. The search is local: it reports the values it reaches from the start and does not look for others."
4. **Rules.** "A goal is met when its value is within its tolerance of its target. An evaluation whose solve did not converge, that has no value of a goal, or whose trial values the network rejects (a topology or fluid-range error) is never used as a residual: {one variable: the search goes around it, probing up to 4 times on each side | several: the least-squares search sees a residual of 10 times the largest so far, at least 1000 tolerances, in every goal}. At most {cap} evaluations are made ({60 for one variable | 20 per variable plus 20}), within the request's time budget of 45 s; an evaluation starts only while 1.5 times the slowest so far plus 1 s remains. An element's state counts as changed only when it carries more than 10⁻⁶ m³/s in one of the two states. {Several: a variable or goal is said to have no effect below a tenth of a tolerance across the range, and variables to act as one below a singular-value ratio of 10⁻⁴.}"
5. **Each variable.** "Variable {i}: {label}, bounds {lo} to {hi} ({linear | log}), start {x0} ({the case's value | the case's value {v}, clipped into the bounds | the middle of the bounds: the case's resistance is {the Crane TP-410 default for this valve type | ideal (no loss when fully open), a control valve's default | Cv 12}}); found {x}{, at its upper bound}."
6. **Each goal.** "Goal {j}: {label}, target {t}, tolerance {tol} ({default: 0.5 % of the target (CLAUDE.md D6), at least {floor}: {0.01 m of head (D6) | 0.01 m of head (D6), {p} Pa with ρ = {ρ} kg/m³, the case fluid's density at the case's own temperature, held for the whole search | the goal-seek default of 10⁻⁶ m³/s (D16, not in D6) | the goal-seek default of 10⁻³ m/s (D16, not in D6)} | entered}); achieved {g}, residual {r}: {met | not met}." With no value: "achieved: no value ({message})".
7. **Stop.** "Stopped after {k} evaluations ({s} s): {§5.2's message}"
8. **The notes** (§5.3), one item each.

References:
- `BRENT`, already in `services/solver/methods.py` (read, not changed).
- `BRENT_MINIMIZE` = "Brent, R. P. Algorithms for Minimization without Derivatives. Prentice-Hall, 1973, ch. 5 (scipy.optimize.minimize_scalar, method 'bounded')."
- `VOGLIS_LAGARIS` = "Voglis, C., and I. E. Lagaris. A rectangular trust region dogleg approach for unconstrained and bound constrained nonlinear optimization. WSEAS International Conference on Applied Mathematics, Corfu, 2004 (scipy.optimize.least_squares, method 'dogbox')." Several variables only.
- `DENNIS_SCHNABEL` = "Dennis, J. E., and R. B. Schnabel. Numerical Methods for Unconstrained Optimization and Nonlinear Equations. Prentice-Hall, 1983, §5.4 (forward-difference Jacobian)." Several variables only.
- `SCIPY` = "Virtanen, P., et al. SciPy 1.0: fundamental algorithms for scientific computing in Python. Nature Methods 17, 261–272, 2020."
- `GOAL_SEEK_DECISION` = "OpenSolve Pipe design decision D16 (CLAUDE.md), from docs/proposals/goal-seek.md." It is the source of the search's constants and of the flow and velocity floors.

The SciPy version is already in the summary's `libraries`.

**Scenario section marks.** In a scenario case, each item of the "Scenario" section, and each scenario element note, for an override a variable replaces, ends with "In this goal seek the value found takes its place (see Goal seek)." (for a whole-fluid override: "In this goal seek the value found takes the place of its temperature"). `scenario_section` and `element_notes` gain an optional `replaced: frozenset[int] = frozenset()` (override indices, the variables' `replacedOverride` values). `/solve` passes none, so its text is unchanged.

### 5.5 Element notes

Each varied component or connection gets one first note in its trace, before any scenario note:
- "Goal seek set the maximum speed ratio here to 0.858937 (case value 0.9, set by scenario 'Winter' (id S2)) to meet its goals; the inputs below are the goal-seek value."
- For a pipe: "Goal seek set the length of pipe 1 here to 41.3 m (case value 40 m) …".
- For a resistance on its default: "… the flow coefficient here to Cv 18.2 (case value: none, the Crane TP-410 default) …", or for a control valve "… the resistance coefficient here to K 3.2 (case value: none, ideal: no loss when fully open) …".

The fluid temperature gets no element note: the section states it, as D15 does. Trace input sources stay `user` and `default`.

### 5.6 No flags

The solved state keeps the solve's own flags. A goal not met is not physics (GOALS §4.6). It is in `result`, the methods section and the web's banner.

### 5.7 Versions

- `METHOD_VERSION` stays **1.2.0**, and `METHOD_CHANGELOG` is unchanged: every evaluation is the unchanged solve, and `result.methodVersion` names it.
- **No goal-seek version** (decision 22, after the review). GOALS §4.3 asks that a project record the method version that produced its results and that a later version's changes be disclosed; goal seek's values, once applied, are ordinary inputs, solved by `METHOD_VERSION`. The search itself is described where its result is: the methods section names the method, its citations and every constant of §3.10, and it travels in the response and the copied report. A label would have needed a changelog that `GET /api/v1/method-versions` does not serve and hand bumps. If reports need one, a label with a published changelog is a reversible addition (§10).
- `schemaVersion` stays 1: nothing is added to `Project` (D14).
- The corpus comparison of solves is untouched (§7.3).

---

## 6. Web

### 6.1 Rules the user can rely on

1. **Nothing changes until Apply.** A goal seek never edits the project. Apply is one undo step, and it says what it wrote and where.
2. **Every result names its case.** The dialog names the case it runs on, and a result keeps that case after a switch.
3. **Exact values.** Apply writes the floats the API found, never the displayed text, so the applied case's solve reproduces the values shown.
4. **Not met is said in words**, with the closest value, never as a silent clamp.
5. **One calculation at a time.** While a goal seek runs, Solve waits (it says why). Cancel stops either.
6. **Projects without scenarios** get the Goal seek button and nothing else new.

### 6.2 Entry points

1. **Results pane header** (`ResultsPanel.svelte`). A **Goal seek** button sits at the right end of the row with "Results", the case chip and the status line.
   - **Look.** The new `target` icon (a crosshair) with the label. Below 24 rem it shows the icon only, `w-11 px-0`, with `aria-label="Goal seek"`. Measured: 34 px wide without `w-11`, 44 px with it.
   - **While a goal seek runs,** the icon becomes the spinner (`motion-safe:animate-spin`) and the accessible name "Goal seek (running)".
   - **Always available.** Opening the dialog never needs a solve. On desktop, while a trace covers the results, the row is inert as today, and the trace's own entry applies.
   - `data-goal-seek-button` gives the dialog a focus target on close.
2. **Trace** (`TraceView.svelte`). A quiet text button **Use in goal seek** sits on the "Result values" heading of every element.
   - Its accessible name is "Use a result of {element} in goal seek".
   - It opens the dialog with the New goal form open, the element preselected (a connection, a pump, a valve, a boundary, or another component's first port), and focus on the Result radio group.
   - On phones the trace is itself a sheet, so it closes first (`ws.closeInspector()`): modals are never stacked.
3. **Not in the workspace header.** Measured with one more 44 px control after Scenarios:
   - at 640 px the project name falls from 155 to 103 px, and to 26 px while Cancel shows;
   - at 768 px a labelled button leaves 26 px for the name and scrolls the page 83 px sideways;
   - at 320 px the header takes three rows.

`Workspace.svelte` mounts `{#if ws.goalSeekOpen}<GoalSeekDialog />{/if}`, next to Settings and the Scenario manager. `ws.openGoalSeek(prefill?: ElementRef)` opens it.

### 6.3 Dialog layout (`workspace/GoalSeekDialog.svelte`)

- **Size.** The existing `Dialog`, with the title **Goal seek** and a new `xl` prop (`sm:max-w-2xl lg:max-w-5xl`). The content is `lg:grid lg:grid-cols-2 lg:items-start lg:gap-6`, and the result column is `lg:sticky lg:top-0`.
  - Measured at 1280 × 800: `xl` is 1024 × 680, with inputs of 166–192 px, and the result is in view beside the setup. The existing `wide` (672 px) puts the result below its 550 px body.
- **Intro.** "Finds the input values that make results reach their targets. Each trial is a full solve of the case; nothing in the project changes until you apply the values." Without scenarios it says "of the project".
- **Case line**, only when the project has scenarios: "Case [chip] (the case shown; switch it in the case bar)". The chip is slate for "Base case", or teal with the scenario name (`break-words`).
- **Sections:** `h3` "Results to reach (n)" with [+ Add goal], then `h3` "Inputs to change (n)" with [+ Add variable], then `h3` "Result" (`tabindex="-1"`).
- **Before any run,** the result column says "Add a goal and a variable, then Run goal seek." On phones the Run button's reason says it instead.
- **Footer**, the existing `footer` snippet, always visible: a status line (`basis-full` on phones, `mr-auto` from 640 px), Close, Cancel (only while running), and **Run goal seek** (primary).
- **Inputs never locked.** The dialog root calls `provideFieldMode({ scenario: false })`. Its inputs are page state, so none of them is locked in a scenario.

```
Desktop ≥ 1024 px
┌ Goal seek ───────────────────────────────────────────────────────────────────────────── [×] ┐
│ Finds the input values that make results reach   │ RESULT                                    │
│ their targets. …                                  │ ┌ ✓ Goal met ─────────────────────────┐   │
│ Case [Base case]                                  │ │ 12 trial solves in 0.4 s on the base │   │
│ RESULTS TO REACH (1)               [+ Add goal]   │ │ case.                                │   │
│ ┌ Transfer pump → Discharge valve · Flow  [🗑] ┐  │ └──────────────────────────────────────┘   │
│ │ Target [ 15     |L/s]  Tolerance [Default|L/s]│ │ Values found                              │
│ │ Last solve: 18.99 L/s. Positive from Transfer │ │  Transfer pump · Speed 86.1174 % (was 100 %)│
│ │ pump to Discharge valve. Default tolerance:   │ │ Results reached (table)                   │
│ │ 0.5 % of the target, at least 0.001 L/s.      │ │ [Apply to base case] [Apply as new scenario]│
│ └───────────────────────────────────────────────┘ │ [Copy report]                             │
│ INPUTS TO CHANGE (1)            [+ Add variable]  │ ▸ Trial solves (12)                       │
│ ┌ Transfer pump · Speed                    [🗑] ┐ │ ▸ Method                                  │
│ │ Now 100 %    From [ 20 |%]   To [ 100 |%]      │ │                                           │
│ └───────────────────────────────────────────────┘ │                                           │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ (status line)                                                    [Close] [▶ Run goal seek]    │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
Phone 390 × 844: bottom sheet 92 dvh (776 px, scroll body 646 px), one column: intro, case, goals,
variables, result. Footer 77 px idle, 97 px running: the status line on its own row, then
[Close] [× Cancel] [Seeking…].
```

### 6.4 Goals ("Results to reach")

**Catalogue.** `GOAL_QUANTITIES` in `utils/goal-seek.ts` maps each API quantity to its Compare quantity, reusing `QUANTITIES` (label, unit category, gauge flag, reader), `rowLabel`, `rowUnit` and `rowElement`:

| Picker group | Result | API `quantity` | Compare | Hint (sign) |
|---|---|---|---|---|
| Ports (every port) | Pressure | `port_pressure` | `portPressure` | Static pressure at the port, gauge |
| Pipe connections | Flow | `link_flow` | `linkFlow` | Positive from {from} to {to} |
| Pipe connections | Largest velocity | `link_velocity` | `linkVelocity` | The largest in the connection's pipes; never negative (to target zero or a direction, use Flow) |
| Pipe connections | Head loss | `link_head_loss` | `linkHeadLoss` | Energy-grade-line drop from {from} to {to} |
| Pumps | Flow | `pump_flow` | `pumpFlow` | Positive from suction to discharge |
| Pumps | Head | `pump_head` | `pumpHead` | |
| Pumps | NPSH available | `pump_npsh_available` | `pumpNpsha` | Only for a fluid with a vapor pressure |
| Pumps | NPSH margin | `pump_npsh_margin` | `pumpNpshMargin` | NPSHa − NPSHr; only for a curve with NPSHr; none when the pump carries no flow |
| Valves | Flow | `valve_flow` | `valveFlow` | Positive from inlet to outlet |
| Valves | Pressure drop | `valve_pressure_drop` | `valvePressureDrop` | Inlet minus outlet static pressure |
| Reservoirs and reference nodes | Outflow | `boundary_outflow` | `boundaryOutflow` | Positive into the network |

A quantity whose `needs` (`x-goal-quantities`) the case lacks is shown unavailable with its reason, for example "NPSH margin (the pump's curve has no NPSHr)".

**New goal form.** "Add goal" opens an inline `fieldset` "New goal" (never a nested dialog):
- a filter input when more than six elements exist;
- **Element:** a `<select>` with `optgroup`s in the table's order. Labels read "Outlet of Far user tee", "Transfer pump → Discharge valve" or "Transfer pump". Elements come from `ws.labelsProject`.
- **Result:** radio buttons for the group's quantities. A result already used shows checked and unavailable, "(already a goal)".
- [Add goal] [Cancel]. After Add, the new card appears at the end and focus goes to its Target. Cancel returns focus to "Add goal".

**Goal card.** A `<fieldset>` whose `<legend>` is `rowLabel(…)`, for example "Outlet of Far user tee · Pressure", with an icon button "Remove goal {label}".
- **Target:** a required `NumberField` in the display unit of the quantity's category: "bar(g)" or "psig" for a port pressure, "bar" or "psi" for a pressure drop. It has no default: the target is the user's question.
- **Tolerance:** an optional `NumberField` with the placeholder "Default", in the same category as a difference, with `exclusiveMinimum: 0` from the schema and a `minimum` of max(10⁻⁶ × |target|, the quantity's `minimum.absolute`) from `x-goal-quantities`, which moves with the target. So every tolerance rule is checked at the field, and Run never meets a 400 for it.
- **Hint**, one paragraph of up to three sentences:
  1. "Last solve: 18.99 L/s." from the case's latest converged response, or "Last solve (out of date): …", or "Last solve: no value (Transfer pump carries no flow)." Nothing when the case has no response.
  2. The sign convention from the table.
  3. "Default tolerance: 0.5 % of the target, at least {floor in display units}", worded from `x-goal-quantities`. For a pressure: "at least 0.01 m of head".

**Lapsed goals.** A goal whose element or port no longer exists shows "{id} (deleted): no longer exists" in its legend, with Remove, and blocks Run. Labels are always current names. A deleted element's id is never given to a new element while a row names it (§6.15), so a row never moves to another element; Undo of the deletion makes the row current again.

**Already used.** "(already a goal)" and "(already a variable)", and Run reasons 3 and 6, apply the published `x-goal-seek-rules` and `x-ordered-fields` (§2.4), never a copy of the request validator.

### 6.5 Variables ("Inputs to change")

**Catalogue.** It is read from `x-goal-variables`, never copied. An entry is offered when the case shown has the value (`valueOf(ws.project, target, field) !== undefined`, or the valve exists for a resistance).

| Element | Field | Label | Display | Offered when |
|---|---|---|---|---|
| Pump | `speed` | Speed; **Maximum speed** for a flow-controlled pump (`fieldLabelFor`) | % | always |
| Pump | `control.setpoint` | Flow setpoint | flow | the case's pump has flow control |
| Reservoir | `liquidLevel` | Liquid level | length | always |
| Reservoir | `surfacePressure` | Surface pressure | pressure, gauge | always |
| Reference node | `pressure` | Pressure | pressure, gauge | always |
| Assigned-flow node | `flow` | Assigned flow (+ demand, − supply) | flow, signed | always |
| PRV / PSV | `setpoint` | Outlet / Inlet pressure setpoint | pressure, gauge | always |
| FCV | `setpoint` | Flow setpoint | flow | always |
| Isolation, check, control valve | `resistance` | Resistance K, Cv or Kv, as the valve holds it (K on its default) | the coefficient | always |
| Pipe n of a connection | `length` | Length | length | always |
| Project | `fluid.temperature` | Fluid temperature | temperature | the case's fluid is built in |

- **Never variables:** statuses, a pipe's spec and the whole fluid. Plugs, tees and wyes are not listed.
- **Resistance.** The request's `coefficient` is the case valve's kind, or K when the valve has no resistance. "Now" then reads, by the valve's default: "default (Crane K {kOpen} at the connected diameter)" from the last solve for an isolation or check valve, or "ideal (K = 0, no loss when fully open)" for a control valve. To vary a Cv, the user sets the valve's resistance as a Cv in Build first. A kind select is Later.
- **Assigned flow.** Its bounds are signed and may cross zero; the label states the convention. The Build form's direction-plus-magnitude pair cannot express a range.

**New variable form.** The same shape as New goal: a `fieldset` "New variable" with Filter, Element and Value.
- **Groups:** Pumps, Control valves, Valves (resistance), Reservoirs, Reference nodes, Assigned-flow nodes, Pipes ("Pipe 2 of Suction tank → Transfer pump") and Fluid.
- A value already chosen is unavailable, "(already a variable)".
- After Add, the card appears with its default bounds, and focus goes to From.
- With nothing to offer, the form says: "This network has no values goal seek can change yet."

**Variable card.** A `<fieldset>` whose `<legend>` is "Transfer pump · Speed" (`changeTargetLabel` + `changeFieldLabel`), with "Remove variable {label}".
- **Now:** "Now 100 %", the case's value (`changeValueText`). It adds "(set by Winter)" when the active scenario overrides it, and ", outside the bounds: the search starts at the nearer bound" when it lies outside them.
- **From and To:** two `NumberField`s side by side (`grid grid-cols-2 gap-3`) in display units. Their bounds are the intersection (`intersectBounds`) of:
  - the field's schema bounds (`schemaBounds`, `setpointBounds(valveType)`);
  - `orderedBounds` (a controlled pump's maximum speed above its minimum speed);
  - each other, from the variable schema's `x-ordered-fields` (`lower` < `upper`, strict).

  An out-of-range entry is refused at the field, with the field's own message.
- **Hint:** "Defaults: 20 % to 100 %." while both bounds equal the defaults. It disappears once a bound is edited.

**Lapsed variables** block Run until they are removed or the case is switched back:
- "{id} (deleted): no longer exists" (the id stays reserved while the row names it, §6.15);
- "Transfer pump has no flow control" or "the fluid is a custom fluid" (the value no longer applies in the case shown);
- a pipe variable whose connection's pipe count or ends changed since it was chosen: "The pipes of Suction tank → Transfer pump changed since you chose Pipe 2; choose it again." Page state cannot follow pipes by identity as `carryChanges` does, so it lapses conservatively.

### 6.6 Default bounds (`utils/goal-seek.ts` `defaultBounds`)

They are pre-fill values only, clipped to §6.5's bounds and tested per row:

| Variable | From | To |
|---|---|---|
| Speed, fixed-speed pump | 20 % | 100 % |
| Maximum speed, flow-controlled pump | the smallest whole percent strictly above its minimum speed (`minSpeed < speed`: 0.5 gives 51 %, 0.505 gives 51 %); halfway between the minimum speed and 100 % when that would be 100 % (a minimum speed of 99 % or more) | 100 % |
| Pump flow setpoint | 10 % of the value now | 3 × the value now |
| FCV setpoint | 0 | 3 × the value now (10 L/s when it is 0) |
| PRV or PSV setpoint, surface pressure, reference-node pressure | 5 bar below the value now, not below 0 bar(g) unless the value now is | 5 bar above |
| Liquid level | 0 | the value now + max(20 m, 2 × the value now) |
| Assigned flow q | demand: 0; supply: 3q; zero: 0 | demand: 3q; supply: 0; zero: 10 L/s |
| Pipe length | the value now ÷ 10 | 10 × the value now |
| Fluid temperature | the fluid's range (`FluidInfo.temperatureRange`, or the freezing point at its concentration), shrunk 1 K inside each end; ±20 K around the value now when the library is not loaded | |
| Resistance | the value now ÷ 100 | 100 × the value now |

For a resistance on its Crane default (an isolation or check valve without a resistance), "the value now" is the last converged solve's `kOpen`, so the API's middle start (the geometric mean) is the case's own K. Without a result it is 1, giving 0.01 to 100. An ideal control valve (no resistance, `kOpen` 0) also gets 0.01 to 100: a log range cannot be centred on 0, and its middle start, K = 1, is labelled as such ("the case's resistance is ideal").

### 6.7 The case

- **Which case.** A goal seek runs on the case shown (`store.activeCase`), exactly as Solve does. The Run button's accessible name names it ("Run goal seek on Winter"); its visible label stays "Run goal seek".
- **The setup.** There is one setup per page, kept across case switches: goals and variables address elements, and the topology is the same in every case. The variables' "Now" values follow the case shown.
- **A result keeps its case.** After a switch, its first line says: "This goal seek ran on scenario Winter (you are viewing the base case)." Its Apply buttons still name Winter.
- **The request** carries `scenarioId` in the body only, and only for a scenario.

### 6.8 Run, progress and Cancel

**One calculation request at a time per page.** The page sends one request at a time: a solve, a Solve all run, a system curve or a goal seek.

| While… | Every Solve, Solve all and "Solve now" control | Run goal seek | Pump chart's system curve |
|---|---|---|---|
| a solve or Solve all runs | as today | `aria-disabled`: "A solve is running; wait for it or cancel it." | as today |
| a goal seek runs | `aria-disabled`: "A goal seek is running; Cancel stops it." (no spinner on Solve) | "Seeking…" (`aria-disabled`), with Cancel | a request in flight is cancelled when the goal seek starts; new ones wait for it |

- **Every entry point.** Seven controls in five components start a solve today, each with its own busy test from `store.run` and `store.solvingCase`: the header's Solve (`WorkspaceHeader`), Solve all in the case bar (`ScenarioBar`) and in Compare (`CompareView`, `canRun`), Solve and Solve all in the Results pane (`ResultsPanel`, `busy`), "Solve again" in `ResultsStateNotice` (`busy`), and "Solve now" in the Results pane, which has no test at all. All of them, and Run goal seek, read one store getter, `calculating: 'solve' | 'solveAll' | 'goalSeek' | null`, and take their reason from one helper (`calculatingReason`), so a new entry point cannot miss a goal seek.
- **The store refuses, it does not drop.** While a goal seek runs, `solve()` and `solveAll()` send nothing and return; while a solve or Solve all runs, `runGoalSeek()` sends nothing and returns. Only Cancel (`cancelSolve()`, `cancelGoalSeek()`), `load()` and `dispose()` stop a request in flight. So a control that missed the getter still cannot cancel a goal seek by accident (decision 27).
- **Cancel.** The header's Cancel (`cancelSolve()`) also cancels a goal seek, with the accessible name "Cancel goal seek".
- **The case bar.** Solve all's reason is "A goal seek is running; Cancel in the header stops it.", and the bar's status line says "Goal seek running on {case}…".

**Run's reasons.** Run is `aria-disabled` with the first reason that applies, in `aria-describedby` and its `title`:
1. "Add a component to the network first."
2. "Add at least one goal and one variable."
3. "Goal seek needs as many goals as variables: 2 goals, 1 variable."
4. "Enter a target for each goal."
5. "Remove the goals and variables that no longer apply."
6. "Each variable needs its From value below its To value."
7. The reasons in the table above.

The other rules:
- **Limits.** Add is unavailable at `itemLimit('GoalSeekRequest', 'variables')`: "A goal seek takes at most 4 variables."
- **Input problems** ("Inputs to check") never block Run.
- **Clicks.** Run ignores the second click of a double click (`event.detail > 1`), and checks its reasons at click time.

**Running.**
- **Status line.** "Running on the base case… 12 s. A goal seek stops by itself after at most 45 s." The seconds tick in an `aria-hidden` span. 45 s is `GOAL_SEEK_BUDGET_S`, with a comment pointing at `workers.REQUEST_BUDGET_S`.
- **No trial counts:** one request, no streaming (§10).
- **Buttons.** Run becomes "Seeking…" with the spinner, keeping its width (both labels share one grid cell), and Cancel appears to its left.
- **The result column** shows "Running…"; a previous result is hidden and comes back if the run is cancelled.
- **Editing.** The setup stays editable, and edits affect the next run only. A result always shows the setup as sent.

**Cancel, close and the end of a run.**
- **Cancel** (in the dialog or the header) aborts the request; the server stops at its next check (D10). A late answer is dropped. The result column says "Goal seek cancelled. Nothing in the project changed.", above any previous result, labelled current or out of date as before.
- **Closing** the dialog (Close, Escape, the backdrop) during a run does not cancel it. The results-header spinner and the header's Cancel show it is running.
- **The end, with the dialog open.** The live region announces the outcome. If the focus was on Run or Cancel, it moves to the Result heading, scrolled into view on phones; otherwise it stays where it is.
- **The end, with the dialog closed.** A workspace notice: "Goal seek on the base case finished: goal met. Open Goal seek to apply the values." It is an info notice; a failure is an error notice. It is not repeated in the dialog.

### 6.9 The result (`goal-seek/GoalSeekResult.svelte`)

It is rendered from the run's record (the request and project as sent, plus the response), never from the live setup.

**Banner.** Each banner has an icon and words: colour is never the only signal.

| Outcome | Look | Text |
|---|---|---|
| `met: true` | check, emerald | "Goal met" / "All 2 goals met". "{k} trial solves in {s} s on {case}." For `met_at_start`: "The case already meets every goal: nothing to change." (Apply hidden). With `evaluation_limit` or `time_budget`: "Stopped early, but every result is within its tolerance." |
| `not_reachable` | alert, amber | "Goal not met". "None of the {k} trial values of {variable} from {lo} to {hi} reaches {target} for {goal}: the results never cross it between them. The closest, {value}, is at {variable} {x} ({at the upper bound \| on a range where results do not change \| inside the bounds}). A narrow crossing between two trial values is possible; narrow the bounds to look closer, widen them, or change another input. You can still apply the closest value." |
| `jump` | alert, amber | "Goal not met". "{goal} jumps from {g1} to {g2} between {variable} {x1} and {x2} ({element states}), so no value there gives {target}. The closest value found is shown." |
| `unsolved_crossing` | alert, amber | "Goal not met". "{goal} crosses {target} only between {variable} {a} and {b}, where the network has no solution ({message})." |
| `no_progress` | alert, amber | "Goals not met". One sentence per goal not met: "The closest point found misses {goal} by {residual} (tolerance ±{tol})." Then the diagnosis notes. |
| `evaluation_limit` (not met) | alert, amber | "Stopped after {n} trial solves, the most one goal seek makes. The best point found is shown." |
| `time_budget` (not met) | alert, amber | "Stopped after {s} s, the time one request may take, with {n} trial solves. The best point found is shown." |
| `no_usable_evaluation` | alert, red | "No trial solve gave a result: {message}. Narrow the bounds, or check the case's own solve." |
| request error | alert, red | the Errors list below |
| cancelled | info, slate | "Goal seek cancelled. Nothing in the project changed." |

An unknown stop reason or note code shows the API's sentence (forward compatible). A `jump`, `unsolved_crossing` or `not_reachable` banner appears only when the goal is not met (§3.5); a met run whose search passed a jump shows "Goal met" with the jump among the notes.

**Values found.** A `dl` with one row per variable: "Transfer pump · Speed — **86.1174 %**, was 100 %".
- The value has 6 significant digits, as `NumberField` shows, so the Build field after Apply shows the same text.
- "at the lower bound" or "at the upper bound" is added from `atBound`.
- The exact SI value is in the row's `title` and in the report.

**Results reached.** A small table in its own sideways-scroll box, with the first column sticky. Columns: Result, Reached, Target, Off by, Tolerance, Met.
- **Reached** is formatted with `Formatter.value`, the results tables' precision.
- **Off by** is signed, with a true minus and 2 significant digits.
- **Tolerance** reads "±0.075 L/s (default)" or "(entered)".
- **Met** is Yes or No, with the reason when there is no value.

**Notes.** They are worded from codes and data, with names and display units:
- **Other crossing** (D13): "Another value may also meet this goal: the results crossed the target again between 31.0 % and 35.0 % Transfer pump speed. Narrow the bounds there to find it."
- **State changes:** "At the values found: Transfer pump carries no flow (it was running)."
- `start_clipped`, `sensitive` ("Apply this value exactly; rounding it to 6 significant digits moves the result by more than its tolerance"), and the n-variable diagnoses, `slope_unknown` included ("The effect of {variable} near this point is unknown: its trial solves there gave no result").

**At the values found.** The physically invalid flags of `solvedState`, with `ws.flagText`: "At the values found: 1 physically invalid result: NPSH available is below NPSH required at Transfer pump." Without any: "At the values found: converged, no physically invalid results." The full results views are not rendered from it: after Apply the case is solved and shown as usual.

**Trial solves.** A closed `<details>` "Trial solves (n)" holding a `ResultsTable`-like table (`goalSeekTrialTable()`). The first column "Trial k" is sticky, and long tables render in chunks. Columns:
- **Why**, from the purpose: Start, Scan, Root search, Probe, Closest-value search, Step, Slope.
- One column per variable (display units, 6 digits) and one per goal ("—" with the reason when there is none).
- **Result**, from the outcome: Yes; "Did not converge"; "No value: {message}"; "Rejected: {message}"; "Not computed (time budget)".
- **States**, the state changes against the first trial ("Transfer pump: no flow").

The reported trial is marked "(reported)".

**Method.** A `<details>` "Method" renders `result.methods` with `MethodsSummary`'s section rendering: the API's text and citations.

**Copy report** (`goalSeekReport()`, with the clipboard and the selected-textarea fallback of `MethodsSummary`):

```
Goal seek: {project name}
Case: base case | scenario Winter (S2)
Run: {local date and time}; {n} trial solves in {t} s; calculation method 1.2.0
Outcome: goal met. Every goal is met, after 12 evaluations.

Inputs changed
  Transfer pump · Speed: 86.1174 % (stored 0.8611744213850658), was 100 %; bounds 20 % to 100 %
Results reached
  Transfer pump → Discharge valve · Flow: 15.00 L/s; target 15 L/s; off by +0.0000069 L/s;
  tolerance ±0.075 L/s (default); met
Notes
  …
At the values found
  converged, no physically invalid results
Method
  {the Goal seek section, with references}
Trial solves
  Trial<TAB>Why<TAB>Transfer pump speed (%)<TAB>… · Flow (L/s)<TAB>Result<TAB>States
  …
```

The trial table is tab-separated, so it pastes into a spreadsheet. The report says "out of date" when the result is.

**Errors.** These reuse the Results pane's words and helpers:
- **Topology (422):** "The network cannot be solved yet", with `topologyIssueViews` and Show buttons. Show closes the dialog and runs `ws.show(...)`.
- **Fluid (400 `FLUID_ERROR`):** "The fluid properties cannot be calculated: …".
- **Validation (400):** "The calculation server rejected the goal seek." An issue at `body.variables.{i}` or `body.goals.{j}` is shown at its card: "Variable 2 (Pipe 1 of A → B · Length): {message}".
- **Not found (404):** the rows it names are marked lapsed.
- **Scenario issues** (`scenarios.{s}.overrides.{j}`) are shown as the Results pane shows them, with Reset to base.
- **Network errors** (offline, 429, 503 `SERVER_BUSY`, `TIMEOUT`): the message, plus "Run again".

### 6.10 Apply (`utils/goal-seek.ts` `applyToCase`, `asNewScenario`, `applyProblems`)

| Ran on | Offered | Not offered, with the reason shown |
|---|---|---|
| the base case | **Apply to base case**; **Apply as new scenario** | an existing scenario: "Its other changes would give other results; run goal seek on that scenario." |
| scenario Winter | **Apply to scenario** (accessible name "Apply to scenario Winter"); **Apply as new scenario** (Winter's changes plus the values) | the base case: "The values were found with Winter's changes; in the base case they would give other results. Run goal seek on the base case to find base values." |

- **Labels.** Buttons are `whitespace-nowrap`, and a long case name goes in the accessible name only.
- **Not met.** Apply is offered when goals are not met, and the banner already says so.
- **Unavailable**, `aria-disabled` with the reason:
  - out of date;
  - "Winter holds {n} changes; these values would add {k}, more than the 30 a scenario holds. Remove a change first.";
  - "A project holds at most 20 scenarios.";
  - no values (failed, cancelled, or a request error).
- **Hidden** for `met_at_start`.

**Apply to the case it ran on.**
1. `store.setCase(run.caseId)`, so the undo entry records that case and the user sees it.
2. One `ws.updateStored(...)`:
   - **Base:** write each variable's `override.value` at its path with `setValue(draft, target, field, value)`, the inverse of `valueOf`, new in `utils/scenarios.ts`.
   - **Scenario:** `withChange(scenario, override)` upserts by (target, field). An override of the whole `fluid` replaces the scenario's fluid override. A value exactly equal to the base value removes the change instead (D15 decision 21).
   - The undo label is "apply goal seek values" or "apply goal seek values in Winter".
3. Close the dialog, then `ws.solve()`: the Results pane, that case.
4. A notice: "Applied to the base case: Transfer pump speed 86.1174 %. Undo restores the values before." It adds "Winter sets its own Transfer pump speed, so it keeps it." when a scenario overrides an applied base value.

**Apply as new scenario.**
1. One `ws.updateStored(...)` adds a scenario:
   - id `newScenarioId`; name "Goal seek {n}" from the id number;
   - overrides: the run case's overrides (none for the base), copied as Duplicate does, with the variables' overrides upserted (the same equal-to-base rule);
   - description: "Values found by goal seek on the base case for: Transfer pump → Discharge valve · Flow 15 L/s (met). 2026-10-25." It is in display units at that time, cut to 500 characters with "…", editable afterwards, and travels in the link.
2. The undo label is "add scenario Goal seek 3". The entry records the run's case, so Undo returns there.
3. `ws.setCase(newId)` (announced), close the dialog, `ws.solve()`.
4. A notice: "Added scenario Goal seek 3 with the values found. Rename it in Scenarios; Undo removes it."

In a project without scenarios, this creates the first one, so the case bar appears.

**Exact values.** Apply writes the float the API returned, never the displayed text (measured: rounding to 4 digits moved 15 L/s to 15.00076 L/s). Floats survive the JSON round trip exactly, so the applied case's `/solve` reproduces `solvedState` (§7.3).

**Solve after Apply.** Edits elsewhere never solve, but here the user's intent is to see the network at those values, and one more request (about 30 ms on small networks) shows the full results, flags and traces through the normal path.

### 6.11 Out of date

- **The run's key** is `caseKey(project as sent, caseId, hydraulicFingerprint(...))`, the key results use: the base fingerprint plus that scenario's overrides. Names, units and descriptions never make it stale.
- **Recomputed on every change, results or not.** `ProjectStore.#restale` returns at once when no case has results (`project.svelte.ts` 673–675), and a goal seek adds no case state: a project opened from a link has no results, and goal seek needs none (§6.2). So `#replace` calls `#restaleGoalSeek(project, fingerprint)` itself, before and apart from `#restale`, with the one fingerprint both use: `goalSeek.stale` is true when the run case's key now differs, or the scenario is gone (`#key` gives null). The same call recomputes the `applied` state from `applied.key`. Undo back to the run's project makes the result current again.
- **Applied.** After Apply, the result records `{caseId, key}` of the target case right after the edit. It shows "Applied to the base case." (Apply hidden) while that key is current; "Out of date: the project changed after this goal seek. Run it again to apply values that hold." (Apply unavailable) otherwise; and current again when the run's own key is current.
- **The setup** never goes out of date. It is read at every Run, and only its lapsed rows block Run.

### 6.12 Page state only

The setup (goals, variables, bounds, targets) and the last result live in `Workspace`, not in `Project` and not in the link.
- **Why.** The answer travels as ordinary inputs; Apply as new scenario states the question; Copy report keeps the record. There is no model change, no pipe-indexed targets to carry through base edits, and no link growth. This is consistent with Compare rows and the active case (D15 decisions 29–30).
- **Reset.** `load()` resets it through `onLoad`: another project, an example or a link. Case switches and closing the dialog keep it.
- **Reversible** (D14): a `Project.goalSeeks` field can be added later; the request models stand alone, so it could hold them unchanged.

### 6.13 Accessibility

- **Names.**
  - The dialog is "Goal seek". Cards are `fieldset` + `legend`, so "Target", "Tolerance", "From" and "To" are announced with their row (Playwright finds them as `group` by name).
  - Remove buttons name their row. Run, Cancel and Apply name the case in their accessible names.
- **Unavailable controls** use `aria-disabled` with the reason in `aria-describedby`, so focus stays on them; inputs are never `disabled`.
- **Live regions.** One polite region in the footer announces the start ("Goal seek running on the base case.") and the outcome:
  - "Goal met: Transfer pump speed 86.1174 %.";
  - "Goal not met; see the result.";
  - "Goal seek failed: {first line}.";
  - "Goal seek cancelled."

  The seconds are `aria-hidden`. With the dialog closed, the workspace notice says it instead: never both.
- **Focus.**
  - On open: native dialog focus (Close), as other dialogs.
  - After Add: the new row's first field. After Remove: the section's Add button.
  - At the end of a run: §6.8.
  - Apply closes the dialog and returns focus to the opener. When the opener is gone, `[data-goal-seek-button]` takes it; `Dialog` already skips a detached or hidden opener.
- **Keyboard.** Enter in a `NumberField` commits without submitting. Escape reverts a field being edited, otherwise it closes the dialog (a run goes on). Global undo works outside fields.
- **Colour and contrast.** Banners carry an icon and a sentence, and the existing tokens give the contrast (emerald-950 on emerald-50, amber-900 on amber-50, red-900 on red-50). Touch targets are at least 44 px, and spinners run only under `motion-safe`.

### 6.14 Mobile (390 × 844, checked at 360 × 740)

- **The sheet** is 92 dvh with one column. Two `NumberField`s per row fit: inputs of 103–129 px at 390, and 88–114 px at 360. There is no sideways scroll in the page or the sheet; the reached and trial tables scroll in their own boxes.
- **Content height,** measured: 1,219 px for 1 goal + 1 variable + result, 1,595 px for 2 + 2.
- **Entry.** The Results header button keeps its label (108 px) at 390 px and is icon-only below 24 rem. The trace's entry closes the trace sheet first.
- **At the end of a run** with focus on Run or Cancel, the Result heading scrolls into view and takes focus.
- **Long names wrap** (`break-words`), and Apply buttons keep short visible labels. On phones `ws.solve()` after Apply shows the Results tab.

### 6.15 Store and workspace (`state/project.svelte.ts`, `state/workspace.svelte.ts`)

```ts
export interface GoalSeekRun {
  caseId: CaseId;                 // the case it ran on (null: the base case)
  request: GoalSeekRequest;       // as sent (SI)
  project: Project;               // the whole project as sent
  key: string;                    // caseKey when sent
  startedAt: number;
}
export interface GoalSeekFinished {
  status: 'done' | 'failed';
  run: GoalSeekRun;
  response: GoalSeekResponse | null;    // done
  error: ResultsError | null;           // failed (topology, validation, not found, fluid, network)
  stale: boolean;
  applied: { caseId: CaseId; key: string } | null;
}
export type GoalSeekState =
  | { status: 'running' | 'cancelled'; run: GoalSeekRun; previous: GoalSeekFinished | null }
  | GoalSeekFinished
  | null;
// ProjectStore
goalSeek = $state.raw<GoalSeekState>(null);
get goalSeekRunning(): boolean;
get calculating(): 'solve' | 'solveAll' | 'goalSeek' | null;   // read by every Solve control
runGoalSeek(request: GoalSeekRequest, caseId: CaseId = this.activeCase): Promise<boolean>;
                                        // false: refused, a solve or Solve all is running
cancelGoalSeek(): boolean;              // also called by cancelSolve()
markGoalSeekApplied(caseId: CaseId): void;
// Workspace
goalSeekOpen = $state(false);
goalSeekPrefill = $state.raw<ElementRef | null>(null);
goalSeekSetup = $state.raw<GoalSeekSetup>({ goals: [], variables: [] });  // drafts, SI or null
openGoalSeek(prefill?: ElementRef): void;
runGoalSeek(): Promise<void>;           // flush(), toRequest(setup), store.runGoalSeek(...)
applyGoalSeek(mode: 'case' | 'new'): boolean;
```

- **`runGoalSeek`** returns false without sending while `calculating` is `'solve'` or `'solveAll'`. Otherwise it calls `#cancelSystemCurves()`, then posts with its own `AbortController` and a sequence number. A late answer after a cancel or `load()` is dropped. The curve queue awaits `#goalSeekDone`, as it awaits `#runDone`.
- **`solve()` and `solveAll()`** return without sending while a goal seek runs (§6.8): only Cancel stops it.
- **`load()` and `dispose()`** abort it and clear it.
- **Staleness** is recomputed by `#replace` on every project change, whether or not any case has results (§6.11).
- **No project change** comes from a goal seek: there is no method-version recording and no undo step until Apply.
- **Pipe variables** also record `{pipeCount, ends}` for §6.5's lapse rule.
- **Reserved ids.** While the setup names a component or connection, no new element takes its id. `Workspace` passes the ids the setup's goals and variables name as `newId`'s existing `alsoUsed` wherever it creates an element: `createComponent`'s options and the edits that create connections (`connect`, insertions and splits in `utils/edit.ts`) take them. This is D15's rule for ids that scenario changes name (`usedIds`, `factory.ts`), applied to page state. A deleted element's row then lapses and stays lapsed; it never moves to a new element, and Undo of the deletion makes it current again. When the row is removed, the id is free.
- **The client** (`api/client.ts`): `goalSeek(project, { variables, goals }, { signal, scenarioId })` → `POST /api/v1/goal-seek`, body `{project, scenarioId?, variables, goals}`. Errors are mapped as for `/solve`, plus a new `NotFoundError` for a 404 `NOT_FOUND`, which keeps its issues. It **extends `ValidationError`** (same `details`, plus `issues`), so `toResultsError` (`project.svelte.ts` 286–305) still maps `/solve`'s and `/system-curve`'s 404s (an unknown scenario or pump) to kind `validation`, as today; only goal seek reads `issues` to mark rows lapsed.

---

## 7. Tests

No existing test is weakened. The schema-v1 fixture and `test_released_links.py` stay as they are: `Project` does not change.

### 7.1 API unit tests (`tests/unit`)

**`test_goal_seek_models.py`:**
- **The derivation.**
  - `GOAL_*_FIELDS` are exactly the allow-list entries whose holder field is a float, plus resistance through `FlowCoefficient.value`.
  - Every other entry is in `NOT_VARIABLES` with its reason.
  - The Literals equal the tables' names, and every class of the `Component` union is covered (`{}` for none).
  - No validator of a holder reads two variable fields (§2.1).
- **The extensions.**
  - `x-goal-variables` states exactly the tables; each `schema` and `path` resolves to a numeric property in `openapi.json`; `coefficients` equals `FlowCoefficient.kind`.
  - `x-goal-quantities` matches the readers, the targets, the default-tolerance function and the minima (`MIN_TOLERANCE`), with no density in any minimum.
  - `x-ordered-fields` on the three variable schemas, and `x-goal-seek-rules`: each `uniqueBy` key list rejects two items equal on it and accepts two that differ on one key; `sameLength` matches the validator.
- **Request rules.** Each rule of §2.5 is rejected without echoing the submitted value (sentinels, as `test_validation_errors_do_not_echo_submitted_values`), including `NaN` and `Infinity` in the JSON.
- **The body limit.** `test_project_bounds_fit_the_body_limit` is extended with 4 variables and 4 goals at the largest project.

**`test_goal_seek_search.py`.** The pure core, `search(variables, goals, evaluate, limits, clock)`, driven by synthetic evaluators, with no network:
- **The map (§3.1 step 2):**
  - over random linear and log ranges, field maxima included: no trial outside [lower, upper]; u = 0 and u = 1 give `lower` and `upper` exactly;
  - a log resistance with bounds [2000, 10⁷] evaluates exactly 10⁷ at u = 1, and the trial validates;
  - evaluation 0, the scan's start point and dogbox's first call are the case's value bit for bit, with no second solve of it; a `middle` start is the scan's k = 4 point;
  - `atBound` from the value; a pipe length [4, 400] at u = 1 is exactly 400.
- **One variable, met:**
  - linear: met after the scan plus 1–2 Brent solves, stopping at tier 0;
  - met at the start: 1 evaluation, `met_at_start`;
  - a start clipped to a bound: `start_clipped`, and `met` (not `met_at_start`);
  - the scan order is 0, 1, 1/2, 1/4, 3/4, 1/8, 3/8, 5/8, 7/8, and a scan cut short by the clock after 3 points has solved both bounds and the middle.
- **One variable, several answers:**
  - two brackets: the one nearest the start is solved, the other gets `other_crossing`;
  - several met scan points: `met_range` with their count, and the tier-0 one nearest the start is reported even when a tier-1 one is nearer;
  - a tangent minimum within tolerance: `met`, `met_without_crossing`.
- **One variable, not reached:**
  - monotone: `not_reachable`, `closest_at_bound`, 10 evaluations, and a message that counts the values solved and claims no more;
  - a plateau: `closest_on_plateau` with its range;
  - an interior minimum: `minimize_scalar`, `closest_inside`.
- **One variable, jumps and gaps:**
  - a step across the target with synthetic states: `jump`, a final bracket of at most 10⁻¹⁰ in u, and the state changes, within the cap of 60;
  - a zero-flow label flip (closed → isolated, flows 0 on both sides) beside a real switch: only the switch is named;
  - a steep continuous crossing within resolution: `met`, with `sensitive`;
  - a jump nearest the start and a root further away (the review's case: a switch at u = 0.31, start 0.29, a root in a farther bracket): the next bracket is met, and the jump note stays;
  - a tier-1 scan point at a turning point (+0.6 tolerances) and a jump in the nearest bracket (+1.8 to −4): `met`, success true, the `jump` note and `met_without_crossing`, and no message saying that no value meets the goal (§3.5);
  - an unusable band inside a bracket: `unsolved_crossing` after at most 4 probe rounds;
  - an unusable band left of a root: the probes find a gap-free bracket, then `met`;
  - every evaluation unusable: `no_usable_evaluation`.
- **Several variables:**
  - n = 2 linear: met in 4 evaluations, the start, 2 slopes and one step (a Gauss–Newton step is exact), from every start, including u0 = (0.024, 0.02) and (10⁻⁴, 0) near the lower bounds;
  - inconsistent goals: `no_progress`, with the least scaled cost reported;
  - a zero Jacobian column: `variable_no_effect`;
  - collinear columns: `variables_collinear`;
  - a flat goal: `goal_no_effect`;
  - n = 3 nonlinear: met;
  - an unusable region: the penalty, the trust region shrinks, then met;
  - a start at a usable/unusable edge (a forward slope step unusable): the step is retried backward, and the search is met;
  - a column with no usable step beside the iterate: `slope_unknown`, and no `variables_collinear` or `variable_no_effect` note for it;
  - a start on a bound stays on it.
- **Notes:** `sensitive` fires for x = 0.1000004 (rounded to 0.1, a change of 4×10⁻⁶ of x) where a 5×10⁻⁷ test would not, and names the two evaluations of its slope.
- **Caps and the budget:**
  - the cap: `evaluation_limit`, with `met` from the reported evaluation;
  - a fake clock: no evaluation starts without 1.5 × the slowest + 1 s left, giving `time_budget`;
  - a `SolveDeadlineError` from evaluation k ≥ 1: `not_computed` and `time_budget`; from evaluation 0 it propagates;
  - `SolveCancelledError` always propagates.
- **Determinism.** Two runs give identical evaluation sequences; the cache never solves a point twice; the reported evaluation follows §3.2's order (ties by distance, then index).

**`test_goal_seek_service.py`:**
- **Resolution.**
  - Every variable on every target type writes at its location and reads its start; a resistance of another kind, or on the default, starts at the geometric middle.
  - Every not-applicable case gives 400 with its ids in `componentIds` or `connectionIds` and no id in any message (the sentinel test extended to ids); unknown ids give 404, all listed, naming them.
- **Goals.**
  - Each quantity reads its field and sign on a solved fixture, equal to Compare's reader through the shared fixture (§7.5).
  - Wrong element kinds, a missing NPSHr curve, a missing vapor pressure and a tolerance below its minimum give 400, the minimum the same for water and a glycol.
  - A missing value (closed-off section, floating section, the NPSH margin of a pump without flow) makes the evaluation `no_value` with its message; NPSH available of a pump without flow has its value, equal to `npshAvailable`.
- **Tolerances.** The default per quantity, with the case density, and its source.
- **Bounds.** A speed bound at or below `minSpeed` gives 400 at `variables.0.lower`; an FCV bound above 100 gives 400. A low speed bound where `CONTROLLED_PUMP_SETPOINT` holds gives no error: those trials are `topology_error`. A spy on `solve_project` proves that no solve runs before steps 1–7 pass.
- **The order of checks**, step by step (§4.2).
- **Metamorphic.** On reference projects with a pump, a controlled pump, a PRV, an FCV, an assigned flow, a glycol with a vapor-pressure override and a multi-pipe connection:
  - the start evaluation's state (when it is the case) equals `solve_project(case)`, timestamp aside;
  - the found-values state equals `solve_case` of the project with the result's `override` applied (to the base, into the scenario, and as a new scenario) bit for bit, apart from `timestamp`, `trace.methods.sections` and the notes annotation adds;
  - the trial project equals the independent patcher's (`tests/unit/scenario_patch.py`), model and `fields_set`.
- **Scenarios.**
  - A variable that the scenario overrides starts at the scenario's value, its `replacedOverride` is that override's index, and the Scenario section marks it replaced; a variable the scenario does not override has `replacedOverride` null.
  - A temperature inside the scenario's whole fluid gives a `fluid` override.
  - The scenario's own errors come first.
- **Annotation.** Exactly one first section "Goal seek", then "Scenario" if there is one; one first note per varied element; nothing else changes.

**`test_api_goal_seek.py`:**
- the response matches its schema, and `success` equals `result.met`;
- every error and the order of checks;
- 503 `SERVER_BUSY`;
- with one client's goal seek in the pool, a second client's goal seek gets 503 `SERVER_BUSY` with `Retry-After` at once, and a third client's plain solve runs and returns 200; a cancelled goal seek holds its slot until its work stops;
- a budget patched short gives 200 `time_budget` after the first evaluation, or 503 `TIMEOUT` before it;
- the OpenAPI document lists 404;
- the path is rate-limited.

**Also extended:**
- `test_logging_privacy.py`: a goal-seek request logs nothing of its body.
- `test_schema_rules.py`: both extensions, and the staleness of `openapi.json`.
- `test_scenario_*`: `scenario_section` and `element_notes` without `replaced` give today's text.

### 7.2 Independent closed-form reference cases (`tests/reference/test_goal_seek.py`, `derivations_goal_seek.py`)

**Ground rules:**
- **The tester** reads this design, the specs and the models, not `services/goal_seek.py`.
- **Closed forms** come from the reference suite's independent laws (`derivations`, `element_laws`, `line`): `fluids.friction.Colebrook` or 64/Re, `fluids.fittings` for Crane K and the Cv↔K conversion, and CoolProp `PropsSI` for water. The conventions are EGL nodal heads (D7) and no boundary entrance or exit loss without a fitting (D10).
- **Case files:** `tests/reference/cases/goal_seek_*.json`, each with a `goalSeek` request (variables, goals) and the `expected` closed-form values, generated by `build_closed_form_cases.py` and kept current by `test_derivations_current.py`.

| # | Network | Variable → goal | Closed form, expected outcome |
|---|---|---|---|
| G1 | R1 → one pipe → R2, turbulent, custom fluid | R1 `liquidLevel` → flow in L1 | level = z₂ + h₂ − z₁ + f(Re)(L/D)v²/2g, v = 4Q/πD²: met |
| G2 | G1, laminar (Re < 2000) | the same | f = 64/Re (level linear in Q): met |
| G3 | G1 with `entrance_sharp` and `exit`, water | the same | + (K_ent + K_exit)v²/2g (Crane 0.57 and 1.0): met |
| G4 | R1 → pipe → pump → pipe → R2; a linear curve (collinear points, so PCHIP is that line) | pump `speed` → pump flow (duty point) | s = [bQ + √(b²Q² + 4aH)]/(2a), H = H₂ − H₁ + h₁(Q) + h₂(Q) (affinity laws): met |
| G5 | G4 | pump `speed` → static pressure at the discharge port | Q from ρg(H₂ + h₂(Q) − v₂²/2g − z_d) = p, then s as in G4: met |
| G6 | R1 → pipe → PRV → pipe → R2 | PRV `setpoint` → flow in the outlet pipe | p_set = ρg(H₂ + h₂(Q) − v₂²/2g − z_v), the PRV active (checked from the upstream head): met |
| G7 | R1 → pipe → assigned flow | `flow` → static pressure at its port | Q from ρg(H₁ − h(Q) − v²/2g − z) = p: met |
| G8 | R1 and R2 → ideal tee → R3 (n = 2) | both levels → flows in L1 and L2 | H_T = H₃ + h₃(Q₁ + Q₂); level_i = H_T + h_i(Q_i) − z_i (EGL continuous at an ideal tee): met |
| G9 | G1 | L1 `length` → flow (log scale) | L = (H₁ − H₂) × 2gD/(f v²): met |
| G10 | R1 → pipe → gate valve → pipe → R2 | `resistance` Cv → flow (log scale) | K = [H₁ − H₂ − h₁ − h₂] × 2g/v_ref²; Cv = `fluids.fittings.K_to_Cv(K, D_ref)`: met |
| G11 | reference node → pipe → R2 | node `pressure` → flow | p = ρg(H₂ + h(Q) − z): met |
| G12 | a pump with an NPSHr curve, water | `fluid.temperature` → NPSH margin 0 | NPSHa(T) = EGL_s − z_s + (p_atm − p_vap(T))/(ρ(T)g), with EGL_s = H₁ − h_suction(Q); Q(T) from the pump law; NPSHr(Q) linear; T by brentq in the derivation: met |
| G13 | R1 → pipe → FCV → pipe → R2 | FCV `setpoint` → static pressure at the FCV outlet | Q from ρg(H₂ + h₂(Q) − v²/2g − z) = p; setpoint = Q, the FCV active (H₁ − H₂ above the losses at Q): met |
| G14 | two parallel pumps with linear curves (n = 2) | both speeds → both pump flows | each s from G4 at the common head: met |
| G15 | G1 with a target above what the upper bound gives | R1 level → flow | not met, `not_reachable`, `closest_at_bound` (upper); the value found is exactly the upper bound, and achieved = the closed form there; 10 evaluations |
| G16 | R1 → pipe → flow-controlled pump (Q_set 20 L/s, s ∈ [0.5, 0.9]) → pipe → assigned demand (the network of `assigned_flow_flow_pump_max_speed`) | the demand `flow`, bounds [10, 32] L/s → static pressure at its port, target a third of the way from the min-speed side's value to the max-speed side's at Q_set | max speed below Q_set, min speed above (D12); between them, no steady state (over-controlled): not met, `unsolved_crossing`, a < Q_set < b; the reported value = the closed form of the min-speed side at its x, within D6; the two sides' states `max_speed` and `min_speed` |
| G17 | R1 → pipe → check valve (cracking 2 kPa) → pipe → R2, the case's R1 level below opening | R1 level → flow | closed below H₂ + h_crack, then the open law h_crack + K v²/2g + friction: met; `state_changes` names CV1 closed → open |
| G18 | G1 with the case's level equal to the closed-form inverse for its target | R1 level → flow | 1 evaluation, `met_at_start` |
| G19 | G1 with scenario S1 overriding R2's level, L1's length and R1's level | R1 level → flow, on S1 | the closed form with S1's values; start = S1's R1 level; `override` replaces S1's level override; the Scenario section marks it replaced; applying it into S1 and solving gives the found state bit for bit |

**Pass criteria (D6):**
- **Default tolerance:** every goal is met, and the closed-form forward model at the value found is within the tolerance plus D6 of the target.
- **Tight tolerance:** with the smallest allowed tolerance (max(10⁻⁶ × \|target\|, the quantity's minimum), §2.2), every goal is met, and the value found is within D6 of the closed-form inverse: levels and pressures 0.5 % or 0.01 m of head; speeds 0.5 % relative (D6's speed rule); flows 0.5 %. For lengths, Cv and temperature, which have no D6 quantity, the forward model at the value found is within D6 of the target.
- **G15 to G19:** the stated outcome, stop reason, notes and values within D6.
- A new variable field or goal quantity ships with a reference case (D6).

### 7.3 Identity of solves (D13 acceptance)

- `services/solver/` has no diff.
- **The corpus comparison** (TSD §10.4) against the commit the build starts from: 5,136 projects with system curves, identical, different 0, no ignores.
- **`scenario_check`** over the corpus: 0 different (the planner and writer are only renamed).

### 7.4 Corpus tool (`tests/differential/goal_seek_check.py`, new)

For every corpus project and n = 1 to 4 (seeded `Random(f"goalseek:{name}:{n}")`):
1. **Draw the variables.** Choose the field kind uniformly first, then a target that has it. Bounds are a seeded interval within the field's bounds (log-uniform for log variables).
2. **Draw the goals** among the case's results that have values.
3. **Set the targets** to the goal values at a seeded interior point. Keep the draw only if the case misses a target by more than 10 tolerances.
4. **Run `goal_seek_case` twice.**

Checks:
- (a) no exception other than the documented errors;
- (b) the response matches its schema;
- (c) the two runs are identical apart from `seconds`, `computeTime` and `timestamp`;
- (d) the found-values state equals the solve of the project with the overrides applied (base, and into a seeded scenario on every 10th project), bit for bit outside the annotation;
- (e) every evaluation within the cap, and the time within the budget;
- (f) the counts of each stop reason and the met rate per n, recorded (no threshold: the measurements of §3.11 are the reference).

Exit status 1 on (a), (b), (c) or (d). `test_goal_seek_check_smoke.py` runs the reference cases and 10 seeds of each fuzz profile.

### 7.5 Web unit and component tests (Vitest)

- **`utils/goal-seek.test.ts`:**
  - **Catalogues:** the 11 quantities and their Compare mapping; `needs`; variables per element type from `x-goal-variables`; a pump with and without flow control; FCV against PRV/PSV units; a custom fluid has no temperature; statuses, spec and fluid never offered; a scenario setting a built-in fluid offers a temperature the base lacks.
  - **Default bounds:** each row of §6.6, clipping, the controlled pump's ordered bound (a minimum speed of 0.5 gives From 51 %, 0.995 gives a From below 100 %), zero values, a vacuum surface pressure, temperature with and without `FluidInfo`, a resistance on the Crane default centred on `kOpen`, and an ideal control valve (`kOpen` 0) with 0.01 to 100 and "Now: ideal (K = 0)".
  - **Tolerance field:** its minimum from `x-goal-quantities` moves with the target; a value the field accepts is never below the API's minimum.
  - **Reserved ids:** a goal on V2, V2 deleted, a valve added: the new valve is V3 and the row stays lapsed; Undo of the deletion makes it current; with the row removed, the next valve may be V2. The same for a connection.
  - **Lapses:** a deleted element or port; flow control removed; the fluid made custom; a pipe list changed by `removePipe`, a join and insert-with-reversal; a rename does not lapse.
  - **`runProblems`:** each reason, in order, and the caps.
  - **`toRequest`:** SI values, `coefficient`, `scenarioId` absent for the base, stable key order, nothing else sent.
  - **Words:** `outcomeText` for every stop reason, `noteText` for every code, `purposeText` and `outcomeLabel`; an unknown code shows the API's message.
  - **Tables and report:** `goalSeekTrialTable` (columns, units, "—" with a reason, the reported row); `goalSeekReport` (the case, the bounds, the exact SI value, the calculation method version, out-of-date wording, a tab-separated table).
  - **Apply:** `applyToCase` (a base write, a scenario upsert, a whole-fluid override replaced, equal-to-base removing the change); `asNewScenario` (id, "Goal seek n", the run case's overrides copied, the description cut at 500); `applyProblems` (30 changes, 20 scenarios, stale, no values, the base never offered for a scenario run).
- **The shared fixture** (`utils/__fixtures__/goal-seek-cases.json`, generated by `tests/fixtures/goal_seek_cases.py` with the real trial builder and readers, regenerated by `pnpm gen:types`; `tests/unit/test_goal_seek_cases.py` fails while it is stale):
  - **cases:** base and scenario runs, a value equal to the base, a scenario-overridden field, a pipe length, a temperature inside a whole-fluid override, a resistance;
  - **web checks:** `caseProject(applyToCase(...))` equals the API's trial project, and each quantity's Compare reader gives the API's goal value on the fixture's solved state.
- **`state/project.svelte.test.ts`** (a fake `Solver.goalSeek`):
  - running → done, and failed for each error kind;
  - Cancel aborts the signal and drops a late answer;
  - `cancelSolve()` cancels a goal seek;
  - `solve()` and `solveAll()` during a goal seek send nothing and the goal seek goes on; `runGoalSeek()` during a solve or Solve all returns false and sends nothing; `calculating` names what runs;
  - curves wait, and a curve in flight is cancelled at the start;
  - `scenarioId` is sent only for scenarios;
  - stale after a hydraulic edit, not after a rename, current again after undo;
  - on a project never solved (no case state): a goal seek, an edit, then stale; undo, then current; the `applied` state likewise;
  - a deleted scenario makes its result stale;
  - `markGoalSeekApplied`, and the applied and stale states;
  - `load()` clears it;
  - the previous result is kept through a cancelled run.
- **Components:**
  - `GoalSeekDialog.svelte.test.ts`: Add and Remove with their focus; prefill from an element; fields editable in a scenario; Run's reasons in `aria-describedby`; the running state (Cancel, the `aria-hidden` timer, the live text); every banner of §6.9; Apply buttons per run case and the base not offered for a scenario run; Apply unavailable when out of date; the applied state; Copy report with its fallback; the trial table; flags at the values found; focus to the Result heading when Run had it; the notice when closed.
  - `ResultsPanel`, `WorkspaceHeader`, `ScenarioBar`, `CompareView` and `ResultsStateNotice`: the button's names, "Cancel goal seek", and, during a goal seek, every Solve, Solve all, Solve again and Solve now control `aria-disabled` with the reason, a click sending nothing and leaving the goal seek running.
  - `TraceView`: Use in goal seek preselects the element, and on narrow screens the trace closes first.
  - `Dialog`: the `xl` class.
- **`client.test.ts`** and **`model-rules.test.ts`:**
  - the URL, the body (no `scenarioId` for the base), the signal;
  - 422 → `TopologyError`, 400 → `ValidationError` without values, 404 → `NotFoundError` with issues (an instance of `ValidationError`), 503 `TIMEOUT` → `NetworkError` with its code;
  - `/solve`'s unknown-scenario 404 still maps to the results error kind `validation` (`toResultsError`);
  - `x-goal-variables`, `x-goal-quantities`, `x-goal-seek-rules`, the variable schemas' `x-ordered-fields` and the item limits are read, and the tests fail if they are absent.

### 7.6 End to end (Playwright, `tests/goal-seek.e2e.ts`)

Each flow runs in both projects: `desktop` (1280 × 800) and `mobile` (390 × 844), with one worker, the real app and the real API. The numbers come from the pump-transfer example: 100 % speed gives 18.99 L/s in Transfer pump → Discharge isolation valve.

1. **Met, Apply to base.**
   - Results → Goal seek. Add the goal Transfer pump → Discharge isolation valve · Flow, target 15 L/s. Add the variable Transfer pump · Speed (defaults 20–100 %). Run.
   - Expect "Goal met", a speed between 85 % and 87 %, and "Apply to base case". Apply: the dialog closes, the case is solved, and the Links table's flow shows the same text as "Reached".
   - Undo: the speed is 100 % again, and Apply is offered again in the dialog.
2. **Not met.** Target 25 L/s: "Goal not met", the closest at the upper bound (100 %), Apply still offered, and the trial table listing every trial.
3. **Cancel.**
   - Hold `/api/v1/goal-seek` with `page.route`. Run → Cancel: the request is aborted (`requestfailed`), "Goal seek cancelled", the project unchanged.
   - Run, close the dialog, then the header's "Cancel goal seek": aborted. Unroute, then Run works.
4. **Scenario.**
   - Create the scenario "Low suction" (a lower Suction tank level) and switch to it. The dialog shows the case chip, and its fields are editable. Run.
   - "Apply to base case" is not offered, and says why. Apply as new scenario: the case select shows "Goal seek 2 (2 changes)", active and solved, with the description in the results card. Undo returns to "Low suction".
5. **Out of date.** On the example opened from its link and never solved, run a goal seek, then change the pump speed in Build. Reopen: "Out of date", with Apply `aria-disabled` and its reason. Undo: current again. Run again: current. While the run is held (`page.route`), Results' "Solve now" is `aria-disabled` with the goal-seek reason, and clicking it leaves the run going.
6. **Trace entry.** Links → that connection's trace → Use in goal seek. The New goal form shows the connection; choose Flow, Add, and the Target field has the focus. On mobile the trace sheet closed first. Closing the dialog returns focus to the Goal seek button.
7. **Layout.**
   - On both projects: no sideways page scroll with the dialog open and a result shown, and Run and Close inside the viewport.
   - On mobile, after Run, the Result heading is focused and in view.

### 7.7 Acceptance (D6, D13)

- The reference suite is green, G1–G19 included.
- `services/solver/` has no diff, and the corpus comparison is 0 different with no ignores (§7.3).
- `goal_seek_check` exits 0; its met rates and stop-reason counts are recorded in TSD §10.4.
- API: `uv run pytest`, ruff, ruff format and mypy strict.
- Web: `pnpm test`, `pnpm check`, `pnpm lint` and `pnpm test:e2e`.

---

## 8. What changes where

**API (`apps/api`)**

| File | Change |
|---|---|
| `models/goal_seek.py` (new) | Variables, goals, derived tables, `NOT_VARIABLES`, tolerance constants and minima, extension data (`x-goal-variables`, `x-goal-quantities`, `x-goal-seek-rules`, the variables' `x-ordered-fields`), result models |
| `models/api.py` | `GoalSeekRequest` (with `x-goal-variables`, `x-goal-quantities`), `GoalSeekResponse` |
| `services/goal_seek.py` (new) | `goal_seek_case`: checks, the map of §3.1, trial builder, evaluator, `search` (the pure core), result, notes, texts, annotation, the two errors |
| `services/scenarios.py` | `plan_override` and `write_override` public (renamed, same behaviour); `scenario_section` and `element_notes` take `replaced` (default empty) |
| `routers/goal_seek.py` (new); `routers/_common.py` (new: `_ERRORS`, `_client`); `routers/solve.py` (imports them); `main.py` | the endpoint, the router included, two handlers |
| `middleware.py` | `/api/v1/goal-seek` in `RATE_LIMITED_PATHS` |
| `workers.py` | `MAX_GOAL_SEEKS = SOLVE_WORKERS − 1`: goal seeks counted from submission to the end of their work, another refused with `ServerBusyError` (§4.3) |
| `services/solver/*` | **no change** (read only: `BRENT`, `fluid_properties`, `build_network`, `solve_project`, budget errors) |
| `tests/unit/test_goal_seek_{models,search,service,cases}.py`, `test_api_goal_seek.py` (new); `test_schema_rules.py`, `test_logging_privacy.py`, `test_api_robustness.py` (extended) | §7.1 |
| `tests/fixtures/goal_seek_cases.py` (new) | the web fixture's generator |
| `tests/reference/test_goal_seek.py`, `derivations_goal_seek.py`, `cases/goal_seek_*.json` (new); `build_closed_form_cases.py` (registers them) | §7.2 |
| `tests/differential/goal_seek_check.py`, `test_goal_seek_check_smoke.py` (new) | §7.4 |

**Web (`apps/web`)**

| File | Change |
|---|---|
| `src/lib/api/openapi.json`, `schema.d.ts` | regenerated by `pnpm gen:types`, never edited |
| `scripts/gen-api-types.sh` | also writes `utils/__fixtures__/goal-seek-cases.json` |
| `src/lib/api/types.ts`, `client.ts` (+ test) | goal-seek types; `goalSeek()`; a new `NotFoundError` (404 with its issues) |
| `src/lib/utils/goal-seek.ts` (new, + test) | `GOAL_QUANTITIES`, `goalChoices`, `variableChoices`, `defaultBounds`, `variableBounds`, labels, lapses, `runProblems`, `toRequest`, `outcomeText`, `noteText`, `purposeText`, `outcomeLabel`, `goalSeekTrialTable`, `goalSeekReport`, `applyToCase`, `asNewScenario`, `applyProblems` |
| `src/lib/utils/scenarios.ts` (+ test) | `setValue(project, target, field, value)` |
| `src/lib/utils/factory.ts`, `utils/edit.ts` (+ tests) | the id-creating edits take reserved ids (`alsoUsed`), passed by `Workspace` from the setup (§6.15) |
| `src/lib/utils/model-rules.ts` (+ test) | `goalVariableFields()`, `goalQuantities()`, `goalSeekLimits()` |
| `src/lib/state/project.svelte.ts`, `workspace.svelte.ts` (+ tests) | §6.15; `#resetPage` resets the page state |
| `components/workspace/GoalSeekDialog.svelte`, `components/workspace/goal-seek/{GoalCard,VariableCard,NewGoalForm,NewVariableForm,GoalSeekResult}.svelte` (new) | §6.3–§6.10 |
| `components/workspace/Workspace.svelte` | mounts the dialog |
| `components/results/ResultsPanel.svelte`, `TraceView.svelte` | the entry points; Solve, Solve all and Solve now read `store.calculating` |
| `components/results/CompareView.svelte`, `ResultsStateNotice.svelte` | Solve all and Solve again read `store.calculating`, with the reason (§6.8) |
| `components/workspace/WorkspaceHeader.svelte`, `ScenarioBar.svelte` | Cancel's name and the reasons during a goal seek |
| `components/ui/Dialog.svelte`, `Icon.svelte` | the `xl` prop; the `target` icon |
| `src/lib/testing/{results,workspace}.ts` | a `goalSeekResponse()` factory; `testWorkspace({ solver: { solve, goalSeek } })` |
| `tests/goal-seek.e2e.ts` (new) | §7.6 |

**Docs (made by the builders)**

| File | Change |
|---|---|
| `CLAUDE.md` | D5: move goal seek from Deferred to "In v1" ("Goal seek (D16)"). New D16 (draft below). D10's list of published extensions gains `x-goal-variables`, `x-goal-quantities` and `x-goal-seek-rules` (and `x-ordered-fields` now also on the goal-seek variable schemas). The status line lists goal seek among what v1 has. |
| PRD | §3.9 drops "Later" and states the variable and goal lists, the default tolerances, ≤ 4 variables, the output (the evaluations, each a full solve, listed; "iteration count" becomes the number of evaluations) and the apply flows. §2.4's row is marked built. Line 113 drops goal seek from Later. |
| SDD | §3.2.1: the endpoint (drop "Later"). §4.13: these models, replacing the sketch. §5.1: the endpoint row, and `x-goal-variables`, `x-goal-quantities` and `x-goal-seek-rules` in the extensions table. §5.1.2: the goal-seek rows: 404 `NOT_FOUND` for an unknown element, port or pipe (ids named); 400 `VALIDATION_ERROR` for input problems and bounds (by index, ids only in `componentIds` and `connectionIds`); 503 `SERVER_BUSY` when a goal seek is already in the pool; 429 as for `/solve`. |
| TSD | §5.7: the goal-seek bullets as built (§3–§5 here; the TSD sketch's "fail the run" replaced by §3.6). §10.1: the row as §7.2 (G1–G19). §10.4: `goal_seek_check`. §12: a decided item (goal seek's search, caps and tolerances). |
| `docs/proposals/goal-seek.md` | §12 "As built" after the build, as the scenario manager's |

**CLAUDE.md D16, draft:**

> ### D16. Goal seek (owner, 2026-10-25)
> Built from `docs/proposals/goal-seek.md`. Specs: PRD §3.9, SDD §4.13, TSD §5.7.
> - **Model.** `POST /api/v1/goal-seek {project, scenarioId?, variables (1–4), goals (as many)}`. A variable is a numeric value of D15's allow-list addressed as an override (a resistance as one K, Cv or Kv) with SI bounds inside the field's own (`x-goal-variables`); the search starts at the case's value. A goal is a port's static pressure, a connection's flow, largest velocity or head loss, a pump's flow, head, NPSHa or NPSH margin, a valve's flow or pressure drop, or a boundary's outflow (Compare's rows), with a target and a tolerance: default 0.5 % of the target, at least 0.01 m of head (pressures ×ρg), 10⁻⁶ m³/s or 10⁻³ m/s (`x-goal-quantities`; the flow and velocity floors are this decision's, not D6's), and never below fixed minima that do not depend on the fluid. Nothing is saved in the project or the link; while the web's setup names an element, no new element takes its id. *(GOALS §4.1: every value named and typed.)*
> - **Search.** Every evaluation is `solve_project` of the case with the variables written on top (cold, no system curves); nothing under `services/solver/` changes. Each variable is scaled to [0, 1] (log for lengths and resistances), mapped back exactly at the bounds and the start and clamped elsewhere, so no trial leaves the bounds. One variable: the start, a 9-point scan (coarse to fine), Brent in the bracket nearest the start; several: dogbox least squares on residual/tolerance, shifted to the start, with a forward-difference Jacobian (an unusable step retried backward). Stop at a tenth of the tolerance; met within it. Unusable trials are never residuals (gaps probed; penalties). Jumps (closed to 10⁻¹⁰ of the range) and crossings where the solve fails are named, never met; state changes count only elements that carry flow; other crossings found are noted, and "not reachable" says only what the values solved show (D13). The stop reason follows the reported evaluation: met when it meets every goal. Caps 60 for one variable and 20(n + 1) for n, inside the one 45 s budget (best so far); at most one goal seek in the worker pool at a time (503 `SERVER_BUSY`), so a solve always has a worker. Deterministic. *(GOALS §3: correctness over convergence.)*
> - **Results.** The reported evaluation's own solved state, a "Goal seek" methods section first and a note on each varied element, every evaluation listed, and each variable's `override`: applied and solved it gives the same state bit for bit. In a scenario run, each variable names the override it replaced (`replacedOverride`). Errors: 404 unknown scenario or element (ids named), 400 by index without values or ids in messages (bounds checked before any solve), 422 and 400 for the case's topology and fluid. `METHOD_VERSION` stays 1.2.0 and is named; the search has no version label, and its methods section states every constant. *(GOALS §4.2, §4.3.)*
> - **Web.** A Goal seek dialog from the Results header and the trace, on the case shown; one request at a time (every Solve control reads one store getter, the store refuses a solve during a goal seek, and only Cancel stops one); Apply to the case it ran on or as a new scenario (never a scenario run into the base), exact values, one undo step, then solved; a result goes out of date by the case key, whether or not the project has results. *(GOALS §4.7.)*
> - **Proof.** Closed-form inverses G1–G19, the metamorphic bit-identity, `goal_seek_check` over the corpus, the corpus comparison 0 different.

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| **The time budget limits network size.** Under §3.8's start rule a typical one-variable search (about 12 evaluations) fits up to about 3.5 s per solve, and the start plus the scan up to about 4.2 s: at the 499-component Crane ladder (4.40 s here) the budget binds after 9 evaluations. At 999 Crane components (11.4 s per solve) only 3 start: best so far, not met, and a stopping point that depends on the machine. Timings vary by host. | The caps count solves and do not vary; the message says a run stopped by time can differ. The coarse-to-fine scan makes a cut scan still span the bounds. Dumping the case once saves about 25 % of an evaluation. Building the state and trace is 70 % of a 999-component ideal solve and could only be cut inside `services/solver/` (out of scope). |
| **A goal seek holds one of the 2 workers for up to 45 s.** | At most one goal seek is in the pool (`MAX_GOAL_SEEKS`), so a plain solve always has a worker; a second client's goal seek gets 503 `SERVER_BUSY` with `Retry-After`, which the web shows with "Run again". The per-client turn and the pool bound are unchanged, and the path is rate-limited. A system curve on a large network can also hold a worker for long; that is today's behaviour and is not changed here. |
| **least_squares is local.** A flat start (an FCV fully open, a PRV holding the goal node's pressure) or a singular problem (a variable that moves no goal, two that act as one) ends not met. | The Jacobian diagnosis notes say why, and the methods text says the search is local. There is no global search in v1 (§10). |
| **The scan can miss narrow second crossings** (it found 15 of 16 cases), and several-variable searches never look for others. | The result says so (D13); finding every answer is not a goal. |
| **The penalty residual is a heuristic.** | An unusable slope step is retried backward first (400 of 400 met at a failure edge, against 2 without); a column with no usable step is never used to explain an ending (`slope_unknown`). Measured no worse than stopping. Failed trials are listed. |
| **Jumps and unsolved crossings surprise users** ("no value meets the target"). | The message names the switching elements that carry flow, or the solve's message, and the closest value solved; it appears only when no evaluation meets the goal. |
| **The default tolerance (0.5 %) can read loose:** 249.8 kPa for a 250 kPa target is met. | It is D6's same answer (D13). The web shows the tolerance beside the target, and tightening it costs 0–3 solves. |
| **The flow and velocity floors are not cited values.** | They are designers' defaults, stated as such in the methods text and reversible. |
| **Bit-identity of Apply needs the exact float.** A rounded display value may lose "met" (2 of 364 at 6 digits). | Apply writes the returned float. The `sensitive` note warns where rounding matters. The e2e test checks the Links text. |
| **Two implementations of applying.** The web mirrors the override upsert; a drift would apply something else. | The generated shared fixture, with a staleness test. |
| **A new numeric allow-list field couples D15 and D16.** | The derivation test fails until the variable tables or `NOT_VARIABLES` name it. |
| **Coupled topology rules** (a controlled pump's speed and setpoint varied together) are not checked at the bounds. | Their trials are unusable and the search goes around them. A box entirely inside such a region ends as `no_usable_evaluation`, with the message. |
| **The modal dialog hides Build and Results** while setting up. | Two columns on desktop, "Now" values, last-solve hints, the trace entry, and closing during a run. |
| **The page-state setup is lost on reload.** | Apply as new scenario states the question; Copy report keeps the record. Saving setups is reversible Later. |
| **Pipe variables lapse when their connection's pipes change.** | Lapses are conservative and visible, and labels are current names. A deleted element's id stays reserved while a row names it, so a row never moves to a new element (§6.15). |
| **No streamed progress** in a run of up to 45 s. | An elapsed timer, "stops by itself after at most 45 s", and Cancel. |
| **The caps and constants were measured on the corpus** (up to about 1,000 components, mostly ≤ 200). Real networks with long Crane-tee manifolds or many controls may switch states more often. | `goal_seek_check` records the rates; the constants are reversible (D14) and stated in every result's methods section. |

---

## 10. Open points the owner may want to revisit (none blocking)

1. **Saved setups.** A `Project.goalSeeks` field (omitted when empty) holding the request models unchanged, with lapsing as the web does now.
2. **A start value and an evaluation limit in the request,** for API users who want another local answer or a cheaper run.
3. **More goals:** network extremes, absolute pressure, HGL/EGL, efficiency (two answers or none at its peak), power, a controlled pump's speed.
4. **A coefficient select** for resistance variables (vary a Cv on a valve that holds a K).
5. **Applying a scenario run's values to the base,** re-solved there.
6. **An adaptive scan** (fewer points when the start solve is slow): measured to meet a 499-component case in 4 solves instead of 10, at the cost of a machine-dependent path.
7. **A global or multi-start search** for several variables, or a trf fallback when dogbox stalls.
8. **Streamed progress** through the gzip middleware and Cloud Run.
9. **The tolerance floors for flow and velocity**, and the stop margin of a tenth, if users find them too tight or too loose.
10. **More than 4 variables**, or larger caps on large networks, after `goal_seek_check` has run on real projects.
11. **A goal-seek version label**, with its changelog served by `GET /api/v1/method-versions` and shown beside the method's, if reports or applied scenarios should name the search by a version (dropped after the review: decision 22).
12. **More than one goal seek in the pool at once** (`MAX_GOAL_SEEKS`), on a host with more workers, or the same admission limit for long system curves.

---

## 11. Design review

Two reviewers (numerics: N-N1 to N-N8; web and API: W-R1 to W-R15) raised 23 issues against the synthesized design. The reviser checked each one against the code (SciPy 1.18.1, `apps/api`, `apps/web` at `e0dff4b`) and, for the numerical ones, by experiment. The reviewers' scripts are in the workflow scratchpad's `goalseek/critic-numerics/`, and the reviser's in `goalseek/reviser/`; neither is committed. Their results are the rows marked **R** in §3.11. Every issue was real. N-N2's fix differs from the reviewer's first option, and W-R3 repeats N-N1. The decisions of §1.2 are the final list; the rows marked R changed in this review.

| Issue | Verdict | What changed |
|---|---|---|
| **N-N1** (major) The map from u to x leaves the box on log variables, gives a 500 at the field maximum, and breaks the start and `atBound` | **Confirmed.** `FlowCoefficient` rejects the u = 1 trial 10000000.000000006, and the start misses its own x for most log values. | §3.1 step 2 specifies the map: exact at u = 0, at u = 1 and at the start, clamped elsewhere, a `middle` start equal to x(1/2), and exact bounds in shifted coordinates. `atBound` is decided by value. Decisions 4–6, §2.1, §2.6 and §3.2 are updated, with map tests in §7.1. Measured: 0 of 1,300,000 trials outside the bounds. |
| **N-N2** (major) Closing a jump to 10⁻¹⁰ of u costs more than the 40-evaluation cap leaves | **Confirmed** (median 32 solves to close; 1,690 of 2,000 runs over 40). Of the two fixes offered, this design takes the alternative (raise the cap), not the 10⁻⁶ jump rule. A real check valve's opening is continuous, yet a root 5×10⁻⁷ of u from the switch shows −3 and +3 tolerances across a 10⁻⁶ bracket whose states differ. The 10⁻⁶ rule would call it a jump, a false "no value meets it". | `EVALUATIONS_ONE` = 60 (decision 16, §3.8, §3.10): 2,000 of 2,000 jumps named, and 1,996 of 2,000 meet the next root. The prototype's 6 real jump targets are unchanged, at 32–40 solves. `BRACKET_XTOL` stays 10⁻¹⁰, with the reason in decision 14, §3.7 and §3.10. Updated: §3.3 step 4, the methods text and the D16 draft. |
| **N-N3** (major) Dogbox's first trust radius is max \|u0\|, tiny for starts near the lower bounds | **Confirmed** (SciPy `dogbox.py` line 175). On a linear problem, 13 solves at u0 = 0.05 and 40 at (10⁻⁴, 0), against 4. | Least squares runs in v = u − u0 with bounds (−u0, 1 − u0), so it meets that problem in 4 solves from every start (decision 12, §3.4). The Jacobian's backward rule is restated in v. Updated: §5.4 item 3, and §7.1 tests from starts near the bounds. |
| **N-N4** (minor) A response can say success with stop reason `jump`, and the `met_range` note can misstate which point is reported | **Confirmed**, from §3.2, §3.3 and §3.5 as written. Two further mis-statements turned up: `met_range` said "every value solved from a to b" for met points that need not be contiguous, and the jump message said "the closer side is reported" when the reported evaluation can lie elsewhere. | The stop reason is derived after the reported evaluation (§3.3 step 10, §3.5): `jump`, `unsolved_crossing`, `not_reachable` and `no_progress` only when nothing is met. `met_range` now gives a count and the actual tie rule, and `met_without_crossing` is worded generally. The jump messages give "the closest value solved" (§5.2, §6.9). The reviewer's case is a test (§7.1). |
| **N-N5** (minor) `ROUNDING` = 5×10⁻⁷ understates 6-digit rounding by up to 10× | **Confirmed** (up to 4.97×10⁻⁶; above 5×10⁻⁷ for 61 % of values). | The `sensitive` test uses the value's own rounding, \|∂g/∂x\| × \|round6(x) − x\| > tol, with no constant (`SIGNIFICANT_DIGITS` replaces `ROUNDING`). The note carries the rounded value, the estimated change and the two evaluations of its slope (§5.3, §3.10). The x = 0.1000004 test is in §7.1. |
| **N-N6** (minor) A penalty column in the last Jacobian gives a false `variables_collinear` or misses `variable_no_effect` | **Confirmed** (12 of 12 `no_progress` endings with a false collinear note). Further, a start at a failure edge, where the forward step crosses it, met in 2 of 400 runs. | An unusable slope step is retried backward (400 of 400 met in 5 solves). The diagnosis uses only columns with a usable step, and a new note, `slope_unknown`, covers the rest (decisions 12 and 13, §2.6, §3.4, §3.6, §5.3, §6.9). Edge tests are in §7.1. |
| **N-N7** (minor) The `not_reachable` messages assert impossibility that the search did not establish | **Confirmed**: no sign change among 10 solved values does not rule out a narrow double crossing (§3.11: 3.4 % one turning point, the scan finds 15 of 16). | The API, methods and web texts now say what was solved ("at none of the {k} values solved … does its residual change sign; a crossing between two solved values is not excluded"), with the scan's resolution (§3.3 step 8, §5.2, §5.4 item 2, §6.9). The `no_progress` message, which said the goals "cannot all be met from this start", now says the search is local. |
| **N-N8** (minor) At 4.4 s per solve the one-variable search does not fit, the table and §9 are optimistic, and the index-order scan wastes a cut scan | **Confirmed**: under the 1.5× + 1 s rule, 9 evaluations start at 4.40 s. The table's "fits" was the prototype's 3.28 s under a 1.2× rule, and at 999 Crane components only 3 evaluations start, not 4. | §3.8 gives the rule's formula, (m + 0.5)·t ≤ 44, and a recomputed table: 499 components bind after 9, 999 Crane after 3, other rows recounted. §9 gives about 3.5 s per solve. The scan is solved coarse to fine (0, 1, 1/2, 1/4, …): the same points, so a complete scan is unchanged (§3.3 step 1, §3.10, §5.4). |
| **W-R1** (major) A goal seek on a never-solved project is never marked out of date | **Confirmed** (`#restale` returns when no case has results, `project.svelte.ts` 673–675). | `#replace` recomputes the goal-seek and applied staleness itself, with the shared fingerprint (§6.11, §6.15, decision 29). Store and e2e tests cover a never-solved project (§7.5, §7.6). |
| **W-R2** (major) The 400 input messages contain ids, which SDD §5.1.2 forbids | **Confirmed**: SDD §5.1.2 says "no input values, tags or ids in messages", and the scenario 400 keeps ids in `componentIds`. `MISSING_HOLDER` formats ids, but only into 200 results. | The step-5 messages name the element's kind, never its id; ids go in `componentIds` and `connectionIds`; goal seek words its own not-applicable texts (§4.2, §4.4, §4.5, decision 23). The sentinel test covers ids (§7.1). The SDD §5.1.2 goal-seek rows are added to §8. |
| **W-R3** (major) The log map is inexact at the ends: trials outside the user's bounds, a 500 at the field maximum, missed cache hits | **Confirmed; the same defect as N-N1.** | As N-N1. The cache is keyed by the exact x (§3.1 step 3), and the map makes the start, the bounds and the middle start exact hits. |
| **W-R4** (major) Two clients' goal seeks hold both workers; other users' solves time out | **Confirmed**: 2 workers, and a budget counted from arrival (`workers.py`). A system curve on a large network can already hold a worker for long; goal seek makes long requests deliberate. | `MAX_GOAL_SEEKS = SOLVE_WORKERS − 1` goal seeks in the pool, counted until their work stops. Another gets 503 `SERVER_BUSY` with `Retry-After` (decision 24, §4.3, §3.10, §8, §9). System curves are unchanged; an admission limit for them is open point 12 (§10). Covered by an API test (§7.1). |
| **W-R5** (major) Unlisted Solve buttons would silently cancel a running goal seek | **Confirmed**: seven controls in five components start a solve, each with its own busy test, and "Solve now" has none. | One store getter, `calculating`, with one reason helper, used by every control. The store refuses a solve during a goal seek, and a goal seek during a solve, rather than dropping either; only Cancel, `load()` and `dispose()` stop one (decision 27, §6.8, §6.15). `CompareView` and `ResultsStateNotice` are added to §8, with component tests (§7.5). |
| **W-R6** (minor) Three request rules are unpublished validators that the web copies | **Confirmed** under D10. | `x-ordered-fields` on the three variable schemas (`lower` < `upper`), and `x-goal-seek-rules` (`sameLength`, `uniqueBy`) on the request (§2.1, §2.4). The web reads them (§6.4, §6.5), `test_schema_rules.py` checks them (§7.1), and D10's list grows (§8). |
| **W-R7** (minor) In a scenario run, the `scenario` record states an override's value that the solve did not use | **Confirmed** (`OverrideResult.value` is "the value used"). | Each variable carries `replacedOverride`, the index it replaced, and the response field's description says so. `/solve`'s `OverrideResult` is unchanged (decision 20, §2.6, §4.4, §5.4). The metamorphic tests check it (§7.1). |
| **W-R8** (minor) A control valve's default is ideal (K = 0), not Crane, giving default bounds [0, 0]; the maximum-speed default can equal `minSpeed` | **Confirmed**, both (`ControlValve`, `valves.py` 17–18; `Pump._check_speed_limits`). While revising, a third edge appeared: a `minSpeed` of 99 % or more rounds up to the 100 % upper bound. | Texts follow the valve's actual default: Crane for isolation and check valves, ideal for control valves. An ideal control valve gets 0.01 to 100 and "Now: ideal (K = 0)". The maximum speed starts at the smallest whole percent strictly above `minSpeed`, or halfway to 100 % (decisions 3 and 31, §5.4, §5.5, §6.5, §6.6, §7.5). |
| **W-R9** (minor) NPSH available has a value at zero flow; only the margin is null | **Confirmed** (`results.py` 723, 786–791). | "No value" now means a null published field or an absent result. NPSHa keeps its value at zero flow, and only the margin lacks one (§2.2, §7.1). |
| **W-R10** (minor) Some numbers in the result cannot be traced to their inputs: every floor credited to D6, ρ unstated, the `sensitive` slope unreferenced | **Confirmed.** | The methods text credits each floor to its own source (head to D6; flow and velocity to D16, "not in D6") and states ρ for pressures (§5.4 item 6, decision 9, §2.2). The `sensitive` note names its two evaluations (§5.3). |
| **W-R11** (minor) `GOAL_SEEK_VERSION` has a changelog that no endpoint publishes | **Confirmed** (`/api/v1/method-versions` serves `METHOD_CHANGELOG` only). | This design takes the simpler option: the label is dropped. GOALS §4.3 concerns a project's results, which applied values leave to `METHOD_VERSION`, and the methods section states every constant of §3.10 (decision 22, §1.3, §2.1, §2.6, §3.10, §5.4, §5.7, §6.9, §6.10, §9, D16 draft). A published label is open point 11 (§10). |
| **W-R12** (minor) A deleted element's id is reused at once, so a row moves silently to a new element | **Confirmed** (`newId` takes the first unused id; `usedIds` reserves only scenario-named ids). The other fix offered, recording kind and ports, would miss a same-kind element at the reused id. | While a row names an id, it is reserved through `newId`'s `alsoUsed`, as D15 reserves scenario-named ids. A deleted element's row stays lapsed, and Undo makes it current (decision 30, §6.4, §6.5, §6.15, §8, §9). Covered by tests (§7.5). |
| **W-R13** (minor) Zero-flow label flips would be named as state changes (D13) | **Confirmed.** | A state change counts only for an element with a flow above 10⁻⁶ m³/s in one of the two states (§3.1 step 6, decision 14, §3.7, §3.10, §5.2, §5.3). A test covers a zero-flow flip beside a real switch (§7.1). |
| **W-R14** (minor) A new `NotFoundError` for every 404 would reclassify `/solve`'s 404s as network errors | **Confirmed** (`client.ts` 247–257; `toResultsError`). | `NotFoundError` extends `ValidationError`, keeping its issues (§6.15). A client test checks that `/solve`'s unknown-scenario 404 still maps to `validation` (§7.5). |
| **W-R15** (minor) The pressure tolerance minimum depends on ρ, so the web cannot check it before Run | **Confirmed.** | Fixed minima per quantity: 0.1 Pa for pressures, 10⁻⁵ m for heads, 10⁻⁹ m³/s for flows and 10⁻⁶ m/s for velocity, published in `x-goal-quantities` as `minimum.absolute`. The web's Tolerance field enforces max(10⁻⁶ × \|target\|, minimum) (decision 9, §2.2–§2.4, §4.2, §6.4, §7.1, §7.5). |
