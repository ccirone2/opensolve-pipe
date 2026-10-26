/**
 * Data for the pump chart (design §5): the pump curve at the operating speed, the system curve
 * and the operating point, in display units, split into the part of the pump curve inside its
 * data (solid) and the extrapolated part outside it (dashed).
 *
 * Every point comes from the API: the pump curve and operating point from the PumpResult, the
 * system curve from POST /api/v1/system-curve for the same solve (D10: fetched on demand). A
 * system-curve point the API could not solve has no head; it is a gap in the line and a row
 * that says why in the table, never a value made up here: from the point's reason, told with
 * element names and in display units when the names are given (utils/system-curve-text.ts), with
 * the API's sentence kept as the row's detail. The flow range of the curve's data at speed s is
 * s × [Q_min, Q_max] of the head-curve points the user entered (the affinity law the solver
 * applies; API PumpResult.curve spans exactly that range). When the curve definition is not
 * available, the span of the sampled curve is used instead.
 *
 * Outside that range the solver extrapolates the head along the curve's end slope, which is a
 * straight line in Q at a fixed speed (H = s²·H₀(Q/s) with H₀ linear), so the dashed segment from
 * the curve's end to an operating point outside the range is exactly that extrapolation; it joins
 * two values the API reported and adds none.
 *
 * The panels below the head (proposal pump-chart.md §4.2) are the API's too: the efficiency,
 * shaft-power and NPSHr curves sampled at the running speed over their own data
 * (PumpResult.efficiencyCurve, powerCurve, npshrCurve), NPSHa at each system-curve point
 * (SystemCurvePoint.npshAvailable) and the duty's values. Only the readout between samples and
 * the flow where NPSHa falls below NPSHr are read from the drawn lines, and they say so.
 */
import type {
	CurvePoint,
	Project,
	PumpResult,
	SystemCurveResponse,
	UnitPreferences
} from '../api/types';
import type { SystemCurveState } from '../state/project.svelte';
import { componentById } from './graph';
import { systemPointNote, type SystemCurveTextContext } from './system-curve-text';
import { displayUnit, formatNumber, fromSI, unitLabel } from './units';

/** A system-curve row: flow and head formatted, and why a point without a head has none. */
export interface SystemRow {
	flow: string;
	head: string;
	/** NPSHa at the pump's suction at this flow ('—' without one). */
	npsha: string;
	/** Why the point has no head ('' when it has one). */
	note: string;
	/** The API's sentence, when `note` is told in the browser. */
	detail?: string;
}

/** The projects a system-curve point's reason is told with (names; kinds as solved). */
export type SystemCurveNames = Omit<SystemCurveTextContext, 'units'>;

export interface ChartPoint {
	/** Flow, display unit. */
	x: number;
	/** Head, display unit. */
	y: number;
}

/** The chart's panels, top to bottom, sharing the flow axis (proposal pump-chart.md §4.1). */
export const PANELS = ['head', 'efficiency', 'power', 'npsh'] as const;
export type PanelKey = (typeof PANELS)[number];

/** A point of a line: a null value is a gap. */
export interface ChartDatum {
	x: number;
	y: number | null;
}

/** The efficiency panel: η at the running speed over its data (%), and at the duty. */
export interface EfficiencyPanel {
	curve: ChartPoint[];
	duty: ChartPoint | null;
	/** The duty's flow is outside the efficiency data: the solver held η at its end value. */
	held: boolean;
}

/** The shaft-power panel: ρgQH/η over the flows both curves' data reach, and at the duty. */
export interface PowerPanel {
	curve: ChartPoint[];
	duty: ChartPoint | null;
	/** The largest shaft power of the samples: "largest over the curve data". */
	largest: ChartPoint;
}

/** The NPSH panel: NPSHr over its data, NPSHa along the system curve, both at the duty. */
export interface NpshPanel {
	required: ChartPoint[] | null;
	/** NPSHa at each system-curve point (null: no head, or no NPSHa there); null: no curve. */
	available: ChartDatum[] | null;
	requiredAt: ChartPoint | null;
	availableAt: ChartPoint | null;
	/** The first flow where NPSHa(Q) falls below NPSHr(Q), read from the drawn lines. */
	crossing: number | null;
}

