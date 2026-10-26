/**
 * The SpreadsheetML writer (proposal export.md §3.2, §7.1): the exact XML of every part of a tiny
 * workbook (two sheets, three data rows), written out by hand from §3.2 (not from the writer's
 * output): content types, relationships, core properties (W3CDTF, to the second, Z), the workbook
 * with both defined names per sheet, the styles, each worksheet (caption in A1, row 2 absent,
 * headers in row 3, the frozen pane, sheetFormatPr, widths, autofilter, in the schema's order),
 * and the shared strings with their counts, `xml:space`, escaping, removed control characters,
 * `_xHHHH_` and CR. Then the cut at a cell's 32,767 characters and the sheet-name rules.
 */
import { describe, expect, it } from 'vitest';
import type { ExportBundle, ExportSheet } from './model';
import {
	CELL_LIMIT,
	cellText,
	columnName,
	coreXml,
	sanitizeText,
	validSheetName,
	writeXlsx,
	XLSX_MIME
} from './xlsx';
import { blobBytes, entryText, readZip } from './zip-reader.testing';

const HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n';
const MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';
const REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships';
const PANE =
	'<sheetViews><sheetView workbookViewId="0"><pane ySplit="3" topLeftCell="A4" activePane="bottomLeft" state="frozen"/><selection pane="bottomLeft"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="15"/>';

function tinyBundle(): ExportBundle {
	const about: ExportSheet = {
		id: 'about',
		title: 'About',
		file: 'about.csv',
		kind: 'document',
		caption: 'About — Pump & <tank>',
		columns: [
			{ label: 'Section', kind: 'text' },
			{ label: 'Item', kind: 'text' },
			{ label: 'Value', kind: 'text' }
		],
		rowCount: 1,
		rows: () => [['Export', 'Converged', false]]
	};
	const compare: ExportSheet = {
		id: 'compare-cases',
		title: 'Compare cases',
		file: 'compare-cases.csv',
		kind: 'table',
		caption: 'Compare cases — Pump & <tank> — "quoted"',
		columns: [
			{ label: 'Name', kind: 'text' },
			{ label: 'Flow', unit: 'L/s', kind: 'number' },
			{ label: 'Open', kind: 'boolean' },
			{ label: 'Note', kind: 'text' }
		],
		rowCount: 2,
		rows: () => [
			['Pump_x0041_B', 1e-7, true, 'Export'],
			['=HYPERLINK("x")', -0, null, ' a\u0001b\r\nc ']
		]
	};
	return {
		sheets: [about, compare],
		omitted: [],
		warnings: [],
		fileName: 'Tiny - results 2026-10-25 1432.xlsx',
		folder: null,
		title: 'Pump & <tank>',
		created: new Date('2026-10-25T12:32:05.678Z'),
		utcOffsetMinutes: 120,
		readme: []
	};
}

