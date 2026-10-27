/**
 * Topology issues from the calculation server, as people read them: every code the solver's
 * builder raises (apps/api solver/builder.py and solver/library.py) is told in the browser with
 * component, port and piping names and with values in the display units, chosen by the issue's
 * code and the ids it lists, never by rewording the server's text. The server's message is kept
 * with each issue told here (`detail`, shown under Details), so nothing it said is lost; any
 * other issue, and any issue whose message is not in the form expected, keeps the server's
 * message as its text. Ids stay where nothing has a name (a component the project does not
 * have, a port a component does not have, a duplicated id). Every issue links to the components
 * it names (and to the open port, for an unconnected one), and an issue about piping links to
 * that piping.
 *
 * Values the server states in its message (a pipe's roughness and inner diameter, a valve's
 * resistance, an equipment item's rating, a controlled pump curve's flow interval or setpoint
 * bound, a pipe library's schedules and sizes) are taken from the message, which states what the
 * server solved, and shown in the display unit; pipes are numbered from 1, as the message and the piping editor
 * number them. Values that the message does not state are taken from the project only when the
 * error is for the project as it is now (`current`).
 *
 * A speed-controlled pump whose curve does not give one speed for each head
 * (CONTROLLED_PUMP_CURVE) is told with its names, and the curve and the flow interval where it
 * fails are taken from the server's message (an issue has no details) and shown in the display
 * unit. So is a flow setpoint that no speed up to the maximum can hold (CONTROLLED_PUMP_SETPOINT),
 * with the curve and the bound the setpoint must stay below taken from the message (shown rounded
 * toward zero, so that every setpoint below the value shown is below it), and the setpoint and
 * maximum speed from the project. The server's message is shown instead when it does
 * not state them in the form expected, when it names another curve than the pump's, or when the
 * error is not for the project as it is now (the pump may have been given another curve since the
 * solve was sent).
 */
import type {
	Component,
	FluidDefinition,
	FluidInfo,
	PipeConnection,
	Project,
	TopologyIssue,
	UnitPreferences
} from '../api/types';
import { componentById, connectionById, freePorts, portById } from './graph';
import { fluidSummary, portLabel, sameSize } from './labels';
import { formatNumber, formatValue, INCH, SI_UNITS } from './units';

export interface IssueLink {
	componentId: string;
	/** Open this port's piping (an unconnected port, a port connected twice, a piping's end). */
	portId?: string;
	/** The link's text when it is not the component's name: a piping's ("Tank → Pump"). */
	label?: string;
}

export interface IssueView {
	text: string;
	links: IssueLink[];
	/** The server's message, when `text` is told in the browser: kept, and shown as a detail. */
	detail?: string;
}

/** What the browser may know besides the project, to name things in an issue. */
export interface IssueTextOptions {
	/** The pipe library's name of a material id (undefined when not loaded or unknown). */
	materialName?: (id: string) => string | undefined;
	/** The pipe library's nominal sizes, for their NPS designations ('2-1/2'), and so that a size
	 * the library lacks is never told as one of them (UNKNOWN_PIPE_SIZE). */
	nominalSizes?: readonly { nominalSize: number; nps: string }[];
}

/** The options from the pipe library (a LibraryStore): material names and NPS designations. */
export function issueTextOptions(library: {
	material(id: string): { name: string } | undefined;
	readonly nominalSizes: readonly { nominalSize: number; nps: string }[];
}): IssueTextOptions {
	return {
		materialName: (id) => library.material(id)?.name,
		nominalSizes: library.nominalSizes
	};
}

/** An id as the server's messages quote it (Identifier: letters, digits, '_' or '-'). */
const ID = '([A-Za-z0-9_-]+)';
/** A number as Python's `:g` and `:.6g` print it (no inf or nan: those are not told here). */
const NUM = '(-?\\d+(?:\\.\\d+)?(?:e[+-]?\\d+)?)';

/**
 * How to show the issues of one topology error. `current`: the error is for the project as it
 * is now (not stale), so its open ports and a controlled pump's curve can be named from it;
 * otherwise those issues keep the server's message. `units` are the display units of values told
 * in the browser (default SI).
 */
