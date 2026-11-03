/**
 * Other cases' station duties on the Pumps together chart (CLAUDE.md D21 slice 4d): the rings
 * (their points, numbers, labels and merging within the duty checks' tolerances), the legend,
 * the accessible name, the notes and the image's footer, and the chart configuration (slate
 * rings drawn on top with a transparent fill, labelled in slate, listed last in the image's
 * legend; nothing else changes without rings). The duties are the shared fixture's real API
 * answers for the `one-off` case's scenarios.
 */
import { describe, expect, it } from 'vitest';
import type {
	Flag,
	Project,
	PumpGroupCurveResponse,
	PumpResult,
	SolveResponse
} from '$lib/api/types';
import type { GroupCurveState } from '$lib/state/project.svelte';
import fixture from './__fixtures__/pump-groups-input.json';
import { ratedCurveRange } from './pump-chart';
import { CHART_COLORS, pumpGroupConfig, type PumpChartConfig } from './pump-chart-config';
import {
	DUTY_CLAIM_RULE,
	GROUP_OTHER,
	groupChartData,
	groupLegend,
	groupNoteLines,
	groupNotes,
	groupSummary,
	OTHER_SYMBOL,
	stationResponse,
	type GroupMemberInput
} from './pump-group-chart';
import { otherGroupCases, type OtherGroupCase } from './pump-group-one-off';
import { applyScenario } from './scenarios';
import { formatNumber } from './units';

interface Answer {
	status: number;
	body: unknown;
}
interface FixtureCase {
	name: string;
	project: Project;
	memberIds: string[];
	solve: SolveResponse;
	groupCurve: Answer;
	systemCurve: Answer | null;
	scenarioCases?: Record<string, { solve: SolveResponse; groupCurve: Answer; systemCurve: Answer }>;
}
const cases = fixture.cases as unknown as FixtureCase[];
const oneOff = cases.find((c) => c.name === 'one-off')!;
const body = (a: Answer) => a.body as PumpGroupCurveResponse;
const group = body(oneOff.groupCurve);
const system = body(oneOff.systemCurve!);
const prefs = oneOff.project.settings.units;
const f4 = (v: number) => formatNumber(v, 4);
const ready = (a: Answer): GroupCurveState => ({ status: 'ready', response: body(a) });
const scenario = (id: string) => oneOff.scenarioCases![id]!;
const nameOf = (id: string) => oneOff.project.scenarios!.find((s) => s.id === id)!.name;

const members: GroupMemberInput[] = oneOff.memberIds.map((id, slot) => {
	const pump = oneOff.project.components.find((x) => x.id === id)!;
	return {
		id,
		name: pump.name,
		result: oneOff.solve.solvedState.pumpResults[id] as PumpResult,
		ratedRange: ratedCurveRange(oneOff.project, id),
		curveId: pump.type === 'pump' ? pump.curveId : null,
		slot,
		flags: (oneOff.solve.solvedState.flags as Flag[]).filter((f) => f.componentId === id)
	};
});

/** The `one-off` scenarios as the card has them, every one ready (S3 another rest). */
function others(ids = ['S1', 'S2', 'S3', 'S4']): OtherGroupCase[] {
	return otherGroupCases({
		valued: ids.map((id) => ({
			key: id,
			caseId: id,
			name: nameOf(id),
			stale: false,
			group: ready(scenario(id).groupCurve),
			system: undefined,
			shared: id !== 'S3',
			solved: applyScenario(oneOff.project, id).project
		})),
		shownKeys: new Set(ids),
		othersOn: true,
		shownSettled: true,
		station: group.station,
		systemShown: system,
		memberIds: oneOff.memberIds,
		project: oneOff.project,
		boxes: oneOff.memberIds
	});
}
const duty = (id: string) => body(scenario(id).groupCurve).duty!;
/** A case of the chart with its duty moved (synthetic). */
const moved = (o: OtherGroupCase, flow: number, head: number): OtherGroupCase => ({
	...o,
	duty: { flow, head }
});

