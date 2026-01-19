/**
 * Undo/redo history management for project state.
 */

import { writable, derived, get } from 'svelte/store';
import type { Project } from '$lib/models';

/** Maximum number of undo states to keep. */
const MAX_HISTORY_SIZE = 50;

/** History entry with timestamp. */
interface HistoryEntry {
	state: Project;
	timestamp: number;
	description: string;
}

/** Internal history state. */
interface HistoryState {
	past: HistoryEntry[];
	present: Project | null;
	future: HistoryEntry[];
}

/** Create the history store. */
function createHistoryStore() {
	const { subscribe, set, update } = writable<HistoryState>({
		past: [],
		present: null,
		future: []
	});

	return {
		subscribe,

		/**
		 * Initialize history with a project.
		 * Clears all history.
		 */
		initialize(project: Project) {
			set({
				past: [],
				present: structuredClone(project),
				future: []
			});
		},

		/**
		 * Push a new state to history.
		 * Clears any redo states.
		 */
		push(project: Project, description: string = 'Edit') {
			update((history) => {
				if (!history.present) {
					return {
						past: [],
						present: structuredClone(project),
						future: []
					};
				}

				// Add current present to past
				const newPast = [
					...history.past,
					{
						state: history.present,
						timestamp: Date.now(),
						description
					}
				];

				// Trim if exceeds max size
				if (newPast.length > MAX_HISTORY_SIZE) {
					newPast.shift();
				}

				return {
					past: newPast,
					present: structuredClone(project),
					future: [] // Clear redo stack
				};
			});
		},

		/**
		 * Undo the last action.
		 * Returns the restored state or null if nothing to undo.
		 */
		undo(): Project | null {
			let restoredState: Project | null = null;

			update((history) => {
				if (history.past.length === 0 || !history.present) {
					return history;
				}

				const previous = history.past[history.past.length - 1];
				const newPast = history.past.slice(0, -1);

				restoredState = structuredClone(previous.state);

				return {
					past: newPast,
					present: previous.state,
					future: [
						{
							state: history.present,
							timestamp: Date.now(),
							description: 'Undo'
						},
						...history.future
					]
				};
			});

			return restoredState;
		},

		/**
		 * Redo the last undone action.
		 * Returns the restored state or null if nothing to redo.
		 */
		redo(): Project | null {
			let restoredState: Project | null = null;

			update((history) => {
				if (history.future.length === 0 || !history.present) {
					return history;
				}

				const next = history.future[0];
				const newFuture = history.future.slice(1);

				restoredState = structuredClone(next.state);

				return {
					past: [
						...history.past,
						{
							state: history.present,
							timestamp: Date.now(),
							description: 'Redo'
						}
					],
					present: next.state,
					future: newFuture
				};
			});

			return restoredState;
		},

		/**
		 * Clear all history.
		 */
		clear() {
			update((history) => ({
				past: [],
				present: history.present,
				future: []
			}));
		},

		/**
		 * Get current state snapshot.
		 */
		getPresent(): Project | null {
			return get({ subscribe }).present;
		}
	};
}

/** The history store instance. */
export const historyStore = createHistoryStore();

/** Whether undo is available. */
export const canUndo = derived(historyStore, ($history) => $history.past.length > 0);

/** Whether redo is available. */
export const canRedo = derived(historyStore, ($history) => $history.future.length > 0);

/** Number of undo steps available. */
export const undoCount = derived(historyStore, ($history) => $history.past.length);

/** Number of redo steps available. */
export const redoCount = derived(historyStore, ($history) => $history.future.length);
