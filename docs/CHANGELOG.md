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

- **Protocol Interfaces Module** (PR #118)
  - `protocols/` module for type-safe structural contracts
  - `NetworkSolver` protocol for solver strategies
  - `HasPorts`, `HeadSource`, `HeadLossCalculator` protocols for component interfaces
  - `FluidPropertyProvider` protocol for fluid property services
  - ADR-008: Protocol-based interfaces decision

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

- Looped network support (EPANET integration)
- Server-side project storage for large projects
- Pump curve digitization from images
- Global pump database
- Export to EPANET format
- Cost estimation utility
- Pipe sizing optimization

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
