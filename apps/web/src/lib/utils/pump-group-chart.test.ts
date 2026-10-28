/**
 * The Pumps together card's data, chart configuration, notes and tables (proposal pump-groups.md
 * §6.3–6.5), on real API responses: the shared fixture __fixtures__/pump-groups-input.json
 * (apps/api/tests/fixtures/pump_groups_input.py). Numbers in the expected words are the
 * fixture's, formatted as the card formats them.
 */
import { describe, expect, it } from 'vitest';
import type {
	Flag,
	Project,
	PumpGroupCurveResponse,
	PumpResult,
	SolvedState,
	UnitPreferences
} from '$lib/api/types';
import type { GroupCurveState } from '$lib/state/project.svelte';
import fixture from './__fixtures__/pump-groups-input.json';
import { ratedCurveRange } from './pump-chart';
import {
	GROUP_BEYOND_LABEL,
	GROUP_CURVE_LABEL,
	pumpGroupConfig,
	type PumpChartConfig
} from './pump-chart-config';
import {
	GROUP_AQUA,
	GROUP_BLUE,
	GROUP_INK,
	GROUP_SLOTS,
	groupCaption,
	groupChartData,
	groupImageTitle,
	groupLegend,
	groupNoteLines,
	groupNotes,
	groupSampleRows,
	groupSummary,
	groupTable,
	stopRise,
	type GroupMemberInput
} from './pump-group-chart';
import { formatNumber, fromSI, SI_UNITS } from './units';

interface FixtureCase {
	name: string;
	project: Project;
	memberIds: string[];
	solve: { solvedState: SolvedState };
	groupCurve: { status: number; body: unknown };
}
const cases = fixture.cases as unknown as FixtureCase[];
const named = (name: string) => cases.find((c) => c.name === name)!;

/** The members of a fixture case, in slots 0, 1, … (or the slots given). */
function membersOf(c: FixtureCase, slots: (string | null)[] = c.memberIds): GroupMemberInput[] {
	const s = c.solve.solvedState;
	return slots.flatMap((id, slot) => {
		if (id === null) return [];
		const pump = c.project.components.find((x) => x.id === id)!;
		return [
			{
				id,
				name: pump.name,
				result: s.pumpResults[id] as PumpResult,
				ratedRange: ratedCurveRange(c.project, id),
				curveId: pump.type === 'pump' ? pump.curveId : null,
				slot,
				flags: (s.flags as Flag[]).filter((f) => f.componentId === id)
			}
		];
	});
}
const responseOf = (c: FixtureCase) => c.groupCurve.body as PumpGroupCurveResponse;
const ready = (c: FixtureCase): GroupCurveState => ({ status: 'ready', response: responseOf(c) });
const prefsOf = (c: FixtureCase): UnitPreferences => c.project.settings.units;
const f4 = (v: number) => formatNumber(v, 4);
const m = (v: number) => `${f4(v)} m`;
const ft = (v: number) => `${f4(fromSI(v, 'ft'))} ft`;

function notesOf(c: FixtureCase, state: GroupCurveState | undefined = ready(c)) {
	const members = membersOf(c);
	const response = state?.status === 'ready' ? state.response : null;
	const data = groupChartData(members, prefsOf(c), response);
	return groupNotes({ data, members, state, project: c.project, prefs: prefsOf(c) });
}

const config = (data: ReturnType<typeof groupChartData>): PumpChartConfig =>
	pumpGroupConfig(data, { legendLabels: () => [], format: f4 });
type Dataset = PumpChartConfig['data']['datasets'][number] & {
	caseLabel?: string;
	legend?: boolean;
	memberIds?: string[];
};
const datasets = (cfg: PumpChartConfig) => cfg.data.datasets as Dataset[];

