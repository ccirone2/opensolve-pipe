/**
 * One pump off, drawn together (CLAUDE.md D21 slice 4d, proposal pump-groups.md §8 and §17), with
 * pump lineups (CLAUDE.md D24 slice L1, proposal pump-lineups.md §7): the Pumps together card's
 * other cases.
 *
 * - The cases the card's Add cases block makes are pump-lineups.ts's lineupPlan (By number
 *   running, or Each pump off: 4d's cases, whose existing case is found by sameCase and whose
 *   idle member, on but carrying no flow, is read from its flow), drawn by PumpLineupsBlock.
 * - Other cases' station duties: each from that case's own group-curve answer (never computed
 *   here), drawn as a numbered ring only when its station is the one shown; a ring is called a
 *   point of the group system curve shown only when that case, as solved, is the same as this one
 *   outside the station (hydraulicFingerprint of each project without the station's interior, the
 *   design checks and the library entries no element outside refers to: D21, the curve depends on
 *   nothing inside), its flow is above zero, the curve has a rise at the computed flows on both
 *   sides of it, and the shown case's own system duty check agrees (D13). The chart takes the
 *   cases in lineupChartPriority's order (one lineup of each number running first), at most
 *   MAX_GROUP_CASES.
 * - The curve family (D24 slice L3, proposal pump-lineups.md §9.1, §9.5): a ring's own group
 *   curve, from the same answer, is drawn only when this case's group curve is drawn, the ring's
 *   answer is a group curve, its station differs from this case's inside only in which members are
 *   switched on (insideOf, both as solved) and the curve has flow; its ring is called the crossing
 *   with the group system curve only when its duty check agrees, the claim is `on` and the curve
 *   is drawn. Each ring's curve state is said in OTHER_CURVE_WORDS.
 * - Running combinations: every case's members, with the group table's cell rules applied to that
 *   case's own solve (Compare's rule says which responses have values), a line per case saying
 *   which members carry flow, are on and carry none, are off or have no result (read from the
 *   solve, never from the name; D24 §7.10), and the extremes over the current cases (screen
 *   only, never in the image or the export: D17).
 *
 * Names need not be unique: two members of one name are told apart by their ids wherever words
 * alone name them (the cases made, the block's notes, Running combinations' row headers and
 * lines, the extremes; memberLabels).
 *
 * Pure: every value is the API's; the store's fingerprint is passed in (no util imports the store).
 */
import type {
	Component,
	Flag,
	Project,
	PumpGroupCurvePoint,
	PumpGroupCurveResponse,
	PumpGroupStation,
	SolveResponse,
	UnitPreferences
} from '../api/types';
import type { CaseStatus, GroupCurveState, GroupSystemCurveState } from '../state/project.svelte';
import { CHECK_TITLES, OUTCOME_ORDER, OUTCOME_TITLES } from './design-checks';
import type { Calculating } from './goal-seek';
import { canonicalJson } from './json';
import { CASE_STATUS_LABELS } from './labels';
import {
	andList,
	DUTY_CHECK_FLOOR,
	dutyFlow,
	runningWords,
	slotStyle,
	stationPortWords,
	type GroupSlot
} from './pump-group-chart';
import { MAX_GROUP_PUMPS, pressureControlOnly, refusalWords, wordsText } from './pump-groups';
import { carriesFlow, lineupChartPriority, memberLabels } from './pump-lineups';
import { Formatter, flagsForElement, pumpStatusLabel, type Column } from './results';
import type { CaseId } from './scenarios';

export { DUTY_CLAIM_RULE, runningWords } from './pump-group-chart';
export { addedNotice, memberLabels, offName, offOverride } from './pump-lineups';

/**
 * Other cases on the group chart at once: every case with one pump off of a full group, and
 * every number running of one (N − 1 ≤ 5; D24 §7.9).
 */
export const MAX_GROUP_CASES = MAX_GROUP_PUMPS;

// ---------------------------------------------------------------------------------------------
// The rest of the network, and whether a ring is a point of the group system curve shown
// ---------------------------------------------------------------------------------------------

/** Every string in `value`, at any depth (the ids an element refers to among them). */
function stringsIn(value: unknown, into: Set<string> = new Set()): Set<string> {
	if (typeof value === 'string') into.add(value);
	else if (Array.isArray(value)) for (const item of value) stringsIn(item, into);
	else if (value && typeof value === 'object') {
		for (const item of Object.values(value)) stringsIn(item, into);
	}
	return into;
}

