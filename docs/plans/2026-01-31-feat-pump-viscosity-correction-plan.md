---
title: "feat: Implement pump viscosity correction per ANSI/HI 9.6.7"
type: feat
date: 2026-01-31
issue: "#110"
---

## Overview

Implement automatic viscosity correction for pumps handling fluids more viscous than water using the Hydraulic Institute method per ANSI/HI 9.6.7. When pumping viscous fluids, pump curves must be de-rated because:

- **Flow capacity decreases** (C_Q < 1.0)
- **Head decreases** (C_H < 1.0)
- **Efficiency decreases** (C_eta < 1.0)
- **Power increases** (higher load)

## Problem Statement / Motivation

Pump curves are typically generated using water as the test fluid. Engineers frequently pump more viscous fluids (glycol mixtures, oils, fuel) and need accurate predictions of reduced pump performance. Without viscosity correction, the solver overestimates pump head and efficiency, leading to:

- Undersized pumps
- Insufficient flow rates
- Higher-than-expected power consumption
- NPSH margin issues

The infrastructure already exists (`ViscosityCorrectionFactors`, `PumpResult.viscosity_correction_applied`, `PumpComponent.viscosity_correction_enabled`) but the calculation logic is missing.

## Proposed Solution

### ANSI/HI 9.6.7 Algorithm

#### Step 1: Calculate viscosity parameter B

```text
B = 16.5 * (nu^0.5 * H_BEP^0.0625) / (Q_BEP^0.375 * N^0.25)
```

Where:

- nu = kinematic viscosity (cSt)
- H_BEP = head at BEP (ft)
- Q_BEP = flow at BEP (GPM)
- N = pump speed (RPM, default 1750)

#### Step 2: Calculate correction factors

```text
C_Q = 1.0 - 4.5 * 10^-3 * B^1.5    (flow correction)
C_H = 1.0 - 7.0 * 10^-4 * B^2.0    (head correction at BEP)
C_eta = B^(-0.0547 * B^0.69)        (efficiency correction)
```

#### Step 3: Apply corrections to pump curve

```text
Q_viscous = Q_water * C_Q
H_viscous = H_water * C_H
eta_viscous = eta_water * C_eta
P_viscous = (Q_viscous * H_viscous * SG) / (3960 * eta_viscous)  [HP]
```

### Implementation Strategy

1. Create new module `viscosity_correction.py` with pure calculation functions
2. Integrate into simple solver before pump curve interpolation
3. Store correction factors in `PumpResult`
4. Add appropriate warnings to results

## Technical Considerations

### Architecture Impacts

- **New module:** `apps/api/src/opensolve_pipe/services/solver/viscosity_correction.py`
- **Solver integration:** Modify `solve_simple_path()` in `network.py` (lines ~460-473)
- **Unit handling:** Calculations in FPS units (GPM, ft, cSt), consistent with existing solver

### Decision Points

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Viscosity threshold | 4.3 cSt | Water at 100°F, standard HI threshold |
| BEP determination | Max efficiency point or 80% shutoff if no efficiency curve | Standard industry practice |
| Default pump speed | 1750 RPM | Standard 4-pole motor speed |
| Correction order | Viscosity first, then VFD affinity laws | Match HI methodology |

### Edge Cases

| Case | Behavior |
|------|----------|
| Viscosity ≤ 4.3 cSt | Skip correction, set `viscosity_correction_applied = false` |
| No efficiency curve | Calculate C_η but set `PumpResult.efficiency = None` |
| Correction factor < 0.3 | Issue warning "Extreme viscosity correction" |
| B parameter > 40 | Issue warning "Outside HI method limits" |
| `viscosity_correction_enabled = false` | Skip correction, issue info warning for viscous fluids |

### Performance Implications

Negligible - adds ~10-20 arithmetic operations per pump.

## Files to Create/Modify

### New Files

#### `apps/api/src/opensolve_pipe/services/solver/viscosity_correction.py`

```python
"""ANSI/HI 9.6.7 Pump viscosity correction calculations."""

from opensolve_pipe.models.pump import FlowHeadPoint
from opensolve_pipe.models.results import ViscosityCorrectionFactors

VISCOSITY_THRESHOLD_CST = 4.3  # Skip correction below this
DEFAULT_PUMP_SPEED_RPM = 1750.0

def calculate_viscosity_parameter_b(
    flow_bep_gpm: float,
    head_bep_ft: float,
    viscosity_cst: float,
    speed_rpm: float = DEFAULT_PUMP_SPEED_RPM,
) -> float:
    """Calculate the viscosity parameter B per ANSI/HI 9.6.7."""
    ...

def calculate_correction_factors(b_parameter: float) -> ViscosityCorrectionFactors:
    """Calculate C_Q, C_H, C_eta from viscosity parameter B."""
    ...

def should_apply_correction(viscosity_cst: float) -> bool:
    """Check if viscosity correction should be applied."""
    return viscosity_cst > VISCOSITY_THRESHOLD_CST

def apply_viscosity_correction(
    pump_curve_points: list[FlowHeadPoint],
    correction_factors: ViscosityCorrectionFactors,
) -> list[FlowHeadPoint]:
    """Return corrected pump curve points."""
    ...

def estimate_bep_from_curve(
    pump_curve_points: list[FlowHeadPoint],
    efficiency_points: list[FlowHeadPoint] | None = None,
) -> tuple[float, float]:
    """Estimate BEP flow and head from pump curve."""
    ...
```

#### `apps/api/tests/test_services/test_solver/test_viscosity_correction.py`

