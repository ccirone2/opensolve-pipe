/**
 * Pump chart data: the curve inside its data is solid, the extrapolated part dashed, and every
 * point is a reported value in display units. Pump results are made-up test inputs.
 */
import { describe, expect, it } from 'vitest';
import { pumpResult, systemCurvePoint, systemCurveResponse } from '../testing/results';
import { pumpTransferExample } from './examples';
import { chartNotes, otherCasesData, pumpChartData, ratedCurveRange } from './pump-chart';
import { IMPERIAL_UNITS, SI_UNITS } from './units';

const GPM = (231 * 0.0254 ** 3) / 60; // m³/s, US gallon = 231 in³
const FT = 0.3048;

describe('pump chart data', () => {
	it('reads the curve’s flow range at rated speed from the project', () => {
		expect(ratedCurveRange(pumpTransferExample(), 'P1')).toEqual([0, 0.03]);
		expect(ratedCurveRange(pumpTransferExample(), 'V1')).toBeNull();
	});

	it('maps the curve, system curve and operating point to display units', () => {
		const data = pumpChartData(pumpResult(), SI_UNITS, [0, 0.03], systemCurveResponse());
		expect(data.flowUnit).toBe('L/s');
		expect(data.headUnit).toBe('m');
		expect(data.curve.map((p) => [Number(p.x.toFixed(9)), p.y])).toEqual([
			[0, 30],
			[10, 28],
			[20, 22],
			[30, 12]
		]);
		expect(data.extrapolated).toEqual([]);
		expect(data.system?.map((p) => Number(p.x.toFixed(9)))).toEqual([0, 10, 20, 30]);
		expect(data.system?.map((p) => p.y)).toEqual([12, 14.5, 22, 34.5]);
		expect(data.systemMissing).toBe(0);
		// The flows the curve was requested over (SystemCurveResponse.flowRange), in L/s.
		expect(data.systemSpan?.map((v) => Number(v.toFixed(9)))).toEqual([0, 30]);
		expect(data.operating).toEqual({ x: expect.closeTo(20, 9), y: 22 });
		expect(data.range?.map((v) => Number(v.toFixed(9)))).toEqual([0, 30]);

		const us = pumpChartData(pumpResult(), IMPERIAL_UNITS, [0, 0.03]);
		expect(us.systemSpan).toBeNull();
		expect(us.flowUnit).toBe('gpm');
		expect(us.headUnit).toBe('ft');
		expect(us.operating?.x).toBeCloseTo(0.02 / GPM, 9);
		expect(us.operating?.y).toBeCloseTo(22 / FT, 9);
	});

	it('dashes the extrapolation from the curve’s end to an operating point beyond it', () => {
		const data = pumpChartData(
			pumpResult({ operatingFlow: 0.034, operatingHead: 7.5, inCurveRange: false }),
			SI_UNITS,
			[0, 0.03]
		);
		expect(data.curve).toHaveLength(4);
		expect(data.extrapolated).toHaveLength(1);
		const [from, to] = data.extrapolated[0]!;
		expect([from!.x, from!.y]).toEqual([expect.closeTo(30, 9), 12]);
		expect([to!.x, to!.y]).toEqual([expect.closeTo(34, 9), 7.5]);
		expect(data.inCurveRange).toBe(false);
	});

	it('dashes an operating point below a curve that starts above zero flow', () => {
		const data = pumpChartData(
			pumpResult({
				curve: [
					{ flow: 0.01, head: 28 },
					{ flow: 0.03, head: 12 }
				],
				operatingFlow: 0.005,
				operatingHead: 29,
				inCurveRange: false
			}),
			SI_UNITS,
			[0.01, 0.03]
		);
		expect(data.extrapolated).toEqual([
			[
				{ x: expect.closeTo(5, 9), y: 29 },
				{ x: expect.closeTo(10, 9), y: 28 }
			]
		]);
	});

	it('dashes sampled points outside the data range at the operating speed', () => {
		// A curve sampled beyond its data (made-up): data 0–0.03 m³/s at rated speed, 80 % speed.
		const data = pumpChartData(
			pumpResult({
				speed: 0.8,
				curve: [
					{ flow: 0, head: 19.2 },
					{ flow: 0.012, head: 17 },
					{ flow: 0.024, head: 7.7 },
					{ flow: 0.03, head: 3 }
				],
				operatingFlow: 0.012,
				operatingHead: 17
			}),
			SI_UNITS,
			[0, 0.03]
		);
		expect(data.range?.map((v) => Number(v.toFixed(9)))).toEqual([0, 24]);
		expect(data.curve.map((p) => p.y)).toEqual([19.2, 17, 7.7]);
		expect(data.extrapolated.map((line) => line.map((p) => p.y))).toEqual([[7.7, 3]]);
		expect(data.curveRows.map((r) => r.extrapolated)).toEqual([false, false, false, true]);
	});

	it('takes the sampled curve’s span as the data range when the curve definition is unknown', () => {
		const data = pumpChartData(pumpResult(), SI_UNITS);
		expect(data.range?.map((v) => Number(v.toFixed(9)))).toEqual([0, 30]);
		expect(data.extrapolated).toEqual([]);
	});

	it('has no operating point when the pump is off, and no system curve when none is given', () => {
		const data = pumpChartData(
			pumpResult({ status: 'off', operatingFlow: 0, operatingHead: -5 }),
			SI_UNITS,
			[0, 0.03]
		);
		expect(data.operating).toBeNull();
		expect(data.extrapolated).toEqual([]);
		expect(data.system).toBeNull();
		expect(data.systemRows).toEqual([]);
	});

	it('leaves system-curve points without a solution as gaps, with the API’s reason', () => {
		const data = pumpChartData(pumpResult(), SI_UNITS, [0, 0.03], systemCurveResponse('P1', [1]));
		expect(data.system?.map((p) => p.y)).toEqual([12, null, 22, 34.5]);
		expect(data.systemMissing).toBe(1);
		expect(data.systemRows).toEqual([
			{ flow: '0', head: '12', note: '' },
			{ flow: '10', head: '—', note: 'made-up reason: not converged' },
			{ flow: '20', head: '22', note: '' },
			{ flow: '30', head: '34.5', note: '' }
		]);
	});

	it('tells a point’s reason with names and display units, keeping the API’s sentence', () => {
		// The pump-transfer example's V1 made an FCV set to 0.02 m³/s (made-up test input): the
		// point at 0.03 m³/s is beyond what it passes.
		const project = pumpTransferExample();
		project.components[2] = {
			type: 'valve',
			valveType: 'fcv',
			id: 'V1',
			name: 'Flow limiter',
			elevation: 0,
			status: 'active',
			setpoint: 0.02,
			ports: project.components[2]!.ports
		};
		const curve = systemCurveResponse('P1', [3]);
		const message =
			"no steady state carries this flow: every way from the pump's discharge back to its " +
			"suction, through the network or a reservoir or reference node, passes FCV 'V1', which " +
			'passes at most 0.02 m³/s that way (an FCV passes neither reverse flow nor more than its setpoint)';
		curve.points[3] = systemCurvePoint({
			flow: 0.03,
			message,
			reason: 'beyond_limit',
			componentIds: ['V1'],
			limitFlow: 0.02,
			passedFlow: 0.02
		});
		const names = { project, solved: project };
		const row = pumpChartData(pumpResult(), IMPERIAL_UNITS, [0, 0.03], curve, names).systemRows[3];
		expect(row).toEqual({
			flow: String(Number((0.03 / GPM).toPrecision(4))),
			head: '—',
			note:
				"No steady state carries this flow: every way from the pump's discharge back to its " +
				'suction, through the network or a reservoir or reference node, passes Flow limiter, ' +
				`which passes at most ${Number((0.02 / GPM).toPrecision(4))} gpm that way (an FCV ` +
				'passes neither reverse flow nor more than its flow setpoint).',
			detail: message
		});
		// Without names, the API's sentence, with no detail; a point with a head has neither.
		const plain = pumpChartData(pumpResult(), SI_UNITS, [0, 0.03], curve).systemRows;
		expect(plain[3]).toEqual({ flow: '30', head: '—', note: message });
		expect(pumpChartData(pumpResult(), SI_UNITS, [0, 0.03], curve, names).systemRows[0]).toEqual({
			flow: '0',
			head: '12',
			note: ''
		});
		// Other cases' curves are told the same way.
		const [other] = otherCasesData(
			[{ key: 'S1', name: 'Winter', result: pumpResult(), stale: false, system: curve }],
			SI_UNITS,
			[0, 0.03],
			1,
			names
		);
		expect(other!.systemRows[3]!.note).toContain(
			'passes Flow limiter, which passes at most 20 L/s'
		);
		expect(other!.systemRows[3]!.detail).toBe(message);
	});

	it('formats data-table rows to 4 significant figures', () => {
		const data = pumpChartData(pumpResult(), IMPERIAL_UNITS, [0, 0.03]);
		expect(data.curveRows[1]).toEqual({
			flow: String(Number((0.01 / GPM).toPrecision(4))),
			head: String(Number((28 / FT).toPrecision(4))),
			extrapolated: false
		});
	});
});