/**
 * The project as the rest of the network sees it: without the station's interior (its components
 * and connections), and without what changes no value outside it: the design checks (D19: a check
 * never changes a solved value) and the library entries no element outside refers to (D22: a pump
 * curve only members use, a pipe spec or resistance entry used only inside; an edit to one reaches
 * only its users). An entry is kept when its id is any string of the elements outside, so a
 * reference of any kind keeps it (ids are one namespace: factory.ts usedIds); a name that happens
 * to equal an id keeps one entry more, which can only withhold a "Yes". The fluid, the settings
 * the solve reads and every element outside (boundaries, assigned flows, relief valves) stay.
 */
export function restOf(project: Project, station: PumpGroupStation): Project {
	const inside = new Set(station.interiorComponentIds);
	const insideConnections = new Set(station.interiorConnectionIds);
	const components = project.components.filter((c) => !inside.has(c.id));
	const connections = project.connections.filter((c) => !insideConnections.has(c.id));
	const used = stringsIn([components, connections]);
	const settings = { ...project.settings };
	delete settings.designChecks;
	const rest: Project = {
		...project,
		settings,
		components,
		connections,
		pumpLibrary: project.pumpLibrary.filter((c) => used.has(c.id))
	};
	// Absent when none is left, as in a project without a library (hydraulicFingerprint).
	const pipeLibrary = (project.pipeLibrary ?? []).filter((s) => used.has(s.id));
	const resistanceLibrary = (project.resistanceLibrary ?? []).filter((e) => used.has(e.id));
	if (pipeLibrary.length) rest.pipeLibrary = pipeLibrary;
	else delete rest.pipeLibrary;
	if (resistanceLibrary.length) rest.resistanceLibrary = resistanceLibrary;
	else delete rest.resistanceLibrary;
	return rest;
}

/**
 * Two cases, each as solved, are the same outside the station: the fingerprints of their rests
 * (restOf) are equal (false when either is missing). The group system curve holds everything
 * inside closed (D21), so with equal rests the curve shown is the other case's too.
 */
export function sharedRest(
	shown: Project | null,
	other: Project | null,
	station: PumpGroupStation,
	fingerprint: (project: Project) => string
): boolean {
	if (!shown || !other) return false;
	return fingerprint(restOf(shown, station)) === fingerprint(restOf(other, station));
}

/**
 * The station as its group curve sees it (D24 §9.1 condition 4): its interior components, the
 * members without their `status`, the interior connections, the fluid, the settings without the
 * design checks (D19: a check never changes a solved value), and the library entries used inside
 * (an entry is kept when its id is any string of the interior, as restOf keeps one used outside).
 * The group curve is the station solved alone (D21), so two cases whose insides are equal differ
 * in their group curves only by which members are switched on.
 */
export function insideOf(project: Project, station: PumpGroupStation): Project {
	const inside = new Set(station.interiorComponentIds);
	const insideConnections = new Set(station.interiorConnectionIds);
	const members = new Set(station.memberIds);
	const components = project.components
		.filter((c) => inside.has(c.id))
		.map((c): Component => {
			if (c.type !== 'pump' || !members.has(c.id)) return c;
			const unswitched: Partial<typeof c> = { ...c };
			delete unswitched.status;
			return unswitched as Component;
		});
	const connections = project.connections.filter((c) => insideConnections.has(c.id));
	const used = stringsIn([components, connections]);
	const settings = { ...project.settings };
	delete settings.designChecks;
	const interior: Project = {
		...project,
		settings,
		components,
		connections,
		pumpLibrary: project.pumpLibrary.filter((c) => used.has(c.id))
	};
	// Absent when none is left, as in a project without a library (hydraulicFingerprint).
	const pipeLibrary = (project.pipeLibrary ?? []).filter((s) => used.has(s.id));
	const resistanceLibrary = (project.resistanceLibrary ?? []).filter((e) => used.has(e.id));
	if (pipeLibrary.length) interior.pipeLibrary = pipeLibrary;
	else delete interior.pipeLibrary;
	if (resistanceLibrary.length) interior.resistanceLibrary = resistanceLibrary;
	else delete interior.resistanceLibrary;
	return interior;
}

/**
 * How another case's station compares with the shown case's inside, both as solved (D24 §9.1):
 * - `same`: the same inside, members switched on alike (the ink curve is its own group curve);
 * - `statuses`: the same inside but for which members are switched on (its curve can be drawn);
 * - `differs`: anything else inside differs (a speed, a setpoint, a valve), or a case is missing.
 */
export type InsideComparison = 'same' | 'statuses' | 'differs';

