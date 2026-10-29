/**
 * The group system curve on the Pumps together card (CLAUDE.md D21, slice 4b, proposal
 * pump-groups.md §3.4 and §7), on real API responses: the shared fixture's `systemCurve`
 * answers (__fixtures__/pump-groups-input.json, apps/api/tests/fixtures/pump_groups_input.py).
 * The orange line and its gaps, the Group point's label by both duty checks, "Read along the
 * curves" read exactly from the response, the notes' words and the data table's rows. Numbers in
 * the expected words are the fixture's, formatted as the card formats them.
 */
import { describe, expect, it } from 'vitest';
import type {
	Flag,
	Project,
	PumpGroupCurveResponse,
	PumpResult,
	SolvedState,
	TopologyIssue,
	UnitPreferences
} from '$lib/api/types';
import type { GroupCurveState, GroupSystemCurveState } from '$lib/state/project.svelte';
import fixture from './__fixtures__/pump-groups-input.json';
import { ratedCurveRange } from './pump-chart';
import {
	CHART_COLORS,
	GROUP_SYSTEM_CURVE_LABEL,
	GROUP_SYSTEM_TAG,
	pumpGroupConfig,
	type PumpChartConfig
} from './pump-chart-config';
import {
	GROUP_SYSTEM,
	GROUP_SYSTEM_LABEL,
	groupChartData,
	groupLegend,
	groupNoteLines,
	groupNotes,
	groupReadout,
	groupSummary,
	groupSystemRows,
	systemDutyCheckState,
	type GroupMemberInput
} from './pump-group-chart';
import { systemPointNote } from './system-curve-text';
import { formatNumber, fromSI } from './units';

interface FixtureCase {
	name: string;
	project: Project;
	memberIds: string[];
	solve: { solvedState: SolvedState };
	groupCurve: { status: number; body: unknown };
	systemCurve: { status: number; body: unknown } | null;
}
const cases = fixture.cases as unknown as FixtureCase[];
const named = (name: string) => cases.find((c) => c.name === name)!;

function membersOf(c: FixtureCase): GroupMemberInput[] {
	const s = c.solve.solvedState;
	return c.memberIds.map((id, slot) => {
		const pump = c.project.components.find((x) => x.id === id)!;
		return {
			id,
			name: pump.name,
			result: s.pumpResults[id] as PumpResult,
			ratedRange: ratedCurveRange(c.project, id),
			curveId: pump.type === 'pump' ? pump.curveId : null,
			slot,
			flags: (s.flags as Flag[]).filter((f) => f.componentId === id)
		};
	});
}
const groupOf = (c: FixtureCase) =>
	c.groupCurve.status === 200 ? (c.groupCurve.body as PumpGroupCurveResponse) : null;
const systemOf = (c: FixtureCase) => c.systemCurve!.body as PumpGroupCurveResponse;
const prefsOf = (c: FixtureCase): UnitPreferences => c.project.settings.units;
const nameOf = (c: FixtureCase) => (id: string) =>
	c.project.components.find((x) => x.id === id)?.name ?? id;
const f4 = (v: number) => formatNumber(v, 4);
const m = (v: number) => `${f4(v)} m`;

/** The group curve's state of a fixture case: its answer, a response or a refusal. */
function groupState(c: FixtureCase): GroupCurveState {
	if (c.groupCurve.status === 200) return { status: 'ready', response: groupOf(c)! };
	const body = c.groupCurve.body as { message: string; issues: TopologyIssue[] };
	return { status: 'refused', message: body.message, issues: body.issues };
}

/**
 * The card's data and notes for a fixture case with both answers (or the states given; a null
 * system: not asked for).
 */
function card(
	c: FixtureCase,
	group: GroupCurveState = groupState(c),
	asked: GroupSystemCurveState | null = { status: 'ready', response: systemOf(c) }
) {
	const system = asked ?? undefined;
	const members = membersOf(c);
	const data = groupChartData(
		members,
		prefsOf(c),
		group.status === 'ready' ? group.response : null,
		system?.status === 'ready' ? system.response : null
	);
	const notes = groupNotes({
		data,
		members,
		state: group,
		system,
		project: c.project,
		prefs: prefsOf(c)
	});
	return { data, notes };
}

