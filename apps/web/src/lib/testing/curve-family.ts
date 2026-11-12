/**
 * The curve family's test views (CLAUDE.md D24 slice L3, proposal pump-lineups.md §10.3): the
 * Pumps together card's inputs for one case of the shared fixture's `lineups` station shown, with
 * the other cases as PumpsView gives them (each case as solved, its rest and its inside compared
 * with the shown case's by the app's own functions, its members switched on read by pumpLineup,
 * in number order with the project's case numbers, caseTags, ticked as chartKeys takes them by
 * lineupChartPriority; nit 5, slice 5b). Every response is the fixture's real API answer
 * (apps/api/tests/fixtures/pump_groups_input.py). Not used by the app.
 *
 * With the UI half: drawnChart, a stand-in for the Chart.js instance the chart's label plugin is
 * given (the unit projects have no canvas), mapping each dataset's points to pixels linearly over
 * the axes the configuration sets, or its data's extent, and recording the text and the boxes
 * written (a case tag's box, pump-chart-config.ts fillLabel).
 */
import type {
	Flag,
	Project,
	PumpGroupCurveResponse,
	PumpResult,
	SolveResponse
} from '../api/types';
import { hydraulicFingerprint, type GroupCurveState } from '../state/project.svelte';
import fixture from '../utils/__fixtures__/pump-groups-input.json';
import { caseTags, inCaseOrder, ratedCurveRange } from '../utils/pump-chart';
import type { ChartDatum, PumpChartConfig } from '../utils/pump-chart-config';
import {
	groupChartData,
	type GroupChartData,
	type GroupMemberInput,
	type PxBox
} from '../utils/pump-group-chart';
import {
	chartKeys,
	groupCurveDrawn,
	otherGroupCases,
	sameInside,
	sharedRest,
	type OtherCasesInput,
	type OtherGroupCase
} from '../utils/pump-group-one-off';
import { pumpLineup } from '../utils/pump-lineups';
import { applyScenario } from '../utils/scenarios';

export interface Answer {
	status: number;
	body: unknown;
}
export interface FixtureCase {
	name: string;
	project: Project;
	memberIds: string[];
	solve: SolveResponse;
	groupCurve: Answer;
	systemCurve: Answer | null;
	scenarioCases?: Record<string, { solve: SolveResponse; groupCurve: Answer; systemCurve: Answer }>;
}

export const fixtureCases = fixture.cases as unknown as FixtureCase[];
export const fixtureCase = (name: string) => fixtureCases.find((c) => c.name === name)!;
export const answer = (a: Answer) => a.body as PumpGroupCurveResponse;
export const readyState = (a: Answer): GroupCurveState => ({
	status: 'ready',
	response: answer(a)
});

/** Four pumps on Crane tees: by number running (S1–S3), each pump off (S4–S6), S7 and S8. */
export const lineups = fixtureCase('lineups');
/** Every case of `lineups`: the base ('') and its eight scenarios. */
export const LINEUP_KEYS = ['', 'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8'] as const;
export const lineupStation = answer(lineups.groupCurve).station;
export const lineupPrefs = lineups.project.settings.units;

/** A case's solve, group curve and group system curve. */
export function lineupAnswers(key: string) {
	return key === ''
		? { solve: lineups.solve, groupCurve: lineups.groupCurve, systemCurve: lineups.systemCurve! }
		: lineups.scenarioCases![key]!;
}
/** A case as solved (store.caseInputs): the base, or the scenario applied to it. */
export const lineupSolved = (key: string): Project =>
	key === '' ? lineups.project : applyScenario(lineups.project, key).project;
export const lineupCaseName = (key: string) =>
	key === '' ? 'Base case' : lineups.project.scenarios!.find((s) => s.id === key)!.name;
/** The members switched on in a case as solved (D24 §9.1's k). */
export const lineupOn = (key: string) =>
	pumpLineup(undefined, lineupSolved(key), lineups.memberIds).on.length;

/** The card's members for a case shown: its solve's results, slots in member order. */
export function lineupMembers(shown: string): GroupMemberInput[] {
	const { solve } = lineupAnswers(shown);
	return lineups.memberIds.map((id, slot) => {
		const pump = lineups.project.components.find((x) => x.id === id)!;
		return {
			id,
			name: pump.name,
			result: solve.solvedState.pumpResults[id] as PumpResult,
			ratedRange: ratedCurveRange(lineupSolved(shown), id),
			curveId: pump.type === 'pump' ? pump.curveId : null,
			slot,
			flags: (solve.solvedState.flags as Flag[]).filter((f) => f.componentId === id)
		};
	});
}

