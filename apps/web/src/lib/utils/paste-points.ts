/**
 * Points pasted into a curve's table (proposal usability-entry.md §6): a column, or a table of
 * two columns, copied from a spreadsheet (cells separated by tabs, a cell with a line break in
 * quotes) or a data sheet (by spaces or semicolons), with or without a heading of one or two rows.
 *
 * Nothing is guessed. The heading is read whole: every word must be a column name this table
 * knows ("Flow", "Q", "Head", "NPSHr", "Efficiency"…), a word that names no column, a point-number
 * word over a dropped first column, or a unit (units.ts namesUnit). The units are one per column
 * ("Flow (gpm) Head [ft]", or "gpm ft"); the names, where any is given, name every column pasted,
 * each over its own column; a word it cannot read ("MGD", "l/sec", "Imp gpm", "n/a") refuses the
 * paste rather than being passed over. Every cell is read as a typed value is (units.ts
 * parseQuantity), in its own unit, the heading's or the table's, and checked against the schema's
 * bounds. An empty cell, a comma in the data, digits that could be grouped by a space ("1 000",
 * "1 000.5"), efficiencies that may be fractions with no unit to say so, or a third column not
 * headed as point numbers: nothing is pasted, and the reason, row and column are named.
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
 * another column's kind than the one under it refuses the paste ("Efficiency" over a head
 * curve). "Discharge" is none of them: "discharge head" and "discharge pressure" are heads.
 */
const COLUMN_WORDS: Readonly<Record<string, readonly string[]>> = {
	flow: ['flow', 'flowrate', 'flow-rate', 'rate', 'q', 'capacity'],
	head: ['head', 'h', 'tdh'],
	npshr: ['npsh', 'npshr', 'npsh3', 'npshre', 'npshreq'],
	efficiency: ['efficiency', 'eff', 'eff.', 'η', 'eta']
};

/** Words that name point numbers: allowed only over a first column that is dropped. */
const POINT_WORDS = new Set(['#', 'no', 'no.', 'n', 'nr', 'nr.', 'pt', 'pt.', 'point', 'points']);

/** Words a heading may hold that name no column: "rate", "total", "developed" and the like. */
const OTHER_WORDS = new Set([
	'total',
	'dynamic',
	'differential',
	'developed',
	'required',
	'req',
	'req.',
	"req'd",
	'req’d',
	'pump',
	'bowl',
	'hydraulic',
	'overall',
	'of',
	'and',
	'at',
	'the',
	'us',
	'u.s.',
	'value',
	'values',
	'curve'
]);

/**
 * Units that say an efficiency column holds fractions (0.75), not percentages: in brackets
 * ("(-)", "[1]", "(fraction)"); as a bare word only a word ("fraction"), since a bare dash in a
 * heading ("Pump - efficiency") is punctuation.
 */
const FRACTION_WORDS = /^(-|–|—|1|fraction|frac\.?|decimal)$/i;
const FRACTION_WORD = /^(fraction|frac\.?|decimal)$/i;

/** The columns' names in messages, by kind. */
const KIND_NAMES: Readonly<Record<string, string>> = {
	flow: 'flow',
	head: 'head',
	npshr: 'NPSHr',
	efficiency: 'efficiency'
};

/** A second heading row of units alone, with no letter: "%", "(%)", "(-)", "[-]". */
function isUnitsRow(cells: readonly string[]): boolean {
	return (
		cells.length > 0 && cells.every((cell) => /^(%|[([]\s*(%|-|–|—)\s*[)\]])$/.test(cell.trim()))
	);
}

/** What a column holds, from its axis: a key of COLUMN_WORDS. */
function kindOf(axis: PasteAxis): string {
	if (axis.category === 'flow') return 'flow';
	if (axis.category === 'fraction') return 'efficiency';
	return /npsh/i.test(axis.label) ? 'npshr' : 'head';
}

/**
 * The kind a heading word names: a key of COLUMN_WORDS, 'point' for a point-number word, ''
 * for a word that names none, null for one it cannot read.
 */
function wordKind(word: string): string | null {
	const lower = word.toLowerCase();
	for (const [kind, words] of Object.entries(COLUMN_WORDS)) if (words.includes(lower)) return kind;
	if (POINT_WORDS.has(lower)) return 'point';
	return OTHER_WORDS.has(lower) ? '' : null;
}

/** True when a cell starts as a number does, with or without a unit. */
function startsWithNumber(cell: string): boolean {
	return /^[+-]?(\d|\.\d)/.test(cell.trim());
}

