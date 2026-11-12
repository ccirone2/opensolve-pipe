/**
 * The pump chart's configuration (proposal export.md §3.4): the screen's chart and the image's
 * fixed-size render draw the same datasets; the image has no animation, events or tooltip, is
 * drawn at 2× and has larger fonts; other cases are slate with their markers. Pump results are
 * made-up test inputs.
 */
import { describe, expect, it } from 'vitest';
import { pumpResult, systemCurveResponse } from '../testing/results';
import { otherCasesData, pumpChartData } from './pump-chart';
import { CHART_COLORS, pumpChartConfig, pumpGroupConfig } from './pump-chart-config';
import { GROUP_SLOTS, groupChartData, type GroupMemberInput } from './pump-group-chart';
import { formatNumber, SI_UNITS } from './units';

describe('pump chart configuration', () => {
	const legendLabels = () => [];
	const format = (v: number) => formatNumber(v, 4);
	const labelsOf = (config: ReturnType<typeof pumpChartConfig>) =>
		config.data.datasets.map((d) => d.label);

	it('draws the screen chart responsive, with tooltips, and the image at a fixed size', () => {
		const data = pumpChartData(pumpResult(), SI_UNITS, [0, 0.03], systemCurveResponse());
		const screen = pumpChartConfig(data, [], { speedText: '100 % speed', legendLabels, format });
		expect(labelsOf(screen)).toEqual([
			'Pump curve at 100 % speed',
			'System curve',
			'Operating point',
			'Shutoff head'
		]);
		expect(screen.options?.responsive).toBe(true);
		expect(screen.options?.animation).toBe(false);
		expect(screen.options?.devicePixelRatio).toBeUndefined();
		expect(screen.options?.plugins?.tooltip).not.toHaveProperty('enabled');

		const image = pumpChartConfig(data, [], {
			speedText: '100 % speed',
			legendLabels,
			format,
			forImage: true
		});
		// The same datasets, drawn once at 2× without events, animation or tooltip.
		expect(image.data).toEqual(screen.data);
		expect(image.options).toMatchObject({
			responsive: false,
			maintainAspectRatio: false,
			animation: false,
			devicePixelRatio: 2,
			events: [],
			plugins: { tooltip: { enabled: false }, legend: { labels: { font: { size: 14 } } } },
			scales: {
				x: { title: { text: 'Flow (L/s)', font: { size: 15 } }, ticks: { font: { size: 14 } } },
				y: { title: { text: 'Head (m)', font: { size: 15 } }, ticks: { font: { size: 14 } } }
			}
		});
	});

	it('draws the other cases in slate with their markers', () => {
		const data = pumpChartData(pumpResult(), SI_UNITS, [0, 0.03]);
		const others = otherCasesData(
			[
				{
					key: 'S1',
					name: 'Winter',
					result: pumpResult({ speed: 0.9, operatingFlow: 0.015, operatingHead: 20 }),
					stale: true,
					system: null
				}
			],
			SI_UNITS,
			[0, 0.03],
			1
		);
		const config = pumpChartConfig(data, others, {
			speedText: '100 % speed',
			legendLabels,
			format
		});
		const winter = config.data.datasets.find((d) => d.label === 'Winter (out of date)');
		expect(winter).toMatchObject({
			borderColor: CHART_COLORS.slate,
			pointStyle: 'triangle',
			showLine: false
		});
		expect(labelsOf(config)).toContain('Pump curve at 90 % speed (Winter, out of date)');
	});

	it('draws ▽ as Chart.js’s triangle turned over, the other markers unturned (pumps-results-layout.md §6.2 S8)', () => {
		const data = pumpChartData(pumpResult(), SI_UNITS, [0, 0.03]);
		const cases = ['S1', 'S2', 'S3', 'S4', 'S5'].map((key) => ({
			key,
			name: `Case ${key}`,
			result: pumpResult(),
			stale: false,
			system: null
		}));
		const config = pumpChartConfig(data, otherCasesData(cases, SI_UNITS, [0, 0.03], 1), {
			speedText: '100 % speed',
			legendLabels,
			format
		});
		const point = (label: string) => config.data.datasets.find((d) => d.label === label);
		expect(['Case S1', 'Case S2', 'Case S3', 'Case S4', 'Case S5'].map(point)).toMatchObject([
			{ pointStyle: 'triangle', pointRotation: 0 },
			{ pointStyle: 'rect', pointRotation: 0 },
			{ pointStyle: 'star', pointRotation: 0 },
			{ pointStyle: 'crossRot', pointRotation: 0 },
			{ pointStyle: 'triangle', pointRotation: 180 }
		]);
	});
});

describe('the group chart’s member marks (owner, 2026-11-12, nit 5; docs/proposals/pumps-nits.md item 5)', () => {
	/**
	 * The point styles Chart.js 4.5.1 draws as open paths, stroked only: its drawPoint moves and
	 * draws lines for `cross`, `crossRot`, `star`, `line` and `dash`, and its fill() then fills no
	 * area (node_modules/chart.js/dist/chunks/helpers.dataset.js, drawPointLegend). Such a mark is
	 * its border alone, on the chart and in the image's legend.
	 */
	const STROKE_ONLY = new Set(['cross', 'crossRot', 'star', 'line', 'dash']);

	it('strokes every stroke-only member mark in its slot’s colour, 3 px or more: none is drawn white, as slot 3’s star was', () => {
		// A member in each of the six slots, running.
		const members: GroupMemberInput[] = GROUP_SLOTS.map((_, slot) => ({
			id: `P${slot + 1}`,
			name: `Pump P${slot + 1}`,
			result: pumpResult({ operatingFlow: 0.005 * (slot + 1) }),
			ratedRange: [0, 0.03],
			curveId: null,
			slot,
			flags: []
		}));
		const data = groupChartData(members, SI_UNITS, null);
		const config = pumpGroupConfig(data, {
			legendLabels: () => [],
			format: (v: number) => formatNumber(v, 4)
		});
		// Each member's point: a dataset of one point, no line, naming its member.
		type Mark = (typeof config.data.datasets)[number] & { memberIds?: string[] };
		const marks = (config.data.datasets as Mark[]).filter(
			(d) => d.showLine === false && d.memberIds?.length === 1
		);
		expect(marks.map((d) => d.memberIds![0])).toEqual(['P1', 'P2', 'P3', 'P4', 'P5', 'P6']);
		const stroked = marks.filter((d) => STROKE_ONLY.has(d.pointStyle as string));
		// The slots whose marker is stroke-only, as GROUP_SLOTS gives them (★, × and + today).
		expect(stroked.map((d) => d.pointStyle)).toEqual(
			GROUP_SLOTS.map((s) => s.marker).filter((m) => STROKE_ONLY.has(m))
		);
		expect(stroked.length).toBeGreaterThan(0);
		for (const mark of stroked) {
			const slot = GROUP_SLOTS[marks.indexOf(mark)]!;
			expect(mark.borderColor, `${mark.label}'s ${String(mark.pointStyle)}`).toBe(slot.color);
			expect(mark.borderWidth, `${mark.label}'s ${String(mark.pointStyle)}`).toBeGreaterThanOrEqual(
				3
			);
		}
	});
});
