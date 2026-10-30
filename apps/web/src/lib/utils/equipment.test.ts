/**
 * The equipment element in the web's utilities (proposal equipment-pressure-drop.md §5.3, §6, §7.6):
 * the rating union read from the schema, the scenario mirror's whole/part rule for the rating, its
 * words, the results table and strip, Compare's rows, goal seek's groups, bounds and notices, the
 * topology issue, schema problems and links. Ratings, flows and solved states are made-up test
 * inputs (testing/helpers.ts equipmentProject, testing/results.ts equipmentSolved); expected
 * display values are computed here from the unit definitions (NIST SP 811), not from units.ts.
 */
import { describe, expect, it } from 'vitest';
import type {
	EquipmentRating,
	GoalSeekResponse,
	Override,
	Project,
	TopologyIssue,
	VariableResult
} from '../api/types';
import openapi from '../api/openapi.json';
import { deepFreeze, equipmentProject } from '../testing/helpers';
import { equipmentSolved, goalSeekResponse } from '../testing/results';
import { pumpTransferExample } from './examples';
import { compareCells, defaultRows, ELEMENT_QUANTITIES, QUANTITIES, rowLabel } from './compare';
import { decodeProject, encodeProject } from './encoding';
import { RATING_KINDS } from './factory';
import {
	defaultBounds,
	foundValueTexts,
	goalChoices,
	goalElements,
	goalHint,
	goalSpec,
	goalValue,
	keptByScenarios,
	newVariable,
	variableChoices,
	variableLabel,
	variableSpec,
	variableView,
	withCaseKind,
	applyToCase,
	type WordsContext
} from './goal-seek';
import { topologyIssueViews } from './issue-text';
import {
	GOAL_QUANTITY_RULES,
	GOAL_VARIABLE_FIELDS,
	holdsSchema,
	OVERRIDE_FIELDS,
	ratingKinds,
	ratingSchemaName
} from './model-rules';
import {
	availableViews,
	elementSummary,
	equipmentTable,
	rowsForElement,
	valueText,
	type Cell
} from './results';
import {
	applyScenario,
	carryChanges,
	caseProject,
	changeStates,
	changeValueText,
	fieldLabelFor,
	overlappingChanges,
	scenarioEdit,
	trackPipes,
	valueOf,
	withScenarios
} from './scenarios';
import { IMPERIAL_UNITS, SI_UNITS } from './units';
import { schemaProblems } from './validate';

// Definitions (exact): 1 in = 0.0254 m, 1 ft = 0.3048 m, 1 lb = 0.45359237 kg, g_n = 9.80665 m/s²,
// US gallon = 231 in³.
const IN = 0.0254;
const LB = 0.45359237;
const PSI = (LB * 9.80665) / (IN * IN); // Pa
const GPM = (231 * IN ** 3) / 60; // m³/s
const sig4 = (v: number) => String(Number(v.toPrecision(4)));

const E1 = { kind: 'component', componentId: 'E1' } as const;
const POINT = { kind: 'point', pressureLoss: 25000, flow: 0.01, density: 999.1 } as const;

/** equipmentProject with scenario S1 "Dirty strainer" holding `overrides`, frozen. */
function withScenario(overrides: Override[] = [], rating: EquipmentRating = POINT): Project {
	return deepFreeze(
		withScenarios(equipmentProject(rating), [{ id: 'S1', name: 'Dirty strainer', overrides }])
	);
}

/** Edit E1's rating in case S1 (as the form does) and return the scenario's changes. */
function editRating(project: Project, rating: EquipmentRating): Override[] {
	const edit = scenarioEdit(project, 'S1', (draft) => {
		const item = draft.components.find((c) => c.id === 'E1');
		if (item?.type === 'equipment') item.rating = rating;
	});
	if (!edit.ok) throw new Error(edit.message);
	const next = structuredClone(project);
	edit.apply(next);
	return next.scenarios![0]!.overrides ?? [];
}

const change = (field: string, value: unknown): Override =>
	({ kind: 'component', componentId: 'E1', field, value }) as Override;

