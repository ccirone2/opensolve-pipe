/**
 * The orifice plate in the web's utilities (proposal orifice-plate.md §5.3, §5.4, §6, §7.6): the
 * pipe bore D and β the form shows (utils/orifice.ts), the published rules, links, the results
 * table, view and strip, Compare's rows and its one element-kind mapping, goal seek's groups,
 * need check, bounds and start text, the scenario words, and the flag and issue texts. Bores,
 * pipes, flows and solved states are made-up test inputs (testing/helpers.ts orificeProject,
 * testing/results.ts orificeSolved, testing/library.ts TEST_LIBRARY); expected display values are
 * computed here from the unit definitions (NIST SP 811), not from units.ts. The topology issue's
 * server messages were printed by the API's own builder (_orifice_issue_text) for these plates.
 */
import { describe, expect, it } from 'vitest';
import type {
	Component,
	Flag,
	Override,
	PipeDefinition,
	Project,
	TopologyIssue
} from '../api/types';
import { deepFreeze, enteredFor, orificeProject } from '../testing/helpers';
import { TEST_LIBRARY } from '../testing/library';
import { flag, orificeResult, orificeSolved } from '../testing/results';
import {
	compareCells,
	compareElementKind,
	defaultRows,
	ELEMENT_QUANTITIES,
	QUANTITIES,
	rowLabel
} from './compare';
import { decodeProject, encodeProject } from './encoding';
import { changeCategory } from './export/tables';
import { COMPONENT_KINDS, componentKind, createComponent } from './factory';
import { flagText } from './flag-text';
import {
	defaultBounds,
	goalChoices,
	goalElements,
	goalHint,
	goalNeedProblem,
	goalSpec,
	goalValue,
	newVariable,
	nowText,
	variableChoices,
	variableSpec
} from './goal-seek';
import { topologyIssueViews } from './issue-text';
import { GOAL_QUANTITY_RULES, GOAL_VARIABLE_FIELDS, OVERRIDE_FIELDS } from './model-rules';
import { betaLine, inletBore, pipeAtPort, type PipeSizes } from './orifice';
import { sameSize } from './labels';
import {
	availableViews,
	elementSummary,
	orificeCoefficientSource,
	orificeTable,
	rowsForElement,
	valueText,
	type Cell
} from './results';
import { applyScenario, changeValueText, fieldLabelFor, withScenarios } from './scenarios';
import { IMPERIAL_UNITS, INCH, SI_UNITS } from './units';
import { schemaProblems } from './validate';

// Definitions (exact): 1 in = 0.0254 m, 1 lb = 0.45359237 kg, g_n = 9.80665 m/s², US gallon =
// 231 in³.
const IN = 0.0254;
const LB = 0.45359237;
const PSI = (LB * 9.80665) / (IN * IN); // Pa
const GPM = (231 * IN ** 3) / 60; // m³/s
const sig4 = (v: number) => String(Number(v.toPrecision(4)));

/** TEST_LIBRARY's NPS 4 schedule 40 inner diameter, m (a test input). */
const D4 = 0.10226;
const O1 = { kind: 'component', componentId: 'O1' } as const;
const NOMINAL_SIZES = [3, 4, 6].map((n) => ({ nominalSize: n * INCH, nps: String(n) }));

/** The pipe library as the resolver reads it: TEST_LIBRARY, loaded or not. */
function library(status: PipeSizes['libraryStatus'] = 'ready'): PipeSizes {
	return {
		libraryStatus: status,
		size: (materialId, scheduleId, nominalSize) =>
			status !== 'ready' || nominalSize == null
				? undefined
				: TEST_LIBRARY.materials
						.find((m) => m.id === materialId)
						?.schedules.find((s) => s.id === scheduleId)
						?.sizes.find((s) => sameSize(s.nominalSize, nominalSize))
	};
}

/** orificeProject with L1's pipes replaced (and L1 reversed when `reversed`). */
function withInletPipes(pipes: PipeDefinition[], reversed = false): Project {
	const project = orificeProject();
	const [l1, l2] = project.connections;
	const inlet = reversed
		? {
				...l1!,
				fromComponentId: 'O1',
				fromPortId: 'inlet',
				toComponentId: 'R1',
				toPortId: 'port_1'
			}
		: l1!;
	return { ...project, connections: [{ ...inlet, piping: { pipes, fittings: [] } }, l2!] };
}

const nps = (n: number, length = 10): PipeDefinition => ({
	materialId: 'carbon_steel',
	schedule: '40',
	nominalSize: n * INCH,
	length
});

