/**
 * Port-graph helpers (D2, SDD §3.1.1, TSD §8.1). Components are nodes with typed ports;
 * PipeConnections are edges between two ports. The panel navigator walks this graph from a start
 * component; at a branch it asks which way to go, and the breadcrumb (a list of
 * NavigationSteps) records the path taken.
 *
 * All functions are pure and never modify the project.
 */
import type { Component, PipeConnection, Port, Project } from '../api/types';
import { namedPortRole } from './model-rules';

/** One step of the navigator's breadcrumb (SDD §3.1.1). */
export interface NavigationStep {
	componentId: string;
	/** Connection used to arrive here (absent for the start). */
	viaConnectionId?: string;
}

/** A port of a component. */
export interface PortRef {
	componentId: string;
	portId: string;
}

/** A connection attached to a component, seen from that component. */
export interface Neighbor {
	connection: PipeConnection;
	/** Port of this component the connection attaches to. */
	portId: string;
	/** Component at the other end. */
	otherId: string;
	/** Port at the other end. */
	otherPortId: string;
	/** True when this component is the connection's 'from' end (positive flow leaves here). */
	outgoing: boolean;
}

/** A way forward from the end of the navigator's path. */
export interface NextOption extends Neighbor {
	/** True when the connection leads back to a component already on the path (a loop). */
	loop: boolean;
	/** For a loop: index in the path of the component it leads back to. */
	loopIndex?: number;
}

/** Flow role of a port: 'in' receives flow, 'out' delivers it, 'any' either (boundaries). */
export type PortRole = 'in' | 'out' | 'any';

/**
 * Lookups of a stored project, built once per project version (each when first needed): the store
 * deep-freezes every project it keeps, so they never go stale. A project that is not frozen
 * throughout (an edit's draft) is searched as before. Each answers as the search does (the first
 * element with an id, in project order), so a large network's checks and tables take one pass, not
 * one per row.
 */
class GraphIndex {
	readonly #project: Project;
	#components: Map<string, Component> | undefined;
	#connections: Map<string, PipeConnection> | undefined;
	#attached: Map<string, PipeConnection[]> | undefined;
	#atPort: Map<string, PipeConnection> | undefined;

	constructor(project: Project) {
		this.#project = project;
	}

