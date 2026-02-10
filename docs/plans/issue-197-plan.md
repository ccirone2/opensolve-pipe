# Issue #197: Make Navigation Sidebar Panel Wider

## Current State

- Sidebar width is defined as CSS custom property: `--sidebar-width: 260px` in `/workspace/apps/web/src/app.css` (line 26)
- The workspace uses CSS Grid with `grid-template-columns: var(--sidebar-width) 1fr var(--inspector-width)`
- Inspector width is `--inspector-width: 380px`
- No hardcoded widths found in sidebar child components (SidebarTabs, ComponentTree, etc.)
- Mobile layout uses `grid-template-columns: 1fr` and hides sidebar entirely (BottomSheet replaces it)

## Changes

### 1. Increase `--sidebar-width` from 260px to 280px

- File: `apps/web/src/app.css`, line 26
- Change: `--sidebar-width: 260px` -> `--sidebar-width: 280px`
- This single change propagates through all grid template references:
  - `.workspace` default layout
  - `.workspace.inspector-collapsed` layout
  - Sidebar collapsed states already use `0px` (unaffected)

### 2. No other changes needed

- No components have hardcoded sidebar widths
- Mobile layout is unaffected (sidebar hidden, uses BottomSheet)
- Focus mode is unaffected (uses `grid-template-columns: 1fr`)
- Inspector width unchanged at 380px

## Impact Analysis

| Screen Width | Canvas before (260px sidebar) | Canvas after (280px sidebar) | Delta |
|---|---|---|---|
| 1280px | 640px | 620px | -20px |
| 1440px | 800px | 780px | -20px |
| 1920px | 1280px | 1260px | -20px |

The canvas loses 20px, which is negligible. Layout remains balanced at all standard sizes.

## Acceptance Criteria

- [x] Sidebar is visibly wider (~280px)
- [x] Component names and property values have more room
- [x] Layout balanced on 1280px+ screens
- [x] Canvas area not excessively compressed
- [x] Mobile layout unaffected
