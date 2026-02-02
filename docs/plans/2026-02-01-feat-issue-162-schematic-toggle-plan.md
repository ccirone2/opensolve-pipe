---
title: "feat: Integrate Schematic Viewer as Toggle"
type: feat
date: 2026-02-01
issue: "#162"
---

## Overview

Integrate the existing SchematicViewer component into the main UI as a toggleable stacked view that persists across view mode switches (Build/Results).

## Problem Statement

The SchematicViewer component exists but is not integrated into the main project page UI. Users cannot visualize their pipe network as a schematic diagram while building or reviewing results.

## Proposed Solution

Add a schematic toggle button to the Header component that shows/hides the SchematicViewer in a stacked layout above the Panel/Results content. The toggle state persists when switching between Build and Results modes.

## Technical Approach

### Layout Design (Stacked)

```text
┌─────────────────────────────────────┐
│           Header                     │ ← Add schematic toggle button
├─────────────────────────────────────┤
│                                     │
│     SchematicViewer (collapsible)   │ ← Shows when toggle is ON
│                                     │
├─────────────────────────────────────┤
│                                     │
│     Panel Navigator OR Results      │ ← Existing content
│                                     │
└─────────────────────────────────────┘
```

### Implementation Tasks

- [x] 1. Add `showSchematic` state to project page
- [x] 2. Add schematic toggle button to Header component
- [x] 3. Render SchematicViewer when toggle is ON
- [x] 4. Wire up component click handlers for selection
- [x] 5. Pass solved results for overlay display
- [x] 6. Add collapse/expand animation
- [x] 7. Test on mobile responsiveness

## Acceptance Criteria

- [x] Schematic toggle button visible in Header
- [x] Toggle persists across Build/Results mode switches
- [x] Schematic displays actual project components with proper symbols
- [x] Clicking component in schematic selects it in Panel view
- [x] Results overlay shows flow/pressure when solved
- [x] Mobile-friendly layout
- [x] Smooth expand/collapse animation

## Files Modified

- `apps/web/src/routes/p/[...encoded]/+page.svelte` - Add state and render schematic
- `apps/web/src/lib/components/Header.svelte` - Add toggle button

## References

- SchematicViewer: `apps/web/src/lib/components/schematic/SchematicViewer.svelte`
- Layout utils: `apps/web/src/lib/utils/schematic/layout.ts`
- GitHub Issue: #162
