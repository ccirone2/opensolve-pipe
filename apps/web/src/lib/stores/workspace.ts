/**
 * Workspace layout state store.
 *
 * Manages UI layout preferences (sidebar, inspector, zoom, focus mode)
 * independently from project data. Persisted to localStorage.
 */

import { writable, derived } from 'svelte/store';
import { browser } from '$app/environment';

/** Sidebar tab options. */
export type SidebarTab = 'tree' | 'config' | 'results';

/** Inspector tab options. */
export type InspectorTab = 'properties' | 'piping' | 'results';

/** Workspace layout state. */
export interface WorkspaceState {
	sidebarOpen: boolean;
	sidebarTab: SidebarTab;
	inspectorOpen: boolean;
	inspectorTab: InspectorTab;
	focusMode: boolean;
	canvasZoom: number;
	lastSelectedComponentId: string | null;
}

/** Default workspace state. */
const DEFAULT_STATE: WorkspaceState = {
	sidebarOpen: true,
	sidebarTab: 'tree',
	inspectorOpen: true,
	inspectorTab: 'properties',
	focusMode: false,
	canvasZoom: 1,
	lastSelectedComponentId: null
};

/** Storage key for workspace preferences. */
const STORAGE_KEY = 'opensolve-pipe-workspace';

/**
 * Load workspace state from localStorage, merging with defaults.
 */
function loadState(): WorkspaceState {
	if (!browser) return { ...DEFAULT_STATE };

	try {
		const stored = localStorage.getItem(STORAGE_KEY);
		if (stored) {
			const parsed = JSON.parse(stored);
			return { ...DEFAULT_STATE, ...parsed };
		}
	} catch {
		// Invalid JSON — use defaults
	}

	return { ...DEFAULT_STATE };
}

/**
 * Save workspace state to localStorage.
 */
function saveState(state: WorkspaceState): void {
	if (!browser) return;

	try {
		localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
	} catch {
		// localStorage full or unavailable
	}
}

/**
 * Create the workspace store.
 */
function createWorkspaceStore() {
	const store = writable<WorkspaceState>(loadState());

	// Auto-persist on changes
	store.subscribe((state) => {
		saveState(state);
	});

	function update(updater: (state: WorkspaceState) => WorkspaceState) {
		store.update(updater);
	}

	return {
		subscribe: store.subscribe,

		/** Toggle the sidebar open/closed. */
		toggleSidebar() {
			update((s) => ({ ...s, sidebarOpen: !s.sidebarOpen }));
		},

		/** Set sidebar open state directly. */
		setSidebarOpen(open: boolean) {
			update((s) => ({ ...s, sidebarOpen: open }));
		},

		/** Switch the active sidebar tab. */
		setSidebarTab(tab: SidebarTab) {
			update((s) => ({ ...s, sidebarTab: tab }));
		},

		/** Toggle the inspector open/closed. */
		toggleInspector() {
			update((s) => ({ ...s, inspectorOpen: !s.inspectorOpen }));
		},

		/** Set inspector open state directly. */
		setInspectorOpen(open: boolean) {
			update((s) => ({ ...s, inspectorOpen: open }));
		},

		/** Switch the active inspector tab. */
		setInspectorTab(tab: InspectorTab) {
			update((s) => ({ ...s, inspectorTab: tab }));
		},

		/** Toggle focus mode on/off. */
		toggleFocusMode() {
			update((s) => ({ ...s, focusMode: !s.focusMode }));
		},

		/** Set focus mode directly. */
		setFocusMode(enabled: boolean) {
			update((s) => ({ ...s, focusMode: enabled }));
		},

		/** Set the canvas zoom level. */
		setCanvasZoom(zoom: number) {
			update((s) => ({ ...s, canvasZoom: Math.max(0.1, Math.min(5, zoom)) }));
		},

		/** Track the last selected component. */
		setLastSelectedComponent(id: string | null) {
			update((s) => ({ ...s, lastSelectedComponentId: id }));
		},

		/** Reset all layout state to defaults. */
		reset() {
			store.set({ ...DEFAULT_STATE });
		}
	};
}

/** The workspace store instance. */
export const workspaceStore = createWorkspaceStore();

/** Whether the sidebar is open. */
export const isSidebarOpen = derived(workspaceStore, ($ws) => $ws.sidebarOpen);

/** Whether the inspector is open. */
export const isInspectorOpen = derived(workspaceStore, ($ws) => $ws.inspectorOpen);

/** The active sidebar tab. */
export const activeSidebarTab = derived(workspaceStore, ($ws) => $ws.sidebarTab);

/** The active inspector tab. */
export const activeInspectorTab = derived(workspaceStore, ($ws) => $ws.inspectorTab);

/** Whether focus mode is active. */
export const isFocusMode = derived(workspaceStore, ($ws) => $ws.focusMode);

/** The current canvas zoom level. */
export const canvasZoom = derived(workspaceStore, ($ws) => $ws.canvasZoom);
