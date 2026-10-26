# Equipment pressure drop: design proposal

**Status: design, not built; the owner answered its questions on 2026-10-26 (§10).** This design was written on 2026-10-26 against `bbafbff` (D14) by a design workflow. Three designers worked from different angles, each with prototypes: one on the physics, model and solver, one on the sources and verification (citations read, closed-form cases, EPANET runs), and one on the web. A synthesizer merged their designs into this one. It checked the disputed claims against the code and by calculation (the **S** checks in §7.7) and wrote this document. §1.3 lists where the designs disagreed and why this design chose as it did. Two reviewers (physics, product) then checked it, and a reviser verified each finding and revised the design at the root. A second reviser then folded in the owner's answers, above all Q5: a rating may be a **Cv or Kv** in this slice (decision 22). Reviewers checked that revision, and a fixer verified each of their findings and fixed the upheld ones at the root. §11 records each finding and each revision.

**The owner's request (2026-10-26):** "Equipment pressure drop: a component for heat exchangers, strainers, filters and coils, entered as a datasheet pressure drop at a rated flow and scaled with flow² and density. Every real loop has some of these. Small, easy to check by hand, little upkeep."

D5 lists "heat exchangers, strainers … and user-defined elements" as deferred. This slice moves the rated-pressure-drop element into v1, rated by a pressure drop at a flow or, by the owner's answer to Q5, by a Cv or Kv. The other forms in PRD §3.1.2 stay Later: the K of "Fixed pressure drop, or Cv/K model" (a flow-independent fixed drop is not planned, §9), "K-factor (clean and dirty)" and "Cv curve or K-factor".

The workflow had already decided these points, which were not re-opened:
- D1–D17 are binding.
- The work is one verified slice; anything bigger goes in §9.
- The change touches the API, so it does not go on a `web/` branch (CLAUDE.md, Tooling).

Every other choice is the designers' own and reversible under D14. §10 records the owner's answers to the product questions (2026-10-26); where the owner was not asked, the recommended default stands. D15–D17 called these "designers' web defaults (reversible, D14)".

**Sources read:**
- **Specs:** PRD §3.1.2, §3.8, §3.9; SDD §4.2, §4.9, §4.10; TSD §5.3, §10.1, §10.4, §12; GOALS §3–§6; CLAUDE.md D4, D6–D17.
- **API code** at `bbafbff`:
  - `models/{components,results,scenarios,goal_seek,fluids,base}.py`;
  - `services/solver/{elements,network,builder,gga,status,system_curve,results,trace,methods,flags,valves,version}.py`;
  - `services/{scenarios,goal_seek}.py`;
  - tests `reference/{derivations_valves,element_laws,case_format,network_check,closed_form,generate_epanet_cases}.py`, `unit/test_goal_seek_models.py` and `differential/{generator,corpus,compare,checks,epanet_model,goal_seek_check}.py`.
- **Web code:**
  - `utils/{factory,compare,goal-seek,scenarios,model-rules,results,flag-text,issue-text,units}.ts` and `utils/export/{tables,about}.ts`;
  - `components/panel/{AddComponentDialog,NewComponentFields,PanelNavigator,ConnectionPanel,ComponentPanel,ResistanceField}.svelte` and `components/results/*`;
  - `state/{workspace,library}.svelte.ts`.
