# Project library: design proposal

**Status: built** (2026-10-28; CLAUDE.md D21; §12 records where the build departs from this design). The owner accepted every recommendation of §10 on 2026-10-28 ("Go with your recommendations and build it"). It was written against `f0a1f2f` (the condenser water example; `main` at `b7f09eb`) by one designer: the claims about the code were read in it, and every number in §1.2 and §7 was measured by the prototype in Appendix A. §10 lists the product questions; where the owner does not answer one, the recommended default stands, and every web choice is a designer's default, reversible under D14.

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
- `Project.pipe_library: list[PipeSpec] = Field(default_factory=list, max_length=100, exclude_if=...)`; ids unique among themselves and against every other project id (as pump curves, scenarios). *[Correction, as built (§12 item 2): the API checks neither pump-curve ids nor scenario ids against other ids; pump-curve ids are unique among themselves (`DUPLICATE_PUMP_CURVE_ID`) and scenario ids are their own namespace. Entry ids are unique within each list.]*
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
- The corpus comparison against the commit before the change: every project identical, no ignores (both lists are omitted when empty, so the request bodies themselves are identical). *[Correction, as built (§12, Proof): §2.4's `METHOD_VERSION` 1.5.0 changes the two method-version paths of every solved state, so the comparison leaves those two out, and nothing else.]*
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

## 12. As built

The library was built from §1–§10 on `2723d3c` (this design with the owner's answers, on `main` with design checks, D19, and the orifice plate, D20, merged) and committed as `938851d`, with the integration changes after it. This design had no review stage, so it has no §11; the section is numbered as the other designs' as-built records are. The decision is **D21**; its specs are PRD §3.1.5, SDD §4.17 and TSD §4.11. A contract builder wrote the models and published rules; an API builder the resolution, topology issues, traces, methods text, version and the scenario and goal-seek services (`tests/unit/test_project_library.py`, 45 tests, beside the contract's `test_project_library_models.py`); a reference tester who did not read `services/` or the API builder's tests wrote `tests/reference/test_project_library.py` and `derivations_project_library.py`; a corpus-tool author `tests/differential/library_check.py` and its smoke test; a web model builder `utils/project-library.ts` and the model, validation, scenario, goal-seek, text and export changes; a web UI builder the dialog, forms, results and e2e flows; an example builder the condenser water example; integrators the validation locations, the reference helpers and the scenario reference draws; and a gate runner every gate below.

Where the build departs from this design, each departure is reversible (D14), and none weakens a rule of the design:

**Contract**

1. **`models/project_library.py`, not `models/library.py`** (§2.1, §8): `models/library.py` already describes the cited catalog the API serves (`GET /api/v1/library`), and the new module's docstring says which is which. `FLOW_COEFFICIENT_MAX` moved to `models/base.py`: `components.py` imports `project_library` for `ResistanceRef`, and an entry's value needs the same bound as a valve's coefficient.
2. **Ids are unique within each list** (§2.1 asked for uniqueness against every other project id): one model validator per list (400, by index only, "pipe specs 0 and 2 have the same id"), as scenario ids are their own namespace. Every reference names its list, so the API resolves each in its own: a pipe spec and a resistance entry that share an id each resolve correctly (`test_an_id_in_both_lists_resolves_in_its_own`, which would also accept a 400). The web keeps one namespace for the ids it gives (`factory.usedIds`, with the prefixes `PS` and `RS`), so a new entry never takes an id in use, and reports duplicate entry ids as the API would. §2.1's "as pump curves, scenarios" was not so in the code and is marked there.
3. **A source needs a character that is not white space** (the pattern `\S`) besides its 1–300 characters: a blank source states no origin (answer 2). It is JSON Schema, so Ajv enforces it in the browser too.
4. **Two published extensions** (§2.3 hoped for none): `x-fields-by-value` on `PipeSpec` (a custom spec needs `roughness`) and `ResistanceSpec` (a K needs `referenceDiameter`, a Cv or Kv takes none), and `x-reference-fields` on `PipeDefinition` (`specId` replaces `materialId`, `schedule`, `nominalSize`, `innerDiameter` and `roughness`; `materialId` is required without it) and `Fitting` (`resistanceId` replaces `kOverride`); a spec's outer diameter above its inner reuses `x-ordered-fields`. JSON Schema's own `not` and `if`/`then` would have made the web refuse such a link as a schema problem, where a model-rule problem opens and is flagged (SDD §5.2). `x-required-parameters` is unchanged (`custom: [kOverride]`): `resistanceId` meets it through `x-reference-fields`. The validators and the extensions are generated from the same class variables and tables, and `test_schema_rules.py` checks each extension against its validator both ways.
5. **`ResistanceSpec` is one model with a validator**, not a union by kind. `PIPE_SPEC_KEYS` is `(*SPEC_FIELDS, "spec_id")`, `spec_id` last, because `services/scenarios.py` builds `invalid_pipe_spec`'s message from the first key. `material_id` is optional on `PipeDefinition` and dumps as null beside a `spec_id`, like its sibling fields, so a dump validates again; `spec_id` and `resistance_id` are left out of every dump when absent.
6. **The valve resistance union** (`ValveResistance` in `models/components.py`: `FlowCoefficient` tagged `coefficient`, `ResistanceRef` tagged `library`) has a callable discriminator with the custom error `invalid_resistance`, "unknown resistance kind (expected 'K', 'Cv', 'Kv' or 'library')", as the equipment rating's, so an unknown kind is never quoted. Its validation locations are item 32.
7. **The contract changed no serialization:** every project the repository held, 5,420 (the 5,168 corpus items and 252 JSON fixture projects), dumped three ways (`model_dump_json`, `model_dump(mode="json")` and with `exclude_unset`) before and after the change: 0 different.

**API**

8. **No `apply_library` and no `services/library_refs.py`** (§3.1, §8): references resolve inside the network build, where library data is resolved today: `library.resolve_pipe(pipe, specs)` resolves a `specId` pipe as the pipe the spec stands for (`project_library.spec_pipe`: material, bore, roughness when given, the segment's length) through the same code as a typed pipe; `valves.valve_resistance(valve, d_ref, entries)` and `fittings.resolve_fitting(…, entries)` take an entry's K on the element's bore; `builder.validate_topology` reports dangling references. Every path that solves (`/solve`, `/system-curve`, scenarios, goal seek, design checks, the corpus tools) takes them with no extra call, and the routers are unchanged; a pre-solve rewrite would have had to be called on each of those paths and to carry §3.1's side table for the labels. The numbers are still exactly the hand-typed project's (proven by the unit, reference and corpus twins below), and `gga.py`, `status.py`, `network.py` and `system_curve.py` are unchanged. The lookups, conversion and texts are in `services/solver/project_library.py`; `k_from_coefficient` moved unchanged into a new leaf module, `coefficients.py`, beside `k_at_bore`, to break the import cycle fittings → project library → valves → fittings (`valves.py` still imports it; `equipment.py`'s trace text, "via valves.k_from_coefficient", is kept so that traces without a library stay byte-identical).
9. **The labels** (§3.2): input sources stay `user`, and a spec pipe's `diameter_source` stays `user`; the provenance goes into the data sources ("Pipe N inner diameter", and "Pipe N roughness" when the spec gives one) and one note per pipe, as §4.1 says. A blank roughness keeps `resolve_pipe`'s Farshad text ("evaluated at the user inner diameter … m"), the same code path as the twin's. A pipe's trace gains the input "Pipe N pipe spec" (`"<name>" (<id>)`) and its nominal diameter from the spec.
10. **K = K₀ (D/d₀)⁴ is written exactly `k0 * (d / d0) ** 4`** (`coefficients.k_at_bore`): D = d₀ gives K₀ bit for bit, and a tester's natural Python expression gives the same double. `library_check`'s twin check holds the API to it: a reordering, `k0*d**4/d0**4`, or a K one unit in the last place off is reported (item 20).
11. **`FittingResult.source`** of a fitting on an entry is the provenance, `project library resistance "<name>" (<id>): <source>`, where a `kOverride` gives `user`: a free-text citation field, so traceability argues for the provenance. With the traces of the elements on entries and the methods section, it is all that differs from the hand-typed twin; the traces differ in inputs, equations, correlations, data sources and notes, their intermediates equal.
12. **The methods section appears whenever the project has a library** (§4.2 said only when an entry is used), with an unused entry "not used by any element", so a reader sees the whole library a result was solved with, as §4.2 intends. It sits between "Pipe friction" and "Minor losses" and lists each element that uses an entry with the K and bore it takes; its references are D21 and, when a Cv or Kv entry is used, ISA-75.01.01.
13. **§4.3's advice is the web's, not the server's.** The server's `CORRELATION_OUT_OF_RANGE` message is unchanged, because §2.4 and §7.3 promise that no message of a project without a library changes, which the corpus comparison checks. `utils/flag-text.ts` ends a valve's Crane-default range flag (one with `details.referenceDiameter`) with "Enter the manufacturer's coefficient as a resistance, or in the project library." and an inline fitting's Crane range flag with "Enter the manufacturer's coefficient as its K, or in the project library."; not a fitting's laminar flag, since an entered coefficient is no more valid in laminar flow.
14. **Errors** (§2.3): `UNKNOWN_RESISTANCE` and `UNKNOWN_PIPE_SPEC` right after `UNKNOWN_PUMP_CURVE` (valves first, in component order, then each connection's pipes and fittings; a dangling spec is not reported twice). A spec on an unknown material is `UNKNOWN_PIPE_MATERIAL` at each pipe that uses it, its message starting "pipe spec 'PSn':"; an unused one raises nothing. An entry the solver cannot represent is a 422, not a 500: `VALVE_RESISTANCE_OUT_OF_RANGE` with a message for entries ("valve 'V1': its project library resistance entry 'RS1', K 0.3 at 1e-91 m, on the inlet pipe's inner diameter of 0.1 m gives a loss coefficient that is not a finite positive floating-point number; …"; the inline message unchanged), also when a K entry underflows to 0 on the valve's bore, since an inline K must be above 0; and a new code, `FITTING_RESISTANCE_OUT_OF_RANGE`, when a fitting entry's K, or K/(2gA²), is not finite. A fitting's entry is not bounded by `kOverride`'s [0, 10⁴]: §2.2 bounds every entry at 10⁷, and the reference tester's case uses a K of about 5.3×10⁴ uncut.
15. **Goal seek** (§5.2): the start for a K entry is the valve's own K on its bore, K₀ (D/d₀)⁴ (`built.valves[id].resistance.k`), so `prepare` builds the case network before resolving variables, still once, and holds its topology error until after the 404 and 400 checks, keeping the error order. `caseValue` and `baseValue` are the reference object, `{kind: 'library', id}`: a resistance's value is always its whole object (D18's null rule is for ratings). The variable's text says "(the case's value, from its project library resistance "…" (RS1), K 0.3 at 0.09 m)" and that each value tried, and the override, is written on the valve as an inline coefficient in place of the entry; the element's note adds that the value found replaces the entry.
16. **Scenario texts** name entries by the trace's labels, `project library pipe spec "<name>" (<id>)` and `project library resistance "<name>" (<id>)`, by id where the project lacks them; `invalid_pipe_spec` reads "a pipe spec is an object with materialId and optionally schedule, nominalSize, innerDiameter, roughness, or with specId alone (a pipe spec of the project library), and no other key". A scenario that refers to a missing entry gets the hand-edited project's topology issue (§5.1).
17. **`models/components.inline_coefficient`**, the contract's interim guard that raised `TypeError` on an unresolved reference, was removed once resolution existed.

**Reference cases** (the tester's choices)

18. **Fifteen tests beyond §7.1** (225 in all; the 210 written first passed against the finished API with no expectation changed): entries on a sudden and a conical reducer, three custom fittings and a butterfly valve whose ports differ in bore, in reverse flow, against a closed form that does not depend on the bore the K is converted on (a K left at its stated bore would give 2.84× the valve's loss and 0.19× the reducer's, a Cv converted on one bore and applied with the other's velocity 2.09×); a fitting K entry moved above `kOverride`'s 10⁴, used uncut; a spec edit reaching every pipe; a spec's display fields changing nothing; D19's pipe-velocity check on spec pipes; an entry replacing a 0.74295 m butterfly valve's Crane default and its flag (P5); goal seek on a K entry stated at another bore and met at the start, a clipped start, and a scenario run with `replacedOverride`; the 400s for what the slice leaves out (an override or a goal-seek variable aimed at an entry, an equipment rating that refers to one, a 101st spec); an id in both lists.
19. **A goal seek's start on a K entry** is taken as K₀ (D/d₀)⁴, the case's value on the valve's bore (D16's start rule with §3.1's resolution); a case that already meets its goal decides it, since from K₀ the flow would move 7.4 %.

**Corpus tool**

20. **`library_check` has two modes and a twin check** (§7.2 described one lift): `exact`, each K at its element's own bore, so (D/d₀)⁴ = 1.0 and the lifted project B must equal the original A bit for bit (the trace, the timestamp and a library fitting's `source` left out, and the Crane flags of a lifted Crane default, which becomes user data); `rebased`, each K stated at d₀ = 1.1 D, so the conversion runs, B within D6 of A and each K within 10⁻¹² of A's, and, check (y), B bit for bit equal to its inline twin, B's project with each reference typed as a user would type it (a K as K₀ (D/d₀)⁴ computed in the check on the element's bore), so that whatever differs between A and B is the round-off of the moved K, not the library. A Crane default's `kOpen` is lifted too, as a K at the valve's bore. The smoke test (19 tests) makes what the corpus lacks (a spec without a roughness, more than 100 distinct definitions, a topology issue, a project that already refers to the library) and requires one-ulp falsifications to be reported. §7.2's second, independent resolver is the unit tests' `hand_resolved`.

**Web**

21. **"Use a pipe spec for…"** (§6.2's "Use this spec for…") is reachable from any pipe, not only from a spec pipe. Its scopes are this pipe, every pipe of the same material and size (from a spec pipe, every pipe on the same spec, which replaces one spec by another everywhere) and every pipe of the connection, each with its count, and the status line says how many pipes change before anything does; it is one undo step and keeps each pipe's identity, so scenario changes and the last results stay on it. "New pipe spec…" there goes on to the library's form, and the new spec is applied to the chosen scope in the same step. In a scenario each pipe's spec becomes a change of that scenario.
22. **The header button is "Project library"** (its accessible name; an icon with a book, labelled "Library" from 1280 px), just before the Fluid chip (§6.1: "next to Fluid"): at 1024 px a label left the project name about 50 px while a solve ran. Below 1024 px it is hidden while a solve or goal seek runs, so Cancel takes its place; when Cancel goes, Library comes back under the pointer, so its click ignores the second click of a double click or tap, as Solve's and Cancel's do (without that, `cancel.e2e.ts`'s double-tap test failed on the phone). Measured with no sideways scroll at 320, 360, 390, 640, 768, 1024 and 1280 px, idle and during a held solve. Below 1024 px, a single click on Cancel at the instant a calculation ends can still land on Library and open the dialog (a benign race).
23. **The dialog** edits through the store directly (base case only), not `ws.edit`, so that a refusal (a delete in use, a rule) is shown inside the modal dialog instead of in a notice behind it. Tabs switch with the arrow keys; each card expands its users; Save focuses the saved card. A form opened from a picker ("New pipe spec…", "New entry…", "Edit in the library") or from a trace link opens the dialog on that form or entry, and Save or Cancel closes the whole dialog, returning focus to the picker; a new entry made from a picker is created and used in one undo step ("add resistance entry X for …"). A new entry starts as a Cv, a new spec on the first library material. Escape closes the dialog and drops a draft, as the other dialogs do.
24. **The fittings editor** replaces the always-visible "K override" field with a "Fitting N loss coefficient" select (the cited K of the fitting's type, a K entered here, the entries, New entry…), one step more to enter a K, as `ResistanceField` has for valves; an entry is shown read-only, a K entry with its K₀ (D/d₀)⁴ at the pipe's bore where the browser knows that bore. The valve forms share `panel/ValveResistanceField.svelte` (the case's value, the scenario change, the entries, "New entry…").
25. **The browser converts only a K entry.** A Cv's or Kv's K and a library material's roughness at a spec's bore are the server's (D10: read, never copy); the spec form shows that roughness as a number only where the pipe library has a size of exactly that bore (the same Farshad value at the same D), and otherwise says that the server evaluates it there and the trace shows it.
26. **Delete is refused for scenario users too** (§6.1 named elements): an entry a scenario's change refers to is kept, the refusal naming that change.
27. **Trace links** read the server's labels (`libraryMentions`), so a change of that text must change the web as well. The ports editor names a spec pipe by its spec and compares its NPS with the port's (it read "a custom pipe (inner diameter —)").
28. **Export** (§5.3): a Project library sheet after the element tables and before Scenario changes (every entry of each case with a response, as that case was solved: its values as entered, "Roughness from" the entry or the material at the bore, computed by the server, its source as typed, and its users by count, label and id), "Pipe spec id" and "Pipe spec" columns in Pipes and "Resistance entry id" and "Resistance entry" in Fittings and Valves (§5.3 said a Spec column in the pipe and fitting tables), and one About line, all only in a file with a library, so a file without one is unchanged. A scenario's change of a valve's resistance to an entry reads "Project library RS1 “Name”".
29. **UI primitives:** `SelectField` resets the DOM select to its `value` after `onchange`, so an action option ("New entry…") or a choice the store refused never stays shown; `TextField` gains `error` and `oninput`.
30. **The e2e flows use the pump-transfer example** (§7.4 named the condenser example's NPS 48 pipes, which the rebuilt example no longer has: its NPS 60 pipes already use a spec): a spec created with its errors first and used for the 2 pipes of one size in one undo step, the solve request carrying `{specId, length}`, its source and link found in a trace; a Cv entry made from a valve's "New entry…", cited, and its deletion refused naming the valve; the header's fit and the double click on Cancel on the phone.

**Condenser water example** (§8, answer 6)

31. **Rebuilt with the water flowing one way through every header:** the six pumps into an NPS 60 supply header, the seven chillers off it and onto an NPS 60 return header, the tower bypass tee, one NPS 60 riser (60 m) and an NPS 60 distribution header along the six cells (cell 6 fed from its end through a 60×30 reducer), every tee on a Crane pattern. `PS1`, "NPS 60 carbon steel, 0.375 in wall (illustrative)": a 59.25 in bore with the roughness left to carbon steel's Farshad value at it (3.39709×10⁻⁵ m), its source saying the size is not taken from a cited table (so it does not claim ASME B36.10M, as §1.2 and §8 put it), on 25 pipes. `RS1`, "NPS 30 butterfly valve, open (illustrative)": a Cv of 48,800, not §8's made-up 60,000, derived from Crane's NPS 16–24 butterfly valve K, 25 f_T, extrapolated to the NPS 30 STD bore 0.74294 m (f_T 0.0109612, K 0.274029), converted with fluids' `K_to_Cv` (48,760) and rounded (K 0.273581 on the bore), on the six cell valves (as a valve's `{kind: 'library', id}`) and on the six pump suction lines' butterfly valve fittings (by `resistanceId`), so one entry shows both kinds of reference. The bypass and pump discharge valves stay NPS 24 on Crane's default, inside its table. 75 components and 86 connections, as before; the link is 5,321 characters (4,783 before). Both cases converge with 0 flags (the base in 13 Newton iterations and 3 outer iterations, the winter scenario in 8 and 2): the pumps 14,798–15,267 gpm at 109.1–110.7 ft; the cells 14,455–15,713 gpm, the far cell taking most (a dividing manifold's static regain); the largest velocity 3.51 m/s; the cell valves' drop 0.087–0.103 psi at K 0.273581.

**Integration**

32. **Validation locations** (the contract's open item). The union put its tag in every request-validation location under a valve's resistance (`…resistance.coefficient.value`), which changed the 400 of a project without a library. `main.py`'s `_without_resistance_tag` drops it, with `services/scenarios.RESISTANCE_TAGS` and only under a valve's `resistance` (an equipment rating keeps `rating.point.flow`, as always): every invalid inline value gives its `2723d3c` body byte for byte (48 of 48: eight invalid values on six request paths), and a reference's id is located at `resistance.id`. A resistance whose kind is unknown, missing or null, or that is not an object, still differs (six input classes): the discriminator's `invalid_resistance` at `…resistance`, where `2723d3c` gave `literal_error` or `missing` at `…resistance.kind`, or `model_attributes_type` at `…resistance`. A discriminator that fell back to `coefficient` for any kind but `library` would make every input without a library byte-identical (measured on 123 cases in a scratch worktree, `openapi.json` unchanged), at the cost of FlowCoefficient's message, which does not mention `library`, for a mistyped `library`; it is left as built, an open item.
33. **Reference helpers:** `tests/reference/element_laws.valve_k` takes the whole resistance type and raises `TypeError` naming a `ResistanceRef` (it gave a K of None silently), clearing 14 type errors in 9 files; the reference patcher's `SPEC_KEYS` gained `specId`; `test_scenarios.py` gained the `ladder_7_project_library` network (3 specs on 16 of its 24 connections; the 159 networks before it draw the same scenarios), spec-change draws to another spec and `test_spec_changes_to_and_from_the_project_library` (spec to spec, to a library pipe, to a custom pipe, a library pipe to a spec, each moving the solution beyond D6); taking `specId` back out of the patcher fails 4 tests.
34. **Fixtures:** the export fixture's `project-library` case, 3 applied and 1 invalid scenario cases and 3 goal-seek apply cases, all generated by the real API code (§7.4's shared fixture "by the real `apply_library`" is these); the committed export workbook regenerated for 1.5.0; `project-library.test.ts`'s encoding test runs on the two plain examples and adds a round trip for the condenser example, which now has a library.

**Proof** (§7.3; TSD §10.4 has the full record)

- **Reference suite:** 2,371 tests (2,367 passed at the tester's final run, then the integrator's 4 scenario tests). `test_project_library.py`, 225: the lift on 166 networks in 180 runs (789 specs, 190 entries, 50 valve references, 140 library fittings), bit for bit; NPS 60 by hand, 0.0 relative; K at a stated bore, −2.9×10⁻¹⁵; K, Cv and Kv entries against the ISA definition, +4.8×10⁻¹¹; the reverse-flow reducer line and the high-K fitting within 10⁻⁶; goal seek's Cv 123.345 against 123.3455 in closed form.
- **Corpus comparison** against `2723d3c`, with system curves: identical 5,168, different 0, with `--ignore methodVersion --ignore trace.methods.methodVersion` (5,168 values each); without them every project differs only there, 1.4.0 → 1.5.0. No corpus project has a library, so this shows that projects without one are unchanged; `library_check` covers projects with one.
- **`library_check`**, both modes: 0 different over the 5,168 projects; 95,501 specs and 47,325 entries lifted; in mode `rebased` every lifted project bit for bit its inline twin, and against the original 8.53×10⁻¹⁰ of the largest flow, 9.01×10⁻⁵ m of head (1.05×10⁻⁹ relative) and 7.17×10⁻¹⁶ in K, 49 values different only at zero flow, all in `fuzzaf_20055` (which zero-flow state is reported, D13). **`scenario_check`**: 0 different (4,723 solved, 445 invalid in both, 124 system curves). **`equipment_check`**, **`orifice_check`** (both modes) and **`design_checks_check`**: 0 different. **Fuzz:** 0 critical, the 9,000 records identical to `2723d3c`'s. **`missing_result_check`:** its baseline on both trees. **`goal_seek_check`** (5,168 projects, 96 min): 15,484 goal seeks, 0 violations, 0 errors, 72.0 % met (94.9 % of interior targets).
- **Gates on the integrated tree** (the gate runner, with the integrator's and example builder's changes): API `uv run pytest` 6,002 passed (617 s); ruff, ruff format (192 files) and mypy strict (61 source files) clean. Web `pnpm test` 1,325 passed (105 files), `pnpm check` 0 errors and 0 warnings (775 files), `pnpm lint` clean; Playwright 162 passed and 8 skipped by their projects' conditions (170 tests), the `project-library` flows passing on desktop and on the phone (5 passed, the phone-only header test skipped on desktop). No runtime dependency was added.

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