describe('the rings', () => {
	it('puts each case drawn at its duty, in display units, numbered in case order', () => {
		const data = groupChartData(members, prefs, group, system, others());
		expect(data.others.map((r) => [r.numbers, r.names, r.label, r.tag, r.short])).toEqual([
			[[1], ['Pump PA off'], '1 · Pump PA off (station duty)', '1 · Pump PA off', '1'],
			[[2], ['Pump PB off'], '2 · Pump PB off (station duty)', '2 · Pump PB off', '2'],
			[
				[3],
				['Delivery tank 5 m higher'],
				'3 · Delivery tank 5 m higher (station duty)',
				'3 · Delivery tank 5 m higher',
				'3'
			],
			[[4], ['Both pumps off'], '4 · Both pumps off (station duty)', '4 · Both pumps off', '4']
		]);
		expect(data.others[0]!.point).toEqual({ x: duty('S1').flow * 1000, y: duty('S1').head });
		expect(data.others[1]!.point).toEqual({ x: duty('S2').flow * 1000, y: duty('S2').head });
		// A ring's case: the flow as words give it (0 below the duty check's floor).
		expect(data.others[3]!.cases[0]!.flow).toBe(0);
		// No rings without other cases, nor for a case not drawn.
		expect(groupChartData(members, prefs, group, system).others).toEqual([]);
		const off = others().map((o) => ({ ...o, state: 'off' as const, number: null }));
		expect(groupChartData(members, prefs, group, system, off).others).toEqual([]);
	});

	it('shares one ring between duties within the duty checks’ tolerances, keeping the first’s point', () => {
		const [s1, s2] = others(['S1', 'S2']);
		const q = duty('S1').flow;
		const h = duty('S1').head;
		const near = groupChartData(members, prefs, group, system, [s1!, moved(s2!, q * 1.004, h)]);
		expect(near.others).toHaveLength(1);
		expect(near.others[0]).toMatchObject({
			numbers: [1, 2],
			names: ['Pump PA off', 'Pump PB off'],
			label:
				"1, 2 · Pump PA off and Pump PB off (station duties, equal within the duty checks' tolerances)",
			tag: '1, 2 · Pump PA off, Pump PB off',
			short: '1, 2',
			point: { x: q * 1000, y: h }
		});
		const far = groupChartData(members, prefs, group, system, [s1!, moved(s2!, q * 1.006, h)]);
		expect(far.others.map((r) => r.numbers)).toEqual([[1], [2]]);
		// The rise's tolerance: 0.5 % or 0.01 m.
		const high = groupChartData(members, prefs, group, system, [s1!, moved(s2!, q, h * 1.006)]);
		expect(high.others).toHaveLength(2);
		// Three or more: two names on the chart, then a count.
		const [a, b, c] = others(['S1', 'S2', 'S3']);
		const three = groupChartData(members, prefs, group, system, [
			a!,
			moved(b!, q, h),
			moved(c!, q, h)
		]);
		expect(three.others[0]!.tag).toBe('1, 2, 3 · Pump PA off, Pump PB off and 1 more');
		expect(three.others[0]!.label).toBe(
			"1, 2, 3 · Pump PA off, Pump PB off and Delivery tank 5 m higher (station duties, equal within the duty checks' tolerances)"
		);
	});

	it('lists the rings in the legend after the station, in slate with their symbol', () => {
		const legend = groupLegend(groupChartData(members, prefs, group, system, others()));
		const station = legend.findIndex((i) => i.key === 'station');
		expect(legend.slice(station + 1)).toEqual(
			[1, 2, 3, 4].map((n) => ({
				key: `other-${n}`,
				label: expect.stringMatching(new RegExp(`^${n} · .* \\(station duty\\)$`)),
				kind: 'marker',
				color: GROUP_OTHER,
				symbol: OTHER_SYMBOL
			}))
		);
		expect(GROUP_OTHER).toBe(CHART_COLORS.slate);
		expect(OTHER_SYMBOL).toBe('○');
	});

	it('names every case drawn in the chart’s accessible name, with its claim', () => {
		const data = groupChartData(members, prefs, group, system, others());
		const summary = groupSummary(data, members, group, oneOff.project, system);
		const line = (id: string, n: number, flow: number, claim: string) =>
			`${n} · ${nameOf(id)}, ${f4(flow)} L/s at a rise of ${f4(duty(id).head)} m (${claim})`;
		expect(summary).toContain(
			`; other cases' station duties: ${[
				line('S1', 1, duty('S1').flow * 1000, 'Yes: the same rest of the network'),
				line('S2', 2, duty('S2').flow * 1000, 'Yes: the same rest of the network'),
				line(
					'S3',
					3,
					duty('S3').flow * 1000,
					'No: it changes the rest of the network; its own group system curve is not drawn'
				),
				line(
					'S4',
					4,
					0,
					'Not said: at zero station flow the rest can hold more than one state (D13)'
				)
			].join('; ')}; group curve shown; group system curve shown.`
		);
		expect(
			groupSummary(
				groupChartData(members, prefs, group, system),
				members,
				group,
				oneOff.project,
				system
			)
		).not.toContain('other cases');
	});
});

