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

## ADR-007: Port-Level Elevation with Inheritance

**Date:** 2026-01-25
**Status:** Accepted
**Context:** Issue #89 - Port-Level Elevation Support

### Decision

Add an optional `elevation` field to the `Port` model with inheritance behavior:

```python
class Port(OpenSolvePipeBaseModel):
    id: str
    nominal_size: PositiveFloat
    direction: PortDirection
    elevation: Elevation | None = None  # Optional, inherits from component if None
```

The `BaseComponent` class provides a `get_port_elevation(port_id)` method that:

1. Returns `port.elevation` if explicitly set
2. Returns `component.elevation` if port elevation is `None`

### Rationale

1. **Real-world accuracy**: Equipment often has ports at different heights:
   - Tanks: bottom drain vs side fill vs top overflow
   - Pumps: suction nozzle below discharge nozzle
   - Heat exchangers: shell/tube connections at different heights

2. **Backward compatibility**: By making elevation optional with inheritance, existing projects work unchanged. Ports default to inheriting from the parent component, which is correct for most equipment (valves, strainers, etc.).

3. **Minimal API surface**: A single optional field and one helper method, rather than separate elevation fields for each port type.

4. **Solver integration**: The `get_port_elevation()` method provides a clean abstraction for the solver to use port-level elevations in hydraulic calculations without checking for None everywhere.

### Consequences

**Positive:**

- More accurate head loss calculations for tall equipment
- Better NPSH calculations when pump suction/discharge are at different heights
- Cleaner API than alternatives (e.g., separate port elevation arrays)

**Negative:**

- Solver must be updated to use port elevations instead of component elevations where appropriate
- UI forms may need updates to allow port elevation input for relevant component types

**Migration:**

- No migration required - existing projects continue to work
- Port elevation field defaults to `None` (inherit from component)

---

## ADR-008: Protocol-Based Interfaces

**Date:** 2026-01-31
**Status:** Accepted
**Context:** Issue #118 - Create protocols module structure

### Decision

Use `typing.Protocol` for defining structural contracts that components and services must satisfy. Protocols are organized in a dedicated `protocols/` module:

```text
protocols/
├── __init__.py       # Re-exports all protocols
├── solver.py         # NetworkSolver protocol
├── components.py     # HasPorts, HeadSource, HeadLossCalculator protocols
└── fluids.py         # FluidPropertyProvider protocol
```

### Rationale

- **Avoid metaclass conflicts**: Pydantic models use `ModelMetaclass`, which conflicts with `ABCMeta`. Protocols use structural subtyping without metaclass requirements.
- **Structural subtyping**: Classes satisfy protocols implicitly by implementing the required methods, no explicit inheritance needed.
- **Static type safety**: mypy validates protocol conformance at type-check time.
- **No runtime overhead**: Protocols are not `@runtime_checkable`, avoiding isinstance() overhead.
- **Separation of concerns**: Interface contracts live separately from implementations.

### Consequences

**Positive:**

- Clean separation between interface contracts and implementations
- No isinstance() checks at runtime (use type annotations instead)
- Existing Pydantic models can satisfy protocols without modification
- mypy catches protocol violations during development

**Negative:**

- Cannot use isinstance() to check protocol conformance at runtime
- Developers must understand structural subtyping concept
- Protocol method signatures must be kept in sync with implementations

---

## ADR-009: WNTR/EPANET Integration for Looped Networks

**Date:** 2026-01-31
**Status:** Accepted
**Context:** Issue #128, #129, #130, #131 - Phase 2 Looped Network Support

### Decision

Integrate WNTR (Water Network Tool for Resilience) as the solver backend for looped/complex networks:

1. **Dependency**: Add `wntr` package to Python dependencies
2. **Wrapper Module**: Create `epanet.py` wrapper that:
   - Converts OpenSolve component chain to WNTR network graph
   - Maps component types to WNTR equivalents
   - Runs EPANET simulation via WNTR's solver interface
   - Converts WNTR results back to OpenSolve `SolvedState` format
