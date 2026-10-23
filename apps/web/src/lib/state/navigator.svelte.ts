/**
 * Panel navigator state (SDD §3.1.1): the walk through the port graph.
 *
 * The breadcrumb `path` starts at a chosen component (default: the first reservoir or
 * reference node) and records the connections taken. Next follows a connection to a component
 * not yet on the path; at a branch the UI asks which one (nextOptions gives the choices, with
 * loops offered as a jump back). Previous steps back along the path.
 *
 * The path is re-validated against the current project on every read, so after an edit, undo
 * or redo it is cut back to the part that still exists (and comes back if an undo restores it).
 */
import type { Component, PipeConnection, Project } from '../api/types';
import {
	componentById,
	connectionAtPort,
	defaultStart,
	nextOptions,
	pathTo,
	validPathPrefix,
	type NavigationStep,
	type NextOption
} from '../utils/graph';
import type { ProjectStore } from './project.svelte';

export type EditMode = 'component' | 'connection';

/** What happens when Next is pressed. */
export type NextResult = 'moved' | 'choose' | 'none';

/** The valid part of `raw`, or a new walk from the default start when nothing of it is left. */
export function resolvePath(project: Project, raw: readonly NavigationStep[]): NavigationStep[] {
	const valid = validPathPrefix(project, raw);
	if (valid.length) return valid;
	const start = defaultStart(project);
	return start ? [{ componentId: start }] : [];
}

/** The port of the current (last) component that the arrival connection attaches to. */
export function arrivalPortId(
	project: Project,
	path: readonly NavigationStep[]
): string | undefined {
	const step = path[path.length - 1];
	if (!step?.viaConnectionId) return undefined;
	const connection = project.connections.find((c) => c.id === step.viaConnectionId);
	if (!connection) return undefined;
	if (connection.toComponentId === step.componentId) return connection.toPortId;
	if (connection.fromComponentId === step.componentId) return connection.fromPortId;
	return undefined;
}

/**
 * The port whose connection the piping view opens on by default: the first port other than the
 * one the walk arrived by (the way onward), else the arrival port.
 */
export function defaultActivePort(
	project: Project,
	path: readonly NavigationStep[]
): string | undefined {
	const step = path[path.length - 1];
	const component = step ? componentById(project, step.componentId) : undefined;
	if (!component) return undefined;
	const arrival = arrivalPortId(project, path);
	return (component.ports.find((p) => p.id !== arrival) ?? component.ports[0])?.id;
}

/** A connection joining components a and b (either direction), skipping `exclude`. */
export function connectionBetween(
	project: Project,
	a: string,
	b: string,
	exclude?: ReadonlySet<string>
): PipeConnection | undefined {
	return project.connections.find(
		(c) =>
			!exclude?.has(c.id) &&
			((c.fromComponentId === a && c.toComponentId === b) ||
				(c.fromComponentId === b && c.toComponentId === a))
	);
}

/**
 * The walk after component `insertedId` was inserted into connection `connectionId` of the
 * current component: if that was the connection the walk arrived by, the new component takes
 * the current one's place (between the previous component and it); otherwise it is the next
 * step after the current component. Either way the walk ends at the new component.
 */
export function pathAfterInsert(
	project: Project,
	path: readonly NavigationStep[],
	insertedId: string,
	connectionId: string
): NavigationStep[] {
	const current = path[path.length - 1];
	if (!current) return [{ componentId: insertedId }];
	if (current.viaConnectionId === connectionId && path.length > 1) {
		const previous = path[path.length - 2] as NavigationStep;
		const via = connectionBetween(project, previous.componentId, insertedId);
		const base = validPathPrefix(project, path.slice(0, -1));
		return via ? [...base, { componentId: insertedId, viaConnectionId: via.id }] : base;
	}
	const via = connectionBetween(project, current.componentId, insertedId);
	const base = validPathPrefix(project, path);
	return via
		? [...base, { componentId: insertedId, viaConnectionId: via.id }]
		: [{ componentId: insertedId }];
}

export class NavigatorStore {
	readonly #store: ProjectStore;
	#raw = $state.raw<readonly NavigationStep[]>([]);
	#mode = $state<EditMode>('component');
	/** Component the edit mode and active port were chosen for. */
	#modeFor = $state<string | null>(null);
	#port = $state<string | null>(null);