describe('the notes', () => {
	const notesOf = (list: OtherGroupCase[], withSystem = true) => {
		const state = ready(oneOff.groupCurve);
		const systemState = withSystem ? ready(oneOff.systemCurve!) : undefined;
		const data = groupChartData(members, prefs, group, withSystem ? system : null, list);
		return groupNotes({
			data,
			members,
			state,
			system: systemState,
			project: oneOff.project,
			prefs,
			others: list
		});
	};

	it('says what a ring is, when one is on the curve shown, lists the rings and the cases without one', () => {
		const list = others();
		// S4 unticked (synthetic): no ring, and the reason.
		list[3] = {
			...list[3]!,
			state: 'unticked',
			onChart: false,
			number: null,
			duty: null,
			claim: null,
			words: 'not on the chart (unticked under Cases on this chart)'
		};
		const notes = notesOf(list);
		expect(notes.others).toEqual([
			"Each numbered slate ring is another case's station duty: that case's station flow and its rise from Tee T1 (run inlet) to Tee T2 (run outlet). With a pump off, the station's flow is the running pumps' flow, so a ring lies below their curves by their losses on the way: it is not a pump's own point, and not on this case's group curve, which is drawn with this case's pumps running. Each pump's own flow and head in each case are in Running combinations.",
			DUTY_CLAIM_RULE,
			`Other cases on the chart (slate rings, numbered): 1 · Pump PA off, ${f4(duty('S1').flow * 1000)} L/s at a rise of ${f4(duty('S1').head)} m: Yes: the same rest of the network; 2 · Pump PB off, ${f4(duty('S2').flow * 1000)} L/s at a rise of ${f4(duty('S2').head)} m: Yes: the same rest of the network; 3 · Delivery tank 5 m higher, ${f4(duty('S3').flow * 1000)} L/s at a rise of ${f4(duty('S3').head)} m: No: it changes the rest of the network; its own group system curve is not drawn.`,
			'Not on the chart: Both pumps off (not on the chart (unticked under Cases on this chart)).'
		]);
		// The image's footer: after the system duty notes, before the members'.
		const lines = groupNoteLines(notes);
		const at = lines.indexOf(notes.others[0]!);
		expect(lines.slice(at, at + 4)).toEqual(notes.others);
		expect(lines.indexOf(notes.systemDuty.at(-1)!)).toBeLessThan(at);
	});

	it('leaves out the rule without a group system curve, and says nothing without other cases', () => {
		const notes = notesOf(others(['S1']), false);
		expect(notes.others).not.toContain(DUTY_CLAIM_RULE);
		expect(notes.others).toHaveLength(2);
		expect(notesOf([]).others).toEqual([]);
		// The 4a/4b notes are unchanged by the other cases.
		const { others: _with, ...rest } = notesOf(others());
		const { others: _without, ...plain } = notesOf([]);
		void _with;
		void _without;
		expect(rest).toEqual(plain);
	});

	it('takes the station shown from the group curve, else the group system curve with a duty', () => {
		expect(stationResponse(ready(oneOff.groupCurve), undefined)).toBe(group);
		expect(stationResponse({ status: 'loading' }, ready(oneOff.systemCurve!))).toBe(system);
		const noDuty = structuredClone(system);
		noDuty.duty = null;
		expect(stationResponse(undefined, { status: 'ready', response: noDuty })).toBeNull();
		expect(stationResponse(undefined, undefined)).toBeNull();
	});
});

