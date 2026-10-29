/**
 * Scenarios with the project library (CLAUDE.md D22, proposal project-library.md §5.1, §6.3): a
 * pipe's spec change may switch it to or from a pipe spec, a valve's resistance change may point it
 * at an entry, and the library itself is base data, never edited in a scenario. The shared
 * fixture's library cases (scenario-cases.json, by the API's real apply_scenario) are checked in
 * scenarios.test.ts with every other case. Made-up test inputs.
 */
import { describe, expect, it } from 'vitest';
import type { Override, Project } from '../api/types';
import { deepFreeze, libraryProject } from '../testing/helpers';
import { applyPipeSpec, setPipeSpec, setValveResistance } from './project-library';
import { applyScenario, changeValueText, scenarioEdit, valueOf, withScenarios } from './scenarios';
import { scenarioProblems } from './scenario-problems';
import { SI_UNITS } from './units';

function withScenario(overrides: Override[] = []): Project {
	return deepFreeze(withScenarios(libraryProject(), [{ id: 'S1', name: 'Winter', overrides }]));
}

function editIn(project: Project, change: (draft: Project) => Project | void): Project {
	const edit = scenarioEdit(project, 'S1', change);
	if (!edit.ok) throw new Error(edit.reason);
	const draft = structuredClone(project);
	edit.apply(draft);
	return draft;
}

const L2 = { kind: 'pipe', connectionId: 'L2', pipeIndex: 0 } as const;
const L1 = { kind: 'pipe', connectionId: 'L1', pipeIndex: 0 } as const;
const V1 = { kind: 'component', componentId: 'V1' } as const;

describe('values that refer to the library', () => {
	it('read and apply as one spec value, or one resistance value', () => {
		const project = withScenario([
			{ kind: 'pipe', connectionId: 'L2', pipeIndex: 0, field: 'spec', value: { specId: 'PS2' } },
			{
				kind: 'pipe',
				connectionId: 'L1',
				pipeIndex: 0,
				field: 'spec',
				value: { materialId: 'custom', innerDiameter: 0.1, roughness: 1e-5 }
			},
			{
				kind: 'component',
				componentId: 'V1',
				field: 'resistance',
				value: { kind: 'Kv', value: 80 }
			}
		]);
		expect(valueOf(project, L1, 'spec')).toEqual({ specId: 'PS1' });
		const applied = applyScenario(project, 'S1').project;
		expect(applied.connections[1]!.piping.pipes[0]).toEqual({ specId: 'PS2', length: 10 });
		expect(applied.connections[0]!.piping.pipes[0]).toEqual({
			materialId: 'custom',
			innerDiameter: 0.1,
			roughness: 1e-5,
			length: 30
		});
		expect(applied.components.find((c) => c.id === 'V1')).toMatchObject({
			resistance: { kind: 'Kv', value: 80 }
		});
		// The library is the base's, in the case too.
		expect(applied.pipeLibrary).toEqual(project.pipeLibrary);
		expect(scenarioProblems(project, 'S1')).toEqual([]);
	});

	it('are named by their entries in the change texts, by id when the library lacks one', () => {
		const project = libraryProject();
		const spec: Override = {
			kind: 'pipe',
			connectionId: 'L2',
			pipeIndex: 0,
			field: 'spec',
			value: { specId: 'PS2' }
		};
		expect(changeValueText(project, spec, spec.value, SI_UNITS)).toBe(
			'“Lined 80 mm” (project library pipe spec)'
		);
		expect(changeValueText(project, spec, { specId: 'PS9' }, SI_UNITS)).toBe(
			'project library pipe spec PS9 (not in the library)'
		);
		const resistance: Override = {
			kind: 'component',
			componentId: 'V1',
			field: 'resistance',
			value: { kind: 'library', id: 'RS2' }
		};
		expect(changeValueText(project, resistance, resistance.value, SI_UNITS)).toBe(
			'“Elbow (K)” (project library, K 0.3 at 90 mm)'
		);
		expect(changeValueText(project, resistance, { kind: 'Cv', value: 120 }, SI_UNITS)).toBe(
			'Cv 120'
		);
		expect(changeValueText(project, resistance, null, SI_UNITS)).toBe('Default');
	});
});

describe('editing in a scenario', () => {
	it("records a pipe switched to a spec, or to its own values, as that pipe's spec change", () => {
		const base = withScenario();
		const switched = editIn(
			base,
			(draft) =>
				applyPipeSpec(draft, 'PS2', { kind: 'pipe', connectionId: 'L2', pipeIndex: 0 }).project
		);
		expect(switched.scenarios![0]!.overrides).toEqual([
			{ kind: 'pipe', connectionId: 'L2', pipeIndex: 0, field: 'spec', value: { specId: 'PS2' } }
		]);
		// The base is unchanged; switching back to the base's value removes the change.
		expect(switched.connections[1]!.piping.pipes[0]!.specId).toBeUndefined();
		const back = editIn(switched, (draft) => {
			draft.connections[1]!.piping.pipes[0] = {
				materialId: 'carbon_steel',
				schedule: '40',
				nominalSize: 0.1016,
				length: 10
			};
		});
		expect(back.scenarios![0]!.overrides).toEqual([]);
	});

	it('records "every pipe of the same size" as one spec change per pipe', () => {
		const base = withScenario();
		const edited = editIn(
			base,
			(draft) =>
				applyPipeSpec(draft, 'PS2', { kind: 'same', connectionId: 'L2', pipeIndex: 0 }).project
		);
		expect(edited.scenarios![0]!.overrides!.map((o) => [o.kind, o.field, o.value])).toEqual([
			['pipe', 'spec', { specId: 'PS2' }],
			['pipe', 'spec', { specId: 'PS2' }]
		]);
	});

	it('records a valve pointed at an entry as its resistance change', () => {
		const base = withScenario();
		const edited = editIn(base, (draft) =>
			setValveResistance(draft, 'V1', { kind: 'library', id: 'RS2' })
		);
		expect(edited.scenarios![0]!.overrides).toEqual([
			{
				kind: 'component',
				componentId: 'V1',
				field: 'resistance',
				value: { kind: 'library', id: 'RS2' }
			}
		]);
		expect(valueOf(base, V1, 'resistance')).toEqual({ kind: 'library', id: 'RS1' });
	});

	it('refuses an edit of the library: entries are base data, shared by every case', () => {
		const base = withScenario();
		const edit = scenarioEdit(base, 'S1', (draft) =>
			setPipeSpec(draft, { ...draft.pipeLibrary![0]!, innerDiameter: 0.2 })
		);
		expect(edit).toMatchObject({ ok: false, reason: 'refused' });
		const fitting = scenarioEdit(base, 'S1', (draft) => {
			draft.connections[0]!.piping.fittings[0]!.resistanceId = 'RS1';
		});
		// A fitting's entry is not a scenario value (fittings are not on the allow-list).
		expect(fitting).toMatchObject({ ok: false, reason: 'refused' });
		expect(valueOf(base, L2, 'spec')).toEqual({
			materialId: 'carbon_steel',
			schedule: '40',
			nominalSize: 0.1016
		});
	});
});