describe('the pipe bore D and β the form shows (utils/orifice.ts, §6 W3)', () => {
	it('reads D from the library pipe at the inlet: β to 4 decimals, D in the diameter unit', () => {
		const inlet = inletBore(orificeProject(), 'O1', library());
		expect(inlet).toEqual({ state: 'known', diameter: D4, pipe: nps(4) });
		expect(betaLine(0.05, inlet, SI_UNITS, NOMINAL_SIZES)).toEqual({
			// 0.05 ÷ 0.10226 = 0.48895 to 5 digits, 0.4889 to 4 decimals (0.488950 rounds down).
			text: 'β = d ÷ D = 0.4889, with D = 102.3 mm, the inner diameter of the inlet pipe (NPS 4, Sch 40)',
			warning: false,
			beta: 0.05 / D4
		});
		expect(betaLine(0.05, inlet, IMPERIAL_UNITS, NOMINAL_SIZES).text).toBe(
			`β = d ÷ D = 0.4889, with D = ${sig4(D4 / IN)} in, the inner diameter of the inlet pipe (NPS 4, Sch 40)`
		);
	});

	it("takes the pipe that meets the inlet port: the first at the 'from' end, the last at the 'to'", () => {
		const atTo = withInletPipes([nps(3), nps(6)]);
		expect(pipeAtPort(atTo.connections[0]!, 'O1', 'inlet')).toEqual({ pipe: nps(6), index: 1 });
		expect(inletBore(atTo, 'O1', library())).toMatchObject({ diameter: 0.15405 });
		const atFrom = withInletPipes([nps(3), nps(6)], true);
		expect(pipeAtPort(atFrom.connections[0]!, 'O1', 'inlet')).toEqual({ pipe: nps(3), index: 0 });
		expect(inletBore(atFrom, 'O1', library())).toMatchObject({ diameter: 0.07792 });
	});

	it('reads a custom pipe and an inner-diameter override without the library', () => {
		const custom: PipeDefinition = {
			materialId: 'custom',
			innerDiameter: 0.09,
			roughness: 1e-5,
			length: 10
		};
		const inlet = inletBore(withInletPipes([custom]), 'O1', library('loading'));
		expect(inlet).toEqual({ state: 'known', diameter: 0.09, pipe: custom });
		expect(betaLine(0.045, inlet, SI_UNITS).text).toBe(
			'β = d ÷ D = 0.5000, with D = 90 mm, the inner diameter of the inlet pipe (a custom pipe)'
		);
		const override = { ...nps(4), innerDiameter: 0.1 };
		const overridden = inletBore(withInletPipes([override]), 'O1', library('unavailable'));
		expect(overridden).toEqual({ state: 'known', diameter: 0.1, pipe: override });
		expect(betaLine(0.05, overridden, SI_UNITS, NOMINAL_SIZES).text).toBe(
			'β = d ÷ D = 0.5000, with D = 100 mm, the inner diameter of the inlet pipe (NPS 4, Sch 40, inner diameter override)'
		);
	});

	it('says when β will be shown: the inlet not connected, the library not loaded, no size', () => {
		const open = { ...orificeProject(), connections: orificeProject().connections.slice(1) };
		const unconnected = inletBore(open, 'O1', library());
		expect(unconnected).toEqual({ state: 'unconnected' });
		expect(betaLine(0.05, unconnected, SI_UNITS)).toEqual({
			text: 'β is shown once the inlet is connected.',
			warning: false
		});
		const loading = inletBore(orificeProject(), 'O1', library('loading'));
		expect(loading).toEqual({ state: 'library', pipe: nps(4) });
		expect(betaLine(0.05, loading, SI_UNITS).text).toBe('β is shown once the pipe library loads.');
		// A size the library does not have: the solve reports it as a topology issue.
		const missing = inletBore(withInletPipes([nps(5)]), 'O1', library());
		expect(missing).toEqual({ state: 'unknown', pipe: nps(5) });
		expect(betaLine(0.05, missing, SI_UNITS).text).toBe(
			"β is shown once the inlet pipe's inner diameter is known."
		);
	});

	it('warns, never refuses, when the bore is not smaller than D: the solve refuses it', () => {
		const inlet = inletBore(orificeProject(), 'O1', library());
		for (const bore of [0.11, D4]) {
			expect(betaLine(bore, inlet, SI_UNITS)).toEqual({
				text: "β ≥ 1: the bore is not smaller than the inlet pipe's (102.3 mm); the solve refuses it.",
				warning: true,
				beta: bore / D4
			});
		}
	});
});

describe('published rules and links (§2.1, §2.3)', () => {
	it('publishes the two allow-list entries, the two variables and the four goals', () => {
		expect(OVERRIDE_FIELDS.Orifice).toEqual({
			boreDiameter: { schema: 'Orifice', path: ['boreDiameter'], keys: [] },
			dischargeCoefficient: { schema: 'Orifice', path: ['dischargeCoefficient'], keys: [] }
		});
		expect(GOAL_VARIABLE_FIELDS.Orifice).toMatchObject({
			boreDiameter: { schema: 'Orifice', path: ['boreDiameter'], scale: 'log' },
			dischargeCoefficient: { schema: 'Orifice', path: ['dischargeCoefficient'], scale: 'linear' }
		});
		for (const quantity of [
			'orifice_flow',
			'orifice_pressure_loss',
			'orifice_differential_pressure',
			'orifice_pressure_drop'
		]) {
			expect(GOAL_QUANTITY_RULES[quantity]?.targets, quantity).toEqual(['Orifice']);
			// The reading needs taps (published as `needs`, never copied: D10).
			expect(GOAL_QUANTITY_RULES[quantity]?.needs, quantity).toEqual(
				quantity === 'orifice_differential_pressure' ? ['taps'] : []
			);
		}
	});

	it('round-trips a plate exactly, every optional field; schemaVersion stays 1', () => {
		for (const plate of [
			{},
			{ dischargeCoefficient: 0.6, taps: 'flange' as const },
			// Doubles that take 17 digits (typed values converted to SI are such numbers).
			{ boreDiameter: 0.05 / 3, dischargeCoefficient: 0.62 / 1.0000001, taps: 'd_and_d_2' as const }
		]) {
			const project = orificeProject(plate);
			const encoded = encodeProject(project);
			const decoded = decodeProject(encoded);
			expect(decoded).toEqual(project);
			expect(decoded.schemaVersion).toBe(1);
			expect(encodeProject(decoded)).toBe(encoded);
		}
	});

	it('reports a bore or a C out of its bounds, and an unknown tap set, at its field', () => {
		const bad = structuredClone(orificeProject());
		const plate = bad.components[1] as unknown as Record<string, unknown>;
		plate.boreDiameter = 0;
		expect(schemaProblems(bad).join(' ')).toMatch(/"O1" › boreDiameter: must be > 0/);
		plate.boreDiameter = 0.05;
		plate.dischargeCoefficient = 1.2;
		expect(schemaProblems(bad).join(' ')).toMatch(/"O1" › dischargeCoefficient/);
		plate.dischargeCoefficient = 0.6;
		plate.taps = 'vena_contracta';
		expect(schemaProblems(bad).join(' ')).toMatch(/"O1" › taps/);
	});
});