	constructor(store: ProjectStore, start?: string) {
		this.#store = store;
		this.restart(start);
	}

	/** The breadcrumb: valid in the current project; the last step is the current component. */
	readonly path: NavigationStep[] = $derived.by(() => resolvePath(this.#store.project, this.#raw));

	readonly current: Component | undefined = $derived.by(() => {
		const step = this.path[this.path.length - 1];
		return step ? componentById(this.#store.project, step.componentId) : undefined;
	});

	/** Ways forward from the current component (loops flagged). */
	readonly options: NextOption[] = $derived.by(() => nextOptions(this.#store.project, this.path));

	get startId(): string | undefined {
		return this.path[0]?.componentId;
	}

	/** The connection the walk arrived by (absent at the start). */
	get arrivalConnectionId(): string | undefined {
		return this.path[this.path.length - 1]?.viaConnectionId;
	}

	get mode(): EditMode {
		return this.#modeFor === this.current?.id ? this.#mode : 'component';
	}

	/** Port whose connection the piping view shows. */
	get activePortId(): string | undefined {
		const current = this.current;
		if (!current) return undefined;
		if (
			this.#modeFor === current.id &&
			this.#port &&
			current.ports.some((p) => p.id === this.#port)
		) {
			return this.#port;
		}
		return defaultActivePort(this.#store.project, this.path);
	}

	/** The connection at the active port, if it is connected. */
	get activeConnection(): PipeConnection | undefined {
		const current = this.current;
		const port = this.activePortId;
		return current && port ? connectionAtPort(this.#store.project, current.id, port) : undefined;
	}

	/** Replace the walk (steps are validated on read). */
	setPath(steps: readonly NavigationStep[]): void {
		this.#raw = [...steps];
		this.#mode = 'component';
		this.#modeFor = null;
		this.#port = null;
	}

	/** Start a new walk at `componentId` (default: the first boundary component). */
	restart(componentId?: string): void {
		const start = componentId ?? defaultStart(this.#store.project);
		this.setPath(start ? [{ componentId: start }] : []);
	}

	/**
	 * Next: with exactly one way forward that is not a loop, take it ('moved'); with several (a
	 * tee, a multi-port reservoir) or a loop, the UI must ask ('choose'); with none, 'none'.
	 */
	next(): NextResult {
		const options = this.options;
		const only = options[0];
		if (options.length === 1 && only && !only.loop) {
			this.choose(only);
			return 'moved';
		}
		return options.length ? 'choose' : 'none';
	}

	/** Follow a way forward; a loop option jumps back along the path instead of extending it. */
	choose(option: NextOption): void {
		if (option.loop && option.loopIndex !== undefined) {
			this.setPath(this.path.slice(0, option.loopIndex + 1));
			return;
		}
		this.setPath([
			...this.path,
			{ componentId: option.otherId, viaConnectionId: option.connection.id }
		]);
	}

	/** Step back along the path. */
	previous(): boolean {
		if (this.path.length <= 1) return false;
		this.setPath(this.path.slice(0, -1));
		return true;
	}

	/** Go back to breadcrumb step `index`. */
	goToStep(index: number): void {
		if (index < 0 || index >= this.path.length) return;
		this.setPath(this.path.slice(0, index + 1));
	}

	/**
	 * Show a component chosen directly (jump-to list, results): back along the path if it is on
	 * it, else by the shortest path from the start, else as a new walk starting there (a part of
	 * the network not connected to the start).
	 */
	jumpTo(componentId: string): void {
		const index = this.path.findIndex((s) => s.componentId === componentId);
		if (index >= 0) {
			this.goToStep(index);
			return;
		}
		const start = this.startId;
		const route = start ? pathTo(this.#store.project, start, componentId) : null;
		this.setPath(route ?? [{ componentId }]);
	}

	/** Go along a connection of the current component (arrival connection: step back). */
	follow(connectionId: string): void {
		if (connectionId === this.arrivalConnectionId) {
			this.previous();
			return;
		}
		const option = this.options.find((o) => o.connection.id === connectionId);
		if (option) this.choose(option);
	}

	/** Open the piping view on a port of the current component. */
	showConnection(portId: string): void {
		this.#mode = 'connection';
		this.#modeFor = this.current?.id ?? null;
		this.#port = portId;
	}

	showComponent(): void {
		this.#mode = 'component';
		this.#modeFor = this.current?.id ?? null;
	}
}