/**
 * A heading row: no cell starts as a number and the row has a letter. A row with a cell such as
 * "-" or "—" and no letter is data, refused as such, never dropped as a heading.
 */
function isHeading(cells: readonly string[]): boolean {
	return cells.length > 0 && !cells.some(startsWithNumber) && /\p{L}/u.test(cells.join(' '));
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

interface Cells {
	rows: string[][];
	/** Cells separated by tabs (a spreadsheet's copy), so a heading's cells stand over columns. */
	tabbed: boolean;
}

/**
 * Rows of cells: by tabs, and quotes as a spreadsheet writes them, when the text has a tab or
 * starts with a quote; else by runs of ASCII spaces or semicolons (a no-break or thin space is
 * part of its cell, so "1 000" written with one is refused as a number). Every line is a row,
 * an empty one too, so an empty cell is never closed up.
 */
function cellsOf(text: string): Cells {
	if (text.includes('\t') || text.startsWith('"')) return { rows: tabCells(text), tabbed: true };
	const rows = text
		.split('\n')
		.map((line) => (line.trim() === '' ? [''] : line.trim().split(/ *; *| +/)));
	return { rows, tabbed: false };
}

/**
 * Rows that could each be one number with its thousands grouped by a space ("1 000", "12 500",
 * "1 000.5"): two cells, up to three digits then exactly three, with or without a decimal part.
 * A group never starts with 0, so a row such as "0 150" (a curve's shutoff point) shows a table.
 */
function groupedDigits(rows: string[][]): boolean {
	return (
		rows.length > 0 &&
		rows.every(
			(row) =>
				row.length === 2 &&
				/^[1-9]\d{0,2}$/.test(row[0] ?? '') &&
				/^\d{3}(\.\d+)?$/.test(row[1] ?? '')
		)
	);
}

/** A first column numbered 1, 2, 3…: the point numbers of a data sheet or of this table. */
function numbered(rows: string[][]): boolean {
	return rows.every((row, i) => row[0]?.replace(/\.$/, '') === String(i + 1));
}

/** A heading cell, or a whole heading line, read: its units and the kinds it names. */
interface HeadingWords {
	bracketed: string[];
	/** Brackets with nothing in them: "( )", "[]". */
	empty: number;
	unitWords: string[];
	kinds: string[];
	unread: string[];
}

/** The units and names in heading text; a word it cannot read is listed in `unread`. */
function headingWords(text: string, efficiency: boolean): HeadingWords {
	const inBrackets = [...text.matchAll(/[([]\s*([^()[\]]*?)\s*[)\]]/g)].map((m) =>
		(m[1] ?? '').replace(/\s+/g, ' ')
	);
	const bracketed = inBrackets.filter(Boolean);
	const empty = inBrackets.length - bracketed.length;
	const words = text
		.replace(/[([][^()[\]]*[)\]]/g, ' ')
		.split(/[\s;]+/)
		// A word set off by punctuation: "Capacity, gpm" is "Capacity" and "gpm".
		.map((word) => word.replace(/^[,:]+|[,:]+$/g, ''))
		// A dash standing alone is punctuation ("Pump - efficiency"); in brackets it is a unit.
		.filter((word) => word !== '' && !/^[-–—]+$/.test(word));
	const read: HeadingWords = { bracketed, empty, unitWords: [], kinds: [], unread: [] };
	const take = (part: string): boolean => {
		if (namesUnit(part) || (efficiency && FRACTION_WORD.test(part))) {
			read.unitWords.push(part);
			return true;
		}
		const kind = wordKind(part);
		if (kind === null) return false;
		if (kind) read.kinds.push(kind);
		return true;
	};
	for (const word of words) {
		if (take(word)) continue;
		// "Q/gpm", "flow_gpm", "Head,ft": a name and a unit run together.
		const parts = word.split(/[/_,:=-]+/).filter(Boolean);
		const kept = [read.unitWords.length, read.kinds.length] as const;
		if (parts.length > 1 && parts.every((part) => take(part))) continue;
		read.unitWords.length = kept[0];
		read.kinds.length = kept[1];
		read.unread.push(word);
	}
	return read;
}

/**
 * A heading: its cells over the columns when the copy had tabs, else its lines (one, or a
 * data sheet's two), whose words cannot be placed over columns, only read in order.
 */
type Heading = { tabbed: true; cells: string[] } | { tabbed: false; lines: string[] };

/** A heading's text, whole. */
function headingText(heading: Heading): string {
	return heading.tabbed ? heading.cells.join(' ') : heading.lines.join(' ');
}

/** Names in order with a name repeated next to itself once ("Flow rate" is one name). */
function sequenceOf(kinds: readonly string[]): string[] {
	return kinds.filter((kind, i) => kind !== kinds[i - 1]);
}

/**
 * Read a heading for the columns pasted (their kinds and labels, in order): its units, one per
 * column or none, after checking its names. Anything it cannot read refuses the paste.
 */
function readHeading(
	heading: Heading,
	kinds: readonly string[],
	labels: readonly string[]
): { units: (string | null)[]; named: boolean } | { error: string } {
	const efficiency = kinds.includes('efficiency');
	const whole = headingWords(headingText(heading), efficiency);
	if (whole.empty) {
		return {
			error: `Nothing was pasted: the heading has empty brackets. Name the unit in them${efficiency ? ', write (-) for fractions,' : ''} or leave them out.`
		};
	}
	if (whole.unread.length) {
		return {
			error: `Nothing was pasted: the heading has ${whole.unread.map((w) => `“${w}”`).join(', ')}, which this table does not read as a column’s name or a unit it takes. ${BRACKETS}`
		};
	}
	if (whole.bracketed.length && whole.unitWords.length) {
		return {
			error: `Nothing was pasted: the heading names units both in brackets and without (${[...whole.bracketed, ...whole.unitWords].join(', ')}). ${BRACKETS}`
		};
	}
	const units = whole.bracketed.length ? whole.bracketed : whole.unitWords;
	if (units.length && units.length !== kinds.length) {
		return {
			error: `Nothing was pasted: the heading names ${units.length} ${units.length === 1 ? 'unit' : 'units'} (${units.join(', ')}) for ${kinds.length} ${kinds.length === 1 ? 'column' : 'columns'}. ${BRACKETS}`
		};
	}
	const want = labels.map(inSentence);
	const names =
		kinds.length === 1
			? `This paste fills ${want[0]}: name it so, or name nothing.`
			: `This paste fills ${want.join(', then ')}: name each column over its own, or name none.`;
	if (whole.kinds.includes('point')) {
		return {
			error: `Nothing was pasted: the heading names point numbers over a column of values. ${names}`
		};
	}
	const foreign = [...new Set(whole.kinds)].filter((kind) => !kinds.includes(kind));
	if (foreign.length) {
		return {
			error: `Nothing was pasted: the heading names ${foreign.map((kind) => KIND_NAMES[kind] ?? kind).join(' and ')}. ${names}`
		};
	}
	// Each name over its own column: cell by cell where the cells stand over the columns; where
	// they do not (spaces), line by line, each line naming every column in order or none, and
	// giving every column's unit or none, so a heading wrapped onto two lines cannot put a name
	// of the first column after one of the second.
	const same = (list: readonly string[]) =>
		list.length === kinds.length && list.every((kind, c) => kind === kinds[c]);
	const swapped = (list: readonly (string | undefined)[]) =>
		kinds.length === 2 && list[0] === kinds[1] && list[1] === kinds[0];
	const named = whole.kinds.length > 0;
	let placed: boolean;
	let reversed: boolean;
	if (heading.tabbed) {
		const perColumn = heading.cells.map((cell) => [
			...new Set(headingWords(cell, efficiency).kinds)
		]);
		placed =
			perColumn.length === kinds.length &&
			perColumn.every((list, c) => list.length === 1 && list[0] === kinds[c]);
		reversed = swapped(perColumn.map((list) => list[0]));
	} else {
		const perLine = heading.lines.map((line) => headingWords(line, efficiency));
		for (const line of perLine) {
			const count = line.bracketed.length + line.unitWords.length;
			if (count !== 0 && count !== kinds.length) {
				return {
					error: `Nothing was pasted: a line of the heading gives ${count} ${count === 1 ? 'unit' : 'units'} for ${kinds.length} ${kinds.length === 1 ? 'column' : 'columns'}: give every column's unit on one line. ${BRACKETS}`
				};
			}
		}
		const sequences = perLine.map((line) => sequenceOf(line.kinds));
		placed = sequences.every((list) => list.length === 0 || same(list));
		reversed = sequences.some((list) => swapped(list));
	}
	if (named && !placed) {
		return {
			error: reversed
				? `Nothing was pasted: the heading names the columns in the other order. This table takes ${want.join(', then ')}.`
				: `Nothing was pasted: the heading does not name the columns one over each. ${names}`
		};
	}
	return { units: units.length ? units : kinds.map(() => null), named };
}

/** How a column is read: in a unit of the registry, or an efficiency column as fractions. */
type ColumnReading = { unit: UnitId; stated: boolean } | { fraction: true };

const COMMA =
	'Nothing was pasted: a comma can be a decimal mark, a thousands separator or a list. Copy the points from a spreadsheet, or separate the columns with spaces or tabs and write decimals with a point.';

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
	const { rows: parsed, tabbed } = cellsOf(body);
	const lines = body.split('\n');

	// A heading of one row, or two (a data sheet's names, then its units on the next line).
	let headingRows = 0;
	while (
		headingRows < 2 &&
		(isHeading(parsed[headingRows] ?? []) ||
			(headingRows === 1 && isUnitsRow(parsed[headingRows] ?? [])))
	)
		headingRows += 1;
	let rows = parsed.slice(headingRows);
	if (rows.length === 0) return { ok: false, error: 'Nothing was pasted: no rows of numbers.' };
	if (!tabbed && rows.some((row) => row.some((cell) => cell.includes(',')))) {
		return { ok: false, error: COMMA };
	}

	let width = rows.reduce((most, row) => Math.max(most, row.length), 0);
	// The heading's cells over the columns (with tabs), else its lines.
	const headingCells = parsed.slice(0, headingRows);
	let heading: Heading | null =
		headingRows === 0
			? null
			: tabbed
				? {
						tabbed: true,
						cells: Array.from(
							{ length: headingCells.reduce((most, r) => Math.max(most, r.length), 0) },
							(_, c) =>
								headingCells
									.map((r) => r[c] ?? '')
									.join(' ')
									.trim()
						)
					}
				: { tabbed: false, lines: lines.slice(0, headingRows) };
	// Three columns whose first is headed as point numbers ("#", "No.", "Point No.") and numbers
	// them 1, 2, 3…: the point numbers are dropped, with their heading words. Without such a
	// heading a first column counting 1, 2, 3 may be flows, so three columns are refused.
	const pointWords = (text: string) => {
		const words = text.trim().split(/\s+/);
		let n = 0;
		while (n < words.length && wordKind(words[n] ?? '') === 'point') n += 1;
		return { n, rest: words.slice(n).join(' ') };
	};
	const headedAsPoints =
		heading !== null &&
		(heading.tabbed
			? (() => {
					const first = heading.cells[0] ?? '';
					return first !== '' && pointWords(first).rest === '';
				})()
			: pointWords(heading.lines[0] ?? '').n > 0);
	if (width === 3 && headedAsPoints && rows.every((row) => row.length === 3) && numbered(rows)) {
		rows = rows.map((row) => row.slice(1));
		if (heading?.tabbed) heading = { tabbed: true, cells: heading.cells.slice(1) };
		else if (heading)
			heading = { tabbed: false, lines: heading.lines.map((line) => pointWords(line).rest) };
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

	if (heading?.tabbed && heading.cells.length !== width) {
		const cells = heading.cells.length;
		return {
			ok: false,
			error: `Nothing was pasted: the heading has ${cells} ${cells === 1 ? 'cell' : 'cells'} over ${width} ${width === 1 ? 'column' : 'columns'}. ${BRACKETS}`
		};
	}
	// Text split on spaces where each row could be one number with its thousands grouped by a
	// space, and no heading naming two columns to say it is a table: not guessed. Said before
	// the heading is read, so a headed column of grouped numbers is told so.
	if (!tabbed && width === 2 && groupedDigits(rows)) {
		const words = heading ? headingWords(headingText(heading), false) : null;
		const stated = words
			? Math.max(sequenceOf(words.kinds).length, words.bracketed.length + words.unitWords.length)
			: 0;
		if (stated < 2) {
			return {
				ok: false,
				error:
					'Nothing was pasted: each row could be one number with its thousands grouped by a space (“1 000”) or two numbers. Copy the points from a spreadsheet, write the numbers without spaces in them, or head the columns with their units, “Flow (gpm) Head (ft)”.'
			};
		}
	}
	const read =
		heading === null
			? { units: axes.map(() => null), named: false }
			: readHeading(
					heading,
					axes.map(kindOf),
					axes.map((axis) => axis.label)
				);
	if ('error' in read) return { ok: false, error: read.error };

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
			if (cell.includes(',')) return { ok: false, error: COMMA };
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
				if (si > 1) {
					return {
						ok: false,
						error: `Nothing was pasted: ${where}, “${cell}”: the heading reads this column as fractions (0.75 for 75 %), and ${cell} is more than 1. Head it “${axis.label} (%)” if it holds percentages.`
					};
				}
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
