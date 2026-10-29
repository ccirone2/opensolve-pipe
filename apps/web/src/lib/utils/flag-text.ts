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
 * messages (the segmentIndex and fittingIndex details are 0-based indexes). A pipe's flag
 * (TRANSITIONAL_FLOW, CORRELATION_OUT_OF_RANGE) is numbered from its segmentIndex, so a copy with
 * the pipe's index as it is now (Build's strip, utils/results.ts) names that pipe.
 *
 * An orifice plate's validity flags (CORRELATION_OUT_OF_RANGE on the component, proposal
 * orifice-plate.md §3.5) are told from `details.limit` and their SI numbers; the flashing check at
 * its vena contracta (BELOW_VAPOR_PRESSURE) from `details.venaContractaAbsolutePressure`. Its
 * Reynolds-number flag, whose numbers have no unit and whose consequence differs between ISO's and
 * an entered coefficient, keeps the API's words (names for ids).
 *
 * A relief valve's flags (proposal pressure-relief-valve.md §3.6, §4.3) are told from their
 * details: full lift (RELIEF_VALVE_OPEN), closed with no result (RELIEF_VALVE_CLOSED), partial lift
 * and a viscous liquid (CORRELATION_OUT_OF_RANGE, `details.limit`), and flashing at its outlet
 * (BELOW_VAPOR_PRESSURE, `details.backAbsolutePressure`); each falls back to the API's message
 * without its details.
 */
import type { Flag, Project, UnitPreferences } from '../api/types';
import { componentById, connectionById } from './graph';
import { fittingFallbackName, portLabel } from './labels';
import { connectionName, Formatter, pipeLabel, siText } from './results';
import { digitsApart, formatValue, type LabelOptions, type UnitCategory } from './units';

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
 * Text from the API, readable in the project: ids in quotes become names, and SI quantities are
 * shown in display units (a pressure keeps the gauge or absolute wording of the text; no marker
 * is added). Used for flags (messageText) and the convergence report's message.
 */
export function readableText(text: string, project: Project, prefs: UnitPreferences): string {
	const named = text.replace(/'([^']+)'/g, (whole, id: string) => {
		const name = nameOf(project, id);
		return name ? `“${name}”` : whole;
	});
	return capitalize(siText(named, prefs));
}

/**
 * The components that text from the API names (ids in quotes; a port's key names its
 * component), in the order named, each once, leaving out ids the project does not have.
 */
export function namedComponents(text: string, project: Project): string[] {
	const ids: string[] = [];
	for (const [, id = ''] of text.matchAll(/'([^']+)'/g)) {
		const componentId = componentById(project, id) ? id : id.split(':')[0];
		if (componentId && componentById(project, componentId) && !ids.includes(componentId)) {
			ids.push(componentId);
		}
	}
	return ids;
}

/**
 * The API's message, readable in the project (readableText), with a leading "<kind> '<id>': "
 * naming the flag's own element dropped.
 */
export function messageText(flag: Flag, context: FlagTextContext): string {
	const own = flag.componentId ?? flag.connectionId;
	let text = flag.message;
	if (own) {
		const prefix = new RegExp(`^[A-Za-z ]+ '${own.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}': `);
		text = text.replace(prefix, '');
	}
	return readableText(text, context.project, context.prefs);
}

/** The text after "pipe N: " or "fitting N (type): " in a connection flag's message. */
function reason(message: string): string {
	const match = /(?:pipe \d+|fitting \d+ \([^)]*\)): (.*)$/s.exec(message);
	return match?.[1] ?? message;
}

/** The end of an orifice plate's ISO-range flags: what being outside the range means. */
const OUTSIDE_ISO =
	"ISO 5167-2's discharge coefficient (Reader-Harris/Gallagher) is used outside its validated range.";

/**
 * An orifice plate's validity flag told from its `details.limit` and SI numbers (proposal
 * orifice-plate.md §3.5), or null to keep the API's words: its Reynolds-number flag, a flag of
 * another element, or details not in the form expected. A value and the limit or value it is
 * compared with are shown with as many digits as tell them apart (units.ts digitsApart, as
 * design checks do), so a value just past a limit never reads as the limit.
 */