describe('results: the Orifices view, table and strip (§6 W4, W5)', () => {
	const project = orificeProject();
	const element = { kind: 'component', id: 'O1' } as const;

	it('shows the view only when the solve has plates, after Equipment; an older response has none', () => {
		expect(availableViews(orificeSolved())).toEqual([
			'summary',
			'nodes',
			'links',
			'orifices',
			'boundaries',
			'methods'
		]);
		expect(availableViews(orificeSolved({}, { orificeResults: {} }))).not.toContain('orifices');
		const older = { ...orificeSolved() } as Partial<ReturnType<typeof orificeSolved>>;
		delete older.orificeResults;
		const solved = older as ReturnType<typeof orificeSolved>;
		expect(availableViews(solved)).not.toContain('orifices');
		expect(orificeTable(project, solved, SI_UNITS).rows).toEqual([]);
	});

	it('gives ten columns in display units, "—" for the reading without taps', () => {
		const table = orificeTable(project, orificeSolved(), SI_UNITS);
		expect(table.columns.map((c) => [c.label, c.unit])).toEqual([
			['Flow (+ inlet → outlet)', 'L/s'],
			['Permanent loss', 'kPa'],
			['Differential pressure (taps)', 'kPa'],
			['β', undefined],
			['C', undefined],
			['C from', undefined],
			['Re (inlet pipe)', undefined],
			['Vena contracta pressure', 'kPa(g)'],
			['Pressure drop (static)', 'kPa'],
			['Head loss', 'm']
		]);
		const [row] = table.rows;
		expect(row!.name).toBe('Bypass orifice');
		expect(row!.detail).toBe('Orifice plate (ISO 5167-2) · O1');
		expect(row!.cells).toEqual({
			flow: '13',
			pressureLoss: '42.1',
			differentialPressure: '—',
			beta: '0.489',
			dischargeCoefficient: '0.6047',
			coefficientSource: 'ISO 5167-2',
			reynoldsNumber: '160000',
			venaContractaPressure: '-20',
			pressureDrop: '42.1',
			headLoss: '4.3'
		});
		const meter = orificeSolved({ taps: 'flange', differentialPressure: 57100 });
		const us = orificeTable(project, meter, IMPERIAL_UNITS).rows[0]!.cells;
		expect(us.flow).toBe(sig4(0.013 / GPM));
		expect(us.pressureLoss).toBe(sig4(42100 / PSI));
		expect(us.differentialPressure).toBe(sig4(57100 / PSI));
		expect(us.venaContractaPressure).toBe(sig4(-20000 / PSI));
	});

	it('says where C came from: ISO 5167-2, held, entered, or entered and moved', () => {
		expect(orificeCoefficientSource(orificeResult())).toBe('ISO 5167-2');
		// Held: C is evaluated at ISO's lowest Reynolds number, above the flow's (flagged).
		expect(
			orificeCoefficientSource(
				orificeResult({ reynoldsNumber: 1017.76, coefficientReynoldsNumber: 5000 })
			)
		).toBe('ISO 5167-2 (held)');
		expect(
			orificeCoefficientSource(
				orificeResult({ coefficientSource: 'entered', coefficientReynoldsNumber: null })
			)
		).toBe('Entered');
		expect(
			orificeCoefficientSource(
				orificeResult({ coefficientSource: 'entered', tapCoefficientRatio: 1.021 })
			)
		).toBe('Entered, moved to D and D/2');
	});

	it('shows ≈ 0 below the head resolution and "—" for a vena contracta with no jet', () => {
		// ρg × 10⁻⁷ m at 998 kg/m³ is about 9.8×10⁻⁴ Pa.
		const still = orificeSolved({
			flow: 0,
			pressureLoss: 5e-4,
			headLoss: 5e-8,
			pressureDrop: 2e-4,
			venaContractaPressure: null
		});
		const cells = orificeTable(project, still, SI_UNITS).rows[0]!.cells;
		for (const key of ['pressureLoss', 'headLoss', 'pressureDrop']) {
			expect(valueText(cells[key] as Cell as string), key).toBe('≈ 0');
		}
		expect(cells.venaContractaPressure).toBe('—');
	});

	it('gives the trace its rows and the strip the table cells: flow, loss and the reading', () => {
		const groups = rowsForElement(project, orificeSolved(), SI_UNITS, element);
		expect(groups.map((g) => g.title)).toEqual(['Orifice plate', 'Ports']);
		// Without taps the strip leaves the reading's "—" out.
		const summary = elementSummary(project, orificeSolved(), SI_UNITS, element);
		expect(summary?.items.map((i) => [i.label, i.cell, i.unit])).toEqual([
			['Flow (+ inlet → outlet)', '13', 'L/s'],
			['Permanent loss', '42.1', 'kPa']
		]);
		const meter = orificeSolved({ taps: 'flange', differentialPressure: 57100 });
		const items = elementSummary(project, meter, SI_UNITS, element)!.items;
		const row = orificeTable(project, meter, SI_UNITS).rows[0]!;
		expect(items.map((i) => i.key)).toEqual(['flow', 'pressureLoss', 'differentialPressure']);
		for (const item of items) expect(item.cell, item.key).toEqual(row.cells[item.key]);
	});
});

