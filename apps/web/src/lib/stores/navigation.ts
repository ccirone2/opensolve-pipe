/**
 * Navigation state management for the panel navigator.
 */

import { writable, derived } from 'svelte/store';
import type { Readable } from 'svelte/store';
import type { Component } from '$lib/models';

/** Navigation state. */
interface NavigationState {
	/** Currently selected component ID. */
	currentElementId: string | null;
	/** History of visited component IDs (for back navigation). */
	visitHistory: string[];
	/** Maximum index in visit history (for forward navigation). */
	visitHistoryIndex: number;
}

/** Create the navigation store. */
function createNavigationStore() {
	const { subscribe, set, update } = writable<NavigationState>({
		currentElementId: null,
		visitHistory: [],
		visitHistoryIndex: -1
	});

	return {
		subscribe,

		/**
		 * Navigate to a component.
		 */
		navigateTo(componentId: string) {
			update((state) => {
				// If already at this component, do nothing
				if (state.currentElementId === componentId) {
					return state;
				}

				// Truncate forward history if we're in the middle
				const newHistory = state.visitHistory.slice(0, state.visitHistoryIndex + 1);

				// Add new component to history
				newHistory.push(componentId);

				return {
					currentElementId: componentId,
					visitHistory: newHistory,
					visitHistoryIndex: newHistory.length - 1
				};
			});
		},

		/**
		 * Go back in navigation history.
		 */
		goBack(): string | null {
			let targetId: string | null = null;

			update((state) => {
				if (state.visitHistoryIndex <= 0) {
					return state;
				}

				const newIndex = state.visitHistoryIndex - 1;
				targetId = state.visitHistory[newIndex];

				return {
					...state,
					currentElementId: targetId,
					visitHistoryIndex: newIndex
				};
			});

			return targetId;
		},

		/**
		 * Go forward in navigation history.
		 */
		goForward(): string | null {
			let targetId: string | null = null;

			update((state) => {
				if (state.visitHistoryIndex >= state.visitHistory.length - 1) {
					return state;
				}

				const newIndex = state.visitHistoryIndex + 1;
				targetId = state.visitHistory[newIndex];

				return {
					...state,
					currentElementId: targetId,
					visitHistoryIndex: newIndex
				};
			});

			return targetId;
		},

		/**
		 * Clear navigation state.
		 */
		clear() {
			set({
				currentElementId: null,
				visitHistory: [],
				visitHistoryIndex: -1
			});
		},

		/**
		 * Remove a component from history (when deleted).
		 */
		removeFromHistory(componentId: string) {
			update((state) => {
				const newHistory = state.visitHistory.filter((id) => id !== componentId);
				let newIndex = state.visitHistoryIndex;
				let newCurrentId = state.currentElementId;

				// Adjust index if items were removed before current position
				const removedBefore = state.visitHistory
					.slice(0, state.visitHistoryIndex + 1)
					.filter((id) => id === componentId).length;
				newIndex = Math.max(-1, newIndex - removedBefore);

				// If current element was removed, select previous or null
				if (state.currentElementId === componentId) {
					newCurrentId = newIndex >= 0 ? newHistory[newIndex] : null;
				}

				return {
					currentElementId: newCurrentId,
					visitHistory: newHistory,
					visitHistoryIndex: Math.min(newIndex, newHistory.length - 1)
				};
			});
		}
	};
}

/** The navigation store instance. */
export const navigationStore = createNavigationStore();

/** Currently selected component ID. */
export const currentElementId: Readable<string | null> = derived(
	navigationStore,
	($nav) => $nav.currentElementId
);

/** Whether back navigation is available. */
export const canGoBack = derived(navigationStore, ($nav) => $nav.visitHistoryIndex > 0);

/** Whether forward navigation is available. */
export const canGoForward = derived(
	navigationStore,
	($nav) => $nav.visitHistoryIndex < $nav.visitHistory.length - 1
);

/**
 * Create a breadcrumb path store from components.
 * Returns the path from root to current element.
 */
export function createBreadcrumbPath(
	components: Readable<Component[]>,
	currentId: Readable<string | null>
): Readable<Component[]> {
	return derived([components, currentId], ([$components, $currentId]) => {
		if (!$currentId || $components.length === 0) {
			return [];
		}

		// Build a map of component ID to component
		const componentMap = new Map($components.map((c) => [c.id, c]));

		// Find current component
		const current = componentMap.get($currentId);
		if (!current) {
			return [];
		}

		// Build path from component chain
		// For now, return a simple path based on component index
		const currentIndex = $components.findIndex((c) => c.id === $currentId);
		if (currentIndex === -1) {
			return [current];
		}

		// Return components from start to current
		return $components.slice(0, currentIndex + 1);
	});
}
