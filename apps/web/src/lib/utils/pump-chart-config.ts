/**
 * The pump chart's Chart.js configuration (proposal export.md §3.4): the one the screen draws and
 * the image draws again at a fixed size, so the image cannot drift from the chart shown. In the
 * chart's chunk (components/results/chart-setup.ts re-exports it), loaded before any chart is
 * drawn: it is code only the chart needs, so the page does not carry it, and it imports nothing
 * of the page at run time (the tooltip's number format and the legend's labels are passed in), so
 * the bundler keeps the page's modules where they are. Its two run-time imports are leaf modules
 * the page shares (nit 5, slice 5c): the marks' spec (chart-marks.ts, which the HTML legend's
 * swatches draw too) and the point labels' placer (point-labels.ts).
 */
import type { Chart as ChartInstance, ChartConfiguration, LegendItem, Plugin } from 'chart.js';
import { CHART_MARKS, memberMark, SURFACE } from './chart-marks';
import {
	leaderCrosses,
	placePointLabels,
	POINT_LABEL_HALO,
	POINT_LABEL_LEADER,
	type NotLabelledPoint,
	type PlacedPointLabel,
	type PointLabelItem
} from './point-labels';
import type { CaseNumber, ChartPoint, OtherCaseData, PanelKey, PumpChartData } from './pump-chart';
import type {
	CurveLabelInput,
	CurveLabelPlacement,
	GroupChartData,
	GroupReadoutMark,
	PlacedCurveLabel,
	PxBox
} from './pump-group-chart';

/**
 * The chart's palette: categorical slots 1 and 2 of the dataviz reference palette (validated
 * light-mode pair) for the pump and system curves, the operating point in the primary ink, and
 * other cases in neutral slate (7.6:1 on white), slate rings told apart by their case numbers
 * (nit 5, slice 5b). Identity is also given by the legend, the dash pattern and the points' labels
 * (placePointLabels: a ring's number, a pump's name, nit 5, slice 5c), and by the data table. The
 * marks themselves are chart-marks.ts's, the HTML legend's swatches' too.
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
	/**
	 * A phone's screen: an other case's ring is labelled by its case number alone on the canvas
	 * (the legend, the list and the data table name it); never in the image (nit 5, rule 4).
	 */
	compactLabels?: boolean;
	/**
	 * Told after every drawing where the rings' labels went and which were left out (nit 5, rule
	 * 7; slice 5c): the notes name those, the canvas keeps the placement (absent: not told).
	 */
	onlabels?: (drawn: PointLabelsDrawn) => void;
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

/**
 * A label's case tag (owner, 2026-11-12, nit 5; docs/proposals/pumps-nits.md item 5, rule 4): a
 * label starting "[…]" ("[2] Winter", "[1, 4] 3 running", "[Base] Base case") shows the case
 * numbers inside the brackets in a small box, then the words after it; a label without one is its
 * words alone. Only for a label whose leading tag the code builds from case numbers (a ring's, an
 * other case's, a curve label's): a user's text alone, such as a pump's name "[2] Standby", is
 * never read for one (review CASE-NUMBERS-A1, B2).
 */
export function labelTag(text: string): { tag: string | null; words: string } {
	const tagged = /^\[([^\]]+)\](?: (.*))?$/s.exec(text);
	return tagged ? { tag: tagged[1]!, words: tagged[2] ?? '' } : { tag: null, words: text };
}

/**
 * Write a label where the label code puts it (left end `x`, baseline `y`, the font of `size` px
 * set): a leading case tag (labelTag) as its numbers in a box exactly as wide as its bracketed text
 * measures, so the label takes the width its text measures and is placed by it, from the font's
 * size above the baseline to a quarter of it below (a text's box: descenders), with a 1 px slate
 * edge (the lists' CaseTag box, drawn), the numbers bold and centred in the legend's ink; then the
 * words after it in the fill colour set. The font, fill and alignment are set back as they were.
 * Called only with labels the code tags (labelTag); a pump's name goes to fillText as typed.
 *
 * Without `halo` the box is not filled, as the curves' labels are drawn (D24 §9.3): they are placed
 * clear of the marks, but a white box hid the mark under a label that fell on one (slice 5b). With
 * `halo`, a point's label (placePointLabels, which keeps it off every mark but its own: nit 5, rule
 * 7; slice 5c), the box is filled with it and the words drawn over a POINT_LABEL_HALO px stroke of
 * it, so the label reads over a curve under it.
 */
export function fillLabel(
	ctx: CanvasRenderingContext2D,
	text: string,
	x: number,
	y: number,
	size: number,
	halo?: string
): void {
	const { tag, words } = labelTag(text);
	if (tag === null) {
		if (halo) haloText(ctx, text, x, y, halo);
		ctx.fillText(text, x, y);
		return;
	}
	const { font, fillStyle, strokeStyle, lineWidth, textAlign, textBaseline } = ctx;
	const width = ctx.measureText(`[${tag}]`).width;
	const after = ctx.measureText(`[${tag}] `).width;
	const top = y - size;
	const height = size * 1.25;
	ctx.beginPath();
	if (typeof ctx.roundRect === 'function')
		ctx.roundRect(x + 0.5, top + 0.5, width - 1, height - 1, 3);
	else ctx.rect(x + 0.5, top + 0.5, width - 1, height - 1);
	if (halo) {
		ctx.fillStyle = halo;
		ctx.fill();
	}
	ctx.strokeStyle = CHART_COLORS.slate;
	ctx.lineWidth = 1;
	ctx.stroke();
	ctx.font = `600 ${size - 2}px system-ui, sans-serif`;
	ctx.fillStyle = CHART_COLORS.legend;
	ctx.textAlign = 'center';
	ctx.textBaseline = 'alphabetic';
	ctx.fillText(tag, x + width / 2, y - 1);
	ctx.font = font;
	ctx.fillStyle = fillStyle;
	ctx.strokeStyle = strokeStyle;
	ctx.lineWidth = lineWidth;
	ctx.textAlign = textAlign;
	ctx.textBaseline = textBaseline;
	if (words) {
		if (halo) haloText(ctx, words, x + after, y, halo);
		ctx.fillText(words, x + after, y);
	}
}

