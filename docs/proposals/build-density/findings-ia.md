> Discipline findings for [`../build-density.md`](../build-density.md), written 2026-10-30 against the running app before the build (`5693197`). Paths under `/tmp/claude-0/` are the reviewer's scratch evidence, not kept. The proposal's §4 says what was adopted.

# Build panel: card sort of input fields (IA)

Sources: `apps/web/src/lib/api/openapi.json` (components.schemas, `x-override-fields` on Scenario), the three
examples in `apps/web/src/lib/utils/examples.ts` (evaluated: 84 components, 186 ports, 98 pipes, 54 fittings,
2 pump curves, 1 scenario with 19 overrides), PRD Appendix B (US-001..004), `docs/decisions/D*.md`, the forms in
`apps/web/src/lib/components/panel/`. Read-only; nothing in the repo was changed.

Frequency = how many example items hold a value other than the schema/web default (or "req" when the field is
required and has no default). "Case" = field is in the scenario allow-list (`x-override-fields`, D15): the value
can differ per case. Web default = the value `utils/factory.ts` writes for a new component when the schema has
none.

Examples cover: reservoir 12, tee 24, pump 7, isolation valve 15 (gate 1, globe 1, butterfly 13), check valve 6,
control valve (FCV) 7, equipment 13. **No** reference node, plug, assigned flow, wye, orifice or relief valve
appears in any example, and no port elevation, wye angle, pump control, K entered on a fitting or pipe override.
Frequency for those is judged from the PRD, the decisions and the factory/creation flow, and marked "n/a".

---

## 1. Facets (in this order, on every type)

| # | Facet (heading an engineer scans for) | What goes in it | Test for membership |
|---|---|---|---|
| 1 | **Operation** | status, control mode, setpoints, speed; boundary conditions: liquid level, surface pressure, fixed pressure, assigned flow | Something an operator or a case changes on the same installed plant. 18 of the example scenario's 19 overrides are `status`; the allow-list (`x-override-fields`) holds every field in this facet except `control.minSpeed`. |
| 2 | **Rating** | what the item does to flow, from its datasheet, nameplate or a cited standard: pump curve (+ efficiency, NPSHr, manufacturer limits), valve resistance (default / K / Cv / Kv / library entry), cracking pressure, equipment rating, orifice bore and C, relief set pressure and capacity, tee/wye loss model, pipe material / schedule / spec and its ID/roughness overrides | Fixed when the item is bought; changing it means a different item (or a fouled one). Every library reference lives **here, as one option of the field's source picker**, not in a facet of its own. |
| 3 | **Size and position** | component elevation, ports (size, elevation), wye branch angle, orifice pressure taps, pipe nominal size and length | Where it sits and how big it is; mostly inherited when the item is added at a port (`state/workspace.svelte.ts` ~l.736: `elevation: port.elevation ?? existing.elevation`), so rarely edited after creation. None of these is in the allow-list except pipe size/length (`PipeDefinition.spec`, `length`). |
| 4 | **Fittings** (Piping tab only) | the fitting list of a connection: type, quantity, position, K source, entered K, angle, r/D | Minor losses added to a pipe run. Only `PipingSegment` has them; a component never does. |
| 5 | **Identification** | component name (header, not a form field), pump curve name, manufacturer, model, fitting description | Words that name the item; never change a result. |

Order rationale: **Operation first** because status is the most-edited field (scenario data above) and the
setpoint is what an engineer reads against the result strip; it is also short scalars, so it fits above the fold
on a phone. **Rating second**: the defining datasheet input, required at creation for pump, equipment, orifice and
relief valve (`NewComponentFields.svelte`), often a table or a picker with a pending kind, so it is better below
the short scalars. The current forms already put Operation before Rating in every type (valve type → status →
setpoint/cracking → resistance; pump status → control → speed → curve; relief status → set → capacity), so the
facet order needs no reorder there; only **elevation moves** from first (ComponentPanel renders it before every
form) to Size and position. **Fittings** stay on Piping. **Identification last**.