describe('the rating union, read from the schema (§2.3, §6.4)', () => {
	it('names the member of each kind; K is not a kind', () => {
		expect(ratingSchemaName('point')).toBe('RatedPoint');
		expect(ratingSchemaName('Cv')).toBe('RatedFlowCoefficient');
		expect(ratingSchemaName('Kv')).toBe('RatedFlowCoefficient');
		expect(ratingSchemaName('K')).toBeNull();
		expect(ratingSchemaName('builtin')).toBeNull();
		// The form's Rated by choice offers the union's kinds, in its order.
		expect(ratingKinds()).toEqual(['point', 'Cv', 'Kv']);
		expect([...RATING_KINDS]).toEqual(ratingKinds());
		const members = openapi.components.schemas.Equipment.properties.rating.oneOf.map((m) =>
			m.$ref.split('/').pop()
		);
		expect(members).toEqual(['RatedPoint', 'RatedFlowCoefficient']);
	});

	it("tells a holder of a rating member by its kind, as the API's holder test does", () => {
		expect(holdsSchema(POINT, 'RatedPoint')).toBe(true);
		expect(holdsSchema(POINT, 'RatedFlowCoefficient')).toBe(false);
		expect(holdsSchema({ kind: 'Kv', value: 60 }, 'RatedFlowCoefficient')).toBe(true);
		expect(holdsSchema({ kind: 'Kv', value: 60 }, 'RatedPoint')).toBe(false);
		expect(holdsSchema(undefined, 'RatedPoint')).toBe(false);
		// The fluid's union as before; any other holder need only exist.
		expect(holdsSchema({ kind: 'builtin' }, 'BuiltinFluid')).toBe(true);
		expect(holdsSchema({ kind: 'custom' }, 'BuiltinFluid')).toBe(false);
		expect(holdsSchema({ mode: 'flow' }, 'PumpControl')).toBe(true);
	});

	it('publishes the five allow-list entries, the four variables and the three goals', () => {
		expect(OVERRIDE_FIELDS.Equipment).toEqual({
			rating: { schema: 'Equipment', path: ['rating'], keys: [] },
			'rating.density': { schema: 'RatedPoint', path: ['rating', 'density'], keys: [] },
			'rating.flow': { schema: 'RatedPoint', path: ['rating', 'flow'], keys: [] },
			'rating.pressureLoss': { schema: 'RatedPoint', path: ['rating', 'pressureLoss'], keys: [] },
			'rating.value': { schema: 'RatedFlowCoefficient', path: ['rating', 'value'], keys: [] }
		});
		const scales = Object.fromEntries(
			Object.entries(GOAL_VARIABLE_FIELDS.Equipment ?? {}).map(([f, e]) => [f, e.scale])
		);
		expect(scales).toEqual({
			'rating.pressureLoss': 'log',
			'rating.flow': 'log',
			'rating.density': 'linear',
			'rating.value': 'log'
		});
		for (const q of ['equipment_flow', 'equipment_pressure_loss', 'equipment_pressure_drop']) {
			expect(GOAL_QUANTITY_RULES[q]?.targets, q).toEqual(['Equipment']);
		}
		expect(GOAL_QUANTITY_RULES.equipment_flow?.unit).toBe('m³/s');
		expect(GOAL_QUANTITY_RULES.equipment_pressure_loss?.unit).toBe('Pa (difference)');
	});
});