/**
 * A text's halo (nit 5, rule 7): the text stroked POINT_LABEL_HALO px wide in `halo` with round
 * joins, under the text filled after it; the stroke's colour, width and join are set back.
 */
function haloText(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, halo: string) {
	const { strokeStyle, lineWidth, lineJoin } = ctx;
	ctx.strokeStyle = halo;
	ctx.lineWidth = POINT_LABEL_HALO;
	ctx.lineJoin = 'round';
	ctx.strokeText(text, x, y);
	ctx.strokeStyle = strokeStyle;
	ctx.lineWidth = lineWidth;
	ctx.lineJoin = lineJoin;
}

/**
 * A point's label as placePointLabels placed it (nit 5, rule 7; slice 5c): a far one's leader first,
 * POINT_LABEL_LEADER px in `color` from its box to its mark's edge, then its text over a halo of
 * the surface: a ring's numbers in their box (fillLabel), a name or "Group" as it is.
 */
function drawPointLabel(
	ctx: CanvasRenderingContext2D,
	label: PlacedPointLabel,
	size: number,
	color: string
) {
	if (label.leader) {
		ctx.save();
		ctx.strokeStyle = color;
		ctx.lineWidth = POINT_LABEL_LEADER;
		ctx.setLineDash([]);
		ctx.beginPath();
		ctx.moveTo(label.leader.x1, label.leader.y1);
		ctx.lineTo(label.leader.x2, label.leader.y2);
		ctx.stroke();
		ctx.restore();
	}
	ctx.fillStyle = color;
	if (label.kind === 'ring') fillLabel(ctx, label.text, label.x, label.y, size, SURFACE);
	else {
		haloText(ctx, label.text, label.x, label.y, SURFACE);
		ctx.fillText(label.text, label.x, label.y);
	}
}

/**
 * The point labels as one drawing placed them (nit 5, rule 7; slice 5c), for the notes and for
 * measuring the layout (the canvas's `data-point-labels`): the plot they keep inside, each point
 * labelled or to be (its kind, its centre and its mark's extent `r`, px), the other marks they keep
 * clear of, the labels drawn, and each point whose label is left out, as the notes name it.
 */
export interface PointLabelsDrawn {
	plot: PxBox;
	items: { kind: PointLabelItem['kind']; x: number; y: number; r: number }[];
	obstacles: PxBox[];
	labels: PlacedPointLabel[];
	leftOut: NotLabelledPoint[];
}

/**
 * A point drawn as one dataset of one point (nit 5, rule 7; slice 5c): `pointItem`, how the
 * placer takes it (its kind and words: a ring's numbers and its name where shown); `notLabelled`,
 * how the notes name it with its values where its label is left out (a ring of several cases: each
 * case).
 */
interface PointLabelled {
	pointItem?: PointItemSpec;
	notLabelled?: NotLabelledPoint[];
}
type PointItemSpec =
	| { kind: 'group'; text: string; short?: string }
	| { kind: 'member'; id: string; name: string }
	| { kind: 'ring'; numbers: CaseNumber[]; name?: string };

/**
 * Place the point labels of the datasets that carry a `pointItem`, in `order` (their dataset
 * indices), on the chart as drawn: each centre and mark's extent (its radius and half its border)
 * from Chart.js's pixels, clear of `obstacles` (the marks they do not label) inside `plot`.
 */
function pointLabelsOf(
	chart: ChartInstance<'line'>,
	order: readonly number[],
	obstacles: readonly PxBox[],
	plot: PxBox,
	size: number
): { placed: PointLabelsDrawn; indices: number[] } {
	const items: PointLabelItem[] = [];
	const indices: number[] = [];
	for (const i of order) {
		const dataset = chart.data.datasets[i] as unknown as PointLabelled & {
			pointRadius?: number;
			borderWidth?: number;
		};
		const point = chart.getDatasetMeta(i).data[0];
		const spec = dataset.pointItem;
		if (!spec || !point || !chart.isDatasetVisible(i)) continue;
		if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) continue;
		const r = (dataset.pointRadius ?? 0) + (dataset.borderWidth ?? 0) / 2;
		items.push({ ...spec, x: point.x, y: point.y, r } as PointLabelItem);
		indices.push(i);
	}
	const placement = placePointLabels(
		items,
		obstacles,
		plot,
		(text) => chart.ctx.measureText(text).width,
		size
	);
	const leftOut = placement.leftOut.flatMap(
		(k) => (chart.data.datasets[indices[k]!] as unknown as PointLabelled).notLabelled ?? []
	);
	return {
		placed: {
			plot,
			items: items.map(({ kind, x, y, r }) => ({ kind, x, y, r })),
			obstacles: [...obstacles],
			labels: placement.labels,
			leftOut
		},
		indices
	};
}

/** A mark's box (px): its centre ± its extent. */
function markBox(x: number, y: number, r: number): PxBox {
	return { left: x - r, right: x + r, top: y - r, bottom: y + r };
}

