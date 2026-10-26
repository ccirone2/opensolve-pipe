/**
 * Helpers for the export's tests (not used by the app): the shared fixture's inputs (real API
 * responses, export-input.json), and a bundle's sheets read back by header label.
 */
import fixture from '../__fixtures__/export-input.json';
import type { CellValue, ExportBundle, ExportInput, ExportSheet } from './model';
import { columnHeader } from './csv';

type FixtureCase = { name: string; input: Omit<ExportInput, 'now'> & { now: string } };

/** The fixture's cases by name. */
export const FIXTURE_NAMES = (fixture as unknown as { cases: FixtureCase[] }).cases.map(
	(c) => c.name
);

/** A fixture case's ExportInput (a fresh copy each time), with `now` as a Date. */
export function fixtureInput(
	name: string,
	options: Partial<ExportInput['options']> = {}
): ExportInput {
	const found = (fixture as unknown as { cases: FixtureCase[] }).cases.find((c) => c.name === name);
	if (!found) throw new Error(`No fixture case ${name}`);
	const input = structuredClone(found.input);
	return {
		...(input as unknown as ExportInput),
		now: new Date(input.now),
		options: { ...input.options, ...options }
	};
}

/** A sheet of a bundle, read back: its header labels (without units) and rows. */
export interface ReadSheet {
	sheet: ExportSheet;
	labels: string[];
	headers: string[];
	rows: CellValue[][];
	/** The cell of `row` under the column labelled `label` (its label without the unit). */
	get(row: readonly CellValue[], label: string): CellValue;
	/** Every row's cell under `label`. */
	column(label: string): CellValue[];
}

export function readSheet(bundle: ExportBundle, id: string): ReadSheet {
	const sheet = bundle.sheets.find((s) => s.id === id);
	if (!sheet)
		throw new Error(`No sheet ${id} (sheets: ${bundle.sheets.map((s) => s.id).join(', ')})`);
	const labels = sheet.columns.map((c) => c.label);
	const rows = [...sheet.rows()].map((r) => [...r]);
	const index = (label: string) => {
		const i = labels.indexOf(label);
		if (i < 0) throw new Error(`No column ${label} in ${id} (${labels.join(' | ')})`);
		return i;
	};
	return {
		sheet,
		labels,
		headers: sheet.columns.map(columnHeader),
		rows,
		get: (row, label) => row[index(label)] ?? null,
		column: (label) => rows.map((r) => r[index(label)] ?? null)
	};
}

export function sheetIds(bundle: ExportBundle): string[] {
	return bundle.sheets.map((s) => s.id);
}
