/**
 * The Pumps together card's data (CLAUDE.md D21, proposal pump-groups.md §6.3–6.5): the members'
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
 * The group system curve (slice 4b, proposal §3.4 and §7) is the same request with curve 'system':
 * the rise EGL(D) − EGL(S) the rest of the network needs at each station's flow, every link inside
 * the station held closed. It is drawn in the pump chart's system orange (orange keeps one meaning
 * in the Pumps view: a system curve), with a gap at each point without a rise and the point's
 * reason in the data table (system-curve-text.ts, in the station's words). The Group point is
 * labelled as the two curves' crossing only when both duty checks agree. "Read along the curves"
 * steps over the group curve's samples, each member's flow and the station's read from the
 * response at that rise (no value between samples is made up here).
 *
 * Slice 4d (one pump off): other cases' station duties, each from that case's own group-curve
 * answer, are numbered slate rings (pump-group-one-off.ts says which cases, in which state, and
 * whether a ring is a point of the group system curve shown); duties within the duty checks'
 * tolerances share one ring.
 *
 * Slice L3 of pump lineups (CLAUDE.md D24, proposal pump-lineups.md §9): a ring's own group curve,
 * where pump-group-one-off.ts says it is drawn, is a slate line split as the group curve is, with
 * its labels (placeCurveLabels places them on the canvas, pure), one legend entry for the family,
 * the axes it needs (x cut where other curves pass everything else, y capped near the pumps with
 * the group system curve cut there), its words in the notes and the accessible name, and its
 * points in a table of their own. Without a curve drawn the chart is 4d's.
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
	PumpGroupSystemPoint,
	PumpResult,
	StationPort,
	UnitPreferences
} from '../api/types';
import type { GroupCurveState, GroupSystemCurveState } from '../state/project.svelte';
import type { OtherGroupCase } from './pump-group-one-off';
import { readableText } from './flag-text';
import { componentById } from './graph';
import { portLabel } from './labels';
import { pumpChartData, type ChartPoint } from './pump-chart';
import { pressureControlOnly } from './pump-groups';
import { Formatter, pumpStatusLabel, type Column } from './results';
import { systemPointNote, type SystemCurveTextContext } from './system-curve-text';
import { displayUnit, formatNumber, fromSI, unitLabel, type UnitId } from './units';

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
/**
 * The group system curve: the pump chart's system orange (pump-chart-config.ts
 * CHART_COLORS.system, which the chart chunk holds; equal by test), so orange means a system
 * curve wherever the Pumps view draws one.
 */
export const GROUP_SYSTEM = '#eb6834';
/** The group system curve's legend entry and dataset label. */
export const GROUP_SYSTEM_LABEL =
	"Group system curve (the rest of the network between the station's inlet and outlet, station's flow)";

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

/**
 * Other cases' station duties (slice 4d): slate rings, the pump chart's colour for other cases
 * (pump-chart-config.ts CHART_COLORS.slate, 7.6:1 on white; equal by test), numbered.
 */
export const GROUP_OTHER = '#475569';
/** An other case's ring as text (the legend, the tables). */
export const OTHER_SYMBOL = '○';

/**
 * Other cases' own group curves (D24 slice L3): their one legend entry, on screen and in the image
 * (a canvas legend item does not wrap: 62 characters).
 */
export const OTHER_CURVES_LABEL = "Other cases' group curves (slate; dashed beyond a pump's data)";

/**
 * When a ring is called a point of the group system curve shown (pump-group-one-off.ts
 * dutyClaim): the notes' sentence, while a ring and a group system curve are drawn.
 */
export const DUTY_CLAIM_RULE =
	"A ring is called a point of the group system curve shown only when its case, as solved, is the same as this one outside the station, its station flow is above zero, the curve has a rise at the computed flows on both sides of it, and this case's own duty is on the curve. Its duty is then a steady state of the same rest of the network, so it lies on the curve wherever the rest has one state at its flow; the curve is drawn through sampled points, each the state the system curve's starts find (D13).";

/**
 * The station and its duty the card shows: the group curve's ready response, else the group
 * system curve's when it has a duty (the same station and duty, from the case's own solve; the
 * group curve refused only for an active PRV or PSV inside).
 */
export function stationResponse(
	group: GroupCurveState | undefined,
	system: GroupSystemCurveState | undefined
): PumpGroupCurveResponse | null {
	if (group?.status === 'ready') return group.response;
	return system?.status === 'ready' && system.response.duty ? system.response : null;
}

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
	/**
	 * The station's duty (Q_st, ΔH_st), from the group curve's response, else the group system
	 * curve's (the same: the case's own solve); `onCurve` when the group curve's duty check agrees,
	 * `onSystem` when the group system curve's does, `crossing` when both do (the Group point is
	 * then where the two curves cross); `flow`, Q_st in display units as words give it (0 below the
	 * duty check's floor, dutyFlow); `label`, its legend entry; `tag`, its label on the chart.
	 */
	station: {
		point: ChartPoint;
		onCurve: boolean;
		onSystem: boolean;
		crossing: boolean;
		flow: number;
		label: string;
		tag: string;
	} | null;
	/**
	 * The group system curve in flow order (station's flow, rise): a null rise is a point without
	 * one (a gap); null without a group system curve response or points. While other cases' curves
	 * are drawn, the line as drawn under `yMax` (D24 §9.4: its points inside the plot and those
	 * next to one); `systemMissing` and `systemTotal` count the whole curve.
	 */
	system: { x: number; y: number | null }[] | null;
	/** Points of the group system curve without a rise (gaps), of `systemTotal`. */
	systemMissing: number;
	systemTotal: number;
	/** Other cases' station duties, as rings (slice 4d): in number order, empty without any. */
	others: OtherRing[];
	/**
	 * Other cases' own group curves (D24 slice L3, §9.1): one per case whose curve is drawn, in
	 * number order; empty without any (the chart is then 4d's).
	 */
	otherCurves: OtherCurve[];
	/**
	 * This case's members switched on, as solved (groupChartData's `on`): its ink curve's label
	 * while other cases' curves are drawn (§9.3); null when not given.
	 */
	on: number | null;
	/**
	 * The x-axis maximum (display units, §9.4): set only when other cases' curves pass the largest
	 * flow of everything else; they are cut at it. Null: Chart.js's own range.
	 */
	xMax: number | null;
	/**
	 * A point of another case's curve lies beyond `xMax`: the curves are cut at the plot's right
	 * edge (the clip note). x max rounded up can lie beyond every one of them: nothing is cut.
	 */
	curvesCut: boolean;
	/**
	 * The x-axis minimum (display units, §9.4: other cases' curves do not widen the x-axis): 0 when
	 * only they reach below zero flow (round-off at their shutoff rise, about −10⁻¹¹ L/s, would
	 * start the axis a tick below zero). Null: Chart.js's own range.
	 */
	xMin: number | null;
	/**
	 * The y-axis maximum (display units, §9.4, decision 25): while other cases' curves are drawn,
	 * from every drawn head but the group system curve's, whose points above it are cut from
	 * `system`. Null: Chart.js's own range (4b's and 4d's charts).
	 */
	yMax: number | null;
	/** The group system curve had a rise above `yMax`: it is cut at the plot's top (the clip note). */
	systemCut: boolean;
}

/**
 * An other case's own group curve on the chart (D24 slice L3, §9.1, §9.2): slate, solid where
 * every member is inside its data and dashed where one runs beyond it, as the group curve is.
 */