export interface PumpChartData {
	flowUnit: string;
	headUnit: string;
	/** Power display unit (kW, or hp with US units). */
	powerUnit: string;
	/** The panels this pump has data for, in order (the head panel always). */
	panels: PanelKey[];
	efficiency: EfficiencyPanel | null;
	power: PowerPanel | null;
	npsh: NpshPanel | null;
	/** Flow range of the curve's data at the operating speed, display unit (null: unknown). */
	range: [number, number] | null;
	/** The pump curve inside its data: solid. */
	curve: ChartPoint[];
	/** Extrapolated parts of the pump curve (each a polyline): dashed. */
	extrapolated: ChartPoint[][];
	/** The system curve, when given: a null head is a point the API could not solve (a gap). */
	system: { x: number; y: number | null }[] | null;
	/** System-curve points without a head (each row says why). */
	systemMissing: number;
	/** The flows the system curve's points span, display unit (SystemCurveResponse.flowRange). */
	systemSpan: [number, number] | null;
	/** The operating point, when the pump is running. */
	operating: ChartPoint | null;
	/**
	 * A pump held at zero flow ('no_flow'): the point (0, head across it) the API reports. Not on
	 * the pump curve unless the pump is dead-headed at its shutoff head.
	 */
	held: ChartPoint | null;
	inCurveRange: boolean;
	/** Data table rows (formatted): pump curve points, with an extrapolated mark. */
	curveRows: { flow: string; head: string; extrapolated: boolean }[];
	/** Data table rows of the system curve: '—' and the reason for a point with no head. */
	systemRows: SystemRow[];
}

/** Flow range (m³/s) of a pump's head-curve points at rated speed, from the project. */
export function ratedCurveRange(project: Project, pumpId: string): [number, number] | null {
	const pump = componentById(project, pumpId);
	if (!pump || pump.type !== 'pump') return null;
	const curve = project.pumpLibrary.find((c) => c.id === pump.curveId);
	const flows = curve?.points.map((p) => p.flow) ?? [];
	if (!flows.length) return null;
	return [Math.min(...flows), Math.max(...flows)];
}

const RANGE_TOLERANCE = 1e-9;

/**
 * Chart data for one pump. `ratedRange` is the curve's flow range at rated speed (m³/s), from
 * ratedCurveRange(); without it, the sampled curve's own span is taken as the data range.
 * `systemCurve` is the pump's system curve for the same solve, when it has been computed.
 * `names` tells a point's reason with element names and display units; without them, a point
 * without a head keeps the API's sentence.
 */
