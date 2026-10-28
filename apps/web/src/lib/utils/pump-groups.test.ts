/**
 * The groups the Pumps together card suggests (proposal pump-groups.md §4) and the words for the
 * API's NOT_A_STATION reasons (§6.2). The projects of the shared fixture are the API's
 * (__fixtures__/pump-groups-input.json, apps/api/tests/fixtures/pump_groups_input.py); the
 * others are hand-built topologies (made-up test inputs: only the components' kinds, ports and
 * connections matter).
 */
import { describe, expect, it } from 'vitest';
import type { Component, Project, TopologyIssue } from '$lib/api/types';
import { link, projectWith } from '$lib/testing/helpers';
import fixture from './__fixtures__/pump-groups-input.json';
import {
	defaultGroup,
	MAX_GROUP_PUMPS,
	refusalWords,
	suggestGroups,
	wordsText,
	type GroupSuggestion
} from './pump-groups';

const port = (id: string) => ({ id, nominalSize: 0.1016 });
const comp = (value: Record<string, unknown>) => value as unknown as Component;
const reservoir = (id: string, ports = 1) =>
	comp({
		id,
		name: `Tank ${id}`,
		type: 'reservoir',
		elevation: 0,
		liquidLevel: 1,
		surfacePressure: 0,
		ports: Array.from({ length: ports }, (_, i) => port(`port_${i + 1}`))
	});
const tee = (id: string) =>
	comp({
		id,
		name: `Tee ${id}`,
		type: 'branch',
		branchType: 'tee',
		elevation: 0,
		ports: ['run_inlet', 'run_outlet', 'branch'].map(port)
	});
const pump = (id: string) =>
	comp({
		id,
		name: `Pump ${id}`,
		type: 'pump',
		elevation: 0,
		curveId: 'C1',
		speed: 1,
		status: 'on',
		ports: ['suction', 'discharge'].map(port)
	});
const valve = (id: string) =>
	comp({
		id,
		name: `Valve ${id}`,
		type: 'valve',
		valveType: 'gate',
		elevation: 0,
		ports: ['inlet', 'outlet'].map(port)
	});
const assigned = (id: string) =>
	comp({
		id,
		name: `Demand ${id}`,
		type: 'assigned_flow',
		elevation: 0,
		flow: 0.001,
		ports: [port('port_1')]
	});
/** A pipe "A:port" → "B:port". */
const pipe = (id: string, from: string, to: string) =>
	link(id, from.split(':') as [string, string], to.split(':') as [string, string]);

const ids = (groups: readonly GroupSuggestion[]) => groups.map((g) => g.pumpIds);

interface FixtureCase {
	name: string;
	project: unknown;
	memberIds: string[];
	solve: { solvedState: { pumpResults: Record<string, unknown> } };
}
const cases = fixture.cases as unknown as FixtureCase[];
const fixtureCase = (name: string) => cases.find((c) => c.name === name)!;
const suggestedIn = (name: string) => {
	const c = fixtureCase(name);
	return suggestGroups(c.project as Project, Object.keys(c.solve.solvedState.pumpResults));
};

/** The parallel reference topology: R1 → T1, PA and PB legs, T2 → R2. */
function parallel(): { components: Component[]; connections: ReturnType<typeof pipe>[] } {
	return {
		components: [reservoir('R1'), tee('T1'), pump('PA'), pump('PB'), tee('T2'), reservoir('R2')],
		connections: [
			pipe('L1', 'R1:port_1', 'T1:run_inlet'),
			pipe('LA1', 'T1:run_outlet', 'PA:suction'),
			pipe('LA2', 'PA:discharge', 'T2:run_inlet'),
			pipe('LB1', 'T1:branch', 'PB:suction'),
			pipe('LB2', 'PB:discharge', 'T2:branch'),
			pipe('L2', 'T2:run_outlet', 'R2:port_1')
		]
	};
}

