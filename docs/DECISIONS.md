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

## ADR-015: Universal Load Redirect for New Project Route

**Date:** 2026-02-10
**Status:** Accepted
**Context:** Issue #193 - New Project button loading screen never loads workspace

### Decision

Replace the client-side `onMount` + `goto()` redirect in `/p/+page.svelte` with a SvelteKit universal load function in `/p/+page.ts`:

```typescript
// apps/web/src/routes/p/+page.ts
import { redirect } from '@sveltejs/kit';
export const load: PageLoad = () => {
  const project = createNewProject();
  const result = encodeProject(project);
  redirect(307, `/p/${result.encoded}`);
};
```

### Rationale

- **Root cause**: `onMount` callbacks in Svelte 5 do not fire reliably during hydration in Vite preview builds. The `/p` route showed "Creating new project..." indefinitely because the `goto()` call inside `onMount` never executed.
- **Universal load**: SvelteKit's `+page.ts` load function runs on both server and client, before the component renders. `redirect()` is handled at the framework level, bypassing the hydration issue entirely.
- **Consistent behavior**: The redirect works identically in `pnpm dev` (Vite dev server), `pnpm preview` (Vite preview), and production builds (Vercel adapter).
- **Simpler component**: `/p/+page.svelte` is reduced to a minimal loading fallback that only displays briefly during the redirect, instead of containing navigation logic.

### Consequences

**Positive:**

- New project creation works in all build modes (dev, preview, production)
- E2E tests can verify the redirect by asserting `toHaveURL(/\/p\/.+/)`
- Component is simpler (no `onMount`, no `goto` import)

**Negative:**

- Encoding a default project in the load function adds a small latency to the redirect (~5ms)
- The `+page.svelte` is now essentially dead code (the redirect fires before it renders) but kept for loading state fallback

---

## ADR-016: Display Units Simplification (Removing Mixed Mode)

**Date:** 2026-02-10
**Status:** Accepted
**Context:** Issue #196 - Remove "Mixed" button under Config > Units

### Decision

Remove the `MIXED` value from the `UnitSystem` enum on both frontend and backend, leaving only `IMPERIAL` and `SI`. Rename the UI section from "Unit System" to "Display Units."

**Backend:**

```python
class UnitSystem(str, Enum):
    IMPERIAL = "imperial"
    SI = "si"
    # MIXED removed
```

**Frontend:**

```typescript
type UnitSystem = 'imperial' | 'si';
// 'mixed' removed
```

### Rationale

- **Users can always enter data in any unit**: The input fields accept values and the system converts internally. "Mixed" implied a third mode but offered no additional capability.
- **Display units are what matters**: The toggle controls which unit system is used for displaying results and default input fields. Calling it "Display Units" is more accurate and less confusing.
- **Simpler UI**: Two-button toggle (Imperial / SI) is clearer than a three-button toggle where one option ("Mixed") had unclear semantics.

### Consequences

**Positive:**

- Clearer user experience — no ambiguity about what "Mixed" means
- Simpler validation — only two valid enum values
- Frontend and backend models are smaller and easier to maintain

**Negative:**

- Breaking change for any saved projects that reference `unit_system: "mixed"` (mitigated: defaults to `imperial` on deserialization if value is unrecognized)

---

## ADR-017: Library Tab for Reusable Data Definitions

**Date:** 2026-02-10
**Status:** Accepted
**Context:** Issue #195 - Add Library tab for pump curves, loss curves, and reference profiles

### Decision

Add a fourth sidebar tab ("Library") for managing reusable data definitions:

1. **Tab structure**: Three collapsible sections — Pump Curves (functional), Loss Curves (Coming Soon), Reference Profiles (Coming Soon).
2. **Pump Curve CRUD**: Full create, read, update, delete for pump curves backed by the existing `pumpLibrary` store.
3. **Inline editing**: Clicking a pump curve in the list expands an inline editor (`PumpCurveEditor.svelte`) with name field and flow/head data point table.
4. **Coming Soon sections**: Loss Curves and Reference Profiles display a description of planned functionality with a "Coming Soon" badge.

