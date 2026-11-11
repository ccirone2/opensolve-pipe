/**
 * The pump chart's configuration (proposal export.md §3.4): the screen's chart and the image's
 * fixed-size render draw the same datasets; the image has no animation, events or tooltip, is
 * drawn at 2× and has larger fonts; other cases are slate with their markers. Pump results are
 * made-up test inputs.
 */
import { describe, expect, it } from 'vitest';
import { pumpResult, systemCurveResponse } from '../testing/results';
import { otherCasesData, pumpChartData } from './pump-chart';
import { CHART_COLORS, pumpChartConfig } from './pump-chart-config';
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
