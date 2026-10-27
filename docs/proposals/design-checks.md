# Design checks: design proposal

**Status: built** (2026-10-27), as slice 3 of `docs/proposals/pump-chart.md` widened to PRD §5's opt-in check library; §7 records where the build departs from this text. **Owner's answers (2026-10-27):** a check framework with three first checks (NPSH margin, the pump's operating region, pipe velocity), not a pump-only feature; every limit is a user value, and presets fill one in only where a source is cited, labelled "as quoted by …" where the standard itself was not read; optional manufacturer data on the pump curve (allowable operating region, minimum continuous stable flow, minimum thermal flow, motor rated power). This lifts "design checks" out of D5's Deferred list (CLAUDE.md D19).

Sources: PRD §5 (design checks: not active by default, toggled one by one, violations reported on solve), SDD §9.3, GOALS §4.1 (cited data only), §4.6 (physics flagged by default, design practice opt-in), the pump chart proposal's research brief (§§1, 5 and its sources), CLAUDE.md D10, D13, D14, D18 (precedents for additive outputs and `--ignore-empty`).

## 1. Principles

1. **Off by default, per project.** A project without design checks solves, links and dumps exactly as before. The checks a user turns on travel with the project (its link), since the limits are part of the design being checked.
2. **Checks are not flags.** Flags are physics (GOALS §4.6). A check result says whether a value meets a limit the user chose; it never changes a solved value, a status or a flag, and a check that fails never blocks or degrades a solve.
3. **No uncited limit.** Every limit is user data. A preset only writes a value into a field, labelled with its source; where the standard itself was not read the label says "as quoted by" the secondary source (GOALS §4.1). Velocity limits have no preset in this slice: no source read gives one that suits every fluid and application.
4. **Traceable.** Each result names the check, the element, the value checked, the limit, its source (user or the preset's citation) and the inequality that set the outcome; a methods-summary section lists the checks that ran.
5. **Computed by the API** from the solved state, after the solve, so the screen, the export and any API user see one answer.

## 2. Model

`ProjectSettings.designChecks` (optional; omitted when none is on):

```
DesignChecks {
  npshMargin?:      { minimumMargin?: m in [0, 100]; minimumRatio?: [1, 10]; source: CheckSource }
  operatingRegion?: { preferredMin?: (0, 5]; preferredMax?: (0, 5], above preferredMin; source: CheckSource }
  pipeVelocity?:    { minimum?: m/s in [0, 100]; maximum?: m/s in (0, 100], above minimum; source: CheckSource }
}
CheckSource = { kind: 'user' } | { kind: 'preset'; preset: PresetId }
```

A check is on when its object is present; a check with no limit set is listed as not evaluated ("no limit set"). The ordered pairs are model rules (400), published as `x-ordered-fields`. Presets (published as `x-design-check-presets` on `DesignChecks`, with their values and citations, which the web reads):

| Preset | Writes | Citation, as labelled |
|---|---|---|
| `api610_por` | operating region 0.70–1.20 of BEP flow | API 610 (10th/11th ed.) 5.1.14 "preferred operating region of 70 % to 120 % of best efficiency flowrate", as quoted by Datacor, "Are you operating your pump off BEP?" (the standard itself was not read) |
| `hi961_2012_general` | NPSH margin ratio 1.1, margin 1.0 m (the greater applies) | ANSI/HI 9.6.1-2012, "General" application, as reproduced by Michael Smith Engineers, "NPSH" (the standard itself was not read; the 2024 edition's tables may differ) |

`PumpCurve` gains optional manufacturer data, user values at rated speed:

```
allowableOperatingRegion?: { flowMin: m³/s ≥ 0; flowMax: m³/s > flowMin }   // x-ordered-fields
minimumContinuousStableFlow?: m³/s > 0
minimumThermalFlow?: m³/s > 0
motorRatedPower?: W in (0, 10⁸]
```

The solve reads none of them. `schemaVersion` stays 1 (D14, additive).

## 3. Checks

Run for every element with the values needed; an element without them is listed as **not evaluated** with the reason (no limit set, no NPSHr curve, no NPSHa, no best efficiency point and why, no shaft power, the pump off or held at zero flow).

| Check id | Element | Passes when | Notes |
|---|---|---|---|
| `npsh_margin` | each pump with a result | NPSHa ≥ max(NPSHr + margin, ratio × NPSHr) for the limits set | The physics flag (NPSHa < NPSHr) is unchanged and separate. |
| `operating_region` | each pump with a result | preferredMin ≤ Q/Q_BEP ≤ preferredMax for the limits set, Q_BEP at the running speed | BEP flow scales with speed by the affinity laws, as the pump chart's BEP (`PumpResult.bestEfficiencyPoint`); the message says so. |
| `allowable_region` | each running pump whose curve has an AOR | flowMin ≤ Q/s ≤ flowMax | Rated-speed equivalent flow (affinity); with the operating-region check. |
| `minimum_flow` | each running pump whose curve has an MCSF and/or minimum thermal flow | Q/s ≥ the larger | Likewise; the message names which. |
| `motor_power` | each running pump whose curve has a motor rating | P_shaft ≤ motorRatedPower | With the operating-region check (the pump's selection check); no service-factor margin (no cited value). Not evaluated without a shaft power. |
| `pipe_velocity` | each connection with a link result | minimum ≤ \|v\| ≤ maximum in every pipe, for the limits set | One result per connection: the value is the fastest pipe's above a maximum, else the slowest's below a minimum, else the fastest's (the slowest's with a minimum only). |

## 4. Results

`SolvedState.designChecks: DesignCheckResult[]` (always present; empty without checks): `{check, componentId | null, connectionId | null, outcome: 'pass' | 'fail' | 'not_evaluated', value | null, pipeIndex | null, pipesOutside: int[], limits: {min | null, max | null}, unit, source, message}`, all SI, pipe indexes 0-based (the message numbers pipes from 1, D10). Pumps in component order (each pump's checks in the table's order), then connections in project order. A solve that did not converge has none. `source` is "user", "manufacturer data (user)" or the preset's citation. The methods summary gains a "Design checks" section, last (each check, its limits, and the presets' citations as references) only when a check is on.

## 5. Web

- **Settings → Design checks:** a section with a switch per check, its limit fields in display units, preset buttons that fill the fields and label them with their source; a limit typed by hand makes the source "user"; a pair out of order is refused with the reason at its field. In a scenario the section is locked, as the site and solver settings are: the checks are the same in every case.
- **Pump curve form:** a "Manufacturer data (optional)" disclosure with the four fields (the allowable region's two ends kept on the page until both are entered).
- **Results → Checks:** a view after Summary, shown only when the solve has checks: not met, then met, then not evaluated, each naming its element (a link to its results and trace), its value against its limits in display units (more digits where a rounded value would read as its limit), its limits' source, and the server's message under Details. The Results tab's marker is unchanged (checks are not flags). The Summary shows a "Design checks" card: the counts, the first three not met, and a link to the view.
- **Pump chart,** behind a "Design checks" chip when a check draws on the pump: the limits, never the verdicts. The preferred region shaded on the head panel (from Q_BEP at the running speed), the allowable region shaded in grey and the minimum flow as a dash-dot line (manufacturer data drawn at s × flow), the NPSHa the NPSH margin check requires as a dotted line on the NPSH panel, the motor's rating as a dashed line on the power panel; each told in a note under the chart and in the image's footer, with its values and source.
- **Export:** a "Design checks" sheet after Flags when a case has check results (D17's tables rule), one row per result in the screen's order, each value and limit in its row's Unit, the screen's words, the server's message and source as reported; an About line only in a file that has it.

## 6. Proof

API: unit tests of every check's pass/fail/not-evaluated boundary in closed form, against the solve's own values (`tests/unit/test_design_checks.py`); the presets' published values and citations; the corpus comparison against `main` with `--ignore-empty designChecks` (no project in the corpus has checks); and `tests/differential/design_checks_check.py`, which solves every corpus project with and without every check on (pump curves given manufacturer data, and efficiency and NPSHr curves where they have none, as test inputs), requires the two solved states to be equal but for the checks and their methods section, and re-derives every result from the solved state's JSON by a second implementation of §3's rules. Web: unit tests of the wording, the chart overlays and the export sheet on the real API's results of a shared fixture case (`design-checks`, from `tests/fixtures/export_input.py`); component tests of the settings section, the curve form's fields, the Checks view and the Summary card; an e2e flow on desktop and phone; axe.

## 7. As built (2026-10-27)

- **All limits optional.** §2 first required both ends of the operating region; as built every limit is optional (a one-sided band is common, e.g. a maximum velocity only), and a check with none is not evaluated, so the switch can be turned on before its limits are typed.
- **Pipe data on the result.** `pipeIndex` and `pipesOutside` were added so that the web words a velocity result in display units from data, never by parsing the message (D10).
- **Pump checks of a pump not running** are not evaluated, without limits (its manufacturer-data checks are not listed): there is no duty to judge.
- **The chart draws limits from the project as solved** (`ProjectStore.solvedProject`), not from the results: the NPSH requirement is a line along NPSHr, which a result at the duty cannot give. Neither the checks nor the pump library are scenario values, so the base project sent is every case's.
- **The export's Pipes outside #** lists every pipe outside the limits, one too; the words name a single pipe only once.
- **Corpus tool coverage.** Few corpus pumps have an efficiency or NPSHr curve, so `design_checks_check` gives each pump curve without one a test-input curve in both solves (neither changes a flow or a head); the counts per check and outcome are TSD §10.4's.
