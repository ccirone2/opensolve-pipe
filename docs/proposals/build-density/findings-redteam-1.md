> Discipline findings for [`../build-density.md`](../build-density.md), written 2026-10-30 against the running app before the build (`5693197`). Paths under `/tmp/claude-0/` are the reviewer's scratch evidence, not kept. The proposal's §4 says what was adopted.

# Red team 1: Build density draft (3 personas)

Shots: `/tmp/claude-0/scratch/findings/shots/redteam-*.png`. Scripts: `/tmp/claude-0/-home-user-opensolve-pipe/237c8a8c-ec22-50c7-88e9-bdb1e9d0f236/scratchpad/{p3,a2,a3}.cjs`.
Note: `apps/web/src/lib/utils/field-registry.ts` (untracked) and a `schemaFields` diff in `model-rules.ts` already exist in the working tree. Where an attack below applies to that code, it is cited.

## 1. Field engineer, 390x844, touch (pump-transfer)

Shortest path today: **10 taps and 2 scrolls**. My script did 12 taps because it also ran an optional first solve.
Next: Transfer pump (y 792) → Piping (y 525) → scroll → Size (select + option) → **Solve (y 52)** → **Build tab (y 101)** → Next: Discharge isolation valve (y 792) → scroll **up** → Status (select + option) → **Solve (y 52)**.
- Each Solve on a phone switches to the Results pane (`redteam-p1-resolved1.png`). Every edit-and-solve cycle therefore costs two taps in the top 15 % of the screen (Solve, then Build). The draft keeps Solve in the top header and says nothing about this pane switch, so the target of "≤ 2 actions" cannot be met for edit → solve → edit.
- The scroll position carries over on Next. The valve opened scrolled to its ports (`redteam-p1-valve.png`): Status was at y = −3, above the viewport. "Core fields visible without scrolling" fails on the second component visited unless Next resets the scroll to the top.
- Size is at content y 1044 of a 585 px scroller (`redteam-p1-pump-piping.png`), below the Suction/Discharge port chooser, the connection card and its 4 actions (Go to, Insert, Add branch, Disconnect), and "Pipes". The draft makes inputs shorter but does not move the connection actions, so Size probably stays below the fold.
- Status is a native select: 2 taps to change an open/closed choice. A segmented control would need 1, and so would any choice with no more than 3 values.
- Draft risks for this persona: (a) a 40 px coarse control is still ≥ 24 px, but 4 icon+short-label actions in one row at 390 px leaves a destructive **Delete** about 8 px from Add branch. (b) With the header in one row, Undo/Redo/Solve all sit in the top 60 px, the hardest place to reach with a thumb. (c) The overflow hides the Scenarios count badge (it reads "1" today).

## 2. Correctness auditor (condenser-water, "Winter: tower bypassed" = S1, 19 changes)

| Must stay visible | Where today (selector) | How the draft hides it |
|---|---|---|
| D15, base case: "Winter: tower bypassed sets its own value." | BP Status and Resistance: `p#<id>-change.hint` (ChangeNote.svelte l.33) — `redteam-a-*-BP-base.png` | **It is styled `.hint`**, so it disappears with the draft's "static help only on :focus-within" |
| D15, scenario: "Changed · Base: Closed (isolated) · Reset" | `div.mt-1.flex` after the field; `span#<id>-change.sr-only` | At 390 px it sits at content y 1068, under the result strip plus the ScenarioBanner (≈200 px) (`redteam-a-mobile-BP-scenario-solved.png`: no field at all on screen). Resistance is tier `more` in the registry, and the More panel opens only for a "scenario change", not for a base-case `setBy` |
| D10 valve default "Default: Crane TP-410 K, full bore and fully open, at the connected size" | the **selected `<option>`** of the resistance select (`ResistanceField.svelte` l.88) | The registry puts RESISTANCE in `losses`/`more`. A default value is null, so `isSet()` returns false and the panel stays closed: the default label is hidden. A narrow value column also cuts it to "Default: Crane TP-4…". In a scenario the note reads only "Base: Default" |
| D10 relief preliminary basis (Kd 0.65, ASME 10 %/3 psi) | `p#<id>-preliminary` with class `hint` when it is not a warning (ReliefValveFields l.224) — `redteam-a-RV1.png` | It switches between `.hint` and amber, so it is **hidden whenever it is not a warning** |
| D10 ASME overpressure default | `p#<id>-overpressure` (not `.hint`) + select option `asmeDefaultText` | Safe from the focus rule, but hidden if Capacity's sub-fields ever go to `more` |
| Dynamic notes sent through the `hint` prop | "Velocity at the last solve: 3.981 m/s" (PipeSegmentForm `velocityHint`); "This curve is shared by N pumps" (PumpForm l.219); "The solver uses the connected pipe: NPS 3.5" (PortsEditor l.102); assigned-flow zero note | All of them render as `p#<id>-hint.hint`. **The draft's "dynamic notes stay visible" does not hold: they are the same element as static help** |
| Port-size mismatch warning (amber, `redteam-p1-valve.png`) | in PortsEditor, tier `more` (PORTS) | It is a warning, not an error, so More does not open for it. Also, `isSet` treats any non-empty list as set, and ports are never empty: **More would be "set" and open on every component**, which defeats the density work |
| Result strip extras | `[role=group]` "Last solve": "Out of date: solve again" badge, up to 2 flags + "n more", "did not converge" text, `dt` "(kPa(g))" | "One or two compact lines of label/value pairs" leaves no room for the stale badge, flags or non-converged text. Moving the unit from the `dt` to the value risks dropping "(g)" |
| D4 gauge units | `span.inline-flex.min-h-11` suffix "kPa(g)" (B1 surface pressure); relief set = "kPa" (a difference) | `NumberInput.gauge` is **optional and false by default**: a new pressure entry that omits it shows kPa for a gauge value, and no test catches it |