export function pumpChartData(
	result: PumpResult,
	prefs: UnitPreferences,
	ratedRange: [number, number] | null = null,
	systemCurve: SystemCurveResponse | null = null,
	names: SystemCurveNames | null = null
): PumpChartData {
	const flowUnit = displayUnit('flow', prefs);
	const headUnit = displayUnit('head', prefs);
	const point = (p: CurvePoint): ChartPoint => ({
		x: fromSI(p.flow, flowUnit),
		y: fromSI(p.head, headUnit)
	});

	const powerUnit = displayUnit('power', prefs);
	const sampled = [...result.curve].sort((a, b) => a.flow - b.flow);
	let rangeSI: [number, number] | null = null;
	if (ratedRange) {
		rangeSI = [ratedRange[0] * result.speed, ratedRange[1] * result.speed];
	} else if (sampled.length) {
		rangeSI = [sampled[0]!.flow, sampled[sampled.length - 1]!.flow];
	}
	const tolerance = rangeSI ? RANGE_TOLERANCE * Math.max(Math.abs(rangeSI[1]), 1e-12) : 0;
	const inside = (q: number) =>
		!rangeSI || (q >= rangeSI[0] - tolerance && q <= rangeSI[1] + tolerance);

	// Solid: the points inside the data. Dashed: runs of points outside it, each joined to the
	// nearest point inside so the line is continuous.
	const curve: ChartPoint[] = [];
	const extrapolated: ChartPoint[][] = [];
	let run: CurvePoint[] = [];
	const closeRun = (next?: CurvePoint) => {
		if (!run.length) return;
		const before = sampled[sampled.indexOf(run[0]!) - 1];
		const line = [...(before ? [before] : []), ...run, ...(next ? [next] : [])];
		extrapolated.push(line.map(point));
		run = [];
	};
	for (const p of sampled) {
		if (inside(p.flow)) {
			closeRun(p);
			curve.push(point(p));
		} else {
			run.push(p);
		}
	}
	closeRun();

	const running = result.status === 'running';
	const operatingSI: CurvePoint = { flow: result.operatingFlow, head: result.operatingHead };
	const operating = running ? point(operatingSI) : null;
	// An operating point beyond the sampled curve: the end-slope extrapolation reaches it.
	if (running && sampled.length) {
		const first = sampled[0]!;
		const last = sampled[sampled.length - 1]!;
		if (operatingSI.flow > last.flow) extrapolated.push([point(last), point(operatingSI)]);
		else if (operatingSI.flow < first.flow) extrapolated.push([point(operatingSI), point(first)]);
	}

	const held = result.status === 'no_flow' ? point(operatingSI) : null;

	const systemPoints = systemCurve?.points.length
		? [...systemCurve.points].sort((a, b) => a.flow - b.flow)
		: null;
	const system =
		systemPoints?.map((p) => ({
			x: fromSI(p.flow, flowUnit),
			y: p.head === null ? null : fromSI(p.head, headUnit)
		})) ?? null;
	const fmt = (v: number) => formatNumber(v, 4);
	const panels = lowerPanels(result, prefs, systemPoints);
	return {
		flowUnit: unitLabel('flow', flowUnit),
		headUnit: unitLabel('head', headUnit),
		powerUnit: unitLabel('power', powerUnit),
		panels: PANELS.filter((key) => key === 'head' || panels[key] !== null),
		...panels,
		range: rangeSI ? [fromSI(rangeSI[0], flowUnit), fromSI(rangeSI[1], flowUnit)] : null,
		curve,
		extrapolated,
		system,
		operating,
		held,
		inCurveRange: result.inCurveRange,
		curveRows: sampled.map((p) => {
			const c = point(p);
			return { flow: fmt(c.x), head: fmt(c.y), extrapolated: !inside(p.flow) };
		}),
		systemMissing: (system ?? []).filter((c) => c.y === null).length,
		systemSpan:
			system && systemCurve
				? [fromSI(systemCurve.flowRange.min, flowUnit), fromSI(systemCurve.flowRange.max, flowUnit)]
				: null,
		systemRows: (system ?? []).map((c, i) => {
			const p = systemPoints?.[i];
			const why =
				c.y === null && p
					? names
						? systemPointNote(p, { ...names, units: prefs })
						: { text: p.message }
					: { text: '' };
			const npsha = p?.npshAvailable;
			return {
				flow: fmt(c.x),
				head: c.y === null ? '—' : fmt(c.y),
				npsha: npsha === null || npsha === undefined ? '—' : fmt(fromSI(npsha, headUnit)),
				note: why.text,
				...(why.detail ? { detail: why.detail } : {})
			};
		})
	};
}

/** The flows a sampled curve spans (its first and last sample), SI. */
function span(points: readonly { flow: number }[]): [number, number] | null {
	return points.length ? [points[0]!.flow, points[points.length - 1]!.flow] : null;
}

/**
 * The panels below the head, from the API's samples, in display units; null where the pump has
 * no data for one. `system` is the system curve's points, sorted by flow.
 */
