/**
 * The project library's model layer (CLAUDE.md D21, proposal project-library.md §6, §7.4): edits,
 * refusals, usage, display resolution and words. Every project is a made-up test input
 * (testing/helpers.ts libraryProject).
 */
import { describe, expect, it } from 'vitest';
import type { PipeConnection, Project, ResistanceSpec } from '../api/types';
import { deepFreeze, libraryProject, projectWith } from '../testing/helpers';
import { TEST_LIBRARY } from '../testing/library';
import { EditError } from './edit';
import { EXAMPLES } from './examples';
import { decodeProject, encodeProject } from './encoding';
import { createComponent, newId, usedIds } from './factory';
import { originOf } from './identity';
import { canonicalJson } from './json';
import {
	applyPipeSpec,
	entryKAtBore,
	entryRefText,
	entryValueText,
	hasLibrary,
	inlineCoefficient,
	isResistanceRef,
	libraryMentions,
	MAX_PIPE_SPECS,
	MAX_RESISTANCE_ENTRIES,
	newPipeSpecId,
	newResistanceId,
	pipeAsSolved,
	pipeSpecRuleProblems,
	pipeSpecScope,
	pipeSpecUsers,
	removePipeSpec,
	removeResistanceSpec,
	resistanceSpecRuleProblems,
	resistanceText,
	resistanceUsers,
	resolvePipe,
	samePipeKind,
	setFittingResistance,
	setPipeSpec,
	setResistanceSpec,
	setValveResistance,
	specPipe,
	specRefText,
	specValuesText,
	userLabel,
	valveEntry,
	withPipeLibrary,
	withResistanceKind,
	withResistanceLibrary,
	withSpec
} from './project-library';
import { projectProblems } from './validate';
import { SI_UNITS } from './units';

const sizes = {
	size(
		materialId: string,
		schedule: string | null | undefined,
		nominal: number | null | undefined
	) {
		const material = TEST_LIBRARY.materials.find((m) => m.id === materialId);
		return material?.schedules
			.find((s) => s.id === schedule)
			?.sizes.find((s) => nominal != null && Math.abs(s.nominalSize - nominal) < 1e-9);
	}
};

function l1(project: Project): PipeConnection {
	return project.connections.find((c) => c.id === 'L1') as PipeConnection;
}

describe('the test project', () => {
	it('is a valid project with no problems', () => {
		expect(projectProblems(libraryProject())).toEqual([]);
	});
});

describe('lists', () => {
	it('are left out of the project when empty, so a project without a library encodes as before', () => {
		const plain = projectWith([], []);
		const encoded = encodeProject(plain);
		const added = setPipeSpec(plain, {
			id: 'PS1',
			name: 'Spec',
			source: 'test input',
			materialId: 'custom',
			innerDiameter: 0.1,
			roughness: 1e-5
		});
		expect(added.pipeLibrary).toHaveLength(1);
		const removed = removePipeSpec(added, 'PS1');
		expect('pipeLibrary' in removed).toBe(false);
		expect(encodeProject(removed)).toBe(encoded);
		const entry = setResistanceSpec(plain, {
			id: 'RS1',
			name: 'Cv',
			source: 'test input',
			kind: 'Cv',
			value: 10
		});
		const none = removeResistanceSpec(entry, 'RS1');
		expect('resistanceLibrary' in none).toBe(false);
		expect(encodeProject(none)).toBe(encoded);
		expect(withPipeLibrary(plain, [])).not.toHaveProperty('pipeLibrary');
		expect(withResistanceLibrary(plain, [])).not.toHaveProperty('resistanceLibrary');
		expect(hasLibrary(plain)).toBe(false);
		expect(hasLibrary(added)).toBe(true);
	});

	it('round-trip through a link', () => {
		const project = libraryProject();
		const decoded = decodeProject(encodeProject(project));
		expect(canonicalJson(decoded)).toBe(canonicalJson(project));
	});
});