describe('Compare: the orifice rows and the one element-kind mapping (§5.3)', () => {
	const base = orificeSolved({ taps: 'flange', differentialPressure: 57100 });
	const bigger = orificeSolved({
		taps: 'flange',
		flow: 0.0192,
		pressureLoss: 35400,
		differentialPressure: 55200,
		pressureDrop: 35000
	});
	const columns = [base, bigger].map((solved) => ({ solved, converged: true }));
	const change = (field: string, value: unknown): Override =>
		({ kind: 'component', componentId: 'O1', field, value }) as Override;
	const project = deepFreeze(
		withScenarios(orificeProject({ taps: 'flange' }), [
			{ id: 'S1', name: 'Bigger bore', overrides: [change('boreDiameter', 0.06)] }
		])
	);

	it('reads flow, permanent loss, reading and static drop; relative only with a true zero', () => {
		expect(ELEMENT_QUANTITIES.orifice).toEqual([
			'orificeFlow',
			'orificePressureLoss',
			'orificeDifferentialPressure',
			'orificePressureDrop'
		]);
		expect(
			QUANTITIES.orificeDifferentialPressure.value(base, {
				quantity: 'orificeDifferentialPressure',
				elementId: 'O1'
			})
		).toBe(57100);
		const cells = (quantity: (typeof ELEMENT_QUANTITIES.orifice)[number]) =>
			compareCells({ quantity, elementId: 'O1' }, columns, project, SI_UNITS);
		expect(cells('orificeFlow')[1]!.diff!.text).toBe('+6.2 (+47.7 %)');
		expect(cells('orificePressureLoss')[1]!.diff!.text).toBe('−6.7 (−15.9 %)');
		expect(cells('orificeDifferentialPressure')[1]!.diff!.text).toBe('−1.9 (−3.33 %)');
		// The static drop holds the ports' elevation and velocity terms: no true zero.
		expect(cells('orificePressureDrop')[1]!.diff!.text).toBe('−7.1');
		expect(rowLabel(project, { quantity: 'orificePressureLoss', elementId: 'O1' })).toBe(
			'Bypass orifice · Permanent loss'
		);
		// No reading without taps: no value, so no difference.
		const plain = [orificeSolved(), orificeSolved()].map((solved) => ({ solved, converged: true }));
		const reading = compareCells(
			{ quantity: 'orificeDifferentialPressure', elementId: 'O1' },
			plain,
			project,
			SI_UNITS
		);
		expect(reading.map((c) => [c.text, c.diff])).toEqual([
			['—', undefined],
			['—', undefined]
		]);
	});

	it("adds a plate's flow and permanent loss to the default rows when a scenario changes it", () => {
		const rows = defaultRows(project, [base, bigger]);
		expect(rows).toContainEqual({ quantity: 'orificeFlow', elementId: 'O1' });
		expect(rows).toContainEqual({ quantity: 'orificePressureLoss', elementId: 'O1' });
		const unchanged = withScenarios(orificeProject(), [{ id: 'S1', name: 'Other', overrides: [] }]);
		expect(defaultRows(unchanged, [base, null])).not.toContainEqual({
			quantity: 'orificeFlow',
			elementId: 'O1'
		});
	});

	it('maps every kind of component to its rows once (the dialog and the trace read it)', () => {
		let project = orificeProject();
		const kinds = new Map<string, string | null>();
		for (const kind of COMPONENT_KINDS) {
			const component: Component = createComponent(kind, project, enteredFor(kind));
			project = { ...project, components: [...project.components, component] };
			kinds.set(componentKind(component), compareElementKind(component));
		}
		expect(Object.fromEntries(kinds)).toEqual({
			reservoir: 'boundary',
			reference_node: 'boundary',
			plug: null,
			assigned_flow: 'assigned',
			tee: null,
			wye: null,
			pump: 'pump',
			gate: 'valve',
			ball: 'valve',
			butterfly: 'valve',
			globe: 'valve',
			check: 'valve',
			stop_check: 'valve',
			prv: 'valve',
			psv: 'valve',
			fcv: 'valve',
			equipment: 'equipment',
			orifice: 'orifice'
		});
	});
});