export interface OtherCurve {
	/** '' for the base, else the scenario id. */
	key: string;
	/** Its case's ring number. */
	number: number;
	/** The case's name, "(out of date)" after it when its results are. */
	name: string;
	/** Members switched on in that case as solved (k), of `of`. */
	k: number;
	of: number;
	stale: boolean;
	/** "3 running", or for a stale case "as last solved: 3 running" (runningWords). */
	running: string;
	/** The response's points in rise order (display units), as groupCurveRuns splits them. */
	solid: ChartPoint[][];
	beyond: ChartPoint[][];
	/** The dataset's label (tooltips) from 640 px and in the image: "1 · {name}: group curve, 3 running". */
	label: string;
	/** Below 640 px, where a tooltip does not wrap: "1 · 3 running: group curve". */
	shortLabel: string;
}

/** A case of a ring: its number, name and duty (display units, the flow as words give it). */
export interface OtherRingCase {
	number: number;
	/** The case's name, "(out of date)" after it when its results are. */
	name: string;
	/** Q_st in display units, 0 below the duty check's floor (dutyFlow). */
	flow: number;
	/** ΔH_st in display units. */
	rise: number;
	/** Whether it lies on the group system curve shown, in short words (DUTY_CLAIM_WORDS). */
	claim: string;
	/**
	 * Its own group curve's state in words (D24 §9.6, OTHER_CURVE_WORDS), for the notes and the
	 * accessible name; null without a curve state (4d's chart).
	 */
	curve: string | null;
	/** The same words starting with a capital: the "Its group curve" column. */
	curveCell: string | null;
	/** Its own group curve is drawn. */
	drawn: boolean;
}

/**
 * An other case's station duty on the chart (slice 4d): a slate ring at (Q_st, ΔH_st) of the
 * first of its cases; cases whose duties agree within the two duty checks' tolerances share one.
 */
export interface OtherRing {
	numbers: number[];
	names: string[];
	point: ChartPoint;
	/** The dataset's and the legend's label: "1 · Pump PA off (station duty)". */
	label: string;
	/**
	 * On the chart: "1 · Pump PA off", "1, 2 · A, B and 1 more" past two names; its numbers only
	 * when every case of the ring has its own curve drawn (D24 §9.3: the labels and the legend
	 * name them).
	 */
	tag: string;
	/** On a phone's screen: "1", "1, 2". */
	short: string;
	cases: OtherRingCase[];
}

const same = (a: number, b: number) => Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(b));

/** "87.32 %" of a speed (a fraction). */
export const speedPercent = (speed: number) => `${formatNumber(speed * 100, 4)} %`;

/**
 * The chart's data: each member's curve at its speed (members with one curve at one speed on one
 * line), each member's point, from `response` the group curve and the station's duty, and from
 * `system` (the same request with curve 'system') the group system curve. With `others` (slice
 * 4d) their rings, and their own group curves where drawn (D24 slice L3) with the axes those
 * need; `on` is this case's members switched on as solved, its curve's label (§9.3).
 */
export function groupChartData(
	members: readonly GroupMemberInput[],
	prefs: UnitPreferences,
	response: PumpGroupCurveResponse | null,
	system: PumpGroupCurveResponse | null = null,
	others: readonly OtherGroupCase[] = [],
	on: number | null = null
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
	const duty = response?.duty ?? system?.duty ?? null;
	const systemPoints = system?.systemPoints.length
		? [...system.systemPoints].sort((a, b) => a.flow - b.flow)
		: null;
	const systemLine =
		systemPoints?.map((p) => ({
			x: fromSI(p.flow, flowUnit),
			y: p.head === null ? null : fromSI(p.head, headUnit)
		})) ?? null;
	const systemDrawn = !!systemLine?.some((p) => p.y !== null);
	const onCurve = !!response?.dutyCheck?.agrees;
	const onSystem = !!system?.systemDutyCheck?.agrees;
	const crossing = onCurve && onSystem && !!response?.points.length && systemDrawn;
	const curve = response && response.points.length ? groupCurveRuns(response.points, at) : null;
	const rings = otherRings(others, at, flowUnit, headUnit);
	const otherCurves = familyCurves(others, at);
	const axes = familyAxes({
		lines,
		points,
		curve,
		system: systemLine,
		station: duty ? at(duty.flow, duty.head) : null,
		rings,
		otherCurves
	});
	return {
		flowUnit: unitLabel('flow', flowUnit),
		headUnit: unitLabel('head', headUnit),
		lines,
		points,
		curve,
		missing: response ? response.points.filter((p) => p.flow === null).length : 0,
		total: response?.points.length ?? 0,
		station: duty
			? {
					point: at(duty.flow, duty.head),
					onCurve,
					onSystem,
					crossing,
					flow: fromSI(dutyFlow(duty.flow), flowUnit),
					label: crossing
						? 'Group duty, where the group curve and the group system curve cross'
						: onCurve
							? systemDrawn
								? 'Group duty, on the group curve'
								: 'Group duty, on the curve'
							: onSystem && systemDrawn
								? 'Group duty, on the group system curve'
								: "Group duty (the solve's)",
					tag: crossing ? 'Group (crossing)' : 'Group'
				}
			: null,
		// The line as drawn (cut above y max while the family is drawn); its gaps counted whole.
		system: axes.system,
		systemMissing: (systemLine ?? []).filter((p) => p.y === null).length,
		systemTotal: systemLine?.length ?? 0,
		others: rings,
		otherCurves,
		on,
		xMin: axes.xMin,
		xMax: axes.xMax,
		curvesCut: axes.curvesCut,
		yMax: axes.yMax,
		systemCut: axes.systemCut
	};
}

/**
 * Each other case whose own group curve is drawn (otherGroupCases' `curve`: on the chart, ready,
 * the same station), in number order: its response's points in rise order as groupCurveRuns
 * splits them, and its labels (D24 §9.2, §9.6).
 */
function familyCurves(
	others: readonly OtherGroupCase[],
	at: (flow: number, head: number) => ChartPoint
): OtherCurve[] {
	return others
		.filter((o) => o.onChart && o.state === 'ready' && o.curve && o.number !== null)
		.sort((a, b) => a.number! - b.number!)
		.map((o) => {
			const { points, on: k, of } = o.curve!;
			const runs = groupCurveRuns(points, at);
			const name = `${o.name}${o.stale ? ' (out of date)' : ''}`;
			const running = runningWords(k, o.stale);
			return {
				key: o.key,
				number: o.number!,
				name,
				k,
				of,
				stale: o.stale,
				running,
				solid: runs.solid,
				beyond: runs.beyond,
				label: `${o.number} · ${name}: group curve, ${running}`,
				shortLabel: `${o.number} · ${running}: group curve`
			};
		});
}

/**
 * "3 running"; for a stale case "as last solved: 3 running" (D24 §9.1): its k is its last
 * solve's, while its name may already have followed a later toggle (§4.5).
 */
export function runningWords(on: number, stale: boolean): string {
	return stale ? `as last solved: ${on} running` : `${on} running`;
}

/** The steps of a rounded axis maximum (D24 §9.4): {1, 1.2, …, 8} × 10ⁿ. */
const NICE_STEPS = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8] as const;

/**
 * The least of {1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8} × 10ⁿ at or above `value` (D24 §9.4); null for
 * a value that is not positive and finite.
 */
export function roundUpNice(value: number): number | null {
	if (!Number.isFinite(value) || value <= 0) return null;
	// From a decade below: log10 can round up across a power of ten.
	const n = Math.floor(Math.log10(value)) - 1;
	for (let exponent = n; ; exponent++) {
		for (const step of NICE_STEPS) {
			// Rounded to 12 figures: 3 × 10⁻¹ is 0.3, not 0.30000000000000004.
			const candidate = Number((step * 10 ** exponent).toPrecision(12));
			if (candidate >= value) return candidate;
		}
	}
}

