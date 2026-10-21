/**
 * Flag text for display. The API writes a flag's message in SI with element ids ("pump 'PU1'
 * operates at 0.0475 m³/s"). Here the text is built from the flag's code and details, in the
 * project's display units and with names, for the codes whose details carry the values. Any
 * other flag shows the API's message with element ids replaced by names and SI quantities
 * ("0.0475 m³/s", "-52340.5 Pa", "0.1023 m") converted to display units by their unit symbol.
 *
 * The element a flag is about is shown next to the text (a link, a table row or the trace
 * panel), so the text does not start with it. Every number comes from the flag; only units
 * change. Pipes and fittings are numbered from 1, as in the results tables and the API's
 * messages (the segmentIndex and fittingIndex details are 0-based indexes).
 */
import type { Flag, Project, UnitPreferences } from '../api/types';
import { componentById, connectionById } from './graph';
import { fittingFallbackName, portLabel } from './labels';
import { connectionName, Formatter, pipeLabel, siText } from './results';
import type { LabelOptions, UnitCategory } from './units';

export interface FlagTextContext {
	project: Project;
	prefs: UnitPreferences;
	/** Library name of a fitting type (falls back to the built-in names). */
	fittingName?: (type: string) => string;
	/** Valve type by component id (e.g. from the solved valve results), for setpoint units. */
	valveTypes?: Readonly<Record<string, string>>;
}

function number(flag: Flag, key: string): number | null {
	const value = flag.details[key];
	return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function capitalize(text: string): string {
	return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

/** The name the UI uses for an id in a message: a component, a port of one, or a connection. */
function nameOf(project: Project, id: string): string | null {
	const component = componentById(project, id);
	if (component) return component.name;
	const [componentId = '', portId] = id.split(':');
	const owner = portId !== undefined ? componentById(project, componentId) : undefined;
	if (owner && portId) return `${portLabel(portId)} of ${owner.name}`;
	if (connectionById(project, id)) return connectionName(project, id);
	return null;
}

/**
 * The API's message, readable in the project: ids in quotes become names, SI quantities are
 * shown in display units (a pressure keeps the gauge or absolute wording of the message; no
 * marker is added), and a leading "<kind> '<id>': " naming the flag's own element is dropped.
 */
export function messageText(flag: Flag, context: FlagTextContext): string {
	const own = flag.componentId ?? flag.connectionId;
	let text = flag.message;
	if (own) {
		const prefix = new RegExp(`^[A-Za-z ]+ '${own.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}': `);
		text = text.replace(prefix, '');
	}
	text = text.replace(/'([^']+)'/g, (whole, id: string) => {
		const name = nameOf(context.project, id);
		return name ? `“${name}”` : whole;
	});
	return capitalize(siText(text, context.prefs));
}

/** The text after "pipe N: " or "fitting N (type): " in a connection flag's message. */
function reason(message: string): string {
	const match = /(?:pipe \d+|fitting \d+ \([^)]*\)): (.*)$/s.exec(message);
	return match?.[1] ?? message;
}

