---
title: feat: Add port-level hydraulic results instead of component-level results
type: feat
date: 2026-01-25
issue: 77
---

<!-- markdownlint-disable MD025 -->

## Port-Level Hydraulic Results

## Overview

The backend currently provides hydraulic results (pressure, HGL, EGL) at the **component level**, but the frontend UI now displays results **per port**. This means all ports of a multi-port component (e.g., pump with suction/discharge, valve with inlet/outlet) show identical values, which doesn't reflect the actual hydraulic conditions at each port.

## Problem Statement

Currently:

- `component_results` in `SolvedState` is keyed by `component_id`
- All ports of a component share the same pressure/HGL/EGL values
- Frontend shows repeated values for each port row (e.g., pump suction and discharge show same pressure)

This is physically incorrect:

- Pump suction has lower pressure than discharge (pump adds head)
- Valve inlet has higher pressure than outlet (valve causes pressure drop)
- Branch ports have different pressures depending on flow split

## Proposed Solution

Change the result key structure from `component_id` to `{component_id}_{port_id}` for port-specific results.

### Data Model Changes

**Backend (`apps/api/src/opensolve_pipe/models/results.py`):**

```python
class ComponentResult(OpenSolvePipeBaseModel):
    component_id: str  # Component ID
    port_id: str       # NEW: Port ID (e.g., "suction", "discharge")
    pressure: float
    dynamic_pressure: float = 0.0
    total_pressure: float
    hgl: float
    egl: float
```

**Frontend (`apps/web/src/lib/models/results.ts`):**

```typescript
export interface ComponentResult {
    component_id: string;
    port_id: string;  // NEW
    pressure: number;
    dynamic_pressure: number;
    total_pressure: number;
    hgl: number;
    egl: number;
}
```

### Key Structure Change

From:

```json
{
  "component_results": {
    "pump_1": { "pressure": 45.0, "hgl": 103.9, ... }
  }
}
```

To:

```json
{
  "component_results": {
    "pump_1_suction": { "component_id": "pump_1", "port_id": "suction", "pressure": 4.3, "hgl": 10.0, ... },
    "pump_1_discharge": { "component_id": "pump_1", "port_id": "discharge", "pressure": 56.3, "hgl": 130.0, ... }
  }
}
```

## Technical Approach

### Phase 1: Backend Model Update

**File: `apps/api/src/opensolve_pipe/models/results.py`**

1. Add `port_id` field to `ComponentResult` model
2. Keep backward compatibility by making `port_id` optional with default "default"

### Phase 2: Backend Solver Update

**File: `apps/api/src/opensolve_pipe/services/solver/network.py`**

1. Modify `SolverState.pressures` to store port-level values keyed by `{comp_id}_{port_id}`
2. Update `solve_simple_path()` to calculate and store pressures at each port:
   - For pump: calculate suction pressure (before pump head) and discharge pressure (after pump head)
   - For valve: calculate inlet pressure (before) and outlet pressure (after pressure drop)
   - For single-port components: use the single port ID
3. Update `solve_branching_network()` similarly
4. Update `solve_project()` result building to emit port-keyed results

### Phase 3: Frontend Model Update

**File: `apps/web/src/lib/models/results.ts`**

1. Add `port_id` field to `ComponentResult` interface
2. Add helper function `getPortResult(state, componentId, portId)`

### Phase 4: Frontend Component Update

**File: `apps/web/src/lib/components/results/ComponentTable.svelte`**

1. Update lookup logic to use `{componentId}_{portId}` key
2. Handle fallback for components without port-specific results

## Acceptance Criteria

- [ ] Backend `ComponentResult` model includes `port_id` field
- [ ] Backend solver calculates and returns per-port hydraulic values
- [ ] Results keyed by `{component_id}_{port_id}` in `component_results`
- [ ] Pump suction vs discharge ports show different pressures
- [ ] Valve inlet vs outlet ports show pressure drop across valve
- [ ] Frontend displays unique values per port
- [ ] Existing single-port components continue to work
- [ ] All existing tests pass
- [ ] New tests cover port-level result generation

## Implementation Files

### Backend

- `apps/api/src/opensolve_pipe/models/results.py` - Add port_id field
- `apps/api/src/opensolve_pipe/services/solver/network.py` - Calculate port-level pressures

### Frontend

- `apps/web/src/lib/models/results.ts` - Add port_id field
- `apps/web/src/lib/components/results/ComponentTable.svelte` - Update lookup logic

### Tests

- `apps/api/tests/services/solver/test_network.py` - Verify port-level results

## References

- Issue: #77
- Related PR: #78 (frontend port display)
- SDD Section 4.10: Solved State models
