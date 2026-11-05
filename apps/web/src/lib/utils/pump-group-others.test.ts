/**
 * Other cases' station duties on the Pumps together chart (CLAUDE.md D21 slice 4d): the rings
 * (their points, numbers, labels and merging within the duty checks' tolerances), the legend,
 * the accessible name, the notes and the image's footer, and the chart configuration (slate
 * rings drawn on top with a transparent fill, labelled in slate, listed last in the image's
 * legend; nothing else changes without rings). The duties are the shared fixture's real API
 * answers for the `one-off` case's scenarios. Then the curve family (CLAUDE.md D24 slice L3,
 * proposal pump-lineups.md §10.3's unit list): which other cases' group curves are drawn and how,
 * their labels (placeCurveLabels on m4_labels.txt's anchors), the legend, the notes, the
 * accessible name, the tables and the axes, on the `lineups` station's real answers.
 */
import { BasicPlatform } from 'chart.js';
import { describe, expect, it } from 'vitest';
import type {
	Flag,
	Project,
	PumpGroupCurveResponse,
	PumpResult,
	SolveResponse,
	TopologyIssue
} from '$lib/api/types';
import { Chart } from '$lib/components/results/chart-setup';
import { hydraulicFingerprint, type GroupCurveState } from '$lib/state/project.svelte';
import {
	answer as answerOf,
	drawnChart,
	lineupAnswers,
	lineupCaseName,
	lineupPrefs,
	lineups,
	lineupView,
	type LineupView
} from '$lib/testing/curve-family';
import fixture from './__fixtures__/pump-groups-input.json';
import { ratedCurveRange } from './pump-chart';
import {
	CHART_COLORS,
	GROUP_BEYOND_LABEL,
	GROUP_SYSTEM_CURVE_LABEL,
	GROUP_SYSTEM_TAG,
	OTHER_CURVES_LEGEND,
	pumpGroupConfig,
	type CurveLabelsDrawn,
	type PumpChartConfig
} from './pump-chart-config';
import {
	clipNote,
	CURVE_LABEL_ROW,
	curveAnchor,
	curveLabelText,
	DUTY_CHECK_FLOOR,
	DUTY_CLAIM_RULE,
	dutyFlow,
	GROUP_OTHER,
	groupChartData,
	groupLegend,
	groupNoteLines,
	groupNotes,
	groupSampleRows,
	groupSummary,
	labelsLeftOutNote,
	OTHER_CURVE_COLUMN,
	OTHER_CURVES_CAPTION,
	OTHER_CURVES_FRAME,
	OTHER_CURVES_LABEL,
	OTHER_SYMBOL,
	otherCurveRows,
	placeCurveLabels,
	roundUpNice,
	stationResponse,
	SYSTEM_DUTY_CHECK_FLOOR,
	type CurveLabelInput,
	type GroupChartData,
	type PxBox,
	type GroupMemberInput
} from './pump-group-chart';
import { otherGroupCases, sameInside, type OtherGroupCase } from './pump-group-one-off';
import { pumpLineup } from './pump-lineups';
import { applyScenario } from './scenarios';
import { formatNumber, fromSI } from './units';

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

/** The frame's words for a station between `s` and `d` (pump-group-chart.ts otherNotes). */
const PARALLEL =
	"In parallel that flow is the sum of the flows of the pumps running in that case, and that rise is each running pump's own head less its loss on the way.";
