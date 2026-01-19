# Issue #9 Implementation Plan: Fluid Properties Service

**GitHub Issue:** #9 - Backend - Implement Fluid Properties Service
**Branch:** `feature/issue-9`
**Status:** Planning
**Created:** 2026-01-19

---

## Overview

Create a dedicated fluid properties service that provides temperature-aware fluid
property calculations with unit conversion support. This builds on the existing
`services/data.py` implementation to provide a higher-level API using the
`fluids` library for more accurate calculations.

### Objectives

1. Create `services/fluids.py` with temperature unit conversion (F, C, K)
2. Integrate with `fluids` library for accurate water property calculations
3. Provide convenience methods for common engineering calculations
4. Write tests comparing results to known engineering values

### Dependencies

- Issue #7 (Data Libraries) - Completed
  - `FluidProperties` model already exists in `models/fluids.py`
  - `get_fluid_properties()` already exists in `services/data.py`
  - `fluids.json` data file already exists

---

## Implementation Analysis

### What Already Exists

From Issue #7, we already have:

- `FluidProperties` Pydantic model with density, viscosity, vapor_pressure
- `get_fluid_properties()` function with water interpolation
- `fluids.json` with water properties at 5C intervals (0-100C)
- Error handling for out-of-range temperatures

### What's Missing (Issue #9 Scope)

1. **Temperature unit conversion** - Currently only accepts Celsius
2. **`fluids` library integration** - For more accurate calculations
3. **Higher-level service API** - With cleaner interface for API endpoints
4. **US Customary unit outputs** - Density in lb/ft, etc.
5. **Validation against known values** - Water at 68F = ~62.32 lb/ft

---

## Service Functions

### Location: `apps/api/src/opensolve_pipe/services/fluids.py`

### Function Signatures

```python
def get_water_properties(
    temperature: float,
    temperature_unit: str = "F"
) -> FluidProperties:
    """
    Get water properties at specified temperature using fluids library.

    Args:
        temperature: Temperature value
        temperature_unit: One of "F", "C", "K"

    Returns:
        FluidProperties with density, viscosity, vapor_pressure in SI units

    Raises:
        TemperatureOutOfRangeError: If temperature outside 0-100C range
        ValueError: If invalid temperature unit
    """


def get_fluid_properties_with_units(
    fluid_definition: FluidDefinition,
    temperature_unit: str = "F"
) -> FluidProperties:
    """
    Get fluid properties from a FluidDefinition model.

    Handles temperature unit conversion and dispatches to appropriate
    calculation method based on fluid type.

    Args:
        fluid_definition: FluidDefinition from project
        temperature_unit: Unit of temperature in fluid_definition

    Returns:
        FluidProperties in SI units
    """


def convert_temperature(
    value: float,
    from_unit: str,
    to_unit: str
) -> float:
    """
    Convert temperature between F, C, and K.

    Args:
        value: Temperature value
        from_unit: Source unit ("F", "C", or "K")
        to_unit: Target unit ("F", "C", or "K")

    Returns:
        Converted temperature value
    """


def density_to_imperial(density_kg_m3: float) -> float:
    """Convert density from kg/m to lb/ft."""


def viscosity_to_imperial(viscosity_m2_s: float) -> float:
    """Convert kinematic viscosity from m/s to ft/s."""
```

---

## Implementation Tasks

### Phase 1: Temperature Conversion

- [ ] **Task 1.1:** Create `services/fluids.py` with module structure
  - Import existing functions from `services/data.py`
  - Add temperature conversion function

- [ ] **Task 1.2:** Implement temperature unit conversion
  - Support F, C, K conversions
  - Handle edge cases (absolute zero, etc.)

### Phase 2: Fluids Library Integration

- [ ] **Task 2.1:** Integrate `fluids` library for water properties
  - Use `fluids.IAPWS95` or `fluids.IAPWS97` for water
  - Compare accuracy vs current interpolation table
  - Fall back to table if fluids library unavailable

- [ ] **Task 2.2:** Implement `get_water_properties()` function
  - Accept temperature in any unit (F, C, K)
  - Return FluidProperties in SI units
  - Use fluids library for calculation

### Phase 3: Higher-Level API

- [ ] **Task 3.1:** Implement `get_fluid_properties_with_units()`
  - Accept FluidDefinition from project model
  - Handle temperature unit from project settings
  - Dispatch to appropriate calculation method

- [ ] **Task 3.2:** Add imperial unit conversion helpers
  - `density_to_imperial()` - kg/m to lb/ft
  - `viscosity_to_imperial()` - m/s to ft/s
  - `pressure_to_imperial()` - Pa to psi

### Phase 4: Tests

- [ ] **Task 4.1:** Test temperature conversions
  - F to C: 68F = 20C
  - C to K: 20C = 293.15K
  - Round-trip conversions

- [ ] **Task 4.2:** Test water properties against known values
  - Water at 68F: density ~62.32 lb/ft (998.2 kg/m)
  - Water at 68F: kinematic viscosity ~1.004e-6 m/s
  - Water at 212F (100C): vapor pressure ~101,325 Pa

- [ ] **Task 4.3:** Test integration with FluidDefinition model
  - Various fluid types
  - Temperature unit handling
  - Error cases

---

## File Structure

```text
apps/api/src/opensolve_pipe/
services/
    __init__.py           # (existing)
    data.py               # (existing - Issue #7)
    fluids.py             # NEW - Higher-level fluid service
tests/test_services/
    __init__.py           # (existing)
    test_data.py          # (existing - Issue #7)
    test_fluids.py        # NEW - Fluid service tests
```

---

## Acceptance Criteria

1. **Temperature Conversion**
   - [ ] F to C conversion accurate to 0.01
   - [ ] C to K conversion accurate to 0.01
   - [ ] All conversions bidirectionally correct

2. **Water Properties**
   - [ ] Water at 68F returns density ~62.32 lb/ft (998.2 kg/m)
   - [ ] Properties consistent with `fluids` library (< 0.1% deviation)
   - [ ] Works across 32-212F (0-100C) range

3. **API Integration**
   - [ ] `get_fluid_properties_with_units()` works with FluidDefinition
   - [ ] Proper error handling for invalid inputs
   - [ ] Clean API for future router endpoints

4. **Test Coverage**
   - [ ] 95% code coverage for fluids.py
   - [ ] Tests against known engineering values
   - [ ] Edge case coverage

5. **Code Quality**
   - [ ] All tests pass
   - [ ] mypy type checking passes
   - [ ] ruff linting passes

---

## References

1. **IAPWS-IF97** - Industrial Formulation for Water and Steam Properties
2. **fluids library** - Python thermophysical property calculations
3. **Crane TP-410** - Reference water properties table

---

## Notes

### Design Decisions

1. **Keep data.py intact:** The existing `get_fluid_properties()` in data.py
   provides the JSON-based lookup. The new fluids.py will use fluids library
   for more accuracy but can fall back to data.py interpolation.

2. **SI internal, convert on output:** All calculations in SI units internally.
   Unit conversion happens at service boundaries.

3. **Fluids library optional:** If fluids library calculation fails, fall back
   to JSON interpolation table for robustness.

### Known Engineering Values

| Property | Water at 68F (20C) | Source |
|----------|-------------------|--------|
| Density | 62.32 lb/ft (998.2 kg/m) | Crane TP-410 |
| Kinematic viscosity | 1.004e-6 m/s | IAPWS |
| Vapor pressure | 2339 Pa (0.339 psi) | IAPWS |

---

**Last Updated:** 2026-01-19
