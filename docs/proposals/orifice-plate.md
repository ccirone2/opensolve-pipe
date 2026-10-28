# Orifice plate: design proposal

**Status: built** (2026-10-28; CLAUDE.md D20; §12 records where the build departs from this design). The owner answered its questions on 2026-10-27 (§10). Written on 2026-10-27 against `2014c6e` (D18 merged) by a design workflow. Three designers each worked from their own angle, with prototypes: one on the physics, model and solver, one on the sources and verification (citations read, closed-form cases, EPANET runs, a corpus survey), and one on the web. A synthesizer merged their designs into this one. It checked the disputed claims against the code and by calculation (the **S** checks in §7.7) and wrote this document. Two reviewers, one on the physics and one on the product, then reviewed it, and a reviser checked each finding (the **R** checks in §7.7) and revised the design at the root. §11 records each finding, whether it was upheld, and what changed. §1.3 lists where the designs disagreed and why this design chose as it did. §10 holds the owner's answers to its product questions, and §12 the as-built record.

**The owner's request (2026-10-27):** "Orifice plate: restriction orifices (minimum-flow bypasses, balancing) and orifice flow meters. Discharge coefficient and permanent pressure loss per ISO 5167-2, from the fluids library already used. A two-port element like equipment, and fully checkable by hand."

D5 lists "sprinklers, orifices and user-defined elements" as deferred. This slice moves the square-edged orifice plate into v1. Sprinklers, user-defined elements and the other plate types stay Later (§9). PRD §3.1.1 lists "Orifice: Diameter, Cd, or Cv, 2 ports". This design takes the diameter and C. It leaves out a Cv on the orifice, because an orifice rated only by a Cv or Kv is already D18's equipment element (Q1).

The workflow had already decided these points, which were not re-opened:
- D1–D18 are binding.
- The work is one verified slice; anything bigger goes in §9.
- The change touches the API, so it does not go on a `web/` branch (CLAUDE.md, Tooling).

Every other choice is the designers' own and reversible under D14.

