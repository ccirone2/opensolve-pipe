/**
 * The library dialog's users (users.ts): every entry's users in one walk of the project, equal
 * to pipeSpecUsers and resistanceUsers entry by entry, and named exactly as userLabel names them,
 * without searching the project for each (CLAUDE.md D22; proposal project-library.md §6.1). At
 * the schema's largest network, asking entry by entry and naming each user by a search of the
 * project froze the dialog for about 0.3 s on a desktop and 2 s on a phone. Test inputs (made
 * up): libraryProject, and a chain of valves on 100 specs and 100 entries.
 */
import { describe, expect, it } from 'vitest';
import type { Component, IsolationValve, PipeConnection, Project } from '$lib/api/types';
import { libraryProject, link, projectWith } from '$lib/testing/helpers';
import {
	pipeSpecUsers,
	resistanceUsers,
	userLabel,
	type LibraryUser
} from '$lib/utils/project-library';
import { libraryUsers, userLabeller } from './users';

/**
 * R1 → V1 → ... → Vn → R2: each connection on two spec pipes and a plain one, with two fittings on
 * entries and one on its cited K; each valve on an entry, every fifth on its Crane default; 100
 * specs and 100 entries, the last ten of each used by nothing; scenario changes of each kind, and
 * of other fields.
 */
function chain(n: number): Project {
	const port = (id: string) => ({ id, nominalSize: 0.1016, direction: 'bidirectional' }) as const;
	const reservoir = (id: string, name: string): Component => ({
		id,
		name,
		elevation: 0,
		type: 'reservoir',
		liquidLevel: 10,
		surfacePressure: 0,
		ports: [port('port_1')]
	});
	const valves = Array.from({ length: n }, (_, i): IsolationValve => ({
		id: `V${i + 1}`,
		name: `Gate valve ${i + 1}`,
		elevation: 0,
		type: 'valve',
		valveType: 'gate',
		status: 'active',
		...(i % 5 === 4 ? {} : { resistance: { kind: 'library', id: `RS${(i % 90) + 1}` } }),
		ports: [
			{ id: 'inlet', nominalSize: 0.1016, direction: 'inlet' },
			{ id: 'outlet', nominalSize: 0.1016, direction: 'outlet' }
		]
	}));
	const ends: [string, string][] = [['R1', 'port_1']];
	for (const v of valves) ends.push([v.id, 'inlet'], [v.id, 'outlet']);
	ends.push(['R2', 'port_1']);
	const connections: PipeConnection[] = [];
	for (let k = 0; k < ends.length; k += 2) {
		const c = link(`L${k / 2 + 1}`, ends[k]!, ends[k + 1]!);
		const j = k / 2;
		c.piping = {
			pipes: [
				{ specId: `PS${((2 * j) % 90) + 1}`, length: 10 },
				{ materialId: 'carbon_steel', schedule: '40', nominalSize: 0.1016, length: 5 },
				{ specId: `PS${((7 * j) % 90) + 1}`, length: 10 }
			],
			fittings: [
				{ type: 'elbow_90_lr', quantity: 1, pipeIndex: 0, resistanceId: `RS${((3 * j) % 90) + 1}` },
				{ type: 'elbow_90_sr', quantity: 2, pipeIndex: 1 },
				{ type: 'custom', quantity: 1, pipeIndex: 2, resistanceId: `RS${((j + 40) % 90) + 1}` }
			]
		};
		connections.push(c);
	}
	const project = projectWith(
		[reservoir('R1', 'Upper tank'), ...valves, reservoir('R2', 'Lower tank')],
		connections
	);
	project.pipeLibrary = Array.from({ length: 100 }, (_, i) => ({
		id: `PS${i + 1}`,
		name: `Spec ${i + 1}`,
		source: 'Test input: a made-up bore',
		materialId: 'custom',
		innerDiameter: 0.1,
		roughness: 4.5e-5
	}));
	project.resistanceLibrary = Array.from({ length: 100 }, (_, i) => ({
		id: `RS${i + 1}`,
		name: `Entry ${i + 1}`,
		source: 'Test input: a made-up Cv',
		kind: 'Cv',
		value: 300 + i
	}));
	project.scenarios = [
		{
			id: 'S1',
			name: 'Lined',
			overrides: [
				{ kind: 'pipe', connectionId: 'L2', pipeIndex: 1, field: 'spec', value: { specId: 'PS3' } },
				{ kind: 'component', componentId: 'V1', field: 'status', value: 'closed' },
				{
					kind: 'component',
					componentId: 'V5',
					field: 'resistance',
					value: { kind: 'library', id: 'RS3' }
				},
				{
					kind: 'pipe',
					connectionId: 'L3',
					pipeIndex: 1,
					field: 'spec',
					value: { materialId: 'carbon_steel', schedule: '80', nominalSize: 0.1016 }
				}
			]
		},
		{
			id: 'S2',
			name: 'Throttled',
			overrides: [
				{
					kind: 'component',
					componentId: 'V2',
					field: 'resistance',
					value: { kind: 'Cv', value: 120 }
				},
				{
					kind: 'component',
					componentId: 'V3',
					field: 'resistance',
					value: { kind: 'library', id: 'RS3' }
				},
				{ kind: 'pipe', connectionId: 'L4', pipeIndex: 0, field: 'spec', value: { specId: 'PS3' } }
			]
		}
	];
	return project;
}

