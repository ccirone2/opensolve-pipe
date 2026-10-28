# Project library: design proposal

**Status: approved** (2026-10-28): the owner accepted every recommendation of §10 ("Go with your recommendations and build it"); this is the design the build follows, CLAUDE.md D21 once built. It was written against `f0a1f2f` (the condenser water example; `main` at `b7f09eb`) by one designer: the claims about the code were read in it, and every number in §1.2 and §7 was measured by the prototype in Appendix A. §10 lists the product questions; where the owner does not answer one, the recommended default stands, and every web choice is a designer's default, reversible under D14.

**The owner's request (2026-10-28):** "This has identified a real gap for piping and valves larger than the libraries provide. Make an informed suggestion on how to include customized elements and pipes definitions." The gap showed while building the condenser water example (90,000 gpm): steel pipe stops at NPS 48 in the cited library, Crane's butterfly valve table at NPS 24, and the example had to be laid out around both limits (pumps and chillers alternating along an NPS 42 header, every butterfly valve NPS 24 at most).

The constraints taken as binding:
- D1–D18. In particular D8 (cited data only, generated from `fluids`), D10 (traceability, privacy), D13 (same answer), D14 (nothing released, `schemaVersion` stays 1), D15 (scenario allow-list), D16 (goal-seek variables) and D18's rule that a K means nothing without its bore.
- One verified slice; anything bigger goes in §9.
- The change touches the API, so it does not go on a `web/` branch (CLAUDE.md, Tooling).

**Sources read:**
- **Specs:** GOALS §3, §4.1, §4.2; PRD §3.1, §3.8; SDD §4.3, §4.12; TSD §4 (pipe data, line 392), §12; CLAUDE.md D1–D18.
- **API code:** `models/{piping,components,project,pumps,scenarios}.py`; `services/solver/{library,fittings,valves,builder}.py`; `data/{pipe_materials,fittings}.json`.
- **Web code:** `components/panel/{PipeSegmentForm,ResistanceField,FittingsEditor}.svelte`; `utils/{edit,factory,piping,scenarios,validate}.ts`; `state/library.svelte.ts`; the files that read `materialId`, `innerDiameter`, `resistance` or `kOverride` (§8).
- **fluids 1.3.1:** `fluids.piping` (the `NPS*` tables), `fluids.friction.roughness_Farshad` (source and coefficients), `fluids.fittings.Cv_to_K`.

**Test inputs.** The 60,000 Cv, the K of 0.30 at 0.7366 m and every rating in Appendix A are made-up inputs, not data for a real valve.

---

## 1. Scope and decisions

### 1.1 The gap

The tool already accepts user values in place of library data, one element at a time:

| Need | Supported today | What is missing |
|---|---|---|
| A pipe the library lacks | A **custom pipe** (`materialId: "custom"`, `innerDiameter`, `roughness`), or a library pipe with an `innerDiameter` or `roughness` override (`library.resolve_pipe`) | Set on every pipe segment separately: the example's 48" headers would need the same values typed on about 30 segments, and edited on each of them. The trace labels the values `user`, with nowhere to say where they came from (`USER_SOURCE`). |
| A valve outside its correlation | A valve **`resistance`** (K, Cv or Kv), which replaces the Crane default and its range flag (`valves.valve_resistance`) | The same: one value per valve (six identical cell valves, six copies), and no source. A K is taken on the valve's inlet pipe, so a datasheet K stated at another bore cannot be entered as published. |
| An inline fitting outside its correlation | A fitting **`kOverride`** (`fittings.py`) | A K on the pipe it sits in, with no bore of its own and no source. |
| Cited data for larger sizes | — | `fluids.piping` stops at NPS 48 for steel (STD, XS) and NPS 36 for schedules 10–40, and the data script reads only `fluids` (D8). |

So the gap is not the values themselves but **reuse and provenance**. An engineer with a datasheet has to enter its value on every element it applies to, keep the copies in step by hand, and cannot record which datasheet it came from.

