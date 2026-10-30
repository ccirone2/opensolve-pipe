# D18. Equipment pressure drop (owner, 2026-10-26)

Decision D18 of the OpenSolve Pipe decision record ([index](README.md)). Decisions override the specs; `docs/GOALS.md` overrides decisions. Code and tests cite this decision as `CLAUDE.md D18`.

Design proposal: [`equipment-pressure-drop.md`](../proposals/equipment-pressure-drop.md).

---

Built from `docs/proposals/equipment-pressure-drop.md` (physics, sources and web designers, a synthesizer, two reviewers, a reviser, the owner's answers of 2026-10-26 in its §10 and a second reviser; then a contract builder, API, reference, corpus-tool and web builders, and integrators; its §12 records the as-built departures). Specs: PRD §3.1.2, SDD §4.14, TSD §4.9.

### Model

`Equipment`, type `equipment`, ports `inlet` → `outlet`: one side of a heat exchanger, a coil, a strainer, a filter or any passive element whose datasheet gives its loss. No type field (the user names it) and no status (valves isolate and bypass it). A required `rating` with no default, a union on `kind`: a **rated point** `{kind: 'point', pressureLoss, flow, density}` (Pa, a difference, in (0, 10⁸]; m³/s in (0, 100]; kg/m³ in (0, 3×10⁴]), the datasheet's drop at its flow for a fluid of the stated density, which is required (owner, 2026-10-26: a water default left in place would mis-scale a coil rated on glycol); or a **Cv or Kv** `{kind, value}`, `FlowCoefficient` narrowed to Cv and Kv, stored as entered, (0, 10⁷]. A K alone is not a kind: it means nothing without its bore (Later). An unknown kind is 400 `invalid_rating`, never quoting it. Each value's only rule bounds it, so no new `x-` extension. `schemaVersion` stays 1 (an additive type, D14). *(GOALS §4.1: no source gives a default rating.)*

### Law

h = EGL_in − EGL_out = cQ\|Q\| (`elements.QuadraticLossLaw`, `LinkKind.EQUIPMENT`), c computed once (`services/solver/equipment.py`): c = ΔP_r/(ρ_r g Q_r²) for a rated point; c = K/(2gA²) for a Cv or Kv, K from the valves' `k_from_coefficient` (fluids `Cv_to_K`/`Kv_to_K`, ISA-75.01.01) at a 1 m bore. K ∝ D⁴, so c is the same on every bore and a Cv or Kv needs no pipe: it is a rated point on water (1 psi at Cv US gpm, 1 bar at Kv m³/h, ρ_w = 999.297 kg/m³, fluids' water). So ρgh = ΔP_r(ρ/ρ_r)(Q/Q_r)\|Q/Q_r\|: ISA-75.01.01 eq. (1) at constant C, the high-Re limit of Darby's 3-K. ΔP_r is the dissipative loss of total pressure between the ports (the EGL drop × ρ_r g), without their static head; the static drop is ρgh + ρg(z_out − z_in) + ρ(v_out² − v_in²)/2 (D7), so resizing a pipe beside it never changes its loss. Zero flow takes the valve path (the GGA's Jacobian floor; the law stays exact); `gga.py`, `status.py` and `system_curve.py` are unchanged, and a system curve through it holds cQ². A c that is not a finite positive double, or a conversion that divides by zero or overflows inside the bounds, is the topology issue `EQUIPMENT_RATING_OUT_OF_RANGE` (422, listed after the other issues, quoting the rating). *(GOALS §4.1: exact, and checkable by hand.)*

### Limits, flagged