describe('suggested groups on the fixture topologies (the API answered for each)', () => {
	it('finds two pumps between two tees, with ideal or Crane tees, on or off, held or not', () => {
		for (const name of ['parallel-ideal', 'parallel-crane', 'dead-headed', 'off']) {
			expect(suggestedIn(name), name).toEqual([{ pumpIds: ['PA', 'PB'], kind: 'parallel' }]);
		}
	});

	it('finds the whole tee ladder, and the two pumps between the inner tees', () => {
		expect(suggestedIn('ladder')).toEqual([
			{ pumpIds: ['P1', 'P2', 'P3'], kind: 'parallel' },
			{ pumpIds: ['P2', 'P3'], kind: 'parallel' }
		]);
	});

	it('finds pumps in series on one chain, speed-controlled or not', () => {
		expect(suggestedIn('series')).toEqual([{ pumpIds: ['PA', 'PB'], kind: 'series' }]);
		expect(suggestedIn('controlled')).toEqual([{ pumpIds: ['PA', 'PB'], kind: 'series' }]);
	});

	it('suggests nothing the API refuses: a tank on the header, pumps facing each other', () => {
		expect(suggestedIn('refused')).toEqual([]);
		expect(suggestedIn('refused-reversed')).toEqual([]);
	});

	it('every suggestion on the fixture is a group the API accepted', () => {
		for (const c of cases) {
			const status = (c as unknown as { groupCurve: { status: number } }).groupCurve.status;
			for (const group of suggestedIn(c.name)) {
				if (group.pumpIds.join() !== c.memberIds.join()) continue;
				expect(status, c.name).toBe(200);
			}
		}
	});
});

