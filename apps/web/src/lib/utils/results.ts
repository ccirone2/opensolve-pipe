/**
 * Results for display (design §5): the solver's SI values arranged as tables, in the project's
 * display units, with element names and the physics flags that belong to each row.
 *
 * Nothing here computes a hydraulic value. Every number shown comes from the SolvedState the API
 * returned; this module only selects, orders, converts units (units.ts) and labels them. Names
 * come from the current project; an element that no longer exists (results kept after an edit)
 * is shown by its id. A connection's "From → To" (its ends and their names) comes from the project
 * the results belong to (resultsProject): the project as solved once they are out of date, as the
 * sign of its flow does. Where out-of-date values are shown against a connection as it is now
 * (Build's strip and pipe hints, Compare cases), linkReading finds the direction and the pipes
 * they refer to, exactly or not at all: a value in the other direction is given with the other
 * sign (the one change made to a number here), and one it cannot place is left out.
 */
import type {
	BoundaryResult,
	BranchResult,
	Component,
	EquipmentResult,
	Flag,
	LinkResult,
	NodeResult,
	OrificeResult,
	PipeConnection,
	Project,
	PumpResult,
	ReliefValveResult,
	SegmentResult,
	SolvedState,
	UnitPreferences,
	ValveResult
} from '../api/types';
import { DIRECTION_NAMES, flowDirection } from './assigned-flow';
import { reversePiping } from './edit';
import { componentById, connectionById } from './graph';
import { originOf } from './identity';
import { canonicalJson } from './json';
import {
	fittingFallbackName,
	humanize,
	kindLabel,
	portLabel,
	PUMP_CONTROL_MODE_NAMES,
	PUMP_CONTROL_STATE_LABELS
} from './labels';
import { reliefStateLabel } from './relief';
import {
	displayUnit,
	formatNumber,
	fromSI,
	STANDARD_GRAVITY,
	toSI,
	unitLabel,
	type LabelOptions,
	type UnitCategory,
	type UnitId
} from './units';

/** Significant figures shown in results (design §5). */
export const RESULT_DIGITS = 4;

/**
 * m. Heads, elevations and lengths are shown to at least this resolution (D6: results are
 * checked to 0.01 m of head), and to 4 significant figures where that is finer. Four
 * significant figures alone resolve only 1 m on a grade line 1000 m above the datum, which
 * hides the loss across a valve or the velocity head (design §5 note: "4 s.f., or 0.01 m for
 * lengths and heads, whichever is finer").
 */
export const HEAD_RESOLUTION = 0.01;

/**
 * m. Head differences smaller than the solver's energy tolerance (API solver/gga.py ENERGY_TOL)
 * are not resolved by the solve: they are round-off, shown as "≈ 0" (the exact value is kept in
 * the cell's title).
 */
export const HEAD_NOISE = 1e-7;

/** Branch K values converge to this tolerance (API solver/status.py K_TOL); smaller is "≈ 0". */
export const K_NOISE = 1e-4;

const SUPERSCRIPT: Readonly<Record<string, string>> = {
	'-': '⁻',
	'0': '⁰',
	'1': '¹',
	'2': '²',
	'3': '³',
	'4': '⁴',
	'5': '⁵',
	'6': '⁶',
	'7': '⁷',
	'8': '⁸',
	'9': '⁹'
};

/**
 * A result number: 4 significant figures (at least `decimals` decimals when given), and very
 * small or large numbers as 2.555×10⁻⁶ instead of "2.555e-6".
 */
export function formatResultNumber(value: number, decimals = 0): string {
	if (!Number.isFinite(value)) return '—';
	if (value === 0) return '0';
	const text = formatNumber(value, RESULT_DIGITS);
	const exponent = /^(-?[\d.]+)e([+-]?\d+)$/.exec(text);
	if (exponent) {
		const power = (exponent[2] ?? '').replace('+', '');
		return `${exponent[1]}×10${[...power].map((c) => SUPERSCRIPT[c] ?? c).join('')}`;
	}
	if (decimals > 0 && (text.split('.')[1]?.length ?? 0) < decimals) {
		return String(Number(value.toFixed(decimals)));
	}
	return text;
}

/** Decimals that resolve HEAD_RESOLUTION in a length unit (m: 2, ft: 2, in: 1, mm: 0). */
function headDecimals(unit: UnitId): number {
	const resolution = HEAD_RESOLUTION / (toSI(1, unit) - toSI(0, unit));
	return Math.max(0, Math.ceil(-Math.log10(resolution) - 1e-9));
}

export type ElementKind = 'component' | 'connection';

/** An element of the network that results, flags and traces refer to. */
export interface ElementRef {
	kind: ElementKind;
	id: string;
}

export type Severity = Flag['severity'];

/** Severity order of the flags summary: physically invalid first. */
export const SEVERITIES: readonly Severity[] = ['invalid', 'warning', 'info'];

export const SEVERITY_LABELS: Readonly<Record<Severity, string>> = {
	invalid: 'Invalid',
	warning: 'Warning',
	info: 'Info'
};

export const SEVERITY_TITLES: Readonly<Record<Severity, string>> = {
	invalid: 'Physically invalid',
	warning: 'Warnings',
	info: 'Information'
};

export interface FlagGroup {
	severity: Severity;
	flags: Flag[];
}

/** Flags grouped by severity (invalid, warning, info), keeping their order; empty groups left out. */
export function groupFlags(flags: readonly Flag[]): FlagGroup[] {
	return SEVERITIES.map((severity) => ({
		severity,
		flags: flags.filter((f) => f.severity === severity)
	})).filter((g) => g.flags.length > 0);
}

/** The element a flag is about: its component, else its connection; null for a network-wide flag. */
export function flagElement(flag: Flag): ElementRef | null {
	if (flag.componentId) return { kind: 'component', id: flag.componentId };
	if (flag.connectionId) return { kind: 'connection', id: flag.connectionId };
	return null;
}

export function sameElement(a: ElementRef | null | undefined, b: ElementRef | null | undefined) {
	return !!a && !!b && a.kind === b.kind && a.id === b.id;
}

/** Flags about one element (for a component: any of its ports). */
export function flagsForElement(flags: readonly Flag[], element: ElementRef): Flag[] {
	return flags.filter((f) =>
		element.kind === 'component'
			? f.componentId === element.id
			: f.connectionId === element.id && !f.componentId
	);
}

/** What each solve's results belong to, recorded by the store (see recordResultsProject). */
const resultsProjects = new WeakMap<SolvedState, () => Project | null>();

/**
 * Record the project a solve's results belong to once they are out of date: `outOfDate` gives
 * null while they are current, else the project exactly as sent for that solve. The store calls it
 * for every response it keeps. A getter, so a table derived from it follows its results going out
 * of date (it reads the store's state).
 */
export function recordResultsProject(solved: SolvedState, outOfDate: () => Project | null): void {
	resultsProjects.set(solved, outOfDate);
}

/**
 * The project that labels a solve's connections, "From → To" (proposal export.md decision 8):
 * `current` while its results are current (their staleness key, names left out, equals the current
 * project's, so every connection joins the same ends), else the project as sent for that solve. So
 * after a reversal made since the solve, a row names the ends its flow sign refers to, and an id
 * given since to another element does not lend that element's name. `current` for a solve the
 * store did not record (a table built outside it).
 */
export function resultsProject(current: Project, solved: SolvedState): Project {
	return outOfDateProject(solved) ?? current;
}

/**
 * The project exactly as sent for a solve whose results are out of date; null while they are
 * current, and for a solve the store did not record (see recordResultsProject).
 */
export function outOfDateProject(solved: SolvedState): Project | null {
	return resultsProjects.get(solved)?.() ?? null;
}

/** A pipe of the current project as a pipe of a solve (identity.ts). */
export interface PipeReading {
	/** The connection it was in for the solve, and its index there (SegmentResult.index). */
	connectionId: string;
	index: number;
	/** -1 where it now runs the other way in its connection: its signed values are negated. */
	sign: 1 | -1;
}

/**
 * How a solve's values of a connection read on that connection as it is now. The API signs a
 * connection's flow, velocities and head losses from its 'from' end to its 'to' end, and numbers
 * its pipes and fittings in its order, as it was solved; an edit since may have reversed it (an
 * insertion turns a connection drawn against the flow, a join may turn either side), moved an end
 * (an insertion, a join), added or removed pipes, or given its id to a new connection.
 */
export interface LinkReading {
	/**
	 * The sign that gives its flow at the solve in its current direction: from its ends when it is
	 * the connection solved between the same two ports (`ends`), else from its pipes when it holds
	 * pipes solved in it and none solved in another connection (an insertion moved an end); null
	 * when neither tells (a join of two, an id used again).
	 */
	flow: 1 | -1 | null;
	/**
	 * The sign of values between its ends (head loss): null unless it joins the same two ports as
	 * solved and is the connection solved there, holding pipes solved in it and none solved in
	 * another connection. Ids are used again (the first free one), so a new connection can join
	 * the solved ports under the solved id: its pipes tell it apart.
	 */
	ends: 1 | -1 | null;
	/**
	 * Why `ends` is null: 'ends', an end moved (an insertion, a join, an id used again with other
	 * ends); 'pipes', it joins the same two ports but holds no pipe solved in it, or one solved in
	 * another connection (an id and its ends used again by a new connection). Null with `ends`.
	 */
	changed: 'ends' | 'pipes' | null;
	/**
	 * Each of its pipes as solved, found by identity (never by position) in any connection of the
	 * solve, the sign from the ends that connection shares with this one (or the order of the
	 * pipes they share); null for a pipe added since, or one whose direction neither tells.
	 */
	pipes: (PipeReading | null)[];
	/**
	 * Its pipes are the pipes solved in it, every one and no other (in any order or direction), so
	 * a value over all of them (its largest velocity) refers to its pipes now.
	 */
	samePipes: boolean;
	/** Its fittings are the ones solved, at the same indexes (only with every pipe in place). */
	fittings: boolean;
}

