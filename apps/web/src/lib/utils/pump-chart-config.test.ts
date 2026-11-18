/**
 * The pump chart's configuration (proposal export.md §3.4): the screen's chart and the image's
 * fixed-size render draw the same datasets; the image has no animation, events or tooltip, is
 * drawn at 2× and has larger fonts; other cases are slate rings named by their case numbers. Pump
 * results are made-up test inputs.
 */
import { BasicPlatform } from 'chart.js';
import { describe, expect, it } from 'vitest';
import { Chart } from '$lib/components/results/chart-setup';
import { pumpResult, systemCurveResponse } from '../testing/results';
import { otherCasesData, pumpChartData, type OtherCaseData } from './pump-chart';
import {
	CHART_COLORS,
	fillLabel,
	labelTag,
	pumpChartConfig,
	type PointLabelsDrawn,
	pumpGroupConfig
} from './pump-chart-config';
import { lineupView } from '../testing/curve-family';
import {
	GROUP_AQUA,
	GROUP_BLUE,
	GROUP_SLOTS,
	groupChartData,
	type GroupMemberInput
} from './pump-group-chart';
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

	// Nit 5 (owner, 2026-11-12; docs/proposals/pumps-nits.md item 5, slice 5b): a slate ring named
	// by its case's number, in place of the hollow triangle named "Winter (out of date)".
	it('draws the other cases in slate, each a ring named by its number', () => {
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
			1,
			null,
			{ S1: 3 }
		);
		const config = pumpChartConfig(data, others, {
			speedText: '100 % speed',
			legendLabels,
			format
		});
		const winter = config.data.datasets.find((d) => d.label === 'Case 3: Winter (out of date)');
		expect(winter).toMatchObject({
			borderColor: CHART_COLORS.slate,
			pointStyle: 'circle',
			showLine: false
		});
		// Nit 5 (slice 5b, review CASE-NUMBERS-A2 and B3): its pump curve names it by its number too,
		// as its ring does; was "Pump curve at 90 % speed (Winter, out of date)".
		expect(labelsOf(config)).toContain('Pump curve at 90 % speed (case 3: Winter, out of date)');
	});

	// ▽, the triangle turned over, went with the other shapes (nit 5, slice 5b): the test that drew
	// it is replaced by "draws every other case as a slate ring" below, eight cases, none turned.
});

describe('the group chart’s member marks (owner, 2026-11-12, nit 5; docs/proposals/pumps-nits.md item 5)', () => {
	/**
	 * The point styles Chart.js 4.5.1 draws as open paths, stroked only: its drawPoint moves and
	 * draws lines for `cross`, `crossRot`, `star`, `line` and `dash`, and its fill() then fills no
	 * area (node_modules/chart.js/dist/chunks/helpers.dataset.js, drawPointLegend). Such a mark is
	 * its border alone, on the chart and in the image's legend.
	 */
	const STROKE_ONLY = new Set(['cross', 'crossRot', 'star', 'line', 'dash']);

	// Nit 5, slice 5c (Q1 "Shapes go too"): moved from "strokes every stroke-only member mark in
	// its slot's colour, 3 px or more" (5a's interim fix for slot 3's white star), now that each
	// member's point is a dot: no member mark is stroke-only, and each one's ink, its fill (a dot)
	// or its 2 px border (the held diamond), is its line's colour, never the surface's white.
	it('draws no member mark stroke-only: each dot is filled, each held diamond stroked, in its line’s colour, never white', () => {
		// A member in each of the six slots, running, and one more held at zero flow.
		const members: GroupMemberInput[] = [
			...GROUP_SLOTS.map((_, slot) => ({
				id: `P${slot + 1}`,
				name: `Pump P${slot + 1}`,
				result: pumpResult({ operatingFlow: 0.005 * (slot + 1) }),
				ratedRange: [0, 0.03] as [number, number],
				curveId: null,
				slot,
				flags: []
			})),
			{
				id: 'P7',
				name: 'Pump P7',
				result: pumpResult({ status: 'no_flow', operatingFlow: 0, operatingHead: 30 }),
				ratedRange: [0, 0.03] as [number, number],
				curveId: null,
				slot: 0,
				flags: []
			}
		];
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
		// In slot order: the held P7 shares slot 1 with P1.
		expect(marks.map((d) => d.memberIds![0])).toEqual(['P1', 'P7', 'P2', 'P3', 'P4', 'P5', 'P6']);
		expect(marks.filter((d) => STROKE_ONLY.has(d.pointStyle as string))).toEqual([]);
		for (const mark of marks) {
			const line = data.lines.find((l) => l.ids.includes(mark.memberIds![0]!))!;
			const held = mark.memberIds![0] === 'P7';
			expect(mark.pointStyle, mark.label).toBe(held ? 'rectRot' : 'circle');
			// Its ink in its line's colour: a dot's fill, the held diamond's border.
			expect(held ? mark.borderColor : mark.backgroundColor, mark.label).toBe(line.style.color);
			expect(line.style.color, mark.label).not.toBe('#ffffff');
			expect(mark.borderWidth, mark.label).toBe(2);
		}
	});
});

