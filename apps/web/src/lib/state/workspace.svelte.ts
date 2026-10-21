/**
 * The workspace of an open project: the project store, the API library, the navigator, and
 * the graph-edit actions the panels offer (add after / before, add branch, delete, plug,
 * connect). Each action is one undo step and moves the navigator to where the change is.
 */
import { getContext, setContext, untrack } from 'svelte';
import type { Component, Flag, PipeConnection, Project, UnitPreferences } from '../api/types';
import { flagText } from '../utils/flag-text';
import { fittingFallbackName } from '../utils/labels';
import {
	addBranch,
	addComponentAtPort,
	connectPorts,
	deleteComponent,
	disconnect,
	insertComponentInConnection,
	plugPort,
	updateComponent,
	updateConnection
} from '../utils/edit';
import { createComponent, type ComponentKind } from '../utils/factory';
import type { ElementRef } from '../utils/results';
import {
	componentById,
	connectionAtPort,
	connectionsOf,
	portById,
	type PortRef
} from '../utils/graph';
import type { ProjectStore } from './project.svelte';
import { LibraryStore } from './library.svelte';
import { NavigatorStore, pathAfterInsert } from './navigator.svelte';

export type Pane = 'build' | 'results';

export interface Notice {
	kind: 'error' | 'info';
	text: string;
	/** Increments with every notice, so the same text shown twice is announced twice. */
	id: number;
}

/** Kinds that can be inserted into a connection (separate inlet and outlet ports). */
export const INLINE_KINDS: readonly ComponentKind[] = [
	'pump',
	'gate',
	'ball',
	'butterfly',
	'globe',
	'check',
	'stop_check',
	'prv',
	'psv',
	'fcv',
	'tee',
	'wye'
];

export class Workspace {
	readonly store: ProjectStore;
	readonly library: LibraryStore;
	readonly nav: NavigatorStore;
	/** Pane shown on narrow screens (both are shown side by side on wide ones). */
	pane = $state<Pane>('build');
	notice = $state.raw<Notice | null>(null);
	/** The element whose results and trace are open in the results pane (null: none). */
	inspected = $state.raw<ElementRef | null>(null);
	#noticeId = 0;

	/** Changes only when the display units change (not on every edit). */
	#unitsKey: string;
	/** Changes only when a name, a kind, the ports or a connection's ends change. */
	#labelsKey: string;

	/**
	 * The display units, as an object that stays the same across edits that keep them, so
	 * results derived from it are not rebuilt on every edit.
	 */
	displayUnits: UnitPreferences;

	/**
	 * The project for labelling results (names, kinds, port order, connection ends): updated
	 * only when one of those changes, so editing a value does not rebuild the result tables.
	 * Never use it for values.
	 */
	labelsProject: Project;

	constructor(store: ProjectStore, library: LibraryStore = new LibraryStore()) {
		this.store = store;
		this.library = library;
		this.nav = new NavigatorStore(store);
		this.#unitsKey = $derived(JSON.stringify(this.store.project.settings.units));
		this.#labelsKey = $derived(labelsKey(this.store.project));
		this.displayUnits = $derived.by(() => {
			void this.#unitsKey;
			return untrack(() => this.store.project.settings.units);
		});
		this.labelsProject = $derived.by(() => {
			void this.#labelsKey;
			return untrack(() => this.store.project);
		});
	}

	get project(): Project {
		return this.store.project;
	}

	get units(): UnitPreferences {
		return this.store.project.settings.units;
	}

	/** A flag's text for display: names and display units (utils/flag-text.ts). */
	flagText(flag: Flag): string {
		const solved = this.store.solved;
		const valveTypes = solved
			? Object.fromEntries(Object.entries(solved.valveResults).map(([id, v]) => [id, v.valveType]))
			: undefined;
		return flagText(flag, {
			project: this.labelsProject,
			prefs: this.displayUnits,
			fittingName: (type) => this.library.fitting(type)?.name ?? fittingFallbackName(type),
			...(valveTypes ? { valveTypes } : {})
		});
	}

