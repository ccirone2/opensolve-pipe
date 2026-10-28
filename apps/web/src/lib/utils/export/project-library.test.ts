/**
 * The export's Project library sheet and entry columns (CLAUDE.md D21, proposal
 * project-library.md §5.3), on the shared fixture's `project-library` case (real API responses:
 * export_input.py, a line whose pipes, valve and fittings refer to the project library, with an
 * entry of each list that nothing uses, and a scenario S1 that points the valve at another entry
 * and gives a pipe its own values): every entry of each case as solved, its values as entered
 * (SI cells the stored doubles bit for bit, display cells `fromSI` of them), its source and its
 * users; the Pipes, Fittings and Valves sheets name each element's entry; About says so. A file
 * without a library has none of it (every other fixture case).
 */
import { describe, expect, it } from 'vitest';
import { displayUnit, fromSI } from '../units';
import { fixtureInput, FIXTURE_NAMES, readSheet, sheetIds } from './export-testing.testing';
import { buildExport } from './model';
import { csvLine } from './csv';
import { exportContext } from './context';

const NAME = 'project-library';

describe('a file with a project library', () => {
	it('has the Project library sheet after the element tables, and one About line', () => {
		const bundle = buildExport(fixtureInput(NAME));
		const ids = sheetIds(bundle);
		expect(ids).toContain('project-library');
		expect(ids.indexOf('project-library')).toBe(ids.indexOf('scenario-changes') - 1);
		expect(ids.indexOf('project-library')).toBeGreaterThan(ids.indexOf('valves'));
		const about = readSheet(bundle, 'about');
		const lines = about.rows.filter((r) => r[1] === 'Project library');
		expect(lines).toHaveLength(1);
		expect(String(lines[0]![2])).toMatch(/^The Project library sheet lists/);
		expect(about.rows.some((r) => r[1] === 'Sheet: Project library' && r[2] === 14)).toBe(true);
	});

	it('lists every entry of each case as solved, with its values, source and users', () => {
		const input = fixtureInput(NAME, { units: 'si' });
		const t = readSheet(buildExport(input), 'project-library');
		expect(t.labels).toEqual([
			'Case id',
			'Case',
			'Solved at',
			'Results',
			'List',
			'Entry id',
			'Entry',
			'Material id',
			'Material',
			'Nominal size',
			'Inner diameter',
			'Outer diameter',
			'Roughness',
			'Roughness from',
			'Coefficient kind',
			'Coefficient (as entered)',
			'Reference diameter (K)',
			'Source',
			'Used by (count)',
			'Used by',
			'Used by (ids)'
		]);
		const project = input.project;
		const rowsOf = (caseId: string | null) =>
			t.rows.filter((r) => r[0] === caseId).map((r) => t.get(r, 'Entry id'));
		expect(rowsOf(null)).toEqual(['PS1', 'PS2', 'PS3', 'RS1', 'RS2', 'RS3', 'RS4']);
		expect(rowsOf('S1')).toEqual(['PS1', 'PS2', 'PS3', 'RS1', 'RS2', 'RS3', 'RS4']);
		const row = (caseId: string | null, id: string) =>
			t.rows.find((r) => r[0] === caseId && t.get(r, 'Entry id') === id)!;
		// SI cells are the stored doubles, bit for bit.
		for (const spec of project.pipeLibrary!) {
			const r = row(null, spec.id);
			expect(t.get(r, 'Entry')).toBe(spec.name);
			expect(t.get(r, 'Material id')).toBe(spec.materialId);
			expect(t.get(r, 'Inner diameter')).toBe(spec.innerDiameter);
			expect(t.get(r, 'Outer diameter')).toBe(spec.outerDiameter ?? null);
			expect(t.get(r, 'Roughness')).toBe(spec.roughness ?? null);
			expect(t.get(r, 'Source')).toBe(spec.source);
		}
		for (const entry of project.resistanceLibrary!) {
			const r = row(null, entry.id);
			expect(t.get(r, 'Coefficient kind')).toBe(entry.kind);
			expect(t.get(r, 'Coefficient (as entered)')).toBe(entry.value);
			expect(t.get(r, 'Reference diameter (K)')).toBe(entry.referenceDiameter ?? null);
		}
		expect(t.get(row(null, 'PS1'), 'Roughness from')).toMatch(/computed by the server$/);
		expect(t.get(row(null, 'PS2'), 'Roughness from')).toBe('The entry');
		// Users, in the case as solved: S1 points the valve at RS3 and gives L2's first pipe its own values.
		const users = (caseId: string | null, id: string) => [
			t.get(row(caseId, id), 'Used by (count)'),
			t.get(row(caseId, id), 'Used by (ids)')
		];
		expect(users(null, 'PS1')).toEqual([2, 'L1 pipe 1; L1 pipe 2']);
		expect(users(null, 'PS2')).toEqual([1, 'L2 pipe 1']);
		expect(users('S1', 'PS2')).toEqual([0, null]);
		expect(users(null, 'PS3')).toEqual([0, null]);
		expect(users(null, 'RS1')).toEqual([1, 'V1']);
		expect(users('S1', 'RS1')).toEqual([0, null]);
		expect(users(null, 'RS3')).toEqual([1, 'L1 fitting 3']);
		expect(users('S1', 'RS3')).toEqual([2, 'V1; L1 fitting 3']);
		expect(users(null, 'RS4')).toEqual([0, null]);
		expect(t.get(row(null, 'RS3'), 'Used by')).toBe(
			'Fitting 3 (Custom fitting (user K)) of Upper tank → Isolation valve'
		);
	});

	it('writes diameters in the display unit, fromSI of the stored value, and a Cv as entered', () => {
		const input = fixtureInput(NAME, { units: 'display' });
		const t = readSheet(buildExport(input), 'project-library');
		const mm = displayUnit('diameter', input.prefs);
		const spec = input.project.pipeLibrary![1]!;
		const r = t.rows.find((x) => x[0] === null && t.get(x, 'Entry id') === spec.id)!;
		expect(t.get(r, 'Inner diameter')).toBe(fromSI(spec.innerDiameter, mm));
		expect(t.get(r, 'Roughness')).toBe(fromSI(spec.roughness!, mm));
		const cv = t.rows.find((x) => x[0] === null && t.get(x, 'Entry id') === 'RS3')!;
		expect(t.get(cv, 'Coefficient (as entered)')).toBe(350);
		expect(t.headers).toContain('Inner diameter [mm]');
	});

	it('names the entry of each pipe, fitting and valve, as each case was solved', () => {
		const bundle = buildExport(fixtureInput(NAME));
		const pipes = readSheet(bundle, 'pipes');
		expect(
			pipes.rows.map((r) => [
				r[0],
				t(pipes, r, 'Connection id'),
				t(pipes, r, 'Pipe #'),
				t(pipes, r, 'Pipe spec id'),
				t(pipes, r, 'Pipe spec')
			])
		).toEqual([
			[null, 'L1', 1, 'PS1', 'NPS 3 carbon steel, measured bore'],
			[null, 'L1', 2, 'PS1', 'NPS 3 carbon steel, measured bore'],
			[null, 'L2', 1, 'PS2', 'Lined 80 mm'],
			[null, 'L2', 2, null, null],
			['S1', 'L1', 1, 'PS1', 'NPS 3 carbon steel, measured bore'],
			['S1', 'L1', 2, 'PS1', 'NPS 3 carbon steel, measured bore'],
			['S1', 'L2', 1, null, null],
			['S1', 'L2', 2, null, null]
		]);
		// A spec pipe's material and nominal size are its spec's.
		expect(pipes.get(pipes.rows[0]!, 'Material')).toBe('Carbon steel');
		expect(pipes.get(pipes.rows[0]!, 'Nominal size')).toBe('NPS 3');
		expect(pipes.get(pipes.rows[2]!, 'Material')).toBe('Custom pipe');
		const fittings = readSheet(bundle, 'fittings');
		expect(fittings.column('Resistance entry id')).toEqual([
			null,
			'RS2',
			'RS3',
			null,
			null,
			'RS2',
			'RS3',
			null
		]);
		const valves = readSheet(bundle, 'valves');
		expect(
			valves.rows.map((r) => [
				r[0],
				valves.get(r, 'Resistance entry id'),
				valves.get(r, 'Resistance entry')
			])
		).toEqual([
			[null, 'RS1', '3 in butterfly valve, open'],
			['S1', 'RS3', 'Basket strainer']
		]);
		const changes = readSheet(bundle, 'scenario-changes');
		expect(changes.column('Value')).toEqual([
			'Project library RS3 “Basket strainer”',
			'Custom pipe, inner diameter 80 mm, roughness 0.01 mm'
		]);
		expect(changes.column('Base value')).toEqual([
			'Project library RS1 “3 in butterfly valve, open”',
			'“Lined 80 mm” (project library pipe spec)'
		]);
	});

	it('guards a source that reads as a formula in CSV, as every text cell', () => {
		const input = fixtureInput(NAME, { format: 'csv' });
		input.project.pipeLibrary![0]!.source = '=HYPERLINK("x")';
		for (const c of input.cases) if (c.inputs) c.inputs.pipeLibrary![0]!.source = '=HYPERLINK("x")';
		const sheet = buildExport(input).sheets.find((s) => s.id === 'project-library')!;
		const first = [...sheet.rows()][0]!;
		expect(csvLine(sheet.columns, first)).toContain(`"'=HYPERLINK(""x"")"`);
	});
});

/** A cell of `sheet`'s row under `label`. */
function t(sheet: ReturnType<typeof readSheet>, row: readonly unknown[], label: string) {
	return sheet.get(row as never, label);
}

describe('a file without a project library', () => {
	it('is as before: no sheet, no entry columns, no About line', () => {
		for (const name of FIXTURE_NAMES.filter((n) => n !== NAME)) {
			for (const cases of ['shown', 'all'] as const) {
				const input = fixtureInput(name, { cases });
				expect(exportContext(input).library, name).toBe(false);
				const bundle = buildExport(input);
				expect(sheetIds(bundle), name).not.toContain('project-library');
				for (const sheet of bundle.sheets) {
					for (const column of sheet.columns) {
						expect(column.label, `${name} ${sheet.id}`).not.toMatch(/Pipe spec|Resistance entry/);
					}
				}
				const about = readSheet(bundle, 'about');
				expect(
					about.rows.some((r) => r[1] === 'Project library'),
					name
				).toBe(false);
			}
		}
	});
});
