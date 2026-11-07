/**
 * Pump lineups, slices L1a and L1b (CLAUDE.md D24, proposal pump-lineups.md §4, §7 and §10.1 "L1a,
 * unit" and "L1b, unit"): the reader (pumpLineup), the frame (lineupGroups, frameKey), the same
 * case (effectiveChanges, sameCase), the names (lineupName), the names that follow
 * (followLineupNames, renameNotice), the Add cases block's plan (lineupPlan, withLineupCases, the
 * stop order and the block's words, with 4d's plan tests moved under Each pump off) and the
 * chart's order (lineupChartPriority). Every string is checked word for word. The projects are
 * made-up test inputs (only the components' kinds, ports, statuses, names and connections matter
 * here), the examples', and the shared fixture's (__fixtures__/pump-groups-input.json, the API's
 * own projects and answers); a base solve made up for a made-up project is named synthetic.
 */
import { describe, expect, it, vi } from 'vitest';
import type {
	Component,
	Override,
	Project,
	PumpGroupCurveResponse,
	PumpGroupStation,
	PumpResult,
	Scenario,
	SolveResponse
} from '$lib/api/types';
import { projectWith } from '$lib/testing/helpers';
import {
	ladder,
	pipe,
	prvStation,
	pump,
	pumpIds,
	series,
	station,
	stations,
	tank,
	twoByTwo,
	type StationSpec
} from '$lib/testing/lineups';
import fixture from './__fixtures__/pump-groups-input.json';
import { condenserWaterExample, pumpTransferExample } from './examples';
import { chartKeys, offName } from './pump-group-one-off';
import { suggestGroups } from './pump-groups';
import {
	ADD_CASES_WORDS,
	addedNotice,
	carriesFlow,
	defaultStopOrder,
	effectiveChanges,
	effectiveStopOrder,
	followLineupNames,
	frameKey,
	LINEUP_BLOCK_WORDS,
	LINEUP_NAME_BUDGET,
	LINEUP_PRESET_LABELS,
	LINEUP_UNDO_LABELS,
	lineupChartPriority,
	lineupGroups,
	lineupName,
	lineupNotice,
	lineupPlan,
	movedStopOrder,
	offOverride,
	pumpLineup,
	renameNotice,
	sameCase,
	solvedCaseWords,
	STOP_ORDER_WORDS,
	stopOrderSummary,
	withLineupCases,
	type LineupGroup,
	type LineupPlan,
	type LineupPlanInput
} from './pump-lineups';
import {
	copyName,
	MAX_SCENARIOS,
	SCENARIO_NAME_LIMIT,
	scenariosOf,
	withScenarios
} from './scenarios';

// The finder, counted (§10.1: memoised): the real one, wrapped.
vi.mock('./pump-groups', async (importOriginal) => {
	const actual = await importOriginal<typeof import('./pump-groups')>();
	return { ...actual, suggestGroups: vi.fn(actual.suggestGroups) };
});

interface FixtureCase {
	name: string;
	project: Project;
}
const fixtureProject = (name: string) =>
	structuredClone(
		(fixture.cases as unknown as FixtureCase[]).find((c) => c.name === name)!.project
	);

const status = (componentId: string, value: 'on' | 'off'): Override => ({
	kind: 'component',
	componentId,
	field: 'status',
	value
});
const level = (componentId: string, value: number): Override => ({
	kind: 'component',
	componentId,
	field: 'liquidLevel',
	value
});
const off = (...ids: string[]) => ids.map((id) => status(id, 'off'));
const scenario = (overrides: Override[], name = 'Case', id = 'S1'): Scenario => ({
	id,
	name,
	overrides
});
/** The project with these scenarios. */
const withCases = (project: Project, ...cases: Scenario[]) => withScenarios(project, cases);
/** lineupName of a scenario of these changes on `project`. */
const nameOf = (project: Project, overrides: Override[]) =>
	lineupName(project, scenario(overrides));

/** Every order of a list. */
function permutations<T>(items: readonly T[]): T[][] {
	if (items.length <= 1) return [[...items]];
	return items.flatMap((item, i) =>
		permutations([...items.slice(0, i), ...items.slice(i + 1)]).map((rest) => [item, ...rest])
	);
}

/** The project with a component changed (a base edit). */
function edited(project: Project, id: string, change: (c: Component) => Component): Project {
	return {
		...project,
		components: project.components.map((c) => (c.id === id ? change(c) : c))
	};
}
const renamedPump = (project: Project, id: string, name: string) =>
	edited(project, id, (c) => ({ ...c, name }));
const baseStatus = (project: Project, id: string, value: 'on' | 'off') =>
	edited(project, id, (c) => ({ ...c, status: value }) as Component);
/** The project with a scenario's changes replaced (a press in that case). */
function pressed(project: Project, id: string, overrides: Override[]): Project {
	return withScenarios(
		project,
		scenariosOf(project).map((s) => (s.id === id ? { ...s, overrides } : s))
	);
}
const namesOf = (project: Project) => scenariosOf(project).map((s) => s.name);

// ---------------------------------------------------------------------------------------------
// §4.1 pumpLineup
// ---------------------------------------------------------------------------------------------

describe('pumpLineup', () => {
	const p = station(4, { off: ['P4'] });
	const members = ['P1', 'P2', 'P3', 'P4'];

	it('gives equal lineups for every order of a case’s changes', () => {
		const changes = [status('P1', 'on'), status('P2', 'off'), status('P3', 'off'), level('A1', 5)];
		const lineups = permutations(changes).map((o) => pumpLineup(scenario(o), p, members));
		expect(lineups).toHaveLength(24);
		for (const l of lineups) {
			expect({ ...l, other: l.other.length }).toEqual({
				...lineups[0]!,
				other: lineups[0]!.other.length
			});
		}
		expect(lineups[0]).toMatchObject({
			members,
			off: ['P2', 'P3', 'P4'],
			on: ['P1'],
			setOff: ['P2', 'P3'],
			setOn: ['P1'],
			statusOnly: false
		});
	});

	it('collects the other changes: another pump’s status, any other value, a change that no longer applies', () => {
		const p2 = stations({ ids: ['P1', 'P2'] }, { ids: ['Q1', 'Q2'] });
		const gone = status('P9', 'off');
		const l = pumpLineup(
			scenario([status('P1', 'off'), status('Q1', 'off'), level('A1', 5), gone]),
			p2,
			['P1', 'P2']
		);
		expect(l.other).toEqual([status('Q1', 'off'), level('A1', 5), gone]);
		expect(l.statusOnly).toBe(false);
	});

	it('drops a member that is not a pump of the project (deleted)', () => {
		const l = pumpLineup(scenario(off('P2', 'P9')), station(2), ['P9', 'P2', 'P1']);
		expect(l.members).toEqual(['P1', 'P2']);
		expect(l.off).toEqual(['P2']);
		expect(l.other).toEqual([status('P9', 'off')]);
	});

	it('reads the base’s statuses: the base case, and members a scenario leaves alone', () => {
		expect(pumpLineup(undefined, p, members)).toMatchObject({
			off: ['P4'],
			on: ['P1', 'P2', 'P3'],
			setOff: [],
			setOn: [],
			statusOnly: false
		});
		expect(pumpLineup(scenario(off('P1')), p, members).off).toEqual(['P1', 'P4']);
	});

	it('is status-only when every change is a member’s status, and there is one', () => {
		expect(pumpLineup(scenario(off('P1')), p, members).statusOnly).toBe(true);
		expect(pumpLineup(scenario([status('P4', 'off')]), p, members).statusOnly).toBe(true);
		expect(pumpLineup(scenario([]), p, members).statusOnly).toBe(false);
		expect(pumpLineup(scenario([...off('P1'), level('A1', 5)]), p, members).statusOnly).toBe(false);
		expect(pumpLineup(scenario(off('P1')), p, ['P2', 'P3']).statusOnly).toBe(false);
	});
});

// ---------------------------------------------------------------------------------------------
// §4.2 lineupGroups, frameKey
// ---------------------------------------------------------------------------------------------

const frame = (project: Project) =>
	lineupGroups(project).map((g) => ({ kind: g.kind, pumpIds: [...g.pumpIds] }));

describe('lineupGroups', () => {
	it('the condenser example: one parallel group of 6', () => {
		expect(frame(condenserWaterExample())).toEqual([
			{ kind: 'parallel', pumpIds: ['P1', 'P2', 'P3', 'P4', 'P5', 'P6'] }
		]);
	});

	it('the ladder: [P1, P2, P3], not the inner pair', () => {
		expect(frame(fixtureProject('ladder'))).toEqual([
			{ kind: 'parallel', pumpIds: ['P1', 'P2', 'P3'] }
		]);
	});

	it('a 2 × 2 station: one mixed group of 4', () => {
		expect(frame(twoByTwo())).toEqual([{ kind: 'mixed', pumpIds: ['A1', 'A2', 'B1', 'B2'] }]);
	});

	it('two pumps on one chain: a series group', () => {
		expect(frame(series())).toEqual([{ kind: 'series', pumpIds: ['PA', 'PB'] }]);
		expect(frame(fixtureProject('series'))).toEqual([{ kind: 'series', pumpIds: ['PA', 'PB'] }]);
	});

	it('the pump-transfer example: Other pumps only', () => {
		expect(frame(pumpTransferExample())).toEqual([{ kind: 'other', pumpIds: ['P1'] }]);
	});

	it('a station of 7 pumps falls under Other pumps', () => {
		expect(frame(station(7))).toEqual([{ kind: 'other', pumpIds: pumpIds(7) }]);
	});

	it('a tee-ladder station of 7 or 8 pumps falls under Other pumps whole, not as an inner 6', () => {
		// Each inner ladder is a station of its own, which the finder suggests up to 6 pumps.
		expect(frame(ladder(6))).toEqual([{ kind: 'parallel', pumpIds: pumpIds(6) }]);
		expect(frame(ladder(7))).toEqual([{ kind: 'other', pumpIds: pumpIds(7) }]);
		expect(frame(ladder(8))).toEqual([{ kind: 'other', pumpIds: pumpIds(8) }]);
	});

	it('a PRV inside a station set active moves its pumps to Other, and frameKey changes', () => {
		const open = lineupGroups(prvStation('failed_open'));
		const active = lineupGroups(prvStation('active'));
		expect(open).toEqual([{ kind: 'parallel', pumpIds: ['PA', 'PB'] }]);
		expect(active).toEqual([{ kind: 'other', pumpIds: ['PA', 'PB'] }]);
		expect(frameKey(open)).not.toBe(frameKey(active));
		expect(frameKey(open)).toBe(frameKey(lineupGroups(prvStation('failed_open'))));
	});

	it('orders groups by their first pump, pumps in component order, Other last', () => {
		// Q's station first in the components, a lone pump L1 between the stations.
		const p = stations({ ids: ['Q1', 'Q2'] }, { ids: ['P1', 'P2', 'P3'] });
		const lone = projectWith(
			[
				...p.components.slice(0, 4),
				pump('L1'),
				tank('X1', 1),
				tank('X2', 1),
				...p.components.slice(4)
			],
			[
				...p.connections,
				pipe('LX1', 'X1:port_1', 'L1:suction'),
				pipe('LX2', 'L1:discharge', 'X2:port_1')
			],
			p.pumpLibrary
		);
		expect(frame(lone)).toEqual([
			{ kind: 'parallel', pumpIds: ['Q1', 'Q2'] },
			{ kind: 'parallel', pumpIds: ['P1', 'P2', 'P3'] },
			{ kind: 'other', pumpIds: ['L1'] }
		]);
	});

	it('is memoised on what the finder reads: connections alone find the frame again, a rename does not', () => {
		// A project not seen before (its own elevation).
		const before = withCases(
			edited(station(3), 'A1', (c) => ({ ...c, elevation: 31.4159 })),
			scenario(off('P3'), '2 of 3 running (Pump P3 off)')
		);
		// P3's discharge pipe removed: P3 leaves the station, and only the connections changed.
		const cut = { ...before, connections: before.connections.filter((c) => c.id !== 'DP3') };
		expect(frameKey(lineupGroups(before))).toBe('parallel:P1,P2,P3');
		expect(frameKey(lineupGroups(cut))).toBe('parallel:P1,P2;other:P3');
		expect(namesOf(followLineupNames(before, cut).project)).toEqual(['Pump P3 off']);
		const finder = vi.mocked(suggestGroups);
		finder.mockClear();
		const renamed = renamedPump(before, 'P3', 'Spare');
		expect(namesOf(followLineupNames(before, renamed).project)).toEqual([
			'2 of 3 running (Spare off)'
		]);
		expect(finder).not.toHaveBeenCalled();
	});

	it('is memoised: the finder runs once across a press', () => {
		// A project not seen before (its own elevation), so nothing is remembered yet.
		const before = withCases(
			edited(station(3), 'A1', (c) => ({ ...c, elevation: 12.345 })),
			scenario([], 'Scenario 1')
		);
		const after = pressed(before, 'S1', off('P3'));
		const finder = vi.mocked(suggestGroups);
		finder.mockClear();
		const { renamed } = followLineupNames(before, after);
		expect(renamed).toEqual([{ from: 'Scenario 1', to: '2 of 3 running (Pump P3 off)' }]);
		lineupName(after, scenario(off('P2')));
		lineupGroups(before);
		expect(finder).toHaveBeenCalledTimes(1);
	});
});

// ---------------------------------------------------------------------------------------------
// §4.3 sameCase
// ---------------------------------------------------------------------------------------------