Viscosity is not corrected (owner): the loss scales with density only; by Blasius an element rated on water at 15 °C and run on 30 % MEG at 5 °C sees about 1.32× what the law gives. Reverse flow (the symmetric law) and laminar flow (0 < Re < 2000 in the end segment of a connected pipe, the lower of the two, as a valve's Cv or Kv) each raise `CORRELATION_OUT_OF_RANGE` (warning). No flag for a flow far from the rating: no source gives a threshold, and design checks are opt-in. *(GOALS §4.6.)*

### Results and traceability

`SolvedState.equipmentResults`, always present (`{}` without equipment or when the solve did not converge): flow, `flowRatio` (Q/Q_r, null for a Cv or Kv), `headLoss`, `pressureLoss` = ρg·headLoss, `pressureDrop` (static, as a valve's) and the `rating` used. A closed-off element has no result; one in a floating section has its flow and head differences. Its trace gives the rating as entered (source `user`), c, h_r or a coefficient's equivalent rated point with ρ_w, Q/Q_r, the connected pipes' bores, velocities and Re, the head loss as solved and by the law, every term of the static-drop identity, and notes (the rated-drop definition, the density ratio, the viscosity limit, each flag's inequality). An "Equipment" methods section after Valves and one assumption appear only when the project has equipment, and its Cv/Kv item only with a coefficient. *(GOALS §4.2.)*

### Scenarios and goal seek

D15's allow-list gains the whole `rating` and its four values; a value the item's kind does not hold is `not_applicable`, and a rating with one of its values in one scenario is 400. Goal seek varies the four values (log scale, the density linear), never the whole rating; three goals, `equipment_flow`, `equipment_pressure_loss` and `equipment_pressure_drop`, which are also Compare's rows. Values varied inside a whole rating that the scenario sets each get that whole rating holding every value found, built from the reported evaluation's case (the rule a fluid's temperature had, generalized), and the marks name the values replaced; a variable's `baseValue` is null where the base rates the item by another kind (a Kv's number is not a Cv). The rated drop's trace unit is `Pa (difference)`. *(GOALS §4.2.)*

### Designers' web defaults (reversible, D14)

One menu entry, "Equipment (rated pressure drop)", in the group "Equipment: heat exchangers, coils, strainers, filters", id prefix `E`; every path that creates one asks for its rating first, the error at each empty field. **Rated by**: a pressure drop at a flow, Cv or Kv; the density has two buttons, *Water at 15 °C* and *This case's fluid*, each writing the API's exact value as user data (owner). An Equipment results view after Valves; a Build strip of flow, flow ÷ rated flow and pressure loss; Compare rows; goal-seek groups with default bounds ×10 either way (×2 for the density); an Equipment export sheet holding the rating each solve used (its one departure from the screen's table), with About lines only in a file that has it. In a scenario an edit within the base's kind is a change of that value, a change of kind one whole-rating change; a base switch between Cv and Kv removes the scenarios' `rating.value` changes, as D15's PRV/PSV↔FCV rule does. *(GOALS §4.7.)*

### Versions

`METHOD_VERSION` 1.3.0: the deployed 1.2.0 has no equipment, so an equipment result names a version that has it (GOALS §4.3, as D11). Its changelog line says that projects without equipment are unchanged in every value; every link last solved with 1.2.0 shows the method-change notice after its next solve.

### Proof

15 reference cases: 12 closed-form (among them the solve giving back the datasheet, the definition of Kv, a Cv on glycol, ports at different elevations and bores pinning every term of the static-drop identity, a loop, an assigned demand, a suction strainer's NPSHa, and both flags) and 3 EPANET, each element a TCV of K = 2gA²c between junctions (EPANET's flows 4.2–4.5×10⁻⁴ higher, relative, the loop's bypass leg 4.16×10⁻⁴: its minor-loss constant is rounded to 0.02517); goal-seek inverses G25–G32 and scenario tests, all by a tester who did not read `services/`. The corpus comparison against `3da03c1`: 5,136 identical, 0 different, with `--ignore-empty equipmentResults` (5,136 empty maps) and the two method-version paths. `scenario_check` 0 different. The new `tests/differential/equipment_check.py`, in place of a fuzz profile, replaces every active isolation valve that has a result by an element of the same c (one rated by a Cv or Kv by the same coefficient): 1,781 valves in 1,414 corpus projects, 0 different, the largest differences 7.8×10⁻¹⁰ of the largest flow and 6.4×10⁻⁷ m of head. The three fuzz profiles give the same 9,000 records as `3da03c1`; `goal_seek_check` over the whole corpus, 5,151 projects (15,405 goal seeks), 0 violations; the `equipment` e2e flows on desktop and phone. TSD §10.4 has the counts.
