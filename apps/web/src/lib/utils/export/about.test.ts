/**
 * The Methods text names a case by its stored name and id, with the name it was solved under when
 * a rename came after the solve (CLAUDE.md D24, proposal pump-lineups.md §5, §6, §10.1 "L1a,
 * workspace"): a rename leaves the case current, so its response keeps the old name. Over the
 * shared fixture (real API responses, export-input.json); only the stored name is changed here.
 */
import { describe, expect, it } from 'vitest';
import { scenariosOf, withScenarios } from '../scenarios';
import { fixtureInput, readSheet } from './export-testing.testing';
import { buildExport, type ExportInput } from './model';

/** The input with scenario `id` renamed after its solve (its response keeps the old name). */
function renamedAfterSolve(input: ExportInput, id: string, name: string): ExportInput {
	return {
		...input,
		project: withScenarios(
			input.project,
			scenariosOf(input.project).map((s) => (s.id === id ? { ...s, name } : s))
		),
		cases: input.cases.map((c) => (c.id === id ? { ...c, name } : c))
	};
}

const caseLines = (input: ExportInput) =>
	readSheet(buildExport(input), 'methods')
		.column('Text')
		.filter((line) => String(line).startsWith('Case: '));

describe('the Methods text names each case', () => {
	it('by its stored name and id, as solved when they are the same', () => {
		expect(caseLines(fixtureInput('scenarios'))).toEqual([
			'Case: base case',
			'Case: scenario Cv valve (S1)',
			'Case: scenario Supply at AF1 (S2)'
		]);
	});

	it('with the name it was solved under after a rename', () => {
		const input = renamedAfterSolve(fixtureInput('scenarios'), 'S1', 'Valve on Cv, renamed');
		expect(input.cases.find((c) => c.id === 'S1')?.response?.scenario?.name).toBe('Cv valve');
		expect(caseLines(input)).toEqual([
			'Case: base case',
			'Case: scenario Valve on Cv, renamed (S1), solved as «Cv valve»',
			'Case: scenario Supply at AF1 (S2)'
		]);
	});
});
