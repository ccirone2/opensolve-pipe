# Pressure relief valve: design proposal

**Status: built** (2026-10-29; CLAUDE.md D22, `METHOD_VERSION` 1.5.0; §12 records where the build departs from this design). The owner answered its questions on 2026-10-28 (§10). Written on 2026-10-28 against `b7f09eb` (D20 merged) by a design workflow. Three designers worked from their own angles, with prototypes: one on the physics, model and solver (**P**), one on the sources and verification (**V**: citations read, closed-form cases, EPANET runs, a corpus pilot), and one on the web (**W**). A synthesizer (**S**) merged their designs into this one, recomputed the disputed numbers in code (the **S** checks, §7.7) and wrote this document. Two reviewers then checked it against the sources and the code, and a reviser (**R**) verified each finding, revised the design at the root and measured what changed (the **R** checks, §7.7); §11 records every finding, upheld or rejected. §1.3 lists where the designs disagreed and why this design chose as it did. §10 holds the product questions for the owner, each with the default the build uses unless the owner says otherwise.

**The owner's request (2026-10-28):** "Pressure relief valve: a relief valve with a set pressure and a capacity sized by API 520 (fluids' API520_A_l), discharging to atmosphere or to a return. It protects a pump's discharge. A new solver element, verified like D18 and D20 (reference cases, corpus proofs). The steady-state model between set pressure and full lift needs the owner's answers first."

D1 lists relief valves as Later for the solver, D5 defers them, and PRD §3.1.2 has "Pressure Relief Valve | Setpoint, capacity | Later". This slice moves the liquid relief valve into v1. Gas, steam and two-phase relief, balanced-bellows and pilot valves, pop action and blowdown stay Later (§9).

The workflow had already decided these points, which were not re-opened:
- D1–D20 are binding.
- The work is one verified slice; anything bigger goes in §9.
- Liquids only (every fluid in the app is a liquid).
- The change touches the API, so it does not go on a `web/` branch (CLAUDE.md, Tooling).

Every other choice is the designers' own and reversible under D14.

