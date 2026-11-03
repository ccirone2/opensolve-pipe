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
 * resistance, an equipment item's rating, an orifice plate's bore, pipe bore, β and the bound its
 * discharge coefficient breaks, a relief valve's set pressure, capacity and overpressure, a
 * controlled pump curve's flow interval or setpoint bound, a pipe
 * library's schedules and sizes) are taken from the message, which states what the
 * server solved, and shown in the display unit; pipes are numbered from 1, as the message and the piping editor
 * number them. Values that the message does not state are taken from the project only when the
 * error is for the project as it is now (`current`).
 *
 * A reference to a project library entry the project does not have (UNKNOWN_PIPE_SPEC,
 * UNKNOWN_RESISTANCE), and an entry whose coefficient the solver cannot represent on an element's
 * bore (VALVE_RESISTANCE_OUT_OF_RANGE, FITTING_RESISTANCE_OUT_OF_RANGE), are told with the
 * element's names and the entry's name from the project (CLAUDE.md D22); the server's messages
 * name entries by id only.
 *
 * A valve, a fitting on an entry, a piping's fittings, an equipment item or an orifice plate
 * whose loss coefficient c is finite but above half the largest floating-point number is refused
 * under the same codes in a form of its own (the builder's coefficients.slope_bound_text): the
 * law's slope, formed as (2c)|Q|, is then not a finite number at any flow. It is told with the
 * names, the element's values in display units, and c and the bound as the message quotes them
 * (SI, s²/m⁵ or, for a plate's K, none: they have no display unit), each with the digits that
 * tell them apart (at least the message's 6), so c never reads as the bound.
 *
 * A pipe or an orifice plate whose Reynolds-number arithmetic the fluid, at the schema's bounds,
 * makes unrepresentable is refused under the same codes (PIPE_SIZE_OUT_OF_RANGE's A ν form, the
 * builder's _unrepresentable_pipes; ORIFICE_OUT_OF_RANGE's rule (e), _ORIFICE_FLUID_TAILS). It is
 * told with the names and links, the bores in the display unit, the kinematic viscosity as the
 * message quotes it (m²/s: it has no display unit), and the density and dynamic viscosity in
 * theirs where they are normal floating-point numbers there; otherwise as quoted, in kg/m³ and
 * Pa·s (a density near the smallest double is 0 in lb/ft³), so no value is shown that the message
 * does not state.
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
import { fittingFallbackName, fluidSummary, portLabel, sameSize } from './labels';
import { pipeSpecOf, resistanceEntryOf } from './project-library';
import { displayUnit, formatNumber, formatValue, fromSI, INCH, SI_UNITS } from './units';

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
			const slope = EQUIPMENT_SLOPE.exec(issue.message);
			const match = slope ?? EQUIPMENT_RATING.exec(issue.message);
			if (!match || match[1] !== only || !component) return null;
			const [, , loss, flow, density, kind, value, c = '', max = ''] = match;
			const rating =
				kind !== undefined
					? `a ${kind} of ${formatNumber(Number(value), 6)}`
					: `a rated pressure drop of ${formatValue(Number(loss), 'pressure', units, 6)} at ${formatValue(Number(flow), 'flow', units, 6)} for a fluid of ${formatValue(Number(density), 'density', units, 6)}`;
			if (slope) {
				const words = slopeWords('c', c, max, PER_FLOW_SQUARED, 'its head loss, 2c|Q|');
				if (words === null) return null;
				return {
					text: `${component.name}: ${rating} gives ${words} and the solver cannot represent this element. Check its rating.`,
					links
				};
			}
			return {
				text:
					`${component.name}: ${rating} gives a loss coefficient that is not a finite positive ` +
					'floating-point number, so the solver cannot represent this element. Check its rating.',
				links
			};
		}
		case 'ORIFICE_OUT_OF_RANGE':
			return orificeIssue(issue, links, component, only, units);
		case 'RELIEF_VALVE_OUT_OF_RANGE':
			return reliefIssue(issue, links, component, only, units);
		case 'UNKNOWN_PIPE_SPEC':
		case 'UNKNOWN_RESISTANCE':
		case 'FITTING_RESISTANCE_OUT_OF_RANGE':
			return libraryIssue(issue, links, context, component, only);
		case 'VALVE_RESISTANCE_OUT_OF_RANGE': {
			const entrySlope = VALVE_ENTRY_SLOPE.exec(issue.message);
			const entry = entrySlope ?? VALVE_ENTRY.exec(issue.message);
			if (entry) {
				if (entry[1] !== only || !component) return null;
				const [, , id = '', kind = '', value = '', bore, diameter = '', c = '', max = ''] = entry;
				const words = entrySlope
					? slopeWords('K/(2 g A²)', c, max, PER_FLOW_SQUARED, VALVE_SLOPE_WORDS)
					: 'a loss coefficient that is not a finite positive floating-point number,';
				if (words === null) return null;
				return {
					text:
						`${component.name}: its project library entry ${entryWords(project, id)} ` +
						`(${coefficientWords(kind, value, bore, units)}) on its inlet pipe's inner diameter ` +
						`(${formatValue(Number(diameter), 'diameter', units)}) gives ${words} ` +
						`${entrySlope ? 'and' : 'so'} the solver cannot represent this valve. Check the entry.`,
					links
				};
			}
			const slope = VALVE_RESISTANCE_SLOPE.exec(issue.message);
			const match = slope ?? VALVE_RESISTANCE.exec(issue.message);
			if (!match || match[1] !== only || !component) return null;
			const [, , kind, value = '', diameter = '', c = '', max = ''] = match;
			const words = slope
				? slopeWords('K/(2 g A²)', c, max, PER_FLOW_SQUARED, VALVE_SLOPE_WORDS)
				: 'a loss coefficient that is not a finite floating-point number,';
			if (words === null) return null;
			return {
				text:
					`${component.name}: a ${kind} of ${formatNumber(Number(value), 6)} on its inlet pipe's inner ` +
					`diameter (${formatValue(Number(diameter), 'diameter', units)}) gives ${words} ` +
					`${slope ? 'and' : 'so'} the solver cannot represent this valve. Check its resistance.`,
				links
			};
		}
	}
	return null;
}

