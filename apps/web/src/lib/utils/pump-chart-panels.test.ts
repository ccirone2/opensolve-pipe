/**
 * The pump chart's panels below the head (proposal pump-chart.md §4): efficiency, shaft power
 * and NPSH from the API's samples, the readout and the NPSH crossing read from the drawn lines,
 * the panels' notes, and their stacked axes. Pump results and system curves are made-up test
 * inputs (testing/results.ts).
 */
import { describe, expect, it } from 'vitest';
import type { PumpResult } from '../api/types';
import { pumpResult, systemCurvePoint, systemCurveResponse } from '../testing/results';
import { plotHeight, CHART_HEIGHT, PANEL_HEIGHT } from './export/chart-image';
import {
	chartHeightRem,
	chartNotes,
	chartReadout,
	npshCrossing,
	pumpChartData,
	valueAt
} from './pump-chart';
import { pumpChartConfig } from './pump-chart-config';
import { formatNumber, IMPERIAL_UNITS, SI_UNITS } from './units';

/** The made-up pump with its efficiency, power and NPSHr curves over 0.005–0.03 m³/s. */
function richPump(values: Partial<PumpResult> = {}): PumpResult {
	return pumpResult({
		efficiencyCurve: [
			{ flow: 0.005, efficiency: 0.4 },
			{ flow: 0.02, efficiency: 0.7 },
			{ flow: 0.03, efficiency: 0.65 }
		],
		powerCurve: [
			{ flow: 0.005, shaftPower: 3500 },
			{ flow: 0.02, shaftPower: 6000 },
			{ flow: 0.03, shaftPower: 5500 }
		],
		npshrCurve: [
			{ flow: 0.005, npshr: 1 },
			{ flow: 0.02, npshr: 3 },
			{ flow: 0.03, npshr: 6 }
		],
		...values
	});
}

/** A system curve whose NPSHa falls from 14 m to 2 m: it meets NPSHr between 0.02 and 0.03. */
function npshaCurve() {
	const curve = systemCurveResponse();
	const npsha = [14, 13, 10, 2];
	return {
		...curve,
		points: curve.points.map((p, i) => ({ ...p, npshAvailable: npsha[i]! }))
	};
}