### Rationale

- **Discoverability**: Pump curves were previously only accessible from within the Pump component form. A dedicated Library tab makes them easy to find, create, and manage independently of any specific pump.
- **Extensibility**: The collapsible section pattern supports future data types (loss curves, reference profiles) without restructuring.
- **Existing store**: The `pumpLibrary` store already exists in the project model. The Library tab is purely a new UI surface for existing data.
- **Minimum 2 points**: Enforced in the editor UI, matching the backend `PumpCurve` Pydantic model's `min_length=2` constraint.

### Consequences

**Positive:**

- Pump curves are easier to manage and discover
- Architecture is ready for loss curves and reference profiles
- No backend changes required — uses existing `pumpLibrary` store and `PumpCurve` model

**Negative:**

- Fourth sidebar tab may feel crowded on smaller screens (mitigated by vertical icon strip design)
- Coming Soon placeholders may set user expectations for features not yet available
- Chart.js visualization of pump curves is not yet included (future enhancement)

---

## ADR-018: Keyboard-First Component Navigation

**Date:** 2026-02-10
**Status:** Accepted
**Context:** Issues #204, #209 - Arrow key navigation in component tree and workspace

### Decision

Implement a split keyboard navigation model:

- **Up/Down arrows** in the component tree panel (listbox pattern with `role="listbox"` / `role="option"`)
- **Left/Right arrows** at the workspace level for schematic navigation
- Home/End keys for jump-to-first/last in the tree
- Arrow keys skip navigation when focus is on input/textarea/select elements

The component tree list container receives focus on click (`listEl.focus()`) so arrow keys work immediately after selecting a component. Workspace-level arrows are handled via the global `svelte:window onkeydown` handler with element tag guards.

### Rationale

- **No conflicts:** Up/Down in tree vs Left/Right in workspace avoids key collisions
- **Standard patterns:** listbox/option ARIA roles match WAI-ARIA authoring practices
- **Input safety:** Tag-based guard (`INPUT`, `TEXTAREA`, `SELECT`) prevents arrow keys from interfering with form fields
- **Inspector sync:** Both navigation paths update `currentElementId` via `navigationStore.navigateTo()`, keeping the inspector panel in sync

### Consequences

**Positive:**

- Full keyboard-driven workflow without mouse for component navigation
- Accessible to screen reader users via ARIA roles
- Auto-scroll keeps selected component visible in both tree and schematic

**Negative:**

- Left/Right arrows are globally captured on the workspace page (could conflict with future text editing in canvas)
- Users must click a component first before arrow keys work (no implicit focus)

---

## ADR-019: Sidebar Footer as Help-Only (Shortcuts Popup)

**Date:** 2026-02-10
**Status:** Accepted
**Context:** Issue #205 - Redesign sidebar footer

### Decision

Replace the sidebar footer action buttons (Add Component, Solve, Undo, Redo) with a single "Shortcuts" button that opens a modal popup listing all keyboard shortcuts. The footer no longer triggers any actions directly — it serves purely as a discoverability aid for keyboard shortcuts.

### Rationale

- **Redundancy removal:** All footer actions were already accessible via keyboard shortcuts (Ctrl+K, Ctrl+Enter, Ctrl+Z, Ctrl+Shift+Z) and toolbar buttons
- **Discoverability:** New users need a way to discover available shortcuts; a dedicated popup serves this better than duplicated buttons
- **Prop simplification:** Removing `onUndo`/`onRedo` from SidebarTabs reduces prop threading complexity
- **Screen real estate:** Single small button uses less vertical space than four action buttons

### Consequences

**Positive:**

- Cleaner sidebar footer with minimal visual clutter
- Self-documenting UI — users can always find all shortcuts in one place
- Reduced prop coupling between workspace page and sidebar components

**Negative:**

- Users who relied on footer buttons must use keyboard shortcuts or toolbar instead
- Shortcuts list is static (must be manually updated when new shortcuts are added)

---

## ADR-020: Environment-Variable API URL for Deployment Flexibility

