/**
 * Compare cases (proposal scenario-manager.md §6.12): chosen results of each case side by side,
 * with each scenario's difference from the base case.
 *
 * Every value comes from a case's solved state; nothing is computed here but differences of
 * values the API returned, in the display units. A difference is the scenario's value minus the
 * base case's, with a true minus sign and + for an increase. A relative difference is given only
 * for quantities with a true zero (flows, velocities, a pump's head, head losses, power, speed),
 * never for gauge pressures, grade lines, elevations or NPSH margins. "Same" means the two values
 * display the same: there is no tolerance snapping (D6 and D13 are acceptance rules for solver
 * changes; differences between cases are real results of changed inputs). A case that did not
 * converge shows no values, since they are not a solution; its status row says so.
 */
import type { Flag, Project, SolvedState, SolveResponse, UnitPreferences } from '../api/types';
import type { CaseStatus, ResultsState } from '../state/project.svelte';
import { componentById, connectionById } from './graph';
import { portLabel } from './labels';
import {
	connectionName,
	fastestLink,
	Formatter,
	lowestPressureNode,
	pumpStatusLabel,
	valveStateLabel,
	type ElementRef
} from './results';
import { overridesOf, scenariosOf } from './scenarios';
import { formatNumber, type LabelOptions, type UnitCategory } from './units';

/** What a comparison row shows. */
export type Quantity =
	| 'status'
	| 'lowestPressure'
	| 'highestVelocity'
	| 'fluidDensity'
	| 'fluidVaporPressure'
	| 'pumpFlow'
	| 'pumpHead'
	| 'pumpSpeed'
	| 'pumpEfficiency'
	| 'pumpShaftPower'
	| 'pumpNpsha'
	| 'pumpNpshMargin'
	| 'pumpStatus'
	| 'valveFlow'
	| 'valveHeadLoss'
	| 'valvePressureDrop'
	| 'valveState'
	| 'valveSetpointMet'
	| 'linkFlow'
	| 'linkVelocity'
	| 'linkHeadLoss'
	| 'portPressure'
	| 'portAbsolutePressure'
	| 'portHgl'
	| 'portEgl'
	| 'boundaryOutflow'
	| 'boundaryEgl'
	| 'assignedPressure'
	| 'assignedHgl';

/** One row: a quantity of an element (a component, a connection, a port) or of the network. */
export interface CompareRow {
	quantity: Quantity;
	/** The component or connection; absent for a quantity of the whole network. */
	elementId?: string;
	/** The port, for a port's quantity. */
	portId?: string;
}

interface Spec {
	label: string;
	/** Numbers are compared; text is shown as it is. */
	category?: UnitCategory;
	options?: LabelOptions;
	/** A relative difference is meaningful (a true zero). */
	relative?: boolean;
	element: 'network' | 'pump' | 'valve' | 'connection' | 'port' | 'boundary' | 'assigned';
	value: (solved: SolvedState, row: CompareRow) => number | string | null | undefined;
	/** Where a network extreme occurs, for the cell's second line. */
	where?: (solved: SolvedState, project: Project) => string;
}

const pump = (s: SolvedState, r: CompareRow) =>
	r.elementId ? s.pumpResults[r.elementId] : undefined;
const valve = (s: SolvedState, r: CompareRow) =>
	r.elementId ? s.valveResults[r.elementId] : undefined;
const link = (s: SolvedState, r: CompareRow) =>
	r.elementId ? s.linkResults[r.elementId] : undefined;
const node = (s: SolvedState, r: CompareRow) =>
	r.elementId && r.portId ? s.nodeResults[`${r.elementId}:${r.portId}`] : undefined;
const boundary = (s: SolvedState, r: CompareRow) =>
	r.elementId ? s.boundaryResults[r.elementId] : undefined;
const assignedNode = (s: SolvedState, r: CompareRow) => {
	const b = boundary(s, r);
	const port = b ? Object.keys(b.portOutflows)[0] : undefined;
	return port === undefined ? undefined : s.nodeResults[`${r.elementId}:${port}`];
};

