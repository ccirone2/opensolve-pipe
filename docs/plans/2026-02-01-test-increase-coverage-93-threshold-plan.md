---
title: "test: increase test coverage to meet 93% threshold"
type: test
date: 2026-02-01
issue: "#146"
---

## Overview

Current test coverage is 88.44%, below the required 93% threshold. The main contributor is `epanet.py` at 53% coverage. This plan adds targeted tests to reach the 93% threshold.

## Problem Statement / Motivation

The coverage threshold was increased to 93% per project standards. The `epanet.py` module has significant untested code paths that need coverage to pass pre-commit hooks and CI.

## Current Coverage Analysis

| Module | Coverage | Gap | Priority |
|--------|----------|-----|----------|
| `services/solver/epanet.py` | 53% | 40% | **HIGH** |
| `services/solver/network.py` | 90% | 3% | LOW |
| `services/solver/simple.py` | 89% | 4% | LOW |
| `models/reference_node.py` | 89% | 4% | MEDIUM |

**Focus:** `epanet.py` - improving from 53% to 80%+ will bring overall coverage above 93%.

## Proposed Solution

Add comprehensive tests for `epanet.py` covering:

1. **Component building** - IdealReferenceNode, NonIdealReferenceNode, Plug
2. **Valve handling** - PRV, PSV, FCV, gate/ball valves, status handling
3. **Connection handling** - Error paths, port resolution
4. **Helper functions** - `_get_valve_k_factor`, `_get_wntr_node_for_port`
5. **Results conversion** - Piping results, pump results, error handling
6. **End-to-end integration** - Full solve with various network types

## Technical Approach

### Test Strategy

Follow existing patterns from `test_viscosity_correction.py` and `test_looped_solver.py`:

- Unit tests for individual functions
- Integration tests with real WNTR library
- Fixture-based test data
- Clear test class organization

### Implementation Phases

#### Phase 1: Component Building Tests

Test `_add_component_to_wntr()` for uncovered component types:

```python
# tests/test_services/test_solver/test_epanet.py

class TestAddIdealReferenceNode:
    def test_ideal_reference_node_creates_reservoir(self):
        """IdealReferenceNode should create WNTR reservoir."""

class TestAddNonIdealReferenceNode:
    def test_non_ideal_with_curve_uses_first_point(self):
        """NonIdealReferenceNode with curve uses first pressure point."""

    def test_non_ideal_without_curve_uses_elevation(self):
        """NonIdealReferenceNode without curve falls back to elevation."""

class TestAddPlug:
    def test_plug_creates_zero_demand_junction(self):
        """Plug creates junction with zero demand."""
```

**Files:** `tests/test_services/test_solver/test_epanet.py`
**Lines covered:** 196-224

#### Phase 2: Valve Component Tests

Test valve handling for all types and statuses:

```python
class TestAddValveComponent:
    def test_prv_valve_creates_wntr_prv(self):
        """PRV creates WNTR PRV valve with correct setting."""

    def test_psv_valve_creates_wntr_psv(self):
        """PSV creates WNTR PSV valve with correct setting."""

    def test_fcv_valve_creates_wntr_fcv(self):
        """FCV creates WNTR FCV valve with flow setting."""

    def test_gate_valve_creates_pipe_with_k_factor(self):
        """Gate valve creates pipe with appropriate K-factor."""

    def test_failed_closed_valve_high_k_factor(self):
        """FAILED_CLOSED valve has very high K-factor."""

    def test_failed_open_control_valve_creates_pipe(self):
        """FAILED_OPEN control valve creates open pipe."""
```

**Files:** `tests/test_services/test_solver/test_epanet.py`
**Lines covered:** 270-400

#### Phase 3: Valve K-Factor Tests

Test `_get_valve_k_factor()` function:

```python
class TestGetValveKFactor:
    def test_failed_closed_returns_very_high_k(self):
        """FAILED_CLOSED returns 1e6 K-factor."""

    def test_failed_open_returns_base_k(self):
        """FAILED_OPEN returns base K for valve type."""

    def test_active_gate_valve_base_k(self):
        """ACTIVE gate valve returns 0.2 K-factor."""

    def test_position_affects_k_factor(self):
        """Partially closed valve has higher K-factor."""

    def test_nearly_closed_position_very_high_k(self):
        """Position < 0.01 returns 1e6 K-factor."""
```

**Files:** `tests/test_services/test_solver/test_epanet.py`
**Lines covered:** 672-711

#### Phase 4: Connection and Port Tests

Test connection handling and port resolution:

```python
class TestAddConnectionToWNTR:
    def test_missing_from_component_warns(self):
        """Connection with missing from_component adds warning."""

    def test_missing_to_component_warns(self):
        """Connection with missing to_component adds warning."""

    def test_unresolvable_ports_warns(self):
        """Unresolvable ports add topology warning."""

class TestGetWNTRNodeForPort:
    def test_pump_inlet_returns_suction_junction(self):
        """Pump inlet direction returns suction junction."""

    def test_pump_outlet_returns_discharge_junction(self):
        """Pump outlet direction returns discharge junction."""

    def test_valve_inlet_returns_inlet_junction(self):
        """Valve inlet direction returns inlet junction."""

    def test_branch_matches_port_id(self):
        """Branch component matches by port ID."""
```