describe('pump chart panels', () => {
	it('has a panel for each curve the API sent, in order, the head always', () => {
		expect(pumpChartData(pumpResult(), SI_UNITS).panels).toEqual(['head']);
		const data = pumpChartData(richPump(), SI_UNITS);
		expect(data.panels).toEqual(['head', 'efficiency', 'power', 'npsh']);
		// Duty NPSH values alone draw no line: no panel.
		expect(pumpChartData(pumpResult({ npshAvailable: 9 }), SI_UNITS).panels).toEqual(['head']);
		// NPSHa along a computed system curve is a line.
		expect(pumpChartData(pumpResult(), SI_UNITS, null, npshaCurve()).panels).toEqual([
			'head',
			'npsh'
		]);
	});

	it('gives each panel its curve and duty value in display units', () => {
		const data = pumpChartData(richPump(), IMPERIAL_UNITS, null, npshaCurve());
		const gpm = (q: number) => q / 6.30901964e-5;
		const ft = (h: number) => h / 0.3048;
		const hp = (w: number) => w / 745.6998715822702;
		expect(data.powerUnit).toBe('hp');
		expect(data.efficiency!.curve[1]!.x).toBeCloseTo(gpm(0.02), 9);
		expect(data.efficiency!.curve[1]!.y).toBeCloseTo(70, 12);
		expect(data.efficiency!.duty!.x).toBeCloseTo(gpm(0.02), 9);
		expect(data.efficiency!.duty!.y).toBe(70);
		expect(data.efficiency!.held).toBe(false);
		expect(data.power!.curve[0]!.y).toBeCloseTo(hp(3500), 9);
		expect(data.power!.duty!.y).toBeCloseTo(hp(5000), 9);
		expect(data.power!.largest.y).toBeCloseTo(hp(6000), 9);
		expect(data.npsh!.required![2]!.y).toBeCloseTo(ft(6), 9);
		expect(data.npsh!.available!.map((p) => p.y)).toEqual([14, 13, 10, 2].map(ft));
		expect(data.npsh!.requiredAt!.y).toBeCloseTo(ft(3), 9);
		expect(data.npsh!.availableAt!.y).toBeCloseTo(ft(12), 9);
		expect(data.systemRows[2]!.npsha).toBe(formatNumber(ft(10), 4));
	});

	it('marks a duty outside the efficiency data as held, and an off pump has no duty values', () => {
		const held = pumpChartData(richPump({ operatingFlow: 0.032 }), SI_UNITS);
		expect(held.efficiency!.held).toBe(true);
		const off = pumpChartData(richPump({ status: 'off' }), SI_UNITS);
		expect(off.efficiency!.duty).toBeNull();
		expect(off.power!.duty).toBeNull();
		expect(off.npsh!.requiredAt).toBeNull();
		expect(off.npsh!.availableAt).toBeNull();
	});

	it('reads a line as drawn: linear between samples, nothing outside them or across a gap', () => {
		const line = [
			{ x: 0, y: 10 },
			{ x: 10, y: 20 },
			{ x: 20, y: null },
			{ x: 30, y: 0 }
		];
		expect(valueAt(line, 5)).toBe(15);
		expect(valueAt(line, 10)).toBe(20);
		expect(valueAt(line, 15)).toBeNull();
		expect(valueAt(line, 25)).toBeNull();
		expect(valueAt(line, -1)).toBeNull();
		expect(valueAt(line, 31)).toBeNull();
	});

	it('finds the first flow where NPSHa falls below NPSHr', () => {
		const required = [
			{ x: 0, y: 2 },
			{ x: 30, y: 8 }
		];
		// NPSHa 10, 10, 2 at 0, 20, 30: NPSHa − NPSHr is 4 at 20 and −6 at 30, so they meet at 24.
		const available = [
			{ x: 0, y: 10 },
			{ x: 20, y: 10 },
			{ x: 30, y: 2 }
		];
		expect(npshCrossing(required, available)).toBeCloseTo(24, 12);
		expect(npshCrossing(required, available.slice(0, 2))).toBeNull();
		// A gap breaks the pair; points outside the NPSHr data are not compared.
		expect(
			npshCrossing(required, [
				{ x: 20, y: 10 },
				{ x: 25, y: null },
				{ x: 30, y: 2 }
			])
		).toBeNull();
		expect(
			npshCrossing(required, [
				{ x: 20, y: 10 },
				{ x: 40, y: 0 }
			])
		).toBeNull();
	});

	it('reads every line of the panels shown at one flow', () => {
		const data = pumpChartData(richPump(), SI_UNITS, null, npshaCurve());
		const at = chartReadout(data, data.panels, 20);
		expect(at.map((r) => [r.key, r.value])).toEqual([
			['pump', 22],
			['system', 22],
			['efficiency', 70],
			['power', 6],
			['npshr', 3],
			['npsha', 10]
		]);
		expect(chartReadout(data, ['head'], 20).map((r) => r.key)).toEqual(['pump', 'system']);
		// Below the efficiency, power and NPSHr data, only the lines drawn there.
		expect(chartReadout(data, data.panels, 2).map((r) => r.key)).toEqual([
			'pump',
			'system',
			'npsha'
		]);
	});

	it('says what the panels show and where they stop', () => {
		const data = pumpChartData(richPump({ speed: 0.9 }), SI_UNITS, null, npshaCurve());
		const notes = chartNotes({
			data,
			result: richPump({ speed: 0.9 }),
			system: undefined,
			shown: data.panels
		});
		expect(notes.panels).toEqual([
			'Efficiency at 90 % speed: η₀(Q/s), the affinity laws without an efficiency correction.',
			'Shaft power ρgQH/η over the flows that both the head and efficiency data reach; the largest there is 6 kW at 20 L/s (beyond the data it is not known).',
			expect.stringMatching(
				/^NPSHa falls below NPSHr at about 2\d\.?\d* L\/s \(read from the drawn lines\)/
			)
		]);
		// Hidden panels have no notes; without a system curve, NPSHa waits for it.
		expect(chartNotes({ data, result: richPump(), system: undefined }).panels).toEqual([]);
		const bare = pumpChartData(richPump(), SI_UNITS);
		expect(
			chartNotes({ data: bare, result: richPump(), system: undefined, shown: ['npsh'] }).panels
		).toEqual(['NPSHa along the system curve is drawn once the system curve is computed.']);
	});

	it('stacks one axis per panel shown on the shared flow axis, the head on top', () => {
		const data = pumpChartData(richPump(), SI_UNITS, null, npshaCurve());
		const options = { speedText: '100 % speed', legendLabels: () => [], format: String };
		const head = pumpChartConfig(data, [], options);
		expect(Object.keys(head.options!.scales!)).toEqual(['x', 'y']);
		expect(head.data.datasets.every((d) => d.yAxisID === 'y')).toBe(true);
		const all = pumpChartConfig(data, [], { ...options, panels: data.panels });
		const scales = all.options!.scales! as Record<string, { stack?: string; stackWeight?: number }>;
		// Chart.js stacks from the bottom up.
		expect(Object.keys(scales)).toEqual(['x', 'yNpsh', 'yPower', 'yEfficiency', 'y']);
		expect(scales.y!.stackWeight).toBe(3);
		expect(new Set(Object.values(scales).map((s) => s.stack))).toEqual(
			new Set([undefined, 'panels'])
		);
		const axis = (label: string) => all.data.datasets.find((d) => d.label === label)?.yAxisID;
		expect(axis('System curve')).toBe('y');
		expect(axis('Efficiency')).toBe('yEfficiency');
		expect(axis('Shaft power')).toBe('yPower');
		expect(axis('NPSHr')).toBe('yNpsh');
		expect(axis('NPSHa')).toBe('yNpsh');
		// The image grows by one panel height per panel below the head.
		expect(plotHeight(head)).toBe(CHART_HEIGHT);
		expect(plotHeight(all)).toBe(CHART_HEIGHT + 3 * PANEL_HEIGHT);
		expect(chartHeightRem(['head'], false)).toBe(18);
		expect(chartHeightRem(data.panels, true)).toBe(16 + 3 * 6);
	});

	it('keeps NPSHa gaps where a system-curve point has no NPSHa', () => {
		const curve = systemCurveResponse();
		curve.points[1] = systemCurvePoint({ flow: 0.01, head: 14.5, converged: true });
		curve.points[2] = { ...curve.points[2]!, npshAvailable: 10 };
		const data = pumpChartData(pumpResult(), SI_UNITS, null, curve);
		expect(data.npsh!.available!.map((p) => p.y)).toEqual([null, null, 10, null]);
	});
});
