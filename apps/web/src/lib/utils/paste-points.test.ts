/**
 * Points pasted into a curve's table (proposal usability-entry.md §6). Expected values are the
 * unit definitions restated (NIST SP 811, the 1959 yard and pound), never the code under test.
 */
import { describe, expect, it } from 'vitest';
import { readPastedPoints, type PasteAxis } from './paste-points';
import { IMPERIAL_UNITS, SI_UNITS } from './units';

const ft = 0.3048;
const gpm = (231 * 0.0254 ** 3) / 60;

const FLOW: PasteAxis = { label: 'Flow', category: 'flow', bounds: { minimum: 0 } };
const HEAD: PasteAxis = { label: 'Head', category: 'head', bounds: {} };
const NPSHR: PasteAxis = { label: 'NPSHr', category: 'head', bounds: { minimum: 0 } };
const EFFICIENCY: PasteAxis = {
	label: 'Efficiency',
	category: 'fraction',
	bounds: { exclusiveMinimum: 0, maximum: 1 }
};

function close(actual: number | undefined, expected: number) {
	expect(actual).toBeDefined();
	expect(Math.abs((actual as number) - expected)).toBeLessThanOrEqual(Math.abs(expected) * 1e-14);
}

function ok(result: ReturnType<typeof readPastedPoints>) {
	if (!result?.ok) throw new Error(result ? result.error : 'not a paste');
	return result;
}

function refused(result: ReturnType<typeof readPastedPoints>) {
	if (!result || result.ok) throw new Error('accepted');
	return result.error;
}

