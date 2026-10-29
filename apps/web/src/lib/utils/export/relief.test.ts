/**
 * The export's Relief valves sheet and lines (proposal pressure-relief-valve.md §5). Two relief
 * valves, an API 526 letter at partial lift and a certified valve past full lift, take their place
 * in each case of the shared fixture (real API responses, export_input.py) with made-up results
 * (test inputs, not hydraulic results): SI cells are the API's doubles bit for bit, display cells
 * `fromSI` of the field, the screen's table reads the same fields, the set, overpressure and
 * capacity are the ones the solve used, a valve with no result is listed by its flag, About gains
 * its relief lines only with the sheet (a file without relief valves is as before), a case that
 * did not converge gives no values, and the scenario changes write a set as a difference, a
 * capacity with exact numbers and a certified overpressure on ASME's default in words.
 */
import { describe, expect, it } from 'vitest';
import type {
	Component,
	OverrideResult,
	Project,
	ReliefValveResult,
	SolvedState
} from '../../api/types';
import { flag } from '../../testing/results';
import { Formatter, HEAD_NOISE, reliefTable, RELIEF_NO_RESULT, valueText } from '../results';
import { displayUnit, fromSI, STANDARD_GRAVITY } from '../units';
import { fixtureInput, readSheet, sheetIds, withoutReliefValves } from './export-testing.testing';
import { buildExport, type ExportInput } from './model';

const ports = [
	{ id: 'inlet', nominalSize: 0.0508, direction: 'inlet' },
	{ id: 'outlet', nominalSize: 0.0762, direction: 'outlet' }
] as Component['ports'];
const LETTER: Component = {
	id: 'RV9',
	name: 'Header relief',
	elevation: 0,
	type: 'relief_valve',
	setPressure: 500000,
	capacity: { kind: 'api526', letter: 'F' },
	status: 'active',
	ports
};
const CERTIFIED: Component = {
	id: 'RV8',
	name: 'Bypass relief',
	elevation: 0,
	type: 'relief_valve',
	setPressure: 350000,
	capacity: { kind: 'certified', area: 0.00025, dischargeCoefficient: 0.7, overpressure: 0.08 },
	status: 'active',
	ports
};
const CLOSED: Component = { ...LETTER, id: 'RV7', name: 'Spare relief' } as Component;

/** Made-up results of the two valves in a case (`k` makes each case's numbers its own). */
function results(k: number): Record<string, ReliefValveResult> {
	return {
		RV9: {
			state: 'partial_lift',
			flow: 0.002221210802348 * k,
			lift: 0.5311270926,
			headLoss: 53.80140800223 * k,
			totalPressureDifference: 526556.3546123 * k,
			pressureDrop: 526139.3676789 * k,
			inletPressure: 526131.6131234 * k,
			backPressure: -7.754453834,
			setPressure: 500000,
			setRatio: 1.053112709246 * k,
			overpressure: 0.1,
			overpressureSource: 'asme_default',
			fullLiftPressureDifference: 550000,
			fullLiftFlow: 0.004274154702,
			flowRatio: 0.5196842317 * k,
			capacity: { kind: 'api526', letter: 'F', area: 0.00019806412, dischargeCoefficient: 0.65 },
			reynoldsNumber: 177412.123 * k
		},
		RV8: {
			state: 'full_lift',
			flow: 0.00637456 * k,
			lift: 1,
			headLoss: 41.2345 * k,
			totalPressureDifference: 403456.789 * k,
			pressureDrop: 403111.222 * k,
			inletPressure: null,
			backPressure: null,
			setPressure: 350000,
			setRatio: 1.15273368 * k,
			overpressure: 0.08,
			overpressureSource: 'user',
			fullLiftPressureDifference: 378000,
			fullLiftFlow: 0.006170262,
			flowRatio: 1.0331107 * k,
			capacity: {
				kind: 'certified',
				area: 0.00025,
				dischargeCoefficient: 0.7,
				overpressure: 0.08
			},
			reynoldsNumber: 289045.5 * k
		}
	};
}

/**
 * `input` with the three valves in its projects (RV7 with no result: closed, its inlet floating),
 * and the two others' results in place of each response's relief valve results.
 */
