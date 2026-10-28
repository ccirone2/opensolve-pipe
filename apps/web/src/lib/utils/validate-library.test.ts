/**
 * Validation of the project library (CLAUDE.md D21): the published rules read from the schema
 * (`x-reference-fields`, `x-fields-by-value`, model-rules.ts), dangling references, duplicate
 * entry ids, and a valve resistance checked against the member its kind names. Made-up test
 * inputs (testing/helpers.ts libraryProject).
 */
import { describe, expect, it } from 'vitest';
import type { Project } from '../api/types';
import { libraryProject } from '../testing/helpers';
import openapi from '../api/openapi.json';
import {
	byValueViolations,
	fieldsByValue,
	FITTING_REFERENCES,
	LIBRARY_RESISTANCE_KIND,
	missingFittingParameters,
	PIPE_REFERENCES,
	referenceFields,
	referenceViolations,
	resistanceSchemaName,
	schemaOrderedFields,
	schemaOrderViolations
} from './model-rules';
import {
	modelRuleIssues,
	pipeSpecProblems,
	projectProblems,
	referenceProblems,
	resistanceSpecProblems,
	schemaProblems
} from './validate';

const schemas = openapi.components.schemas as unknown as Record<string, Record<string, unknown>>;

describe('the published rules', () => {
	it('are read from the schema, never copied', () => {
		expect(PIPE_REFERENCES).toEqual(schemas.PipeDefinition!['x-reference-fields']);
		expect(FITTING_REFERENCES).toEqual(schemas.Fitting!['x-reference-fields']);
		expect(Object.keys(PIPE_REFERENCES)).toEqual(['specId']);
		expect(PIPE_REFERENCES.specId!.replaces).toContain('materialId');
		expect(PIPE_REFERENCES.specId!.requiredWithout).toEqual(['materialId']);
		expect(FITTING_REFERENCES.resistanceId!.replaces).toEqual(['kOverride']);
		expect(referenceFields('Reservoir')).toEqual({});
		expect(fieldsByValue('PipeSpec')).toEqual(schemas.PipeSpec!['x-fields-by-value']);
		expect(fieldsByValue('ResistanceSpec')).toEqual(schemas.ResistanceSpec!['x-fields-by-value']);
		expect(fieldsByValue('Pump')).toBeNull();
		expect(schemaOrderedFields('PipeSpec')).toEqual([
			{ lower: 'innerDiameter', upper: 'outerDiameter', strict: true }
		]);
	});

	it('pick the schema of a valve resistance by its kind', () => {
		expect(resistanceSchemaName('K')).toBe('FlowCoefficient');
		expect(resistanceSchemaName('Cv')).toBe('FlowCoefficient');
		expect(resistanceSchemaName('library')).toBe('ResistanceRef');
		expect(resistanceSchemaName('point')).toBeNull();
		expect(LIBRARY_RESISTANCE_KIND).toBe('library');
	});

	it('say what a value breaks', () => {
		expect(referenceViolations({ specId: 'PS1', length: 1 }, PIPE_REFERENCES)).toEqual([]);
		expect(
			referenceViolations({ specId: 'PS1', materialId: 'custom', length: 1 }, PIPE_REFERENCES)
		).toEqual([{ reference: 'specId', given: ['materialId'], missing: [] }]);
		expect(referenceViolations({ length: 1 }, PIPE_REFERENCES)).toEqual([
			{ reference: 'specId', given: [], missing: ['materialId'] }
		]);
		// Null counts as absent, as the API's.
		expect(
			referenceViolations({ specId: 'PS1', schedule: null, length: 1 }, PIPE_REFERENCES)
		).toEqual([]);
		expect(byValueViolations({ kind: 'K', value: 1 }, 'ResistanceSpec')).toMatchObject({
			missing: ['referenceDiameter'],
			extra: []
		});
		expect(
			byValueViolations({ kind: 'Kv', value: 1, referenceDiameter: 1 }, 'ResistanceSpec')
		).toMatchObject({ missing: [], extra: ['referenceDiameter'] });
		expect(
			schemaOrderViolations({ innerDiameter: 0.2, outerDiameter: 0.1 }, 'PipeSpec')
		).toHaveLength(1);
	});

	it("let a resistanceId meet a custom fitting's need for kOverride", () => {
		expect(missingFittingParameters({ type: 'custom', quantity: 1, pipeIndex: 0 })).toEqual([
			'kOverride'
		]);
		expect(
			missingFittingParameters({ type: 'custom', quantity: 1, pipeIndex: 0, resistanceId: 'RS1' })
		).toEqual([]);
	});
});