- **Cited sources:** §3.6 says what each one supports and how it was verified; fluids 1.3.1's `Cv_to_K` and `Kv_to_K` were read in its source.
- **Prototypes and logs** are in the workflow's scratchpad (`equipment-design/`, not committed):
  - physics: `proto.py`, `proto_loop.py`, `proto_hand.py` and `proto_kv.py`, with their `*_output.txt`;
  - sources: `proto/proto_equipment.py`, `proto_extra.py` and `proto_closed_forms.py`, with their `*.out.txt`, plus the downloaded documents in `downloads/`;
  - web: `surrogate_probe.py`, `static_vs_loss_probe.py`, `labels-probe.mts`, `probes.out.txt` and the form sketches;
  - synthesizer: `synth/checks.py` and `synth/checks.out.txt`;
  - reviewers: `reviewer-physics/check_*.py` and `reviewer-product/static_head_entry.py`, with their `*.out.txt`;
  - reviser: `reviser/check_revisions.py`, `check_npsh.py` and `count_iso.py`, with their `*.out.txt`;
  - second reviser (the owner's answers): `cvkv/model_shape.py`, `mypy_narrow.py`, `check_cvkv.py`, `check_kv_reference_water.py` and `count_cvkv.py`, with their `*.out.txt`;
  - fixer (the reviewers' findings on that revision): `cvkv/fixer/check_fixer.py`, `cv_star.py` and `two_parts_fix.py`, with their `*.out.txt`; the reviewers' own scripts are in `cvkv/review/`.

**Test inputs.** Every rating, length, level and fluid in the cases below is a made-up test input, entered as the user's data. Every result number was measured by the prototype named next to it.

---

## 1. Scope and decisions

### 1.1 Scope

One new two-port component, `equipment`. It models one side of a heat exchanger, a coil, a strainer, a filter, or any other passive element whose datasheet gives a pressure drop at a flow. The user enters its `rating`, of one of two kinds (decisions 3 and 22):
- **a rated point**, three values: the rated pressure drop ΔP_r (`rating.pressureLoss`), the rated flow Q_r (`rating.flow`) and the density ρ_r of the fluid the rating is for (`rating.density`);
- **a flow coefficient**, one value as the datasheet prints it: a Cv (US gpm of water at 1 psi) or a Kv (m³/h of water at 1 bar), stored as entered, as a valve's is (D9).

The element's law:

```
h(Q)   = EGL_inlet − EGL_outlet = (ΔP_r / (ρ_r g)) · (Q/Q_r)·|Q/Q_r| = c·Q|Q|,   c = ΔP_r / (ρ_r g Q_r²)
ρ g h  = ΔP_r · (ρ/ρ_r) · (Q/Q_r)²            (forward flow; the owner's "flow² and density")
Cv, Kv: c = K/(2gA²), K = fluids' Cv_to_K or Kv_to_K on any bore (K ∝ D⁴ ∝ A², so the bore cancels)
        = 1.76758×10⁸/Cv² or 1.32248×10⁸/Kv² s²/m⁵:  the rated point 1 psi at Cv US gpm,
          or 1 bar at Kv m³/h, on water at ρ_w = 999.297 kg/m³ (§3.1)
```

The element has no status and needs no new numerics: in the network solve it is a Newton link like an open valve with K > 0. Its results, trace, methods text, scenarios, goal seek, Compare rows and export table follow the valve patterns.

**Not in this slice** (Later, §9):
- other ways to enter a rating: a head, K on a stated diameter, a mass-flow rating, a curve or a second rated point;
- a viscosity correction, and a reverse rating;
- a type label and a status;
- a flag for operation far from the rated flow;
- heat transfer.

### 1.2 Decisions

Origin key:
- **P**: physics, model and solver designer.
- **V**: sources and verification designer.
- **W**: web designer.
- **S**: synthesizer, resolving a disagreement (§1.3) or adding what the designs missed.
- **review**: the first reviser, from the reviewers' findings (§11). **owner**: the owner's answers (§10), designed by the second reviser.

| # | Decision | Reason | Origin |
|---|---|---|---|
| 1 | **One component type `equipment`** (`Equipment`) with ports `inlet` → `outlet`, published as `x-port-ids` and `x-port-roles`. One law covers every kind of equipment. A two-sided heat exchanger is one element per side. | One law fits every datasheet that gives a drop at a flow (V: Eaton, Islip, TEMA, §3.6). The two sides of an exchanger are hydraulically independent. | P, W |
| 2 | **No type field.** The user names the element. Default name "Equipment E1", id prefix `E` (free: R, N, PL, AF, T, Y, P, V, L and C are taken). | A field with no physics behind it. An enum would suggest behaviour that depends on the type. The name already says what the element is, in every table and trace. An optional label can be added later without breaking anything (Q2). | W over P (§1.3) |
| 3 | **A required `rating`, with no default, of one of two kinds** (decision 22). **A rated point** has three required fields: `pressureLoss` (Pa, a difference, in (0, 10⁸]; labelled "Rated pressure drop", the datasheet's word), `flow` (m³/s, in (0, 100]) and `density` (kg/m³, in (0, 3×10⁴]). **A Cv or Kv** has one, `value`, in `FlowCoefficient`'s (0, 10⁷], stored as entered. | GOALS §4.1. No source gives a default rating. A rating fluid has a cited candidate, water: strainer and filter charts are on water (Eaton, Islip, §3.6), and ISA-75.01.01 defines a flow coefficient on water at ρ₀ = 999.1033 kg/m³ (S2). But exchanger and coil sheets rate the process fluid and state its density (TEMA), and a water default left in place would silently mis-scale those, so the density is required (owner, Q1). A Cv or Kv needs no density: it is defined on water (§3.1). The API name pairs the input with the result it scales to, `pressureLoss`, not the static `pressureDrop` (decision 11). The bounds are ones the model already has: the PRV/PSV setpoint and gauge maximum (`components.py:308`, `base.py:49`), D11's flow bound (`FCV_SETPOINT_RANGE`), a custom fluid's density (`fluids.py:45`) and a valve's flow coefficient (`components.py:65`). | P, V; S over W (§1.3); review; owner |
| 4 | **ΔP_r is the dissipative loss (friction and form) of total pressure between the ports**: the EGL drop × ρ_r g, without the static head of the ports' elevation difference. The law is on the EGL (D7). Each port's static pressure follows D7, using the velocity in its connected pipe, so the static drop reported is ρgh + ρg(z_out − z_in) + ρ(v_out² − v_in²)/2. The ports keep their real elevations. A datasheet's static drop S_r between nozzles at different elevations or bores is entered as ΔP_r = S_r − ρ_r g (z_out − z_in) − ρ_r (v_out² − v_in²)/2 (the nozzle velocities at the rated flow). | D7 makes the EGL the nodal unknown. With this definition the element's loss does not depend on the pipes next to it: resizing a pipe beside an exchanger must not change its datasheet loss. A static-pressure definition would tie the law to the neighbouring bores, and could give a negative loss where the outlet pipe is narrower. IEC/ISA test taps at one elevation in equal-size pipe measure exactly this loss (P, V), and so do nozzle-to-nozzle charts when the nozzles have one bore and one elevation. Entering S_r as the loss instead puts a flow-independent head into the Q² law: 10.5 % low in flow for a 2 m nozzle rise (review, §11). | P, V; review |
| 5 | **The law is h = c·Q\|Q\|**, with c = h_r/Q_r² and h_r = ΔP_r/(ρ_r g) for a rated point, and c = K/(2gA²) for a Cv or Kv, K from the valves' `k_from_coefficient` (fluids `Cv_to_K`/`Kv_to_K`) at a 1 m bore. The builder computes it once, in that order. dh/dQ = 2c\|Q\|. | ISA-75.01.01-2007 eq. (1) for non-choked liquid flow, Δp = (ρ/ρ₀)(Q/(N₁C))², is this law (V, read in fluids). A constant K is the high-Re limit of Darby's 3-K method (V). The operating density cancels out of the head law; it only converts head to pressure. fluids' K = 1.6×10⁹D⁴/Kv² makes K/A² independent of D, so a Cv or Kv needs no pipe: the 1 m bore's c equals the valve path's on any bore to round-off, at most 6 ulp (8.8×10⁻¹⁶ relative; measured, §3.1). | P, V; owner |
| 6 | **Reverse flow** uses the same law, which is symmetric. The element raises `CORRELATION_OUT_OF_RANGE` with its fixed severity, *warning*. The message contains no numbers. | No datasheet rates reverse flow (V). GOALS §4.6 flags operation outside a correlation's range. Reusing an existing code adds no flag plumbing. The flag also catches an element placed backwards (Q3). | P, V over W (§1.3) |
| 7 | **Zero flow** takes the valve path unchanged. The GGA's Jacobian floor (`gga.JACOBIAN_FLOOR_RELATIVE`) applies to the element as to any non-pipe link, and the law itself stays exact. The initial flow is 1 ft/s × the inlet pipe's area, as for valves (EPANET 2.2 `initlinkflow`). | Measured (P): zero flow between equal heads converged in 10 iterations, a dead end to a plug in 8, and every c from 2.2 to 2.2×10¹⁰ s²/m⁵ in 8–10. A laminar term would be an uncited change to the physics. A head offset cannot work, because the loss depends on the link's own flow. | P |
| 8 | **No status.** Isolation and bypass are modelled with valves. | A passive element always passes flow. Without a status there is no status logic and no scenario `status` entry. | P, W |
| 9 | **No viscosity correction. Laminar flow in a connected pipe is flagged**, as for a valve's Cv or Kv: `CORRELATION_OUT_OF_RANGE` (warning) when 0 < Re < `RE_LAMINAR_MAX` (2000) in either connected pipe's end segment (the lower Re of the two). No other low-flow flag. The trace and the methods text state the limit. | No cited criterion corrects viscosity without the equipment's geometry; the only viscosity tables are manufacturer-specific (Eaton, Islip). The valves already flag the same ISA-75.01.01 law in laminar flow, at the EPANET 2.2 limit (`results.py:913-938`, `methods.py:411`); GOALS §4.1 and §4.6 apply to equipment alike. In most equipment the flow divides into passages slower than the pipe, so the flag is a floor: it misses viscous effects at higher pipe Re (§3.1, Q6). A flow-far-from-rating flag would need a threshold no source gives, and design checks are opt-in (§4.6). | P, V, W; review |
| 10 | **Topology issue `EQUIPMENT_RATING_OUT_OF_RANGE`** (422, listed with the other issues) when c is not a finite positive double, or computing it divides by zero or overflows. Examples inside the bounds: ρ_r = Q_r = 10⁻³⁰⁰ (ZeroDivisionError), a Cv of 10⁻¹⁷⁰ (ZeroDivisionError in `Cv_to_K`), a Kv of 10⁻¹⁶⁰ (OverflowError in `Kv_to_K`); a Cv or Kv of 2×10⁻¹⁵⁰ already gives c = ∞, 10⁻¹⁴⁹ does not (measured, `check_cvkv.out.txt` G). | The pattern of `VALVE_RESISTANCE_OUT_OF_RANGE` (`builder._unrepresentable_valves`, which catches both exceptions): the solver could only fail on such an element. c is monotone in each rating value, so it stays finite and positive between bounds where it is; a goal-seek trial that still raised it would be an unusable trial (D16), never a residual. | P; owner |
| 11 | **`EquipmentResult`** in `SolvedState.equipmentResults`. The map is always present, and `{}` when there is no equipment or the solve did not converge. Fields: flow, flowRatio (null for a Cv or Kv), headLoss, pressureLoss, pressureDrop, and the `rating` used. | The datasheet comparison needs the loss; nozzle gauges read the static drop. The two differ by 1.7 % when the outlet pipe is one size up (W, measured), which is beyond D6. `pressureDrop` keeps `ValveResult.pressureDrop`'s static meaning, and the rated input is named for the loss it scales to. The rating used (after any scenario) is echoed as `ValveResult.setpoint` is. A Cv or Kv has no rated flow, so no flow ratio: Q over the flow at 1 psi is no operating rating. `OutputModel` sends every field. | P, W, S; review; owner |
| 12 | **Its own Results view, "Equipment"**, shown only when equipment exists. It is not filed under `valveResults`. | The valve columns (state, setpoint, open K) would describe a heat exchanger. | W |
| 13 | **A trace for every element, and a methods section "Equipment"** only when the project has equipment. | GOALS §4.2. This is D12's pattern, and it keeps projects without equipment unchanged. | P |
| 14 | **Scenario allow-list:** the whole `rating`, and each of its values: `rating.pressureLoss`, `rating.flow` and `rating.density` (held by a rated point) and `rating.value` (held by a Cv or Kv). A value the element's kind does not hold is `not_applicable`. | A dirty strainer is one change (ΔP_r). Another datasheet is entered as printed, with its own flow and fluid, or as its Cv: one whole-rating change, never a hand-scaled number (GOALS §4.2; Q4). The fluid's precedent (`fluid` and `fluid.temperature`): D15's rule "never a value with a part of it" and its holder test give the rest unchanged (decision 22). | S, between P and W (§1.3); owner |
| 15 | **Goal-seek variables: the four values**, `rating.pressureLoss`, `rating.flow` and `rating.value` on the log scale, `rating.density` linear; one element offers those its kind holds. `_variable` is unchanged; the whole `rating` joins `NOT_VARIABLES`, as the whole `fluid` is. | D16: a variable is a numeric value of D15's allow-list. `_variable` makes every float entry one, and `test_goal_seek_models.py` requires it. Values that act together are already variables (a reservoir's `liquidLevel` and `surfacePressure` enter one fixed head), and dogbox handles that. `rating.flow` has its own use: catalogs list a flow at a standard drop; `rating.value` finds the Cv a strainer needs. | review, over P and W; owner |
| 16 | **Three goals,** `equipment_flow`, `equipment_pressure_loss` and `equipment_pressure_drop`, and the same three Compare rows. | D16 takes goals from Compare's rows. The loss is the datasheet's number; the static drop is what gauges read. | S, from P (the drop) and W (the loss) |
| 17 | **`METHOD_VERSION` 1.3.0**, with one changelog line. Projects without equipment are unchanged in every value (corpus comparison, §3.5). | version.py's rule and D11's precedent (GOALS §4.3): a result with equipment names a method version that has it. 1.2.0 is deployed, so D12's "added in the unreleased version" does not apply. The cost: every link last solved with 1.2.0 shows the method-change notice after its next solve (`ResultsPanel.svelte:190`, `MethodVersionNotice`), listing this changelog line, which says its values are unchanged; the export's About gains its "Calculation methods changed" row. Keeping 1.2.0 would make an equipment result name a method version that has no equipment. | P, V; review |
| 18 | **`schemaVersion` stays 1.** | An additive type (D12's precedent; D14). | P |
| 19 | **Web entry:** one menu entry, "Equipment (rated pressure drop)", in the group "Equipment: heat exchangers, coils, strainers, filters" (owner, Q2). Every path that creates an element asks for a rating first: the first component, Add after, Add before or Insert, and the Piping view's Add here. A **Rated by** choice (Pressure drop at a flow, Cv, Kv) shows the point's three values or the one coefficient. The density has two buttons, **Water at 15 °C** and **This case's fluid** (owner, Q1). | No field has a default (decision 3). "Add before" a pump is the commonest way to place a suction strainer, and the insert path takes no entered values today. Strainer charts are on water, so a case-fluid button alone would cancel the density scaling for a water-rated strainer in a glycol loop. Strainer catalogs often print a Cv (Eaton: "ΔP = [Q/Cv]²"). | W, S (the button), review (the water button); owner |
| 20 | **EPANET mapping** (for the three EPANET reference cases): a TCV between two junctions at the ports' elevations. Its diameter is that of the inlet pipe's end segment, its setting K_E = 2gA²c: 2ΔP_r A²/(ρ_r Q_r²) for a rated point, and for a Cv or Kv the K of that coefficient on the inlet bore, as an isolation valve with that Cv or Kv is mapped today. Its minor loss is 0. | The mapping is exact for any D. EPANET's TCV loss is 0.999077 of ours, which is its 0.02517 against 0.0251933 at our g (S1), and which `network_check.EPANET_MODEL.k_scale` already models; measured the same for a Cv (§7.2). A TCV passes flow both ways. | V, P; owner |
| 21 | **No new fuzz profile.** An exact valve-equivalence check over the corpus, `equipment_check` (§7.4), replaces it. A valve rated by a Cv or Kv becomes an element rated by the same Cv or Kv. | The element's law is `ValveLaw`'s form (c·Q\|Q\|, `elements.py:342-363`), and an active isolation valve's control is fixed OPEN, which the status rules never change, a fixed mode is never starved (`gga.py:90`), and `flow_limit` treats it as no control (`system_curve.py:278-290`). 1,632 of the 5,136 corpus projects hold 2,047 active isolation valves, in all three profiles (`count_iso.out.txt`), and the valves are EPANET-checked there; 513 of them (241 Cv, 272 Kv) in 484 projects test the coefficient path (`count_cvkv.out.txt`). The check needs no generator, EPANET model, `checks.py` rules or class tables, and the corpus and every later run of it do not grow by 1,000 projects (the owner's "little upkeep"; GOALS §5). A profile is Later (§9). | review, over P and V; owner |
| 22 | **The rating is a discriminated union**, `rating: EquipmentRating` = `RatedPoint {kind: 'point', pressureLoss, flow, density}` \| `RatedFlowCoefficient {kind: 'Cv' \| 'Kv', value}`, tagged by a callable discriminator (as `FluidDefinition`). `RatedFlowCoefficient` is `FlowCoefficient` narrowed to Cv and Kv. K alone is not a kind: a K means nothing without the bore it refers to (K on a stated diameter is Later, §9). | Each kind's fields are required, so there is no cross-field rule and no new `x-` extension. Flat optional fields with an exactly-one rule would need one; a scenario would switch kinds with four overrides (three set to null and the coefficient), and a point value set on a Cv-rated element would be a 400 from that rule, not `not_applicable`. The union gets the fluid's behaviour for free (measured, `model_shape.out.txt`): `plan_override`'s holder test makes a part of the other kind `not_applicable`, `overlap_problems` refuses a whole rating with a part of it, `_variable` derives the four parts with no change, and errors never quote the submitted kind. The narrowed subclass passes through the valves' `k_from_coefficient` as it is, with the same bounds (mypy --strict accepts it). The valve's coefficient variable (`resistance` with `coefficient: K \| Cv \| Kv`) is not copied: it exists because a valve's resistance may be absent (the Crane default), while an element always holds its rating; a whole-rating variable beside part variables would also need a new "a value and a part of it" goal-seek list rule. | owner (Q5) |

### 1.3 Where the designs disagreed

1. **Rated density: required or optional.**
   - W: optional, with a blank meaning "the case fluid". P and V: required.
   - This design requires it (decision 3). "Same as the case fluid" is not neutral. It turns the head law into ΔP_r/(ρg)·(Q/Q_r)², so the pressure loss at the rated flow stays at ΔP_r whatever the fluid. That silently drops the density scaling the owner asked for whenever the datasheet fluid differs from the case fluid, and a fluid or temperature scenario would rescale the rating with no sign of it.
   - A default rating fluid would have a cited candidate, water (decision 3), but exchanger and coil sheets rate the process fluid. The web's two buttons write water at 15 °C or the case fluid's density as a number, labelled as user data, so the common cases are still one click (Q1).
2. **Type field.**
   - P: a required enum {heat_exchanger, coil, strainer, filter, other}, used only as a label. W: no field; the name says what it is.
   - This design has no field (decision 2). A required field with no physics adds one more entry to every create path, and a label is what the name already gives (Q2).
3. **Reverse flow.**
   - P and V: flag `CORRELATION_OUT_OF_RANGE` as a warning. W: a trace note and no flag.
   - This design flags it (decision 6), as GOALS §4.6 requires. The message has no numbers, so `flag-text.ts`'s fallback can word it (§4.3), and the form's hint says that reverse flow is flagged (Q3).
4. **Allow-list.**
   - P: ΔP_r and Q_r. W: ΔP_r only.
   - This design takes all three (decision 14) and, with Cv/Kv (owner, Q5), the whole rating and the coefficient too. A rated point is the three numbers together (a Cv or Kv is one). A scenario for another vendor's datasheet, rated on another fluid or by a Cv, needs all of it; without it the user would type a hand-scaled ΔP_r, a number with no source.
   - The cost is five labels, which the web's exhaustiveness test checks (§7.6). Goal seek varies the four numbers, as D16 makes every numeric allow-list value a variable (decision 15; both designers had proposed ΔP_r only).
5. **Goals.**
   - P: flow and the static drop. W: flow and the pressure loss, with three Compare rows.
   - This design has three goals, the same as the three Compare rows (decision 16).
6. **"Equivalent K on the inlet pipe" in the trace.**
   - P proposed it as an intermediate, "for comparison, not used". This design leaves it out.
   - That K changes when a neighbouring pipe is resized, which invites the reading that decision 4 rules out. The reference check computes K_E on its own (§7.1).
7. **Rating echoed in the result.**
   - W: yes, plus a `ratedDensityEntered` flag. P: no.
   - This design echoes the rating used (decision 11), as `ValveResult.setpoint` does, so the export reads a scenario's rating without applying the scenario itself. `ratedDensityEntered` has no meaning once the density is required.
8. **Citations.**
   - P cited Crane TP-410 ch. 2 and Idelchik for a constant K. V could read neither.
   - This design cites only what was read (§3.6). Crane's or Idelchik's wording is added only if a builder quotes it from a copy.
9. **The empty map in the corpus comparison.**
   - P: `--ignore equipmentResults`, plus a check that every new dump holds `{}`. V: omit the map when it is empty, or add `--ignore-empty`.
   - This design keeps the map always present (`OutputModel`'s rule) and adds `--ignore-empty PATH` to `compare.py`, built like `--ignore-null`. A non-empty map in an old project is then still a difference.

---

## 2. Model and API

### 2.1 `Equipment` (`models/components.py`)

```python
class RatedPoint(CamelModel):
    """A datasheet rating: a pressure drop at a flow, for a fluid of a stated density."""

    kind: Literal["point"]
    pressure_loss: float = Field(gt=0, le=1.0e8, description=...)
    flow: float = Field(gt=0, le=FCV_SETPOINT_RANGE[1], description=...)
    density: float = Field(gt=0, le=3.0e4, description=...)


class RatedFlowCoefficient(FlowCoefficient):
    """A datasheet rating as a flow coefficient, stored as entered: Cv (US gpm of water at
    1 psi) or Kv (m³/h of water at 1 bar). A K needs the bore it refers to (not in v1)."""

    kind: Literal["Cv", "Kv"]


def _rating_tag(value: object) -> str | None:
    kind = value.get("kind") if isinstance(value, dict) else getattr(value, "kind", None)
    return "point" if kind == "point" else "coefficient" if kind in ("Cv", "Kv") else None


EquipmentRating = Annotated[
    Annotated[RatedPoint, Tag("point")] | Annotated[RatedFlowCoefficient, Tag("coefficient")],
    Discriminator(  # callable, as FluidDefinition's: errors never quote the submitted kind
        _rating_tag,
        custom_error_type="invalid_rating",
        custom_error_message="unknown rating kind (expected 'point', 'Cv' or 'Kv')",
    ),
]


class Equipment(BaseComponent):
    """A passive element given by its datasheet: a pressure drop at a rated flow, or a Cv or
    Kv, scaled with the square of the flow and with density (SDD §4.14)."""

    PORT_IDS = ("inlet", "outlet")
    PORT_ROLES: ClassVar[dict[str, PortRole]] = {"inlet": "inlet", "outlet": "outlet"}

    type: Literal["equipment"]
    rating: EquipmentRating = Field(description=...)
```

The `Component` union gains `Annotated[Equipment, Tag("equipment")]`. `_component_tag` already returns `type` for a type that is neither a branch nor a valve.

| Field | Unit | Bounds | Description (the schema's text) |
|---|---|---|---|
| `rating.kind` | | `point`, `Cv`, `Kv` | How the datasheet gives the rating. |
| `rating.pressureLoss` (point) | Pa (difference) | (0, 10⁸] | The datasheet pressure drop at the rated flow, as the loss of total pressure from inlet to outlet: the dissipative loss (friction and form), without the static head between the ports. It scales to the result's `pressureLoss`. It equals the static pressure difference when both ports have one elevation and their pipes one bore. Keep the ports at their real elevations; a datasheet's static drop S between nozzles at different elevations or bores is entered as S − ρ_r g (z_out − z_in) − ρ_r (v_out² − v_in²)/2, with the nozzle velocities at the rated flow. |
| `rating.flow` (point) | m³/s | (0, 100] | The flow, inlet → outlet, at which the datasheet gives that drop. A mass-flow rating ṁ_r is entered as ṁ_r/ρ_r. |
| `rating.density` (point) | kg/m³ | (0, 3×10⁴] | The density of the fluid the datasheet's rating is for, which may differ from the fluid being solved. |
| `rating.value` (Cv, Kv) | as entered | (0, 10⁷] | The flow coefficient as the datasheet prints it: Cv in US gpm of water at 1 psi, Kv in m³/h of water at 1 bar, stored as entered (as a valve's resistance). It is a rated point on water (999.297 kg/m³, fluids' `Kv_to_K`): the loss scales with the square of the flow and with density, and needs no pipe diameter. |

- **Rules.** There is no cross-field rule: each kind's fields are required and bounded on their own, so no new `x-ordered-fields` or other extension (the schema's `oneOf` and each member's `kind` enum state the union, measured in `model_shape.out.txt`). Each value's only rule bounds that one value, so D16's argument holds: when a variable's two bounds validate, every trial between them validates.
- **Errors.**
  - A value out of bounds is 400 `VALIDATION_ERROR` at its field, never echoing the value (D10). An unknown kind, a K included, is 400 `VALIDATION_ERROR` with the error type `invalid_rating`, which never quotes it (measured).
  - Inside the union pydantic puts the member's tag in the location (`rating`, `point`, `pressureLoss`). `services/scenarios._clean` drops it, as it drops the fluid's kind; otherwise a scenario's bad rating value would not be matched to its override (§5.1).
  - `EQUIPMENT_RATING_OUT_OF_RANGE` is 422, listed after the other issues (`_unrepresentable_equipment`, appended after `_unrepresentable_valves`). It names the component in `componentIds` and quotes the rating (the three values, or the Cv or Kv), as topology issues name the value at fault (D10).
- **Ports** carry `nominalSize` and an optional elevation, as every port does (SDD §4.2).

### 2.2 `EquipmentResult` (`models/results.py`)

| Field | Unit | Meaning |
|---|---|---|
| `flow` | m³/s | Positive from inlet to outlet. |
| `flowRatio` | none | Q/Q_r, signed; null for a Cv or Kv, which has no rated flow. |
| `headLoss` | m | EGL(inlet) − EGL(outlet), from the solved heads (as `ValveResult.headLoss`). |
| `pressureLoss` | Pa (difference) | ρg × headLoss: the rating scaled to the solved flow and density. |
| `pressureDrop` | Pa (difference) | Static p(inlet) − p(outlet), the meaning `ValveResult.pressureDrop` has: what gauges at the nozzles read. |
| `rating` | as the input | The rating the solve used, after any scenario or goal-seek trial: an `EquipmentRating`, as `OverrideResult.override` echoes an input model. |

- **Where it lives.** `SolvedState.equipment_results: dict[str, EquipmentResult]`, keyed by component id. It is filled on both branches of `build_solved_state`.
- **A closed-off element** (between closed valves) has no result, and its trace says that no values were computed, as for valves.
- **An element in a floating section** (`UNDETERMINED_PRESSURE`) has a result, because the differences are determined there, as for valves.
- **Port results.** Each port has its `NodeResult` like any port: EGL, HGL, static and absolute pressure, and `BELOW_VAPOR_PRESSURE`.

### 2.3 Published rules

- `x-port-ids` and `x-port-roles` come from the class, as for every component.
- `x-override-fields.Equipment` lists the five fields (§5.1): `rating` by its path, each part with its holder schema, `RatedPoint` or `RatedFlowCoefficient`.
- `x-goal-variables.Equipment` is `{rating.pressureLoss: log, rating.flow: log, rating.density: linear}` with schema `RatedPoint`, and `{rating.value: log}` with schema `RatedFlowCoefficient`.
- The web reads which kinds each member holds from the members' `kind` enums (`utils/model-rules.ts`, §6.4), not from a copy.
- `x-goal-quantities` gains the three goals (§5.2).
- `openapi.json` and `schema.d.ts` are regenerated (`pnpm gen:types`), and the model-rules staleness test stays green.

---

## 3. Physics and solver

### 3.1 The law and its limits

- **The law.**
  - The loss is h = c·Q|Q| with c = ΔP_r/(ρ_r g Q_r²), so h(Q_r) = ΔP_r/(ρ_r g) and ρgh(Q_r) = ΔP_r·ρ/ρ_r.
  - Datasheets apply the same density rule (Eaton: "Multiply the pressure drop for water shown in charts by the specific gravity of the liquid"; Islip likewise).
  - It is the ISA-75.01.01 liquid equation at constant C. D9's Cv and Kv are the same law (`k_from_coefficient`).
- **A Cv or Kv** (owner, Q5) is a rated point on water by definition, so its c needs no diameter (measured in `cvkv/check_cvkv.out.txt` A and B):
  - fluids 1.3.1 gives K = 1.6×10⁹ D⁴/Kv² (`Kv_to_K`) and Kv = Cv/1.1560992283536566 (`Cv_to_K`). With A = πD²/4 the D⁴ cancels: c = K/(2gA²) = 1.28×10¹⁰/(π² g Kv²) = 1.32248132708×10⁸/Kv² s²/m⁵, and 1.76758281804×10⁸/Cv².
  - By the definition (Kv m³/h at 1 bar of water), c = 10⁵·3600²/(ρ_w g Kv²). The two agree when ρ_w = 2·10⁵(π/4)²·3600²/1.6×10⁹ = 101.25π² = 999.297445610 kg/m³: fluids' 60 °F water, which its docstring prints as 999.29744568 (7.0×10⁻¹¹ apart). fluids' Cv constant equals 1/(gal·60·√(bar/psi)) to 1.9×10⁻¹⁶ with fluids' own gallon and psi, so c(Cv) = 1 psi/(ρ_w g (Cv gpm)²) to round-off.
  - So ρgh = (ρ/ρ_w)·1 bar·(Q/Kv)², with Q in m³/h: ISA-75.01.01 eq. (1) with fluids' water. The operating density cancels out of the head law, as for a rated point; a Cv or Kv carries its own rating density, ρ_w.
  - The builder computes c = `k_from_coefficient(rating, 1.0)` / (2g·A(1 m)²), the valves' own conversion at a 1 m bore. It equals the valve path (K on the bore, then `ValveLaw`'s K/(2gA²)) and the closed form to round-off, not bit for bit. Over 300,000 random draws (Cv or Kv log-uniform in [10⁻³, 10⁷], bores log-uniform in [5 mm, 2.5 m]) it differs from the valve path by at most 6 ulp (8.8×10⁻¹⁶ relative; 0 ulp in 31 % of the draws), and from the closed form 1.28×10¹⁰/(π² g Kv²) by at most 4 ulp (5.3×10⁻¹⁶; 0 ulp in 49 %) (`cvkv/fixer/check_fixer.out.txt`; the reviewers found the same maxima, and 4 ulp on the 304 library bores). The tests compare these at 2×10⁻¹⁵ relative (§7.6), never as equal or within a fixed number of ulp.
  - The reference suite's own Cv and Kv (`element_laws.k_from_flow_coefficient`, from the definitions with CoolProp's IAPWS-95 water at 60 °F and 703,572 Pa, 999.29744529767 kg/m³) differ from fluids' constant by 3.1×10⁻¹⁰, as they already do for valves (`check_kv_reference_water.out.txt`).
- **Constant K.** This is the fully turbulent form. Darby's 3-K, K = K₁/Re + K_i(1 + K_d/D^0.3), tends to a constant K at high Re. At low Re the K₁/Re term grows, and the real loss tends towards a linear law. `size_control_valve_l` applies a Reynolds factor F_R for Re_v ≤ 10,000 for the same reason.
- **Viscosity is not corrected.** Measured sizes of the error (V, checked in S3):
  - A smooth-tube element dominated by friction scales by Blasius as ρ^0.75 μ^0.25 Q^1.75.
  - Rated on water at 15 °C (999.103 kg/m³, 1.1376 mPa·s) and run on 30 % MEG at 5 °C (1043.47 kg/m³, 3.5592 mPa·s), such an element sees 1.374× its rated drop. The density rule gives 1.044×, so the real drop is 1.32× what this law gives.
  - Against a Q^1.75 law, the square law is 16 % low at half the rated flow (0.841) and 11 % high at 1.5× it (1.107).
  - The laminar flag (§3.2) does not catch this case: the pipe's Re is about 55,000 on the MEG (`reviewer-physics/check_cases.out.txt`).
- **Not modelled:** choking and cavitation inside the element (no F_L data). Port `BELOW_VAPOR_PRESSURE` still applies.

### 3.2 Zero and reverse flow

- **Zero flow.**
  - The slope 2c|Q| is 0 at Q = 0. The GGA floors it in the Jacobian only, as it does for every non-pipe link: max(dh/dQ, 10⁻⁶ × the slopes of the pipes at the link's end nodes). The law stays exact.
  - EPANET 2.2 bounds such a link's gradient by RQtol instead (`hydcoeffs.c`).
  - Measured convergence is in decision 7.
- **Reverse flow.**
  - The law is odd in Q, so reverse flow is solved like forward flow.
  - Where the reported flow is below −q_zero (`results.py`'s zero-flow rounding, ZERO_FLOW_RTOL · max|Q| + CONTINUITY_ATOL), the element raises `CORRELATION_OUT_OF_RANGE` (warning). The message: "equipment '{id}': the flow runs from outlet to inlet; its rating is for inlet → outlet flow, and the loss is taken as for forward flow at the same flow rate". Details: `{flow}`, and `ratedFlow` for a rated point.
- **Laminar flow** (decision 9). Where 0 < Re < `RE_LAMINAR_MAX` in the end segment of the inlet or the outlet pipe (the lower of the two), the element raises `CORRELATION_OUT_OF_RANGE` (warning), as `results.py:927-938` does for a Cv or Kv: "equipment '{id}': its rating is scaled at constant K, the turbulent-flow law of ISA-75.01.01, but the flow in its {inlet|outlet} pipe is laminar (Re = {re:.0f}); the loss is likely underestimated". Details: `{reynoldsNumber}`. It can come with the reverse-flow flag.

### 3.3 EGL and static pressures

- D7 applies unchanged: p = ρg(EGL − z − v²/2g) at each port, with v in the connected pipe.
- The trace states the identity Δp_static = ρgh + ρg(z_out − z_in) + ρ(v_out² − v_in²)/2.
- Measured (V, `equipment_ports_differ` with both ports at z = 20 m, a 102.3 mm inlet pipe and a 77.9 mm outlet pipe): loss 116,660 Pa, static drop 124,323 Pa, and outlet pressure −50,715 Pa gauge.
- Measured (reviser, the same case as it ships, with the outlet port at 22 m, §7.1): the flow and EGLs are unchanged; static drop 143,936.7 Pa = 116,660.4 + 19,613.3 (elevation) + 7,663.0 (velocity heads), p_out −70,328.5 Pa gauge. Closed form and solver (the element emulated as a valve) agree.
- Measured (P, a 3" outlet pipe with the outlet port 2 m higher): loss 52,913.68 Pa against a static drop of 78,650.69 Pa = 52,913.7 + 19,578.0 (elevation) + 6,159.0 (velocity heads). Closed form and solver agree to 10⁻¹⁶.

### 3.4 Solver integration

| File | Change |
|---|---|
| `services/solver/elements.py` | New `QuadraticLossLaw(coefficient)`: `evaluate(q) = (c·q\|q\|, 2c\|q\|)`, with a docstring citing the zero-slope floor. A new class rather than `ValveLaw`, which computes K/(2gA²): the valves' bits stay exactly as they are. |
| `services/solver/network.py` | `LinkKind.EQUIPMENT`. Only `builder.py` and `gga.py` dispatch on `LinkKind`, and `gga.py` tests only `CONNECTION` (pipes, not floored) and `PUMP`. The element is therefore floored like a valve. |
| `services/solver/equipment.py` (new, small, like `valves.py`) | `EquipmentLaw(coefficient, rated_head, rating_density, source)` and `equipment_law(rating, g)`: for a rated point h_r = ΔP_r/(ρ_r g), c = h_r/Q_r²; for a Cv or Kv c = `valves.k_from_coefficient(rating, 1.0)` / (2g·A(1 m)²), with its equivalent point for the trace (1 psi at Cv US gpm or 1 bar at Kv m³/h, ρ_w = ΔP₁/(g c Q₁²) from that c, so no fluids constant is copied). The citation constants (§3.6). |
| `services/solver/builder.py` | `EquipmentData(component, link_index, law, inlet, outlet, inlet_pipe, outlet_pipe)` and `BuiltNetwork.equipment`. `_unrepresentable_equipment`, which computes c inside `try … except (ZeroDivisionError, OverflowError)` as `_unrepresentable_valves` does (decision 10). An `elif isinstance(comp, Equipment)` branch that adds the link inlet → outlet with `QuadraticLossLaw(c)`. The final `assert` and the module docstring are extended. |
| `services/solver/results.py`, `trace.py`, `methods.py`, `version.py`, `__init__.py` | §2.2, the two flags (§3.2), §4 and §3.5. |
| Unchanged | `status.py` (no control, so the link is always NORMAL, and the closed-off, floating and zero-flow-opening logic treat it as open, like a pipe), `gga.py`, `system_curve.py` (`flow_limit` treats a link without a control as unlimited both ways), `branches.py`, `npsh.py` and `friction.py`. A system curve contains c·Q²; a strainer on a pump's suction lowers NPSHa through the EGL. |

### 3.5 `METHOD_VERSION` and the bit-identity proof

- **Version.** `METHOD_VERSION` becomes 1.3.0. Changelog line: "Adds the equipment element: a loss between two ports from a datasheet pressure drop at a rated flow and the density of the fluid it is rated for, or from a Cv or Kv (a rated point on water, converted as for valves), at constant K (scaled with the square of the flow and with density). Flows, heads, pressures, statuses, traces, messages and system curves of projects without equipment are unchanged (corpus comparison)."
- **Why projects without equipment are identical:**
  - every new code path sits behind `isinstance(comp, Equipment)` or a non-empty `built.equipment`;
  - the new issue check finds nothing in old projects, and its issues are appended last;
  - the methods additions are conditional;
  - `LinkKind` only gains a member.
- **Proof.** Dump the corpus (5,136 projects, system curves included) on `bbafbff` and on the branch (`tests.differential.corpus`), then run:

  `compare A B --ignore-empty equipmentResults --ignore methodVersion --ignore trace.methods.methodVersion`

  - Expect "identical 5,136, different 0". The new reference cases show as missing in A: `corpus.py:76-79` adds every `tests/reference/cases/*.json`, so the branch's corpus holds them.
  - `--ignore-empty` is new (§1.3 item 9). Its per-path count must be 5,136, and a unit test proves that a non-empty value is still a difference.
  - The two version paths are the ones D11 ignored (`results.py:1147`, `:1205`).
- **Also required (D13), on the branch's whole corpus, the new reference cases included:**
  - `scenario_check`: 0 different.
  - `goal_seek_check`: 0 violations. Draws are seeded by project name, but the new cases shift positions (`goal_seek_check` runs every 10th project on a scenario, `scenario_check` every 20th with a system curve), so both gates are counts, not project-by-project comparisons of outcomes.
  - `equipment_check` (§7.4): no difference beyond D6.
  - The three existing fuzz profiles: 0 critical seeds, the same classes, and no converged solve left not converged.
  - The reference suite green.
- **The tools must know the type first:** both independent scenario patchers and `goal_seek_check`'s goal readers are keyed by type or result map and would fail or skip on equipment today (§7.4, §8).

### 3.6 Sources

| Source | What it supports | How verified |
|---|---|---|
| ISA-75.01.01-2007 / IEC 60534-2-1, eq. (1), via `fluids.control_valve.size_control_valve_l` (fluids 1.3.1: `C = Q/N1*sqrt(rho/rho0/dP)`) | The density-scaled square law for non-choked, turbulent liquid flow, and its Reynolds limit (F_R for Re_v ≤ 10,000). Cited as `methods.ISA_75`. | V read the source; S2 checked `rho0` = 999.1033 kg/m³. |
| `fluids.core.dP_from_K` ("dP = 0.5Kρ V²") and `head_from_K` ("head = K V²/(2g)") | The definition of a constant K. The head form has no density in it. | V read the docstrings. |
| Silverberg & Darby, Chem. Eng. 106(7), 1999, 101 (`fluids.fittings.Darby3K`) | A constant K is the high-Re limit of K₁/Re + K_i(1 + K_d/D^0.3). Cited as `methods.DARBY`. | V read the docstring. |
| `fluids.fittings.Kv_to_K` and `Cv_to_K` (ISA-75.01.01-2007 draft), through `valves.k_from_coefficient` | A Cv or Kv is a rated point: 1 psi at Cv US gpm or 1 bar at Kv m³/h, water at 999.29744568 kg/m³ (60 °F, IAPWS-95; 101.25π² inside K = 1.6×10⁹D⁴/Kv²); Cv = 1.1560992283536566 Kv. The Cv/Kv rating's c (§3.1). | S2; the second reviser read the source and derived the constants (`check_cvkv.out.txt` A). |
| `friction.RE_LAMINAR_MAX` = 2000 (EPANET 2.2 `hydcoeffs.c:600`) | The laminar flag's threshold, as for a valve's Cv, Kv or Crane K. | In the code (`results.py:913-938`). |
| `fluids.friction.Blasius` (f = 0.3164/Re^0.25, 3000 < Re < 200,000) | The size of the viscosity limit (§3.1). Used in the design and the methods text only, never in a calculation. | S3 |
| Eaton, "Pressure Drop Calculations", EF-SCPS-15 (3-2013) | Strainer ratings are on water. "ΔP = [Q/Cv]²", and "multiply the pressure drop for water … by the specific gravity". Viscosity factors are the vendor's own. | V read the PDF. |
| Islip Flow Controls, basket strainers | Ratings for water with clean screens. "Multiply … by the specific gravity". Vendor viscosity charts. | V read the PDF. |
| TEMA metric data sheet (2026) | An exchanger rating is a pressure drop at a mass flow, with the fluid's density stated (so Q_r = ṁ/ρ_r). It does not say whether the drop is static or total. | V read the PDF. |
| Not cited (not verified): Crane TP-410's wording on constant K, Idelchik, AHRI 410 (HTTP 403), SWEP, Tranter | None. | Unreachable, or no copy available. |

---

## 4. Traceability

### 4.1 Trace (`trace._equipment_trace`, `element_type = "equipment"`)

It is dispatched before the final `else` (valves) branch, using `TraceInputs.equipment`.

- **Inputs:**
  - a rated point: ΔP_r (Pa (difference)), Q_r (m³/s) and ρ_r (kg/m³); or a Cv (US gpm at 1 psi) or Kv (m³/h at 1 bar) as entered; all with source `user`;
  - the ports' elevations;
  - ρ of the case fluid and g.
- **Equations:**
  - a rated point: h_r = ΔP_r/(ρ_r g) and c = h_r/Q_r²;
  - a Cv or Kv: K = `fluids.fittings.Cv_to_K(Cv, D)` (or `Kv_to_K`) and c = K/(2gA²), the same for every bore D, evaluated at D = 1 m;
  - EGL_in − EGL_out = cQ|Q| (= h_r(Q/Q_r)|Q/Q_r| for a rated point);
  - ρgh = ΔP_r(ρ/ρ_r)(Q/Q_r)|Q/Q_r|, or (ρ/ρ_w)·1 psi·(Q/Cv gpm)|Q/Cv gpm| (1 bar and m³/h for a Kv);
  - the static pressure at each port (D7);
  - the Δp_static identity (§3.3).
- **Correlations:** "Constant-K square law with density scaling: the form of ISA-75.01.01-2007 eq. (1) for non-choked, turbulent liquid flow. A constant K is the high-Re limit of the 3-K method (Silverberg & Darby 1999)."
- **Data source:** "Rating: user data (equipment datasheet)"; for a Cv or Kv also the valves' conversion, "fluids.fittings.Cv_to_K / Kv_to_K (ISA-75.01.01-2007), water at 999.29744568 kg/m³", as a valve's trace cites it (D9).
- **Intermediates:**
  - c, Q, and h_r and Q/Q_r for a rated point; for a Cv or Kv its equivalent rated point, ΔP₁ (1 psi or 1 bar) at Q₁ (Cv US gpm or Kv m³/h) with ρ_w = ΔP₁/(g c Q₁²);
  - v_in and v_out, and Re, in the connected pipes' end segments;
  - h as solved (EGL difference) and as the law gives it;
  - ρgh, ρ/ρ_r (ρ/ρ_w) and Δp_static;
  - the port states (`_port_state_values`).
- **Notes:**
  - The rated drop is the dissipative loss of total pressure between the ports, without the static head between them.
  - For a Cv or Kv: it is a rated point on water by definition, so its loss scales with ρ/ρ_w, and it needs no pipe diameter.
  - The loss scales with density only. It does not account for a viscosity or Reynolds number different from the datasheet's: with a more viscous fluid, or at flows well below the rated flow, the real loss may be higher than this law gives.
  - The density ratio ρ/ρ_r (ρ/ρ_w), stated in words.
  - The reverse-flow and laminar-flow notes, when they apply, each with the inequality that set it.
  - The flags.
  - In a scenario, D15's "Changed by this scenario" note; in a goal seek, D16's.

### 4.2 Methods summary

- **A section "Equipment"** comes after "Valves", only when the project has equipment. It states:
  - the law and the definition of the rated drop (decision 4);
  - the density scaling and why the operating density cancels out of the head;
  - only when an element is rated by a Cv or Kv: the conversion (the valves' fluids functions, the rated point on water it defines, no pipe diameter);
  - reverse flow (flagged, symmetric law);
  - laminar flow in a connected pipe (Re < 2000) flagged, as for valves;
  - the zero-flow Jacobian floor;
  - the viscosity limit (§3.1).

  Its references are `ISA_75` and `DARBY`, both already in `methods.py`; the Cv/Kv item names `fluids.fittings.Cv_to_K / Kv_to_K` in its text, as the Valves item does (`methods.py:407`).
- **One entry in `assumptions`**, under the same condition: "Equipment losses scale with the square of the flow and with density from one rated point, a Cv or a Kv (constant K); viscosity is not corrected".
- No other section or assumption changes.

### 4.3 Flags

- **Flags.** No new code. Reverse flow and laminar flow raise `CORRELATION_OUT_OF_RANGE` on the element (§3.2). Port flags are the generic ones.
- **Web wording.** The reverse-flow message has no numbers, and the laminar one only a Reynolds number, which has no unit. `flag-text.ts` reaches its fallback for a `CORRELATION_OUT_OF_RANGE` without `segmentIndex` or `fittingIndex`, as for the valves' laminar flag, and that fallback words it with the element's name.
- **Issue text.** `issue-text.ts` gains `EQUIPMENT_RATING_OUT_OF_RANGE`: the element's name and its rating, the three values in display units or the Cv or Kv as entered.

---

## 5. Scenarios, goal seek, Compare and export

### 5.1 Scenarios (D15)

- **API allow-list.** `models/scenarios.py` sets `COMPONENT_FIELDS[Equipment]` to (trace unit, label):
  - `rating` (`Overridable(("rating",))`, "", "rating"): the whole rating, as `fluid` is the whole fluid;
  - `rating.pressureLoss` (holder `RatedPoint`; "Pa", "rated pressure drop");
  - `rating.flow` (holder `RatedPoint`; "m³/s", "rated flow");
  - `rating.density` (holder `RatedPoint`; "kg/m³", "rated fluid density");
  - `rating.value` (holder `RatedFlowCoefficient`; "", a label by the target's kind, "Cv" or "Kv", and "flow coefficient" with no target, as `_speed_label` names a speed by its pump).

  `ComponentField` gains the five names, and `services/scenarios.COMPONENT_NAMES[Equipment]` is "equipment".
- **Rules, all D15's own** (checked on the prototype model, `model_shape.out.txt`):
  - `rating` with any `rating.*` in one scenario is "a value and a part of it" (400, `overlap_problems`), so order never matters.
  - A part the base element's kind does not hold is `not_applicable` (`plan_override`'s holder test): kept, reported, ignored. `MISSING_HOLDER` gains the reasons: "equipment {id} is rated by a Cv or Kv in the base project (rating.pressureLoss applies to a rated point; set the whole rating instead)", and for `rating.value` "… by a pressure drop at a flow … (rating.value applies to a Cv or Kv rating …)".
  - A whole `rating` is validated by the union: an unknown kind or a bad value is 400 at its override, never echoed; `_clean` drops the union's tag from the error location (§2.1).
- **Text** (GOALS §4.2). `value_text`, which writes an applied override in the element's "Changed by this scenario" note and in the Scenario methods section, gains a `rating` branch beside `spec`, `fluid` and `resistance`: a Cv or Kv as "Cv 120" (`resistance`'s form, 6 significant digits), a rated point as "50000 Pa at 0.015 m³/s, 999.1 kg/m³" (SI with units, `_number`, as every API text). Without it a whole rating falls to `str(value)` and the note reads "rating {'kind': 'Cv', 'value': 120.0} (base: {'kind': 'point', …})" (measured). The parts are numbers and keep the generic branch.
- **Use cases:** a clean or dirty strainer (`rating.pressureLoss`), a fouled exchanger, another vendor's datasheet, as a point on its own fluid or as its Cv (one whole-`rating` change).
- **PRD §3.8's list** gains the rating and its values.
- An equipment override on another type of component is `not_applicable`, as D15 defines.

### 5.2 Goal seek (D16)

- **Variables.** `_variable` derives the four parts from the allow-list with no change, as for every float field (measured, `model_shape.out.txt`): their holders, `RatedPoint` and `RatedFlowCoefficient`, bound them, as `PumpControl` bounds `control.setpoint`. `VariableComponentField` gains the four names, and `LOG_FIELDS` gains `rating.pressureLoss`, `rating.flow` and `rating.value`: each is > 0 by its bound and spans decades. `rating.density` is linear. The whole `rating` is not a number, so `NOT_VARIABLES` gains `"rating": "a whole rating, a rated point or a flow coefficient; vary one of its values"`, as `fluid` is there. `test_goal_seek_models.py`'s `EXPECTED` gains the Equipment row, its `NOT_VARIABLES` pin the fourth name, and `test_no_rule_reads_two_variables_of_one_element` a point-rated Equipment base over each pair of its three values (the test is generalized from two variables per base, §7.6).
- **A part of the other kind** is `VARIABLE_NOT_APPLICABLE` (400, "inputs that do not apply", D16), with the reason worded as for `control.setpoint` in `_resolve_variable`: "equipment E1 is rated by a Cv in this case (rating.pressureLoss applies to a rated point)". A goal seek varies the rating in the kind entered; to search for a Cv, rate the element by a Cv first. The valves' `coefficient` field is not used (decision 22).
- **A whole rating in the case's scenario.** When the scenario run sets the whole `rating` and one or more variables are parts of it, each such variable's `override` carries the whole rating with **every** varied part at its found value, and its `replacedOverride` names the scenario's override. This is the rule `_Var` has for `fluid.temperature` under a whole `fluid` (`whole_fluid`, `goal_seek.py:1681`), generalized to a part whose whole value the scenario overrides, with one more step:
  - `_Var.override` builds a whole value from the **reported evaluation's dump** (the case dump with every variable written at its found value, by `_Var.write`), not from the case dump (`goal_seek.py:2337`). The overrides of two parts of one whole rating are then equal, and applying any one of them, or all of them (upserted by target and field, as the web and `goal_seek_check` do, or each written at its `replacedOverride`, as `test_goal_seek.py` does), gives the solved state bit for bit (D16).
  - Built from the case dump, each override would carry only its own found part and the case's value of the other; whichever is applied last wins, and a found value is lost (measured by a reviewer and by the fixer, `cvkv/fixer/two_parts_fix.out.txt`: reproduces False today, True with the reported dump). Adding both instead is refused as "overrides i and j set the same value" (400).
  - The fluid has one part, its temperature, so its override is the same as today, bit for bit: the reported dump's fluid already holds the found temperature.
- **Text of a replaced whole rating.** The Scenario methods section and the element's scenario note mark an override that a goal-seek variable replaced (`_replaced_mark`, `element_notes`). For a whole rating whose parts the goal seek varied, the generic mark ("the value found takes the place of its rating") would say the whole rating was replaced. The mark names the parts instead: "In this goal seek the values found take the place of its rated pressure drop and rated flow (see Goal seek)", as `REPLACED_TEMPERATURE` names the fluid's temperature. For this, the replaced overrides passed to `annotate` carry, per index, the labels of the parts replaced (none when the variable replaced the whole value). The texts of projects without equipment are unchanged, `REPLACED_TEMPERATURE` included (corpus comparison and `scenario_check`, §3.5), and `goal_seek_check`'s count of marked items (one per replaced override) still holds.
- **Example uses.** "How dirty can the strainer get before the flow falls below the demand": the largest ΔP_r at which equipment_flow = Q_min. "Which catalog size": the rated flow at the catalog's standard drop that keeps the demand, or the Cv at which the flow meets it.
- **Goals.** The `ElementKind` "equipment" has targets `(Equipment,)`. A `goal_value` branch goes before the final boundary branch.

| Goal | Unit, category | Reads | Label |
|---|---|---|---|
| `equipment_flow` | m³/s, flow | `flow` | flow through {element} |
| `equipment_pressure_loss` | Pa (difference), pressure | `pressureLoss` | pressure loss across {element} |
| `equipment_pressure_drop` | Pa (difference), pressure | `pressureDrop` | static pressure drop across {element} |

Default tolerances and minimums follow the existing categories (D16).

### 5.3 Compare (web, `utils/compare.ts`)

- **Element kind `equipment`.** `ELEMENT_QUANTITIES.equipment` is:
  - `equipmentFlow`, relative difference shown;
  - `equipmentPressureLoss`, relative shown (a true zero);
  - `equipmentPressureDrop`, no relative (no true zero, as `valvePressureDrop`).
- **Default rows.** `defaultRows` adds an item's flow and pressure-loss rows when a scenario changes that item.
- **Dialog.** `CompareRowsDialog` gains the group "Equipment", after Valves.

### 5.4 Export (D17, web)

- **A new sheet** `equipment` ("Equipment", `equipment.csv`), after Valves, with one row per item and case. Its columns:
  - the case columns and Solved at / Results (D17);
  - Equipment id and Equipment;
  - Flow (+ inlet → outlet) and Flow ÷ rated flow (empty for a Cv or Kv);
  - Pressure loss, Head loss and Pressure drop (static);
  - Rated by (text: "Pressure drop at a flow", "Cv" or "Kv");
  - Rated pressure drop (loss), Rated flow and Rated fluid density (empty for a Cv or Kv);
  - Flow coefficient (the Cv or Kv as entered, empty for a rated point; its kind is in Rated by);
  - Flags.

  Every number cell is an API double. The rated columns are the one named departure from the screen's table: a file has no form to read the rating from. "(loss)" says which result column the rated drop scales to.
- **Scenario changes sheet.** `changeCategory` maps `rating.pressureLoss`, `rating.flow` and `rating.density` to a pressure difference (no gauge marker), a flow and a density. `rating` and `rating.value` have no category and are written as text, as `resistance` is: "Cv 120", or "50 kPa at 15 L/s, 999.1 kg/m³" in the file's units. Today an unknown field falls to the dimensionless category.
- **About lines,** only when the file has an Equipment sheet, so files without equipment stay byte-identical:
  - the flow sign for equipment;
  - flow ÷ rated flow in the fractions line;
  - the "≈ 0" line extended to equipment pressure differences;
  - in "Units: exceptions", that a Cv (US gpm of water at 1 psi) or Kv (m³/h of water at 1 bar) is as entered in every unit system.

---

## 6. Web

### 6.1 Adding an element

- **Labels.** `utils/factory.ts` gains:
  - kind `equipment`;
  - the label "Equipment (rated pressure drop)";
  - the default name "Equipment E1";
  - the prefix `E`.

  `components/panel/kinds.ts` places the group "Equipment: heat exchangers, coils, strainers, filters" after Control valves.
- **Entry checks.**
  - A list `ENTRY_KINDS = ['assigned_flow', 'equipment']` replaces the `kind === 'assigned_flow'` checks: `factory.missingEntry`, `NewComponentFields`, `ConnectionPanel` and the first-component form in `PanelNavigator` (`firstKind === 'assigned_flow'`, `PanelNavigator.svelte:160`).
  - `state/workspace.svelte.ts`'s `INLINE_KINDS` gains `'equipment'`: Add before and Insert offer only the kinds in it (`AddComponentDialog.svelte:79-86`).
  - `missingEntries(kind, values)` returns one error per empty field of the chosen kind, for example "Enter the rated pressure drop from the datasheet: it has no default." or "Enter the Cv from the datasheet: it has no default." `missingEntry` keeps its signature.
  - `MissingFlowError` becomes `MissingEntryError`.
- **The insert path takes entered values.** `ws.insert(connectionId, kind, values)`, and `AddComponentDialog` checks `missingEntry` in every mode but branch. Today it checks it only in `after` mode, because no inline kind needed values.
- **The Add dialog** (a sheet on phones) shows **Rated by** (Pressure drop at a flow, Cv, Kv; it starts on the first, which stores nothing until its values are entered), then the chosen kind's fields: the point's three, with the density's two buttons, **Water at 15 °C** and **This case's fluid** (owner, Q1), or the one coefficient.
  - Each button reads its fluid's properties through `library.fluidProperties` (D10's POST, with the fluid in the body: built-in water at 288.15 K, CoolProp IAPWS-95, 999.102621 kg/m³, within 7×10⁻⁷ of ISA-75.01.01's ρ₀ as fluids gives it, 999.1033; or the case fluid) and writes the exact double, as user data.
  - An error clears on input, never on blur, so the Add button never moves under the pointer (the layout rule `NewComponentFields` follows).

### 6.2 Form (`forms/EquipmentForm.svelte`, sharing `EquipmentRatingFields.svelte` with the Add dialog)

| Field | Category, unit (SI / US) | Hint |
|---|---|---|
| Rated by | a select: "Pressure drop at a flow", "Cv (US flow coefficient)", "Kv (metric flow coefficient)" | "How the datasheet gives the rating." |
| Rated pressure drop | `pressure` with no gauge marker: kPa / psi (never "kPa(g)", W probe) | "From the datasheet: the pressure lost from inlet to outlet at the rated flow, without any static head. For a drop measured between nozzles at different heights, subtract ρ g × their height difference; keep the ports at their real elevations." |
| Rated flow | `flow`: L/s / gpm | "The flow at which the datasheet gives that drop." |
| Rated fluid density | `density`: kg/m³ / lb/ft³, with the two buttons | "The density of the fluid the datasheet is rated with. Strainer and filter charts are usually for water; exchanger and coil datasheets state their fluid." |
| Cv or Kv | `dimensionless`, as entered; bounds `schemaBounds('RatedFlowCoefficient', 'value')` | `ResistanceField`'s own hints: "US gpm of water at 1 psi pressure drop (stored as entered)." and "m³/h of water at 1 bar pressure drop (stored as entered)." |

- **Reuse.** The coefficient's option labels and hints move from `ResistanceField.svelte` to `utils/flow-coefficient.ts`, read by both components; the valves' field is otherwise unchanged. The kind rule is `ResistanceField`'s: a number is never carried to another kind, and a kind picked with no value of it yet is pending. With no default to fall back on, the element keeps its stored rating until the new kind's values are all entered, with the warning "Enter the Cv to use it; until then the rated point applies."
- **Layout.** Elevation comes first, then the rating fields, then the hint and the Ports. One column on phones, two from 640 px.
- **Hint text:** "A heat exchanger, coil, strainer, filter or other element given by its datasheet: a pressure drop at a rated flow, or a Cv or Kv. The loss scales with the square of the flow and with density: ΔP = ΔP_rated × (Q ÷ Q_rated)² × ρ ÷ ρ_rated; a Cv or Kv is a rating on water. Viscosity is not corrected; the scaling holds where the loss goes as the flow squared, as in turbulent flow. Laminar flow in a connected pipe, and flow from outlet to inlet, are flagged. For a dirty strainer or a fouled exchanger, make a scenario with its own rating: a higher rated pressure drop, or a lower Cv or Kv."
- **Bounds.** Field messages come from `schemaBounds`, in display units.
- **In a scenario,** the rating is editable (D15), stored by `nextOverrides`' rule (§6.4), as the fluid is:
  - An edit of a value while the element keeps the base's kind is a part change, marked Changed with the base value and Reset at its field: the rated pressure drop is `rating.pressureLoss`, and a Cv or Kv value, on an element whose base is rated by that coefficient, is `rating.value` (Cv 90 → 80 is one `rating.value` change).
  - A change of kind (point → Cv, Cv → Kv) is one whole-rating change, noted once at the group with the base rating and Reset, as `ResistanceField` notes a resistance. While it exists, every later edit of the rating updates it, as an edit of the fluid updates a whole-fluid change.

### 6.3 Results

- **The Equipment view** (tab order Valves, Equipment, Branches) appears in `availableViews` only when `equipmentResults` has entries. Its caption is "Results per equipment item"; its first column is Equipment.
- **`equipmentTable`** is built as `valveTable` is. Its columns:
  - Flow (+ inlet → outlet);
  - Flow ÷ rated flow (%), "—" for a Cv or Kv;
  - Pressure loss: `f.diff`, with ρg·HEAD_NOISE;
  - Head loss: `f.diff`, with HEAD_NOISE;
  - Pressure drop: static, `f.diff`.
- **Note under the table:** "Pressure loss is the rating scaled to the solved flow and density, ρg × head loss. Pressure drop is the static pressure difference, inlet minus outlet, as for valves; it equals the pressure loss when both ports are at one elevation and their pipes have one bore. Flow, flow ÷ rated flow, pressure loss and head loss are negative when the flow runs from outlet to inlet; the pressure drop also holds the ports' elevation and velocity terms, so its sign need not follow the flow. An element rated by a Cv or Kv has no rated flow."
- **Strip.** `SUMMARY_COLUMNS.Equipment` is `['flow', 'flowRatio', 'pressureLoss']`, and `rowsForElement` adds the table after Valve. `elementSummary` leaves out a "—" cell, so a Cv- or Kv-rated element shows flow and pressure loss.
- **Trace.** `TraceView` is generic. Its "Add to comparison" and "Use in goal seek" gain an `equipment` case.

### 6.4 Elsewhere

- **`utils/model-rules.ts`** gains `ratingSchemaName(kind)`, read from the members of `Equipment.rating`'s union and their `kind` enums, as `fluidSchemaName` is read from the fluid's.
- **`utils/scenarios.ts`.**
  - `fieldLabelFor` and `changeValueText` cover the five fields with their units: "Rating", "Rated pressure drop", "Rated flow", "Rated fluid density", and "Cv" or "Kv" by the element's kind; the whole rating's text is "Cv 120" or "50 kPa at 15 L/s, 999.1 kg/m³". A new exhaustiveness test (§7.6) prevents the dimensionless fallback, which would otherwise show "70000" with no unit in four places.
  - `holderMatches` checks a rating holder's schema by `ratingSchemaName`, as it checks a fluid's. Today it would accept any rating, so `valueOf` would offer `rating.value` on a point-rated element (and goal seek's picker with it).
  - `diffComponents` emits **one** raw change for the rating, the whole `rating`, never its parts. Today it pushes a raw change for every allow-list entry whose value differs, so one edit of the rated pressure drop would yield `rating` and `rating.pressureLoss`, and a switch from a point to a Cv would yield `rating`, three null parts and `rating.value`; `set()` would upsert them all, "a value and a part of it" (400 from the API, `overlappingChanges` in the web). The rule is general: an entry whose path is a proper prefix of another entry's of the same component is a whole value, and only its raw change is emitted, as `diffCase` emits the whole `fluid` once and never `fluid.temperature`. No component has such an entry today, so nothing else changes.
  - `nextOverrides` then turns that one raw change into the scenario's changes as it treats the fluid's:
    - a rating equal to the base's removes the whole change and every part change of that element;
    - while no whole-rating change exists and the kind is the base's, one part change per value that differs from the base's (`rating.pressureLoss`, `rating.flow`, `rating.density`, or `rating.value`), and a part equal to the base's again is removed;
    - otherwise one whole-rating change, which takes the place of the first part change and removes the others (never a value and a part of it). While it exists, later edits update it.
  - A base edit that changes an element's kind leaves the scenario's part changes not applying (`not_applicable`), kept and shown as D15 keeps them.
- **`utils/goal-seek.ts`.**
  - Variable group "Equipment", after Valves, with the four fields; `variableChoices` offers those the element's kind holds (through `valueOf`). `variableSpec`: a pressure with no gauge marker, a flow, a density, and for `rating.value` a dimensionless number with the prefix "Cv " or "Kv ", as a resistance's.
  - Default bounds: [v/10, 10v] for the rated drop, the rated flow and the Cv or Kv, [v/2, 2v] for the density, clipped to the field's bounds. Without them the defaults would be [v, v], which breaks lower < upper. These are designers' defaults:
    - A Cv or Kv is a rated flow at a stated drop (c ∝ 1/Cv², as c ∝ 1/Q_r²), so it gets the rated flow's range.
    - This departs from a valve's coefficient on purpose. `defaultBounds` gives a valve's `resistance` [v/100, 100v] whether it is a K, a Cv or a Kv, so the same Cv gets a range 10× wider at each end on a valve. A valve's resistance is often not a datasheet value: it may start from the Crane default's K, and one rule covers all three kinds. An element always holds a datasheet rating, and a factor of 10 either way in Cv already spans a factor of 100 either way in c (up to 10 either way in flow where the element dominates). The narrower range gives the 9-point scan finer steps. The bounds are always shown and editable (D16).
  - Goal group "Equipment" with the three goals. Hints: "Positive from inlet to outlet."; "The rating scaled to the flow and density (ρg × head loss)."; "Static pressure, inlet minus outlet."
  - **Whole-value overrides** (§5.2). Today the web special-cases only the whole fluid. A scenario run returns a whole `rating` override for a part variable, so two helpers change, and Apply is checked:
    - **The notices name each value found by its variable.** These are the outcome announcement (`GoalSeekDialog`), the Apply notice and its "already holds" text (`applyGoalSeek`). Each takes its label and text from the `VariableResult`'s `variable` and `value` (the variable's label, its value through `variableSpec`), never from its override. A whole-rating override carries the scenario's other values too, and the overrides of two parts of one rating are the same. Read through today's `overrideValueText`, a rating would read "rating —" (`formatValue` of an object), and `variableLabelOf` cannot tell which part it carries. The fluid's mapping (`fluid` → `fluid.temperature`) becomes the general case, with its texts unchanged.
    - **`keptByScenarios`** lists a scenario that sets the override's field **or any whole value it is a part of** (each proper prefix of its path). Today it checks `fluid` and `fluid.temperature` for a project override but only `o.field` for a component. A base run that varies `rating.pressureLoss` would then miss a scenario with a whole-`rating` change, which keeps its own rating. For the fluid this gives the same two fields.
    - **Apply** (`upserted`, `applyToCase`) needs no change. Two equal whole-rating overrides upsert to one change, and `changeCount` counts it once.
- **Unchanged:** the navigator's walk (Prev/Next through a two-port pass-through, orientation from `x-port-roles`; only `PanelNavigator`'s first-component form changes, §6.1), `trace.ts`, `system-curve-text.ts` (the element is not one-way), `DeleteDialog`, `encoding`, `migrations`, `examples.ts` and `MethodsSummary`.
- **Phone and desktop (GOALS §4.7).** The form is one column on phones and the Add dialog a sheet. The table has five data columns (Valves has ten) and a sticky first column. The extra view pill appears only when equipment exists, and below 1024 px the pills already scroll sideways.

---

## 7. Verification

### 7.1 Closed-form reference cases (`tests/reference/derivations_equipment.py`)

- **Where.** A new derivations file, added to `closed_form.py` and generated by `build_closed_form_cases.py`. It imports only `opensolve_pipe.models` and `tests.reference`, never `services`.
- **New helpers.**
  - `element_laws.equipment_k(rating, d)`: 2ΔP_r A²/(ρ_r Q_r²) for a rated point; for a Cv or Kv the suite's own `k_from_flow_coefficient(rating, d)`, from the definitions with CoolProp's water (3.1×10⁻¹⁰ from fluids' constant, §3.1), so the reference does not reuse the solver's conversion;
  - `element_laws.equipment_head(rating, q, g)` = c·q|q|, c = `equipment_k(rating, d)`/(2gA²) at any d;
  - a `case_format.equipment(...)` builder taking either kind;
  - an `equipment` block in `Expected` (headLoss, pressureLoss, pressureDrop).
- **Self-check.** `network_check` evaluates the law, so its fsolve self-check covers the element.
- **Shared inputs.** The element E1 (test input): ΔP_r = 50 kPa at Q_r = 15 L/s, ρ_r = CoolProp water at 15 °C = 999.102621 kg/m³. That gives h_r = 5.10316053 m and c = 22,680.7135 s²/m⁵. The coefficient cases rate it Kv 60 or Cv 90 instead (test inputs; c = 36,735.592 and 21,822.010 s²/m⁵). Pipes have ε = 4.5×10⁻⁵ m.

Each case's numbers were measured by V (`proto_equipment.out.txt`, `proto_closed_forms.out.txt`), those of `equipment_ports_differ` and `equipment_suction_strainer_npsh` by the reviser (`reviser/check_revisions.out.txt`, `check_npsh.out.txt`), and those of the two coefficient cases by the second reviser (`cvkv/check_cvkv.out.txt` C1–C2, `check_kv_reference_water.out.txt`). The prototypes emulated the element as an isolation valve with K = K_E, or with that Cv or Kv (K on the inlet bore), and matched every hand calculation to about 10⁻¹⁵ relative (10⁻¹⁰ where the suite's own reference water is used). Pipes are custom; "EPANET water" is a custom fluid of 1000 kg/m³ with EPANET's ν = 1.1×10⁻⁵ ft²/s; "liquid A" is the suite's 998 kg/m³, 1 mPa·s.

| Case | Network (test inputs) | Derivation | Expected (measured) |
|---|---|---|---|
| `equipment_rated_point` | Liquid ρ = ρ_r = 998 kg/m³, μ = 1 mPa·s; 102.3 mm pipes of 60 m and 40 m (Colebrook) | Explicit: H₁ − H₂ = h_L1(Q_r) + ΔP_r/(ρ_r g) + h_L2(Q_r) = 8.20250633098 m | Q = Q_r exactly (3.5×10⁻¹⁶); static Δp 50,000 Pa (1.5×10⁻¹⁶). "The solve gives back the datasheet." |
| `equipment_line` | H₁ = 12 m, H₂ = 1 m, E1 at z = 3 m; 102.3 mm × 60 m and × 40 m; EPANET water, `swamee_jain` | brentq on H₁ − H₂ = Σh_line(Q) + cQ\|Q\| | Q = 0.0173994741 m³/s; h = 6.86640 m; ρgh = 67,336.4 Pa; EGL in/out 9.519839 / 2.653441 m; static 61,697.198 / −5,639.161 Pa |
| `equipment_density_scaling` | (a) the same line at ρ = 1100 kg/m³ and the same ν; (b) built-in 30 % MEG at 5 °C (Melinder 2010: 1043.470019 kg/m³, 3.55924 mPa·s), Colebrook | (a) a metamorphic pair: same Q and EGL, Δp ×1.1; (b) brentq | (a) Δp 74,070.0 Pa; (b) Q = 0.0168778222 m³/s, h = 6.46085 m, Δp = 66,113.5 Pa = (ρ/ρ_r)ΔP_r(Q/Q_r)² |
| `equipment_reverse_flow` | `equipment_line` with the heads swapped | Mirror | Q = −0.0173994741 m³/s; EGL in/out 3.480161 / 10.346559 m; static 2,468.197 / 69,804.556 Pa; `CORRELATION_OUT_OF_RANGE` on E1 |
| `equipment_ports_differ` | R1 z = 25 m, level 5 m (H₁ = 30 m); E1 at z = 20 m, inlet port 20 m, **outlet port 22 m**; inlet 102.3 mm × 30 m, outlet 77.9 mm × 50 m; R2 z = 0, level 2 m; EPANET water, `swamee_jain` | brentq; static pressures by D7 | Q = 0.0229019814 m³/s; EGL in/out 27.901780 / 16.005729 m; h = 11.8960512 m; `pressureLoss` 116,660.4 Pa; static p_in 73,608.2, p_out −70,328.5 Pa (g); `pressureDrop` 143,936.7 Pa = 116,660.4 + 19,613.3 (ρgΔz) + 7,663.0 (velocity heads). Pins every term of the §3.3 identity. |
| `equipment_in_loop` | R1 z = 15 m, level 5 m (H 20 m) → 154.1 mm × 100 m → ideal tee T1 (z 5 m); leg A: 102.3 mm × 40 m → E5 (80 kPa at 20 L/s, ρ_r water at 15 °C; z 6 m) → 102.3 mm × 40 m; leg B (T1 branch → T2 branch): 77.9 mm × 120 m; ideal tee T2 (z 4 m) → 154.1 mm × 80 m → R2 z = 0, level 2 m; EPANET water, `swamee_jain` | Nested brentq: the split inside, the total outside | Q = 0.0360345011; Q_A = 0.0213608636; Q_B = 0.0146736374 m³/s; EGL T1 17.893958, T2 3.684833, E5 in/out 15.446402 / 6.132389 m; loop closure 2×10⁻¹³ |
| `equipment_assigned_demand` | R1 z = 20 m, level 5 m (H 25 m) → 102.3 mm × 60 m → E7 (30 kPa at 10 L/s, ρ_r water at 15 °C; z 2 m) → 77.9 mm × 30 m → assigned demand D of 12 L/s at z 1 m (D12); liquid A, Colebrook | Explicit | EGL E7 in/out 23.782960408 / 19.373829708 m, D 16.978845625 m; `pressureLoss` 43,152.324 Pa; `pressureDrop` 45,251.968 Pa (the 77.9 mm outlet's velocity head); static p at D 153,222.299 Pa |
| `equipment_kv_definition` | Custom liquid at the suite's reference water, ρ_w = 999.29744529767 kg/m³ (`element_laws.REFERENCE_WATER_DENSITY`), μ = 1 mPa·s; R1 z 10 m; E1 **Kv 60** at z 5 m; 102.3 mm × 60 m and × 40 m (Colebrook); R2 z 0, level 1 m | Explicit: H₁ − H₂ = h_L1(Q₁) + 1 bar/(ρ_w g) + h_L2(Q₁) = 13.98354526673 m with Q₁ = Kv m³/h; R1 level 4.98354526673 m | Q = Q₁ = 0.0166666667 m³/s; static Δp 100,000 Pa; EGL in/out 12.716016845 / 2.511685614 m. "The solve gives back the definition of Kv": the solver's flow is 1.2×10⁻¹⁰ off and its drop 8.2×10⁻¹¹, the suite's water against fluids' constant. |
| `equipment_cv_glycol` | The `equipment_line` network with E1 rated **Cv 90**, on built-in 30 % MEG at 5 °C (1043.470019 kg/m³, 3.55924 mPa·s), Colebrook | brentq on H₁ − H₂ = Σh_line(Q) + c_Cv Q\|Q\| | Q = 0.0170755360 m³/s; h = 6.3627292 m; `pressureLoss` 65,109.4599 Pa = (ρ/ρ_w)·1 psi·(Q/Cv gpm)², ISA eq. (1) with ρ₀ = ρ_w, fluids' `Kv_to_K` water (10⁻¹⁶; with `size_control_valve_l`'s ρ₀ = 999.1032908 kg/m³ it would be 65,122.1126 Pa, +1.9×10⁻⁴, the S2 difference D9 accepts); EGL in/out 9.217637537 / 2.854908308 m; static 61,373.014 / −3,736.446 Pa; pipe Re 62,306, so no laminar flag; `NO_VAPOR_PRESSURE` (glycol, D9) |
| `equipment_suction_strainer_npsh` | Built-in water at 50 °C, site 1500 m (`ATMOSPHERE_1976`); R1 z 0, level 2 m → `NPSH_SUCTION` (154.1 mm × 8 m, sharp entrance, LR elbow) → strainer S (10 kPa at 30 L/s, ρ_r water at 15 °C; z 4 m) → 154.1 mm × 1 m → PU1 (z 4 m, `curve_a`) → `NPSH_DISCHARGE` → R2 z 18 m, level 2 m (the inputs of `npsh_margin_standard_atmosphere`, with the strainer) | `pump_line_case`'s residual with −cQ² on the suction; NPSHa = H_s − z_s + (p_atm − p_v)/(ρg) | Q = 0.0323599743 m³/s; EGL S in/out 1.761701472 / 0.574175675 m; strainer loss 11,506.3102 Pa; H_s 0.557988064 m; NPSHa 4.010293945 m, NPSHr 3.478180814 m, margin 0.532113131 m (5.186774563 m NPSHa without the strainer); no flags |

**System curve** (`test_system_curves.py`). Pump → equipment → reservoir gives H_sys(Q) = Δz + Σh_line(Q) + cQ² at every point, explicitly.

### 7.2 EPANET cases (`generate_epanet_cases.py`, `epanet_model.py`)

- **Mapping.** As decision 20: the TCV setting is K_E unscaled, written by WNTR to 11 significant digits, as for isolation valves; a Cv or Kv takes `element_laws.k_from_flow_coefficient` on the inlet pipe's bore, the isolation valves' own path. One sentence is added to `source_text`.
- **Measured.** By V with WNTR 1.5.0 running EPANET 2.2 (D-W headloss, GPM, accuracy 10⁻⁵), by P for the loop, and by the second reviser for the Cv (`cvkv/check_cvkv.out.txt` D). Every row passes D6.

| Case | ΔQ (relative) | Largest Δ head | Notes |
|---|---|---|---|
| E1 line (`epanet_equipment_line`) | +4.47×10⁻⁴ | 1.2×10⁻⁴ m | TCV loss / cQ² = 0.999077 |
| E3 reverse | +4.47×10⁻⁴ | 1.2×10⁻⁴ m | The TCV passes flow both ways |
| E4 elevation, unequal pipes | +4.35×10⁻⁴ | 5.7×10⁻⁴ m | |
| E5 loop (`epanet_equipment_loop`) | +4.33×10⁻⁴ (Q_A +4.45×10⁻⁴) | 1.6×10⁻⁴ m | |
| P's loop (5 links) | 4.32×10⁻⁴ | 1.73×10⁻⁴ m | |
| E1, TCV with K × 1.000924 | +1.54×10⁻⁴ | | The remainder is the pipes' g = 32.2 ft/s² bias, as for every EPANET case |
| E1, a GPV with 201 curve points, forward and reverse | ±1.54×10⁻⁴ | | A GPV is the alternative; it was not chosen, being piecewise linear |
| E1 rated **Cv 90** (`epanet_equipment_cv_line`), K_E = 28.915301256 on 102.3 mm (`element_laws.k_from_flow_coefficient`, the mapping above; fluids' `Cv_to_K` gives 28.915301247, 3.1×10⁻¹⁰ apart, and the same EPANET result) | +4.471×10⁻⁴ | 1.2×10⁻⁴ m | TCV loss / cQ² = 0.999077, as for a rated point; reverse −4.471×10⁻⁴ |

Three EPANET cases ship: the line, the loop and the Cv line.

### 7.3 Goal seek and scenario references

- **`test_goal_seek.py`** (by a tester who has not read `services/`): closed-form inverses for each new goal and each new variable, at the default and at the smallest tolerance. Measured by the reviser (`check_revisions.out.txt`; the element emulated as a valve gives the target exactly):
  - **The three variables, goal `equipment_flow` = 0.016 m³/s on `equipment_line`:** with h_E = H₁ − H₂ − h_lines(Q*) and c* = h_E/Q*², ΔP_r* = ρ_r g c* Q_r² = 64,383.9587021 Pa; Q_r* = √(ΔP_r/(ρ_r g c*)) = 0.0132186597 m³/s; ρ_r* = ΔP_r/(g c* Q_r²) = 775.8940593 kg/m³.
  - **Variable R1 `liquidLevel`, goal `equipment_pressure_drop` = 130 kPa on `equipment_ports_differ`:** Δp_static = Q²[ρgc + ρ(1/A_out² − 1/A_in²)/2] + ρgΔz gives Q* = 0.0215801758 m³/s and level = H₂ + h_line(Q*) − z_R1 = 1.91286791 m; the loss there is 103,582.7 Pa.
  - **The same, goal `equipment_pressure_loss` = 100 kPa:** Q* = Q_r√(Δp*ρ_r/(ρΔP_r)) = 0.0212036832 m³/s, level 1.06637058 m; the static drop there is 126,181.9 Pa. A reader of the wrong field misses either goal by more than 20 %.
  - **Which c₁.** The two coefficient inverses below are printed with fluids' constants c₁ (§3.1), the solver's conversion, at which the solver meets each target to round-off. The reference test computes c₁ with the suite's own `k_from_flow_coefficient` (CoolProp's water, §3.1), which is 3.1×10⁻¹⁰ larger and gives each inverse 1.56×10⁻¹⁰ higher, far inside every goal tolerance. Both values are printed (`cvkv/fixer/check_fixer.out.txt`, `cv_star.out.txt`).
  - **Variable `rating.value` (Cv), goal `equipment_flow` = 0.016 m³/s on `equipment_cv_glycol`:** c* = h_E/Q*² and c = c₁/Cv² give Cv* = Q*√(c₁/h_E) = 81.0723929388 with c₁ = 1.76758281804×10⁸ s²/m⁵ (`check_cvkv.out.txt` E; the solver, with a valve stand-in, gives a flow of 0.016 there to 3×10⁻¹⁶), or 81.0723929515 with the suite's c₁ = 1.76758281860×10⁸.
  - **Variable `rating.value` (Kv), goal `equipment_pressure_loss` = 80 kPa on `equipment_kv_definition`:** h* = Δp*/(ρg), Q* from H₁ − H₂ − h* = h_lines(Q*) = 0.0208949307 m³/s on the case as written (reference water, H₁ − H₂ = 13.98354526673 m), Kv* = Q*√(c₁/h*) = 84.1004736136 with c₁ = 1.32248132708×10⁸ s²/m⁵ (the solver, with a valve stand-in, gives a loss of 80,000 Pa there to 4×10⁻¹⁶; `cvkv/review/r_constants.out.txt`), or 84.1004736267 with the suite's c₁ = 1.32248132749×10⁸. The value printed before, 84.1004736222, was computed on fluids' water (H₁ − H₂ = 13.98354526343 m), not on this case's fluid.
  - **Two parts of one scenario rating** (metamorphic, §5.2): on `equipment_line` with a scenario whose whole-`rating` override is E1's own rating at another rated pressure drop, variables `rating.pressureLoss` and `rating.flow`, and two goals, as D16's list rule requires (as many goals as variables): `equipment_flow` = 0.016 m³/s and `equipment_pressure_loss` = 73,320.43 Pa, the loss at that flow (ρ g h_E with h_E = c*Q*² = 7.4766035 m, c* = 29,205.482 s²/m⁵ from the inverse above), so the targets agree. The two variables act together through c (decision 15), so the values found need not be unique. Whether met or not, both variables' overrides are the same whole rating holding both found values, each names the scenario's override in `replacedOverride`, and each applied alone, and both applied, reproduce the reported state bit for bit (the test's `apply_problems`, which writes each at its `replacedOverride`).
  - **Not applicable:** `rating.value` on a point-rated element and `rating.pressureLoss` on a Cv-rated one are each 400 `VARIABLE_NOT_APPLICABLE`.
- **`test_scenarios.py`** (metamorphic): a "dirty strainer" override of `rating.pressureLoss`, a "vendor B" override of the whole rating as a point on another fluid, and a "vendor C" override of the whole rating as Cv 120, each solve bit for bit like the hand-edited project; `rating.value` on a point-rated element is `not_applicable`, and `rating` with `rating.flow` in one scenario is 400.
- **Unit test.** The element gives the same flows and heads as a gate valve with resistance K = K_E on the inlet pipe, to about 10⁻¹² relative, and an element rated Cv 90 or Kv 60 as a gate valve with that Cv or Kv (its c equal to the valve's to 2×10⁻¹⁵ relative, §3.1). This is the web's e2e check as well.

### 7.4 Independent checks

- **`network_check`** (reference suite): in `element_law`, the element is "open" with the residual h_in − h_out − `valve_loss(equipment_k(...)·k_scale, q, d_in, g)`, so the fsolve self-check covers every case.
- **`tests/differential/equipment_check.py`** (new; decision 21), a metamorphic check over the corpus. For each project with an active isolation valve (1,632 of 5,136, holding 2,047 valves: 979 `default`, 335 `flow_control`, 311 `assigned_flow`, 7 others), solve the project, then replace every active isolation valve that has a result by an element on the same ports and elevations:
  - A valve rated by a Cv or Kv (513 of the 2,047: 241 Cv and 272 Kv, in 484 projects: 481 of the three profiles, 2 reference cases and 1 unit fixture, `count_cvkv.out.txt`) becomes an element rated by the same Cv or Kv: its c equals the valve's to round-off (at most 6 ulp, §3.1), so this tests the coefficient path end to end.
  - Every other valve (496 K, 1,038 on the Crane default) becomes a rated point: ρ_r drawn with `Random(f"equipment:{name}")` uniform in 800–1200 kg/m³, Q_r = A_ref × 1 m/s and ΔP_r = ρ_r K_open (1 m/s)²/2, with `kOpen` and `referenceDiameter` from the valve's result, so c = K_open/(2gA_ref²) up to rounding; a valve whose ΔP_r would pass 10⁸ Pa is kept and counted.
  - Expected (D13): the same convergence; every flow, EGL and static pressure within D6, or different only at zero flow (listed, not failures); each element's `headLoss` within D6 of its valve's; and, in the element's own result, `pressureLoss` = ρg·`headLoss` and `pressureDrop` equal to the §3.3 identity from the port elevations and the end segments' velocities, both to round-off.
  - A smoke test pins a few projects (`test_equipment_check_smoke.py`, as `test_scenario_check_smoke.py`).
- **The corpus tools learn the type:** `tests/unit/scenario_patch.py` (`FIELDS["equipment"]`, `_component_value` for the five fields, a part only on its kind), `tests/reference/scenario_patch.py` (`COMPONENT_FIELDS[Equipment]`) and `test_scenarios.draw` (whole ratings of both kinds, and parts), `scenario_check.OUT_OF_BOUNDS` (a bad value for each field, and a whole rating of kind K), and `goal_seek_check`: `candidates` offers only the parts the element's kind holds (as `control.setpoint` only with control), `case_value` and `written` read and write them, `SPAN_FLOOR` gains `rating.density`, and `goal_value` and `goal_candidates` read the three goals from `equipmentResults`. Without them, `draw_overrides` and `hand_patched` raise `KeyError 'equipment'` on the new reference cases, `test_scenarios.draw` fails its last assert, and the new goals are never drawn.

### 7.5 Acceptance (D6, D13)

- **The reference suite is green,** with the ten cases in §7.1 and the three EPANET cases.
- **The corpus comparison** gives 5,136 identical (§3.5); on the branch's corpus, `scenario_check` gives 0 different, `goal_seek_check` 0 violations and `equipment_check` no difference beyond D6.
- **Fuzz.** The three existing profiles give 0 critical seeds, the same classes, and no converged solve left not converged.
- **The corpus** gains the new reference cases by itself (`corpus.py:76-79`); `corpus.py` does not change.

### 7.6 Unit, component and e2e tests

- **API unit tests:**
  - the law: odd, with slope 0 at 0;
  - the builder: the link kind, c computed in its order for each kind, a Cv's or Kv's c equal to the closed form and to the valve path on several bores within 2×10⁻¹⁵ relative (the measured maxima are 5.3×10⁻¹⁶ and 8.8×10⁻¹⁶, §3.1; neither is bit-exact), and the topology issue collected with the others, including the conversion's ZeroDivisionError and OverflowError;
  - the model's bounds and its published `x-port-ids` and `x-port-roles`; the union: each kind's required fields, a K or unknown kind refused without quoting it, and `_clean` matching a bad scenario value inside the union to its override;
  - zero flow between equal heads, and a dead end;
  - an element closed off between two isolated valves (no result, and a note);
  - an element in a floating pump loop;
  - the flags: reverse flow; laminar flow in the inlet pipe and in the outlet pipe (MEG at a low head, as the valves' Kv test), with the Re of the lower pipe; both together;
  - the trace: every input source `user`, the notes, and a Cv's equivalent rated point;
  - methods: a section only with equipment, the Cv/Kv item only with a coefficient, and a snapshot showing a summary without equipment unchanged;
  - goal-seek models: `EXPECTED` gains the Equipment row (three log fields, one linear), `NOT_VARIABLES` gains `rating`, and the pair test a point-rated Equipment base. `test_no_rule_reads_two_variables_of_one_element` asserts `len(fields) == 2` and writes every field of `EXPECTED[schema]` into one base, so it is generalized to every pair of the fields its base's kind holds: the point's three values give three pairs, and `rating.value`, held only by a Cv or Kv, has no pair on one element and is checked alone. `GRIDS` gains rows for the three values;
  - goal seek:
    - a part of the other kind is `VARIABLE_NOT_APPLICABLE` with its reason;
    - a part under the scenario's whole rating carries the whole rating with `replacedOverride` set;
    - two parts under one whole rating carry the same whole rating, holding both found values and built from the reported evaluation's dump;
    - a whole fluid's override is unchanged;
    - the replaced-part mark names the parts in the Scenario section and in the element's note (§5.2);
  - scenario text: `value_text` of a whole rating of each kind (§5.1);
  - `--ignore-empty` in `compare.py`;
  - the version pins (`test_methods.py`, `test_api_goal_seek.py` and the web fixtures that name 1.2.0).
- **Web unit tests:**
  - `factory`: valid against the schema and the model rules, the missing-value errors, the label and the prefix;
  - `model-rules`: the component union, the rating union and `ratingSchemaName`, `x-override-fields`, the log variables and the three quantities;
  - `schema-bounds`, `encoding` (a round trip of each kind) and `edit` (insertion orientation, with entered values in the loops over `COMPONENT_KINDS`);
  - `results`: the cells, ≈ 0, "—" for a coefficient's flow ratio, the view only when present, `rowsForElement` and `elementSummary`;
  - `compare`;
  - `goal-seek`:
    - `defaultBounds` gives lower < upper;
    - only the kind's parts are offered;
    - the notices name a found value by its variable, never "rating —", and list each of two parts under one whole rating once;
    - `keptByScenarios` lists a scenario with a whole-`rating` change for a base `rating.pressureLoss`;
  - `scenarios`:
    - `holderMatches` checks by kind;
    - `diffComponents` emits only the whole `rating`, both for an edit of the rated pressure drop and for a point → Cv switch;
    - `nextOverrides` makes one `rating.pressureLoss` change for that edit, one `rating.value` change for Cv 90 → 80 on a Cv-rated base, and one whole change for a change of kind, never a value and a part of it;
    - `overlappingChanges` is empty after each;
  - **the exhaustiveness test:** every numeric field in `x-override-fields` and `x-goal-variables` has a label, a value text with its unit, an export category and a variable spec, none of them the dimensionless default; a coefficient (`resistance`, `rating.value`) is the named exception, written with its kind ("Cv 80").
- **Component tests:**
  - `EquipmentForm`: accessible names "Rated pressure drop (kPa)" and "(psi)", never "(g)"; exact SI storage; the bounds message; each density button writes its exact double; Rated by: a Cv stored as entered, a pending kind that keeps the stored rating with its warning, no number carried between kinds; the scenario fields: a part change marked, with Reset, at its field, and a change of kind noted once at the group, with Reset (§6.2).
  - Every Add surface: the required errors first, then the element is added.
  - `ResultStrip`, `ResultsViews` (the tab, caption and note) and `GoalSeek` (the groups).
- **Export tests:**
  - both oracle blocks in `export/model.test.ts` (cells equal to the API values; the screen and the file read one field in one category);
  - the conditional About lines, and no Equipment sheet without equipment;
  - no values for a case that did not converge.

  Fixtures:
  - `apps/api/tests/fixtures/export_input.py`'s `scenario_project()` gains two elements, one rated by a point with a scenario change of its `rating.pressureLoss`, one rated by a Kv;
  - `export-input.json`, `export-results.xlsx` and `export-results.expected.json` are regenerated;
  - `test_web_export_fixture.py` gains the sheet and `expected_equipment()`.
- **E2E (`tests/equipment.e2e.ts`, desktop and phone):**
  1. **Build and solve.**
     - Build R1 (5 m) → 10 m NPS 4 pipe with a sharp entrance → E1 → 10 m NPS 4 pipe with an exit → R2 (0 m), with water at 20 °C.
     - Add E1 with Add after, see the three required errors, then enter 35 kPa at 10 L/s with This case's fluid (test inputs). Solve.
     - Expected, measured by W with a gate valve of K = 47.3021 on the 102.26 mm bore (S4): 11.2278 L/s, 112.278 %, pressure loss 44.1222 kPa, static drop 44.1222 kPa, head loss 4.5073 m.
     - The strip equals the table, and the trace shows the sources as User.
     - Share the link, reopen it, and see the same table.
  2. **Add before.** The insert path, including the layout test that the first click lands on Add.
  3. **Scenarios.** "Dirty strainer" sets 70 kPa (one change of the rated pressure drop). "Vendor B" picks Rated by Cv, sees the warning that the rated point applies until a Cv is entered, and enters 80 (test input): one whole-rating change. Solve all.
     - Compare's default rows include E1's flow and pressure loss; the dirty strainer's flow falls.
     - Vendor B's E1, measured with a gate valve of Cv 80 on the 102.26 mm bore (`cvkv/check_cvkv.out.txt` F): 12.6015 L/s, pressure loss and static drop 42.9327 kPa (equal to ISA eq. (1) with fluids' water), head loss 4.3858 m; Flow ÷ rated flow is "—" and left out of the strip.
     - The Export dialog lists the Equipment sheet with 3 rows for All cases.

### 7.7 Synthesizer's checks (`synth/checks.py`, `checks.out.txt`)

| # | Check | Result |
|---|---|---|
| S1 | EPANET's minor-loss constant against the exact 8/(gπ²) at our g, in ft and cfs | 0.0251933; 0.02517 / 0.0251933 = 0.999076, the measured TCV ratio |
| S2 | The reference densities in fluids 1.3.1 | `Kv_to_K` 999.29744568 kg/m³; `control_valve.rho0` 999.1033 kg/m³ (they differ by 1.9×10⁻⁴; D9 keeps `Kv_to_K`'s, and so does the Cv/Kv rating, §3.1) |
| S3 | The Blasius ratios (CoolProp 8.0.0) | water at 15 °C: 999.1026 kg/m³, 1.13757 mPa·s; 30 % MEG at 5 °C: 1043.4700 kg/m³, 3.55924 mPa·s; Blasius 1.3740 against the density rule's 1.0444, a ratio of 1.316; 0.5^0.25 = 0.841, 1.5^0.25 = 1.107 |
| S4 | The web's stand-in K_eq | ρ water at 20 °C 998.2072 kg/m³; K_eq = 47.30208 at D = 0.10226 m |
| S5 | Code facts the decisions rest on | Each flag code has one severity (`flags.FLAG_SEVERITY`: `CORRELATION_OUT_OF_RANGE` is a warning); `ValveLaw` rejects K ≤ 0; `gga.py` dispatches only on `CONNECTION` and `PUMP`; `NOT_VARIABLES` is keyed by field name and pinned by `test_goal_seek_models.py`; `AddComponentDialog` checks entries only in `after` mode; the corpus adds 1,000 seeds per profile |

---

## 8. Files to change

**API** (`apps/api/src/opensolve_pipe/`):
- `models/components.py` (`RatedPoint`, `RatedFlowCoefficient`, `EquipmentRating`, `Equipment`), `models/results.py`, `models/scenarios.py` and `models/goal_seek.py` (`LOG_FIELDS`, `NOT_VARIABLES`).
- `services/solver/{elements,network,builder,results,trace,methods,version,__init__}.py`, and the new `services/solver/equipment.py` (reusing `valves.k_from_coefficient`).
- `services/scenarios.py` (`COMPONENT_NAMES`, `MISSING_HOLDER`, `_clean`, `value_text`'s `rating` branch, and the replaced-part mark in `_replaced_mark` and `element_notes`, §5.1–§5.2) and `services/goal_seek.py` (`goal_value`, the not-applicable reasons, the whole-value rule of `whole_fluid` generalized, with each whole-value override built from the reported evaluation's dump, and the replaced parts passed to `annotate`).

**API tests and tools** (`apps/api/tests/`):
- `reference/{element_laws,case_format,network_check,closed_form,build_closed_form_cases,generate_epanet_cases}.py`, the new `derivations_equipment.py`, `cases/equipment_*.json` and three EPANET cases.
- `reference/test_goal_seek.py`, `test_scenarios.py` (`draw`), `test_system_curves.py` and `reference/scenario_patch.py` (`COMPONENT_FIELDS[Equipment]`).
- `unit/scenario_patch.py` (`FIELDS`, `_component_value`), the independent patcher `scenario_check` and `goal_seek_check` import.
- Unit tests, including `test_methods.py`, `test_goal_seek_models.py` and `test_web_export_fixture.py`.
- `fixtures/{export_input,scenario_cases,goal_seek_cases}.py`.
- `differential/compare.py` (`--ignore-empty`), `scenario_check.py` (`OUT_OF_BOUNDS`), `goal_seek_check.py` (`candidates`, `case_value`, `written`, `SPAN_FLOOR`, `goal_value`, `goal_candidates`), and the new `equipment_check.py` with `test_equipment_check_smoke.py`. `generator.py`, `corpus.py`, `checks.py`, `epanet_model.py`, `fuzz.py`, `classes.py` and `stats.py` do not change.

**Web** (`apps/web/`):
- `src/lib/api/{openapi.json,schema.d.ts,types.ts}`.
- `utils/factory.ts`, `components/panel/kinds.ts` and `state/workspace.svelte.ts` (`INLINE_KINDS`, `insert`, and `applyGoalSeek`'s notices, §6.4).
- `components/panel/{AddComponentDialog,NewComponentFields,PanelNavigator,ConnectionPanel,ComponentPanel,ResistanceField}.svelte`, plus the new `EquipmentRatingFields.svelte` and `forms/EquipmentForm.svelte`.
- `utils/{results,compare,goal-seek,scenarios,model-rules,issue-text}.ts` (in `scenarios.ts` also `diffComponents`; in `goal-seek.ts` the notices' texts by variable and `keptByScenarios`, §6.4), the new `utils/flow-coefficient.ts` (the coefficient labels and hints, moved from `ResistanceField`), and `utils/export/{tables,about}.ts`.
- `components/workspace/GoalSeekDialog.svelte` (the outcome announcement, §6.4).
- `components/results/{ResultsPanel,TraceView,CompareRowsDialog}.svelte`.
- `testing/{helpers,results}.ts`, with an `equipmentProject` and an `enteredFor(kind)` helper.
- The regenerated fixtures under `utils/__fixtures__/`.
- The new `tests/equipment.e2e.ts`.

**Docs:**
- **CLAUDE.md:**
  - a new **D18** (the model, the law, decisions 1–22 in brief, and the proof);
  - D5 moves "equipment by rated pressure drop or Cv/Kv" into v1 and keeps a head rating, curves, K on a diameter and the viscosity correction deferred;
  - D15's allow-list sentence ("The list is PRD §3.8's: …") gains an equipment's `rating` and its values, and D16's goal list ("a valve's flow or pressure drop, or a boundary's outflow") gains equipment's flow, pressure loss and static pressure drop, amended in place so D16 and D18 cannot disagree. D16's non-variables ("statuses, a pipe's `spec` and the whole `fluid`") gain an equipment's whole `rating`.
- **PRD:**
  - §3.1.2: one Equipment row, "Rated pressure drop at a rated flow, with the rating fluid's density, or a Cv or Kv; loss ∝ ρQ²", v1. It replaces Heat Exchanger and Strainer/Filter, and keeps User-Defined Element and a "K on a diameter, head rating, ΔP–flow curve, viscosity correction" row Later.
  - The port table, §3.8 and §3.9.
- **SDD:** §3.1.3 (an Equipment row in the results views), §4.2 (the component union and the comment), §4.10 SolvedState, §4.12 (the allow-list), §4.13 (the `GoalQuantity` union and the non-variables), §5.1.4 (the export's tables) and a new §4.14 Equipment Model (with the rating union).
- **TSD:** §4.9 (the solver mapping), §5.3 (the law table, with the Cv/Kv constants), §5.7 (scenarios and goal seek), §8.3 (`tables.ts` gains Equipment), §10.1 (the cases; the scenario row's "each of the 18 overridable kinds" becomes 23), §10.4 (the comparison and `equipment_check`) and §12 (the decided items).
- **This proposal:** marked as built, with an as-built section.

---

## 9. Later

- **Other ways to enter a rating** (Cv and Kv are in this slice, owner Q5), each a new member of the `rating` union:
  - a K on a stated diameter (PRD's user-defined element): unlike a Cv or Kv, a K means nothing without the bore it refers to, so it needs that diameter as a field;
  - a rating given as a head (ft or m of liquid, as US HVAC coil schedules give it), which needs the unit-aware entry of ui-ux item 11;
  - a mass-flow rating.
- **Other laws:** a ΔP–flow curve, or a two-point (aQ + bQ²) law.
- **Viscosity:** a Reynolds or viscosity correction, which needs geometry or a cited correlation per equipment type, or an optional rated viscosity with an information flag that has no threshold.
- **Reverse rating:** a direction-dependent rating for strainers and filters.
- **Clean and dirty:** a clean/dirty pair inside one component (scenarios cover it now).
- **Type and status:** a type label or presets (Q2), and a status (bypassed or isolated; valves do it now).
- **Screens:** `fluids.filters` screen correlations (Blevins), which need the open area and Re.
- **More than two ports:** multi-port equipment.
- **Heat transfer:** the solver is isothermal.
- **Design checks:** an out-of-rating check (flow far from Q_r) and an allowable-ΔP check, both opt-in (GOALS §4.6).
- **Examples and drawing:** an example project with a coil and a strainer, and a schematic symbol.
- **A fuzz profile `equipment`** (EPANET-compared, as the designers proposed): when `equipment_check` finds a difference, or the element gains behaviour an open valve does not have (a status, another law).
- **Not planned:** a "fixed pressure drop" that does not depend on the flow. A passive element dissipates nothing at zero flow. A drop of sign(Q)·ΔP would be a set-valued law needing status logic, and datasheets always give a drop at a flow (P). The PRD's "Fixed pressure drop" becomes "rated pressure drop at a rated flow".

---

## 10. Owner's answers (2026-10-26)

The design put six product questions to the owner, each with a recommended default; all stay reversible under D14. The owner answered on 2026-10-26:

1. **Rated fluid density: (a), as recommended.** Required, no default, with two one-click buttons, *Water at 15 °C* and *This case's fluid*, each writing an exact number labelled as user data (decisions 3 and 19). The options not chosen were (b) a cited default, water at 15 °C (ISA-75.01.01's 999.1 kg/m³), which would silently scale a coil rated on 30 % glycol by 0.96 and an exchanger rated on an 850 kg/m³ oil by 0.85 if left in place, and (c) an optional field meaning "the fluid being solved", which would leave a water rating used for glycol unscaled.
2. **Naming: as recommended.** One element that the user names, in one menu entry "Equipment (rated pressure drop)" under the group "Equipment: heat exchangers, coils, strainers, filters" (decisions 2 and 19). No type label; an optional one can be added later (§9).
3. **Reverse flow: not asked; the recommended default stands.** Flagged as a warning (`CORRELATION_OUT_OF_RANGE`), saying that the forward rating is used (decision 6). Not flagging it is ruled out by GOALS §4.6.
4. **Scenario allow-list: not asked; the recommended default stands.** Every rating value, so that a second datasheet is entered as printed (decision 14). With Cv/Kv (answer 5) that is the whole rating and each of its four values; goal seek follows (decision 15).
5. **Ways to enter a rating: Cv/Kv now, against the recommendation.** The recommendation was the rated point only. The owner chose to add Cv and Kv in this slice: decision 22, and the Cv/Kv path in §1.1, §2, §3.1, §3.4, §4, §5, §6 and §7. K on a stated diameter, a head rating, a mass-flow rating and curves stay Later (§9).
6. **Viscosity: as recommended.** No correction; the limit is stated in the trace and the methods text, and laminar flow in a connected pipe is flagged as for valves (decision 9). By Blasius, an element rated on water at 15 °C and run on 30 % MEG at 5 °C sees about 1.32× the drop the density rule gives, and the square law is about 16 % low at half the rated flow against Q^1.75 (§3.1).

---

## 11. Review record

Two reviewers (physics: R-P; product: R-Q) checked the design. The reviser checked each finding against the code or by calculation (`reviser/check_revisions.py`, `check_npsh.py`, `count_iso.py`, with their `*.out.txt`). Each was upheld and the design was revised at the root. The duplicates (1 and 10, 5 and 11, 8 and 13) were fixed once. Row 20 records the second reviser's revision for the owner's answers (§10), checked the same way (`cvkv/model_shape.py`, `check_cvkv.py`, `check_kv_reference_water.py`, `count_cvkv.py`, with their `*.out.txt`). Rows 21–31 record the findings of the reviewers who then checked that revision (17 findings, numbered F1–F17 in the order they were given; duplicates share a row). A fixer checked each one against the code at `bbafbff` or by calculation (`cvkv/fixer/check_fixer.py`, `cv_star.py`, `two_parts_fix.py`, with their `*.out.txt`). Every finding was upheld and fixed at the root; none was rejected.

| # | Finding (severity, reviewer) | Verdict | What changed |
|---|---|---|---|
| 1 | The schema's advice for a datasheet drop that includes a static head is wrong (should fix, R-P) | Upheld. Reproduced: −10.51 % in flow for a 2 m nozzle rise; the corrected entry, S_r − ρ_r g Δz with real elevations, gives the true flow exactly. | Decision 4 and §2.1: keep the real port elevations, convert a static S_r as S_r − ρ_r g Δz − ρ_r Δ(v²)/2. The form hint (§6.2) says the same. |
| 2 | The square law goes unflagged in laminar flow, though valves flag the same ISA law (should fix, R-P) | Upheld. `results.py:913-938` and `methods.py:411` flag a Cv or Kv at Re < 2000 in the inlet pipe. | Decision 9, §3.2, §3.6, §4: `CORRELATION_OUT_OF_RANGE` (warning) at Re < `RE_LAMINAR_MAX` in either connected pipe, with the trace, methods text, unit tests and Q6. |
| 3 | Three reference-case specs do not match their numbers (should fix, R-P) | Upheld, all three reproduced: the loop uses E5 (80 kPa at 20 L/s), not E1; 43,152.324 Pa is the loss, and the static drop is 45,251.968 Pa; the inverse on `equipment_line` is 64,383.9587021 Pa. | §7.1 states every input and names each field; §7.3's inverse is on `equipment_line`. P's line example was dropped (its inputs were not stated). |
| 4 | No case separates the static drop from the loss, and none has port elevations that differ (should fix, R-P) | Upheld. | `equipment_ports_differ` puts the outlet port 2 m up (every term of the §3.3 identity pinned, §3.3). The drop and loss goals run on it, 20 % apart (§7.3). |
| 5 | The scenario patcher and `goal_seek_check` are not updated (should fix, R-P) | Upheld. `draw_overrides` raises `KeyError 'equipment'`; `goal_value` has no equipment branch. | §3.5, §7.4 and §8 list both patchers, `test_scenarios.draw`, `scenario_check.OUT_OF_BOUNDS` and `goal_seek_check`'s readers. |
| 6 | Decision 4's reason has the sign reversed: a static law gives a negative loss where the outlet narrows (nit, R-P) | Upheld, by D7: h = S/(ρg) + (v_in² − v_out²)/(2g). | Decision 4: "narrower"; "dissipative (friction and form)"; nozzle charts measure the loss only for equal bores and elevations. |
| 7 | "All are negative in reverse flow" is false for the static drop (nit, R-P) | Upheld: the elevation and velocity terms do not change sign. | §6.3's note names the signed columns and says the static drop's sign need not follow the flow. |
| 8 | "No source gives a default rating fluid" contradicts the sources (nit, R-P) | Upheld: Eaton and Islip rate on water; ISA-75.01.01's ρ₀ is water. | Decision 3 and §1.3 item 1 say so and why the field stays required; Q1 offers the cited default as option (b). |
| 9 | `equipment_problems` is underspecified, and the NPSH case has no numbers (nit, R-P) | Upheld. | The pressure-drop identity check is in `equipment_check` (§7.4; the fuzz profile is gone). `equipment_suction_strainer_npsh` has its full inputs and values (§7.1), confirmed by the solver. |
| 10 | Same as 1 (should fix, R-Q) | Upheld: −14.07 % in flow, reproduced. | As 1. |
| 11 | The new cases join the corpus and crash the tools; the patchers are missing from §8 (should fix, R-Q) | Upheld: `corpus.py:76-79` adds every reference case; `reference/scenario_patch.py:132` and `test_scenarios.draw` fail too; positions shift, so "same outcomes" cannot be claimed. | As 5, plus §3.5: the gates run on the branch's whole corpus, and goal seek's gate is the violation count. The fuzz-tool items fell away with 15. |
| 12 | Leaving the rated flow and density out of goal seek does not work as described and breaks D16 (should fix, R-Q) | Upheld: `_variable` never reads `NOT_VARIABLES`; the test pins numeric values as variables; `liquidLevel` and `surfacePressure` are already a collinear pair. | Decision 15 and §5.2: all three are variables, with no change to `_variable`, `NOT_VARIABLES` or D16; §7.3 has an inverse for each; the web gets default bounds for each. (Row 20 adds `rating.value` and puts the whole `rating` in `NOT_VARIABLES`, as the whole `fluid` is.) |
| 13 | Q1 leaves out the cited default; the case-fluid button cancels the scaling for water-rated strainers (should fix, R-Q) | Upheld. | Q1 has three options; decision 19 and §6.1–§6.2 add a *Water at 15 °C* button next to *This case's fluid*, with a hint naming which sheets use which. |
| 14 | §8 misses D15, D16 and the spec sections that list kinds (should fix, R-Q) | Upheld, each location checked. | §8: D15's and D16's lists amended in place; SDD §3.1.3, §4.12, §4.13, §5.1.4; TSD §5.7, §8.3, §10.1 (18 → 21 kinds). (Since row 20 the rating adds five entries, so 18 → 23, as §8 says; row 30.) |
| 15 | A fuzz profile adds upkeep where a valve-equivalence check over the corpus would cover more (should fix, R-Q) | Upheld: the law is `ValveLaw`'s form, and an active isolation valve is a fixed-OPEN control that the status rules and `flow_limit` treat as no control. 1,632 corpus projects hold 2,047 such valves, in all three profiles. | Decision 21 and §7.4: `equipment_check` replaces the profile, which is Later (§9); `generator`, `checks`, `epanet_model`, `fuzz`, `stats` and `corpus` do not change. |
| 16 | The 1.3.0 bump shows the method-change notice on every existing link (nit, R-Q) | Upheld as a cost to state. It is not an owner question: keeping 1.2.0 would make an equipment result name a method version without equipment (GOALS §4.3, D11). | Decision 17 states the cost, and that the notice lists the changelog line saying those values are unchanged. |
| 17 | Q3's "no flag at all" is ruled out by GOALS §4.6 (nit, R-Q) | Upheld. | Q3 drops it and says why. |
| 18 | `ratedPressureDrop` pairs with `pressureLoss`, not `pressureDrop` (nit, R-Q) | Upheld. | The API field is `ratedPressureLoss` (since row 20, `rating.pressureLoss`), labelled "Rated pressure drop" on screen (decisions 3 and 11); the export column is "Rated pressure drop (loss)". |
| 19 | Name `INLINE_KINDS`; "navigator unchanged" contradicts §8 (nit, R-Q) | Upheld: `AddComponentDialog.svelte:79-86`, `PanelNavigator.svelte:160`. | §6.1 adds `'equipment'` to `INLINE_KINDS` and lists every `ENTRY_KINDS` site; §6.4 says only the first-component form changes. |
| 20 | The owner's answers to §10 (2026-10-26): Q1 (a), Q2 and Q6 as recommended, Q3 and Q4 not asked, and Q5 **Cv/Kv in this slice**, against the recommendation (owner) | Folded in at the root by a second reviser. Each fact the Cv/Kv design rests on was checked against the code at `bbafbff` and fluids 1.3.1: the valves' `FlowCoefficient` (stored as entered) and `k_from_coefficient`; the allow-list's whole `resistance`; goal seek's `coefficient` variable (written whole, log scale, middle start); the holder test, overlap rule, `_variable` and `whole_fluid`. Measured: fluids' K = 1.6×10⁹D⁴/Kv² is the rated point 1 bar at Kv m³/h on water at 101.25π² = 999.297445610 kg/m³ (its docstring's 999.29744568, 7×10⁻¹¹), its Cv constant is the unit definitions' to 1.9×10⁻¹⁶, and c at a 1 m bore is within 2 ulp of the valve path on bores from 12.7 mm to 2.5 m for the four coefficients measured (row 28 gives the bound over all draws: 6 ulp). Found on the way: inside the bounds the conversion can raise ZeroDivisionError or OverflowError rather than give ∞ (as `_unrepresentable_valves` already catches); the union's error locations carry its tag, which `_clean` must drop; and the web's `holderMatches` accepts any rating today. | §10 records the answers, and the status line and §1 say so. Decision 22 makes the rating a union, a rated point or a Cv/Kv (`RatedFlowCoefficient`, `FlowCoefficient` narrowed); decisions 3, 5, 10, 11, 14, 15 and 19–21 and §2–§8 carry the Cv/Kv path: the law and its proof (§3.1), `equipment.py` reusing `k_from_coefficient`, the trace's equivalent rated point, the methods item, the allow-list (`rating` and four parts, `MISSING_HOLDER`, `_clean`), goal seek's four parts (`rating` in `NOT_VARIABLES`; the whole-value rule generalized), export's Rated by and Flow coefficient columns, the web's Rated by with `ResistanceField`'s hints and pending-kind rule, `holderMatches`, `nextOverrides` and `ratingSchemaName`. Verification gains `equipment_kv_definition` and `equipment_cv_glycol` (§7.1), the EPANET case `epanet_equipment_cv_line` (§7.2), Cv* and Kv* inverses (§7.3), the 513 Cv/Kv valves in `equipment_check` (§7.4) and the e2e Vendor B scenario (§7.6). K on a stated diameter stays Later (§9). |
| 21 | F1, F8: with two parts of one scenario whole rating as variables, each override carries only its own found value, so applying them loses one (should fix, both) | Upheld. `_Var.override(x, prepared.dump)` builds the whole value from the case dump with only its own part set (`goal_seek.py:1475-1500`, `:2337`), and `UNIQUE_BY` allows two parts of one element (`models/goal_seek.py:478-481`). The reference test, the web's `upserted` and `goal_seek_check` all keep the last override. Reproduced by the fixer: False today, True when the overrides are built from the reported evaluation's dump (`two_parts_fix.out.txt`). | §5.2: every part variable under one whole rating carries the same whole rating, holding all found parts and built from the reported evaluation's dump; the fluid's override is unchanged bit for bit. §7.3 adds a metamorphic two-part case, §7.6 the unit tests, §8 the change. |
| 22 | F2, F10: `diffComponents` emits the whole `rating` and each changed part as raw changes, so one edit would store "a value and a part of it" (400) (should fix, both) | Upheld. `scenarios.ts:535-553` pushes a raw change for every allow-list entry that differs, and `read` returns a missing part as null. `diffCase` pushes the fluid once, and `nextOverrides` special-cases only `fluid`. | §6.4: `diffComponents` emits only a whole value's raw change, never its parts' (the general rule: an entry whose path is a proper prefix of another's). `nextOverrides`' rating rule is stated step by step. §7.6 pins both, with `overlappingChanges` empty. |
| 23 | F3, F11: §6.2 and §6.4 disagree on whether a Cv or Kv value edit is a whole-rating change or a `rating.value` change (nit; should fix) | Upheld: the two sentences conflict. | One rule, the fluid's: a value edit within the base's kind is a part change, so Cv 90 → 80 is `rating.value`, consistent with the allow-list, goal seek's Apply and the export text. Only a change of kind is a whole change. §6.2 and §6.4 say so, and §7.6 tests both. |
| 24 | F4, F12: the web's goal-seek helpers special-case only the whole fluid: `keptByScenarios`, `overrideValueText` ("rating —") and `variableLabelOf` (nit; should fix) | Upheld. Checked at `goal-seek.ts:2095-2142` and `units.ts:249`. | §6.4: the notices take each label and value from its `VariableResult`, not from its override. `keptByScenarios` also checks every whole value the field is part of. Apply needs no change (equal overrides upsert to one). §7.6 and §8 list them. |
| 25 | F9: the API's scenario note and methods text would print a whole rating as a Python dict, and the goal-seek mark would say the whole rating was replaced (should fix) | Upheld. `value_text('rating', …)` returns the dict's repr (run by the fixer). `_replaced_mark` and `element_notes` word only a whole value or the fluid's temperature. | §5.1: `value_text` gains a `rating` branch ("Cv 120", "50000 Pa at 0.015 m³/s, 999.1 kg/m³"). §5.2: the mark names the replaced parts, with `REPLACED_TEMPERATURE` unchanged. §7.6 and §8 list them. |
| 26 | F5, F14: Kv* (§7.3) was printed from fluids' water and K_E of the Cv EPANET case (§7.2) from `Cv_to_K`, not from the case and the mapping the design specifies (nit, both) | Upheld. On the case as written, Kv* = 84.1004736136 with fluids' c₁, or 84.1004736267 with the suite's own. K_E by `element_laws.k_from_flow_coefficient` is 28.915301256. EPANET's flow is the same with either K_E (+4.4707×10⁻⁴). (`check_fixer.out.txt`, `cv_star.out.txt`, `review/r_epanet.out.txt`.) | §7.3 says which c₁ each inverse uses, prints both values (Cv* too: 81.0723929388 and 81.0723929515), and records where 84.1004736222 came from. §7.2 prints K_E = 28.915301256 and names fluids' value. |
| 27 | F6: "ISA eq. (1), 10⁻¹⁶" for `equipment_cv_glycol` holds only with fluids' `Kv_to_K` water, not with the ρ₀ of the cited `size_control_valve_l` (nit) | Upheld. With ρ₀ = 999.1032907570 the same flow gives 65,122.1126 Pa (+1.9×10⁻⁴), within D6 (`check_fixer.out.txt`). | The §7.1 row says "ISA eq. (1) with ρ₀ = ρ_w, fluids' `Kv_to_K` water", and gives the cited ρ₀'s value and the S2 difference. |
| 28 | F13: "within 2 ulp on any bore" and "equal to the closed form" are false beyond the four values measured (should fix) | Upheld. Over 300,000 draws the unit-bore c differs from the valve path by up to 6 ulp (8.8×10⁻¹⁶) and from the closed form by up to 4 ulp (5.3×10⁻¹⁶). It is bit-equal to the closed form in only 49 % of draws (`check_fixer.out.txt`; the reviewers' sweeps agree). | Decision 5, §3.1, §7.3, §7.4 and §7.6 give the measured maxima. The tests compare at 2×10⁻¹⁵ relative, never as equal or within a fixed number of ulp. Row 20 notes its narrower measurement. |
| 29 | F15: the pair test asserts two variables per base, so an Equipment row needs more than a new base (nit) | Upheld. `test_goal_seek_models.py:204-212` asserts `len(fields) == 2` and writes every `EXPECTED` field into one base, which a point base cannot hold for `rating.value`. | §7.6: the test runs every pair of the fields its base's kind holds, and `GRIDS` gains three rows. |
| 30 | F7, F16: "A rating is the three numbers together" (§1.3 item 4) and row 14's "18 → 21 kinds" (nit, both) | Upheld. The allow-list counts 14 + 2 + 2 = 18 entries today, and Equipment adds 5. | §1.3 item 4 says "a rated point is the three numbers together (a Cv or Kv is one)". Row 14 notes 18 → 23, as §8 says. |
| 31 | F17: the Cv default bounds' rationale holds only against a K, and the form hint assumes a rated point (nit) | Upheld. `defaultBounds` gives a valve's `resistance` [v/100, 100v] for a K, a Cv and a Kv alike (`goal-seek.ts:963-967`), so the same Cv gets different ranges on a valve and on equipment. | §6.4 keeps [v/10, 10v] as a deliberate designers' default. Its reason is now that a Cv is a rated flow at a stated drop, so it gets the rated flow's range, and the departure from the valves' range is named with its reason. §6.2's hint says "its own rating: a higher rated pressure drop, or a lower Cv or Kv". |