function lowerPanels(
	result: PumpResult,
	prefs: UnitPreferences,
	system: SystemCurveResponse['points'] | null
): Pick<PumpChartData, 'efficiency' | 'power' | 'npsh'> {
	const flowUnit = displayUnit('flow', prefs);
	const headUnit = displayUnit('head', prefs);
	const powerUnit = displayUnit('power', prefs);
	const x = (flow: number) => fromSI(flow, flowUnit);
	const running = result.status === 'running';
	const dutyX = x(result.operatingFlow);

	const effSamples = result.efficiencyCurve ?? [];
	const effSpan = span(effSamples);
	const efficiency: EfficiencyPanel | null = effSamples.length
		? {
				curve: effSamples.map((p) => ({ x: x(p.flow), y: p.efficiency * 100 })),
				duty:
					running && result.efficiency !== null ? { x: dutyX, y: result.efficiency * 100 } : null,
				held:
					running &&
					!!effSpan &&
					(result.operatingFlow < effSpan[0] * (1 - RANGE_TOLERANCE) ||
						result.operatingFlow > effSpan[1] * (1 + RANGE_TOLERANCE))
			}
		: null;

	const powerSamples = result.powerCurve ?? [];
	const powerPoints = powerSamples.map((p) => ({
		x: x(p.flow),
		y: fromSI(p.shaftPower, powerUnit)
	}));
	const power: PowerPanel | null = powerPoints.length
		? {
				curve: powerPoints,
				duty:
					running && result.shaftPower !== null
						? { x: dutyX, y: fromSI(result.shaftPower, powerUnit) }
						: null,
				largest: powerPoints.reduce((a, b) => (b.y > a.y ? b : a))
			}
		: null;

	const required =
		result.npshrCurve?.map((p) => ({ x: x(p.flow), y: fromSI(p.npshr, headUnit) })) ?? null;
	const available = system
		? system.map((p) => ({
				x: x(p.flow),
				y:
					p.npshAvailable === null || p.npshAvailable === undefined
						? null
						: fromSI(p.npshAvailable, headUnit)
			}))
		: null;
	const requiredAt =
		running && result.npshRequired !== null
			? { x: dutyX, y: fromSI(result.npshRequired, headUnit) }
			: null;
	const availableAt =
		running && result.npshAvailable !== null
			? { x: dutyX, y: fromSI(result.npshAvailable, headUnit) }
			: null;
	// A panel needs a line: NPSHr data, or NPSHa along a computed system curve.
	const hasAvailable = !!available?.some((p) => p.y !== null);
	const npsh: NpshPanel | null =
		required?.length || hasAvailable
			? {
					required: required?.length ? required : null,
					available: available?.some((p) => p.y !== null) ? available : null,
					requiredAt,
					availableAt,
					crossing: required && available ? npshCrossing(required, available) : null
				}
			: null;
	return { efficiency, power, npsh };
}

/**
 * A line's value at x, linear between its neighbouring samples (sorted by x); null outside its
 * samples or next to a gap. This reads the line as drawn.
 */
export function valueAt(line: readonly ChartDatum[], at: number): number | null {
	for (let i = 0; i < line.length; i++) {
		const b = line[i]!;
		if (b.x === at) return b.y;
		if (b.x > at) {
			const a = line[i - 1];
			if (!a || a.y === null || b.y === null) return null;
			return a.y + ((b.y - a.y) * (at - a.x)) / (b.x - a.x);
		}
	}
	return null;
}

/**
 * The first flow, going up, where NPSHa falls below NPSHr: between two neighbouring NPSHa points
 * inside the NPSHr data, where NPSHa − NPSHr (NPSHr read from its drawn line) goes from ≥ 0 to
 * < 0, the flow where the two straight pieces meet. Null where they do not cross.
 */
export function npshCrossing(
	required: readonly ChartPoint[],
	available: readonly ChartDatum[]
): number | null {
	let previous: { x: number; d: number } | null = null;
	for (const p of available) {
		const r = p.y === null ? null : valueAt(required, p.x);
		if (p.y === null || r === null) {
			previous = null;
			continue;
		}
		const d = p.y - r;
		if (previous && previous.d >= 0 && d < 0) {
			return previous.x + ((p.x - previous.x) * previous.d) / (previous.d - d);
		}
		previous = { x: p.x, d };
	}
	return null;
}

/** The panels' names, as their chips and the readout say them. */
export const PANEL_LABELS: Readonly<Record<PanelKey, string>> = {
	head: 'Head',
	efficiency: 'Efficiency',
	power: 'Shaft power',
	npsh: 'NPSH'
};

/** The chart's height (rem) for the panels shown: the head panel's, plus each other panel's. */
export function chartHeightRem(panels: readonly PanelKey[], phone: boolean): number {
	const extra = panels.filter((p) => p !== 'head').length;
	return (phone ? 16 : 18) + extra * (phone ? 6 : 7);
}

/** localStorage key of the panels the user hid (a per-browser choice, never project data). */
export const HIDDEN_PANELS_KEY = 'opensolve-pipe:pump-chart-hidden-panels';

/** The panels hidden before in this browser ([] where storage is refused or holds nothing). */
export function loadHiddenPanels(): PanelKey[] {
	try {
		const parsed: unknown = JSON.parse(localStorage.getItem(HIDDEN_PANELS_KEY) ?? '[]');
		return Array.isArray(parsed) ? PANELS.filter((p) => p !== 'head' && parsed.includes(p)) : [];
	} catch {
		return [];
	}
}

