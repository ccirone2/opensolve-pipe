/**
 * A system curve as the charts draw it (docs/proposals/open-defects-2.md §2 C1): the line, its
 * vertical parts and the words for them. The points are synthetic, shaped as the API's
 * SystemCurvePoint (models/api.py: reason, openHead, openHeadBound, limitFlow); the recorded
 * condenser responses are drawn in pump-group-system.test.ts and pump-chart.test.ts.
 */
import { describe, expect, it } from 'vitest';
import { systemCurvePoint, systemCurveResponse } from '$lib/testing/results';
import {
	pointRay,
	systemCurvePoints,
	systemLine,
	verticalCell,
	verticalSummary,
	verticalWords,
	type SystemLineInput
} from './system-curve-line';

const point = (flow: number, head: number | null, rest: Partial<SystemLineInput> = {}) => ({
	flow,
	head,
	reason: null,
	openHead: null,
	openHeadBound: null,
	limitFlow: null,
	...rest
});
const atSwitch = (flow: number, openHead: unknown, openHeadBound: unknown) =>
	point(flow, null, {
		reason: 'valve_at_switch',
		openHead: openHead as number,
		openHeadBound: openHeadBound as 'lower'
	});

describe('a system curve as drawn', () => {
	it('keeps every point with a head, in flow order, in display units', () => {
		const drawn = systemLine([point(0.002, 12), point(0, 10), point(0.001, 11)], 'L/s', 'm');
		expect(drawn.line).toEqual([
			{ x: 0, y: 10 },
			{ x: 1, y: 11 },
			{ x: 2, y: 12 }
		]);
		expect(drawn.rays).toEqual([]);
		expect(drawn.missing).toBe(0);
		expect(drawn.past).toEqual([]);
	});

	it('draws a switch with a finite openHead as its foot in the line and a ray, up or down', () => {
		const up = systemLine(
			[point(0, 10), atSwitch(0.003, 24.6, 'lower'), point(0.004, null)],
			'L/s',
			'm'
		);
		expect(up.line).toEqual([
			{ x: 0, y: 10 },
			{ x: 3, y: 24.6, bound: 'lower' },
			{ x: 4, y: null }
		]);
		expect(up.rays).toEqual([{ x: 3, from: 24.6, bound: 'lower' }]);
		// The API's count of points without a head: the vertical's point among them.
		expect(up.missing).toBe(2);
		const down = systemLine([atSwitch(0.003, 0.3048, 'upper')], 'L/s', 'ft');
		expect(down.rays).toEqual([{ x: 3, from: 1, bound: 'upper' }]);
		expect(down.line).toEqual([{ x: 3, y: 1, bound: 'upper' }]);
	});

	it('leaves a switch without a finite openHead or a known bound a gap, as every other reason', () => {
		for (const [head, bound] of [
			[null, 'lower'],
			[Number.NaN, 'lower'],
			[Number.POSITIVE_INFINITY, 'lower'],
			[20, null],
			[20, 'sideways']
		] as const) {
			const drawn = systemLine([atSwitch(0.001, head, bound)], 'L/s', 'm');
			expect(drawn.line, `${head} ${bound}`).toEqual([{ x: 1, y: null }]);
			expect(drawn.rays).toEqual([]);
			expect(pointRay(atSwitch(0.001, head, bound))).toBeNull();
		}
		for (const reason of [
			'beyond_limit',
			'below_floor',
			'no_way_through',
			'no_steady_state_found',
			'free_level',
			'closed_off',
			'not_converged',
			'not_computed',
			'made_up_code',
			null
		]) {
			// An openHead beside another reason is not a vertical part.
			const p = point(0.001, null, {
				reason: reason as 'closed_off',
				openHead: 20,
				openHeadBound: 'lower'
			});
			expect(systemLine([p], 'L/s', 'm').line, String(reason)).toEqual([{ x: 1, y: null }]);
			expect(pointRay(p)).toBeNull();
		}
		// A point with a head is never a vertical part, whatever else it carries.
		expect(pointRay(point(0.001, 5, { reason: 'valve_at_switch', openHead: 20 }))).toBeNull();
	});

	it('counts the points past each limit, a negative limit (every flow beyond it) too', () => {
		const drawn = systemLine(
			[
				point(0.001, null, { reason: 'below_floor', limitFlow: 0.0015 }),
				point(0.002, 7),
				atSwitch(0.003, 24.6, 'lower'),
				point(0.004, null, { reason: 'beyond_limit', limitFlow: 0.003 }),
				point(0.005, null, { reason: 'beyond_limit', limitFlow: 0.003 }),
				point(0.006, null, { reason: 'not_converged' }),
				point(0.007, null, { reason: 'beyond_limit', limitFlow: null })
			],
			'L/s',
			'm'
		);
		expect(drawn.past).toEqual([
			{ limit: 1.5, side: 'below', count: 1 },
			{ limit: 3, side: 'beyond', count: 2 }
		]);
		const all = systemLine(
			[0, 0.001].map((q) => point(q, null, { reason: 'beyond_limit', limitFlow: -0.0005 })),
			'L/s',
			'm'
		);
		expect(all.line.every((p) => p.y === null)).toBe(true);
		expect(all.rays).toEqual([]);
		expect(all.past).toEqual([{ limit: -0.5, side: 'beyond', count: 2 }]);
	});
});