/**
 * The axes while other cases' curves are drawn (D24 §9.4; with none, Chart.js's own range and the
 * group system curve whole, as in 4b and 4d):
 * - y max: the largest head of everything drawn but the group system curve (the members' lines and
 *   points, this case's group curve and the others', the Group point, every ring) × 1.05, rounded
 *   up (roundUpNice). The group system curve keeps only its points drawn inside and those next
 *   to one, so its line runs to the plot's top edge, where the chart clips it, and its gaps there
 *   stay: nothing it shows above every pump's head can be a crossing, since no group curve
 *   reaches there.
 * - x max: only when the other cases' curves pass the largest flow of everything else (the
 *   members' lines and points, this case's group curve and its group system curve as drawn, the
 *   Group point, every ring), that flow × 1.05, rounded up; the other curves are cut at it, where
 *   a point of one lies beyond it (`curvesCut`, the clip note's clause).
 * - x min: 0 when only the other cases' curves reach below zero flow (nor do they widen it there).
 */
function familyAxes(input: {
	lines: readonly GroupLine[];
	points: readonly GroupPoint[];
	curve: { solid: ChartPoint[][]; beyond: ChartPoint[][] } | null;
	system: { x: number; y: number | null }[] | null;
	station: ChartPoint | null;
	rings: readonly OtherRing[];
	otherCurves: readonly OtherCurve[];
}): {
	xMin: number | null;
	xMax: number | null;
	curvesCut: boolean;
	yMax: number | null;
	system: { x: number; y: number | null }[] | null;
	systemCut: boolean;
} {
	const { lines, points, curve, station, rings, otherCurves } = input;
	if (!otherCurves.length) {
		const system = input.system;
		return { xMin: null, xMax: null, curvesCut: false, yMax: null, system, systemCut: false };
	}
	const runs = (c: { solid: ChartPoint[][]; beyond: ChartPoint[][] } | null) =>
		c ? [...c.solid, ...c.beyond].flat() : [];
	const own: ChartPoint[] = [
		...lines.flatMap((l) => [...l.curve, ...l.extrapolated.flat()]),
		...points.map((p) => p.point),
		...runs(curve),
		...(station ? [station] : []),
		...rings.map((r) => r.point)
	];
	const family = otherCurves.flatMap((c) => runs(c));
	const yMax = roundUpNice(Math.max(...[...own, ...family].map((p) => p.y)) * 1.05);
	let system = input.system;
	let systemCut = false;
	if (system && yMax !== null) {
		const line = system;
		const inside = (i: number) => {
			const y = line[i]?.y;
			return y !== null && y !== undefined && y <= yMax;
		};
		systemCut = line.some((p) => p.y !== null && p.y > yMax);
		// A point drawn inside, or next to one (a point above it, or a gap beside it): any other
		// lies wholly above the plot or beyond the line drawn there.
		system = line.filter((_, i) => inside(i) || inside(i - 1) || inside(i + 1));
	}
	const drawnSystem = (system ?? []).filter((p): p is ChartPoint => p.y !== null);
	const largest = Math.max(...[...own, ...drawnSystem].map((p) => p.x));
	const familyLargest = Math.max(...family.map((p) => p.x));
	const xMax = familyLargest > largest ? roundUpNice(largest * 1.05) : null;
	const curvesCut = xMax !== null && family.some((p) => p.x > xMax);
	const smallest = Math.min(...[...own, ...drawnSystem].map((p) => p.x));
	const xMin = Math.min(...family.map((p) => p.x)) < 0 && smallest >= 0 ? 0 : null;
	return { xMin, xMax, curvesCut, yMax, system, systemCut };
}

/** Two duties agree within the duty checks' tolerances (the flow's, and the rise's of 4b). */
function dutiesAgree(a: { flow: number; head: number }, b: { flow: number; head: number }) {
	return (
		Math.abs(b.flow - a.flow) <= Math.max(0.005 * Math.abs(a.flow), DUTY_CHECK_FLOOR) &&
		Math.abs(b.head - a.head) <= Math.max(0.005 * Math.abs(a.head), SYSTEM_DUTY_CHECK_FLOOR)
	);
}

/**
 * The rings of the other cases drawn (on the chart, ready, the same station, with a duty), in
 * number order: a case whose duty agrees with a ring's first case's within the duty checks'
 * tolerances joins that ring, which keeps its first case's point.
 */
function otherRings(
	others: readonly OtherGroupCase[],
	at: (flow: number, head: number) => ChartPoint,
	flowUnit: UnitId,
	headUnit: UnitId
): OtherRing[] {
	const drawn = others
		.filter((o) => o.onChart && o.state === 'ready' && o.duty && o.number !== null)
		.sort((a, b) => a.number! - b.number!);
	const rings: { first: { flow: number; head: number }; ring: OtherRing }[] = [];
	for (const o of drawn) {
		const duty = o.duty!;
		const name = `${o.name}${o.stale ? ' (out of date)' : ''}`;
		const entry: OtherRingCase = {
			number: o.number!,
			name,
			flow: fromSI(dutyFlow(duty.flow), flowUnit),
			rise: fromSI(duty.head, headUnit),
			claim: o.words,
			curve: o.curveWords,
			curveCell: o.curveWords === null ? null : upperFirst(o.curveWords),
			drawn: o.curve !== null
		};
		const joined = rings.find((r) => dutiesAgree(r.first, duty));
		if (joined) {
			joined.ring.numbers.push(o.number!);
			joined.ring.names.push(name);
			joined.ring.cases.push(entry);
		} else {
			rings.push({
				first: duty,
				ring: {
					numbers: [o.number!],
					names: [name],
					point: at(duty.flow, duty.head),
					label: '',
					tag: '',
					short: '',
					cases: [entry]
				}
			});
		}
	}
	return rings.map(({ ring }) => {
		const numbers = ring.numbers.join(', ');
		const merged = ring.names.length > 1;
		const shown =
			ring.names.length <= 2
				? ring.names.join(', ')
				: `${ring.names.slice(0, 2).join(', ')} and ${ring.names.length - 2} more`;
		return {
			...ring,
			label: merged
				? `${numbers} · ${andList(ring.names)} (station duties, equal within the duty checks' tolerances)`
				: `${numbers} · ${ring.names[0]} (station duty)`,
			// Its numbers only when every case of it has its curve drawn (D24 §9.3): the labels on
			// the curves, the legend, the notes and the tables name them, and lineup names are long.
			tag: ring.cases.every((c) => c.drawn) ? numbers : `${numbers} · ${shown}`,
			short: numbers
		};
	});
}

/** "drawn (…)" → "Drawn (…)" (a table cell). */
function upperFirst(text: string): string {
	return text.charAt(0).toUpperCase() + text.slice(1);
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
		// Other cases' own group curves (D24 §9.6): one entry for the family; its labels and the
		// notes say which curve is which.
		...(data.otherCurves.length
			? [
					{
						key: 'other-curves',
						label: OTHER_CURVES_LABEL,
						kind: 'line' as const,
						color: GROUP_OTHER,
						dash: []
					}
				]
			: []),
		...(data.system?.some((p) => p.y !== null)
			? [
					{
						key: 'group-system',
						label: GROUP_SYSTEM_LABEL,
						kind: 'line' as const,
						color: GROUP_SYSTEM,
						dash: []
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
						label: data.station.label,
						kind: 'marker' as const,
						color: GROUP_INK,
						symbol: STATION_SYMBOL
					}
				]
			: []),
		...data.others.map((ring): GroupLegendItem => ({
			key: `other-${ring.numbers.join('-')}`,
			label: ring.label,
			kind: 'marker',
			color: GROUP_OTHER,
			symbol: OTHER_SYMBOL
		}))
	];
}

// ---------------------------------------------------------------------------------------------
// Labels on the curves (D24 slice L3, §9.3)
// ---------------------------------------------------------------------------------------------

/** A box on the canvas (px; y grows downwards). */
export interface PxBox {
	left: number;
	right: number;
	top: number;
	bottom: number;
}

