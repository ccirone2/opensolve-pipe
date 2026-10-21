/**
 * Trace values for display (design §5, GOALS §4.2). The API reports trace inputs and intermediate
 * values in SI with a unit string. The unit string alone decides how a value is converted; the
 * value's name never changes a number or a gauge/absolute marker. Unit strings understood:
 *
 * - 'm', 'm³/s' (or 'm3/s'), 'm/s', 'kg/m³', 'Pa·s', 'W': converted to the display unit. A length
 *   in 'm' is shown in the diameter, head or length display unit depending on what it is (all
 *   are lengths, so the number is right either way).
 * - 'Pa(g)' / 'Pa (gauge)': a gauge pressure, labelled "(g)" / "psig".
 * - 'Pa(a)' / 'Pa (absolute)': an absolute pressure, labelled "(a)" / "psia".
 * - 'Pa (difference)': a pressure difference, no marker.
 * - 'Pa': converted (a pressure conversion has no offset, so the number is right whatever the
 *   reference), with "(reference not stated)" unless the name states it (gauge, absolute) or
 *   names a difference (drop, rise, change, margin, ...).
 * - 'K' and anything else: shown exactly as reported. A kelvin value may be a temperature or a
 *   temperature difference, which convert differently, and the unit string does not say which.
 *
 * Only units change: no value is computed.
 */
import type { MethodsSummary, Project, UnitPreferences } from '../api/types';
import { componentById } from './graph';
import { portLabel } from './labels';
import { displayUnit, unitLabel, type LabelOptions, type UnitCategory } from './units';
import { formatResultNumber, Formatter } from './results';

export interface QuantityMapping {
	category: UnitCategory;
	options: LabelOptions;
	/** A pressure whose reference (gauge or absolute) is not stated by its unit or name. */
	referenceUnstated?: boolean;
}

const GAUGE_UNITS = new Set(['Pa(g)', 'Pa (gauge)', 'Pa gauge', 'Pa(gauge)']);
const ABSOLUTE_UNITS = new Set(['Pa(a)', 'Pa (absolute)', 'Pa absolute', 'Pa(absolute)']);
const DIFFERENCE_UNITS = new Set(['Pa (difference)', 'Pa(d)', 'Pa difference', 'Pa(difference)']);

/** Names that state a pressure's reference, or name a difference (which has none). */
const REFERENCE_STATED =
	/gauge|absolute|drop|differen|change|rise|loss|margin|above|below|increase|decrease|delta|Δ/i;

/**
 * The display category for a value named `name` reported in SI unit `unit`, or null when the
 * unit is not one this app converts (it is then shown as reported). See the module comment.
 */
export function quantityMapping(name: string, unit: string): QuantityMapping | null {
	const u = unit.trim();
	if (u === 'm') {
		if (/diam|rough|bore|\bID\b/i.test(name)) return { category: 'diameter', options: {} };
		if (/head|loss|grade|egl|hgl|npsh|level/i.test(name)) return { category: 'head', options: {} };
		return { category: 'length', options: {} };
	}
	if (u === 'm³/s' || u === 'm3/s' || u === 'm^3/s') return { category: 'flow', options: {} };
	if (u === 'm/s') return { category: 'velocity', options: {} };
	if (GAUGE_UNITS.has(u)) return { category: 'pressure', options: { gauge: true } };
	if (ABSOLUTE_UNITS.has(u)) return { category: 'pressure', options: { absolute: true } };
	if (DIFFERENCE_UNITS.has(u)) return { category: 'pressure', options: {} };
	if (u === 'Pa') {
		return REFERENCE_STATED.test(name)
			? { category: 'pressure', options: {} }
			: { category: 'pressure', options: {}, referenceUnstated: true };
	}
	if (u === 'kg/m³' || u === 'kg/m3' || u === 'kg/m^3') return { category: 'density', options: {} };
	if (u === 'Pa·s' || u === 'Pa.s' || u === 'Pa s') return { category: 'viscosity', options: {} };
	if (u === 'W') return { category: 'power', options: {} };
	return null;
}

export interface QuantityText {
	/** In display units with the unit label, e.g. "50.12 L/s". */
	text: string;
	/** The SI value as reported, when it differs from `text` (e.g. "0.05012 m³/s"). */
	si?: string;
}

