/**
 * The Pumps together card's data (CLAUDE.md D20, proposal pump-groups.md §6.3–6.5): the members'
 * curves and points, the group curve and the station's duty, in display units; the notes under
 * the chart (one function for the screen and the image's footer); the group table and the data
 * table. Everything comes from the API: each member's curve and point from its PumpResult
 * (pumpChartData, unchanged), the group curve and the duty from POST /api/v1/pump-group-curve for
 * the same solve. The plain combined curve (flows added at equal head, or heads at equal flow) is
 * not drawn (owner, Q2): it misses the duty (§2.1).
 *
 * Two flows share the x-axis, and the notes and legend say which: a member's curve and point are
 * against the flow through that pump; the group curve and the Group point against the station's
 * flow, the net flow from S into the station.
 *
 * Identity never rests on colour alone: each member has a colour (the dataviz palette's blue and,
 * a step darker than its slot 3 to clear 3:1 on white, aqua; orange stays the system's), a dash
 * pattern from its third slot on, a marker with a text stand-in, a direct label, a legend entry
 * and a table row. A member keeps its slot (its colour) while it stays ticked.
 */
import type {
	Flag,
	MethodsSection,
	NodeResult,
	Project,
	PumpGroupCurvePoint,
	PumpGroupCurveResponse,
	PumpResult,
	StationPort,
	UnitPreferences
} from '../api/types';
import type { GroupCurveState } from '../state/project.svelte';
import { componentById } from './graph';
import { portLabel } from './labels';
import { pumpChartData, type ChartPoint } from './pump-chart';
import { Formatter, pumpStatusLabel, type Column } from './results';
import { displayUnit, formatNumber, fromSI, unitLabel } from './units';

/** Chart.js point styles of the members' points (a held pump: 'rectRot', the pump chart's diamond). */
export type GroupMarker = 'triangle' | 'rect' | 'star' | 'crossRot' | 'cross' | 'rectRounded';

/** A member's look: colour, dash patterns (inside its data and beyond it) and marker. */
export interface GroupSlot {
	color: string;
	/** Inside the curve's data: [] is solid. */
	dash: number[];
	/** Beyond it (extrapolated). */
	beyondDash: number[];
	marker: GroupMarker;
	/** The marker as text (the checkboxes, the tables, the image's notes). */
	symbol: string;
}

/** Blue, the dataviz palette's slot 1 (4.4:1 on white). */
export const GROUP_BLUE = '#2a78d6';
/**
 * Aqua: the palette's aqua stepped down to `#199e70` (3.4:1 on white; slot 3's `#1baf7a` is
 * 2.8:1). With blue and the system's orange it passes the palette validator all-pairs on white
 * (CVD ΔE 8.4, normal vision 21.6, contrast ≥ 3:1).
 */
export const GROUP_AQUA = '#199e70';
/** The group curve and the station's point: the primary ink (the pump chart's operating point). */
export const GROUP_INK = '#0f172a';

/** The six slots: blue and aqua in turn, each pair with its own dashes, every one its marker. */
export const GROUP_SLOTS: readonly GroupSlot[] = [
	{ color: GROUP_BLUE, dash: [], beyondDash: [6, 4], marker: 'triangle', symbol: '▲' },
	{ color: GROUP_AQUA, dash: [], beyondDash: [6, 4], marker: 'rect', symbol: '■' },
	{ color: GROUP_BLUE, dash: [12, 3, 3, 3], beyondDash: [2, 3], marker: 'star', symbol: '★' },
	{ color: GROUP_AQUA, dash: [12, 3, 3, 3], beyondDash: [2, 3], marker: 'crossRot', symbol: '×' },
	{ color: GROUP_BLUE, dash: [4, 2], beyondDash: [1, 5], marker: 'cross', symbol: '+' },
	{ color: GROUP_AQUA, dash: [4, 2], beyondDash: [1, 5], marker: 'rectRounded', symbol: '▢' }
];

/** The station's point as text, and a held pump's (the pump chart's diamond). */
export const STATION_SYMBOL = '●';
export const HELD_SYMBOL = '◇';

