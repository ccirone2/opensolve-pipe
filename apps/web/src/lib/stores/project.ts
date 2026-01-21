/**
 * Project state management with Svelte stores.
 */

import { writable, derived, get } from 'svelte/store';
import type { Readable, Writable } from 'svelte/store';
import type {
	Project,
	Component,
	ComponentType,
	PumpCurve,
	SolvedState,
	Connection,
	PipingSegment
} from '$lib/models';
import {
	createNewProject,
	touchProject,
	generateComponentId,
	createDefaultComponent
} from '$lib/models';
import { historyStore } from './history';
import { navigationStore } from './navigation';

/** Storage key for local persistence. */
const STORAGE_KEY = 'opensolve-pipe-project';

/** Create the main project store. */
function createProjectStore() {
	const store: Writable<Project> = writable(createNewProject());

	// Initialize history with the new project
	historyStore.initialize(get(store));

	/**
	 * Update project, save to history, and mark as modified.
	 */
	function updateWithHistory(
		description: string,
		updater: (project: Project) => Project
	) {
		store.update((project) => {
			const updated = touchProject(updater(project));
			// Push the updated state to history (saves current present as undo point)
			historyStore.push(updated, description);
			return updated;
		});
	}

	/**
	 * Update project without saving to history (for results, etc.).
	 */
	function updateProject(updater: (project: Project) => Project) {
		store.update((project) => touchProject(updater(project)));
	}

	return {
		subscribe: store.subscribe,

		/**
		 * Load a project into the store.
		 */
		load(project: Project) {
			store.set(structuredClone(project));
			historyStore.initialize(project);
			navigationStore.clear();
		},

		/**
		 * Create a new empty project.
		 */
		createNew() {
			const newProject = createNewProject();
			store.set(newProject);
			historyStore.initialize(newProject);
			navigationStore.clear();
		},

		/**
		 * Update project metadata.
		 */
		updateMetadata(updates: Partial<Project['metadata']>) {
			updateWithHistory('Update metadata', (project) => ({
				...project,
				metadata: { ...project.metadata, ...updates }
			}));
		},

		/**
		 * Update project settings.
		 */
		updateSettings(updates: Partial<Project['settings']>) {
			updateWithHistory('Update settings', (project) => ({
				...project,
				settings: { ...project.settings, ...updates }
			}));
		},

		/**
		 * Update fluid definition.
		 */
		updateFluid(updates: Partial<Project['fluid']>) {
			updateWithHistory('Update fluid', (project) => ({
				...project,
				fluid: { ...project.fluid, ...updates }
			}));
		},

		/**
		 * Add a new component.
		 */
		addComponent(type: ComponentType, atIndex?: number): string {
			const id = generateComponentId();
			const component = createDefaultComponent(type, id);

			updateWithHistory(`Add ${type}`, (project) => {
				const newComponents = [...project.components];
				if (atIndex !== undefined && atIndex >= 0 && atIndex <= newComponents.length) {
					newComponents.splice(atIndex, 0, component);
				} else {
					newComponents.push(component);
				}
				return { ...project, components: newComponents };
			});

			// Navigate to new component
			navigationStore.navigateTo(id);

			return id;
		},

		/**
		 * Remove a component by ID.
		 */
		removeComponent(componentId: string) {
			updateWithHistory('Remove component', (project) => {
				// Remove component
				const newComponents = project.components.filter((c) => c.id !== componentId);

				// Remove references to deleted component from connections
				const cleanedComponents = newComponents.map((c) => ({
					...c,
					downstream_connections: c.downstream_connections.filter(
						(conn) => conn.target_component_id !== componentId
					)
				}));

				return { ...project, components: cleanedComponents };
			});

			// Update navigation
			navigationStore.removeFromHistory(componentId);
		},

		/**
		 * Update a component's properties.
		 */
		updateComponent(componentId: string, updates: Partial<Component>) {
			updateWithHistory('Update component', (project) => ({
				...project,
				components: project.components.map((c) =>
					c.id === componentId ? ({ ...c, ...updates } as Component) : c
				)
			}));
		},

		/**
		 * Move a component to a new index.
		 */
		moveComponent(componentId: string, toIndex: number) {
			updateWithHistory('Move component', (project) => {
				const fromIndex = project.components.findIndex((c) => c.id === componentId);
				if (fromIndex === -1 || fromIndex === toIndex) {
					return project;
				}

				const newComponents = [...project.components];
				const [removed] = newComponents.splice(fromIndex, 1);
				newComponents.splice(toIndex, 0, removed);

				return { ...project, components: newComponents };
			});
		},

		/**
		 * Add a connection between components.
		 */
		addConnection(fromComponentId: string, toComponentId: string, piping?: PipingSegment) {
			updateWithHistory('Add connection', (project) => ({
				...project,
				components: project.components.map((c) => {
					if (c.id === fromComponentId) {
						const newConnection: Connection = {
							target_component_id: toComponentId,
							piping
						};
						return {
							...c,
							downstream_connections: [...c.downstream_connections, newConnection]
						};
					}
					return c;
				})
			}));
		},

		/**
		 * Remove a connection between components.
		 */
		removeConnection(fromComponentId: string, toComponentId: string) {
			updateWithHistory('Remove connection', (project) => ({
				...project,
				components: project.components.map((c) => {
					if (c.id === fromComponentId) {
						return {
							...c,
							downstream_connections: c.downstream_connections.filter(
								(conn) => conn.target_component_id !== toComponentId
							)
						};
					}
					return c;
				})
			}));
		},

		/**
		 * Update upstream piping for a component.
		 */
		updateUpstreamPiping(componentId: string, piping: PipingSegment | undefined) {
			updateWithHistory('Update piping', (project) => ({
				...project,
				components: project.components.map((c) =>
					c.id === componentId ? { ...c, upstream_piping: piping } : c
				)
			}));
		},

		/**
		 * Update downstream connection piping for a component.
		 * Updates the piping for the first downstream connection.
		 */
		updateDownstreamPiping(
			componentId: string,
			targetComponentId: string,
			piping: PipingSegment | undefined
		) {
			updateWithHistory('Update downstream piping', (project) => ({
				...project,
				components: project.components.map((c) => {
					if (c.id === componentId) {
						return {
							...c,
							downstream_connections: c.downstream_connections.map((conn) =>
								conn.target_component_id === targetComponentId
									? { ...conn, piping }
									: conn
							)
						};
					}
					return c;
				})
			}));
		},

		/**
		 * Add a pump curve to the library.
		 */
		addPumpCurve(curve: PumpCurve) {
			updateWithHistory('Add pump curve', (project) => ({
				...project,
				pump_library: [...project.pump_library, curve]
			}));
		},

		/**
		 * Remove a pump curve from the library.
		 */
		removePumpCurve(curveId: string) {
			updateWithHistory('Remove pump curve', (project) => ({
				...project,
				pump_library: project.pump_library.filter((c) => c.id !== curveId)
			}));
		},

		/**
		 * Update a pump curve.
		 */
		updatePumpCurve(curveId: string, updates: Partial<PumpCurve>) {
			updateWithHistory('Update pump curve', (project) => ({
				...project,
				pump_library: project.pump_library.map((c) =>
					c.id === curveId ? { ...c, ...updates } : c
				)
			}));
		},

		/**
		 * Set solved state (results).
		 */
		setResults(results: SolvedState | undefined) {
			// Don't save results changes to history
			updateProject((project) => ({
				...project,
				results
			}));
		},

		/**
		 * Clear solved state.
		 */
		clearResults() {
			updateProject((project) => ({
				...project,
				results: undefined
			}));
		},

		/**
		 * Undo the last action.
		 */
		undo(): boolean {
			const restored = historyStore.undo();
			if (restored) {
				store.set(restored);
				return true;
			}
			return false;
		},

		/**
		 * Redo the last undone action.
		 */
		redo(): boolean {
			const restored = historyStore.redo();
			if (restored) {
				store.set(restored);
				return true;
			}
			return false;
		},

		/**
		 * Save project to local storage.
		 */
		saveToLocalStorage() {
			try {
				const project = get(store);
				localStorage.setItem(STORAGE_KEY, JSON.stringify(project));
				return true;
			} catch {
				return false;
			}
		},

		/**
		 * Load project from local storage.
		 */
		loadFromLocalStorage(): boolean {
			try {
				const stored = localStorage.getItem(STORAGE_KEY);
				if (stored) {
					const project = JSON.parse(stored) as Project;
					this.load(project);
					return true;
				}
				return false;
			} catch {
				return false;
			}
		},

		/**
		 * Clear local storage.
		 */
		clearLocalStorage() {
			localStorage.removeItem(STORAGE_KEY);
		}
	};
}

