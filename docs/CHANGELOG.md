# Changelog

All notable changes to OpenSolve Pipe will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-01-19

### Added

#### Backend (API)

- Unit conversion system with SI/Imperial support
- Fluid properties service with temperature-dependent calculations
- Simple solver for single-path hydraulic networks
- Pipe materials and fittings data libraries (Crane TP-410)
- `/api/v1/solve` endpoint for network solving
- `/api/v1/fluids` endpoints for fluid properties
- `/api/v1/solve/simple` endpoint for pump-pipe systems
- Health check endpoint at `/health`

#### Frontend (Web)

- SvelteKit application with TypeScript
- Panel Navigator for component-by-component editing
- Component forms for all node and link types
- Results display with pump curve visualization
- URL encoding/decoding for shareable projects
- Project state management with undo/redo
- API client with retry logic and error handling
- Solve button with loading state and keyboard shortcut

#### Infrastructure

- GitHub Actions CI/CD pipeline
- Vercel configuration for frontend deployment
- Docker and Railway configuration for backend deployment
- Pre-commit hooks for code quality

#### Documentation

- Getting Started guide
- Component reference
- FAQ
- Calculation methodology

### Technical Details

- Python 3.11 with FastAPI for backend
- Svelte 5 with runes for frontend
- Chart.js for pump curve visualization
- Tailwind CSS for styling
- Vitest for unit tests
- Playwright for E2E tests

## [Unreleased]

### Added

#### Backend (API)