/** A member of the group, as the card gets it. */
export interface GroupMemberInput {
	id: string;
	name: string;
	result: PumpResult;
	/** The curve's flow range at rated speed (m³/s), from the project as solved. */
	ratedRange: [number, number] | null;
	/** The pump's curve id as solved: members with one curve at one speed share a line. */
	curveId: string | null;
	/** Its slot (its place among the boxes ticked): colour, dash and marker. */
	slot: number;
	flags: readonly Flag[];
}

/** A member's line: one curve at one speed, naming every member it is. */
export interface GroupLine {
	ids: string[];
	/** "PA, 100 % speed (own flow)", or for members sharing it "PA and PB, … (each one's flow)". */
	label: string;
	style: GroupSlot;
	/** Inside the curve's data. */
	curve: ChartPoint[];
	/** Beyond it: the start tangent to the shutoff head, the end slope out to its point. */
	extrapolated: ChartPoint[][];
}

/** A member's solved point (a running pump), or its zero-flow point (held). */
export interface GroupPoint {
	id: string;
	name: string;
	style: GroupSlot;
	point: ChartPoint;
	/** Held at zero flow ('no_flow'): drawn as the pump chart's diamond. */
	held: boolean;
}

export interface GroupChartData {
	flowUnit: string;
	headUnit: string;
	lines: GroupLine[];
	points: GroupPoint[];
	/** The group curve (station flow, rise): solid runs, and runs where a member is beyond its data. */
	curve: { solid: ChartPoint[][]; beyond: ChartPoint[][] } | null;
	/** Points of the group curve without a flow (gaps), of `total`. */
	missing: number;
	total: number;
	/** The station's duty (Q_st, ΔH_st); `onCurve` when the duty check agrees. */
	station: { point: ChartPoint; onCurve: boolean } | null;
}

const same = (a: number, b: number) => Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(b));

/** "87.32 %" of a speed (a fraction). */
export const speedPercent = (speed: number) => `${formatNumber(speed * 100, 4)} %`;

/**
 * The chart's data: each member's curve at its speed (members with one curve at one speed on one
 * line), each member's point, and from `response` the group curve and the station's duty.
 */
export function groupChartData(
	members: readonly GroupMemberInput[],
	prefs: UnitPreferences,
	response: PumpGroupCurveResponse | null
): GroupChartData {
	const flowUnit = displayUnit('flow', prefs);
	const headUnit = displayUnit('head', prefs);
	const at = (flow: number, head: number): ChartPoint => ({
		x: fromSI(flow, flowUnit),
		y: fromSI(head, headUnit)
	});
	const lines: GroupLine[] = [];
	const points: GroupPoint[] = [];
	for (const member of [...members].sort((a, b) => a.slot - b.slot)) {
		const style = slotStyle(member.slot);
		const data = pumpChartData(member.result, prefs, member.ratedRange);
		const sharing = members.filter(
			(m) =>
				m.curveId !== null &&
				m.curveId === member.curveId &&
				same(m.result.speed, member.result.speed)
		);
		const first = [...sharing].sort((a, b) => a.slot - b.slot)[0];
		if (!first || first === member) {
			const named = sharing.length ? [...sharing].sort((a, b) => a.slot - b.slot) : [member];
			const pumps = named.map((m) => (m.result.status === 'off' ? `${m.name} (off)` : m.name));
			lines.push({
				ids: named.map((m) => m.id),
				label: `${andList(pumps)}, ${speedPercent(member.result.speed)} speed (${named.length > 1 ? "each one's" : 'own'} flow)`,
				style,
				curve: data.curve,
				extrapolated: data.extrapolated
			});
		} else {
			// Its curve is drawn once; its own point beyond the shared data still gets its segment.
			const line = lines.find((l) => l.ids.includes(first.id));
			if (line && data.operating && !member.result.inCurveRange) {
				line.extrapolated.push(
					...data.extrapolated.filter((s) => s.some((p) => same(p.x, data.operating!.x)))
				);
			}
		}
		if (data.operating) {
			points.push({ id: member.id, name: member.name, style, point: data.operating, held: false });
		} else if (data.held) {
			points.push({ id: member.id, name: member.name, style, point: data.held, held: true });
		}
	}
	const duty = response?.duty ?? null;
	return {
		flowUnit: unitLabel('flow', flowUnit),
		headUnit: unitLabel('head', headUnit),
		lines,
		points,
		curve: response && response.points.length ? groupCurveRuns(response.points, at) : null,
		missing: response ? response.points.filter((p) => p.flow === null).length : 0,
		total: response?.points.length ?? 0,
		station: duty
			? { point: at(duty.flow, duty.head), onCurve: !!response?.dutyCheck?.agrees }
			: null
	};
}