describe('ids', () => {
	it('share the namespace of elements and curves, and new ones never reuse an id in use or referred to', () => {
		const project = libraryProject();
		const used = usedIds(project);
		for (const id of ['PS1', 'PS2', 'RS1', 'RS2']) expect(used.has(id)).toBe(true);
		expect(newPipeSpecId(project)).toBe('PS3');
		expect(newResistanceId(project)).toBe('RS3');
		// A reference to an entry the library does not have keeps its id from a new entry.
		const dangling = structuredClone(project);
		l1(dangling).piping.pipes[1] = { specId: 'PS3', length: 12 };
		expect(newPipeSpecId(dangling)).toBe('PS4');
		const scenario = structuredClone(project);
		scenario.scenarios = [
			{
				id: 'S1',
				name: 'Winter',
				overrides: [
					{
						kind: 'component',
						componentId: 'V1',
						field: 'resistance',
						value: { kind: 'library', id: 'RS3' }
					}
				]
			}
		];
		expect(newResistanceId(scenario)).toBe('RS4');
		expect(newResistanceId(project, ['RS3'])).toBe('RS4');
	});

	it("of a deleted entry nothing refers to may be given again, as an element's is (§12 item 27)", () => {
		const project = removePipeSpec(libraryProject(), 'PS2');
		expect(newPipeSpecId(project)).toBe('PS2');
		const valve = libraryProject().components.find((c) => c.id === 'V1')!;
		const withoutValve = {
			...libraryProject(),
			components: libraryProject().components.filter((c) => c.id !== 'V1'),
			connections: []
		};
		expect(newId(withoutValve, 'V')).toBe(valve.id);
		// So an out-of-date mention of the deleted entry links to the entry that took its id.
		const other = setPipeSpec(project, {
			id: 'PS2',
			name: 'Other spec',
			source: 'test input',
			materialId: 'custom',
			innerDiameter: 0.3,
			roughness: 1e-5
		});
		const mentions = libraryMentions('project library pipe spec "Lined 80 mm" (PS2): x', other);
		expect(mentions.map((m) => [m.list, m.id])).toEqual([['pipe', 'PS2']]);
		expect(other.pipeLibrary!.find((s) => s.id === 'PS2')?.name).toBe('Other spec');
	});

	it('of a new entry may not be in use', () => {
		const project = libraryProject();
		expect(() =>
			setPipeSpec(project, {
				id: 'V1',
				name: 'x',
				source: 'test input',
				materialId: 'custom',
				innerDiameter: 0.1,
				roughness: 0
			})
		).toThrow(EditError);
		expect(() =>
			setResistanceSpec(project, { id: 'PS1', name: 'x', source: 's', kind: 'Cv', value: 1 })
		).toThrow(/already used/);
	});

	it('are taken by no new component', () => {
		const project = libraryProject();
		project.pipeLibrary!.push({
			id: 'V2',
			name: 'Odd id',
			source: 'test input',
			materialId: 'custom',
			innerDiameter: 0.1,
			roughness: 0
		});
		expect(createComponent('gate', project).id).toBe('V3');
		expect(newId(project, 'V')).toBe('V3');
	});
});