**Date:** 2026-02-10
**Status:** Accepted
**Context:** Issue #207 - Solver not working on Vercel deployment

### Decision

Use `import.meta.env.PUBLIC_API_URL` for the SSR base URL in the API client, with `http://localhost:8000` as the fallback. Browser requests continue to use the relative `/api/v1` path (proxied by SvelteKit or Vercel rewrites).

Chose `import.meta.env` over SvelteKit's `$env/dynamic/public` because the dynamic import caused page crashes in Vite preview builds (elements detached from DOM).

### Rationale

- **Deployment flexibility:** Different environments (local, staging, production) can point to different API backends
- **Vite compatibility:** `import.meta.env` works reliably in dev, preview, and production builds
- **Zero breaking change:** Defaults to localhost when env var is not set

### Consequences

**Positive:**

- Vercel deployment now works correctly with `PUBLIC_API_URL` pointing to the deployed API
- Local development works without any configuration
- `.env.example` documents the required variables for deployment

**Negative:**

- `import.meta.env` values are baked in at build time (not truly dynamic at runtime)
- Must rebuild the frontend when changing the API URL

---

## ADR-021: Full-Width Canvas Editor for Pump Curves

**Date:** 2026-02-10
**Status:** Accepted
**Context:** Issue #217 - Library Panel Pump Curve Editor

### Decision

Replace the inline sidebar pump curve editor with a full-width tabbed editor panel that takes over the canvas area when a pump curve is selected from the Library sidebar tab. The editor state is driven by `editingPumpCurveId` in the workspace store.

The editor shows when `editingPumpCurveId !== null` AND `activeSidebarTab === 'library'`. Switching to another sidebar tab reveals the schematic; switching back to Library restores the editor for the previously selected curve.

### Rationale

- **Space for data entry:** Pump curves have multiple data types (head, efficiency, NPSH, power) and metadata fields that are too cramped for a 300px sidebar
- **Tab-based organization:** Three primary tabs (Info, Data, Preview) with four data sub-tabs mirror the logical groupings of pump curve data
- **Non-destructive switching:** Canvas content toggles between schematic and editor based on store state, preserving both views
- **Consistent with Library pattern:** As more library types are added (loss curves, reference profiles), the same canvas-takeover pattern can be reused

### Consequences

**Positive:**

- Full-width layout accommodates data tables, forms, and chart preview comfortably
- Local editable state with explicit Save prevents accidental data loss
- SVG preview chart provides immediate visual feedback without external dependencies

**Negative:**

- Schematic is hidden while editing pump curves (trade-off for full-width editing space)
- Each new library item type will need its own editor panel component

---

## ADR-022: Pump Curve Chart Architecture (Shared Flow Domain, NPSH Subplot)

**Date:** 2026-02-10
**Status:** Accepted
**Context:** Issue #219 - Pump Curve Editor Enhancements

### Decision

Rewrite the Curve Preview SVG charts with:

1. **Shared flow domain** across all curve types for a consistent X-axis
2. **Nice axis ticks** algorithm that computes round numbers (1, 2, 5 multiples) for both axes
3. **NPSH as a separate subplot** below the main chart with its own Y-axis scale
4. **Design point crosshair** rendered as dashed lines spanning the full chart with a diamond marker
5. **BEP marker** computed from quadratic efficiency curve fit

### Rationale

- **Shared flow domain:** All curves on the same chart need identical X-axis scaling for visual correlation; previously each curve computed its own max flow independently
- **Nice ticks:** Engineers expect round-number axis labels (0, 50, 100) not arbitrary values; the algorithm snaps to 1/2/5 × 10^n increments
- **NPSH subplot:** NPSH required values (typically 5-30 ft) are a different order of magnitude from head (50-200 ft), making overlay confusing; a separate subplot with its own Y-axis is standard practice in pump curve sheets
- **Design point crosshair:** Industry convention for marking the rated operating condition on pump curve charts

### Consequences

**Positive:**

