# Issue #48 Implementation Plan

## Refactor: Rename 'Nodes/Links' terminology to 'Components/Piping' (ADR-006)

**Issue:** [#48](https://github.com/ccirone2/opensolve-pipe/issues/48)
**Branch:** `feature/issue-48`
**ADR:** ADR-006 in `docs/DECISIONS.md`

---

## Summary

Rename user-facing "Nodes/Links" terminology to "Components/Piping" throughout the codebase. The internal solver can still use EPANET's node/link representation, but user-facing elements should use the new terminology.

---

## Implementation Steps

### Phase 1: Frontend UI Components (High Priority)

#### 1.1 Update ResultsPanel.svelte

- Change tab labels: "Nodes" → "Components", "Links" → "Piping"
- Update stat card labels in summary view
- Update component imports after renaming tables

#### 1.2 Rename NodeTable.svelte → ComponentTable.svelte

- Rename the file
- Update component name
- Keep internal functionality the same

#### 1.3 Rename LinkTable.svelte → PipingTable.svelte

- Rename the file
- Update component name
- Keep internal functionality the same

#### 1.4 Update results/index.ts

- Update exports to reflect new component names

### Phase 2: Frontend Models

#### 2.1 Update models/results.ts

- Rename `NodeResult` → `ComponentResult`
- Rename `LinkResult` → `PipingResult`
- Update `SolvedState` properties: `node_results` → `component_results`, `link_results` → `piping_results`

#### 2.2 Update models/index.ts

- Update exports

### Phase 3: Backend Models

#### 3.1 Update models/results.py

- Rename `NodeResult` → `ComponentResult`
- Rename `LinkResult` → `PipingResult`
- Update `SolvedState` fields: `node_results` → `component_results`, `link_results` → `piping_results`

#### 3.2 Update models/**init**.py

- Update exports

#### 3.3 Update routers/solve.py

- Update any references to old field names

### Phase 4: Tests

#### 4.1 Update frontend tests

- Update test file references and assertions

#### 4.2 Update backend tests

- Update test_results.py with new class and field names

### Phase 5: Documentation

#### 5.1 Update docs/PRD.md

- Section 3.1.1: "Nodes" → "Components"
- Section 3.1.2: "Links" → "Piping"

#### 5.2 Update docs/TSD.md

- Update any node/link terminology

---

## Breaking Changes

### API Response Structure

```json
// Before
{
  "node_results": {...},
  "link_results": {...},
  "pump_results": {...}
}

// After
{
  "component_results": {...},
  "piping_results": {...},
  "pump_results": {...}
}
```

This is a breaking change for any existing API consumers. Since this is pre-v1.0, we document it as a breaking change rather than adding backward compatibility.

---

## Acceptance Criteria

- [ ] No UI element displays "Node" or "Link" to users
- [ ] All TypeScript types use `ComponentResult` and `PipingResult`
- [ ] All Python models use `ComponentResult` and `PipingResult`
- [ ] API response uses `component_results` and `piping_results`
- [ ] All tests pass
- [ ] Documentation updated

---

## Files Changed

### Frontend

- `apps/web/src/lib/components/results/ResultsPanel.svelte`
- `apps/web/src/lib/components/results/NodeTable.svelte` → `ComponentTable.svelte`
- `apps/web/src/lib/components/results/LinkTable.svelte` → `PipingTable.svelte`
- `apps/web/src/lib/components/results/index.ts`
- `apps/web/src/lib/models/results.ts`
- `apps/web/src/lib/models/index.ts`
- `apps/web/src/lib/stores/__tests__/project.test.ts`

### Backend

- `apps/api/src/opensolve_pipe/models/results.py`
- `apps/api/src/opensolve_pipe/models/__init__.py`
- `apps/api/src/opensolve_pipe/routers/solve.py`
- `apps/api/tests/test_models/test_results.py`

### Documentation

- `docs/PRD.md`
- `docs/TSD.md`