Not a facet:
- **References** (library entries). Each reference is one choice of the same decision as the value it replaces:
  the Material select already lists pipe specs (`PipeSegmentForm` SPEC_PREFIX group), "Resistance given as" lists
  K/Cv/Kv and the resistance entries, the fitting's loss-coefficient select lists cited / entered / entries, and the
  pump curve select is the pump library. `x-reference-fields` says exactly this (`specId` *replaces*
  materialId, schedule, nominalSize, innerDiameter, roughness; `resistanceId` replaces `kOverride`). A separate
  References section would split one decision over two places.
- **Losses** as a component facet: a component's loss law is its rating (valve resistance, equipment rating,
  orifice C, tee loss model). "Losses" survives only as the Fittings list on a connection.

Facet use by type (core fields / more fields):

| Type | Operation | Rating | Size and position | Identification |
|---|---|---|---|---|
| Reservoir | liquid level / surface pressure | – | elevation / ports | – |
| Reference node | pressure | – | elevation / port | – |
| Plug | – | – | elevation / port | – |
| Assigned flow | direction + flow | – | elevation / port | – |
| Tee | – | – / loss model | elevation / ports | – |
| Wye | – | – / loss model | elevation, branch angle / ports | – |
| Pump | status, control, setpoint, min speed, speed | curve (select + head table), NPSHr / efficiency, manufacturer limits | elevation / ports | – / curve name, manufacturer, model |
| Isolation valve | status | resistance | elevation / ports | – |
| Check valve | status | resistance / cracking pressure | elevation / ports | – |
| Control valve | status, setpoint | resistance | elevation / ports | – |
| Equipment | – | rating (kind + values) | elevation / ports | – |
| Orifice | – | bore / discharge coefficient | elevation / taps, ports | – |
| Relief valve | status | set pressure, capacity (kind + values) / overpressure | elevation / ports | – |
| Pipe (Piping tab) | – | material or spec, schedule / ID and roughness overrides | size, length | – |
| Fitting (Piping tab) | – | – | – | – / description; Fittings facet: type, quantity / position, K source, K; angle, r/D when the type needs them |

Every type except Plug and Equipment has something in Operation, and every one has Size and position, so a new type
fits by giving each field a facet; nothing needs a type-specific section. (Plug: its only field is elevation.)

---

## 2. Field table

Tier: **core** = visible; **more** = in a closed disclosure of its facet. "cond." = shown only when a sibling
value makes it apply (that is visibility, not tier; it follows the schema's `x-required-parameters`,
`x-fields-by-value`, the union kind or `control`). No field changes tier with another field's value, except that
a custom pipe's ID/roughness and a custom fitting's K become required (core) — the registry needs a "required
when" rule from those extensions, not a second tier. Pump.speed is core in both modes (see its reason).

### Components

