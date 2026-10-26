/**
 * The split between Build and Results on wide screens (proposal ui-ux-refinement.md item 10): the
 * Results pane's share of the workspace width, chosen with the splitter between them, or null for
 * the default layout (Build 3 : Results 2, Build at most 52 rem). The choice is a per-browser
 * convenience kept in localStorage, never project data: it is not in the link.
 */

/** localStorage key of the chosen share. */
export const SPLIT_STORAGE_KEY = 'opensolve-pipe:results-share';

/** Neither pane narrower than this (22 rem): Build's two-column forms and a results table. */
export const MIN_PANE_PX = 352;

/** Neither pane's share beyond this, whatever the width. */
const MIN_SHARE = 0.25;
const MAX_SHARE = 0.75;

/** One arrow-key step of the splitter. */
export const SPLIT_STEP = 0.05;

/** Build's widest in the default layout (52 rem), as Workspace's `lg:max-w-[52rem]`. */
const DEFAULT_BUILD_MAX_PX = 832;

/** The Results share the default layout gives at a workspace width: Build 3/5, at most 52 rem. */
export function defaultShare(width: number): number {
	if (!(width > 0)) return 0.4;
	return 1 - Math.min(0.6 * width, DEFAULT_BUILD_MAX_PX) / width;
}

/**
 * The Results share kept within bounds at a workspace `width` (px): both panes stay usable. An
 * unknown width (0, before layout) applies only the share bounds.
 */
export function clampShare(share: number, width: number): number {
	const pane = width > 0 ? MIN_PANE_PX / width : 0;
	const min = Math.max(MIN_SHARE, pane);
	const max = Math.min(MAX_SHARE, 1 - pane);
	if (!(min <= max)) return 0.5;
	return Math.min(max, Math.max(min, share));
}

/** The bounds of the Results share at a workspace width, as clampShare applies them. */
export function shareBounds(width: number): { min: number; max: number } {
	return { min: clampShare(0, width), max: clampShare(1, width) };
}

/** Storage, or null where the browser refuses it (private modes, blocked site data). */
function storage(): Storage | null {
	try {
		return typeof localStorage === 'undefined' ? null : localStorage;
	} catch {
		return null;
	}
}

/** The share chosen before in this browser, or null for the default layout. */
export function loadShare(): number | null {
	try {
		const text = storage()?.getItem(SPLIT_STORAGE_KEY);
		if (text === null || text === undefined) return null;
		const share = Number(text);
		return Number.isFinite(share) && share > 0 && share < 1 ? share : null;
	} catch {
		return null;
	}
}

/** Remember the share (null: back to the default layout); silently does nothing if refused. */
export function saveShare(share: number | null): void {
	try {
		const store = storage();
		if (!store) return;
		if (share === null) store.removeItem(SPLIT_STORAGE_KEY);
		else store.setItem(SPLIT_STORAGE_KEY, String(Math.round(share * 1000) / 1000));
	} catch {
		// A refused write only loses the convenience.
	}
}
