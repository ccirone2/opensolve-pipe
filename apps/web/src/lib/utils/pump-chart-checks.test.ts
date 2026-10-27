/**
 * The design checks' limits on the pump chart (CLAUDE.md D19; utils/pump-chart.ts checkOverlays):
 * the real API's pump result of the shared fixture's `design-checks` case (export_input.py: the
 * pump at 90 % speed with a best efficiency point and manufacturer data, US display units), and
 * made-up results (test inputs) for the NPSH requirement, which that case has no NPSHr curve for.
 * The limits are the project's as solved; the chart never draws a verdict.
 */
import { describe, expect, it } from 'vitest';
import type { DesignChecks, PumpCurve, PumpResult } from '../api/types';
import { pumpResult } from '../testing/results';
import { fixtureInput } from './export/export-testing.testing';
import {
	checkOverlays,
	checksDrawn,
	chartNotes,
	pumpChartData,
	type PanelKey,
	type PumpChecksInput
} from './pump-chart';
import { pumpChartConfig } from './pump-chart-config';
import { displayUnit, fromSI, SI_UNITS } from './units';

const input = fixtureInput('design-checks');
const project = input.project;
const result = input.cases[0]!.response!.solvedState.pumpResults.P1!;
const prefs = input.prefs;
const curve = project.pumpLibrary[0]! as PumpCurve;
const checks = project.settings.designChecks!;
const sources = { npshMargin: 'HI 9.6.1-2012 (general) preset', operatingRegion: 'API 610 preset' };
const fixtureChecks: PumpChecksInput = { checks, curve, sources };
const flow = (si: number) => fromSI(si, displayUnit('flow', prefs));

describe('checkOverlays', () => {
	it('draws the preferred region from the BEP flow at this speed, the manufacturer data at s × flow', () => {
		expect(result.speed).toBe(0.9);
		const bep = result.bestEfficiencyPoint!;
		const o = checkOverlays(result, prefs, fixtureChecks, null)!;
		expect(o.preferred).toEqual({
			low: 0.7,
			high: 1.2,
			from: flow(0.7 * bep.flow),
			to: flow(1.2 * bep.flow),
			source: 'API 610 preset'
		});
		expect(o.allowable).toEqual({
			from: flow(0.006 * 0.9),
			to: flow(0.026 * 0.9),
			ratedFrom: flow(0.006),
			ratedTo: flow(0.026)
		});
		// The larger of the two minimum flows: the thermal one (0.005 > 0.004 m³/s).
		expect(o.minimumFlow).toEqual({
			flow: flow(0.005 * 0.9),
			rated: flow(0.005),
			name: 'minimum thermal flow'
		});
		expect(o.motorRating).toBe(fromSI(4000, displayUnit('power', prefs)));
		expect(o.npshRequired).toBeNull(); // no NPSHr curve
		// The duty against the band: inside it, as the Checks view says (119.6 % of the BEP flow).
		expect(flow(result.operatingFlow)).toBeGreaterThan(o.preferred!.from!);
		expect(flow(result.operatingFlow)).toBeLessThan(o.preferred!.to!);
	});

	it('reads the manufacturer data only with the operating region check on (as the API checks them)', () => {
		const velocityOnly: DesignChecks = { pipeVelocity: checks.pipeVelocity! };
		expect(
			checkOverlays(result, prefs, { ...fixtureChecks, checks: velocityOnly }, null)
		).toBeNull();
		const npshOnly: DesignChecks = { npshMargin: checks.npshMargin! };
		expect(checkOverlays(result, prefs, { ...fixtureChecks, checks: npshOnly }, null)).toBeNull();
		// An open end: from the lower limit to the axis's end.
		const lowOnly: DesignChecks = {
			operatingRegion: { preferredMin: 0.7, source: { kind: 'user' } }
		};
		const o = checkOverlays(result, prefs, { checks: lowOnly, curve: null, sources }, null)!;
		expect(o.preferred).toMatchObject({ low: 0.7, high: null, to: null });
		expect(o.allowable).toBeNull();
	});

	it('requires NPSHa ≥ max(NPSHr + margin, ratio × NPSHr) along the NPSHr line, in display units', () => {
		const npshr = [
			{ x: 1, y: 2 },
			{ x: 2, y: 20 }
		];
		const both: DesignChecks = {
			npshMargin: { minimumMargin: 1, minimumRatio: 1.1, source: { kind: 'user' } }
		};
		const si = checkOverlays(result, SI_UNITS, { checks: both, curve: null, sources }, npshr)!;
		// 2 + 1 m beats 1.1 × 2; 1.1 × 20 beats 20 + 1 m.
		expect(si.npshRequired!.line).toEqual([
			{ x: 1, y: 3 },
			{ x: 2, y: 22 }
		]);
		const us = checkOverlays(result, prefs, { checks: both, curve: null, sources }, npshr)!;
		const ft = fromSI(1, displayUnit('head', prefs));
		expect(us.npshRequired!.margin).toBe(ft);
		expect(us.npshRequired!.line[0]!.y).toBe(2 + ft);
		const ratioOnly: DesignChecks = { npshMargin: { minimumRatio: 1.3, source: { kind: 'user' } } };
		expect(
			checkOverlays(
				result,
				SI_UNITS,
				{ checks: ratioOnly, curve: null, sources },
				npshr
			)!.npshRequired!.line.map((p) => p.y)
		).toEqual([1.3 * 2, 1.3 * 20]);
	});
});

