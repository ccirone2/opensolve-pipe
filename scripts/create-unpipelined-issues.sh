#!/bin/bash
# Create GitHub issues for unpipelined Phase 2 features
# Run: gh auth login && ./scripts/create-unpipelined-issues.sh

set -e

REPO="ccirone2/opensolve-pipe"

echo "Creating issues for unpipelined Phase 2 features..."

# Issue 1: Schematic click-to-navigate (HIGH PRIORITY)
echo "Creating issue 1/6: Schematic click-to-navigate..."
gh issue create --repo "$REPO" \
  --title "Integrate schematic click-to-navigate with panel navigator" \
  --label "enhancement,integration,high-priority" \
  --body "$(cat <<'EOF'
## Summary
The schematic click handler exists but doesn't fully navigate to the clicked component in the panel navigator.

## Current State
- ✅ SchematicViewer component fully implemented
- ✅ Component click handler registered in `apps/web/src/routes/p/[...encoded]/+page.svelte`
- ✅ Navigation store with `navigationStore.navigateTo(componentId)` method exists
- ✅ PanelNavigator properly uses navigation store for previous/next

## What's Missing
- ❌ No call to `navigationStore.navigateTo(componentId)` in the schematic click handler
- The handler only switches to panel view but doesn't navigate to the specific component

## Code Location
`apps/web/src/routes/p/[...encoded]/+page.svelte` (lines 28-40)

```typescript
// Current implementation (incomplete):
function handleSchematicComponentClick(componentId: string) {
  // The PanelNavigator will need to expose a way to navigate to a specific component
  // For now, we at least switch to panel view
  if (viewMode !== 'panel') {
    viewMode = 'panel';
  }
}
```

## Proposed Fix
```typescript
function handleSchematicComponentClick(componentId: string) {
  navigationStore.navigateTo(componentId);  // ← Add this
  if (viewMode !== 'panel') {
    viewMode = 'panel';
  }
}
```

## Acceptance Criteria
- [ ] Clicking a component in the schematic navigates to that component's panel
- [ ] View automatically switches to panel mode if in schematic-only mode
- [ ] Navigation history is properly updated

## Priority
**HIGH** - Core UX feature that connects the two main UI modes
EOF
)"

# Issue 2: Undo/Redo UI (HIGH PRIORITY)
echo "Creating issue 2/6: Undo/Redo UI..."
gh issue create --repo "$REPO" \
  --title "Add Undo/Redo UI controls and keyboard shortcuts" \
  --label "enhancement,ui,high-priority" \
  --body "$(cat <<'EOF'
## Summary
Undo/Redo functionality is fully implemented in the project store but has NO UI exposure.

## Current State
- ✅ Complete undo/redo history system with stacks (`apps/web/src/lib/stores/project.ts` lines 450-469)
- ✅ `historyStore` with past/future state tracking
- ✅ All project modifications save to history automatically
- ✅ Methods `projectStore.undo()` and `projectStore.redo()` work correctly
- ✅ `canUndo` and `canRedo` derived stores available in `apps/web/src/lib/stores/index.ts`

## What's Missing
- ❌ No UI buttons to trigger undo/redo
- ❌ No keyboard shortcuts (Ctrl+Z / Cmd+Z, Ctrl+Shift+Z / Cmd+Shift+Z)
- ❌ No visual indicator of undo/redo availability
- ❌ Zero references to undo/redo in any Svelte component

## Proposed Implementation

### 1. Add buttons to Header component
```svelte
<script>
  import { projectStore, canUndo, canRedo } from '$lib/stores';
</script>

<button on:click={() => projectStore.undo()} disabled={!$canUndo}>
  Undo
</button>
<button on:click={() => projectStore.redo()} disabled={!$canRedo}>
  Redo
</button>
```

### 2. Add keyboard shortcuts
```svelte
<svelte:window on:keydown={handleKeydown} />

<script>
  function handleKeydown(e: KeyboardEvent) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
      e.preventDefault();
      if (e.shiftKey) {
        projectStore.redo();
      } else {
        projectStore.undo();
      }
    }
  }
</script>
```

