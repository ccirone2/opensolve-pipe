/**
 * The export's Equipment sheet and lines (proposal equipment-pressure-drop.md §5.4). The shared
 * fixture's `scenarios` case holds two real items (export_input.py: the strainer E1 rated by a
 * point, with S1's change of its rated pressure drop, and the cooler E2 rated by a Kv), which the
 * oracles of model.test.ts and the committed workbook check on real API responses. Here two more
 * items, a coil rated by a point and a strainer rated by a Kv, take the place of each case's
 * equipment results, with made-up results (test inputs, not hydraulic results), so that every
 * fixture case can carry equipment, in reverse flow too: SI cells are the API's doubles bit for
 * bit, display cells `fromSI` of the field, the screen's table reads the same fields, the rating
 * columns are the rating used, About gains its equipment lines only with the sheet, and a case
 * that did not converge gives no values.
 */
import { describe, expect, it } from 'vitest';
import type {
	Component,
	EquipmentResult,
	OverrideResult,
	Project,
	SolvedState
} from '../../api/types';
import { equipmentTable, Formatter, HEAD_NOISE, valueText } from '../results';
import { displayUnit, fromSI, STANDARD_GRAVITY } from '../units';
import { fixtureInput, readSheet, sheetIds } from './export-testing.testing';
import { buildExport, type ExportInput } from './model';

const ports = [
	{ id: 'inlet', nominalSize: 0.1016, direction: 'inlet' },
	{ id: 'outlet', nominalSize: 0.1016, direction: 'outlet' }
] as Component['ports'];
const COIL: Component = {
	id: 'E9',
	name: 'Cooling coil',
	elevation: 0,
	type: 'equipment',
	rating: { kind: 'point', pressureLoss: 40000, flow: 0.012, density: 1043.47 },
	ports
};
const STRAINER: Component = {
	id: 'E8',
	name: 'Suction strainer',
	elevation: 0,
	type: 'equipment',
	rating: { kind: 'Kv', value: 60 },
	ports
};

/** Made-up results of the two items in a case (`k` makes each case's numbers its own). */
function results(k: number): Record<string, EquipmentResult> {
	return {
		E9: {
			flow: 0.0131 * k,
			flowRatio: (0.0131 * k) / 0.012,
			headLoss: 4.66 * k,
			pressureLoss: 47700.123456789 * k,
			pressureDrop: 48100.987654321 * k,
			rating: { kind: 'point', pressureLoss: 40000, flow: 0.012, density: 1043.47 }
		},
		E8: {
			flow: -0.0042 * k,
			flowRatio: null,
			headLoss: -0.62 * k,
			pressureLoss: -6081.5 * k,
			pressureDrop: -6050.25 * k,
			rating: { kind: 'Kv', value: 60 }
		}
	};
}

/**
 * `input` with the two items in its projects, and their results in place of each response's
 * equipment results (the fixture's own items stay in the projects, without results).
 */
function withEquipment(input: ExportInput, converged = true): ExportInput {
	const add = (p: Project | null) => p && { ...p, components: [...p.components, COIL, STRAINER] };
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
					equipmentResults: results(1 + i / 10)
				}
			}
		}))
	};
}

/** `input` with no equipment results in any response: a file without an Equipment sheet. */
function withoutEquipment(input: ExportInput): ExportInput {
	return {
		...input,
		cases: input.cases.map((c) => ({
			...c,
			response: c.response && {
				...c.response,
				solvedState: { ...c.response.solvedState, equipmentResults: {} }
			}
		}))
	};
}

/**
 * `input` without orifice plate results (the shared fixture has a flow meter, orifice-plate.md
 * §7.6), so About's lines compared here are the equipment's alone.
 */
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

