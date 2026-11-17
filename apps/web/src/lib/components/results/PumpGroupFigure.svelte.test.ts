/**
 * The group chart's figure with pumps as named dots (owner, 2026-11-12, nit 5; Q1 "Shapes go too";
 * docs/proposals/pumps-nits.md item 5, rules 1, 2, 7 and 8; slice 5c), drawn through the Pumps
 * together card as PumpGroupChart.svelte.test.ts draws it (Chart.js replaced by a recorder; the
 * shared fixture's real API answers):
 * - the legend's swatches drawn from the canvas's mark spec (chart-marks.ts), no entry for a
 *   member's point and no character;
 * - "Each pump's point" names each pump as typed, with no mark before it;
 * - a label the placer leaves out is named in the notes with its values, never only counted.
 */
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type {
	Flag,
	Project,
	PumpGroupCurveResponse,
	PumpResult,
	SolvedState,
	SolveResponse
} from '$lib/api/types';
import type { GroupCurveState } from '$lib/state/project.svelte';
import {
	drawnChart,
	lineupAnswers,
	lineupOn,
	lineupPrefs,
	lineups,
	lineupView,
	readyState
} from '$lib/testing/curve-family';
import { designators } from '$lib/testing/helpers';
import type { ChartImageSource, FigureImageRequest } from '$lib/utils/export/chart-image';
import { fakeResizeObserver } from '$lib/testing/resize';
import fixture from '$lib/utils/__fixtures__/pump-groups-input.json';
import type { PumpChartConfig } from '$lib/utils/pump-chart-config';
import { caseTagOf, caseTags, ratedCurveRange } from '$lib/utils/pump-chart';
import type { GroupMemberInput } from '$lib/utils/pump-group-chart';
import { otherGroupCases, type OtherGroupCase } from '$lib/utils/pump-group-one-off';
import { formatNumber } from '$lib/utils/units';
import PumpGroupChart from './PumpGroupChart.svelte';

const charts = vi.hoisted(() => [] as { config: unknown; destroyed: boolean; draws: number }[]);
const images = vi.hoisted(() => ({ requests: [] as unknown[] }));

vi.mock('./chart-setup', async () => ({
	pumpGroupConfig: (await import('$lib/utils/pump-chart-config')).pumpGroupConfig,
	Chart: class {
		static defaults = { plugins: { legend: { labels: { generateLabels: () => [] } } } };
		record: { config: unknown; destroyed: boolean; draws: number };
		constructor(_context: unknown, config: unknown) {
			this.record = { config, destroyed: false, draws: 0 };
			charts.push(this.record);
		}
		draw() {
			this.record.draws++;
		}
		destroy() {
			this.record.destroyed = true;
		}
	},
	downloadChartImage: async (_chart: unknown, request: unknown) =>
		void images.requests.push(request),
	IMAGE_REASONS_IN: 'made-up place says'
}));

const getContext = HTMLCanvasElement.prototype.getContext;
let observers: ReturnType<typeof fakeResizeObserver>;
beforeEach(() => {
	charts.length = 0;
	images.requests.length = 0;
	HTMLCanvasElement.prototype.getContext = (() => ({})) as unknown as typeof getContext;
	observers = fakeResizeObserver();
});
afterEach(() => {
	HTMLCanvasElement.prototype.getContext = getContext;
	observers.restore();
	localStorage.clear();
});

interface FixtureCase {
	name: string;
	project: Project;
	memberIds: string[];
	solve: SolveResponse & { solvedState: SolvedState };
	groupCurve: { status: number; body: unknown };
	systemCurve: { status: number; body: unknown } | null;
	scenarioCases?: Record<string, { solve: SolveResponse; groupCurve: { body: unknown } }>;
}
const named = (name: string) =>
	(fixture.cases as unknown as FixtureCase[]).find((c) => c.name === name)!;

