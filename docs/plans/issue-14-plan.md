# Issue #14: Backend - Implement Unit Conversion System

> **GitHub Issue:** [#14](https://github.com/ccirone2/opensolve-pipe/issues/14)
> **Phase:** 1 - MVP
> **Priority:** Medium
> **Estimated Effort:** Medium (1-2 days)

---

## Overview

Implement a comprehensive unit conversion system for all physical quantities used in OpenSolve Pipe hydraulic calculations. This consolidates scattered conversion code into a single, type-safe module with proper validation and error handling.

## Problem Statement

Currently, unit conversion logic is scattered across multiple files:

- `services/fluids.py` - Temperature, density, viscosity, pressure conversions
- `services/solver/friction.py` - Flow rate, length conversions

This leads to:

- Duplicate constants with inconsistent precision
- No unified `convert()` function
- Missing bidirectional conversions
- No type-safe validation of unit categories

## Proposed Solution

Create a centralized unit conversion module at `apps/api/src/opensolve_pipe/utils/units.py` with:

1. **UnitCategory enum** - Type-safe categorization of physical quantities
2. **Conversion factors dictionary** - Single source of truth for all factors
3. **Generic `convert()` function** - Unified interface with validation
4. **Temperature offset handling** - Proper absolute vs interval conversions
5. **Enhanced UnitPreferences** - Complete Pydantic model with validation

---

## Technical Approach

### Architecture

```text
apps/api/src/opensolve_pipe/
├── utils/
│   ├── __init__.py           # NEW: Package init
│   └── units.py              # NEW: Unit conversion system
├── models/
│   └── units.py              # MODIFY: Enhance UnitPreferences
└── services/
    ├── fluids.py             # MODIFY: Use new conversion module
    └── solver/friction.py    # MODIFY: Use new conversion module
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Custom implementation (not Pint) | Maximum performance for solver loops, full control |
| Multiply-to-SI pattern | All conversions go through SI base unit for consistency |
| Category-based validation | Prevent incompatible conversions at runtime |
| Separate temperature handling | Offset conversions require different logic |
| Case-insensitive input | Better UX, normalized internally |

---

## Implementation Phases

### Phase 1: Core Module Structure

**Files:**

- `apps/api/src/opensolve_pipe/utils/__init__.py`
- `apps/api/src/opensolve_pipe/utils/units.py`

**Tasks:**

- [ ] Create `utils/` directory and `__init__.py`
- [ ] Define `UnitCategory` enum with all categories:

  ```python
  class UnitCategory(str, Enum):
      LENGTH = "length"
      PRESSURE = "pressure"
      FLOW = "flow"
      VELOCITY = "velocity"
      TEMPERATURE = "temperature"
      VISCOSITY_KINEMATIC = "viscosity_kinematic"
      VISCOSITY_DYNAMIC = "viscosity_dynamic"
      DENSITY = "density"
      HEAD = "head"  # Separate from pressure per ADR-004
  ```

- [ ] Create `CONVERSION_FACTORS` dictionary with SI base units:

  ```python
  CONVERSION_FACTORS: dict[str, tuple[UnitCategory, float, float]] = {
      # Length -> meters
      "m": (UnitCategory.LENGTH, 1.0, 0.0),
      "ft": (UnitCategory.LENGTH, 0.3048, 0.0),
      "in": (UnitCategory.LENGTH, 0.0254, 0.0),
      "mm": (UnitCategory.LENGTH, 0.001, 0.0),
      # ... (complete list below)
  }
  ```

- [ ] Implement `get_unit_info(unit: str)` function with case-insensitive lookup
- [ ] Implement `get_units_for_category(category: UnitCategory)` function

### Phase 2: Conversion Functions

**File:** `apps/api/src/opensolve_pipe/utils/units.py`

**Tasks:**

- [ ] Implement main `convert(value, from_unit, to_unit)` function:

  ```python
  def convert(value: float, from_unit: str, to_unit: str) -> float:
      """
      Convert value between units of the same category.

      Args:
          value: Numeric value to convert
          from_unit: Source unit symbol (case-insensitive)
          to_unit: Target unit symbol (case-insensitive)

      Returns:
          Converted value

      Raises:
          InvalidUnitError: If unit not found
          IncompatibleUnitsError: If units from different categories
          ValueError: If value physically impossible (e.g., below absolute zero)
      """
  ```

- [ ] Implement temperature-specific conversion with offset handling:

  ```python
  def _convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
      """Handle temperature conversion with offsets."""
      # K = C + 273.15
      # K = (F + 459.67) * 5/9
  ```

- [ ] Implement convenience functions:
  - `to_si(value: float, unit: str) -> float`
  - `from_si(value: float, unit: str) -> float`

- [ ] Add validation for absolute zero (temperature)

### Phase 3: Error Handling

**File:** `apps/api/src/opensolve_pipe/utils/units.py`

**Tasks:**

- [ ] Define custom exception classes:

  ```python
  class UnitConversionError(ValueError):
      """Base exception for unit conversion errors."""
      pass

  class InvalidUnitError(UnitConversionError):
      """Raised when unit symbol is not recognized."""
      def __init__(self, unit: str, category: UnitCategory | None = None):
          self.unit = unit
          self.category = category

  class IncompatibleUnitsError(UnitConversionError):
      """Raised when converting between incompatible categories."""
      def __init__(self, from_unit: str, to_unit: str,
                   from_category: UnitCategory, to_category: UnitCategory):
          ...
  ```

- [ ] Add helpful error messages with suggestions

### Phase 4: UnitPreferences Enhancement

**File:** `apps/api/src/opensolve_pipe/models/units.py`

**Tasks:**

- [ ] Add missing fields to `UnitPreferences`:

  ```python
  class UnitPreferences(OpenSolvePipeBaseModel):
      system: UnitSystem = UnitSystem.IMPERIAL
      length: str = "ft"
      diameter: str = "in"
      pressure: str = "psi"
      head: str = "ft"
      flow: str = "GPM"
      velocity: str = "ft/s"
      temperature: str = "F"
      viscosity_kinematic: str = "ft2/s"  # NEW
      viscosity_dynamic: str = "cP"       # NEW
      density: str = "lb/ft3"             # NEW
  ```

- [ ] Add field validators for unit strings:

  ```python
  @field_validator("length", "diameter")
  @classmethod
  def validate_length_unit(cls, v: str) -> str:
      from opensolve_pipe.utils.units import validate_unit_for_category, UnitCategory
      return validate_unit_for_category(v, UnitCategory.LENGTH)
  ```

- [ ] Define preset mappings for UnitSystem:

  ```python
  SYSTEM_PRESETS: dict[UnitSystem, dict[str, str]] = {
      UnitSystem.IMPERIAL: {"length": "ft", "pressure": "psi", ...},
      UnitSystem.SI: {"length": "m", "pressure": "kPa", ...},
      UnitSystem.MIXED: {"length": "m", "pressure": "bar", ...},
  }
  ```

### Phase 5: Integration & Refactoring

**Files:**

- `apps/api/src/opensolve_pipe/services/fluids.py`
- `apps/api/src/opensolve_pipe/services/solver/friction.py`

**Tasks:**

- [ ] Update `services/fluids.py` to use new module:
  - Replace inline conversion constants with imports
  - Update `convert_temperature()` to call `utils.units.convert()`
  - Update `density_to_imperial()`, `density_to_si()` etc.

- [ ] Update `services/solver/friction.py` to use new module:
  - Replace `GPM_TO_CFS`, `GPM_TO_M3S`, `FT_TO_M` constants with imports
  - Use `convert()` for flow and length conversions

- [ ] Update imports in `__init__.py` files

### Phase 6: Testing

**File:** `apps/api/tests/test_utils/test_units.py`

**Tasks:**

- [ ] Test conversion accuracy with known values:

  ```python
  @pytest.mark.parametrize("value,from_unit,to_unit,expected,tol", [
      (1.0, "ft", "m", 0.3048, 1e-6),
      (14.696, "psi", "Pa", 101325.0, 10),
      (100, "GPM", "L/s", 6.30902, 1e-4),
      (0, "C", "F", 32.0, 0.01),
      (100, "C", "F", 212.0, 0.01),
  ])
  def test_conversion_accuracy(value, from_unit, to_unit, expected, tol):
      result = convert(value, from_unit, to_unit)
      assert abs(result - expected) < tol
  ```

- [ ] Test roundtrip conversions:

  ```python
  def test_roundtrip_preserves_value():
      for value in [1.0, 100.0, 0.001]:
          result = convert(convert(value, "GPM", "L/s"), "L/s", "GPM")
          assert result == pytest.approx(value, rel=1e-10)
  ```

- [ ] Test temperature offset handling:

  ```python
  def test_temperature_freezing_point():
      assert convert(32, "F", "C") == pytest.approx(0.0, abs=0.01)
      assert convert(0, "C", "K") == pytest.approx(273.15, abs=0.01)

  def test_below_absolute_zero_raises():
      with pytest.raises(ValueError, match="absolute zero"):
          convert(-300, "C", "F")
  ```

- [ ] Test error cases:

  ```python
  def test_invalid_unit_raises():
      with pytest.raises(InvalidUnitError, match="xyz"):
          convert(100, "xyz", "m")

  def test_incompatible_units_raises():
      with pytest.raises(IncompatibleUnitsError):
          convert(100, "psi", "GPM")

  def test_case_insensitive():
      assert convert(100, "gpm", "L/s") == convert(100, "GPM", "L/s")
  ```

- [ ] Test UnitPreferences validation:

  ```python
  def test_invalid_unit_preference_raises():
      with pytest.raises(ValidationError):
          UnitPreferences(length="invalid_unit")
  ```

---

## Complete Unit Conversion Factors

```python
# All factors convert TO SI base unit (multiply factor + offset)
# Format: "symbol": (UnitCategory, to_si_factor, to_si_offset)

CONVERSION_FACTORS = {
    # Length -> meters
    "m": (UnitCategory.LENGTH, 1.0, 0.0),
    "ft": (UnitCategory.LENGTH, 0.3048, 0.0),
    "in": (UnitCategory.LENGTH, 0.0254, 0.0),
    "mm": (UnitCategory.LENGTH, 0.001, 0.0),
    "cm": (UnitCategory.LENGTH, 0.01, 0.0),

    # Pressure -> Pascals
    "Pa": (UnitCategory.PRESSURE, 1.0, 0.0),
    "kPa": (UnitCategory.PRESSURE, 1000.0, 0.0),
    "psi": (UnitCategory.PRESSURE, 6894.76, 0.0),
    "bar": (UnitCategory.PRESSURE, 100000.0, 0.0),
    "atm": (UnitCategory.PRESSURE, 101325.0, 0.0),

    # Head -> meters (separate from pressure per ADR-004)
    "m_head": (UnitCategory.HEAD, 1.0, 0.0),
    "ft_head": (UnitCategory.HEAD, 0.3048, 0.0),
    "ft_H2O": (UnitCategory.HEAD, 0.3048, 0.0),  # Alias
    "m_H2O": (UnitCategory.HEAD, 1.0, 0.0),      # Alias

    # Flow -> m³/s
    "m3/s": (UnitCategory.FLOW, 1.0, 0.0),
    "L/s": (UnitCategory.FLOW, 0.001, 0.0),
    "GPM": (UnitCategory.FLOW, 6.30902e-5, 0.0),
    "m3/h": (UnitCategory.FLOW, 1/3600, 0.0),
    "CFM": (UnitCategory.FLOW, 0.000471947, 0.0),
    "CFS": (UnitCategory.FLOW, 0.0283168, 0.0),

    # Velocity -> m/s
    "m/s": (UnitCategory.VELOCITY, 1.0, 0.0),
    "ft/s": (UnitCategory.VELOCITY, 0.3048, 0.0),

    # Temperature -> Kelvin (with offset)
    "K": (UnitCategory.TEMPERATURE, 1.0, 0.0),
    "C": (UnitCategory.TEMPERATURE, 1.0, 273.15),
    "F": (UnitCategory.TEMPERATURE, 5/9, 255.372222),

    # Kinematic viscosity -> m²/s
    "m2/s": (UnitCategory.VISCOSITY_KINEMATIC, 1.0, 0.0),
    "ft2/s": (UnitCategory.VISCOSITY_KINEMATIC, 0.0929030, 0.0),
    "cSt": (UnitCategory.VISCOSITY_KINEMATIC, 1e-6, 0.0),
    "St": (UnitCategory.VISCOSITY_KINEMATIC, 1e-4, 0.0),

    # Dynamic viscosity -> Pa·s
    "Pa.s": (UnitCategory.VISCOSITY_DYNAMIC, 1.0, 0.0),
    "cP": (UnitCategory.VISCOSITY_DYNAMIC, 0.001, 0.0),
    "P": (UnitCategory.VISCOSITY_DYNAMIC, 0.1, 0.0),
    "lb/(ft.s)": (UnitCategory.VISCOSITY_DYNAMIC, 1.48816, 0.0),

    # Density -> kg/m³
    "kg/m3": (UnitCategory.DENSITY, 1.0, 0.0),
    "lb/ft3": (UnitCategory.DENSITY, 16.0185, 0.0),
    "g/cm3": (UnitCategory.DENSITY, 1000.0, 0.0),
}

# Case-insensitive alias mapping
UNIT_ALIASES = {
    "gpm": "GPM",
    "cfm": "CFM",
    "cfs": "CFS",
    "celsius": "C",
    "fahrenheit": "F",
    "kelvin": "K",
    "meter": "m",
    "meters": "m",
    "foot": "ft",
    "feet": "ft",
    "inch": "in",
    "inches": "in",
}
```

---

## Acceptance Criteria

### Functional Requirements

- [x] `UnitCategory` enum defined with all categories
- [ ] `convert(value, from_unit, to_unit)` function works for all units
- [ ] Temperature conversions handle offsets correctly (0°C = 32°F = 273.15K)
- [ ] Incompatible category conversions raise `IncompatibleUnitsError`
- [ ] Invalid unit symbols raise `InvalidUnitError`
- [ ] Below absolute zero temperature raises `ValueError`
- [ ] Case-insensitive unit lookup works
- [ ] `UnitPreferences` model validates unit strings

### Non-Functional Requirements

- [ ] Conversion accuracy within 0.001% for standard conversions
- [ ] Performance: < 1µs per conversion (no dependencies on external libraries)
- [ ] All conversion factors documented with sources (Crane TP-410, NIST)

### Quality Gates

- [ ] Test coverage ≥ 93% for utils/units.py
- [ ] All parametrized conversion tests pass
- [ ] Roundtrip tests preserve value within 1e-10 relative tolerance
- [ ] MyPy type checking passes
- [ ] Ruff linting passes

---

## Dependencies & Prerequisites

**Dependencies:**

- None (pure Python implementation)

**Blocked By:**

- None

**Blocks:**

- Issue #15: API Endpoints (needs conversion for request/response)
- Issue #17: Frontend TypeScript Interfaces (will mirror these enums)

---

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Precision loss in conversions | Low | Medium | Use float64, test roundtrips |
| Temperature offset bugs | Medium | High | Extensive tests at reference points |
| Breaking existing code | Medium | Medium | Keep old functions as wrappers initially |

---

## References

### Internal References

- `apps/api/src/opensolve_pipe/models/units.py` - Existing UnitPreferences model
- `apps/api/src/opensolve_pipe/services/fluids.py:24-33` - Existing conversion constants
- `apps/api/src/opensolve_pipe/services/solver/friction.py:26-31` - Existing conversion constants
- `docs/TSD.md` Section 6 - Unit Conversion System specification
- `docs/DECISIONS.md` ADR-004 - Unit Handling in Models

### External References

- [Crane TP-410](https://www.flowoffluids.com/) - K-factors and engineering units
- [NIST Guide to SI](https://www.nist.gov/pml/owm/metric-si/si-units) - SI base units
- [Pint Documentation](https://pint.readthedocs.io/) - Temperature handling patterns

---

## MVP Checklist

```python
# apps/api/src/opensolve_pipe/utils/units.py

from enum import Enum
from typing import Tuple

class UnitCategory(str, Enum):
    """Categories of physical quantities."""
    LENGTH = "length"
    PRESSURE = "pressure"
    FLOW = "flow"
    VELOCITY = "velocity"
    TEMPERATURE = "temperature"
    VISCOSITY_KINEMATIC = "viscosity_kinematic"
    VISCOSITY_DYNAMIC = "viscosity_dynamic"
    DENSITY = "density"
    HEAD = "head"

class UnitConversionError(ValueError):
    """Base exception for unit conversion errors."""
    pass

class InvalidUnitError(UnitConversionError):
    """Unknown unit symbol."""
    pass

class IncompatibleUnitsError(UnitConversionError):
    """Cannot convert between different categories."""
    pass

# Conversion factors: unit -> (category, to_si_factor, to_si_offset)
CONVERSION_FACTORS: dict[str, Tuple[UnitCategory, float, float]] = {
    # ... (see complete list above)
}

def convert(value: float, from_unit: str, to_unit: str) -> float:
    """Convert value between units of the same category."""
    ...

def to_si(value: float, unit: str) -> float:
    """Convert to SI base unit."""
    ...

def from_si(value: float, unit: str) -> float:
    """Convert from SI base unit."""
    ...

def get_units_for_category(category: UnitCategory) -> list[str]:
    """Get all unit symbols for a category."""
    ...
```

---

**Created:** 2026-01-19
**Author:** Claude (Plan workflow)
**Status:** Ready for Implementation
