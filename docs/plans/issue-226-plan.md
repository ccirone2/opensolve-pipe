# Issue #226: Inspector Pane Shows Selected Entity Details from Results Views

## Summary

When clicking items in Results views, navigate the inspector panel to that entity's configuration.

## Implementation

### Pattern

Replicate the existing schematic click handler pattern:

```typescript
navigationStore.navigateTo(componentId);
workspaceStore.setInspectorOpen(true);
```

### Components Modified

1. **ComponentTable.svelte** - Click row navigates to component, highlights selected
2. **PipingTable.svelte** - Click row navigates to source component, highlights selected
3. **PumpResultsCard.svelte** - Click card navigates to pump, highlights with accent border
4. **ElevationProfile.svelte** - Click SVG markers or data table rows navigates to component

### Design Decisions

- Navigate to source component for piping rows (the component whose downstream piping is shown)
- Only component-type elements are clickable in elevation profile (connections don't map to a single component)
- Selected row/card highlighted with accent color
- Inspector auto-opens if closed when a results item is clicked
- Both results viewer (left overlay) and inspector (right sidebar) visible simultaneously

## Files Changed

- `apps/web/src/lib/components/results/ComponentTable.svelte`
- `apps/web/src/lib/components/results/PipingTable.svelte`
- `apps/web/src/lib/components/results/PumpResultsCard.svelte`
- `apps/web/src/lib/components/results/ElevationProfile.svelte`