/**
 * An orifice plate the solver cannot represent (ORIFICE_OUT_OF_RANGE, the builder's
 * _unrepresentable_orifices, proposal orifice-plate.md decision 17), told with its name and the
 * message's bore, pipe bore, β and the bound its discharge coefficient breaks, in display units,
 * or its K above the slope bound (rule 'slope'), or the fluid that makes its Reynolds-number
 * arithmetic unrepresentable (rule (e), `orificeFluidWords`); null (the server's message) when the
 * message is not in a form expected.
 */
function orificeIssue(
	issue: TopologyIssue,
	links: IssueLink[],
	component: Component | undefined,
	only: string | undefined,
	units: UnitPreferences
): IssueView | null {
	const head = ORIFICE_HEAD.exec(issue.message);
	if (!head || head[1] !== only || !component) return null;
	const [, , bore = '', pipe = '', beta = '', rest = ''] = head;
	const d = formatValue(Number(bore), 'diameter', units);
	const D = formatValue(Number(pipe), 'diameter', units);
	const b = formatNumber(Number(beta), 6);
	const name = component.name;
	const fluid = orificeFluidWords(rest, units);
	let text: string | null = null;
	if (fluid) {
		text =
			`${name} (a bore of ${d} in an inlet pipe of inner diameter ${D}, β = ${b}): ${fluid[0]}, ` +
			`so the solver cannot represent this plate. ${fluid[1]}`;
	} else if (ORIFICE_BETA.test(rest)) {
		text =
			`${name}'s bore (${d}) is not smaller than its inlet pipe's inner diameter (${D}): an ` +
			'orifice plate needs β = d ÷ D below 1. Use a smaller bore.';
	} else {
		const iso = ORIFICE_ISO.exec(rest);
		const moved = ORIFICE_MOVED.exec(rest);
		const unbounded = ORIFICE_UNBOUNDED.test(rest);
		const loss = ORIFICE_LOSS.exec(rest);
		const slope = ORIFICE_SLOPE.exec(rest);
		if (slope) {
			const [, high = '', k = '', max = ''] = slope;
			const words = slopeWords('K', k, max, '', 'its head loss, 2 K|Q|/(2 g A²)', true, true);
			if (words !== null) {
				text =
					`${name}: a bore of ${d} in an inlet pipe of inner diameter ${D} (β = ${b}) gives, with ` +
					`a discharge coefficient of at most ${formatNumber(Number(high), 6)} at every flow, ${words} and the ` +
					'solver cannot represent this plate. Check its bore and discharge coefficient.';
			}
		} else if (iso) {
			const [, where = '', use = '', entered = '', from = '', coefficient = '', tail = ''] = iso;
			const start =
				`${name}'s bore (${d}) is so close to its inlet pipe's inner diameter (${D}, β = ${b}) ` +
				`that ISO 5167-2's discharge coefficient at ${where}`;
			const up = `could exceed 1 (up to ${formatNumber(Number(coefficient), 6)})`;
			const lossTail = ORIFICE_ISO_LOSS.exec(tail);
			if (use === "which sets the plate's loss" && lossTail) {
				const taps = lossTail[1];
				text =
					`${start}, which sets the plate's loss, ${up}: a jet larger than the bore, which is ` +
					'physically impossible. ' +
					(taps === undefined
						? "Use a smaller bore, or enter a discharge coefficient (ISO 5167-2's C at D and D/2 " +
							'tappings, used as entered).'
						: `Use a smaller bore: an entered discharge coefficient at its ${taps} would be moved ` +
							"to D and D/2 tappings by ISO 5167-2's ratio, which uses this coefficient, and " +
							'refused the same way.');
			} else if (use === "which gives only the meter's reading" && ORIFICE_ISO_READING.test(tail)) {
				text =
					`${start}, which gives only the meter's reading, ${up}: the correlation would be ` +
					"extrapolated far beyond ISO 5167-2's range, so the reading at these taps has no " +
					"basis (the plate's loss uses the coefficient at D and D/2 tappings, which stays at or " +
					'below 1). Use a smaller bore, D and D/2 taps, or no taps (a restriction orifice, with ' +
					'no reading).';
			} else if (entered !== '' && ORIFICE_ISO_MOVE.test(tail)) {
				text =
					`${start}, one of the two in the ratio that moves its entered discharge coefficient ` +
					`${formatNumber(Number(entered), 6)} from its ${from} to D and D/2 tappings, ${up}: ` +
					"the correlation would be extrapolated far beyond ISO 5167-2's range, so the move has " +
					'no basis at this plate. Use a smaller bore, or give the discharge coefficient at D and ' +
					'D/2 tappings (with D and D/2 taps, or no taps), where it is used as entered.';
			}
		} else if (moved) {
			const [, entered = '', taps = '', ratio = '', coefficient = ''] = moved;
			text =
				`${name}: its entered discharge coefficient ${formatNumber(Number(entered), 6)} at its ` +
				`${taps}, moved to D and D/2 tappings by ISO 5167-2's ratio of the two tap sets' ` +
				`coefficients (up to ${formatNumber(Number(ratio), 6)} at a bore of ${d} in an inlet ` +
				`pipe of ${D}), could reach ${formatNumber(Number(coefficient), 6)}, above 1: a jet ` +
				'larger than the bore, which is physically impossible. Check the entered coefficient: ' +
				"ISO 5167-2's C at the plate's taps, not the flow coefficient C ÷ √(1 − β⁴).";
		} else if (unbounded || loss) {
			const low = loss ? ` down to ${formatNumber(Number(loss[1]), 6)}` : '';
			text =
				`${name}: a bore of ${d} in an inlet pipe of inner diameter ${D} (β = ${b}) gives ` +
				(unbounded
					? 'an ISO 5167-2 discharge coefficient that cannot be bounded'
					: `a loss coefficient, with a discharge coefficient${low}, that is not a finite positive floating-point number`) +
				', so the solver cannot represent this plate. Check its bore and discharge coefficient.';
		}
	}
	return text === null ? null : { text, links };
}

