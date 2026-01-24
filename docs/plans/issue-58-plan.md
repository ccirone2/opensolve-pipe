# Implementation Plan: Issue #58 - Backend Port-Based Architecture

## Summary

Implement the port-based connection architecture that enables components with variable numbers of connection points, providing explicit inlet/outlet ports and pipe connections between specific ports.

## Tasks

### 1. Create Port Model (`apps/api/src/opensolve_pipe/models/ports.py`)

- [ ] Define `PortDirection` enum (INLET, OUTLET, BIDIRECTIONAL)
- [ ] Define `Port` model with id, nominal_size, direction fields
- [ ] Create port factory functions for each component type

### 2. Create PipeConnection Model (`apps/api/src/opensolve_pipe/models/connections.py`)

- [ ] Define `PipeConnection` model with from/to component and port IDs
- [ ] Include optional `piping` field (PipingSegment)
- [ ] Add validation for matching port sizes (within tolerance)
- [ ] Add validation for port directions (inlet → outlet)

### 3. Update BaseComponent (`apps/api/src/opensolve_pipe/models/components.py`)

- [ ] Add `ports: list[Port]` field to BaseComponent
- [ ] Keep `downstream_connections` for backward compatibility but mark as deprecated
- [ ] Add helper methods for port access

### 4. Add Port Configurations to Components

- [ ] Reservoir: 1-n bidirectional ports
- [ ] Tank: 1-n bidirectional ports
- [ ] Junction: 1-n bidirectional ports
- [ ] Pump: 2 ports (suction inlet, discharge outlet)
- [ ] Valve: 2 ports (inlet, outlet)
- [ ] HeatExchanger: 2 ports (inlet, outlet)
- [ ] Strainer: 2 ports (inlet, outlet)
- [ ] Orifice: 2 ports (inlet, outlet)
- [ ] Sprinkler: 1 port (inlet)

### 5. Update Project Model (`apps/api/src/opensolve_pipe/models/project.py`)

- [ ] Add `connections: list[PipeConnection]` field
- [ ] Add validators for connection validity
- [ ] Maintain backward compatibility with downstream_connections

### 6. Update PipingSegment Model (`apps/api/src/opensolve_pipe/models/piping.py`)

- [ ] Add support for multiple pipe segments in series (list of PipeDefinition)

### 7. Write Unit Tests

- [ ] Test port creation for each component type
- [ ] Test PipeConnection validation
- [ ] Test port size compatibility validation
- [ ] Test port direction validation
- [ ] Test Project-level connection validation
- [ ] Ensure existing tests continue to pass

## Acceptance Criteria

- All components have explicit port definitions
- Pipe connections reference specific ports
- Port size validation catches mismatched connections
- Existing tests continue to pass with new model

## Dependencies

- Issue #5 (Data Models) - COMPLETED
