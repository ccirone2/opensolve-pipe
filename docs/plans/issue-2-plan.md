# Implementation Plan: Issue #2 - Backend Data Models

**Issue:** Backend - Define Pydantic Data Models
**Branch:** `feature/issue-2-data-models`
**Created:** 2026-01-19
**Status:** Ready for Implementation

---

## Overview

Create Pydantic models for all core data structures: Project, Component, Piping, and SolvedState. These models form the foundation for the entire application's data layer and must align with the TypeScript interfaces defined in the TSD.

## Success Criteria

- [ ] All models serialize to/from JSON correctly
- [ ] Invalid data raises `ValidationError` with clear messages
- [ ] Models match TypeScript interfaces in TSD
- [ ] Unit tests achieve >93% coverage
- [ ] All models pass type checking (mypy)

---

## File Structure

```
apps/api/src/opensolve_pipe/models/
├── __init__.py              # Export all models
├── base.py                  # BaseModel config, common types
├── project.py               # Project, ProjectMetadata, ProjectSettings
├── components.py            # All component types (Reservoir, Tank, etc.)
├── piping.py                # PipeDefinition, PipingSegment, Fitting
├── pump.py                  # Pump, PumpCurve, FlowHeadPoint
├── fluids.py                # FluidDefinition, FluidProperties
├── results.py               # SolvedState, NodeResult, LinkResult, PumpResult
└── units.py                 # UnitPreferences, SolverOptions
```

---

## Implementation Steps

### Step 1: Create Base Model Configuration

**File:** `apps/api/src/opensolve_pipe/models/base.py`

**Tasks:**
- [ ] Create `BaseModelConfig` with common Pydantic settings
- [ ] Define custom validators for common patterns
- [ ] Create type aliases for physical units (Length, Pressure, Flow, etc.)
- [ ] Add utility types: `PositiveFloat`, `NonNegativeFloat`, `PositiveInt`

**Implementation Notes:**
```python
from pydantic import BaseModel, ConfigDict

class OpenSolvePipeBaseModel(BaseModel):
    """Base model with common configuration."""
    model_config = ConfigDict(
        populate_by_name=True,      # Allow field aliases
        validate_assignment=True,    # Validate on attribute assignment
        extra="forbid",              # Fail on unknown fields
        str_strip_whitespace=True,   # Strip whitespace from strings
    )
```

**Validation Rules:**
- All length values must be positive
- Elevation can be negative (below sea level)
- Pressure can be negative (vacuum) but typically positive for liquids
- Flow direction determined by sign (positive = downstream)

---

### Step 2: Define Unit and Settings Models

**File:** `apps/api/src/opensolve_pipe/models/units.py`

**Tasks:**
- [ ] Create `UnitSystem` enum (IMPERIAL, SI, MIXED)
- [ ] Create `UnitPreferences` model with per-quantity unit settings
- [ ] Create `SolverOptions` model
- [ ] Add validation for unit compatibility

**Models:**
```python
class UnitPreferences(OpenSolvePipeBaseModel):
    """User's preferred units for display and input."""
    system: UnitSystem = UnitSystem.IMPERIAL
    length: str = "ft"
    diameter: str = "in"
    pressure: str = "psi"
    head: str = "ft"
    flow: str = "GPM"
    velocity: str = "ft/s"
    temperature: str = "F"

class SolverOptions(OpenSolvePipeBaseModel):
    """Configuration options for the hydraulic solver."""
    max_iterations: PositiveInt = 100
    tolerance: PositiveFloat = 0.001
    include_system_curve: bool = True
    flow_range_min: NonNegativeFloat = 0.0
    flow_range_max: PositiveFloat = 500.0
```

---

### Step 3: Define Piping Models

**File:** `apps/api/src/opensolve_pipe/models/piping.py`

**Tasks:**
- [ ] Create `PipeMaterial` enum (CARBON_STEEL, STAINLESS_STEEL, PVC, etc.)
- [ ] Create `PipeSchedule` enum (SCH_40, SCH_80, etc.)
- [ ] Create `PipeDefinition` model
- [ ] Create `FittingType` enum
- [ ] Create `Fitting` model with K-factor handling
- [ ] Create `PipingSegment` model (pipe + fittings collection)