	notify(kind: Notice['kind'], text: string): void {
		this.notice = { kind, text, id: ++this.#noticeId };
	}

	dismissNotice(): void {
		this.notice = null;
	}

	/**
	 * Apply a change as one undo step. A refused change (it would make the project invalid)
	 * changes nothing and is reported as a notice. Returns true when the change was applied.
	 */
	edit(change: (draft: Project) => Project | void, label: string): boolean {
		const result = this.store.update(change, label);
		if (!result.ok) {
			this.notify(
				'error',
				`Could not ${label}: ${result.problems[0] ?? 'the change is not valid.'}`
			);
			return false;
		}
		return true;
	}

	/** Edit one component in place (its id and connected ports cannot change). */
	editComponent<T extends Component>(
		id: string,
		label: string,
		change: (component: T) => T | void
	): boolean {
		return this.edit(
			(p) => updateComponent(p, id, (c) => (change(c as T) ?? c) as Component),
			label
		);
	}

	/** Edit one connection in place (its id and ends cannot change). */
	editConnection(
		id: string,
		label: string,
		change: (connection: PipeConnection) => PipeConnection | void
	): boolean {
		return this.edit((p) => updateConnection(p, id, (c) => change(c) ?? c), label);
	}

	/** Add the first component of an empty project (or a separate one) and show it. */
	addStandalone(kind: ComponentKind): string | null {
		const component = createComponent(kind, this.project);
		const ok = this.edit(
			(p) => ({ ...p, components: [...p.components, component] }),
			`add ${component.name}`
		);
		if (!ok) return null;
		this.nav.restart(component.id);
		return component.id;
	}

	/**
	 * Add a component at a free port of `componentId`, connected with a default pipe sized to the
	 * port, and walk on to it. The new component starts at the same elevation.
	 */
	addAfter(componentId: string, portId: string, kind: ComponentKind): string | null {
		const existing = componentById(this.project, componentId);
		const port = existing ? portById(existing, portId) : undefined;
		if (!existing || !port) return null;
		const component = createComponent(kind, this.project, {
			elevation: port.elevation ?? existing.elevation,
			nominalSize: port.nominalSize
		});
		const ok = this.edit(
			(p) => addComponentAtPort(p, componentId, portId, component),
			`add ${component.name}`
		);
		if (!ok) return null;
		const connection = connectionsOf(this.project, component.id)[0];
		if (this.nav.current?.id === componentId && connection) {
			this.nav.setPath([
				...this.nav.path,
				{ componentId: component.id, viaConnectionId: connection.id }
			]);
		} else {
			this.nav.jumpTo(component.id);
		}
		return component.id;
	}

	/**
	 * Insert a component into a connection of the current component and show it: in the
	 * connection the walk arrived by it goes before the current component, in any other after.
	 */
	insert(connectionId: string, kind: ComponentKind): string | null {
		const connection = this.project.connections.find((c) => c.id === connectionId);
		if (!connection) return null;
		const component = createComponent(kind, this.project, this.#insertOptions(connection));
		const attached = this.#attachedToCurrent(connection);
		const ok = this.edit(
			(p) => insertComponentInConnection(p, connectionId, component),
			`add ${component.name}`
		);
		if (!ok) return null;
		this.#reveal(component.id, connectionId, attached);
		return component.id;
	}

	/** Insert a tee (or wye) into a connection and show its free branch port. */
	addBranch(connectionId: string, kind: 'tee' | 'wye' = 'tee'): string | null {
		const connection = this.project.connections.find((c) => c.id === connectionId);
		if (!connection) return null;
		const branch = createComponent(kind, this.project, this.#insertOptions(connection));
		const attached = this.#attachedToCurrent(connection);
		const ok = this.edit((p) => addBranch(p, connectionId, branch), `add ${branch.name}`);
		if (!ok) return null;
		this.#reveal(branch.id, connectionId, attached);
		const free = branch.ports.find((p) => !connectionAtPort(this.project, branch.id, p.id));
		if (free) this.nav.showConnection(free.id);
		return branch.id;
	}

	/** A component inserted in `connection` sits at its upstream end's elevation, sized to its last pipe. */
	#insertOptions(connection: PipeConnection): { elevation: number; nominalSize?: number } {
		const from = componentById(this.project, connection.fromComponentId);
		const size = connection.piping.pipes[connection.piping.pipes.length - 1]?.nominalSize;
		return { elevation: from?.elevation ?? 0, ...(size ? { nominalSize: size } : {}) };
	}

	#attachedToCurrent(connection: PipeConnection): boolean {
		const id = this.nav.current?.id;
		return !!id && (connection.fromComponentId === id || connection.toComponentId === id);
	}

	#reveal(insertedId: string, connectionId: string, attachedToCurrent: boolean): void {
		if (attachedToCurrent) {
			this.nav.setPath(pathAfterInsert(this.project, this.nav.path, insertedId, connectionId));
		} else {
			this.nav.jumpTo(insertedId);
		}
	}

