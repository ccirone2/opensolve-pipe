# D19. Design checks (owner, 2026-10-27)

Decision D19 of the OpenSolve Pipe decision record ([index](README.md)). Decisions override the specs; `docs/GOALS.md` overrides decisions. Code and tests cite this decision as `CLAUDE.md D19`.

Design proposal: [`design-checks.md`](../proposals/design-checks.md).

---

Built from `docs/proposals/design-checks.md` (slice 3 of `pump-chart.md`, widened to PRD §5's check library; its §7 records the as-built departures). Specs: PRD §5, SDD §4.15, TSD §5.8.

### Model

`ProjectSettings.designChecks` (omitted when none is on; `schemaVersion` stays 1, D14): `npshMargin {minimumMargin?, minimumRatio?}`, `operatingRegion {preferredMin?, preferredMax?}` (fractions of the BEP flow) and `pipeVelocity {minimum?, maximum?}`, each with a `source`, `{kind: 'user'}` or `{kind: 'preset', preset}`. Every limit is user data (owner); a preset only fills limits in, `api610_por` (0.7–1.2) or `hi961_2012_general` (ratio 1.1 or 1.0 m, the greater), each cited through the secondary source that quotes it, since the standards were not read (owner), and published as `x-design-check-presets`. Each check's source takes only its own preset, holding exactly its values (else 400), so no result cites a standard for limits it does not give. No velocity preset: no source read suits every fluid and use. A `designChecks` with no check present is none. `PumpCurve` gains optional manufacturer data at rated speed (owner): `allowableOperatingRegion {flowMin, flowMax}`, `minimumContinuousStableFlow`, `minimumThermalFlow` and `motorRatedPower` (W); the solve reads none of them. The ordered pairs are `x-ordered-fields`. *(GOALS §4.1: no uncited limit.)*

### Checks

Computed by the API from a converged solved state (`services/design_checks.py`), never in the solver: `SolvedState.designChecks` (always present; `[]` without checks or when the solve did not converge), per pump in component order, then per connection: `npsh_margin` (NPSHa ≥ max(NPSHr + margin, ratio × NPSHr)), `operating_region` (Q/Q_BEP, the BEP at the running speed) and with it the manufacturer data at the rated-speed flow Q/s, `allowable_region`, `minimum_flow` (the larger minimum) and `motor_power` (P_shaft ≤ the rating, no service-factor margin), and `pipe_velocity` (every pipe of a connection, `pipeIndex` and `pipesOutside` 0-based). Each is pass, fail or not evaluated with the reason, with its value, limits, unit, source and the inequality in its message (6 significant digits, or as many more as tell a value from its limit); a "Design checks" methods section, last, only when a check is on. Design practice, never a flag: a check changes no solved value, status or flag (GOALS §4.6). `METHOD_VERSION` stays 1.3.0: no calculation changes. *(GOALS §4.2.)*

### Designers' web defaults (reversible, D14)

Settings → Design checks: a switch per check, limits in display units, the preset buttons; a typed limit makes the source the user's; a pair out of order is refused with the reason (the pairs read from `x-ordered-fields`); locked in a scenario, as the site and solver are. "Manufacturer data (optional)" in the pump curve form. Results → Checks after Summary (not met, met, not evaluated; element links; the server's message under Details) and a Summary card; checks never mark the Results tab. On the pump chart, behind a "Design checks" chip, the limits only (the preferred and allowable regions shaded, the minimum flow, the NPSHa required, the motor's rating), each in a note. An export sheet after Flags. *(GOALS §4.7.)*

### Proof

`tests/unit/test_design_checks.py` (each boundary against the solve's own values, the presets, the methods section, the endpoint); the corpus comparison against `1c1e3a8` (5,151 identical, `--ignore-empty designChecks`); `tests/differential/design_checks_check.py`, every corpus project solved with and without every check on, the solved states equal but for the checks, every result re-derived by a second implementation (5,151 projects, 0 different; every check passes and fails somewhere; TSD §10.4 has the counts); the web's wording, chart and export tests on the real API's results of the export fixture's `design-checks` case; the `design-checks` e2e flows on desktop and phone.
