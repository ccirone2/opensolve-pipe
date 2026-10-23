# Speed-controlled pumps, slice 2: discharge-pressure control

**Status: design, not built.** The owner answered §13's questions on 2026-10-23 (recorded at the end of §13). This is the build-ready design of slice 2 of `vfd-pump-modes.md` (§4.10 there sketches it). Where this document and that sketch disagree, this document holds; §2.10 lists the corrections.

Written against `f9d402b` (branch `ccr-efab8cb5-vzm6cg`) by a design workflow: three independent designs, each taking one angle — **E** (solver exactness), **C** (edge cases) and **V** (verification) — then a judge, **J**, who resolved their conflicts against the code and re-measured the points where they disagreed. A two-lens adversarial review followed (physics and numerics, **PN**; verification and governance, **RVG**), each finding checked by a skeptic, and a reviser, **R**, re-checked the upheld findings against the code, re-measured where needed and revised this document; §14 records every finding and what was done. Every file:line reference is to `f9d402b` unless it says "working tree". No repository file was changed to measure anything. Every number marked *measured* names who measured it and with which scratch script (Appendix B). A number without that mark is derived in the text.

---

## 1. Summary and scope

### 1.1 What slice 2 adds

A pump can now hold a **discharge pressure** setpoint:

```
Pump.control = {mode: "discharge_pressure", setpoint, minSpeed}
```

- The drive varies the speed within [`control.minSpeed`, `speed`].
- It holds the **gauge static pressure at the pump's own discharge port** at the setpoint.
- `speed` stays the maximum speed, at most 1.

**How it works:**
1. **Regulating.** The pump link is the existing `FIXED_DOWNSTREAM_HEAD` link: the active-PRV form (`network.py:42-47`, `status.py:347-364`). It holds EGL_d = z_d + p_set/(ρg) + c_d·Q_d² at its own discharge port and passes the flow that leaves the port. The flow is coupled exactly in Newton's step (`gga.py:645-659`).
2. **Speed recovery.** After convergence, the speed is the unique root of s²H₀(Q/s) = EGL_d − EGL_s on [s_lo(Q), s_max], at the solved flow Q. This is exact by slice 1's block-triangular argument (§5.3).
3. **At a speed limit**, the pump is the v1 fixed-speed pump at that limit:
   - at s_max it uses the link's own law;
   - at s_min it uses the slice-1 `LinkState.law` override.
4. **Free-level logic.** Its rules compare the discharge head with the setpoint head, not only head differences. So the pump joins the PRV/PSV ("PRV-class") free-level logic of `_update_controls` (`status.py:464-473`), with exact zero-flow bounds (§5.7).
5. **Guards against answers the inputs do not determine:**
   - a running pump on an undetermined level (§5.8);
   - over-control (§5.9);
   - the second-state tests (§5.10): a static pressure that falls as the flow rises, where several states satisfy every rule, a closed pump whose running alternative also holds, and a pump sharing its discharge's pressure zone with another pressure source;
   - several pressure pumps on one pressure zone (§5.11).

### 1.2 Change sets

There are three change sets. Each has every gate green and its own commit.

| Change set | Contents | METHOD_VERSION | Proof that nothing else moved |
|---|---|---|---|
| **C0** | `compare.py --within-tolerance`, `corpus.py --solver-options` (the tight-tolerance dumps of §2.7 criterion 7), and their unit tests. No solver change. | unchanged | gates only |
| **C1** | The prerequisite: the velocity-head coupling of a held downstream head (PRVs now, and the pressure pump in C2), §2 | **1.2.0** | Exact identity for projects with no PRV whose status is `active`; for the rest, within measured tolerances at default settings and the same fixed point at a tight tolerance (§2.7) |
| **C2** | Slice 2: model, solver, results, traces, methods, web, reference cases, fuzz profile | **1.3.0** | Exact corpus identity (C1 tree against C2 tree) for every project without discharge-pressure control |

### 1.3 Standing answers applied (not re-asked)

- The setpoint is the static pressure at the discharge port only.
- `minSpeed` is required and has no default.
- At low demand the pump runs at minimum speed (no sleep).
- `speed` is the maximum speed, at most 1 (no overspeed).
- D6 for speed: within 0.5 % relative, and the implied head s²H₀(Q/s) within 0.01 m.
- Efficiency follows the plain affinity law, η₀(Q/s).
- schemaVersion follows proposal §3.5's rule (§4.5).
- C1 is measured on the corpus and versioned on its own, before slice 2.

### 1.4 Interaction with work in progress

While this design was written, another session left an uncommitted change in the working tree. It touches `status.py`, `builder.py`, `pumps.py`, `system_curve.py`, `methods.py`, `trace.py`, `version.py` and `tests/differential/generator.py`, for the owner items "setpoint rule, curve cold retry". Its effects on this design:

1. **The flow-setpoint rule.** A flow setpoint at or above s_max·x_mono becomes the topology issue `CONTROLLED_PUMP_SETPOINT`, which resolves TSD §12 item 5 for flow mode. Pressure mode has no build-time analogue, because its flow is solved, so the x_mono band of §5.6 item 6 stays a solve-time property.
2. **The system-curve change.** A cold retry of points without a head, then a start with the control valves open (`run_outer_loop(..., open_valves=True)`). This resolves TSD §12 item 4. Slice 2 builds on it unchanged: `initial_controls(open_valves=True)` opens only control valves, and a speed-controlled pump that is on still starts ACTIVE (working tree `status.py:311-345`). A pressure pump keeps that start, as a flow pump does; slice 2 changes no initial status (§5.5). *(Revised, RVG-19: an earlier draft said a pressure pump "should start at OPEN" there, which no section built or tested.)*
3. **Versions.** It adds its entries to the unreleased 1.1.0 changelog. If that stands, C1 is 1.2.0 and C2 is 1.3.0. Otherwise each takes the next minor version in turn.
4. **Re-running the proof.** The measurements of §2 are against `f9d402b`. The build re-runs §2.7 against the HEAD that C1 is committed on.

### 1.5 Later

- Suction-pressure control (the PSV shape).
- Remote control nodes.
- Differential pressure (slice 3).
- Mass-flow setpoints, overspeed, sleep or stop at low demand.
- Stations that share one transmitter, run at equal speed or stage lead/lag pumps. These need the US 8,265,911 review, proposal §9.1 item 8.
- Reduced-speed efficiency corrections.
- A falling-static-pressure check for PRVs (§12, risk 7).
- An exact Newton step on the whole downstream response of a held head, where the outlet pipe alone loses at most one velocity head (§2.3, risk 15).

---

## 2. Prerequisite C1: the velocity-head coupling of a held downstream head

### 2.1 Today

An active PRV holds its outlet node at H_set = V + c·Q_ref², where:
- V = z + p_set/(ρg);
- c = 1/(2gA²) is taken from the end segment of its outlet pipe;
- Q_ref is that pipe's flow (`LinkState.head`, `network.py:71-77`).

The held value is evaluated at the current iterate (`known_heads`, `gga.py:690-698`). So the reference pipe's energy residual contains −c·Q_ref², whose exact flow derivative is −2c·Q_ref·sign.

The Newton step adds that derivative only where it is positive (`gga.py:798-804`):

```python
extra[pos] += max(sign * 2.0 * st.coefficient * q_ref, 0.0)
```

The held node is the start of a PRV's outlet pipe (sign −1). So for forward flow the term is always negative and always dropped, which means it is lagged.

**Contraction ratio.** Take a held node whose downstream path loses r velocity heads of the outlet pipe, so that dEGL/dQ = 2rcQ at the port. The lagged iteration then multiplies the flow error by 1/r per step.

*Measured* (E, `exp2`). Network: R1 at 60 m → 50 m of 0.1 m pipe → PRV at 200 kPa → 0.1 m spool of length L with an exit fitting → R2, with R2's level set so that Q = 0.03 m³/s. Iterations are for the active solve alone.

| L (m) | r | 1/r | Measured multiplier | Iterations, lagged | Default solve (100 iterations) |
|---|---|---|---|---|---|
| 0.1 | 1.0171 | 0.9832 | 0.9683 | 941 | not converged |
| 0.3 | 1.0512 | 0.9513 | 0.9357 | 339 | not converged |
| 1 | 1.1705 | 0.8543 | 0.8536 | 98 | converged |
| 2 | 1.3411 | 0.7457 | 0.7609 | 68 | converged |
| 5 | 1.8527 | 0.5397 | 0.5613 | 37 | converged |
| 10 | 2.7054 | 0.3696 | 0.3795 | 25 | converged |
| 30 | 6.1163 | 0.1635 | 0.1642 | 16 | converged |

*Measured* (J, `j1`). Network: R1 at 50 m → 100 m of 0.1023 m pipe → ideal PRV at z 0 → spool of L m (0.1023 m, exit) → R2 at 5 m, with setpoints chosen for about 1, 2 and 3 m/s. Today, every spool of 0.05, 0.3, 0.5 and 1 m ends **not converged** at the default 100 iterations (111 inner iterations over the outer loop). Longer spools converge: 58–66 iterations for 2 m, 28–37 for 5 m, 15–18 for 20 m.

V (`exp1`) found the same thresholds. Its counts match n ≈ ln(10⁻⁹)/ln(1/r) within about 10 %:

| r | Predicted | Measured |
|---|---|---|
| 1.197 | 115 | 108 |
| 1.395 | 62 | 60 |
| 1.986 | 30 | 28 |

**Finding.** Today an active PRV whose outlet loses only a little more than one velocity head (r ≲ 1.2: a spool of about 1 m or less with an exit fitting into a tank) needs more than the default 100 iterations and ends not converged, although a valid active state exists. J and V measured this for spools of 1 m or less; E's 1 m spool (r = 1.17) just made it, in 98 iterations. The web app adds an exit fitting wherever a connection arrives at a reservoir (`withReservoirLosses`, `apps/web/src/lib/utils/edit.ts:152-175`).

### 2.2 The change

`gga.py:795-805` becomes:

```python
extra = np.zeros(nl)
own = offset_arrays.own_slopes(q_all)[in_series]
np.add.at(extra, series_pos, np.where(own < 0.0, 0.0, own))   # unchanged
negative = np.zeros(nl)
for k, pos, sign in held_reference:
    st = states[k]
    q_ref = float(q_all[st.reference_link])
    term = sign * 2.0 * st.coefficient * q_ref
    if term > 0.0:
        extra[pos] += term                  # as today: max(term, 0) == term
    elif st.mode is LinkMode.FIXED_DOWNSTREAM_HEAD:
        negative[pos] += term               # today dropped
slope = d + extra
if negative.any():
    combined = slope + negative             # the exact diagonal
    slope = np.where(combined >= JACOBIAN_FLOOR_RELATIVE * slope, combined, slope)
d_inv = 1.0 / jacobian_slopes(slope, is_pipe, s, e, n)
```

**The rule.** For a held downstream head (an active PRV now, and in C2 an active discharge-pressure pump), the velocity-head term enters the reference pipe's Jacobian slope with its exact value wherever the slope with it stays at least `JACOBIAN_FLOOR_RELATIVE` (10⁻⁶, `gga.py:101-110`) times the slope without it. Otherwise it stays lagged.

**Bit-identity:**
- An iterate with no negative term of a held downstream head runs exactly today's floating-point operations, in today's order.
- A PRV can be ACTIVE at an iterate only if its status is `active`: `initial_controls` starts such a PRV ACTIVE (`status.py:335-339`), and a `failed_open` or `failed_closed` one is fixed. A PRV that ends open or closed may still have been ACTIVE at earlier iterates, and then its path changes (RVG-1).
- So a network with **no PRV whose status is `active`**, whatever its PSVs, is bit-identical: a PSV with forward flow has a positive term, added today; a PSV with reverse flow keeps today's lag.
- *Measured* (§2.4, R `m5_prv_status_split.py`): all 1,956 corpus projects with no PRV whose status is `active` are identical (1,745 with no PRV, 211 whose PRVs are all `failed_open` or `failed_closed`). A project whose PRVs all end open or closed can differ: 612 such projects did (RVG `rv1_active_split.py`; for example fuzz_101, PRV2 and PRV7 open, 196 differences of round-off size, inner iterations 24 → 21).

