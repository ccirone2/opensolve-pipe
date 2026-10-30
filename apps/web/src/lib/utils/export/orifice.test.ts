/**
 * The export's Orifice plates sheet and lines (proposal orifice-plate.md §5.4). Two plates, a flow
 * meter with flange taps on an entered C and a restriction orifice without taps on ISO 5167-2's C,
 * take their place in each case of the shared fixture (real API responses, export_input.py) with
 * made-up results (test inputs, not hydraulic results), in reverse flow too: SI cells are the
 * API's doubles bit for bit, display cells `fromSI` of the field, the screen's table reads the
 * same fields, the bore and pipe bore are the ones the solve used, About gains its orifice lines
 * only with the sheet (a file without plates is as before), a case that did not converge gives no
 * values, and the scenario changes write a bore with its unit and no entered C as ISO's default.
 */
import { describe, expect, it } from 'vitest';
import type {
	Component,
	OrificeResult,
	OverrideResult,
	Project,
	SolvedState
} from '../../api/types';
import { Formatter, HEAD_NOISE, orificeTable, valueText } from '../results';
import { displayUnit, fromSI, STANDARD_GRAVITY } from '../units';
import { fixtureInput, readSheet, sheetIds, withoutReliefValves } from './export-testing.testing';
import { buildExport, type ExportInput } from './model';

const ports = [
	{ id: 'inlet', nominalSize: 0.1016, direction: 'inlet' },
	{ id: 'outlet', nominalSize: 0.1016, direction: 'outlet' }
] as Component['ports'];
const METER: Component = {
	id: 'O9',
	name: 'Flow meter',
	elevation: 0,
	type: 'orifice',
	boreDiameter: 0.05,
	dischargeCoefficient: 0.62,
	taps: 'flange',
	ports
};
const RESTRICTION: Component = {
	id: 'O8',
	name: 'Bypass orifice',
	elevation: 0,
	type: 'orifice',
	boreDiameter: 0.015,
	ports
};

/** Made-up results of the two plates in a case (`k` makes each case's numbers its own). */
function results(k: number): Record<string, OrificeResult> {
	return {
		O9: {
			flow: 0.0134147 * k,
			headLoss: 4.3087 * k,
			pressureLoss: 42168.512345678 * k,
			pressureDrop: 42168.512345678 * k,
			differentialPressure: 57140.9012345 * k,
			venaContractaPressure: -12345.678 * k,
			beta: 0.488947823399869,
			pipeDiameter: 0.1022604,
			boreDiameter: 0.05,
			reynoldsNumber: 166441.123 * k,
			dischargeCoefficient: 0.619924,
			coefficientSource: 'entered',
			coefficientReynoldsNumber: 166441.123 * k,
			tapCoefficientRatio: 0.99987742,
			lossCoefficient: 29.71234,
			taps: 'flange',
			meterDischargeCoefficient: 0.62
		},
		O8: {
			flow: -0.0025434 * k,
			headLoss: -26.1489 * k,
			pressureLoss: -255912.25 * k,
			pressureDrop: -255800.5 * k,
			differentialPressure: null,
			venaContractaPressure: null,
			beta: 0.2857142857,
			pipeDiameter: 0.0525,
			boreDiameter: 0.015,
			reynoldsNumber: 61561.7 * k,
			dischargeCoefficient: 0.602918139,
			coefficientSource: 'iso_5167_2',
			coefficientReynoldsNumber: 61561.7 * k,
			tapCoefficientRatio: null,
			lossCoefficient: 371.5146249,
			taps: null,
			meterDischargeCoefficient: null
		}
	};
}

/**
 * `input` with the two plates in its projects, and their results in place of each response's
 * orifice results.
 */