const config = (data: ReturnType<typeof groupChartData>, values = {}): PumpChartConfig =>
	pumpGroupConfig(data, { legendLabels: () => [], format: f4, ...values });
type Dataset = PumpChartConfig['data']['datasets'][number] & { caseLabel?: string };
const datasets = (cfg: PumpChartConfig) => cfg.data.datasets as Dataset[];

describe('the group system curve on the chart', () => {
	it('is the response’s points in flow order, in display units, in the system orange', () => {
		const c = named('series');
		const system = systemOf(c);
		const { data } = card(c);
		const sorted = [...system.systemPoints].sort((a, b) => a.flow - b.flow);
		expect(data.system).toEqual(
			sorted.map((p) => ({ x: fromSI(p.flow, 'gpm'), y: fromSI(p.head!, 'ft') }))
		);
		expect(data.systemMissing).toBe(0);
		expect(data.systemTotal).toBe(system.systemPoints.length);
		// The orange is the pump chart's system orange: one meaning in the Pumps view.
		expect(GROUP_SYSTEM).toBe(CHART_COLORS.system);
		expect(GROUP_SYSTEM_LABEL).toBe(GROUP_SYSTEM_CURVE_LABEL);
		const set = datasets(config(data)).find((d) => d.label === GROUP_SYSTEM_CURVE_LABEL)!;
		expect(set).toMatchObject({
			borderColor: CHART_COLORS.system,
			borderWidth: 2,
			spanGaps: false,
			curveTag: GROUP_SYSTEM_TAG
		});
		expect(set.data).toBe(data.system);
		expect(groupLegend(data).find((i) => i.key === 'group-system')).toEqual({
			key: 'group-system',
			label:
				"Group system curve (the rest of the network between the station's inlet and outlet, station's flow)",
			kind: 'line',
			color: GROUP_SYSTEM,
			dash: []
		});
	});

	it('has a gap at each point without a rise, never bridged (an FCV outside: beyond its limit)', () => {
		const c = named('fcv-outside');
		const system = systemOf(c);
		const { data } = card(c);
		const missing = system.systemPoints.filter((p) => p.head === null);
		expect(missing.length).toBeGreaterThan(0);
		expect(new Set(missing.map((p) => p.reason))).toEqual(new Set(['beyond_limit']));
		expect(data.systemMissing).toBe(missing.length);
		const gaps = data.system!.filter((p) => p.y === null).map((p) => p.x);
		expect(gaps).toEqual(missing.map((p) => fromSI(p.flow, 'L/s')).sort((a, b) => a - b));
		// Every point above the FCV's 60 L/s, and none below.
		expect(gaps.every((x) => x > 60)).toBe(true);
		expect(data.system!.filter((p) => p.y !== null).every((p) => p.x <= 60)).toBe(true);
		const set = datasets(config(data)).find((d) => d.label === GROUP_SYSTEM_CURVE_LABEL)!;
		expect(set.spanGaps).toBe(false);
		expect((set.data as { y: number | null }[]).filter((p) => p.y === null)).toHaveLength(
			missing.length
		);
	});

	it('is not drawn when no point has a rise, and is absent without its response', () => {
		const c = named('parallel-ideal');
		const none = structuredClone(systemOf(c));
		for (const p of none.systemPoints) Object.assign(p, { head: null, reason: 'not_computed' });
		const { data } = card(c, groupState(c), { status: 'ready', response: none });
		expect(datasets(config(data)).map((d) => d.label)).not.toContain(GROUP_SYSTEM_CURVE_LABEL);
		expect(groupLegend(data).map((i) => i.key)).not.toContain('group-system');
		const without = card(c, groupState(c), null).data;
		expect(without.system).toBeNull();
		expect(without.systemTotal).toBe(0);
	});
});

