/**
 * The results workbook (.xlsx): our own minimal SpreadsheetML writer (ECMA-376 / ISO/IEC 29500
 * subset; proposal export.md §3.2), in our own ZIP container (zip.ts).
 *
 * Parts: [Content_Types].xml, _rels/.rels, docProps/core.xml (title, creator, created: no other
 * property, never the link), xl/workbook.xml (the sheets; per sheet the defined names Excel writes
 * for the autofilter, hidden, and the print titles, rows 1–3), xl/_rels/workbook.xml.rels,
 * xl/styles.xml (regular and bold fonts; the two fills Excel requires; one border; cell formats 0
 * default, 1 bold for the caption, 2 bold and wrapped for the headers), xl/sharedStrings.xml and
 * one xl/worksheets/sheetN.xml per sheet.
 *
 * Every sheet: the caption in A1 (style 1), row 2 absent (blank, so Excel's and LibreOffice's
 * range detection never takes the caption for a header), the headers in row 3 (style 2), data
 * from row 4; panes frozen below row 3; an autofilter on A3 to the last cell. pandas reads every
 * sheet with `header=2`. Elements in the schema's order: dimension, sheetViews, sheetFormatPr,
 * cols, sheetData, autoFilter. The pane is written exactly (CT_Pane's `state` defaults to `split`,
 * which would split, not freeze), and `sheetFormatPr` carries its required `defaultRowHeight`.
 *
 * Cells: a number is `<v>String(n)</v>` in the General format (exponent forms read back exactly);
 * text is a shared string (never a formula: a name such as `=HYPERLINK(...)` stays text); a
 * boolean is `t="b"`; a null has no cell. Every shared string (captions and headers included) is
 * sanitized: cut to 32,766 characters plus "…" when longer than a cell holds (32,767); the
 * characters XML 1.0 forbids removed (a lone surrogate becomes U+FFFD when encoded); every
 * underscore that begins a literal `_xHHHH_` written as `_x005F_` (SpreadsheetML decodes `_xHHHH_`
 * as a character, left to right); `& < > "` escaped; CR written as `&#13;` (XML parsing turns a
 * literal CR into LF). The workbook's title (docProps/core.xml) is plain XML text: no `_x` escape
 * and no cut, since a document property is not ST_Xstring.
 *
 * Deterministic: the same bundle gives the same bytes (no clock, time zone or random source;
 * `created` is the bundle's).
 */
import type { CellValue, ExportBundle, ExportColumn, ExportSheet, WriteOptions } from './model';
import { columnHeader, numberText } from './csv';
import { Pacer } from './yield';
import { ZipWriter, type ZipEntry } from './zip';

export const XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

/** The most characters a cell holds (Excel's limit). */
export const CELL_LIMIT = 32767;
/** The most rows a sheet holds. */
export const ROW_LIMIT = 1_048_576;
/** Rows above the data: the caption (1), a blank row (2) and the headers (3). */
export const HEADER_ROWS = 3;
/** Rows read for the column widths. */
export const WIDTH_ROWS = 200;
export const MIN_WIDTH = 8;
export const MAX_WIDTH = 60;

const XML_HEADER = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n';
const MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';
const REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships';
const PKG_REL = 'http://schemas.openxmlformats.org/package/2006/relationships';

// eslint-disable-next-line no-control-regex -- the characters XML 1.0 forbids
const FORBIDDEN = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\uFFFE\uFFFF]/g;

/** Text cut to what a cell holds: 32,766 characters and "…" (a surrogate pair is never split). */
export function cellText(text: string): string {
	if (text.length <= CELL_LIMIT) return text;
	let cut = CELL_LIMIT - 1;
	const last = text.charCodeAt(cut - 1);
	if (last >= 0xd800 && last <= 0xdbff) cut--;
	return `${text.slice(0, cut)}…`;
}

/** Escaped for XML text and attributes: `& < > "`. */
export function escapeXml(text: string): string {
	return text
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;');
}

/**
 * A string as SpreadsheetML text (§3.2 sanitizing): cut to a cell, forbidden characters removed,
 * `_xHHHH_` escaped, XML-escaped, CR as `&#13;`. Every underscore that begins an `_xHHHH_` is
 * written `_x005F_`, so two sequences that share an underscore (`_x0041_x0042_`) are both
 * escaped: an ST_Xstring reader decodes left to right, and a non-overlapping match would leave
 * the second one to be read as a character.
 */