function orificeText(flag: Flag, f: Formatter): string | null {
	const limit = flag.details.limit;
	if (typeof limit !== 'string' || !flag.componentId) return null;
	const n = (key: string) => number(flag, key);
	const value = n('value');
	const lower = n('lower');
	const upper = n('upper');
	/** The value and the other number in `category`'s display unit, told apart. */
	const apart = (v: number, other: number, category: UnitCategory): [string, string] => {
		const show = (si: number, sig: number) => formatValue(si, category, f.prefs, sig);
		const sig = digitsApart(v, [other], show);
		return [show(v, sig), show(other, sig)];
	};
	const range = (what: string, category: UnitCategory): string | null => {
		if (value === null) return null;
		if (lower !== null) {
			const [v, l] = apart(value, lower, category);
			return `${what} (${v}) is below ISO 5167-2's smallest, ${l}: ${OUTSIDE_ISO}`;
		}
		if (upper !== null) {
			const [v, u] = apart(value, upper, category);
			return `${what} (${v}) is above ISO 5167-2's largest, ${u}: ${OUTSIDE_ISO}`;
		}
		return null;
	};
	switch (limit) {
		case 'boreDiameter':
			return range('Its bore diameter', 'diameter');
		case 'pipeDiameter':
			return range("Its inlet pipe's inner diameter", 'diameter');
		case 'beta':
			return range('Its diameter ratio β = d ÷ D', 'dimensionless');
		case 'outletDiameter': {
			const inlet = n('inlet');
			if (value === null || inlet === null) return null;
			const [outlet, inletText] = apart(value, inlet, 'diameter');
			return `Its outlet pipe's inner diameter (${outlet}) differs from its inlet pipe's (${inletText}): ISO 5167-2's pressure-loss relation assumes the jet recovers in a pipe of the inlet's bore, about 6 D downstream, so the loss is less certain.`;
		}
		case 'laminar': {
			if (value === null || upper === null) return null;
			const [re, top] = apart(value, upper, 'dimensionless');
			return `Its entered discharge coefficient is held at every flow, a square law for turbulent flow, but the flow in its inlet pipe is laminar (Re = ${re}, below ${top}): the loss is likely underestimated.`;
		}
		case 'reverseFlow': {
			const q = n('flow');
			if (q === null) return null;
			return `The flow runs from outlet to inlet (${f.value(q, 'flow')}): ISO 5167-2's coefficient is for flow onto the plate's upstream face, and the loss is taken as for forward flow at the same flow rate.`;
		}
		default:
			return null;
	}
}

/** A ratio (a fraction of something) as a percentage, told apart from `others` (digitsApart). */
function percentApart(f: Formatter, value: number, others: readonly number[]): string {
	const show = (si: number, sig: number) => formatValue(si, 'fraction', f.prefs, sig);
	return show(value, digitsApart(value, others, show));
}

/**
 * A relief valve's validity flags (CORRELATION_OUT_OF_RANGE on the component, proposal
 * pressure-relief-valve.md §3.6), told from `details.limit` ('partial_lift', 'viscosity') and
 * their SI numbers, or null to keep the API's words (another limit, or details not in the form
 * expected). A value near the limit it is compared with gets the digits that tell them apart.
 */