export function topologyIssueViews(
	issues: readonly TopologyIssue[],
	project: Project,
	current: boolean,
	units: UnitPreferences = SI_UNITS,
	options: IssueTextOptions = {}
): IssueView[] {
	// Unconnected-port issues name a component, one issue per open port in port order (as the
	// server lists them). They are named only when the counts agree with the project.
	const openPorts = new Map<string, string[]>();
	const counts = new Map<string, number>();
	for (const issue of issues) {
		const id = issue.code === 'UNCONNECTED_PORT' ? issue.componentIds[0] : undefined;
		if (id !== undefined) counts.set(id, (counts.get(id) ?? 0) + 1);
	}
	if (current) {
		for (const [id, n] of counts) {
			const ports = freePorts(project, id).map((p) => p.id);
			if (ports.length === n) openPorts.set(id, ports);
		}
	}
	const context: Context = { project, current, units, options, openPorts };

	return issues.map((issue) => {
		const links: IssueLink[] = issue.componentIds.map((componentId) => ({ componentId }));
		const told = tell(issue, links, context);
		if (!told) return { text: issue.message, links };
		return told.text === issue.message ? told : { ...told, detail: issue.message };
	});
}

interface Context {
	project: Project;
	current: boolean;
	units: UnitPreferences;
	options: IssueTextOptions;
	openPorts: Map<string, string[]>;
}