export interface LineupViewOptions {
	/** Cases unticked under "Cases on this chart". */
	unticked?: readonly string[];
	/** Cases whose results are out of date. */
	stale?: readonly string[];
	/** Leave out `inside` and `on` (4d's inputs): no curve states. */
	without?: boolean;
	/** Each valued case's input changed (synthetic edits, named by the test). */
	edit?: (v: OtherCasesInput['valued'][number]) => OtherCasesInput['valued'][number];
}

/** The other cases' input with `shown` shown, as PumpsView builds it. */
export function lineupInput(shown: string, options: LineupViewOptions = {}): OtherCasesInput {
	const { unticked = [], stale = [], without = false, edit = (v) => v } = options;
	const keys = LINEUP_KEYS.filter((k) => k !== shown).map((key) => ({ key, caseId: key || null }));
	const members = lineups.memberIds;
	const tags = caseTags(lineups.project);
	const order = inCaseOrder(keys, tags).map((k) => k.key);
	const shownSolved = lineupSolved(shown);
	const shownAnswers = lineupAnswers(shown);
	return {
		valued: order.map((key) =>
			edit({
				key,
				caseId: key || null,
				name: lineupCaseName(key),
				stale: stale.includes(key),
				group: readyState(lineupAnswers(key).groupCurve),
				system: undefined,
				shared: sharedRest(shownSolved, lineupSolved(key), lineupStation, hydraulicFingerprint),
				solved: lineupSolved(key),
				...(without
					? {}
					: {
							inside: sameInside(
								shownSolved,
								lineupSolved(key),
								lineupStation,
								hydraulicFingerprint
							),
							on: lineupOn(key)
						})
			})
		),
		tags,
		shownKeys: new Set(chartKeys(keys, lineups.project, members, unticked)),
		othersOn: true,
		shownSettled: true,
		station: lineupStation,
		systemShown: answer(shownAnswers.systemCurve),
		memberIds: members,
		project: lineups.project,
		boxes: members,
		curveDrawn: groupCurveDrawn(readyState(shownAnswers.groupCurve))
	};
}

export interface LineupView {
	input: OtherCasesInput;
	others: OtherGroupCase[];
	members: GroupMemberInput[];
	response: PumpGroupCurveResponse;
	system: PumpGroupCurveResponse;
	data: GroupChartData;
}

/** The card's chart data with `shown` shown and the other cases as PumpsView gives them. */
export function lineupView(shown: string, options: LineupViewOptions = {}): LineupView {
	const input = lineupInput(shown, options);
	const others = otherGroupCases(input);
	const members = lineupMembers(shown);
	const { groupCurve, systemCurve } = lineupAnswers(shown);
	const response = answer(groupCurve);
	const system = answer(systemCurve);
	const data = groupChartData(members, lineupPrefs, response, system, others, lineupOn(shown));
	return { input, others, members, response, system, data };
}

/** A plot for drawnChart (px): about the 390 px phone's (m4_labels.py's). */
export const TEST_PLOT: PxBox = { left: 50, right: 330, top: 10, bottom: 210 };

/** Text written on the stand-in canvas: where, in which colour and font. */
export interface Written {
	text: string;
	x: number;
	y: number;
	color: string;
	font: string;
	/** The alignment it was written with ('start' unless set). */
	align: string;
}

/** A box drawn on the stand-in canvas (a rect or roundRect path), its fill and its edge. */
export interface DrawnBox {
	x: number;
	y: number;
	w: number;
	h: number;
	fill: string | null;
	stroke: string | null;
	lineWidth: number | null;
}

/**
 * A stand-in for the chart drawn from `config` on `plot`: Chart.js's pixels as a linear map of
 * the axes (the configuration's min and max where set, else 0 to the data's largest value), a
 * context whose text is `charWidth` px a character, and every text written. `draw()` runs the
 * configuration's label plugin, as Chart.js does after drawing the datasets.
 */
