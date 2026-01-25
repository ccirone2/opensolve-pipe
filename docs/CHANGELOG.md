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