/** A slot's style (slots past the sixth reuse the palette: never reached, at most six members). */
export function slotStyle(slot: number): GroupSlot {
	return GROUP_SLOTS[((slot % GROUP_SLOTS.length) + GROUP_SLOTS.length) % GROUP_SLOTS.length]!;
}

/**
 * The group curve in rise order as runs of points: a segment is in a `beyond` run where a member
 * runs beyond its curve data at either end, else in a `solid` run; a point without a flow breaks
 * both (a gap).
 */
function groupCurveRuns(
	points: readonly PumpGroupCurvePoint[],
	at: (flow: number, head: number) => ChartPoint
): { solid: ChartPoint[][]; beyond: ChartPoint[][] } {
	const solid: ChartPoint[][] = [];
	const beyond: ChartPoint[][] = [];
	const sorted = [...points].sort((a, b) => a.head - b.head);
	const isBeyond = (p: PumpGroupCurvePoint) => p.members.some((m) => m.beyondData);
	let run: { kind: 'solid' | 'beyond'; points: ChartPoint[] } | null = null;
	const close = () => {
		if (run && run.points.length > 1) (run.kind === 'solid' ? solid : beyond).push(run.points);
		run = null;
	};
	for (let i = 0; i + 1 < sorted.length; i++) {
		const a = sorted[i]!;
		const b = sorted[i + 1]!;
		if (a.flow === null || b.flow === null) {
			close();
			continue;
		}
		const kind = isBeyond(a) || isBeyond(b) ? 'beyond' : 'solid';
		const pa = at(a.flow, a.head);
		const pb = at(b.flow, b.head);
		const current = run as { kind: 'solid' | 'beyond'; points: ChartPoint[] } | null;
		if (current && current.kind === kind) current.points.push(pb);
		else {
			close();
			run = { kind, points: [pa, pb] };
		}
	}
	close();
	return { solid, beyond };
}

/** An entry of the legend the page draws under the chart (the image draws Chart.js's own). */
export interface GroupLegendItem {
	key: string;
	label: string;
	/** A line (its colour and dash), or a marker (its text stand-in in its colour). */
	kind: 'line' | 'marker';
	color: string;
	dash?: number[];
	symbol?: string;
}

/** The legend, in the chart's dataset order: one entry per line and per point. */
export function groupLegend(data: GroupChartData): GroupLegendItem[] {
	return [
		...data.lines.map((line): GroupLegendItem => ({
			key: `line-${line.ids.join()}`,
			label: line.label,
			kind: 'line',
			color: line.style.color,
			dash: line.style.dash
		})),
		...(data.curve?.solid.length
			? [
					{
						key: 'group',
						label: "Group curve (station's flow)",
						kind: 'line' as const,
						color: GROUP_INK,
						dash: []
					}
				]
			: []),
		...(data.curve?.beyond.length
			? [
					{
						key: 'group-beyond',
						label: 'Group curve, a pump beyond its data (dashed)',
						kind: 'line' as const,
						color: GROUP_INK,
						dash: [6, 4]
					}
				]
			: []),
		...data.points.map((p): GroupLegendItem => ({
			key: `point-${p.id}`,
			label: p.held ? `${p.name}, held at zero flow` : p.name,
			kind: 'marker',
			color: p.style.color,
			symbol: p.held ? HELD_SYMBOL : p.style.symbol
		})),
		...(data.station
			? [
					{
						key: 'station',
						label: data.station.onCurve ? 'Group duty, on the curve' : "Group duty (the solve's)",
						kind: 'marker' as const,
						color: GROUP_INK,
						symbol: STATION_SYMBOL
					}
				]
			: [])
	];
}