/**
 * The two cases' insideOf fingerprints compared, then the members' statuses (`status` of each of
 * the station's members, as solved). Symmetric: either case may be the one shown.
 */
export function sameInside(
	shown: Project | null,
	other: Project | null,
	station: PumpGroupStation,
	fingerprint: (project: Project) => string
): InsideComparison {
	if (!shown || !other) return 'differs';
	if (fingerprint(insideOf(shown, station)) !== fingerprint(insideOf(other, station))) {
		return 'differs';
	}
	const statuses = (project: Project) =>
		station.memberIds.map((id) => {
			const c = project.components.find((x) => x.id === id);
			return c?.type === 'pump' ? c.status : null;
		});
	const a = statuses(shown);
	const b = statuses(other);
	return a.every((s, i) => s === b[i]) ? 'same' : 'statuses';
}

/** Two answers name the same station: its ports, arrangement, members and interior. */
export function sameStation(a: PumpGroupStation, b: PumpGroupStation): boolean {
	const key = (s: PumpGroupStation) =>
		canonicalJson({
			inlet: s.inlet,
			outlet: s.outlet,
			arrangement: s.arrangement,
			memberIds: s.memberIds,
			interiorComponentIds: s.interiorComponentIds,
			interiorConnectionIds: s.interiorConnectionIds
		});
	return key(a) === key(b);
}

/** Whether an other case's duty is called a point of the group system curve shown, or why not. */
export type DutyClaim =
	'on' | 'rest_differs' | 'no_curve' | 'zero_flow' | 'beyond_range' | 'gap' | 'shown_duty';

export const DUTY_CLAIM_WORDS: Readonly<Record<DutyClaim, string>> = {
	on: 'Yes: the same rest of the network',
	// Symmetric: whichever case is shown, the two rests differ (neither is said to change it).
	rest_differs:
		"No: the rest of the network differs from this case's; its own group system curve is not drawn",
	no_curve: 'Not said: no group system curve is drawn for this case',
	zero_flow: 'Not said: at zero station flow the rest can hold more than one state (D13)',
	beyond_range: 'Not said: its flow is beyond the flows this curve was computed for',
	gap: 'Not said: the curve has no rise next to its flow',
	shown_duty: "Not said: this case's own duty is not on the curve (D13)"
};

/**
 * The first that applies: the rests differ; no group system curve is shown; the duty is at zero
 * station flow (below the duty check's floor); no computed flow of the curve lies at or below it,
 * or at or above it; the nearest of those on either side has no rise; the shown case's own system
 * duty check does not agree; else on.
 */
export function dutyClaim(input: {
	shared: boolean;
	duty: { flow: number; head: number };
	system: PumpGroupCurveResponse | null;
}): DutyClaim {
	const { shared, duty, system } = input;
	if (!shared) return 'rest_differs';
	if (!system || !system.systemPoints.length) return 'no_curve';
	const q = dutyFlow(duty.flow);
	if (q === 0) return 'zero_flow';
	const points = [...system.systemPoints].sort((a, b) => a.flow - b.flow);
	const below = points.filter((p) => p.flow <= q).at(-1);
	const above = points.find((p) => p.flow >= q);
	if (!below || !above) return 'beyond_range';
	if (below.head === null || above.head === null) return 'gap';
	if (!system.systemDutyCheck?.agrees) return 'shown_duty';
	return 'on';
}

// ---------------------------------------------------------------------------------------------
// The other cases on the chart
// ---------------------------------------------------------------------------------------------

/**
 * The keys of the cases on the chart: lineupChartPriority's order (D24 §4.6) without the cases
 * unticked under "Cases on this chart", at most MAX_GROUP_CASES, so a case unticked lets the next
 * one in.
 */
export function chartKeys(
	keys: readonly { key: string; caseId: CaseId }[],
	project: Project,
	memberIds: readonly string[],
	unticked: readonly string[]
): string[] {
	return lineupChartPriority(keys, project, memberIds)
		.filter((key) => !unticked.includes(key))
		.slice(0, MAX_GROUP_CASES);
}

