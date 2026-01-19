# Issue #7 Implementation Plan: Pipe Materials and Fittings Data Libraries

**GitHub Issue:** #7 - Backend - Create Pipe Materials and Fittings Data Libraries
**Branch:** `feature/issue-7`
**Status:** 🟡 Planning
**Created:** 2026-01-19

---

## Overview

Create JSON data files for pipe materials, fittings, and fluids with lookup
services. These data libraries are foundational for the hydraulic solver and
provide accurate engineering data from industry-standard references.

### Objectives

1. Create `pipe_materials.json` with comprehensive pipe dimension data
2. Create `fittings.json` with Crane TP-410 K-factor data
3. Create `fluids.json` with temperature-dependent water properties
4. Implement service functions for data lookup
5. Write comprehensive unit tests

### Dependencies

- ✅ Issue #2 (Pydantic Data Models) - Completed
  - `PipeMaterial` enum defined
  - `FittingType` enum defined
  - `FluidType` enum defined

---

## Data File Specifications

### 1. Pipe Materials (`pipe_materials.json`)

**Location:** `apps/api/src/opensolve_pipe/data/pipe_materials.json`

**Structure:**

```json
{
  "version": "1.0.0",
  "source": "ASME B36.10M, B36.19M",
  "materials": {
    "carbon_steel": {
      "name": "Carbon Steel",
      "roughness_mm": 0.046,
      "roughness_in": 0.0018,
      "schedules": {
        "40": {
          "2": { "od_in": 2.375, "id_in": 2.067, "wall_in": 0.154 },
          "2.5": { "od_in": 2.875, "id_in": 2.469, "wall_in": 0.203 },
          ...
        }
      }
    }
  }
}
```

**Materials to include:**

- Carbon Steel (Schedule 5, 10, 40, 80, 160)
- Stainless Steel (Schedule 5S, 10S, 40S, 80S)
- PVC (Schedule 40, 80)
- CPVC (Schedule 40, 80)
- HDPE (SDR 11, SDR 17)
- Ductile Iron (Class 150, 200, 250, 300, 350)

**Nominal sizes:** 1/2", 3/4", 1", 1.25", 1.5", 2", 2.5", 3", 4", 6", 8", 10", 12"

**Roughness values (absolute roughness):**
| Material | ε (mm) | ε (in) | Source |
|----------|--------|--------|--------|
| Carbon Steel | 0.046 | 0.0018 | Crane TP-410 |
| Stainless Steel | 0.015 | 0.0006 | Crane TP-410 |
| PVC/CPVC | 0.0015 | 0.00006 | Literature |
| HDPE | 0.007 | 0.00028 | Literature |
| Ductile Iron | 0.25 | 0.01 | Cement-lined |
| Cast Iron | 0.26 | 0.010 | Crane TP-410 |

### 2. Fittings (`fittings.json`)

**Location:** `apps/api/src/opensolve_pipe/data/fittings.json`

**Structure:**

```json
{
  "version": "1.0.0",
  "source": "Crane TP-410, 2018 Edition",
  "methods": {
    "L_over_D": "K = f_T × (L/D) where f_T is friction factor at complete turbulence",
    "K_fixed": "K is constant regardless of pipe size",
    "K_curve": "K varies with pipe diameter per lookup table"
  },
  "fittings": {
    "elbow_90_lr": {
      "name": "90° Long Radius Elbow",
      "category": "elbow",
      "k_method": "L_over_D",
      "L_over_D": 14,
      "notes": "r/D = 1.5, welded"
    },
    ...
  }
}
```

**Fittings to include (Crane TP-410 data):**