const sameEnd = (
	a: PipeConnection,
	aEnd: 'from' | 'to',
	b: PipeConnection,
	bEnd: 'from' | 'to'
): boolean =>
	a[`${aEnd}ComponentId`] === b[`${bEnd}ComponentId`] && a[`${aEnd}PortId`] === b[`${bEnd}PortId`];

/** 1: both ends as solved; -1: both swapped (a reversal); null: an end moved. */
function bothEnds(now: PipeConnection, then: PipeConnection): 1 | -1 | null {
	if (sameEnd(now, 'from', then, 'from') && sameEnd(now, 'to', then, 'to')) return 1;
	if (sameEnd(now, 'from', then, 'to') && sameEnd(now, 'to', then, 'from')) return -1;
	return null;
}

/**
 * The direction of `now` relative to `then` for the pipes they share: every edit keeps a pipe on
 * the same side of each end it keeps (it splits or joins connections only at their ends, and a
 * reversal swaps both), so an end at the same side gives 1 and one at the other side -1. Without a
 * shared end, the order of two or more shared pipes tells. Null when nothing tells, or the two
 * disagree (an edit outside the app's own).
 */
function direction(
	now: PipeConnection,
	then: PipeConnection,
	order: readonly (readonly [number, number])[]
): 1 | -1 | null {
	const atEnds =
		sameEnd(now, 'from', then, 'from') || sameEnd(now, 'to', then, 'to')
			? 1
			: sameEnd(now, 'from', then, 'to') || sameEnd(now, 'to', then, 'from')
				? -1
				: null;
	let byOrder: 1 | -1 | null = null;
	if (order.length > 1) {
		const steps = order.slice(1).map(([, j], k) => j - (order[k]?.[1] ?? j));
		if (steps.every((d) => d > 0)) byOrder = 1;
		else if (steps.every((d) => d < 0)) byOrder = -1;
		else return null;
	}
	if (atEnds !== null && byOrder !== null && atEnds !== byOrder) return null;
	return atEnds ?? byOrder;
}

/** Each pipe of a solve's project by its origin (identity.ts): where it was solved. */
const solvedPipes = new WeakMap<Project, Map<object, { connectionId: string; index: number }>>();

function pipesOf(project: Project): Map<object, { connectionId: string; index: number }> {
	let map = solvedPipes.get(project);
	if (!map) {
		const found = new Map<object, { connectionId: string; index: number }>();
		for (const c of project.connections) {
			c.piping.pipes.forEach((pipe, index) =>
				found.set(originOf(pipe), { connectionId: c.id, index })
			);
		}
		solvedPipes.set(project, found);
		map = found;
	}
	return map;
}

/**
 * How `solved`'s values of connection `id` read on it in `structure` (the stored project, whose
 * pipes carry their identity), given `sent`, the project as sent for that solve once its results
 * are out of date (null while they are current: then every value reads as solved). Null when the
 * solve or the project has no such connection.
 */
export function linkReading(
	structure: Project,
	sent: Project | null,
	solved: SolvedState,
	id: string
): LinkReading | null {
	const link = solved.linkResults[id];
	const now = connectionById(structure, id);
	if (!link || !now) return null;
	const count = now.piping.pipes.length;
	const then = sent ? connectionById(sent, id) : undefined;
	if (!sent || !then) {
		// Current: the project is the one solved (its staleness key), each pipe the one in its place.
		const inPlace = link.segments.length === count;
		return {
			flow: 1,
			ends: 1,
			changed: null,
			pipes: now.piping.pipes.map((_, i) =>
				inPlace && link.segments.some((s) => s.index === i)
					? { connectionId: id, index: i, sign: 1 }
					: null
			),
			samePipes: true,
			fittings: true
		};
	}
	const at = pipesOf(sent);
	const found = now.piping.pipes.map((pipe) => at.get(originOf(pipe)) ?? null);
	const signs = new Map<string, 1 | -1 | null>();
	const signOf = (connectionId: string): 1 | -1 | null => {
		if (!signs.has(connectionId)) {
			const was = connectionById(sent, connectionId);
			const order = found.flatMap((f, i) =>
				f?.connectionId === connectionId ? [[i, f.index] as const] : []
			);
			signs.set(connectionId, was ? direction(now, was, order) : null);
		}
		return signs.get(connectionId) ?? null;
	};
	const pipes = found.map((f): PipeReading | null => {
		const sign = f ? signOf(f.connectionId) : null;
		return f && sign !== null ? { ...f, sign } : null;
	});
	// The connection solved here holds pipes solved in it, and none solved in another connection
	// (a join): a new connection that took its id and ends holds only new pipes.
	const own = found.flatMap((f) => (f?.connectionId === id ? [f.index] : []));
	const solvedHere = own.length > 0 && found.every((f) => !f || f.connectionId === id);
	const same = bothEnds(now, then);
	const ends = solvedHere ? same : null;
	const flow = ends ?? (solvedHere ? signOf(id) : null);
	const n = then.piping.pipes.length;
	const samePipes = own.length === count && count === n && new Set(own).size === n;
	const inPlace =
		ends !== null &&
		count === n &&
		pipes.every(
			(p, i) =>
				p?.connectionId === id && p.index === (ends === 1 ? i : n - 1 - i) && p.sign === ends
		);
	const solvedFittings = (ends === -1 ? reversePiping(then.piping) : then.piping).fittings;
	return {
		flow,
		ends,
		changed: ends !== null ? null : same === null ? 'ends' : 'pipes',
		pipes,
		samePipes,
		fittings: inPlace && canonicalJson(now.piping.fittings) === canonicalJson(solvedFittings)
	};
}

/** Whether a reading is the connection as solved: every value reads as the results tables show it. */
export function readsAsSolved(reading: LinkReading): boolean {
	return reading.ends === 1 && reading.fittings;
}

/**
 * Pipe `index` of connection `id` in `structure` as a pipe of the solve (its segment result and
 * the sign of its values in the connection's current direction), or null (see linkReading). The
 * project as sent is the store's record for the solve.
 */
export function solvedPipe(
	structure: Project,
	solved: SolvedState,
	id: string,
	index: number
): { segment: SegmentResult; sign: 1 | -1 } | null {
	const pipe = linkReading(structure, outOfDateProject(solved), solved, id)?.pipes[index];
	const segment = pipe
		? solved.linkResults[pipe.connectionId]?.segments.find((s) => s.index === pipe.index)
		: undefined;
	return pipe && segment ? { segment, sign: pipe.sign } : null;
}

/** "Suction tank → Transfer pump", or the connection id when it no longer exists. */
export function connectionName(project: Project, connectionId: string): string {
	const connection = connectionById(project, connectionId);
	if (!connection) return connectionId;
	const from =
		componentById(project, connection.fromComponentId)?.name ?? connection.fromComponentId;
	const to = componentById(project, connection.toComponentId)?.name ?? connection.toComponentId;
	return `${from} → ${to}`;
}

/** Display name of an element: the component's name, or "from → to" for a connection. */
export function elementName(project: Project, element: ElementRef): string {
	return element.kind === 'component'
		? (componentById(project, element.id)?.name ?? element.id)
		: connectionName(project, element.id);
}

/** "Pump · P1", "Pipe connection · L1". */
export function elementDescription(project: Project, element: ElementRef): string {
	if (element.kind === 'connection') return `Pipe connection · ${element.id}`;
	const component = componentById(project, element.id);
	return component ? `${kindLabel(component)} · ${element.id}` : element.id;
}

const SI_QUANTITY = /(-?\d+(?:\.\d+)?(?:e[+-]?\d+)?) (m³\/s|m\/s|Pa|m)(?![\w³²/])/g;

const SI_CATEGORY: Readonly<Record<string, UnitCategory>> = {
	'm³/s': 'flow',
	'm/s': 'velocity',
	Pa: 'pressure',
	m: 'length'
};

/**
 * Text from the API with SI quantities ("0.0475 m³/s", "-52340.5 Pa", "0.1023 m") shown in the
 * display units. The unit symbol decides the conversion; a length shortly after "D_" or
 * "diameter" is shown in the diameter unit (both are lengths, so the number is right either
 * way). A pressure keeps the gauge or absolute wording of the text: no marker is added.
 */
export function siText(text: string, prefs: UnitPreferences): string {
	const f = new Formatter(prefs);
	return text.replace(SI_QUANTITY, (whole, value: string, unit: string, offset: number) => {
		const si = Number(value);
		let category = SI_CATEGORY[unit];
		if (!category || !Number.isFinite(si)) return whole;
		const before = text.slice(Math.max(0, offset - 40), offset);
		if (category === 'length' && /D_\w|diameter/i.test(before)) category = 'diameter';
		return f.value(si, category);
	});
}

/** A column of a results table. */
export interface Column {
	key: string;
	label: string;
	/** Display unit label ("kPa(g)"); absent for text and pure numbers. */
	unit?: string;
	/** Numbers are right-aligned. */
	numeric?: boolean;
	/** Long text (a citation): wraps in a wider cell. */
	wrap?: boolean;
}