```python
"""Tests for ANSI/HI 9.6.7 viscosity correction."""

import pytest
from opensolve_pipe.services.solver.viscosity_correction import (
    calculate_viscosity_parameter_b,
    calculate_correction_factors,
    should_apply_correction,
    apply_viscosity_correction,
    estimate_bep_from_curve,
)

class TestViscosityParameterB:
    """Tests for B parameter calculation."""

    def test_water_viscosity_low_b(self):
        """Water-like viscosity should produce B close to 1."""
        ...

    def test_known_hi_example(self):
        """Validate against Hydraulic Institute published example."""
        ...

class TestCorrectionFactors:
    """Tests for correction factor calculations."""

    def test_factors_at_b_equals_1(self):
        """B=1 should give factors close to 1.0."""
        ...

    def test_factors_bounds(self):
        """All factors should be between 0 and 1."""
        ...

class TestApplyCorrection:
    """Tests for pump curve correction."""

    def test_curve_flow_reduced(self):
        """Corrected curve should have reduced flow at same head."""
        ...
```

### Modified Files

#### `apps/api/src/opensolve_pipe/services/solver/network.py`

Modify `solve_simple_path()` around line 460-473:

```python
# Before building pump curve interpolator:
if pump_comp.viscosity_correction_enabled and should_apply_correction(viscosity_cst):
    bep_flow, bep_head = estimate_bep_from_curve(pump_curve.points, pump_curve.efficiency_curve)
    b_param = calculate_viscosity_parameter_b(bep_flow, bep_head, viscosity_cst)
    correction_factors = calculate_correction_factors(b_param)
    corrected_points = apply_viscosity_correction(pump_curve.points, correction_factors)
    # Use corrected_points for interpolator
    # Store factors for PumpResult
```

#### `apps/api/src/opensolve_pipe/models/results.py`

Add `b_parameter` field to `ViscosityCorrectionFactors` for debugging (optional):

```python
class ViscosityCorrectionFactors(OpenSolvePipeBaseModel):
    # ... existing fields ...
    b_parameter: float | None = Field(
        default=None,
        description="Viscosity parameter B used in calculation (for debugging)",
    )
```

#### `apps/api/src/opensolve_pipe/models/components.py`

Add `pump_speed_rpm` field to `PumpComponent` (if not present):

```python
pump_speed_rpm: PositiveFloat = Field(
    default=1750.0,
    description="Pump speed in RPM for viscosity correction",
)
```

## Acceptance Criteria

### Functional Requirements

- [ ] Correction factors calculated per ANSI/HI 9.6.7 formulas
- [ ] Pump curve corrected before solving when enabled and viscosity > threshold
- [ ] Results include `viscosity_correction_applied = true` and factors
- [ ] Power calculated with corrected efficiency (when efficiency curve present)
- [ ] Correction skipped for water-like viscosities (< 4.3 cSt)
- [ ] User can disable correction per pump via `viscosity_correction_enabled`
- [ ] Warning issued when correction disabled but fluid is viscous

### Non-Functional Requirements

- [ ] Unit tests with known HI example values (< 1% deviation)
- [ ] Integration test: full solve with glycol 50% at various temperatures
- [ ] Test coverage ≥ 93% for new module
- [ ] Ruff and mypy pass

### Quality Gates

- [ ] All existing tests continue to pass
- [ ] New tests for viscosity correction module
- [ ] Integration tests for solver with viscous fluids
- [ ] Documentation updated in code docstrings

## Success Metrics

- Correction factors match published HI examples within 1%
- Solver produces accurate results for viscous fluids (validated against manual calculations)
- No performance regression for water-based solves

## Dependencies & Risks

### Dependencies

- #103 (viscosity_correction_enabled field) - ✅ Already implemented
- #105 (ViscosityCorrectionFactors model) - ✅ Already implemented
- Fluid properties service for kinematic viscosity - ✅ Exists

### Risks

| Risk | Mitigation |
|------|------------|
| HI formula accuracy | Validate against published examples |
| Efficiency curve missing | Gracefully handle, document limitation |
| Extreme viscosities | Add warnings for out-of-range B parameter |

## Implementation Phases

### Phase 1: Core Calculation Functions (Primary)

1. Create `viscosity_correction.py` module
2. Implement B parameter calculation
3. Implement correction factor calculations
4. Implement BEP estimation
5. Add unit tests with known values

### Phase 2: Solver Integration

1. Integrate into `solve_simple_path()` in `network.py`
2. Apply correction to pump curve before interpolation
3. Populate `PumpResult` fields
4. Add integration tests

### Phase 3: Warnings & Edge Cases

1. Add warning generation for edge cases
2. Handle missing efficiency curve
3. Handle extreme viscosity values
4. Add `pump_speed_rpm` field if needed

## References & Research

### Internal References

- ViscosityCorrectionFactors model: `apps/api/src/opensolve_pipe/models/results.py:74-95`
- PumpResult fields: `apps/api/src/opensolve_pipe/models/results.py:98-140`
- PumpComponent.viscosity_correction_enabled: `apps/api/src/opensolve_pipe/models/components.py:340`
- Simple solver pump handling: `apps/api/src/opensolve_pipe/services/solver/network.py:460-588`
- Unit handling decision: `docs/DECISIONS.md` (ADR-004)

### External References

- ANSI/HI 9.6.7 - Effects of Liquid Viscosity on Rotodynamic Pump Performance
- Hydraulic Institute Standards (<https://www.pumps.org>)
- Crane TP-410 (fluid property reference)

### Related Issues

- Issue #110 - This implementation plan
- Issue #103 - viscosity_correction_enabled field (completed)
- Issue #105 - ViscosityCorrectionFactors model (completed)

---

Closes #110