describe('setPipeSpec and setResistanceSpec', () => {
	it('replace an entry in place: every element that refers to it takes its new values', () => {
		const project = deepFreeze(libraryProject());
		const spec = { ...project.pipeLibrary![0]!, innerDiameter: 0.11 };
		const next = setPipeSpec(project, spec);
		expect(next.pipeLibrary![0]).toEqual(spec);
		expect(next.pipeLibrary).toHaveLength(2);
		expect(resolvePipe(next, l1(next).piping.pipes[0]!).innerDiameter).toBe(0.11);
		// A Cv entry made a Kv: the valve and fitting that refer to it follow, references unchanged.
		const kv = setResistanceSpec(next, {
			...project.resistanceLibrary![0]!,
			kind: 'Kv',
			value: 80
		});
		expect(kv.resistanceLibrary![0]).toMatchObject({ kind: 'Kv', value: 80 });
		expect(kv.components.find((c) => c.id === 'V1')).toMatchObject({
			resistance: { kind: 'library', id: 'RS1' }
		});
		expect(
			valveEntry(
				kv,
				kv.components.find((c) => c.id === 'V1')!
			)?.kind
		).toBe('Kv');
	});

	it('refuse an entry that breaks the published rules, naming fields only', () => {
		const project = libraryProject();
		expect(() =>
			setPipeSpec(project, {
				id: 'PS3',
				name: 'Custom',
				source: 'test input',
				materialId: 'custom',
				innerDiameter: 0.1
			})
		).toThrow('A custom pipe spec needs its roughness.');
		expect(() =>
			setPipeSpec(project, {
				id: 'PS3',
				name: 'Thin',
				source: 'test input',
				materialId: 'carbon_steel',
				innerDiameter: 0.1,
				outerDiameter: 0.1
			})
		).toThrow('Its inner diameter must be below its outer diameter.');
		expect(() =>
			setResistanceSpec(project, { id: 'RS3', name: 'K', source: 's', kind: 'K', value: 1 })
		).toThrow('A K entry needs its reference diameter (a K is stated at a bore).');
		expect(() =>
			setResistanceSpec(project, {
				id: 'RS3',
				name: 'Cv',
				source: 's',
				kind: 'Cv',
				value: 1,
				referenceDiameter: 0.1
			})
		).toThrow('A Cv entry takes no reference diameter (it needs no bore).');
	});

	it('refuse a new entry on a full list, as the API does, but edit one in place', () => {
		// 100 made-up entries in each list: the schema's maxItems.
		const project = deepFreeze({
			...libraryProject(),
			pipeLibrary: Array.from({ length: 100 }, (_, i) => ({
				id: `PS${i + 1}`,
				name: `Spec ${i + 1}`,
				source: 'test input',
				materialId: 'custom',
				innerDiameter: 0.05,
				roughness: 1e-5
			})),
			resistanceLibrary: Array.from({ length: 100 }, (_, i) => ({
				id: `RS${i + 1}`,
				name: `Entry ${i + 1}`,
				source: 'test input',
				kind: 'Cv' as const,
				value: 100
			}))
		});
		expect([MAX_PIPE_SPECS, MAX_RESISTANCE_ENTRIES]).toEqual([100, 100]);
		expect(() =>
			setPipeSpec(project, {
				id: 'PS101',
				name: 'One more',
				source: 'test input',
				materialId: 'custom',
				innerDiameter: 0.05,
				roughness: 1e-5
			})
		).toThrow(new EditError('A project holds at most 100 pipe specs.'));
		expect(() =>
			setResistanceSpec(project, {
				id: 'RS101',
				name: 'One more',
				source: 'test input',
				kind: 'Cv',
				value: 100
			})
		).toThrow(new EditError('A project holds at most 100 resistance entries.'));
		const edited = setPipeSpec(project, { ...project.pipeLibrary![99]!, innerDiameter: 0.06 });
		expect(edited.pipeLibrary).toHaveLength(100);
		expect(edited.pipeLibrary![99]!.innerDiameter).toBe(0.06);
		const kv = setResistanceSpec(project, { ...project.resistanceLibrary![0]!, kind: 'Kv' });
		expect(kv.resistanceLibrary).toHaveLength(100);
	});

	it('rule problems match the published rules both ways', () => {
		const base = { id: 'X', name: 'X', source: 's' };
		expect(
			pipeSpecRuleProblems({ ...base, materialId: 'carbon_steel', innerDiameter: 0.1 })
		).toEqual([]);
		expect(
			pipeSpecRuleProblems({ ...base, materialId: 'custom', innerDiameter: 0.1, roughness: 0 })
		).toEqual([]);
		expect(
			pipeSpecRuleProblems({
				...base,
				materialId: 'custom',
				innerDiameter: 0.2,
				outerDiameter: 0.1
			})
		).toEqual([
			'a custom pipe spec needs its roughness',
			'its inner diameter must be below its outer diameter'
		]);
		const entry = (e: Partial<ResistanceSpec>) =>
			({ ...base, kind: 'K', value: 1, ...e }) as ResistanceSpec;
		expect(resistanceSpecRuleProblems(entry({ referenceDiameter: 0.1 }))).toEqual([]);
		expect(resistanceSpecRuleProblems(entry({ kind: 'Kv' }))).toEqual([]);
		expect(resistanceSpecRuleProblems(entry({ kind: 'Kv', referenceDiameter: 0.1 }))).toHaveLength(
			1
		);
	});

	it('withResistanceKind keeps a value only within its kind and a bore for a K only', () => {
		const entry: ResistanceSpec = {
			id: 'RS9',
			name: 'n',
			source: 's',
			kind: 'K',
			value: 0.3,
			referenceDiameter: 0.1
		};
		expect(withResistanceKind(entry, 'K')).toEqual(entry);
		expect(withResistanceKind(entry, 'Cv')).toEqual({
			id: 'RS9',
			name: 'n',
			source: 's',
			kind: 'Cv'
		});
	});
});

