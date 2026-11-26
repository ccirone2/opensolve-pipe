/**
 * A system curve as the charts draw it (CLAUDE.md D10; a group's, D21 slice 4b), and the words
 * for its vertical parts (docs/proposals/open-defects-2.md §2 C1): one source for the pump chart
 * and the group chart, on screen and in the image.
 *
 * A point with a head is a point of the line. A point whose head is undetermined because a control
 * valve sits at its switch (`valve_at_switch`, with a finite `openHead` and a known
 * `openHeadBound`) is a vertical part: the API states that every head on the bound's side of
 * `openHead` holds at that flow ('lower': at or above it; 'upper': at or below it). The line takes
 * `openHead` there, the bound itself, which is one of the heads that hold, marked with its bound
 * (`bound`, so a tooltip says the range, never a bare head), and a ray runs from it to the edge of
 * its own y axis: the top for 'lower', the foot for 'upper'. Where an FCV's setpoint is reached,
 * the curve so turns vertical at the limit, and a pump or group curve above `openHead` crosses it
 * there.
 *
 * Every other point without a head is a gap, never bridged: `beyond_limit` and `below_floor` state
 * where no steady state carries the flow, not the head at the limit, so nothing is drawn at a
 * limit unless a point there states its `openHead`; a `valve_at_switch` point without a finite
 * `openHead` or a known bound keeps the API's sentence, and is a gap.
 *
 * The points are a flat list in any order: a /system-curve response's grid and its limit points
 * (open-defects-2.md §3 C3: the points solved after the grid where its range beyond the flow limit
 * or below its floor begins) are merged in flow order (`systemCurvePoints`) before they are drawn,
 * listed or exported, so a limit point's vertical part is drawn like any other.
 */
import type { SystemCurveResponse } from '../api/types';
import { formatNumber, fromSI, type UnitId } from './units';

/** A point of a system curve: a pump's (D10), or a group's (D21, slice 4b). */
export type SystemLineInput = Pick<
	SystemCurveResponse['points'][number],
	'flow' | 'head' | 'reason' | 'openHead' | 'openHeadBound' | 'limitFlow'
>;

/** Which heads hold at a vertical part: at or above its foot ('lower'), or at or below ('upper'). */
export type RayBound = 'lower' | 'upper';

/** A point of the line as drawn (display units): a null head is a gap; `bound` a vertical's foot. */
export interface SystemLinePoint {
	x: number;
	y: number | null;
	/** The foot of a vertical part: `y` is `openHead`, the bound of the heads that hold there. */
	bound?: RayBound;
}

/** A vertical part, display units: at flow `x`, from `from` up ('lower') or down ('upper'). */
export interface SystemRay {
	x: number;
	from: number;
	bound: RayBound;
}

/** Points without a head past a flow limit: `count` of them beyond (or below) `limit`. */
export interface PastLimit {
	/** The limit flow (display unit): the API's `limitFlow`. */
	limit: number;
	/** 'beyond': `beyond_limit`, at flows above it; 'below': `below_floor`, at flows below it. */
	side: 'beyond' | 'below';
	count: number;
}

export interface SystemLine {
	/** Every point in flow order: its head, `openHead` at a vertical part, null for a gap. */
	line: SystemLinePoint[];
	rays: SystemRay[];
	/** Points the API gives no head, a vertical part's among them (the counts in words). */
	missing: number;
	/** The points without a head past a limit, by limit, in flow order of their first point. */
	past: PastLimit[];
}

type SystemCurvePoint = SystemCurveResponse['points'][number];

/** A point of a /system-curve response as drawn, listed and exported: `atLimit` for a limit point. */
export type MergedSystemPoint = SystemCurvePoint & {
	/** One of the response's `limitPoints` (C3), not one of its evenly spaced flows. */
	atLimit: boolean;
};

/**
 * A /system-curve response's points and its limit points (open-defects-2.md §3 C3), in flow
 * order, each marked. A response without `limitPoints` (an API deployed before C3) has none.
 */
export function systemCurvePoints(
	curve: Pick<SystemCurveResponse, 'points'> & Partial<Pick<SystemCurveResponse, 'limitPoints'>>
): MergedSystemPoint[] {
	return [
		...curve.points.map((p) => ({ ...p, atLimit: false })),
		...(curve.limitPoints ?? []).map((p) => ({ ...p, atLimit: true }))
	].sort((a, b) => a.flow - b.flow);
}

function finite(value: number | null | undefined): value is number {
	return typeof value === 'number' && Number.isFinite(value);
}

