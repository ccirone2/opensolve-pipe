# Implementation Plan: Port-Level Elevation Support (Issue #89)

## Overview

Add optional elevation field to the Port model to allow port-specific elevations on components. This enables accurate modeling of:

- Tanks/Reservoirs with ports at different heights (bottom drain, side fill, top overflow)
- Pumps with suction and discharge nozzles at different elevations
- Heat exchangers with shell/tube connections at different heights
- Vertical equipment where connection points span multiple elevations

## Implementation Summary

### 1. Backend Changes

#### 1.1 Port Model (`apps/api/src/opensolve_pipe/models/ports.py`)

- Added optional `elevation: Elevation | None = None` field to `Port` class
- Updated docstring to explain the inheritance behavior

#### 1.2 BaseComponent (`apps/api/src/opensolve_pipe/models/components.py`)

- Added `get_port_elevation(port_id: str) -> float` method
- Returns port-specific elevation if set, otherwise inherits component elevation
- Raises `ValueError` if port_id not found

### 2. Frontend Changes

#### 2.1 Port Interface (`apps/web/src/lib/models/components.ts`)

- Added optional `elevation?: number` field to `Port` interface
- Updated interface documentation

#### 2.2 Helper Function

- Added `getPortElevation(component: Component, portId: string): number`
- Mirrors Python implementation behavior

### 3. Tests Added

#### Backend Tests (`apps/api/tests/test_models/`)

- `test_ports.py::TestPortElevation` - 9 tests for Port elevation field
- `test_components.py::TestGetPortElevation` - 7 tests for get_port_elevation method

#### Frontend Tests (`apps/web/src/lib/models/__tests__/`)

- `components.test.ts` - 13 tests for getPortElevation and Port interface

### 4. Acceptance Criteria Status

- [x] Add optional `elevation` field to Port model
- [x] Add `get_port_elevation()` method to BaseComponent
- [ ] Update solver service to use port-level elevations (deferred - requires careful analysis)
- [ ] Update frontend forms to allow port elevation input (deferred - separate PR)
- [x] Add unit tests for elevation inheritance logic
- [ ] Update documentation (minimal updates in code, full docs separate PR)

### 5. Notes

The solver service changes were intentionally deferred to a follow-up PR because:

1. The current implementation establishes the foundation (data model + methods)
2. Solver changes require careful analysis of all elevation usage points
3. Frontend form changes should come with the solver update for a complete feature

## Test Results

- Backend: 629 tests passed
- Frontend: 86 tests passed
- Linting: All checks passed
- Type checking: No errors or warnings