describe('the Equipment sheet', () => {
	it('SI: every number cell is the API double, with the base unit; ratings as used', () => {
		const input = withEquipment(fixtureInput('scenarios')); // SI, all three cases
		const bundle = buildExport(input);
		expect(sheetIds(bundle)).toContain('equipment');
		// After Valves (a fixture case has a PRV), before Branches.
		const ids = sheetIds(bundle);
		expect(ids.indexOf('equipment')).toBe(ids.indexOf('valves') + 1);
		const t = readSheet(bundle, 'equipment');
		expect(t.headers).toEqual([
			'Case id',
			'Case',
			'Solved at',
			'Results',
			'Equipment id',
			'Equipment',
			'Flow (+ inlet → outlet) [m³/s]',
			'Flow ÷ rated flow',
			'Pressure loss [Pa]',
			'Head loss [m]',
			'Pressure drop, static [Pa]',
			'Rated by',
			'Rated pressure drop (loss) [Pa]',
			'Rated flow [m³/s]',
			'Rated fluid density [kg/m³]',
			'Flow coefficient',
			'Flags'
		]);
		// Two rows per case, in project order (the coil is listed before the strainer).
		expect(t.rows).toHaveLength(6);
		for (const row of t.rows) {
			const id = String(t.get(row, 'Equipment id'));
			const e = solvedOf(input, t.get(row, 'Case id') as string | null).equipmentResults[id]!;
			const same = (label: string, api: number | null) =>
				api === null
					? expect(t.get(row, label), label).toBeNull()
					: expect(Object.is(t.get(row, label), api), label).toBe(true);
			same('Flow (+ inlet → outlet)', e.flow);
			same('Flow ÷ rated flow', e.flowRatio);
			same('Pressure loss', e.pressureLoss);
			same('Head loss', e.headLoss);
			same('Pressure drop, static', e.pressureDrop);
			const point = e.rating.kind === 'point' ? e.rating : null;
			same('Rated pressure drop (loss)', point?.pressureLoss ?? null);
			same('Rated flow', point?.flow ?? null);
			same('Rated fluid density', point?.density ?? null);
			same('Flow coefficient', e.rating.kind === 'point' ? null : e.rating.value);
			expect(t.get(row, 'Rated by')).toBe(id === 'E9' ? 'Pressure drop at a flow' : 'Kv');
			expect(t.get(row, 'Equipment')).toBe(id === 'E9' ? 'Cooling coil' : 'Suction strainer');
		}
	});

	it('display units: fromSI of each field, and the screen reads the same fields', () => {
		const input = withEquipment(fixtureInput('pump-transfer')); // display units, one case
		const bundle = buildExport(input);
		const t = readSheet(bundle, 'equipment');
		const prefs = input.prefs;
		const solved = solvedOf(input, null);
		const unit = (category: Parameters<typeof displayUnit>[0]) => displayUnit(category, prefs);
		expect(t.rows.map((r) => t.get(r, 'Equipment id'))).toEqual(['E9', 'E8']);
		for (const row of t.rows) {
			const e = solved.equipmentResults[String(t.get(row, 'Equipment id'))]!;
			expect(t.get(row, 'Flow (+ inlet → outlet)')).toBe(fromSI(e.flow, unit('flow')));
			expect(t.get(row, 'Flow ÷ rated flow')).toBe(
				e.flowRatio === null ? null : fromSI(e.flowRatio, unit('fraction'))
			);
			expect(t.get(row, 'Pressure loss')).toBe(fromSI(e.pressureLoss, unit('pressure')));
			expect(t.get(row, 'Head loss')).toBe(fromSI(e.headLoss, unit('head')));
			expect(t.get(row, 'Pressure drop, static')).toBe(fromSI(e.pressureDrop, unit('pressure')));
		}
		// A pressure difference: no gauge marker in the header.
		expect(t.headers).toContain(`Pressure loss [${prefs.pressure}]`);
		// The screen's table: the same items and order, each cell the field in the same category.
		const f = new Formatter(prefs);
		const screen = equipmentTable(input.project, solved, prefs);
		expect(screen.rows.map((r) => r.key)).toEqual(['E9', 'E8']);
		const noise = solved.fluid.density * STANDARD_GRAVITY * HEAD_NOISE;
		for (const row of screen.rows) {
			const e = solved.equipmentResults[row.key]!;
			expect(row.cells.flow).toBe(f.num(e.flow, 'flow'));
			expect(row.cells.flowRatio).toBe(f.num(e.flowRatio, 'fraction'));
			expect(valueText(row.cells.pressureLoss as string)).toBe(
				valueText(f.diff(e.pressureLoss, 'pressure', noise))
			);
			expect(valueText(row.cells.pressureDrop as string)).toBe(
				valueText(f.diff(e.pressureDrop, 'pressure', noise))
			);
		}
	});

	it('is left out without equipment, and holds no values from a solve that did not converge', () => {
		expect(sheetIds(buildExport(fixtureInput('pump-transfer')))).not.toContain('equipment');
		const stopped = withEquipment(fixtureInput('pump-transfer'), false);
		expect(sheetIds(buildExport(stopped))).not.toContain('equipment');
	});
});

