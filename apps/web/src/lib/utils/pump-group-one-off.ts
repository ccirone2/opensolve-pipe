/**
 * One pump off, drawn together (CLAUDE.md D21 slice 4d, proposal pump-groups.md §8 and §16): the
 * Pumps together card's N−1 for a parallel station.
 *
 * - "Add cases with one pump off": one D15 scenario per member running in the base case, each the
 *   base with that pump's `status` off and nothing else (the proposal's single override, always
 *   relative to the base, so it is offered only while the base case is shown and current). A
 *   member whose case exists (a scenario whose only change is that) is skipped, a member on but
 *   held at zero flow gets none (with it off the base's state is the same), and the add is refused
 *   past the schema's scenario limit with the count.
 * - Other cases' station duties: each from that case's own group-curve answer (never computed
 *   here), drawn as a numbered ring only when its station is the one shown; a ring is called a
 *   point of the group system curve shown only when that case, as solved, is the same as this one
 *   outside the station (hydraulicFingerprint of each project without the station's interior, the
 *   design checks and the library entries no element outside refers to: D21, the curve depends on
 *   nothing inside), its flow is above zero, the curve has a rise at the computed flows on both
 *   sides of it, and the shown case's own system duty check agrees (D13).
 * - Running combinations: every case's members, with the group table's cell rules applied to that
 *   case's own solve (Compare's rule says which responses have values), and the extremes over the
 *   current cases (screen only, never in the image or the export: D17).
 *
 * Names need not be unique: two members of one name are told apart by their ids wherever words
 * alone name them (the cases made, the block's notes, Running combinations' row headers, the
 * extremes; memberLabels).
 *
 * Pure: every value is the API's; the store's fingerprint is passed in (no util imports the store).
 */
import type {
	Flag,
	Override,
	Project,
	PumpGroupCurveResponse,
	PumpGroupStation,
	Scenario,
	SolveResponse,
	UnitPreferences
} from '../api/types';
import type { CaseStatus, GroupCurveState, GroupSystemCurveState } from '../state/project.svelte';
import { CHECK_TITLES, OUTCOME_ORDER, OUTCOME_TITLES } from './design-checks';
import type { Calculating } from './goal-seek';
import { componentById } from './graph';
import { canonicalJson } from './json';
import { CASE_STATUS_LABELS } from './labels';
import { andList, dutyFlow, slotStyle, stationPortWords, type GroupSlot } from './pump-group-chart';
import { MAX_GROUP_PUMPS, pressureControlOnly, refusalWords, wordsText } from './pump-groups';
import { Formatter, flagsForElement, pumpStatusLabel, type Column } from './results';
import {
	findScenario,
	makeOverride,
	MAX_SCENARIOS,
	newScenarioId,
	overridesOf,
	sameValue,
	SCENARIO_NAME_LIMIT,
	scenariosOf,
	withScenarios,
	type CaseId
} from './scenarios';

export { DUTY_CLAIM_RULE } from './pump-group-chart';

/** Other cases on the group chart at once: every case with one pump off of a full group. */
export const MAX_GROUP_CASES = MAX_GROUP_PUMPS;

// ---------------------------------------------------------------------------------------------
// The cases with one pump off
// ---------------------------------------------------------------------------------------------

/** The one change of a case with one pump off: that pump's status off. */
export function offOverride(pumpId: string): Override {
	return makeOverride({ kind: 'component', componentId: pumpId }, 'status', 'off');
}

/** `scenario` is the case with `pumpId` off: its only change is that pump's status off. */
export function isOnePumpOff(scenario: Scenario, pumpId: string): boolean {
	const overrides = overridesOf(scenario);
	return overrides.length === 1 && sameValue(overrides[0], offOverride(pumpId));
}

/**
 * "Pump PA off", or with the pump's id when another member has its name ("Booster pump (PA)
 * off"), the name cut to the scenario name limit as copyName cuts (never the id).
 */
export function offName(pumpName: string, id?: string): string {
	const suffix = id === undefined ? ' off' : ` (${id}) off`;
	return pumpName.length + suffix.length <= SCENARIO_NAME_LIMIT
		? `${pumpName}${suffix}`
		: `${pumpName.slice(0, SCENARIO_NAME_LIMIT - suffix.length)}${suffix}`;
}

/**
 * Each member's name in words, by id: its name, with its id after it where another member has the
 * same name ("Booster pump (PA)"), since names need not be unique (a duty and a standby unit often
 * share one).
 */