// Case numbers (owner, 2026-11-12, nit 5; Q1 "Shapes go too"; docs/proposals/pumps-nits.md item
// 5, slice 5b): the pump chart's other cases are slate rings, as the group chart's are, named by
// their numbers in the legend and the tooltips; the shapes △ □ ✳ × ▽ go. The canvas's own labels
// (placePointLabels since slice 5c) are tested under "the pump chart's other cases on the canvas".
describe('the pump chart’s other cases as numbered slate rings (nit 5, slice 5b)', () => {
	const legendLabels = () => [];
	const format = (v: number) => formatNumber(v, 4);
	const ids = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8'];
	const tags = Object.fromEntries(ids.map((id, i) => [id, i + 1]));
	type Dataset = Record<string, unknown> & { label?: string };
	const datasetsOf = (config: ReturnType<typeof pumpChartConfig>) =>
		config.data.datasets as unknown as Dataset[];

	it('draws every other case as a slate ring: r 10, 2 px, a transparent fill, on top; no shape tells them apart', () => {
		const data = pumpChartData(pumpResult(), SI_UNITS, [0, 0.03]);
		const others = otherCasesData(
			ids.map((key, i) => ({
				key,
				name: `Scenario ${key}`,
				result: pumpResult({ operatingFlow: 0.002 * (i + 1), operatingHead: 30 - i }),
				stale: false,
				system: null
			})),
			SI_UNITS,
			[0, 0.03],
			1,
			null,
			tags
		);
		const config = pumpChartConfig(data, others, {
			speedText: '100 % speed',
			legendLabels,
			format
		});
		const rings = datasetsOf(config).filter((d) => /^Case \d+: /.test(d.label ?? ''));
		// The legend and the tooltips name each by its number (eight: none runs out).
		expect(rings.map((d) => d.label)).toEqual(ids.map((id, i) => `Case ${i + 1}: Scenario ${id}`));
		for (const ring of rings) {
			expect(ring, ring.label).toMatchObject({
				borderColor: CHART_COLORS.slate,
				backgroundColor: 'transparent',
				borderWidth: 2,
				pointStyle: 'circle',
				pointRadius: 10,
				showLine: false,
				// On top (Chart.js draws the lowest order last), as the group chart's rings.
				order: -1
			});
			expect(ring.pointRotation ?? 0, ring.label).toBe(0);
		}
		// No other case's point is one of the old shapes.
		const shapes = new Set(['triangle', 'rect', 'star', 'crossRot', 'triangleDown', 'rectRounded']);
		expect(datasetsOf(config).filter((d) => shapes.has(d.pointStyle as string))).toEqual([]);
	});

	it('names an other case’s system curve by its number, the base case by its name', () => {
		const data = pumpChartData(pumpResult(), SI_UNITS, [0, 0.03]);
		const others = otherCasesData(
			[
				{
					key: '',
					name: 'Base case',
					result: pumpResult(),
					stale: false,
					system: systemCurveResponse()
				},
				{
					key: 'S2',
					name: 'Pump PB off',
					result: pumpResult({ operatingFlow: 0.012 }),
					stale: true,
					system: systemCurveResponse()
				}
			],
			SI_UNITS,
			[0, 0.03],
			1,
			null,
			{ '': 'Base', S2: 2 }
		);
		const labels = datasetsOf(
			pumpChartConfig(data, others, { speedText: '100 % speed', legendLabels, format })
		).map((d) => d.label);
		expect(labels).toEqual(
			expect.arrayContaining([
				'Base case',
				'System curve, Base case',
				'Case 2: Pump PB off (out of date)',
				'System curve, case 2'
			])
		);
		// Never a name alone for a numbered case, nor the old "System curve, {name}".
		expect(labels).not.toContain('Pump PB off (out of date)');
		expect(labels).not.toContain('System curve, Pump PB off (out of date)');
	});
});

// "Read along the curves" on the group chart (owner, 2026-11-12, nit 5; docs/proposals/pumps-nits.md
// item 5, rule 6): its rings are stroked dashed [4, 3], the rise line's own dash, so none reads as
// an other case's solid slate ring (r 10) beside it; today they are solid at r 11.
describe('the group chart’s readout rings (nit 5, slice 5b)', () => {
	/** A context that records each stroke: whether its path holds an arc, and the dash then set. */
	function recordingContext() {
		const strokes: { arc: boolean; dash: number[]; color: string; width: number }[] = [];
		let state = { dash: [] as number[] };
		const saved: (typeof state)[] = [];
		let arc = false;
		const ctx = {
			strokeStyle: '',
			fillStyle: '',
			lineWidth: 1,
			font: '',
			save() {
				saved.push({ ...state, dash: [...state.dash] });
			},
			restore() {
				state = saved.pop() ?? { dash: [] };
			},
			setLineDash(dash: number[]) {
				state.dash = [...dash];
			},
			getLineDash: () => [...state.dash],
			beginPath() {
				arc = false;
			},
			moveTo() {},
			lineTo() {},
			arc() {
				arc = true;
			},
			stroke() {
				strokes.push({ arc, dash: [...state.dash], color: ctx.strokeStyle, width: ctx.lineWidth });
			},
			fill() {},
			fillText() {},
			measureText: () => ({ width: 10 })
		};
		return { ctx, strokes };
	}

	it('strokes the rings on the points read dashed [4, 3], as the rise line, in slate', () => {
		const members: GroupMemberInput[] = [0, 1].map((slot) => ({
			id: `P${slot + 1}`,
			name: `Pump P${slot + 1}`,
			result: pumpResult({ operatingFlow: 0.01 * (slot + 1) }),
			ratedRange: [0, 0.03],
			curveId: null,
			slot,
			flags: []
		}));
		const data = groupChartData(members, SI_UNITS, null);
		const config = pumpGroupConfig(data, {
			legendLabels: () => [],
			format: (v: number) => formatNumber(v, 4),
			readout: () => ({
				rise: 20,
				points: [
					{ x: 5, y: 20 },
					{ x: 10, y: 20 },
					{ x: 15, y: 20 }
				]
			})
		});
		const plugin = config.plugins!.find((p) => p.id === 'groupReadout')!;
		const { ctx, strokes } = recordingContext();
		const chart = {
			ctx,
			chartArea: { left: 0, right: 1000, top: 0, bottom: 1000 },
			scales: {
				x: { getPixelForValue: (v: number) => v * 10 },
				y: { getPixelForValue: (v: number) => 1000 - v * 10 }
			}
		};
		plugin.afterDatasetsDraw!(chart as never, {} as never, {} as never, undefined as never);
		const rings = strokes.filter((s) => s.arc);
		const rise = strokes.filter((s) => !s.arc);
		expect(rings).toHaveLength(3);
		expect(rise).toHaveLength(1);
		expect(rise[0]!.dash).toEqual([4, 3]);
		for (const ring of rings) {
			expect(ring.dash).toEqual([4, 3]);
			expect(ring.color).toBe(CHART_COLORS.slate);
		}
	});
});