/** Display text of a flag (see the module comment). */
export function flagText(flag: Flag, context: FlagTextContext): string {
	const f = new Formatter(context.prefs);
	const value = (key: string, category: UnitCategory, options: LabelOptions = {}) => {
		const v = number(flag, key);
		return v === null ? null : f.value(v, category, options);
	};
	const fallback = () => messageText(flag, context);

	switch (flag.code) {
		case 'CAVITATION': {
			const a = value('npshAvailable', 'head');
			const r = value('npshRequired', 'head');
			const m = value('npshMargin', 'head');
			if (!a || !r || !m) return fallback();
			return `NPSH available ${a} is below NPSH required ${r} (margin ${m}): the pump would cavitate.`;
		}
		case 'BELOW_VAPOR_PRESSURE': {
			const vapor = value('vaporPressure', 'pressure', { absolute: true });
			const bound = vapor
				? `the vapor pressure (${vapor})`
				: `${f.value(0, 'pressure', { absolute: true })}, below any liquid's vapor pressure (this fluid has none given)`;
			const surface = value('surfaceAbsolutePressure', 'pressure', { absolute: true });
			if (surface)
				return `The liquid surface is at ${surface}, below ${bound}: the liquid would boil.`;
			const p = value('absolutePressure', 'pressure', { absolute: true });
			if (!p) return fallback();
			const where = flag.portId ? `at ${portLabel(flag.portId)} ` : '';
			return `The absolute pressure ${where}is ${p}, below ${bound}: the liquid would flash.`;
		}
		case 'PUMP_FLOW_REVERSAL': {
			const rise = number(flag, 'headRise');
			const shutoff = number(flag, 'shutoffHead');
			if (rise === null || shutoff === null) return fallback();
			return rise > shutoff
				? `The system head across it (${f.value(rise, 'head')}) exceeds its shutoff head (${f.value(shutoff, 'head')}): flow would reverse, and the pump's check holds it at zero flow.`
				: `Its discharge is closed off, so it runs dead-headed at its shutoff head (${f.value(shutoff, 'head')}), held at zero flow by its check.`;
		}
		case 'PUMP_OUTSIDE_CURVE': {
			const q = value('flow', 'flow');
			const curve = flag.details.curve;
			if (!q) return fallback();
			if (curve === 'efficiency') {
				return `The operating flow (${q}) is outside its efficiency curve: the efficiency is held at the curve's nearest end value.`;
			}
			if (curve === 'npshr') {
				return `The operating flow (${q}) is outside its NPSHr curve: NPSHr is extrapolated along the curve's end slope.`;
			}
			const speed = value('speed', 'fraction');
			const at = speed ? ` at ${speed} speed` : '';
			return `It operates at ${q}, outside the flow range of its curve${at}: the head is extrapolated along the curve's end slope (dashed on the pump chart).`;
		}
		case 'TRANSITIONAL_FLOW': {
			const segment = number(flag, 'segmentIndex');
			const re = number(flag, 'reynoldsNumber');
			if (segment === null || re === null) return fallback();
			return `${pipeLabel(segment)}: Re = ${f.plain(re)} is in the laminar–turbulent transition range: the friction factor is interpolated and the flow may be unsteady.`;
		}
		case 'CORRELATION_OUT_OF_RANGE': {
			const segment = number(flag, 'segmentIndex');
			if (segment !== null && flag.connectionId) {
				return `${pipeLabel(segment)}: ${messageText({ ...flag, message: reason(flag.message) }, context)}`;
			}
			const fitting = number(flag, 'fittingIndex');
			if (fitting !== null && flag.connectionId) {
				const type =
					/fitting \d+ \(([^)]+)\)/.exec(flag.message)?.[1] ??
					connectionById(context.project, flag.connectionId)?.piping.fittings[fitting]?.type;
				const name = type ? (context.fittingName ?? fittingFallbackName)(type) : 'Fitting';
				return `${name} (fitting ${fitting + 1}): ${messageText({ ...flag, message: reason(flag.message) }, context)}`;
			}
			return fallback();
		}
		case 'CHECK_VALVE_CLOSED': {
			const dh = value('headDifference', 'head');
			const crack = value('crackingHead', 'head');
			if (!dh || !crack) return fallback();
			return `Closed: the head across it (${dh}) does not exceed its cracking head (${crack}) in the forward direction.`;
		}
		case 'CONTROL_VALVE_SETPOINT_NOT_MET': {
			const setpoint = number(flag, 'setpoint');
			const state = flag.details.state;
			const id = flag.componentId ?? '';
			const component = componentById(context.project, id);
			const type =
				context.valveTypes?.[id] ?? (component?.type === 'valve' ? component.valveType : undefined);
			if (setpoint === null || typeof state !== 'string' || !type) return fallback();
			const target =
				type === 'fcv'
					? `flow setpoint (${f.value(setpoint, 'flow')})`
					: type === 'prv'
						? `outlet pressure setpoint (${f.value(setpoint, 'pressure', { gauge: true })})`
						: type === 'psv'
							? `inlet pressure setpoint (${f.value(setpoint, 'pressure', { gauge: true })})`
							: null;
			if (!target) return fallback();
			return `It is ${state}: it cannot hold its ${target}.`;
		}
		case 'PORT_ABOVE_LIQUID_LEVEL': {
			const port = value('portElevation', 'length');
			const surface = value('liquidSurfaceElevation', 'length');
			if (!port || !surface || !flag.portId) return fallback();
			return `${portLabel(flag.portId)} is above the liquid surface (${port} > ${surface}): it would draw air.`;
		}
		case 'ISOLATED_SECTION': {
			const ids = flag.details.componentIds;
			if (typeof ids !== 'string') return fallback();
			const names = ids
				.split(',')
				.map((id) => id.trim())
				.filter(Boolean)
				.map((id) => nameOf(context.project, id) ?? id);
			return `No flow path to a fixed-pressure boundary (closed off): ${names.join(', ')}. These elements carry no flow and have no computed pressure.`;
		}
		default:
			return fallback();
	}
}