/** Invalid flags of the network (convergence) and their count, for the status row. */
function statusText(solved: SolvedState, success: boolean): string {
	if (!(success && solved.converged)) return 'Did not converge';
	const invalid = solved.flags.filter((f) => f.severity === 'invalid').length;
	return invalid ? `${invalid} physically invalid` : 'Converged, 0 physically invalid';
}

export const QUANTITIES: Readonly<Record<Quantity, Spec>> = {
	status: { label: 'Status', element: 'network', value: () => null },
	lowestPressure: {
		label: 'Lowest pressure',
		category: 'pressure',
		options: { gauge: true },
		element: 'network',
		value: (s) => lowestPressureNode(s)?.pressure,
		where: (s, p) => {
			const n = lowestPressureNode(s);
			return n
				? `${portLabel(n.portId)} of ${componentById(p, n.componentId)?.name ?? n.componentId}`
				: '';
		}
	},
	highestVelocity: {
		label: 'Highest velocity',
		category: 'velocity',
		relative: true,
		element: 'network',
		value: (s) => fastestLink(s)?.velocity,
		where: (s, p) => {
			const l = fastestLink(s);
			return l ? connectionName(p, l.id) : '';
		}
	},
	fluidDensity: {
		label: 'Fluid density',
		category: 'density',
		element: 'network',
		value: (s) => s.fluid.density
	},
	fluidVaporPressure: {
		label: 'Fluid vapor pressure',
		category: 'pressure',
		options: { absolute: true },
		element: 'network',
		value: (s) => s.fluid.vaporPressure
	},
	pumpFlow: {
		label: 'Flow',
		category: 'flow',
		relative: true,
		element: 'pump',
		value: (s, r) => pump(s, r)?.operatingFlow
	},
	pumpHead: {
		label: 'Head',
		category: 'head',
		relative: true,
		element: 'pump',
		value: (s, r) => pump(s, r)?.operatingHead
	},
	pumpSpeed: {
		label: 'Speed',
		category: 'fraction',
		relative: true,
		element: 'pump',
		value: (s, r) => {
			const p = pump(s, r);
			return p && p.status !== 'off' ? p.speed : null;
		}
	},
	pumpEfficiency: {
		label: 'Efficiency',
		category: 'fraction',
		element: 'pump',
		value: (s, r) => pump(s, r)?.efficiency
	},
	pumpShaftPower: {
		label: 'Shaft power',
		category: 'power',
		relative: true,
		element: 'pump',
		value: (s, r) => pump(s, r)?.shaftPower
	},
	pumpNpsha: {
		label: 'NPSHa',
		category: 'head',
		element: 'pump',
		value: (s, r) => pump(s, r)?.npshAvailable
	},
	pumpNpshMargin: {
		label: 'NPSH margin',
		category: 'head',
		element: 'pump',
		value: (s, r) => pump(s, r)?.npshMargin
	},
	pumpStatus: {
		label: 'Status',
		element: 'pump',
		value: (s, r) => {
			const p = pump(s, r);
			return p ? pumpStatusLabel(p, flagsOf(s.flags, r)) : null;
		}
	},
	valveFlow: {
		label: 'Flow',
		category: 'flow',
		relative: true,
		element: 'valve',
		value: (s, r) => valve(s, r)?.flow
	},
	valveHeadLoss: {
		label: 'Head loss',
		category: 'head',
		relative: true,
		element: 'valve',
		value: (s, r) => valve(s, r)?.headLoss
	},
	valvePressureDrop: {
		label: 'Pressure drop',
		category: 'pressure',
		element: 'valve',
		value: (s, r) => valve(s, r)?.pressureDrop
	},
	valveState: {
		label: 'State',
		element: 'valve',
		value: (s, r) => {
			const v = valve(s, r);
			return v ? valveStateLabel(v.state) : null;
		}
	},
	valveSetpointMet: {
		label: 'Setpoint met',
		element: 'valve',
		value: (s, r) => {
			const met = valve(s, r)?.setpointAchieved;
			return met === null || met === undefined ? null : met ? 'Yes' : 'No';
		}
	},
	linkFlow: {
		label: 'Flow',
		category: 'flow',
		relative: true,
		element: 'connection',
		value: (s, r) => link(s, r)?.flow
	},
	linkVelocity: {
		label: 'Largest velocity',
		category: 'velocity',
		relative: true,
		element: 'connection',
		value: (s, r) => {
			const l = link(s, r);
			return l
				? Math.max(...[l.velocity, ...l.segments.map((x) => x.velocity)].map(Math.abs))
				: null;
		}
	},
	linkHeadLoss: {
		label: 'Head loss',
		category: 'head',
		relative: true,
		element: 'connection',
		value: (s, r) => link(s, r)?.headLoss
	},
	portPressure: {
		label: 'Pressure',
		category: 'pressure',
		options: { gauge: true },
		element: 'port',
		value: (s, r) => node(s, r)?.pressure
	},
	portAbsolutePressure: {
		label: 'Absolute pressure',
		category: 'pressure',
		options: { absolute: true },
		element: 'port',
		value: (s, r) => node(s, r)?.absolutePressure
	},
	portHgl: { label: 'HGL', category: 'head', element: 'port', value: (s, r) => node(s, r)?.hgl },
	portEgl: { label: 'EGL', category: 'head', element: 'port', value: (s, r) => node(s, r)?.egl },
	boundaryOutflow: {
		label: 'Outflow',
		category: 'flow',
		relative: true,
		element: 'boundary',
		value: (s, r) => boundary(s, r)?.outflow
	},
	boundaryEgl: {
		label: 'EGL',
		category: 'head',
		element: 'boundary',
		value: (s, r) => boundary(s, r)?.egl
	},
	assignedPressure: {
		label: 'Pressure',
		category: 'pressure',
		options: { gauge: true },
		element: 'assigned',
		value: (s, r) => assignedNode(s, r)?.pressure
	},
	assignedHgl: {
		label: 'HGL',
		category: 'head',
		element: 'assigned',
		value: (s, r) => assignedNode(s, r)?.hgl
	}
};

