import { describe, expect, it } from 'vitest';
import { referentialIssues } from '../testing/helpers';
import { decodeProject, encodeProject, URL_LENGTH_WARNING, projectUrl } from './encoding';
import { EXAMPLES, exampleProject } from './examples';
import { componentKind } from './factory';
import { defaultStart, isBoundary, reachable } from './graph';
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
		expect(encodeProject(exampleProject('closed-loop')!)).toBe(
			encodeProject(exampleProject('closed-loop')!)
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

	it('cover the three v1 scenarios', () => {
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
		// (3) closed loop: pump, check valve, ideal reference node, and a loop
		const loop = exampleProject('closed-loop')!;
		expect(kinds('closed-loop').sort()).toEqual(['check', 'pump', 'reference_node', 'tee'].sort());
		expect(loop.connections.length).toBe(loop.components.length); // one independent loop
		expect(loop.components.some((c) => c.type === 'reservoir')).toBe(false);
	});
});