describe("the Group point: the curves' crossing only when both duty checks agree", () => {
	it('both agree: labelled as the crossing, on the chart and in the legend', () => {
		const c = named('parallel-ideal');
		expect(groupOf(c)!.dutyCheck!.agrees).toBe(true);
		expect(systemOf(c).systemDutyCheck!.agrees).toBe(true);
		const { data } = card(c);
		expect(data.station).toMatchObject({
			onCurve: true,
			onSystem: true,
			crossing: true,
			label: 'Group duty, where the group curve and the group system curve cross',
			tag: 'Group (crossing)'
		});
		expect(datasets(config(data)).at(-1)).toMatchObject({
			label: 'Group duty, where the group curve and the group system curve cross',
			caseLabel: 'Group (crossing)'
		});
		expect(groupLegend(data).at(-1)).toMatchObject({
			label: 'Group duty, where the group curve and the group system curve cross'
		});
	});

	it('one check disagrees: on the curve that agrees, not the crossing; neither: the solve’s', () => {
		const c = named('parallel-crane');
		const group = structuredClone(groupOf(c)!);
		const system = structuredClone(systemOf(c));
		system.systemDutyCheck!.agrees = false;
		const labelOf = (g: PumpGroupCurveResponse, s: PumpGroupCurveResponse) =>
			card(c, { status: 'ready', response: g }, { status: 'ready', response: s }).data.station!;
		expect(labelOf(group, system)).toMatchObject({
			crossing: false,
			label: 'Group duty, on the group curve',
			tag: 'Group'
		});
		const agrees = systemOf(c);
		group.dutyCheck!.agrees = false;
		expect(labelOf(group, agrees)).toMatchObject({
			crossing: false,
			label: 'Group duty, on the group system curve',
			tag: 'Group'
		});
		expect(labelOf(group, system)).toMatchObject({
			crossing: false,
			label: "Group duty (the solve's)",
			tag: 'Group'
		});
	});

	it('the group curve refused for a PRV inside: the duty from the system curve, on it', () => {
		const c = named('prv-inside');
		const system = systemOf(c);
		const { data } = card(c);
		expect(data.curve).toBeNull();
		expect(data.station).toMatchObject({
			point: { x: fromSI(system.duty!.flow, 'L/s'), y: system.duty!.head },
			onCurve: false,
			onSystem: true,
			crossing: false,
			label: 'Group duty, on the group system curve'
		});
		expect(datasets(config(data)).map((d) => d.label)).toContain(GROUP_SYSTEM_CURVE_LABEL);
	});

	it('the accessible name says where the Group point is and which curves are shown', () => {
		const c = named('parallel-ideal');
		const { data } = card(c);
		const summary = groupSummary(data, membersOf(c), groupOf(c), c.project, systemOf(c));
		expect(summary).toMatch(
			/from Tee T1 \(run inlet\) to Tee T2 \(run outlet\), on the group curve and the group system curve, where they cross; group curve shown; group system curve shown\.$/
		);
		const prv = named('prv-inside');
		const p = card(prv);
		expect(groupSummary(p.data, membersOf(prv), null, prv.project, systemOf(prv))).toMatch(
			/, on the group system curve; no group curve shown; group system curve shown\.$/
		);
	});
});

