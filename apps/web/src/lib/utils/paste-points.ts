/**
 * Points pasted into a curve's table (proposal usability-entry.md §6): a column, or a table of
 * two columns, copied from a spreadsheet (cells separated by tabs, a cell with a line break in
 * quotes) or a data sheet (by spaces or semicolons), with or without a heading row.
 *
 * Nothing is guessed. The heading is read whole: every word must be a column name this table
 * knows ("Flow", "Q", "Head", "NPSHr", "Efficiency"…) or a unit (units.ts namesUnit), the units
 * one per column ("Flow (gpm) Head [ft]", or "gpm ft"), the names in the table's order; a word it
 * cannot read ("MGD", "l/sec", "Imp gpm", "n/a") refuses the paste rather than being passed over.
 * Every cell is read as a typed value is (units.ts parseQuantity), in its own unit, the heading's
 * or the table's, and checked against the schema's bounds. An empty cell, a comma, digits grouped
 * by a space ("1 000"), efficiencies that may be fractions with no unit to say so, or a third
 * column not headed as point numbers: nothing is pasted, and the reason, row and column are named.
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
	/** "Flow", "Head", "NPSHr", "Efficiency": the column's name in messages and in headings. */
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
	/** What was pasted, for the table to say: "Pasted 4 points: flow in gpm, head in ft." */
	summary: string;
}

export type PasteResult = PastedPoints | { ok: false; error: string };

const BRACKETS =
	'Put each column’s unit in brackets after its name, “Flow (gpm)”, or leave the heading out.';

/** A label in a sentence: lower case, but an acronym ("NPSHr") kept as written. */
export function inSentence(label: string): string {
	return /[A-Z].*[A-Z]/.test(label) ? label : label.toLowerCase();
}

/**
 * The words a heading may name each column by, lower case, by what the column holds. A word of
 * another column's kind than this paste's ("Efficiency" over a head curve) refuses the paste.
 */
const COLUMN_WORDS: Readonly<Record<string, readonly string[]>> = {
	flow: ['flow', 'flowrate', 'q', 'capacity', 'discharge'],
	head: ['head', 'h', 'tdh'],
	npshr: ['npsh', 'npshr', 'npsh3', 'npshre', 'npshreq'],
	efficiency: ['efficiency', 'eff', 'eff.', 'η', 'eta']
};

/** Words a heading may hold that name no column: "rate", "total", "No." and the like. */
const OTHER_WORDS = new Set([
	'rate',
	'total',
	'dynamic',
	'differential',
	'required',
	'req',
	'req.',
	'pump',
	'hydraulic',
	'overall',
	'of',
	'and',
	'at',
	'the',
	'us',
	'value',
	'values',
	'curve',
	'#',
	'no',
	'no.',
	'n',
	'nr',
	'nr.',
	'pt',
	'pt.',
	'point',
	'points'
]);

/** Units that say an efficiency column holds fractions (0.75), not percentages. */
const FRACTION_WORDS = /^(-|–|—|1|fraction|frac\.?|decimal)$/i;

/** What a column holds, from its axis: a key of COLUMN_WORDS. */
function kindOf(axis: PasteAxis): string {
	if (axis.category === 'flow') return 'flow';
	if (axis.category === 'fraction') return 'efficiency';
	return /npsh/i.test(axis.label) ? 'npshr' : 'head';
}

/** The kind a heading word names, '' for a word that names none, null for one it cannot read. */
function wordKind(word: string): string | null {
	const lower = word.toLowerCase();
	for (const [kind, words] of Object.entries(COLUMN_WORDS)) if (words.includes(lower)) return kind;
	return OTHER_WORDS.has(lower) ? '' : null;
}

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
 * Cells of tab-separated text, as a spreadsheet copies it: a cell holding a tab, a line break or
 * a quote is in quotes, a quote in it doubled. Every row is kept, an empty one too.
 */