describe('scenarios: the rating and its values (§6.4)', () => {
	it("a value of the item's kind applies; one of the other kind does not, and says why", () => {
		const point = withScenario();
		expect(valueOf(point, E1, 'rating')).toEqual(POINT);
		expect(valueOf(point, E1, 'rating.pressureLoss')).toBe(25000);
		expect(valueOf(point, E1, 'rating.value')).toBeUndefined();
		const cv = withScenario([], { kind: 'Cv', value: 90 });
		expect(valueOf(cv, E1, 'rating.value')).toBe(90);
		expect(valueOf(cv, E1, 'rating.flow')).toBeUndefined();
		const lapsed = withScenario([change('rating.value', 80), change('rating.flow', 0.012)]);
		expect(changeStates(lapsed, 'S1').map((c) => [c.override.field, c.state])).toEqual([
			['rating.value', 'not_applicable'],
			['rating.flow', 'applied']
		]);
		expect(changeStates(lapsed, 'S1')[0]!.message).toBe(
			'Strainer is rated by a pressure drop at a flow (its flow coefficient applies to a rating by a Cv or Kv)'
		);
		expect(applyScenario(lapsed, 'S1').project.components[1]).toMatchObject({
			rating: { ...POINT, flow: 0.012 }
		});
		const onCv = withScenario([change('rating.pressureLoss', 70000)], { kind: 'Cv', value: 90 });
		expect(changeStates(onCv, 'S1')[0]!.message).toBe(
			'Strainer is rated by a Cv (its rated pressure drop applies to a rating by a pressure drop at a flow)'
		);
	});

	it('an edit of the rated pressure drop is one change of it (never the whole rating too)', () => {
		const project = withScenario();
		const dirty = editRating(project, { ...POINT, pressureLoss: 70000 });
		expect(dirty).toEqual([change('rating.pressureLoss', 70000)]);
		expect(overlappingChanges(dirty)).toEqual([]);
		// A second value of the same kind is its own change; typing the base back removes it.
		const both = editRating(withScenario(dirty), { ...POINT, pressureLoss: 70000, flow: 0.012 });
		expect(both).toEqual([change('rating.pressureLoss', 70000), change('rating.flow', 0.012)]);
		const back = editRating(withScenario(both), { ...POINT, flow: 0.012 });
		expect(back).toEqual([change('rating.flow', 0.012)]);
		expect(editRating(withScenario(back), POINT)).toEqual([]);
	});

	it('a change of kind is one whole-rating change, in the place of the first value change', () => {
		const project = withScenario([
			{ kind: 'component', componentId: 'R1', field: 'liquidLevel', value: 4 },
			change('rating.pressureLoss', 70000),
			change('rating.density', 1043.47)
		]);
		const vendorB = editRating(project, { kind: 'Cv', value: 80 });
		expect(vendorB).toEqual([
			{ kind: 'component', componentId: 'R1', field: 'liquidLevel', value: 4 },
			change('rating', { kind: 'Cv', value: 80 })
		]);
		expect(overlappingChanges(vendorB)).toEqual([]);
		// While it exists, later edits update it, even back to a point of the base's kind.
		const lower = editRating(withScenario(vendorB), { kind: 'Cv', value: 70 });
		expect(lower[1]).toEqual(change('rating', { kind: 'Cv', value: 70 }));
		const point = editRating(withScenario(lower), { ...POINT, pressureLoss: 40000 });
		expect(point[1]).toEqual(change('rating', { ...POINT, pressureLoss: 40000 }));
		expect(point).toHaveLength(2);
		// Equal to the base's rating again: no rating change is left.
		expect(editRating(withScenario(point), POINT)).toEqual([
			{ kind: 'component', componentId: 'R1', field: 'liquidLevel', value: 4 }
		]);
	});

	it('on a Cv-rated item, Cv 90 → 80 is one change of rating.value; Cv → Kv is the whole', () => {
		const cv = { kind: 'Cv', value: 90 } as const;
		const project = withScenario([], cv);
		expect(editRating(project, { kind: 'Cv', value: 80 })).toEqual([change('rating.value', 80)]);
		expect(editRating(project, { kind: 'Kv', value: 60 })).toEqual([
			change('rating', { kind: 'Kv', value: 60 })
		]);
		expect(
			caseProject(withScenario([change('rating.value', 80)], cv), 'S1').components[1]
		).toMatchObject({ rating: { kind: 'Cv', value: 80 } });
	});

	it('names each value and writes it with its unit; a whole rating as the datasheet gives it', () => {
		const project = withScenario();
		const item = project.components[1];
		expect(fieldLabelFor(item, 'rating')).toBe('Rating');
		expect(fieldLabelFor(item, 'rating.pressureLoss')).toBe('Rated pressure drop');
		expect(fieldLabelFor(item, 'rating.flow')).toBe('Rated flow');
		expect(fieldLabelFor(item, 'rating.density')).toBe('Rated fluid density');
		expect(fieldLabelFor(item, 'rating.value')).toBe('Flow coefficient');
		const cv = withScenario([], { kind: 'Cv', value: 90 });
		expect(fieldLabelFor(cv.components[1], 'rating.value')).toBe('Cv');
		const text = (p: Project, field: string, value: unknown, units = SI_UNITS) =>
			changeValueText(p, change(field, value), value, units);
		// A pressure difference: kPa, never kPa(g).
		expect(text(project, 'rating.pressureLoss', 70000)).toBe('70 kPa');
		expect(text(project, 'rating.flow', 0.015)).toBe('15 L/s');
		expect(text(project, 'rating.density', 999.1)).toBe('999.1 kg/m³');
		expect(text(project, 'rating', POINT)).toBe('25 kPa at 10 L/s, 999.1 kg/m³');
		expect(text(project, 'rating', { kind: 'Cv', value: 120 })).toBe('Cv 120');
		expect(text(cv, 'rating.value', 80)).toBe('Cv 80');
		expect(text(project, 'rating.pressureLoss', 70000, IMPERIAL_UNITS)).toBe(
			`${sig4(70000 / PSI)} psi`
		);
	});

	it('a base edit from a Cv to a Kv removes the Cv changes, which a Kv would misread', () => {
		const before = withScenario([change('rating.value', 80)], { kind: 'Cv', value: 90 });
		const next = structuredClone(before);
		const item = next.components[1];
		if (item?.type === 'equipment') item.rating = { kind: 'Kv', value: 60 };
		const carried = carryChanges(before, trackPipes(before, structuredClone(before)), next);
		expect(carried.project.scenarios![0]!.overrides).toEqual([]);
		expect(carried.notes).toEqual([
			'The Cv changes of Strainer in Dirty strainer were removed: it is rated by a Kv now, and a Cv is not a Kv.'
		]);
		// From a rated point to a Cv, the point's changes are kept and no longer apply.
		const point = withScenario([change('rating.pressureLoss', 70000)]);
		const cv = structuredClone(point);
		const strainer = cv.components[1];
		if (strainer?.type === 'equipment') strainer.rating = { kind: 'Cv', value: 90 };
		const kept = carryChanges(point, trackPipes(point, structuredClone(point)), cv);
		expect(kept.project.scenarios![0]!.overrides).toEqual([change('rating.pressureLoss', 70000)]);
		expect(kept.notes).toEqual([
			'The rating value changes of Strainer in Dirty strainer no longer apply: it is rated by a Cv now. They apply again if it is rated by a pressure drop at a flow.'
		]);
	});

	it('a base edit that changes the kind leaves the value changes kept, not applying', () => {
		const project = withScenario([change('rating.pressureLoss', 70000)]);
		const next = structuredClone(project);
		const item = next.components[1];
		if (item?.type === 'equipment') item.rating = { kind: 'Kv', value: 60 };
		expect(changeStates(next, 'S1')).toMatchObject([{ state: 'not_applicable' }]);
		expect(next.scenarios![0]!.overrides).toEqual([change('rating.pressureLoss', 70000)]);
	});
});