describe('sameCase', () => {
	const p = station(4);

	it('is the same case in any order', () => {
		expect(
			sameCase(
				p,
				scenario([...off('P3', 'P4'), level('A1', 5)]),
				scenario([level('A1', 5), ...off('P4', 'P3')])
			)
		).toBe(true);
	});

	it('ignores a change equal to the base value', () => {
		expect(sameCase(p, scenario([status('P1', 'on'), ...off('P4')]), scenario(off('P4')))).toBe(
			true
		);
		expect(sameCase(p, scenario([level('A1', 2)]), undefined)).toBe(true);
		expect(effectiveChanges(p, scenario([status('P1', 'on'), ...off('P4')])).size).toBe(1);
	});

	it('ignores a change that no longer applies', () => {
		expect(sameCase(p, scenario([...off('P4'), status('P9', 'off')]), scenario(off('P4')))).toBe(
			true
		);
		expect(
			sameCase(
				p,
				scenario([
					...off('P4'),
					{ kind: 'component', componentId: 'A1', field: 'status', value: 'off' }
				]),
				scenario(off('P4'))
			)
		).toBe(true);
	});

	it('never matches a case with another change', () => {
		expect(
			sameCase(p, scenario([...off('P3', 'P4'), level('A1', 5)]), scenario(off('P3', 'P4')))
		).toBe(false);
		expect(sameCase(p, scenario(off('P4')), scenario(off('P3')))).toBe(false);
		expect(sameCase(p, scenario(off('P4')), undefined)).toBe(false);
		// The other way round: the case with fewer changes first.
		expect(sameCase(p, undefined, scenario(off('P4')))).toBe(false);
		expect(sameCase(p, scenario(off('P4')), scenario(off('P3', 'P4')))).toBe(false);
	});
});

// ---------------------------------------------------------------------------------------------
// §4.4 lineupName
// ---------------------------------------------------------------------------------------------