function tabCells(text: string): string[][] {
	const rows: string[][] = [];
	let row: string[] = [];
	let cell = '';
	let quoted = false;
	for (let i = 0; i < text.length; i += 1) {
		const char = text[i] as string;
		if (quoted) {
			if (char === '"' && text[i + 1] === '"') {
				cell += '"';
				i += 1;
			} else if (char === '"') quoted = false;
			else cell += char;
		} else if (char === '"' && cell.trim() === '') {
			quoted = true;
			cell = '';
		} else if (char === '\t') {
			row.push(cell);
			cell = '';
		} else if (char === '\n') {
			row.push(cell);
			rows.push(row);
			row = [];
			cell = '';
		} else cell += char;
	}
	row.push(cell);
	rows.push(row);
	return rows.map((r) => r.map((c) => c.replace(/\s+/g, ' ').trim()));
}

/**
 * Rows of cells: by tabs when the text has any, else by runs of ASCII spaces or semicolons (a
 * no-break or thin space is part of its cell, so "1 000" with one is refused as a number). Every
 * line is a row, an empty one too, so an empty cell is never closed up.
 */
function cellsOf(text: string): string[][] | { error: string } {
	if (text.includes('\t')) return tabCells(text);
	const rows = text
		.split('\n')
		.map((line) => (line.trim() === '' ? [''] : line.trim().split(/ *; *| +/)));
	if (rows.some((row) => row.some((cell) => cell.includes(',')))) {
		return {
			error:
				'Nothing was pasted: a comma can be a decimal mark, a thousands separator or a list. Copy the points from a spreadsheet, or separate the columns with spaces or tabs and write decimals with a point.'
		};
	}
	return rows;
}

/**
 * Rows that could each be one number with its thousands grouped by a space ("1 000", "12 500"):
 * two cells, up to three digits then exactly three. A group never starts with 0, so a row such
 * as "0 150" (a curve's shutoff point) shows the rows are a table.
 */
function groupedDigits(rows: string[][]): boolean {
	return (
		rows.length > 0 &&
		rows.every(
			(row) =>
				row.length === 2 && /^[1-9]\d{0,2}$/.test(row[0] ?? '') && /^\d{3}$/.test(row[1] ?? '')
		)
	);
}

/** A first column numbered 1, 2, 3…: the point numbers of a data sheet or of this table. */
function numbered(rows: string[][]): boolean {
	return rows.every((row, i) => row[0]?.replace(/\.$/, '') === String(i + 1));
}

/**
 * Read a heading for `kinds`, the kinds of the columns pasted, in order: its units, one per
 * column or none, and its names, only of these columns and in their order. A word it cannot
 * read refuses the paste.
 */