| Schema | Field path | Facet | Tier | Default | Decision | Frequency (examples) | Case | Reason |
|---|---|---|---|---|---|---|---|---|
| Reservoir | `liquidLevel` | Operation | core | req (web 0) | D1, D12 (fixed-pressure boundary) | 6/12 ≠ 0 | Y | Sets the boundary head with the elevation; the reservoir's main input. |
| Reservoir | `surfacePressure` | Operation | more | 0 (open) | D4 (gauge) | 0/12 | Y | Closed, pressurised tanks are the exception; "0 = open to atmosphere" is the right default. Summary should read "open to atmosphere" or the value. Borderline: a closed-loop expansion tank (PRD §61) sets it; it then shows "· 1 set". |
| Reservoir | `elevation` | Size and position | core | req (web 0) | D4 (datum), D7 | 9/12 ≠ 0 | – | With liquid level gives the head; place it **adjacent to liquid level** (Operation is the facet just above, so it is). |
| IdealReferenceNode | `pressure` | Operation | core | req (web 0) | D1, D12, D4 (gauge) | n/a (0 examples; created by "Discharge to atmosphere" at 0, D23) | Y | Its only input. |
| IdealReferenceNode | `elevation` | Size and position | core | req (web 0, or the outlet's) | D4 | n/a | – | Pressure is held at this elevation; meaningless without it. |
| Plug | `elevation` | Size and position | core | req (web 0) | D4 | n/a | – | Only field; reported pressure at the closed end depends on it. |
| AssignedFlow | `flow` (UI: Direction + Flow) | Operation | core | req (asked at creation) | D12 | n/a (0 examples) | Y | Its only input; the sign is split into a Direction select (demand/supply) and a magnitude. |
| AssignedFlow | `elevation` | Size and position | core | req (web 0) | D4, D12 | n/a | – | Port pressure (a result) is at this elevation. |
| TeeBranch | `lossModel` | Rating | more | crane | D9 | 0/24 | – | `ideal` is for EPANET comparison only (its hint says so); 24 of 24 tees keep Crane. |
| TeeBranch | `elevation` | Size and position | core | req (web: inherited) | D4 | 24/24 ≠ 0 | – | See "Elevation of inline items" below. |
| WyeBranch | `lossModel` | Rating | more | crane | D9 | n/a | – | As tee. |
| WyeBranch | `angle` | Size and position | core | 45 | D9 (Crane 30–60°) | n/a (0 wyes) | – | Borderline: the default is fine for a 45° lateral, but the angle is what identifies the fitting bought (45° vs 60° lateral) and it is the wye's only geometric input; one row. |
| WyeBranch | `elevation` | Size and position | core | req | D4 | n/a | – | As tee. |
| Pump | `status` | Operation | core | on | D9 (EPANET 2.2 status) | 0/7 in base; 5/7 overridden in the scenario | Y | The most-changed field across cases. |
| Pump | `control` (UI "Control": fixed / flow) | Operation | core | null = fixed speed | D11 | 0/7 | – (whole control not allowed; `control.setpoint` is) | Defines how the pump runs; one select row. |
| Pump | `control.setpoint` | Operation | core, cond. (flow control) | req in control | D11 | n/a | Y | The target the drive holds. |
| Pump | `control.minSpeed` | Operation | core, cond. (flow control) | req in control (no standard default) | D11 | n/a | N | No default exists ("there is no standard default"), so it cannot be hidden while control is on. |
| Pump | `speed` (UI "Speed" / "Maximum speed") | Operation | core | 1.0 | D9 (affinity), D11 (maximum), D16 (goal-seek variable) | 0/7 | Y | Borderline (0/7 changed). Kept core: a speed ≠ 100 % rescales every pump result, so it must be readable next to the result strip without opening anything, and it is the drive's upper bound under control. One row with the "default" label (D10). |
| Pump | `curveId` (UI "Pump curve" select, the pump library) | Rating | core | req | D9 (PCHIP) | 7/7 (req) | N | Defining input; the select is also the library reference (not a References facet). |
| Pump | `elevation` | Size and position | core | req | D4; NPSHa (D9, `npsh.py`) | 6/7 ≠ 0 | – | Enters NPSHa (z_s); kept core though placed after the curve. |
| IsolationValve | `status` | Operation | core | active (Open) | D9 | 1/15 base (BP isolated); 7 overridden in the scenario | Y | Second most-changed field across cases. |
| IsolationValve | `resistance` (kind default/K/Cv/Kv/library; `.value`; `.id`) | Rating | core (the "Resistance given as" select); `.value` cond. | null = Crane TP-410 K at the connected size | D9, D8, D22 | 6/15 (all library RS1); 1 scenario override (K 16.5) | Y | Borderline (21 % of valves set it). Core because it is every valve's only Rating field, and the one-line select shows the source of the loss ("Default: Crane TP-410 K…", D10). The number input appears only for K/Cv/Kv. |
| IsolationValve | `elevation` | Size and position | core | req | D4 | 14/15 ≠ 0 | – | See below. |
| CheckValve | `status` | Operation | core | active (Automatic) | D9 | 0/6 | Y | Borderline (0/6). Core so that Status sits in the same place on every valve (scan by position), and a locked valve is the first thing to check when a result shows zero flow. |
| CheckValve | `crackingPressure` | Rating | more | 0 | D9 (SDD §4 check rule) | 0/6 | N | 0 opens on any forward flow; the 330-character hint goes with it. |
| CheckValve | `resistance` | Rating | core | null = cited loss | D9, D22 | 0/6 | Y | As isolation valve. |
| CheckValve | `elevation` | Size and position | core | req | D4 | 6/6 ≠ 0 | – | See below. |
| ControlValve | `status` | Operation | core | active | D9 | 0/7 base; 6/7 overridden | Y | As isolation valve. |
| ControlValve | `setpoint` (UI Flow / Outlet pressure / Inlet pressure setpoint) | Operation | core | req (web 0, warned) | D9 (EPANET PRV/PSV/FCV), D4 (gauge for PRV/PSV), `x-setpoint-bounds` | 7/7 | Y | The control valve's defining value. |
| ControlValve | `resistance` | Rating | core | null = ideal (no loss open) | D9, D22 | 0/7 | Y | As isolation valve (same row on every valve). |
| ControlValve | `elevation` | Size and position | core | req | D4 (the setpoint is a static pressure at this elevation) | 7/7 ≠ 0 | – | A PRV/PSV holds a static pressure, which depends on it. |
| Equipment | `rating.kind` (UI "Rated by") | Rating | core | req (asked at creation) | D18 | 13/13 point | Y (`rating`) | Defining. |
| Equipment / RatedPoint | `rating.pressureLoss` | Rating | core, cond. (point) | req | D18 | 13/13 | Y | Datasheet value, no default. |
| Equipment / RatedPoint | `rating.flow` | Rating | core, cond. (point) | req | D18 | 13/13 | Y | Datasheet value, no default. |
| Equipment / RatedPoint | `rating.density` | Rating | core, cond. (point) | req | D18 | 13/13 (995.8) | Y | No default (a strainer chart's water vs an exchanger's stated fluid), so it cannot be hidden. |
| Equipment / RatedFlowCoefficient | `rating.value` (Cv / Kv) | Rating | core, cond. (Cv/Kv) | req | D18 | 0/13 | Y | Datasheet value. |
| Equipment | `elevation` | Size and position | core | req | D4, D18 (static-drop identity) | 13/13 ≠ 0 | – | See below. |
| Orifice | `boreDiameter` | Rating | core | req (asked at creation) | D20 | n/a (0 orifices) | Y | "The one value a plate cannot be added without". |
| Orifice | `dischargeCoefficient` (UI ISO / Entered C) | Rating | more | null = ISO 5167-2 (RHG) | D20 | n/a | Y | ISO's C is the cited default; an entered C comes from a calibration. Summary must show "ISO 5167-2 (default)" (D10). |
| Orifice | `taps` | Size and position | more | null = no taps (restriction orifice) | D20 | n/a | N (locked: installation) | Borderline: needed only for a flow meter's reading; changes no network result (the loss uses D and D/2 taps whatever the taps). Summary "No taps" / "Flange taps". |
| Orifice | `elevation` | Size and position | core | req | D4, D20 (p_vc uses z) | n/a | – | See below. |
| ReliefValve | `status` | Operation | core | active | D23 | n/a | Y | As other valves; "locked closed" is the scenario's "no relief" case. |
| ReliefValve | `setPressure` | Rating | core | req (asked at creation) | D23 | n/a | Y | Nameplate value, no default. |
| ReliefValve | `capacity.kind` (UI "Capacity given by") | Rating | core | req (asked at creation) | D23 | n/a | Y (`capacity`) | Defining. |
| ReliefValve / Api526Orifice | `capacity.letter` | Rating | core, cond. (api526) | req | D23, `x-relief-data` | n/a | Y | No default. |
| ReliefValve / Effective, Certified | `capacity.area` | Rating | core, cond. | req | D23 | n/a | Y | No default. |
| ReliefValve / CertifiedOrifice | `capacity.dischargeCoefficient` | Rating | core, cond. (certified) | req | D23 | n/a | Y | No default. |
| ReliefValve / CertifiedOrifice | `capacity.overpressure` | Rating | more, cond. (certified) | null = ASME (10 %, 3 psi floor) | D23 | n/a | Y | Cited default is right unless the certification states another; summary "ASME default". |
| ReliefValve | `elevation` | Size and position | core | req | D4, D23 ("Discharge to atmosphere" at the outlet's elevation) | n/a | – | See below. |

### Ports (every component; `PortsEditor.svelte`)

| Schema | Field path | Facet | Tier | Default | Decision | Frequency | Case | Reason |
|---|---|---|---|---|---|---|---|---|
| Port | `ports[].nominalSize` (UI "Port size (NPS)") | Size and position | more | req (web: the size of the port it was added at) | D2, D22 | 186/186 req; sizes mirror the pipes | N | Its own hint: "Default size for new piping here … the solver uses the connected pipe." It changes no result once connected. The **mismatch warning** (and its "Make the pipe NPS x" button) is a dynamic note and stays visible; the port card's "Connected to … / Edit piping / Connect…" line is navigation and stays core. |
| Port | `ports[].elevation` (UI "Port elevation") | Size and position | more | null = component's elevation | D18, D20, D23 (static-drop identity, nozzles at different heights) | 0/186 | N | Rare (0 in examples); only nozzle-height cases need it. Today shown only on reservoirs or when already set (see inconsistency 12). |
| Port | `ports[].direction` | – | not shown | bidirectional | D2, `x-port-roles` | fixed by type | N | Structural: set by the type's `x-port-roles`, no UI. Listed for completeness only. |

### Pump curve (`PumpCurveEditor.svelte`, `pumpLibrary`)

| Schema | Field path | Facet | Tier | Default | Decision | Frequency (2 curves) | Case | Reason |
|---|---|---|---|---|---|---|---|---|
| PumpCurve | `points[].flow`, `points[].head` | Rating | core | req (≥ 3 points) | D9 (PCHIP), D8 (user data) | 2/2 (4 and 6 points) | N | Defines the pump (US-001, US-002). |
| PumpCurve | `npshrCurve[].flow`, `.npshr` | Rating | core (collapsed table with count when set; "Add NPSHr curve" when not) | null | D9, `npsh.py` (CAVITATION invalid, NPSH_NOT_CHECKED warning) | 2/2 | N | Borderline. Its absence raises NPSH_NOT_CHECKED on every pump and its presence drives the CAVITATION physics flag (GOALS §4.6), so the engineer must see whether it is there. Show the table's presence and point count in the core row; the rows themselves may collapse. |
| PumpCurve | `efficiencyCurve[].flow`, `.efficiency` | Rating | more | null | D9 (power), D19 (preferred region), D21 | 2/2 | N | No flag depends on it; it adds power and BEP. 2/2 examples set it, so the disclosure summary must show "· 3 points" rather than auto-opening (see note on auto-open). |
| PumpCurve | `allowableOperatingRegion.flowMin` / `.flowMax` | Rating | more | null | D19 (opt-in checks) | 0/2 | N | Read only by opt-in design checks. Already in "Manufacturer data (optional)". |
| PumpCurve | `minimumContinuousStableFlow` | Rating | more | null | D19 | 0/2 | N | As above. |
| PumpCurve | `minimumThermalFlow` | Rating | more | null | D19 | 0/2 | N | As above. |
| PumpCurve | `motorRatedPower` | Rating | more | null | D19 | 0/2 | N | As above. |
| PumpCurve | `name` (UI "Curve name") | Identification | more (core while creating a curve: required) | req | – | 2/2 req | N | The curve select already shows it; edit it in the disclosure. |
| PumpCurve | `manufacturer` | Identification | more | null | D19 (cited in check sources) | 0/2 | N | Never changes a result. |
| PumpCurve | `model` | Identification | more | null | – | 0/2 | N | As above. |

### Pipes and fittings (Piping tab: `PipeSegmentForm.svelte`, `FittingsEditor.svelte`)

| Schema | Field path | Facet | Tier | Default | Decision | Frequency | Case | Reason |
|---|---|---|---|---|---|---|---|---|
| PipeDefinition | `materialId` / `specId` (one "Material" select, specs grouped) | Rating | core | materialId req without specId (`x-reference-fields`) | D8 (cited pipe data), D22 (spec) | 73/98 material (all carbon steel), 25/98 spec PS1 (condenser only) | Y (`spec`) | Defines ID and roughness. The spec is one option of this select: not a separate References section. |
| PipeDefinition | `schedule` | Rating | core, cond. (library material) | null | D8 | 73/98 (40 or STD) | Y (`spec`) | Required to look up the ID. |
| PipeDefinition | `nominalSize` (UI "Size (NPS)") | Size and position | core | null (req for a library material) | D8, D22 | 73/98 | Y (`spec`) | US-004 "compare pipe sizes": the most important pipe edit. Today at content y 1199 on a phone (sketch); must be in the first screen of Piping. |
| PipeDefinition | `length` | Size and position | core | req | D1 | 98/98 | Y | Required, always set. |
| PipeDefinition | `innerDiameter` | Rating | more ("Overrides"); core, cond., for material `custom` | null = from the library | D8, D22, `x-fields-by-value` on PipeSpec | 0/98 | Y (`spec`) | Override of cited data; required (so core) only for a custom pipe. |
| PipeDefinition | `roughness` | Rating | more ("Overrides"); core, cond., for `custom` | null = from the library | D8 | 0/98 | Y (`spec`) | As inner diameter. |
| Fitting | `fittings[].type` | Fittings | core | req | D8 (one Crane function per fitting) | 54/54 | N | Defines the fitting. |
| Fitting | `fittings[].quantity` | Fittings | core | 1 | D8 | 12/54 ≠ 1 | N | Read with the type ("4 × 90° LR elbow"); one small input. |
| Fitting | `fittings[].pipeIndex` (UI "In pipe" / "Position") | Fittings | more, cond. (> 1 pipe or a reducer) | 0 | SDD §4 (PipingSegment) | 1/54 ≠ 0 | N | 4 of 98 connections have 2 pipes; the reducer's position is between pipes. |
| Fitting | `fittings[].kOverride` / `resistanceId` (UI "Fitting n loss coefficient": cited / entered / library) | Fittings | more | null = cited Crane K (the "K source" line) | D8 (user values labelled), D22 | 0/54 entered, 6/54 library | N | Cited K is the default in 89 %; the "K source: …" line stays visible (D10). Core (cond.) only for `custom`, where `kOverride` is required (`x-required-parameters`). |
| Fitting | `fittings[].angle` | Fittings | core, cond. (bend, reducer_conical) | null | D8, `x-required-parameters` | 4/54 (all conical reducers) | N | Required by the type when shown. |
| Fitting | `fittings[].radiusRatio` (UI "Radius ratio (r/D)") | Fittings | core, cond. (bend, entrance_rounded) | null | D8, `x-required-parameters` | 0/54 | N | Required by the type when shown. |
| Fitting | `fittings[].description` | Identification | more | null | – | 0/54 | N | **In the schema but no form edits it** (see inconsistency 13). |

### Elevation of inline items (the sketch's open question 7)

Data: elevation is non-zero in **79 of 84** example components: inline valves 27/28, equipment 13/13, tees 24/24,
pumps 6/7, reservoirs 9/12 (the condenser plant sits at 0.5, 5, 10 and 11 m). So "more for inline valves and
fittings" is **not supported**: the value is set almost everywhere, and a `more` section that opens itself when
it holds a set value (sketch §5) would be open on 94 % of components, so the disclosure would save nothing and
the rule would read as noise. It is, however, rarely *edited*: a component added at a port starts at that port's
elevation (`workspace.svelte.ts`), so the engineer reads it far more than they type it. Call: **core on every
type, last field before Ports, in Size and position** (moved down from first). It matters to results on every type
(the static pressure at every port is EGL − z − v²/2g; a PRV/PSV setpoint is a static pressure at this elevation;
NPSHa uses it; the vena contracta and relief "Discharge to atmosphere" use it).

### Tier totals

Counting each row above once (conditional rows included, `direction` excluded): 74 rows, core 52, more 22. Per type the
visible core set at creation is at most 5 scalar rows plus one picker or table (pump: status, control, speed,
curve select + head table, NPSHr row, elevation).

### Note on auto-open of `more` sections

Sketch §5 opens a `more` section when it "holds a set value". That works for scalars. For point tables
(efficiency, NPSHr) and for groups whose values are set in most projects (efficiency 2/2), opening on "set"
defeats the disclosure; show the count in the summary ("Efficiency curve · 3 points") and open only on an error
or a scenario change. Likewise a summary for every `more` group should state the default it holds in words
("Open to atmosphere", "ISO 5167-2 C (default)", "ASME overpressure (default)", "Cited K"), which also keeps D10's
"default" label visible while closed.

---

## 3. Sibling-form inconsistencies

Naming

1. **"K" means two different things.** Valve resistance and fittings: "K (loss coefficient)", "K", "K override"
   (`utils/flow-coefficient.ts`, `FittingsEditor.svelte`). Relief valve: "Rated coefficient of discharge (K)"
   (`utils/relief.ts` CAPACITY_FIELD_LABELS), a discharge coefficient. Same symbol in one panel, opposite physics.
2. **`dischargeCoefficient` has two labels** for the same schema name: orifice "Discharge coefficient" / "Entered C";
   relief "Rated coefficient of discharge (K)".
3. **The source picker has five labels and five wordings for "default"**: valves "Resistance given as" with
   "Default: <what>"; equipment "Rated by"; relief "Capacity given by"; orifice a hidden-label select under a legend
   "Discharge coefficient" with "ISO 5167-2 (Reader-Harris/Gallagher), the default"; fitting "Fitting n loss
   coefficient" with "Cited K of this fitting type" / "K entered here"; port elevation placeholder "Same as the
   component"; certified overpressure "ASME's default …". One pattern ("<Quantity> from: Default (<source>) / Entered
   / Library entry …") would let the registry describe all of them with one input spec.
4. **Pressure differences are labelled inconsistently.** Relief "Set pressure (difference)"; check valve "Cracking
   pressure" (also a difference, on the EGL, not marked); equipment "Rated pressure drop" (schema `pressureLoss`,
   D18 says "pressure loss"). All are ungauged differences (D4), only one label says so.
5. **`angle` has two labels for two meanings**: wye "Branch angle" (between branch leg and run), fitting "Angle"
   (bend angle, or the conical reducer's angle).
6. **"Direction"**: assigned flow's Direction (demand / supply, a sign) vs `Port.direction` (inlet / outlet /
   bidirectional, the port role). Fine today because ports' direction is not shown, but a registry keyed on field
   names must not merge them.
7. **Status value "active" reads differently on every type**: isolation "Open", check "Automatic (closes on
   reverse flow)", control "Active (controls to the setpoint)", relief "Active", pump "On". Schema-driven and
   reasonable, but only the relief valve's Status has a hint; isolation and check valve Type selects have no hint
   while the control valve's does.
