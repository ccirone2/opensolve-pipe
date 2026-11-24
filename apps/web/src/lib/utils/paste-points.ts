/**
 * Points pasted into a curve's table (proposal usability-entry.md §6): a column, or a table of
 * two columns, copied from a spreadsheet (cells separated by tabs) or a data sheet (by spaces),
 * with or without a heading row. A heading's units ("Flow (gpm)", "Head [m]", or "gpm ft") say
 * what the columns are in, one unit per column; without any the columns are in the table's
 * display units. Every cell is read as a typed value is (units.ts parseQuantity) and checked
 * against the schema's bounds. Nothing is guessed: a heading whose units cannot be put one to a
 * column, a cell that does not read, a value out of bounds, a comma (a decimal mark, a thousands
 * separator or a list) or a third column not named as point numbers, and nothing is pasted, with
 * the reason, the row and the column named.
 */
import { boundsProblem, type Bounds } from './schema-bounds';
import {
	displayUnit,
	formatValue,
	namesUnit,
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

/** True when a cell starts as a number does, with or without a unit. */
function startsWithNumber(cell: string): boolean {
	return /^[+-]?(\d|\.\d)/.test(cell.trim());
}

/**
 * A heading row: no cell starts as a number and the row has a letter. A first row with a cell
 * such as "-" or "—" and no letter is data, refused as such, never dropped as a heading.
 */
function isHeading(cells: readonly string[]): boolean {
	return cells.length > 0 && !cells.some(startsWithNumber) && /\p{L}/u.test(cells.join(' '));
}

/** A heading cell that names a column of point numbers. */
function namesPointNumbers(cell: string | undefined): boolean {
	return /^(#|no\.?|n|nr\.?|pt\.?|point|points)$/i.test((cell ?? '').trim());
}

/**
 * The units a heading names, one per column, or null for none: each in brackets ("Flow (gpm)
 * Head [ft]"), else each word that names a unit ("gpm ft"). A heading that names units in a
 * number other than the columns' is refused: which unit goes with which column is not known.
 */
function headingUnits(line: string, width: number): (string | null)[] | { error: string } {
	const bracketed = [...line.matchAll(/[([]\s*([^()[\]]+?)\s*[)\]]/g)].map((m) => m[1] ?? '');
	const named = bracketed.length
		? bracketed
		: line.split(/[\t;]+|\s+/).filter((word) => namesUnit(word));
	if (named.length === 0) return Array.from({ length: width }, () => null);
	if (named.length !== width) {
		return {
			error: `Nothing was pasted: the heading “${line.trim()}” names ${named.length} ${named.length === 1 ? 'unit' : 'units'} (${named.join(', ')}) for ${width} ${width === 1 ? 'column' : 'columns'}. Put each column's unit in brackets after its name, “Flow (gpm)”, or leave the heading out.`
		};
	}
	return named;
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
	const heading = isHeading(first) ? first : null;
	const headingLine = heading ? (lines.split('\n')[0] ?? '') : null;
	if (heading) rows = rows.slice(1);
	if (rows.length === 0) return { ok: false, error: 'Nothing was pasted: no rows of numbers.' };

	let width = Math.max(...rows.map((row) => row.length));
	let line = headingLine;
	// Three columns whose first is headed as point numbers ("#", "No.", "Point") and numbers
	// them 1, 2, 3…: the point numbers are dropped. Without such a heading a first column
	// counting 1, 2, 3 may be flows, so three columns are refused.
	if (
		width === 3 &&
		heading &&
		namesPointNumbers(heading[0]) &&
		rows.every((row) => row.length === 3) &&
		numbered(rows)
	) {
		rows = rows.map((row) => row.slice(1));
		line = (headingLine ?? '').replace(/^\s*\S+/, '');
		width = 2;
	}
	if (width > 2) {
		return {
			ok: false,
			error: `Nothing was pasted: this table takes one column or two (${x.label}, ${y.label}), and ${width} were copied. Copy the two columns alone, or with a first column of point numbers headed “#”.`
		};
	}
	if (rows.some((row) => row.length !== width)) {
		return { ok: false, error: 'Nothing was pasted: some rows have fewer cells than others.' };
	}
	const columns: PasteColumn[] = width === 2 ? ['x', 'y'] : [at];

	// Each column's unit: its heading's, else the table's.
	const named = line === null ? null : headingUnits(line, width);
	if (named && !Array.isArray(named)) return { ok: false, error: named.error };
	const columnUnits: UnitId[] = [];
	for (const [c, column] of columns.entries()) {
		const axis = column === 'x' ? x : y;
		const shown = displayUnit(axis.category, units);
		const unit = named?.[c] ?? null;
		if (unit === null) {
			columnUnits.push(shown);
			continue;
		}
		const read = parseQuantity(`1 ${unit}`, axis.category, shown, axis.options);
		if (!read?.ok) {
			return {
				ok: false,
				error: `Nothing was pasted: the ${axis.label.toLowerCase()} column's unit in the heading, “${unit}”: ${read ? read.error : ''}`
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