/** A made-up pump with every panel and an NPSHr curve (test input). */
function fullPump(values: Partial<PumpResult> = {}): PumpResult {
	return pumpResult({
		efficiencyCurve: [
			{ flow: 0.004, efficiency: 0.4 },
			{ flow: 0.012, efficiency: 0.7 },
			{ flow: 0.02, efficiency: 0.6 }
		],
		bestEfficiencyPoint: { flow: 0.012, efficiency: 0.7, head: 18, headExtrapolated: false },
		powerCurve: [
			{ flow: 0.004, shaftPower: 2000 },
			{ flow: 0.02, shaftPower: 5000 }
		],
		npshrCurve: [
			{ flow: 0, npshr: 1 },
			{ flow: 0.03, npshr: 4 }
		],
		...values
	});
}

const everything: PumpChecksInput = {
	checks: {
		npshMargin: { minimumMargin: 1, source: { kind: 'user' } },
		operatingRegion: { preferredMin: 0.7, preferredMax: 1.2, source: { kind: 'user' } }
	},
	curve: {
		id: 'C1',
		name: 'Curve',
		points: [
			{ flow: 0, head: 30 },
			{ flow: 0.03, head: 12 }
		],
		allowableOperatingRegion: { flowMin: 0.004, flowMax: 0.025 },
		minimumContinuousStableFlow: 0.003,
		motorRatedPower: 5500
	},
	sources: { npshMargin: 'your values', operatingRegion: 'your values' }
};

