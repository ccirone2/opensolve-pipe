# Design proposals

One proposal per feature. A proposal is the record of how a feature was designed: the owner's request, what was already decided, the designers' angles and measurements, the owner's answers, the review record and, once built, the **as-built** section listing every departure from the design. After the build the proposal is frozen except for that section; the decision file in [`../decisions/`](../decisions/README.md) is the binding summary.

Read a proposal when you need to know *why* a feature is shaped as it is, or when designing its next slice (each has a "Later" section). For *what* was built, read the decision; for the counts, TSD §10.4.

| Proposal | Status | Decision | Read for |
|---|---|---|---|
| [`vfd-industry-conventions.md`](vfd-industry-conventions.md) | research notes | D11 | How AFT Fathom, WaterGEMS, EPANET and PIPE-FLO define controlled pumps (cited) |
| [`vfd-pump-modes.md`](vfd-pump-modes.md) | slice 1 built; slices 2–3 designed, not built | D11 | Flow-setpoint pumps: formulation, uniqueness test, status rules, §10 owner's answers |
| [`vfd-slice2-discharge-pressure.md`](vfd-slice2-discharge-pressure.md) | **shelved** (D13); C0b built as 1.2.0 | D7, D13 | The round-off-aware stop test (§2.11.10); the discharge-pressure design and its measurements, kept as notes |
| [`scenario-manager.md`](scenario-manager.md) | built | D15 | The allow-list, the client mirror, edits in a scenario, Compare; §10 as built |
| [`goal-seek.md`](goal-seek.md) | built | D16 | The search (§3), tolerances, the web dialog; §12 as built |
| [`export.md`](export.md) | built | D17 | Workbook and CSV contents, the SpreadsheetML and ZIP writers, licensing; §12 as built |
| [`ui-ux-refinement.md`](ui-ux-refinement.md) | Tier 1 and items 6, 8–10 built | — | Measured friction in the web app and the remaining opportunities |
| [`landing-page.md`](landing-page.md) | built (web only) | — | The owner's answers on the landing page's goals, its sections and sources, recent projects on this device, the hand-taken screenshots; §5 as built |
| [`build-density.md`](build-density.md) | built (web only) | — | The Build forms measured; the field registry, density tokens and the budgets CI enforces; six disciplines' and the red team's findings in `build-density/`; §11 as built |
| [`equipment-pressure-drop.md`](equipment-pressure-drop.md) | built | D18 | The rated-point and Cv/Kv law, the density scaling, §9 Later, §10 owner's answers, §12 as built |
| [`pump-chart.md`](pump-chart.md) | slices 1–3 and 4a–4d built | D19, D21 | What an engineer reads from a pump chart; the slice plan; §9–§10 as built |
| [`design-checks.md`](design-checks.md) | built | D19 | The check framework, presets and their citations; §7 as built |
| [`orifice-plate.md`](orifice-plate.md) | built | D20 | ISO 5167-2 as implemented, the named departures and their measured size, §10 owner's answers, §12 as built |
| [`pump-groups.md`](pump-groups.md) | slices 4a–4d built | D21 | The station frame, the group curve and the group system curve, three designs reconciled (§11), §13 owner's answers, §14–§17 as built |
| [`project-library.md`](project-library.md) | built | D22 | References not templates, the K-at-a-bore conversion, §9 Later, §10 owner's answers, §12 as built, appendix prototype |
| [`pressure-relief-valve.md`](pressure-relief-valve.md) | built | D23 | The law and its three named departures, the band convention accepted as an exception, §10 owner's answers, §12 as built |
| [`pump-lineups.md`](pump-lineups.md) | slices L1 (L1a, L1b), L2 and L3 built (web only) | D24 | Lineups as status-only scenarios: the presets, the naming and follow rule, the pump table, the curve family; §13 owner's answers, §14 review record, §15 as built |
| [`pumps-results-layout.md`](pumps-results-layout.md) | accepted (2026-11-05); S0 and S1 built (web), S2 to S8 and A1 (an API slice for words) to build | D21, D24 | The Pumps tab below the pump chart measured (three projects, both sizes); one anatomy for both charts, headed sections, a sticky section nav, flags on screen, every feature kept; the rings explained one step away and the extremes a table; the slices S0–S8 and A1; §12 the owner's answers, §15 as built |

## Writing one

The built proposals share a shape; [`../workflow.md`](../workflow.md) §2 lists it. Keep the status line current, number the as-built departures, and quote the owner's answers with their date. Several proposals are long (the relief valve's is 146 KB) because they hold the designers' measurements; that is their purpose, and the decision file is the short form.