/** Boxes overlap (touching edges do not). */
function boxesOverlap(a: PxBox, b: PxBox): boolean {
	return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
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
		borderColor: hollow ? INK : SURFACE,
		backgroundColor: hollow ? SURFACE : INK,
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
 * system curve, the operating point or the zero-flow point, and the other cases, from the data of
 * pumpChartData() and otherCasesData(). Each other case is a slate ring (r 10, 2 px, a
 * transparent fill), drawn on top (`order: -1`) as the group chart's rings are, named "Case 2:
 * Winter" in the legend and the tooltips and its system curve "System curve, case 2", and labelled
 * on the canvas by its number in a box, then its name (its number alone on a phone's screen); the
 * shapes △ □ ✳ × ▽ are gone (owner, 2026-11-12, nit 5; Q1 "Shapes go too";
 * docs/proposals/pumps-nits.md item 5, slice 5b).
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
		checks = false,
		compactLabels = false,
		onlabels
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
	/**
	 * Another case's ring as the notes name it where its label is left out (nit 5, rule 7):
	 * "case 2, Winter, its ring at 12 L/s and 25 m" (notLabelledNote), the base case by its name.
	 */
	const ringLeftOut = (tag: CaseNumber, name: string, at: ChartPoint): NotLabelledPoint => ({
		name: tag === 'Base' ? name : `case ${tag}, ${name}`,
		mark: 'ring',
		flow: `${fmt(at.x)} ${d.flowUnit}`,
		head: `${fmt(at.y)} ${d.headUnit}`
	});
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
						borderColor: SURFACE,
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
						// The hollow diamond in ink (nit 5, rule 5; chart-marks.ts).
						borderColor: CHART_MARKS.held.stroke,
						backgroundColor: CHART_MARKS.held.fill,
						borderWidth: CHART_MARKS.held.border,
						pointStyle: 'rectRot' as const,
						pointRadius: CHART_MARKS.held.radius,
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
							label: `System curve, ${c.tag === 'Base' ? c.label : `case ${c.tag}`}`,
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
							// The legend's and the tooltips' words: "Case 2: Winter", the base case its name.
							label: c.tag === 'Base' ? c.label : `Case ${c.tag}: ${c.label}`,
							yAxisID: 'y',
							// On the canvas: its number in a box, then its name; a phone's screen the box alone.
							caseLabel: compactLabels && !forImage ? `[${c.tag}]` : `[${c.tag}] ${c.label}`,
							// Placed by placePointLabels (rule 7): "[n] name" where it fits, else "[n]".
							pointItem: {
								kind: 'ring' as const,
								numbers: [c.tag],
								...(compactLabels && !forImage ? {} : { name: c.label })
							},
							notLabelled: [ringLeftOut(c.tag, c.label, (c.operating ?? c.held) as ChartPoint)],
							data: [(c.operating ?? c.held) as ChartPoint],
							// The slate ring (rule 4; chart-marks.ts), as the group chart's.
							borderColor: CHART_MARKS.ring.stroke,
							backgroundColor: CHART_MARKS.ring.fill,
							borderWidth: CHART_MARKS.ring.border,
							pointStyle: 'circle' as const,
							pointRadius: CHART_MARKS.ring.radius,
							pointHoverRadius: 12,
							pointHitRadius: 12,
							showLine: false,
							// Drawn last, on top (Chart.js draws the lowest order last), as the group
							// chart's rings: the case shown's point at the same place shows through.
							order: -1,
							otherCase: true
						}
					]
				: [])
		])
	];
	spanDrawnFlows(datasets);
	// The other cases' rings labelled by placePointLabels (owner, 2026-11-12, nit 5, rules 4 and 7;
	// slice 5c): "[n] name" where the whole label has a place, else its number alone (a phone's
	// screen the number alone), each clear of the other marks (the operating point, the held
	// diamond, the shutoff dash, the BEP crosses, the lower panels' duty dots) and of the other
	// labels, inside the head panel; a ring with none is named in the notes with its values. Was
	// "right of the ring, above and below in turn", which overprinted close rings' labels.
	const caseLabels: Plugin<'line'> = {
		id: 'caseLabels',
		afterDatasetsDraw(chart) {
			const ctx = chart.ctx;
			ctx.save();
			const caseSize = forImage ? 14 : 12;
			ctx.font = `${caseSize}px system-ui, sans-serif`;
			const area = chart.chartArea;
			const head = chart.scales?.y;
			const plot = {
				left: area.left,
				right: area.right,
				top: head?.top ?? area.top,
				bottom: head?.bottom ?? area.bottom
			};
			const rings: number[] = [];
			const obstacles: PxBox[] = [];
			/** The same marks by their dataset: a short label keeps clear of all but its own point's. */
			const marks: { i: number; box: PxBox }[] = [];
			chart.data.datasets.forEach((dataset, i) => {
				const ds = dataset as PointLabelled & {
					showLine?: boolean;
					pointRadius?: number;
					borderWidth?: number;
				};
				if (ds.pointItem) rings.push(i);
				else if (ds.showLine === false && chart.isDatasetVisible(i)) {
					const r = (ds.pointRadius ?? 0) + (ds.borderWidth ?? 0) / 2;
					for (const el of chart.getDatasetMeta(i).data)
						if (Number.isFinite(el.x) && Number.isFinite(el.y)) {
							const box = markBox(el.x, el.y, r);
							obstacles.push(box);
							marks.push({ i, box });
						}
				}
			});
			const { placed } = pointLabelsOf(chart, rings, obstacles, plot, caseSize);
			ctx.textAlign = 'left';
			ctx.textBaseline = 'alphabetic';
			for (const label of placed.labels) drawPointLabel(ctx, label, caseSize, SLATE);
			onlabels?.(placed);
			// Short labels at one point of a line or marker ("BEP", "70 %"), in dataset order; a
			// label that would overlap one already drawn, or a mark, is left out (the legend and notes
			// name it).
			const size = forImage ? 13 : 11;
			ctx.font = `${size}px system-ui, sans-serif`;
			ctx.fillStyle = SLATE;
			// The rings' labels come first (rule 7): a short label over one is left out.
			const taken: { x: number; y: number; w: number; h: number }[] = placed.labels.map(
				({ box }) => ({
					x: box.left,
					y: box.top,
					w: box.right - box.left,
					h: box.bottom - box.top
				})
			);
			// Nor is one drawn over a mark it does not name (rule 7; slice 5c integration: "BEP" fell on
			// another case's ring): the rings, and every single-point mark but its own point's.
			const ringMarks = placed.items.map(({ x, y, r }) => markBox(x, y, r));
			// Nor across a ring label's leader (review DOTS-LABELS-A1), which would seem to run from it.
			const leaders = placed.labels.flatMap((l) => (l.leader ? [l.leader] : []));
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
				const overMark = [...ringMarks, ...marks.filter((m) => m.i !== i).map((m) => m.box)].some(
					(m) =>
						box.x < m.right && m.left < box.x + box.w && box.y < m.bottom && m.top < box.y + box.h
				);
				const crossed = leaders.some((leader) =>
					leaderCrosses(leader, {
						left: box.x,
						right: box.x + box.w,
						top: box.y,
						bottom: box.y + box.h
					})
				);
				if (overlaps || overMark || crossed) return;
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
						// Curves as a line (dashed where dashed), the operating point as a dot, an other
						// case as its ring. Chart.js lists datasets by `order`: the rings (−1, drawn on
						// top) are listed where their datasets are, as before.
						generateLabels: (c) =>
							legendLabels(c)
								.map((item) => ({
									...item,
									pointStyle: legendStyle(c.data.datasets[item.datasetIndex ?? -1] ?? {}) as
										'circle' | 'line'
								}))
								.sort(
									(a, b) =>
										legendOrder(c, a) - legendOrder(c, b) ||
										(a.datasetIndex ?? 0) - (b.datasetIndex ?? 0)
								)
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
/**
 * The group system curve in the system orange (slice 4b): its legend entry (pump-group-chart.ts
 * GROUP_SYSTEM_LABEL, the page's, equal by test) and its direct label on the chart.
 */
export const GROUP_SYSTEM_CURVE_LABEL =
	"Group system curve (the rest of the network between the station's inlet and outlet, station's flow)";
export const GROUP_SYSTEM_TAG = 'Group system curve';
/**
 * Other cases' own group curves (CLAUDE.md D24 slice L3): their one entry in the image's legend
 * (pump-group-chart.ts OTHER_CURVES_LABEL, the page's, equal by test), which Chart.js's labels
 * collapse the family's datasets into (flag `curveFamily`, §9.6).
 */
export const OTHER_CURVES_LEGEND = "Other cases' group curves (slate; dashed beyond a pump's data)";

/**
 * The labels on the curves (D24 §9.3): the page's pure placement, pump-group-chart.ts
 * placeCurveLabels and curveAnchor, passed in as Chart.js's legend labels are, so this module
 * imports nothing of the page at run time.
 */
export interface CurveLabelTools {
	place: (
		curves: readonly CurveLabelInput[],
		obstacles: readonly PxBox[],
		plot: PxBox,
		measure: (text: string) => number,
		compact?: boolean
	) => CurveLabelPlacement;
	anchor: (
		points: readonly { x: number; y: number }[],
		plot: PxBox
	) => { x: number; y: number } | null;
}

/** A box the curve labels keep clear of (D24 §9.3), and what it is. */
export interface CurveLabelObstacle {
	/**
	 * A point's mark, a member's or the Group point's label, a ring's tag, a far label's leader
	 * (nit 5, rule 7: the box it crosses). A curve's tag is placed after the curve labels (rule 7;
	 * review DOTS-LABELS-B1), so it is none of these.
	 */
	kind: 'marker' | 'label' | 'ring' | 'leader';
	text?: string;
	box: PxBox;
}

/** A curve's tag as drawn ("Group system curve"): its left end and baseline, and its box. */
export interface CurveTagDrawn {
	text: string;
	x: number;
	y: number;
	box: PxBox;
}

/**
 * The curve labels as one drawing placed them (pumpGroupConfig's `onlabels`): the labels drawn,
 * the curves whose label was left out for space (the notes count them), and, for measuring the
 * layout, the plot, the boxes kept clear of and the axes' ranges (display units).
 */
export interface CurveLabelsDrawn {
	plot: PxBox;
	labels: PlacedCurveLabel[];
	leftOut: number;
	obstacles: CurveLabelObstacle[];
	x: { min: number; max: number } | null;
	y: { min: number; max: number } | null;
	/** Where the points' labels went, placed before the curves' (nit 5, rule 7; slice 5c). */
	points: PointLabelsDrawn;
	/** The curves' tags drawn, placed after the curve labels (rule 7; review DOTS-LABELS-B1). */
	tags: CurveTagDrawn[];
	/** The tags left out for space, each named in the notes with its curve's end (rule 7). */
	tagsLeftOut: NotLabelledPoint[];
}

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
	/**
	 * The sample "Read along the curves" is at (read when the chart draws): a dashed line at its
	 * rise and a ring on each point read there. Not in the image.
	 */
	readout?: () => GroupReadoutMark | null;
	/**
	 * A phone's screen (slice 4d): an other case's ring is labelled by its number only on the
	 * canvas (the legend, the name and the tables name it); never in the image. D24 slice L3: the
	 * other cases' curves are labelled "{k} running" and their tooltips take the short form.
	 */
	compactLabels?: boolean;
	/**
	 * The labels on the curves while other cases' curves are drawn (D24 §9.3; absent: none
	 * drawn), placed where placeCurveLabels puts them with Chart.js's pixels and the canvas's
	 * measured text.
	 */
	curveLabels?: CurveLabelTools;
	/** Told after every drawing where the curve labels went (absent: not told). */
	onlabels?: (drawn: CurveLabelsDrawn) => void;
}

/**
 * The Pumps together chart, head panel only: each member's curve (its colour and its slot's own
 * dash, dashed beyond its data) and point (a dot in its line's colour, a held pump the hollow
 * diamond in it; named beside it: nit 5, rules 2 and 5, slice 5c), the group curve in ink
 * (dashed where a pump runs beyond its data, gaps where a point has no flow), the group system
 * curve in the system orange (gaps where a point has no rise; a direct label at its end) and the
 * station's duty, an ink dot labelled "Group" ("Group (crossing)" where both duty checks agree).
 * Nothing else: no combined curve and no member's system curve (proposal §6.3, §7). Slice 4d: other cases' station duties, slate rings with a transparent
 * fill, drawn on top (`order: -1`: Chart.js draws the last dataset in its sorted order first) so a
 * Group dot or a member's dot at the same place shows through; the image's legend lists them
 * last. Each ring is tagged with its case's number in a box ("[2] Pump PB off", fillLabel), named
 * "Case 2: …" in the legend and the tooltip (owner, 2026-11-12, nit 5; docs/proposals/pumps-nits.md
 * item 5, slice 5b).
 *
 * D24 slice L3 (proposal pump-lineups.md §9.2–9.6): other cases' own group curves, where drawn,
 * slate at 1.5 px (dashed [6, 4] where a member runs beyond its data, gaps where a point has no
 * flow), under every other line (`order: 1`); their labels ("[1] 3 running": the case numbers in a
 * box) and this case's "{k} running (this case)" placed by placeCurveLabels clear of the marks,
 * the points' labels (placed first by placePointLabels, rule 7) and the tags; the axes' ranges
 * the data sets (§9.4); one entry for the family in the image's legend; each curve's tooltip label its case's, the short form on a phone's screen.
 * "Read along the curves" rings each point read, dashed [4, 3] as its rise line is (nit 5, rule 6).
 */
export function pumpGroupConfig(
	d: GroupChartData,
	{
		legendLabels,
		format,
		forImage = false,
		htmlLegend = false,
		readout,
		compactLabels = false,
		curveLabels,
		onlabels
	}: PumpGroupConfigOptions
): PumpChartConfig {
	const { ink: INK, grid: GRID, text: TEXT, system: SYSTEM, slate: SLATE } = CHART_COLORS;
	const fmt = format;
	const font = (size: number) => (forImage ? { font: { size } } : {});
	/**
	 * A marker's clip (px beyond each edge of the plot): Chart.js's own allowance for a point, its
	 * radius (hovered, its hover radius) and its border, kept on every edge. Chart.js allows none
	 * beyond an edge whose bound the configuration sets (x min, x max and y max while other cases'
	 * curves are drawn, D24 §9.4), which would cut a marker there in half: only other cases'
	 * curves are cut at the plot's edge.
	 */
	const markerClip = (radius: number, hoverRadius: number, borderWidth: number) =>
		Math.max(radius, hoverRadius) + borderWidth;
	/** A phone's screen (never the image): short labels on the canvas and in the tooltips. */
	const compact = compactLabels && !forImage;
	/**
	 * Other cases' own group curves (D24 §9.2): per case a solid dataset and a dashed one where a
	 * member runs beyond its data, each run joined with gaps (a point without a flow breaks both).
	 */
	const family = d.otherCurves.flatMap((c) => {
		const line = (runs: ChartPoint[][], dash: readonly number[]) => ({
			// The tooltip's: the case's name and its members on, or on a phone the short form.
			label: compact ? c.shortLabel : c.label,
			yAxisID: 'y',
			data: joinSegments(runs),
			// Parsed, so Chart.js finds the flow falls along the curve (rise order): with the
			// chart's `parsing: false` it takes the data as sorted by x and, where x max cuts the
			// curve (D24 §9.4), draws only the index range a binary search finds (library-facts.md).
			parsing: { xAxisKey: 'x', yAxisKey: 'y' },
			borderColor: SLATE,
			backgroundColor: SLATE,
			borderWidth: 1.5,
			...(dash.length ? { borderDash: [...dash] } : {}),
			pointRadius: 0,
			pointHitRadius: 4,
			spanGaps: false,
			// Drawn first, under this case's lines and the system curve; the rings stay on top.
			order: 1,
			curveFamily: true,
			curveNumber: c.number
		});
		return [
			...(c.solid.length ? [line(c.solid, [])] : []),
			...(c.beyond.length ? [line(c.beyond, [6, 4])] : [])
		];
	});
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
		// After the group curve and before the group system curve, as the page's legend lists them.
		...family,
		...(d.system?.some((p) => p.y !== null)
			? [
					{
						label: GROUP_SYSTEM_CURVE_LABEL,
						yAxisID: 'y',
						data: d.system as ChartDatum[],
						borderColor: SYSTEM,
						backgroundColor: SYSTEM,
						borderWidth: 2,
						pointRadius: 0,
						pointHitRadius: 6,
						// A point without a solution is a gap, never bridged.
						spanGaps: false,
						curveTag: GROUP_SYSTEM_TAG
					}
				]
			: []),
		// Each member's point (nit 5, rules 2 and 5; slice 5c): a dot in its line's colour with a
		// surface edge, or the hollow diamond in it while held at zero flow (chart-marks.ts
		// memberMark), named beside it by the placer; a running one has no entry in the image's
		// legend (its line's entry names it), a held one keeps its entry, its fact in words. No
		// shape or character stands for a pump (`crossed` and the slots' markers went with them).
		...d.points.map((p) => {
			const mark = memberMark(p.style.color, p.held);
			return {
				label: p.held ? `${p.name}, held at zero flow` : p.name,
				yAxisID: 'y',
				data: [p.point] as ChartDatum[],
				borderColor: mark.stroke,
				backgroundColor: mark.fill,
				borderWidth: mark.border,
				pointStyle: p.held ? ('rectRot' as const) : ('circle' as const),
				pointRadius: mark.radius,
				pointHoverRadius: mark.radius + 2,
				pointHitRadius: 12,
				clip: markerClip(mark.radius, mark.radius + 2, mark.border),
				showLine: false,
				caseLabel: p.name,
				pointItem: { kind: 'member' as const, id: p.id, name: p.name },
				notLabelled: [
					{
						name: p.held ? `${p.name}, held at zero flow` : p.name,
						mark: 'point' as const,
						flow: `${fmt(p.point.x)} ${d.flowUnit}`,
						head: `${fmt(p.point.y)} ${d.headUnit}`
					}
				],
				...(p.held ? {} : { legend: false }),
				memberIds: [p.id]
			};
		}),
		...(d.station
			? [
					{
						label: d.station.label,
						yAxisID: 'y',
						data: [d.station.point] as ChartDatum[],
						// The ink dot (rule 3; chart-marks.ts).
						borderColor: CHART_MARKS.group.stroke,
						backgroundColor: CHART_MARKS.group.fill,
						borderWidth: CHART_MARKS.group.border,
						pointStyle: 'circle' as const,
						pointRadius: CHART_MARKS.group.radius,
						pointHoverRadius: 9,
						pointHitRadius: 12,
						clip: markerClip(CHART_MARKS.group.radius, 9, CHART_MARKS.group.border),
						showLine: false,
						caseLabel: d.station.tag,
						// "Group" where the whole label has no place (rule 3; review DOTS-LABELS-B6).
						pointItem: { kind: 'group' as const, text: d.station.tag, short: 'Group' },
						notLabelled: [
							{
								name: 'Group',
								mark: 'point' as const,
								flow: `${fmt(d.station.flow)} ${d.flowUnit}`,
								head: `${fmt(d.station.point.y)} ${d.headUnit}`
							}
						]
					}
				]
			: []),
		...d.others.map((ring) => {
			const tag = compactLabels && !forImage ? ring.short : ring.tag;
			// Its names where the chart shows them (desktop and the image): the words of its tag.
			const words = labelTag(tag).words;
			return {
				label: ring.label,
				yAxisID: 'y',
				data: [ring.point] as ChartDatum[],
				// The slate ring (rule 4; chart-marks.ts).
				borderColor: CHART_MARKS.ring.stroke,
				backgroundColor: CHART_MARKS.ring.fill,
				borderWidth: CHART_MARKS.ring.border,
				pointStyle: 'circle' as const,
				pointRadius: CHART_MARKS.ring.radius,
				pointHoverRadius: 12,
				pointHitRadius: 12,
				clip: markerClip(CHART_MARKS.ring.radius, 12, CHART_MARKS.ring.border),
				showLine: false,
				// Drawn last, on top: Chart.js draws datasets from the last in its sorted order.
				order: -1,
				caseLabel: tag,
				pointItem: {
					kind: 'ring' as const,
					numbers: [...ring.numbers],
					...(words ? { name: words } : {})
				},
				// Each of its cases by number and name, at its own duty (rule 7).
				notLabelled: ring.cases.map((c): NotLabelledPoint => ({
					name: c.number === 'Base' ? c.name : `case ${c.number}, ${c.name}`,
					mark: 'ring',
					flow: `${fmt(c.flow)} ${d.flowUnit}`,
					head: `${fmt(c.rise)} ${d.headUnit}`
				})),
				labelColor: SLATE,
				otherCase: true
			};
		})
	];
	// Each point's label where placePointLabels puts it (owner, 2026-11-12, nit 5, rule 7; slice
	// 5c): this case's first (the Group, then each member, a held one among them), then the other
	// cases' rings; each clear of every mark but its own and of the other labels, inside the plot;
	// members within 12 px share one label; a pump left out so is tried again before the other
	// pumps (review DOTS-LABELS-B7). A point whose label has no place is named in the notes
	// with its values. Then D24's curve labels, clear of every mark, point label and leader; then
	// the group system curve's tag, last (rule 7): where its curve ends, else beside that end, clear
	// of them all, else left out and named in the notes with its end's values. Was "right of the
	// point, above and below in turn", which overprinted close points' labels ("Pump P1" over "Pump
	// P3"); and the tag first, where its curve ends, the points' labels clear of it, which took the
	// lineups' pumps' one place on a phone (review DOTS-LABELS-B1).
	const pointLabels: Plugin<'line'> = {
		id: 'groupLabels',
		afterDatasetsDraw(chart) {
			const ctx = chart.ctx;
			const size = forImage ? 14 : 12;
			/** What the curve labels keep clear of (D24 §9.3): every mark, label and leader here. */
			const obstacles: CurveLabelObstacle[] = [];
			/** A text's box at its baseline: the font's size above it, a quarter below (descenders). */
			const textBox = (x: number, y: number, width: number): PxBox => ({
				left: x,
				right: x + width,
				top: y - size,
				bottom: y + size / 4
			});
			ctx.save();
			ctx.fillStyle = INK;
			ctx.font = `${size}px system-ui, sans-serif`;
			const area = chart.chartArea;
			const plot = { left: area.left, right: area.right, top: area.top, bottom: area.bottom };
			// The points in the placer's order: the Group, the members, the rings.
			const kindOf = (i: number) =>
				(chart.data.datasets[i] as unknown as PointLabelled).pointItem?.kind;
			const all = chart.data.datasets.map((_, i) => i);
			const order = (['group', 'member', 'ring'] as const).flatMap((kind) =>
				all.filter((i) => kindOf(i) === kind)
			);
			const { placed, indices } = pointLabelsOf(chart, order, [], plot, size);
			ctx.textAlign = 'left';
			ctx.textBaseline = 'alphabetic';
			// Each point's mark (its radius and half its border), then each label and its leader.
			indices.forEach((i, k) => {
				const { x, y, r } = placed.items[k]!;
				const text = (chart.data.datasets[i] as { caseLabel?: string }).caseLabel;
				obstacles.push({ kind: 'marker', ...(text ? { text } : {}), box: markBox(x, y, r) });
			});
			for (const label of placed.labels) {
				// A ring's tag, which the code builds from its case numbers: its numbers in a box, then
				// its names where they are shown (fillLabel). Every other label (a pump's name, the
				// user's text, and "Group") is written as it is: a name that starts "[2] " is a name,
				// never case 2's box (nit 5, rules 2 and 4; review CASE-NUMBERS-A1, B2).
				drawPointLabel(ctx, label, size, label.kind === 'ring' ? SLATE : INK);
				obstacles.push({
					kind: label.kind === 'ring' ? 'ring' : 'label',
					text: label.text,
					box: label.box
				});
				const leader = label.leader;
				if (leader)
					obstacles.push({
						kind: 'leader',
						text: label.text,
						box: {
							left: Math.min(leader.x1, leader.x2),
							right: Math.max(leader.x1, leader.x2),
							top: Math.min(leader.y1, leader.y2),
							bottom: Math.max(leader.y1, leader.y2)
						}
					});
			}
			const placement = curveLabelsOf(chart, obstacles);
			ctx.textAlign = 'left';
			ctx.textBaseline = 'alphabetic';
			for (const label of placement.labels) {
				ctx.fillStyle = label.shown ? INK : SLATE;
				// Another case's: its numbers in a box, then "3 running" (fillLabel).
				fillLabel(ctx, label.text, label.x, label.y, size);
			}
			// A curve's tag, last (rule 7), near its last drawn point inside the plot: above the line
			// and ending there (as before), else right of that point, else under it to its right or to
			// its left; inside the plot, over no point label (as the points' labels kept off it before:
			// it has no halo to keep apart) or leader, mark, curve label or tag before it. With none, it
			// is left out and named in the notes with that point's values.
			const tags: CurveTagDrawn[] = [];
			const tagsLeftOut: NotLabelledPoint[] = [];
			const marks = obstacles.filter((o) => o.kind === 'marker').map((o) => o.box);
			const leaders = placed.labels.flatMap((l) => (l.leader ? [l.leader] : []));
			chart.data.datasets.forEach((dataset, i) => {
				const tag = (dataset as { curveTag?: string }).curveTag;
				if (!tag || !chart.isDatasetVisible(i)) return;
				let end: { x: number; y: number; datum: ChartPoint } | null = null;
				chart.getDatasetMeta(i).data.forEach((el, k) => {
					const datum = dataset.data[k] as ChartDatum | undefined;
					if (datum?.y == null) return;
					const inside =
						el.x >= area.left && el.x <= area.right && el.y >= area.top && el.y <= area.bottom;
					if (inside) end = { x: el.x, y: el.y, datum: { x: datum.x, y: datum.y } };
				});
				const at = end as { x: number; y: number; datum: ChartPoint } | null;
				if (!at) return;
				const width = ctx.measureText(tag).width;
				const row = Math.max(area.top + 14, at.y - 8);
				const below = at.y + size + 4;
				const inX = (x: number) => Math.max(area.left + 2, Math.min(x, area.right - width - 2));
				const taken = [
					...placed.labels.map((l) => l.box),
					...placement.labels.map((l) => l.box),
					...tags.map((t) => t.box)
				];
				const clear = (box: PxBox) =>
					box.left >= area.left &&
					box.right <= area.right &&
					box.top >= area.top &&
					box.bottom <= area.bottom &&
					![...taken, ...marks].some((b) => boxesOverlap(b, box)) &&
					!leaders.some((l) => leaderCrosses(l, box));
				const spot = [
					{ x: inX(at.x - width), y: row },
					{ x: at.x + 4, y: row },
					{ x: at.x + 4, y: below },
					{ x: inX(at.x - width - 4), y: below }
				]
					.map((p) => ({ ...p, box: textBox(p.x, p.y, width) }))
					.find((p) => clear(p.box));
				if (!spot) {
					tagsLeftOut.push({
						name: tag,
						mark: 'end',
						flow: `${fmt(at.datum.x)} ${d.flowUnit}`,
						head: `${fmt(at.datum.y)} ${d.headUnit}`
					});
					return;
				}
				ctx.fillStyle = (dataset as { labelColor?: string }).labelColor ?? INK;
				ctx.fillText(tag, spot.x, spot.y);
				tags.push({ text: tag, x: spot.x, y: spot.y, box: spot.box });
			});
			ctx.restore();
			const { left, right, top, bottom } = chart.chartArea;
			const range = (id: string) => {
				const scale = chart.scales?.[id];
				return scale ? { min: scale.min, max: scale.max } : null;
			};
			onlabels?.({
				plot: { left, right, top, bottom },
				labels: placement.labels,
				leftOut: placement.leftOut,
				obstacles,
				tags,
				tagsLeftOut,
				points: placed,
				x: range('x'),
				y: range('y')
			});
		}
	};
	/**
	 * The curve labels' placement (D24 §9.3), while other cases' curves are drawn: each such curve
	 * and this case's group curve anchored at its drawn point of largest flow inside the plot (in
	 * Chart.js's pixels), placed by placeCurveLabels with the canvas's measured text, clear of
	 * `obstacles`. None without the family, or without the page's placement.
	 */
	function curveLabelsOf(
		chart: ChartInstance<'line'>,
		obstacles: readonly CurveLabelObstacle[]
	): CurveLabelPlacement {
		if (!curveLabels || !d.otherCurves.length) return { labels: [], leftOut: 0 };
		const { left, right, top, bottom } = chart.chartArea;
		const plot = { left, right, top, bottom };
		/** The drawn points (px) of the datasets `which` picks: a gap's point is not drawn. */
		const drawn = (which: (dataset: Record<string, unknown>) => boolean) =>
			chart.data.datasets.flatMap((dataset, i) =>
				which(dataset as unknown as Record<string, unknown>) && chart.isDatasetVisible(i)
					? chart
							.getDatasetMeta(i)
							.data.filter((_, k) => (dataset.data[k] as ChartDatum | undefined)?.y != null)
							.map((el) => ({ x: el.x, y: el.y }))
					: []
			);
		const curves: CurveLabelInput[] = d.otherCurves.map((c) => ({
			anchor: curveLabels.anchor(
				drawn((ds) => ds.curveFamily === true && ds.curveNumber === c.number),
				plot
			),
			k: c.k,
			numbers: [c.number]
		}));
		if (d.on !== null) {
			curves.push({
				anchor: curveLabels.anchor(
					drawn((ds) => ds.label === GROUP_CURVE_LABEL || ds.label === GROUP_BEYOND_LABEL),
					plot
				),
				k: d.on,
				numbers: []
			});
		}
		return curveLabels.place(
			curves,
			obstacles.map((o) => o.box),
			plot,
			(text) => chart.ctx.measureText(text).width,
			compact
		);
	}
	// "Read along the curves": the sample read, a dashed line at its rise and a dashed ring on
	// each point read there (drawn last, over the curves).
	const readoutMark: Plugin<'line'> = {
		id: 'groupReadout',
		afterDatasetsDraw(chart) {
			const mark = readout?.();
			const { ctx, chartArea, scales } = chart;
			const x = scales.x;
			const y = scales.y;
			if (!mark || !x || !y) return;
			const py = y.getPixelForValue(mark.rise);
			ctx.save();
			ctx.strokeStyle = SLATE;
			if (py >= chartArea.top && py <= chartArea.bottom) {
				ctx.lineWidth = 1;
				ctx.setLineDash([4, 3]);
				ctx.beginPath();
				ctx.moveTo(chartArea.left, py);
				ctx.lineTo(chartArea.right, py);
				ctx.stroke();
			}
			// The rings on the points read: dashed as the rise line is, so none reads as an other
			// case's solid slate ring (r 10) beside it (nit 5, rule 6).
			ctx.setLineDash([4, 3]);
			ctx.lineWidth = 2;
			for (const p of mark.points) {
				const px = x.getPixelForValue(p.x);
				const ppy = y.getPixelForValue(p.y);
				if (px < chartArea.left || px > chartArea.right) continue;
				if (ppy < chartArea.top || ppy > chartArea.bottom) continue;
				ctx.beginPath();
				ctx.arc(px, ppy, 11, 0, 2 * Math.PI);
				ctx.stroke();
			}
			ctx.restore();
		}
	};
	return {
		type: 'line',
		plugins: forImage || !readout ? [pointLabels] : [pointLabels, readoutMark],
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
					// Set only where other cases' curves would widen it: they are cut there (D24 §9.4).
					...(d.xMin !== null ? { min: d.xMin } : {}),
					...(d.xMax !== null ? { max: d.xMax } : {}),
					title: { display: true, text: `Flow (${d.flowUnit})`, color: TEXT, ...font(15) },
					grid: { color: GRID },
					ticks: { color: TEXT, ...font(14) }
				},
				y: {
					type: 'linear',
					beginAtZero: true,
					// While other cases' curves are drawn: near the pumps, the group system curve cut (§9.4).
					...(d.yMax !== null ? { max: d.yMax } : {}),
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
						generateLabels: (c) => {
							const items = legendLabels(c).map((item) => {
								const ds = c.data.datasets[item.datasetIndex ?? -1] as
									{ showLine?: boolean; pointStyle?: unknown; borderDash?: number[] } | undefined;
								const point = ds?.showLine === false && typeof ds.pointStyle === 'string';
								return {
									...item,
									pointStyle: (point ? ds.pointStyle : 'line') as 'circle' | 'line',
									// A line's swatch dashed as its line (rule 2: a slot's pattern is its second
									// cue): Chart.js takes an entry's style from its first point under
									// usePointStyle, which has no dashes, so it drew every line solid (review
									// DOTS-LABELS-B3).
									...(point ? {} : { lineDash: [...(ds?.borderDash ?? [])] })
								};
							});
							// Other cases' own group curves as one entry, a solid slate line (D24 §9.6).
							const first = items.find((item) => curveFamily(c, item));
							return (
								items
									.filter((item) => item === first || !curveFamily(c, item))
									.map((item) =>
										item === first
											? {
													...item,
													text: OTHER_CURVES_LEGEND,
													strokeStyle: SLATE,
													fillStyle: SLATE,
													lineDash: []
												}
											: item
									)
									// Other cases' rings last (their `order` would list them first), the rest in
									// the datasets' order (the family's `order` would list it after the points).
									.sort(
										(a, b) =>
											otherCase(c, a) - otherCase(c, b) ||
											(a.datasetIndex ?? 0) - (b.datasetIndex ?? 0)
									)
							);
						}
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

/**
 * A pump chart legend item's place: its dataset's `order`, an other case's ring (`order: −1`, so
 * drawn on top) counted as 0, where its dataset is.
 */
function legendOrder(chart: ChartInstance, item: LegendItem): number {
	const ds = chart.data.datasets[item.datasetIndex ?? -1] as
		{ order?: number; otherCase?: boolean } | undefined;
	return ds?.otherCase ? 0 : (ds?.order ?? 0);
}

/** 1 for a legend item of an other case's ring (slice 4d), else 0. */
function otherCase(chart: ChartInstance, item: LegendItem): number {
	const ds = chart.data.datasets[item.datasetIndex ?? -1] as { otherCase?: boolean } | undefined;
	return ds?.otherCase ? 1 : 0;
}

/** A legend item of an other case's own group curve (D24 slice L3). */
function curveFamily(chart: ChartInstance, item: LegendItem): boolean {
	const ds = chart.data.datasets[item.datasetIndex ?? -1] as { curveFamily?: boolean } | undefined;
	return ds?.curveFamily === true;
}
