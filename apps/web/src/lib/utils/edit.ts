/**
 * Graph-edit operations (D2). Each one is pure: it returns a new project and never modifies its
 * input. Each keeps a valid project valid (schema and port-graph references); a request that
 * would break that, such as connecting a port that is already connected, throws EditError
 * instead, so the UI can disable the action beforehand.
 */
import type {
	Component,
	Fitting,
	PipeConnection,
	PipingSegment,
	Port,
	Project,
	PumpCurve
} from '../api/types';
import {
	CONNECTION_PREFIX,
	createComponent,
	createConnection,
	DEFAULT_NOMINAL_SIZE,
	defaultPiping,
	newId,
	SHORT_PIPE_LENGTH,
	usedIds
} from './factory';
import {
	componentById,
	connectionAtPort,
	connectionById,
	connectionsOf,
	inletPort,
	otherEnd,
	outletPort,
	portById,
	portRole,
	type PortRef,
	type PortRole
} from './graph';
import {
	ENTRANCE_TYPES,
	EXIT_TYPES,
	maxPorts,
	REDUCER_TYPES,
	requiredPortCount,
	requiredPortIds
} from './model-rules';

export class EditError extends Error {
	constructor(message: string) {
		super(message);
		this.name = 'EditError';
	}
}

/**
 * Whether ports can be added to a component: its type fixes neither its port ids nor their
 * number (in v1, reservoirs) and it has fewer than the schema's maximum (model-rules.ts).
 */
export function canAddPort(component: Component): boolean {
	return (
		requiredPortIds(component) === null &&
		requiredPortCount(component) === null &&
		component.ports.length < maxPorts(component)
	);
}

function requireComponent(project: Project, id: string): Component {
	const component = componentById(project, id);
	if (!component) throw new EditError(`There is no component "${id}".`);
	return component;
}

function requireConnection(project: Project, id: string): PipeConnection {
	const connection = connectionById(project, id);
	if (!connection) throw new EditError(`There is no connection "${id}".`);
	return connection;
}

function requirePort(component: Component, portId: string): Port {
	const port = portById(component, portId);
	if (!port) throw new EditError(`Component "${component.id}" has no port "${portId}".`);
	return port;
}

function requireFreePort(project: Project, ref: PortRef): { component: Component; port: Port } {
	const component = requireComponent(project, ref.componentId);
	const port = requirePort(component, ref.portId);
	if (connectionAtPort(project, ref.componentId, ref.portId)) {
		throw new EditError(`Port "${ref.portId}" of "${ref.componentId}" is already connected.`);
	}
	return { component, port };
}

function requireNewComponent(project: Project, component: Component): void {
	if (usedIds(project).has(component.id)) {
		throw new EditError(`The id "${component.id}" is already used in this project.`);
	}
}

function replaceAt<T>(items: readonly T[], index: number, ...replacements: T[]): T[] {
	return [...items.slice(0, index), ...replacements, ...items.slice(index + 1)];
}

/**
 * True when a connection from `from` to `to` would run against the expected flow: it leaves a
 * port that receives flow (a pump suction, a valve inlet, a tee's run inlet, an assigned-flow
 * demand) or arrives at one that delivers it (an assigned-flow supply), and turning it around
 * agrees with both ends' roles (ports with role 'any', such as reservoir ports, accept either
 * direction; see flowRole).
 */
function runsAgainstFlow(project: Project, from: PortRef, to: PortRef): boolean {
	const role = (ref: PortRef) => {
		const component = componentById(project, ref.componentId);
		return component ? flowRole(component, ref.portId) : 'any';
	};
	const fromRole = role(from);
	const toRole = role(to);
	return (fromRole === 'in' || toRole === 'out') && fromRole !== 'out' && toRole !== 'in';
}

/** The same connection described the other way round: ends swapped, piping reversed. */
function turnedAround(connection: PipeConnection): PipeConnection {
	return {
		...connection,
		fromComponentId: connection.toComponentId,
		fromPortId: connection.toPortId,
		toComponentId: connection.fromComponentId,
		toPortId: connection.fromPortId,
		piping: reversePiping(connection.piping)
	};
}