export interface OtherGroupCase {
	/** '' for the base, else the scenario id. */
	key: string;
	caseId: CaseId;
	name: string;
	stale: boolean;
	/** On the chart: ticked under "Cases on this chart" and within the limit. */
	onChart: boolean;
	/** The ring number (the order of `valued` among the cases drawn); null when not drawn. */
	number: number | null;
	state:
		| 'unticked'
		| 'off'
		| 'waiting'
		| 'loading'
		| 'cancelled'
		| 'error'
		| 'refused'
		| 'no_duty'
		| 'other_station'
		| 'ready';
	/** The state in words; for a ring, its claim's short words. */
	words: string;
	/** Q_st and ΔH_st (SI), the API's; null without a ring. */
	duty: { flow: number; head: number } | null;
	claim: DutyClaim | null;
	/** "Compute them again" applies: cancelled by the user, or failed. */
	retry: boolean;
	/**
	 * Its own group curve when drawn (D24 §9.1): the response's points, the members switched on in
	 * that case as solved and the members' count; null when not drawn.
	 */
	curve: { points: readonly PumpGroupCurvePoint[]; on: number; of: number } | null;
	/**
	 * Why its curve is or is not drawn (D24 §9.1, §9.5). Null without a ring, and while the chart
	 * is 4d's: this case's own group curve not drawn, or the ring's case given no `inside` and `on`.
	 */
	curveState: OtherCurveState | null;
	/** The curve state in words (OTHER_CURVE_WORDS, a stale case's k "as last solved"); null with none. */
	curveWords: string | null;
}

/** Why a ring's own group curve is or is not drawn (D24 §9.1), and what its ring is then (§9.5). */
export type OtherCurveState =
	| 'crossing'
	| 'through'
	| 'not_through'
	| 'same_inside'
	| 'inside_differs'
	| 'no_group_curve'
	| 'no_flow';

/**
 * Each curve state in words (D24 §9.6, the notes' list; the table's column starts them with a
 * capital), from the members switched on in words (runningWords: "3 running", or "as last solved:
 * 3 running" for a stale case).
 */
export const OTHER_CURVE_WORDS: Readonly<Record<OtherCurveState, (running: string) => string>> = {
	crossing: (running) => `drawn (${running}): it crosses the group system curve at the ring`,
	through: (running) => `drawn (${running}): it passes through the ring`,
	not_through: (running) => `drawn (${running}): it does not pass through the ring (D13)`,
	same_inside: () => "the same as this case's: the station is the same inside",
	inside_differs: () =>
		'not drawn: the station differs inside in more than which pumps are switched on',
	no_group_curve: () => 'none: an active PRV or PSV inside',
	no_flow: () => 'not drawn: no flow at any rise'
};

/**
 * This case's own group curve is drawn (D24 §9.1 condition 3): its ready answer has a point with
 * a flow. Without it the chart is 4d's: rings only.
 */
export function groupCurveDrawn(state: GroupCurveState | undefined): boolean {
	return state?.status === 'ready' && state.response.points.some((p) => p.flow !== null);
}

export interface OtherCasesInput {
	/**
	 * The other cases with values (Compare's rule), in the chart's order (lineupChartPriority's,
	 * unticked ones in their place; D24 §7.9): listed and numbered in this order.
	 */
	valued: readonly {
		key: string;
		caseId: CaseId;
		name: string;
		stale: boolean;
		group: GroupCurveState | undefined;
		system: GroupSystemCurveState | undefined;
		/** sharedRest(…) of this case and the case shown. */
		shared: boolean;
		/** This case as solved (ws.store.caseInputs): a refusal's topology. */
		solved: Project | null;
		/**
		 * sameInside(…) of the case shown and this case (D24 §9.1 condition 4). Absent: no curve
		 * state (4d's chart, rings only).
		 */
		inside?: InsideComparison;
		/**
		 * The members switched on in this case as solved: pumpLineup(undefined, caseInputs(caseId),
		 * memberIds).on.length (D24 §9.1). Absent: no curve state.
		 */
		on?: number;
	}[];
	/**
	 * This case's own group curve is drawn (groupCurveDrawn; D24 §9.1 condition 3; default
	 * false): without it no other case's curve is drawn and none has a curve state.
	 */
	curveDrawn?: boolean;
	/** The keys on the chart: ticked and within MAX_GROUP_CASES. */
	shownKeys: ReadonlySet<string>;
	/** "Also show the other cases' station duties" is ticked. */
	othersOn: boolean;
	/** The case shown's curves have answered (its requests go first in the one queue). */
	shownSettled: boolean;
	/**
	 * What the page is calculating (store.calculating; default null): while a solve, Solve all or
	 * goal seek runs, no other case is asked, so one not asked yet waits for it.
	 */
	calculating?: Calculating;
	/** The station the card shows. */
	station: PumpGroupStation;
	/** The case shown's group system curve (ready), else null. */
	systemShown: PumpGroupCurveResponse | null;
	memberIds: readonly string[];
	/** Names (the labels project, with elements deleted since as solved). */
	project: Project;
	/** The pumps the card has a box for. */
	boxes: readonly string[];
}