describe('pumps not running', () => {
	it('marks a pump held at zero flow at the head the API reports, and an off pump not at all', () => {
		const held = pumpChartData(
			pumpResult({ status: 'no_flow', operatingFlow: 0, operatingHead: 30 }),
			SI_UNITS,
			[0, 0.03]
		);
		expect(held.operating).toBeNull();
		expect(held.held).toEqual({ x: 0, y: 30 });
		const off = pumpChartData(
			pumpResult({ status: 'off', operatingFlow: 0, operatingHead: 0 }),
			SI_UNITS,
			[0, 0.03]
		);
		expect(off.operating).toBeNull();
		expect(off.held).toBeNull();
	});
});

// The notes the screen and the image both use (proposal export.md §3.4).
describe('chart notes', () => {
	it('tells the pump, the system curve, how it was computed and the extrapolation', () => {
		const data = pumpChartData(
			pumpResult({ operatingFlow: 0.034, operatingHead: 7.5, inCurveRange: false }),
			SI_UNITS,
			[0, 0.03],
			systemCurveResponse('P1', [1])
		);
		const notes = chartNotes({
			data,
			result: pumpResult(),
			system: { status: 'ready', curve: systemCurveResponse('P1', [1]) }
		});
		expect(notes.pump).toBeNull();
		expect(notes.curve).toEqual({
			kind: 'missing',
			text:
				'1 of 4 system-curve points have no head: the line has gaps there, and the data table ' +
				'says why for each (no steady state carries the flow, its head is undetermined, its ' +
				'solve did not converge, or it was not computed).'
		});
		expect(notes.method).toBe(
			'System curve: the network of this solve, solved again with the pump replaced by each of ' +
				'4 evenly spaced flows from 0 to 30 L/s (other pumps running, valves following their ' +
				'rules); the system head at each flow is the EGL at the discharge minus the EGL at the ' +
				'suction.'
		);
		expect(notes.extrapolated).toBe(
			"Dashed: the pump curve extrapolated beyond its data (0 to 30 L/s at this speed), along the curve's end slope, as the solver does."
		);
		// The image has no data table: it says where the reasons are instead.
		const image = chartNotes({
			data,
			result: pumpResult(),
			system: { status: 'ready', curve: systemCurveResponse('P1', [1]) },
			reasonsIn: 'the workbook says'
		});
		expect(image.curve?.text).toBe(
			'1 of 4 system-curve points have no head: the line has gaps there, and the workbook says ' +
				'why for each (no steady state carries the flow, its head is undetermined, its solve did ' +
				'not converge, or it was not computed).'
		);
		expect({ ...image, curve: null }).toEqual({ ...notes, curve: null });
	});

	it('says why the system curve is not shown, and when the pump is off or held', () => {
		const result = pumpResult();
		const data = pumpChartData(result, SI_UNITS);
		const curve = (system: Parameters<typeof chartNotes>[0]['system']) =>
			chartNotes({ data, result, system }).curve;
		expect(curve(undefined)).toEqual({
			kind: 'cancelled',
			text: 'The system curve has not been computed for this solve.'
		});
		expect(curve({ status: 'loading' })?.kind).toBe('loading');
		expect(curve({ status: 'error', message: 'Made-up message.' })).toEqual({
			kind: 'error',
			text: 'The system curve could not be computed: Made-up message.'
		});
		expect(curve({ status: 'cancelled', by: 'user' })?.text).toBe(
			'The system curve was not computed: you cancelled it.'
		);
		expect(curve({ status: 'cancelled', by: 'goalSeek' })?.text).toBe(
			'The system curve was not computed: a goal seek was started.'
		);
		expect(curve({ status: 'cancelled', by: 'solve' })?.text).toBe(
			'The system curve was not computed: a new solve was started.'
		);
		const allMissing = systemCurveResponse('P1', [0, 1, 2, 3]);
		expect(
			chartNotes({
				data: pumpChartData(result, SI_UNITS, null, allMissing),
				result,
				system: { status: 'ready', curve: allMissing }
			}).curve?.text
		).toMatch(/^No point of the system curve has a head, so it is not drawn; the data table/);

		const off = pumpResult({ status: 'off', operatingFlow: 0 });
		expect(
			chartNotes({ data: pumpChartData(off, SI_UNITS), result: off, system: undefined }).pump
		).toBe(
			'This pump is off: it carries no flow. Its curve is shown at its set speed, for reference.'
		);
		const held = pumpResult({ status: 'no_flow', operatingFlow: 0, operatingHead: 31 });
		expect(
			chartNotes({ data: pumpChartData(held, SI_UNITS), result: held, system: undefined }).pump
		).toBe(
			'This pump is held at zero flow by its check (see its flag). The diamond marks zero flow at the head across the pump.'
		);
	});
});