/** Text with a note shown on hover, e.g. "≈ 0" with the exact value the solver returned. */
export interface NotedText {
	text: string;
	title: string;
}

/** One value: text, or text with a note. */
export type Value = string | NotedText;

export function valueText(value: Value): string {
	return typeof value === 'string' ? value : value.text;
}

/** A labelled value inside a cell (e.g. one port of a tee, one pipe of a connection). */
export interface CellPart {
	label: string;
	value: Value;
}

/** A cell: one value, several lines, or labelled values (one per port of a tee). */
export type Cell = Value | string[] | CellPart[];

/** A cell as lines of text ("Run inlet: 50.12"), e.g. for copying or for tests. */
export function cellLines(cell: Cell): string[] {
	if (!Array.isArray(cell)) return [valueText(cell)];
	return cell.map((part) =>
		typeof part === 'string' ? part : `${part.label}: ${valueText(part.value)}`
	);
}

export interface Row {
	key: string;
	element: ElementRef;
	/** Element name (first column). */
	name: string;
	/** Second line of the first column: the port, the id, or the kind. */
	detail: string;
	cells: Record<string, Cell>;
	flags: Flag[];
}

export interface Table {
	columns: Column[];
	rows: Row[];
}

/** Formats SI values in the display units of a project. */
export class Formatter {
	readonly prefs: UnitPreferences;

	constructor(prefs: UnitPreferences) {
		this.prefs = prefs;
	}

	/**
	 * Number only, in the category's display unit: 4 significant figures, and for lengths and
	 * heads at least HEAD_RESOLUTION; "—" for none.
	 */
	num(si: number | null | undefined, category: UnitCategory): string {
		if (si === null || si === undefined || !Number.isFinite(si)) return '—';
		const unit = displayUnit(category, this.prefs);
		const decimals = category === 'head' || category === 'length' ? headDecimals(unit) : 0;
		return formatResultNumber(fromSI(si, unit), decimals);
	}

	/**
	 * A difference the solver resolves only to `noise` (SI, same unit as `si`): smaller values
	 * are round-off and shown as "≈ 0", with the exact value as the note.
	 */
	diff(si: number | null | undefined, category: UnitCategory, noise: number): Value {
		if (si !== null && si !== undefined && si !== 0 && Math.abs(si) < noise) {
			return {
				text: '≈ 0',
				title: `${this.value(si, category)}: round-off, below the solver's resolution`
			};
		}
		return this.num(si, category);
	}

	/** Number with its unit label: "245.2 kPa(g)". */
	value(si: number | null | undefined, category: UnitCategory, options: LabelOptions = {}): string {
		const text = this.num(si, category);
		if (text === '—') return text;
		const unit = displayUnit(category, this.prefs);
		const label = unitLabel(category, unit, options);
		if (!label) return text;
		return unit === 'deg' ? `${text}${label}` : `${text} ${label}`;
	}

	/** Unit label of a category in the display units: "kPa(g)", "psia", "L/s". */
	unit(category: UnitCategory, options: LabelOptions = {}): string {
		return unitLabel(category, displayUnit(category, this.prefs), options);
	}

	/** A pure number (Re, f, K), 4 significant figures. */
	plain(value: number | null | undefined): string {
		return value === null || value === undefined ? '—' : formatResultNumber(value);
	}

	column(key: string, label: string, category?: UnitCategory, options: LabelOptions = {}): Column {
		const unit = category ? this.unit(category, options) : undefined;
		return { key, label, ...(unit ? { unit } : {}), numeric: true };
	}
}

function text(key: string, label: string, wrap = false): Column {
	return wrap ? { key, label, wrap } : { key, label };
}

/** Component ids in project order, then ids of results whose component no longer exists. */
function orderedIds(project: Project, keys: readonly string[]): string[] {
	const known = project.components.map((c) => c.id).filter((id) => keys.includes(id));
	return [...known, ...keys.filter((k) => !known.includes(k))];
}

function componentRow(
	project: Project,
	flags: readonly Flag[],
	id: string,
	cells: Record<string, Cell>
): Row {
	const element: ElementRef = { kind: 'component', id };
	const component = componentById(project, id);
	return {
		key: id,
		element,
		name: component?.name ?? id,
		detail: component ? `${kindLabel(component)} · ${id}` : id,
		cells,
		flags: flagsForElement(flags, element)
	};
}

export const REGIME_LABELS: Readonly<Record<LinkResult['flowRegime'], string>> = {
	none: 'No flow',
	laminar: 'Laminar',
	transitional: 'Transitional',
	turbulent: 'Turbulent'
};

/**
 * Nodes: one row per component port, in project order. Only flags naming that port are shown on
 * the row; flags about a whole component are shown in that component's own table.
 */
export function nodeTable(project: Project, solved: SolvedState, prefs: UnitPreferences): Table {
	const f = new Formatter(prefs);
	const columns: Column[] = [
		f.column('elevation', 'Elevation', 'length'),
		f.column('pressure', 'Pressure', 'pressure', { gauge: true }),
		// ½ρv²: a pressure difference, so neither gauge nor absolute.
		f.column('dynamicPressure', 'Dynamic pressure', 'pressure'),
		f.column('totalPressure', 'Total pressure', 'pressure', { gauge: true }),
		f.column('absolutePressure', 'Absolute pressure', 'pressure', { absolute: true }),
		f.column('velocity', 'Velocity', 'velocity'),
		f.column('hgl', 'HGL', 'head'),
		f.column('egl', 'EGL', 'head')
	];
	const results = solved.nodeResults;
	const keys: string[] = [];
	for (const component of project.components) {
		for (const port of component.ports) {
			const key = `${component.id}:${port.id}`;
			if (results[key]) keys.push(key);
		}
	}
	for (const key of Object.keys(results)) if (!keys.includes(key)) keys.push(key);
	const rows = keys.map((key): Row => {
		const node = results[key] as NodeResult;
		const element: ElementRef = { kind: 'component', id: node.componentId };
		return {
			key,
			element,
			name: componentById(project, node.componentId)?.name ?? node.componentId,
			detail: portLabel(node.portId),
			cells: {
				elevation: f.num(node.elevation, 'length'),
				pressure: f.num(node.pressure, 'pressure'),
				dynamicPressure: f.num(node.dynamicPressure, 'pressure'),
				totalPressure: f.num(node.totalPressure, 'pressure'),
				absolutePressure: f.num(node.absolutePressure, 'pressure'),
				velocity: f.num(node.velocity, 'velocity'),
				hgl: f.num(node.hgl, 'head'),
				egl: f.num(node.egl, 'head')
			},
			flags: solved.flags.filter(
				(flag) => flag.componentId === node.componentId && flag.portId === node.portId
			)
		};
	});
	return { columns, rows };
}

/**
 * Links: one row per connection, in project order, named "From → To" from the project the results
 * belong to (resultsProject), so that the name and the sign of the flow refer to the same ends.
 * Velocity, Re, f and regime are per pipe: a connection of one pipe shows its values; a
 * connection of several shows each pipe's ("Pipe 1", "Pipe 2", ...), since one value (the API's
 * top-level LinkResult values are the first pipe's) would hide a faster or transitional pipe
 * further on.
 */
export function linkTable(project: Project, solved: SolvedState, prefs: UnitPreferences): Table {
	const f = new Formatter(prefs);
	const columns = linkColumns(f);
	const results = solved.linkResults;
	const resultKeys = Object.keys(results);
	const known = project.connections.map((c) => c.id).filter((id) => resultKeys.includes(id));
	const ids = [...known, ...resultKeys.filter((k) => !known.includes(k))];
	const labels = resultsProject(project, solved);
	const rows = ids.map((id): Row => {
		const link = results[id] as LinkResult;
		const element: ElementRef = { kind: 'connection', id };
		const perPipe = link.segments.length > 1;
		const pipeValues = (single: Value, value: (segment: SegmentResult) => Value): Cell =>
			perPipe ? link.segments.map((s) => ({ label: pipeLabel(s.index), value: value(s) })) : single;
		return {
			key: id,
			element,
			name: connectionName(labels, id),
			detail: perPipe ? `${id} · ${link.segments.length} pipes` : id,
			cells: {
				flow: f.num(link.flow, 'flow'),
				velocity: pipeValues(f.num(link.velocity, 'velocity'), (s) =>
					f.num(s.velocity, 'velocity')
				),
				headLoss: f.diff(link.headLoss, 'head', HEAD_NOISE),
				reynoldsNumber: pipeValues(f.plain(link.reynoldsNumber), (s) => f.plain(s.reynoldsNumber)),
				frictionFactor: pipeValues(f.plain(link.frictionFactor), (s) => f.plain(s.frictionFactor)),
				flowRegime: pipeValues(regimeLabel(link.flowRegime), (s) => regimeLabel(s.flowRegime))
			},
			flags: flagsForElement(solved.flags, element)
		};
	});
	return { columns, rows };
}

/** The Links table's columns (also the strip's labels for a connection). */
function linkColumns(f: Formatter): Column[] {
	return [
		f.column('flow', 'Flow', 'flow'),
		f.column('velocity', 'Velocity', 'velocity'),
		f.column('headLoss', 'Head loss', 'head'),
		f.column('reynoldsNumber', 'Re'),
		f.column('frictionFactor', 'f (Darcy)'),
		text('flowRegime', 'Regime')
	];
}