describe('Read along the curves', () => {
	it("gives every member's flow and the station's at each sample, exactly from the response", () => {
		const c = named('parallel-ideal');
		const response = groupOf(c)!;
		const readout = groupReadout(response, nameOf(c), prefsOf(c));
		const sorted = [...response.points].sort((a, b) => a.head - b.head);
		expect(readout).toHaveLength(sorted.length);
		for (const [i, p] of sorted.entries()) {
			const l = (q: number) => `${f4(q * 1000)} L/s`;
			const pa = p.members.find((x) => x.pumpId === 'PA')!;
			const pb = p.members.find((x) => x.pumpId === 'PB')!;
			const state = (x: typeof pa) =>
				x.status === 'running' ? '' : ` (${x.status === 'off' ? 'off' : 'no flow'})`;
			expect(readout[i]!.text).toBe(
				`At a rise of ${f4(p.head)} m: Pump PA ${l(pa.flow)}${state(pa)}, Pump PB ${l(pb.flow)}${state(pb)}, group ${l(p.flow!)}`
			);
			expect(readout[i]!.duty).toBe(p.isDuty);
			// Marked: each member's point (its flow, its own head) and the station's (its flow, the rise).
			expect(readout[i]!.mark).toEqual({
				rise: p.head,
				points: [
					...p.members.map((x) => ({ x: fromSI(x.flow, 'L/s'), y: x.head! })),
					{ x: fromSI(p.flow!, 'L/s'), y: p.head }
				]
			});
		}
		// PB stops on this curve: told as no flow, never as running at zero.
		expect(readout.some((r) => r.text.includes('Pump PB 0 L/s (no flow)'))).toBe(true);
	});

	it('in the display units (US), and at a rise without a flow it says so', () => {
		const c = named('series');
		const response = structuredClone(groupOf(c)!);
		const duty = response.points.find((p) => p.isDuty)!;
		const readout = groupReadout(response, nameOf(c), prefsOf(c));
		const at = readout.find((r) => r.duty)!;
		const gpm = (q: number) => `${f4(fromSI(q, 'gpm'))} gpm`;
		expect(at.text).toBe(
			`At a rise of ${f4(fromSI(duty.head, 'ft'))} ft: Pump PA ${gpm(duty.members[0]!.flow)}, Pump PB ${gpm(duty.members[1]!.flow)}, group ${gpm(duty.flow!)}`
		);
		Object.assign(duty, { flow: null, members: [], converged: false, reason: 'not_converged' });
		const gap = groupReadout(response, nameOf(c), prefsOf(c)).find((r) => r.duty)!;
		expect(gap.text).toBe(
			`At a rise of ${f4(fromSI(duty.head, 'ft'))} ft: no flow solved here; the data table says why.`
		);
		expect(gap.mark.points).toEqual([]);
	});

	it('marks the chart only on screen, never in the image', () => {
		const c = named('parallel-ideal');
		const { data } = card(c);
		const plugins = (cfg: PumpChartConfig) => (cfg.plugins ?? []).map((p) => p.id);
		expect(plugins(config(data, { readout: () => null }))).toEqual(['groupLabels', 'groupReadout']);
		expect(plugins(config(data))).toEqual(['groupLabels']);
		expect(plugins(config(data, { readout: () => null, forImage: true }))).toEqual(['groupLabels']);
	});
});