describe('projects with a library', () => {
	it('validate against the schema, with a valve resistance checked as its kind names', () => {
		const project = libraryProject();
		expect(projectProblems(project)).toEqual([]);
		const bad = structuredClone(project) as unknown as {
			components: { resistance?: unknown }[];
		};
		bad.components[1]!.resistance = { kind: 'library' };
		expect(schemaProblems(bad)).toEqual([
			'components[1] "V1" › resistance: is missing the required field "id"'
		]);
		bad.components[1]!.resistance = { kind: 'Kv', value: -1 };
		expect(schemaProblems(bad)).toEqual(['components[1] "V1" › resistance › value: must be > 0']);
		bad.components[1]!.resistance = { kind: 'Q', value: 1 };
		expect(schemaProblems(bad)).toEqual([
			`components[1] "V1" › resistance: unknown resistance kind "Q" ('K', 'Cv' or 'Kv' as entered, or 'library': a project library entry)`
		]);
	});

	it('report dangling references with their codes, by id in text and by name in message', () => {
		const project = libraryProject();
		project.pipeLibrary = project.pipeLibrary!.filter((s) => s.id !== 'PS1');
		project.resistanceLibrary = [];
		const issues = modelRuleIssues(project);
		expect(issues.map((i) => [i.code, i.text])).toEqual([
			[
				'UNKNOWN_RESISTANCE',
				'Component "V1" refers to resistance entry "RS1", which is not in the project library.'
			],
			[
				'UNKNOWN_PIPE_SPEC',
				'Connection "L1", pipe 1 refers to pipe spec "PS1", which is not in the project library.'
			],
			[
				'UNKNOWN_RESISTANCE',
				'Connection "L1", fitting 1 (elbow_90_lr) refers to resistance entry "RS2", which is not in the project library.'
			],
			[
				'UNKNOWN_RESISTANCE',
				'Connection "L1", fitting 2 (custom) refers to resistance entry "RS1", which is not in the project library.'
			]
		]);
		expect(issues[0]!.message).toBe(
			'Gate valve V1 refers to a resistance entry the project library does not have (“RS1”): choose an entry from the library, enter its resistance, or leave it on its default.'
		);
		expect(issues[1]).toMatchObject({ connectionId: 'L1', pipeIndex: 0, componentId: 'R1' });
		// A project with dangling references still opens (the solver reports them, 422).
		expect(referenceProblems(project)).toEqual([]);
	});

	it('report a reference beside the values it stands in for, and a pipe with neither', () => {
		const project = libraryProject();
		const pipes = project.connections[0]!.piping.pipes;
		pipes[0] = { specId: 'PS1', materialId: 'custom', innerDiameter: 0.1, length: 30 };
		pipes[1] = { length: 12 };
		project.connections[0]!.piping.fittings[1]!.kOverride = 2;
		expect(modelRuleIssues(project).map((i) => i.message)).toEqual([
			'Piping Upper tank → Gate valve V1, pipe 1: a pipe of a project library spec takes no material and inner diameter of its own: the spec gives them.',
			'Piping Upper tank → Gate valve V1, pipe 2: a pipe needs a material, or a pipe spec of the project library.',
			'Piping Upper tank → Gate valve V1, fitting 2 (custom fitting (enter k)) takes its K from the project library and has a K value of its own too: keep one.'
		]);
		expect(modelRuleIssues(project).map((i) => i.text)).toEqual([
			'Connection "L1", pipe 1: materialId and innerDiameter cannot be given with specId: the project library entry gives them.',
			'Connection "L1", pipe 2: materialId is required without specId.',
			'Connection "L1", fitting 2 (custom): kOverride cannot be given with resistanceId: the project library entry gives them.'
		]);
	});

	it("report the entries' own rules, and their duplicate ids as structural problems", () => {
		const project = libraryProject() as Project;
		project.pipeLibrary![1] = { ...project.pipeLibrary![1]!, roughness: null };
		project.resistanceLibrary![0] = { ...project.resistanceLibrary![0]!, referenceDiameter: 0.1 };
		expect(modelRuleIssues(project).map((i) => i.message)).toEqual([
			'Pipe spec “Lined 80 mm” in the project library: a custom pipe spec needs its roughness.',
			'Resistance entry “Gate, open” in the project library: a Cv entry takes no reference diameter (it needs no bore).'
		]);
		const twice = libraryProject();
		twice.pipeLibrary!.push({ ...twice.pipeLibrary![0]! });
		twice.resistanceLibrary!.push({ ...twice.resistanceLibrary![1]! });
		expect(referenceProblems(twice)).toEqual([
			'Pipe spec id "PS1" is used more than once.',
			'Resistance entry id "RS2" is used more than once.'
		]);
	});

	it('entry forms get the schema problems, then the rules', () => {
		expect(
			pipeSpecProblems({
				id: 'PS3',
				name: 'x',
				source: 's',
				materialId: 'custom',
				innerDiameter: 0.1,
				roughness: 0
			})
		).toEqual([]);
		expect(
			pipeSpecProblems({
				id: 'PS3',
				name: 'x',
				source: '  ',
				materialId: 'custom',
				innerDiameter: 0.1
			})
		).toEqual(['source: must match pattern "\\S"']);
		expect(
			pipeSpecProblems({
				id: 'PS3',
				name: 'x',
				source: 's',
				materialId: 'custom',
				innerDiameter: 0.1
			})
		).toEqual(['a custom pipe spec needs its roughness']);
		expect(resistanceSpecProblems({ id: 'RS3', name: 'x', source: 's', kind: 'Cv' })).toEqual([
			'project: is missing the required field "value"'
		]);
		expect(
			resistanceSpecProblems({ id: 'RS3', name: 'x', source: 's', kind: 'K', value: 2 })
		).toEqual(['a K entry needs its reference diameter (a K is stated at a bore)']);
	});
});