export function regimeLabel(regime: LinkResult['flowRegime']): string {
	return REGIME_LABELS[regime] ?? humanize(regime);
}

/** The UI numbers the pipes of a connection from 1 (the API's segment index is 0-based). */
export function pipeLabel(index: number): string {
	return `Pipe ${index + 1}`;
}

function detailIndex(flag: Flag, key: string): number | null {
	const value = flag.details[key];
	return typeof value === 'number' && Number.isInteger(value) ? value : null;
}

/** Flags of connection `id` about one of its pipes (details.segmentIndex, 0-based). */
export function segmentFlags(flags: readonly Flag[], id: string, index: number): Flag[] {
	return flags.filter(
		(f) => f.connectionId === id && !f.componentId && detailIndex(f, 'segmentIndex') === index
	);
}

/** Flags of connection `id` about one of its fittings (details.fittingIndex). */
export function fittingFlags(flags: readonly Flag[], id: string, index: number): Flag[] {
	return flags.filter(
		(f) => f.connectionId === id && !f.componentId && detailIndex(f, 'fittingIndex') === index
	);
}

/** The pipe segments of connection `id`, as a table, each with the flags about it. */
export function segmentTable(
	id: string,
	link: LinkResult,
	prefs: UnitPreferences,
	flags: readonly Flag[] = []
): Table {
	const f = new Formatter(prefs);
	return {
		columns: [
			f.column('innerDiameter', 'Inner diameter', 'diameter'),
			f.column('length', 'Length', 'length'),
			f.column('roughness', 'Roughness', 'diameter'),
			f.column('velocity', 'Velocity', 'velocity'),
			f.column('reynoldsNumber', 'Re'),
			f.column('frictionFactor', 'f (Darcy)'),
			text('flowRegime', 'Regime'),
			f.column('headLoss', 'Friction loss', 'head')
		],
		rows: link.segments.map((s) => ({
			key: `${id}:segment:${s.index}`,
			element: { kind: 'connection', id },
			name: pipeLabel(s.index),
			detail: '',
			cells: {
				innerDiameter: f.num(s.innerDiameter, 'diameter'),
				length: f.num(s.length, 'length'),
				roughness: f.num(s.roughness, 'diameter'),
				velocity: f.num(s.velocity, 'velocity'),
				reynoldsNumber: f.plain(s.reynoldsNumber),
				frictionFactor: f.plain(s.frictionFactor),
				flowRegime: regimeLabel(s.flowRegime),
				headLoss: f.diff(s.headLoss, 'head', HEAD_NOISE)
			},
			flags: segmentFlags(flags, id, s.index)
		}))
	};
}

/** The fittings of connection `id`, with the K the solver used, its source and its flags. */
export function fittingTable(
	id: string,
	link: LinkResult,
	prefs: UnitPreferences,
	fittingName: (type: string) => string = fittingFallbackName,
	flags: readonly Flag[] = []
): Table {
	const f = new Formatter(prefs);
	return {
		columns: [
			f.column('quantity', 'Quantity'),
			f.column('k', 'K (each)'),
			f.column('referenceDiameter', 'K referred to diameter', 'diameter'),
			f.column('headLoss', 'Head loss (all)', 'head'),
			text('source', 'Source', true)
		],
		rows: link.fittings.map((fitting) => ({
			key: `${id}:fitting:${fitting.index}`,
			element: { kind: 'connection', id },
			name: fittingName(fitting.type),
			detail: `Fitting ${fitting.index + 1}`,
			cells: {
				quantity: f.plain(fitting.quantity),
				k: f.plain(fitting.k),
				referenceDiameter: f.num(fitting.referenceDiameter, 'diameter'),
				headLoss: f.diff(fitting.headLoss, 'head', HEAD_NOISE),
				source: fitting.source
			},
			flags: fittingFlags(flags, id, fitting.index)
		}))
	};
}

/**
 * A pump's solved status. 'no_flow' covers two cases the API tells apart in its
 * PUMP_FLOW_REVERSAL flag (details headRise and shutoffHead): the system head across the pump
 * exceeds its shutoff head, or its discharge is closed off (e.g. behind a closed check valve)
 * and it runs dead-headed at its shutoff head. Without that flag the label stays neutral.
 */
export function pumpStatusLabel(result: PumpResult, flags: readonly Flag[] = []): string {
	if (result.status === 'running') return runningLabel(result.control);
	if (result.status === 'off') return 'Off';
	if (result.status !== 'no_flow') return humanize(result.status);
	const reversal = flags.find((f) => f.code === 'PUMP_FLOW_REVERSAL');
	const rise = reversal?.details.headRise;
	const shutoff = reversal?.details.shutoffHead;
	if (typeof rise === 'number' && typeof shutoff === 'number') {
		return rise > shutoff
			? 'No flow (system head above shutoff)'
			: 'No flow (discharge closed off: dead-headed at shutoff head)';
	}
	return 'No flow (held at zero by its check)';
}

/**
 * A running pump's status: plain 'Running' at a fixed speed; for a speed-controlled pump (CLAUDE.md
 * D11), whether its speed holds the setpoint or it runs at a limit of its drive. At a limit the
 * flow can still equal the setpoint (within the solver's flow tolerance; setpointAchieved).
 */
function runningLabel(control: PumpResult['control']): string {
	if (!control) return 'Running';
	const held = control.setpointAchieved === true;
	switch (control.state) {
		case 'active':
			return 'Running (holding flow setpoint)';
		case 'max_speed':
			return held
				? 'Running at maximum speed (holding flow setpoint)'
				: 'Running at maximum speed (setpoint not met)';
		case 'min_speed':
			return held
				? 'Running at minimum speed (holding flow setpoint)'
				: 'Running at minimum speed (above setpoint)';
		default:
			return 'Running';
	}
}

/**
 * A pump's control in results: 'Fixed speed', or the mode and setpoint with what the control
 * achieved ("Flow 12 L/s: held", "Flow 12 L/s: 9.8 L/s at maximum speed"). Every value comes
 * from the result; only units change.
 */
export function pumpControlText(result: PumpResult, prefs: UnitPreferences): string {
	const control = result.control;
	if (!control) return 'Fixed speed';
	const f = new Formatter(prefs);
	const mode = PUMP_CONTROL_MODE_NAMES[control.mode] ?? humanize(control.mode);
	const state = PUMP_CONTROL_STATE_LABELS[control.state] ?? humanize(control.state);
	const limit = control.state === 'max_speed' || control.state === 'min_speed';
	const achieved =
		limit && control.setpointAchieved === false
			? `${f.value(result.operatingFlow, 'flow')} ${state}`
			: limit
				? `${PUMP_CONTROL_STATE_LABELS.active} ${state}`
				: state;
	return `${mode} ${f.value(control.setpoint, 'flow')}: ${achieved}`;
}

/**
 * Pumps: operating point, power and NPSH. An off pump has no speed ("—"). A Control column is
 * shown only when a pump of the solve is speed-controlled (it keeps narrow tables narrow).
 */
export function pumpTable(project: Project, solved: SolvedState, prefs: UnitPreferences): Table {
	const f = new Formatter(prefs);
	const results = solved.pumpResults;
	const controlled = Object.values(results).some((pump) => pump?.control);
	const columns: Column[] = [
		text('status', 'Status'),
		...(controlled ? [text('control', 'Control')] : []),
		f.column('flow', 'Flow', 'flow'),
		f.column('head', 'Head', 'head'),
		f.column('speed', 'Speed', 'fraction'),
		f.column('efficiency', 'Efficiency', 'fraction'),
		f.column('hydraulicPower', 'Hydraulic power', 'power'),
		f.column('shaftPower', 'Shaft power', 'power'),
		f.column('npshAvailable', 'NPSHa', 'head'),
		f.column('npshRequired', 'NPSHr', 'head'),
		f.column('npshMargin', 'NPSH margin', 'head')
	];
	const rows = orderedIds(project, Object.keys(results)).map((id) => {
		const pump = results[id] as PumpResult;
		const flags = flagsForElement(solved.flags, { kind: 'component', id });
		return componentRow(project, solved.flags, id, {
			status: pumpStatusLabel(pump, flags),
			...(controlled ? { control: pumpControlText(pump, prefs) } : {}),
			flow: f.num(pump.operatingFlow, 'flow'),
			head: f.num(pump.operatingHead, 'head'),
			speed: pump.status === 'off' ? '—' : f.num(pump.speed, 'fraction'),
			efficiency: f.num(pump.efficiency, 'fraction'),
			hydraulicPower: f.num(pump.hydraulicPower, 'power'),
			shaftPower: f.num(pump.shaftPower, 'power'),
			npshAvailable: f.num(pump.npshAvailable, 'head'),
			npshRequired: f.num(pump.npshRequired, 'head'),
			npshMargin: f.num(pump.npshMargin, 'head')
		});
	});
	return { columns, rows };
}

const VALVE_STATE: Readonly<Record<ValveResult['state'], string>> = {
	open: 'Open',
	closed: 'Closed',
	active: 'Active (throttling)'
};

const VALVE_TYPES: Readonly<Record<string, string>> = {
	gate: 'Gate',
	ball: 'Ball',
	butterfly: 'Butterfly',
	globe: 'Globe',
	check: 'Check',
	stop_check: 'Stop-check',
	prv: 'PRV',
	psv: 'PSV',
	fcv: 'FCV'
};