describe('About and Scenario changes with equipment', () => {
	/** About's rows as Item → Value (without orifice plates: their lines are their own). */
	function about(input: ExportInput): Map<string, unknown> {
		const t = readSheet(buildExport(withoutOrifices(input)), 'about');
		return new Map(t.rows.map((r) => [String(t.get(r, 'Item')), t.get(r, 'Value')]));
	}

	it('adds the equipment lines only with an Equipment sheet', () => {
		const plain = about(withoutEquipment(fixtureInput('scenarios')));
		expect(plain.has('Sheet: Equipment')).toBe(false);
		// The fixture's own two items in its three cases, and the two made-up ones in their place.
		expect(about(fixtureInput('scenarios')).get('Sheet: Equipment')).toBe(6);
		const rows = about(withEquipment(fixtureInput('scenarios')));
		expect(rows.get('Sheet: Equipment')).toBe(6);
		expect(rows.get('Sign: equipment flow')).toMatch(/^\+ inlet → outlet; /);
		expect(plain.has('Sign: equipment flow')).toBe(false);
		expect(rows.get('Units: fractions (speed, efficiency, flow ÷ rated flow)')).toBe(
			'none (a pure number)'
		);
		expect(plain.has('Units: fractions (speed, efficiency)')).toBe(true);
		// Flow ÷ rated flow is no 0–1 fraction: it is signed and unbounded (this file's made-up
		// items run above their rated flows), so the SI line says so apart from speed and efficiency.
		expect(rows.get('Units: fractions')).toBe(
			'Fractions (speed, efficiency) are 0–1 and carry no unit. Flow ÷ rated flow is a signed ratio with no unit: 1 at the rated flow, negative when the flow runs from outlet to inlet.'
		);
		expect(plain.get('Units: fractions')).toBe(
			'Fractions (speed, efficiency) are 0–1 and carry no unit.'
		);
		expect(String(rows.get('Units: exceptions'))).toMatch(
			/A Cv \(US gpm of water at 1 psi\) or Kv \(m³\/h of water at 1 bar\) is as entered in every unit system\.$/
		);
		expect(String(plain.get('Units: exceptions'))).not.toMatch(/Cv/);
		expect(String(rows.get('Numbers'))).toContain(
			'valve and equipment pressure drops and equipment pressure losses below ρg·10⁻⁷ m'
		);
		expect(String(plain.get('Numbers'))).toContain('valve pressure drops below ρg·10⁻⁷ m');
		// Every other row is as without equipment.
		const shared = [...plain.keys()].filter(
			(k) => !k.startsWith('Units: fractions') && k !== 'Units: exceptions' && k !== 'Numbers'
		);
		for (const key of shared) {
			if (key.startsWith('Exported') || key.startsWith('Link')) continue;
			expect(rows.get(key), key).toEqual(plain.get(key));
		}
	});

	it('writes a whole rating and a Cv or Kv as text, a rated value as a number with its unit', () => {
		const input = withEquipment(fixtureInput('scenarios'));
		const s1 = input.cases.find((c) => c.id === 'S1')!;
		const scenario = s1.response!.scenario!;
		const records: OverrideResult[] = [
			{
				index: 10,
				override: {
					kind: 'component',
					componentId: 'E9',
					field: 'rating',
					value: { kind: 'Cv', value: 120 }
				},
				state: 'applied',
				value: { kind: 'Cv', value: 120 },
				baseValue: { kind: 'point', pressureLoss: 40000, flow: 0.012, density: 1043.47 },
				unit: '',
				message: ''
			},
			{
				index: 11,
				override: { kind: 'component', componentId: 'E8', field: 'rating.value', value: 55.5 },
				state: 'applied',
				value: 55.5,
				baseValue: 60,
				unit: '',
				message: ''
			},
			{
				index: 12,
				override: {
					kind: 'component',
					componentId: 'E9',
					field: 'rating.pressureLoss',
					value: 70000
				},
				state: 'not_applicable',
				value: null,
				baseValue: null,
				unit: '',
				message: 'made-up: rated by a Cv in this scenario'
			}
		];
		const run: ExportInput = {
			...input,
			cases: input.cases.map((c) =>
				c.id === 'S1'
					? {
							...c,
							response: {
								...c.response!,
								scenario: { ...scenario, overrides: [...scenario.overrides, ...records] }
							}
						}
					: c
			)
		};
		const t = readSheet(buildExport(run), 'scenario-changes');
		const row = (field: string, id = field === 'rating.value' ? 'E8' : 'E9') =>
			t.rows.find(
				(r) =>
					t.get(r, 'Case id') === 'S1' &&
					t.get(r, 'Element id') === id &&
					t.get(r, 'Field id') === field
			)!;
		expect(t.get(row('rating'), 'Field')).toBe('Rating');
		expect(t.get(row('rating'), 'Value')).toBe('Cv 120');
		expect(t.get(row('rating'), 'Base value')).toBe('40000 Pa at 0.012 m³/s, 1043.47 kg/m³');
		expect(t.get(row('rating'), 'Unit')).toBeNull();
		expect(t.get(row('rating.value'), 'Field')).toBe('Kv');
		expect(t.get(row('rating.value'), 'Value')).toBe('Kv 55.5');
		expect(t.get(row('rating.value'), 'Base value')).toBe('Kv 60');
		expect(t.get(row('rating.value'), 'Unit')).toBeNull();
		expect(t.get(row('rating.pressureLoss'), 'Field')).toBe('Rated pressure drop');
		expect(t.get(row('rating.pressureLoss'), 'Value')).toBeNull();
		// The fixture's own change, applied by the server: S1's dirty strainer E1 (SI file).
		const dirty = row('rating.pressureLoss', 'E1');
		expect(t.get(dirty, 'State')).toBe('Applied');
		expect(t.get(dirty, 'Field')).toBe('Rated pressure drop');
		expect(t.get(dirty, 'Value')).toBe(40000);
		expect(t.get(dirty, 'Base value')).toBe(20000);
		expect(t.get(dirty, 'Unit')).toBe('Pa');
	});
});