/** The issue told in the browser, or null to keep the server's message. */
function tell(issue: TopologyIssue, links: IssueLink[], context: Context): IssueView | null {
	const { project, current, units } = context;
	const only = issue.componentIds.length === 1 ? issue.componentIds[0] : undefined;
	const component = only === undefined ? undefined : componentById(project, only);
	switch (issue.code) {
		case 'UNKNOWN_PUMP_CURVE':
			if (component?.type === 'pump') {
				return {
					text: `${component.name} needs a pump curve: enter at least 3 points of its head against flow, or pick a curve from the project's pump library.`,
					links
				};
			}
			return null;
		case 'UNCONNECTED_PORT': {
			const portId = component ? context.openPorts.get(component.id)?.shift() : undefined;
			if (component && portId) {
				return {
					text: `${portLabel(portId)} of ${component.name} is not connected: connect it or add a plug.`,
					links: [{ componentId: component.id, portId }]
				};
			}
			return null;
		}
		case 'CONTROLLED_PUMP_CURVE': {
			const interval = CURVE_INTERVAL.exec(issue.message);
			const named = CURVE_ID.exec(issue.message)?.[1];
			const curve =
				current && component?.type === 'pump' && component.curveId === named
					? project.pumpLibrary.find((c) => c.id === named)
					: undefined;
			if (component && curve && interval) {
				const [low, high] = [Number(interval[1]), Number(interval[2])];
				if (Number.isFinite(low) && Number.isFinite(high)) {
					const from = formatValue(low, 'flow', units, 4, { unit: false });
					return {
						text:
							`${component.name} is speed-controlled, but its pump curve “${curve.name}” does not ` +
							`give one speed for each head: at a fixed flow the head s²·H₀(Q/s) must rise with ` +
							`the speed s, and it does not where 2·H₀(x) − x·H₀′(x) ≤ 0, for rated-speed flows x ` +
							`from ${from} to ${formatValue(high, 'flow', units)}. Use a curve whose head rises ` +
							`less steeply with flow there (2·H₀(x) > x·H₀′(x)), or a fixed speed.`,
						links
					};
				}
			}
			return null;
		}
		case 'CONTROLLED_PUMP_SETPOINT': {
			const bound = Number(SETPOINT_BOUND.exec(issue.message)?.[1]);
			const named = SETPOINT_CURVE_ID.exec(issue.message)?.[1];
			const pump = component?.type === 'pump' ? component : undefined;
			const curve =
				current && pump?.control && pump.curveId === named
					? project.pumpLibrary.find((c) => c.id === named)
					: undefined;
			if (pump?.control && curve && Number.isFinite(bound)) {
				return {
					text:
						`${pump.name} is speed-controlled to hold ` +
						`${formatValue(pump.control.setpoint, 'flow', units)}, but no speed up to its ` +
						`maximum speed (${formatValue(pump.speed, 'fraction', units)}) can hold that flow ` +
						`on its pump curve “${curve.name}”: at that flow the head s²·H₀(Q/s) falls as the ` +
						`speed s rises, at every speed, because Q/s lies beyond x_mono, twice the flow at ` +
						`which the curve's end tangent reaches zero head. Use a setpoint below ` +
						`${formatValue(bound, 'flow', units, 4, { towardZero: true })} (the maximum ` +
						`speed × x_mono), or a curve that extends to higher flows.`,
					links
				};
			}
			return null;
		}
		case 'NO_FIXED_HEAD': {
			// An assigned-flow node in the part fixes a flow, not a pressure (SDD §4.11): say
			// that it does not count, so it is not taken for the boundary the part lacks.
			const assigned = issue.componentIds.some(
				(id) => componentById(project, id)?.type === 'assigned_flow'
			);
			return {
				text: issue.componentIds.length
					? 'This part of the network has no fixed-pressure boundary: add a reservoir or reference node to it.' +
						(assigned
							? ' Assigned-flow nodes fix a flow, not a pressure, so they do not count as one.'
							: '')
					: 'The network is empty: add a reservoir or reference node and connect it.',
				links
			};
		}
		case 'DUPLICATE_COMPONENT_ID': {
			const id = idOf(issue.message, DUPLICATE_COMPONENT, only);
			if (id === null) return null;
			const names = project.components.filter((c) => c.id === id).map((c) => c.name);
			return {
				text: `More than one component has the id “${id}”${current ? listed(names) : ''}: every component needs its own id.`,
				links
			};
		}
		case 'DUPLICATE_CONNECTION_ID': {
			const id = idOf(issue.message, DUPLICATE_CONNECTION, single(issue.connectionIds));
			if (id === null) return null;
			const pipings = project.connections.filter((c) => c.id === id);
			return {
				text: `More than one pipe connection has the id “${id}”${current ? listed(pipings.map((c) => pipingName(project, c))) : ''}: every pipe connection needs its own id.`,
				links: [...links, ...pipings.flatMap((c) => pipingLink(project, c))]
			};
		}
		case 'DUPLICATE_ID': {
			const id = idOf(issue.message, DUPLICATE_ELEMENT, only);
			if (id === null || single(issue.connectionIds) !== id) return null;
			const connection = connectionById(project, id);
			const what = [
				`a component${component ? ` (${component.name})` : ''}`,
				`a pipe connection${connection ? ` (${pipingName(project, connection)})` : ''}`
			];
			return {
				text: `The id “${id}” names both ${what.join(' and ')}: every element needs its own id.`,
				links: [...links, ...(connection ? pipingLink(project, connection) : [])]
			};
		}
		case 'DUPLICATE_PUMP_CURVE_ID': {
			const id = idOf(issue.message, DUPLICATE_CURVE, undefined);
			if (id === null) return null;
			const names = project.pumpLibrary.filter((c) => c.id === id).map((c) => `“${c.name}”`);
			return {
				text: `More than one pump curve in the project's pump library has the id “${id}”${current ? listed(names) : ''}: every pump curve needs its own id.`,
				links
			};
		}
		case 'UNKNOWN_COMPONENT': {
			const match = UNKNOWN_COMPONENT.exec(issue.message);
			const connection = pipingOf(project, issue, match?.[1]);
			if (!match || !connection) return null;
			const [, , end, componentId] = match;
			const known = end === 'from' ? 'to' : 'from';
			return {
				text: `Piping ${pipingName(project, connection)} ${end === 'from' ? 'starts' : 'ends'} at component “${componentId}”, which the project does not have.`,
				links: [...links, ...pipingLink(project, connection, known)]
			};
		}
		case 'UNKNOWN_PORT': {
			const match = UNKNOWN_PORT.exec(issue.message);
			const connection = pipingOf(project, issue, match?.[1]);
			if (!match || !connection || match[4] !== only || !component) return null;
			const [, , end, portId] = match;
			const ports = component.ports.map((p) => portLabel(p.id));
			return {
				text:
					`Piping ${pipingName(project, connection)} ${end === 'from' ? 'starts' : 'ends'} at a port “${portId}” of ` +
					`${component.name}, which has no such port${current && ports.length ? ` (its ports: ${ports.join(', ')})` : ''}.`,
				links
			};
		}
		case 'SELF_CONNECTION': {
			const match = SELF_CONNECTION.exec(issue.message);
			const connection = pipingOf(project, issue, match?.[1]);
			if (!match || !connection || match[2] !== only || !component) return null;
			const portId = match[3] ?? '';
			return {
				text: `${portLabel(portId)} of ${component.name} is connected to itself (piping ${pipingName(project, connection)}): a pipe connection joins two different ports.`,
				links: portById(component, portId) ? [{ componentId: component.id, portId }] : links
			};
		}
		case 'PORT_CONNECTED_TWICE': {
			const match = PORT_CONNECTED_TWICE.exec(issue.message);
			if (!match || match[1] !== only || !component) return null;
			const [, , portId = '', count] = match;
			const pipings = issue.connectionIds.map((id) => {
				const connection = connectionById(project, id);
				return connection ? pipingName(project, connection) : `“${id}”`;
			});
			return {
				text:
					`${portLabel(portId)} of ${component.name} has ${count} pipe connections${listed(pipings)}: ` +
					'a port takes exactly one. To branch the flow, use a tee or wye.',
				links: portById(component, portId) ? [{ componentId: component.id, portId }] : links
			};
		}
		case 'UNKNOWN_PIPE_MATERIAL':
		case 'UNKNOWN_PIPE_SCHEDULE':
		case 'UNKNOWN_PIPE_SIZE':
		case 'ROUGHNESS_OUT_OF_RANGE':
		case 'PIPE_SIZE_OUT_OF_RANGE':
			return pipeIssue(issue, links, context);
		case 'EQUIPMENT_RATING_OUT_OF_RANGE': {
			const match = EQUIPMENT_RATING.exec(issue.message);
			if (!match || match[1] !== only || !component) return null;
			const [, , loss, flow, density, kind, value] = match;
			const rating =
				kind !== undefined
					? `a ${kind} of ${formatNumber(Number(value), 6)}`
					: `a rated pressure drop of ${formatValue(Number(loss), 'pressure', units, 6)} at ${formatValue(Number(flow), 'flow', units, 6)} for a fluid of ${formatValue(Number(density), 'density', units, 6)}`;
			return {
				text:
					`${component.name}: ${rating} gives a loss coefficient that is not a finite positive ` +
					'floating-point number, so the solver cannot represent this element. Check its rating.',
				links
			};
		}
		case 'VALVE_RESISTANCE_OUT_OF_RANGE': {
			const match = VALVE_RESISTANCE.exec(issue.message);
			if (!match || match[1] !== only || !component) return null;
			const [, , kind, value = '', diameter = ''] = match;
			return {
				text:
					`${component.name}: a ${kind} of ${formatNumber(Number(value), 6)} on its inlet pipe's inner ` +
					`diameter (${formatValue(Number(diameter), 'diameter', units)}) gives a loss coefficient ` +
					'that is not a finite floating-point number, so the solver cannot represent this valve. ' +
					'Check its resistance.',
				links
			};
		}
	}
	return null;
}