/** A valve's solved state in words ('Open', 'Closed', 'Active (throttling)'). */
export function valveStateLabel(state: ValveResult['state']): string {
	return VALVE_STATE[state] ?? humanize(state);
}

export function valveTypeLabel(type: string): string {
	return VALVE_TYPES[type] ?? humanize(type);
}

/** A control valve's setpoint in its own unit: pressure (gauge) for PRV/PSV, flow for FCV. */
export function setpointText(valve: ValveResult, prefs: UnitPreferences): string {
	if (valve.setpoint === null) return '—';
	const f = new Formatter(prefs);
	if (valve.valveType === 'fcv') return f.value(valve.setpoint, 'flow');
	if (valve.valveType === 'prv' || valve.valveType === 'psv') {
		return f.value(valve.setpoint, 'pressure', { gauge: true });
	}
	return f.plain(valve.setpoint);
}

/** Valves: solved state, loss and resistance, setpoint. */
export function valveTable(project: Project, solved: SolvedState, prefs: UnitPreferences): Table {
	const f = new Formatter(prefs);
	const columns: Column[] = [
		text('type', 'Type'),
		text('state', 'State'),
		f.column('flow', 'Flow (+ inlet → outlet)', 'flow'),
		f.column('headLoss', 'Head loss', 'head'),
		f.column('pressureDrop', 'Pressure drop', 'pressure'),
		f.column('kOpen', 'K (open)'),
		f.column('kEffective', 'K effective'),
		f.column('cvEffective', 'Cv effective'),
		{ key: 'setpoint', label: 'Setpoint', numeric: true },
		text('setpointAchieved', 'Setpoint met')
	];
	const results = solved.valveResults;
	// The head tolerance as a pressure, at the solved fluid's density and standard gravity.
	const pressureNoise = solved.fluid.density * STANDARD_GRAVITY * HEAD_NOISE;
	const rows = orderedIds(project, Object.keys(results)).map((id) => {
		const valve = results[id] as ValveResult;
		return componentRow(project, solved.flags, id, {
			type: valveTypeLabel(valve.valveType),
			state: VALVE_STATE[valve.state] ?? humanize(valve.state),
			flow: f.num(valve.flow, 'flow'),
			headLoss: f.diff(valve.headLoss, 'head', HEAD_NOISE),
			pressureDrop: f.diff(valve.pressureDrop, 'pressure', pressureNoise),
			kOpen: f.plain(valve.kOpen),
			kEffective: f.plain(valve.kEffective),
			cvEffective: f.plain(valve.cvEffective),
			setpoint: setpointText(valve, prefs),
			setpointAchieved:
				valve.setpointAchieved === null ? '—' : valve.setpointAchieved ? 'Yes' : 'No'
		});
	});
	return { columns, rows };
}

/** A relief valve with no result: closed, with a side closed off or floating (RELIEF_VALVE_CLOSED). */
export const RELIEF_NO_RESULT = 'Closed (no result)';

/**
 * Relief valves (proposal pressure-relief-valve.md §6 W4): the state, the flow, the capacity at
 * full lift for the case fluid and the flow as a fraction of it, the inlet's static pressure
 * (gauge), the total-pressure difference as a fraction of the set (above 100 %, an active valve
 * relieves and the rise is its overpressure; a locked-closed one stays closed), the lift, the back
 * pressure (gauge), the static pressure drop, inlet minus outlet, as for valves, and the head
 * loss; "—" for none (a pressure in a floating section). The state of a valve locked closed in the
 * case as solved (`inputs`, see assignedFlowTable) reads "Closed (locked)" (relief.ts
 * reliefStateLabel). A relief valve with no result (a side closed off or floating) is listed by
 * its RELIEF_VALVE_CLOSED flag, with "—" for every value. Differences the solver resolves only to
 * its head tolerance read "≈ 0".
 */
export function reliefTable(
	project: Project,
	solved: SolvedState,
	prefs: UnitPreferences,
	inputs: Project | null = null
): Table {
	const f = new Formatter(prefs);
	const columns: Column[] = [
		text('state', 'State'),
		f.column('flow', 'Flow (+ inlet → outlet)', 'flow'),
		f.column('fullLiftFlow', 'Capacity (full lift)', 'flow'),
		f.column('flowRatio', 'Flow ÷ capacity', 'fraction'),
		f.column('inletPressure', 'Inlet pressure', 'pressure', { gauge: true }),
		f.column('setRatio', 'Δp ÷ set', 'fraction'),
		f.column('lift', 'Lift', 'fraction'),
		f.column('backPressure', 'Back pressure', 'pressure', { gauge: true }),
		f.column('pressureDrop', 'Pressure drop (static)', 'pressure'),
		f.column('headLoss', 'Head loss', 'head')
	];
	// An older response may have no map at all.
	const results = solved.reliefValveResults ?? {};
	const closed = solved.flags
		.filter((flag) => flag.code === 'RELIEF_VALVE_CLOSED' && flag.componentId)
		.map((flag) => flag.componentId as string)
		.filter((id) => !(id in results));
	// The head tolerance as a pressure, at the solved fluid's density and standard gravity.
	const pressureNoise = solved.fluid.density * STANDARD_GRAVITY * HEAD_NOISE;
	const rows = orderedIds(project, [...Object.keys(results), ...new Set(closed)]).map((id) => {
		const valve = results[id] as ReliefValveResult | undefined;
		if (!valve) {
			return componentRow(project, solved.flags, id, {
				state: RELIEF_NO_RESULT,
				...Object.fromEntries(columns.slice(1).map((c) => [c.key, '—']))
			});
		}
		return componentRow(project, solved.flags, id, {
			state: reliefStateLabel(valve.state, id, inputs),
			flow: f.num(valve.flow, 'flow'),
			fullLiftFlow: f.num(valve.fullLiftFlow, 'flow'),
			flowRatio: f.num(valve.flowRatio, 'fraction'),
			inletPressure: f.num(valve.inletPressure, 'pressure'),
			setRatio: f.num(valve.setRatio, 'fraction'),
			lift: f.num(valve.lift, 'fraction'),
			backPressure: f.num(valve.backPressure, 'pressure'),
			pressureDrop: f.diff(valve.pressureDrop, 'pressure', pressureNoise),
			headLoss: f.diff(valve.headLoss, 'head', HEAD_NOISE)
		});
	});
	return { columns, rows };
}

/** Whether a solve has a relief valve to show: a result, or one with none (RELIEF_VALVE_CLOSED). */
export function hasReliefValves(solved: SolvedState): boolean {
	return (
		Object.keys(solved.reliefValveResults ?? {}).length > 0 ||
		solved.flags.some((flag) => flag.code === 'RELIEF_VALVE_CLOSED')
	);
}

/**
 * Equipment (proposal equipment-pressure-drop.md §6.3): flow, flow ÷ rated flow ("—" for a Cv or
 * Kv rating, which has no rated flow), the pressure loss (the rating scaled to the solved flow and
 * density, ρg × head loss), the head loss and the static pressure drop, inlet minus outlet, as for
 * valves. Differences the solver resolves only to its head tolerance read "≈ 0".
 */
export function equipmentTable(
	project: Project,
	solved: SolvedState,
	prefs: UnitPreferences
): Table {
	const f = new Formatter(prefs);
	const columns: Column[] = [
		f.column('flow', 'Flow (+ inlet → outlet)', 'flow'),
		f.column('flowRatio', 'Flow ÷ rated flow', 'fraction'),
		f.column('pressureLoss', 'Pressure loss', 'pressure'),
		f.column('headLoss', 'Head loss', 'head'),
		f.column('pressureDrop', 'Pressure drop (static)', 'pressure')
	];
	const results = solved.equipmentResults ?? {};
	// The head tolerance as a pressure, at the solved fluid's density and standard gravity.
	const pressureNoise = solved.fluid.density * STANDARD_GRAVITY * HEAD_NOISE;
	const rows = orderedIds(project, Object.keys(results)).map((id) => {
		const item = results[id] as EquipmentResult;
		return componentRow(project, solved.flags, id, {
			flow: f.num(item.flow, 'flow'),
			flowRatio: f.num(item.flowRatio, 'fraction'),
			pressureLoss: f.diff(item.pressureLoss, 'pressure', pressureNoise),
			headLoss: f.diff(item.headLoss, 'head', HEAD_NOISE),
			pressureDrop: f.diff(item.pressureDrop, 'pressure', pressureNoise)
		});
	});
	return { columns, rows };
}

/**
 * Where an orifice plate's loss coefficient C came from, in words (proposal orifice-plate.md §5.4):
 * ISO 5167-2's, held at ISO's lowest Reynolds number when the flow's is below it (flagged), or the
 * entered C, moved to D and D/2 tappings from corner or flange taps (tapCoefficientRatio given).
 */
export function orificeCoefficientSource(result: OrificeResult): string {
	if (result.coefficientSource === 'entered') {
		return result.tapCoefficientRatio !== null ? 'Entered, moved to D and D/2' : 'Entered';
	}
	const held =
		result.coefficientReynoldsNumber !== null &&
		result.coefficientReynoldsNumber > result.reynoldsNumber;
	return held ? 'ISO 5167-2 (held)' : 'ISO 5167-2';
}

