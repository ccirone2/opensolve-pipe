/**
 * CSV files of an export, in one zip (proposal export.md §3.1).
 *
 * Dialect: RFC 4180. A comma between fields, CRLF after every line (the last included), one
 * header row. A field is quoted only when it holds `,`, `"`, CR or LF, with a quote inside it
 * doubled; numbers are never quoted. UTF-8 with a BOM (Excel on Windows reads a file without one
 * as cp1252). Numbers are `String(n)`: `.` decimals whatever the browser's locale, no grouping,
 * JavaScript's exponent form (1.5e-7, 1e+21), the shortest form that reads back exactly; -0 is 0
 * and a non-finite value is empty (the API never sends one). Booleans are TRUE and FALSE; a null
 * is an empty field.
 *
 * Formula guard (OWASP CSV injection; names come from shared links, so they are third-party
 * input): a text field that begins with `=`, `+`, `-`, `@`, TAB or CR is written with a leading
 * `'`. Numbers, negative ones included, are never guarded. Nor is a JSON cell that is a JSON number
 * (canonical JSON begins with `-` only for a number literal, which no spreadsheet runs as a formula,
 * and `'-0.01` would not be JSON); any other JSON cell is guarded like text, which canonical JSON
 * never needs.
 *
 * The zip: one top folder, `results {YYYY-MM-DD HHmm}`, holding README.txt first (how to open the
 * files without misreading them under a comma-decimal setting), then the files of §2.5 in sheet
 * order: tables as .csv, the text documents (methods, goal seek) as UTF-8 .txt with CRLF.
 */
import type { CellValue, ExportBundle, ExportColumn, ExportSheet, WriteOptions } from './model';
import { zipFolderName } from './filename';
import { Pacer } from './yield';
import { ZipWriter } from './zip';

export const CSV_MIME = 'text/csv';
export const ZIP_MIME = 'application/zip';
export const BOM = '\uFEFF';
export const CRLF = '\r\n';

const GUARDED = /^[=+\-@\t\r]/;
/** A JSON number literal (RFC 8259 §6). */
const JSON_NUMBER = /^-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?$/;

/** A number as written: String(n), -0 as 0, nothing for a non-finite value. */
export function numberText(n: number): string {
	if (!Number.isFinite(n)) return '';
	return Object.is(n, -0) ? '0' : String(n);
}

function quoted(text: string): string {
	return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** One field of a CSV row. */
export function csvField(value: CellValue, kind: ExportColumn['kind'] = 'text'): string {
	if (value === null || value === undefined) return '';
	if (typeof value === 'boolean') return value ? 'TRUE' : 'FALSE';
	if (typeof value === 'number') return numberText(value);
	const exempt = kind === 'json' && JSON_NUMBER.test(value);
	return quoted(!exempt && GUARDED.test(value) ? `'${value}` : value);
}

/** A column's header: "Label [unit]", or the label alone. */
export function columnHeader(column: ExportColumn): string {
	return column.unit ? `${column.label} [${column.unit}]` : column.label;
}

/** One line of a CSV file, with its CRLF. */
export function csvLine(columns: readonly ExportColumn[], row: readonly CellValue[]): string {
	return columns.map((c, i) => csvField(row[i] ?? null, c.kind)).join(',') + CRLF;
}

/** The header line (the headers are text, guarded as text). */
export function csvHeaderLine(columns: readonly ExportColumn[]): string {
	return columns.map((c) => csvField(columnHeader(c), 'text')).join(',') + CRLF;
}

/** A whole CSV file: the BOM, the header and the rows, each line ending in CRLF. */
export function toCsv(
	columns: readonly ExportColumn[],
	rows: Iterable<readonly CellValue[]>
): string {
	let text = BOM + csvHeaderLine(columns);
	for (const row of rows) text += csvLine(columns, row);
	return text;
}

/** Text lines with CRLF after each (a .txt document). */
export function crlfText(lines: Iterable<string>): string {
	let text = '';
	for (const line of lines) text += line.replace(/\r?\n/g, CRLF) + CRLF;
	return text;
}

/** Write a sheet's file into the zip, yielding between slices. */
async function writeSheet(
	zip: ZipWriter,
	folder: string,
	sheet: ExportSheet,
	pacer: Pacer
): Promise<void> {
	const entry = zip.entry(`${folder}/${sheet.file}`);
	if (sheet.text) {
		for (const line of sheet.text()) {
			const text = line.replace(/\r?\n/g, CRLF) + CRLF;
			entry.write(text);
			await pacer.row(text.length);
		}
	} else {
		entry.write(BOM + csvHeaderLine(sheet.columns));
		for (const row of sheet.rows()) {
			const line = csvLine(sheet.columns, row);
			entry.write(line);
			await pacer.row(line.length);
		}
	}
	entry.end();
}

/**
 * The CSV files of `bundle` in one zip: README.txt first, then every sheet's file, in one
 * `results {time}` folder. Yields every 500 rows or 64 KiB, and stops with an AbortError when
 * `options.signal` is aborted.
 */
export async function writeCsvZip(bundle: ExportBundle, options: WriteOptions = {}): Promise<Blob> {
	const pacer = new Pacer(options.signal);
	pacer.check();
	const folder = bundle.folder ?? zipFolderName(bundle.created, bundle.utcOffsetMinutes);
	const zip = new ZipWriter(bundle.created, bundle.utcOffsetMinutes);
	zip.file(`${folder}/README.txt`, crlfText(bundle.readme));
	for (const [i, sheet] of bundle.sheets.entries()) {
		options.onProgress?.({ sheet: i + 1, sheets: bundle.sheets.length, title: sheet.title });
		await writeSheet(zip, folder, sheet, pacer);
		await pacer.pause();
	}
	return zip.finish(ZIP_MIME);
}