**Models:**
```python
class PipeMaterial(str, Enum):
    CARBON_STEEL = "carbon_steel"
    STAINLESS_STEEL = "stainless_steel"
    PVC = "pvc"
    HDPE = "hdpe"
    DUCTILE_IRON = "ductile_iron"
    GRP = "grp"

class FittingType(str, Enum):
    ELBOW_90_LR = "elbow_90_lr"
    ELBOW_90_SR = "elbow_90_sr"
    ELBOW_45 = "elbow_45"
    TEE_THROUGH = "tee_through"
    TEE_BRANCH = "tee_branch"
    GATE_VALVE = "gate_valve"
    BALL_VALVE = "ball_valve"
    CHECK_VALVE = "check_valve"
    ENTRANCE_SHARP = "entrance_sharp"
    ENTRANCE_ROUNDED = "entrance_rounded"
    EXIT = "exit"
    STRAINER = "strainer_basket"

class PipeDefinition(OpenSolvePipeBaseModel):
    """Definition of a pipe segment."""
    material: PipeMaterial
    nominal_diameter: PositiveFloat  # In project units (typically inches)
    schedule: str = "40"
    length: PositiveFloat
    roughness_override: PositiveFloat | None = None  # Override calculated roughness

class Fitting(OpenSolvePipeBaseModel):
    """A fitting or valve in a piping segment."""
    type: FittingType
    quantity: PositiveInt = 1
    k_factor_override: PositiveFloat | None = None  # User override

class PipingSegment(OpenSolvePipeBaseModel):
    """A piping segment consisting of a pipe and zero or more fittings."""
    pipe: PipeDefinition
    fittings: list[Fitting] = []
```

**Validation Rules:**
- Nominal diameter must be from standard sizes (2", 2.5", 3", 4", 6", 8")
- Schedule must be valid for the material
- Fitting quantity must be positive integer
- K-factor override must be positive if provided

---

### Step 4: Define Pump Models

**File:** `apps/api/src/opensolve_pipe/models/pump.py`

**Tasks:**
- [ ] Create `FlowHeadPoint` model (single curve point)
- [ ] Create `PumpCurve` model with validation
- [ ] Create curve validation (monotonic, positive head)

**Models:**
```python
class FlowHeadPoint(OpenSolvePipeBaseModel):
    """A single point on a pump curve."""
    flow: NonNegativeFloat  # GPM or project units
    head: NonNegativeFloat  # ft or project units

class FlowEfficiencyPoint(OpenSolvePipeBaseModel):
    """A single point on an efficiency curve."""
    flow: NonNegativeFloat
    efficiency: float  # 0-1 or 0-100 depending on convention

class NPSHRPoint(OpenSolvePipeBaseModel):
    """A single point on NPSH required curve."""
    flow: NonNegativeFloat
    npsh_required: PositiveFloat

class PumpCurve(OpenSolvePipeBaseModel):
    """Pump performance curve definition."""
    id: str
    name: str
    manufacturer: str | None = None
    model: str | None = None
    points: list[FlowHeadPoint]  # Minimum 2 points
    efficiency_curve: list[FlowEfficiencyPoint] | None = None
    npshr_curve: list[NPSHRPoint] | None = None

    @field_validator("points")
    @classmethod
    def validate_pump_curve(cls, v: list[FlowHeadPoint]) -> list[FlowHeadPoint]:
        if len(v) < 2:
            raise ValueError("Pump curve requires at least 2 points")
        # Verify points are sorted by flow
        flows = [p.flow for p in v]
        if flows != sorted(flows):
            raise ValueError("Pump curve points must be sorted by flow")
        # Verify head decreases with increasing flow (typical pump behavior)
        heads = [p.head for p in v]
        if not all(heads[i] >= heads[i+1] for i in range(len(heads)-1)):
            # Warning only - some curves may not be monotonic
            pass
        return v
```

---

### Step 5: Define Component Models

**File:** `apps/api/src/opensolve_pipe/models/components.py`

**Tasks:**
- [ ] Create `ComponentType` enum
- [ ] Create `BaseComponent` model with common fields
- [ ] Create `Connection` model for downstream connections
- [ ] Create `Reservoir` component model
- [ ] Create `Tank` component model
- [ ] Create `Junction` component model
- [ ] Create `Pump` component model (references PumpCurve)
- [ ] Create discriminated union `Component` type

