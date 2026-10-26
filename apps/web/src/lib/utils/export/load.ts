/**
 * The export dialog's chunk (proposal export.md §5.2, decision 3). Export is occasional, so the
 * dialog, the file model and the writers are a lazily loaded chunk rather than part of every
 * `/p` visit. One memoized import(): started at idle when the Export button first renders (so the
 * chunk usually arrives while the deployment is the page's own), and awaited on the click. A
 * failed import is forgotten, so a later call imports again, but a browser may keep the failed
 * module for the page's life (Chromium does: it fetches that URL no more), so a click after a
 * failed preload can fail without a request. The caller then says so in STALE_CHUNK_MESSAGE's
 * words, which name both causes: a tab opened before a redeploy asks for files the new
 * deployment no longer has, or the connection dropped. Either way a reload loads it again. This
 * module is static and small: ResultsPanel imports it, never the chunk.
 */
import type { Component } from 'svelte';

/** The dialog's choices, kept for the page session by ResultsPanel (never stored). */
export interface ExportChoices {
	/** Excel workbook (default) or CSV files in one zip. */
	format: 'xlsx' | 'csv';
	/** The project's display units (default) or SI base units. */
	units: 'display' | 'si';
	/** Include the project link (default on). */
	link: boolean;
}

export const DEFAULT_EXPORT_CHOICES: Readonly<ExportChoices> = Object.freeze({
	format: 'xlsx',
	units: 'display',
	link: true
});

/**
 * Why a lazily loaded part of the app (the export dialog, the pump chart) could not open: its
 * file is from an older deployment, or the connection dropped while it loaded. A reload fixes
 * both; the browser keeps a failed module, so trying again in the page does not.
 */
export const STALE_CHUNK_MESSAGE =
	'This part of the app could not be loaded: the app may have been updated since this page opened, or the connection dropped. Reload the page (the project is in its link), then solve again.';

/** Run `task` when the browser is idle (requestIdleCallback where it exists, else soon). */
function whenIdle(task: () => void): void {
	if (typeof requestIdleCallback === 'function') requestIdleCallback(task, { timeout: 5000 });
	else setTimeout(task, 200);
}

/**
 * A memoized loader of a lazily imported module: `load()` imports it once (a failure is
 * forgotten, so the next call calls the importer again, though the browser may answer from the
 * failed module it keeps); `preload()` starts that import once, at idle, and ignores its failure.
 */
export function createLoader<T>(importer: () => Promise<T>): {
	load: () => Promise<T>;
	preload: () => void;
} {
	let pending: Promise<T> | null = null;
	let preloaded = false;
	const load = (): Promise<T> =>
		(pending ??= importer().catch((error: unknown) => {
			pending = null;
			throw error;
		}));
	const preload = () => {
		if (preloaded) return;
		preloaded = true;
		whenIdle(() => void load().catch(() => {}));
	};
	return { load, preload };
}

/** Props of the export dialog (components/results/ExportDialog.svelte). */
export interface ExportDialogProps {
	/** The session's choices, and where a change goes. */
	choices: ExportChoices;
	onchoices: (choices: ExportChoices) => void;
	/** The Cases choice when the dialog opens: the case shown, or All cases (Compare cases tab). */
	initialCases: 'shown' | 'all';
	onclose: () => void;
}

const exportDialog = createLoader(
	(): Promise<{ default: Component<ExportDialogProps> }> =>
		import('../../components/results/ExportDialog.svelte')
);

/** The export dialog's component, loading its chunk once. */
export const loadExportDialog = exportDialog.load;

/** Start loading the export dialog's chunk at idle, once per page. */
export const preloadExportDialog = exportDialog.preload;