/**
 * Orifice plates (proposal orifice-plate.md §6 W4): flow, ISO 5167-2's permanent pressure loss
 * (ρg × head loss), a meter's differential pressure at its taps ("—" without taps), β, the C that
 * sets the loss (at D and D/2 tappings) and where it came from, the inlet pipe's Reynolds number,
 * the static pressure at the vena contracta (gauge; "—" at zero flow and where the pressure level
 * is undetermined), the static pressure drop, inlet minus outlet, as for valves, and the head
 * loss. Differences the solver resolves only to its head tolerance read "≈ 0".
 */
export function orificeTable(project: Project, solved: SolvedState, prefs: UnitPreferences): Table {
	const f = new Formatter(prefs);
	const columns: Column[] = [
		f.column('flow', 'Flow (+ inlet → outlet)', 'flow'),
		f.column('pressureLoss', 'Permanent loss', 'pressure'),
		f.column('differentialPressure', 'Differential pressure (taps)', 'pressure'),
		f.column('beta', 'β'),
		f.column('dischargeCoefficient', 'C'),
		text('coefficientSource', 'C from'),
		f.column('reynoldsNumber', 'Re (inlet pipe)'),
		f.column('venaContractaPressure', 'Vena contracta pressure', 'pressure', { gauge: true }),
		f.column('pressureDrop', 'Pressure drop (static)', 'pressure'),
		f.column('headLoss', 'Head loss', 'head')
	];
	// An older response may have no map at all.
	const results = solved.orificeResults ?? {};
	// The head tolerance as a pressure, at the solved fluid's density and standard gravity.
	const pressureNoise = solved.fluid.density * STANDARD_GRAVITY * HEAD_NOISE;
	const rows = orderedIds(project, Object.keys(results)).map((id) => {
		const plate = results[id] as OrificeResult;
		return componentRow(project, solved.flags, id, {
			flow: f.num(plate.flow, 'flow'),
			pressureLoss: f.diff(plate.pressureLoss, 'pressure', pressureNoise),
			differentialPressure: f.num(plate.differentialPressure, 'pressure'),
			beta: f.plain(plate.beta),
			dischargeCoefficient: f.plain(plate.dischargeCoefficient),
			coefficientSource: orificeCoefficientSource(plate),
			reynoldsNumber: f.plain(plate.reynoldsNumber),
			venaContractaPressure: f.num(plate.venaContractaPressure, 'pressure'),
			pressureDrop: f.diff(plate.pressureDrop, 'pressure', pressureNoise),
			headLoss: f.diff(plate.headLoss, 'head', HEAD_NOISE)
		});
	});
	return { columns, rows };
}

/** Labelled values for a per-port map ("Run inlet" → "12.3"), in the order of the component's ports. */
function perPort(
	project: Project,
	componentId: string,
	values: Readonly<Record<string, number>>,
	format: (v: number, port: string) => Value
): CellPart[] {
	const component = componentById(project, componentId);
	const order = component ? component.ports.map((p) => p.id) : [];
	const keys = [
		...order.filter((k) => k in values),
		...Object.keys(values).filter((k) => !order.includes(k))
	];
	return keys.map((k) => ({ label: portLabel(k), value: format(values[k] as number, k) }));
}

/** "diverging from run_inlet" → "Diverging from run inlet" (port ids as port labels). */
export function branchPatternLabel(pattern: string, component?: Component): string {
	const ports = new Set(component?.ports.map((p) => p.id) ?? []);
	const text = pattern
		.split(' ')
		.map((word) => (ports.has(word) || word.includes('_') ? portLabel(word).toLowerCase() : word))
		.join(' ');
	return text.charAt(0).toUpperCase() + text.slice(1);
}

/**
 * The velocity a branch's K values are referred to (path loss = K·v²/2g):
 * - 'combined': the combined-flow velocity (BranchResult.referenceVelocity), on which the API
 *   reports every K: Crane TP-410's (combined port on the run) and the Darby 3-K fallback's it
 *   flags TEE_PATTERN_FALLBACK (combined flow through a tee's branch) alike. A leg with no flow
 *   has the K its head implies on the same velocity.
 * - 'none': an ideal junction (no loss) or no flow.
 */
export type BranchVelocityBasis = 'combined' | 'none';

export function branchVelocityBasis(branch: BranchResult): BranchVelocityBasis {
	if (branch.lossModel === 'ideal' || branch.combinedPortId === null) return 'none';
	return 'combined';
}

/** Whether the solve flagged this branch's Darby 3-K fallback (TEE_PATTERN_FALLBACK). */
export function branchFallback(id: string, flags: readonly Flag[]): boolean {
	return flags.some((f) => f.code === 'TEE_PATTERN_FALLBACK' && f.componentId === id);
}

/**
 * Branches (tees and wyes): solved pattern, port flows, K per path with the velocity it is
 * referred to, path losses, correlation.
 */
export function branchTable(project: Project, solved: SolvedState, prefs: UnitPreferences): Table {
	const f = new Formatter(prefs);
	const columns: Column[] = [
		text('pattern', 'Flow pattern'),
		{ key: 'portFlows', label: 'Port flows (+ in)', unit: f.unit('flow'), numeric: true },
		{ key: 'kFactors', label: 'K per path', numeric: true },
		{ key: 'kVelocity', label: 'Velocity K is on', unit: f.unit('velocity'), numeric: true },
		{ key: 'pathHeadLosses', label: 'Path loss', unit: f.unit('head'), numeric: true },
		text('correlation', 'Correlation', true)
	];
	const results = solved.branchResults;
	const rows = orderedIds(project, Object.keys(results)).map((id) => {
		const branch = results[id] as BranchResult;
		const correlation = [siText(branch.correlation, prefs)];
		if (!branch.inCorrelationRange) correlation.push('Outside the correlation’s range.');
		const basis = branchVelocityBasis(branch);
		const kVelocity: Cell =
			basis === 'combined'
				? [{ label: 'Combined flow', value: f.num(Math.abs(branch.referenceVelocity), 'velocity') }]
				: '—';
		return componentRow(project, solved.flags, id, {
			pattern: branchPatternLabel(branch.pattern, componentById(project, id)),
			portFlows: perPort(project, id, branch.portFlows, (v) => f.num(v, 'flow')),
			kFactors: perPort(project, id, branch.kFactors, (v) => {
				const k = f.plain(v);
				return v !== 0 && Math.abs(v) < K_NOISE
					? { text: '≈ 0', title: `${k}: round-off, below the solver's resolution` }
					: k;
			}),
			kVelocity,
			pathHeadLosses: perPort(project, id, branch.pathHeadLosses, (v) =>
				f.diff(v, 'head', HEAD_NOISE)
			),
			correlation
		});
	});
	return { columns, rows };
}

/** The velocity bases used in a solve's branches (to explain the K values under the table). */
export function branchBases(solved: SolvedState): Set<BranchVelocityBasis> {
	return new Set(Object.values(solved.branchResults).map((b) => branchVelocityBasis(b)));
}

/** Whether any branch of the solve is on the flagged Darby 3-K fallback. */
export function anyBranchFallback(solved: SolvedState): boolean {
	return Object.keys(solved.branchResults).some((id) => branchFallback(id, solved.flags));
}

const BOUNDARY_TYPES: Readonly<Record<BoundaryResult['type'], string>> = {
	reservoir: 'Reservoir',
	reference_node: 'Reference node',
	plug: 'Plug',
	assigned_flow: 'Assigned flow'
};

/**
 * The API reports assigned-flow nodes with the boundaries (a BoundaryResult of type
 * 'assigned_flow'), but they fix a flow, not a pressure: they have a table of their own.
 */
function isAssignedFlowResult(result: BoundaryResult | undefined): boolean {
	return result?.type === 'assigned_flow';
}

/**
 * Boundaries (reservoirs, reference nodes and plugs): the head each holds and the flow it supplies
 * (positive into the network). Assigned-flow nodes are in assignedFlowTable.
 */
export function boundaryTable(
	project: Project,
	solved: SolvedState,
	prefs: UnitPreferences
): Table {
	const f = new Formatter(prefs);
	const columns: Column[] = [
		text('type', 'Type'),
		f.column('egl', 'EGL', 'head'),
		f.column('outflow', 'Outflow (+ into network)', 'flow'),
		{ key: 'portOutflows', label: 'Per port', unit: f.unit('flow'), numeric: true }
	];
	const results = solved.boundaryResults;
	const ids = Object.keys(results).filter((id) => !isAssignedFlowResult(results[id]));
	const rows = orderedIds(project, ids).map((id) => {
		const boundary = results[id] as BoundaryResult;
		return componentRow(project, solved.flags, id, {
			type: BOUNDARY_TYPES[boundary.type] ?? humanize(boundary.type),
			egl: f.num(boundary.egl, 'head'),
			outflow: f.num(boundary.outflow, 'flow'),
			portOutflows: perPort(project, id, boundary.portOutflows, (v) => f.num(v, 'flow'))
		});
	});
	return { columns, rows };
}

/**
 * Assigned-flow nodes (SDD §4.11, PRD §3.2.1): the flow as entered (its direction and magnitude),
 * and the static pressure and HGL at the node, with the node's flags (e.g. BELOW_VAPOR_PRESSURE).
 * The flow is the input of this solve, read from `inputs`, the project exactly as it was solved
 * (ProjectStore.solvedProject), so it matches the row's results after later edits; every other
 * value is from the solved state. A node without a solved pressure (closed off, or on an
 * undetermined level) has no row, as in the other tables.
 */
