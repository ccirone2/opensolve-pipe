/**
 * The pump chart's configuration (proposal export.md §3.4): the screen's chart and the image's
 * fixed-size render draw the same datasets; the image has no animation, events or tooltip, is
 * drawn at 2× and has larger fonts; other cases are slate rings named by their case numbers. Pump
 * results are made-up test inputs.
 */
import { describe, expect, it } from 'vitest';
import { pumpResult, systemCurveResponse } from '../testing/results';
import { otherCasesData, pumpChartData } from './pump-chart';
import {
	CHART_COLORS,
	fillLabel,
	labelTag,
	pumpChartConfig,
	pumpGroupConfig
} from './pump-chart-config';
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

// Case numbers (owner, 2026-11-12, nit 5; Q1 "Shapes go too"; docs/proposals/pumps-nits.md item
// 5, slice 5b): the pump chart's other cases are slate rings, as the group chart's are, named by
// their numbers in the legend and the tooltips; the shapes △ □ ✳ × ▽ go. The canvas's own labels
// keep today's code (a boxed number where a shape was), so they are not tested here.
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

	it('draws each ring’s tag right of it with today’s label code, and the brackets never reach the canvas', () => {
		const data = pumpChartData(pumpResult(), SI_UNITS, [0, 0.03]);
		const config = pumpChartConfig(data, others(), { speedText: '100 %', legendLabels, format });
		const written: { text: string; x: number; y: number }[] = [];
		const boxes: number[][] = [];
		const ctx = {
			font: '',
			fillStyle: '',
			strokeStyle: '',
			lineWidth: 1,
			textAlign: 'start',
			textBaseline: 'alphabetic',
			save() {},
			restore() {},
			measureText: (text: string) => ({ width: text.length * 6 }),
			beginPath() {},
			roundRect: (...a: number[]) => boxes.push(a),
			fill() {},
			stroke() {},
			fillText: (text: string, x: number, y: number) => written.push({ text, x, y })
		};
		const sets = config.data.datasets as unknown as Dataset[];
		const chart = {
			ctx,
			// A plot wide enough for every label whole (review CASE-NUMBERS-B1: the plugin reads its
			// right edge; the test below draws one too narrow).
			chartArea: { left: 0, right: 10000, top: 0, bottom: 1000 },
			data: config.data,
			isDatasetVisible: () => true,
			getDatasetMeta: (i: number) => ({
				data: (sets[i]!.data as unknown[]).map((_, k) => ({ x: 100 + 50 * i + k, y: 200 }))
			})
		};
		const plugin = config.plugins!.find((p) => p.id === 'caseLabels')!;
		plugin.afterDatasetsDraw!(chart as never, {} as never, {} as never, undefined as never);
		const at = (label: string) => {
			const i = sets.findIndex((d) => d.caseLabel === label);
			return { x: 100 + 50 * i, y: 200 };
		};
		// Above the first ring and below the second (in turn), 10 px right of its centre (r 10).
		const base = at('[Base] Base case');
		const winter = at('[2] Winter');
		expect(boxes).toEqual([
			[base.x + 10 + 0.5, base.y - 10 - 12 + 0.5, 6 * 6 - 1, 14, 3],
			[winter.x + 10 + 0.5, winter.y + 20 - 12 + 0.5, 3 * 6 - 1, 14, 3]
		]);
		expect(written).toContainEqual({ text: 'Base case', x: base.x + 10 + 7 * 6, y: base.y - 10 });
		expect(written).toContainEqual({ text: 'Winter', x: winter.x + 10 + 4 * 6, y: winter.y + 20 });
		expect(written.map((w) => w.text)).toEqual(
			expect.arrayContaining(['Base', '2', 'Base case', 'Winter'])
		);
		expect(written.some((w) => w.text.includes('['))).toBe(false);
	});

	// Review CASE-NUMBERS-B1 (rule 4: "the name follows the box where it fits"): a label that would
	// run past the plot's right edge is its number alone, never a name cut at the canvas's edge. On
	// e5e6558 the one-off's case 2 at 1280 px read "[2] Pump PB", the name of the pump that is off in
	// it, and the lineups image cut "[6] 2 of 4 running (Pump P3, Pump P4 of".
	it('draws a ring’s name after its number only where the whole label fits in the plot, else its number alone', () => {
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
			const config = pumpChartConfig(data, cases, {
				speedText: '100 %',
				legendLabels,
				format,
				...options
			});
			const sets = config.data.datasets as unknown as Dataset[];
			const written: { text: string; x: number; align: string }[] = [];
			const boxes: { x: number; w: number }[] = [];
			const ctx = {
				font: '',
				fillStyle: '',
				strokeStyle: '',
				lineWidth: 1,
				textAlign: 'start',
				textBaseline: 'alphabetic',
				save() {},
				restore() {},
				measureText: (text: string) => ({ width: text.length * 6 }),
				beginPath() {},
				roundRect: (x: number, _y: number, w: number) => boxes.push({ x: x - 0.5, w: w + 1 }),
				fill() {},
				stroke() {},
				fillText(text: string, x: number) {
					written.push({ text, x, align: this.textAlign });
				}
			};
			const chart = {
				ctx,
				chartArea: plot,
				data: config.data,
				isDatasetVisible: () => true,
				getDatasetMeta: (i: number) => {
					const tag = /^\[(\d+)\]/.exec(sets[i]!.caseLabel ?? '')?.[1];
					return {
						data: (sets[i]!.data as unknown[]).map(() => ({ x: ringX[tag!] ?? 60, y: 150 }))
					};
				}
			};
			const plugin = config.plugins!.find((p) => p.id === 'caseLabels')!;
			plugin.afterDatasetsDraw!(chart as never, {} as never, {} as never, undefined as never);
			return { written, boxes };
		};
		for (const forImage of [false, true]) {
			const { written, boxes } = draw({ forImage });
			// No name is cut: the names left out are not written at all, and nothing passes the edge.
			const words = written.filter((w) => w.align !== 'center');
			for (const w of words)
				expect(w.x + w.text.length * 6, w.text).toBeLessThanOrEqual(plot.right);
			expect(words.map((w) => w.text)).toEqual(['Pump PA off']);
			// Case 1 fits whole, right of its ring: "[1] Pump PA off" is 90 px, 110 to 200.
			expect(boxes[0]).toEqual({ x: 110, w: 18 });
			expect(written).toContainEqual({ text: 'Pump PA off', x: 110 + 24, align: 'start' });
			// Case 2's whole label would end at 430 + 90 = 520, past 500: its number alone, right of it.
			expect(boxes[1]).toEqual({ x: 430, w: 18 });
			// Case 3's number alone would end at 495 + 18 = 513: left of its ring, 457 to 475.
			expect(boxes[2]).toEqual({ x: 485 - 10 - 18, w: 18 });
			expect(boxes).toHaveLength(3);
			for (const b of boxes) expect(b.x + b.w).toBeLessThanOrEqual(plot.right);
			// Each box holds its number.
			expect(written.filter((w) => w.align === 'center').map((w) => w.text)).toEqual([
				'1',
				'2',
				'3'
			]);
		}
		// A phone's screen: each number alone, the one at the edge left of its ring.
		const phone = draw({ compactLabels: true });
		expect(phone.boxes).toEqual([
			{ x: 110, w: 18 },
			{ x: 430, w: 18 },
			{ x: 457, w: 18 }
		]);
		expect(phone.written.filter((w) => w.align !== 'center')).toEqual([]);
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