**Sources read:**
- **Specs:** PRD §3.1, §3.8, §3.9; SDD §4.2, §4.10, §4.12–§4.14; TSD §4.9, §10.4, §12; GOALS §3–§6; CLAUDE.md D1–D18; `docs/proposals/equipment-pressure-drop.md`, the precedent this design follows.
- **API code** at `2014c6e`: `models/{components,results,scenarios,goal_seek,piping}.py`; `services/solver/{elements,network,builder,equipment,valves,gga,status,system_curve,results,trace,methods,flags,version}.py`; `services/{scenarios,goal_seek}.py`; `tests/reference/*` and `tests/differential/{equipment_check,compare,corpus}.py`.
- **Web code:** `utils/{factory,compare,goal-seek,scenarios,model-rules,validate,results,flag-text,issue-text}.ts`, `utils/export/{tables,about}.ts`, `components/panel/*` and `components/results/*`.
- **Cited sources:** §3.10 says what each one supports and how it was verified. fluids 1.3.1's `flow_meter.py` was read in its installed source.
- **Prototypes and logs** are in the workflow's scratchpad (`orifice-design/`, not committed):
  - physics: `orifice_law.py`, `proto_law.py`, `proto_gga.py`, `proto_gga2.py`, `proto_dcdre.py`, `proto_monotone.py`, `proto_cases.py`, `proto_epanet.py`, `proto_borda.py` and `proto_inverse.py`, each with its `*.out.txt`;
  - sources: `verify_fluids.py`, `orifice_law.py`, `proto_cases.py`, `proto_sensitivity.py`, `epanet_proto.py`, `proto_extra.py`, `proto_bore.py`, `proto_slope.py` and `corpus_survey.py`, each with its `*.out.txt`, plus the downloaded documents in `downloads/`;
  - web: `taps_probe.py`, `e2e_values.py` and `e2e_entered.py`, each with its `*.out.txt`;
  - synthesizer: `synth/s1_loss_c.py`, `law.py`, `cases.py`, `epanet.py`, `gs.py`, `e2e.py` and `s7_meter_c.py`, each with its `*.out.txt` (`law.py` is the law the others import);
  - reviewers: `reviewer-physics/*.py` and `reviewer-product/*.py`, with their outputs;
  - reviser: `reviser/law2.py` (the revised law: the entered C's move, the continuous Re_lo, the cancellation-free K), `checks.py`, `ratio_checks.py`, `mono2.py` to `mono5.py`, `rbound.py`, `rvar.py`, `cases2.py`, `cases3.py` and `cases4.py`, each with its `*.out.txt` (`cases3.py` is `cases4.py` with the additive move, kept as the record of the rejected form).

**Test inputs.** Every bore, pipe, level and fluid in the cases below is a made-up test input, entered as the user's data. Every result number was measured by the prototype named next to it.

---

## 1. Scope and decisions

### 1.1 Scope

This slice adds one new two-port component, `orifice`, inlet → outlet: a square-edged concentric orifice plate. It serves as a restriction orifice (a minimum-flow bypass, a balancing leg) or as a flow meter. The user enters:
- its **bore diameter** d (required);
- optionally, an **entered C** (from a calibration or datasheet): ISO 5167-2's discharge coefficient C of eq. (1) at the plate's taps, at D and D/2 tappings for a plate without taps. It is not the flow coefficient α = C/√(1 − β⁴). Without one, C is ISO 5167-2's Reader-Harris/Gallagher equation, the cited default;
- optionally, the **pressure taps** of a meter: corner, flange, or D and D/2. Without taps it is a restriction orifice, and no meter reading is reported.

The pipe bore D is the inlet pipe's (β = d/D). The law is on the EGL:

```
h(Q) = EGL_inlet − EGL_outlet = K(C_L) · v|v| / (2g),   v = Q / (πD²/4)
K(C) = u²,  u = (1 − β⁴) / (C β² (S + C β²)),  S = √(1 − β⁴(1 − C²)),  1 − β⁴ = (1 − β)(1 + β)(1 + β²)
       ISO 5167-2's pressure-loss relation over ρv²/2: (S/(Cβ²) − 1)², fluids discharge_coefficient_to_K,
       written without its cancellation as β → 1, with 1 − β = (D − d)/D
C_L  = Reader-Harris/Gallagher (ISO 5167-2:2003 eq. 4) at D and D/2 tappings at Re_eff = max(Re_D, Re_lo),
       Re_D = 4ρ|Q|/(πDμ), Re_lo ISO's lowest Re (made continuous at β 0.56); or an entered C_e moved to
       D and D/2 tappings: C_e · C_ISO(D and D/2, Re_eff) / C_ISO(taps, Re_eff) at corner or flange taps,
       C_e itself without taps or at D and D/2 taps
Δp   = (1 − β⁴) / (C_M² β⁴) · ρ v|v| / 2               the meter's reading (ISO eq. 1, ε = 1); C_M is ISO's C
                                                       at its taps, or the entered C as entered
p_vc = p_up + ρg(z_up − z_down) − (1 − β⁴) / (C_L² β⁴) · ρ v² / 2
                                                       the vena contracta pressure, at the elevation of the port
                                                       the flow leaves by; checked for flashing; none at zero flow
```

h depends only on the element's own flow. The element is therefore an exact Newton link with an analytic slope, like a pipe under Colebrook. It needs no lag and no status logic, and `gga.py`, `status.py` and `system_curve.py` are unchanged.

**Not in this slice** (Later, §9): other plate types (eccentric, quadrant-edge, conical, multi-hole, multi-stage), nozzles and venturis, gases, a low-Re C correlation, choked flow and an incipient-cavitation check, ISO's uncertainty of C, installation checks, a reverse-flow (bevelled) model, a Cv on the orifice, and a fuzz profile.

**Deliberate departures, named** (as D9 names its departures from EPANET), each stated in the methods summary and the trace:
- **One loss per plate.** The loss uses the C at D and D/2 tappings for every plate, whatever its taps (decision 5). ISO's pressure-loss relation read literally takes the meter's own C, which gives a corner- or flange-tapped meter a K up to 5.95 % higher at β 0.75 and a flow up to 2.6 % lower on a line the plate dominates (R1, on 2 m lines of 102.3 and 300 mm at Re about 10⁵–10⁶). Over ISO's whole range (D 50 mm–1 m, β 0.1–0.75, Re_D from Re_lo up) the largest are a K 6.14 % higher at corner and 6.34 % at flange tappings (β 0.75 as Re_D grows, flange on a 1 m pipe) and a flow 2.94 % and 3.03 % lower where the plate takes the whole head, which the methods summary and the trace state (§12 item 41). This reads the owner's "permanent pressure loss per ISO 5167-2", so it is also owner question Q3.
- **D and D/2 rather than Reader-Harris et al.'s L2′ = 0.125** for that C (decision 5). Their C gives a K up to 1.2 % lower and a flow up to +0.56 % on such a line at β 0.75 (R2); over ISO's whole range, a K 0.063–1.24 % lower and a flow up to +0.63 % where the plate takes the whole head (§12 item 41).
- **ISO's lowest Reynolds number made continuous**, max(5000, 16000β²) for corner and D and D/2 tappings, stricter than ISO's only for 0.559 < β ≤ 0.56, by up to 17.6 (decision 7).

### 1.2 Decisions

Origin key:
- **P**: the physics, model and solver designer.
- **V**: the sources and verification designer.
- **W**: the web designer.
- **S**: the synthesizer, resolving a disagreement (§1.3) or adding what the designs missed.

| # | Decision | Reason | Origin |
|---|---|---|---|
| 1 | **One component type `orifice`** (`Orifice`), ports `inlet` → `outlet` (`x-port-ids`, `x-port-roles`). It serves restriction orifices and meters. It has **no status**: valves isolate it. | D18's precedent. A plate always passes flow. A meter differs from a restriction orifice only in its taps (decision 2), and one plate has one loss whatever its taps (decision 5). | P, W |
| 2 | **Fields:** `boreDiameter` d (m, (0, 10], required, no default); `dischargeCoefficient` (a number in (0, 1], or absent); `taps` (`corner`, `flange` or `d_and_d_2`, or absent). An absent `dischargeCoefficient` means ISO 5167-2's C, the cited default. A number is an entered C, user data: ISO 5167-2's C of eq. (1), q_m = C/√(1 − β⁴)·ε·(π/4)d²·√(2Δpρ), with Δp between the plate's taps, or between D and D/2 tappings for a plate without taps. It is not the flow coefficient α = C/√(1 − β⁴) that datasheets often quote, and the schema text, form and trace say so. An absent `taps` means a plate with no pressure taps: no reading. `schemaVersion` stays 1. | GOALS §4.1: no source gives a default bore, so d is required; ISO 5167-2 is the cited source of C, so it is the default, labelled "default" (D10), and an entered C overrides it, labelled as user data. This is exactly how D8/D9 treat a valve's K: Crane by default, a user value overrides it. GOALS §4.2 and D11 ("the field's meaning is stated, not inferred") require C's definition: entered as C, an α moves the flow by up to +20 % at β 0.7 (product review). The taps decide whether a reading is reported, and where (decision 14), and where an entered C was measured (decision 13). With ISO's C they change no solved value, so their absence assumes nothing. (0, 10] is the pipe inner-diameter bound (`piping.py`). C ≤ 1: in the loss relation C ≤ 1 is exactly μ ≤ 1, a jet no larger than the bore (decision 17). | S over P and W (§1.3 items 2–3); R (C's definition, §11 F10) |
| 3 | **D is the inner diameter of the inlet pipe's end segment** at the inlet port, as for a valve's K (D9). d and D are taken at flowing conditions; thermal expansion is not modelled, and the trace says so. | ISO's D is the upstream pipe's bore (fluids: "Upstream internal pipe diameter"). The plate's geometry does not depend on the flow direction. `UNCONNECTED_PORT` guarantees an inlet pipe. | P, W |
| 4 | **The law** h = K(C_L)·v\|v\|/(2g), with K from `fluids.flow_meter.discharge_coefficient_to_K(D, d, C_L)`. | ISO's pressure-loss relation Δϖ = [√(1−β⁴(1−C²)) − Cβ²]/[√(1−β⁴(1−C²)) + Cβ²]·Δp, with Δp from eq. (1), is K(C)·ρv²/2 exactly (V: 1.9×10⁻¹² over 10⁵ draws; W: 3.3×10⁻¹⁶). It is Borda–Carnot's (1/(μβ²) − 1)² with the vena-contracta ratio μ = C/√(1−β⁴(1−C²)) (P, V: to 1.8×10⁻¹⁴). ISO's alternative, 1 − β^1.9, differs by up to −4.5 % at β = 0.75 (S1), so it is not used. | P, V |
| 5 | **The C that sets the loss, C_L, is the C at D and D/2 tappings for every plate, whatever its own taps:** ISO's C there, or an entered C moved there (decision 13). The meter's taps set its reading (decision 14). This is a named departure from ISO's relation read literally with the meter's own C (§1.1), and owner question Q3. | One plate has one permanent loss, which cannot depend on where the meter's taps were drilled. The loss relation's theory (Urner 1997, as given by Reader-Harris et al. 2019) takes C "using tappings 1D upstream" and downstream between the plate and the vena contracta. Of ISO's three tap sets, only D and D/2 has L1 = 1. Deltares WANDA's orifice model makes the same choice: "the RHG equation for D and D/2 tappings is applicable". Reader-Harris et al. 2019 themselves take p2 at 0.125D downstream ("it has to be between the downstream corner and the vena contracta"), with C_DandP from RHG at L1 = 1 and L2′ = 0.125. That C gives a K 0.06–1.2 % lower than D and D/2's for β 0.1–0.75 (S1, at Re 10⁵), which moves the flow by up to +0.56 % at β 0.75 on a line the plate dominates (R2), just beyond D6 (over ISO's whole range 0.063–1.24 % in K and +0.63 % in flow, §12 item 41). This design keeps D and D/2, an ISO tap set with ISO's own Reynolds limits and WANDA's precedent, rather than an RHG evaluation at a tap position ISO does not list; the trace and methods state the alternative and its size. With each meter's own C, corner and flange taps would give a K up to +5.95 % and +5.57 % (R1's lines; over ISO's whole range +6.14 % and +6.34 %, §12 item 41), and a restriction orifice, which has no taps, an arbitrary answer. | S, from V over P and W (§1.3 item 1); R (§1.3 item 13, Q3) |
| 6 | **C from `fluids.flow_meter.C_Reader_Harris_Gallagher(D, d, ρ, μ, m, taps)` with m = (πDμ/4)·Re_eff**, the mass flow whose Re_D is Re_eff = max(Re_D, Re_lo) (decision 7, §3.2), and the case fluid's ρ and μ. It is never called with m = ρ\|Q\|: at Q = 0 fluids divides by Re_D = 0 (`ZeroDivisionError`). Liquids only, so ε = 1. | D8/D9: fluids is the one implementation. At Re_D ≥ 5000 it equals an independent transcription of ISO eq. (4) (WANDA's) to 4.4×10⁻¹⁶ (V, 2×10⁵ draws) and exactly on S1's grid. fluids says the expansibility is "1 for incompressible fluids". | P, V; R (m, §11 F7) |
| 7 | **Below ISO's lowest Reynolds number, C is held at its value there and flagged.** For corner and D and D/2 tappings Re_lo = max(5000, 16000β²); for flange tappings Re_lo = max(5000, 170000β²D), with D in m. C is never evaluated at Re_D < Re_lo, at Q = 0, or in fluids' code below Re 3700. | fluids' docstring lists ISO 5167-2:2003's and ASME MFC-3M's limits: 5000 "for 0.10 ≤ β ≤ 0.56", and 16000β² "for β ≥ 0.56", which jumps from 5000 to 5017.6 at β 0.56. A held C that jumps with β makes K(β) rise by 2.8×10⁻⁴ (relative) across β 0.56, so a bore inverse would not be unique and `orifice_check`'s mode 2 would have no exact root there (physics review). max(5000, 16000β²) is continuous. It differs from ISO's only for 0.559 < β ≤ 0.56, by up to 17.6 and on the stricter side, so the C held is still ISO's C at an Re inside ISO's range. With it, the held K strictly decreases in β over β 0.02–0.97 for every tap set and D 52.5 mm–1 m (R4). As written, eq. (4) gives C > 1 below about Re 100–300 and K → 0 near zero flow, a vanishing loss; at β 0.5 C is 59 at Re 1 (P, V). fluids adds two terms below Re 3700 that its comments mark "not in the ISO standard", with no citation (V). WANDA documents the hold: "The applicable Re-number is fixed to the minimum Re-number". A held C keeps h(Q) strictly increasing (P: no counterexample over D 10 mm–3 m, β 0.02–0.99, every tap set, Re 1–10⁹; V: d ln h/d ln Q ≥ 2.000011 over ISO's range; R: ≥ 2.0012 from β 0.75 up to decision 17's β limit) and makes the law exactly c·Q\|Q\| near zero flow. The extrapolation is flagged, as a pump curve's end slope is (D9). | P, V; R (continuous, §11 F4) |
| 8 | **The slope is exact; there is no lag:** dh/dQ = (2K\|Q\| + Q²·dK/dQ)/(2gA²). dK/dQ = dK/dC·dC_L/dRe·Re/\|Q\|, with dK/dC = −2K(1/C + β²/S), the same as −2u(1−β⁴)/(S C² β²), computed with the cancellation-free u of §1.1. dC_L/dRe is the analytic derivative of eq. (4)'s terms, for an entered C moved from corner or flange taps C_e times the derivative of the ratio (decision 13), and dK/dQ = 0 where C is held. | The precedent is `friction.colebrook`'s analytic df/dRe. The analytic and central-difference slopes agree to ≤ 7.3×10⁻⁷ relative, the difference's own error (P), and d ln K/dC = −2(1/C + β²/S) to 4.1×10⁻¹⁰ (R5). Over 18 networks, the GGA with the law emulated matches the closed form to ≤ 3.7×10⁻¹³ in 5–11 inner iterations (P). The slope jump at Re_lo (≤ 13.8 %) costs nothing: 6 iterations at the hold and at 10⁻⁸ and 10⁻³ either side of it (P). fluids' subtractive form of K loses every digit as β → 1 (physics review: K = 0, a zero-loss link, at some flows for 1 − β up to 1.2×10⁻⁵); the cancellation-free u equals it to 3.6×10⁻¹⁵ for β 0.02–0.97 and stays positive and strictly decreasing in β down to 1 − β = 10⁻¹² (R5). | P; R (cancellation-free, §11 F3) |
| 9 | **Zero flow takes the valve path.** h(0) = 0 and the slope is 0. The GGA floors the slope in its Jacobian only (non-pipe link), and the law stays exact. The initial flow is 1 ft/s × the inlet area (EPANET 2.2 `initlinkflow`). | Measured (P): equal heads converge in 10 iterations, a dead end to a plug in 4. | P |
| 10 | **Reverse flow** uses the symmetric law K(\|Q\|) on the inlet pipe's D, and raises `CORRELATION_OUT_OF_RANGE` (warning). The reading is signed as the flow. The vena contracta is then on the inlet side. | ISO's C is for flow onto the plate's upstream face, and a bevelled plate run backwards is another device (WANDA: "If the orifice plate is bevelled, the numerical result for negative flow rates are unreliable"). As D18 decision 6. | P, V |
| 11 | **ISO's geometric limits are flagged** wherever eq. (4) is used (ISO's C, or an entered C moved from corner or flange taps), one `CORRELATION_OUT_OF_RANGE` per inequality broken: d < 12.5 mm; D < 50 mm or D > 1000 mm; β < 0.1 or β > 0.75. They are not refused. fluids' "250 kPa" and "6 micrometers" roughness limits, the edge geometry and the straight lengths are not checked; the trace states that the plate and installation are assumed to meet ISO 5167-2. | GOALS §4.6. The limits come from fluids' docstring, citing ISO 5167-2:2003 and MFC-3M, and are corroborated by WANDA's warnings and ISO's abstract. The other two limits could not be traced to ISO (V). | P, V |
| 12 | **An outlet pipe whose bore differs from D is solved and flagged** (`CORRELATION_OUT_OF_RANGE`, warning, both ways of giving C), quoting both bores. | The loss relation assumes recovery within about 6D in the same bore (fluids: "recovered by 6 pipe diameters downstream"; WANDA; Reader-Harris et al. 2019's momentum balance at about 6D). No tolerance on the downstream bore was found in a source read, so any difference is flagged. | P |
| 13 | **An entered C is the C at the plate's taps** (at D and D/2 tappings for a plate without taps), held at every flow. The reading uses it as entered (C_M = C_e). The loss uses it moved to D and D/2 tappings: **C_L = C_e · r(Re_eff), r = C_ISO(D and D/2, Re_eff)/C_ISO(taps, Re_eff)** for corner or flange taps, both from fluids at the same Re_eff as ISO's C_L (decision 7), and C_L = C_e (r = 1) without taps or at D and D/2 taps, where K is constant and nothing depends on Re. Laminar flow (0 < Re_D < 2000 in the inlet pipe, `RE_LAMINAR_MAX`) is flagged, as for a valve's Cv (D9). ISO's geometric and Reynolds flags apply only where r is used (decision 11). | Decision 5 for an entered C. A calibration's C belongs to its taps, usually flange or corner, so using it for the loss as is would give one plate a loss that depends on where its taps were drilled, the very thing decision 5 rules out. A calibration that reproduced ISO's C at its own taps exactly would then move the flow by −2.53 % from ISO's default at β 0.75 (corner taps; −2.59 % with flange taps on 300 mm; R3, physics review). With the move it gives ISO's answer exactly (R3: every flow within 4.4×10⁻¹⁶ relative, and the reading too). r is the square root of ISO's ratio of the differential pressures at the two tap sets at one flow (eq. 1): the calibrated Δp at the taps is moved to D and D/2 by ISO's own prediction of the pressure difference between those positions, as Reader-Harris et al. 2019 compute the pressures between tap positions "using the Reader-Harris/Gallagher (1998) Equation". The additive form C_e + (C_ISO(D and D/2) − C_ISO(taps)), eq. (4)'s tap terms, was tried first and rejected: for a small C_e (10⁻³ at flange taps) it drives C_L towards 0, and h(Q) stops increasing (d ln h/d ln Q down to −76, R6). With the ratio, d ln r/d ln Re ≤ 0.076 and d ln h/d ln Q ≥ 1.78 over 9,118 plates with C_e from 10⁻⁶ to 1 below decision 17's β limit (R6). r lies in [0.9976, 1.0225] over ISO's range (R6). A user C is user data, and the square law holds in turbulent flow. The valves flag the same constant-K law in laminar flow in their inlet pipe (`results.py`). | P; S (the inlet pipe, §1.3 item 8); R (the move, §1.3 item 12, §11 F1) |
| 14 | **A meter's reading,** `differentialPressure` = (1−β⁴)/(C_M²β⁴)·ρv\|v\|/2, is ISO eq. (1) solved for Δp with ε = 1. C_M is ISO's C at the plate's own taps, held at their own Re_lo, or the entered C as entered. It is null without taps. It is reported beside `pressureLoss` = ρg·h and does not act on the network. | fluids' `differential_pressure_meter_solver` (flange, ε = 1) reads it back to the solved mass flow to 1.1×10⁻¹⁶ (S2, case C2). | P, V, W |
| 15 | **Flashing at the vena contracta raises `BELOW_VAPOR_PRESSURE` (invalid) on the component** (no port), when p_vc,abs < p_v, or p_vc,abs ≤ 0 Pa for a fluid with no vapor pressure (`results._below_vapor_pressure`). p_vc = p_up + ρg(z_up − z_down) − (1−β⁴)/(C_L²β⁴)·ρv²/2, with p_up the static pressure of the port the flow enters (D7) and the vena contracta at the elevation z_down of the port the flow leaves by. At zero flow (the reported flow is 0) there is no jet: p_vc is null and nothing is checked. It is not checked in a floating section. Incipient cavitation is not checked (Later). | GOALS §4.6: flashing is physically invalid, and a flashing liquid chokes the flow, so the flow solved is too high. ISO is single-phase only. Within the loss model this p_vc is exact: Bernoulli from the upstream section to the jet of area μA_d equals the flow-equation Δp at C_L to 6.4×10⁻¹⁵ (P). Ports carry their own elevations (`models/ports.py`), so p_vc needs one: WANDA computes P_vc = (H_vc − z₂)ρg for Q > 0 and (H_vc − z₁)ρg for Q ≤ 0, the downstream side's elevation, which this design follows; the cases have both ports at one elevation, where the term is 0. WANDA warns in the same case. The flag code already covers flashing (`flags.py`) and has a component-level form (a reservoir surface). | P, V; R (elevation and zero flow, §11 F6) |
| 16 | **D7 applies unchanged.** Each port's static pressure uses its own pipe's velocity. The static drop is ρgh + ρg(z_out − z_in) + ρ(v_out² − v_in²)/2, and the outlet port's pressure is the recovered one. | D7; D18 decision 4. The pipes carry their own friction, and the loss relation (momentum) holds no wall friction, so nothing is counted twice. S2's case C11 pins the identity. | P, V |
| 17 | **Topology issue `ORIFICE_OUT_OF_RANGE`** (422, listed after `EQUIPMENT_RATING_OUT_OF_RANGE`), raised for a plate the law cannot represent physically, one issue per plate naming the first rule it breaks: (a) β ≥ 1; (b) eq. (4), wherever it is used (ISO's C, or the move of decision 13), can exceed 1 at D and D/2 tappings or at the plate's taps; (c) an entered C moved from corner or flange taps can exceed 1, C_e·r_max > 1; (d) the coefficient K/(2gA²) at the smallest C_L is not a finite double, or computing it raises `ZeroDivisionError` or `OverflowError` (a tiny d or C). Each extreme over Re ∈ [Re_lo, ∞) is a closed-form bound: a C_ISO extreme takes each Re-dependent term of eq. (4) at whichever end of that range makes the bound safe (each term is monotone in Re). For (b) that is the largest C_ISO. For (c) it is r_max = 1 + max(ΔC(Re_lo), ΔC(∞), 0)/C_ISO,taps,min, with ΔC = C_ISO,DD2 − C_ISO,taps, which is eq. (4)'s tap terms alone and monotone in Re, so exact at the two ends. For (d) it is the smallest C_L: ISO's C at its smallest, or the entered C times r_min = 1 + min(ΔC(Re_lo), ΔC(∞), 0)/C_ISO,taps,min. The issue names the plate and quotes d, D, β and the C_L bound it breaks (D10). | `_unrepresentable_valves`/`_unrepresentable_equipment`'s pattern. (b) and (c): in the loss relation C ≤ 1 is exactly μ = C/√(1 − β⁴(1 − C²)) ≤ 1, a jet no larger than the bore; beyond it K drops below Borda–Carnot's sudden expansion from the bore, (1/β² − 1)², which is physically impossible. (As built, §12 item 40: that argument holds for the C at D and D/2 tappings, which sets the loss. Elsewhere eq. (4) serves only the reading (ISO's C_M at a meter's corner or flange taps) or the move (either coefficient of an entered C's ratio), and a C above 1 there is eq. (4) extrapolated far beyond ISO's range, whose largest C is below 0.7; the 422 text says which, with a remedy that works for that plate.) Extrapolated past β 0.75, eq. (4) at D and D/2 reaches 1 at β 0.9725 (Re_lo) and 0.9743 (Re 10⁸), and 2.2 at β 0.99 (physics review); the bound reaches 1 at β 0.97025 (D ≥ 71.12 mm; 0.97034 at D 52.5 mm), so it refuses only β 0.97025–0.9725 more than the exact maximum would, and it increases with β over 0.5–0.999 (R7). r_max holds over every Re and exceeds r's true maximum by at most 3.6×10⁻⁵ over ISO's range (9.7×10⁻³ up to the β limit), so at β 0.75 an entered C up to 0.9786 at corner taps and 0.9900 at flange taps is accepted (R8). A CORRELATION_OUT_OF_RANGE warning on β alone would not say the value is impossible, and D9 likewise refuses where no cited correlation gives a physical value. Below the limit, ISO's C strictly decreases with Re (R7), so the flow law is as in decision 7. (d): K decreases in C for β < 1 (decision 8), eq. (4)'s smallest bound stays above 0.58 for every β < 1 and D 52.5 mm–3 m (R7), and with the cancellation-free u, K > 0 whenever d < D (R5). So every flow's coefficient lies between finite positive bounds. The build adds a unit test of each bound. | P; S (the bound); R (C ≤ 1 and the name, §11 F2, F3) |
| 18 | **`OrificeResult`** in `SolvedState.orificeResults`, always present: `{}` with no orifice or when the solve did not converge (§2.2). | D18's `equipmentResults` rule (`OutputModel` sends every field). | P, W |
| 19 | **Its own Results view "Orifices", a trace for every orifice, and an "Orifices" methods section** only when the project has an orifice. | GOALS §4.2; D12/D18's rule keeps projects without the element unchanged. | P, W |
| 20 | **Scenario allow-list:** `boreDiameter` and `dischargeCoefficient` (a number, or null for ISO's). The taps are not listed. | A second plate is one bore change; a calibrated plate is one C. The taps are installation, the same in every case: with ISO's C they change no solved value, and with an entered C they say where that C was measured. | S, from P and W; R (the taps' role) |
| 21 | **Goal seek:** the variables are `boreDiameter` (log) and `dischargeCoefficient` (linear; the C at the plate's taps, as entered, decision 13). A case on ISO's C starts the C in the middle of the bounds, as a resistance on the Crane default does (D16). `_check_bounds` also builds the network at each bound of an orifice's bore or C variable, with the other values as the case holds them (the 2n cases D16 already validates), and reports decision 17's issue there as a bounds 400 (`VALIDATION_ERROR`). Like every `GoalSeekInputError`, the 400 is located by index and holds no id or submitted value: for example "body.variables.0.upper: the orifice's bore is not smaller than its inlet pipe's inner diameter", with the orifice in `componentIds`. The case's own 422 keeps the quoting (D10). There are four goals: `orifice_flow`, `orifice_pressure_loss`, `orifice_differential_pressure` (published with `needs: ['taps']` in `x-goal-quantities`) and `orifice_pressure_drop`. | D16: every numeric allow-list value is a variable, and goals are Compare's rows. D16's `_check_bounds` validates the model only; an orifice's bore also meets topology rules (β < 1, decision 17), so the builds turn a bound the solve would refuse into a clear 400. Without them, a bound above D would turn half the box into unusable trials, which the search would report as "not reachable". For a bore variable alone (on ISO's C, or on an entered C without a move) or a C variable alone, the issue's test is monotone in that value: β, the bound of decision 17 (b), which increases with β over 0.5–0.999 (R7), and K at the smallest C. So the two builds prove every trial builds. Otherwise, with a bore and a C varied together or a bore on an entered C moved from corner or flange taps (r_max is not shown monotone in β), a trial the builds did not cover can still be refused; it is then an unusable trial (D16), never a residual. A `needs` entry is how the published rules already say what a quantity requires (`vaporPressure`, `npshrCurve`); the web reads it through `goalNeedProblem` instead of copying a rule (D10). | P, W; S (the start); R (§11 F8, F12, F17) |
| 22 | **`METHOD_VERSION` 1.4.0**, with one changelog line: projects without orifices are unchanged in every value (§3.9). `schemaVersion` stays 1. | GOALS §4.3; 1.3.0 is deployed (D18's rule); an additive type (D14). | P, V |
| 23 | **EPANET mapping:** each orifice is a GPV with a 201-point HEADLOSS curve on [0, 2\|Q_ref\|], tabulated from the reference's own law. | EPANET cannot hold K(Re), and a TCV at the converged K proves only a fixed point. A GPV carries the Re dependence: on the low-Re line, holding C at Re 10⁸ moves Q by −9.2×10⁻³, while the GPV agrees to 1.5×10⁻⁵ (S3). | V over P (§1.3 item 4) |
| 24 | **No fuzz profile.** `orifice_check` runs over the corpus instead, in two exact modes (§7.4). | D18 decision 21's reasoning: the element is a two-port law with no control; the check needs no generator or EPANET model; GOALS §5 upkeep. | P, V |
| 25 | **Web entry:** one menu entry "Orifice plate (ISO 5167-2)"; the bore is the one required entry, on every create path (§6). | Q2. | P, W |

### 1.3 Where the designs disagreed

1. **Which C sets the permanent loss.**
   - P and W: the C of the plate's chosen taps, as ISO's loss relation is literally written with the meter's Δp and C. V: always D and D/2, with the taps setting only the reading.
   - This design takes V's (decision 5). Taken with each meter's own C, the relation gives one plate three losses, up to 5.8 % apart at β 0.75 (S1), and it would give a restriction orifice, which has no taps, an arbitrary answer.
   - The relation's theory (Reader-Harris et al. 2019, read) takes C between 1D upstream and a point between the plate and the vena contracta. D and D/2 is ISO's only tap set with L1 = 1, and it lies within 1.2 % in K of that theory's C_DandP at every β in ISO's range (S1). WANDA uses D and D/2 for its whole element.
   - For a meter user who reads ISO literally, the trace also shows the K that the meter's own C would give (§4.1).
   - The reviewers showed that this reading of the owner's "permanent pressure loss per ISO 5167-2" moves a high-β corner- or flange-tapped meter's flow beyond D6 (R1), so it is a named departure (§1.1) and owner question Q3, with this choice as the recommended default. The same rule now covers an entered C (item 12).
2. **Are the taps required?**
   - P and W: required, with no default, because the taps change the loss. V: the taps set only the reading.
   - With decision 5 the taps change no solved value on ISO's C, and with an entered C they only say where it was measured, so this design makes them optional (decision 2). Absent means a plate without pressure taps, a restriction orifice, which reports no reading.
   - A restriction orifice no longer needs a tap choice that no source can give it (P's Q2, W's Q1).
3. **How C is given.**
   - P and W: a union, `{kind: 'iso_5167_2', taps}` | `{kind: 'entered', coefficient}`, with no default.
   - Once the taps leave it (item 2), the ISO member holds nothing. ISO 5167-2 is a cited source of C, so GOALS §4.1 ("give each extra input a cited default") makes it the default.
   - This design uses an optional number, the valve resistance's precedent (D8/D9). That drops the union, its discriminator and error type, `_clean`'s union tag, the whole-and-part scenario rules, the web's generalized `kindUnionOf` and the pending-kind warning.
   - A goal seek of C on a case using ISO's C starts in the middle of the bounds, the existing rule for a resistance on its default (`AxisSpec.case = None`).
4. **EPANET mapping.**
   - P: a TCV at the converged K (+4.5×10⁻⁴). V: a GPV head-loss curve (+1.5×10⁻⁴).
   - This design takes the GPV (decision 23). A TCV proves only that our state is a fixed point. A GPV makes EPANET solve the Re-dependent law itself, and it tells a wrong Re dependence apart beyond D6 on a low-Re line (S3).
5. **Names.**
   - P: `boreDiameter`, `discharge`, `differentialPressure`. W: `bore`, `dischargeCoefficient`, `tapPressureDifference`.
   - This design uses `boreDiameter`: the web's diameter detection (`/D_\w|diameter/`) already matches it. It uses `dischargeCoefficient` for both the input and the result's C used (the input is now a number, item 3), and `differentialPressure`, ISO's own term for the reading.
6. **Goals.** P proposed three; W proposed four, with the static drop. This design has four, the same as Compare's rows, as for equipment (D18).
7. **Bounds of a bore variable.** P: check the topology at each bound. D16 today validates only the model. This design takes P's check (decision 21): it turns a bound at or above D into a clear 400, located by index like every goal-seek input error, and it proves every trial builds for a bore or a C variable alone (not for the two together, where a refused trial is an unusable trial).
8. **Laminar check for an entered C.** P: the lower Re of the two connected pipes, as for equipment. This design uses the inlet pipe's Re_D, the orifice's own Reynolds number and the valves' rule for a Cv (decision 13), so an orifice has one Re.
9. **Zero-flow valves in `orifice_check`'s ISO mode.** V: skipped, because K is undefined at zero flow. With the hold (decision 7), K at zero flow is K(C(Re_lo)), so they are included (§7.4).
10. **Flashing.** P and V: flag it. W: silent. This design flags it, as GOALS §4.6 requires (decision 15). It is not an owner question.
11. **A rating kind of Equipment, or its own type?** (Recorded after the product review.) For `{kind: 'orifice', bore, C?}` on D18's equipment: it would reuse D18's scenario, goal-seek, Compare, export and web plumbing; an entered-C orifice without a move is already a constant-c law once D is fixed (`orifice_check`'s mode 1 relies on that); and there would be one menu entry fewer. Against, and these decide it: ISO's C varies with Re, so the law is not equipment's `QuadraticLossLaw` with "c computed once"; β needs the inlet pipe's bore, while equipment deliberately needs no pipe (D18: "a Cv or Kv needs no pipe"); the reading, p_vc, β, Re and ISO's flags would add a set of nullable fields to `EquipmentResult`; and under D18's whole-and-part scenario rules a bore change on a point-rated base would be `not_applicable` or a whole-rating change. This design keeps its own type, "a two-port element like equipment" in the owner's words. A restriction orifice known only by a datasheet drop at a flow, a Cv or a Kv is Equipment, and both forms' hints say so (§6 W3).
12. **What an entered C means** (physics review). The synthesis used an entered C for the loss as entered, while it moved ISO's C to D and D/2 (decision 5), so a perfect calibration at corner taps gave a flow 2.53 % below ISO's default at β 0.75 (R3). The options were: (a) define the entered C as the C at D and D/2 tappings, which leaves the user to convert a calibration made at the meter's own taps; (b) take it as the C at the plate's taps and move it to D and D/2 for the loss; (c) ask the owner. This design takes (b) (decision 13): the user enters the calibration as certified, the reading is exact, and a calibration equal to ISO's C gives ISO's answer. The move is the ratio of ISO's C at the two tap sets, not their difference; the difference fails for small entered values (R6). Q3's option (b) restores the as-entered rule if the owner reads ISO literally.
13. **D and D/2 or L2′ = 0.125 for the loss's C** (physics review). Reader-Harris et al. 2019 take C_DandP at L1 = 1, L2′ = 0.125, which moves the flow by up to +0.56 % at β 0.75 on a line the plate dominates (R2; +0.63 % at most over ISO's whole range, §12 item 41). This design keeps D and D/2 (decision 5's reasons) and states the alternative and its size in the trace and methods.

---

## 2. Model and API

### 2.1 `Orifice` (`models/components.py`)

```python
OrificeTaps = Literal["corner", "flange", "d_and_d_2"]


class Orifice(BaseComponent):
    """A square-edged concentric orifice plate (SDD §4.15): a restriction orifice, or a flow meter
    with pressure taps. Its loss is ISO 5167-2's permanent pressure loss; it has no status."""

    PORT_IDS = ("inlet", "outlet")
    PORT_ROLES: ClassVar[dict[str, PortRole]] = {"inlet": "inlet", "outlet": "outlet"}

    type: Literal["orifice"]
    bore_diameter: float = Field(gt=0, le=10.0, description=...)
    discharge_coefficient: float | None = Field(default=None, gt=0, le=1.0, description=...)
    taps: OrificeTaps | None = Field(default=None, description=...)
```

The `Component` union gains `Annotated[Orifice, Tag("orifice")]`. `_component_tag` already returns `type` for a type that is neither a branch nor a valve.

| Field | Unit | Bounds | Description (the schema's text) |
|---|---|---|---|
| `boreDiameter` | m | (0, 10] | The diameter of the plate's hole, ISO 5167-2's d, at the flowing temperature. It must be smaller than the inlet pipe's inner diameter (a topology issue otherwise). |
| `dischargeCoefficient` | none | (0, 1] or absent | Absent: ISO 5167-2's Reader-Harris/Gallagher C at the solved flow (the default). A number: ISO 5167-2's discharge coefficient C of eq. (1), q_m = C/√(1 − β⁴)·ε·(π/4)d²·√(2Δpρ), with Δp between the plate's taps (between D and D/2 tappings for a plate without taps), from a calibration or datasheet, held at every flow. Not the flow coefficient α = C/√(1 − β⁴): convert it, C = α·√(1 − β⁴). The reading uses it as entered; the loss uses it moved to D and D/2 tappings by ISO 5167-2's ratio of the two tap sets' C. |
| `taps` | | `corner`, `flange`, `d_and_d_2` or absent | Where a meter's pressure taps are; the differential pressure is reported at them, and an entered C is the C at them. Absent: a plate without taps (a restriction orifice), with no reading. The plate's loss uses the C at D and D/2 tappings whatever its taps. |

- **No new `x-` extension.** Each value's only rule bounds it. β < 1 and C_L ≤ 1 depend on the pipe and the taps, so they are a topology issue (decision 17), not model rules.
- **Errors.** A value out of bounds, or an unknown tap set, is 400 `VALIDATION_ERROR` at its field, never echoing the value (D10). `ORIFICE_OUT_OF_RANGE` is 422, appended after the other issues (`_unrepresentable_orifices`, after `_unrepresentable_equipment`); it names the component and quotes d, D, β and the C bound it breaks.

### 2.2 `OrificeResult` (`models/results.py`)

| Field | Unit | Meaning |
|---|---|---|
| `flow` | m³/s | Positive from inlet to outlet. |
| `headLoss` | m | EGL(inlet) − EGL(outlet), from the solved heads. |
| `pressureLoss` | Pa (difference) | ρg × headLoss: ISO 5167-2's permanent pressure loss, the part not recovered downstream. |
| `pressureDrop` | Pa (difference) | Static p(inlet) − p(outlet), as `ValveResult.pressureDrop`. |
| `differentialPressure` | Pa (difference) or null | The reading between the plate's taps, signed as the flow; null without taps. |
| `venaContractaPressure` | Pa (gauge) or null | p_vc (decision 15), at the elevation of the port the flow leaves by; null at zero flow and where the pressure level is undetermined. |
| `beta` | none | d/D. |
| `pipeDiameter` | m | D, the inlet pipe's end segment. |
| `boreDiameter` | m | d used, after any scenario or goal-seek trial. |
| `reynoldsNumber` | none | Re_D at the solved flow, in the inlet pipe. |
| `dischargeCoefficient` | none | C_L, the C that sets the loss (at D and D/2 tappings). |
| `coefficientSource` | `iso_5167_2` or `entered` | Where C_L came from. |
| `coefficientReynoldsNumber` | none or null | The Re at which eq. (4) is evaluated for C_L (or for the move's ratio): Re_D, or Re_lo when held; null for an entered C without a move. |
| `tapCoefficientRatio` | none or null | r = C_ISO(D and D/2)/C_ISO(taps) at `coefficientReynoldsNumber`, the move of an entered C from corner or flange taps (decision 13); null otherwise. |
| `lossCoefficient` | none | K, on the inlet pipe's velocity. |
| `taps` | as the input | The taps the reading is at (null without). |
| `meterDischargeCoefficient` | none or null | C_M, the C in the reading: ISO's at the taps, or the entered C as entered; null without taps. |

- **Echoes.** The inputs that a scenario or trial can change (d, the source of C, and the entered C, which is C_M with taps and C_L without) are echoed, as D18 echoes the rating, so the export reads a case without applying its scenario.
- **A closed-off orifice** has no result. **One in a floating section** has its flow, head differences, reading, K and C, and a null `venaContractaPressure`.
- **Port results.** Each port has its `NodeResult` like any port.

### 2.3 Published rules

- `x-port-ids` and `x-port-roles` come from the class.
- `x-override-fields.Orifice` gains the two fields (§5.1); `x-goal-variables.Orifice` gains `{boreDiameter: log, dischargeCoefficient: linear}`; `x-goal-quantities` gains the four goals (§5.2), `orifice_differential_pressure` with `needs: ['taps']` (a new value of the existing `needs` list, not a new extension).
- `openapi.json` and `schema.d.ts` are regenerated, and the model-rules staleness test stays green.

---

## 3. Physics and solver

### 3.1 The law

- The loss and K are as in §1.1. K is a function of β and C only; v and A are those of the inlet pipe's bore D.
- **Monotone.** Over ISO's range (D 50–1000 mm, β 0.1–0.75, three tap sets, Re 5×10³–10⁸, 475,200 points), C strictly decreases with Re, and d ln h/d ln Q lies in [2.000011, about 2.1] (V). From β 0.75 to decision 17's limit (about 0.970), C still strictly decreases with Re and d ln h/d ln Q ≥ 2.0012 (R7). Beyond it, extrapolated eq. (4) rises with Re (β ≥ 0.98, physics review) and exceeds 1, and decision 17 refuses the plate. With the hold, h(Q) was strictly increasing everywhere P looked (D 10 mm–3 m, β 0.02–0.99). With the continuous Re_lo (decision 7), the held K also strictly decreases in β across 0.56 (R4), and K strictly decreases in β elsewhere (V), so a bore inverse is unique. An entered C moved from corner or flange taps keeps d ln h/d ln Q ≥ 1.78 (R6, decision 13).
- **What D6 can see.** On an ordinary line, holding C at a fixed Re moves Q by only 0.2–0.4 % (V), which is inside D6. The proof therefore needs cases at low Re, where a wrong Re dependence moves Q by 1.2–1.9 % (S2, C7), and checks that do not depend on D6 (§7.4).

### 3.2 C and the hold

- C_L = `C_Reader_Harris_Gallagher(D, d, ρ, μ, m, "D")` evaluated at Re_eff = max(Re_D, Re_lo(D and D/2, β)), that is with m = (πDμ/4)·Re_eff (fluids takes Re_D = 4m/(πDμ)). C_M is the same with the plate's taps and their own Re_lo.
- **Re_lo** = max(5000, 16000β²) for corner and D and D/2 tappings and max(5000, 170000β²D) for flange tappings (decision 7). ISO's written limit jumps from 5000 to 5017.6 at β 0.56; the max is continuous, and stricter only for 0.559 < β ≤ 0.56.
- **An entered C** (decision 13): C_M = C_e; C_L = C_e·r(Re_eff), with r = C_ISO(D and D/2, Re_eff)/C_ISO(taps, Re_eff), both from the same fluids call as above, for corner or flange taps, and r = 1 otherwise. In eq. (4) the two Cs differ only in the upstream-tap term (its (1 − 0.11A) factor varies with Re) and the downstream M2′ term, so r is a smooth function of Re with an analytic derivative from the same terms.
- Because Re_eff ≥ 5000 > 3700, fluids' two code-only terms (`max(…)`, active below Re 3700 and 3687.2, V) never act. What is used is exactly eq. (4).
- The D < 71.12 mm term: fluids' docstring prints 0.11(0.75 − β)(2.8 − D/0.0254), but its code and WANDA's transcription of ISO both use 0.011. Using 0.11 would move C by +3 % at D = 52.5 mm (V). The trace prints 0.011.
- **Measured effect of the hold** (V, P): on a viscous line at Re about 1000, eq. (4) as written and the hold give flows 4.0 % apart. Hollingshead's data at β 0.5 give C 0.670 at Re 1000 against 0.627 held. Hollingshead's data cover only β 0.5–0.7 and are Later.

### 3.3 Slope

Decision 8 gives the formula. `orifice.py` holds eq. (4) term by term (C∞ with the slope term, the upstream, downstream and small-D terms) for the trace and for dC/dRe, and K in the cancellation-free form of §1.1. A unit test pins the sum of its terms to fluids' C (P: 7.8×10⁻¹⁶), K to `discharge_coefficient_to_K` where that form does not cancel (R5: 3.6×10⁻¹⁵ for β 0.02–0.97), and dC/dRe, dr/dRe and dK/dC to central differences. Leaving dK/dQ out still converges (\|d ln K/d ln Q\| ≤ 0.275), with 0–2 more iterations, but it stops at about 2×10⁻¹² instead of 4×10⁻¹⁴ near the hold (P). So the slope is exact.

### 3.4 Zero and reverse flow

- **Zero flow:** decision 9. Re_D = 0 never reaches fluids, because C is held: fluids is called with m = (πDμ/4)·Re_eff ≥ (πDμ/4)·5000 (decision 6). Laws are evaluated at exactly Q = 0 on every solve: `gga.py:490` and `status.py:693` call `law.evaluate(0.0)` for every NORMAL link that is not a head offset, and an orifice takes that branch. `circulating_parts` reads h(0) = 0. There is no jet, so p_vc is null (decision 15).
- **Reverse flow:** decision 10. The flag is raised where the reported flow is below −q_zero (`results.py`'s zero-flow rounding). Message: "orifice '{id}': the flow runs from outlet to inlet; ISO 5167-2's coefficient is for flow onto the plate's upstream face, and the loss is taken as for forward flow at the same flow rate". Details: `{limit: 'reverseFlow', flow}`.

### 3.5 Validity flags

Each flag is `CORRELATION_OUT_OF_RANGE` (warning) on the component, one per inequality broken, with `details.limit` naming it and the numbers in SI, so that `flag-text.ts` can word it in display units:

| `limit` | When | Details |
|---|---|---|
| `boreDiameter` | eq. (4) used (ISO's C, or an entered C moved from corner or flange taps) and d < 0.0125 m | value, lower |
| `pipeDiameter` | eq. (4) used and D < 0.05 m or D > 1.0 m | value, lower or upper |
| `beta` | eq. (4) used and β < 0.1 or β > 0.75 | value, lower or upper |
| `reynoldsNumber` | eq. (4) used and 0 < Re_D < Re_lo of C_L (or of the move's ratio) or of ISO's C_M | value, lower (C_L's), meterLower (C_M's, with taps and ISO's C) |
| `outletDiameter` | the outlet pipe's end-segment bore ≠ D | value (outlet), inlet (D) |
| `laminar` | an entered C and 0 < Re_D < 2000 | value, upper |
| `reverseFlow` | flow < −q_zero | flow |

The messages say "bore diameter …" or "pipe diameter …", so the web's diameter detection converts them.

### 3.6 The reading and the vena contracta

- `differentialPressure`: decision 14. With D and D/2 taps C_M = C_L. With corner or flange taps C_M is up to 2.2 % below C_L at β 0.75, so the reading is up to 4.5 % higher (0.3–0.7 % at β 0.6; S7), which is why the reading is at the meter's own taps. With an entered C, C_M is that C, and C_L = C_M·r.
- `venaContractaPressure`: decision 15. It is computed from C_L whatever the taps, because it belongs to the loss model, and it is the same quantity WANDA reports, at the elevation WANDA uses: p_vc = p_up + ρg(z_up − z_down) − (1 − β⁴)/(C_L²β⁴)·ρv²/2, where "up" is the port the flow enters and "down" the port it leaves by (the inlet and outlet for Q > 0, the reverse for Q < 0). At zero flow it is null and not checked. The flag details are `venaContractaAbsolutePressure` and `vaporPressure` (or "not given"), the reservoir surface flag's form.

### 3.7 EGL and static pressures

D7 applies unchanged: p = ρg(EGL − z − v²/2g) at each port, with v in the connected pipe. With equal bores and elevations the static drop equals the loss. S2's case C11 pins the identity with a larger outlet pipe: static drop 75,558.76276 Pa = loss 77,639.78156 Pa − 2,081.0188 Pa of velocity heads, equal to the solver's to the digits shown.

### 3.8 Solver integration

| File | Change |
|---|---|
| `services/solver/orifice.py` (new) | `re_lo` (continuous); eq. (4)'s terms; `dc_dre`, the move's ratio `tap_ratio` and its derivative, `k_of_c` (the cancellation-free form), `dk_dc`; `OrificeLaw(d_pipe, d_bore, density, viscosity, entered, taps)` with `evaluate(q) → (h, dh/dq)`, `c_loss(q)`, `c_meter(q)`, `differential(q, c)`; `orifice_law(...)`; the bounds of decision 17; the citation strings. |
| `services/solver/network.py` | `LinkKind.ORIFICE`. Only `builder.py` and `gga.py` dispatch on `LinkKind`, and `gga.py` tests only `CONNECTION` and `PUMP`, so the link is floored like a valve. |
| `services/solver/builder.py` | `OrificeData(component, link_index, law, inlet, outlet, inlet_pipe, outlet_pipe)` and `BuiltNetwork.orifices`; `_unrepresentable_orifices` (the inlet pipe resolved as `_unrepresentable_valves` resolves it); an `elif isinstance(comp, Orifice)` branch adding the link inlet → outlet. |
| `services/solver/results.py`, `trace.py`, `methods.py`, `version.py` | §2.2, §3.4–§3.6, §4, §3.9. |
| Unchanged | `gga.py`, `status.py` (its `isinstance` tests are on `ValveLaw`, valve types and `HeadOffsetLaw`; an `OrificeLaw` is neither a valve nor a head offset, so it takes the `law.evaluate(0.0)` branch at `status.py:693` and `gga.py:490`, which decision 7's hold makes safe), `system_curve.py` (no control, so `flow_limit` treats the link as unlimited, and H_sys holds h(Q)), `npsh.py` (an orifice on a suction line lowers NPSHa through the EGL), `elements.py`, `branches.py`, `friction.py`. |

### 3.9 `METHOD_VERSION` and the bit-identity proof

- **Version.** 1.4.0. Changelog line: "Adds the orifice plate: ISO 5167-2's permanent pressure loss from the bore and the Reader-Harris/Gallagher discharge coefficient at D and D/2 tappings for every plate (held below ISO's lowest Reynolds number, flagged), or an entered coefficient at the plate's taps moved to D and D/2 tappings by ISO's ratio of the two tap sets' coefficients, with the differential pressure at a meter's taps and a flashing check at the vena contracta; a plate whose coefficient at D and D/2 tappings could exceed 1 is refused. Flows, heads, pressures, statuses, traces, messages and system curves of projects without orifices are unchanged (corpus comparison)." Every link last solved with 1.3.0 shows the method-change notice after its next solve, as D18 accepted.
- **Why projects without orifices are identical:** every new path sits behind `isinstance(comp, Orifice)` or a non-empty `built.orifices`; the new issue check finds nothing in them and its issues come last; the methods additions are conditional; `LinkKind` only gains a member; the goal-seek bounds build runs only for an orifice's bore or C variable; `needs: ['taps']` is checked only for the orifice goal that declares it.
- **Proof.** Dump the corpus (5,151 projects, with system curves) on `2014c6e` and on the branch, then run `compare A B --ignore-empty orificeResults --ignore methodVersion --ignore trace.methods.methodVersion`. Expect "identical 5,151, different 0", with the new reference cases missing in A. `--ignore-empty` exists since D18.
- **Also required on the branch's whole corpus (D13):** `scenario_check` 0 different; `goal_seek_check` 0 violations; `equipment_check` 0 different; `orifice_check` (§7.4) within D6; the three fuzz profiles give the same 9,000 records; `missing_result_check` stays at its baseline; the reference suite is green. The tools must learn the type first (§7.4).

### 3.10 Sources

| Source | What it supports | How verified |
|---|---|---|
| ISO 5167-2:2003 via fluids 1.3.1: `C_Reader_Harris_Gallagher` (eq. 4, the RHG 1998 equation, "5.3.2.1" per Reader-Harris 2019), `discharge_coefficient_to_K` and `dP_orifice` (the pressure-loss relation), `flow_meter_discharge` (eq. 1), `differential_pressure_meter_solver` | C, K, the reading, ISO's limits (docstring, also citing ASME MFC-3M-2004) | V read the source and reproduced all five docstring examples; an independent transcription equals fluids to 4.4×10⁻¹⁶. The standard itself (paywalled) was not read, so its clause numbers are quoted from secondary sources only. |
| Reader-Harris, *ISO 5167: Past and Present*, GFMW 2022 | RHG entered by the 1998 amendment; the 2022 revision of Part 2 lists no change to eq. (4) or its limits | V read it. ISO 5167-2:2003 is replaced by the 2022 edition, so the methods text cites "ISO 5167-2:2003 (as in fluids 1.3.1); not changed in eq. (4) by the 2022 edition". |
| Reader-Harris, Barnett, Mistry, FLOMEKO 2019, "Orifice plate pressure loss ratio …" | The loss relation's momentum theory (after Urner 1997, which was not read), C taken "using tappings 1D upstream" and at 0.125D downstream, the alternative decision 5 states; moving pressures between tap positions "using the Reader-Harris/Gallagher (1998) Equation" (decision 13's move); a water calibration parallel to RHG | V; S read §3.2 (decision 5); R re-read lines 197–220 of the saved text (decisions 5, 13). |
| Skelton et al., 28th NSFMW 2010 | A worked pressure-loss ratio: β 0.4, C 0.602 → 0.823 (fluids gives 0.82296) | V; a unit test. |
| Deltares WANDA, orifice component documentation | Precedent for the law H1 − H2 = ξQ\|Q\|/(2gA²), D and D/2 for the loss, the Re hold, the geometric and vena-contracta warnings, the vena contracta at the downstream side's elevation (P_vc = (H_vc − z₂)ρg for Q > 0), and symmetric reverse flow | V saved the source; S read the tap and warning lines; R read the vena-contracta lines (decision 15). |
| Hollingshead, MS thesis, Utah State 2011 (via fluids) | Low-Re C data, β 0.5–0.7: the hold's size; Later | V |
| `friction.RE_LAMINAR_MAX` = 2000 (EPANET 2.2) | The entered-C laminar flag, as for valves | In the code. |
| Not verified: the ISO text, its §5.4 clause number and uncertainty statement; Crane TP-410 2009's RHG pages; Urner 1997; Idelchik | None is cited as read. | |

---

## 4. Traceability

### 4.1 Trace (`trace._orifice_trace`, `element_type = "orifice"`)

- **Inputs:** d (`user`); C entered (`user`), with its definition (ISO eq. (1)'s C at the plate's taps, at D and D/2 without taps; not α = C/√(1 − β⁴)), or ISO 5167-2's (`default`); the taps (`user`, or "none" `default`); D with its pipe source (library or user); ρ and μ with their fluid sources; g; the ports' elevations.
- **Equations:**
  - β = d/D and Re_D = 4ρ|Q|/(πDμ);
  - eq. (4) as ISO writes it, with L1 and L2′ for D and D/2 and for the meter's taps, and the small-pipe term 0.011(0.75 − β)(2.8 − D/0.0254);
  - the hold, Re_eff = max(Re_D, Re_lo), with Re_lo's rule (continuous at β 0.56);
  - for an entered C at corner or flange taps, the move C_L = C_e·r, r = C_ISO(D and D/2, Re_eff)/C_ISO(taps, Re_eff);
  - K(C) in the cancellation-free form, h = K v|v|/(2g) and Δϖ = ρgh;
  - Δp = (1 − β⁴)/(C_M²β⁴)·ρv|v|/2;
  - p_vc = p_up + ρg(z_up − z_down) − (1 − β⁴)/(C_L²β⁴)·ρv²/2;
  - the static pressure at each port (D7) and the static-drop identity.
- **Intermediates:** β, 1 − β, A, v, Re_D, Re_lo (both, with taps), Re_eff, A_RHG = (19000β/Re)^0.8, each term of eq. (4), C_L, C_M, r (with a move), μ = C_L/√(1 − β⁴(1 − C_L²)) (≤ 1), K, h by the law and as solved, ρgh, Δp, the ratio Δϖ/Δp, p_in, p_out, p_vc (absolute), p_v, and the elevation and velocity-head terms.
- **Notes:**
  - The loss uses the C at D and D/2 tappings whatever the meter's taps, with the reason (decision 5) and the named departure from ISO's relation read with the meter's own C. With corner or flange taps, the K that ISO's relation would give with the meter's own C is shown, marked as not used.
  - The alternative tap position for that C, Reader-Harris et al. 2019's L1 = 1 and L2′ = 0.125: its C and K at this plate, marked as not used, with the measured size of the difference (K 0.06–1.2 % lower for β 0.1–0.75; up to +0.56 % in flow on a line the plate dominates; as built, the largest over ISO's whole range, 0.063–1.24 % and +0.63 %, §12 item 41).
  - ε = 1 (a liquid).
  - The plate and its installation are assumed to meet ISO 5167-2.
  - d and D are at flowing conditions.
  - The outlet pressure is the recovered one, about 6D downstream.
  - For an entered C: the reading uses it as entered; the loss uses it as entered without taps or at D and D/2 taps, and moved by r from corner or flange taps, so that one plate has one loss (decision 13).
  - The vena contracta is taken at the elevation of the port the flow leaves by (WANDA); none at zero flow.
  - Re_lo is ISO's limit made continuous at β 0.56 (decision 7), when 0.559 < β ≤ 0.56.
  - Each flag's inequality.
  - In a scenario, D15's "Changed by this scenario" note; in a goal seek, D16's.
- **Correlations and data:** "ISO 5167-2:2003 Reader-Harris/Gallagher equation (fluids.flow_meter.C_Reader_Harris_Gallagher)"; "ISO 5167-2 pressure-loss relation (fluids.flow_meter.discharge_coefficient_to_K)"; "ISO 5167-2 eq. (1), ε = 1".

### 4.2 Methods summary

- **A section "Orifices"** comes after "Equipment", only when the project has an orifice. It states:
  - the law and the loss relation;
  - C from eq. (4) at D and D/2 tappings for every plate, and why, with the named departures of §1.1 (ISO's relation read with the meter's own C; Reader-Harris et al.'s L2′ = 0.125; the continuous Re_lo), each with its measured size;
  - the hold below Re_lo (flagged, WANDA's practice);
  - the refusal where C at D and D/2 could exceed 1 (decision 17);
  - the reading at the meter's taps;
  - the vena-contracta flashing check;
  - ISO's limits, the outlet bore and reverse flow, each flagged;
  - the zero-flow Jacobian floor;
  - ε = 1;
  - only when one is entered: the entered C's definition, its move from corner or flange taps, and its laminar flag.

  References: ISO 5167-2:2003 via fluids, Reader-Harris et al. 2019, WANDA, and `RENNELS` if Borda–Carnot is named.
- **One assumption**, under the same condition: "Orifice plates meet ISO 5167-2 in geometry and installation; their loss is ISO 5167-2's permanent pressure loss with the discharge coefficient at D and D/2 tappings (or an entered one), for a single-phase liquid."

### 4.3 Flags and issue text

- No new flag code (§3.5, decision 15).
- `flag-text.ts` gains an orifice branch keyed on `details.limit`, and a vena-contracta branch keyed on `details.venaContractaAbsolutePressure`, each worded in display units. Without details, it falls back to the message.
- `issue-text.ts` gains `ORIFICE_OUT_OF_RANGE`, for example: "Orifice O1's bore (110 mm) is not smaller than its inlet pipe's bore (102.3 mm)." or "Orifice O1's bore (99.5 mm) is so close to its inlet pipe's bore (102.3 mm) that ISO 5167-2's discharge coefficient could exceed 1; enter a C, or use a smaller bore." (As built, §12 item 40: entering a C is offered only to a plate without taps or with D and D/2 taps, where it is used as entered; at corner or flange taps it would be moved by eq. (4) and refused the same way, and a refusal at a meter's own taps names the reading or the move it would rest on.)

---

## 5. Scenarios, goal seek, Compare and export

### 5.1 Scenarios (D15)

- **Allow-list.** `COMPONENT_FIELDS[Orifice]` holds:
  - `boreDiameter`: "m", label "bore diameter";
  - `dischargeCoefficient`: "", label "discharge coefficient".
- **Values.** A null `dischargeCoefficient` sets ISO's C. `value_text` writes it as "ISO 5167-2's (the default)" rather than the generic "none (the default)". `COMPONENT_NAMES[Orifice]` is "orifice".
- **Use cases:** a second plate (another bore), a calibrated plate (C entered), ISO's C against a vendor's C.
- **PRD §3.8's list** gains both fields. An orifice field on another type of component is `not_applicable`, as D15 defines.

### 5.2 Goal seek (D16)

- **Variables.** `_variable` derives both fields from the allow-list unchanged. `LOG_FIELDS` gains `boreDiameter`. When the case holds no C (ISO's), the start is the middle of the bounds (`AxisSpec.case = None`), and the "held" text names ISO's C, as `_default_text` names the Crane default. This is a small branch in `_resolve_variable`, which today reads a plain number with `float(raw)` and lets only a resistance be absent. `test_goal_seek_models.py`'s `EXPECTED` gains the Orifice row.
- **Bounds.** `_check_bounds` gains decision 21's build at each bound of an orifice's `boreDiameter` or `dischargeCoefficient` variable. Its issues are `GoalSeekInputError`s like the model check's: located by index, the orifice in `componentIds`, and no id, bore, D, β or C in the text (D10, SDD §5.1.2). For example: "body.variables.0.upper: the orifice's bore is not smaller than its inlet pipe's inner diameter", or "…: ISO 5167-2's discharge coefficient at this bore could exceed 1". The builder's 422 text, which quotes the values, is not reused. D stays fixed during a goal seek: a pipe's `spec` is not a variable (D16), and its `length` does not change its bore.
- **Goals.** The `ElementKind` "orifice" has targets `(Orifice,)`:

| Goal | Unit, category | Reads | Label |
|---|---|---|---|
| `orifice_flow` | m³/s, flow | `flow` | flow through {element} |
| `orifice_pressure_loss` | Pa (difference), pressure | `pressureLoss` | permanent pressure loss across {element} |
| `orifice_differential_pressure` | Pa (difference), pressure | `differentialPressure` | differential pressure at the taps of {element} |
| `orifice_pressure_drop` | Pa (difference), pressure | `pressureDrop` | static pressure drop across {element} |

  `orifice_differential_pressure` is published with `needs: ['taps']` (`QuantitySpec(..., needs=('taps',))`, the field that already carries `vaporPressure` and `npshrCurve`). On a plate without taps the API's need check gives 400 `GOAL_NOT_APPLICABLE` ("…: the orifice has no pressure taps; set its taps to read a differential pressure"), and the web's `NEED_CHECKS` gains a `taps` entry, so `goalNeedProblem` reads the rule from `openapi.json` instead of copying it (D10). The taps cannot be overridden, so the case's taps are the base's.
- **Uses:** sizing a restriction orifice (the bore for a bypass flow), sizing a meter (the bore for a reading at a design flow), the C a calibration must show.

### 5.3 Compare (web)

- **Element kind `orifice`.** Its quantities are `orificeFlow` (relative), `orificePressureLoss` (relative, true zero), `orificeDifferentialPressure` (relative, true zero) and `orificePressureDrop` (no relative).
- **Default rows.** `defaultRows` adds an orifice's flow and loss when a scenario changes it. `CompareRowsDialog` gains the group "Orifice plates".
- **One mapping.** `TraceView` and `CompareRowsDialog` each repeat a type → kind ladder; it moves into one `compareElementKind(component)` in `compare.ts`, rather than being copied a third time (W).

### 5.4 Export (D17, web)

- **A new sheet** `orifices` ("Orifice plates", `orifices.csv`), after Equipment. Its columns:
  - the case columns, Solved at and Results;
  - Orifice id, Orifice;
  - Flow (+ inlet → outlet);
  - Permanent pressure loss, Differential pressure (taps), Pressure drop, static, Head loss;
  - Vena contracta pressure;
  - β, Reynolds number (inlet pipe), Discharge coefficient (C_L), C from ("ISO 5167-2", "ISO 5167-2 (held)", "Entered" or "Entered, moved to D and D/2"), C evaluated at Re (`coefficientReynoldsNumber`, a number), Tap ratio r (`tapCoefficientRatio`, a number);
  - Taps;
  - Meter C;
  - Loss coefficient K;
  - Bore and Pipe bore D (the echoed inputs, the sheet's named departure from the screen, as D18's rated columns);
  - Flags.
- **About lines**, only in a file with the sheet: the orifice sign row (the loss, reading and head loss signed as the flow; the static drop holds the elevation and velocity terms), and the "≈ 0" clause extended to orifice pressure differences.
- **Scenario changes sheet.** `changeCategory` maps `boreDiameter` to `diameter`; `dischargeCoefficient` is dimensionless, with null written "ISO 5167-2 (default)".

---

## 6. Web

These are the designers' web defaults, reversible under D14.

- **W1. Menu.** One entry, "Orifice plate (ISO 5167-2)", in a new group "Orifice plates: restriction orifices, flow meters", after Equipment (`kinds.ts`). Kind `orifice`, default name "Orifice O1", id prefix `O` (free: R N PL AF T Y P V E L C are taken).
- **W2. Entry.** `ENTRY_KINDS` and `INLINE_KINDS` gain `orifice`. Every create path asks for the bore first: the first component, Add after, Add before or Insert, and the Piping view's Add here. "Insert into the bypass line" is the commonest placement of a restriction orifice. `missingEntries` returns "Enter the orifice bore: it has no default." `EnteredValues` gains `boreDiameter`. An error clears on input, never on blur (D18's layout rule).
- **W3. Form** `forms/OrificeForm.svelte`, sharing `OrificeFields.svelte` with the Add dialog. In order:
  - **Elevation.**
  - **Bore diameter** (category `diameter`; accessible name "Bore diameter (mm)"). Hint: "The diameter of the plate's hole (ISO 5167-2's d) at the flowing temperature; smaller than the inlet pipe's bore."
  - **The β line**, a read-only `<output>`, also in the bore's `aria-describedby`: "β = d ÷ D = 0.4890, with D = 102.3 mm, the bore of the inlet pipe (NPS 4, Sch 40)". D is resolved from the inlet port's pipe segment through `resolvedPipe` (`utils/orifice.ts`, with `PortsEditor`'s `pipeAt` moved to a utility). It has three other states: "β is shown once the inlet is connected.", "β is shown once the pipe library loads." and, in amber, "β ≥ 1: the bore is not smaller than the inlet pipe's (102.3 mm); the solve refuses it."
  - **Discharge coefficient**, `ResistanceField`'s pattern: "ISO 5167-2 (Reader-Harris/Gallagher), the default" or "Entered C", which shows a number field "Entered C" with `schemaBounds`. A kind picked with no value yet keeps the stored one, with a warning. The entered C's hint, also in its `aria-describedby`, defines it: "ISO 5167-2's discharge coefficient C at this plate's taps (at D and D/2 tappings for a plate without taps): q = C ÷ √(1 − β⁴) × (π/4)d² × √(2Δp/ρ). A datasheet's flow coefficient α = C ÷ √(1 − β⁴) is not C: enter α × √(1 − β⁴). The plate's loss uses this C moved to D and D/2 tappings."
  - **Pressure taps:** "None (a restriction orifice)" (the default), "Corner", "Flange", "D and D/2". Hint: "Where a flow meter's pressure taps are; the differential pressure is reported at them, and an entered C is the C at them. The plate's loss uses the C at D and D/2 tappings whatever the taps."
  - **Form hint:** "An orifice plate: a restriction orifice (a minimum-flow bypass, balancing) or an orifice flow meter. Its loss in the network is ISO 5167-2's permanent pressure loss, the part of the pressure difference across the plate not recovered downstream, with the discharge coefficient at D and D/2 tappings. A meter's differential pressure is reported at its taps. Flow from outlet to inlet, flashing at the vena contracta, and a plate or flow outside ISO 5167-2's validated range are flagged. For a restriction orifice given by a pressure drop at a flow, a Cv or a Kv, use Equipment."
  - **Equipment's hint** (`EquipmentForm.svelte`) gains the restriction orifice, so the most common restriction-orifice datasheet, a drop at a design flow, has a visible path: "A heat exchanger, coil, strainer, filter, restriction orifice or other element given by its datasheet: …". The menu group's label is unchanged.
  - There are no pre-solve ISO-range warnings: the limits are the API's, and copying them would break D10's "read, never copy". After a solve the result strip shows the flags.
  - One column on phones, two from 640 px.
- **W4. Results view "Orifices"**, in tab order after Equipment and before Branches, only when `orificeResults` has entries (an older response without the map is read as `{}`). Caption "Results per orifice plate"; first column "Orifice plate". `orificeTable`, built as `equipmentTable` is, has these columns:
  - Flow;
  - Permanent loss (`f.diff`, ρg·HEAD_NOISE);
  - Differential pressure (taps), "—" without taps;
  - β;
  - C;
  - C from;
  - Re (inlet pipe);
  - Vena contracta pressure (g);
  - Pressure drop (static);
  - Head loss.

  That is ten data columns, as Valves has, with a sticky first column, sideways scrolling on phones, and sorting and Flagged only as on every table.

  Note under the table: "Permanent loss is ISO 5167-2's pressure loss: what the plate takes from the line once the jet has recovered downstream, ρg × head loss; it sets the flow, with the discharge coefficient at D and D/2 tappings. Differential pressure is what a flow meter reads between its taps; it is larger than the permanent loss and does not act on the network. Pressure drop is the static difference, inlet minus outlet, as for valves. Flow, the losses and the differential pressure are negative when the flow runs from outlet to inlet."
- **W5. Strip.** `SUMMARY_COLUMNS['Orifice plate']` = flow, pressureLoss, differentialPressure; `elementSummary` leaves out a "—" cell.
- **W6. Compare, goal seek and scenarios.**
  - Compare: §5.3.
  - Goal seek:
    - The group "Orifice plates" holds "Bore diameter" (`diameter`) and "Discharge coefficient" (dimensionless).
    - Default bounds for the bore are [0.1D, 0.75D] (ISO's β range), widened to include the case's bore and clipped to the field. D comes from the last converged solve's `pipeDiameter` (a new `DefaultBoundsContext.pipeDiameter`, read as `kOpen` is) or the form's resolver. The resolver finds no D only when the inlet is not connected, where the goal seek cannot run (the case has `UNCONNECTED_PORT`), or before the pipe library loads. With no D the bounds are [d/2, d]: the upper bound is the case's bore, which a valid plate keeps below D, so the default is never a bounds 400; the user can raise it. On the e2e pipe the bounds are [10.23, 76.70] mm.
    - Default bounds for C are [v/2, min(2v, 1)], where v is the case's entered C or the last solve's C at the plate's taps (`meterDischargeCoefficient` with taps, `dischargeCoefficient` without); with neither they are [0.5, 1]. With corner or flange taps the upper bound is also at most 0.99/r̂, with r̂ the last solve's `tapCoefficientRatio` (on ISO's C, its C_L/C_M). That keeps the default box inside decision 17 (c): over ISO's range r's bound exceeds r by at most 3.6×10⁻⁵, and r changes by at most 0.66 % with Re at one plate (R8).
    - The goals' hints are: "Positive from inlet to outlet."; "ISO 5167-2's permanent loss, ρg × head loss."; "Between the plate's taps: what a flow meter reads."; "Static pressure, inlet minus outlet."
    - The trace's "Use in goal seek" and "Add to comparison" gain the orifice.
  - Scenarios: `fieldLabelFor` and `changeValueText` cover both fields: the bore in the diameter unit, and C as a number or "ISO 5167-2 (default)". A bore or C edit in a scenario is one change, marked Changed with the base value and Reset.
- **W7. Text.** `flag-text.ts` and `issue-text.ts` as in §4.3. In `siText`, "diameter" is already matched.
- **W8. Unchanged:** the navigator's walk (a two-port pass-through oriented by `x-port-roles`), `encoding`, `migrations`, `DeleteDialog`, `system-curve-text`, `MethodsSummary` and the generic trace view.
- **W9. Phones and desktop** (GOALS §4.7): the Add dialog is a sheet; the β line wraps under the bore; the table scrolls with a sticky first column; the extra view pill appears only with orifices.

---

## 7. Verification

### 7.1 Closed-form reference cases (`tests/reference/derivations_orifice.py`)

- **Method.** A new derivations file, imported only from `opensolve_pipe.models` and `tests.reference`, never `services`.
  - `element_laws` gains its own transcription of eq. (4) (`orifice_c`), K(C), `orifice_head`, `orifice_differential` and `re_lo`; `test_derivation_checks` pins `orifice_c` to fluids' C.
  - `case_format` gains an `orifice(...)` builder, and `Expected` gains an `orifice` block: flow, headLoss, pressureLoss, pressureDrop, differentialPressure, venaContractaPressure, dischargeCoefficient and lossCoefficient.
  - `network_check` evaluates the law, so its fsolve self-check covers every case.
- **Shared inputs.** "Liquid A" is the suite's 998 kg/m³ at 1 mPa·s. Pipes have ε = 4.5×10⁻⁵ m and use Colebrook unless stated.
- **Measured by the synthesizer** under this design's law (`synth/cases.py`). Each case was also solved by the real solver with the orifice as a gate valve of K = K(Q*) on the inlet bore: every flow agrees to ≤ 2.2×10⁻¹⁶, the fixed point, which confirms the pipes, tees, pump and heads.

| Case | Network (test inputs) | Derivation | Expected (measured) |
|---|---|---|---|
| C1 `orifice_line` | R1 z 10 m, level 2 m → 102.3 mm × 60 m → OR1 (z 3 m, d 51.15 mm, β 0.5, **flange taps**) → 102.3 mm × 40 m → R2 z 0, level 1 m; liquid A | brentq on H₁ − H₂ = Σh_pipes(Q) + h_or(Q) | Q 0.01742501098029; Re_D 216,440.28; C_L 0.6047534222; K 30.05055523; h 6.885978346 m; loss 67,393.32279 Pa; C_M 0.6047651385; Δp 91,977.61225 Pa; EGL 9.531587007 / 2.645608662 m; p 61,682.21694 / −5,711.105846 Pa(g); p_vc −30,298.95924 Pa(g). With no taps, corner taps or D and D/2 taps the flow is the same bit for bit; only Δp changes (91,778.82 and 91,981.18 Pa). |
| C2 `orifice_meter_readback` | C1 with R1 z 5 m, level 1.286445470686 m, so Q* = 0.012 | Explicit | C_L 0.605371841; K 29.9797294; h 3.25804615 m; loss 31,886.61724 Pa; C_M 0.6053866614; Δp 43,531.76776 Pa. fluids' `differential_pressure_meter_solver` (flange, ε = 1) reads m = 11.976 kg/s = ρQ* (−1.1×10⁻¹⁶). |
| C3 `orifice_entered_c` | C1 without taps (a restriction orifice), with an entered C = 0.6, so C_L = 0.6 | brentq | Q 0.01732389858578; K 30.60272137; h 6.931358229 m; loss 67,837.45736 Pa; no reading; no flags (R: `reviser/cases2.out.txt`) |
| C4 `orifice_reverse_flow` | C1 with the heads swapped | Mirror | Q −0.01742501098029; EGL in/out 3.468412993 / 10.35439134 m; Δp −91,977.61225 Pa; p_vc (inlet side) −22,246.14305 Pa(g); reverse-flow flag |
| C5 `orifice_outside_iso_geometry` | R1 z 0, level 30 m → 40.9 mm × 20 m → OR (z 0, d 10 mm, β 0.2445, corner taps) → 40.9 mm × 10 m → R2 z 0, level 0 | brentq | Q 0.00118312543162; Re 36,757.68; C_L 0.6056492608 (the small-D term adds 0.0066156975); K 706.9666603; h 29.23054057 m; C_M 0.60662552; Δp 306,609.9411 Pa; flags d < 12.5 mm and D < 50 mm |
| C6 `orifice_low_reynolds` | C1's pipes, OR1 β 0.5, flange; oil 900 kg/m³, 0.06 Pa·s; R1 z 1, level 2 m → R2 z 0, level 1 m | brentq with C held at Re 5000 | Q 0.005451562364008; Re 1,017.76; C_L 0.6264073608 (held); K 27.7012504; h 0.6213100427 m; C_M 0.6265920474 (held); Δp 7,562.992808 Pa; Reynolds flag |
| C7 `orifice_reynolds_dependence` | 102.3 mm × 30 m and × 20 m; OR β 0.65, flange; light oil 870 kg/m³, 0.012 Pa·s; R1 z 1, level 3 m → R2 z 0, level 1 m | brentq | Q 0.01373313452249; Re 12,392.02 (Re_lo 6,760 for C_L and 7,347.7 for C_M: inside); C_L 0.6320436773; K 6.443357054; h 0.917103979 m; C_M 0.6304237957; Δp 14,061.50967 Pa. C held at Re 10⁵, 10⁶ or 10⁸ moves Q by −1.216, −1.650 or −1.907 %, beyond D6. |
| C8 `orifice_balancing_loop` | R1 z 15 m, level 5 m → 154.1 mm × 100 m → ideal tee T1 (z 5); leg A 77.9 mm × 40 m → ORA (β 0.45) → 77.9 mm × 40 m; leg B 77.9 mm × 60 m → ORB (β 0.6) → 77.9 mm × 60 m; ideal tee T2 (z 4) → 154.1 mm × 80 m → R2 z 0, level 2 m; no taps | Nested brentq | Q 0.02353786228879; Q_A 0.01017566844332; Q_B 0.01336219384547; EGL T1 19.0653575, T2 2.747714002 m; ORA C 0.60298948, K 50.15587064; ORB C 0.60954761, K 11.34066465; loop closure 7.1×10⁻¹⁵ |
| C9 `orifice_min_flow_bypass` | R1 (z 0, level 2 m, two ports) → 154.1 mm × 8 m → PU1 (z 0.5, `curve_a`) → 102.3 mm × 5 m → ideal tee T1 (z 1) → 102.3 mm × 50 m → R2 z 18, level 2 m; T1 branch → 52.5 mm × 10 m → RO (z 1, d 15 mm, no taps) → 52.5 mm × 5 m → R1 port_2 | brentq on T1's EGL | EGL T1 28.61046775 m; pump 0.03920447916487, process 0.03666103258417, bypass 0.002543446580695 m³/s; RO β 0.28571429, Re 61,561, C 0.602918139, K 371.5146249, h 26.1489051 m |
| C10 `orifice_vena_contracta_flashing` | Built-in water at 20 °C (998.2071505 kg/m³, 1.0015961 mPa·s, p_v 2,339.3182 Pa); R1 z 0, level 2 m, surface 1.8 MPa g → 52.5 mm × 5 m → RO (z 0, β 0.25, no taps) → 52.5 mm × 5 m → R2 z 0, level 1 m | brentq | Q 0.005086337361782; C 0.6019006438; K 652.7682753; h 183.7391557 m; loss 1,798,635.117 Pa; ports at 1,912,570.8 and 113,935.6 Pa abs, far above p_v; p_vc −26,861.40 Pa abs < p_v, so `BELOW_VAPOR_PRESSURE` |
| C11 `orifice_outlet_bore_differs` | C1 with a 154.1 mm × 40 m outlet pipe | brentq; D7 | Q 0.01869908683627; loss 77,639.78156 Pa; static drop 75,558.76276 Pa = loss − 2,081.018799 Pa (velocity heads); outlet-bore flag |
| C12 `orifice_entered_c_at_taps` | R1 z 0, level 1 m → 102.3 mm × 1 m → OR (z 0, d 76.7 mm, β 0.7497556, **corner taps**, entered C = 0.6) → 102.3 mm × 1 m → R2 z 0, level 0; liquid A | brentq; decision 13's move | Q 0.02131227740861; Re_D 264,724.96; r 1.021059944023; C_L 0.6126359664; K 2.564521099; h 0.8790893699 m; loss 8,603.679926 Pa; C_M 0.6; Δp 20,172.34651 Pa; EGL 0.939544685 / 0.06045531504 m; p_vc −13,508.32504 Pa(g); no flags. Using 0.6 for the loss as entered would give Q −2.519 %, beyond D6. On ISO's C the same network gives Q 0.02134831923356, C_L 0.6134828942, C_M 0.6008290351755132 (R: `reviser/cases4.out.txt`). |

**System curve** (`test_system_curves.py`): pump → orifice → reservoir gives H_sys(Q) = Δz + Σh_pipes(Q) + h_or(Q) at every point, explicitly, with C(Re) varying along the curve.

### 7.2 EPANET cases (`generate_epanet_cases.py`, `epanet_model.py`)

- **Mapping.** Decision 23, written with WNTR (`add_curve(name, 'HEADLOSS', pts)`, then `add_valve(..., 'GPV', initial_setting=name)`). `network_check.EPANET_MODEL` evaluates the same curve piecewise-linearly (`np.interp`), so its self-check stays exact. One sentence is added to `source_text`.
- **Measured** (`synth/epanet.out.txt`; WNTR 1.5.0, EPANET 2.2, "EPANET water", Swamee–Jain in the 5.74 form). Each row passes D6. The remainder is the pipes' g = 32.2 ft/s² bias, as in every EPANET case (V: a TCV adds EPANET's minor-loss constant, +4.5×10⁻⁴).

| Case | Reference | GPV, ΔQ relative | Holding C at Re 10⁸ would move Q |
|---|---|---|---|
| E1 `epanet_orifice_line` (C1's network) | Q 0.01740061988423, C 0.604785304, K 30.046898243 | +1.534×10⁻⁴ (reverse +1.534×10⁻⁴) | −3.9×10⁻³ |
| E2 `epanet_orifice_balancing` (C8's) | Q_A 0.01016327504258, Q_B 0.01332101666158 | Q_A +1.352×10⁻⁴, Q_B +3.181×10⁻⁴ | (V: C at Re 10⁶ moves Q_A −2.0×10⁻³) |
| E3 `epanet_orifice_low_re` (52.5 mm, β 0.3, 10 m + 10 m, H 1.2 → 0) | Q 5.966495101066×10⁻⁴, Re 14,159.5, C 0.606438105, K 298.423787919 | +1.478×10⁻⁵ (reverse the same) | −9.2×10⁻³, beyond D6: EPANET tells the Re dependence apart here |

### 7.3 Goal seek and scenario references

- **`test_goal_seek.py`** (by a tester who has not read `services/`), with the derivations, `MET_CASES`, `LABELS` and `DIMENSION` in `derivations_goal_seek.py`: closed-form inverses, at the default and at the smallest tolerance, numbered after D18's G25–G32 (`synth/gs.out.txt`, `reviser/cases2.out.txt`, `reviser/cases4.out.txt`). Each of the four goal quantities and both variable fields has a case, as `test_every_variable_field_and_goal_quantity_has_a_case` requires:
  - **G33**, variable `boreDiameter`, goal `orifice_flow` = 0.015 m³/s on C1: h* = 7.90629233124 m, K* = 46.5611093191, d* = 46.7639723052 mm (β 0.457125828985). The forward solve gives 0.015.
  - **G34**, variable `dischargeCoefficient`, the same goal on C3 (no taps, so C_L = C): C* = `K_to_discharge_coefficient`(D, d, K*) = 0.499134545651.
  - **G35**, meter sizing. The network is R1 z 20 m, level 10 m → 102.3 mm × 20 m → OR (z 0, flange taps) → 102.3 mm × 20 m → an assigned demand of 12 L/s (D12). The variable is `boreDiameter` and the goal `orifice_differential_pressure` = 50 kPa. Result: d* = 49.5345909038 mm (β 0.4842090997). fluids' `differential_pressure_meter_solver` gives 49.5345907179 mm (−3.8×10⁻⁹, its own tolerance), and the loss there is 37,401.93 Pa.
  - **G36**, restriction-orifice sizing on C9: bypass 3.0 L/s. Result: EGL T1 28.4660973619 m, h_RO* 25.83728685 m, K* 263.8590807, d* = 16.2563444213 mm (β 0.3096446556).
  - **G37**, `dischargeCoefficient` on C12's network on ISO's C (corner taps), goal `orifice_flow` = 0.018 m³/s: the start is the middle of the bounds, and the C found is the C at the corner taps. h* = 0.912464598857 m, K* = 3.73167645722, C_L* = 0.533852485837, r = 1.020983626357 at Re 223,582.36, so C* = C_L*/r = 0.522880555629. This pins the move in a goal seek: C_L* itself would be 2.1 % off.
  - **G38**, variable R1's `liquidLevel`, goal `orifice_pressure_loss` = 60 kPa on C1: h* = 6.13055839466 m, Q* = 0.01644422884743 (brentq on the orifice law alone), level* = 0.814811461525 m. The forward solve gives a loss of 60,000 Pa.
  - **G39**, variable R1's `liquidLevel`, goal `orifice_pressure_drop` = 70 kPa on C11 (the unequal-bore outlet, so the static drop differs from the loss): Q* = 0.01800008371611 from ρg·h(Q) + ρ(v_out² − v_in²)/2 = 70 kPa, level* = 1.20165988673 m; the loss there is 71,928.34287 Pa and the velocity term −1,928.34287 Pa. A swapped static-drop and loss would miss by 2.8 %.
  - **Not applicable:** `orifice_differential_pressure` on a plate without taps is 400 `GOAL_NOT_APPLICABLE` (its `needs: ['taps']`). A bore bound at or above D is a bounds 400 located by index, with the orifice in `componentIds` and no value in the text; the test asserts that neither the bound nor the id appears in the message.
- **`test_scenarios.py`** (metamorphic): a bore change, an entered C, and a C set back to null on a base that enters one each solve bit for bit like the hand-edited project.

### 7.4 Independent checks

- **Checks that D6 cannot replace,** in `test_reference_cases`' orifice block: at the solver's own flow, the reported C_L equals `element_laws.orifice_c(Re_eff(Q))` (times r for C12) to 10⁻¹² relative, K equals K(C_L) to 10⁻¹², `headLoss` equals K v²/2g within the energy stop tolerance, and Δp equals eq. (1) at the reported flow to 10⁻¹². With C6 and C7 these are what catch a wrong C(Re) (§3.1).
- **The calibration identity** (decision 13), a metamorphic test on C12's network: solve it on ISO's C, then with an entered C equal to the reported `meterDischargeCoefficient` (the full double). The flow, K and reading must equal the first solve's to 10⁻¹⁰ relative (the prototype gives 0 and 2.2×10⁻¹⁶; R3). It fails if an entered C is used for the loss as entered (−2.5 %) or moved by the wrong form.
- **`tests/differential/orifice_check.py`** (new; decision 24). For each project with an active isolation valve that has a result, solve it (A). Then replace each such valve by an orifice on the same ports and elevations, with D = the valve's `referenceDiameter` (its inlet bore), and solve again (B). It runs in two modes, each with an exact expected answer, A itself:
  - **Mode 1, entered C, no taps** (so C_L = C and K is constant, decision 13): C drawn per valve in [0.6, 0.65] with `Random(f"orifice:{name}")`, and β from the exact inverse β⁴ = 1/(1 + C²((1 + √K_open)² − 1)), so that K = K_open. B must equal A to round-off, as `equipment_check`'s 7.8×10⁻¹⁰.
  - **Mode 2, ISO's C:** β by brentq so that K(C_L(β, Re_eff(Q_A))) = K_open, with seeded taps for the reading. A's state then satisfies B's equations exactly, so B must reproduce it through the Re-dependent law and its slope. Valves at zero flow are included, with C at Re_lo.
  - Valves whose K_open is below K at β 0.95 stay valves and are counted. V's sample survey (291 valves with results in 243 projects) found a mode-1 bore for 245 of them; K_open's median is 1.07 and its 95th percentile 391. The full counts are the build's.
  - **Criteria (D13):** the same convergence; every flow, EGL and static pressure within D6, the largest differences recorded. In B's own results: `pressureLoss` = ρg·`headLoss`, the static drop equal to §3.7's identity, and C_L equal to eq. (4) at the reported flow, all to round-off.
  - A smoke test pins a few projects (`test_orifice_check_smoke.py`).
- **The corpus tools learn the type:**
  - `tests/unit/scenario_patch.py` (`FIELDS["orifice"]`, `_component_value`) and `tests/reference/scenario_patch.py` (`COMPONENT_FIELDS[Orifice]`);
  - `test_scenarios.draw`;
  - `scenario_check.OUT_OF_BOUNDS` (a bore of 0 or 11 m, a C of 0 or 1.5);
  - `goal_seek_check`: `candidates`, `case_value`, `written`, `SPAN_FLOOR` and `goal_value`/`goal_candidates` for the four goals, the reading only with taps;
  - `compare.py`, as D18 changed it for `equipmentResults`: `orificeResults` joins `element_flows` and `Judge.element`, so orifice values get the zero-flow round-off allowance and orifice flows count in the largest flow; `differentialPressure` and `venaContractaPressure` join the pressure `KEYS` (`pressureLoss` is there since D18), so `--within-tolerance` judges them at ρg·10⁻⁶ m and not at 10⁻⁶ relative; `test_harness.py` gains the cases, as D18's did.

  Without them the new reference cases crash the tools, as D18 found, and every later solver change compared with `--within-tolerance` would misjudge the orifice cases in the corpus.

### 7.5 Acceptance (D6, D13)

- The reference suite is green, with C1–C12 and E1–E3 (15 cases), G33–G39, the calibration identity and the scenario tests.
- The corpus comparison gives 5,151 identical (§3.9). On the branch's corpus, `scenario_check` gives 0 different, `goal_seek_check` 0 violations, `equipment_check` 0 different, and `orifice_check` no difference beyond D6 in either mode.
- The three fuzz profiles give the same 9,000 records.

### 7.6 Unit, component and e2e tests

- **API unit tests:**
  - fluids' five docstring examples;
  - the transcription equal to fluids to 2×10⁻¹⁵;
  - K·ρv²/2 = `dP_orifice`(Δp);
  - the C ↔ K round trip;
  - Borda–Carnot at C = 1 (`diffuser_sharp`·(D/d)⁴);
  - Skelton's 0.823;
  - the cancellation-free K equal to `discharge_coefficient_to_K` to 4×10⁻¹⁵ for β 0.02–0.97, and positive and strictly decreasing in β for 1 − β from 10⁻³ to 10⁻¹² (where fluids' form returns 0);
  - monotonicity in Re and β, including the held K strictly decreasing across β 0.56 (the continuous Re_lo);
  - the hold: continuous at Re_lo, and fluids never called at Re < Re_lo or Q = 0;
  - dC/dRe, dr/dRe and dK/dC = −2K(1/C + β²/S) against central differences;
  - the move: r = 1 without taps and at D and D/2 taps; C_L = C_e·r at corner and flange taps; and an entered C equal to ISO's C at the taps giving ISO's C_L;
  - each bound of decision 17, (a) to (d), at its edge: β at the C = 1 limit (0.97025 for D ≥ 71.12 mm), an entered C just above 1/r_max at corner taps, a tiny d and a tiny C, with r_max and r_min never exceeded by r on a Re grid;
  - p_vc with the ports at different elevations (the downstream port's elevation, for either flow direction) and null at zero flow;
  - each flag at its bound;
  - an entered C equal to a gate valve of K = `discharge_coefficient_to_K`;
  - zero flow and a dead end;
  - closed off (no result) and floating (no p_vc);
  - the trace: every source, `default` for ISO's C and for no taps;
  - methods: a section only with an orifice, the entered-C item only with one, and a summary without orifices unchanged;
  - `EXPECTED` and the version pins (1.4.0).
- **Web unit tests:**
  - factory (valid, the bore's missing-entry error, the prefix);
  - model-rules (the component union, `x-override-fields`, `x-goal-variables`, the four quantities);
  - schema bounds;
  - encoding;
  - edit (insertion orientation);
  - `utils/orifice` (a library pipe, a custom pipe, an ID override, the pipe's from or to end, the inlet not connected, the library not loaded, β ≥ 1);
  - results ("—" without taps; the view only when present; strip = cells);
  - compare (relative only with a true zero; `compareElementKind`);
  - goal-seek (bounds with and without D, never reaching D; C's bounds, below 0.99/r̂ with corner or flange taps; `NEED_CHECKS.taps` read through the published `needs`);
  - scenarios (labels, value texts, null as "ISO 5167-2 (default)");
  - issue-text and flag-text (each limit in SI and US units, the vena contracta, the fallback).
- **Component tests:**
  - `OrificeForm`: accessible names "(mm)" and "(in)", exact SI storage, every β state, the entered-C warning, and the scenario Changed and Reset;
  - every Add surface: the bore's error first, then the plate is added;
  - `ResultStrip`, `ResultsViews`, the GoalSeek groups and `CompareRowsDialog`.
- **Export:** oracles in `export/model.test.ts`, conditional About lines, no sheet without plates, and no values for a case that did not converge. `export_input.scenario_project()` gains a plate whose outlet pipe is a size up, so a swapped static-drop column fails, plus an S1 bore change. `test_web_export_fixture.py` gains the sheet.
- **E2E `tests/orifice.e2e.ts`**, desktop and phone, against the real API.
  - **The network:** R1 (0 m, level 5 m) → 10 m NPS 4 Sch 40 with a sharp entrance → O1 → 10 m NPS 4 with an exit → R2 (0 m, level 0); water at 20 °C.
  - **Expected values** were measured with a gate-valve stand-in of K = K(C_L(Q)) iterated to a fixed point (`synth/e2e.out.txt`; "Calibrated" re-measured under decision 13's move, `reviser/cases2.out.txt`).
  - **Flow 1, build and solve.** Add after; the bore's error; enter 50 mm and choose Flange taps; the form shows β 0.4890 against 102.3 mm. Solve.
    - Expected: 13.0855 L/s, permanent loss 42.4832 kPa, differential pressure 57.1424 kPa, β 0.48895, C 0.604705, Re 1.62376×10⁵, static drop 42.4832 kPa, head loss 4.33987 m, no flags.
    - The strip equals the table, and the trace sources read User and Default. Share, reopen, and see the same table.
  - **Flow 2, insert into a connection** (the bypass placement), including the layout check that the first click lands on Add.
  - **Flow 3, scenarios**, then Solve all; Compare's default rows hold O1's flow and permanent loss.
    - "Bigger bore" is one bore change to 60 mm: 19.2555 L/s, 35.3691 kPa, reading 55.2133 kPa.
    - "Calibrated" enters C 0.62, the C at O1's flange taps: C_L = 0.619924 after the move; 13.4147 L/s, 42.1685 kPa, reading 57.1409 kPa.
  - **Flow 4, goal seek:** O1's flow = 12 L/s, varying O1's bore within the default bounds [10.23, 76.70] mm. It is met near 48.0331 mm (β 0.46972). Apply as a new scenario.
  - **Flow 5, export:** the dialog lists Orifice plates with one row per case.
  - axe scans of the form and the view at both sizes.

### 7.7 Synthesizer's and reviser's checks (`synth/*.py`, `reviser/*.py`, each with its `*.out.txt`)

| # | Check | Result |
|---|---|---|
| S1 | K across tap positions at Re 10⁵, D 102.26 and 300 mm, against D and D/2 (`s1_loss_c`) | corner −0.47 to +5.79 %, flange −0.28 to +5.37 %, Reader-Harris's (L1 = 1, L2′ = 0.125) −0.06 to −1.21 %; 1 − β^1.9 against the relation −0.83 % at β 0.6 and −4.5 % at 0.75. The transcription equals fluids exactly on the grid (Re ≥ 5000). |
| S2 | C1–C11 under this design's law, with a valve stand-in in the real solver (`cases`) | §7.1; every stand-in flow equals the closed form to ≤ 2.2×10⁻¹⁶ |
| S3 | EPANET GPV under this design's law (`epanet`) | §7.2 |
| S4 | Goal-seek inverses (`gs`) | §7.3 |
| S5 | The web e2e values under this design's law (`e2e`) | §7.6. W's values used the flange C for the loss: 13.0871 L/s, 0.012 % above this design's. |
| S6 | Code facts the decisions rest on | `_check_bounds` only validates the model (no build). `AxisSpec.case = None` starts the search at the middle. `value_text(None)` gives "none (the default)". `BELOW_VAPOR_PRESSURE` is `invalid`, with a component-level form (the reservoir surface, `surfaceAbsolutePressure`). `UNCONNECTED_PORT` guarantees an inlet pipe. `validate.ts` tags `{kind}` objects by kind, which this design avoids by having no union. WANDA's model uses D and D/2 for its whole element (its documentation, line 111). |
| S7 | C at corner and flange taps against D and D/2, β 0.6 and 0.75, D 102.26–900 mm, Re 10⁵ and 10⁷ (`s7_meter_c`) | C_M/C_L − 1 down to −2.19 % at β 0.75 (reading +4.54 %); −0.16 to −0.33 % at β 0.6 (reading +0.31 to +0.66 %) |
| R1 | The meter's own C for the loss against one loss per plate, on a 102.3 mm or 300 mm line of 2 m with 1 m of head (`checks`, F9/Q3; the reviewers' `taps_k` and `entered_c` reproduced) | K +3.12 % and Q −1.40 % at β 0.7 (corner); K +5.95 % and Q −2.50 % at β 0.75 (corner); K +2.71 % and Q −1.17 % (flange, 102.3 mm) and K +5.57 % and Q −2.57 % (flange, 300 mm) at β 0.75; K +0.59 % and Q −0.28 % at β 0.6 (corner) |
| R2 | C_DandP at L2′ = 0.125 against D and D/2 (`reviewer-physics/l2p`, reproduced) | Q +0.532 % (102.3 mm, β 0.75), +0.557 % (300 mm, β 0.75), +0.478 % (102.3 mm, β 0.6) on the R1 lines |
| R3 | The calibration identity: ISO's default against an entered C equal to ISO's C at the meter's taps (`checks` F1b, `cases2`, `cases4`) | Entered C used for the loss as entered: Q −2.53 % (β 0.75 corner), −1.18 % (flange), −2.59 % (300 mm flange), −1.42 % (β 0.7 corner), −0.29 % (β 0.6 corner). With decision 13's move: every flow and reading within 4.4×10⁻¹⁶ (0 on C12's network) |
| R4 | The held K across β 0.56 (`checks` F4; `reviewer-physics/beta056` reproduced) | ISO's written limit: K rises by 2.8×10⁻⁴ (relative) from β 0.56 to 0.5600001. With max(5000, 16000β²): K strictly decreasing over 30,001 β in 0.5585–0.5615, and over β 0.02–0.97 for every tap set and D 52.5 mm–1 m |
| R5 | K's forms (`checks` F3, `ratio_checks` 3; `reviewer-physics/kzero_scan` reproduced) | fluids' subtractive K is 0 or above decision 17's old bound in 188 of 1,200 cases with 1 − β ≤ 1.2×10⁻⁵. The cancellation-free u equals it to 3.6×10⁻¹⁵ for β 0.02–0.97 and C 0.3–1, and stays positive and strictly decreasing in β for 1 − β 10⁻³–10⁻¹²; d ln K/dC = −2(1/C + β²/S) to 4.1×10⁻¹⁰ |
| R6 | The move of an entered C (`checks` F1a/F1c, `mono3`–`mono5`, `ratio_checks`) | ΔC from fluids equals the transcription's tap terms to 1.1×10⁻¹⁶; ΔC in [−0.00146, +0.01290] (corner) and [−0.00120, +0.01331] (flange) over ISO's range. The additive move fails: d ln h/d ln Q down to −0.73 above β 0.97025 (C_e 0.01) and to −76 below it (C_e 10⁻⁴, flange). The ratio move: d ln r/d ln Re ≤ 0.076 and d ln h/d ln Q ≥ 1.78 over 9,118 plates (corner and flange, D 10 mm–3 m, β 0.02–0.97024, C_e 10⁻⁶–1 with C_L ≤ 1); r in [0.99764, 1.02254] over ISO's range |
| R7 | ISO's C past β 0.75 (`checks` F2, `mono2`; `reviewer-physics/highbeta`, `mono`, `s1_check` reproduced) | Exact maximum of C at D and D/2 reaches 1 at β 0.97252 (0.97261 at D 52.5 mm); the term-wise bound at 0.97025 (0.97034), increasing in β over 0.5–0.999; the smallest bound above 0.5887 for every β < 1. From β 0.75 to 0.97024: C strictly decreasing in Re (largest step −7.65×10⁻⁶), d ln h/d ln Q ≥ 2.001202 |
| R8 | Decision 17 (c)'s r bounds (`rbound`, `rvar`) | r_max and r_min hold on every Re grid point (corner and flange, D 20 mm–1 m, β 0.05–0.97024); where r exceeds 1, r_max exceeds its true maximum by at most 3.6×10⁻⁵ over ISO's range and 9.7×10⁻³ up to the β limit; the largest entered C accepted at β 0.75 is 0.978575 (corner) and 0.990030 (flange); r changes by at most 0.66 % with Re at one plate over ISO's range |
| R9 | Re-measured cases (`cases2`, `cases3`, `cases4`) | C1 and C11 unchanged to every digit printed; C3 without taps unchanged but its reading; C12, G37, G38, G39 and the e2e "Calibrated" values of §7.1, §7.3 and §7.6 |

---

## 8. Files to change

**API** (`apps/api/src/opensolve_pipe/`):
- `models/components.py` (`Orifice`, the union), `models/results.py` (`OrificeResult`, `SolvedState.orificeResults`), `models/scenarios.py`, `models/goal_seek.py` (`LOG_FIELDS`, the four quantities, `needs=('taps',)` on the reading).
- `services/solver/{network,builder,results,trace,methods,version}.py`, plus the new `services/solver/orifice.py`.
- `services/scenarios.py` (`COMPONENT_NAMES`, `value_text`) and `services/goal_seek.py` (`goal_value`, the null start's text, `_check_bounds`'s build with index-located messages, the `taps` need's `GOAL_NOT_APPLICABLE`).

**API tests and tools** (`apps/api/tests/`):
- `reference/{element_laws,case_format,network_check,closed_form,build_closed_form_cases,generate_epanet_cases,test_derivation_checks,test_reference_cases,test_goal_seek,derivations_goal_seek,test_derivations_current,test_scenarios,test_system_curves,scenario_patch}.py`, the new `derivations_orifice.py`, `cases/orifice_*.json` and the three EPANET cases. `derivations_goal_seek.py` holds G33–G39 with `MET_CASES`, `LABELS` and `DIMENSION`, as it holds D18's G25–G32. `test_derivations_current.py`'s `EPANET_CASE_NAMES` gains `epanet_orifice_line`, `epanet_orifice_balancing` and `epanet_orifice_low_re`; without them the EPANET case files are never checked for staleness, and nothing fails.
- `unit/` tests (with `test_methods.py`, `test_goal_seek_models.py`, `test_schema_rules.py`, `test_web_export_fixture.py` and `scenario_patch.py`), and `fixtures/{export_input,scenario_cases,goal_seek_cases}.py`.
- `differential/{scenario_check,goal_seek_check,compare,test_harness}.py` (§7.4; `compare.py` as D18 changed it), and the new `orifice_check.py` with `test_orifice_check_smoke.py`. `corpus.py`, `generator.py`, `checks.py`, `epanet_model.py`, `fuzz.py` and `equipment_check.py` do not change.

**Web** (`apps/web/`):
- `src/lib/api/{openapi.json,schema.d.ts,types.ts}` (regenerated).
- `utils/factory.ts`, `components/panel/kinds.ts`, `state/workspace.svelte.ts` (`INLINE_KINDS`).
- `components/panel/{AddComponentDialog,NewComponentFields,ComponentPanel,PortsEditor}.svelte` and `forms/EquipmentForm.svelte` (its hint names restriction orifices), plus the new `OrificeFields.svelte` and `forms/OrificeForm.svelte`.
- `utils/{results,compare,goal-seek,scenarios,issue-text,flag-text}.ts` (`goal-seek.ts`: `NEED_CHECKS.taps`, the bore's and C's default bounds), the new `utils/orifice.ts`, and `utils/export/{tables,about}.ts`.
- `components/results/{ResultsPanel,TraceView,CompareRowsDialog}.svelte` and `components/workspace/goal-seek/VariableCard.svelte`.
- `testing/{helpers,results}.ts` (`orificeProject`).
- The regenerated fixtures under `utils/__fixtures__/`.
- The new `tests/orifice.e2e.ts`.

**Docs:**
- **CLAUDE.md:** D5 moves the orifice plate into v1, keeping other plates, nozzles, venturis and sprinklers deferred. A new **D19** gives the model, the law, decisions 1–25 in brief, the named departures of §1.1 (as D9 names its EPANET departures) with the owner's answer to Q3, and the proof. D15's allow-list and D16's goal list are amended in place. D16's sentence "every model rule on these values bounds one value, so validating the 2n bounds before any solve proves every trial validates" is amended: an orifice's bore also meets topology rules, checked by a build at each bound of an orifice's bore or C variable, which proves every trial builds for one such variable alone; any other refused trial is an unusable trial.
- **PRD:** the Orifice row leaves §3.1.1 (Nodes) for §3.1.2 (Links), v1: "Bore; C by ISO 5167-2 (Reader-Harris/Gallagher, default) or entered (ISO's discharge coefficient at the plate's taps, not the flow coefficient α = C/√(1 − β⁴)); pressure taps for a meter's reading; a restriction given by a drop at a flow, a Cv or a Kv is Equipment". §2.3's "In v1" list gains an orifice-plate bullet beside Equipment's. Also §3.8, §3.9 and the Later list.
- **SDD:** §3.1.3, §4.2 (the union; "Later: … Orifice" drops it), §4.10, §4.12, §4.13, §5.1.4 and a new §4.15 Orifice Model.
- **TSD:** a new §4.10, §5.3 (the law table), §5.7, §8.3, §10.1, §10.4 and §12.
- **README.md:** the features list gains an orifice-plate line beside Equipment's, as D18's did.
- **docs/prompts/continue-v1.md:** the decision range (D1–D19), the verified counts with the orifice cases and `orifice_check`, and the candidates, as D18 updated them.
- **This proposal:** marked as built, with an as-built section.

---

## 9. Later

- **Other plates:** eccentric, segmental, quadrant-edge and conical (ISO/TR 15377, Miller; fluids has `C_eccentric_orifice_ISO_15377_1998` and others), thick plates (e/d > 0.1, Idelchik), and multi-hole and multi-stage restriction orifices (which V's restriction-orifice source recommends at high pressure ratios).
- **Nozzles and venturis** (ISO 5167-3 and -4).
- **Low-Re C:** Hollingshead (β 0.5–0.7) or Miller in place of the held C.
- **Cavitation:** choked flow, and an incipient-cavitation design check (a cavitation index per plate, opt-in).
- **Gases:** expansibility (`orifice_expansibility`).
- **Installation checks:** straight lengths, roughness and the recovery length against the outlet pipe, as design checks.
- **ISO's uncertainty of C** in the trace.
- **A reverse-flow (bevelled plate) model.**
- **A Cv or Kv on the orifice** (Q1, if the owner wants it).
- **The loss's C at Reader-Harris et al.'s L2′ = 0.125** in place of D and D/2, if a source in hand settles the choice (§1.3 item 13).
- **Web:** a β preview in the Add dialog, an example project with a pump's minimum-flow bypass, and a schematic symbol (ui-ux item 15).
- **A fuzz profile `orifice`**, if `orifice_check` finds a difference.

---

## 10. Owner's answers (2026-10-27)

The design put three product questions to the owner, each with a recommended default; all stay reversible under D14. The owner chose the recommended default for each, on 2026-10-27. The physics choices (the tap position of the loss's C between D and D/2 and L2′ = 0.125, the hold below ISO's Reynolds limit, the C ≤ 1 refusal, the flashing flag) were decided in this design, not put to the owner.

1. **How an orifice's C is given: (a), as recommended.** ISO 5167-2's Reader-Harris/Gallagher C by default, or a C the user enters from a calibration or datasheet: ISO's C at the plate's taps, not the flow coefficient α = C/√(1 − β⁴), as a valve's K is Crane's by default or the user's (decisions 2 and 13). No Cv or Kv on the orifice: a restriction known only by a Cv, a Kv or a drop at a flow is D18's equipment element, and both forms' hints say so. Not chosen: (b) a Cv or Kv on the orifice too; (c) ISO's C only, with an entered C Later.
2. **One element for both uses: (a), as recommended.** One menu entry, "Orifice plate (ISO 5167-2)", with optional pressure taps: none means a restriction orifice with no reading; corner, flange or D and D/2 taps make it a flow meter whose differential pressure is reported at those taps (decisions 1, 2, 14 and 25). Not chosen: (b) two menu entries creating the same element.
3. **A flow meter's permanent loss: (a), as recommended.** One loss per plate: the loss uses the C at D and D/2 tappings whatever the taps, ISO's C there or an entered C moved there by ISO's ratio of the two tap sets' C, and the trace and methods name this as a departure and show the K the meter's own C would give (decisions 5 and 13). Not chosen: (b) ISO's relation read literally with the meter's own C, whose loss depends on the tap choice (up to 5.95 % in K and 2.6 % in flow at β 0.75; within D6 for β up to about 0.6). [Review note, 2026-10-28: those sizes were R1's lines; over ISO's whole range the largest are 6.14 % (corner) and 6.34 % (flange) in K and 2.94 % and 3.03 % in flow where the plate takes the whole head, and within 0.84 % in K and 0.42 % in flow for β up to 0.6 (§12 item 41). The choice is unchanged.]

**Since this design was written** (`2014c6e`), `main` gained D19, the opt-in design checks (PR #247). The build takes the next decision number, **D20**, and the next method version after `main`'s at the time it is built, and checks whether a D19 check applies to the orifice (none is expected: D19's checks are a pump's NPSH margin and operating region and a pipe's velocity).

---

## 11. Review record

Two reviewers, one on the physics and one on the product, reviewed the synthesis. The reviser checked every finding by reproducing it (the reviewers' scripts re-run, and its own `reviser/*.py`) or by reading the code at `2014c6e`, revised the design at the root, and re-measured every number the revision changes (R1–R9, §7.7). All twenty findings were upheld. Where the reviser's fix departs from the one a finding suggested, the reason is given.

| # | Finding (severity) | Verdict | Evidence checked | What changed |
|---|---|---|---|---|
| F1 | An entered C gives the same plate a different loss than ISO's default, against decision 5's premise (should fix) | Upheld | `entered_c` re-run: −2.53 % at β 0.75 (corner), −1.18 % (flange). R3 adds −2.59 % (300 mm flange). | Decision 13: an entered C is the C at the plate's taps (D and D/2 without taps). The reading uses it as entered; the loss uses it moved to D and D/2, C_L = C_e·r with r = C_ISO(D and D/2)/C_ISO(taps) at the same Re. A calibration equal to ISO's C now gives ISO's answer to 4.4×10⁻¹⁶ (R3). The finding's option (b), adding eq. (4)'s tap-term differences, was tried first and rejected: for small entered values it makes h(Q) non-monotone (d ln h/d ln Q to −76, R6). The ratio keeps d ln h/d ln Q ≥ 1.78 (R6), and it is the ratio of ISO's differential pressures at the two tap sets. Also changed: §1.1, §1.3 item 12, §2.1, §2.2 (`tapCoefficientRatio`), §3.2, §4.1, §4.2, decisions 1, 2, 11 and 20, §3.5's flag conditions, §3.9's changelog, and C3, which loses its taps so it stays a constant-K case. New: C12 (corner taps, β 0.75, the move beyond D6), the calibration identity (§7.4), G37 moved onto C12's network, the e2e "Calibrated" values, and orifice_check's mode 1 without taps. |
| F2 | Above β ≈ 0.9725 ISO's extrapolated C exceeds 1 and K falls below Borda–Carnot, with only a β warning (should fix) | Upheld | `highbeta`, `s1_check` and `mono` re-run; R7. | Decision 17 (b) and (c): a plate whose C_L can exceed 1 at some flow is refused (`ORIFICE_OUT_OF_RANGE`, 422). In the loss relation C ≤ 1 is exactly μ ≤ 1, so the refusal states a physical bound, as D9 refuses where no cited correlation exists. The closed-form bound refuses β ≥ 0.97025 (0.97034 at D 52.5 mm) on ISO's C, increases with β, and is 0.0023 in β stricter than the exact maximum (R7). The finding's alternative, holding C at 1 and flagging, was not taken: it would solve an uncited clamp. Below the limit, C strictly decreases with Re and d ln h/d ln Q ≥ 2.0012 (R7), which corrects §3.1's monotonicity claim to its domain. The issue was renamed from `ORIFICE_BORE_OUT_OF_RANGE`, because a moved entered C can also break it. |
| F3 | fluids' subtractive K loses all precision as β → 1, so decision 17's "finite positive bounds" fails in floating point (nit) | Upheld | `kzero_scan` re-run: 188 of 1,200 cases; R5. | §1.1 and decision 8: K in the cancellation-free form u = (1 − β⁴)/(Cβ²(S + Cβ²)), with 1 − β = (D − d)/D. It equals fluids' to 3.6×10⁻¹⁵ where fluids' form does not cancel, and it stays positive and decreasing in β down to 1 − β = 10⁻¹² (R5). dK/dC = −2K(1/C + β²/S) (R5). Unit tests pin both (§7.6). |
| F4 | ISO's Re_lo jumps at β = 0.56, so the held K(β) is not monotone and the bore inverse is not unique (nit) | Upheld | `beta056` re-run; R4. | Decision 7 and §3.2: Re_lo = max(5000, 16000β²), the finding's fix. It is continuous, and stricter than ISO's only for 0.559 < β ≤ 0.56, by up to 17.6. The held K is now strictly decreasing across 0.56 and over β 0.02–0.97 for every tap set (R4). Named in §1.1 and the trace. No case changes: none has β in that band. |
| F5 | C_L at D and D/2 rather than the cited theory's L2′ = 0.125 moves the flow beyond D6 at β 0.75; say so (nit) | Upheld (state it) | `l2p` re-run: +0.532 %, +0.557 %, +0.478 % (R2). | D and D/2 is kept: ISO's own tap set with ISO's Reynolds limits, WANDA's choice, and within the theory's own constraint (p2 "between the downstream corner and the vena contracta"). The alternative and its size are now stated in decision 5, §1.1's named departures, §1.3 item 13, the trace (its C and K, marked not used), the methods summary and §9. |
| F6 | p_vc at the upstream port's elevation, against WANDA's downstream one, and undefined at zero flow (nit) | Upheld | WANDA's lines 113–124 and `models/ports.py:29–31` read. | Decision 15, §1.1, §2.2, §3.6 and §4.1: p_vc = p_up + ρg(z_up − z_down) − Δp_vc, at the elevation of the port the flow leaves by (WANDA); null and unchecked at zero flow. Every case has both ports at one elevation, so no number changes; a unit test covers unequal elevations both ways. |
| F7 | Decision 6's m = ρ\|Q\| contradicts the hold and raises at Q = 0; §3.8's status.py claim is inaccurate (nit) | Upheld | `C_Reader_Harris_Gallagher(..., m=0.0, 'D')` raises `ZeroDivisionError`. `status.py:693`, `gga.py:490`, and `status.py`'s `HeadOffsetLaw` and valve-type `isinstance` tests read. | Decision 6: m = (πDμ/4)·Re_eff. §3.4 names the evaluate(0.0) calls. §3.8 lists every `isinstance` in `status.py`, and why an orifice takes the safe branch. |
| F8 | The goal-seek bounds 400 would echo the bound and the id, which D10/D16 forbid (should fix) | Upheld | `goal_seek.py:197–200` (`GoalSeekInputError`: "no message holds an id or a submitted value") and `_check_bounds` (l. 1881–1902) read. | Decision 21, §5.2 and §7.3: the bounds 400 is located by index, with the orifice in `componentIds` and no bore, D, β, C or id in its text; the builder's quoting text is not reused, and the case's 422 keeps it. The reference test asserts that neither the bound nor the id appears. |
| F9 | Decision 5 departs from the owner's "permanent pressure loss per ISO 5167-2" beyond D6 but is not an owner question (should fix) | Upheld | `taps_k` re-run (+5.79 %, +3.05 %, +5.37 %); R1 on lines: K +5.95 %, Q −2.50 % (corner, β 0.75), −2.57 % (300 mm flange). | Both of the finding's fixes. Owner question Q3, with one loss per plate as the recommended default and the literal reading as (b). A named departure in §1.1, carried into D19's text (§8), the methods summary and the trace. §10's preamble now says why this one physics reading goes to the owner. Decision 13's move answers the related inconsistency for an entered C (F1). |
| F10 | The entered C is never defined; entering α = C/√(1 − β⁴) or a vendor "Cd" moves the flow by up to +20 % (should fix) | Upheld | `alpha_vs_c` re-run: +3.80 %, +8.95 % and +20.24 % in flow at β 0.5, 0.6 and 0.7. | §1.1, decision 2, §2.1's schema text, the form's hint (W3), the trace input, Q1 and the PRD row now define C by ISO eq. (1) at the plate's taps, and say that α is not C and how to convert it. |
| F11 | Two of the four goal quantities have no goal-seek reference case, so an existing test fails (should fix) | Upheld | `test_goal_seek.py:750–763` read: every `GoalQuantity` must appear in `MET_CASES`. | §7.3: G38 (`orifice_pressure_loss`, level inverse on C1, level* 0.814811461525 m) and G39 (`orifice_pressure_drop` on C11's unequal-bore outlet, level* 1.20165988673 m), both measured (`cases2`, `cases4`). A first G39 target of 60 kPa needed a negative level, so it was raised to 70 kPa. |
| F12 | The "reading needs taps" rule is hard-coded and copied in the web, instead of published as a `needs` (should fix) | Upheld | `models/goal_seek.py:355–357` (`needs`), `goal_quantities()` and the web's `NEED_CHECKS`/`goalNeedProblem` (`goal-seek.ts:339–373`) read. | §2.3, decision 21 and §5.2: `QuantitySpec(..., needs=('taps',))`; the API's need check gives the same 400; the web's `NEED_CHECKS` gains `taps`; the web test reads it through the published `needs`. |
| F13 | `compare.py` must learn `orificeResults`, as D18 had to for `equipmentResults` (should fix) | Upheld | `compare.py`'s `KEYS`, `element_flows` and `Judge.element` read; `git diff 3a01b94 2014c6e -- tests/differential/compare.py`. | §7.4 and §8: `orificeResults` in `element_flows` and `Judge.element`; `differentialPressure` and `venaContractaPressure` in the pressure `KEYS`; `test_harness.py` extended. `compare.py` was removed from the "do not change" list. |
| F14 | The files-to-change list misses files D18 changed for the same kind of addition (should fix) | Upheld | `git diff --stat 3a01b94 2014c6e`; `test_derivations_current.py`'s `EPANET_CASE_NAMES`; `derivations_goal_seek.py:1791`; `README.md:15`; `continue-v1.md`; `PRD.md:106` read. | §8 gains `derivations_goal_seek.py`, `test_derivations_current.py` (the three EPANET names), `README.md`, `docs/prompts/continue-v1.md`, PRD §2.3's In-v1 bullet, and D16's amended "every trial validates" sentence in CLAUDE.md. |
| F15 | The alternative of an Equipment rating kind is never recorded (nit) | Upheld | `components.py:415–431`, `elements.py:369–381` and D18 read. | §1.3 item 11 records both sides and why a separate type is chosen. |
| F16 | A restriction orifice rated by a drop at a flow has no visible path to Equipment (nit) | Upheld | `kinds.ts:13` and `EquipmentForm.svelte:83–90` read. | W3: the orifice's hint names "a pressure drop at a flow, a Cv or a Kv", and Equipment's hint names restriction orifices. The menu group's label is unchanged (§8 lists `EquipmentForm.svelte`). |
| F17 | "The two builds cover every trial" is false with a C variable too (nit) | Upheld | Decision 21's text against decision 17's bounds. | Decision 21 and §1.3 item 7: the builds run at each bound of an orifice's bore or C variable. They prove every trial builds for one such variable alone, where the test is monotone (R7, R8). With a bore and a C together, or a bore on a moved entered C, a refused trial is an unusable trial (D16). D16's text is amended to match (§8). |
| F18 | The export's "C from" hard-codes "held at Re 5000" and puts a number in a text cell (nit) | Upheld | Decision 7's Re_lo rule. | §5.4: "C from" is text only ("ISO 5167-2", "ISO 5167-2 (held)", "Entered", "Entered, moved to D and D/2"), with numeric columns for `coefficientReynoldsNumber` and `tapCoefficientRatio`. |
| F19 | The fallback bore bounds [d/2, 2d] are a guaranteed bounds 400 for β ≥ 0.5 (nit) | Upheld | Decision 21's 400 at a bound ≥ D. | W6: with no D the fallback is [d/2, d], which never reaches D. The resolver finds no D only when the inlet is unconnected (no goal seek can run) or the library has not loaded. The same principle is applied to C's default upper bound with corner or flange taps, at most 0.99/r̂, which decision 17 (c) introduced (R8). |
| F20 | Q1(c)'s stated cost is misdescribed (nit) | Upheld | Decision 11 and §9 read. | Q1(c) now says plates outside ISO's range are solved and flagged under every option and multi-hole plates are Later under every option. The real cost is the loss of a calibrated or vendor C: the "Calibrated" scenario, G34, G37 and the calibration identity. |

**Not changed by the review:** the law for ISO's C below β 0.97 and every case but C3 and the new C12. C1, C2 and C4–C11, E1–E3, G33–G36 and the e2e flows 1, 2, 4 and "Bigger bore" have the same numbers, since none has an entered C at corner or flange taps, β near 0.56 or β above 0.97, and the cancellation-free K equals fluids' there to round-off (R9). The corpus-comparison plan and its bit-identity argument (§3.9) are unchanged.

---

## 12. As built

The element was built from §1–§11 on `main` at `b6e2088`, not on `2014c6e`: since this design, `main` gained the pump chart's curve facts (PR #244) and the opt-in design checks (D19, PR #247: `services/design_checks.py`, `SolvedState.designChecks`, `ProjectSettings.designChecks`). Where this design's file or line references had moved, the builders followed the code. The decision is **D20**, not §8's D19, and its specs are SDD §4.16 and TSD §4.10 (D19 took SDD §4.15). A contract builder wrote the models and published rules; an API builder the solver law, builder, results, flags, trace, methods text, version and the scenario and goal-seek services (`tests/unit/test_orifice.py`, 48 tests, beside the contract's `test_orifice_model.py`); a reference tester who did not read `services/` or any builder's notes wrote `derivations_orifice.py`, the 15 cases, G33–G39 and the scenario tests; a corpus-tool builder `compare.py`, the scenario patchers, `scenario_check`, `goal_seek_check`, `orifice_check.py` and the fixture sources; a web builder the web side; an API integrator ran the proofs; a web integrator regenerated the committed export fixtures and ran the web gates and the e2e flows; a docs integrator wrote the specs (CLAUDE.md D5, D15, D16, D20, the status line and the spec notes; PRD §2.3, §3.1.1, §3.1.2, §3.1.4, §3.2.1, §3.2.3, §3.8, §3.9; SDD §3.1.3, §3.2.1, §4.2, §4.10, §4.12, §4.13, §4.16, §5.1, §5.1.4; TSD §3.1, §4.10, §5.1, §5.3, §5.6, §5.7, §8.1, §8.3, §10.1–§10.4, §12 item 14; README; `docs/prompts/continue-v1.md`).

**Design checks (D19).** None of D19's checks applies to the plate, as §10 expected: the NPSH margin and the operating region (with its manufacturer data) are a pump's, and pipe velocity covers the pipes on both sides of a plate, not its bore. The web's design-check code lists no component types. `test_orifice.py::test_no_design_check_applies_to_a_plate` pins it (only pipe velocity on the plate's two connections), and the `design_checks_check` smoke test passed over the orifice reference cases.

Where the build departs from this design, each departure is reversible (D14), and none weakens a rule of the design:

**Contract and API**

1. **The Reynolds flag** (§3.5) is raised when 0 < Re_D is below C_L's Re_lo, or below the Re_lo of the plate's corner or flange taps wherever eq. (4) is used there: ISO's C_M, and also an entered C moved from those taps, because the move's denominator C_ISO(taps) is evaluated at C_L's Re_eff, which can fall below that tap set's own limit. `details.meterLower` is present whenever eq. (4) is used with corner or flange taps, a moved entered C included, and left out at D and D/2 taps, where it would equal `lower`; §3.5 listed it only for "taps and ISO's C".
2. **The geometric and outlet-bore flags are raised in the builder**, as a valve's Crane size note is, because they are known before solving, so they also appear when the solve does not converge or the plate is closed off.
3. **Decision 21's bounds check** builds the trial at each bound of an orifice plate's `boreDiameter` or `dischargeCoefficient` variable (`_orifice_bound_issues`), and each `ORIFICE_OUT_OF_RANGE` naming that plate becomes an issue with that code inside the 400 `VALIDATION_ERROR` envelope, its rule looked up through `builder.orifice_refusals`. The texts: "the orifice's bore is not smaller than its inlet pipe's inner diameter"; for rule (b), by its basis (item 40), "ISO 5167-2's discharge coefficient at D and D/2 tappings, which sets the orifice's loss, could exceed 1 at this {bore\|discharge coefficient}", "ISO 5167-2's discharge coefficient at the orifice's taps, which gives its reading, could exceed 1 at this …" or "ISO 5167-2's discharge coefficient in the ratio that moves the orifice's entered coefficient to D and D/2 tappings could exceed 1 at this …"; "the orifice's discharge coefficient, moved from its taps to D and D/2 tappings, could exceed 1 at this …"; "the orifice's loss coefficient is not a finite positive floating-point number at this …". Any other topology issue at a bound is not expected; it would read "the project does not build at this bound (CODE)".
4. **The 422 texts** all begin "orifice '{id}': a bore diameter of {d:g} m in an inlet pipe of inner diameter {D:g} m (β = d/D = {β:.6g}): " and end in one of four tails: (a) "the bore is not smaller than the pipe; …"; (b) "ISO 5167-2's discharge coefficient (Reader-Harris/Gallagher) at {D and D/2 tappings\|corner tappings\|flange tappings}, {which sets the plate's loss\|which gives only the meter's reading\|one of the two in the ratio that moves its entered discharge coefficient {C_e:g} from its {taps} to D and D/2 tappings}, can reach {C:.6g} at some flow, above 1…", by its basis, with a remedy that works for the plate (item 40); (c) "its entered discharge coefficient {C_e:g} at its {taps}, moved to D and D/2 tappings by ISO 5167-2's ratio … (up to {r:.6g} at this plate), can reach {C:.6g} …"; (d) "with a discharge coefficient down to {C:.6g} it gives a loss coefficient, K/(2 g A²), that is not a finite positive floating-point number; …". The web's `issue-text.ts` reads these four forms, rule (b) by its basis (item 49).
5. **The term-by-term transcription** (`rhg_terms`) accepts Re ≥ 3700, where fluids' two extra terms are zero, rather than Re ≥ 5000: fluids itself turns m = (πDμ/4)·5000 back into Re_D = 4999.999999999999. `c_iso`, which supplies every C the solver uses, still refuses Re below 5000. No behaviour changes.
6. **fluids' subtractive K** (§7.6 said it "returns 0" for 1 − β from 10⁻³ to 10⁻¹²): in the API builder's measurements (C 0.6 and 1, D 52.5–300 mm) it never returned exactly 0 but lost accuracy, up to about 10⁻⁴ relative. The unit test pins the cancellation-free K to a 60-digit `Decimal` evaluation (10⁻¹² relative), asserts that fluids' form deviates by more than 10⁻⁶ there, and keeps the test that K is positive and strictly decreasing in β.
7. **The valves' inlet-pipe map** moved into a shared helper, `builder._port_end_pipes`, with the same behaviour, so the plate's D is resolved exactly as a valve's reference diameter.
8. **`COMPONENT_NAMES[Orifice]`** stays "orifice", as the contract set it, so messages read "orifice O1". The methods summary, the 422 text of rule (b) at D and D/2 tappings and, since the review (item 42), the trace name the Borda–Carnot bound; the methods summary and the trace cite `RENNELS`, as §4.2 allows. (Before the review only the methods summary and the 422 text named it.)
9. **Version pins.** `test_methods.py`'s 1.3.0 test finds its changelog entry by version instead of taking the last one, and a new 1.4.0 test pins `METHOD_VERSION`, the changelog list and its line; the literal 1.3.0 pins in `test_api_goal_seek.py` and `test_equipment.py` became 1.4.0. No assertion was dropped.
10. **Four web fixtures regenerated by the API builder** (`export-input.json`, `goal-seek-cases.json`, `export-results.xlsx`, `export-results.expected.json`) with their documented generators only (`pnpm gen:types`; `UPDATE_FIXTURES=1 vitest run fixture.test.ts`), because the bump to 1.4.0 made them stale and failed three API unit tests; only `methodVersion` strings changed.

**Reference cases** (the tester's choices)

11. **The GPV curve's span** (decision 23) is [0, Q_span] with h_or(Q_span) equal to the spread of the network's fixed heads, not [0, 2\|Q_ref\|]: in a network without pumps no plate carries more than that flow, and the span comes from the project alone, so `network_check` rebuilds exactly the curve EPANET ran (the generator checks the INP text against it). EPANET's flows come out above the closed form by +1.52×10⁻⁴ (E1), +1.34×10⁻⁴ and +3.15×10⁻⁴ (E2's legs) and +1.2×10⁻⁵ (E3), within about 3×10⁻⁶ of §7.2's +1.534×10⁻⁴, +1.352/3.181×10⁻⁴ and +1.478×10⁻⁵.
12. **The expected block is `orifices`** and holds all 17 `OrificeResult` fields, not §7.1's eight: texts and nulls must match exactly; flows, heads and pressures within D6; dimensionless values and diameters within 0.5 %.
13. **Expected flags may carry `limit`** (matched against `details.limit`) **or `detail`** (a key the flag's details must hold), so each `CORRELATION_OUT_OF_RANGE` inequality and the vena-contracta `BELOW_VAPOR_PRESSURE` are checked one by one; `_check_flags` was extended, and entries without these keys are matched as before.
14. **The EPANET orifice cases are in the `component` agreement test** (flows within 0.25 %, heads within max(0.25 %, 5 mm)), not the heads-pinned 1 mm test: a GPV curve has none of EPANET's g bias while the pipes beside it do, so heads between the reservoirs move by 1.28 mm (line) and 1.63 mm (loop). Both tests' docstrings say so with the measured numbers.
15. **Test inputs this design leaves open** (made up, as user data; none changes a printed value): plate elevations in C6 (0.5 m), C7 (0.5 m) and C8 (5 m, both plates), which change pressures only; liquid A for C9; E3 is R1 at z 0, level 1.2 m, to R2 at z 0, level 0, without taps; G35's starting bore 0.06 m and its demand at z 0; bounds [0.1 D, 0.75 D] for bores, (0.3, 1.0) for G34's C, (0.3, 0.95) for G37's C (which keeps C_e·r_max below 1 at the upper bound) and (0, 5) m for the levels of G38 and G39.
16. **The scenario test of a C set back to null** on C12 moves the flow by only +0.17 %, because its entered 0.6 is close to ISO's 0.6008 at the corner taps, so that scenario checks that the coefficient changed rather than a move beyond D6, and a null scenario on C3 (+0.58 %) was added.

**Corpus tools and fixtures**

17. **`equipment_check.head_bound`** also counts `orificeResults` head losses and reads the maps with `state.get`, although §8 listed `equipment_check.py` as unchanged: `orifice_check` reuses it as the round-off bound in floating sections, which without the plates' losses could be too small. Projects without plates give the same values, and the equipment smoke test passes.
18. **`orifice_check` checks more than §7.4 lists:** besides `pressureLoss`, the static-drop identity and C_L, it checks D (the valve's `referenceDiameter`, decision 3), d, β, Re_D, the taps, `coefficientSource`, Re_eff, C_M, the reading (eq. (1)), K = K(C_L), the head loss by the law (within 10 × the 10⁻⁷ m energy stop tolerance plus 10⁻¹² × the heads, for round-off) and the vena-contracta pressure (decision 15).
19. **`orifice_check` uses the solver's own `orifice.refusal`**, only to choose a buildable configuration: a drawn tap set decision 17 would refuse (flange taps on a small pipe at a high β) is dropped and counted as `untapped` (7 plates). Mode `iso` is seeded with `Random(f"orifice:iso:{name}")`; §7.4 names no seed for it.
20. **β stays within [0.02, 0.95] in both modes;** §7.4 states only the 0.95 cap. At β 0.95, K is 0.031–0.042 on ISO's C and 0.058–0.077 with an entered C of 0.6–0.65, so more ball valves stay valves in mode `entered` (317 kept, against 83 in mode `iso`).
21. **The smoke test's `NOISE`** is {flow 10⁻⁹, head 10⁻⁵ m}, where `equipment_check`'s is {10⁻⁹, 10⁻⁶ m}: the corpus-wide head maximum is 6.71×10⁻⁶ m, in `fuzzaf_20938`, whose heads reach 4,600 m (1.6×10⁻⁹ of its 4,264 m head loss, the solver's flow tolerance). Equipment gives 0 there because its law follows the valve's path bit for bit.
22. **`goal_seek_check` caps the bounds it draws** so that decision 21's bounds 400, which its check (a) would count as a violation, is not drawn: a bore at most 0.75 D (ISO's largest β, the web's default) and an entered C at corner or flange taps at most 0.98/r, r the ratio the case solved at. That 400 is left to the reference tests. The caps are not decision 17 (c) itself (the web review, item 45): r can be below r_max (a flange plate whose ISO C is held: C_L/C_M 0.9795 against r_max 1.0018 on 52.5 mm at β 0.7), and a bore drawn under an entered C at those taps is not capped by r_max, so a draw could reach that 400; none on the corpus did (0 violations). The tool and its records are unchanged; its docstrings and TSD §10.4 say so.
23. **`scenario_check`**: §7.4's "a bore of 0 or 11 m, a C of 0 or 1.5" is built as `OUT_OF_BOUNDS` (11 m, 1.5) plus a new `BELOW_BOUNDS` (0, 0), drawn half the time, with the extra random draw only when an orifice field was chosen, so draws for projects without plates are unchanged.
24. **`export_input.scenario_project()`** gains O1, a flange-tapped meter on ISO's C with a 62.7 mm outlet pipe after its 50 mm inlet pipe, so its loss (48.58 kPa) differs from its static drop (47.61 kPa); besides §7.6's S1 bore change (30 mm), S2 enters C 0.62 on it, so the shared fixture also covers "Entered, moved to D and D/2" and the tap-ratio column.
25. **`goal_seek_cases`** (listed in §8, not detailed) gains O1 (a flange-tapped meter on ISO's C, its outlet port 0.5 m up) and O2 (a restriction orifice with an entered C, no taps), four apply cases (the bore, a C on ISO's default, an entered C, and a scenario that sets both) and five goals; the reading on O2 gives null with a message. `test_goal_seek_cases` requires every goal quantity.

**Web**

26. **The β line** reads "β = d ÷ D = 0.4889, with D = 102.3 mm, the inner diameter of the inlet pipe (NPS 4, Sch 40)". W3's example has 0.4890 and "the bore of the inlet pipe": 0.05 ÷ 0.10226 = 0.48895, which is 0.4889 to four decimals (0.4890 rounds 0.48895 a second time), and "inner diameter" avoids two different bores in one sentence. The e2e test expects 0.4889.
27. **The β line has a fifth state,** "β is shown once the inlet pipe's inner diameter is known.", for a library pipe whose size the library lacks (the solve reports it as a topology issue).
28. **The Add dialog asks only for the bore** (the required entry; `EnteredValues` gains `boreDiameter`, and `OrificeFields.svelte` holds the bore field the dialog and the form share). The taps and C are set in the form after the plate is added, because a β preview in the Add dialog is Later (§9).
29. **`flag-text.ts` words every orifice limit from `details.limit` except `reynoldsNumber`,** which keeps the API's message with ids replaced by names: its numbers have no unit, and its consequence differs between ISO's C (held) and a moved entered C (used outside its range), which the details do not say.
30. **The goal-seek need text** for a plate without taps is "the orifice plate has no pressure taps, so it has no reading", in the style of the web's other need texts, not the API's 400 wording.
31. **Export column labels** follow the screen and file style: "Discharge coefficient (loss)" for C_L, "Bore" and "Pipe bore D" in the diameter unit; taps without a value are written "None".
32. **No axe scans** in `tests/orifice.e2e.ts`: the repository has no axe dependency (`@axe-core/playwright`), and adding one is a new dependency this build did not take.
33. **`export/orifice.test.ts`** puts made-up results through the Orifice plates sheet, as D18 has `export/equipment.test.ts`, beside the oracle fields in `model.test.ts` that run on the shared fixture's plate.
34. **Two existing tests changed** so they stay correct once the shared fixture holds a plate: `export/equipment.test.ts`'s About comparison strips orifice results so it compares the equipment lines alone, and `filename.test.ts`'s list of zip files gains `orifices.csv`.

**Integration**

35. **The export fixture's Compare rows** gained O1's four orifice rows (`orificeFlow`, `orificePressureLoss`, `orificeDifferentialPressure`, `orificePressureDrop`; `export_input.scenarios()`), closing the corpus-tool builder's open item; they change `export-input.json` and the committed workbook's Compare sheet.
36. **The export reader** (`apps/api/tests/unit/test_web_export_fixture.py`) learned the Orifice plates sheet from §5.4, written without reading the web's export code: its headers, a row builder (`expected_orifices`, "C from" from the result fields by §5.4's wording, the taps checked as any non-empty text), its place after Equipment, the four Compare readers (relative differences for the flow, the loss and the reading, not the static drop), the ≈ 0 About sentence naming orifice plate drops and losses, the orifice sign row exactly when the sheet exists, and a null `dischargeCoefficient` written "ISO 5167-2 (default)". Against a workbook the web's current code wrote, the three fixture test files passed 90 of 90; no existing assertion was weakened.
37. **The base corpus and the base fuzz** ran from a worktree of `b6e2088`; the fuzz baseline was run again there rather than reused, and the three profiles were compared record by record (every field but the time, tree paths normalized), which proves "no converged solve left not converged" directly. `goal_seek_check` ran once over the whole corpus, not split by prefix; its orifice coverage (fields and goals drawn) comes from re-drawing the same seeded requests without running them again.
38. **Web integration.** The committed workbook (`export-results.xlsx`, with `export-results.expected.json`) was regenerated from the new `export-input.json`, and `fixture.test.ts`'s pinned sheet list gained "Orifice plates" after "Equipment". The β line's text moved into a `<span>` that carries the id the bore's description points at, since an `<output>` takes its accessible name from its labels, never its text, so a description pointing at the `<output>` itself was empty in a browser; its component test now checks the text's parent. `tests/orifice.e2e.ts` takes D = 0.10226 m, the library's NPS 4 Schedule 40 inner diameter (ASME B36.10M's 114.3 mm OD and 6.02 mm wall, via fluids), where it had 0.1022604 m, and expects the goal seek's defaults as "10.226 mm to 76.695 mm". Bundle, measured by the final gate on the tree with items 39–49 against `b6e2088`: the initial `/p` download grew by 8.0 KB gzip (289,181 → 297,176 B; 6.6 KB at this integration, before the review fixes) and the export chunk by 0.5 KB (23,831 → 24,292 B gzip -9); the chart chunk and `third-party-licenses.txt` (11 packages) are unchanged (TSD §8.3); this design set no budget.

**Review fixes** (2026-10-28: an adversarial review of the built element; each finding upheld was fixed at its root, with a test that fails before the fix where it is code)

39. **Two closed-form cases more, C13 and C14** (`derivations_orifice.py`), written by the API fixer from the suite's own derivations (`element_laws`, `derivations_orifice`), never from the solver. C13 `orifice_entered_c_flange_low_re` pins item 1: an entered C of 0.6 at flange taps on a β 0.7 plate in a 0.3 m line, light oil, at Re_D 13,235, above D and D/2's Re_lo (7,840, so C_L = C_e·r(Re_D) is not held) but below the flange tappings' (170000 β² D = 24,990), so the move's denominator is eq. (4) below its tap set's limit, flagged `reynoldsNumber`. The independent reference had encoded the opposite rule (the tap set's Re_lo only for ISO's C), and no case reached the band, so the flag for a moved C was untested: `orifice_flags` and `test_derivation_checks`' flag check now take the plate's tap Re_lo wherever eq. (4) is evaluated there. C13's ports are 0.7 m apart in elevation (forward flow). C14 `orifice_reverse_flow_port_elevations` is C4 with the outlet port 1.3 m above the inlet port: in reverse flow p_vc runs from the outlet port to the inlet port's elevation (decision 15), and the static drop holds ρg(z_out − z_in); before, every case had both ports at the plate's elevation and only the builder's unit test and a fixture pinned the term. Unit tests: `test_a_moved_coefficient_below_its_taps_reynolds_number_is_flagged` (the flag with `details.meterLower`) and `test_the_input_flags_hold_where_the_plate_has_no_result` (item 2: the geometric and outlet-bore flags on a closed-off plate and in a solve that does not converge). Each fails under the review's runtime mutant of the rule it pins (the moved-C flag test and C13 under `no_moved_flag_only`, the flag test under `no_moved_meter_flag` too, the input-flags test under `input_flags_with_result_only`, C13 and C14 under `vc_no_elevation_term`) and passes without it.
40. **Decision 17 (b) says what its coefficient is used for** (`orifice.Refusal.basis`). The rule is unchanged, but its text was not true everywhere: only ISO's C at D and D/2 tappings sets the loss, where C ≤ 1 is the jet bound (Borda–Carnot); elsewhere eq. (4) serves only the reading (ISO's C_M at a meter's corner or flange taps) or the move (either coefficient of an entered C's ratio), and a C above 1 there is eq. (4) extrapolated far beyond ISO's range (its largest C over D 50 mm–1 m, β 0.1–0.75 and Re_D from Re_lo is 0.678, measured from `c_range`; no refusal falls inside that range). The 422 tail is now one of: "…at D and D/2 tappings, which sets the plate's loss, can reach {C} at some flow, above 1, which would make the jet larger than the bore … physically impossible; use a smaller bore, or enter a discharge coefficient (ISO 5167-2's C at D and D/2 tappings, used as entered)" for a plate without taps or with D and D/2 taps, and "…; use a smaller bore (an entered discharge coefficient at its {taps} would be moved to D and D/2 tappings by ISO 5167-2's ratio, which uses this coefficient, and refused the same way)" at corner or flange taps; "…at flange tappings, which gives only the meter's reading, can reach {C} at some flow, above 1: the correlation is extrapolated far beyond ISO 5167-2's range, so the reading at these taps has no basis (the plate's loss uses the coefficient at D and D/2 tappings, which stays at or below 1); use a smaller bore, D and D/2 taps, or no taps (a restriction orifice, with no reading)"; "…at {where}, one of the two in the ratio that moves its entered discharge coefficient {C_e} from its {taps} to D and D/2 tappings, can reach {C} at some flow, above 1: the correlation is extrapolated far beyond ISO 5167-2's range, so the move has no basis at this plate; use a smaller bore, or give the discharge coefficient at D and D/2 tappings (with D and D/2 taps, or no taps), where it is used as entered". `test_each_refusal_says_what_its_coefficient_is_for_with_a_remedy_that_works` checks each text and solves each remedy it offers. The goal-seek bounds texts (item 3) follow the basis. The thresholds, measured by bisection of `refusal` on ISO's C: 0.97025 for D ≥ 71.12 mm, rising to 0.9706 on the smallest pipes, without taps and with corner or D and D/2 taps; with flange taps on a pipe below about 55 mm the flange tappings' bound comes first (0.969 at D 52.5 mm, 0.963 at 40.9 mm, 0.930 at 15.8 mm, 0.67 at 2 mm). The methods summary, SDD §4.16 and TSD §4.10 say so; the web's `issue-text.ts` reads the new forms (item 49).
41. **The named departures' sizes are their largest over ISO's range** (methods summary, trace notes, SDD, TSD, §1.1, decision 5): R1's and R2's figures were measured on 2 m lines at Re about 10⁵–10⁶ but were stated as maxima, and the plate's own trace could exceed them inside ISO's range. Measured from fluids' C and K over D 50 mm–1 m, β 0.1–0.75 and Re_D from both tap sets' Re_lo up (the K ratio grows with Re_D, so the largest is approached as Re_D grows; ISO, as fluids documents it, gives no upper limit): ISO's relation with the meter's own C gives a K up to 6.14 % higher at corner tappings (at β 0.75, the same on every pipe) and 6.34 % at flange tappings (β 0.75, D 1 m), a flow up to 2.94 % and 3.03 % lower where the plate takes the whole head (the flow at a fixed head scales as K^(−1/2)); for β up to 0.6, 0.64 % and 0.84 % in K, 0.32 % and 0.42 % in flow; Reader-Harris et al.'s L2′ = 0.125 gives a K 0.063 % (β 0.1, Re_lo) to 1.24 % (β 0.726, D ≥ 71.12 mm) lower, a flow up to 0.63 % higher. `test_the_named_departures_are_stated_at_their_largest_over_isos_range` recomputes each from fluids and finds it in the methods text and the trace notes. The choice of Q3 is unchanged.
42. **The trace** cites WANDA for the hold only where eq. (4) is used (an entered C without a move has no Re_lo and no hold; it cites WANDA for the vena contracta's elevation alone), says that the L2′ = 0.125 alternative's C and K are "shown above" only where a solved flow shows them (a closed-off plate has the note without it), and shows the Borda–Carnot bound, (1/β² − 1)², K at C = 1, with its equation and `RENNELS` (`test_the_trace_names_only_the_hold_and_alternative_the_plate_has`).
43. **SDD §4.16**, not §4.15, in the docstrings of `models/components.py` (`Orifice` and the module) and `models/results.py` (`OrificeResult`); `openapi.json` and `schema.d.ts` regenerated with `pnpm gen:types`.
44. **Numbers.** Item 14's loop is 1.63 mm (1.625879 mm at `ORA:inlet`, re-measured), not 1.62 mm. The gate counts below and the bundle sizes (item 38, TSD §8.3) are the final gate's, on the tree with items 39–49.
45. **Goal seek's default boxes keep decision 17 (c) without a solve** (§6 W6; the web review's findings that a default box could be a bounds 400). W6 capped a C at corner or flange taps at 0.99/r̂, r̂ the last solve's ratio, but r̂ can be below r_max (a flange plate whose ISO C is held: C_L/C_M 0.9795 against r_max 1.0018 on 52.5 mm at β 0.7), a plate not solved yet or edited since has none, and a bore box under an entered C at those taps had no cap (an entered C of 0.98 at corner taps on NPS 4 gave an upper bound of 0.75 D, which the API refuses). The web now computes r_max itself (`utils/orifice-bound.ts` `movedRatioBound`, a term-by-term transcription of the API's `ratio_range`, `c_range`, `tap_difference` and `rhg_terms_at`, eq. (4) as fluids 1.3.1 computes it), from the plate's D, d and taps alone. A C's upper bound at those taps is at most max(0.99/r_max, the case's entered C); without D, the entered C (a box [v/2, v]) or, on ISO's C, 0.99/`RATIO_BOUND_ANY` = 0.99/2.05, above the largest r_max of any plate the API builds on ISO's C (2.04451, corner taps as D → 0 at β 0.9706); the lower bound is halved where the cap falls to it. A bore box on an entered C at those taps keeps C·r_max at most max(0.99, the case's own, below 1 − 10⁻⁹) at each bound, moved toward the case's bore by bisection where it would not; the case's own value is always in the box. This copies an API rule, against D10's "read, never copy", only to pre-fill defaults (the API still decides): `orifice-bound.test.ts` pins it to the API's printed `ratio_range` on 45 plates within 10⁻¹² relative (`testing/orifice-r-max.ts`), and `apps/api/tests/unit/test_web_orifice_r_max.py` (final gate) checks those printed values, and `RATIO_BOUND_ANY` against every plate the API builds on ISO's C from D 0.1 mm to 10 m, with the API as it is now, so a change to the bound fails while the copy is stale. Checked against the real API by the web fixer: 92,160 default boxes (every tap set, D 52.5 mm–1 m, β 0.02–0.97, ISO's C and 9 entered values, both variables, with and without D) have no bound the API refuses (563 bore boxes shrink to the case's bore, all with an entered C of exactly 1.0, where Run asks for From below To), and of 385 goal seeks posted with the web's boxes 381 gave 200, 4 gave 422 (plates refused on their own) and none 400.
46. **D and the plate's result are never an out-of-date solve's in goal seek** (`currentOrificeResult`, `orificePipeDiameter`): D is the inlet pipe's inner diameter as the case is now (the form's resolver, `inletBore`), else a current solve's `pipeDiameter`; the C that a box or "Now" centres on is read only from a converged solve that is not out of date. W6 put the last converged solve's D first, which after a pipe edit could belong to another pipe.
47. **"Now" for a C on ISO's default** names where its number is: "at D and D/2 tappings" for a plate without taps, "at the plate's taps" otherwise (it said the plate's taps for every plate).
48. **A value near its flag limit reads apart from the limit** (`units.ts` `digitsApart`, 4 to 17 significant figures, moved from `design-checks.ts`, whose texts are unchanged): `flag-text.ts`'s orifice texts use it for the bore, the pipe bore, β, the laminar Reynolds number and the outlet bore, so β 0.7500489 reads "0.75005 is above … 0.75" and a bore of 0.0124999 m "12.4999 mm" (0.49212 in), where four figures read as the limit itself.
49. **The web reads rule (b)'s three bases** (final gate; item 40 had left it to the web side). `issue-text.ts`'s `ORIFICE_ISO` stopped matching once the API inserted the basis, so the server's words were shown. It now reads the tap set, the basis and the largest C, and words each basis with the server's reason and remedy: the loss (a jet larger than the bore, then either "or enter a discharge coefficient (ISO 5167-2's C at D and D/2 tappings, used as entered)" or, at corner or flange taps, why an entered C would be refused the same way), only the reading (eq. (4) extrapolated far beyond ISO's range; a smaller bore, D and D/2 taps or no taps) and the move (give the C at D and D/2 tappings); a reason or remedy in another form keeps the server's words. `orifice.test.ts` pins the four messages the API builder printed for these plates (O1 on NPS 4 without taps and with corner taps; flange taps on 26.6 mm with ISO's C and with an entered 0.6) and fails on the earlier parser.

**Proof** (§7.5; TSD §10.4 has the full record)

- **Reference suite:** 2,116 passed, with the 15 orifice cases (12 closed-form, 3 EPANET); no solver or derivation change was needed, and no expected value was changed after running the solver. The closed-form cases agree within 5.7×10⁻¹⁶ in flow and 5.3×10⁻¹⁵ m in EGL; the suite's transcription of eq. (4) equals fluids' within 10⁻¹³ relative and the solver's C, r and p_vc agree with it to about 10⁻¹⁶; every printed value of §7.1 is reproduced within 10⁻⁹. Spot checks against §7.1: C12's Q 0.021312277409, r 1.021059944023, C_L 0.61263596641, K 2.56452110, Δp 20,172.3465 Pa and p_vc −13,508.325 Pa; C8's loop 0.010175668443 and 0.013362193845; C9's bypass 0.002543446581. The calibration identity holds within 10⁻¹⁰. After the review (item 39): 2,142 passed, with 17 orifice cases (14 closed-form, 3 EPANET); the fourteen closed-form cases agree within the same 5.7×10⁻¹⁶ in flow and 5.3×10⁻¹⁵ m in EGL.
- **Corpus comparison** against `b6e2088`, with system curves: identical 5,151, different 0, with `--ignore-empty orificeResults` (5,151 values in 5,151 projects) and the two method-version paths (5,151 each); the 15 orifice cases are only on the branch. After the review, the branch dumped again (5,168 projects, 531 s with 3 workers) against the same `b6e2088` dump: identical 5,151, different 0, with the same ignores (5,151 values each), the 17 orifice cases only on the branch.
- **`scenario_check`** (5,166 projects): 4,721 solved, 445 invalid in both, 119 system curves, 0 different; the orifice cases 14 solved, 1 invalid, 61 overrides. **`orifice_check`**: mode `entered` 1,464 valves in 1,220 projects (317 kept), mode `iso` 1,698 valves in 1,358 projects (1,239 held, 293 varying, 1,277 tapped, 7 untapped; 83 kept), 0 different in both, the largest differences 7.33×10⁻¹⁰ and 9.26×10⁻¹⁰ of the largest flow and 6.71×10⁻⁶ m and 3.54×10⁻⁶ m. **`equipment_check`**: 1,781 valves in 1,414 projects, 0 different. **Fuzz:** 0 critical in each profile, the 9,000 records identical to `b6e2088`'s. **`missing_result_check`:** the baseline on both trees. **`goal_seek_check`** (5,166 projects, 63 min): 19,128 draws, 15,462 ran, 0 violations, 0 errors, 72.1 % met (95.0 % of interior targets); the orifice cases 60 draws, the bore varied 25 times and the C 20 times, all four goals drawn. After the review, on the 17 orifice cases (`--only ref_orifice` and `--only ref_epanet_orifice`): `scenario_check` 16 solved, 1 invalid in both, 1 system curve, 0 different; `goal_seek_check` 68 draws, 67 ran, 0 violations, 0 errors.
- **Gates on the integrated tree** (the final gate, with items 39–49): API `uv run pytest` 5,627 passed (5,625 at the review's run, plus `test_web_orifice_r_max.py`'s two); ruff, ruff format (182 files), mypy strict (58 source files) and `generate_pipe_data.py --check` clean; `pnpm gen:types` stable (`openapi.json`, `schema.d.ts` and every `__fixtures__` file unchanged when regenerated). Web `pnpm check` 0 errors and 0 warnings (756 files), `pnpm lint` clean, `pnpm test` 1,217 passed (95 files), `pnpm test:e2e` 157 passed and 7 skipped by design (164: each skipped test a check for the other viewport), the four `orifice` flows passing on desktop and on the phone.
