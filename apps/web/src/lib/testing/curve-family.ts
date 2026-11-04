/**
 * The curve family's test views (CLAUDE.md D24 slice L3, proposal pump-lineups.md §10.3): the
 * Pumps together card's inputs for one case of the shared fixture's `lineups` station shown, with
 * the other cases as PumpsView gives them (each case as solved, its rest and its inside compared
 * with the shown case's by the app's own functions, its members switched on read by pumpLineup,
 * in lineupChartPriority's order, ticked as chartKeys takes them). Every response is the fixture's
 * real API answer (apps/api/tests/fixtures/pump_groups_input.py). Not used by the app.
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
import { ratedCurveRange } from '../utils/pump-chart';
import {
	groupChartData,
	type GroupChartData,
	type GroupMemberInput
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
import { lineupChartPriority, pumpLineup } from '../utils/pump-lineups';
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
	const order = lineupChartPriority(keys, lineups.project, members);
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