describe('the notes (screen and image)', () => {
	it("say what the group system curve is, between the station's ports, and that the curves cross", () => {
		const c = named('parallel-ideal');
		const { notes } = card(c);
		expect(notes.system).toBe(
			"The group's system curve is the rise the rest of the network needs between Tee T1 (run inlet) and Tee T2 (run outlet) at each total flow; it does not depend on how the pumps share the flow."
		);
		expect(notes.systemDuty).toEqual([
			"At the duty's flow the group system curve gives the solve's rise (within 0.5 % or 0.01 m): it passes through the Group point, where it crosses the group curve."
		]);
		expect(notes.systemCurve).toBeNull();
		expect(notes.axes).toBe(
			"Each pump's curve and point are drawn against the flow through that pump; the group curve, the group system curve and the Group point against the station's flow, the net flow into the station at its inlet."
		);
		// The image's footer: the same lines, in the figure's order.
		const lines = groupNoteLines(notes);
		expect(lines.indexOf(notes.system!)).toBe(lines.indexOf(notes.frame!) + 1);
		expect(lines.indexOf(notes.systemDuty[0]!)).toBe(lines.indexOf(notes.duty.at(-1)!) + 1);
	});

	it('in series, the ports are the pumps’ own, and the tolerance in display units', () => {
		const c = named('series');
		const { notes } = card(c);
		expect(notes.system).toBe(
			"The group's system curve is the rise the rest of the network needs between Pump PA (suction) and Pump PB (discharge) at each total flow; it does not depend on how the pumps share the flow."
		);
		expect(notes.systemDuty).toEqual([
			`At the duty's flow the group system curve gives the solve's rise (within 0.5 % or ${f4(fromSI(0.01, 'ft'))} ft): it passes through the Group point, where it crosses the group curve.`
		]);
	});

	it("a system duty check that disagrees: its rise against the solve's, and several steady states (D13)", () => {
		const c = named('parallel-ideal');
		const system = structuredClone(systemOf(c));
		// Made-up: the curve at the duty's flow needs 1 m more than the solve's rise.
		Object.assign(system.systemDutyCheck!, {
			agrees: false,
			head: system.duty!.head + 1,
			message: 'made-up server words'
		});
		const { notes } = card(c, groupState(c), { status: 'ready', response: system });
		expect(notes.systemDuty).toEqual([
			`The group system curve does not pass through the Group point: at the duty's flow it needs a rise of ${m(system.duty!.head + 1)} (the solve: ${m(system.duty!.head)}), more than 0.5 % or 0.01 m apart.`,
			'Several steady states can exist (D13); the point is the one the solve found.'
		]);
		expect(systemDutyCheckState(system)).toBe('the group system curve does not pass through it');
	});

	it('a system duty check without a rise: whether it passes is not known, and why', () => {
		const c = named('parallel-ideal');
		const system = structuredClone(systemOf(c));
		const duty = system.systemPoints.find((p) => p.isDuty)!;
		Object.assign(duty, {
			head: null,
			converged: false,
			reason: 'not_computed',
			message: 'not computed: the time budget ran out'
		});
		Object.assign(system.systemDutyCheck!, { agrees: false, head: null });
		const { notes } = card(c, groupState(c), { status: 'ready', response: system });
		expect(notes.systemDuty).toEqual([
			"The group system curve has no rise at the duty's flow, so whether it passes through the Group point is not known: not computed: the time allowed for the calculation ran out before this point was solved."
		]);
		expect(systemDutyCheckState(system)).toBe(
			'not known, the group system curve has no rise at the duty’s flow'
		);
	});

	it("tells the group system curve's state: progress, failure, cancellation, gaps", () => {
		const c = named('parallel-ideal');
		const text = (system: GroupSystemCurveState) =>
			card(c, groupState(c), system).notes.systemCurve;
		expect(text({ status: 'loading' })).toEqual({
			kind: 'loading',
			text: 'Computing the group system curve for this solve…'
		});
		expect(text({ status: 'error', message: 'The server is busy.' })).toEqual({
			kind: 'error',
			text: 'The group system curve could not be computed: The server is busy.'
		});
		expect(text({ status: 'cancelled', by: 'user' })!.text).toBe(
			'The group system curve was not computed: you cancelled it.'
		);
		expect(text({ status: 'cancelled', by: 'solve' })!.text).toBe(
			'The group system curve was not computed: a new solve was started.'
		);
		expect(text({ status: 'cancelled', by: 'goalSeek' })!.text).toBe(
			'The group system curve was not computed: a goal seek was started.'
		);
		// The group curve's notes are unchanged, its frame and duty check kept (slice 4a).
		const plain = card(c, groupState(c), null).notes;
		expect(plain.systemCurve).toBeNull();
		expect(plain.system).toBeNull();
		expect(plain.systemDuty).toEqual([]);
		expect(plain.axes).toBe(
			"Each pump's curve and point are drawn against the flow through that pump; the group curve and the Group point against the station's flow, the net flow into the station at its inlet."
		);
		const fcv = named('fcv-outside');
		const missing = systemOf(fcv).systemPoints.filter((p) => p.head === null).length;
		expect(card(fcv).notes.systemCurve).toEqual({
			kind: 'missing',
			text: `${missing} of ${systemOf(fcv).systemPoints.length} group-system-curve points have no rise: the line has gaps there, and the data table says why for each.`
		});
	});

	it('a PRV inside: the group curve is not defined there, its group system curve is', () => {
		const c = named('prv-inside');
		const { notes } = card(c);
		expect(notes.curve).toEqual({
			kind: 'refused',
			text: "These pumps form a station, but its group curve is not defined there; its group system curve is, and the pumps' own curves and points are drawn."
		});
		expect(notes.frame).toBeNull();
		expect(notes.system).toBe(
			"The group's system curve is the rise the rest of the network needs between Tee T1 (run inlet) and Tee T2 (run outlet) at each total flow; it does not depend on how the pumps share the flow."
		);
		expect(notes.systemDuty).toEqual([
			"At the duty's flow the group system curve gives the solve's rise (within 0.5 % or 0.01 m): it passes through the Group point."
		]);
		expect(notes.axes).toBe(
			"Each pump's curve and point are drawn against the flow through that pump; the group system curve and the Group point against the station's flow, the net flow into the station at its inlet."
		);
		// A refusal for anything else keeps slice 4a's words.
		const refused = named('refused');
		const body = refused.groupCurve.body as { message: string; issues: TopologyIssue[] };
		expect(
			card(refused, { status: 'refused', message: body.message, issues: body.issues }, null).notes
				.curve!.text
		).toBe(
			'These pumps do not form a station, so they have no group curve; their own curves and points are drawn.'
		);
	});
});