// The pump chart's other cases on the canvas (owner, 2026-11-12, nit 5;
// docs/proposals/pumps-nits.md item 5, slice 5b): today's label code, a boxed number where the
// shape was. A label "[2] Winter" is drawn by fillLabel as the number in a box as wide as "[2]"
// measures, then the name; the legend keeps each ring where its dataset is, though `order: -1`
// draws it on top.
describe('the pump chart’s other cases on the canvas (nit 5, slice 5b)', () => {
	const legendLabels = () => [];
	const format = (v: number) => formatNumber(v, 4);
	type Dataset = Record<string, unknown> & { label?: string; caseLabel?: string };
	const others = (stale = false) =>
		otherCasesData(
			[
				{ key: '', name: 'Base case', result: pumpResult(), stale: false, system: null },
				{
					key: 'S2',
					name: 'Winter',
					result: pumpResult({ operatingFlow: 0.012, operatingHead: 25 }),
					stale,
					system: systemCurveResponse()
				}
			],
			SI_UNITS,
			[0, 0.03],
			1,
			null,
			{ '': 'Base', S2: 2 }
		);
	const rings = (config: ReturnType<typeof pumpChartConfig>) =>
		(config.data.datasets as unknown as Dataset[]).filter((d) => d.otherCase === true);

	it('tags each ring "[n] name" on the canvas, "[n]" alone on a phone’s screen, never so in the image', () => {
		const data = pumpChartData(pumpResult(), SI_UNITS, [0, 0.03]);
		const screen = pumpChartConfig(data, others(true), {
			speedText: '100 %',
			legendLabels,
			format
		});
		expect(rings(screen).map((d) => d.caseLabel)).toEqual([
			'[Base] Base case',
			'[2] Winter (out of date)'
		]);
		const phone = pumpChartConfig(data, others(), {
			speedText: '100 %',
			legendLabels,
			format,
			compactLabels: true
		});
		expect(rings(phone).map((d) => d.caseLabel)).toEqual(['[Base]', '[2]']);
		const image = pumpChartConfig(data, others(), {
			speedText: '100 %',
			legendLabels,
			format,
			compactLabels: true,
			forImage: true
		});
		expect(rings(image).map((d) => d.caseLabel)).toEqual(['[Base] Base case', '[2] Winter']);
	});

	it('writes a tagged label as its number in a box, then its words, the label as wide as its text measures', () => {
		expect(labelTag('[2] Winter')).toEqual({ tag: '2', words: 'Winter' });
		expect(labelTag('[1, 4, 5, 6] 3 running')).toEqual({ tag: '1, 4, 5, 6', words: '3 running' });
		expect(labelTag('[Base]')).toEqual({ tag: 'Base', words: '' });
		expect(labelTag('Group (crossing)')).toEqual({ tag: null, words: 'Group (crossing)' });
		const calls: unknown[][] = [];
		const ctx = {
			font: '12px system-ui, sans-serif',
			fillStyle: '#475569',
			strokeStyle: '#000000',
			lineWidth: 3,
			textAlign: 'left',
			textBaseline: 'alphabetic',
			measureText: (text: string) => ({ width: text.length * 6 }),
			beginPath: () => calls.push(['beginPath']),
			roundRect: (...a: number[]) => calls.push(['roundRect', ...a]),
			fill() {
				calls.push(['fill', this.fillStyle]);
			},
			stroke() {
				calls.push(['stroke', this.strokeStyle, this.lineWidth]);
			},
			fillText(text: string, x: number, y: number) {
				calls.push(['fillText', text, x, y, this.font, this.fillStyle, this.textAlign]);
			}
		};
		fillLabel(ctx as unknown as CanvasRenderingContext2D, '[12] Winter', 100, 50, 12);
		// The box: "[12]" measures 24 px; from the font's size above the baseline to a quarter of it
		// below (12 + 3 px), on half pixels for a crisp 1 px edge, a slate edge and no fill. Nit 5,
		// slice 5b integration: moved from "white with a slate edge" (['fill', '#ffffff'] before the
		// stroke). Today's label code puts a label wherever it falls, so a white box hid the mark under
		// it: the group duty's ink dot in the one-off and lineups views at 1280 and 390 px, half the
		// case shown's operating point on the one-off's pump chart. Unfilled, a mark shows through it
		// as it did through the plain text before; keeping labels off marks is 5c's placer's.
		expect(calls).toEqual([
			['beginPath'],
			['roundRect', 100.5, 38.5, 23, 14, 3],
			['stroke', CHART_COLORS.slate, 1],
			// Its number bold, centred in it, in the legend's ink, 1 px above the baseline.
			['fillText', '12', 112, 49, '600 10px system-ui, sans-serif', CHART_COLORS.legend, 'center'],
			// Then the words where "[12] " ends, in the colour, font and alignment set.
			['fillText', 'Winter', 130, 50, '12px system-ui, sans-serif', '#475569', 'left']
		]);
		// Everything set back.
		expect([ctx.font, ctx.fillStyle, ctx.strokeStyle, ctx.lineWidth, ctx.textAlign]).toEqual([
			'12px system-ui, sans-serif',
			'#475569',
			'#000000',
			3,
			'left'
		]);
		// A label without a tag: its text alone, as before.
		calls.length = 0;
		fillLabel(ctx as unknown as CanvasRenderingContext2D, 'BEP', 10, 20, 12);
		expect(calls).toEqual([
			['fillText', 'BEP', 10, 20, '12px system-ui, sans-serif', '#475569', 'left']
		]);
	});

	// Nit 5, rule 7 (slice 5c): a point's label, placed clear of every mark but its own, is drawn
	// over a halo of the surface, so it reads over a curve under it: its box filled with the
	// surface, its words stroked POINT_LABEL_HALO (3) px wide in it, round joined, before they are
	// filled; the stroke set back. A curve's label (no halo) is the call list above, unchanged.
	it('draws a point’s label over a halo of the surface: its box filled, its words stroked 3 px under them', () => {
		const calls: unknown[][] = [];
		const ctx = {
			font: '12px system-ui, sans-serif',
			fillStyle: '#475569',
			strokeStyle: '#000000',
			lineWidth: 1,
			lineJoin: 'miter',
			textAlign: 'left',
			textBaseline: 'alphabetic',
			measureText: (text: string) => ({ width: text.length * 6 }),
			beginPath: () => calls.push(['beginPath']),
			roundRect: (...a: number[]) => calls.push(['roundRect', ...a]),
			fill() {
				calls.push(['fill', this.fillStyle]);
			},
			stroke() {
				calls.push(['stroke', this.strokeStyle, this.lineWidth]);
			},
			strokeText(text: string, x: number, y: number) {
				calls.push(['strokeText', text, x, y, this.strokeStyle, this.lineWidth, this.lineJoin]);
			},
			fillText(text: string, x: number, y: number) {
				calls.push(['fillText', text, x, y, this.font, this.fillStyle, this.textAlign]);
			}
		};
		fillLabel(ctx as unknown as CanvasRenderingContext2D, '[2] Winter', 100, 50, 12, '#ffffff');
		expect(calls).toEqual([
			['beginPath'],
			['roundRect', 100.5, 38.5, 17, 14, 3],
			['fill', '#ffffff'],
			['stroke', CHART_COLORS.slate, 1],
			['fillText', '2', 109, 49, '600 10px system-ui, sans-serif', CHART_COLORS.legend, 'center'],
			['strokeText', 'Winter', 124, 50, '#ffffff', 3, 'round'],
			['fillText', 'Winter', 124, 50, '12px system-ui, sans-serif', '#475569', 'left']
		]);
		expect([ctx.fillStyle, ctx.strokeStyle, ctx.lineWidth, ctx.lineJoin]).toEqual([
			'#475569',
			'#000000',
			1,
			'miter'
		]);
		// A name, untagged: its halo, then its text.
		calls.length = 0;
		fillLabel(ctx as unknown as CanvasRenderingContext2D, 'Pump PA', 10, 20, 12, '#ffffff');
		expect(calls).toEqual([
			['strokeText', 'Pump PA', 10, 20, '#ffffff', 3, 'round'],
			['fillText', 'Pump PA', 10, 20, '12px system-ui, sans-serif', '#475569', 'left']
		]);
	});

	/**
	 * The caseLabels plugin run on a stand-in chart: each ring's centre at `at(its case number)`,
	 * every other dataset's points far right of the plot (no mark in the way unless `others` puts
	 * one there); the boxes, texts and halos it draws, and what it tells `onlabels`.
	 */
	const drawCaseLabels = (
		config: ReturnType<typeof pumpChartConfig>,
		plot: { left: number; right: number; top: number; bottom: number },
		at: (tag: string) => { x: number; y: number },
		others: (i: number) => { x: number; y: number } = () => ({ x: 5000, y: 5000 })
	) => {
		const sets = config.data.datasets as unknown as Dataset[];
		const written: { text: string; x: number; y: number; align: string }[] = [];
		const halos: { text: string; x: number; y: number; color: string; width: number }[] = [];
		const boxes: { x: number; y: number; w: number; fill: string | null }[] = [];
		let fill: string | null = null;
		const ctx = {
			font: '',
			fillStyle: '',
			strokeStyle: '',
			lineWidth: 1,
			lineJoin: 'miter',
			textAlign: 'start',
			textBaseline: 'alphabetic',
			save() {},
			restore() {},
			setLineDash() {},
			measureText: (text: string) => ({ width: text.length * 6 }),
			beginPath() {
				fill = null;
			},
			moveTo() {},
			lineTo() {},
			roundRect(x: number, y: number, w: number) {
				boxes.push({ x: x - 0.5, y: y - 0.5, w: w + 1, fill: null });
			},
			fill() {
				fill = this.fillStyle;
				boxes.at(-1)!.fill = fill;
			},
			stroke() {},
			strokeText(text: string, x: number, y: number) {
				halos.push({ text, x, y, color: this.strokeStyle, width: this.lineWidth });
			},
			fillText(text: string, x: number, y: number) {
				written.push({ text, x, y, align: this.textAlign });
			}
		};
		const chart = {
			ctx,
			chartArea: plot,
			data: config.data,
			isDatasetVisible: () => true,
			getDatasetMeta: (i: number) => {
				const tag = /^\[([^\]]+)\]/.exec(sets[i]!.caseLabel ?? '')?.[1];
				return {
					data: (sets[i]!.data as unknown[]).map(() => (tag ? at(tag) : others(i)))
				};
			}
		};
		const plugin = config.plugins!.find((p) => p.id === 'caseLabels')!;
		plugin.afterDatasetsDraw!(chart as never, {} as never, {} as never, undefined as never);
		return { written, halos, boxes };
	};

	// Nit 5, slice 5c (rule 7): moved from "draws each ring's tag right of it with today's label
	// code" (10 px right of its centre, above and below in turn, which overprinted close rings'
	// labels): each ring's label goes where placePointLabels puts it, its first place right of
	// the ring, its box POINT_LABEL_NEAR (2) px clear of the ring's mark (r 10 and half its 2 px
	// border: 11), centred on it; over a halo of the surface; the brackets never reach the canvas.
	it('labels each ring where placePointLabels puts it, right of it where that is free, over a halo, and tells where', () => {
		const data = pumpChartData(pumpResult(), SI_UNITS, [0, 0.03]);
		const told: PointLabelsDrawn[] = [];
		const config = pumpChartConfig(data, others(), {
			speedText: '100 %',
			legendLabels,
			format,
			onlabels: (placed) => told.push(placed)
		});
		const centres: Record<string, { x: number; y: number }> = {
			Base: { x: 100, y: 200 },
			2: { x: 400, y: 200 }
		};
		const plot = { left: 0, right: 1000, top: 0, bottom: 1000 };
		const { written, halos, boxes } = drawCaseLabels(config, plot, (tag) => centres[tag]!);
		// 12 px text, 6 px a character here: a label 15 px tall (12 above its baseline, 3 below),
		// its box's left 100 + 11 + 2 = 113, its top 200 − 15 / 2 = 192.5, its baseline 204.5.
		// "[Base] Base case" is 16 characters, 96 px; "[2] Winter" 10, 60 px.
		expect(boxes).toEqual([
			{ x: 113, y: 192.5, w: 36, fill: '#ffffff' },
			{ x: 413, y: 192.5, w: 18, fill: '#ffffff' }
		]);
		// The words where "[Base] " (42 px) and "[2] " (24 px) end, each over its halo.
		expect(written).toContainEqual({ text: 'Base case', x: 155, y: 204.5, align: 'left' });
		expect(written).toContainEqual({ text: 'Winter', x: 437, y: 204.5, align: 'left' });
		expect(halos).toEqual([
			{ text: 'Base case', x: 155, y: 204.5, color: '#ffffff', width: 3 },
			{ text: 'Winter', x: 437, y: 204.5, color: '#ffffff', width: 3 }
		]);
		expect(written.map((w) => w.text)).toEqual(
			expect.arrayContaining(['Base', '2', 'Base case', 'Winter'])
		);
		expect(written.some((w) => w.text.includes('['))).toBe(false);
		// Told where: the head panel's plot, each ring, its label, none left out.
		expect(told).toHaveLength(1);
		expect(told[0]!.plot).toEqual(plot);
		expect(told[0]!.items).toEqual([
			{ kind: 'ring', x: 100, y: 200, r: 11 },
			{ kind: 'ring', x: 400, y: 200, r: 11 }
		]);
		expect(told[0]!.labels.map((l) => [l.text, l.box, l.leader])).toEqual([
			['[Base] Base case', { left: 113, right: 209, top: 192.5, bottom: 207.5 }, null],
			['[2] Winter', { left: 413, right: 473, top: 192.5, bottom: 207.5 }, null]
		]);
		expect(told[0]!.leftOut).toEqual([]);
	});

	// Review CASE-NUMBERS-B1 (rule 4: "the name follows the box where it fits"): a label that would
	// run past the plot's right edge is never cut at the canvas's edge. On e5e6558 the one-off's
	// case 2 at 1280 px read "[2] Pump PB", the name of the pump that is off in it. Nit 5, slice 5c
	// (rule 7): moved from "its number alone, right of the ring, or left of it at the edge" (boxes at
	// 110, 430 and 457): the placer tries the whole label at each of its places first, so case 2's
	// name follows its box on the left, where it has room; case 3's has none, so its box is alone.
	it('draws a ring’s name after its number wherever the whole label has a place in the plot, else its number alone', () => {
		const data = pumpChartData(pumpResult(), SI_UNITS, [0, 0.03]);
		const input = (key: string, name: string) => ({
			key,
			name,
			result: pumpResult({ operatingFlow: 0.012, operatingHead: 25 }),
			stale: false,
			system: null
		});
		const cases = otherCasesData(
			[input('S1', 'Pump PA off'), input('S2', 'Pump PB off'), input('S3', 'Both pumps off')],
			SI_UNITS,
			[0, 0.03],
			1,
			null,
			{ S1: 1, S2: 2, S3: 3 }
		);
		const plot = { left: 40, right: 500, top: 0, bottom: 300 };
		/** Each ring's centre (px): case 1 well inside, case 2 near the edge, case 3 at it. */
		const ringX: Record<string, number> = { 1: 100, 2: 420, 3: 485 };
		const draw = (options: { forImage?: boolean; compactLabels?: boolean }) => {
			const told: PointLabelsDrawn[] = [];
			const config = pumpChartConfig(data, cases, {
				speedText: '100 %',
				legendLabels,
				format,
				onlabels: (placed) => told.push(placed),
				...options
			});
			// The case shown's marks (its operating point, shutoff dash, BEP) at (60, 150).
			const drawn = drawCaseLabels(
				config,
				plot,
				(tag) => ({ x: ringX[tag]!, y: 150 }),
				() => ({ x: 60, y: 150 })
			);
			return { ...drawn, told: told[0]! };
		};
		for (const forImage of [false, true]) {
			const { written, boxes, told } = draw({ forImage });
			// No name is cut: the names left out are not written at all, and nothing passes the edge.
			const words = written.filter((w) => w.align !== 'center');
			for (const w of words)
				expect(w.x + w.text.length * 6, w.text).toBeLessThanOrEqual(plot.right);
			expect(words.map((w) => w.text)).toEqual(['Pump PA off', 'Pump PB off']);
			// Case 1 fits whole right of its ring: 100 + 11 + 2 = 113 to 113 + 90 = 203.
			expect(boxes[0]).toMatchObject({ x: 113, w: 18 });
			expect(written).toContainEqual(expect.objectContaining({ text: 'Pump PA off', x: 137 }));
			// Case 2's whole label would end at 433 + 90 = 523, past 500: left of its ring instead,
			// 420 − 11 − 2 − 90 = 317 to 407, clear of case 3's ring (474 to 496).
			expect(boxes[1]).toMatchObject({ x: 317, w: 18 });
			expect(written).toContainEqual(expect.objectContaining({ text: 'Pump PB off', x: 341 }));
			// Case 3's whole label (108 px) has no place: right passes 500, left and the corners meet
			// case 2's label or lie nearer case 2's ring. Its number alone, left of it: 485 − 13 − 18
			// = 454 to 472.
			expect(boxes[2]).toMatchObject({ x: 454, w: 18 });
			expect(boxes).toHaveLength(3);
			for (const b of boxes) expect(b.x + b.w).toBeLessThanOrEqual(plot.right);
			// Each box holds its number.
			expect(written.filter((w) => w.align === 'center').map((w) => w.text)).toEqual([
				'1',
				'2',
				'3'
			]);
			expect(told.labels.map((l) => l.text)).toEqual(['[1] Pump PA off', '[2] Pump PB off', '[3]']);
			expect(told.leftOut).toEqual([]);
		}
		// A phone's screen: each number alone; case 3's left place lies 3 px from case 2's box, under
		// the 4 px gap, so it goes above its ring: 485 − 9 = 476, its bottom 150 − 13 = 137.
		const phone = draw({ compactLabels: true });
		expect(phone.boxes.map((b) => b.x)).toEqual([113, 433, 476]);
		expect(phone.boxes[2]).toMatchObject({ y: 122 });
		expect(phone.written.filter((w) => w.align !== 'center')).toEqual([]);
	});

	// Nit 5, rule 7 (slice 5c): a ring whose label has no place is never dropped silently: the
	// drawing tells it, by its case's number and name with its values, for the notes to name.
	it('tells a ring whose label has no place, named by its case with its values, for the notes', () => {
		const data = pumpChartData(pumpResult(), SI_UNITS, [0, 0.03]);
		const told: PointLabelsDrawn[] = [];
		const config = pumpChartConfig(data, others(), {
			speedText: '100 %',
			legendLabels,
			format,
			onlabels: (placed) => told.push(placed)
		});
		// A plot 20 px square round both rings: no label has a place.
		const { written, boxes } = drawCaseLabels(
			config,
			{ left: 90, right: 110, top: 190, bottom: 210 },
			(tag) => (tag === 'Base' ? { x: 95, y: 200 } : { x: 105, y: 200 })
		);
		expect(boxes).toEqual([]);
		expect(written.filter((w) => /Base|Winter|^2$/.test(w.text))).toEqual([]);
		const ring = (c: OtherCaseData) => c.operating ?? c.held!;
		const [base, winter] = others();
		expect(told[0]!.labels).toEqual([]);
		expect(told[0]!.leftOut).toEqual([
			{
				name: 'Base case',
				mark: 'ring',
				flow: `${format(ring(base!).x)} L/s`,
				head: `${format(ring(base!).y)} m`
			},
			{
				name: 'case 2, Winter',
				mark: 'ring',
				flow: `${format(ring(winter!).x)} L/s`,
				head: `${format(ring(winter!).y)} m`
			}
		]);
	});

	// Nit 5, slice 5c integration (rule 7: no label over a mark it does not name): the short labels
	// ("BEP", an iso-efficiency line's "70 %") kept clear of the labels drawn before them only, so
	// "BEP" was written over another case's ring in the browser (the lineups' case 2 and the
	// condenser's case 1 at 1280×800, the lineups' case 2 at 390×844). A short label that would lie
	// over a ring or over any mark but its own point's is left out, as one over a label is: the
	// legend and the notes name the best efficiency point.
	it('leaves a short label out where it would lie over a ring or another mark, as over a label', () => {
		const result = pumpResult({
			bestEfficiencyPoint: { flow: 0.012, efficiency: 0.7, head: 18, headExtrapolated: false }
		});
		const data = pumpChartData(result, SI_UNITS, [0, 0.03]);
		const config = pumpChartConfig(data, others(), { speedText: '100 %', legendLabels, format });
		const sets = config.data.datasets as unknown as Dataset[];
		const bep = sets.findIndex((d) => d.pointLabel === 'BEP');
		const operating = sets.findIndex((d) => d.label === 'Operating point');
		expect(bep).toBeGreaterThanOrEqual(0);
		expect(operating).toBeGreaterThanOrEqual(0);
		const plot = { left: 0, right: 1000, top: 0, bottom: 1000 };
		const far = { x: 5000, y: 5000 };
		/** "BEP" as drawn: its cross at (200, 200), case 2's ring at `ring`, the duty at `duty`. */
		const draw = (ring: { x: number; y: number }, duty = far) =>
			drawCaseLabels(
				config,
				plot,
				(tag) => (tag === '2' ? ring : { x: 700, y: 700 }),
				(i) => (i === bep ? { x: 200, y: 200 } : i === operating ? duty : far)
			)
				.written.filter((w) => w.text === 'BEP')
				.map(({ text, x, y }) => ({ text, x, y }));
		// Clear of every mark: 6 px right of its cross and 6 px above it, 11 px text, 18 px wide
		// here; its box 206 to 224 across, 183 to 194 down, over its own cross (190.5 to 209.5).
		expect(draw({ x: 600, y: 600 })).toEqual([{ text: 'BEP', x: 206, y: 194 }]);
		// Case 2's ring (r 10 and half its 2 px border: 11) at (215, 180): 204 to 226 across, 169 to
		// 191 down, over the box. Its own label goes right of it (228 on), clear of the box.
		expect(draw({ x: 215, y: 180 })).toEqual([]);
		// The operating point's dot (r 6 and half its 2 px border: 7) at (230, 190): 223 to 237
		// across, 183 to 197 down, over the box's right end.
		expect(draw({ x: 600, y: 600 }, { x: 230, y: 190 })).toEqual([]);
		// Just clear of both: the ring's box ends at 182, above the box's top (183).
		expect(draw({ x: 215, y: 171 }, { x: 232, y: 190 })).toEqual([{ text: 'BEP', x: 206, y: 194 }]);
	});

	// Review DOTS-LABELS-A1 (rule 7: a leader on a clear path): the short labels kept clear of the
	// rings' labels' boxes, not of their leaders, so "BEP" could be written across a ring label's
	// leader, which then seemed to run from "BEP". Case 2's ring under the BEP cross, its near
	// places blocked (the plot's right edge and foot, the cross), its "[2]" placed above it, far,
	// its leader running up through where "BEP" goes: at 7b36d82 "BEP" was written across it.
	it('leaves a short label out where a ring label’s leader would run through it', () => {
		const result = pumpResult({
			bestEfficiencyPoint: { flow: 0.012, efficiency: 0.7, head: 18, headExtrapolated: false }
		});
		const data = pumpChartData(result, SI_UNITS, [0, 0.03]);
		const told: PointLabelsDrawn[] = [];
		const config = pumpChartConfig(data, others(), {
			speedText: '100 %',
			legendLabels,
			format,
			compactLabels: true,
			onlabels: (placed) => told.push(placed)
		});
		const sets = config.data.datasets as unknown as Dataset[];
		const bep = sets.findIndex((d) => d.pointLabel === 'BEP');
		const { written } = drawCaseLabels(
			config,
			{ left: 0, right: 230, top: 0, bottom: 218 },
			(tag) => (tag === '2' ? { x: 215, y: 205 } : { x: 60, y: 60 }),
			(i) => (i === bep ? { x: 200, y: 200 } : { x: 5000, y: 5000 })
		);
		// "[2]" far above its ring: its leader from its box down to the ring, at x 215, 180 to 194.
		const ring = told[0]!.labels.find((l) => l.text === '[2]')!;
		expect(ring.leader).toEqual({ x1: 215, y1: 180, x2: 215, y2: 194 });
		// "BEP" would go 6 px right of its cross and 6 px above it: 206 to 224 across, 183 to 194
		// down, the leader through it. Left out; the legend and the notes name the point.
		expect(written.filter((w) => w.text === 'BEP')).toEqual([]);
	});

	it('lists each ring in the legend where its dataset is, though it is drawn on top', () => {
		const data = pumpChartData(pumpResult(), SI_UNITS, [0, 0.03], systemCurveResponse());
		const plain = pumpChartConfig(data, others(), { speedText: '100 %', legendLabels, format });
		const sets = plain.data.datasets as unknown as Dataset[];
		// Chart.js's own items, sorted as it sorts them (by `order`, then the datasets' order).
		const sorted = sets
			.map((d, i) => ({ d, i }))
			.sort((a, b) => ((a.d.order as number) ?? 0) - ((b.d.order as number) ?? 0) || a.i - b.i);
		const config = pumpChartConfig(data, others(), {
			speedText: '100 %',
			legendLabels: () => sorted.map(({ d, i }) => ({ text: d.label!, datasetIndex: i }) as never),
			format
		});
		expect(sorted[0]!.d.otherCase).toBe(true);
		const labels = config.options!.plugins!.legend!.labels!.generateLabels!({
			data: config.data
		} as never).map((item) => item.text);
		// The datasets' order, but for those of a higher order listed after (as before: the rising
		// stretch, `order: 1`), the rings in their place among the other cases' datasets.
		const expected = sets
			.map((d, i) => ({ d, i }))
			.sort(
				(a, b) =>
					(a.d.otherCase ? 0 : ((a.d.order as number) ?? 0)) -
						(b.d.otherCase ? 0 : ((b.d.order as number) ?? 0)) || a.i - b.i
			)
			.map(({ d }) => d.label);
		expect(labels).toEqual(expected);
		expect(labels.slice(-3)).toEqual(['Base case', 'System curve, case 2', 'Case 2: Winter']);
	});
});

