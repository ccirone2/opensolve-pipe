/**
 * Results for display (design §5): the solver's SI values arranged as tables, in the project's
 * display units, with element names and the physics flags that belong to each row.
 *
 * Nothing here computes a hydraulic value. Every number shown comes from the SolvedState the API
 * returned; this module only selects, orders, converts units (units.ts) and labels them. Names
 * come from the current project; an element that no longer exists (results kept after an edit)
 * is shown by its id.
 */
import type {
	BoundaryResult,
	BranchResult,
	Component,
	Flag,
	LinkResult,
	NodeResult,
	Project,
	PumpResult,
	SegmentResult,
	SolvedState,
	UnitPreferences,
	ValveResult
} from '../api/types';
import { DIRECTION_NAMES, flowDirection } from './assigned-flow';
import { componentById, connectionById } from './graph';
import {
	fittingFallbackName,
	humanize,
	kindLabel,
	portLabel,
	PUMP_CONTROL_MODE_NAMES,
	PUMP_CONTROL_STATE_LABELS
} from './labels';
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
 * Links: one row per connection, in project order. Velocity, Re, f and regime are per pipe: a
 * connection of one pipe shows its values; a connection of several shows each pipe's ("Pipe 1",
 * "Pipe 2", ...), since one value (the API's top-level LinkResult values are the first pipe's)
 * would hide a faster or transitional pipe further on.
 */
export function linkTable(project: Project, solved: SolvedState, prefs: UnitPreferences): Table {
	const f = new Formatter(prefs);
	const columns: Column[] = [
		f.column('flow', 'Flow', 'flow'),
		f.column('velocity', 'Velocity', 'velocity'),
		f.column('headLoss', 'Head loss', 'head'),
		f.column('reynoldsNumber', 'Re'),
		f.column('frictionFactor', 'f (Darcy)'),
		text('flowRegime', 'Regime')
	];
	const results = solved.linkResults;
	const resultKeys = Object.keys(results);
	const known = project.connections.map((c) => c.id).filter((id) => resultKeys.includes(id));
	const ids = [...known, ...resultKeys.filter((k) => !known.includes(k))];
	const rows = ids.map((id): Row => {
		const link = results[id] as LinkResult;
		const element: ElementRef = { kind: 'connection', id };
		const perPipe = link.segments.length > 1;
		const pipeValues = (single: Value, value: (segment: SegmentResult) => Value): Cell =>
			perPipe ? link.segments.map((s) => ({ label: pipeLabel(s.index), value: value(s) })) : single;
		return {
			key: id,
			element,
			name: connectionName(project, id),
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
	| 'nodes'
	| 'links'
	| 'pumps'
	| 'valves'
	| 'branches'
	| 'boundaries'
	| 'assignedFlows'
	| 'methods';

export const VIEW_LABELS: Readonly<Record<ResultsView, string>> = {
	summary: 'Summary',
	nodes: 'Nodes',
	links: 'Links',
	pumps: 'Pumps',
	valves: 'Valves',
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
	if (has(solved.nodeResults)) views.push('nodes');
	if (has(solved.linkResults)) views.push('links');
	if (has(solved.pumpResults)) views.push('pumps');
	if (has(solved.valveResults)) views.push('valves');
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