describe('the chart data', () => {
	it("draws each member's curve and point in its slot's colour, marker and dashes", () => {
		const c = named('parallel-ideal');
		const data = groupChartData(membersOf(c), prefsOf(c), responseOf(c));
		expect(data.flowUnit).toBe('L/s');
		expect(data.lines.map((l) => [l.label, l.style.color, l.style.dash])).toEqual([
			['Pump PA, 100 % speed (own flow)', GROUP_BLUE, []],
			['Pump PB, 85 % speed (own flow)', GROUP_AQUA, []]
		]);
		const pa = c.solve.solvedState.pumpResults.PA!;
		expect(data.points[0]).toMatchObject({
			id: 'PA',
			held: false,
			point: { x: expect.closeTo(pa.operatingFlow * 1000, 12), y: pa.operatingHead }
		});
		expect(data.points.map((p) => p.style.marker)).toEqual(['triangle', 'rect']);
		// The pump curve as the pump chart draws it: the API's samples, unchanged.
		expect(data.lines[0]!.curve).toEqual(
			pa.curve.map((p) => ({ x: expect.closeTo(p.flow * 1000, 12), y: p.head }))
		);
	});

	it('keeps a colour with its pump while it stays ticked; later members reuse hues with dashes', () => {
		const c = named('ladder');
		// P1 unticked (slot 0 free): P2 keeps aqua, P3 keeps the third slot's blue dash-dot.
		const data = groupChartData(membersOf(c, [null, 'P2', 'P3']), prefsOf(c), null);
		expect(data.lines.map((l) => [l.ids, l.style.color, l.style.dash, l.style.beyondDash])).toEqual(
			[
				[['P2'], GROUP_AQUA, [], [6, 4]],
				[['P3'], GROUP_BLUE, [12, 3, 3, 3], [2, 3]]
			]
		);
		expect(data.points.map((p) => [p.id, p.style.marker])).toEqual([
			['P2', 'rect'],
			['P3', 'star']
		]);
		// Six distinct looks: colour, dash and marker together never repeat.
		const looks = GROUP_SLOTS.map((s) => `${s.color}${s.dash.join()}${s.marker}`);
		expect(new Set(looks).size).toBe(6);
		expect(new Set(GROUP_SLOTS.map((s) => s.marker)).size).toBe(6);
	});

	it('draws one line for members with one curve at one speed, naming them all', () => {
		const c = named('parallel-ideal');
		const [pa] = membersOf(c);
		const twin = { ...pa!, id: 'PX', name: 'Pump PX', slot: 1 };
		const data = groupChartData([pa!, twin], prefsOf(c), null);
		expect(data.lines.map((l) => [l.ids, l.label])).toEqual([
			[['PA', 'PX'], "Pump PA and Pump PX, 100 % speed (each one's flow)"]
		]);
		expect(data.points).toHaveLength(2);
	});

	it("marks a pump held at zero flow, draws an off pump's curve for reference and no point", () => {
		const held = named('dead-headed');
		const data = groupChartData(membersOf(held), prefsOf(held), responseOf(held));
		expect(data.points.find((p) => p.id === 'PB')).toMatchObject({
			held: true,
			point: { x: 0, y: held.solve.solvedState.pumpResults.PB!.operatingHead }
		});
		const off = named('off');
		const offData = groupChartData(membersOf(off), prefsOf(off), responseOf(off));
		expect(offData.points.map((p) => p.id)).toEqual(['PA']);
		expect(offData.lines[1]!.label).toBe('Pump PB (off), 85 % speed (own flow)');
	});

	it("draws the group curve against the station's flow: dashed where a member is beyond its data, gaps where a point has no flow", () => {
		const c = named('parallel-ideal');
		const response = responseOf(c);
		const data = groupChartData(membersOf(c), prefsOf(c), response);
		const points = [...response.points].sort((a, b) => a.head - b.head);
		const all = [...data.curve!.solid, ...data.curve!.beyond].flat();
		for (const p of points) {
			expect(all).toContainEqual({ x: expect.closeTo(p.flow! * 1000, 9), y: p.head });
		}
		// The lowest rises have members beyond their data: dashed.
		expect(points[0]!.members.some((x) => x.beyondData)).toBe(true);
		expect(data.curve!.beyond[0]![0]).toEqual({
			x: expect.closeTo(points[0]!.flow! * 1000, 9),
			y: points[0]!.head
		});
		expect(data.missing).toBe(0);
		expect(data.total).toBe(points.length);
		// A point without a flow: a gap in every run.
		const gap = structuredClone(response);
		const at = gap.points.findIndex((p) => p.isDuty);
		Object.assign(gap.points[at]!, { flow: null, converged: false, reason: 'not_converged' });
		const gapped = groupChartData(membersOf(c), prefsOf(c), gap);
		expect(gapped.missing).toBe(1);
		const drawn = [...gapped.curve!.solid, ...gapped.curve!.beyond].flat();
		expect(drawn.some((p) => p.y === gap.points[at]!.head)).toBe(false);
	});

	it("puts the station's duty at (Q_st, ΔH_st) in display units, on the curve when the check agrees", () => {
		const c = named('series');
		const response = responseOf(c);
		const data = groupChartData(membersOf(c), prefsOf(c), response);
		expect(data.station).toEqual({
			point: {
				x: expect.closeTo(fromSI(response.duty!.flow, 'gpm'), 9),
				y: expect.closeTo(fromSI(response.duty!.head, 'ft'), 9)
			},
			onCurve: true
		});
		const disagree = structuredClone(response);
		disagree.dutyCheck!.agrees = false;
		expect(groupChartData(membersOf(c), prefsOf(c), disagree).station!.onCurve).toBe(false);
	});
});