- **Pump Operating Modes and Status** (PR #114)
  - `PumpOperatingMode` enum: fixed_speed, variable_speed, controlled_pressure, controlled_flow, off
  - `PumpStatus` enum: running, off_check, off_no_check, locked_out
  - Updated `PumpComponent` with operating_mode, status, control_setpoint, viscosity_correction_enabled fields
  - Validation for controlled modes requiring setpoints
  - VFD (Variable Frequency Drive) support for pressure/flow control modes

- **Protocol Interfaces Module** (PR #118, #119, #121, #124)
  - `protocols/` module for type-safe structural contracts
  - `NetworkSolver` protocol for solver strategies with method signatures
  - `HeadSource` protocol for components with fixed head boundary conditions
  - `HeadLossCalculator` protocol for components that cause head loss
  - `HasPorts`, `FluidPropertyProvider` protocols for component interfaces
  - `SimpleSolver` and `BranchingSolver` strategy classes implementing NetworkSolver
  - `SolverRegistry` for selecting appropriate solver by network topology
  - `solve_project()` refactored to use registry pattern
  - `get_source_head()` simplified using HeadSource protocol
  - `calculate_component_head_loss()` helper using HeadLossCalculator protocol
  - `total_head` property added to IdealReferenceNode and NonIdealReferenceNode
  - `calculate_head_loss()` method added to ValveComponent, HeatExchanger, Strainer, Orifice
  - `get_valve_k_factor()` helper for valve K-factor lookup
  - ADR-008: Protocol-based interfaces decision

- **Looped Network Solver Strategy** (PR #129)
  - `LoopedSolver` class implementing NetworkSolver protocol for looped networks
  - Automatic network type detection using graph cycle analysis
  - WNTR/EPANET integration for gradient-based network solving
  - SolvedState to SolverState conversion for consistent API
  - Registered in default solver registry for automatic selection

- **Complex Network Validation Tests** (PR #137)
  - Parallel pumps test: equal flow split, flow continuity
  - Series pumps test: same flow through stages, head addition
  - Looped distribution test: grid topology with demands
  - Building riser test: multi-floor vertical distribution
  - Fire sprinkler loop test: cross-connected mains
  - Performance benchmarks: solve time < 1s for simple networks

- **WNTR/EPANET Integration** (PR #128)
  - `wntr` dependency added to pyproject.toml
  - `epanet.py` wrapper module (700+ lines) for EPANET solver integration
  - `build_wntr_network()` function for converting component chain to WNTR graph
  - Component type mapping: Reservoir→WNTR Reservoir, Tank→WNTR Tank, Junction→WNTR Junction
  - Pump→WNTR Pump with curve conversion, Valve→WNTR Valve (PRV, PSV, FCV, TCV)
  - `run_epanet_simulation()` and `solve_with_epanet()` functions
  - Results conversion back to SolvedState format
  - Comprehensive test suite in `test_epanet.py` and `test_epanet_comprehensive.py`

- **Component Chain to EPANET Adapter** (PR #130)
  - Reservoir, Tank, Junction → WNTR node types
  - Pump with curve conversion to WNTR format
  - Valve type mapping (gate→TCV, ball→TCV, check→CV, PRV→PRV, PSV→PSV, FCV→FCV)
  - PipeConnection → WNTR Pipe link with friction parameters
  - Fittings → equivalent pipe lengths for K-factor conversion
  - Elevation handling for NPSH calculations

- **Solver Router Enhancement** (PR #131)
  - `NetworkType.LOOPED` detection in `classify_network()` using graph cycle analysis
  - `SolverRegistry` updated to include `LoopedSolver` for automatic selection
  - Clear error messages for unsupported network topologies
  - Logging of solver selection for debugging

- **Valve Status States** (PR #115)
  - `ValveStatus` enum: active, isolated, failed_open, failed_closed, locked_open
  - Updated `ValveComponent` with status field for operational state tracking
  - Support for isolation and failure mode scenarios

- **Enhanced Solver Result Fields** (PR #116)
  - `ViscosityCorrectionFactors` model with c_q, c_h, c_eta factors per ANSI/HI 9.6.7
  - `ControlValveResult` model for control valve behavior tracking
  - Enhanced `PumpResult` with status, actual_speed, viscosity_correction_applied, viscosity_correction_factors
  - Enhanced `SolvedState` with control_valve_results dictionary

- **Port-Based Architecture** (PR #64)
  - Port model with id, nominal_size, and direction (inlet/outlet/bidirectional)
  - PipeConnection model for explicit port-to-port connections
  - Port factory functions for all component types
  - Connection validation (size compatibility, direction checks)

- **Port-Level Elevation Support** (PR #90)
  - Optional `elevation` field on Port model for port-specific heights
  - `get_port_elevation(port_id)` method on BaseComponent for elevation lookup
  - Inheritance behavior: ports without elevation use parent component elevation
  - Enables accurate modeling of tall equipment (tanks, vertical pumps, heat exchangers)

- **Reference Node Components** (PR #65)
  - IdealReferenceNode: Fixed pressure boundary condition
  - NonIdealReferenceNode: Pressure-flow curve boundary with interpolation
  - FlowPressurePoint model for curve data

- **Plug/Cap Component** (PR #65)
  - Dead-end boundary condition (zero flow)
  - Single port with configurable size

- **Branch Components** (PR #66)
  - TeeBranch: 90° fitting with run_inlet, run_outlet, branch ports
  - WyeBranch: Angled fitting (22.5-60°) for smoother flow transitions
  - CrossBranch: Four-way fitting with perpendicular branches
  - Configurable port sizes for reduced-size branches

#### Frontend (Web)

- **Pump and Valve TypeScript Models** (PR #117)
  - TypeScript types for PumpOperatingMode, PumpStatus, ValveStatus
  - Human-readable label maps for all enums (PUMP_OPERATING_MODE_LABELS, etc.)
  - Updated PumpComponent and ValveComponent interfaces
  - ViscosityCorrectionFactors and ControlValveResult types
  - Enhanced PumpResult and SolvedState types
  - Updated PumpForm to use new running/off_check status values
  - Updated example project with new pump/valve status fields

- **Port Connection Models** (PR #67)
  - Port and PortDirection types matching backend
  - PipeConnection type for port-based connections
  - Port factory functions for all component types (14 functions)
  - Type guards for new component types
  - Project store connection management (add/remove/update)

- **Reference Node Forms** (PR #68)
  - ReferenceNodeForm for ideal and non-ideal nodes
  - Pressure-flow curve editor table for non-ideal nodes
  - PlugForm for dead-end configuration

- **Branch Component Forms** (PR #69)
  - TeeBranchForm with angle and port size configuration
  - WyeBranchForm with angled branch visualization
  - CrossBranchForm with four-way port configuration
  - Visual SVG diagrams showing port arrangement
  - Validation warnings for unusual configurations

- **Schematic Viewer** (PR #132)
  - `SchematicViewer.svelte` - main container with toolbar
  - `SchematicCanvas.svelte` - SVG canvas with zoom/pan support
  - Viewport management with fit-to-screen functionality
  - Pan with drag support (click and drag to move)
  - Zoom controls with level indicator (mousewheel + buttons)
  - "Fit to View" button for auto-centering

- **Graph Layout Algorithm** (PR #133)
  - `layout.ts` with automatic component positioning
  - Left-to-right flow layout optimized for hydraulic networks
  - Linear chain handling with consistent spacing
  - Branch handling for split/merge points (tees, wyes, crosses)
  - Dagre-based layout with hydraulic network optimizations

- **Component Symbols** (PR #134)
  - Core SVG symbols: `ReservoirSymbol`, `TankSymbol`, `JunctionSymbol`, `PumpSymbol`, `ValveSymbol`, `PipeSymbol`
  - `GenericSymbol` fallback for unknown component types
  - Dark/light theme support via CSS variables
  - Status indicators on pump/valve symbols (running/off, open/closed)
  - Symbol factory function for component type → symbol mapping
  - `HeatExchangerSymbol` - shell-and-tube pattern with tube bundle lines
  - `StrainerSymbol` - Y-strainer with mesh pattern
  - `OrificeSymbol` - restriction plate with gap
  - `SprinklerSymbol` - nozzle with spray pattern
  - `PlugSymbol` - cap/dead-end symbol
  - `ReferenceNodeSymbol` - diamond boundary marker (P for ideal, PQ for non-ideal)
  - `TeeSymbol` - T-junction with 3 connection points
  - `WyeSymbol` - Y-junction with angled branch
  - `CrossSymbol` - four-way intersection with 4 ports

- **Schematic Interaction** (PR #135)
  - Click handler selects component and opens property panel
  - Hover highlight effect with visual feedback
  - Tooltip with component name on hover
  - Result values on hover (pressure, HGL) when solved
  - Selection highlight with border/glow effect

- **Branching UI Support** (PR #136)
  - `BranchSelector.svelte` for tee/wye/cross component navigation
  - Shows downstream connections visually
  - "Add Branch" functionality for creating new downstream paths
  - Loop closure feature (connect to existing component)
  - Topology validation to prevent invalid connections

- **Workspace Layout System** (PR #172, Issues #164-171)
  - `workspaceStore` with persistent layout state (sidebar, inspector, focus mode, canvas zoom)
  - localStorage-backed persistence across sessions
  - Multi-tab sidebar with Component Tree, Project Config, and System Results panels
  - Keyboard shortcuts for sidebar tabs (Ctrl+1/2/3)
  - `ProjectConfigPanel` with collapsible Fluid, Units, Solver, Pump Library sections
  - `SystemResultsPanel` with solve status, component counts, node/flow results tables
  - `PropertyPanel` rewrite with `MetricsStrip` (pressure/flow/velocity/head at a glance)
  - `ProjectSummary` empty-state panel with project stats and quick-solve button
  - Inline component actions in inspector (duplicate, move up/down, delete)
  - CSS utility classes: `.section-heading`, `.card`, `.result-card`, `.form-input`, `.mono-value`
  - Smooth panel transitions via CSS `grid-template-columns` animation
  - Loading spinner for URL-decoded projects
  - Improved empty state with larger "Add Component" CTA
  - `prefers-reduced-motion` media query support
  - Toolbar breadcrumb navigation: Project / Component / Tab
  - Interactive status bar (click Converged/Failed/warnings to open Results)
  - Mobile bottom sheet with swipe gestures (collapsed/half/full snap points)
  - Mobile nav bar with Components/Settings/Results/Solve tabs
  - Desktop Focus Mode combining spatial schematic + sequential PanelNavigator (Ctrl+Shift+F)

- **UI Audit Remaining Items** (PR #174, Issue #173)
  - Canvas zoom sync: SchematicViewer persists zoom level to workspaceStore
  - Bidirectional highlighting: ComponentTree auto-scrolls to selected component
  - View system: restructured routes to `/p/[encoded]/`, added stub results and cost views
  - Form CSS consistency: replaced inline Tailwind input/select patterns with `.form-input` utility
  - Component form registry: `FORM_REGISTRY` map replaces 15-branch if/else chain in ElementPanel

- **Pump Operating Mode UI Controls** (PR #111)
  - Operating mode dropdown (fixed_speed, variable_speed, controlled_pressure, controlled_flow)
  - Conditional setpoint fields for controlled modes (pressure/flow setpoint)
  - Speed ratio input for variable_speed mode (0.5-1.2 range)
  - Viscosity correction checkbox
  - Status dropdown in PumpForm.svelte (running, off_check)

- **Valve Status UI Controls** (PR #112)
  - Status dropdown (active, failed_open, failed_closed, isolated, locked_open)
  - Visual indicators for failure states (warning badges)
  - Conditional field behavior based on status (setpoint disabled when failed)
  - Implemented in ValveForm.svelte

- **Enhanced Results Display** (PR #113, #157-160)
  - Pump status badge with color coding (running=green, off=gray, locked=red)
  - Actual speed display for VFD pumps (percentage of rated)
  - Power consumption in HP with kW→HP conversion (×1.341)
  - Efficiency with "(viscosity corrected)" indicator when applicable
  - NPSH Available, Required, and Margin with percentage calculation
  - Viscosity correction factors expandable section (C_Q, C_H, C_η)
  - Control valve results: status, setpoint vs actual, position, pressure drop
  - Null safety fixes for result fields (formatNumber helper with null handling)

### Fixed

#### Backend (API)

- **NPSH Margin Storage** (PR #157)
  - Calculate and store `npsh_margin` in PumpResult (NPSHa - NPSHr)
  - Interpolate NPSHr from pump curve at operating flow
  - Add warning when NPSH margin is negative (cavitation risk)

- **Efficiency Interpolation** (PR #158)
  - Interpolate pump efficiency from efficiency curve at operating flow
  - Apply viscosity correction factor (C_η) when applicable
  - Handle extrapolation for flows outside curve range (use nearest endpoint)

- **Power Calculation** (PR #159)
  - Calculate hydraulic power: Water HP = (Flow × Head × SG) / 3960
  - Calculate brake HP: Brake HP = Water HP / efficiency
  - Convert to kW: Power (kW) = Brake HP × 0.7457
  - Store `power` field in PumpResult (kW)

#### Frontend (Web)

- **Pump Results Card Null Safety** (PR #160)
  - Fixed null reference errors in PumpResultsCard.svelte
  - Added `formatNumber()` helper with null/undefined handling
  - Fixed NPSH section to handle missing npsh_margin gracefully
  - Fixed efficiency and power display for pumps without curves

- **Pump Curve Chart Improvements** (PR #126)
  - Fixed duplicate "Pump Curve" label in tooltip hovertext
  - Fixed Pump Curve legend to show solid circle with line (matches graph)
  - Fixed System Curve legend to show line only without circle marker (matches graph)
  - Changed BEP marker from purple star to amber/orange cross-hair (+) for better visibility
  - Pump curve rendered as smooth quadratic best-fit line with data points overlay
  - Efficiency curve rendered as smooth quadratic best-fit line on secondary Y-axis
  - BEP calculated from mathematical maximum of efficiency curve fit
  - Added quadratic regression functions: `fitQuadratic()`, `evaluateQuadratic()`, `findQuadraticMaximum()`
  - Added curve generators: `generatePumpBestFitCurve()`, `generateEfficiencyBestFitCurve()`
  - Added `interpolateEfficiency()` function for efficiency curve interpolation
  - Operating point tooltip now shows efficiency when efficiency curve is available
  - Added 33 new unit tests for pump model functions

### Changed

- **BREAKING:** Renamed "Nodes/Links" terminology to "Components/Piping" per ADR-006
  - `NodeResult` → `ComponentResult`
  - `LinkResult` → `PipingResult`
  - `node_results` → `component_results`
  - `link_results` → `piping_results`
  - UI tabs renamed from "Nodes"/"Links" to "Components"/"Piping"

- Component categories reorganized:
  - Sources: reservoir, tank, ideal_reference_node, non_ideal_reference_node
  - Connections: junction, tee_branch, wye_branch, cross_branch, plug
  - Equipment: pump, valve, heat_exchanger, strainer, orifice, sprinkler

### Planned Features

- Server-side project storage for large projects (> 50KB)
- Pump curve digitization from images
- Global pump database integration
- Export to EPANET INP format
- Cost estimation utility
- Pipe sizing optimization
- Flow direction arrows on pipe symbols
- Keyboard navigation for schematic viewer
- Manual position override for schematic layout

---

## Release Notes Format

### [Version] - YYYY-MM-DD

#### Added

- New features

#### Changed

- Changes in existing functionality

#### Deprecated

- Soon-to-be removed features

#### Removed

- Removed features

#### Fixed

- Bug fixes

#### Security

- Vulnerability fixes