/** A connection oriented with the expected flow (see runsAgainstFlow). */
function withFlow(project: Project, connection: PipeConnection): PipeConnection {
	const from = { componentId: connection.fromComponentId, portId: connection.fromPortId };
	const to = { componentId: connection.toComponentId, portId: connection.toPortId };
	return runsAgainstFlow(project, from, to) ? turnedAround(connection) : connection;
}

/** The default entrance at a reservoir: sharp-edged (flush), K from Crane TP-410 via the API. */
export const DEFAULT_ENTRANCE: Fitting['type'] = 'entrance_sharp';
/** The default exit at a reservoir (the API's exit fitting; K from its cited correlation). */
export const DEFAULT_EXIT: Fitting['type'] = 'exit';

/**
 * Whether piping at the reservoir end of a connection has an entrance or exit fitting: either
 * describes the loss where the pipe meets the body of liquid (entrance when flow leaves it, exit
 * when it enters).
 */
export function hasReservoirLoss(piping: PipingSegment): boolean {
	return piping.fittings.some((f) => EXIT_TYPES.has(f.type) || ENTRANCE_TYPES.has(f.type));
}

/**
 * The connection with the cited default losses where it meets a reservoir (GOALS §4.1: a cited
 * default, visible in the piping and removable): a sharp-edged entrance where it leaves one (its
 * 'from' end, the expected flow direction) and an exit where it arrives at one (its 'to' end).
 * K values come from the API's fitting library (Crane TP-410). An end whose piping already has
 * an entrance or exit fitting is left as it is.
 */
export function withReservoirLosses(project: Project, connection: PipeConnection): PipeConnection {
	const isReservoir = (id: string) => componentById(project, id)?.type === 'reservoir';
	const { pipes, fittings } = connection.piping;
	const added: Fitting[] = [];
	if (
		isReservoir(connection.fromComponentId) &&
		!fittings.some((f) => ENTRANCE_TYPES.has(f.type))
	) {
		added.push({ type: DEFAULT_ENTRANCE, quantity: 1, pipeIndex: 0 });
	}
	if (isReservoir(connection.toComponentId) && !fittings.some((f) => EXIT_TYPES.has(f.type))) {
		added.push({ type: DEFAULT_EXIT, quantity: 1, pipeIndex: Math.max(0, pipes.length - 1) });
	}
	if (!added.length) return connection;
	return { ...connection, piping: { pipes, fittings: [...fittings, ...added] } };
}

/**
 * The role a port plays for the expected flow: its own role (portRole), except at an
 * assigned-flow node, whose entered flow fixes it (SDD §4.11): a demand (flow > 0) receives flow
 * at its port, a supply (flow < 0) delivers it, and a flow of 0 has no direction.
 */
export function flowRole(component: Component, portId: string): PortRole {
	if (component.type === 'assigned_flow') {
		return component.flow > 0 ? 'in' : component.flow < 0 ? 'out' : 'any';
	}
	return portRole(component, portId);
}

/**
 * Whether a component added at a free port goes upstream of it, by the expected flow (see
 * addComponentAtPort): when the existing port receives flow (a pump suction, a valve inlet, a
 * tee's run inlet, an assigned-flow demand), or when it takes either direction (a reservoir
 * port) and every port of the new component delivers flow (an assigned-flow supply).
 */
export function addsUpstream(existing: Component, portId: string, added: Component): boolean {
	const role = flowRole(existing, portId);
	if (role !== 'any') return role === 'in';
	return added.ports.length > 0 && added.ports.every((p) => flowRole(added, p.id) === 'out');
}

/**
 * Add `newComponent` at a free port of an existing component, connected to the new
 * component's first suitable port with a default pipe sized to the existing port (and the
 * default entrance or exit fitting where it meets a reservoir, see withReservoirLosses).
 *
 * The connection is oriented with the expected flow (addsUpstream): when the existing port
 * receives flow (a pump suction, a valve inlet, a tee's run inlet, an assigned-flow demand), or
 * takes either direction while the new component only delivers flow (an assigned-flow supply),
 * the new component is upstream and is connected by its outlet; otherwise it is downstream and
 * connected by its inlet. So a supply added after a reservoir runs into it, and gets the exit
 * loss there, as the flow it enters does.
 */