/** The quantities that can be compared for each kind of element (the Choose results dialog). */
export const ELEMENT_QUANTITIES: Readonly<Record<Spec['element'], readonly Quantity[]>> = {
	network: ['status', 'lowestPressure', 'highestVelocity', 'fluidDensity', 'fluidVaporPressure'],
	pump: [
		'pumpFlow',
		'pumpHead',
		'pumpSpeed',
		'pumpEfficiency',
		'pumpShaftPower',
		'pumpNpsha',
		'pumpNpshMargin',
		'pumpStatus'
	],
	valve: ['valveFlow', 'valveHeadLoss', 'valvePressureDrop', 'valveState', 'valveSetpointMet'],
	connection: ['linkFlow', 'linkVelocity', 'linkHeadLoss'],
	port: ['portPressure', 'portAbsolutePressure', 'portHgl', 'portEgl'],
	boundary: ['boundaryOutflow', 'boundaryEgl'],
	assigned: ['assignedPressure', 'assignedHgl']
};

function flagsOf(flags: readonly Flag[], row: CompareRow): Flag[] {
	if (!row.elementId) return [];
	return flags.filter(
		(f) => f.componentId === row.elementId || (!f.componentId && f.connectionId === row.elementId)
	);
}

/** A row's identity (rows are unique by it). */
export function rowKey(row: CompareRow): string {
	return [row.quantity, row.elementId ?? '', row.portId ?? ''].join('\u0000');
}

