# Scenario manager: design proposal

**Status: built** (2026-10-25; CLAUDE.md D15; §10 records where the build departs from this design). This design was written on 2026-10-25 against `4ccdf9f` (D14) by a design workflow. Two designers worked from different angles, one on the model and API and one on the web UX, and a synthesizer merged their designs into this one. The synthesizer checked every disputed claim against the code. It re-ran the API designer's prototype and measured the body-limit numbers in §2.5. §1.3 lists where the two designs disagreed and why this design chose as it did.

The owner asked for the scenario manager next (2026-10-25). The owner and the workflow had already decided these points, which were not re-opened:
- Overrides are addressed through a field allow-list, not JSON Pointer (TSD §12 open item 4).
- A scenario changes values only, never topology (PRD §3.8).
- The overridable values are PRD §3.8's list.
- Scenarios travel in the project, in the shared URL, with `schemaVersion` 1 (D14).
- An override whose target no longer exists is kept, reported as orphaned and ignored.

Every other choice in this document is the designers' own. Each is a simple default chosen to serve working engineers, reversible under D14, and not escalated to the owner. §1.2 marks the origin of each.

Sources:
- PRD §2.1, §2.3, §2.4, §3.8, §4.4; SDD §3.2.1, §4.1, §4.12, §5.1; TSD §5.6, §5.7, §10, §12; CLAUDE.md D2, D3, D6, D10, D13, D14.
- Code read: `models/*`, `routers/solve.py`, `main.py`, `workers.py`, `middleware.py`, and `services/solver/{__init__,methods,trace,labels,system_curve}.py`.
- On the web side: `state/{project,workspace}.svelte.ts`, `utils/{edit,piping,factory,encoding,model-rules,validate,labels,results,trace}.ts`, `api/client.ts` and `components/{workspace,panel,results,ui}/*`.

---

## 1. Scope and decisions

### 1.1 Scope

This slice builds all of PRD §3.8:
- A project holds the **base** and up to 20 named **scenarios**. Each scenario stores only its overrides of base values.
- Solve one case or all of them.
- A comparison of chosen results side by side, with differences from the base.
- The pump/system-curve chart shows other cases.
- Scenarios travel in the link.
- Every result says which case produced it and lists that scenario's overrides.

**Not in this slice (Later):**
- The active case in the link.
- "Apply scenario changes to the base".
- Comparison rows saved in the project.
- Differences against a case other than the base.
- Copying the comparison as text (CSV export is deferred, D5).
- Per-case hues on the chart.
- Overrides of values outside PRD §3.8's list: cracking pressure, minimum speed, a pump's control mode, fittings, site and solver settings. Each is a one-line addition to the allow-list.
- Adding or removing components in a scenario (PRD §3.8).
- An example project with scenarios.

### 1.2 Decisions

Origin key:
- **O**: decided before design (owner, or the workflow from the specs).
- **A**: API designer.
- **W**: web designer.
- **S**: synthesizer, either resolving a disagreement or adding what both designs missed.

