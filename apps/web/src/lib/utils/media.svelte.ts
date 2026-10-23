/**
 * Media queries as reactive values (svelte/reactivity MediaQuery), with a fixed answer where the
 * browser has no matchMedia (server rendering, test DOMs).
 */
import { MediaQuery } from 'svelte/reactivity';

/** Wide screens show Build and Results side by side (Tailwind's lg breakpoint, as Workspace). */
export const WIDE_SCREEN = '(min-width: 1024px)';

export function mediaQuery(query: string, fallback = false): { readonly current: boolean } {
	if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
		return { current: fallback };
	}
	return new MediaQuery(query, fallback);
}