/** An issue about one pipe of a piping ("connection 'L1' pipe 2: ..."), told with its names. */
function pipeIssue(issue: TopologyIssue, links: IssueLink[], context: Context): IssueView | null {
	const { project, units, options } = context;
	const head = PIPE_PREFIX.exec(issue.message);
	const connection = pipingOf(project, issue, head?.[1]);
	if (!head || !connection) return null;
	const [, , number, rest = ''] = head;
	const where = `Piping ${pipingName(project, connection)}, pipe ${number}`;
	const material = (id: string) => options.materialName?.(id) ?? `material “${id}”`;
	let text: string | null = null;
	switch (issue.code) {
		case 'UNKNOWN_PIPE_MATERIAL': {
			const match = UNKNOWN_MATERIAL.exec(rest);
			if (match)
				text = `${where}: the pipe library has no material “${match[1]}”: choose a material from the library, or enter a custom pipe.`;
			break;
		}
		case 'UNKNOWN_PIPE_SCHEDULE': {
			const match = UNKNOWN_SCHEDULE.exec(rest);
			if (match) {
				const [, id = '', schedule] = match;
				text = `${where}: the pipe library has no schedule “${schedule}” for ${material(id)}: choose one of its schedules, or enter a custom pipe.`;
			}
			break;
		}
		case 'UNKNOWN_PIPE_SIZE': {
			const match = UNKNOWN_SIZE.exec(rest);
			const [, id = '', schedule, metres = '', inches = '', available = ''] = match ?? [];
			const nps = match && missingNps(metres, inches, available, options.nominalSizes ?? []);
			if (nps)
				text = `${where}: the pipe library has no ${nps} in schedule ${schedule} of ${material(id)}: choose one of its sizes, or enter a custom pipe.`;
			break;
		}
		case 'ROUGHNESS_OUT_OF_RANGE': {
			const match = ROUGHNESS.exec(rest);
			if (match) {
				const [, roughness = '', ratio = '', diameter = '', limit = ''] = match;
				text =
					`${where}: its roughness (${formatValue(Number(roughness), 'diameter', units)}) is ` +
					`${formatNumber(Number(ratio), 4)} times its inner diameter ` +
					`(${formatValue(Number(diameter), 'diameter', units)}), and the Colebrook equation has ` +
					`no solution for a relative roughness (roughness ÷ inner diameter) of ` +
					`${formatNumber(Number(limit), 6)} or more. Use a smaller roughness or a larger inner ` +
					'diameter.';
			}
			break;
		}
		case 'PIPE_SIZE_OUT_OF_RANGE': {
			const match = PIPE_SIZE.exec(rest);
			if (match) {
				const [, diameter = '', length = ''] = match;
				text =
					`${where}: an inner diameter of ${formatValue(Number(diameter), 'diameter', units)} and ` +
					`a length of ${formatValue(Number(length), 'length', units)} give a pipe resistance ` +
					'that is not a finite floating-point number, so the solver cannot represent this ' +
					'pipe. Check its inner diameter and length.';
			}
			break;
		}
	}
	return text === null ? null : { text, links: [...links, ...pipingLink(project, connection)] };
}

