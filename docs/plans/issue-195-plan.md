# Issue #195: Add Library Tab to Navigation Panel

## Overview

Add a "Library" tab to the sidebar navigation panel for managing reusable data definitions: pump curves (fully functional), loss curves and reference profiles (placeholder UI with "Coming Soon" labels).

## Scope (Minimal Viable Implementation)

### In Scope

1. Add "Library" tab to sidebar (next to Tree/Config/Results)
2. Display existing `pump_library` items in the Library tab
3. Pump curve CRUD: create, edit (name + data points), delete
4. Placeholder sections for "Loss Curves" and "Reference Profiles" (Coming Soon UI)
5. Backend pump curve validation (already exists via `PumpCurve` model with `min_length=2`)

### Out of Scope (Future Work)

- Chart.js pump curve visualization
- Full loss curve data model and editor
- Full reference profile data model and editor
- Component property panels referencing library items via dropdown
- Usage indicators (which components reference library items)

## Implementation Plan

### Step 1: Extend SidebarTab Type

**File:** `apps/web/src/lib/stores/workspace.ts`

- Add `'library'` to `SidebarTab` union type

### Step 2: Add Library Tab Icon to SidebarTabs

**File:** `apps/web/src/lib/components/workspace/SidebarTabs.svelte`

- Add `{ id: 'library', label: 'Library' }` to tabs array
- Add a book/library SVG icon for the new tab
- Wire up the tab content to render `LibraryTab` component

### Step 3: Create LibraryTab Component

**New File:** `apps/web/src/lib/components/workspace/LibraryTab.svelte`

- Main container with three collapsible sections:
  - Pump Curves (functional)
  - Loss Curves (Coming Soon placeholder)
  - Reference Profiles (Coming Soon placeholder)

### Step 4: Create PumpCurveList Component

**New File:** `apps/web/src/lib/components/workspace/PumpCurveList.svelte`

- List of pump curves from `pumpLibrary` store
- "Add Pump Curve" button
- Each item shows name + point count + delete button
- Click item to expand inline editor

### Step 5: Create PumpCurveEditor Component

**New File:** `apps/web/src/lib/components/workspace/PumpCurveEditor.svelte`

- Form fields: name, manufacturer, model (optional)
- Data points table: flow/head pairs with add/remove rows
- Validate minimum 2 points
- Save/cancel buttons

### Step 6: Export New Components

**File:** `apps/web/src/lib/components/workspace/index.ts`

- Add exports for LibraryTab

### Step 7: Validate

- `pnpm svelte-check` passes
- `pnpm build` passes
- Backend validation already in place (PumpCurve Pydantic model)