export function addComponentAtPort(
	project: Project,
	componentId: string,
	portId: string,
	newComponent: Component
): Project {
	const { component, port } = requireFreePort(project, { componentId, portId });
	requireNewComponent(project, newComponent);
	const upstream = addsUpstream(component, portId, newComponent);
	const newPort = upstream ? outletPort(newComponent) : inletPort(newComponent);
	if (!newPort) throw new EditError(`"${newComponent.id}" has no port to connect.`);
	const existingEnd = { componentId, portId };
	const newEnd = { componentId: newComponent.id, portId: newPort.id };
	const withComponent = { ...project, components: [...project.components, newComponent] };
	const connection = withReservoirLosses(
		withComponent,
		createConnection(
			withComponent,
			upstream ? newEnd : existingEnd,
			upstream ? existingEnd : newEnd,
			defaultPiping(port.nominalSize)
		)
	);
	return { ...withComponent, connections: [...project.connections, connection] };
}

/**
 * Insert a component into a connection (from A to B), splitting it in two:
 * A → component inlet keeps the connection's id and all its piping; component outlet → B is a
 * new connection with one short pipe (SHORT_PIPE_LENGTH, 1 m) of the same material, schedule
 * and size as the last pipe segment, so the insertion adds 1 m of pipe for the user to adjust.
 * Exit fittings describe the discharge at the B end, so they move to the new half.
 *
 * The split follows the expected flow, so the component faces it: a connection drawn against
 * the flow (for example from a pump suction to the tank feeding it, see runsAgainstFlow) is
 * first turned around, its piping reversed, so A is the upstream end and the component's inlet
 * faces A.
 *
 * The component needs separate inlet and outlet ports (pumps, valves; tees and wyes use their
 * run, leaving the branch port free).
 */
export function insertComponentInConnection(
	project: Project,
	connectionId: string,
	component: Component
): Project {
	const original = requireConnection(project, connectionId);
	requireNewComponent(project, component);
	const connection = withFlow(project, original);
	const inlet = inletPort(component);
	const outlet = outletPort(component);
	if (!inlet || !outlet || inlet.id === outlet.id) {
		throw new EditError(`"${component.id}" needs separate inlet and outlet ports to be inserted.`);
	}
	const { pipes, fittings } = connection.piping;
	const lastPipe = pipes[pipes.length - 1];
	if (!lastPipe) throw new EditError(`Connection "${connectionId}" has no pipe.`);
	const exits = fittings.filter((f) => EXIT_TYPES.has(f.type));
	const upstream: PipeConnection = {
		...connection,
		toComponentId: component.id,
		toPortId: inlet.id,
		piping: { pipes, fittings: fittings.filter((f) => !EXIT_TYPES.has(f.type)) }
	};
	const withComponent = { ...project, components: [...project.components, component] };
	const downstream = createConnection(
		withComponent,
		{ componentId: component.id, portId: outlet.id },
		{ componentId: connection.toComponentId, portId: connection.toPortId },
		{
			pipes: [{ ...lastPipe, length: SHORT_PIPE_LENGTH }],
			fittings: exits.map((f) => ({ ...f, pipeIndex: 0 }))
		}
	);
	const index = project.connections.indexOf(original);
	return {
		...withComponent,
		connections: replaceAt(project.connections, index, upstream, downstream)
	};
}

/**
 * Insert a tee into a connection (its run in line, the branch port left free for the new
 * branch). Without `branch`, a tee is created at the upstream component's elevation, sized to
 * the connection's last pipe.
 */
export function addBranch(project: Project, connectionId: string, branch?: Component): Project {
	const connection = requireConnection(project, connectionId);
	const from = requireComponent(project, connection.fromComponentId);
	const size =
		connection.piping.pipes[connection.piping.pipes.length - 1]?.nominalSize ??
		portById(from, connection.fromPortId)?.nominalSize;
	const tee =
		branch ?? createComponent('tee', project, { elevation: from.elevation, nominalSize: size });
	if (tee.type !== 'branch') throw new EditError('A branch is added with a tee or a wye.');
	return insertComponentInConnection(project, connectionId, tee);
}