// Pumps as named dots (owner, 2026-11-12, nit 5; Q1 "Shapes go too"; docs/proposals/pumps-nits.md
// item 5, rules 2 and 5; slice 5c): each member's point on the group chart is a filled dot (r 6)
// in its line's colour with a 2 px surface edge, named beside it (the placer's); members on one
// line share that line's colour; the six slots keep their colours, each with a line pattern of its
// own; a pump held at zero flow keeps the hollow diamond (rectRot) in its line's colour. Fails
// first on the slots' shapes ▲ ■ ★ × + ▢, P2 and P4 aqua on P1's blue line, slots 1 and 2 both
// solid (blue against aqua at 1.30:1) and a held pump's diamond in its own slot's colour.
describe('the group chart’s members as dots in their line’s colour (nit 5, slice 5c)', () => {
	type Dataset = Record<string, unknown> & {
		label?: string;
		memberIds?: string[];
		showLine?: boolean;
		caseLabel?: string;
	};
	const options = { legendLabels: () => [], format: (v: number) => formatNumber(v, 4) };
	const sets = (config: ReturnType<typeof pumpGroupConfig>) =>
		config.data.datasets as unknown as Dataset[];
	/** Each member's point: a dataset of one point, no line, naming its member. */
	const pointsOf = (config: ReturnType<typeof pumpGroupConfig>) =>
		sets(config).filter((d) => d.showLine === false && d.memberIds?.length === 1);
	/** The line a member is drawn on (inside its data), by its id. */
	const lineOf = (config: ReturnType<typeof pumpGroupConfig>, id: string) =>
		sets(config).find(
			(d) =>
				d.showLine !== false &&
				d.memberIds?.includes(id) &&
				!String(d.label).endsWith(', beyond its data')
		)!;
	/** The Group's ink dot: its 2 px edge is the surface, as the members' is. */
	const groupDot = (config: ReturnType<typeof pumpGroupConfig>) =>
		sets(config).find((d) => d.caseLabel === 'Group' || d.caseLabel === 'Group (crossing)')!;
	/** A member on a curve of its own (`curve`), or sharing one with the members of that curve. */
	const member = (
		id: string,
		slot: number,
		curve: string,
		values: Parameters<typeof pumpResult>[0] = {}
	): GroupMemberInput => ({
		id,
		name: `Pump ${id}`,
		result: pumpResult(values),
		ratedRange: [0, 0.03],
		curveId: curve,
		slot,
		flags: []
	});
	/** A station's duty, so the chart draws the Group dot (made-up: the shape of the API's). */
	const station = {
		duty: { flow: 0.03, head: 20, members: [] },
		points: [],
		dutyCheck: null
	} as never;

	it('draws every running member’s point as a circle r 6 filled with its line’s colour, with the Group dot’s 2 px surface edge', () => {
		// Six members, each on a curve of its own: six lines, one per slot.
		const members = GROUP_SLOTS.map((_, slot) =>
			member(`P${slot + 1}`, slot, `C${slot + 1}`, { operatingFlow: 0.004 * (slot + 1) })
		);
		const config = pumpGroupConfig(groupChartData(members, SI_UNITS, station), options);
		const points = pointsOf(config);
		expect(points.map((d) => d.memberIds![0])).toEqual(['P1', 'P2', 'P3', 'P4', 'P5', 'P6']);
		const surface = groupDot(config).borderColor;
		expect(surface).toBeDefined();
		for (const point of points) {
			expect(point, point.label).toMatchObject({
				pointStyle: 'circle',
				pointRadius: 6,
				borderWidth: 2,
				borderColor: surface,
				backgroundColor: lineOf(config, point.memberIds![0]!).borderColor
			});
			expect(point.pointRotation ?? 0, point.label).toBe(0);
			// Named beside it on the canvas, as typed (the placer's label).
			expect(point.caseLabel, point.label).toBe(`Pump ${point.memberIds![0]}`);
		}
	});

	it('gives members on one shared line that line’s colour: the lineups’ P2 and P4 are blue on P1’s blue line, not aqua', () => {
		// Made-up: four members on one curve at one speed (one line, slot 1's) and a fifth on its own.
		const members = [
			member('P1', 0, 'C1', { operatingFlow: 0.02 }),
			member('P2', 1, 'C1', { operatingFlow: 0.021 }),
			member('P3', 2, 'C1', { operatingFlow: 0.019 }),
			member('P4', 3, 'C1', { operatingFlow: 0.022 }),
			member('P5', 4, 'C5', { operatingFlow: 0.01 })
		];
		const config = pumpGroupConfig(groupChartData(members, SI_UNITS, null), options);
		const colours = Object.fromEntries(
			pointsOf(config).map((d) => [d.memberIds![0], d.backgroundColor])
		);
		expect(colours).toEqual({
			P1: GROUP_BLUE,
			P2: GROUP_BLUE,
			P3: GROUP_BLUE,
			P4: GROUP_BLUE,
			P5: lineOf(config, 'P5').borderColor
		});
		// The lineups station as the fixture solves it: its four pumps on one line, one colour.
		const lineups = pumpGroupConfig(lineupView('').data, options);
		const shared = sets(lineups).filter((d) => d.showLine !== false && d.memberIds?.length === 4);
		expect(shared).not.toHaveLength(0);
		for (const point of pointsOf(lineups))
			expect(point.backgroundColor, point.label).toBe(shared[0]!.borderColor);
	});

	it('keeps the six slots’ colours and gives each a line pattern of its own: slots 1 and 2 differ by more than hue', () => {
		expect(GROUP_SLOTS.map((s) => s.color)).toEqual([
			GROUP_BLUE,
			GROUP_AQUA,
			GROUP_BLUE,
			GROUP_AQUA,
			GROUP_BLUE,
			GROUP_AQUA
		]);
		// Pairwise distinct inside the data (today: two solid, two dash-dot, two dashed).
		const patterns = GROUP_SLOTS.map((s) => JSON.stringify(s.dash));
		expect(new Set(patterns).size).toBe(6);
		// No marker and no symbol any more: a slot is a colour and its dashes.
		for (const slot of GROUP_SLOTS)
			expect(Object.keys(slot).sort()).toEqual(['beyondDash', 'color', 'dash']);
		// On the chart: six members on six lines, each line's pattern its own.
		const members = GROUP_SLOTS.map((_, slot) => member(`P${slot + 1}`, slot, `C${slot + 1}`));
		const config = pumpGroupConfig(groupChartData(members, SI_UNITS, null), options);
		const drawn = members.map((m) => JSON.stringify(lineOf(config, m.id).borderDash ?? []));
		expect(new Set(drawn).size).toBe(6);
	});

	it('draws a pump held at zero flow as the hollow diamond (rectRot) in its line’s colour, named “held at zero flow”', () => {
		const held = { status: 'no_flow' as const, operatingFlow: 0, operatingHead: 30 };
		// On a line of its own: its slot's colour (aqua, slot 2).
		const alone = pumpGroupConfig(
			groupChartData([member('PA', 0, 'C1'), member('PB', 1, 'C2', held)], SI_UNITS, station),
			options
		);
		const surface = groupDot(alone).borderColor;
		const diamond = pointsOf(alone).find((d) => d.memberIds![0] === 'PB')!;
		expect(diamond).toMatchObject({
			label: 'Pump PB, held at zero flow',
			pointStyle: 'rectRot',
			borderColor: GROUP_AQUA,
			backgroundColor: surface
		});
		// On a line it shares with Pump PA: that line's colour (blue), as every member's point.
		const sharing = pumpGroupConfig(
			groupChartData([member('PA', 0, 'C1'), member('PB', 1, 'C1', held)], SI_UNITS, station),
			options
		);
		expect(pointsOf(sharing).find((d) => d.memberIds![0] === 'PB')).toMatchObject({
			pointStyle: 'rectRot',
			borderColor: GROUP_BLUE,
			backgroundColor: surface
		});
	});

	// Review DOTS-LABELS-B6 (rule 3): the Group's label has a shorter form, "Group", for the placer
	// to take where "Group (crossing)" has no place (point-labels.test.ts holds the placer to it).
	it('gives the Group point “Group” as its label’s shorter form, its whole label first', () => {
		const lineups = pumpGroupConfig(lineupView('').data, options);
		expect(groupDot(lineups).pointItem).toEqual({
			kind: 'group',
			text: 'Group (crossing)',
			short: 'Group'
		});
		const members = [member('PA', 0, 'C1'), member('PB', 1, 'C2', { operatingFlow: 0.01 })];
		const plain = pumpGroupConfig(groupChartData(members, SI_UNITS, station), options);
		expect(groupDot(plain).pointItem).toEqual({ kind: 'group', text: 'Group', short: 'Group' });
	});

	it('leaves the members’ points out of the image’s legend: the labels on the chart name them', () => {
		const members = [member('PA', 0, 'C1'), member('PB', 1, 'C2', { operatingFlow: 0.01 })];
		const config = pumpGroupConfig(groupChartData(members, SI_UNITS, station), {
			...options,
			forImage: true
		});
		const filter = config.options!.plugins!.legend!.labels!.filter!;
		const listed = sets(config).filter((_, i) =>
			filter({ datasetIndex: i } as never, config.data as never)
		);
		expect(listed.filter((d) => d.showLine === false && d.memberIds?.length === 1)).toEqual([]);
		// The lines stay, and the Group dot.
		expect(listed.map((d) => d.label)).toEqual(
			expect.arrayContaining([
				'Pump PA, 100 % speed (own flow)',
				'Pump PB, 100 % speed (own flow)',
				groupDot(config).label
			])
		);
	});
});