describe('the words for a vertical part', () => {
	const units = { flowUnit: 'L/s', headUnit: 'm' };

	it('names the vertical part, the flows past its limit and the other gaps', () => {
		const drawn = systemLine(
			[
				point(0.002, 7),
				atSwitch(0.003, 24.6, 'lower'),
				point(0.004, null, { reason: 'beyond_limit', limitFlow: 0.003 }),
				point(0.005, null, { reason: 'beyond_limit', limitFlow: 0.003 }),
				point(0.006, null, { reason: 'not_converged' })
			],
			'L/s',
			'm'
		);
		expect(verticalWords(drawn, { value: 'rise', edge: 'the plot', ...units })).toBe(
			"at 3 L/s it is undetermined, any rise at or above 24.6 m holding, drawn as the curve's vertical part from there to the top of the plot; at the 2 flows sampled beyond 3 L/s no steady state carries the flow; the other is a gap in the line"
		);
		const down = systemLine(
			[
				atSwitch(0.003, 24.6, 'upper'),
				point(0.001, null, { reason: 'below_floor', limitFlow: 0.003 })
			],
			'L/s',
			'm'
		);
		expect(verticalWords(down, { value: 'head', edge: 'the head axis', ...units })).toBe(
			"at 3 L/s it is undetermined, any head at or below 24.6 m holding, drawn as the curve's vertical part from there to the foot of the head axis; at the flow sampled below 3 L/s no steady state carries the flow"
		);
		// No vertical part: the notes keep their own words.
		expect(
			verticalWords(systemLine([point(0.001, null)], 'L/s', 'm'), {
				value: 'head',
				edge: 'the head axis',
				...units
			})
		).toBeNull();
	});

	it('says each vertical part in the accessible name, and its foot in the data table', () => {
		expect(
			verticalSummary(
				[
					{ x: 5678.117675999999, from: 24.626490325577457, bound: 'lower' },
					{ x: 3, from: 1, bound: 'upper' }
				],
				'L/s',
				'm'
			)
		).toBe(', vertical at 5678 L/s from 24.63 m up, vertical at 3 L/s from 1 m down');
		expect(verticalCell(24.626490325577457, 'lower')).toBe('≥ 24.63');
		expect(verticalCell(24.626490325577457, 'upper')).toBe('≤ 24.63');
	});
});

// docs/proposals/open-defects-2.md §3 C3: /system-curve's limit points, solved after the grid at
// the flows where its range beyond the limit or below its floor begins. Synthetic shapes, the
// API's SystemCurvePoint; the recorded condenser Winter case is drawn in pump-chart.test.ts.
describe('a system curve’s limit points (open-defects-2.md C3)', () => {
	it('merges them into the grid in flow order, each marked, the grid unmarked', () => {
		const curve = systemCurveResponse();
		const between = systemCurvePoint({
			flow: 0.015,
			reason: 'valve_at_switch',
			openHead: 17,
			openHeadBound: 'lower'
		});
		const above = systemCurvePoint({ flow: 0.025, head: 28, converged: true });
		curve.limitPoints = [above, between];
		const merged = systemCurvePoints(curve);
		expect(merged.map((p) => [p.flow, p.atLimit])).toEqual([
			[0, false],
			[0.01, false],
			[0.015, true],
			[0.02, false],
			[0.025, true],
			[0.03, false]
		]);
		expect(merged[2]).toEqual({ ...between, atLimit: true });
		expect(merged[0]).toEqual({ ...curve.points[0]!, atLimit: false });
		// The line takes the limit point's foot and ray like any grid point's.
		const drawn = systemLine(merged, 'L/s', 'm');
		expect(drawn.rays).toEqual([{ x: 15, from: 17, bound: 'lower' }]);
		expect(drawn.line.map((p) => p.x)).toEqual([0, 10, 15, 20, 25, 30]);
	});

	it('takes a response without limitPoints (an API deployed before C3) as having none', () => {
		const curve = systemCurveResponse();
		const old = { ...curve } as Partial<typeof curve>;
		delete old.limitPoints;
		const merged = systemCurvePoints(old as typeof curve);
		expect(merged).toEqual(curve.points.map((p) => ({ ...p, atLimit: false })));
		expect(systemCurvePoints({ ...curve, limitPoints: [] })).toEqual(merged);
	});
});