/** A curve to label, as the chart draws it. */
export interface CurveLabelInput {
	/** Its anchor: its drawn point of largest flow inside the plot (curveAnchor), px; null: none. */
	anchor: { x: number; y: number } | null;
	/** Members switched on in its case, as solved. */
	k: number;
	/** Its case's ring numbers; empty for this case's own (ink) curve. */
	numbers: readonly number[];
}

/** A label placed by placeCurveLabels. */
export interface PlacedCurveLabel {
	text: string;
	/** The curves it labels, by their index in the input: more than one when merged. */
	curves: number[];
	/** This case's own curve: drawn in ink, the others in slate. */
	shown: boolean;
	/** The text's left end and its baseline (px: textAlign 'left', textBaseline 'alphabetic'). */
	x: number;
	y: number;
	/** Its row: 0, or moved up one or two rows. */
	row: number;
	box: PxBox;
}

/** The labels drawn, and how many curves have their label left out for space. */
export interface CurveLabelPlacement {
	labels: PlacedCurveLabel[];
	leftOut: number;
}

/** A label's row (px): a label that would overlap moves up by one, at most twice (§9.3). */
export const CURVE_LABEL_ROW = 14;
/** Rows in all: the anchor's and two above it. */
const CURVE_LABEL_ROWS = 3;
/** How far a label sits left of and above its anchor (px). */
const CURVE_LABEL_OFFSET = 4;
/** How far inside the plot's left edge a label is clamped (px), as the system curve's tag is. */
const CURVE_LABEL_EDGE = 2;
/** Labels closer than this side by side read as one (px; m4's spacing): they overlap. */
const CURVE_LABEL_GAP = 3;

/**
 * A curve's label (§9.3): another case's "{numbers} · {k} running" (numbers ascending), "{k}
 * running" on a phone (`compact`); this case's own "{k} running (this case)", "{k} running" on a
 * phone. The image takes the desktop's.
 */
export function curveLabelText(numbers: readonly number[], k: number, compact = false): string {
	if (!numbers.length) return compact ? `${k} running` : `${k} running (this case)`;
	const sorted = [...numbers].sort((a, b) => a - b);
	return compact ? `${k} running` : `${sorted.join(', ')} · ${k} running`;
}

/**
 * A curve's anchor (§9.3): of its drawn points (px), the one of largest flow (rightmost) inside
 * the plot, edges included; null when none is inside (the curve is not seen, and not labelled).
 */
export function curveAnchor(
	points: readonly { x: number; y: number }[],
	plot: PxBox
): { x: number; y: number } | null {
	let best: { x: number; y: number } | null = null;
	for (const p of points) {
		const inside = p.x >= plot.left && p.x <= plot.right && p.y >= plot.top && p.y <= plot.bottom;
		if (inside && (!best || p.x > best.x)) best = { x: p.x, y: p.y };
	}
	return best;
}

function overlaps(a: PxBox, b: PxBox): boolean {
	return (
		a.left < b.right + CURVE_LABEL_GAP &&
		b.left < a.right + CURVE_LABEL_GAP &&
		a.top < b.bottom &&
		b.top < a.bottom
	);
}

/**
 * Where the curves' labels go (§9.3), pure: the chart's plugin calls it with Chart.js's pixels
 * and `ctx.measureText`, the tests with a fixed-width `measure`.
 * - Each label is right-aligned 4 px left of its anchor and 4 px above it, clamped inside the
 *   plot's left edge.
 * - Labels of other cases' curves with equal k whose anchors are less than one label width apart
 *   (the width of the later one's own label) merge into one at the rightmost anchor, their numbers
 *   ascending: "1, 4, 5, 6 · 3 running". This case's label never merges.
 * - From left to right, a label that would overlap one placed before or an obstacle (a ring's
 *   tag, a marker, a member's label) moves up one 14 px row, at most twice; a row that would leave
 *   the plot's top does not fit either. A label that still overlaps is left out, and `leftOut`
 *   counts the curves it labels (the notes say so; the data table lists every curve).
 */
export function placeCurveLabels(
	curves: readonly CurveLabelInput[],
	obstacles: readonly PxBox[],
	plot: PxBox,
	measure: (text: string) => number,
	compact = false
): CurveLabelPlacement {
	type Group = {
		curves: number[];
		numbers: number[];
		k: number;
		shown: boolean;
		anchor: { x: number; y: number };
	};
	const items = curves
		.flatMap((c, i) => (c.anchor ? [{ i, c, anchor: c.anchor }] : []))
		.sort((a, b) => a.anchor.x - b.anchor.x || a.i - b.i);
	const groups: Group[] = [];
	const lastOfK = new Map<number, Group>();
	for (const { i, c, anchor } of items) {
		const shown = c.numbers.length === 0;
		if (!shown) {
			const last = lastOfK.get(c.k);
			const width = measure(curveLabelText(c.numbers, c.k, compact));
			if (last && anchor.x - last.anchor.x < width) {
				last.curves.push(i);
				last.numbers.push(...c.numbers);
				last.anchor = anchor;
				continue;
			}
		}
		const group: Group = { curves: [i], numbers: [...c.numbers], k: c.k, shown, anchor };
		groups.push(group);
		if (!shown) lastOfK.set(c.k, group);
	}
	groups.sort((a, b) => a.anchor.x - b.anchor.x);
	const labels: PlacedCurveLabel[] = [];
	let leftOut = 0;
	for (const g of groups) {
		const text = curveLabelText(g.numbers, g.k, compact);
		const width = measure(text);
		const x = Math.max(plot.left + CURVE_LABEL_EDGE, g.anchor.x - CURVE_LABEL_OFFSET - width);
		let placed: PlacedCurveLabel | null = null;
		for (let row = 0; row < CURVE_LABEL_ROWS && !placed; row++) {
			const y = g.anchor.y - CURVE_LABEL_OFFSET - row * CURVE_LABEL_ROW;
			const box = { left: x, right: x + width, top: y - CURVE_LABEL_ROW, bottom: y };
			if (box.top < plot.top) break;
			const taken = [...labels.map((l) => l.box), ...obstacles].some((b) => overlaps(box, b));
			if (!taken) placed = { text, curves: g.curves, shown: g.shown, x, y, row, box };
		}
		if (placed) labels.push(placed);
		else leftOut += g.curves.length;
	}
	return { labels, leftOut };
}

// ---------------------------------------------------------------------------------------------
// Words
// ---------------------------------------------------------------------------------------------

/**
 * The project the card names elements from: the labels project (current names, as the rest of the
 * screen names them), with the components of `solved` (the project the results belong to) that it
 * no longer has, under their names as solved: an element deleted since the solve.
 */
export function namesProject(labels: Project, solved: Project | null | undefined): Project {
	if (!solved || solved === labels) return labels;
	const ids = new Set(labels.components.map((c) => c.id));
	const gone = solved.components.filter((c) => !ids.has(c.id));
	return gone.length ? { ...labels, components: [...labels.components, ...gone] } : labels;
}

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
	'loading' | 'error' | 'cancelled' | 'refused' | 'missing' | 'few' | 'not_converged' | 'no_duty';

/** The state of the group system curve the card tells, with the control beside it. */
export type GroupSystemNoteKind =
	'loading' | 'error' | 'cancelled' | 'refused' | 'missing' | 'not_converged' | 'no_duty';

/** The sentences under the chart, which the image's footer repeats (proposal §6.4). */
export interface GroupNotes {
	/** The group curve's state (null: drawn whole). */
	curve: { kind: GroupCurveNoteKind; text: string } | null;
	/**
	 * The group system curve's state (null: drawn whole, or not asked for: it is asked for after
	 * the group curve's answer, store.wantsGroupSystemCurve).
	 */
	systemCurve: { kind: GroupSystemNoteKind; text: string } | null;
	/**
	 * What the group system curve is (proposal §7's note, the station's ports named), when it has
	 * a response with a duty.
	 */
	system: string | null;
	/**
	 * The group system curve at the duty's flow: whether it passes through the Group point (and
	 * crosses the group curve there), or why that is not known.
	 */
	systemDuty: string[];
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
	/**
	 * Other cases' station duties (slice 4d): what a ring is, when one is called a point of the
	 * group system curve shown, the rings, and the cases without one and why; one line while
	 * they are not asked for (empty with no other case).
	 */
	others: string[];
}

