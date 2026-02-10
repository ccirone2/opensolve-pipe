# Issue #194: Add Shortcuts Menu to Navigation Panel Footer

## Overview

Add a persistent footer strip at the bottom of the sidebar panel with quick-action icon buttons for common operations. Each button shows its keyboard shortcut on hover.

## Component Structure

### SidebarFooter.svelte

Location: `apps/web/src/lib/components/workspace/SidebarFooter.svelte`

**Props Interface:**

```typescript
interface Props {
  onOpenCommandPalette?: () => void;
  onSolve?: () => void;
  onUndo?: () => void;
  onRedo?: () => void;
}
```

**Actions:**
| Action | Icon | Shortcut | Description |
|--------|------|----------|-------------|
| Add Component | Plus (+) | Ctrl+K | Opens command palette |
| Solve | Signal/waves | Ctrl+Enter | Triggers network solve |
| Undo | Arrow left | Ctrl+Z | Undo last action |
| Redo | Arrow right | Ctrl+Shift+Z | Redo last undone action |

## Design Details

- Horizontal strip of icon buttons pinned to sidebar bottom
- Uses existing CSS variables for colors and spacing
- Buttons use `canUndo` / `canRedo` stores to disable when unavailable
- Tooltip on hover shows action name + keyboard shortcut
- Proper ARIA roles: `role="toolbar"`, `aria-label="Quick actions"`
- Divider line at top to separate from sidebar content

## Styling

- Border-top separator
- Compact height (~36px)
- Icon buttons: 28x28px with hover state
- Consistent with existing button styles in WorkspaceToolbar

## Integration

- Import and add to SidebarTabs.svelte below the tab content area
- Pass callbacks from SidebarTabs props (already has onOpenCommandPalette, onSolve)
- Add onUndo/onRedo props to SidebarTabs, wire from parent page

## Mobile Considerations

- The sidebar footer is only visible on desktop (sidebar is hidden on mobile)
- Mobile users have the MobileNavBar for similar quick actions
- No changes needed to MobileNavBar

## Files Modified

1. **New:** `apps/web/src/lib/components/workspace/SidebarFooter.svelte`
2. **Modified:** `apps/web/src/lib/components/workspace/SidebarTabs.svelte` - integrate footer
3. **Modified:** `apps/web/src/lib/components/workspace/index.ts` - add barrel export
4. **Modified:** `apps/web/src/routes/p/[encoded]/+page.svelte` - pass undo/redo callbacks