describe('a tiny workbook', () => {
	it('holds exactly these parts, in this order', async () => {
		const blob = await writeXlsx(tinyBundle());
		expect(blob.type).toBe(XLSX_MIME);
		const entries = readZip(await blobBytes(blob));
		expect(entries.map((e) => e.name)).toEqual([
			'[Content_Types].xml',
			'_rels/.rels',
			'docProps/core.xml',
			'xl/workbook.xml',
			'xl/_rels/workbook.xml.rels',
			'xl/styles.xml',
			'xl/worksheets/sheet1.xml',
			'xl/worksheets/sheet2.xml',
			'xl/sharedStrings.xml'
		]);
		const part = (name: string) => entryText(entries, name);

		expect(part('[Content_Types].xml')).toBe(
			`${HEAD}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">` +
				'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
				'<Default Extension="xml" ContentType="application/xml"/>' +
				'<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
				'<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' +
				'<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' +
				'<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' +
				'<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>' +
				'<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>' +
				'</Types>'
		);

		expect(part('_rels/.rels')).toBe(
			`${HEAD}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">` +
				`<Relationship Id="rId1" Type="${REL}/officeDocument" Target="xl/workbook.xml"/>` +
				'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>' +
				'</Relationships>'
		);

		expect(part('docProps/core.xml')).toBe(
			`${HEAD}<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">` +
				'<dc:title>Pump &amp; &lt;tank&gt;</dc:title><dc:creator>OpenSolve Pipe</dc:creator>' +
				'<dcterms:created xsi:type="dcterms:W3CDTF">2026-10-25T12:32:05Z</dcterms:created>' +
				'</cp:coreProperties>'
		);

		expect(part('xl/workbook.xml')).toBe(
			`${HEAD}<workbook xmlns="${MAIN}" xmlns:r="${REL}"><bookViews><workbookView/></bookViews>` +
				'<sheets><sheet name="About" sheetId="1" r:id="rId1"/><sheet name="Compare cases" sheetId="2" r:id="rId2"/></sheets>' +
				'<definedNames>' +
				`<definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">'About'!$A$3:$C$4</definedName>` +
				`<definedName name="_xlnm._FilterDatabase" localSheetId="1" hidden="1">'Compare cases'!$A$3:$D$5</definedName>` +
				`<definedName name="_xlnm.Print_Titles" localSheetId="0">'About'!$1:$3</definedName>` +
				`<definedName name="_xlnm.Print_Titles" localSheetId="1">'Compare cases'!$1:$3</definedName>` +
				'</definedNames></workbook>'
		);

		expect(part('xl/_rels/workbook.xml.rels')).toBe(
			`${HEAD}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">` +
				`<Relationship Id="rId1" Type="${REL}/worksheet" Target="worksheets/sheet1.xml"/>` +
				`<Relationship Id="rId2" Type="${REL}/worksheet" Target="worksheets/sheet2.xml"/>` +
				`<Relationship Id="rId3" Type="${REL}/styles" Target="styles.xml"/>` +
				`<Relationship Id="rId4" Type="${REL}/sharedStrings" Target="sharedStrings.xml"/>` +
				'</Relationships>'
		);

		expect(part('xl/styles.xml')).toBe(
			`${HEAD}<styleSheet xmlns="${MAIN}">` +
				'<fonts count="2"><font><sz val="11"/><name val="Calibri"/><family val="2"/></font><font><b/><sz val="11"/><name val="Calibri"/><family val="2"/></font></fonts>' +
				'<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>' +
				'<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>' +
				'<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>' +
				'<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>' +
				'<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>' +
				'<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf></cellXfs>' +
				'<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>' +
				'</styleSheet>'
		);

		// About: widths 7+2, 9+2 and clamp(5+2) = 8; the caption is shared string 0.
		expect(part('xl/worksheets/sheet1.xml')).toBe(
			`${HEAD}<worksheet xmlns="${MAIN}" xmlns:r="${REL}"><dimension ref="A1:C4"/>${PANE}` +
				'<cols><col min="1" max="1" width="9" customWidth="1"/><col min="2" max="2" width="11" customWidth="1"/><col min="3" max="3" width="8" customWidth="1"/></cols>' +
				'<sheetData>' +
				'<row r="1"><c r="A1" s="1" t="s"><v>0</v></c></row>' +
				'<row r="3"><c r="A3" s="2" t="s"><v>1</v></c><c r="B3" s="2" t="s"><v>2</v></c><c r="C3" s="2" t="s"><v>3</v></c></row>' +
				'<row r="4"><c r="A4" t="s"><v>4</v></c><c r="B4" t="s"><v>5</v></c><c r="C4" t="b"><v>0</v></c></row>' +
				'</sheetData><autoFilter ref="A3:C4"/></worksheet>'
		);

		// Compare cases: "Export" is shared string 4 again; -0 is 0; a null has no cell.
		expect(part('xl/worksheets/sheet2.xml')).toBe(
			`${HEAD}<worksheet xmlns="${MAIN}" xmlns:r="${REL}"><dimension ref="A1:D5"/>${PANE}` +
				'<cols><col min="1" max="1" width="17" customWidth="1"/><col min="2" max="2" width="12" customWidth="1"/><col min="3" max="3" width="8" customWidth="1"/><col min="4" max="4" width="10" customWidth="1"/></cols>' +
				'<sheetData>' +
				'<row r="1"><c r="A1" s="1" t="s"><v>6</v></c></row>' +
				'<row r="3"><c r="A3" s="2" t="s"><v>7</v></c><c r="B3" s="2" t="s"><v>8</v></c><c r="C3" s="2" t="s"><v>9</v></c><c r="D3" s="2" t="s"><v>10</v></c></row>' +
				'<row r="4"><c r="A4" t="s"><v>11</v></c><c r="B4"><v>1e-7</v></c><c r="C4" t="b"><v>1</v></c><c r="D4" t="s"><v>4</v></c></row>' +
				'<row r="5"><c r="A5" t="s"><v>12</v></c><c r="B5"><v>0</v></c><c r="D5" t="s"><v>13</v></c></row>' +
				'</sheetData><autoFilter ref="A3:D5"/></worksheet>'
		);

		// 15 text cells, 14 distinct; the control character is removed, `_x0041_` escaped, CR as
		// &#13; and the leading space preserved.
		expect(part('xl/sharedStrings.xml')).toBe(
			`${HEAD}<sst xmlns="${MAIN}" count="15" uniqueCount="14">` +
				'<si><t>About — Pump &amp; &lt;tank&gt;</t></si>' +
				'<si><t>Section</t></si><si><t>Item</t></si><si><t>Value</t></si>' +
				'<si><t>Export</t></si><si><t>Converged</t></si>' +
				'<si><t>Compare cases — Pump &amp; &lt;tank&gt; — &quot;quoted&quot;</t></si>' +
				'<si><t>Name</t></si><si><t>Flow [L/s]</t></si><si><t>Open</t></si><si><t>Note</t></si>' +
				'<si><t>Pump_x005F_x0041_B</t></si>' +
				'<si><t>=HYPERLINK(&quot;x&quot;)</t></si>' +
				'<si><t xml:space="preserve"> ab&#13;\nc </t></si>' +
				'</sst>'
		);
	});

	it('is the same bytes for the same bundle', async () => {
		const a = await blobBytes(await writeXlsx(tinyBundle()));
		const b = await blobBytes(await writeXlsx(tinyBundle()));
		expect(a).toEqual(b);
	});

	it('stops with an AbortError when its signal is aborted', async () => {
		const controller = new AbortController();
		controller.abort();
		await expect(writeXlsx(tinyBundle(), { signal: controller.signal })).rejects.toThrow(
			/cancelled/
		);
	});
});