/** A sentence ending in one full stop. */
function sentence(text: string): string {
	return /[.!?]$/.test(text.trim()) ? text.trim() : `${text.trim()}.`;
}

const CANCELLED_WORDS: Readonly<Record<'user' | 'solve' | 'goalSeek', string>> = {
	user: 'cancelled: you cancelled it',
	solve: 'cancelled by a solve; asked again when it ends',
	goalSeek: 'cancelled by a goal seek; asked again when it ends'
};

/** A calculation an other case not asked yet waits for, as the Scenarios menu names it. */
const CALCULATION_WORDS: Readonly<Record<NonNullable<Calculating>, string>> = {
	solve: 'the solve',
	solveAll: 'Solve all',
	goalSeek: 'the goal seek'
};

/** Each other case with values, in the order given, in its state with its words and its ring. */
export function otherGroupCases(input: OtherCasesInput): OtherGroupCase[] {
	const { station, project } = input;
	let number = 0;
	return input.valued.map((v) => {
		const base = {
			key: v.key,
			caseId: v.caseId,
			name: v.name,
			stale: v.stale,
			onChart: input.shownKeys.has(v.key),
			number: null,
			duty: null,
			claim: null,
			retry: false,
			curve: null,
			curveState: null,
			curveWords: null
		};
		const as = (state: OtherGroupCase['state'], words: string, retry = false): OtherGroupCase => ({
			...base,
			state,
			words,
			retry
		});
		/**
		 * A state of a request, or null when it is ready (its response). One not asked yet waits
		 * for a calculation that runs, then for the case shown's curves; asked in this turn
		 * otherwise (the Pumps view's first requests).
		 */
		const pending = (s: GroupCurveState | undefined): OtherGroupCase | null => {
			if (s === undefined) {
				const shown = input.shownSettled ? '' : "this case's curves";
				if (input.calculating) {
					const calculation = CALCULATION_WORDS[input.calculating];
					return as(
						'waiting',
						`waits for ${calculation} to end${shown ? `, then for ${shown}` : ''}`
					);
				}
				return shown ? as('waiting', `waits for ${shown}`) : as('loading', 'being computed');
			}
			// The store sends no curve request while a calculation runs (its queue waits for the
			// end): one asked then, by "Compute them again" before it was unavailable, waits too.
			if (s.status === 'loading') {
				return input.calculating
					? as('waiting', `waits for ${CALCULATION_WORDS[input.calculating]} to end`)
					: as('loading', 'being computed');
			}
			if (s.status === 'cancelled') return as('cancelled', CANCELLED_WORDS[s.by], s.by === 'user');
			if (s.status === 'error') return as('error', `failed: ${s.message}`, true);
			return null;
		};
		// The box off first: "Cases on this chart" is not shown then.
		if (!input.othersOn) {
			return as('off', "not computed: tick “Also show the other cases' station duties”");
		}
		if (!base.onChart)
			return as('unticked', 'not on the chart (unticked under Cases on this chart)');
		const group = pending(v.group);
		if (group) return group;
		let response: PumpGroupCurveResponse | null = null;
		if (v.group?.status === 'refused') {
			if (!pressureControlOnly(v.group.issues)) {
				const issue = v.group.issues[0];
				const words = issue
					? wordsText(
							refusalWords(issue, input.memberIds, project, {
								...(v.solved ? { solved: v.solved } : {}),
								boxes: input.boxes
							})
						)
					: sentence(v.group.message);
				return as('refused', `not a station in this case: ${words}`);
			}
			const system = pending(v.system);
			if (system) return system;
			if (v.system?.status === 'refused') {
				return as('refused', `not a station in this case: ${sentence(v.system.message)}`);
			}
			response = v.system?.status === 'ready' ? v.system.response : null;
		} else if (v.group?.status === 'ready') {
			response = v.group.response;
		}
		if (!response) return as('loading', 'being computed');
		if (!response.duty) {
			return as(
				'no_duty',
				`no duty: ${sentence(response.message || 'the station has no duty in this case')}`
			);
		}
		if (!sameStation(response.station, station)) {
			const s = stationPortWords(response.station.inlet, project);
			const d = stationPortWords(response.station.outlet, project);
			return as('other_station', `another station in this case: from ${s} to ${d} there`);
		}
		const duty = { flow: response.duty.flow, head: response.duty.head };
		const claim = dutyClaim({ shared: v.shared, duty, system: input.systemShown });
		const curveState = otherCurveState(v, response, claim, input.curveDrawn ?? false);
		const drawn =
			curveState === 'crossing' || curveState === 'through' || curveState === 'not_through';
		return {
			...base,
			state: 'ready',
			words: DUTY_CLAIM_WORDS[claim],
			number: ++number,
			duty,
			claim,
			retry: false,
			curve: drawn ? { points: response.points, on: v.on!, of: input.memberIds.length } : null,
			curveState,
			curveWords: curveState ? OTHER_CURVE_WORDS[curveState](runningWords(v.on!, v.stale)) : null
		};
	});
}