/** The main project store instance. */
export const projectStore = createProjectStore();

/** Derived store for project components. */
export const components: Readable<Component[]> = derived(
	projectStore,
	($project) => $project.components
);

/** Derived store for pump library. */
export const pumpLibrary: Readable<PumpCurve[]> = derived(
	projectStore,
	($project) => $project.pump_library
);

/** Derived store for fluid definition. */
export const fluid = derived(projectStore, ($project) => $project.fluid);

/** Derived store for project settings. */
export const settings = derived(projectStore, ($project) => $project.settings);

/** Derived store for project metadata. */
export const metadata = derived(projectStore, ($project) => $project.metadata);

/** Derived store for solved state. */
export const solvedState: Readable<SolvedState | undefined> = derived(
	projectStore,
	($project) => $project.results
);

/** Whether the project has been solved. */
export const isSolved: Readable<boolean> = derived(
	projectStore,
	($project) => $project.results?.converged === true
);

/** Get a component by ID from the current project. */
export function getComponent(componentId: string): Component | undefined {
	const project = get(projectStore);
	return project.components.find((c) => c.id === componentId);
}

/** Get a pump curve by ID from the current project. */
export function getPumpCurve(curveId: string): PumpCurve | undefined {
	const project = get(projectStore);
	return project.pump_library.find((c) => c.id === curveId);
}