/** Remember the hidden panels; a refused write only loses the convenience. */
export function saveHiddenPanels(hidden: readonly PanelKey[]): void {
	try {
		if (hidden.length) localStorage.setItem(HIDDEN_PANELS_KEY, JSON.stringify(hidden));
		else localStorage.removeItem(HIDDEN_PANELS_KEY);
	} catch {
		// Private modes and blocked site data refuse storage.
	}
}

/** One value of the readout under the chart. */
export interface ReadoutItem {
	key: 'pump' | 'system' | 'efficiency' | 'power' | 'npshr' | 'npsha';
	label: string;
	value: number;
	unit: string;
}

/** The pump curve as one line, extrapolated parts included, sorted by flow. */
export function pumpLine(d: PumpChartData): ChartPoint[] {
	const points = [...d.curve, ...d.extrapolated.flat()].sort((a, b) => a.x - b.x);
	return points.filter((p, i) => i === 0 || p.x !== points[i - 1]!.x);
}

/**
 * Every line of the panels shown, read at one flow (display units) as drawn: linear between the
 * API's samples, nothing outside a line's samples or across a gap.
 */
export function chartReadout(
	d: PumpChartData,
	shown: readonly PanelKey[],
	flow: number
): ReadoutItem[] {
	const items: ReadoutItem[] = [];
	const add = (
		key: ReadoutItem['key'],
		label: string,
		line: readonly ChartDatum[] | null,
		unit: string
	) => {
		const value = line ? valueAt(line, flow) : null;
		if (value !== null) items.push({ key, label, value, unit });
	};
	add('pump', 'Pump head', pumpLine(d), d.headUnit);
	add('system', 'System head', d.system, d.headUnit);
	if (shown.includes('efficiency'))
		add('efficiency', 'Efficiency', d.efficiency?.curve ?? null, '%');
	if (shown.includes('power')) add('power', 'Shaft power', d.power?.curve ?? null, d.powerUnit);
	if (shown.includes('npsh')) {
		add('npshr', 'NPSHr', d.npsh?.required ?? null, d.headUnit);
		add('npsha', 'NPSHa', d.npsh?.available ?? null, d.headUnit);
	}
	return items;
}

// ---------------------------------------------------------------------------------------------
// Other cases on the chart (scenario manager, proposal scenario-manager.md §6.13)
// ---------------------------------------------------------------------------------------------

/**
 * Hollow markers that tell other cases apart (with a direct label, the legend and the table:
 * never colour alone). 'rectRot' stays "held at zero flow".
 */
export const CASE_MARKERS = ['triangle', 'rect', 'star', 'crossRot', 'rectRounded'] as const;
export type CaseMarker = (typeof CASE_MARKERS)[number];

/** At most this many cases on the chart at once (the case shown and five others). */
export const MAX_CHART_CASES = 6;

export interface OtherCaseInput {
	/** The case's id ('' for the base case). */
	key: string;
	name: string;
	/** This pump's result in that case's last solve. */
	result: PumpResult;
	/** The case's results are out of date. */
	stale: boolean;
	/** That case's system curve on this chart's flow grid, when computed. */
	system: SystemCurveResponse | null;
}

export interface OtherCaseData {
	key: string;
	/** "Winter", or "Winter (out of date)". */
	label: string;
	marker: CaseMarker;
	/** Its operating point (a running pump). */
	operating: ChartPoint | null;
	/** Its pump held at zero flow: (0, head across it). */
	held: ChartPoint | null;
	/**
	 * Its pump curve, when the pump runs at another speed than in the case shown; given once per
	 * speed (the first case at that speed), with `curveLabel` naming every case at it.
	 */
	curve: ChartPoint[] | null;
	/** "Pump curve at 100 % speed (Base case, Higher tank)". */
	curveLabel: string;
	/** Its system curve, when computed (a null head is a gap). */
	system: { x: number; y: number | null }[] | null;
	/** Table row: flow, head, speed and state, formatted. */
	row: { flow: string; head: string; speed: string; state: string };
	systemRows: SystemRow[];
}

const STATE_WORDS: Readonly<Record<string, string>> = {
	running: 'Running',
	off: 'Off',
	no_flow: 'Held at zero flow'
};