describe("the data table's group system curve", () => {
	it('lists every point in flow order with its rise, or why it has none in names and display units', () => {
		const c = named('fcv-outside');
		const system = systemOf(c);
		const rows = groupSystemRows(system, prefsOf(c), { project: c.project });
		const sorted = [...system.systemPoints].sort((a, b) => a.flow - b.flow);
		expect(rows.map((r) => [r.flow, r.rise, r.duty])).toEqual(
			sorted.map((p) => [f4(fromSI(p.flow, 'L/s')), p.head === null ? '—' : f4(p.head), p.isDuty])
		);
		const gap = rows.find((r) => r.rise === '—')!;
		const point = sorted.find((p) => p.head === null)!;
		expect(gap.note).toBe(
			"No steady state carries this flow: every way from the station's outlet back to its inlet, through the network or a reservoir or reference node, passes Control valve FC, which passes at most 60 L/s that way (an FCV passes neither reverse flow nor more than its flow setpoint)."
		);
		expect(gap.detail).toBe(point.message);
		// The pump chart's words, in the station's: one telling for both (system-curve-text.ts).
		expect(gap.note).toBe(
			systemPointNote(point, { project: c.project, units: prefsOf(c), subject: 'station' }).text
		);
		// Without names: the API's sentence.
		expect(groupSystemRows(system, prefsOf(c)).find((r) => r.rise === '—')!.note).toBe(
			point.message
		);
		expect(rows.filter((r) => r.duty)).toHaveLength(1);
		expect(rows.find((r) => r.duty)!.note).toBe('');
		expect(systemDutyCheckState(system)).toBe('the group system curve passes through it');
	});
});

describe("a system-curve point's reason, in a station's words", () => {
	const c = named('fcv-outside');
	const base = systemOf(c).systemPoints.find((p) => p.head === null)!;
	const told = (point: Partial<typeof base>) =>
		systemPointNote(
			{ ...base, ...point },
			{ project: c.project, units: prefsOf(c), subject: 'station' }
		).text;

	it('says the station, its inlet and outlet, and its rise, where a pump has its own', () => {
		expect(told({ reason: 'no_way_through', componentIds: [], flow: 0 })).toBe(
			"At zero flow the rise across the station is undetermined: a side of the station reaches no reservoir or reference node, nor the station's other side, through elements that can open (every element but those closed by a status you set)."
		);
		expect(told({ reason: 'closed_off', componentIds: ['FC'] })).toBe(
			'The rise across the station is undetermined: Control valve FC closes off a side of the station, and no reservoir or reference node fixes the pressure in the part closed off.'
		);
		expect(
			told({
				reason: 'valve_at_switch',
				componentIds: ['FC'],
				openHead: 30,
				openHeadBound: 'lower'
			})
		).toBe(
			'The rise across the station is undetermined: at this flow Control valve FC passes exactly its flow setpoint, so it could also hold the flow throttled, with any rise across the station at or above 30 m (its rise with the valve fully open), and no reservoir or reference node fixes the pressure between the valve and the station.'
		);
		// A pump's own system curve keeps the pump's words.
		expect(
			systemPointNote(
				{ ...base, reason: 'closed_off', componentIds: ['FC'] },
				{ project: c.project, units: prefsOf(c) }
			).text
		).toBe(
			'The head across the pump is undetermined: Control valve FC closes off a side of the pump, and no reservoir or reference node fixes the pressure in the part closed off.'
		);
	});
});
