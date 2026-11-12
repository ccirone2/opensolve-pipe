/**
 * "(D13)" in plain words (pumps-results-layout.md §6.2 S8, W1 to W9; the owner's answer 4): no word
 * the Pumps view shows holds the decision's number, on the Pumps together card, on the pump chart
 * or in either image's footer. A guard over the words functions' outputs in the shared fixture's
 * states (real API answers, __fixtures__/pump-groups-input.json): every case alone, and every case
 * of the fixture's projects with scenarios shown in turn with the others as rings, with and
 * without their curve states, each also with the duty checks made to disagree and with no group
 * curve drawn (synthetic, named below), so that W1 to W9 are each among the words read, word for
 * word as §6.2's "After"; and over the word tables of the modules that make them. Running
 * combinations' station line is a case's duty and its `words` (PumpsView), read here as `words`.
 */
import { describe, expect, it } from 'vitest';
import type {
	Flag,
	Project,
	PumpGroupCurveResponse,
	PumpResult,
	SolveResponse,
	TopologyIssue
} from '$lib/api/types';
import { DISCLAIMER } from '$lib/components/links';
import { hydraulicFingerprint, type GroupCurveState } from '$lib/state/project.svelte';
import { fixtureCases, type Answer, type FixtureCase } from '$lib/testing/curve-family';
import { chartImageCaption, IMAGE_REASONS_IN, imageNoteLines } from './export/chart-image';
import * as lineupTable from './lineup-table';
import * as pumpChart from './pump-chart';
import {
	caseTagOf,
	caseTags,
	chartNotes,
	inCaseOrder,
	offCasesNote,
	otherCasesData,
	PANELS,
	pumpChartCases,
	pumpChartData,
	ratedCurveRange
} from './pump-chart';
import * as pumpChartConfig from './pump-chart-config';
import * as groupChart from './pump-group-chart';
import {
	DUTY_CLAIM_RULE,
	groupChartData,
	groupMethodsLines,
	groupNoteLines,
	groupNotes,
	groupSummary,
	OTHER_CURVES_FRAME,
	otherCurveRows,
	runningWords,
	type GroupMemberInput
} from './pump-group-chart';
import * as oneOff from './pump-group-one-off';
import {
	chartKeys,
	DUTY_CLAIM_WORDS,
	groupCurveDrawn,
	OTHER_CURVE_WORDS,
	otherGroupCases,
	sameInside,
	sharedRest,
	type OtherCasesInput
} from './pump-group-one-off';
import * as pumpGroups from './pump-groups';
import { refusalWords, wordsText } from './pump-groups';
import * as pumpLineups from './pump-lineups';
import { pumpLineup } from './pump-lineups';
import { applyScenario } from './scenarios';
import * as sectionNav from './section-nav';

/** The decision's number, however written: "(D13)", "(CLAUDE.md D13)", "; CLAUDE.md D13". */
const NUMBER = /D13/;

/** W1 to W9 of §6.2, each as its "After" column words it (W5's and W6's ends, W9 with k = 3). */
const W = {
	W1: 'Several steady states can exist; the point is the one the solve found.',
	W2: 'Several steady states can exist; the point is the one the solve found.',
	W3: "the curve is drawn through sampled points, each the state the system curve's starts find.",
	W4: 'and the station has one state at its rise. Where its case differs',
	W5: 'and the station has one state at its rise: the curve drawn here when',
	W6: 'and the station has one state at its rise; no group curve is drawn here.',
	W7: 'Not said: at zero station flow the rest can hold more than one state',
	W8: "Not said: this case's own duty is not on the curve (several steady states can exist; the duty is the one the solve found)",
	W9: 'it does not pass through the ring (several steady states can exist; the ring is the one the solve found)'
} as const;

/** Every word read, by where it is shown. */
interface Read {
	where: string;
	text: string;
}