function pumpsOf(c: FixtureCase): Omit<GroupMemberInput, 'slot'>[] {
	const s = c.solve.solvedState;
	return Object.keys(s.pumpResults).map((id) => {
		const pump = c.project.components.find((x) => x.id === id)!;
		return {
			id,
			name: pump.name,
			result: s.pumpResults[id] as PumpResult,
			ratedRange: ratedCurveRange(c.project, id),
			curveId: pump.type === 'pump' ? pump.curveId : null,
			flags: (s.flags as Flag[]).filter((f) => f.componentId === id)
		};
	});
}
const ready = (body: unknown): GroupCurveState => ({
	status: 'ready',
	response: body as PumpGroupCurveResponse
});
function props(c: FixtureCase, values: Record<string, unknown> = {}) {
	return {
		pumps: pumpsOf(c),
		slots: c.memberIds,
		prefs: c.project.settings.units,
		project: c.project,
		nodes: c.solve.solvedState.nodeResults,
		open: true,
		curve: ready(c.groupCurve.body),
		...values
	};
}
/** The card for the `lineups` station, its base case shown, the other cases' rings on. */
function lineupsProps() {
	const view = lineupView('');
	const { groupCurve, systemCurve, solve } = lineupAnswers('');
	return {
		pumps: view.members.map(({ id, name, result, ratedRange, curveId, flags }) => ({
			id,
			name,
			result,
			ratedRange,
			curveId,
			flags
		})),
		slots: lineups.memberIds,
		prefs: lineupPrefs,
		project: lineups.project,
		nodes: solve.solvedState.nodeResults,
		open: true,
		curve: readyState(groupCurve),
		system: readyState(systemCurve),
		otherCases: view.others,
		tags: caseTags(lineups.project),
		caseTag: caseTagOf(caseTags(lineups.project), ''),
		othersOn: true,
		onothers: () => {},
		shownOn: lineupOn(''),
		caseName: 'Base case'
	};
}
/** The `one-off` card, its base case shown, with its four scenarios' rings, every one ready. */
function oneOffProps() {
	const c = named('one-off');
	const station = (c.groupCurve.body as PumpGroupCurveResponse).station;
	const ids = ['S1', 'S2', 'S3', 'S4'];
	const others: OtherGroupCase[] = otherGroupCases({
		valued: ids.map((id) => ({
			key: id,
			caseId: id,
			name: c.project.scenarios!.find((s) => s.id === id)!.name,
			stale: false,
			group: ready(c.scenarioCases![id]!.groupCurve.body),
			system: undefined,
			shared: id !== 'S3',
			solved: null
		})),
		tags: caseTags(c.project),
		shownKeys: new Set(ids),
		othersOn: true,
		shownSettled: true,
		station,
		systemShown: c.systemCurve!.body as PumpGroupCurveResponse,
		memberIds: ['PA', 'PB'],
		project: c.project,
		boxes: ['PA', 'PB']
	});
	return props(c, {
		system: ready(c.systemCurve!.body),
		caseName: 'Base case',
		tags: caseTags(c.project),
		otherCases: others,
		othersOn: true,
		onothers: () => {}
	});
}
/** The chart was drawn (its chunk is imported first: slow on a loaded machine). */
async function renderDrawn(values: Record<string, unknown>) {
	const before = charts.length;
	const view = render(PumpGroupChart, values);
	await vi.waitFor(() => expect(charts).toHaveLength(before + 1), { timeout: 10_000 });
	return view;
}
const f4 = (v: number) => formatNumber(v, 4);

describe('the legend’s swatches from the canvas’s mark spec (rule 8)', () => {
	it('draws the Group’s ink dot and each ring as the canvas draws them, lists no member’s point and writes no character', async () => {
		await renderDrawn(lineupsProps());
		// The canvas's marks, as the chart was configured (chart-marks.ts's spec:
		// utils/chart-marks.test.ts holds the canvas to it).
		const sets = (charts.at(-1)!.config as PumpChartConfig).data.datasets as unknown as Record<
			string,
			unknown
		>[];
		const drawn = (d: Record<string, unknown>) => ({
			radius: d.pointRadius,
			border: d.borderWidth,
			fill: d.backgroundColor,
			stroke: d.borderColor
		});
		const groupMark = drawn(sets.find((d) => /^Group( \(crossing\))?$/.test(String(d.caseLabel)))!);
		const ringMark = drawn(sets.find((d) => d.otherCase === true)!);
		const legend = within(screen.getByRole('figure')).getByRole('list', { name: 'Legend' });
		const items = within(legend).getAllByRole('listitem');
		const text = (li: HTMLElement) => li.textContent!.replace(/\s+/g, ' ').trim();
		// Rule 1: no character in the legend; rule 2: a member's point is named on the chart, so
		// the legend has no entry for it (its line's entry names it: "Pump P1, Pump P2, …").
		expect(designators(legend)).toEqual([]);
		for (const name of ['Pump P1', 'Pump P2', 'Pump P3', 'Pump P4'])
			expect(items.map(text), name).not.toContain(name);
		/** An entry's swatch, drawn as the canvas draws its mark: its circle and its box. */
		const swatch = (li: HTMLElement) => {
			const svg = li.querySelector('svg');
			const circle = svg?.querySelector('circle');
			expect(svg?.getAttribute('aria-hidden'), text(li)).toBe('true');
			expect(circle, text(li)).not.toBeNull();
			return {
				mark: {
					radius: Number(circle!.getAttribute('r')),
					border: Number(circle!.getAttribute('stroke-width')),
					fill: circle!.getAttribute('fill'),
					stroke: circle!.getAttribute('stroke')
				},
				width: Number(svg!.getAttribute('width')),
				height: Number(svg!.getAttribute('height')),
				cx: Number(circle!.getAttribute('cx')),
				cy: Number(circle!.getAttribute('cy'))
			};
		};
		/** The whole mark, its border's outer half too, inside its box and centred in it. */
		const whole = (s: ReturnType<typeof swatch>, where: string) => {
			const r = s.mark.radius + s.mark.border / 2;
			expect(s.width, where).toBeGreaterThanOrEqual(2 * r);
			expect(s.height, where).toBeGreaterThanOrEqual(2 * r);
			expect(s.cx, where).toBe(s.width / 2);
			expect(s.cy, where).toBe(s.height / 2);
		};
		// Rule 3: the legend entry starts with "Group", its swatch the ink dot.
		const group = items.filter((li) => text(li).startsWith('Group duty'));
		expect(group).toHaveLength(1);
		const dot = swatch(group[0]!);
		expect(dot.mark).toEqual(groupMark);
		whole(dot, 'the Group');
		// Each other case's ring: the slate ring.
		const rings = items.filter((li) => /^Cases? \d/.test(text(li)));
		expect(rings.length).toBeGreaterThan(0);
		for (const li of rings) {
			const ring = swatch(li);
			expect(ring.mark, text(li)).toEqual(ringMark);
			whole(ring, text(li));
		}
	});
});