/** A trace value (number, text, yes/no or none) for display. */
export function formatQuantity(
	name: string,
	value: number | string | boolean | null,
	unit: string,
	prefs: UnitPreferences
): QuantityText {
	if (value === null) return { text: '—' };
	if (typeof value === 'boolean') return { text: value ? 'Yes' : 'No' };
	if (typeof value === 'string') return { text: unit && unit !== '-' ? `${value} ${unit}` : value };
	const raw = formatResultNumber(value);
	const reported = unit && unit !== '-' && unit !== '1' ? `${raw} ${unit}` : raw;
	const mapping = quantityMapping(name, unit);
	if (!mapping) return { text: reported };
	const converted = new Formatter(prefs).value(value, mapping.category, mapping.options);
	const text = mapping.referenceUnstated ? `${converted} (reference not stated)` : converted;
	const siLabel = unitLabel(
		mapping.category,
		displayUnit(mapping.category, prefs),
		mapping.options
	);
	const same = converted === reported || converted === `${raw} ${siLabel}`;
	return same ? { text } : { text, si: reported };
}

/**
 * A trace text value that is a port's node key ("P1:discharge", the API's id of a port: ids
 * contain no ':'), named as in Build with the key kept for reference: "Discharge of Transfer
 * pump (P1:discharge)". Any other text is returned as it is.
 */
export function traceTextValue(value: string, project: Project): string {
	const match = /^([A-Za-z0-9_-]+):([A-Za-z0-9_-]+)$/.exec(value);
	if (!match) return value;
	const [, componentId = '', portId = ''] = match;
	const component = componentById(project, componentId);
	if (!component?.ports.some((p) => p.id === portId)) return value;
	return `${portLabel(portId)} of ${component.name} (${value})`;
}

/**
 * A trace input or value name, with the numbering and port names used in Build: the API numbers
 * a connection's pipe segments and fittings from 0 ("Segment 0", "Fitting 0 (bend)"), Build from
 * 1, so the Build number is added ("Segment 0 (pipe 1)"); a port id in "Port port_1 outflow" of
 * component `elementId` becomes its label ("Port 1 outflow"). Only names change, never values.
 */
export function traceName(name: string, project: Project, elementId: string): string {
	const segment = /^Segment (\d+)\b/.exec(name);
	if (segment) {
		const n = Number(segment[1]);
		return `Segment ${n} (pipe ${n + 1})${name.slice(segment[0].length)}`;
	}
	const fitting = /^Fitting (\d+) \(/.exec(name);
	if (fitting) {
		const n = Number(fitting[1]);
		return `Fitting ${n} (fitting ${n + 1}, ${name.slice(fitting[0].length)}`;
	}
	const port = /^Port ([A-Za-z0-9_-]+)\b/.exec(name);
	const component = componentById(project, elementId);
	if (port && component?.ports.some((p) => p.id === port[1])) {
		return `${portLabel(port[1] as string)}${name.slice(port[0].length)}`;
	}
	return name;
}

export interface MethodsTextContext {
	projectName?: string;
	/** When the solve ran (ISO 8601). */
	timestamp?: string;
	/** Whether the solve converged (false: its values are not a solution). */
	converged?: boolean;
	/** True when the project changed after the solve. */
	stale?: boolean;
}

/** The solve-status lines of the methods text (none when the state is not given). */
export function solveStatusLines(context: MethodsTextContext): string[] {
	const lines: string[] = [];
	if (context.converged === true) lines.push('Solve status: converged.');
	if (context.converged === false) {
		lines.push(
			'Solve status: DID NOT CONVERGE. The values are from the last iteration; they are not a solution of the network and must not be used.'
		);
	}
	if (context.stale) {
		lines.push(
			'Results out of date: the project changed after this solve. Solve again before using these results.'
		);
	}
	return lines;
}

/**
 * The methods summary as plain text, for pasting into a report: a heading, the project, the
 * solve's time and status (converged or not, out of date or not), each section with its items
 * and references, the assumptions, and the software versions.
 */
export function methodsText(methods: MethodsSummary, context: MethodsTextContext = {}): string {
	const lines: string[] = ['Calculation methods and assumptions'];
	if (context.projectName) lines.push(`Project: ${context.projectName}`);
	lines.push(`OpenSolve Pipe calculation methods version ${methods.methodVersion}`);
	if (context.timestamp) lines.push(`Solved: ${context.timestamp}`);
	lines.push(...solveStatusLines(context));
	for (const section of methods.sections) {
		lines.push('', section.title);
		for (const item of section.items) lines.push(`- ${item}`);
		if (section.references.length) {
			lines.push('References:');
			for (const ref of section.references) lines.push(`- ${ref}`);
		}
	}
	if (methods.assumptions.length) {
		lines.push('', 'Assumptions');
		for (const item of methods.assumptions) lines.push(`- ${item}`);
	}
	const libraries = Object.entries(methods.libraries);
	if (libraries.length) {
		lines.push('', 'Software');
		for (const [name, version] of libraries) lines.push(`- ${name} ${version}`);
	}
	return lines.join('\n') + '\n';
}