8. **Size labels**: pipe "Size (NPS)", port "Port size (NPS)", orifice "Bore diameter", custom pipe "Inner diameter"
   vs override "Inner diameter override", "Roughness" vs "Roughness override" (same field, label changes with the
   material). Roughness uses the `diameter` unit category (shown in mm) under the label "Roughness".
9. **Pump curve identity is split**: "Curve name", "Manufacturer" and "Model" sit at the top of the curve editor,
   while "Manufacturer data (optional)" (a disclosure further down) holds the operating limits, not the
   manufacturer. Curve name is rendered in two branches (create l.147, edit l.168).
10. **Accessible names within a fitting row are uneven**: "Fitting n type" and "Fitting n loss coefficient" carry
    the index; "Quantity", "In pipe"/"Position", "K"/"K override", "Angle", "Radius ratio (r/D)" do not (a screen
    reader's form list shows several identical "Quantity" fields).

Order and grouping

11. **Elevation comes first on every type** (ComponentPanel renders it before the per-type form), so on a valve it
    precedes "Valve type", the valve's identity, and on a pump it precedes Status. Everything else already follows
    Operation → Rating.
12. **Port elevation is reachable only on reservoirs** (or a port that already has one, `PortsEditor.svelte`
    l.108), yet the equipment hint says "keep the ports at their real elevations" and the check-valve and relief
    hints reason with port elevations (D18/D20/D23 test them). A user cannot set them on equipment, orifices, valves
    or relief valves from the UI. A `more` Ports section with Port elevation on every type fixes this.
13. **`Fitting.description` is in the schema (≤ 200 chars) but no form edits it**; a registry guard ("schema field
    reachable from Build has no entry") would fail here, so decide: add it under Identification (more), or list it
    as intentionally not editable.
14. **Group containers differ**: Rating / Capacity / Resistance / Discharge coefficient are `<fieldset>` + `<legend>`;
    the pump curve is a `<section aria-label>` with a top border; Ports and Fittings are sections with an `h3`; a
    pipe is an `h4` "Pipe n of m". One facet heading element per facet would make them scan alike.
15. **Three patterns for optional content**: `<details>` "Manufacturer data (optional)" (▸ text glyph, slate text,
    `PumpCurveEditor`), `<details>` "Overrides (optional)" (Icon `right`, blue text, `PipeSegmentForm`), and
    Add/Remove buttons for the efficiency and NPSHr tables (caption "(optional)"). The sketch's tier `more` should
    replace all three with one disclosure.
16. **Always-visible type explanations are uneven**: assigned flow, equipment, orifice, relief valve, tee (but not
    wye) and plug end with a long paragraph about the type (up to ~10 lines); isolation, check and control valves,
    pump, reservoir and reference node have none. One "About this type" line or disclosure, in the same place on
    every type, would make it predictable (the sketch's focus-only help covers field hints, not these paragraphs).
17. **Speed label changes with mode** ("Speed" → "Maximum speed") and the field moves below the two control fields
    when control is on; Status → Control → [Flow setpoint, Minimum speed] → Maximum speed puts minimum before
    maximum, good, but the fixed-speed form has Speed after Control while the controlled one has it last.
18. **What a case can change is not signalled by facet.** The allow-list (`x-override-fields`) coincides with
    Operation + Rating (+ pipe size/length); everything in Size and position (except pipe size/length) is the same
    in every case. The registry can read this from `x-override-fields` instead of a per-field flag, and the panel can
    say once per facet "Same in every case" in a scenario instead of per field (today only the name has that hint,
    and the orifice taps' lock is described only in a code comment).

Units

19. Gauge marking (D4) is applied to reservoir surface pressure, reference pressure and PRV/PSV setpoints, and not to
    differences (cracking, set, rated drop): correct, but the difference fields do not say "difference" in their
    labels (item 4), so the absence of "(g)" is the only cue.
20. `control.minSpeed` and `speed` use the `fraction` category (shown as %), while relief `capacity.overpressure`
    (also a fraction) is shown as "Entered overpressure" with a fraction unit, and pump efficiency points too: check
    they all display as % for consistency (`fraction` category in all three, so likely already consistent; flagged
    only for the registry's unit-category column).
