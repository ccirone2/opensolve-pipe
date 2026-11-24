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
			refused(readPastedPoints('Flow (psi)\tHead\n1\t2\n3\t4', 'x', FLOW, HEAD, IMPERIAL_UNITS))
		).toMatch(
			/^Nothing was pasted: the heading “Flow \(psi\)”: “psi” is not a unit this field takes/
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
			'Nothing was pasted: this table takes one column or two (Flow, Head), and 3 were copied.'
		);
		expect(refused(readPastedPoints('0\t150\n300', 'x', FLOW, HEAD, IMPERIAL_UNITS))).toBe(
			'Nothing was pasted: some rows have fewer cells than others.'
		);
		expect(refused(readPastedPoints('Flow\tHead\n', 'x', FLOW, HEAD, IMPERIAL_UNITS))).toBe(
			'Nothing was pasted: no rows of numbers.'
		);
	});
});