3. **Solver Selection**: Automatic routing based on network topology:
   - Simple (no branches): Use direct calculation (`SimpleSolver`)
   - Branching (tree): Use `BranchingSolver`
   - Looped (cycles): Use `LoopedSolver` → WNTR/EPANET

### Rationale

- **Industry standard**: EPANET is the de facto standard for hydraulic network analysis
- **Proven accuracy**: 30+ years of validation in water distribution systems
- **Python integration**: WNTR provides clean Python API to EPANET solver
- **Gradient-based solving**: Hardy Cross / Newton-Raphson handles complex topologies
- **Maintained library**: WNTR actively maintained by US EPA and Sandia National Labs

### Consequences

**Positive:**

- Supports any network topology (parallel, looped, complex branching)
- Leverages validated solver algorithms
- Consistent results with industry tools

**Negative:**

- Additional dependency (~50MB with EPANET binaries)
- Conversion overhead between component chain and WNTR graph
- WNTR uses SI units internally (requires conversion layer)
- Some OpenSolve features (viscosity correction) not natively supported by EPANET

**Component Mapping:**

| OpenSolve | WNTR |
|-----------|------|
| Reservoir | Reservoir (fixed head) |
| Tank | Tank (variable level) |
| Junction | Junction (demand node) |
| Pump | Pump (with head curve) |
| Valve (PRV/PSV/FCV) | Valve (matching type) |
| Valve (gate/ball/check) | Pipe with minor loss |
| PipeConnection | Pipe (with friction) |
| HeatExchanger, Strainer | Pipe with equivalent K-factor |

---

## ADR-010: Schematic Layout Algorithm

**Date:** 2026-01-31
**Status:** Accepted
**Context:** Issue #133 - Graph Layout Algorithm for Schematic Viewer

### Decision

Use a left-to-right directed graph layout algorithm based on dagre principles:

1. **Layout Direction**: Left-to-right (LR) flow matching typical P&ID conventions
2. **Algorithm**: Layered graph layout (Sugiyama-style) with:
   - Topological sorting to establish component layers
   - Rank assignment based on distance from source
   - Node ordering within layers to minimize edge crossings
   - Horizontal and vertical spacing based on component types
3. **Implementation**: Custom TypeScript implementation in `layout.ts`

### Rationale

- **P&ID conventions**: Hydraulic schematics typically flow left-to-right
- **Readable output**: Layered layout produces clean, organized diagrams
- **Branch handling**: Algorithm naturally handles split/merge points
- **No external dependency**: Custom implementation avoids dagre.js bundle size
- **Customization**: Can tune spacing, ranking for hydraulic-specific needs

### Consequences

**Positive:**

- Clean, professional-looking schematics
- Consistent layout across different network topologies
- No external runtime dependencies
- Full control over layout parameters

**Negative:**

- Manual position override not implemented (would require significant UI work)
- Complex networks may have suboptimal edge routing
- Algorithm complexity: O(V + E) for basic layout, O(V²) worst case for crossing minimization

**Future Considerations:**

- Could add elkjs for more sophisticated layout options
- Manual position persistence would require schema changes

---

## ADR-011: Generic Symbol Fallback Pattern

**Date:** 2026-01-31
**Status:** Accepted
**Context:** Issue #134 - Component Symbols for Schematic Viewer

### Decision

Implement a two-tier symbol system:

1. **Dedicated Symbols**: Full SVG symbols for core component types:
   - `ReservoirSymbol`: Tank-like shape with water level indication
   - `TankSymbol`: Cylinder with level indicator
   - `JunctionSymbol`: Connection point (dot or small circle)
   - `PumpSymbol`: Circle with impeller indication
   - `ValveSymbol`: Bowtie shape (two triangles)
   - `PipeSymbol`: Line with flow direction

2. **Generic Fallback**: `GenericSymbol` for components without dedicated symbols:
   - Rounded rectangle with 2-3 letter abbreviation
   - Abbreviations: HX (heat exchanger), STR (strainer), ORF (orifice), etc.
   - Consistent sizing and styling with dedicated symbols
   - Theme-aware colors via CSS variables

### Rationale