/**
 * Chart data of the other cases with a result for this pump, each with its marker (in order),
 * from their own PumpResult and system curve. `speed` is the pump's speed in the case shown: a
 * case whose pump runs at another speed also gets its pump curve. `names` as for pumpChartData
 * (names and kinds are the same in every case: scenarios change values, never topology).
 */
export function otherCasesData(
	others: readonly OtherCaseInput[],
	prefs: UnitPreferences,
	ratedRange: [number, number] | null,
	speed: number,
	names: SystemCurveNames | null = null
): OtherCaseData[] {
	const fmt = (v: number) => formatNumber(v, 4);
	const same = (a: number, b: number) => Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(b));
	const running = (o: OtherCaseInput) => o.result.status === 'running';
	return others.map((other, i) => {
		const data = pumpChartData(other.result, prefs, ratedRange, other.system, names);
		const atSpeed = others.filter((o) => running(o) && same(o.result.speed, other.result.speed));
		const first = atSpeed[0] === other;
		const drawn = running(other) && !same(other.result.speed, speed) && first;
		return {
			key: other.key,
			label: other.stale ? `${other.name} (out of date)` : other.name,
			marker: CASE_MARKERS[i % CASE_MARKERS.length] as CaseMarker,
			operating: data.operating,
			held: data.held,
			curve: drawn ? [...data.curve, ...data.extrapolated.flat()].sort((a, b) => a.x - b.x) : null,
			curveLabel: `Pump curve at ${formatNumber(other.result.speed * 100, 4)} % speed (${atSpeed
				.map((o) => (o.stale ? `${o.name}, out of date` : o.name))
				.join('; ')})`,
			system: data.system,
			row: {
				flow: data.operating ? fmt(data.operating.x) : data.held ? '0' : '—',
				head: data.operating ? fmt(data.operating.y) : data.held ? fmt(data.held.y) : '—',
				speed:
					other.result.status === 'off' ? '—' : `${formatNumber(other.result.speed * 100, 4)} %`,
				state: STATE_WORDS[other.result.status] ?? other.result.status
			},
			systemRows: data.systemRows
		};
	});
}

// ---------------------------------------------------------------------------------------------
// The figure's notes: one source for the screen and the image (proposal export.md §3.4). The
// chart's configuration is in pump-chart-config.ts, in the chart's chunk.
// ---------------------------------------------------------------------------------------------

/** The other cases' markers as text (the case checkboxes, the table and the image's notes). */
export const MARKER_SYMBOLS: Readonly<Record<CaseMarker, string>> = {
	triangle: '△',
	rect: '□',
	star: '☆',
	crossRot: '×',
	rectRounded: '▢'
};

/** Why a system-curve point has no head, as the API's messages say (TSD §5.6). */
const NO_HEAD_REASONS =
	'(no steady state carries the flow, its head is undetermined, its solve did not converge, ' +
	'or it was not computed)';

/** The state of the system curve the chart tells, with the control the screen offers beside it. */
export type CurveNoteKind = 'loading' | 'error' | 'cancelled' | 'missing';

/** The sentences the figure shows under the chart (export.md §3.4): the screen's and the image's. */
export interface ChartNotes {
	/** The pump off, or held at zero flow by its check. */
	pump: string | null;
	/**
	 * The system curve's state: being computed, failed, not computed (cancelled, or never asked
	 * for), or with points without a head.
	 */
	curve: { kind: CurveNoteKind; text: string } | null;
	/** How the system curve shown was computed (D10). */
	method: string | null;
	/** The dashed extrapolation, with the curve's data range. */
	extrapolated: string | null;
	/** What the panels below the head show and where they stop (proposal pump-chart.md §4.2). */
	panels: string[];
}

export interface ChartNotesInput {
	data: PumpChartData;
	result: PumpResult;
	/** The pump's system curve for the solve (undefined: not requested). */
	system: SystemCurveState | undefined;
	/** Another pump of the solve is speed-controlled and on: it regulates in the system curve. */
	othersControlled?: boolean;
	/**
	 * Where the reasons of the points without a head are, as the subject of "say why": the
	 * screen's data table (the default), or for the image, which has none, where they are.
	 */
	reasonsIn?: string;
	/** The panels shown (default: the head only). */
	shown?: readonly PanelKey[];
}

