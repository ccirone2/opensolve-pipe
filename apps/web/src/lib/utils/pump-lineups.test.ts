/**
 * Pump lineups, slice L1a (CLAUDE.md D24, proposal pump-lineups.md §4 and §10.1 "L1a, unit"): the
 * reader (pumpLineup), the frame (lineupGroups, frameKey), the same case (effectiveChanges,
 * sameCase), the names (lineupName) and the names that follow (followLineupNames, renameNotice).
 * Every string is checked word for word. The projects are made-up test inputs (only the
 * components' kinds, ports, statuses, names and connections matter here), the examples', and the
 * shared fixture's (__fixtures__/pump-groups-input.json, the API's own projects).
 */
import { describe, expect, it, vi } from 'vitest';
import type { Component, Override, Project, Scenario } from '$lib/api/types';
import { projectWith } from '$lib/testing/helpers';
import {
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
import { offName } from './pump-group-one-off';
import { suggestGroups } from './pump-groups';
import {
	effectiveChanges,
	followLineupNames,
	frameKey,
	LINEUP_NAME_BUDGET,
	lineupGroups,
	lineupName,
	pumpLineup,
	renameNotice,
	sameCase,
	solvedCaseWords,
	type LineupGroup
} from './pump-lineups';
import { copyName, SCENARIO_NAME_LIMIT, scenariosOf, withScenarios } from './scenarios';

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
			scenario([], 'Scenario 2 (copy)', 'S5')
		);
		const edits = [
			pressed(before, 'S1', off('P2', 'P4')),
			pressed(before, 'S4', [level('A1', 5), ...off('P2')]),
			pressed(before, 'S5', off('P2')),
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
