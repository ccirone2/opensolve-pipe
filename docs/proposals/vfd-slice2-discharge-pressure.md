# Speed-controlled pumps, slice 2: discharge-pressure control

**Status: design, not built.** The owner answered §13's questions on 2026-10-23 (recorded at the end of §13). Q1 was answered (c), not the recommendation, and §5.11 was redesigned for it in an owner-answer revision (§14.4); a review of that revision and the fixes it led to are recorded there too (§14.4.1). After C1's first build the owner answered again on 2026-10-24 (Q7 (b), end of §13): C1 is redesigned in §2.11, with three new questions, Q8–Q10 (Q9 split in two after the redesign's review, §2.11.15), which the owner answered the same day (end of §13: C0b as 1.2.0, C1 as 1.3.0, C2 as 1.4.0). This is the build-ready design of slice 2 of `vfd-pump-modes.md` (§4.10 there sketches it). Where this document and that sketch disagree, this document holds; §2.10 lists the corrections.

Written against `f9d402b` (branch `ccr-efab8cb5-vzm6cg`) by a design workflow: three independent designs, each taking one angle — **E** (solver exactness), **C** (edge cases) and **V** (verification) — then a judge, **J**, who resolved their conflicts against the code and re-measured the points where they disagreed. A two-lens adversarial review followed (physics and numerics, **PN**; verification and governance, **RVG**), each finding checked by a skeptic, and a reviser, **R**, re-checked the upheld findings against the code, re-measured where needed and revised this document; §14 records every finding and what was done. After the owner's answers, Q1 (c) was designed by two more designs, **ZE** (enumeration) and **ZS** (control stability), and a judge, **ZJ**, who merged them (§5.11, §14.4). A review of the merged design followed (**ZR**, each finding checked by a skeptic), and a reviser, **ZF**, re-checked each upheld finding against the code and by experiment and revised this document (§14.4.1). Every file:line reference is to `f9d402b` unless it says "working tree". No repository file was changed to measure anything. Every number marked *measured* names who measured it and with which scratch script (Appendix B). A number without that mark is derived in the text.

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
   - the second-state tests (§5.10), for a pressure pump alone in its pressure zone: a static pressure that falls as the flow rises, where several states satisfy every rule, and a closed pump whose running alternative also holds;
   - rule S (§5.11.4): a regulating state is reported only if the speed-controlled pumps' drives can hold it, the response of their controlled values to their own heads being a P-matrix;
   - the zone search (§5.11.6), where a pressure pump shares its pressure zone with other pumps or pressure-control valves (several pressure pumps on one zone are allowed, owner's answer Q1 (c)): a bounded search for a second steady state, refused when found, flagged `STATE_SEARCH_INCOMPLETE` where a bound leaves candidates unsolved. The bounds are counts (candidates per zone, Newton iterations per candidate network solve and per search), so they do not depend on the project's `maxIterations` or on machine speed (§5.11.6).

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

1. **The flow-setpoint rule.** A flow setpoint at or above s_max·x_mono becomes the topology issue `CONTROLLED_PUMP_SETPOINT`, which resolves TSD §12 open item 5 (now decided item 7) for flow mode. Pressure mode has no build-time analogue, because its flow is solved, so the x_mono band of §5.6 item 6 stays a solve-time property.
2. **The system-curve change.** A cold retry of points without a head, then a start with the control valves open (`run_outer_loop(..., open_valves=True)`). This resolves TSD §12 open item 4 (now decided item 8). Slice 2 builds on it unchanged: `initial_controls(open_valves=True)` opens only control valves, and a speed-controlled pump that is on still starts ACTIVE (working tree `status.py:311-345`). A pressure pump keeps that start, as a flow pump does; slice 2 changes no initial status (§5.5). *(Revised, RVG-19: an earlier draft said a pressure pump "should start at OPEN" there, which no section built or tested.)*
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
- An exact Newton step on the whole downstream response of a held head, where the outlet pipe alone loses at most one velocity head (§2.3, risk 15). *(No longer Later: it is C1, §2.11, after the owner's answer Q7 (b).)*
- Cheaper zone searches (§5.11.12–§5.11.13): symmetry between interchangeable members, ZE's monotone-network certificate and corner pruning; and whether the index sum of §5.11.5 should ever refuse. (The cap on candidate inner solves is built in slice 2, §5.11.6.)
- Broader zone searches, if the fuzz's documented classes 5 and 6 (§9.5) find stable states the search misses: a joint search of zones that change together (two zones joined by a PRV or PSV that ends open), and a second, cold attempt for a candidate whose single attempt did not converge.

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

**Amendment A1 (2026-10-24, after the build's review, findings N1 and N2; not adopted).** The owner chose instead to design a broader fix first (Q7 (b), §13, owner's answers of 2026-10-24); C1's first build, with A1, was not committed (it is kept as a patch for that design). **That design is §2.11, which replaces the rule above and this amendment as C1;** both stay here as the record. The rule above, built as specified, fails where the outlet pipe ends at a free node whose head carries lagged dependences on that pipe's flow. The review measured it and its skeptic reproduced it; this amendment narrows the rule. §2.7's criteria are unchanged and were run again on it (§2.4, the note at its end).
- *Mechanism* (N1). A Crane (or Darby) tee's leg offsets K·c·Q_comb² depend on the combined flow, which is the outlet pipe's own flow when the pipe ends at the tee's combined port; only a leg's own-flow part enters the Jacobian (`gga.py` module docstring), so that dependence stays lagged. In 1.1.0 the lagged velocity-head term (+cQ²) and these lagged offsets partly cancel. With only the velocity-head term exact (combined/slope ≈ 0.40 on the review's network, far above 10⁻⁶), the step overshoots with a multiplier near −1: the outlet pipe's flow alternates with period 2 (0.024, 0.033, 0.025, 0.031 m³/s, ... around 0.0273) and the inner solve never converges, where 1.1.0's converges in 8 iterations. A Newton link between the pipe and the tee (a gate or ball valve) carries the same effect (the skeptic's `gate.json`), so neither lagging the term only where the far node's group has flow-dependent offsets nor adding those offsets' derivative to the slope removes it (the review's two options; the first measured by the skeptic).
- *Measured* (fixer, `c0c1fix/families_summary.txt`; 9,002 networks, the review's families `proj{A,E,F,G,Gsj,H,I}.json` and the skeptic's `mine.json` and `gate.json`: a PRV's outlet pipe into a Crane or ideal tee, directly, through a spool with a K, through a gate or ball valve, two PRVs in parallel into a tee, and spools into a tank; each solved by `d78a8ef`, by the rule as first built and by A1, with the fuzz harness's independent status check and, for Swamee–Jain, its law check). The rule as first built: 85 converged solves end not converged; 31 networks that converge in both reach another state (N2: the review's network into a tee's branch has V active at 5.85·10⁻⁴ m³/s at 1.1.0 and closed at the first build, both states rule-valid, the largest flow moving by 1.1·10⁻³ of itself); 110 that 1.1.0 left not converged converge.
- *The amended rule.* The negative term of a held downstream head enters only where the reference pipe's far end is a fixed or held node too: a reservoir or reference node, or a port that another active PRV or PSV holds (`known_far` in `held_reference`); there it enters with the threshold above, tested on the positive terms' sum. Both of the pipe's end heads then depend on no flow but the pipe's own, so its flow is set by its own energy equation and the step for it is Newton's step for that equation: exact, quadratic near a regular root. The rest of the network sees that flow through the held node's exact coupling (the system is block-triangular there). Elsewhere the term stays lagged, as in 1.1.0.
- *Bit-identity, extended.* An iterate at which no active PRV's outlet pipe ends at such a node runs 1.1.0's floating-point operations. So a project in which no PRV whose status is `active` has its outlet connection end at a reservoir, a reference node, the inlet of an active-status PSV or the outlet of an active-status PRV is bit-identical to 1.1.0 but for the methods sentence (*measured*, the note at the end of §2.4: all 2,125 such projects of the corpus).
- *Measured* (the same 9,002 networks), A1 against `d78a8ef`: 0 converged → not converged, 0 state changes, 60 not converged → converged (all of them spools with an exit fitting into a tank, `projA` 18 and `projE` 42, which the first build converged too); the other 7,615 bit-identical, iteration counts included; no converged result fails the independent checks. Inner iterations 499,577 → 448,221 (first build: 378,212).
- *What A1 gives up.* 50 networks of the 9,002 that the first build converged and 1.1.0 did not stay not converged at the default 100 iterations, as in 1.1.0: two PRVs in parallel, each spool into one tee (48 of the 50 an ideal tee; `projG`, `projGsj`). An active PRV whose outlet pipe ends at a free node keeps 1.1.0's lag whatever that pipe loses, so the documented limitation of §2.3 (r_ref ≤ 1 < r_tot ≲ 1.2, Q7 (a)) widens to every such PRV whose path beyond the port loses only a little more than one velocity head (TSD §12 item 6 in the uncommitted build). Q7's answer covered the narrower class; the wider one is put to the owner, with this amendment.
- *C2.* The held discharge of a regulating discharge-pressure pump takes the same rule: its exact term enters only where its discharge pipe ends at a fixed or held node. §5–§6 and the PVH cases assume the first rule and are to be re-checked when C2 is built.
- *Texts.* In the uncommitted build, the methods sentence (§2.8) and the changelog stated the amended condition (`methods.py`, `version.py`); the `gga.py` docstring and comment, TSD §5.2, §5.3, §10.4 and §12 item 6, and CLAUDE.md D10 follow it.
- *Tests* (§2.9): the review's network (PRV → 10 m pipe → a Crane tee's run, its legs to tanks at 5 and 8 m), the same with a ball valve between, and N2's network into the branch: each converges with V active, keeps its laws, takes 1.1.0's step at every iterate, and every inner solve of its outer loop converges (all fail with the first build). VH1 with an ideal reference node in place of R2 takes the exact term; so does the pipe between a PRV and a PSV.

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
- So where r_ref ≤ 1 < r_tot ≲ 1.2, an active PRV, and in C2 an active pressure pump, can end **not converged** at the default settings, although a valid active state exists (§6 row 2; cases VH7 and PVH5). C1 does not change this. An exact step on the whole response (the held-head term is a rank-one change of the Schur matrix, applicable by Sherman–Morrison with the existing factor at the cost of one extra solve) would; it is a separate method change, needing its own measurement and corpus run, and is Later (§1.5, risk 15). *(Superseded, 2026-10-24: the owner chose that step for C1, Q7 (b). It is designed and measured in §2.11, which also shows that the rank-one update with the existing factor alone makes N1 worse, §2.11.2, so the step includes the branch offsets' flow dependences.)*

**The fixed point is unchanged in both cases.** Only the path and the rate change.

**r_tot ≤ 1: the static pressure at the port falls as the flow rises.**
- For a single held node, the lagged term is a rank-one change of the Jacobian. The iteration's multiplier on that mode is 1/r_tot > 1, so it cannot converge to such a forward root.
- *Measured* (E, `exp2`/`exp3`): a PRV with no exit fitting, L = 0.1 to 5 m (r = 0.017 to 0.85), ends with the PRV **closed** in all 5 cases. The active iteration finds the reverse-flow root instead (Q* = −0.0295 to −0.0073 m³/s).
- *Measured* (V, `exp3`): with no exit fitting, both versions give the same states. The PRV is open for a setpoint above R2's static head and closed below it.
- **These are not unique states** (PN4, RVG-5). With r < 1 a PRV ends in one of several rule-valid states (risk 7). *Measured* (PN, `r3_prv_noexit.py`): with the PRV open, the outlet static head is 2.3334, 2.7586 and 4.5603 m for 0.1, 1 and 5 m spools, and OPEN satisfies prvstatus for every setpoint head between that and R2's 5 m; the default solve reports closed in all 9 runs (setpoints 4.9, 4.5 and 4.0 m), and OPEN is also valid in 7 of them. *Measured* (RVG, `rv6_vh6_states.py`, reference laws and `checks.rule_prv` only): for spools of 0.5, 0.1, 0.5 and 2.0 m at setpoints of 4.5 or 4.8 m, closed, active at the unstable forward root (Q 0.026932, 0.025966, 0.017065 and 0.020258 m³/s) and open (about 0.0598 m³/s) all satisfy the rules; the solver reports closed in all four (`rv8_vh6_solver.py`). CLOSED is the unique valid state only when the setpoint head lies below the open state's static head by a margin (VH6, §2.9).
- **Several held nodes.** Two parallel pressure pumps started symmetrically reach the symmetric, control-unstable active state (E, `exp12`), because the error has no component in the unstable antisymmetric mode. A held head beside another pressure source on one header can also leave two rule-valid states with r > 1 at the pump: a PRV and a booster at equal setpoints, *measured* by PN (`r6_prv_parallel.py`; §5.10, §5.11.8). Under Q1 (c) (§5.11), rule S refuses a reached regulating state whose pumps' response is not a P-matrix, the symmetric pair among them (the lag converges at a regulating state of this class only if the state is holdable, ZS, §5.11.4), and the zone search refuses a zone with a second steady state, a PRV or another pump beside a booster among them; §5.10's tests cover a pressure pump alone in its zone. Neither is a proof for every layout (§5.10, §5.11.13).

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

**Re-measured at the build** (2026-10-24, on `d78a8ef`, 5,140 projects: the corpus above plus the `assigned_flow` profile, its reference cases and VH1–VH6; the build was not committed, so these counts live here and in its measurement files, not in TSD §10.4). With the rule as first built, criteria 1, 2 and 4–7 were met and criterion 3 failed in 22 projects, but the build's review found regressions outside the corpus, which amendment A1 (§2.2) removes. With A1, run again in full: criteria 1, 2 and 4–8 are met. Criterion 3 is not met as stated, in 3 projects, and is put to the owner (2026-10-24): fuzzaf_20323 and fuzzaf_20611, which converge in neither tree, differ only in their `NOT_CONVERGED` flag, which repeats fields of the ignored `convergence.*` (the elements where round-off residuals lie); fuzzfc_10246's five connections that carry at most 1.13·10⁻¹² m³/s at 1.1.0 (below Qtol) carry exactly 0 at 1.2.0, so their flow-regime labels and a nearly closed PRV's K_eff differ (every number present on both sides is within tolerance). One state changes, at zero flow (fuzz_205, PRV9 open → closed, both states valid); the first build's state changes (fuzz_1656, fuzzaf_20055) and fuzzaf_20938's head differences are gone. Worst at default settings: flows 1.1·10⁻⁹ of the largest flow, heads 1.4·10⁻⁷ m; at 10⁻¹³, flows 5.2·10⁻¹². The fuzz: 0 critical in all three profiles; one record changes class (`flow_control` seed 11,194, as in §2.5) and one changes states only (default seed 205). The design's text above is kept as measured on `f9d402b`. **The redesigned C1 (§2.11) has its own measurements on the corpus, at the fixed point and on the fuzz (§2.11.8), and its own handling of criterion 3 (§2.11.10).**

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

Owner question Q5 approves these criteria. For the redesigned C1, §2.11.11 states how they apply and adds criteria 9–12 (the adversarial families, exactness, the code path, performance). §2.11.10 gives criterion 3's investigation and its recommended handling, put to the owner as Q9 (C0b) and Q10 (criterion 3).

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

**As amended (A1, §2.2; built, not committed).** The changelog entry and the methods sentence above state the first rule; the uncommitted build stated the amended condition (`version.py`, `methods.py`). The sentence, pinned by `test_methods.py`, reads:

  > Where an active PRV holds its outlet, the velocity head in its setpoint head enters Newton's step with its flow derivative when the outlet pipe ends at a reservoir, a reference node or a port that another active PRV or PSV holds (so that the pipe's flow is set by its own energy equation) and the pipe's slope (the flow derivative of its own loss, plus that of the velocity head such a valve holds) exceeds the flow derivative of the PRV's velocity head by at least 1e-06 of the slope; otherwise it is taken from the previous iteration, which converges only where the network beyond the port loses more than one velocity head, and slowly near one.

  It states the code's test as it is: the slope is the pipe's own with the positive term of a valve holding its far end, summed first (the review's findings T2 and T3 on the first texts, which named a branch path in series as part of the test and left out that positive term).

**For the redesigned C1** the changelog entry, the methods sentence, the docstrings and the doc changes are in §2.11.13. The texts above are the record of the first rule and of A1.

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

**Under the redesigned C1** (measured in §2.11.8; tests in §2.11.12), the outcomes change:
- VH1–VH3 converge in 5–9 iterations, and VH4 in 7 (JG).
- VH7 converges at the default 100 iterations in 6–8 (ideal or Crane tee, JG) and becomes a case file instead of a documented limitation.
- Cases VH8–VH10 are added.

The rows above record the first rule.

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
- With A1 (§2.2): the review's network (PRV → 10 m pipe → a Crane tee's run, its legs to tanks at 5 and 8 m), the same with a ball valve between, and N2's network into the branch converge with V active, keep their laws, take 1.1.0's step at every iterate (`held_head_slopes` never runs), and every inner solve of their outer loops converges; each of these fails with the first build. VH1 with an ideal reference node in place of R2 takes the exact term, and the two-held-heads test checks that it enters on the sum.

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
   - parallel pressure pumps (§5.11: rule S and the zone search);
   - the slow lag where the outlet pipe alone loses at most one velocity head (§2.3).

### 2.11 C1 as redesigned (owner's answer Q7 (b), 2026-10-24)

**Status: design, measured on prototypes, not built; revised after its review (§2.11.15).** This subsection is C1 from now on. It replaces the rule of §2.2 and its amendment A1, which stay above as the record; where §2.1–§2.10 and this subsection disagree, this subsection holds.

**Status of the open questions (2026-10-24; the design team's note, not the owner's words):**
- The broader fix is designed here: three designs, a judge's merge, the measurements of §2.11.8, and the review's corrections (§2.11.15).
- The one new acceptance class, state changes of class D in the adversarial families (D1 and D2, §2.11.9), is Q8.
- C0b, the two defect fixes found by the investigation of criterion 3, with its own criteria and its METHOD_VERSION, is Q9 (§2.11.10).
- Criterion 3's handling after C0b is Q10 (§2.11.10).
- Neither C0b nor C1 is committed until those answers.

**How it was made.** After the owner's answers of 2026-10-24 (§13), a design workflow wrote three independent designs, each from one angle:
- **RU**, a rank update of the existing step;
- **OC**, exact cross terms of the branch offsets;
- **VA**, verification.

It also ran an investigation of criterion 3 (**C3**). A judge (**JG**) then scored the designs, checked the disputed claims against the code and by experiment, and merged them. A two-lens review of the merge followed (numerics, **RN**; verification, **RV**), each finding checked by a skeptic, and a reviser re-checked the upheld findings against the code and by experiment and revised this subsection (§2.11.15).

**Provenance.** Every script named below lives in `…/scratchpad/c1-redesign/<label>/`, where `…/scratchpad/` is this session's scratch directory, `/tmp/claude-0/-home-user-opensolve-pipe/e3247eb5-2f4d-5fa4-86e2-449a266a4fbe/scratchpad/`, and the labels are `rank-update/`, `offset-cross-terms/`, `verification/`, `crit3/` and `judge/`, and, for the review of §2.11.15, `review-numerics/`, `review-verification/`, `skeptic-numerics/`, `skeptic-verification/` and the reviser's `revise/`. Every measurement:
- ran on a clean `git archive` copy of `d0beec5`, whose solver is `d78a8ef`'s (`git diff d78a8ef d0beec5 -- apps/api/src` is empty);
- printed or recorded the `opensolve_pipe.__file__` of that copy;
- wrote no repository file.

A number marked *measured* names who measured it and with which script. The judge's, the review's and the reviser's large outputs were kept in `/dev/shm` and are not preserved. Their scripts, prototype diffs and the files named below are.

#### 2.11.1 The rule, and how the designs were merged

**The rule.** At an inner iterate where an active PRV passes forward flow in its outlet pipe, the step is Newton's exact step for the whole inner system. The PRVs' velocity-head terms enter with their derivatives, and so does every flow dependence of the branch-leg offsets. Four gates decide whether the step is taken, and they apply to every such PRV together:
- **R:** each PRV's own rule keeps it active at the iterate's heads;
- **L:** no held term would stay lagged: no live active PSV has a negative held term (reverse flow in its reference pipe; added after the review, RN-3);
- **C:** the held-head modes are locally stable for the iteration that is exact in everything but the held terms (for one PRV, the static pressure at the port rises with the flow);
- **T:** the step keeps each PRV's outlet flow forward.

Otherwise the iterate takes 1.1.0's step, operation for operation (§2.11.4). It is built as change set C1, after C0b and before C2, with its own METHOD_VERSION (1.3.0 if C0b takes 1.2.0, as Q9 recommends; §2.11.13).

**Where the parts come from.**

| Part | Source | Basis |
|---|---|---|
| Gates R and T, and their order | VA | Of the three designs' variants, the only one measured with 0 converged → not converged both on the 9,002 networks of the review (§2.2) and on VA's 2,232 new ones (JG reproduced it bit for bit, §2.11.8). A1, measured on both sets after the merge (RV1), also has 0, and no state change; the owner rejected A1 (§13), so it is evidence here, not an option (§2.11.8) |
| Gate L | The review (RN-3) | It makes §2.11.6 item 2 hold by construction for every held term. It changes nothing in the families with PSVs, and changes numbers within criterion 3's tolerance in 13 corpus projects, with no state, convergence or flag change (§2.11.4) |
| The exact Jacobian in the GGA's own variables: subtree incidence, cross terms, negative own slopes, the root port's placement | RU, VA | Finite-difference checks by RU, VA and JG (§2.11.8) |
| Gate C as a spectral test of the held-mode multiplier | RU | It states what the gate tests: the local stability, at the iterate, of the iteration that is exact in everything but the held terms, a physical criterion (for one PRV, r_tot > 1/(1 − τ): the static pressure at the port rises with the flow). It does not test that 1.1.0's iteration would converge there (RN-1, §2.11.4). It rejects negative-stiffness modes, which VA's P-matrix test passes (§2.11.4). Results are identical to VA's test wherever R and T apply (JG) |
| One linear-algebra path: a sparse LU of the whole Newton system | RU's KKT path, VA's block system | Simplest to verify. Measured equal to RU's Woodbury path (RU) and to VA's dense solve (JG). Cost in §2.11.5 |
| Derivative identities (Euler, vectorised against scalar) as unit tests; the finding that the negative own slopes must enter | OC | OC, `tools/check_derivs.py`, `make_proto.py` |
| Criterion 3's findings and their handling | C3 | §2.11.10 |

**Not adopted.**

| Not adopted | From | Why |
|---|---|---|
| The outer-loop amendment S1 | RU | It changes the outer loop of every project. Its by-construction bit-identity becomes only empirical. It is not needed with R and T. JG measured RU's rule with S1 leaving 3 converged solves not converged on VA's new families (§2.11.8) |
| First-appearance stickiness | OC | It keeps per-solve state. The 2 regressions remain without it (OC) |
| The bordered system and the tee-centre parametrisation | OC | A third linear-algebra form. Its head step is quadratic only over two iterations (§2.11.3) |
| The P-matrix form of gate C | VA | See above |
| The Woodbury path | RU | A second path. It is 5× slower at 1,000 components (RU) |
| Counting exact steps in the methods item "This solve" | VA's Q6 | The count is a path detail. The converged equations, which the traces state, do not depend on it |

**Scores.** 5 is best. The rows are in the order the brief weighs them.

| Criterion | RU (EDR + S1) | OC | VA (X-RT) | Chosen |
|---|---|---|---|---|
| Correctness and exactness | 5: exact Newton; spectral gate | 4: exact flow step, head step quadratic over two iterations; its test passes negative-stiffness modes | 4: exact Jacobian; P-matrix test passes negative-stiffness modes (never at an iterate R passes, JG) | 5 |
| Regression safety | 2: 0 → not-converged on the 9,002 only with S1; 3 on the new families (JG); 24 changed states on the 9,002 (12 valve states and 12 other, JG at 10⁻⁶ of the largest flow; RU's own count, 28, is the count at a threshold of 10⁻⁷, which adds 4 G networks at 2.3–3.7·10⁻⁷, and its list `rank-update/results/changed28.txt` has 30 names, adding 2 I networks at 1.05·10⁻⁹; the reviser's check of `j_edrS.json` against `j_off.json`) | 2: 2 converged → not converged; 22 changed results | 4 (5 before the review): 0 / 0 on the 9,002; 8 changes of class D on the new families, 6 of them D2, and 66 more state changes in the review's families (§2.11.9) | 4 (5 before the review), as VA |
| Bit-identity for untouched networks | 3: S1 changes every project's outer loop (identity measured, not constructed) | 5 | 5 | 5 |
| Cost | 4: measured; Woodbury above 64 columns slow; BLAS threads | 3: bordered assembly about 2× per exact iterate (prototype) | 3: dense prototype, build path not timed | 4 (§2.11.5) |
| Verifiability | 4 | 4 | 5: new families, criteria, test plan | 5 |
| Maintenance | 3: two linear-algebra paths and an outer-loop change | 2: stickiness state, bordered system, two parametrisations | 3: three gates | 3: four gates, one linear-algebra path |

A1 has no column: the owner rejected it before the merge. Measured after it (RV1, §2.11.8), it has 0 converged → not converged and 0 state changes on the 9,002 and on the 2,232, and converges 16 networks that the chosen rule does not; the chosen rule converges 52 + 57 that A1 does not.

#### 2.11.2 Why the velocity-head term alone cannot be made exact

RU's one-dimensional model makes the point. Take one PRV and its outlet pipe, with:
- p: the pipe's slope;
- w = 2cQ: the velocity-head slope;
- g: the downstream head's flow derivative that 1.1.0's step sees;
- l: the part 1.1.0 lags, the offsets' dependence on the combined flow.

Then r_tot = (p + g + l)/w, and the error multiplier per iteration is:

| Step | Multiplier |
|---|---|
| 1.1.0 (w and l lagged) | (w − l)/(p + g): the two lags partly cancel |
| The first build, or a rank-one update of the existing factor (w exact, l lagged) | −l/(p + g − w): near −1 on the review's network, the period-2 oscillation of N1 |
| l exact, w lagged | w/(p + g + l) = 1/r_tot |
| Everything exact | 0: Newton, quadratic |

So the literal form of Q7 (b), "a rank-one Sherman–Morrison update with the existing factor", reproduces N1 wherever it applies, and applies more often than the first rule's local test.

Gate C (§2.11.4) bounds the third row, w/(p + g + l) = 1/r_tot, not 1.1.0's multiplier (w − l)/(p + g) (RN-1). The two differ: where l > p + g + w, the third row is below 1 while |w − l| > p + g, so gate C passes and 1.1.0's lag diverges. Gate C is therefore a criterion of physical stability (the static pressure at the port rises with the flow), not of reachability by 1.1.0's iteration (§2.11.6 item 3).

*Measured* on the 9,002 networks against `d78a8ef`, by all three designs, each with its own gate:

| Measured by | Script | Converged → not converged | State changes |
|---|---|---|---|
| RU | `rank-update/sweep.py`, `EDR_MODE=heldonly` | 176 | 40 |
| OC | `offset-cross-terms/make_proto.py`, `OC_VH=global OC_CROSS=none` | 204 | 51 |
| VA | `verification/c1proto.py`, mode `sm0` | 195 | 39 |

The first build had 85 and 31. **The exact step must include the branch offsets' flow dependences.**

#### 2.11.3 The inner residual and its exact Jacobian

The step is exact for the residual **as `gga.py` evaluates it**, in the GGA's own unknowns (RU, VA). OC used the tee centre as the head unknown instead. That gives the same flow step, but its head step converges quadratically only over two iterations, so the build does not use it.

**Unknowns and residuals** (`gga.py:562-1012`):
- q is the flows of the nl Newton links (pipes, valves with K > 0, pumps); h is the heads of the nf free group roots.
- Every link flow is linear in q: Q_all = L·q + constants (`special_flows`, `full_flows`, `gga.py:816-847`). L is:
  - the identity on Newton links;
  - ± the balance of the held node for an active PRV or PSV;
  - the continuity of the subtree T_k below an offset link k (a branch leg, or an ideal valve): Q_k = s_k·Σ_{u∈T_k}(inflow at u from the other links − demand_u), with s_k = −1 where k ends at its child node and +1 otherwise (`GroupLevels.subtree_flows`, `gga.py:335-344`).
- Energy: E_j = h_j(q_j) + (A12·h)_j + κ_{e_j}(q) − κ_{s_j}(q). κ_v is the known part of node v's head (`known_heads`, `gga.py:849-857`):
  - for a node of a free group, κ_v = −shift_v, with shift_v = Σ σ_k·o_k(q) over the offset links k on the path from the root to v; σ_k = +1 where k starts at its parent, so σ_k = −s_k;
  - at a node held by an active PRV or PSV, κ_v = V + c·Q_ref².
- Continuity: C = M21·q − b. It is linear, and M21 (A21 plus the held ports' coupling, `gga.py:801-814`) is already its exact Jacobian.

**Branch offsets** (`HeadOffsetLaw`, `elements.py:194-283`). Each is o = offset + a·Q_r|Q_r|·K(φ), where:
- Q_r is the reference leg's flow and Q_o the leg's own;
- φ = −Q_o/Q_r on a branch path and 1 + Q_o/Q_r on a run path;
- K is the tangent k0 + K′(φ − φ0), held inside [k_min, k_max] (`KTangent`, `elements.py:176-191`).

Its partial derivatives:
- **Own flow:** ∂o/∂Q_o = a·Q_r|Q_r|·K′·∂φ/∂Q_o, with ∂φ/∂Q_o = −1/Q_r on a branch path and +1/Q_r on a run path. This is today's `own_slope`, of either sign.
- **Reference flow:** ∂o/∂Q_r = a·(2|Q_r|·K + Q_r|Q_r|·K′·∂φ/∂Q_r), with ∂φ/∂Q_r = +Q_o/Q_r² on a branch path and −Q_o/Q_r² on a run path. This is the cross term 1.1.0 lags.
- **Special cases:**
  - K′ = 0 where K is held at a bound or Q_r = 0, which is the law as evaluated there;
  - a law without a tangent (a Darby fallback leg, or `k_common`) has its own leg as its reference, and the single derivative 2a|Q|;
  - an ideal leg and a K = 0 valve have no derivative.
- **Euler check.** The flow-dependent part is homogeneous of degree 2, so Q_o·∂o/∂Q_o + Q_r·∂o/∂Q_r = 2(o − offset). *Measured* by OC (`offset-cross-terms/tools/check_derivs.py`) on 2,400 samples of the four `fluids` Crane functions: this identity holds to 1.6·10⁻¹² relative, and central differences agree to 1.3·10⁻⁵, the remainder at the clip bounds.

**The exact Jacobian.** Let G be the subtree incidence, G[k, j] = s_k·([e_j ∈ T_k] − [s_j ∈ T_k]) for offset link k and Newton link j. G[k, j] is both ∂Q_k/∂q_j and ∂(κ_{e_j} − κ_{s_j})/∂o_k, because σ_k = −s_k (RU). Then

  ∂E/∂q = diag(h′) + Gᵀ·(diag(α)·G_own + diag(β)·G_ref) + Σ_i δ_i·e_{r_i}·e_{r_i}ᵀ,  ∂E/∂h = A12,  ∂C/∂q = M21,  ∂C/∂h = 0,

where:
- α_k = ∂o_k/∂Q_own and β_k = ∂o_k/∂Q_ref;
- G_own and G_ref are the rows of G at each law's own and reference legs;
- r_i is the reference pipe of held node i, and δ_i = sign_i·2c_i·Q_ref,i.

Every port node has exactly one connection, a pipe link (`builder.py:560-592`), and its component's internal links. So a group's subtree flows are sums of the flows of the pipes at its ports, and G needs only the Newton links. The build asserts that no group node carries a control-valve link or a demand.

**What the step uses.** 1.1.0's step uses B0 = `jacobian_slopes`(h′ + the positive own slopes on the pipe in series with each leg + the positive held terms) (`gga.py:960-970`). The exact system is

  J_off = B0 − diag(own⁺) + C_L,  C_L = Gᵀ·(diag(α)·G_own + diag(β)·G_ref),  J = J_off + Σ_{i∈P} δ_i·e_{r_i}·e_{r_i}ᵀ,

where P is the set of live active PRVs whose term δ_i is negative, that is, with forward flow in the outlet pipe.

C_L holds three things that 1.1.0's step lacks (RU):
1. The cross terms β: the N1 mechanism.
2. The negative own slopes. Lagged, they made the step up to 31 % short: *measured* by OC (`offset-cross-terms/make_proto.py`, `OC_FDCHECK`, network `H Ls0.05 K1 run_inlet h12 h3 15 La0.5 Lb10`), with own slope −44.7 and a linear rate of 0.30.
3. The root port leg's placement. The root is the first port (`builder.py:553`, `merge_offset_links`), so the root port leg's offset moves the other ports' heads, not the root's.

C_L's nonzero columns are the pipes at the ports of the branches whose offsets depend on the flow (Crane and Darby legs). Ideal tees and ideal valves add none. *Measured* by RU (`rank-update/edr.py`, `STATS["kmax"]`), the number of such columns plus held terms: at most 5 on the 9,002, 33 on a 10-rung Crane ladder, and 1,473 on the 1,000-component ladder.

#### 2.11.4 The step

At each inner iterate, today's code runs unchanged up to `d_inv` (`gga.py:960-970`). The redesigned step is tried only where **P is not empty**, that is, where a live active PRV passes forward flow in its outlet pipe. It is taken only if all four gates pass, for every PRV of P together:

1. **Gate R: the PRV's rule keeps it active.** For every PRV of P, at the iterate's heads, H1 − hml(Q) ≥ H_set − Htol. This is the "stays active" test of `prv_status` (`status.py:256-280`), with:
   - hml the fully open loss at the valve's flow, 0 for an ideal valve;
   - H_set = V + cQ_ref² at the iterate;
   - Htol = `HTOL`.

   It needs no solve.

   **Gate L: no held term stays lagged.** No live active PSV has a negative held term at the iterate, that is, sign·2c·Q_ref < 0 in the `held_reference` loop (`gga.py:963-969`), the term that 1.1.0 and resolution R1 of §2.2 lag through `max(term, 0.0)` (a PSV under reverse flow, a transient its own rule closes). It needs no solve either. Added after the review (RN-3): without it such a term stayed lagged at an accepted iterate, and gate C's M (item 3) does not contain it, so nothing bounded that mode's multiplier. *Measured* (review, `review-numerics/` with the `sparsepsv` instrumented copy, RN_PSV_REJECT=1, reproduced by the skeptic with `skeptic-numerics/make_psv.py`): on 1,152 networks with PSVs (the review's PZ2 144 and PZ3 864, VA's ND 144), no accepted exact step had a live PSV with a negative held term, and the rule with the gate is bit-identical to the rule without it on all 1,152 (`review-numerics/results/psv_reject_cmp.txt`). On ND, 8 iterates with such a PSV reached the exact step and gate T rejected all 8 (the skeptic).

   *Measured* by the reviser on the other sets (`revise/psv_count.py` on a clean `d0beec5` tree with `judge/make_sparse.py` and the skeptic's counter `skeptic-numerics/make_psv.py`, which counts the accepted exact steps at which a live active PSV has a negative held term; `SKN_PSV_REJECT=1` rejects them, which is gate L in results, though not in cost):
   - every family network with a PSV (1,520: the 32 PRV-and-PSV networks of the 9,002, in the first review's `projA.json`, the review's PZ 336, PZ2 144 and PZ3 864, VA's ND 144): 0 such iterates among 2,398 accepted exact steps (`revise/psv_count_families.txt`), so gate L changes nothing there;
   - the corpus, its 1,158 projects with a PRV and a PSV, main solves and system curves: **492 such iterates in 73 projects**, among 5,929 accepted exact steps (`revise/psv_count_corpus.txt`). The review's "zero measured cost" therefore held for the families only;
   - the fuzz seeds the corpus does not hold (`flow_control` 11,000–12,999 and `assigned_flow` 21,000–22,999; 1,000 with a PRV and a PSV): 801 such iterates in 76 seeds (`revise/psv_count_fuzzrest.txt`).

   Gate L can change results only in projects with such an iterate (elsewhere it never fires). The 73 corpus projects were dumped with their system curves in 1.1.0, in the chosen rule and in the chosen rule with gate L (`revise/dump_names.py`), and compared with `compare.py` and §2.7's ignores (`revise/cmp73_*.txt`): with gate L against without it, 60 identical and 13 within tolerance (worst 1.44·10⁻³ of criterion 3's head tolerance and 3.3·10⁻⁴ of its flow tolerance), none different, so no state, convergence or flag changes; against 1.1.0, 49 identical with gate L (45 without), 23 within tolerance and 1 different, `fuzzaf_20050`, by its flag's residual locations only (defect 1 of §2.11.10), as without gate L. On the 148 fuzz seeds where it acts (the corpus's 72 that are fuzz seeds and the 76 above: 47 default, 58 `flow_control`, 43 `assigned_flow`), the fuzz harness was run seed by seed with and without gate L (`revise/fuzz_one.sh`; the fixer's `c0c1fix/tools/fuzzdiff.py`, `revise/fuzzdiff_gateL_148.txt`): the class table is unchanged, 0 critical, self-checks empty, no state differs, and 28 records differ in their numbers only.
2. **Assemble and factor.** Build the whole Newton system with J_off, K_off = [J_off, A12; M21, 0], and factor it with one sparse LU (SuperLU's `splu`, as `_solve_linear` uses). Solve it for:
   - the right-hand side −(E, C), giving x₀;
   - the |P| unit vectors at the reference pipes' energy rows, giving the responses Z, whose entries at those rows are Z_PP.
3. **Gate C: the held-head modes are stable for the iteration.** M = −Z_PP·Δ, with Δ = diag δ_i, is the error multiplier, in held coordinates, of an iteration exact in everything but the held terms (RU). It is not 1.1.0's multiplier, since 1.1.0 lags the offsets' flow dependences too (§2.11.2, RN-1). Every eigenvalue λ of M must have Re λ ≥ 0 and |λ| ≤ 1 − τ, with τ = `JACOBIAN_FLOOR_RELATIVE` = 10⁻⁶.
   - For one PRV, M = 1/r_tot. Here r_tot is the loss of the whole path beyond the port, branch losses included, in velocity heads of the outlet pipe. The test then reads r_tot ≥ 1/(1 − τ): the static pressure at the port rises with the flow, since dP/dQ = 2cQ(r_tot − 1).
   - Re λ ≥ 0 rejects a negative downstream stiffness (r_tot < 0, a static pressure that falls with the flow), which |λ| ≤ 1 − τ alone would pass.
4. **The exact step,** by Sherman–Morrison–Woodbury on the same factor: x = x₀ − Z·(I + Δ·Z_PP)⁻¹·Δ·x₀[P]. This is algebraically the solution of [J, A12; M21, 0]·(dq, dh) = −(E, C).
5. **Gate T: the step keeps the outlet flows forward.** For every PRV of P, (q_r + dq_r)·q_r > 0.
6. **Otherwise** (a gate fails, the factor is singular, or the step is not finite): 1.1.0's step, computed by today's code (`gga.py:970-983`), operation for operation. Gates R and L are tested before the factor, so an iterate where either fails costs what it costs today.

**Why each gate.** Each was measured by removing it (VA, `verification/c1proto.py` modes `x1`, `x1t`, `x1r`; JG, `judge/judge_c1.py`). The counts are converged → not converged / state changes on the 9,002 networks, then on VA's 2,232 new ones (`verification/gen_new.py`):

| Gates | Measured by | 9,002 | 2,232 new |
|---|---|---|---|
| C alone | VA (JG with the spectral C: the same) | 2 / 12, and 12 other tee patterns (JG) | 3 / 20 (JG: 3 / 18) |
| C and T (no R) | VA | 2 / 7 | 3 / 18 |
| C and R (no T) | VA | 0 / 4 | 1 / 8 |
| **R, C and T** | VA, reproduced by JG | **0 / 0** | **0 / 8** |

Gate L was added after these runs. It changes nothing in the families (gate L above): the rows stand for R, L, C and T. In the corpus it changes 13 projects within tolerance (gate L above), so the corpus measurements of §2.11.8 stand within criterion 3's tolerances; the build re-runs everything with all four gates (criteria 1–9).

- **All-or-nothing.** Partial exactness is the N1 mechanism (§2.11.2). OC measured the variant that drops only the weakest held head from a failed joint test: 6 converged → not converged (G family, two parallel PRVs).
- **C** keeps 1.1.0's step where the iteration that is exact in everything but the held terms is not locally stable at the iterate: for one PRV, r_tot < 1/(1 − τ), a static pressure at the port that does not rise with the flow. That is a physical stability criterion of the held state. It is **not** a test that 1.1.0's iteration reaches the root (RN-1): 1.1.0 also lags the offsets, its multiplier in §2.11.2's model is (w − l)/(p + g), and gate C passes where 1.1.0's lag diverges (l > p + g + w). So Newton can converge an inner solve to a root that repels 1.1.0's iteration, and the outer loop, steered by that inner solve, can end in another valid state (class D2, §2.11.9).
  - *Measured* (review, `review-numerics/lag_at_root.py` and `cycle.py`; the skeptic, `skeptic-numerics/lag_growth.py`; the reviser, the same script on its own clean `d0beec5` trees, `revise/lag_growth_NC_h6.txt`): on `NC Ls10.0 branch h6.0 h38.0 Lm0.5 Lb0.5 colebrook`, the first two inner solves are identical in both trees; the third (index 2), with V `FIXED_DOWNSTREAM_HEAD`, takes exact steps and converges in 7 iterations to Q_S = 0.00883123 m³/s. From that root × (1 + 10⁻⁹), 1.1.0's step (`EDR_OFF=1`, the same statuses and K tangents) moves away by a factor of 1.930 per iteration, constant over the first 15 iterations (1.31·10⁻¹⁰ → 1.30·10⁻⁶ m³/s after 15), and does not converge in 1,000 iterations, ending 4.51·10⁻³ m³/s from the root; run from its own warm start with 1,000 iterations, 1.1.0's iterate of S wanders between 0.00275 and 0.0389 m³/s. The same holds on `NC … h12.0 h330.0 … swamee_jain` (root 0.0206347 m³/s; a 10⁻⁹ perturbation ends 0.0113 m³/s away). At the final outer iterate the new root attracts 1.1.0 (it converges from × (1 + 10⁻³) in 20 iterations): the difference lies in the intermediate inner solves.
  - Where C fails, the behaviour is 1.1.0's, including the r_tot ≤ 1 multiplicity of §2.3 (risk 7; VH5, VH6).
  - The spectral form differs from VA's P-matrix test of I − M only where M has an eigenvalue with a negative real part. *Measured* by JG (`judge/judge_c1.py`, counters `neg_eig`, `pm_only`, `spec_only`): with C alone this happened at 27 iterates of the 9,002 networks and 41 of the 2,232, which the P-matrix test passed. With R it happened at none.
  - With R and T the two forms give bit-identical results on all 11,234 networks. On the 2,232 there were 6 iterates where the spectral test passed and the P-matrix test failed; T rejected all 6.
- **R.** Where a PRV's rule rejects its active state at the iterate, the inner solve is iterating on a state the outer loop will change. Newton converges it, where 1.1.0's lag usually fails and its fallback (`_open_bad_valves` on the early check iterate, `CHECK_ITERATIONS`) chooses the next statuses. The two paths then reach different warm starts and, in networks with several valid states, other final states or the outer loop's own oscillation (VA: the I family, at 0.2034 m³/s through a 102 mm line with the inlet far below the setpoint).

  R keeps 1.1.0's evidence for the outer loop wherever the rule rejects the active state.
  - The rule's own form used here, H1 − hml ≥ H_set − Htol, and VA's measured form, H1 ≥ H_set, give bit-identical results on all 11,234 networks (JG).
  - *Measured* gate counts (JG, reproducing VA) on the 9,002: 303,011 iterates with P non-empty; R rejected 255,786, C 1,822 and T 329; 45,074 took the exact step; no factor was singular.
- **T** is a trust guard. A step that drives a PRV's outlet flow to zero or into reverse leaves the regime in which its term is negative, and the PRV's rule closes it on reverse flow. Without T, Newton jumped in the G family (parallel PRVs at equal setpoints) to the root with V1 reversed (VA).

**C2.** A regulating discharge-pressure pump's held discharge joins P. Gate R then uses the pump's own rule ("stays regulating", §5.4), gate C the same multiplier over P, and gate T the pump's flow. Rule S (§5.11.4) remains the verdict on states: gate C is an iteration criterion only. §5–§6 and the PVH cases are re-checked with this step when C2 is built.

#### 2.11.5 Linear algebra and cost

**One path.** Every exact iterate uses one sparse LU of the (nl + nf) saddle system K_off with SuperLU, then 1 + |P| solves and an eigenvalue problem of size |P|. The corpus has at most 7 active-status PRVs in a project (VA). C_L is assembled from index lists precomputed once per inner solve (G and the own and reference rows), with one `np.add.at` per iterate. RU measured that its per-iterate SciPy assembly cost 3.9 ms per call in the prototype.

**Why not the alternatives.**
- **Woodbury on today's Schur factor** (RU, up to 64 columns) reuses today's factor, but adds a dense k × k system and nl × k products. *Measured* by RU (`rank-update/timing.py`): 40.6 s against 8.66 s for the sparse LU at 490 rungs. Its dense products used multithreaded BLAS, 38.2 s against 0.45 s at 50 rungs under load with default threads.
- **OC's bordered Schur system** is a third form.
- RU measured its KKT path against its Woodbury path on the 9,002: the same convergence and states, flows within 8.8·10⁻¹¹ of the largest flow, inner iterations 250,105 → 250,119.

**Cost per exact iterate.** One extra factorization of a matrix about twice the size of today's Schur matrix, plus 1 + |P| solves. Today's factor is computed only where the exact step is rejected after R and L passed. An iterate where R or L fails costs what it costs today. The fraction of iterates that pay is small: on the 9,002, 45,074 + 2,151 of 303,011 iterates with P non-empty (JG).

**Measured** (JG, `judge/timing.py` with `judge/edrj.py` and `judge/make_sparse.py`, best of 3, `OPENBLAS_NUM_THREADS=1`; the machine otherwise idle, load average below 1; files `judge/results/timing_active.txt` and `judge/results/timing.txt`):

| Network (components) | 1.1.0 | Chosen rule (prototype) | Inner iterations | Correction columns (max) |
|---|---|---|---|---|
| Crane ladder, active PRV (100 kPa) on the feed, 10 rungs (26) | 0.083 s | 0.112 s | 38 → 22 | 33 |
| 50 rungs (106) | 0.250 s | 0.292 s | 53 → 30 | 153 |
| 150 rungs (306) | 1.144 s | 1.293 s | 116 → 81 | 453 |
| 300 rungs (606) | 3.326 s | 3.601 s | 165 → 127 | 903 |
| 490 rungs (986) | 7.437 s | 8.536 s (1.15×) | 243 → 191 | 1,473 |
| The same ladders with the PRV open (300 kPa; gate R rejects every iterate) | 0.088–8.999 s | 0.092–9.055 s | identical (43–352) | none taken |
| The 200-tee stub chain of `test_gga.py` with Crane tees and an active PRV after RA | 0.651 s | 0.722 s | 12 → 10 | 401 |
| The same with gate valves on the stubs | 0.723 s | 0.780 s | 12 → 10 | 401 |

In the chain, both trees end with the continuity residual at or below 7.3·10⁻¹⁷ m³/s (0 with the new step) and every plugged stub at exactly 0, so the sparse LU of the saddle system kept its accuracy where the review's ill-conditioned case needs it.

The prototype builds G with Python loops once per inner solve, and C_L with SciPy products at every iterate. Its ratio to 1.1.0 is 1.15× at 986 components and 1.35× at 26 components. The corpus total was 909 s against 1,071 s, but those runs were not controlled: they were dumped with 2 workers while other sweeps ran, so the figure is not a measurement of the build. Criterion 12 is the gate.

**Workers.** The API's worker pool and the Dockerfile pin BLAS to one thread (`OPENBLAS_NUM_THREADS=1`; RU measured an 85× slowdown under load otherwise). The exact path's dense work is the |P| × |P| eigenvalue problem, so the pin matters less than for RU's Woodbury path. It costs nothing.

#### 2.11.6 What is exact, what stays lagged, and why that is safe

**Exact at an accepted iterate:** every flow dependence of the inner residual as evaluated. That covers:
- the held heads of the PRVs of P;
- the branch offsets' dependences on the combined flow and on their own flows, of both signs;
- the held ports' coupling, already exact;
- the fixed flows, which are constants.

**Not a derivative at an accepted iterate:**
- The `jacobian_slopes` floors of non-pipe Newton links (`gga.py:216-238`). This regularization is unchanged and applies as in 1.1.0's step: every non-pipe link's slope is replaced by max(slope, floor), the floor being 10⁻⁶ of the adjacent pipe slopes (at least `JACOBIAN_FLOOR_ABSOLUTE`). It stiffens a valve at Q = 0 or a flat stretch of a pump curve, and it also replaces a negative slope by the positive floor: a fixed-speed pump on the rising stretch of a drooping curve has dh/dQ = −H′ < 0 (`PumpLaw.evaluate` returns the negated curve slope). At such an iterate the step is not Newton's for that link (RN-3).
- A kink of the law: K at a bound of the correlation's range, Q_ref = 0, the laminar–turbulent switch. Here the step uses the derivative of the piece the iterate is on, which is one of the two one-sided derivatives (JG's finite-difference check, §2.11.8).

The outer loop's re-centring of the K tangents and its status changes lie outside the inner system, as before.

**Never part of an accepted step:** the negative held term of a PSV under reverse flow. Gate L takes 1.1.0's step wherever a live active PSV has one, so it is lagged there as in 1.1.0 (a transient that the PSV's own rule closes; resolution R1 of §2.2 stands).

**Lagged as in 1.1.0 (1.1.0's step):**
- every iterate of a project with no PRV whose status is `active`;
- every iterate at which no active PRV passes forward flow in its outlet pipe. There the branch offsets' cross terms and negative own slopes stay lagged, so a Crane network without an active PRV keeps 1.1.0's linear rate. Making them exact everywhere is a separate, later method change, OC's "network-wide" variant. It changes every Crane project: *measured* by OC (`offset-cross-terms/tools/corpus.sh`), it changes 21 of the 22 Crane projects of the corpus without an active PRV;
- every iterate at which a gate fails.

**Why this is safe** (correctness first, GOALS §3):
1. **The fixed point is unchanged.** Each iterate takes either 1.1.0's step or Newton's step for the same residual. The residuals, the stop test (`gga.py:944-950`), the status rules and the outer loop are unchanged. A converged result therefore satisfies the same equations to the same tolerances, and is accepted under the same rules, as in 1.1.0. The step changes the path and the rate, never what counts as a solution.
2. **The N1 overshoot cannot occur.** At an accepted iterate no flow dependence of the residual is lagged, by construction: the step is all-or-nothing over P and over every offset, and gate L excludes the one held term the step would otherwise still lag (a PSV's under reverse flow; a PRV's negative term is in P, and every positive term already enters 1.1.0's slopes). The floors of the first bullet above are not a lag of a flow dependence but a replacement of a slope, the same in both steps. So the first build's mixed map is never used: velocity head exact, offsets lagged, multiplier −(B0 + C_H)⁻¹·C_L. Near a regular root where the gates hold strictly, the iteration is Newton's, quadratic up to the floors. Near a root where gate C fails strictly, it is 1.1.0's.
3. **Gate C targets only held states whose static pressure rises with the flow; it does not keep Newton to 1.1.0's roots.** Gate C admits the exact step only where the iteration that is exact in everything but the held terms is locally stable at the iterate: for one PRV, r_tot > 1/(1 − τ). That is a physical stability criterion of the held state. It is not reachability by 1.1.0, whose multiplier is (w − l)/(p + g) (§2.11.2): gate C passes where 1.1.0's lag diverges, and Newton can then converge an inner solve to a root that 1.1.0's iteration is repelled from, so that the outer loop ends in another valid state (RN-1; class D2, §2.11.9). r_tot ≤ 1 keeps 1.1.0's behaviour (risk 7).
4. **The outer loop sees 1.1.0's evidence where the active state is rejected** (gate R), and Newton's overshoot through zero flow is refused (gate T). These two are path safeguards, not part of Newton's method: they only make 1.1.0's step be chosen more often. Gate R also keeps 16 E-family lines not converged that A1 converges (§2.11.8).
5. **Failure is honest.** A singular factor, a non-finite step or a failed gate gives 1.1.0's step, never an error. A solve that does not converge says so, with 1.1.0's message.

**What is not proven.** Newton has no globalization here beyond R and T:
- That no converged result is invalid is proven, by item 1.
- That no converged solve becomes not converged, and that states change only in the classes named in §2.11.9, is measured, not proven (§2.11.8, §2.11.14).
- That the state reached is one 1.1.0 would reach with more iterations is false in general: class D2 (§2.11.9) is measured where it is not.

#### 2.11.7 Bit-identity

**By construction.** These iterates run 1.1.0's operations in 1.1.0's order:
- an iterate at which P is empty;
- an iterate at which gate R or gate L fails, since gate R reads only the iterate's own heads and gate L only its own flows.

An iterate at which R and L pass but C or T fails, or the factor is singular, also takes 1.1.0's step, computed by today's code after the discarded attempt. The build keeps that code path byte-identical, not refactored (VA). Hence:
- A project with **no PRV whose status is `active`** is bit-identical to 1.1.0 in every solved value, trace, flag and system-curve point, its methods summary included (criterion 1, unchanged). A PRV can be ACTIVE at an iterate only if its status is `active` (§2.2).
- An inner solve none of whose iterates takes the exact step is bit-identical, and so is an outer loop all of whose inner solves are.

**Measured** (§2.11.8):
- all 2,458 corpus projects without an active-status PRV are identical in exact mode;
- 4,818 of the 9,002 networks and 1,509 of the 2,232 are bit-identical, iteration counts included.

#### 2.11.8 Measurements

Unless marked otherwise, every row below was *measured* by JG. Rows and bullets marked with the review's finding ids (RN-…, RV…) were measured after the merge by the review on its own clean `d0beec5` trees with the judge's prototype (`judge/make_sparse.py`, the chosen rule), reproduced by its skeptics, and, where §2.11.15 says so, re-run by the reviser.

**Harness and reproductions** (JG, `judge/sweep.py` and `judge/famcmp2.py`, copies of VA's `sweep.py` and `famcmp.py`, with `judge/make_list.py` and `judge/run_batch.sh`):

| Check | Result |
|---|---|
| The judge's prototype with its step switched off, on the 9,002 | Reproduces the fixer's `d78a8ef` results (`c0c1fix/families_results.tar.gz`, `fam_head.json`) on all 9,002 networks (flows, EGLs, states, convergence and inner iterations; 499,577 = 499,577) |
| The same, on the 2,232 | Reproduces VA's `new_off.json` on all 2,232 |
| The judge's copy of VA's prototype (`judge/judge_c1.py`, `judge/make_proto.py`) | Reproduces VA's `res_x1rt.json` and `new_x1rt.json` bit for bit, with the same gate counts |
| The judge's rebuild of RU's EDR + S1 from its two diffs and `edr.py` on a fresh archive | Equals RU's tree file for file, and reproduces RU's `fam_rkS.json` bit for bit |

**The networks.**
- The 9,002 of the review and its skeptic (§2.2): `c0c1/review-numerics/proj{A,E,F,G,Gsj,H,I}.json`, `c0c1/skeptic-numerics/{mine,gate}.json`.
- VA's 2,232 (`verification/gen_new.py`), in ten families, each with both friction models:
  - three PRVs into a two-tee header;
  - PRVs in series through a tee;
  - a PRV into a Crane tee's branch or run with a second supply;
  - a PRV into a Crane wye;
  - a PRV then a PSV, and a PSV then a PRV;
  - a flow-controlled pump or an FCV beside a PRV;
  - an assigned flow below a PRV;
  - a PRV in a pump loop;
  - no exit beyond a free node, and the VH7 layout.

**Results against `d78a8ef`.** Each network was solved with the fuzz harness's independent status checks, and with its law checks for Swamee–Jain. "Other state" means the same valve states but a flow differing by more than 10⁻⁶ of the largest flow: another tee pattern or root.

| Rule | Measured by | Set | Identical | Conv. → not | Not → conv. | Valve-state changes | Other state | Check failures | Inner iterations |
|---|---|---|---|---|---|---|---|---|---|
| 1.1.0 | fixer | 9,002 | — | — | (128 not conv.) | — | — | 0 | 499,577 |
| First build (§2.2) | fixer | 9,002 | 2,487 | 85 | 110 | 31 | — | 0 | 378,212 |
| A1 | fixer | 9,002 | 7,615 | 0 | 60 | 0 | 0 | 0 | 448,221 |
| A1 | review (RV1), skeptic, reviser | 2,232 | 1,944 | 0 | 0 | 0 | 0 | 0 | 264,424 → 244,124 |
| RU: EDR + S1 | RU, JG | 9,002 | 1,997 | 0 | 114 | 12 | 12 | 0 | 250,105 |
| RU: EDR + S1 | JG | 2,232 | 642 | **3** | 62 | 17 | 0 | 0 | 264,424 → 136,930 |
| OC: proposed | OC | 9,002 | 2,007 | 2 | 115 | 8 | 12 | 0 | 255,631 |
| **Chosen (R, C, T)** | VA, JG | 9,002 | **4,818** | **0** | **96** | **0** | **0** | **0** | **378,066** |
| **Chosen (R, C, T)** | VA, JG | 2,232 | **1,509** | **0** | **57** | **8** | **0** | **0** | 264,424 → **201,486** (VA's dense path and JG's dense copy; JG's sparse path 201,492, the 2 iteration counts below) |
| **Chosen (R, C, T)**, sparse | review (RN-2), reviser | the review's 5,244 | **3,008** | **0** | **120** | **66** | **0** | **0** | 653,801 → 461,967 |
| Both trees at `max_iterations` 1,000 | review (RN-1, RN-2) | 9,002 | 4,803 | 0 | 27 | 0 | 0 | 0 | 1,399,540 → 1,230,904 |
| Both trees at `max_iterations` 1,000 | review (RN-1), skeptic | 2,232 | 1,494 | 0 | 0 | 6 (NC, D2) | 0 | 0 | 867,892 → 799,737 |
| Both trees at `max_iterations` 1,000 | review, reviser | TD, NZ2, TT of the 5,244 (1,168) | 328 | 0 | 0 | 0 | 0 | 0 | 484,498 → 397,697 |
| Both trees at `max_iterations` 1,000 | reviser | the rest of the 5,244 (4,076) | 2,650 | 0 | 24 | 0 | 0 | 0 | 1,863,538 → 1,705,404 |

- **RU's three regressions on the new families** are all NA networks: `NA s(0.05, 0.5, 3.0) none Lh0.3 Lm0.5 crane h(10.0, 10.01, 9.99)` with both friction models, and `NA s(0.05, 0.5, 3.0) none Lh5.0 Lm0.5 crane h(12.0, 10.0, 8.0) colebrook`. They converge at 1.1.0 and under the chosen rule. RU's claim of 0 regressions therefore holds for the 9,002 only.
- **The first build's 85 regressions and the 96 conversions** (corrected after RV7; the reviser re-ran the skeptic's `skeptic-verification/cmp1.py` as `revise/cmp1.py` on the same records). The chosen rule converges all 85 of the first build's regressions, which converged at 1.1.0, in 1.1.0's valve states. Its 96 conversions (A 18, E 26, G 24, Gsj 24, mine 4) are other networks, none of the 85; they include 48 of the 50 networks that the first build converged and A1 gave up.
- **Against A1** (RV1; the review, `review-verification/cmp_a1_chosen.py`, `cmp_off_a1.txt`; the skeptic, `skeptic-verification/cmp1.py`, `cmp2.py`; the reviser, `revise/cmp1.py`, `revise/cmp2.py`). A1 was measured on both sets: on the 9,002 by the fixer (`c0c1fix/families_results.tar.gz`, `fam_fix1.json`), on the 2,232 by the review (regenerated with `verification/gen_new.py`, names equal to `n_off.json`, swept with `judge/sweep.py`, `review-verification/new_a1.json.gz`). It has 0 converged → not converged and 0 state changes on both. On the 9,002 it converges 16 networks that the chosen rule leaves not converged (all E family, below), and the chosen rule converges 52 that A1 does not (G 24, Gsj 24, mine 4); on the 2,232 A1 converges none of 1.1.0's 134 not-converged networks and the chosen rule 57.
- **Not converged in both** (32):
  - 16 E-family lines, all with setpoint 5.01 m against a tank at 5 m and μ = 0.001 Pa·s: 13 with d = 0.03 m and 3 with d = 0.1023 m (`E L0.003 h5.01 rev0 d0.1023 mu0.001 H1500.0`, its `rev1` twin and `E L0.01 h5.01 rev1 d0.1023 mu0.001 H1500.0`). **A1 converges all 16**, in 9–16 inner iterations with V active, and so does the first build; the chosen rule takes 112–116. The cause is gate R, not r_tot: the first exact step leaves an iterate that gate R then rejects for 99 iterations, and 1.1.0's lag, with r_tot − 1 ≈ 3·10⁻⁵, would need about 7·10⁵ (JG, `judge/one.py` on `E|E L0.0001 h5.01 rev0 d0.03 mu0.001 H1500.0`). The review reproduced three of them (`review-verification/e_lines.py`: a clean `d0beec5` archive and the judge's sparse tree not converged at 114, 113 and 112; A1 converged at 12, 11 and 13, V active).
  - 8 G and 8 Gsj networks: two PRVs in parallel. The first build converges 1 G and 1 Gsj of them.

  1.1.0 does not converge any of them.
- **Worst same-state change:** 3.71·10⁻⁷ of the largest flow (`G L10.05 L20.05 h8.0 h8.01 Lm30.0 ex1 crane`: 1.1.0's own lag error), and 1.67·10⁻⁶ m in EGL.

**The sparse path against the dense prototype** (JG, `judge/edrj.py`, `judge/make_sparse.py`, `judge/prototype_sparse_gga.diff`):
- on the 9,002, the same convergence, states and inner iterations, with flows within 4.2·10⁻¹³ of the largest;
- on the 2,232, the same convergence and states, 2 iteration counts different, and flows within 2.3·10⁻¹².

**Exactness** (JG, `judge/judge_c1.py` with `C1V_FDCHECK`, and `judge/fd.py`). At every iterate that passed gates R and C, each column of the analytic energy Jacobian was compared with a central difference of the GGA's own residual, rebuilt from its closures with heads fixed and flows varied. The check runs before gate T, so the counts include iterates that T then rejected (RN-3, RV6).

| Set | Networks checked | Iterates checked (R and C passed) | Median relative column error | Iterates above 10⁻⁵ |
|---|---|---|---|---|
| 9,002 (8 per sub-family) | 104 sampled, 43 with an accepted iterate | 386 | 1.5·10⁻⁹ | 52: 13 kinks, 39 finite-difference noise (4 of them in the F family, confirmed by a step sweep) |
| 2,232 (all) | 790 with an accepted iterate | 8,405: 8,195 took the exact step, 210 were rejected by T (from the gate counts of `n_x1rt_sp`) | 5.4·10⁻⁹ | 860 kinks, 308 finite-difference noise, 8 with a PSV in reverse flow, all 8 rejected by T (the skeptic of RV6) and, with gate L, refused before the factor |

How the iterates above 10⁻⁵ were classified:
- **Kink:** one one-sided difference equals the analytic column within 10⁻⁵ and the two one-sided differences disagree. For example, on `G L10.05 L20.05 h8.0 h8.01 Lm0.5 ex0 crane`, with a leg at 3.7·10⁻²⁷ m³/s, the backward difference is −24.39 against an analytic −24.39, and the forward difference −86.24.
- **Finite-difference noise:** central differences over steps of 10⁻⁷ to 10⁻⁴ vary by more than the discrepancy. This happens in the F family's heads of 2,000–8,000 m and in columns of order 10⁻⁵.
- **PSV in reverse flow:** the NDa layout. Its PSV's negative term is lagged by design (R1), and is the whole difference: FD −2,057.8 against an analytic 177.5. These 8 iterates took no exact step; gate L now refuses them before the factor.

`judge/fd.py` first left 13 iterates unexplained: the 8 NDa iterates and 5 that JG reclassified as finite-difference noise by a step sweep whose output was not kept. The skeptic of RV6 re-ran the sweep on those 5 (`skeptic-verification/fd_sweep.py`, output `fd_sweep_out.txt`): over steps of 10⁻⁷ to 10⁻⁴ their errors vary by more than the discrepancy, at links carrying about 0 m³/s. No discrepancy remained unexplained in these sets (a statement about the sets checked, RN-4). RU (`rank-update/fdcheck.py`) and VA (`c1proto.py`, `C1V_FDCHECK`) found the same on their networks: medians 5·10⁻¹⁰ to 8·10⁻⁹ and worst 2.1·10⁻⁶, respectively.

**Local convergence.** Flow change per iterate of the last active inner solve, *measured* by VA (`verification/rate.py`):
- `mine`: 1.8·10⁻⁵, 7.0·10⁻⁹, 1.1·10⁻¹⁵, 0, where 1.1.0's ratio is 0.2 per step;
- `gate`: 1.7·10⁻⁸, 5.4·10⁻¹⁵, 0;
- a PRV line with a 0.5 m exit spool, cold start: 6.4·10⁻³, 3.9·10⁻⁴, 1.3·10⁻⁶, 1.5·10⁻¹¹, 0, where 1.1.0's ratio is 0.91.

**Reference cases** (JG, `judge/vh_check.py`, VA's `vh_check.py` on the judge's trees):

| Case | 1.1.0 | Chosen rule |
|---|---|---|
| VH1 (0.5 m), VH2 (1 m), VH3 (0.05 m) | not converged, 111 inner iterations | converged in 7, 5 and 9 iterations, 1 outer; flows within 9.0·10⁻¹⁷ m³/s and EGLs within 6.4·10⁻¹⁴ m of the case's expected values |
| VH4 (5 m) | 38 iterations | 7 |
| VH5, VH6 | open in 109, closed in 14 | bit-identical |
| VH7, ideal tee, (0.3, 0.3) and (0.5, 0.5) m at 1, 2 and 3 m/s | not converged at 100 iterations (113); at 300, converged in 108–182 with relative error 5.1–9.7·10⁻⁹ | converged in 6–7 iterations at 100, within 1.0·10⁻¹³ relative of the closed form (`brentq` on `line.Line`) |

VH7 with a Crane tee, its branch plugged (JG, `judge/vh_check_model.py` with `VH7_MODEL=crane`): converged active in 7–8 iterations at 100, within 3.4·10⁻¹² relative of the ideal-tee closed form (the Crane run K is 0 at zero branch flow). 1.1.0 is not converged at 100 (326 inner iterations), and at 300 converges in 109–183 with relative error 4.4–8.8·10⁻⁹.

**Corpus.** 5,140 projects: HEAD's 5,134 plus VH1–VH6, with system curves. Both trees were dumped by their own `corpus.py` (JG, `judge/run_corpus.sh`), and compared with `compare.py` using `--group 'Valve type=prv,Status=active'`.
- **Exact mode:** 4,741 identical and 399 different. All 2,458 projects without an active-status PRV are identical; 2,283 of the 2,682 with one are identical.
- **Within tolerance,** with the §2.7 ignores (`methodVersion`, `trace.methods.methodVersion`, `convergence`, `trace.methods.sections.0.items.4` and `.2`): 4,810 identical, 319 within tolerance, 11 different:
  - VH1–VH3: not converged → converged (criterion 5);
  - `fuzz_2197`: PU4 gains curve points, 7 → 11 (criterion 5);
  - six `fuzzaf` projects, not converged in both, differing only in their `NOT_CONVERGED` flag's `maxContinuityResidualAt` or `maxEnergyResidualAt`: `fuzzaf_20050`, `fuzzaf_20415`, `fuzzaf_20650`, `fuzzaf_20661`, `fuzzaf_20756` and `fuzzaf_20846` (§2.11.10);
  - `fuzzfc_10246`: one system-curve head, PU9's point 1, 6,117.667716 against 6,117.667800 m, 1.36× its tolerance of 10⁻⁸ relative. At tolerance 10⁻¹³ and 1,000 iterations both trees give 6,117.667734779023 m (JG, `judge/redump.py`).
- **Worst changes** (JG, `judge/measure.py`, VA's):

  | Quantity | Worst change | Where |
  |---|---|---|
  | Flow | 1.08·10⁻⁹ of the largest flow | `fuzzaf_20328` |
  | Head | 1.37·10⁻⁷ m | |
  | Pressure | 8.2·10⁻⁸ m of head | |
  | Speed | 5.4·10⁻¹⁵ relative | |
  | System-curve head | 1.36·10⁻⁸ relative above 1 m (`fuzzfc_10246`); 3.9·10⁻³ m on a 1.49·10⁸ m point (`fuzz_2745`) | |

  - No state changes.
  - Converged-flag changes: only VH1–VH3. Curve-point changes: only `fuzz_2197`.
  - Inner iterations: 118,722 → 117,975, fewer in 136 projects and more in 9. The largest rise is `fuzzfc_10809`, 44 → 77, with the same states: an intermediate inner solve fails in both trees.
- **A1's three criterion-3 projects:** `fuzzaf_20323` and `fuzzaf_20611` are identical, and `fuzzfc_10246` differs only in the curve point above.

**The fixed point** (criterion 7): both trees dumped in full, system curves included, with `--solver-options tolerance=1e-13,max_iterations=1000` (JG, `judge/tight_corpus.sh`), and compared with `compare.py --within-tolerance --fixed-point`. Results:
- 4,851 identical, 281 within the fixed-point tolerances, 8 different.
- All 2,458 projects without an active-status PRV are identical.
- Worst, relative to criterion 7's tolerances:

  | Quantity | Worst | Where |
  |---|---|---|
  | Flow | 0.82× | `fuzzfc_10144`, T0's inlet |
  | Head | 0.069× | `fuzzfc_10679` |
  | Pressure | 0.069× | `fuzzfc_10679` |
  | Speed | 6.8·10⁻⁵× | |
  | System-curve head | 0.018× | |

  So criterion 7 needs no absolute flow term here: RU and VA had asked for one, from `fuzz_153` and `fuzzfc_10144` on their prototypes.
- No state differs.
- The 8 different:
  - 7 `fuzzaf` projects, not converged in both, that differ only in the `NOT_CONVERGED` flag's residual locations: `fuzzaf_20050`, `fuzzaf_20527`, `fuzzaf_20658`, `fuzzaf_20661`, `fuzzaf_20756`, `fuzzaf_20770` and `fuzzaf_20846` (defect 1 of §2.11.10);
  - VH3 (`ref_prv_velocity_head_exit_spool_0_05m`), which converges only under the new rule. 1.1.0 needs more than 1,000 iterations at r ≈ 1.01.

File: `judge/results/cmp_tight.txt`.

**Differential fuzz,** all three profiles in full (JG, `judge/run_fuzz.sh`, against the `d78a8ef` records of `c0c1/fuzz_results.tar.gz`, with the fixer's `c0c1fix/tools/fuzzdiff.py`):

| Profile | Seeds | Class table | Critical | Self-checks | Same-class record differences | States-only changes |
|---|---|---|---|---|---|---|
| default | 0–2,999 | unchanged | 0 | empty | 155 | none |
| `flow_control` | 10,000–12,999 | unchanged | 0 | empty | 158 | seed 11,075: FCV1, PRV2 and CV3 go from isolated to open, closed and closed, at exactly 0 m³/s (VA measured the same) |
| `assigned_flow` | 20,000–22,999 | unchanged | 0 | empty | 117 | none |

No changed seed is pinned in the smoke tests (0–49, 10,000–10,024, 11,738, 12,703, 12,773, 20,000–20,025, 20,035). VA re-validated the "before" records on seeds 1,650–1,659 with HEAD. Files: `judge/results/fuzzdiff_{default,fc,af}.txt`.

#### 2.11.9 The changed states and their classes

The corpus and the fuzz have **no** state change at nonzero flow: the fuzz's one states-only record (`flow_control` seed 11,075) is at exactly 0 m³/s, criterion 4's class. The 9,002 networks have **none**. At default settings, against `d78a8ef`, VA's 2,232 have **8** and the review's 5,244 have **66** (RN-2); every one passes the independent checks on both sides.

**The classes** (revised after RN-1 and RN-2). A state change in the families is of **class D** if both states pass the independent status and law checks, with each project's own friction model. It is:
- **D1** if 1.1.0 (`d78a8ef`) run with `max_iterations` 1,000 reaches the new rule's default-settings state: the same valve states and flows within criterion 3's flow tolerance (10⁻⁸ of the largest flow). 1.1.0's state at the default 100 iterations was then an artefact of its slow lag and its fallback, and more iterations of 1.1.0 remove it.
- **D2** otherwise: 1.1.0 with 1,000 iterations still ends in its own state. Gate C is not a reachability test (§2.11.4, §2.11.6 item 3), and these are the changes it allows.

A change whose flows agree within that tolerance, an element reported closed on one side and without a result on the other, is a **zero-flow label change**: criterion 4's class, listed, not class D.

**What "both states pass the checks" covers** (the reviser, while re-checking RN-2). The independent status check tests every pump and valve that has a result and both port heads; it skips an element without a result (`tests/differential/checks.py:485-489`: state "isolated", or a port head missing). Such an element is a PRV closed beside a section that v1 isolates (its section without a source, or behind a held zero-flow tee leg), which v1's own free-level rules accept and the checker does not re-test. In 48 of the 62 changes at nonzero flow one side has such a PRV: 1.1.0's side in NA's 2, NC's 6 (every D2 change), 14 TD and 2 TT; both sides in the 24 TD changes where the demand moves to the other PRV. Only NZ2's 12 and PZ3's 2 are checked element by element on both sides (`revise/` count on the dumps of §2.11.15).

The first text of this subsection defined class D by four conditions (VA, `verification/paths.py`, `verification/recheck.py`): both states valid; 1.1.0's path had failed active inner solves; the new path has none; the new active state stable by ±1 Pa re-solves over the setpoint. The review showed conditions 2–4 unsound (RN-2, reproduced by its skeptic with VA's scripts): condition 3 rejects changes with the same mechanism (the NZ2 tank variants and both PZ3 networks, whose cold-start active inner solve fails in the new path too, diverging to 1.95·10³² m³/s in both trees while gate C rejects every iterate), and condition 4 is undefined for a PRV that feeds only assigned demands or whose setpoint lies within 1 Pa of a boundary (r_tot = −5.9·10¹⁰ and +4.1·10¹⁰, the sign by noise, on TD; none on NZ2, where ±1 Pa flips the state). The 1,000-iteration run is free of tolerances of its own and classifies every case found.

**VA's 2,232: 8 changes, in 4 networks of 2 families (NA, NC), each in both friction models:**

| Network | 1.1.0 | Chosen rule | 1.1.0 at 1,000 iterations | Class |
|---|---|---|---|---|
| `NA s(0.05, 0.05, 0.05) k1 Lh5.0 Lm30.0 crane h(10.0, 10.01, 9.99)` | V2 and V3 active, V1 without a result (closed, its section isolated), 524 inner iterations | all three active, 33 | all three active, 291; flows within 1.14·10⁻⁹ of the largest | D1 |
| `NC Ls10.0 branch h6.0 h38.0 Lm0.5 Lb0.5` | V without a result (closed with its leg held), 171 | V active at 0.0029987 m³/s, 38 | V without a result, 1,071 | **D2** |
| `NC Ls10.0 branch h9.0 h315.0 Lm0.5 Lb0.5` | the same, 186 | V active at 0.0078347 m³/s, 45 | the same, 1,086 | **D2** |
| `NC Ls10.0 branch h12.0 h330.0 Lm0.5 Lb0.5` | the same, 191 | V active at 0.0059812 m³/s, 42 | the same, 1,091 | **D2** |

(Flows and counts for Colebrook; the Swamee–Jain twins agree within 0.2 %. *Measured* by the review, RN-1 and RN-2, `review-numerics/results/va_cmp_1000.txt`; the skeptic, `skeptic-numerics/results/nc_head1000_vs_new100.txt`; and the reviser on its own trees, `revise/changes_va8_d1d2.txt`.)

**The D2 networks (NC's 6).** Both states pass the independent checks, 1.1.0's with V unchecked (above: V has no result, closed beside its held branch leg), and the new active state's r_tot is 24.5–55.7 by VA's ±1 Pa re-solves (defined here: V's outlet path ends at tanks). The mechanism is RN-1's (§2.11.4, gate C): the third inner solve takes exact steps and converges to a root that repels 1.1.0's lag, with a growth factor of 1.930 per iteration from 10⁻⁹ (h6/h38); 1.1.0's iterate there wanders between 0.00275 and 0.0389 m³/s for 1,000 iterations, its fallback then closes V with its branch leg held, and it ends there after 1,071 inner iterations. On h12/h330 the root is 0.0206347 m³/s and a 10⁻⁹ perturbation ends 0.0113 m³/s away. At the final statuses the new root attracts 1.1.0 too (from × (1 + 10⁻³) in 20 iterations): the two methods differ in the inner solves that steer the outer loop, not at the final state.

**The review's 5,244: 66 changes, in 4 families** (RN-2; generators `review-numerics/gen_rn.py`, `gen_rn2.py`, `gen_rn3.py`; the review, `review-numerics/results/rn_cmp.txt`, `rn2_cmp.txt`, `rn3_cmp.txt`; reproduced by the reviser on its own clean trees, `revise/rn_cmp_default.txt`: 3,008 identical, 0 converged → not converged, 120 not converged → converged, 0 check failures, inner iterations 653,801 → 461,967):

| Family | Changes | Zero-flow label changes | At nonzero flow |
|---|---|---|---|
| TD: two PRVs in parallel into a Crane tee that feeds only an assigned demand | 46 | 8 (one PRV closed against without a result; flows within 8.1·10⁻¹¹ of the largest) | 38: in 24 the whole demand moves from one PRV to the other (`TD L13.0 L23.0 h8.0,8.5 q0.08 Lm0.5 branch colebrook`: V1 active carrying 0.08 m³/s at 1.1.0, V2 active carrying 0.08 under the new rule); in 14 one PRV active becomes both active |
| TT: two PRVs into one Crane tee (run inlet and branch), the run outlet to an assigned demand | 6 | 4 | 2: one PRV active becomes both active |
| NZ2: a PRV 10⁻⁶ to 10⁻⁴ m above the tank head, through a Crane tee | 12 | 0 | 12: closed → active at 4.8·10⁻⁵ to 2.8·10⁻³ m³/s (Qtol is 10⁻⁸ m³/s) |
| PZ3: a PRV and a PSV at nearly zero flow on one tee | 2 | 0 | 2: the PSV closed → active at 0.036 m³/s |

So 66 changes, 12 of them zero-flow label changes and 54 at nonzero flow. *Measured* by the reviser (`revise/classify.py`, `revise/changes66_d1d2.txt`): with `max_iterations` 1,000, 1.1.0 reaches the new rule's default-settings state in all 66, with flows within 5.95·10⁻⁹ of the largest flow. **All 54 are D1** (the review measured the same; its skeptic on TD and NZ2, `skeptic-numerics/results/README.txt`). The review had given NZ2's new flows as 4.8·10⁻⁵ to 7.0·10⁻⁴ m³/s; the reviser's dump has 2.8·10⁻³ m³/s in the dh 10⁻⁴ tank variants.

**In all** at default settings: 56 changes of class D1 (NA 2, TD 38, TT 2, NZ2 12, PZ3 2), 6 of class D2 (NC), and 12 zero-flow label changes, in 6 families. Accepting D1 and D2 in the adversarial families, each named and checked, is question Q8 (§13).

#### 2.11.10 Criterion 3: the investigation and its handling

The owner did not accept A1's three criterion-3 exceptions before further investigation (§13). C3 investigated them, and the 22 first-build failures (`crit3/`, scripts named there).

**Findings.** None is a C1 regression of a fixed point or a state. They come from three defects that already exist in 1.1.0:

1. **The `NOT_CONVERGED` flag names a location for round-off residuals.** The location is `np.argmax` of residuals that are all within tolerance, or exactly 0, which returns the first node or link (`gga.py:993-994`; the flag is built at `results.py:1122-1137`).
   - `fuzzaf_20323`: 2.08·10⁻¹⁷ m³/s and 3.63·10⁻¹⁵ m at 1.1.0, exactly 0 at A1.
   - `fuzzaf_20611` is the same.
   - All 384 corpus projects that do not converge at 1.1.0 end with both residuals inside the stop tolerances, so every location their flags name is noise (C3, `crit3/resid.py`).
   - In the exit for "keep returning to a failed state", the message describes the failed solve while the flag reports the last solve's residuals.
2. **The energy stop test has a round-off floor.** `ENERGY_TOL` = 10⁻⁷ m is below one unit in the last place of heads above about 6·10⁸ m.
   - At A1, an inner solve of `fuzzfc_10246`, with EGLs up to 7.0·10⁸ m, stuck at 1.19–2.38·10⁻⁷ m for 91 iterations. It was then treated as failed, and the outer loop took another path to the same statuses.
   - *Measured* (C3, `crit3/floor_scan.py`; JG re-read `crit3/results/scan_main_head.json` and `scan_main_a1.json`): on the main solves of 5,134 projects, 54 projects stall at 1.1.0 (2,217 iterations) and 26 inner solves fail there; at A1, 57, 2,539 and 29.
   - With a round-off-aware test in 1.1.0 (`crit3/results/proto_head_fe_vs_head.diff`), the final state of 9 projects changes between valid states: `fuzz_1446`, `fuzz_2522`, `fuzz_586`, `fuzzaf_20131`, `fuzzfc_10302`, `fuzzfc_10535`, `fuzzfc_10660`, `fuzzfc_10775` and `fuzzfc_10931`. The floor decides which of several valid states 1.1.0 reports (C3, `crit3/selfcheck.py`).
3. **Zero-by-continuity reporting covers only dead-end trees.** It does not cover a link into a part with no source: `fuzzfc_10246`'s five links carry 1.13·10⁻¹² m³/s at 1.1.0 where the exact value is 0. 18 converged corpus projects report such a flow, up to 7.15·10⁻¹⁰ of the largest (`fuzz_2258`) (C3, `crit3/bridge_scan.py`).

In addition, criterion 3's head tolerance does not match its flow tolerance on high-resistance paths. On `fuzzaf_20938` (first build), a flow error the stop test allows moves heads by about 4·10⁻⁶ m, and 1.1.0 itself lies 3.98·10⁻⁶ m from its own fixed point (C3, `crit3/vs_tight.py`).

**Under the redesigned rule** (JG, §2.11.8), criterion 3 fails as written in 7 corpus projects:
- the six `NOT_CONVERGED` flag-location projects, which are defect 1;
- `fuzzfc_10246`'s system-curve point, which is the tolerance mismatch above, in system-curve heads. On a 6,117.67 m point at 0.196 L/s, 1.1.0 lies 1.9·10⁻⁵ m and the new rule 6.5·10⁻⁵ m from the common fixed point. Which side of the tolerance the default solve lands on depends on round-off: VA's dense prototype had it within tolerance.

`fuzzaf_20323`, `fuzzaf_20611` and `fuzzfc_10246`'s labels no longer differ. *Measured* (JG, `judge/redump.py`, with C3's flag prototype `crit3/results/proto_head_fl_vs_head.diff` applied to both trees; `judge/results/fl_cmp.txt`): the six flag projects, `fuzzaf_20323` and `fuzzaf_20611` are identical, and only `fuzzfc_10246`'s curve point remains.

**What that measurement does not cover** (RV2). It re-dumped 9 named projects only (8 identical, 1 different), with fix (a) alone. Fix (b) was applied to neither tree of C1's comparison, and the flag projects of the tight run (`fuzzaf_20527`, `20658`, `20770`, `judge/results/cmp_tight.txt`) were not re-dumped. The set of flag projects depends on the solve path, so it cannot be predicted from one run:
- VA's dense prototype: `fuzzaf_20050`, `20135`, `20415`, `20650`, `20756`, `20846`;
- JG's sparse prototype: `fuzzaf_20050`, `20415`, `20650`, `20661`, `20756`, `20846`;
- the tight settings: `fuzzaf_20050`, `20527`, `20658`, `20661`, `20756`, `20770`, `20846`.

Fix (b) changes paths too (C3's self-check: `fuzz_1446` 119 → 49 inner iterations, `fuzz_2522` 107 → 20), so C1's comparison on top of C0b can differ elsewhere. **Criterion 3 under C0b is therefore expected, not measured.** Before it is claimed met, the build dumps the full corpus at default settings and at criterion 7's settings with both C0b fixes in both trees, and reports the result (§2.11.11).

**Recommended handling.**

1. **C0b, a separate change set committed before C1, with its own acceptance criteria (below), its own corpus and fuzz comparison, its own changelog lines and, recommended, its own METHOD_VERSION,** holds the two code fixes. Both trees of C1's comparison then share them. Approving C0b is Q9.

   | Fix | Defect | What it does | Expected effect |
   |---|---|---|---|
   | a. Flag locations (traceability, GOALS §4.2) | 1 | The flag names a residual's location only where the residual exceeds its stop tolerance. The failed-state exit reports the residuals of the solve its message describes | Changes only flags of not-converged results. Since all 384 not-converged corpus projects end inside both stop tolerances (largest ratios 0.81 continuity, 0.60 energy; `crit3/results/resid_all_head.txt`, re-counted by RV3), it removes the location from every one of their flags. Not measured on the corpus |
   | b. Round-off-aware energy test (correctness, GOALS §3) | 2 | \|residual\| ≤ `ENERGY_TOL` + 4ε × the largest of the link's end heads and its loss, as C3 prototyped (`crit3/results/proto_head_fe_vs_head.diff`) | A method change. C3 measured, on the 58 stalling projects of `crit3/stall_names.txt` (main solves only), 9 final states moving between valid states, all at zero flow (below). Its methods text states the test. Proposal §12 risk 2 is closed |

   **The 9 state changes are all at zero flow** (RV3: the review, `review-verification/states_flows.py`; its skeptic, `skeptic-verification/sf_head.txt`, `sf_fe.txt`; *measured* again by the reviser with exact flows, `revise/states_exact.py` on a clean `d0beec5` archive and the same archive with fix (b)'s diff): every element whose state changes carries exactly 0.0 m³/s on each side that reports it, and most changes are between a state and no result (an isolated section). For example `fuzz_1446` FCV4 closed → open at 0, `fuzzfc_10775` PU10 no_flow → running at 0 and FCV6 and PU13 gaining results at 0, `fuzz_2522` CV1, PRV2 and PRV3 losing their results. All 9 converge in both trees, in fewer inner iterations with fix (b) (for example 119 → 49, 107 → 20, 128 → 18). So they fall in criterion 4's class.

   **C0b's own acceptance criteria** (RV3; stated before its build runs, in the form of §2.7). C0b is compared with 1.1.0 (`d0beec5`, or the HEAD it is committed on):
   - **B1. Identity where the stop test's verdict does not change.** Fix (b) changes only the energy stop test, so an inner solve whose every iterate gets the same verdict from both tests runs the same operations. The build counts, with an instrumented run, the iterates whose verdict changes; every project with none is bit-identical in every solved value, trace, flag and system-curve point, apart from the methods sentence of B5 and, in a not-converged result, the flag fields of B2. A project with no changed verdict that differs otherwise blocks.
   - **B2. Flags.** Only `NOT_CONVERGED` flags of not-converged results change, and only in their residual locations and, in the failed-state exit, in the residuals reported.
   - **B3. States and convergence.** States change only at zero flow through the changed element (criterion 4's class), convergence only from not converged to converged, and curve-point counts only upward; each change listed by name and self-checked (criterion 6's form).
   - **B4. The full corpus**, system curves included, at default settings and at criterion 7's settings; at the tight settings every number of a project converged in both within criterion 7's tolerances, and every project not converged in either, or in one, listed by name with its reason.
   - **B5. Methods text.** The sentence that states the energy test, pinned byte for byte (criterion 2's form).
   - **B6. Fuzz.** The three profiles' class tables unchanged, 0 critical, every changed record listed (criterion 8's form).
   - **B7. System-curve stall scan.** C3's `crit3/floor_scan.py` extended to the system-curve solves, before and after: every curve point whose head changes is listed, and none goes from a head to no head.
   - **B8.** The reference suite and the unit tests green (D6).

   C1's comparison then runs with both trees at C0b, and C1's criteria (§2.7, §2.11.11) are measured against C0b, not against 1.1.0.

   **METHOD_VERSION** (RV4). The owner's answer of 2026-10-24 gives C1 "its own design, measurement and METHOD_VERSION". Fix (b) is a method change, so a C0b that shares 1.2.0 with C1 would make 1.2.0 label two different methods between the two commits, and C1's changelog line "projects without a PRV whose status is active are unchanged" would hold only relative to C0b. The recommendation is therefore **C0b as 1.2.0 and C1 as 1.3.0** (C2 then 1.4.0, §1.4 item 3's rule; §1.2, §4.6 and risk 11 follow when the owner answers). Sharing 1.2.0, as the owner's decisions of 2026-10-23 shared 1.1.0 (D11), departs from that answer and is offered only as the alternative (Q9 (b)); with it, C1's changelog line is phrased relative to C0b's lines and 1.2.0's net effect against 1.1.0 is stated (§2.11.13).
2. **Defect 3** is optional and not needed by C1. If it is built, it needs a new trace note (the dead-end note would be wrong for a link into a pump loop). C3 recommends against zeroing flows below Qtol or raising `ZERO_FLOW_RTOL`, since both would hide real small flows.
3. **Criterion 3 stays as written, with one addition for the measured class of numbers at the solver's resolution.** A number outside its default-settings tolerance passes only if both trees agree at criterion 7's tight settings within criterion 7's tolerance. It is listed by name with both default values and the fixed-point value (today: `fuzzfc_10246`). The comparator gains no ignore paths. Fix (a) removes the flag class at the source, and the round-off exclusion of §2.7 already covers labels at round-off flows. The tolerance mismatch is put to the owner as Q10, separately from C0b (Q9), because criterion 3 is the owner's (Q5, and the answer of 2026-10-24). Whether `fuzzfc_10246` is still the only number it covers once C0b is in both trees is expected, not measured (above).

#### 2.11.11 How the §2.7 criteria apply

Criteria 1–8 keep their definitions and are re-run by the build on the HEAD it commits on, after C0b.

| # | Criterion | Applied to the redesigned rule (JG unless stated) |
|---|---|---|
| 1 | Identity without an active-status PRV | 2,458 of 2,458 identical (§2.11.8); by construction (§2.11.7) |
| 2 | Methods sentence | The sentence of §2.11.13, byte for byte, exactly where an active-status PRV exists. Not measurable on the prototypes, whose summaries were not changed |
| 3 | Within tolerance | Without C0b: not met in 7 projects (§2.11.10). With C0b: **expected, not measured** (RV2), to be met except `fuzzfc_10246`'s curve point, which the addition of §2.11.10 item 3 handles (Q10). Fix (a) was re-dumped on 9 named projects only and fix (b) in neither tree; the build dumps the full corpus at default settings and at criterion 7's settings with both C0b fixes in both trees, and reports the result before claiming this criterion |
| 4 | States change only at zero flow | Met: no state change in the corpus |
| 5 | Convergence and curve-point counts change only from not converged to converged | Met: VH1–VH3, and `fuzz_2197`'s points |
| 6 | Named and self-checked | VH1–VH3, `fuzz_2197`, `fuzzfc_10246`, and the fuzz records of §2.11.8 |
| 7 | Fixed point | Every number is within the fixed-point tolerances (worst flow 0.82× in `fuzzfc_10144`, heads 0.069×, speeds 6.8·10⁻⁵×, curve heads 0.018×), with no state difference. Different: 7 `fuzzaf` projects not converged in both, by flag locations only (defect 1; expected to go with C0b's fix (a), not measured: RV2), and VH3, which converges only under the new rule (a criterion-5 change, listed) |
| 8 | Fuzz | Met: class tables unchanged in all three profiles, 0 critical; the one states-only record (`flow_control` seed 11,075, zero flow) is listed with its empty self-check |

New criteria, stated before the build runs:
- **9. Families.** The 9,002 networks, VA's 2,232 and the review's 5,244 (RN-2), against `d78a8ef` (or C0b's HEAD), each set swept twice: at default settings, and with both trees at `max_iterations` 1,000. In both runs: 0 converged → not converged and 0 independent-check failures. At default settings, state changes only of class D (§2.11.9: D1 or D2 by 1.1.0's 1,000-iteration run, within criterion 3's flow tolerance) or zero-flow label changes, each named with its class and checked on both sides, a PRV without a result included (a check of its closed state against the levels its isolated section can take, which `checks.py` skips today); D2 only as Q8 allows. The generators and tools are committed under `tests/differential/held_heads/`: the first review's `gen*.py`, its skeptic's, VA's `gen_new.py`, this review's `gen_rn.py`, `gen_rn2.py`, `gen_rn3.py` and `genlib.py` (the TD, TT, NZ2 and PZ3 layouts among them), `sweep.py`, `famcmp2.py` and the reviser's `classify.py`. A new state change outside these classes, or any regression, blocks.
- **10. Exactness.** The finite-difference test of §2.11.12 (U1, U2).
- **11. Code path.** Bit-identity by code path (U8), gate L included.
- **12. Performance.** Measured controlled, on a quiet runner, with the budgets of §2.11.5: the corpus total within 1.25× of 1.1.0's, the 986-component ladder with an active PRV within 1.5×, and U11.

#### 2.11.12 Tests

**Unit tests** (`tests/unit/test_gga_held.py`, `test_elements.py`):
- **U1. Exact Jacobian.** At every accepted iterate of VH1, VH7 (ideal and Crane), the review's N1 network and its gate and ball variants, N2 (into the branch), a 3-tee Crane ladder fed by a PRV and two PRVs into a Crane tee, the analytic Jacobian equals central differences of the GGA residual within 10⁻⁵ relative per column. At a kink it equals one of the one-sided differences, and the test asserts which.
- **U2. Step.** The SMW step equals a dense solve of the exact system within 10⁻⁹ relative.
- **U3. Derivatives** (OC):
  - `HeadOffsetArrays.reference_slopes` (new) is bit-identical to the scalar `HeadOffsetLaw.reference_slope`;
  - the Euler identity holds within 10⁻¹²;
  - central differences agree away from the clip bounds.
- **U4. Quadratic convergence:** e_{k+1} ≤ 100·e_k² over the last three iterates of VH1, VH7 and N1.
- **U5. Gate C:**
  - at M = 1 − τ ± ε;
  - at r_tot < 1 (the VH5 and VH6 lines);
  - with a constructed negative stiffness (rejected);
  - two PRVs with real and complex eigenvalues.
- **U6. Gate R:** on `I Ls5.0 run_inlet h6.0 h32.0 La0.5 Lb0.5 d30.1023`, the iterates whose PRV fails its rule take 1.1.0's step, and the solve ends at 1.1.0's state, its flows within 10⁻⁸ of the largest flow.
- **U7. Gate T:** on `G L13.0 L23.0 h8.0 h8.0 Lm30.0 ex0 crane`, the reversing step is rejected, and the solve ends in 1.1.0's state, both PRVs active.
- **U8. Code path:**
  - the exact-step function is never called without an active-status PRV (monkeypatched to raise);
  - a gated iterate's arrays equal those of a kept reference copy of 1.1.0's step;
  - a PSV with forward or reverse flow takes 1.1.0's step;
  - gate L: an iterate with a PRV in P and a live active PSV in reverse flow (an NDa or PZ3 network at such an iterate) takes 1.1.0's step, before any factor (RN-3).
- **U9. Order:** two held heads on one pipe give the same step in either `held_reference` order.
- **U10. Inner solves:** every inner solve of the outer loops of N1, N2 and the gate network converges, with exact steps taken.
- **U11. Performance:** the 986-component Crane ladder with an active PRV, and the 200-tee review chain with Crane tees and an active PRV, converge within the budgets of criterion 12, the chain's plugged stubs at exactly 0.
- **U12. Structure:** no group node carries a control-valve link or a demand (the assertion of §2.11.3).
- **U13. Gate C is not reachability (a documented D2 case):** on `NC Ls10.0 branch h6.0 h38.0 Lm0.5 Lb0.5 colebrook`, the third inner solve takes exact steps and converges; from its root × (1 + 10⁻⁹), 1.1.0's step grows the deviation by more than 1.5 per iteration over the first 10 iterations; the project ends with V active under the new rule (D2, §2.11.9).

**Reference cases** (`tests/reference/derivations_velocity_head.py`):
- VH1–VH6 as built. VH1–VH3 now pass; they fail at 1.1.0.
- **VH7** becomes a case file at the default 100 iterations: the ideal tee with its branch plugged, at 1, 2 and 3 m/s, against the closed form (`brentq` on `line.Line`).
- **VH8:** PRV → 10 m pipe → a Crane tee's run → tanks at 5 and 8 m with exits, the review's N1 network. Its independent solution is `brentq` on the network equations, with the `fluids` Crane K at the solved split (`derivations_branches`), to D6's 0.5 %.
- **VH9:** VH8 with a gate valve between the pipe and the tee.
- **VH10:** two PRVs in parallel with exits, only if its derivation shows one valid, stable state.

**Fuzz.** No new profile. The families of criterion 9 are deterministic grids and are run at every C1 and C2 build. The three existing profiles are run under criterion 8.

#### 2.11.13 Texts and METHOD_VERSION

**`version.py`:** C1's own METHOD_VERSION, after C0b's (RV4, §2.11.10): **"1.3.0"**, with C0b as "1.2.0" (Q9 (a), recommended; C2 then becomes 1.4.0). The changelog entry:

> An active PRV holds its outlet at its setpoint head, which includes the velocity head in its outlet pipe. Where an active PRV passes forward flow, Newton's step now includes the flow derivative of that velocity head and of every branch loss's dependence on the flows (before, both were taken from the previous iteration), at each iteration where, for every such PRV, its own rule keeps it active at that iteration's heads, no active PSV passes reverse flow, the network beyond the held ports responds stably (for one PRV, the path beyond its port loses more than one velocity head of the outlet pipe), and the step keeps its outlet flow forward; at every other iteration the step is that of methods 1.1.0 and 1.2.0. An active PRV whose path beyond its port loses only a little more than one velocity head (a short spool with an exit into a tank, or a short spool into a tee and a main) now converges in a few iterations, where it took up to 100 or did not converge, except where the first exact step leaves an iteration at which the PRV's rule rejects its active state (the step is then the previous method's). Both iterations have the same fixed point (corpus at a tolerance of 10⁻¹³: flows within [8.2·10⁻¹²] of each project's largest flow, heads within [7·10⁻¹⁰] m). Compared with 1.2.0, projects without a PRV whose status is active are unchanged. With default settings the corpus of [5,140] projects differs from 1.2.0 by at most [1.1·10⁻⁹] of each project's largest flow, [1.4·10⁻⁷] m in heads and [1.4·10⁻⁸] relative in system-curve heads; solves that did not converge may now converge ([3], all of them reference cases added with this change; none of the [5,134] existing projects), one pump gained four system-curve points, and no state changed; a network with several valid states may end in another of them, including one that the previous method would not reach with more iterations (measured only in adversarial test networks, none in the corpus or the fuzz).

The bracketed numbers are re-measured by the build, against C0b.

**If C0b and C1 share 1.2.0** (Q9 (b), which departs from the owner's "own METHOD_VERSION"): the same entry follows C0b's lines in 1.2.0, with "compared with 1.2.0" and "differs from 1.2.0" read as "compared with C0b's lines above", and 1.2.0's entry ends with its net effect against 1.1.0, measured by the build: projects without a PRV whose status is active changed only by C0b (states only at zero flow, convergence only from not converged to converged, the energy test's methods sentence, and the residual locations in not-converged flags), and the rest within C1's bounds of C0b's results.

**`methods.py`:** one sentence, appended after one space to the Network-solution item (`trace.methods.sections.0.items.2`), only where the project has a PRV whose status is `active`:

> Where an active PRV holds its outlet with forward flow, Newton's step is exact at each iteration where, for every such PRV, its rule keeps it active at that iteration's heads, no active PSV passes reverse flow, the held heads are stable for the iteration (every eigenvalue of the error multiplier of the iteration that takes only the held heads' velocity-head terms from the previous iteration has a nonnegative real part and a modulus of at most 1 − 1e-06; for one PRV, the path beyond its port loses more than one velocity head of its outlet pipe, so that the static pressure at the port rises with the flow), and the step keeps its outlet flow forward: its velocity head and every branch loss's dependence on the flows then enter with their derivatives; otherwise they are taken from the previous iteration, as in method 1.1.0.

- 1e-06 is printed from `JACOBIAN_FLOOR_RELATIVE` with `:g`.
- `test_methods.py` pins the sentence byte for byte. It also pins the sentence's presence on a project with an active-status PRV, and its absence on one whose PRVs are all failed open or closed and on one with only a PSV.
- C2 extends the condition to "or a discharge-pressure pump that is on".

**`gga.py`:**
- The module docstring:
  - the branch-leg paragraph ("Only the dependence on other links' flows is lagged") gains the exception;
  - the held-node paragraph gains the step.
- The comment at the `held_reference` loop (`gga.py:963-969`), which states gate L.
- `JACOBIAN_FLOOR_RELATIVE`'s docstring gains its use as the gate C threshold.

**No trace change.** The equations of the converged state are unchanged. `schemaVersion` stays 1.

**Docs:**
- TSD §5.2 (held nodes, branch legs) and the §5.3 PRV row.
- TSD §10.4: criteria 1–12, the commands, and the results.
- TSD §12 gains a new decided item for C1's exact step (a new entry: item 6 at HEAD is slice 1's speed control, and the slow-lag item existed only in the uncommitted first build; RV10). Its limitation: the step is the previous method's at iterates where a gate fails. That covers r_tot ≤ 1/(1 − τ) (gate C), an active state the PRV's rule rejects at the iterate (gate R, which also keeps the 16 E-family lines of §2.11.8 not converged where A1 converges them), a live active PSV in reverse flow (gate L), and a step that would reverse an outlet flow (gate T); and that, where several valid states exist, the state reached can differ from the one the previous method reaches even with more iterations (class D2, §2.11.9).
- CLAUDE.md D10's sentence "PRV/PSV flows are coupled exactly in the Newton step (no lag)." gains (RV10): "; where an active PRV passes forward flow, so are its velocity-head term and every branch loss's flow dependence (the exact Newton step of the inner system) at iterations where the PRV's rule keeps it active, no active PSV passes reverse flow, its held head is stable for the iteration (`JACOBIAN_FLOOR_RELATIVE`) and the step keeps its flow forward; elsewhere they are lagged, as in 1.1.0 (METHOD_VERSION 1.3.0, or 1.2.0 if shared with C0b, Q9; proposal vfd-slice2-discharge-pressure.md §2.11)". D7 notes the branch-leg exception.
- Proposal §1.5 (Later) and §12 risk 15 now point here.

#### 2.11.14 Risks and open items

1. **Path safeguards, not a proof.** Gates R, L and T preserve 1.1.0's path. They are not part of Newton's method, and a layout outside the families could show a new change class. Mitigations: criterion 9 at every C1 and C2 build, and the family generators committed.
2. **Multiplicity.** Wherever the step changes the path, the outer loop can reach another rule-valid state. Measured at default settings (§2.11.9): 8 in VA's 2,232 (NA 2 of class D1, NC 6 of class D2) and 66 in the review's 5,244, in 4 more families (54 at nonzero flow, all D1; 12 zero-flow label changes); 0 at nonzero flow in the corpus and the fuzz, and 0 in the 9,002. Gate C does not keep Newton to roots 1.1.0 reaches (RN-1), so a D2 change is a state 1.1.0 does not reach with more iterations. These families are path-dependent in both methods. *Measured* by the reviser (TD, NZ2 and TT, 1,168 networks, both trees at 100 and at 1,000 iterations; `revise/cmp_tdnztt_*.txt`): 1.1.0 itself changes 70 states on TD and NZ2 (58 + 12, as the review's skeptic counted) and 14 on TT between 100 and 1,000 iterations; in 20 more networks (TD 12, TT 8) both methods agree at default settings and both end in another state at 1,000; and at 1,000 iterations the two methods agree on every state of the 1,168 (0 changes, 0 converged → not converged). PRV multiplicity stays undetected in v1 (risk 7).
3. **Residual non-convergence.** 32 networks of the 9,002 stay not converged, as in 1.1.0: the 16 E-family lines, which **A1 and the first build converge** in 9–16 inner iterations, and 16 parallel-PRV networks, 2 of which the first build converges. For the E lines the cause is gate R after the first exact step (§2.11.8), not r_tot. This narrower limitation is documented in TSD §12. A variant that, where gate R fails, takes A1's exact velocity-head term (where the outlet pipe's far end is known) instead of 1.1.0's step could converge them; it is neither designed nor measured, and A1 itself was rejected by the owner (RV1).
4. **Cost.** The KKT factor runs at every accepted iterate. It is timed in §2.11.5 on the prototype, and the build must meet criterion 12 on a quiet runner. SuperLU on an indefinite saddle system relies on partial pivoting. JG measured the 200-tee review chain with Crane tees and an active PRV (it converges in 10 iterations against 1.1.0's 12, with up to 401 correction columns, a continuity residual of 0 and its plugged stubs at exactly 0; `judge/timing.py`), but not every ill-conditioned layout.
5. **C2.** The held discharge of a pressure pump needs its own gate R (the pump's rules), and gate C must be reconciled with rule S's P-matrix verdict. §5–§6 and the PVH cases are to be re-measured.
6. **Corpus coverage.** The corpus holds few projects with both an active PRV and a Crane branch: OC counted 4. The adversarial families carry that evidence and are part of the acceptance run (criterion 9).
7. **C0b first.** Criterion 3's result depends on C0b landing first, and on top of C0b it is expected, not measured (RV2). Fix (b) moves 9 corpus states of 1.1.0 between valid states, all at zero flow, on the 58 stalling projects C3 ran; it needs its own measurement under criteria B1–B8 (§2.11.10), including C3's stall scan of the system curves, which has not been run.
8. **Gate L's effect** is measured, not proven, to be small: nothing in the 1,520 family networks with PSVs; numbers within tolerance in 13 of the 73 corpus projects where it acts, with no state, convergence or flag change (§2.11.4). It was not added to the judge's full corpus, fixed-point and fuzz runs, which the build repeats with all four gates.

#### 2.11.15 Review of the redesign and its disposition

A two-lens review of §2.11 as merged (numerics, **RN**; verification, **RV**), each finding checked by a skeptic who re-ran the reviewer's scripts in its own clean `d0beec5` trees, raised 18 findings; the skeptics upheld 13 (RV9 in part) and rejected 5. The reviser (label `revise/`) re-checked every upheld finding against the code at `d0beec5` and, where the fix rests on numbers, by experiment in its own clean trees under `/dev/shm` (a `git archive` of `d0beec5`, and the same with `judge/make_sparse.py`, the chosen rule; `opensolve_pipe.__file__` printed by every run), before changing the design.

**What the reviser re-measured** (scripts and summaries in `revise/`):
- RN-1's growth at the exact root (`lag_growth_NC_h6.txt`, the skeptic's `lag_growth.py`): 1.930 per iteration from 10⁻⁹, constant over the first 15 iterations.
- The review's 5,244 networks regenerated from its generators and swept in both trees at default settings (`rn_cmp_default.txt`): 3,008 identical, 0 converged → not converged, 120 not converged → converged, 44 not converged in both, 66 valve-state changes, 0 other-state changes, 0 check failures, inner iterations 653,801 → 461,967, the review's numbers exactly.
- The 66 classified (`classify.py`, `changes66_default.txt`, `changes66_d1d2.txt`): 12 zero-flow label changes (TD 8, TT 4; flows within 8.1·10⁻¹¹ of the largest), 54 at nonzero flow (TD 38, NZ2 12, TT 2, PZ3 2); 1.1.0 at 1,000 iterations reaches the new rule's default-settings state in all 66, flows within 5.95·10⁻⁹.
- VA's 8 (`changes_va8_d1d2.txt`): NA's 2 D1 (within 1.14·10⁻⁹), NC's 6 D2.
- TD, NZ2 and TT (1,168) in both trees at 1,000 iterations (`cmp_tdnztt_*.txt`): 0 state changes and 0 converged → not converged between the trees; 1.1.0 changes 84 states between 100 and 1,000 iterations (TD 58, NZ2 12, TT 14).
- The rest of the 5,244 (4,076) in both trees at 1,000 iterations (`cmp_rest_head1000_vs_sparse1000.txt`): 2,650 identical, 0 converged → not converged, 24 not converged → converged, 0 state changes, 0 check failures. With TD, NZ2 and TT, the whole 5,244 at 1,000 iterations has no state change and no converged → not converged.
- The A1 comparisons (`cmp1.py`, `cmp2.py`, the skeptic's scripts re-pointed): the counts of §2.11.8, and RU's change count against `j_edrS.json` (RV13).
- C0b's 9 state changes with exact flows (`states_exact.py`): every changed element at exactly 0.0 m³/s.
- Gate L's reach and effect (`psv_count.py`, `dump_names.py`, `cmp73_*.txt`, `fuzz_one.sh`, `fuzzdiff_gateL_148.txt`): 0 iterates where it acts in the 1,520 family networks with PSVs; 492 in 73 corpus projects and 801 in 76 fuzz seeds outside the corpus; on the 73, 13 change within tolerance and nothing else; on the 148 fuzz seeds, no class, state, critical or self-check change (§2.11.4).
- The independent checks' coverage of the changed states (a count on the dumps above): in 48 of the 62 changes at nonzero flow one side has a PRV without a result, which `checks.py` skips (§2.11.9).

**Upheld:**

| ID | Severity | Finding | Re-checked against | What was done |
|---|---|---|---|---|
| RN-1 | major | Gate C's safety argument was false: it said gate C admits the exact step only where the lag would converge, "so the roots Newton converges to are roots 1.1.0's iteration reaches too". Gate C tests the iteration that lags only the held terms, not 1.1.0's, which lags the offsets too; in §2.11.2's model it passes where 1.1.0 diverges (l > p + g + w). Newton then converges inner solves to roots that repel 1.1.0, and the state changes stay with more iterations | The algebra of §2.11.2; the reviser's run of `lag_growth.py` on its own trees (growth 1.930 per iteration at NC h6/h38's third inner solve); 1.1.0 at 1,000 iterations on VA's 8: NC's 6 still in 1.1.0's state after 1,071–1,091 inner iterations, NA's 2 in the new state | Both sentences removed (§2.11.4 bullet C, §2.11.6 item 3) and replaced by the stability statement (for one PRV, r_tot > 1/(1 − τ), static pressure rising with the flow), with the measurement; §2.11.2 states which multiplier gate C bounds; §2.11.1's table; the methods sentence names the iteration whose multiplier it is; class D split into D1 and D2 with D2's evidence (§2.11.9); "what is not proven" gains D2; U13; Q8 puts D2 to the owner (options (a) and (a′)); the changelog's multiplicity sentence and the TSD §12 text say the state can differ from the one the previous method reaches with more iterations |
| RN-2 | major | Class-D changes are far more common than 8 in 4 layouts, and occur on simple layouts; conditions 3 and 4 of the class are unsound (condition 3 rejects changes with the same mechanism; condition 4 is undefined for PRVs feeding only assigned demands or set within 1 Pa of a boundary); 1.1.0 at 1,000 iterations is a checkable criterion | The reviser's sweeps above. The skeptic's correction holds: 12 of the 66 are zero-flow label changes, 54 at nonzero flow. One more correction: NZ2's new flows reach 2.8·10⁻³ m³/s (dh 10⁻⁴ tank variants), not 7.0·10⁻⁴ | §2.11.9 rewritten: D1/D2 by 1.1.0's 1,000-iteration run within criterion 3's flow tolerance, zero-flow label changes under criterion 4, the old conditions and why they were dropped, the review's families with their counts; criterion 9 (the 5,244 added, a 1,000-iteration run of both trees, the TD/TT/NZ2/PZ3 generators committed); risk 2 (counts, and the path dependence of these families in 1.1.0 itself); Q8's counts, before the owner answers |
| RN-3 | minor | §2.11.6 item 2 ("no flow dependence is lagged at an accepted iterate") contradicted the PSV exception listed above it, and nothing bounded that mode; the floor bullet understated the floors, which also replace a negative slope of a non-pipe link | `gga.py:963-969` (`max(sign·2c·Q_ref, 0.0)`), `gga.py:238` (`np.maximum(slopes, floor)` for non-pipes), `elements.py:374-375` (a pump's slope is the negated curve slope); the review's 1,152 PSV networks (0 accepted exact steps with a reversed PSV; bit-identical with the rejection). **Corrected by the reviser:** the fix's "zero measured cost" holds for the families only. In the corpus the chosen rule takes 492 exact steps with a reversed active PSV, in 73 projects, and in 76 more fuzz seeds; gate L changes 13 of the 73 within tolerance and nothing else, and no fuzz class, state or critical record (above) | Gate L added (§2.11.1, §2.11.4 item 1 with its measured reach and effect, §2.11.7, §2.11.13's changelog, methods sentence, `gga.py` comment and D10 text), knowing its corpus effect: it makes item 2 true by construction at a measured cost of 13 projects' numbers within tolerance, which correctness first (GOALS §3) accepts; the floor bullet reworded; the PSV term moved to "never part of an accepted step"; item 2 holds by construction; U8 gains the case; the exactness table relabelled (iterates checked before gate T; the 8 NDa iterates were rejected by T); risk 8 |
| RV1 | major | The redesign was compared with 1.1.0 only, never with A1; measured, A1 has 0 regressions and 0 state changes on both sets and converges 16 networks the chosen rule does not; "the only variant measured with 0 regressions" was false, and Q8 was framed without this | The reviser's `cmp1.py`/`cmp2.py`: A1 converges 16 E-family lines the chosen rule does not (9–16 against 112–116 inner iterations), the first build 18 (E 16, G 1, Gsj 1); on the 2,232 A1 is 1,944 identical, 0 / 0, 0 state changes, 264,424 → 244,124; the chosen rule converges 52 + 57 that A1 does not | A1's 2,232 row and an "Against A1" bullet (§2.11.8); the E-line bullet names gate R as the cause and says A1 converges them; "the only variant" sentence replaced (§2.11.1); the TSD §12 text names gate R; Q8 states the trade, with A1 as evidence and not an option (the skeptic's mitigation: the owner rejected A1); risk 3 names the possible variant (A1's term where gate R fails) as neither designed nor measured, the finding's optional part |
| RV2 | major | "With C0b: met except `fuzzfc_10246`'s curve point" was a prediction: C0b was never applied to either tree of C1's comparison | `judge/results/fl_cmp.txt` and `judge/redump.py` (9 named projects, fix (a) only: 8 identical, 1 different); the tight-run flag projects not re-dumped (`cmp_tight.txt`); fix (b)'s path changes, reproduced by the reviser (`fuzz_1446` 119 → 49, `fuzz_2522` 107 → 20) | §2.11.10's paragraph on what the measurement does not cover, with the path-dependent flag sets; criterion 3 and 7 rows marked expected, not measured, with the dumps the build must make first; risk 7; Q10 |
| RV3 | major | C0b had no acceptance criteria, its measurement was partial, and Q9 (a) bundled it with the criterion-3 addition | `crit3/stall_names.txt` (58 projects, main solves), `crit3/results/resid_all_head.txt` (384 rows, largest ratios 0.81 and 0.60); the reviser's exact-flow re-measurement of the 9 changes (all at exactly 0.0 m³/s) | C0b's criteria B1–B8 (§2.11.10); the zero-flow result reported; fix (a)'s effect on the 384 flags stated and marked unmeasured; Q9 (C0b) split from Q10 (criterion 3) |
| RV4 | major | One METHOD_VERSION 1.2.0 for C0b and C1 contradicted the owner's "own METHOD_VERSION" for C1, unflagged, and made C1's "unchanged" changelog line false against 1.1.0 | The owner's answers of 2026-10-24 (§13); §1.2 and §4.6 (C2 is 1.3.0); §1.4 item 3 (each takes the next minor version) | Recommended C0b as 1.2.0 and C1 as 1.3.0 (C2 then 1.4.0), §2.11.10, §2.11.13, Q9 (a); sharing kept only as Q9 (b), flagged as the departure, with C1's line relative to C0b and 1.2.0's net effect against 1.1.0; §1.2, §4.6 and risk 11 follow the answer |
| RV7 | minor | "They include all 85 of the first build's regressions" cannot be true: the 85 converged at 1.1.0 | `revise/cmp1.py`: intersection 0; all 85 converge under the chosen rule in 1.1.0's valve states; 48 of the 50 A1 gave up are among the 96 | The bullet reworded as the finding proposed |
| RV9 | minor | Q8 said the redesign "changes none in … the corpus or the fuzz", but the fuzz has a states-only change at zero flow | §2.11.8's fuzz table (`flow_control` seed 11,075 at exactly 0 m³/s) | Q8 and §2.11.9 say "no state change at nonzero flow". The finding's second part (name seed 11,005) was refuted by the skeptic: it is one of the 158 same-class record differences the table counts, none a state change; not applied |
| RV10 | minor | Three cross-references pointed to text that does not exist at HEAD | `git show HEAD:docs/TSD.md` (§12 item 6 is slice 1's speed control; no slow-lag item); `git show HEAD:CLAUDE.md` (D10 has only "PRV/PSV flows are coupled exactly in the Newton step (no lag)."); proposal §12 risk 2 is the round-off floor | §2.11.13's Docs bullets (a new TSD §12 entry; the D10 sentence named exactly); §2.11.10's fix (b) row ("proposal §12 risk 2") |
| RV11 | minor | The changelog counted VH1–VH3, added by C1 itself, as corpus conversions, and its convergence claim was contradicted by the 16 E-family lines | §2.11.8 (converged-flag changes only VH1–VH3; `judge/results/cmp_tol.txt`); RV1's E lines | Changelog: "([3], all of them reference cases added with this change; none of the [5,134] existing projects)", and the gate-R exception to the convergence claim |
| RV12 | minor | A design-team status note sat inside the owner's answers of 2026-10-24 | §13 as written | Moved to the head of §2.11; the answers block holds only the owner's answers |
| RV13 | minor | Some numbers were attributed or counted inconsistently: RU's "28 changed states" against 24; 201,492 attributed to VA; "d = 0.03 m" for all 16 E lines | The reviser's check of `j_edrS.json` against `j_off.json`: 12 valve-state and 12 other-state changes at 10⁻⁶ of the largest flow, 28 at 10⁻⁷ (4 G networks at 2.3–3.7·10⁻⁷), and RU's `changed28.txt` lists 30 names (2 I networks at 1.05·10⁻⁹); `n_x1rt_sp`/`n_x1rt_pm` total 201,486 and `n_sparse` 201,492; 3 of the 16 E lines have d = 0.1023 m | Scores table, results table and the E-line bullet corrected |

**Rejected (recorded, not applied):**

| ID | Finding | Skeptic's reason for rejecting it |
|---|---|---|
| RN-4 | No exactness defect was found on the new layouts, but U1 as specified would fail on valid kinks, JG's "no discrepancy remained unexplained" holds only for the sample checked, the FD leaves the continuity manifold and crosses the clip at a dead tee leg, and the classifier's 10⁻⁵ tolerance is below the FD noise at small flows | Not a defect in the design. U1 already says "at a kink it equals one of the one-sided differences, and the test asserts which"; in the reviewer's NZ2 dead-leg case the backward difference equals the analytic column (−0.03271 both). The "42 unexplained" come from the reviewer's own classifier tolerance, and the reviewer found no exactness defect. None of the networks shown is in U1's list, and JG's FD on the VH7 layout (the NH family, Crane tees with the branch plugged) marks every iterate "ok" (`judge/results/fd_new.txt`). JG's statement is for JG's own sets. Continuity-preserving perturbations and a step sweep are reasonable ways to implement the test, not corrections to it. (The reviser added "in these sets" to the statement, §2.11.8.) |
| RV5 | Two owner-level choices are presented as decided: the literal Q7 (b) is replaced by a different, gated method, and new acceptance criteria, performance budgets among them, are added | Refuted. The owner's answer is "the exact Newton step on the whole downstream response of a held head"; the Sherman–Morrison phrase described how to build it. §2.11.2 shows, with three independent measurements (176, 195 and 204 regressions), that the literal rank-one form reproduces N1, and §2.11.1 and §2.11.4 state the gates and their counts; the changelog and the methods text state the gating. The design is a proposal the owner reads, marked not built. Criteria 10–12 only add gates; none relaxes an owner criterion, and the one that does relax (criterion 9's class D) is put to the owner as Q8 |
| RV6 | The proof claim that no flow dependence is lagged at an accepted iterate, so the mixed map is never used, is contradicted by the design's own measurement, and the exactness summary overstates what was explained | The central claim is refuted: in `judge_c1.py` the FD check runs after gates R and C but before T; `n_x1rt_sp` shows exact = 0 for every NDa "h20.0,25.0 h38.0" network, with trust = 1 in exactly the 8 Ls0.5/Ls3.0 ones, so gate T refused the 8 PSV iterates; 8,195 exact + 210 trust = 8,405, the table's count. NDa is identical to 1.1.0 (36/36). The 5 reclassified iterates vary by more than the discrepancy over steps of 10⁻⁷ to 10⁻⁴ (`skeptic-verification/fd_sweep.py`, `fd_sweep_out.txt`). Its residual nits (name the PSV exception in item 2; the 8,405 include the 210 T-rejected; no sweep output was kept) were applied with RN-3 (§2.11.6, §2.11.8) |
| RV8 | §2.11 does not report the API test suite on the prototype, though D6 requires it green for a solver change, and the only preserved record shows failures | Not a defect of the design text. §2.11 makes no claim about the suite; D6's rule applies to the change when it is built, and the build runs it. The VA record (`pytest_x1rt.txt`) is not cited. The reviewer's own run of the build-path prototype gives 3,737 passed; its 4 failures are artefacts of the copy (the missing `derivations_velocity_head.py`, the released-link fixtures and `apps/web`). A suite line would be a nicety, as in §2.6 |
| RV14 | Criterion 9 builds in Q8 (a) while Q8 is open, and criterion 7's stall listing is not reported for the redesign | Refuted as a defect. Criterion 9's link to Q8 is explicit (§2.11.9 ends with Q8; Q8 (a) is "criterion 9 as stated"), so the class-D clause cannot be read as settled. Criterion 7's by-name listing is a build-time record, and §2.11.11 says the build re-runs criteria 1–8 after C0b; the prototype's non-converged list is preserved (`judge/results/cmp_tight.txt`, 385 not converged or not solved on a side). Marking criterion 9 "subject to Q8" would be cosmetic. (Criterion 9 now says "D2 only as Q8 allows", which the D2 split needed anyway.) |

**A reviser's observation, not a finding of the review.** While re-checking RN-2, the reviser found that the independent status check skips a pump or valve without a result (`tests/differential/checks.py:485-489`), so "both states pass the checks" does not cover a PRV closed beside a section v1 isolates. One side has such a PRV in 48 of the 62 changes at nonzero flow, 1.1.0's side of every D2 change among them. §2.11.9 and Q8 now say so, and criterion 9 requires a check of those PRVs.

**Effect on the owner questions:**
- Q7: its answered note says four gates.
- Q8: rewritten with the corrected counts (8 + 66 changes; D1 56, D2 6, 12 zero-flow label changes), D2 put explicitly (new option (a′): accept D1 only), and the trade against A1 shown as evidence; recommendation still (a).
- Q9: now C0b alone, with its criteria and its METHOD_VERSION; recommendation (a), C0b 1.2.0 and C1 1.3.0, with sharing 1.2.0 flagged as a departure (b).
- Q10: new, the criterion-3 addition split from the former Q9; recommendation (a), measured on top of C0b before it is claimed.

**Sections changed by this round:** the header (Q8–Q10); §2.7's last paragraph (Q9 and Q10); §2.11's status and provenance; §2.11.1 (the rule's gates, the parts table, the scores, A1's note); §2.11.2 (gate C's multiplier); §2.11.4 (gate L with its measured reach and effect, gate C's item 3 and bullet C with RN-1's measurement, the gate table's note); §2.11.5 (the cost of gates R and L); §2.11.6 (floors, the PSV term, items 2–4, what is not proven); §2.11.7; §2.11.8 (the introduction, the A1 row, the 2,232 row's iterations, the rows for the review's 5,244 and for 1,000 iterations, the conversion, A1 and E-line bullets, the exactness table and its classification); §2.11.9 (rewritten, with the checks' coverage); §2.11.10 (what the re-dump does not cover, fix (a)'s effect, the zero-flow result, criteria B1–B8, METHOD_VERSION, item 3); §2.11.11 (rows 3 and 7, criteria 9 and 11); §2.11.12 (U8, U13); §2.11.13 (version, changelog, the shared alternative, methods sentence, `gga.py` comment, Docs); §2.11.14 (risks 1, 2, 3, 7, new 8); this §2.11.15; §13 (Q7's note, Q8, Q9, new Q10, the status bullets removed from the answers block); Appendix B (the review's and the reviser's labels).

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
- **`NOT_CONVERGED`** with a message naming the pump, for each guard of §5.8–§5.11. For rule S's exits its details carry each pump's state, flow and speed (§5.11.4).
- **`STATE_SEARCH_INCOMPLETE`** (warning, new code): the zone search stopped at its candidate limit or at the search budget with candidates unsolved, or a pinned test of §5.9–§5.10 was not run because the budget was spent, so the state is not shown to be the only one (§5.11.6).

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

None. The owner answered Q1 with (c): several discharge-pressure pumps may share one pressure zone, so there is no `PRESSURE_CONTROL_ZONE` and no 422; the solve searches for second steady states instead (§5.11). `validate_topology` (`builder.py:227`) is unchanged, and `CONTROLLED_PUMP_CURVE` (`builder.py:274-296`) already applies to every controlled pump, of either mode. The zone partition is built once in `builder.py` for the search (§5.11.2).

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

  > Adds speed-controlled pumps holding a discharge pressure: the static pressure at the pump's discharge port is held in the network solve, as a PRV holds its outlet, and the speed recovered from the affinity laws, within a minimum and maximum speed. Several such pumps may hold one pressure zone: a regulating state is reported only where the drives can hold it (the response of their controlled values to their heads is a P-matrix), and the combinations of the zone's pump and valve states are searched for a second steady state, reported as not converged when one is found; the search has fixed limits, and a result whose search they cut short is flagged. Results of projects without discharge-pressure control are unchanged (corpus comparison).

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
2. **Parallel pressure pumps on one header.** *Measured* (E, `exp12`): two identical pumps with equal setpoints on spools without fittings reach 2–3 distinct rule-valid states depending on the start: (A, A), (A, CLOSED), (CLOSED, A), or (A, OPEN), (OPEN, A). With K = 2 on each spool the state is unique from all 16 starts. *Measured* (C, `p5b_parallel.py`, rule set C), 2 m spools: a +100 Pa setpoint difference moved the split from 0.027392/0.027392 to 0.007674/0.045278 m³/s. With 20 m spools it moved by 0.5 %. §5.11 handles this (Q1 (c)): the symmetric (A, A) is control-unstable, which rule S refuses, and C's +100 Pa split is a jump between states, not the sensitivity of one state (§5.11.5); the zone search refuses a second stable state. On the web app's default header, with Crane tees, pinned solves reached no second rule-valid state in 28 networks (ZJ, §5.11.1); pinned solves cannot reach a control-unstable root (§5.11.4), so that does not show that none exists, and on PZ8's network a speed-space scan found none (ZR, ZF; §9.3). A booster beside another pressure source that is not a pressure pump (an active PRV, a fixed or flow-controlled pump) can also have two valid states, one with the booster closed; the zone search handles that too (PN2, §5.11.8).
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

The owner chose Q2 (a). The section was revised after the review (PN1, PN2, PN6): the first draft compared only the two running limits, ran only for a pump with Q_d > Qtol, and so missed a closed alternative (PN1) and a second pressure source on the same header (PN2).

**Scope under Q1 (c)** (revised, §14.4). These tests now cover a pressure pump that is the **only member of its pressure zone** (§5.11.2). Everywhere else §5.11 takes over:
- for a regulating pump, rule S (§5.11.4) replaces V1's measurement and V2, and V7 becomes S's exit S5;
- V6 is removed: a booster beside another pressure source is a searched zone, and the zone search (§5.11.6) tries its alternatives, V6's among them;
- inside a searched zone, V3–V5's pinned sets are candidates of the search.

**Why.** With r ≤ 1, raising the speed lowers the port pressure:
- a drive holding the setpoint there is unstable (a normally acting controller runs to a limit);
- by continuity of a falling P(Q), the limit states on both sides of the unstable root satisfy their rules: at maximum speed, and at minimum speed with or without flow (§5.6 item 1).

A booster beside another pressure source can also have two states with r > 1 at the booster, one with it closed (PN2, below). Reporting either state as "the" answer is a choice the inputs do not make (GOALS §3).

**What the iteration already does.** For a single held node, C1's lag makes an unstable forward active root repelling (§2.3), so the active iteration cannot converge there. *Measured* (C, rule set C): in the header case of §5.6 the pinned active solve converged to a reverse root (Q −0.0189 to −0.0292 m³/s); PN measured the same on R2 31 and 33 m (§5.6 item 1). But the limit-state ambiguity remains, the closed alternative too, and symmetric multi-held-node layouts can still converge to an unstable active state (E, `exp12`).

**When the tests run.** At the converged exit, after §5.8, §5.9 and rule S (§5.11.3), for each pressure pump that is on, not forced and the only member of its zone. A pinned solve (below) skips these tests, rule S, the zone search and §5.9's swap test, so there is no recursion.

**Pinned solves.** New arguments to `run_outer_loop` (`status.py:1586`), beside `forced_flows`, used by V3–V5, §5.9's swap test and the zone search: `pinned: Mapping[str, frozenset[Status]] | None`; `guards: bool = True` (False in every pinned solve: §5.8's floating rule and §5.9's over-control test still run, the other guards do not, §5.11.3); `branch_restarts: bool = True` (False in the zone search's candidates, §5.11.6); and `search: SearchBudget | None = None`, given in every pinned solve (ZR F1, §5.11.6). Their semantics:
- a pinned control starts at the set's first status, and a rule that would move it out of the set leaves it where it is; every other element follows its rules;
- with `search` given, each inner solve runs at min(`CANDIDATE_MAX_ITERATIONS` = 30, `maxIterations`, the budget's remaining Newton iterations) and charges the budget with the iterations it used; when the budget is spent before an inner solve, the pinned solve is abandoned (`SearchBudgetSpent`) and its test is reported as not run (§5.11.6). So no pinned solve costs more than the budget, whatever the project's `maxIterations`;
- a converged pinned solve is a **second state** only when (i) every element's unrestricted rules keep its final status (§5.4 for the pinned pump, with σ0 by C1), and (ii) it differs from the converged state in flowing state: a flow or a head where there is flow differs by more than D6's tolerances (the criterion of `state_search.same`). A pinned solve that differs only in labels at zero flow, with the section beyond at rest, is one physical state (§5.6 item 4) and is not a second state. Under Q1 (c) the criterion is §5.11.7's for every pinned solve: (iii) rule S must also hold at its state, and a rule-valid state the drives cannot hold is listed, not counted;
- a second state → the solve is **not converged** ("two steady states", naming the pump, the element states and flows of both, and the test that found it). Otherwise the converged state stands, and the trace notes the test and its outcome (the state reached, the rule that failed, or that the pinned solve did not converge, at the cap or otherwise: the fuzz's class 6 reads it, §9.5).

**The tests:**

| Test | Applies to | Pinned solve | Reason |
|---|---|---|---|
| **V1, regulation ratio** | running (OPEN or MIN_SPEED) with Q_d > Qtol and both port heads known; for a regulating pump, rule S's solves give r for the trace | none: from rule S's open-loop solves (below) | — |
| **V2** | ACTIVE with r ≤ 1 | none: not converged; this is rule S with one regulating pump (exit S1, §5.11.4) | the regulating state is unstable |
| **V3** | OPEN with r ≤ 1 | {MIN_SPEED, CLOSED}, from MIN_SPEED: the pump's s_min branch, where N0 moves it to CLOSED and C1, with σ0 = s_min, back | the other side of the unstable root is at s_min, running or held at no flow (PN1) |
| **V4** | MIN_SPEED with r ≤ 1 | {OPEN} | with a falling P, CLOSED at s_max cannot also hold beside a valid MIN_SPEED (σ0 would be s_min; PN skeptic, derived) |
| **V5** | CLOSED, both port heads known, EGL_d ≥ H_set0 (σ0 = s_min) and H ≤ S_max + Htol | {OPEN} | the necessary condition for OPEN to hold too (PN1); a closed pump has no r |
| ~~V6, shared zone~~ | removed under Q1 (c): such a pump is in a searched zone (§5.11.2), whose search tries V6's two pinned solves among its distance-1 candidates (§5.11.8) | — | — |
| **V7** | a perturbed solve that does not converge | none: not converged; rule S's exit S5 (§5.11.4) | — |

**V1, the response** (revised under Q1 (c)). The pump's own law with a head offset ±δ (a new `OffsetLaw` wrapper in `elements.py`), δ = Htol = 10⁻⁴ m, in two inner solves (`solve_gga`) with every other state and branch law as converged, warm-started from the converged flows, at tolerance `RESPONSE_TOL` = 10⁻¹² and the project's `maxIterations`. These are rule S's solves for the pumps of its set L (§5.11.4), which run whenever P = A ∪ L is not empty, also when no pump regulates anywhere (A empty, ZR F5): the regulating speed-controlled pumps, if any, are opened to their fixed-speed laws, and V1's r, defined with them holding their values, is recovered exactly by a Schur complement (with A empty, r comes straight from the pump's own two solves). Then k_down = ΔEGL_d/ΔQ_d and r = k_down/(2c_dQ_d). If ΔQ_d = 0, r = ∞: the flow is fixed elsewhere, for example by an FCV upstream.

*Why not the held value:* the first draft perturbed an ACTIVE pump's held value H_set0 ± δ with the other regulating pumps holding theirs. At an unstable state that held solve is repelled by the lag and does not converge, so V7 would refuse with the wrong reason (*measured*, ZJ `j1_v1_held.py`: six symmetric states, 100 iterations each; ZS: four). *Why the pump's own state, not its discharge EGL:* holding the discharge EGL instead makes the perturbed solve undetermined when an FCV is upstream (C found this). *Why `RESPONSE_TOL`:* a numerical choice, so that a flow change of about δ/k_down, near 10⁻⁶·Q in the measured cases, is resolved (C). Both numbers are in the methods summary (§8.2 item 4).

**V2's message** (rule S's exit S1; PN6: the first draft asserted that both limit states satisfy their rules, which nothing checked; revised under Q1 (c), ZS: with one drive the index sum of §5.11.5 is the intermediate value theorem, so the companions of an unstable root exist in its frame, and the sentence states it):

> the static pressure at the discharge port of <PU> falls as its flow rises (r = 0.22: the losses beyond the port are less than one velocity head of its discharge pipe), so a drive holding it is unstable; with every other element as solved, at least two other steady states then exist for this pump (at a speed limit, held at no flow, or regulating on a rising stretch); add the exit or expansion loss beyond the port (an exit fitting at a reservoir, a reducer fitting, a Crane tee)

The companion clause holds in the pump's own frame: one drive, every other element frozen at its state. With one regulating pump (|A| = 1) that is the clause above. When S1 names one of two or more regulating pumps (|A| ≥ 2), the other drives are open loops at their present speeds in the measurement, and the clause reads "with the other regulating pumps held at their present speeds and every other element as solved, at least two other steady states then exist for this pump": the zone's own frame, with every drive regulating, can have a positive determinant and no companion at all (ZR F2; *measured*, ZF `y5_box_vi.py`: the affine frame G′ = [[1, 3], [−3, −1]] fails S1 through g′₂₂ = −1, has det 8 and its regulating state as its only state).

**Why V5, and the zone search's V6 candidates, refuse nothing where the state is unique** (derived; V6's derivation now explains the search's outcome on a booster beside another pressure source):
- V5: with r > 1 (P rising), OPEN at s_max runs at Q_M > 0 with P(Q_M) > P(0) = EGL_d(closed) ≥ H_set0, so X1 fires and the pinned OPEN state fails its rules. This is PCF7's and EP4's configuration (§9.3, §9.4), whose derivations require that X1 fires at s_max by `STATE_MARGIN`.
- The former V6, running booster: let r_spool be the loss between the port and the shared node in velocity heads of the discharge pipe. Regulating at Q_P, the shared node's head is H_set0 + (1 − r_spool)·c_dQ_P²; closed, it falls by what the other source's head loses with the smaller total flow; C1 keeps the booster closed only if the closed-state head at the port is still ≥ H_set0. Both hold only in a band of width at most (1 − r_spool)·c_dQ_P² of the other source's setpoint (PN, derived; 0.039 m in the measured network). With r_spool > 1 the pinned CLOSED state re-opens (C1), so it refuses nothing. The same derivation covers a fixed pump beside the booster (PN), so PCF14's derivation proves its setpoint outside that band (§9.3).
- The former V6, closed booster: if the other source holds the header at or above H_set0 (σ0 = s_min), a pinned regulating state with r_spool > 1 would put the header below H_set0 while adding flow to it, so it needs a reverse flow and P1 fails it; if the header is below H_set0 (σ0 = s_max), the closed state holds only with H > S_max, where no speed in range passes forward flow (P1 or P2 fails it).

*Measured* (PN, `r6_prv_parallel.py`, `r6b_r.py`, today's solver, the booster emulated by a pump at s_max and an ideal PRV at its port; PN skeptic reproduced it): RH 60 m → 100 m line → PRV (25 m of head) → 1 m spool → ideal tee run inlet; RL (head −10 m) → 10 m line → PU (H₀ = 60 − 2000x, s ∈ [0.7, 1]) → 1 m spool → tee branch; tee run outlet → 50 m with an exit → R2 24.5 m; both setpoints 25 m of head; no fittings on the spools.
- State A, PU regulating: Q 0.007664 m³/s, H 35.1709 m, s* 0.903942 ∈ [0.7, 1]; the real PRV is closed, with its outlet at 25.03874 m ≥ Hset − Htol, which prvstatus keeps closed (`status.py:212-239`).
- State B, the PRV active and PU closed: the PRV passes 0.007664 m³/s; PU's EGL_d is 25.03874 m ≥ H_set0, so σ0 = 0.7, and H = 35.0387 m > S_min = 29.40 m: C1 keeps it closed.
- V1 in state A: r = 10.590 (11.6 with the 0.1023 m bore). From state A, the zone search's candidate (PRV active, PU closed) is expected to reach state B, which holds every rule, and from state B its candidate (PRV closed, PU active) to reach state A; each is a permutation of the other, so the search tries it first (derived from the two measured states; ZE measured the same three-state permutation class with two boosters and a PRV, `e10_mixed.py`, §5.11.11; the pinned paths on PN2's network are a C2 unit test, §9.7).
- The band: c_dQ² = 0.04855 m and the spool loses 0.00981 m, so r_spool = 0.202 and the band is 0.039 m. Equal setpoints ("2.5 bar" on both) are a natural input.

**On the measured header networks** (derived from the fixed-pump measurements; the build's unit tests, §9.7):
- J `j5`, R2 = 19 m: accepted at max speed; V3's pinned s_min branch runs at s_min with a port pressure below the setpoint (181,863.6 Pa), so N1 fails; and the closed state fails too (its discharge at zero flow, 19 m, is below H_set0, so σ0 = s_max, and H = 14 m < S_max re-opens it).
- J `j5`, R2 = 20.8–21.3 m: not converged; both limits hold (J) and r ≈ 0.22 (C).
- PN1, R2 = 31 and 33 m: not converged. Ending CLOSED (the path PN measured), V5's pinned OPEN state holds (X0 and X1 fail). Ending OPEN, V3's pinned branch reaches CLOSED at s_min, which C1 keeps.
- PN2: not converged, from either state, by the zone search (§5.11).

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
- The tests look for a second state of each pressure pump, with the other elements following their rules. A multiplicity that needs another element pinned (v1's status-rule multiplicity, TSD §10.4) is not refused, as in v1 and slice 1. §5.11.13 lists the zone search's own limitations.

**Cost.** V1: two warm-started inner solves per lone pressure pump at a limit, inside rule S's solves (§5.11.12). V3 and V4: one pinned outer solve where r ≤ 1. V5: one per lone closed pressure pump at or above its setpoint with both heads known (the "satisfied booster"). Each pinned solve runs with the cap and the search budget of §5.11.6, as the zone search's candidates do, so its cost does not grow with the project's `maxIterations`. The zone search's cost and the gate are in §5.11.12.

### 5.11 Pressure zones: control stability and the zone search (owner's answer Q1 (c))

The owner answered Q1 with (c) (§13, 2026-10-23): several discharge-pressure pumps may share one pressure zone, each holding its own discharge port (parallel boosters on one header). There is no `PRESSURE_CONTROL_ZONE` and no 422. The solve searches for further steady states at solve time, more broadly than §5.10's single-pump tests, and reports **not converged**, naming the pumps and describing the states found:
- when it finds a **second steady state** that satisfies every rule; or
- when the regulating state it reached is **unstable as a control system**.

This section was designed in an owner-answer revision (§14.4): two independent designs, **ZE** (an exhaustive, bounded enumeration) and **ZS** (control stability of the regulating set), then a judge, **ZJ**, who compared them, re-measured the points where they disagreed or where neither had measured, and merged them. Every *measured* number names who measured it and with which scratch script (Appendix B).

**Which rules the measurements ran.** Rule set Z is §5.4's table exactly as written (the closing test first at OPEN and MIN_SPEED, P0's split at H_set0 + Htol, C1 via EGL_d, P3 on F(s_lo(Q), Q)), with a pressure pump in ACTIVE as the `FIXED_DOWNSTREAM_HEAD` link of §5.2. It ran on a clean `git archive` copy of `f9d402b`:
- ZE and ZJ applied the C1 code of §2.2 to their copies; ZS did not (its networks have bare spools, where C1 applies no exact term, §2.3).
- ZE and ZS emulated the main solve on inner solves (`solve_gga`), in networks with ideal tees and no other status elements.
- ZJ's prototype (`czone.py`) pins the members as fixed controls inside the real `run_outer_loop`, so Crane-tee branch iterations, warm starts, branch restarts and the fallbacks are the code's own; only the members' rules run in an emulated loop around it.

Every configuration quoted here becomes a C2 test whose expected outcome is stated from a derivation or `state_search`, not copied from the solver (§5.4, RVG-16).

#### 5.11.1 What is decided

| | Mechanism | Runs | Extra work | Replaces |
|---|---|---|---|---|
| **S** | **Control stability of the regulating set.** The response G′ of the regulating speed-controlled pumps' controlled values to their own heads, from open-loop solves; the state is reported only if every block of G′ that holds a regulating pressure pump is a P-matrix | The perturbed solves: every converged state with a regulating pressure pump or a lone pressure pump at a limit with flow (P = A ∪ L not empty); the test: where a pressure pump regulates; every valid candidate of the search; every system-curve point | 2 inner solves per regulating pump (and per lone pressure pump at a limit) | V1 for regulating pumps, V2, V7 |
| **Z** | **The zone search.** Pinned solves of the zone members' status combinations, permutations of the reached statuses first; at most `ZONE_SEARCH_LIMIT` = 63 per zone per solve and `ZONE_SEARCH_POINT_LIMIT` = 15 per zone per system-curve point; each candidate's network solves capped at `CANDIDATE_MAX_ITERATIONS` = 30 Newton iterations; every pinned solve of a solve within `SEARCH_NEWTON_BUDGET` = 4,000 Newton iterations, of a system curve within `CURVE_SEARCH_NEWTON_BUDGET` = 10,000; beyond any of them, `STATE_SEARCH_INCOMPLETE` | Every zone with a discharge-pressure pump and at least one other member | At most 63 pinned outer solves per zone and 4,000 Newton iterations per solve | V6, and V3–V5 inside such zones |
| **C** | **The exact second-state criterion** (§5.11.7): converged, every rule holds, differs in flowing state, control-stable | Each candidate | — | §5.10's definition, extended |
| **I** | **The index sum** (§5.11.5): a diagnostic in the trace and the fuzz | The reached state and the valid candidates of its frame | none | — |

A pressure pump that is the only member of its zone keeps §5.10's V1 and V3–V5 (owner's answer Q2 (a)).

**What the measurements show:**
- **Parallel boosters on ideal tees with bare spools have several rule-valid states, and the default start lands on the control-unstable one.** Identical pumps started ACTIVE stay symmetric, and the symmetric regulating state is unstable whenever the discharge spool loses less than one velocity head (§5.11.4, closed form). *Measured* (ZE `e1_two.py`, `e3_dp.py`; ZJ `j1_v1_held.py`, `j2_crane.py`): (A, A) reached with Niederlinski index −0.155 to −0.558. S refuses it.
- **V1's held-frame perturbation cannot be computed there.** *Measured* (ZJ `j1_v1_held.py`): at all six unstable symmetric states, both perturbed solves of V1 (the held value ±Htol, the other pump holding its port) ended not converged after 100 iterations, so V7 would refuse with the wrong reason. ZS measured the same at four states (`s1`, `s3`, `s5`). The open-loop perturbation of S converged in 3 iterations at every state measured, stable or not (ZJ, ZS).
- **Every stable second state found was a permutation of the reached statuses** whenever the reached state passed S. *Measured*: ZE (`e13_orders.py`, 124 random networks and the hand-built ones); ZJ (`j5_variants.py`, 49 networks): with permutations first, the search found it at candidate 1 (at candidate 1 or 2 when it ran after S's refusal).
- **On the web app's default header pinned solves reached no second state.** The web app creates Crane tees (`factory.ts:260`). *Measured* (ZJ `j5_variants.py`): in 28 Crane-tee headers (19 with two boosters, 9 with three) the full enumeration by pinned solves reached no second rule-valid state that differs in flowing state, and every reached state passed S; in 21 ideal-tee headers, 9 had a stable second state and 4 reached a control-unstable state. The same inputs on an ideal tee and on a Crane tee: (A, A) unstable with (C, A) and (A, C) stable, against (C, A) alone by pinned solves (ZJ `j2_crane.py`, 2 m bare spools, 250 kPa). Pinned solves are repelled from control-unstable roots (§5.11.4), so these counts do not show that the Crane headers have no unstable rule-valid state (ZR F7); for PZ8's network a speed-space scan (pumps at fixed speeds in the real outer loop, Crane K iterated, every root refined) found no (A, A) root at all (*measured*, ZR `x4_speed_space.py`; reproduced by ZF, `y6_speed_space.log`). The case derivations of §9.3 must find unstable roots too.
- **The search dominates the cost** (§5.11.12): at `maxIterations` 100 and without the cap, a two-member zone added a median of 295 Newton iterations per solve and a three-member zone 2,149 (ZJ `j5_variants.py`); with the cap of 30 (§5.11.6), at most 293 Newton iterations in the 5 hand-built two-member zones and 1,734 in the 15 three-member zones of ZJ's `j7` records (re-analysed by ZF, `j7_analyze.py` and the per-network sums of §5.11.12), whatever the project's `maxIterations`.

#### 5.11.2 Zones, members and searched zones

**Zone partition.** Built once in `builder.py` from the user statuses, as the old §5.11 defined it. Remove from the port graph:
- reservoirs and ideal reference nodes;
- every pump;
- every PRV, PSV and FCV whose status is `active` or `failed_closed`;
- every isolation valve whose status is `isolated`;
- every check valve whose status is `locked_closed`.

A zone is a connected component of what remains: ports joined by connections, and through the remaining components' internal links. A removed component's ports stay in the zones they connect to. The partition does not change during a solve.

**Members of a zone Z** are the status elements that hold or push the pressure of Z, each with its options:

| Member | Condition | Options (pinned statuses) |
|---|---|---|
| Discharge-pressure pump | on, not forced, discharge port in Z | ACTIVE, OPEN (s_max), MIN_SPEED (s_min), CLOSED |
| Flow-controlled pump | on, not forced, discharge port in Z | ACTIVE (fixed flow), OPEN, MIN_SPEED, CLOSED |
| Fixed-speed pump | on, not forced, discharge port in Z | OPEN, CLOSED |
| PRV | status `active`, outlet port in Z | ACTIVE, OPEN, CLOSED |
| PSV | status `active`, inlet port in Z (it holds Z from below) | ACTIVE, OPEN, CLOSED |

Not members: FCVs (their series interaction is §5.9's swap test), a pump forced by a system-curve solve (a fixed flow), check valves and every other element. These follow their rules in every pinned solve.

**A searched zone** has at least one discharge-pressure member and at least two members. Two consequences:
- A pressure pump that is the only member of its zone keeps §5.10's V1 and V3–V5.
- A zone without a pressure member is not searched, so every project without discharge-pressure control runs exactly the C1 code path (C2's exact corpus identity, §9.9). PRV-only zones keep v1's behaviour (risk 7).

**Series pressure pumps** lie in different zones. A flow control upstream of a pressure pump is not a member of the pressure pump's zone (its discharge lies in the zone between them), so §5.9's swap test still covers it.

#### 5.11.3 Order of the tests at the converged exit

At the exit of `run_outer_loop` (`status.py:1740` region, after `_over_controlled`), in this order:
1. §5.8's floating rule.
2. §5.9's over-control test, then §5.9's swap test (Q3 (b)).
3. **S** (§5.11.4), over the regulating set of the whole network.
4. §5.10's V1 and V3–V5, for each pressure pump that is the only member of its zone.
5. **The zone search** (§5.11.6), for each searched zone, in the order of its smallest member id.

A refusal in any step ends the solve as **not converged**; the message names the step, the pumps and the states (§5.11.10). Without a refusal the state stands, and the trace records what each step did.

**When S refuses,** step 5 still runs for the zones of the refused pumps, with the same limits and an early stop at the first valid, control-stable candidate, only to describe a state the drives can hold in the message ("with PU1 at maximum speed and PU2 regulating at speed 0.807, every rule holds and the drives can hold it").

**Pinned solves** (the search's candidates, V3–V5, §5.9's swap test) run with `guards=False`. They keep §5.8's floating rule and §5.9's over-control test, whose not-converged outcome makes the candidate "no state found", and skip step 2's swap test and steps 3, 4 and 5, so nothing recurses. The search computes S at a valid candidate itself (§5.11.7). Every pinned solve of steps 2, 4 and 5 runs with `CANDIDATE_MAX_ITERATIONS` and charges the solve's one search budget, in the order of the steps (§5.11.6); a test that the spent budget leaves unrun is reported, never skipped silently.

#### 5.11.4 S: control stability of the regulating set

**The drive model (ZS).** Each speed-controlled pump that regulates has its own integral controller acting on its speed, ds_i/dt = k_i·(y_set,i − y_i), with k_i > 0: it speeds up when its discharge pressure (or its flow) is low. The hydraulics settle much faster than the drives, so y(s) is the steady network solution at speeds s. Linearised at a state, δṡ = −K·G·δs, with G = ∂y/∂s over the regulating pumps and K = diag(k_i). A drive at a speed limit, or out of regulation, is an open loop (k_i = 0). The model has no tuning, so the test asks whether **some** tuning holds the state, also with any subset of the drives out of regulation.

**The sets.**
- **A**, the regulating set: every speed-controlled pump that is ACTIVE, not forced, with flow (Q_d > Qtol for a pressure pump; a flow pump's flow is its setpoint, > 0), when at least one pressure pump is in it; otherwise A is empty.
- **L**: every pressure pump at OPEN or MIN_SPEED with Q_d > Qtol that is the only member of its zone (V1's pumps at a limit, for V3 and V4).
- **P = A ∪ L**, the perturbed set. **The perturbed solves run whenever P is not empty**, also with A empty: a lone pressure pump at a limit needs V1's r for V3 and V4 where nothing regulates anywhere, as in the J `j5` and PN1 header networks (revised, ZR F5: the earlier wording, "otherwise A is empty and S does not run", could be read as skipping them).
- **The tested blocks.** The P-matrix test (below) runs only on the blocks of G′_AA that hold a regulating pressure pump. A block of flow pumps alone is not tested, even when a pressure pump regulates elsewhere in the project, so flow pumps keep slice 1's behaviour wherever no pressure pump shares their block (ZR F5), and a project without discharge-pressure control runs neither the solves nor the test (C2's corpus identity).

Flow-controlled pumps are in A because their drives are integral loops too (decided by GOALS §3; Appendix A, R18). PRVs, PSVs and FCVs stay held: they are taken as fast, ideal loops, a modelling choice stated in the methods summary.

**The measurement (open loop).** New `regulation_response(built, result, controls, states, max_iterations)` in `status.py`:
- **Base states:** the converged states, with each j ∈ A replaced by its fixed-speed law at its recovered speed, `LinkState(NORMAL, law=PumpLaw(curve_j, s*_j))` (s*_j from `operating_speed`, computed once and shared with `results.py`). The pumps of L keep their own law (s_max) or `min_law`. Every other element keeps its converged state: held PRVs and PSVs, fixed flows of pumps not in P, check valves, closures and the branch leg laws.
- **Perturbed solves:** for each j ∈ P and each sign, `solve_gga` with link j's law wrapped as `OffsetLaw(law_j, ±δ)` (h(Q) ∓ δ: δ of head added or removed), δ = Htol = 10⁻⁴ m, tolerance `RESPONSE_TOL` = 10⁻¹², the project's `maxIterations`, warm-started from the converged flows.
- **Read** for every i ∈ P: the controlled value y_i (a pressure pump's port static head P_i = EGL_d,i − c_i·Q_d,i², a flow pump's flow Q_i), EGL_d,i and Q_d,i.
- **G′_ij** = (y_i⁺ − y_i⁻)/(2δ); GE and GQ (the EGL_d and Q responses) the same way.

*Why the open loop.* V1's held frame perturbs a held value while the other regulating pumps hold theirs. At an unstable state that held solve is repelled by the lagged velocity-head term (§2.3) and does not converge (*measured*, ZJ `j1_v1_held.py`, six states; ZS, four). In the parallel-booster class (independent suction lines, a passive discharge network with port transfer resistances Z_dd, C = diag(2c_iQ_i)), the lag multiplies the flow error by Z_dd⁻¹C, so the held iteration converges locally iff M = Z_dd − C is positive definite, which in that class holds iff G′ is a P-matrix (ZS, derived from G′ = M(M + N)⁻¹ with N a positive diagonal). *Measured* (ZS `s6_closed_form.py`): the predicted multiplier 0.4266 against 0.4266 observed (K = 2 spools, converges), 2.9205 against 2.9206 (fitting-less, diverges). With every regulating pump at a fixed speed, the network is passive with falling pump curves, has one solution, and the perturbed solves converged in 3 iterations everywhere (*measured*, ZJ and ZS).

*Units.* G′ differs from ∂y/∂s only by the positive column scaling ∂F/∂s_j (> 0 on [s_lo, s_max] by the ψ test). Positive row and column scalings leave every principal-minor sign and every Niederlinski index unchanged. *Measured* (ZJ `j1_v1_held.py`): the index −0.5032 by speed perturbations ±10⁻⁶ relative and by head offsets ±10⁻⁴ m.

*Crane tees.* The leg laws of a Crane branch carry the tangent of K in the flow fraction (`HeadOffsetLaw.tangent`, `elements.py:177-230`), so the frozen-law response includes K's dependence on the split to first order. *Measured* (ZJ `j4c_kcheck.py`, five Crane headers with two or three boosters): G with the branch laws frozen against G with the Crane K re-iterated by the outer loop (K_TOL and OFFSET_TOL set to 10⁻¹²) agree within 4.2·10⁻⁸ to 1.5·10⁻⁶ relative at speed steps of ±10⁻⁴, and within 7.9·10⁻⁶ at ±10⁻³.

**The condition.** Each tested block G′_BB (B ⊆ A, a block holding a regulating pressure pump, as split below) must be a **P-matrix**: every principal minor, of every order 1 … |B|, resolved positive. Equivalently:
- g′_ii > 0 for every i ∈ B (each drive alone holds it; for one pressure pump this is r > 1, V2); and
- NI(G′_JJ) = det G′_JJ/∏_{i∈J} g′_ii > 0 for every J ⊆ B with |J| ≥ 2 (the Niederlinski index of every subset).

Blocks are decoupled within the resolution (no entry between two blocks exceeds it, below), so G′_AA is a P-matrix exactly when every block is, and the condition on the tested blocks is the condition on G′_AA without the blocks of flow pumps alone.

**Why (cited, and derived).**
- **Integrity.** A decentralized integral controller gives the plant integrity when the closed loop stays stable with any combination of the individual controllers taken out of service (Campo & Morari 1994, as defined in Kariwala, Forbes & Meadows 2005). Kariwala, Forbes & Meadows (2005), Proposition 4, restating Gündes & Kabuli's (2001) conditions (their Theorem 2) in Niederlinski indices: if NI(G_γ) > 0 for every principal subsystem γ of a stable plant, a block-diagonal controller with integral action exists that gives it integrity, and the conditions are also necessary when all but one of the controllers are strictly proper; Gündes & Kabuli give them for up to four blocks, and the NI form extends "by induction". For scalar loops: "for fully decentralized control, satisfying (10) … guarantees the existence of a pure integral action controller such that G(s) has integrity".
- **The drives' sign is fixed.** Kariwala et al. let each loop's sign be chosen. A drive acts normally (up on low pressure), and a single integral loop with k_i·g_ii < 0 is unstable, so g′_ii > 0 is required too. Together: G′_AA is a P-matrix.
- **Necessary conditions** (Skogestad & Morari 1992, Theorems 1 and 2, from Grosdidier, Morari & Holt 1985, Theorems 6 and 3, and Niederlinski 1971): RGA_ii(G(0)) < 0 for some i, or det G(0)/∏ g_ii < 0, implies that the plant is not decentralized integral controllable. A P-matrix has a positive RGA diagonal: λ_ii = g_ii·det G_{−i}/det G > 0.
- **Elementary form** (derived; ZE, ZS). The characteristic polynomial det(λI + KG′) has the coefficients c_m = Σ_{|J|=m} (∏_{i∈J} k_i)·det G′_JJ. If det G′_AA ≤ 0, the product of the eigenvalues of KG′ is ≤ 0 and the loop is unstable for **every** positive tuning; if every principal minor of one order m is ≤ 0, c_m ≤ 0 for every K, and again no tuning holds it.
- **A full-determinant test is not enough.** *Measured* (ZS `s4_three_complete.py`, three fitting-less boosters): (A, A, A) with det G′ = +164.7 (index 0.355) but all three 2×2 minors negative (−42.52, −42.52, −45.25) and two negative eigenvalues; unstable for every tuning.
- **Per-pump r is not enough.** *Measured* (ZS `s5_mixed.py`, unlike spools, K = 0.5 against none): (A, A) with open-loop r 2.997 and 5.197, both > 1, and det −38.07.

**What S does not cover.** The drives' dynamics, and the PRV, PSV and FCV loops, which are taken as ideal. A state that passes S is not proven stable for a given tuning: S excludes the states that no decentralized integral controller with these signs can hold with integrity.

**Resolution and size** (ZS). `RESPONSE_RTOL` = 10⁻⁶, a numerical choice disclosed in the methods summary:
- order 1: g′_ii is resolved positive if g′_ii > RESPONSE_RTOL·max_j |g′_ij|;
- order ≥ 2: NI is resolved positive above RESPONSE_RTOL and negative below −RESPONSE_RTOL; NI is invariant to positive diagonal scalings;
- basis: *measured* (ZS `s1_two_boosters.py`, `s6_closed_form.py`): G·M − I off-diagonals ≤ 1.8·10⁻⁸, the closed form below within 1.4·10⁻¹⁰, so the margin is at least 50×;
- **degenerate:** some minor unresolved and none resolved negative; the regulating pumps do not independently set their controlled values (exit S4);
- **blocks:** G′_AA is split into irreducible blocks (i and j coupled when |g′_ij| or |g′_ji| > RESPONSE_RTOL × the row's largest entry); each block that holds a regulating pressure pump is tested exhaustively by `slogdet` up to 12 pumps (4,095 minors), and a block of flow pumps alone is not tested (ZR F5); a larger tested block gives not converged, "the stability of n coupled regulating pumps is not assessed (more than 12)", never a silent pass.

**What the same solves give.**
- **r_j for j ∈ A** (pressure pumps), with the other regulating pumps at their speeds: r_j = (ΔEGL_d,j/ΔQ_d,j)/(2c_jQ_d,j). It goes to the trace.
- **V1's r for j ∈ L** (held frame: every other element in its state, the regulating pumps holding their values), by a Schur complement of the same solves: w = −G′_AA⁻¹·G′_Aj, ΔQ = GQ_jj + GQ_jA·w, ΔE = GE_jj + GE_jA·w, r_j = (ΔE/ΔQ)/(2c_jQ_d,j). Its sign is that of the gain pump j would have if it joined A. *Measured* (ZS `s8_saturated_r.py`, state (ACTIVE, OPEN) of C's `p5` network): r of the pump at maximum speed 0.2261 held, 0.2261 by the Schur complement, 1.9590 with the other pump at its fixed speed. V3 and V4 keep their trigger r ≤ 1.
- **One pressure pump** (|A| = 1, nothing else perturbed): the speed perturbation moves the operating point along the unchanged downstream characteristic, so g′ = (∂Q_d/∂e)·2c_dQ_d·(r − 1) with ∂Q_d/∂e > 0: g′ > 0 ⟺ r > 1, which is V2 (derived). S's exit S1 keeps V2's message.

**Closed form for k pumps on one ideal node** (ZS, derived; used by the reference cases, §9.3). With independent suction lines and a passive discharge network, d_M,i = h′_D,i(Q_i) − 2c_iQ_i, d_S,i = h′_D,i + h′_S,i − ∂F/∂Q(s*_i, Q_i), R_M = h′_M(ΣQ), β = R_M/(1 + R_M·Σ 1/d_S,i), u_i = 1 − d_M,i/d_S,i, w_i = 1/d_S,i:
- G′ = diag(d_M/d_S) + β·u·wᵀ, and det G′_JJ = ∏_{i∈J}(d_M,i/d_S,i)·[1 + β·Σ_{i∈J}(d_S,i − d_M,i)/(d_S,i·d_M,i)] (matrix determinant lemma);
- so every principal minor is positive when every spool's loss rises with flow faster than its velocity head (d_M,i > 0);
- for identical pumps at equal flows, the antisymmetric eigenvalue of G = ∂P/∂s is λ_a = g′b, with the sign of r_D − 1, r_D the spool's loss in its own velocity heads (ZE): **a symmetric regulating pair whose discharge spools lose less than one velocity head is control-unstable**.

*Measured*: closed form against the solver's G′, 9.7·10⁻¹¹ (K = 2 spools) and 1.4·10⁻¹⁰ relative (fitting-less) (ZS `s6_closed_form.py`); ZE's closed form of ∂P/∂s against finite differences, 5.0·10⁻¹⁰ to 8.6·10⁻¹⁰ (`e14_closed_g.py`), with λ_a −3.425 at r_D 0.342 (2 m bare), +4.296 at 2.098 (0.5 m with K = 2) and +8.058 at 3.536 (20 m bare).

**Exits** (for each tested block B, the first that applies, in the order S5, S4, S1, S2, S3; texts in §5.11.10; revised, ZR F2: the earlier S2, "det G′_JJ ≤ 0 for some J", took in every failing subset, so S3 could never be reached and S2's "every tuning" was false for a proper subset):
- **S5** a perturbed solve did not converge (V7, generalised);
- **S4** degenerate (over-controlled): some principal minor of B unresolved and none resolved negative;
- **S1** a pump of B with g′_ii resolved ≤ 0: its own drive is unstable with the others at their present speeds (V2's message for that pump, with its r and the companion clause of its own frame, §5.10);
- **S2** **unstable for every tuning**: det G′_BB resolved negative; or, for some order m with 2 ≤ m < |B|, every principal minor of order m is negative or unresolved and at least one of them is resolved negative (then c_|B| < 0, or c_m ≤ 0 with the unresolved minors taken as zero, for every positive K: the elementary form above);
- **S3** **held only while every drive regulates**: any other failure, that is, some principal minor of a proper subset J (2 ≤ |J| < |B|) resolved negative while det G′_BB is positive and some minor of each order is positive. A tuning may hold the state with every drive regulating, but not with integrity (R23).

**Index and companions** (ZR F2). A state's index in the frame of a zone Z (§5.11.5) is the sign of the **frame determinant** D_Z = det G′_AA / det G′_OO, with O = A ∖ A_Z the regulating pumps outside Z, which hold their values in Z's frame (the determinant of the Schur complement of G′_OO; D_Z = det G′_{A_Z A_Z} when no pump regulates outside Z). D_Z is used only where both determinants are resolved nonzero. Only D_Z < 0 implies companions (two or more other states in Z's frame); det G′_AA itself is not a frame's index when A spans zones, as with series pressure pumps.

`NOT_CONVERGED`'s details gain, for every pump of the refused state, `"{id}.state"`, `"{id}.flow"` and `"{id}.speed"` as full-precision floats, because a non-converged result carries no element results (`results.py:1099-1130`) and the fuzz's independent check rebuilds the state from them (§9.5).

**Measured** (open-loop G′ or G at the reached or enumerated states; NI = det/∏ diag):

| Network | State | Q (m³/s) | Gain matrix | Verdict | Who, script |
|---|---|---|---|---|---|
| C's `p5`: 2 boosters, shared 10 m suction main, ideal tees, 2 m fitting-less spools, 100 m main, H₀ = 40 − 500x, 2.0·10⁵ Pa each | (A, A) | 0.027392 each, s 0.846245 | G = [[9.4236, 12.9646], [12.9646, 9.4236]] m per unit speed; det −79.28; NI −0.893 | not P | ZS `s1` |
| same | (A, OPEN) | 0.007674 / 0.045278 | G 13.2777; r 11.5099 | P | ZS `s1` |
| same, K = 2 spools, +100 Pa | (A, A) | 0.024553 / 0.024739 | NI 0.6123; eigenvalues 5.61, 24.14 | P, unique from 16 of 16 starts | ZS `s1` |
| ZE's family (curve_a, R1 10 m, 5 m suctions, R2 20 m, ideal tee, main with exit): 0.5 m bare spools, main 30 m, 250 kPa | (A, A) | 0.016674 each | G = [[15.8179, 19.3934], [19.3934, 15.8179]]; det −125.9; NI −0.5032 | not P | ZE `e1`; ZJ `j1` |
| same family, 3 m bare, main 300 m, 250 kPa | (A, A) | 0.005329 each | det −91.45; NI −0.155 | not P | ZE `e1`; ZJ `j1` |
| same family, 2 m bare, main 30 m, 350 kPa | (A, A) | 0.028287 each | det −165.2; NI −0.329 | not P | ZE `e3`; ZJ `j1` |
| same family, 20 m bare, main 30 m, 250 / 255 kPa | (A, A) | 0.011991 / 0.019699 | det 320.7; NI 0.606 | P | ZE `e3`; ZJ `j1` |
| same family, 0.5 m with K = 2, main 300 m, 250 kPa | (A, A) | 0.005311 each | G diag 27.375; det 216.8; NI 0.289 | P | ZE `e1` |
| 3 fitting-less boosters, ideal tees | (A, A, A) | 0.0169855 / 0.0182867 / 0.0182867 | minors 7.93, 7.65, 7.65; −42.52, −42.52, −45.25; det +164.7 | not P | ZS `s4` |
| 3 boosters, K = 2 spools | (A, A, A) | 0.017387 / 0.016836 / 0.016836 | all 7 minors > 0; pair NI 0.581, 0.581, 0.571; full NI 0.282 | P | ZS `s3` |
| 2 boosters, unlike spools (K = 0.5 against none) | (A, A) | 0.036004 / 0.017613 | G = [[9.8192, 13.3761], [11.1793, 11.3516]]; det −38.07; r 2.997, 5.197 | not P | ZS `s5` |
| 2 pressure pumps in series, 1.2 / 2.5 bar | (A, A) | 0.024384 | G = [[30.8472, −12.0705], [16.0853, 22.1565]]; det 877.6 | P (series stays allowed) | ZS `s7` |
| Crane header (ZJ's family: ZE's with a Crane tee, PU1 → run inlet, PU2 → branch), 20 m bare, 250 / 250 kPa | (A, A) | 0.014442 / 0.015530 | G = [[23.6939, 14.1188], [13.8638, 23.5069]]; det 361.23 | P | ZJ `j4c` |
| Crane, 3 boosters, 20 m bare, 350 kPa each | (A, A, A) | 0.011164 / 0.011985 / 0.019708 | det 10,776; every minor > 0 | P | ZJ `j4c` |

#### 5.11.5 Stability and multiplicity: the index sum

**The frame (ZS).** Freeze every element except the speed-controlled pumps of the zone at its state. The steady states of those pumps are then the solutions of the box-constrained variational inequality VI(B, y(s) − y_set) on B = ∏[s_min,i, s_max,i]: a regulating pump is interior with y = y_set; OPEN (or CLOSED with its drive wound up) is at s_max with y ≤ y_set; MIN_SPEED (or CLOSED at s_min) is at s_min with y ≥ y_set. This holds modulo the 2·Htol bands and the x_mono band of §5.6 item 6.

**The index sum** (derived by ZJ; ZS cites the general theorem). For a continuous y on a box, the homotopy to y = s − s₀ for an interior s₀ keeps every solution inside B, so the degree of the VI is 1. A nondegenerate solution has index sign D_Z, the determinant of the frame's response over its regulating pumps (§5.11.4; +1 with none regulating). So **the indices of the states of a frame sum to 1**. The generalized Poincaré–Hopf theorem for compact regions gives the same (Simsek, Ozdaglar & Acemoglu 2007; record confirmed through Crossref, the paper not read). *Measured* (ZS `s2_speed_space.py`, `s4_three_complete.py`, `s5_mixed.py`): the sum was 1 in all 9 networks once every state had been found by a speed-space Newton search.

**Consequences** (revised, ZR F2):
1. A state whose frame determinant is negative (D_Z < 0, index −1) has at least two other states in its frame.
2. Among two or more nondegenerate states of a frame, at least one has a negative determinant: the sum of two or more indices of +1 alone would exceed 1. The argument does not say where that state lies; the earlier "two states the drives can hold are always separated by one they cannot" claimed more than it gives.
3. A state that fails S with D_Z > 0 has index +1, and nothing implies companions. That covers S2 through the minors of one order with a positive determinant (PZM6's matrix), S3, and S1 with two or more regulating pumps. *Measured* (ZF `y5_box_vi.py`, affine frames y = Ms + c on [−1, 1]ⁿ with every face enumerated): G′ = [[1, 3], [−3, −1]] (S1 through g′₂₂ < 0, det 8) has its regulating state as its only state; so does the 3×3 [[0.645, 1.079, 1.617], [1.65, 0.326, 0.158], [0.447, 0.833, 0.262]] with c = [−0.362, 0.086, −0.013] (positive diagonal, all three 2×2 minors negative, det +1.567: S2 through the order-2 minors), ZR's example; among 200,000 random 3×3 frames, 94 had a positive diagonal, all 2×2 minors negative, det > 0 and the regulating state among their states, and in 15 of them it was the only one (ZR counted 228 of 1,848 in its own sample). In all 200,000 the index sum was 1, and every state with a negative determinant had at least two companions.
4. Two holdable states can coexist (index +1 each). S never separates them; only the search does.

So the not-converged texts state companions only where D_Z < 0 (§5.11.10), and for S1 only in the pump's own frame, with the other drives at their present speeds (§5.10).

**Where the iteration lands.** The default start (every pressure pump ACTIVE) of identical boosters is symmetric, and so is the first inner solve, so the error has no component in the unstable antisymmetric mode. *Measured*: ZS `s1` (9 of 16 starts, the all-ACTIVE start among them, end at the unstable (A, A)); ZS `s4` (8 of the 12 converged starts of three boosters end at unstable states); ZE `e1`, ZJ `j2` (the default start reaches the unstable (A, A) on ideal-tee pairs with identical bare spools and equal setpoints of 250 and 350 kPa). The drives leave such a state: *measured* (ZS `s2`, quasi-static integral drives, three tunings, s₁ ± 10⁻⁶), all 6 runs end at (A, OPEN) or (OPEN, A), by the sign of the perturbation.

**C's "+100 Pa moves the split from 0.0274/0.0274 to 0.0077/0.0453"** (§5.6 item 2) is not the sensitivity of one state: at +100 Pa the (A, A) state still exists (0.027577/0.027234 m³/s, det −79.34, *measured*, ZS `s2`), but it is unstable, the lag diverges from it, and the solve lands on a holdable state. With K = 2 spools the same +100 Pa moves the split smoothly, 0.024634/0.024634 to 0.024553/0.024739 (ZS `s1`).

**The diagnostic.** The trace reports the index sum, the signs of D_Z, over the reached state and the valid candidates of the search that lie in its frame (the same statuses of every non-member element and every member that is not a speed-controlled pump, the same branch patterns, every state nondegenerate). A sum other than 1 is printed as "at least one steady state of these pumps was not found". It refuses nothing and raises no flag, because degenerate states (the bands, zero-flow labels) make the count fragile; the fuzz counts it (`findings/index_incomplete`, §9.5). Whether it should ever refuse is a decision for after that count, as Q7's limitation was answered (§14.4).

#### 5.11.6 The zone search

**Candidates.** Every assignment of the members' options other than the reached one: ∏|options| − 1.

| Zone | Candidates |
|---|---|
| 2 pressure pumps | 15 |
| 2 pressure pumps and a fixed pump | 31 |
| 2 pressure pumps and a PRV | 47 |
| 3 pressure pumps, or 2 and two fixed pumps | 63 |
| 3 pressure pumps and a fixed pump | 127 |
| 4 pressure pumps | 255 |

**Order** (deterministic):
1. **Permutations of the reached statuses:** the assignments with the same multiset of statuses, each member's status among its own options.
2. Then by **Hamming distance** from the reached assignment.
3. Then lexicographically by member id, with CLOSED < OPEN < MIN_SPEED < ACTIVE.

*Measured*: with permutations first, the second state was candidate 1 in all 5 networks whose reached state passed S (ZJ `j5_variants.py`), and candidate 1 or 2 after S's refusal (4 networks); ZE (`e13_orders.py`): a median of 1 pinned solve for two boosters and 2 for three, against 13 and 23 in Hamming order.

**The candidate solve.** `run_outer_loop(built, pinned={member: frozenset({status}) …}, guards=False, warm=<the reached OuterLoopResult>, branch_restarts=False, search=<the solve's SearchBudget>)`:
- members start at their pin, and a rule that would move one leaves it there (§5.10's pinned semantics);
- every other element follows its rules from its reached status, branch pattern, K and flows (`_warm_start`, `status.py:1865`), with the fallbacks as in any solve;
- each inner solve runs at most min(`CANDIDATE_MAX_ITERATIONS` = 30, `maxIterations`) Newton iterations, at the project's tolerance (ZR F1; below);
- one attempt: no branch restart (`branch_restarts=False` skips the restart at `status.py:1667-1686`) and no cold retry. If it does not converge, including an inner solve stopped at the cap, the candidate has **no state found**: counted, and its assignment listed in the trace (§5.11.10), never a second state.

*Why one warm attempt.* *Measured* (ZJ `j3_candidates.py`, 1,455 candidates in 49 networks, rule set Z): 141 warm attempts failed, 138 of them with a held (ACTIVE) pin; a cold retry converged in 21 of those, and only one of these was rule-valid, (A, A, X) on an ideal three-booster header, which is control-unstable (NI −0.18); warm attempts without branch restarts found every other valid candidate. Over the 49 networks (ZJ `j5_variants.py`), the stable second states found were identical with and without restarts and retries, and for three-member zones the single attempt took 16 % fewer Newton iterations at the median and 52 % fewer at the maximum.

**At a system-curve point,** a candidate starts from the same candidate's converged pinned solve at the previous point, else from the point's own state. *Measured* (ZJ `j6_curve.py`, 41-point curves of PU1 on three-booster headers): 18,160 → 9,686, 11,945 → 6,805 and 3,936 → 2,394 Newton iterations of the search per curve; the second states found agree once the criterion's at-rest test is applied (ZJ `j6c_point.py`: the one point where they differed, q = 0.036 m³/s on the Crane 2 m header, is a pump regulating at 2.3·10⁻⁵ m³/s against the same pump closed, one physical state by `at_rest_more`).

**Limits** (revised, ZR F1: the earlier design bounded only the number of candidates, so a failing candidate cost its project's `maxIterations`, up to 1,000, per inner solve, and a project with searched zones could run past the 45 s request budget and return no result at all). Four counts, none a time:
1. `ZONE_SEARCH_LIMIT` = 63 candidate solves per searched zone per solve: every zone of up to three speed-controlled pumps (or two and a PRV or PSV, or two and up to two fixed pumps) is searched completely by count.
2. `ZONE_SEARCH_POINT_LIMIT` = 15 per searched zone per system-curve point: a zone of two pressure pumps is searched completely at every point (§5.11.9 for why it is lower).
3. `CANDIDATE_MAX_ITERATIONS` = 30 Newton iterations per inner solve of every pinned solve (the candidates, V3–V5 and §5.9's swap test), or the project's `maxIterations` if lower. *Measured* basis: in ZJ's 1,020 candidates of three-member zones every rule-valid candidate converged within 14 iterations per inner solve, and a cap of 30 loses none (ZJ `j7_inner_its.py`); in ZF's re-runs, uncapped at `maxIterations` 100 (six networks) and 1,000 (three of them) and with the cap, the rule-valid candidates found were identical on every network, among them the multi-state PZM1 ((A, X), (X, A) from (A, A)), PZM3 ((A, C, C), (C, A, C)) and ZJ's three-booster ideal header ((A, C, X), (C, X, A), (X, C, A)) (ZF `y1_cap.py`).
4. A **search budget** of Newton iterations, shared in a fixed order by every pinned solve and every S solve at a candidate: `SEARCH_NEWTON_BUDGET` = 4,000 per solve (all zones, in the order of their smallest member id, after §5.9's swap test and V3–V5), and `CURVE_SEARCH_NEWTON_BUDGET` = 10,000 per system curve (all its points, in increasing flow, and all zones). The main solve, rule S at the reached state and the points' own solves are not charged. The budget is checked before every inner solve, which runs at most the iterations left, so it is never exceeded (`SearchBudget`, passed as `search=` to `run_outer_loop`). Each pump's curve has its own budget, so a curve is the same whether `POST /api/v1/system-curve` or a solve with `includeSystemCurve` computes it.

The cost of one pinned solve is then at most (30 + 4b) × 30 Newton iterations, b being the Crane branches: `MAX_OUTER_ITERATIONS` = 30 counted inner solves, plus the uncounted ones that hold or release zero-flow legs, at most two holds and two releases per branch (`MAX_DEAD_CLOSURES` = 2, `status.py:1052`, `1645-1652`); without the cap it was that many times `maxIterations` (the earlier "about `maxIterations`" was wrong: ZJ's `j3` records show failed single attempts of 100, 113 and 157 Newton iterations at `maxIterations` 100, and up to 257 with branch restarts). The cost of the whole search is at most the budget. Its values were set from the measurements of §5.11.12: with the cap, the whole search of the costliest measured three-member zone takes 1,734 Newton iterations and of the costliest 41-point curve 7,956, so one three-member zone per solve, and every measured curve, are searched completely. Because every bound is a count, results do not depend on machine speed or on how many CPUs serve the request, short of the backstop. The 45 s request budget remains that backstop (`check_budget()` in every outer iteration, `status.py:1655`, and every Newton iteration, `gga.py:739`); with the search bounded by the budget, only a network whose own Newton iterations are slow enough for 4,000 of them to approach 45 s can reach it during a search, which gate item 7 of §5.11.12 checks on the largest networks measured; such a request fails with the deadline error, as any solve that slow does today, never with a partial search reported as complete. The search stops at the first second state (§5.11.7).

**Beyond a limit** the candidates left are not solved, and the result says so:
- in a solve, the warning flag **`STATE_SEARCH_INCOMPLETE`** on each pressure member of the zone, with the counts and which limit stopped it (the candidate limit, or the budget, with the candidate at which it was spent; a zone the budget leaves wholly unsearched gets the flag too), and a trace line;
- a V3–V5 or swap test that the spent budget leaves unrun: the same flag on its pump, naming the test;
- at a system-curve point, the point keeps its head and its message says the search was incomplete, or not run because the curve's budget was spent (§5.11.9).

The search stops by count, so where it stops is the same on every machine; the converged main result is kept.

Converging with a warning, rather than refusing, is decided by GOALS §4.6 (an unreliable result is flagged) and by the owner's answer, which refuses where a second state is found (Appendix A, R20).

#### 5.11.7 The second-state criterion (exact)

A candidate c is a **second steady state** of the reached state r when all of these hold:
1. **Converged:** its single warm pinned solve converged, and neither §5.8's floating rule nor §5.9's over-control test refuses it (a floating section with flow has heads on an arbitrary level, which no comparison of heads can judge).
2. **Every rule holds:** every member's *unrestricted* rules keep its pinned status at the solved heads and flows: §5.4 for pressure pumps (σ0 by C1), §4.5 of the proposal for flow pumps, pumpstatus for fixed pumps, prvstatus and psvstatus for valves. The non-members followed their rules to convergence.
3. **It differs in flowing state** from r, by `state_search.multiple` (`tests/differential/state_search.py:183`): some connection carrying flow (more than 10⁻⁹ m³/s) in either state has a flow, or an EGL at its ports, outside D6 (0.5 %, or 10⁻⁹ m³/s, or 0.01 m), and neither state is the other with more of the network at rest (`at_rest_more`, `state_search.py:177`). Labels of elements at zero flow, with the section beyond at rest, are one physical state (§5.6 item 4, Q6 (a)).
4. **It is control-stable:** S at the candidate's own state (2|A_c| inner solves) finds G′ a P-matrix. A candidate that meets 1–3 but fails S is not a state the drives can hold: it is listed in the message and the trace ("also satisfies the rules, but its drives cannot hold it") and does not by itself refuse the solve.
5. **It is not the documented x_mono pair:** one pressure member ACTIVE in one state and MIN_SPEED in the other, with Q/s_min > x_mono and everything else equal (D11's path rule, as PCF10 pins it).

A found second state ends the search, and the solve is **not converged** (§5.11.10).

**Why (4) is decided, not asked** (Appendix A, R21). The owner's answer refuses a reached state that is "unstable as a control system", so such a state is not one a station settles in, whether reached or found; counting it would refuse states that are correct. The index sum (§5.11.5) shows that a found state whose frame determinant is negative, beside the reached one, implies at least one further state in the frame, which the search looks for and the trace reports when missing; a found state that fails S with a positive determinant implies nothing more (§5.11.5, consequence 3; ZR F2). *Measured*: every rule-valid state that the pinned solves missed was control-unstable (ZE `e6_oracle_check.py`, `e7_random.py`: 124 random networks against an oracle that scans the header head without the GGA; ZJ `j3_candidates.py`).

#### 5.11.8 Interaction with §5.9 and §5.10

- **V1:** for a regulating pump, S replaces it; for a lone pressure pump at a limit, its r comes from S's solves by the Schur complement (§5.11.4), equal to V1's definition in exact arithmetic.
- **V2** is S with one regulating pressure pump (exit S1, V2's message).
- **V3, V4, V5** run only for a pressure pump that is the only member of its zone. In a searched zone their pinned sets are among the candidates: V3's {MIN_SPEED, CLOSED} and V4's and V5's {OPEN} are candidates at Hamming distance 1.
- **V6 is removed.** Its pinned solves (CLOSED from running, the running statuses from CLOSED) are distance-1 candidates of the search, which also tries every other member's alternatives. PN2's network (one booster beside an active PRV, 1 m spools, equal setpoints) has two rule-valid states, A (the booster regulating, the PRV closed) and B (the PRV active, the booster closed), each the other's statuses exchanged (*measured*, PN `r6_prv_parallel.py`, §5.10), so the search's candidate 1, the one permutation, meets the other (derived from the order). ZE's network of two boosters beside a PRV (1 m spools, 250 kPa each; PZM4) has three rule-valid states, each a permutation of the others (*measured*, ZE `e10_mixed.py`), so the search meets a second one among its first two candidates (derived from the order); with 20 m spools that network's state is unique (PRV active, both boosters closed; PZ7). (Revised, ZR F9: the earlier text gave PN2's network ZE's three states.)
- **V7** becomes exit S5.
- **§5.9's over-control test and swap test** run before S and the search, unchanged.
- **Two pressure pumps holding the same node through zero-loss paths** cannot be modelled exactly: every port has one connection of positive length (`models/piping.py:94`), and the GGA rejects a node held twice (`gga.py:459`) or a held node joined by head-offset links (`gga.py:597`). In the limit of vanishing spool losses the split is **not** undetermined: each port's static head is P_i = H_T − c_iQ_i², which fixes Q_i, and the symmetric state is control-unstable. *Measured*: ZE `e12_zero_loss.py`, bare spools of 2, 0.5, 0.1 and 0.02 m at 350 kPa, NI −0.329, −0.498, −0.547 and −0.558 (ZJ `j1` reproduced all four); ZS `s10_zero_loss.py`, 0.01 m, det −124.86, eig(Z − C) −46.18 against −2c_dQ = −46.26. S refuses it with exit S2, not the over-control text; a singular G′ (exit S4) carries the over-control text.

#### 5.11.9 System-curve points

At each point:
- the viewed pump is a fixed flow, so it is neither a member nor in A;
- the other pumps keep their controls, and warm starts carry their statuses (§7);
- S, V1 and V3–V5 for lone pressure pumps, and the zone search run as in a solve, with `ZONE_SEARCH_POINT_LIMIT` = 15 per zone, the cap of 30 per candidate inner solve, candidates warm-started from the previous point (§5.11.6), and one `CURVE_SEARCH_NEWTON_BUDGET` = 10,000 Newton iterations for the whole curve, spent in increasing flow.

A point that S or the search refuses has no head, with the not-converged message ("two steady states …" or "the drives cannot hold …"), as D10's points without a head. A point whose search reached a limit keeps its head; on `POST /api/v1/system-curve` its `message` says "the search for other steady states at this flow solved 15 of its {m} candidate states", or, once the curve's budget is spent, "the search for other steady states at this flow solved {n} of its {m} candidate states: the curve's search budget (10,000 Newton iterations) was spent" (n may be 0 at the later points), and in a solve's embedded curve (`includeSystemCurve`, points without messages) the viewed pump's trace counts such points and names the flow at which the budget was spent. `SystemCurvePoint.message`'s description becomes "why the point has no head, or a note on its head ('' when there is none)"; for projects without a searched zone it stays '' at every point, so C2's corpus identity holds.

**Why a lower limit at points.** A zone of k pressure pumps has k − 1 members at the points of one of its pumps. *Measured* (ZJ `j6_curve.py`, Newton iterations per 41-point curve of PU1, previous-point warm starts): three boosters on a Crane header with 2 m bare spools: points' own solves 3,989, S 430, search 9,686; with 20 m spools 1,261, 866 and 6,805; on an ideal header with 20 m spools 312, 336 and 2,394. A four-booster zone at 63 candidates per point would cost about 41 × 2,149 ≈ 88,000 Newton iterations (derived from the three-member median at `maxIterations` 100), beyond the 45 s budget on the measured machine, so the whole curve would fail; at 15 per point it keeps every point, the truncated ones saying so. The curve's budget bounds the rest (ZR F1): *measured* (ZF `zj/y3_curve.py`, ZJ's `j6` cases re-run, load average 0.9–1.1), the search of PU1's 41-point curve on the three-booster Crane header with 2 m bare spools costs 9,686 Newton iterations (12.0 s) at `maxIterations` 100 and 14,356 (17.0 s) at 1,000 without the cap, and 7,770 (10.4 s) and 7,956 (10.8 s) with it; with 20 m spools 6,805 (8.8 s), 11,305 (14.5 s), 6,455 (9.1 s) and 6,455 (10.0 s); on the ideal header with 20 m spools 2,394 (3.6–3.7 s) in all four. The points where a second state was found were the same with and without the cap. ZR measured 9,146 against 13,646 for its own previous-point curve search at 100 and 1,000 (`x5_curve.py`, cited by ZR, not in its directory).

#### 5.11.10 Traceability texts

Numbers print as the existing traces print them; constants with `:g`.

**Pump trace, for each pressure pump in a searched zone or in A:**
1. **Zone:** "Pressure zone: the discharge port of {PU1} lies in the zone that also holds {PU2 (discharge pressure), FP1 (fixed speed), PRV3 (outlet)} (the part of the network between reservoirs, reference nodes, pumps, active or failed-closed control valves, closed isolation valves and locked-closed check valves)."
2. **Search:** "Zone search: {n} of {m} candidate states of the members' statuses solved with those statuses held, permutations of the statuses reached first, each network solve at most 30 Newton iterations ({f} with no converged solution: {their assignments, each as 'PU1 closed, PU2 at minimum speed, PU3 regulating'}); no other steady state that satisfies every rule, differs in flow and that the drives can hold was found." The assignments without a converged solution are listed in full (at most 63 per zone): the fuzz classifies a missed state by them (§9.5, class 6). With unstable valid states: "; {assignment} also satisfies the rules, but its drives cannot hold it (G′ not a P-matrix)". With the candidate limit reached: "… solved {63} of {m} (ZONE_SEARCH_LIMIT 63); the other {m − 63} were not solved." With the budget spent: "… solved {n} of {m}: the search budget of this solve (4,000 Newton iterations) was spent during candidate {n + 1} ({assignment}); the other {m − n} were not solved." A zone the budget reaches spent: "Zone search: not run; the search budget of this solve (4,000 Newton iterations) was spent on the tests and zones before it; its {m} candidate states were not solved." With the index count: "The indices of the states found in this frame sum to {n}{; at least one steady state of these pumps was not found}."
3. **Stability:** "Control stability: the response of the regulating pumps' controlled values to their own heads, G′_ij = ∂y_i/∂e_j (the change of pump i's discharge static head, or flow, per metre of head added to pump j at its running speed, the others at their running speeds; solves at ±0.0001 m to a flow tolerance of 1e-12), is [[0.278, 0.180], [0.180, 0.278]]; every principal minor is positive (Niederlinski index 0.58): a decentralized integral control of the drives exists that holds this state, also with any drive out of regulation (Kariwala, Forbes and Meadows 2005). r = {r} for this pump with the others at their speeds."

**Not converged, a second state (search):**

> two steady states in the pressure zone of PU1, PU2: the state reached has PU1 regulating at speed 0.807 (0.0172 m³/s) and PU2 at maximum speed (0.0389 m³/s); with PU1 at maximum speed (0.0389 m³/s) and PU2 regulating at speed 0.807 (0.0172 m³/s) every rule also holds, the flows differ and the drives can hold it. Which one a station settles in depends on its controllers, which a steady-state model does not have (zone search, candidate 1 of 15). Give the pumps setpoints further apart, add a fitting or check valve that loses more than one velocity head on each discharge, or run all but one at fixed speed.

**Not converged, S** (exits S1–S5; values in braces; revised, ZR F2: companions are stated only where the index argument gives them, §5.11.5):
- **S1:** V2's message (§5.10). With one regulating pump its companion clause is "with every other element as solved, at least two other steady states then exist for this pump …"; when S1 names one of two or more regulating pumps, the clause is "with the other regulating pumps held at their present speeds and every other element as solved, at least two other steady states then exist for this pump …" (its own frame), never a claim about the zone's frame.
- **S2, through the determinant** (det G′_BB resolved negative):

  > the pumps {PU1, PU2} regulate their discharge pressures in a state their drives cannot hold: in the response of their port pressures to their heads the determinant for {PU1, PU2} is {−0.0245} (Niederlinski index {−0.329}), so whatever their controllers' tuning the drives leave this state ({PU1: regulating, 0.028287 m³/s, speed 0.893; PU2: regulating, 0.028287 m³/s, speed 0.893}).{ With every other element as solved, at least two other steady states of {PU1, PU2} then exist (the determinant of their frame is negative, and the indices of a frame's states sum to 1).} {With PU1 at maximum speed and PU2 regulating at speed 0.807, every rule holds and the drives can hold it. | None that the drives can hold was found ({n} of {m} candidate states solved).} A discharge connection that loses more than one velocity head of its own pipe (the check and isolation valves of each pump, or a Crane tee) can make such a set holdable; on one header node it does (§5.11.4).

  The companion sentence is printed once for each zone Z of the block whose frame determinant D_Z is resolved negative (§5.11.4), naming that zone's regulating pumps. For a block that lies within one zone, as boosters on one header, D_Z has the sign of the block's determinant wherever the zone's other blocks pass S, so it prints. When the block spans zones (series pressure pumps) and no D_Z is negative, it is left out.
- **S2, through the minors of one order** (det G′_BB positive, every principal minor of order m negative or unresolved):

  > the pumps {PU1, PU2, PU3} regulate their discharge pressures in a state their drives cannot hold: in the response of their port pressures to their heads every principal minor of order {2} is negative or zero ({−42.52 for PU1, PU2; −42.52 for PU1, PU3; −45.25 for PU2, PU3}), so whatever their controllers' tuning the drives leave this state ({states}). {With … every rule holds and the drives can hold it. | None that the drives can hold was found ({n} of {m} candidate states solved).} A discharge connection that loses more than one velocity head of its own pipe (the check and isolation valves of each pump, or a Crane tee) can make such a set holdable; on one header node it does (§5.11.4).

  No companion sentence: the state's index is +1, and it can be the only state of its frame (§5.11.5, consequence 3).

- **S3:**

  > the pumps {…} can hold this state only while every one of them regulates: with {PU3} at a fixed speed (at a speed limit, or out of regulation) the drives of {PU1, PU2} are unstable (principal minor {…}); no tuning of their speed controllers holds it with integrity (Kariwala, Forbes and Meadows 2005)

- **S4:**

  > the regulating pumps {…} do not independently set their port pressures (their response is singular to within 1e-06): their speeds are undetermined (over-controlled)

- **S5:**

  > the response of the regulating pumps could not be computed: the solve with '{PUj}' raised by 0.0001 m did not converge ({gga message})

- A block larger than 12 pumps: "the stability of {n} coupled regulating pumps is not assessed (more than 12)".

**Flag `STATE_SEARCH_INCOMPLETE`** (warning, new code; the flags audit; web `flag-text.ts`):

> the search for other steady states of the pressure zone of {PU1, PU2, PU3, PU4} solved 63 of its 255 candidate states (ZONE_SEARCH_LIMIT); none of them is a second steady state; the other 192 were not solved, so this state is not shown to be the only one

With the budget spent (ZR F1), one of:

> the search for other steady states of the pressure zone of {PU7, PU8, PU9} stopped after {26} of its {63} candidate states: the search budget of this solve (4,000 Newton iterations, SEARCH_NEWTON_BUDGET) was spent; none of those solved is a second steady state; the other {37} were not solved, so this state is not shown to be the only one

> the pressure zone of {PU7, PU8, PU9} was not searched for other steady states: the search budget of this solve (4,000 Newton iterations, SEARCH_NEWTON_BUDGET) was spent on the tests and zones before it, so this state is not shown to be the only one

> the test for a second steady state of {PU3} ({at minimum speed, or held at no flow (V3)}) was not run: the search budget of this solve (4,000 Newton iterations, SEARCH_NEWTON_BUDGET) was spent, so this state is not shown to be the only one

The flag's details carry the zone's members, `solved`, `candidates`, `noStateFound` and `stoppedBy` ("ZONE_SEARCH_LIMIT" or "SEARCH_NEWTON_BUDGET").

**Methods summary** (§8.2): items 4 and 5 are replaced by the texts there.

**References** (pressure list): Kariwala, Forbes & Meadows (2005); Campo & Morari (1994); Skogestad & Morari (1992); Grosdidier, Morari & Holt (1985); Niederlinski (1971); Simsek, Ozdaglar & Acemoglu (2007), where the index sentence prints. The Bentley "one VSP per zone" rule is no longer cited by the method; it stays in `vfd-industry-conventions.md` §2 as context.

#### 5.11.11 Measured outcomes (the prototypes)

**Hand-built networks** (rule set Z; ZE's family: pumps on curve_a, s ∈ [0.5, 1], R1 10 m, 5 m suction lines with a sharp entrance, an ideal tee or two, a main with an exit; ZJ's Crane variant puts PU1 on the run inlet and PU2 on the branch of each Crane tee). Ideal-tee rows list the states of ZE's oracle, a scan of the header head that finds unstable roots too; Crane rows list the states that ZJ's pinned enumeration reached, and pinned solves cannot reach a control-unstable root, so "only" there means "the only one reached by pinned solves" (ZR F7). For the PZ8 row a speed-space scan confirms it (§9.3).

| Network | Rule-valid states (stable unless marked) | Outcome | Who, script |
|---|---|---|---|
| 2 boosters, 2 m bare, main 30 m, R2 20 m, 350 / 350 kPa, ideal tee | (A, A) unstable (NI −0.329); (A, X) and (X, A), 0.017155/0.038930 | refused by S; the search then finds (X, A) at candidate 2 (the order from (A, A): (C, A), (X, A), …; revised, ZR F9) | ZE `e3`; ZJ `j2`, `j3` |
| same, 350 / 350.1 kPa | (A, X) reached; (X, A), 0.038920/0.017185 | refused at candidate 1 (a permutation) | ZE `e3`; ZJ `j3` |
| same inputs, Crane tee | (A, X) only, 0.014794/0.038628 | accepted after the full search (15) | ZJ `j2`, `j5` |
| 2 boosters, 2 m bare, 250 / 250 kPa: ideal tee; Crane tee | ideal: (A, A) unstable (NI −0.327), (C, A), (A, C); Crane: (C, A) only, 0.031574 | ideal refused by S; Crane accepted | ZJ `j2` |
| 2 m bare, main 300 m, 250 / 255 kPa, ideal | (C, A) only, 0.011222 | accepted after the full search | ZE `e3` |
| 20 m bare, main 30 m, 250 / 255 kPa, ideal | (A, A) only, 0.011991/0.019699, s* 0.6195/0.6815 | accepted | ZE `e3` |
| 3 boosters, 2 m bare, main 30 m, R2 25 m, 300/350/400 kPa, ideal | (C, A, X) only, 0/0.006921/0.039058 | accepted; 23 of 63 candidates fail (ZE, with cold retries) | ZE `e4`, `e5` |
| same inputs, Crane tees | (C, A, X) only, 0/0.005278/0.038543 | accepted after 63 candidates | ZJ `j2` |
| 3 boosters, 2 m bare, R2 25 m, 350 kPa each: ideal; Crane | ideal: (C, A, X) reached, (C, X, A), (A, C, X), (X, C, A) stable, (A, A, X) unstable; Crane: (C, A, X) only | ideal refused at candidate 1; Crane accepted | ZJ `j2`, `j5` |
| 3 boosters, 2 m bare, main 300 m, 350 kPa each, ideal | (C, C, A), (A, C, C), (C, A, C) stable; (A, C, A), (C, A, A) unstable (det G −193.1) | refused at candidate 1 | ZE `e4`, `e6`; ZJ `j5` |
| 3 boosters, 20 m bare, 350 kPa each, ideal | (A, A, A) only, 0.01427/0.01427/0.01613, NI 0.376 | accepted | ZE `e4` |
| 2 boosters + a fixed pump, 2 m bare, 300 kPa, ideal | (FP:X, A, A) unstable (det −88.5); (FP:X, A, C), (FP:X, C, A) | refused by S | ZE `e10` |
| same, 20 m bare | (FP:X, A, A) only, det 628.7 | accepted | ZE `e10` |
| 2 boosters + PRV from RH 60 m, 1 m spools, 250 kPa each (PN2's class) | (PRV:C, PU1:C, PU2:A), (PRV:C, PU1:A, PU2:C), (PRV:A, PU1:C, PU2:C) | refused: the other two are permutations of the reached state, so candidates 1 and 2 (derived from the order) | ZE `e10` |
| same, 20 m spools | (PRV:A, PU1:C, PU2:C) only | accepted | ZE `e10` |

**Random networks.**
- **ZE** (`e7_random.py`, `analyze.py`; ideal tees; draws `random.Random(f"zone:{k}:{seed}")`, seeds 0–99 for two boosters and 0–23 for three): against an independent oracle that scans the header head with the solver's connection laws and the §5.4 rule functions, without the GGA: every main solve converged and reached a state in the oracle's list; 17 two-booster networks had 3 valid states (2 stable), two three-booster networks had 3 (2 stable) and one had 9 (4 stable); 8 reached states failed S (identical pumps, equal setpoints, equal spools without a K ≥ 1 fitting); **no stable second state was missed and nothing was refused falsely**. The oracle's lesson for the reference author: a uniform grid missed a stable (X, A) whose rising piece spans about 2 mm of header head; the scan must include each monotone piece's domain ends.
- **ZJ** (`j3_candidates.py`, `j5_variants.py`; ZE's draws with the tee model drawn Crane or ideal with equal probability, seeds 0–29 for two boosters and 0–11 for three, plus 9 hand-built networks; real `run_outer_loop`): 2 main solves cycled (both Crane, reported not converged by the real outer loop); of the other 49, the 28 on Crane tees had no second rule-valid state reached by pinned solves, and every reached state passed S; of the 21 on ideal tees, 9 had a stable second state (4 of them reached an unstable state first) and 1 had an unstable valid candidate.

#### 5.11.12 Cost and the performance gate

**Extra work per solve:**
- **S:** 2|P| warm inner solves at the reached state, and 2|A_c| at each valid candidate. *Measured*: 3 Newton iterations per perturbed solve at every state (ZJ `j1`; ZS `s4c`: 4 solves, 12 iterations, for two boosters; 6 solves, 18 iterations, for three).
- **The search,** per searched zone: at most 63 single-attempt pinned outer solves, each at most (30 + 4b) × 30 Newton iterations (§5.11.6); a converging candidate costs a median of 15 Newton iterations (more on Crane tees, whose K iterates; *measured*, ZJ `j3`), a failing one stops at the cap (*measured*, ZF `y1_cap.py`: the costliest whole candidate 34 Newton iterations on PZ8 and 66 on PZ5 on Crane tees, two and three inner solves). All the pinned solves of a solve together cost at most `SEARCH_NEWTON_BUDGET` = 4,000 Newton iterations, those of a system curve at most 10,000.

*Measured before the cap* (ZJ `j5_variants.py`, Newton iterations of the whole search at `maxIterations` 100, the single warm attempt; wall times from the same records' `ms`, under ZJ's load, which it did not record, at 2.0–2.4 ms per Newton iteration at the median):

| Zone | Networks | Median | Max | Wall time, median and max | With branch restarts and a cold retry (median, max) |
|---|---|---|---|---|---|
| two pressure pumps | 34 | 295 | 534 | 0.73 s, 1.08 s | 302, 1,017 |
| three pressure pumps | 15 | 2,149 | 3,561 | 4.09 s, 10.28 s | 2,549, 7,457 |

The earlier draft turned these iterations into times at about 1 ms each and quoted "at most 0.5 s" for a two-member zone; the records' own wall times are the ones above (ZR F1).

*Measured with the cap and the budget* (ZR F1; ZF `y1_cap.py`, `y2_multizone.py`, `y4_budget.py`, on the reviewer's prototype `rz.py`: members pinned as fixed controls with the §5.2 `LinkState` inside the real `run_outer_loop` of a clean `f9d402b` copy with the C1 patch; every candidate other than the reached assignment, one warm attempt without branch restarts; wall time by `perf_counter` around the candidate solves only; load average 0.6–1.1 on the 4-CPU machine). Newton iterations and wall time of the whole search; the rule-valid candidates found were the same in every column of a row:

| Network (reached state) | Candidates | `maxIterations` 100, no cap | 1,000, no cap | Cap 30 (any `maxIterations`) |
|---|---|---|---|---|
| PZ8: two boosters on a Crane tee, 2 m bare spools (A, X) | 15 | 478, 0.71 s | 1,599, 1.72 s | 268, 0.30 s |
| PZM1: two boosters on an ideal tee (A, A) | 15 | 294, 0.29 s | — | 154, 0.18 s |
| PZ5: three boosters, ideal tees (C, A, X) | 63 | 2,769, 3.23 s | 20,095, 20.72 s | 1,073, 1.32 s |
| PZ5's inputs on Crane tees (C, A, X) | 63 | 3,553, 3.98 s | 14,334, 16.65 s | 1,711, 2.72 s |
| PZM3: three identical boosters, ideal tees (C, C, A) | 63 | 2,190, 2.42 s | — | 1,058, 1.40 s |
| ZJ's three-booster ideal header, 350 kPa each (C, A, X) | 63 | 2,791, 2.90 s | — | 1,074, 1.26 s |
| Three zones of PZ5's inputs on Crane tees in one project (C, A, X) each | 189 | — | 42,980, 49.55 s | 5,114, 6.84–7.22 s; with the 4,000 budget: 4,000, 5.95 s, stopped during the third zone's 27th candidate |

ZR measured the same counts within 1 % on its prototype without the C1 patch (its PZ8 482 and 1,602; PZ5 2,769 and 20,095; PZ5 on Crane tees 3,565 and 14,369). The main solves took 0.015–0.066 s. So, with the cap, a two-member zone adds about 0.2–0.3 s to a solve and a three-member zone 1.3–2.7 s, at any `maxIterations`; without it, one three-member zone took up to 20.7 s at `maxIterations` 1,000 and three of them 49.6 s, past the 45 s request budget (ZR's derived claim, now measured). The search of a 41-point curve of a pump in a three-booster zone takes 2,394–7,956 Newton iterations and 3.6–10.8 s with the cap (§5.11.9).

**Consequence for PRD §4.2.** A project with a searched zone of three or more members can exceed the 1 s target for simple systems (1.3–2.7 s measured with the cap). The search's breadth is what the owner's answer asks for, and correctness outranks usability (GOALS §3), so the search is not narrowed to meet the target; PRD §4.2 gains a note in C2 ("a project whose pressure zone holds three or more pumps or pressure-control valves is searched for other steady states, which can take several seconds"). The cap on candidate inner solves, the earlier draft's first remedy, is built (§5.11.6, ZR F1). The remaining measured remedies, in order, if the gate below fails (none is built in slice 2):
1. **Symmetry** (ZE): candidates that swap interchangeable members (equal data, identical connections to the same reservoir or ideal-tee node) are solved once: 15 → 9 for two identical pumps, 63 → 19 for three. Never on a Crane header, whose ports have roles.
2. **ZE's monotone-network certificate and corner pruning** (§5.11.13): ideal tees only.
3. **A smaller search budget,** measured on the fuzz first: more results flagged `STATE_SEARCH_INCOMPLETE`, never a wrong one.

**The gate** (stated before the build runs; measured on the reference machine, 4 CPUs, 3 workers; wall times quoted as measured, with the load average, never as iterations times a per-iteration time; recorded in TSD §5.2):
1. Every corpus project, the Crane-tee ladders and every `pressure_control` fuzz seed solve within the 45 s budget, S, V1–V5 and the search included, at their own solver settings and again with `maxIterations` 1,000 (C0's `corpus.py --solver-options max_iterations=1000`; ZR F1).
2. Projects without a searched zone meet PRD §4.2 as before.
3. Projects whose searched zones have two members meet PRD §4.2 (under 1 s below 20 components), at `maxIterations` 100 and 1,000 (*measured*: PZ8 0.30 s of search and 0.04 s of main solve).
4. Projects with one three-member zone solve in under 5 s, at `maxIterations` 100 and 1,000 (*measured*: 2.72 s of search, PZ5 on Crane tees).
5. **Several searched zones** (ZR F1): PZM8 (§9.3), three three-booster Crane zones at `maxIterations` 1,000, solves in under 10 s, its search stopping at the budget with `STATE_SEARCH_INCOMPLETE` on the third zone (*measured*: 5.95 s of search, 0.04 s of main solve).
6. A 41-point `POST /system-curve` for a pump in a zone of up to three pressure pumps finishes in under 30 s, at `maxIterations` 100 and 1,000 (*measured*: 10.8 s of search and 3,905 Newton iterations of the points' own solves on the costliest case).
7. **The search budget fits the request budget:** on the largest network of the corpus, the ladders and the fuzz that has a searched zone, 4,000 Newton iterations take under 20 s (measured on that network), so a search cannot be what reaches the 45 s backstop.
8. Recorded: per searched zone, candidates solved, no-state-found counts (and how many stopped at the cap), whether the budget stopped the search, Newton iterations and wall time (median, 95th percentile, maximum), per solve and per curve.

A failure of items 1–7 is recorded with the case named, then the remedies above are measured on the fuzz before one is applied; the 45 s budget is never relaxed.

#### 5.11.13 Limitations, and what is designed but not built

**Limitations** (TSD §12; each one the fuzz meets is a documented class of §9.5, counted and reviewed, not a critical finding, or is stated there as critical; revised, ZR F3):
1. **One attempt per candidate.** A stable state whose candidate's single warm attempt does not converge, also where an inner solve stops at the cap, is missed: §9.5's class 6. A stable state whose candidate's attempt converges to another state would be missed too, but that has not been observed (ZJ `j3`: every rule-valid candidate that any of the warm, cold or restarted attempts found, the single warm attempt found too, except one control-unstable state found only by a cold retry), and in the fuzz it is critical. No stable state was missed in ZE's 124 oracle-checked networks or ZJ's 49 networks, but that is not a proof.
2. **Zones are searched one at a time.** A multiplicity that needs members of two zones to change together, as across two zones joined by a PRV or PSV that ends open, is not refused: §9.5's class 5. One that needs a non-member pinned is v1's status-rule multiplicity, class 4.
3. **S is a condition on steady-state gains.** Drive dynamics, and the PRV, PSV and FCV loops, are not modelled.
4. **The limits and the budget** leave larger zones, or the later zones of a project, partly searched or unsearched, flagged.
5. **The index sum** is a diagnostic, fragile at degenerate states.
6. **Drooping curves** (§5.6 item 5) break the frame's unique hydraulic solution that §5.11.5 assumes.

**Remedies stated before the fuzz runs** (ZR F3; each a design change for the owner, measured on the fuzz before it is applied, never added after the results are seen): a stable second state in class 6 → a second attempt for a candidate without a converged solution, from the cold start with the members pinned (ZJ `j3`: cold retries converged in 21 of 141 failed warm attempts; restarts and cold retries together cost 19 % more Newton iterations at the median, ZJ-3); in class 5 → a joint search of the zones involved, their members' options multiplied, within the same limits; a critical "converged elsewhere" finding → the same second attempt, for candidates whose attempt converged with a member's rule failing.

**Designed by ZE, not built (Later; first candidates if the gate fails):**
- **A uniqueness certificate.** Where every element of the connected region is a monotone two-terminal law (pipes, open valves, check valves, ideal tees and wyes, pumps whose curve does not rise, PRVs, PSVs, FCVs; no Crane branches) and every held source's discharge chain loses at least one port velocity head in fittings, a discrete maximum principle proves one steady state (ZE's proof: each pressure pump with its chain selects φ = max(0, clamp(Q_A(H_T), Q_N, Q_X)), monotone in its end heads; a pipe crossing the boundary of {δ > 0} contradicts equal net flows). *Measured* (ZE `e7_random.py`): 23 of 23 certified random networks unique and stable. It never applies on the web app's Crane headers.
- **Corner pruning** (ideal tees only): a candidate with held pins is refuted by fixed-law corner solves under a comparison principle. *Measured* (ZE `e9_corners.py`, `e13_orders.py`): no valid state refuted in 125 networks; 14.0 → 9.5 and 57.3 → 31.1 pinned solves on average.
- **Symmetry**, above.

---

## 6. Edge cases

| # | Configuration | Handling | Expected outcome (evidence) |
|---|---|---|---|
| 1 | Short discharge connection that itself has an exit or expansion loss (r_ref slightly above 1) | C1 | Active in 6–9 iterations. *Measured*, C `p1c_spool.py` (rule set C): lagged, 0.5 and 0.1 m spools end "statuses oscillate (PU)"; exact, 8 iterations, s* 0.968158, p = 250,000.0 Pa. E `exp10`: 22 cases with a 1 m discharge fail lagged, 6–9 iterations exact. |
| 2 | Discharge connection without its own loss (r_ref ≤ 1), network beyond losing a little more than one velocity head (1 < r_tot ≲ 1.2): a short spool into an ideal tee, or a Crane run with no branch flow, then a main with an exit (PN3) | The lag stays (§2.3) | May end not converged at the default 100 iterations, although an active state exists; converges with more iterations. Documented, cases VH7 and PVH5. *Measured* for a PRV (PN `r2_prv_tee.py`, today and with C1 identical): r_tot ≈ 1.11 not converged (113 inner iterations, 326 with a Crane tee); r_tot ≈ 1.23 converged in 82–90 |
| 3 | Network beyond recovers the velocity head (r_tot ≤ 1) | Rule S (§5.11.4) for a regulating pump; §5.10 V1, V3, V4 for a lone pump at a limit | Not converged where S finds the regulating state unstable (V2's message for one pump) or V3/V4 find a second state; accepted where only one limit holds |
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
| 18 | Two or more pressure pumps whose discharges share a zone (Q1 (c)) | §5.11: rule S, then the zone search | Converged where the reached state passes S and the search finds no second state (ZE `e3`: 20 m bare spools; ZJ `j2`: every Crane header measured); not converged where S refuses the reached state or the search finds a second stable state (§5.11.11); converged with `STATE_SEARCH_INCOMPLETE` where the limit leaves candidates unsolved |
| 19 | Discharge connection drawn toward the pump | `held_reference` sign (`gga.py:638-644`) | Same answer (§5.2) |
| 20 | Port elevation differs from the component's | z_d from the port node | *Measured*, C `p17_orient.py` (rule set C): H_set0 = 28.54399 m = 3 + p/(ρg) for a port 3 m up |
| 21 | Multi-segment discharge connection | c_d from the end segment at the port | Case PCF3 |
| 22 | Negative gauge setpoint, or one below the vapour pressure | Allowed within the bounds | `BELOW_VAPOR_PRESSURE` and NPSH as today |
| 23 | Glycol with no vapour pressure | `NPSH_NOT_CHECKED` at s* | As slice 1 |
| 24 | Transient iterates with heads near 10⁹ m | Existing `ENERGY_TOL` floor | Costs iterations, not results (§2.4, fuzzfc_10269) |
| 25 | Status off | CLOSED, fixed | `control.state` off, no setpoint flag |
| 26 | Crane tees nearby | Sequential mode as today | About one outer iteration per saturation (proposal risk 3) |
| 27 | Closed booster, alone in its zone, whose discharge is at or above its setpoint, both heads known, H ≤ S_max + Htol | §5.10 V5 (in a searched zone, the search's candidates) | One pinned OPEN solve: with r > 1 it fails X1 and the closed state stands (PCF7, EP4); with a falling P it holds and the solve is not converged (PN1 network, R2 31 and 33 m) |
| 28 | Booster sharing its discharge zone with an active PRV or another pump that is on | The zone search (§5.11.6; V6 removed) | Not converged where a second state holds: PN2's network (one booster beside a PRV, equal setpoints, r_spool 0.20) has two states, each the other's statuses exchanged (PN `r6`); ZE `e10`'s two boosters beside a PRV with 1 m spools have three (PZM4). The state stands where the spool loses more than its velocity head (PCF14, PZ6, and PZ7, `e10`'s network with 20 m spools: PRV active, both boosters closed) |
| 29 | Identical boosters, equal setpoints, ideal tee, spools losing less than one velocity head | Rule S at the default start | Not converged (exit S2), the message naming a state the drives can hold where the search finds one (PZM1; ZE, ZS, ZJ measured the default start reaching the unstable (A, A)) |
| 30 | Parallel boosters on Crane tees (the web app's default header) | Rule S and the zone search | One valid state reached by pinned solves in every measured network (ZJ `j5`: 28 networks; pinned solves cannot reach unstable roots, and PZ8's speed-space scan found none, ZR); the search costs a full enumeration there (§5.11.12); case PZ8 |
| 31 | Zone of four or more pressure pumps, or three and another member; or several searched zones in one project | The limits and the search budget (§5.11.6) | Converged with `STATE_SEARCH_INCOMPLETE` if no second state is among the candidates solved (63 per zone, 4,000 Newton iterations per solve); at curve points, 15 per point and 10,000 Newton iterations per curve, with a note (PZM7, PZM8) |
| 32 | Pressure pumps in series | Different zones; rule S over both regulating pumps | Converged where G′ is a P-matrix (ZS `s7`: 1.2 / 2.5 bar, det 877.6) |
| 33 | Two pressure pumps practically holding one node (very short bare spools) | Rule S (§5.11.8) | Not converged (exit S2): the split is fixed by the port velocity heads and the symmetric state is unstable (ZE `e12`, ZS `s10`) |
| 34 | `maxIterations` set high (up to 1,000) on a project with a searched zone | The cap of 30 per candidate inner solve and the budget (§5.11.6) | The search costs what it costs at the default; without them one three-member zone took 20.7 s and three zones 49.6 s, past the 45 s budget (ZF `y1`, `y2`; ZR F1) |

---

## 7. System curves

There is no algorithm change (`system_curve.py`), beyond the work in progress of §1.4, which slice 2 builds on:
- **The viewed pump's control is replaced by the forced flow,** whatever its mode (`status.py:319-321`, `394-395`). So H_sys keeps one definition, and the operating point lies on F(s*, ·).
- **Other pressure pumps that are on keep regulating,** and warm starts copy their statuses (`_warm_start`, `status.py:1865-1888`).
- **At each point,** the floating rule, the over-control tests, rule S, the second-state tests (§5.10) for a pressure pump alone in its zone and the zone search run for those other pumps (§5.11.9), the search at most 15 candidates per zone per point, each warm-started from the same candidate at the previous point, with the cap of 30 per candidate inner solve and 10,000 Newton iterations for the whole curve. A point that fails one has no head ("not converged: …"); a point whose search reached a limit keeps its head, and its message says so. *Measured* (ZJ `j6_curve.py`, at `maxIterations` 100 without the cap): a 41-point curve of a pump in a three-booster zone costs 2,394–9,686 Newton iterations of search, against 312–3,989 for its points' own solves; with the cap 2,394–7,956, at `maxIterations` 100 or 1,000 (ZF `zj/y3_curve.py`, §5.11.9).
- **The default range** uses `speed`, the maximum (`default_flow_max`, `system_curve.py:67-71`).
- **The method text** is the existing sentence (`methods.py:163-167`): "A speed-controlled pump's own control is replaced by the fixed flow at each point; other speed-controlled pumps that are on keep regulating; its default range uses its maximum speed." It is true of both modes, so it stays gated on any controlled pump, as today, and a flow-only project's text is unchanged (RVG-14; an earlier draft added a second, pressure-specific sentence).
- **Slice 1's known limitation** (TSD §12 former open item 4, now decided item 8: starved first points) does not arise for a pressure pump: P0 never closes it.

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
- "r = (dEGL_d/dQ_d)/(2 c_d Q_d); the static pressure at the port rises with flow iff r > 1" (Q2 (a)).
- With a regulating set (Q1 (c), §5.11.4): "G′_ij = ∂y_i/∂e_j, the change of pump i's discharge static head (or flow) per metre of head added to pump j at its running speed, the others at their running speeds; held by its drives with integrity iff G′ over the regulating pumps is a P-matrix (every principal minor > 0; the drives speed up on low pressure)".

**Sources:**
- EPANET 2.2 prvstatus and pumpstatus (hydstatus.c);
- Brent (1973);
- Fritsch–Carlson (1980);
- Bentley Fixed Speed Override (URL, proposal §2.4);
- Elhay et al. (2025), doi:10.1017/wat.2025.10005;
- with a regulating set or a searched zone (Q1 (c)): Kariwala, Forbes & Meadows (2005), doi:10.1016/j.automatica.2005.03.024; Campo & Morari (1994), doi:10.1109/9.284869; Skogestad & Morari (1992), doi:10.4173/mic.1992.2.3; Grosdidier, Morari & Holt (1985), doi:10.1021/i100018a015; Niederlinski (1971), doi:10.1016/0005-1098(71)90007-0; and, where the index sentence prints, Simsek, Ozdaglar & Acemoglu (2007), doi:10.1287/moor.1060.0235. The Bentley pressure-zone rule is not a source of the method (Q1 (c));
- CLAUDE.md D12.

**Values:**
- H_set0, c_d, Q_d, H_set(Q_d);
- the port's static pressure P_d·ρg, beside p_set;
- H, F(s_lo(Q), Q), F(s_max, Q), S_min, S_max, σ0;
- s* and the residual F(s*, Q) − H;
- s_lo, x_mono, ψ_min;
- r (with how it was computed) and the pinned outcome;
- with a regulating set or a searched zone (§5.11.10): G′ as printed, its smallest normalised principal minor with its subset, the frame determinant D_Z of each zone, and the verdict; the zone's members, the candidates solved of those it has, the no-state-found count with those candidates' assignments, what stopped the search (none, `ZONE_SEARCH_LIMIT` or `SEARCH_NEWTON_BUDGET`), the Newton iterations it used, any rule-valid states the drives cannot hold, and the index sum.

**State notes** state the inequality that set the state, with its values, as `_control_rule_values` does for valves (`trace.py:1353`). One template per row of §3.2 and per cause (RVG-14; values in braces, numbers printed as the existing notes print them). The first is filled with case PCF1's values:

| State | Cause | Note |
|---|---|---|
| active | regulating with flow | "Active: F(s_lo, Q) − Htol = 7.1991 m ≤ H = 12.7113 m ≤ F(s_max, Q) + Htol = 34.3986 m at Q = 0.0140039 m³/s; the discharge port is held at EGL_d = z_d + p_set/(ρg) + v_d²/(2g) = {z_d} + {p_set/ρg} + {v_d²/2g} m, 150,000 Pa(g) static; s* = 0.638074 on [s_lo, s_max] = [0.5, 1] (residual {res} m); r = {r} > 1 (rule S, §5.11.4)." |
| active | zero flow, discharge dead-ended (plug, closed isolation valve) | "Active at zero flow (its discharge is dead-ended): EGL_d = H_set0 = {h} m; H = {H} m lies within [S_min − Htol, S_max + Htol] = [{a}, {b}] m; s* = √(H/H₀(0)) = {s}; a pump running dead-headed at that speed, not reversed (no PUMP_FLOW_REVERSAL)." |
| max_speed | X1 fails at OPEN | "At maximum speed: the discharge static pressure {p_d} Pa(g) is below p_set = {p_set} Pa(g) by more than ρg·Htol (EGL_d = {e} m < H_set(Q_d) + Htol = {x} m), and H = {H} m ≤ S_max + Htol with Q ≥ −Qtol, so it runs as the fixed-speed pump at s_max = {s}; it returns to regulating once its discharge reaches p_set (EPANET 2.2 prvstatus)." |
| max_speed | P0, starved | "At maximum speed, dead-headed: its suction side reaches no reservoir or reference node, so it cannot hold its discharge; at zero flow EGL_d = {e} m < H_set0 + Htol = {x} m, so its drive runs to s_max = {s} (P0). The suction level is reported as EGL_d − S_max = {..} m, the dead-headed level (v1's convention)." |
| min_speed | N1 fails at MIN_SPEED | "At minimum speed: the discharge static pressure {p_d} Pa(g) is above p_set = {p_set} Pa(g) by more than ρg·Htol (EGL_d = {e} m > H_set(Q_d) − Htol = {x} m) at s_min = {s}, and H = {H} m ≤ S_min + Htol: it runs at s_min (no sleep) and passes more than the flow that would hold p_set; it returns to regulating once its discharge falls to p_set." |
| min_speed | P0, starved | "At minimum speed, dead-headed: its suction side reaches no reservoir or reference node; at zero flow EGL_d = {e} m ≥ H_set0 + Htol = {x} m, so its drive runs down to s_min = {s} (P0). The suction level is reported as EGL_d − S_min = {..} m (v1's convention)." |
| no_flow | both heads known, σ0 = s_min | "No flow: at zero flow its discharge EGL_d = {e} m is at or above H_set0 = {h} m, so its drive is at s_min = {s}, and the head across it, H = {H} m, exceeds that speed's shutoff head S_min = {S} m (EPANET 2.2 pumpstatus).{ For a pump alone in its pressure zone, when V5 ran: 'Re-solved once at maximum speed (V5): {the rule that failed, e.g. its discharge would be at {p} Pa(g), above p_set, so it would regulate}.' For a pump in a searched zone: 'Its pressure zone was searched for other steady states (zone search, below).'}" (Revised, ZR F9: V5 does not run in a searched zone, whose search covers its pinned set.) |
| no_flow | both heads known, σ0 = s_max | "No flow: at zero flow its discharge EGL_d = {e} m is below H_set0 = {h} m, so its drive is at s_max = {s}, and the head across it, H = {H} m, exceeds that speed's shutoff head S_max = {S} m." |
| no_flow | discharge closed off | "No flow, its discharge closed off (no reservoir or reference node beyond it): the head across it is not fixed. Reported at the lowest discharge level that keeps it closed, EGL_d = EGL_s + S_eff = {..} m, S_eff = clip(H_set0 − EGL_s, S_min, S_max) = {..} m, with the speed that level implies, √(S_eff/H₀(0)) = {..} (a convention: v1's dead-headed level, generalised)." |
| no_flow | suction closed off | "No flow, its suction closed off: reported at the highest suction level that keeps it closed, EGL_s = EGL_d − F(σ0, 0) = {..} m, σ0 = {s_min or s_max} because EGL_d = {e} m is {at or above, or below} H_set0 = {h} m (a convention)." |
| — | both sides closed off | No pump result and no trace values, as v1 (`results.py:686-699`); the topology note names the closed-off section. |
| off | status off | "Off: the control is not applied." |

Every second-state test that ran (§5.10) adds a line: the test, r where computed (with "own-state perturbation ±1e-4 m, solves to 1e-12"), and the pinned outcome. Rule S and the zone search add the zone, search and stability lines of §5.11.10.

`test_trace.py` checks each template byte for byte, on a network that reaches that row, and that flow-mode and fixed-pump traces are byte-identical to the C1 tree's.

### 8.2 Methods summary (`methods.py:121-170`)

**Conditions** (RVG-14). Today the whole flow-setpoint text is gated on any control: `controlled = any(pump.control is not None …)` (`methods.py:121`, `125`). It becomes mode-specific:
- the flow-setpoint items (the first, second and fourth of `speed_control_items`) and their references appear when a flow-controlled pump exists, exactly as today;
- the items below appear when a pump with a discharge-pressure control exists;
- the shared items (efficiency and NPSHr by the affinity laws; the system-curve sentence, §7) appear when either exists, once. Order: when a flow-controlled pump exists, today's four items in today's order (the efficiency item third), then the pressure items below; with no flow pump, the pressure items with the efficiency item after their item 2;
- references: the flow list as today, then the pressure list (EPANET 2.2 hydstatus.c prvstatus and pumpstatus; Brent 1973; Bentley Fixed Speed Override; EPANET 2.2's speed efficiency; Elhay et al. 2025; Kariwala, Forbes and Meadows 2005; Campo and Morari 1994; Skogestad and Morari 1992; Grosdidier, Morari and Holt 1985; Niederlinski 1971; with item 5, Simsek, Ozdaglar and Acemoglu 2007; CLAUDE.md D12), without repeats.

So a flow-only project's summary is byte-identical to the C1 tree's, and a pressure-only one carries no flow-setpoint text. `test_methods.py` checks the three cases (flow only, pressure only, both).

**Items** (numbers printed from their constants with `:g`, as the existing items do):
1. **The held-port formulation, the speed recovery and its exactness:** "Speed-controlled pumps (discharge pressure): while the drive regulates, the static pressure at the pump's discharge port is held at its setpoint, EGL_d = z_d + p_set/(ρg) + v_d²/(2g), as an active PRV holds its outlet, and the pump passes the flow that leaves the port. Its speed is the unique root of F(s, Q) = EGL_d − EGL_s on [s_lo(Q), s_max] at the solved flow (Brent's method); this equals solving the speed with the network: it enters only the pump's own head equation."
2. **Limits:** "It regulates while F(s_lo(Q), Q) − 0.0001 m ≤ EGL_d − EGL_s ≤ F(s_max, Q) + 0.0001 m. Above, it runs as a fixed-speed pump at s_max (pressure below its setpoint); below, at s_min (pressure above it; no sleep). It returns to regulating once the port pressure reaches the setpoint (EPANET 2.2 prvstatus). At zero flow its drive is at s_min when the port is at or above the setpoint and at s_max otherwise, and the pump re-opens once the head across it is at most that speed's shutoff head (EPANET 2.2 pumpstatus). Where the flow divided by s_min lies beyond x_mono, for a head between F(s_lo(Q), Q) and F(s_min, Q) the pump held at s_min and passing more flow is a steady state too; the solve starts with the pump regulating and does not move it to s_min for a head in that band."
3. **The floating-section rule and over-control:** "A discharge-pressure-controlled pump that runs with a port in a part of the network that no reservoir or reference node fixes is reported as not converged, naming it: the speed that holds a pressure on that arbitrary level is undetermined. Closed with both ports in such a part, and closed at every level of it (the head across it at least its maximum-speed shutoff head plus 0.00005 m), it is reported with that part's flows and head differences only. One at a speed limit whose discharge is within 0.0001 m of its setpoint head, in series with another control with nothing fixing the pressure between them, is reported as not converged (over-controlled). A flow control in series with one is solved once more with the one at its limit held regulating; if that state also satisfies every rule, the solve is reported as not converged, naming both states." (The last sentence with Q3(b).)
4. **Rule S and the second-state tests of a lone pump** (Q1 (c), Q2 (a); revised, §14.4): "Stability of regulation: at the converged state, the speed-controlled pumps that regulate with flow (when one of them holds a discharge pressure), and each discharge-pressure-controlled pump at a speed limit that is alone in its pressure zone, are each solved twice more as fixed-speed pumps at their running speeds with ±0.0001 m added to the pump's head, to a flow tolerance of 1e-12. This gives the response G′ of the regulating pumps' controlled values (discharge static pressure, or flow) to each pump's head. A state is reported only if G′, over each group of coupled regulating pumps that includes a discharge-pressure-controlled one, is a P-matrix, every principal minor positive to within a relative resolution of 1e-06: a decentralized integral control of the drives then exists that holds it, also with any of them out of regulation (integrity; Campo and Morari 1994; Kariwala, Forbes and Meadows 2005); otherwise the solve is reported as not converged, naming the pumps. For one pump this is r > 1, where r = (dEGL_d/dQ_d)/(2 c_d Q_d), c_d Q_d² being the velocity head at the port: the static pressure at the port rises with its flow. The drives' dynamics are not modelled, and the control valves are taken as holding their setpoints. A pump alone in its pressure zone at a speed limit with r ≤ 1 is solved once more on the other side (at minimum speed with or without flow, or at maximum speed), and one held at no flow with its discharge at or above its setpoint once more at maximum speed, each network solve of these at most 30 Newton iterations; a second state that satisfies every rule, differs in flow and that the drives can hold is reported as not converged (two steady states). r is evaluated at the solved flow only, and each further solve follows one path."
5. **The zone search** (Q1 (c); replaces the zone rule of the first design), present when a project has a searched zone: "Several pumps may hold the pressure of one zone (the part of the network bounded by reservoirs, reference nodes, pumps, active or failed-closed control valves, closed isolation valves and locked-closed check valves). Where a zone holds a discharge-pressure-controlled pump and at least one other pump, PRV or PSV, the combinations of their states are solved once more each with those states held, from the state reached, the exchanges of the states reached first and then by the number of states changed, at most 63 per zone (15 per zone at each system-curve point), each network solve at most 30 Newton iterations, and all these solves together at most 4,000 Newton iterations per solve (10,000 per system curve), whatever the maximum iterations set. A combination that satisfies every rule, differs in flow and that the drives can hold is a second steady state, and the solve is reported as not converged; one whose solve does not converge gives no state, and one whose drives cannot hold it is listed but not counted. Where a limit leaves combinations unsolved, the result is flagged (STATE_SEARCH_INCOMPLETE). With every other element as solved, the states of these pumps have indices, the sign of the determinant of their response (the regulating pumps outside the zone holding their values), that sum to 1 (Simsek, Ozdaglar and Acemoglu 2007): a state whose determinant is negative has at least two other states in its frame; among two or more nondegenerate states at least one has a negative determinant." (Revised, ZR F1 and F2.)
   The "This solve" item gains "; zone search: {n} candidate states solved in {z} zones, {k} Newton iterations{, stopped by the search budget}" when a zone was searched.
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
  - **The candidates** are every combination of the options of every status element of the case: active, max_speed, min_speed and no_flow per controlled pump; running and no_flow per fixed pump; open and closed per check valve that is `active`; active, open and closed per PRV, PSV and FCV that is `active`. Each competing combination is shown to fail one of its rules by `STATE_MARGIN`. A combination that satisfies every rule but whose drives cannot hold it (G′ not a P-matrix, §5.11.4) still counts as rule-valid for this requirement (Q1 (c)): a network with such a second combination is a unit test, never a case file.
  - **One physical state, two labels.** Candidates that differ only in the labels of elements at zero flow, with the sections beyond them at rest (`state_search.same`, TSD §5.4; v1's zero-flow multiplicity, D9), are listed in the derivation. The case may pin the label the rules reach, with the path written out (the solve's start state and the rules that fire), as slice 1's dead-end case does (`derivations_pump_control.py:2169-2229`). Where that label depends on an open owner question (Q6: PCF16 B), it is a membership unit test until the answer.
  - **The one documented two-state band** (§5.6 item 6, the x_mono band): a case may pin ACTIVE there by D11's path rule (the solve starts active, and P3 tests F(s_lo(Q), Q)), as slice 1's CF21 does (`derivations_pump_control.py:770-842`), only if its derivation enumerates and checks the second state, MIN_SPEED, and states the path. This exception is written into D12 and kept out of the fuzz's critical rule (§9.5).
  - Where several states hold otherwise, the test is a unit test that asserts "not converged, or one of the enumerated valid states". It is never a pinned state. Under Q1 (c), where the enumeration (with G′ from the closed form of §5.11.4 on one ideal header node, or by finite differences of the reference laws elsewhere) shows two states the drives can hold, or a reached state they cannot, the unit test asserts "not converged", with the message naming states among the enumerated ones (§9.3, PZM cases).
  - **Unstable roots count** (ZR F7). The enumeration of a zone case must find the rule-valid states the drives cannot hold as well as the others, because they count against a case file. Pinned solves cannot show their absence: the lag repels them (§5.11.4). So each zone derivation uses a method that finds every root, unstable ones included: the header reduction's scan on ideal tees, and on Crane headers the two-dimensional scan of §9.3 step 5.

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
| PCF14 `…_parallel_fixed` | A pressure pump beside a fixed pump on a header T, with H_T unknown: the pressure pump's flow from H_set(Q_P) − H_T = h_LP(Q_P); the fixed pump's from F_f(Q_f) = H_T + h_Lf(Q_f) − EGL_s; continuity solved for H_T by brentq. The pressure pump's spool has an exit-like loss (r_spool > 1 by margin), and the guards enumerate the fixed pump's running and no_flow × the pressure pump's four states; in particular the state with the pressure pump closed and the fixed pump alone puts the header below H_set0 − margin, so C1 re-opens it: the setpoint lies outside the two-state band of the former V6's derivation (§5.10, PN2). | Coexistence; under Q1 (c) a searched zone: rule S passes and the search's 7 candidates refuse nothing |
| PCF15 `…_loop_with_reference` | R1 → L1 → PU1 → L2 → ideal tee T1 run inlet; two parallel pipes La (run outlet) and Lb (branch) of different lengths to ideal tee T2; T2 → L3 → an ideal reference node RN at a fixed gauge pressure. Q is the root of H_RN + h_L3(Q) + h_par(Q) + h_L2(Q) = H_set(Q) by `brentq`, with h_par(Q) from h_a(Q_a) = h_b(Q − Q_a), itself by `brentq` (ideal tees impose one head per tee); guards as for an active case (r > 1 at the root, φ increasing) and the four pump states enumerated (RVG-11: written out; the first draft had no derivation). | Determined loops |
| PCF16 `…_zero_flow_bound_reopen` | The pump and a discharge check valve close together; the pipe between has a free level X. H_s + S_min < H_down < H_set0 < H_s + S_max, so they re-open (S_eff = H_set0 − H_s > H_down − H_s), where a bound at S_min would keep them shut. The closed candidate needs X ≥ H_s + S_eff = H_set0 > H_down + margin with the check valve closed, which fails. Final state by brentq, as CF14b. Variant B (H_set0 < H_down < H_s + S_max with H_down − H_s > S_min: they stay closed, where a bound at S_max would re-open them) is two-state under §5.6 item 4 (closed, or active at zero flow) and depends on Q6, so it is a membership unit test (§9.7), not a case file (RVG-11). | The one-sided bound S_eff |
| PCF17 `…_suction_closed_{min,max}` | A closed isolation valve on the suction. R2 above the setpoint: min speed, dead-headed, EGL_s = EGL_d − S_min. R2 below: max, EGL_s = EGL_d − S_max. The derivation lists CLOSED with the suction section at rest as the same physical state with another label (§9.2), and writes the path: the solve starts ACTIVE, the GGA starves the link, P0 picks the target by EGL_d against H_set0 + Htol (margin), and the target keeps its state (X1 or N1 fails by margin). | P0's split |
| PCF18 `…_two_check_valves` | R1 → CV1 → PU → CV2 → R2 with S_min > H_R2 − H_R1 (C's s_min 0.8 case): min speed with flow, by brentq. The guards enumerate the pump's four states × CV1 and CV2 open and closed. | The exact union (§5.7); the "no constraint" rule fails it |

**Pressure zones** (Q1 (c), §5.11; the reference author's `tests/reference/derivations_pump_zones.py`, imports as §9.1).

*The header reduction* (ZE's oracle, made a derivation):
1. The unknown is the head H of one header node: the ideal tee for two boosters; tee T1 for three, with H_T2 = H_T1 − h_L12(Q1 + Q2).
2. Each member's flow as a function of its tee's head, per status:
   - OPEN or MIN_SPEED: the root of F(s, Q) = H + h_D(Q) + h_S(Q) − H_R1, unique and falling in H for a curve that does not rise; none if F(s, 0) ≤ H − H_R1;
   - ACTIVE: on each monotone piece of g(Q) = h_D(Q) − c_dQ², the root of H + g(Q) = V; the piece's domain ends in H are added to the scan;
   - CLOSED: 0; a fixed pump as OPEN at its speed; an active PRV by its own g on its outlet spool, open by its line law.
3. Continuity at the header, Σ member flows = Q_main(H) with h_main(Q_main) = H − H_R2: roots bracketed on a grid that includes every piece's domain ends, refined by `brentq`. (ZE's lesson: a uniform grid missed a stable state whose rising piece spans about 2 mm of header head.)
4. Every root is checked against §5.4 with `STATE_MARGIN`; G′ comes from §5.11.4's closed form (one header node) or from fixed-speed scalar solves of the line laws (two nodes), with the P-matrix test.
5. **On a Crane header (PZ8)** (revised, ZR F7: a `brentq` on the split at each header head does not prove a single root, since both leg K's depend on the split, and it cannot show that no unstable state exists). The leg losses come from `fluids`' converging Crane correlations at the split (combined flow through the run outlet). The derivation finds every state by one of two scans, both written with the reference laws only, and states which it used:
   - **(header head, split).** The unknowns are the outlet node's head H and the split φ = Q_run/(Q_run + Q_branch) ∈ [0, 1]. For each member status pattern, the residuals are the two members' flows (step 2's laws at the leg inlet heads H + Δh_leg(Q, φ)) against Q·φ and Q·(1 − φ), with Q = Q_main(H). The scan covers a grid of H that includes every piece's domain ends (step 3) and a grid of φ that includes 0 and 1; every cell where both residuals change sign is refined by Newton (`scipy.optimize.fsolve`, xtol 10⁻¹²), and every root of the split equation at a given H is bracketed, not only the first.
   - **Speed space** (ZR's method, `x4_speed_space.py`, and §9.5's `speed_space`). With every pump fixed at a speed (or closed), the network is solved by the reference laws; for each pattern of members at a limit or closed, every root of P_i(s) = H_set0,i over the regulating members' speeds is found on a grid of [s_min, s_max] per member and refined, and every 1-D root with the others at a limit.
   Either scan is run twice, the second at twice the grid density in every axis; the two must find the same roots, within D6's tolerances, or the case is not built. Every root is checked against §5.4 with `STATE_MARGIN`, and G = ∂P/∂s comes from central differences of the same laws (±10⁻⁵ in speed), whose P-matrix verdict and determinant signs are G′'s (§5.11.4, *Units*). *Measured* on PZ8's inputs (ZR `x4_speed_space.py`, 21 × 21 speeds, real outer loop with Crane K iterated; reproduced by ZF, `y6_speed_space.log`): no (A, A) root; (A, X) at s 0.794225, Q 0.014794/0.038628, with the pump at maximum speed 0.3254 m of head below its setpoint (X1 fails by more than `STATE_MARGIN`: valid); (X, A) at s 0.808317 with the pump at maximum speed 0.1176 m above (X1 fires: invalid). On PZM1's inputs the same scan finds the unstable (A, A) at s 0.892532 each, dP/ds det −165.2, beside (A, X) and (X, A).

*Cases* (exactly one rule-valid combination, by margin, §9.2):

| Case | Inputs | Expected (derivation) | Prototype values (*measured*; the derivation recomputes them) |
|---|---|---|---|
| PZ1 `pump_pressure_zone_two_k2` | ZE's family: R1 10 m; 5 m × 0.1 m suctions with a sharp entrance; curve_a, s ∈ [0.5, 1]; 0.5 m × 0.1 m spools with a K = 2 fitting; ideal tee; main 300 m with an exit; R2 20 m; 250 kPa each | (A, A), symmetric; G′ a P-matrix (every spool loses more than its velocity head, §5.11.4); the 15 other combinations fail by margin | Q 0.005311 each; G diag 27.375, det 216.8, NI 0.289 (ZE `e1_two.py`) |
| PZ2 `…_two_20m` | 20 m bare spools; main 30 m; 250 / 255 kPa | (A, A); the search runs its 15 candidates and refuses nothing | Q 0.011991/0.019699, s* 0.6195/0.6815, NI 0.606 (ZE `e3_dp.py`; ZJ `j1_v1_held.py`: det 320.71) |
| PZ3 `…_two_one_closed` | 2 m bare; main 300 m; 250 / 255 kPa | (C, A) | Q 0/0.011222, s* 0.62476 (ZE `e3_dp.py`) |
| PZ4 `…_three_k2` | 0.5 m spools with K = 2; L12 1 m; main 30 m; R2 25 m; 350 kPa each | (A, A, A); all 7 minors positive | Q 0.01380/0.01380/0.01773, NI 0.139 (ZE `e4_three.py`) |
| PZ5 `…_three_failing_candidates` | 2 m bare; main 30 m; R2 25 m; 300 / 350 / 400 kPa | (C, A, X); the test also asserts convergence to it although some candidates have no converged solve (no-state-found count ≥ 1) | Q 0/0.006921/0.039058 (ZE `e4_three.py`, `e5_undecided.py`) |
| PZ6 `…_pair_fixed` | 20 m bare; main 30 m; R2 20 m; 300 kPa; a fixed pump on a third header inlet | (fixed pump running, A, A) | Q 0.00102/0.00102/0.04367, det 628.7 (ZE `e10_mixed.py`) |
| PZ7 `…_pair_prv` | 20 m bare; a PRV from RH 60 m through 100 m, with a 1 m outlet spool; every setpoint 250 kPa; R2 24.5 m | (PRV active, PU1 closed, PU2 closed) | (ZE `e10_mixed.py`) |
| PZ8 `…_crane_header` | ZE's family with a Crane tee: PU1 on the run inlet, PU2 on the branch; 2 m bare spools; main 30 m; R2 20 m; 350 / 350 kPa (the web app's default header) | (A, OPEN), by step 5's scan (unstable roots included) | Q 0.014794/0.038628; one rule-valid state reached by the full enumeration of pinned solves (ZJ `j2_crane.py`, `j5_variants.py`), and no other root, unstable or not, in ZR's speed-space scan, (X, A) failing X1 by 0.1176 m (ZR `x4_speed_space.py`; ZF) |
| PZ-G (unit) | PZ1's and PZM1's states | G′ from §5.11.4's closed form against `regulation_response` within 10⁻⁶ relative | closed form against the solver 9.7·10⁻¹¹ and 1.4·10⁻¹⁰ (ZS `s6_closed_form.py`) |

*Several states* (unit tests, never case files, §9.2; each run from the default start and from each enumerated state):
- **PZM1:** PZ1's family with 2 m bare spools, main 30 m, 350 kPa each. The scan gives (A, A) at Q 0.028287 each, s* 0.8925, NI −0.329 (unstable), and (A, X)/(X, A) at 0.017155/0.038930, s* 0.8067 (stable) (ZE `e3_dp.py`; ZJ `j1_v1_held.py`, `j8_speeds.py`). Expected: from the default start, not converged with exit S2, the companion sentence (D_Z < 0), and (X, A) named as a state the drives can hold: candidate 2 in the order from (A, A), since the enumeration shows candidate 1, (C, A), fails its rules (ZR F9; *measured*, ZF `y1_cap.py`: from (A, A) the pinned solves reach (A, X) and (X, A) with and without the cap); from an asymmetric start, "two steady states" at candidate 1.
- **PZM2:** PZM1 with 350 / 350.1 kPa: (A, X) reached, (X, A) at 0.038920/0.017185 also valid: "two steady states" at candidate 1 (ZE `e3_dp.py`; ZJ `j3_candidates.py`).
- **PZM3:** three identical boosters, 2 m bare, main 300 m, 350 kPa each: (C, C, A), (A, C, C), (C, A, C) stable; (A, C, A), (C, A, A) unstable, det −193.1 (ZE `e4_three.py`, `e6_oracle_check.py`; ZJ `j5_variants.py`).
- **PZM4:** two boosters and a PRV, 1 m spools, 250 kPa each (PN2's class): three rule-valid states, permutations of each other (ZE `e10_mixed.py`).
- **PZM5:** ZS's two boosters with unlike spools (K = 0.5 on one, none on the other), equal setpoints: (A, A) with r 2.997 and 5.197, both > 1, and det −38.07: exit S2, which a per-pump r would not give (ZS `s5_mixed.py`).
- **PZM6** (the P-test function): ZS `s4`'s 3×3 matrix (det +164.7, three negative 2×2 minors) is refused; minors at ±RESPONSE_RTOL; the block split; the 12-pump cap.
- **PZM7** (the limit): four boosters on 20 m bare spools with setpoints 250, 255, 260 and 265 kPa, whose single rule-valid combination the derivation's scan establishes over the 256: converged with `STATE_SEARCH_INCOMPLETE`, 63 of 255 candidates solved, and the trace's counts (derived, not yet run).
- **PZM8** (the search budget; ZR F1): three disconnected copies of PZ5's inputs on Crane tees (three searched zones), `maxIterations` 1,000. Each zone's single rule-valid combination, (C, A, X), comes from step 5's scan of one copy (the copies are independent). Expected: converged at (C, A, X) in each zone; the first two zones searched completely; `STATE_SEARCH_INCOMPLETE` on the third zone's pressure members with `stoppedBy` `SEARCH_NEWTON_BUDGET`; no inner solve of a candidate over 30 Newton iterations; the search's Newton iterations exactly 4,000; and the same result at `maxIterations` 100. *Measured* (ZF `y4_budget.py`, prototype order): the budget is spent during the third zone's 27th candidate, after 5.95 s of search; without the cap and budget, 42,980 Newton iterations and 49.55 s (`y2_multizone.py`). The candidate at which the budget is spent in the design's order is derived by the unit test from the order of §5.11.6, not copied from the solver.
- **The exit texts** (ZR F2), byte for byte, on synthetic G′ injected into the message builder, one of each kind: S1 with one regulating pump (V2's message, frame clause); S1 with two, G′ = [[1, 3], [−3, −1]] (det 8: the own-frame clause only); S2 through the determinant on PZM1's G′ (companion sentence); S2 through the order-2 minors on PZM6's matrix (det +164.7: no companion sentence); S3 on [[1, 2, 0.5], [1, 1, −0.6], [−0.8, 1.2, 1]] (minors 1, 1, 1; −1.0, 1.4, 1.72; det 1.68, ZF `y7_s3_example.py`); S2 over a block spanning two zones, with one zone's D_Z negative and the other's positive (the sentence printed once, for the first); S4; S5.

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
- **Parallel groups** (Q1 (c), §5.11; replaces the first draft's "never two pressure pumps in one zone"; ZE's draws, with ZJ's tee draw). With probability 0.35 a controlled pump gets one or two parallel siblings: a suction from a new port on the same reservoir or a tee on its suction connection, and a discharge into a new tee on its discharge connection. The tee is Crane with probability 0.5 (the web app's default, `factory.ts:260`), else ideal. Siblings copy the pump's curve and data with probability 0.6. Their setpoints are equal with probability 0.4, within ±300 Pa with probability 0.2, else independent. Each discharge spool takes a K ∈ [1.2, 3] fitting with probability 0.5, else none (0.3–3 m bare). With probability 0.1 a fixed pump or an active PRV joins the group, and with probability 0.05 a group has four non-identical pressure pumps (the limit). All of it is drawn after every existing draw.
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
  - §5.9 swap test, §5.10 V3–V5 and the zone search's "two steady states": `state_search` (below) must find at least two fully determined valid solutions that differ in flowing state (`state_search.multiple`) and that pass `checks.regulation_check` (below);
  - rule S's exits S1–S3 (Q1 (c)): `checks.regulation_check` must resolve the named state's regulating set as not a P-matrix; S4 and S5 are counted by reason and listed;
  - with one regulating pressure pump, also: an independent r from EPANET, r_EP = (ΔH_d/ΔQ_d)/(2c_dQ_d) from two runs of the substitute with its setting at ±δ_EP, EPANET's heads being our EGLs (D7), must be ≤ 1 + β;
  - `STATE_SEARCH_INCOMPLETE` is not an exit: those seeds are counted and searched by `state_search` like any converged result;
  - an exit that its check does not confirm is a new critical class, `a_guard_unjustified`, added to `classes.CRITICAL`;
  - and a converged result with an ACTIVE pressure pump whose r_EP < 1 − β is critical too (`a_unstable_active`), since V2 should have refused it; so is a converged result whose regulating set `checks.regulation_check` resolves as not a P-matrix outside its band (`a_unstable_regulation`, new), since rule S should have refused it.
  - δ_EP and β (derived, not tuned): EPANET returns float32 results (continuation prompt §4), so δ_EP = 0.01 m (100 × Htol) keeps a head difference resolved to about 2·10⁻⁴ of itself at heads near 30 m; β = 0.05 covers EPANET's constants (friction and minor losses up to 9.2·10⁻⁴ below ours, TSD §10.4) and the secant over ±δ_EP (a change of r of order ΔQ_d/Q_d ≈ 1 % for the generator's spools). A pump with |r_EP − 1| ≤ β is recorded as borderline, not critical.

**Speed comparison** (`speed_comparison`, `checks.py:259-306`):
- s_ref = `implied_speed` at EPANET's (Q_e, H_e), within 0.5 %;
- our implied head at (s_o, Q_e) against H_e by D6's head criterion;
- p_d from EPANET's head at the discharge junction, against p_set by D6's pressure criterion.

**`checks.regulation_check`** (Q1 (c); the reference author's, independent of `services/`). From a converged result's speeds, or from rule S's `NOT_CONVERGED` details (`{id}.state`, `.flow`, `.speed`, §5.11.4), it builds a copy of the project with every regulating speed-controlled pump fixed at its speed (control removed), solves it with `solve_project` (v1's fixed-pump path) at tolerance 10⁻¹² and 1,000 iterations, and checks that the port pressures (and flows) equal the setpoints within D6, so that it reproduced the state. It then forms G = Δy/Δs from copies at s·(1 ± 10⁻⁶) (one-sided where s(1 + 10⁻⁶) would exceed `speed`) and applies the P-matrix test, with a borderline band |NI| ≤ 10⁻³ recorded, not critical (derived: the solves to 10⁻¹² resolve G to about 10⁻⁶ relative, so the band is 100× that).

**`state_search`** (`state_search.py:38-80`):
- pins every member of every searched zone (§5.11.2) over its options, jointly across zones (so a pair that needs two zones to change together is found, and classed 5 below), and the pressure pumps of lone zones as before; `options` gains the PRV and PSV options for members, and LIMIT 729 stays (four pressure pumps, a fixed pump and a PRV: 4⁴·2·3 = 1,536, the first 729 searched and the truncation counted);
- **a pressure pump pinned active is the EPANET substitute of §9.4** in our own solver (the pump at s_max, a new node at z_d, and an ideal PRV holding p_set; equal to the active pump within 2.4·10⁻¹² in flow, PM5), so a pinned project has no discharge-pressure pump: neither rule S nor the zone search runs inside the checker's solves, which stay independent of the slice-2 code; the original speed range is enforced afterwards by the original rules (P2, P3), as flow pumps' widened range is today;
- new `stable_solutions`: the valid solutions whose regulating set passes `checks.regulation_check`;
- new `speed_space` (ZS's `s2`/`s4` method, for the critical-class review only): Newton over fixed-speed copies from a 5^m grid of speeds for every subset of m regulating pressure pumps, the others at OPEN, MIN or CLOSED, capped at 20,000 solves per seed; it finds the unstable states that pinned solves cannot reach (*measured*, ZS: 1,711–1,841 solves for two boosters from a 9² grid, 11,963 for three with closures), so the frame's index sum can be checked (`findings/index_incomplete`, counted, not critical).

**Criticality of a second state** (revised, RVG-6, and again after ZR F3; defined here, before the run). The first draft made every second valid state with a pressure pump in another running state critical, which the design's own accepted multiplicities would have made unattainable. The owner-answer revision then let `control_search` pin every member of every searched zone jointly, across zones, with independent solves, while §5.11.13 accepts three kinds of miss (one attempt per candidate, zones searched one at a time, the limits): a fuzz-found instance of any of them would have been critical with no class and no remedy (ZR F3). Now, in this profile, a converged result is **critical** (`a_pressure_multiple`, added to `classes.CRITICAL`) when `control_search` finds a valid solution c that differs in flowing state from the solution r equal to the result (`state_search.same`; both fully determined, `state_search.multiple`), both passing `checks.regulation_check` (`stable_solutions`; Q1 (c): a rule-valid solution the drives cannot hold goes to `findings/unstable_valid`, counted, not critical), unless the pair (r, c) falls in one of these documented classes, each with a mechanical test:
1. **zero-flow labels** (§5.6 item 4, Q6): the two differ only in a pressure pump's status, its flow at most Qtol in both, with the section beyond it at rest;
2. **drooping curve** (§5.6 item 5): a pressure pump whose curve's H₀ rises somewhere on [0, x_last] differs between the two;
3. **the x_mono band** (§5.6 item 6): one solution has a pressure pump ACTIVE and the other MIN_SPEED, with Q_active/s_min > x_mono;
4. **v1's status-rule multiplicity** (TSD §10.4, slice 1's test): with every pressure pump fixed at its speed in each solution and searched over running and closed, the same solutions are found;
5. **two zones** (`cross_zone`; §5.11.13 limitation 2, risk 8): the members whose statuses differ between r and c lie in two or more searched zones of the checker's own partition (§5.11.2, built by the reference author from the port graph and the user statuses), as across two zones joined by a PRV or PSV that ends open;
6. **one attempt** (`pinned_unconverged`; §5.11.13 limitation 1 and the cap): the members whose statuses differ lie in one searched zone, and the result's trace lists c's assignment of that zone's members among its candidates with no converged solution (§5.11.10); or they are one lone pressure pump, and its trace's V3–V5 line reports that pinned set's solve as not converged;
7. **search incomplete** (`search_incomplete_multiple`; §5.11.13 limitation 4): the result is flagged `STATE_SEARCH_INCOMPLETE` for that zone or pump, and c's assignment is not among the candidates it solved (the first n of the order of §5.11.6, n from the flag's details, the order rebuilt by the checker from §5.11.6's rules), or the test that would have pinned it was not run.

Every other pair is critical. In particular a pressure pump at max_speed with flow in one solution and held at no flow in the other (PN1), closed in one and regulating in the other beside another pressure source (PN2), or two pressure pumps of one zone exchanging their statuses (§5.11), whose test or candidate ran and converged, is critical: §5.10's V3 or V5, or the zone search, should have refused it. So is a pair whose candidate's single attempt converged, but to another state: limitation 1 does not cover it (it was not observed, §5.11.13), and its remedy is stated there. Excluded pairs are written to `findings/control_multiple_states` with their class, and the counts per class are pinned in TSD §10.4, as slice 1's seven are. The gate is 0 critical, not 0 in classes 5–7: a nonzero count in class 5 or 6 is reported to the owner with the remedy that §5.11.13 states for it (a joint search of the zones involved; a cold second attempt), measured on the fuzz before it is applied. A pair in no class is critical: either a guard missed it, or it is a new class, which is a design change reviewed by the owner, not an exclusion added after the results are seen.

**Stats** (`stats.py`) gain the kind `pressure_pump`, with metrics `speed`, `speed_head` and `setpoint_pressure`, final-state counts, each guard exit counted by reason (§5.8, §5.9 over-control and swap, S1–S5, V3–V5, the zone search) with whether its check confirmed it, and control-search counts per documented class. Per searched zone (Q1 (c)): members, candidates, the outcome (unique, refused by S, refused by the search, incomplete by count, incomplete by budget), candidates solved, no-state-found counts (and how many stopped at the cap), Newton iterations and wall time; the same summed per system curve; the counts of classes 5–7; and the index-sum findings. **Independence of `maxIterations`** (ZR F1): every seed is solved again with `maxIterations` 1,000; where the main solve's result is identical, the search's outcome (candidates solved, no-state-found assignments, flags, refusals) must be identical too, and a difference is critical (`a_search_iterations`, new): the cap and the budget make the search independent of that setting.

**Count gates** (RVG-17; chosen, about twice slice 1's 163 EPANET-compared active pumps, and stated before the full run):
- at least 300 ACTIVE pressure pumps with Q_d > Qtol compared with EPANET through the substitute;
- at least 50 of them on discharge connections with r_ref < 1.5 (the C1 stress);
- at least 30 final states each of max_speed, min_speed, no_flow at s_min and no_flow at s_max;
- the active pumps at zero flow (dead-ended) counted separately, outside the first gate;
- Q1 (c), chosen and stated before the run: at least 150 searched zones, 50 of them on Crane tees; at least 40 converged results with two or more regulating pumps that `checks.regulation_check` resolves as a P-matrix; at least 30 rule-S exits and 20 zone-search exits, each confirmed; at least 5 results reaching `ZONE_SEARCH_LIMIT` and 5 stopped by `SEARCH_NEWTON_BUDGET` (the generator's groups with a fixed pump or PRV and its four-pump groups, and its seeds with two or more groups, ZR F1).
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
  - rule V on the J `j5` header network (R2 20.8–21.3 m not converged, 19 m accepted), with r asserted against r = (h_spool′ + h_rest′)/(2c_dQ) on a line;
  - **V3 and V5 on PN1's network** (§5.6 item 1; R1 5 m, PU H₀ = 40 − 500x, s ∈ [0.8, 1], 1 m spool, ideal tee, 50 m of 0.3 m header with an exit, the branch to a plug): at R2 = 31 m (p_set 301,395.9 Pa) and 33 m (321,471.2 Pa), not converged with the "two steady states" message naming the pump at maximum speed and held at no flow at s_min; each started both from the default state and from OPEN (forcing V3's path) (PN1);
  - **the zone search on PN2's network** (§5.10, §5.11.8; formerly V6): the booster and the PRV at equal setpoints of 25 m of head, not converged ("two steady states") from either start; with a K = 2 fitting on the booster's spool (r_spool > 1), converged, unique (PN2);
  - **V5 refuses nothing** where the state is unique: PCF7's and EP4's networks converge at no_flow with the V5 note in the trace;
  - V2's message text byte for byte (PN6);
  - the pinned-set semantics: a rule leaving the set keeps the status, and the unrestricted rules decide a second state; `guards=False` keeps §5.8 and §5.9's over-control test and skips the rest; `branch_restarts=False` skips the restart;
  - **rule S** (Q1 (c), §5.11.4): `regulation_response` against the closed form (PZ-G); the P-test (PZM6); the k = 1 equivalence g′ > 0 ⟺ r > 1 on PCF1's line (r 23.5) and on the 1 m spool with an exit (r 1.17); **V1 with A empty** (ZR F5): on the J `j5` header network nothing regulates anywhere, and the test asserts that the perturbed solves ran for the lone pump at its limit alone (two inner solves, r in the trace) and that r ≤ 1 triggered V3 or V4 (R2 19 m: accepted at maximum speed, V3's pinned branch failing N1; 20.8–21.3 m refused, both limits valid); a block of flow pumps alone is not tested (a project with a regulating pressure pump and, elsewhere, two regulating flow pumps whose G′ block, injected, is not a P-matrix converges, its flow pumps' results equal to slice 1's); V1's r of a lone pump at a limit by the Schur complement against a held solve where that converges (ZS `s8`'s network: 0.2261); the default start of identical boosters on bare spools ending in exit S2 (PZM1); exits S1–S5 and the `NOT_CONVERGED` details keys; flow-controlled pumps in A only when a pressure pump regulates (a flow-only project runs no S, byte-identical);
  - **the zone search** (§5.11.6): the zone partition and members (a fixed pump, a PRV outlet, a PSV inlet, a forced pump excluded, an FCV excluded); the candidate order (golden lists for a two- and a three-member zone, permutations first); the single warm attempt; the cap (a candidate whose inner solve would need more than 30 iterations is "no state found", with its assignment listed in the trace); the limits and `STATE_SEARCH_INCOMPLETE` (PZM7); the budget (PZM8: the search's Newton iterations exactly 4,000, the stop inside a candidate, the flag's details and texts, and the same search at `maxIterations` 100 and 1,000; a V3 test left unrun by a spent budget, flagged with its text; a curve whose budget is spent, its later points' notes); the no-state-found count; the criterion's five parts, each failing alone (a candidate differing only at rest, a control-unstable one listed, the x_mono pair); the early stop; the search after an S refusal naming a holdable state; the index sum in the trace;
  - the not-converged texts of §5.11.10 byte for byte, each exit on a G′ of its kind (§9.3, "The exit texts"; ZR F2), and the `STATE_SEARCH_INCOMPLETE` texts of each kind.
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
- the header bistability (J `j5`);
- the pressure zones (Q1 (c)): PZM1–PZM8, the Crane header PZ8, the near-zero-loss pair (ZE `e12`, ZS `s10`), a curve point of a three-booster zone (ZJ `j6`), and the projects of PZM8 and of PZ5 on Crane tees at `maxIterations` 1,000 (ZR F1).

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
  - **performance:** the gate of §5.11.12, stated before the run (Q1 (c); it replaces the first draft's PRD §4.2 gate, which a searched zone of three members can fail: *measured*, ZF `y1_cap.py`, 1.3–2.7 s of search with the cap): every corpus project, the Crane-tee ladders and every `pressure_control` seed within the 45 s budget, at their own settings and at `maxIterations` 1,000; projects without a searched zone, and those whose zones have two members, within PRD §4.2; three-member zones under 5 s; several searched zones at `maxIterations` 1,000 (PZM8) under 10 s, stopped by the budget and flagged; a 41-point curve in such a zone under 30 s; the search budget under 20 s on the largest network with a searched zone; wall times as measured, with the load, and the counts recorded in TSD §5.2 (ZR F1).

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
6. **`utils/flag-text.ts`** (171): a pressure branch of the `PUMP_SETPOINT_NOT_MET` formatter, in display units, gauge; and the new warning `STATE_SEARCH_INCOMPLETE` (Q1 (c), §5.11.6), whose server text is shown as given.
7. **No `issue-text.ts` change** (Q1 (c)): there is no `PRESSURE_CONTROL_ZONE`. The not-converged texts of rule S and the zone search are server text, shown as today. The pump chart shows a system-curve point's `message` when the point has a head and a note (the search's limit at that flow, §5.11.9), beside the point (a marker with the note as its text, as the chart shows points without a head).
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
  - the zone partition and each zone's members, built once (Q1 (c), §5.11.2); no topology issue.
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
  - at the converged exit (1740): the floating rule, the series swap test, rule S, V1 and V3–V5 for a pressure pump alone in its zone, and the zone search (revised, ZR F9: V2 and V7 are S's exits and V6 is removed);
  - `run_outer_loop(pinned=…, guards=…, branch_restarts=…, search=…)` (1586), pinned to sets of statuses (§5.10), each inner solve of a pinned solve at most `CANDIDATE_MAX_ITERATIONS` and charged to the `SearchBudget` (§5.11.6, ZR F1);
  - the exit order of §5.11.3: rule S (`regulation_response`, the P-test, exits S1–S5), §5.10's tests for lone pressure pumps, then the zone search;
  - **new module `services/solver/zones.py`** (Q1 (c)): the members and searched zones of `builder.py`'s partition, the candidate order, `zone_search` (the single warm attempt, the limits, `CANDIDATE_MAX_ITERATIONS` 30 and the `SearchBudget` with `SEARCH_NEWTON_BUDGET` 4,000 and `CURVE_SEARCH_NEWTON_BUDGET` 10,000, the early stop, the criterion of §5.11.7 with `state_search.multiple`'s semantics re-implemented in the solver, the previous-point warm starts at curve points) and the index sum;
  - `initial_controls` (310-344) unchanged (§1.4 item 2, §5.5).
- **`services/solver/gga.py`:** the loose message (543-554).
- **`services/solver/elements.py`:** `OffsetLaw` (Q2(a)).
- **`services/solver/results.py`:** `pump_speed` (566-584), `pump_control_result` (586-663), and dead-headed EGLs (699-708).
- **`services/solver/trace.py`** (924-1288) and **`methods.py`** (121-170).
- **`services/solver/version.py`.**
- **`services/solver/flags.py`:** the warning `STATE_SEARCH_INCOMPLETE` (Q1 (c)) with its four texts and details (`stoppedBy`, ZR F1), in the flags audit; `NOT_CONVERGED` details keys for rule S's exits.
- **`services/solver/system_curve.py`:** the per-point search limit, the curve's search budget (one `SearchBudget` per curve, spent in increasing flow) and the notes on a point with a head (§5.11.9); `models/api.py`: the description of `SystemCurvePoint.message`.
- **Docstrings only:** `pumps.py`, `network.py` (42-47).
- **Tests:**
  - by the **reference author** (§9.1; the implementer does not edit these): `tests/reference/` `derivations_pump_pressure.py`, `element_laws.py` (`pressure_pump_state_problem`), `network_check.py` (the active law), `free_levels.py` (the union), `generate_epanet_cases.py`, `closed_form.py` and the generated JSONs; `derivations_pump_zones.py` (the header reduction and PZ1–PZ8, Q1 (c)); `tests/differential/` `checks.py` (the rules, the guard-exit checks, `regulation_check`), `state_search.py` (the pins, the zone members' pins with the substitute for an active pressure pump, `stable_solutions`, `speed_space`), `epanet_model.py` (the substitute, the r runs) and `classes.py` (the critical classes `a_pressure_multiple`, `a_guard_unjustified`, `a_unstable_active`, `a_unstable_regulation`, `a_search_iterations`; the documented classes 5–7 of §9.5, ZR F3);
  - by the implementer: `tests/reference/` `test_pump_pressure.py`, `test_floating_sections.py`, `test_system_curves.py` (the test drivers over the reference author's cases); `tests/unit/` `test_pressure_control.py`, `test_pressure_zones.py` (rule S, the zone search, PZM1–PZM8 and the exit texts, Q1 (c)), `test_status_rules.py`, `test_schema_rules.py`, `test_flags_audit.py`, `test_trace.py`, `test_methods.py`, and `test_released_links.py` if bumped; `tests/differential/` `generator.py`, `stats.py`, `corpus.py`, `test_fuzz_smoke.py`.
- **Web:** §10, plus `tests/pump-control.e2e.ts`.
- **Docs:**
  - CLAUDE.md: a new D12 (slice 2: mode, setpoint, rules, the guards and second-state tests, rule S with its citation and constants (`RESPONSE_TOL`, `RESPONSE_RTOL`, the 12-pump block cap), the zone search (no zone issue; members; order; the single warm attempt; `ZONE_SEARCH_LIMIT` 63, `ZONE_SEARCH_POINT_LIMIT` 15, `CANDIDATE_MAX_ITERATIONS` 30, `SEARCH_NEWTON_BUDGET` 4,000 and `CURVE_SEARCH_NEWTON_BUDGET` 10,000 with `STATE_SEARCH_INCOMPLETE`; the second-state criterion with its exceptions: labels at rest, the x_mono pair, states the drives cannot hold), the x_mono band's path rule that PCF10 relies on, as D11 states it for flow mode, versions); D5's deferred list loses "a discharge pressure (slice 2)";
  - PRD §3.1.2.1, and §4.2's note on searched zones of three or more members (§5.11.12);
  - SDD §4.8;
  - TSD §5.3–§5.6, §10.1, §10.4 (the count gates, the guard exits by reason, the documented multiplicity classes with their counts), §12 (a decided item; open items for r ≤ 1 at PRVs, the zone search's limitations (§5.11.13: one attempt per candidate, zones one at a time, the limits and the budget, S on steady-state gains, the index sum as a diagnostic, with the fuzz classes and the remedies stated for them), the zero-flow multiplicity, ENERGY_TOL against heads near 10⁹ m, and the slow lag where r_ref ≤ 1 < r_tot ≲ 1.2).

---

## 12. Risks

1. **C1 changes PRV iteration paths** in 924 of 4,120 corpus projects, all with a PRV whose status is `active`. All agree within 7.7·10⁻¹⁰ in flow and 2.9·10⁻⁸ m in head at default settings, and within 8.4·10⁻¹³ in flow at a tolerance of 10⁻¹³ (the same fixed point), but one multiplicity seed changes state (fuzz_1656). A project run with more iterations or a looser tolerance may differ more (measured up to 6·10⁻⁸ in flow at 1,000 iterations, RVG). The full fuzz class tables are re-run (§2.5).
2. **The round-off floor.** `ENERGY_TOL` = 10⁻⁷ m is below one ulp of heads above about 6·10⁸ m. Measured: fuzzfc_10269 took 54 → 111 inner iterations, with the same result. This is pre-existing; a relative energy tolerance would be its own method change.
3. **The free-level logic is the most fuzz-sensitive code in `status.py`.** The pressure pump joins it with union regions. Mitigations: the independent checker with the exact union, `state_search` pins, and the `pressure_control` profile.
4. **Several states can satisfy every rule** (§5.6). Reference cases exist only where enumeration over every status element proves one valid state; elsewhere they are membership tests. Two documented exceptions pin a state by its written path: labels of one physical state at zero flow, and the x_mono band (PCF10), both as in slice 1 (§9.2).
5. **The guards' cost** (revised under Q1 (c), measured). Rule S costs two inner solves per regulating pump, about 3 Newton iterations each (ZJ, ZS). §5.10's tests cost a pinned outer solve per lone pump where r ≤ 1 (V3, V4) and per lone satisfied booster (V5). The zone search dominates: at `maxIterations` 100 without the cap a median of 295 Newton iterations per solve for a two-member zone and 2,149 for a three-member zone (max 3,561; ZJ `j5`); with the cap of 30, which makes the cost independent of `maxIterations`, at most 293 and 1,734 in ZJ's `j7` networks, and 0.30 s and 1.3–2.7 s of wall time measured (ZF `y1`), so a project with a three-member zone can miss PRD §4.2's 1 s for simple systems (§5.11.12); a 41-point curve's search costs up to 7,956 Newton iterations, 10.8 s (ZF `y3`). Without the cap and the budget a project's `maxIterations` multiplied the cost of every failing candidate: three three-member zones at 1,000 took 49.6 s, past the 45 s budget (ZR F1, measured by ZF); the budgets of 4,000 Newton iterations per solve and 10,000 per curve now bound it, and gate item 7 checks that 4,000 of them fit the request budget on the largest network with a searched zone. Correctness is kept over that target (GOALS §3); the gate and the measured remedies are in §5.11.12. r is local, and each pinned solve follows one path. Two numerical choices, `RESPONSE_TOL` and `RESPONSE_RTOL`, are disclosed in the methods summary. A perturbed solve that fails gives "not converged" (S5); ZJ and ZS saw none fail in the open-loop frame, but numerical fragility in large networks could produce false not-converged results. The fuzz counts every exit by reason and requires an independent check to confirm it (§9.5); an unconfirmed exit is critical.
6. **`LEVEL_SEARCH_LIMIT`** (4,096) may be reached sooner with union rows. Statuses are then kept for that pass.
7. **PRVs already have the falling-static-pressure multiplicity.** With r < 1, closed, open and active at an unstable forward root can all satisfy the rules (E, V, PN `r3`, RVG `rv6`; §2.3), and v1 reports the state its iteration reaches. Applying the second-state tests to PRVs would change v1 results; it is Later, with its own method version. The C1 reference cases avoid it: VH5 and VH6 are chosen with one valid state (§2.9).
8. **The zone search is bounded and makes one attempt per candidate** (Q1 (c), §5.11.13). It searches zones one at a time, with one warm attempt per candidate, each inner solve capped at 30 Newton iterations, at most 63 candidates per zone per solve and 15 per curve point, and at most 4,000 Newton iterations per solve (10,000 per curve); a zone the limits cut short is flagged `STATE_SEARCH_INCOMPLETE`, not refused. A stable state whose candidate's attempt does not converge is missed; ZE's oracle (124 networks) and ZJ's enumeration (49) found none, and the fuzz counts any as its class 6 (§9.5). The zone partition is still topological: two zones joined by an active PRV that ends open interact, and their combinations are not searched together (the fuzz's class 5). Both classes are counted, not critical, and a nonzero count goes to the owner with the remedy §5.11.13 states for it (ZR F3).
9. **The EPANET substitute** stands only for active and max_speed. Min speed and no flow rely on SPEED runs and our rules, so those state decisions are proven by the closed-form cases.
10. **Fuzz power.** Slice 1's placement left most controlled pumps dead-ended (TSD §10.4), which in pressure mode is the trivial zero-flow active path. The count gates of §9.5 and the 200-seed sample guard against a profile that rarely exercises the held port with flow. A generator-only proxy (RVG, `rv9_discharge_r.py`) finds 85.7 % of on controlled pumps with a discharge connection that alone loses more than one velocity head; where r ≤ 1, EPANET, which has no velocity heads, still converges, so those seeds are checked by the guard-exit checks rather than by comparison.
11. **The union rename** changes OpenAPI component names and the web's `schemaBounds` call sites. A deployment before C2 makes the schemaVersion bump mandatory, and old links then show the method-version notice twice (1.2.0, then 1.3.0).
12. **User expectations:**
    - the setpoint is at the pump's own port, not at a header transmitter (remote nodes are Later);
    - "no flow at minimum speed" is dead-heading (no sleep, Q4).
13. **Slice-1 limitations carry over:** drooping curves (TSD §12 item 3) and the x_mono band at solve time (§5.6 item 6). Items 4 and 5 are being resolved by the work in progress of §1.4, and the build rebases onto it.
14. **Patent US 8,265,911** (listed active to 2030-11-27) recites tank control nodes, extended periods, fixed-flow updates and batteries. Slice 2 holds the pump's own port in a steady state, with no tank and no battery; under Q1 (c) parallel pumps are independent controllers, each holding its own port, with no common speed, battery or lead/lag staging. US 7,013,248 (a fixed control-node head in the GGA) is listed as expired. This is not a legal reading.
15. **The slow lag where the outlet pipe alone loses at most one velocity head** (r_ref ≤ 1 < r_tot ≲ 1.2; §2.3, PN3). An active PRV, and an active pressure pump, there can end not converged at the default 100 iterations although a valid state exists (measured for a PRV: r_tot ≈ 1.11 not converged, 1.23 converged in 82–90). C1 does not change it. An exact step on the whole response by Sherman–Morrison is a possible later method change, with its own measurement and corpus run. *(Superseded: the redesigned C1, §2.11, takes the exact step. VH7 and the review's networks now converge. What remains is listed in §2.11.14 item 3.)*
16. **A path-pinned case.** PCF10 pins ACTIVE in the x_mono band by D11's path rule. A future rule change that alters the path could move it to the other valid state; the case's derivation names both, so that change would show as a deliberate case update, not a silent one.
17. **Rule S rests on steady-state gains and ideal valves** (Q1 (c), §5.11.4). A state that passes S is one that some decentralized integral tuning holds with integrity, not one every tuning holds; the drives' dynamics and the PRV, PSV and FCV loops are not modelled. A state that fails S is refused even where a particular tuning without integrity might hold it (exit S3); the message says which.
18. **The natural input of identical boosters on fitting-less spools ends not converged** (Q1 (c)): the default start reaches the symmetric state, which rule S refuses (§5.11.5). The message names a state the drives can hold where the search finds one, and the fix (a fitting or check valve that loses more than one velocity head on each discharge). On the web app's default Crane headers no such case was measured: pinned solves reached no second state in 28 networks (ZJ), and PZ8's speed-space scan found no unstable state (ZR).
19. **The search's cost is spent where it has found nothing** (Q1 (c)). Every measured multiplicity was on ideal tees; on the Crane headers the web app draws, pinned solves reached one state each (ZJ, 28 networks), which does not show that no control-unstable state exists there (ZR F7; PZ8's speed-space scan found none), and no proof covers them (ZE's certificate needs ideal tees), so they are searched in full, within the limits and the budget.

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
   - **Answered (c)** by the owner on 2026-10-23, not the recommendation: several pressure pumps may share a zone, and the solve searches for second steady states at solve time and refuses an unstable regulating state. §5.11 is redesigned for it (§14.4): no `PRESSURE_CONTROL_ZONE`; rule S (§5.11.4) and the zone search (§5.11.6), which replaces V6. The text above is kept as the record of the question.
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
   - **Answered (b)** by the owner on 2026-10-24, after C1's first build (answers below). This replaces the answer (a) of 2026-10-23. The step is designed and measured in §2.11. The rank-one update with the existing factor alone was measured to make N1 worse (§2.11.2), so the exact step includes the branch offsets' flow dependences, behind four gates (three at the merge; gate L added after its review, §2.11.15).
8. **State changes in the adversarial families** (§2.11.9; criterion 9 of §2.11.11; added by the redesign of C1, revised after its review, RN-1, RN-2, RV1, RV9).
   - **What was measured** at default settings, against 1.1.0:
     - The 9,002 networks of the first review: no state change. The corpus and the fuzz: no state change at nonzero flow (one fuzz record, `flow_control` seed 11,075, changes labels at exactly 0 m³/s).
     - VA's 2,232: 8 changes, in 4 networks of 2 families, each with both friction models. NA's 2 are of **class D1**: 1.1.0 run with 1,000 iterations reaches the new rule's state. NC's 6 are of **class D2**: 1.1.0 with 1,000 iterations still ends with the PRV closed and its tee leg held, while the new rule ends with it active (r_tot 24.5–55.7, a static pressure that rises with the flow).
     - The review's 5,244: 66 changes, in 4 more families (two PRVs in parallel into a Crane tee that feeds only an assigned demand, 46; two PRVs into one Crane tee, 6; a PRV set 10⁻⁶ to 10⁻⁴ m above a tank head, 12; a PRV and a PSV at nearly zero flow, 2). 12 are zero-flow label changes; the 54 at nonzero flow are all D1 (flows within 5.95·10⁻⁹ of 1.1.0's at 1,000 iterations).
     - In every case both states pass the independent checks, so neither is shown wrong, and the inputs admit several valid states (PRV multiplicity, risk 7). The checks skip a PRV without a result (closed beside a section v1 isolates, valid by v1's own free-level rules): one side has one in 48 of the 62 changes at nonzero flow, among them 1.1.0's side of every D2 change (§2.11.9).
     - D2 exists because gate C tests the stability of the held state, not that 1.1.0's iteration would reach the same root. In NC's networks Newton converges an intermediate inner solve to a root that repels 1.1.0's lag (growth 1.93 per iteration), and the outer loop then takes another path (§2.11.4). An earlier text said gate C kept Newton to roots 1.1.0 reaches; that was wrong and is withdrawn.
   - **The trade against A1** (evidence only: you rejected A1 on 2026-10-24, and it is not offered again). On the two sets both were measured on (the 9,002 and the 2,232), A1 changes no state, leaves no converged solve not converged, and converges 60 + 0 networks that 1.1.0 does not. The chosen rule also leaves no converged solve not converged; it converges 96 + 57 (and 120 of the review's 5,244, where A1 was not run), changes the 8 states above on the 2,232, and leaves 16 networks not converged that A1 converges (E-family lines, held back by gate R; risk 3 of §2.11.14).
   - Options:
     - (a) Accept D1 and D2 in the families: criterion 9 as stated in §2.11.11 (each change named with its class, both states checked; zero-flow label changes listed under criterion 4), with criterion 4 strict for the corpus and the fuzz.
     - (a′) Accept D1 only. A D2 change blocks, and C1 waits for more design that removes NC's 6 (none is designed or measured).
     - (b) Require no state change in the families. This needs more design (for example a second-state test for PRVs, risk 7), and C1 waits for it.
     - (c) Report not converged where two valid states are found (the PRVs' second-state tests, Later).
   - **Recommend (a).**
   - Why:
     - Neither state is shown wrong in either class: both satisfy every rule the independent checks test, and the PRVs they skip are valid by v1's own free-level rules, so correctness is not at stake (GOALS §3); criterion 9 now also requires an independent check of those PRVs.
     - D1: 1.1.0's state at its default 100 iterations is an artefact of its slow lag and its fallback; given more iterations, 1.1.0 itself reaches the new rule's state.
     - D2: where several valid states exist, two iterations may reach different ones. That is the precedent you accepted in D11 (a controlled pump re-solved as the fixed pump "may reach different ones, since their iterations differ") and v1's semantics for PRV multiplicity (risk 7; Q6 (a)). The new state is the stable active one, reached by an inner solve that converged; 1.1.0's comes from its fallback after its lag diverged.
     - These families are path-dependent in 1.1.0 itself: on TD, NZ2 and TT, 1.1.0 changes 84 states between 100 and 1,000 iterations, and with 1,000 iterations the two methods agree on every state there (§2.11.14 risk 2).
     - No link has been deployed, and the corpus and the fuzz show no state change at nonzero flow (GOALS §3, longevity).
     - (a′), (b) and (c) need design that is not done; (b) and (c) change what a PRV result means, which belongs with PRV multiplicity (risk 7, Later).
9. **C0b, the two defect fixes found by the investigation of criterion 3, and its METHOD_VERSION** (§2.11.10). This question was split from the criterion-3 question (now Q10) after the review (RV3, RV4), so that C0b, which holds a method change, is approved on its own.
   - **What C0b is.** Fix (a), traceability: the `NOT_CONVERGED` flag names a residual's location only where the residual exceeds its stop tolerance, and the failed-state exit reports the residuals of the solve its message describes. Fix (b), a method change: the energy stop test allows the round-off floor of the heads it subtracts, |residual| ≤ `ENERGY_TOL` + 4ε × the largest of the link's end heads and its loss.
   - **What was measured, and what was not.** On the 58 projects that stall at the floor (main solves), fix (b) changes 9 final states; every changed element carries exactly 0 m³/s on both sides, and all 9 converge in both trees, in fewer inner iterations. Fix (a) was re-dumped on 9 named projects only; since all 384 not-converged corpus projects end with their residuals inside the stop tolerances, it removes the location from every one of their flags. Neither fix has run on the full corpus, the fuzz or the system-curve stall scan; criteria B1–B8 (§2.11.10) state what the build must show, before it runs.
   - Options:
     - (a) Build C0b before C1, under B1–B8, as **METHOD_VERSION 1.2.0**; C1 becomes 1.3.0 and C2 1.4.0.
     - (b) Build C0b under B1–B8, sharing the unreleased 1.2.0 with C1, each with its own changelog lines. **This departs from your answer that C1 has its own METHOD_VERSION**: between the two commits 1.2.0 would label two methods, and C1's "unchanged" line holds only relative to C0b, so 1.2.0's entry states its net effect against 1.1.0 (§2.11.13).
     - (c) Build fix (a) only, in C0b as 1.2.0, and leave fix (b) as a later method change (proposal §12 risk 2 stays open).
     - (d) No C0b: amend the comparator instead (Q10 (b)).
   - **Recommend (a).**
   - Why:
     - It follows your instruction: each change set has its own method version (GOALS §4.3).
     - Both defects are real and pre-existing: the flag names locations for round-off (GOALS §4.2), and the energy floor treats converged solves as failed and lets round-off choose among valid states (GOALS §3).
     - The state changes measured so far are all at zero flow, criterion 4's class, and B1–B8 turn the rest into a measurement.
     - (c) leaves the correctness defect in v1, and (d) leaves both.
10. **Criterion 3's handling after C0b** (§2.11.10 item 3; the second half of the former Q9). The owner's answer of 2026-10-24 reserved this until the three exceptions of A1 were investigated.
    - **What was found.** Under the redesigned rule, criterion 3 fails as written in 7 corpus projects: six by their `NOT_CONVERGED` flag's residual locations (defect 1, which C0b's fix (a) removes at the source), and `fuzzfc_10246`'s system-curve point, 1.36× its tolerance at default settings, where both trees give the same value at a tolerance of 10⁻¹³ (a mismatch between criterion 3's head tolerance and the solver's resolution on that path). With C0b in both trees, the outcome is **expected, not measured** (RV2): the set of flag projects depends on the solve path, and fix (b) changes paths.
    - Options:
      - (a) Criterion 3 as written, with one addition: a number outside its default-settings tolerance passes only if both trees agree within criterion 7's tolerance at criterion 7's settings, and it is listed by name with its values (today, `fuzzfc_10246`'s point).
      - (b) Amend the comparator instead, with no code fix before C1: ignore the flag's residual locations where neither side converged, exclude the labels of elements at round-off flow, and derive head tolerances from the path's head loss (C3's max(10⁻⁶ m, 2·10⁻⁸ × the largest link head loss)).
      - (c) Keep criterion 3 strict and list each exception by name at every run.
    - **Recommend (a)**, measured on top of C0b (both trees, full corpus, default and criterion 7's settings) before it is claimed met.
    - Why:
      - The addition covers only numbers shown to agree at the fixed point, and adds no ignore path to the comparator.
      - (b) widens the comparator for every project and, without C0b, leaves both defects in v1.
      - (c) makes every future run depend on hand-kept lists.
---

### Owner's answers (2026-10-23)

- **Q1:** (c), not the recommendation. Several discharge-pressure pumps may share one pressure zone (parallel boosters on one header); the solve searches for multiple steady states at solve time, more broadly than §5.10's single-pump tests, and reports not converged, naming the pumps and describing the states found, when it finds a second steady state that satisfies every rule, or when the regulating state it reached is unstable as a control system. There is no `PRESSURE_CONTROL_ZONE` issue. §5.11 is redesigned for this (owner-answer revision, §14.4).
- **Q2:** (a), the second-state tests V1–V7: not converged where the regulating state is unstable (r ≤ 1) or a pinned solve finds a second state that satisfies every rule.
- **Q3:** (b), solve the swapped state once; if it also holds, not converged, naming and describing both states.
- **Q4:** (a), `PUMP_FLOW_REVERSAL` (invalid) plus `PUMP_SETPOINT_NOT_MET` (info) stating the cause; revisit with sleep mode.
- **Q5:** (a), the measured acceptance criteria of §2.7, with the fixed point proven at tolerance 10⁻¹³.
- **Q6:** (a), v1's semantics: the state the iteration reaches, documented in TSD §12 and recorded as a documented fuzz class.
- **Q7:** (a), accepted for slice 2 as a documented limitation (TSD §12; VH7, PVH5), counted in the fuzz and revisited with that count.

---

### Owner's answers (2026-10-24, after C1's first build)

- **C1's rule:** neither the rule of §2.2 as specified (the review measured 85 converged solves that it leaves not converged and 31 state changes on 9,002 adversarial networks) nor amendment A1 (no regression, but it widens the slow-lag limitation to every active PRV whose outlet pipe ends at a free node). The owner chose to **design a broader fix first**: the exact Newton step on the whole downstream response of a held head (Q7 option (b), which replaces Q7's earlier answer (a)), as its own change set before C2, with its own design, measurement and METHOD_VERSION.
- **Criterion 3:** not accepted yet. The three projects that failed it with A1 (fuzzaf_20323 and fuzzaf_20611, differing only in their `NOT_CONVERGED` flag's copies of the ignored `convergence.*` fields, and fuzzfc_10246, whose five connections carry 1.13·10⁻¹² m³/s at 1.1.0 and 0 at 1.2.0) are to be investigated further before any C1 is committed.
- **C0** (the corpus tools' tolerance mode and solver-options override) is committed on its own: it changes no solver code.

### Owner's answers (2026-10-24, on the C1 redesign)

- **Q8:** (a). State changes of class D1 and D2 in the adversarial families are accepted, each named and checked on both sides (a PRV without a result included); criterion 4 stays strict for the corpus and the fuzz (criterion 9 as stated in §2.11.11).
- **Q9:** (a). C0b (the `NOT_CONVERGED` flag-location fix and the round-off-aware energy stop test) is its own change set under criteria B1–B8 (§2.11.10), METHOD_VERSION 1.2.0; C1 as redesigned (§2.11) is 1.3.0 and C2 (slice 2) 1.4.0.
- **Q10:** (a). Once C0b is in, C1's criterion 3 applies as written, plus one addition: a number outside its tolerance passes only if both trees agree within criterion 7 at the tight fixed-point settings, and it is listed by name; this is measured on top of C0b before it is claimed met.

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
| R10 | r ≤ 1: zone rule only (E), rule V (C), trace note (V) | Rule V and the zone rule, both as owner questions (Q1, Q2). The owner answered Q1 (c) and Q2 (a): rule V for a pump alone in its zone; rule S and the zone search for the rest (R15–R26) | Header bistability reproduced by J with today's solver; rule V misses closed-pump alternatives in parallel (§5.10, §5.11) |
| R11 | Over-control at a pressure setpoint: flow-only (E) or generalised (C, V) | Generalised | Measured silent arbitrary speed (C, §5.9) |
| R12 | Flow plus pressure series multiplicity: unmentioned (E), unique (C), two states (V) | Swap test (Q3) | V's closed-form enumeration (4 / 4,000); C's prototype cases were all unique |
| R13 | Fuzz seeds 13,000–15,999 (E) or 20,000–22,999 (C, V) | 20,000–22,999 | Majority; disjoint |
| R14 | C1's methods text: unconditional (E, C) or conditional (V) | Conditional on a PRV | The existing sentence at `methods.py:189-191` is unconditional; a change there would make every project differ |

**The owner-answer revision (Q1 (c)): the two zone designs, ZE and ZS, reconciled by ZJ** (§14.4):

| # | Conflict | Decision | Basis |
|---|---|---|---|
| R15 | V1's held-frame r at an unstable symmetric state: computed and > 1, so "V1 misses parallel instability" (ZE), or not computable (ZS) | Not computable; rule S's open-loop measurement replaces V1 for regulating pumps | *Measured* (ZJ `j1`): both held perturbed solves not converged at all six states; ZE's r values (33.2 to 7.0·10¹⁶) were read from those unconverged solves. In exact arithmetic the held r has the sign of det G/g_22, so it would refuse; the iteration cannot reach it (§5.11.4) |
| R16 | Perturbation: speed ±10⁻⁶ relative (ZE) or head offset ±10⁻⁴ m (ZS) | Head offset | One `OffsetLaw` mechanism for regulating pumps and V1's pumps at a limit (Schur complement); the verdict is identical (positive column scaling; *measured*, ZJ `j1`: NI −0.5032 both ways) |
| R17 | Stability basis: necessary conditions for decentralized integral controllability (ZE: Skogestad & Morari 1992, Theorems 1–2) or necessary and sufficient conditions for integrity (ZS: Kariwala, Forbes & Meadows 2005, Proposition 4) | The P-matrix test, cited to both | Both give it once the drives' fixed sign is added; ZJ read Proposition 4 and its remarks in ZS's copy and confirmed both records through Crossref (§14.4) |
| R18 | Flow-controlled pumps in the regulating set: no, ideal loops (ZE), or yes (ZS, its Q9) | Yes, when a pressure pump regulates | GOALS §3: their drives are integral loops too; flow-only projects run no rule S (C2 identity) |
| R19 | The search: a full bounded enumeration with a certificate, symmetry, two phases, corner pruning, 64 pinned solves and a cold retry (ZE), or a distance-ordered search with an open bound (ZS) | ZE's enumeration, permutations first then Hamming distance; one warm attempt without branch restart; limits 63 per zone per solve and 15 per curve point; certificate, symmetry and pruning not built | *Measured* (ZJ `j3`, `j5`): retries and restarts added no stable state; the certificate and pruning need ideal tees and symmetry needs port-less merged nodes, none of which the web app's Crane headers have (§5.11.12–§5.11.13) |
| R20 | Beyond the bound: converge with `STATE_SEARCH_INCOMPLETE` (ZE, asked as its N1) or "say so in the result" (ZS) | The flag, converged | GOALS §4.6 (an unreliable result is flagged); the owner's answer refuses where a second state is found |
| R21 | A rule-valid candidate the drives cannot hold: listed, not counted (ZE asked it as N3; ZS decided it) | Listed, not counted | The owner's own answer treats a control-unstable state as no answer; GOALS §3 (§5.11.7) |
| R22 | The index sum: trace and fuzz (ZS, asked as its Q10); not used (ZE) | Trace and fuzz count only | Fragile at degenerate states; measured first, as Q7's limitation was |
| R23 | Integrity (every principal minor) or only the full determinant and same-order minors (ZE N2, ZS Q8) | Every principal minor | GOALS §3: a state that a drive at a limit or in manual makes unstable is not one the inputs show a station holds; both designs recommended it |
| R24 | Curve points: the full search (ZE, asked as N4) or unspecified (ZS) | The same rules, a per-point limit of 15 and previous-point warm starts | *Measured* (ZJ `j6`): 41 × 63 candidates for a four-member zone would exceed the 45 s budget; previous-point warm starts cut the search by 39–47 % |
| R25 | A uniqueness certificate that skips the search (ZE, asked as N5) | Designed, not built (Later) | It never applies on the web app's Crane headers; ZE's proof is kept in §5.11.13 |
| R26 | Which zones are searched (ZE N6) | Only zones with a discharge-pressure pump and another member | C2's exact corpus identity; PRV-only multiplicity is risk 7, Later |

**The review of the owner-answer revision (ZR), decided by its reviser ZF** (§14.4.1):

| # | Question | Decision | Basis |
|---|---|---|---|
| R27 | How to bound a candidate's cost (ZR F1) | `CANDIDATE_MAX_ITERATIONS` = 30 per inner solve of every pinned solve, or `maxIterations` if lower | *Measured*: every rule-valid candidate converged within 14 iterations per inner solve in ZJ's 1,020 (`j7`); ZF's re-runs at 100, 1,000 and the cap found the same valid candidates on every network (`y1_cap.py`) |
| R28 | How to bound the whole search (ZR F1) | A budget counted in Newton iterations, 4,000 per solve and 10,000 per system curve, each curve its own; the 45 s deadline is not turned into a flag | Counts keep results the same on every machine and on both curve endpoints; the values cover the costliest measured three-member zone (1,734) and curve (7,956) with the cap; gate item 7 checks that the budget fits the request budget |
| R29 | When a not-converged text may state companion states (ZR F2) | Only where the frame determinant D_Z (§5.11.4) is negative, per zone; for S1, in the pump's own frame | The index sum gives companions only for index −1; *measured* counter-examples with index +1 and no companion (ZF `y5_box_vi.py`) |
| R30 | Fuzz pairs that the accepted limitations allow (ZR F3) | Documented classes 5 (two zones), 6 (the candidate's attempt did not converge) and 7 (search incomplete), counted; a candidate that converged to another state stays critical; remedies stated now (§5.11.13) | Keeps §9.5 consistent with §5.11.13 without hiding the one kind of miss never observed (ZJ `j3`) |
| R31 | How a Crane zone case proves one state (ZR F7) | A two-dimensional scan over (header head, split), or speed space, every root bracketed, repeated at twice the density | A pinned or one-dimensional search cannot show that no unstable root exists; *measured* on PZ8 (ZR, ZF) |
| R32 | Which solves and tests run with no regulating pressure pump, and on which blocks (ZR F5) | The perturbed solves whenever P = A ∪ L is not empty; the P-matrix test only on blocks with a regulating pressure pump | V3 and V4 need V1's r where nothing regulates (J `j5`, PN1); flow pumps keep slice 1's behaviour outside such blocks |

## Appendix B. Measurements

**The redesigned C1 (§2.11).** Its scripts live in `…/scratchpad/c1-redesign/<label>/` (labels `rank-update/`, `offset-cross-terms/`, `verification/`, `crit3/` and `judge/`; for its review, §2.11.15, `review-numerics/`, `review-verification/`, `skeptic-numerics/`, `skeptic-verification/` and the reviser's `revise/`). §2.11 names the script with each measured number, and its provenance paragraph states how the runs were isolated.

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

**The owner-answer revision (Q1 (c), §5.11, §14.4).** These scripts live in `…/scratchpad/zone-design/<label>/`. Each was run from `apps/api` with `.venv/bin/python` and `PYTHONPATH` set to a clean `git archive` copy of `f9d402b` in its own directory, and each printed or asserted that `opensolve_pipe.__file__` is that copy. No measurement wrote a repository file. The load on the 4-CPU machine varied (the concurrent session of §1.4 ran its own gates), so times are quoted only where the load was low, and costs are compared in Newton iterations.
- **ZE (zone design, enumeration), `enumeration/`** (rule set Z, C1 applied to its copy):
  - `zproto.py` (the members, rule set Z, the emulated main solve, the enumeration, G = ∂P/∂s), `nets.py` (the booster family), `oracle.py` (the header-head scan, independent of the GGA and the status logic);
  - `e1_two.py`, `e2_percand.py`, `e3_dp.py` (setpoint sweeps, both gain routes), `e4_three.py`, `search_opt.py`, `e5_undecided.py`, `e6_oracle_check.py`, `e7_random.py` with `analyze.py` (124 random networks against the oracle), `e8_cost.py`, `corners.py` with `e9_corners.py`, `e10_mixed.py`, `e11_curve.py`, `e12_zero_loss.py`, `e13_orders.py` with `analyze13.py`, `e14_closed_g.py`; records in `out/`.
- **ZS (zone design, control stability), `stability/scripts/`** (rule set Z on its own `booster.py`, without C1):
  - `s1_two_boosters.py`, `s2_speed_space.py` (speed-space Newton; quasi-static integral drives), `s3_three_boosters.py`, `s4_three_complete.py` (the nine states of three boosters, the index sum, timings `s4c`), `s5_mixed.py`, `s6_closed_form.py`, `s7_series.py`, `s8_saturated_r.py`, `s9_search_cost.py`, `s10_zero_loss.py`; logs `s*.log`; Kariwala, Forbes & Meadows (2005), downloaded by ZS, in `stability/dl/`.
- **ZJ (judge), `judge/`** (the copy holds `apps/api/src` and `apps/api/tests` of `f9d402b`, with the §2.2 code applied as `c1.patch`, and two instrumentation hooks added to its `gga.py`, a per-iteration trace and an optional flow stop, used only by `j3`, `j5` and `j7`):
  - `czone.py`: pinned outer solves inside the real `run_outer_loop` (a pinned pump is a fixed `Control` whose `LinkState` is overridden), the emulated loop over the members' rules, the candidate order, G by speed perturbations with the branch laws frozen or re-iterated; ZE's `zproto.py`, `nets.py` and `oracle.py`, re-pointed to this copy;
  - `j1_v1_held.py` (§5.11.4: V1's held perturbation with its convergence flag; G by speed and by head offset);
  - `j2_crane.py` (§5.11.1, §5.11.11: Crane against ideal headers, full enumerations);
  - `j3_candidates.py` with `j3_analyze.py`, `j3_analyze2.py` (§5.11.6: 1,455 candidates, warm, cold and without restarts);
  - `j4c_kcheck.py` (§5.11.4: frozen against re-iterated Crane K; `j4_crane_k.py` and `j4b_kcheck.py` are superseded, because they did not restore the tee leg laws that `run_outer_loop` mutates through `_apply`);
  - `j5_variants.py` with `j5_analyze.py` (§5.11.6, §5.11.12: the search's cost and its stable second states under five candidate-solve variants, 49 networks; the variants with a flow stop at 100 times the reached state's largest flow were rejected: with every member closed that flow is near zero and the stop ends every candidate at once);
  - `j6_curve.py`, `j6c_point.py` (§5.11.9: curve points, previous-point warm starts, the one disagreement explained);
  - `j7_inner_its.py` with `j7_analyze.py` (§5.11.12: iterations per candidate inner solve, caps);
  - `j8_speeds.py` (§5.11.10's example values); outputs and logs in `out/`.
- **ZR (review of the owner-answer revision), `review/`; its skeptic, `skeptic/`** (ZR's copy holds `apps/api/src` and `apps/api/tests` of `f9d402b` without the C1 patch; the skeptic re-ran ZR's scripts in its own copy):
  - `rz.py`: an independent prototype, the members pinned as fixed controls with the §5.2 `LinkState` inside the real `run_outer_loop`, the §5.4 rules as written, the open-loop G′;
  - `x1_enumerate.py` (full enumerations), `x2_cost.py` (the search's cost at `maxIterations` 100 and 1,000; the skeptic's logs `x2_pz5.log`, `x2_pz5c.log`), `x3_margins.py` (the margin by which each competitor fails), `x4_speed_space.py` (§9.3 step 5's speed-space scan); the skeptic's `vi_check.py` (affine box VIs). ZR also cites `x5_curve.py` and `x6_speed_space3.py`, which are not in its directory, so their numbers are quoted as ZR's only.
- **ZF (reviser of this round), `reviser2/`** (a clean `git archive` copy of `f9d402b`'s `apps/api/src` and `apps/api/tests` with ZJ's `c1.patch` applied; each script asserts that `opensolve_pipe.__file__` is that copy; load average 0.4–1.1 during the timed runs):
  - `rz.py`, `x1_enumerate.py`, `x3_margins.py`, `x4_speed_space.py`: ZR's, re-pointed to this copy (`y6_speed_space.log`: PZ8 and PZM1);
  - `y1_cap.py` (§5.11.6, §5.11.12: the search's cost and the valid candidates at `maxIterations` 100 and 1,000 and with the cap; logs `y1_pz8.log`, `y1_pz5.log`, `y1_pz5_crane.log`, `y1_multi.log`);
  - `y2_multizone.py` (three searched zones in one project, PZM8's network; `y2_3zones.log`) and `y4_budget.py` (the budget enforced before every inner solve; `y4_budget.log`);
  - `zj/y3_curve.py` with ZJ's `czone.py`, `zproto.py`, `nets.py` and `oracle.py` re-pointed to this copy (§5.11.9: ZJ's `j6` curves with and without the cap; `y3_curve.log`);
  - `y5_box_vi.py` (§5.11.5: affine box VIs, the index sum and companions; `y5_box_vi.log`), `y7_s3_example.py` (§9.3: the exit-text matrices);
  - ZJ's `j5` and `j7` records (`judge/out/`) re-analysed for wall times and for the search's cost with the cap (§5.11.1, §5.11.12).

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
- Q1: answered (c) after the review, not the recommendation; §14.4.

### 14.4 Owner-answer revision (Q1 (c))

**The answer.** The owner answered Q1 with (c) on 2026-10-23: several discharge-pressure pumps may share one pressure zone (parallel boosters on one header, each holding its own discharge port's static pressure); there is no `PRESSURE_CONTROL_ZONE` and no 422; the solve searches for multiple steady states at solve time, more broadly than §5.10's single-pump tests, and reports not converged, naming the pumps and describing the states found, when it finds a second steady state that satisfies every rule or when the regulating state it reached is unstable as a control system. Q2–Q7 were answered as recommended.

**How the revision was made.** Two independent designs answered it, each from one angle, each with a prototype on a clean copy of `f9d402b`:
- **ZE (enumeration):** the zone partition and members; an exhaustive search of the members' status combinations as pinned solves, with a uniqueness certificate that skips it, symmetry, two phases, corner pruning, a bound of 64 pinned solves and a cold retry; a stability test S on G = ∂P/∂s (P-matrix, after Skogestad & Morari 1992); an oracle independent of the GGA; 124 random networks; six owner questions (N1–N6).
- **ZS (stability):** rule S on the open-loop response G′ = ∂y/∂e (P-matrix, after Kariwala, Forbes & Meadows 2005), with its resolution, blocks, exits and the Schur complement for V1; the index sum over a frozen frame; closed forms; a sketch of the search; three owner questions (Q8–Q10).

A judge, **ZJ**, compared them, checked the disputed claims against the code at `f9d402b` and by experiment (Appendix B, `zone-design/judge/`), chose and merged, and revised this document. The merged design is §5.11; Appendix A rows R15–R26 record each conflict.

**What ZJ verified, found or decided:**
- **ZJ-1, V1 at unstable states** (R15). ZE reported V1's held-frame r at symmetric unstable states as 33.2 to 7.0·10¹⁶, so that "V1 accepts" them; ZS reported that the held solves do not converge. *Measured* (ZJ `j1_v1_held.py`): at all six states both perturbed solves ended not converged after 100 iterations, with exactly ZE's r values read from them (ZE's `r_ratio` does not read the convergence flag). ZS is right; under the first draft V7 would have refused with the wrong reason. Rule S's open-loop solves converged in 3 iterations everywhere.
- **ZJ-2, the web app's default header.** Both designs measured ideal tees only, and ZE argued that real stations pass its certificate. The web app creates Crane tees (`factory.ts:260`, `273`) and adds no default fittings on pump connections (`edit.ts:152-175`). ZJ prototyped pinned solves in the real outer loop, with Crane branches (`czone.py`). *Measured* (ZJ `j2_crane.py`, `j5_variants.py`): 28 Crane headers, one valid state each reached by pinned solves (which cannot reach a control-unstable state: qualified after ZR F7, §14.4.1); the same inputs on ideal tees, several. Crane legs have port roles, so no member is interchangeable, and ZE's certificate and corner pruning (ideal tees only) never apply there: those are not built (R19, R25) and the search is costed in full on Crane headers.
- **ZJ-3, the candidate solve** (R19). *Measured* (ZJ `j3_candidates.py`, `j5_variants.py`, 1,455 candidates in 49 networks): branch restarts and a cold retry found no additional state the drives can hold (the cold retry found one rule-valid state, control-unstable), at 19 % more Newton iterations at the median and twice as many at the maximum for three-member zones; one warm attempt without restart is the design.
- **ZJ-4, Crane K in rule S.** The perturbed solves freeze the branch laws. *Measured* (ZJ `j4c_kcheck.py`): against Crane K re-iterated, G agrees within 1.5·10⁻⁶ relative, because the leg laws carry K's tangent in the split (`elements.py:177-230`). (ZJ's first two scripts for this, `j4`, `j4b`, compared against laws that `run_outer_loop` had mutated through `_apply`, and are superseded.)
- **ZJ-5, cost.** Neither design measured the search with the real outer loop. *Measured* (ZJ `j5_variants.py`): a median of 295 Newton iterations per solve for a two-member zone and 2,149 for three (max 3,561), about 1 ms per iteration on these networks; the failing candidates and the Crane K iterations dominate. A three-member zone can miss PRD §4.2's 1 s; §5.11.12 states the gate and the remedies (a per-candidate cap, *measured* −38 % with no valid candidate lost in 1,020, ZJ `j7_inner_its.py`; symmetry; the certificate).
- **ZJ-6, curve points** (R24). *Measured* (ZJ `j6_curve.py`): a three-booster curve costs 3,000–14,000 Newton iterations with previous-point warm starts (39–47 % less than warm starts from the point's own state); a four-member zone at 63 candidates per point would exceed the 45 s budget, hence `ZONE_SEARCH_POINT_LIMIT` = 15. The one point where the two warm starts disagreed (ZJ `j6c_point.py`) was a pump regulating at 2.3·10⁻⁵ m³/s against the same pump closed: one physical state by `at_rest_more`, which ZJ's first analysis had not applied.
- **ZJ-7, the fuzz's independence.** The designs pinned an active pressure pump in `state_search` by its control with a widened range; under Q1 (c) the checker's own solves would then run rule S and the zone search, the code under test. The pin is now the EPANET substitute of §9.4 in our own solver, so no pinned project has a discharge-pressure pump (§9.5).
- **ZJ-8, the index sum.** ZS's statement rests on the generalized Poincaré–Hopf theorem (Simsek, Ozdaglar & Acemoglu 2007, record confirmed, not read) and degree theory (Facchinei & Pang 2003, theorem numbers not checked). ZJ derived it directly (the homotopy to s − s₀ on the box, §5.11.5) and kept it a diagnostic (R22).
- **ZJ-9, citations.** Confirmed through Crossref (title, journal, volume, pages): Kariwala, Forbes & Meadows (2005); Skogestad & Morari (1992); Grosdidier, Morari & Holt (1985); Niederlinski (1971); Campo & Morari (1994); Gündes & Kabuli (2001), IEEE TAC 46(2) 296–301, doi:10.1109/9.905697; Simsek, Ozdaglar & Acemoglu (2007). Read: Kariwala et al. (2005), Proposition 4 and the remarks after it, by ZS and by ZJ in ZS's copy (the iff for up to four blocks from Gündes & Kabuli, "the extension to the general case is simple (by induction)", and "for fully decentralized control … guarantees the existence of a pure integral action controller such that G(s) has integrity"); Skogestad & Morari (1992), Theorems 1–2 and the DIC definition, by ZE. Not read: Grosdidier et al., Niederlinski, Campo & Morari, Gündes & Kabuli (cited only through the two read papers). Not confirmed and not cited: Yu & Fan (1990); the textbook DIC theorems ZS saw in a search summary.

**The designs' owner questions, and why none is asked** (each decided by GOALS §3, the owner's own answer, or a precedent the owner set):
- ZE N1, the limit reached: converge with `STATE_SEARCH_INCOMPLETE` (R20).
- ZE N2 and ZS Q8, integrity: every principal minor (R23).
- ZE N3, rule-valid states the drives cannot hold: listed, not counted (R21).
- ZE N4, curve points: the same rules, a lower per-point limit, disclosed per point (R24).
- ZE N5, the certificate: not built (R25).
- ZE N6, which zones: those with a pressure pump (R26).
- ZS Q9, flow pumps in rule S: yes, when a pressure pump regulates (R18).
- ZS Q10, the index sum: diagnostic, counted first (R22).

The one trade-off GOALS §3 decides that the owner may wish to see: the search's breadth, which the answer asks for, can make a project with three or more pumps or pressure valves in one zone slower than PRD §4.2's 1 s for simple systems (ZJ-5). Correctness ranks above usability, so the search is kept and the gate records the times; the remedies are measured and ready (§5.11.12).

**Sections changed by this revision:** the header; §1.1 item 5; §1.5; §2.3's last bullet; §2.10 item 7; §3.3; §4.3 (no topology issue); §4.6's changelog; §5.6 item 2; §5.10 (scope, pinned-solve arguments, V1, V2 = S, V6 removed, V7 = S5, V2's message, cost); §5.11 (rewritten); §6 rows 3, 18, 27, 28 and new rows 29–33; §7; §8.1; §8.2 items 4 and 5; §9.2; §9.3 (PZ1–PZ8, PZ-G, PZM1–PZM7); §9.5; §9.7; §9.8; §9.11; §10 items 6 and 7; §11; §12 risks 5, 8, 14 and new 17–19; §13 Q1 (answered (c)) and the answers block; §14.3; Appendix A (R10, R15–R26); Appendix B. Removed: `PRESSURE_CONTROL_ZONE`, its 422, its web text (`issue-text.ts`), its methods item and its Bentley citation in the method, and the fuzz generator's exclusion of two pressure pumps from one zone.

#### 14.4.1 Review of the owner-answer revision (ZR) and its disposition

A review of §5.11 as ZJ merged it (**ZR**, with a skeptic who re-ran each script in its own clean copy, Appendix B) raised ten findings; the skeptic upheld six and rejected four. The reviser, **ZF**, re-checked each upheld finding against the code at `f9d402b` and by experiment in its own clean copy with the C1 patch (Appendix B, ZF) before changing the design. Appendix A rows R27–R32 record the decisions.

**Upheld:**

| ID | Severity | Finding | Re-checked against | What was done |
|---|---|---|---|---|
| F1 | major | The cost bounds and the gate assumed `maxIterations` 100. A failing candidate costs at least the project's `maxIterations` (up to 1,000) per inner solve, nothing capped a candidate, a search or several zones, so a project could pass the 45 s budget and get no result at all, and "results do not depend on machine speed" did not hold. The gate quoted iterations × 1 ms, not wall times. | `models/project.py:42-44` (`max_iterations` 10–1,000); `run_outer_loop` (`status.py:1586-1862`: every inner solve at `max_iterations`, fallbacks while fewer than 30 counted outer iterations, holds and releases of zero-flow legs uncounted, `MAX_DEAD_CLOSURES` 2); ZJ's `j3` records (failed single attempts of 100, 113 and 157 Newton iterations at 100, up to 257 with restarts); ZJ's `j5` wall times (two members: median 0.73 s, max 1.08 s; three: 4.09 s, 10.28 s). Reproduced ZR's costs within 1 % (ZF `y1_cap.py`: PZ8 478 and 1,599 Newton iterations at 100 and 1,000; PZ5 2,769 and 20,095, 3.23 s and 20.72 s; on Crane tees 3,553 and 14,334) and measured what ZR derived: three three-member Crane zones at 1,000, 42,980 Newton iterations and 49.55 s of candidate solves (`y2_multizone.py`). | Built the earlier remedy 1 and a budget (§5.11.6): `CANDIDATE_MAX_ITERATIONS` = 30 per inner solve of every pinned solve; `SEARCH_NEWTON_BUDGET` = 4,000 per solve and `CURVE_SEARCH_NEWTON_BUDGET` = 10,000 per system curve, checked before every inner solve; the search stops with `STATE_SEARCH_INCOMPLETE` (new texts and `stoppedBy` details) and keeps the converged result. The real bound stated: (30 + 4b) × 30 per pinned solve, the budget per search. *Measured* with the cap: PZ8 268 Newton iterations, 0.30 s; PZ5 1,073, 1.32 s; on Crane tees 1,711, 2.72 s; the same valid candidates in every setting on six networks; three zones 5,114 in 6.84–7.22 s, and with the budget 4,000 in 5.95 s, stopped in the third zone (`y4_budget.py`); curves 2,394–7,956, 3.6–10.8 s (`zj/y3_curve.py`). §5.11.12 quotes measured wall times; the gate gains `maxIterations` 1,000 runs, several zones (new PZM8, §9.3) and a check that the budget fits the request budget (item 7); the fuzz checks that the search does not depend on `maxIterations` (`a_search_iterations`); methods item 5 discloses the numbers. |
| F2 | major | S2 ("det G′_JJ ≤ 0 for some J") took in every failing subset, so S3 was unreachable and "every tuning" false for proper subsets; S2's text and methods item 5 claimed companions that the index sum gives only for index −1 (det < 0), not through an order's minors with det > 0, S3, or S1 with two or more pumps; "separated by" claimed more than the sum gives; across zones det G′_AA is not a frame's index. | §5.11.4–§5.11.5, §5.11.10, §8.2 as written. ZF `y5_box_vi.py` (affine box VIs, every face enumerated, independent of ZR's `vi_check.py`): G′ = [[1, 3], [−3, −1]] has its regulating state as its only state (index +1); so does ZR's 3×3 (det +1.567, all 2×2 minors negative); in 200,000 random 3×3 frames the index sum was always 1 and every det < 0 state had at least two companions, and 15 of 94 frames of PZM6's kind had the regulating state alone. ZR's PZM1 values (det −0.024502, NI −0.329) are the S2 example's. | §5.11.4: S2 = det G′_BB resolved negative, or every principal minor of one order ≤ 0 with one resolved negative; S3 = any other failing minor; the frame determinant D_Z = det G′_AA / det G′_OO per zone. §5.11.5's consequences rewritten (companions only for D_Z < 0; "among two or more nondegenerate states at least one has a negative determinant"; index +1 states imply nothing). §5.11.10: two S2 templates, the companion sentence only where D_Z < 0, per zone; S1's clause in the pump's own frame for two or more pumps (§5.10). §5.11.7's "Why (4)" and methods item 5 reworded as proposed. Byte-level text tests on a G′ of each kind, the S3 example from `y7_s3_example.py` (§9.3, §9.7). |
| F3 | major | §9.5's `control_search` pins every member of every searched zone jointly, across zones, so a fuzz-found instance of any limitation that §5.11.13 and risk 8 accept (a stable state the single attempt does not reach, a multiplicity across two zones, zones joined by a PRV that ends open) was critical, with no class and no remedy: the defect RVG-6 had fixed once. | §9.5 against §5.11.13 and risk 8; ZJ `j3` (every rule-valid candidate that any attempt found, the single warm attempt found too, except one control-unstable state found only cold); ZF `y1`: 25 of PZ5's 63 candidates without a converged solve with the cap (23 at 100 without). | §9.5 gains classes 5 (two zones), 6 (the candidate's, or V3–V5's, pinned attempt did not converge, read from the trace, which now lists those assignments, §5.11.10) and 7 (search incomplete, from the order and the flag's details), each mechanical, counted, pinned in TSD §10.4, not critical; a candidate whose attempt converged to another state stays critical (never observed). §5.11.13 states the limitations to match and, before the fuzz runs, the remedy each class triggers (a cold second attempt; a joint search of the zones involved), each a design change for the owner if its count is not zero; risk 8, §1.5 and R30 agree. |
| F5 | minor | "Otherwise A is empty and S does not run" could be read as skipping the perturbed solves that V1 needs for a lone pump at a limit when nothing regulates (J `j5`, PN1); and every block of G′ was tested, so a block of flow pumps alone came under S because a pressure pump regulated elsewhere. | §5.11.4's sets; §5.10's V1 row; §9.7's J `j5` test, which relies on V1's r with A empty | §5.11.4: the perturbed solves run whenever P = A ∪ L is not empty; the P-matrix test runs only on blocks holding a regulating pressure pump. §5.10's V1, §5.11.1's table and methods item 4 follow. §9.7: a test of V1 with A empty on J `j5`, and one with an injected flow-pump block that is not a P-matrix. R32. |
| F7 | minor | "In 28 Crane-tee headers the full enumeration found no second rule-valid state" overclaims: pinned solves are repelled from control-unstable roots, which §9.2 counts against a case file; PZ8's derivation by `brentq` on the split at each header head does not prove one root. | Re-ran ZR's speed-space scan in ZF's copy (`y6_speed_space.log`): PZ8 has no (A, A) root, (A, X) valid by 0.3254 m, (X, A) failing X1 by 0.1176 m; on PZM1 the scan finds the unstable (A, A) (det −165.2). | Claims restated as "reached by pinned solves" (§5.6 item 2, §5.11.1, §5.11.11's note and ZJ bullet, §6 row 30, risks 18 and 19, ZJ-2). §9.2: unstable roots count, and each zone derivation must find them. §9.3 step 5: a two-dimensional scan over (header head, split) or a speed-space scan, every root of the split equation bracketed, repeated at twice the density; PZ8's row states the scan's result. R31. |
| F9 | minor | Text left behind: §11's "V1–V7"; the no_flow note always naming V5; PN2's network given ZE `e10`'s three states in §5.11.8 and §6 row 28; "(A, X) at candidate 2" where the order gives (X, A); the answers block's Q1 entry without the instability clause. | The order of §5.11.6 from (A, A): (C, A), (X, A), (N, A), (A, C), (A, X), (A, N) (ZJ's `czone.candidates` sorts the same way) | §11 lists the converged-exit tests as built; the no_flow note names V5 only for a pump alone in its zone that V5 ran on, and the zone search otherwise; PN2 (one booster, two states) separated from `e10`/PZM4 (two boosters, three states) and PZ7; (X, A) at candidate 2 in §5.11.11 and PZM1; the Q1 answer gains "or when the regulating state it reached is unstable as a control system". |

**Rejected (recorded, not applied):**

| ID | Finding | Skeptic's reason for rejecting it |
|---|---|---|
| F4 | S3 refuses a regulating state that some tuning holds while every drive regulates, perhaps the only steady state, for lack of integrity; integrity is a controllability or design-practice criterion, design checks are opt-in (GOALS §4.6), and R23 decided it without the owner. | Refusing S3 is the stability criterion the design was asked to use, not a design-practice check: decentralized integral controllability (Skogestad & Morari; Grosdidier, Morari & Holt), the framework named, is defined with each loop detunable to zero, which is integrity, and Kariwala, Forbes & Meadows' Proposition 4 is an integrity result. R23 records the decision, risk 17 discloses it, and the S3 text names the drive that makes the state unstable. Whether such a state is held depends on a tuning the model does not have, so refusing it follows GOALS §3, not §4.6. The finding's own derivation shows S3 does not arise in the parallel-booster class, so no wrong refusal has been shown. |
| F6 | Candidates without a converged solve and an index sum other than 1 are reported only in the trace, with no flag, though the owner asked never to skip silently. | Neither is silent: the search line prints the count with no converged solution (now with their assignments) and the index line prints "at least one steady state of these pumps was not found". The owner's "never silently skip" concerned candidates left unsolved beyond the bound, which get the flag. A candidate with no converged pinned solve is not a skipped search: most such pins have no state at all (PZ8 3 of 15, PZ5 23 of 63, each with one rule-valid state), and flagging every such zone would empty the flag of meaning. Keeping the fragile index sum out of flags is recorded (R22), and the fuzz counts it. |
| F8 | Active PRVs and PSVs in a searched zone are members, yet S takes their loops as ideal, so a PRV regulating at a falling static pressure (r ≤ 1) beside a regulating booster is reported converged though unstable as a control system. | A documented modelling choice (§5.11.4 "What S does not cover", §5.11.13 limitation 3, risks 7 and 17, methods item 4). Refusing or flagging a member PRV with r ≤ 1 would extend v1's PRV multiplicity handling, which risk 7 defers to its own method version. The finding did not show the main solve reaching such a state, and the owner's "unstable as a control system" concerns the pump drives the answer is about. |
| F10 | The cited sources exist and Proposition 4 says what the design reports, but the support beyond four blocks is a remark and one attribution is wrong. | The finding confirms the citations. §5.11.4 already says Gündes & Kabuli give the conditions for up to four blocks and the NI form extends "by induction" (Kariwala et al., pp. 1576 and 1578 in ZS's copy); Kariwala et al. label the result "Theorem 2 (Gündes & Kabuli, 2001)", so "(their Theorem 2)" is at worst ambiguous; the GMH theorem numbers are given as cited through Skogestad & Morari. A time-scale derivation would be an enhancement, not a correction. |

**Sections changed by this round:** the header; §1.1 item 5; §1.5; §3.3; §4.6's changelog; §5.6 item 2; §5.10 (the pinned-solve arguments, V1's solves with A empty, the companion clause of S1, cost); §5.11.1 (table, Crane bullet, cost bullet); §5.11.3; §5.11.4 (sets, tested blocks, condition, exits, the frame determinant); §5.11.5 (index, consequences, diagnostic); §5.11.6 (candidate solve, limits, beyond a limit); §5.11.7; §5.11.8 (V6 bullet); §5.11.9; §5.11.10 (search line, S1, S2, `STATE_SEARCH_INCOMPLETE`); §5.11.11 (row 1, the table's note, ZJ's bullet); §5.11.12 (rewritten); §5.11.13 (limitations, remedies); §6 rows 28, 30, 31 and new 34; §7; §8.1 (the no_flow note, values); §8.2 items 4 and 5 and "This solve"; §9.2; §9.3 (step 5, PZ8, PZM1, new PZM8, the exit texts); §9.5 (state_search, the criticality classes, stats, count gates); §9.7; §9.8; §9.11; §11; §12 risks 5, 8, 18 and 19; §13's answers block (Q1); §14.4 ZJ-2; Appendix A (R27–R32); Appendix B (ZR, ZF).