/**
 * A ring's curve state (D24 §9.1, §9.5), the first that applies: none while the chart is 4d's
 * (this case's group curve not drawn, or no `inside` and `on` given); its answer is the group
 * system curve's (a group curve refused for an active PRV or PSV inside); the station is the same
 * inside (its group curve is the one drawn for this case); it differs inside in more than which
 * members are switched on; no point has a flow above DUTY_CHECK_FLOOR. Otherwise its curve is
 * drawn, and its ring is called the crossing only when its own duty check agrees (D13) and 4d's
 * claim is `on`; on its curve when the check agrees; else not on it.
 */
function otherCurveState(
	v: OtherCasesInput['valued'][number],
	response: PumpGroupCurveResponse,
	claim: DutyClaim,
	curveDrawn: boolean
): OtherCurveState | null {
	if (!curveDrawn || v.inside === undefined || v.on === undefined) return null;
	if (v.group?.status !== 'ready') return 'no_group_curve';
	if (v.inside === 'same') return 'same_inside';
	if (v.inside === 'differs') return 'inside_differs';
	if (!response.points.some((p) => p.flow !== null && p.flow > DUTY_CHECK_FLOOR)) return 'no_flow';
	if (!response.dutyCheck?.agrees) return 'not_through';
	return claim === 'on' ? 'crossing' : 'through';
}

// ---------------------------------------------------------------------------------------------
// Running combinations
// ---------------------------------------------------------------------------------------------

export interface CombinationsInput {
	/** The card's members, with their slots. */
	members: readonly { id: string; name: string; slot: number }[];
	/** Every case: the shown first, then the others in case order. */
	cases: readonly {
		key: string;
		name: string;
		shown: boolean;
		status: CaseStatus;
		/** Compare's rule (caseResponse): null for a failed or not reached case. */
		response: SolveResponse | null;
		stale: boolean;
		/** The second line of a case with values (the station's duty and claim, or its state). */
		station: string | null;
		/** Its ring number on the chart, when drawn. */
		ring?: number | null;
	}[];
	prefs: UnitPreferences;
	/** The stored project: component order. */
	project: Project;
}

export interface CombinationRow {
	id: string;
	/** The row header: the member's name, with its id where another member has it (memberLabels). */
	name: string;
	style: GroupSlot;
	cells: Record<string, string>;
	/** The member has a flag of severity `invalid` in this case: its values are marked. */
	invalid: boolean;
	flags: readonly Flag[];
}

export interface CombinationGroup {
	key: string;
	/** "Pump PA off (out of date) · ring 1". */
	heading: string;
	/**
	 * The lineup line (D24 §7.10), read from the case's solve: "2 of 4 carrying flow: Pump P1 and
	 * Pump P2; off: Pump P3 and Pump P4"; null without values.
	 */
	lineup: string | null;
	/** The second line: the station's duty, a state's words, or Compare's words without values. */
	detail: string | null;
	stale: boolean;
	/** The case has values (a converged solve, by Compare's rule). */
	values: boolean;
	rows: CombinationRow[];
}

export interface CombinationsTable {
	columns: Column[];
	groups: CombinationGroup[];
}

/** The columns whose values Running combinations marks as physically invalid. */
export const INVALID_MARKED = ['flow', 'head', 'shaftPower', 'npshMargin'] as const;

/** A case's response has values (a converged solve). */
const hasValues = (response: SolveResponse | null): response is SolveResponse =>
	!!response && response.success && response.solvedState.converged;

/**
 * The lineup line of a case with values (D24 §7.10): `{r} of {n} carrying flow: {A and B}; on,
 * carrying no flow: {C}; off: {D}; no result: {E}`, each part only when it applies and the list
 * after the count only when r > 0. A member carries flow when on with |operatingFlow| above
 * DUTY_CHECK_FLOOR (carriesFlow), whatever its state word: one on behind a closed valve reads
 * `running` at zero flow and is "on, carrying no flow". It never says "running", which in a
 * lineup's name means switched on.
 */
