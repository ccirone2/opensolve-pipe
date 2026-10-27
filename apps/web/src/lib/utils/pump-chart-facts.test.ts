/**
 * The pump chart's curve facts (proposal pump-chart.md §6, slice 2): the best efficiency point,
 * the shutoff head (and the start tangent down to it when the data start above zero flow), where
 * the head rises, a speed-controlled pump's speed range, their notes and datasets. Pump results
 * are made-up test inputs (testing/results.ts).
 */
import { describe, expect, it } from 'vitest';
import type { PumpResult } from '../api/types';
import { pumpResult } from '../testing/results';
import { chartNotes, pumpChartData } from './pump-chart';
import { pumpChartConfig } from './pump-chart-config';
import { SI_UNITS } from './units';

/** A flow-controlled pump at 80 % speed with a BEP, a hump, and its speed range (SI values). */
function factsPump(values: Partial<PumpResult> = {}): PumpResult {
	return pumpResult({
		speed: 0.8,
		control: { mode: 'flow', setpoint: 0.016, state: 'active', setpointAchieved: true },
		efficiencyCurve: [
			{ flow: 0.004, efficiency: 0.4 },
			{ flow: 0.012, efficiency: 0.7 },
			{ flow: 0.02, efficiency: 0.6 }
		],
		bestEfficiencyPoint: { flow: 0.012, efficiency: 0.7, head: 18, headExtrapolated: false },
		shutoffHead: { head: 19.2, extrapolated: false },
		risingHeadRanges: [{ flowMin: 0, flowMax: 0.005 }],
		speedCurves: [
			{
				limit: 'min',
				speed: 0.5,
				curve: [
					{ flow: 0, head: 7.5 },
					{ flow: 0.015, head: 3 }
				]
			},
			{
				limit: 'max',
				speed: 1,
				curve: [
					{ flow: 0, head: 30 },
					{ flow: 0.03, head: 12 }
				]
			}
		],
		isoEfficiencyLines: [
			{
				efficiency: 0.7,
				best: true,
				ratedFlow: 0.015,
				points: [
					{ flow: 0.0075, head: 6.25 },
					{ flow: 0.015, head: 25 }
				]
			},
			{
				efficiency: 0.65,
				best: false,
				ratedFlow: 0.01,
				points: [
					{ flow: 0.005, head: 7 },
					{ flow: 0.01, head: 28 }
				]
			}
		],
		...values
	});
}

const SPEED_NOTE = /^Speed range of the flow control/;

describe('pump chart curve facts', () => {
	it('gives the facts in display units', () => {
		const { facts } = pumpChartData(factsPump(), SI_UNITS);
		expect(facts.bep).toEqual({
			head: { x: 12, y: 18 },
			efficiency: { x: 12, y: 70 },
			headExtrapolated: false
		});
		expect(facts.shutoff).toEqual({ point: { x: 0, y: 19.2 }, extrapolated: false });
		expect(facts.rising.ranges).toEqual([[0, 5]]);
		// The rising stretch follows the pump line from 0 to 5 L/s (read at its ends).
		expect(facts.rising.lines[0]![0]).toEqual({ x: 0, y: 30 });
		expect(facts.rising.lines[0]!.at(-1)!.x).toBe(5);
		expect(facts.speedRange!.min).toEqual({
			speed: 50,
			curve: [
				{ x: 0, y: 7.5 },
				{ x: 15, y: 3 }
			]
		});
		expect(facts.speedRange!.iso.map((l) => [l.efficiency, l.best])).toEqual([
			[70, true],
			[65, false]
		]);
		expect(pumpChartData(pumpResult(), SI_UNITS).facts.speedRange).toBeNull();
	});

	it('draws the start tangent down to an extrapolated shutoff head, dashed', () => {
		const result = pumpResult({
			curve: [
				{ flow: 0.005, head: 28 },
				{ flow: 0.03, head: 12 }
			],
			shutoffHead: { head: 30, extrapolated: true }
		});
		const data = pumpChartData(result, SI_UNITS, [0.005, 0.03]);
		expect(data.extrapolated[0]).toEqual([
			{ x: 0, y: 30 },
			{ x: 5, y: 28 }
		]);
		expect(chartNotes({ data, result, system: undefined }).facts).toContain(
			"Shutoff head (–): 30 m, extrapolated along the curve's start slope (the data start above zero flow)."
		);
	});

	it('says what the facts are, and the speed range only while it is shown', () => {
		const result = factsPump();
		const data = pumpChartData(result, SI_UNITS);
		const notes = chartNotes({ data, result, system: undefined, speedShown: true }).facts;
		expect(notes[0]).toBe(
			"Best efficiency point (+): 70 % at 12 L/s and 18 m, the efficiency curve's highest point inside its data, at this speed."
		);
		expect(notes[1]).toBe('Shutoff head (–): 19.2 m.');
		expect(notes[2]).toBe(
			'The head rises with flow from 0 to 5 L/s (amber): a system curve can cross the pump curve more than once there.'
		);
		expect(notes[3]).toMatch(SPEED_NOTE);
		expect(notes[3]).toContain('minimum (50 %) and maximum (100 %) speeds');
		expect(notes[3]).toContain('through the best efficiency point and at 65 %');
		const hidden = chartNotes({ data, result, system: undefined, speedShown: false }).facts;
		expect(hidden.some((n) => SPEED_NOTE.test(n))).toBe(false);
		// An efficiency curve whose highest point is at an end: no BEP, and why.
		const noBep = factsPump({ bestEfficiencyPoint: null });
		expect(
			chartNotes({ data: pumpChartData(noBep, SI_UNITS), result: noBep, system: undefined })
				.facts[0]
		).toMatch(/^No best efficiency point is marked/);
	});

	it('draws the facts on the head axis, the rising stretch under the pump curve', () => {
		const data = pumpChartData(factsPump(), SI_UNITS);
		const options = { speedText: '80 % speed', legendLabels: () => [], format: String };
		const labels = (config: ReturnType<typeof pumpChartConfig>) =>
			config.data.datasets.map((d) => d.label);
		const plain = pumpChartConfig(data, [], options);
		expect(labels(plain)).toEqual(
			expect.arrayContaining(['Head rises with flow', 'Shutoff head', 'Best efficiency point'])
		);
		expect(labels(plain).some((l) => /speed \((minimum|maximum)\)/.test(l ?? ''))).toBe(false);
		const rising = plain.data.datasets.find((d) => d.label === 'Head rises with flow')!;
		expect(rising.order).toBe(1);
		expect(rising.yAxisID).toBe('y');
		const withRange = pumpChartConfig(data, [], { ...options, speedRange: true });
		expect(labels(withRange)).toEqual(
			expect.arrayContaining([
				'Pump curve at 50 % speed (minimum)',
				'Pump curve at 100 % speed (maximum)',
				'Constant efficiency (dotted)'
			])
		);
		const iso = withRange.data.datasets.filter((d) => d.label === 'Constant efficiency (dotted)');
		expect(iso.map((d) => (d as { pointLabel?: string }).pointLabel)).toEqual(['BEP line', '65 %']);
		// One legend entry for all iso lines: the others are left out of the legend.
		expect(iso.map((d) => !!(d as { duty?: boolean }).duty)).toEqual([false, true]);
		// With the efficiency panel shown, the BEP is marked there too, on its axis.
		const withPanel = pumpChartConfig(data, [], { ...options, panels: ['head', 'efficiency'] });
		const beps = withPanel.data.datasets.filter((d) => d.label === 'Best efficiency point');
		expect(beps.map((d) => d.yAxisID)).toEqual(['y', 'yEfficiency']);
	});
});