function withRelief(input: ExportInput, converged = true): ExportInput {
	const add = (p: Project | null) =>
		p && { ...p, components: [...p.components, LETTER, CERTIFIED, CLOSED] };
	const closed = flag({
		code: 'RELIEF_VALVE_CLOSED',
		severity: 'info',
		message: 'made-up',
		componentId: 'RV7',
		details: { side: 'inlet', section: 'floating', setHead: 51.09, setPressure: 500000 }
	});
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
					reliefValveResults: results(1 + i / 10),
					flags: [...c.response.solvedState.flags, closed]
				}
			}
		}))
	};
}

const solvedOf = (input: ExportInput, id: string | null): SolvedState =>
	input.cases.find((c) => c.id === id)!.response!.solvedState;

describe('the Relief valves sheet', () => {
	it('SI: every number cell is the API double, with the base unit; the capacity as used', () => {
		const input = withRelief(fixtureInput('scenarios')); // SI, all three cases
		const bundle = buildExport(input);
		// After Valves (a fixture case has a PRV), before Equipment.
		const ids = sheetIds(bundle);
		expect(ids).toContain('relief-valves');
		expect(ids.indexOf('relief-valves')).toBe(ids.indexOf('valves') + 1);
		expect(ids.indexOf('equipment')).toBe(ids.indexOf('relief-valves') + 1);
		const t = readSheet(bundle, 'relief-valves');
		expect(t.sheet.file).toBe('relief-valves.csv');
		expect(t.sheet.title).toBe('Relief valves');
		expect(t.headers).toEqual([
			'Case id',
			'Case',
			'Solved at',
			'Results',
			'Relief valve id',
			'Relief valve',
			'State',
			'Flow (+ inlet → outlet) [m³/s]',
			'Lift',
			'Capacity (full lift) [m³/s]',
			'Flow ÷ capacity',
			'Inlet pressure [Pa(g)]',
			'Back pressure [Pa(g)]',
			'Δp ÷ set',
			'Pressure difference, total [Pa]',
			'Pressure drop, static [Pa]',
			'Head loss [m]',
			'Set pressure [Pa]',
			'Overpressure at full lift',
			'Overpressure from',
			'Capacity given by',
			'Area [m²]',
			'Kd',
			'Covering letter',
			'Reynolds number (orifice)',
			'Flags'
		]);
		// Three rows per case, in project order; RV7, with no result, by its flag.
		expect(t.rows).toHaveLength(9);
		for (const row of t.rows) {
			const id = String(t.get(row, 'Relief valve id'));
			const v = solvedOf(input, t.get(row, 'Case id') as string | null).reliefValveResults[id];
			if (!v) {
				expect(id).toBe('RV7');
				expect(t.get(row, 'State')).toBe(RELIEF_NO_RESULT);
				expect(t.get(row, 'Flow (+ inlet → outlet)')).toBeNull();
				expect(t.get(row, 'Area')).toBeNull();
				expect(t.get(row, 'Flags')).toBe('RELIEF_VALVE_CLOSED');
				continue;
			}
			const same = (label: string, api: number | null) =>
				api === null
					? expect(t.get(row, label), label).toBeNull()
					: expect(Object.is(t.get(row, label), api), label).toBe(true);
			same('Flow (+ inlet → outlet)', v.flow);
			same('Lift', v.lift);
			same('Capacity (full lift)', v.fullLiftFlow);
			same('Flow ÷ capacity', v.flowRatio);
			same('Inlet pressure', v.inletPressure);
			same('Back pressure', v.backPressure);
			same('Δp ÷ set', v.setRatio);
			same('Pressure difference, total', v.totalPressureDifference);
			same('Pressure drop, static', v.pressureDrop);
			same('Head loss', v.headLoss);
			same('Set pressure', v.setPressure);
			same('Overpressure at full lift', v.overpressure);
			same('Area', v.capacity.area);
			same('Kd', v.capacity.dischargeCoefficient);
			same('Reynolds number (orifice)', v.reynoldsNumber);
			const letter = id === 'RV9';
			expect(t.get(row, 'Relief valve')).toBe(letter ? 'Header relief' : 'Bypass relief');
			expect(t.get(row, 'State')).toBe(letter ? 'Partial lift' : 'Full lift');
			expect(t.get(row, 'Capacity given by')).toBe(letter ? 'API 526 F' : 'Certified');
			expect(t.get(row, 'Overpressure from')).toBe(
				letter ? "ASME's (the default)" : 'Certified (entered)'
			);
			expect(t.get(row, 'Covering letter')).toBeNull();
			expect(t.get(row, 'Flags')).toBeNull();
		}
	});

	it('display units: fromSI of each field, and the screen reads the same fields', () => {
		const input = withRelief(fixtureInput('pump-transfer')); // display units, one case
		const bundle = buildExport(input);
		const t = readSheet(bundle, 'relief-valves');
		const prefs = input.prefs;
		const solved = solvedOf(input, null);
		const unit = (category: Parameters<typeof displayUnit>[0]) => displayUnit(category, prefs);
		expect(t.rows.map((r) => t.get(r, 'Relief valve id'))).toEqual(['RV9', 'RV8', 'RV7']);
		for (const row of t.rows.slice(0, 2)) {
			const v = solved.reliefValveResults[String(t.get(row, 'Relief valve id'))]!;
			const pressure = (x: number | null) => (x === null ? null : fromSI(x, unit('pressure')));
			expect(t.get(row, 'Flow (+ inlet → outlet)')).toBe(fromSI(v.flow, unit('flow')));
			expect(t.get(row, 'Lift')).toBe(fromSI(v.lift, unit('fraction')));
			expect(t.get(row, 'Δp ÷ set')).toBe(fromSI(v.setRatio, unit('fraction')));
			expect(t.get(row, 'Inlet pressure')).toBe(pressure(v.inletPressure));
			expect(t.get(row, 'Pressure difference, total')).toBe(pressure(v.totalPressureDifference));
			expect(t.get(row, 'Set pressure')).toBe(pressure(v.setPressure));
			expect(t.get(row, 'Head loss')).toBe(fromSI(v.headLoss, unit('head')));
			expect(t.get(row, 'Area')).toBe(fromSI(v.capacity.area, unit('area')));
			// Pure numbers are the API's doubles in every unit system.
			expect(t.get(row, 'Kd')).toBe(v.capacity.dischargeCoefficient);
		}
		// A set pressure is a difference: no gauge marker; the inlet pressure has one.
		expect(t.headers).toContain(`Set pressure [${prefs.pressure}]`);
		expect(t.headers.find((h) => h.startsWith('Inlet pressure'))).not.toBe(
			`Inlet pressure [${prefs.pressure}]`
		);
		// The screen's table: the same valves and order, each cell the field in the same category.
		const f = new Formatter(prefs);
		const screen = reliefTable(input.project, solved, prefs);
		expect(screen.rows.map((r) => r.key)).toEqual(['RV9', 'RV8', 'RV7']);
		const noise = solved.fluid.density * STANDARD_GRAVITY * HEAD_NOISE;
		for (const row of screen.rows.slice(0, 2)) {
			const v = solved.reliefValveResults[row.key]!;
			expect(row.cells.flow).toBe(f.num(v.flow, 'flow'));
			expect(row.cells.inletPressure).toBe(f.num(v.inletPressure, 'pressure'));
			expect(row.cells.setRatio).toBe(f.num(v.setRatio, 'fraction'));
			expect(valueText(row.cells.pressureDrop as string)).toBe(
				valueText(f.diff(v.pressureDrop, 'pressure', noise))
			);
		}
	});

	it('names the covering letter of an effective area', () => {
		const input = withRelief(fixtureInput('pump-transfer'));
		const solved = input.cases[0]!.response!.solvedState;
		solved.reliefValveResults.RV8 = {
			...solved.reliefValveResults.RV8!,
			capacity: {
				kind: 'effective',
				area: 0.000447,
				dischargeCoefficient: 0.65,
				coveringLetter: 'H'
			},
			overpressureSource: 'asme_default'
		};
		const t = readSheet(buildExport(input), 'relief-valves');
		const row = t.rows.find((r) => t.get(r, 'Relief valve id') === 'RV8')!;
		expect(t.get(row, 'Capacity given by')).toBe('Effective area');
		expect(t.get(row, 'Covering letter')).toBe('H');
	});

	it('is left out without relief valves, and holds no values from a solve that did not converge', () => {
		expect(sheetIds(buildExport(withoutReliefValves(fixtureInput('pump-transfer'))))).not.toContain(
			'relief-valves'
		);
		const stopped = withRelief(fixtureInput('pump-transfer'), false);
		expect(sheetIds(buildExport(stopped))).not.toContain('relief-valves');
	});
});