- **Incremental delivery**: Ship working schematic with core symbols first
- **Always renderable**: Every component can be displayed, even without custom art
- **ISA-5.1 compliance**: Core symbols follow P&ID standards
- **Extensibility**: New symbol components can be added without changing layout code
- **Theme support**: CSS variables enable dark/light mode switching

### Consequences

**Positive:**

- Schematic always renders completely (no missing components)
- Clear visual distinction between component types
- Easy to add new symbols incrementally
- Consistent look across themes

**Negative:**

- Some components less recognizable (HX vs actual heat exchanger symbol)
- Users familiar with P&ID symbols may expect standard representations
- Need to implement 9 more dedicated symbols for full coverage

**Remaining Symbols Needed:**

- HeatExchanger: Coil or shell-and-tube pattern
- Strainer: Basket/Y-strainer pattern
- Orifice: Restriction plate symbol
- Sprinkler: Spray pattern
- Plug: Cap/dead-end symbol
- ReferenceNode: Boundary marker
- Tee/Wye/Cross: Junction shapes

---

## ADR-012: Workspace Layout with Persistent State and Dual Interaction Paradigms

**Date:** 2026-02-10
**Status:** Accepted
**Context:** Issues #164-#171 - UI/UX Audit Improvements

### Decision

Adopt a dual-paradigm workspace design that supports both spatial (IDE-like) and sequential (panel navigator) interaction models:

1. **workspaceStore**: A localStorage-persisted Svelte store manages all layout state (sidebar, inspector, focus mode, zoom, active tabs). This replaces scattered local `$state` variables across components.

2. **Multi-tab Sidebar**: The sidebar uses a tabbed interface (Tree/Config/Results) instead of a single component tree, giving every feature a permanent home.

3. **Always-rendered Panels**: Sidebar and inspector are always mounted in the DOM. Visibility is controlled by CSS `grid-template-columns` transitions (0px width when collapsed), enabling smooth slide animations instead of instant `{#if}` block removal.

4. **Focus Mode (Desktop)**: A toggle (`Ctrl+Shift+F`) collapses sidebar and inspector, replacing them with the PanelNavigator in a bottom panel (~35vh). This gives desktop users access to the sequential editing paradigm without leaving the workspace.

5. **Bottom Sheet (Mobile)**: On mobile (≤768px), the sidebar and inspector are hidden entirely. A swipe-driven bottom sheet with three snap points (collapsed/half/full) renders the PanelNavigator, and a bottom nav bar provides tab-based navigation (Components/Settings/Results/Solve).

6. **CSS Utility Classes**: Repeated Tailwind patterns are extracted into semantic utility classes (`.section-heading`, `.card`, `.form-input`, `.mono-value`) in `app.css` to reduce duplication across 15+ component files.

### Rationale

- **Persistence**: Layout preferences (which panels are open, active tabs) should survive page reloads. localStorage is sufficient since this is client-only state.
- **Smooth transitions**: CSS grid transitions are more performant than Svelte transitions for layout changes because they avoid DOM insertion/removal.
- **Dual paradigms**: Engineers need both spatial overview (see everything) and sequential deep-editing (walk the chain). Rather than forcing one model, both are available.
- **Mobile-first bottom sheet**: Touch-driven swipe gestures are the native mobile interaction pattern. The bottom sheet preserves canvas visibility while allowing full editing.
- **CSS utilities**: 30+ instances of identical class strings across files was a maintenance burden. Semantic class names improve readability.

### Consequences

**Positive:**

- Unified state management via workspaceStore eliminates state sync bugs
- Smooth CSS animations for all panel toggles (200ms ease)
- Mobile users get a native-feeling editing experience
- Desktop users can switch between spatial and sequential paradigms
- Reduced CSS duplication improves consistency

**Negative:**

- Always-rendered panels consume memory even when hidden (minimal impact)
- Bottom sheet swipe gestures require careful threshold tuning
- Focus mode layout requires a separate CSS grid definition
- CSS utility classes add a layer of indirection vs inline Tailwind

---

## ADR-013: Component Form Registry Pattern and Route-Based View System