describe('goal seek: orifice goals and variables (§5.2, §6 W6)', () => {
	it('offers the plate in an Orifice plates group with its four goals, read as Compare reads them', () => {
		const project = orificeProject();
		const own = goalElements(project).filter((e) => e.group === 'orifice');
		expect(own.map((e) => [e.elementId, e.label])).toEqual([['O1', 'Bypass orifice']]);
		expect(goalChoices(project, own[0]!)).toEqual([
			'orifice_flow',
			'orifice_pressure_loss',
			'orifice_differential_pressure',
			'orifice_pressure_drop'
		]);
		for (const q of [
			'orifice_pressure_loss',
			'orifice_differential_pressure',
			'orifice_pressure_drop'
		] as const) {
			expect(goalSpec(q), q).toEqual({ category: 'pressure', options: {} });
		}
		expect(goalValue(orificeSolved(), { quantity: 'orifice_pressure_drop', elementId: 'O1' })).toBe(
			42100
		);
		expect(
			goalValue(orificeSolved(), { quantity: 'orifice_differential_pressure', elementId: 'O1' })
		).toBeNull();
		expect(
			[
				'orifice_flow',
				'orifice_pressure_loss',
				'orifice_differential_pressure',
				'orifice_pressure_drop'
			].map((quantity) =>
				goalHint(project, { quantity: quantity as 'orifice_flow', elementId: 'O1' })
			)
		).toEqual([
			'Positive from inlet to outlet.',
			"ISO 5167-2's permanent loss, ρg × head loss.",
			"Between the plate's taps: what a flow meter reads.",
			'Static pressure, inlet minus outlet.'
		]);
	});

	it('reads the reading need through the published `needs`: a plate without taps has none', () => {
		expect(goalNeedProblem(orificeProject(), 'orifice_differential_pressure', 'O1')).toBe(
			'the orifice plate has no pressure taps, so it has no reading'
		);
		for (const taps of ['corner', 'flange', 'd_and_d_2'] as const) {
			expect(
				goalNeedProblem(orificeProject({ taps }), 'orifice_differential_pressure', 'O1'),
				taps
			).toBeNull();
		}
		// The other goals need nothing, with taps or without.
		for (const q of ['orifice_flow', 'orifice_pressure_loss', 'orifice_pressure_drop'] as const) {
			expect(goalNeedProblem(orificeProject(), q, 'O1'), q).toBeNull();
		}
	});

	it('offers the bore and the C, also on ISO 5167-2 (no entered C), with their units', () => {
		const choices = variableChoices(orificeProject()).filter((c) => c.group === 'orifice');
		expect(choices.map((c) => [c.label, c.field])).toEqual([
			['Bypass orifice · Bore diameter', 'boreDiameter'],
			['Bypass orifice · Discharge coefficient', 'dischargeCoefficient']
		]);
		expect(variableSpec(orificeProject(), { target: O1, field: 'boreDiameter' })).toEqual({
			category: 'diameter',
			options: {}
		});
		expect(variableSpec(orificeProject(), { target: O1, field: 'dischargeCoefficient' })).toEqual({
			category: 'dimensionless',
			options: {}
		});
	});

	it("defaults the bore to ISO's β range, widened to the case's bore; never reaching D", () => {
		const bounds = (project: Project, pipeDiameter?: number | null) =>
			defaultBounds(project, { target: O1, field: 'boreDiameter' }, { pipeDiameter });
		expect(bounds(orificeProject(), D4)).toEqual({ lower: 0.1 * D4, upper: 0.75 * D4 });
		// Widened to hold the case's bore, either side.
		expect(bounds(orificeProject({ boreDiameter: 0.008 }), D4)).toEqual({
			lower: 0.008,
			upper: 0.75 * D4
		});
		expect(bounds(orificeProject({ boreDiameter: 0.09 }), D4)).toEqual({
			lower: 0.1 * D4,
			upper: 0.09
		});
		// Without D: half the bore to the bore, which a valid plate keeps below D.
		for (const D of [undefined, null]) {
			expect(bounds(orificeProject(), D)).toEqual({ lower: 0.025, upper: 0.05 });
		}
		for (const bore of [0.008, 0.05, 0.09, 0.1]) {
			for (const D of [D4, null]) {
				const { lower, upper } = bounds(orificeProject({ boreDiameter: bore }), D);
				expect(lower, `${bore} ${D}`).toBeLessThan(upper);
				expect(upper, `${bore} ${D}`).toBeLessThan(D4);
			}
		}
	});

	it("defaults the C to half and twice the case's or the last solve's C at the taps, below 0.99 ÷ r̂", () => {
		const bounds = (project: Project, orifice?: ReturnType<typeof orificeResult> | null) =>
			defaultBounds(project, { target: O1, field: 'dischargeCoefficient' }, { orifice });
		// An entered C: half to twice, at most 1.
		expect(bounds(orificeProject({ dischargeCoefficient: 0.4 }))).toEqual({
			lower: 0.2,
			upper: 0.8
		});
		expect(bounds(orificeProject({ dischargeCoefficient: 0.62 }))).toEqual({
			lower: 0.31,
			upper: 1
		});
		// ISO's C: the last solve's C at the plate's taps (the C at D and D/2 without taps).
		expect(bounds(orificeProject(), orificeResult())).toEqual({ lower: 0.6047 / 2, upper: 1 });
		const meter = orificeResult({
			taps: 'flange',
			meterDischargeCoefficient: 0.6005,
			dischargeCoefficient: 0.6131
		});
		const flange = bounds(orificeProject({ taps: 'flange' }), meter);
		expect(flange).toEqual({ lower: 0.6005 / 2, upper: 0.99 / (0.6131 / 0.6005) });
		// An entered C moved from corner taps: its ratio r̂.
		const moved = orificeResult({
			taps: 'corner',
			coefficientSource: 'entered',
			meterDischargeCoefficient: 0.6,
			dischargeCoefficient: 0.6126,
			tapCoefficientRatio: 1.021
		});
		const corner = bounds(orificeProject({ taps: 'corner', dischargeCoefficient: 0.6 }), moved);
		expect(corner).toEqual({ lower: 0.3, upper: 0.99 / 1.021 });
		expect(corner.upper * 1.021).toBeLessThanOrEqual(0.99);
		// Neither a C nor a solve: 0.5 to 1.
		expect(bounds(orificeProject())).toEqual({ lower: 0.5, upper: 1 });
		for (const v of [
			newVariable(orificeProject(), { target: O1, field: 'dischargeCoefficient' }),
			newVariable(orificeProject(), { target: O1, field: 'boreDiameter' }, { pipeDiameter: D4 })
		]) {
			expect(v.lower, v.field).toBeLessThan(v.upper);
		}
	});

	it("says that a C on ISO 5167-2's starts at the middle of the bounds", () => {
		const variable = newVariable(orificeProject(), { target: O1, field: 'dischargeCoefficient' });
		expect(nowText(orificeProject(), variable, { prefs: SI_UNITS })).toBe(
			"Now ISO 5167-2's discharge coefficient, the default; the search starts at the middle of the bounds"
		);
		expect(nowText(orificeProject(), variable, { prefs: SI_UNITS, orifice: orificeResult() })).toBe(
			"Now ISO 5167-2's discharge coefficient, the default (0.6047 at the plate's taps in the last solve); the search starts at the middle of the bounds"
		);
		const entered = orificeProject({ dischargeCoefficient: 0.62 });
		expect(
			nowText(entered, newVariable(entered, { target: O1, field: 'dischargeCoefficient' }), {
				prefs: SI_UNITS
			})
		).toBe('Now 0.62');
		const bore = newVariable(
			orificeProject(),
			{ target: O1, field: 'boreDiameter' },
			{ pipeDiameter: D4 }
		);
		expect(nowText(orificeProject(), bore, { prefs: SI_UNITS })).toBe('Now 50 mm');
	});
});