describe('results: the Equipment view, table and strip (§6.3)', () => {
	const project = equipmentProject();

	it('shows the view only when the solve has equipment, after Valves', () => {
		expect(availableViews(equipmentSolved())).toEqual([
			'summary',
			'nodes',
			'links',
			'equipment',
			'boundaries',
			'methods'
		]);
		expect(availableViews(equipmentSolved({}, { equipmentResults: {} }))).not.toContain(
			'equipment'
		);
	});

	it('gives flow, flow ÷ rated flow, pressure loss, head loss and static drop in display units', () => {
		const table = equipmentTable(project, equipmentSolved(), SI_UNITS);
		expect(table.columns.map((c) => [c.label, c.unit])).toEqual([
			['Flow (+ inlet → outlet)', 'L/s'],
			['Flow ÷ rated flow', '%'],
			['Pressure loss', 'kPa'],
			['Head loss', 'm'],
			['Pressure drop (static)', 'kPa']
		]);
		const [row] = table.rows;
		expect(row!.name).toBe('Strainer');
		expect(row!.detail).toBe('Equipment (rated pressure drop) · E1');
		expect(row!.cells).toEqual({
			flow: '12',
			flowRatio: '120',
			pressureLoss: '36',
			headLoss: '3.675',
			pressureDrop: '36.5'
		});
		const us = equipmentTable(project, equipmentSolved(), IMPERIAL_UNITS).rows[0]!.cells;
		expect(us.flow).toBe(sig4(0.012 / GPM));
		expect(us.pressureLoss).toBe(sig4(36000 / PSI));
	});

	it('shows "—" for the flow ratio of a Cv or Kv rating, and ≈ 0 below the head resolution', () => {
		const cv = equipmentSolved({ flowRatio: null, rating: { kind: 'Cv', value: 80 } });
		expect(equipmentTable(project, cv, SI_UNITS).rows[0]!.cells.flowRatio).toBe('—');
		// ρg × 10⁻⁷ m at 998 kg/m³ is about 9.8×10⁻⁴ Pa.
		const still = equipmentSolved({ pressureLoss: 5e-4, headLoss: 5e-8, pressureDrop: 2e-4 });
		const cells = equipmentTable(project, still, SI_UNITS).rows[0]!.cells;
		for (const key of ['pressureLoss', 'headLoss', 'pressureDrop']) {
			expect(valueText(cells[key] as Cell as string), key).toBe('≈ 0');
		}
	});

	it('gives the trace its rows and the strip flow, flow ratio and pressure loss', () => {
		const element = { kind: 'component', id: 'E1' } as const;
		const groups = rowsForElement(project, equipmentSolved(), SI_UNITS, element);
		expect(groups.map((g) => g.title)).toEqual(['Equipment', 'Ports']);
		const summary = elementSummary(project, equipmentSolved(), SI_UNITS, element);
		expect(summary?.items.map((i) => [i.label, i.cell, i.unit])).toEqual([
			['Flow (+ inlet → outlet)', '12', 'L/s'],
			['Flow ÷ rated flow', '120', '%'],
			['Pressure loss', '36', 'kPa']
		]);
		// A Cv or Kv has no rated flow: the strip leaves its "—" out.
		const cv = equipmentSolved({ flowRatio: null, rating: { kind: 'Cv', value: 80 } });
		expect(elementSummary(project, cv, SI_UNITS, element)?.items.map((i) => i.key)).toEqual([
			'flow',
			'pressureLoss'
		]);
	});
});