/** What deleting a component with `join` does (see joinPlan). */
export interface JoinPlan {
	/** The two ports whose connections are merged, in port order. */
	ports: [Port, Port];
	/** Plugs closing the component's other ports; they are removed with their stubs. */
	plugIds: string[];
}

/**
 * Whether deleting a component can join two of its neighbors into one connection, and how:
 * exactly two of its ports are connected (by different connections), or exactly two are
 * connected to something other than a plug. Its other ports must be free or plugged, as on a
 * tee whose branch was added and then left open or closed. Null when it cannot join.
 */
export function joinPlan(project: Project, componentId: string): JoinPlan | null {
	const component = componentById(project, componentId);
	if (!component) return null;
	const attached = component.ports.flatMap((port) => {
		const connection = connectionAtPort(project, componentId, port.id);
		if (!connection) return [];
		const other = otherEnd(connection, { componentId, portId: port.id });
		const plug = componentById(project, other.componentId);
		return [{ port, connection, plugId: plug?.type === 'plug' ? plug.id : undefined }];
	});
	const kept = attached.length === 2 ? attached : attached.filter((a) => a.plugId === undefined);
	const [a, b] = kept;
	if (kept.length !== 2 || !a || !b || a.connection === b.connection) return null;
	const plugIds = attached.filter((x) => !kept.includes(x)).map((x) => x.plugId as string);
	return { ports: [a.port, b.port], plugIds };
}

/** True when deleting the component can join two of its neighbors (see joinPlan). */
export function canJoin(project: Project, componentId: string): boolean {
	return joinPlan(project, componentId) !== null;
}

/**
 * The same piping traversed the other way: pipes reversed, fitting indices mirrored.
 *
 * A reducer sits between pipes i and i + 1, which become n - 2 - i and n - 1 - i. One placed
 * after the last pipe (i = n - 1, which the model rules flag: it needs a following segment)
 * would mirror to -1, which the schema rejects; it is kept at 0 instead, so in a join it lies
 * between the two joined sides.
 */
export function reversePiping(piping: PipingSegment): PipingSegment {
	const n = piping.pipes.length;
	return {
		pipes: [...piping.pipes].reverse(),
		fittings: piping.fittings.map((f) => ({
			...f,
			pipeIndex: Math.max(0, (REDUCER_TYPES.has(f.type) ? n - 2 : n - 1) - f.pipeIndex)
		}))
	};
}

/**
 * Delete a component and its connections, freeing the neighbors' ports.
 *
 * With `join` (see joinPlan: two connected ports, any others free or plugged), the two
 * connections are merged into one instead, so the neighbors stay connected: pipes in series
 * (upstream connection first, in flow order) and fittings with their pipe indices offset. The
 * merged connection keeps the upstream connection's id. Plugs on the other ports are removed
 * with their stubs.
 */
