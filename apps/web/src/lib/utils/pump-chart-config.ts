/**
 * The pump chart's Chart.js configuration (proposal export.md §3.4): the one the screen draws and
 * the image draws again at a fixed size, so the image cannot drift from the chart shown. In the
 * chart's chunk (components/results/chart-setup.ts re-exports it), loaded before any chart is
 * drawn: it is code only the chart needs, so the page does not carry it, and it imports nothing
 * of the page at run time (the tooltip's number format and the legend's labels are passed in), so
 * the bundler keeps the page's modules where they are.
 */
import type { Chart as ChartInstance, ChartConfiguration, LegendItem, Plugin } from 'chart.js';
import type { ChartPoint, OtherCaseData, PanelKey, PumpChartData } from './pump-chart';
import type { GroupChartData } from './pump-group-chart';

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
	legend: '#1e293b',
	/** Where the head rises with flow: amber-700, 5.0:1 on white (a fact, not a flag colour). */
	rising: '#b45309',
	/**
	 * The design checks' regions (D19), light tints under the curves: the preferred region in the
	 * pump's blue, the allowable region in slate; their edges and labels in the slate ink.
	 */
	preferredFill: 'rgba(42, 120, 214, 0.13)',
	allowableFill: 'rgba(71, 85, 105, 0.08)'
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
	/** The panels shown, top to bottom (the head panel always; default: the head only). */
	panels?: readonly PanelKey[];
	/** The flow the readout reads (display unit), drawn as a vertical line; null: none. */
	cursor?: () => number | null;
	/** A speed-controlled pump's speed range (limit curves, iso-efficiency lines) is shown. */
	speedRange?: boolean;
	/** The design checks' limits (D19) are shown. */
	checks?: boolean;
}

/** Each panel's y-axis id and share of the height (proposal pump-chart.md §4.1). */
const PANEL_AXES: Readonly<Record<PanelKey, { id: string; weight: number }>> = {
	head: { id: 'y', weight: 3 },
	efficiency: { id: 'yEfficiency', weight: 1 },
	power: { id: 'yPower', weight: 1 },
	npsh: { id: 'yNpsh', weight: 1.3 }
};