	/** Components by id. */
	get components(): Map<string, Component> {
		return (this.#components ??= firstById(this.#project.components));
	}

	/** Connections by id. */
	get connections(): Map<string, PipeConnection> {
		return (this.#connections ??= firstById(this.#project.connections));
	}

	/** The connections attached to each component, in project order (connectionsOf). */
	get attached(): Map<string, PipeConnection[]> {
		if (!this.#attached) {
			const attached = new Map<string, PipeConnection[]>();
			for (const connection of this.#project.connections) {
				const { fromComponentId: from, toComponentId: to } = connection;
				for (const id of from === to ? [from] : [from, to]) {
					const list = attached.get(id);
					if (list) list.push(connection);
					else attached.set(id, [connection]);
				}
			}
			this.#attached = attached;
		}
		return this.#attached;
	}

	/** The first connection at each port (connectionAtPort), by portKey(). */
	get atPort(): Map<string, PipeConnection> {
		if (!this.#atPort) {
			const atPort = new Map<string, PipeConnection>();
			for (const connection of this.#project.connections) {
				for (const key of [
					portKey(connection.fromComponentId, connection.fromPortId),
					portKey(connection.toComponentId, connection.toPortId)
				]) {
					if (!atPort.has(key)) atPort.set(key, connection);
				}
			}
			this.#atPort = atPort;
		}
		return this.#atPort;
	}
}

function firstById<T extends { id: string }>(list: readonly T[]): Map<string, T> {
	const byId = new Map<string, T>();
	for (const element of list) if (!byId.has(element.id)) byId.set(element.id, element);
	return byId;
}

const indexes = new WeakMap<Project, GraphIndex>();

const portKey = (componentId: string, portId: string) => `${componentId}\u0000${portId}`;

/** The index of a project frozen throughout (null for one that may still change). */
function indexOf(project: Project): GraphIndex | null {
	const known = indexes.get(project);
	if (known) return known;
	const { components, connections } = project;
	if (!Object.isFrozen(project) || !Object.isFrozen(components) || !Object.isFrozen(connections)) {
		return null;
	}
	if (!components.every(Object.isFrozen) || !connections.every(Object.isFrozen)) return null;
	const index = new GraphIndex(project);
	indexes.set(project, index);
	return index;
}

export function componentById(project: Project, id: string): Component | undefined {
	const index = indexOf(project);
	return index ? index.components.get(id) : project.components.find((c) => c.id === id);
}

export function connectionById(project: Project, id: string): PipeConnection | undefined {
	const index = indexOf(project);
	return index ? index.connections.get(id) : project.connections.find((c) => c.id === id);
}

export function portById(component: Component, portId: string): Port | undefined {
	return component.ports.find((p) => p.id === portId);
}

/** The connection attached to a port, if any. */
export function connectionAtPort(
	project: Project,
	componentId: string,
	portId: string
): PipeConnection | undefined {
	const index = indexOf(project);
	if (index) return index.atPort.get(portKey(componentId, portId));
	return project.connections.find(
		(c) =>
			(c.fromComponentId === componentId && c.fromPortId === portId) ||
			(c.toComponentId === componentId && c.toPortId === portId)
	);
}

/** Ports of a component with no connection, in port order. */
export function freePorts(project: Project, componentId: string): Port[] {
	const component = componentById(project, componentId);
	if (!component) return [];
	const used = new Set<string>();
	for (const c of connectionsOf(project, componentId)) {
		if (c.fromComponentId === componentId) used.add(c.fromPortId);
		if (c.toComponentId === componentId) used.add(c.toPortId);
	}
	return component.ports.filter((p) => !used.has(p.id));
}

/** Connections attached to a component (each once). */
export function connectionsOf(project: Project, componentId: string): PipeConnection[] {
	const index = indexOf(project);
	if (index) return [...(index.attached.get(componentId) ?? [])];
	return project.connections.filter(
		(c) => c.fromComponentId === componentId || c.toComponentId === componentId
	);
}

/** The end of a connection that is not the given port. */
export function otherEnd(connection: PipeConnection, end: PortRef): PortRef {
	const isFrom =
		connection.fromComponentId === end.componentId && connection.fromPortId === end.portId;
	return isFrom
		? { componentId: connection.toComponentId, portId: connection.toPortId }
		: { componentId: connection.fromComponentId, portId: connection.fromPortId };
}

/**
 * Connections attached to a component with the component and port at the other end, in the
 * component's port order. A connection between two ports of the same component appears once
 * per port.
 */
export function neighbors(project: Project, componentId: string): Neighbor[] {
	const component = componentById(project, componentId);
	if (!component) return [];
	const byPort = new Map<string, Neighbor>();
	for (const connection of connectionsOf(project, componentId)) {
		if (connection.fromComponentId === componentId && !byPort.has(connection.fromPortId)) {
			byPort.set(connection.fromPortId, {
				connection,
				portId: connection.fromPortId,
				otherId: connection.toComponentId,
				otherPortId: connection.toPortId,
				outgoing: true
			});
		}
		if (connection.toComponentId === componentId && !byPort.has(connection.toPortId)) {
			byPort.set(connection.toPortId, {
				connection,
				portId: connection.toPortId,
				otherId: connection.fromComponentId,
				otherPortId: connection.fromPortId,
				outgoing: false
			});
		}
	}
	return component.ports.flatMap((p) => {
		const n = byPort.get(p.id);
		return n ? [n] : [];
	});
}

/**
 * Ways forward from the end of the path: connections of the current component other than the
 * one used to arrive. Those leading to a component already on the path are loop options
 * (jump back), flagged with `loop` and the path index they lead to. Connections from the
 * current component back to itself are not options.
 */
export function nextOptions(project: Project, path: readonly NavigationStep[]): NextOption[] {
	const current = path[path.length - 1];
	if (!current) return [];
	const index = new Map<string, number>();
	path.forEach((step, i) => index.set(step.componentId, i));
	return neighbors(project, current.componentId)
		.filter((n) => n.connection.id !== current.viaConnectionId && n.otherId !== current.componentId)
		.map((n) => {
			const loopIndex = index.get(n.otherId);
			return loopIndex === undefined ? { ...n, loop: false } : { ...n, loop: true, loopIndex };
		});
}

export function isBoundary(component: Component): boolean {
	return component.type === 'reservoir' || component.type === 'reference_node';
}

/** Where the navigator starts: the first reservoir or reference node, else the first component. */
export function defaultStart(project: Project): string | undefined {
	return (project.components.find(isBoundary) ?? project.components[0])?.id;
}

function adjacency(project: Project): Map<string, { connectionId: string; otherId: string }[]> {
	const adj = new Map<string, { connectionId: string; otherId: string }[]>();
	for (const c of project.components) adj.set(c.id, []);
	for (const c of project.connections) {
		adj.get(c.fromComponentId)?.push({ connectionId: c.id, otherId: c.toComponentId });
		adj.get(c.toComponentId)?.push({ connectionId: c.id, otherId: c.fromComponentId });
	}
	return adj;
}

/** Ids of the components connected to `startId` (including it), in breadth-first order. */
export function reachable(project: Project, startId: string): Set<string> {
	const adj = adjacency(project);
	if (!adj.has(startId)) return new Set();
	const seen = new Set([startId]);
	const queue = [startId];
	for (let i = 0; i < queue.length; i++) {
		for (const { otherId } of adj.get(queue[i] as string) ?? []) {
			if (!seen.has(otherId) && adj.has(otherId)) {
				seen.add(otherId);
				queue.push(otherId);
			}
		}
	}
	return seen;
}

/**
 * Shortest path (fewest connections) from `startId` to `targetId` as navigator steps, or null
 * when the target is not connected to the start. Ties follow connection order.
 */
export function pathTo(
	project: Project,
	startId: string,
	targetId: string
): NavigationStep[] | null {
	const adj = adjacency(project);
	if (!adj.has(startId) || !adj.has(targetId)) return null;
	const via = new Map<string, { from: string; connectionId: string } | null>([[startId, null]]);
	const queue = [startId];
	for (let i = 0; i < queue.length && !via.has(targetId); i++) {
		const id = queue[i] as string;
		for (const { connectionId, otherId } of adj.get(id) ?? []) {
			if (!via.has(otherId) && adj.has(otherId)) {
				via.set(otherId, { from: id, connectionId });
				queue.push(otherId);
			}
		}
	}
	if (!via.has(targetId)) return null;
	const steps: NavigationStep[] = [];
	for (let id: string | undefined = targetId; id !== undefined;) {
		const link: { from: string; connectionId: string } | null | undefined = via.get(id);
		steps.unshift(
			link ? { componentId: id, viaConnectionId: link.connectionId } : { componentId: id }
		);
		id = link?.from;
	}
	return steps;
}

/**
 * The longest prefix of a navigator path that is still valid in `project` (after an edit or
 * undo): every component exists, and each step's connection joins it to the previous step.
 */
export function validPathPrefix(
	project: Project,
	path: readonly NavigationStep[]
): NavigationStep[] {
	const valid: NavigationStep[] = [];
	for (const [i, step] of path.entries()) {
		if (!componentById(project, step.componentId)) break;
		if (i === 0) {
			valid.push({ componentId: step.componentId });
			continue;
		}
		const previous = path[i - 1] as NavigationStep;
		const connection = step.viaConnectionId
			? connectionById(project, step.viaConnectionId)
			: undefined;
		const joins =
			connection &&
			((connection.fromComponentId === previous.componentId &&
				connection.toComponentId === step.componentId) ||
				(connection.toComponentId === previous.componentId &&
					connection.fromComponentId === step.componentId));
		if (!joins) break;
		valid.push(step);
	}
	return valid;
}

/**
 * The flow role of a port: from its direction when set ('inlet'/'outlet'), else from the role
 * the API gives the port in its type's forward flow direction (x-port-roles: pumps, valves, tees
 * and wyes; model-rules.ts). Boundary and plug ports are 'any'. Roles only orient new
 * connections; the solver decides the actual flow direction.
 */
export function portRole(component: Component, portId: string): PortRole {
	const port = portById(component, portId);
	const role =
		port?.direction === 'inlet' || port?.direction === 'outlet'
			? port.direction
			: namedPortRole(component, portId);
	return role === 'inlet' ? 'in' : role === 'outlet' ? 'out' : 'any';
}

/** The port flow enters by: the first 'in' port, else the first 'any' port. */
export function inletPort(component: Component): Port | undefined {
	return (
		component.ports.find((p) => portRole(component, p.id) === 'in') ??
		component.ports.find((p) => portRole(component, p.id) === 'any')
	);
}

/** The port flow leaves by: the first 'out' port, else the first 'any' port. */
export function outletPort(component: Component): Port | undefined {
	return (
		component.ports.find((p) => portRole(component, p.id) === 'out') ??
		component.ports.find((p) => portRole(component, p.id) === 'any')
	);
}

/**
 * The free port the network goes on from ("Add after", Next at the end of the walk): a free port
 * flow can leave by ('out' or 'any'), `preferred` first; else, when only ports flow enters by are
 * free (the walk arrived at the outlet), `preferred` or the first of those. So adding after a
 * valve or pump with both ports free goes downstream, at its outlet, not before it at its inlet.
 */
export function onwardFreePort(
	project: Project,
	componentId: string,
	preferred?: string
): Port | undefined {
	const component = componentById(project, componentId);
	if (!component) return undefined;
	const free = freePorts(project, componentId);
	const onward = free.filter((p) => portRole(component, p.id) !== 'in');
	const pick = (ports: Port[]) => ports.find((p) => p.id === preferred) ?? ports[0];
	return pick(onward) ?? pick(free);
}
