# Issue #223: Elevation Profile Visualization

## Overview

Add an interactive SVG-based Elevation Profile visualization as a new "Elevation" sub-tab
in the inspector Results panel. This shows physical pipe elevations, component positions,
HGL (hydraulic grade lines), and head losses across the system.

## Implementation Steps

### Step 1: Data Transformation Utility

**File:** `apps/web/src/lib/utils/elevationProfile.ts`

Create types and a `buildElevationData()` function that transforms the existing project
component chain + solved state into a flat array of `ElevationElement` objects ordered
from upstream to downstream.

**Mapping:**

- Component `elevation` field → `p1_el` (upstream port elevation)
- Port-specific elevations → `p2_el` (downstream port, if different)
- Tank `min_level` / `max_level` + elevation → `min_el` / `max_el`
- Reservoir `water_level` + elevation → `max_el`
- `PipingSegment.pipe.length` → `length` (connections only)
- `ComponentResult` HGL deltas / `PipingResult.head_loss` → `head_change`

### Step 2: ElevationProfile.svelte Component

**File:** `apps/web/src/lib/components/results/ElevationProfile.svelte`

Translate the React reference (`docs/features/viz_elevation_profile/fluid-circuit.jsx`)
to Svelte 5 with runes. Key sections:

1. **Data processing** — cumulative lengths, segments, boundaries
2. **SVG grid and axes** — auto-scaled Y (elevation), proportional X (length)
3. **Connection lines** — 3-piece (single) or 2-piece (series) routing
4. **Component markers** — color-coded circles at port elevations
5. **Tank water level ranges** — pulsing rectangles between min/max
6. **Min/max indicators** — amber dashed lines for pipe high/low points
7. **No-flow HGL** — purple dashed line at tank surfaces, jump at pumps
8. **Flowing HGL** — green solid line from cumulative head changes, clipped
9. **Hover tooltips** — element details with head change color coding
10. **Toggle controls** — checkboxes for Min/Max, No-Flow HGL, Flowing HGL
11. **Data table** — tabular view with hover cross-highlighting
12. **Theme support** — CSS variables for dark/light mode

### Step 3: ResultsPanel Integration

**File:** `apps/web/src/lib/components/results/ResultsPanel.svelte`

- Add `'elevation'` to the `TabId` type
- Add Elevation tab to the `tabs` array (always shown when results exist)
- Add `{:else if activeTab === 'elevation'}` block rendering `ElevationProfile`
- Pass components, connections, and solvedState to ElevationProfile

### Step 4: Tests

**File:** `apps/web/src/lib/utils/__tests__/elevationProfile.test.ts`

- Test buildElevationData with a simple linear network
- Test head_change mapping from solved results
- Test tank min/max elevation computation
- Test empty/missing results handling

### Step 5: Build Verification

- `pnpm build` passes
- `npx vitest run` passes
- All existing tests still pass

## No Backend Changes

All data transformation is done client-side. The existing solve response
(`SolvedState`) plus project components already contain all necessary data.

## Files Created/Modified

| Action   | File |
|----------|------|
| Create   | `apps/web/src/lib/utils/elevationProfile.ts` |
| Create   | `apps/web/src/lib/components/results/ElevationProfile.svelte` |
| Create   | `apps/web/src/lib/utils/__tests__/elevationProfile.test.ts` |
| Modify   | `apps/web/src/lib/components/results/ResultsPanel.svelte` |
| Modify   | `docs/CHANGELOG.md` |