export function drawnChart(
	config: PumpChartConfig,
	{ plot = TEST_PLOT, charWidth = 6 }: { plot?: PxBox; charWidth?: number } = {}
) {
	const sets = config.data.datasets as unknown as { data: ChartDatum[] }[];
	const drawnPoints = sets.flatMap((d) => d.data.filter((p) => p.y !== null));
	const scales = (config.options?.scales ?? {}) as Record<string, { min?: number; max?: number }>;
	const range = (id: 'x' | 'y', values: number[]) => ({
		min: scales[id]?.min ?? Math.min(0, ...values),
		max: scales[id]?.max ?? Math.max(...values)
	});
	const x = range(
		'x',
		drawnPoints.map((p) => p.x)
	);
	const y = range(
		'y',
		drawnPoints.map((p) => p.y!)
	);
	const px = (v: number) => plot.left + ((v - x.min) / (x.max - x.min)) * (plot.right - plot.left);
	const py = (v: number) =>
		plot.bottom - ((v - y.min) / (y.max - y.min)) * (plot.bottom - plot.top);
	const written: Written[] = [];
	const boxes: DrawnBox[] = [];
	let path: DrawnBox | null = null;
	const ctx = {
		fillStyle: '',
		strokeStyle: '',
		lineWidth: 1,
		font: '',
		textAlign: 'start',
		textBaseline: 'alphabetic',
		save() {},
		restore() {},
		measureText: (text: string) => ({ width: text.length * charWidth }),
		fillText(text: string, tx: number, ty: number) {
			written.push({
				text,
				x: tx,
				y: ty,
				color: this.fillStyle,
				font: this.font,
				align: this.textAlign
			});
		},
		beginPath() {
			path = null;
		},
		rect(bx: number, by: number, w: number, h: number) {
			path = { x: bx, y: by, w, h, fill: null, stroke: null, lineWidth: null };
			boxes.push(path);
		},
		roundRect(bx: number, by: number, w: number, h: number) {
			this.rect(bx, by, w, h);
		},
		fill() {
			if (path) path.fill = this.fillStyle;
		},
		stroke() {
			if (path) {
				path.stroke = this.strokeStyle;
				path.lineWidth = this.lineWidth;
			}
		}
	};
	const chart = {
		ctx,
		chartArea: { ...plot },
		data: config.data,
		scales: { x, y },
		isDatasetVisible: () => true,
		getDatasetMeta: (i: number) => ({
			data: sets[i]!.data.map((p) => ({ x: px(p.x), y: p.y === null ? Number.NaN : py(p.y) }))
		})
	};
	const draw = () => {
		const plugin = config.plugins!.find((p) => p.id === 'groupLabels')!;
		plugin.afterDatasetsDraw!(chart as never, {} as never, {} as never, undefined as never);
	};
	/**
	 * A label as fillLabel writes it, found by its text ("[1] 3 running", "Pump PA"): its left end,
	 * its baseline, the colour and font of its words. A case tag's box must be there, `charWidth`
	 * a character of its bracketed text wide, from the font's size above the baseline to a quarter
	 * of it below, white with a slate edge, its numbers written centred in it; else undefined.
	 */
	const label = (text: string): Written | undefined => {
		const tagged = /^\[([^\]]+)\](?: (.*))?$/s.exec(text);
		if (!tagged) return written.find((w) => w.text === text);
		const [, tag, words = ''] = tagged;
		const width = (tag!.length + 2) * charWidth;
		const after = (tag!.length + 3) * charWidth;
		for (const box of boxes) {
			const x0 = box.x - 0.5;
			const number = written.find(
				(w) => w.text === tag && w.align === 'center' && Math.abs(w.x - (x0 + width / 2)) < 1e-9
			);
			if (!number || Math.abs(box.w - (width - 1)) > 1e-9) continue;
			const size = Number(/(\d+)px/.exec(number.font)?.[1]) + 2;
			const y = number.y + 1;
			if (Math.abs(box.y - 0.5 - (y - size)) > 1e-9) continue;
			if (Math.abs(box.h - (size * 1.25 - 1)) > 1e-9) continue;
			if (box.fill !== '#ffffff' || box.stroke !== '#475569' || box.lineWidth !== 1) continue;
			if (!words) return { ...number, text, x: x0, y, align: 'start' };
			const rest = written.find(
				(w) => w.text === words && Math.abs(w.x - (x0 + after)) < 1e-9 && w.y === y
			);
			if (rest) return { ...rest, text, x: x0 };
		}
		return undefined;
	};
	return { chart, written, boxes, label, px, py, x, y, draw };
}