describe('the chart', () => {
	const data = pumpChartData(fullPump(), SI_UNITS, null, null, null, everything);
	const config = (on: boolean) =>
		pumpChartConfig(data, [], {
			speedText: '100 % speed',
			legendLabels: () => [],
			format: String,
			panels: ['head', 'efficiency', 'power', 'npsh'],
			checks: on
		});
	const labels = (on: boolean) => config(on).data.datasets.map((d) => d.label);

	it('draws the limits as datasets on their panels, with the regions and line in the legend', () => {
		const sets = config(true).data.datasets as { label?: string; yAxisID?: string }[];
		const axis = (label: string) => sets.find((d) => d.label === label)?.yAxisID;
		expect(axis('Preferred operating region (POR)')).toBe('y');
		expect(axis('Allowable operating region (AOR)')).toBe('y');
		expect(axis('Minimum flow (dash-dot)')).toBe('y');
		expect(axis('NPSHa required by the check (dotted)')).toBe('yNpsh');
		expect(axis('Motor rated power (dashed)')).toBe('yPower');
		// The rating at 5.5 kW across every flow the chart shows (the head curve's 30 L/s), not
		// only the power curve's 20 L/s, so a duty beyond the efficiency data is under it.
		expect(sets.find((d) => d.label === 'Motor rated power (dashed)')).toMatchObject({
			data: [
				{ x: 0, y: 5.5 },
				{ x: 30, y: 5.5 }
			]
		});
		// The plugin's marks are named on their legend entries, so a click there hides them.
		expect(sets.flatMap((d) => (d as { checkMark?: string }).checkMark ?? [])).toEqual([
			'preferred',
			'allowable',
			'minimum'
		]);
		expect(config(true).plugins?.map((p) => p.id)).toContain('checkMarks');
	});

	it('draws none of them when hidden, nor on panels not shown', () => {
		expect(
			labels(false).some((l) => /operating region|required by|Motor|Minimum flow/.test(l ?? ''))
		).toBe(false);
		const headOnly = pumpChartConfig(data, [], {
			speedText: '100 % speed',
			legendLabels: () => [],
			format: String,
			checks: true
		}).data.datasets.map((d) => d.label);
		expect(headOnly).toContain('Preferred operating region (POR)');
		expect(headOnly).not.toContain('NPSHa required by the check (dotted)');
		expect(headOnly).not.toContain('Motor rated power (dashed)');
	});

	it('tells each limit in a note, with its values and source, only when shown', () => {
		const notes = (checksShown: boolean, shown: PanelKey[] = ['head', 'power', 'npsh']) =>
			chartNotes({ data, result: fullPump(), system: undefined, shown, checksShown }).checks;
		expect(notes(false)).toEqual([]);
		const all = notes(true);
		expect(all[0]).toBe(
			'Shaded blue (POR): the preferred operating region, 70 % to 120 % of the best efficiency flow at this speed (8.4 to 14.4 L/s; your values).'
		);
		expect(all[1]).toMatch(
			/^Shaded grey \(AOR\): .* 4 to 25 L\/s at this speed \(4 to 25 L\/s at rated speed/
		);
		expect(all[2]).toBe(
			"Dash-dot line: the minimum continuous stable flow, 3 L/s at this speed (3 L/s at rated speed), the larger of the curve's minimum flows."
		);
		expect(all[3]).toBe(
			'Dotted on the NPSH panel: the NPSHa the NPSH margin check requires, NPSHr + 1 m (your values).'
		);
		expect(all[4]).toBe(
			"Dashed on the power panel: the motor's rated power, 5.5 kW (manufacturer data; no service-factor margin)."
		);
		expect(all.at(-1)).toMatch(/^These are the limits of the design checks you turned on/);
		const headOnly = notes(true, ['head']);
		expect(headOnly.some((n) => n.startsWith('Dotted') || n.startsWith('Dashed'))).toBe(false);
	});

	it('gives each panel its own unit in the tooltip', () => {
		const label = config(true).options?.plugins?.tooltip as {
			callbacks: { label: (item: unknown) => string };
		};
		const item = (dataset: object, y: number) => ({ dataset, raw: { x: 10, y } });
		expect(
			label.callbacks.label(item({ label: 'Motor rated power (dashed)', yAxisID: 'yPower' }, 5.5))
		).toBe('Motor rated power (dashed): 10 L/s, 5.5 kW');
		expect(label.callbacks.label(item({ label: 'Efficiency', yAxisID: 'yEfficiency' }, 70))).toBe(
			'Efficiency: 10 L/s, 70 %'
		);
		expect(label.callbacks.label(item({ label: 'NPSHr', yAxisID: 'yNpsh' }, 2))).toBe(
			'NPSHr: 10 L/s, 2 m'
		);
		expect(label.callbacks.label(item({ label: 'System curve', yAxisID: 'y' }, 12))).toBe(
			'System curve: 10 L/s, 12 m'
		);
	});

	it('claims limits only where one is drawn with the panels shown', () => {
		const npshOnly = pumpChartData(fullPump(), SI_UNITS, null, null, null, {
			...everything,
			checks: { npshMargin: { minimumMargin: 1, source: { kind: 'user' } } }
		});
		expect(checksDrawn(npshOnly, ['head', 'npsh'])).toBe(true);
		expect(checksDrawn(npshOnly, ['head'])).toBe(false);
		const notes = chartNotes({
			data: npshOnly,
			result: fullPump(),
			system: undefined,
			shown: ['head'],
			checksShown: true
		}).checks;
		expect(notes).toEqual([]); // not even the closing sentence
		// A motor rating with no shaft-power curve has no panel to be drawn on.
		const region = { operatingRegion: { source: { kind: 'user' as const } } };
		const noPower = pumpChartData(fullPump({ powerCurve: null }), SI_UNITS, null, null, null, {
			...everything,
			checks: region
		});
		expect(noPower.checks?.motorRating).toBeNull();
		const ratingOnly = pumpChartData(fullPump({ powerCurve: null }), SI_UNITS, null, null, null, {
			...everything,
			checks: region,
			curve: {
				...everything.curve!,
				allowableOperatingRegion: null,
				minimumContinuousStableFlow: null
			}
		});
		expect(ratingOnly.checks).toBeNull();
	});

	it('has no limits without checks, and a chip to hide them', () => {
		expect(pumpChartData(fullPump(), SI_UNITS).checks).toBeNull();
		expect(data.checks).not.toBeNull();
	});
});