The correlation limits are real, and their flags stay. Crane's butterfly valve K is tabulated for NPS 2–24 only, so a 30" valve is flagged, rightly. The fix for a 30" valve is its manufacturer's Cv, not a loosened flag. The Crane tee correlations have no size limit; only the Darby 3-K fallback for patterns Crane does not cover stops at NPS 36 (`branches.py`), and that is a flag about the pattern, not the size.

### 1.2 What works today (measured, Appendix A)

These follow from the code as it is and are worth stating in the docs whatever the owner decides:

- **A larger steel pipe with cited roughness.** A library material with a user `innerDiameter` and no `roughness` takes the Farshad roughness evaluated at that bore (`resolve_pipe`, last branch). NPS 60 STD (inner diameter 59.25 in, 1.50495 m) on carbon steel resolves to ε = 3.397×10⁻⁵ m, labelled "evaluated at the user inner diameter 1.50495 m" (P2). At 90,000 gpm that pipe runs at 3.19 m/s, against 5.02 m/s in NPS 48 STD. Only the bore is unsourced: the trace says `user`.
- **A large valve without a flag.** A 30" cell valve with no resistance raises `CORRELATION_OUT_OF_RANGE` (Crane's table stops at NPS 24); with a Cv of 60,000 it raises none (P5).
- **A custom pipe changes nothing but the label.** Every library pipe of the condenser example replaced by a custom pipe holding the resolved bore and roughness: 258 flows and heads, 0 different, bit for bit (P1). This is what makes §3's proof cheap.

### 1.3 Decisions

1. **A project library of named, sourced definitions, referred to by id**, on the precedent of `pumpLibrary` and `Pump.curveId`: two new lists on `Project`, `pipeLibrary` (pipe specs) and `resistanceLibrary` (K, Cv or Kv entries). A pipe segment refers to a spec with `specId`; a valve's `resistance` and a fitting's override can refer to an entry. Editing an entry changes every element that refers to it. *(Usability without trading correctness: one value, one place.)*
2. **Every entry has a required `source`** (free text, 1–300 characters), shown in every trace that uses it and in the methods summary. *(GOALS §4.1: user data is allowed when labelled as such; §4.2: a value is traceable only if its origin is stated.)*
3. **A K entry carries the bore it is stated at** (`referenceDiameter`, required for K, absent for Cv and Kv), and the solver moves it to the bore it is used on with K = K₀ (D/d₀)⁴, the same constant head loss at a given flow (P3). A Cv or Kv needs no bore: `Cv_to_K` already scales as D⁴ (P3). *(D18: a K means nothing without its bore.)*
4. **The solver does not change.** References are resolved to the values the solver takes today before any solve, outside `services/solver/` except for the source labels (§3). A project that uses the library solves bit-identically to the same project with the values typed in by hand. *(GOALS §3: correctness is proven, not argued.)*
5. **A project without a library is unchanged**: both lists are omitted when empty (`exclude_if`, as `scenarios`), so its serialization, link, solve, trace and methods text are byte-identical. *(D13, D14.)*
6. **No new flags, and the existing ones stay.** A spec's bore or a datasheet K far from the pipe it is used on has no cited threshold (D18 decided the same for a flow far from a rating). The out-of-range flag text gains a pointer to the library (§4.3).
7. **The cited library grows only from sources that can be checked** (§9.1): the project library is the general answer, and data the owner cannot verify against a standard does not go into `data/`.

### 1.4 Alternatives considered

- **Templates instead of references** (an entry is a preset; applying it copies its values onto the element, with a note). Smaller: no model change outside the entries, nothing to resolve. Rejected as the default because an edit to the datasheet value would not reach the copies, which is the failure the user hit, and because the copies lose their provenance as soon as one is edited. §10 Q1 puts the choice to the owner.
- **A `source` field on every inline user value** (custom pipe, `resistance`, `kOverride`). Cheap, and fixes provenance, but not reuse. It can come later on its own (§9.2).
- **Raising the correlation limits** (extrapolating Crane's butterfly table, or Darby's tee beyond NPS 36). Rejected: GOALS §4.1, no uncited K.
- **References to shorten links.** Not a reason: gzip already removes the repetition. The condenser example encodes to 4,752 characters with library pipes, 4,860 with a custom pipe on every segment, and 4,822 with its 5 distinct specs referenced by id (P4, Python's gzip; the web's pako gives about the same). A library costs a few dozen characters per entry and saves nothing measurable.