describe('scenarios: the bore and the C (§5.1, §6 W6)', () => {
	const change = (componentId: string, field: string, value: unknown): Override =>
		({ kind: 'component', componentId, field, value }) as Override;

	it('names both values and writes them with their units; no C is ISO 5167-2 (default)', () => {
		const project = orificeProject();
		const plate = project.components[1];
		expect(fieldLabelFor(plate, 'boreDiameter')).toBe('Bore diameter');
		expect(fieldLabelFor(plate, 'dischargeCoefficient')).toBe('Discharge coefficient');
		const text = (field: string, value: unknown, units = SI_UNITS) =>
			changeValueText(project, change('O1', field, value), value, units);
		expect(text('boreDiameter', 0.06)).toBe('60 mm');
		expect(text('boreDiameter', 0.06, IMPERIAL_UNITS)).toBe(`${sig4(0.06 / IN)} in`);
		expect(text('dischargeCoefficient', 0.62)).toBe('0.62');
		expect(text('dischargeCoefficient', null)).toBe('ISO 5167-2 (default)');
		// The export's categories: the bore a diameter, the C a pure number.
		const record = (field: string, value: unknown) => ({
			index: 0,
			override: change('O1', field, value),
			state: 'applied' as const,
			value,
			baseValue: value,
			unit: '',
			message: ''
		});
		expect(changeCategory(project, record('boreDiameter', 0.06))).toEqual({
			category: 'diameter',
			options: {}
		});
		expect(changeCategory(project, record('dischargeCoefficient', 0.62))).toEqual({
			category: 'dimensionless',
			options: {}
		});
	});

	it('applies a bore, an entered C and a C set back to ISO 5167-2; never on another type', () => {
		const base = orificeProject({ dischargeCoefficient: 0.6, taps: 'flange' });
		const project = withScenarios(base, [
			{
				id: 'S1',
				name: 'Second plate',
				overrides: [
					change('O1', 'boreDiameter', 0.06),
					change('O1', 'dischargeCoefficient', null),
					change('R1', 'dischargeCoefficient', 0.6),
					change('O1', 'status', 'isolated')
				]
			}
		]);
		const applied = applyScenario(project, 'S1');
		expect(applied.changes.map((c) => [c.index, c.state])).toEqual([
			[0, 'applied'],
			[1, 'applied'],
			[2, 'not_applicable'],
			[3, 'not_applicable']
		]);
		const plate = applied.project.components.find((c) => c.id === 'O1');
		expect(plate).toMatchObject({ boreDiameter: 0.06, dischargeCoefficient: null, taps: 'flange' });
	});
});