/**
 * Rule (e) (the builder's _ORIFICE_FLUID_TAILS, orifice.fluid_refusal): what the case's fluid
 * makes unrepresentable at the plate, with ρ and μ as the message quotes them (`propertyText`),
 * and the remedy; null when `rest` (the message after its head) is not one of its forms.
 */
function orificeFluidWords(rest: string, units: UnitPreferences): [string, string] | null {
	const rho = (value: string) => propertyText(value, 'density', units);
	const mu = (value: string) => propertyText(value, 'viscosity', units);
	const both = "Check the fluid's density and viscosity.";
	const denominator = ORIFICE_FLUID_DENOMINATOR.exec(rest);
	if (denominator) {
		return [
			`with the fluid's dynamic viscosity of ${mu(denominator[1] ?? '')}, the denominator π D μ ` +
				'of its Reynolds number Re_D = 4ρ|Q|/(π D μ) is 0 in floating point (it underflows)',
			"Check the fluid's viscosity."
		];
	}
	const area = ORIFICE_FLUID_AREA.exec(rest);
	if (area) {
		return [
			"ISO 5167-2's discharge coefficient is evaluated from the mass flow, dividing by the " +
				"pipe's area times the fluid's density, (π D²/4) ρ, which with a density of " +
				`${rho(area[1] ?? '')} is 0 in floating point (it underflows)`,
			"Check the fluid's density."
		];
	}
	const infinite = ORIFICE_FLUID_INFINITE.exec(rest);
	if (infinite) {
		const [, density = '', viscosity = ''] = infinite;
		return [
			`with the fluid's density of ${rho(density)} and dynamic viscosity of ${mu(viscosity)}, ` +
				'its Reynolds number per unit flow, 4ρ/(π D μ), is not a finite floating-point ' +
				"number: Re_D is infinite at every flow but zero, where ISO 5167-2's discharge " +
				'coefficient cannot be evaluated',
			both
		];
	}
	const low = ORIFICE_FLUID_RE_LO.exec(rest);
	if (low) {
		const [, density = '', viscosity = ''] = low;
		return [
			`with the fluid's density of ${rho(density)} and dynamic viscosity of ${mu(viscosity)}, ` +
				"ISO 5167-2's discharge coefficient cannot be evaluated at the plate's lowest Reynolds " +
				'number',
			both
		];
	}
	return null;
}

/** The smallest positive normal double, 2⁻¹⁰²²: below it a double has lost significant digits. */
const MIN_NORMAL = 2 ** -1022;

/**
 * A fluid's density or dynamic viscosity as a message quotes it (SI: kg/m³, Pa·s), in the display
 * unit; as quoted, in SI with the message's 6 significant digits, where its value in the display
 * unit is not a normal floating-point number (a density near the smallest double is 0 in lb/ft³,
 * and a subnormal keeps fewer digits than are shown), so no value is shown that the message does
 * not state.
 */
function propertyText(
	value: string,
	category: 'density' | 'viscosity',
	units: UnitPreferences
): string {
	const si = Number(value);
	if (Math.abs(fromSI(si, displayUnit(category, units))) >= MIN_NORMAL)
		return formatValue(si, category, units);
	return formatValue(si, category, { ...units, density: 'kg/m3', viscosity: 'Pa.s' }, 6);
}

/**
 * A relief valve the solver refuses (RELIEF_VALVE_OUT_OF_RANGE, the builder's
 * _unrepresentable_relief_valves, proposal pressure-relief-valve.md decision 14), told with its
 * name and the message's values in display units: a set below ASME VIII's scope where the
 * overpressure would be ASME's default, with the remedy the message gives; or a capacity the
 * floating point cannot represent. Null (the server's message) when the message is not in a form
 * expected.
 */
function reliefIssue(
	issue: TopologyIssue,
	links: IssueLink[],
	component: Component | undefined,
	only: string | undefined,
	units: UnitPreferences
): IssueView | null {
	const scope = RELIEF_SCOPE.exec(issue.message);
	if (scope) {
		const [, id, set = '', psi = '', bound = '', remedy = ''] = scope;
		if (id !== only || !component) return null;
		const told = RELIEF_REMEDIES[remedy];
		if (!told) return null;
		// The scope as the message states it, in psi, and in the display unit unless that is psi.
		const scopeText =
			displayUnit('pressure', units) === 'psi'
				? `${formatNumber(Number(psi), 6)} psi`
				: `${formatNumber(Number(psi), 6)} psi (${formatValue(Number(bound), 'pressure', units, 6)})`;
		return {
			text:
				`${component.name}: its set pressure (${formatValue(Number(set), 'pressure', units, 6)}) is ` +
				`below ASME VIII's scope, ${scopeText}: ` +
				"below it no cited source gives its overpressure at full lift (ASME's default, 10 % or 3 " +
				"psi, is for sets within that scope), and API 520's effective coefficient of discharge " +
				`applies to valves certified within it. ${told}`,
			links
		};
	}
	const law = RELIEF_LAW.exec(issue.message);
	if (!law || law[1] !== only || !component) return null;
	const [, , words = '', c = '', set = '', op = ''] = law;
	const capacity = reliefCapacityWords(words, units);
	if (capacity === null) return null;
	const overpressure = op === 'nan' ? 'none' : formatValue(Number(op), 'fraction', units, 6);
	return {
		text:
			`${component.name}: ${capacity}, C = Kd·A = ${formatValue(Number(c), 'area', units, 6)}, with a ` +
			`set pressure of ${formatValue(Number(set), 'pressure', units, 6)} and an overpressure of ` +
			`${overpressure} gives a capacity, a full-lift flow or a band coefficient that is not a ` +
			'finite positive floating-point number, so the solver cannot represent this valve. Check ' +
			'its set pressure and capacity.',
		links
	};
}