/** Legend markers: curves as a line (dashed where dashed), points as their marker. */
function legendStyle(dataset: {
	label?: string;
	showLine?: boolean;
	pointStyle?: unknown;
	legendBox?: boolean;
}) {
	if (dataset.legendBox) return 'rect';
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
 * The curve facts on the head and efficiency panels (proposal pump-chart.md §6, slice 2): where
 * the head rises with flow (amber, under the pump curve), the shutoff head (a dash at zero flow,
 * hollow when extrapolated), the best efficiency point (a cross, labelled "BEP"), and for a
 * speed-controlled pump with its speed range shown, its curves at the limit speeds (thin) and the
 * iso-efficiency lines (dotted, labelled at the maximum speed).
 */
function factDatasets(d: PumpChartData, shown: (key: PanelKey) => boolean, speedRange: boolean) {
	const { pump: PUMP, ink: INK, slate: SLATE, rising: RISING } = CHART_COLORS;
	const { bep, shutoff, rising, speedRange: range } = d.facts;
	const marker = (label: string, point: ChartPoint, yAxisID: string, style: 'cross' | 'dash') => ({
		label,
		data: [point],
		yAxisID,
		borderColor: INK,
		backgroundColor: INK,
		borderWidth: 3,
		pointStyle: style,
		pointRadius: 8,
		pointHoverRadius: 10,
		pointHitRadius: 10,
		showLine: false
	});
	const thin = (label: string, data: ChartPoint[], extra: object = {}) => ({
		label,
		data,
		yAxisID: 'y',
		borderColor: PUMP,
		backgroundColor: PUMP,
		borderWidth: 1,
		pointRadius: 0,
		pointHitRadius: 4,
		...extra
	});
	return [
		...rising.lines.map((line, i) => ({
			label: 'Head rises with flow',
			data: line,
			yAxisID: 'y',
			borderColor: RISING,
			backgroundColor: RISING,
			borderWidth: 6,
			pointRadius: 0,
			pointHitRadius: 4,
			// Drawn under the pump curve (a higher order is drawn first).
			order: 1,
			...(i ? { duty: true } : {})
		})),
		{
			...marker('Shutoff head', shutoff.point, 'y', 'dash'),
			...(shutoff.extrapolated ? { borderColor: SLATE } : {})
		},
		...(bep
			? [
					{ ...marker('Best efficiency point', bep.head, 'y', 'cross'), pointLabel: 'BEP' },
					...(shown('efficiency') && d.efficiency
						? [
								{
									...marker('Best efficiency point', bep.efficiency, 'yEfficiency', 'cross'),
									duty: true
								}
							]
						: [])
				]
			: []),
		...(speedRange && range
			? [
					thin(`Pump curve at ${trim(range.min.speed)} % speed (minimum)`, range.min.curve),
					thin(`Pump curve at ${trim(range.max.speed)} % speed (maximum)`, range.max.curve, {
						borderDash: [8, 3]
					}),
					...range.iso.map((line, i) => ({
						label: 'Constant efficiency (dotted)',
						data: line.points,
						yAxisID: 'y',
						borderColor: SLATE,
						backgroundColor: SLATE,
						borderWidth: 1,
						borderDash: [1, 3],
						pointRadius: 0,
						pointHitRadius: 4,
						pointLabel: line.best ? 'BEP line' : `${trim(line.efficiency)} %`,
						labelAt: -1,
						...(i ? { duty: true } : {})
					}))
				]
			: [])
	];
}

/**
 * The design checks' limits as datasets (D19): legend entries for the regions (drawn by the
 * checkMarks plugin, under the curves), the NPSHa the NPSH margin check requires (dotted, on the
 * NPSH panel) and the motor's rated power (dashed, across the power panel). As datasets, the
 * panels' axes reach them.
 */
function checkDatasets(d: PumpChartData, shown: (key: PanelKey) => boolean) {
	const c = d.checks;
	if (!c) return [];
	const { ink: INK, slate: SLATE, preferredFill, allowableFill } = CHART_COLORS;
	// The regions and the minimum flow are drawn by the checkMarks plugin; these entries carry
	// `checkMark`, so a click on one in the legend hides what it names.
	const box = (label: string, fill: string, checkMark: CheckMark) => ({
		label,
		data: [],
		yAxisID: 'y',
		borderColor: SLATE,
		backgroundColor: fill,
		borderWidth: 1,
		legendBox: true,
		checkMark
	});
	const n = shown('npsh') && d.npsh ? c.npshRequired : null;
	const power = shown('power') ? d.power : null;
	const xs = power?.curve.map((p) => p.x) ?? [];
	return [
		...(c.preferred ? [box('Preferred operating region (POR)', preferredFill, 'preferred')] : []),
		...(c.allowable ? [box('Allowable operating region (AOR)', allowableFill, 'allowable')] : []),
		...(c.minimumFlow
			? [
					{
						label: 'Minimum flow (dash-dot)',
						data: [],
						yAxisID: 'y',
						borderColor: SLATE,
						backgroundColor: SLATE,
						borderWidth: 1.5,
						borderDash: [8, 3, 2, 3],
						checkMark: 'minimum' as const
					}
				]
			: []),
		...(n
			? [
					{
						label: 'NPSHa required by the check (dotted)',
						data: n.line,
						yAxisID: 'yNpsh',
						borderColor: INK,
						backgroundColor: INK,
						borderWidth: 1.5,
						borderDash: [2, 2],
						pointRadius: 0,
						pointHitRadius: 4
					}
				]
			: []),
		...(c.motorRating !== null && power && xs.length
			? [
					{
						label: 'Motor rated power (dashed)',
						// Its end is set to the largest flow of the datasets drawn (spanDrawnFlows),
						// so the duty it is checked at, at any flow shown, is under it.
						data: [
							{ x: Math.min(0, ...xs), y: c.motorRating },
							{ x: Math.max(...xs), y: c.motorRating }
						],
						spanDrawnFlows: true,
						yAxisID: 'yPower',
						borderColor: INK,
						backgroundColor: INK,
						borderWidth: 1.5,
						borderDash: [6, 3],
						pointRadius: 0,
						pointHitRadius: 4
					}
				]
			: [])
	];
}

/** The marks the checkMarks plugin draws, named on their legend entries. */
type CheckMark = 'preferred' | 'allowable' | 'minimum';

/**
 * A line across the flows drawn (the motor's rating): its last point is moved to the largest
 * flow any other dataset reaches with a value (a point without a head is not drawn, and a
 * curve with none is not a dataset), the other cases and the speed range included.
 */
function spanDrawnFlows(datasets: readonly { data: ChartDatum[]; spanDrawnFlows?: boolean }[]) {
	const xs = datasets
		.filter((ds) => !ds.spanDrawnFlows)
		.flatMap((ds) => ds.data.filter((p) => p.y !== null).map((p) => p.x));
	for (const ds of datasets) {
		const last = ds.spanDrawnFlows ? ds.data[ds.data.length - 1] : undefined;
		if (last) last.x = Math.max(last.x, ...xs);
	}
}

/** A percentage written briefly ("70", "62.5"). */
function trim(value: number): string {
	return String(Number(value.toFixed(1)));
}

/**
 * The panels below the head (proposal pump-chart.md §4.2), for those shown: efficiency and shaft
 * power in the pump's colour (they are the pump's curves), NPSHr in the pump's colour and NPSHa
 * in the system's (it is the system's), each duty value in the operating point's ink; a duty
 * held at the efficiency curve's end value is hollow.
 */
function lowerDatasets(d: PumpChartData, shown: (key: PanelKey) => boolean) {
	const { pump: PUMP, system: SYSTEM, ink: INK } = CHART_COLORS;
	const line = (label: string, data: ChartDatum[], yAxisID: string, color: string) => ({
		label,
		data,
		yAxisID,
		borderColor: color,
		backgroundColor: color,
		borderWidth: 2,
		pointRadius: 0,
		pointHitRadius: 6,
		spanGaps: false
	});
	const dot = (label: string, point: ChartPoint, yAxisID: string, hollow = false) => ({
		label,
		data: [point],
		yAxisID,
		borderColor: hollow ? INK : '#ffffff',
		backgroundColor: hollow ? '#ffffff' : INK,
		borderWidth: 2,
		pointRadius: 5,
		pointHoverRadius: 7,
		pointHitRadius: 10,
		showLine: false,
		duty: true
	});
	const e = shown('efficiency') ? d.efficiency : null;
	const p = shown('power') ? d.power : null;
	const n = shown('npsh') ? d.npsh : null;
	return [
		...(e ? [line('Efficiency', e.curve, 'yEfficiency', PUMP)] : []),
		...(e?.duty ? [dot('Efficiency at the duty', e.duty, 'yEfficiency', e.held)] : []),
		...(p ? [line('Shaft power', p.curve, 'yPower', PUMP)] : []),
		...(p?.duty ? [dot('Shaft power at the duty', p.duty, 'yPower')] : []),
		...(n?.required ? [{ ...line('NPSHr', n.required, 'yNpsh', PUMP), borderDash: [8, 3] }] : []),
		...(n?.available ? [line('NPSHa', n.available, 'yNpsh', SYSTEM)] : []),
		...(n?.requiredAt ? [dot('NPSHr at the duty', n.requiredAt, 'yNpsh', true)] : []),
		...(n?.availableAt ? [dot('NPSHa at the duty', n.availableAt, 'yNpsh')] : [])
	];
}

/**
 * The chart of one pump: its curve at the operating speed (dashed where extrapolated), the
 * system curve, the operating point or the zero-flow point, and the other cases (slate, with
 * their markers and direct labels), from the data of pumpChartData() and otherCasesData().
 */
export function pumpChartConfig(
	d: PumpChartData,
	cases: readonly OtherCaseData[],
	{
		speedText,
		legendLabels,
		format,
		forImage = false,
		panels = ['head'],
		cursor,
		speedRange = false,
		checks = false
	}: PumpChartConfigOptions
): PumpChartConfig {
	const shown = (key: PanelKey) => panels.includes(key);
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
			yAxisID: 'y',
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
						yAxisID: 'y',
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
						yAxisID: 'y',
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
						yAxisID: 'y',
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
						yAxisID: 'y',
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
		...factDatasets(d, shown, speedRange),
		...lowerDatasets(d, shown),
		...(checks ? checkDatasets(d, shown) : []),
		...cases.flatMap((c) => [
			...(c.curve
				? [
						{
							label: c.curveLabel,
							yAxisID: 'y',
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
							yAxisID: 'y',
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
							yAxisID: 'y',
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
	spanDrawnFlows(datasets);
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
			// Short labels at one point of a line or marker ("BEP", "70 %"), in dataset order; a
			// label that would overlap one already drawn is left out (the legend and notes name it).
			const size = forImage ? 13 : 11;
			ctx.font = `${size}px system-ui, sans-serif`;
			const taken: { x: number; y: number; w: number; h: number }[] = [];
			chart.data.datasets.forEach((dataset, i) => {
				const { pointLabel, labelAt } = dataset as { pointLabel?: string; labelAt?: number };
				const points = chart.getDatasetMeta(i).data;
				const point = points[labelAt === -1 ? points.length - 1 : (labelAt ?? 0)];
				if (!pointLabel || !point || !chart.isDatasetVisible(i)) return;
				const box = {
					x: point.x + 6,
					y: point.y - 6 - size,
					w: ctx.measureText(pointLabel).width,
					h: size
				};
				const overlaps = taken.some(
					(o) =>
						box.x < o.x + o.w + 2 &&
						o.x < box.x + box.w + 2 &&
						box.y < o.y + o.h &&
						o.y < box.y + box.h
				);
				if (overlaps) return;
				taken.push(box);
				ctx.fillText(pointLabel, point.x + 6, point.y - 6);
			});
			ctx.restore();
		}
	};
	// A vertical line at the duty through every panel, and the readout's flow (dashed).
	const lines: Plugin<'line'> = {
		id: 'flowLines',
		afterDatasetsDraw(chart) {
			const { ctx, chartArea, scales } = chart;
			const scale = scales.x;
			if (!scale) return;
			const draw = (flow: number, color: string, dash: number[]) => {
				const px = scale.getPixelForValue(flow);
				if (px < chartArea.left || px > chartArea.right) return;
				ctx.save();
				ctx.strokeStyle = color;
				ctx.lineWidth = 1;
				ctx.setLineDash(dash);
				ctx.beginPath();
				ctx.moveTo(px, chartArea.top);
				ctx.lineTo(px, chartArea.bottom);
				ctx.stroke();
				ctx.restore();
			};
			if (d.operating && panels.length > 1) draw(d.operating.x, INK, [2, 3]);
			const at = cursor?.();
			if (at !== null && at !== undefined) draw(at, SLATE, [4, 3]);
		}
	};
	// The design checks' regions under the curves on the head panel, and the minimum flow
	// through every panel (D19), each labelled at its top; outside the axis, only the notes
	// tell them.
	const checkMarks: Plugin<'line'> = {
		id: 'checkMarks',
		beforeDatasetsDraw(chart) {
			const c = d.checks;
			const { ctx, chartArea, scales } = chart;
			const xScale = scales.x;
			const head = scales.y;
			if (!checks || !c || !xScale || !head) return;
			// A mark whose legend entry was clicked off is not drawn.
			const shown = (mark: CheckMark) => {
				const i = chart.data.datasets.findIndex(
					(ds) => (ds as { checkMark?: CheckMark }).checkMark === mark
				);
				return i < 0 || chart.isDatasetVisible(i);
			};
			const size = forImage ? 13 : 11;
			const clamp = (px: number) => Math.min(Math.max(px, chartArea.left), chartArea.right);
			const band = (
				from: number | null,
				to: number | null,
				fill: string,
				label: string,
				labelAt: 'top' | 'bottom'
			) => {
				const left = clamp(from === null ? chartArea.left : xScale.getPixelForValue(from));
				const right = clamp(to === null ? chartArea.right : xScale.getPixelForValue(to));
				if (right - left < 1) return;
				ctx.save();
				ctx.fillStyle = fill;
				ctx.fillRect(left, head.top, right - left, head.bottom - head.top);
				ctx.strokeStyle = CHART_COLORS.slate;
				ctx.lineWidth = 1;
				ctx.setLineDash([3, 3]);
				for (const [value, px] of [
					[from, left],
					[to, right]
				] as const) {
					if (value === null || px <= chartArea.left || px >= chartArea.right) continue;
					ctx.beginPath();
					ctx.moveTo(px, head.top);
					ctx.lineTo(px, head.bottom);
					ctx.stroke();
				}
				ctx.fillStyle = CHART_COLORS.slate;
				ctx.font = `${size}px system-ui, sans-serif`;
				if (right - left > ctx.measureText(label).width + 8)
					ctx.fillText(label, left + 4, labelAt === 'top' ? head.top + size + 3 : head.bottom - 4);
				ctx.restore();
			};
			if (c.allowable && shown('allowable'))
				band(c.allowable.from, c.allowable.to, CHART_COLORS.allowableFill, 'AOR', 'bottom');
			if (c.preferred && shown('preferred'))
				band(c.preferred.from, c.preferred.to, CHART_COLORS.preferredFill, 'POR', 'top');
			if (c.minimumFlow && shown('minimum')) {
				const px = xScale.getPixelForValue(c.minimumFlow.flow);
				if (px >= chartArea.left && px <= chartArea.right) {
					ctx.save();
					ctx.strokeStyle = CHART_COLORS.slate;
					ctx.lineWidth = 1.5;
					ctx.setLineDash([8, 3, 2, 3]);
					ctx.beginPath();
					ctx.moveTo(px, chartArea.top);
					ctx.lineTo(px, chartArea.bottom);
					ctx.stroke();
					ctx.restore();
				}
			}
		}
	};
	const yScale = (key: PanelKey, title: string) => ({
		type: 'linear' as const,
		beginAtZero: true,
		title: { display: true, text: title, color: TEXT, ...font(15) },
		grid: { color: GRID },
		ticks: { color: TEXT, ...(key === 'head' ? {} : { maxTicksLimit: 4 }), ...font(14) },
		...(panels.length > 1
			? { stack: 'panels', stackWeight: PANEL_AXES[key].weight, offset: true }
			: {})
	});
	// Chart.js stacks axes in the order given from the bottom up: the head panel goes last.
	const lowerScales = [...panels]
		.filter((key) => key !== 'head')
		.reverse()
		.map((key) => [
			PANEL_AXES[key].id,
			yScale(
				key,
				key === 'efficiency'
					? 'η (%)'
					: key === 'power'
						? `P (${d.powerUnit})`
						: `NPSH (${d.headUnit})`
			)
		]);
	return {
		type: 'line',
		plugins: [checkMarks, caseLabels, lines],
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
				...Object.fromEntries(lowerScales),
				y: yScale('head', `Head (${d.headUnit})`)
			},
			plugins: {
				legend: {
					position: 'bottom',
					labels: {
						color: CHART_COLORS.legend,
						usePointStyle: true,
						boxHeight: 12,
						// The panels' duty dots repeat the operating point's entry.
						filter: (item, chartData) =>
							!(chartData.datasets[item.datasetIndex ?? -1] as { duty?: boolean } | undefined)
								?.duty,
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
									// Each panel's own unit: % on the efficiency panel, power on the power panel.
									const axis = (item.dataset as { yAxisID?: string }).yAxisID;
									const unit =
										axis === 'yEfficiency' ? '%' : axis === 'yPower' ? d.powerUnit : d.headUnit;
									return `${item.dataset.label}: ${fmt(p.x)} ${d.flowUnit}, ${fmt(p.y)} ${unit}`;
								}
							}
						}
			}
		}
	};
}

// ---------------------------------------------------------------------------------------------
// The Pumps together card (CLAUDE.md D21, proposal pump-groups.md §6.3)
// ---------------------------------------------------------------------------------------------

/** The group curve and the station's point: the primary ink, as the pump chart's duty. */
export const GROUP_CURVE_LABEL = "Group curve (station's flow)";
export const GROUP_BEYOND_LABEL = 'Group curve, a pump beyond its data (dashed)';

export interface PumpGroupConfigOptions {
	/** Chart.js's own legend labels, from the chart chunk (as pumpChartConfig's). */
	legendLabels: (chart: ChartInstance) => LegendItem[];
	/** How the tooltip writes a number. */
	format: (value: number) => string;
	/** The fixed-size render of the image (as pumpChartConfig's). */
	forImage?: boolean;
	/**
	 * The page draws the legend under the canvas (pump-group-chart.ts groupLegend), so the plot
	 * keeps the panel's height on a phone; the image draws Chart.js's own.
	 */
	htmlLegend?: boolean;
}

/**
 * The Pumps together chart, head panel only: each member's curve (its colour and dash, dashed
 * beyond its data) and point (its marker, a held pump the pump chart's diamond, a direct label),
 * the group curve in ink (dashed where a pump runs beyond its data, gaps where a point has no
 * flow) and the station's duty, an ink dot labelled "Group". Nothing else: no combined curve and
 * no member's system curve (proposal §6.3).
 */
export function pumpGroupConfig(
	d: GroupChartData,
	{ legendLabels, format, forImage = false, htmlLegend = false }: PumpGroupConfigOptions
): PumpChartConfig {
	const { ink: INK, grid: GRID, text: TEXT } = CHART_COLORS;
	const fmt = format;
	const font = (size: number) => (forImage ? { font: { size } } : {});
	const crossed = (marker: string) => marker === 'cross' || marker === 'crossRot';
	const datasets = [
		...d.lines.flatMap((line) => [
			{
				label: line.label,
				yAxisID: 'y',
				data: line.curve as ChartDatum[],
				borderColor: line.style.color,
				backgroundColor: line.style.color,
				borderWidth: 2,
				...(line.style.dash.length ? { borderDash: line.style.dash } : {}),
				pointRadius: 0,
				pointHitRadius: 6,
				memberIds: line.ids
			},
			...(line.extrapolated.length
				? [
						{
							label: `${line.label}, beyond its data`,
							yAxisID: 'y',
							data: joinSegments(line.extrapolated),
							borderColor: line.style.color,
							backgroundColor: line.style.color,
							borderWidth: 2,
							borderDash: line.style.beyondDash,
							pointRadius: 0,
							pointHitRadius: 6,
							spanGaps: false,
							// The notes say what dashes are: one legend entry per line.
							legend: false,
							memberIds: line.ids
						}
					]
				: [])
		]),
		...(d.curve?.solid.length
			? [
					{
						label: GROUP_CURVE_LABEL,
						yAxisID: 'y',
						data: joinSegments(d.curve.solid),
						borderColor: INK,
						backgroundColor: INK,
						borderWidth: 2,
						pointRadius: 0,
						pointHitRadius: 6,
						spanGaps: false
					}
				]
			: []),
		...(d.curve?.beyond.length
			? [
					{
						label: GROUP_BEYOND_LABEL,
						yAxisID: 'y',
						data: joinSegments(d.curve.beyond),
						borderColor: INK,
						backgroundColor: INK,
						borderWidth: 2,
						borderDash: [6, 4],
						pointRadius: 0,
						pointHitRadius: 6,
						spanGaps: false
					}
				]
			: []),
		...d.points.map((p) => ({
			label: p.held ? `${p.name}, held at zero flow` : p.name,
			yAxisID: 'y',
			data: [p.point] as ChartDatum[],
			borderColor: p.held || crossed(p.style.marker) ? p.style.color : '#ffffff',
			backgroundColor: p.held ? '#ffffff' : p.style.color,
			borderWidth: p.held || crossed(p.style.marker) ? 3 : 1.5,
			pointStyle: p.held ? ('rectRot' as const) : p.style.marker,
			pointRadius: 8,
			pointHoverRadius: 10,
			pointHitRadius: 12,
			showLine: false,
			caseLabel: p.name,
			memberIds: [p.id]
		})),
		...(d.station
			? [
					{
						label: d.station.onCurve ? 'Group duty, on the curve' : "Group duty (the solve's)",
						yAxisID: 'y',
						data: [d.station.point] as ChartDatum[],
						borderColor: '#ffffff',
						backgroundColor: INK,
						borderWidth: 2,
						pointStyle: 'circle' as const,
						pointRadius: 7,
						pointHoverRadius: 9,
						pointHitRadius: 12,
						showLine: false,
						caseLabel: 'Group'
					}
				]
			: [])
	];
	// Direct labels next to each point: above and below in turn, so close points' labels part.
	const pointLabels: Plugin<'line'> = {
		id: 'groupLabels',
		afterDatasetsDraw(chart) {
			const ctx = chart.ctx;
			ctx.save();
			ctx.fillStyle = INK;
			ctx.font = `${forImage ? 14 : 12}px system-ui, sans-serif`;
			let n = 0;
			chart.data.datasets.forEach((dataset, i) => {
				const label = (dataset as { caseLabel?: string }).caseLabel;
				const point = chart.getDatasetMeta(i).data[0];
				if (!label || !point || !chart.isDatasetVisible(i)) return;
				// To the right of the point, or to its left where the plot ends first.
				const width = ctx.measureText(label).width;
				const x =
					point.x + 10 + width > chart.chartArea.right ? point.x - 10 - width : point.x + 10;
				ctx.fillText(label, x, n++ % 2 === 0 ? point.y - 10 : point.y + 20);
			});
			ctx.restore();
		}
	};
	return {
		type: 'line',
		plugins: [pointLabels],
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
					title: { display: true, text: `Head or rise (${d.headUnit})`, color: TEXT, ...font(15) },
					grid: { color: GRID },
					ticks: { color: TEXT, ...font(14) }
				}
			},
			plugins: {
				legend: {
					display: !htmlLegend,
					position: 'bottom',
					labels: {
						color: CHART_COLORS.legend,
						usePointStyle: true,
						boxHeight: 12,
						filter: (item, chartData) =>
							(chartData.datasets[item.datasetIndex ?? -1] as { legend?: boolean } | undefined)
								?.legend !== false,
						...font(14),
						generateLabels: (c) =>
							legendLabels(c).map((item) => {
								const ds = c.data.datasets[item.datasetIndex ?? -1] as
									{ showLine?: boolean; pointStyle?: unknown } | undefined;
								return {
									...item,
									pointStyle: (ds?.showLine === false && typeof ds.pointStyle === 'string'
										? ds.pointStyle
										: 'line') as 'circle' | 'line'
								};
							})
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
