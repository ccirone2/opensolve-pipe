# Implementation Plan: Issue #61 - Frontend Port Connection Editor

## Summary

Create UI for managing port-based connections between components.

## Tasks

### 1. Update Frontend Models (COMPLETED)

- [x] Add Port and PortDirection types to components.ts
- [x] Add PipeConnection type for port-based connections
- [x] Update component interfaces to include ports field
- [x] Add new component types (IdealReferenceNode, NonIdealReferenceNode, Plug, branches)
- [x] Add port factory functions for each component type
- [x] Add type guards for new components
- [x] Update createDefaultComponent to include ports

### 2. Update Project Model (COMPLETED)

- [x] Add connections list to Project interface
- [x] Update createNewProject to include empty connections array
- [x] Add connection validation functions
- [x] Add connection helper functions (getConnectionById, getConnectionsFromComponent, etc.)
- [x] Update example project with ports and connections

### 3. Update Project Store (COMPLETED)

- [x] Add PipeConnection import and generateConnectionId
- [x] Add addPipeConnection function
- [x] Add removePipeConnection function
- [x] Add updatePipeConnectionPiping function
- [x] Add getConnectionsForComponent function
- [x] Add connections derived store

### 4. Create Port and Connection UI Components (TODO)

- [ ] Create `PortSelector.svelte` - dropdown to select a port from a component
- [ ] Create `PortConnectionEditor.svelte` - manage connection between two ports
- [ ] Add port display in component forms (showing available ports)

### 5. Update Existing UI (TODO)

- [ ] Update PipingPanel to work with port-based connections
- [ ] Show visual indicators for connected vs unconnected ports
- [ ] Display validation errors for invalid connections

### 6. Write Tests (TODO)

- [ ] Test PortSelector component
- [ ] Test PortConnectionEditor component
- [ ] Test project store connection functions

## Dependencies

- Issue #58 (Backend Port-Based Architecture) - REQUIRED
- Issue #59 (Reference Node and Plug) - for new component types
- Issue #60 (Branch Components) - for branch types

## Acceptance Criteria

- [x] Port and PipeConnection types defined
- [x] Project store can manage connections
- [x] All existing tests pass
- [ ] Users can select source and target ports for connections (UI TODO)
- [ ] Invalid connections show clear errors (UI TODO)
- [ ] All available ports are visible in the selector (UI TODO)
- [ ] Connection state updates correctly in the store (DONE)

## Notes

This PR completes the model and store updates for port-based connections.
The UI components (PortSelector, PortConnectionEditor) will be implemented
in a follow-up PR as they require more design consideration.