function lineupLine(
	members: readonly { id: string }[],
	response: SolveResponse,
	name: (id: string) => string
): string {
	const results = response.solvedState.pumpResults;
	const carrying: string[] = [];
	const idle: string[] = [];
	const off: string[] = [];
	const none: string[] = [];
	for (const { id } of members) {
		const r = results[id];
		(!r ? none : r.status === 'off' ? off : carriesFlow(r) ? carrying : idle).push(name(id));
	}
	const count = `${carrying.length} of ${members.length} carrying flow`;
	return [
		carrying.length ? `${count}: ${andList(carrying)}` : count,
		...(idle.length ? [`on, carrying no flow: ${andList(idle)}`] : []),
		...(off.length ? [`off: ${andList(off)}`] : []),
		...(none.length ? [`no result: ${andList(none)}`] : [])
	].join('; ');
}

/** "Not met: Operating region, Motor power · Met: NPSH margin", the API's results copied. */
function checksWords(response: SolveResponse, pumpId: string): string {
	const results = response.solvedState.designChecks.filter((c) => c.componentId === pumpId);
	const words = OUTCOME_ORDER.flatMap((outcome) => {
		const titles = results.filter((r) => r.outcome === outcome).map((r) => CHECK_TITLES[r.check]);
		return titles.length ? [`${OUTCOME_TITLES[outcome]}: ${titles.join(', ')}`] : [];
	});
	return words.length ? words.join(' · ') : '—';
}

/**
 * Every case's members, one row group per case (the shown first), one row per member in the
 * stored project's component order, its row header the member's name with its id where another
 * member has that name (memberLabels: the slot's symbol is hidden from screen readers, so two
 * members of one name would otherwise give two rows the same header); the group table's cell
 * rules on that case's own solve.
 */
export function runningCombinations(input: CombinationsInput): CombinationsTable {
	const f = new Formatter(input.prefs);
	const order = new Map(input.project.components.map((c, i) => [c.id, i]));
	const members = [...input.members].sort(
		(a, b) => (order.get(a.id) ?? Infinity) - (order.get(b.id) ?? Infinity)
	);
	const labels = memberLabels(members);
	const nameOf = (m: { id: string; name: string }) => labels.get(m.id)?.name ?? m.name;
	const valued = input.cases.filter((c) => hasValues(c.response));
	// As the group table shows it: a member that is on, under a speed control or at a speed other
	// than 1, in some case with values (an off pump's speed is never shown).
	const speed = valued.some((c) =>
		members.some((m) => {
			const r = c.response!.solvedState.pumpResults[m.id];
			return !!r && r.status !== 'off' && (!!r.control || r.speed !== 1);
		})
	);
	const checks = valued.some((c) =>
		c.response!.solvedState.designChecks.some((r) => members.some((m) => m.id === r.componentId))
	);
	const columns: Column[] = [
		{ key: 'state', label: 'State' },
		...(speed ? [f.column('speed', 'Speed', 'fraction')] : []),
		f.column('flow', 'Flow', 'flow'),
		f.column('head', 'Head', 'head'),
		f.column('shaftPower', 'Shaft power', 'power'),
		f.column('npshMargin', 'NPSH margin', 'head'),
		{ key: 'inCurve', label: 'Inside curve data' },
		...(checks ? [{ key: 'checks', label: 'Design checks' }] : [])
	];
	const groups = input.cases.map((c): CombinationGroup => {
		const values = hasValues(c.response);
		const stale = !!c.response && c.stale;
		const heading = `${c.name}${c.shown ? ' (shown)' : ''}${stale ? ' (out of date)' : ''}${c.ring ? ` · ring ${c.ring}` : ''}`;
		if (!values) {
			return {
				key: c.key,
				heading,
				lineup: null,
				detail:
					c.status === 'not_converged'
						? 'Did not converge: no values shown'
						: CASE_STATUS_LABELS[c.status],
				stale,
				values: false,
				rows: []
			};
		}
		const response = c.response!;
		const rows = members.map((m): CombinationRow => {
			const style = slotStyle(m.slot);
			const r = response.solvedState.pumpResults[m.id];
			if (!r) {
				const cells: Record<string, string> = Object.fromEntries(
					columns.map((col) => [col.key, '—'])
				);
				cells.state = 'No result (closed off)';
				return { id: m.id, name: nameOf(m), style, cells, invalid: false, flags: [] };
			}
			const flags = flagsForElement(response.solvedState.flags, { kind: 'component', id: m.id });
			const cells: Record<string, string> = {
				state: pumpStatusLabel(r, flags),
				...(speed ? { speed: r.status === 'off' ? '—' : f.num(r.speed, 'fraction') } : {}),
				flow: f.num(r.operatingFlow, 'flow'),
				head: f.num(r.operatingHead, 'head'),
				shaftPower: f.num(r.shaftPower, 'power'),
				npshMargin: f.num(r.npshMargin, 'head'),
				inCurve: r.status === 'running' ? (r.inCurveRange ? 'Yes' : 'No: beyond its data') : '—',
				...(checks ? { checks: checksWords(response, m.id) } : {})
			};
			return {
				id: m.id,
				name: nameOf(m),
				style,
				cells,
				invalid: flags.some((flag) => flag.severity === 'invalid'),
				flags
			};
		});
		return {
			key: c.key,
			heading,
			lineup: lineupLine(members, response, (id) => labels.get(id)?.name ?? id),
			detail: c.station,
			stale,
			values: true,
			rows
		};
	});
	return { columns, groups };
}