describe('“Each pump’s point”: each pump its name (rules 1 and 2)', () => {
	it('names each pump as typed, a held one too, with no mark before it', async () => {
		for (const [c, names] of [
			[named('parallel-ideal'), ['Pump PA', 'Pump PB']],
			[named('dead-headed'), ['Pump PA', 'Pump PB']]
		] as const) {
			const view = render(PumpGroupChart, props(c));
			await fireEvent.click(
				screen.getByRole('button', { name: 'Show data table of the group chart' })
			);
			const table = screen.getByRole('table', { name: "Each pump's point (flow through it)" });
			expect(designators(table), c.name).toEqual([]);
			const heads = within(table)
				.getAllByRole('rowheader')
				.map((h) => h.textContent!.replace(/\s+/g, ' ').trim());
			expect(heads, c.name).toEqual(names);
			view.unmount();
			localStorage.clear();
		}
	});
});

describe('a label left out is named in the notes, with its values (rule 7)', () => {
	it('names each label its drawing left out, the ring by its case and name, never only a count', async () => {
		await renderDrawn(oneOffProps());
		const config = charts.at(-1)!.config as PumpChartConfig;
		// A plot 20 px square: no label has a place, so every one is left out.
		drawnChart(config, { plot: { left: 50, right: 70, top: 10, bottom: 30 } }).draw();
		const canvas = document.querySelector('[data-pumps-together] canvas') as HTMLCanvasElement;
		await vi.waitFor(() => expect(canvas.dataset.pointLabels).toBeDefined());
		const placed = JSON.parse(canvas.dataset.pointLabels!) as {
			labels: unknown[];
			leftOut: unknown[];
		};
		expect(placed.labels).toEqual([]);
		expect(placed.leftOut.length).toBeGreaterThan(0);
		const note = await screen.findByText(/^Not labelled on the chart: /);
		expect(note).toBeVisible();
		const words = note.textContent!;
		// The plan's words for a ring: its case, its name, its place.
		expect(words).toContain('case 2, Pump PB off, its ring at 40.75 L/s and 23.68 m');
		// Each pump by its name and its point's values.
		const c = named('one-off');
		for (const id of ['PA', 'PB']) {
			const r = c.solve.solvedState.pumpResults[id] as PumpResult;
			const name = id === 'PA' ? 'Pump PA' : 'Pump PB';
			expect(words, name).toMatch(
				new RegExp(`${name}\\b[^;]*${f4(r.operatingFlow * 1000)} L/s and ${f4(r.operatingHead)} m`)
			);
		}
		expect(designators(words)).toEqual([]);
	});
});

describe('the image names the points its own drawing left unlabelled (rule 7)', () => {
	it('reads them once the image is drawn: none with room, each with its values where crowded', async () => {
		const image: ChartImageSource = {
			projectName: 'Booster station',
			timestamp: '2026-11-12T09:30:00Z',
			methodVersion: '1.6.0',
			stale: false,
			unavailable: '',
			origin: 'https://opensolve-pipe.app',
			notify: () => {}
		};
		await renderDrawn({ ...oneOffProps(), image });
		await fireEvent.click(
			screen.getByRole('button', { name: /^Download image of the pumps together/ })
		);
		await vi.waitFor(() => expect(images.requests).toHaveLength(1));
		const request = images.requests[0] as FigureImageRequest;
		const unlabelled = (lines: readonly string[]) =>
			lines.filter((l) => l.startsWith('Not labelled on the chart: '));
		// Before the image's chart is drawn, and on the screen's notes: no point named.
		expect(unlabelled(request.lines)).toEqual([]);
		expect(unlabelled(request.drawnLines!())).toEqual([]);
		// Drawn in a plot 20 px square: every point's label left out, each named with its values.
		drawnChart(request.config, { plot: { left: 50, right: 70, top: 10, bottom: 30 } }).draw();
		const [line] = unlabelled(request.drawnLines!());
		expect(line).toContain('case 2, Pump PB off, its ring at 40.75 L/s and 23.68 m');
		expect(line).toMatch(/^Not labelled on the chart: Group, its point at /);
		expect(designators(line!)).toEqual([]);
		// The rest of the lines as the screen's, the named points after the dashed note.
		expect(request.drawnLines!().filter((l) => l !== line)).toEqual(request.lines);
		// Drawn with room: every point labelled, no line.
		drawnChart(request.config, { plot: { left: 50, right: 1500, top: 10, bottom: 900 } }).draw();
		expect(unlabelled(request.drawnLines!())).toEqual([]);
	});
});