**Models:**
```python
class ComponentType(str, Enum):
    RESERVOIR = "reservoir"
    TANK = "tank"
    JUNCTION = "junction"
    PUMP = "pump"
    VALVE = "valve"
    HEAT_EXCHANGER = "heat_exchanger"
    STRAINER = "strainer"
    ORIFICE = "orifice"
    SPRINKLER = "sprinkler"

class Connection(OpenSolvePipeBaseModel):
    """Connection to a downstream component."""
    target_component_id: str
    piping: PipingSegment | None = None

class BaseComponent(OpenSolvePipeBaseModel):
    """Base class for all components."""
    id: str
    type: ComponentType
    name: str
    elevation: float  # Can be negative
    upstream_piping: PipingSegment | None = None
    downstream_connections: list[Connection] = []

class Reservoir(BaseComponent):
    """Fixed-head water source."""
    type: Literal[ComponentType.RESERVOIR] = ComponentType.RESERVOIR
    water_level: NonNegativeFloat  # Above reservoir bottom

    @computed_field
    @property
    def total_head(self) -> float:
        """Total head = elevation + water level."""
        return self.elevation + self.water_level

class Tank(BaseComponent):
    """Variable-level storage tank."""
    type: Literal[ComponentType.TANK] = ComponentType.TANK
    diameter: PositiveFloat
    min_level: NonNegativeFloat = 0.0
    max_level: PositiveFloat
    initial_level: NonNegativeFloat

    @field_validator("initial_level")
    @classmethod
    def validate_initial_level(cls, v, info):
        data = info.data
        if "min_level" in data and v < data["min_level"]:
            raise ValueError("Initial level cannot be below minimum level")
        if "max_level" in data and v > data["max_level"]:
            raise ValueError("Initial level cannot exceed maximum level")
        return v

class Junction(BaseComponent):
    """Connection point, optionally with demand."""
    type: Literal[ComponentType.JUNCTION] = ComponentType.JUNCTION
    demand: NonNegativeFloat = 0.0  # Flow withdrawn at this point

class PumpComponent(BaseComponent):
    """Pump component that references a pump curve."""
    type: Literal[ComponentType.PUMP] = ComponentType.PUMP
    curve_id: str  # Reference to pump curve in project's pump_library
    speed: PositiveFloat = 1.0  # Fraction of rated speed
    status: Literal["on", "off"] = "on"

# Discriminated union for all components
Component = Annotated[
    Reservoir | Tank | Junction | PumpComponent,
    Field(discriminator="type")
]
```

---

### Step 6: Define Fluid Models

**File:** `apps/api/src/opensolve_pipe/models/fluids.py`

**Tasks:**
- [ ] Create `FluidType` enum
- [ ] Create `FluidDefinition` model
- [ ] Create `FluidProperties` model (calculated values)

**Models:**
```python
class FluidType(str, Enum):
    WATER = "water"
    ETHYLENE_GLYCOL = "ethylene_glycol"
    PROPYLENE_GLYCOL = "propylene_glycol"
    DIESEL = "diesel"
    GASOLINE = "gasoline"
    CUSTOM = "custom"

class FluidDefinition(OpenSolvePipeBaseModel):
    """Definition of the working fluid."""
    type: FluidType = FluidType.WATER
    temperature: float = 68.0  # In project units (F or C)
    concentration: float | None = None  # For glycol mixtures (%)

    # For custom fluids
    custom_density: PositiveFloat | None = None
    custom_viscosity: PositiveFloat | None = None
    custom_vapor_pressure: NonNegativeFloat | None = None

class FluidProperties(OpenSolvePipeBaseModel):
    """Calculated fluid properties at operating conditions."""
    density: PositiveFloat  # In SI (kg/m³)
    kinematic_viscosity: PositiveFloat  # In SI (m²/s)
    dynamic_viscosity: PositiveFloat  # In SI (Pa·s)
    vapor_pressure: NonNegativeFloat  # In SI (Pa)
```

---

### Step 7: Define Project Models

**File:** `apps/api/src/opensolve_pipe/models/project.py`

**Tasks:**
- [ ] Create `ProjectMetadata` model
- [ ] Create `ProjectSettings` model
- [ ] Create `Project` model (top-level container)
- [ ] Add validation for component references
- [ ] Add validation for pump curve references