Tests I would write:
1. A Playwright run on condenser-water with **no field focused** (`page.locator(':focus')` is body). In the base case, at BP, expect both `getByText('Winter: tower bypassed sets its own value.')` toBeVisible. Switch Case to S1 and expect 2 × `getByText('Changed', {exact:true})` and `getByRole('button',{name:/^Reset Status/})` toBeVisible, inside the scroller viewport after one scroll at most.
2. A Vitest invariant: no element whose text comes from ChangeNote, a warning, `velocityHint`, a shared-curve note, a port mismatch or a preliminary/default line carries the help class. Split the `hint` prop into `help` (static, focus-only) and `note` (dynamic, always shown), and make the type checker reject a `$derived` in `help`.
3. Any `<details>` closes only if it contains no `[data-note]` (setBy, warning, a default label). A test opens V1 of `all` and asserts the resistance control's visible text matches `/^Default: Crane TP-410/`, measured at a 320 px width with `scrollWidth <= clientWidth`.
4. A registry test: every `input.category === 'pressure'` entry declares `gauge` explicitly (make it required). Cross-check against the schema description ("gauge"). Every `elementSummary` pressure item has unit `*(g)`, `psig` or is a difference.
5. A strip test: after an edit, "Out of date" toBeVisible; with flags, the flag text is visible, not truncated by the compact layout.

## 3. Next feature author

Roadmap §2 candidates that add fields: relief valve **API 520 Kw/Kv/Kc** (fields under `capacity`), and equipment **"K on a stated diameter", head or mass-flow rating, ΔP curve** (new `rating` union members).
Files touched today to add one relief-valve capacity field (traced via `overpressure`/`dischargeCoefficient`):
- `components/panel/ReliefValveFields.svelte` (input, hint, change note, `groupNoted`, `described`)
- `forms/ReliefValveForm.svelte`
- `utils/relief.ts` (`CAPACITY_FIELD_LABELS`, default text)
- `utils/factory.ts` (`CapacityField`, the per-kind field list, normalising)
- `utils/scenarios.ts` (its own label `switch`, l.1205–1218; value text, l.1448)
- `utils/goal-seek.ts` (labels l.712, allow-list l.827, bounds l.1482)
- `utils/export/tables.ts` (column, override text l.1278, capacity words l.1314)
- `utils/results.ts` + `results/ResultsPanel.svelte`
- `utils/issue-text.ts` (error remedies)
- `testing/results.ts`, plus tests

That is **≈10 files with 4 independent label sources**.

The registry as drafted does not reach "one entry plus a label". Capacity, rating, resistance, ports and flow are `whole: true`, and `unregisteredFields()` skips everything under a `whole` entry. A new `capacity.backpressureCorrection` or equipment rating member therefore **passes the guard with no input drawn**, exactly where the roadmap's next fields land.

For one entry plus a label, the registry must guarantee:
- (a) It is the only label source: scenarios.ts `changeFieldLabel`, goal-seek, export and issue-text read `labelOf()`, and none falls back to `humanize()`.
- (b) The guard covers union members under `whole` entries: each must be listed as drawn by a named editor (`drawnBy: 'ReliefValveFields'`), and that editor's test enumerates the paths it draws.
- (c) Every `x-override-fields` / `x-goal-variables` path has an entry, with a test.
- (d) Change notes, error placement (`errorOf(path)`) and D10 default text come from the entry's path automatically for `input`-drawn fields.
- (e) `gauge` is required for pressure.
- (f) A field with a schema default shows its "Default: …" label without being "set", and the More count shows "n set · m default".
