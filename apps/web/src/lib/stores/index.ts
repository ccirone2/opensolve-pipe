/**
 * OpenSolve Pipe Svelte Stores
 *
 * State management for the frontend application.
 */

// Project store
export {
	projectStore,
	components,
	pumpLibrary,
	fluid,
	settings,
	metadata,
	solvedState,
	isSolved,
	getComponent,
	getPumpCurve
} from './project';

// Navigation store
export {
	navigationStore,
	currentElementId,
	canGoBack,
	canGoForward,
	createBreadcrumbPath
} from './navigation';

// History store (undo/redo)
export { historyStore, canUndo, canRedo, undoCount, redoCount } from './history';