**Models:**
```python
from datetime import datetime
from uuid import uuid4

class ProjectMetadata(OpenSolvePipeBaseModel):
    """Project metadata and versioning info."""
    name: str = "Untitled Project"
    description: str | None = None
    created: datetime = Field(default_factory=datetime.utcnow)
    modified: datetime = Field(default_factory=datetime.utcnow)
    version: str = "1"
    parent_version: str | None = None  # For branching

class ProjectSettings(OpenSolvePipeBaseModel):
    """Project-level settings."""
    units: UnitPreferences = Field(default_factory=UnitPreferences)
    enabled_checks: list[str] = []
    solver_options: SolverOptions = Field(default_factory=SolverOptions)

class Project(OpenSolvePipeBaseModel):
    """Top-level project container."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    metadata: ProjectMetadata = Field(default_factory=ProjectMetadata)
    settings: ProjectSettings = Field(default_factory=ProjectSettings)
    fluid: FluidDefinition = Field(default_factory=FluidDefinition)
    components: list[Component] = []
    pump_library: list[PumpCurve] = []
    results: "SolvedState | None" = None

    @field_validator("components")
    @classmethod
    def validate_component_references(cls, v: list[Component]) -> list[Component]:
        """Ensure all component references are valid."""
        component_ids = {c.id for c in v}
        for component in v:
            for conn in component.downstream_connections:
                if conn.target_component_id not in component_ids:
                    raise ValueError(
                        f"Component {component.id} references unknown "
                        f"target: {conn.target_component_id}"
                    )
        return v

    @model_validator(mode="after")
    def validate_pump_curve_references(self) -> "Project":
        """Ensure pump components reference valid pump curves."""
        curve_ids = {c.id for c in self.pump_library}
        for component in self.components:
            if isinstance(component, PumpComponent):
                if component.curve_id not in curve_ids:
                    raise ValueError(
                        f"Pump {component.id} references unknown "
                        f"curve: {component.curve_id}"
                    )
        return self
```

---

### Step 8: Define Results Models

**File:** `apps/api/src/opensolve_pipe/models/results.py`

**Tasks:**
- [ ] Create `NodeResult` model
- [ ] Create `LinkResult` model
- [ ] Create `PumpResult` model
- [ ] Create `Warning` model for design check results
- [ ] Create `SolvedState` model

**Models:**
```python
from datetime import datetime

class NodeResult(OpenSolvePipeBaseModel):
    """Solved state for a node (reservoir, tank, junction)."""
    component_id: str
    pressure: float  # Static pressure in project units
    dynamic_pressure: float
    total_pressure: float
    hgl: float  # Hydraulic Grade Line
    egl: float  # Energy Grade Line

class LinkResult(OpenSolvePipeBaseModel):
    """Solved state for a link (pipe segment)."""
    component_id: str
    upstream_node_id: str
    downstream_node_id: str
    flow: float  # In project units
    velocity: float
    head_loss: float
    reynolds_number: float
    friction_factor: float
    regime: Literal["laminar", "transitional", "turbulent"]

class PumpResult(OpenSolvePipeBaseModel):
    """Solved state for a pump at its operating point."""
    component_id: str
    operating_flow: float
    operating_head: float
    npsh_available: float
    npsh_margin: float | None = None  # If NPSHR provided
    efficiency: float | None = None  # If efficiency curve provided
    power: float | None = None  # Calculated power consumption
    system_curve: list[FlowHeadPoint] = []

class WarningCategory(str, Enum):
    VELOCITY = "velocity"
    PRESSURE = "pressure"
    NPSH = "npsh"
    CONVERGENCE = "convergence"

class Warning(OpenSolvePipeBaseModel):
    """Design check warning or solver message."""
    category: WarningCategory
    severity: Literal["info", "warning", "error"]
    component_id: str | None = None
    message: str
    details: dict[str, Any] | None = None

class SolvedState(OpenSolvePipeBaseModel):
    """Complete solved state of the network."""
    converged: bool
    iterations: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    error: str | None = None  # Error message if not converged

    node_results: dict[str, NodeResult] = {}
    link_results: dict[str, LinkResult] = {}
    pump_results: dict[str, PumpResult] = {}

    warnings: list[Warning] = []
```

---

### Step 9: Create Model Exports

**File:** `apps/api/src/opensolve_pipe/models/__init__.py`

**Tasks:**
- [ ] Export all public models
- [ ] Create type aliases for common patterns
- [ ] Add model version constant