/** The issue's one connection, when the message names it and the project has it. */
function pipingOf(
	project: Project,
	issue: TopologyIssue,
	named: string | undefined
): PipeConnection | undefined {
	const id = single(issue.connectionIds);
	return id !== undefined && id === named ? connectionById(project, id) : undefined;
}

/** "Tank → Pump": the names of a piping's ends (an id where the project has no such component). */
function pipingName(project: Project, connection: PipeConnection): string {
	const name = (id: string) => componentById(project, id)?.name ?? `“${id}”`;
	return `${name(connection.fromComponentId)} → ${name(connection.toComponentId)}`;
}

/**
 * A link that opens the piping at one of its ends (`end`, else whichever end the project has):
 * none when neither end is a port of a component of the project.
 */
function pipingLink(
	project: Project,
	connection: PipeConnection,
	end?: 'from' | 'to'
): IssueLink[] {
	const ends = (end ? [end] : (['from', 'to'] as const)).map((e) =>
		e === 'from'
			? { componentId: connection.fromComponentId, portId: connection.fromPortId }
			: { componentId: connection.toComponentId, portId: connection.toPortId }
	);
	const at = ends.find(({ componentId, portId }) => {
		const owner: Component | undefined = componentById(project, componentId);
		return owner !== undefined && portById(owner, portId) !== undefined;
	});
	return at ? [{ ...at, label: pipingName(project, connection) }] : [];
}

/** The one element of a list, or undefined. */
function single(ids: readonly string[]): string | undefined {
	return ids.length === 1 ? ids[0] : undefined;
}