export function sanitizeText(text: string): string {
	return escapeXml(
		cellText(text)
			.replace(FORBIDDEN, '')
			.replace(/_(?=x[0-9A-Fa-f]{4}_)/g, '_x005F_')
	).replace(/\r/g, '&#13;');
}

/**
 * A string as plain XML text (a document property, which is not ST_Xstring, so no reader decodes
 * `_xHHHH_` in it): forbidden characters removed, XML-escaped, CR as `&#13;`; never cut.
 */
export function xmlText(text: string): string {
	return escapeXml(text.replace(FORBIDDEN, '')).replace(/\r/g, '&#13;');
}

/** "A", "B", …, "Z", "AA", … for a 0-based column index. */
export function columnName(index: number): string {
	let name = '';
	let n = index + 1;
	while (n > 0) {
		const r = (n - 1) % 26;
		name = String.fromCharCode(65 + r) + name;
		n = Math.floor((n - 1) / 26);
	}
	return name;
}

/** The shared-string table: each distinct text once, in the order first used. */
export class SharedStrings {
	readonly #index = new Map<string, number>();
	readonly #texts: string[] = [];
	/** Text cells written (with repeats). */
	count = 0;

	/** The index of `text` in the table (added when new). */
	add(text: string): number {
		this.count++;
		let i = this.#index.get(text);
		if (i === undefined) {
			i = this.#texts.length;
			this.#index.set(text, i);
			this.#texts.push(text);
		}
		return i;
	}

	get uniqueCount(): number {
		return this.#texts.length;
	}

	/** xl/sharedStrings.xml, in parts. */
	*xml(): Generator<string> {
		yield `${XML_HEADER}<sst xmlns="${MAIN}" count="${this.count}" uniqueCount="${this.uniqueCount}">`;
		for (const text of this.#texts) {
			const preserve = /^\s|\s$|[\r\n]/.test(text) ? ' xml:space="preserve"' : '';
			yield `<si><t${preserve}>${sanitizeText(text)}</t></si>`;
		}
		yield '</sst>';
	}
}

/** One cell's XML (none for a null or a non-finite number). */
export function cellXml(
	ref: string,
	value: CellValue,
	strings: SharedStrings,
	style?: number
): string {
	if (value === null || value === undefined) return '';
	const s = style === undefined ? '' : ` s="${style}"`;
	if (typeof value === 'number') {
		return Number.isFinite(value) ? `<c r="${ref}"${s}><v>${numberText(value)}</v></c>` : '';
	}
	if (typeof value === 'boolean') return `<c r="${ref}"${s} t="b"><v>${value ? 1 : 0}</v></c>`;
	return `<c r="${ref}"${s} t="s"><v>${strings.add(value)}</v></c>`;
}

/** A row's XML, from row number `r`. */
export function rowXml(
	r: number,
	values: readonly CellValue[],
	strings: SharedStrings,
	style?: number
): string {
	let cells = '';
	values.forEach((v, i) => (cells += cellXml(`${columnName(i)}${r}`, v, strings, style)));
	return `<row r="${r}">${cells}</row>`;
}

/** The text length a cell shows (for the column widths). */
function shownLength(value: CellValue): number {
	if (value === null || value === undefined) return 0;
	if (typeof value === 'boolean') return value ? 4 : 5;
	if (typeof value === 'number') return numberText(value).length;
	return value.length;
}

/**
 * Column widths, in characters: clamp(max(header, longest text of the first 200 rows) + 2, 8, 60),
 * or the column's own width.
 */
export function columnWidths(
	columns: readonly ExportColumn[],
	rows: readonly (readonly CellValue[])[]
): number[] {
	return columns.map((column, i) => {
		if (column.width !== undefined) return column.width;
		let longest = columnHeader(column).length;
		for (const row of rows.slice(0, WIDTH_ROWS))
			longest = Math.max(longest, shownLength(row[i] ?? null));
		return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, longest + 2));
	});
}

/** A sheet's name in a reference: quoted, with a quote doubled. */
function sheetRef(title: string): string {
	return `'${title.replace(/'/g, "''")}'`;
}

