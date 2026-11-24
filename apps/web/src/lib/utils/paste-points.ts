/**
 * Points pasted into a curve's table (proposal usability-entry.md §6): a column, or a table of
 * two columns, copied from a spreadsheet (cells separated by tabs) or a data sheet (by spaces),
 * with or without a heading row. A heading's unit ("Flow (gpm)", "Head [m]") says what the column
 * is in; without one the column is in the table's display unit. Every cell is read as a typed
 * value is (units.ts parseQuantity) and checked against the schema's bounds: one cell that does
 * not read, or one out of bounds, and nothing is pasted, with the row and column named. Nothing
 * is guessed: a comma could be a decimal mark, a thousands separator or a list, so it is refused.
 */
import { boundsProblem, type Bounds } from './schema-bounds';
import {
	displayUnit,
	formatValue,
	parseQuantity,
	unitLabel,
	type LabelOptions,
	type UnitCategory,
	type UnitId
} from './units';
import type { UnitPreferences } from '../api/types';

export interface PasteAxis {
	/** "Flow", "Head": the column's name in messages. */
	label: string;
	category: UnitCategory;
	bounds: Bounds;
	options?: LabelOptions;
}

export type PasteColumn = 'x' | 'y';

export interface PastedPoints {
	ok: true;
	/** One entry per pasted row, in order: the columns pasted, SI. */
	rows: { x?: number; y?: number }[];
	/** The columns the paste fills: one, or both. */
	columns: PasteColumn[];
	/** What was pasted, for the table to say: "7 points: flow in gpm, head in ft." */
	summary: string;
}

export type PasteResult = PastedPoints | { ok: false; error: string };

/** The unit a heading names in brackets at its end: "Flow (gpm)" → "gpm". */
function headingUnit(heading: string): string | null {
	const match = /[([]\s*([^()[\]]+?)\s*[)\]]\s*$/.exec(heading);
	return match?.[1] ?? null;
}

/** True when a cell reads as a number, with or without a unit (not a heading). */
function startsWithNumber(cell: string): boolean {
	return /^[+-]?(\d|\.\d)/.test(cell.trim());
}

/** Rows of cells: by tabs when the text has any, else by runs of spaces or semicolons. */
function cellsOf(text: string): string[][] | { error: string } {
	const lines = text
		.replace(/\r\n?/g, '\n')
		.split('\n')
		.map((line) => line.trim())
		.filter((line) => line !== '');
	const tabbed = lines.some((line) => line.includes('\t'));
	const rows = lines.map((line) =>
		(tabbed ? line.split('\t') : line.split(/\s*;\s*|\s+/)).map((cell) => cell.trim())
	);
	if (!tabbed && rows.some((row) => row.some((cell) => cell.includes(',')))) {
		return {
			error:
				'Nothing was pasted: a comma can be a decimal mark, a thousands separator or a list. Copy the points from a spreadsheet, or separate the columns with spaces or tabs and write decimals with a point.'
		};
	}
	return rows;
}

/** A first column numbered 1, 2, 3…: the point numbers of a data sheet or of this table. */
function numbered(rows: string[][]): boolean {
	return rows.every((row, i) => row[0]?.replace(/\.$/, '') === String(i + 1));
}

/**
 * Read pasted text for a points table. `at` is the column of the cell pasted into: a single
 * column fills it, two columns fill both. Returns null for text that is one value (no tab, one
 * line): the field takes that paste as typed text.
 */
export function readPastedPoints(
	text: string,
	at: PasteColumn,
	x: PasteAxis,
	y: PasteAxis,
	units: UnitPreferences
): PasteResult | null {
	const lines = text.replace(/\r\n?/g, '\n').trim();
	if (!lines.includes('\n') && !lines.includes('\t')) return null;
	const parsed = cellsOf(lines);
	if ('error' in parsed) return { ok: false, error: parsed.error };
	let rows = parsed;

	const first = rows[0] ?? [];
	const heading = first.length > 0 && !first.every(startsWithNumber) ? first : null;
	if (heading) rows = rows.slice(1);
	if (rows.length === 0) return { ok: false, error: 'Nothing was pasted: no rows of numbers.' };

	let width = Math.max(...rows.map((row) => row.length));
	let headings = heading;
	// A table of three columns whose first numbers the points: the point numbers are dropped.
	if (width === 3 && rows.every((row) => row.length === 3) && numbered(rows)) {
		rows = rows.map((row) => row.slice(1));
		headings = headings ? headings.slice(-2) : null;
		width = 2;
	}
	if (width > 2) {
		return {
			ok: false,
			error: `Nothing was pasted: this table takes one column or two (${x.label}, ${y.label}), and ${width} were copied.`
		};
	}
	if (rows.some((row) => row.length !== width)) {
		return { ok: false, error: 'Nothing was pasted: some rows have fewer cells than others.' };
	}
	const columns: PasteColumn[] = width === 2 ? ['x', 'y'] : [at];
	if (headings && headings.length !== width) headings = null;

	// Each column's unit: its heading's, else the table's.
	const columnUnits: UnitId[] = [];
	for (const [c, column] of columns.entries()) {
		const axis = column === 'x' ? x : y;
		const shown = displayUnit(axis.category, units);
		const named = headings?.[c] ? headingUnit(headings[c]) : null;
		if (!named) {
			columnUnits.push(shown);
			continue;
		}
		const read = parseQuantity(`1 ${named}`, axis.category, shown, axis.options);
		if (!read?.ok) {
			return {
				ok: false,
				error: `Nothing was pasted: the heading “${headings?.[c] ?? ''}”: ${read ? read.error : ''}`
			};
		}
		columnUnits.push(read.unit);
	}

	const out: { x?: number; y?: number }[] = [];
	for (const [r, row] of rows.entries()) {
		const point: { x?: number; y?: number } = {};
		for (const [c, column] of columns.entries()) {
			const axis = column === 'x' ? x : y;
			const unit = columnUnits[c] as UnitId;
			const cell = row[c] ?? '';
			const where = `row ${r + 1}, ${axis.label.toLowerCase()}`;
			const read = parseQuantity(cell, axis.category, unit, axis.options);
			if (!read) return { ok: false, error: `Nothing was pasted: ${where} is empty.` };
			if (!read.ok)
				return { ok: false, error: `Nothing was pasted: ${where}, “${cell}”: ${read.error}` };
			const problem = boundsProblem(read.si, axis.bounds, (si) =>
				formatValue(si, axis.category, units, 6, axis.options)
			);
			if (problem)
				return { ok: false, error: `Nothing was pasted: ${where}, “${cell}”: ${problem}` };
			point[column] = read.si;
		}
		out.push(point);
	}

	const described = columns.map((column, c) => {
		const axis = column === 'x' ? x : y;
		const label = unitLabel(axis.category, columnUnits[c] as UnitId, axis.options);
		return label ? `${axis.label.toLowerCase()} in ${label}` : axis.label.toLowerCase();
	});
	const count = `${out.length} ${out.length === 1 ? 'value' : 'values'}`;
	const summary =
		width === 2
			? `Pasted ${out.length} ${out.length === 1 ? 'point' : 'points'}: ${described.join(', ')}.`
			: `Pasted ${count} of ${described[0]}.`;
	return { ok: true, rows: out, columns, summary };
}
