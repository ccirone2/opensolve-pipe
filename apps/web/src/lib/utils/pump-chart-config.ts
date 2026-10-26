/**
 * The pump chart's Chart.js configuration (proposal export.md §3.4): the one the screen draws and
 * the image draws again at a fixed size, so the image cannot drift from the chart shown. In the
 * chart's chunk (components/results/chart-setup.ts re-exports it), loaded before any chart is
 * drawn: it is code only the chart needs, so the page does not carry it, and it imports nothing
 * of the page at run time (the tooltip's number format and the legend's labels are passed in), so
 * the bundler keeps the page's modules where they are.
 */
import type { Chart as ChartInstance, ChartConfiguration, LegendItem, Plugin } from 'chart.js';
import type { ChartPoint, OtherCaseData, PumpChartData } from './pump-chart';

/**
 * The chart's palette: categorical slots 1 and 2 of the dataviz reference palette (validated
 * light-mode pair) for the pump and system curves, the operating point in the primary ink, and
 * other cases in neutral slate (7.6:1 on white), told apart by marker and label. Identity is also
 * given by the legend, the dash pattern and the point marker, and by the data table.
 */
export const CHART_COLORS = {
	pump: '#2a78d6',
	system: '#eb6834',
	ink: '#0f172a',
	slate: '#475569',
	grid: '#e2e8f0',
	text: '#475569',
	legend: '#1e293b'
} as const;

/** The legend entry of a pump held at zero flow. */
export const HELD_LABEL = 'Held at zero flow';

/** A point of a dataset: a null head is a gap. */
export type ChartDatum = { x: number; y: number | null };

/** The configuration both the screen and the image draw (Chart.js 'line' with linear scales). */
export type PumpChartConfig = ChartConfiguration<'line', ChartDatum[]>;

export interface PumpChartConfigOptions {
	/** "100 % speed", "87.32 % speed (flow control)": the pump curve's label. */
	speedText: string;
	/**
	 * Chart.js's own legend labels (`Chart.defaults.plugins.legend.labels.generateLabels`), from
	 * the chart chunk: passed in, so this module loads no Chart.js code.
	 */
	legendLabels: (chart: ChartInstance) => LegendItem[];
	/** How the tooltip writes a number (units.ts formatNumber to 4 figures, from the page). */
	format: (value: number) => string;
	/**
	 * The fixed-size render of the image (export.md §3.4): not responsive, no animation, events
	 * or tooltip, at 2× pixels, with larger fonts.
	 */
	forImage?: boolean;
}

/** Legend markers: curves as a line (dashed where dashed), points as their marker. */
function legendStyle(dataset: { label?: string; showLine?: boolean; pointStyle?: unknown }) {
	if (dataset.label === 'Operating point') return 'circle';
	if (dataset.label === HELD_LABEL) return 'rectRot';
	return dataset.showLine === false && typeof dataset.pointStyle === 'string'
		? dataset.pointStyle
		: 'line';
}

/** Dashed segments as one dataset, separated by gaps. */
function joinSegments(segments: ChartPoint[][]): ChartDatum[] {
	const points: ChartDatum[] = [];
	segments.forEach((segment, i) => {
		if (i > 0 && segment[0]) points.push({ x: segment[0].x, y: null });
		points.push(...segment);
	});
	return points;
}

/**
 * The chart of one pump: its curve at the operating speed (dashed where extrapolated), the
 * system curve, the operating point or the zero-flow point, and the other cases (slate, with
 * their markers and direct labels), from the data of pumpChartData() and otherCasesData().
 */