describe('About and Scenario changes with relief valves', () => {
	/** About's rows as Item → Value. */
	function about(input: ExportInput): Map<string, unknown> {
		const t = readSheet(buildExport(input), 'about');
		return new Map(t.rows.map((r) => [String(t.get(r, 'Item')), t.get(r, 'Value')]));
	}

	it('adds the relief lines only with a Relief valves sheet; every other row as before', () => {
		const plain = about(withoutReliefValves(fixtureInput('scenarios')));
		const rows = about(withRelief(fixtureInput('scenarios')));
		expect(plain.has('Sheet: Relief valves')).toBe(false);
		expect(rows.get('Sheet: Relief valves')).toBe(9);
		expect(rows.get('Sign: relief valve flow')).toMatch(
			/^\+ inlet → outlet; the valve closes on reverse flow beyond the status rules' flow tolerance \(EPANET 2\.2's Qtol, 1×10⁻⁸ m³\/s\), so a valve at its switch can show a flow a little below zero, with its state closed;/
		);
		expect(plain.has('Sign: relief valve flow')).toBe(false);
		expect(rows.get('Units: areas')).toBe('m²');
		expect(plain.has('Units: areas')).toBe(false);
		// The ≈ 0 rule names the relief valves' pressure drops too.
		expect(String(rows.get('Numbers'))).toContain(
			'valve, relief valve, equipment and orifice plate pressure drops'
		);
		expect(String(plain.get('Numbers'))).not.toContain('relief valve');
		// The Numbers row names the relief valves, and the made-up flag of RV7 is a Flags row.
		const changed = new Set(['Numbers', 'Units: fractions', 'Sheet: Flags']);
		for (const key of [...plain.keys()]) {
			if (key.startsWith('Exported') || key.startsWith('Link')) continue;
			if (key.startsWith('Units: fractions')) continue;
			if (changed.has(key)) continue;
			expect(rows.get(key), key).toEqual(plain.get(key));
		}
		// SI: the ratios are no 0–1 fractions, and the fractions' row names them.
		expect(String(rows.get('Units: fractions'))).toMatch(
			/A relief valve's Δp ÷ set is a ratio with no unit, 1 at its set and above 1 while it relieves/
		);
		expect(
			[...rows.keys()].some((k) => /^Units: fractions \(.*a relief valve's lift/.test(k))
		).toBe(true);
		// The sign row follows the valves' sign row, before the equipment's.
		const items = [...rows.keys()];
		expect(items.indexOf('Sign: relief valve flow')).toBe(items.indexOf('Sign: valve flow') + 1);
	});

	it("writes a set as a difference, a capacity with its exact numbers, ASME's overpressure in words", () => {
		const input = withRelief(fixtureInput('scenarios'));
		const s1 = input.cases.find((c) => c.id === 'S1')!;
		const scenario = s1.response!.scenario!;
		const record = (
			index: number,
			field: string,
			value: unknown,
			baseValue: unknown,
			unit: string
		): OverrideResult => ({
			index,
			override: { kind: 'component', componentId: 'RV8', field: field as never, value },
			state: 'applied',
			value,
			baseValue,
			unit,
			message: ''
		});
		scenario.overrides = [
			record(0, 'setPressure', 400000, 350000, 'Pa'),
			record(1, 'capacity.overpressure', null, 0.08, ''),
			record(
				2,
				'capacity',
				{ kind: 'api526', letter: 'J' },
				{ kind: 'certified', area: 0.00025, dischargeCoefficient: 0.7, overpressure: 0.08 },
				''
			),
			record(3, 'capacity.area', 0.0003, 0.00025, 'm²')
		];
		const t = readSheet(buildExport(input), 'scenario-changes');
		const rows = t.rows.filter((r) => t.get(r, 'Element id') === 'RV8');
		expect(
			rows.map((r) => [
				t.get(r, 'Field'),
				t.get(r, 'Value'),
				t.get(r, 'Base value'),
				t.get(r, 'Unit')
			])
		).toEqual([
			['Set pressure', 400000, 350000, 'Pa'],
			[
				'Overpressure at full lift',
				"ASME's 10 % or 3 psi, whichever is greater (the default)",
				0.08,
				null
			],
			[
				'Capacity',
				'API 526 J (0.00083032092 m²), Kd 0.65 (preliminary)',
				'Certified area 0.00025 m², rated coefficient 0.7, overpressure 0.08',
				null
			],
			['Actual orifice area', 0.0003, 0.00025, 'm²']
		]);
	});
});