## Acceptance Criteria
- [ ] Undo/Redo buttons visible in header
- [ ] Buttons disabled when action unavailable
- [ ] Ctrl+Z / Cmd+Z triggers undo
- [ ] Ctrl+Shift+Z / Cmd+Shift+Z triggers redo
- [ ] Visual feedback on undo/redo action

## Priority
**HIGH** - Essential editing feature users expect
EOF
)"

# Issue 3: Project Settings UI (MEDIUM PRIORITY)
echo "Creating issue 3/6: Project Settings UI..."
gh issue create --repo "$REPO" \
  --title "Create Project Settings panel/modal UI" \
  --label "enhancement,ui,medium-priority" \
  --body "$(cat <<'EOF'
## Summary
Project settings data model exists but there's NO UI to view or edit settings.

## Current State
- ✅ `ProjectSettings` interface defined in `apps/web/src/lib/models/project.ts`
  ```typescript
  interface ProjectSettings {
    units: UnitPreferences;
    enabled_checks: string[];
    solver_options: SolverOptions;
  }
  ```
- ✅ `projectStore.updateSettings()` method exists
- ✅ Settings saved in every project
- ✅ Backend supports settings

## What's Missing
- ❌ No UI component to view/edit settings
- ❌ No settings panel, modal, or menu option
- ❌ No access point in header or navigation
- ❌ Users cannot change units, design checks, or solver options

## Proposed Implementation

### 1. Create SettingsPanel component
```
apps/web/src/lib/components/settings/SettingsPanel.svelte
```

Sections:
- **Units**: Select display units for pressure, flow, length, etc.
- **Design Checks**: Toggle enabled/disabled checks
- **Solver Options**: Max iterations, tolerance, etc.

### 2. Add access point
- Settings icon/button in Header
- Opens modal or slide-out panel

### 3. Wire to store
```svelte
<script>
  import { projectStore, currentProject } from '$lib/stores';

  function updateUnits(units: UnitPreferences) {
    projectStore.updateSettings({
      ...$currentProject.settings,
      units
    });
  }
</script>
```

## Acceptance Criteria
- [ ] Settings accessible from header
- [ ] Can view current unit preferences
- [ ] Can change unit preferences
- [ ] Can toggle design checks
- [ ] Can modify solver options
- [ ] Changes persist to project state/URL

## Priority
**MEDIUM** - Important for usability, especially unit preferences
EOF
)"

# Issue 4: Fluid Selection UI (MEDIUM PRIORITY)
echo "Creating issue 4/6: Fluid Selection UI..."
gh issue create --repo "$REPO" \
  --title "Create Fluid Selection and Properties UI" \
  --label "enhancement,ui,medium-priority" \
  --body "$(cat <<'EOF'
## Summary
Backend fluid API and frontend client exist but there's NO UI to select or view fluids.

## Current State
- ✅ Backend API endpoints for fluids
- ✅ Frontend API client functions in `apps/web/src/lib/api/client.ts`:
  - `listFluids()` - exported but never called
  - `getFluidProperties()` - exported but never called
  - `calculateFluidProperties()` - exported but never called
- ✅ Project has `fluid` field in data model
- ✅ Backend fluid library with temperature-dependent properties

## What's Missing
- ❌ No UI to select/change project fluid
- ❌ No fluid properties display
- ❌ No temperature input for property calculation
- ❌ API client functions are never called from any component

## Proposed Implementation

### 1. Create FluidSelector component
```
apps/web/src/lib/components/fluid/FluidSelector.svelte
```

Features:
- Dropdown to select from available fluids
- Temperature input field
- Display calculated properties (density, viscosity, etc.)
- Real-time property updates when temperature changes

### 2. Integration points
- Project settings panel (primary)
- Possibly inline in component panels that need fluid data

### 3. Wire to API
```svelte
<script>
  import { listFluids, calculateFluidProperties } from '$lib/api/client';

  let fluids = [];
  let selectedFluid = 'water';
  let temperature = 20; // °C
  let properties = null;

  onMount(async () => {
    fluids = await listFluids();
  });

  $: calculateFluidProperties(selectedFluid, temperature)
    .then(p => properties = p);
</script>
```