/** Every string of a value: itself, an array's or a plain object's, at any depth. */
function strings(value: unknown, seen = new Set<unknown>()): string[] {
	if (typeof value === 'string') return [value];
	if (!value || typeof value !== 'object' || seen.has(value)) return [];
	seen.add(value);
	const proto = Object.getPrototypeOf(value);
	if (!Array.isArray(value) && proto !== Object.prototype && proto !== null) return [];
	return Object.values(value).flatMap((v) => strings(v, seen));
}

const prefsOf = (c: FixtureCase) => c.project.settings.units;
const body = (a: Answer) => a.body as PumpGroupCurveResponse;
const keysOf = (c: FixtureCase) => ['', ...Object.keys(c.scenarioCases ?? {})];
const answersOf = (c: FixtureCase, key: string) =>
	key === ''
		? { solve: c.solve, groupCurve: c.groupCurve, systemCurve: c.systemCurve }
		: c.scenarioCases![key]!;
const solvedOf = (c: FixtureCase, key: string): Project =>
	key === '' ? c.project : applyScenario(c.project, key).project;
const nameOf = (c: FixtureCase, key: string) =>
	key === '' ? 'Base case' : c.project.scenarios!.find((s) => s.id === key)!.name;

/** A group curve's answer as the card holds it: ready, or refused with its issues. */
function stateOf(a: Answer): GroupCurveState {
	if (a.status === 200) return { status: 'ready', response: body(a) };
	const refusal = a.body as { message: string; issues: TopologyIssue[] };
	return { status: 'refused', message: refusal.message, issues: refusal.issues };
}

/**
 * The card's members for a case shown: its solve's results, slots in member order; a member
 * without a result in that solve (`lineups-closed-leg`'s S1) has no point to word.
 */
function membersOf(c: FixtureCase, solve: SolveResponse, solved: Project): GroupMemberInput[] {
	return c.memberIds
		.map((id, slot) => ({ id, slot, result: solve.solvedState.pumpResults[id] }))
		.filter((m): m is typeof m & { result: PumpResult } => !!m.result)
		.map(({ id, slot, result }) => {
			const pump = c.project.components.find((x) => x.id === id)!;
			return {
				id,
				name: pump.name,
				result,
				ratedRange: ratedCurveRange(solved, id),
				curveId: pump.type === 'pump' ? pump.curveId : null,
				slot,
				flags: (solve.solvedState.flags as Flag[]).filter((f) => f.componentId === id)
			};
		});
}

/** Synthetic: both duty checks of a response disagree (W1, W2; and W8 for the rings it shows). */
function disagreeing(r: PumpGroupCurveResponse): PumpGroupCurveResponse {
	const copy = structuredClone(r);
	if (copy.dutyCheck && copy.duty) {
		Object.assign(copy.dutyCheck, {
			agrees: false,
			flow: copy.duty.flow * 1.1,
			message: 'made-up server words'
		});
	}
	if (copy.systemDutyCheck && copy.duty) {
		Object.assign(copy.systemDutyCheck, {
			agrees: false,
			head: copy.duty.head + 2,
			message: 'made-up server words'
		});
	}
	return copy;
}
/** Synthetic: no point of the group curve has a flow, so none is drawn (W6). */
function flowless(r: PumpGroupCurveResponse): PumpGroupCurveResponse {
	const copy = structuredClone(r);
	copy.points = copy.points.map((point) => ({ ...point, flow: null }));
	return copy;
}

type Edit = 'as answered' | 'checks disagree' | 'no group curve drawn';
const EDITS: readonly Edit[] = ['as answered', 'checks disagree', 'no group curve drawn'];

/**
 * The card's words for case `shown` of `c` with every other case of its scenarios on the chart,
 * as PumpsView gives them (number order with the project's case numbers, chartKeys' ticks by
 * lineupChartPriority; nit 5, slice 5b), `curveStates` with
 * each case's inside and members switched on (D24 §9.1) or without them (4d's rings), after the
 * edit: the notes, as the screen and the image's footer give them, the accessible name, the
 * rings' cells, each case's words and the server's words the card shows.
 */
