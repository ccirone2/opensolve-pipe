# D11. Speed-controlled pumps (VFD), slice 1: flow setpoint

Decision D11 of the OpenSolve Pipe decision record ([index](README.md)). Decisions override the specs; `docs/GOALS.md` overrides decisions. Code and tests cite this decision as `CLAUDE.md D11`.

Design proposal: [`vfd-pump-modes.md`](../proposals/vfd-pump-modes.md).

---

Design and owner's answers: `docs/proposals/vfd-pump-modes.md`.

### Model

`Pump.control = {mode: "flow", setpoint, minSpeed}`; omitted means fixed speed. The setpoint is the volumetric flow through the pump, suction → discharge, 0 < Q_set ≤ 100 m³/s. For a controlled pump `speed` is the maximum speed (≤ 1). `minSpeed` is required, with no default, and `minSpeed < speed` is a model rule (400) published as `x-ordered-fields`. *(GOALS §4.1: no tool or paper cites a default minimum speed; §4.2: the field's meaning is stated, not inferred.)*

### Solve

F(s, Q) = s²H₀(Q/s) rises with speed on [s_lo, speed], s_lo = max(minSpeed, Q_set/x_mono) (below `speed`: see the setpoint rule under *Uniqueness*). While a speed there holds Q_set, F(s_lo, Q_set) − Htol ≤ EGL_d − EGL_s ≤ F(speed, Q_set) + Htol, the pump is a fixed-flow link (EPANET 2.2's "pump of a specific flow": a demand at the suction, a supply at the discharge), and its speed is recovered afterwards as the unique root of F(s, Q_set) = EGL_d − EGL_s on [s_lo, speed] by Brent's method. This is exact: the speed enters only the pump's own head equation. s_lo exceeds minSpeed only when Q_set/minSpeed lies beyond x_mono on the curve's end tangent, where head falls as speed rises: no stable flow controller holds that stretch. There, for a head at Q_set between F(s_lo, Q_set) and F(minSpeed, Q_set), the pump at minSpeed passing more than Q_set is a steady state too (a drive saturated at its minimum); the solve starts active and does not leave that state for a head in that band. A setpoint with Q_set/`speed` itself beyond x_mono is rejected (*Uniqueness*): no speed in the range would be on a rising stretch, and two limit states (max_speed by rule A1, and minSpeed passing more than Q_set) could both satisfy the rules, so the result would depend on the solve's path. *(GOALS §4.1: exact, and checkable in closed form and by EPANET.)*

### Uniqueness

A controlled pump's curve must have ψ = 2H₀ − xH₀′ > 0 on [0, x_last], checked exactly on the PCHIP pieces; otherwise `CONTROLLED_PUMP_CURVE` (422). On a curve that passes, a setpoint Q_set ≥ `speed` × x_mono (x_mono: twice the flow at which the curve's falling end tangent reaches zero head; infinite, so never reached, when the end tangent does not fall) is `CONTROLLED_PUMP_SETPOINT` (422, with every other issue; owner's decision 2026-10-23), as is Q_set/x_mono ≥ `speed`, the same test in quotient form, so that s_lo < `speed` in floating point too. Drooping curves that pass are accepted. The test guarantees a unique speed root (one speed per head at a flow), not a unique operating state: on a drooping curve the limit rules close the pump against s²H₀(0), as v1 closes a fixed pump, so a running state with a head above that is not found (no flow, flagged invalid; or, at minSpeed, not converged). EPANET 2.2 rejects such curves (error 227); the owner kept this v1 behaviour, documented (2026-10-23, TSD §12). *(GOALS §3: a speed that is not unique would be an arbitrary answer.)*

### Limits

Above the band the pump runs as the fixed-speed pump at `speed` (the link's own law, bit-identical), below it at `minSpeed` (a per-solve `LinkState.law` override), and it keeps running at low demand (no sleep). The setpoint is then not held: `PUMP_SETPOINT_NOT_MET` (info). At zero flow it closes and re-opens as the fixed-speed pump at `speed`. Re-solved as that fixed pump, a network gives the same result where it has one steady state that satisfies every rule; where it has several (v1's zero-flow multiplicity, D9), the two solves may reach different ones, since their iterations differ (proposal §7.3, M1). *(GOALS §4.6: a pump at a limit is a valid state, flagged as information.)*

### Status rules

A0 (starved → maximum speed), A1/A2 (Htol band on F(s_max, Q_set) and F(s_lo, Q_set)), X1/N1 (back to regulating once the flow reaches the setpoint, EPANET 2.2 fcvstatus), X2/N2/C1 (EPANET 2.2 pumpstatus at the limit speed). They compare flows and head differences only, so the closed-off and floating-section logic applies unchanged; the fallbacks add a minimum-speed step between open and closed, and valve-only networks keep the v1 option sequence. Two flow controls in series holding the same flow (equal setpoints, the pressure between them undetermined) are reported as not converged, naming them, with a message that says the pressure between them is undetermined (over-controlled) whether the solve ends at a limit carrying the setpoint or with statuses cycling. No new tolerance: Htol and Qtol. *(GOALS §3: correctness over convergence.)*

### Results and traces

`PumpResult.speed` is the speed the pump runs at, and curve, range, efficiency (plain affinity, η₀(Q/s), no Sârbu–Borza correction), NPSHr and power are at that speed; `PumpResult.control` gives the mode, setpoint, state (active, max_speed, min_speed, no_flow, off) and whether the setpoint is achieved. The trace states the inequality that set the state, the speed root and its residual, s_lo, x_mono and the uniqueness margin; the methods summary describes speed control only when a project uses it. *(GOALS §4.2.)*

### System curves

The viewed pump's control is replaced by the fixed flow (H_sys as for any pump); other controlled pumps that are on keep regulating, and warm starts carry their statuses; the default range uses `speed` (the maximum). *(GOALS §4.2: one definition of H_sys.)*

### Versions

`schemaVersion` stays 1 (nothing deployed before slice 1); `METHOD_VERSION` 1.1.0, whose changelog says that the flows, heads, pressures, statuses and speeds of projects without speed control are unchanged, proven by the corpus comparison (TSD §10.4: every such value identical, with `pumpResults.*.control` null or absent, `compare --ignore-null`); their methods summary changes in the sentence on the outer loop's new oscillation fallback, which can also let a solve that did not converge before converge (none in the corpus or the fuzz), and in the Pumps section's system-curve item, which every summary has (with a pump or not) and whose references gain Ford–Fulkerson (the owner's system-curve decision, D10). The owner's decisions of 2026-10-23 (the setpoint rule above, and system-curve points solved again from other starts, D10) are in the same unreleased 1.1.0, each with a changelog line. *(GOALS §4.3: a controlled-pump result names a method version that has speed control.)*