describe('Compare: the equipment rows (§5.3)', () => {
	const base = equipmentSolved();
	const dirty = equipmentSolved({ flow: 0.0105, pressureLoss: 48000, pressureDrop: 48400 });
	const columns = [base, dirty].map((solved) => ({ solved, converged: true }));
	const project = withScenario([change('rating.pressureLoss', 70000)]);

	it('reads flow, pressure loss and static drop; relative only for flow and loss', () => {
		expect(ELEMENT_QUANTITIES.equipment).toEqual([
			'equipmentFlow',
			'equipmentPressureLoss',
			'equipmentPressureDrop'
		]);
		expect(
			QUANTITIES.equipmentPressureLoss.value(base, {
				quantity: 'equipmentPressureLoss',
				elementId: 'E1'
			})
		).toBe(36000);
		const cells = (quantity: 'equipmentFlow' | 'equipmentPressureLoss' | 'equipmentPressureDrop') =>
			compareCells({ quantity, elementId: 'E1' }, columns, project, SI_UNITS);
		expect(cells('equipmentFlow')[1]!.diff!.text).toBe('−1.5 (−12.5 %)');
		expect(cells('equipmentPressureLoss')[1]!.diff!.text).toBe('+12 (+33.3 %)');
		// The static drop holds the ports' elevation and velocity terms: no true zero.
		expect(cells('equipmentPressureDrop')[1]!.diff!.text).toBe('+11.9');
		expect(rowLabel(project, { quantity: 'equipmentPressureLoss', elementId: 'E1' })).toBe(
			'Strainer · Pressure loss'
		);
	});

	it("adds an item's flow and pressure loss to the default rows when a scenario changes it", () => {
		const rows = defaultRows(project, [base, dirty]);
		expect(rows).toContainEqual({ quantity: 'equipmentFlow', elementId: 'E1' });
		expect(rows).toContainEqual({ quantity: 'equipmentPressureLoss', elementId: 'E1' });
		expect(defaultRows(withScenario(), [base, null])).not.toContainEqual({
			quantity: 'equipmentFlow',
			elementId: 'E1'
		});
	});
});