describe('the chart configuration', () => {
	it('draws the members, the group curve in ink and the Group point, and nothing else', () => {
		const c = named('dead-headed');
		const cfg = config(groupChartData(membersOf(c), prefsOf(c), responseOf(c)));
		const sets = datasets(cfg);
		expect(sets.map((d) => d.label)).toEqual([
			'Pump PA, 100 % speed (own flow)',
			'Pump PA, 100 % speed (own flow), beyond its data',
			'Pump PB, 70 % speed (own flow)',
			GROUP_CURVE_LABEL,
			GROUP_BEYOND_LABEL,
			'Pump PA',
			'Pump PB, held at zero flow',
			'Group duty, on the curve'
		]);
		const byLabel = (label: string) => sets.find((d) => d.label === label)!;
		expect(byLabel(GROUP_CURVE_LABEL)).toMatchObject({
			borderColor: GROUP_INK,
			borderWidth: 2,
			spanGaps: false
		});
		expect(byLabel(GROUP_CURVE_LABEL)).not.toHaveProperty('borderDash');
		expect(byLabel(GROUP_BEYOND_LABEL)).toMatchObject({
			borderColor: GROUP_INK,
			borderDash: [6, 4]
		});
		// The markers: each member's (its slot's shape, a held pump the diamond) and the station's.
		const markers = sets.filter((d) => (d as { showLine?: boolean }).showLine === false);
		expect(
			markers.map((d) => [d.label, (d as { pointStyle?: string }).pointStyle, d.caseLabel])
		).toEqual([
			['Pump PA', 'triangle', 'Pump PA'],
			['Pump PB, held at zero flow', 'rectRot', 'Pump PB'],
			['Group duty, on the curve', 'circle', 'Group']
		]);
		expect(byLabel('Group duty, on the curve')).toMatchObject({ backgroundColor: GROUP_INK });
		// One legend entry per line: a member's dashed part is told by the notes.
		const filter = cfg.options!.plugins!.legend!.labels!.filter!;
		const shown = sets.filter((_, i) => filter({ datasetIndex: i } as never, cfg.data as never));
		expect(shown.map((d) => d.label)).not.toContain(
			'Pump PA, 100 % speed (own flow), beyond its data'
		);
		expect(shown.map((d) => d.label)).toContain(GROUP_BEYOND_LABEL);
		expect(cfg.options!.scales!.x!.title).toMatchObject({ text: 'Flow (L/s)' });
		expect(cfg.options!.scales!.y!.title).toMatchObject({ text: 'Head or rise (m)' });
		expect(Object.keys(cfg.options!.scales!)).toEqual(['x', 'y']);
	});

	it('labels the Group point as on the curve only when the duty check agrees', () => {
		const c = named('parallel-crane');
		const disagree = structuredClone(responseOf(c));
		disagree.dutyCheck!.agrees = false;
		const sets = datasets(config(groupChartData(membersOf(c), prefsOf(c), disagree)));
		expect(sets.at(-1)).toMatchObject({ label: "Group duty (the solve's)", caseLabel: 'Group' });
	});

	it('draws the members alone, without a station point, when the pumps are not a station', () => {
		const c = named('refused');
		const sets = datasets(config(groupChartData(membersOf(c), prefsOf(c), null)));
		expect(sets.map((d) => d.label)).toEqual([
			'Pump PA, 100 % speed (own flow)',
			'Pump PB, 85 % speed (own flow)',
			'Pump PA',
			'Pump PB'
		]);
	});

	it('leaves the legend to the page on screen, and draws its own in the image', () => {
		const c = named('dead-headed');
		const data = groupChartData(membersOf(c), prefsOf(c), responseOf(c));
		const screenConfig = pumpGroupConfig(data, {
			legendLabels: () => [],
			format: f4,
			htmlLegend: true
		});
		expect(screenConfig.options!.plugins!.legend!.display).toBe(false);
		expect(config(data).options!.plugins!.legend!.display).toBe(true);
		// The page's legend names what the chart's would, its markers as text.
		expect(groupLegend(data).map((i) => [i.label, i.kind, i.symbol ?? i.dash])).toEqual([
			['Pump PA, 100 % speed (own flow)', 'line', []],
			['Pump PB, 70 % speed (own flow)', 'line', []],
			["Group curve (station's flow)", 'line', []],
			['Group curve, a pump beyond its data (dashed)', 'line', [6, 4]],
			['Pump PA', 'marker', '▲'],
			['Pump PB, held at zero flow', 'marker', '◇'],
			['Group duty, on the curve', 'marker', '●']
		]);
	});

	it('draws the image at a fixed size, without events or tooltips', () => {
		const c = named('series');
		const cfg = pumpGroupConfig(groupChartData(membersOf(c), prefsOf(c), responseOf(c)), {
			legendLabels: () => [],
			format: f4,
			forImage: true
		});
		expect(cfg.options).toMatchObject({ responsive: false, devicePixelRatio: 2, events: [] });
		expect(cfg.options!.plugins!.tooltip).toEqual({ enabled: false });
	});
});