export function assignedFlowTable(
	project: Project,
	solved: SolvedState,
	prefs: UnitPreferences,
	inputs: Project | null
): Table {
	const f = new Formatter(prefs);
	const columns: Column[] = [
		text('direction', 'Direction'),
		f.column('flow', 'Assigned flow', 'flow'),
		f.column('elevation', 'Elevation', 'length'),
		f.column('pressure', 'Pressure', 'pressure', { gauge: true }),
		f.column('absolutePressure', 'Absolute pressure', 'pressure', { absolute: true }),
		f.column('hgl', 'HGL', 'head')
	];
	const results = solved.boundaryResults;
	const ids = Object.keys(results).filter((id) => isAssignedFlowResult(results[id]));
	const rows = orderedIds(project, ids).map((id) => {
		const boundary = results[id] as BoundaryResult;
		const portId = Object.keys(boundary.portOutflows)[0];
		const node = portId === undefined ? undefined : solved.nodeResults[`${id}:${portId}`];
		const input = inputs?.components.find((c) => c.id === id);
		const flow = input?.type === 'assigned_flow' ? input.flow : null;
		const direction = flow === null ? null : flowDirection(flow);
		return componentRow(project, solved.flags, id, {
			direction: flow === null ? '—' : direction ? DIRECTION_NAMES[direction] : 'None (as a plug)',
			flow: flow === null ? '—' : f.num(Math.abs(flow), 'flow'),
			elevation: f.num(node?.elevation, 'length'),
			pressure: f.num(node?.pressure, 'pressure'),
			absolutePressure: f.num(node?.absolutePressure, 'pressure'),
			hgl: f.num(node?.hgl, 'head')
		});
	});
	return { columns, rows };
}

/**
 * The table with the rows of elements a scenario changed marked in their detail line ("changed in
 * this scenario"), for the results of that scenario (proposal scenario-manager.md §6.11).
 */
export function markChanged(table: Table, changed: ReadonlySet<string>): Table {
	if (!changed.size) return table;
	return {
		...table,
		rows: table.rows.map((row) =>
			changed.has(row.element.id)
				? { ...row, detail: `${row.detail} · changed in this scenario` }
				: row
		)
	};
}

/** The views of the results pane, in tab order. */
export type ResultsView =
	| 'summary'
	| 'checks'
	| 'nodes'
	| 'links'
	| 'pumps'
	| 'valves'
	| 'reliefValves'
	| 'equipment'
	| 'orifices'
	| 'branches'
	| 'boundaries'
	| 'assignedFlows'
	| 'methods';

export const VIEW_LABELS: Readonly<Record<ResultsView, string>> = {
	summary: 'Summary',
	checks: 'Checks',
	nodes: 'Nodes',
	links: 'Links',
	pumps: 'Pumps',
	valves: 'Valves',
	reliefValves: 'Relief valves',
	equipment: 'Equipment',
	orifices: 'Orifices',
	branches: 'Branches',
	boundaries: 'Boundaries',
	assignedFlows: 'Assigned flows',
	methods: 'Methods'
};

/** Views that have something to show: element tables without results are left out. */
export function availableViews(solved: SolvedState): ResultsView[] {
	const has = (map: Readonly<Record<string, unknown>>) => Object.keys(map).length > 0;
	const boundaries = Object.values(solved.boundaryResults);
	const views: ResultsView[] = ['summary'];
	// The opt-in design checks (D19), when the project has some (an older response has none).
	if (solved.designChecks?.length) views.push('checks');
	if (has(solved.nodeResults)) views.push('nodes');
	if (has(solved.linkResults)) views.push('links');
	if (has(solved.pumpResults)) views.push('pumps');
	if (has(solved.valveResults)) views.push('valves');
	// Relief valves after the valves (proposal pressure-relief-valve.md W4), when the solve has
	// some (an older response may have no map at all), with or without a result.
	if (hasReliefValves(solved)) views.push('reliefValves');
	// Equipment only when the solve has some (an older response may have no map at all).
	if (has(solved.equipmentResults ?? {})) views.push('equipment');
	// Orifice plates only when the solve has some (an older response may have no map at all).
	if (has(solved.orificeResults ?? {})) views.push('orifices');
	if (has(solved.branchResults)) views.push('branches');
	if (boundaries.some((b) => !isAssignedFlowResult(b))) views.push('boundaries');
	if (boundaries.some((b) => isAssignedFlowResult(b))) views.push('assignedFlows');
	views.push('methods');
	return views;
}

/**
 * Rows (from any table) for one element, for the trace view's result values. `inputs` is the
 * project as solved (see assignedFlowTable).
 */
export function rowsForElement(
	project: Project,
	solved: SolvedState,
	prefs: UnitPreferences,
	element: ElementRef,
	inputs: Project | null = null
): { title: string; table: Table; rows: Row[] }[] {
	const tables: { title: string; table: Table }[] =
		element.kind === 'connection'
			? [{ title: 'Pipe connection', table: linkTable(project, solved, prefs) }]
			: [
					{ title: 'Pump', table: pumpTable(project, solved, prefs) },
					{ title: 'Valve', table: valveTable(project, solved, prefs) },
					{ title: 'Relief valve', table: reliefTable(project, solved, prefs, inputs) },
					{ title: 'Equipment', table: equipmentTable(project, solved, prefs) },
					{ title: 'Orifice plate', table: orificeTable(project, solved, prefs) },
					{ title: 'Branch', table: branchTable(project, solved, prefs) },
					{ title: 'Boundary', table: boundaryTable(project, solved, prefs) },
					{
						title: 'Assigned flow',
						table: assignedFlowTable(project, solved, prefs, inputs)
					},
					{ title: 'Ports', table: nodeTable(project, solved, prefs) }
				];
	return tables
		.map(({ title, table }) => ({
			title,
			table,
			rows: table.rows.filter((r) => sameElement(r.element, element))
		}))
		.filter((t) => t.rows.length > 0);
}

/** One value of an element's summary: a results-table cell with that column's label and unit. */
export interface SummaryItem {
	key: string;
	label: string;
	unit?: string;
	cell: Cell;
}

/** An element's key results from the last solve, shown beside its inputs in Build. */
export interface ElementSummary {
	items: SummaryItem[];
	/** Flags about the element, each about what it names as the element is now. */
	flags: Flag[];
	/**
	 * Flags about the element that name a pipe or fitting it cannot place on the element as it is
	 * now (after a structural edit since the solve): its trace lists them as solved.
	 */
	unlisted: number;
	/** What reads otherwise after a structural edit since the solve, and what is left out and why. */
	notes: string[];
}

/**
 * The columns an element's summary shows, by the results table its row is in (the first that has
 * it, in rowsForElement's order): what a designer checks first for that kind of element.
 */
const SUMMARY_COLUMNS: Readonly<Record<string, readonly string[]>> = {
	'Pipe connection': ['flow', 'velocity', 'headLoss'],
	Pump: ['status', 'flow', 'head', 'npshMargin'],
	Valve: ['state', 'flow', 'pressureDrop'],
	// Δp ÷ set says how close a closed valve is to opening, or how far an open one relieves past it
	// (a locked-closed valve stays closed above 100 %: its state says so).
	'Relief valve': ['state', 'flow', 'inletPressure', 'setRatio'],
	// A Cv- or Kv-rated item has no flow ratio ("—"): left out, so it shows flow and pressure loss.
	Equipment: ['flow', 'flowRatio', 'pressureLoss'],
	// A plate without taps has no reading ("—"): left out, so it shows flow and permanent loss.
	'Orifice plate': ['flow', 'pressureLoss', 'differentialPressure'],
	Branch: ['portFlows'],
	Boundary: ['outflow'],
	'Assigned flow': ['pressure'],
	Ports: ['pressure']
};

/**
 * An element's key results, from the same rows and formatting as the results tables, so the
 * values match them exactly; values the solve has none of ("—") are left out. Null when the
 * element has no results in this solve (added after it, or no longer in the project).
 */
export function elementSummary(
	project: Project,
	solved: SolvedState,
	prefs: UnitPreferences,
	element: ElementRef,
	inputs: Project | null = null,
	structure: Project = project
): ElementSummary | null {
	if (element.kind === 'connection') {
		const reading = linkReading(structure, outOfDateProject(solved), solved, element.id);
		if (reading && !readsAsSolved(reading)) {
			return connectionSummary(solved, prefs, element.id, reading);
		}
	}
	const found = rowsForElement(project, solved, prefs, element, inputs)[0];
	const row = found?.rows[0];
	if (!found || !row) return null;
	const items = (SUMMARY_COLUMNS[found.title] ?? []).flatMap((key): SummaryItem[] => {
		const column = found.table.columns.find((c) => c.key === key);
		const cell = row.cells[key];
		if (!column || cell === undefined || cellLines(cell).every((line) => line.endsWith('—')))
			return [];
		return [{ key, label: column.label, ...(column.unit ? { unit: column.unit } : {}), cell }];
	});
	return { items, flags: row.flags, unlisted: 0, notes: [] };
}

/** Flag codes whose text flag-text.ts numbers from details.segmentIndex (a pipe's own flags). */
const PIPE_FLAGS: ReadonlySet<Flag['code']> = new Set([
	'TRANSITIONAL_FLOW',
	'CORRELATION_OUT_OF_RANGE'
]);

/** "pipe 2", "pipes 2 and 3", "pipes 1, 2 and 4" (numbered from 1). */
function pipesText(indexes: readonly number[]): string {
	const numbers = indexes.map((i) => String(i + 1));
	if (numbers.length === 1) return `pipe ${numbers[0]}`;
	return `pipes ${numbers.slice(0, -1).join(', ')} and ${numbers[numbers.length - 1]}`;
}