/** The capacity the refusal quotes ("API 526 letter J (0.00083 m²)"), in display units, or null. */
function reliefCapacityWords(words: string, units: UnitPreferences): string | null {
	const area = (v: string) => formatValue(Number(v), 'area', units, 6);
	const letter = new RegExp(`^API 526 letter ([A-Z]) \\(${NUM} m²\\)$`).exec(words);
	if (letter) return `API 526 letter ${letter[1]} (${area(letter[2] ?? '')})`;
	const effective = new RegExp(`^an API 520 effective area of ${NUM} m²$`).exec(words);
	if (effective) return `an API 520 effective area of ${area(effective[1] ?? '')}`;
	const certified = new RegExp(
		`^a certified area of ${NUM} m² with a rated coefficient of discharge of ${NUM}$`
	).exec(words);
	if (certified) {
		return `a certified area of ${area(certified[1] ?? '')} with a rated coefficient of discharge of ${formatNumber(Number(certified[2]), 6)}`;
	}
	return null;
}

/** A project library entry in an issue: its name in the project (“Name”), else its id. */
function entryWords(project: Project, id: string): string {
	const entry = resistanceEntryOf(project, id);
	return `“${entry?.name ?? id}”`;
}

/** An entry's coefficient as the server's message states it (SI), in display units. */
function coefficientWords(
	kind: string,
	value: string,
	bore: string | undefined,
	units: UnitPreferences
): string {
	const at = bore === undefined ? '' : ` at ${formatValue(Number(bore), 'diameter', units)}`;
	return `${kind} ${formatNumber(Number(value), 6)}${at}`;
}

/** s²/m⁵: the unit of a loss coefficient c in h = c Q|Q|, as the server quotes c (SI; c has no
 * display unit). */
const PER_FLOW_SQUARED = 's²/m⁵';
/** The slope of a valve's head loss, as the server's message names it. */
const VALVE_SLOPE_WORDS = 'its head loss, 2 K/(2 g A²) |Q|';

/**
 * A coefficient above the slope bound and the bound, as the server quotes them, each shown with
 * the significant digits (6, the server's least, up to 17) at which they read apart; null when
 * they are not numbers with the coefficient above the bound (the message is then not told).
 */
function apart(value: string, bound: string): [string, string] | null {
	const [v, b] = [Number(value), Number(bound)];
	if (!Number.isFinite(v) || !Number.isFinite(b) || !(v > b)) return null;
	let sig = 6;
	while (sig < 17 && formatNumber(v, sig) === formatNumber(b, sig)) sig += 1;
	return [formatNumber(v, sig), formatNumber(b, sig)];
}

/**
 * "a loss coefficient <symbol> of [at least ]<c> <unit>, above half the largest floating-point
 * number (<bound> <unit>), so the slope of <slope>, is not a finite floating-point number at any
 * flow": a refusal at the slope bound (the builder's coefficients.slope_bound_text), with c and the
 * bound as the message quotes them (`apart`); null when they are not in the form expected.
 * `butZero`: an orifice plate's slope, which is 0 at zero flow (its law forms 2K|Q| before
 * 1/(2 g A²)). `atLeast`: c is a lower bound of every value the law takes (an orifice plate's K at
 * the upper bound of its discharge coefficient, the builder's rule (d)), told as "of at least <c>".
 */
function slopeWords(
	symbol: string,
	c: string,
	bound: string,
	unit: string,
	slope: string,
	butZero = false,
	atLeast = false
): string | null {
	const quoted = apart(c, bound);
	if (quoted === null) return null;
	const u = unit ? ` ${unit}` : '';
	return (
		`a loss coefficient ${symbol} of ${atLeast ? 'at least ' : ''}${quoted[0]}${u}, above half the largest floating-point ` +
		`number (${quoted[1]}${u}), so the slope of ${slope}, is not a finite floating-point number ` +
		`at any flow${butZero ? ' but zero' : ''}`
	);
}

/**
 * A reference to a project library entry the project does not have (UNKNOWN_PIPE_SPEC,
 * UNKNOWN_RESISTANCE: a valve's or a fitting's), or a fitting whose entry the solver cannot
 * represent on its pipe, for one unit or its quantity, or a piping whose fittings' loss
 * coefficients sum to no finite number (FITTING_RESISTANCE_OUT_OF_RANGE), or to one above the
 * slope bound, told with names (CLAUDE.md D22); null (the server's message) when the message is
 * not in a form expected.
 */