function withOrifices(input: ExportInput, converged = true): ExportInput {
	const add = (p: Project | null) =>
		p && { ...p, components: [...p.components, METER, RESTRICTION] };
	return {
		...input,
		project: add(input.project)!,
		cases: input.cases.map((c, i) => ({
			...c,
			sent: add(c.sent),
			inputs: add(c.inputs),
			response: c.response && {
				...c.response,
				success: converged && c.response.success,
				solvedState: {
					...c.response.solvedState,
					converged: converged && c.response.solvedState.converged,
					orificeResults: results(1 + i / 10)
				}
			}
		}))
	};
}

/** `input` with no orifice results in any response: a file without an Orifice plates sheet. */
function withoutOrifices(input: ExportInput): ExportInput {
	return {
		...input,
		cases: input.cases.map((c) => ({
			...c,
			response: c.response && {
				...c.response,
				solvedState: { ...c.response.solvedState, orificeResults: {} }
			}
		}))
	};
}

const solvedOf = (input: ExportInput, id: string | null): SolvedState =>
	input.cases.find((c) => c.id === id)!.response!.solvedState;

describe('the Orifice plates sheet', () => {
	it('SI: every number cell is the API double, with the base unit; the bore as used', () => {
		const input = withOrifices(fixtureInput('scenarios')); // SI, all three cases
		const bundle = buildExport(input);
		// After Equipment (the fixture case has equipment), before Branches.
		const ids = sheetIds(bundle);
		expect(ids).toContain('orifices');
		expect(ids.indexOf('orifices')).toBe(ids.indexOf('equipment') + 1);
		const t = readSheet(bundle, 'orifices');
		expect(t.headers).toEqual([
			'Case id',
			'Case',
			'Solved at',
			'Results',
			'Orifice id',
			'Orifice',
			'Flow (+ inlet → outlet) [m³/s]',
			'Permanent pressure loss [Pa]',
			'Differential pressure (taps) [Pa]',
			'Pressure drop, static [Pa]',
			'Head loss [m]',
			'Vena contracta pressure [Pa(g)]',
			'β',
			'Reynolds number (inlet pipe)',
			'Discharge coefficient (loss)',
			'C from',
			'C evaluated at Re',
			'Tap ratio r',
			'Taps',
			'Meter C',
			'Loss coefficient K',
			'Bore [m]',
			'Pipe bore D [m]',
			'Flags'
		]);
		// Two rows per case, in project order (the meter is listed before the restriction).
		expect(t.rows).toHaveLength(6);
		for (const row of t.rows) {
			const id = String(t.get(row, 'Orifice id'));
			const o = solvedOf(input, t.get(row, 'Case id') as string | null).orificeResults[id]!;
			const same = (label: string, api: number | null) =>
				api === null
					? expect(t.get(row, label), label).toBeNull()
					: expect(Object.is(t.get(row, label), api), label).toBe(true);
			same('Flow (+ inlet → outlet)', o.flow);
			same('Permanent pressure loss', o.pressureLoss);
			same('Differential pressure (taps)', o.differentialPressure);
			same('Pressure drop, static', o.pressureDrop);
			same('Head loss', o.headLoss);
			same('Vena contracta pressure', o.venaContractaPressure);
			same('β', o.beta);
			same('Reynolds number (inlet pipe)', o.reynoldsNumber);
			same('Discharge coefficient (loss)', o.dischargeCoefficient);
			same('C evaluated at Re', o.coefficientReynoldsNumber);
			same('Tap ratio r', o.tapCoefficientRatio);
			same('Meter C', o.meterDischargeCoefficient);
			same('Loss coefficient K', o.lossCoefficient);
			same('Bore', o.boreDiameter);
			same('Pipe bore D', o.pipeDiameter);
			const meter = id === 'O9';
			expect(t.get(row, 'Orifice')).toBe(meter ? 'Flow meter' : 'Bypass orifice');
			expect(t.get(row, 'C from')).toBe(meter ? 'Entered, moved to D and D/2' : 'ISO 5167-2');
			expect(t.get(row, 'Taps')).toBe(meter ? 'Flange' : 'None');
		}
	});

	it('display units: fromSI of each field, and the screen reads the same fields', () => {
		const input = withOrifices(fixtureInput('pump-transfer')); // display units, one case
		const bundle = buildExport(input);
		const t = readSheet(bundle, 'orifices');
		const prefs = input.prefs;
		const solved = solvedOf(input, null);
		const unit = (category: Parameters<typeof displayUnit>[0]) => displayUnit(category, prefs);
		expect(t.rows.map((r) => t.get(r, 'Orifice id'))).toEqual(['O9', 'O8']);
		for (const row of t.rows) {
			const o = solved.orificeResults[String(t.get(row, 'Orifice id'))]!;
			const pressure = (v: number | null) => (v === null ? null : fromSI(v, unit('pressure')));
			expect(t.get(row, 'Flow (+ inlet → outlet)')).toBe(fromSI(o.flow, unit('flow')));
			expect(t.get(row, 'Permanent pressure loss')).toBe(pressure(o.pressureLoss));
			expect(t.get(row, 'Differential pressure (taps)')).toBe(pressure(o.differentialPressure));
			expect(t.get(row, 'Pressure drop, static')).toBe(pressure(o.pressureDrop));
			expect(t.get(row, 'Vena contracta pressure')).toBe(pressure(o.venaContractaPressure));
			expect(t.get(row, 'Head loss')).toBe(fromSI(o.headLoss, unit('head')));
			expect(t.get(row, 'Bore')).toBe(fromSI(o.boreDiameter, unit('diameter')));
			expect(t.get(row, 'Pipe bore D')).toBe(fromSI(o.pipeDiameter, unit('diameter')));
			// Pure numbers are the API's doubles in every unit system.
			expect(t.get(row, 'β')).toBe(o.beta);
			expect(t.get(row, 'Loss coefficient K')).toBe(o.lossCoefficient);
		}
		// A pressure difference has no gauge marker in its header; the vena contracta's has one.
		expect(t.headers).toContain(`Permanent pressure loss [${prefs.pressure}]`);
		expect(t.headers.find((h) => h.startsWith('Vena contracta pressure'))).not.toBe(
			`Vena contracta pressure [${prefs.pressure}]`
		);
		// The screen's table: the same plates and order, each cell the field in the same category.
		const f = new Formatter(prefs);
		const screen = orificeTable(input.project, solved, prefs);
		expect(screen.rows.map((r) => r.key)).toEqual(['O9', 'O8']);
		const noise = solved.fluid.density * STANDARD_GRAVITY * HEAD_NOISE;
		for (const row of screen.rows) {
			const o = solved.orificeResults[row.key]!;
			expect(row.cells.flow).toBe(f.num(o.flow, 'flow'));
			expect(row.cells.differentialPressure).toBe(f.num(o.differentialPressure, 'pressure'));
			expect(row.cells.venaContractaPressure).toBe(f.num(o.venaContractaPressure, 'pressure'));
			expect(valueText(row.cells.pressureLoss as string)).toBe(
				valueText(f.diff(o.pressureLoss, 'pressure', noise))
			);
			expect(valueText(row.cells.pressureDrop as string)).toBe(
				valueText(f.diff(o.pressureDrop, 'pressure', noise))
			);
		}
	});

	it('is left out without plates, and holds no values from a solve that did not converge', () => {
		expect(sheetIds(buildExport(fixtureInput('pump-transfer')))).not.toContain('orifices');
		const stopped = withOrifices(fixtureInput('pump-transfer'), false);
		expect(sheetIds(buildExport(stopped))).not.toContain('orifices');
	});
});