/**
 * A connection's key results read on it as it is now (linkReading), after a structural edit since
 * the solve: its flow and head loss in its current direction (the solved value with the other sign
 * after a reversal), each pipe's velocity as that pipe's (numbered as it is now), and its flags with
 * their pipes numbered as now; what cannot be placed is left out, and the notes say why.
 */
function connectionSummary(
	solved: SolvedState,
	prefs: UnitPreferences,
	id: string,
	reading: LinkReading
): ElementSummary {
	const f = new Formatter(prefs);
	const link = solved.linkResults[id] as LinkResult;
	const columns = linkColumns(f);
	const item = (key: string, cell: Cell): SummaryItem[] => {
		const column = columns.find((c) => c.key === key);
		if (!column || cellLines(cell).every((line) => line.endsWith('—'))) return [];
		return [{ key, label: column.label, ...(column.unit ? { unit: column.unit } : {}), cell }];
	};
	const velocities = reading.pipes.map((pipe) => {
		const segment = pipe
			? solved.linkResults[pipe.connectionId]?.segments.find((s) => s.index === pipe.index)
			: undefined;
		return pipe && segment ? f.num(pipe.sign * segment.velocity, 'velocity') : null;
	});
	const parts = velocities.flatMap((value, i) =>
		value === null ? [] : [{ label: pipeLabel(i), value }]
	);
	const items = [
		...(reading.flow === null ? [] : item('flow', f.num(reading.flow * link.flow, 'flow'))),
		...(velocities.length === 1 && velocities[0] ? item('velocity', velocities[0]) : []),
		...(velocities.length > 1 && parts.length ? item('velocity', parts) : []),
		...(reading.ends === null
			? []
			: item('headLoss', f.diff(reading.ends * link.headLoss, 'head', HEAD_NOISE)))
	];
	const notes: string[] = [];
	if (reading.ends === -1 || (reading.ends === null && reading.flow === -1)) {
		notes.push('Reversed since the last solve: the values are given in its new direction.');
	}
	if (reading.changed === 'pipes') {
		notes.push(
			'Its pipes changed since the last solve: solve again to see its flow and head loss.'
		);
	} else if (reading.ends === null) {
		notes.push(
			`Its ends changed since the last solve: solve again to see its ${reading.flow === null ? 'flow and head loss' : 'head loss'}.`
		);
	}
	const missing = velocities.flatMap((v, i) => (v === null ? [i] : []));
	if (missing.length) {
		const which = velocities.length === 1 ? 'its pipe' : pipesText(missing);
		notes.push(
			`No velocity from the last solve for ${which}: solve again to see ${missing.length > 1 ? 'them' : 'it'}.`
		);
	}
	const own = flagsForElement(solved.flags, { kind: 'connection', id });
	const flags = own.flatMap((flag): Flag[] => {
		const segment = detailIndex(flag, 'segmentIndex');
		if (segment !== null) {
			if (!PIPE_FLAGS.has(flag.code)) return [];
			const now = reading.pipes.findIndex((p) => p?.connectionId === id && p.index === segment);
			if (now < 0) return [];
			return [
				now === segment ? flag : { ...flag, details: { ...flag.details, segmentIndex: now } }
			];
		}
		if (detailIndex(flag, 'fittingIndex') !== null) return reading.fittings ? [flag] : [];
		return [flag];
	});
	return { items, flags, unlisted: own.length - flags.length, notes };
}

/** The node with the lowest absolute static pressure (closest to vapor pressure), if any. */
export function lowestPressureNode(solved: SolvedState): NodeResult | null {
	let lowest: NodeResult | null = null;
	for (const node of Object.values(solved.nodeResults)) {
		if (!lowest || node.absolutePressure < lowest.absolutePressure) lowest = node;
	}
	return lowest;
}

/** The connection with the highest speed in any of its segments, if any. */
export function fastestLink(solved: SolvedState): { id: string; velocity: number } | null {
	let best: { id: string; velocity: number } | null = null;
	for (const [id, link] of Object.entries(solved.linkResults)) {
		const speeds = [link.velocity, ...link.segments.map((s) => s.velocity)].map(Math.abs);
		const velocity = Math.max(...speeds);
		if (!best || velocity > best.velocity) best = { id, velocity };
	}
	return best;
}

/** Compare dotted version numbers ("1.10.0" > "1.9.2"); non-numeric parts compare as text. */
export function compareVersions(a: string, b: string): number {
	const pa = a.split('.');
	const pb = b.split('.');
	for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
		const x = pa[i] ?? '0';
		const y = pb[i] ?? '0';
		const nx = Number(x);
		const ny = Number(y);
		const diff = Number.isFinite(nx) && Number.isFinite(ny) ? nx - ny : x < y ? -1 : x > y ? 1 : 0;
		if (diff !== 0) return Math.sign(diff);
	}
	return 0;
}

/**
 * Method versions that changed between the version a project was solved with before and the
 * version of these results: newer than the older one, up to and including the newer one, oldest
 * first.
 */
export function versionsBetween<T extends { version: string }>(
	versions: readonly T[],
	a: string,
	b: string
): T[] {
	const [low, high] = compareVersions(a, b) <= 0 ? [a, b] : [b, a];
	return versions
		.filter((v) => compareVersions(v.version, low) > 0 && compareVersions(v.version, high) <= 0)
		.sort((x, y) => compareVersions(x.version, y.version));
}

/** The first column's sort key (the element's name). */
export const NAME_SORT_KEY = '';

export type SortDirection = 'ascending' | 'descending';

export interface TableSort {
	/** A column key, or NAME_SORT_KEY for the first column. */
	key: string;
	direction: SortDirection;
}

/** A displayed number back to a number: "18.98", "-0.5", "2.555×10⁻⁶"; null for anything else. */
export function displayedNumber(text: string): number | null {
	const plain = /^-?\d+(\.\d+)?$/.exec(text);
	if (plain) return Number(text);
	const scientific = /^(-?\d+(?:\.\d+)?)×10([⁻⁰¹²³⁴⁵⁶⁷⁸⁹]+)$/.exec(text);
	if (!scientific) return null;
	const digits = Object.fromEntries(Object.entries(SUPERSCRIPT).map(([d, s]) => [s, d]));
	const power = [...(scientific[2] ?? '')].map((c) => digits[c] ?? '').join('');
	return Number(`${scientific[1]}e${power}`);
}

/**
 * What a cell sorts by: the number it shows ("≈ 0", round-off below the solver's resolution, is
 * 0), else its text; a cell of several values (one per pipe or port) by its largest number; null
 * for no value ("—"), which sorts last either way.
 */
export function sortValue(cell: Cell | undefined): number | string | null {
	if (cell === undefined) return null;
	// Several values: a labelled part's value ("Pipe 1: 2.312" sorts by 2.312), or each line.
	const texts = Array.isArray(cell)
		? cell.map((part) => (typeof part === 'string' ? part : valueText(part.value)))
		: [];
	const values = (Array.isArray(cell) ? texts : [valueText(cell)]).map((text) =>
		text === '≈ 0' ? 0 : displayedNumber(text)
	);
	const numbers = values.filter((v): v is number => v !== null);
	if (numbers.length) return Math.max(...numbers);
	const text = Array.isArray(cell) ? (texts[0] ?? '') : valueText(cell);
	return text === '—' || text === '' ? null : text;
}

/**
 * Rows in a table's sort order: by the values shown in that column (numbers as numbers, text in
 * natural order), rows without a value last, ties in the table's own order. Null keeps the order.
 */
export function sortRows(rows: readonly Row[], sort: TableSort | null): Row[] {
	if (!sort) return [...rows];
	const sign = sort.direction === 'ascending' ? 1 : -1;
	const keyOf = (row: Row) =>
		sort.key === NAME_SORT_KEY ? row.name : sortValue(row.cells[sort.key]);
	return rows
		.map((row, index) => ({ row, index, value: keyOf(row) }))
		.sort((a, b) => {
			if (a.value === null || b.value === null) {
				return a.value === b.value ? a.index - b.index : a.value === null ? 1 : -1;
			}
			const order =
				typeof a.value === 'number' && typeof b.value === 'number'
					? a.value - b.value
					: String(a.value).localeCompare(String(b.value), undefined, { numeric: true });
			return order === 0 ? a.index - b.index : sign * order;
		})
		.map((entry) => entry.row);
}

/** Whether a column can be sorted: some row shows a value in it. */
export function sortableColumn(rows: readonly Row[], key: string): boolean {
	return key === NAME_SORT_KEY || rows.some((row) => sortValue(row.cells[key]) !== null);
}

/** The port with the highest static pressure, if any. */
export function highestPressureNode(solved: SolvedState): NodeResult | null {
	let highest: NodeResult | null = null;
	for (const node of Object.values(solved.nodeResults)) {
		if (!highest || node.pressure > highest.pressure) highest = node;
	}
	return highest;
}

/** The pump with the smallest NPSH margin (only pumps with one: a fluid with a vapor pressure). */
export function smallestNpshMargin(solved: SolvedState): { id: string; margin: number } | null {
	let smallest: { id: string; margin: number } | null = null;
	for (const [id, pump] of Object.entries(solved.pumpResults)) {
		const margin = pump.npshMargin;
		if (margin === null || margin === undefined) continue;
		if (!smallest || margin < smallest.margin) smallest = { id, margin };
	}
	return smallest;
}