/** Sheet names Excel accepts: at most 31 characters, none of `[]:*?/\`, not empty, not quoted at the ends. */
export function validSheetName(title: string): boolean {
	return (
		title.length > 0 &&
		title.length <= 31 &&
		!/[[\]:*?/\\]/.test(title) &&
		!title.startsWith("'") &&
		!title.endsWith("'")
	);
}

/** The XML of a sheet's last column and row (the autofilter's and dimension's corner). */
function lastCell(columns: number, rows: number): string {
	return `${columnName(Math.max(columns, 1) - 1)}${HEADER_ROWS + rows}`;
}

/**
 * Write one worksheet: the first 200 rows are read for the widths, then everything streams.
 * Returns the number of data rows written.
 */
async function writeWorksheet(
	entry: ZipEntry,
	sheet: ExportSheet,
	strings: SharedStrings,
	pacer: Pacer
): Promise<number> {
	const iterator = sheet.rows()[Symbol.iterator]();
	const head: (readonly CellValue[])[] = [];
	let next = iterator.next();
	while (!next.done && head.length < WIDTH_ROWS) {
		head.push(next.value);
		next = iterator.next();
	}
	const widths = columnWidths(sheet.columns, head);
	const total = sheet.rowCount;
	if (total > ROW_LIMIT - HEADER_ROWS) {
		throw new Error(`The ${sheet.title} sheet has more rows than a worksheet holds.`);
	}
	const corner = lastCell(sheet.columns.length, total);
	entry.write(
		`${XML_HEADER}<worksheet xmlns="${MAIN}" xmlns:r="${REL}"><dimension ref="A1:${corner}"/>` +
			'<sheetViews><sheetView workbookViewId="0"><pane ySplit="3" topLeftCell="A4" activePane="bottomLeft" state="frozen"/><selection pane="bottomLeft"/></sheetView></sheetViews>' +
			'<sheetFormatPr defaultRowHeight="15"/><cols>' +
			widths
				.map((w, i) => `<col min="${i + 1}" max="${i + 1}" width="${w}" customWidth="1"/>`)
				.join('') +
			'</cols><sheetData>'
	);
	entry.write(rowXml(1, [sheet.caption], strings, 1));
	entry.write(rowXml(3, sheet.columns.map(columnHeader), strings, 2));
	let r = HEADER_ROWS;
	const writeRow = async (values: readonly CellValue[]) => {
		r++;
		const xml = rowXml(r, values, strings);
		entry.write(xml);
		await pacer.row(xml.length);
	};
	for (const row of head) await writeRow(row);
	while (!next.done) {
		await writeRow(next.value);
		next = iterator.next();
	}
	const rows = r - HEADER_ROWS;
	if (rows !== total) {
		throw new Error(`The ${sheet.title} sheet has ${rows} rows, not the ${total} counted.`);
	}
	entry.write(`</sheetData><autoFilter ref="A3:${corner}"/></worksheet>`);
	entry.end();
	return rows;
}

/** [Content_Types].xml for `sheets` worksheets. */
export function contentTypesXml(sheets: number): string {
	const sheetTypes = Array.from(
		{ length: sheets },
		(_, i) =>
			`<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`
	).join('');
	return (
		`${XML_HEADER}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">` +
		'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
		'<Default Extension="xml" ContentType="application/xml"/>' +
		'<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
		sheetTypes +
		'<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' +
		'<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>' +
		'<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>' +
		'</Types>'
	);
}

export const ROOT_RELS_XML =
	`${XML_HEADER}<Relationships xmlns="${PKG_REL}">` +
	`<Relationship Id="rId1" Type="${REL}/officeDocument" Target="xl/workbook.xml"/>` +
	'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>' +
	'</Relationships>';

/** The export time in UTC to the second, as Excel writes `dcterms:created`. */
export function w3cdtf(created: Date): string {
	return created.toISOString().replace(/\.\d{3}Z$/, 'Z');
}

/** docProps/core.xml: the title (the project's name), the creator and the time. */
export function coreXml(title: string, created: Date): string {
	return (
		`${XML_HEADER}<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">` +
		`<dc:title>${xmlText(title)}</dc:title><dc:creator>OpenSolve Pipe</dc:creator>` +
		`<dcterms:created xsi:type="dcterms:W3CDTF">${w3cdtf(created)}</dcterms:created>` +
		'</cp:coreProperties>'
	);
}