/** The vertical part a point states, in SI (null: none). */
export function pointRay(
	p: Pick<SystemLineInput, 'head' | 'reason' | 'openHead' | 'openHeadBound'>
): { from: number; bound: RayBound } | null {
	if (p.head !== null || p.reason !== 'valve_at_switch') return null;
	const bound = p.openHeadBound;
	if (!finite(p.openHead) || (bound !== 'lower' && bound !== 'upper')) return null;
	return { from: p.openHead, bound };
}

/** The line, the vertical parts and the limits of `points` (any order), in the units given. */
export function systemLine(
	points: readonly SystemLineInput[],
	flowUnit: UnitId,
	headUnit: UnitId
): SystemLine {
	const sorted = [...points].sort((a, b) => a.flow - b.flow);
	const rays: SystemRay[] = [];
	const past: PastLimit[] = [];
	const line = sorted.map((p): SystemLinePoint => {
		const x = fromSI(p.flow, flowUnit);
		if (p.head !== null) return { x, y: fromSI(p.head, headUnit) };
		const ray = pointRay(p);
		if (ray) {
			const from = fromSI(ray.from, headUnit);
			rays.push({ x, from, bound: ray.bound });
			return { x, y: from, bound: ray.bound };
		}
		const side =
			p.reason === 'beyond_limit' ? 'beyond' : p.reason === 'below_floor' ? 'below' : null;
		if (side && finite(p.limitFlow)) {
			const limit = fromSI(p.limitFlow, flowUnit);
			const group = past.find((g) => g.side === side && g.limit === limit);
			if (group) group.count++;
			else past.push({ limit, side, count: 1 });
		}
		return { x, y: null };
	});
	return { line, rays, missing: sorted.filter((p) => p.head === null).length, past };
}

/** How the words name a curve's value and the edge its vertical parts run to. */
export interface VerticalWordsOptions {
	/** 'head' (a pump's system curve) or 'rise' (a group's). */
	value: 'head' | 'rise';
	/** The edge of the y axis a ray runs to, "the plot" or "the head axis". */
	edge: string;
	flowUnit: string;
	headUnit: string;
}

const fmt = (v: number) => formatNumber(v, 4);

/** "at or above" for a ray from its foot up, "at or below" for one down. */
export function boundWords(bound: RayBound): string {
	return bound === 'lower' ? 'at or above' : 'at or below';
}

/**
 * Why the points without a head are drawn as they are, when the curve has a vertical part (null
 * without one; the notes then keep their words): "at 5678 L/s it is undetermined, any rise at or
 * above 24.63 m holding, drawn as the curve's vertical part from there to the top of the plot; at
 * the 24 flows sampled beyond 5678 L/s no steady state carries the flow". Points past a limit lie
 * where no steady state exists, not in a gap of the line; any other is a gap.
 */
export function verticalWords(
	drawn: Pick<SystemLine, 'rays' | 'missing' | 'past'>,
	{ value, edge, flowUnit, headUnit }: VerticalWordsOptions
): string | null {
	if (!drawn.rays.length) return null;
	const rays = drawn.rays.map(
		(r) =>
			`at ${fmt(r.x)} ${flowUnit} it is undetermined, any ${value} ${boundWords(r.bound)} ${fmt(r.from)} ${headUnit} holding, drawn as the curve's vertical part from there to the ${r.bound === 'lower' ? 'top' : 'foot'} of ${edge}`
	);
	const past = drawn.past.map(
		(g) =>
			`at ${g.count === 1 ? 'the flow' : `the ${g.count} flows`} sampled ${g.side} ${fmt(g.limit)} ${flowUnit} no steady state carries the flow`
	);
	const gaps = drawn.missing - drawn.rays.length - drawn.past.reduce((n, g) => n + g.count, 0);
	const rest =
		gaps > 0
			? [gaps === 1 ? 'the other is a gap in the line' : `the other ${gaps} are gaps in the line`]
			: [];
	return [...rays, ...past, ...rest].join('; ');
}

/** The accessible name's words for the vertical parts: ", vertical at 5678 L/s from 24.63 m up". */
export function verticalSummary(
	rays: readonly SystemRay[],
	flowUnit: string,
	headUnit: string
): string {
	return rays
		.map(
			(r) =>
				`, vertical at ${fmt(r.x)} ${flowUnit} from ${fmt(r.from)} ${headUnit} ${r.bound === 'lower' ? 'up' : 'down'}`
		)
		.join('');
}

/** A data table's cell for a vertical part's foot (display unit): "≥ 24.63", "≤ 24.63". */
export function verticalCell(from: number, bound: RayBound): string {
	return `${bound === 'lower' ? '≥' : '≤'} ${fmt(from)}`;
}
