# Implementation Plan: Issue #60 - Backend Branch Component (Tee/Wye/Cross)

## Summary

Implement Branch components for flow splitting/combining with proper K-factor calculations based on Crane TP-410.

## Tasks

### 1. Branch Models (`apps/api/src/opensolve_pipe/models/branch.py`)

- [x] Define `BranchType` enum (TEE, WYE, CROSS)
- [x] Define `BaseBranch` base model with variable ports
- [x] Define `TeeBranch` model (3 ports: run_inlet, run_outlet, branch)
- [x] Define `WyeBranch` model (3 ports with configurable angle)
- [x] Define `CrossBranch` model (4 ports)
- [x] Add port factory functions for each branch type
- [x] Validate port configurations

### 2. Update Component Types

- [x] Add TEE_BRANCH, WYE_BRANCH, CROSS_BRANCH to ComponentType enum
- [x] Add to discriminated union in components.py
- [x] Update __init__.py exports

### 3. Write Unit Tests

- [x] Test branch model creation and validation
- [x] Test port configurations for each branch type
- [x] Test serialization roundtrips
- [x] Test discriminated union parsing

## Notes

K-factor calculations and solver integration will be handled in a separate issue as they require more complex hydraulic logic. This issue focuses on the data models only.

## Dependencies

- Issue #58 (Port-Based Architecture) - REQUIRED
- Issue #59 (Reference Node and Plug) - builds on same branch

## Acceptance Criteria

- [x] TeeBranch has 3 ports (run_inlet, run_outlet, branch)
- [x] WyeBranch has 3 ports with configurable branch angle
- [x] CrossBranch has 4 ports
- [x] All models serialize/deserialize correctly
- [x] All models work in Component discriminated union