describe('suggested groups on hand-built topologies', () => {
	it('finds pumps drawing from one reservoir through separate ports', () => {
		const { components, connections } = parallel();
		const project = projectWith(
			[reservoir('R1', 2), ...components.filter((c) => !['R1', 'T1'].includes(c.id))],
			[
				pipe('LA1', 'R1:port_1', 'PA:suction'),
				pipe('LB1', 'R1:port_2', 'PB:suction'),
				...connections.filter((c) => !['L1', 'LA1', 'LB1'].includes(c.id))
			]
		);
		expect(ids(suggestGroups(project, ['PA', 'PB']))).toEqual([['PA', 'PB']]);
	});

	it('finds pumps between two reservoirs, each through its own ports', () => {
		const project = projectWith(
			[reservoir('R1', 2), pump('PA'), pump('PB'), reservoir('R2', 2)],
			[
				pipe('A1', 'R1:port_1', 'PA:suction'),
				pipe('A2', 'PA:discharge', 'R2:port_1'),
				pipe('B1', 'R1:port_2', 'PB:suction'),
				pipe('B2', 'PB:discharge', 'R2:port_2')
			]
		);
		expect(suggestGroups(project, ['PA', 'PB'])).toEqual([
			{ pumpIds: ['PA', 'PB'], kind: 'parallel' }
		]);
	});

	it('finds series pumps through a valve, and only pumps facing the same way', () => {
		const line = (reversed: boolean) =>
			projectWith(
				[reservoir('R1'), pump('PA'), valve('V1'), pump('PB'), reservoir('R2')],
				[
					pipe('L1', 'R1:port_1', 'PA:suction'),
					pipe('L2', 'PA:discharge', 'V1:inlet'),
					pipe('L3', 'V1:outlet', reversed ? 'PB:discharge' : 'PB:suction'),
					pipe('L4', reversed ? 'PB:suction' : 'PB:discharge', 'R2:port_1')
				]
			);
		expect(suggestGroups(line(false), ['PA', 'PB'])).toEqual([
			{ pumpIds: ['PA', 'PB'], kind: 'series' }
		]);
		expect(suggestGroups(line(true), ['PA', 'PB'])).toEqual([]);
	});

	it('finds a 2 × 2 station and each of its series pairs, the largest first', () => {
		const project = projectWith(
			[
				reservoir('R1'),
				tee('T1'),
				pump('A1'),
				pump('A2'),
				pump('B1'),
				pump('B2'),
				tee('T2'),
				reservoir('R2')
			],
			[
				pipe('L1', 'R1:port_1', 'T1:run_inlet'),
				pipe('a1', 'T1:run_outlet', 'A1:suction'),
				pipe('a2', 'A1:discharge', 'A2:suction'),
				pipe('a3', 'A2:discharge', 'T2:run_inlet'),
				pipe('b1', 'T1:branch', 'B1:suction'),
				pipe('b2', 'B1:discharge', 'B2:suction'),
				pipe('b3', 'B2:discharge', 'T2:branch'),
				pipe('L2', 'T2:run_outlet', 'R2:port_1')
			]
		);
		expect(suggestGroups(project, ['A1', 'A2', 'B1', 'B2'])).toEqual([
			{ pumpIds: ['A1', 'A2', 'B1', 'B2'], kind: 'parallel' },
			{ pumpIds: ['A1', 'A2'], kind: 'series' },
			{ pumpIds: ['B1', 'B2'], kind: 'series' }
		]);
	});

	it('does not suggest pumps on two reservoirs', () => {
		const { components, connections } = parallel();
		const project = projectWith(
			[reservoir('R3'), ...components.filter((c) => c.id !== 'T1')],
			[
				pipe('LA1', 'R1:port_1', 'PA:suction'),
				pipe('LB1', 'R3:port_1', 'PB:suction'),
				...connections.filter((c) => !['L1', 'LA1', 'LB1'].includes(c.id))
			]
		);
		expect(suggestGroups(project, ['PA', 'PB'])).toEqual([]);
	});

	it('does not suggest pumps with an assigned flow tapped between them', () => {
		const { components, connections } = parallel();
		const project = projectWith(
			[...components, tee('T3'), assigned('A1')],
			[
				...connections.filter((c) => c.id !== 'LA2'),
				pipe('LA2', 'PA:discharge', 'T3:run_inlet'),
				pipe('LA3', 'T3:run_outlet', 'T2:run_inlet'),
				pipe('LD', 'T3:branch', 'A1:port_1')
			]
		);
		expect(suggestGroups(project, ['PA', 'PB'])).toEqual([]);
	});

	it('does not suggest pumps a bypass joins without a pump (the API finds them mixed)', () => {
		// T1:branch → T3 → PB, T3:branch → bypass → T4 on the discharge line.
		const { components, connections } = parallel();
		const project = projectWith(
			[...components, tee('T3'), tee('T4')],
			[
				...connections.filter((c) => !['LB1', 'L2'].includes(c.id)),
				pipe('LB0', 'T1:branch', 'T3:run_inlet'),
				pipe('LB1', 'T3:run_outlet', 'PB:suction'),
				pipe('BY', 'T3:branch', 'T4:branch'),
				pipe('L2', 'T2:run_outlet', 'T4:run_inlet'),
				pipe('L3', 'T4:run_outlet', 'R2:port_1')
			]
		);
		expect(suggestGroups(project, ['PA', 'PB'])).toEqual([]);
	});

	it('does not suggest pumps with an active PRV or PSV between their tees', () => {
		const { components, connections } = parallel();
		const prv = (status: string) =>
			comp({
				id: 'V1',
				name: 'PRV V1',
				type: 'valve',
				valveType: 'prv',
				status,
				setpoint: 2e5,
				elevation: 0,
				ports: ['inlet', 'outlet'].map(port)
			});
		const withValve = (status: string) =>
			projectWith(
				[...components, prv(status)],
				[
					...connections.filter((c) => c.id !== 'LA2'),
					pipe('LA2', 'PA:discharge', 'V1:inlet'),
					pipe('LA3', 'V1:outlet', 'T2:run_inlet')
				]
			);
		expect(suggestGroups(withValve('active'), ['PA', 'PB'])).toEqual([]);
		// Failed open or closed, it is no pressure control: the API accepts the station.
		expect(ids(suggestGroups(withValve('failed_open'), ['PA', 'PB']))).toEqual([['PA', 'PB']]);
	});

	it('does not suggest pumps in series whose chain leads nowhere at one end', () => {
		// R1 → PA → PB → T1, whose other ports end at plugs: no flow passes through them.
		const plug = (id: string) =>
			comp({ id, name: `Plug ${id}`, type: 'plug', elevation: 0, ports: [port('port_1')] });
		const into = (end: Component[], links: ReturnType<typeof pipe>[]) =>
			projectWith(
				[reservoir('R1'), pump('PA'), pump('PB'), ...end],
				[pipe('L1', 'R1:port_1', 'PA:suction'), pipe('L2', 'PA:discharge', 'PB:suction'), ...links]
			);
		const deadEnd = into(
			[tee('T1'), plug('P1'), plug('P2')],
			[
				pipe('L3', 'PB:discharge', 'T1:run_inlet'),
				pipe('L4', 'T1:run_outlet', 'P1:port_1'),
				pipe('L5', 'T1:branch', 'P2:port_1')
			]
		);
		expect(suggestGroups(deadEnd, ['PA', 'PB'])).toEqual([]);
		const onward = into([reservoir('R2')], [pipe('L3', 'PB:discharge', 'R2:port_1')]);
		expect(ids(suggestGroups(onward, ['PA', 'PB']))).toEqual([['PA', 'PB']]);
	});

	it('suggests only pumps with results, and never more than six', () => {
		const n = MAX_GROUP_PUMPS + 1;
		const pumps = Array.from({ length: n }, (_, i) => pump(`P${i + 1}`));
		const project = projectWith(
			[reservoir('R1', n), ...pumps, reservoir('R2', n)],
			pumps.flatMap((p, i) => [
				pipe(`S${i + 1}`, `R1:port_${i + 1}`, `${p.id}:suction`),
				pipe(`D${i + 1}`, `${p.id}:discharge`, `R2:port_${i + 1}`)
			])
		);
		expect(
			suggestGroups(
				project,
				pumps.map((p) => p.id)
			)
		).toEqual([]);
		expect(suggestGroups(project, ['P1'])).toEqual([]);
	});

	it('finds every station along a long line of them, quickly, at the model’s size limit', () => {
		// 249 stations in series along one main, 998 components (the model allows 1,000):
		// R1 → (T, two pumps, T) × 249 → R2.
		const components: Component[] = [reservoir('R1'), reservoir('R2')];
		const connections: ReturnType<typeof pipe>[] = [];
		let from = 'R1:port_1';
		for (let k = 0; k < 249; k++) {
			const [s, d, a, b] = [`S${k}`, `D${k}`, `A${k}`, `B${k}`];
			components.push(tee(s), pump(a), pump(b), tee(d));
			connections.push(
				pipe(`in${k}`, from, `${s}:run_inlet`),
				pipe(`a${k}s`, `${s}:run_outlet`, `${a}:suction`),
				pipe(`a${k}d`, `${a}:discharge`, `${d}:run_inlet`),
				pipe(`b${k}s`, `${s}:branch`, `${b}:suction`),
				pipe(`b${k}d`, `${b}:discharge`, `${d}:branch`)
			);
			from = `${d}:run_outlet`;
		}
		connections.push(pipe('out', from, 'R2:port_1'));
		const project = projectWith(components, connections);
		const started = performance.now();
		const groups = suggestGroups(
			project,
			components.filter((c) => c.type === 'pump').map((c) => c.id)
		);
		expect(performance.now() - started).toBeLessThan(5000);
		expect(groups).toHaveLength(249);
		expect(groups[37]).toEqual({ pumpIds: ['A37', 'B37'], kind: 'parallel' });
	});
});

