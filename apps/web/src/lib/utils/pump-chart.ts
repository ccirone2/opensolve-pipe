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
 *
 * With design checks on (CLAUDE.md D19), the chart draws their limits, never their verdicts (the
 * Checks view has those): the preferred operating region, the curve's allowable region and
 * minimum flow (manufacturer data at rated speed, drawn at s × flow, the affinity law the checks
 * apply), the NPSHa the NPSH margin check requires, max(NPSHr + margin, ratio × NPSHr) along the
 * NPSHr curve, and the motor's rated power. All from the project as solved.
 */
import type {
	CurvePoint,
	DesignChecks,
	Project,
	PumpCurve,
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

/** A speed-controlled pump's curve at a limit speed (display units). */
export interface SpeedLine {
	/** Percent of rated speed. */
	speed: number;
	curve: ChartPoint[];
}

/** An iso-efficiency line over the speed range (display units). */
export interface IsoLine {
	/** Percent. */
	efficiency: number;
	/** The line through the best efficiency point. */
	best: boolean;
	points: ChartPoint[];
}

/** Facts of the pump's curves (proposal pump-chart.md §6, slice 2), from the API. */
export interface CurveFacts {
	/** The best efficiency point at the running speed: on the head and efficiency panels. */
	bep: { head: ChartPoint; efficiency: ChartPoint; headExtrapolated: boolean } | null;
	/** Whether the pump has an efficiency curve (to say why there is no BEP). */
	hasEfficiency: boolean;
	shutoff: { point: ChartPoint; extrapolated: boolean };
	/** Where the head rises with flow: the flow ranges and the stretches of the pump line. */
	rising: { ranges: [number, number][]; lines: ChartPoint[][] };
	/** A speed-controlled pump's limit curves and iso-efficiency lines. */
	speedRange: { min: SpeedLine; max: SpeedLine; iso: IsoLine[] } | null;
}

/** A pump's design checks as solved (D19): the project's checks and the pump's curve. */
export interface PumpChecksInput {
	checks: DesignChecks;
	/** The pump's curve as solved (its manufacturer data); null: not found. */
	curve: PumpCurve | null;
	/** "API 610 preset", "your values" …: where each check's limits came from. */
	sources: { npshMargin: string | null; operatingRegion: string | null };
}

/** The design checks' limits drawn on the chart (display units; flows at the running speed). */
export interface CheckOverlays {
	/** The preferred operating region: fractions of the BEP flow and the flows (null: open end). */
	preferred: {
		low: number | null;
		high: number | null;
		from: number | null;
		to: number | null;
		source: string;
	} | null;
	/** The curve's allowable operating region at this speed, and as entered (rated speed). */
	allowable: { from: number; to: number; ratedFrom: number; ratedTo: number } | null;
	/** The larger of the curve's minimum flows at this speed, and as entered (rated speed). */
	minimumFlow: { flow: number; rated: number; name: string } | null;
	/** The NPSHa the NPSH margin check requires along the NPSHr curve (margin in display units). */
	npshRequired: {
		line: ChartPoint[];
		margin: number | null;
		ratio: number | null;
		source: string;
	} | null;
	/** The motor's rated power (display unit). */
	motorRating: number | null;
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
	facts: CurveFacts;
	/** The design checks' limits (D19); null without checks that draw on this pump's chart. */
	checks: CheckOverlays | null;
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
 * without a head keeps the API's sentence. `checks` are the design checks as solved (D19).
 */
export function pumpChartData(
	result: PumpResult,
	prefs: UnitPreferences,
	ratedRange: [number, number] | null = null,
	systemCurve: SystemCurveResponse | null = null,
	names: SystemCurveNames | null = null,
	checks: PumpChecksInput | null = null
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
	// Data that start above zero flow: the start tangent down to the shutoff head (straight in Q
	// at a fixed speed, H = s²·H₀(Q/s) with H₀ linear), as the solver extrapolates.
	const first = sampled[0];
	if (result.shutoffHead.extrapolated && first && first.flow > 0) {
		extrapolated.unshift([point({ flow: 0, head: result.shutoffHead.head }), point(first)]);
	}

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
	const facts = curveFacts(result, prefs, [...curve, ...extrapolated.flat()]);
	return {
		facts,
		checks: checks ? checkOverlays(result, prefs, checks, panels.npsh?.required ?? null) : null,
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

/** The curve facts in display units; `line` is every drawn point of the pump curve. */
function curveFacts(result: PumpResult, prefs: UnitPreferences, line: ChartPoint[]): CurveFacts {
	const flowUnit = displayUnit('flow', prefs);
	const headUnit = displayUnit('head', prefs);
	const x = (flow: number) => fromSI(flow, flowUnit);
	const y = (head: number) => fromSI(head, headUnit);
	const bep = result.bestEfficiencyPoint;
	const sorted = [...line].sort((a, b) => a.x - b.x);
	const ranges = result.risingHeadRanges.map((r): [number, number] => [x(r.flowMin), x(r.flowMax)]);
	const lines = ranges.map(([lo, hi]) => {
		const ends = [lo, hi].flatMap((at) => {
			const value = valueAt(sorted, at);
			return value === null ? [] : [{ x: at, y: value }];
		});
		return [...ends, ...sorted.filter((p) => p.x > lo && p.x < hi)].sort((a, b) => a.x - b.x);
	});
	const min = result.speedCurves.find((c) => c.limit === 'min');
	const max = result.speedCurves.find((c) => c.limit === 'max');
	const speedLine = (c: NonNullable<typeof min>): SpeedLine => ({
		speed: c.speed * 100,
		curve: c.curve.map((p) => ({ x: x(p.flow), y: y(p.head) }))
	});
	return {
		bep: bep
			? {
					head: { x: x(bep.flow), y: y(bep.head) },
					efficiency: { x: x(bep.flow), y: bep.efficiency * 100 },
					headExtrapolated: bep.headExtrapolated
				}
			: null,
		hasEfficiency: !!result.efficiencyCurve?.length,
		shutoff: {
			point: { x: 0, y: y(result.shutoffHead.head) },
			extrapolated: result.shutoffHead.extrapolated
		},
		rising: { ranges, lines },
		speedRange:
			min && max
				? {
						min: speedLine(min),
						max: speedLine(max),
						iso: result.isoEfficiencyLines.map((l) => ({
							efficiency: l.efficiency * 100,
							best: l.best,
							points: l.points.map((p) => ({ x: x(p.flow), y: y(p.head) }))
						}))
					}
				: null
	};
}

/**
 * The design checks' limits in display units (D19): the preferred region from the BEP flow at
 * this speed; the curve's manufacturer data, at rated speed, drawn at s × flow; the NPSHa the
 * NPSH margin check requires along the NPSHr line drawn; the motor's rating. Null when none of
 * them applies to this pump.
 */
export function checkOverlays(
	result: PumpResult,
	prefs: UnitPreferences,
	{ checks, curve, sources }: PumpChecksInput,
	npshr: readonly ChartPoint[] | null
): CheckOverlays | null {
	const flowUnit = displayUnit('flow', prefs);
	const headUnit = displayUnit('head', prefs);
	const x = (flow: number) => fromSI(flow, flowUnit);
	const s = result.speed;
	const region = checks.operatingRegion;
	const bep = result.bestEfficiencyPoint;
	const low = region?.preferredMin ?? null;
	const high = region?.preferredMax ?? null;
	const preferred =
		region && bep && (low !== null || high !== null)
			? {
					low,
					high,
					from: low === null ? null : x(low * bep.flow),
					to: high === null ? null : x(high * bep.flow),
					source: sources.operatingRegion ?? 'your values'
				}
			: null;
	// The manufacturer data are checked with the operating region (proposal design-checks.md §3).
	const data = region ? curve : null;
	const aor = data?.allowableOperatingRegion;
	const minimums = [
		{ value: data?.minimumContinuousStableFlow, name: 'minimum continuous stable flow' },
		{ value: data?.minimumThermalFlow, name: 'minimum thermal flow' }
	].filter((m): m is { value: number; name: string } => m.value !== null && m.value !== undefined);
	const floor = minimums.length ? minimums.reduce((a, b) => (b.value > a.value ? b : a)) : null;
	const npsh = checks.npshMargin;
	const margin = npsh?.minimumMargin ?? null;
	const ratio = npsh?.minimumRatio ?? null;
	const npshRequired =
		npsh && npshr?.length && (margin !== null || ratio !== null)
			? {
					line: npshr.map((p) => ({
						x: p.x,
						y: Math.max(
							margin === null ? -Infinity : p.y + fromSI(margin, headUnit),
							ratio === null ? -Infinity : ratio * p.y
						)
					})),
					margin: margin === null ? null : fromSI(margin, headUnit),
					ratio,
					source: sources.npshMargin ?? 'your values'
				}
			: null;
	const rating = data?.motorRatedPower;
	const overlays: CheckOverlays = {
		preferred,
		allowable: aor
			? {
					from: x(aor.flowMin * s),
					to: x(aor.flowMax * s),
					ratedFrom: x(aor.flowMin),
					ratedTo: x(aor.flowMax)
				}
			: null,
		minimumFlow: floor
			? { flow: x(floor.value * s), rated: x(floor.value), name: floor.name }
			: null,
		npshRequired,
		motorRating:
			rating === null || rating === undefined ? null : fromSI(rating, displayUnit('power', prefs))
	};
	return Object.values(overlays).some((v) => v !== null) ? overlays : null;
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

/**
 * What a chip shows or hides: a panel below the head, a speed-controlled pump's speed range, or
 * the design checks' limits (D19).
 */
export type ChipKey = Exclude<PanelKey, 'head'> | 'speed' | 'checks';
const CHIP_KEYS: readonly ChipKey[] = ['efficiency', 'power', 'npsh', 'speed', 'checks'];

/** The chips' names. */
export const CHIP_LABELS: Readonly<Record<ChipKey, string>> = {
	efficiency: 'Efficiency',
	power: 'Shaft power',
	npsh: 'NPSH',
	speed: 'Speed range',
	checks: 'Design checks'
};

/** What was hidden before in this browser ([] where storage is refused or holds nothing). */
export function loadHiddenPanels(): ChipKey[] {
	try {
		const parsed: unknown = JSON.parse(localStorage.getItem(HIDDEN_PANELS_KEY) ?? '[]');
		return Array.isArray(parsed) ? CHIP_KEYS.filter((p) => parsed.includes(p)) : [];
	} catch {
		return [];
	}
}

/** Remember what is hidden; a refused write only loses the convenience. */
export function saveHiddenPanels(hidden: readonly ChipKey[]): void {
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
	/** The curve facts: best efficiency, shutoff, rising head, speed range (§6, slice 2). */
	facts: string[];
	/** The design checks' limits drawn (D19), when shown. */
	checks: string[];
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
	/** A speed-controlled pump's speed range is shown. */
	speedShown?: boolean;
	/** The design checks' limits are shown. */
	checksShown?: boolean;
}

/** The figure's notes, from one function the screen and the image both use. */
export function chartNotes({
	data,
	result,
	system,
	othersControlled = false,
	reasonsIn = 'the data table says',
	shown = ['head'],
	speedShown = false,
	checksShown = false
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
	return {
		pump,
		curve,
		method,
		extrapolated,
		panels: panelNotes(data, result, shown),
		facts: factNotes(data, speedShown),
		checks: checksShown ? checkNotes(data, shown) : []
	};
}

/**
 * The design checks' limits as sentences (screen and image): what each mark is, its values and
 * where they came from. Design practice, not physics (GOALS §4.6); the verdicts are the Checks
 * view's.
 */
function checkNotes(d: PumpChartData, shown: readonly PanelKey[]): string[] {
	const c = d.checks;
	if (!c) return [];
	const fmt = (v: number) => formatNumber(v, 4);
	const pct = (v: number) => `${formatNumber(v * 100, 4)} %`;
	const flow = (v: number) => `${fmt(v)} ${d.flowUnit}`;
	const notes: string[] = [];
	const p = c.preferred;
	if (p) {
		const fractions =
			p.low !== null && p.high !== null
				? `${pct(p.low)} to ${pct(p.high)}`
				: p.low !== null
					? `at least ${pct(p.low)}`
					: `at most ${pct(p.high!)}`;
		const flows =
			p.from !== null && p.to !== null
				? `${fmt(p.from)} to ${flow(p.to)}`
				: p.from !== null
					? `from ${flow(p.from)}`
					: `up to ${flow(p.to!)}`;
		notes.push(
			`Shaded blue (POR): the preferred operating region, ${fractions} of the best efficiency flow at this speed (${flows}; ${p.source}).`
		);
	}
	if (c.allowable)
		notes.push(
			`Shaded grey (AOR): the allowable operating region from the pump's manufacturer data, ${fmt(c.allowable.from)} to ${flow(c.allowable.to)} at this speed (${fmt(c.allowable.ratedFrom)} to ${flow(c.allowable.ratedTo)} at rated speed, × speed by the affinity laws).`
		);
	if (c.minimumFlow)
		notes.push(
			`Dash-dot line: the ${c.minimumFlow.name}, ${flow(c.minimumFlow.flow)} at this speed (${flow(c.minimumFlow.rated)} at rated speed), the larger of the curve's minimum flows.`
		);
	const n = c.npshRequired;
	if (n && shown.includes('npsh')) {
		const terms = [
			...(n.margin !== null ? [`NPSHr + ${fmt(n.margin)} ${d.headUnit}`] : []),
			...(n.ratio !== null ? [`${fmt(n.ratio)} × NPSHr`] : [])
		];
		notes.push(
			`Dotted on the NPSH panel: the NPSHa the NPSH margin check requires, ${
				terms.length > 1 ? `the greater of ${terms.join(' and ')}` : terms[0]
			} (${n.source}).`
		);
	}
	if (c.motorRating !== null && shown.includes('power') && d.power)
		notes.push(
			`Dashed on the power panel: the motor's rated power, ${fmt(c.motorRating)} ${d.powerUnit} (manufacturer data; no service-factor margin).`
		);
	notes.push(
		'These are the limits of the design checks you turned on, design practice, not physics: Results → Checks says whether the duty meets them.'
	);
	return notes;
}

/** The curve facts as sentences (screen and image). */
function factNotes(d: PumpChartData, speedShown: boolean): string[] {
	const fmt = (v: number) => formatNumber(v, 4);
	const { bep, shutoff, rising, speedRange } = d.facts;
	const notes: string[] = [];
	if (bep)
		notes.push(
			`Best efficiency point (+): ${fmt(bep.efficiency.y)} % at ${fmt(bep.head.x)} ${d.flowUnit} and ${fmt(bep.head.y)} ${d.headUnit}${
				bep.headExtrapolated ? ' (head extrapolated)' : ''
			}, the efficiency curve's highest point inside its data, at this speed.`
		);
	else if (d.facts.hasEfficiency)
		notes.push(
			"No best efficiency point is marked: the efficiency data's highest point is at an end of the data, so the data do not show a maximum."
		);
	notes.push(
		`Shutoff head (–): ${fmt(shutoff.point.y)} ${d.headUnit}${
			shutoff.extrapolated
				? ", extrapolated along the curve's start slope (the data start above zero flow)"
				: ''
		}.`
	);
	for (const [lo, hi] of rising.ranges)
		notes.push(
			`The head rises with flow from ${fmt(lo)} to ${fmt(hi)} ${d.flowUnit} (amber): a system curve can cross the pump curve more than once there.`
		);
	if (speedShown && speedRange) {
		const levels = speedRange.iso.filter((l) => !l.best).map((l) => l.efficiency);
		const unique = [...new Set(levels.map((l) => fmt(l)))];
		const iso = speedRange.iso.length
			? `; dotted, the lines of constant efficiency through the best efficiency point${
					unique.length ? ` and at ${unique.join(', ')} %` : ''
				}, H ∝ Q² by the affinity laws with η₀(Q/s) unchanged (no reduced-speed efficiency correction)`
			: '';
		notes.push(
			`Speed range of the flow control: the pump curve at its minimum (${fmt(speedRange.min.speed)} %) and maximum (${fmt(speedRange.max.speed)} %) speeds${iso}.`
		);
	}
	return notes;
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