**Sources read:**
- **Specs:** GOALS §3–§6; CLAUDE.md D1–D20; PRD §3.1.2; `docs/proposals/orifice-plate.md` and `equipment-pressure-drop.md`, the precedents this design follows.
- **API code** at `b7f09eb`: `models/{components,results,goal_seek}.py`; `services/solver/{elements,builder,status,system_curve,results,flags,gga}.py`.
- **Web code:** `components/panel/kinds.ts`, `utils/{factory,compare,validate}.ts` (W read the rest, listed in §8).
- **Cited sources:** §3.10 says what each supports and how it was verified.
- **Prototypes and logs** are in the workflow's scratchpad (`relief-design/`, not committed):
  - physics: `relief_law.py`, `proto_deadhead.py`, `proto_more.py`, `proto_edges.py`, `proto_epanet.py`, `api520_identity.py`, `band_root_check.py`, each with its `*.out.txt`;
  - sources: `laws.py`, `fluids_checks.py`, `cases.py`, `r7c.py`, `epanet_proto.py`, `sizing_inverse.py`, `relief_check_pilot.py`, `corpus_survey.py`, each with its `*.out.txt`, and the downloaded Pentair handbook and Trimeric paper (`dl-handbook/`, `dl-trimeric/`);
  - web: `e2e_values.py`, `measure_p.py`, `schema_trim.py`, `schema-trim.plugin.ts`, with their outputs;
  - synthesizer: `synth/law.py` (the law this design chooses, which the other scripts import), `harness.py` (the real solver with that law placed in a check valve's link, status code unchanged), `s1_law_checks.py`, `s1b_slope.py`, `cases.py`, `gs.py`, `e2e.py`, `relief_check_pilot.py`, `relief_check_pilot_open.py`, `relief_check_closed.py`, `triage.py` and `triage_closed.py`, each with its `*.out.txt`;
  - reviewers: `review-1/` (`indep.py`, an independent transcription and closed forms of C1–C9 and G40–G44; `fig412.py`, `op_basis.py`, `root_bigop.py`, `epanet_check.py`, `edge.py`, and the rendered page of Fig. 4-12, `fig/q-046.png`) and `review-2/` (`closed_loop_probe.py`, `check_cracking_reading.py`, `q1d_check_valve_fit.py`), each with its `*.out.txt`;
  - reviser: `reviser/alt_laws.py` (the other band laws in the harness's shape), `measure.py`, `falling.py`, `closed_loop.py`, `certified.py`, `oneshot.py`, each with its `*.out.txt`, and `proposal-before-review.md` (this document before the review).

**Test inputs.** Every pipe, level, set pressure, valve size and fluid in the cases below is a made-up test input, entered as the user's data, unless a source is named. Every result number was measured by the prototype named next to it.

---

## 1. Scope and decisions

### 1.1 Scope

This slice adds one new two-port component, `relief_valve`, inlet → outlet: a conventional spring-loaded pressure relief valve in liquid service. It is closed while the pressure difference across it is below its set pressure, lifts in proportion to the overpressure, and is fully open from set plus overpressure on. The user enters:
- its **set pressure**, a pressure difference, inlet minus outlet (required, no default);
- its **capacity** (required, no default), one of three kinds, never mixed:
  - an **API 526 orifice letter**, or an **API 520 effective area**, each with API 520's effective coefficient of discharge 0.65 and ASME's liquid certification overpressure (10 % or 3 psi, whichever is greater), for preliminary sizing: API 520's own values, never changed;
  - the valve's **certified** actual orifice area with its rated coefficient of discharge and, optionally, the overpressure at which it reaches full lift (default: ASME's);
- its **status**: active, or locked closed.

ASME's default overpressure exists only for a set of at least 15 psi (103,421.36 Pa), ASME VIII's scope; below it the overpressure must be entered, on a certified capacity (decision 6).

Discharge to atmosphere is topology: the outlet pipe ends at a reference node at 0 kPa(g), which the web offers to add at a relief valve's free outlet (decision 9). A return line is any other connection.

The law, on Δp_t, the total-pressure difference between the ports (decision 5):

```
Δp_t = (p_in + ρ v_in²/2) − (p_out + ρ v_out²/2) = ρ g (h − (z_in − z_out)),   h = EGL_in − EGL_out
x    = clip((Δp_t − Δp_s) / (Δp_f − Δp_s), 0, 1)        lift; Δp_f = Δp_s (1 + op)
Q    = x · C · √(2 Δp_t / ρ),   C = Kd · A               API 520's liquid equation (Kw = Kc = Kv = 1) at lift x
```

Inverted for the GGA, for Q ≥ 0:

```
h(Q) = h_set + (Δp(Q) − Δp_s) / (ρ g),   h_set = Δp_s / (ρ g) + z_in − z_out
band (Q < Q_f):   u = √Δp is the largest real root of u³ − Δp_s u − R Q = 0,   R = (Δp_f − Δp_s) / (C √(2/ρ))
                  Δp − Δp_s = R Q / u   (no cancellation),   dΔp/dQ = 2 u R / (3u² − Δp_s)
full lift (Q ≥ Q_f):   Δp = ρ Q² / (2 C²),   Q_f = C √(2 Δp_f / ρ)
```

The status rule is the check valve's (EPANET 2.2 cvstatus) with its cracking head set to h_set, so the element joins every rule of `status.py` and `system_curve.py` without a new rule or tolerance (§3.4). Its h_set holds the ports' elevation term, so it opens on the static pressure difference; today's check valve compares its cracking pressure with the EGL difference instead (§3.4, §1.3 item 15).

**Not in this slice** (Later, §9): balanced-bellows and pilot valves (set on the inlet's gauge pressure), pop action, blowdown and chatter (the falling branch of the lift characteristic), a manufacturer's pressure–flow curve, API 520's viscosity correction Kv and back-pressure correction Kw, rupture-disc combinations (Kc), non-certified valves (API 520's Kd 0.62 with Kp), a nameplate rated capacity, a one-shot required area on every result, gas, steam and two-phase relief, a one-port valve discharging to atmosphere, a failed-open status, relief design checks, a fuzz profile, and the web's Summary card and discharge choice at creation.

**Deliberate departures, named** (as D9 names its departures from EPANET), each stated in the methods summary and the trace:
- **The band between set and full lift is a convention, not the cited behaviour.** API 520 and ASME certify one point, the capacity at set plus overpressure. The one lift characteristic read is Pentair's "Typical Relief Valve Lift Characteristic" (TP-V300 ch. 4, Fig. 4-12, p. 4.8), a schematic for a liquid trim:
  - almost no lift up to the set, then about half lift at 107 % of set;
  - a surge to full lift there ("a surge, or gush, of liquid flow … with less than 10% overpressure and full lift");
  - on falling pressure, full lift down to about 95 % of set, reclosing near 90 % ("a fixed blowdown that will allow the device to reclose at approximately 10% to 15% below set pressure").

  So between about 90 % and 107 % of set it has two steady states. This design's law is the linear lift, the convention of two established simulators (MathWorks Simscape, AFT Impulse), exact at the certified points. It lies inside the figure's hysteresis loop up to 70 % lift and above its rising branch beyond. Measured with the real solver (§7.7, R1):
  - **the rising branch** (with a chord across its surge, alternative (f)) puts the inlet 0.31–0.73 % of set higher on network M, with 4.5–19.4 % less flow. It is 0.78 % higher on C6 (1.4 % less flow) and 0.88 % higher on W's e2e network (6.6 % less flow);
  - **a valve that has surged open** sits on the falling branch: its inlet is 3.4 % (C2), 6.5 % (W's e2e network) and 12.0 % (C6) of set lower, with 19–85 % more flow (D13: a significantly different state, which the solver does not search for).

  Every relieving state short of full lift is flagged (`CORRELATION_OUT_OF_RANGE`, warning, decision 15). No cited source verifies any band law, so shipping one is an exception to GOALS §5's Verifiable gate and §4.1. It goes to the owner (Q1) and is recorded in D22. The band's reference cases verify the implementation of the law chosen, not the law.
- **API 520's P1 − P2 is read as the total-pressure difference between the ports** (decision 5). ASME's definitions, as Pentair quotes them, put the capacity on the inlet stagnation pressure and the outlet static pressure. That reading differs by the outlet pipe's velocity head. Measured at full lift (S1e, test inputs):
  - 4.60 % of the pressure difference for API 526's T orifice on an 8 × 10 Sch 40 body, 4.32 % for R;
  - 2.06–2.12 % for L, P and Q, and 1.28 % for J;
  - below 1 % for the others.

  This design's reading is on the safe side of it: a higher inlet pressure at a given flow.
- **With a superimposed back pressure, the overpressure is taken on the set difference.**
  - *What the sources fix.* ASME's and API's overpressure is "a pressure increase over the set pressure", the set being the inlet static pressure (Pentair ch. 2). API 520's P1 is set plus overpressure (fluids' `API520_A_l` takes P_set = (P1 − atm)/(1 + overpressure), for Kw). The certification fixes full lift only on the bench, discharging to atmosphere, where the two coincide.
  - *What this design infers.* It keeps the lift on the pressure difference, as the opening is ("for every one unit of superimposed back pressure … it will add one unit to the in situ opening pressure"; on an open valve built-up back pressure "will assist in reseating the valve as additional downward force is applied on the top of the disc holder", Pentair ch. 4). For full lift this is an inference, named.
  - *Its consequence.* With a superimposed back pressure P_b, full lift comes at an inlet op·P_b below the in-situ relieving pressure, (1 + op) × the gauge set. On C6 that is 383.04 against 385.00 kPa(g). In the band C6's inlet is 1.43 kPa (0.41 % of set) lower, with 0.73 % more flow, than with the overpressure on the gauge set (R2).
  - *Where the readings agree.* At the relieving pressure both are at or past full lift and give API 520's equation: the same flow (R2), and the same size from a goal seek (G41).

  Owner question Q4.

### 1.2 Decisions

Origin key: **P** physics designer, **V** sources designer, **W** web designer, **S** synthesizer (resolving a disagreement, §1.3, or adding what the designs missed), **R** reviser (after the review, §11).

| # | Decision | Reason | Source | Origin |
|---|---|---|---|---|
| 1 | **One component type `relief_valve`** (`ReliefValve`), ports `inlet` → `outlet` (`x-port-ids`, `x-port-roles`), two-port only. Not a `valveType` of `type: "valve"`. | Its inputs (a set, an overpressure, a capacity) and results (lift, capacity, overpressure) share nothing with the isolation, check and control valves but two ports; as a valve type it would need a `ValveResult` whose `kOpen`, `setpoint` and `setpointAchieved` mean other things, and a second result per element. D18 and D20 are the precedent, and the web already treats `{type: 'valve', valveType: 'relief'}` as an unknown schema (`model-rules.test.ts`). The solver puts it in `built.valves` all the same (decision 10), so the status code needs no second map. | D18, D20 | W over P (§1.3 item 3) |
| 2 | **A conventional spring-loaded valve: the set pressure `setPressure` is a pressure difference, inlet minus outlet static, at which the valve starts to open.** Discharging to atmosphere at the valve's elevation (the open discharge the web adds), it is the gauge set pressure; against a constant back pressure, the bench setting (the cold differential test pressure without its temperature correction). Back pressure adds to the inlet pressure at which the valve opens, and (an inference, named in §1.1) at which it reaches full lift. | A conventional valve's spring sees the difference: "for every one unit of superimposed back pressure … it will add one unit to the in situ opening pressure", and Pentair's pump example: a valve that must open at 100 psig with 25 psig at the pump suction is set at 75 psig on the bench. A difference keeps the law a function of the valve's own flow, so the check valve's rule applies with its cracking head. Balanced-bellows and pilot valves follow the inlet's gauge pressure; that needs new level-dependent rules (§9). Owner question Q2. | Pentair TP-V300 ch. 4 (bench setting, CDTP, back pressure on the disc); AFT (conventional on the differential) | P; S over V (§1.3 item 2) |
| 3 | **Between set and full lift the lift rises linearly with the overpressure** (§1.1), full lift at Δp_f = Δp_s(1 + op), API 520's full-lift equation beyond. A convention, named as a departure from the cited typical characteristic and flagged in the band (decision 15). | Exact at the two points the certification fixes (closed at set; rated capacity at set plus overpressure); continuous and strictly increasing with a finite positive slope at zero flow, so one steady state and no Jacobian floor; an exact closed form for the trace; the model of two established simulators, so engineers can reproduce it (GOALS §2). Pentair's Fig. 4-12 differs (§1.1). Owner question Q1, with every alternative's measured consequence and the GOALS §5 exception. | Simscape "Pressure Relief Valve (IL)"; AFT Impulse (set to overpressure); API 520 via Technical Toolboxes (capacity varies with lift up to full lift); Pentair Fig. 4-12 (the typical characteristic it departs from) | P, V (law C), W; R (the departure); owner |
| 4 | **The full-lift equation in exact SI, Q = Kd·A·√(2Δp/ρ)**, not with API's rounded constant 11.78. | fluids gives it as API 520's "raw expression in SI units"; ρ0 and G1 cancel. API's 11.78 is +6.092144×10⁻⁵ above the exact 11.779282389196 (S1f, every letter), which the trace states. A reference test pins the identity to `API520_A_l`. | fluids 1.3.1 `API520_A_l` | P, V |
| 5 | **API 520's P1 − P2 is read as Δp_t, the total-pressure difference between the ports** (the EGL drop less the ports' elevation term). At zero flow it is the static difference, so the opening point is exactly the set. | The EGL is the nodal unknown (D7), and D18 and D20 read their laws on it. Δp_t keeps h(Q) strictly increasing for every pipe size, while the static reading needs a refusal when the outlet pipe is smaller than the inlet, and the definitions' literal reading (inlet stagnation, outlet static) cannot keep the band monotone for an API 526 T orifice on an 8 × 10 Sch 40 body (test inputs) at ASME's 10 % (margin −0.0025, S1e). It sits between the two, on the safe side of the literal one (§3.2). The trace shows both other readings, not used. | Pentair ch. 2 (definitions); D7 | S over P and V (§1.3 item 1) |
| 6 | **The overpressure `op` at full lift: ASME's liquid certification overpressure, max(10 %, 3 psi/Δp_s), labelled "default" (D10), for a set of at least 15 psi; a number only on a certified capacity.** 3 psi = 20,684.27 Pa; the default is then in [0.1, 0.2]. A letter or an effective area always takes ASME's: API 520's effective coefficient 0.65 is for valves certified to reach rated capacity by that overpressure, so another overpressure with it is the mix decision 7 forbids. A certified capacity takes an optional `overpressure` in (0, 1], user data: the overpressure at which that valve reaches its rated capacity, from its certification. It is not the allowable accumulation a valve is sized for (10, 16 or 21 % above the MAWP in ASME VIII, Pentair ch. 3). Below 15 psi (103,421.36 Pa) the set is outside ASME VIII's scope and the default is not cited: a letter, an effective area, or a certified capacity without an overpressure is refused (decision 14). The fraction is of the set difference (§1.1). | GOALS §4.1: a cited default, and none where no source gives one. "The steam, gas, or liquid capacity tests are performed with 10% or 3 psi [0.207 bar] overpressure", "rated capacity is obtained with a maximum of 10% overpressure"; "outside of the scope of ASME (below 15 psig)". The test is on the set difference, which never exceeds the in-situ set, so the default is never applied outside ASME's scope; it can refuse a valve on a high back pressure that lies inside it, with a remedy. Within these bounds op ≤ 1 everywhere, the range S1b verified. Owner question Q4. | Pentair ch. 2 (overpressure), ch. 3 (certification, accumulation), ch. 4 (liquid trim), ch. 5 (scope); Technical Toolboxes (certification at 10 %; Kd 0.62 at 25 % for non-certified valves) | P, V; R (scope, placement) |
| 7 | **`capacity`, a union on `kind`:** `{kind: 'api526', letter: D…T}` (the API 526 effective area of the letter) or `{kind: 'effective', area}` (an API 520 effective area), both with **Kd = 0.65 fixed** and ASME's overpressure, labelled "preliminary"; or `{kind: 'certified', area, dischargeCoefficient, overpressure?}`, the actual area and the rated coefficient, both required. The result names, for an effective area, the smallest API 526 letter that covers it (fluids' `API520_round_size`). | "IN NO CASE SHOULD AN API EFFECTIVE COEFFICIENT OF DISCHARGE OR EFFECTIVE AREA BE USED WITH THE RATED COEFFICIENT OF DISCHARGE OR ACTUAL AREA": an editable Kd on a letter invites that mix. The effective pair understates a real valve: for one series the rated K·A is 1.138–1.141 times the effective pair, letter by letter (V). The effective area is what `API520_A_l` returns, so goal seek on it sizes a valve by API 520 against the network (G41) without putting 0.65 in the certified kind. Owner question Q3. | fluids `API520_A_l` ("0.65 normally"), `API526_A`, `API520_round_size`; Pentair ch. 5 (the rule; K = 0.9 Kd), Table 7-6 (V); Trimeric | P over W (§1.3 item 6); R (effective kind) |
| 8 | **`status`: `active` (default) or `locked_closed`** (gagged, or isolated by its block valve), the check valve's vocabulary. | A scenario can show what the pressure reaches if the valve does not open. Failed open is Later. Owner question Q5. | — | P, W |
| 9 | **Discharge to atmosphere is topology.** At a relief valve's free outlet the web offers "Discharge to atmosphere" beside "Plug this port": an open discharge, a reference node at 0 kPa(g) at the valve's elevation, reached by 1 m of pipe sized to the port with an `exit` fitting. | Its friction is solved as built-up back pressure; the exit makes the pipe end's static pressure exactly 0 (D7, D10); no new kind of boundary for D1's rule. One action on one surface, as `plugPort`; a choice at creation is Later (§9). Owner question Q6. | — | W over P (§1.3 item 7); R (one surface) |
| 10 | **The status rule is EPANET 2.2 cvstatus with h_c = h_set**, through a new `ControlKind` `"relief"` that takes the check branch at each of `status.py`'s five check sites, plus `RULES` and `KIND_NAMES` entries. No new tolerance (Htol, Qtol). | At zero flow h − h_set = (p_in − p_out − Δp_s)/(ρg) exactly, so "opens when the static difference exceeds the set by ρg·Htol" is the rule as written. Every closed-off, free-level, disconnected-section and system-curve rule then applies as to a check valve (§3.4). | EPANET 2.2 hydstatus.c (in `status.py`) | P |
| 11 | **The valve starts CLOSED**, its normal state. | A pump deadheaded behind a valve set above its shutoff: started open, the pump and valve close together and the discharge has no pressure (D9's zero-flow multiplicity); started closed, the pump runs at zero flow and the inlet reads the shutoff pressure (S2, C7). Over the corpus, the closed start matched the "valve shut" answer in 799 of 870 projects against 679 for an open start (S6). Only relief valves are affected. | — | P; S measured |
| 12 | **Zero and reverse flow.** The slope at 0⁺ is R/(√Δp_s·ρg), finite and positive. For Q < 0 Newton sees the odd extension about h_set; the rule closes the valve on reverse flow, so no reverse law is used. | As the check valve's h_c + K Q\|Q\|. | — | P |
| 13 | **Computed without cancellation:** the increment Δp − Δp_s = RQ/u, and the lift reported as x = Q/(C√(2Δp_t/ρ)). | (Δp − Δp_s)/(Δp_f − Δp_s) loses digits at a small overpressure (S1a: a round trip off by 4.6×10⁻¹⁰); the root and slope are exact to 8.2×10⁻¹⁶ against a 60-digit solve for op ≤ 1 (S1b), the whole range decision 6 allows. | — | S |
| 14 | **Topology issue `RELIEF_VALVE_OUT_OF_RANGE`** (422, after `ORIFICE_OUT_OF_RANGE`, one per valve, quoting the values and the basis): C, Q_f or R is not a finite positive normal double (as built also C² and the band root's scale, §12 item 41); or the set is below 15 psi where the overpressure would be ASME's default (decision 6), with the remedy (the valve's certified area, coefficient and overpressure). No refusal on geometry. | D18's rule for a law the floating point cannot represent, and D20's for a value no cited source gives there. With decision 5 the law is monotone for every pipe size, so P's two geometric refusals are not needed (§1.3 item 8). Each basis is monotone in each relief variable alone, so goal seek's two bound builds prove every trial builds (decision 19). | D18, D20 | S over P; R (scope) |
| 15 | **Flags:** `RELIEF_VALVE_OPEN` (info, new code) on a valve at full lift; `CORRELATION_OUT_OF_RANGE` (warning, `limit: 'partial_lift'`) on a valve relieving short of full lift; `RELIEF_VALVE_CLOSED` (info, new code) on an active valve that ends closed with no result (a closed-off or floating side), saying why; `BELOW_VAPOR_PRESSURE` (invalid) on the component while relieving with the outlet's absolute static pressure ≤ the vapor pressure (≤ 0 Pa for a fluid without one); `CORRELATION_OUT_OF_RANGE` (warning, `limit: 'viscosity'`) while relieving with μ ≥ 0.1 Pa·s. No flag for a closed valve that has a result (its state says so), for flow beyond full lift, or for chatter. | Partial lift rests on a convention that the cited characteristic contradicts, with a second steady state (§1.1): GOALS §4.6 flags operation outside a correlation's validated range, as D18 and D20 do. Info: "a state worth knowing" (`flags.py`), as `CHECK_VALVE_CLOSED` is for a check valve in the same place. Flashing: the jet leaves at the back pressure, so a liquid below its vapor pressure there flashes and the flow solved is too high (GOALS §4.6). Viscosity: API 520 10E's Kv is not applied, and API recommends Kv = 1 below 0.1 Pa·s (as fluids documents it); Kv at the solved flow is in the trace. Beyond full lift API's equation holds; a limit on it is design practice (D19, §9). | `flags.py`; fluids `API520_Kv`; Pentair Fig. 4-12 | P; S; R (the band warning, the closed flag) |
| 16 | **`ReliefValveResult` in `SolvedState.reliefValveResults`**, always present (`{}` without relief valves or when the solve did not converge). No `ValveResult`. A valve with a closed-off or floating side has no result, as a check valve, and `RELIEF_VALVE_CLOSED` says why. | D18's and D20's rule; one result per element. | — | W over P; R (the flag) |
| 17 | **A trace per valve; a "Relief valves" methods section after Valves and one assumption, only with a relief valve.** | GOALS §4.2; D12, D18 and D20 keep projects without the element unchanged. | — | P, W; S (position) |
| 18 | **Scenario allow-list:** `status`, `setPressure`, the whole `capacity`, `capacity.letter`, `capacity.area` (effective or certified), `capacity.dischargeCoefficient` and `capacity.overpressure` (certified; null for ASME's default). A value the base's kind does not hold is `not_applicable`. A base switch between kinds removes the scenarios' changes of the other kind's values; between effective and certified it removes the `capacity.area` changes too (an effective area is not an actual area, as D18's Cv is not a Kv). | D15, and D18's whole-and-part rule. | D15, D18 | P, W; R (kinds) |
| 19 | **Goal seek:** variables `setPressure` (linear), `capacity.area` (log; effective or certified), `capacity.dischargeCoefficient` (linear; certified), `capacity.overpressure` (linear; certified; on the default, the start is the middle of the bounds); goals `relief_valve_flow` and `relief_valve_pressure_drop`; the inlet's pressure is the existing port static-pressure goal. The network is built at each bound of a relief variable (D20's pattern). Sizing is the effective area for the inlet at the relieving pressure (G41). | D16: every numeric allow-list value is a variable, goals are Compare's rows. Decision 14's tests are monotone in each variable alone, so the two builds prove every trial builds. | D16, D20 | S, from P and W; R (kinds, G41) |
| 20 | **Compare:** rows `reliefFlow` (relative), `reliefState`, `reliefInletPressure`, `reliefSetRatio`, `reliefPressureDrop`. Every comparison shows each relief valve's flow, state and inlet pressure by default, right after the pumps' rows, before the changed elements (so the 40-row limit cuts changed elements first). | A relief valve's relieving cases come from changing other elements (a blocked discharge), so D18's "changed elements only" would hide the answer; the lift and flow ÷ capacity stay in the view and the export. | — | W; R (rows, order) |
| 21 | **Export:** a "Relief valves" sheet after Valves, holding the capacity each solve used. | D17; the view's position (decision 17). | D17 | W |
| 22 | **No design check** in this slice: overpressure, built-up back pressure and inlet-loss limits are Later D19 extensions, each once its source is read. Owner question Q7. | GOALS §4.6: design practice is opt-in, and none of the limits was read in its standard. | — | P, V, W |
| 23 | **`METHOD_VERSION` 1.5.0**, one changelog line; `schemaVersion` stays 1. | GOALS §4.3; 1.4.0 is deployed; an additive type (D14). | — | P |
| 24 | **EPANET mapping:** a GPV whose HEADLOSS curve tabulates the relief's EGL law at Q = 0 (h_set), at Q_f and at 201 evenly spaced flows, in series with its inlet pipe as an EPANET CV pipe. | EPANET has no relief valve; the CV closes it below set and on reverse flow. Q_f is a point because the slope steps up there (S1c): a case on it misses by −3.8×10⁻⁴ without it and +1.4×10⁻⁵ with it (review-1, `epanet_check`, re-run by R). Measured within 1.7×10⁻⁴ (§7.2). | — | P, V; R (Q_f) |
| 25 | **No fuzz profile;** `relief_check` runs over the whole corpus instead, in three modes with an exact expected answer each (§7.4). | Its open modes place 733 relief valves (368 reversed) on corpus networks, 0 different started open and 3 explained started closed; its closed mode 870 more. A profile would add EPANET's tolerance on new topologies for its upkeep (GOALS §5). | — | S over V (§1.3 item 9) |
| 26 | **Web:** "Pressure relief valve (API 520, liquids)" in a group "Relief valves: overpressure protection, liquids" after Control valves; id prefix `RV`; never abbreviated PRV or PSV; the PSV form's hint and the check valve form's hint point relief users to it. Owner question Q8. | In this app PRV and PSV are EPANET's pressure-reducing and pressure-sustaining valves; process engineers say PSV for a safety valve. Users model relief today with cracking check valves, which beyond the flow their K was fitted to understate the inlet pressure API 520 gives (Q1 (d)). | — | W; R (check valve hint) |
| 27 | **`x-relief-data`** on the capacity schema: API 526's letters with their effective areas (m²), the 15 psi scope bound and the 3 psi floor, read from `data/api526_orifices.json`, which `scripts/generate_relief_data.py` writes from fluids (`API526_letters`, `API526_A_sq_inch`, `API526_A`) with a citation per entry and a `--check` mode, as D8's pipe data. | The web reads the letter table and the bounds instead of copying them (D10); a library change shows up as a diff in the JSON, which a unit test regenerates and compares (`test_relief_model.py`), not a schema pinned to fluids at run time. | D8, D10 | P, W; R (data file) |

### 1.3 Where the designs disagreed

1. **Which pressures API 520's P1 − P2 reads.**
   - P: static at both ports (API's P1 is set plus overpressure, and set is a static pressure; the highest inlet pressure at a given flow). V: three forms, static, EGL and stagnation-in/static-out, and the owner to name one; ASME's definitions as Pentair quotes them give the third ("Flow Rating Pressure: the inlet stagnation pressure at which the relieving capacity … is measured"; "Back Pressure: the static pressure existing at the outlet"), which also answers P's open item on the test's pressure convention.
   - This design takes the total-pressure difference (decision 5). The literal reading cannot keep h(Q) increasing in any band where the outlet velocity head at full lift exceeds op/(2 + 3op) of the difference: S1e finds T on 8 × 10 Sch 40 at −0.0025 and R on 6 × 8 at +0.0003 at ASME's 10 %. The static reading needs P's refusal for an outlet pipe smaller than the inlet. The total-pressure reading is monotone for every geometry (margin op/(2 + 3op), S1d), is the reading D7, D18 and D20 use, and lies between the two: it departs from the literal reading by the outlet velocity head ((C/A_out)² of the difference, ≤ 4.60 % at full lift on S1e's bodies) and from the static one by (C/A_in)² − (C/A_out)² (≤ 8.63 %). On C2's partial lift the literal reading would pass 0.418 % more flow at the same pressures and the static one 1.609 % less (S2).
   - This is a physics reading, decided here (GOALS §3: a unique, verifiable answer first), with the alternatives shown in every trace. It concerns which pressures P1 and P2 are; the reference of the overpressure is a separate inference (§1.1, Q4).
2. **What the set pressure is measured against.** P: the difference (a conventional valve). V: an owner question, gauge (balanced, pilot) or difference. W: hint drafts for both. This design recommends the difference (decision 2) and puts it to the owner as Q2, because the gauge form is a product scope choice that needs new solver rules.
3. **A valve type or its own type.** P: `type: "valve"`, `valveType: "relief"`, with a `ValveResult` and a second map, reusing the valve goals and Compare rows. W: its own type and map. This design takes W's (decision 1): the solver's reuse (P's real point) does not depend on the API type, since the builder can put a `ReliefValve` in `built.valves` either way.
4. **The law's name.** P's B2 and V's law C are the same law when the outlet discharges to atmosphere (V reads it on the EGL drop with equal port elevations). V set ω at 10 % of the gauge set, P at 10 % of the difference; this design takes the difference (decision 6), which changes C6 (the return to suction) by its ω; the reviser named it as an inference and put it to the owner (§1.1, Q4).
5. **The law between set and full lift.** P: B2, recommended. V: five candidates (regulator, pop, linear on the difference, linear on the gauge pressure, offset quadratic) and the owner to choose. W: measured three. This design recommends B2 as Q1's default with every alternative's measured consequence (§10), against Pentair's Fig. 4-12, which the designs had not used (§11, finding 1).
6. **Kd on the letter kind.** W: an editable default 0.65. P: fixed. This design fixes it (decision 7): an editable Kd on an effective area is the mix Pentair forbids, and a real valve's coefficient belongs to the certified kind with its actual area. For the same reason the letter and effective-area kinds take ASME's overpressure, never a user one (decision 6).
7. **The atmosphere boundary.** P: a reservoir at level 0. W: a reference node at 0 kPa(g) at the valve's elevation with an exit-fitted stub. This design takes W's (decision 9); both are exact, and a reference node needs no level.
8. **Refusals.** P: refuse an outlet so small that h(Q) falls (M ≤ 0), and an orifice area at or above the inlet pipe's. With decision 5 the first cannot happen, and the second is representable (the valve's inlet flange can be larger than the pipe, through a reducer); inlet sizing is design practice (API 520 Part II, Later). Only decision 14's refusals remain.
9. **A fuzz profile.** V: a fourth profile `relief`, because the valve is a status element and the fuzz draws check valves only at cracking 0. P: Later. This design takes P's, with a stronger corpus tool (decision 25): `relief_check` exercises cvstatus with a nonzero cracking head on every corpus topology, open and closed, with exact answers rather than EPANET's tolerance.
10. **The corpus tool.** P: replace zero-cracking check valves by relief valves of tiny set (not exact). V: PSV and check-valve stand-ins at a fixed point. This design takes V's fixed-point idea for the chosen law, adds reversed placement and a closed mode, and piloted it (§7.4).
11. **Goals.** P: reuse the valve goals. W: relief goals. With decision 1, relief goals (decision 19).
12. **Where the view, sheet and methods section go.** P: after Orifices. W: after Valves. This design takes W's: users look for a relief valve beside the valves.
13. **Status wording.** P: `locked_closed`. W: "Failed closed". This design keeps `locked_closed` (the check valve's vocabulary, already in `FIXED_CLOSED`) with W's label "Locked closed (gagged or blocked: does not open)".
14. **Result fields.** P: lift, overpressure and capacity fields. W: inlet ÷ set (gauge), back pressure. This design reports both families, with the ratio on the difference, Δp_t/Δp_s, which is what the valve responds to (§2.2).
15. **The opening reading beside today's check valve** (raised by the review, §11 finding 13). A check valve's cracking head h_c = Δp_c/(ρg) is compared with the EGL difference, so with its outlet port 2 m above its inlet a 100 kPa cracking pressure stays closed at a static difference of 119 kPa and opens near 119.6 kPa (review-2, `check_cracking_reading`). The relief valve's h_set adds z_in − z_out, so it opens on the static difference, the force on a spring-loaded disc (C4). Both forms said "pressure difference, inlet minus outlet". This design keeps the relief valve on the static difference, states each element's reading in its hint and trace (W3, §4.1), and lists moving the check valve to the static difference as Later, with its D13 corpus cost (§9).

---

## 2. Model and API

### 2.1 `ReliefValve` (`models/components.py`)

```python
API526Letter = Literal["D", "E", "F", "G", "H", "J", "K", "L", "M", "N", "P", "Q", "R", "T"]


class Api526Orifice(CamelModel):
    kind: Literal["api526"]
    letter: API526Letter


class EffectiveOrifice(CamelModel):
    kind: Literal["effective"]
    area: float = Field(gt=0, le=math.pi * 10.0**2 / 4, description=...)


class CertifiedOrifice(CamelModel):
    kind: Literal["certified"]
    area: float = Field(gt=0, le=math.pi * 10.0**2 / 4, description=...)
    discharge_coefficient: float = Field(gt=0, le=1.0, description=...)
    overpressure: float | None = Field(default=None, gt=0, le=1.0, description=...)


ReliefCapacity = Annotated[
    Api526Orifice | EffectiveOrifice | CertifiedOrifice, Discriminator(...)
]  # custom error


class ReliefValve(BaseComponent):
    """A conventional spring-loaded pressure relief valve, liquid service (SDD §4.18)."""

    PORT_IDS = ("inlet", "outlet")
    PORT_ROLES: ClassVar[dict[str, PortRole]] = {"inlet": "inlet", "outlet": "outlet"}

    type: Literal["relief_valve"]
    set_pressure: float = Field(gt=0, le=RATED_PRESSURE_LOSS_MAX, description=...)
    capacity: ReliefCapacity
    status: Literal["active", "locked_closed"] = "active"
```

The `Component` union gains `Annotated[ReliefValve, Tag("relief_valve")]`.

| Field | Unit | Bounds | Description (the schema's text) |
|---|---|---|---|
| `setPressure` | Pa (difference) | (0, 10⁸] | The static pressure difference, inlet minus outlet, at which the valve starts to open. Discharging to atmosphere at the valve's elevation, it is the gauge set pressure (an outlet pipe rising or falling to its open end adds its liquid-full static head, §3.2); against a constant back pressure, the bench setting (the cold differential test pressure without its temperature correction: the set pressure minus that back pressure). A conventional spring-loaded valve: back pressure adds to the inlet pressure at which it opens. |
| `capacity` | | union on `kind` | `api526`: an API 526 orifice letter, with API 526's effective area; `effective`: an API 520 effective area (m², (0, 78.54]); each with API 520's effective coefficient of discharge, 0.65, and ASME's certification overpressure, for preliminary sizing. `certified`: the valve's actual orifice area (m², (0, 78.54]) with its rated coefficient of discharge ((0, 1]: ASME's K, 0.9 × the measured coefficient), both from its certification, and optionally its overpressure. Never one value from each set. |
| `capacity.overpressure` (certified) | fraction | (0, 1] or absent | The rise of the pressure difference above the set, as a fraction of the set, at which this valve reaches full lift (its rated capacity), from its certification; not the allowable accumulation a valve is sized for. Absent: ASME's liquid certification overpressure, 10 % of the set or 3 psi (20.68 kPa), whichever is greater (the default), for a set of at least 15 psi (103.42 kPa); below it, enter it. |
| `status` | | `active`, `locked_closed` | Locked closed: gagged, or isolated by its block valve; it does not open. |

- **No cross-field model rule** (each value's only rule bounds it; the union carries which values a kind takes). The 15 psi scope rule is a refusal (decision 14), not a model rule, so it needs no new extension for the web to copy. `x-relief-data` (decision 27) is published on the capacity union: `{api526Areas: {letter: m²}, asmeMinimumSetPressure: 103421.36, asmeOverpressureFloor: 20684.27}`, read from `data/api526_orifices.json`.
- **Errors.** A value out of bounds, an unknown letter or kind is 400 `VALIDATION_ERROR` at its field, never echoing it (an unknown kind `invalid_capacity`, as D18's `invalid_rating`). `RELIEF_VALVE_OUT_OF_RANGE` is 422, after `ORIFICE_OUT_OF_RANGE`, one per valve, quoting the valve's C, Δp_s and op, or its set and the 15 psi bound, with the basis and the remedy (decision 14).

### 2.2 `ReliefValveResult` (`models/results.py`)

| Field | Unit | Meaning |
|---|---|---|
| `state` | `closed`, `partial_lift`, `full_lift` | `full_lift` at x = 1 (Q ≥ Q_f). |
| `flow` | m³/s | Positive inlet → outlet (never below zero: the valve closes on reverse flow; as built, a valve open at its switch can report a flow within Qtol below zero, closed, §12 item 2). |
| `lift` | fraction | x, from the flow (decision 13). |
| `headLoss` | m | EGL(inlet) − EGL(outlet). |
| `totalPressureDifference` | Pa (difference) | Δp_t = ρg(headLoss − (z_in − z_out)), what the law reads. |
| `pressureDrop` | Pa (difference) | Static p(inlet) − p(outlet), as `ValveResult.pressureDrop`; = Δp_t − ρ(v_in² − v_out²)/2. |
| `inletPressure`, `backPressure` | Pa (gauge) or null | Static pressure at the inlet and outlet ports; null where the pressure level is undetermined. |
| `setPressure` | Pa (difference) | Δp_s used. |
| `setRatio` | none | Δp_t / Δp_s: below 1 closed; above 1, 1 + the overpressure reached (as built, for an active valve: one locked closed stays closed at any ratio, §12 item 46). |
| `overpressure`, `overpressureSource` | fraction; `asme_default` or `user` | op used. |
| `fullLiftPressureDifference` | Pa (difference) | Δp_f. |
| `fullLiftFlow` | m³/s | Q_f, the capacity at full lift for the case fluid's density. |
| `flowRatio` | none | flow / Q_f. |
| `capacity` | as the input | The capacity the solve used (after any scenario or goal-seek trial), with `area` and `dischargeCoefficient` resolved, and for an effective area `coveringLetter`: the smallest API 526 letter whose effective area is at least it (null above T's). |
| `reynoldsNumber` | none or null | API's Re on the orifice, ρ(Q/A)√(4A/π)/μ; null at zero flow. |

A valve with a closed-off or floating side has no result (a check valve's rule) and raises `RELIEF_VALVE_CLOSED` (decision 15). One inside a floating section has its flow, lift and differences, and null pressures. Each port has its `NodeResult`.

### 2.3 Published rules

`x-port-ids`, `x-port-roles` from the class; `x-override-fields.ReliefValve` gains decision 18's fields; `x-goal-variables.ReliefValve` gains decision 19's four with their scales; `x-goal-quantities` gains the two goals; `x-relief-data` is new, and CLAUDE.md D10's list of extensions gains it. `openapi.json` and `schema.d.ts` are regenerated and the model-rules staleness test stays green.

---

## 3. Physics and solver

### 3.1 The law

§1.1 gives it. Properties measured in `synth/law.py` (S1):
- **Exact inverse.** The band root (trigonometric form while 27R²Q² ≤ 4Δp_s³, which holds over the whole band for op²(1 + op) ≤ 4/27, that is op ≤ 1/3; Cardano's form otherwise) and its slope equal a 60-digit Decimal solve to 8.2×10⁻¹⁶ and 7.9×10⁻¹⁶ over 20,000 draws (ρ 700–1300 kg/m³, C 10⁻⁶–0.03 m², Δp_s 10⁴–3×10⁷ Pa, op 10⁻³–1; S1b). Decision 6 keeps op ≤ 1 everywhere (the default at most 0.2); the Cardano branch loses digits beyond that (4.1×10⁻¹⁵ at op 4.1, 7.1×10⁻⁸ at op 2×10⁴: review-1, `root_bigop`), which no input reaches.
- **Monotone.** dΔp/dQ·C²/(ρQ) is least at Q_f, where it is op/(2 + 3op) (S1d, op 0.001–1), so h(Q) strictly increases on the band for every op > 0, and beyond it.
- **Continuous at Q_f** with a slope step up (825.65 → 18,990 m per m³/s on a G orifice at 700 kPa, 10 %; S1c), so h is monotone and convex there. The slope at 0⁺ is R/(√Δp_s·ρg).
- **API 520.** `API520_A_l(m = ρQ_f, P1 − P2 = Δp_f, Kd 0.65, Kw = Kc = Kv = 1)` gives each letter's area × (1 + 6.092144×10⁻⁵), the rounding of 11.78 (S1f).

### 3.2 The pressure reading (decision 5)

h = Δp/(ρg) + (z_in − z_out) + κQ\|Q\| with κ = 0 for the total-pressure reading (used), (1/A_in² − 1/A_out²)/(2g) for the static one and −1/(2gA_out²) for inlet stagnation, outlet static. On the band, h increases iff op/(2 + 3op) + 2gκC² > 0. Measured on API 526 letters with Kd 0.65 on Sch 40 inlet × outlet bodies (test inputs, not a cited table), at ASME's 10 % (margin 0.04348 for the reading used; S1e):

| Letter, body | (C/A_in)² | (C/A_out)² | static − total, of Δp | stagnation − total | margin, static | margin, stagnation |
|---|---|---|---|---|---|---|
| D 1 × 2 | 0.00685 | 0.00045 | +0.64 % | −0.05 % | +0.0499 | +0.0430 |
| H 1.5 × 3 | 0.06254 | 0.00477 | +5.78 % | −0.48 % | +0.1013 | +0.0387 |
| L 3 × 4 | 0.06295 | 0.02122 | +4.17 % | −2.12 % | +0.0852 | +0.0223 |
| P 4 × 6 | 0.10612 | 0.02059 | +8.55 % | −2.06 % | +0.1290 | +0.0229 |
| R 6 × 8 | 0.12949 | 0.04320 | +8.63 % | −4.32 % | +0.1298 | +0.0003 |
| T 8 × 10 | 0.11407 | 0.04597 | +6.81 % | −4.60 % | +0.1116 | **−0.0025** |

These rows hold the largest departures; every letter is in `s1_law_checks.out.txt`. At a given flow the static reading gives the highest inlet static pressure and the literal (stagnation) reading the lowest; the reading used lies between, above the literal one by the outlet velocity head. The trace gives, at the solved state, the difference by each reading and the flow each would give at the solved pressures (marked not used).

**The outlet piping is liquid-full.** A discharge pipe whose end is below or above the valve has the static head of a full pipe at zero flow: with an open end Δz above the outlet port, the valve opens at a gauge inlet pressure of the set plus ρgΔz. An open tailpipe that drains while the valve is closed is not modelled (§9). The web's open discharge is at the valve's elevation, so it has none.

### 3.3 Zero and reverse flow

Decision 12. `gga.py:490` and `status.py:693` call `law.evaluate(0.0)` for every NORMAL link that is not a head offset; the relief law returns h_set there, as a check valve's `ValveLaw` returns its cracking head, so `closed_off_sections` and the floating-section offsets read h(0) = h_set.

### 3.4 Status rule and the machinery

`check_valve_status` (EPANET 2.2 cvstatus, `status.py:158`) with `cracking_head = h_set`:

```
if |dh − h_set| > Htol:  CLOSED if dh − h_set < −Htol or Q < −Qtol, else OPEN
else:                    CLOSED if Q < −Qtol, else unchanged
```

**Integration.** `ControlKind` gains `"relief"`, which takes the check branch at each site whose `else` would otherwise send it to the PRV/PSV rules or skip it:
- `initial_controls` (l. 383): a `ReliefValve` starts CLOSED (decision 11), fixed when `locked_closed`;
- `_update_controls` (l. 549), the status update;
- `_runaway_status` (l. 594, 604): a disconnected net supply at the inlet or demand at the outlet opens it (D12);
- `_border_constraints` (l. 865): the closed-off constraint H_in − H_out ≤ h_set + Htol;
- `_level_changes` (l. 1053): the free-level test.

`RULES["relief"]` = "a relief valve passes no reverse flow, and no flow while the pressure difference across it is below its set pressure"; `KIND_NAMES["relief"]` = "relief valve"; `FIXED_CLOSED` already has "locked closed". `ValveData` gains `relief: ReliefLaw | None` (None for other valves), and its `resistance` holds the full-lift K on the inlet bore, (A_in/C)², for the trace only. Unchanged: the badvalve options (a relief valve is never ACTIVE), `_check_changes` (active controls only), `gga.py`, `branches.py`.

**The opening reading.** The check valve's rule is reused with another cracking head. A check valve's h_c = Δp_c/(ρg) holds no elevation term, so it opens on the EGL difference; the relief valve's h_set = Δp_s/(ρg) + z_in − z_out opens it on the static difference (§1.3 item 15). Both are stated in their traces and hints.

**Evidence.** With the law placed in a check valve's link and `status.py` unchanged (`synth/harness.py`), the real solver meets the closed forms of §7.1 to ≤ 1.4×10⁻¹⁴ in flow (S2, R3–R6). P measured the same emulation under its static reading: parallel valves, a floating loop closed only by a relief valve, overpressures 0.001–1 (1.4×10⁻¹⁴ to the closed form), and a reverse head, all converged.

**More than one steady state (D9, D13).**
- *Around a closed relief valve.* Where a closed relief valve and a pump bound a closed-off section, more than one zero-flow state can satisfy every rule. Starting closed picks the one an engineer checks (C7). The corpus pilot found one project where the closed start ends in another valid state: `fuzzfc_10917`, a floating loop closed only by the relief valve, ends with every element closed, where the open start keeps A's circulation (S6).
- *A loop whose only fixed head is the relief valve's discharge.* A closed pump loop whose only fixed head is the open discharge (C16, R5) floats when started closed: flows solved, the level undetermined (`UNDETERMINED_PRESSURE`), the relief valve with no result and `RELIEF_VALVE_CLOSED` saying why. Every level at which it does not exceed its set is a steady state here, the valve being the only closed element around the loop. Started open, the solve picks the highest of them, with the inlet at the set (300 kPa(g), the pump discharge 466.47 kPa(g)). The floating answer is the honest one, and the flag's message names the levels at which the valve stays closed (as built, the valve's own bound only, §12 item 42).
- *In the band* (§1.1). A real valve has a second state on the falling branch of its lift characteristic, beyond D6 of this law's. The model has one branch. The band warning names the other state.

The solver reports the state it reaches and does not search for others (D13: finding every such state is not a v1 goal). This design records each case and its count, and §9 lists the general fix.

### 3.5 System curves

`system_curve.py` is unchanged. `has_way_through` blocks only a `locked_closed` valve; `flow_limit` treats the valve as one-way, a reverse arc of capacity 0 and an unlimited forward one; `_switch_message` concerns only control valves; the reason texts read `RULES` and `KIND_NAMES`. H_sys through an opening relief valve holds its law: the pump bypass of C6 over 9 points from 0 to 0.048 m³/s matches the closed form to 1.7×10⁻¹² m (S2, B3), and H_sys(0) = h_set plus the static terms. The web's `system-curve-text.ts` copies `RULES`, so it gains the entry.

### 3.6 Flags (decision 15)

| Flag | When | Details |
|---|---|---|
| `RELIEF_VALVE_OPEN` (info) | at full lift, Q ≥ Q_f | flow, totalPressureDifference, setRatio, flowRatio; the message says "beyond its rated overpressure" where Q > Q_f |
| `CORRELATION_OUT_OF_RANGE` (warning), `limit: 'partial_lift'` | relieving short of full lift, 0 < Q < Q_f (Q beyond the zero-flow rounding) | lift, setRatio, overpressure. The message: "relief valve 'RV1' relieves at partial lift (x): between set and full lift the lift is the linear convention, not a cited law. A typical liquid-trim valve lifts more slowly, surges to full lift near 107 % of set and recloses near 90 % (Pentair TP-V300 Fig. 4-12). A valve that has surged open passes more flow at a lower inlet pressure." |
| `RELIEF_VALVE_CLOSED` (info) | active, closed, with a closed-off or floating side (no result) | `side` (`inlet` or `outlet`), `floating`, h_set; the message, as `CHECK_VALVE_CLOSED`'s: "relief valve 'RV1' is closed and has no result: the section on its inlet side has no fixed pressure level (UNDETERMINED_PRESSURE), so the pressure difference across it is undetermined; every level at which it does not exceed its set pressure is a steady state" (or "… is closed off"); as built it names those levels as the valve's own, §12 item 42 |
| `BELOW_VAPOR_PRESSURE` (invalid, on the component) | relieving, and the outlet port's absolute static pressure ≤ p_v (≤ 0 Pa without one); not in a floating section | `backAbsolutePressure`, `vaporPressure` (or "not given") |
| `CORRELATION_OUT_OF_RANGE` (warning), `limit: 'viscosity'` | relieving, μ ≥ 0.1 Pa·s | value, the Kv API 520 10E would give (not applied) |

### 3.7 Refusal (decision 14)

`_unrepresentable_relief_valves` (after `_unrepresentable_orifices`) refuses, one issue per valve with its basis:
- a valve whose C = Kd·A, Q_f or R is not a finite positive normal double, quoting C, Δp_s and op: possible only at extreme inputs (C below about 10⁻³⁰⁰ m²); as built also C² (C below about 1.5×10⁻¹⁵⁴ m²) and the band root's scale 2Δp_s√(Δp_s/3) (a set below about 3.6×10⁻²⁰⁶ Pa), which the law divides by (§12 item 41);
- a valve with a set below 15 psi (103,421.36 Pa) whose overpressure would be ASME's default (a letter, an effective area, or a certified capacity without an overpressure), quoting the set and the bound: "below ASME VIII's scope (15 psi) no cited source gives its overpressure, and API 520's effective coefficient applies to valves certified within it; enter the valve's certified area, rated coefficient and full-lift overpressure".

### 3.8 Solver integration

| File | Change |
|---|---|
| `services/solver/relief.py` (new) | `default_overpressure`, `band_root`, `ReliefLaw(rho, g, c_area, dps, op, dz)` with `evaluate(q) → (h, dh/dq)`, `dp(q)`, `lift(q)`, `q_full`, `h_set`; the three readings for the trace; `covering_letter`; `relief_refusals`; citation strings. |
| `services/solver/builder.py` | an `elif isinstance(comp, ReliefValve)` branch adding a `LinkKind.VALVE` link with the law, its `ValveData` in `built.valves` (cracking head h_set, 0 when locked closed); `_unrepresentable_relief_valves`. `_unrepresentable_valves` needs no change (its `isinstance` excludes the new class). |
| `services/solver/valves.py` | the `Valve` union gains `ReliefValve`. |
| `services/solver/status.py` | §3.4. |
| `services/solver/results.py`, `trace.py`, `methods.py`, `flags.py`, `version.py` | §2.2, §3.6, §4, `FLAG_SEVERITY`, §3.9; `valve_result` returns None for a relief valve, which `relief_result` maps instead; `relief_result` returns None with a closed-off or floating side and raises `RELIEF_VALVE_CLOSED`, a `ReliefValve` branch beside `closed_off_valve_flag`'s check and control valve branches. |
| `data/api526_orifices.json` (new), `scripts/generate_relief_data.py` (new) | decision 27. |
| Unchanged | `gga.py`, `network.py`, `elements.py`, `system_curve.py`, `branches.py`, `npsh.py`, `friction.py`. |

### 3.9 `METHOD_VERSION` and the bit-identity proof

- **Version 1.5.0.** Changelog line: "Adds the liquid pressure relief valve: a conventional spring-loaded valve closed below its set pressure difference, its lift rising linearly with the overpressure (a convention, flagged; not the typical characteristic's surge and blowdown) to full lift at set plus overpressure (ASME's 10 % or 3 psi by default, for sets of at least 15 psi), with API 520's liquid equation Q = Kd·A·√(2Δp/ρ) at its lift on the total-pressure difference between its ports; API 526 letters and effective areas at API 520's preliminary coefficient 0.65, or a certified area and rated coefficient. Flows, heads, pressures, statuses, traces, messages and system curves of projects without relief valves are unchanged (corpus comparison)." Every link last solved with 1.4.0 shows the method-change notice after its next solve, as D18 and D20 accepted.
- **Why projects without relief valves are identical:** every new path sits behind `isinstance(comp, ReliefValve)` or `control.kind == "relief"`; each check branch keeps its code and gains a kind; the issue check finds nothing and its issues come last; the methods additions are conditional; `FlagCode` and `ControlKind` only gain members; the goal-seek bound builds run only for a relief variable.
- **Proof.** Dump the corpus (5,168 projects, with system curves) on `b7f09eb` and on the branch, then `compare A B --ignore-empty reliefValveResults --ignore methodVersion --ignore trace.methods.methodVersion`: identical 5,168, the new reference cases only on the branch. Also on the branch's corpus (D13): `scenario_check` 0 different, `goal_seek_check` 0 violations, `equipment_check` and `orifice_check` 0 different, `relief_check` (§7.4) within its criteria, `missing_result_check` at its baseline, the three fuzz profiles the same 9,000 records, the reference suite green.

### 3.10 Sources

| Source | What it supports | How verified |
|---|---|---|
| fluids 1.3.1 `safety_valve`: `API520_A_l`, `API520_Kv`, `API520_W`, `API526_letters`, `API526_A_sq_inch`, `API526_A`, `API520_round_size` | The liquid equation and its exact SI form, the constant's derivation, Kd 0.65 "normally", API 520 10E's Kv and its 0.1 Pa·s recommendation (as documented), the API 526 areas, the letter covering an area (`API520_round_size` raises above T) | P and V read the source and ran the docstring examples (V: three reproduced exactly); S1f. R re-read `API520_A_l`'s source: its `overpressure` is the allowable overpressure, used only to recover P_set = (P1 − atm)/(1 + overpressure) for Kw. Traps: `Kv = None` with `mu = None` raises `TypeError`; `Kw = None` applies the balanced-bellows table to every valve. The law calls neither. |
| Pentair *Pressure Relief Valve Engineering Handbook*, TP-V300, rev. 12-2012 (secondary, on ASME VIII and API 520/526) | The definitions (set, overpressure, relieving pressure, flow rating, back pressure, CDTP); ASME's 10 % or 3 psi certification; the 16 % and 21 % accumulations used in sizing; the set tolerance (Table 3-2: ±2 psi to 70 psig, ±3 % above); fixed blowdowns for liquid valves; K = 0.9 Kd; "outside of the scope of ASME (below 15 psig)"; the pump relief's bench setting; superimposed and built-up back pressure on a conventional valve's disc; Kw = 1 for conventional valves; the no-mixing rule; Table 7-6's areas and 0.650; Fig. 4-12, the typical liquid-trim lift characteristic (§1.1) | V downloaded and read it (pdftotext); S re-read each quotation used here in the saved text; R re-read the definitions, Fig. 4-12 (the rendered page, `review-1/fig/q-046.png`), Table 3-2, the back-pressure pages and the scope sentence. |
| Trimeric (Kerr et al.), PRV capacity paper | API 526 areas are nominal, for preliminary sizing; effective and actual values not mixed (API 520 Part 1 §5.2.5) | V read it. |
| Technical Toolboxes help pages on API 520 | Capacity varies with lift up to full lift; certification at 10 %; Kd 0.62 at 25 % for non-certified valves | V fetched them; the equations are images. |
| MathWorks Simscape "Pressure Relief Valve (IL)"; AFT Impulse and Fathom pages | Linear opening from set to set plus a range, on the difference or the inlet gauge pressure; set and overpressure as full open; Fathom's two-state model and its cycling warning | V fetched them. |
| EPANET 2.2 (hydstatus.c, as in `status.py`) | cvstatus | In the code. |
| Not read: API 520 Parts I and II, API 526, ASME VIII (UG-125 to UG-136) and Section XIII, ASME PTC 25 | | None is cited as read; their content above is via the secondary sources. |

---

## 4. Traceability

### 4.1 Trace (`trace._relief_trace`, `element_type = "relief_valve"`)

- **Inputs:** Δp_s (`user`), with its reading (the static difference at zero flow); op (`default`, ASME's, with the 3 psi floor where it applies, or `user` on a certified capacity); the capacity:
  - a letter: its area from `data/api526_orifices.json`, "library", with Kd 0.65, labelled preliminary, "API 520's effective values; the selected valve's actual area and rated coefficient give its capacity";
  - an effective area: `user`, with Kd 0.65, labelled preliminary, and its covering letter;
  - certified: area and rated K, `user`, with "a rated K is 0.9 × the measured coefficient (ASME)".

  Then the status; ρ, μ, p_v with their sources; g; the ports' elevations; the inlet and outlet bores.
- **Equations:** Δp_t and its identity with the EGL drop; x; the full-lift equation; API's 11.78 form and its +6.09×10⁻⁵; h_set; the band cubic and its root; Δp_f, Q_f; the static pressure at each port (D7) and the static-drop identity.
- **Intermediates:** C, R, Q_f, Δp_t, x, setRatio, flowRatio, the slope, Re and the Kv API 520 10E would give. With a back pressure, the inlet gauge pressure at full lift at the solved back pressure, and the overpressure on the gauge set that would put full lift at (1 + op) × (Δp_s + p_out), op·(Δp_s + p_out)/Δp_s (not used).
- **The inequality that set its state:** "closed: Δp_t X Pa does not exceed the set Y Pa by more than ρg·Htol", or the open rule.
- **Notes:**
  - a conventional valve: back pressure adds to the opening pressure; the set is the bench setting against a constant back pressure; it opens on the static difference, where a check valve's cracking pressure reads the EGL difference;
  - the overpressure is taken on the set difference, an inference for full lift (§1.1);
  - the band is the linear-lift convention (Simscape, AFT), not a cited law. Pentair's typical liquid-trim characteristic (Fig. 4-12) lifts to about half at 107 % of set, surges to full lift there, and on falling pressure stays at full lift to about 95 % and recloses near 90 % (a fixed blowdown of 10–15 %). This state is on a rising branch, and a valve that has surged open passes more flow at a lower inlet pressure;
  - what the certification does not bound: ASME VIII's set tolerance (±2 psi to 70 psig, ±3 % above), and a rated coefficient 0.9 of the measured one, so a certified valve's capacity may exceed the rated one;
  - the pressure reading, and both other readings' difference and flow, not used;
  - Kw = Kc = Kv = 1; no blowdown; liquid-full outlet piping; liquids only;
  - each flag's inequality;
  - in a scenario, D15's note; in a goal seek, D16's.

### 4.2 Methods summary

A "Relief valves" section after Valves, only with a relief valve:
- the law and its three named departures (§1.1), with Fig. 4-12 and the band warning;
- the default overpressure and its 15 psi scope;
- the three capacity kinds and the no-mixing rule;
- the status rule, the closed start and the opening reading;
- the flags and the refusals;
- Kw, Kc and Kv not applied.

References: fluids `safety_valve` (API 520 Part I, 10th ed., and API 526), Pentair TP-V300, Simscape, AFT. One assumption: "Relief valves are conventional spring-loaded valves in liquid service, lifting linearly (a convention) from their set pressure difference to full lift at set plus overpressure, with API 520's liquid capacity equation on the total-pressure difference across them."

### 4.3 Issue and flag text (web)

`issue-text.ts` gains `RELIEF_VALVE_OUT_OF_RANGE` (both bases). `flag-text.ts` gains, each in display units, with `digitsApart` near a limit and falling back to the message without details:
- `RELIEF_VALVE_OPEN`;
- `RELIEF_VALVE_CLOSED`;
- the partial-lift limit;
- the back-pressure flashing branch, keyed on `details.backAbsolutePressure`;
- the viscosity limit.

---

## 5. Scenarios, goal seek, Compare, export, design checks

- **Scenarios (D15):** decision 18. `COMPONENT_NAMES[ReliefValve]` = "relief valve". `value_text` writes:
  - a null `capacity.overpressure` "ASME's 10 % or 3 psi (the default)";
  - a letter capacity "API 526 J (830.3 mm²), Kd 0.65 (preliminary)";
  - an effective one "API 520 effective area 447.1 mm², Kd 0.65 (preliminary)".

  Use cases: a blocked discharge (an isolation valve changed, the relief valve's own values untouched), a smaller valve (a letter), a gagged valve (`locked_closed`), a lower set.
- **Goal seek (D16):** decision 19. `LOG_FIELDS` gains `capacity.area`.
  - A certified case on the default overpressure starts in the middle of the bounds (`AxisSpec.case = None`), the "held" text naming ASME's default.
  - `capacity.area` is `not_applicable` on a letter. `capacity.dischargeCoefficient` and `capacity.overpressure` are `not_applicable` on a letter or an effective area; a variable's `baseValue` is null there, as D18.
  - The bound builds' 400s are located by index with no id or value in the text (D20).

  Uses:
  - the set for a relief flow;
  - **sizing**: the effective area that puts the inlet at the relieving pressure, set plus 10 % (G41), which equals `API520_A_l` at the solved flow and pressures, with the letter that covers it in the result;
  - the overpressure a calibration must show.
- **Goals:**

| Goal | Unit, category | Reads | Label |
|---|---|---|---|
| `relief_valve_flow` | m³/s, flow | `flow` | flow through {element} |
| `relief_valve_pressure_drop` | Pa (difference), pressure | `pressureDrop` | static pressure drop across {element} |

- **Compare (web):** decision 20; `compareElementKind` returns `'relief'`; `CompareRowsDialog` gains "Relief valves"; relative only for the flow.
- **Export (D17, web):** sheet `relief_valves` ("Relief valves", `relief_valves.csv`) after Valves, with these columns:
  - case columns, Solved at, Results; Relief valve id, Relief valve;
  - State, Flow, Lift, Capacity (full lift), Flow ÷ capacity, Inlet pressure (g), Back pressure (g), Δp ÷ set, Pressure difference (total), Pressure drop (static), Head loss;
  - Set pressure, Overpressure at full lift, Overpressure from;
  - Capacity given by ("API 526 J", "Effective area", "Certified"), Area, Kd, Covering letter;
  - Reynolds number; Flags.

  The inputs are as solved, the sheet's named departure, as D18 and D20. About lines only in a file with the sheet: the sign row and the "≈ 0" clause.
- **Design checks (D19):** none applies (decision 22); `test_relief.py` pins that only pipe velocity covers the valve's two connections.

---

## 6. Web

These are the designers' web defaults, reversible under D14, from W's memo with this design's model.

- **W1. Menu and entry.** Decision 26. Kind `relief_valve`, default name "Relief valve RV1". `ENTRY_KINDS` and `INLINE_KINDS` gain it.
  - Every create path (the first component in `PanelNavigator`, Add after, Add before, Insert, the Piping view's Add here) asks for the set pressure and the capacity first.
  - One message per empty field: "Enter the set pressure: it has no default." and "Choose an API 526 orifice letter, or enter an effective area or the certified area and coefficient: the capacity has no default."
  - An error clears on input, never on blur (D18's layout rule).
  - `validate.ts`'s `taggedSchema` maps the capacity's `kind` to its member (`capacitySchemaName`, beside the fluid's and the rating's), so a schema problem is reported against its kind only.
- **W2. Discharge.** A new `edit.ts` helper `addOpenDischarge` (modelled on `plugPort`) adds an open discharge at a free port in one undo step. `ConnectionPanel` offers it as "Discharge to atmosphere (adds an open discharge: a reference node at 0 kPa(g), 1 m of pipe with an exit, at the valve's elevation)" at a relief valve's free outlet, before "Plug this port". A choice at creation is Later (§9).
- **W3. Form** `forms/ReliefValveForm.svelte`, sharing `ReliefValveFields.svelte` with the Add dialog; one column on phones, two from 640 px:
  - Elevation; Status ("Active" or "Locked closed (gagged or blocked: does not open)").
  - **Set pressure (difference)**, category pressure (a difference, not gauge). Hint: "The static pressure difference, inlet minus outlet, at which the valve starts to open. Discharging to atmosphere at the valve's elevation it is the gauge set pressure; with a constant back pressure (a return line) it is the bench setting: the set pressure minus that back pressure. Back pressure adds to the inlet pressure at which a conventional valve opens."
  - **Capacity** fieldset, a kind union (D18's pattern, no value carried between kinds, a pending kind with a warning):
    - "API 526 orifice letter": a select whose options read "J: 830.3 mm²" or "J: 1.287 in²" from `x-relief-data`.
    - "API 520 effective area": the area in a new derived unit category `area`.

    Both show a read-only line "API 520's effective coefficient 0.65 and ASME's overpressure (10 % or 3 psi): preliminary" (as built with ASME's 15 psi scope, amber for a set below it, §12 item 47).
    - "Certified area and coefficient": the area, "Rated coefficient of discharge (K)", and **Overpressure at full lift**, category fraction, "ASME's 10 % or 3 psi, whichever is greater (the default)" or a number. Its hint: "The overpressure at which this valve reaches its rated capacity, from its certification; not the allowable accumulation a valve is sized for. Required for a set below 15 psi."

    The fieldset's hint: "The manufacturer's actual orifice area with its rated coefficient, or an API 526 letter or effective area with API 520's effective values: never one from each."
  - Form hint: "A conventional spring-loaded pressure relief valve in liquid service (API 520 Part I): closed while the pressure difference across it is below its set pressure, opening in proportion to the overpressure (a convention: real valves surge open and reclose below set; partial lift is flagged), fully open at set plus overpressure with API 520's liquid capacity. Not EPANET's PSV (pressure-sustaining valve). Flashing at its outlet and a viscous liquid are flagged; gases, steam and two-phase relief are not modelled."
  - The PSV form's hint gains the reverse pointer. The check valve form's cracking-pressure hint becomes: "The forward pressure across the valve that opens it, read on the energy grade line: the static pressure difference, inlet minus outlet, plus ρg × (inlet port elevation − outlet port elevation); 0 opens on any forward flow. For overpressure protection use a pressure relief valve: a check valve's fixed K does not follow API 520's capacity."
  - No pre-solve range checks (D10: read, never copy). In a scenario, the allow-listed values are marked Changed with the base value and Reset; a kind change is one whole-capacity change.
- **W4. Results view "Relief valves"**, after Valves, only when `reliefValveResults` has entries (an older response is read as `{}`).
  - Columns: State, Flow, Capacity (full lift), Flow ÷ capacity, Inlet pressure (g), Δp ÷ set, Lift, Back pressure (g), Pressure drop (static), Head loss; "—" for null; sticky first column, sideways scroll on phones.
  - A note under the table explains Δp ÷ set (above 100 % it is relieving, as built an active valve, one locked closed reading "Closed (locked)", §12 item 46; the rise is its overpressure, which is the accumulation only when it is set at the protected equipment's MAWP), Capacity, and that partial lift is a convention (the warning).
  - A valve with no result is listed by its `RELIEF_VALVE_CLOSED` flag.
- **W5. Strip.** `SUMMARY_COLUMNS['Relief valve']` = state, flow, inlet pressure, Δp ÷ set. A Summary card is Later (§9).
- **W6. Compare, goal seek and scenarios.** Decisions 18–20. Goal-seek group "Relief valves", with these default bounds:
  - the set: [v/2, 2v], its lower bound raised to `x-relief-data`'s 15 psi where the overpressure is ASME's;
  - the area: API 526's D to T effective range, widened to hold the case's area (and on a certified area the same range);
  - the coefficient: [v/2, min(2v, 1)];
  - the overpressure: [v/2, min(2v, 1)] (on the default, from ASME's value for the case's set, 0.1–0.2).

  Goal hints: "Positive from inlet to outlet: the relieving flow." and "Static pressure, inlet minus outlet." Scenario labels and value texts as §5.
- **W7. Units.** `units.ts` gains the fixed derived category `area` (mm² 10⁻⁶, m² 1, in² 6.4516×10⁻⁴), the only way to enter the effective and certified areas; `export/units.ts` maps it to m².
- **W8. Bundle.** W estimated +7 to 8.5 KB gzip on the initial `/p` download by scope from D18 (+7.0) and D20 (+8.0), before the review moved the Summary card and the creation choice to Later. It is measured and recorded as TSD §8.3 does. W's schema-trim build plugin (the bundled `openapi.json` without annotation keywords: −18.8 KB gzip measured, 892 node-project tests green) is a separate web-only change, not part of this slice (§9).

---

## 7. Verification

### 7.1 Closed-form reference cases (`tests/reference/derivations_relief.py`)

- **Method.** A new derivations file by a tester who does not read `services/`:
  - `element_laws` gains its own transcription of the law (`relief_head`, the band root);
  - `case_format` gains `relief_valve(...)`;
  - `Expected` gains a `reliefValves` block with every result field, and each case its flags;
  - `network_check` evaluates the law;
  - `closed_form.py` registers `derivations_relief.CASES`.

  Liquid A (998 kg/m³, 1 mPa·s), ε 4.5×10⁻⁵ m, Colebrook, unless stated.
- **Measured.** Each case was measured against the real solver with the law in a check valve's link, started closed: every flow within 1.4×10⁻¹⁴ relative, every EGL within 3×10⁻¹⁴ m.
  - C1–C4 and C6–C9 by the synthesizer (`synth/cases.py`);
  - C5, C15 and C16 by the reviser (`reviser/measure.py`, `certified.py`, `closed_loop.py`);
  - C1–C4 and C6–C9 again independently by review-1 (`indep.py`), to the digits shown (its C5 was the earlier 100 kPa set, now below ASME's scope).

  C10–C14 are outlined for the tester. The partial-lift cases (C2, C4–C6, C8, C9, C15) verify the implementation of the linear convention, not the convention (§1.1).
- **Network M** (V's R2–R4): R1 (z 0, level 2 m, surface p_R) → 102.3 mm × 100 m → ideal tee T1 (z 0) → 102.3 mm × 100 m → R2 (z 0, level 2 m); T1 branch → 52.5 mm × 2 m → RV1 (z 0; set 500 kPa, API 526 F, op default 0.1) → 77.9 mm × 3 m → R3 (z 0, level 0). Q_f 0.004274154702 m³/s, h_set 51.08798662 m.
- **Network B** (V's R1): R1 (z 0, level 2 m, two ports) → 154.1 mm × 5 m → PU1 (z 0, `curve_a`) → 102.3 mm × 5 m → ideal tee T1 (z 0); run → 102.3 mm × 50 m → IV1 gate, isolated → 102.3 mm × 50 m → R2 (z 0, level 10 m); branch → 77.9 mm × 3 m → RV1 (z 0, API 526 L) → 102.3 mm × 6 m → R1 port_2. Set 330,425.9266 Pa: 350 kPa(g) less the superimposed 19,574.07 Pa (ρg × 2 m), the bench setting.

| Case | Network | Derivation | Expected (measured) |
|---|---|---|---|
| C1 `relief_closed` | M, p_R 600 kPa | brentq on T1's EGL; relief closed since EGL_T1 − EGL_R3 < h_set | Q 0; p_in 319,574.0734 Pa(g); no relief flag |
| C2 `relief_partial_lift` | M, p_R 1.05 MPa | nested brentq | Q 0.002221210802348; x 0.5311270926; Q/Q_f 0.5196842317; EGL in/out 53.81168955 / 0.01028154777 m; p_in 526,131.6131, p_out −7.754453834 Pa(g); Δp_t 526,556.3546, static drop 526,139.3676 Pa; at these pressures the stagnation reading gives Q +0.418 %, the static one −1.609 %; `CORRELATION_OUT_OF_RANGE` (`partial_lift`) |
| C3 `relief_full_lift` | M, p_R 1.4 MPa | nested brentq | Q 0.004732647684257; Q/Q_f 1.107271031; p_in 672,346.5806 Pa(g); h 68.90002007 m; `API520_A_l` on ρgh gives A_F × (1 + 6.092144×10⁻⁵); `RELIEF_VALVE_OPEN` |
| C4 `relief_port_elevations` | M, p_R 1.05 MPa, outlet port 0.5 m above the inlet port | h_set = Δp_s/(ρg) − 0.5 | Q 0.002466109033239; x 0.5880976056; p_in 523,985.4996, p_out −4,905.375361 Pa(g); static drop 528,890.875 Pa; opens at p_in − p_out = 500 kPa exactly |
| C5 `relief_asme_3psi` | M, set 150 kPa, p_R 300 kPa | op = 3 psi/Δp_s (inside ASME VIII's scope) | op 0.1378951459; Q 0.001473859256618; x 0.6332320359; Q/Q_f 0.6189996008; p_in 162,914.5764 Pa(g) |
| C6 `relief_pump_bypass` | B | brentq on the pump's flow | Q 0.02530885872613; x 0.7913442325; Q/Q_f 0.7838029109; p_in 367,016.2267 Pa(g) (104.86 % of 350 kPa(g)); setRatio (Δp_t/Δp_s) 1.07913442325 (the static ratio, not a result field, 1.0508690913) |
| C7 `relief_set_above_shutoff` | B, set 450 kPa | zero flow: p_in = ρg(EGL at shutoff) | closed; pump running at zero flow; p_in 459,990.7249 Pa(g). Started open (a check valve's start) the pump and valve close together and the inlet has no result: decision 11. |
| C8 `relief_parallel_staggered` | B with a second ideal tee T2 after 77.9 mm × 3 m feeding RVa and RVb (J each, 77.9 mm × 1 m in, 102.3 mm × 6 m out to reservoirs at level 2 m); sets 350 and 364 kPa(g) less 19,574.07 Pa | brentq on T2's EGL | Qa 0.01460771747274 (full lift), Qb 0.00964240706616 (x 0.658683); T2 EGL 39.6433689 m |
| C9 `relief_assigned_demand` | R1 (level 2 m, surface p_R) → 52.5 mm × 2 m → RV1 (as M) → 77.9 mm × 3 m → AF1 demand 3 L/s | explicit; AF1's static pressure subtracts ρv²/2 in its 77.9 mm pipe (D7) | p_R 600 kPa: h 54.72182215 m, x 0.71128963, EGL out 8.4999204 m, AF1 82,817.09534 Pa(g). p_R 450 kPa: the inlet is below a gauge set but the difference opens it: EGL out −6.826475587 m, AF1 −67,182.90466 Pa(g) |
| C10 `relief_locked_closed` | C6, `locked_closed` | zero flow, C7's closed form | p_in 459,990.7249 Pa(g), as an isolated valve |
| C11 `relief_reverse_head` | R1 (surface 300 kPa) → RV1 → R3 (surface 400 kPa); and 520/600 kPa (V's R6) | — | closed, Q 0 |
| C12 `relief_glycol` | C2 on built-in 30 % MEG | ρ scaling | to be measured by the tester |
| C13 `relief_flashing` | C2's network on built-in water at 120 °C (p_v 198,674.4 Pa, the app's CoolProp) | the outlet ≈ 101 kPa abs < p_v | `BELOW_VAPOR_PRESSURE` on RV1, beside the port flags below p_v |
| C14 `relief_viscous` | C3 on a custom liquid of 0.2 Pa·s | — | `CORRELATION_OUT_OF_RANGE` (viscosity), Kv in the trace |
| C15 `relief_certified` | M, p_R 1.05 MPa, certified area 2.5×10⁻⁴ m², K 0.70, overpressure 0.08 (test inputs) | nested brentq | Q_f 0.005756846582; Q 0.002921930523253; x 0.5168904272; Q/Q_f 0.5075574764; p_in 519,932.5011 Pa(g); `overpressureSource` `user` |
| C16 `relief_closed_loop` | PU1 (`curve_a`) → 102.3 mm × 150 m → ideal tee T1 → 102.3 mm × 150 m → PU1 suction; T1 branch → 52.5 mm × 2 m → RV1 (set 300 kPa, F) → 77.9 mm × 1 m → N1, a reference node at 0 kPa(g) (the only fixed head) | the pump's head equals the loop's friction | Started closed: loop flow 0.03016051574499 m³/s (pump head 35.39224763 m); `UNDETERMINED_PRESSURE`; RV1 has no result and `RELIEF_VALVE_CLOSED` (floating inlet side). The open start's state (RV1 at its switch, inlet 300 kPa(g), pump discharge 466.4738 kPa(g)) is the highest of the levels the flag names, not a result (§3.4) |

**System curve** (`test_system_curves.py`): PU1 of C6, H_sys(Q) = the pipes + h_relief(Q) at every point (S2: 1.7×10⁻¹² m over 9 points).

### 7.2 EPANET cases (`generate_epanet_cases.py`, `epanet_model.py`)

Decision 24, written with WNTR (`add_curve(..., 'HEADLOSS', …)`, the points at 0, Q_f and 201 evenly spaced flows, a GPV, the inlet pipe as a CV pipe); `network_check.EPANET_MODEL` evaluates the same curve. V measured network M's law under EPANET 2.2 (WNTR 1.5.0, water at ρ 1000, Swamee–Jain in the 5.74 form), which is this design's law exactly (discharge to atmosphere, set and overpressure on the difference); review-1 reproduced E1–E3 with its own run:

| Case | Reference relief Q | EPANET, ΔQ relative |
|---|---|---|
| E1 `epanet_relief_partial` (p_R 1.05 MPa) | 0.0022186660463 | +1.702×10⁻⁴ |
| E2 `epanet_relief_full` (p_R 1.4 MPa) | 0.0047276688973 | +1.038×10⁻⁵ |
| E3 `epanet_relief_near_set` (p_R 1.004 MPa) | 0.0010820268256 | +1.629×10⁻⁴ |

The closed state is not an EPANET case: EPANET reports a meaningless 50.99 m at the junction the closed CV pipe isolates (V); C1 covers it. `test_derivations_current.EPANET_CASE_NAMES` gains the three.

### 7.3 Goal seek and scenario references

`test_goal_seek.py` (the same tester), numbered after D20's G33–G39, measured by `synth/gs.py` and `reviser/measure.py` and `certified.py` with a forward solve, and G40, G43 and G44 independently by review-1 (`indep_gs.py`):
- **G40** `setPressure`, goal `relief_valve_flow` = 0.020 on C6: set* 366,924.6494 Pa (x 0.5987988).
- **G41** (sizing) `capacity.area` on an **effective** capacity in C6's place, goal port `RV1:inlet` static pressure = 385 kPa(g), the relieving pressure 1.1 × 350 kPa(g): A* 1.2866259342×10⁻³ m² (1.994274 in²), past full lift (Q/Q_f 1.0128157, R4). `API520_A_l` at the solved flow with P1 − P2 = Δp_t gives A* × (1 + 6.092144×10⁻⁵): sizing by API 520 against the network. The result's covering letter is L.
- **G42** `capacity.overpressure` (certified, C15's valve), goal `relief_valve_flow` = 0.0025 on C15: op* 0.1099375341 (x 0.44075; R6).
- **G43** `capacity.dischargeCoefficient` (certified, area 1.9806412×10⁻⁴ m², a test input), goal `relief_valve_flow` = 0.0045 on C3: K* 0.6169863575.
- **G44** R1's `surfacePressure`, goal `relief_valve_pressure_drop` = 520 kPa on C4: p_R* 1,018,261.857 Pa (Δp_t 520,239.30 Pa: the static drop and the law's difference differ, so a swap misses).
- **Not applicable:** `capacity.area` on a letter, and `capacity.overpressure` on an effective area, are each 400 at their index.
- **Bounds:** a `setPressure` box whose lower bound is below 15 psi on a letter is a bounds 400 (the build there is refused, decision 14).

`test_scenarios.py` (metamorphic): a set change, a letter change, a kind change, `locked_closed` and a null `capacity.overpressure` each solve bit for bit like the hand-edited project.

### 7.4 `relief_check` and the corpus tools

**`tests/differential/relief_check.py`** (new; decision 25), three modes with an exact expected answer each, run on the whole corpus. Every placed valve has a certified capacity (K ~ U[0.6, 0.9], area C/K) with a drawn overpressure, so decision 14's scope refusal never applies.
- **`band`** and **`full`**: each active isolation valve with a result and a flow is replaced by a relief valve placed in the flow's direction (its ports swapped in the connections for a reverse flow), so that A's state satisfies B's equations: Δp_A = ρg(\|h_A\| − (z_up − z_down)).
  - `band`: op ~ U[0.05, 0.5], x ~ U[0.1, 0.9], Δp_s = Δp_A/(1 + x·op), C = \|Q_A\|/(x√(2Δp_A/ρ)).
  - `full`: op ~ U[0.05, 0.5], k ~ U[1.05, 2], Δp_s = Δp_A/(k(1 + op)), C = \|Q_A\|/√(2Δp_A/ρ).
  - Kept as valves: no flow, or Δp_A − Δp_s below 10 Htol ρg.
- **`closed`**: per project, the first active isolation valve with a result. A′ is the project with it isolated. B replaces it by a relief valve set above the difference across it in A′ (k ~ U[1.05, 2] times it, plus 10 Htol ρg; op ~ U[0.05, 0.5]). Skipped where A′ has a side without a head or a floating section.
- **Criteria (D13):** the same convergence; every flow and EGL within D6, `equipment_check.head_bound` gaining `("reliefValveResults", "headLoss")` for ports in floating sections.
  - Counted and listed, not failures: differences confined to elements carrying zero flow and the sections they close off (D9's multiplicity: which nodes have results, flows at the zero-flow rounding), and to an element at its switch within Htol with every head within D6. Each listed project is triaged in the build record.
  - In B's results: Δp_t = ρg(headLoss − Δz), the static-drop identity, and x and Q against the law, to round-off.
- **Pilot** (`synth/relief_check_pilot.py`, `relief_check_closed.py`, the law in a check valve's link; 5,168 projects, 4 workers):

| Mode | Projects (valves, reversed) | Started closed (the design) | Started open |
|---|---|---|---|
| `band` | 297 (316, 159) | 296 identical; 1: `fuzzfc_10917`, a floating loop closed only by the relief valve, ends with every element closed (§3.4) | 297 identical |
| `full` | 386 (417, 209) | 384 identical; `fuzzfc_10917` as above; `fuzzfc_10169`: FCV8 at its switch (1.3×10⁻⁶ m across it in A, 2.3×10⁻⁵ m in B, both within Htol), flows ≤ 1.8×10⁻⁶ m³/s apart, heads within 4.6×10⁻⁵ m | 386 identical (largest 1.05×10⁻⁹ of the largest flow, 5.3×10⁻⁶ m) |
| `closed` | 870 | 799 identical; 67 differ only in which nodes are closed off; 4 in flows, at most 1.2×10⁻⁸ m³/s apart | 679 identical; 181 in closed-off nodes only; 9 in flows; 1 in an EGL (`fuzz_1326`, 15.0 m at a node both report) |

  The pilot placed C directly; the kind does not change the law. Two early `closed` differences (`fuzz_384`, `fuzz_2285`) were the pilot's own fault, a set drawn where A′ reported no head; the rule above skips them.
- **The corpus tools learn the type**, as D18 and D20:
  - both `scenario_patch.py`;
  - `scenario_check.OUT_OF_BOUNDS`/`BELOW_BOUNDS`: a set of 0 or 2×10⁸ Pa, an overpressure of 0 or 2, an area of 0, a K of 1.5;
  - `goal_seek_check`: `candidates`, `case_value`, `written`, `SPAN_FLOOR`, and `goal_value` for the two goals;
  - `compare.py`: `reliefValveResults` in `element_flows` and `Judge.element`; `inletPressure`, `backPressure`, `totalPressureDifference` and `fullLiftPressureDifference` in the pressure `KEYS`;
  - `equipment_check.head_bound`; `test_harness.py`; the smoke tests `test_compare_tolerance.py` and `test_goal_seek_check_smoke.py`.

  A smoke test pins a few projects (`test_relief_check_smoke.py`).

### 7.5 Acceptance (D6, D13)

The reference suite green with C1–C16 and E1–E3, G40–G44 and the scenario tests; the corpus comparison identical (§3.9); on the branch's corpus `scenario_check` 0 different, `goal_seek_check` 0 violations, `equipment_check` and `orifice_check` 0 different, `relief_check` no difference outside its listed classes; the three fuzz profiles the same 9,000 records.

### 7.6 Unit, component and e2e tests

- **API unit** (`tests/unit/test_relief.py`, beside a contract `test_relief_model.py`):
  - **The law:** fluids' docstring examples and the `API520_A_l` identity for every letter; the band root and slope against a high-precision solve and central differences; continuity at Q_f; the margin op/(2 + 3op).
  - **Inputs and the default:** the default overpressure at the 3 psi crossover (206,842.72 Pa) and the 15 psi scope (103,421.36 Pa: refused just below with each defaulted kind, accepted with a certified overpressure); h_set with port elevations.
  - **States and flags:** start closed and `locked_closed`; each flag at its bound (the partial-lift warning just below Q_f and `RELIEF_VALVE_OPEN` at it) and none on a closed valve with a result; `RELIEF_VALVE_CLOSED` closed off and floating (null pressures); the refusal at its edge.
  - **Results and records:** the covering letter (at a letter's exact area, just above it, above T); the trace's sources, its three readings and its gauge-set overpressure; the methods section only with a relief valve.
  - **Data and versions:** `data/api526_orifices.json` regenerated equal to the committed file, and `x-relief-data` equal to it; `ElementKind` gains `relief_valve`; `EXPECTED` and the version pins (1.5.0); no design check on the valve.
- **Web unit and component:**
  - factory (missing entries, prefix); `addOpenDischarge` (a 0 Pa reference node at the port's elevation, an exit-fitted stub sized to the port, one undo step, offered on a relief valve's free outlet only);
  - model-rules (the union, `x-relief-data`, the override and goal fields); `validate.ts` (a capacity problem reported against its kind only); units (area exact);
  - results (columns, labels, "—" in a floating section, strip = cells); compare (default rows and their order, relative only for flow); goal seek (each default box, the set's 15 psi floor); scenarios (labels, a kind switch removing the other kind's changes);
  - flag-text and issue-text in SI and US units;
  - `ReliefValveForm` (names with units, all three kinds, the pending kind, both unit systems, scenario Changed and Reset); `CheckValveForm`'s new hint; each Add surface (the errors first).
- **Export:** oracles in `export/model.test.ts`; `export_input.scenario_project()` gains a relief valve that relieves in one scenario (with a letter change), whose outlet pipe is a size up so a swapped static-drop column fails; `test_web_export_fixture.py` gains the sheet.
- **E2E `tests/relief-valve.e2e.ts`**, desktop and phone, against the real API (no axe: the repository has none, as D20 found).
  - **Network** (W's, every pipe NPS 4 Sch 40): R1 (z 0, level 3 m) → 10 m with a sharp entrance → P1 (0/30, 10/28, 20/22, 30/12 L/s/m) → 10 m → Crane tee T1 → 1 m → V1 gate → 10 m with an exit → R2 (z 10 m, level 2 m); T1 branch → 10 m → RV1 (set 280 kPa, letter J, op default) → open discharge (added by "Discharge to atmosphere": 1 m with an exit → N1 at 0 kPa(g)); water at 20 °C.

  Expected (S5, this design's law):
  - **Flow 1, build and solve:** RV1 closed, inlet 129.5808 kPa(g), Δp 46.28 % of set, pump 28.91322 L/s. Share and reopen.
  - **Flow 2, "Blocked discharge"** (V1 isolated), Solve all: partial lift 9.30759 L/s, lift 0.703762, inlet 299.8260 kPa(g), back 0.1207 kPa(g), Δp 107.04 % of set, capacity 13.40724 L/s, 69.42 % of it, with the partial-lift warning; Compare's default rows hold RV1's flow, state and inlet.
  - **Flow 3, "Smaller valve"** (blocked, letter E): full lift 2.086091 L/s, inlet 321.5098 kPa(g), 102.17 % of capacity. "Gagged" (blocked, locked closed): 323.0392 kPa(g) (W).
  - **Flow 4, goal seek (sizing)** in the blocked case with RV1 an effective area: the area for an inlet of 308 kPa(g) (1.1 × 280, discharging to atmosphere) is 447.0709 mm² (0.69296 in²; lift 0.99732), covering letter H; apply as a new scenario.
  - **Flow 5, export:** the dialog lists Relief valves, one row per case.

### 7.7 Checks (`synth/*.py` and `reviser/*.py`, each with its `*.out.txt`)

| # | Check | Result |
|---|---|---|
| S1 | The law's identities (`s1_law_checks`, `s1b_slope`) | (a) Q → Δp → Q through the forward law: 4.6×10⁻¹⁰ (the forward lift's cancellation, decision 13); (b) root and slope against 60 digits: 8.2×10⁻¹⁶, 7.9×10⁻¹⁶; (c) continuous at Q_f, slope 825.65 → 18,990; (d) least band ratio = op/(2 + 3op) at op 0.001, 0.1, 0.25, 1; (e) §3.2's table; (f) `API520_A_l` +6.092144×10⁻⁵ for all 14 letters; Kv(10E) on F at 5 L/s 0.99979 (1 mPa·s) and 0.97941 (0.1 Pa·s); (g) the trigonometric root covers the band for op ≤ 1/3 exactly (op²(1 + op) = 4/27; P's memo said 0.3466) |
| S2 | Cases C1–C9 against the real solver with the law in a check valve's link (`cases`, `harness`) | §7.1; flows ≤ 1.4×10⁻¹⁴ relative; C7 started open loses the inlet pressure; the system curve 1.7×10⁻¹² m. (The script's own C9 closed form omits AF1's ρv²/2; the table's solver value is right, as review-1's closed form confirms.) |
| S3 | Whether V's EPANET and closed-form runs of law C are this design's law (V's `laws.py`, `cases.out.txt`) | Yes where the outlet discharges to atmosphere: V's law reads the EGL drop with equal port elevations and ω = 10 % of a 500 kPa set; C1–C3 reproduce V's R2–R4 (C2: 0.002221210802347752 against V's 0.002221210802347735), so V's E2a, E2b and E2d serve as E1–E3 |
| S4 | Goal-seek inverses (`gs`) | §7.3; each forward solve meets its target |
| S5 | W's e2e network under this design's law (`e2e`) | §7.6. W's proportional emulation read the lift on the inlet gauge pressure: 9.32663 L/s and 299.7482 kPa(g) against 9.30759 and 299.8260 here |
| S6 | `relief_check`'s pilot and its triage (`relief_check_pilot`, `_open`, `relief_check_closed`, `triage`, `triage_closed`) | §7.4 |
| R1 | Q1's alternatives with the real solver (`measure` A, `falling`; laws in `alt_laws`) | (f) Fig. 4-12's rising branch below half lift and the chord to the certified point, against (a): network M at p_R 1.004–1.11 MPa, p_in +1.56 to +3.63 kPa (+0.31 to +0.73 % of set), Q −4.5 to −19.4 %; C6 +2.744 kPa (+0.78 %), Q −1.40 %; W's e2e (blocked, J) +2.478 kPa (+0.88 %), Q −6.60 %. Below half lift (f) equals review-1's Fig. 4-12 law to the digits (`fig412`). The falling branch (full lift down to 95 % of the set difference, closing at 90 %): C2 p_in −17.19 kPa (−3.44 %), Q +85.4 %; C6 −42.10 kPa (−12.03 %), Q +19.4 %; e2e −18.25 kPa (−6.52 %), Q +37.7 % |
| R2 | The overpressure's basis on C6 (`measure` B; review-1 `op_basis`) | On the gauge set (op_eff 0.105924): Q 25.1245 against 25.3089 L/s, p_in 368.449 against 367.016 kPa(g); full lift at zero built-up back pressure 385.000 against 383.043 kPa(g); at an inlet of 385 kPa(g) both at or past full lift, Q 0.03237665423 m³/s each |
| R3 | C5 inside ASME's scope (`measure` C) | §7.1; solver 3.3×10⁻¹⁵ relative |
| R4 | G41 on an effective area (`measure` D) | A* 1.2866259342×10⁻³ m² at 385 kPa(g), the forward solve's p_in 385 kPa(g) to round-off; `API520_A_l` at the solved state A* × (1 + 6.092144×10⁻⁵); `API520_round_size` L. At the old target, 380 kPa(g), the same A* as before (1.33489895×10⁻³). A one-shot required area at the solved flow (Q3 (b), `oneshot`) is +12.1 % with L in the band and −5.5 %, −31.5 % and −57.3 % with K, J and H beyond full lift |
| R5 | C16, the closed loop (`closed_loop`; review-2 `closed_loop_probe`) | §7.1; loop flow 4.4×10⁻¹⁶ relative to the closed form, started closed or open |
| R6 | C15 and G42 (`certified`) | §7.1, §7.3; solver 1.2×10⁻¹⁴ relative; G42's forward solve 0.0025 |
| R7 | EPANET with Q_f tabulated (review-1 `epanet_check`, re-run) | E1–E3 reproduced; at Q_f −3.808×10⁻⁴ without the point, +1.384×10⁻⁵ with it |

---

## 8. Files to change

**API** (`apps/api/src/opensolve_pipe/`):
- `models/components.py` (`ReliefValve`, the capacity union of three kinds and its error, the union, `x-relief-data`);
- `models/results.py` (`ReliefValveResult`, `SolvedState.reliefValveResults`, `FlagCode` `RELIEF_VALVE_OPEN` and `RELIEF_VALVE_CLOSED`);
- `models/scenarios.py`; `models/goal_seek.py` (`ElementKind` gains `relief_valve`, `LOG_FIELDS`, the two goals);
- `services/solver/{builder,valves,status,results,trace,methods,flags,version}.py` and the new `services/solver/relief.py`;
- `services/scenarios.py` (`COMPONENT_NAMES`, `value_text`); `services/goal_seek.py` (`goal_value`, the default start, the bound builds);
- the new `data/api526_orifices.json` and `scripts/generate_relief_data.py` (with `--check`).

**API tests and tools** (`apps/api/tests/`):
- `reference/`: `element_laws`, `case_format`, `network_check`, `closed_form` (registers the new cases), `build_closed_form_cases`, `generate_epanet_cases`, `test_reference_cases`, `test_derivation_checks`, `test_derivations_current`, `test_system_curves`, `test_goal_seek`, `derivations_goal_seek`, `test_scenarios`, `scenario_patch` (all `.py`); the new `derivations_relief.py`, `cases/relief_*.json` and `cases/epanet_relief_*.json`.
- `unit/`: `test_relief.py`, `test_relief_model.py`, `test_schema_rules.py`, `test_methods.py`, `test_flags_audit.py`, `test_goal_seek_models.py`, `test_scenario_models.py`, `test_web_export_fixture.py`, `scenario_patch.py`.
- `fixtures/`: `export_input`, `scenario_cases`, `goal_seek_cases`.
- `differential/`: `scenario_check`, `goal_seek_check`, `compare`, `equipment_check` (`head_bound`), `test_harness`, `test_compare_tolerance`, `test_goal_seek_check_smoke`; the new `relief_check.py` and `test_relief_check_smoke.py`.
- Unchanged: `generator.py`, `fuzz.py`, `checks.py`, `epanet_model.py`, `corpus.py`.

**Web** (`apps/web/`):
- `src/lib/api/{openapi.json,schema.d.ts,types.ts}` (regenerated);
- `utils/{factory,edit,units,model-rules,validate,results,compare,goal-seek,scenarios,labels,flag-text,issue-text,system-curve-text}.ts`, `utils/export/{tables,about,units}.ts`;
- `components/panel/{kinds.ts,PanelNavigator,AddComponentDialog,NewComponentFields,ComponentPanel,ConnectionPanel}.svelte`, the new `ReliefValveFields.svelte` and `forms/ReliefValveForm.svelte`, `forms/ControlValveForm.svelte` (the PSV hint), `forms/CheckValveForm.svelte` (the cracking-pressure hint);
- `state/workspace.svelte.ts` (`INLINE_KINDS`, `openDischarge`); `components/results/{ResultsPanel,CompareRowsDialog}.svelte`; `components/workspace/goal-seek/VariableCard.svelte` (the area unit);
- `testing/{helpers,results}.ts` (`reliefProject`); the regenerated fixtures; the new `tests/relief-valve.e2e.ts`.

**Docs:**
- **CLAUDE.md:** D1 and D5 (relief valves leave Later, keeping balanced, pilot, pop, gas and two-phase relief deferred); a new D22 with the model, the law, the named departures, the GOALS §5 exception the owner accepts or not (Q1), the owner's answers, the status integration and the proof; D10's list of `x-` extensions gains `x-relief-data`; D15's allow-list and D16's variable and goal lists amended in place; the status line.
- **PRD:** §3.1.2 (the row becomes v1: "Set pressure (a difference), capacity: API 526 letter or effective area (preliminary), or certified area, K and overpressure (ASME default)"), §2.3, §3.8, §3.9 and the Later list.
- **SDD:** §3.2.1 (drop "pressure relief valves" from its Later line, `SDD.md:381`, and add the relief valve's preconditions to the topology checks), §4.2 (drop "Later: … ReliefValve"), §4.10, §4.12, §4.13, a new §4.18.
- **TSD:** a new §4.11, §5.3, §5.7, §8.3, §10.1, §10.4, §12.
- README; `docs/prompts/continue-v1.md`; this proposal, marked built with an as-built section.

---

## 9. Later

- **Balanced-bellows and pilot valves** (set on the inlet's gauge pressure, API520_W's Kw): a held inlet head with droop needs a linear term in `LinkState.head`, the held-reference Jacobian term, `psvstatus` with a band and level-dependent tests in closed-off and floating sections (P). A modulating pilot that holds its inlet at set is today's PSV with a full-lift K, (A_in/C)² (V: exact to 10⁻¹⁶).
- **Pop action, blowdown and chatter reporting**: the falling branch of the lift characteristic (Pentair Fig. 4-12), two steady states inside the blowdown, which D13 requires to be reported (R1 measures their size).
- **The overpressure on the in-situ gauge set** with a superimposed back pressure, if the owner chooses it (Q4 (c)): a superimposed back pressure input, or a level-dependent law.
- **A manufacturer's pressure–flow or lift curve.**
- **API 520's Kv** (10E, exact at full lift as a quadratic plus linear law), **Kc** for rupture-disc combinations, and **non-certified valves** (API 520's Kd 0.62 with Kp at 25 % overpressure, via Technical Toolboxes, once read in API 520).
- **A nameplate rated capacity** (water at its stamped overpressure) as a capacity kind, once its rating conditions are cited.
- **A one-shot required area** on every relieving valve's result (Q3 (b)), with its departure from self-consistent sizing stated.
- **Gas, steam and two-phase relief** (API520_A_g, API520_A_steam, API 520 Annex C), and a **free-draining discharge** (an open tailpipe empty while the valve is closed).
- **A one-port valve discharging to atmosphere** (a new conditional boundary under D1).
- **A failed-open status.**
- **Relief design checks** (D19 extensions, each once its standard is read): overpressure at the solved flow within an allowable value, API 520 Part II's 3 % inlet loss at rated capacity, built-up back pressure within 10 % of set for a conventional valve.
- **The check valve's cracking pressure on the static difference** (h_c = Δp_c/(ρg) + z_in − z_out, as the relief valve's h_set): a method change for every project with a cracking check valve between ports at different elevations, proven by D13's corpus comparison with those differences named in `METHOD_CHANGELOG`.
- **The zero-flow multiplicity** around closed elements that bound a closed-off or floating section (§3.4; D9, D13), for every status element.
- **A fuzz profile `relief`**, if `relief_check` or the review finds a difference.
- **Web:**
  - a "Relief valves" Summary card;
  - the discharge choice at creation (a "Discharges to" radio on the create paths);
  - the schema-trim build plugin (W8, a separate `web/` change);
  - an open discharge on any free port;
  - a "would chatter" explanation;
  - a schematic symbol (ui-ux item 15).

---

## 10. Owner questions and answers

**Owner's answers (2026-10-28).** The owner chose the recommended default for every question; all stay reversible under D14.
1. **Q1, the band: (a), as recommended.** The lift rises linearly from set to full lift at set plus overpressure, with API 520's equation at that lift; every relieving state short of full lift is flagged (`CORRELATION_OUT_OF_RANGE`, `partial_lift`), the departure from Pentair's Fig. 4-12 is named in the methods and the trace, and the owner accepted that this band ships as an exception to GOALS §5's Verifiable gate and §4.1, recorded in D22. The question put the alternatives' measured consequences; none was chosen.
2. **Q2, the set: (a), as recommended.** A pressure difference, inlet minus outlet static (a conventional spring-loaded valve); balanced-bellows and pilot valves stay Later.
3. **Q3, the capacity: (a), as recommended.** Three kinds, never mixed: an API 526 letter or an API 520 effective area, each with Kd 0.65 and ASME's overpressure, labelled preliminary; or a certified actual area with its rated coefficient and optional overpressure. Sizing is goal seek on the effective area, with the covering API 526 letter in the result.
4. **Q4–Q8: as recommended.** ASME's overpressure (10 % or 3 psi, whichever is greater) as the labelled default only for sets of at least 15 psi, a user overpressure only on a certified capacity, taken on the set difference (Q4); statuses active and locked closed (Q5); discharge to atmosphere as a "Discharge to atmosphere" action at a relief valve's free outlet (Q6); no relief design checks in this slice (Q7); "Pressure relief valve (API 520, liquids)", id prefix `RV`, never abbreviated PRV or PSV (Q8).

The questions as put to the owner follow.

Product choices only. Each has a recommended default, which the build uses unless the owner says otherwise; all stay reversible under D14. The physics choices (the pressure reading of decision 5, the opening reading, the closed start, the refusals, the flags, the exact constant) are decided in this design and stated in every trace.

1. **The steady state between set pressure and full lift, and the GOALS §5 exception it needs.**

   **What the sources give.** API 520 and ASME certify one point, the capacity at set plus overpressure. The one lift characteristic read is Pentair's typical liquid-trim curve (TP-V300 Fig. 4-12):
   - almost no lift up to the set, about half at 107 % of set, then a surge to full lift;
   - on falling pressure, full lift down to about 95 % and reclosing near 90 %, two steady states between.

   It is a schematic, and gives no law for other overpressures.

   **What any choice costs.** Every single-valued law departs from it, is flagged as a warning in the band, and is named in the methods and the trace. None can be verified against a cited source there, so this slice ships the band as an exception to GOALS §5's Verifiable gate (and §4.1), which D22 records. The reference cases verify only the implementation.

   **Recommended: (a)** the linear lift from set to full lift at set plus overpressure, API 520's equation at that lift:
   - exact at the two points ASME certifies;
   - one steady state, and a closed form in every trace;
   - the model of Simscape and AFT Impulse, so results can be reproduced there;
   - inside Fig. 4-12's hysteresis loop up to 70 % lift and above its rising branch beyond.

   **Its measured consequences (R1), at the same supply:**
   - the figure's rising branch (with (f)'s chord across the surge) puts the inlet 0.31–0.88 % of set higher than (a), with 1.4–19.4 % less flow;
   - a valve that has surged open (the falling branch) puts it 3.4–12.0 % of set lower than (a), with 19–85 % more flow.

   **Alternatives, measured on the same networks:**
   - **(b)** A regulator holding its inlet at set until its capacity is used (today's PSV with a full-lift loss). The pump bypass C6 passes 8.2 % more flow at a 4.6 % lower inlet pressure; C2, 1.85 times the flow; 1 kPa above set on a stiff supply, 27 times, the flow then set by the inlet piping's friction (V). It is how a modulating pilot behaves, not a spring valve.
   - **(c)** A pop valve, closed or fully open. An oversized valve has no steady state (C6's L orifice opens to an inlet below set; W's e2e network drops to 66.7 % of set), reported as not converged. With blowdown, two valid states that D13 requires to be reported (their size: R1's falling branch).
   - **(d)** Today's check valve, documented, with no new element. Cracking pressure = set and K = (A_in/C)²·op/(1 + op) on the inlet bore.
     - *Exact* at both certified points (closed at set; Q_f at set plus overpressure).
     - *No upkeep:* no solver element, `METHOD_VERSION` or corpus proof (GOALS §5).
     - *In the band* it rises as a square root: at 5 % overpressure it passes 1.45 times (a)'s flow, at 1 %, 3.3 times.
     - *Beyond full lift* it understates the protected pressure: at a given flow it needs a smaller difference than API 520, 8.45 % at 1.05 Q_f, 16.76 % at C3's 1.107 Q_f, 27.8 % at 1.2 Q_f.
     - It reads the EGL difference (§1.3 item 15) (review-2, `q1d_check_valve_fit`).
   - **(e)** The manufacturer's curve: Later.
   - **(f)** Fig. 4-12's rising branch below half lift (half lift at set + 0.7 op), then the chord to the certified point. It never puts the inlet below the figure's rising branch or below (a): the conservative side for the protected pressure. It reads two numbers off a schematic made for a 10 % valve and scales them with op, an uncited extrapolation.
   - **(g)** Refuse partial lift (no result in the band): every oversized valve gives no answer, though the full-lift and closed states are cited.
2. **What the set pressure is measured against.** Recommended: **(a)** the pressure difference across the valve, as a conventional spring-loaded valve opens:
   - discharging to atmosphere at its elevation it is the gauge set pressure;
   - with a return line the user enters the bench setting (set minus the back pressure, as Pentair's pump example), and back pressure built up by the flow raises the inlet pressure;
   - it reuses the check valve's rules.

   **(b)** The inlet's gauge pressure (balanced bellows, pilot): new level-dependent solver rules; Later.
3. **How the capacity is given, and whether this slice sizes a valve** (the request: "a capacity sized by API 520 (fluids' API520_A_l)").

   **Recommended: (a)** three kinds, never mixed:
   - an API 526 letter or an API 520 effective area, each with API 520's effective coefficient 0.65 and ASME's overpressure, labelled preliminary;
   - or the certified actual area with its rated coefficient and full-lift overpressure.

   Sizing is goal seek on the effective area against the relieving pressure:
   - exact and self-consistent with the network: the flow the pump delivers at that pressure and the back pressure it builds;
   - equal to `API520_A_l` at the solved state within its constant's 6.09×10⁻⁵ (G41);
   - the smallest API 526 letter covering it shown in the result and trace.

   **Alternatives:**
   - **(b)** Also a one-shot required area on every relieving valve, `API520_A_l` at the solved flow and the full-lift difference: one number with no goal seek, but not self-consistent. On C6 it is 12.1 % high for a valve in the band and 5.5–57 % low for valves beyond full lift (R4). Later.
   - **(c)** The forward capacity only (a letter or certified values), sizing Later. Goal seek could then size only by entering 0.65 as a certified coefficient, the mix decision 7 forbids, labelled certified in the trace and export.
   - **(d)** Also a nameplate rated flow at a stated overpressure: Later, until its rating conditions are cited.
   - **(e)** Certified values only: no preliminary sizing.
4. **The overpressure: its default, where a user value goes, and its reference with a back pressure.**

   **Recommended: (a)**
   - ASME's liquid certification overpressure, 10 % of the set or 3 psi, whichever is greater, labelled default, for a set of at least 15 psi (ASME VIII's scope); below it the overpressure must be entered (a letter or effective area is then refused, with the remedy).
   - A user overpressure only on a certified capacity: the valve's own full-lift overpressure. API 520's preliminary pair (0.65 with a letter or effective area) always comes with ASME's, never 0.25 or another value.
   - The overpressure taken on the set difference, as the lift's force balance is. With a superimposed back pressure P_b, full lift comes op·P_b below the in-situ relieving pressure (C6: 383.04 against 385.00 kPa(g); in the band 1.43 kPa lower, 0.73 % more flow); at the relieving pressure, API 520's flow and sizing are the same either way.

   **Alternatives:**
   - **(b)** Required on every valve, with no default: every user looks it up, and most will type 10 %.
   - **(c)** The overpressure taken on the in-situ gauge set, as the definitions and API 520's P1 are. It needs the superimposed back pressure as a second input that must match the network's outlet pressure at zero flow (or a level-dependent law): Later.
5. **Statuses.** Recommended: **(a)** active and locked closed (gagged or blocked), so a scenario shows the pressure without relief. **(b)** Also failed open (stuck at full lift): Later.
6. **Discharge to atmosphere.** Recommended: **(a)** two ports always.
   - A relief valve's free outlet offers "Discharge to atmosphere": a reference node at 0 kPa(g), 1 m of pipe with an exit, at the valve's elevation, one undo step.
   - Its friction is solved as built-up back pressure.

   **Alternatives:**
   - **(b)** The same choice offered when the valve is created (five create paths): Later.
   - **(c)** A one-port valve to atmosphere, a second menu entry and a new kind of boundary: Later.
7. **Relief design checks** (overpressure limit, built-up back pressure, API 520's 3 % inlet loss). Recommended: **(a)** Later, as D19 extensions once each source is read; the results already show Δp ÷ set and flow ÷ capacity. **(b)** In this slice: uncited limits, or a user-limit-only check.
8. **Name and identity.** Recommended:
   - "Pressure relief valve (API 520, liquids)" in its own group after Control valves, id prefix `RV`;
   - never abbreviated PRV or PSV (this app's PRV and PSV are EPANET's pressure-reducing and pressure-sustaining valves);
   - the PSV and check valve forms' hints pointing relief users to it.

---

## 11. Review record

Two reviewers checked the design (review-1: 10 findings; review-2: 9). The reviser verified each by reproducing it or by reading the code or source, and revised the design at the root where it was upheld. Numbers are the review's order. R-checks are in §7.7.

| # | Severity, finding | Verdict | Verification | What changed |
|---|---|---|---|---|
| 1 | Blocking: the "uncited" band is contradicted by Pentair's Fig. 4-12, and the linear lift puts the inlet below its rising branch | **Upheld** | The figure and its text are in the downloaded handbook (p. 4.8, `handbook.txt` 2725–2750; rendered page `review-1/fig/q-046.png`). R1 reproduces review-1's rising-branch numbers to the digits, and adds the chord above half lift, C6 and W's network. It also measures the figure's falling branch, a second state 3.4–12 % of set lower. | §1.1's first departure rewritten (the figure, both branches, the measured consequences, the GOALS §5 exception); decision 3 and §3.10 cite it; Q1 rewritten with (f), (d) measured and (g); trace notes, methods summary, changelog line and form hint name it; the band warning (finding 7); §3.4 names the falling-branch state (D13). The linear law stays recommended (Q1 says why), for the owner to decide. |
| 2 | Blocking: the overpressure on the differential set puts full lift op·P_b below API 520's relieving pressure | **Upheld in part** | Pentair's definitions and fluids' source (P_set = (P1 − atm)/(1 + overpressure)) read as stated. R2 reproduces C6 (1.43 kPa, 0.73 % flow; 383.04 against 385.00 kPa(g)). Not upheld: that the design's reading is an established error. The certification fixes full lift only at atmospheric back pressure, and the lift's force balance (Pentair ch. 4: back pressure acts on the disc, adding to the opening pressure and helping an open valve reseat) supports the difference. At the relieving pressure both readings give API 520's flow and the same size (R2, G41). | Named as a third departure (§1.1) with its size, in decision 6, §1.3 items 1 and 4, the trace (the gauge-set overpressure that would put full lift at the relieving pressure) and Q4 (c); the earlier sentence that `API520_A_l` "takes pressures, not their reference" now limits itself to P1 and P2. |
| 3 | Should fix: the advice to enter op 0.25 for a non-certified valve on a letter gives 9 % less Δp than API's pair | **Upheld** | (0.62/0.65)² = 0.9098; the proposal's own source table gives Kd 0.62 at 25 % for non-certified valves. | The advice is gone. The overpressure moved into the certified kind, so API 520's preliminary pair always comes with ASME's overpressure (decisions 6–7). The field says it is the full-lift overpressure, not the allowable overpressure of sizing (Pentair ch. 3: 16 %, 21 %). Non-certified valves (Kd 0.62 with Kp) are Later. |
| 4 | Should fix: the trace's "interval the certification allows" is not supported | **Upheld** | Pentair: liquid valves have fixed blowdowns (an open valve passes flow below set, Fig. 4-12); Table 3-2's set tolerance; rated K = 0.9 × measured. | The interval is gone from the trace (§4.1) and from the warning (finding 15). The notes state the figure's characteristic, the set tolerance and the rated-coefficient margin as what the certification does not bound. |
| 5 | Should fix: C6's setRatio is the static ratio | **Upheld** | `synth/cases.py` prints `(p_in − p_out)/Δp_s` as "dp/dps"; review-1's closed form gives Δp_t/Δp_s 1.07913442325 and the static ratio 1.0508690913. | C6's row gives setRatio 1.07913442325 and labels the static ratio. |
| 6 | Should fix: the default overpressure leaves the field's bounds, ASME's scope and the tested root range | **Upheld** | 3 psi/Δp_s > 1 below 20,684.27 Pa; Pentair puts sets below 15 psig "outside of the scope of ASME"; review-1's `root_bigop` loses digits as op grows. | The default applies only for a set of at least 15 psi (then 0.1–0.2); below, a defaulted overpressure is refused with a remedy (decision 14, §3.7). op ≤ 1 everywhere, inside S1b's range (§3.1). C5 moved to a 150 kPa set (R3), and the goal-seek set box keeps its 15 psi floor (W6). |
| 7 | Should fix: operation in the uncited band gets only an info flag | **Upheld** | GOALS §4.6; D18's and D20's warnings for their unsupported regions. | `CORRELATION_OUT_OF_RANGE` (warning, `partial_lift`) on every state short of full lift; `RELIEF_VALVE_OPEN` (info) at full lift only (decision 15, §3.6); C2 and the e2e's Flow 2 expect it. |
| 8 | Nit: C9's closed form in the synthesizer's script omits the velocity head | **Upheld** | `cases.out.txt` gives 83,014.79843 against the solver's 82,817.09534; review-1's closed form gives 82,817.0953385. | C9's derivation says AF1's pressure subtracts ρv²/2 (D7); S2 notes the script's slip. |
| 9 | Nit: the EPANET curve should tabulate Q_f | **Upheld** | Re-ran `review-1/epanet_check`: at Q_f −3.808×10⁻⁴ without the point, +1.384×10⁻⁵ with it; E1–E3 reproduced. | Decision 24 and §7.2 tabulate 0, Q_f and the 201 points. |
| 10 | Nit: G41 is called "set plus 10 %" but targets 380 kPa(g) | **Upheld** | 1.1 × 350 = 385 kPa(g). | G41 targets 385 kPa(g) on an effective area (finding 11): A* 1.2866259342×10⁻³ m² (R4). |
| 11 | Blocking: the only sizing route breaks the no-mixing rule, and the owner's `API520_A_l` sizing was deferred without asking | **Upheld** | G41 and e2e Flow 4 entered 0.65 in the certified kind, which the trace and export then label certified; Q3 asked only how the capacity is entered. | A third kind, `effective` (an API 520 effective area, Kd 0.65, preliminary), whose area goal seek varies. G41 shows sizing by API 520 against the network (equal to `API520_A_l` at the solved state) and names the covering letter (`API520_round_size`). Flow 4 uses it, with unchanged numbers. Q3 now asks whether the slice sizes, with the one-shot required area measured as (b) (R4). |
| 12 | Should fix: a closed loop whose only fixed head is the relief valve's discharge loses the valve from the results with no flag of its own | **Upheld** | `results.py:967–973` and `1246–1285` read as stated. C16 (R5) reproduces the probe with the pump on its curve. | `RELIEF_VALVE_CLOSED` (info) on a valve with a closed-off or floating side, naming the range of levels (decisions 15–16, §3.6, §3.8); C16 pins the closed start; §3.4 names the open start's state as the highest of those levels (D13). |
| 13 | Should fix: the check valve's cracking pressure reads the EGL difference and the relief valve's set the static one, with the same words | **Upheld** | `builder.py` (`h_c = cracking_pressure/ρg`), `status.py:549`, `trace.py:1711`; review-2's run opens near 119.6 kPa with a 2 m rise. | §1.3 item 15 and §3.4 name it; the relief hint says "static"; the check valve's hint states its reading and points to the relief valve; the trace notes both; Later lists moving the check valve, with its D13 cost. |
| 14 | Should fix: Q1 (d) is not measured | **Upheld** | Review-2's `q1d_check_valve_fit` arithmetic re-derived: K = (A_in/C)²·op/(1 + op) fits both certified points. | Q1 (d) carries its strongest form, its upkeep advantage and its numbers; decision 26 and the check valve hint carry its beyond-full-lift warning. The type choice stands (decision 1 adds the web test reviewer 2 found). |
| 15 | Should fix: the band is flagged only as information, and its GOALS §5 exception is not put to the owner | **Upheld** (as finding 7) | GOALS §4.6, §5; the reference cases test the law against itself in the band. | The band warning (finding 7); Q1 and §1.1 state the §5 and §4.1 exception for D22. Not adopted: the warning's message quoting the "certification interval", which finding 4 shows is not supported. |
| 16 | Should fix: the files list misses places D18 and D20 touched | **Upheld** | Each read in `a374ef0`, `0383aef` and the tree: `validate.ts` `taggedSchema`, `PanelNavigator.svelte`, `closed_form.py`, `equipment_check.head_bound`, the two smoke tests, `goal_seek.ElementKind`, `SDD.md:381`, D10's extension list. | §8, §7.1, §7.4, §7.6 and W1 name each. |
| 17 | Nit: API 526 areas read from fluids at run time, not a generated data file | **Upheld** | CLAUDE.md's convention; `data/` holds `fittings.json` and `pipe_materials.json`; `generate_pipe_data.py --check`. | `data/api526_orifices.json` from `scripts/generate_relief_data.py` with `--check`, read by the model and `x-relief-data` (decision 27). |
| 18 | Nit: "discharging to atmosphere it is the gauge set pressure" needs the outlet at zero gauge | **Upheld** | §3.2's liquid-full rule. | The schema text, decision 2 and the hint say "at the valve's elevation", and §3.2 gives the ρgΔz rule. |
| 19 | Nit: the web scope exceeds D18 and D20 | **Upheld in part** | `SummaryView.svelte` has cards for pumps, checks and extremes only; D18 has 3 Compare rows and D20 4; `DEFAULT_ROW_LIMIT` 40. | The Summary card and the creation choice moved to Later; the open discharge is one `ConnectionPanel` action. Compare has 5 rows (lift and flow ÷ capacity dropped), the default rows sit after the pumps'. Not adopted: dropping the `area` unit category, the only way to enter an effective or certified area. |

---

## 12. As built

The valve was built from §1–§11 on `main` at `b7f09eb`, the commit this design was written against, after a contract checkpoint (`d05bb7d`). The decision is **D22** in CLAUDE.md; the specs are PRD §3.1.2, SDD §4.18 and TSD §4.11. The API builder ran the checkpoint's law through the real solver and kept it: it matches every number §7 prints for C1–C7, C9, C10, C15 and C16 (flows to the digits printed, within 2.6×10⁻¹³ relative, their rounding; C8's within 3.5×10⁻¹³; the case files within 10⁻¹⁴), and C11, C13 and C14 give the states and flags they expect. The reference tester derived every case anew without reading `services/`, and the solver met them all at the first integrated run (2,673 reference tests passed); no solver or derivation fix was needed.

**Proof.** The corpus comparison against `b7f09eb` (5,168 projects, system curves included): 5,168 identical, 0 different, with `--ignore-empty reliefValveResults` and the two method-version paths; the 21 relief cases only on the branch. On the branch's 5,189-project corpus: `relief_check` 0 different in all three modes (`band` 323 valves in 302 projects, 161 reversed; `full` 420 in 389, 211 reversed; `closed` 803 closed and 63 with no result in 866 projects; the largest differences 1.05×10⁻⁹ of the largest flow and 4.47×10⁻⁶ m of head in the open modes), `scenario_check` 0 different, `goal_seek_check` 0 violations (15,558 goal seeks; the relief cases 84 draws), `equipment_check` and `orifice_check` 0 different, the three fuzz profiles the same 9,000 records as `b7f09eb`, `missing_result_check` at its baseline. TSD §10.4 has the counts and the triage of every listed project.

**Design checks (D19).** None applies to the valve, as decision 22 says; only pipe velocity covers its two connections, as for any pipe (`test_relief.py`).

Where the build departs from this design, each departure is reversible (D14), and none weakens a rule of the design:

**Solver and API**

1. **System-curve points start an active relief valve open**, as a check valve starts; solves keep decision 11's closed start, and `locked_closed` stays fixed closed. With the closed start, a pump whose only way out is the valve had no head at any flow above 0 on a cold `/system-curve` request: the pump is a fixed flow there, the closed valve leaves it starved, and no rule re-opens the valve. This contradicted §3.5. The prototype's check (S2, B3) skipped points without a head, and C6 warm-starts from a solve where the valve is already open, so the design did not catch it. Now H_sys(0) is h_set plus the static terms and every point matches a closed form within 10⁻¹¹ m. The change is in `status.initial_controls`, only when forced flows are given; `system_curve.py` is unchanged. The methods section and the `status.py` docstring state it.
2. **`ReliefValveResult.flow` can be a little below zero.** §2.2 said "never below zero", but the status rule (EPANET 2.2 cvstatus) closes the valve only below −Qtol, so a valve open at its switch reports a flow in [−Qtol, 0) with state closed; six corpus projects in `relief_check`'s `closed` mode show −4.4×10⁻¹⁰ to −3.6×10⁻⁹ m³/s. Only the field's description changed (the regenerated `openapi.json` and `schema.d.ts` differ only in that string); no value changed. The web's About sign row says so too (`utils/export/about.ts`, pinned at `export/relief.test.ts`), and the trace says "open at its switch, reported closed" for such a valve (item 43).
3. **`RELIEF_VALVE_CLOSED`'s details** are `side`, `section` (`'floating'` or `'closed_off'`), `setHead`, `setPressure` and, where the other side has a head, `pressureLimit` (the level that keeps the valve closed). §3.6 names `side`, `floating` and h_set, but flag details hold only numbers and strings, so the boolean became the string `section`.
4. **Flashing at the outlet** uses the app's shared rule (`results._below_vapor_pressure`): strictly below the vapor pressure, or at or below 0 Pa without one, as ports and orifice plates do. §3.6 says at or below the vapor pressure.
5. **`x-relief-data` sits on the `ReliefValve` schema**, not on the capacity union (§2.1, §2.3), where the web reads every other extension (the union is inline and has no named schema), and holds two more values than §2.1 lists: `effectiveDischargeCoefficient` (0.65) and `asmeOverpressureFraction` (0.10), beside `api526Areas`, `asmeOverpressureFloor` and `asmeMinimumSetPressure`.
6. **`x-override-fields` publishes `holders`** for a value that more than one member of a union holds: a relief valve's `capacity.area`, held by `EffectiveOrifice` and `CertifiedOrifice` (`Overridable.also_held_by`; the bounds are the first holder's, pinned equal by a unit test). `plan_override` accepts any holder.
7. **The trace's "Head loss by the law"** shows only while the valve relieves. On a closed valve it read h_set beside the solved difference, which looked like a mismatch.
8. **Scenario value texts give areas in m²**, as every API value text is in SI ("API 526 J (0.000830321 m²), Kd 0.65 (preliminary)"); §5's examples show mm². `MISSING_HOLDER` has a reason for each of the four capacity values, and `_clean` drops the capacity union's tag from error locations.
9. **Goal seek's bound builds** treat ASME's 15 psi scope refusal at a set's bound as not applying when the same valve's overpressure is also a variable: every trial then writes an overpressure, never the default.
10. **Relief valve states go into goal seek's state map** under the existing `valve_state` aspect, so a crossing can name a relief valve opening. A new aspect would have changed the model and `openapi.json`.
11. **Goal seek's section names the covering API 526 letter** of an effective area found, or says that none covers it above T.
12. **Version pins** moved to 1.5.0 as D20 did, with a new 1.5.0 changelog test; `test_trace.py` accepts the relief trace's two new units (`Pa^1.5·s/m³` for R and `s/m²` for dh/dQ), as D18 did for its own.
13. **`test_apply_scenario`'s order test** now shuffles the valid overrides in two scenarios of about half each: the relief entries took the list to 31, past the 30-override limit per scenario. Every entry is still shuffled and checked, and the whole capacity sits on a different valve than its parts.
14. **`tests/unit/scenario_patch.py`**, the independent patcher the corpus tools share, covers relief valves (fields, the kind rule, value draws, not-applicable overrides); its draws never give a defaulted overpressure below 15 psi, nor a whole capacity with one of its parts. 353 random relief overrides drawn from it matched `apply_scenario` with 0 mismatches.

**Reference cases** (the tester's choices)

15. **C8's second valve RVa is set at 340 kPa(g)** less the 2 m of tank head, not 350: at 350 its flow is 1.0029 Q_f, within D6 of the kink at full lift, so an answer D6 accepts could fall in the band and change the state and flags. At 340 it is 1.0184 Q_f. Beyond full lift the flow does not depend on the set, so §7.1's Qa, Qb and T2 EGL are unchanged and still checked.
16. **C9 and C11 are two cases each** (C9 at 600 and 450 kPa supply, `relief_assigned_demand` and `_low_supply`; C11 at 300/400 and 520/600 kPa, `relief_reverse_head` and `_above_set`), one network per case file.
17. **C16 is not a case file.** Its loop floats and has no EGL at any port, which the case format and its self-checks cannot hold (the reason `test_floating_sections.py` gives). It is `test_relief_valve_closed_loop_floats` there, against the closed-form loop flow.
18. **An added case, `relief_closed_off`:** a valve whose inlet side an isolated valve closes off, covering decisions 15 and 16 (no result, `RELIEF_VALVE_CLOSED` with `side`, `ISOLATED_SECTION`) through the case format's null entry.
19. **Inputs this design left open** (test inputs, as user data): C12 on 30 % MEG at 20 °C; C14 liquid A's density (998 kg/m³) at 0.2 Pa·s, its mains transitional and flagged `TRANSITIONAL_FLOW`; C13 also expects `BELOW_VAPOR_PRESSURE` on R2, whose open surface and port are below p_v at 120 °C (SDD §4.10); G43's base coefficient 0.65; G44's surface-pressure bounds [0.9, 1.3] MPa; G41's target the literal 385,000 Pa.
20. **C7 and C10 expect `PUMP_OUTSIDE_CURVE`** on PU1 (`details.curve` npshr, SDD §4.10), which §7.1 does not list: the pump runs at zero flow, below `curve_a`'s first NPSHr point at 5 L/s. No expected value changed.
21. **The EPANET mapping lives in `generate_epanet_cases.py`**; `tests/differential/epanet_model.py` is unchanged, as §8 lists it (§7.2's heading also names it). EPANET's flows match the design's measured runs within 6×10⁻⁸ and the closed form within 2×10⁻⁴.
22. **Kept from the checkpoint:** `element_laws.pump_state_problem` accepts a running pump at zero flow whose lift equals its shutoff head exactly (the dead end behind a closed relief valve, C7 and C10), and `derivations.water_properties` gives saturated liquid above the normal boiling point (TSD §4.6), which C13 needs.
23. **`network_check`** accepts a closed relief valve whose side has no head (a closed-off section).

**Corpus tools and fixtures**

24. **`relief_check`'s closed mode** sets C to the valve's own full-open equivalent, A_ref/√K_open (A_ref on a valve without loss), with K ~ U[0.6, 0.9] and area C/K; §7.4 gives no C for this mode, and this follows the pilot.
25. **`relief_check` has a third listed class**, "which nodes have results", beside §7.4's two: every difference is a node value present on one side only, and every flow is within D6 (D9's multiplicity: which zero-flow state a PRV gets). It covers `fuzz_497`, `fuzz_1225` and `fuzzfc_10223`. The "element at its switch" class needs the switching element's state or flow to differ between A and B; otherwise any open control valve at zero flow would qualify. A relief valve with no result in B is treated as at zero flow, as `network_problems` treats links.
26. **`relief_check` draws one RNG per project**, `Random(f"relief:{mode}:{name}")`, per valve in component order; the pilot used one seed per valve, so the counts differ slightly from §7.4's (band 302 projects against 297, full 389 against 386, closed 866 against 870).
27. **`compare.py`'s pressure keys** add `setPressure`, `backAbsolutePressure` and `pressureLimit` to §7.4's four, and `setHead` (`RELIEF_VALVE_CLOSED`'s h_set) as a head; `fullLiftFlow` stays "other" (10⁻⁶ relative).
28. **`export_input.scenario_project()`**: §7.6's "relieves in one scenario (with a letter change)" is S1, which sets RV1's `setPressure` to 270 kPa and its `capacity.letter` to K. RV1 sits on its own pressure tank R4 (level 2 m, 280 kPa(g)), a separate part of the network with fixed heads of its own, discharging through 1 m with an exit to N1 at 0 kPa(g), so its relief flow is coupled into none of the PRV, E1, O1 and E2 results (`test_export_input.py` pins R1 at two ports). Its outlet pipe is a size up, and Compare gets five relief rows.
29. **`test_web_export_fixture.py`'s lowest-pressure oracle** follows export.md §2.7's `lowestPressureNode` (the least absolute pressure, first in the API's `nodeResults` order) instead of the first in project port order: the two differ only on ties, and the fixture's closed relief valve outlet and its discharge reference node tie at exactly 0 Pa(g). Its scenario-change Value and Base value are empty for a change that was not applied (export review V2), for every field; the fixture has only applied changes, so no expectation changed. The relief sign row in About is checked for "+ inlet → outlet" and its three quantities, the fractions sentence to extend the earlier sentences and name Δp ÷ set, lift and flow ÷ capacity, a `capacity.letter` change exactly as "API 526 K (0.00118580408 m²)", and a whole capacity for its kind, its exact numbers and 0.65.

**Web**

30. **`src/lib/api/types.ts`** gained `ReliefValve`, `ReliefCapacity` and `ReliefValveResult` aliases: it is a hand-maintained alias file through which every web module imports schema types, not a generated one (`openapi.json` and `schema.d.ts` were only regenerated).
31. **The export sheet's id and CSV name** are `relief-valves` and `relief-valves.csv`, not §5's `relief_valves`, as every other sheet's id is kebab-case (`orifice-plates`).
32. **The Relief valves view and sheet list a valve with no result** from its `RELIEF_VALVE_CLOSED` flag, as "Closed (no result)" with every value "—", and the view also appears when a solve has only such flags; otherwise a valve closed off or beside a floating section would disappear from every table.
33. **The open discharge** sits at the outlet port's own elevation when the port has one, else at the valve's (decision 9 says "at the valve's elevation", the same unless a port elevation is set; the hint keeps decision 9's words), and is named "Open discharge N<k>".
34. **The form and fields are imported statically.** Lazy loading saved only 0.6 KB, because Vite split the shared code into another preloaded chunk.
35. **The certified overpressure** is a select of "ASME's 10 % or 3 psi (…)" or "Entered (certified)", with a fraction field when entered, as the orifice form's entered C.
36. **In an SI export file a null overpressure change** is written in the source's words, "ASME's 10 % or 3 psi, whichever is greater (the default)", without converting 3 psi: the SI file promises the API's exact values, and 20.68 kPa would be a rounded number.
37. **`OverrideField.holders` is optional** in `model-rules.ts`, present only where `x-override-fields` publishes it (today only `capacity.area`), so the existing exact-equality model-rules tests stay valid.
38. **About's "Units: areas" row and the extended fractions label** appear only in files with the Relief valves sheet, so files without a relief valve stay byte-identical.
39. **The e2e file is `tests/relief.e2e.ts`** (§7.6 named `tests/relief-valve.e2e.ts`). Its goal seek enters a 0.01 kPa tolerance: with the default (±1.54 kPa) the search may stop anywhere within about ±1.2 % of the area (it stopped at 448.262 mm²), too loose a check of the 447.0709 mm² reference; with 10 Pa the API gives 447.092 mm². Flow 1's inlet is 129.58 kPa(g), Flow 2's partial lift 9.308 L/s, Gagged 323.04 kPa(g), as §7.6 prints.
40. **The bundle** grew by 13.7 KB gzip on the initial `/p` download (297,151 → 310,820 B against `b7f09eb`, gzip -9 as TSD §8.3 measures, on the tree with the review fixes): 3.8 KB is the contract's `openapi.json` (`b7f09eb`'s code with this tree's schema: 300,940 B) and 9.9 KB the web code (4.9 KB in the `/p` page node, 2.7 KB in the shared openapi and model chunk, 2.3 KB in the utilities chunk), above W8's estimate of 7 to 8.5 KB, which did not count the schema. The export chunk grew by 1.0 KB (24,289 → 25,240 B). `third-party-licenses.txt` is byte-identical.

**After the review** (items 41–52)

41. **The representability refusal covers every value the law divides by.** C², which the full-lift branch divides by, underflowed to zero for a schema-valid certified area of 10⁻²⁰⁰ m² while C, Q_f and R were normal: a `ZeroDivisionError` in the solve (HTTP 500 from `/solve`, and from a goal seek whose bound reached it). The band root's trigonometric form divides by 2Δp_s√(Δp_s/3), which underflows for a set below about 3.6×10⁻²⁰⁶ Pa (on a certified capacity, which takes any set). Both are now refused (`relief.LAW_CONSTANTS`), each with its own sentence and remedy (the web's `issue-text.ts` reads only the C, Q_f and R sentence and shows the others as the server words them); with Kd·A underflowing to zero the text quotes Q_f = 0, not inf. Each rule stays monotone in each relief value, so goal seek's bound builds still prove every trial builds. Next to the band root's branch boundary, 27(RQ)² = 4Δp_s³, the two tests can round differently and Cardano's radicand, zero there, came out below zero (a math domain error, found at Δp_s 42.1 MPa, op > 1/3); it is held at zero, which changes no value where it was not negative.
42. **`RELIEF_VALVE_CLOSED` names the levels at which this valve stays closed**, not each as a steady state: around a closed-off or floating section other elements have rules of their own (two closed relief valves in series bound their middle section from both sides), so the message says that which of those levels are steady states depends also on them. It quotes the bound only, not the other side's pressure, which was round-off of zero (4.2×10⁻¹⁵ Pa(g)). The web's `flag-text.ts` builds its own text from `details`.
43. **The trace** gives ASME's default overpressure by its equation, op = max(0.10, 3 psi/Δp_s), and names the term that sets it at the set (the 3 psi floor at 150 kPa, the 10 % at 500 kPa); shows the full-lift K on the inlet bore, (A_in/C)², that the builder stores, with Δp_t = Kρv_in²/2 from Q_f on, for comparison; and says "open at its switch, reported closed" where the status rule keeps a valve open at a flow in [−Qtol, 0], which its result labels closed (item 2), instead of "Open, closed".
44. **Goal seek's `baseValue`** is null only for a value inside a capacity the base gives by another kind; a set pressure keeps the base's value when a scenario changes the capacity's kind (`goal_seek_check.rated_otherwise` read it so already).
45. **Tests added:** the static-difference opening inside the window between the two readings (outlet 0.5 m up at 502 kPa static opens; 0.5 m down at 498 kPa stays closed), the free-level rule's relief branch (`status._level_changes`, reached by two PSVs in a loop bounded by a closed relief valve), the viscosity flag at 0.1 Pa·s and one double below, each representability bound at its edge, and EPANET's network M closed form with Swamee–Jain in the relief branch too (it used Colebrook there, up to 6.8×10⁻⁵ off the reference flows). **Proof after items 41–44:** the corpus comparison against `b7f09eb` again 5,168 identical, 0 different (the same ignores); the 21 relief cases against the integrated tree before them, 0 numeric differences (only the trace's new lines and `relief_closed_off`'s flag message); `relief_check` 0 different in all three modes with the counts and largest differences above, `scenario_check` 0 different, `goal_seek_check` on the relief cases 0 violations (84 draws).
46. **A relief valve locked closed reads "Closed (locked)"** in the Relief valves view, the Build strip, trace values, Compare cases (on screen and in the export) and the export's Relief valves sheet (`relief.reliefStateLabel`). Its result alone cannot tell it from an active valve below its set, and its Δp ÷ set can be far above 100 % (213.9 % in the review's probe of the real API), where §6 W4's note said a valve relieves. The label reads the valve's status from the case's project as solved (the store's `caseInputs`), so it follows a scenario's status change and not an edit made after the solve. The view's note and `ReliefValveResult.setRatio`'s description say that above 100 % an active valve relieves and one locked closed stays closed (the regenerated `openapi.json` and `schema.d.ts` differ only in that string).
47. **The preliminary kinds' read-only line states ASME's scope**, "for a set of at least 15 psi (103.4 kPa), ASME VIII's scope" (from `x-relief-data`), which W3's line left out; for a set entered below it the line turns amber with the remedy (a certified area and coefficient with the valve's full-lift overpressure) and is linked to the letter select or the area field by `aria-describedby`, as the certified kind's default-overpressure line already was. The letter select marks an error with `aria-invalid` (`SelectField`'s new `invalid` prop).
48. **Trace areas show in the area unit.** `utils/trace.ts` converts a trace value in `m²` to the area unit (mm², m², in²), with the SI value beside it, so a relief valve's areas read as its form enters them. This also changes, on screen only, how every pipe's "area A", a valve's reference area and an orifice plate's inlet pipe area read in the trace view of projects without a relief valve; no value changes, the export's Trace sheet stays in SI as reported, and `m²/s` (a kinematic viscosity) stays as reported. SDD §4.10 and TSD §6.1's trace-value list say so.
49. **Labels inside sentences keep acronyms.** Undo labels read "change API 526 orifice letter" (`labels.inSentence` lowercases only a first word that is not an acronym of two or more capitals or digits, so "(K)" keeps its case), and goal-seek notices keep words in capitals and digits ("API 520 effective area"); no other variable label has such a word, so other notices read as before. The Discharge to atmosphere hint gives the stub's 1 m in the display length unit (3.281 ft in US units).
50. **A goal-seek variable names a relief valve's area by the capacity kind of the case shown**, as equipment's Cv and Kv already were: the card read "Orifice area" for a scenario that gives RV1 an effective area while the base has a letter. `VariableDraft` gains `capacityKind`; `withRatingKind` became `withCaseKind`, which also sets it for `capacity.area`, and `withKindsOfCase` replaced `caseRatingKind` for the result view and the found-value notices, with the same Cv and Kv results.
51. **The web's `RELIEF_VALVE_CLOSED` text** (`utils/flag-text.ts`) follows item 42: the valve stays closed at every level up to the bound, and whether such a level is a steady state depends also on the other elements around the section.
52. **The e2e flows** (`tests/relief.e2e.ts`) enter the effective area 830.32092 mm² and check the field's 6-significant-digit display, 830.321, with the goal-seek request's scenario holding the area as typed, 830.32092×10⁻⁶ m²; the scenario goal seek applies is "Goal seek 2", the second after "Sizing", as `goal-seek.e2e.ts` names them.

**Open items** (not departures):

- The web's `issue-text.ts` tells item 41's two new refusal sentences (C² and the band root's scale) in the server's SI words: its `RELIEF_LAW` form reads only the C, Q_f and R sentence. Correct, but not in display units.
- `x-goal-variables.ReliefValve['capacity.area']` names only `EffectiveOrifice` as its schema, with no `holders`. The web reads which kinds hold the area from `x-override-fields`, and both schemas have the same bounds, so nothing goes wrong; publishing `holders` there too would be cleaner.
- In `relief_locked_closed`, the pump's only way out is the locked-closed valve, and its system curve has no points; base projects behave the same way (`ref_pump_flow_control_dead_end`). Not specific to the relief valve.