- Chart axes now have readable numeric labels matching engineering convention
- NPSH is clearly visible with appropriate scale instead of being compressed
- Design point is prominent and easy to identify on both main chart and NPSH subplot

**Negative:**

- Two separate SVG elements require coordinated X-axis (solved via shared `flowAxisMax` state)
- Chart rendering code is more complex with const declarations requiring Svelte `{#if true}` wrappers

---

## ADR-023: Surface Pressure Integration in Solver Head Calculations

**Date:** 2026-02-10
**Status:** Accepted
**Context:** Issue #225 - HGL calculation: port elevation and surface pressure handling

### Decision

Integrate surface pressure into the hydraulic solver by extending `get_source_head()` with an optional `fluid_props` parameter:

```python
def get_source_head(
    component: Component,
    fluid_props: FluidProperties | None = None,
) -> float:
```

When `fluid_props` is provided and the component has non-zero `surface_pressure`, gauge pressure (psi) is converted to feet of head using: `pressure_head_ft = surface_pressure * 2.31 / specific_gravity`.

For the WNTR/EPANET solver, surface pressure is added to the reservoir `base_head` and tank `init_level` before passing to WNTR, since EPANET has no native surface pressure concept.

### Rationale

- **Physical correctness**: Pressurized tanks (e.g., bladder tanks, elevated tanks with gas blanket) have total head = elevation + water level + pressure head. Omitting surface pressure yields incorrect system curves and operating points.
- **Backward compatibility**: The `fluid_props` parameter is optional with `None` default. Existing callers that don't pass it get identical behavior to before.
- **Standard conversion**: 2.31 ft/psi is the standard conversion factor for water at standard conditions; dividing by specific gravity handles non-water fluids.
- **Port elevation independence**: After analysis, HGL (total head) is independent of the observation point elevation. Port elevation affects local pressure head at that point but not the HGL value, so no solver change was needed for port elevation.

### Consequences

**Positive:**

- Pressurized tanks now produce correct HGL values
- All three solver strategies (simple, branching, looped) handle surface pressure consistently
- Backward compatible — no changes needed for callers that don't use surface pressure

**Negative:**

- WNTR integration uses a workaround (inflating init_level) since EPANET doesn't natively support surface pressure
- Surface pressure conversion assumes incompressible fluid (valid for liquids, the only fluids OpenSolve supports)

---

## ADR-024: Results View Click-to-Inspector Navigation Pattern

**Date:** 2026-02-10
**Status:** Accepted
**Context:** Issue #226 - Inspector pane shows selected entity details from results views

### Decision

Add click handlers to all four results views (ComponentTable, PipingTable, PumpResultsCard, ElevationProfile) that navigate the inspector panel to the clicked entity using the existing `navigationStore.navigateTo(componentId)` + `workspaceStore.setInspectorOpen(true)` pattern. Selected items are highlighted using the `$currentElementId` reactive store.

Design choices:

1. **Piping rows navigate to source component** — piping exists on connections between components; the source (upstream) component is the natural owner
2. **Only component markers are clickable in elevation profile** — connection lines span between two components and don't map to a single inspectable entity
3. **Inspector auto-opens** when a results item is clicked, even if it was previously closed
4. **Both panels visible simultaneously** — the results overlay (left, max 800px) and inspector sidebar (right) can coexist

### Rationale

- **Existing pattern**: The schematic click handler already uses `navigationStore.navigateTo()` + `workspaceStore.setInspectorOpen(true)`. Replicating this pattern in results views creates a consistent UX.
- **Source component for piping**: Engineers mentally associate pipe segments with their upstream equipment. Navigating to the source component gives context for the piping configuration.
- **Auto-open inspector**: If a user clicks a results item, they clearly want to see details. Opening the inspector removes a friction step.

### Consequences

**Positive:**

- Seamless navigation between results data and component configuration
- Consistent selection highlighting across all results views
- No new stores or state management — leverages existing `currentElementId`

**Negative:**

- Clicking a piping row navigates to the source component, not the connection itself (connections are not directly editable entities)
- Connection lines in elevation profile are not clickable (could be confusing if users expect them to be)

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