**Implementation:**
```python
"""OpenSolve Pipe data models."""

from .base import OpenSolvePipeBaseModel
from .units import UnitSystem, UnitPreferences, SolverOptions
from .piping import (
    PipeMaterial,
    PipeSchedule,
    PipeDefinition,
    FittingType,
    Fitting,
    PipingSegment,
)
from .pump import (
    FlowHeadPoint,
    FlowEfficiencyPoint,
    NPSHRPoint,
    PumpCurve,
)
from .components import (
    ComponentType,
    Connection,
    BaseComponent,
    Reservoir,
    Tank,
    Junction,
    PumpComponent,
    Component,
)
from .fluids import FluidType, FluidDefinition, FluidProperties
from .project import ProjectMetadata, ProjectSettings, Project
from .results import (
    NodeResult,
    LinkResult,
    PumpResult,
    WarningCategory,
    Warning,
    SolvedState,
)

__all__ = [
    # Base
    "OpenSolvePipeBaseModel",
    # Units
    "UnitSystem",
    "UnitPreferences",
    "SolverOptions",
    # Piping
    "PipeMaterial",
    "PipeSchedule",
    "PipeDefinition",
    "FittingType",
    "Fitting",
    "PipingSegment",
    # Pump
    "FlowHeadPoint",
    "FlowEfficiencyPoint",
    "NPSHRPoint",
    "PumpCurve",
    # Components
    "ComponentType",
    "Connection",
    "BaseComponent",
    "Reservoir",
    "Tank",
    "Junction",
    "PumpComponent",
    "Component",
    # Fluids
    "FluidType",
    "FluidDefinition",
    "FluidProperties",
    # Project
    "ProjectMetadata",
    "ProjectSettings",
    "Project",
    # Results
    "NodeResult",
    "LinkResult",
    "PumpResult",
    "WarningCategory",
    "Warning",
    "SolvedState",
]

MODEL_VERSION = "1.0.0"
```

---

### Step 10: Write Unit Tests

**File:** `apps/api/tests/test_models/`

**Test Structure:**
```
apps/api/tests/test_models/
├── __init__.py
├── conftest.py           # Shared fixtures
├── test_base.py          # Base model tests
├── test_units.py         # Unit preference tests
├── test_piping.py        # Piping model tests
├── test_pump.py          # Pump curve tests
├── test_components.py    # Component model tests
├── test_fluids.py        # Fluid model tests
├── test_project.py       # Project model tests
└── test_results.py       # Results model tests
```

**Key Test Cases:**

1. **Serialization Roundtrip:**
   ```python
   def test_project_roundtrip():
       project = create_sample_project()
       json_str = project.model_dump_json()
       loaded = Project.model_validate_json(json_str)
       assert project == loaded
   ```

2. **Validation Errors:**
   ```python
   def test_negative_diameter_rejected():
       with pytest.raises(ValidationError):
           PipeDefinition(material="carbon_steel", nominal_diameter=-1, length=100)
   ```

3. **Reference Validation:**
   ```python
   def test_invalid_component_reference():
       with pytest.raises(ValidationError):
           Project(
               components=[
                   Reservoir(id="R1", name="Source", elevation=100, water_level=10,
                       downstream_connections=[
                           Connection(target_component_id="nonexistent")
                       ])
               ]
           )
   ```

4. **Pump Curve Validation:**
   ```python
   def test_pump_curve_minimum_points():
       with pytest.raises(ValidationError):
           PumpCurve(id="P1", name="Test", points=[
               FlowHeadPoint(flow=0, head=100)  # Only 1 point
           ])
   ```

---

## Dependencies

**Required Python Packages:**
- `pydantic>=2.0` (already installed)
- `annotated-types>=0.4` (for Annotated types)

**No new dependencies required.**

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Schema drift between Python/TypeScript | Medium | High | Generate TypeScript from Pydantic using `pydantic-to-typescript` |
| Over-validation blocking valid use cases | Medium | Medium | Start permissive, tighten based on feedback |
| Performance with large projects | Low | Medium | Use `model_dump(exclude_none=True)` for serialization |

---

## Definition of Done

- [ ] All models implemented as specified
- [ ] All models have docstrings
- [ ] Unit tests pass with >93% coverage
- [ ] Type checking passes (mypy --strict)
- [ ] Linting passes (ruff)
- [ ] Models serialize to JSON matching TSD specification
- [ ] Example project serializes and deserializes correctly

---

## Estimated Effort

| Step | Complexity | Effort |
|------|------------|--------|
| Steps 1-2 (Base, Units) | Low | Small |
| Step 3 (Piping) | Medium | Small |
| Step 4 (Pump) | Medium | Small |
| Step 5 (Components) | High | Medium |
| Step 6 (Fluids) | Low | Small |
| Step 7 (Project) | High | Medium |
| Step 8 (Results) | Medium | Small |
| Steps 9-10 (Exports, Tests) | Medium | Medium |

**Total:** Medium complexity

---

## Next Steps After This Issue

1. **Issue #3** - Create pipe materials and fittings data libraries (depends on piping models)
2. **Issue #4** - Implement fluid properties service (depends on fluids models)
3. **Issue #5** - Implement simple solver (depends on all models)