function readHeading(
	cells: readonly string[],
	kinds: readonly string[],
	labels: readonly string[]
): { units: (string | null)[]; names: number } | { error: string } {
	const line = cells.join('\t');
	const bracketed = [...line.matchAll(/[([]\s*([^()[\]]*?)\s*[)\]]/g)].map((m) => m[1] ?? '');
	const words = line
		.replace(/[([][^()[\]]*[)\]]/g, ' ')
		.split(/[\s;]+/)
		.filter(Boolean);
	const unitWords: string[] = [];
	const named: string[] = [];
	const unread: string[] = [];
	const efficiency = kinds.includes('efficiency');
	const take = (part: string): boolean => {
		if (namesUnit(part) || (efficiency && FRACTION_WORDS.test(part))) {
			unitWords.push(part);
			return true;
		}
		const kind = wordKind(part);
		if (kind === null) return false;
		if (kind) named.push(kind);
		return true;
	};
	for (const word of words) {
		if (take(word)) continue;
		// "Q/gpm", "flow_gpm", "Head,ft": a name and a unit run together.
		const parts = word.split(/[/_,:=]+/).filter(Boolean);
		const kept = [unitWords.length, named.length] as const;
		if (parts.length > 1 && parts.every((part) => take(part))) continue;
		unitWords.length = kept[0];
		named.length = kept[1];
		unread.push(word);
	}
	if (unread.length) {
		return {
			error: `Nothing was pasted: the heading has ${unread.map((w) => `“${w}”`).join(', ')}, which this table does not read as a column’s name or a unit it takes. ${BRACKETS}`
		};
	}
	if (bracketed.length && unitWords.length) {
		return {
			error: `Nothing was pasted: the heading names units both in brackets and without (${[...bracketed, ...unitWords].join(', ')}). ${BRACKETS}`
		};
	}
	const units = bracketed.length ? bracketed : unitWords;
	if (units.length && units.length !== kinds.length) {
		return {
			error: `Nothing was pasted: the heading names ${units.length} ${units.length === 1 ? 'unit' : 'units'} (${units.join(', ')}) for ${kinds.length} ${kinds.length === 1 ? 'column' : 'columns'}. ${BRACKETS}`
		};
	}
	// The names: only the columns pasted, in their order.
	const order = [...new Set(named)];
	const want = labels.map(inSentence);
	const foreign = order.filter((kind) => !kinds.includes(kind));
	if (foreign.length) {
		return {
			error: `Nothing was pasted: the heading names ${foreign.join(' and ')}, and this paste fills ${want.join(' and ')}.`
		};
	}
	if (order.length === kinds.length && order.some((kind, i) => kind !== kinds[i])) {
		return {
			error: `Nothing was pasted: the heading names the columns in the other order. This table takes ${want.join(', then ')}.`
		};
	}
	return { units: units.length ? units : kinds.map(() => null), names: order.length };
}