describe('readPastedPoints', () => {
	it('leaves one value to the field: no tab, one line', () => {
		expect(readPastedPoints('300', 'x', FLOW, HEAD, IMPERIAL_UNITS)).toBeNull();
		expect(readPastedPoints('300 gpm', 'x', FLOW, HEAD, IMPERIAL_UNITS)).toBeNull();
		expect(readPastedPoints('  300\n', 'x', FLOW, HEAD, IMPERIAL_UNITS)).toBeNull();
	});

	it('reads a spreadsheet table (tabs), in the display units without a heading', () => {
		const pasted = ok(
			readPastedPoints('0\t150\r\n300\t130\r\n500\t100\r\n', 'x', FLOW, HEAD, IMPERIAL_UNITS)
		);
		expect(pasted.columns).toEqual(['x', 'y']);
		expect(pasted.rows).toHaveLength(3);
		close(pasted.rows[1]?.x, 300 * gpm);
		close(pasted.rows[1]?.y, 130 * ft);
		expect(pasted.rows[0]?.x).toBe(0);
		expect(pasted.summary).toBe('Pasted 3 points: flow in gpm, head in ft.');
	});

	it('reads a two-column paste as both columns, whichever cell it was pasted into', () => {
		const pasted = ok(readPastedPoints('0\t150\n300\t130', 'y', FLOW, HEAD, IMPERIAL_UNITS));
		expect(pasted.columns).toEqual(['x', 'y']);
		close(pasted.rows[1]?.y, 130 * ft);
	});

	it('reads a column into the column pasted into', () => {
		const pasted = ok(readPastedPoints('150\n130\n100', 'y', FLOW, HEAD, IMPERIAL_UNITS));
		expect(pasted.columns).toEqual(['y']);
		expect(pasted.rows.map((r) => r.x)).toEqual([undefined, undefined, undefined]);
		close(pasted.rows[2]?.y, 100 * ft);
		expect(pasted.summary).toBe('Pasted 3 values of head in ft.');
	});

	it('reads the units of a heading row and converts them', () => {
		const pasted = ok(
			readPastedPoints('Flow (m3/h)\tHead [m]\n0\t45\n36\t40', 'x', FLOW, HEAD, IMPERIAL_UNITS)
		);
		expect(pasted.rows).toHaveLength(2);
		close(pasted.rows[1]?.x, 36 / 3600);
		expect(pasted.rows[1]?.y).toBe(40);
		expect(pasted.summary).toBe('Pasted 2 points: flow in m³/h, head in m.');
	});

	it('takes a heading without a unit as the display unit', () => {
		const pasted = ok(readPastedPoints('Q\tH\n10\t20\n20\t18', 'x', FLOW, HEAD, SI_UNITS));
		close(pasted.rows[0]?.x, 10e-3);
		expect(pasted.rows[0]?.y).toBe(20);
	});

	it('reads a data sheet copied with spaces, and a unit on each cell', () => {
		const spaced = ok(
			readPastedPoints('0   150\n300 130\n500  100', 'x', FLOW, HEAD, IMPERIAL_UNITS)
		);
		close(spaced.rows[2]?.x, 500 * gpm);
		const unitInCells = ok(
			readPastedPoints('0 gpm\t150 ft\n300 gpm\t40 m', 'x', FLOW, HEAD, IMPERIAL_UNITS)
		);
		expect(unitInCells.rows[1]?.y).toBe(40);
	});

	it('drops a first column that numbers the points (this table, or a data sheet)', () => {
		const pasted = ok(
			readPastedPoints(
				'#\tFlow (gpm)\tHead (ft)\n1\t0\t150\n2\t300\t130',
				'x',
				FLOW,
				HEAD,
				IMPERIAL_UNITS
			)
		);
		expect(pasted.rows).toHaveLength(2);
		close(pasted.rows[1]?.x, 300 * gpm);
		close(pasted.rows[1]?.y, 130 * ft);
	});

	it('reads percentages for an efficiency curve', () => {
		const pasted = ok(readPastedPoints('70\n82\n78', 'y', FLOW, EFFICIENCY, SI_UNITS));
		close(pasted.rows[0]?.y, 0.7);
		close(pasted.rows[1]?.y, 0.82);
		close(pasted.rows[2]?.y, 0.78);
	});

	it('refuses the whole paste for one bad cell, naming its row and column', () => {
		expect(refused(readPastedPoints('0\t150\n3OO\t130', 'x', FLOW, HEAD, IMPERIAL_UNITS))).toBe(
			'Nothing was pasted: row 2, flow, “3OO”: “OO” is not a unit this field takes. Enter it in m³/s, m³/h, L/s, L/min or gpm.'
		);
		expect(refused(readPastedPoints('0\t150\n-5\t130', 'x', FLOW, HEAD, IMPERIAL_UNITS))).toBe(
			'Nothing was pasted: row 2, flow, “-5”: Must be at least 0 gpm.'
		);
		expect(
			refused(
				readPastedPoints('Flow (psi)\tHead (ft)\n1\t2\n3\t4', 'x', FLOW, HEAD, IMPERIAL_UNITS)
			)
		).toBe(
			'Nothing was pasted: the flow column’s unit in the heading, “psi”: “psi” is not a unit this field takes. Enter it in m³/s, m³/h, L/s, L/min or gpm.'
		);
	});

	it('refuses commas, which it cannot read without guessing', () => {
		expect(refused(readPastedPoints('1,000\n2,000', 'x', FLOW, HEAD, IMPERIAL_UNITS))).toMatch(
			/a comma can be a decimal mark, a thousands separator or a list/
		);
	});

	it('refuses more than two columns, and ragged rows', () => {
		expect(
			refused(readPastedPoints('0\t150\t0.5\n300\t130\t0.7', 'x', FLOW, HEAD, IMPERIAL_UNITS))
		).toBe(
			'Nothing was pasted: this table takes one column or two (Flow, Head), and 3 were copied. Copy the two columns alone, or with a first column of point numbers headed “#”.'
		);
		expect(refused(readPastedPoints('0\t150\n300', 'x', FLOW, HEAD, IMPERIAL_UNITS))).toBe(
			'Nothing was pasted: some rows have fewer cells than others.'
		);
		expect(refused(readPastedPoints('Flow\tHead\n', 'x', FLOW, HEAD, IMPERIAL_UNITS))).toBe(
			'Nothing was pasted: no rows of numbers.'
		);
	});

	// The review of 2026-11-24 (usability-entry.md §10): each of these was misread before.
	it("reads the unit of a single column's heading, though spaces split the heading", () => {
		const pasted = ok(readPastedPoints('Flow (gpm)\r\n0\r\n100\r\n200', 'x', FLOW, HEAD, SI_UNITS));
		expect(pasted.rows).toHaveLength(3);
		close(pasted.rows[1]?.x, 100 * gpm);
		expect(pasted.summary).toBe('Pasted 3 values of flow in gpm.');
		const spaced = ok(
			readPastedPoints('Flow (gpm) Head (ft)\n0 150\n300 130', 'x', FLOW, HEAD, SI_UNITS)
		);
		close(spaced.rows[1]?.x, 300 * gpm);
		close(spaced.rows[1]?.y, 130 * ft);
	});

	it('reads a heading of bare units, one per column', () => {
		const pasted = ok(readPastedPoints('gpm\tft\n0\t150\n300\t130', 'x', FLOW, HEAD, SI_UNITS));
		close(pasted.rows[1]?.x, 300 * gpm);
		close(pasted.rows[1]?.y, 130 * ft);
	});

	it('refuses a heading whose units cannot be put one to a column', () => {
		expect(
			refused(
				readPastedPoints('Q [gpm]\tH [ft]\tEff (%)\n0\t150\n300\t130', 'x', FLOW, HEAD, SI_UNITS)
			)
		).toBe(
			'Nothing was pasted: the heading names 3 units (gpm, ft, %) for 2 columns. Put each column’s unit in brackets after its name, “Flow (gpm)”, or leave the heading out.'
		);
		// "in" is a unit (inches) as well as a word: refused, never read as one or the other.
		expect(refused(readPastedPoints('Flow in gpm\n0\n100', 'x', FLOW, HEAD, SI_UNITS))).toMatch(
			/names 2 units \(in, gpm\) for 1 column/
		);
	});

	it('takes a first row with no letter as data, refusing it rather than dropping it', () => {
		expect(refused(readPastedPoints('-\n2.1\n2.8\n3.5', 'y', FLOW, HEAD, SI_UNITS))).toBe(
			'Nothing was pasted: row 1, head, “-”: Enter a number, e.g. 12.5 or 1.2e-3.'
		);
		expect(refused(readPastedPoints('0\t—\n300\t130', 'x', FLOW, HEAD, SI_UNITS))).toMatch(
			/^Nothing was pasted: row 1, head, “—”/
		);
	});

	it('keeps a first column counting 1, 2, 3 unless its heading names point numbers', () => {
		expect(
			refused(readPastedPoints('1\t50\t0.6\n2\t45\t0.7\n3\t38\t0.65', 'x', FLOW, HEAD, SI_UNITS))
		).toMatch(/and 3 were copied/);
		expect(
			refused(
				readPastedPoints('Q (L/s)\tH (m)\tEff\n1\t50\t0.6\n2\t45\t0.7', 'x', FLOW, HEAD, SI_UNITS)
			)
		).toMatch(/and 3 were copied/);
		const numbered = ok(
			readPastedPoints('No.\tQ (L/s)\tH (m)\n1\t0\t50\n2\t10\t45', 'x', FLOW, HEAD, SI_UNITS)
		);
		close(numbered.rows[1]?.x, 10e-3);
		expect(numbered.rows[1]?.y).toBe(45);
	});

	it('says capitals matter in a heading too', () => {
		expect(refused(readPastedPoints('MM\n1\n2', 'y', FLOW, HEAD, SI_UNITS))).toMatch(
			/mind the capitals/
		);
	});
	// The second review (usability-entry.md §10 item 5): each of these was misread before.
	it('refuses an empty cell, never closing the column up; a trailing line break is no row', () => {
		expect(
			refused(readPastedPoints('151\r\n\r\n101\r\n81\r\n', 'y', FLOW, HEAD, IMPERIAL_UNITS))
		).toBe('Nothing was pasted: row 2, head is empty.');
		expect(refused(readPastedPoints('\r\n100\r\n80', 'y', FLOW, HEAD, IMPERIAL_UNITS))).toBe(
			'Nothing was pasted: row 1, head is empty.'
		);
		expect(
			refused(readPastedPoints('0\t150\r\n\t\r\n500\t100', 'x', FLOW, HEAD, IMPERIAL_UNITS))
		).toBe('Nothing was pasted: row 2, flow is empty.');
		expect(
			ok(readPastedPoints('150\r\n130\r\n\r\n', 'y', FLOW, HEAD, IMPERIAL_UNITS)).rows
		).toHaveLength(2);
		expect(readPastedPoints('300\r\n', 'x', FLOW, HEAD, IMPERIAL_UNITS)).toBeNull();
	});

	it('refuses a heading word it cannot read, rather than passing it over', () => {
		for (const heading of [
			'Flow l/sec',
			'Flow m3/hour',
			'Flow MGD',
			'Flow m^3/h',
			'Flow Imp gpm',
			'Q UK gpm'
		]) {
			expect(
				refused(readPastedPoints(`${heading}\n0\n20`, 'x', FLOW, HEAD, IMPERIAL_UNITS)),
				heading
			).toMatch(
				/^Nothing was pasted: the heading has “[^”]+”(, “[^”]+”)*, which this table does not read as a column’s name or a unit it takes\./
			);
		}
		expect(refused(readPastedPoints('Head mWC\n10\n20', 'y', FLOW, HEAD, IMPERIAL_UNITS))).toMatch(
			/“mWC”/
		);
		// A first cell such as "n/a" or "Shutoff" is a heading it cannot read, not one dropped.
		expect(refused(readPastedPoints('n/a\n2.1\n2.8', 'y', FLOW, NPSHR, SI_UNITS))).toMatch(
			/“n\/a”/
		);
		expect(refused(readPastedPoints('Shutoff\n150\n130', 'y', FLOW, HEAD, SI_UNITS))).toMatch(
			/“Shutoff”/
		);
	});

	it('reads a name and a unit run together, and "US gpm"', () => {
		const slashed = ok(readPastedPoints('Q/gpm\tH/ft\n0\t150\n500\t80', 'x', FLOW, HEAD, SI_UNITS));
		close(slashed.rows[1]?.x, 500 * gpm);
		close(slashed.rows[1]?.y, 80 * ft);
		const joined = ok(
			readPastedPoints('flow_gpm\thead_ft\n0\t150\n500\t80', 'x', FLOW, HEAD, SI_UNITS)
		);
		close(joined.rows[1]?.x, 500 * gpm);
		const us = ok(readPastedPoints('Flow US gpm\n0\n500', 'x', FLOW, HEAD, SI_UNITS));
		close(us.rows[1]?.x, 500 * gpm);
	});

	it('refuses a heading naming another column, or the columns in the other order', () => {
		expect(
			refused(readPastedPoints('Head (ft)\tFlow (gpm)\n150\t0\n80\t500', 'x', FLOW, HEAD, SI_UNITS))
		).toBe(
			'Nothing was pasted: the heading names the columns in the other order. This table takes flow, then head.'
		);
		expect(
			refused(
				readPastedPoints('Flow (gpm)\tEfficiency (%)\n0\t0\n500\t80', 'x', FLOW, HEAD, SI_UNITS)
			)
		).toBe('Nothing was pasted: the heading names efficiency, and this paste fills flow and head.');
		expect(refused(readPastedPoints('Head (ft)\n150\n80', 'x', FLOW, HEAD, SI_UNITS))).toBe(
			'Nothing was pasted: the heading names head, and this paste fills flow.'
		);
	});

	it('refuses rows that could be numbers grouped by a space ("1 000"), unless shown to be a table', () => {
		for (const text of ['1 000\r\n2 000\r\n3 000', '1 200\n2 400\n3 600', 'Flow\n1 000\n2 000']) {
			expect(refused(readPastedPoints(text, 'x', FLOW, HEAD, SI_UNITS)), text).toMatch(
				/each row could be one number with its thousands grouped by a space/
			);
		}
		// A no-break or thin space inside a number keeps it one cell, refused as a number.
		const nbsp = String.fromCodePoint(0xa0);
		const thin = String.fromCodePoint(0x202f);
		expect(refused(readPastedPoints(`1${nbsp}000\n2${thin}000`, 'x', FLOW, HEAD, SI_UNITS))).toBe(
			`Nothing was pasted: row 1, flow, “1${nbsp}000”: Enter a number, e.g. 12.5 or 1.2e-3.`
		);
		// "0 150" cannot be a grouped number (a group never starts with 0): a table.
		expect(
			ok(readPastedPoints('0 150\n300 130\n500 100', 'x', FLOW, HEAD, SI_UNITS)).rows
		).toHaveLength(3);
		// A heading naming two columns says it is a table.
		const headed = ok(
			readPastedPoints('Flow (gpm) Head (ft)\n300 130\n500 100', 'x', FLOW, HEAD, SI_UNITS)
		);
		close(headed.rows[0]?.x, 300 * gpm);
	});

	it('reads semicolons as separators in text without tabs, never inside tabbed cells', () => {
		const semi = ok(readPastedPoints('0;50\n10;45', 'x', FLOW, HEAD, SI_UNITS));
		close(semi.rows[1]?.x, 10e-3);
		expect(semi.rows[1]?.y).toBe(45);
		expect(ok(readPastedPoints('0 ; 50\n10 ; 45', 'x', FLOW, HEAD, SI_UNITS)).rows[1]?.y).toBe(45);
		expect(refused(readPastedPoints('0;1\t50\n10\t45', 'x', FLOW, HEAD, SI_UNITS))).toMatch(
			/row 1, flow, “0;1”/
		);
	});

	it('reads a spreadsheet heading cell with a line break in it (in quotes)', () => {
		const pasted = ok(
			readPastedPoints(
				'"Flow\n(gpm)"\t"Head\n(ft)"\r\n0\t100\r\n500\t80\r\n',
				'x',
				FLOW,
				HEAD,
				SI_UNITS
			)
		);
		close(pasted.rows[1]?.x, 500 * gpm);
		close(pasted.rows[1]?.y, 80 * ft);
	});

	it('refuses efficiencies that may be fractions unless a unit says which', () => {
		expect(refused(readPastedPoints('0.6\n0.75\n0.7', 'y', FLOW, EFFICIENCY, SI_UNITS))).toBe(
			'Nothing was pasted: every efficiency is 1 % or less, so they may be fractions (0.75 for 75 %). Head the column “Efficiency (%)” if they are percentages, or “Efficiency (-)” if they are fractions.'
		);
		const fractions = ok(
			readPastedPoints('Efficiency (-)\n0.6\n0.75', 'y', FLOW, EFFICIENCY, SI_UNITS)
		);
		expect(fractions.rows.map((row) => row.y)).toEqual([0.6, 0.75]);
		expect(fractions.summary).toBe('Pasted 2 values of efficiency as a fraction.');
		expect(
			ok(readPastedPoints('η [-]\n0.6\n0.8', 'y', FLOW, EFFICIENCY, SI_UNITS)).rows[1]?.y
		).toBe(0.8);
		const percent = ok(readPastedPoints('Eff (%)\n0.6\n0.75', 'y', FLOW, EFFICIENCY, SI_UNITS));
		close(percent.rows[1]?.y, 0.0075);
	});

	it('names the units the cells were in, and refuses a cell against its heading', () => {
		const cells = ok(readPastedPoints('100 gpm\t50 ft\n200 gpm\t40 ft', 'x', FLOW, HEAD, SI_UNITS));
		expect(cells.summary).toBe('Pasted 2 points: flow in gpm, head in ft.');
		const mixed = ok(readPastedPoints('100 gpm\t50\n10\t40', 'x', FLOW, HEAD, SI_UNITS));
		expect(mixed.summary).toBe('Pasted 2 points: flow in gpm and L/s, head in m.');
		expect(
			refused(readPastedPoints('Flow (L/s)\tHead (m)\n100 gpm\t50', 'x', FLOW, HEAD, SI_UNITS))
		).toBe('Nothing was pasted: row 1, flow, “100 gpm”: the heading says L/s.');
	});

	it('keeps an acronym as written in its messages', () => {
		expect(ok(readPastedPoints('NPSHr (m)\n2\n3', 'y', FLOW, NPSHR, SI_UNITS)).summary).toBe(
			'Pasted 2 values of NPSHr in m.'
		);
	});
});
