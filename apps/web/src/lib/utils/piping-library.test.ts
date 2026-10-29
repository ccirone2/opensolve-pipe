/**
 * Where the browser resolves a pipe for display (CLAUDE.md D22): an orifice plate's D from an
 * inlet pipe of a project library spec, a spec pipe given its own material, the store's
 * staleness fingerprint, which holds the library (and is unchanged for a project without one),
 * and the port size of a component inserted where a spec pipe ends (the spec's nominal size).
 * Made-up test inputs.
 */
import { describe, expect, it } from 'vitest';
import type { PipeDefinition, Project } from '../api/types';
import { hydraulicFingerprint } from '../state/project.svelte';
import { libraryProject } from '../testing/helpers';
import { TEST_LIBRARY } from '../testing/library';
import { pumpTransferExample } from './examples';
import { betaLine, inletBore, type PipeSizes } from './orifice';
import { addBranch } from './edit';
import { CUSTOM_MATERIAL_ID, pipeNominalSize, withMaterial } from './piping';
import { resolvePipe, setPipeSpec } from './project-library';
import { SI_UNITS } from './units';

/** The library project, its V1 inlet pipe (L1's last) of spec `specId` (null: as it is). */
function withInletSpec(specId: string | null): Project {
	const project = libraryProject();
	const pipes = project.connections[0]!.piping.pipes;
	if (specId) pipes[1] = { specId, length: 12 };
	return project;
}

function sizes(status: PipeSizes['libraryStatus']): PipeSizes {
	return {
		libraryStatus: status,
		size: (materialId, schedule, nominal) =>
			TEST_LIBRARY.materials
				.find((m) => m.id === materialId)
				?.schedules.find((s) => s.id === schedule)
				?.sizes.find((s) => nominal != null && Math.abs(s.nominalSize - nominal) < 1e-9)
	};
}

describe("an orifice plate's D from a spec pipe", () => {
	it("is the spec's inner diameter, known before the pipe library loads", () => {
		const project = withInletSpec('PS2');
		const inlet = inletBore(project, 'V1', sizes('loading'));
		expect(inlet).toMatchObject({ state: 'known', diameter: 0.08, spec: { id: 'PS2' } });
		expect(betaLine(0.04, inlet, SI_UNITS).text).toBe(
			'β = d ÷ D = 0.5000, with D = 80 mm, the inner diameter of the inlet pipe (pipe spec “Lined 80 mm”)'
		);
	});

	it('is unknown for a spec the project does not have', () => {
		expect(inletBore(withInletSpec('PS9'), 'V1', sizes('ready'))).toMatchObject({
			state: 'unknown'
		});
	});

	it('of a pipe of its own is as before', () => {
		const project = withInletSpec(null);
		expect(inletBore(project, 'V1', sizes('loading'))).toMatchObject({ state: 'library' });
		expect(inletBore(project, 'V1', sizes('ready'))).toMatchObject({
			state: 'known',
			diameter: 0.10226
		});
	});
});

describe('a spec pipe given its own material', () => {
	const spec: PipeDefinition = { specId: 'PS1', length: 30 };

	it('becomes a custom pipe of the bore and roughness it resolved to', () => {
		const project = libraryProject();
		const custom = withMaterial(
			spec,
			CUSTOM_MATERIAL_ID,
			resolvePipe(withInletSpec('PS2'), { specId: 'PS2', length: 30 })
		);
		expect(custom).toEqual({
			materialId: 'custom',
			length: 30,
			innerDiameter: 0.08,
			roughness: 1.5e-6
		});
		expect(resolvePipe(project, spec)).toMatchObject({ innerDiameter: 0.1 });
	});

	it("becomes a library pipe of the size nearest its spec's bore", () => {
		const material = TEST_LIBRARY.materials[0]!;
		const resolved = resolvePipe(libraryProject(), spec);
		expect(withMaterial(spec, material, resolved)).toEqual({
			materialId: 'carbon_steel',
			length: 30,
			schedule: '40',
			nominalSize: material.schedules[0]!.sizes[1]!.nominalSize
		});
	});
});

describe('the staleness fingerprint', () => {
	it('is unchanged for a project without a library, and follows an edit of an entry', () => {
		const plain = pumpTransferExample();
		const withEmpty = { ...plain, pipeLibrary: undefined, resistanceLibrary: undefined };
		expect(hydraulicFingerprint(withEmpty as unknown as Project)).toBe(hydraulicFingerprint(plain));
		const project = libraryProject();
		const before = hydraulicFingerprint(project);
		const edited = setPipeSpec(project, { ...project.pipeLibrary![0]!, innerDiameter: 0.11 });
		expect(hydraulicFingerprint(edited)).not.toBe(before);
	});
});

describe('a component inserted where a spec pipe ends', () => {
	/** The library project with L2 (V1 outlet, NPS 4 → R2) on a new NPS 6 spec, PS3. */
	function onNps6Spec(): Project {
		const project = libraryProject();
		project.pipeLibrary = [
			...project.pipeLibrary!,
			{
				id: 'PS3',
				name: 'NPS 6 measured',
				source: 'test input',
				materialId: 'carbon_steel',
				innerDiameter: 0.154,
				nominalSize: 0.1524
			}
		];
		project.connections[1]!.piping = { pipes: [{ specId: 'PS3', length: 5 }], fittings: [] };
		return project;
	}

	it("takes the spec's nominal size, the pipe's own otherwise", () => {
		const project = onNps6Spec();
		expect(pipeNominalSize(project, { specId: 'PS3', length: 5 })).toBe(0.1524);
		// A spec without a nominal size (a custom bore), or one the project does not have: none.
		expect(pipeNominalSize(project, { specId: 'PS2', length: 5 })).toBeUndefined();
		expect(pipeNominalSize(project, { specId: 'PS9', length: 5 })).toBeUndefined();
		expect(
			pipeNominalSize(project, {
				materialId: 'carbon_steel',
				schedule: '40',
				nominalSize: 0.0762,
				length: 5
			})
		).toBe(0.0762);
		expect(pipeNominalSize(project, undefined)).toBeUndefined();
	});

	it("sizes a tee added without one to the spec, not to the upstream port's NPS 4", () => {
		const result = addBranch(onNps6Spec(), 'L2');
		const tee = result.components.find((c) => c.type === 'branch')!;
		expect(tee.ports.map((p) => [p.id, p.nominalSize])).toEqual([
			['run_inlet', 0.1524],
			['run_outlet', 0.1524],
			['branch', 0.1524]
		]);
	});
});