describe('flags in display units (§3.5, §4.3)', () => {
	const project = orificeProject();
	const text = (f: Flag, units = SI_UNITS) => flagText(f, { project, prefs: units });
	const range = (details: Flag['details'], message = "orifice 'O1': its bore diameter …") =>
		flag({
			code: 'CORRELATION_OUT_OF_RANGE',
			severity: 'warning',
			message,
			componentId: 'O1',
			details
		});
	const OUTSIDE =
		"ISO 5167-2's discharge coefficient (Reader-Harris/Gallagher) is used outside its validated range.";

	it('tells each ISO limit with its numbers, in SI and US units', () => {
		const bore = range({ limit: 'boreDiameter', value: 0.01, lower: 0.0125 });
		expect(text(bore)).toBe(
			`Its bore diameter (10 mm) is below ISO 5167-2's smallest, 12.5 mm: ${OUTSIDE}`
		);
		expect(text(bore, IMPERIAL_UNITS)).toBe(
			`Its bore diameter (${sig4(0.01 / IN)} in) is below ISO 5167-2's smallest, ${sig4(0.0125 / IN)} in: ${OUTSIDE}`
		);
		expect(text(range({ limit: 'pipeDiameter', value: 0.0409, lower: 0.05 }))).toBe(
			`Its inlet pipe's inner diameter (40.9 mm) is below ISO 5167-2's smallest, 50 mm: ${OUTSIDE}`
		);
		expect(text(range({ limit: 'pipeDiameter', value: 1.2, upper: 1 }), IMPERIAL_UNITS)).toBe(
			`Its inlet pipe's inner diameter (${sig4(1.2 / IN)} in) is above ISO 5167-2's largest, ${sig4(1 / IN)} in: ${OUTSIDE}`
		);
		expect(text(range({ limit: 'beta', value: 0.05, lower: 0.1 }))).toBe(
			`Its diameter ratio β = d ÷ D (0.05) is below ISO 5167-2's smallest, 0.1: ${OUTSIDE}`
		);
		expect(text(range({ limit: 'beta', value: 0.8, upper: 0.75 }))).toBe(
			`Its diameter ratio β = d ÷ D (0.8) is above ISO 5167-2's largest, 0.75: ${OUTSIDE}`
		);
	});

	it('tells the outlet bore, laminar flow with an entered C and reverse flow', () => {
		expect(text(range({ limit: 'outletDiameter', value: 0.15405, inlet: D4 }))).toBe(
			"Its outlet pipe's inner diameter (154 mm) differs from its inlet pipe's (102.3 mm): ISO 5167-2's pressure-loss relation assumes the jet recovers in a pipe of the inlet's bore, about 6 D downstream, so the loss is less certain."
		);
		expect(text(range({ limit: 'laminar', value: 1500, upper: 2000 }))).toBe(
			'Its entered discharge coefficient is held at every flow, a square law for turbulent flow, but the flow in its inlet pipe is laminar (Re = 1500, below 2000): the loss is likely underestimated.'
		);
		const reverse = range({ limit: 'reverseFlow', flow: -0.0174 });
		expect(text(reverse)).toBe(
			"The flow runs from outlet to inlet (-17.4 L/s): ISO 5167-2's coefficient is for flow onto the plate's upstream face, and the loss is taken as for forward flow at the same flow rate."
		);
		expect(text(reverse, IMPERIAL_UNITS)).toContain(`(${sig4(-0.0174 / GPM)} gpm)`);
	});

	it("keeps the API's words for the Reynolds number, and without details", () => {
		const message =
			"orifice 'O1': Re = 1018 in its inlet pipe is below ISO 5167-2's lowest Reynolds number at D and D/2 tappings (5000), so the discharge coefficient that sets the loss is held at its value there (not extrapolated)";
		expect(text(range({ limit: 'reynoldsNumber', value: 1017.76, lower: 5000 }, message))).toBe(
			"Re = 1018 in its inlet pipe is below ISO 5167-2's lowest Reynolds number at D and D/2 tappings (5000), so the discharge coefficient that sets the loss is held at its value there (not extrapolated)"
		);
		// Without details, the server's words with names and SI units shown by their symbol (a
		// length far from the word "diameter" is a length).
		const bare = range(
			{},
			"orifice 'O1': its bore diameter 0.01 m is below ISO 5167-2's smallest, 0.0125 m"
		);
		expect(text(bare)).toBe("Its bore diameter 10 mm is below ISO 5167-2's smallest, 0.0125 m");
	});

	it('tells flashing at the vena contracta, absolute, with or without a vapor pressure', () => {
		const flashing = (vaporPressure: number | string) =>
			flag({
				code: 'BELOW_VAPOR_PRESSURE',
				severity: 'invalid',
				message: "orifice 'O1': the absolute pressure at its vena contracta …",
				componentId: 'O1',
				details: { venaContractaAbsolutePressure: -26861.4, vaporPressure }
			});
		const end =
			': the liquid would flash there, and a flashing jet chokes the flow, so the flow solved is too high.';
		expect(text(flashing(2339.3))).toBe(
			`The absolute pressure at its vena contracta is -26.86 kPa(a), below the vapor pressure (2.339 kPa(a))${end}`
		);
		expect(text(flashing(2339.3), IMPERIAL_UNITS)).toBe(
			`The absolute pressure at its vena contracta is ${sig4(-26861.4 / PSI)} psia, below the vapor pressure (${sig4(2339.3 / PSI)} psia)${end}`
		);
		expect(text(flashing('not given'))).toBe(
			`The absolute pressure at its vena contracta is -26.86 kPa(a), below 0 kPa(a), below any liquid's vapor pressure (this fluid has none given)${end}`
		);
	});
});