function cardWords(c: FixtureCase, shown: string, edit: Edit, curveStates: boolean): Read[] {
	const answers = answersOf(c, shown);
	const solved = solvedOf(c, shown);
	const members = membersOf(c, answers.solve, solved);
	const prefs = prefsOf(c);
	let state = stateOf(answers.groupCurve);
	let system =
		answers.systemCurve && answers.systemCurve.status === 200 ? body(answers.systemCurve) : null;
	if (edit === 'checks disagree') {
		if (state.status === 'ready')
			state = { status: 'ready', response: disagreeing(state.response) };
		if (system) system = disagreeing(system);
	}
	if (edit === 'no group curve drawn' && state.status === 'ready') {
		state = { status: 'ready', response: flowless(state.response) };
	}
	const response = state.status === 'ready' ? state.response : null;
	const station = response ?? system;
	const keys = keysOf(c)
		.filter((k) => k !== shown)
		.map((key) => ({ key, caseId: key || null }));
	const tags = caseTags(c.project);
	const others =
		station && keys.length
			? otherGroupCases({
					valued: inCaseOrder(keys, tags).map(({ key }) => {
						const theirs = answersOf(c, key);
						let group = stateOf(theirs.groupCurve);
						// Synthetic: each other case's own duty check disagrees too (W9).
						if (edit === 'checks disagree' && group.status === 'ready') {
							group = { status: 'ready', response: disagreeing(group.response) };
						}
						const other = solvedOf(c, key);
						return {
							key,
							caseId: key || null,
							name: nameOf(c, key),
							stale: false,
							group,
							system: undefined,
							shared: sharedRest(solved, other, station.station, hydraulicFingerprint),
							solved: other,
							...(curveStates
								? {
										inside: sameInside(solved, other, station.station, hydraulicFingerprint),
										on: pumpLineup(undefined, other, c.memberIds).on.length
									}
								: {})
						} satisfies OtherCasesInput['valued'][number];
					}),
					tags,
					shownKeys: new Set(chartKeys(keys, c.project, c.memberIds, [])),
					othersOn: true,
					shownSettled: true,
					station: station.station,
					systemShown: system,
					memberIds: c.memberIds,
					project: c.project,
					boxes: c.memberIds,
					curveDrawn: groupCurveDrawn(state)
				})
			: [];
	const on = pumpLineup(undefined, solved, c.memberIds).on.length;
	const data = groupChartData(members, prefs, response, system, others, on);
	const notes = groupNotes({
		data,
		members,
		state,
		system: system ? { status: 'ready', response: system } : undefined,
		project: c.project,
		solved,
		prefs,
		others
	});
	const refusals =
		state.status === 'refused'
			? state.issues.map((issue) =>
					wordsText(refusalWords(issue, c.memberIds, c.project, { solved }))
				)
			: [];
	const lines = groupNoteLines(notes, refusals);
	const footer = chartImageCaption({
		pumpName: '',
		title: 'Pumps together',
		projectName: c.project.metadata.name,
		timestamp: answers.solve.solvedState.timestamp,
		methodVersion: answers.solve.solvedState.methodVersion ?? '',
		stale: false,
		notes: lines,
		disclaimer: DISCLAIMER,
		origin: 'https://example.test',
		utcOffsetMinutes: 0
	}).footer;
	const read = (where: string, texts: readonly (string | null | undefined)[]): Read[] =>
		texts.filter((t): t is string => !!t).map((text) => ({ where, text }));
	return [
		...read('the card: the duty check', notes.duty),
		...read('the card: the system duty check', notes.systemDuty),
		...read('the card: the other cases', notes.others),
		...read('the card: the notes', lines),
		...read('the group image: the footer', footer),
		...read('the card: the accessible name', [
			groupSummary(data, members, response, c.project, system)
		]),
		...read(
			"the card: Other cases' station duties",
			data.others.flatMap((ring) => ring.cases.flatMap((x) => [x.claim, x.curveCell]))
		),
		...read(
			"the card: Other cases' group curves",
			otherCurveRows(others, prefs, c.project).flatMap((g) => [
				g.header,
				...g.rows.map((row) => row.note)
			])
		),
		...read(
			"the card: Running combinations' station line",
			others.map((o) => o.words)
		),
		...read('the card: the refusals', [
			...refusals,
			...(state.status === 'refused' ? state.issues.map((issue) => issue.message) : [])
		]),
		...read("the card: the server's words", [
			response?.dutyCheck?.message,
			system?.systemDutyCheck?.message,
			...(response ? groupMethodsLines(response) : []),
			...(system ? groupMethodsLines(system) : [])
		])
	];
}