describe('goal seek: equipment goals and variables (§5.2, §6.4)', () => {
	it('offers the item in an Equipment group with its three goals, read as Compare reads them', () => {
		const project = equipmentProject();
		const own = goalElements(project).filter((e) => e.group === 'equipment');
		expect(own.map((e) => e.elementId)).toEqual(['E1']);
		expect(goalChoices(project, own[0]!)).toEqual([
			'equipment_flow',
			'equipment_pressure_loss',
			'equipment_pressure_drop'
		]);
		expect(goalSpec('equipment_pressure_loss')).toEqual({ category: 'pressure', options: {} });
		expect(goalSpec('equipment_pressure_drop')).toEqual({ category: 'pressure', options: {} });
		expect(
			goalValue(equipmentSolved(), { quantity: 'equipment_pressure_drop', elementId: 'E1' })
		).toBe(36500);
		expect(goalHint(project, { quantity: 'equipment_flow', elementId: 'E1' })).toBe(
			'Positive from inlet to outlet.'
		);
		expect(goalHint(project, { quantity: 'equipment_pressure_loss', elementId: 'E1' })).toBe(
			'The rating scaled to the flow and density (ρg × head loss).'
		);
	});

	it("offers only the values the item's kind of rating holds", () => {
		const point = variableChoices(equipmentProject()).filter((c) => c.group === 'equipment');
		expect(point.map((c) => c.label)).toEqual([
			'Strainer · Rated pressure drop',
			'Strainer · Rated flow',
			'Strainer · Rated fluid density'
		]);
		const kv = variableChoices(equipmentProject({ kind: 'Kv', value: 60 })).filter(
			(c) => c.group === 'equipment'
		);
		expect(kv.map((c) => [c.label, c.field])).toEqual([['Strainer · Kv', 'rating.value']]);
	});

	it('defaults to a factor of 10 either way (2 for the density), lower below upper, in bounds', () => {
		const project = equipmentProject();
		const bounds = (field: string, p = project) => defaultBounds(p, { target: E1, field });
		expect(bounds('rating.pressureLoss')).toEqual({ lower: 2500, upper: 250000 });
		expect(bounds('rating.flow')).toEqual({ lower: 0.001, upper: 0.1 });
		expect(bounds('rating.density')).toEqual({ lower: 499.55, upper: 1998.2 });
		expect(bounds('rating.value', equipmentProject({ kind: 'Cv', value: 90 }))).toEqual({
			lower: 9,
			upper: 900
		});
		// Clipped to the field's own bounds (a rated flow is at most 100 m³/s).
		const big = equipmentProject({ ...POINT, flow: 50 });
		expect(bounds('rating.flow', big)).toEqual({ lower: 5, upper: 100 });
		for (const field of ['rating.pressureLoss', 'rating.flow', 'rating.density']) {
			const v = newVariable(project, { target: E1, field });
			expect(v.lower, field).toBeLessThan(v.upper);
		}
	});

	it('shows the rated drop as a difference and a Cv or Kv with its kind', () => {
		expect(variableSpec(equipmentProject(), { target: E1, field: 'rating.pressureLoss' })).toEqual({
			category: 'pressure',
			options: {}
		});
		expect(
			variableSpec(equipmentProject({ kind: 'Cv', value: 90 }), {
				target: E1,
				field: 'rating.value'
			})
		).toEqual({ category: 'dimensionless', options: {}, prefix: 'Cv ' });
	});

	/** A scenario run whose case S1 rates E1 by a whole rating; two of its values were varied. */
	function twoParts(): { response: GoalSeekResponse; context: WordsContext } {
		const found = {
			kind: 'point',
			pressureLoss: 64383.9587021,
			flow: 0.0132186597,
			density: 999.1
		};
		const sent = withScenario([change('rating', { ...POINT, pressureLoss: 40000 })]);
		const whole = change('rating', found);
		const variable = (field: string, value: number, index: number): VariableResult => ({
			index,
			variable: { kind: 'component', componentId: 'E1', field: field as never, lower: 1, upper: 2 },
			label: `${field} of equipment E1`,
			unit: '',
			scale: 'log',
			start: 1,
			startSource: 'case',
			caseValue: 1,
			baseValue: 1,
			value,
			atBound: null,
			override: whole as VariableResult['override'],
			replacedOverride: 0
		});
		const response = goalSeekResponse({
			variables: [
				variable('rating.pressureLoss', found.pressureLoss, 0),
				variable('rating.flow', found.flow, 1)
			]
		});
		return {
			response,
			context: {
				labels: sent,
				sent,
				prefs: SI_UNITS,
				caseWords: 'scenario Dirty strainer',
				caseId: 'S1'
			}
		};
	}

	it('names each value found by its variable, never by its whole-rating override', () => {
		const { response, context } = twoParts();
		expect(foundValueTexts(response, context)).toEqual([
			'Strainer rated pressure drop 64.384 kPa',
			'Strainer rated flow 13.2187 L/s'
		]);
		// Values of other fields read as before: a pump's speed, and a fluid temperature whose
		// override (in a scenario run with a whole fluid change) is the whole fluid.
		const transfer = pumpTransferExample();
		const plain = { ...context, labels: transfer, sent: transfer, caseId: null };
		expect(foundValueTexts(goalSeekResponse(), plain)).toEqual(['Transfer pump speed 86.1174 %']);
		const temperature = goalSeekResponse({
			variables: [
				{
					...goalSeekResponse().result.variables[0]!,
					variable: { kind: 'project', field: 'fluid.temperature', lower: 278.15, upper: 313.15 },
					value: 285.5,
					override: {
						kind: 'project',
						field: 'fluid',
						value: { kind: 'builtin', fluidId: 'water', temperature: 285.5 }
					}
				}
			]
		});
		expect(foundValueTexts(temperature, plain)).toEqual(['fluid temperature 12.35 °C']);
	});

	it('names a Cv or Kv found by its kind once: "Strainer Cv 81.0724", never "Cv Cv"', () => {
		// §7.3's Cv* (a made-up rating's inverse); the number is only formatted here.
		const found = 81.0723929388;
		for (const kind of ['Cv', 'Kv'] as const) {
			const project = deepFreeze(equipmentProject({ kind, value: 90 }));
			const response = goalSeekResponse({
				variables: [
					{
						...goalSeekResponse().result.variables[0]!,
						variable: {
							kind: 'component',
							componentId: 'E1',
							field: 'rating.value',
							lower: 9,
							upper: 900
						},
						label: `${kind} of equipment E1`,
						scale: 'log',
						caseValue: 90,
						baseValue: 90,
						value: found,
						override: change('rating.value', found) as VariableResult['override']
					}
				]
			});
			const context = { labels: project, sent: project, prefs: SI_UNITS, caseId: null };
			expect(foundValueTexts(response, context), kind).toEqual([`Strainer ${kind} 81.0724`]);
			// The kind is named once in imperial units too (a coefficient is as entered).
			expect(foundValueTexts(response, { ...context, prefs: IMPERIAL_UNITS }), kind).toEqual([
				`Strainer ${kind} 81.0724`
			]);
		}
	});

	it('applies the equal whole-rating overrides of two values as one change', () => {
		const { response, context } = twoParts();
		const overrides = response.result.variables.map((v) => v.override as Override);
		const applied = applyToCase(context.sent, 'S1', overrides);
		expect(applied.scenarios![0]!.overrides).toEqual([overrides[0]]);
	});

	it('names a Cv or Kv by its kind in the case run (a scenario may rate the item otherwise)', () => {
		const sent = withScenario([change('rating', { kind: 'Kv', value: 60 })], {
			kind: 'Cv',
			value: 90
		});
		const context: WordsContext = {
			labels: sent,
			sent,
			prefs: SI_UNITS,
			caseWords: 'scenario Dirty strainer',
			caseId: 'S1'
		};
		const view = variableView(context, {
			kind: 'component',
			componentId: 'E1',
			field: 'rating.value',
			lower: 6,
			upper: 600
		});
		expect(view.label).toBe('Strainer · Kv');
		expect(view.text(84.1004736136)).toBe('Kv 84.1005');
		expect(view.unit).toBe('Kv');
	});

	it("names a setup's Cv or Kv by the case shown, whatever the names project says", () => {
		const base = withScenario([change('rating', { kind: 'Kv', value: 60 })], {
			kind: 'Cv',
			value: 90
		});
		const variable = { target: E1, field: 'rating.value' };
		expect(variableLabel(base, variable)).toBe('Strainer · Cv');
		expect(variableLabel(base, withCaseKind(caseProject(base, 'S1'), variable))).toBe(
			'Strainer · Kv'
		);
		// Other fields are left as they are.
		const other = { target: E1, field: 'rating.flow' };
		expect(withCaseKind(caseProject(base, 'S1'), other)).toBe(other);
	});

	it('says a scenario with a whole-rating change keeps its own rated pressure drop', () => {
		const project = withScenario([change('rating', { kind: 'Cv', value: 80 })]);
		expect(keptByScenarios(project, [change('rating.pressureLoss', 30000)])).toEqual([
			{ label: 'Strainer rated pressure drop', scenarios: ['Dirty strainer'] }
		]);
		// A scenario of another value of the item keeps nothing of this one.
		const other = withScenario([change('rating.flow', 0.012)]);
		expect(keptByScenarios(other, [change('rating.pressureLoss', 30000)])).toEqual([]);
	});
});