describe('text', () => {
	it('is cut to 32,766 characters and "…" beyond a cell, never splitting a pair', () => {
		expect(cellText('x'.repeat(CELL_LIMIT))).toBe('x'.repeat(CELL_LIMIT));
		const long = cellText('x'.repeat(CELL_LIMIT + 1));
		expect(long.length).toBe(CELL_LIMIT);
		expect(long.endsWith('x…')).toBe(true);
		const pair = cellText(`${'x'.repeat(CELL_LIMIT - 2)}😀${'y'.repeat(5)}`);
		expect(pair).toBe(`${'x'.repeat(CELL_LIMIT - 2)}…`);
	});

	it('escapes markup and _xHHHH_, removes forbidden characters, writes CR as &#13;', () => {
		expect(sanitizeText('a & b < c > d "e"')).toBe('a &amp; b &lt; c &gt; d &quot;e&quot;');
		expect(sanitizeText('Pump_x0041_B and _x00e9_')).toBe('Pump_x005F_x0041_B and _x005F_x00e9_');
		expect(sanitizeText('_x12_ _xZZZZ_')).toBe('_x12_ _xZZZZ_');
		expect(sanitizeText('a\u0000b\u0008c\u000Bd\u000Ce\u001Ff\uFFFEg\uFFFFh')).toBe('abcdefgh');
		expect(sanitizeText('tab\tlf\ncr\rcrlf\r\n')).toBe('tab\tlf\ncr&#13;crlf&#13;\n');
	});

	it('escapes every underscore that begins an _xHHHH_, sequences sharing one included (review V4)', () => {
		expect(sanitizeText('A_x0041_x0042_B')).toBe('A_x005F_x0041_x005F_x0042_B');
		expect(sanitizeText('_x0041_x0042_')).toBe('_x005F_x0041_x005F_x0042_');
		expect(sanitizeText('x_x005F_x0041_y')).toBe('x_x005F_x005F_x005F_x0041_y');
		expect(sanitizeText('a_x0041_x0042_x0043_b')).toBe('a_x005F_x0041_x005F_x0042_x005F_x0043_b');
		// An ST_Xstring reader (LibreOffice, Excel) decodes left to right, each _xHHHH_ a character.
		const decode = (t: string) =>
			t.replace(/_x([0-9A-Fa-f]{4})_/g, (_, hex: string) => String.fromCharCode(parseInt(hex, 16)));
		for (const name of [
			'A_x0041_x0042_B',
			'_x0041_x0042_',
			'x_x005F_x0041_y',
			'a_x0041_x0042_x0043_b',
			'Tank_x0041_x0042_end',
			'_x005F_',
			'__x0041__x0042__',
			'Pump_x0041_B'
		]) {
			expect(decode(sanitizeText(name)), name).toBe(name);
		}
	});
});