describe('removePipeSpec and removeResistanceSpec', () => {
	it('are refused while an element uses the entry, naming the first user', () => {
		const project = deepFreeze(libraryProject());
		expect(() => removePipeSpec(project, 'PS1')).toThrow(
			'Pipe 1 of Upper tank → Gate valve V1 uses this spec.'
		);
		expect(() => removeResistanceSpec(project, 'RS1')).toThrow(
			'Gate valve V1 (and 1 more) uses this entry.'
		);
		expect(() => removeResistanceSpec(project, 'RS2')).toThrow(
			'Fitting 1 (90° elbow, long radius) of Upper tank → Gate valve V1 uses this entry.'
		);
		expect(() => removePipeSpec(project, 'PS9')).toThrow('There is no pipe spec "PS9".');
		expect(() => removeResistanceSpec(project, 'RS9')).toThrow(EditError);
		const next = removePipeSpec(project, 'PS2');
		expect(next.pipeLibrary!.map((s) => s.id)).toEqual(['PS1']);
	});

	it('are refused while a scenario change uses the entry', () => {
		const project = libraryProject();
		project.scenarios = [
			{
				id: 'S1',
				name: 'Lined',
				overrides: [
					{
						kind: 'pipe',
						connectionId: 'L2',
						pipeIndex: 0,
						field: 'spec',
						value: { specId: 'PS2' }
					}
				]
			}
		];
		expect(() => removePipeSpec(project, 'PS2')).toThrow(
			'Scenario Lined, change 1 uses this spec.'
		);
		expect(pipeSpecUsers(project, 'PS2')).toEqual([
			{
				kind: 'scenario',
				scenarioId: 'S1',
				changeIndex: 0,
				override: project.scenarios[0]!.overrides![0]
			}
		]);
	});
});

describe('usage', () => {
	it('lists every user in order: pipes, valves, fittings, then scenario changes', () => {
		const project = libraryProject();
		expect(pipeSpecUsers(project, 'PS1')).toEqual([
			{ kind: 'pipe', connectionId: 'L1', pipeIndex: 0 }
		]);
		expect(resistanceUsers(project, 'RS1')).toEqual([
			{ kind: 'valve', componentId: 'V1' },
			{ kind: 'fitting', connectionId: 'L1', fittingIndex: 1 }
		]);
		expect(resistanceUsers(project, 'RS2')).toEqual([
			{ kind: 'fitting', connectionId: 'L1', fittingIndex: 0 }
		]);
		expect(pipeSpecUsers(project, 'PS2')).toEqual([]);
		expect(userLabel(project, { kind: 'fitting', connectionId: 'L1', fittingIndex: 1 })).toBe(
			'Fitting 2 (Custom fitting (enter K)) of Upper tank → Gate valve V1'
		);
	});
});

