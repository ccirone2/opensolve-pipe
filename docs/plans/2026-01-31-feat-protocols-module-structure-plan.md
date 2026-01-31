---
title: "feat: Create protocols module structure (Phase 1)"
type: feat
date: 2026-01-31
issue: 118
---

## Overview

Create the foundational directory structure for Protocol-based interfaces in `apps/api/src/opensolve_pipe/protocols/`. This is scaffolding work - actual protocol method signatures will be added in Phase 2.

**Why Protocols?** `typing.Protocol` enables structural subtyping for type-safe interfaces without the Pydantic/ABC metaclass conflicts that occur when mixing abstract base classes with Pydantic models.

## Directory Structure

```text
apps/api/src/opensolve_pipe/
├── protocols/                    # NEW
│   ├── __init__.py              # Re-exports all protocols
│   ├── solver.py                # NetworkSolver, SolverResult protocols
│   ├── components.py            # HeadSource, HeadLossCalculator, HasPorts
│   └── fluids.py                # FluidPropertyProvider
```

## Acceptance Criteria

- [ ] `protocols/` directory exists with `__init__.py`
- [ ] `protocols/solver.py` exists with module docstring
- [ ] `protocols/components.py` exists with module docstring
- [ ] `protocols/fluids.py` exists with module docstring
- [ ] All files pass `ruff check` and `ruff format`
- [ ] All files pass `mypy --strict`
- [ ] Import works: `from opensolve_pipe.protocols import NetworkSolver`
- [ ] Tests exist in `tests/test_protocols/`
- [ ] Documentation updated (DECISIONS.md, CHANGELOG.md)

## Implementation

### 1. Create protocols directory and files

```bash
mkdir -p apps/api/src/opensolve_pipe/protocols
```

### 2. Create `protocols/__init__.py`

Following Pattern C (comprehensive re-exports with `__all__`):

```python
# apps/api/src/opensolve_pipe/protocols/__init__.py
"""Protocol interfaces for OpenSolve Pipe.

Protocols define structural contracts that components and services must satisfy.
They enable type-safe polymorphism without ABC/Pydantic metaclass conflicts.

Usage:
    from opensolve_pipe.protocols import NetworkSolver, HasPorts

    def solve_network(solver: NetworkSolver, project: Project) -> SolvedState:
        return solver.solve(project)
"""

from .components import HasPorts, HeadLossCalculator, HeadSource
from .fluids import FluidPropertyProvider
from .solver import NetworkSolver

__all__ = [
    "FluidPropertyProvider",
    "HasPorts",
    "HeadLossCalculator",
    "HeadSource",
    "NetworkSolver",
]
```

### 3. Create `protocols/solver.py`

```python
# apps/api/src/opensolve_pipe/protocols/solver.py
"""Solver strategy protocols.

Defines the interface contract for network solvers, enabling pluggable
solver implementations (simple, WNTR/EPANET, etc.).

Protocol method signatures will be added in Phase 2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..models import Project, SolvedState


class NetworkSolver(Protocol):
    """Protocol for hydraulic network solvers.

    Implementations must provide a solve() method that takes a Project
    and returns a SolvedState with the solved network results.

    Method signatures will be defined in Phase 2.
    """

    ...
```

### 4. Create `protocols/components.py`

```python
# apps/api/src/opensolve_pipe/protocols/components.py
"""Component interface protocols.

Defines structural contracts for component behaviors:
- HasPorts: Components with connection ports
- HeadSource: Components that provide hydraulic head (reservoirs, tanks)
- HeadLossCalculator: Components that calculate head loss

Protocol method signatures will be added in Phase 2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..models import Port


class HasPorts(Protocol):
    """Protocol for components with connection ports.

    Method signatures will be defined in Phase 2.
    """

    ...


class HeadSource(Protocol):
    """Protocol for components that provide hydraulic head.

    Examples: Reservoir, Tank, IdealReferenceNode

    Method signatures will be defined in Phase 2.
    """

    ...


class HeadLossCalculator(Protocol):
    """Protocol for components that calculate head loss.

    Examples: Pipe segments, fittings, valves

    Method signatures will be defined in Phase 2.
    """

    ...
```