describe('a rating the solver cannot represent (EQUIPMENT_RATING_OUT_OF_RANGE)', () => {
	const issue = (message: string): TopologyIssue => ({
		code: 'EQUIPMENT_RATING_OUT_OF_RANGE',
		message,
		componentIds: ['E1'],
		connectionIds: []
	});

	it("is told with the item's name and its rating in display units, the server's words kept", () => {
		const point = issue(
			"equipment 'E1': a rating of 50000 Pa at 1e-300 m³/s for a fluid of 1e-300 kg/m³ gives a loss coefficient, c = ΔP_r/(ρ_r g Q_r²), that is not a finite positive floating-point number; the solver cannot represent this element"
		);
		const [view] = topologyIssueViews([point], equipmentProject(), true, SI_UNITS);
		expect(view).toEqual({
			text: 'Strainer: a rated pressure drop of 50 kPa at 1e-297 L/s for a fluid of 1e-300 kg/m³ gives a loss coefficient that is not a finite positive floating-point number, so the solver cannot represent this element. Check its rating.',
			links: [{ componentId: 'E1' }],
			detail: point.message
		});
		const cv = issue(
			"equipment 'E1': a rating of Cv 1e-170 gives a loss coefficient, c = K/(2 g A²) with K from the Cv (fluids.fittings.Cv_to_K), that is not a finite positive floating-point number; the solver cannot represent this element"
		);
		expect(topologyIssueViews([cv], equipmentProject(), true)[0]!.text).toBe(
			'Strainer: a Cv of 1e-170 gives a loss coefficient that is not a finite positive floating-point number, so the solver cannot represent this element. Check its rating.'
		);
		// Another form keeps the server's message.
		const other = issue("equipment 'E1': something else");
		expect(topologyIssueViews([other], equipmentProject(), true)[0]!.text).toBe(other.message);
	});
});