export interface ExtremeLine {
	/** The member's id and the measure: "PA:operatingFlow" (a name need not be unique). */
	key: string;
	/** "Pump PA, largest flow" ("Booster pump (PA), largest flow" where two share a name). */
	term: string;
	/** "40.75 L/s in Pump PB off; beyond its curve data (over 5 of 5 cases)". */
	value: string;
	/** The case it is in has a flag of severity `invalid` for that pump. */
	invalid: boolean;
}

/**
 * Per member, its largest flow, its largest shaft power and its smallest NPSH margin over the
 * cases with current values (at least two; none otherwise), each with its case (the first in
 * table order; "and k other cases" on equal doubles), "beyond its curve data" and "physically
 * invalid" where they apply there, and how many cases give a value. Out-of-date cases are not
 * counted and are named (`notCounted`).
 */
export function combinationExtremes(input: CombinationsInput): {
	lines: ExtremeLine[];
	notCounted: string[];
} {
	const f = new Formatter(input.prefs);
	const current = input.cases.filter((c) => hasValues(c.response) && !c.stale);
	const notCounted = input.cases.filter((c) => hasValues(c.response) && c.stale).map((c) => c.name);
	if (current.length < 2) return { lines: [], notCounted: [] };
	const order = new Map(input.project.components.map((c, i) => [c.id, i]));
	const members = [...input.members].sort(
		(a, b) => (order.get(a.id) ?? Infinity) - (order.get(b.id) ?? Infinity)
	);
	const total = current.length;
	const labels = memberLabels(members);
	const measures = [
		{ what: 'largest flow', key: 'operatingFlow', category: 'flow', largest: true },
		{ what: 'largest shaft power', key: 'shaftPower', category: 'power', largest: true },
		{ what: 'smallest NPSH margin', key: 'npshMargin', category: 'head', largest: false }
	] as const;
	const lines: ExtremeLine[] = [];
	for (const m of members) {
		for (const measure of measures) {
			const key = `${m.id}:${measure.key}`;
			const term = `${labels.get(m.id)?.name ?? m.name}, ${measure.what}`;
			const found = current.flatMap((c) => {
				const r = c.response!.solvedState.pumpResults[m.id];
				const v = r ? r[measure.key] : null;
				return typeof v === 'number' && Number.isFinite(v) ? [{ c, r: r!, v }] : [];
			});
			if (!found.length) {
				lines.push({ key, term, value: 'no case gives one', invalid: false });
				continue;
			}
			const best = found.reduce(
				(a, b) => (measure.largest ? Math.max(a, b.v) : Math.min(a, b.v)),
				found[0]!.v
			);
			const at = found.filter((x) => x.v === best);
			const first = at[0]!;
			const others = at.length - 1;
			const where = others
				? `${first.c.name} and ${others} other ${others === 1 ? 'case' : 'cases'}`
				: first.c.name;
			const flags = flagsForElement(first.c.response!.solvedState.flags, {
				kind: 'component',
				id: m.id
			});
			const invalid = flags.some((flag) => flag.severity === 'invalid');
			const qualifiers = [
				...(first.r.status === 'running' && !first.r.inCurveRange ? ['beyond its curve data'] : []),
				...(invalid ? ['physically invalid'] : [])
			];
			const missing = total - found.length;
			lines.push({
				key,
				term,
				value: `${f.value(best, measure.category)} in ${where}${qualifiers.length ? `; ${qualifiers.join('; ')}` : ''} (over ${found.length} of ${total} cases${missing ? `; no value in ${missing}` : ''})`,
				invalid
			});
		}
	}
	return { lines, notCounted };
}
