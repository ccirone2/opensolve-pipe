# Issue #193: Fix 'New Project' Button Loading Screen

## Root Cause Analysis

The `/p/+page.svelte` route uses `onMount` + `goto()` for a client-side redirect:

```svelte
onMount(() => {
  const project = get(projectStore);
  const result = encodeProject(project);
  goto(`/p/${result.encoded}`, { replaceState: true });
});
```

This fails in Vite preview/production builds because SvelteKit's hydration
completes but the `onMount` callback never fires reliably. The user sees
a spinner indefinitely at `/p/`.

## Chosen Approach: Client-Side URL Generation + Universal Load Redirect

Two complementary fixes:

1. **`+page.ts` universal load function**: A SvelteKit load function at `/p/`
   creates a new project, encodes it, and issues a `redirect(307)`. This runs
   in both SSR and CSR contexts, ensuring the redirect always works.

2. **Landing page onclick handler**: The "New Project" link generates the
   encoded URL client-side via `handleNewProject()` before navigation,
   bypassing the `/p/` redirect page entirely for the primary flow.

## Files Modified

1. `apps/web/src/routes/+page.svelte` - Added onclick handler for "New Project"
2. `apps/web/src/routes/p/+page.svelte` - Removed broken onMount redirect
3. `apps/web/src/routes/p/+page.ts` - New universal load function (redirect)
4. `apps/web/e2e/homepage.test.ts` - Updated to verify workspace loads
5. `apps/web/e2e/url-encoding.test.ts` - Updated redirect behavior test

## Test Plan

- `pnpm svelte-check` passes (0 errors)
- `pnpm build` succeeds
- E2E test "navigates to new project page" verifies workspace loads within 5s
- E2E test "new project redirects /p/ to encoded workspace URL" verifies fallback