// Leftover L16 (docs/proposals/pumps-nits.md §8.14 bullet 4; §11.5): the pump chart's legend drew
// every curve's swatch solid, "Motor rated power (dashed)" and "Minimum flow (dash-dot)" among
// them, since with usePointStyle Chart.js 4.5.1 takes an entry's style from its first point, which
// has no dashes (the group chart's DOTS-LABELS-B3). Drawn here by Chart.js itself.
describe('the pump chart’s legend draws each line in its dataset’s dashes (leftover L16)', () => {
	const full = pumpResult({
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
		]
	});
	const checks = {
		checks: {
			npshMargin: { minimumMargin: 1, source: { kind: 'user' as const } },
			operatingRegion: { preferredMin: 0.7, preferredMax: 1.2, source: { kind: 'user' as const } }
		},
		curve: {
			id: 'C1',
			name: 'Curve',
			points: [
				{ flow: 0, head: 30 },
				{ flow: 0.02, head: 22 }
			],
			allowableOperatingRegion: { flowMin: 0.004, flowMax: 0.025 },
			minimumContinuousStableFlow: 0.003,
			motorRatedPower: 5500
		},
		sources: { npshMargin: 'your values', operatingRegion: 'your values' }
	};

	it('strokes each curve’s swatch with its own dashes, as drawn on the canvas, on screen and in the image', () => {
		// Rated to 20 L/s, so the curve beyond it is dashed; a second case with its system curve.
		const data = pumpChartData(full, SI_UNITS, [0, 0.02], systemCurveResponse(), null, checks);
		const others = otherCasesData(
			[
				{
					key: 'S1',
					name: 'Winter',
					result: pumpResult({ operatingFlow: 0.015, operatingHead: 25 }),
					stale: false,
					system: systemCurveResponse()
				}
			],
			SI_UNITS,
			[0, 0.02],
			1,
			null,
			{ S1: 2 }
		);
		for (const forImage of [false, true]) {
			const legend = drawnLegend(
				pumpChartConfig(data, others, {
					speedText: '100 % speed',
					legendLabels: Chart.defaults.plugins.legend.labels.generateLabels,
					format: (v) => formatNumber(v, 4),
					panels: ['head', 'efficiency', 'power', 'npsh'],
					checks: true,
					forImage
				}),
				900,
				1100
			);
			const named = [
				'Motor rated power (dashed)',
				'Minimum flow (dash-dot)',
				'Pump curve, extrapolated (dashed)',
				'NPSHa required by the check (dotted)',
				'NPSHr',
				'System curve, case 2',
				'Pump curve at 100 % speed',
				'System curve'
			];
			expect(legend.items.map((i) => i.text)).toEqual(expect.arrayContaining(named));
			const dash = (text: string) => legend.items.find((i) => i.text === text)!.lineDash;
			expect(dash('Motor rated power (dashed)'), `forImage ${forImage}`).toEqual([6, 3]);
			expect(dash('Minimum flow (dash-dot)')).toEqual([8, 3, 2, 3]);
			expect(dash('Pump curve, extrapolated (dashed)')).toEqual([6, 4]);
			expect(dash('NPSHa required by the check (dotted)')).toEqual([2, 2]);
			expect(dash('NPSHr')).toEqual([8, 3]);
			expect(dash('System curve, case 2')).toEqual([2, 3]);
			// A solid curve stays solid.
			expect(dash('Pump curve at 100 % speed')).toEqual([]);
			expect(dash('System curve')).toEqual([]);
			// Each line entry's dashes are its dataset's own, and its swatch is stroked with them, in
			// the legend's order (the shutoff's dash, a point style, is one solid segment too).
			const lines = legend.items.filter((i) => i.pointStyle === 'line');
			for (const line of lines) expect(line.lineDash, line.text).toEqual(line.own);
			expect(legend.swatches.map((s) => s.dash)).toEqual(
				legend.items
					.filter((i) => i.pointStyle === 'line' || i.pointStyle === 'dash')
					.map((i) => (i.pointStyle === 'line' ? i.own : []))
			);
		}
	});
});