export function deleteComponent(
	project: Project,
	componentId: string,
	options: { join?: boolean } = {}
): Project {
	const component = requireComponent(project, componentId);
	const attached = new Set(connectionsOf(project, componentId));
	const components = project.components.filter((c) => c !== component);
	if (!options.join) {
		return {
			...project,
			components,
			connections: project.connections.filter((c) => !attached.has(c))
		};
	}
	const plan = joinPlan(project, componentId);
	if (!plan) {
		throw new EditError(
			`"${componentId}" cannot be removed and joined: it needs exactly two connected ports, with any others free or plugged.`
		);
	}
	const [first, second] = plan.ports;
	const [inPort, outPort] =
		portRole(component, second.id) === 'in' ? [second, first] : [first, second];
	const inConnection = connectionAtPort(project, componentId, inPort.id) as PipeConnection;
	const outConnection = connectionAtPort(project, componentId, outPort.id) as PipeConnection;

	const inEnd = { componentId, portId: inPort.id };
	const outEnd = { componentId, portId: outPort.id };
	const endsAt = (c: PipeConnection, end: PortRef) =>
		c.toComponentId === end.componentId && c.toPortId === end.portId;
	const startsAt = (c: PipeConnection, end: PortRef) =>
		c.fromComponentId === end.componentId && c.fromPortId === end.portId;

	// Upstream piping oriented toward the component; downstream piping away from it.
	const upstreamPiping = endsAt(inConnection, inEnd)
		? inConnection.piping
		: reversePiping(inConnection.piping);
	const downstreamPiping = startsAt(outConnection, outEnd)
		? outConnection.piping
		: reversePiping(outConnection.piping);
	const source = endsAt(inConnection, inEnd)
		? { componentId: inConnection.fromComponentId, portId: inConnection.fromPortId }
		: { componentId: inConnection.toComponentId, portId: inConnection.toPortId };
	const target = startsAt(outConnection, outEnd)
		? { componentId: outConnection.toComponentId, portId: outConnection.toPortId }
		: { componentId: outConnection.fromComponentId, portId: outConnection.fromPortId };
	const offset = upstreamPiping.pipes.length;
	const merged: PipeConnection = {
		id: inConnection.id,
		fromComponentId: source.componentId,
		fromPortId: source.portId,
		toComponentId: target.componentId,
		toPortId: target.portId,
		piping: {
			pipes: [...upstreamPiping.pipes, ...downstreamPiping.pipes],
			fittings: [
				...upstreamPiping.fittings,
				...downstreamPiping.fittings.map((f) => ({ ...f, pipeIndex: f.pipeIndex + offset }))
			]
		}
	};
	const plugs = new Set(plan.plugIds);
	const connections = project.connections.flatMap((c) =>
		c === inConnection
			? [merged]
			: c === outConnection ||
				  (attached.has(c) && (plugs.has(c.fromComponentId) || plugs.has(c.toComponentId)))
				? []
				: [c]
	);
	return {
		...project,
		components: components.filter((c) => !plugs.has(c.id)),
		connections
	};
}

/**
 * Close a free port with a plug, connected by a short stub of default pipe (SHORT_PIPE_LENGTH)
 * sized to the port. The plug sits at the port's elevation.
 */
export function plugPort(project: Project, componentId: string, portId: string): Project {
	const { component, port } = requireFreePort(project, { componentId, portId });
	const plug = createComponent('plug', project, {
		nominalSize: port.nominalSize,
		elevation: port.elevation ?? component.elevation
	});
	const withPlug = { ...project, components: [...project.components, plug] };
	const connection = createConnection(
		withPlug,
		{ componentId, portId },
		{ componentId: plug.id, portId: 'port_1' },
		defaultPiping(port.nominalSize, SHORT_PIPE_LENGTH)
	);
	return { ...withPlug, connections: [...project.connections, connection] };
}

/**
 * Connect two free ports (for example to close a loop) with `piping` (listed from `from` to
 * `to`), by default a default pipe sized to the `from` port (with the default entrance or exit
 * fitting where it meets a reservoir, see withReservoirLosses). The connection runs with the
 * expected flow: from `from` to `to`, unless that is against the ports' roles (see
 * runsAgainstFlow, e.g. from a pump suction to the tank feeding it); then it is turned around,
 * piping included.
 */
export function connectPorts(
	project: Project,
	from: PortRef,
	to: PortRef,
	piping?: PipingSegment
): Project {
	const start = requireFreePort(project, from);
	requireFreePort(project, to);
	if (from.componentId === to.componentId && from.portId === to.portId) {
		throw new EditError('A port cannot be connected to itself.');
	}
	const oriented = withFlow(
		project,
		createConnection(
			project,
			from,
			to,
			piping ?? defaultPiping(start.port.nominalSize),
			newId(project, CONNECTION_PREFIX)
		)
	);
	const connection = piping ? oriented : withReservoirLosses(project, oriented);
	return { ...project, connections: [...project.connections, connection] };
}

/** Remove a connection, leaving both ports free. */
export function disconnect(project: Project, connectionId: string): Project {
	const connection = requireConnection(project, connectionId);
	return { ...project, connections: project.connections.filter((c) => c !== connection) };
}

/**
 * Replace a component with `update(copy of it)`. The id cannot change, and every connected
 * port must still exist (disconnect a port before removing it).
 */
