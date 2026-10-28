/**
 * Goal seek on a valve that takes its resistance from the project library (CLAUDE.md D21,
 * proposal project-library.md §5.2): the search starts at the entry's value when it is of the
 * variable's kind (a K on the valve's inlet bore, K₀ (D/d₀)⁴), the middle of the bounds otherwise,
 * and the values found are the valve's own coefficient. The shared fixture's library cases
 * (goal-seek-cases.json, by the API's real trial builder) are checked in goal-seek.test.ts with
 * every other case. Made-up test inputs.
 */
import { describe, expect, it } from 'vitest';
import type { Override, Project } from '../api/types';
import { deepFreeze, libraryProject } from '../testing/helpers';
import {
	applyToCase,
	caseValueText,
	defaultBounds,
	entryStart,
	newVariable,
	nowText,
	variableChoices,
	variableValue,
	type VariableDraft
} from './goal-seek';
import { withScenarios } from './scenarios';
import { SI_UNITS } from './units';

const V1 = { kind: 'component', componentId: 'V1' } as const;

/** The test project with V1's inlet pipe (L1's last) of spec PS1 (D = 0.1 m), on entry `entry`. */
function onEntry(entry: string, specInlet = true): Project {
	const project = libraryProject();
	if (specInlet) project.connections[0]!.piping.pipes[1] = { specId: 'PS1', length: 12 };
	const valve = project.components.find((c) => c.id === 'V1')!;
	if (valve.type === 'valve') valve.resistance = { kind: 'library', id: entry };
	return deepFreeze(project);
}

function draft(project: Project, coefficient: 'K' | 'Cv' | 'Kv'): VariableDraft {
	return newVariable(project, { target: V1, field: 'resistance', coefficient });
}

describe('the start of a resistance from an entry', () => {
	it("is the entry's Cv or Kv, of the variable's kind", () => {
		const project = onEntry('RS1');
		expect(variableChoices(project).find((c) => c.field === 'resistance')?.coefficient).toBe('Cv');
		expect(variableValue(project, { target: V1, field: 'resistance', coefficient: 'Cv' })).toBe(
			900
		);
		expect(
			variableValue(project, { target: V1, field: 'resistance', coefficient: 'K' })
		).toBeNull();
		expect(defaultBounds(project, { target: V1, field: 'resistance', coefficient: 'Cv' })).toEqual({
			lower: 9,
			upper: 90000
		});
	});

	it("is a K entry's K on the valve's inlet bore, K₀ (D/d₀)⁴", () => {
		const project = onEntry('RS2');
		expect(variableChoices(project).find((c) => c.field === 'resistance')?.coefficient).toBe('K');
		// RS2: K₀ = 0.3 at d₀ = 0.09 m; V1's inlet pipe is spec PS1, D = 0.1 m.
		const k = 0.3 * (0.1 / 0.09) ** 4;
		expect(entryStart(project, { target: V1, field: 'resistance', coefficient: 'K' })).toBe(k);
		expect(entryStart(project, { target: V1, field: 'resistance', coefficient: 'Cv' })).toBeNull();
	});

	it("falls back to the last solve's K where the project does not give the bore", () => {
		const project = onEntry('RS2', false);
		const variable = { target: V1, field: 'resistance', coefficient: 'K' as const };
		expect(entryStart(project, variable)).toBeNull();
		expect(entryStart(project, variable, 0.42)).toBe(0.42);
		expect(variableValue(project, variable, 0.42)).toBe(0.42);
	});

	it('is said with the entry in "Now", and that a value found replaces it', () => {
		const cv = onEntry('RS1');
		expect(nowText(cv, draft(cv, 'Cv'), { prefs: SI_UNITS })).toBe(
			"Now “Gate, open” (project library, Cv 900); a value found is the valve's own Cv, in place of the entry"
		);
		expect(nowText(cv, draft(cv, 'K'), { prefs: SI_UNITS })).toBe(
			"Now “Gate, open” (project library, Cv 900); the search starts at the middle of the bounds (it varies K); a value found is the valve's own K, in place of the entry"
		);
		const k = onEntry('RS2');
		expect(nowText(k, draft(k, 'K'), { prefs: SI_UNITS })).toBe(
			"Now “Elbow (K)” (project library, K 0.3 at 90 mm); the search starts at its K on this valve's inlet pipe, 0.457247; a value found is the valve's own K, in place of the entry"
		);
		const unknown = onEntry('RS2', false);
		expect(nowText(unknown, draft(unknown, 'K'), { prefs: SI_UNITS })).toContain(
			"the search starts at its K on this valve's inlet pipe (solve to see it)"
		);
	});
});

describe('applying a value found', () => {
	const override: Override = {
		kind: 'component',
		componentId: 'V1',
		field: 'resistance',
		value: { kind: 'Cv', value: 1234.5678 }
	};

	it('writes the inline coefficient in place of the reference, in the base', () => {
		const project = onEntry('RS1');
		const next = applyToCase(project, null, [override]);
		expect(next.components.find((c) => c.id === 'V1')).toMatchObject({
			resistance: { kind: 'Cv', value: 1234.5678 }
		});
		// The entry stays in the library (another element may use it).
		expect(next.resistanceLibrary).toEqual(project.resistanceLibrary);
	});

	it('upserts it as the scenario change it ran on', () => {
		const project = deepFreeze(
			withScenarios(onEntry('RS1'), [
				{
					id: 'S1',
					name: 'Winter',
					overrides: [
						{
							kind: 'component',
							componentId: 'V1',
							field: 'resistance',
							value: { kind: 'library', id: 'RS2' }
						}
					]
				}
			])
		);
		const next = applyToCase(project, 'S1', [override]);
		expect(next.scenarios![0]!.overrides).toEqual([override]);
		expect(next.components.find((c) => c.id === 'V1')).toMatchObject({
			resistance: { kind: 'library', id: 'RS1' }
		});
	});

	it("names the case's entry in the result's case value", () => {
		const project = onEntry('RS1');
		const text = caseValueText(
			{ labels: project, sent: project, prefs: SI_UNITS, caseWords: 'the base case' },
			{
				index: 0,
				variable: {
					kind: 'component',
					componentId: 'V1',
					field: 'resistance',
					coefficient: 'Cv',
					lower: 10,
					upper: 5000
				},
				value: 1234.5678,
				caseValue: { kind: 'library', id: 'RS1' },
				override
			} as never
		);
		expect(text).toBe('“Gate, open” (project library, Cv 900)');
	});
});