/**
 * Chart.js lays out and draws `config` on a canvas of `width` × `height` in the `server` project
 * (BasicPlatform, no DOM), the context recording each stroke's dashes and points (text measured at
 * 6 px a character); then its legend is drawn again on its own. Its items with each one's dataset's
 * own `borderDash`, and the 'line' swatches stroked (two points in their path), in order.
 */
function drawnLegend(
	config: ReturnType<typeof pumpChartConfig>,
	width: number,
	height: number
): {
	items: {
		text: string;
		pointStyle: unknown;
		lineDash: number[] | undefined;
		hidden: boolean;
		own: number[];
	}[];
	swatches: { dash: number[]; points: number }[];
} {
	const strokes: { dash: number[]; points: number }[] = [];
	let dash: number[] = [];
	let points = 0;
	const ctx: Record<string | symbol, unknown> = new Proxy({} as Record<string | symbol, unknown>, {
		get(target, prop) {
			if (prop in target) return target[prop];
			if (prop === 'measureText') return (text: string) => ({ width: String(text).length * 6 });
			if (prop === 'setLineDash') return (d: number[]) => (dash = [...d]);
			if (prop === 'getLineDash') return () => [...dash];
			if (prop === 'beginPath') return () => (points = 0);
			if (prop === 'moveTo' || prop === 'lineTo') return () => points++;
			if (prop === 'stroke') return () => strokes.push({ dash: [...dash], points });
			return () => undefined;
		}
	});
	const canvas = { width, height, style: {}, getContext: () => ctx };
	ctx.canvas = canvas;
	const chart = new Chart(canvas as never, { ...config, platform: BasicPlatform } as never);
	try {
		const items = chart.legend!.legendItems!.map((item) => ({
			text: item.text,
			pointStyle: item.pointStyle,
			lineDash: item.lineDash,
			hidden: item.hidden,
			own: [
				...((chart.data.datasets[item.datasetIndex ?? -1] as { borderDash?: number[] } | undefined)
					?.borderDash ?? [])
			]
		}));
		strokes.length = 0;
		chart.legend!.draw(chart.chartArea);
		return { items, swatches: strokes.filter((s) => s.points === 2) };
	} finally {
		chart.destroy();
	}
}