describe('lineupName', () => {
	it('names N = 2 to 6 pumps of default names, the last ones off (proto-card/output.txt)', () => {
		const names: string[] = [];
		for (let n = 2; n <= 6; n++) {
			const ids = pumpIds(n);
			for (let k = n - 1; k >= 1; k--) names.push(nameOf(station(n), off(...ids.slice(k)))!);
		}
		expect(names).toEqual([
			'1 of 2 running (Pump P2 off)',
			'2 of 3 running (Pump P3 off)',
			'1 of 3 running (Pump P2, Pump P3 off)',
			'3 of 4 running (Pump P4 off)',
			'2 of 4 running (Pump P3, Pump P4 off)',
			'1 of 4 running (Pump P2, Pump P3, Pump P4 off)',
			'4 of 5 running (Pump P5 off)',
			'3 of 5 running (Pump P4, Pump P5 off)',
			'2 of 5 running (Pump P3, Pump P4, Pump P5 off)',
			'1 of 5 running (Pump P2, Pump P3, Pump P4, Pump P5 off)',
			'5 of 6 running (Pump P6 off)',
			'4 of 6 running (Pump P5, Pump P6 off)',
			'3 of 6 running (Pump P4, Pump P5, Pump P6 off)',
			'2 of 6 running (Pump P3, Pump P4, Pump P5, Pump P6 off)',
			'1 of 6 running (Pump P2, Pump P3, Pump P4, Pump P5, Pump P6 off)'
		]);
	});

	it('tells pumps of one name apart by their ids, project-wide', () => {
		const p = station(4, { names: ['Duty pump', 'Duty pump', 'Standby', 'Standby'] });
		expect(nameOf(p, off('P2', 'P3', 'P4'))).toBe(
			'1 of 4 running (Duty pump (P2), Standby (P3), Standby (P4) off)'
		);
		// Another station's pump of the same name makes the label "Name (id)" here too.
		const two = stations(
			{ ids: ['P1', 'P2'], names: ['Pump A', 'Pump B'] },
			{ ids: ['Q1', 'Q2'], names: ['Pump A', 'Pump C'] }
		);
		expect(nameOf(two, off('P1'))).toBe('1 of 2 running (Pump A (P1) off)');
	});

	it('names the condenser example’s pumps by their ids: their longest part is over the budget', () => {
		expect(nameOf(condenserWaterExample(), off('P4', 'P5', 'P6'))).toBe(
			'3 of 6 running (P4, P5, P6 off)'
		);
		expect(nameOf(condenserWaterExample(), off('P6'))).toBe('5 of 6 running (P6 off)');
	});

	it('names a standby put in service with the duty pump off', () => {
		const p = stations({ ids: ['PA', 'PB'], off: ['PB'] });
		expect(nameOf(p, [status('PB', 'on'), status('PA', 'off')])).toBe(
			'1 of 2 running (Pump PA off)'
		);
	});

	it('names pumps off in the base as off, and nothing off as N of N', () => {
		expect(nameOf(station(4, { off: ['P4'] }), off('P3'))).toBe(
			'2 of 4 running (Pump P3, Pump P4 off)'
		);
		expect(nameOf(station(4), [status('P1', 'on')])).toBe('4 of 4 running');
		expect(nameOf(station(4, { off: ['P4'] }), [status('P4', 'on')])).toBe('4 of 4 running');
	});

	it('joins two groups by "; ", in frame order', () => {
		const p = stations(
			{ ids: pumpIds(6), names: pumpIds(6) },
			{ ids: pumpIds(6, 'Q'), names: pumpIds(6, 'Q') }
		);
		expect(nameOf(p, [...off('Q6'), ...off('P5', 'P6')])).toBe(
			'4 of 6 running (P5, P6 off); 5 of 6 running (Q6 off)'
		);
	});

	it('names other pumps "off" and "on" one by one', () => {
		expect(nameOf(pumpTransferExample(), off('P1'))).toBe('Transfer pump off');
		expect(nameOf(baseStatus(pumpTransferExample(), 'P1', 'off'), [status('P1', 'on')])).toBe(
			'Transfer pump on'
		);
	});

	it('names the pumps of a 7- or 8-pump tee ladder one by one, as Other pumps', () => {
		expect(nameOf(ladder(7, { off: ['P1'] }), off('P7'))).toBe('Pump P7 off');
		expect(nameOf(ladder(8), off('P1', 'P8'))).toBe('Pump P1 off; Pump P8 off');
	});

	it('names a pump on its own by its label when "{label} off" fits, else by its id, whatever its status', () => {
		// "x" × 91 + " off" is 95 characters: L1 by its id, while the group keeps its labels.
		const long = stations({ ids: ['P1', 'P2'] }, { ids: ['L1'], names: ['x'.repeat(91)] });
		expect(nameOf(long, [...off('P2'), ...off('L1')])).toBe('1 of 2 running (Pump P2 off); L1 off');
		// "y" × 90 + " on" fits (93) but " off" does not (94): by its id, as when it is off.
		const on = stations({ ids: ['L1'], names: ['y'.repeat(90)], off: ['L1'] });
		expect(nameOf(on, [status('L1', 'on')])).toBe('L1 on');
		expect(nameOf(station(1, { ids: ['L1'], names: ['y'.repeat(89)] }), off('L1'))).toBe(
			`${'y'.repeat(89)} off`
		);
	});

	it('names pumps in series and in a mixed group pump by pump, never "k of N running"', () => {
		expect(nameOf(series(), off('PB'))).toBe('Pump PB off');
		expect(nameOf(twoByTwo(), off('B2'))).toBe('Pump B2 off');
		expect(nameOf(twoByTwo(), [...off('B2'), status('A1', 'on')])).toBe('Pump A1 on; Pump B2 off');
	});

	it('counts the other effective changes, kept whole within the budget', () => {
		const p = station(4);
		expect(nameOf(p, [...off('P4'), level('A1', 5)])).toBe(
			'3 of 4 running (Pump P4 off) + 1 other change'
		);
		expect(nameOf(p, [...off('P4'), level('A1', 5), level('B1', 6)])).toBe(
			'3 of 4 running (Pump P4 off) + 2 other changes'
		);
		// Equal to the base value, or no longer applying: not counted.
		expect(nameOf(p, [...off('P4'), level('A1', 2), level('X9', 5)])).toBe(
			'3 of 4 running (Pump P4 off)'
		);
		// The suffix stays whole: the pump part goes to ids, then to counts, to fit.
		const long = (n: number) => `Station pump number ${n}`;
		const big = station(4, { names: [1, 2, 3, 4].map(long) });
		expect(nameOf(big, [...off('P2', 'P3', 'P4'), level('A1', 5)])).toBe(
			'1 of 4 running (P2, P3, P4 off) + 1 other change'
		);
		// The most a case holds: one pump's status and 29 other changes.
		const many = projectWith(
			[...big.components, ...Array.from({ length: 29 }, (_, i) => tankOf(i))],
			big.connections,
			big.pumpLibrary
		);
		const others = Array.from({ length: 29 }, (_, i) => level(`T${i}`, 9));
		const name = nameOf(many, [...off('P4'), ...others])!;
		expect(name).toBe('3 of 4 running (P4 off) + 29 other changes');
		expect(name.length).toBeLessThanOrEqual(LINEUP_NAME_BUDGET);
	});

	it('is null for a case that changes no pump’s status', () => {
		expect(nameOf(station(4), [level('A1', 5)])).toBeNull();
		expect(nameOf(station(4), [])).toBeNull();
		expect(nameOf(station(4), off('P9'))).toBeNull();
	});

	it('reaches tier 2: every part by ids when the parts by their labels do not fit together', () => {
		const names = (s: string) => [1, 2, 3].map((i) => `Pump number ${i}${s}`);
		const p = stations(
			{ ids: ['A1x', 'A2x', 'A3x'], names: names('A') },
			{ ids: ['B1x', 'B2x', 'B3x'], names: names('B') }
		);
		// Each part alone fits by its labels (67 characters at most), not both together.
		expect(nameOf(p, off('A2x', 'A3x'))).toBe(
			'1 of 3 running (Pump number 2A, Pump number 3A off)'
		);
		expect(nameOf(p, off('A2x', 'A3x', 'B2x', 'B3x'))).toBe(
			'1 of 3 running (A2x, A3x off); 1 of 3 running (B2x, B3x off)'
		);
	});

	it('reaches tier 3: counts per part when even the ids do not fit', () => {
		const ids = Array.from({ length: 6 }, (_, i) => `pump_unit_${i + 1}_main`);
		const p = stations({ ids, names: ids.map((id) => `Main ${id}`) }, { ids: ['L1'] });
		expect(nameOf(p, off(...ids.slice(1)))).toBe('1 of 6 running (5 off)');
		expect(nameOf(p, [...off(...ids.slice(1)), status('L1', 'off')])).toBe(
			'1 of 6 running (5 off); 1 other pump off'
		);
	});

	it('reaches tier 4: one count when the counts per part do not fit either', () => {
		const specs = Array.from({ length: 5 }, (_, s) => ({ ids: [`S${s}a`, `S${s}b`] }));
		const p = stations(...specs);
		expect(nameOf(p, off(...specs.map((s) => s.ids[1]!)))).toBe('5 of 10 pumps running (5 off)');
	});

	it('keeps every name within 93 characters over 1,000 seeded random names and ids, and never lists only some of a group’s pumps off', () => {
		const random = mulberry32(20261104);
		const seen = { named: 0, shared: 0, ids: 0, counts: 0, oneCount: 0, suffix: 0 };
		for (let run = 0; run < 1000; run++) {
			const { project, scenario: s, groups } = randomCase(random);
			const name = lineupName(project, s);
			if (name === null) continue;
			expect(name.length, name).toBeLessThanOrEqual(LINEUP_NAME_BUDGET);
			// Duplicate never cuts it.
			expect(copyName(name)).toBe(`${name} (copy)`);
			checkParts(project, s, groups, name);
			seen.named++;
			if (/ \(x[\w-]*\d+\)/.test(name)) seen.shared++;
			if (/[(,] x[\w-]*\d+[,)]|[(]x[\w-]*\d+[ ,]|^x[\w-]*\d+ o/.test(name)) seen.ids++;
			if (/running \(\d+ off\)|^\d+ other pump/.test(name)) seen.counts++;
			if (/pumps running/.test(name)) seen.oneCount++;
			if (/ other changes?$/.test(name)) seen.suffix++;
		}
		// The cases reach every tier: shared labels, ids, counts per part, one count, the suffix.
		for (const [what, count] of Object.entries(seen)) expect(count, what).toBeGreaterThan(10);
	});
});

/** Tanks T0, T1, … for other changes (made-up inputs). */
function tankOf(i: number): Component {
	return { ...tank(`T${i}`, 0), ports: [] } as Component;
}

/** A seeded generator (mulberry32): the same 1,000 cases every run. */
function mulberry32(seed: number): () => number {
	let a = seed;
	return () => {
		a = (a + 0x6d2b79f5) | 0;
		let t = Math.imul(a ^ (a >>> 15), 1 | a);
		t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}

/**
 * A random project: 1 to 4 stations of 1 to 7 pumps (one pump, or seven: Other pumps), with names
 * of 1 to 40 characters from a small vocabulary (so some repeat) and ids of 1 to 20 characters,
 * some pumps off in the base; and a scenario setting some pumps' statuses, with 0 to 20 other
 * changes (a tank level each, effective).
 */
function randomCase(random: () => number) {
	const pick = (n: number) => Math.floor(random() * n);
	const word = () =>
		['Pump', 'Duty', 'Standby', 'CWP', 'Booster', 'unit', 'no', 'A', 'B'][pick(9)]!;
	const text = (max: number) => {
		let s = word();
		while (s.length < max && random() < 0.6) s += ` ${word()}${pick(3) ? '' : pick(100)}`;
		return s.slice(0, max).trim() || 'P';
	};
	// Ids of 2 to 20 characters ("x…n"), never a tank's (A1, B1, …).
	const idOf = (n: number) => {
		const length = 2 + pick(19) - String(n).length;
		let id = 'x';
		while (id.length < length) id += 'abcdefghij0123456789_-'[pick(22)];
		return `${id}${n}`;
	};
	let n = 0;
	const specs: StationSpec[] = Array.from({ length: 1 + pick(4) }, () => {
		const size = [1, 2, 3, 4, 5, 6, 7][pick(7)]!;
		const ids = Array.from({ length: size }, () => idOf(n++));
		return {
			ids,
			names: ids.map(() => text(1 + pick(40))),
			off: ids.filter(() => random() < 0.15)
		};
	});
	const project = stations(...specs);
	const all = specs.flatMap((s) => s.ids);
	const changes: Override[] = all
		.filter(() => random() < 0.4)
		.map((id) => status(id, random() < 0.7 ? 'off' : 'on'));
	const tanks = project.components.filter((c) => c.type === 'reservoir').map((c) => c.id);
	const others = Array.from({ length: Math.min(pick(21), tanks.length) }, (_, i) =>
		level(tanks[i]!, 50 + i)
	);
	const s = scenario([...changes, ...others]);
	return { project, scenario: s, groups: lineupGroups(project) };
}

/**
 * The name's parts against the frame: each parallel group named lists every member off (by its
 * labels or its ids) or counts them, never a part; each pump named on its own is named with its
 * status in the case (or counted with the others); tier 4 counts every pump named.
 */
function checkParts(
	project: Project,
	s: Scenario,
	groups: readonly LineupGroup[],
	name: string
): void {
	const statusOf = (id: string) => {
		const own = (s.overrides ?? []).find((o) => o.kind === 'component' && o.componentId === id);
		if (own) return own.value === 'off' ? 'off' : 'on';
		const c = project.components.find((x) => x.id === id);
		return c?.type === 'pump' && c.status === 'off' ? 'off' : 'on';
	};
	const named = new Set(
		(s.overrides ?? []).flatMap((o) =>
			o.kind === 'component' && o.field === 'status' ? [o.componentId] : []
		)
	);
	const others = (s.overrides ?? []).filter((o) => o.field !== 'status').length;
	const suffix = others ? ` + ${others} other ${others === 1 ? 'change' : 'changes'}` : '';
	expect(name.endsWith(suffix), name).toBe(true);
	const body = name.slice(0, name.length - suffix.length);
	const pumps = project.components.filter((c) => c.type === 'pump');
	const label = (id: string) => {
		const c = pumps.find((x) => x.id === id)!;
		return pumps.filter((x) => x.name === c.name).length > 1 ? `${c.name} (${id})` : c.name;
	};
	const parallel = groups.filter(
		(g) => g.kind === 'parallel' && g.pumpIds.some((id) => named.has(id))
	);
	const own = groups
		.filter((g) => g.kind !== 'parallel')
		.flatMap((g) => g.pumpIds.filter((id) => named.has(id)));
	const offIn = (ids: readonly string[]) => ids.filter((id) => statusOf(id) === 'off');
	const tier4 = /^(\d+) of (\d+) pumps running(?: \((\d+) off\))?$/.exec(body);
	if (tier4) {
		const every = [...parallel.flatMap((g) => g.pumpIds), ...own];
		const m = offIn(every).length;
		expect(body).toBe(
			m
				? `${every.length - m} of ${every.length} pumps running (${m} off)`
				: `${every.length} of ${every.length} pumps running`
		);
		return;
	}
	const parts = body.split('; ');
	parallel.forEach((g, i) => {
		const part = parts[i]!;
		const n = g.pumpIds.length;
		const down = offIn(g.pumpIds);
		const head = `${n - down.length} of ${n} running`;
		if (!down.length) {
			expect(part).toBe(head);
			return;
		}
		expect([
			`${head} (${down.map(label).join(', ')} off)`,
			`${head} (${down.join(', ')} off)`,
			`${head} (${down.length} off)`
		]).toContain(part);
	});
	const rest = parts.slice(parallel.length);
	// Labels and ids start with a letter: a part that starts with a digit is tier 3's count.
	if (!(rest.length === 1 && /^\d+ other pumps? /.test(rest[0]!))) {
		expect(rest).toHaveLength(own.length);
		rest.forEach((part, i) => {
			const id = own[i]!;
			expect([`${label(id)} ${statusOf(id)}`, `${id} ${statusOf(id)}`]).toContain(part);
		});
		return;
	}
	const down = offIn(own).length;
	const up = own.length - down;
	expect(rest).toEqual([
		[
			...(down ? [`${down} other ${down === 1 ? 'pump' : 'pumps'} off`] : []),
			...(up ? [`${up} other ${up === 1 ? 'pump' : 'pumps'} on`] : [])
		].join(', ')
	]);
}

// ---------------------------------------------------------------------------------------------
// §4.5 followLineupNames, renameNotice
// ---------------------------------------------------------------------------------------------

describe('followLineupNames', () => {
	const template = (...ids: string[]) =>
		withCases(station(4), scenario(off(...ids), nameOf(station(4), off(...ids))!));

	it('renames a case on a toggle', () => {
		const before = template('P4');
		expect(namesOf(before)).toEqual(['3 of 4 running (Pump P4 off)']);
		const { project, renamed } = followLineupNames(before, pressed(before, 'S1', off('P3', 'P4')));
		expect(namesOf(project)).toEqual(['2 of 4 running (Pump P3, Pump P4 off)']);
		expect(renamed).toEqual([
			{ from: '3 of 4 running (Pump P4 off)', to: '2 of 4 running (Pump P3, Pump P4 off)' }
		]);
	});

	it('does not follow a scenario renamed in the same edit', () => {
		const before = template('P4');
		const after = withScenarios(before, [scenario(off('P3', 'P4'), 'Night')]);
		expect(followLineupNames(before, after)).toEqual({ project: after, renamed: [] });
	});

	it('never touches a user’s name', () => {
		const p = station(4);
		const before = withCases(
			p,
			scenario(off('P4'), 'My lineup', 'S1'),
			scenario(off('P3', 'P4'), 'Night', 'S2'),
			scenario(off('P1'), 'Winter: tower bypassed', 'S3'),
			scenario([level('A1', 5)], 'Scenario 3', 'S4'),
			scenario([], 'Scenario 2 (copy)', 'S5'),
			// "Scenario n" of another id than its own: the user's.
			scenario([], 'Scenario 2', 'S6')
		);
		const edits = [
			pressed(before, 'S1', off('P2', 'P4')),
			pressed(before, 'S4', [level('A1', 5), ...off('P2')]),
			pressed(before, 'S5', off('P2')),
			pressed(before, 'S6', off('P2')),
			renamedPump(before, 'P4', 'Standby'),
			baseStatus(before, 'P3', 'off')
		];
		for (const after of edits) {
			const { renamed } = followLineupNames(before, after);
			expect(renamed).toEqual([]);
		}
	});

	it('follows a 4d name on its own toggles and its pump’s rename, not on a base edit or an added other change', () => {
		const before = withCases(station(4), scenario(off('P1'), offName('Pump P1')));
		expect(namesOf(before)).toEqual(['Pump P1 off']);
		const follow = (after: Project) => namesOf(followLineupNames(before, after).project);
		expect(follow(pressed(before, 'S1', off('P1', 'P2')))).toEqual([
			'2 of 4 running (Pump P1, Pump P2 off)'
		]);
		expect(follow(renamedPump(before, 'P1', 'Duty pump'))).toEqual(['Duty pump off']);
		expect(follow(baseStatus(before, 'P3', 'off'))).toEqual(['Pump P1 off']);
		expect(follow(pressed(before, 'S1', [...off('P1'), level('A1', 5)]))).toEqual(['Pump P1 off']);
		// With its id, as 4d names a pump whose name another member has.
		const shared = withCases(
			station(2, { names: ['Booster pump', 'Booster pump'] }),
			scenario(off('P1'), offName('Booster pump', 'P1'))
		);
		expect(
			namesOf(followLineupNames(shared, renamedPump(shared, 'P1', 'Lead pump')).project)
		).toEqual(['Lead pump (P1) off']);
	});

	it('follows a name ending " on" on its pump’s rename and on a toggle', () => {
		const transfer = withCases(
			baseStatus(pumpTransferExample(), 'P1', 'off'),
			scenario([status('P1', 'on')], 'Transfer pump on')
		);
		expect(
			namesOf(followLineupNames(transfer, renamedPump(transfer, 'P1', 'Main pump')).project)
		).toEqual(['Main pump on']);
		const mixed = withCases(
			baseStatus(twoByTwo(), 'A1', 'off'),
			scenario([status('A1', 'on')], 'Pump A1 on')
		);
		const toggled = pressed(mixed, 'S1', [status('A1', 'on'), ...off('B2')]);
		expect(namesOf(followLineupNames(mixed, toggled).project)).toEqual(['Pump A1 on; Pump B2 off']);
	});

	it('follows a template name on a base status edit, a pump rename and a frame change', () => {
		const before = template('P4');
		const follow = (after: Project) => namesOf(followLineupNames(before, after).project);
		expect(follow(baseStatus(before, 'P3', 'off'))).toEqual([
			'2 of 4 running (Pump P3, Pump P4 off)'
		]);
		expect(follow(renamedPump(before, 'P3', 'Standby'))).toEqual(['3 of 4 running (Pump P4 off)']);
		expect(follow(renamedPump(before, 'P4', 'Standby'))).toEqual(['3 of 4 running (Standby off)']);
		// A frame change: a fifth pump joins the station.
		const five = stations({ ids: pumpIds(5) });
		const grown = withScenarios(five, scenariosOf(before));
		expect(follow(grown)).toEqual(['4 of 5 running (Pump P4 off)']);
	});

	it('follows a seventh pump joining a 6-pump tee ladder: the station goes to Other pumps', () => {
		const six = ladder(6);
		const named = (id: string, ids: string[]) =>
			scenario(off(...ids), nameOf(six, off(...ids))!, id);
		const before = withCases(
			six,
			named('S1', ['P6']),
			named('S2', ['P1']),
			named('S3', ['P4', 'P5', 'P6'])
		);
		expect(namesOf(before)).toEqual([
			'5 of 6 running (Pump P6 off)',
			'5 of 6 running (Pump P1 off)',
			'3 of 6 running (Pump P4, Pump P5, Pump P6 off)'
		]);
		const seven = withScenarios(ladder(7), scenariosOf(before));
		expect(namesOf(followLineupNames(before, seven).project)).toEqual([
			'Pump P6 off',
			'Pump P1 off',
			'Pump P4 off; Pump P5 off; Pump P6 off'
		]);
	});

	it('follows a PRV inside a station set active in the base, and then the next toggle', () => {
		const before = withCases(
			prvStation('failed_open'),
			scenario(off('PB'), '1 of 2 running (Pump PB off)')
		);
		expect(lineupName(before, scenariosOf(before)[0]!)).toBe('1 of 2 running (Pump PB off)');
		const active = withScenarios(prvStation('active'), scenariosOf(before));
		const first = followLineupNames(before, active);
		expect(first.renamed).toEqual([{ from: '1 of 2 running (Pump PB off)', to: 'Pump PB off' }]);
		const next = followLineupNames(first.project, pressed(first.project, 'S1', off('PA', 'PB')));
		expect(next.renamed).toEqual([{ from: 'Pump PB off', to: 'Pump PA off; Pump PB off' }]);
	});

	it('adds " + 1 other change" when a tank level is added, and takes it off when it goes', () => {
		const before = template('P4');
		const added = followLineupNames(before, pressed(before, 'S1', [...off('P4'), level('A1', 5)]));
		expect(namesOf(added.project)).toEqual(['3 of 4 running (Pump P4 off) + 1 other change']);
		const removed = followLineupNames(added.project, pressed(added.project, 'S1', off('P4')));
		expect(namesOf(removed.project)).toEqual(['3 of 4 running (Pump P4 off)']);
		// A base edit that makes the level the base's own: the change no longer changes anything.
		const same = followLineupNames(
			added.project,
			edited(added.project, 'A1', (c) => ({ ...c, liquidLevel: 5 }) as Component)
		);
		expect(namesOf(same.project)).toEqual(['3 of 4 running (Pump P4 off)']);
		// And a base edit that makes it change something again.
		const again = followLineupNames(
			same.project,
			edited(same.project, 'A1', (c) => ({ ...c, liquidLevel: 2 }) as Component)
		);
		expect(namesOf(again.project)).toEqual(['3 of 4 running (Pump P4 off) + 1 other change']);
	});

	it('adds and takes off " + 1 other change" on a name of pumps named on their own, in either order of edits', () => {
		const cases = [
			{ project: series(), pump: 'PB', name: 'Pump PB off', tank: 'R1' },
			{ project: twoByTwo(), pump: 'B2', name: 'Pump B2 off', tank: 'R1' },
			{ project: pumpTransferExample(), pump: 'P1', name: 'Transfer pump off', tank: 'R1' }
		];
		for (const { project: start, pump: id, name, tank: t } of cases) {
			const follow = (project: Project, overrides: Override[]) =>
				followLineupNames(project, pressed(project, 'S1', overrides)).project;
			let project = follow(withCases(start, scenario([], 'Scenario 1')), off(id));
			expect(namesOf(project)).toEqual([name]);
			project = follow(project, [...off(id), level(t, 5)]);
			expect(namesOf(project)).toEqual([`${name} + 1 other change`]);
			project = follow(project, off(id));
			expect(namesOf(project)).toEqual([name]);
		}
		// The same changes reached through another pump's status first: the same name.
		let project = withCases(series(), scenario(off('PA', 'PB'), 'Pump PA off; Pump PB off'));
		for (const overrides of [
			[...off('PA', 'PB'), level('R1', 5)],
			[...off('PB'), level('R1', 5)]
		]) {
			project = followLineupNames(project, pressed(project, 'S1', overrides)).project;
		}
		expect(namesOf(project)).toEqual(['Pump PB off + 1 other change']);
	});

	it('keeps a name that is both 4d’s form and the lineup name when a base edit puts its pump in a station', () => {
		// PB on its own (an active PRV ends the station): "Pump PB off" is both forms.
		const before = withCases(prvStation('active'), scenario(off('PB'), 'Pump PB off'));
		expect(lineupName(before, scenariosOf(before)[0]!)).toBe(offName('Pump PB'));
		const after = withScenarios(prvStation('failed_open'), scenariosOf(before));
		expect(namesOf(followLineupNames(before, after).project)).toEqual(['Pump PB off']);
	});

	it('counts the other changes of a 4d name whose pump leaves its station, in either order of edits', () => {
		// 4d's Each pump off in PA and PB in parallel: "Pump PB off". The same two edits, a tank level
		// in the case and the PRV in PB's line set active in the base (PB then on its own, where
		// "Pump PB off" is the pure lineup name of PB off), in both orders, then a further level.
		const start = withCases(prvStation('failed_open'), scenario(off('PB'), offName('Pump PB')));
		const follow = (before: Project, after: Project) => followLineupNames(before, after).project;
		const levelEdit = (project: Project, value: number) =>
			follow(project, pressed(project, 'S1', [...off('PB'), level('A1', value)]));
		const prvActive = (project: Project) =>
			follow(
				project,
				edited(project, 'V1', (c) => ({ ...c, status: 'active' }) as Component)
			);
		const c = prvActive(levelEdit(start, 5));
		const d = levelEdit(prvActive(start), 5);
		expect(scenariosOf(c)).toEqual(scenariosOf(d));
		expect(namesOf(c)).toEqual(['Pump PB off + 1 other change']);
		expect(namesOf(levelEdit(c, 6))).toEqual(['Pump PB off + 1 other change']);
		expect(namesOf(levelEdit(d, 6))).toEqual(['Pump PB off + 1 other change']);
		// A stored case already in that state (no rename yet) follows on its next edit.
		const stuck = withCases(
			prvStation('active'),
			scenario([...off('PB'), level('A1', 5)], 'Pump PB off')
		);
		expect(namesOf(levelEdit(stuck, 6))).toEqual(['Pump PB off + 1 other change']);
	});

	it('follows "Scenario n" from its first press, and back when the presses are reversed', () => {
		const long = (s: string) => pumpIds(6).map((_, i) => `Condenser water pump ${s}-${i + 1}`);
		const p = stations(
			{ ids: pumpIds(6), names: long('P') },
			{ ids: pumpIds(6, 'Q'), names: long('Q') }
		);
		let project = withCases(p, scenario([], 'Scenario 1'));
		const presses = [off('P6'), off('P6', 'P5'), [...off('P6', 'P5'), ...off('Q1')]];
		const names: string[] = [];
		for (const changes of [...presses, presses[1]!, presses[0]!, []]) {
			project = followLineupNames(project, pressed(project, 'S1', changes)).project;
			names.push(namesOf(project)[0]!);
		}
		expect(names).toEqual([
			'5 of 6 running (P6 off)',
			'4 of 6 running (P5, P6 off)',
			'4 of 6 running (P5, P6 off); 5 of 6 running (Q1 off)',
			'4 of 6 running (P5, P6 off)',
			'5 of 6 running (P6 off)',
			'Scenario 1'
		]);
	});

	it('keeps "Scenario 3" with a tank change, and an empty "Scenario 2 (copy)" stored as S5', () => {
		const before = withCases(
			station(4),
			scenario([level('A1', 5)], 'Scenario 3', 'S3'),
			scenario([], 'Scenario 2 (copy)', 'S5')
		);
		const after = withScenarios(before, [
			scenario([level('A1', 5), ...off('P4')], 'Scenario 3', 'S3'),
			scenario(off('P4'), 'Scenario 2 (copy)', 'S5')
		]);
		expect(followLineupNames(before, after).renamed).toEqual([]);
	});

	it('keeps "(copy)" of both forms on a pump rename, a base edit and a frame change, and drops it on a toggle of its own pumps', () => {
		const before = withCases(
			station(4),
			scenario(off('P4'), copyName('3 of 4 running (Pump P4 off)'), 'S1'),
			scenario(off('P1'), copyName(offName('Pump P1')), 'S2')
		);
		const follow = (after: Project) => namesOf(followLineupNames(before, after).project);
		expect(follow(renamedPump(before, 'P4', 'Standby'))).toEqual([
			'3 of 4 running (Standby off) (copy)',
			'Pump P1 off (copy)'
		]);
		expect(follow(renamedPump(before, 'P1', 'Lead'))).toEqual([
			'3 of 4 running (Pump P4 off) (copy)',
			'Lead off (copy)'
		]);
		expect(follow(baseStatus(before, 'P3', 'off'))).toEqual([
			'2 of 4 running (Pump P3, Pump P4 off) (copy)',
			'Pump P1 off (copy)'
		]);
		expect(follow(withScenarios(stations({ ids: pumpIds(5) }), scenariosOf(before)))).toEqual([
			'4 of 5 running (Pump P4 off) (copy)',
			'Pump P1 off (copy)'
		]);
		const toggled = withScenarios(before, [
			scenario(off('P3', 'P4'), copyName('3 of 4 running (Pump P4 off)'), 'S1'),
			scenario(off('P1', 'P2'), copyName(offName('Pump P1')), 'S2')
		]);
		expect(follow(toggled)).toEqual([
			'2 of 4 running (Pump P3, Pump P4 off)',
			'2 of 4 running (Pump P1, Pump P2 off)'
		]);
	});

	it('follows a copy of a copy, and recognises a copy cut at 100 characters', () => {
		const twice = copyName(copyName('3 of 4 running (Pump P4 off)'));
		expect(twice).toBe('3 of 4 running (Pump P4 off) (copy) (copy)');
		const before = withCases(station(4), scenario(off('P4'), twice));
		expect(
			namesOf(followLineupNames(before, pressed(before, 'S1', off('P3', 'P4'))).project)
		).toEqual(['2 of 4 running (Pump P3, Pump P4 off)']);
		// A name of 90 characters: its second copy is cut at the name limit.
		// A name of 87 characters (its longest part, 93, still fits): its second copy is cut.
		const names = ['Lead', 'Main condenser water pump num 22', 'Main condenser water pump num 33'];
		const p = stations({ ids: ['P1', 'P2', 'P3'], names });
		const base = nameOf(p, off('P2', 'P3'))!;
		expect(base).toBe(
			'1 of 3 running (Main condenser water pump num 22, Main condenser water pump num 33 off)'
		);
		const cut = copyName(copyName(base));
		expect(cut.length).toBe(SCENARIO_NAME_LIMIT);
		expect(cut).toBe(`${base} (copy (copy)`);
		const withCut = withCases(p, scenario(off('P2', 'P3'), cut));
		const followed = followLineupNames(withCut, renamedPump(withCut, 'P3', 'Spare'));
		expect(namesOf(followed.project)).toEqual([
			'1 of 3 running (Main condenser water pump num 22, Spare off) (copy) (copy)'
		]);
	});

	it('names a deleted pump’s case "Scenario n"', () => {
		const before = withCases(station(4), scenario(off('P4'), '3 of 4 running (Pump P4 off)', 'S2'));
		const after = {
			...before,
			components: before.components.filter((c) => c.id !== 'P4'),
			connections: before.connections.filter((c) => !['SP4', 'DP4'].includes(c.id))
		};
		expect(followLineupNames(before, after).renamed).toEqual([
			{ from: '3 of 4 running (Pump P4 off)', to: 'Scenario 2' }
		]);
	});

	it('does nothing when no name passes the pattern, or nothing it reads changed', () => {
		const user = withCases(station(4), scenario(off('P4'), 'Night'));
		const after = renamedPump(user, 'P4', 'Standby');
		expect(followLineupNames(user, after).project).toBe(after);
		const lineup = template('P4');
		const moved = edited(lineup, 'A1', (c) => ({ ...c, elevation: 3 }));
		expect(followLineupNames(lineup, moved).project).toBe(moved);
	});
});

describe('renameNotice', () => {
	const r = (from: string, to: string) => ({ from, to });

	it('says one rename in full', () => {
		expect(renameNotice([r('Scenario 2', '3 of 4 running (Pump P4 off)')])).toBe(
			'«Scenario 2» is now «3 of 4 running (Pump P4 off)»: a name the app made follows its pumps until you rename it.'
		);
	});

	it('says two in full', () => {
		expect(
			renameNotice([
				r('3 of 4 running (Pump P4 off)', '2 of 4 running (Pump P3, Pump P4 off)'),
				r('2 of 4 running (Pump P3, Pump P4 off)', '1 of 4 running (Pump P2, Pump P3, Pump P4 off)')
			])
		).toBe(
			'Renamed 2 scenarios to match their pumps: «3 of 4 running (Pump P4 off)» is now «2 of 4 running (Pump P3, Pump P4 off)»; «2 of 4 running (Pump P3, Pump P4 off)» is now «1 of 4 running (Pump P2, Pump P3, Pump P4 off)». A name the app made follows its pumps until you rename it.'
		);
	});

	it('says more than two by count, with one example', () => {
		expect(
			renameNotice([
				r('3 of 4 running (Pump P4 off)', '3 of 4 running (Standby off)'),
				r('2 of 4 running (Pump P3, Pump P4 off)', '2 of 4 running (Pump P3, Standby off)'),
				r('Pump P4 off', 'Standby off')
			])
		).toBe(
			'Renamed 3 scenarios to match their pumps, for example «3 of 4 running (Pump P4 off)» is now «3 of 4 running (Standby off)». A name the app made follows its pumps until you rename it.'
		);
	});

	it('says nothing for none', () => {
		expect(renameNotice([])).toBe('');
	});
});

describe('solvedCaseWords', () => {
	it('names a solved case by its stored name and id, and the name solved under when it differs', () => {
		const solved = { id: 'S2', name: '3 of 4 running (Pump P4 off)' };
		expect(solvedCaseWords('3 of 4 running (Pump P4 off)', solved)).toBe(
			'scenario 3 of 4 running (Pump P4 off) (S2)'
		);
		expect(solvedCaseWords('3 of 4 running (Standby off)', solved)).toBe(
			'scenario 3 of 4 running (Standby off) (S2), solved as «3 of 4 running (Pump P4 off)»'
		);
	});
});

// ---------------------------------------------------------------------------------------------
// §7 The Add cases block (L1b): lineupPlan, withLineupCases, the stop order, the words
// ---------------------------------------------------------------------------------------------

interface Answer {
	status: number;
	body: unknown;
}
/** A fixture case with the API's answers (__fixtures__/pump-groups-input.json). */
interface SolvedCase {
	name: string;
	project: Project;
	memberIds: string[];
	solve: SolveResponse;
	groupCurve: Answer;
	scenarioCases?: Record<string, { solve: SolveResponse; groupCurve: Answer }>;
}
const solvedCase = (name: string) =>
	(fixture.cases as unknown as SolvedCase[]).find((c) => c.name === name)!;
const stationOf = (c: SolvedCase) => (c.groupCurve.body as PumpGroupCurveResponse).station;
const withoutScenarios = (p: Project) => withScenarios(structuredClone(p), []);

/** The `lineups` case: four curve_a pumps on Crane tees, all carrying flow in the base case. */
const lineups = solvedCase('lineups');
/** PA and PB, PB's discharge valve isolated: PB `running` at 0.0 m³/s in the base case. */
const closedLeg = solvedCase('lineups-closed-leg');
const oneOffCase = solvedCase('one-off');

/** The plan for a fixture case's base case shown and current (its station, members and solve). */
function planOn(c: SolvedCase, values: Partial<LineupPlanInput> = {}): LineupPlan {
	return lineupPlan({
		project: withoutScenarios(c.project),
		shownCase: null,
		station: stationOf(c),
		memberIds: c.memberIds,
		base: { response: c.solve, stale: false },
		preset: 'running',
		savedOrder: [],
		...values
	});
}

/** A response with some pump results changed (synthetic). */
function edit(response: SolveResponse, changes: Record<string, Partial<PumpResult>>) {
	const copy = structuredClone(response);
	for (const [id, change] of Object.entries(changes)) {
		Object.assign(copy.solvedState.pumpResults[id]!, change);
	}
	return copy;
}

/**
 * A base solve of a made-up project (synthetic): each pump running at 20 L/s, full speed, no
 * control, off where the project has it off; `changes` alters some.
 */
function solveOf(project: Project, changes: Record<string, Partial<PumpResult>> = {}) {
	const pumpResults: Record<string, Partial<PumpResult>> = {};
	for (const c of project.components) {
		if (c.type !== 'pump') continue;
		const off = c.status === 'off';
		pumpResults[c.id] = {
			status: off ? 'off' : 'running',
			operatingFlow: off ? 0 : 0.02,
			speed: 1,
			control: null,
			...changes[c.id]
		};
	}
	return { solvedState: { pumpResults } } as unknown as SolveResponse;
}
const PARALLEL = { arrangement: 'parallel' } as PumpGroupStation;
const pumpsOf = (project: Project) =>
	project.components.filter((c) => c.type === 'pump').map((c) => c.id);

/** The plan for a made-up project, every pump a member, its synthetic base solve. */
function planOf(
	project: Project,
	values: Partial<LineupPlanInput> = {},
	changes: Record<string, Partial<PumpResult>> = {}
): LineupPlan {
	return lineupPlan({
		project,
		shownCase: null,
		station: PARALLEL,
		memberIds: pumpsOf(project),
		base: { response: solveOf(project, changes), stale: false },
		preset: 'running',
		savedOrder: [],
		...values
	});
}

/** Each case's preview item. */
const items = (plan: LineupPlan) => plan.cases.map((c) => c.words);
/** The changes each case writes, as `id off` (stored order). */
const writes = (project: Project) =>
	scenariosOf(project).map((s) =>
		(s.overrides ?? []).map((o) =>
			o.kind === 'component' ? `${o.componentId} ${String(o.value)}` : o.kind
		)
	);

describe('lineupPlan: the gates (§7.2)', () => {
	const series = stationOf(solvedCase('series'));
	const station = stationOf(lineups);
	const gate = (values: Partial<LineupPlanInput>) => planOn(lineups, values);

	it('gives each gate’s words, in 4d’s order, under both presets', () => {
		for (const preset of ['running', 'each'] as const) {
			const at = (values: Partial<LineupPlanInput>) => gate({ preset, ...values });
			expect(at({ station: series })).toMatchObject({
				gateKind: 'series',
				gate: 'Cases are added here for pumps in parallel only: in series a stopped pump blocks the line in this app (a stopped pump passing flow is not modelled), so the station would carry no flow.',
				showSolveAll: false
			});
			expect(at({ station: { ...station, arrangement: 'mixed' } })).toMatchObject({
				gateKind: 'mixed',
				gate: 'Cases are added here for pumps in parallel only; this station is mixed: neither all in parallel nor all in series.',
				showSolveAll: false
			});
			expect(at({ project: lineups.project, shownCase: 'S8' })).toMatchObject({
				gateKind: 'scenario',
				gate: 'Cases are made from the base case: show the base case to add them. To study Delivery tank 5 m higher with pumps off, duplicate it in Scenarios and set those pumps off there.',
				showSolveAll: false
			});
			// The arrangement first: a series station in a scenario says why in series.
			expect(at({ station: series, project: lineups.project, shownCase: 'S8' }).gateKind).toBe(
				'series'
			);
			expect(at({ base: { response: lineups.solve, stale: true } })).toMatchObject({
				gateKind: 'stale',
				gate: "The base case's results are out of date: solve it again, so the pumps that run are read from the project as it is now.",
				showSolveAll: true
			});
			expect(at({ base: null }).gateKind).toBe('stale');
			const offs = edit(lineups.solve, {
				P2: { status: 'off', operatingFlow: 0 },
				P3: { status: 'off', operatingFlow: 0 },
				P4: { status: 'off', operatingFlow: 0 }
			});
			expect(at({ base: { response: offs, stale: false } })).toMatchObject({
				gateKind: 'fewer_on',
				gate: 'Needs two or more of these pumps switched on in the base case: Pump P2, Pump P3 and Pump P4 are off.',
				showSolveAll: true
			});
			// One off: "is".
			expect(at({ memberIds: ['P1', 'P2'], base: { response: offs, stale: false } }).gate).toBe(
				'Needs two or more of these pumps switched on in the base case: Pump P2 is off.'
			);
			// No member carries flow: some on behind a closed valve (running at zero flow), some
			// held at no flow; the test is the flow, not the state word (§3.5).
			const none = edit(lineups.solve, {
				P1: { operatingFlow: 0 },
				P2: { operatingFlow: 0 },
				P3: { status: 'no_flow', operatingFlow: 0 },
				P4: { operatingFlow: 1e-7 }
			});
			expect(at({ base: { response: none, stale: false } })).toMatchObject({
				gateKind: 'no_flow',
				gate: 'No pump of the group carries flow in the base case, so switching pumps off changes nothing.',
				showSolveAll: true
			});
			// Under a gate: nothing else, and the button's words with no count.
			for (const plan of [
				at({ station: series }),
				at({ base: { response: none, stale: false } })
			]) {
				expect(plan).toMatchObject({
					about: null,
					sentence: null,
					stopOrder: null,
					cases: [],
					add: [],
					frame: null,
					refusal: null,
					label: 'Add cases',
					notice: null,
					undoLabel: LINEUP_UNDO_LABELS[preset]
				});
			}
			// No station: no block.
			expect(at({ station: null })).toMatchObject({ gate: null, gateKind: null, add: [] });
			expect(at({ station: null }).showSolveAll).toBe(false);
		}
	});
});

describe('lineupPlan: By number running (§7.4)', () => {
	it('makes the lineups fixture’s three cases, its scenarios exactly, with every word', () => {
		const project = withoutScenarios(lineups.project);
		const plan = planOn(lineups);
		expect(plan.gate).toBeNull();
		expect(plan.showSolveAll).toBe(true);
		expect(plan.about).toBe(
			"Makes one scenario for each number of these pumps running, from 3 down to 1: the base case with the pumps that stop first switched off and nothing else changed. In a case's name, running means switched on; Running combinations shows whether each pump carries flow. Other sets of the same number of pumps are not made: change the stop order and add again to compare them."
		);
		expect(plan.sentence).toBe(
			"Pump P1, Pump P2, Pump P3 and Pump P4 have the same pump curve and speed. Which of them run can still change the answer, through the tees and each pump's own piping, most when few run: change the stop order to compare which run at each count; Each pump off compares them with one off."
		);
		expect(plan.stopOrder).toEqual({
			order: ['P4', 'P3', 'P2', 'P1'],
			isDefault: true,
			summary:
				'Stop order: Pump P4 first, then Pump P3 and Pump P2; Pump P1 stays on in every case',
			items: [
				{ id: 'P4', label: 'Pump P4', note: ' (stops first)' },
				{ id: 'P3', label: 'Pump P3', note: '' },
				{ id: 'P2', label: 'Pump P2', note: '' },
				{ id: 'P1', label: 'Pump P1', note: ' (stays on in every case)' }
			]
		});
		expect(items(plan)).toEqual([
			'3 of 4 running (Pump P4 off)',
			'2 of 4 running (Pump P3, Pump P4 off)',
			'1 of 4 running (Pump P2, Pump P3, Pump P4 off)'
		]);
		expect(plan.add).toEqual([
			{ id: 'S1', name: '3 of 4 running (Pump P4 off)', stopped: ['P4'] },
			{ id: 'S2', name: '2 of 4 running (Pump P3, Pump P4 off)', stopped: ['P3', 'P4'] },
			{
				id: 'S3',
				name: '1 of 4 running (Pump P2, Pump P3, Pump P4 off)',
				stopped: ['P2', 'P3', 'P4']
			}
		]);
		expect(plan.cases.map((c) => [c.kind, c.id, c.sameNameId])).toEqual([
			['add', 'S1', null],
			['add', 'S2', null],
			['add', 'S3', null]
		]);
		expect(plan.existing).toEqual([]);
		expect(plan.idle).toEqual([]);
		expect(plan.frame).toBeNull();
		expect(plan.refusal).toBeNull();
		expect(plan.label).toBe('Add 3 cases');
		expect(plan.undoLabel).toBe('add cases by number running');
		expect(plan.notice).toBe(
			'Added 3 cases by number running: «3 of 4 running (Pump P4 off)», «2 of 4 running (Pump P3, Pump P4 off)» and «1 of 4 running (Pump P2, Pump P3, Pump P4 off)». Solve all solves every case not yet solved; Undo removes them.'
		);
		// Exactly the fixture's S1 to S3, the scenarios the API solved.
		const made = withLineupCases(project, plan.add);
		expect(made.scenarios).toEqual(lineups.project.scenarios!.slice(0, 3));
		expect(made.scenarios!.map((s) => s.id)).toEqual(plan.add.map((a) => a.id));
		// Then Each pump off: P4's case is S1 already; S4 to S6 are the fixture's too.
		const each = lineupPlan({
			project: made,
			shownCase: null,
			station: stationOf(lineups),
			memberIds: lineups.memberIds,
			base: { response: lineups.solve, stale: false },
			preset: 'each',
			savedOrder: []
		});
		expect(items(each)).toEqual([
			'Pump P1 off',
			'Pump P2 off',
			'Pump P3 off',
			'Pump P4 off: already a scenario, «3 of 4 running (Pump P4 off)» (S1)'
		]);
		expect(withLineupCases(made, each.add).scenarios).toEqual(
			lineups.project.scenarios!.slice(0, 6)
		);
	});

	it('names N = 2 to 6 pumps’ cases, the pumps that stop first by the stop order, written in component order', () => {
		const expected: Record<number, string[]> = {
			2: ['1 of 2 running (Pump P2 off)'],
			3: ['2 of 3 running (Pump P3 off)', '1 of 3 running (Pump P2, Pump P3 off)'],
			4: [
				'3 of 4 running (Pump P4 off)',
				'2 of 4 running (Pump P3, Pump P4 off)',
				'1 of 4 running (Pump P2, Pump P3, Pump P4 off)'
			],
			5: [
				'4 of 5 running (Pump P5 off)',
				'3 of 5 running (Pump P4, Pump P5 off)',
				'2 of 5 running (Pump P3, Pump P4, Pump P5 off)',
				'1 of 5 running (Pump P2, Pump P3, Pump P4, Pump P5 off)'
			],
			6: [
				'5 of 6 running (Pump P6 off)',
				'4 of 6 running (Pump P5, Pump P6 off)',
				'3 of 6 running (Pump P4, Pump P5, Pump P6 off)',
				'2 of 6 running (Pump P3, Pump P4, Pump P5, Pump P6 off)',
				'1 of 6 running (Pump P2, Pump P3, Pump P4, Pump P5, Pump P6 off)'
			]
		};
		for (let n = 2; n <= 6; n++) {
			const project = station(n);
			const ids = pumpIds(n);
			const plan = planOf(project);
			expect(plan.cases, `${n}`).toHaveLength(n - 1);
			expect(plan.add.map((a) => a.name)).toEqual(expected[n]);
			// The last listed stop first: k running stops the last n − k.
			expect(plan.add.map((a) => a.stopped)).toEqual(
				Array.from({ length: n - 1 }, (_, i) => ids.slice(n - 1 - i))
			);
			expect(plan.stopOrder!.order).toEqual([...ids].reverse());
			// Another order: the first pump stops first, the rest from the last.
			const order = [ids[0]!, ...ids.slice(1).reverse()];
			const moved = planOf(project, { savedOrder: order });
			const made = withLineupCases(project, moved.add);
			for (const [i, written] of writes(made).entries()) {
				const stopped = order.slice(0, i + 1);
				// Component order, whatever the stop order.
				expect(written).toEqual(ids.filter((id) => stopped.includes(id)).map((id) => `${id} off`));
			}
		}
	});

	it('makes the worked cases: a reordered stop, P4 off in the base, P4 idle (§7.4’s table)', () => {
		const four = station(4);
		const reordered = planOf(four, { savedOrder: ['P1', 'P4', 'P3', 'P2'] });
		expect(items(reordered)).toEqual([
			'3 of 4 running (Pump P1 off)',
			'2 of 4 running (Pump P1, Pump P4 off)',
			'1 of 4 running (Pump P1, Pump P3, Pump P4 off)'
		]);
		expect(writes(withLineupCases(four, reordered.add))).toEqual([
			['P1 off'],
			['P1 off', 'P4 off'],
			['P1 off', 'P3 off', 'P4 off']
		]);
		expect(reordered.stopOrder).toMatchObject({
			isDefault: false,
			summary: 'Stop order: Pump P1 first, then Pump P4 and Pump P3; Pump P2 stays on in every case'
		});

		// P4 off in the base: named as off in every case, never written.
		const p4Off = station(4, { off: ['P4'] });
		const plan = planOf(p4Off);
		expect(plan.stopOrder!.order).toEqual(['P3', 'P2', 'P1']);
		expect(items(plan)).toEqual([
			'2 of 4 running (Pump P3, Pump P4 off)',
			'1 of 4 running (Pump P2, Pump P3, Pump P4 off)'
		]);
		expect(writes(withLineupCases(p4Off, plan.add))).toEqual([['P3 off'], ['P2 off', 'P3 off']]);
		expect(plan.about).toBe(
			"Makes one scenario for each number of these pumps running, from 2 down to 1: the base case with the pumps that stop first switched off and nothing else changed. Pump P4 is off in the base case and stays off in every case. In a case's name, running means switched on; Running combinations shows whether each pump carries flow. Other sets of the same number of pumps are not made: change the stop order and add again to compare them."
		);
		const twoOff = planOf(station(4, { off: ['P3', 'P4'] }));
		expect(twoOff.about).toBe(
			"Makes one scenario with one of these pumps running: the base case with the pump that stops first switched off and nothing else changed. Pump P3 and Pump P4 are off in the base case and stay off in every case. In a case's name, running means switched on; Running combinations shows whether each pump carries flow. Other sets of the same number of pumps are not made: change the stop order and add again to compare them."
		);
		expect(twoOff.stopOrder!.summary).toBe(
			'Stop order: Pump P2 stops; Pump P1 stays on in every case'
		);
		expect(items(twoOff)).toEqual(['1 of 4 running (Pump P2, Pump P3, Pump P4 off)']);

		// P4 idle (on behind a closed valve: running at zero flow): its case alone is the base's
		// state; a case that stops it with others is made.
		const idle = planOf(four, {}, { P4: { operatingFlow: 0 } });
		expect(idle.idle).toEqual(['P4']);
		expect(idle.cases.map((c) => [c.kind, c.stopped])).toEqual([
			['base_state', ['P4']],
			['add', ['P3', 'P4']],
			['add', ['P2', 'P3', 'P4']]
		]);
		expect(items(idle)).toEqual([
			"3 of 4 running (Pump P4 off): not made, the base case's state (Pump P4 carries no flow in the base case)",
			'2 of 4 running (Pump P3, Pump P4 off)',
			'1 of 4 running (Pump P2, Pump P3, Pump P4 off)'
		]);
		expect(idle.add.map((a) => a.id)).toEqual(['S1', 'S2']);
		expect(idle.stopOrder!.items.map((i) => i.note)).toEqual([
			' (stops first) (carries no flow in the base case)',
			'',
			'',
			' (stays on in every case)'
		]);
		// Two idle pumps stopped together: one item, both named.
		const two = planOf(
			four,
			{},
			{ P3: { status: 'no_flow', operatingFlow: 0 }, P4: { operatingFlow: 0 } }
		);
		expect(items(two).slice(0, 2)).toEqual([
			"3 of 4 running (Pump P4 off): not made, the base case's state (Pump P4 carries no flow in the base case)",
			"2 of 4 running (Pump P3, Pump P4 off): not made, the base case's state (Pump P3 and Pump P4 carry no flow in the base case)"
		]);
	});

	it('on lineups-closed-leg’s real base: PB, running at 0.0, is idle, so the only case is the base’s state', () => {
		const pb = closedLeg.solve.solvedState.pumpResults.PB!;
		expect([pb.status, pb.operatingFlow]).toEqual(['running', 0]);
		expect(carriesFlow(pb)).toBe(false);
		expect(carriesFlow(closedLeg.solve.solvedState.pumpResults.PA)).toBe(true);
		const plan = planOn(closedLeg);
		expect(plan.idle).toEqual(['PB']);
		expect(plan.cases.map((c) => c.kind)).toEqual(['base_state']);
		expect(items(plan)).toEqual([
			"1 of 2 running (Pump PB off): not made, the base case's state (Pump PB carries no flow in the base case)"
		]);
		expect(plan.add).toEqual([]);
		expect(plan.refusal).toBe(
			"Nothing to add: each case by number running already exists or is the base case's state."
		);
		expect(plan.label).toBe('Add cases');
		expect(plan.notice).toBeNull();
		expect(plan.stopOrder!.items.map((i) => i.note)).toEqual([
			' (stops first) (carries no flow in the base case)',
			' (stays on in every case)'
		]);
		// With the fixture's own "Pump PB off" present: still the base's state, not an existing case.
		expect(planOn(closedLeg, { project: closedLeg.project }).cases.map((c) => c.kind)).toEqual([
			'base_state'
		]);
	});

	it('finds an existing case in any order of its changes and with a change equal to the base, named with its id', () => {
		const project = withScenarios(withoutScenarios(lineups.project), [
			{ id: 'S1', name: 'Winter', overrides: [...off('P3', 'P4'), level('R2', 5)] },
			{ id: 'S2', name: 'Pump P4 off (hand)', overrides: [status('P1', 'on'), ...off('P4')] },
			{ id: 'S3', name: 'Two off', overrides: off('P4', 'P3') },
			{ id: 'S4', name: 'Two off again', overrides: off('P3', 'P4') }
		]);
		const plan = planOn(lineups, { project });
		expect(plan.cases.map((c) => [c.kind, c.id, c.existingName])).toEqual([
			['existing', 'S2', 'Pump P4 off (hand)'],
			// The first in case order; "Winter" has a tank level too and is never a match.
			['existing', 'S3', 'Two off'],
			['add', 'S5', null]
		]);
		expect(items(plan)).toEqual([
			'3 of 4 running (Pump P4 off): already a scenario, «Pump P4 off (hand)» (S2)',
			'2 of 4 running (Pump P3, Pump P4 off): already a scenario, «Two off» (S3)',
			'1 of 4 running (Pump P2, Pump P3, Pump P4 off)'
		]);
		expect(plan.existing).toEqual([
			{ stopped: ['P4'], scenarioId: 'S2', scenarioName: 'Pump P4 off (hand)' },
			{ stopped: ['P3', 'P4'], scenarioId: 'S3', scenarioName: 'Two off' }
		]);
		expect(plan.label).toBe('Add 1 case');
		expect(plan.notice).toBe(
			'Added 1 case by number running: «1 of 4 running (Pump P2, Pump P3, Pump P4 off)». Solve all solves every case not yet solved; Undo removes them.'
		);
		// The same name: the short form.
		expect(items(planOn(lineups, { project: lineups.project }))[0]).toBe(
			'3 of 4 running (Pump P4 off): already a scenario (S1)'
		);
	});

	it('adds a case whose name another case has, and says which', () => {
		const project = withScenarios(withoutScenarios(lineups.project), [
			{
				id: 'S1',
				name: '2 of 4 running (Pump P3, Pump P4 off)',
				overrides: [...off('P3', 'P4'), level('R2', 5)]
			}
		]);
		const plan = planOn(lineups, { project });
		expect(plan.cases.map((c) => [c.kind, c.id, c.sameNameId])).toEqual([
			['add', 'S2', null],
			['add', 'S3', 'S1'],
			['add', 'S4', null]
		]);
		expect(items(plan)[1]).toBe(
			'2 of 4 running (Pump P3, Pump P4 off): scenario S1 has this name too but is another case'
		);
	});

	it('takes the first free ids on the growing project', () => {
		const project = withScenarios(withoutScenarios(lineups.project), [
			{ id: 'S2', name: 'Winter', overrides: [] }
		]);
		const plan = planOn(lineups, { project });
		expect(plan.add.map((a) => a.id)).toEqual(['S1', 'S3', 'S4']);
		expect(scenariosOf(withLineupCases(project, plan.add)).map((s) => [s.id, s.name])).toEqual([
			['S2', 'Winter'],
			['S1', '3 of 4 running (Pump P4 off)'],
			['S3', '2 of 4 running (Pump P3, Pump P4 off)'],
			['S4', '1 of 4 running (Pump P2, Pump P3, Pump P4 off)']
		]);
	});

	it('refuses past the scenario limit with the count, and says when nothing is left to add', () => {
		const eighteen: Scenario[] = Array.from({ length: 18 }, (_, i) => ({
			id: `S${i + 1}`,
			name: `Case ${i + 1}`,
			overrides: []
		}));
		const plan = planOn(lineups, {
			project: withScenarios(withoutScenarios(lineups.project), eighteen)
		});
		expect(MAX_SCENARIOS).toBe(20);
		expect(plan.refusal).toBe(
			'Adding 3 cases would make 21 scenarios; a project holds at most 20 scenarios.'
		);
		expect(plan.label).toBe('Add 3 cases');
		// At the limit, not past it: 17 scenarios and 3 cases make 20, which a project holds.
		const atLimit = planOn(lineups, {
			project: withScenarios(withoutScenarios(lineups.project), eighteen.slice(0, 17))
		});
		expect(atLimit.add).toHaveLength(3);
		expect(atLimit.refusal).toBeNull();
		expect(atLimit.label).toBe('Add 3 cases');
		// The fixture's own scenarios hold every case.
		const every = planOn(lineups, { project: lineups.project });
		expect(every.add).toEqual([]);
		expect(every.refusal).toBe(
			'Every case by number running already exists: «3 of 4 running (Pump P4 off)», «2 of 4 running (Pump P3, Pump P4 off)» and «1 of 4 running (Pump P2, Pump P3, Pump P4 off)».'
		);
		expect(every.label).toBe('Add cases');
		// Existing and base-state cases only.
		const idle = edit(lineups.solve, { P4: { operatingFlow: 0 } });
		const rest = planOn(lineups, {
			project: lineups.project,
			base: { response: idle, stale: false }
		});
		expect(rest.cases.map((c) => c.kind)).toEqual(['base_state', 'existing', 'existing']);
		expect(rest.refusal).toBe(
			"Nothing to add: each case by number running already exists or is the base case's state."
		);
	});

	it('derives the stop order: the saved one for the same pumps on, else the default, and the saved one back', () => {
		const ids = pumpIds(4);
		const saved = ['P1', 'P4', 'P3', 'P2'];
		expect(defaultStopOrder(ids)).toEqual(['P4', 'P3', 'P2', 'P1']);
		expect(effectiveStopOrder(saved, ids)).toEqual(saved);
		expect(effectiveStopOrder([], ids)).toEqual(['P4', 'P3', 'P2', 'P1']);
		// Another set on: the default, nothing merged.
		expect(effectiveStopOrder(saved, ['P1', 'P2', 'P3'])).toEqual(['P3', 'P2', 'P1']);
		expect(effectiveStopOrder(['P1', 'P1', 'P2', 'P3'], ids)).toEqual(['P4', 'P3', 'P2', 'P1']);
		// Another set of the same size (P1 on and P4 off where P4 was on and P1 off): the default.
		expect(effectiveStopOrder(['P2', 'P4', 'P3'], ['P1', 'P2', 'P3'])).toEqual(['P3', 'P2', 'P1']);
		// Through the plan: P4 set off in the base, then on again (an Undo).
		expect(planOf(station(4), { savedOrder: saved }).stopOrder!.order).toEqual(saved);
		const p4Off = station(4, { off: ['P4'] });
		expect(planOf(p4Off, { savedOrder: saved }).stopOrder).toMatchObject({
			order: ['P3', 'P2', 'P1'],
			isDefault: true
		});
		expect(planOf(station(4), { savedOrder: saved }).stopOrder).toMatchObject({
			order: saved,
			isDefault: false
		});
		// An order saved with P1 off in the base holds there; with P1 on and P4 off instead (as
		// many pumps on, another set) the plan uses the default: its list, its cases, nothing of P4.
		const p1Saved = ['P2', 'P4', 'P3'];
		expect(planOf(station(4, { off: ['P1'] }), { savedOrder: p1Saved }).stopOrder).toMatchObject({
			order: p1Saved,
			isDefault: false
		});
		const swapped = planOf(p4Off, { savedOrder: p1Saved });
		expect(swapped.stopOrder).toMatchObject({ order: ['P3', 'P2', 'P1'], isDefault: true });
		expect(swapped.stopOrder!.items.map((item) => item.label)).toEqual([
			'Pump P3',
			'Pump P2',
			'Pump P1'
		]);
		expect(swapped.add.map((a) => a.stopped)).toEqual([['P3'], ['P2', 'P3']]);
		expect(items(swapped)).toEqual([
			'2 of 4 running (Pump P3, Pump P4 off)',
			'1 of 4 running (Pump P2, Pump P3, Pump P4 off)'
		]);
		// A saved order equal to the default is the default (§7.5: Default order is not shown),
		// as after "Stop Pump P4 later" then "Stop Pump P4 earlier".
		const back = movedStopOrder(movedStopOrder(defaultStopOrder(ids), 'P4', 'down'), 'P4', 'up');
		expect(back).toEqual(['P4', 'P3', 'P2', 'P1']);
		expect(planOf(station(4), { savedOrder: back }).stopOrder).toMatchObject({
			order: ['P4', 'P3', 'P2', 'P1'],
			isDefault: true
		});
		// A move swaps neighbours; at an end it changes nothing.
		expect(movedStopOrder(ids, 'P2', 'up')).toEqual(['P2', 'P1', 'P3', 'P4']);
		expect(movedStopOrder(ids, 'P2', 'down')).toEqual(['P1', 'P3', 'P2', 'P4']);
		expect(movedStopOrder(ids, 'P1', 'up')).toEqual(ids);
		expect(movedStopOrder(ids, 'P4', 'down')).toEqual(ids);
		expect(movedStopOrder(ids, 'P9', 'up')).toEqual(ids);
	});

	it('names the pumps in the summary as the group’s names do: by ids on the condenser example', () => {
		const condenser = withScenarios(condenserWaterExample(), []);
		const plan = planOf(condenser);
		expect(plan.stopOrder!.summary).toBe(
			'Stop order: P6 first, then P5, P4, P3 and P2; P1 stays on in every case'
		);
		expect(plan.add[0]!.name).toBe('5 of 6 running (P6 off)');
		// The list and the sentence keep the full labels.
		expect(plan.stopOrder!.items[0]).toEqual({
			id: 'P6',
			label: 'Condenser water pump CWP-6',
			note: ' (stops first)'
		});
		expect(stopOrderSummary(condenser, ['P2', 'P1'])).toBe(
			'Stop order: P2 stops; P1 stays on in every case'
		);
		expect(stopOrderSummary(station(3), ['P3', 'P2', 'P1'])).toBe(
			'Stop order: Pump P3 first, then Pump P2; Pump P1 stays on in every case'
		);
	});

	it('names the pumps project-wide where a pump off the card has a member’s name (§7.5 Labels, decision 8)', () => {
		// P4, not on the card, is named "Pump P3" too: project-wide the member P3 is "Pump P3
		// (P3)", while over the card's members alone (4d's memberLabels) it would be "Pump P3".
		const twin = renamedPump(station(4), 'P4', 'Pump P3');
		const card = { memberIds: ['P1', 'P2', 'P3'] };
		const plan = planOf(twin, card);
		// The stop order's list.
		expect(plan.stopOrder!.items.map((item) => item.label)).toEqual([
			'Pump P3 (P3)',
			'Pump P2',
			'Pump P1'
		]);
		// The sentence of §7.6.
		expect(plan.sentence).toBe(
			"Pump P1, Pump P2 and Pump P3 (P3) have the same pump curve and speed. Which of them run can still change the answer, through the tees and each pump's own piping, most when few run: change the stop order to compare which run at each count; Each pump off compares them with one off."
		);
		// A base-state item: P3 on and carrying no flow.
		const idle = planOf(twin, card, { P3: { operatingFlow: 0 } });
		expect(idle.cases[0]).toMatchObject({ kind: 'base_state', stopped: ['P3'] });
		expect(idle.cases[0]!.words).toBe(
			`${idle.cases[0]!.name}: not made, the base case's state (Pump P3 (P3) carries no flow in the base case)`
		);
		// About's base-off sentence: P3 off in the base.
		const p3Off = renamedPump(station(4, { off: ['P3'] }), 'P4', 'Pump P3');
		expect(planOf(p3Off, card).about).toContain(
			' Pump P3 (P3) is off in the base case and stays off in every case. '
		);
	});

	it('states a shared curve and speed as a fact of the inputs, else says the choice can matter', () => {
		const same =
			"have the same pump curve and speed. Which of them run can still change the answer, through the tees and each pump's own piping, most when few run: change the stop order to compare which run at each count; Each pump off compares them with one off.";
		const differ =
			'Not all of these pumps have the same pump curve and speed without a speed control, so which of them run can change the answer: the stop order decides which stop first.';
		const four = station(4);
		const all = { P1: { speed: 0.9 }, P2: { speed: 0.9 }, P3: { speed: 0.9 }, P4: { speed: 0.9 } };
		expect(planOf(four, {}, all).sentence).toBe(`Pump P1, Pump P2, Pump P3 and Pump P4 ${same}`);
		// Equal doubles only.
		expect(planOf(four, {}, { ...all, P2: { speed: 0.9000000000000001 } }).sentence).toBe(differ);
		// A speed control on one, at the same speed.
		const control = lineups.solve.solvedState.pumpResults.P1!.control;
		expect(control).toBeNull();
		expect(
			planOf(four, {}, { P3: { control: { mode: 'flow' } as PumpResult['control'] } }).sentence
		).toBe(differ);
		// Another curve.
		const other = edited(four, 'P2', (c) => ({ ...c, curveId: 'C2' }) as Component);
		expect(planOf(other).sentence).toBe(differ);
		// Only the pumps on count: P4 off on another curve.
		const offOther = edited(
			station(4, { off: ['P4'] }),
			'P4',
			(c) => ({ ...c, curveId: 'C2' }) as Component
		);
		expect(planOf(offOther).sentence).toBe(`Pump P1, Pump P2 and Pump P3 ${same}`);
		// Each pump off has none.
		expect(planOf(four, { preset: 'each' }).sentence).toBeNull();
	});

	it('says which group the names count when the card is not one parallel group of the frame', () => {
		// The default card: none.
		expect(planOn(lineups).frame).toBeNull();
		// A subset ticked by hand: the names count the whole station.
		const subset = planOn(lineups, { memberIds: ['P2', 'P3', 'P4'] });
		expect(subset.frame).toBe(
			'Names count every pump of the group Pump P1, Pump P2, Pump P3 and Pump P4.'
		);
		expect(items(subset)).toEqual([
			'3 of 4 running (Pump P4 off)',
			'2 of 4 running (Pump P3, Pump P4 off)'
		]);
		expect(subset.about).toMatch(
			/^Makes one scenario for each number of these pumps running, from 2 down to 1:/
		);
		// A station the finder does not suggest (seven pumps): each pump named on its own.
		const seven = planOf(station(7));
		expect(seven.frame).toBe('Names list each pump on its own.');
		expect(seven.add[0]!.name).toBe('Pump P7 off');
		expect(seven.add[1]!.name).toBe('Pump P6 off; Pump P7 off');
		// Each pump off's names are 4d's: no sentence.
		expect(planOn(lineups, { memberIds: ['P2', 'P3', 'P4'], preset: 'each' }).frame).toBeNull();
	});

	it('has the block’s, the stop order’s and the notice’s words', () => {
		expect(LINEUP_BLOCK_WORDS).toEqual({
			heading: 'Add cases',
			preset: 'Cases to add',
			cases: 'Cases:'
		});
		expect(LINEUP_PRESET_LABELS).toEqual({ running: 'By number running', each: 'Each pump off' });
		expect(LINEUP_UNDO_LABELS).toEqual({
			running: 'add cases by number running',
			each: 'add cases with one pump off'
		});
		const w = STOP_ORDER_WORDS;
		expect([
			w.hint,
			w.list,
			w.first,
			w.last,
			w.idle,
			w.atFirst,
			w.atLast,
			w.reset,
			w.resetHint
		]).toEqual([
			'The first in this list stops first. The cases below change as you move pumps.',
			'Stop order',
			' (stops first)',
			' (stays on in every case)',
			' (carries no flow in the base case)',
			'Already the first to stop.',
			'Already the last to stop.',
			'Default order',
			"The default: the last pump switched on in the group's list stops first."
		]);
		expect(w.earlier('Pump P1')).toBe('Stop Pump P1 earlier');
		expect(w.later('Pump P1')).toBe('Stop Pump P1 later');
		expect(w.moved('Pump P1', 2, 4)).toBe('Pump P1 is now number 2 of 4 to stop.');
		expect(w.resetDone('Pump P4')).toBe('Default order: Pump P4 stops first.');
		expect(lineupNotice('running', ['A, B', 'C'])).toBe(
			'Added 2 cases by number running: «A, B» and «C». Solve all solves every case not yet solved; Undo removes them.'
		);
		expect(lineupNotice('each', ['Pump PA off'])).toBe(addedNotice(['Pump PA off']));
	});
});

describe('lineupPlan: the plan’s summary and which pump each id is (pumps-results-layout.md §5.3, §6.2, S4)', () => {
	/** The fixture's three lineups as scenarios S1 to S3, the cases By number running makes. */
	const made = (count: number) =>
		withScenarios(withoutScenarios(lineups.project), lineups.project.scenarios!.slice(0, count));

	it('says what the plan holds and how much of it is made: to add, all made, some not made', () => {
		// To add: every case, or what is left.
		expect(planOn(lineups).summary).toBe('3 cases by number running: 3 to add');
		expect(planOn(lineups, { preset: 'each' }).summary).toBe(
			'4 cases with each pump off: 4 to add'
		);
		expect(planOn(lineups, { project: made(2) }).summary).toBe(
			'3 cases by number running: 1 to add'
		);
		// All made: the folded plan's words (nothing to add, every case a scenario).
		const all = planOn(lineups, { project: made(3) });
		expect(all.add).toEqual([]);
		expect(all.existing).toHaveLength(3);
		expect(all.summary).toBe('3 cases by number running: all 3 made');
		// One case, made: its count, not "all 1".
		const two = withCases(station(2), scenario(off('P2'), '1 of 2 running (Pump P2 off)'));
		expect(planOf(two).summary).toBe('1 case by number running: 1 made');
		// A case that is the base case's state is not made, and said so.
		expect(planOn(closedLeg).summary).toBe(
			"1 case by number running: 0 made, 1 not made (the base case's state)"
		);
		const idle = { P4: { status: 'no_flow', operatingFlow: 0 } } as const;
		const four = station(4);
		expect(planOf(four, {}, idle).summary).toBe('3 cases by number running: 2 to add');
		const someMade = withCases(
			four,
			scenario(off('P3', 'P4'), 'two off', 'S1'),
			scenario(off('P2', 'P3', 'P4'), 'three off', 'S2')
		);
		const plan = planOf(someMade, {}, idle);
		expect(plan.cases.map((c) => c.kind)).toEqual(['base_state', 'existing', 'existing']);
		expect(plan.summary).toBe(
			"3 cases by number running: 2 made, 1 not made (the base case's state)"
		);
	});

	it('names which pump each id is where the plan writes pumps by id: the condenser example, in the stop order', () => {
		const condenser = withScenarios(condenserWaterExample(), []);
		const plan = planOf(condenser);
		expect(plan.cases.map((c) => c.name)).toEqual([
			'5 of 6 running (P6 off)',
			'4 of 6 running (P5, P6 off)',
			'3 of 6 running (P4, P5, P6 off)',
			'2 of 6 running (P3, P4, P5, P6 off)',
			'1 of 6 running (P2, P3, P4, P5, P6 off)'
		]);
		expect(plan.ids).toBe(
			'In the names, P6 is Condenser water pump CWP-6, P5 is Condenser water pump CWP-5, P4 is Condenser water pump CWP-4, P3 is Condenser water pump CWP-3, P2 is Condenser water pump CWP-2 and P1 is Condenser water pump CWP-1.'
		);
		// The stop order moved: the line follows it, as its summary does.
		const moved = planOf(condenser, { savedOrder: ['P1', 'P6', 'P5', 'P4', 'P3', 'P2'] });
		expect(moved.stopOrder!.summary).toBe(
			'Stop order: P1 first, then P6, P5, P4 and P3; P2 stays on in every case'
		);
		expect(moved.ids).toMatch(/^In the names, P1 is Condenser water pump CWP-1, P6 is /);
		expect(moved.ids).toMatch(/ and P2 is Condenser water pump CWP-2\.$/);
		// A pump off in the base is in no stop order, and its id is in the names: it comes last.
		const p6Off = baseStatus(condenser, 'P6', 'off');
		const offPlan = planOf(p6Off);
		expect(offPlan.cases[0]!.name).toBe('4 of 6 running (P5, P6 off)');
		expect(offPlan.ids).toBe(
			'In the names, P5 is Condenser water pump CWP-5, P4 is Condenser water pump CWP-4, P3 is Condenser water pump CWP-3, P2 is Condenser water pump CWP-2, P1 is Condenser water pump CWP-1 and P6 is Condenser water pump CWP-6.'
		);
	});

	it('draws no id line where the names use labels, where every id is in its pump’s name, under Each pump off and under a gate', () => {
		// The names by labels ("3 of 4 running (Pump P4 off)"): nothing written by id.
		expect(planOn(lineups).ids).toBeNull();
		// By ids, each name holding its id ("Condenser water pump P1 of the north loop"): the line
		// would tell nothing.
		const named = (id: string) => `Condenser water pump ${id} of the north loop`;
		const long = station(4, { names: pumpIds(4).map(named) });
		const byIds = planOf(long);
		expect(byIds.cases[0]!.name).toBe('3 of 4 running (P4 off)');
		expect(byIds.stopOrder!.summary).toBe(
			'Stop order: P4 first, then P3 and P2; P1 stays on in every case'
		);
		expect(byIds.ids).toBeNull();
		// One name without its id: every id written is said.
		const one = renamedPump(long, 'P2', 'Condenser water pump of the north loop, second');
		expect(planOf(one).ids).toBe(
			'In the names, P4 is Condenser water pump P4 of the north loop, P3 is Condenser water pump P3 of the north loop, P2 is Condenser water pump of the north loop, second and P1 is Condenser water pump P1 of the north loop.'
		);
		// Each pump off: 4d's names, by the pumps' names.
		const condenser = withScenarios(condenserWaterExample(), []);
		expect(planOf(condenser, { preset: 'each' }).ids).toBeNull();
		// A gate: no plan, no summary.
		const stale = planOn(lineups, { base: { response: lineups.solve, stale: true } });
		expect(stale.gate).not.toBeNull();
		expect(stale.summary).toBeNull();
		expect(stale.ids).toBeNull();
	});

	it('has Add cases’ own words (§6.2), beside D24’s, which are unchanged', () => {
		expect(ADD_CASES_WORDS).toEqual({
			tag: 'Changes the project',
			planLead: 'The plan',
			nowTicked: "Now ticked: “Also show the other cases' station duties” (Group chart)."
		});
	});
});

describe('lineupPlan: Each pump off (4d’s cases; 4d’s plan tests moved here)', () => {
	// Moved from pump-group-one-off.test.ts with their assertions. The strings §7.12 lists under
	// "4d's strings that change" follow it, each named where it changes; the plan's cases now hold
	// the pumps they stop (`stopped`, several under By number running) where 4d held one `pumpId`,
	// and 4d's `notes` are the preview's items other than the cases added (notesOf).
	const station = stationOf(oneOffCase);
	const each = (project: Project, values: Partial<LineupPlanInput> = {}) =>
		lineupPlan({
			project,
			shownCase: null,
			station,
			memberIds: ['PA', 'PB'],
			base: { response: oneOffCase.solve, stale: false },
			preset: 'each',
			savedOrder: [],
			...values
		});
	/** 4d's notes: the items of the cases not added (existing, and the base case's state). */
	const notesOf = (plan: LineupPlan) =>
		plan.cases.filter((c) => c.kind !== 'add').map((c) => c.words);
	const withStatus = (response: SolveResponse, pumpId: string, value: PumpResult['status']) =>
		edit(response, { [pumpId]: { status: value } });

	it('makes a case per running pump, its only change that pump off, named and numbered', () => {
		const project = withoutScenarios(oneOffCase.project);
		const plan = each(project);
		expect(plan.gate).toBeNull();
		expect(plan.about).toBe(
			'Makes one scenario per pump running in the base case (Pump PA and Pump PB): the base case with that one pump off and nothing else changed. Pumps off in the base case stay off.'
		);
		expect(plan.add).toEqual([
			{ stopped: ['PA'], id: 'S1', name: 'Pump PA off' },
			{ stopped: ['PB'], id: 'S2', name: 'Pump PB off' }
		]);
		// §7.12: "Add cases with one pump off ({n})" becomes "Add {n} cases".
		expect(plan.label).toBe('Add 2 cases');
		expect(plan.refusal).toBeNull();
		expect(plan.showSolveAll).toBe(true);
		const made = withLineupCases(project, plan.add);
		// Exactly the fixture's S1 and S2, the scenarios the API solved.
		expect(made.scenarios).toEqual(oneOffCase.project.scenarios!.slice(0, 2));
		expect(made.scenarios!.map((s) => s.id)).toEqual(plan.add.map((a) => a.id));
		expect(addedNotice(plan.add.map((a) => a.name))).toBe(
			'Added 2 cases with one pump off: Pump PA off and Pump PB off. Solve all solves every case not yet solved; Undo removes them.'
		);
		expect(addedNotice(['Pump PA off'])).toBe(
			'Added 1 case with one pump off: Pump PA off. Solve all solves every case not yet solved; Undo removes them.'
		);
		expect(plan.notice).toBe(addedNotice(['Pump PA off', 'Pump PB off']));
		expect(plan.undoLabel).toBe('add cases with one pump off');
		expect(plan.stopOrder).toBeNull();
	});

	it('skips a pump whose case exists, whatever it is named, and refuses when every one exists', () => {
		const plan = each(oneOffCase.project);
		expect(plan.add).toEqual([]);
		expect(plan.existing).toEqual([
			{ stopped: ['PA'], scenarioId: 'S1', scenarioName: 'Pump PA off' },
			{ stopped: ['PB'], scenarioId: 'S2', scenarioName: 'Pump PB off' }
		]);
		// §7.12: the note "{name} has its case already: {found.name}." becomes the preview item
		// "{offName}: already a scenario, «{other}» ({id})", its short form when the names are equal
		// (§7.7).
		expect(notesOf(plan)).toEqual([
			'Pump PA off: already a scenario (S1)',
			'Pump PB off: already a scenario (S2)'
		]);
		expect(plan.refusal).toBe(
			'Every case with one pump off already exists: Pump PA off and Pump PB off.'
		);
		// §7.12: "Add cases with one pump off" becomes "Add cases".
		expect(plan.label).toBe('Add cases');
		// Renamed, it is still PA's case.
		const renamed = structuredClone(oneOffCase.project);
		renamed.scenarios![0]!.name = 'N-1 (PA)';
		expect(each(renamed).existing[0]).toEqual({
			stopped: ['PA'],
			scenarioId: 'S1',
			scenarioName: 'N-1 (PA)'
		});
		expect(notesOf(each(renamed))[0]).toBe('Pump PA off: already a scenario, «N-1 (PA)» (S1)');
	});

	it('takes the first free ids on the growing project', () => {
		const project = withScenarios(withoutScenarios(oneOffCase.project), [
			{ id: 'S1', name: 'Winter', overrides: [] }
		]);
		const plan = each(project);
		expect(plan.add.map((a) => a.id)).toEqual(['S2', 'S3']);
		const made = withLineupCases(project, plan.add);
		expect(made.scenarios!.map((s) => [s.id, s.name])).toEqual([
			['S1', 'Winter'],
			['S2', 'Pump PA off'],
			['S3', 'Pump PB off']
		]);
	});

	it('refuses past the scenario limit with the count', () => {
		const nineteen: Scenario[] = Array.from({ length: 19 }, (_, i) => ({
			id: `S${i + 1}`,
			name: `Case ${i + 1}`,
			overrides: []
		}));
		const plan = each(withScenarios(withoutScenarios(oneOffCase.project), nineteen));
		expect(MAX_SCENARIOS).toBe(20);
		expect(plan.refusal).toBe(
			'Adding 2 cases would make 21 scenarios; a project holds at most 20 scenarios.'
		);
		// §7.12: "Add cases with one pump off ({n})" becomes "Add {n} cases".
		expect(plan.label).toBe('Add 2 cases');
		// At the limit, not past it: 18 scenarios and 2 cases make 20, which a project holds.
		const atLimit = each(
			withScenarios(withoutScenarios(oneOffCase.project), nineteen.slice(0, 18))
		);
		expect(atLimit.add).toHaveLength(2);
		expect(atLimit.refusal).toBeNull();
		expect(atLimit.label).toBe('Add 2 cases');
	});

	it('tells two pumps of the same name apart by their ids, in the cases it makes and its words', () => {
		// Synthetic: a duty and a standby unit both named "Booster pump" (names need not be unique).
		const project = withoutScenarios(oneOffCase.project);
		for (const c of project.components) if (c.type === 'pump') c.name = 'Booster pump';
		const plan = each(project);
		expect(plan.add).toEqual([
			{ stopped: ['PA'], id: 'S1', name: 'Booster pump (PA) off' },
			{ stopped: ['PB'], id: 'S2', name: 'Booster pump (PB) off' }
		]);
		expect(plan.about).toBe(
			'Makes one scenario per pump running in the base case (Booster pump (PA) and Booster pump (PB)): the base case with that one pump off and nothing else changed. Pumps off in the base case stay off.'
		);
		const made = withLineupCases(project, plan.add);
		const again = each(made);
		// §7.12: "{name} has its case already: {found.name}." becomes the preview item (§7.7's short
		// form: the names are equal).
		expect(notesOf(again)).toEqual([
			'Booster pump (PA) off: already a scenario (S1)',
			'Booster pump (PB) off: already a scenario (S2)'
		]);
		expect(new Set(notesOf(again)).size).toBe(2);
		// A name only one member has keeps its plain words.
		const one = structuredClone(project);
		one.components.find((c) => c.id === 'PB')!.name = 'Pump PB';
		expect(each(one).add.map((a) => a.name)).toEqual(['Booster pump off', 'Pump PB off']);
	});

	it('tells a case with one pump off by sameCase (4d’s isOnePumpOff replaced)', () => {
		const [s1, s2, s3, s4] = oneOffCase.project.scenarios!;
		const project = oneOffCase.project;
		const alone = (pumpId: string): Scenario => ({
			id: 'X',
			name: 'X',
			overrides: [offOverride(pumpId)]
		});
		expect(sameCase(project, s1, alone('PA'))).toBe(true);
		expect(sameCase(project, s2, alone('PB'))).toBe(true);
		expect(sameCase(project, s1, alone('PB'))).toBe(false);
		expect(sameCase(project, s3, alone('PA'))).toBe(false);
		// Two changes, or a status on.
		expect(sameCase(project, s4, alone('PA'))).toBe(false);
		const on: Scenario = {
			id: 'S9',
			name: 'On',
			overrides: [{ kind: 'component', componentId: 'PA', field: 'status', value: 'on' }]
		};
		expect(sameCase(project, on, alone('PA'))).toBe(false);
		expect(offOverride('PA')).toEqual({
			kind: 'component',
			componentId: 'PA',
			field: 'status',
			value: 'off'
		});
	});

	it('gives no case to a pump on but carrying no flow, and says why', () => {
		const c = solvedCase('one-off-dead-headed');
		const plan = lineupPlan({
			project: withoutScenarios(c.project),
			shownCase: null,
			station: stationOf(c),
			memberIds: c.memberIds,
			base: { response: c.solve, stale: false },
			preset: 'each',
			savedOrder: []
		});
		expect(plan.add).toEqual([{ stopped: ['PA'], id: 'S1', name: 'Pump PA off' }]);
		expect(plan.idle).toEqual(['PB']);
		// §7.12: the idle note becomes the preview item.
		expect(notesOf(plan)).toEqual([
			"Pump PB off: not made, the base case's state (Pump PB carries no flow in the base case)"
		]);
		expect(plan.about).toBe(
			'Makes one scenario per pump running in the base case (Pump PA): the base case with that one pump off and nothing else changed. Pumps off in the base case stay off.'
		);
		// The fixture's S1 is what the add makes.
		expect(withLineupCases(withoutScenarios(c.project), plan.add).scenarios).toEqual(
			c.project.scenarios
		);
	});

	it('skips lineups-closed-leg’s PB, running at 0.0 (the flow, not the state word)', () => {
		const plan = planOn(closedLeg, { preset: 'each' });
		expect(plan.add).toEqual([{ stopped: ['PA'], id: 'S1', name: 'Pump PA off' }]);
		expect(plan.idle).toEqual(['PB']);
		expect(items(plan)).toEqual([
			'Pump PA off',
			"Pump PB off: not made, the base case's state (Pump PB carries no flow in the base case)"
		]);
		expect(plan.about).toBe(
			'Makes one scenario per pump running in the base case (Pump PA): the base case with that one pump off and nothing else changed. Pumps off in the base case stay off.'
		);
	});

	it('is offered for a parallel station from the base case, current, with two pumps on, one carrying flow', () => {
		const project = withoutScenarios(oneOffCase.project);
		const series = stationOf(solvedCase('series'));
		const mixed = { ...station, arrangement: 'mixed' as const };
		const gate = (values: Partial<LineupPlanInput>) => each(project, values);
		// §7.12: gate 1's words become §7.2 row 1's.
		expect(gate({ station: series }).gate).toBe(
			'Cases are added here for pumps in parallel only: in series a stopped pump blocks the line in this app (a stopped pump passing flow is not modelled), so the station would carry no flow.'
		);
		expect(gate({ station: series }).showSolveAll).toBe(false);
		// §7.12: gate 2 likewise (row 2).
		expect(gate({ station: mixed }).gate).toBe(
			'Cases are added here for pumps in parallel only; this station is mixed: neither all in parallel nor all in series.'
		);
		const shown = gate({ project: oneOffCase.project, shownCase: 'S3' });
		// §7.12: gate 3's words become row 3's.
		expect(shown.gate).toBe(
			'Cases are made from the base case: show the base case to add them. To study Delivery tank 5 m higher with pumps off, duplicate it in Scenarios and set those pumps off there.'
		);
		expect(shown.showSolveAll).toBe(false);
		// The arrangement first: a series station in a scenario says why in series.
		expect(gate({ station: series, shownCase: 'S3', project: oneOffCase.project }).gate).toMatch(
			/^Cases are added here for pumps in parallel only: in series/
		);
		const stale = gate({ base: { response: oneOffCase.solve, stale: true } });
		expect(stale.gate).toBe(
			"The base case's results are out of date: solve it again, so the pumps that run are read from the project as it is now."
		);
		expect(stale.showSolveAll).toBe(true);
		const offPlan = gate({
			base: { response: withStatus(oneOffCase.solve, 'PB', 'off'), stale: false }
		});
		expect(offPlan.gate).toBe(
			'Needs two or more of these pumps switched on in the base case: Pump PB is off.'
		);
		expect(offPlan.showSolveAll).toBe(true);
		const bothOff = gate({
			base: {
				response: withStatus(withStatus(oneOffCase.solve, 'PB', 'off'), 'PA', 'off'),
				stale: false
			}
		});
		expect(bothOff.gate).toBe(
			'Needs two or more of these pumps switched on in the base case: Pump PA and Pump PB are off.'
		);
		const none = gate({
			base: {
				response: edit(oneOffCase.solve, {
					PA: { status: 'no_flow', operatingFlow: 0 },
					PB: { status: 'no_flow', operatingFlow: 0 }
				}),
				stale: false
			}
		});
		// §7.12: gate 6's words become row 6's.
		expect(none.gate).toBe(
			'No pump of the group carries flow in the base case, so switching pumps off changes nothing.'
		);
		expect(none.showSolveAll).toBe(true);
		for (const plan of [offPlan, none, stale, shown]) expect(plan.add).toEqual([]);
		// No station: no block.
		expect(gate({ station: null })).toMatchObject({ gate: null, add: [], showSolveAll: false });
	});
});

// ---------------------------------------------------------------------------------------------
// §4.6 lineupChartPriority
// ---------------------------------------------------------------------------------------------

describe('lineupChartPriority', () => {
	const keysOf = (project: Project, base = false) => [
		...(base ? [{ key: '', caseId: null }] : []),
		...scenariosOf(project).map((s) => ({ key: s.id, caseId: s.id }))
	];

	it('six pumps with both presets: one lineup of each number running first, 5 to 1, then one more', () => {
		const six = station(6);
		const running = withLineupCases(six, planOf(six).add);
		const both = withLineupCases(running, planOf(running, { preset: 'each' }).add);
		expect(namesOf(both)).toEqual([
			'5 of 6 running (Pump P6 off)',
			'4 of 6 running (Pump P5, Pump P6 off)',
			'3 of 6 running (Pump P4, Pump P5, Pump P6 off)',
			'2 of 6 running (Pump P3, Pump P4, Pump P5, Pump P6 off)',
			'1 of 6 running (Pump P2, Pump P3, Pump P4, Pump P5, Pump P6 off)',
			'Pump P1 off',
			'Pump P2 off',
			'Pump P3 off',
			'Pump P4 off',
			'Pump P5 off'
		]);
		const order = lineupChartPriority(keysOf(both), both, pumpIds(6));
		expect(order).toEqual(['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10']);
		const on = (id: string) =>
			pumpLineup(
				scenariosOf(both).find((s) => s.id === id),
				both,
				pumpIds(6)
			).on.length;
		expect(order.slice(0, 6).map(on)).toEqual([5, 4, 3, 2, 1, 5]);
		// Each pump off first in case order: the first of each count still leads.
		const eachFirst = withLineupCases(
			withLineupCases(six, planOf(six, { preset: 'each' }).add),
			[]
		);
		const thenRunning = withLineupCases(eachFirst, planOf(eachFirst).add);
		const mixed = lineupChartPriority(keysOf(thenRunning), thenRunning, pumpIds(6));
		const onIn = (id: string) =>
			pumpLineup(
				scenariosOf(thenRunning).find((s) => s.id === id),
				thenRunning,
				pumpIds(6)
			).on.length;
		expect(mixed.slice(0, 6).map(onIn)).toEqual([5, 4, 3, 2, 1, 5]);
		expect(mixed[0]).toBe('S1');
	});

	it('puts the other lineups most running first, then in case order (step 2): they decide the six charted', () => {
		// By number running, again after a reorder (P1 first), then Each pump off: the counts in
		// case order are 3, 2, 1, 3, 2, 1, 3 and 3 running, so case order is not count order.
		const four = station(4);
		const running = withLineupCases(four, planOf(four).add);
		const reordered = withLineupCases(
			running,
			planOf(running, { savedOrder: ['P1', 'P4', 'P3', 'P2'] }).add
		);
		const all = withLineupCases(reordered, planOf(reordered, { preset: 'each' }).add);
		expect(namesOf(all)).toEqual([
			'3 of 4 running (Pump P4 off)',
			'2 of 4 running (Pump P3, Pump P4 off)',
			'1 of 4 running (Pump P2, Pump P3, Pump P4 off)',
			'3 of 4 running (Pump P1 off)',
			'2 of 4 running (Pump P1, Pump P4 off)',
			'1 of 4 running (Pump P1, Pump P3, Pump P4 off)',
			'Pump P2 off',
			'Pump P3 off'
		]);
		const order = lineupChartPriority(keysOf(all), all, pumpIds(4));
		expect(order).toEqual(['S1', 'S2', 'S3', 'S4', 'S7', 'S8', 'S5', 'S6']);
		// The six on the chart: the first of each count, then the other cases with 3 running.
		expect(chartKeys(keysOf(all), all, pumpIds(4), [])).toEqual([
			'S1',
			'S2',
			'S3',
			'S4',
			'S7',
			'S8'
		]);
	});

	it('counts the base when it is another case, with its pumps on', () => {
		const project = withLineupCases(station(3), planOf(station(3)).add);
		expect(lineupChartPriority(keysOf(project, true), project, pumpIds(3))).toEqual([
			'',
			'S1',
			'S2'
		]);
	});

	it('leaves a status-only scenario equal to the base, and any other change, among the other cases', () => {
		const project = withCases(
			station(3),
			scenario([status('P1', 'on')], 'Same as the base', 'S1'),
			scenario([...off('P3'), level('A1', 5)], 'Winter', 'S2'),
			scenario(off('P2', 'P3'), '1 of 3 running (Pump P2, Pump P3 off)', 'S3'),
			scenario(off('P3'), '2 of 3 running (Pump P3 off)', 'S4')
		);
		expect(lineupChartPriority(keysOf(project), project, pumpIds(3))).toEqual([
			'S4',
			'S3',
			'S1',
			'S2'
		]);
	});

	it('orders 4d’s one-off project: one of each count, most running first, then the rest', () => {
		// 4d's chartPriority test, on the new order (§4.6 replaces chartPriority): S3 "Tank" first
		// in the scenarios, then S1 and S2 (one pump off each, 1 running) and S4 (both off, 0).
		const project = withScenarios(structuredClone(oneOffCase.project), [
			{ id: 'S3', name: 'Tank', overrides: [] },
			...oneOffCase.project.scenarios!.filter((s) => s.id !== 'S3')
		]);
		const order = [
			{ key: '', caseId: null },
			...['S1', 'S2', 'S3', 'S4'].map((id) => ({ key: id, caseId: id }))
		];
		expect(lineupChartPriority(order, project, ['PA', 'PB'])).toEqual(['', 'S1', 'S4', 'S2', 'S3']);
		// A member no longer in the group: a case that changes another pump is no lineup of these.
		expect(lineupChartPriority(order, project, ['PA'])).toEqual(['', 'S1', 'S2', 'S3', 'S4']);
	});
});