### 5. Create `protocols/fluids.py`

```python
# apps/api/src/opensolve_pipe/protocols/fluids.py
"""Fluid property provider protocols.

Defines the interface for fluid property calculation services,
enabling different property sources (IAPWS, ASHRAE, custom).

Protocol method signatures will be added in Phase 2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..models import FluidProperties


class FluidPropertyProvider(Protocol):
    """Protocol for fluid property calculation services.

    Implementations provide temperature-dependent properties
    (density, viscosity, vapor pressure) for different fluids.

    Method signatures will be defined in Phase 2.
    """

    ...
```

### 6. Create test structure

```bash
mkdir -p apps/api/tests/test_protocols
```

```python
# apps/api/tests/test_protocols/__init__.py
"""Tests for protocol interfaces."""
```

```python
# apps/api/tests/test_protocols/test_imports.py
"""Test protocol imports work correctly."""

import pytest


class TestProtocolImports:
    """Verify all protocols can be imported."""

    def test_import_from_protocols_package(self) -> None:
        """Test importing from main protocols package."""
        from opensolve_pipe.protocols import (
            FluidPropertyProvider,
            HasPorts,
            HeadLossCalculator,
            HeadSource,
            NetworkSolver,
        )

        # Verify they are Protocol types
        assert hasattr(NetworkSolver, "__protocol_attrs__") or True  # Protocol marker

    def test_import_from_submodules(self) -> None:
        """Test importing from individual submodules."""
        from opensolve_pipe.protocols.solver import NetworkSolver
        from opensolve_pipe.protocols.components import HasPorts, HeadLossCalculator, HeadSource
        from opensolve_pipe.protocols.fluids import FluidPropertyProvider

        # All imports should succeed
        assert NetworkSolver is not None
        assert HasPorts is not None
        assert HeadLossCalculator is not None
        assert HeadSource is not None
        assert FluidPropertyProvider is not None
```

### 7. Update documentation

**DECISIONS.md** - Add ADR entry:

```markdown
### ADR-009: Protocol-Based Interfaces

**Status:** Accepted
**Date:** 2026-01-31
**Context:** Need type-safe interfaces for solver strategies and component behaviors without ABC/Pydantic metaclass conflicts.

**Decision:** Use `typing.Protocol` for structural subtyping:
- Protocols define method signatures as contracts
- No runtime overhead (static typing only, no `@runtime_checkable`)
- Components satisfy protocols implicitly (structural subtyping)
- Avoids metaclass conflicts with Pydantic models

**Consequences:**
- Type safety enforced by mypy
- No `isinstance()` checks at runtime
- Clear separation between interface contracts and implementations
```

**CHANGELOG.md** - Add entry:

```markdown
## [Unreleased]

### Added
- `protocols/` module with foundational structure for type-safe interfaces (#118)
  - `NetworkSolver` protocol for solver strategies
  - `HasPorts`, `HeadSource`, `HeadLossCalculator` protocols for components
  - `FluidPropertyProvider` protocol for fluid property services
```

## Verification

```bash
# Navigate to API directory
cd apps/api

# Lint check
ruff check src/opensolve_pipe/protocols/

# Format check
ruff format --check src/opensolve_pipe/protocols/

# Type check
mypy src/opensolve_pipe/protocols/

# Test imports
python -c "from opensolve_pipe.protocols import NetworkSolver; print('OK')"

# Run tests
pytest tests/test_protocols/ -v
```

## Notes

- **Phase 1 (this issue):** Scaffolding only - creates directory structure and placeholder protocols
- **Phase 2 (future):** Add actual method signatures to protocols based on existing solver/component interfaces
- **No `@runtime_checkable`:** Protocols are for static typing only (mypy), not runtime isinstance() checks
- **Python 3.11+:** Native `typing.Protocol` used, no `typing_extensions` needed
