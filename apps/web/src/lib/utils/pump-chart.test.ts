/**
 * Pump chart data: the curve inside its data is solid, the extrapolated part dashed, and every
 * point is a reported value in display units. Pump results are made-up test inputs.
 */
import { describe, expect, it } from 'vitest';
import { pumpResult } from '../testing/results';
import { pumpTransferExample } from './examples';
import { pumpChartData, ratedCurveRange } from './pump-chart';
import { IMPERIAL_UNITS, SI_UNITS } from './units';

const GPM = (231 * 0.0254 ** 3) / 60; // m³/s, US gallon = 231 in³
const FT = 0.3048;

describe('pump chart data', () => {
	it('reads the curve’s flow range at rated speed from the project', () => {
		expect(ratedCurveRange(pumpTransferExample(), 'P1')).toEqual([0, 0.03]);
		expect(ratedCurveRange(pumpTransferExample(), 'V1')).toBeNull();
	});

	it('maps the curve, system curve and operating point to display units', () => {
		const data = pumpChartData(pumpResult(), SI_UNITS, [0, 0.03]);
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
		expect(data.operating).toEqual({ x: expect.closeTo(20, 9), y: 22 });
		expect(data.range?.map((v) => Number(v.toFixed(9)))).toEqual([0, 30]);

		const us = pumpChartData(pumpResult(), IMPERIAL_UNITS, [0, 0.03]);
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

	it('has no operating point when the pump is off, and no system curve when none was returned', () => {
		const data = pumpChartData(
			pumpResult({ status: 'off', operatingFlow: 0, operatingHead: -5, systemCurve: null }),
			SI_UNITS,
			[0, 0.03]
		);
		expect(data.operating).toBeNull();
		expect(data.extrapolated).toEqual([]);
		expect(data.system).toBeNull();
		expect(data.systemRows).toEqual([]);
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