describe('the chart configuration', () => {
	type Dataset = PumpChartConfig['data']['datasets'][number] & Record<string, unknown>;
	const config = (data: ReturnType<typeof groupChartData>, options = {}) =>
		pumpGroupConfig(data, { legendLabels: () => [], format: f4, ...options });
	const datasets = (cfg: PumpChartConfig) => cfg.data.datasets as Dataset[];

	it('draws each ring after the station, slate, hollow and on top, labelled in slate', () => {
		const data = groupChartData(members, prefs, group, system, others(['S1', 'S2']));
		const sets = datasets(config(data));
		const station = sets.findIndex((d) => d.label === data.station!.label);
		expect(sets.slice(station + 1).map((d) => d.label)).toEqual([
			'1 · Pump PA off (station duty)',
			'2 · Pump PB off (station duty)'
		]);
		expect(sets.at(-1)).toMatchObject({
			data: [data.others[1]!.point],
			borderColor: CHART_COLORS.slate,
			backgroundColor: 'transparent',
			borderWidth: 2,
			pointStyle: 'circle',
			pointRadius: 10,
			pointHoverRadius: 12,
			pointHitRadius: 12,
			showLine: false,
			order: -1,
			caseLabel: '2 · Pump PB off',
			labelColor: CHART_COLORS.slate,
			otherCase: true
		});
	});

	it('labels a ring by its number on a phone’s screen, never in the image', () => {
		const data = groupChartData(members, prefs, group, system, others(['S1']));
		expect(datasets(config(data, { compactLabels: true })).at(-1)!.caseLabel).toBe('1');
		expect(datasets(config(data, { compactLabels: true, forImage: true })).at(-1)!.caseLabel).toBe(
			'1 · Pump PA off'
		);
		expect(datasets(config(data)).at(-1)!.caseLabel).toBe('1 · Pump PA off');
	});

	it('lists the rings last in the image’s legend, the rest in their order', () => {
		const data = groupChartData(members, prefs, group, system, others(['S1', 'S2']));
		const sets = datasets(config(data));
		// Chart.js lists datasets by `order`: the rings (order −1) first.
		const sorted = [
			...sets.map((d, i) => ({ d, i })).filter(({ d }) => d.order === -1),
			...sets.map((d, i) => ({ d, i })).filter(({ d }) => d.order !== -1)
		];
		const cfg = config(data, {
			forImage: true,
			legendLabels: () => sorted.map(({ d, i }) => ({ text: d.label, datasetIndex: i }))
		});
		const labels = cfg.options!.plugins!.legend!.labels!.generateLabels!({
			data: cfg.data
		} as never).map((item) => item.text);
		expect(labels.slice(-2)).toEqual([
			'1 · Pump PA off (station duty)',
			'2 · Pump PB off (station duty)'
		]);
		expect(labels.slice(0, -2)).toEqual(sets.filter((d) => d.order !== -1).map((d) => d.label));
	});

	it('writes each label in its dataset’s colour (slate for a ring, ink otherwise)', () => {
		const data = groupChartData(members, prefs, group, system, others(['S1']));
		const cfg = config(data, { forImage: true });
		const sets = datasets(cfg);
		const written: [string, string][] = [];
		const ctx = {
			fillStyle: '',
			font: '',
			save() {},
			restore() {},
			measureText: () => ({ width: 10 }),
			fillText(text: string) {
				written.push([text, this.fillStyle]);
			}
		};
		const chart = {
			ctx,
			chartArea: { left: 0, right: 1000, top: 0, bottom: 1000 },
			data: cfg.data,
			isDatasetVisible: () => true,
			getDatasetMeta: (i: number) => ({
				data: (sets[i]!.data as unknown[]).map(() => ({ x: 100, y: 100 }))
			})
		};
		const plugin = cfg.plugins!.find((p) => p.id === 'groupLabels')!;
		plugin.afterDatasetsDraw!(chart as never, {} as never, {} as never, undefined as never);
		expect(written).toContainEqual(['1 · Pump PA off', CHART_COLORS.slate]);
		expect(written).toContainEqual(['Group (crossing)', CHART_COLORS.ink]);
		expect(written).toContainEqual(['Pump PA', CHART_COLORS.ink]);
	});

	it('changes nothing else: without rings the configuration is the one with them less their datasets', () => {
		const plain = config(groupChartData(members, prefs, group, system));
		const ringed = config(groupChartData(members, prefs, group, system, others()));
		const json = (value: unknown) => JSON.parse(JSON.stringify(value));
		expect(
			json({ ...ringed, data: { datasets: datasets(ringed).filter((d) => !d.otherCase) } })
		).toEqual(json(plain));
		expect(datasets(plain).some((d) => 'order' in d || 'labelColor' in d)).toBe(false);
	});
});