/** "Pump A · Flow", "Network · Lowest pressure", "Outlet of Gate valve V1 · Pressure". */
export function rowLabel(project: Project, row: CompareRow): string {
	const spec = QUANTITIES[row.quantity];
	if (!row.elementId) return `Network · ${spec.label}`;
	if (spec.element === 'connection')
		return `${connectionName(project, row.elementId)} · ${spec.label}`;
	const name = componentById(project, row.elementId)?.name ?? row.elementId;
	if (spec.element === 'port' && row.portId)
		return `${portLabel(row.portId)} of ${name} · ${spec.label}`;
	return `${name} · ${spec.label}`;
}

/** The unit of a row's numbers in the display units ("L/s"); '' for text. */
export function rowUnit(row: CompareRow, prefs: UnitPreferences): string {
	const spec = QUANTITIES[row.quantity];
	return spec.category ? new Formatter(prefs).unit(spec.category, spec.options ?? {}) : '';
}

/** The element a row opens (its trace), if any. */
export function rowElement(project: Project, row: CompareRow): ElementRef | null {
	if (!row.elementId) return null;
	if (QUANTITIES[row.quantity].element === 'connection') {
		return connectionById(project, row.elementId)
			? { kind: 'connection', id: row.elementId }
			: null;
	}
	return componentById(project, row.elementId) ? { kind: 'component', id: row.elementId } : null;
}

/** At most this many default rows. */
export const DEFAULT_ROW_LIMIT = 40;

/**
 * The default rows (proposal §6.12): the network's status; each pump's flow and head, its NPSH
 * margin where the base case has one, and its speed where a case flow-controls it or changes its
 * speed; each element a scenario changes (a valve's flow and state, a reservoir's or reference
 * node's outflow, a pipe's connection flow and head loss, the fluid's density and vapor
 * pressure); each assigned-flow node's pressure; the lowest pressure and the highest velocity.
 * Pumps and changed elements first, at most 40.
 */
export function defaultRows(
	project: Project,
	cases: readonly (SolvedState | null)[]
): CompareRow[] {
	const rows: CompareRow[] = [{ quantity: 'status' }];
	const base = cases[0] ?? null;
	const changes = scenariosOf(project).flatMap((s) => [...overridesOf(s)]);
	for (const component of project.components) {
		if (component.type !== 'pump') continue;
		const id = component.id;
		rows.push({ quantity: 'pumpFlow', elementId: id }, { quantity: 'pumpHead', elementId: id });
		const margin = base?.pumpResults[id]?.npshMargin;
		if (margin !== null && margin !== undefined)
			rows.push({ quantity: 'pumpNpshMargin', elementId: id });
		const controlled =
			component.control ||
			cases.some((s) => s?.pumpResults[id]?.control) ||
			changes.some((o) => o.kind === 'component' && o.componentId === id && o.field === 'speed');
		if (controlled) rows.push({ quantity: 'pumpSpeed', elementId: id });
	}
	for (const o of changes) {
		if (o.kind === 'component') {
			const component = componentById(project, o.componentId);
			if (component?.type === 'valve') {
				rows.push(
					{ quantity: 'valveFlow', elementId: o.componentId },
					{ quantity: 'valveState', elementId: o.componentId }
				);
			} else if (component?.type === 'reservoir' || component?.type === 'reference_node') {
				rows.push({ quantity: 'boundaryOutflow', elementId: o.componentId });
			}
		} else if (o.kind === 'pipe') {
			if (connectionById(project, o.connectionId)) {
				rows.push(
					{ quantity: 'linkFlow', elementId: o.connectionId },
					{ quantity: 'linkHeadLoss', elementId: o.connectionId }
				);
			}
		} else {
			rows.push({ quantity: 'fluidDensity' }, { quantity: 'fluidVaporPressure' });
		}
	}
	for (const component of project.components) {
		if (component.type === 'assigned_flow')
			rows.push({ quantity: 'assignedPressure', elementId: component.id });
	}
	const seen = new Set<string>();
	const unique = rows.filter((r) => !seen.has(rowKey(r)) && !!seen.add(rowKey(r)));
	// The network's extremes always end the defaults; the rows before them are cut to fit.
	const extremes: CompareRow[] = [{ quantity: 'lowestPressure' }, { quantity: 'highestVelocity' }];
	return [...unique.slice(0, DEFAULT_ROW_LIMIT - extremes.length), ...extremes];
}