**Date:** 2026-02-10
**Status:** Accepted
**Context:** Issue #173 - Remaining UI audit items

### Decision

1. **Form Registry**: Replace the 15-branch `{#if}/{:else if}` chain in `ElementPanel.svelte` with a `FORM_REGISTRY` map (`Record<ComponentType, SvelteComponent>`) in `forms/index.ts`. `ReferenceNodeForm` retains a special case for its `onTypeChange` prop. Uses Svelte 5's native dynamic component rendering instead of deprecated `<svelte:component>`.

2. **Route-Based Views**: Restructure URL routes from `[...encoded]` (rest parameter) to `[encoded]` (single segment), enabling sub-routes like `/p/{encoded}/results` and `/p/{encoded}/cost`. A new `/p/+page.svelte` handles the "new project" case (previously caught by the rest parameter matching zero segments).

3. **CSS Form Utility**: Update `.form-input` class to match full form field styling (0.875rem font, 0.75rem padding, accent focus ring, shadow) and replace inline Tailwind class strings across all form components.

### Rationale

- **Registry pattern**: Adding a new component type becomes a one-line entry in the registry instead of touching the panel template. Eliminates 14 type guard imports.
- **Route restructuring**: base64url encoding doesn't contain `/`, so the rest parameter was unnecessary. Single-segment params enable SvelteKit's standard nested routing for future full-screen views.
- **CSS utility**: The inline select/input class string (`mt-1 block w-full rounded-md border...`) appeared 8+ times across forms. A single `.form-input` class eliminates duplication.

### Consequences

**Positive:**

- Adding new component types requires only: form component + registry entry
- Future views (results, cost estimation, pipe sizing) get dedicated routes
- Form CSS maintenance is centralized in one class definition

**Negative:**

- Dynamic component rendering loses TypeScript narrowing on form props (mitigated by `any` type on registry)
- Existing URLs with `/p/` (no encoded data) now route to a redirect page instead of the workspace directly
- Sub-routes share no layout yet — a `+layout.svelte` extraction would be needed for shared workspace chrome

---

## ADR-014: Parent-Child Component Inheritance with Auto-Break

**Date:** 2026-02-10
**Status:** Accepted
**Context:** Issue #180 - Copy component with series/parallel options and parent-child inheritance

### Decision

When a component is copied (via right-click context menu), the copy maintains a `parent_id` reference to the original:

1. **`parent_id` field**: Added to `BaseComponentProps`. `undefined` means independent; a string ID means linked to a parent.
2. **Copy in Series**: Inserts the copy immediately after the original in the component chain and redirects downstream connections through the copy.
3. **Copy in Parallel**: Inserts the copy after the original without modifying connections.
4. **Auto-propagation**: When `updateComponent()` is called on a parent, type-specific fields (everything except `id`, `name`, `parent_id`, `downstream_connections`, `upstream_piping`, `ports`) are propagated to all linked children.
5. **Auto-break**: When `updateComponent()` is called directly on a child (a component with `parent_id`), the `parent_id` is set to `undefined`, making it independent.
6. **Visual indicator**: A chain-link icon appears in the component tree next to linked children.

### Rationale

- **Common workflow**: Engineers frequently duplicate equipment with minor variations. Copy-then-edit is faster than configuring from scratch.
- **Consistency guarantee**: Parent-child links ensure replicated components stay in sync until intentionally diverged.
- **Explicit break**: Editing a child is a clear signal of intentional divergence; auto-breaking the link prevents confusion about which component "owns" the values.
- **Non-propagating fields**: Identity (`id`, `name`), topology (`connections`, `piping`, `ports`), and lineage (`parent_id`) are inherently per-component and must not propagate.

### Consequences

**Positive:**

- Fast duplication workflow for common equipment
- Linked components stay synchronized automatically
- Clear visual indication of parent-child relationships
- Clean break semantics — no partial inheritance states

**Negative:**

- Propagation is shallow (one level only; grandchildren don't inherit from grandparent)
- Breaking the link is irreversible without undo
- Bulk edits to multiple children require editing the parent (or each child individually after break)

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