describe('a plate the solver cannot represent (ORIFICE_OUT_OF_RANGE, §4.3)', () => {
	const issue = (message: string): TopologyIssue => ({
		code: 'ORIFICE_OUT_OF_RANGE',
		message,
		componentIds: ['O1'],
		connectionIds: []
	});
	const head = (bore: string, beta: string) =>
		`orifice 'O1': a bore diameter of ${bore} m in an inlet pipe of inner diameter 0.10226 m (β = d/D = ${beta})`;
	const view = (message: string, units = SI_UNITS) =>
		topologyIssueViews([issue(message)], orificeProject(), true, units)[0]!;

	it("tells a bore not smaller than the pipe's with the names and both bores in display units", () => {
		const message = `${head('0.11', '1.07569')}: the bore is not smaller than the pipe; an orifice plate needs β < 1, so the solver cannot represent this plate`;
		expect(view(message)).toEqual({
			text: "Bypass orifice's bore (110 mm) is not smaller than its inlet pipe's inner diameter (102.3 mm): an orifice plate needs β = d ÷ D below 1. Use a smaller bore.",
			links: [{ componentId: 'O1' }],
			detail: message
		});
		expect(view(message, IMPERIAL_UNITS).text).toBe(
			`Bypass orifice's bore (${sig4(0.11 / IN)} in) is not smaller than its inlet pipe's inner diameter (${sig4(D4 / IN)} in): an orifice plate needs β = d ÷ D below 1. Use a smaller bore.`
		);
	});

	it("tells ISO's C that could exceed 1, and a moved entered C, quoting the server's numbers", () => {
		const iso = `${head('0.0995', '0.97301')}: ISO 5167-2's discharge coefficient (Reader-Harris/Gallagher) at D and D/2 tappings can reach 1.05827 at some flow, above 1, which would make the jet larger than the bore and the loss smaller than the sudden expansion from the bore (Borda-Carnot), physically impossible; use a smaller bore, or enter a discharge coefficient`;
		expect(view(iso).text).toBe(
			"Bypass orifice's bore (99.5 mm) is so close to its inlet pipe's inner diameter (102.3 mm, β = 0.97301) that ISO 5167-2's discharge coefficient at D and D/2 tappings could exceed 1 (up to 1.05827): a jet larger than the bore, which is physically impossible. Use a smaller bore, or enter a discharge coefficient."
		);
		const moved = `${head('0.0767', '0.750049')}: its entered discharge coefficient 0.99 at its corner tappings, moved to D and D/2 tappings by ISO 5167-2's ratio of the two tap sets' coefficients (up to 1.02191 at this plate), can reach 1.01169 at some flow, above 1, which would make the jet larger than the bore, physically impossible; check the entered coefficient (ISO 5167-2's C at the plate's taps, not the flow coefficient C/√(1 - β⁴))`;
		expect(view(moved).text).toBe(
			"Bypass orifice: its entered discharge coefficient 0.99 at its corner tappings, moved to D and D/2 tappings by ISO 5167-2's ratio of the two tap sets' coefficients (up to 1.02191 at a bore of 76.7 mm in an inlet pipe of 102.3 mm), could reach 1.01169, above 1: a jet larger than the bore, which is physically impossible. Check the entered coefficient: ISO 5167-2's C at the plate's taps, not the flow coefficient C ÷ √(1 − β⁴)."
		);
	});

	it("tells a loss coefficient that is not a finite double; another form keeps the server's words", () => {
		const loss = `${head('1e-05', '9.77899e-05')}: with a discharge coefficient down to 1e-08 it gives a loss coefficient, K/(2 g A²), that is not a finite positive floating-point number; the solver cannot represent this plate`;
		expect(view(loss).text).toBe(
			'Bypass orifice: a bore of 0.01 mm in an inlet pipe of inner diameter 102.3 mm (β = 9.77899e-5) gives a loss coefficient, with a discharge coefficient down to 1e-8, that is not a finite positive floating-point number, so the solver cannot represent this plate. Check its bore and discharge coefficient.'
		);
		const other = `${head('0.05', '0.48895')}: something else`;
		expect(view(other)).toEqual({ text: other, links: [{ componentId: 'O1' }] });
		// A message naming another plate keeps the server's words.
		const elsewhere = issue(
			"orifice 'O2': a bore diameter of 0.11 m in an inlet pipe of inner diameter 0.10226 m (β = d/D = 1.07569): the bore is not smaller than the pipe; an orifice plate needs β < 1, so the solver cannot represent this plate"
		);
		expect(topologyIssueViews([elsewhere], orificeProject(), true)[0]!.text).toBe(
			elsewhere.message
		);
	});
});