| Fitting | Category | K Method | L/D or K |
|---------|----------|----------|----------|
| 90° Long Radius Elbow (welded) | elbow | L/D | 14 |
| 90° Short Radius Elbow (welded) | elbow | L/D | 30 |
| 90° Threaded Elbow | elbow | L/D | 30 |
| 45° Elbow | elbow | L/D | 16 |
| Tee (Through Run) | tee | L/D | 20 |
| Tee (Into Branch) | tee | L/D | 60 |
| Gate Valve (Full Open) | valve | L/D | 8 |
| Ball Valve (Full Open) | valve | L/D | 3 |
| Butterfly Valve (Full Open) | K_fixed | K_fixed | 0.35 |
| Globe Valve (Full Open) | valve | L/D | 340 |
| Swing Check Valve | valve | L/D | 50 |
| Lift Check Valve | valve | L/D | 600 |
| Entrance (Sharp-Edged) | entrance | K_fixed | 0.5 |
| Entrance (Rounded r/D=0.1) | entrance | K_fixed | 0.04 |
| Entrance (Projecting) | entrance | K_fixed | 0.78 |
| Exit | exit | K_fixed | 1.0 |
| Basket Strainer (Clean) | strainer | K_fixed | 2.0 |
| Y-Strainer (Clean) | strainer | K_fixed | 1.5 |

**Friction factor at complete turbulence (f_T) table:**
For L/D method, K = f_T × (L/D). The f_T values by pipe size:

| Nominal Size | f_T |
|--------------|-----|
| 1/2" | 0.027 |
| 3/4" | 0.025 |
| 1" | 0.023 |
| 1-1/4" | 0.022 |
| 1-1/2" | 0.021 |
| 2" | 0.019 |
| 2-1/2", 3" | 0.018 |
| 4" | 0.017 |
| 6" | 0.015 |
| 8"-10" | 0.014 |
| 12"-16" | 0.013 |
| 18"-24" | 0.012 |

### 3. Fluids (`fluids.json`)

**Location:** `apps/api/src/opensolve_pipe/data/fluids.json`

**Structure:**

```json
{
  "version": "1.0.0",
  "source": "IAPWS-IF97, CoolProp",
  "fluids": {
    "water": {
      "name": "Water",
      "type": "temperature_dependent",
      "temperature_range_C": [0, 100],
      "properties": [
        {
          "temp_C": 0,
          "density_kg_m3": 999.84,
          "viscosity_Pa_s": 0.001792,
          "vapor_pressure_Pa": 611
        },
        {
          "temp_C": 10,
          "density_kg_m3": 999.70,
          "viscosity_Pa_s": 0.001307,
          "vapor_pressure_Pa": 1228
        },
        ...
      ]
    },
    "diesel": {
      "name": "Diesel Fuel",
      "type": "fixed",
      "density_kg_m3": 850,
      "kinematic_viscosity_m2_s": 3.0e-6,
      "vapor_pressure_Pa": 500
    }
  }
}
```

**Water properties table (every 10°C):**
| T (°C) | T (°F) | ρ (kg/m³) | μ (Pa·s) | ν (m²/s) | Pv (Pa) |
|--------|--------|-----------|----------|----------|---------|
| 0 | 32 | 999.84 | 0.001792 | 1.793e-6 | 611 |
| 10 | 50 | 999.70 | 0.001307 | 1.307e-6 | 1,228 |
| 20 | 68 | 998.21 | 0.001002 | 1.004e-6 | 2,339 |
| 25 | 77 | 997.05 | 0.000890 | 8.93e-7 | 3,169 |
| 30 | 86 | 995.65 | 0.000798 | 8.01e-7 | 4,246 |
| 40 | 104 | 992.22 | 0.000653 | 6.58e-7 | 7,384 |
| 50 | 122 | 988.04 | 0.000547 | 5.53e-7 | 12,352 |
| 60 | 140 | 983.20 | 0.000466 | 4.74e-7 | 19,946 |
| 70 | 158 | 977.77 | 0.000404 | 4.13e-7 | 31,201 |
| 80 | 176 | 971.79 | 0.000354 | 3.65e-7 | 47,414 |
| 90 | 194 | 965.31 | 0.000315 | 3.26e-7 | 70,182 |
| 100 | 212 | 958.35 | 0.000282 | 2.94e-7 | 101,420 |

---

## Service Functions

### Location: `apps/api/src/opensolve_pipe/services/data.py`

### Function Signatures