const frame = (s: string, d: string, arrangement = '') =>
	[
		`Each numbered slate ring is another case's station duty: that case's station flow and its rise from ${s} to ${d}, drawn against the station's flow as the group curve is, not a pump's own point.`,
		arrangement,
		"Each pump's own flow and head in each case are in Running combinations.",
		"A ring lies on its own case's group curve where that case has one (none with an active PRV or PSV inside) and the station has one state at its rise (D13): the curve drawn here when its case differs from this one only outside the station; with other pumps running, a curve of theirs that is not drawn."
	]
		.filter((x) => x)
		.join(' ');

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
					"No: the rest of the network differs from this case's; its own group system curve is not drawn"
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
			frame('Tee T1 (run inlet)', 'Tee T2 (run outlet)', PARALLEL),
			DUTY_CLAIM_RULE,
			`Other cases on the chart (slate rings, numbered): 1 · Pump PA off, ${f4(duty('S1').flow * 1000)} L/s at a rise of ${f4(duty('S1').head)} m: Yes: the same rest of the network; 2 · Pump PB off, ${f4(duty('S2').flow * 1000)} L/s at a rise of ${f4(duty('S2').head)} m: Yes: the same rest of the network; 3 · Delivery tank 5 m higher, ${f4(duty('S3').flow * 1000)} L/s at a rise of ${f4(duty('S3').head)} m: No: the rest of the network differs from this case's; its own group system curve is not drawn.`,
			'Not on the chart: Both pumps off (not on the chart (unticked under Cases on this chart)).'
		]);
		// The image's footer: after the system duty notes, before the members'.
		const lines = groupNoteLines(notes);
		const at = lines.indexOf(notes.others[0]!);
		expect(lines.slice(at, at + 4)).toEqual(notes.others);
		expect(lines.indexOf(notes.systemDuty.at(-1)!)).toBeLessThan(at);
	});

	it('words the frame for any number of pumps running: a station of three (the ladder)', () => {
		// Three pumps in parallel, all running: a ring of a case with one of N ≥ 3 off has two or
		// more running, so it lies at their summed flow, beyond each one's own flow, never below
		// "their curves" (the frame once said so, true with one pump running only).
		const ladder = cases.find((c) => c.name === 'ladder')!;
		const answer = body(ladder.groupCurve);
		expect(answer.station.memberIds).toEqual(['P1', 'P2', 'P3']);
		expect(answer.station.arrangement).toBe('parallel');
		const duty = answer.duty!;
		const running = duty.members.filter((m) => m.status === 'running');
		expect(running).toHaveLength(3);
		// The frame's two statements on the API's own numbers: the station's flow is the sum of
		// the running pumps' flows (the duty check's floor, D21), beyond each one's own; its rise
		// is each one's head less its loss on the way (D6's floor of the rise).
		const sum = running.reduce((total, m) => total + m.flow!, 0);
		expect(Math.abs(sum - duty.flow)).toBeLessThanOrEqual(DUTY_CHECK_FLOOR);
		for (const m of running) {
			expect(m.flow!).toBeLessThan(duty.flow);
			expect(Math.abs(m.head! - m.routeHeadLoss! - duty.head)).toBeLessThanOrEqual(
				SYSTEM_DUTY_CHECK_FLOOR
			);
		}
		const ladderMembers: GroupMemberInput[] = ladder.memberIds.map((id, slot) => {
			const pump = ladder.project.components.find((x) => x.id === id)!;
			return {
				id,
				name: pump.name,
				result: ladder.solve.solvedState.pumpResults[id] as PumpResult,
				ratedRange: ratedCurveRange(ladder.project, id),
				curveId: pump.type === 'pump' ? pump.curveId : null,
				slot,
				flags: []
			};
		});
		// A ring at the ladder's own duty (synthetic: another case, the same inside).
		const [ring] = otherGroupCases({
			valued: [
				{
					key: 'S1',
					caseId: 'S1',
					name: 'Pump P2 off',
					stale: false,
					group: ready(ladder.groupCurve),
					system: undefined,
					shared: false,
					solved: null
				}
			],
			shownKeys: new Set(['S1']),
			othersOn: true,
			shownSettled: true,
			station: answer.station,
			systemShown: null,
			memberIds: ladder.memberIds,
			project: ladder.project,
			boxes: ladder.memberIds
		});
		const ladderPrefs = ladder.project.settings.units;
		const notes = groupNotes({
			data: groupChartData(ladderMembers, ladderPrefs, answer, null, [ring!]),
			members: ladderMembers,
			state: ready(ladder.groupCurve),
			project: ladder.project,
			prefs: ladderPrefs,
			others: [ring!]
		});
		expect(notes.others[0]).toBe(frame('Tee TS1 (run inlet)', 'Tee TD1 (run outlet)', PARALLEL));
		expect(notes.others[0]).not.toMatch(/below/);
		// In series the flow is each pump's; in a mixed station neither is said.
		const series = cases.find((c) => c.name === 'series')!;
		const seriesAnswer = body(series.groupCurve);
		const seriesNotes = groupNotes({
			data: groupChartData([], prefs, seriesAnswer, null, [{ ...ring!, key: 'S2' }]),
			members: [],
			state: ready(series.groupCurve),
			project: series.project,
			prefs,
			others: [{ ...ring!, key: 'S2' }]
		});
		expect(seriesNotes.others[0]).toContain(
			'In series that flow passes through every pump, and that rise is their heads added together less the head across the elements between them.'
		);
		const mixed = { ...answer, station: { ...answer.station, arrangement: 'mixed' as const } };
		const mixedNotes = groupNotes({
			data: groupChartData(ladderMembers, ladderPrefs, mixed, null, [ring!]),
			members: ladderMembers,
			state: { status: 'ready', response: mixed },
			project: ladder.project,
			prefs: ladderPrefs,
			others: [ring!]
		});
		expect(mixedNotes.others[0]).toBe(frame('Tee TS1 (run inlet)', 'Tee TD1 (run outlet)'));
	});

	it('words the frame without a group curve drawn: an active PRV inside (prv-inside), or no flow', () => {
		// The group curve refused for the PRV alone: the station and its duty come from the group
		// system answer, and no group curve is drawn. A ring at that duty (synthetic: another case
		// with the same station), its case's duty from its own group system answer.
		const prv = cases.find((c) => c.name === 'prv-inside')!;
		const issues = (prv.groupCurve.body as { issues: TopologyIssue[] }).issues;
		expect(issues.map((i) => i.code)).toEqual(['PRESSURE_CONTROL_INSIDE']);
		const refused: GroupCurveState = { status: 'refused', message: 'PRV', issues };
		const answer = body(prv.systemCurve!);
		expect(stationResponse(refused, ready(prv.systemCurve!))).toBe(answer);
		const [ring] = otherGroupCases({
			valued: [
				{
					key: 'S1',
					caseId: 'S1',
					name: 'Pump PA off',
					stale: false,
					group: refused,
					system: ready(prv.systemCurve!),
					shared: false,
					solved: null
				}
			],
			shownKeys: new Set(['S1']),
			othersOn: true,
			shownSettled: true,
			station: answer.station,
			systemShown: answer,
			memberIds: prv.memberIds,
			project: prv.project,
			boxes: prv.memberIds
		});
		expect(ring!.state).toBe('ready');
		const prvMembers: GroupMemberInput[] = prv.memberIds.map((id, slot) => {
			const pump = prv.project.components.find((x) => x.id === id)!;
			return {
				id,
				name: pump.name,
				result: prv.solve.solvedState.pumpResults[id] as PumpResult,
				ratedRange: ratedCurveRange(prv.project, id),
				curveId: pump.type === 'pump' ? pump.curveId : null,
				slot,
				flags: []
			};
		});
		const prvPrefs = prv.project.settings.units;
		const data = groupChartData(prvMembers, prvPrefs, null, answer, [ring!]);
		expect(data.curve).toBeNull();
		expect(data.system!.some((p) => p.y !== null)).toBe(true);
		const notes = groupNotes({
			data,
			members: prvMembers,
			state: refused,
			system: ready(prv.systemCurve!),
			project: prv.project,
			prefs: prvPrefs,
			others: [ring!]
		});
		expect(notes.curve?.kind).toBe('refused');
		expect(notes.others[0]).toBe(
			[
				"Each numbered slate ring is another case's station duty: that case's station flow and its rise from Tee T1 (run inlet) to Tee T2 (run outlet), drawn against the station's flow as the group system curve is, not a pump's own point.",
				PARALLEL,
				"Each pump's own flow and head in each case are in Running combinations.",
				"With an active PRV or PSV inside, the station has no group curve, so none is drawn here; each ring is its case's duty from its group system curve where one is active in that case too, else from its group curve."
			].join(' ')
		);
		// No group curve drawn for another reason (synthetic: no point of `one-off`'s with a flow):
		// said against the group system curve, and that none is drawn.
		const flowless = structuredClone(group);
		flowless.points = flowless.points.map((point) => ({ ...point, flow: null }));
		const list = others(['S1']);
		const plain = groupNotes({
			data: groupChartData(members, prefs, flowless, system, list),
			members,
			state: { status: 'ready', response: flowless },
			system: ready(oneOff.systemCurve!),
			project: oneOff.project,
			prefs,
			others: list
		});
		expect(plain.curve?.kind).toBe('missing');
		expect(plain.others[0]).toBe(
			[
				"Each numbered slate ring is another case's station duty: that case's station flow and its rise from Tee T1 (run inlet) to Tee T2 (run outlet), drawn against the station's flow as the group system curve is, not a pump's own point.",
				PARALLEL,
				"Each pump's own flow and head in each case are in Running combinations.",
				"A ring lies on its own case's group curve where that case has one (none with an active PRV or PSV inside) and the station has one state at its rise (D13); no group curve is drawn here."
			].join(' ')
		);
	});

	it('gives one line, never a list, while the other cases’ duties are not asked for', () => {
		const off = otherGroupCases({
			valued: ['S1', 'S2', 'S3', 'S4'].map((id) => ({
				key: id,
				caseId: id,
				name: nameOf(id),
				stale: id === 'S2',
				group: undefined,
				system: undefined,
				shared: id !== 'S3',
				solved: applyScenario(oneOff.project, id).project
			})),
			// S4 unticked: with the box off, it is not listed either.
			shownKeys: new Set(['S1', 'S2', 'S3']),
			othersOn: false,
			shownSettled: true,
			station: group.station,
			systemShown: system,
			memberIds: oneOff.memberIds,
			project: oneOff.project,
			boxes: oneOff.memberIds
		});
		expect(off.map((o) => o.state)).toEqual(['off', 'off', 'off', 'off']);
		const notes = notesOf(off);
		expect(notes.others).toEqual([
			"Other cases' station duties are not on the chart: tick “Also show the other cases' station duties” to compute them (4 other cases with results)."
		]);
		for (const id of ['S1', 'S2', 'S3', 'S4']) expect(notes.others[0]).not.toContain(nameOf(id));
		// The image's footer: that one line.
		expect(groupNoteLines(notes).filter((l) => l.includes('Also show'))).toEqual(notes.others);
		expect(notesOf(off.slice(0, 1)).others).toEqual([
			"Other cases' station duties are not on the chart: tick “Also show the other cases' station duties” to compute them (1 other case with results)."
		]);
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

// ---------------------------------------------------------------------------------------------
// The curve family (CLAUDE.md D24 slice L3, proposal pump-lineups.md §9, §10.3's unit list), on
// the `lineups` station's real answers (testing/curve-family.ts builds the card's inputs as
// PumpsView does).
// ---------------------------------------------------------------------------------------------

const lineupBody = (key: string) => answerOf(lineupAnswers(key).groupCurve);
/** A flow in the fixture's display unit, as the card converts it. */
const lps = (q: number) => fromSI(q, 'L/s');
const lineupDuty = (key: string) => lineupBody(key).duty!;
/** The `lineups` case names, as the fixture stores them. */
const NAMES = {
	S1: '3 of 4 running (Pump P4 off)',
	S2: '2 of 4 running (Pump P3, Pump P4 off)',
	S3: '1 of 4 running (Pump P2, Pump P3, Pump P4 off)',
	S4: 'Pump P1 off',
	S5: 'Pump P2 off',
	S6: 'Pump P3 off',
	S7: 'Pump P1 at 90 % speed',
	S8: 'Delivery tank 5 m higher'
} as const;
/** §9.6's frame sentence, the last of the frame's (typed from the proposal). */
const L3_FRAME =
	"A ring lies on its own case's group curve where that case has one (none with an active PRV or PSV inside) and the station has one state at its rise (D13). Where its case differs from this one inside the station only in which pumps are switched on, and its curve has flow, that curve is drawn in slate and labelled with the number of pumps switched on; where it differs only outside the station, it is the group curve drawn for this case; otherwise it is not drawn. The list below says, for each ring, which.";
const lineupFrame = [
	"Each numbered slate ring is another case's station duty: that case's station flow and its rise from Tee TS1 (run inlet) to Tee TD1 (run outlet), drawn against the station's flow as the group curve is, not a pump's own point.",
	PARALLEL,
	"Each pump's own flow and head in each case are in Running combinations.",
	L3_FRAME
].join(' ');
/** A ring's entry in the notes' list, with its curve's words (§9.6). */
const entry = (n: number, key: keyof typeof NAMES, claim: string, curve: string) =>
	`${n} · ${NAMES[key]}, ${f4(lps(lineupDuty(key).flow))} L/s at a rise of ${f4(lineupDuty(key).head)} m: ${claim}; group curve: ${curve}`;
const CROSSING = (k: string) => `drawn (${k}): it crosses the group system curve at the ring`;
const ON = 'Yes: the same rest of the network';
const notesFor = (view: LineupView, labelsLeftOut = 0) =>
	groupNotes({
		data: view.data,
		members: view.members,
		state: { status: 'ready', response: view.response },
		system: { status: 'ready', response: view.system },
		project: lineups.project,
		prefs: lineupPrefs,
		others: view.others,
		labelsLeftOut
	});

describe('the curve family: which curves are drawn, and their points', () => {
	it('draws each curve as its response’s points in display units, in rise order, solid and beyond split where a member is beyond its data, gaps at null flows', () => {
		for (const [key, name] of Object.entries(NAMES)) expect(lineupCaseName(key)).toBe(name);
		const { data } = lineupView('');
		expect(data.otherCurves.map((c) => [c.key, c.number, c.k, c.of])).toEqual([
			['S1', 1, 3, 4],
			['S2', 2, 2, 4],
			['S3', 3, 1, 4],
			['S4', 4, 3, 4],
			['S5', 5, 3, 4],
			['S6', 6, 3, 4]
		]);
		for (const c of data.otherCurves) {
			const points = [...lineupBody(c.key).points].sort((a, b) => a.head - b.head);
			// Every segment between two neighbouring points with a flow, in rise order: beyond when
			// a member is beyond its data at either end; a point without a flow is a gap.
			const at = (p: (typeof points)[number]) => ({ x: lps(p.flow!), y: p.head });
			const segments = points.slice(1).flatMap((b, i) => {
				const a = points[i]!;
				if (a.flow === null || b.flow === null) return [];
				const beyond = [a, b].some((p) => p.members.some((m) => m.beyondData));
				return [{ from: at(a), to: at(b), beyond }];
			});
			// The same segments, from the runs as drawn.
			const drawn = [
				...c.solid.map((run) => ({ run, beyond: false })),
				...c.beyond.map((run) => ({ run, beyond: true }))
			]
				.flatMap(({ run, beyond }) => run.slice(1).map((to, i) => ({ from: run[i]!, to, beyond })))
				.sort((a, b) => a.from.y - b.from.y);
			expect(drawn).toEqual(segments);
			// Runs are whole: two runs of one kind never meet end to start.
			for (const runs of [c.solid, c.beyond]) {
				for (const a of runs) {
					for (const b of runs) {
						if (a !== b) expect(a.at(-1)).not.toEqual(b[0]);
					}
				}
			}
			expect(c.solid.length + c.beyond.length).toBeGreaterThan(0);
		}
		// "1 of 4 running" has no flow at its 45 m rise (its solve did not converge there): a gap.
		const low = data.otherCurves.find((c) => c.key === 'S3')!;
		const gap = lineupBody('S3').points.filter((p) => p.flow === null);
		expect(gap.map((p) => p.head)).toEqual([45]);
		expect([...low.solid, ...low.beyond].flat().some((p) => p.y === 45)).toBe(false);
	});

	it('draws the lineup siblings with the base shown, the base with a lineup shown, a stale case named so; no other', () => {
		expect(lineupView('S1').data.otherCurves.map((c) => [c.key, c.k])).toEqual([
			['', 4],
			['S4', 3],
			['S2', 2],
			['S3', 1],
			['S5', 3],
			['S6', 3]
		]);
		const [s1] = lineupView('').data.otherCurves;
		expect(s1).toMatchObject({
			name: NAMES.S1,
			running: '3 running',
			label: `1 · ${NAMES.S1}: group curve, 3 running`,
			shortLabel: '1 · 3 running: group curve'
		});
		const [stale] = lineupView('', { stale: ['S1'] }).data.otherCurves;
		expect(stale).toMatchObject({
			stale: true,
			name: `${NAMES.S1} (out of date)`,
			running: 'as last solved: 3 running',
			label: `1 · ${NAMES.S1} (out of date): group curve, as last solved: 3 running`,
			shortLabel: '1 · as last solved: 3 running: group curve'
		});
		// The same inside (S8) and another inside (S7, a speed) are rings only; S4 and S5 unticked.
		const swapped = lineupView('', { unticked: ['S4', 'S5'] });
		expect(swapped.data.otherCurves.map((c) => c.key)).toEqual(['S1', 'S2', 'S3', 'S6']);
		expect(swapped.data.others.map((r) => r.numbers)).toEqual([[1], [2], [3], [4], [5], [6]]);
		// Refused for an active PRV inside (synthetic: S2 with prv-inside's issues, its ring from
		// its group system answer): a ring, no curve.
		const prvIssues = (
			cases.find((c) => c.name === 'prv-inside')!.groupCurve.body as {
				issues: TopologyIssue[];
			}
		).issues;
		const refused = lineupView('', {
			edit: (v) =>
				v.key === 'S2'
					? {
							...v,
							group: { status: 'refused', message: 'PRV', issues: prvIssues },
							system: { status: 'ready', response: answerOf(lineupAnswers('S2').systemCurve) },
							inside: 'differs'
						}
					: v
		});
		expect(refused.data.others.flatMap((r) => r.numbers)).toContain(2);
		expect(refused.data.otherCurves.map((c) => c.key)).toEqual(['S1', 'S3', 'S4', 'S5', 'S6']);
		// One-off's both pumps off: no flow at any rise, a ring only; its two lineups drawn.
		const oneOffFamily = otherGroupCases({
			valued: ['S1', 'S2', 'S3', 'S4'].map((id) => {
				const solved = applyScenario(oneOff.project, id).project;
				return {
					key: id,
					caseId: id,
					name: nameOf(id),
					stale: false,
					group: ready(scenario(id).groupCurve),
					system: undefined,
					shared: id !== 'S3',
					solved,
					inside: sameInside(oneOff.project, solved, group.station, hydraulicFingerprint),
					on: pumpLineup(undefined, solved, oneOff.memberIds).on.length
				};
			}),
			shownKeys: new Set(['S1', 'S2', 'S3', 'S4']),
			othersOn: true,
			shownSettled: true,
			station: group.station,
			systemShown: system,
			memberIds: oneOff.memberIds,
			project: oneOff.project,
			boxes: oneOff.memberIds,
			curveDrawn: true
		});
		const oneOffData = groupChartData(members, prefs, group, system, oneOffFamily, 2);
		expect(oneOffData.others.flatMap((r) => r.numbers)).toEqual([1, 2, 3, 4]);
		expect(oneOffData.otherCurves.map((c) => [c.key, c.k])).toEqual([
			['S1', 1],
			['S2', 1]
		]);
		// Past the cap (S7, S8 with the base shown): neither ring nor curve.
		expect(lineupView('').data.others.flatMap((r) => r.names)).not.toContain(NAMES.S7);
		// This case's curve not drawn, or 4d's inputs: no curve at all, and the chart is 4d's.
		const plain = lineupView('', { without: true });
		expect(plain.data.otherCurves).toEqual([]);
		const flowless = lineupView('');
		const none = groupChartData(
			flowless.members,
			lineupPrefs,
			flowless.response,
			flowless.system,
			otherGroupCases({ ...flowless.input, curveDrawn: false }),
			4
		);
		expect(none.otherCurves).toEqual([]);
		expect(none).toEqual(plain.data);
	});

	it('changes nothing of 4d’s chart without a curve drawn: the same lines, points, rings, axes and system curve', () => {
		const plain = lineupView('', { without: true }).data;
		expect(plain).toMatchObject({ xMax: null, curvesCut: false, yMax: null, systemCut: false });
		expect(plain.system).toHaveLength(42);
		expect(plain.others.map((r) => r.tag)).toEqual([
			`1 · ${NAMES.S1}`,
			`2 · ${NAMES.S2}`,
			`3 · ${NAMES.S3}`,
			`4, 5, 6 · ${NAMES.S4}, ${NAMES.S5} and 1 more`
		]);
		expect(
			plain.others.flatMap((r) => r.cases.map((c) => [c.curve, c.curveCell, c.drawn]))
		).toEqual(Array.from({ length: 6 }, () => [null, null, false]));
		// With the family: the same members, group curve, station and ring points.
		const family = lineupView('').data;
		for (const key of ['lines', 'points', 'curve', 'station', 'missing', 'total'] as const) {
			expect(family[key]).toEqual(plain[key]);
		}
		expect(family.others.map((r) => r.point)).toEqual(plain.others.map((r) => r.point));
		expect([family.systemMissing, family.systemTotal]).toEqual([0, 42]);
	});
});

describe('the curve family: labels on the curves', () => {
	/** m2_labels.py's fixed character widths at 12 px (lineups/measure, the design's estimate). */
	const m4Width = (text: string) =>
		[...text].reduce(
			(w, ch) =>
				w + (/[0-9]/.test(ch) ? 6.7 : ch === ',' || ch === ' ' ? 3.3 : ch === '·' ? 4 : 6.6),
			0
		);
	// m4_labels.py's plots: a 390 px phone and a 1280 × 800 desktop.
	const PHONE = { left: 50, right: 328, top: 8, bottom: 211 };
	const DESKTOP = { left: 55, right: 554, top: 8, bottom: 243 };
	/** m4's anchors (px): this case's curve's end, then other cases' 1 to n with their k. */
	const curvesOf = (
		plot: PxBox,
		shown: [number, number],
		others: [number, number][]
	): CurveLabelInput[] => [
		{ anchor: { x: shown[1], y: plot.bottom }, k: shown[0], numbers: [] },
		...others.map(([k, x], i) => ({ anchor: { x, y: plot.bottom }, k, numbers: [i + 1] }))
	];
	/**
	 * m4_labels.txt's four families: each curve's end at a rise of 0, its largest flow, in px as
	 * m4_labels.py's `end` gives it from m1_family.json's real curves (to 4 decimals; m4 prints
	 * only the boxes).
	 */
	const FAMILIES = {
		crane: {
			phone: curvesOf(
				PHONE,
				[4, 250.1859],
				[
					[3, 200.3375],
					[2, 151.8312],
					[1, 101.7915],
					[3, 204.0382],
					[3, 203.4834],
					[3, 203.6371]
				]
			),
			desktop: curvesOf(
				DESKTOP,
				[4, 414.3264],
				[
					[3, 324.8505],
					[2, 237.7834],
					[1, 147.9638],
					[3, 331.493],
					[3, 330.4971],
					[3, 330.773]
				]
			)
		},
		ideal: {
			phone: curvesOf(
				PHONE,
				[4, 268.1681],
				[
					[3, 214.0904],
					[2, 159.5332],
					[1, 104.7815],
					[3, 213.3866],
					[3, 213.8972],
					[3, 214.0904]
				]
			),
			desktop: curvesOf(
				DESKTOP,
				[4, 446.6039],
				[
					[3, 349.5364],
					[2, 251.6081],
					[1, 153.3308],
					[3, 348.2731],
					[3, 349.1895],
					[3, 349.5364]
				]
			)
		},
		ladder: {
			phone: curvesOf(
				PHONE,
				[3, 241.5375],
				[
					[2, 193.6562],
					[1, 138.8114]
				]
			),
			desktop: curvesOf(
				DESKTOP,
				[3, 437.0033],
				[
					[2, 341.5086],
					[1, 232.1259]
				]
			)
		},
		six: {
			phone: curvesOf(
				PHONE,
				[6, 243.7178],
				[
					[5, 212.7405],
					[4, 180.8834],
					[3, 148.4542],
					[2, 115.7199],
					[1, 82.8689]
				]
			),
			desktop: curvesOf(
				DESKTOP,
				[6, 441.3516],
				[
					[5, 379.5705],
					[4, 316.0345],
					[3, 251.3576],
					[2, 186.0721],
					[1, 120.5539]
				]
			)
		}
	};
	/** m4_labels.txt's rounding: Python's "{:.0f}", half to even. */
	const m4Round = (v: number) => {
		const r = Math.round(v);
		return v - Math.floor(v) === 0.5 && r % 2 !== 0 ? r - 1 : r;
	};
	const rows = (placement: ReturnType<typeof placeCurveLabels>) =>
		placement.labels.map((l) => [l.row, l.text, `${m4Round(l.box.left)}..${m4Round(l.box.right)}`]);
	const place = (
		curves: CurveLabelInput[],
		plot: PxBox,
		compact: boolean,
		obstacles: readonly PxBox[] = []
	) => placeCurveLabels(curves, obstacles, plot, m4Width, compact);

	it('words each label by view: desktop and image with the numbers, a phone the count; this case’s own', () => {
		expect(curveLabelText([1], 3)).toBe('1 · 3 running');
		expect(curveLabelText([6, 1, 5, 4], 3)).toBe('1, 4, 5, 6 · 3 running');
		expect(curveLabelText([1], 3, true)).toBe('3 running');
		expect(curveLabelText([], 4)).toBe('4 running (this case)');
		expect(curveLabelText([], 4, true)).toBe('4 running');
		// The image takes the desktop's words (it is never compact).
		const { labels } = place(FAMILIES.ladder.desktop, DESKTOP, false);
		expect(labels.map((l) => [l.text, l.shown])).toEqual([
			['2 · 1 running', false],
			['1 · 2 running', false],
			['3 running (this case)', true]
		]);
	});

	it('places m4’s four families as measured: merged equal counts, numbers ascending, at most three rows, none left out', () => {
		expect(rows(place(FAMILIES.crane.phone, PHONE, true))).toEqual([
			[0, '1 running', '52..108'],
			[1, '2 running', '92..148'],
			[0, '3 running', '144..200'],
			[1, '4 running', '190..246']
		]);
		expect(rows(place(FAMILIES.crane.desktop, DESKTOP, false))).toEqual([
			[0, '3 · 1 running', '70..144'],
			[0, '2 · 2 running', '160..234'],
			// m4_labels.txt listed the merged numbers unsorted ("1, 5, 6, 4"); §9.3 sorts them.
			[1, '1, 4, 5, 6 · 3 running', '214..327'],
			[0, '4 running (this case)', '282..410']
		]);
		expect(rows(place(FAMILIES.ideal.phone, PHONE, true))).toEqual([
			[0, '1 running', '52..108'],
			[1, '2 running', '99..156'],
			[0, '3 running', '154..210'],
			[1, '4 running', '208..264']
		]);
		expect(rows(place(FAMILIES.ideal.desktop, DESKTOP, false))).toEqual([
			[0, '3 · 1 running', '76..149'],
			[0, '2 · 2 running', '174..248'],
			[1, '1, 4, 5, 6 · 3 running', '232..346'],
			[0, '4 running (this case)', '314..443']
		]);
		expect(rows(place(FAMILIES.ladder.phone, PHONE, true))).toEqual([
			[0, '1 running', '79..135'],
			[1, '2 running', '133..190'],
			[0, '3 running', '181..238']
		]);
		expect(rows(place(FAMILIES.ladder.desktop, DESKTOP, false))).toEqual([
			[0, '2 · 1 running', '155..228'],
			[0, '1 · 2 running', '264..338'],
			[1, '3 running (this case)', '304..433']
		]);
		// N = 6: the third row is needed on a phone (two rows left one overlap, m3_labels.txt).
		expect(rows(place(FAMILIES.six.phone, PHONE, true))).toEqual([
			[0, '1 running', '52..108'],
			[1, '2 running', '56..112'],
			[2, '3 running', '88..144'],
			[0, '4 running', '121..177'],
			[1, '5 running', '153..209'],
			[0, '6 running', '184..240']
		]);
		expect(rows(place(FAMILIES.six.desktop, DESKTOP, false))).toEqual([
			[0, '5 · 1 running', '57..130'],
			[1, '4 · 2 running', '109..182'],
			[0, '3 · 3 running', '174..247'],
			[1, '2 · 4 running', '239..312'],
			[0, '1 · 5 running', '302..376'],
			[2, '6 running (this case)', '309..437']
		]);
		for (const family of Object.values(FAMILIES)) {
			expect(place(family.phone, PHONE, true).leftOut).toBe(0);
			expect(place(family.desktop, DESKTOP, false).leftOut).toBe(0);
		}
		// Each label right-aligned 4 px left of and 4 px above its anchor (the rightmost merged).
		const [, , merged] = place(FAMILIES.crane.desktop, DESKTOP, false).labels;
		expect(merged!.curves).toEqual([1, 5, 6, 4]);
		expect(merged!.box.right).toBeCloseTo(331.493 - 4, 9);
		expect(merged!.y).toBe(DESKTOP.bottom - 4 - CURVE_LABEL_ROW);
		expect(merged!.x).toBe(merged!.box.left);
		// Clamped inside the plot's left edge (2 px, as the group system curve's tag is).
		expect(place(FAMILIES.crane.phone, PHONE, true).labels[0]!.box.left).toBe(PHONE.left + 2);
	});

	it('merges equal counts only within one label width; never this case’s label, never other counts', () => {
		const width = m4Width('2 · 2 running');
		const pair = (dx: number): CurveLabelInput[] => [
			{ anchor: { x: 300, y: 243 }, k: 2, numbers: [2] },
			{ anchor: { x: 300 + dx, y: 243 }, k: 2, numbers: [1] }
		];
		expect(place(pair(width - 0.01), DESKTOP, false).labels.map((l) => l.text)).toEqual([
			'1, 2 · 2 running'
		]);
		// One label width apart or more: two labels (unlike pumps' equal counts end far apart).
		expect(place(pair(width), DESKTOP, false).labels.map((l) => l.text)).toEqual([
			'2 · 2 running',
			'1 · 2 running'
		]);
		// This case's curve of the same count at the same end: never merged.
		const own: CurveLabelInput[] = [
			{ anchor: { x: 300, y: 243 }, k: 2, numbers: [] },
			{ anchor: { x: 301, y: 243 }, k: 2, numbers: [1] }
		];
		expect(
			place(own, DESKTOP, false)
				.labels.map((l) => l.text)
				.sort()
		).toEqual(['1 · 2 running', '2 running (this case)']);
		// Nor when another case's end comes first and this case's a pixel to its right.
		const after: CurveLabelInput[] = [
			{ anchor: { x: 300, y: 243 }, k: 2, numbers: [1] },
			{ anchor: { x: 301, y: 243 }, k: 2, numbers: [] }
		];
		const kept = place(after, DESKTOP, false).labels;
		expect(kept.map((l) => [l.text, l.curves, l.shown])).toEqual([
			['1 · 2 running', [0], false],
			['2 running (this case)', [1], true]
		]);
		expect(place(after, PHONE, true).labels.map((l) => [l.text, l.curves])).toEqual([
			['2 running', [0]],
			['2 running', [1]]
		]);
		// A merge across another count's end: the merged label sits at its rightmost anchor, right
		// of that end, so rows go from left to right by where the labels are placed (§9.3).
		const across: CurveLabelInput[] = [
			{ anchor: { x: 150, y: 200 }, k: 2, numbers: [1] },
			{ anchor: { x: 170, y: 200 }, k: 1, numbers: [2] },
			{ anchor: { x: 200, y: 200 }, k: 2, numbers: [3] }
		];
		const fixed = (text: string) => text.length * 6;
		const plot = { left: 0, right: 400, top: 0, bottom: 210 };
		const crossed = placeCurveLabels(across, [], plot, fixed, true);
		expect(crossed.labels.map((l) => [l.text, l.curves, l.row])).toEqual([
			['1 running', [1], 0],
			['2 running', [0, 2], 1]
		]);
		expect(crossed.labels[1]!.box.right).toBe(200 - 4);
		expect(placeCurveLabels(across, [], plot, fixed).labels.map((l) => [l.text, l.row])).toEqual([
			['2 · 1 running', 0],
			['1, 3 · 2 running', 1]
		]);
		// A curve with no point inside the plot has no label, and is not counted as left out.
		const outside = place([{ anchor: null, k: 1, numbers: [1] }], DESKTOP, false);
		expect(outside).toEqual({ labels: [], leftOut: 0 });
	});

	it('moves a label up past a marker, a ring’s tag or a member’s label; leaves it out after the third row, counted', () => {
		// A marker over "3 · 1 running" on its own row: it moves up one row.
		const marker = { left: 100, right: 120, top: 225, bottom: 241 };
		const moved = place(FAMILIES.crane.desktop, DESKTOP, false, [marker]);
		expect(rows(moved)[0]).toEqual([1, '3 · 1 running', '70..144']);
		// A ring's tag on the third row of "3 running" (N = 6, phone): no row is free.
		const tag = { left: 100, right: 130, top: 166, bottom: 178 };
		const crowded = place(FAMILIES.six.phone, PHONE, true, [tag]);
		expect(crowded.labels.map((l) => l.text)).toEqual([
			'1 running',
			'2 running',
			'4 running',
			'5 running',
			'6 running'
		]);
		expect(crowded.leftOut).toBe(1);
		// A member's label over the merged label's second and third rows: its four curves left out.
		const memberLabel = { left: 250, right: 300, top: 190, bottom: 215 };
		const merged = place(FAMILIES.crane.desktop, DESKTOP, false, [memberLabel]);
		expect(rows(merged)).toEqual([
			[0, '3 · 1 running', '70..144'],
			[0, '2 · 2 running', '160..234'],
			[0, '4 running (this case)', '282..410']
		]);
		expect(merged.leftOut).toBe(4);
		// A row above the plot's top does not fit.
		const high = placeCurveLabels(
			[
				{ anchor: { x: 200, y: DESKTOP.top + 20 }, k: 1, numbers: [1] },
				{ anchor: { x: 200, y: DESKTOP.top + 20 }, k: 2, numbers: [2] }
			],
			[],
			DESKTOP,
			m4Width
		);
		expect(high.labels.map((l) => [l.row, l.text])).toEqual([[0, '1 · 1 running']]);
		expect(high.leftOut).toBe(1);
		// The notes count them.
		expect(labelsLeftOutNote(4)).toBe(
			'Labels of 4 curves are left out for space; the data table lists every curve.'
		);
		expect(labelsLeftOutNote(0)).toBeNull();
		const notes = notesFor(lineupView(''), 1);
		expect(notes.others.at(-1)).toBe(
			'Labels of 1 curve are left out for space; the data table lists every curve.'
		);
		expect(notesFor(lineupView('')).others.join(' ')).not.toContain('left out for space');
	});

	it('anchors a label at the curve’s drawn point of largest flow inside the plot', () => {
		const plot = { left: 50, right: 300, top: 10, bottom: 200 };
		expect(
			curveAnchor(
				[
					{ x: 320, y: 190 },
					{ x: 280, y: 150 },
					{ x: 290, y: 5 },
					{ x: 60, y: 20 }
				],
				plot
			)
		).toEqual({ x: 280, y: 150 });
		expect(curveAnchor([{ x: 300, y: 200 }], plot)).toEqual({ x: 300, y: 200 });
		expect(curveAnchor([{ x: 301, y: 100 }], plot)).toBeNull();
	});

	it('tags a ring by its numbers only when every case of it has its curve drawn', () => {
		expect(lineupView('').data.others.map((r) => [r.tag, r.short])).toEqual([
			['1', '1'],
			['2', '2'],
			['3', '3'],
			['4, 5, 6', '4, 5, 6']
		]);
		// S4 and S5 unticked: S7 (another inside) and S8 (the same inside) keep 4d's tags; S8's
		// duty moved onto S1's (synthetic) shares S1's ring, which then keeps 4d's tag too.
		const view = lineupView('', { unticked: ['S4', 'S5'] });
		expect(view.data.others.map((r) => r.tag)).toEqual([
			'1',
			'2',
			'3',
			'4',
			`5 · ${NAMES.S7}`,
			`6 · ${NAMES.S8}`
		]);
		const s1 = view.others.find((o) => o.key === 'S1')!;
		const shared = view.others.map((o) => (o.key === 'S8' ? { ...o, duty: s1.duty } : o));
		const data = groupChartData(view.members, lineupPrefs, view.response, view.system, shared, 4);
		expect(data.others[0]).toMatchObject({
			numbers: [1, 6],
			tag: `1, 6 · ${NAMES.S1}, ${NAMES.S8}`,
			short: '1, 6'
		});
	});
});

describe('the curve family: the legend, the notes, the accessible name and the tables', () => {
	it('adds one legend entry, slate, for the whole family (62 characters)', () => {
		const legend = groupLegend(lineupView('').data);
		const family = legend.filter((i) => i.key === 'other-curves');
		expect(family).toEqual([
			{ key: 'other-curves', label: OTHER_CURVES_LABEL, kind: 'line', color: GROUP_OTHER, dash: [] }
		]);
		expect(OTHER_CURVES_LABEL).toBe(
			"Other cases' group curves (slate; dashed beyond a pump's data)"
		);
		expect(OTHER_CURVES_LABEL).toHaveLength(62);
		// After the group curve's entries, before the group system curve's.
		const keys = legend.map((i) => i.key);
		expect(keys.indexOf('other-curves')).toBe(keys.indexOf('group-beyond') + 1);
		expect(keys.indexOf('group-system')).toBe(keys.indexOf('other-curves') + 1);
		expect(groupLegend(lineupView('', { without: true }).data).map((i) => i.key)).toEqual(
			keys.filter((k) => k !== 'other-curves')
		);
	});

	it('says the frame, the clip note’s clauses, each ring’s curve and the cases not on the chart, exactly', () => {
		expect(OTHER_CURVES_FRAME).toBe(L3_FRAME);
		// The base shown: the group system curve cut at the top (the family inside the base's).
		expect(notesFor(lineupView('')).others).toEqual([
			lineupFrame,
			"The group system curve is cut at the top, above every pump's head; the data tables list all their points.",
			DUTY_CLAIM_RULE,
			`Other cases on the chart (slate rings, numbered): ${[
				entry(1, 'S1', ON, CROSSING('3 running')),
				entry(2, 'S2', ON, CROSSING('2 running')),
				entry(3, 'S3', ON, CROSSING('1 running')),
				entry(4, 'S4', ON, CROSSING('3 running')),
				entry(5, 'S5', ON, CROSSING('3 running')),
				entry(6, 'S6', ON, CROSSING('3 running'))
			].join('; ')}.`,
			`Not on the chart: ${NAMES.S7} (not on the chart (unticked under Cases on this chart)); ${NAMES.S8} (not on the chart (unticked under Cases on this chart)).`
		]);
		// "1 of 4 running" shown: the other curves cut at the right edge; its system curve whole.
		const low = notesFor(lineupView('S3')).others;
		expect(low[1]).toBe(
			"Other cases' group curves are cut at the chart's right edge, the largest flow of this case's own lines and the rings; the data tables list all their points."
		);
		// "2 of 4 running" shown: both cuts.
		expect(notesFor(lineupView('S2')).others[1]).toBe(
			"Other cases' group curves are cut at the chart's right edge, the largest flow of this case's own lines and the rings; the group system curve is cut at the top, above every pump's head; the data tables list all their points."
		);
		// Its x clause follows a cut made (curvesCut), not x max set.
		expect(clipNote({ curvesCut: false, systemCut: false })).toBeNull();
		// S7 and S8 on the chart, a stale S1: each state's words.
		const view = lineupView('', { unticked: ['S4', 'S5'], stale: ['S1'] });
		const list = notesFor(view).others.find((l) => l.startsWith('Other cases on the chart'))!;
		const words = (n: number, key: keyof typeof NAMES) => {
			const o = view.others.find((x) => x.key === key)!;
			return `${n} · ${NAMES[key]}, ${f4(lps(dutyFlow(o.duty!.flow)))} L/s at a rise of ${f4(o.duty!.head)} m: ${o.words}; group curve: `;
		};
		expect(list).toContain(
			`${words(1, 'S1').replace(NAMES.S1, `${NAMES.S1} (out of date)`)}drawn (as last solved: 3 running): it crosses the group system curve at the ring;`
		);
		expect(list).toContain(
			`${words(5, 'S7')}not drawn: the station differs inside in more than which pumps are switched on;`
		);
		expect(list).toContain(
			`${words(6, 'S8')}the same as this case's: the station is the same inside.`
		);
		expect(view.others.find((o) => o.key === 'S8')!.words).toBe(
			"No: the rest of the network differs from this case's; its own group system curve is not drawn"
		);
		// The image's footer: the frame, the clip note and the list, in that order.
		const notes = notesFor(lineupView(''));
		const lines = groupNoteLines(notes);
		const at = lines.indexOf(notes.others[0]!);
		expect(lines.slice(at, at + notes.others.length)).toEqual(notes.others);
	});

	it('says the frame sentence while the rings’ curves are judged, though none of theirs is drawn', () => {
		// The base shown with only S7 (another inside) and S8 (the same inside) on the chart: this
		// case's group curve is drawn, the rings carry their curve states, no other curve is drawn.
		const view = lineupView('', { unticked: ['S1', 'S2', 'S3', 'S4', 'S5', 'S6'] });
		expect(view.data.otherCurves).toEqual([]);
		const rings = view.others.filter((o) => o.onChart);
		expect(rings.map((o) => [o.key, o.curveState])).toEqual([
			['S7', 'inside_differs'],
			['S8', 'same_inside']
		]);
		const notes = notesFor(view).others;
		expect(notes[0]).toBe(lineupFrame);
		expect(notes[1]).toBe(DUTY_CLAIM_RULE);
		const [s7, s8] = rings.map(
			(o) =>
				`${o.number} · ${NAMES[o.key as keyof typeof NAMES]}, ${f4(lps(dutyFlow(o.duty!.flow)))} L/s at a rise of ${f4(o.duty!.head)} m: ${o.words}; group curve: `
		);
		expect(notes[2]).toBe(
			`Other cases on the chart (slate rings, numbered): ${s7}not drawn: the station differs inside in more than which pumps are switched on; ${s8}the same as this case's: the station is the same inside.`
		);
	});

	it('names each other case’s curve in the chart’s accessible name, then the curves drawn', () => {
		const view = lineupView('');
		const summary = groupSummary(
			view.data,
			view.members,
			view.response,
			lineups.project,
			view.system
		);
		const part = (n: number, key: keyof typeof NAMES, k: string) =>
			`${n} · ${NAMES[key]}, ${f4(lps(lineupDuty(key).flow))} L/s at a rise of ${f4(lineupDuty(key).head)} m (${ON}; group curve: ${CROSSING(k)})`;
		expect(summary).toContain(
			`; other cases' station duties: ${[
				part(1, 'S1', '3 running'),
				part(2, 'S2', '2 running'),
				part(3, 'S3', '1 running'),
				part(4, 'S4', '3 running'),
				part(5, 'S5', '3 running'),
				part(6, 'S6', '3 running')
			].join(
				'; '
			)}; other cases' group curves drawn: 1 (3 running), 2 (2 running), 3 (1 running), 4 (3 running), 5 (3 running) and 6 (3 running); group curve shown; group system curve shown.`
		);
		const stale = lineupView('', { stale: ['S1'] });
		expect(
			groupSummary(stale.data, stale.members, stale.response, lineups.project, stale.system)
		).toContain("; other cases' group curves drawn: 1 (as last solved: 3 running), 2 (2 running)");
		const plain = lineupView('', { without: true });
		expect(
			groupSummary(plain.data, plain.members, plain.response, lineups.project, plain.system)
		).not.toContain('group curve:');
	});

	it('lists every point of each drawn curve in the new table, and its state in the duties table’s column', () => {
		const view = lineupView('', { stale: ['S1'] });
		const groups = otherCurveRows(view.others, lineupPrefs, lineups.project);
		expect(groups.map((g) => g.header)).toEqual([
			`1 · ${NAMES.S1} (out of date): as last solved: 3 running`,
			`2 · ${NAMES.S2}: 2 running`,
			`3 · ${NAMES.S3}: 1 running`,
			`4 · ${NAMES.S4}: 3 running`,
			`5 · ${NAMES.S5}: 3 running`,
			`6 · ${NAMES.S6}: 3 running`
		]);
		for (const g of groups) {
			const response = lineupBody(g.key);
			const points = [...response.points].sort((a, b) => a.head - b.head);
			const samples = groupSampleRows(response, [], lineupPrefs, lineups.project);
			expect(g.rows).toHaveLength(42);
			expect(g.rows).toEqual(
				points.map((p, i) => ({
					rise: f4(p.head),
					flow: p.flow === null ? '—' : f4(lps(p.flow)),
					note: p.isDuty ? "Its duty's rise (its duty check)." : samples[i]!.note
				}))
			);
			expect(g.rows.filter((r) => r.note === "Its duty's rise (its duty check).")).toHaveLength(1);
		}
		// The point without a flow, by its message as groupSampleRows gives it.
		const gap = groups[2]!.rows.find((r) => r.flow === '—')!;
		expect(gap.rise).toBe('45');
		expect(gap.note).toMatch(/^Its solve did not converge\. /);
		// None without a curve drawn.
		expect(otherCurveRows(lineupView('', { without: true }).others, lineupPrefs)).toEqual([]);
		// The station duties table's column and the new table's caption.
		expect(OTHER_CURVE_COLUMN).toBe('Its group curve');
		expect(OTHER_CURVES_CAPTION).toBe("Other cases' group curves (station's flow at each rise)");
		const cells = view.data.others.flatMap((r) => r.cases.map((c) => c.curveCell));
		expect(cells[0]).toBe(
			'Drawn (as last solved: 3 running): it crosses the group system curve at the ring'
		);
		expect(cells[1]).toBe('Drawn (2 running): it crosses the group system curve at the ring');
		const swapped = lineupView('', { unticked: ['S4', 'S5'] }).data.others;
		expect(swapped.map((r) => r.cases[0]!.curveCell).slice(4)).toEqual([
			'Not drawn: the station differs inside in more than which pumps are switched on',
			"The same as this case's: the station is the same inside"
		]);
	});
});

describe('the curve family: the axes', () => {
	/** The largest flow of everything but the other cases' curves (§9.4), as drawn. */
	const largestElse = (data: GroupChartData) =>
		Math.max(
			...data.lines.flatMap((l) => [...l.curve, ...l.extrapolated.flat()].map((p) => p.x)),
			...data.points.map((p) => p.point.x),
			...[...(data.curve?.solid ?? []), ...(data.curve?.beyond ?? [])].flat().map((p) => p.x),
			...(data.system ?? []).filter((p) => p.y !== null).map((p) => p.x),
			...(data.station ? [data.station.point.x] : []),
			...data.others.map((r) => r.point.x)
		);
	const familyFlows = (data: GroupChartData) =>
		data.otherCurves.flatMap((c) => [...c.solid, ...c.beyond].flat().map((p) => p.x));

	it('rounds an axis up to {1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8} × 10ⁿ', () => {
		const cases: [number, number | null][] = [
			[47.25, 50],
			[89.49, 100],
			[50, 50],
			[101, 120],
			[150, 150],
			[151, 200],
			[2.51, 3],
			// Just above each step, so each one is the answer once: 2.5, 4, 6 and 8 (no 3.5, no 7).
			[2.4, 2.5],
			[3.2, 4],
			[3.9, 4],
			[5.5, 6],
			[6.5, 8],
			// 0.01 above each step (with 101, 151 and 2.51 above), so no step lies between two
			// neighbours: the answer is the next one (no 1.22, 2.2, 3.1, 4.5, 5.2 or 6.2).
			[1.21, 1.5],
			[2.01, 2.5],
			[3.01, 4],
			[4.01, 5],
			[5.01, 6],
			[6.01, 8],
			[8.01, 10],
			// Below 1, where step × 10ⁿ is inexact in binary (3 × 10⁻¹ is 0.30000000000000004).
			[0.29, 0.3],
			[0.149, 0.15],
			[7.9, 8],
			[8.1, 10],
			[0.0119, 0.012],
			[1, 1],
			[1234, 1500],
			[0, null],
			[-1, null],
			[Number.NaN, null],
			[Number.POSITIVE_INFINITY, null]
		];
		for (const [value, expected] of cases)
			expect([value, roundUpNice(value)]).toEqual([value, expected]);
	});

	it('sets no x max with the base shown: every other curve lies inside the base’s own', () => {
		const { data } = lineupView('');
		expect(data.xMax).toBeNull();
		expect(Math.max(...familyFlows(data))).toBeLessThanOrEqual(largestElse(data));
	});

	it('sets x max with “1 of 4 running” shown from its own lines and the rings, rounded up; every ring inside', () => {
		const { data } = lineupView('S3');
		// The base's ring is the largest flow of everything else (85.23 L/s); the base's curve
		// reaches 216 L/s.
		expect(largestElse(data)).toBe(lps(lineupDuty('').flow));
		expect(Math.max(...familyFlows(data))).toBe(
			lps(Math.max(...lineupBody('').points.map((p) => p.flow ?? 0)))
		);
		expect(data.xMax).toBe(100);
		expect(largestElse(data) * 1.05).toBeLessThanOrEqual(100);
		expect(largestElse(data) * 1.05).toBeGreaterThan(80);
		for (const ring of data.others) expect(ring.point.x).toBeLessThanOrEqual(data.xMax!);
		// "2 of 4 running" shown: from its group system curve as drawn (cut at y max).
		const mid = lineupView('S2').data;
		expect(mid.xMax).toBe(roundUpNice(largestElse(mid) * 1.05));
		expect(mid.xMax).toBe(120);
	});

	it('sets x max from each part of everything else in turn, wherever it is the largest flow (synthetic)', () => {
		// "1 of 4 running" shown: the base's ring (85.23 L/s) is the largest flow but the family's,
		// so x max is 100 L/s. Each edit below makes one other part reach 110 L/s, the largest:
		// x max is then 110 × 1.05 = 115.5 rounded up, 120 L/s, and the family still passes it.
		const view = lineupView('S3');
		expect(view.data.xMax).toBe(100);
		const Q = 0.11;
		const xMaxWith = (edit: {
			members?: (m: GroupMemberInput) => GroupMemberInput;
			response?: (r: PumpGroupCurveResponse) => void;
			system?: (r: PumpGroupCurveResponse) => void;
		}) => {
			const response = structuredClone(view.response);
			const system = structuredClone(view.system);
			edit.response?.(response);
			edit.system?.(system);
			const members = view.members.map(edit.members ?? ((m) => m));
			const data = groupChartData(members, lineupPrefs, response, system, view.others, 1);
			expect(Math.max(...familyFlows(data))).toBeGreaterThan(largestElse(data));
			return { data, largest: largestElse(data) };
		};
		const p1 = (change: (r: PumpResult) => PumpResult, range?: [number, number]) => ({
			members: (m: GroupMemberInput) =>
				m.id === 'P1'
					? { ...m, result: change(structuredClone(m.result)), ratedRange: range ?? m.ratedRange }
					: m
		});
		const longer = (r: PumpResult) => ({ ...r, curve: [...r.curve, { flow: Q, head: 1 }] });
		const cases = {
			// The members' line inside its data (the curve's data range widened to its last point).
			'members’ line': p1(longer, [0, Q]),
			// The members' line beyond its data (the end-slope extrapolation out to that point).
			'members’ line beyond its data': p1(longer),
			// A member's point (its curve without samples, so no line reaches it).
			'member’s point': p1((r) => ({ ...r, curve: [], operatingFlow: Q })),
			'Group point': {
				response: (r: PumpGroupCurveResponse) => void (r.duty!.flow = Q)
			},
			// The group system curve, as drawn (S3's reaches 31.6 m, under y max: drawn whole).
			'group system curve': {
				system: (r: PumpGroupCurveResponse) => {
					const top = Math.max(...r.systemPoints.map((p) => p.flow));
					for (const p of r.systemPoints) p.flow *= Q / top;
				}
			}
		};
		for (const [part, edit] of Object.entries(cases)) {
			const { data, largest } = xMaxWith(edit);
			expect([part, largest]).toEqual([part, lps(Q)]);
			expect([part, data.xMax]).toEqual([part, 120]);
		}
		// The members' line beyond its data is drawn dashed: the part that reaches 110 L/s.
		const beyond = xMaxWith(cases['members’ line beyond its data']).data.lines[0]!;
		expect(Math.max(...beyond.curve.map((p) => p.x))).toBeLessThan(lps(Q));
		expect(Math.max(...beyond.extrapolated.flat().map((p) => p.x))).toBe(lps(Q));
	});

	it('sets x max whenever the family passes everything else, and says a curve is cut only where one is', () => {
		const SYSTEM_CUT =
			"The group system curve is cut at the top, above every pump's head; the data tables list all their points.";
		// A 3-running case shown and the base unticked: its siblings' curves pass its own (162.2
		// L/s) by a little, so x max is set (§9.4), at 162.2 × 1.05 rounded up, 200 L/s; no point of
		// any of them lies beyond it, so nothing is cut at the right edge and the note says so.
		for (const shown of ['S1', 'S5', 'S6']) {
			const view = lineupView(shown, { unticked: [''] });
			const { data } = view;
			expect(Math.max(...familyFlows(data))).toBeGreaterThan(largestElse(data));
			expect(Math.max(...familyFlows(data))).toBeLessThan(largestElse(data) * 1.05);
			expect(data.xMax).toBe(200);
			expect(familyFlows(data).filter((x) => x > data.xMax!)).toEqual([]);
			expect(notesFor(view).others[1]).toBe(SYSTEM_CUT);
			expect(groupNoteLines(notesFor(view)).join(' ')).not.toContain('right edge');
			expect(data.curvesCut).toBe(false);
		}
		// Flow in m³/h, the base ticked: "3 of 4 running" shown, its own largest flow 584 m³/h gives
		// x max 800 m³/h (600 without the margin), past the base's 777.7 m³/h: nothing is cut.
		const metric = { ...lineupPrefs, flow: 'm3/h' as const };
		const inUnits = (shown: string) => {
			const view = lineupView(shown);
			const { members, response, system, others, data } = view;
			return groupChartData(members, metric, response, system, others, data.on);
		};
		for (const shown of ['S1', 'S4', 'S5', 'S6']) {
			const data = inUnits(shown);
			expect(data.xMax).toBe(800);
			expect(Math.max(...familyFlows(data))).toBeGreaterThan(largestElse(data));
			expect(familyFlows(data).filter((x) => x > 800)).toEqual([]);
			expect(clipNote(data)).toBe(SYSTEM_CUT);
			expect(data.curvesCut).toBe(false);
		}
		// "1 of 4 running" shown in m³/h: the base's curve passes x max, cut, and the note says so.
		const low = inUnits('S3');
		expect(familyFlows(low).some((x) => x > low.xMax!)).toBe(true);
		expect(low.curvesCut).toBe(true);
		expect(clipNote(low)).toBe(
			"Other cases' group curves are cut at the chart's right edge, the largest flow of this case's own lines and the rings; the data tables list all their points."
		);
	});

	it('sets y max only while the family is drawn, from every drawn head but the group system curve’s, which is cut above it', () => {
		// No family (4d's inputs, or this case's curve not drawn): Chart.js's own range, whole.
		const plain = lineupView('', { without: true }).data;
		expect(plain.yMax).toBeNull();
		expect(plain.system).toEqual(
			[...lineupView('').system.systemPoints]
				.sort((a, b) => a.flow - b.flow)
				.map((p) => ({ x: lps(p.flow), y: p.head }))
		);
		const { data, system } = lineupView('');
		const heads = [
			...data.lines.flatMap((l) => [...l.curve, ...l.extrapolated.flat()].map((p) => p.y)),
			...data.points.map((p) => p.point.y),
			...[...data.curve!.solid, ...data.curve!.beyond].flat().map((p) => p.y),
			...data.otherCurves.flatMap((c) => [...c.solid, ...c.beyond].flat().map((p) => p.y)),
			data.station!.point.y,
			...data.others.map((r) => r.point.y)
		];
		// The largest is the pumps' shutoff head (45 m): 47.25 m rounds up to 50 m.
		expect(Math.max(...heads)).toBe(45);
		expect(data.yMax).toBe(50);
		for (const y of heads) expect(y).toBeLessThanOrEqual(data.yMax!);
		// The group system curve (to 184 m) cut: its points up to 50 m, and the first above, so
		// its line runs to the plot's top edge; the clip note says so; its gaps counted whole.
		const full = [...system.systemPoints]
			.sort((a, b) => a.flow - b.flow)
			.map((p) => ({ x: lps(p.flow), y: p.head! }));
		expect(Math.max(...full.map((p) => p.y))).toBeGreaterThan(180);
		const below = full.filter((p) => p.y <= 50);
		expect(data.system).toEqual([...below, full.find((p) => p.y > 50)!]);
		expect(data.systemCut).toBe(true);
		expect([data.systemMissing, data.systemTotal]).toEqual([0, 42]);
		expect(notesFor(lineupView('')).others[1]).toBe(
			"The group system curve is cut at the top, above every pump's head; the data tables list all their points."
		);
		// Gaps (synthetic: two points without a rise): one inside the plot stays, so the line
		// breaks there; one far above goes with the points around it.
		const gapped = structuredClone(system);
		const sorted = [...gapped.systemPoints].sort((a, b) => a.flow - b.flow);
		sorted[5]!.head = null;
		sorted[35]!.head = null;
		const view = lineupView('');
		const cut = groupChartData(view.members, lineupPrefs, view.response, gapped, view.others, 4);
		expect(cut.system).toEqual([
			...below.slice(0, 5),
			{ x: below[5]!.x, y: null },
			...below.slice(6),
			full.find((p) => p.y > 50)!
		]);
		expect([cut.systemMissing, cut.systemTotal]).toEqual([2, 42]);
		// "1 of 4 running" shown: its group system curve (to 31.6 m) is under y max, not cut.
		const low = lineupView('S3').data;
		expect(low.yMax).toBe(50);
		expect(low.systemCut).toBe(false);
		expect(low.system).toHaveLength(42);
	});

	it('sets y max at the largest head × 1.05, rounded up: the margin decides it in ft and above 45.45 m', () => {
		const view = lineupView('');
		// Head in ft: the shutoff, 45 m = 147.6 ft, × 1.05 = 155.0 ft rounds up to 200 ft (150 ft
		// without the margin would put the shutoff 2.4 ft under the plot's top).
		const feet = groupChartData(
			view.members,
			{ ...lineupPrefs, head: 'ft' },
			view.response,
			view.system,
			view.others,
			4
		);
		const shutoff = fromSI(45, 'ft');
		expect(shutoff).toBeGreaterThan(147.6);
		expect(shutoff).toBeLessThan(150);
		expect(shutoff * 1.05).toBeGreaterThan(150);
		expect(feet.yMax).toBe(200);
		// Synthetic: a ring at a rise of 46.5 m, the largest head: × 1.05 = 48.8 m gives 50 m (× 1.1
		// would give 60 m).
		const s1 = view.others.find((o) => o.key === 'S1')!;
		const high = view.others.map((o) =>
			o.key === 'S1' ? { ...o, duty: { ...s1.duty!, head: 46.5 } } : o
		);
		const raised = groupChartData(view.members, lineupPrefs, view.response, view.system, high, 4);
		expect(Math.max(...raised.others.map((r) => r.point.y))).toBe(46.5);
		expect(raised.yMax).toBe(50);
	});
});

describe('the curve family: the chart configuration (pumpGroupConfig, the UI half)', () => {
	type Dataset = PumpChartConfig['data']['datasets'][number] & Record<string, unknown>;
	const tools = { place: placeCurveLabels, anchor: curveAnchor };
	const config = (data: GroupChartData, options = {}) =>
		pumpGroupConfig(data, { legendLabels: () => [], format: f4, ...options });
	const datasets = (cfg: PumpChartConfig) => cfg.data.datasets as Dataset[];
	const familyOf = (cfg: PumpChartConfig) => datasets(cfg).filter((d) => d.curveFamily === true);
	/** Runs joined as the chart joins them: a point without a head between runs (a gap). */
	const joined = (runs: readonly { x: number; y: number }[][]) =>
		runs.flatMap((run, i) => [...(i ? [{ x: run[0]!.x, y: null }] : []), ...run]);
	/** The tooltip's line for a point of a dataset (screen only). */
	const tooltip = (cfg: PumpChartConfig, dataset: Dataset, raw: { x: number; y: number }) =>
		(
			cfg.options!.plugins!.tooltip as {
				callbacks: { label: (item: unknown) => string };
			}
		).callbacks.label({ raw, dataset });

	it('draws each other case’s curve slate at 1.5 px, solid inside its data and [6, 4] beyond it, gaps at null flows, under every line; the rings stay on top', () => {
		const { data } = lineupView('');
		const cfg = config(data);
		const family = familyOf(cfg);
		const expected = data.otherCurves.flatMap((c) => [
			...(c.solid.length ? [{ number: c.number, data: joined(c.solid), dash: undefined }] : []),
			...(c.beyond.length ? [{ number: c.number, data: joined(c.beyond), dash: [6, 4] }] : [])
		]);
		expect(
			family.map((d) => ({ number: d.curveNumber, data: d.data, dash: d.borderDash }))
		).toEqual(expected);
		// Both kinds are drawn: the beyond runs are dashed (the shown curve's rule, §9.2).
		expect(family.some((d) => d.borderDash === undefined)).toBe(true);
		expect(family.some((d) => Array.isArray(d.borderDash))).toBe(true);
		for (const d of family) {
			expect(d).toMatchObject({
				yAxisID: 'y',
				borderColor: CHART_COLORS.slate,
				backgroundColor: CHART_COLORS.slate,
				borderWidth: 1.5,
				pointRadius: 0,
				spanGaps: false,
				order: 1
			});
		}
		// "1 of 4 running" has no flow at its 45 m rise: the dataset never reaches it.
		const low = data.otherCurves.find((c) => c.key === 'S3')!;
		const lowSets = family.filter((d) => d.curveNumber === low.number);
		expect(lowSets.flatMap((d) => d.data as { y: number | null }[]).some((p) => p.y === 45)).toBe(
			false
		);
		// Synthetic: a point without a flow in the middle of a curve breaks its line there.
		const view = lineupView('', {
			edit: (v) => {
				if (v.key !== 'S2' || v.group?.status !== 'ready') return v;
				const response = structuredClone(v.group.response);
				const sorted = [...response.points].sort((a, b) => a.head - b.head);
				sorted[10]!.flow = null;
				return { ...v, group: { status: 'ready', response } };
			}
		});
		const gapped = familyOf(config(view.data)).filter((d) => d.curveNumber === 2);
		const nulls = gapped
			.flatMap((d) => d.data as { y: number | null }[])
			.filter((p) => p.y === null);
		expect(nulls.length).toBeGreaterThan(
			familyOf(cfg)
				.filter((d) => d.curveNumber === 2)
				.flatMap((d) => d.data as { y: number | null }[])
				.filter((p) => p.y === null).length
		);
		// After the group curve, before the group system curve; the rings last, on top.
		const labels = datasets(cfg).map((d) => d.label);
		expect(labels.indexOf(family[0]!.label!)).toBe(labels.indexOf(GROUP_BEYOND_LABEL) + 1);
		expect(labels.indexOf(GROUP_SYSTEM_CURVE_LABEL)).toBe(
			labels.indexOf(GROUP_BEYOND_LABEL) + family.length + 1
		);
		const rings = datasets(cfg).filter((d) => d.otherCase === true);
		expect(rings).toHaveLength(data.others.length);
		for (const r of rings) expect(r.order).toBe(-1);
		expect(datasets(cfg).filter((d) => d.order === 1)).toEqual(family);
		// Without the family nothing of it is there (4d's configuration).
		expect(familyOf(config(lineupView('', { without: true }).data))).toEqual([]);
	});

	it('labels each curve’s tooltip by its case: the full form from 640 px, the short form on a phone’s screen, a stale case “as last solved”', () => {
		const { data } = lineupView('', { stale: ['S2'] });
		const point = { x: 12.5, y: 30 };
		const line = (label: string) => `${label}: 12.5 L/s, 30 m`;
		const screen = familyOf(config(data));
		const phone = familyOf(config(data, { compactLabels: true }));
		expect(screen.map((d) => d.curveNumber)).toEqual(phone.map((d) => d.curveNumber));
		const byNumber = (sets: Dataset[], n: number) => sets.find((d) => d.curveNumber === n)!;
		expect(tooltip(config(data), byNumber(screen, 1), point)).toBe(
			line(`1 · ${NAMES.S1}: group curve, 3 running`)
		);
		expect(tooltip(config(data), byNumber(screen, 2), point)).toBe(
			line(`2 · ${NAMES.S2} (out of date): group curve, as last solved: 2 running`)
		);
		expect(tooltip(config(data), byNumber(screen, 3), point)).toBe(
			line(`3 · ${NAMES.S3}: group curve, 1 running`)
		);
		expect(tooltip(config(data, { compactLabels: true }), byNumber(phone, 1), point)).toBe(
			line('1 · 3 running: group curve')
		);
		expect(tooltip(config(data, { compactLabels: true }), byNumber(phone, 2), point)).toBe(
			line('2 · as last solved: 2 running: group curve')
		);
		// Every dataset of a case carries its label, the beyond part's too.
		for (const c of data.otherCurves) {
			for (const d of screen.filter((x) => x.curveNumber === c.number))
				expect(d.label).toBe(c.label);
			for (const d of phone.filter((x) => x.curveNumber === c.number))
				expect(d.label).toBe(c.shortLabel);
		}
	});

	it('carries them into the image with their full labels, and its legend collapses the family into one entry where the page lists it', () => {
		const { data } = lineupView('', { stale: ['S2'] });
		const cfg = config(data, { forImage: true, compactLabels: true });
		const family = familyOf(cfg);
		expect(family.map((d) => d.label)).toEqual(familyOf(config(data)).map((d) => d.label));
		expect(family.find((d) => d.curveNumber === 2)!.label).toBe(
			`2 · ${NAMES.S2} (out of date): group curve, as last solved: 2 running`
		);
		// Chart.js's own items, sorted as it sorts them (by `order`, then the datasets' order).
		const sets = datasets(cfg);
		const sorted = sets
			.map((d, i) => ({ d, i }))
			.sort((a, b) => ((a.d.order as number) ?? 0) - ((b.d.order as number) ?? 0) || a.i - b.i);
		const cfgWith = config(data, {
			forImage: true,
			legendLabels: () =>
				sorted.map(({ d, i }) => ({
					text: d.label,
					datasetIndex: i,
					strokeStyle: d.borderColor,
					lineDash: d.borderDash ?? []
				}))
		});
		const shown = cfgWith.options!.plugins!.legend!.labels!.generateLabels!({
			data: cfgWith.data
		} as never).filter((item) =>
			cfgWith.options!.plugins!.legend!.labels!.filter!(item, cfgWith.data)
		);
		// The image's legend lists what the page's does, in its order: one entry for the family.
		expect(shown.map((item) => item.text)).toEqual(groupLegend(data).map((i) => i.label));
		const entry = shown.find((item) => item.text === OTHER_CURVES_LEGEND)!;
		expect(entry).toMatchObject({
			strokeStyle: CHART_COLORS.slate,
			fillStyle: CHART_COLORS.slate,
			lineDash: [],
			pointStyle: 'line'
		});
		expect(OTHER_CURVES_LEGEND).toBe(OTHER_CURVES_LABEL);
		expect(cfgWith.options!.plugins!.tooltip).toEqual({ enabled: false });
	});

	it('sets the axes from the data: x min and max where other curves would widen it, y max while they are drawn; neither without them', () => {
		const axes = (data: GroupChartData) => {
			const scales = config(data).options!.scales as Record<string, Record<string, unknown>>;
			return [scales.x!.min, scales.x!.max, scales.y!.max];
		};
		// The base shown: other curves' shutoff round-off (−10⁻¹¹ L/s) below zero; y near the pumps.
		expect(axes(lineupView('').data)).toEqual([0, undefined, 50]);
		// "1 of 4 running" shown: cut at 100 L/s.
		expect(axes(lineupView('S3').data)).toEqual([0, 100, 50]);
		// "2 of 4 running" shown: its own group curve has the round-off too, so x min is Chart.js's,
		// as on 4d's chart (the family does not widen it).
		expect(axes(lineupView('S2').data)).toEqual([undefined, 120, 50]);
		// Without the family: Chart.js's own range (4b's and 4d's charts).
		expect(axes(lineupView('', { without: true }).data)).toEqual([undefined, undefined, undefined]);
		const scales = config(lineupView('', { without: true }).data).options!.scales as Record<
			string,
			object
		>;
		expect('min' in scales.x! || 'max' in scales.x! || 'max' in scales.y!).toBe(false);
	});

	it('keeps every marker whole at the plot’s edges, those the axes set included (Chart.js draws it)', () => {
		// Synthetic: Pump P4 on and carrying no flow (§3.5, decision 14), held at zero flow, with
		// the base shown: the family's round-off sets x min 0 and the family sets y max 50 m.
		const view = lineupView('');
		const held = view.members.map((m) =>
			m.id === 'P4'
				? { ...m, result: { ...m.result, status: 'no_flow' as const, operatingFlow: 0 } }
				: m
		);
		const data = groupChartData(held, lineupPrefs, view.response, view.system, view.others, 3);
		expect([data.xMin, data.yMax]).toEqual([0, 50]);
		expect(data.points.find((p) => p.id === 'P4')).toMatchObject({ held: true, point: { x: 0 } });
		const chart = new Chart(
			fakeCanvas(800, 500) as never,
			{
				...config(data, { curveLabels: tools }),
				platform: BasicPlatform
			} as never
		);
		try {
			const area = chart.chartArea;
			const markers = datasets(config(data)).flatMap((d, i) => (d.showLine === false ? [i] : []));
			// The members' points, the Group point and the rings.
			expect(markers).toHaveLength(data.points.length + 1 + data.others.length);
			const marker = (i: number) => {
				const d = chart.data.datasets[i] as unknown as Record<string, number> & { label: string };
				// Where Chart.js clips the dataset: its clip's allowance (px) beyond each edge.
				const clip = (chart.getDatasetMeta(i) as unknown as { _clip: Record<string, number> })
					._clip;
				// A marker reaches its radius (hovered, its hover radius) and half its border out.
				const r = Math.max(d.pointRadius!, d.pointHoverRadius!) + d.borderWidth! / 2;
				return { label: d.label, clip, r, elements: chart.getDatasetMeta(i).data };
			};
			// P4's diamond is centred on the plot's left edge, and drawn whole.
			const p4 = markers.find(
				(i) => chart.data.datasets[i]!.label === 'Pump P4, held at zero flow'
			)!;
			expect(chart.getDatasetMeta(p4).data[0]!.x).toBeCloseTo(area.left, 6);
			for (const { label, clip, r, elements } of markers.map(marker)) {
				for (const el of elements) {
					expect(el.x - r, label).toBeGreaterThanOrEqual(area.left - clip.left!);
					expect(el.x + r, label).toBeLessThanOrEqual(area.right + clip.right!);
					expect(el.y - r, label).toBeGreaterThanOrEqual(area.top - clip.top!);
					expect(el.y + r, label).toBeLessThanOrEqual(area.bottom + clip.bottom!);
				}
			}
			// Every marker keeps its extent beyond every edge, wherever it is drawn.
			for (const { label, clip, r } of markers.map(marker)) {
				for (const side of ['left', 'right', 'top', 'bottom'] as const) {
					expect(clip[side], `${label}, ${side}`).toBeGreaterThanOrEqual(r);
				}
			}
		} finally {
			chart.destroy();
		}
		// On 4d's chart, no bound set, it is the allowance Chart.js gives a point by itself.
		const without = lineupView('', { without: true });
		const plain = config(
			groupChartData(held, lineupPrefs, without.response, without.system, without.others)
		);
		expect(plain.options!.scales!.x!.min).toBeUndefined();
		const unclipped = {
			...plain,
			data: {
				datasets: datasets(plain).map((d) =>
					Object.fromEntries(Object.entries(d).filter(([key]) => key !== 'clip'))
				)
			}
		} as unknown as PumpChartConfig;
		const clips = (cfg: PumpChartConfig) => {
			const drawn = new Chart(
				fakeCanvas(800, 500) as never,
				{
					...cfg,
					platform: BasicPlatform
				} as never
			);
			const out = cfg.data.datasets.map(
				(_, i) => (drawn.getDatasetMeta(i) as unknown as { _clip: unknown })._clip
			);
			drawn.destroy();
			return out;
		};
		expect(datasets(plain).filter((d) => 'clip' in d)).toHaveLength(
			data.points.length + 1 + data.others.length
		);
		expect(clips(plain)).toEqual(clips(unclipped));
	});

	it('draws each other case’s curve to the plot’s edge where x max cuts it, every point inside drawn (Chart.js draws it)', () => {
		// Each curve runs in rise order, so its flow falls (§9.2). Chart.js takes a line's data as
		// sorted by x without its own parsing, and where x max is set it then draws only the index
		// range a binary search finds: the base's curve lost all but its first two points with
		// "1 of 4 running" shown (library-facts.md, Chart.js 4.5.1).
		for (const [shown, xMax] of [
			['S3', 100],
			['S2', 120]
		] as const) {
			const { data } = lineupView(shown);
			expect(data.xMax).toBe(xMax);
			const chart = new Chart(
				fakeCanvas(800, 500) as never,
				{ ...config(data, { curveLabels: tools }), platform: BasicPlatform } as never
			);
			try {
				// Drawn again with the same axes: Chart.js then updates only the range it draws.
				chart.update();
				const x = chart.scales.x!;
				expect(x.max).toBe(xMax);
				const family = chart.data.datasets.flatMap((d, i) =>
					(d as unknown as Dataset).curveFamily === true ? [i] : []
				);
				let cut = 0;
				for (const i of family) {
					const label = `${chart.data.datasets[i]!.label} (${shown}, dataset ${i})`;
					const points = chart.data.datasets[i]!.data as { x: number; y: number | null }[];
					const meta = chart.getDatasetMeta(i);
					const { _drawStart: start, _drawCount: count } = meta.controller as unknown as {
						_drawStart: number;
						_drawCount: number;
					};
					if (points.some((p) => p.x > xMax)) cut++;
					// Each point inside the plot, and its neighbours, so the line reaches the edge.
					const wanted = new Set(
						points.flatMap((p, k) =>
							p.y !== null && p.x >= x.min && p.x <= xMax ? [k - 1, k, k + 1] : []
						)
					);
					for (const k of wanted) {
						if (k < 0 || k >= points.length || points[k]!.y === null) continue;
						expect(k, label).toBeGreaterThanOrEqual(start);
						expect(k, label).toBeLessThan(start + count);
						expect((meta.data[k] as unknown as { skip: boolean }).skip, label).toBe(false);
					}
				}
				// Some curve is cut at x max, the base's (4 running) among them with S3 shown.
				expect(cut).toBeGreaterThan(0);
			} finally {
				chart.destroy();
			}
		}
	});

	it('sets x min only when the other curves alone reach below zero flow', () => {
		const { data } = lineupView('');
		const below = data.otherCurves.flatMap((c) =>
			[...c.solid, ...c.beyond].flat().filter((p) => p.x < 0)
		);
		expect(below.length).toBeGreaterThan(0);
		for (const p of below) expect(p.x).toBeGreaterThan(-1e-9);
		expect(data.xMin).toBe(0);
		// Everything else at or above zero flow: the members, the curve, the system curve, the rings.
		const else_ = [
			...data.lines.flatMap((l) => [...l.curve, ...l.extrapolated.flat()]),
			...data.points.map((p) => p.point),
			...[...data.curve!.solid, ...data.curve!.beyond].flat(),
			...(data.system ?? []).filter((p): p is { x: number; y: number } => p.y !== null),
			data.station!.point,
			...data.others.map((r) => r.point)
		];
		expect(Math.min(...else_.map((p) => p.x))).toBeGreaterThanOrEqual(0);
		// Synthetic: this case's own group system curve below zero flow too: Chart.js's range.
		const view = lineupView('');
		const reaching = structuredClone(view.system);
		reaching.systemPoints[0]!.flow = -0.001;
		const own = groupChartData(view.members, lineupPrefs, view.response, reaching, view.others, 4);
		expect(own.xMin).toBeNull();
		// Without the family: none.
		expect(lineupView('', { without: true }).data.xMin).toBeNull();
	});

	it('draws each curve’s label where placeCurveLabels puts it, clear of every marker, label and tag, in its colour, and tells where', () => {
		const { data } = lineupView('');
		const told: CurveLabelsDrawn[] = [];
		const cfg = config(data, {
			curveLabels: tools,
			onlabels: (d: CurveLabelsDrawn) => told.push(d)
		});
		const chart = drawnChart(cfg);
		chart.draw();
		expect(told).toHaveLength(1);
		const drawn = told[0]!;
		// The obstacles: each point's marker, each member's and the Group point's label, each ring's
		// tag and the group system curve's tag, as drawn.
		const points = datasets(cfg).filter((d) => typeof d.caseLabel === 'string');
		expect(drawn.obstacles.filter((o) => o.kind === 'marker').map((o) => o.text)).toEqual(
			points.map((d) => d.caseLabel)
		);
		expect(drawn.obstacles.filter((o) => o.kind === 'ring').map((o) => o.text)).toEqual(
			data.others.map((r) => r.tag)
		);
		expect(drawn.obstacles.filter((o) => o.kind === 'label').map((o) => o.text)).toEqual([
			...data.points.map((p) => p.name),
			data.station!.tag
		]);
		expect(drawn.obstacles.filter((o) => o.kind === 'curve').map((o) => o.text)).toEqual([
			GROUP_SYSTEM_TAG
		]);
		for (const o of drawn.obstacles) {
			const written = chart.written.find((w) => w.text === o.text)!;
			if (o.kind === 'marker') {
				const ds = points.find((d) => d.caseLabel === o.text)!;
				const r = (ds.pointRadius as number) + (ds.borderWidth as number) / 2;
				expect(o.box.right - o.box.left).toBeCloseTo(2 * r, 9);
				expect(o.box.bottom - o.box.top).toBeCloseTo(2 * r, 9);
			} else {
				expect(o.box).toEqual({
					left: written.x,
					right: written.x + written.text.length * 6,
					top: written.y - 12,
					bottom: written.y + 3
				});
			}
		}
		// The anchors from the curves' own pixels, placed by the pure function with them.
		const plot = drawn.plot;
		const px = (p: { x: number; y: number }) => ({ x: chart.px(p.x), y: chart.py(p.y) });
		const inputs: CurveLabelInput[] = [
			...data.otherCurves.map((c) => ({
				anchor: curveAnchor([...c.solid, ...c.beyond].flat().map(px), plot),
				k: c.k,
				numbers: [c.number]
			})),
			{
				anchor: curveAnchor([...data.curve!.solid, ...data.curve!.beyond].flat().map(px), plot),
				k: 4,
				numbers: []
			}
		];
		const expected = placeCurveLabels(
			inputs,
			drawn.obstacles.map((o) => o.box),
			plot,
			(text) => text.length * 6
		);
		expect(drawn.labels).toEqual(expected.labels);
		expect(drawn.leftOut).toBe(expected.leftOut);
		expect(drawn.labels.map((l) => l.text)).toContain('4 running (this case)');
		// Written where placed: other cases' in slate, this case's in ink.
		for (const label of drawn.labels) {
			expect(chart.written).toContainEqual({
				text: label.text,
				x: label.x,
				y: label.y,
				color: label.shown ? CHART_COLORS.ink : CHART_COLORS.slate,
				font: '12px system-ui, sans-serif'
			});
		}
		// Clear of every obstacle and of each other.
		for (const [i, label] of drawn.labels.entries()) {
			for (const o of drawn.obstacles) expect(boxesMeet(label.box, o.box), o.text).toBe(false);
			for (const other of drawn.labels.slice(i + 1))
				expect(boxesMeet(label.box, other.box)).toBe(false);
		}
		expect(drawn.x).toEqual({ min: chart.x.min, max: chart.x.max });
		expect(drawn.y).toEqual({ min: 0, max: 50 });
	});

	it('keeps each label off every ring’s tag, marker and point’s label where they are in the way, or leaves it out', () => {
		// m4_labels.py's plots: a 390 px phone and a 1280 × 800 desktop.
		const PHONE = { left: 50, right: 328, top: 8, bottom: 211 };
		const DESKTOP = { left: 55, right: 554, top: 8, bottom: 243 };
		const drawn = (shown: string, plot: PxBox, compact: boolean) => {
			const { data } = lineupView(shown);
			const told: CurveLabelsDrawn[] = [];
			const cfg = config(data, {
				curveLabels: tools,
				compactLabels: compact,
				onlabels: (d: CurveLabelsDrawn) => told.push(d)
			});
			const chart = drawnChart(cfg, { plot });
			chart.draw();
			return { data, chart, placed: told[0]! };
		};
		// "2 of 4 running" on a phone; "1 of 4 running" on a phone and on a desktop.
		const s2 = drawn('S2', PHONE, true);
		const s3 = drawn('S3', PHONE, true);
		const views = [s2, s3, drawn('S3', DESKTOP, false)];
		for (const { data, placed } of views) {
			// Every curve labelled or counted: the other cases' and this case's.
			expect(placed.labels.flatMap((l) => l.curves).length + placed.leftOut).toBe(
				data.otherCurves.length + 1
			);
			expect(placed.leftOut + placed.labels.filter((l) => l.row > 0).length).toBeGreaterThan(0);
			for (const label of placed.labels) {
				for (const o of placed.obstacles) {
					expect(boxesMeet(label.box, o.box), `${label.text} over ${o.kind} ${o.text}`).toBe(false);
				}
			}
		}
		// What is in the way, by §9.3's geometry (right-aligned 4 px left of its anchor, 4 px above
		// it, 14 px a row; 6 px a character here): the kinds of obstacle a box meets.
		const kinds = (placed: CurveLabelsDrawn, box: PxBox) =>
			[...new Set(placed.obstacles.filter((o) => boxesMeet(box, o.box)).map((o) => o.kind))].sort();
		const down = (box: PxBox, rows: number) => ({
			...box,
			top: box.top + rows * CURVE_LABEL_ROW,
			bottom: box.bottom + rows * CURVE_LABEL_ROW
		});
		// "1 of 4 running", phone: the base's "4 running" two rows up, past ring 1's marker and tag.
		const four = s3.placed.labels.find((l) => l.text === '4 running')!;
		expect(four.row).toBe(2);
		expect(kinds(s3.placed, down(four.box, 1))).toEqual(['marker', 'ring']);
		// "2 of 4 running", phone: the base's "4 running" left out; at each of its rows a ring's
		// tag or the Group point's label is in the way.
		expect(s2.placed.leftOut).toBe(1);
		expect(s2.placed.labels.map((l) => l.text)).not.toContain('4 running');
		const base = s2.data.otherCurves.find((c) => c.key === '')!;
		const plot = s2.placed.plot;
		const anchor = curveAnchor(
			[...base.solid, ...base.beyond]
				.flat()
				.map((p) => ({ x: s2.chart.px(p.x), y: s2.chart.py(p.y) })),
			plot
		)!;
		const width = '4 running'.length * 6;
		const left = Math.max(plot.left + 2, anchor.x - 4 - width);
		const rows = [0, 1, 2].map((row) => {
			const bottom = anchor.y - 4 - row * CURVE_LABEL_ROW;
			return kinds(s2.placed, { left, right: left + width, top: bottom - CURVE_LABEL_ROW, bottom });
		});
		for (const met of rows) expect(met.length).toBeGreaterThan(0);
		expect([...new Set(rows.flat())].sort()).toEqual(expect.arrayContaining(['label', 'ring']));
		const groupTag = s2.data.station!.tag;
		expect(
			s2.placed.obstacles.some(
				(o) =>
					o.kind === 'label' &&
					o.text === groupTag &&
					[0, 1, 2].some((row) => {
						const bottom = anchor.y - 4 - row * CURVE_LABEL_ROW;
						return boxesMeet(
							{ left, right: left + width, top: bottom - CURVE_LABEL_ROW, bottom },
							o.box
						);
					})
			)
		).toBe(true);
	});

	it('labels this case’s curve “(this case)” where its end lies just right of equal counts’ (“Pump P1 off” shown)', () => {
		// m4_labels.py's desktop plot; the 3-running siblings end a pixel left of this case's end.
		const DESKTOP = { left: 55, right: 554, top: 8, bottom: 243 };
		for (const shown of ['S4', 'S5', 'S6']) {
			const { data } = lineupView(shown);
			const told: CurveLabelsDrawn[] = [];
			const cfg = config(data, {
				curveLabels: tools,
				onlabels: (d: CurveLabelsDrawn) => told.push(d)
			});
			drawnChart(cfg, { plot: DESKTOP }).draw();
			const own = told[0]!.labels.filter((l) => l.shown);
			expect(
				own.map((l) => [l.text, l.curves]),
				shown
			).toEqual([['3 running (this case)', [data.otherCurves.length]]]);
			// The siblings' label names only their numbers, never this case's count among them.
			const siblings = told[0]!.labels.find((l) => !l.shown && l.text.endsWith('· 3 running'))!;
			expect(siblings.curves).not.toContain(data.otherCurves.length);
		}
	});

	it('words the labels by view: a phone’s screen the count, the image the numbers at 14 px', () => {
		const { data } = lineupView('');
		const texts = (options: object) => {
			const told: CurveLabelsDrawn[] = [];
			const cfg = config(data, {
				curveLabels: tools,
				onlabels: (d: CurveLabelsDrawn) => told.push(d),
				...options
			});
			const chart = drawnChart(cfg, { plot: { left: 50, right: 750, top: 10, bottom: 400 } });
			chart.draw();
			const labels = told[0]!.labels;
			return {
				texts: labels.map((l) => l.text).sort(),
				fonts: [
					...new Set(
						chart.written.filter((w) => labels.some((l) => l.text === w.text)).map((w) => w.font)
					)
				]
			};
		};
		expect(texts({ compactLabels: true })).toEqual({
			texts: ['1 running', '2 running', '3 running', '4 running'],
			fonts: ['12px system-ui, sans-serif']
		});
		const image = texts({ compactLabels: true, forImage: true });
		expect(image).toEqual({
			texts: ['1, 4, 5, 6 · 3 running', '2 · 2 running', '3 · 1 running', '4 running (this case)'],
			fonts: ['14px system-ui, sans-serif']
		});
		expect(texts({})).toEqual({ ...image, fonts: ['12px system-ui, sans-serif'] });
	});

	it('leaves out a label that finds no room, and tells the count; draws none without the family or the page’s placement', () => {
		const { data } = lineupView('S3');
		const told: CurveLabelsDrawn[] = [];
		const cfg = config(data, {
			curveLabels: tools,
			onlabels: (d: CurveLabelsDrawn) => told.push(d)
		});
		// A plot 60 px wide: the labels, clamped at its left edge, crowd three rows and no more.
		drawnChart(cfg, { plot: { left: 50, right: 110, top: 10, bottom: 60 } }).draw();
		expect(told[0]!.leftOut).toBeGreaterThan(0);
		const curves = told[0]!.labels.flatMap((l) => l.curves).length;
		expect(curves + told[0]!.leftOut).toBe(data.otherCurves.length + 1);
		// Without the family, or without the placement passed in: no curve label, none left out.
		for (const [d, options] of [
			[lineupView('S3', { without: true }).data, { curveLabels: tools }],
			[data, {}]
		] as const) {
			const seen: CurveLabelsDrawn[] = [];
			const plain = config(d, { ...options, onlabels: (x: CurveLabelsDrawn) => seen.push(x) });
			const chart = drawnChart(plain);
			chart.draw();
			expect(seen[0]!).toMatchObject({ labels: [], leftOut: 0 });
			expect(chart.written.some((w) => / running( \(this case\))?$/.test(w.text))).toBe(false);
		}
	});
});

/**
 * A canvas for Chart.js in the `server` project (no DOM): Chart.js's BasicPlatform draws on its
 * context, every call a no-op but text measured at 6 px a character.
 */
function fakeCanvas(width: number, height: number) {
	const ctx: Record<string | symbol, unknown> = new Proxy({} as Record<string | symbol, unknown>, {
		get(target, prop) {
			if (prop in target) return target[prop];
			if (prop === 'measureText') return (text: string) => ({ width: text.length * 6 });
			if (prop === 'getLineDash') return () => [];
			return () => undefined;
		}
	});
	const canvas = { width, height, style: {}, getContext: () => ctx };
	ctx.canvas = canvas;
	return canvas;
}

/** Two boxes meet (px; y down): they share area. */
function boxesMeet(a: PxBox, b: PxBox): boolean {
	return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
}