export function pumpChartConfig(
	d: PumpChartData,
	cases: readonly OtherCaseData[],
	{ speedText, legendLabels, format, forImage = false }: PumpChartConfigOptions
): PumpChartConfig {
	const {
		pump: PUMP,
		system: SYSTEM,
		ink: INK,
		slate: SLATE,
		grid: GRID,
		text: TEXT
	} = CHART_COLORS;
	const fmt = format;
	const font = (size: number) => (forImage ? { font: { size } } : {});
	const datasets = [
		{
			label: `Pump curve at ${speedText}`,
			data: d.curve,
			borderColor: PUMP,
			backgroundColor: PUMP,
			borderWidth: 2,
			pointRadius: 0,
			pointHitRadius: 6
		},
		...(d.extrapolated.length
			? [
					{
						label: 'Pump curve, extrapolated (dashed)',
						data: joinSegments(d.extrapolated),
						borderColor: PUMP,
						backgroundColor: PUMP,
						borderWidth: 2,
						borderDash: [6, 4],
						pointRadius: 0,
						pointHitRadius: 6,
						spanGaps: false
					}
				]
			: []),
		...(d.system && d.systemMissing < d.system.length
			? [
					{
						label: 'System curve',
						data: d.system,
						borderColor: SYSTEM,
						backgroundColor: SYSTEM,
						borderWidth: 2,
						pointRadius: 0,
						pointHitRadius: 6,
						// A point without a solution is a gap, never bridged.
						spanGaps: false
					}
				]
			: []),
		...(d.operating
			? [
					{
						label: 'Operating point',
						data: [d.operating],
						borderColor: '#ffffff',
						backgroundColor: INK,
						borderWidth: 2,
						pointRadius: 6,
						pointHoverRadius: 8,
						pointHitRadius: 12,
						showLine: false
					}
				]
			: []),
		...(d.held
			? [
					{
						label: HELD_LABEL,
						data: [d.held],
						borderColor: INK,
						backgroundColor: '#ffffff',
						borderWidth: 2,
						pointStyle: 'rectRot' as const,
						pointRadius: 7,
						pointHoverRadius: 9,
						pointHitRadius: 12,
						showLine: false
					}
				]
			: []),
		...cases.flatMap((c) => [
			...(c.curve
				? [
						{
							label: c.curveLabel,
							data: c.curve,
							borderColor: SLATE,
							backgroundColor: SLATE,
							borderWidth: 1,
							pointRadius: 0,
							pointHitRadius: 4
						}
					]
				: []),
			...(c.system && c.system.some((p) => p.y !== null)
				? [
						{
							label: `System curve, ${c.label}`,
							data: c.system,
							borderColor: SLATE,
							backgroundColor: SLATE,
							borderWidth: 1.5,
							borderDash: [2, 3],
							pointRadius: 0,
							pointHitRadius: 4,
							spanGaps: false
						}
					]
				: []),
			...(c.operating || c.held
				? [
						{
							label: c.label,
							caseLabel: c.label,
							data: [(c.operating ?? c.held) as ChartPoint],
							borderColor: SLATE,
							backgroundColor: '#ffffff',
							borderWidth: 2,
							pointStyle: c.marker,
							pointRadius: 7,
							pointHoverRadius: 9,
							pointHitRadius: 12,
							showLine: false
						}
					]
				: [])
		])
	];
	// Direct labels next to the other cases' operating points.
	const caseLabels: Plugin<'line'> = {
		id: 'caseLabels',
		afterDatasetsDraw(chart) {
			const ctx = chart.ctx;
			ctx.save();
			ctx.fillStyle = SLATE;
			ctx.font = `${forImage ? 14 : 12}px system-ui, sans-serif`;
			// Above and below in turn, so the labels of close points do not overlap.
			let n = 0;
			chart.data.datasets.forEach((dataset, i) => {
				const label = (dataset as { caseLabel?: string }).caseLabel;
				const point = chart.getDatasetMeta(i).data[0];
				if (!label || !point || !chart.isDatasetVisible(i)) return;
				ctx.fillText(label, point.x + 9, n++ % 2 === 0 ? point.y - 9 : point.y + 19);
			});
			ctx.restore();
		}
	};
	return {
		type: 'line',
		plugins: [caseLabels],
		data: { datasets },
		options: {
			animation: false,
			responsive: !forImage,
			maintainAspectRatio: false,
			...(forImage ? { devicePixelRatio: 2, events: [] } : {}),
			parsing: false,
			interaction: { mode: 'nearest', intersect: false },
			scales: {
				x: {
					type: 'linear',
					beginAtZero: true,
					title: { display: true, text: `Flow (${d.flowUnit})`, color: TEXT, ...font(15) },
					grid: { color: GRID },
					ticks: { color: TEXT, ...font(14) }
				},
				y: {
					type: 'linear',
					beginAtZero: true,
					title: { display: true, text: `Head (${d.headUnit})`, color: TEXT, ...font(15) },
					grid: { color: GRID },
					ticks: { color: TEXT, ...font(14) }
				}
			},
			plugins: {
				legend: {
					position: 'bottom',
					labels: {
						color: CHART_COLORS.legend,
						usePointStyle: true,
						boxHeight: 12,
						...font(14),
						// Curves as a line (dashed where dashed), the operating point as a dot.
						generateLabels: (c) =>
							legendLabels(c).map((item) => ({
								...item,
								pointStyle: legendStyle(c.data.datasets[item.datasetIndex ?? -1] ?? {}) as
									'circle' | 'line'
							}))
					}
				},
				tooltip: forImage
					? { enabled: false }
					: {
							callbacks: {
								label: (item) => {
									const p = item.raw as ChartDatum;
									if (p.y === null) return '';
									return `${item.dataset.label}: ${fmt(p.x)} ${d.flowUnit}, ${fmt(p.y)} ${d.headUnit}`;
								}
							}
						}
			}
		}
	};
}