function libraryIssue(
	issue: TopologyIssue,
	links: IssueLink[],
	context: Context,
	component: Component | undefined,
	only: string | undefined
): IssueView | null {
	const { project, units } = context;
	const valve = VALVE_UNKNOWN_ENTRY.exec(issue.message);
	if (valve) {
		if (valve[1] !== only || !component) return null;
		return {
			text: `${component.name} refers to a resistance entry the project library does not have (“${valve[2]}”): choose an entry from the library, enter its resistance, or leave it on its default.`,
			links
		};
	}
	const pipe = PIPE_UNKNOWN_SPEC.exec(issue.message);
	const fitting = FITTING_UNKNOWN_ENTRY.exec(issue.message);
	const rangeSlope = FITTING_ENTRY_SLOPE.exec(issue.message);
	const range = rangeSlope ?? FITTING_ENTRY_RANGE.exec(issue.message);
	const sumSlope = FITTING_SUM_SLOPE.exec(issue.message);
	const sum = sumSlope ?? FITTING_ENTRY_SUM.exec(issue.message);
	const connection = pipingOf(project, issue, (pipe ?? fitting ?? range ?? sum)?.[1]);
	if (!connection) return null;
	const piping = `Piping ${pipingName(project, connection)}`;
	const fittingWords = (number: string, type: string) =>
		`fitting ${number} (${fittingFallbackName(type).toLowerCase()})`;
	let text: string | null = null;
	if (pipe && issue.code === 'UNKNOWN_PIPE_SPEC') {
		const [, , number, id] = pipe;
		text = `${piping}, pipe ${number} refers to a pipe spec the project library does not have (“${id}”): choose a spec from the library, or give the pipe its own size.`;
	} else if (fitting && issue.code === 'UNKNOWN_RESISTANCE') {
		const [, , number = '', type = '', id] = fitting;
		text = `${piping}, ${fittingWords(number, type)} refers to a resistance entry the project library does not have (“${id}”): choose an entry from the library, or enter its K.`;
	} else if (range && issue.code === 'FITTING_RESISTANCE_OUT_OF_RANGE') {
		const [
			,
			,
			number = '',
			type = '',
			id = '',
			kind = '',
			value = '',
			bore,
			pipeNumber,
			d = '',
			quantity,
			c = '',
			max = ''
		] = range;
		const forQuantity = quantity === undefined ? '' : `, for its quantity of ${quantity},`;
		const words = rangeSlope
			? slopeWords(
					'n K/(2 g A²)',
					c,
					max,
					PER_FLOW_SQUARED,
					"the piping's head loss, which takes 2 n K/(2 g A²) |Q| from it"
				)
			: 'a loss coefficient that is not a finite floating-point number,';
		if (words !== null) {
			text =
				`${piping}, ${fittingWords(number, type)}: its project library entry ${entryWords(project, id)} ` +
				`(${coefficientWords(kind, value, bore, units)}) on the inner diameter of pipe ${pipeNumber} ` +
				`(${formatValue(Number(d), 'diameter', units)}) gives${forQuantity} ${words} ` +
				`${rangeSlope ? 'and' : 'so'} the solver cannot represent this fitting. Check the entry.`;
		}
	} else if (sum && issue.code === 'FITTING_RESISTANCE_OUT_OF_RANGE') {
		// The slope form quotes the sum and the bound between the direction and the entries.
		const direction = sum[2];
		const list = (sumSlope ? sum[5] : sum[3]) ?? '';
		const quoted = sumSlope ? apart(sum[3] ?? '', sum[4] ?? '') : null;
		const onEntries = list.split(', ').map((item) => FITTING_ON_ENTRY.exec(item));
		const told = !sumSlope || quoted !== null;
		if (told && onEntries.length && onEntries.every((m): m is RegExpExecArray => m !== null)) {
			const name = (componentId: string) =>
				componentById(project, componentId)?.name ?? `“${componentId}”`;
			const [from, to] =
				direction === 'from → to'
					? [connection.fromComponentId, connection.toComponentId]
					: [connection.toComponentId, connection.fromComponentId];
			const fittings = onEntries
				.map((m) => `${fittingWords(m[1] ?? '', m[2] ?? '')} on ${entryWords(project, m[3] ?? '')}`)
				.join(', ');
			const flow = `flow from ${name(from)} to ${name(to)}`;
			text = quoted
				? `${piping}: its fittings' loss coefficients are each finite, but their sum for ${flow}, ` +
					`${quoted[0]} ${PER_FLOW_SQUARED}, is above half the largest floating-point number ` +
					`(${quoted[1]} ${PER_FLOW_SQUARED}), so the slope of the piping's head loss, which takes ` +
					'2 Σ n K/(2 g A²) |Q| from them, is not a finite floating-point number at any flow and ' +
					'the solver cannot represent this piping (fittings on project library entries: ' +
					`${fittings}). Check the entries.`
				: `${piping}: its fittings' loss coefficients are each finite, but their sum for ${flow} ` +
					'is not a finite floating-point number, so the solver cannot represent this piping ' +
					`(fittings on project library entries: ${fittings}). Check the entries.`;
		}
	}
	return text === null ? null : { text, links: [...links, ...pipingLink(project, connection)] };
}