---

## 2. Model and API

### 2.1 Pipe specs (`models/library.py`, new; `models/piping.py`; `models/project.py`)

```python
class PipeSpec(CamelModel):
    """A pipe size the user defines once and refers to from any pipe segment."""
    id: Identifier
    name: Name                                   # e.g. "NPS 60 STD carbon steel"
    source: str = Field(min_length=1, max_length=300)
    material_id: str                             # a library material or "custom"
    inner_diameter: float = Field(gt=0, le=10.0)
    roughness: float | None = Field(default=None, ge=0, le=0.1)
    outer_diameter: float | None = Field(default=None, gt=0, le=10.0)   # display only
    nominal_size: float | None = Field(default=None, gt=0, le=10.0)     # display, port sizes

    # validator: "custom" needs roughness; a library material without roughness takes its
    # Farshad roughness at inner_diameter (resolve_pipe's existing branch); outer_diameter,
    # when given, exceeds inner_diameter.
```

- `PipeDefinition` gains `spec_id: Identifier | None`. With it, `material_id`, `schedule`, `nominal_size`, `inner_diameter` and `roughness` must be absent (`material_id` becomes optional for that case only); without it, the rules are today's. Only `length` sits beside a spec.
- `Project.pipe_library: list[PipeSpec] = Field(default_factory=list, max_length=100, exclude_if=...)`; ids unique among themselves and against every other project id (as pump curves, scenarios).
- A spec on a library material keeps that material's cited roughness, so the `source` describes only the bore ("ASME B36.10M-2004, NPS 60 STD: 60 in OD, 0.375 in wall"). A custom spec's `source` covers both.

### 2.2 Resistance entries

```python
class ResistanceSpec(CamelModel):
    """A loss coefficient from a datasheet, referred to by valves and fittings."""
    id: Identifier
    name: Name                                   # e.g. "30 in butterfly valve, fully open"
    source: str = Field(min_length=1, max_length=300)
    kind: Literal["K", "Cv", "Kv"]
    value: float = Field(gt=0, le=1.0e7)         # stored as entered, as FlowCoefficient
    reference_diameter: float | None = Field(default=None, gt=0, le=10.0)  # m; K only

    # validator: reference_diameter required for K, absent for Cv and Kv.
```

- `FlowCoefficient` stays; a valve's `resistance` becomes `FlowCoefficient | ResistanceRef`, with `ResistanceRef = {kind: "library", id}`. The union is on `kind`, so existing values keep their meaning.
- `Fitting` gains `resistance_id: Identifier | None`, exclusive with `k_override`; a `custom` fitting needs one of the two.
- `Project.resistance_library: list[ResistanceSpec]` (≤ 100, omitted when empty), ids unique as above.
- Equipment keeps its own `rating` (D18): a rating is the element's datasheet, not a shared part. §9.3.

### 2.3 Errors

- A reference to an entry that does not exist is a topology issue, `UNKNOWN_PIPE_SPEC` or `UNKNOWN_RESISTANCE`, listed with the others (422), as `UNKNOWN_PUMP_CURVE` is today (`builder.py`). It names the element and the id.
- Entry validation errors are 400 `VALIDATION_ERROR` and never echo the submitted values (D10). Names and sources are submitted text: a topology issue or trace names an entry by id only in error messages; traces, which go only to the requester, show its name and source.
- No new `x-` extension where JSON Schema can state the rule (bounds, `required`, `oneOf`). If the generated schema cannot state that `specId` excludes the other spec fields, a published extension in the pattern of `x-ordered-fields` is the fallback: a builder's call, not a product question.

