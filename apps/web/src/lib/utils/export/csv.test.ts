/**
 * The CSV writer (proposal export.md §3.1, §7.1) against exact file contents: the BOM, CRLF after
 * every line, RFC 4180 quoting, String(n) numbers, booleans and empty fields, and the formula
 * guard on text (never on numbers, nor on a JSON number).
 */
import { describe, expect, it } from 'vitest';
import { csvField, numberText, toCsv } from './csv';
import type { ExportColumn } from './model';

const t = (label: string, unit?: string): ExportColumn =>
	unit ? { label, unit, kind: 'text' } : { label, kind: 'text' };
const n = (label: string, unit?: string): ExportColumn =>
	unit ? { label, unit, kind: 'number' } : { label, kind: 'number' };

describe('a CSV file', () => {
	it('starts with the BOM and the header, and ends every line (the last too) with CRLF', () => {
		expect(toCsv([t('Name'), n('Flow', 'L/s'), n('Re')], [['Pump A', 12.5, 200000]])).toBe(
			'\uFEFFName,Flow [L/s],Re\r\nPump A,12.5,200000\r\n'
		);
	});

	it('holds only the header line when there are no rows', () => {
		expect(toCsv([t('Severity'), t('Code')], [])).toBe('\uFEFFSeverity,Code\r\n');
	});

	it('quotes a field only when it holds a comma, a quote, CR or LF, doubling quotes', () => {
		expect(
			toCsv(
				[t('A'), t('B'), t('C'), t('D'), t('E')],
				[['a,b', 'say "hi"', 'line\nnext', 'cr\ronly', 'plain']]
			)
		).toBe('\uFEFFA,B,C,D,E\r\n"a,b","say ""hi""","line\nnext","cr\ronly",plain\r\n');
	});

	it('writes numbers as String(n): no rounding, exponent forms, -0 as 0, never quoted', () => {
		expect(
			toCsv(
				[n('a'), n('b'), n('c'), n('d'), n('e'), n('f')],
				[[0.1, 1e-7, 1e21, -0, 5e-324, 0.1 + 0.2]]
			)
		).toBe('\uFEFFa,b,c,d,e,f\r\n0.1,1e-7,1e+21,0,5e-324,0.30000000000000004\r\n');
		expect(numberText(-0)).toBe('0');
		expect(numberText(Number.NaN)).toBe('');
		expect(numberText(Number.POSITIVE_INFINITY)).toBe('');
	});

	it('writes booleans as TRUE and FALSE, and a null as an empty field', () => {
		expect(
			toCsv(
				[{ label: 'x', kind: 'boolean' }, { label: 'y', kind: 'boolean' }, t('z'), n('w')],
				[[true, false, null, null]]
			)
		).toBe('\uFEFFx,y,z,w\r\nTRUE,FALSE,,\r\n');
	});
});

describe('the formula guard (OWASP CSV injection)', () => {
	it('guards text that begins with = + - @, TAB or CR with a leading apostrophe', () => {
		expect(csvField('=1+2')).toBe("'=1+2");
		expect(csvField('+A1')).toBe("'+A1");
		expect(csvField('-North tank')).toBe("'-North tank");
		expect(csvField('@SUM(A1)')).toBe("'@SUM(A1)");
		expect(csvField('\tTab')).toBe("'\tTab");
		expect(csvField('\rCR')).toBe('"\'\rCR"');
		expect(csvField('=HYPERLINK("http://x")')).toBe('"\'=HYPERLINK(""http://x"")"');
	});

	it('never guards a number, a negative one included', () => {
		expect(csvField(-5, 'number')).toBe('-5');
		expect(csvField(-5, 'text')).toBe('-5');
	});

	it('leaves a JSON number unguarded, so it parses back; guards text in a text column', () => {
		const value = JSON.stringify(-0.01);
		expect(csvField(value, 'json')).toBe('-0.01');
		expect(JSON.parse(csvField(value, 'json'))).toBe(-0.01);
		expect(csvField('-1e-7', 'json')).toBe('-1e-7');
		expect(csvField('-1.5e+21', 'json')).toBe('-1.5e+21');
		// Not JSON numbers: guarded as text even in a JSON column.
		expect(csvField('-2+3', 'json')).toBe("'-2+3");
		expect(csvField('-North tank', 'json')).toBe("'-North tank");
		// The same text in a text column stays guarded.
		expect(csvField('-0.01', 'text')).toBe("'-0.01");
		expect(csvField('=1+2', 'text')).toBe("'=1+2");
	});

	it('needs no guard for an empty unit cell (a dimensionless value)', () => {
		expect(
			toCsv([t('Quantity'), t('Unit'), { label: 'JSON', kind: 'json' }], [['Re', '', '-0.01']])
		).toBe('\uFEFFQuantity,Unit,JSON\r\nRe,,-0.01\r\n');
		expect(csvField('', 'text')).toBe('');
	});

	it('keeps object JSON as it is (quoted for its commas and quotes)', () => {
		expect(csvField('{"kind":"Cv","value":120}', 'json')).toBe('"{""kind"":""Cv"",""value"":120}"');
	});
});