describe('the notes (screen and image)', () => {
	it('parallel: the rise between the outer ports and each pump’s loss on its way', () => {
		const c = named('parallel-crane');
		const duty = responseOf(c).duty!;
		const [pa, pb] = duty.members;
		const notes = notesOf(c);
		expect(notes.frame).toBe(
			`Pump curves and points are at each pump's flanges. The group curve is the rise from Tee T1 (run inlet) to Tee T2 (run outlet), solved with every pump on its own law: it lies below the pumps' curves added together by each pump's own losses on its way. At the duty Pump PA loses ${m(pa!.routeHeadLoss!)} and Pump PB ${m(pb!.routeHeadLoss!)}.`
		);
		expect(notes.duty).toEqual([
			"At the duty's rise the group curve gives the solve's flows, the station's and every pump's (within 0.5 %): it passes through the Group point."
		]);
		expect(notes.axes).toBe(
			"Each pump's curve and point are drawn against the flow through that pump; the group curve and the Group point against the station's flow, the net flow into the station at its inlet."
		);
		expect(notes.systemCurves).toBe(
			"Each pump's own system curve is on its pump chart above; it crosses that pump's curve, not the group curve."
		);
	});

	it('series: the loss of the piping between the pumps, in display units', () => {
		const c = named('series');
		expect(notesOf(c).frame).toBe(
			`Pump curves and points are at each pump's flanges. The group curve is the rise from Pump PA (suction) to Pump PB (discharge), solved with every pump on its own law: it lies below the pumps' curves added together by the losses of the piping between them; the piping between the pumps loses ${ft(responseOf(c).duty!.interstageHeadLoss!)} at the duty.`
		);
	});

	it('a member that stops: from the first rise sampled where it has no flow, with its shutoff head', () => {
		const c = named('dead-headed');
		const response = responseOf(c);
		const rise = stopRise(response.points, 'PB');
		expect(typeof rise).toBe('number');
		expect(notesOf(c).members).toEqual([
			`Pump PB delivers nothing from a rise of ${m(rise as number)}: above its shutoff head, ${m(c.solve.solvedState.pumpResults.PB!.shutoffHead.head)}, the solver closes it.`
		]);
		// The rise is a sample's: running below it, at no flow from it up.
		const below = [...response.points]
			.filter((p) => p.head < (rise as number))
			.sort((a, b) => b.head - a.head)[0]!;
		expect(below.members.find((x) => x.pumpId === 'PB')!.status).toBe('running');
		expect(stopRise(response.points, 'PA')).toBe(null);
	});

	it('an off member, and a speed-controlled one', () => {
		expect(notesOf(named('off')).members).toEqual([
			'Pump PB is off and adds nothing. A stopped pump is closed both ways in this app; in series it blocks the line (a stopped pump passing flow is not modelled).'
		]);
		const c = named('controlled');
		const speed = c.solve.solvedState.pumpResults.PB!.speed;
		expect(notesOf(c).members).toEqual([
			`Pump PB is speed-controlled: its curve is drawn at its solved speed, ${f4(speed * 100)} %; the group curve follows its control.`
		]);
	});

	it('a duty check that disagrees: its values in display units, and that several steady states can exist', () => {
		const c = named('parallel-ideal');
		const response = structuredClone(responseOf(c));
		const duty = response.duty!;
		// Made-up values: the curve at the duty's rise with PB stopped (another steady state).
		response.dutyCheck = {
			agrees: false,
			flow: duty.members[0]!.flow,
			members: [
				{ pumpId: 'PA', flow: duty.members[0]!.flow * (1 + 1e-4) },
				{ pumpId: 'PB', flow: 0 }
			],
			message: 'made-up server words'
		};
		const l = (q: number) => `${f4(q * 1000)} L/s`;
		expect(notesOf(c, { status: 'ready', response }).duty).toEqual([
			`The group curve does not pass through the Group point: at the duty's rise it gives ${l(duty.members[0]!.flow)} (the solve: ${l(duty.flow)}), and Pump PB 0 L/s (the solve: ${l(duty.members[1]!.flow)}).`,
			'Several steady states can exist (D13); the point is the one the solve found.'
		]);
	});

	it("says the group curve's state: computing, failed, cancelled, refused, too few pumps", () => {
		const c = named('parallel-ideal');
		const curve = (state: GroupCurveState | undefined) => notesOf(c, state).curve;
		expect(curve({ status: 'loading' })).toEqual({
			kind: 'loading',
			text: 'Computing the group curve for this solve…'
		});
		expect(curve({ status: 'error', message: 'The server is busy.' })).toEqual({
			kind: 'error',
			text: 'The group curve could not be computed: The server is busy.'
		});
		expect(curve({ status: 'cancelled', by: 'user' })!.text).toBe(
			'The group curve was not computed: you cancelled it.'
		);
		expect(curve({ status: 'cancelled', by: 'solve' })!.text).toBe(
			'The group curve was not computed: a new solve was started.'
		);
		expect(curve({ status: 'cancelled', by: 'goalSeek' })!.text).toBe(
			'The group curve was not computed: a goal seek was started.'
		);
		const members = membersOf(c);
		const none = groupChartData(members, prefsOf(c), null);
		expect(
			groupNotes({ data: none, members, state: undefined, project: c.project, prefs: SI_UNITS })
				.curve
		).toEqual({
			kind: 'cancelled',
			text: 'The group curve has not been computed for this solve.'
		});
		expect(curve({ status: 'refused', message: 'x', issues: [] })).toEqual({
			kind: 'refused',
			text: 'These pumps do not form a station, so they have no group curve; their own curves and points are drawn.'
		});
		expect(curve(ready(c))).toBe(null);
		const one = membersOf(c).slice(0, 1);
		const data = groupChartData(one, prefsOf(c), null);
		expect(
			groupNotes({ data, members: one, state: undefined, project: c.project, prefs: SI_UNITS })
				.curve
		).toEqual({ kind: 'few', text: 'Tick two pumps or more to compute their group curve.' });
	});

	it('gives the image the notes in the screen’s order, the refusal reasons after the state', () => {
		const c = named('refused');
		const notes = notesOf(c, { status: 'refused', message: 'x', issues: [] });
		expect(groupNoteLines(notes, ['Tank R4 is why.'])).toEqual([
			'These pumps do not form a station, so they have no group curve; their own curves and points are drawn.',
			'Tank R4 is why.',
			"Each pump's curve and point are drawn against the flow through that pump.",
			notes.systemCurves
		]);
	});
});