describe('applyPipeSpec', () => {
	it('uses a spec for one pipe, keeping its length and its identity', () => {
		const project = deepFreeze(libraryProject());
		const before = l1(project).piping.pipes[1]!;
		const { project: next, count } = applyPipeSpec(project, 'PS2', {
			kind: 'pipe',
			connectionId: 'L1',
			pipeIndex: 1
		});
		expect(count).toBe(1);
		const after = l1(next).piping.pipes[1]!;
		expect(after).toEqual({ specId: 'PS2', length: 12 });
		expect(originOf(after)).toBe(originOf(before));
		expect(projectProblems(next)).toEqual([]);
	});

	it('reaches every pipe of the same size and material, or every pipe of a connection', () => {
		const project = libraryProject();
		// L1 pipe 2 and L2's pipe are NPS 4 Sch 40 carbon steel; L1 pipe 1 is spec PS1.
		expect(pipeSpecScope(project, { kind: 'same', connectionId: 'L2', pipeIndex: 0 })).toEqual([
			{ connectionId: 'L1', pipeIndex: 1 },
			{ connectionId: 'L2', pipeIndex: 0 }
		]);
		const same = applyPipeSpec(project, 'PS2', { kind: 'same', connectionId: 'L2', pipeIndex: 0 });
		expect(same.count).toBe(2);
		expect(
			same.project.connections.map((c) => c.piping.pipes.map((p) => p.specId ?? null))
		).toEqual([['PS1', 'PS2'], ['PS2']]);
		const all = applyPipeSpec(project, 'PS1', {
			kind: 'connection',
			connectionId: 'L1',
			pipeIndex: 0
		});
		// The pipe already on PS1 is left as it is.
		expect(all.count).toBe(1);
		expect(l1(all.project).piping.pipes[0]).toBe(l1(project).piping.pipes[0]);
		// From a spec pipe, "the same" is every pipe of that spec.
		expect(pipeSpecScope(project, { kind: 'same', connectionId: 'L1', pipeIndex: 0 })).toEqual([
			{ connectionId: 'L1', pipeIndex: 0 }
		]);
	});

	it('is refused for a spec or a pipe the project does not have', () => {
		const project = libraryProject();
		expect(() =>
			applyPipeSpec(project, 'PS9', { kind: 'pipe', connectionId: 'L1', pipeIndex: 0 })
		).toThrow('There is no pipe spec "PS9".');
		expect(() =>
			applyPipeSpec(project, 'PS1', { kind: 'pipe', connectionId: 'L1', pipeIndex: 5 })
		).toThrow(EditError);
	});

	it('compares nominal sizes as the library does', () => {
		expect(
			samePipeKind(
				{ materialId: 'carbon_steel', schedule: '40', nominalSize: 4 * 0.0254, length: 1 },
				{ materialId: 'carbon_steel', schedule: '40', nominalSize: 0.1016, length: 9 }
			)
		).toBe(true);
		expect(
			samePipeKind(
				{ materialId: 'carbon_steel', schedule: '40', nominalSize: 0.1016, length: 1 },
				{
					materialId: 'carbon_steel',
					schedule: '40',
					nominalSize: 0.1016,
					innerDiameter: 0.1,
					length: 1
				}
			)
		).toBe(false);
		expect(samePipeKind(withSpec({ length: 1 }, 'PS1'), withSpec({ length: 2 }, 'PS1'))).toBe(true);
	});
});

describe('valve and fitting references', () => {
	it('setValveResistance writes a reference, a coefficient or none', () => {
		const project = deepFreeze(libraryProject());
		const kv = setValveResistance(project, 'V1', { kind: 'Kv', value: 50 });
		expect(kv.components.find((c) => c.id === 'V1')).toMatchObject({
			resistance: { kind: 'Kv', value: 50 }
		});
		const none = setValveResistance(kv, 'V1', null);
		expect(none.components.find((c) => c.id === 'V1')).not.toHaveProperty('resistance');
		const back = setValveResistance(none, 'V1', { kind: 'library', id: 'RS2' });
		expect(back.components.find((c) => c.id === 'V1')).toMatchObject({
			resistance: { kind: 'library', id: 'RS2' }
		});
		expect(() => setValveResistance(project, 'V1', { kind: 'library', id: 'RS9' })).toThrow(
			'There is no resistance entry "RS9".'
		);
		expect(() => setValveResistance(project, 'R1', null)).toThrow(/not a valve/);
	});

	it('setFittingResistance takes the K from an entry, never beside a kOverride', () => {
		const piping = {
			pipes: [{ materialId: 'carbon_steel', schedule: '40', nominalSize: 0.1016, length: 1 }],
			fittings: [{ type: 'custom' as const, quantity: 1, pipeIndex: 0, kOverride: 2 }]
		};
		const next = setFittingResistance(piping, 0, 'RS1');
		expect(next.fittings[0]).toEqual({
			type: 'custom',
			quantity: 1,
			pipeIndex: 0,
			resistanceId: 'RS1'
		});
		expect(setFittingResistance(next, 0, null).fittings[0]).toEqual({
			type: 'custom',
			quantity: 1,
			pipeIndex: 0
		});
		expect(setFittingResistance(piping, 3, 'RS1')).toBe(piping);
	});

	it('tells a reference from a coefficient', () => {
		expect(isResistanceRef({ kind: 'library', id: 'RS1' })).toBe(true);
		expect(isResistanceRef({ kind: 'Cv', value: 1 })).toBe(false);
		expect(isResistanceRef(null)).toBe(false);
		expect(inlineCoefficient({ kind: 'library', id: 'RS1' })).toBeNull();
		expect(inlineCoefficient({ kind: 'K', value: 1 })).toEqual({ kind: 'K', value: 1 });
		expect(inlineCoefficient(undefined)).toBeNull();
	});
});