### 2.4 Versions

- `schemaVersion` stays 1 (additive, D14).
- `METHOD_VERSION` 1.5.0 for the K-at-a-stated-bore conversion (`main` took 1.4.0 for the orifice plate, D20, after this proposal was written), which is a new calculation; its changelog line says that projects without a project library are unchanged in every value, trace and message (§7.3). §10 Q5.

---

## 3. Resolution and solver

### 3.1 `apply_library` (`services/library_refs.py`, new; outside `services/solver/`)

Called by the routers before `solve_project`, after `apply_scenario` (so a scenario may switch a pipe to a spec, §5.1). It returns a project in which:
- every `spec_id` segment holds the spec's `material_id`, `inner_diameter` and `roughness` (when set) and its own `length`: exactly the custom or bore-override pipe a user could have typed (P1 shows that pipe solves identically);
- every `ResistanceRef` and fitting `resistance_id` holds an inline coefficient on the element's own reference bore: a Cv or Kv as entered, a K as K₀ (D/d₀)⁴, D the bore the solver uses for that element (a valve's inlet end segment, a fitting's `pipeIndex` segment, both known only after the pipes resolve, so pipe specs resolve first);
- a side table maps each element, pipe and fitting to the entry it came from, for the labels (§4).

The project the solver sees therefore contains only today's fields, and nothing in `gga.py`, `status.py`, `network.py` or `system_curve.py` changes. `/solve`, `/system-curve` and `/goal-seek` all call it, so every path sees the same values.

### 3.2 The labels (`services/solver/library.py`, `fittings.py`, `valves.py`)

The one change inside `services/solver/` is text: `resolve_pipe`, `valve_resistance` and the fitting resolver accept an optional label for a value that came from the library and use it instead of `user`. Numbers are not touched, and a project without a library passes no labels, so its traces are byte-identical (§7.3).

### 3.3 The K conversion

For a K entry stated at d₀ and used at D, K = K₀ (D/d₀)⁴. At flow Q the head loss is K₀ (Q/A₀)²/2g on either basis: measured equal to 1.8×10⁻¹⁶ relative (P3, K₀ = 0.30 at 0.7366 m moved to 0.74294 m). This is the same reasoning D18 used to make an equipment item's Cv independent of the pipe, and the same scaling `fluids.fittings.Cv_to_K` applies (P3: its ratio between the two bores equals (D/d₀)⁴ to 15 digits).

---

## 4. Traceability

### 4.1 Traces