## Acceptance Criteria
- [ ] Can select fluid from available options
- [ ] Can input temperature
- [ ] Displays calculated fluid properties
- [ ] Properties update when temperature changes
- [ ] Selected fluid persists to project

## Priority
**MEDIUM** - Important for accurate calculations with non-water fluids
EOF
)"

# Issue 5: Local Storage Persistence (MEDIUM PRIORITY)
echo "Creating issue 5/6: Local Storage Persistence..."
gh issue create --repo "$REPO" \
  --title "Implement auto-save and recovery via localStorage" \
  --label "enhancement,feature,medium-priority" \
  --body "$(cat <<'EOF'
## Summary
Local storage methods exist but are never called - no auto-save or recovery functionality.

## Current State
- ✅ `projectStore.saveToLocalStorage()` method exists (`apps/web/src/lib/stores/project.ts`)
- ✅ `projectStore.loadFromLocalStorage()` method exists
- ✅ Complete implementation ready to use

## What's Missing
- ❌ No auto-save on project changes
- ❌ No load from localStorage on app start
- ❌ No recovery UI for unsaved work
- ❌ Methods are never called anywhere

## Proposed Implementation

### 1. Auto-save on changes
```typescript
// In project store or layout
$: if ($currentProject) {
  // Debounce to avoid excessive saves
  debounce(() => projectStore.saveToLocalStorage(), 1000);
}
```

### 2. Recovery on app load
```svelte
<!-- In +layout.svelte or +page.svelte -->
<script>
  onMount(() => {
    // If no URL project and localStorage has data, offer recovery
    if (!urlHasProject && projectStore.hasLocalStorageData()) {
      showRecoveryModal = true;
    }
  });
</script>

{#if showRecoveryModal}
  <RecoveryModal
    onRecover={() => projectStore.loadFromLocalStorage()}
    onDiscard={() => projectStore.clearLocalStorage()}
  />
{/if}
```

### 3. Recovery UI component
- Modal asking "Recover unsaved project?"
- Shows last save timestamp
- Options: Recover / Start Fresh

## Acceptance Criteria
- [ ] Project auto-saves to localStorage on changes
- [ ] On app load, check for recoverable project
- [ ] Recovery modal shown when unsaved work exists
- [ ] User can choose to recover or start fresh
- [ ] Clear localStorage when URL project is loaded

## Priority
**MEDIUM** - Prevents data loss, improves user experience
EOF
)"

# Issue 6: Branching UI Discoverability (LOW PRIORITY)
echo "Creating issue 6/6: Branching UI Discoverability..."
gh issue create --repo "$REPO" \
  --title "Improve branching feature discoverability in UI" \
  --label "enhancement,ux,low-priority" \
  --body "$(cat <<'EOF'
## Summary
BranchSelector component exists and works but has limited discoverability.

## Current State
- ✅ `BranchSelector.svelte` component functional
- ✅ Adds branches, manages downstream connections
- ✅ Supports loop closure (connect to existing components)

## Current Limitations
- Only appears in "Downstream" tab for tee/wye/cross components
- User must navigate to a branch component and go to downstream tab to find it
- Not discoverable for new users

## Proposed Improvements

### Option A: Visual indicators
- Add branch icons on schematic
- Tooltip hints on branch components
- "Add branch" quick action in component panel header

### Option B: Onboarding/Help
- First-time user tooltip
- Help documentation
- Example project with branches

### Option C: Quick actions
- Right-click context menu on schematic
- Floating action button for common operations

## Acceptance Criteria
- [ ] New users can discover how to add branches
- [ ] Clear visual indication of branch capability
- [ ] Documented in help/onboarding

## Priority
**LOW** - Feature works, just needs better discoverability
EOF
)"

echo ""
echo "✅ All 6 issues created successfully!"
echo ""
echo "View issues at: https://github.com/$REPO/issues"