| # | Decision | Reason | Origin |
|---|---|---|---|
| 1 | Overrides are addressed by a field allow-list: a target (a component, one pipe of a connection, or the project) and a field name from the allow-list for that target's type. | TSD §12 item 4: the safer option. Every overridable value is named, typed and checked; a pointer could reach ids, ports or curve points. | O |
| 2 | Scenarios change values only, never components, connections, ports or pipe counts. | PRD §3.8: it keeps scenarios small in the URL, and every difference from the base is a list of values. | O |
| 3 | The allow-list is PRD §3.8's list, mapped onto the real fields (§2.2). | PRD §3.8. | O, mapped by A and S |
| 4 | An override whose target is gone is kept, reported as `orphaned` and ignored. An override whose target exists but has no such value (a status on a reservoir, a flow setpoint on a pump without speed control, a temperature on a custom fluid) is kept, reported as `not_applicable` and ignored. The web calls both "no longer applies". | O for orphaned. Not-applicable states arise from base edits too (flow control removed, the fluid made custom). Treating them like orphans keeps the user's work and says so. | O, A |
| 5 | Scenarios are part of `Project` (`scenarios`, omitted when empty) and travel in the URL fragment. `schemaVersion` stays 1. | D3, D14. Omitting the key when it is empty keeps every link without scenarios byte-identical. | O, A, W |
| 6 | The server applies the scenario. `/solve` and `/system-curve` take an optional `scenarioId`; `services/scenarios.py` builds the effective project and hands the unchanged solver a plain `Project`. | The SDD specifies it (§3.2.1). There is one authoritative validation (the Pydantic models). The record of what was applied comes from the code that built the solved project. API users get scenarios. No new privacy surface: the body already carries the whole project. | O (SDD), A |
| 7 | The effective project is built as JSON: dump the base (`exclude_unset`), write each override's raw value at its target, drop `scenarios`, then `Project.model_validate`. | The result equals a project whose JSON was edited by hand, `fields_set` included, so a scenario solve equals that project's solve bit for bit. Every model validator runs. Prototype re-run: true. | A |
| 8 | An override's value is a JSON value, validated at apply time by the target's own field and validators. | The type depends on the target: a status is `on`/`off` on a pump and `active`/`isolated` on a gate valve. A typed union per field would duplicate every model type. | A |
| 9 | A scenario is an order-free set: at most one override per (target, field), and no override of a value together with an override of a part of it (`fluid` with `fluid.temperature`). Both are rejected at request validation (400, indices only). | The result does not depend on list order (prototype: 5 shuffles identical). There is one place to look for a value. | A |
| 10 | Pipe material, schedule, nominal size and the bore/roughness overrides form **one** pipe field, `spec`. Length is a separate field. | One user action (a material) rewrites the schedule and size and drops the bore overrides (`withMaterial`). Separate fields let a scenario keep a size that the base's new schedule lacks. One value keeps the scenario's pipe self-consistent, reads as one line ("Pipe 1: Stainless, Sch 40S, 6 in") and is smaller than four overrides. | W, adopted by S over A's six fields |
| 11 | The fluid is one `fluid` field (the whole definition). A built-in fluid's temperature alone is `fluid.temperature`. | A temperature case ("winter, 5 °C") is the common one and should not freeze the rest of the fluid. Anything else changes the fluid as a whole. | A, W |
| 12 | Overrides are a discriminated union on `kind`: `component {componentId}`, `pipe {connectionId, pipeIndex}` (0-based, as `Fitting.pipeIndex`), `project`. `field` is a camelCase dotted path relative to the target, as `x-ordered-fields` uses. | SDD §4.12's nested target is replaced: a flat union gives `pipeIndex` only where it means something and generates precise types. | A |
| 13 | The allow-list is data in `models/scenarios.py`, published as `x-override-fields` on the `Scenario` schema. The web reads it through `utils/model-rules.ts`, with a staleness test. | D10: the web reads model rules and never copies them. Goal seek (SDD §4.13) will reuse the same list. | A, W (name: A's) |
| 14 | Results carry the scenario in the response envelope: `SolveResponse.scenario` and `SystemCurveResponse.scenario` (`ScenarioResult \| null`), listing every override with its state, the value used and the base value. `SolvedState` does not change. | The solver and the corpus dumps stay untouched. The web keeps whole responses per case anyway. | A, over W's `solvedState.scenario` |
| 15 | Scenario text enters a solved state in one place, `annotate()`, after the solve. It adds a "Scenario" methods section first, and a note first in each overridden element's trace. Trace input sources stay `user`/`default`; no `scenario` source is added. | The solver sees only a plain project (non-negotiable). Input names differ per element and are display strings, so relabelling them after the solve would be brittle. The web shows a structured "Changed by this scenario" block from the response instead (§6.11). | A, over W's `source: 'scenario'` |
| 16 | No flags for orphaned or not-applicable overrides. | They are not physics (GOALS §4.6). They are listed in the response, the methods section and the results card. | A |
| 17 | Solve all is one independent `POST /solve` per case: the base first, then the scenarios in order, one at a time from a snapshot. Cases whose results are current are skipped. A topology or validation error belongs to its case and the run continues. Any network error (including 429, 503 and timeout) stops the run, and Solve all resumes with the cases still missing. | TSD §5.7. Progressive results, per-case errors, the same server code and the same 45 s budget per case. No batch endpoint is needed. Stopping is simpler than retrying, and resuming costs one tap. | A, W; stop rule from W, over A's retry-once |
| 18 | `METHOD_VERSION` stays 1.2.0 and `METHOD_CHANGELOG` is unchanged. | Applying a scenario composes inputs and changes no calculation. Each scenario result is the 1.2.0 solve of its effective project (the metamorphic test, §7.2), and the methods section lists that project's differences from the base. | A |
| 19 | Bounds: at most 20 scenarios, 30 overrides per scenario, descriptions up to 500 characters, `pipeIndex` ≤ 99 (`MAX_PIPES` = 100, extracted). | Measured (§2.5): with 160-byte `spec` overrides, 20 × 30 fits the 1 MB body at the largest project with about 20 KB to spare. The API designer's 50 per scenario does not fit (142 KB at 40). These are operating limits and reversible. | A, bound by S |
| 20 | The web uses the UI words **base case**, **scenario**, **case** (either one) and **change** (for an override), and **no longer applies** for an orphaned or not-applicable override. | The app already uses "override" for pipe bore and roughness, fluid properties and atmospheric pressure. | W |
| 21 | Changing a value in a scenario records it in the active scenario and marks it "Changed"; Reset removes the change. Typing the base value back also removes the change. | A scenario's changes are then exactly its differences from the base at the time of editing. API users can still pin a value equal to the base. | W, over A's pinning |
| 22 | In a scenario, values on the allow-list are editable. Names, project description and display units are shared (they apply to every case and never change results). Everything else is read-only with a lock ("Same in every scenario"), and topology actions are hidden. A field is locked by default unless it declares itself a scenario value or shared. | A "scenario" edit applied to the base would silently change every case. Locked-by-default means a field added later is never editable in a scenario by accident. | W |
| 23 | `ws.project` becomes the case's project (base plus the active scenario, applied by the client mirror). `ws.edit` diffs the edit against the allow-list and writes it into the active scenario as one undo step. | Existing forms keep reading `ws.project` and calling `ws.edit`; the routing lives in one place. | W |
| 24 | Pipe changes follow their pipes through every base edit by **object identity** inside the edit (§6.7): moved, reversed or merged pipes keep their changes. A removed pipe's changes are removed with it in the same undo step. A deleted connection's or component's changes are kept as orphaned. | Pipes have no ids. Both designers listed per-function remaps (remove, reverse, join) but missed `insertComponentInConnection`, which can turn a connection to the flow direction and reverse its pipes (`withFlow`, `edit.ts:262`). One generic remap covers every current and future edit path. A removed pipe's index would otherwise re-attach to the next pipe added. | S (generic remap); W and A (removed-pipe rule) |
| 25 | A base valve-type change between a pressure valve (PRV, PSV) and a flow valve (FCV) removes that valve's setpoint changes in every scenario, in the same undo step, with a notice. Overrides do not record the target's kind. | The base already resets the setpoint to 0 for the same reason (`ControlValveForm.changeType`). Forms never change a valve's family, and within a family status and resistance keep their meaning. A kind field would duplicate data the project holds and lengthen every override. | A, over W's recorded kind |
| 26 | New ids never re-use an id that any override targets (`usedIds` includes them). | `newId` takes the first free `${prefix}n` (`factory.ts:182`), so a deleted P7's orphaned change would attach to the next new P7. | A, W |
| 27 | One undo history for the base and all scenarios. Each entry records the case it was made in, and undo/redo switch to that case with a notice. | Undoing a change in a case the user is not looking at would otherwise be invisible. | W |
| 28 | Results, errors, staleness and system curves are kept per case. A case's staleness key is the base hydraulic fingerprint plus that scenario's canonical overrides. | It is cheap on large projects: one base fingerprint per edit, not 21. It is conservative: a base edit to a value a scenario overrides marks the scenario out of date although its results would not change, but stale results are never shown as current. | A, over W's per-case full fingerprint |
| 29 | The active case is page state, not part of the link and not an undo step. A link opens on the base case. | Links stay the project; one link serves every case. The Share dialog says it opens on the base case. | W |
| 30 | Comparison: the base first, then scenarios. Default rows are derived from the project (≤ 40). Values are in display units, with scenario minus base under each value. A relative difference is shown only for quantities with a true zero, and there is no tolerance snapping. A column that did not converge shows no values. | D6 and D13 are acceptance rules for solver changes. Differences between cases are real results of changed inputs. Values that are not a solution are not set beside ones that are. | W |
| 31 | Chart: the active case keeps today's encoding. Other cases are neutral slate with distinct hollow markers and direct labels. Their operating points and their pump curves at a different speed are shown by default; their system curves only on request, one at a time, with Cancel. | No new hues and no palette risk. Free data is shown; costly data (about 41 solves per curve) only on request. | W |
| 32 | Error messages name a scenario by id only. Its name appears in results (methods section, notes), never in an error message. | `VALIDATION_ERROR` never echoes submitted values (D10), and a name is a submitted value. Results already carry names (pump curve names). | S |

### 1.3 Where the two designs disagreed

1. **Pipe fields.** The API designer used six separate fields; the web designer used one pipe-spec value. This design takes the spec, plus length (decision 10). Measured: one spec override (160 B) replaces up to four field overrides (about 95 B each).
2. **Where the scenario record lives.** `SolveResponse.scenario` (A) or `solvedState.scenario` (W). This design uses the envelope (decision 14): the `SolvedState` schema, the corpus dumps and the solver stay as they are.
3. **A `scenario` trace source.** The web designer wanted inputs a scenario set to carry `source: 'scenario'`. The solver cannot know this without seeing scenarios. A post-solve relabel would have to map override fields to trace input names: these are per element type ("Liquid level h_L above z", "Speed ratio s", "Maximum speed s_max (field speed)") and change with the trace text. This design keeps `user`/`default` and adds notes and a structured block (decision 15).
4. **Recording the target's kind.** Not adopted (decision 25). Checked in the forms: `IsolationValveForm` and `CheckValveForm` change `valveType` only within their family, and `ControlValveForm.changeType` resets the setpoint across pressure and flow.
5. **Pinning a value equal to the base.** The web designer removes the change; the API designer keeps it. The web removes it (decision 21), and the API accepts both.
6. **Extension name and fluid addressing.** `x-override-fields` and `project` / `fluid.temperature` are the API designer's; `x-scenario-fields` and a `fluid` target with `temperature` are the web designer's. The path form keeps every field a dotted path relative to its target, the same rule as `x-ordered-fields`.
7. **Staleness key.** A full fingerprint of each case project (W) costs a canonical JSON of the whole project per case per edit, about 0.9 MB at the largest project. Base fingerprint plus overrides (A) is used instead (decision 28).
8. **Solve-all errors.** The API designer retries once after `Retry-After` on 503; the web designer stops on any network error. This design stops (decision 17). Requests are strictly sequential, so `SERVER_BUSY` means another client at the same address, or a full instance, and the stopped run resumes where it stopped.
9. **Override bound.** 50 per scenario (A) does not fit the body limit with spec overrides (§2.5). This design uses 30.
10. **Pipe remapping.** Both designs listed remove, reverse and join. The code also reverses a kept connection's pipes on insert (`insertComponentInConnection` → `withFlow` → `turnedAround`, used by `addBranch` too). This design remaps generically by identity (decision 24) and tests every edit path with a marker property (§7.4).

---

## 2. Model and allow-list

### 2.1 Models (`models/scenarios.py`, new; `models/project.py`; `models/piping.py`)

```python
"""Scenarios: named sets of overrides of base-project values (PRD §3.8, SDD §4.12, CLAUDE.md D15).

A scenario changes values only, never topology. Each override names a target in the base
project (a component, one pipe of a connection, or the project itself) and one field the
allow-list names for that target's type. Its value is checked against the target's own field and
validators when the scenario is applied (services/scenarios.py). A scenario overrides each value
at most once, so the order of its overrides does not change the result.
"""

MAX_SCENARIOS = 20       # fits the 1 MB body limit with the largest project (proposal §2.5)
MAX_OVERRIDES = 30       # per scenario

ComponentField = Literal["status", "speed", "control.setpoint", "setpoint", "resistance",
                         "liquidLevel", "surfacePressure", "pressure", "flow"]
PipeField = Literal["spec", "length"]
ProjectField = Literal["fluid", "fluid.temperature"]

class ComponentOverride(CamelModel):
    kind: Literal["component"]
    component_id: Identifier
    field: ComponentField
    value: JsonValue = Field(description="SI, of the target field's own type (checked when the "
        "scenario is applied); the fields each component type takes: x-override-fields")

class PipeOverride(CamelModel):
    kind: Literal["pipe"]
    connection_id: Identifier
    pipe_index: int = Field(ge=0, le=MAX_PIPES - 1, description="0-based index into the "
        "connection's piping.pipes, as Fitting.pipeIndex (messages number pipes from 1)")
    field: PipeField
    value: JsonValue

class ProjectOverride(CamelModel):
    kind: Literal["project"]
    field: ProjectField
    value: JsonValue

Override = Annotated[
    Annotated[ComponentOverride, Tag("component")] | Annotated[PipeOverride, Tag("pipe")]
    | Annotated[ProjectOverride, Tag("project")],
    Discriminator(_override_tag, custom_error_type="invalid_override",
        custom_error_message="unknown override kind (expected 'component', 'pipe' or 'project')"),
]   # a callable discriminator, as FluidDefinition's, so the error never quotes the tag

class Scenario(CamelModel):
    model_config = ConfigDict(json_schema_extra=_scenario_schema_extra)   # x-override-fields
    id: Identifier
    name: Name
    description: str | None = Field(default=None, max_length=500)
    overrides: list[Override] = Field(default_factory=list, max_length=MAX_OVERRIDES)

    @model_validator(mode="after")
    def _check_overrides(self) -> Self:
        # Per target (("component", id) | ("pipe", id, index) | ("project",)):
        #   the same field twice -> "overrides {i} and {j} set the same value"
        #   a field path that is a prefix of another (fluid, fluid.temperature) ->
        #   "overrides {i} and {j} set a value and a part of it: set the part in the whole
        #    value's override"
        # Indices only: request-validation errors never echo submitted values (SDD §5.1.2).
```

`Project` gains a field and a validator:

```python
scenarios: list[Scenario] = Field(default_factory=list, max_length=MAX_SCENARIOS,
    description="Named sets of overrides of this project's values (the base); solve one with "
    "scenarioId")
# model validator: "scenarios {i} and {j} have the same id"
```

`piping.py` extracts `MAX_PIPES = 100`, used by `PipingSegment.pipes` (today a literal) and by `PipeOverride.pipe_index`.

Model rules:
- Scenario ids have their own namespace; the web writes `S1`, `S2`, ….
- Names need not be unique; the web keeps them distinct only as a convenience.
- A scenario with no overrides is valid, and its solved values equal the base's.
- The generated TypeScript type of `value` is the JSON-value type. The web reads values through typed accessors in `utils/scenarios.ts`.

### 2.2 The allow-list

The allow-list is data in `models/scenarios.py`, keyed by the target's model class. It is the single source for the API, the extension, the tests and later goal seek:

```python
@dataclass(frozen=True)
class Overridable:
    path: tuple[str, ...]            # snake_case attributes from the target to the value
    holder: type[BaseModel]          # the model that must hold the value's last attribute
    keys: tuple[str, ...] = ()       # a group: these sibling attributes are replaced together
    unit: str = ""                   # trace unit: 'm', 'Pa(g)', 'm³/s', 'K', ''
    label: str = ""                  # name in notes and the methods summary

COMPONENT_FIELDS: dict[type[BaseComponent], dict[str, Overridable]]  # every class, {} if none
PIPE_FIELDS: dict[str, Overridable]
PROJECT_FIELDS: dict[str, Overridable]
```

The project's `fluid` field is held by the target itself, so `models/scenarios.py` never imports `Project` and there is no import cycle.

| Target kind | Target type | Field | Value type | Unit | Validation at apply time | Missing holder → |
|---|---|---|---|---|---|---|
| component | Reservoir | `liquidLevel` | number | m | 0 to 1000 | — |
| component | Reservoir | `surfacePressure` | number | Pa(g) | `GaugePressure`, −1e5 to 1e8 | — |
| component | IdealReferenceNode | `pressure` | number | Pa(g) | `GaugePressure` | — |
| component | AssignedFlow | `flow` | number | m³/s | −100 to 100; 0 behaves as a plug (D12) | — |
| component | Pump | `status` | `'on' \| 'off'` | — | Literal | — |
| component | Pump | `speed` | number | — (fraction) | (0, 1]; with control, > `control.minSpeed` (validator, 400) | — |
| component | Pump | `control.setpoint` | number | m³/s | (0, 100]; `CONTROLLED_PUMP_SETPOINT` (422) as for any project | not applicable: "pump P1 has no speed control in the base project" |
| component | IsolationValve | `status` | `'active' \| 'isolated'` | — | Literal | — |
| component | IsolationValve, CheckValve, ControlValve | `resistance` | `FlowCoefficient` or null (null: the cited default) | as entered (K, Cv, Kv) | `FlowCoefficient` | — |
| component | CheckValve | `status` | `'active' \| 'locked_open' \| 'locked_closed'` | — | Literal | — |
| component | ControlValve | `status` | `'active' \| 'failed_open' \| 'failed_closed'` | — | Literal | — |
| component | ControlValve | `setpoint` | number | Pa(g) for PRV/PSV, m³/s for FCV | −1e5 to 1e8; FCV 0 to 100 (validator, `x-setpoint-bounds`) | — |
| component | Plug, TeeBranch, WyeBranch | (none) | | | | any field: not applicable |
| pipe | PipeDefinition | `spec` | object: `materialId` (required), `schedule`, `nominalSize`, `innerDiameter`, `roughness` (each optional) | m for the last three | Only those keys (else 400, `invalid_pipe_spec`, not naming the key). Then `PipeDefinition` with the pipe's length: a custom pipe needs bore and roughness, a library pipe needs schedule and size or a bore. An unknown material, schedule or size is a topology issue (422). | — |
| pipe | PipeDefinition | `length` | number | m | (0, 1e6] | — |
| project | Project | `fluid` | `FluidDefinition` (whole) | — | the union and its fields; out of the property source's range: `FLUID_ERROR` (400) | — |
| project | BuiltinFluid | `fluid.temperature` | number | K | (0, 1000]; out of CoolProp's range: `FLUID_ERROR` | not applicable: "the fluid is a custom fluid, whose properties do not depend on its temperature (set the whole fluid instead)" |

Writing a `spec` removes all five spec keys from the pipe and writes the keys the value has. A spec without `innerDiameter` therefore drops the base's bore override, as `withMaterial` does. The base value of a spec is the base pipe's five keys that are set and not null.

### 2.3 Published rule

`x-override-fields` sits on the `Scenario` schema:

```json
{ "Pump": { "status": {"schema": "Pump", "path": ["status"]},
            "speed": {"schema": "Pump", "path": ["speed"]},
            "control.setpoint": {"schema": "PumpControl", "path": ["control", "setpoint"]} },
  "PipeDefinition": { "spec": {"schema": "PipeDefinition",
                               "keys": ["materialId", "schedule", "nominalSize", "innerDiameter", "roughness"]},
                      "length": {"schema": "PipeDefinition", "path": ["length"]} },
  "Project": { "fluid": {"schema": "Project", "path": ["fluid"]},
               "fluid.temperature": {"schema": "BuiltinFluid", "path": ["fluid", "temperature"]} },
  "Plug": {}, "TeeBranch": {}, "WyeBranch": {}, "...": "every component schema" }
```

- The web finds a value's bounds at `components.schemas[schema].properties[leaf]`, never copied. It finds a component's key with the existing `componentSchemaName()`, and the fluid's holder with `fluidSchemaName()`.
- Ajv already registers every `x-` keyword (`schemaExtensions()`).
- `test_schema_rules.py` fails if the extension and the allow-list disagree, or if `openapi.json` is stale.

### 2.4 Rules on a scenario

| Rule | Where | Outcome |
|---|---|---|
| `kind` unknown, `field` not in the kind's Literal, `pipeIndex` out of bounds, a list over its bound | request validation | 400 `VALIDATION_ERROR`, locations only |
| Same (target, field) twice; a value and a part of it | `Scenario` validator | 400, "overrides i and j …" |
| Two scenarios with one id | `Project` validator | 400, "scenarios i and j have the same id" |
| Anything about the values | applied scenario only (§4.1) | at solve time, for that scenario only |

Only the requested scenario's values are checked. A scenario with a bad value never blocks the base or another scenario, though its structure must still pass request validation.

The web mirrors the structural rules in `utils/validate.ts` (`referenceProblems`), so a link with duplicate overrides is reported on open. The shared fixture (§6.16) includes rejected structures.

### 2.5 Bounds and the body limit (measured at `4ccdf9f`)

- **Room in the body.** The largest project at frontend sizes (`test_project_bounds_fit_the_body_limit`) is 869,509 B of `MAX_BODY_BYTES` = 1,000,000, so 130,491 B remain.
- **Override sizes in compact JSON:**

  | Override | Bytes |
  |---|---|
  | `spec` (pipe 100, stainless, schedule 40S, an unrounded float size) | 160 |
  | `length` | 95 |
  | `status` | 73 |
  | `control.setpoint` | 95 |
  | `resistance` | 101 |
  | whole glycol fluid with property overrides | 211 |
  | scenario header with a 500-character description | 592 (654 with a 100-character name) |

- **At the bounds.** 20 × (654 + 211 + 29 × 160) = 110,100 B, which leaves 20,391 B. At 40 overrides per scenario it would be 142,100 B, which does not fit. So `MAX_OVERRIDES` = 30.
- **The bounds test is extended, not weakened.** It also includes 20 scenarios of 30 overrides: one fluid override, and the rest `spec` overrides at frontend sizes.
- **URL.** The URL fragment holds the whole project. The 8,000-character warning (D3) applies to it unchanged. The API designer measured 1,114 → 1,274 → 1,408 characters for 0, 1 and 10 five-override scenarios on `tests/fixtures/pump_system.json`.

### 2.6 Versions

- `schemaVersion` stays 1 (D14).
- The schema-v1 fixture link and `test_released_links.py` are unchanged, because the web never writes an empty `scenarios`.
- `METHOD_VERSION` stays 1.2.0 (decision 18). If the owner wants scenario results to name a version that has scenarios, a 1.3.0 bump with a changelog line is a one-line change; the corpus comparison would then ignore `method_version`.

---

## 3. API

### 3.1 Requests

```python
class SolveRequest(CamelModel):
    project: Project
    scenario_id: Identifier | None = Field(default=None, description="Solve this scenario of "
        "project.scenarios: its overrides are applied to the base project before the network is "
        "built (null: the base project; unknown id: 404 NOT_FOUND)")
    options: SolveOptions = Field(default_factory=SolveOptions)

class SystemCurveRequest(CamelModel):   # + scenario_id, the same description
```

- `scenarioId` is sent in the body only, never in a query string (D10).
- The web omits it for the base case, so a base request is byte-identical to today's.
- `/solve` adds 404 to its documented responses (`test_openapi_documents_the_errors_the_api_returns`).

### 3.2 Responses

```python
OverrideState = Literal["applied", "orphaned", "not_applicable"]

class OverrideResult(OutputModel):
    index: int                 # 0-based index into the scenario's overrides
    override: Override         # as given
    state: OverrideState       # orphaned: its component, connection or pipe is not in the project;
                               # not_applicable: its target has no such value. Both kept, ignored
    value: JsonValue           # the value used, as validated, SI (null unless applied)
    base_value: JsonValue      # the base project's value, SI (null unless applied); an unset
                               # field gives its default
    unit: str                  # trace unit of value and baseValue ('' for none)
    message: str               # why it was not applied ('' when applied)

class ScenarioResult(OutputModel):
    id: str; name: str; description: str | None
    overrides: list[OverrideResult]   # every override, in the scenario's order

class SolveResponse(OutputModel):       # + scenario: ScenarioResult | None (null for the base)
class SystemCurveResponse(OutputModel): # + scenario: ScenarioResult | None
```

### 3.3 Outcomes, errors and warnings

| Situation | Outcome |
|---|---|
| Unknown `scenarioId` | 404 `NOT_FOUND`, "the project has no scenario 'S9'" (names the id, D10) |
| Target missing: the component or connection was deleted, or `pipeIndex` is beyond the pipes | `orphaned`: applied nothing, reported in `scenario.overrides`, the methods section and the web. Messages: "the project has no component P9", "connection L3 has 1 pipe, no pipe 2" |
| Target present without the value: a field not overridable on its type, or its holder missing | `not_applicable`, the same treatment. Messages: "a reservoir has no status to override", "pump P1 has no speed control in the base project (control.setpoint applies to a speed-controlled pump)" |
| A value fails the field or the target's validators | 400 `VALIDATION_ERROR`, "Invalid input: N problem(s).", every problem listed (§4.1 step 4), never echoing a value |
| The effective project has topology issues (unknown pipe size, `CONTROLLED_PUMP_SETPOINT`, …) | 422 `TOPOLOGY_ERROR`, the issues exactly as for the hand-edited project, message "Scenario S2 cannot be solved: N topology issue(s)." |
| The effective fluid is out of range | 400 `FLUID_ERROR`, "Scenario S2: <the fluid message>" |
| Unknown pump id (system curve) | 404, as now |

The checks run in this order: scenario 404 → override 400 → pump 404 → topology 422 and fluid 400. The base handlers stay as they are; the scenario errors are subclasses (`ScenarioTopologyError(TopologyError)`, `ScenarioFluidError(FluidError)`) with their own handlers.

### 3.4 Solve all

There is no new endpoint. "Solve all" is one independent `POST /solve` per case (TSD §5.7). The web sends them strictly one after another, so the per-client turn never blocks.

- Each request has its own 45 s budget, waiting included. The web never queues a request ahead (`MAX_WAITING_PER_CLIENT` = 1 would let one wait, but its budget would run while it waits).
- 21 requests (base plus 20 scenarios) stay inside the rate limit of 60 a minute per client. Pump-chart curve fetches share that budget; a 429 stops the run (§6.10).
- System curve for a scenario: `POST /system-curve` with `scenarioId`. The default range uses that case's pump speed, so overlays pass the `flowMin`/`flowMax` of the curve already shown and every case shares one flow grid.
- A batch endpoint was rejected. It would need a shared or per-scenario budget, a response of n full traces, new worker semantics and coarse cancellation.

### 3.5 Privacy

Nothing new is logged. The scenario travels in the request body, as the project does, and the access log drops bodies and query strings. Error messages name scenarios by id only (decision 32).

---

## 4. Solver integration

### 4.1 `apply_scenario` (`services/scenarios.py`, new; outside `services/solver/`)

```python
@dataclass(frozen=True)
class AppliedOverride:            # internal; OverrideResult is its API form
    index: int; override: Override; state: OverrideState
    value: JsonValue; base_value: JsonValue; unit: str; message: str
    target_label: str             # "component P2 (pump)", "connection L3, pipe 1", "the fluid"
    label: str                    # "status", "pipe spec", "fluid temperature", ...
    location: tuple[str | int, ...]   # where the value was written in the project JSON

@dataclass(frozen=True)
class AppliedScenario:
    scenario: Scenario; index: int
    project: Project              # plain: no scenarios
    overrides: list[AppliedOverride]
    def result(self) -> ScenarioResult: ...

def apply_scenario(project: Project, scenario_id: str) -> AppliedScenario
```

1. **Find the scenario.** If it is missing, raise `ScenarioNotFoundError("the project has no scenario '<id>'")`.
2. **Dump the base.** `data = project.model_dump(mode="json", exclude_unset=True)`, then `data.pop("scenarios", None)`.
3. **For each override, in order:**
   1. Resolve the target. A component by id. A connection by id, then the pipe index, which must be below the pipe count. The project always resolves. If the target is missing, the override is `orphaned`.
   2. Look up the field in the table for the target's type. If it is absent, the override is `not_applicable`.
   3. Walk `path[:-1]` from the target. The model reached must be an instance of `holder`; if not, `not_applicable`.
   4. Record `base_value`: the base model's value, dumped to JSON. For a `spec`, the set keys.
   5. Write the raw JSON value at its location in `data`. A `spec` replaces the five keys. Remember the location.
4. **Validate.** `effective = Project.model_validate(data)`. On `ValidationError`, map each error to the overrides whose location is a prefix of the error's location, or has it as a prefix, after dropping the union tags pydantic inserts: the component tag after a component index, and the fluid kind after `fluid`.
   - One issue per (error, override) whose location contains the error's, with code = the pydantic error type, as the request-validation handler does.
   - Message: `body.project.scenarios.{s}.overrides.{j}.value{.subpath}: {msg}`. The subpath is for a key inside a `spec` or a whole fluid. An object-level validator gives `body.project.scenarios.{s}.overrides.{j}: Value error, minSpeed must be below speed (...)`, once, as the hand-edited project reports it: at the override(s) of that object whose base value clears the error (the project validated again with that override left out), or at every override of the object when no single one does (review fix, §10). A valid status beside an invalid setpoint of the same valve is not blamed.
   - `componentIds` and `connectionIds` hold the override's target, so the web can say "set by this scenario".
   - An error that matches no override (impossible while the base is valid) is reported at `body.project.scenarios.{s}`, never dropped.
   - Raise `ScenarioOverrideError(issues)`. Messages are `err["msg"]` only, never the input; a sentinel test proves it.
5. **Record values.** Each applied override's `value` is read back from `effective`, as validated.

Cost: the designer measured dump plus validate of a 1000-component project at 36 ms. It runs inside the worker, under the request's budget.

### 4.2 Entry points

```python
def solve_case(project, options, scenario_id) -> tuple[SolvedState, ScenarioResult | None]:
    if scenario_id is None:
        return solve_project(project, options), None        # today's path, untouched
    applied = apply_scenario(project, scenario_id)
    try:
        state = solve_project(applied.project, options)
    except TopologyError as e:
        raise ScenarioTopologyError(e.issues, applied) from e
    except FluidError as e:
        raise ScenarioFluidError(applied, e) from e
    return annotate(state, applied), applied.result()

def system_curve_case(project, pump_id, scenario_id, *, flow_min, flow_max, num_points)
    -> tuple[SystemCurve, ScenarioResult | None]          # apply, then system_curve(effective, ...)
```

`routers/solve.py` calls `run_solve(http, client, solve_case, request.project, request.options, request.scenario_id)`. `main.py` adds handlers for `ScenarioNotFoundError` (404), `ScenarioOverrideError` (400), `ScenarioTopologyError` (422) and `ScenarioFluidError` (400).

### 4.3 Nothing in the solver changes; the base is bit-identical

- No file under `services/solver/` changes. The solver never reads `project.scenarios`.
- A request without `scenarioId` takes exactly today's call, `solve_project(project, options)`. For a project that carries scenarios, the base solve equals the solve of the same project without them, bit for bit apart from the timestamp. Both the base-invariance test (§7.2) and the API designer's prototype show this (re-run: true).
- A scenario solve is `annotate(solve_project(P'))`, where P' is the hand-edited project. `annotate` touches only the methods sections and element notes (§5). Every other field of the solved state is 1.2.0's solve of P'.
- Corpus comparison (TSD §10.4) against `4ccdf9f`: 0 different, no ignores. Plain projects are unchanged, and the solver package has no diff.

---

## 5. Results, traces and methods text

### 5.1 The response

`SolveResponse.scenario` is null for the base. For a scenario it lists every override: its state, the value used, the base value, its unit and, if not applied, why. The web shows this server record with every result, never its own mirror (§6.11).

### 5.2 Element notes

`annotate` puts one note first in the trace of each component or connection with an applied override. Values are in SI, as in other notes, and the web converts them with `siText`. Pipes are numbered from 1 (`labels.pipe_name`).

> Scenario 'Pump 2 off' (id S1) overrides the base project here: status off (base: on). The inputs below are the scenario's values.

> Scenario 'Winter, 6 in discharge' (id S2) overrides the base project here: pipe 1 spec stainless_steel, schedule 40S, nominal size 0.1524 m (base: carbon_steel, schedule 40, nominal size 0.0762 m).

Trace input sources stay as the hand-edited project gives them. A value equal to its field's default is labelled `default` (D10); the note gives its provenance.

### 5.3 Methods summary

A scenario solve gets a first section titled **Scenario**:
- Opening item: "Scenario 'Winter, 6 in discharge' (id S2) of this project: 2 of its 3 override(s) of base values were applied to the base project before the network was built, so every result, trace and section below is of the project with those values. Every other value is the base project's; a scenario changes values only, never the components or connections." The description follows when there is one.
- One item per applied override, for example "The fluid: fluid temperature 278.15 K (base: 293.15 K)." or "Connection L3, pipe 1: length 240 m (base: 120 m)."
- One item per ignored override, for example "Not applied (orphaned): component P9, status: the project has no component P9; the override is kept in the scenario and ignored." Not-applicable overrides read the same, with "(not applicable)".
- Reference: `SCENARIO_DECISION` = "OpenSolve Pipe design decision D15 (CLAUDE.md), from docs/proposals/scenario-manager.md."

A base solve has no scenario section and `scenario` is null. The web labels it "Base case", and its copied methods text adds "Case: base case" when the project has scenarios (§6.11).

### 5.4 Value text

- Numbers are written `:.6g` with their unit; strings as they are.
- null is "none (the default)". A `FlowCoefficient` is "Cv 120".
- A spec is "stainless_steel, schedule 40S, nominal size 0.1524 m", adding ", inner diameter … m" or ", roughness … m" when set.
- A fluid is "propylene_glycol at 278.15 K, mass fraction 0.3", with ", with property overrides (density 1030 kg/m³)" when it has them, or "custom fluid 'Brine' (density 1100 kg/m³, dynamic viscosity 0.002 Pa·s, vapor pressure 2339 Pa absolute)", with " at … K" after the name when its temperature is set: the values that define it, so a change of one property never reads "X (base: X)" (review fix, §10). The web's text gives the same values in display units.
- A speed-controlled pump's `speed` is its "maximum speed ratio" (D11), a fixed-speed pump's its "speed ratio".

### 5.5 No flags

Orphaned and not-applicable overrides are not physics. They appear in the response, the methods section and the web's results card (decision 16).

---

## 6. Web

### 6.1 Rules the user can rely on

1. **Where edits go.** An always-visible bar names the case being edited, says where edits go, and is teal in a scenario. Colour is never the only signal.
2. **Which case produced a result.** Every result names its case: the results header, trace, chart caption, methods summary, copied methods text and every comparison column.
3. **What a scenario changed.** Every changed field shows "Changed", the base value and Reset. A scenario's results list its changes as the server applied them, including any it ignored.
4. **No silent change of meaning.** A change never re-attaches to another pipe, a recycled id, or a setpoint of another meaning. When a change can no longer apply, it is kept and shown as "no longer applies". The exception is a removed pipe, whose changes go with it (§6.7).
5. **Projects without scenarios.** They look and behave as today, apart from the Scenarios button: no bar, no Compare and no decorations. Their link, requests and results are byte-identical (§7.4).

### 6.2 Header (`WorkspaceHeader.svelte`)

- A new **Scenarios** button (new `layers` icon) opens the scenario manager. Once scenarios exist it shows a count, with the accessible name "Scenarios (3)".
- Placement:
  - It comes right after the project name in DOM order.
  - On phones held upright it ends row 1 (home, name, Scenarios). Row 2 keeps Undo, Redo, Cancel, Solve, Share and Settings, which would not fit with a sixth control at 390 px.
  - From 640 px there is one row.
- **Solve** solves the active case. When scenarios exist its accessible name includes the case ("Solve Winter"); the visible label stays "Solve". The existing Cancel also cancels a Solve all run, with the accessible name "Cancel solving all cases". A solve goes on after a case switch: Solve keeps its spinner and Cancel, named "Cancel solving Winter" when another case is shown, and the other Solve buttons are unavailable until it ends (review fix, §10).

### 6.3 Case bar (`workspace/ScenarioBar.svelte`, new)

The bar appears only when the project has at least one scenario. It sits between the header and `<main>`: across both panes on desktop, and above the Build/Results tabs on phones, so it is visible in every pane.

```
Desktop, a scenario active (bg-teal-50, 4 px left border teal-600, text teal-900):
| Case [ Winter (3 changes)        v ]  Edits change only this scenario's values.   [>> Solve all] |
Base case active (bg-slate-50, border-slate-200):
| Case [ Base case                 v ]  Edits change the base case and every scenario that does not set its own value.  [>> Solve all] |
Phone (390 px): the mode sentence is hidden below 640 px (the colour, the select's text and the Build banner carry it)
| Case [ Winter (3 changes) v ] [>> Solve all] |
```

- **Case select.** A native `<select>` with the visible label "Case". Its options are "Base case", then each scenario as "Winter (3 changes)" or "Winter (3 changes, 1 no longer applies)".
- **Switching.** It is page state: not an undo step and not in the link. A polite live region announces it: "Showing scenario Winter, 3 changes. Your edits now change this scenario."
- **Solve all.** It is `aria-disabled` with the reason "Every case's results are current." when nothing needs solving, or "Every case is solved except Winter, which has an error to fix first." when the only cases left have a current error of their own. During a run it stays in place, unavailable (the focus stays on it), and the progress "Solving 2 of 4: Winter…" has a line of its own under the row, the one live region that announces it; a single solve of a case other than the one shown reads "Solving Winter…" there (review fix, §10). Its hint: "Solves each case whose results are missing or out of date, one after another: up to {n} solves."

### 6.4 Scenario manager (`workspace/ScenarioManager.svelte`, new)

It uses the existing wide `Dialog`: a modal on desktop, a bottom sheet (92 dvh) on phones. Its title is "Scenarios". The intro reads: "A scenario keeps another operating or design case of this network, such as a pump off, a valve closed or a larger pipe, as a list of values changed from the base case. Editing the base case updates every scenario that does not set its own value. The layout of the network is the same in every scenario."

- **Base case card:** "The network as built.", with a result status chip and [Show].
- **Scenario card** (`<details>`; the active one starts open):
  - **Summary line:** the name, the id (monospace), "3 changes", and a status chip: Solved, Out of date, Not solved, Failed, Did not converge, Solving… or Waiting.
  - **Name:** a required `TextField` with the schema's length limit, labelled "Name of scenario S2".
  - **Description:** optional, multiline.
  - **Changes:** one row per change, giving the element name, the field label and the value in display units, with "Base: …" on a second line on phones. [Show] closes the dialog, switches to the scenario and opens the element in Build. [Remove] is one undo step.
  - **No longer applies** (only when there are any): rows such as "P7 (deleted) · Speed 90 %: no longer applies, ignored when solving" or "P1 · Flow setpoint: P1 has no flow control", each with [Remove], plus "Remove the 2 changes that no longer apply".
  - **Problems:** client-side validation of the case's project. An example is a base minimum speed raised above the scenario's maximum speed, with [Show].
  - **Actions:** [Show] [Duplicate] [Move up] [Move down] [Delete], each at least 44 px, in a wrapping row. There is no drag. A new `up` icon is needed.
- **Footer:** [New scenario] [Done]. The long-link warning of `ShareButton` is repeated above the footer when `store.urlTooLong` is set.

| Action | Behaviour | Undo label |
|---|---|---|
| New scenario | Adds "Scenario n" (id `S<n>`, the first free one among scenarios) with no changes, at the end. Makes it active, opens its card and focuses its Name with the text selected. | "add scenario" |
| Duplicate | Adds "Winter (copy)" (cut to the limit) right after the original, with its changes but not its results, makes it active and focuses its name. | "duplicate scenario Winter" |
| Delete | Asks "Delete scenario «Winter»? Its 3 changes and its results are removed. You can undo this." [Cancel] [Delete]. An active scenario returns to the base case. Focus goes to the list heading. Deleting the last scenario removes the `scenarios` key. | "delete scenario Winter" |
| Rename, describe, move | Labels only: results are never made out of date. | "rename scenario Winter", … |

At a bound (`schemaBounds`: 20 scenarios, 30 changes), New, Duplicate and value edits that would add a change are `aria-disabled` or refused with the reason, for example "A project holds at most 20 scenarios." or "A scenario holds at most 30 changes."

### 6.5 Switching the active case

- **Build.** Build shows the case's values. The navigator path, tab and open port stay, since the topology is the same.
- **Results.** Results shows the case's latest results and keeps the selected view (Nodes, Links, …), so flipping cases on one table compares them. An open trace stays on the same element if the case has results; otherwise it closes.
- **No results yet.** A case without results shows "Winter has not been solved yet. [Solve] or [Solve all]", the button's accessible name "Solve Winter" (a name of up to 100 characters on a button would not fit a phone).
- **Load.** Reloading or opening a link starts on the base case.

### 6.6 Editing in a scenario

**Three classes of input**

| Class | Inputs | In a scenario |
|---|---|---|
| Scenario values | The §2.2 list: pump status, speed and flow setpoint (the setpoint only when the base pump has flow control); valve status, resistance and control-valve setpoint; reservoir liquid level and surface pressure; reference-node pressure; assigned flow; pipe spec and length; fluid and temperature | Editable. Recorded in the active scenario and marked Changed |
| Shared labels | Component names, project name and description, display units: exactly what `hydraulicFingerprint` excludes | Editable. Applies to every case and never changes results |
| Everything else | Topology (add, insert, branch, delete, connect, disconnect, plug, ports), elevations, valve type, cracking pressure, branch loss model and angle, pump curve and library, pump control mode and minimum speed, fittings, site elevation, atmospheric pressure, solver options | Read-only, with a lock and "Same in every scenario" |

**Field states**

- **Scenario value, unchanged:** as today.
- **Scenario value, changed:** a 2 px teal-600 border and one line under the input, before any hint: `[Changed]  Base: 2.50 m  [Reset]`.
  - The line is wired with `aria-describedby`: "Changed in this scenario. Base value 2.50 m."
  - Reset's accessible name is "Reset Liquid level to the base value, 2.50 m". Reset is one undo step ("reset liquid level in Winter").
- **Base case, a value scenarios set:** a hint with the `layers` icon, "Winter sets its own value." or "3 scenarios set their own value: Winter, Pump B off, 6 in main." There is no Reset here.
- **Locked:** `readonly` but focusable, with a slate-50 fill, normal text and a lock icon. `aria-describedby` points to "Same in every scenario." A locked select is drawn as a read-only text input showing the option's label. Disabled controls are never used: they lose focus and fail contrast.
- **Locked by default.** `NumberField`, `SelectField` and `TextField` read a `fieldMode` context from `Workspace.svelte`. In a scenario they are locked unless given a `change` prop (a scenario value) or `shared`.
  - Inputs not built on them (checkboxes, custom editors) are locked explicitly.
  - The edit-layer refusal is the backstop.

**Composite inputs (one change, one note at the group)**

- **Resistance** (`ResistanceField`): the kind and the number form one `resistance` change. Choosing another kind records null until a value is entered, as the base does.
- **Assigned flow** (`AssignedFlowFields`): direction and magnitude form one `flow` change.
- **Pipe** (`PipeSegmentForm`): material, schedule, size and the bore and roughness overrides (or a custom pipe's bore and roughness) form one `spec` change. The note sits in the pipe card's header, for example "Changed: Stainless, Sch 40S, 6 in. Base: Carbon steel, Sch 40, 4 in. [Reset pipe]". Length has its own note.
- **Fluid** (`FluidSettings`):
  - When only a built-in fluid's temperature differs from the base, a `fluid.temperature` change is recorded.
  - Any other fluid edit records one `fluid` change holding the whole definition, temperature included. It replaces a `fluid.temperature` change if one existed, as the order-free rule requires. While a `fluid` change exists, editing the temperature updates it.
  - The note sits at the section heading. The calculated-properties panel keeps working, because it reads the case's fluid.
- **Pump:**
  - The Control select and Minimum speed are locked; flow control cannot be started in a scenario.
  - The hint "This pump is off: its flow control is not applied" still shows when a scenario turns the pump off.
  - `speedBounds` and `controlFieldBounds` read the case's component, so a maximum speed at or below the minimum speed is reported at the field (`x-ordered-fields`).

**Actions hidden in a scenario**

- `ComponentActions` (Add after, Add before, Add branch, Delete) is replaced by `panel/ScenarioBanner.svelte`, about the same height on phones:
  > **Scenario: Winter.** Values you change here are recorded in this scenario and marked "Changed". Locked values are the base case's, the same in every scenario. Names and display units are shared by every case. [Switch to base case]
- In `ConnectionPanel`: Insert component, Add branch, Disconnect, Add pipe segment and Remove pipe ("Go to …" stays).
- The add and remove buttons of `FittingsEditor`, `PortsEditor` and `PumpCurveEditor`.
- An unconnected port, and an empty project, say "Switch to the base case to connect or plug this port." (or "…to add a component") with that button.

**Edit routing (`Workspace.edit`)**

- `ws.project` becomes `caseProject`: `applyScenario(store.project, activeCase).project`, deep-frozen and derived, carrying the base's `scenarios`.
- `ws.store.project` stays the stored base. `labelsProject`, `displayUnits` and `NavigatorStore` keep using the base: names, units and topology are the same in every case.
- In a scenario, `edit(change, label)`:
  1. applies `change` to a copy of the case project;
  2. diffs the result against the case project using the allow-list, sorting each difference into `changes` (allow-list values, composites as above), `shared` (names, project metadata, units) or `refused` (anything else, including any id, port, connection or pipe-count difference);
  3. if anything is refused, changes nothing and shows "In a scenario you can change only its values. Switch to the base case to {label}.";
  4. otherwise makes one `store.update` on the base. It upserts each change into the active scenario, deletes a change whose value equals the base value, and applies the shared edits to the base. The label is "{label} in {scenario name}", and merging of equal labels works as today;
  5. refuses the edit, with the field's or model rule's message, when the case's resulting project is invalid (schema, references, model rules), as base edits are refused today.

### 6.7 Base edits that move or retire changes (`utils/scenarios.ts`, called from `ProjectStore.update`)

Every base edit runs inside `carryChanges(change)`, a wrapper applied in `store.update` for base edits.

**Pipe changes**

- Before the edit, it records which pipe object of the draft each pipe change targets.
- Edit functions keep pipe objects when they move them: `reversePiping` (`[...pipes].reverse()`), `deleteComponent` with `join` (concatenation), `removePipe` (filter) and `insertComponentInConnection` (the kept connection's `pipes`). A test enforces this (§7.4).
- After the edit, each pipe change (c, i) is handled in the first of these cases that applies:
  1. Its pipe object is found at (c′, i′): the change is retargeted there. This covers joins (with reversal and offset), and inserts that turn the kept connection to the flow direction.
  2. Connection c still exists with the same number of pipes: the change is kept at (c, i) (the pipe was edited in place).
  3. Connection c still exists with fewer pipes: the pipe was removed, and its changes are removed in the same undo step. The notice reads "Pipe 2 removed, with its changes in Winter. Undo restores both."
  4. Connection c is gone (deleted, disconnected, or a plug stub removed by a join): the change is kept and becomes orphaned.

  A change that was already orphaned is left as it is.

**Other cases**

| Base edit | Scenario changes | User is told |
|---|---|---|
| Delete a component (no join) | Its changes and those of its removed connections are kept and no longer apply. Undo makes them apply again. | DeleteDialog: "2 scenario changes refer to it (Winter, Pump B off). They are kept but no longer apply; you can remove them in Scenarios." |
| Insert into a connection, or add a branch | The kept connection's changes follow its pipes (case 1 above). The new short pipe after the component has the base values in every scenario. | When the split pipe had a `spec` change: "The new pipe after P3 has the base case's size in Winter, which changes the pipe it was split from." |
| Control valve PRV/PSV ↔ FCV | That valve's `setpoint` changes are removed in every scenario (decision 25). Status and resistance stay. | "The setpoint changes of V2 in Winter and Peak were removed: a PRV or PSV setpoint is a pressure, an FCV's a flow." |
| Pump flow control removed | Its `control.setpoint` changes no longer apply (not applicable). They apply again when flow control is added back. | A notice |
| Fluid made custom | `fluid.temperature` changes no longer apply. | A notice |
| Any new id | `usedIds` includes every id an override targets, so `newId` never re-uses one (decision 26). | — |

### 6.8 Undo and redo

- **History.** There is one history. Each `HistoryEntry` records the `caseId` it was made in.
- **Switching on undo and redo.** They switch to the entry's case if it still exists in the restored project, otherwise to the base. They show "Undid change liquid level in Winter. Now showing Winter." only when the case changes.
- **Manager edits.** Add, duplicate, rename, move, delete and remove-change are made in the case the user was in. Undoing "add scenario" therefore returns to the base case.

### 6.9 Results per case (`ProjectStore`)

- **Store fields.** `ProjectStore` gains `activeCase: string | null`, where null is the base. `results` becomes a getter for the active case's `ResultsState`. `resultsFor(caseId)` and `allResults` serve Compare, and every existing reader of `store.results` keeps working.
- **Per-case state.** Each case keeps its own response, error, stale, errorStale and cancelled flags, its `solvedProject` (the whole project as sent), its staleness key and its system-curve cache.
- **Deleted scenarios.** Deleting a scenario drops its results.
- **Staleness** (decision 28).
  - The base key is `hydraulicFingerprint(project)`, unchanged.
  - A scenario's key is that plus `canonicalJson(scenario.overrides)`. Editing Winter makes only Winter out of date, and renaming changes nothing.
  - A base edit makes the base and every scenario out of date. This includes a scenario that overrides the edited value: it is conservative, and never shows stale results as current.
- **Assigned flows.** The "as entered" flows in the Assigned flows table come from the case's solved inputs, `applyScenario(solvedProject, caseId)`.

### 6.10 Solve and Solve all

- **Solve one.** Header Solve, "Solve again" and "Solve now" solve the active case. The request carries the full project plus `scenarioId` (absent for the base). The rest is today's flow: a newer solve supersedes an older one, an edit during a solve makes its result out of date, and the method version is recorded.
- **Solve all** (decision 17):
  - **Which cases:** those whose results are missing, out of date, cancelled or failed with a network error. A case with current results, or with a current topology or validation error, is skipped: the solver is deterministic.
  - **Order:** the base first, then the scenarios in list order, one request at a time, all from the project as it was when Solve all was pressed. Edits during the run make results out of date by the usual rules.
  - **Errors:** a topology, validation, fluid or not-found error is recorded for its case, and the run continues. Any `NetworkError` (no connection, timeout, 429, 503 `SERVER_BUSY` or `TIMEOUT`) stops the run. The cases not reached show "Not solved: the run stopped after a network error", and Solve all offers itself again.
  - **Progress:** Solve shows its spinner. The bar and the Compare view show "Solving 2 of 4: Winter…". Compare's headers show Waiting, Solving… or the outcome. The results status line says "Solving 2 of 4 (Winter)…".
  - **Cancel:** aborts the request in flight and skips the rest. Cases already solved keep their new results. The others keep what they had, labelled as today, and focus returns to Solve.
- **System curves.** A solve starting still cancels curve requests. A curve fetch waits for the run (one request at a time).

### 6.11 Traceability in the results

- **Header.** "Results" with a case chip (teal for a scenario, slate for the base), and the live status "Last solve of Winter: converged".
- **Case tabs.** These appear only when scenarios exist: `[ Winter ] [ Compare cases ]`. The first tab is the existing results pane for the active case, unchanged below. Compare works even when the active case has no results.
- **Scenario card** (`results/ScenarioCard.svelte`, at the top of a scenario's results):
  - "Scenario: Winter (S2)" and its description.
  - "The base case with these 3 changes:", from the server's `scenario.overrides` with state `applied`, in display units with base values. Each element is a link to its trace.
  - "Ignored, no longer applies:", with the server's messages.
  - For the base case of a project with scenarios, one line: "Base case: the network as built, without scenario changes. [Compare cases]".
- **Tables.** A row whose element the scenario changed has "changed in this scenario" in its detail line.
- **Trace view.**
  - A case chip next to the element description.
  - A **Changed by this scenario** block at the top, listing that element's applied overrides with base values in display units, from the response (decision 15).
  - Below it, the server's notes, including the scenario note.
- **Methods summary.** The server's Scenario section is shown first, and the heading adds "for scenario Winter". `methodsText` adds "Case: scenario Winter (S2)", or "Case: base case" when the project has scenarios, so copied text always names its case.
- **Pump chart caption.** "Pump and system curves: Pump A, Winter".
- **Inputs to check.** It reads `ws.project`, so it covers the case. It also lists "Winter has 1 change that no longer applies (P7 was deleted)." with [Review], which opens the manager at that card.
- **Scenario errors.**
  - A 400 issue at `scenarios.{s}.overrides.{j}` is shown as "The value Winter sets for P1 speed is not valid: …" with [Show] and [Reset to base].
  - A 422 issue whose component or connection a scenario change targets adds "Set by this scenario." with [Reset to base].

### 6.12 Compare cases (`results/CompareView.svelte`, `utils/compare.ts`, new)

**Content**

- The heading "Compare cases" and the intro "Chosen results of each case side by side. Under each scenario value is its difference from the base case.", with [Choose results…] and [Solve all].
- When some results are missing or out of date: "2 of 4 cases have results that are missing or out of date." with [Solve all], counting the cases Solve all would solve. Cases whose latest solve failed with an error of their own are named apart: "Winter failed with an error to fix first: Solve all skips it until its inputs change."
- **Columns:** the base first, then the scenarios. Each header is a button that switches to its case, with a status line: Converged, Did not converge, Out of date, Not solved, Failed, Solving…, Waiting or Cancelled, each with an icon.
- **Rows:** "Pump A · Flow (L/s)". The row header opens that element's trace in the active case; while the active case has no results it is unavailable, described "Solve Winter to open its traces.". A column header switches case and gives the focus to that case's tab.

**Default rows** (derived from the stored project and its scenarios, at most 40, pumps and changed elements first)

1. Status: "Converged, 0 physically invalid", "Did not converge" or "2 physically invalid".
2. Each pump: flow and head. NPSH margin where the base has one. Speed when any case has the pump flow-controlled or changes its speed.
3. Each element a scenario changes:

   | Element changed | Rows |
   |---|---|
   | Valve | flow, state |
   | Reservoir or reference node | outflow |
   | Pipe | its connection's flow and head loss |
   | Fluid | the Summary's density and vapor pressure |

4. Each assigned-flow node: gauge pressure at its port.
5. Lowest static pressure and highest velocity, each with where it occurs.

**Values**

- From each case's solved state, through the existing `Formatter`: display units, 4 significant figures, 0.01 m for heads.
- Under each scenario value: scenario minus base, with a true minus sign and + for increases, for example "−2.20 (−17.9 %)". The relative part appears only for flow, velocity, pump head, head loss, power and speed. It is never given for gauge pressures, HGL, EGL, elevations or NPSH margin.
- "Same" (muted) appears only when the two values display identically; the exact difference is in the title. There is no tolerance snapping (decision 30).
- Text rows show the scenario's text, and "base: Open" when it differs.
- An alert icon, with screen-reader text, marks an element with a physically invalid flag in that case.
- A column that **did not converge** shows "—" with the header "Did not converge: no values shown". Its own results tab still shows them, with today's warnings.
- "Not solved", "Failed" and not-reached columns show "—" (a response kept is from an earlier version of the project). Out-of-date values are tinted amber, under an amber "Out of date" header. A long status has a short form in the header ("Not reached"), its full words for screen readers.
- Footnote: "Differences are the scenario's value minus the base case's, in the units shown; 'Same' means the values agree to the precision shown. Values are from each case's last solve."

**Choosing rows** (`results/CompareRowsDialog.svelte`)

- The current rows, each with [Move up] [Move down] [Remove].
- "Add results": an element select grouped by kind, with a filter beyond 6 elements, then checkboxes for that element's quantities, then [Add].

  | Element | Quantities |
  |---|---|
  | Pump | flow, head, speed, efficiency, shaft power, NPSHa, NPSH margin, status |
  | Valve | flow, head loss, pressure drop, state, setpoint met |
  | Connection | flow, largest velocity, head loss |
  | Port | pressure, absolute pressure, HGL, EGL |
  | Reservoir or reference node | outflow, EGL |
  | Assigned-flow node | pressure, HGL |
  | Network | lowest pressure, highest velocity, status |

- [Reset to defaults].
- The trace view has "Add to comparison" when the project has scenarios.
- The selection is page state: a reload restores the defaults.

**Layout** (container query, not viewport)

- **≥ 30 rem:** a `ResultsTable`-style table. The row-header column sticks, with a divider. The table scrolls sideways in its own box, about three 7 rem case columns in the 512 px results pane at 1280 px.
- **< 30 rem** (phones): one card per row, with no sideways scrolling.
  ```
  Pump A · Flow (L/s)
    Base case      12.30
    Winter         10.10   −2.20 (−17.9 %)
    Pump B off      8.02   −4.28 (−34.8 %)
  ```
- **Accessibility:** a `<table>` with the caption "Results by case", `th scope=col` per case (status inside) and `th scope=row` per result. Differences carry the screen-reader prefix "difference from base". Cards are `<section>` + `h4` + `<dl>`.
- **Empty state:** "No case has results yet." [Solve all].

### 6.13 Pump chart with other cases (`PumpChart.svelte`, `utils/pump-chart.ts`)

- **Active case.** Drawn as today: pump curve `#2a78d6` (dashed where extrapolated), system curve `#eb6834`, operating point in ink.
- **Other cases.**
  - Drawn in slate-600 `#475569` (7.6:1), each with its own hollow marker (triangle, rect, star, crossRot, rectRounded; `rectRot` stays "held at zero flow") and a direct label drawn by a small Chart.js plugin.
  - Identity is never colour alone: shape, label, legend, tooltip and table carry it. No new hues are used, so no new palette needs checking. Case hues, if ever wanted, need an all-pairs distinctness check in both themes (at most 3 slots).
- **Shown by default.**
  - The operating point of every solved case, with stale ones labelled "(out of date)".
  - The pump curve of a case that runs the pump at another speed, from its `PumpResult.curve`, as a thin slate line with a label.
- **On request.**
  - A checkbox reads "Also show the other cases' system curves", with the hint "Each is computed on request, one at a time, for that case's last solve; a curve costs about 41 solves of the network."
  - Ticking it queues `POST /system-curve` with the case's `solvedProject`, `scenarioId` and the active curve's `flowMin`/`flowMax`, for the other cases the chart shows: after a case switch, for the case that became another, never for the case shown.
  - While the curves load: "Computing system curves: 1 of 3…" [Cancel]. Cancel stops the queued overlays only.
  - The cache is per (case, pump) and is dropped with that case's next solve. A curve is never shown with another solve's results (D10).
- **Controls.** These appear when at least 2 cases have a result for this pump: a fieldset "Cases on the chart" with one 44 px checkbox per solved case and its marker swatch. All are ticked by default, at most 6 at once; past 6 the rest are disabled with the reason "At most 6 cases at once."
- **Accessibility.** The `role="img"` summary adds "other cases' operating points: Winter 10.1 L/s at 32.0 m; …". The data table adds "Operating points by case" (Case, Flow, Head, Speed, State), plus one system-curve table per case shown. The chart's height is unchanged, and the legend wraps at 390 px.

### 6.14 Sharing

- **Share dialog.** It adds "This link holds the base case and its 3 scenarios. It opens on the base case." When a scenario is active, it also says "You are looking at «Winter»: the person you send it to can choose it from the Case menu."
- **Long links.** The 8,000-character warning is unchanged and covers the whole encoded project. The manager repeats it when it applies.
- **Copy-on-write is unchanged.** Every scenario edit rewrites the current URL, and older links open older states.

### 6.15 Accessibility checklist

- **Text, not colour only.** The case is named in text wherever colour marks it: the bar, the banner, the chips and "Changed".
- **Live regions** announce case switches, solve-all progress and outcome, undo switches and refusals, each once: Solve all's progress only in the case bar, and a case switch replaces the results status line instead of updating it.
- **Focus.**
  - A new scenario focuses its name; Delete focuses the list heading.
  - Show and "Switch to base case" focus the current heading (`focusCurrentHeading`).
  - The end of a run focuses Solve (Solve all stays in place during the run, so a run started from it keeps the focus there). The overlay Cancel and retry hand focus to each other. A control that goes when it is used (Compare's column headers, the card's Compare cases) gives the focus to the tab it shows.
- **Group notes.** The inputs of a composite value (a pipe's size and material, the fluid, a valve's resistance) are each described by the group's note ("Changed in this scenario. Base value …", "Winter sets its own value.").
- **Locked fields** are read-only and focusable, described by "Same in every scenario."
- **Interaction.** All targets are at least 44 px. There is no drag and no hover-only information. Comparison and chart data are available as tables.

### 6.16 Client mirror and shared fixture

- **`utils/scenarios.ts`** (new):
  - `overrideFields()` (from `x-override-fields`, via `model-rules.ts`);
  - `applyScenario(project, id)`, giving `{project, overrides: [{index, state, message}], problems}`;
  - `diffToChanges`;
  - `withChange` and `withoutChange`;
  - `carryChanges` (§6.7);
  - `scenarioKey` (§6.9);
  - `changeLabel` and `changeValueText` (display units; the field labels extend `labels.ts`, e.g. `fieldLabel`).

  The mirror is for display and editing only; results always show the server's record.
- **The shared fixture.**
  - `apps/api/tests/fixtures/scenario_cases.py` generates `apps/web/src/lib/utils/__fixtures__/scenario-cases.json` with the real `apply_scenario`. Each case has the input project, the scenario id, the expected effective project, the override states and the error locations; rejected structures are included.
  - `gen-api-types.sh` regenerates it alongside `openapi.json`.
  - A pytest test fails while it is stale, and Vitest runs the mirror on every case.
  - It is generated, never hand-edited.

---

## 7. Tests

No existing test is weakened. The schema-v1 fixture and `test_released_links.py` stay as they are (§2.6).

### 7.1 API unit tests (`tests/unit`)

The new files are named `*scenario_*`. They are distinct from D12's "scenario tests" (`tests/reference/test_assigned_flow_scenarios.py`), which use the word in its test sense.

- **`test_scenario_models.py`:**
  - The allow-list covers every class in the `Component` union, following the pattern of `test_every_component_schema_is_covered`.
  - Every entry's path and holder exist on its model, and its unit is one `utils/trace.ts` understands.
  - The `ComponentField`, `PipeField` and `ProjectField` Literals equal the allow-list's names.
  - `x-override-fields` states exactly the allow-list (`test_schema_rules.py` pattern).
  - Rejections:
    - duplicate overrides;
    - a value with a part of it;
    - duplicate scenario ids;
    - a field of another kind (`pipe` with `status`);
    - an unknown kind;
    - `pipeIndex` 100;
    - lists over their bounds.

    Each is rejected with a message that contains no submitted value: a sentinel, as in `test_validation_errors_do_not_echo_submitted_values`.
  - `test_project_bounds_fit_the_body_limit` is extended with 20 × 30 overrides at frontend sizes (§2.5).
- **`test_apply_scenario.py`:**
  - Parametrized over every allow-list entry: a valid value lands at its target, and the rest of the effective project equals the base, by dump equality.
  - `scenarios` is absent from the effective project, and its `fields_set` equals that of the JSON edited by hand.
  - `spec` drops the bore override when the value omits it, and a spec with `length` is rejected.
  - Orphaned cases (component, connection, pipe index) and not-applicable cases (status on a reservoir, tee or plug; `control.setpoint` on a fixed pump; `fluid.temperature` on a custom fluid) are ignored, with their messages.
  - Invalid values are all reported together, with locations, sub-paths and `componentIds`/`connectionIds`, and without echo. The set:
    - speed > 1, and speed ≤ minSpeed;
    - `isolated` on a pump;
    - an FCV setpoint > 100;
    - a custom spec without a bore;
    - a temperature given as an object;
    - an invalid whole fluid.
  - Base values: unset defaults give the default, a value equal to the base still counts as applied, order independence holds over 20 seeded shuffles, a scenario with no overrides gives the base, and an unknown id raises.
- **`test_scenario_solve.py`:**
  - The metamorphic and property tests of §7.2.
  - `annotate` adds exactly one first methods section and one first note per overridden element, and nothing else.
  - A scenario's topology and fluid errors carry the same issues as P_hand, with the scenario id in the message.
- **`test_api_scenarios.py`:**
  - `/solve` and `/system-curve` with `scenarioId` fill `scenario`, which is null for the base.
  - Errors: 404 for an unknown id; 400 issues, without echo; 422 and fluid errors in a scenario; the order of checks (§3.3).
  - The response matches its schema, and the OpenAPI document lists 404 for `/solve`.
  - A solve-all sequence of 21 requests passes the per-client rule.
  - `test_logging_privacy.py` gains a scenario request: nothing of the body is logged.
- **`test_scenario_cases.py`:** the shared web fixture is current (§6.16).

### 7.2 Independent metamorphic and property tests

The reference P_hand is built by a small JSON patcher written in the test (40 lines: it walks dicts and lists by the override's target and writes the value). It never calls `apply_scenario`, so the two implementations check each other.

1. **Metamorphic, bit for bit** (timestamp excluded).
   - Cases: reference projects chosen to cover:
     - pumps and a controlled pump;
     - a PRV, a PSV, an FCV and check valves;
     - an assigned flow;
     - glycol and custom fluids;
     - multi-pipe connections;
     - Crane tees.
   - Each case runs with a seeded scenario of 1 to 6 overrides.
   - Checks: `solve_case(P, s)` equals `(annotate(solve_project(P_hand), applied), result)`, and every field of the solved state outside `trace.methods.sections[0]` and the first notes equals `solve_project(P_hand)` exactly.
   - `system_curve_case` points equal `system_curve(P_hand)`.
2. **Base invariance.** `solve_case(P + scenarios, None) == solve_project(P)` exactly, and so does the system curve.
3. **Equal-to-base scenario.** A scenario whose overrides restate the base values gives a solved state equal to the base's in every value and every trace input, notes and the first methods section aside.
4. **Order independence.** Shuffled overrides give identical solved states.
5. **Physics checks, independent of the patcher.**
   - **Level shift.** In a network whose only fixed head is one reservoir, with flows fixed by assigned flows (a tree), a scenario raising the liquid level by Δ = 3.7 m leaves every flow equal within 1e-12 m³/s. Every EGL and HGL rises by Δ within 1e-9 m, and every gauge pressure by ρgΔ within 1e-6 Pa.
   - **Fluid temperature.** A `fluid.temperature` scenario's `SolvedState.fluid` equals `fluid_properties` of the base fluid at that temperature (the service behind `POST /fluids/properties`).
   - **Pump off.** In two equal parallel pumps, a scenario turning one off gives the second pump the flow of a single-pump closed-form operating point within D6.

### 7.3 Corpus tool (`tests/differential/scenario_check.py`, new, like `fuzz`/`corpus`)

For every corpus project:
1. **Draw a scenario** with `Random(f"scenario:{name}")`:
   - 1 to 6 overrides, uniform over the (target, field) pairs the project has.
   - Values within the field's bounds, occasionally outside them.
   - Statuses: another literal of the type. Pipes: a neighbouring library size from `data/pipe_materials.json`. Fluid temperatures: ±10 K.
   - 0 to 2 orphaned or not-applicable overrides.
2. **Check:**
   - (a) the effective project and the states equal the patcher's (model and `fields_set`);
   - (b) `solve_case(P, s)` equals `annotate(solve_project(P′), applied)` bit for bit, with errors compared as issue lists;
   - (c) base invariance;
   - (d) for every 20th project with a running pump, the system-curve points are equal.

Exit status 1 on any difference. A pytest smoke test runs the reference cases plus 25 seeds of each fuzz profile.

### 7.4 Web unit and component tests (Vitest)

- **`utils/scenarios.test.ts`:**
  - The mirror on every shared-fixture case.
  - Diff classes: a material change gives one `spec` change; a temperature-only change versus a whole-fluid change; typing the base value back clears the change; topology and locked edits are refused; shared edits reach the base.
  - At a bound, a new change is refused.
  - **Pipe identity property.** Every pipe in a test project gets a distinct length as a marker, and every pipe carries a `spec` change. After each graph edit (`insertComponentInConnection` turned and not turned, `addBranch`, `deleteComponent` with and without `join` and with each side reversed, `removePipe` first, middle and last, `reversePiping`, `disconnect`, `plugPort`), every remaining change targets the pipe with its marker. A removed pipe's change is gone, and a deleted connection's change is kept.
  - The valve-type rule; flow control removed and re-added; the fluid made custom.
  - `newId` never re-uses an override target.
  - Deleting the last scenario removes the key.
- **`state/project.svelte.test.ts`:**
  - Staleness per case.
  - Solve all:
    - which cases are skipped;
    - the order;
    - the snapshot;
    - a per-case error versus a network stop;
    - Cancel mid-run;
    - resuming.
  - Undo and redo switch the case.
  - Per-case system-curve caches.
- **Projects without scenarios:** encoding byte-identical to today's, no `scenarioId` in requests, today's staleness, and no bar, Compare or decorations rendered.
- **`utils/compare.test.ts`:** default rows, differences, the "Same" rule, the relative-percent policy, and missing keys (a run that did not converge, a closed pump without a result).
- **Components:**
  - Field decorations and Reset.
  - Locked fields stay focusable, with their description.
  - The banner and the hidden actions.
  - Manager: create, rename, duplicate, move, delete, and remove orphans.
  - Scenario card; trace block; Compare table and cards; chart overlay data and table.
  - `model-rules.test.ts`: the web reads `x-override-fields`.

### 7.5 End to end (Playwright 1.56.1)

Each flow runs in both projects: `desktop` (1280×800) and `mobile` (390×844). The suite runs with one worker on ports 8010/4183 (`cd apps/web && pnpm test:e2e`). The file is `tests/scenarios.e2e.ts`.

1. Create "Pump B off", set the pump off, see "Changed · Base: On", Reset it, then set it again.
2. A locked elevation is read-only and focusable, and "Switch to base case" works.
3. Solve all over three cases shows progress, Cancel mid-run, then Solve all again solves only the missing cases.
4. Compare shows the differences, as cards on the phone, and "Choose results" adds a row.
5. The pump chart shows the other cases' operating points, and an on-demand system curve with Cancel.
6. Share and reopen: the scenarios are there, and the link opens on the base case.
7. Delete a component a scenario changes: "no longer applies" shows in the manager and in the results card, and undo restores it.
8. Undo from the base case switches to the scenario.
9. A scenario with an invalid value (a maximum speed below the minimum after a base edit) shows the problem in its card and in its solve's error, with Reset to base.

### 7.6 Acceptance (D6, D13)

- The reference suite is green.
- The solver package has no diff, and the corpus comparison against `4ccdf9f` is 0 different with no ignores.
- `scenario_check.py` over the corpus exits 0.
- The three fuzz profiles need no new run for a change outside the solver, but rerunning them is a cheap gate.
- API: `uv run pytest`, ruff, ruff format and mypy strict. Web: `pnpm test`, `pnpm check`, `pnpm lint` and `pnpm test:e2e`.

---

## 8. What changes where

**API (`apps/api`)**

| File | Change |
|---|---|
| `models/scenarios.py` (new) | Override union, `Scenario`, allow-list data, `x-override-fields`, `OverrideResult`, `ScenarioResult`, bounds |
| `models/project.py` | `scenarios` field and the duplicate-id validator |
| `models/piping.py` | `MAX_PIPES` |
| `models/api.py` | `scenarioId` on both requests; `scenario` on both responses |
| `services/scenarios.py` (new) | `apply_scenario`, `annotate`, `solve_case`, `system_curve_case`, the errors |
| `routers/solve.py` | call the case functions; 404 documented for `/solve` |
| `main.py` | four handlers |
| `services/solver/*` | **no change** |
| `tests/unit/test_scenario_models.py`, `test_apply_scenario.py`, `test_scenario_solve.py`, `test_api_scenarios.py`, `test_scenario_cases.py` (new); `test_api_robustness.py` (bounds extended); `test_logging_privacy.py` (a scenario request) | §7.1, §7.2 |
| `tests/fixtures/scenario_cases.py` (new) | generator of the web fixture |
| `tests/differential/scenario_check.py` (new) | §7.3 |

**Web (`apps/web`)**

| File | Change |
|---|---|
| `src/lib/api/openapi.json`, `schema.d.ts` | regenerated by `pnpm gen:types`, never edited |
| `scripts/gen-api-types.sh` | also writes `utils/__fixtures__/scenario-cases.json` |
| `utils/scenarios.ts` (+ test), `utils/compare.ts` (+ test) | new (§6.16, §6.12) |
| `utils/model-rules.ts` | `overrideFields()` |
| `utils/validate.ts` | the scenario structure rules |
| `utils/factory.ts` | `usedIds` includes override targets |
| `utils/labels.ts` | change field labels |
| `utils/results.ts` | changed-row detail |
| `utils/trace.ts` | the case line in `methodsText` |
| `utils/pump-chart.ts` | other cases |
| `api/client.ts` | `scenarioId` in both bodies; `NetworkError` keeps the error code |
| `state/project.svelte.ts` | `activeCase`, per-case results, curves and keys, `solveAll` and the run state, Cancel of a run, `caseId` on history entries, `carryChanges` on base edits |
| `state/workspace.svelte.ts` | `caseProject` as `project`, edit routing, `changeFor(target, field)`, `inScenario`, `setCase`, undo switching |
| `workspace/ScenarioBar.svelte`, `ScenarioManager.svelte`, `panel/ScenarioBanner.svelte`, `ui/ChangeNote.svelte`, `results/ScenarioCard.svelte`, `CompareView.svelte`, `CompareRowsDialog.svelte` | new |
| `ui/Icon.svelte` | new icons: `layers`, `lock`, `up` |
| `ui/NumberField.svelte`, `SelectField.svelte`, `TextField.svelte` | `change` and `shared` props; read-only via the `fieldMode` context |
| Every form in `panel/forms`, plus `ResistanceField`, `AssignedFlowFields`, `NominalSizeField`, `PipeSegmentForm`, `FittingsEditor`, `PortsEditor`, `PumpCurveEditor`, `ComponentActions`, `ConnectionPanel`, `ComponentPanel` (Name shared, Elevation locked), `PanelNavigator` (empty state) and `DeleteDialog` | scenario-mode behaviour |
| `workspace/FluidSettings.svelte`, `SettingsDialog.svelte` (banner; Site and Solver locked; Units and Description shared), `WorkspaceHeader.svelte`, `Workspace.svelte`, `ShareButton.svelte` | scenario-mode behaviour |
| `results/ResultsPanel.svelte`, `ResultsStateNotice.svelte`, `TraceView.svelte`, `MethodsSummary.svelte`, `PumpsView.svelte`, `PumpChart.svelte` | scenario-mode behaviour |
| `tests/scenarios.e2e.ts` (new) | §7.5 |

**Docs (made by the builders)**

| File | Change |
|---|---|
| `CLAUDE.md` | New D15, "Scenario manager (owner, 2026-10-25)", summarising §1.2. Remove the scenario manager from D5's Deferred list and add it to "In v1". |
| PRD | §2.3 and §3.8 drop "Later"; §2.4's row is marked built. |
| SDD | §3.2.1 (`scenarioId`, 404); §4.1 (`scenarios`); §4.12 (these models, replacing the nested target); §4.13 (goal seek reuses the allow-list); §5.1 (the `x-override-fields` row, response fields) |
| TSD | §5.7 (`services/scenarios.py` as §4, `apply_scenario` returning the applied record); §6 or §3.1 (the web's case model); §10 (the tests and the tool); §12 (open item 4 moves to the decided list as item 10) |

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| **Pipe changes rely on identity.** A future edit function that rebuilds pipe objects instead of moving them would orphan or drop changes. | The marker property test (§7.4) runs every graph edit. An edit that copies a pipe fails it. API users manage indices themselves; only an index beyond the pipes is detected (orphaned). Stable pipe ids remain the alternative if this proves fragile (D14 allows the model change; it would touch every fixture). |
| **Two implementations of applying a scenario.** Python is authoritative; TypeScript is for display and editing. If they drift, a form shows a value other than the one solved. | The generated shared fixture with a staleness test; results always show the server's record. |
| **A setpoint's meaning depends on the valve type, and the API cannot detect a stale override.** | The web removes those overrides on a pressure↔flow change (§6.7). The FCV bound of 100 m³/s catches gross mismatches from API users. |
| **Not applicable treated as a warning may hide an API user's mistake** (a status on a reservoir). | Reported in the response and the methods section, never silent. Reversible to a 400. |
| **Base edits can make a scenario invalid** (a minimum speed above a scenario's maximum speed). | Reported in the manager card, "Inputs to check" and the solve's error, never refused (GOALS §4.6). |
| **The conservative staleness key** marks a scenario out of date after a base edit to a value the scenario overrides. | One extra solve, never a stale result shown as current. Solve all skips current cases. |
| **`ws.project` now means the case's project.** Code that must read or write the stored base must use `ws.store.project` explicitly; a mistake would write scenario values into the base. | Edit routing is in one place, and component tests cover the base-only actions. |
| **Locked-by-default depends on every scenario field getting a `change` prop.** A missed prop makes a value read-only: safe, but a usability bug. | A component test walks every allow-list entry and checks its field is editable in a scenario. |
| **Memory.** Full responses kept per case can reach tens of MB on large networks with 20 scenarios. | The bound of 20, and results dropped with their scenario. |
| **Server load.** Solve all costs up to 21 solves, and overlay system curves about 41 solves each. | Current cases are skipped, requests are sequential, cost hints are shown, overlays are on request only, and a run stops on 429 or 503. |
| **The active case resets to the base on reload.** A user may resume editing in the base believing they are in a scenario. | The bar is always visible, and the banner shows in a scenario. |
| **A sixth header control at 390 px** shrinks the project-name field. | Check with long names and at 360 px in the e2e (mobile project) and by hand. |
| **30 overrides per scenario** may be too few to resize every line of a large network in one scenario. | A reversible bound; a total across scenarios is the alternative if needed. |
| **Comparison maps differ across cases** (a run that did not converge has empty maps; a closed pump has no result). | `utils/compare.ts` treats every key as optional, and the tests cover it. |
| **Not bumping `METHOD_VERSION`** may read as under-labelling scenario results. | The methods section names the scenario and its overrides. A bump is a one-line change. |

---

## 10. As built

The API and the web were built from §1–§9 by two builders, tested by an independent tester who read only this design, the specs, the models and the router (`tests/reference/test_scenarios.py`), and integrated against `4ccdf9f`. The specs record the result (PRD §3.8, SDD §4.12, TSD §5.7, §10, §12 item 10). Where the build departs from this design, each departure is reversible (D14):

**API**

1. Not-applicable messages name the component, as the pump's already did: "reservoir R1 has no status to override" (§3.3 had "a reservoir has no status to override").
2. Duplicate scenario ids are a field validator on `Project.scenarios`, so the error is located at `body.project.scenarios`.
3. An empty `scenarios` is left out of every dump (`exclude_if`). Without it every stored reference case gained `"scenarios": []` and 220 currency tests failed. The OpenAPI schema is unchanged by it.
4. The routers keep today's literal calls for the base (`solve_project`, `system_curve`), not `solve_case(…, None)`, which is still exactly today's solve; an existing test monkeypatches `routers.solve.solve_project`.
5. `Overridable.holder` may be `None` (the target itself), and `unit` may be a function of the target: a control valve's setpoint is Pa(g) for a PRV or PSV and m³/s for an FCV.
6. Texts: a whole-fluid item does not repeat its label ("The fluid: custom fluid 'Brine' (base: …)"); a scenario with no overrides, or none applied, has its own opening sentence; invalid-value issues are sorted by override index; a malformed spec gives `invalid_pipe_spec` without naming the offending key.
7. `scenario_check` compares system curves on every 20th project of the selection that has a running pump (`--curve-every`).

**Web**

8. On the one-row header from 640 to 767 px, Settings and Scenarios show their icons only (the header must fit at 640 px with Cancel's text).
9. Compare's table needs a 28 rem pane, not 30 rem: the results pane at 1280 px is just under 30 rem.
10. Solve all skips a case whose response is current, even when a later solve of it failed with a network error.
11. On the chart, cases that run the pump at one speed share one pump-curve line (labelled with every such case); cases that did not converge are left off.
12. `tests/scenarios.e2e.ts` covers §7.5's nine flows in six tests (flow 2 is in the first, flows 4 and 5 in the second, flow 8 in the fifth), each on the desktop and mobile projects; review added a seventh (a long case name).

**Integration**

- Every change reviewed. The independent reference file (335 tests) and the builders' unit tests pass against the implementation, with no mismatch between them; no test was weakened (the existing response fixtures gained `scenario: null`, which the regenerated types require). One cleanup: the workspace store reuses the project store's `deepFreeze` and `structuralProblems` instead of copies.
- `pnpm gen:types` is stable: `openapi.json`, `schema.d.ts` and `scenario-cases.json` are byte-identical when regenerated.
- Base results unchanged: the corpus (TSD §10.4) solved with `4ccdf9f` and with the working tree, 5,136 projects with system curves, identical 5,136, different 0, no ignores. `scenario_check` over the corpus: 0 different (4,693 solved, 443 with a value both the service and the hand-edited project reject, 120 system curves).

**Review fixes** (after the adversarial review; each with a test that failed before and passes after)

- API: a request-validation location stops at an override's `value` (its keys are the submitter's; past pydantic's recursion limit they were all echoed). A rule of a whole component or pipe is one issue, at the override whose base value clears it, as in the hand-edited project (§4.1), in the API and in the web's `scenarioProblems`. A speed-controlled pump's `speed` is its "maximum speed ratio" in notes and the Scenario section. A fluid's value text gives its properties or property overrides (§5.4).
- Web: Compare's defaults read the stored project's scenarios; failed and not-reached columns show no values, and the notice and the bar's reason tell apart the cases Solve all solves from those with an error to fix first; row headers without results are unavailable with their reason; focus goes to the tab shown. A solve of another case stays visible and cancellable (`ProjectStore.solvingCase`). Solve all stays in place during a run; its progress has its own line, announced once. The results' Solve shows "Solve", with the case in its accessible name. The overlay curves follow the other cases after a switch. Loading another project resets the page state (`ProjectStore.onLoad`). Group notes describe their inputs. The scenario card and the trace's Changed block format values as the project was solved, the block names a pipe's number, and the Pumps and Links tables mark changed rows.
- Docs: TSD §10.1's network count (17), and the continuation prompt's reference to the PRV slow-lag item.