```python
def get_pipe_dimensions(
    material: PipeMaterial,
    nominal_diameter: float,
    schedule: str
) -> PipeDimensions:
    """
    Get pipe dimensions (OD, ID, wall thickness) for given material, size, schedule.

    Args:
        material: Pipe material enum value
        nominal_diameter: Nominal pipe diameter (inches)
        schedule: Pipe schedule (e.g., "40", "80", "10S")

    Returns:
        PipeDimensions with od_in, id_in, wall_in, roughness_in, roughness_mm

    Raises:
        PipeMaterialNotFoundError: If material not in database
        PipeSizeNotFoundError: If size/schedule combination not available
    """

def get_pipe_roughness(material: PipeMaterial) -> PipeRoughness:
    """
    Get absolute roughness for pipe material.

    Returns:
        PipeRoughness with roughness_mm and roughness_in
    """

def get_fitting_k_factor(
    fitting_type: FittingType,
    nominal_diameter: float | None = None,
    friction_factor: float | None = None
) -> float:
    """
    Calculate K-factor for a fitting.

    For L/D method fittings, requires either:
      - nominal_diameter to look up f_T from table, OR
      - friction_factor to use directly

    For K_fixed method fittings, returns the fixed K value.

    Args:
        fitting_type: Type of fitting
        nominal_diameter: Pipe nominal diameter in inches (for f_T lookup)
        friction_factor: Friction factor to use (overrides f_T lookup)

    Returns:
        K-factor (dimensionless)

    Raises:
        FittingNotFoundError: If fitting type not in database
        ValueError: If L/D fitting but no diameter or friction factor provided
    """

def get_friction_factor_turbulent(nominal_diameter: float) -> float:
    """
    Get friction factor at complete turbulence (f_T) for pipe size.

    Args:
        nominal_diameter: Nominal pipe diameter in inches

    Returns:
        f_T value for the pipe size (interpolated if necessary)
    """

def get_fluid_properties(
    fluid_type: FluidType,
    temperature_C: float,
    concentration: float | None = None
) -> FluidProperties:
    """
    Get fluid properties at specified temperature.

    Args:
        fluid_type: Type of fluid
        temperature_C: Temperature in Celsius
        concentration: Glycol concentration (0-100) for glycol fluids

    Returns:
        FluidProperties with density, viscosity, vapor_pressure in SI units

    Raises:
        FluidNotFoundError: If fluid type not in database
        TemperatureOutOfRangeError: If temperature outside valid range
        ValueError: If glycol fluid but no concentration provided
    """

def list_available_materials() -> list[dict]:
    """List all available pipe materials with their properties."""

def list_available_fittings() -> list[dict]:
    """List all available fittings with their K-factor methods."""

def list_available_fluids() -> list[dict]:
    """List all available fluids with their property ranges."""
```

### Data Models (for service returns)

```python
@dataclass
class PipeDimensions:
    """Pipe dimensions from lookup."""
    od_in: float
    id_in: float
    wall_in: float
    roughness_in: float
    roughness_mm: float
    material: str
    schedule: str

@dataclass
class PipeRoughness:
    """Pipe roughness values."""
    roughness_mm: float
    roughness_in: float

# FluidProperties already defined in models/fluids.py
```

### Error Classes

```python
class DataNotFoundError(Exception):
    """Base class for data lookup errors."""
    pass

class PipeMaterialNotFoundError(DataNotFoundError):
    """Pipe material not in database."""
    pass

class PipeSizeNotFoundError(DataNotFoundError):
    """Pipe size/schedule combination not available."""
    pass

class FittingNotFoundError(DataNotFoundError):
    """Fitting type not in database."""
    pass

class FluidNotFoundError(DataNotFoundError):
    """Fluid type not in database."""
    pass

class TemperatureOutOfRangeError(DataNotFoundError):
    """Temperature outside valid range for fluid."""
    pass
```

---

## Implementation Tasks

### Phase 1: Data Files (JSON)

- [ ] **Task 1.1:** Create `pipe_materials.json`
  - Carbon steel (Schedule 5, 10, 40, 80, 160)
  - Stainless steel (Schedule 5S, 10S, 40S, 80S)
  - PVC (Schedule 40, 80)
  - CPVC (Schedule 40, 80)
  - Sizes: 1/2" through 12"
  - Include roughness values

