/**
 * Data for the pump chart (design §5): the pump curve at the operating speed, the system curve
 * and the operating point, in display units, split into the part of the pump curve inside its
 * data (solid) and the extrapolated part outside it (dashed).
 *
 * Every point comes from the PumpResult. The flow range of the curve's data at speed s is
 * s × [Q_min, Q_max] of the head-curve points the user entered (the affinity law the solver
 * applies; API PumpResult.curve spans exactly that range). When the curve definition is not
 * available, the span of the sampled curve is used instead.
 *
 * Outside that range the solver extrapolates the head along the curve's end slope, which is a
 * straight line in Q at a fixed speed (H = s²·H₀(Q/s) with H₀ linear), so the dashed segment from
 * the curve's end to an operating point outside the range is exactly that extrapolation; it joins
 * two values the API reported and adds none.
 */
import type { CurvePoint, Project, PumpResult, UnitPreferences } from '../api/types';
import { componentById } from './graph';
import { displayUnit, formatNumber, fromSI, unitLabel } from './units';

export interface ChartPoint {
	/** Flow, display unit. */
	x: number;
	/** Head, display unit. */
	y: number;
}

export interface PumpChartData {
	flowUnit: string;
	headUnit: string;
	/** Flow range of the curve's data at the operating speed, display unit (null: unknown). */
	range: [number, number] | null;
	/** The pump curve inside its data: solid. */
	curve: ChartPoint[];
	/** Extrapolated parts of the pump curve (each a polyline): dashed. */
	extrapolated: ChartPoint[][];
	/** The system curve, if the solve returned one. */
	system: ChartPoint[] | null;
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
	systemRows: { flow: string; head: string }[];
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
 */
export function pumpChartData(
	result: PumpResult,
	prefs: UnitPreferences,
	ratedRange: [number, number] | null = null
): PumpChartData {
	const flowUnit = displayUnit('flow', prefs);
	const headUnit = displayUnit('head', prefs);
	const point = (p: CurvePoint): ChartPoint => ({
		x: fromSI(p.flow, flowUnit),
		y: fromSI(p.head, headUnit)
	});

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

	const system = result.systemCurve?.length
		? [...result.systemCurve].sort((a, b) => a.flow - b.flow).map(point)
		: null;
	const fmt = (v: number) => formatNumber(v, 4);
	return {
		flowUnit: unitLabel('flow', flowUnit),
		headUnit: unitLabel('head', headUnit),
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
		systemRows: (system ?? []).map((c) => ({ flow: fmt(c.x), head: fmt(c.y) }))
	};
}