/** How a column is read: in a unit of the registry, or an efficiency column as fractions. */
type ColumnReading = { unit: UnitId; stated: boolean } | { fraction: true };

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
	// Only the line breaks a spreadsheet adds after the last row are dropped: an empty line
	// before or between rows is an empty cell, refused below, never closed up.
	const body = text.replace(/\r\n?/g, '\n').replace(/[ \t]*\n\s*$/, '');
	if (!body.includes('\n') && !body.includes('\t')) return null;
	const parsed = cellsOf(body);
	if ('error' in parsed) return { ok: false, error: parsed.error };
	let rows = parsed;

	const first = rows[0] ?? [];
	let heading = isHeading(first) ? first : null;
	if (heading) rows = rows.slice(1);
	if (rows.length === 0) return { ok: false, error: 'Nothing was pasted: no rows of numbers.' };

	let width = Math.max(...rows.map((row) => row.length));
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
		heading = heading.slice(1);
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
	const axes = columns.map((column) => (column === 'x' ? x : y));

	const read = heading
		? readHeading(
				heading,
				axes.map(kindOf),
				axes.map((axis) => axis.label)
			)
		: { units: axes.map(() => null), names: 0 };
	if ('error' in read) return { ok: false, error: read.error };
	// Text split on spaces where each row could be one number with its thousands grouped by a
	// space, and no heading naming two columns to say it is a table: not guessed.
	const named = Math.max(read.names, read.units.filter((u) => u !== null).length);
	if (!body.includes('\t') && width === 2 && named < 2 && groupedDigits(rows)) {
		return {
			ok: false,
			error:
				'Nothing was pasted: each row could be one number with its thousands grouped by a space (“1 000”) or two numbers. Copy the points from a spreadsheet, write the numbers without spaces in them, or head the columns with their units, “Flow (gpm) Head (ft)”.'
		};
	}

	// Each column's unit: its heading's, else the table's.
	const readings: ColumnReading[] = [];
	for (const [c, axis] of axes.entries()) {
		const shown = displayUnit(axis.category, units);
		const named = read.units[c] ?? null;
		if (named === null) {
			readings.push({ unit: shown, stated: false });
		} else if (axis.category === 'fraction' && FRACTION_WORDS.test(named)) {
			readings.push({ fraction: true });
		} else {
			const unit = parseQuantity(`1 ${named}`, axis.category, shown, axis.options);
			if (!unit?.ok) {
				return {
					ok: false,
					error: `Nothing was pasted: the ${inSentence(axis.label)} column’s unit in the heading, “${named}”: ${unit ? unit.error : ''}`
				};
			}
			readings.push({ unit: unit.unit, stated: true });
		}
	}

	const out: { x?: number; y?: number }[] = [];
	const used: Set<string>[] = axes.map(() => new Set());
	/** Per column: true while every value was written without a unit of its own. */
	const bare: boolean[] = axes.map(() => true);
	for (const [r, row] of rows.entries()) {
		const point: { x?: number; y?: number } = {};
		for (const [c, column] of columns.entries()) {
			const axis = axes[c] as PasteAxis;
			const reading = readings[c] as ColumnReading;
			const cell = row[c] ?? '';
			const where = `row ${r + 1}, ${inSentence(axis.label)}`;
			if (cell === '') return { ok: false, error: `Nothing was pasted: ${where} is empty.` };
			let si: number;
			if ('fraction' in reading) {
				const value = parseQuantity(cell, 'dimensionless', '');
				if (!value?.ok) {
					return {
						ok: false,
						error: `Nothing was pasted: ${where}, “${cell}”: ${value ? value.error : ''}`
					};
				}
				si = value.si;
				used[c]?.add('a fraction');
			} else {
				const value = parseQuantity(cell, axis.category, reading.unit, axis.options);
				if (!value) return { ok: false, error: `Nothing was pasted: ${where} is empty.` };
				if (!value.ok) {
					return { ok: false, error: `Nothing was pasted: ${where}, “${cell}”: ${value.error}` };
				}
				if (value.converted) bare[c] = false;
				if (reading.stated && value.unit !== reading.unit) {
					return {
						ok: false,
						error: `Nothing was pasted: ${where}, “${cell}”: the heading says ${unitLabel(axis.category, reading.unit, axis.options)}.`
					};
				}
				si = value.si;
				used[c]?.add(unitLabel(axis.category, value.unit, axis.options));
			}
			const problem = boundsProblem(si, axis.bounds, (v) =>
				formatValue(v, axis.category, units, 6, axis.options)
			);
			if (problem) {
				return { ok: false, error: `Nothing was pasted: ${where}, “${cell}”: ${problem}` };
			}
			point[column] = si;
		}
		out.push(point);
	}

	// Efficiencies read in % with no unit given anywhere, all at most 1 %: they may be fractions
	// (0.75 for 75 %), which would be stored 100 times too small, so they are not guessed.
	for (const [c, axis] of axes.entries()) {
		const reading = readings[c] as ColumnReading;
		if (
			axis.category === 'fraction' &&
			!('fraction' in reading) &&
			!reading.stated &&
			bare[c] &&
			out.every((point) => (point[columns[c] as PasteColumn] ?? 1) <= 0.01)
		) {
			return {
				ok: false,
				error: `Nothing was pasted: every ${inSentence(axis.label)} is 1 % or less, so they may be fractions (0.75 for 75 %). Head the column “${axis.label} (%)” if they are percentages, or “${axis.label} (-)” if they are fractions.`
			};
		}
	}

	const described = axes.map((axis, c) => {
		const list = [...(used[c] ?? [])].filter(Boolean);
		const name = inSentence(axis.label);
		if (list.length === 0) return name;
		if (list[0] === 'a fraction') return `${name} as a fraction`;
		return `${name} in ${list.join(' and ')}`;
	});
	const summary =
		width === 2
			? `Pasted ${out.length} ${out.length === 1 ? 'point' : 'points'}: ${described.join(', ')}.`
			: `Pasted ${out.length} ${out.length === 1 ? 'value' : 'values'} of ${described[0]}.`;
	return { ok: true, rows: out, columns, summary };
}