/**
 * The response a case's values come from, by Compare's rule (D15): none when its latest solve of
 * the project failed or a stopped Solve all run did not reach it (a response it kept is from an
 * earlier version of the project), else its latest response (null without one). Compare cases,
 * the other cases on the pump chart and the export read a case through this one rule (proposal
 * export.md §2.1); whether the response has values (it converged) is decided after it.
 */
export function caseResponse(status: CaseStatus, results: ResultsState): SolveResponse | null {
	return status === 'failed' || status === 'not_reached' ? null : results.response;
}

/** One case's column: its solved state (null: none) and whether its values can be shown. */
export interface CompareColumn {
	solved: SolvedState | null;
	/** The solve converged (false: no values are shown, as they are not a solution). */
	converged: boolean;
}

export interface CompareDiff {
	/** "+1.20 (+9.8 %)", "−2.20", or "Same". */
	text: string;
	/** The exact difference, for a title (and "Same" values that differ beyond the display). */
	title: string;
	same: boolean;
}

export interface CompareCell {
	/** The value as shown ("12.30", "Open"), or "—". */
	text: string;
	/** Where a network extreme occurs ("Suction of Pump A"). */
	where?: string;
	/** Scenario columns only: its difference from the base case, when both have numbers. */
	diff?: CompareDiff;
	/** For text that differs from the base case's: the base's ("Open"). */
	baseText?: string;
	/** The element has a physically invalid flag in this case. */
	invalid: boolean;
}

const MINUS = '−';

function signed(text: string, positive: boolean): string {
	if (text === '0') return '0';
	return positive ? `+${text}` : `${MINUS}${text.replace(/^-/, '')}`;
}

/** The cells of one row: the base case first, then each scenario with its difference. */
export function compareCells(
	row: CompareRow,
	columns: readonly CompareColumn[],
	project: Project,
	prefs: UnitPreferences
): CompareCell[] {
	const spec = QUANTITIES[row.quantity];
	const f = new Formatter(prefs);
	const raw = columns.map((c) => {
		if (!c.solved) return null;
		if (row.quantity === 'status') return statusText(c.solved, c.converged);
		if (!c.converged) return null;
		return spec.value(c.solved, row) ?? null;
	});
	const shown = (v: number | string | null) =>
		v === null
			? '—'
			: typeof v === 'number'
				? spec.category
					? f.num(v, spec.category)
					: f.plain(v)
				: v;
	const base = raw[0] ?? null;
	return columns.map((column, i) => {
		const value = raw[i] ?? null;
		const invalid =
			!!column.solved &&
			!!row.elementId &&
			flagsOf(column.solved.flags, row).some((flag) => flag.severity === 'invalid');
		const cell: CompareCell = { text: shown(value), invalid };
		if (spec.where && column.solved && column.converged && value !== null) {
			cell.where = spec.where(column.solved, project);
		}
		if (i === 0 || value === null || base === null) return cell;
		if (typeof value === 'number' && typeof base === 'number' && spec.category) {
			const exact = value - base;
			const exactText = f.value(exact, spec.category, {});
			if (shown(value) === shown(base)) {
				cell.diff = { text: 'Same', title: `Difference: ${exactText}`, same: true };
				return cell;
			}
			let text = signed(f.num(Math.abs(exact), spec.category), exact > 0);
			if (spec.relative && base !== 0) {
				const percent = (exact / Math.abs(base)) * 100;
				text += ` (${signed(formatNumber(Math.abs(percent), 3), percent > 0)} %)`;
			}
			cell.diff = { text, title: `Difference: ${exactText}`, same: false };
		} else if (typeof value === 'string' && value !== base) {
			cell.baseText = String(base);
		}
		return cell;
	});
}
