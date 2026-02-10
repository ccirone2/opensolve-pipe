# Issue #165: Create workspaceStore for persistent layout state

## Plan

1. Create `apps/web/src/lib/stores/workspace.ts` with `WorkspaceState` interface
2. Implement localStorage persistence following the existing `themeStore` pattern
3. Add derived stores for common queries
4. Export from `apps/web/src/lib/stores/index.ts`
5. Migrate sidebar/inspector toggle logic from `p/[...encoded]/+page.svelte`
6. Write unit tests