describe('the caption, title and accessible name', () => {
	it('names the pumps and the arrangement the API found', () => {
		expect(groupCaption(['PA', 'PB'], 'parallel')).toBe('PA and PB in parallel');
		expect(groupCaption(['P1', 'P2', 'P3'], null)).toBe('P1, P2 and P3');
		expect(groupImageTitle(['PA', 'PB'], 'parallel')).toBe('Pumps together: PA, PB (parallel)');
		expect(groupImageTitle(['PA', 'PB'], null)).toBe('Pumps together: PA, PB');
	});

	it("gives every member's point and share, the station's duty, and the group curve shown", () => {
		const c = named('parallel-ideal');
		const response = responseOf(c);
		const members = membersOf(c);
		const data = groupChartData(members, prefsOf(c), response);
		const [pa, pb] = response.duty!.members;
		const r = c.solve.solvedState.pumpResults;
		expect(groupSummary(data, members, response, c.project)).toBe(
			`Pump curves and points of Pump PA at ${f4(r.PA!.operatingFlow * 1000)} L/s and ${f4(r.PA!.operatingHead)} m, share ${f4(pa!.share! * 100)} %; Pump PB at ${f4(r.PB!.operatingFlow * 1000)} L/s and ${f4(r.PB!.operatingHead)} m, share ${f4(pb!.share! * 100)} %; station duty ${f4(response.duty!.flow * 1000)} L/s at a rise of ${f4(response.duty!.head)} m from Tee T1 (run inlet) to Tee T2 (run outlet), on the group curve; group curve shown.`
		);
		expect(
			groupSummary(groupChartData(members, prefsOf(c), null), members, null, c.project)
		).toMatch(/; no group curve shown\.$/);
	});
});