describe('a rating in links and schema checks', () => {
	it('round-trips each kind of rating exactly; schemaVersion stays 1', () => {
		for (const rating of [
			POINT,
			// Doubles that take 17 digits (typed values converted to SI are such numbers).
			{ kind: 'point', pressureLoss: 1e5 / 3, flow: 0.1 / 3, density: 998.2072 },
			{ kind: 'Cv', value: 80 },
			{ kind: 'Kv', value: 60.5 }
		] as EquipmentRating[]) {
			const project = equipmentProject(rating);
			const encoded = encodeProject(project);
			const decoded = decodeProject(encoded);
			expect(decoded).toEqual(project);
			expect(decoded.schemaVersion).toBe(1);
			expect(encodeProject(decoded)).toBe(encoded);
		}
	});

	it('reports a bad value at its field, and an unknown kind (K included) as a rating kind', () => {
		const bad = structuredClone(equipmentProject());
		(bad.components[1] as { rating: unknown }).rating = { ...POINT, pressureLoss: -1 };
		expect(schemaProblems(bad).join(' ')).toMatch(/"E1" › rating › pressureLoss: must be > 0/);
		(bad.components[1] as { rating: unknown }).rating = { kind: 'K', value: 2 };
		expect(schemaProblems(bad)).toEqual([
			"components[1] \"E1\" › rating: unknown rating kind \"K\" (a pressure drop at a flow, 'point'; 'Cv'; or 'Kv')"
		]);
		(bad.components[1] as { rating: unknown }).rating = { kind: 'Cv' };
		expect(schemaProblems(bad).join(' ')).toMatch(/rating: is missing the required field "value"/);
	});
});