// ---------------------------------------------------------------------------------------------
// Words
// ---------------------------------------------------------------------------------------------

/** "Tee T1 (run inlet)", or "Reservoir R1" for a boundary taken whole. */
export function stationPortWords(port: StationPort, project: Project): string {
	const name = componentById(project, port.componentId)?.name ?? port.componentId;
	return port.portId ? `${name} (${portLabel(port.portId).toLowerCase()})` : name;
}

/** "A", "A and B", "A, B and C". */
export function andList(items: readonly string[]): string {
	if (items.length <= 1) return items.join('');
	return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

/** The arrangement in words, as the caption and the image's title give it. */
export const ARRANGEMENT_WORDS: Readonly<Record<string, string>> = {
	parallel: 'parallel',
	series: 'series',
	mixed: 'mixed: neither all in parallel nor all in series'
};

/** "PA and PB in parallel" (the figure's caption, by the pumps' names), "PA and PB" before the answer. */
export function groupCaption(names: readonly string[], arrangement: string | null): string {
	const pumps = andList(names);
	return arrangement === 'parallel' || arrangement === 'series'
		? `${pumps} in ${arrangement}`
		: arrangement === 'mixed'
			? `${pumps} (mixed: neither all in parallel nor all in series)`
			: pumps;
}

/** "Pumps together: PA, PB (parallel)" (the image's title, before its case). */
export function groupImageTitle(names: readonly string[], arrangement: string | null): string {
	return `Pumps together: ${names.join(', ')}${arrangement ? ` (${arrangement})` : ''}`;
}

/** The state of the group curve the card tells, with the control the screen offers beside it. */
export type GroupCurveNoteKind =
	'loading' | 'error' | 'cancelled' | 'refused' | 'missing' | 'few' | 'not_converged';

/** The sentences under the chart, which the image's footer repeats (proposal §6.4). */
export interface GroupNotes {
	/** The group curve's state (null: drawn whole). */
	curve: { kind: GroupCurveNoteKind; text: string } | null;
	/** Which flow each line is drawn against. */
	axes: string;
	/** The frame: the rise between S and D, and each member's loss on its way (or between them). */
	frame: string | null;
	/** The duty check: the curve passes through the Group point, or another steady state. */
	duty: string[];
	/** Members that deliver nothing above a rise, are off, or are speed-controlled. */
	members: string[];
	/** Each pump's own system curve stays on its pump chart. */
	systemCurves: string;
	/** Dashed lines, when any is drawn. */
	dashed: string | null;
}

export interface GroupNotesInput {
	data: GroupChartData;
	members: readonly GroupMemberInput[];
	state: GroupCurveState | undefined;
	/** The labels project: names of the station's ports. */
	project: Project;
	prefs: UnitPreferences;
}

/** The figure's notes, from one function the screen and the image both use. */
export function groupNotes({ data, members, state, project, prefs }: GroupNotesInput): GroupNotes {
	const headUnit = displayUnit('head', prefs);
	const head = (m: number) => `${formatNumber(fromSI(m, headUnit), 4)} ${data.headUnit}`;
	const response = state?.status === 'ready' ? state.response : null;
	const name = (id: string) => members.find((m) => m.id === id)?.name ?? id;
	const ordered = response
		? response.station.memberIds.map((id) => members.find((m) => m.id === id)).filter((m) => !!m)
		: [...members];

	const curve: GroupNotes['curve'] =
		members.length < 2
			? { kind: 'few', text: 'Tick two pumps or more to compute their group curve.' }
			: state === undefined
				? { kind: 'cancelled', text: 'The group curve has not been computed for this solve.' }
				: state.status === 'loading'
					? { kind: 'loading', text: 'Computing the group curve for this solve…' }
					: state.status === 'error'
						? { kind: 'error', text: `The group curve could not be computed: ${state.message}` }
						: state.status === 'cancelled'
							? {
									kind: 'cancelled',
									text:
										state.by === 'user'
											? 'The group curve was not computed: you cancelled it.'
											: state.by === 'goalSeek'
												? 'The group curve was not computed: a goal seek was started.'
												: 'The group curve was not computed: a new solve was started.'
								}
							: state.status === 'refused'
								? {
										kind: 'refused',
										text: 'These pumps do not form a station, so they have no group curve; their own curves and points are drawn.'
									}
								: !state.response.converged
									? {
											kind: 'not_converged',
											text: `The case's solve did not converge, so no group curve is computed${state.response.message ? `: ${state.response.message}` : '.'}`
										}
									: data.total && data.missing === data.total
										? {
												kind: 'missing',
												text: 'No point of the group curve has a flow, so it is not drawn; the data table says why for each.'
											}
										: data.missing
											? {
													kind: 'missing',
													text: `${data.missing} of ${data.total} group-curve points have no flow: the line has gaps there, and the data table says why for each.`
												}
											: null;

	const axes = response?.duty
		? "Each pump's curve and point are drawn against the flow through that pump; the group curve and the Group point against the station's flow, the net flow into the station at its inlet."
		: "Each pump's curve and point are drawn against the flow through that pump.";

	let frame: string | null = null;
	const duty: string[] = [];
	const memberNotes: string[] = [];
	if (response?.duty) {
		const s = stationPortWords(response.station.inlet, project);
		const d = stationPortWords(response.station.outlet, project);
		const opening = `Pump curves and points are at each pump's flanges. The group curve is the rise from ${s} to ${d}, solved with every pump on its own law`;
		const arrangement = response.station.arrangement;
		if (arrangement === 'parallel') {
			const losses = response.duty.members
				.filter((m) => m.routeHeadLoss !== null)
				.map((m, i) => `${name(m.pumpId)}${i === 0 ? ' loses ' : ' '}${head(m.routeHeadLoss!)}`);
			frame =
				`${opening}: it lies below the pumps' curves added together by each pump's own losses on its way.` +
				(losses.length ? ` At the duty ${andList(losses)}.` : '');
		} else if (arrangement === 'series') {
			const loss = response.duty.interstageHeadLoss;
			frame =
				`${opening}: it lies below the pumps' curves added together by the losses of the piping between them` +
				(loss === null ? '.' : `; the piping between the pumps loses ${head(loss)} at the duty.`);
		} else {
			frame = `${opening}; the pumps are neither all in parallel nor all in series between them (mixed), so no share and no loss on the way is given.`;
		}
		const check = response.dutyCheck;
		if (check?.agrees) {
			duty.push(
				"At the duty's rise the group curve gives the solve's flows, the station's and every pump's (within 0.5 %): it passes through the Group point."
			);
		} else if (check) {
			duty.push(
				`The group curve does not pass through the Group point: ${dutyCheckWords(response, name, prefs)}.`,
				'Several steady states can exist (D13); the point is the one the solve found.'
			);
		}
	}

	for (const member of ordered) {
		const result = member.result;
		if (result.status === 'off') {
			memberNotes.push(
				`${member.name} is off and adds nothing. A stopped pump is closed both ways in this app; in series it blocks the line (a stopped pump passing flow is not modelled).`
			);
			continue;
		}
		if (result.control) {
			memberNotes.push(
				`${member.name} is speed-controlled: its curve is drawn at its solved speed, ${speedPercent(result.speed)}; the group curve follows its control.`
			);
		}
		const stop = response ? stopRise(response.points, member.id) : null;
		if (stop === 'never') {
			memberNotes.push(`${member.name} delivers nothing at any rise the group curve samples.`);
		} else if (stop !== null) {
			const shutoff = result.control
				? 'its shutoff head at its maximum speed'
				: `its shutoff head, ${head(result.shutoffHead.head)}`;
			memberNotes.push(
				`${member.name} delivers nothing from a rise of ${head(stop)}: above ${shutoff}, the solver closes it.`
			);
		}
	}

	const dashed =
		data.lines.some((l) => l.extrapolated.length) || (data.curve?.beyond.length ?? 0) > 0
			? `Dashed: ${[
					...(data.lines.some((l) => l.extrapolated.length)
						? ["a pump's curve beyond its data, along its end slope, as the solver extrapolates"]
						: []),
					...((data.curve?.beyond.length ?? 0) > 0
						? ['the group curve where a pump runs beyond its curve data']
						: [])
				].join('; ')}.`
			: null;

	return {
		curve,
		axes,
		frame,
		duty,
		members: memberNotes,
		systemCurves:
			"Each pump's own system curve is on its pump chart above; it crosses that pump's curve, not the group curve.",
		dashed
	};
}

/**
 * The duty check in display units, from the response's values: the station's flow on the group
 * curve at the duty's rise against the solve's, and each pump whose flow there differs from its
 * solved flow by more than the check's tolerance (0.5 % or 10⁻⁶ m³/s, whichever is looser: the
 * API's PumpGroupDutyCheck.agrees). The server's sentence (`dutyCheck.message`, in SI) is kept
 * under Details.
 */
export function dutyCheckWords(
	response: PumpGroupCurveResponse,
	name: (id: string) => string,
	prefs: UnitPreferences
): string {
	const check = response.dutyCheck;
	const duty = response.duty;
	if (!check || !duty) return '';
	const flowUnit = displayUnit('flow', prefs);
	const flow = (q: number | null) =>
		q === null
			? 'no flow'
			: `${formatNumber(fromSI(q, flowUnit), 4)} ${unitLabel('flow', flowUnit)}`;
	const differs = (a: number | null, b: number) =>
		a === null || Math.abs(a - b) > Math.max(0.005 * Math.abs(b), 1e-6);
	const pumps = check.members.flatMap((m) => {
		const solved = duty.members.find((d) => d.pumpId === m.pumpId);
		return solved && differs(m.flow, solved.flow)
			? [`${name(m.pumpId)} ${flow(m.flow)} (the solve: ${flow(solved.flow)})`]
			: [];
	});
	return (
		`at the duty's rise it gives ${flow(check.flow)} (the solve: ${flow(duty.flow)})` +
		(pumps.length ? `, and ${andList(pumps)}` : '')
	);
}

/**
 * The lowest rise of the group curve from which `pumpId` carries no flow at every converged
 * point (null: it runs at the highest rise sampled, or no point has it; 'never': it runs at no
 * converged point).
 */
export function stopRise(
	points: readonly PumpGroupCurvePoint[],
	pumpId: string
): number | 'never' | null {
	const solved = points
		.filter((p) => p.converged && p.members.some((m) => m.pumpId === pumpId))
		.sort((a, b) => a.head - b.head);
	if (!solved.length) return null;
	const running = (p: PumpGroupCurvePoint) =>
		p.members.find((m) => m.pumpId === pumpId)?.status === 'running';
	if (!solved.some(running)) return 'never';
	let from: number | null = null;
	for (let i = solved.length - 1; i >= 0; i--) {
		if (running(solved[i]!)) break;
		from = solved[i]!.head;
	}
	return from;
}

/** The notes in the order the figure shows them: the image's footer lines. */
export function groupNoteLines(notes: GroupNotes, refusals: readonly string[] = []): string[] {
	return [
		notes.curve?.text,
		...refusals,
		notes.frame,
		notes.axes,
		...notes.duty,
		...notes.members,
		notes.dashed,
		notes.systemCurves
	].filter((line): line is string => !!line);
}

/**
 * The chart's accessible name: every member's point and share, the station's duty and whether
 * the group curve is shown.
 */
export function groupSummary(
	data: GroupChartData,
	members: readonly GroupMemberInput[],
	response: PumpGroupCurveResponse | null,
	project: Project
): string {
	const fmt = (v: number) => formatNumber(v, 4);
	const share = (id: string) => response?.duty?.members.find((m) => m.pumpId === id)?.share ?? null;
	const parts = members.map((m) => {
		const p = data.points.find((pt) => pt.id === m.id);
		const s = share(m.id);
		const shareText = s === null ? '' : `, share ${formatNumber(s * 100, 4)} %`;
		if (m.result.status === 'off') return `${m.name} off`;
		if (!p) return `${m.name} without a point`;
		return p.held
			? `${m.name} held at zero flow, ${fmt(p.point.y)} ${data.headUnit} across it${shareText}`
			: `${m.name} at ${fmt(p.point.x)} ${data.flowUnit} and ${fmt(p.point.y)} ${data.headUnit}${shareText}`;
	});
	const station =
		response?.duty && data.station
			? `; station duty ${fmt(data.station.point.x)} ${data.flowUnit} at a rise of ${fmt(data.station.point.y)} ${data.headUnit} from ${stationPortWords(response.station.inlet, project)} to ${stationPortWords(response.station.outlet, project)}${data.station.onCurve ? ', on the group curve' : ''}`
			: '';
	const curve =
		data.curve && data.missing < data.total ? '; group curve shown' : '; no group curve shown';
	return `Pump curves and points of ${parts.join('; ')}${station}${curve}.`;
}

// ---------------------------------------------------------------------------------------------
// The group table (§6.5)
// ---------------------------------------------------------------------------------------------

export interface GroupRow {
	id: string;
	name: string;
	style: GroupSlot;
	cells: Record<string, string>;
	flags: readonly Flag[];
}

export interface GroupTable {
	columns: Column[];
	rows: GroupRow[];
	/** The station's flow and rise (both ports named), and in series the interstage loss. */
	footer: { label: string; value: string }[];
}

/**
 * The group table: per member, from the solve (shown before the group curve arrives), then its
 * share and loss on its way from the response's duty. Columns by arrangement: parallel adds
 * "Lost on its way", series the inlet and discharge static pressures (gauge, from `nodes`).
 */
export function groupTable(
	members: readonly GroupMemberInput[],
	nodes: Readonly<Record<string, NodeResult>>,
	response: PumpGroupCurveResponse | null,
	prefs: UnitPreferences,
	project: Project
): GroupTable {
	const f = new Formatter(prefs);
	const arrangement = response?.station.arrangement ?? null;
	const duty = response?.duty ?? null;
	const columns: Column[] = [
		{ key: 'state', label: 'State' },
		f.column('speed', 'Speed', 'fraction'),
		f.column('flow', 'Flow', 'flow'),
		f.column('share', 'Share', 'fraction'),
		f.column('head', 'Head', 'head'),
		...(arrangement === 'parallel' ? [f.column('routeLoss', 'Lost on its way', 'head')] : []),
		...(arrangement === 'series'
			? [
					f.column('inlet', 'Inlet pressure', 'pressure', { gauge: true }),
					f.column('discharge', 'Discharge pressure', 'pressure', { gauge: true })
				]
			: []),
		f.column('efficiency', 'η', 'fraction'),
		f.column('shaftPower', 'Shaft power', 'power'),
		f.column('npshMargin', 'NPSH margin', 'head'),
		f.column('shutoff', 'Shutoff head', 'head'),
		{ key: 'inCurve', label: 'Inside curve data' }
	];
	const order = new Map(project.components.map((c, i) => [c.id, i]));
	const rows = [...members]
		.sort((a, b) => (order.get(a.id) ?? Infinity) - (order.get(b.id) ?? Infinity))
		.map((m): GroupRow => {
			const r = m.result;
			const d = duty?.members.find((x) => x.pumpId === m.id);
			const running = r.status === 'running';
			const maxSpeed = r.speedCurves.find((c) => c.limit === 'max')?.speed ?? null;
			const shutoff = f.num(r.shutoffHead.head, 'head');
			const atMax =
				r.control && maxSpeed !== null && r.speed > 0
					? f.num(r.shutoffHead.head * (maxSpeed / r.speed) ** 2, 'head')
					: null;
			return {
				id: m.id,
				name: m.name,
				style: slotStyle(m.slot),
				flags: m.flags,
				cells: {
					state: pumpStatusLabel(r, m.flags),
					speed: r.status === 'off' ? '—' : f.num(r.speed, 'fraction'),
					flow: f.num(r.operatingFlow, 'flow'),
					share: d ? f.num(d.share, 'fraction') : '—',
					head: f.num(r.operatingHead, 'head'),
					routeLoss: d ? f.num(d.routeHeadLoss, 'head') : '—',
					inlet: f.num(nodes[`${m.id}:suction`]?.pressure, 'pressure'),
					discharge: f.num(nodes[`${m.id}:discharge`]?.pressure, 'pressure'),
					efficiency: f.num(r.efficiency, 'fraction'),
					shaftPower: f.num(r.shaftPower, 'power'),
					npshMargin: f.num(r.npshMargin, 'head'),
					shutoff: atMax ? `${shutoff} (${atMax} at maximum speed)` : shutoff,
					inCurve: running ? (r.inCurveRange ? 'Yes' : 'No: beyond its data') : '—'
				}
			};
		});
	const footer: GroupTable['footer'] = [];
	if (response?.duty) {
		const s = stationPortWords(response.station.inlet, project);
		const d = stationPortWords(response.station.outlet, project);
		footer.push(
			{
				label: `Station flow, into the station at ${s}`,
				value: f.value(response.duty.flow, 'flow')
			},
			{ label: `Rise from ${s} to ${d}`, value: f.value(response.duty.head, 'head') }
		);
		if (arrangement === 'series' && response.duty.interstageHeadLoss !== null) {
			footer.push({
				label: 'Lost in the piping between the pumps',
				value: f.value(response.duty.interstageHeadLoss, 'head')
			});
		}
	}
	return { columns, rows, footer };
}

// ---------------------------------------------------------------------------------------------
// The data table (the chart's long description)
// ---------------------------------------------------------------------------------------------

const STATUS_WORDS: Readonly<Record<string, string>> = {
	running: 'Running',
	off: 'Off',
	no_flow: 'No flow'
};
const CONTROL_WORDS: Readonly<Record<string, string>> = {
	active: 'holding its setpoint',
	max_speed: 'at maximum speed',
	min_speed: 'at minimum speed',
	no_flow: 'no flow',
	off: 'off'
};

/** A group-curve sample as the data table lists it (formatted, display units). */
export interface GroupSampleRow {
	rise: string;
	flow: string;
	/** Duty: the sample at the duty's rise (the duty check). */
	duty: boolean;
	members: { flow: string; head: string; state: string }[];
	/** Why the point has no flow ('' when it has one). */
	note: string;
}

/** Every sample of the group curve, in rise order, with each member's flow, head and state. */
export function groupSampleRows(
	response: PumpGroupCurveResponse,
	memberIds: readonly string[],
	prefs: UnitPreferences
): GroupSampleRow[] {
	const flowUnit = displayUnit('flow', prefs);
	const headUnit = displayUnit('head', prefs);
	const fmt = (v: number) => formatNumber(v, 4);
	return [...response.points]
		.sort((a, b) => a.head - b.head)
		.map((p) => ({
			rise: fmt(fromSI(p.head, headUnit)),
			flow: p.flow === null ? '—' : fmt(fromSI(p.flow, flowUnit)),
			duty: p.isDuty,
			members: memberIds.map((id) => {
				const m = p.members.find((x) => x.pumpId === id);
				if (!m) return { flow: '—', head: '—', state: '—' };
				const control = m.controlState ? CONTROL_WORDS[m.controlState] : null;
				const state = `${STATUS_WORDS[m.status] ?? m.status}${control && m.status === 'running' ? `, ${control}` : ''}${m.beyondData ? ', beyond its data' : ''}`;
				return {
					flow: fmt(fromSI(m.flow, flowUnit)),
					head: m.head === null ? '—' : fmt(fromSI(m.head, headUnit)),
					state
				};
			}),
			note:
				p.flow !== null
					? ''
					: p.reason === 'not_computed'
						? 'Not computed: the time budget ran out before this point.'
						: p.reason === 'not_converged'
							? `Its solve did not converge.${p.message ? ` ${p.message}` : ''}`
							: p.message
		}));
}

/** The methods section of the response: "How this curve is computed". */
export function groupMethods(state: GroupCurveState | undefined): MethodsSection | null {
	return state?.status === 'ready' ? state.response.methods : null;
}