/** An issue about one pipe of a piping ("connection 'L1' pipe 2: ..."), told with its names. */
function pipeIssue(issue: TopologyIssue, links: IssueLink[], context: Context): IssueView | null {
	const { project, units, options } = context;
	const head = PIPE_PREFIX.exec(issue.message);
	const connection = pipingOf(project, issue, head?.[1]);
	if (!head || !connection) return null;
	const [, , number, whole = ''] = head;
	const where = `Piping ${pipingName(project, connection)}, pipe ${number}`;
	const material = (id: string) => options.materialName?.(id) ?? `material “${id}”`;
	// A pipe of a project library spec (CLAUDE.md D22): the server names the spec by id first.
	const ofSpec = SPEC_PREFIX.exec(whole);
	const rest = ofSpec ? (ofSpec[2] ?? '') : whole;
	const spec = ofSpec ? pipeSpecOf(project, ofSpec[1]) : undefined;
	let text: string | null = null;
	switch (issue.code) {
		case 'UNKNOWN_PIPE_MATERIAL': {
			const match = UNKNOWN_MATERIAL.exec(rest);
			if (match && ofSpec)
				text = `${where}: its pipe spec “${spec?.name ?? ofSpec[1]}” names a material the pipe library does not have, “${match[1]}”: choose a material from the library for the spec, or make it a custom spec.`;
			else if (match)
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
				const r = formatValue(Number(roughness), 'diameter', units);
				const times = `${formatNumber(Number(ratio), 4)} times its inner diameter`;
				const d = formatValue(Number(diameter), 'diameter', units);
				// On a pipe of a spec the values are the spec's, changed in the library (D22).
				text =
					(ofSpec
						? `${where}: its pipe spec “${spec?.name ?? ofSpec[1]}” has a roughness (${r}) ${times} (${d}), `
						: `${where}: its roughness (${r}) is ${times} (${d}), `) +
					`and the Colebrook equation has ` +
					`no solution for a relative roughness (roughness ÷ inner diameter) of ` +
					`${formatNumber(Number(limit), 6)} or more. ` +
					(ofSpec
						? 'Give the spec a smaller roughness or a larger inner diameter in the project library.'
						: 'Use a smaller roughness or a larger inner diameter.');
			}
			break;
		}
		case 'PIPE_SIZE_OUT_OF_RANGE': {
			const match = PIPE_SIZE.exec(rest);
			const underflow = PIPE_RE_DENOMINATOR.exec(rest);
			if (underflow) {
				const [, diameter = '', nu = ''] = underflow;
				const d = formatValue(Number(diameter), 'diameter', units);
				// ν (m²/s) has no display unit: as the message quotes it.
				text =
					(ofSpec
						? `${where}: the inner diameter of its pipe spec “${spec?.name ?? ofSpec[1]}”, ${d}, with `
						: `${where}: an inner diameter of ${d} with `) +
					`the fluid's kinematic viscosity of ${formatNumber(Number(nu), 6)} m²/s gives a ` +
					'Reynolds number |Q| D/(A ν) whose denominator A ν is 0 in floating point (it ' +
					'underflows), so the solver cannot represent this pipe. ' +
					(ofSpec
						? "Check the spec's inner diameter in the project library, and the fluid's viscosity."
						: "Check its inner diameter and the fluid's viscosity.");
			} else if (match) {
				const [, diameter = '', length = ''] = match;
				const d = formatValue(Number(diameter), 'diameter', units);
				const l = formatValue(Number(length), 'length', units);
				// On a pipe of a spec the bore is the spec's (changed in the library), the length the pipe's.
				text =
					(ofSpec
						? `${where}: the inner diameter of its pipe spec “${spec?.name ?? ofSpec[1]}”, ${d}, and its length, ${l}, give a pipe resistance `
						: `${where}: an inner diameter of ${d} and a length of ${l} give a pipe resistance `) +
					'that is not a finite floating-point number, so the solver cannot represent this ' +
					'pipe. ' +
					(ofSpec
						? "Check the spec's inner diameter in the project library, and the pipe's length."
						: 'Check its inner diameter and length.');
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
/**
 * A relief valve refused below ASME VIII's scope (the API's relief.refusal_text, rule 'scope'):
 * its set, the scope in psi and Pa, and the remedy.
 */
const RELIEF_SCOPE = new RegExp(
	`^relief valve '${ID}': its set pressure of ${NUM} Pa is below ASME VIII's scope, ${NUM} psi ` +
		`\\(${NUM} Pa\\): below it no cited source gives its overpressure at full lift \\(ASME's ` +
		"default, 10 % or 3 psi, is for sets within that scope\\), and API 520's effective " +
		'coefficient of discharge applies to valves certified within it; (.*)$',
	's'
);
/** The remedies RELIEF_SCOPE's message gives, as the app tells them. */
const RELIEF_REMEDIES: Readonly<Record<string, string>> = {
	'enter its certified overpressure at full lift': 'Enter its certified overpressure at full lift.',
	"enter the valve's certified capacity: its actual orifice area, rated coefficient of discharge and full-lift overpressure":
		"Give its capacity as certified: the valve's actual orifice area, rated coefficient of discharge and full-lift overpressure."
};
/**
 * A relief valve whose law the floating point cannot represent (rule 'representable'): its
 * capacity in words, C, its set and its overpressure (nan when none).
 */
const RELIEF_LAW = new RegExp(
	`^relief valve '${ID}': (.*), C = Kd·A = ${NUM} m², with a set pressure of ${NUM} Pa and an ` +
		`overpressure of (${NUM.slice(1, -1)}|nan) gives C, the full-lift flow Q_f = \\S+ m³/s or ` +
		'the band coefficient R = \\S+ that is not a finite positive normal floating-point number; ' +
		'the solver cannot represent this valve$',
	's'
);
const VALVE_RESISTANCE = new RegExp(
	`^valve '${ID}': a (K|Cv|Kv) of ${NUM} on the inlet pipe's inner diameter of ${NUM} m gives a ` +
		'loss coefficient that is not a finite floating-point number; the solver cannot represent ' +
		'this valve$'
);
/** A pattern matching `text` literally. */
function literal(text: string): string {
	return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
/**
 * A refusal at the slope bound (the builder's coefficients.slope_bound_text): "a loss coefficient
 * <symbol> of [at least ]<c> <unit>, above <bound> <unit>, half the largest floating-point number,
 * so <the slope's words>, is not a finite floating-point number at any flow", c and the bound as
 * groups. `atLeast`: the "at least " before c (an orifice plate's rule (d)).
 */
function slopeSource(symbol: string, unit: string, slope: string, atLeast = false): string {
	const u = unit ? ` ${literal(unit)}` : '';
	return (
		`a loss coefficient ${literal(symbol)} of ${atLeast ? 'at least ' : ''}${NUM}${u}, above ${NUM}${u}, half the largest ` +
		`floating-point number, so ${literal(slope)}, is not a finite floating-point number at any flow`
	);
}
/** A valve's refusal at the slope bound ends so (the builder's VALVE_SLOPE). */
const VALVE_SLOPE_TAIL =
	slopeSource('K/(2 g A²)', 's²/m⁵', 'the slope of its head loss, 2 K/(2 g A²) |Q|') +
	'; the solver cannot represent this valve$';
const VALVE_RESISTANCE_SLOPE = new RegExp(
	`^valve '${ID}': a (K|Cv|Kv) of ${NUM} on the inlet pipe's inner diameter of ${NUM} m gives ` +
		VALVE_SLOPE_TAIL
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
/** The same rating with a finite c above the slope bound: c and the bound (s²/m⁵) follow. */
const EQUIPMENT_SLOPE = new RegExp(
	`^equipment '${ID}': a rating of (?:${NUM} Pa at ${NUM} m³/s for a fluid of ${NUM} kg/m³|(Cv|Kv) ${NUM}) ` +
		`gives a loss coefficient, .*, of ${NUM} s²/m⁵, above ${NUM} s²/m⁵, half the largest ` +
		'floating-point number, so the slope of its head loss, 2c\\|Q\\|, is not a finite ' +
		'floating-point number at any flow; the solver cannot represent this element$',
	's'
);
/**
 * An orifice plate the solver cannot represent (the builder's _orifice_issue_text): its bore and
 * its inlet pipe's inner diameter, m (Python's `:g`), β (`:.6g`), then the rule it breaks.
 */
const ORIFICE_HEAD = new RegExp(
	`^orifice '${ID}': a bore diameter of ${NUM} m in an inlet pipe of inner diameter ${NUM} m ` +
		`\\(β = d/D = ${NUM}\\): (.*)$`,
	's'
);
const ORIFICE_BETA =
	/^the bore is not smaller than the pipe; an orifice plate needs β < 1, so the solver cannot represent this plate$/;
/**
 * Decision 17 (b) (the builder's _orifice_iso_tail): the tap set where eq. (4) can exceed 1, what
 * eq. (4) is used for there (the loss, only a meter's reading, or a coefficient of an entered C's
 * move, `orifice.Refusal.basis`), the largest C, then the server's reason and remedy (`tail`).
 */
const ORIFICE_ISO = new RegExp(
	`^ISO 5167-2's discharge coefficient \\(Reader-Harris/Gallagher\\) at (corner tappings|flange tappings|D and D/2 tappings), ` +
		`(which sets the plate's loss|which gives only the meter's reading|one of the two in the ratio that moves its ` +
		`entered discharge coefficient ${NUM} from its (corner tappings|flange tappings) to D and D/2 tappings), ` +
		`can reach ${NUM} at some flow, above 1(.*)$`,
	's'
);
/** The loss's reason and its remedy for a plate without taps or with D and D/2 taps, or (group
 * 1) the tap set of a meter's corner or flange taps, where an entered C would be moved. */
const ORIFICE_ISO_LOSS = new RegExp(
	'^, which would make the jet larger than the bore and the loss smaller than the sudden ' +
		'expansion from the bore \\(Borda-Carnot\\), physically impossible; use a smaller bore' +
		"(?:, or enter a discharge coefficient \\(ISO 5167-2's C at D and D/2 tappings, used as " +
		'entered\\)| \\(an entered discharge coefficient at its (corner tappings|flange tappings) ' +
		"would be moved to D and D/2 tappings by ISO 5167-2's ratio, which uses this coefficient, " +
		'and refused the same way\\))$'
);
const ORIFICE_ISO_READING =
	/^: the correlation is extrapolated far beyond ISO 5167-2's range, so the reading at these taps has no basis \(the plate's loss uses the coefficient at D and D\/2 tappings, which stays at or below 1\); use a smaller bore, D and D\/2 taps, or no taps \(a restriction orifice, with no reading\)$/;
const ORIFICE_ISO_MOVE =
	/^: the correlation is extrapolated far beyond ISO 5167-2's range, so the move has no basis at this plate; use a smaller bore, or give the discharge coefficient at D and D\/2 tappings \(with D and D\/2 taps, or no taps\), where it is used as entered$/;
const ORIFICE_MOVED = new RegExp(
	`^its entered discharge coefficient ${NUM} at its (corner tappings|flange tappings), moved to D and ` +
		`D/2 tappings by ISO 5167-2's ratio of the two tap sets' coefficients \\(up to ${NUM} at this ` +
		`plate\\), can reach ${NUM} at some flow, above 1, .*$`,
	's'
);
const ORIFICE_UNBOUNDED =
	/^ISO 5167-2's discharge coefficient cannot be bounded at this plate; the solver cannot represent this plate$/;
const ORIFICE_LOSS = new RegExp(
	`^with a discharge coefficient down to ${NUM} it gives a loss coefficient, K/\\(2 g A²\\), that is ` +
		'not a finite positive floating-point number; the solver cannot represent this plate$'
);
/** Rule 'slope': the plate's C bound c_high, quoted "of at most <C> at every flow" (an upper
 * bound of every C the law takes, which need not be reached), and K there (dimensionless), quoted
 * "of at least <K>" (a lower bound of every K the law takes), above the slope bound; the slope is
 * 0 at zero flow, as the law forms 2K|Q| before 1/(2 g A²). */
const ORIFICE_SLOPE = new RegExp(
	`^with a discharge coefficient of at most ${NUM} at every flow it gives ` +
		slopeSource('K', '', 'the slope of its head loss, 2 K|Q|/(2 g A²)', true) +
		' but zero; the solver cannot represent this plate$'
);
/**
 * Rule (e), the case's fluid (the builder's _ORIFICE_FLUID_TAILS after the head, with its
 * ending): μ (Pa·s) for π D μ that underflows; ρ (kg/m³) for (π D²/4) ρ that underflows; ρ and μ
 * for a Reynolds number per unit flow that is not finite, and for ISO 5167-2's C that fluids
 * cannot evaluate at the plate's lowest Reynolds number.
 */
const ORIFICE_FLUID_DENOMINATOR = new RegExp(
	`^with the fluid's dynamic viscosity of ${NUM} Pa·s, ` +
		literal(
			'the denominator π D μ of its Reynolds number Re_D = 4ρ|Q|/(π D μ) is 0 in floating ' +
				'point (it underflows); the solver cannot represent this plate'
		) +
		'$'
);
const ORIFICE_FLUID_AREA = new RegExp(
	'^' +
		literal(
			"ISO 5167-2's discharge coefficient is evaluated (fluids) from the mass flow, dividing " +
				"by the pipe's area times the fluid's density, (π D²/4) ρ, which with a density of "
		) +
		`${NUM} kg/m³ is 0 in floating point \\(it underflows\\); the solver cannot represent ` +
		'this plate$'
);
const ORIFICE_FLUID_INFINITE = new RegExp(
	`^with the fluid's density of ${NUM} kg/m³ and dynamic viscosity of ${NUM} Pa·s, ` +
		literal(
			'its Reynolds number per unit flow, 4ρ/(π D μ), is not a finite floating-point number, ' +
				"so Re_D is infinite at every flow but zero, where ISO 5167-2's discharge coefficient " +
				'cannot be evaluated; the solver cannot represent this plate'
		) +
		'$'
);
const ORIFICE_FLUID_RE_LO = new RegExp(
	`^with the fluid's density of ${NUM} kg/m³ and dynamic viscosity of ${NUM} Pa·s, ` +
		literal(
			"ISO 5167-2's discharge coefficient cannot be evaluated at the plate's lowest Reynolds " +
				"number (fluids' arithmetic fails there); the solver cannot represent this plate"
		) +
		'$'
);
/** "connection 'L1' pipe 2: <the pipe's problem>" (pipes numbered from 1). */
const PIPE_PREFIX = new RegExp(`^connection '${ID}' pipe (\\d+): (.*)$`, 's');
/** A pipe of a project library spec: "pipe spec 'PS1': <its material's, bore's or roughness's
 * problem>" (D22: UNKNOWN_PIPE_MATERIAL, ROUGHNESS_OUT_OF_RANGE, PIPE_SIZE_OUT_OF_RANGE). */
const SPEC_PREFIX = new RegExp(`^pipe spec '${ID}': (.*)$`, 's');
/** An entry's coefficient as entered (project_library.entered_text): "Cv 60000", "K 0.3 at 0.7366 m". */
const ENTERED = `(K|Cv|Kv) ${NUM}(?: at ${NUM} m)?`;
/** A reference to a project library entry the project does not have (builder.py, D22). */
const VALVE_UNKNOWN_ENTRY = new RegExp(
	`^valve '${ID}' refers to resistance entry '${ID}', which is not in the project library$`
);
const PIPE_UNKNOWN_SPEC = new RegExp(
	`^connection '${ID}' pipe (\\d+) refers to pipe spec '${ID}', which is not in the project library$`
);
const FITTING_UNKNOWN_ENTRY = new RegExp(
	`^connection '${ID}' fitting (\\d+) \\(([a-z0-9_]+)\\) refers to resistance entry '${ID}', which is not in the project library$`
);
/** A valve or fitting whose entry gives no representable loss coefficient on its bore (D22). */
const VALVE_ENTRY = new RegExp(
	`^valve '${ID}': its project library resistance entry '${ID}', ${ENTERED}, on the inlet ` +
		`pipe's inner diameter of ${NUM} m gives a loss coefficient that is not a finite positive ` +
		'floating-point number; the solver cannot represent this valve$'
);
const VALVE_ENTRY_SLOPE = new RegExp(
	`^valve '${ID}': its project library resistance entry '${ID}', ${ENTERED}, on the inlet ` +
		`pipe's inner diameter of ${NUM} m gives ${VALVE_SLOPE_TAIL}`
);
const FITTING_ENTRY_RANGE = new RegExp(
	`^connection '${ID}' fitting (\\d+) \\(([a-z0-9_]+)\\): its project library resistance entry ` +
		`'${ID}', ${ENTERED}, on the inner diameter of pipe (\\d+), ${NUM} m, gives` +
		'(?:, for its quantity of (\\d+),)? a loss coefficient that is not a finite floating-point ' +
		'number; the solver cannot represent this fitting$'
);
/** The same fitting with a finite n K/(2 g A²) above the slope bound: c and the bound follow. */
const FITTING_ENTRY_SLOPE = new RegExp(
	`^connection '${ID}' fitting (\\d+) \\(([a-z0-9_]+)\\): its project library resistance entry ` +
		`'${ID}', ${ENTERED}, on the inner diameter of pipe (\\d+), ${NUM} m, gives` +
		'(?:, for its quantity of (\\d+),)? ' +
		slopeSource(
			'n K/(2 g A²)',
			's²/m⁵',
			"the slope of the connection's head loss, which takes 2 n K/(2 g A²) |Q| from it"
		) +
		'; the solver cannot represent this fitting$'
);
/** A connection whose fittings' loss coefficients are each finite but sum, for one flow
 * direction, to no finite number (builder._unrepresentable_fittings, D22): the fittings on
 * entries it lists ("fitting 1 (custom) on 'RS1', fitting 2 (custom) on 'RS1'"). */
const FITTING_ENTRY_SUM = new RegExp(
	`^connection '${ID}': its fittings' loss coefficients n K/\\(2 g A²\\) are each finite, but ` +
		'their sum for flow (from → to|to → from) is not a finite floating-point number \\(on ' +
		'project library resistance entries: (.*)\\); the solver cannot represent this connection$'
);
/** The same sum, finite but above the slope bound: the sum and the bound (s²/m⁵) follow the
 * direction. */
const FITTING_SUM_SLOPE = new RegExp(
	`^connection '${ID}': its fittings' loss coefficients n K/\\(2 g A²\\) are each finite, but ` +
		`their sum for flow (from → to|to → from), ${NUM} s²/m⁵, is above ${NUM} s²/m⁵, half the ` +
		"largest floating-point number, so the slope of the connection's head loss, which takes " +
		'2 Σ n K/\\(2 g A²\\) \\|Q\\| from them, is not a finite floating-point number at any flow ' +
		'\\(on project library resistance entries: (.*)\\); the solver cannot represent this ' +
		'connection$'
);
const FITTING_ON_ENTRY = new RegExp(`^fitting (\\d+) \\(([a-z0-9_]+)\\) on '${ID}'$`);
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
/** A pipe whose Reynolds number's denominator A ν underflows (the builder's
 * _unrepresentable_pipes): its inner diameter (m) and the fluid's kinematic viscosity (m²/s). */
const PIPE_RE_DENOMINATOR = new RegExp(
	`^an inner diameter of ${NUM} m with the fluid's kinematic viscosity of ${NUM} m²/s gives ` +
		literal(
			'a Reynolds number |Q| D/(A ν) whose denominator A ν is 0 in floating point (it ' +
				'underflows); the solver cannot represent this pipe'
		) +
		'$'
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