export function memberLabels(
	members: readonly { id: string; name: string }[]
): Map<string, { name: string; shared: boolean }> {
	const count = new Map<string, number>();
	for (const m of members) count.set(m.name, (count.get(m.name) ?? 0) + 1);
	return new Map(
		members.map((m) => {
			const shared = (count.get(m.name) ?? 0) > 1;
			return [m.id, { name: shared ? `${m.name} (${m.id})` : m.name, shared }];
		})
	);
}

export interface OnePumpOffInput {
	/** The stored project (its scenarios, names and component order). */
	project: Project;
	/** The case shown (ws.store.activeCase). */
	shownCase: CaseId;
	/** The station the card shows (stationResponse(...)?.station); null: no block. */
	station: PumpGroupStation | null;
	/** The card's members (groupMembers). */
	memberIds: readonly string[];
	/** The base case's response by Compare's rule, and whether it is out of date. */
	base: { response: SolveResponse; stale: boolean } | null;
}

export interface OnePumpOffPlan {
	/** Why the action is not offered (null: offered). */
	gate: string | null;
	/** What the action makes, when offered. */
	about: string | null;
	/** The cases to add: the pump, the id it will have (on the growing project) and its name. */
	add: { pumpId: string; id: string; name: string }[];
	/** The members whose case exists, with that scenario. */
	existing: { pumpId: string; scenarioId: string; scenarioName: string }[];
	/** Members on but held at zero flow in the base case: no case. */
	idle: string[];
	/** The idle and "has its case already" sentences, in member order (keyed by index). */
	notes: string[];
	/** Why the add is refused: nothing to add, or past the scenario limit (null: it can be made). */
	refusal: string | null;
	/** "Add cases with one pump off (2)"; no count when there is nothing to add. */
	label: string;
	/** The block's Solve all is drawn (offered, or gates 3–5: the base case shown). */
	showSolveAll: boolean;
}

const LABEL = 'Add cases with one pump off';

/**
 * What "Add cases with one pump off" would make now, or why it is not offered (gates in order:
 * a parallel station; the base case shown; its results current; two members or more on; one
 * running). Without a station, nothing (the block is not drawn).
 */
export function onePumpOffPlan(input: OnePumpOffInput): OnePumpOffPlan {
	const { project, shownCase, station, base } = input;
	const plan = (gate: string | null, showSolveAll: boolean): OnePumpOffPlan => ({
		gate,
		about: null,
		add: [],
		existing: [],
		idle: [],
		notes: [],
		refusal: null,
		label: LABEL,
		showSolveAll
	});
	if (!station) return plan(null, false);
	if (station.arrangement === 'series') {
		return plan(
			'Cases with one pump off are offered for pumps in parallel only: in series a stopped pump blocks the line in this app (a stopped pump passing flow is not modelled), so the station would carry no flow.',
			false
		);
	}
	if (station.arrangement === 'mixed') {
		return plan(
			'Cases with one pump off are offered for pumps in parallel only; this station is mixed: neither all in parallel nor all in series.',
			false
		);
	}
	if (shownCase !== null) {
		const shown = findScenario(project, shownCase)?.name ?? shownCase;
		return plan(
			`Cases with one pump off are made from the base case: show the base case to add them. To study ${shown} with a pump off, duplicate it in Scenarios and set that pump off there.`,
			false
		);
	}
	if (!base || base.stale) {
		return plan(
			"The base case's results are out of date: solve it again, so the pumps that run are read from the project as it is now.",
			true
		);
	}
	const order = new Map(project.components.map((c, i) => [c.id, i]));
	const members = [...input.memberIds].sort(
		(a, b) => (order.get(a) ?? Infinity) - (order.get(b) ?? Infinity)
	);
	const labels = memberLabels(
		members.map((id) => ({ id, name: componentById(project, id)?.name ?? id }))
	);
	const name = (id: string) => labels.get(id)?.name ?? id;
	const results = base.response.solvedState.pumpResults;
	const on = members.filter((id) => results[id] && results[id].status !== 'off');
	if (on.length < 2) {
		const off = members.filter((id) => results[id]?.status === 'off').map(name);
		return plan(
			`Needs two or more of these pumps switched on in the base case: ${andList(off)} ${off.length === 1 ? 'is' : 'are'} off.`,
			true
		);
	}
	const running = members.filter((id) => results[id]?.status === 'running');
	if (!running.length) {
		return plan(
			'No pump of the group runs in the base case, so switching one off changes nothing.',
			true
		);
	}
	const scenarios = scenariosOf(project);
	const notes: string[] = [];
	const existing: OnePumpOffPlan['existing'] = [];
	const idle: string[] = [];
	const wanted: { pumpId: string; name: string }[] = [];
	for (const id of members) {
		const status = results[id]?.status;
		if (status === 'no_flow') {
			idle.push(id);
			notes.push(
				`${name(id)} carries no flow in the base case, so with it off the base case's state is the same: no case is made for it.`
			);
		} else if (status === 'running') {
			const found = scenarios.find((s) => isOnePumpOff(s, id));
			if (found) {
				existing.push({ pumpId: id, scenarioId: found.id, scenarioName: found.name });
				notes.push(`${name(id)} has its case already: ${found.name}.`);
			} else {
				const plain = componentById(project, id)?.name ?? id;
				wanted.push({ pumpId: id, name: offName(plain, labels.get(id)?.shared ? id : undefined) });
			}
		}
	}
	const ids = newIds(project, wanted.length);
	const add = wanted.map((w, i) => ({ ...w, id: ids[i]! }));
	const total = scenarios.length + add.length;
	const refusal = !add.length
		? `Every case with one pump off already exists: ${andList(existing.map((e) => e.scenarioName))}.`
		: total > MAX_SCENARIOS
			? `Adding ${add.length} ${add.length === 1 ? 'case' : 'cases'} would make ${total} scenarios; a project holds at most ${MAX_SCENARIOS} scenarios.`
			: null;
	return {
		gate: null,
		about: `Makes one scenario per pump running in the base case (${andList(running.map(name))}): the base case with that one pump off and nothing else changed. Pumps off in the base case stay off.`,
		add,
		existing,
		idle,
		notes,
		refusal,
		label: add.length ? `${LABEL} (${add.length})` : LABEL,
		showSolveAll: true
	};
}