export interface GroupNotesInput {
	data: GroupChartData;
	members: readonly GroupMemberInput[];
	state: GroupCurveState | undefined;
	/** The group system curve's state (undefined: not asked for, or unavailable). */
	system?: GroupSystemCurveState | undefined;
	/** The labels project: names of the station's ports. */
	project: Project;
	/** The project as solved: each element's kind, for the rule a reason names (default `project`). */
	solved?: Project | null;
	prefs: UnitPreferences;
	/** The other cases with values, each in its state (slice 4d; default none). */
	others?: readonly OtherGroupCase[];
	/**
	 * Curves whose labels placeCurveLabels left out for space where the chart was drawn (D24 §9.3;
	 * default 0): the notes count them.
	 */
	labelsLeftOut?: number;
}

/** The figure's notes, from one function the screen and the image both use. */
export function groupNotes({
	data,
	members,
	state,
	system,
	project,
	solved,
	prefs,
	others = [],
	labelsLeftOut = 0
}: GroupNotesInput): GroupNotes {
	const headUnit = displayUnit('head', prefs);
	const head = (m: number) => `${formatNumber(fromSI(m, headUnit), 4)} ${data.headUnit}`;
	const response = state?.status === 'ready' ? state.response : null;
	/** Refused only for an active PRV or PSV inside: a station, with no group curve there. */
	const undefinedThere = state?.status === 'refused' && pressureControlOnly(state.issues);
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
										text: undefinedThere
											? "These pumps form a station, but its group curve is not defined there; its group system curve is, and the pumps' own curves and points are drawn."
											: 'These pumps do not form a station, so they have no group curve; their own curves and points are drawn.'
									}
								: !state.response.converged
									? {
											kind: 'not_converged',
											text: `The case's solve did not converge, so no group curve is computed${state.response.message ? `: ${state.response.message}` : '.'}`
										}
									: !state.response.duty
										? {
												// The station's inlet or outlet has no head in this case (closed off) or no
												// level a rise can be read against (a floating section): no duty, no curve.
												kind: 'no_duty',
												text: `No group curve for this case: ${sentence(state.response.message || 'the station has no duty in this case')}`
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

	const systemShown = data.system?.some((p) => p.y !== null) ?? false;
	const against = andList([
		...(response?.duty ? ['the group curve'] : []),
		...(systemShown ? ['the group system curve'] : []),
		...(data.station ? ['the Group point'] : [])
	]);
	const axes =
		response?.duty || (systemShown && data.station)
			? `Each pump's curve and point are drawn against the flow through that pump; ${against} against the station's flow, the net flow into the station at its inlet.`
			: "Each pump's curve and point are drawn against the flow through that pump.";
	const {
		systemCurve,
		system: systemNote,
		systemDuty
	} = groupSystemNotes(data, state, system, project, prefs, solved);

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
				`At the duty's rise the group curve gives the solve's flows, the station's and every pump's (within ${dutyCheckTolerance(prefs)}): it passes through the Group point.`
			);
		} else if (check && check.flow === null) {
			// The station alone at the duty's rise has no solved flow: not another steady state.
			const reason = dutyPointReason(response);
			duty.push(
				reason === 'not_converged'
					? "The group curve's point at the duty's rise did not converge, so whether the curve passes through the Group point is not known."
					: reason === 'not_computed'
						? "The group curve's point at the duty's rise was not computed (the time budget ran out), so whether the curve passes through the Group point is not known."
						: "The group curve has no solved flow at the duty's rise, so whether it passes through the Group point is not known."
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
			// The rule compares the pump's own head, not the station's rise, with its shutoff head:
			// in parallel its own head is the rise plus its losses on the way, so it can stop at a
			// rise below its shutoff head.
			const shutoff = result.control
				? 'its shutoff head at its maximum speed'
				: `its shutoff head, ${head(result.shutoffHead.head)}`;
			const from = `${member.name} delivers nothing from a rise of ${head(stop)}, the first rise sampled where it has no flow`;
			memberNotes.push(
				response?.station.arrangement === 'parallel'
					? `${from}: its own head there, the rise plus its losses on the way, would be above ${shutoff}, so the solver closes it.`
					: `${from}: the solver closes a pump whose own head would be above ${shutoff}.`
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
		systemCurve,
		system: systemNote,
		systemDuty,
		axes,
		frame,
		duty,
		members: memberNotes,
		systemCurves:
			"Each pump's own system curve is on its pump chart above; it crosses that pump's curve, not the group curve.",
		dashed,
		others: otherNotes(data, others, stationResponse(state, system), project, {
			drawn: !!data.curve && data.missing < data.total,
			pressureControl: undefinedThere,
			labelsLeftOut
		})
	};
}

/**
 * The frame sentence's last part while a group curve is drawn and the rings' own curves are
 * judged (D24 §9.6): it replaces 4d's, exactly. The list of rings then says which applies.
 */
export const OTHER_CURVES_FRAME =
	"A ring lies on its own case's group curve where that case has one (none with an active PRV or PSV inside) and the station has one state at its rise (D13). Where its case differs from this one inside the station only in which pumps are switched on, and its curve has flow, that curve is drawn in slate and labelled with the number of pumps switched on; where it differs only outside the station, it is the group curve drawn for this case; otherwise it is not drawn. The list below says, for each ring, which.";

/**
 * The clip note (D24 §9.4, §9.6), after the frame sentence when the axes cut a curve: each clause
 * only when that cut was made (null with none): x max set cuts nothing when every other curve
 * ends inside it.
 */
export function clipNote(data: Pick<GroupChartData, 'curvesCut' | 'systemCut'>): string | null {
	const clauses = [
		...(data.curvesCut
			? [
					"other cases' group curves are cut at the chart's right edge, the largest flow of this case's own lines and the rings"
				]
			: []),
		...(data.systemCut ? ["the group system curve is cut at the top, above every pump's head"] : [])
	];
	return clauses.length
		? upperFirst(`${clauses.join('; ')}; the data tables list all their points.`)
		: null;
}

/** The notes' count of curves whose labels are left out for space (D24 §9.3); null for none. */
export function labelsLeftOutNote(n: number): string | null {
	return n > 0
		? `Labels of ${n} ${n === 1 ? 'curve' : 'curves'} are left out for space; the data table lists every curve.`
		: null;
}

/**
 * The notes on the other cases' station duties (slice 4d), in order: what a ring is (while one
 * is drawn), when one is called a point of the group system curve shown (while a ring and that
 * curve are drawn), the rings, and the other cases without one with the reason. While the other
 * cases' duties are not asked for (the box off: every case `off`), one line instead of a list:
 * a project whose scenarios have nothing to do with pumps would otherwise list every case on
 * every card and image.
 *
 * The frame holds for any number of pumps running and any arrangement: a ring is the station's
 * point, at the station's flow (in parallel the sum of the running pumps' flows, so with two or
 * more running it lies beyond each one's own flow, never below "their curves"), and it lies on
 * its own case's group curve where that case has one, which is the drawn group curve when its
 * case differs only outside the station (the group curve depends on head differences and flows
 * inside only, D21). Without a group curve drawn it is said against the group system curve (or
 * the Group point); with an active PRV or PSV inside, the station has no group curve (refused,
 * the station and its duty from the group system answer: stationResponse), and a ring is its
 * case's duty from its group system curve where one is active in that case too
 * (otherGroupCases), else from its group curve.
 *
 * With the rings' own curves judged (D24 slice L3: a group curve drawn and the rings' cases given
 * their curve states), the frame's last sentence is OTHER_CURVES_FRAME, the clip note follows the
 * frame when the axes cut a curve, each ring's entry in the list gains "; group curve: {words}",
 * and the count of curves whose labels are left out for space comes last.
 */
function otherNotes(
	data: GroupChartData,
	others: readonly OtherGroupCase[],
	station: PumpGroupCurveResponse | null,
	project: Project,
	curve: {
		/** A group curve is drawn (some point with a flow). */
		drawn: boolean;
		/** The group curve is refused only for an active PRV or PSV inside. */
		pressureControl: boolean;
		/** Curves whose labels are left out for space (placeCurveLabels). */
		labelsLeftOut: number;
	}
): string[] {
	if (others.length && others.every((o) => o.state === 'off')) {
		const n = others.length;
		return [
			`Other cases' station duties are not on the chart: tick “Also show the other cases' station duties” to compute them (${n} other ${n === 1 ? 'case' : 'cases'} with results).`
		];
	}
	const lines: string[] = [];
	const cases = data.others.flatMap((ring) => ring.cases).sort((a, b) => a.number - b.number);
	/** The rings' own curves are judged (D24 §9.6): the frame sentence is L3's. */
	const family = curve.drawn && cases.some((c) => c.curve !== null);
	if (cases.length && station) {
		const s = stationPortWords(station.station.inlet, project);
		const d = stationPortWords(station.station.outlet, project);
		const arrangement = station.station.arrangement;
		const against = curve.drawn
			? ' as the group curve is'
			: data.system?.some((p) => p.y !== null)
				? ' as the group system curve is'
				: data.station
					? ' as the Group point is'
					: '';
		lines.push(
			[
				`Each numbered slate ring is another case's station duty: that case's station flow and its rise from ${s} to ${d}, drawn against the station's flow${against}, not a pump's own point.`,
				...(arrangement === 'parallel'
					? [
							"In parallel that flow is the sum of the flows of the pumps running in that case, and that rise is each running pump's own head less its loss on the way."
						]
					: arrangement === 'series'
						? [
								'In series that flow passes through every pump, and that rise is their heads added together less the head across the elements between them.'
							]
						: []),
				"Each pump's own flow and head in each case are in Running combinations.",
				family
					? OTHER_CURVES_FRAME
					: curve.drawn
						? "A ring lies on its own case's group curve where that case has one (none with an active PRV or PSV inside) and the station has one state at its rise (D13): the curve drawn here when its case differs from this one only outside the station; with other pumps running, a curve of theirs that is not drawn."
						: curve.pressureControl
							? "With an active PRV or PSV inside, the station has no group curve, so none is drawn here; each ring is its case's duty from its group system curve where one is active in that case too, else from its group curve."
							: "A ring lies on its own case's group curve where that case has one (none with an active PRV or PSV inside) and the station has one state at its rise (D13); no group curve is drawn here."
			].join(' ')
		);
	}
	// The clip note (D24 §9.4): only while the family is drawn, and only for the cuts made.
	const clip = clipNote(data);
	if (clip) lines.push(clip);
	if (cases.length && data.system?.some((p) => p.y !== null)) lines.push(DUTY_CLAIM_RULE);
	if (cases.length) {
		const fmt = (v: number) => formatNumber(v, 4);
		lines.push(
			`Other cases on the chart (slate rings, numbered): ${cases
				.map(
					(c) =>
						`${c.number} · ${c.name}, ${fmt(c.flow)} ${data.flowUnit} at a rise of ${fmt(c.rise)} ${data.headUnit}: ${c.claim}${c.curve === null ? '' : `; group curve: ${c.curve}`}`
				)
				.join('; ')}.`
		);
	}
	const without = others.filter((o) => o.state !== 'ready');
	if (without.length) {
		lines.push(
			`Not on the chart: ${without
				.map((o) => `${o.name}${o.stale ? ' (out of date)' : ''} (${o.words})`)
				.join('; ')}.`
		);
	}
	const leftOut = labelsLeftOutNote(curve.labelsLeftOut);
	if (leftOut) lines.push(leftOut);
	return lines;
}

/** The tolerance of the group system curve's duty check (D6): 0.5 % of the rise, or this, m. */
export const SYSTEM_DUTY_CHECK_FLOOR = 0.01;

/**
 * The group system curve's notes (slice 4b): its state, what it is, and whether it passes through
 * the Group point at the duty's flow (crossing the group curve there when the group curve's duty
 * check agrees too), or why that is not known.
 */
function groupSystemNotes(
	data: GroupChartData,
	state: GroupCurveState | undefined,
	system: GroupSystemCurveState | undefined,
	project: Project,
	prefs: UnitPreferences,
	solved?: Project | null
): Pick<GroupNotes, 'systemCurve' | 'system' | 'systemDuty'> {
	const headUnit = displayUnit('head', prefs);
	const head = (m: number) => `${formatNumber(fromSI(m, headUnit), 4)} ${data.headUnit}`;
	const response = system?.status === 'ready' ? system.response : null;
	const systemCurve: GroupNotes['systemCurve'] =
		system === undefined
			? null
			: system.status === 'loading'
				? { kind: 'loading', text: 'Computing the group system curve for this solve…' }
				: system.status === 'error'
					? {
							kind: 'error',
							text: `The group system curve could not be computed: ${system.message}`
						}
					: system.status === 'cancelled'
						? {
								kind: 'cancelled',
								text:
									system.by === 'user'
										? 'The group system curve was not computed: you cancelled it.'
										: system.by === 'goalSeek'
											? 'The group system curve was not computed: a goal seek was started.'
											: 'The group system curve was not computed: a new solve was started.'
							}
						: system.status === 'refused'
							? {
									kind: 'refused',
									text: `No group system curve: ${sentence(system.message || 'these pumps do not form a station')}`
								}
							: !system.response.converged
								? {
										kind: 'not_converged',
										text: `The case's solve did not converge, so no group system curve is computed${system.response.message ? `: ${system.response.message}` : '.'}`
									}
								: !system.response.duty
									? {
											kind: 'no_duty',
											text: `No group system curve for this case: ${sentence(system.response.message || 'the station has no duty in this case')}`
										}
									: data.systemTotal && data.systemMissing === data.systemTotal
										? {
												kind: 'missing',
												text: 'No point of the group system curve has a rise, so it is not drawn; the data table says why for each.'
											}
										: data.systemMissing
											? {
													kind: 'missing',
													text: `${data.systemMissing} of ${data.systemTotal} group-system-curve points have no rise: the line has gaps there, and the data table says why for each.`
												}
											: null;

	let note: string | null = null;
	const duty: string[] = [];
	if (response?.duty) {
		const s = stationPortWords(response.station.inlet, project);
		const d = stationPortWords(response.station.outlet, project);
		note = `The group's system curve is the rise the rest of the network needs between ${s} and ${d} at each total flow; it does not depend on how the pumps share the flow.`;
		const check = response.systemDutyCheck;
		const groupAgrees = state?.status === 'ready' && !!state.response.dutyCheck?.agrees;
		const tolerance = `0.5 % or ${head(SYSTEM_DUTY_CHECK_FLOOR)}`;
		if (check?.agrees) {
			duty.push(
				`At the duty's flow the group system curve gives the solve's rise (within ${tolerance}): it passes through the Group point${groupAgrees ? ', where it crosses the group curve' : ''}.`
			);
		} else if (check && check.head === null) {
			const point = response.systemPoints.find((p) => p.isDuty);
			const why = point
				? systemPointNote(point, { project, solved, units: prefs, subject: 'station' }).text
				: '';
			duty.push(
				`The group system curve has no rise at the duty's flow, so whether it passes through the Group point is not known${why ? `: ${lowerFirst(why)}` : '.'}`
			);
		} else if (check) {
			duty.push(
				`The group system curve does not pass through the Group point: at the duty's flow it needs a rise of ${head(check.head!)} (the solve: ${head(response.duty.head)}), more than ${tolerance} apart.`,
				'Several steady states can exist (D13); the point is the one the solve found.'
			);
		}
	}
	return { systemCurve, system: note, systemDuty: duty };
}

/** "Its solve …" → "its solve …" (a sentence continued after a colon). */
function lowerFirst(text: string): string {
	return text.charAt(0).toLowerCase() + text.slice(1);
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
	if (check.flow === null) return "the station alone at the duty's rise has no solved flow";
	let zeroed = false;
	const flow = (q: number | null) => {
		if (q === null) return 'no flow';
		if (q !== 0 && dutyFlow(q) === 0) zeroed = true;
		return flowText(dutyFlow(q), prefs);
	};
	const differs = (a: number | null, b: number) =>
		a === null || Math.abs(a - b) > Math.max(0.005 * Math.abs(b), DUTY_CHECK_FLOOR);
	const pumps = check.members.flatMap((m) => {
		const solved = duty.members.find((d) => d.pumpId === m.pumpId);
		return solved && differs(m.flow, solved.flow)
			? [`${name(m.pumpId)} ${flow(m.flow)} (the solve: ${flow(solved.flow)})`]
			: [];
	});
	const words =
		`at the duty's rise it gives ${flow(check.flow)} (the solve: ${flow(duty.flow)})` +
		(pumps.length ? `, and ${andList(pumps)}` : '');
	return zeroed
		? `${words}; flows below ${flowText(DUTY_CHECK_FLOOR, prefs)}, the check's floor, are shown as 0`
		: words;
}

/**
 * The duty check's floor (m³/s): flows agree within 0.5 % or this, whichever is looser (the API's
 * PumpGroupDutyCheck.agrees; CLAUDE.md D21).
 */
export const DUTY_CHECK_FLOOR = 1e-6;

/**
 * A flow of the duty or of its check as shown in words: 0 below the check's floor, where a
 * station dead-headed gives solver noise about zero (the solve's own pump flows are 0 there).
 */
export function dutyFlow(q: number): number {
	return Math.abs(q) < DUTY_CHECK_FLOOR ? 0 : q;
}

/** The duty check's tolerance in display units: "0.5 % or 0.001 L/s". */
export function dutyCheckTolerance(prefs: UnitPreferences): string {
	return `0.5 % or ${flowText(DUTY_CHECK_FLOOR, prefs)}`;
}

/** The reason the duty's point of the group curve has no flow (null: it has one, or none given). */
export function dutyPointReason(
	response: PumpGroupCurveResponse
): 'not_converged' | 'not_computed' | null {
	return response.points.find((p) => p.isDuty)?.reason ?? null;
}

/** The duty check in a few words, for the data table's Group duty line. */
export function dutyCheckState(response: PumpGroupCurveResponse): string {
	const check = response.dutyCheck;
	if (!check) return '';
	if (check.agrees) return 'the group curve passes through it';
	if (check.flow !== null) return 'the group curve does not pass through it';
	const reason = dutyPointReason(response);
	return reason === 'not_converged'
		? 'not known, its point at the duty’s rise did not converge'
		: reason === 'not_computed'
			? 'not known, its point at the duty’s rise was not computed (the time budget ran out)'
			: 'not known, the group curve has no solved flow at the duty’s rise';
}

/** A flow in display units with its unit label. */
function flowText(q: number, prefs: UnitPreferences): string {
	const unit = displayUnit('flow', prefs);
	return `${formatNumber(fromSI(q, unit), 4)} ${unitLabel('flow', unit)}`;
}

/** A sentence ending in one full stop. */
function sentence(text: string): string {
	return /[.!?]$/.test(text.trim()) ? text.trim() : `${text.trim()}.`;
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
		notes.systemCurve?.text,
		notes.frame,
		notes.system,
		notes.axes,
		...notes.duty,
		...notes.systemDuty,
		...notes.others,
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
	project: Project,
	system: PumpGroupCurveResponse | null = null
): string {
	const fmt = (v: number) => formatNumber(v, 4);
	/** The station and its duty: the group curve's, else the group system curve's (the same). */
	const stationOf = response?.duty ? response : system?.duty ? system : null;
	const share = (id: string) =>
		stationOf?.duty?.members.find((m) => m.pumpId === id)?.share ?? null;
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
	const systemShown = data.system?.some((p) => p.y !== null) ?? false;
	const on = data.station?.crossing
		? ', on the group curve and the group system curve, where they cross'
		: data.station?.onCurve
			? ', on the group curve'
			: data.station?.onSystem && systemShown
				? ', on the group system curve'
				: '';
	const station =
		stationOf && data.station
			? `; station duty ${fmt(data.station.flow)} ${data.flowUnit} at a rise of ${fmt(data.station.point.y)} ${data.headUnit} from ${stationPortWords(stationOf.station.inlet, project)} to ${stationPortWords(stationOf.station.outlet, project)}${on}`
			: '';
	const cases = data.others.flatMap((ring) => ring.cases).sort((a, b) => a.number - b.number);
	const others = cases.length
		? `; other cases' station duties: ${cases
				.map(
					(c) =>
						`${c.number} · ${c.name}, ${fmt(c.flow)} ${data.flowUnit} at a rise of ${fmt(c.rise)} ${data.headUnit} (${c.claim}${c.curve === null ? '' : `; group curve: ${c.curve}`})`
				)
				.join('; ')}`
		: '';
	// Their own group curves drawn (D24 §9.6): each by its ring number and its members on.
	const family = data.otherCurves.length
		? `; other cases' group curves drawn: ${andList(data.otherCurves.map((c) => `${c.number} (${c.running})`))}`
		: '';
	const curve =
		data.curve && data.missing < data.total ? '; group curve shown' : '; no group curve shown';
	const systemCurve = system
		? systemShown
			? '; group system curve shown'
			: '; no group system curve shown'
		: '';
	return `Pump curves and points of ${parts.join('; ')}${station}${others}${family}${curve}${systemCurve}.`;
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
				value: f.value(dutyFlow(response.duty.flow), 'flow')
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

/** A member's status at a point or at the duty (running, off, no flow), as the data table words it. */
export const MEMBER_STATUS_WORDS: Readonly<Record<string, string>> = {
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
	prefs: UnitPreferences,
	project?: Project
): GroupSampleRow[] {
	return sampleRows(response.points, memberIds, prefs, project);
}

/** groupSampleRows over a group curve's points (the shown case's, or another case's: D24). */
function sampleRows(
	points: readonly PumpGroupCurvePoint[],
	memberIds: readonly string[],
	prefs: UnitPreferences,
	project?: Project
): GroupSampleRow[] {
	// The outer loop's own words follow "not converged: " (the schema's reason): told once, ids in
	// quotes named and values in display units when the project is given.
	const notConverged = (message: string) => {
		const rest = message.replace(/^not converged:\s*/, '').trim();
		if (!rest) return 'Its solve did not converge.';
		const words = project
			? readableText(rest, project, prefs)
			: rest.charAt(0).toUpperCase() + rest.slice(1);
		return `Its solve did not converge. ${words}${/[.!?]$/.test(words) ? '' : '.'}`;
	};
	const flowUnit = displayUnit('flow', prefs);
	const headUnit = displayUnit('head', prefs);
	const fmt = (v: number) => formatNumber(v, 4);
	return [...points]
		.sort((a, b) => a.head - b.head)
		.map((p) => ({
			rise: fmt(fromSI(p.head, headUnit)),
			flow: p.flow === null ? '—' : fmt(fromSI(p.flow, flowUnit)),
			duty: p.isDuty,
			members: memberIds.map((id) => {
				const m = p.members.find((x) => x.pumpId === id);
				if (!m) return { flow: '—', head: '—', state: '—' };
				const control = m.controlState ? CONTROL_WORDS[m.controlState] : null;
				const state = `${MEMBER_STATUS_WORDS[m.status] ?? m.status}${control && m.status === 'running' ? `, ${control}` : ''}${m.beyondData ? ', beyond its data' : ''}`;
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
							? notConverged(p.message)
							: p.message
		}));
}

/** The rows of one other case's group curve in the data table (D24 §9.6). */
export interface OtherCurveRowGroup {
	/** '' for the base, else the scenario id. */
	key: string;
	/** The row group's header: "1 · {name}: 3 running" ("as last solved: 3 running" when stale). */
	header: string;
	/** Every point of its response, in rise order, those cut from the chart included. */
	rows: { rise: string; flow: string; note: string }[];
}

/**
 * "Other cases' group curves (station's flow at each rise)": one row group per case whose own
 * group curve is drawn, in number order; each point's rise and the station's flow as
 * groupSampleRows formats them, its duty's rise noted "Its duty's rise (its duty check).", and a
 * point without a flow by its message, as groupSampleRows gives it.
 */
export function otherCurveRows(
	others: readonly OtherGroupCase[],
	prefs: UnitPreferences,
	project?: Project
): OtherCurveRowGroup[] {
	return others
		.filter((o) => o.onChart && o.state === 'ready' && o.curve && o.number !== null)
		.sort((a, b) => a.number! - b.number!)
		.map((o) => ({
			key: o.key,
			header: `${o.number} · ${o.name}${o.stale ? ' (out of date)' : ''}: ${runningWords(o.curve!.on, o.stale)}`,
			rows: sampleRows(o.curve!.points, [], prefs, project).map((row) => ({
				rise: row.rise,
				flow: row.flow,
				note: [row.duty ? "Its duty's rise (its duty check)." : '', row.note]
					.filter(Boolean)
					.join(' ')
			}))
		}));
}

/** The column "Its group curve" of "Other cases' station duties" (D24 §9.6). */
export const OTHER_CURVE_COLUMN = 'Its group curve';
/** The new table's caption (D24 §9.6). */
export const OTHER_CURVES_CAPTION = "Other cases' group curves (station's flow at each rise)";

/** A group system curve's sample as the data table lists it (formatted, display units). */
export interface GroupSystemRow {
	flow: string;
	/** The rise ('—' without one). */
	rise: string;
	/** Duty: the point at the duty's flow (the system duty check). */
	duty: boolean;
	/** Why the point has no rise ('' when it has one), in names and display units. */
	note: string;
	/** The API's sentence, when `note` is told in the browser. */
	detail?: string;
}

/**
 * Every sample of the group system curve, in flow order, with its rise or why it has none: the
 * pump chart's system-curve rows (system-curve-text.ts), in the station's words. `names` tells a
 * reason with element names (the labels project) and each element's rule from the project as
 * solved; without it, a point keeps the API's sentence.
 */
export function groupSystemRows(
	response: PumpGroupCurveResponse,
	prefs: UnitPreferences,
	names: Omit<SystemCurveTextContext, 'units' | 'subject'> | null = null
): GroupSystemRow[] {
	const flowUnit = displayUnit('flow', prefs);
	const headUnit = displayUnit('head', prefs);
	const fmt = (v: number) => formatNumber(v, 4);
	return [...response.systemPoints]
		.sort((a, b) => a.flow - b.flow)
		.map((p: PumpGroupSystemPoint) => {
			const why =
				p.head !== null
					? { text: '' }
					: names
						? systemPointNote(p, { ...names, units: prefs, subject: 'station' })
						: { text: p.message };
			return {
				flow: fmt(fromSI(p.flow, flowUnit)),
				rise: p.head === null ? '—' : fmt(fromSI(p.head, headUnit)),
				duty: p.isDuty,
				note: why.text,
				...(why.detail ? { detail: why.detail } : {})
			};
		});
}

/** The group system curve's duty check in a few words, for the data table's Group duty line. */
export function systemDutyCheckState(response: PumpGroupCurveResponse): string {
	const check = response.systemDutyCheck;
	if (!check) return '';
	if (check.agrees) return 'the group system curve passes through it';
	if (check.head !== null) return 'the group system curve does not pass through it';
	return 'not known, the group system curve has no rise at the duty’s flow';
}

// ---------------------------------------------------------------------------------------------
// Read along the curves (slice 4b)
// ---------------------------------------------------------------------------------------------

/** Where the readout marks the chart: the rise read and the points read there (display units). */
export interface GroupReadoutMark {
	/** The rise read (display unit). */
	rise: number;
	/** Each member's point (its flow, its own head) and the station's (its flow, the rise). */
	points: ChartPoint[];
}

/** A sample of the group curve as the readout gives it. */
export interface GroupReadoutSample {
	/** "At a rise of 20 m: Pump PA 43.8 L/s, Pump PB 24 L/s, group 67.8 L/s". */
	text: string;
	/** The sample at the duty's rise. */
	duty: boolean;
	mark: GroupReadoutMark;
}

/**
 * "Read along the curves": the group curve's samples in rise order, each with every member's
 * flow and the station's at that rise, exactly as the response gives them (display units, the
 * card's four figures), and the points to mark. Nothing between samples is read.
 */
export function groupReadout(
	response: PumpGroupCurveResponse,
	name: (pumpId: string) => string,
	prefs: UnitPreferences
): GroupReadoutSample[] {
	const flowUnit = displayUnit('flow', prefs);
	const headUnit = displayUnit('head', prefs);
	const flowLabel = unitLabel('flow', flowUnit);
	const headLabel = unitLabel('head', headUnit);
	const fmt = (v: number) => formatNumber(v, 4);
	return [...response.points]
		.sort((a, b) => a.head - b.head)
		.map((p) => {
			const rise = fromSI(p.head, headUnit);
			const at = `At a rise of ${fmt(rise)} ${headLabel}`;
			if (p.flow === null) {
				return {
					text: `${at}: no flow solved here; the data table says why.`,
					duty: p.isDuty,
					mark: { rise, points: [] }
				};
			}
			const members = response.station.memberIds.flatMap((id) => {
				const m = p.members.find((x) => x.pumpId === id);
				if (!m) return [];
				const state =
					m.status === 'running'
						? ''
						: ` (${MEMBER_STATUS_WORDS[m.status]?.toLowerCase() ?? m.status})`;
				return [`${name(id)} ${fmt(fromSI(m.flow, flowUnit))} ${flowLabel}${state}`];
			});
			const points: ChartPoint[] = [
				...p.members.flatMap((m) =>
					m.head === null ? [] : [{ x: fromSI(m.flow, flowUnit), y: fromSI(m.head, headUnit) }]
				),
				{ x: fromSI(p.flow, flowUnit), y: rise }
			];
			return {
				text: `${at}: ${[...members, `group ${fmt(fromSI(p.flow, flowUnit))} ${flowLabel}`].join(', ')}`,
				duty: p.isDuty,
				mark: { rise, points }
			};
		});
}

/** The methods section of the response: "How this curve is computed". */
export function groupMethods(state: GroupCurveState | undefined): MethodsSection | null {
	return state?.status === 'ready' ? state.response.methods : null;
}

/** "Pump group (calculation methods 1.6.0)": the heading the card and the export give a response's methods. */
export function groupMethodsHeading(r: PumpGroupCurveResponse): string {
	return `${r.methods.title} (calculation methods ${r.methodVersion})`;
}

/** A response's methods as text lines, in methodsText's layout (trace.ts): heading, "- item", "References:", "- ref". */
export function groupMethodsLines(r: PumpGroupCurveResponse): string[] {
	return [
		groupMethodsHeading(r),
		...r.methods.items.map((item) => `- ${item}`),
		...(r.methods.references.length
			? ['References:', ...r.methods.references.map((ref) => `- ${ref}`)]
			: [])
	];
}