- A pipe from a spec: the inputs keep `source: "user"` (D10's source labels are unchanged), and their notes read `project library pipe spec "<name>" (<id>): <source>` for the bore, and the same or the material's cited roughness source for the roughness. The trace states the spec's nominal size when given.
- A valve or fitting from an entry: `project library resistance "<name>" (<id>): <source>`, the value as entered, and for a K the conversion K = K₀ (D/d₀)⁴ with both bores and the result; for a Cv or Kv the existing ISA-75.01.01 conversion text.

### 4.2 Methods summary

A "Project library" section after the pipe-data section, only when an entry is used: each entry used, with its source, and one sentence on each conversion. An entry no element uses is listed under "not used", so a reader sees the whole library a result was solved with.

### 4.3 Flags

None added. The text of a Crane default's `CORRELATION_OUT_OF_RANGE` gains one clause: "enter the manufacturer's coefficient as a resistance, or in the project library". The flag still fires; only the advice is new.

---

## 5. Scenarios, goal seek, Compare and export

### 5.1 Scenarios (D15)

- **Pipe `spec`.** `PIPE_SPEC_KEYS` gains `spec_id`, so a scenario's spec change can switch a pipe to or from a library spec as one value, as it now switches material, schedule and size together.
- **Valve `resistance`.** The value may be a `ResistanceRef`, so a scenario can point a valve at another entry ("dirty strainer", "throttled").
- **The entries themselves are not targets in this slice.** A scenario that changes a spec's bore everywhere ("headers at NPS 54") is where references pay off most in what-if studies, but it needs a new target kind (`{kind: "library", entryId}`) through the allow-list, the patcher, the web's change notes and Compare. §10 Q4 recommends it as the next slice.
- An override on a pipe or valve whose entry is deleted in the base is not orphaned (the element still exists); the entry reference becomes the topology issue of §2.3, as for the base.

### 5.2 Goal seek (D16)

A valve's `resistance` stays a goal-seek variable as one coefficient. On a valve that refers to an entry, the search writes an inline coefficient of the variable's kind (the reported `override` replaces the reference, and the result says so); the start is the entry's value when its kind matches, else today's rule (the middle of the bounds on the log scale). Entries are not variables in this slice (§9.4).

### 5.3 Compare and export (D17)

- Compare reads results, which do not change form: nothing to do.
- Export: a "Project library" sheet (every entry, its source and where it is used) in a file whose case uses one, and a Spec column in the pipe and fitting tables. About gains one line naming it.

---

## 6. Web

### 6.1 The library dialog

A **Library** dialog (`workspace/ProjectLibrary.svelte`, new), opened from the Project toolbar next to Fluid and from every picker that can use an entry. Two tabs, Pipe specs and Resistances; each entry shows its name, values in display units, source and "Used by N". A spec's form has the material (library or Custom), inner diameter, roughness (shown resolved, "Farshad at this bore" when blank on a library material), optional outer diameter and nominal size, and the source. A resistance's form reuses `ResistanceField` with the reference diameter shown for K. Delete is refused while an element uses the entry, as `removePumpCurve` refuses today, naming the first user; ids come from `newId` with prefixes `PS` and `RS` and are never reused.

### 6.2 Using an entry

- **Pipe segment form.** The material select gains a "Project specs" group; choosing one shows its values read-only with "Edit in the library".
- **Valve forms** (`IsolationValveForm`, `CheckValveForm`, `ControlValveForm`) and the **fittings editor**: the resistance field gains "From the project library", a select of entries.
- **Apply to many** ("Use this spec for…"): this pipe; every pipe of the same material, schedule and size; or every pipe on the current connection. One undo step, with a confirmation listing the count. This is the action that fixes the condenser example's 30 identical edits.
- **From a flag.** A `CORRELATION_OUT_OF_RANGE` on a Crane default offers "Enter a datasheet value", opening the resistance form for that valve with the library option.

### 6.3 In a scenario

Library entries are base data: the dialog is read-only in a scenario (as names and descriptions are shared). A pipe's spec and a valve's resistance stay editable in a scenario as today, now with the library options (§5.1).

### 6.4 Elsewhere

The trace view shows the library notes of §4.1 with a link that opens the entry; the "Changed by this scenario" notes name entries by name. Every view works at 390 px (GOALS §4.7).

---

## 7. Verification

### 7.1 Reference cases (`tests/reference/test_project_library.py`, by a tester who does not read `services/`)

1. **A spec equals the pipe it stands for.** For a cited size, a spec holding its bore and roughness, referenced by every pipe of a network: every solved value bit-identical to the library pipes (P1's metamorphic check, kept as a test).
2. **NPS 60 by hand.** One pipe between two reservoirs on an NPS 60 STD spec (B36.10M bore, carbon steel, roughness blank): the flow from Darcy–Weisbach and Colebrook in closed form, ε from Farshad at that bore.
3. **K at a stated bore.** A valve on an entry K₀ = 0.30 at d₀ ≠ D: the head loss K₀ (Q/A₀)²/2g in closed form; and the same valve with an inline K₀ (D/d₀)⁴: bit-identical.
4. **Cv and Kv entries** equal the same coefficients typed inline, bit for bit, on a valve and on a fitting.
5. **Errors.** A dangling `specId` or resistance id is 422 with the other topology issues; a K entry without a bore and a Cv entry with one are 400, values not echoed.
6. **Scenario and goal seek.** A scenario switching a pipe to a spec equals the hand-edited project bit for bit; a goal seek on a valve that refers to an entry reports an `override` that, applied and solved, gives the same state bit for bit.

### 7.2 Independent checks

- `tests/differential/library_check.py` (new, as `equipment_check.py`): for every corpus project, lift each distinct pipe definition into a spec holding its resolved bore and roughness and refer to it from every segment that uses it; lift every valve resistance and fitting `kOverride` into an entry (a K with the bore of its element). Target: 0 different over the whole corpus.
- A second, independent resolver in the test (not `apply_library`) for the unit tests, as the scenario manager's second patcher.

### 7.3 Acceptance (D6, D13)

- The reference suite green.
- The corpus comparison against the commit before the change: every project identical, no ignores (both lists are omitted when empty, so the request bodies themselves are identical).
- The three fuzz profiles give the same records; `scenario_check` and `goal_seek_check` 0 different and 0 violations.

### 7.4 Web tests

Unit tests for the edits (apply to many, delete refused while used, a Cv↔Kv entry change), a shared fixture generated by the real `apply_library` for any client-side mirror, and `project-library` e2e flows on desktop and phone: create a spec, apply it to every NPS 48 pipe of the condenser example, solve, find the source in the trace.

---

## 8. Files to change

- **API models:** `models/library.py` (new: `PipeSpec`, `ResistanceSpec`, `ResistanceRef`), `models/piping.py` (`spec_id`, `resistance_id`), `models/components.py` (the `resistance` union), `models/project.py` (the two lists, id checks), `models/scenarios.py` (`PIPE_SPEC_KEYS`).
- **API services:** `services/library_refs.py` (new), the three routers that solve, `services/goal_seek.py` (§5.2), `services/solver/{library,valves,fittings,builder,trace,methods,version}.py` (labels, topology issues, the methods section, `METHOD_VERSION`).
- **API tests:** §7.1–§7.3; `test_released_links.py` unchanged (no stored link uses a library).
- **Web:** `workspace/ProjectLibrary.svelte` (new); `panel/{PipeSegmentForm,ResistanceField,FittingsEditor}.svelte`; `panel/forms/{IsolationValve,CheckValve,ControlValve}Form.svelte`; `utils/{edit,factory,piping,scenarios,validate,results,goal-seek,issue-text,flag-text}.ts`; `utils/export/tables.ts`; `state/library.svelte.ts`; the generated `api/openapi.json` and `schema.d.ts`.
- **Specs:** PRD §3.1 (pipe and valve data entry), SDD §4.3 and a new §4.17, TSD §4 (line 392's custom-pipe text) and §12, and D21 in CLAUDE.md (D19 and D20 were taken by design checks and the orifice plate).
- **The condenser water example**, after the feature: NPS 60 STD headers from a spec, and NPS 30 cell valves with an illustrative datasheet Cv (labelled as such), so it no longer has to be laid out around the library's limits.

---

## 9. Later

### 9.1 Growing the cited library

Each item is the owner's call under D8, and none is needed for the project library:
- **Steel beyond NPS 48.** ASME B36.10M lists larger sizes than `fluids` carries. Adding them means transcribing the standard's table into `data/` with the script reading it, a departure from D8's "generated from `fluids`", and someone holding the standard to check it.
- **HDPE.** `fluids` has ASTM F2619 dimensions to NPS 65 (and PVC to NPS 60 in ASTM F679, NPS 48 in AWWA C905). TSD §4 leaves HDPE out for lack of a cited roughness, while the library's PVC already takes Farshad's "Plastic coated" surface. Whether that surface may stand for HDPE too is a sourcing question, not a code one.
- **Ductile iron, cement-lined.** Farshad has a "Cement lining" surface; `fluids` has no AWWA C151 dimensions, so the bores would need the same transcription as large steel.

### 9.2 A `source` on inline values

An optional `source` on a custom pipe, a `resistance` and a `kOverride`, for one-off values that do not belong in the library.

### 9.3 Equipment ratings from the library

An equipment item could refer to a shared rating (six identical strainers). D18 keeps the rating on the element; this would follow the same pattern as §2.2 if asked for.

### 9.4 Entries as scenario targets and goal-seek variables

§5.1 and §10 Q4: a scenario or a goal seek on an entry's bore, roughness or value, applied everywhere it is used.

### 9.5 Sharing a library between projects

Import an entry list from another project's link, or from a file. The link format keeps each project self-contained (D3), so this is a copy, not a shared reference.

---

## 10. Questions for the owner

**The owner's answers (2026-10-28):** "Go with your recommendations and build it": Q1 references; Q2 `source` required, 1–300 characters; Q3 no growth of the cited library in this slice; Q4 entries as scenario targets in the next slice, not this one; Q5 a new `METHOD_VERSION`, 1.5.0 (D20 took 1.4.0 meanwhile); Q6 the condenser water example rebuilt on the library.

**Since this was written,** `main` gained the design checks (D19) and the orifice plate (D20). Neither changes this design: design checks read solved results, and the orifice plate takes no K, Cv or Kv (D20, owner), so it does not refer to resistance entries.


1. **References or templates?** References (an edit reaches every user, §1.3 decision 1) or templates (entries copy their values onto the element, §1.4). *Recommended: references.*
2. **Is the `source` required?** Required makes every result traceable, at the cost of a moment's typing on a quick what-if. *Recommended: required, 1–300 characters.*
3. **Grow the cited library now?** Large steel from ASME B36.10M (§9.1), and HDPE on Farshad's plastic surface. *Recommended: not in this slice; the project library covers both, and each addition needs someone to verify the source.*
4. **Entries as scenario targets** ("headers at NPS 54" as one change)? *Recommended: the next slice, after this one is in use.*
5. **`METHOD_VERSION` 1.5.0** (1.4.0 when asked; D20 has since taken it) for the K-at-a-stated-bore conversion, with a changelog line that projects without a library are unchanged? *Recommended: yes, as D18 did for equipment.*
6. **Update the condenser water example** to use the library once built (§8)? *Recommended: yes.*

---

## Appendix A. Prototype

`library-proto/proto.py` in the session scratchpad (not committed, like the other proposals' prototypes), run from `apps/api` with `uv run` against the condenser water example at `f0a1f2f`. Its output:

```
P1 converged True True values 258 bitwise different 0
P2 60in STD bore 1.50495 roughness 3.3970946136682965e-05 | user | ...; evaluated at the user inner diameter 1.50495 m
P2 velocity 90k gpm in 60in STD 3.1920549932293305 m/s; in 48in STD 5.021060402336833
P3 h at d0 0.0760170782431179 h at D 0.07601707824311789 rel diff 1.825614470925928e-16
P3 Cv_to_K scales as D^4: 1.0348755055391234 1.034875505539123
P4 link chars (approx., python gzip): library pipes 4752 | custom on every pipe 4860 | specs by id 4822 | distinct specs 5
P5 Cv None flags [('CORRELATION_OUT_OF_RANGE', 'IV1')]
P5 Cv 60000.0 flags []
```

- **P1:** every library pipe replaced by a custom pipe holding `resolve_pipe`'s bore and roughness; `solve_project` on both; every link flow and node result compared with `!=`.
- **P2:** `resolve_pipe` on `{materialId: carbon_steel, innerDiameter: 59.25 × 0.0254}`.
- **P3:** the head loss of K₀ = 0.30 at 0.7366 m and of K₀ (D/d₀)⁴ at 0.74294 m, both at Q = 0.95 m³/s; and `fluids.fittings.Cv_to_K(60000, D)` at both bores.
- **P4:** canonical JSON (sorted keys, no spaces) → gzip level 9 → base64url without padding, for the example as built, with a custom pipe on every segment, and with its 5 distinct (material, schedule, size) pipes lifted into specs.
- **P5:** cell 1's valve and its two connections at NPS 30 (the 24 in pipes of those connections at 30 in), without and with a `resistance` of Cv 60,000.