/**
 * The pump chart's words for each member of `c` with case `shown` shown: the figure's notes (the
 * screen's and the image's), the other cases' names and the off line, and the image's footer.
 */
function pumpChartWords(c: FixtureCase, shown: string, curves: boolean): Read[] {
	const answers = answersOf(c, shown);
	const solved = solvedOf(c, shown);
	const prefs = prefsOf(c);
	const read: Read[] = [];
	for (const id of c.memberIds) {
		const result = answers.solve.solvedState.pumpResults[id] as PumpResult | undefined;
		if (!result) continue;
		const range = ratedCurveRange(solved, id);
		const data = pumpChartData(result, prefs, range);
		// The other cases with a result for this pump, as PumpsView lists them.
		const inputs = keysOf(c)
			.filter((k) => k !== shown)
			.map((key) => ({
				key,
				name: nameOf(c, key),
				result: answersOf(c, key).solve.solvedState.pumpResults[id] as PumpResult | undefined,
				stale: false,
				system: null
			}))
			.filter((o): o is typeof o & { result: PumpResult } => !!o.result);
		const cases = pumpChartCases(inputs, [], curves);
		const tags = caseTags(c.project);
		const others = otherCasesData(cases.shown, prefs, range, result.speed, null, tags);
		const off = offCasesNote(
			cases.off.map((o) => ({ tag: caseTagOf(tags, o.key), label: o.name }))
		);
		const input = { data, result, system: undefined, shown: [...PANELS], speedShown: true };
		const screen = chartNotes(input);
		const image = chartNotes({ ...input, reasonsIn: IMAGE_REASONS_IN });
		const lines = imageNoteLines(image, others, off);
		const footer = chartImageCaption({
			pumpName: id,
			projectName: c.project.metadata.name,
			timestamp: answers.solve.solvedState.timestamp,
			methodVersion: answers.solve.solvedState.methodVersion ?? '',
			stale: false,
			notes: lines,
			disclaimer: DISCLAIMER,
			origin: 'https://example.test',
			utcOffsetMinutes: 0
		}).footer;
		read.push(
			...strings(screen).map((text) => ({ where: 'the pump chart: the notes', text })),
			...[off, ...others.flatMap((o) => [o.label, o.curveLabel, o.row.state])]
				.filter((t): t is string => !!t)
				.map((text) => ({ where: 'the pump chart: the other cases', text })),
			...footer.map((text) => ({ where: 'the pump image: the footer', text }))
		);
	}
	return read;
}

/** Every state's words: each case alone, and each case of a project with scenarios shown. */
function everyWord(): Read[] {
	const read: Read[] = [];
	for (const c of fixtureCases) {
		for (const shown of keysOf(c)) {
			for (const edit of EDITS) {
				read.push(...cardWords(c, shown, edit, true), ...cardWords(c, shown, edit, false));
			}
			read.push(...pumpChartWords(c, shown, false), ...pumpChartWords(c, shown, true));
		}
	}
	return read;
}