**Files:** `tests/test_services/test_solver/test_epanet.py`
**Lines covered:** 549-666

#### Phase 5: Results Conversion Tests

Test `convert_wntr_results()` function:

```python
class TestConvertWNTRResults:
    def test_converts_node_pressure_to_psi(self):
        """Node pressure converted from m to psi."""

    def test_converts_node_head_to_feet(self):
        """Node head converted from m to feet."""

    def test_piping_flow_converted_to_gpm(self):
        """Pipe flow converted from m³/s to GPM."""

    def test_piping_velocity_converted_to_fps(self):
        """Pipe velocity converted from m/s to ft/s."""

    def test_reynolds_number_calculated(self):
        """Reynolds number calculated for each pipe."""

    def test_friction_factor_calculated(self):
        """Friction factor calculated from Reynolds."""

    def test_pump_results_extracted(self):
        """Pump operating point extracted correctly."""
```

**Files:** `tests/test_services/test_solver/test_epanet.py`
**Lines covered:** 753-931

#### Phase 6: Error Handling Tests

Test error paths and edge cases:

```python
class TestRunEpanetSimulation:
    def test_convergence_error_message(self):
        """Convergence failure returns helpful message."""

    def test_negative_pressure_error_message(self):
        """Negative pressure failure returns helpful message."""

class TestSolveWithEpanet:
    def test_build_errors_return_failure(self):
        """Build errors prevent simulation and return failure."""

    def test_simulation_errors_return_failure(self):
        """Simulation errors return failure state."""
```

**Files:** `tests/test_services/test_solver/test_epanet.py`
**Lines covered:** 738-745, 970-992

#### Phase 7: Integration Tests

Full solver integration with various networks:

```python
class TestEpanetIntegration:
    def test_simple_reservoir_pipe_tank(self):
        """Simple network solves correctly."""

    def test_network_with_prv_valve(self):
        """Network with PRV valve solves."""

    def test_network_with_pump_and_valves(self):
        """Complex network with pump and valves solves."""

    def test_network_with_ideal_reference_node(self):
        """Network with IdealReferenceNode solves."""
```

**Files:** `tests/test_services/test_solver/test_epanet_integration.py`

## Acceptance Criteria

### Functional Requirements

- [x] Overall test coverage ≥ 93%
- [x] `epanet.py` coverage ≥ 80%
- [x] All existing tests continue to pass
- [x] New tests follow existing patterns and conventions

### Non-Functional Requirements

- [x] Tests run in < 30 seconds
- [x] No flaky tests
- [x] Clear test names describing behavior

### Quality Gates

- [x] Ruff and mypy pass
- [x] All tests pass
- [x] Coverage threshold met (93%)

## Files to Create/Modify

### Modified Files

#### `apps/api/tests/test_services/test_solver/test_epanet.py`

Add test classes:

- `TestAddIdealReferenceNode`
- `TestAddNonIdealReferenceNode`
- `TestAddPlug`
- `TestAddValveComponent`
- `TestGetValveKFactor`
- `TestAddConnectionToWNTR`
- `TestGetWNTRNodeForPort`
- `TestConvertWNTRResults`
- `TestRunEpanetSimulation`
- `TestSolveWithEpanet`

### New Files

#### `apps/api/tests/test_services/test_solver/test_epanet_integration.py`

Integration tests for full EPANET solve workflow with various network types.

## Success Metrics

- Coverage increases from 88.44% to ≥ 93%
- `epanet.py` coverage increases from 53% to ≥ 80%
- All 800+ tests pass
- Pre-commit hooks pass

## Dependencies & Risks

### Dependencies

- WNTR library must be available for integration tests
- Existing fixtures in `conftest.py`

### Risks

| Risk | Mitigation |
|------|------------|
| EPANET simulation may be slow | Use smaller test networks |
| Mocking WNTR internals is fragile | Prefer integration tests with real WNTR |
| Edge cases may be hard to trigger | Use mock objects for error paths only |

## Implementation Notes

### Key Helper Functions to Test

1. `_get_valve_k_factor(valve)` - Returns K-factor based on type, position, status
2. `_get_wntr_node_for_port(ctx, comp, port_id, direction)` - Resolves port to WNTR node
3. `_add_component_to_wntr(wn, comp, ctx, project)` - Adds component to WNTR network
4. `_add_connection_to_wntr(wn, conn, ctx, project)` - Adds pipe to WNTR network

### Test Data Patterns

Use existing fixtures from `conftest.py`:

- `sample_reservoir()`, `sample_tank()`, `sample_junction()`
- `sample_pump_curve()`, `sample_pump()`
- `sample_project()`

Create new fixtures for:

- `ideal_reference_node_project()` - Project with IdealReferenceNode
- `valve_test_project()` - Project with various valve types
- `plug_test_project()` - Project with Plug component

## References

### Internal References

- Existing EPANET tests: `tests/test_services/test_solver/test_epanet.py`
- Test patterns: `tests/test_services/test_solver/test_viscosity_correction.py`
- Model fixtures: `tests/test_models/conftest.py`
- EPANET module: `src/opensolve_pipe/services/solver/epanet.py`

### External References

- WNTR documentation: <https://wntr.readthedocs.io/>
- pytest documentation: <https://docs.pytest.org/>

---

Closes #146
