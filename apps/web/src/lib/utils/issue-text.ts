/**
 * Topology issues from the calculation server, as people read them: the common codes a new
 * network meets (a pump with no curve, a port left open, a part with no fixed-pressure boundary)
 * are told in the browser with component and port names, chosen by the issue's code and the ids
 * it lists, never by rewording the server's text. Any other issue keeps the server's message.
 * Every issue links to the components it names (and to the open port, for an unconnected one).
 *
 * A speed-controlled pump whose curve does not give one speed for each head
 * (CONTROLLED_PUMP_CURVE) is told with its names, and the curve and the flow interval where it
 * fails are taken from the server's message (an issue has no details) and shown in the display
 * unit. The server's message is shown instead when it does not state them in the form expected,
 * when it names another curve than the pump's, or when the error is not for the project as it is
 * now (the pump may have been given another curve since the solve was sent).
 */
import type {
	FluidDefinition,
	FluidInfo,
	Project,
	TopologyIssue,
	UnitPreferences
} from '../api/types';
import { componentById, freePorts } from './graph';
import { fluidSummary, portLabel } from './labels';
import { formatValue, SI_UNITS } from './units';

export interface IssueLink {
	componentId: string;
	/** Open this port's piping (an unconnected port). */
	portId?: string;
}

export interface IssueView {
	text: string;
	links: IssueLink[];
}

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
	units: UnitPreferences = SI_UNITS
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

	return issues.map((issue) => {
		const links: IssueLink[] = issue.componentIds.map((componentId) => ({ componentId }));
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
				break;
			case 'UNCONNECTED_PORT': {
				const portId = component ? openPorts.get(component.id)?.shift() : undefined;
				if (component && portId) {
					return {
						text: `${portLabel(portId)} of ${component.name} is not connected: connect it or add a plug.`,
						links: [{ componentId: component.id, portId }]
					};
				}
				break;
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
				break;
			}
			case 'NO_FIXED_HEAD':
				return {
					text: issue.componentIds.length
						? 'This part of the network has no fixed-pressure boundary: add a reservoir or reference node to it.'
						: 'The network is empty: add a reservoir or reference node and connect it.',
					links
				};
		}
		return { text: issue.message, links };
	});
}

/** The curve (its id) that the server's CONTROLLED_PUMP_CURVE message names. */
const CURVE_ID = /is speed-controlled, but its curve '([A-Za-z0-9_-]+)'/;

/** The flow interval (m³/s) in the server's CONTROLLED_PUMP_CURVE message. */
const CURVE_INTERVAL =
	/flows x from (-?\d+(?:\.\d+)?(?:e[+-]?\d+)?) to (-?\d+(?:\.\d+)?(?:e[+-]?\d+)?) m³\/s/;

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
