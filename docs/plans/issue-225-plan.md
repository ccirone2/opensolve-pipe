# Issue #225: HGL Calculation - Port Elevation and Surface Pressure

## Status: In Progress

## Remaining Work Items

### 1. Integrate surface_pressure into `get_source_head()` (HIGH)

- Add optional `fluid_props` parameter
- When surface_pressure != 0, convert to ft of head and add to total_head
- Conversion: `pressure_head_ft = surface_pressure_psi * 2.31 / specific_gravity`
- Update callers: line 412 (simple solver), line 1120 (branching solver)

### 2. WNTR solver surface_pressure (MEDIUM)

- Reservoir: include surface_pressure in `base_head` calculation
- Tank: surface_pressure doesn't map directly to WNTR tank params;
  add it to the head pattern or use total_head_with_pressure for initial head

### 3. Port elevation in solver (LOW)

- HGL is independent of observation point, so port_pressures storage is correct as-is
- Port elevation affects pipe connection routing, not HGL values
- Document this in code comments; no code change needed

### 4. Tests

- Test `get_source_head()` with surface_pressure != 0
- Test `total_head_with_pressure()` for Reservoir and Tank
- Test WNTR reservoir head includes surface_pressure

## Files Modified

- `apps/api/src/opensolve_pipe/services/solver/network.py`
- `apps/api/src/opensolve_pipe/services/solver/epanet.py`
- `apps/api/tests/test_protocols/test_head_source.py`