**Why only the PRV form (resolution R1).** The designs measured both scopes on the corpus (§2.4):
- Including PSVs (E, V) adds a state change (fuzz_1446: PRV2, PSV3 and FCV4 states, V) and an iteration stall (fuzzfc_10256, 35 → 116 inner iterations, C: caused by PSV4's reverse-flow term).
- No design measured a PSV that converged badly because of the lag.
- A PSV's negative term arises only on an iterate with reverse flow through it, a transient state its own rule closes.

**Why the relative threshold (resolution R2).**
- Pipes are never floored except at 10⁻¹² s/m² (`jacobian_slopes`, `gga.py:188-209`). With a test of "slope > 0" (C, V), a combined slope of 10⁻¹² of the pipe's own would be used, putting a Schur weight 10¹² away from its neighbours.
- `JACOBIAN_FLOOR_RELATIVE` already exists to keep a Jacobian weight within 10⁶ of its neighbours'. This reuses it with the same meaning, and its docstring gains this second use (E).
- The two thresholds differ only where r_ref lies within 10⁻⁶ of 1. The two measured runs of the PRV form differ by one project (3,197 against 3,196 identical, §2.4). Neither run has a convergence change or a state change of its own.

**Two held heads on one pipe** (a pump discharge → pipe → PSV inlet). The positive terms are summed first, and the negative ones are then tested on the sum, so the order of `held_reference` does not matter (E).

### 2.3 Why it converges, and what it does not change

**Where combined ≥ 10⁻⁶·slope**, the step is exact in the held-node coupling. Newton then converges quadratically near a regular root.

*Measured* (E, `exp13`, 0.3 m spool), flow error per iteration:

| | Error sequence |
|---|---|
| Exact | 2.8e-2, 1.2e-1, 4.8e-2, 1.4e-2, 2.3e-3, 7.8e-5, 9.6e-8, 1.5e-13, 0 |
| Lagged | ratio about 0.94 per iteration |

*Measured* (J, `j1`): 6–8 inner iterations for every spool from 0.05 to 20 m and every setpoint, converged active. Where both versions converge, flows agree within:

| Spool | Flow agreement |
|---|---|
| 2 m | 2.5·10⁻⁹ |
| 5 m | 1.0·10⁻⁹ |
| 20 m | 2.8·10⁻¹⁰ |

These are the lagged answers' own convergence error.

**Where combined < 10⁻⁶·slope** (r_ref ≲ 1: the reference pipe alone, with any branch path in series at its far end, loses at most one velocity head), the lag stays. The test is local: only the reference pipe's own slope d plus the own slopes of head offsets in series at its far node enter it (`gga.py:617-631`, `795-805`). An ideal tee, or a Crane run carrying no branch flow, adds none. The iteration then contracts at 1/r_tot per step, where r_tot is the response of the whole downstream path, so it needs about ln(10⁹)/ln(r_tot) iterations: more than the default 100 for r_tot ≲ 1.2.
- *Measured* (E, `exp12`): a 0.5 or 3 m spool without fittings into an ideal tee and a 30 or 300 m main with an exit. Lagged and C1 give identical iterations and states, because the exact term is not applied.
- *Measured* (PN, `r2_prv_tee.py`; today and with C1 identical, all three setpoints): R1 50 m → 100 m of 0.1023 m pipe → ideal PRV → spool L_s without fittings → tee (ideal, or Crane with its branch to a plug) → L_a with an exit → R2 5 m, setpoints for 1, 2 and 3 m/s.

  | (L_s, L_a) | r_tot | Default solve (100 iterations) |
  |---|---|---|
  | (0.3, 0.3) m | ≈ 1.11 | not converged: 113 inner iterations (ideal tee), 326 (Crane) |
  | (0.5, 0.5) m | — | not converged, as above |
  | (0.3, 1.0) m | ≈ 1.23 | converged in 82–90 iterations |

- *Measured* (PN skeptic, `s1_tee_long.py`, C1 applied, `max_iterations` 2000): (0.3, 0.3) converges in 169–182 inner iterations and (0.5, 0.5) in 108–113. The cause is the rate of the lag, not the fixed point.
- So where r_ref ≤ 1 < r_tot ≲ 1.2, an active PRV, and in C2 an active pressure pump, can end **not converged** at the default settings, although a valid active state exists (§6 row 2; cases VH7 and PVH5). C1 does not change this. An exact step on the whole response (the held-head term is a rank-one change of the Schur matrix, applicable by Sherman–Morrison with the existing factor at the cost of one extra solve) would; it is a separate method change, needing its own measurement and corpus run, and is Later (§1.5, risk 15).

**The fixed point is unchanged in both cases.** Only the path and the rate change.

**r_tot ≤ 1: the static pressure at the port falls as the flow rises.**
- For a single held node, the lagged term is a rank-one change of the Jacobian. The iteration's multiplier on that mode is 1/r_tot > 1, so it cannot converge to such a forward root.
- *Measured* (E, `exp2`/`exp3`): a PRV with no exit fitting, L = 0.1 to 5 m (r = 0.017 to 0.85), ends with the PRV **closed** in all 5 cases. The active iteration finds the reverse-flow root instead (Q* = −0.0295 to −0.0073 m³/s).
- *Measured* (V, `exp3`): with no exit fitting, both versions give the same states. The PRV is open for a setpoint above R2's static head and closed below it.
- **These are not unique states** (PN4, RVG-5). With r < 1 a PRV ends in one of several rule-valid states (risk 7). *Measured* (PN, `r3_prv_noexit.py`): with the PRV open, the outlet static head is 2.3334, 2.7586 and 4.5603 m for 0.1, 1 and 5 m spools, and OPEN satisfies prvstatus for every setpoint head between that and R2's 5 m; the default solve reports closed in all 9 runs (setpoints 4.9, 4.5 and 4.0 m), and OPEN is also valid in 7 of them. *Measured* (RVG, `rv6_vh6_states.py`, reference laws and `checks.rule_prv` only): for spools of 0.5, 0.1, 0.5 and 2.0 m at setpoints of 4.5 or 4.8 m, closed, active at the unstable forward root (Q 0.026932, 0.025966, 0.017065 and 0.020258 m³/s) and open (about 0.0598 m³/s) all satisfy the rules; the solver reports closed in all four (`rv8_vh6_solver.py`). CLOSED is the unique valid state only when the setpoint head lies below the open state's static head by a margin (VH6, §2.9).
- **Several held nodes.** Two parallel pressure pumps started symmetrically reach the symmetric, control-unstable active state (E, `exp12`), because the error has no component in the unstable antisymmetric mode. A held head beside another pressure source on one header can also leave two rule-valid states with r > 1 at the pump: a PRV and a booster at equal setpoints, *measured* by PN (`r6_prv_parallel.py`; §5.10 V6). §5.11's zone rule refuses two pressure pumps on one zone; §5.10's second-state tests refuse the measured layouts that rule leaves, a PRV or another pump beside a booster among them. Neither is a proof for every layout (§5.10, limitation).

### 2.4 Measured on the corpus

*Measured* (J, `corpus_judge.py`, the §2.2 code applied in memory). Before: today's dump made by V (`verification/corpus_before`). Both dumps are of 4,120 projects with system curves. 3 workers; 499.9 s wall time.

| Result | Value |
|---|---|
| Identical / different | 3,196 / 924 |
| Projects with no PRV whose status is `active` | all 1,956 identical: 1,745 with no PRV, 211 whose PRVs are all `failed_open` or `failed_closed` (R, `m5_prv_status_split.py`, by component). J's split by trace text (`j4_split.py`) found 1,702 without "PRV", 498 of them with a PSV, all identical. |
| Projects with a PRV whose status is `active` | 2,164: 1,240 identical, 924 different |
| Projects that differ | every one has a PRV whose status is `active`. By final state (RVG, `rv1_active_split.py`): 208 end with a PRV active, 612 with every PRV open or closed, and 104 with no PRV result |
| Converged flag changes | 0 |
| State changes | 1: fuzz_1656, FCV1 and FCV3 open → closed |
| System-curve point counts | 1: fuzz_2197, PU4 from 7 to 11 converged points |
| Largest flow change | 7.73·10⁻¹⁰ × the project's largest flow (fuzzfc_10339) |
| Largest EGL change | 2.82·10⁻⁸ m (fuzz_2005) |
| Largest HGL and static pressure change | 2.89·10⁻⁸ m of head (fuzz_2005) |
| Largest speed change | 6.97·10⁻¹⁵ relative |
| Largest system-curve head change | 3.9·10⁻³ m on a 1.49·10⁸ m point (fuzz_2745; 2.6·10⁻¹¹ relative) |
| Large relative changes | only in quantities at round-off flows: K_eff ≈ 1.456·10²⁶ of a nearly closed PRV (fuzzfc_10246); laminar f = 64/Re at Re ≈ 10⁻⁷ (fuzz_102) |
| Inner Newton iterations | 93,631 → 90,217 (505 projects fewer, 41 more) |

Largest drops in inner iterations: fuzz_2605 217 → 47, fuzzfc_10874 138 → 27, fuzz_2197 121 → 28.

**Largest rise: fuzzfc_10269, 54 → 111.** This is a pre-existing round-off floor, not a defect of the change (E `exp7`–`exp9`; C `debug_*`):
- one transient inner solve reaches EGLs of 1.7·10⁹ m;
- the unit in the last place there (2.4·10⁻⁷ m) exceeds `ENERGY_TOL` = 10⁻⁷ m (`gga.py:124`);
- the energy residual alternates between 1.106·10⁻⁷ and 1.279·10⁻⁷ m;
- the outer loop's fallback reaches the same final state.

**The scope and threshold variants, all measured against the same "before":**

| Variant | Measured by | Identical / different | State changes | Other |
|---|---|---|---|---|
| PRV and PSV, slope > 0 | V; C ("variant 1") | 2,841 / 1,279 | fuzz_1446, fuzz_1656 | fuzz_2197 7 → 11 points; inner 93,631 → 88,258; fuzzfc_10256 35 → 116 |
| PRV and PSV, slope ≥ 10⁻⁶ × | E | 2,840 / 1,280 (1,428 projects without an active PRV or PSV not re-solved) | fuzz_1446, fuzz_1656 | fuzz_2197 + 4 points |
| PRV form, slope > 0 | C ("variant 2") | 3,197 / 923 | fuzz_1656 | inner 93,631 → 90,285 |
| **PRV form, slope ≥ 10⁻⁶ × (chosen)** | J | 3,196 / 924 | fuzz_1656 | fuzz_2197 7 → 11 points; inner 93,631 → 90,217 |

The worst flow and EGL changes are the same in every variant: 7.73·10⁻¹⁰ and 2.82·10⁻⁸ m.

**Where the flow changes come from** (PN8). fuzzfc_10339, the project with the largest flow change, has no active PRV at convergence: its change comes from the iteration path (warm starts, below), not from the lag error of its final state. *Measured* (PN, `r4_rule_v_proxy.py`, all 4,120 projects): the 179 active PRVs with forward flow at convergence (173 projects) have r ≥ 2.358 (fuzz_2005, PRV1), so ρ = 1/r ≤ 0.424, and a final iterate's lag error is at most ρ/(1 − ρ) ≤ 0.74 times its last flow step.

**The fixed point, at a tight tolerance** (RVG-3). *Measured* (R, `m2_tight.py`, `m2_analyze.py`): every project with a PRV whose status is `active` (2,164; the others are bit-identical by construction), solver options overridden to tolerance 10⁻¹³ and `max_iterations` 1000, main solve without system curves, f9d402b against the §2.2 code:

| Result | Value |
|---|---|
| Converged in both | 2,163 |
| Not converged in either | 1: fuzzfc_10070, in both trees, by design (PU6 and PU7 in series with equal flow setpoints, D11) |
| Largest flow difference | 8.42·10⁻¹³ × the project's largest flow (fuzz_2005, RN0 outflow) |
| Largest EGL or HGL difference | 6.92·10⁻¹⁰ m (fuzzfc_10679, IV3 outlet HGL) |
| Largest pressure difference | ρg·7.63·10⁻¹⁰ m (fuzzfc_10679) |
| Speeds | identical |
| State differences | fuzz_1656 only (FCV1 and FCV3 open → closed, the zero-flow multiplicity above) |

So the two iterations reach the same fixed point to about 10⁻¹² of the flow; the default-settings differences above are the convergence error of 1.1.0's lagged iteration and of the iteration path. No lagged solve failed to converge at 10⁻¹³ within 1000 iterations, and none stalled at the `ENERGY_TOL` floor (fuzzfc_10269 converged in both).

**With the methods sentence** (RVG-2). *Measured* (R, `m1_corpus_methods.py`, `m1_analyze.py`, 2 workers, 764 s): the corpus dumped with the §2.2 code and the §2.8 sentence (appended only where a PRV has status `active`), against V's "before":

| Result | Value |
|---|---|
| Exact mode, no ignores | 1,956 identical (every project with no active-status PRV), 2,164 different (every project with one) |
| `trace.methods.sections.0.items.2` | equal to 1.1.0's item plus the sentence in all 2,164, unchanged in the other 1,956 |
| With item 2 masked, against J's dump without the sentence | all 4,120 identical: the sentence changes nothing else, and the run reproduces J's |
| Exact mode with the §2.7 ignores (`methodVersion`, `trace.methods.methodVersion`, `convergence.*`, items 4 and 2) | 3,617 identical, 503 different: 421 of the 924 projects of J's comparison differ only in iteration counts; the 503 are the numeric differences that the within-tolerance mode judges (largest relative ones at round-off flows, such as fuzz_215 and fuzzfc_10272, which `ZERO_FLOW_RTOL` excludes) |

### 2.5 Measured on the differential fuzz

*Measured* (J, `fuzz_judge.py`; before = V's runs of today's code).

**Default profile, seeds 0–2,999:**
- 0 critical.
- One record changes: seed 1656 goes from pass to documented (FCV1 and FCV3 open → closed), the corpus change above. Its self-check stays empty.
- Class table after: pass 1,856, documented 536; every other class as in TSD §10.4.

**flow_control profile, seeds 10,000–12,999:**
- 0 critical; the 4 not converged are unchanged (equal flow setpoints in series).
- One record changes: seed 11,194 goes from b_stagnant_heads to pass. A zero-flow section that was held with PRV2 closed, PU7 at maximum speed, CV4 closed, CV5 open and FCV1 open is now reported isolated. Its flows agree with EPANET's in both runs, as V found; only that section's heads differed.
- Class table after: pass 1,765, b_stagnant_heads 85; every other class as in TSD §10.4.

**For comparison** (V, PRV and PSV variant):
- Default: seeds 1446 (documented → pass) and 1656 (pass → documented) swap classes, and both states of each pass the self-check.
- flow_control: seed 11,194 goes from b_stagnant_heads to pass.

### 2.6 Measured on the test suites

*Measured* (J, `judgeplugin.py`, which applies the change before collection; `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`). The run used a clean copy of `f9d402b` (`git archive` into the scratch directory, with its own `uv sync`), because the repository's working tree was changing under the session of §1.4. All 2,979 tests of the API suite passed in 167 s, including the reference suite, the unit tests and the EPANET smoke tests of both fuzz profiles with their pinned classes.

In the same copy, J re-ran `j1` and `j5` with identical output.

For comparison: C's PRV-form variant with "slope > 0" passed all 2,979 tests, including the EPANET smoke tests and their pinned classes. E's PRV and PSV variant passed `tests/reference` and `tests/unit` (2,829) and the fuzz smoke test (81).

### 2.7 Acceptance criteria for the build (stated before it runs)

**C0 adds `tests/differential/compare.py --within-tolerance`** (V), and `corpus.py --solver-options` for criterion 7 (R). The exact mode stays the default.

**Compared exactly:**
- strings, after masking the numbers inside them: statuses, states, flag codes, element ids and trace structure;
- booleans and list lengths, such as `converged` and system-curve point counts.

**Numbers, by key:**

| Quantity | Tolerance |
|---|---|
| Flows (`flow`, `outflow`, `portFlows.*`, `portOutflows.*`, `operatingFlow`, system-curve `flow`) | 10⁻⁸ × the project's largest \|flow\| + 10⁻¹⁴ m³/s |
| EGL, HGL, heads, head losses, head rises, NPSH | 10⁻⁶ m |
| Pressures | ρg·10⁻⁶ m |
| Speeds | 10⁻⁹ relative |
| System-curve heads | 10⁻⁸ relative or 10⁻⁶ m, whichever is looser |
| Every other number | 10⁻⁶ relative, where its element's flow exceeds 10⁻⁹ × the largest flow |

Numbers at the round-off scale of `ZERO_FLOW_RTOL` are excluded and counted.

**Ignored by path** (compare.py's `--ignore`, whole paths at their depth; the same list in the §9.9 command, RVG-2):
- `methodVersion` and `trace.methods.methodVersion`;
- `convergence.*` (innerIterations, outerIterations, message, the residuals, oscillatingComponents);
- `trace.methods.sections.0.items.4`, the methods item "This solve: …" (iteration counts);
- `trace.methods.sections.0.items.2`, the Network-solution item that gains the C1 sentence. It is checked exactly instead, by criterion 2.

**Where the thresholds come from** (revised, PN8 and RVG-3: an earlier draft derived the flow tolerance from a cold-start bound, ρ ≤ 0.81 within 100 iterations, which does not hold: every inner solve after the first is warm-started from the previous flows, `status.py:1656-1662` with `flows` from `status.py:1761, 1801, 1809, 1827, 1833, 1854`, so a slowly contracting lag can meet the stop test after a few iterations; and users may set up to 1,000 iterations and a tolerance up to 10⁻³, `models/project.py:42-50`):
- **Flows, empirical.** Two measured terms. (i) The final-state lag error: the corpus's active PRVs with forward flow have r ≥ 2.358, so at most 0.74 times the last flow step (§2.4, PN). (ii) Iteration-path differences from warm starts: at most 7.73·10⁻¹⁰ of the largest flow (fuzzfc_10339, no active PRV at convergence). The threshold 10⁻⁸ lies 13× outside the measured worst. These hold for the corpus's settings only: every corpus project uses tolerance 10⁻⁹ and 100 iterations (stated in all 94 reference cases and the 9 unit-data networks; the fuzz generator sets the tolerance, `generator.py:123`, and leaves the default 100 iterations).
- **Heads.** 10 × `ENERGY_TOL`; the measured worst lies 35× inside (EGL and pressure).
- **The fixed point** is proven separately, by criterion 7 at a tight tolerance, not by these thresholds.

**Criteria** (stated before the build runs; the build re-runs them on the HEAD it commits on, §1.4 item 4):
1. Every project with **no PRV whose status is `active`** is identical in exact mode, the methods summary included (1,956 projects measured, §2.4). A PRV that ends open or closed may have been ACTIVE at an iterate, so every project with an active-status PRV, whatever its final state, comes under criterion 3 (RVG-1).
2. **Methods.** `trace.methods.sections.0.items.2` equals 1.1.0's item, one space and the §2.8 sentence, byte for byte, in exactly the projects with a PRV whose status is `active`, and is unchanged in every other project. No other methods item changes but "This solve".
3. Every other value of the projects with an active-status PRV is within the tolerances above.
4. A state may change only where the element carries at most Qtol on both sides, with every flow and head present on both sides within the tolerances.
5. A converged flag or a system-curve point count may change only from not converged to converged.
6. Each project under criteria 4 or 5 is named, both of its states are run through the independent self-check, and it is recorded in TSD §10.4. *Measured:* fuzz_1656 and fuzz_2197.
7. **The fixed point** (RVG-3). Both trees dump the whole corpus, system curves included, with every project's solver options overridden to tolerance 10⁻¹³ and `max_iterations` 1000. Every project converged in both trees agrees within 10⁻¹¹ × its largest flow in flows, 10⁻⁸ m or 10⁻¹¹ relative (whichever is looser) in heads, the same in pressures as heads of ρg, and 10⁻¹¹ relative in speeds, with states as in criterion 4. (The relative term matters only for system-curve points with very large heads, such as fuzz_2745's 1.49·10⁸ m, where one unit in the last place is 3·10⁻⁸ m.) A project that converges in neither tree, or in only one, or that stalls at the `ENERGY_TOL` floor, is listed by name with its reason, never dropped; one that converges at 1.2.0 only is a criterion-5 change. These thresholds were set by R from the preliminary measurement of §2.4 on `f9d402b` (main solves of the 2,164 active-status-PRV projects: worst 8.42·10⁻¹³ in flow, 6.92·10⁻¹⁰ m in head, speeds identical, one project, fuzzfc_10070, not converged in either by design), with a margin of at least 12×; they are stated now, before the build's run.
8. **Fuzz.** Both profiles are re-run in full, with 0 critical. Every changed class is listed with its self-check, and smoke-test pins are updated only for reviewed seeds. Seed 1656 lies outside every smoke range (0–49, 10,000–10,024, 11,738, 12,703, 12,773).

Owner question Q5 approves these criteria.

### 2.8 Versions and texts

**`version.py`:** METHOD_VERSION "1.2.0". Changelog entry:

> The setpoint head of an active PRV includes the velocity head in the pipe at its outlet port. Its flow derivative now enters Newton's step exactly wherever the outlet pipe's own loss rises with flow faster than that velocity head by at least 10⁻⁶ of its rate (before, it was taken from the previous iteration). An active PRV whose outlet connection itself loses more than one velocity head (an exit fitting in that connection, into a tank) now converges in a few iterations, where it took up to 100 or did not converge. Both iterations have the same fixed point (corpus at a tolerance of 10⁻¹³: flows within 8.4·10⁻¹³ of each project's largest flow). Converged results agree with 1.1.0 within the convergence error of 1.1.0's lagged iteration: with default solver settings, the corpus of 4,120 projects differs by at most 7.7·10⁻¹⁰ of each project's largest flow and 2.9·10⁻⁸ m in heads, and system-curve heads by at most 2.6·10⁻¹¹ relative; a project with more iterations or a looser tolerance may differ more (measured up to 6·10⁻⁸ of the flow at 1,000 iterations). A solve or a system-curve point that did not converge may now converge (one pump in the corpus gained 4 curve points with heads), and a network with more than one valid zero-flow state may reach another of them (one in the corpus).

The wording is revised from the first draft (RVG-3, RVG-20, PN3): "within the solver's convergence tolerance" was not true for projects with more iterations or a looser tolerance (*measured*, RVG `rv10_lag_error.py`: |ΔQ|/Q 5.40–5.94·10⁻⁸ for a 0.1 m spool at 1,000 iterations, every lagged solve converged); "heads within 2.9·10⁻⁸ m" left out a system-curve head change of 3.9·10⁻³ m on a 1.49·10⁸ m point (fuzz_2745); "a short pipe with an exit loss" is narrowed to the outlet connection's own loss, since an exit beyond an ideal tee keeps the lag (§2.3).

**`methods.py`:**
- One sentence, only when the project has a PRV whose status is `active` (the set criterion 1 of §2.7 keeps bit-identical), so that every other project keeps a byte-identical summary.
- It is appended, after one space, to the Network-solution item at `methods.py:189-191` (`trace.methods.sections.0.items.2` in a corpus dump), which is unconditional today. It states the code's condition, which is local to the outlet pipe (r_ref), and what the iteration then does (r_tot) (RVG-10):

  > Where an active PRV holds its outlet, the velocity head in its setpoint head enters Newton's step with its flow derivative when the outlet pipe's own loss (with any branch path in series at its far end) rises with flow faster than that velocity head by at least 1e-06 of its own rate; otherwise it is taken from the previous iteration, which converges only where the network beyond the port loses more than one velocity head, and slowly near one.

  The number is printed from `JACOBIAN_FLOOR_RELATIVE` with `:g`, as the item before it prints its constants.
- `test_methods.py` pins the sentence byte for byte, its presence on a project with an active-status PRV, and its absence on one whose PRVs are all failed open or closed and on one with only a PSV.
- C2 extends the condition to "a PRV whose status is `active`, or a discharge-pressure pump that is on", and the subject to "an active PRV or a regulating discharge-pressure pump".

**`gga.py`:** the module docstring (`gga.py:49-56`) and the comment at `gga.py:799-801`. That comment says "a PRV: converges exactly when its setpoint is feasible", which §2.1 shows is not true within 100 iterations.

**No trace change.** The equations of the converged state are unchanged.

**Docs:**
- TSD §5.2 "Held nodes", the §5.3 table row and §10.4 (criteria, commands, results).
- CLAUDE.md D10: "PRV/PSV flows are coupled exactly in the Newton step (no lag)" gains "and an active PRV's velocity-head term where the outlet pipe's own loss rises with flow faster than that velocity head by at least 10⁻⁶ of its rate (`JACOBIAN_FLOOR_RELATIVE`); elsewhere it is lagged" (RVG-10).

### 2.9 Tests of C1

**Reference cases** (`tests/reference/derivations_velocity_head.py`, written by the reference author):
- Network: R1 → line → ideal PRV → spool L with an exit fitting → R2.
- Q is the root of z + p_set/(ρg) + cQ² − H_R2 = h_spool(Q), by `brentq` on `line.Line`, Darcy–Weisbach plus `exit_normal()`.
- Upstream EGLs come from the line laws, and the active rule clears `STATE_MARGIN` (`element_laws.py:332`).

| Case | Outlet | r | Expected |
|---|---|---|---|
| VH1 | 0.5 m + exit | ≈ 1.09 | Fails today (not converged, *measured*); passes with C1 in 6–8 iterations |
| VH2 | 1 m + exit | ≈ 1.2 | As VH1 |
| VH3 | 0.05 m + exit | ≈ 1.01 | As VH1 |
| VH4 | 5 m + exit | ≈ 1.9 | Converges today and with C1, same state |
| VH5 | no exit; setpoint above R2's static head | < 1 | PRV open, the unique valid state (*measured*, V; RVG `rv7_vh5_states.py`: closed goes to active, only open is valid). The derivation enumerates closed, active and open and shows the two others fail by `STATE_MARGIN`. |
| VH6 | 1 m spool, no exit; setpoint head V = 2.5 m (p_set 24,467.6 Pa), below the open state's outlet static head P_open by at least `STATE_MARGIN` | < 1 | PRV closed, the unique valid state |
| VH7 | 0.3 m spool without fittings → ideal tee (branch to a plug) → 0.3 m with an exit → R2 | r_ref < 1, r_tot ≈ 1.11 | Documented limitation (§2.3): a unit test, not a case file. At the default 100 iterations: not converged, today and with C1. With `max_iterations` 300: converged active, at the closed-form flow, which the test derives with `line.Line` (*measured*, R `m6_tee_300.py` with C1, which applies no exact term here: 169–182 inner iterations in 1 outer iteration; the (0.5, 0.5) m variant 108–113) |

**VH6's derivation** (PN4, RVG-5). As written before the review ("setpoint below R2's static head"), VH6 had three rule-valid states. Its inputs are now chosen so that CLOSED is unique, and the derivation proves it with reference laws only:
- P_open, the outlet static head with the PRV open, from the line laws (brentq on H_R1 − H_R2 = h_L1(Q) + h_L2(Q), then H_R2 + h_L2(Q_open) − c·Q_open²); require V ≤ P_open − `STATE_MARGIN`, so that OPEN fails X1 ("H2 ≥ Hset + Htol").
- Every forward root of H_R2 + h_L2(Q) = V + cQ² is enumerated; at each, the active rule gives OPEN (H1 − hml < Hset − margin).
- CLOSED holds: H2 = H_R2 > V + margin.
- *Measured* (R, `m3_vh6_unique.py`, reference laws and `checks.rule_prv`; then the solver): with L = 1 m and V = 2.5 m, P_open = 2.7586 m (P_open − V = 0.2586 m); the open state's rule gives active, the only forward active root (Q 0.063004 m³/s) gives open, and closed is the one valid state. The solver ends closed in 2 outer iterations (14 inner), today and with C1. The same holds for (5 m, 4.0 m), (5 m, 4.5 m) and (0.1 m, 2.0 m).

**Unit tests** (`tests/unit/test_gga.py`):
- VH1–VH3 converge within 15 Newton iterations (*measured*: 6–8).
- The errors decrease quadratically on VH1.
- The selection at combined = 10⁻⁶·slope ± ε.
- A PSV with forward or reverse flow is bit-identical to today.
- The no-exit line keeps the lag.
- VH7 (§2.9 table): not converged at 100 iterations, and converged active at the closed-form flow with 300.
- Two held heads on one pipe give the same step in either `held_reference` order.

### 2.10 Corrections to proposal §4.10

1. **Line references.** The lag is at `gga.py:795-805`, not 787-793. The PRV-class condition is at `status.py:464`, not 370.
2. **"A 1 m spool … about 110 iterations."** *Measured* 98 at Q = 0.03 m³/s (E), and 108–113 at 1–3 m/s (V). So the default solve of a 1 m spool fails or only just succeeds, and spools of 0.5 m and less fail in every measured network (E, V, J).
3. **"For r ≤ 1 the solve ends not converged."** Not what happens.
   - A PRV converges to one of its rule-valid states, which with r < 1 are often several: closed, open, and active at an unstable forward root (§2.3; E, V, PN, RVG).
   - For a pressure pump, the rules admit valid limit states, sometimes two at once (§5.10).
4. **"One side known: S_eff = clip(H_set0 − H_s, S_min, S_max)."** This is exact only when the suction head is known. With only the discharge head known, the bound is H_s ≤ H_d − F(σ0(H_d), 0) (§5.7, E).
5. **"Both sides in sections: the convex bound."** Replaced by the exact union (§5.7). C measured the convex bound re-opening spuriously, and "no constraint" converging to a wrong all-closed state.
6. **"A discharge pump with a port in a floating section ends not converged unless it is closed at every level."** This holds for a pump with both ports in one floating section. A closed pump beside one keeps v1's existence semantics (§5.8).
7. **Missing from the sketch:**
   - the starved rule's target (§5.4, P0);
   - over-control at a pressure setpoint (§5.9);
   - the falling-static-pressure multiplicity and the other second states (§5.10);
   - parallel pressure pumps (§5.11);
   - the slow lag where the outlet pipe alone loses at most one velocity head (§2.3).

---

## 3. User-facing semantics

### 3.1 Setpoint

**p_set** is the gauge static pressure held at the pump's discharge port, in Pa.
- "Static" means with the velocity of the end segment of the pipe connected at that port. This is the D9 PRV convention (`models/components.py:272-286`); every tool surveyed uses static pressure (`vfd-industry-conventions.md` §7.3).
- The **bounds** are those of a PRV setpoint, −10⁵ ≤ p_set ≤ 10⁸ Pa (`GaugePressure`, `models/base.py:45-52`).
- A setpoint below the suction pressure, or one that is unreachable, is valid input: it gives a limit state, flagged.

### 3.2 States

| `control.state` | Solver status | `PumpResult.status` | Speed reported | Meaning |
|---|---|---|---|---|
| `active` | ACTIVE | running | s*, solved at the solved flow | Holds p_set at the port. This includes running at zero flow against a dead end (a plug or a closed isolation valve). |
| `max_speed` | OPEN | running | s_max | The port pressure is below p_set even at s_max. It runs as the fixed-speed pump at `speed` (Bentley "Fixed Speed Override", proposal §2.4). |
| `min_speed` | MIN_SPEED | running | s_min | The port pressure is above p_set even at s_min. It runs at s_min with no sleep (standing answer). |
| `no_flow` | CLOSED | no_flow | σ0, the speed its drive takes at zero flow (§5.4) | The integral check holds zero flow. |
| `off` | CLOSED, fixed | off | `speed` | The control is not applied. |

No new solver statuses are needed (`status.py:99-106`).

### 3.3 Flags

- **`PUMP_SETPOINT_NOT_MET`** (info, unchanged code). Raised at max_speed, min_speed or no_flow when |EGL_d − H_set(Q_d)| > Htol. Its pressure-mode messages (the values are illustrative):
  - max_speed: "runs at its maximum speed 0.9 and holds 3.12 bar(g) at its discharge, below its setpoint 3.5 bar(g)";
  - min_speed: "… its minimum speed 0.5, and its discharge is at 2.78 bar(g), above its setpoint";
  - no_flow, by cause: "the pressure beyond it is at or above its setpoint, so its drive is at its minimum speed, whose shutoff head (10 m) the head across it (20 m) exceeds"; or "the head across it (52.1 m) exceeds its shutoff head at its maximum speed (45 m)"; or "its discharge (suction) is closed off …".
- **`PUMP_FLOW_REVERSAL`** (invalid) for no_flow, as in v1 and slice 1, with σ0 in the text. Whether a pump that is "satisfied" at s_min keeps it is owner question Q4.
- **`PUMP_OUTSIDE_CURVE`**, NPSH and cavitation flags at the speed it runs at, as today.
- **`NOT_CONVERGED`** with a message naming the pump, for each guard of §5.8–§5.11.

### 3.4 Results

- **`PumpResult.speed`** is the speed the pump runs at. Curve, range, efficiency η₀(Q/s), NPSHr and power are all at that speed (slice 1).
- **`PumpResult.control`:**
  - `mode`: "discharge_pressure";
  - `setpoint`: Pa gauge;
  - `state`;
  - `setpointAchieved` = |EGL_d − H_set(Q_d)| ≤ Htol (None when off).
- **The achieved pressure** is already reported as `nodeResults["<pump>:discharge"].pressure`, the static gauge pressure with the connected pipe's velocity (`models/results.py:64-77`; `results.py:225-249`). So **no new result field** is added, and flow-mode results keep their exact JSON (resolution R9).

---

## 4. Model and schema

### 4.1 API models (`models/components.py`)

```python
class FlowControl(CamelModel):                       # today's PumpControl (186-205), renamed
    mode: Literal["flow"] = Field(description="flow: hold the volumetric flow through the pump")
    setpoint: float = Field(gt=0, le=FCV_SETPOINT_RANGE[1],
        description="Flow through the pump, suction -> discharge, m³/s")
    min_speed: float = Field(gt=0, lt=1.0, description=MIN_SPEED_TEXT)

class DischargePressureControl(CamelModel):
    mode: Literal["discharge_pressure"] = Field(
        description="discharge_pressure: hold the static pressure at the pump's discharge port")
    setpoint: GaugePressure = Field(
        description="Gauge static pressure held at the pump's discharge port (velocity in the "
                    "connected pipe), Pa")
    min_speed: float = Field(gt=0, lt=1.0, description=MIN_SPEED_TEXT)

PumpControl = Annotated[FlowControl | DischargePressureControl, Field(discriminator="mode")]
```

**Why a discriminated union** (all three designs):
- Each member's bounds are plain JSON Schema: a flow bound exclusive at 0, a gauge-pressure bound. So no `x-setpoint-bounds` entry is needed.
- The generated TypeScript types are exact.
- Slice-1 bodies (`{mode: "flow", setpoint, minSpeed}`) validate unchanged.

**Published rules:**
- `Pump.ORDERED_FIELDS` (`components.py:214`) and `x-ordered-fields` are unchanged. The path `control.minSpeed` exists in both members, so `Pump._check_speed_limits` (`components.py:233-239`) and the web reader (`utils/model-rules.ts`) apply to both.
- `test_schema_rules.py` gains one instance per mode. Its openapi copy check stays green after `pnpm gen:types`.

### 4.2 Results (`models/results.py:119-136`)

- `PumpControlResult.mode` becomes `Literal["flow", "discharge_pressure"]`.
- The `setpoint` description becomes "m³/s through the pump (flow), or Pa gauge static at the discharge port (discharge_pressure)".
- The `state` description gains the pressure meanings, including that no_flow can be at s_min.
- No new field.

### 4.3 Topology issue

`PRESSURE_CONTROL_ZONE` (422) is added only if the owner chooses Q1(a) (§5.11). It goes in `validate_topology` (`builder.py:227`), next to `CONTROLLED_PUMP_CURVE` (`builder.py:274-296`). That issue already applies to every controlled pump, of either mode.

### 4.4 Validation and privacy

A bad pressure setpoint is a 400 `VALIDATION_ERROR` that echoes no value (D10). A test covers it.

### 4.5 schemaVersion (the proposal §3.5 rule, decided by the deployment fact at merge time)

**If no build has been deployed or tagged when C2 merges:** schemaVersion stays 1. No released app can meet a link with the new mode. CLAUDE.md D12 says so, as D11 does.

**Otherwise it becomes 2:**
- `MIGRATIONS[1] = (p) => p` in `apps/web/src/lib/utils/migrations.ts:21`, and `CURRENT_SCHEMA_VERSION = 2` (`migrations.ts:12`);
- `SCHEMA_VERSION = 2` (`models/project.py:13`), and `schema_version: Literal[1, 2]` (`project.py:80`), so v1 bodies sent to the API still validate while the migration is the identity;
- new `schema-v2.txt` and `schema-v2.json` fixtures with one flow-controlled and one pressure-controlled pump, leaving the v1 fixtures untouched;
- `test_released_links.py` and `tests/examples.e2e.ts` solve both.

The reviewer checks the fact with `git tag` (empty at `f9d402b`) and the deployment record of TSD §11.

C1 changes no model, so it does not touch schemaVersion.

### 4.6 METHOD_VERSION

These numbers assume that 1.1.0 is still current when C1 merges (§1.4).
- C1 is 1.2.0 (§2.8).
- C2 is 1.3.0, with this changelog entry:

  > Adds speed-controlled pumps holding a discharge pressure: the static pressure at the pump's discharge port is held in the network solve, as a PRV holds its outlet, and the speed recovered from the affinity laws, within a minimum and maximum speed. Results of projects without discharge-pressure control are unchanged (corpus comparison).

---

## 5. Solver formulation and status rules

### 5.1 Notation

- **Pump link k** runs from suction s to discharge d (`builder.py:602-616`). Q is its flow; Q > 0 is forward.
- **H** = EGL_d − EGL_s. In free-level sections it is the section shifts (`closed_off_sections`, `status.py:526-570`).
- **F(σ, Q)** = σ²H₀(Q/σ) (`PumpCurveModel.head`, `pumps.py:133-136`).
- **Speeds:** s_max = `speed` and s_min = `control.minSpeed`. **Shutoff heads:** S_max = F(s_max, 0) and S_min = F(s_min, 0).
- **s_lo(Q)** = `bracket_low(Q, s_min, s_max, x_mono)` (`pumps.py:260-266`): max(s_min, Q/x_mono), at most s_max. It is s_min for Q ≤ 0.
- **z_d** is the elevation of the discharge port node: the port's own elevation if set, else the component's (`port_elevation`, `builder.py:72-75`).
- **H_set0** = z_d + p_set/(ρg).
- **c_d** = 1/(2gA_d²), where A_d is the area of the end segment at the port of the discharge connection (`BuiltNetwork.port_pipe`, `builder.py:190-195`; `PortPipe.velocity_head_coefficient`, `builder.py:97-100`).
- **Q_d** is that connection's flow out of the port. It equals Q, because a port has one connection.
- **H_set(Q_d)** = H_set0 + c_d·Q_d² (`LinkState.head`). The port's static head is P_d = EGL_d − c_d·Q_d², so EGL_d ≥ H_set(Q_d) + Htol ⟺ P_d ≥ H_set0 + Htol.
- **Regulation ratio r** = k_down/(2c_dQ_d), where k_down = dEGL_d/dQ_d is the response of the network beyond the port with every other element in its state. Then dP_d/dQ_d = 2c_dQ_d(r − 1): the static pressure at the port rises with the flow iff r > 1.
- **Tolerances:** Htol = 10⁻⁴ m and Qtol = 10⁻⁸ m³/s (`status.py:89-92`). The status rules add no new tolerance. §5.10 states its one numerical choice.

### 5.2 Inner-solve law of each state

| Status | `LinkState` | Equation | GGA path |
|---|---|---|---|
| ACTIVE | `FIXED_DOWNSTREAM_HEAD`, `value` = H_set0, `reference_link` = discharge connection's link, `coefficient` = c_d (new `pump_active_state`, mirroring `active_state`, `status.py:347-364`; built once in `PressureControlData`) | EGL_d = H_set(Q_d); no energy row of its own | Held node d (`_held_node`, `gga.py:318-319`). Supply side [s] (`_supply_side`, `gga.py:322-326`): the suction part must reach a fixed or held head, else the link is starved. Flow = −(net inflow at d) (`special_flows`, `gga.py:661-676`). The m21 coupling is exact (`gga.py:645-659`). The velocity term is exact by C1. |
| OPEN | `NORMAL`, the link's own `PumpLaw(curve, s_max)` | h = −F(s_max, Q) | As a fixed pump at `speed`, bit-identical |
| MIN_SPEED | `LinkState(NORMAL, law=min_law)` | h = −F(s_min, Q) | Slice-1 override, read through `law_of` (`network.py:121-123`) |
| CLOSED | `CLOSED` | Q = 0 | — |
| Forced (system curve) | `FIXED_FLOW(q)`, written last | — | Unchanged (`status.py:394-395`) |

**The GGA invariants hold:**
- d is a free node held by one link (`gga.py:456-459`).
- d's only other link is its connection, a pipe, never a head offset (`gga.py:596-597`).
- Two controls never hold one node, because each holds its own port.

*Measured* (C, `p17_orient.py`, rule set C): the discharge connection drawn toward the pump or away from it gives the same answer (s* 0.968154; 8 and 7 iterations).

### 5.3 Exactness and speed recovery

**Exactness.** Take s as an extra unknown. The pump then adds two rows:
- its head row e_k = (EGL_d − EGL_s) − s²H₀(Q/s);
- the setpoint row g = EGL_d − H_set(Q_d).

s appears only in e_k, with ∂e_k/∂s = −s·ψ(Q/s), where ψ(x) = 2H₀(x) − xH₀′(x) > 0 on [s_lo(Q), s_max] by the ψ test (`pumps.speed_uniqueness`, `pumps.py:212-257`; `CONTROLLED_PUMP_CURVE`, `builder.py:274-296`, for both modes).

With columns (Q, H | s), the Jacobian is [[J_red, 0], [∂e_k/∂(Q, H), −sψ]]. J_red is the network with g in place of the pump's head row: exactly the held-node (PRV-form) solve. So:
- the converged flows and heads are those of the simultaneous solve;
- an ACTIVE inner solve never evaluates the curve;
- s* follows from e_k = 0.

This is Elhay et al. (2025)'s "PRV whose loss is non-positive" (`vfd-industry-conventions.md` §6).

**Speed.** s* = `operating_speed(curve, Q, H, s_min, s_max, x_mono)` (`pumps.py:283-322`), called with the **solved** flow Q where flow mode passes Q_set:
- Ĥ = clamp(H, F(s_lo(Q), Q), F(s_max, Q)). The clamp moves H by at most Htol, because rules P2 and P3 (§5.4) held at the same Q and H.
- Brent's method runs with xtol 10⁻¹⁴ and rtol 4ε.
- The trace reports the residual F(s*, Q) − H.

**At Q = 0** (a dead end), s* = √(Ĥ/H₀(0)). H₀(0) > 0 because the ψ test requires ψ(0) = 2H₀(0) > 0.

**For −Qtol ≤ Q < 0**, x = Q/s lies on the start tangent, where ψ = 2h₀ + m₀x ≈ 2H₀(0) > 0, so the root stays unique.

**Closed-form oracle** for a straight curve H₀ = a − bx: s* = [bQ + √(b²Q² + 4aH)]/(2a).

*Measured* checks of the recovery:

| Who | Script | Check | Result |
|---|---|---|---|
| C | `p1_line.py` | s* against the closed form | 0.935822 against 0.9358224409 |
| C | `p1_line.py` | dead-end speed against √((H_set0 − H_s)/H₀(0)) | 0.800824 against 0.8008244498 |
| E | `exp11` | s* against the independent affinity-parabola route, 12 active cases | within 1.5·10⁻¹² relative |

### 5.4 Status rules (the first test that holds wins)

| From | Rule | Test | To | Source / reason |
|---|---|---|---|---|
| ACTIVE | P0 | The GGA starves the link (`GgaResult.starved_links`: the suction part reaches no fixed or held head) | MIN_SPEED if EGL_d is finite and EGL_d ≥ H_set0 + Htol; else OPEN | A drive that sees its port above the setpoint runs down, else up. See the threshold note below. |
| ACTIVE | P1 | Q < −Qtol | CLOSED | Integral check; EPANET 2.2 prvstatus ACTIVE → CLOSED (`status.py:222-223`) |
| ACTIVE | P2 | H > F(s_max, Q) + Htol | OPEN | prvstatus "H1 − hml < Hset − Htol" (`status.py:224`), with the pump at s_max as the fully open element |
| ACTIVE | P3 | H < F(s_lo(Q), Q) − Htol | MIN_SPEED | Slice-1 A2 at the solved flow; F(s_lo(Q), Q), not F(s_min, Q) (proposal §4.3) |
| ACTIVE | P4 | otherwise | ACTIVE | — |
| OPEN | X0 | `pump_status(OPEN, H, Q, S_max)` is CLOSED: H > S_max + Htol or Q < −Qtol (`status.py:132-144`) | CLOSED | EPANET 2.2 pumpstatus. Tested before X1, as prvstatus tests reverse flow first. |
| OPEN | X1 | EGL_d ≥ H_set(Q_d) + Htol | ACTIVE | prvstatus OPEN → ACTIVE "H2 ≥ Hset + Htol" (`status.py:230-231`) |
| OPEN | X2 | otherwise | OPEN | — |
| MIN_SPEED | N0 | `pump_status(OPEN, H, Q, S_min)` is CLOSED | CLOSED | v1 rule at s_min |
| MIN_SPEED | N1 | EGL_d ≤ H_set(Q_d) − Htol | ACTIVE | Mirror of X1 |
| MIN_SPEED | N2 | otherwise | MIN_SPEED | — |
| CLOSED | C1 | σ0 = s_min if EGL_d ≥ H_set0, else s_max. Re-open iff H ≤ F(σ0, 0). | MIN_SPEED if σ0 = s_min, else OPEN | With the check closed, the transmitter reads EGL_d (Q = 0, so H_set = H_set0). The drive sits at s_min when that is at or above the setpoint, and winds up to s_max otherwise. The check opens once the pump's shutoff head at that speed exceeds the head across it (v1 rule). |
| CLOSED | C2 | otherwise | CLOSED | — |

**Equivalent closed set.** The pump stays closed on R = {EGL_d ≥ H_set0 and H > S_min} ∪ {H > S_max}.

When the suction head is known, R is the single bound EGL_d ≥ H_s + S_eff, with S_eff = clip(H_set0 − H_s, S_min, S_max), modulo the boundary points. This is E's form, derived independently by C and V. E's own targets differ from C1's only when EGL_d < H_set0 and H_set0 − H_s ≤ S_min: there E re-opens to MIN_SPEED and C1 to OPEN. Both are starting points that the next solve corrects (resolution R4).

**Bands.** Each of the pairs (P2, X1) and (P3, N1) has a 2·Htol band in which both neighbours hold: EPANET's band behaviour. X0/N0 and C1 share v1's band (S, S + Htol].

**P0's threshold (resolution R3).** In the starved solve the pump is treated as closed, so EGL_d is the discharge head at Q = 0. Dead-headed at its target (OPEN or MIN_SPEED, a NORMAL link at zero flow), EGL_d is the same. So:
- OPEN keeps its state iff X1 fails ⟺ EGL_d < H_set0 + Htol;
- MIN_SPEED keeps its state iff N1 fails ⟺ EGL_d > H_set0 − Htol.

"MIN_SPEED iff EGL_d ≥ H_set0 + Htol" (E) always picks a target that keeps its state.

The alternatives fail:
- **V's slice-1 rule** (always OPEN) cycles, OPEN →X1 ACTIVE →P0 OPEN, whenever the suction is closed off and the network beyond is above the setpoint. *Measured* (C, `p15_suction_closed.py`, rule set C with P0 always OPEN): "statuses oscillate (PU)", not converged. With C's split (rule set C), which is the same as this one outside a 2·Htol band, C measured min speed dead-headed (suction 15 m) or max speed (suction −15 m), in 2 outer iterations each.
- **C's threshold** (≥ H_set0 − Htol) sends EGL_d = H_set0 − Htol exactly to MIN_SPEED, where N1 fires, giving a boundary cycle (derived).

**Order at OPEN and MIN_SPEED (resolution R5).** The closing test comes before X1 and N1 (E, V; prvstatus order). C tested X1 first, which sends a pump with reverse flow and a pressurised network to ACTIVE, where P1 then closes it: one wasted outer iteration.

**No band at C1's knee.** E derived that a +Htol band there cycles (ACTIVE →P1 CLOSED → OPEN →X1 ACTIVE for H_set0 < EGL_d ≤ H_set0 + Htol), and C1 has no band. *Measured* (E, `exp10`): with the exact coupling, E's rule set reached one final state from every start state in 72 line cases, with no cycle. E's rule set has C1's closed set, but E's re-open targets (R4). The build turns this 72-case sweep into a unit test of the rules exactly as written here (§9.7).

**Which rules the measurements ran (RVG-16).** No prototype ran this table exactly. Each measurement of a pressure pump in §5–§7 is labelled with its rule set:
- **Rule set C** (C's prototype tree `proto/`, `pressure_pump_status`): X1 before the closing test at OPEN and N1 before N0 at MIN_SPEED (R5); σ0 = s_min and P0's split at EGL_d ≥ H_set0 − Htol (R3); C1's targets via EGL_d, as here; no second-state tests. Used by every `p*` script.
- **Rule set E** (E's `exp10`/`exp11`): this table's closed set and P0 threshold, with E's re-open targets via S_eff (R4).
- **Fixed pumps only** (J `j5`, PN `r1`–`r7`): today's solver with the pump fixed at a limit speed or replaced by a PRV; no slice-2 rule is involved.

The two prototype rule sets differ from this table in transients and 2·Htol bands; in a network with several valid states the state reached can depend on the path. So every configuration whose outcome is quoted from a prototype is a C2 test (§9.7) whose expected outcome is stated there now, before the build: the final state quoted, where the configuration's derivation or `state_search` shows one valid state; otherwise membership in the enumerated valid states, or the not-converged report of the guard that applies.

**Speed reported for no_flow (σ0, resolution R6):**

| Situation | Speed | Reported EGL |
|---|---|---|
| Both heads known | σ0 by C1 | — |
| Discharge closed off (its level free) | σ_dh = √(S_eff/H₀(0)) ∈ [s_min, s_max] | EGL_d = H_s + S_eff, the lowest level that keeps the pump closed |
| Suction closed off | σ0(EGL_d) | EGL_s = EGL_d − F(σ0(EGL_d), 0), the highest level that keeps it closed |
| Both sides closed off | s_max (slice 1); no result | — |

The two one-sided rows are v1's dead-headed convention (`results.py:699-708`), generalised. The discharge rule is C's level with a speed that matches it. C reported σ0 there, which disagrees with that level when S_eff is interior.

### 5.5 Initial statuses and fallbacks

**Initial statuses** are unchanged (`initial_controls`, `status.py:310-344`):
- on: ACTIVE, not fixed;
- off: CLOSED, fixed;
- forced by a system-curve solve: OPEN, fixed.

**Dispatch.** `controlled_pump_status` (`status.py:197-210`) dispatches on mode to `flow_pump_status` (unchanged) or a new `pressure_pump_status`.

**`_check_changes`** (`status.py:1988-2034`) applies P1–P3 at the early iterate, with H_set taken at that iterate's flows. P0 does not apply there: the starved links are not known at the early iterate.

**`_open_bad_valves`** (`status.py:2037-2095`) is unchanged. It tries OPEN (maximum speed), then MIN_SPEED for options that hold a pump, then CLOSED. Valve-only networks keep the v1 option sequence (`test_valve_only_fallbacks_take_the_v1_options_in_order`).

**`_changed_together`, `_one_change` and `_backtrack`** (`status.py:1578`, `1891`, `1916`) are unchanged.

**The GGA's "loose" message** (`gga.py:543-554`) says "controls" when a pump is named: "… any flow around that loop holds its setpoint". Text that names only valves stays byte-identical, as slice 1 did for `gga.py:500`.

### 5.6 When the state is unique, and where it is not

**Uniqueness.** Assume:
- one pressure pump in passive surroundings;
- the suction EGL does not rise with Q;
- the port's static head P(Q) rises strictly along the network beyond (r > 1);
- F(σ, ·) falls with Q (no drooping);
- ψ > 0.

Let Q_M and Q_m be the operating flows at s_max and s_min. G_σ(Q) = EGL_s(Q) + F(σ, Q) − EGL_d(Q) decreases, so each limit has one operating flow, and Q_m ≤ Q_A ≤ Q_M for the regulating flow Q_A. Outside the Htol bands, exactly one state holds (C, E):

| Condition | State |
|---|---|
| H(0) > S_max and P(0) < H_set0 | CLOSED (at s_max) |
| P(Q_M) < H_set0 | OPEN |
| H(0) > S_min and P(0) ≥ H_set0 | CLOSED (at s_min) |
| P(Q_m) > H_set0 | MIN_SPEED |
| P(Q_m) ≤ H_set0 ≤ P(Q_M) | ACTIVE |

*Measured* (E, `exp10`/`exp11`):
- **Grid:** h1 ∈ {2, 25} m; h2 ∈ {5, 30, 45} m; discharge 1 m or 200 m with an exit; p_set 50–550 kPa; s ∈ [0.5, 1]; curve_a.
- **States:** ACTIVE 12, OPEN 27, MIN 11, CLOSED 22.
- **Agreement:** 0 mismatches against the partition, computed by brentq on the line, not through the GGA; flows within 3.5·10⁻¹⁵.

**Where uniqueness fails:**

1. **r ≤ 1.** The static pressure at the port falls with the flow when the network beyond recovers the discharge velocity head without a loss: an ideal tee into a larger header, a Crane run between unequal run pipes, no exit fitting at a reservoir, or a diameter change without a reducer fitting.
   - Both limit states can then satisfy every rule. *Measured* (J, `j5_header_limits.py`, today's solver, fixed pumps only; C measured the same numbers with its prototype). Network: R1 (5 m) → 10 m line, sharp entrance → pump H₀ = 40 − 500x → 1 m spool (0.1 m) → ideal tee run → 50 m of 0.3 m header with exit → R2; the branch to a plug; setpoint 2 bar.

     | R2 | At s_max = 1: flow, port static pressure | At s_min = 0.8: flow, port static pressure | Both rule-valid |
     |---|---|---|---|
     | 20.8 m | 0.041443 m³/s, 192,739.9 Pa | 0.021972 m³/s, 200,569.7 Pa | yes |
     | 21.0 m | 0.041142 m³/s, 194,855.7 Pa | 0.021563 m³/s, 202,639.5 Pa | yes |
     | 21.3 m | 0.040689 m³/s, 198,027.6 Pa | 0.020946 m³/s, 205,740.8 Pa | yes |
     | 19.0 m | 0.044132 m³/s, 173,658.7 Pa | — | only max speed (min gives 181,863.6 Pa, below the setpoint) |

   - C's prototype (rule set C) reported min_speed silently. §5.10 handles this.
   - **The partition rows are not exclusive when r < 1** (PN1). With a falling P(Q), P(Q_M) < H_set0 ≤ P(0) together with H(0) > S_min makes OPEN and CLOSED at s_min both valid, while MIN_SPEED with flow may not exist. *Measured* (PN, `r1_open_closed.py`, today's solver, fixed pumps; PN skeptic reproduced it on a clean `f9d402b` copy). The same header network, with s ∈ [0.8, 1], so S_min = 25.6 m and S_max = 40 m:

     | R2 | p_set (H_set0) | At s_max | At s_min | Closed |
     |---|---|---|---|---|
     | 31 m | 301,395.9 Pa (30.7954 m) | Q 0.025335 m³/s; port static 299,393.6 Pa, 0.204 m of head below the setpoint; H 27.3325 m; X0 and X1 fail: OPEN valid | the fixed pump gives no flow: MIN_SPEED with flow does not exist | EGL_d 31.0000 m ≥ H_set0, so σ0 = s_min; H 26.0000 m > S_min: C1 keeps it closed, valid |
     | 33 m | 321,471.2 Pa | Q 0.021977 m³/s; port static 319,970.3 Pa, below the setpoint: OPEN valid | no flow | H 28 m > S_min: closed, valid |

     *Measured* (PN, `r5_active_path.py`, an ideal PRV in the pump's place, today and with C1): the ACTIVE inner solve reaches the reverse root, Q_d = −0.014114 m³/s (R2 33 m: −0.012200 m³/s), in 8 iterations, so P1 closes the pump, C1 keeps it closed, and the solve would end converged at no_flow with `PUMP_FLOW_REVERSAL`, without §5.10's CLOSED test (V5). Had the path ended OPEN, the earlier draft's pinned MIN_SPEED solve gives Q = −0.000992 m³/s (PN `r7_pinned_min.py`), N0 fires, and OPEN would have stood. An unstable active root lies between the OPEN state and zero flow, so "no active root lies between a valid limit and an invalid one" (C) does not hold. §5.10 V3 and V5 handle this pair.
     With falling P, the only further pair is this one: (MIN_SPEED, CLOSED at s_max) and the other combinations contradict each other (PN skeptic, derived).
2. **Parallel pressure pumps on one header.** *Measured* (E, `exp12`): two identical pumps with equal setpoints on spools without fittings reach 2–3 distinct rule-valid states depending on the start: (A, A), (A, CLOSED), (CLOSED, A), or (A, OPEN), (OPEN, A). With K = 2 on each spool the state is unique from all 16 starts. *Measured* (C, `p5b_parallel.py`, rule set C), 2 m spools: a +100 Pa setpoint difference moved the split from 0.027392/0.027392 to 0.007674/0.045278 m³/s. With 20 m spools it moved by 0.5 %. §5.11 handles this. A booster beside another pressure source that is not a pressure pump (an active PRV, a fixed or flow-controlled pump) can also have two valid states, one with the booster closed; §5.10 V6 handles that (PN2).
3. **A flow control in series with a pressure pump.** *Measured* (V, `exp9`, closed form, no solver): in 4,000 random lines R1 → flow pump → pipe → pressure pump → line → R2, 4 have two valid states, always (flow pump active, pressure pump at min speed) and (flow pump at max speed, pressure pump active). §5.9 handles this.
4. **Zero-flow multiplicity**, as in v1 (D9). Behind a closed downstream check valve with the network above the setpoint, "closed" and "active at zero flow, dead-headed" both satisfy every rule. *Measured* (C, `p3_cv.py`, rule set C): the C1 targets end closed in 2 outer iterations; a maximum-speed re-open ends active at zero flow (s 0.621192) in 5. Kept, documented and pinned by `state_search` (owner question Q6). The two are one physical state (zero flow, the section between the pump and the check valve at rest; `state_search.same`, TSD §5.4) with two labels; §5.10's tests do not apply to it, because the discharge level is free.
5. **Drooping curves.** Slice 1's limitation (TSD §12 item 3) extends to this mode. *Measured* (C, `p13_misc.py`, rule set C): the curve (0, 40), (0.01, 42), (0.02, 41), (0.03, 35) at 4.5 or 4.6 bar ends not converged.
6. **Q/s_min beyond x_mono.** ACTIVE and MIN_SPEED both hold for F(s_lo(Q), Q) ≤ H < F(s_min, Q). The slice-1 band and its text carry over, including its path rule (D11): the solve starts with the pump ACTIVE, and P3 tests F(s_lo(Q), Q), so for a head in that band it does not move the pump to MIN_SPEED. *Measured* on PCF10's inputs (RVG, `rv5_pcf10_two_states.py`, reference modules only): active at Q = 0.05 m³/s, H = −2 m, s* = 0.361803; the fixed line at s_min = 0.1 runs at Q = 0.052395 m³/s, H = −1.6958 m, with its port static pressure 96,498.4 Pa, 0.2207 m of head above p_set: N0 holds and N1 fails, so MIN_SPEED is valid by more than `STATE_MARGIN` (r of the discharge line 7.41: not a velocity-head effect). This is the one documented two-state band that a case file may pin, by that path rule (§9.2). Flow mode's build-time rejection of a setpoint at or above s_max·x_mono (§1.4) has no pressure-mode analogue, since Q is solved. When the solved Q reaches s_max·x_mono, s_lo(Q) = s_max and the active band shrinks to F(s_max, Q) ± Htol; the result is flagged `PUMP_OUTSIDE_CURVE` and listed in TSD §12.

### 5.7 Free-level sections: PRV-class membership, holding regions, zero-flow bounds

**Membership.** The pump's rules compare EGL_d with a setpoint head, so they depend on a section's level. The PRV-class condition (`status.py:464`) becomes `control.kind in ("prv", "psv") or pressure_pump(control)`, with these effects:
- **Both ports in one section, not CLOSED, Q < −Qtol** → CLOSED (`status.py:465-466`). The reverse-flow rule needs no level.
- **Both ports in sections (one or two), not ACTIVE** → a levelled member (`status.py:467-473`) of `_level_changes` (`status.py:825-954`).
- **One port in a section** → it keeps its state. If it is CLOSED, `zero_flow_openings` re-tests it (below).
- **ACTIVE** cannot have its discharge in a section, because the held node grounds it. A suction in a free part means it is starved (P0).

**`_Levelled` and `_holding_regions`** (`status.py:766-822`) gain a pump row: variables x_s and x_d, the shifts, H_set(Q_d) at the solved Q_d (H_set0 in a closed-off section), S_min and S_max. A strict rule inequality is kept with Htol/2 to spare (`status.py:782-784`):

| Status | Holding region |
|---|---|
| OPEN | H_d − H_s ≤ S_max + Htol, and H_d ≤ H_set + Htol/2 |
| MIN_SPEED | H_d − H_s ≤ S_min + Htol, and H_d ≥ H_set − Htol/2 |
| CLOSED | R1 ∪ R2: R1 = {H_d ≥ H_set0, H_d − H_s ≥ S_min + Htol/2}; R2 = {H_d − H_s ≥ S_max + Htol/2} |

**`_level_changes.new_status`** (`status.py:887-921`; today the fixed-pump rule at `component.speed`, `status.py:895-900`) applies §5.4 at the levels. If the rule gives ACTIVE, the suction is on a free level and the pump cannot hold, so it takes P0's outcome at those levels instead: MIN_SPEED if EGL_d ≥ H_set0 + Htol, else OPEN. This is the analogue of a PRV that "closes if open, opens if closed" (`status.py:915-920`).

**Zero-flow bounds of a CLOSED pressure pump** (`_border_constraints`, `status.py:680-735`; today the fixed-pump edge at `status.py:712-714`), as edges x_v − x_u ≤ w via `difference`:

| Known side | Constraint | Re-open target (`zero_flow_openings`) |
|---|---|---|
| Suction known (h_s), discharge in a section | H_s − H_d ≤ −S_eff, S_eff = clip(H_set0 − h_s, S_min, S_max) | MIN_SPEED if H_set0 − h_s ≤ S_min, else OPEN |
| Discharge known (h_d), suction in a section | H_s − H_d ≤ −F(σ0(h_d), 0), σ0 = s_min if h_d ≥ H_set0, else s_max | MIN_SPEED if σ0 = s_min, else OPEN |
| Both ports in sections | No border edge (as PRVs, `status.py:719-722`); a levelled member with the CLOSED union above | `new_status` at the chosen levels |

**`zero_flow_openings`** returns, for pressure pumps, their target status. `_update_controls` sets it in place of OPEN (`status.py:513-515`). Every other element is unchanged.

**Why the exact union (resolution R7).** *Measured* (C, `p12_two_cv.py`, rule set C, with each zero-flow rule in turn). Network: R1 (5 m) → CV1 → PU → CV2 → R2 (25 m), setpoint 2 bar (20.44 m).

| Zero-flow rule | s_min 0.5 (all closed is valid) | s_min 0.8 (S_min 25.6 m > the 20 m lift: the pump must run) |
|---|---|---|
| No constraint | all closed (correct) | **all closed: wrong** |
| Convex S_max bound (E, V) | spurious re-open; ends at min speed dead-headed with CV1 closed (another valid zero-flow state), 6 outer | min speed, 0.008953 m³/s (correct) |
| **Exact union** | all closed, 2 outer | min speed, 0.008953 m³/s, 8 outer |

The union fits machinery that already exists: PRV and PSV rows are unions of regions today. It costs rows against `LEVEL_SEARCH_LIMIT` = 4,096 Bellman–Ford tests (`status.py:738`), which is risk 6.

**Closed-off (zero-flow) sections keep v1's existence semantics.** The pump keeps its state if one set of levels holds every member while the closed elements around stay closed. A pump with no heads gets no reported result (`results.py:686-699`).

### 5.8 Floating sections

A floating section has flow but no fixed head; its level is the arbitrary 0 m (`FLOATING_REFERENCE_HEAD`, `gga.py:140`). The check runs at the converged exit, next to `_over_controlled` (`status.py:1740`), for each pressure pump that is on and not forced.

**The solve is reported not converged, naming the pump, when:**
- it is OPEN or MIN_SPEED with either port in a floating section (`GgaResult.floating_sections`); or
- it is CLOSED with both ports in one floating section and H < S_max + Htol/2, so that some level would open it.

Message: "the pressure level of the section holding <PU> is not fixed by any reservoir or reference node, so the speed at which <PU> holds its discharge pressure is undetermined; add a reservoir or reference node".

**It converges** (with `UNDETERMINED_PRESSURE`, D10) when it is CLOSED with both ports in one floating section and H ≥ S_max + Htol/2: closed at every level.

**A CLOSED pump with one port beside a floating section keeps v1's existence semantics,** through the one-sided bound of §5.7 (C, V). E made this case not converged too; that would treat a pressure pump more strictly than v1 treats PRVs in the same position (resolution R8).

During the iterations, these pumps follow the §5.7 logic. Only the final state is judged, so a transiently floating state does not abort the solve.

*Measured* (C, `p6_floating.py`, rule set C), a sealed loop:
- The first solve stops at 0 iterations at the GGA's "loose" test (`gga.py:529-554`), and the fallbacks move the pump to max speed.
- Without this check the solve reported converged at max speed, with a discharge pressure on the arbitrary level.
- With it, the solve is not converged and names the pump.

### 5.9 Over-control

**At a limit with the port exactly at its setpoint.** `_over_controlled` (`status.py:2106-2166`) also takes a pressure pump at a limit (OPEN or MIN_SPEED) with |EGL_d − H_set(Q_d)| ≤ Htol:
1. It is re-tested in its ACTIVE state (`pump_active_state`), with `solve_gga(..., max_iterations=0)`.
2. If the GGA then names it and another control in `undetermined_links` (`gga.py:489-514`), the solve is not converged. The message: "… in series with nothing fixing the pressure between them, and '<PU>' holds exactly its setpoint at its limit: the speeds or throttling and that pressure are undetermined (over-controlled)".

`_over_controlled`'s setpoint lookup branches on mode, because a pressure pump's setpoint is not a flow.

*Measured* (C, `p13_misc.py`, rule set C): with an FCV upstream whose setpoint equals the flow the network beyond takes at the pump's setpoint, the solve converged with the FCV active and the pump at max speed, the discharge at exactly 250,000.0 Pa (±0.0002 Pa for ±10⁻⁹ relative changes). The speed is silently arbitrary there.

**Flow control in series with a pressure pump** (the multiplicity of §5.6 item 3; owner question Q3, recommended (b)):
- **Trigger.** At the converged exit, a pressure pump P and a flow control F are in series with nothing fixing the pressure between them. F is a flow pump that is on and not forced, or an FCV that is not fixed. "In series" means that with both in their active states, `solve_gga(..., max_iterations=0)` names both in `undetermined_links`. One of them is ACTIVE and the other at a limit.
- **Test.** Solve the swapped state: `run_outer_loop` with the element at its limit pinned to {ACTIVE} (`pinned`, §5.10), and the other starting at the limit its rule gives.
- **Outcome.** If that solve converges and is a second state by §5.10's definition (every element's unrestricted rules keep its final status, the pinned element's being A1/A2, the FCV's ACTIVE rule, or P0–P3; and the flowing state differs), two states hold and the solve is not converged, naming both and describing both states. Otherwise the converged state stands.
- **Cost.** One pinned outer solve, only in this configuration.

**`_equal_setpoints_note`** (`status.py:2169-2215`) keeps pressure pumps out of its equal-flow test, since their setpoint is a pressure. Valve-only and flow-only messages stay byte-identical.

*Measured* series and parallel combinations (C, `p4_series.py`, `p17_orient.py`, `p13_misc.py`; rule set C, without the swap test). Each row is a C2 test (§9.7): its expected outcome is the one in the table where `state_search` finds one valid state, else the swap test's not-converged report or membership in the valid states found:

| Configuration | Result |
|---|---|
| FCV 0.015 m³/s upstream | FCV active, pump at max |
| FCV 0.04 m³/s upstream | FCV open, pump active (s 0.95279) |
| Flow pump 0.015 m³/s upstream | flow pump at min, pressure pump active |
| Flow pump 0.04 m³/s upstream | flow pump at max, pressure pump at min |
| Two pressure pumps in series, 1.2 / 2.5 bar | both active (s 0.6757 and 0.7892) |
| Two pressure pumps in series, equal setpoints | upstream active, downstream at min |
| Pump → PRV at 1 bar | both active |
| Pump → PRV at 4 bar | PRV open, pump at max |
| PRV at 1 bar → pump | PRV active, pump at max |
| PRV at 5 bar → pump | PRV open, pump at min |
| PSV at 1 or 2.5 bar upstream | PSV active, pump at max |

### 5.10 Second-state tests (rule V and its pinned solves)

This applies if the owner chooses Q2(a). The section was revised after the review (PN1, PN2, PN6): the first draft compared only the two running limits, ran only for a pump with Q_d > Qtol, and so missed a closed alternative (PN1) and a second pressure source on the same header (PN2).

**Why.** With r ≤ 1, raising the speed lowers the port pressure:
- a drive holding the setpoint there is unstable (a normally acting controller runs to a limit);
- by continuity of a falling P(Q), the limit states on both sides of the unstable root satisfy their rules: at maximum speed, and at minimum speed with or without flow (§5.6 item 1).

A booster beside another pressure source can also have two states with r > 1 at the booster, one with it closed (PN2, below). Reporting either state as "the" answer is a choice the inputs do not make (GOALS §3).

**What the iteration already does.** For a single held node, C1's lag makes an unstable forward active root repelling (§2.3), so the active iteration cannot converge there. *Measured* (C, rule set C): in the header case of §5.6 the pinned active solve converged to a reverse root (Q −0.0189 to −0.0292 m³/s); PN measured the same on R2 31 and 33 m (§5.6 item 1). But the limit-state ambiguity remains, the closed alternative too, and symmetric multi-held-node layouts can still converge to an unstable active state (E, `exp12`).

**When the tests run.** At the converged exit, after §5.8 and §5.9, for each pressure pump that is on and not forced. A pinned solve (below) skips these tests and §5.9's swap test, so there is no recursion.

**Pinned solves.** A new argument `pinned: Mapping[str, frozenset[Status]] | None` to `run_outer_loop` (`status.py:1586`), beside `forced_flows`, which §5.9's swap test also uses:
- a pinned control starts at the set's first status, and a rule that would move it out of the set leaves it where it is; every other element follows its rules;
- a converged pinned solve is a **second state** only when (i) every element's unrestricted rules keep its final status (§5.4 for the pinned pump, with σ0 by C1), and (ii) it differs from the converged state in flowing state: a flow or a head where there is flow differs by more than D6's tolerances (the criterion of `state_search.same`). A pinned solve that differs only in labels at zero flow, with the section beyond at rest, is one physical state (§5.6 item 4) and is not a second state;
- a second state → the solve is **not converged** ("two steady states", naming the pump, the element states and flows of both, and the test that found it). Otherwise the converged state stands, and the trace notes the test and its outcome (the state reached, or the rule that failed).

**The tests:**

| Test | Applies to | Pinned solve | Reason |
|---|---|---|---|
| **V1, regulation ratio** | running (ACTIVE, OPEN or MIN_SPEED) with Q_d > Qtol and both port heads known | none: two perturbed inner solves (below) give r | — |
| **V2** | ACTIVE with r ≤ 1 | none: not converged | the regulating state is unstable |
| **V3** | OPEN with r ≤ 1 | {MIN_SPEED, CLOSED}, from MIN_SPEED: the pump's s_min branch, where N0 moves it to CLOSED and C1, with σ0 = s_min, back | the other side of the unstable root is at s_min, running or held at no flow (PN1) |
| **V4** | MIN_SPEED with r ≤ 1 | {OPEN} | with a falling P, CLOSED at s_max cannot also hold beside a valid MIN_SPEED (σ0 would be s_min; PN skeptic, derived) |
| **V5** | CLOSED, both port heads known, EGL_d ≥ H_set0 (σ0 = s_min) and H ≤ S_max + Htol | {OPEN} | the necessary condition for OPEN to hold too (PN1); a closed pump has no r |
| **V6, shared zone** | a pump whose discharge zone (§5.11's partition) also holds the discharge port of another pump that is on, of any kind, or the outlet port of a PRV whose status is `active`: if running, | {CLOSED} | a second pressure source on the header (PN2) |
| | the same, if CLOSED with both port heads known, | {ACTIVE, OPEN, MIN_SPEED}, from ACTIVE | as above, from the closed side |
| **V7** | a perturbed solve of V1 that does not converge | none: not converged, "the response of the network beyond <PU>'s discharge could not be computed" | — |

**V1, the response.** Two inner solves (`solve_gga`), with every state and branch law as converged, warm-started from the converged flows, at tolerance `RESPONSE_TOL` = 10⁻¹² and the project's `maxIterations`. The pump's own state is perturbed by ±δ, δ = Htol = 10⁻⁴ m:
- ACTIVE: the held value H_set0 ± δ;
- OPEN or MIN_SPEED: its law with a head offset ±δ (a new `OffsetLaw` wrapper in `elements.py`).

Then k_down = (EGL_d⁺ − EGL_d⁻)/(Q_d⁺ − Q_d⁻) and r = k_down/(2c_dQ_d). If Q_d⁺ = Q_d⁻, r = ∞: the flow is fixed elsewhere, for example by an FCV upstream.

*Why the pump's own state:* holding the discharge EGL instead makes the perturbed solve undetermined when an FCV is upstream (C found this). *Why `RESPONSE_TOL`:* a numerical choice, so that a flow change of about δ/k_down, near 10⁻⁶·Q in the measured cases, is resolved (C). Both numbers are in the methods summary (§8.2 item 4).

**V2's message** (PN6: the first draft asserted that both limit states satisfy their rules, which nothing checks):

> the static pressure at the discharge port of <PU> falls as its flow rises (r = 0.22: the losses beyond the port are less than one velocity head of its discharge pipe), so a drive holding it is unstable; a limit state, at maximum speed or at minimum speed with or without flow, may also satisfy its rules; add the exit or expansion loss beyond the port (an exit fitting at a reservoir, a reducer fitting, a Crane tee)

**Why V5 and V6 refuse nothing where the state is unique** (derived):
- V5: with r > 1 (P rising), OPEN at s_max runs at Q_M > 0 with P(Q_M) > P(0) = EGL_d(closed) ≥ H_set0, so X1 fires and the pinned OPEN state fails its rules. This is PCF7's and EP4's configuration (§9.3, §9.4), whose derivations require that X1 fires at s_max by `STATE_MARGIN`.
- V6, running booster: let r_spool be the loss between the port and the shared node in velocity heads of the discharge pipe. Regulating at Q_P, the shared node's head is H_set0 + (1 − r_spool)·c_dQ_P²; closed, it falls by what the other source's head loses with the smaller total flow; C1 keeps the booster closed only if the closed-state head at the port is still ≥ H_set0. Both hold only in a band of width at most (1 − r_spool)·c_dQ_P² of the other source's setpoint (PN, derived; 0.039 m in the measured network). With r_spool > 1 the pinned CLOSED state re-opens (C1), so it refuses nothing. The same derivation covers a fixed pump beside the booster (PN), so PCF14's derivation proves its setpoint outside that band (§9.3).
- V6, closed booster: if the other source holds the header at or above H_set0 (σ0 = s_min), a pinned regulating state with r_spool > 1 would put the header below H_set0 while adding flow to it, so it needs a reverse flow and P1 fails it; if the header is below H_set0 (σ0 = s_max), the closed state holds only with H > S_max, where no speed in range passes forward flow (P1 or P2 fails it).

*Measured* (PN, `r6_prv_parallel.py`, `r6b_r.py`, today's solver, the booster emulated by a pump at s_max and an ideal PRV at its port; PN skeptic reproduced it): RH 60 m → 100 m line → PRV (25 m of head) → 1 m spool → ideal tee run inlet; RL (head −10 m) → 10 m line → PU (H₀ = 60 − 2000x, s ∈ [0.7, 1]) → 1 m spool → tee branch; tee run outlet → 50 m with an exit → R2 24.5 m; both setpoints 25 m of head; no fittings on the spools.
- State A, PU regulating: Q 0.007664 m³/s, H 35.1709 m, s* 0.903942 ∈ [0.7, 1]; the real PRV is closed, with its outlet at 25.03874 m ≥ Hset − Htol, which prvstatus keeps closed (`status.py:212-239`).
- State B, the PRV active and PU closed: the PRV passes 0.007664 m³/s; PU's EGL_d is 25.03874 m ≥ H_set0, so σ0 = 0.7, and H = 35.0387 m > S_min = 29.40 m: C1 keeps it closed.
- V1 in state A: r = 10.590 (11.6 with the 0.1023 m bore): accepted. From state A, V6's pinned CLOSED solve is expected to reach state B, which holds every rule, and from state B its pinned regulating solve to reach state A (derived from the two measured states; the pinned paths themselves are not yet run, a C2 unit test, §9.7).
- The band: c_dQ² = 0.04855 m and the spool loses 0.00981 m, so r_spool = 0.202 and the band is 0.039 m. Equal setpoints ("2.5 bar" on both) are a natural input.

**On the measured header networks** (derived from the fixed-pump measurements; the build's unit tests, §9.7):
- J `j5`, R2 = 19 m: accepted at max speed; V3's pinned s_min branch runs at s_min with a port pressure below the setpoint (181,863.6 Pa), so N1 fails; and the closed state fails too (its discharge at zero flow, 19 m, is below H_set0, so σ0 = s_max, and H = 14 m < S_max re-opens it).
- J `j5`, R2 = 20.8–21.3 m: not converged; both limits hold (J) and r ≈ 0.22 (C).
- PN1, R2 = 31 and 33 m: not converged. Ending CLOSED (the path PN measured), V5's pinned OPEN state holds (X0 and X1 fail). Ending OPEN, V3's pinned branch reaches CLOSED at s_min, which C1 keeps.
- PN2: not converged, from either state.

*Measured* r (C, `p16b_regulation.py`, own-state perturbation, rule set C):

| Case | State | r |
|---|---|---|
| 100 m line with exit | active | 18.137 |
| 1 m spool with exit | active | 1.1705 |
| Parallel pumps, 20 m spools | active, active | 5.053, 5.041 |
| Parallel pumps, 2 m spools, +100 Pa | active, max | 11.51, 0.226 |
| Header case, R2 21 m | min | 0.221 |
| Header case, R2 19 m (only max valid) | max | 0.213 |
| FCV-fed pump at max | max | ∞ |

**Limitations (documented).**
- r is local, at the final flow. A multiplicity can be missed where r crosses 1 along the flow (laminar or transitional discharge, where losses are linear in Q).
- Each pinned solve follows one path. A second state that the path does not reach is missed. The fuzz's `state_search` is the independent check (§9.5).
- The tests look for a second state of each pressure pump, with the other elements following their rules. A multiplicity that needs another element pinned (v1's status-rule multiplicity, TSD §10.4) is not refused, as in v1 and slice 1.

**Cost.** V1: two warm-started inner solves per running pressure pump per solve and per system-curve point. V3 and V4: one pinned outer solve where r ≤ 1. V5: one per closed pressure pump at or above its setpoint with both heads known (the "satisfied booster"). V6: one per pressure pump with another pressure source in its zone. Not measured yet; it is a gate (§9.11).

### 5.11 Pressure zones (owner question Q1, recommended (a))

**Zone.** Remove from the port graph:
- every reservoir and ideal reference node;
- every pump;
- every PRV, PSV and FCV whose status is `active` or `failed_closed`;
- every isolation valve whose status is `isolated`;
- every check valve whose status is `locked_closed`.

A zone is a connected component of what remains: ports joined by connections, and through the remaining components' internal links. The removed components' ports stay in the zones they connect to, so a pump's discharge port and an active PRV's outlet port each lie in one zone.

**The rule.** Two or more pumps with status on and a discharge-pressure control whose discharge ports lie in one zone give `PRESSURE_CONTROL_ZONE` (422), naming them (E). The citation: Bentley, "Only one VSP may serve a pressure zone" (`vfd-industry-conventions.md` §2).

It is checked at build time. Series pressure pumps lie in different discharge zones and stay allowed. A pressure pump in parallel with a fixed or flow-controlled pump, or with an active PRV, is allowed; §5.10 V6 refuses such a pair at solve time where it has two steady states. The same partition, built once, gives V6 its zones.

**Limitation.** A zone is a topological approximation. Two zones joined by an active PRV that ends open interact. The 422 counts only pressure pumps; a PRV outlet or another pump in a pressure pump's zone is handled by V6, not by the 422 (v1 already allows parallel PRVs). Both are listed in TSD §12.

---

## 6. Edge cases

| # | Configuration | Handling | Expected outcome (evidence) |
|---|---|---|---|
| 1 | Short discharge connection that itself has an exit or expansion loss (r_ref slightly above 1) | C1 | Active in 6–9 iterations. *Measured*, C `p1c_spool.py` (rule set C): lagged, 0.5 and 0.1 m spools end "statuses oscillate (PU)"; exact, 8 iterations, s* 0.968158, p = 250,000.0 Pa. E `exp10`: 22 cases with a 1 m discharge fail lagged, 6–9 iterations exact. |
| 2 | Discharge connection without its own loss (r_ref ≤ 1), network beyond losing a little more than one velocity head (1 < r_tot ≲ 1.2): a short spool into an ideal tee, or a Crane run with no branch flow, then a main with an exit (PN3) | The lag stays (§2.3) | May end not converged at the default 100 iterations, although an active state exists; converges with more iterations. Documented, cases VH7 and PVH5. *Measured* for a PRV (PN `r2_prv_tee.py`, today and with C1 identical): r_tot ≈ 1.11 not converged (113 inner iterations, 326 with a Crane tee); r_tot ≈ 1.23 converged in 82–90 |
| 3 | Network beyond recovers the velocity head (r_tot ≤ 1) | §5.10 V1–V4 | Not converged where V2 finds the regulating state unstable or V3/V4 find a second state; accepted where only one limit holds |
| 4 | Dead-ended discharge (plug, closed isolation valve) | ACTIVE at zero flow | Running, s* = √((H_set0 − H_s)/H₀(0)), no `PUMP_FLOW_REVERSAL`. Outside [S_min, S_max]: OPEN or MIN_SPEED dead-headed, with the info flag. As a v1 pump against a plug. |
| 5 | Suction closed off | P0 | MIN_SPEED or OPEN dead-headed (§5.4) |
| 6 | Both sides closed off by fixed valves | P0 → OPEN | No result, no flag, as slice-1 CF16 |
| 7 | Closed between two check valves | Exact union (§5.7) | As C `p12` |
| 8 | Closed downstream check valve, network above the setpoint | v1 zero-flow multiplicity | Closed or active at zero flow; documented (Q6) |
| 9 | Reverse flow while ACTIVE | P1 → CLOSED, then C1 | *Measured*, C `p1_line.py` (rule set C): closed at s_min; with s_min 0.8, min speed, 0.009604 m³/s, in 3 outer iterations |
| 10 | Setpoint below the suction pressure | P3 → MIN_SPEED (or C1/C2 if the head is above S_min) | *Measured*, C (rule set C): min speed, discharge 0.80 bar against a 0.2 bar setpoint; flag |
| 11 | Setpoint above reach | P2 → OPEN; CLOSED (σ0 = s_max) if H > S_max | Flags |
| 12 | Q/s beyond x_mono | s_lo(Q) bracket; P3 on F(s_lo(Q), Q) | The slice-1 band (§5.6 item 6) |
| 13 | Drooping curve passing the ψ test | As slice 1 | No flow, or not converged (§5.6 item 5) |
| 14 | Running in a floating section | §5.8 | Not converged |
| 15 | Sealed loop anchored only by the pump | GGA "loose", then fallbacks, then §5.8 | Not converged |
| 16 | Port exactly at its setpoint at a limit, with a flow control in series | §5.9 | Not converged (over-controlled) |
| 17 | Flow control in series, two valid states | §5.9 swap test | Not converged, naming both (Q3) |
| 18 | Two pressure pumps whose discharges share a zone | §5.11 | 422 (Q1) |
| 19 | Discharge connection drawn toward the pump | `held_reference` sign (`gga.py:638-644`) | Same answer (§5.2) |
| 20 | Port elevation differs from the component's | z_d from the port node | *Measured*, C `p17_orient.py` (rule set C): H_set0 = 28.54399 m = 3 + p/(ρg) for a port 3 m up |
| 21 | Multi-segment discharge connection | c_d from the end segment at the port | Case PCF3 |
| 22 | Negative gauge setpoint, or one below the vapour pressure | Allowed within the bounds | `BELOW_VAPOR_PRESSURE` and NPSH as today |
| 23 | Glycol with no vapour pressure | `NPSH_NOT_CHECKED` at s* | As slice 1 |
| 24 | Transient iterates with heads near 10⁹ m | Existing `ENERGY_TOL` floor | Costs iterations, not results (§2.4, fuzzfc_10269) |
| 25 | Status off | CLOSED, fixed | `control.state` off, no setpoint flag |
| 26 | Crane tees nearby | Sequential mode as today | About one outer iteration per saturation (proposal risk 3) |
| 27 | Closed booster whose discharge is at or above its setpoint, both heads known, H ≤ S_max + Htol | §5.10 V5 | One pinned OPEN solve: with r > 1 it fails X1 and the closed state stands (PCF7, EP4); with a falling P it holds and the solve is not converged (PN1 network, R2 31 and 33 m) |
| 28 | Booster sharing its discharge zone with an active PRV or another pump that is on | §5.10 V6 | One pinned solve on the other side (closed, or running): not converged where both hold (PN2 network, equal setpoints, r_spool 0.20); the state stands where the spool loses more than its velocity head (PCF14) |

---

## 7. System curves

There is no algorithm change (`system_curve.py`), beyond the work in progress of §1.4, which slice 2 builds on:
- **The viewed pump's control is replaced by the forced flow,** whatever its mode (`status.py:319-321`, `394-395`). So H_sys keeps one definition, and the operating point lies on F(s*, ·).
- **Other pressure pumps that are on keep regulating,** and warm starts copy their statuses (`_warm_start`, `status.py:1865-1888`).
- **At each point,** the floating rule, the over-control tests and the second-state tests (§5.10) run for those other pumps. A point that fails one has no head ("not converged: …").
- **The default range** uses `speed`, the maximum (`default_flow_max`, `system_curve.py:67-71`).
- **The method text** is the existing sentence (`methods.py:163-167`): "A speed-controlled pump's own control is replaced by the fixed flow at each point; other speed-controlled pumps that are on keep regulating; its default range uses its maximum speed." It is true of both modes, so it stays gated on any controlled pump, as today, and a flow-only project's text is unchanged (RVG-14; an earlier draft added a second, pressure-specific sentence).
- **Slice 1's known limitation** (TSD §12 item 4, starved first points) does not arise for a pressure pump: P0 never closes it.

*Measured* (C, `p11_syscurve.py`, rule set C):
- The pump's own curve passes through its operating point: H_sys(0.0268) = 22.486 m, against 22.489 m at 0.026803 m³/s.
- A fixed pump beside a regulating pressure pump has heads at all 7 points, 13.04 → 29.03 m.
- A fixed pump upstream of a pressure pump has heads at all 6 points: −30.0 m at q = 0 (the pressure pump at max speed, dead-headed), −3.06 m at 0.0268, and 24.35 m at 0.03 (at min speed). The step near the flow where the pressure pump changes state is real.

---

## 8. Traceability

### 8.1 Pump trace (`trace.py:924-1288`)

The additions apply only for pressure mode, so flow-mode and fixed-pump traces stay byte-identical (`_speed_control_method`, `_speed_control_values` and `_speed_control_state_note`, `trace.py:1148-1288`, branch on mode).

**Inputs:**
- control mode "discharge pressure" (user);
- setpoint p_set, in Pa(g) (user);
- minimum speed (user);
- maximum speed (field `speed`, labelled default or user by `_given`, `trace.py:170`);
- the discharge port elevation z_d (its source);
- the diameter of the discharge pipe's end segment (the source of c_d).

**Equations:**
- "Active: EGL_d = z_d + p_set/(ρg) + v_d²/(2g), held at the discharge port (v_d in its pipe's end segment); the pump passes the flow that leaves the port and has no energy equation of its own (an active PRV's form, coupled exactly in Newton's step)".
- "s* solves s²H₀(Q/s) = EGL_d − EGL_s on [s_lo(Q), s_max] at the solved flow Q (Brent)".
- "Exact: the speed enters only the pump's head equation, so the Newton system is block-triangular".
- "Unique: d/ds[s²H₀(Q/s)] = s(2H₀ − xH₀′) > 0, x = Q/s".
- The rules P0–C2, with Htol and Qtol.
- "σ0 = s_min if EGL_d ≥ z_d + p_set/(ρg), else s_max".
- "r = (dEGL_d/dQ_d)/(2 c_d Q_d); the static pressure at the port rises with flow iff r > 1" (with Q2(a)).

**Sources:**
- EPANET 2.2 prvstatus and pumpstatus (hydstatus.c);
- Brent (1973);
- Fritsch–Carlson (1980);
- Bentley Fixed Speed Override (URL, proposal §2.4);
- Elhay et al. (2025), doi:10.1017/wat.2025.10005;
- with Q1(a), the Bentley pressure-zone rule (`vfd-industry-conventions.md` §2);
- CLAUDE.md D12.

**Values:**
- H_set0, c_d, Q_d, H_set(Q_d);
- the port's static pressure P_d·ρg, beside p_set;
- H, F(s_lo(Q), Q), F(s_max, Q), S_min, S_max, σ0;
- s* and the residual F(s*, Q) − H;
- s_lo, x_mono, ψ_min;
- r (with how it was computed) and the pinned outcome.

**State notes** state the inequality that set the state, with its values, as `_control_rule_values` does for valves (`trace.py:1353`). One template per row of §3.2 and per cause (RVG-14; values in braces, numbers printed as the existing notes print them). The first is filled with case PCF1's values:

| State | Cause | Note |
|---|---|---|
| active | regulating with flow | "Active: F(s_lo, Q) − Htol = 7.1991 m ≤ H = 12.7113 m ≤ F(s_max, Q) + Htol = 34.3986 m at Q = 0.0140039 m³/s; the discharge port is held at EGL_d = z_d + p_set/(ρg) + v_d²/(2g) = {z_d} + {p_set/ρg} + {v_d²/2g} m, 150,000 Pa(g) static; s* = 0.638074 on [s_lo, s_max] = [0.5, 1] (residual {res} m); r = {r} > 1 (V1)." |
| active | zero flow, discharge dead-ended (plug, closed isolation valve) | "Active at zero flow (its discharge is dead-ended): EGL_d = H_set0 = {h} m; H = {H} m lies within [S_min − Htol, S_max + Htol] = [{a}, {b}] m; s* = √(H/H₀(0)) = {s}; a pump running dead-headed at that speed, not reversed (no PUMP_FLOW_REVERSAL)." |
| max_speed | X1 fails at OPEN | "At maximum speed: the discharge static pressure {p_d} Pa(g) is below p_set = {p_set} Pa(g) by more than ρg·Htol (EGL_d = {e} m < H_set(Q_d) + Htol = {x} m), and H = {H} m ≤ S_max + Htol with Q ≥ −Qtol, so it runs as the fixed-speed pump at s_max = {s}; it returns to regulating once its discharge reaches p_set (EPANET 2.2 prvstatus)." |
| max_speed | P0, starved | "At maximum speed, dead-headed: its suction side reaches no reservoir or reference node, so it cannot hold its discharge; at zero flow EGL_d = {e} m < H_set0 + Htol = {x} m, so its drive runs to s_max = {s} (P0). The suction level is reported as EGL_d − S_max = {..} m, the dead-headed level (v1's convention)." |
| min_speed | N1 fails at MIN_SPEED | "At minimum speed: the discharge static pressure {p_d} Pa(g) is above p_set = {p_set} Pa(g) by more than ρg·Htol (EGL_d = {e} m > H_set(Q_d) − Htol = {x} m) at s_min = {s}, and H = {H} m ≤ S_min + Htol: it runs at s_min (no sleep) and passes more than the flow that would hold p_set; it returns to regulating once its discharge falls to p_set." |
| min_speed | P0, starved | "At minimum speed, dead-headed: its suction side reaches no reservoir or reference node; at zero flow EGL_d = {e} m ≥ H_set0 + Htol = {x} m, so its drive runs down to s_min = {s} (P0). The suction level is reported as EGL_d − S_min = {..} m (v1's convention)." |
| no_flow | both heads known, σ0 = s_min | "No flow: at zero flow its discharge EGL_d = {e} m is at or above H_set0 = {h} m, so its drive is at s_min = {s}, and the head across it, H = {H} m, exceeds that speed's shutoff head S_min = {S} m (EPANET 2.2 pumpstatus). Re-solved once at maximum speed (V5): {the rule that failed, e.g. 'its discharge would be at {p} Pa(g), above p_set, so it would regulate'}." |
| no_flow | both heads known, σ0 = s_max | "No flow: at zero flow its discharge EGL_d = {e} m is below H_set0 = {h} m, so its drive is at s_max = {s}, and the head across it, H = {H} m, exceeds that speed's shutoff head S_max = {S} m." |
| no_flow | discharge closed off | "No flow, its discharge closed off (no reservoir or reference node beyond it): the head across it is not fixed. Reported at the lowest discharge level that keeps it closed, EGL_d = EGL_s + S_eff = {..} m, S_eff = clip(H_set0 − EGL_s, S_min, S_max) = {..} m, with the speed that level implies, √(S_eff/H₀(0)) = {..} (a convention: v1's dead-headed level, generalised)." |
| no_flow | suction closed off | "No flow, its suction closed off: reported at the highest suction level that keeps it closed, EGL_s = EGL_d − F(σ0, 0) = {..} m, σ0 = {s_min or s_max} because EGL_d = {e} m is {at or above, or below} H_set0 = {h} m (a convention)." |
| — | both sides closed off | No pump result and no trace values, as v1 (`results.py:686-699`); the topology note names the closed-off section. |
| off | status off | "Off: the control is not applied." |

Every second-state test that ran (§5.10) adds a line: the test, r where computed (with "own-state perturbation ±1e-4 m, solves to 1e-12"), and the pinned outcome.

`test_trace.py` checks each template byte for byte, on a network that reaches that row, and that flow-mode and fixed-pump traces are byte-identical to the C1 tree's.

### 8.2 Methods summary (`methods.py:121-170`)

**Conditions** (RVG-14). Today the whole flow-setpoint text is gated on any control: `controlled = any(pump.control is not None …)` (`methods.py:121`, `125`). It becomes mode-specific:
- the flow-setpoint items (the first, second and fourth of `speed_control_items`) and their references appear when a flow-controlled pump exists, exactly as today;
- the items below appear when a pump with a discharge-pressure control exists;
- the shared items (efficiency and NPSHr by the affinity laws; the system-curve sentence, §7) appear when either exists, once. Order: when a flow-controlled pump exists, today's four items in today's order (the efficiency item third), then the pressure items below; with no flow pump, the pressure items with the efficiency item after their item 2;
- references: the flow list as today, then the pressure list (EPANET 2.2 hydstatus.c prvstatus and pumpstatus; Brent 1973; Bentley Fixed Speed Override; EPANET 2.2's speed efficiency; Elhay et al. 2025; CLAUDE.md D12), without repeats.

So a flow-only project's summary is byte-identical to the C1 tree's, and a pressure-only one carries no flow-setpoint text. `test_methods.py` checks the three cases (flow only, pressure only, both).

**Items** (numbers printed from their constants with `:g`, as the existing items do):
1. **The held-port formulation, the speed recovery and its exactness:** "Speed-controlled pumps (discharge pressure): while the drive regulates, the static pressure at the pump's discharge port is held at its setpoint, EGL_d = z_d + p_set/(ρg) + v_d²/(2g), as an active PRV holds its outlet, and the pump passes the flow that leaves the port. Its speed is the unique root of F(s, Q) = EGL_d − EGL_s on [s_lo(Q), s_max] at the solved flow (Brent's method); this equals solving the speed with the network: it enters only the pump's own head equation."
2. **Limits:** "It regulates while F(s_lo(Q), Q) − 0.0001 m ≤ EGL_d − EGL_s ≤ F(s_max, Q) + 0.0001 m. Above, it runs as a fixed-speed pump at s_max (pressure below its setpoint); below, at s_min (pressure above it; no sleep). It returns to regulating once the port pressure reaches the setpoint (EPANET 2.2 prvstatus). At zero flow its drive is at s_min when the port is at or above the setpoint and at s_max otherwise, and the pump re-opens once the head across it is at most that speed's shutoff head (EPANET 2.2 pumpstatus). Where the flow divided by s_min lies beyond x_mono, for a head between F(s_lo(Q), Q) and F(s_min, Q) the pump held at s_min and passing more flow is a steady state too; the solve starts with the pump regulating and does not move it to s_min for a head in that band."
3. **The floating-section rule and over-control:** "A discharge-pressure-controlled pump that runs with a port in a part of the network that no reservoir or reference node fixes is reported as not converged, naming it: the speed that holds a pressure on that arbitrary level is undetermined. Closed with both ports in such a part, and closed at every level of it (the head across it at least its maximum-speed shutoff head plus 0.00005 m), it is reported with that part's flows and head differences only. One at a speed limit whose discharge is within 0.0001 m of its setpoint head, in series with another control with nothing fixing the pressure between them, is reported as not converged (over-controlled). A flow control in series with one is solved once more with the one at its limit held regulating; if that state also satisfies every rule, the solve is reported as not converged, naming both states." (The last sentence with Q3(b).)
4. **The second-state tests** (Q2(a)): "At the converged state, each such pump running with flow is solved twice more with its own head offset by ±0.0001 m, to a flow tolerance of 1e-12, which gives the response of the network beyond its discharge port, r = (dEGL_d/dQ_d)/(2 c_d Q_d), c_d Q_d² being the velocity head at the port; the static pressure at the port rises with flow if and only if r > 1. Where r ≤ 1 a regulating pump is unstable and the solve is reported as not converged; a pump at a speed limit is solved once more on the other side (at minimum speed with or without flow, or at maximum speed). A pump held at no flow with its discharge at or above its setpoint is solved once more at maximum speed, and one whose discharge's pressure zone holds another pump or an active PRV once more closed, or regulating if it is closed. A second state that satisfies every rule and differs in flow is reported as not converged (two steady states). r is evaluated at the solved flow only, and each further solve follows one path."
5. **The zone rule** (Q1(a)): "Two or more discharge-pressure-controlled pumps that are on, whose discharge ports lie in one pressure zone (the part of the network bounded by reservoirs, reference nodes, pumps, active or failed-closed control valves, closed isolation valves and locked-closed check valves), are rejected as a topology issue (PRESSURE_CONTROL_ZONE): one variable-speed pump per pressure zone (Bentley WaterGEMS)."
6. **C1's coupling sentence,** with its condition extended (§2.8).


---

## 9. Verification plan

### 9.1 Process

The process is the slice-1 method:
1. One implementer.
2. An independent reference author, who never reads `services/` and works from this document only: its semantics and rules (§3, §5) and its case specifications (§2.9, §9). The reference author writes:
   - the derivations and case files: their modules import only `opensolve_pipe.models`, `element_laws`, `line`, `derivations`, `derivations_pumps` and `derivations_pump_control` (for `speed_linear`, `speed_on_parabola`, `require_unique_speed`);
   - **every independent checker** (RVG-8), since these decide criticality and validate every case: `tests/reference/element_laws.py` (`pressure_pump_state_problem`), `network_check.py` (the active law), `free_levels.py` (the exact union), `tests/differential/checks.py` (`rule_pressure_pump`, `control_problems`, `_border_regions`, `zero_flow_infeasible`, the floating-section and in-series checks of §9.5), the `state_search.py` pins and `epanet_model.py`'s substitute and r runs. Their imports stay within `opensolve_pipe.models`, `tests.reference` and `tests.differential`, as `checks.py`'s do today; a checker that must run our solver (`state_search`, the corpus and fuzz drivers) calls only the public `solve_project` (`state_search.py` does at `f9d402b`).
   The implementer does not edit these files. A mismatch between solver and checker is resolved by root cause, with the reference author changing a checker only for an error in the checker shown against this document.
3. Integration: on a mismatch, find the root cause, never loosen a tolerance.
4. The corpus comparison and all three fuzz profiles.
5. The six-dimension adversarial review: physics, reference independence, status and free-level logic, traceability, web and longevity, performance.
6. Fixes, each with a test that fails before the fix.

### 9.2 Pass criteria

- **D6, unchanged** (`tests/reference/test_reference_cases.py`):
  - flows within 0.5 %;
  - EGL within 0.5 % or 0.01 m;
  - pressures within 0.5 % or ρg·0.01 m;
  - states exact;
  - warning and invalid flags exhaustive.
- **Speed** (standing answer): within 0.5 %, and s²H₀(Q_ref/s) within 0.01 m of the reference head (`_speed_failures`, `test_reference_cases.py:113`).
- **Pressure mode:**
  - when active, the expected port pressure is p_set, so D6's pressure criterion applies to it;
  - at a limit, the derivation proves the port pressure lies on the documented side of p_set by at least ρg·`STATE_MARGIN`.
- **Margins.** Derivations keep every inequality of §5.4 at least `STATE_MARGIN` = 0.05 m from its threshold (`element_laws.py:332`).
- **Observable velocity head** (revised, RVG-13). D6 takes the looser of 0.5 % and 0.01 m, so at an EGL of 15.5 m the binding head tolerance is 0.077 m, not 0.01 m, and above an EGL of about 30 m the EGL check alone cannot see a dropped 0.15 m velocity head. So each case's derivation also computes the **wrong-model answers**: the same network with H_set = H_set0 (no velocity head), and, where the discharge connection has several segments, with the velocity head of the wrong segment (PCF3). It asserts that each wrong answer fails D6 by at least 2× its tolerance in at least one checked quantity (flow, EGL_d, port pressure, speed or its implied head), and the case's source text states the margins per quantity. *Measured* on PCF1 (RVG, `rv12_pcf1_observable.py`, reference modules only): port velocity head 0.1480 m, EGL_d 15.4744 m; dropping it misses the flow by 2.265 % (4.53× the 0.5 % tolerance), EGL_d by 0.148 m against 0.0774 m (1.91×) and the port pressure by 1,383.6 Pa against 750 Pa (1.84×): PCF1 passes through its flow.
- **Multi-state networks** (revised, RVG-4, RVG-11, PN5). A case file is built only where the derivation enumerates the candidate states and proves that exactly one satisfies every rule by `STATE_MARGIN`.
  - **The candidates** are every combination of the options of every status element of the case: active, max_speed, min_speed and no_flow per controlled pump; running and no_flow per fixed pump; open and closed per check valve that is `active`; active, open and closed per PRV, PSV and FCV that is `active`. Each competing combination is shown to fail one of its rules by `STATE_MARGIN`.
  - **One physical state, two labels.** Candidates that differ only in the labels of elements at zero flow, with the sections beyond them at rest (`state_search.same`, TSD §5.4; v1's zero-flow multiplicity, D9), are listed in the derivation. The case may pin the label the rules reach, with the path written out (the solve's start state and the rules that fire), as slice 1's dead-end case does (`derivations_pump_control.py:2169-2229`). Where that label depends on an open owner question (Q6: PCF16 B), it is a membership unit test until the answer.
  - **The one documented two-state band** (§5.6 item 6, the x_mono band): a case may pin ACTIVE there by D11's path rule (the solve starts active, and P3 tests F(s_lo(Q), Q)), as slice 1's CF21 does (`derivations_pump_control.py:770-842`), only if its derivation enumerates and checks the second state, MIN_SPEED, and states the path. This exception is written into D12 and kept out of the fuzz's critical rule (§9.5).
  - Where several states hold otherwise, the test is a unit test that asserts "not converged, or one of the enumerated valid states". It is never a pinned state.

### 9.3 Closed-form cases (`tests/reference/derivations_pump_pressure.py`)

Expected values gain `speed`, `controlState` and port pressures.

**Common line:** R1 (z₁, level₁) → L1 → PU1 → L2 → R2 (z₂, level₂). Line laws are Darcy–Weisbach with `fluids.friction.Colebrook`, plus the cited `fluids.fittings` K (`line.py`, `derivations.py`), with FLUID_A (`derivations.py:93`).

**Derivation of an active case:**
1. Q is the root of φ(Q) = H_R2 + h_L2(Q) − H_set(Q) = 0, by `brentq`. Guards: a sign change on the bracket; φ increasing (1,000-point sample); r = h_L2/(c_dQ²) > 1 at the root.
2. EGL_s = H_R1 − h_L1(Q), and H = H_set(Q) − EGL_s.
3. The band check F(s_lo(Q), Q) + margin ≤ H ≤ F(s_max, Q) − margin.
4. s* from `speed_linear` (straight curve) or `speed_on_parabola` (PCHIP), cross-checked to 10⁻¹².

| Case | Inputs and derivation | Proves |
|---|---|---|
| PCF1 `pump_pressure_control_active_linear` | z₁ 0, level₁ 3; L1 0.1023 m × 6 m, sharp entrance; PU1 at z 0, `curve_straight` (H₀ = 40 − 400x, `derivations_pump_control.py:464`), s ∈ [0.5, 1], p_set 150,000 Pa; L2 0.1023 m × 120 m, two LR elbows and an exit; R2 z 10, level 2. *Prototype* (V, `exp8`): Q = 0.0140038577697 m³/s, H = 12.7113433745 m, s* = 0.638074114701, r(L2) = 23.5, band [7.1992, 34.3985] m, velocity head 0.148 m. Today's solver with the pump fixed at s* reproduces Q to 3.7·10⁻¹⁶ and p_d = 150,000.0000 Pa. | The held-port form and speed recovery |
| PCF2 `…_active_pchip` | As PCF1 with curve_a: x* by brentq on H₀(x) = (H/Q²)x², s* = Q/x*; `require_unique_speed` on [Q/s_max, Q/s_lo(Q)] | The PCHIP path |
| PCF3 `…_port_segment` | L2 in two segments: 0.0779 m × 2 m at the port (v ≈ 2.9 m/s, v²/(2g) ≈ 0.44 m), then 0.1023 m × 118 m; c_d from the 0.0779 m segment | The end-segment velocity head; the wrong segment misses by more than 0.3 m |
| PCF4 `…_max_speed` | p_set high: the fixed solution at s_max (`derivations_pumps.solve_pump_line`) has EGL_d ≤ H_set(Q) − margin | Saturation equals the fixed pump at `speed`; the info flag |
| PCF5 `…_min_speed` | A gravity line, p_set low: the fixed solution at s_min has EGL_d ≥ H_set(Q) + margin and H ≤ S_min − margin | The lower limit |
| PCF6 `…_no_flow_max` | H_R2 − H_R1 ≥ S_max + margin and H_R2 < H_set0; Q = 0; speed s_max | C1 at s_max; `PUMP_FLOW_REVERSAL` and the info flag |
| PCF7 `…_no_flow_satisfied` | H_R2 ≥ H_set0 + margin and S_min + margin ≤ H_R2 − H_R1 ≤ S_max − margin. No flow at s_min; a fixed pump at s_max would run here. Guards: ACTIVE would reverse L2 (P1); OPEN's port static head exceeds H_set0 by margin (X1 fires), which is also what makes §5.10 V5's pinned OPEN solve fail; MIN_SPEED has H ≥ S_min + margin, so N0 closes it. | C1 at s_min; V5 runs and refuses nothing; flags per Q4 |
| PCF8 `…_dead_end_active` (+ b, c) | L2 ends at a plug. Q = 0, EGL_d = H_set0, s* = √((H_set0 − H_R1)/H₀(0)) with S_min + margin ≤ H ≤ S_max − margin. Variant b: H > S_max + margin, max_speed dead-headed, EGL_d = H_R1 + S_max. Variant c: H < S_min − margin, min_speed, EGL_d = H_R1 + S_min. The derivation lists CLOSED (the plug's section at rest, a free level) as the same physical state with another label (§9.2) and writes the path: the solve starts ACTIVE, the held node fixes EGL_d, and no rule fires (variants b and c: P2 or P3, then X1 or N1 fail). | Running at zero flow, with no reversal flag |
| PCF9 `…_off` | The v1 off pump | The control is ignored |
| PCF10 `…_stable_bracket` | `curve_straight`, s ∈ [0.1, 1], inputs set so that Q = 0.05 m³/s and H = −2 m: p_set = ρg(H_R2 + h_L2(0.05) − c_d·0.05² − z_d), level₁ from EGL_d. Closed form: x_mono = 2a/b = 0.2; s_lo = bQ/(2a) = 0.25; F(s_lo, Q) = −2.5 m < H < F(s_min, Q) = −1.6 m; s* = 0.25 + √5/20 = 0.361803. **Two-state band** (§5.6 item 6; RVG-4, PN5): the derivation enumerates and checks the second state, MIN_SPEED at Q = 0.052395 m³/s with its port 0.2207 m of head above p_set (*measured*, RVG `rv5_pcf10_two_states.py`), and pins ACTIVE by D11's path rule, as slice 1's CF21 (§9.2). | P3 uses F(s_lo(Q), Q); the path rule |
| PCF11 `…_active_outside_curve` | Q/s* beyond the last point, Q/s_max inside; s* by the end-tangent formula (the parabola route agrees) | `PUMP_OUTSIDE_CURVE` at s* |
| PCF12 `…_series_prv_{active,open}` | Pump then PRV2. Regime A: PRV2 below what PU1 and the line give at its inlet, both active (two independent closed forms). Regime B: PRV2 above, PRV2 open, PU1 active through it. The guards enumerate PU1's four states × PRV2's active, open and closed (RVG-11). | Series with a PRV |
| PCF13 `…_series_flow_control_{a,b}` | R1 → PU1 (flow) → L_m → PU2 (pressure) → L2 → R2. Regime A: EGL_d2 = H_R2 + h_L2(Q_set) ≥ H_set(Q_set) + margin, so PU2 is at min and PU1 active with H₁ = EGL_d2 − F₂(s_min, Q_set) − h_Lm(Q_set) − EGL_s1. Regime B: EGL_d2 ≤ H_set(Q_set) − margin, PU2 at max. The guards enumerate PU1's and PU2's four states each (the swapped candidates among them) and require every competing one to fail by margin. | Series with a flow control; the swap test passes |
| PCF14 `…_parallel_fixed` | A pressure pump beside a fixed pump on a header T, with H_T unknown: the pressure pump's flow from H_set(Q_P) − H_T = h_LP(Q_P); the fixed pump's from F_f(Q_f) = H_T + h_Lf(Q_f) − EGL_s; continuity solved for H_T by brentq. The pressure pump's spool has an exit-like loss (r_spool > 1 by margin), and the guards enumerate the fixed pump's running and no_flow × the pressure pump's four states; in particular the state with the pressure pump closed and the fixed pump alone puts the header below H_set0 − margin, so C1 re-opens it: the setpoint lies outside §5.10 V6's two-state band (PN2). | Coexistence; V6 runs and refuses nothing |
| PCF15 `…_loop_with_reference` | R1 → L1 → PU1 → L2 → ideal tee T1 run inlet; two parallel pipes La (run outlet) and Lb (branch) of different lengths to ideal tee T2; T2 → L3 → an ideal reference node RN at a fixed gauge pressure. Q is the root of H_RN + h_L3(Q) + h_par(Q) + h_L2(Q) = H_set(Q) by `brentq`, with h_par(Q) from h_a(Q_a) = h_b(Q − Q_a), itself by `brentq` (ideal tees impose one head per tee); guards as for an active case (r > 1 at the root, φ increasing) and the four pump states enumerated (RVG-11: written out; the first draft had no derivation). | Determined loops |
| PCF16 `…_zero_flow_bound_reopen` | The pump and a discharge check valve close together; the pipe between has a free level X. H_s + S_min < H_down < H_set0 < H_s + S_max, so they re-open (S_eff = H_set0 − H_s > H_down − H_s), where a bound at S_min would keep them shut. The closed candidate needs X ≥ H_s + S_eff = H_set0 > H_down + margin with the check valve closed, which fails. Final state by brentq, as CF14b. Variant B (H_set0 < H_down < H_s + S_max with H_down − H_s > S_min: they stay closed, where a bound at S_max would re-open them) is two-state under §5.6 item 4 (closed, or active at zero flow) and depends on Q6, so it is a membership unit test (§9.7), not a case file (RVG-11). | The one-sided bound S_eff |
| PCF17 `…_suction_closed_{min,max}` | A closed isolation valve on the suction. R2 above the setpoint: min speed, dead-headed, EGL_s = EGL_d − S_min. R2 below: max, EGL_s = EGL_d − S_max. The derivation lists CLOSED with the suction section at rest as the same physical state with another label (§9.2), and writes the path: the solve starts ACTIVE, the GGA starves the link, P0 picks the target by EGL_d against H_set0 + Htol (margin), and the target keeps its state (X1 or N1 fails by margin). | P0's split |
| PCF18 `…_two_check_valves` | R1 → CV1 → PU → CV2 → R2 with S_min > H_R2 − H_R1 (C's s_min 0.8 case): min speed with flow, by brentq. The guards enumerate the pump's four states × CV1 and CV2 open and closed. | The exact union (§5.7); the "no constraint" rule fails it |

**Floating cases** (`test_floating_sections.py`):
- PF1, a sealed loop with an active pressure pump: not converged, and the message names the pump.
- PF2, the same pump off: the v1 isolated result.
- PF3, a fixed-pump floating loop with a closed pressure pump inside, H > S_max + Htol: converged with `UNDETERMINED_PRESSURE`.

**System-curve cases** (`test_system_curves.py`):
- SC-P1: H_sys(q) = H_R2 − H_R1 + h_L1(q) + h_L2(q), and the operating point lies on it and on F(s*, ·).
- SC-P2: a fixed pump A beside pressure pump B, with a closed-form H_sys,A(q) while B regulates, and B closed by P1 past the closed-form flow at which its flow reaches zero.

**Velocity-head stress** (C2):

| Case | Discharge | r | Expected |
|---|---|---|---|
| PVH1 | 0.5 m + exit | ≈ 1.09 | Active, as PCF1; converges only because of C1 |
| PVH2 | 0.05 m + exit | ≈ 1.01 | As PVH1 |
| PVH3 | no exit; p_set above R2's static head at the port | < 1 | max_speed is the unique valid state (X1 fails at every forward flow, because P_d < p_set) |
| PVH4 | no exit; p_set below R2's static head | < 1 | Several rule-valid states; a membership unit test (rule V with Q2(a)) |
| PVH5 | 0.3 m spool without fittings → ideal tee (branch to a plug) → 0.3 m with an exit → R2: VH7's network with the pump in the PRV's place | r_ref < 1, r_tot ≈ 1.1 | Documented limitation (§2.3, §6 row 2): a unit test asserting not converged at the default 100 iterations and, with `max_iterations` 300, converged active at the closed-form flow and speed |

### 9.4 EPANET references (`generate_epanet_cases.py`, WNTR 1.5.0, `swamee_jain`, collinear curves)

**Facts checked** (V) in the installed WNTR:
- `add_pump(..., speed=...)` (`wntr/network/model.py:491`, "Relative speed setting" at 518-519) is written as `SPEED` with `{speed:15.11g}` when it is not 1 (`wntr/epanet/io.py:812-816`).
- `add_valve(..., valve_type="PRV", initial_setting=...)` (`model.py:530`, 538, 558).
- EPANET evaluates h = ω²H₀(q/ω) (`generate_epanet_cases.py:53-61`).
- *Measured* (V, `exp6`): a PRV directly on the pump's discharge junction runs without error.

**Substitute for active and max_speed.** The pump is replaced by:
- a driver pump, OPEN at SPEED = s_max, from the suction junction to a new junction `<id>_mid` at El z_d;
- an ideal PRV from `<id>_mid` to the discharge junction, with the discharge pipe's diameter and minor loss 0.

`PumpRun` (`generate_epanet_cases.py:596`) gains `prv_setting`.

**Setting conversion, as for PRVs** (`generate_epanet_cases.py:37-41`, `751-776`):
- setting = p_set/(ρg) + v_d²/(2g), with v_d = Q/A from the previous EPANET run's flow in our discharge connection (0 to start), and ρ and our g as `element_laws.setpoint_head` uses (`element_laws.py:214-219`);
- iterated until it changes by less than `SETTING_TOLERANCE` = 10⁻¹² m (`generate_epanet_cases.py:128`), in at most 50 iterations;
- the cases use discharge pipes with r ≫ 1, so the iteration contracts fast.

**The substitute and the pump at s\*.** Downstream and suction heads and flows are the same; only the internal junction differs. *Measured* (V, `exp4`/`exp6`):
- For p_set 294,288.9 Pa (the static pressure at SPEED 0.75), the substitute's PRV is active: Q 0.009308287 m³/s, p_d 294,288.901 Pa, s* (closed form) 0.749999966, independent of a 0.1, 1 or 10 m spool.
- EPANET run at SPEED = s* against the substitute: flows within 1.03·10⁻⁷ relative, heads identical.
- With the PRV open, the substitute equals the fixed pump at s_max: Q 0.02087183 m³/s, EGL 39.825954 against 39.825962 m.

**Cases** on the slice-1 `pump_network` (pump at z 1; S1 5 m, S2 30 m, S3 25 m; curve H₀ = 50 − 300x):

| Case | Inputs | EPANET run | Generator assertions | *Measured* (V) |
|---|---|---|---|---|
| EP1 `epanet_pump_pressure_control` | p_set 350,000 Pa, s ∈ [0.7, 0.9] | Substitute | PRV active (status 2); F(s_lo, Q) + margin ≤ H ≤ F(s_max, Q) − margin; s* = `speed_linear` at EPANET's (Q, H); EPANET at SPEED = s* reproduces every flow, and p_d, within D6 | PRV active, Q 0.01779882, H 31.7653 m, s* 0.852244, p_d 350,000.0 Pa |
| EP1b `…_speed` | as EP1 | brentq over ω ∈ [s_min, s_max] of p_d(ω) − p_set on EPANET runs at SPEED = ω, with p_d(ω) = ρg(H_d − z_d − v_d²/(2g)); xtol 10⁻⁹; ω rounded to 11 digits | sign change at the ends; p_d increasing at 9 sampled speeds; ω* within 0.5 % of EP1's s* | at p_set 294,288.9 Pa: ω* = 0.749999935 against s* = 0.749999966 (4.2·10⁻⁸ apart) |
| EP2 `…_max` | p_set 420,000 Pa, s ∈ [0.7, 0.9] | SPEED = s_max; SPEED = ω at 9 sampled speeds; the pump CLOSED | substitute PRV open (status 1); p_d(s_max) ≤ p_set − ρg·margin; p_d(ω) increasing over the 9 speeds, so no speed in range holds p_set and MIN_SPEED fails N1; the closed candidate re-opens: from the closed-pump run's heads, σ0 by EGL_d(0) against H_set0, and H(0) ≤ F(σ0, 0) − margin | p_d(0.9) = 380,126.4 Pa, 4.07 m of head below |
| EP3 `…_min` | p_set 250,000 Pa, s ∈ [0.75, 0.95] | SPEED = s_min; SPEED = ω at 9 sampled speeds; the pump CLOSED | p_d(s_min) ≥ p_set + ρg·margin; pump running; p_d(ω) increasing, so no speed in range holds p_set and OPEN fails X1; the closed candidate re-opens (C1 test on the closed-pump run's heads, as EP2) | p_d(0.75) = 294,288.9 Pa, 4.5 m above |
| EP4 `…_no_flow_min` | p_set 200,000 Pa (H_set0 21.394 m), s ∈ [0.6, 0.9] | SPEED = s_min; SPEED = s_max; SPEED = ω at 9 sampled speeds | EPANET pump closed (status 0) at s_min; EGL_d ≥ H_set0 + margin; H − S_min ≥ margin; S_max − H ≥ margin; at SPEED = s_max the pump runs with p_d(s_max) ≥ p_set + ρg·margin, so OPEN fails X1 (and §5.10 V5 refuses nothing); p_d(ω) ≥ p_set + ρg·margin at every sampled speed at which the pump runs, so no speed holds p_set with forward flow | closed at 0.6; EGL_d 27.319 m, H 22.32 m, S_min 18 m, S_max 40.5 m |

The assertions added after the review (RVG-12: every competing state of EP2–EP4 excluded in EPANET's own runs, as §9.2 requires) are not measured yet; the measured column is V's. EP1's assertion is already on the run at SPEED = s* (the substitute's p_d is p_set by construction, and only reported).

**EPANET's constants.** At the flows the setpoint fixes, EPANET's friction losses are 8.1·10⁻⁴ below ours and its minor losses 9.2·10⁻⁴ below (TSD §10.4). Before writing a case, the generator bounds the shift of the reference head by 9.2·10⁻⁴ × (the suction line's loss) + |∂F/∂Q| × 9.2·10⁻⁴ × Q, and refuses a case where the bound exceeds 0.005 m (V).

### 9.5 Differential fuzz: profile `pressure_control`

**Seeds.** 20,000–22,999 (`PRESSURE_CONTROL_SEEDS`), disjoint from the other profiles. Draws come from `random.Random(f"pressure_control:{seed}")` after every default draw (as `add_flow_controls`, `generator.py:417-481`). So the default and flow_control networks are untouched.

**Generator** (`generator.py`):
- 0–2 controlled pumps (weights [1, 5, 4]), each discharge_pressure with probability 0.75 and flow with probability 0.25, so the modes interact.
- Placement as in `add_flow_controls`, 30 % in series with the previous one.
- **Under Q1(a), never two pressure pumps with discharge ports in one zone** (§5.11). A unit test covers the 422.
- **Setpoint:** p_set = ρg(h_t − z), with h_t uniform on [min boundary head − 5, max boundary head + speed²·H₀(0) + 5], clipped to [0, 9·10⁵] Pa and rounded to 0.1 Pa, so all five states occur.
- **minSpeed:** 0.1–0.9 × speed.
- **Discharge:** with probability 0.25 a short spool (0.3–3 m) with a custom K = 1 fitting (the C1 stress); otherwise the default connections. Crane-tee or exit-fitted discharges occur as well as ideal tees. (Revised, RVG-17: the first draft's reason, "or most draws would end in rule-V exits", is not supported. *Measured* by RVG, `rv9_discharge_r.py`, generator only, over flow_control seeds 10,000–12,999 with f = 0.02 nominal: 3,154 of 3,679 controlled pumps that are on (85.7 %) have a discharge connection that by itself loses more than one port velocity head, a lower bound since it ignores Crane fittings without a K override.)
- **Through placement.** Slice 1's placement, which this reuses, left 183 of 3,995 controlled-pump final states active and 1,957 at max_speed, most at zero flow, dead-ended (TSD §10.4). In pressure mode a dead-ended pump is active at zero flow, the trivial s* path. So the count gates below are set before the full run; if a 200-seed sample (20,000–20,199) run with the first build falls short of them, placement is biased toward connections with a path on to a reservoir (fixed before the full run, and recorded).

**EPANET mapping** (`epanet_model.py`, `control_pins` at 146-170):
- active → the substitute (§9.4), its setting iterated with the PRV/PSV settings in `_run_epanet` (`epanet_model.py:487-533`). That loop stops at 60 rounds (`epanet_model.py:521`) and contracts at 1/r, too slowly for short spools, so the substitute's settings take a secant update from the third round on. Every existing PRV and PSV keeps the plain update, so the frozen default and flow_control records are unchanged (V).
- max_speed / min_speed → OPEN at that SPEED.
- no_flow → CLOSED.
- a pump we report without a result → SPEED s_max.
- Setpoints are ≥ 0 Pa, so no setting is negative.

**Independent checker** (`checks.py`), written by the reference author from §5.4, §5.7 and §5.10 (§9.1):
- `rule_pressure_pump`, with H_set from `el.setpoint_head`;
- `element_law` in ACTIVE: ("head", EGL_d − H_set(Q));
- `connects_heads` False when active;
- `control_problems`:
  - the active speed lies in [s_lo(Q), s_max] with |F(s, Q) − H| ≤ Htol;
  - the limit speeds;
  - σ0 for no_flow;
  - `setpointAchieved` and the flag;
- `zero_flow_infeasible` adds H_s − H_d ≤ −S_min (a necessary condition);
- `headless_infeasible` and `_border_regions` enumerate the exact union R;
- a converged result with a running pressure pump in a floating section is a self-check failure (critical);
- **guard-exit checks** (RVG-7), for each not-converged result whose message names a slice-2 guard:
  - §5.8 floating: the checker's own floating-section test (no path from the pump's port section to a fixed head on the port graph) confirms it;
  - §5.9 over-control: the checker confirms that the named elements lie in series with no fixed or held head between them (a path test on the port graph) and that the pump's port is within Htol of its setpoint head;
  - §5.9 swap test and §5.10 V3–V6: `state_search` (below) must find at least two fully determined valid solutions that differ in flowing state (`state_search.multiple`);
  - §5.10 V2: an independent r from EPANET, r_EP = (ΔH_d/ΔQ_d)/(2c_dQ_d) from two runs of the substitute with its setting at ±δ_EP, EPANET's heads being our EGLs (D7), must be ≤ 1 + β;
  - an exit that its check does not confirm is a new critical class, `a_guard_unjustified`, added to `classes.CRITICAL`;
  - and a converged result with an ACTIVE pressure pump whose r_EP < 1 − β is critical too (`a_unstable_active`), since V2 should have refused it.
  - δ_EP and β (derived, not tuned): EPANET returns float32 results (continuation prompt §4), so δ_EP = 0.01 m (100 × Htol) keeps a head difference resolved to about 2·10⁻⁴ of itself at heads near 30 m; β = 0.05 covers EPANET's constants (friction and minor losses up to 9.2·10⁻⁴ below ours, TSD §10.4) and the secant over ±δ_EP (a change of r of order ΔQ_d/Q_d ≈ 1 % for the generator's spools). A pump with |r_EP − 1| ≤ β is recorded as borderline, not critical.

**Speed comparison** (`speed_comparison`, `checks.py:259-306`):
- s_ref = `implied_speed` at EPANET's (Q_e, H_e), within 0.5 %;
- our implied head at (s_o, Q_e) against H_e by D6's head criterion;
- p_d from EPANET's head at the discharge junction, against p_set by D6's pressure criterion.

**`state_search`** (`state_search.py:38-80`) pins pressure pumps over active (speed range widened to `ACTIVE_SPEEDS`), max_speed, min_speed and no_flow. `control_search` covers both modes.

**Criticality of a second state** (revised, RVG-6; defined here, before the run). The first draft made every second valid state with a pressure pump in another running state critical, which the design's own accepted multiplicities would have made unattainable. Now, in this profile, a converged result is **critical** (`a_pressure_multiple`, added to `classes.CRITICAL`) when `control_search` finds two distinct valid solutions that differ in flowing state (`state_search.multiple`, both fully determined), unless the pair falls in one of these documented classes, each with a mechanical test:
1. **zero-flow labels** (§5.6 item 4, Q6): the two differ only in a pressure pump's status, its flow at most Qtol in both, with the section beyond it at rest;
2. **drooping curve** (§5.6 item 5): a pressure pump whose curve's H₀ rises somewhere on [0, x_last] differs between the two;
3. **the x_mono band** (§5.6 item 6): one solution has a pressure pump ACTIVE and the other MIN_SPEED, with Q_active/s_min > x_mono;
4. **v1's status-rule multiplicity** (TSD §10.4, slice 1's test): with every pressure pump fixed at its speed in each solution and searched over running and closed, the same solutions are found.

In particular a pressure pump at max_speed with flow in one solution and held at no flow in the other (PN1), or closed in one and regulating in the other beside another pressure source (PN2), is critical: §5.10 V3, V5 or V6 should have refused it. Excluded pairs are written to `findings/control_multiple_states` with their class, and the counts per class are pinned in TSD §10.4, as slice 1's seven are. A pair in no class is critical: either a guard missed it, or it is a new class, which is a design change reviewed by the owner, not an exclusion added after the results are seen.

**Stats** (`stats.py`) gain the kind `pressure_pump`, with metrics `speed`, `speed_head` and `setpoint_pressure`, final-state counts, each guard exit counted by reason (§5.8, §5.9 over-control and swap, V2–V7) with whether its check confirmed it, and control-search counts per documented class.

**Count gates** (RVG-17; chosen, about twice slice 1's 163 EPANET-compared active pumps, and stated before the full run):
- at least 300 ACTIVE pressure pumps with Q_d > Qtol compared with EPANET through the substitute;
- at least 50 of them on discharge connections with r_ref < 1.5 (the C1 stress);
- at least 30 final states each of max_speed, min_speed, no_flow at s_min and no_flow at s_max;
- the active pumps at zero flow (dead-ended) counted separately, outside the first gate.
The counts are recorded in TSD §10.4.

**Smoke test** (`test_fuzz_smoke.py`): the first 25-seed window from 20,000 that reaches active, max_speed, min_speed, no_flow at s_max, no_flow at s_min and off, with no multiple valid solutions. Classes are pinned, and any cycle seeds go into `CYCLE_CLASSES`.

**Commands** (TSD §10.4):
- `uv run python -m tests.differential.fuzz 20000 23000 --workers 3 --profile pressure_control --out /tmp/fuzzpc`
- `uv run python -m tests.differential.stats /tmp/fuzzpc`
- `uv run python -m tests.differential.state_search SEED --profile pressure_control --controls`

### 9.6 Metamorphic tests (`tests/unit/test_pressure_control.py`, networks with one valid state)

- **PM1, fixed at the recovered speed.** With the control removed and `speed` = s*, flows and heads equal the controlled solve within 10⁻⁹, and p_d = p_set within ρg·Htol. *Prototype* (V): 3.7·10⁻¹⁶.
- **PM2, at a limit.** Re-solved as the fixed pump at s_max, the result is bit-identical (the same law object). At s_min it is identical.
- **PM3, monotone in the setpoint** (a line with r > 1 and a falling curve). Over 25 setpoints spanning min_speed → active → max_speed:
  - the states come in that order;
  - Q, p_d and the speed do not decrease;
  - reason: dQ/dp_set > 0 for r > 1, and ds*/dp_set = (dH/dp − ∂F/∂Q·dQ/dp)/(∂F/∂s) > 0.
- **PM4, flow–pressure duality.** An active pressure pump with flow Q*, re-solved as a flow pump with Q_set = Q*, gives the same heads and speed within 10⁻⁹, and the flow pump is active.
- **PM5, PRV substitute in our own solver.** The pump at s_max, a short spool, and a PRV holding p_set at z_d give the same flows, and the same EGL past the PRV, within 10⁻⁹. *Prototype* (V): 2.4·10⁻¹² in flow, 7·10⁻¹³ m in EGL.
- **PM6, datum shift.** Every elevation and level shifted by Δz, with gauge setpoints unchanged: EGLs shift by Δz, and flows and speeds are unchanged.
- **PM7, the system curve does not depend on the viewed pump's mode:** fixed, flow or pressure.

### 9.7 Unit tests

- **The rule table** at ±Htol and ±Qtol, with each boundary point kept by both neighbours (`test_status_rules.py`). This includes P0's threshold, and the C1 knee with no cycle.
- **The partition sweep.** E's 72 line cases (`exp10`/`exp11`), run from every start state: one final state per case, with no cycle, equal to the closed-form partition of §5.6, computed by brentq on the line outside the solver.
- **Free-level logic:**
  - `_border_constraints` on each side;
  - `_holding_regions` against brute-force level sampling;
  - the `new_status` replacement of ACTIVE.
- **Fallbacks:**
  - `_check_changes` on pressure pumps;
  - the `_open_bad_valves` order;
  - valve-only sequences unchanged.
- **Speed:** `operating_speed` at a solved flow (Q > 0, Q = 0, −Qtol < Q < 0) against the closed forms; σ0 and σ_dh by side.
- **The guards:**
  - the floating rule (PF1–PF3);
  - over-control at a pressure setpoint (C's FCV exact-match case);
  - the series swap test (PCF13's two-state variant, from V `exp9`);
  - rule V on the J `j5` header network (R2 20.8–21.3 m not converged, 19 m accepted), with r asserted against r = (h_spool′ + h_rest′)/(2c_dQ) on a line, and with 2 m parallel spools if Q1(b);
  - **V3 and V5 on PN1's network** (§5.6 item 1; R1 5 m, PU H₀ = 40 − 500x, s ∈ [0.8, 1], 1 m spool, ideal tee, 50 m of 0.3 m header with an exit, the branch to a plug): at R2 = 31 m (p_set 301,395.9 Pa) and 33 m (321,471.2 Pa), not converged with the "two steady states" message naming the pump at maximum speed and held at no flow at s_min; each started both from the default state and from OPEN (forcing V3's path) (PN1);
  - **V6 on PN2's network** (§5.10): the booster and the PRV at equal setpoints of 25 m of head, not converged from either start; with a K = 2 fitting on the booster's spool (r_spool > 1), converged, unique (PN2);
  - **V5 refuses nothing** where the state is unique: PCF7's and EP4's networks converge at no_flow with the V5 note in the trace;
  - V2's message text byte for byte (PN6);
  - the pinned-set semantics: a rule leaving the set keeps the status, and the unrestricted rules decide a second state;
  - the 422 zone rule if Q1(a).
- **Membership tests for multi-state networks** (§9.2): PVH4; PCF16 B (closed, or active at zero flow, while Q6 is open); VH6's first-draft inputs (closed, active at the unstable root, or open: RVG `rv6_vh6_states.py`'s four parameterisations), each "converged in one of the enumerated valid states, or not converged".
- **Prototype outcomes as C2 tests** (§5.4, RVG-16): each configuration whose outcome §5–§7 quotes from rule set C or E (the §5.9 table, the §6 rows citing C, the §5.7 table, `p3_cv`, `p12_two_cv`, `p15_suction_closed`, `p11_syscurve`, and E's 72-case sweep above), with the expected outcome stated in the test from the quoted result: that final state where `state_search` finds one valid state; otherwise the guard's not-converged report or membership in the valid states. A difference from the quoted outcome is a finding to be explained by the rule-set difference, not a value to be copied from the solver.
- **C1 methods sentence** (§2.8): `test_methods.py` byte for byte; present only with a PRV whose status is `active`.
- **Results:** `setpointAchieved`; the flag details and texts per state.
- **Traces and methods:** notes per state; the conditional methods text; flow-mode and fixed-pump traces byte-identical.
- **Schema:** instances of both modes; the openapi copy check; `VALIDATION_ERROR` without echoed values (`test_schema_rules.py`, `test_flags_audit.py`).

### 9.8 Stress cases (gathered)

- VH1–VH7 (C1);
- PVH1–PVH5;
- the second-state networks (PN1 at R2 31 and 33 m; PN2);
- C1's knee (EGL_d within ±Htol of H_set0, no cycle);
- P0 with a closed-off suction;
- a floating loop;
- a closed pressure pump between two sections (the union);
- the Q/s_min > x_mono band (PCF10);
- the header bistability (J `j5`).

### 9.9 Corpus comparisons

- **C1:** `compare "$OUT/before" "$OUT/after" --within-tolerance --ignore methodVersion --ignore trace.methods.methodVersion --ignore 'convergence.*' --ignore trace.methods.sections.0.items.4 --ignore trace.methods.sections.0.items.2`, with the criteria of §2.7: the same ignores as §2.7 lists (RVG-2; the first draft's command left out `convergence.*` and the "This solve" item, which differ in 546 projects). Criterion 2's exact check of item 2 is a separate script over the two dumps (as R's `m1_analyze.py`). Criterion 7: both trees dumped again with every project's solver options overridden (tolerance 10⁻¹³, `max_iterations` 1000), the override applied in a `corpus.py` option added by C0 (`--solver-options tolerance=1e-13,max_iterations=1000`), compared with criterion 7's tolerances.
- **C2, exact mode** (C1 tree against C2 tree): `compare "$OUT/before" "$OUT/after" --ignore methodVersion --ignore trace.methods.methodVersion`.
  - Every project of the C1 corpus is identical. There is no `--ignore-null`, because no result field is added.
  - The new reference cases and `fuzzpc_20000`–`fuzzpc_20999`, added to `corpus.py` with 11-point curves, appear as "missing in A".

### 9.10 Web tests

**Vitest:**
- per-mode drafts: incomplete, invalid, complete;
- switching flow ↔ pressure keeps minSpeed and clears the setpoint;
- no partial control is ever written;
- bounds come from the per-member schema names and `x-ordered-fields`;
- labels and the Control column;
- the pressure `PUMP_SETPOINT_NOT_MET` text in kPa(g), bar(g) and psi(g);
- a round trip of a pressure-controlled project;
- the hydraulic fingerprint changes with the mode or setpoint;
- `fillDefaults` adds nothing to `schema-v1.json`;
- Ajv validates a `oneOf` discriminated fixture of each mode (`validate.ts:47-49`).

**Playwright,** desktop 1280×800 and mobile 390×844, one worker:
1. Set discharge-pressure control and solve.
2. Read the speed, the state, the discharge pressure (equal to the setpoint) and the chart label.
3. Share and reopen: the same results.
4. An unreachable setpoint shows max speed and the info flag.
5. Switch to flow control and back to fixed speed, with undo.
6. On mobile, no horizontal page scroll in the form or the results table.

### 9.11 Gates

Every gate of `docs/prompts/continue-v1.md` §2 runs, plus:
- **C0:** the compare mode's unit tests (`test_harness.py`).
- **C1:** §2.7 (criteria 1–8, criterion 7 at the tight tolerance), and VH1–VH3 shown failing on the C0 tree.
- **C2:**
  - the reference suite with all §9.3–§9.4 cases;
  - the metamorphic and unit tests;
  - all three fuzz profiles: 0 critical, and default and flow_control records unchanged from the C1 baseline;
  - the C2 corpus comparison;
  - Vitest and Playwright;
  - the count gates of §9.5, and every guard exit confirmed by its check;
  - **performance:** the PRD §4.2 solve times on the corpus and on the Crane-tee ladders, with the second-state tests (V1's two inner solves, and V3–V6's pinned outer solves, V5's on every satisfied booster and V6's on every shared zone), measured and recorded in TSD §5.2.

---

## 10. Web changes (`apps/web/src/lib`)

Desktop and mobile share the single-column panel form, so no layout is device-specific.

1. **`components/panel/forms/PumpForm.svelte`** (the Control `SelectField` at 147):
   - The Control select gains "Discharge pressure (variable speed)" (`PUMP_CONTROL_LABELS`, `utils/labels.ts:131-134`).
   - The setpoint field takes the pressure category, gauge, in display units, with bounds from `schemaBounds('DischargePressureControl', 'setpoint')`. Hint: "Static gauge pressure at the pump's discharge port that the drive holds."
   - Switching between Flow and Discharge pressure starts a new draft: minSpeed is carried, the setpoint is not (a different quantity).
   - One undoable edit writes the control once the draft is valid (the precedent at 50-131).
   - The Maximum-speed relabel and its hint are unchanged.
2. **`utils/pump-control.ts`** (16-78):
   - `ControlDraft` gains `mode`;
   - `withDraft`, `draftProblem` and `completedControl` work per mode;
   - `schemaBounds('PumpControl', …)` moves to the member names;
   - `orderedBounds` is unchanged.
3. **`utils/labels.ts`:**
   - `PUMP_CONTROL_MODE_NAMES` (136-137) gains `discharge_pressure: 'Discharge'`;
   - state labels.
4. **`utils/results.ts`:**
   - `pumpStatusLabel` (573) gains "Running (holding discharge pressure)", "Running at maximum speed (pressure below setpoint)" and "Running at minimum speed (pressure above setpoint)";
   - `pumpControlText` (617) gives "Discharge 3.50 bar(g): held" and "Discharge 3.50 bar(g): 3.12 bar(g) at max speed".
5. **`components/results/PumpChart.svelte`:**
   - the label gains "(discharge-pressure control)";
   - the system-curve note says "this pump's control is replaced by a fixed flow; other controlled pumps keep regulating".
6. **`utils/flag-text.ts`** (171): a pressure branch of the `PUMP_SETPOINT_NOT_MET` formatter, in display units, gauge.
7. **`utils/issue-text.ts`:** `PRESSURE_CONTROL_ZONE` (Q1(a)).
8. **Generated types:** `api/{openapi.json,schema.d.ts}`, regenerated by `pnpm gen:types`, never edited by hand.
9. **Migrations and fixtures** only if §4.5 bumps the version.

---

## 11. What changes where

**C0:**
- `apps/api/tests/differential/compare.py` (`--within-tolerance`)
- `apps/api/tests/differential/corpus.py` (`--solver-options`)
- `tests/differential/test_harness.py`

**C1:**
- `services/solver/gga.py`:
  - the coupling block (795-805);
  - the docstrings at 49-56 and 101-110;
  - the comment at 799-801.
- `services/solver/methods.py`: the conditional sentence (189-191), on a PRV whose status is `active`.
- `services/solver/version.py`.
- Tests:
  - `tests/reference/derivations_velocity_head.py` (VH1–VH6, by the reference author);
  - `closed_form.py` and `build_closed_form_cases.py`, and the generated case JSONs;
  - `tests/unit/test_gga.py` (with VH7);
  - `tests/unit/test_methods.py` (the sentence and its condition).
- Docs:
  - TSD §5.2, §5.3, §10.4 (criteria, results, class tables);
  - CLAUDE.md D10;
  - proposal `vfd-pump-modes.md` §4.10, a pointer to §2.10 here.

**C2:**
- **Models:**
  - `models/components.py`: the union;
  - `models/results.py`: `PumpControlResult`;
  - `models/api.py`: docstrings.
- **`services/solver/builder.py`:**
  - `PumpControlData` becomes `FlowControlData | PressureControlData`; the latter holds H_set0, the discharge `PortPipe`, c_d, `active_state`, `min_law`, S_min, S_max and uniqueness;
  - the zone issue (Q1(a)).
- **`services/solver/status.py`:**
  - `pressure_pump_status`, `pump_active_state`;
  - `controlled_pump_status` dispatch;
  - `link_states` (367-396);
  - `_update_controls`: P0 (460-463), the PRV class (464-473), the rule (474-482), re-open targets (513-515);
  - `zero_flow_openings` (637-677), returning targets;
  - `_border_constraints` (712-714);
  - `_Levelled`, `_holding_regions` and `new_status` (766-921);
  - `_check_changes` (1988-2034);
  - `_over_controlled` (2106-2166);
  - the floating rule, the second-state tests V1–V7 and the series swap test at the converged exit (1740);
  - `run_outer_loop(pinned=…)` (1586), pinned to sets of statuses (§5.10);
  - the zone partition built once, for the 422 (Q1(a)) and V6;
  - `initial_controls` (310-344) unchanged (§1.4 item 2, §5.5).
- **`services/solver/gga.py`:** the loose message (543-554).
- **`services/solver/elements.py`:** `OffsetLaw` (Q2(a)).
- **`services/solver/results.py`:** `pump_speed` (566-584), `pump_control_result` (586-663), and dead-headed EGLs (699-708).
- **`services/solver/trace.py`** (924-1288) and **`methods.py`** (121-170).
- **`services/solver/version.py`.**
- **Docstrings only:** `pumps.py`, `flags.py`, `system_curve.py`, `network.py` (42-47).
- **Tests:**
  - by the **reference author** (§9.1; the implementer does not edit these): `tests/reference/` `derivations_pump_pressure.py`, `element_laws.py` (`pressure_pump_state_problem`), `network_check.py` (the active law), `free_levels.py` (the union), `generate_epanet_cases.py`, `closed_form.py` and the generated JSONs; `tests/differential/` `checks.py` (the rules, the guard-exit checks), `state_search.py` (the pins), `epanet_model.py` (the substitute, the r runs) and `classes.py` (the critical classes `a_pressure_multiple`, `a_guard_unjustified`, `a_unstable_active`);
  - by the implementer: `tests/reference/` `test_pump_pressure.py`, `test_floating_sections.py`, `test_system_curves.py` (the test drivers over the reference author's cases); `tests/unit/` `test_pressure_control.py`, `test_status_rules.py`, `test_schema_rules.py`, `test_flags_audit.py`, `test_trace.py`, `test_methods.py`, and `test_released_links.py` if bumped; `tests/differential/` `generator.py`, `stats.py`, `corpus.py`, `test_fuzz_smoke.py`.
- **Web:** §10, plus `tests/pump-control.e2e.ts`.
- **Docs:**
  - CLAUDE.md: a new D12 (slice 2: mode, setpoint, rules, the guards and second-state tests, the x_mono band's path rule that PCF10 relies on, as D11 states it for flow mode, versions); D5's deferred list loses "a discharge pressure (slice 2)";
  - PRD §3.1.2.1;
  - SDD §4.8;
  - TSD §5.3–§5.6, §10.1, §10.4 (the count gates, the guard exits by reason, the documented multiplicity classes with their counts), §12 (a decided item; open items for r ≤ 1 at PRVs, zone approximations, the zero-flow multiplicity, ENERGY_TOL against heads near 10⁹ m, and the slow lag where r_ref ≤ 1 < r_tot ≲ 1.2).

---

## 12. Risks

1. **C1 changes PRV iteration paths** in 924 of 4,120 corpus projects, all with a PRV whose status is `active`. All agree within 7.7·10⁻¹⁰ in flow and 2.9·10⁻⁸ m in head at default settings, and within 8.4·10⁻¹³ in flow at a tolerance of 10⁻¹³ (the same fixed point), but one multiplicity seed changes state (fuzz_1656). A project run with more iterations or a looser tolerance may differ more (measured up to 6·10⁻⁸ in flow at 1,000 iterations, RVG). The full fuzz class tables are re-run (§2.5).
2. **The round-off floor.** `ENERGY_TOL` = 10⁻⁷ m is below one ulp of heads above about 6·10⁸ m. Measured: fuzzfc_10269 took 54 → 111 inner iterations, with the same result. This is pre-existing; a relative energy tolerance would be its own method change.
3. **The free-level logic is the most fuzz-sensitive code in `status.py`.** The pressure pump joins it with union regions. Mitigations: the independent checker with the exact union, `state_search` pins, and the `pressure_control` profile.
4. **Several states can satisfy every rule** (§5.6). Reference cases exist only where enumeration over every status element proves one valid state; elsewhere they are membership tests. Two documented exceptions pin a state by its written path: labels of one physical state at zero flow, and the x_mono band (PCF10), both as in slice 1 (§9.2).
5. **The second-state tests** cost two inner solves per running pressure pump per solve and per curve point (V1), and a pinned outer solve per pump where r ≤ 1 (V3, V4), per satisfied booster with both heads known (V5) and per pump with another pressure source in its zone (V6); this is unmeasured, and a gate. r is local, and each pinned solve follows one path. They introduce one numerical choice, `RESPONSE_TOL`, disclosed in the methods summary. A perturbed solve that fails gives "not converged". C measured that only in a genuinely unstable symmetric pair, but numerical fragility in large networks could produce false not-converged results. The fuzz counts every exit by reason and requires an independent check to confirm it (§9.5); an unconfirmed exit is critical.
6. **`LEVEL_SEARCH_LIMIT`** (4,096) may be reached sooner with union rows. Statuses are then kept for that pass.
7. **PRVs already have the falling-static-pressure multiplicity.** With r < 1, closed, open and active at an unstable forward root can all satisfy the rules (E, V, PN `r3`, RVG `rv6`; §2.3), and v1 reports the state its iteration reaches. Applying the second-state tests to PRVs would change v1 results; it is Later, with its own method version. The C1 reference cases avoid it: VH5 and VH6 are chosen with one valid state (§2.9).
8. **The zone rule (Q1(a)) is a topological approximation** (§5.11). It refuses parallel boosters, which today are modelled better as one pump plus fixed pumps until stations are built.
9. **The EPANET substitute** stands only for active and max_speed. Min speed and no flow rely on SPEED runs and our rules, so those state decisions are proven by the closed-form cases.
10. **Fuzz power.** Slice 1's placement left most controlled pumps dead-ended (TSD §10.4), which in pressure mode is the trivial zero-flow active path. The count gates of §9.5 and the 200-seed sample guard against a profile that rarely exercises the held port with flow. A generator-only proxy (RVG, `rv9_discharge_r.py`) finds 85.7 % of on controlled pumps with a discharge connection that alone loses more than one velocity head; where r ≤ 1, EPANET, which has no velocity heads, still converges, so those seeds are checked by the guard-exit checks rather than by comparison.
11. **The union rename** changes OpenAPI component names and the web's `schemaBounds` call sites. A deployment before C2 makes the schemaVersion bump mandatory, and old links then show the method-version notice twice (1.2.0, then 1.3.0).
12. **User expectations:**
    - the setpoint is at the pump's own port, not at a header transmitter (remote nodes are Later);
    - "no flow at minimum speed" is dead-heading (no sleep, Q4).
13. **Slice-1 limitations carry over:** drooping curves (TSD §12 item 3) and the x_mono band at solve time (§5.6 item 6). Items 4 and 5 are being resolved by the work in progress of §1.4, and the build rebases onto it.
14. **Patent US 8,265,911** (listed active to 2030-11-27) recites tank control nodes, extended periods, fixed-flow updates and batteries. Slice 2 holds the pump's own port in a steady state, with no tank and no battery. US 7,013,248 (a fixed control-node head in the GGA) is listed as expired. This is not a legal reading.
15. **The slow lag where the outlet pipe alone loses at most one velocity head** (r_ref ≤ 1 < r_tot ≲ 1.2; §2.3, PN3). An active PRV, and an active pressure pump, there can end not converged at the default 100 iterations although a valid state exists (measured for a PRV: r_tot ≈ 1.11 not converged, 1.23 converged in 82–90). C1 does not change it. An exact step on the whole response by Sherman–Morrison is a possible later method change, with its own measurement and corpus run.
16. **A path-pinned case.** PCF10 pins ACTIVE in the x_mono band by D11's path rule. A future rule change that alters the path could move it to the other valid state; the case's derivation names both, so that change would show as a deliberate case update, not a silent one.

---

## 13. Questions for the owner

1. **Several pressure-controlled pumps on one pressure zone** (parallel boosters on one header).
   - Options:
     - (a) One per zone. Two or more give `PRESSURE_CONTROL_ZONE` (422), and shared-transmitter stations stay Later.
     - (b) Allow them as independent controllers, each holding its own port, with the second-state tests of §5.10.
     - (c) Allow them, and test for multiplicity at solve time.
   - **Recommend (a).**
   - Why:
     - E measured 2–3 rule-valid states for two parallel pumps on fitting-less spools, including (A, OPEN) pairs and a symmetric, control-unstable active state.
     - C measured a +100 Pa setpoint difference moving the split from 0.0274/0.0274 to 0.0077/0.0453 m³/s.
     - The second-state tests now also look for a closed alternative (V6, added after the review), but they follow one pinned path per pump; with two regulating pumps the alternatives multiply, and no single pinned solve covers them.
     - Bentley requires one VSP per zone. Real booster sets share one transmitter (Later).
     - Removing a 422 later breaks no link (GOALS §3, §6).
   - A booster beside an active PRV or a fixed pump on one zone is allowed under (a): V6 refuses it at solve time where it has two steady states (Q2).
2. **Answers the inputs do not determine at one pressure pump** (§5.10): a static pressure that falls as the flow rises (r ≤ 1), a satisfied booster whose running state also holds, a booster beside another pressure source.
   - Options:
     - (a) The second-state tests V1–V7: not converged when the regulating state has r ≤ 1 (unstable), or when one pinned solve finds a second state that satisfies every rule: the other side of an unstable root where r ≤ 1 (at the other limit, or held at no flow at s_min), the pump at maximum speed for a closed pump at or above its setpoint, and the other side (closed, or running) for a pump sharing its discharge zone with another pump or an active PRV.
     - (a′) As (a), but in place of V6, widen the 422 of §5.11 to count active PRV outlets: a booster and an active PRV on one zone are refused at build time at any setpoint; a booster beside a fixed pump then has no test.
     - (b) Converge, with a new warning flag stating r and that another state may exist.
     - (c) Report the state reached, with a trace note only (as v1 does for PRVs).
   - **Recommend (a).**
   - Why:
     - J reproduced, with today's solver, a single pump into an ideal-tee header whose two limit states both satisfy every rule at flows of 0.041 and 0.022 m³/s.
     - The review measured two more classes, also with today's solver: the pump at maximum speed against the pump held at no flow at s_min (PN1: R2 31 and 33 m, where the active iteration closes the pump and the first draft's test never ran), and a booster beside a PRV at equal setpoints, with r = 10.59 at the booster (PN2).
     - Reporting one of them is an answer the inputs do not determine (GOALS §3: correctness over convergence), the same class D11 reports as not converged for over-control.
     - (a) refuses only where a second state, or an unstable regulating state, is shown, and the derivations of §5.10 show that V5 and V6 refuse nothing where the spool or line loses more than its velocity head. (a′) refuses every booster sharing a zone with an active PRV, at any setpoint, and misses the fixed-pump case.
     - Its cost (one pinned solve per satisfied booster and per shared zone, two inner solves per running pump) is a gate.
3. **A flow control in series with a pressure pump, two valid states** (§5.6 item 3; V measured 4 in 4,000 random lines).
   - Options:
     - (a) Report the state reached (TSD §12 open item).
     - (b) Solve the swapped state once; if it also holds, not converged, naming both and describing both states.
     - (c) Always not converged for such a series pair.
   - **Recommend (b).**
   - Why: which controller saturates depends on controller dynamics the model does not have. (b) refuses only the ambiguous cases, at one pinned solve each. (c) would refuse the unique majority.
4. **Flags of a pressure pump held at no flow because its discharge is at or above the setpoint at minimum speed** (the "satisfied booster", PCF7 and EP4, and the closed-off-discharge variant of §5.4).
   - Options:
     - (a) `PUMP_FLOW_REVERSAL` (invalid), as v1 flags every pump held shut by the system head, plus `PUMP_SETPOINT_NOT_MET` (info) stating the cause.
     - (b) Only `PUMP_SETPOINT_NOT_MET` (info).
   - **Recommend (a).**
   - Why:
     - With no sleep (your answer Q3), the pump really runs dead-headed at s_min, which GOALS §4.6 flags by default.
     - One meaning per condition keeps the flag audit simple, and the message says why.
     - E and C recommend (a); V recommends (b), as the intended control outcome (Bentley's "Off").
     - Revisit with sleep mode.
5. **Acceptance criteria for C1's corpus comparison** (§2.7). C1 moves values at the convergence-error level, so exact identity is impossible for projects with an active-status PRV.
   - Options:
     - (a) Exact identity, the methods summary included, for every project with no PRV whose status is `active`. The C1 methods sentence exactly where such a PRV exists. With one: flows within 10⁻⁸ of the largest flow, heads within 10⁻⁶ m, pressures within ρg·10⁻⁶ m, speeds within 10⁻⁹. Strings, booleans and counts exact. Each state or count change reviewed by name. And the fixed point proven at a tolerance of 10⁻¹³ (criterion 7).
     - (c) Tighter bounds at default settings, such as 10⁻⁹ in flow and 10⁻⁸ m in head.
   - **Recommend (a).**
   - Why:
     - The default-settings bounds are empirical: the measured worst changes lie 13× (flow) and 35× (heads) inside, and come from the iteration path and 1.1.0's lag error (§2.7; the first draft's derived bound did not hold with warm starts).
     - The fixed point is proven directly: at 10⁻¹³ the two iterations agree within 8.4·10⁻¹³ of the flow on every active-status-PRV project (measured, §2.4).
     - (c) would fail on iteration-path noise: 2.8·10⁻⁸ m measured.
   - The first draft's option (b), "rely on the reference suite and the fuzz alone", is withdrawn: your standing answer is that C1 is measured on the corpus (RVG-15, the part the skeptic upheld).
6. **Zero-flow multiplicity behind a closed downstream check valve** (§5.6 item 4). "Closed" and "active at zero flow, dead-headed" both satisfy every rule; they are one physical state with two labels.
   - Options:
     - (a) Keep v1's semantics: report the state the iteration reaches, documented in TSD §12 and recorded as a documented class in the fuzz (§9.5, class 1).
     - (b) Prefer the regulating state: re-test such a pump with its closed-off discharge held at its setpoint head.
   - **Recommend (a) for slice 2.**
   - Why: it is how v1 treats every zero-flow multiplicity (D9), and it needs no new free-level logic in the most fuzz-sensitive code. (b) belongs with sleep mode, which changes what a satisfied pump is. Until you answer, PCF16 B is a membership test (§9.3).
7. **The slow lag where the discharge pipe alone loses at most one velocity head** (§2.3, §6 row 2; added after the review, PN3). A booster on a short spool without fittings into an ideal tee, then a main with an exit (r_ref ≤ 1 < r_tot ≲ 1.2), can end not converged at the default 100 iterations although its active state exists; more iterations converge it. The same holds for PRVs today, and C1 does not change it.
   - Options:
     - (a) Accept it for slice 2 as a documented limitation (TSD §12, cases VH7 and PVH5), count its not-converged results in the fuzz, and revisit with that count.
     - (b) Before C2, add an exact Newton step on the whole downstream response (a rank-one Sherman–Morrison update with the existing factor) as its own change set, with its own corpus measurement and METHOD_VERSION.
   - **Recommend (a).**
   - Why: the result it gives is honest (not converged, never a wrong state; GOALS §3); (b) is a new solver change in the most numerically delicate code, not yet designed or measured; the fuzz count says whether it matters in practice.
---

### Owner's answers (2026-10-23)

- **Q1:** (c), not the recommendation. Several discharge-pressure pumps may share one pressure zone (parallel boosters on one header); the solve searches for multiple steady states at solve time, more broadly than §5.10's single-pump tests, and reports not converged when it finds a second one. There is no `PRESSURE_CONTROL_ZONE` issue. §5.11 is redesigned for this (owner-answer revision, below).
- **Q2:** (a), the second-state tests V1–V7: not converged where the regulating state is unstable (r ≤ 1) or a pinned solve finds a second state that satisfies every rule.
- **Q3:** (b), solve the swapped state once; if it also holds, not converged, naming and describing both states.
- **Q4:** (a), `PUMP_FLOW_REVERSAL` (invalid) plus `PUMP_SETPOINT_NOT_MET` (info) stating the cause; revisit with sleep mode.
- **Q5:** (a), the measured acceptance criteria of §2.7, with the fixed point proven at tolerance 10⁻¹³.
- **Q6:** (a), v1's semantics: the state the iteration reaches, documented in TSD §12 and recorded as a documented fuzz class.
- **Q7:** (a), accepted for slice 2 as a documented limitation (TSD §12; VH7, PVH5), counted in the fuzz and revisited with that count.

---

## Appendix A. How the three designs were reconciled

| # | Conflict | Decision | Basis |
|---|---|---|---|
| R1 | C1 scope: PRV and PSV (E, V) or the PRV form only (C) | The PRV form only | Measured: the same worst changes, one state change fewer and no PSV stall; no PSV lag defect found (§2.2, §2.4) |
| R2 | C1 threshold: slope > 0 (C, V) or ≥ 10⁻⁶ × slope (E) | 10⁻⁶ × slope | Bounded Schur weights, an existing constant with the same meaning; measured by J (§2.4) |
| R3 | P0 target: always OPEN (V), ≥ H_set0 − Htol (C), ≥ H_set0 + Htol (E) | E's | V's oscillates (measured, C); C's has a boundary cycle (derived) (§5.4) |
| R4 | C1 targets: via S_eff (E) or via EGL_d (C, V) | Via EGL_d, with E's S_eff as the equivalent closed set | Same closed set; the target is only a starting point; the transmitter reads EGL_d (§5.4) |
| R5 | Order at OPEN and MIN_SPEED: X1 first (C) or the closing test first (E, V) | The closing test first | prvstatus order; one fewer wasted iteration (§5.4) |
| R6 | no_flow speed with the discharge closed off: s_max (E, V) or σ0 at H_s + S_eff (C) | C's level, with the speed σ_dh that matches it | v1 dead-headed convention generalised, self-consistent (§5.4) |
| R7 | Both sides in sections: convex S_max (E, V) or exact union (C) | Exact union | Measured: the convex bound lands on another state; "none" is wrong (§5.7) |
| R8 | Closed pump beside a floating section: not converged (E) or existence (C, V) | Existence | v1 consistency; running pumps are not converged in every design (§5.8) |
| R9 | New `controlledValue` result field (C) or none (E, V) | None | Already in `nodeResults`; keeps flow-mode JSON identical (§3.4) |
| R10 | r ≤ 1: zone rule only (E), rule V (C), trace note (V) | Rule V and the zone rule, both as owner questions (Q1, Q2) | Header bistability reproduced by J with today's solver; rule V misses closed-pump alternatives in parallel (§5.10, §5.11) |
| R11 | Over-control at a pressure setpoint: flow-only (E) or generalised (C, V) | Generalised | Measured silent arbitrary speed (C, §5.9) |
| R12 | Flow plus pressure series multiplicity: unmentioned (E), unique (C), two states (V) | Swap test (Q3) | V's closed-form enumeration (4 / 4,000); C's prototype cases were all unique |
| R13 | Fuzz seeds 13,000–15,999 (E) or 20,000–22,999 (C, V) | 20,000–22,999 | Majority; disjoint |
| R14 | C1's methods text: unconditional (E, C) or conditional (V) | Conditional on a PRV | The existing sentence at `methods.py:189-191` is unconditional; a change there would make every project differ |

## Appendix B. Measurements

Every script lives in this session's scratch directory, `…/scratchpad/slice2-design/<label>/`. They were run from `apps/api` with `uv run python`. No measurement wrote a repository file. The working-tree changes that appeared during J's runs belong to the concurrent session of §1.4.
- J's corpus and default-fuzz runs ended before those changes began.
- J's flow_control fuzz imported the solver into its parent process before they began, and its workers are forked from that process.
- J re-ran `j1` and `j5`, and ran the full pytest, in a clean `git archive` copy of `f9d402b`.

- **J (judge):**
  - `judge_patch.py`: the §2.2 code, applied in memory;
  - `j1_prv_spool.py` (§2.1, §2.3);
  - `corpus_judge.py` with `edge-cases/analyze_corpus.py`, `verification/analyze_corpus.py` and `j4_split.py` (§2.4);
  - `fuzz_judge.py` with `verification/compare_fuzz.py` (§2.5);
  - `judgeplugin.py` (§2.6);
  - `j5_header_limits.py` (§5.6).
- **E (exactness):** `exp1`–`exp13`. These include `gga_exact.py` (its C1 variant) and `exp10`/`exp11` (the 72-case prototype and partition).
- **C (edge cases):**
  - `e1*`, `e5` (PRV spools);
  - the corpus variants `corpus/{before,after,after2}`;
  - the prototype tree `proto/` with `p1`–`p17`.
- **V (verification):**
  - `exp1`–`exp9`: PRV lag; WNTR substitute and brentq over ω; the PCF1 prototype; series multiplicity;
  - corpus and fuzz runs of the PRV and PSV variant.
- **PN (physics and numerics review), `review-physics-numerics/`; its skeptic, `skeptic-pn/`** (each reviewer number re-run by the skeptic in J's clean `f9d402b` copy):
  - `r1_open_closed.py` (§5.6 item 1, PN1), `r5_active_path.py` (the active path to the reverse root), `r7_pinned_min.py` (the first draft's pinned MIN_SPEED);
  - `r2_prv_tee.py` (§2.3, PN3) and the skeptic's `s1_tee_long.py`;
  - `r3_prv_noexit.py` (§2.3, PN4);
  - `r4_rule_v_proxy.py` (the active PRVs' r on the corpus, PN8);
  - `r6_prv_parallel.py`, `r6b_r.py` (§5.10, PN2).
- **RVG (verification and governance review), `review-verification-governance/`; its skeptic, `skeptic-vg/`:**
  - `rv1_active_split.py` (§2.4, RVG-1), `rv10_lag_error.py` (§2.8, RVG-3);
  - `rv5_pcf10_two_states.py` (§5.6 item 6, RVG-4), `rv6_vh6_states.py`, `rv7_vh5_states.py`, `rv8_vh6_solver.py` (§2.3, §2.9, RVG-5);
  - `rv9_discharge_r.py` (§9.5, RVG-17), `rv12_pcf1_observable.py` (§9.2, RVG-13).
- **R (reviser), `reviser/`**, run in J's clean `f9d402b` copy (`judge/tree/apps/api`, its own `uv` environment):
  - `m5_prv_status_split.py` (§2.2, §2.4: the corpus split by PRV status, crossed with J's comparison);
  - `m1_corpus_methods.py`, `m1_analyze.py` (§2.4: the corpus with the §2.2 code and the §2.8 sentence; 2 workers, 764 s);
  - `m2_tight.py`, `m2_analyze.py` (§2.4, §2.7 criterion 7: 2,164 projects at tolerance 10⁻¹³, both trees);
  - `m3_vh6_unique.py` (§2.9, VH6's inputs);
  - `m6_tee_300.py` (§2.9, VH7 at 300 iterations; C1 is applied by `r2_prv_tee.py`'s import, which shows today and C1 identical for these cases).

---

## 14. Review findings and their disposition

A two-lens adversarial review (PN: physics and numerics; RVG: verification and governance) raised the findings below. A skeptic re-ran each reviewer's scripts in J's clean `f9d402b` copy and upheld or rejected each finding. The reviser (R) re-checked every upheld finding against the code at `f9d402b` (and the working tree where noted) before changing the design, and re-measured where the fix needed numbers (Appendix B, R).

### 14.1 Upheld findings

| ID | Severity | Finding | Re-checked against | What was done |
|---|---|---|---|---|
| PN1 | major | Rule V compared only the two running limits and ran only with Q_d > Qtol, so it missed (OPEN, no_flow at s_min) where P(Q) falls; the solve would end converged at no_flow. | `status.py` rules as designed; PN's numbers (`r1`, `r5`, `r7`) as reproduced by the skeptic | §5.10 rewritten as the second-state tests with pinned status sets: V3 pins the s_min branch {MIN_SPEED, CLOSED}; new V5 pins OPEN for a closed pump with both heads known, EGL_d ≥ H_set0 and H ≤ S_max + Htol; derivation that V5 refuses nothing where r > 1 (PCF7, EP4). §5.6 item 1 gains the pair and its measurements, and the partition's non-exclusiveness. Unit tests on R2 = 31 and 33 m (§9.7); the pair is critical in the fuzz (§9.5). |
| PN2 | major | A booster and an active PRV on one header at equal setpoints: two rule-valid states, r = 10.59 at the booster, PRV outlet not counted by the zone rule; §2.3 overclaimed. | `prv_status` (`status.py:212-239`); §5.11's zone definition | Fix (b): V6, a pinned solve on the other side (closed if running, regulating if closed) for a pressure pump whose discharge zone holds another pump that is on or an active-status PRV; derivation of the two-state band (1 − r_spool)·c_dQ², so V6 refuses nothing with r_spool > 1; PCF14 proves its setpoint outside the band. §2.3's sentence corrected; §5.11 limitation restated; unit test on PN2's network. Fix (a), counting PRV outlets in the 422, is put to the owner as Q2(a′). |
| PN3 | minor | C1's test is local to the outlet pipe (r_ref); an exit beyond an ideal tee or a zero-flow Crane run keeps the lag, which needs more than 100 iterations for r_tot ≲ 1.2. | `gga.py:617-631`, `795-805` | §2.3 narrowed (local test; ln(10⁹)/ln(r_tot) iterations; PN's table; the skeptic's and R's runs to convergence); §6 row 2 added; VH7 and PVH5 as documented not-converged unit tests (R `m6`: converged at 300 iterations in 169–182); the changelog names "the outlet connection itself"; Sherman–Morrison recorded as Later (§1.5, risk 15) and put to the owner (Q7). |
| PN4 | minor | VH6 as specified had several rule-valid states (open also valid); §2.3 reported one of them as the answer. | `prv_status` | VH6's inputs changed to a setpoint head below the open state's outlet static head by `STATE_MARGIN`, with the derivation enumerating closed, active and open (R `m3`: closed unique; the solver ends closed today and with C1). §2.3 now says PRVs with r < 1 end in one of several valid states (risk 7). |
| PN5 | minor | PCF10 lies in §5.6 item 6's two-state band, contradicting §9.2's one-state rule. | slice 1's CF21 (`derivations_pump_control.py:770-842`) | Merged with RVG-4: §9.2 names the x_mono band as the one documented two-state exception, pinned by D11's path rule; PCF10's derivation enumerates and checks MIN_SPEED; D12 states the rule; the fuzz's class 3 excludes it from criticality. |
| PN6 | minor | Rule V's ACTIVE message asserted that both limit states satisfy their rules, which nothing checks. | §5.10 as drafted | The V2 message is hedged ("a limit state … may also satisfy its rules"), as the skeptic proposed; V2 itself needs no second state, since the regulating state is unstable. |
| PN8 | minor | The ρ ≤ 0.81 bound behind the flow tolerance assumed a cold start; inner solves are warm-started. | `status.py:1656-1662`; warm starts at `1761, 1801, 1809, 1827, 1833, 1854`; `1604` for curves | Merged with RVG-3: §2.7's flow tolerance is now empirical (the corpus PRVs' r ≥ 2.358; the measured worst 7.73·10⁻¹⁰, path-driven), and the fixed point is proven separately (criterion 7). |
| RVG-1 | blocker | Criterion 1 ("without an active PRV") was false: a PRV that ends open or closed still changes the path. | `initial_controls`, `status.py:335-339` | Criterion 1 and §2.2's bit-identity stated on "no PRV whose status is `active`" (R `m5`: 1,956 projects, all identical; all 924 that differ have one). The methods sentence uses the same condition. |
| RVG-2 | blocker | The C1 methods sentence would make every PRV project differ under exact string comparison; §9.9's command lacked the convergence ignores. | `methods.py:189-191`; compare.py's `--ignore` semantics | Criterion 2: an exact expected-string rule for item 2, which the within-tolerance mode ignores by path; the ignore list written out as paths, the same in §2.7 and §9.9; §2.4 re-measured with the sentence applied (R `m1`: item 2 as expected in all 4,120; nothing else changed; 3,617/503 with the ignores). |
| RVG-3 | major | The 10⁻⁸ flow tolerance was not soundly derived; with more iterations or a looser tolerance the lagged result may differ more; the changelog overstated. | `models/project.py:42-50`; warm starts as PN8 | Criterion 7, the fixed point at tolerance 10⁻¹³ and 1000 iterations, with non-converged projects listed by name (R `m2`: 2,163 of 2,164 converged in both, worst 8.42·10⁻¹³ in flow and 6.92·10⁻¹⁰ m in head; fuzzfc_10070 not converged in either, by design); default-settings tolerances labelled empirical; changelog reworded with RVG's 6·10⁻⁸ at 1,000 iterations; C0 gains `corpus.py --solver-options`. |
| RVG-4 | major | PCF10 has two rule-valid states. | as PN5 | As PN5 (written into §9.2 and D12, kept out of the fuzz's critical rule). |
| RVG-5 | major | VH6 had three rule-valid states (closed, active at the unstable root, open). | as PN4 | As PN4; VH6's first-draft inputs become a membership unit test (§9.7). VH5 is unique (RVG `rv7`), and its derivation now enumerates the three states. |
| RVG-6 | major | The fuzz's criticality rule contradicted the multiplicities the design accepts. | `classes.py`; `state_search.multiple`; TSD §10.4's seven flow_control networks | §9.5 defines criticality before the run: `multiple` pairs at a pressure pump, minus four documented classes with mechanical tests (zero-flow labels, drooping curves, the x_mono band, v1's status-rule multiplicity), written to `findings/control_multiple_states` with counts pinned in TSD §10.4. |
| RVG-7 | major | The fuzz could not tell a justified guard exit from a false refusal, and had no independent r. | `classes.py:38, 62`; `checks.py` | §9.5's guard-exit checks: floating and over-control by port-graph checks; swap and V3–V6 by `state_search` finding two fully determined valid states; V2 by an independent r from EPANET runs at ±δ_EP (δ_EP = 0.01 m for float32 results, band β = 0.05, both derived); unconfirmed exits and a converged ACTIVE pump with r_EP < 1 − β are new critical classes. |
| RVG-8 | major | The design did not say who writes the independent checkers. | `free_levels.py:1-30`; `classes.py`; `state_search.py` calls `solve_project` | §9.1 and §11 assign every checker to the reference author, who never reads `services/`; imports limited to models and tests; a checker that needs the solver calls only `solve_project`; the implementer does not edit them. |
| RVG-10 | minor | The C1 methods sentence described r_tot where the code tests r_ref; D10's wording differed from the 10⁻⁶ threshold. | `gga.py:795-805` | Sentence and D10 text rewritten to the local condition with its threshold, and what the iteration then does. |
| RVG-11 | minor | The case enumeration left out other status elements; PCF15 had no derivation. | slice-1 multiplicities in TSD §10.4 | §9.2 requires every status element's options; PCF12–PCF18 state their enumerations; PCF15 is written out; PCF16 B, two-state under §5.6 item 4 and dependent on Q6, becomes a membership test; label multiplicities at zero flow follow slice 1's dead-end precedent with the path written out. |
| RVG-12 | minor | EP2–EP4 did not prove uniqueness. (The skeptic rejected the sub-claim that EP1's p_d check is tautological: it is on the SPEED = s* run.) | `generate_epanet_cases.py:937-967` (slice 1's limit cases) | EP2–EP4 gain sampled-speed monotonicity, the closed candidate's C1 re-open test from a closed-pump EPANET run, and for EP4 a run at s_max showing X1 fires; noted as not yet measured. EP1 unchanged, with the clarification. |
| RVG-13 | minor | The observable-velocity-head claim used the 0.01 m floor; D6 takes the looser 0.5 %. | `test_reference_cases.py` D6 criteria | §9.2: each derivation computes the wrong-model answers and asserts a 2× D6 failure in at least one checked quantity, with margins per quantity (PCF1: flow 4.53×, RVG `rv12`). |
| RVG-14 | minor | Traceability was not specified for every state; the methods condition was not mode-specific; §8.2 items 3–5 had no text. | `methods.py:121, 125, 163-167` | §8.1: one state-note template per §3.2 row and cause (P0, Q = 0 active, each no_flow cause with its EGL convention) with byte-level tests; §8.2: mode-specific conditions and order (flow-only summaries byte-identical), and the texts of items 3–5 with Htol, `RESPONSE_TOL` and δ; §7's extra sentence dropped, since the existing one is mode-generic. |
| RVG-16 | minor | Measured evidence came from prototypes running other rules, unlabelled. | C's `proto/.../status.py:217-255` (X1 first; σ0 at H_set0 − Htol) | §5.4 defines rule sets C and E and every prototype measurement is labelled; each quoted outcome is a C2 test whose expected outcome is stated now (§9.7). |
| RVG-17 | minor | Fuzz power was unmeasured and the discharge-mix rationale unsupported. | TSD §10.4 slice-1 state counts | §9.5: count gates set before the full run, a 200-seed sample with the first build, placement bias if short; the "rule-V exits" rationale replaced by RVG's measured proxy (85.7 %); risk 10 rewritten. |
| RVG-19 | minor | §1.4 said a pressure pump should start OPEN under `open_valves`, which nothing built or tested. | working tree `status.py:311-345` | Decided: no initial-status change; §1.4 item 2 corrected; §11 lists `initial_controls` as unchanged. |
| RVG-20 | minor | The changelog's "heads within 2.9·10⁻⁸ m" left out the system-curve head change and the gained curve points. | §2.4's own table | Changelog states system-curve heads within 2.6·10⁻¹¹ relative and the 4 gained points. |

### 14.2 Rejected findings (recorded, not applied)

| ID | Finding | Skeptic's reason for rejecting it |
|---|---|---|
| PN7 | C1 passes the combined slope to `jacobian_slopes`, lowering the Jacobian floor of a non-pipe Newton link at the reference pipe's far node, which would reintroduce the weight spread R2 avoids. | Refuted. The floor keeps a link within 10⁶ of its neighbours' Schur weights (`gga.py:101-110`, `188-209`); under C1 the reference pipe's weight is the combined slope, so a floor from it keeps the link within 10⁶ of that pipe's actual weight, and the other port's pipe also enters the sum. No weight lands 10¹² from a neighbour. Positive `extra` terms already feed `jacobian_slopes` the same way (`gga.py:796-805`), and §2.4's corpus run applied the §2.2 code verbatim, so any floor effect is inside the measured results. At most one docstring sentence would be a nicety. |
| RVG-9 | The same physical state is reported two ways (no_flow with `PUMP_FLOW_REVERSAL` behind a closed check valve, against PCF8's active dead end with no flag), and Q4(a) would add `PUMP_SETPOINT_NOT_MET` where §3.3's rule would not. | Not a defect of this design. The duality is v1's semantics, kept on purpose (R6; §5.6 item 4; Q6(a)): a pump held at no flow with its discharge closed off is reported dead-headed at its shutoff head, no_flow, with `PUMP_FLOW_REVERSAL` (`results.py` about 698-773), while a v1 pump against a plug runs at zero flow with no flag. Behind a closed check valve the level is free and the reported EGL is a convention; against a plug EGL_d is fixed. The Q4 sub-claim misreads Q4, which concerns the variant at or above the setpoint at minimum speed, where §3.3 does raise the flag. The case and label issues it touches are handled under RVG-11 and RVG-14. One residual oddity, noted but not this finding's fix: with an interior S_eff, `setpointAchieved` is true on a no_flow pump. |
| RVG-15 | Several owner questions are already answered by standing rules or offer options those rules exclude. | Mostly wrong. Q1(b)/(c) are independent controllers, not the shared-transmitter stations of slice-1 Q9. Q2, Q3, Q4 and Q6 are real choices with v1 precedent on both sides, and the continuation prompt requires asking the owner where a choice is theirs (`continue-v1.md:103`). Only Q5(b) is ruled out by a standing answer (C1 measured on the corpus); that option is withdrawn from Q5, the one part applied. |
| RVG-18 | The versioning rule is applied unevenly: the work in progress adds result-changing entries to the unreleased 1.1.0 while C1 takes its own version. | Not uneven in a way this design controls. The project already amends unreleased versions (`ff9a8f3` added the outer-loop fallback entry to 1.1.0); C1 takes its own version because the owner's standing answer requires it (`continue-v1.md:114`; §1.3); C2's own version satisfies `version.py`'s rule; §1.4 items 3 and 4 already cover both outcomes and re-run §2.7 against the HEAD that C1 is committed on. |

### 14.3 Effect on the owner questions

- Q1: the "why" updated (V6 now looks for closed alternatives, but not across two regulating pumps); recommendation unchanged.
- Q2: widened to the second-state tests (PN1, PN2), with option (a′) from PN2's fix (a); recommendation (a).
- Q5: the criteria revised (RVG-1, RVG-2, RVG-3), the derived bound replaced by the measured basis and the fixed-point proof; option (b) withdrawn.
- Q6: PCF16 B depends on it and is a membership test until it is answered.
- Q7: new (PN3), recommendation (a).
