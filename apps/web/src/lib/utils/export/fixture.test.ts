/**
 * The committed fixture workbook (proposal export.md §7.2): the real model and writer build the
 * workbook of the shared fixture's `scenarios` case (real API responses: export-input.json, from
 * apps/api/tests/fixtures/export_input.py), and its bytes must equal the committed
 * `__fixtures__/export-results.xlsx`, and its typed cells the committed
 * `export-results.expected.json`: every cell (sheet, reference, type, value), with each sheet's
 * caption, headers, autofilter range, frozen pane and print titles. An API test reads the committed
 * workbook with openpyxl (an independent SpreadsheetML reader) against the same JSON.
 *
 *     cd apps/web && UPDATE_FIXTURES=1 pnpm exec vitest run src/lib/utils/export/fixture.test.ts
 *
 * writes both instead, so this test fails while they are stale. Every other fixture case is built
 * in both formats here too, and the CSV zip's layout checked.
 */
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { columnHeader } from './csv';
import { fixtureInput, FIXTURE_NAMES } from './export-testing.testing';
import { buildExport, type ExportBundle } from './model';
import { CELL_LIMIT, columnName, HEADER_ROWS, writeXlsx } from './xlsx';
import { blobBytes, entryText, readZip } from './zip-reader.testing';
import { writeCsvZip } from './csv';

const UPDATE = process.env.UPDATE_FIXTURES === '1';
const WORKBOOK = fileURLToPath(new URL('../__fixtures__/export-results.xlsx', import.meta.url));
const EXPECTED = fileURLToPath(
	new URL('../__fixtures__/export-results.expected.json', import.meta.url)
);
/** The fixture case whose workbook is committed. */
const COMMITTED = 'scenarios';

type CellType = 's' | 'n' | 'b';

interface ExpectedWorkbook {
	generatedBy: string;
	input: string;
	sheets: {
		name: string;
		caption: string;
		headers: string[];
		rows: number;
		autoFilter: string;
		freezePanes: string;
		printTitleRows: string;
	}[];
	cells: { sheet: string; ref: string; type: CellType; value: string | number | boolean }[];
}

// eslint-disable-next-line no-control-regex -- the characters XML 1.0 forbids
const FORBIDDEN = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\uFFFE\uFFFF]/;

/** What a correct reader returns from the workbook of `bundle`: every cell, typed. */
function expectedOf(bundle: ExportBundle): ExpectedWorkbook {
	const cells: ExpectedWorkbook['cells'] = [];
	const sheets: ExpectedWorkbook['sheets'] = [];
	for (const sheet of bundle.sheets) {
		const headers = sheet.columns.map(columnHeader);
		const last = columnName(sheet.columns.length - 1);
		const add = (r: number, values: readonly unknown[]) =>
			values.forEach((value, i) => {
				if (value === null || value === undefined) return;
				const type: CellType =
					typeof value === 'number' ? 'n' : typeof value === 'boolean' ? 'b' : 's';
				if (typeof value === 'string') {
					// The texts of the fixture need none of the writer's cuts or removals.
					expect(FORBIDDEN.test(value)).toBe(false);
					expect(value.length).toBeLessThanOrEqual(CELL_LIMIT);
				}
				cells.push({
					sheet: sheet.title,
					ref: `${columnName(i)}${r}`,
					type,
					value: value as string | number | boolean
				});
			});
		add(1, [sheet.caption]);
		add(3, headers);
		let r = HEADER_ROWS;
		for (const row of sheet.rows()) add(++r, row);
		sheets.push({
			name: sheet.title,
			caption: sheet.caption,
			headers,
			rows: sheet.rowCount,
			autoFilter: `A3:${last}${HEADER_ROWS + sheet.rowCount}`,
			freezePanes: 'A4',
			printTitleRows: '$1:$3'
		});
	}
	return {
		generatedBy: 'apps/web/src/lib/utils/export/fixture.test.ts (UPDATE_FIXTURES=1)',
		input: COMMITTED,
		sheets,
		cells
	};
}