describe('document properties (review F2)', () => {
	it('write the title as plain XML text: no _xHHHH_ escape and no cell cut', () => {
		const long = 'x'.repeat(CELL_LIMIT + 10);
		const xml = coreXml(
			`Pump_x0041_B & <co>\r\n${long}\u0001`,
			new Date('2026-10-25T12:32:05.123Z')
		);
		expect(xml).toContain(`<dc:title>Pump_x0041_B &amp; &lt;co&gt;&#13;\n${long}</dc:title>`);
		expect(xml).toContain(
			'<dcterms:created xsi:type="dcterms:W3CDTF">2026-10-25T12:32:05Z</dcterms:created>'
		);
	});
});

describe('sheets', () => {
	it('are named as Excel accepts: at most 31 characters, none of []:*?/\\', () => {
		expect(validSheetName('Compare cases')).toBe(true);
		expect(validSheetName('x'.repeat(31))).toBe(true);
		expect(validSheetName('x'.repeat(32))).toBe(false);
		for (const c of ['[', ']', ':', '*', '?', '/', '\\'])
			expect(validSheetName(`a${c}b`)).toBe(false);
		expect(validSheetName('')).toBe(false);
		expect(validSheetName("'quoted'")).toBe(false);
	});

	it('refuse a name Excel would not accept, and two sheets of one name', async () => {
		const bad = tinyBundle();
		await expect(
			writeXlsx({ ...bad, sheets: [{ ...bad.sheets[0]!, title: 'A/B' }] })
		).rejects.toThrow(/not a sheet name/);
		await expect(
			writeXlsx({ ...bad, sheets: [bad.sheets[0]!, { ...bad.sheets[1]!, title: 'about' }] })
		).rejects.toThrow(/same name/);
	});

	it('refuse a sheet whose rows are not the rows counted', async () => {
		const bad = tinyBundle();
		await expect(
			writeXlsx({ ...bad, sheets: [{ ...bad.sheets[0]!, rowCount: 2 }] })
		).rejects.toThrow(/not the 2 counted/);
	});

	it('name columns A–Z, then AA', () => {
		expect([0, 1, 25, 26, 27, 51, 52, 701, 702].map(columnName)).toEqual([
			'A',
			'B',
			'Z',
			'AA',
			'AB',
			'AZ',
			'BA',
			'ZZ',
			'AAA'
		]);
	});
});