describe('"(D13)" in plain words (pumps-results-layout.md §6.2 S8, the owner\'s answer 4)', () => {
	it('words W1 to W9 as §6.2’s After column, in the word tables', () => {
		expect(DUTY_CLAIM_WORDS.zero_flow).toBe(W.W7);
		expect(DUTY_CLAIM_WORDS.shown_duty).toBe(W.W8);
		expect(OTHER_CURVE_WORDS.not_through(runningWords(3, false))).toBe(
			`drawn (3 running): ${W.W9}`
		);
		expect(DUTY_CLAIM_RULE.endsWith(`; ${W.W3}`)).toBe(true);
		expect(OTHER_CURVES_FRAME).toContain(W.W4);
	});

	it('holds no "D13" in any word table of the modules that make the Pumps view’s words', () => {
		const modules = {
			pumpChart,
			pumpChartConfig,
			groupChart,
			oneOff,
			pumpGroups,
			pumpLineups,
			lineupTable,
			sectionNav
		};
		const tables = Object.entries(modules).flatMap(([module, exports]) =>
			Object.entries(exports).flatMap(([name, value]) =>
				strings(value).map((text) => ({ where: `${module}.${name}`, text }))
			)
		);
		// The tables W3, W4, W7 and W8 are in are read.
		for (const name of ['DUTY_CLAIM_RULE', 'OTHER_CURVES_FRAME', 'DUTY_CLAIM_WORDS']) {
			expect(tables.some((t) => t.where.endsWith(`.${name}`))).toBe(true);
		}
		// Each curve state's words, a stale case's too (W9 among them).
		const curveWords = Object.values(OTHER_CURVE_WORDS).flatMap((words) => [
			words(runningWords(3, false)),
			words(runningWords(3, true))
		]);
		for (const { where, text } of [
			...tables,
			...curveWords.map((text) => ({ where: 'OTHER_CURVE_WORDS', text }))
		]) {
			expect(text, where).not.toMatch(NUMBER);
		}
	});

	it('holds no "D13" in any word of the card, the pump chart or either image, in every state', () => {
		const read = everyWord();
		for (const { where, text } of read) expect(text, where).not.toMatch(NUMBER);
		// The guard is known to read W1 to W9, each where §6.2 says it is shown, and in the image.
		const where = (w: string) => [
			...new Set(read.filter((r) => r.text.includes(w)).map((r) => r.where))
		];
		expect(where(W.W1)).toEqual(
			expect.arrayContaining([
				'the card: the duty check',
				'the card: the system duty check',
				'the group image: the footer'
			])
		);
		for (const w of [W.W3, W.W4, W.W5, W.W6]) {
			expect(where(w), w).toEqual(
				expect.arrayContaining(['the card: the other cases', 'the group image: the footer'])
			);
		}
		for (const w of [W.W7, W.W8]) {
			expect(where(w), w).toEqual(
				expect.arrayContaining([
					'the card: the other cases',
					'the card: the accessible name',
					"the card: Other cases' station duties",
					"the card: Running combinations' station line",
					'the group image: the footer'
				])
			);
		}
		expect(where(W.W9)).toEqual(
			expect.arrayContaining([
				'the card: the other cases',
				'the card: the accessible name',
				'the group image: the footer'
			])
		);
		// "Its group curve", capitalised.
		expect(
			read.some(
				(r) =>
					r.where === "the card: Other cases' station duties" &&
					/^Drawn \(\d running\): it does not pass through the ring \(several steady states can exist; the ring is the one the solve found\)$/.test(
						r.text
					)
			)
		).toBe(true);
		// The pump chart and its image are read too, the off line among them.
		expect(read.filter((r) => r.where === 'the pump image: the footer').length).toBeGreaterThan(0);
		expect(
			read.some(
				(r) =>
					r.where === 'the pump image: the footer' &&
					r.text.startsWith('Off in this case (no operating point): ')
			)
		).toBe(true);
	});
});