describe('the default group', () => {
	const suggestions: GroupSuggestion[] = [
		{ pumpIds: ['P1', 'P2', 'P3'], kind: 'parallel' },
		{ pumpIds: ['P4', 'P5'], kind: 'series' }
	];
	it('is the first suggestion holding the pump viewed, else the first, else none', () => {
		expect(defaultGroup(suggestions, 'P5')).toEqual(['P4', 'P5']);
		expect(defaultGroup(suggestions, 'P2')).toEqual(['P1', 'P2', 'P3']);
		expect(defaultGroup(suggestions, 'P9')).toEqual(['P1', 'P2', 'P3']);
		expect(defaultGroup([], 'P1')).toEqual([]);
	});
});

describe('why the pumps do not form a station, in words', () => {
	const { components, connections } = parallel();
	const project = projectWith(
		[...components, reservoir('R4'), assigned('A1'), valve('V1'), pump('PC')],
		connections
	);
	const issue = (code: string, componentIds: string[]): TopologyIssue => ({
		code,
		message: `server words for ${code}`,
		componentIds,
		connectionIds: []
	});
	const told = (code: string, componentIds: string[], members = ['PA', 'PB']) =>
		wordsText(refusalWords(issue(code, componentIds), members, project));

	it('names each element, linked, for every reason the API gives', () => {
		const words = refusalWords(issue('FIXED_HEAD_INSIDE', ['R4']), ['PA', 'PB'], project);
		expect(words[0]).toEqual({ id: 'R4', name: 'Tank R4' });
		expect(told('FIXED_HEAD_INSIDE', ['R4'])).toBe(
			'Tank R4 connects the pumps to a fixed head a third time: a station meets the rest of the network at exactly two places, its inlet and its outlet, with no reservoir or reference node between them.'
		);
		expect(told('FIXED_HEAD_INSIDE', ['R2', 'R4'])).toBe(
			'The pumps meet the fixed heads of Tank R2 and Tank R4, one place more than a station has: it meets the rest of the network at exactly two places, its inlet and its outlet, with no reservoir or reference node between them.'
		);
		expect(told('NO_SEPARATING_PORTS', ['T1', 'T2', 'R4'])).toBe(
			'Pump PA and Pump PB meet the rest of the network at Tee T1, Tee T2 and Tank R4, not at exactly two places: a station meets it only at its inlet and its outlet, with no other pump, reservoir, reference node or assigned flow between them.'
		);
		expect(told('ASSIGNED_FLOW_INSIDE', ['A1'])).toBe(
			'The assigned flow at Demand A1 enters or leaves the network between the pumps and the rest of it: a station holds no assigned flow between its inlet and its outlet.'
		);
		expect(told('OTHER_PUMP_INSIDE', ['PC'])).toBe(
			'Pump PC lies between the pumps and the rest of the network but is not in the group: tick it too, or choose other pumps.'
		);
		expect(told('MEMBER_REVERSED', ['PA', 'PB'])).toBe(
			'Pump PA and Pump PB face opposite ways between the station’s inlet and outlet: a station’s pumps all deliver from its inlet to its outlet.'
		);
		expect(told('MEMBER_REVERSED', ['PB'], ['PA', 'PB', 'PC'])).toBe(
			'Pump PB faces against the other pumps, from the station’s outlet to its inlet: a station’s pumps all deliver from its inlet to its outlet.'
		);
		expect(told('PRESSURE_CONTROL_INSIDE', ['V1'])).toBe(
			'Valve V1 is inside the station and holds a pressure (an active PRV or PSV): its setpoint is a pressure, not a head difference, so the station alone has no group curve that depends on its rise only.'
		);
		expect(told('SOMETHING_NEW', ['PA'])).toBe('server words for SOMETHING_NEW');
	});

	it('says whether different boundaries are at the suctions or the discharges', () => {
		const twoTanks = projectWith(
			[reservoir('R1'), reservoir('R3'), pump('PA'), pump('PB'), tee('T2'), reservoir('R2')],
			[
				pipe('LA1', 'R1:port_1', 'PA:suction'),
				pipe('LB1', 'R3:port_1', 'PB:suction'),
				pipe('LA2', 'PA:discharge', 'T2:run_inlet'),
				pipe('LB2', 'PB:discharge', 'T2:branch'),
				pipe('L2', 'T2:run_outlet', 'R2:port_1')
			]
		);
		expect(
			wordsText(refusalWords(issue('DIFFERENT_BOUNDARIES', ['R1', 'R3']), ['PA', 'PB'], twoTanks))
		).toBe(
			'Pump PA and Pump PB draw from different reservoirs or reference nodes, Tank R1 and Tank R3, each through its own piping: a station has one inlet and one outlet, so they do not form one, even at equal levels (a scenario can change one).'
		);
	});

	it('words the refusals of the fixture, the API’s own answers', () => {
		const refused = fixtureCase('refused') as unknown as {
			project: Project;
			memberIds: string[];
			groupCurve: { body: { issues: TopologyIssue[] } };
		};
		const [only] = refused.groupCurve.body.issues;
		expect(only!.code).toBe('FIXED_HEAD_INSIDE');
		expect(wordsText(refusalWords(only!, refused.memberIds, refused.project))).toBe(
			'The pumps meet the fixed heads of Reservoir R2 and Tank R4, one place more than a station has: it meets the rest of the network at exactly two places, its inlet and its outlet, with no reservoir or reference node between them.'
		);
	});
});