/** Each entry's users, asked entry by entry. */
function oneByOne(project: Project) {
	return {
		pipe: (project.pipeLibrary ?? []).map((s) => [s.id, pipeSpecUsers(project, s.id)]),
		resistance: (project.resistanceLibrary ?? []).map((e) => [e.id, resistanceUsers(project, e.id)])
	};
}

function grouped(project: Project) {
	const found = libraryUsers(project);
	return {
		pipe: (project.pipeLibrary ?? []).map((s) => [s.id, found.pipe.get(s.id) ?? []]),
		resistance: (project.resistanceLibrary ?? []).map((e) => [
			e.id,
			found.resistance.get(e.id) ?? []
		])
	};
}

const everyUser = (project: Project): LibraryUser[] => {
	const found = libraryUsers(project);
	return [...found.pipe.values(), ...found.resistance.values()].flat();
};

describe('libraryUsers', () => {
	it("lists every entry's users as pipeSpecUsers and resistanceUsers do, in their order", () => {
		const small = libraryProject();
		small.scenarios = chain(4).scenarios;
		for (const project of [libraryProject(), small, chain(60)]) {
			expect(grouped(project)).toEqual(oneByOne(project));
		}
		const project = chain(60);
		const found = libraryUsers(project);
		// The order: pipes, then changes; valves, fittings, then changes (scenario, change order).
		expect(found.pipe.get('PS3')?.map((u) => u.kind)).toEqual([
			...Array(pipeSpecUsers(project, 'PS3').length - 2).fill('pipe'),
			'scenario',
			'scenario'
		]);
		expect(
			found.resistance.get('RS3')?.map((u) => (u.kind === 'scenario' ? u.scenarioId : u.kind))
		).toEqual(
			resistanceUsers(project, 'RS3').map((u) => (u.kind === 'scenario' ? u.scenarioId : u.kind))
		);
		expect(
			found.resistance
				.get('RS3')
				?.slice(-2)
				.map((u) => u.kind)
		).toEqual(['scenario', 'scenario']);
		// The last ten of each list are used by nothing.
		expect(found.pipe.has('PS91')).toBe(false);
		expect(found.resistance.has('RS100')).toBe(false);
	});

	it('walks the project once, whatever the number of entries', () => {
		// Each connection's piping read through a counter: asked entry by entry, the 200 entries
		// read it 200 times each.
		const project = chain(60);
		let reads = 0;
		for (const connection of project.connections) {
			const piping = connection.piping;
			Object.defineProperty(connection, 'piping', {
				get: () => {
					reads += 1;
					return piping;
				}
			});
		}
		const found = libraryUsers(project);
		expect(reads).toBeLessThanOrEqual(2 * project.connections.length);
		const used = (list: { id: string }[] | undefined, users: (id: string) => LibraryUser[]) =>
			(list ?? []).filter((e) => users(e.id).length).map((e) => e.id);
		expect([...found.pipe.keys()].sort()).toEqual(
			used(project.pipeLibrary, (id) => pipeSpecUsers(project, id)).sort()
		);
		expect([...found.resistance.keys()].sort()).toEqual(
			used(project.resistanceLibrary, (id) => resistanceUsers(project, id)).sort()
		);
		expect(found.pipe.size).toBeGreaterThan(50);
	});
});

describe('userLabeller', () => {
	it('names every user as userLabel does, on the whole project', () => {
		const fittingName = (type: string) => `the ${type} fitting`;
		for (const project of [libraryProject(), chain(60)]) {
			const label = userLabeller(project);
			const users = everyUser(project);
			expect(users.length).toBeGreaterThan(3);
			expect(users.map((u) => label(u))).toEqual(users.map((u) => userLabel(project, u)));
			expect(users.map((u) => label(u, fittingName))).toEqual(
				users.map((u) => userLabel(project, u, fittingName))
			);
		}
	});

	it('names a user whose ends are not in the project by their ids, as userLabel does', () => {
		// Made up: L1's start is a component the project does not hold, and a user of a connection
		// and of a valve the project does not hold.
		const project = libraryProject();
		project.connections[0]!.fromComponentId = 'R9';
		const users: LibraryUser[] = [
			...everyUser(project),
			{ kind: 'pipe', connectionId: 'L9', pipeIndex: 0 },
			{ kind: 'fitting', connectionId: 'L9', fittingIndex: 2 },
			{ kind: 'valve', componentId: 'V9' }
		];
		const label = userLabeller(project);
		expect(users.map((u) => label(u))).toEqual(users.map((u) => userLabel(project, u)));
		expect(label({ kind: 'pipe', connectionId: 'L1', pipeIndex: 0 })).toBe(
			'Pipe 1 of R9 → Gate valve V1'
		);
	});

	it('names each user without searching the project', () => {
		const project = chain(60);
		const users = everyUser(project);
		const expected = users.map((u) => userLabel(project, u));
		const label = userLabeller(project);
		const searched = () => {
			throw new Error('searched the project');
		};
		Object.defineProperty(project.components, 'find', { value: searched });
		Object.defineProperty(project.connections, 'find', { value: searched });
		expect(() => userLabel(project, users[0]!)).toThrow('searched the project');
		expect(users.map((u) => label(u))).toEqual(expected);
	});
});