/** xl/workbook.xml: the sheets, then each sheet's autofilter range and print titles. */
export function workbookXml(
	sheets: readonly { title: string; columns: number; rows: number }[]
): string {
	const list = sheets
		.map((s, i) => `<sheet name="${escapeXml(s.title)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`)
		.join('');
	const filters = sheets
		.map((s, i) => {
			const [col, row] = [columnName(Math.max(s.columns, 1) - 1), HEADER_ROWS + s.rows];
			return `<definedName name="_xlnm._FilterDatabase" localSheetId="${i}" hidden="1">${escapeXml(sheetRef(s.title))}!$A$3:$${col}$${row}</definedName>`;
		})
		.join('');
	const titles = sheets
		.map(
			(s, i) =>
				`<definedName name="_xlnm.Print_Titles" localSheetId="${i}">${escapeXml(sheetRef(s.title))}!$1:$3</definedName>`
		)
		.join('');
	return (
		`${XML_HEADER}<workbook xmlns="${MAIN}" xmlns:r="${REL}">` +
		`<bookViews><workbookView/></bookViews><sheets>${list}</sheets>` +
		`<definedNames>${filters}${titles}</definedNames></workbook>`
	);
}

/** xl/_rels/workbook.xml.rels: the worksheets, the styles and the shared strings. */
export function workbookRelsXml(sheets: number): string {
	const rels = Array.from(
		{ length: sheets },
		(_, i) =>
			`<Relationship Id="rId${i + 1}" Type="${REL}/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`
	).join('');
	return (
		`${XML_HEADER}<Relationships xmlns="${PKG_REL}">${rels}` +
		`<Relationship Id="rId${sheets + 1}" Type="${REL}/styles" Target="styles.xml"/>` +
		`<Relationship Id="rId${sheets + 2}" Type="${REL}/sharedStrings" Target="sharedStrings.xml"/>` +
		'</Relationships>'
	);
}

export const STYLES_XML =
	`${XML_HEADER}<styleSheet xmlns="${MAIN}">` +
	'<fonts count="2"><font><sz val="11"/><name val="Calibri"/><family val="2"/></font><font><b/><sz val="11"/><name val="Calibri"/><family val="2"/></font></fonts>' +
	'<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>' +
	'<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>' +
	'<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>' +
	'<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>' +
	'<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>' +
	'<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf></cellXfs>' +
	'<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>' +
	'</styleSheet>';

/**
 * The workbook of `bundle`: About first, then every sheet of the bundle in order. Yields every
 * 500 rows or 64 KiB of XML, and stops with an AbortError when `options.signal` is aborted.
 */
export async function writeXlsx(bundle: ExportBundle, options: WriteOptions = {}): Promise<Blob> {
	const pacer = new Pacer(options.signal);
	pacer.check();
	for (const sheet of bundle.sheets) {
		if (!validSheetName(sheet.title)) throw new Error(`"${sheet.title}" is not a sheet name.`);
	}
	if (new Set(bundle.sheets.map((s) => s.title.toLowerCase())).size !== bundle.sheets.length) {
		throw new Error('Two sheets have the same name.');
	}
	const zip = new ZipWriter(bundle.created, bundle.utcOffsetMinutes);
	const n = bundle.sheets.length;
	zip.file('[Content_Types].xml', contentTypesXml(n));
	zip.file('_rels/.rels', ROOT_RELS_XML);
	zip.file('docProps/core.xml', coreXml(bundle.title, bundle.created));
	zip.file(
		'xl/workbook.xml',
		workbookXml(
			bundle.sheets.map((s) => ({ title: s.title, columns: s.columns.length, rows: s.rowCount }))
		)
	);
	zip.file('xl/_rels/workbook.xml.rels', workbookRelsXml(n));
	zip.file('xl/styles.xml', STYLES_XML);
	const strings = new SharedStrings();
	for (const [i, sheet] of bundle.sheets.entries()) {
		options.onProgress?.({ sheet: i + 1, sheets: n, title: sheet.title });
		await writeWorksheet(zip.entry(`xl/worksheets/sheet${i + 1}.xml`), sheet, strings, pacer);
		await pacer.pause();
	}
	const entry = zip.entry('xl/sharedStrings.xml');
	for (const part of strings.xml()) {
		entry.write(part);
		await pacer.row(part.length);
	}
	entry.end();
	return zip.finish(XLSX_MIME);
}