	/**
	 * Delete a component. With `join`, its two connections become one (see canJoin). The walk
	 * goes back to the previous step, or starts at a former neighbor.
	 */
	remove(componentId: string, join: boolean): boolean {
		const component = componentById(this.project, componentId);
		if (!component) return false;
		const neighbors = connectionsOf(this.project, componentId).map((c) =>
			c.fromComponentId === componentId ? c.toComponentId : c.fromComponentId
		);
		const wasStart = this.nav.startId === componentId;
		const ok = this.edit(
			(p) => deleteComponent(p, componentId, { join }),
			`delete ${component.name}`
		);
		if (!ok) return false;
		if (wasStart) this.nav.restart(neighbors.find((id) => componentById(this.project, id)));
		return true;
	}

	/** Close a free port with a plug. */
	plug(componentId: string, portId: string): boolean {
		return this.edit((p) => plugPort(p, componentId, portId), `plug ${componentId} ${portId}`);
	}

	/** Connect a free port of the current component to a free port elsewhere (e.g. to close a loop). */
	connect(from: PortRef, to: PortRef): boolean {
		return this.edit(
			(p) => connectPorts(p, from, to),
			`connect ${from.componentId} to ${to.componentId}`
		);
	}

	/** Remove a connection, leaving both ports free. */
	disconnect(connectionId: string): boolean {
		return this.edit((p) => disconnect(p, connectionId), `remove connection ${connectionId}`);
	}

	/** Solve, and show the results pane on narrow screens. */
	async solve(): Promise<void> {
		this.pane = 'results';
		this.store.flush();
		await this.store.solve();
	}

	/**
	 * Open an element's results and trace (a row or flag in the results), and point the
	 * navigator at it (see #point). The pane does not change: on narrow screens the results stay
	 * in view, and showElement() goes to Build.
	 */
	inspect(element: ElementRef): void {
		this.inspected = element;
		this.#point(element);
	}

	closeInspector(): void {
		this.inspected = null;
	}

	/** Point the navigator at an element from the results and show it in Build. */
	showElement(element: ElementRef): void {
		this.#point(element);
		this.pane = 'build';
	}

	/**
	 * Clicking an element in the results starts the navigator's walk at it (design §5): at a
	 * component, or for a connection at its 'from' component with that connection's piping open.
	 * Elements no longer in the project leave the navigator as it is.
	 */
	#point(element: ElementRef): void {
		if (element.kind === 'component') {
			if (componentById(this.project, element.id)) this.nav.restart(element.id);
			return;
		}
		const connection = this.project.connections.find((c) => c.id === element.id);
		if (!connection) return;
		this.nav.restart(connection.fromComponentId);
		this.nav.showConnection(connection.fromPortId);
	}

	/**
	 * Show a component in the navigator (from results or issue lists); with `portId`, open the
	 * piping view on that port (e.g. a port that is not connected yet, with its actions).
	 */
	show(componentId: string, portId?: string): void {
		const component = componentById(this.project, componentId);
		if (!component) return;
		this.nav.jumpTo(componentId);
		if (portId && portById(component, portId)) this.nav.showConnection(portId);
		this.pane = 'build';
	}
}

/** What results labels depend on: names, kinds, port order and connection ends. */
export function labelsKey(project: Project): string {
	const parts: string[] = [];
	for (const c of project.components) {
		const kind = c.type === 'valve' ? c.valveType : c.type === 'branch' ? c.branchType : c.type;
		parts.push(`${c.id}\u0000${c.name}\u0000${kind}\u0000${c.ports.map((p) => p.id).join(',')}`);
	}
	for (const c of project.connections) {
		parts.push(
			`${c.id}\u0000${c.fromComponentId}:${c.fromPortId}\u0000${c.toComponentId}:${c.toPortId}\u0000${c.piping.fittings.map((f) => f.type).join(',')}`
		);
	}
	return parts.join('\n');
}

const WORKSPACE_KEY = Symbol('opensolve-pipe:workspace');

export function provideWorkspace(workspace: Workspace): Workspace {
	return setContext(WORKSPACE_KEY, workspace);
}

export function useWorkspace(): Workspace {
	const workspace = getContext<Workspace | undefined>(WORKSPACE_KEY);
	if (!workspace) throw new Error('No Workspace: call provideWorkspace in a parent component.');
	return workspace;
}
