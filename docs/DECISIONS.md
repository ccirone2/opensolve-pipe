# Architecture Decision Records (ADRs)

This document captures architectural decisions made during OpenSolve Pipe development.

---

## ADR-001: Pydantic Model Structure

**Date:** 2026-01-19
**Status:** Accepted
**Context:** Issue #2 - Backend Data Models

### Decision

Organize Pydantic models into separate files by domain concern rather than a single large models file:

```text
models/
├── base.py         # BaseModel config, common types
├── project.py      # Project container
├── components.py   # All component types
├── piping.py       # Pipe and fitting definitions
├── pump.py         # Pump curve models
├── fluids.py       # Fluid definitions and properties
├── results.py      # Solved state and results
└── units.py        # Unit preferences
```

### Rationale

- **Maintainability**: Smaller files are easier to navigate and modify
- **Clear ownership**: Each domain has a dedicated file
- **Circular import prevention**: Careful separation allows forward references
- **Test organization**: Tests can mirror the model structure

### Consequences

- More import statements required
- Need to maintain `__init__.py` exports
- Forward references needed for some types (e.g., `SolvedState` in `Project`)

---

## ADR-002: Component Type Discrimination

**Date:** 2026-01-19
**Status:** Accepted
**Context:** Issue #2 - Backend Data Models

### Decision

Use Pydantic's discriminated union pattern with `type` field as discriminator:

```python
Component = Annotated[
    Reservoir | Tank | Junction | PumpComponent,
    Field(discriminator="type")
]
```

### Rationale

- **Type safety**: Pydantic and mypy understand which fields are available
- **Serialization**: JSON includes `type` field for unambiguous deserialization
- **Extensibility**: New component types can be added to the union
- **Frontend alignment**: Matches TypeScript discriminated union pattern

### Consequences

- Each component class must have a `type: Literal[...]` field
- Order of union types may affect serialization performance (slight)
- Adding new types requires updating the union definition

---

## ADR-003: Validation Strategy

**Date:** 2026-01-19
**Status:** Accepted
**Context:** Issue #2 - Backend Data Models

### Decision

Apply strict validation with `extra="forbid"` and validate physical constraints:

1. **Forbid extra fields**: Catch typos and schema mismatches early
2. **Physical bounds**: Validate that values make physical sense (positive lengths, etc.)
3. **Reference validation**: Verify component and curve references exist
4. **Deferred pump curve validation**: Allow non-monotonic curves with warning (some real pumps have unusual curves)

### Rationale

- Early error detection improves developer experience
- Physical validation prevents nonsensical models from reaching the solver
- Reference validation ensures model integrity
- Flexibility for unusual but valid pump curves

### Consequences

- Stricter than some users might expect
- May need to relax validation if edge cases emerge
- Error messages must be clear about what's wrong

---

## ADR-004: Unit Handling in Models

**Date:** 2026-01-19
**Status:** Accepted
**Context:** Issue #2 - Backend Data Models

### Decision

Models store values in "project units" (user's preferred units), not SI:

- `UnitPreferences` defines what units are used
- Values like `elevation`, `length`, `flow` are in project units
- Unit conversion happens at API boundaries, not in models

### Rationale

- Matches user mental model (they enter 100 GPM, model stores 100 GPM)
- Reduces conversion errors in storage/retrieval
- Solver performs conversions internally when needed
- Simplifies serialization (no unit conversion on save/load)

### Consequences

- Solver must convert to SI before calculations
- Results must be converted back to project units
- Need to be careful about unit consistency across operations

---

## ADR-005: Results Structure

**Date:** 2026-01-19
**Status:** Accepted
**Context:** Issue #2 - Backend Data Models

### Decision

Structure results as dictionaries keyed by component ID rather than lists:

```python
class SolvedState:
    node_results: dict[str, NodeResult]
    link_results: dict[str, LinkResult]
    pump_results: dict[str, PumpResult]
```

### Rationale

- **O(1) lookup**: Direct access by component ID
- **Sparse results**: Only solved components have entries
- **Alignment with frontend**: JavaScript/TypeScript can use object lookup
- **Easier updates**: Can update single component without list index

### Consequences

- Slightly more verbose serialization
- Must ensure IDs are unique (enforced in Project model)
- Ordering not guaranteed (use component list order for display)

---

## ADR-006: Component vs Piping Terminology (Not Nodes vs Links)

**Date:** 2026-01-20
**Status:** Accepted
**Context:** UI Review - Add Component Menu Architecture

### Decision

Rename the conceptual grouping from "Nodes vs Links" to "Components vs Piping":

1. **Components (Equipment)**: All hydraulic equipment in the network
   - Reservoir, Tank, Junction, Sprinkler, Orifice
   - Pump, Valve, Heat Exchanger, Strainer
   - These are the "things" in the system

2. **Piping (Connections)**: The piping and fittings that connect components
   - Pipes (with material, schedule, diameter, length)
   - Fittings (elbows, tees, reducers) with K-factors
   - These exist on the `upstream_piping` and `downstream_connections[].piping` properties

3. **Exception - Tee as Component**: A tee fitting that creates a branch connection should be represented as a Junction component, not as a piping fitting.

### Rationale

The original "Nodes vs Links" terminology was adopted from EPANET/WNTR graph theory where:

- **Nodes** = points with pressure state (junctions, reservoirs, tanks)
- **Links** = flow paths (pipes, pumps, valves)

However, this creates confusion because:

- **User mental model**: Engineers think of "equipment" (pumps, valves, HX) and "piping" (pipes, fittings)
- **EPANET classifies pumps and valves as "links"**, but users see them as equipment/components
- The distinction between "node" and "link" is a solver implementation detail, not a user concept

The new terminology aligns with:

- How engineers describe systems ("add a pump", "add a valve", not "add a link")
- The UI's "Add Component" menu (all equipment should be peers)
- The data model's `PipingSegment` concept (piping connects components)

### Consequences

**Frontend Changes Required:**

- `apps/web/src/lib/models/components.ts`: Replace `COMPONENT_CATEGORIES` Nodes/Links with single "Equipment" category or flat list
- `apps/web/src/lib/models/components.ts`: Remove/rename `isNodeComponent()` and `isLinkComponent()` functions
- `apps/web/src/lib/components/panel/ElementTypeSelector.svelte`: Update grouping UI
- `apps/web/src/lib/components/results/ResultsPanel.svelte`: Rename "Nodes" and "Links" tabs to "Components" or similar
- `apps/web/src/lib/components/results/NodeTable.svelte`: Rename to ComponentTable or merge
- `apps/web/src/lib/components/results/LinkTable.svelte`: Rename to ComponentTable or merge

**Backend Changes Required:**

- `apps/api/src/opensolve_pipe/models/results.py`: Rename `NodeResult` and `LinkResult` to `ComponentResult` or similar
- API response structure may need adjustment

**Documentation Changes Required:**

- `docs/PRD.md`: Update Section 3.1.1 "Nodes" and 3.1.2 "Links" terminology
- `docs/user/components.md`: Update user-facing documentation

**Solver Consideration:**

- The internal solver can still use EPANET's node/link graph representation
- This is an abstraction layer: user-facing "components" map to solver "nodes and links"
- The mapping logic in `component_chain_to_network()` handles this translation

---

## Template for Future ADRs

```markdown
## ADR-XXX: [Title]

**Date:** YYYY-MM-DD
**Status:** Proposed | Accepted | Deprecated | Superseded
**Context:** [Issue or feature this relates to]

### Decision

[What is the change or decision being made]

### Rationale

[Why this decision was made - list key reasons]

### Consequences

[What are the results of this decision - both positive and negative]
```
