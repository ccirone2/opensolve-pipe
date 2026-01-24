# Implementation Plan: Issue #59 - Backend Reference Node and Plug Components

## Summary

Implement Reference Node and Plug/Cap components for defining boundary conditions in the network.

## Tasks

### 1. Reference Node Models (`apps/api/src/opensolve_pipe/models/reference_node.py`)

- [x] Define `FlowPressurePoint` model for curve data
- [x] Define `ReferenceNode` base model with single port
- [x] Define `IdealReferenceNode` model (fixed pressure boundary)
- [x] Define `NonIdealReferenceNode` model (pressure-flow curve)
- [x] Add `ReferenceType` enum (IDEAL, NON_IDEAL)
- [x] Add port factory function for reference nodes

### 2. Plug Model (`apps/api/src/opensolve_pipe/models/plug.py`)

- [x] Define `Plug` model with single port (zero flow boundary)
- [x] Add port factory function for plug

### 3. Update Component Types

- [x] Add IDEAL_REFERENCE_NODE and NON_IDEAL_REFERENCE_NODE to ComponentType enum
- [x] Add PLUG to ComponentType enum
- [x] Add to discriminated union in components.py
- [x] Update __init__.py exports

### 4. Write Unit Tests

- [x] Test reference node model creation and validation
- [x] Test plug model creation and validation
- [x] Test port configurations for both components
- [x] Test pressure-flow curve validation for non-ideal nodes

## Dependencies

- Issue #58 (Port-Based Architecture) - REQUIRED

## Acceptance Criteria

- [x] Reference nodes have single bidirectional port
- [x] Ideal reference node can specify fixed pressure
- [x] Non-ideal reference node can specify pressure-flow curve
- [x] Plug enforces zero flow at connected port
- [x] All models serialize/deserialize correctly
