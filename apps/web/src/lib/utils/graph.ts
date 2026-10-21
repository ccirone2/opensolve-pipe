/**
 * Port-graph helpers (D2, SDD §3.1.1, TSD §8.1). Components are nodes with typed ports;
 * PipeConnections are edges between two ports. The panel navigator walks this graph from a start
 * component; at a branch it asks which way to go, and the breadcrumb (a list of
 * NavigationSteps) records the path taken.
 *
 * All functions are pure and never modify the project.
 */
import type { Component, PipeConnection, Port, Project } from '../api/types';

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

export function componentById(project: Project, id: string): Component | undefined {
	return project.components.find((c) => c.id === id);
}

export function connectionById(project: Project, id: string): PipeConnection | undefined {
	return project.connections.find((c) => c.id === id);
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
	for (const c of project.connections) {
		if (c.fromComponentId === componentId) used.add(c.fromPortId);
		if (c.toComponentId === componentId) used.add(c.toPortId);
	}
	return component.ports.filter((p) => !used.has(p.id));
}

/** Connections attached to a component (each once). */
export function connectionsOf(project: Project, componentId: string): PipeConnection[] {
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
	for (const connection of project.connections) {
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

const NAMED_ROLES: Record<string, Record<string, PortRole>> = {
	pump: { suction: 'in', discharge: 'out' },
	valve: { inlet: 'in', outlet: 'out' },
	branch: {
		run_inlet: 'in',
		run_outlet: 'out',
		branch: 'out',
		inlet: 'in',
		outlet_1: 'out',
		outlet_2: 'out'
	}
};

/**
 * The flow role of a port: from its direction when set ('inlet'/'outlet'), else from the
 * standard port names of pumps, valves, tees and wyes. Boundary and plug ports are 'any'.
 * Roles only orient new connections; the solver decides the actual flow direction.
 */
export function portRole(component: Component, portId: string): PortRole {
	const port = portById(component, portId);
	if (port?.direction === 'inlet') return 'in';
	if (port?.direction === 'outlet') return 'out';
	return NAMED_ROLES[component.type]?.[portId] ?? 'any';
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