/** The id a message names (`pattern`'s first group), checked against the issue's own id. */
function idOf(message: string, pattern: RegExp, own: string | undefined): string | null {
	const id = pattern.exec(message)?.[1];
	if (id === undefined || (own !== undefined && id !== own)) return null;
	return id;
}

/** " (A, B and C)" for two or more names; nothing for fewer (they no longer say more). */
function listed(names: readonly string[]): string {
	return names.length < 2 ? '' : ` (${andList(names)})`;
}

/** "A", "A and B", "A, B and C". */
function andList(items: readonly string[]): string {
	return items.length < 2
		? (items[0] ?? '')
		: `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

// The server's messages (apps/api solver/builder.py, solver/library.py), anchored at both ends:
// an issue told here states exactly what the server's message states.
const DUPLICATE_COMPONENT = new RegExp(`^component id '${ID}' is used more than once$`);
const DUPLICATE_CONNECTION = new RegExp(`^connection id '${ID}' is used more than once$`);
const DUPLICATE_ELEMENT = new RegExp(
	`^id '${ID}' names both a component and a connection; every element needs its own id$`
);
const DUPLICATE_CURVE = new RegExp(`^pump curve id '${ID}' is used more than once$`);
const UNKNOWN_COMPONENT = new RegExp(
	`^connection '${ID}' \\((from|to) end\\) refers to unknown component '${ID}'$`
);
const UNKNOWN_PORT = new RegExp(
	`^connection '${ID}' \\((from|to) end\\) refers to port '${ID}', which component '${ID}' does not have$`
);
const SELF_CONNECTION = new RegExp(`^connection '${ID}' connects port '${ID}:${ID}' to itself$`);
const PORT_CONNECTED_TWICE = new RegExp(
	`^port '${ID}:${ID}' has (\\d+) connections; a port takes exactly one$`
);
const VALVE_RESISTANCE = new RegExp(
	`^valve '${ID}': a (K|Cv|Kv) of ${NUM} on the inlet pipe's inner diameter of ${NUM} m gives a ` +
		'loss coefficient that is not a finite floating-point number; the solver cannot represent ' +
		'this valve$'
);
/**
 * An equipment item whose rating gives no representable loss coefficient (the builder's
 * _unrepresentable_equipment): its rating as the server solved it, SI (services/solver/equipment.py
 * rating_text: "50000 Pa at 0.015 m³/s for a fluid of 999.1 kg/m³", or "Cv 90").
 */
const EQUIPMENT_RATING = new RegExp(
	`^equipment '${ID}': a rating of (?:${NUM} Pa at ${NUM} m³/s for a fluid of ${NUM} kg/m³|(Cv|Kv) ${NUM}) ` +
		'gives a loss coefficient, .*, that is not a finite positive floating-point number; the ' +
		'solver cannot represent this element$',
	's'
);
/** "connection 'L1' pipe 2: <the pipe's problem>" (pipes numbered from 1). */
const PIPE_PREFIX = new RegExp(`^connection '${ID}' pipe (\\d+): (.*)$`, 's');
/** Material ids and schedules are free text up to a quote; the lists that end the messages are
 * the library's (the piping editor offers them), kept in the server's message. */