/** The ids `count` new scenarios take, each the first free one on the growing project. */
function newIds(project: Project, count: number): string[] {
	const ids: string[] = [];
	let next = project;
	for (let i = 0; i < count; i++) {
		const id = newScenarioId(next);
		ids.push(id);
		next = withScenarios(next, [...scenariosOf(next), { id, name: id, overrides: [] }]);
	}
	return ids;
}

/**
 * The project with one case per pump added, in order: `{id, name, overrides: [offOverride]}`,
 * each id the first free one on the growing project (S1, S2, …), `name` the scenario's name
 * (offName of the pump's), no description.
 */
export function withOnePumpOffCases(
	project: Project,
	pumps: readonly { pumpId: string; name: string }[]
): Project {
	let next = project;
	for (const pump of pumps) {
		const scenario: Scenario = {
			id: newScenarioId(next),
			name: pump.name,
			overrides: [offOverride(pump.pumpId)]
		};
		next = withScenarios(next, [...scenariosOf(next), scenario]);
	}
	return next;
}

/** The notice after the add. */
export function addedNotice(names: readonly string[]): string {
	return `Added ${names.length} ${names.length === 1 ? 'case' : 'cases'} with one pump off: ${andList(names)}. Solve all solves every case not yet solved; Undo removes them.`;
}

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
 * The keys in the order the chart takes them: every case with one pump off of a current member
 * first (a scenario whose only change is that member's status off), in case order, then every
 * other case, in case order.
 */
export function chartPriority(
	keys: readonly { key: string; caseId: CaseId }[],
	project: Project,
	memberIds: readonly string[]
): string[] {
	const oneOff = (caseId: CaseId) => {
		const scenario = findScenario(project, caseId);
		return !!scenario && memberIds.some((m) => isOnePumpOff(scenario, m));
	};
	return [
		...keys.filter((k) => oneOff(k.caseId)).map((k) => k.key),
		...keys.filter((k) => !oneOff(k.caseId)).map((k) => k.key)
	];
}

/**
 * The keys of the cases on the chart: chartPriority's order without the cases unticked under
 * "Cases on this chart", at most MAX_GROUP_CASES, so a case unticked lets the next one in.
 */
export function chartKeys(
	keys: readonly { key: string; caseId: CaseId }[],
	project: Project,
	memberIds: readonly string[],
	unticked: readonly string[]
): string[] {
	return chartPriority(keys, project, memberIds)
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
	/** The ring number (case order among the cases drawn); null when not drawn. */
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
}

export interface OtherCasesInput {
	/** The other cases with values (Compare's rule), in case order. */
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
	}[];
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

/** Each other case with values, in case order, in its state with its words and its ring. */
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
			retry: false
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
		return {
			...base,
			state: 'ready',
			words: DUTY_CLAIM_WORDS[claim],
			number: ++number,
			duty,
			claim,
			retry: false
		};
	});
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
		return { key: c.key, heading, detail: c.station, stale, values: true, rows };
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
