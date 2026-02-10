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
	PipingSegment,
	PipeConnection
} from '$lib/models';
import {
	createNewProject,
	touchProject,
	generateComponentId,
	generateConnectionId,
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
		 * Automatically creates downstream connections for linear workflows.
		 */
		addComponent(type: ComponentType, atIndex?: number): string {
			const id = generateComponentId();
			const component = createDefaultComponent(type, id);

			updateWithHistory(`Add ${type}`, (project) => {
				const newComponents = [...project.components];
				const insertAt =
					atIndex !== undefined && atIndex >= 0 && atIndex <= newComponents.length
						? atIndex
						: newComponents.length;

				// Get the component before and after the insertion point
				const prevComponent = insertAt > 0 ? newComponents[insertAt - 1] : null;
				const nextComponent = insertAt < newComponents.length ? newComponents[insertAt] : null;

				// Insert the new component
				newComponents.splice(insertAt, 0, component);

				// Auto-create connections for linear workflow
				// 1. Previous component should connect to new component
				if (prevComponent) {
					// Check if prev was connected to next, and update that connection
					const existingConnIdx = prevComponent.downstream_connections.findIndex(
						(c) => c.target_component_id === nextComponent?.id
					);

					if (existingConnIdx >= 0) {
						// Prev was connected to next - redirect prev to new component
						// and connect new component to next (preserving piping)
						const existingConn = prevComponent.downstream_connections[existingConnIdx];
						prevComponent.downstream_connections[existingConnIdx] = {
							target_component_id: id
						};
						// New component connects to next with the existing piping
						component.downstream_connections = [
							{
								target_component_id: nextComponent!.id,
								piping: existingConn.piping
							}
						];
					} else {
						// No existing connection - create new one from prev to new
						prevComponent.downstream_connections.push({
							target_component_id: id
						});
						// If there's a next component, connect new to next
						if (nextComponent) {
							component.downstream_connections = [
								{
									target_component_id: nextComponent.id
								}
							];
						}
					}
				} else if (nextComponent) {
					// No prev component but there is a next - connect new to next
					component.downstream_connections = [
						{
							target_component_id: nextComponent.id
						}
					];
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
		 * If the component has a parent_id, this edit breaks the parent link.
		 * If the component is a parent, propagate changes to linked children.
		 */
		updateComponent(componentId: string, updates: Partial<Component>) {
			updateWithHistory('Update component', (project) => {
				// Fields that should NOT propagate to children
				const nonPropagatingKeys = new Set(['id', 'name', 'parent_id', 'downstream_connections', 'upstream_piping', 'ports']);

				// Build propagatable updates (type-specific fields only)
				const propagatable: Record<string, unknown> = {};
				for (const [key, value] of Object.entries(updates)) {
					if (!nonPropagatingKeys.has(key)) {
						propagatable[key] = value;
					}
				}

				return {
					...project,
					components: project.components.map((c) => {
						if (c.id === componentId) {
							// Update the target component; break parent link if it's a child
							const updated = { ...c, ...updates } as Component;
							if (c.parent_id) {
								updated.parent_id = undefined;
							}
							return updated;
						}
						// Propagate to linked children
						if (c.parent_id === componentId && Object.keys(propagatable).length > 0) {
							return { ...c, ...propagatable } as Component;
						}
						return c;
					})
				};
			});
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
		 * Copy a component in series (insert after original in the chain).
		 * The copy maintains a parent_id link to the original until edited.
		 */
		copyComponentInSeries(componentId: string): string | null {
			const project = get(store);
			const original = project.components.find((c) => c.id === componentId);
			if (!original) return null;

			const id = generateComponentId();
			const copy = structuredClone(original) as Component;
			copy.id = id;
			copy.name = `${original.name} (Copy)`;
			copy.parent_id = original.id;
			copy.downstream_connections = [];

			const originalIndex = project.components.findIndex((c) => c.id === componentId);

			updateWithHistory('Copy component (series)', (proj) => {
				const newComponents = [...proj.components];
				const insertAt = originalIndex + 1;

				// Get the next component after original
				const nextComponent = insertAt < newComponents.length ? newComponents[insertAt] : null;

				// Insert copy after original
				newComponents.splice(insertAt, 0, copy);

				// Redirect original's downstream to copy, copy connects to next
				const origComp = newComponents[originalIndex];
				if (nextComponent) {
					const existingConnIdx = origComp.downstream_connections.findIndex(
						(c) => c.target_component_id === nextComponent.id
					);
					if (existingConnIdx >= 0) {
						const existingConn = origComp.downstream_connections[existingConnIdx];
						origComp.downstream_connections[existingConnIdx] = {
							target_component_id: id
						};
						copy.downstream_connections = [{
							target_component_id: nextComponent.id,
							piping: existingConn.piping
						}];
					} else {
						origComp.downstream_connections.push({ target_component_id: id });
						copy.downstream_connections = [{ target_component_id: nextComponent.id }];
					}
				} else {
					origComp.downstream_connections.push({ target_component_id: id });
				}

				return { ...proj, components: newComponents };
			});

			navigationStore.navigateTo(id);
			return id;
		},

		/**
		 * Copy a component in parallel (insert after original, no chain redirect).
		 * The copy maintains a parent_id link to the original until edited.
		 */
		copyComponentInParallel(componentId: string): string | null {
			const project = get(store);
			const original = project.components.find((c) => c.id === componentId);
			if (!original) return null;

			const id = generateComponentId();
			const copy = structuredClone(original) as Component;
			copy.id = id;
			copy.name = `${original.name} (Parallel)`;
			copy.parent_id = original.id;
			copy.downstream_connections = [];

			const originalIndex = project.components.findIndex((c) => c.id === componentId);

			updateWithHistory('Copy component (parallel)', (proj) => {
				const newComponents = [...proj.components];
				// Insert right after original (no connection rewiring)
				newComponents.splice(originalIndex + 1, 0, copy);
				return { ...proj, components: newComponents };
			});

			navigationStore.navigateTo(id);
			return id;
		},

		/**
		 * Break the parent-child link on a component (make it independent).
		 */
		breakParentLink(componentId: string) {
			updateWithHistory('Break parent link', (project) => ({
				...project,
				components: project.components.map((c) =>
					c.id === componentId ? { ...c, parent_id: undefined } : c
				)
			}));
		},

		/**
		 * Add a connection between components.
		 * If a connection already exists, it will not add a duplicate.
		 */
		addConnection(fromComponentId: string, toComponentId: string, piping?: PipingSegment) {
			updateWithHistory('Add connection', (project) => ({
				...project,
				components: project.components.map((c) => {
					if (c.id === fromComponentId) {
						// Check if connection already exists
						const existingConn = c.downstream_connections.find(
							(conn) => conn.target_component_id === toComponentId
						);
						if (existingConn) {
							// Connection already exists - don't add duplicate
							return c;
						}
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

		// ========================================================================
		// Port-Based Connection Management
		// ========================================================================

		/**
		 * Add a port-based connection between components.
		 */
		addPipeConnection(
			fromComponentId: string,
			fromPortId: string,
			toComponentId: string,
			toPortId: string,
			piping?: PipingSegment
		): string {
			const id = generateConnectionId();
			const connection: PipeConnection = {
				id,
				from_component_id: fromComponentId,
				from_port_id: fromPortId,
				to_component_id: toComponentId,
				to_port_id: toPortId,
				piping
			};

			updateWithHistory('Add connection', (project) => ({
				...project,
				connections: [...project.connections, connection]
			}));

			return id;
		},

		/**
		 * Remove a port-based connection by ID.
		 */
		removePipeConnection(connectionId: string) {
			updateWithHistory('Remove connection', (project) => ({
				...project,
				connections: project.connections.filter((c) => c.id !== connectionId)
			}));
		},

		/**
		 * Update a port-based connection's piping.
		 */
		updatePipeConnectionPiping(connectionId: string, piping: PipingSegment | undefined) {
			updateWithHistory('Update connection piping', (project) => ({
				...project,
				connections: project.connections.map((c) =>
					c.id === connectionId ? { ...c, piping } : c
				)
			}));
		},

		/**
		 * Get all connections for a component.
		 */
		getConnectionsForComponent(componentId: string): PipeConnection[] {
			const project = get(store);
			return project.connections.filter(
				(c) => c.from_component_id === componentId || c.to_component_id === componentId
			);
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

/** Derived store for port-based connections. */
export const connections: Readable<PipeConnection[]> = derived(
	projectStore,
	($project) => $project.connections
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