const UNKNOWN_MATERIAL = /^unknown pipe material '([^']*)'; available: [^']*$/;
const UNKNOWN_SCHEDULE = /^pipe material '([^']*)' has no schedule '([^']*)'; available: ([^']*)$/;
const UNKNOWN_SIZE = new RegExp(
	`^pipe material '([^']*)' schedule '([^']*)' has no nominal size ${NUM} m \\(NPS ${NUM} in\\); available NPS: ([^']*)$`
);
const ROUGHNESS = new RegExp(
	`^roughness ${NUM} m is ${NUM} times the inner diameter ${NUM} m; the Colebrook equation has ` +
		`no solution for relative roughness of ${NUM} or more$`
);
const PIPE_SIZE = new RegExp(
	`^an inner diameter of ${NUM} m and a length of ${NUM} m give a pipe resistance that is not a ` +
		'finite floating-point number; the solver cannot represent this pipe$'
);

/**
 * The nominal size an UNKNOWN_PIPE_SIZE message says its schedule lacks, as NPS, from the
 * message's own figures (`metres`, `inches`: the size as Python's `:g` prints it, 6 significant
 * digits) and the schedule's sizes it lists (`available`, NPS in inches). The library's
 * designation where the size is one of the library's (of another schedule, as the schedule does
 * not list it); otherwise the size in inches, from the metre figure and then the inch figure,
 * with as many significant digits (4 to 7) as it takes to differ, at that precision, from every
 * size the schedule lists and every size of the library, so the text never names a size the
 * library has. Null, to keep the server's message, when neither figure can be told from a listed
 * size (a size of 1 m or more that the message rounds onto one) or the list is not of numbers.
 */
function missingNps(
	metres: string,
	inches: string,
	available: string,
	sizes: readonly { nominalSize: number; nps: string }[]
): string | null {
	const listed = available.split(', ').map(Number);
	if (listed.some((n) => !Number.isFinite(n))) return null;
	const size = Number(metres);
	const exact = sizes.find((s) => sameSize(s.nominalSize, size));
	if (exact && !listed.some((n) => sameSize(n * INCH, exact.nominalSize)))
		return `NPS ${exact.nps}`;
	const known = [...listed, ...sizes.map((s) => s.nominalSize / INCH)];
	for (const figure of [size / INCH, Number(inches)]) {
		for (let digits = 4; digits <= 7; digits++) {
			const text = formatNumber(figure, digits);
			if (known.every((n) => formatNumber(n, digits) !== text)) return `NPS ${text}`;
		}
	}
	return null;
}

/** The curve (its id) that the server's CONTROLLED_PUMP_CURVE message names. */
const CURVE_ID = /is speed-controlled, but its curve '([A-Za-z0-9_-]+)'/;

/** The flow interval (m³/s) in the server's CONTROLLED_PUMP_CURVE message. */
const CURVE_INTERVAL =
	/flows x from (-?\d+(?:\.\d+)?(?:e[+-]?\d+)?) to (-?\d+(?:\.\d+)?(?:e[+-]?\d+)?) m³\/s/;

/** The curve (its id) that the server's CONTROLLED_PUMP_SETPOINT message names. */
const SETPOINT_CURVE_ID = /can hold it on its curve '([A-Za-z0-9_-]+)'/;

/**
 * The bound (m³/s) the setpoint must stay below, at the end of the server's
 * CONTROLLED_PUMP_SETPOINT message (anchored there: the curve's name, earlier in it, is free text).
 */
const SETPOINT_BOUND =
	/setpoints must be below (-?\d+(?:\.\d+)?(?:e[+-]?\d+)?) m³\/s \(the maximum speed × x_mono\), so use a smaller setpoint or a curve that extends to higher flows$/;

/** "1 problem to fix before the network can be solved:" (pluralized). */
export function topologySummary(count: number): string {
	return `${count} problem${count === 1 ? '' : 's'} to fix before the network can be solved:`;
}

/**
 * The fluid error of a glycol solution with no concentration, told in the display unit
 * (percent by mass) with the library's range when known; null when that is not the case (the
 * server's message is shown as it is).
 */
export function missingConcentrationText(
	fluid: FluidDefinition,
	info: FluidInfo | undefined,
	units: UnitPreferences
): string | null {
	if (fluid.kind !== 'builtin' || fluid.fluidId === 'water' || fluid.concentration != null) {
		return null;
	}
	const name = info?.name ?? fluidSummary(fluid);
	const range = concentrationRangeText(info, units);
	return `${name} needs a glycol concentration: enter it in Settings, as a percentage by mass${range ? ` (${range})` : ''}.`;
}

/** The fluid library's concentration range in the display unit ("0 to 60 %"), if it has one. */
export function concentrationRangeText(
	info: FluidInfo | undefined,
	units: UnitPreferences
): string | null {
	const range = info?.concentrationRange;
	if (!range) return null;
	return `${formatValue(range.min, 'fraction', units, 4, { unit: false })} to ${formatValue(range.max, 'fraction', units)}`;
}
