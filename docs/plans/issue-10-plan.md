# Issue #10 Implementation Plan: Simple Solver (Core Hydraulic Calculations)

**GitHub Issue:** [#10](https://github.com/ccirone2/opensolve-pipe/issues/10) - Backend - Implement Simple Solver
**Branch:** `feature/issue-10`
**Pull Request:** [PR #12](https://github.com/ccirone2/opensolve-pipe/pull/12)
**Status:** ✅ **COMPLETE**
**Created:** 2026-01-19
**Completed:** 2026-01-19
**Priority:** CRITICAL - Core calculation engine

---

## Overview

Implement the simple solver for single-path hydraulic networks (no branches).
This is the core hydraulic calculation engine that powers the MVP. It calculates
head losses, finds pump operating points, and determines pressures throughout
the system.

### Objectives

1. Implement Darcy-Weisbach friction factor calculation (Colebrook equation)
2. Implement pipe head loss calculation (friction + minor losses)
3. Create system curve generator and pump curve interpolator
4. Find operating point via curve intersection
5. Calculate node pressures, velocities, Reynolds numbers, NPSH
6. Write comprehensive tests with known solutions

### Dependencies

- Issue #7 (Data Libraries) - Completed
  - Pipe materials with roughness values
  - Fitting K-factors (Crane TP-410)
  - Fluid properties with interpolation
- Issue #2 (Pydantic Models) - Completed
  - Project, Component, PipingSegment models
  - SolvedState, NodeResult, LinkResult, PumpResult models

---

## Technical Background

### Darcy-Weisbach Equation

The fundamental equation for pipe friction head loss:

```text
h_f = f * (L/D) * (v^2 / 2g)
```

Where:

- h_f = head loss (ft or m)
- f = Darcy friction factor (dimensionless)
- L = pipe length
- D = pipe inner diameter
- v = fluid velocity
- g = gravitational acceleration (32.174 ft/s^2 or 9.81 m/s^2)

### Colebrook Equation (Friction Factor)

Implicit equation solved iteratively:

```text
1/sqrt(f) = -2 * log10(e/(3.7*D) + 2.51/(Re*sqrt(f)))
```

Where:

- e = pipe absolute roughness
- D = pipe inner diameter
- Re = Reynolds number = v*D/nu

### K-Factor Method for Minor Losses

From Crane TP-410:

```text
h_minor = K * (v^2 / 2g)
```

For L/D method fittings: `K = f_T * (L/D)`
Where f_T = friction factor at complete turbulence

### System Curve

Total head required = Static head + Friction losses

```text
H_system(Q) = H_static + h_f(Q) + h_minor(Q)
```

System curve is parabolic (head loss proportional to Q^2)

### Operating Point

Where pump curve intersects system curve:

```text
H_pump(Q) = H_system(Q)
```

---

## Implementation Tasks

### Phase 1: Core Friction Calculations

- [x] **Task 1.1:** Create `services/solver/__init__.py` package structure
  - Create solver package directory
  - Add `__init__.py` with exports

- [x] **Task 1.2:** Implement Colebrook friction factor in `friction.py`
  - Use `fluids.friction.friction_factor_Darcy`
  - Handle laminar flow (Re < 2300): f = 64/Re
  - Handle transition zone (2300 < Re < 4000)
  - Handle turbulent flow (Re > 4000): Colebrook

- [x] **Task 1.3:** Implement Reynolds number calculation
  - `Re = v * D / nu`
  - Handle unit conversions (SI internally)

- [x] **Task 1.4:** Implement pipe head loss calculation
  - Darcy-Weisbach for friction losses
  - Sum of K-factors for minor losses
  - Total = friction + minor

### Phase 2: K-Factor Resolution

- [x] **Task 2.1:** Create `k_factors.py` module
  - Import fitting data from `services/data.py`
  - Implement `resolve_fitting_k()` function

- [x] **Task 2.2:** Implement L/D method K-factor calculation
  - Look up f_T from friction factor turbulent table
  - Calculate K = f_T * (L/D)

- [x] **Task 2.3:** Handle fixed K-value fittings
  - Return K directly for K_fixed method fittings

- [x] **Task 2.4:** Implement total K calculation for piping segment
  - Sum K-factors for all fittings via `resolve_fittings_total_k()`
  - Account for fitting quantities

### Phase 3: System Curve Generation

- [x] **Task 3.1:** Create `simple.py` main solver module
  - Define `SimpleSolverOptions` dataclass
  - Define `SolverResult` dataclass
  - Define solver entry point functions

- [x] **Task 3.2:** Implement component chain traversal
  - `build_system_curve_function()` for parametric calculation
  - Calculate static head (elevation difference)

- [x] **Task 3.3:** Implement system curve generator
  - `generate_system_curve()` calculates head loss at multiple flow rates
  - Generate (flow, head) pairs for curve
  - Handle zero-flow case (returns static head)

### Phase 4: Pump Curve Handling

- [x] **Task 4.1:** Implement pump curve interpolator
  - `build_pump_curve_interpolator()` using `scipy.interpolate.CubicSpline`
  - Handle FlowHeadPoint curve points from pump model
  - Extrapolate for shutoff head and beyond max flow

- [x] **Task 4.2:** Implement operating point finder
  - `find_operating_point()` using `scipy.optimize.brentq`
  - Handle no-intersection case (pump cannot overcome static)
  - Handle curve beyond range (returns max flow point)

### Phase 5: Results Calculation

- [x] **Task 5.1:** Calculate node pressures
  - Returned in SolverResult as part of detailed results
  - Static head and total head loss available

- [x] **Task 5.2:** Calculate link results
  - Flow rate (from operating point)
  - Velocity via `calculate_pipe_head_loss_fps()`
  - Reynolds number
  - Friction factor
  - Head loss

- [x] **Task 5.3:** Calculate pump results
  - Operating flow and head in `SolverResult`
  - System curve data for visualization
  - Pump curve data for visualization

- [x] **Task 5.4:** Implement `SolverResult` assembly
  - Converged status
  - Operating point (flow, head)
  - Detailed hydraulic results (velocity, Reynolds, friction factor)
  - Curve data for visualization

### Phase 6: NPSH Calculation

- [x] **Task 6.1:** Implement NPSH available calculation
  - `calculate_npsh_available()` function
  - NPSH_a = P_atm/gamma + H_s - h_f_suction - P_v/gamma
  - P_atm = atmospheric pressure (configurable)
  - H_s = static suction head (positive if above pump)
  - h_f_suction = friction losses in suction piping
  - P_v = vapor pressure of fluid

### Phase 7: Tests

- [x] **Task 7.1:** Test friction factor calculations (45 tests)
  - Laminar: Re=1000, f=0.064
  - Turbulent: Re=100000, verify Colebrook
  - Compare to `fluids` library

- [x] **Task 7.2:** Test head loss calculations (45 tests)
  - Known pipe: 100ft, 4" Sch40, 100 GPM water
  - Verify against hand calculation

- [x] **Task 7.3:** Test K-factor resolution (38 tests)
  - L/D method calculations
  - Fixed K value fittings
  - Total K for fitting lists

- [x] **Task 7.4:** Test operating point (28 tests)
  - Known pump curve + system curve
  - Verify intersection point
  - Test convenience function `solve_water_system()`

- [x] **Task 7.5:** Test full solver with reference problem
  - 111 solver tests total
  - All tests pass with < 1% error

---

## File Structure

```text
apps/api/src/opensolve_pipe/
  services/
    __init__.py
    data.py                    # (existing - Issue #7)
    solver/
      __init__.py              # NEW - Package init with exports
      friction.py              # NEW - Friction factor calculations
      k_factors.py             # NEW - K-factor resolution
      simple.py                # NEW - Simple solver main module
      types.py                 # NEW - Solver-specific types
tests/test_services/
  __init__.py
  test_data.py                 # (existing - Issue #7)
  test_solver/
    __init__.py                # NEW
    test_friction.py           # NEW - Friction factor tests
    test_k_factors.py          # NEW - K-factor tests
    test_simple.py             # NEW - Simple solver tests
```

---

## API Interface

### Main Solver Function

```python
from dataclasses import dataclass
from typing import Tuple


@dataclass
class SimpleSolverOptions:
    """Options for the simple solver."""
    max_iterations: int = 100
    tolerance: float = 0.001
    flow_range_gpm: Tuple[float, float] = (0.001, 1000)
    num_curve_points: int = 51


def solve_simple_network(
    project: Project,
    options: SimpleSolverOptions | None = None
) -> SolvedState:
    """
    Solve a single-path hydraulic network.

    Algorithm:
    1. Validate network topology (single path, has pump)
    2. Calculate static head difference
    3. Generate system curve (head vs flow)
    4. Build pump curve interpolator
    5. Find operating point (curve intersection)
    6. Calculate all node/link results at operating point

    Args:
        project: Project containing network definition
        options: Solver options (uses defaults if None)

    Returns:
        SolvedState with converged=True if successful

    Raises:
        ValueError: If network topology is invalid
    """
```

### Supporting Functions

```python
def calculate_friction_factor(
    reynolds: float,
    relative_roughness: float
) -> float:
    """Calculate Darcy friction factor using Colebrook equation."""


def calculate_pipe_head_loss(
    pipe: PipeDefinition,
    fittings: list[Fitting],
    flow_gpm: float,
    fluid: FluidProperties
) -> float:
    """Calculate total head loss through pipe segment."""


def generate_system_curve(
    project: Project,
    flow_range: Tuple[float, float],
    num_points: int = 51
) -> list[Tuple[float, float]]:
    """Generate system curve as list of (flow, head) points."""


def find_operating_point(
    pump_curve: Callable[[float], float],
    system_curve: Callable[[float], float],
    flow_range: Tuple[float, float]
) -> Tuple[float, float] | None:
    """Find pump-system curve intersection."""


def calculate_npsh_available(
    suction_pressure_ft: float,
    suction_losses_ft: float,
    fluid: FluidProperties,
    elevation_ft: float = 0
) -> float:
    """Calculate NPSH available at pump suction."""
```

---

## Test Cases

### Test Case 1: Simple Pump System

```text
Reservoir (100 ft elevation)
    |
    v
Pump (0 ft elevation)
    |
100 ft of 4" Sch40 carbon steel pipe
2x 90 long radius elbows
1x gate valve
    |
    v
Tank (50 ft elevation)

Fluid: Water at 68F

Pump curve:
  0 GPM -> 80 ft
  100 GPM -> 70 ft
  200 GPM -> 50 ft
  300 GPM -> 20 ft

Expected results:
- Operating flow: ~180 GPM
- Pump head: ~55 ft
- Velocity in pipe: ~4.5 ft/s
- Reynolds number: ~150,000
```

### Test Case 2: High Friction System

```text
Same as Test 1, but:
- 500 ft of 2" Sch40 pipe
- Expected: Lower flow due to higher friction
```

### Test Case 3: No Solution

```text
- Static head > pump shutoff head
- Expected: converged=False with error message
```

---

## Acceptance Criteria

1. **Friction Calculations**
   - [x] Colebrook equation converges (via fluids library)
   - [x] Laminar/turbulent transition handled correctly
   - [x] Results match `fluids` library exactly (uses same library)

2. **K-Factor Resolution**
   - [x] All FittingType enum values resolve correctly
   - [x] L/D method uses correct f_T values from data module
   - [x] Fixed K values returned correctly

3. **System Curve**
   - [x] Monotonically increasing with flow
   - [x] Correct static head at Q=0
   - [x] Parabolic shape (h proportional to Q^2)

4. **Operating Point**
   - [x] Finds intersection within tolerance (Brent's method)
   - [x] Handles no-solution case gracefully (returns None)
   - [x] Results match hand calculations < 1% error

5. **NPSH**
   - [x] Correct calculation per Hydraulic Institute standards
   - [x] Accounts for suction losses and vapor pressure

6. **Test Coverage**
   - [x] 111 solver tests with >95% code coverage
   - [x] Reference problems validate accuracy
   - [x] Edge cases covered

7. **Code Quality**
   - [x] All 353 tests pass
   - [x] mypy type checking passes
   - [x] ruff linting passes

---

## References

1. **Crane TP-410** - Flow of Fluids Through Valves, Fittings, and Pipe
2. **Hydraulic Institute Standards** - NPSH calculations
3. **fluids library** - Python friction factor implementations
4. **scipy** - Optimization and interpolation

---

## Notes

### Design Decisions

1. **SI units internally:** All calculations in SI (m, kg, Pa, m^3/s).
   Convert from/to user units at boundaries.

2. **fluids library for friction:** Use `fluids.friction_factor()` which
   implements multiple methods (Colebrook, Churchill, etc.) with accuracy.

3. **scipy for interpolation:** Use `scipy.interpolate.CubicSpline` for
   smooth pump curve interpolation.

4. **scipy.optimize.brentq:** Reliable root-finding for curve intersection.

5. **Fail gracefully:** Return `SolvedState(converged=False)` with error
   message rather than raising exceptions for no-solution cases.

### Performance Considerations

- System curve generation is O(n * m) where n = flow points, m = components
- Colebrook iteration typically converges in 5-10 iterations
- Total solve time target: < 1 second for simple networks

### Future Extensions

- Network solver using WNTR for branching networks
- Parallel pump configurations
- Variable speed pump curves
- Transient analysis (future phase)

---

**Last Updated:** 2026-01-19
