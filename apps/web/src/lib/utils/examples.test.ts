import { describe, expect, it } from 'vitest';
import { referentialIssues } from '../testing/helpers';
import { decodeProject, encodeProject, URL_LENGTH_WARNING, projectUrl } from './encoding';
import { EXAMPLES, exampleProject } from './examples';
import { componentKind } from './factory';
import { defaultStart, isBoundary, reachable } from './graph';
import { US_GALLON } from './units';
import { projectProblems, schemaProblems } from './validate';

describe('examples', () => {
	it('are valid against the schema, the port graph and the model rules', () => {
		for (const example of EXAMPLES) {
			const project = example.create();
			expect(schemaProblems(project), example.slug).toEqual([]);
			expect(projectProblems(project), example.slug).toEqual([]);
			expect(referentialIssues(project), example.slug).toEqual([]);
		}
	});

	it('are labeled illustrative', () => {
		for (const example of EXAMPLES) {
			expect(example.create().metadata.description).toMatch(/Illustrative example/);
		}
	});

	it('are connected networks with a fixed-pressure boundary', () => {
		for (const example of EXAMPLES) {
			const project = example.create();
			expect(project.components.some(isBoundary), example.slug).toBe(true);
			const start = defaultStart(project)!;
			expect(reachable(project, start).size, example.slug).toBe(project.components.length);
		}
	});

	it('have unique slugs and stable, fresh copies', () => {
		expect(new Set(EXAMPLES.map((e) => e.slug)).size).toBe(EXAMPLES.length);
		const a = exampleProject('pump-transfer')!;
		a.metadata.name = 'changed';
		expect(exampleProject('pump-transfer')!.metadata.name).toBe('Pump transfer between two tanks');
		expect(encodeProject(exampleProject('condenser-water')!)).toBe(
			encodeProject(exampleProject('condenser-water')!)
		);
		expect(exampleProject('nope')).toBeUndefined();
	});

	it('fit in a link well under the length warning', () => {
		for (const example of EXAMPLES) {
			const project = example.create();
			expect(projectUrl(project).length).toBeLessThan(URL_LENGTH_WARNING);
			expect(decodeProject(encodeProject(project))).toEqual(project);
		}
	});

	it('cover the three example systems', () => {
		const kinds = (slug: string) => exampleProject(slug)!.components.map(componentKind);
		// (1) reservoir → pump → gate valve → reservoir, water at 20 °C, a 4-point curve
		const transfer = exampleProject('pump-transfer')!;
		expect(kinds('pump-transfer')).toEqual(['reservoir', 'pump', 'gate', 'reservoir']);
		expect(transfer.fluid).toEqual({ kind: 'builtin', fluidId: 'water', temperature: 293.15 });
		expect(transfer.pumpLibrary[0]!.points).toHaveLength(4);
		expect(
			transfer.connections.every((c) =>
				c.piping.pipes.every((p) => p.materialId === 'carbon_steel' && p.schedule === '40')
			)
		).toBe(true);
		// (2) gravity-fed: no pump, a tee, two lower reservoirs, one branch with a globe valve
		expect(kinds('gravity-branch').sort()).toEqual(
			['globe', 'reservoir', 'reservoir', 'reservoir', 'tee'].sort()
		);
		// (3) condenser water, 90,000 gpm: six 15,000 gpm pumps on a common header, seven
		// condensers (4 × 15,000 and 3 × 10,000 gpm) each held by a flow control valve, six
		// 15,000 gpm tower cells with nozzle headers, and a tower bypass valve closed at design
		const plant = exampleProject('condenser-water')!;
		const count = (kind: string) => kinds('condenser-water').filter((k) => k === kind).length;
		expect([count('pump'), count('check'), count('fcv'), count('equipment')]).toEqual([
			6, 6, 7, 13
		]);
		const gpm = US_GALLON / 60;
		const fcvs = plant.components.filter((c) => c.type === 'valve' && c.valveType === 'fcv');
		const setpoints = fcvs.map((c) => ('setpoint' in c ? c.setpoint : 0) / gpm);
		expect(setpoints.map((q) => Math.round(q))).toEqual([
			15_000, 15_000, 15_000, 15_000, 10_000, 10_000, 10_000
		]);
		const cells = plant.components.filter((c) => /^Cell \d nozzle header$/.test(c.name));
		expect(
			cells.map(
				(c) =>
					c.type === 'equipment' && Math.round(c.rating.kind === 'point' ? c.rating.flow / gpm : 0)
			)
		).toEqual(Array(6).fill(15_000));
		expect(plant.components.find((c) => c.name === 'Tower bypass valve')).toMatchObject({
			valveType: 'butterfly',
			status: 'isolated'
		});
		expect(plant.scenarios?.map((s) => s.name)).toEqual(['Winter: tower bypassed']);
		// An open circuit: the tower basin feeds the pumps and takes the bypass; each cell sprays
		// to atmosphere.
		expect(count('reservoir')).toBe(7);
		expect(plant.connections.length).toBeGreaterThan(plant.components.length - 1);
	});
});