describe('resolution for display', () => {
	it('a pipe of a spec is the pipe the spec stands for (the API spec_pipe)', () => {
		const project = libraryProject();
		const pipe = l1(project).piping.pipes[0]!;
		expect(pipeAsSolved(project, pipe)).toEqual({
			materialId: 'carbon_steel',
			innerDiameter: 0.1,
			length: 30
		});
		const lined = specPipe({ length: 5 }, project.pipeLibrary![1]!);
		expect(lined).toEqual({
			materialId: 'custom',
			innerDiameter: 0.08,
			roughness: 1.5e-6,
			length: 5
		});
		// A spec on a library material without a roughness: the server's (Farshad at its bore).
		expect(resolvePipe(project, pipe, sizes)).toEqual({
			innerDiameter: 0.1,
			materialId: 'carbon_steel',
			spec: project.pipeLibrary![0],
			serverRoughness: true
		});
		expect(resolvePipe(project, withSpec({ length: 1 }, 'PS2'))).toMatchObject({
			innerDiameter: 0.08,
			roughness: 1.5e-6
		});
		expect(resolvePipe(project, withSpec({ length: 1 }, 'PS9'))).toEqual({ missingSpec: 'PS9' });
		expect(pipeAsSolved(project, withSpec({ length: 1 }, 'PS9'))).toEqual({
			specId: 'PS9',
			length: 1
		});
	});

	it('a pipe of its own resolves as piping.resolvedPipe does', () => {
		const project = libraryProject();
		const library = l1(project).piping.pipes[1]!;
		expect(resolvePipe(project, library, sizes)).toEqual({
			innerDiameter: 0.10226,
			roughness: 3.501e-5,
			materialId: 'carbon_steel'
		});
		expect(resolvePipe(project, library)).toEqual({ materialId: 'carbon_steel' });
		expect(resolvePipe(project, { ...library, innerDiameter: 0.1 }, sizes)).toEqual({
			innerDiameter: 0.1,
			materialId: 'carbon_steel',
			serverRoughness: true
		});
	});

	it("a K entry on another bore is K₀ (D/d₀)⁴; a Cv or Kv is the server's to convert", () => {
		const k = { kind: 'K' as const, value: 0.3, referenceDiameter: 0.7366 };
		expect(entryKAtBore(k, 0.7366)).toBe(0.3);
		expect(entryKAtBore(k, 0.74294)).toBeCloseTo(0.3 * (0.74294 / 0.7366) ** 4, 15);
		expect(entryKAtBore(k, null)).toBeNull();
		expect(entryKAtBore({ kind: 'Cv', value: 60000 }, 0.7)).toBeNull();
	});
});

describe('words', () => {
	it('name entries and their values in display units', () => {
		const project = libraryProject();
		const [cv, k] = project.resistanceLibrary!;
		expect(entryValueText(cv!, SI_UNITS)).toBe('Cv 900');
		expect(entryValueText(k!, SI_UNITS)).toBe('K 0.3 at 90 mm');
		expect(entryRefText(project, 'RS1', SI_UNITS)).toBe('“Gate, open” (project library, Cv 900)');
		expect(entryRefText(project, 'RS9', SI_UNITS)).toBe(
			'project library entry RS9 (not in the library)'
		);
		expect(resistanceText(project, { kind: 'library', id: 'RS2' }, SI_UNITS)).toBe(
			'“Elbow (K)” (project library, K 0.3 at 90 mm)'
		);
		expect(resistanceText(project, { kind: 'Cv', value: 120 }, SI_UNITS)).toBe('Cv 120');
		expect(resistanceText(project, null, SI_UNITS)).toBe('Default');
		expect(specRefText(project, 'PS1')).toBe('“NPS 4 measured” (project library pipe spec)');
		expect(
			specValuesText(project.pipeLibrary![0]!, SI_UNITS, { materialName: () => 'Carbon steel' })
		).toBe(
			"Carbon steel, NPS 4, inner diameter 100 mm, roughness the material's at this bore (Farshad & Rieke), as the server computes it"
		);
		expect(specValuesText(project.pipeLibrary![1]!, SI_UNITS)).toBe(
			'Custom pipe, inner diameter 80 mm, roughness 0.0015 mm'
		);
	});
});