async function formatted(json: unknown): Promise<string> {
	const prettier = await import('prettier');
	const config = (await prettier.resolveConfig(EXPECTED)) ?? {};
	return prettier.format(JSON.stringify(json), { ...config, filepath: EXPECTED });
}

describe('the committed fixture workbook', () => {
	it('is what the model and the writer make of the fixture, byte for byte and cell by cell', async () => {
		const bundle = buildExport(fixtureInput(COMMITTED));
		const bytes = await blobBytes(await writeXlsx(bundle));
		const expected = expectedOf(bundle);
		if (UPDATE) {
			writeFileSync(WORKBOOK, bytes);
			writeFileSync(EXPECTED, await formatted(expected));
		}
		expect(existsSync(WORKBOOK), 'run with UPDATE_FIXTURES=1 to write it').toBe(true);
		expect(new Uint8Array(readFileSync(WORKBOOK))).toEqual(bytes);
		expect(JSON.parse(readFileSync(EXPECTED, 'utf8'))).toEqual(expected);
	});

	it('holds what the reader checks: names, a formula-like name, _x0041_x0042_ and a CR, every type', () => {
		const expected = JSON.parse(readFileSync(EXPECTED, 'utf8')) as ExpectedWorkbook;
		expect(expected.sheets.map((s) => s.name)).toEqual([
			'About',
			'Flags',
			'Compare cases',
			'Nodes',
			'Links',
			'Pipes',
			'Fittings',
			'Valves',
			'Equipment',
			'Orifice plates',
			'Branches',
			'Branch ports',
			'Boundaries',
			'Boundary ports',
			'Assigned flows',
			'Scenario changes',
			'Methods'
		]);
		const values = expected.cells.map((c) => c.value);
		expect(values).toContain('=HYPERLINK("https://example.com","Demand")');
		expect(values).toContain('Low tank_x0041_x0042_\r(B)');
		expect(new Set(expected.cells.map((c) => c.type))).toEqual(new Set(['s', 'n', 'b']));
	});
});

describe('every fixture case', () => {
	it.each(FIXTURE_NAMES)('%s: a workbook and a CSV zip, with README.txt first', async (name) => {
		const xlsx = readZip(await blobBytes(await writeXlsx(buildExport(fixtureInput(name)))));
		expect(xlsx[0]!.name).toBe('[Content_Types].xml');
		const bundle = buildExport(fixtureInput(name, { format: 'csv' }));
		expect(bundle.folder).toBe('results 2026-10-25 1432');
		const zip = readZip(await blobBytes(await writeCsvZip(bundle)));
		const names = zip.map((e) => e.name);
		expect(names[0]).toBe('results 2026-10-25 1432/README.txt');
		expect(names.every((n) => n.startsWith('results 2026-10-25 1432/'))).toBe(true);
		expect(names.slice(1)).toEqual(bundle.sheets.map((s) => `results 2026-10-25 1432/${s.file}`));
		const readme = entryText(zip, names[0]!);
		expect(readme.startsWith('OpenSolve Pipe results\r\nProject: ')).toBe(true);
		expect(readme).toContain('\r\nExported at: 2026-10-25T14:32:05+02:00\r\n');
		expect(readme).toContain(
			'These CSV files use a comma between fields and a point as the decimal mark (101.325 is about a hundred).'
		);
		expect(
			readme.endsWith('The record of the cases, the solves and the software is in about.csv.\r\n')
		).toBe(true);
		const about = entryText(zip, 'results 2026-10-25 1432/about.csv').split('\r\n');
		expect(about[0]).toBe('\uFEFFSection,Item,Value');
		expect(about[1]!.startsWith('Reading this file,Decimal mark,')).toBe(true);
		const nodes = entryText(zip, 'results 2026-10-25 1432/nodes.csv');
		expect(nodes.startsWith('\uFEFF')).toBe(true);
		expect(nodes.endsWith('\r\n')).toBe(true);
	});
});