function reliefText(flag: Flag, f: Formatter): string | null {
	const limit = flag.details.limit;
	if (!flag.componentId || (limit !== 'partial_lift' && limit !== 'viscosity')) return null;
	const n = (key: string) => number(flag, key);
	if (limit === 'partial_lift') {
		const lift = n('lift');
		const ratio = n('setRatio');
		const op = n('overpressure');
		if (lift === null || ratio === null || op === null) return null;
		const full = 1 + op;
		return (
			`It relieves at partial lift (${percentApart(f, lift, [0, 1])}, the pressure difference at ` +
			`${percentApart(f, ratio, [1, full])} of its set; full lift at ${percentApart(f, full, [ratio])}): ` +
			'between set and full lift the lift is the linear convention, not a cited law. A typical ' +
			'liquid-trim valve lifts more slowly, surges to full lift near 107 % of set and recloses ' +
			'near 90 % (Pentair TP-V300 Fig. 4-12). A valve that has surged open passes more flow at a ' +
			'lower inlet pressure.'
		);
	}
	const mu = n('value');
	const lower = n('lower');
	const kv = n('kv');
	const re = n('reynoldsNumber');
	if (mu === null || lower === null || kv === null || re === null) return null;
	const show = (si: number, sig: number) => formatValue(si, 'viscosity', f.prefs, sig);
	const sig = digitsApart(mu, [lower], show);
	return (
		`The liquid's viscosity (${show(mu, sig)}) is at or above ${show(lower, sig)}, where API 520 ` +
		`(10th edition) corrects the capacity by its viscosity factor Kv (${f.plain(kv)} at the ` +
		`solved flow, Reynolds number ${f.plain(re)} on the orifice). Kv is not applied, so the ` +
		'capacity solved is likely overstated and the inlet pressure at this flow understated.'
	);
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
			// A relieving relief valve's jet leaves it at its back pressure (proposal
			// pressure-relief-valve.md decision 15).
			const back = number(flag, 'backAbsolutePressure');
			if (back !== null) {
				const vaporSi = number(flag, 'vaporPressure');
				const show = (si: number, sig: number) =>
					formatValue(si, 'pressure', context.prefs, sig, { absolute: true });
				const sig = digitsApart(back, vaporSi === null ? [0] : [vaporSi], show);
				const limit = vaporSi === null ? bound : `the vapor pressure (${show(vaporSi, sig)})`;
				return `The absolute static pressure at its outlet is ${show(back, sig)}, below ${limit} while it relieves: the jet leaves the valve at that back pressure, so the liquid would flash there and the flow solved is too high.`;
			}
			// An orifice plate's jet (decision 15): at the vena contracta, not at a port.
			const jet = value('venaContractaAbsolutePressure', 'pressure', { absolute: true });
			if (jet)
				return `The absolute pressure at its vena contracta is ${jet}, below ${bound}: the liquid would flash there, and a flashing jet chokes the flow, so the flow solved is too high.`;
			const p = value('absolutePressure', 'pressure', { absolute: true });
			if (!p) return fallback();
			// An assigned-flow node (SDD §4.11) has one port, and its flow is fixed whatever the
			// pressure there: the pressure is what carrying that flow takes.
			const owner = flag.componentId ? componentById(context.project, flag.componentId) : null;
			if (owner?.type === 'assigned_flow') {
				return `The absolute pressure at the node is ${p}, below ${bound}: the liquid would flash. The assigned flow is fixed whatever the pressure, and carrying it takes this pressure.`;
			}
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
			if (segment === null) return fallback();
			// The pipe is numbered from segmentIndex, never from the message (the strip renumbers it).
			if (re === null) {
				return `${pipeLabel(segment)}: ${messageText({ ...flag, message: reason(flag.message) }, context)}`;
			}
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
			return reliefText(flag, f) ?? orificeText(flag, f) ?? fallback();
		}
		case 'RELIEF_VALVE_OPEN': {
			const q = value('flow', 'flow');
			const dp = value('totalPressureDifference', 'pressure');
			const ratio = number(flag, 'setRatio');
			const flowRatio = number(flag, 'flowRatio');
			if (!q || !dp || ratio === null || flowRatio === null) return fallback();
			const beyond =
				flowRatio > 1
					? ": beyond its rated overpressure, where API 520's equation holds and the flow grows with the square root of the pressure difference."
					: '.';
			return `At full lift: it relieves ${q} at a total-pressure difference of ${dp} (${percentApart(f, ratio, [1])} of its set pressure), ${percentApart(f, flowRatio, [1])} of its capacity at full lift${beyond}`;
		}
		case 'RELIEF_VALVE_CLOSED': {
			const side = flag.details.side;
			const section = flag.details.section;
			const set = value('setPressure', 'pressure');
			if ((side !== 'inlet' && side !== 'outlet') || !set) return fallback();
			if (section !== 'floating' && section !== 'closed_off') return fallback();
			const what =
				section === 'floating'
					? 'has no fixed pressure level (undetermined pressure)'
					: 'is closed off (no flow reaches it)';
			const limit = value('pressureLimit', 'pressure', { gauge: true });
			const level = limit
				? side === 'inlet'
					? `: every inlet static pressure up to ${limit} (its back pressure plus its set)`
					: `: every back pressure down to ${limit} (its inlet pressure less its set)`
				: '';
			// The levels at which this valve stays closed, as the API words them: the other elements
			// around the section have rules of their own, so not each level is a steady state.
			return `Closed, with no result: the section on its ${side} side ${what}, so the pressure difference across it is undetermined. It stays closed at every level of that section at which the difference does not exceed its set pressure (${set})${level}; whether such a level is a steady state depends also on the other elements around that section.`;
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
		case 'PUMP_SETPOINT_NOT_MET': {
			// A speed-controlled pump at a limit of its drive (CLAUDE.md D11); details from the API.
			const setpoint = value('setpoint', 'flow');
			const q = value('flow', 'flow');
			const state = flag.details.state;
			if (!setpoint || !q) return fallback();
			if (state === 'max_speed') {
				const speed = value('maxSpeed', 'fraction');
				if (!speed) return fallback();
				return `It runs at its maximum speed (${speed}) and delivers ${q}, below its flow setpoint (${setpoint}).`;
			}
			if (state === 'min_speed') {
				const speed = value('minSpeed', 'fraction');
				if (!speed) return fallback();
				return `It runs at its minimum speed (${speed}) and passes ${q}, above its flow setpoint (${setpoint}): the system drives more flow through it even at that speed.`;
			}
			if (state === 'no_flow') {
				const speed = value('maxSpeed', 'fraction');
				if (!speed) return fallback();
				// closedOff (the API's details): the side or sides closed off. Then no head exceeds
				// the shutoff head: a pump with one side closed off develops exactly that head.
				const closedOff = flag.details.closedOff;
				if (closedOff === 'both') {
					return `It is held at no flow at its maximum speed (${speed}) and both its sides are closed off, so it delivers none of its flow setpoint (${setpoint}).`;
				}
				if (closedOff === 'suction' || closedOff === 'discharge') {
					return `It has no flow: its ${closedOff} is closed off, so it runs dead-headed at its shutoff head at its maximum speed (${speed}) and delivers none of its flow setpoint (${setpoint}).`;
				}
				if (closedOff !== undefined) return fallback();
				return `It has no flow: the head across it exceeds its shutoff head at its maximum speed (${speed}), so it delivers none of its flow setpoint (${setpoint}).`;
			}
			return fallback();
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