- [ ] **Task 1.2:** Create `fittings.json`
  - All FittingType enum values
  - L/D values from Crane TP-410
  - f_T table for turbulent friction factor
  - Fixed K values where applicable

- [ ] **Task 1.3:** Create `fluids.json`
  - Water properties (0-100°C)
  - Fixed-property fluids (diesel, gasoline)
  - Temperature interpolation metadata

### Phase 2: Service Functions

- [ ] **Task 2.1:** Create `services/data.py`
  - JSON loading with caching
  - Error classes
  - Helper data classes

- [ ] **Task 2.2:** Implement pipe material functions
  - `get_pipe_dimensions()`
  - `get_pipe_roughness()`
  - `list_available_materials()`

- [ ] **Task 2.3:** Implement fitting functions
  - `get_fitting_k_factor()`
  - `get_friction_factor_turbulent()`
  - `list_available_fittings()`

- [ ] **Task 2.4:** Implement fluid functions
  - `get_fluid_properties()` with interpolation
  - `list_available_fluids()`

### Phase 3: Tests

- [ ] **Task 3.1:** Test pipe material lookups
  - Valid material/size/schedule combinations
  - Invalid combinations raise appropriate errors
  - Roughness values match expected

- [ ] **Task 3.2:** Test fitting K-factor calculations
  - L/D method with various pipe sizes
  - Fixed K values
  - Error handling for missing data

- [ ] **Task 3.3:** Test fluid property lookups
  - Interpolation between temperature points
  - Edge cases (0°C, 100°C)
  - Error handling for out-of-range temperatures

- [ ] **Task 3.4:** Test data file validation
  - All FittingType enum values have entries
  - All PipeMaterial enum values have entries
  - JSON schema validation

---

## File Structure

```text
apps/api/src/opensolve_pipe/
├── data/
│   ├── __init__.py           # Data package init
│   ├── pipe_materials.json   # Pipe dimension data
│   ├── fittings.json         # Fitting K-factor data
│   └── fluids.json           # Fluid properties data
├── services/
│   ├── __init__.py           # Services package init
│   └── data.py               # Data lookup services
└── tests/
    └── test_services/
        ├── __init__.py
        └── test_data.py      # Service tests
```

---

## Acceptance Criteria

1. **Data Completeness**
   - [ ] All PipeMaterial enum values have entries in pipe_materials.json
   - [ ] All FittingType enum values have entries in fittings.json
   - [ ] Water properties cover 0-100°C range

2. **Data Accuracy**
   - [ ] Pipe dimensions match ASME B36.10M/B36.19M
   - [ ] K-factors match Crane TP-410, 2018 Edition
   - [ ] Water properties match IAPWS-IF97 (< 1% deviation)

3. **Service Functionality**
   - [ ] All lookup functions return correct data
   - [ ] Appropriate errors raised for missing data
   - [ ] Temperature interpolation works correctly

4. **Test Coverage**
   - [ ] ≥95% code coverage for service functions
   - [ ] All edge cases tested
   - [ ] Integration tests with existing models

5. **Code Quality**
   - [ ] All tests pass
   - [ ] mypy type checking passes
   - [ ] ruff linting passes

---

## References

1. **Crane TP-410** - Flow of Fluids Through Valves, Fittings, and Pipe (2018 Edition)
2. **ASME B36.10M** - Welded and Seamless Wrought Steel Pipe
3. **ASME B36.19M** - Stainless Steel Pipe
4. **IAPWS-IF97** - Industrial Formulation for Water and Steam Properties
5. **CoolProp** - Open-source thermophysical property library

---

## Notes

### Design Decisions

1. **Caching:** Load JSON files once and cache in module-level variables
2. **Interpolation:** Use linear interpolation for temperature-dependent properties
3. **Units:** Store all data in both SI and US Customary where applicable
4. **Extensibility:** JSON structure allows adding new materials/fittings
   without code changes

### Future Enhancements

- Add glycol mixture properties (requires CoolProp or similar)
- Add more pipe materials (copper, concrete, etc.)
- Add reducer K-factor calculations (velocity-dependent)
- Add manufacturer-specific pump curve database

---

**Last Updated:** 2026-01-19