/** The figure's notes, from one function the screen and the image both use. */
export function chartNotes({
	data,
	result,
	system,
	othersControlled = false,
	reasonsIn = 'the data table says',
	shown = ['head']
}: ChartNotesInput): ChartNotes {
	const fmt = (v: number) => formatNumber(v, 4);
	const controlled = !!result.control;
	const pump =
		result.status === 'off'
			? `This pump is off: it carries no flow. Its curve is shown at its ${
					controlled ? 'maximum' : 'set'
				} speed, for reference${controlled ? '; its flow control is not applied' : ''}.`
			: data.held
				? 'This pump is held at zero flow by its check (see its flag). The diamond marks zero flow ' +
					'at the head across the pump.'
				: null;
	const why = `${reasonsIn} why for each ${NO_HEAD_REASONS}`;
	const n = data.system?.length ?? 0;
	const curve: ChartNotes['curve'] =
		system?.status === 'loading'
			? { kind: 'loading', text: 'Computing the system curve for this solve…' }
			: system?.status === 'error'
				? { kind: 'error', text: `The system curve could not be computed: ${system.message}` }
				: system === undefined || system.status === 'cancelled'
					? {
							kind: 'cancelled',
							text: !system
								? 'The system curve has not been computed for this solve.'
								: system.by === 'user'
									? 'The system curve was not computed: you cancelled it.'
									: system.by === 'goalSeek'
										? 'The system curve was not computed: a goal seek was started.'
										: 'The system curve was not computed: a new solve was started.'
						}
					: data.system && data.systemMissing === n
						? {
								kind: 'missing',
								text: `No point of the system curve has a head, so it is not drawn; ${why}.`
							}
						: data.systemMissing
							? {
									kind: 'missing',
									text: `${data.systemMissing} of ${n} system-curve points have no head: the line has gaps there, and ${why}.`
								}
							: null;
	const flows =
		data.system && data.systemSpan
			? `${n} evenly spaced flows from ${fmt(data.systemSpan[0])} to ` +
				`${fmt(data.systemSpan[1])} ${data.flowUnit}`
			: null;
	const method = flows
		? `System curve: the network of this solve, solved again with the pump replaced by each of ${flows} (${
				controlled ? 'its flow control replaced by that fixed flow; ' : ''
			}other pumps running${
				othersControlled ? ', speed-controlled ones regulating to their setpoints' : ''
			}, valves following their rules); the system head at each flow is the EGL at the discharge minus the EGL at the suction.`
		: null;
	const extrapolated = data.extrapolated.length
		? `Dashed: the pump curve extrapolated beyond its data${
				data.range
					? ` (${fmt(data.range[0])} to ${fmt(data.range[1])} ${data.flowUnit} at this speed)`
					: ''
			}, along the curve's end slope, as the solver does.`
		: null;
	return { pump, curve, method, extrapolated, panels: panelNotes(data, result, shown) };
}

/** The notes of the panels below the head, in panel order. */
function panelNotes(d: PumpChartData, result: PumpResult, shown: readonly PanelKey[]): string[] {
	const fmt = (v: number) => formatNumber(v, 4);
	const notes: string[] = [];
	const speed = formatNumber(result.speed * 100, 4);
	if (shown.includes('efficiency') && d.efficiency) {
		if (result.speed !== 1)
			notes.push(
				`Efficiency at ${speed} % speed: η₀(Q/s), the affinity laws without an efficiency correction.`
			);
		if (d.efficiency.held)
			notes.push(
				"Efficiency: the duty's flow is outside the efficiency curve's data, so the solver holds η at the curve's end value (hollow marker)."
			);
	}
	if (shown.includes('power') && d.power) {
		const { x, y } = d.power.largest;
		notes.push(
			`Shaft power ρgQH/η over the flows that both the head and efficiency data reach; the largest there is ${fmt(y)} ${d.powerUnit} at ${fmt(x)} ${d.flowUnit} (beyond the data it is not known).`
		);
	}
	if (shown.includes('npsh') && d.npsh) {
		if (d.npsh.crossing !== null)
			notes.push(
				`NPSHa falls below NPSHr at about ${fmt(d.npsh.crossing)} ${d.flowUnit} (read from the drawn lines): the pump would cavitate beyond that flow.`
			);
		else if (!d.system && d.npsh.required)
			notes.push('NPSHa along the system curve is drawn once the system curve is computed.');
	}
	return notes;
}
