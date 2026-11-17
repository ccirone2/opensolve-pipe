/**
 * One mark spec for the canvas and the page's swatches (owner, 2026-11-12, nit 5; Q1 "Shapes go
 * too"; docs/proposals/pumps-nits.md item 5, rule 8; slice 5c): chart-marks.ts holds each mark's
 * radius, border, fill and stroke, and a `surface` token in place of the '#ffffff' literals; both
 * charts draw from it, and the HTML legend's ink dot and slate ring are drawn from it too
 * (components/results/PumpGroupFigure.svelte.test.ts holds the swatches equal). The dark theme's
 * steps (slate-400 rings, a light disc, a halo set to the plot's background) are recorded for a
 * future theme, with no code.
 */
import { describe, expect, it } from 'vitest';
import { lineupView } from '../testing/curve-family';
import { pumpResult } from '../testing/results';
import { CHART_MARKS, memberMark, SURFACE } from './chart-marks';
import { otherCasesData, pumpChartData } from './pump-chart';
import { CHART_COLORS, pumpChartConfig, pumpGroupConfig } from './pump-chart-config';
import { GROUP_AQUA, GROUP_BLUE } from './pump-group-chart';
import { formatNumber, SI_UNITS } from './units';

const options = { legendLabels: () => [], format: (v: number) => formatNumber(v, 4) };
type Dataset = Record<string, unknown> & {
	label?: string;
	caseLabel?: string;
	memberIds?: string[];
	showLine?: boolean;
	otherCase?: boolean;
};

describe('the mark spec (rule 8)', () => {
	it('holds the Group’s ink dot, another case’s slate ring and a member’s dot, the surface white', () => {
		// The plot's background on the light theme: the edge a dot is drawn with, the fill of a
		// hollow mark.
		expect(SURFACE).toBe('#ffffff');
		// Rule 3: the Group point stays the ink dot, r 7, with its 2 px surface edge.
		expect(CHART_MARKS.group).toEqual({
			radius: 7,
			border: 2,
			fill: CHART_COLORS.ink,
			stroke: SURFACE
		});
		// Rule 4: every other case a slate ring, r 10, 2 px, transparent inside.
		expect(CHART_MARKS.ring).toEqual({
			radius: 10,
			border: 2,
			fill: 'transparent',
			stroke: CHART_COLORS.slate
		});
		// Rule 2: a member's dot r 6 with a 2 px surface edge, filled with its line's colour.
		expect(CHART_MARKS.member).toMatchObject({ radius: 6, border: 2, stroke: SURFACE });
		// Rule 5: a pump held at zero flow, the hollow diamond r 7, 2 px, in ink on the pump chart.
		expect(CHART_MARKS.held).toEqual({
			radius: 7,
			border: 2,
			fill: SURFACE,
			stroke: CHART_COLORS.ink
		});
	});

	it('gives a member its line’s colour: the dot filled with it, the held diamond stroked with it', () => {
		expect(memberMark(GROUP_AQUA)).toEqual({
			radius: 6,
			border: 2,
			fill: GROUP_AQUA,
			stroke: SURFACE
		});
		expect(memberMark(GROUP_BLUE, true)).toEqual({
			radius: 7,
			border: 2,
			fill: SURFACE,
			stroke: GROUP_BLUE
		});
	});

	it('is what the group chart draws: the Group dot, the rings and the members’ dots', () => {
		const config = pumpGroupConfig(lineupView('').data, options);
		const sets = config.data.datasets as unknown as Dataset[];
		const look = (d: Dataset) => ({
			radius: d.pointRadius,
			border: d.borderWidth,
			fill: d.backgroundColor,
			stroke: d.borderColor
		});
		const group = sets.filter((d) => /^Group( \(crossing\))?$/.test(d.caseLabel ?? ''));
		expect(group).toHaveLength(1);
		expect(look(group[0]!)).toEqual(CHART_MARKS.group);
		const rings = sets.filter((d) => d.otherCase);
		expect(rings.length).toBeGreaterThan(0);
		for (const ring of rings) expect(look(ring), ring.label).toEqual(CHART_MARKS.ring);
		const members = sets.filter((d) => d.showLine === false && d.memberIds?.length === 1);
		expect(members).toHaveLength(4);
		for (const m of members)
			expect(look(m), m.label).toMatchObject({
				radius: CHART_MARKS.member.radius,
				border: CHART_MARKS.member.border,
				stroke: CHART_MARKS.member.stroke
			});
	});

	it('is what the pump chart draws for another case: the same slate ring', () => {
		const data = pumpChartData(pumpResult(), SI_UNITS, [0, 0.03]);
		const others = otherCasesData(
			[
				{
					key: 'S1',
					name: 'Winter',
					result: pumpResult({ operatingFlow: 0.015, operatingHead: 20 }),
					stale: false,
					system: null
				}
			],
			SI_UNITS,
			[0, 0.03],
			1,
			null,
			{ S1: 1 }
		);
		const config = pumpChartConfig(data, others, { ...options, speedText: '100 % speed' });
		const rings = (config.data.datasets as unknown as Dataset[]).filter((d) => d.otherCase);
		expect(rings).toHaveLength(1);
		expect({
			radius: rings[0]!.pointRadius,
			border: rings[0]!.borderWidth,
			fill: rings[0]!.backgroundColor,
			stroke: rings[0]!.borderColor
		}).toEqual(CHART_MARKS.ring);
	});

	it('leaves no white literal in the charts’ configuration: the surface token stands for it', () => {
		const sources = import.meta.glob<string>('./pump-chart-config.ts', {
			query: '?raw',
			import: 'default',
			eager: true
		});
		const source = sources['./pump-chart-config.ts']!;
		expect(source.length).toBeGreaterThan(1000);
		expect(source.match(/['"]#(?:fff|ffffff)['"]/gi) ?? []).toEqual([]);
	});
});