export function updateComponent(
	project: Project,
	componentId: string,
	update: (component: Component) => Component
): Project {
	const component = requireComponent(project, componentId);
	const updated = update(structuredClone(component));
	if (updated.id !== componentId) throw new EditError('A component id cannot be changed.');
	for (const connection of connectionsOf(project, componentId)) {
		const ends = [
			[connection.fromComponentId, connection.fromPortId],
			[connection.toComponentId, connection.toPortId]
		] as const;
		for (const [cid, pid] of ends) {
			if (cid === componentId && !portById(updated, pid)) {
				throw new EditError(`Port "${pid}" is connected; disconnect it before removing it.`);
			}
		}
	}
	const index = project.components.indexOf(component);
	return { ...project, components: replaceAt(project.components, index, updated) };
}

/** Replace a connection with `update(copy of it)`. Its id and both ends cannot change. */
export function updateConnection(
	project: Project,
	connectionId: string,
	update: (connection: PipeConnection) => PipeConnection
): Project {
	const connection = requireConnection(project, connectionId);
	const updated = update(structuredClone(connection));
	const same =
		updated.id === connection.id &&
		updated.fromComponentId === connection.fromComponentId &&
		updated.fromPortId === connection.fromPortId &&
		updated.toComponentId === connection.toComponentId &&
		updated.toPortId === connection.toPortId;
	if (!same) throw new EditError('A connection id and its ends cannot be changed here.');
	const index = project.connections.indexOf(connection);
	return { ...project, connections: replaceAt(project.connections, index, updated) };
}

/** Add a port to a reservoir (`port_<n>`, sized like its last port unless given). */
export function addPort(
	project: Project,
	componentId: string,
	options: { nominalSize?: number; elevation?: number } = {}
): Project {
	const component = requireComponent(project, componentId);
	if (requiredPortIds(component) !== null || requiredPortCount(component) !== null) {
		throw new EditError('Only reservoirs can have extra ports.');
	}
	if (!canAddPort(component)) {
		throw new EditError(`A reservoir has at most ${maxPorts(component)} ports.`);
	}
	const ids = new Set(component.ports.map((p) => p.id));
	let n = 1;
	while (ids.has(`port_${n}`)) n++;
	const last = component.ports[component.ports.length - 1];
	const port: Port = {
		id: `port_${n}`,
		nominalSize: options.nominalSize ?? last?.nominalSize ?? DEFAULT_NOMINAL_SIZE,
		direction: 'bidirectional',
		...(options.elevation === undefined ? {} : { elevation: options.elevation })
	};
	return updateComponent(project, componentId, (c) => ({ ...c, ports: [...c.ports, port] }));
}

/** Remove a free port from a reservoir that has more than one. */
export function removePort(project: Project, componentId: string, portId: string): Project {
	const { component } = requireFreePort(project, { componentId, portId });
	if (component.type !== 'reservoir') throw new EditError('Only reservoir ports can be removed.');
	if (component.ports.length <= 1) throw new EditError('A reservoir needs at least one port.');
	return updateComponent(project, componentId, (c) => ({
		...c,
		ports: c.ports.filter((p) => p.id !== portId)
	}));
}

/** Add a pump curve to the project library, or replace the one with the same id. */
export function setPumpCurve(project: Project, curve: PumpCurve): Project {
	const index = project.pumpLibrary.findIndex((c) => c.id === curve.id);
	if (index === -1 && usedIds(project).has(curve.id)) {
		throw new EditError(`The id "${curve.id}" is already used in this project.`);
	}
	const pumpLibrary =
		index === -1 ? [...project.pumpLibrary, curve] : replaceAt(project.pumpLibrary, index, curve);
	return { ...project, pumpLibrary };
}

/** Remove a pump curve that no pump uses. */
export function removePumpCurve(project: Project, curveId: string): Project {
	const user = project.components.find((c) => c.type === 'pump' && c.curveId === curveId);
	if (user) throw new EditError(`Pump "${user.id}" uses this curve.`);
	return { ...project, pumpLibrary: project.pumpLibrary.filter((c) => c.id !== curveId) };
}