describe("the server's mentions of entries", () => {
	it('are found by id, for the trace view to link them', () => {
		const project = libraryProject();
		const text =
			'inner diameter from project library pipe spec "NPS 4 "measured"" (PS1): test input; K from ' +
			'project library resistance "Old name" (RS2): test input; project library resistance "Gone" (RS9)';
		const mentions = libraryMentions(text, project);
		expect(mentions.map((m) => [m.list, m.id, text.slice(m.index, m.index + m.length)])).toEqual([
			['pipe', 'PS1', 'project library pipe spec "NPS 4 "measured"" (PS1)'],
			['resistance', 'RS2', 'project library resistance "Old name" (RS2)']
		]);
		expect(libraryMentions('no entry here', project)).toEqual([]);
	});

	/** The mentions of `text` in `project`: list, id and the text linked. */
	const linked = (text: string, project: Project) =>
		libraryMentions(text, project).map((m) => [
			m.list,
			m.id,
			text.slice(m.index, m.index + m.length)
		]);

	/** The library project with RS1 named `name`. */
	const rs1Named = (name: string) => {
		const project = libraryProject();
		project.resistanceLibrary![0] = { ...project.resistanceLibrary![0]!, name };
		return project;
	};

	it('end where the name ends, though it holds an inch mark before a parenthesis', () => {
		const label = 'project library resistance "6" (DN150) gate valve" (RS1)';
		const text = `K from ${label}: test input; project library resistance "Elbow (K)" (RS2)`;
		expect(linked(text, rs1Named('6" (DN150) gate valve'))).toEqual([
			['resistance', 'RS1', label],
			['resistance', 'RS2', 'project library resistance "Elbow (K)" (RS2)']
		]);
		// A name that holds another entry's id in the label's form still names its own entry.
		const other = 'project library resistance "Gate 4" (RS2) spare" (RS1)';
		expect(linked(`${other}: test input`, rs1Named('Gate 4" (RS2) spare'))).toEqual([
			['resistance', 'RS1', other]
		]);
	});

	it('find an entry renamed since the solve by the first id of an entry the project has', () => {
		const project = libraryProject(); // RS1 is "Gate, open" now
		const label = 'project library resistance "6" (DN150) gate valve" (RS1)';
		expect(linked(`${label}: test input`, project)).toEqual([['resistance', 'RS1', label]]);
		// Never past the next mention, nor past the longest name an entry may have (100).
		const gone = 'project library resistance "Gone" (RS9): x; project library pipe spec "A" (PS1)';
		expect(linked(gone, project)).toEqual([['pipe', 'PS1', 'project library pipe spec "A" (PS1)']]);
		const far = `project library resistance "Gone" (RS9): ${'x'.repeat(100)}" (RS1)`;
		expect(linked(far, project)).toEqual([]);
	});
});

describe('canonical encoding', () => {
	/** The project after a spare pipe spec and resistance entry are added and removed again. */
	const addAndRemove = (project: Project) => {
		const id = newPipeSpecId(project);
		const added = setPipeSpec(project, {
			id,
			name: 'Spare',
			source: 'test input',
			materialId: 'custom',
			innerDiameter: 0.1,
			roughness: 1e-5
		});
		const entry = newResistanceId(added);
		const both = setResistanceSpec(added, {
			id: entry,
			name: 'Spare',
			source: 'test input',
			kind: 'Kv',
			value: 10
		});
		return removePipeSpec(removeResistanceSpec(both, entry), id);
	};

	it('of a project without a library is the same after an entry is added and removed', () => {
		const plain = EXAMPLES.filter((e) => e.slug !== 'condenser-water');
		expect(plain.map((e) => e.slug)).toEqual(['pump-transfer', 'gravity-branch']);
		for (const example of plain) {
			const project = example.create();
			expect(project).not.toHaveProperty('pipeLibrary');
			expect(project).not.toHaveProperty('resistanceLibrary');
			expect(encodeProject(addAndRemove(project))).toBe(encodeProject(project));
		}
	});

	it('of a project with a library is the same after an entry is added and removed', () => {
		// The condenser water example is built on its project library (one spec, one entry).
		const project = EXAMPLES.find((e) => e.slug === 'condenser-water')!.create();
		expect([project.pipeLibrary?.length, project.resistanceLibrary?.length]).toEqual([1, 1]);
		expect(encodeProject(addAndRemove(project))).toBe(encodeProject(project));
	});
});
