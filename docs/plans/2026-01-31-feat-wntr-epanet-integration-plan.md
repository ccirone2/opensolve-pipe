---
title: "Backend - WNTR/EPANET Integration for Looped Networks"
type: feat
date: 2026-01-31
issue: "#128"
---

## Plan Overview

## Overview

Integrate WNTR (Water Network Tool for Resilience) library to solve looped hydraulic networks using the EPANET solver engine.

## Technical Approach

### Architecture

The integration follows an adapter pattern:

1. **EPANET Module** (`epanet.py`) - Core WNTR wrapper and network builder
2. **Looped Solver** (`strategies/looped.py`) - NetworkSolver protocol implementation (Issue #129)
3. **EPANET Adapter** (`epanet_adapter.py`) - Component mapping logic (Issue #130)

### Component Mapping

| OpenSolve Component | WNTR Equivalent |
|---------------------|-----------------|
| Reservoir | `wn.add_reservoir()` |
| Tank | `wn.add_tank()` |
| Junction | `wn.add_junction()` |
| IdealReferenceNode | `wn.add_reservoir()` with head |
| NonIdealReferenceNode | `wn.add_reservoir()` with pattern |
| Plug | Junction with zero demand |
| Pump | `wn.add_pump()` |
| Valve (gate/ball/butterfly) | Pipe with K-factor loss |
| Valve (PRV/PSV/FCV) | `wn.add_valve()` |
| TeeBranch/WyeBranch/CrossBranch | Multiple junctions |
| PipeConnection | `wn.add_pipe()` |

### Implementation Tasks

1. **Add WNTR dependency** to `pyproject.toml`
2. **Create epanet.py module** with:
   - `WNTRNetwork` class - wrapper for wntr.network.WaterNetworkModel
   - `build_wntr_network(project)` - convert OpenSolve project to WNTR network
   - `run_epanet_simulation(wn)` - execute EPANET solver
   - `convert_wntr_results(results, project)` - map back to SolvedState
3. **Handle edge cases**:
   - Empty networks
   - No sources
   - Disconnected components
   - Solver convergence failures
4. **Write comprehensive tests**

## Files to Create/Modify

### New Files

- `apps/api/src/opensolve_pipe/services/solver/epanet.py`

### Modified Files

- `apps/api/pyproject.toml` - add wntr dependency
- `apps/api/src/opensolve_pipe/services/solver/__init__.py` - export new functions

## Acceptance Criteria

- [ ] WNTR solves simple networks with same results as SimpleSolver (< 1% deviation)
- [ ] WNTR handles looped networks that SimpleSolver cannot
- [ ] Clear error messages when EPANET fails to converge
- [ ] All tests pass with >93% coverage

## Dependencies

- `wntr>=1.2.0` library