describe('About and Scenario changes with orifice plates', () => {
	/** About's rows as Item → Value (without relief valves: their lines are their own). */
	function about(input: ExportInput): Map<string, unknown> {
		const t = readSheet(buildExport(withoutReliefValves(input)), 'about');
		return new Map(t.rows.map((r) => [String(t.get(r, 'Item')), t.get(r, 'Value')]));
	}

	it('adds the orifice lines only with an Orifice plates sheet; every other row as before', () => {
		const plain = about(withoutOrifices(fixtureInput('scenarios')));
		const rows = about(withOrifices(fixtureInput('scenarios')));
		expect(plain.has('Sheet: Orifice plates')).toBe(false);
		expect(rows.get('Sheet: Orifice plates')).toBe(6);
		expect(rows.get('Sign: orifice plate flow')).toMatch(/^\+ inlet → outlet; /);
		expect(plain.has('Sign: orifice plate flow')).toBe(false);
		// The fixture has equipment: the ≈ 0 rule names both elements' pressure differences.
		expect(String(rows.get('Numbers'))).toContain(
			'valve, equipment and orifice plate pressure drops, equipment pressure losses and orifice plate permanent losses below ρg·10⁻⁷ m'
		);
		expect(String(plain.get('Numbers'))).toContain(
			'valve and equipment pressure drops and equipment pressure losses below ρg·10⁻⁷ m'
		);
		const shared = [...plain.keys()].filter((k) => k !== 'Numbers');
		for (const key of shared) {
			if (key.startsWith('Exported') || key.startsWith('Link')) continue;
			expect(rows.get(key), key).toEqual(plain.get(key));
		}
		// The sign row follows the valves' (and the equipment's) sign rows.
		const items = [...rows.keys()];
		expect(items.indexOf('Sign: orifice plate flow')).toBe(
			items.indexOf('Sign: equipment flow') + 1
		);
		// Without equipment either: only the valves' drops and the plates' differences.
		const onlyPlates = withOrifices(fixtureInput('pump-transfer'));
		expect(String(about(onlyPlates).get('Numbers'))).toContain(
			'valve and orifice plate pressure drops and orifice plate permanent losses below ρg·10⁻⁷ m'
		);
	});

	it('writes a bore with its unit, a C as a pure number and no entered C as ISO 5167-2 (default)', () => {
		const input = withOrifices(fixtureInput('scenarios'));
		const s1 = input.cases.find((c) => c.id === 'S1')!;
		const scenario = s1.response!.scenario!;
		const record = (
			index: number,
			id: string,
			field: string,
			value: number | null,
			baseValue: number | null
		): OverrideResult => ({
			index,
			override: { kind: 'component', componentId: id, field, value } as OverrideResult['override'],
			state: 'applied',
			value,
			baseValue,
			unit: field === 'boreDiameter' ? 'm' : '',
			message: ''
		});
		const run: ExportInput = {
			...input,
			cases: input.cases.map((c) =>
				c.id === 'S1'
					? {
							...c,
							response: {
								...c.response!,
								scenario: {
									...scenario,
									overrides: [
										...scenario.overrides,
										record(10, 'O8', 'boreDiameter', 0.016, 0.015),
										record(11, 'O9', 'dischargeCoefficient', null, 0.62),
										record(12, 'O8', 'dischargeCoefficient', 0.605, null)
									]
								}
							}
						}
					: c
			)
		};
		const t = readSheet(buildExport(run), 'scenario-changes');
		const row = (id: string, field: string) =>
			t.rows.find(
				(r) =>
					t.get(r, 'Case id') === 'S1' &&
					t.get(r, 'Element id') === id &&
					t.get(r, 'Field id') === field
			)!;
		const bore = row('O8', 'boreDiameter');
		expect(t.get(bore, 'Field')).toBe('Bore diameter');
		expect(t.get(bore, 'Value')).toBe(0.016);
		expect(t.get(bore, 'Base value')).toBe(0.015);
		expect(t.get(bore, 'Unit')).toBe('m');
		const iso = row('O9', 'dischargeCoefficient');
		expect(t.get(iso, 'Field')).toBe('Discharge coefficient');
		expect(t.get(iso, 'Value')).toBe('ISO 5167-2 (default)');
		expect(t.get(iso, 'Base value')).toBe(0.62);
		expect(t.get(iso, 'Unit')).toBeNull();
		const entered = row('O8', 'dischargeCoefficient');
		expect(t.get(entered, 'Value')).toBe(0.605);
		expect(t.get(entered, 'Base value')).toBe('ISO 5167-2 (default)');
	});
});