describe('the group table', () => {
	it('parallel: per member from the solve, share and loss on its way from the duty, the footer', () => {
		const c = named('parallel-ideal');
		const response = responseOf(c);
		const table = groupTable(
			membersOf(c),
			c.solve.solvedState.nodeResults,
			response,
			prefsOf(c),
			c.project
		);
		expect(table.columns.map((col) => [col.label, col.unit ?? ''])).toEqual([
			['State', ''],
			['Speed', '%'],
			['Flow', 'L/s'],
			['Share', '%'],
			['Head', 'm'],
			['Lost on its way', 'm'],
			['η', '%'],
			['Shaft power', 'kW'],
			['NPSH margin', 'm'],
			['Shutoff head', 'm'],
			['Inside curve data', '']
		]);
		const [pa] = response.duty!.members;
		expect(table.rows[0]!.cells).toMatchObject({
			state: 'Running',
			speed: '100',
			flow: f4(c.solve.solvedState.pumpResults.PA!.operatingFlow * 1000),
			share: f4(pa!.share! * 100),
			routeLoss: f4(pa!.routeHeadLoss!),
			shutoff: '45',
			inCurve: 'Yes'
		});
		expect(table.footer).toEqual([
			{
				label: 'Station flow, into the station at Tee T1 (run inlet)',
				value: `${f4(response.duty!.flow * 1000)} L/s`
			},
			{
				label: 'Rise from Tee T1 (run inlet) to Tee T2 (run outlet)',
				value: `${f4(response.duty!.head)} m`
			}
		]);
	});

	it('series: inlet and discharge pressures (gauge) and the interstage loss; before the curve, no share', () => {
		const c = named('controlled');
		const nodes = c.solve.solvedState.nodeResults;
		const table = groupTable(membersOf(c), nodes, responseOf(c), prefsOf(c), c.project);
		expect(table.columns.map((col) => [col.key, col.unit ?? ''])).toContainEqual(['inlet', 'psig']);
		expect(table.columns.map((col) => col.key)).not.toContain('routeLoss');
		const pb = table.rows[1]!;
		expect(pb.cells.inlet).toBe(f4(fromSI(nodes['PB:suction']!.pressure, 'psi')));
		// A speed-controlled pump's shutoff head at its running and its maximum speed.
		expect(pb.cells.shutoff).toMatch(/^[\d.]+ \([\d.]+ at maximum speed\)$/);
		expect(pb.cells.state).toBe('Running (holding flow setpoint)');
		expect(table.footer.at(-1)).toEqual({
			label: 'Lost in the piping between the pumps',
			value: ft(responseOf(c).duty!.interstageHeadLoss!)
		});
		const before = groupTable(membersOf(c), nodes, null, prefsOf(c), c.project);
		expect(before.rows.map((r) => r.cells.share)).toEqual(['—', '—']);
		expect(before.footer).toEqual([]);
	});
});

describe('the data table', () => {
	it("lists every sample with each member's flow, head and state, the duty's marked", () => {
		const c = named('controlled');
		const response = responseOf(c);
		const rows = groupSampleRows(response, response.station.memberIds, prefsOf(c));
		expect(rows).toHaveLength(response.points.length);
		expect(rows.filter((r) => r.duty)).toHaveLength(1);
		const first = rows[0]!;
		expect(first.members[1]!.state).toBe('Running, at minimum speed, beyond its data');
		expect(rows.some((r) => r.members[1]!.state === 'Running, holding its setpoint')).toBe(true);
		const gap = structuredClone(response);
		Object.assign(gap.points[0]!, {
			flow: null,
			converged: false,
			reason: 'not_computed',
			members: []
		});
		expect(groupSampleRows(gap, gap.station.memberIds, prefsOf(c))[0]).toMatchObject({
			flow: '—',
			note: 'Not computed: the time budget ran out before this point.',
			members: [
				{ flow: '—', head: '—', state: '—' },
				{ flow: '—', head: '—', state: '—' }
			]
		});
	});
});
