/**
 * The pressure relief valve's web model (proposal pressure-relief-valve.md §5, §6, §7.6): what the
 * factory creates and asks for, the open discharge, the area unit, the capacity union and
 * x-relief-data read from the schema (never copied), validation against the capacity's own kind,
 * ASME's default overpressure, the Relief valves table and Build strip, Compare's rows and their
 * order, goal seek's groups, default boxes and the overpressure start rule, the scenario words and
 * the kind-switch removals of decision 18, and the flag, issue and system-curve texts in SI and US
 * units. Sets, areas, coefficients and results are made-up test inputs; the API's messages are its
 * own words (apps/api solver/results.py, relief.py).
 */
import { describe, expect, it } from 'vitest';
import openapi from '../api/openapi.json';
import type { Component, Flag, Project, ReliefValve } from '../api/types';
import { reliefProject } from '../testing/helpers';
import {
	flag,
	goalSeekResponse,
	reliefResult,
	reliefSolved,
	systemCurvePoint
} from '../testing/results';
import { compareCells, defaultRows, QUANTITIES, rowKey } from './compare';
import { addOpenDischarge, EditError, takesOpenDischarge } from './edit';
import { pumpTransferExample } from './examples';
import {
	CAPACITY_KINDS,
	capacityDraft,
	completeCapacity,
	createComponent,
	createEmptyProject,
	ID_PREFIX,
	KIND_LABELS,
	MissingEntryError,
	missingEntries,
	withCapacityValue
} from './factory';
import { flagText } from './flag-text';
import {
	defaultBounds,
	foundValueTexts,
	GOAL_GROUPS,
	goalHint,
	nowText,
	variableChoices,
	variableLabel,
	variableSpec,
	variableView,
	withCaseKind,
	type WordsContext
} from './goal-seek';
import { topologyIssueViews } from './issue-text';
import {
	api526Letters,
	capacityKinds,
	capacitySchemaName,
	componentGoalFields,
	componentOverrideFields,
	holdsSchema,
	RELIEF_DATA
} from './model-rules';
import {
	capacityText,
	defaultOverpressure,
	letterOptionLabel,
	reliefOnAsmeDefault
} from './relief';
import { elementSummary, hasReliefValves, reliefTable, RELIEF_NO_RESULT } from './results';
import {
	caseProject,
	carryChanges,
	changeStates,
	changeValueText,
	fieldLabelFor,
	trackPipes,
	withScenarios
} from './scenarios';
import { systemPointNote } from './system-curve-text';
import { displayUnit, IMPERIAL_UNITS, INCH, SI_UNITS, toSI, unitLabel } from './units';
import { schemaProblems } from './validate';
import { kindOptions } from '../components/panel/kinds';

type JsonObject = Record<string, unknown>;
const SCHEMAS = openapi.components.schemas as unknown as Record<string, JsonObject>;
const PSI = toSI(1, 'psi');

function valveOf(project: Project, id = 'RV1'): ReliefValve {
	const valve = project.components.find((c) => c.id === id);
	if (valve?.type !== 'relief_valve') throw new Error(`no relief valve ${id}`);
	return valve;
}

describe('the factory', () => {
	it('names the kind, its group and its prefix: never PRV or PSV', () => {
		expect(KIND_LABELS.relief_valve).toBe('Pressure relief valve (API 520, liquids)');
		expect(ID_PREFIX.relief_valve).toBe('RV');
		const options = kindOptions();
		const relief = options.findIndex((o) => o.value === 'relief_valve');
		expect(options[relief]?.group).toBe('Relief valves: overpressure protection, liquids');
		// Right after the control valves.
		expect(options[relief - 1]?.value).toBe('fcv');
	});

	it('asks for the set and the capacity, one message per empty field of the kind chosen', () => {
		expect(missingEntries('relief_valve', {}).map((m) => m.field)).toEqual([
			'setPressure',
			'capacity.letter'
		]);
		expect(
			missingEntries('relief_valve', { setPressure: 5e5, capacity: { kind: 'effective' } })
		).toEqual([
			{
				field: 'capacity.area',
				message:
					'Enter the API 520 effective area, or choose an API 526 orifice letter: the capacity has no default.'
			}
		]);
		expect(
			missingEntries('relief_valve', {
				setPressure: 5e5,
				capacity: { kind: 'certified', area: 2.5e-4 }
			}).map((m) => m.field)
		).toEqual(['capacity.dischargeCoefficient']);
		// The overpressure is optional (ASME's, the default): never missing.
		expect(
			missingEntries('relief_valve', {
				setPressure: 5e5,
				capacity: { kind: 'certified', area: 2.5e-4, dischargeCoefficient: 0.7 }
			})
		).toEqual([]);
		expect(() => createComponent('relief_valve', createEmptyProject())).toThrow(MissingEntryError);
		expect(() =>
			createComponent('relief_valve', createEmptyProject(), { setPressure: 5e5 })
		).toThrow(MissingEntryError);
	});

	it('creates it active, with the values entered exactly, and a certified overpressure only when entered', () => {
		const project = createEmptyProject();
		const valve = createComponent('relief_valve', project, {
			setPressure: 5e5,
			capacity: { kind: 'certified', area: 2.5e-4, dischargeCoefficient: 0.7 }
		});
		expect(valve).toMatchObject({
			id: 'RV1',
			name: 'Relief valve RV1',
			type: 'relief_valve',
			setPressure: 5e5,
			status: 'active',
			capacity: { kind: 'certified', area: 2.5e-4, dischargeCoefficient: 0.7 }
		});
		expect(valve.capacity).not.toHaveProperty('overpressure');
		expect(valve.ports.map((p) => [p.id, p.direction])).toEqual([
			['inlet', 'inlet'],
			['outlet', 'outlet']
		]);
	});

	it('drafts a capacity without carrying a value from one kind to another', () => {
		const certified = {
			kind: 'certified',
			area: 2.5e-4,
			dischargeCoefficient: 0.7,
			overpressure: null
		} as const;
		expect(capacityDraft(certified)).toEqual({
			kind: 'certified',
			area: 2.5e-4,
			dischargeCoefficient: 0.7
		});
		expect(completeCapacity({ kind: 'api526' })).toBeNull();
		expect(completeCapacity({ kind: 'api526', letter: 'J' })).toEqual({
			kind: 'api526',
			letter: 'J'
		});
		expect(completeCapacity({ kind: 'effective', area: Number.NaN })).toBeNull();
		const op = withCapacityValue(
			{ kind: 'certified', area: 1e-4, dischargeCoefficient: 0.7 },
			'overpressure',
			0.08
		);
		expect(completeCapacity(op)).toEqual({
			kind: 'certified',
			area: 1e-4,
			dischargeCoefficient: 0.7,
			overpressure: 0.08
		});
		expect(withCapacityValue(op, 'overpressure', null)).not.toHaveProperty('overpressure');
		expect(CAPACITY_KINDS).toEqual(capacityKinds());
	});
});

describe('the open discharge', () => {
	function freeOutlet(): Project {
		const project = reliefProject();
		return {
			...project,
			components: project.components.slice(0, 2),
			connections: [project.connections[0]!]
		};
	}

	it("is a reference node at 0 Pa gauge at the outlet's elevation, through 1 m of pipe with an exit", () => {
		const project = freeOutlet();
		const valve = valveOf(project);
		valve.elevation = 2;
		valve.ports[1] = { ...valve.ports[1]!, elevation: 2.5 };
		const next = addOpenDischarge(project, 'RV1', 'outlet', { reserved: ['N1'] });
		// The id avoids a reserved one; the node is at the port's own elevation where it has one.
		expect(next.components.at(-1)).toMatchObject({
			id: 'N2',
			name: 'Open discharge N2',
			type: 'reference_node',
			pressure: 0,
			elevation: 2.5,
			ports: [{ id: 'port_1', nominalSize: 0.0762 }]
		});
		expect(next.connections.at(-1)?.piping).toEqual({
			pipes: [{ materialId: 'carbon_steel', schedule: '40', nominalSize: 0.0762, length: 1 }],
			fittings: [{ type: 'exit', quantity: 1, pipeIndex: 0 }]
		});
		expect(project.components).toHaveLength(2); // pure
		expect(() => addOpenDischarge(reliefProject(), 'RV1', 'outlet')).toThrow(EditError);
	});

	it("is offered at a relief valve's outlet only", () => {
		const valve = valveOf(reliefProject());
		expect(takesOpenDischarge(valve, 'outlet')).toBe(true);
		expect(takesOpenDischarge(valve, 'inlet')).toBe(false);
		expect(takesOpenDischarge(createComponent('check', createEmptyProject()), 'outlet')).toBe(
			false
		);
	});
});

describe('the area unit', () => {
	it('is the square of the diameter unit, exactly', () => {
		expect(toSI(1, 'mm2')).toBe(1e-6);
		expect(toSI(1, 'm2')).toBe(1);
		expect(toSI(1, 'in2')).toBe(INCH * INCH);
		expect(toSI(1, 'in2')).toBeCloseTo(6.4516e-4, 18);
		expect(displayUnit('area', SI_UNITS)).toBe('mm2');
		expect(displayUnit('area', IMPERIAL_UNITS)).toBe('in2');
		expect(displayUnit('area', { ...SI_UNITS, diameter: 'm' })).toBe('m2');
		expect([unitLabel('area', 'mm2'), unitLabel('area', 'm2'), unitLabel('area', 'in2')]).toEqual([
			'mm²',
			'm²',
			'in²'
		]);
	});
});

describe('the capacity union and x-relief-data, read from the schema', () => {
	it('tells the capacity apart by its kind', () => {
		expect(capacitySchemaName('api526')).toBe('Api526Orifice');
		expect(capacitySchemaName('effective')).toBe('EffectiveOrifice');
		expect(capacitySchemaName('certified')).toBe('CertifiedOrifice');
		expect(capacitySchemaName('point')).toBeNull();
		expect(holdsSchema({ kind: 'certified' }, 'CertifiedOrifice')).toBe(true);
		expect(holdsSchema({ kind: 'certified' }, 'EffectiveOrifice')).toBe(false);
	});

	it("reads API 526's letters and areas and ASME's numbers from x-relief-data", () => {
		const published = SCHEMAS.ReliefValve!['x-relief-data'] as JsonObject;
		expect(RELIEF_DATA).toEqual(published);
		const letters = ((SCHEMAS.Api526Orifice!.properties as JsonObject).letter as { enum: string[] })
			.enum;
		expect(api526Letters()).toEqual(letters);
		expect(letterOptionLabel('J', SI_UNITS)).toBe('J: 830.3 mm²');
		expect(letterOptionLabel('J', IMPERIAL_UNITS)).toBe('J: 1.287 in²');
	});

	it('publishes the allow-list values and the goal-seek variables of decisions 18-19', () => {
		const valve = valveOf(reliefProject());
		expect(Object.keys(componentOverrideFields(valve)).sort()).toEqual(
			[
				'status',
				'setPressure',
				'capacity',
				'capacity.letter',
				'capacity.area',
				'capacity.dischargeCoefficient',
				'capacity.overpressure'
			].sort()
		);
		expect(componentOverrideFields(valve)['capacity.area']?.holders).toEqual([
			'EffectiveOrifice',
			'CertifiedOrifice'
		]);
		const fields = componentGoalFields(valve);
		expect(Object.fromEntries(Object.entries(fields).map(([k, v]) => [k, v.scale]))).toEqual({
			setPressure: 'linear',
			'capacity.area': 'log',
			'capacity.dischargeCoefficient': 'linear',
			'capacity.overpressure': 'linear'
		});
	});
});

describe('validation', () => {
	it('reports a capacity problem against its own kind only', () => {
		const project = reliefProject({
			capacity: { kind: 'certified', area: 2.5e-4 } as unknown as ReliefValve['capacity']
		});
		const problems = schemaProblems(project);
		expect(problems).toHaveLength(1);
		expect(problems[0]).toMatch(/capacity: is missing the required field "dischargeCoefficient"$/);
		expect(problems[0]).not.toMatch(/letter/);
		expect(schemaProblems(reliefProject())).toEqual([]);
		const unknown = reliefProject({
			capacity: { kind: 'nameplate' } as unknown as ReliefValve['capacity']
		});
		expect(schemaProblems(unknown)).toEqual([
			expect.stringMatching(/capacity: unknown capacity kind "nameplate"/)
		]);
	});
});

describe("ASME's default overpressure (decision 6)", () => {
	it('is 10 % or 3 psi, whichever is greater, for a set of at least 15 psi only', () => {
		// The crossover at 30 psi, where 3 psi is 10 % of the set.
		expect(defaultOverpressure(30 * PSI)).toBeCloseTo(0.1, 15);
		expect(defaultOverpressure(5e5)).toBe(0.1);
		expect(defaultOverpressure(1.5e5)).toBe(RELIEF_DATA.asmeOverpressureFloor / 1.5e5);
		expect(defaultOverpressure(RELIEF_DATA.asmeMinimumSetPressure)).toBeCloseTo(0.2, 15);
		expect(defaultOverpressure(RELIEF_DATA.asmeMinimumSetPressure * (1 - 1e-12))).toBeNull();
		expect(defaultOverpressure(null)).toBeNull();
		expect(defaultOverpressure(Number.NaN)).toBeNull();
	});

	it('applies to a letter and an effective area always, to a certified capacity without one', () => {
		expect(reliefOnAsmeDefault({ capacity: { kind: 'api526', letter: 'J' } })).toBe(true);
		expect(reliefOnAsmeDefault({ capacity: { kind: 'effective', area: 1e-4 } })).toBe(true);
		expect(
			reliefOnAsmeDefault({
				capacity: { kind: 'certified', area: 1e-4, dischargeCoefficient: 0.7 }
			})
		).toBe(true);
		expect(
			reliefOnAsmeDefault({
				capacity: { kind: 'certified', area: 1e-4, dischargeCoefficient: 0.7, overpressure: 0.08 }
			})
		).toBe(false);
	});

	it('words a capacity in the display units', () => {
		expect(capacityText({ kind: 'api526', letter: 'J' }, SI_UNITS)).toBe(
			'API 526 J (830.3 mm²), Kd 0.65 (preliminary)'
		);
		expect(capacityText({ kind: 'effective', area: 4.470709e-4 }, SI_UNITS)).toBe(
			'API 520 effective area 447.1 mm², Kd 0.65 (preliminary)'
		);
		expect(
			capacityText({ kind: 'certified', area: 2.5e-4, dischargeCoefficient: 0.7 }, IMPERIAL_UNITS)
		).toBe(
			"Certified area 0.3875 in², rated coefficient 0.7, overpressure ASME's 10 % or 3 psi (the default)"
		);
		expect(
			capacityText(
				{ kind: 'certified', area: 2.5e-4, dischargeCoefficient: 0.7, overpressure: 0.08 },
				SI_UNITS
			)
		).toBe('Certified area 250 mm², rated coefficient 0.7, overpressure 8 %');
	});
});

describe('the Relief valves table and Build strip', () => {
	it('reads every value from the result, "—" for a pressure in a floating section', () => {
		const project = reliefProject();
		const table = reliefTable(project, reliefSolved({ inletPressure: null }), SI_UNITS);
		expect(table.columns.map((c) => c.key)).toEqual([
			'state',
			'flow',
			'fullLiftFlow',
			'flowRatio',
			'inletPressure',
			'setRatio',
			'lift',
			'backPressure',
			'pressureDrop',
			'headLoss'
		]);
		expect(table.rows[0]?.cells).toMatchObject({
			state: 'Partial lift',
			inletPressure: '—',
			setRatio: '105.3',
			lift: '53.1'
		});
		expect(table.rows[0]?.flags.map((f) => f.code)).toEqual(['CORRELATION_OUT_OF_RANGE']);
	});

	it("gives the strip the table's own cells: state, flow, inlet pressure and Δp ÷ set", () => {
		const project = reliefProject();
		const solved = reliefSolved({ state: 'full_lift', lift: 1, flowRatio: 1.107 });
		const row = reliefTable(project, solved, IMPERIAL_UNITS).rows[0]!;
		const summary = elementSummary(project, solved, IMPERIAL_UNITS, {
			kind: 'component',
			id: 'RV1'
		});
		expect(summary?.items.map((i) => [i.key, i.cell])).toEqual([
			['state', row.cells.state],
			['flow', row.cells.flow],
			['inletPressure', row.cells.inletPressure],
			['setRatio', row.cells.setRatio]
		]);
		expect(summary?.items.find((i) => i.key === 'inletPressure')?.unit).toBe('psig');
		expect(row.cells.state).toBe('Full lift');
	});

	it('lists a valve with no result by its RELIEF_VALVE_CLOSED flag', () => {
		const closed = flag({
			code: 'RELIEF_VALVE_CLOSED',
			severity: 'info',
			message: 'made-up',
			componentId: 'RV1',
			details: { side: 'outlet', section: 'closed_off', setHead: 51, setPressure: 5e5 }
		});
		const solved = reliefSolved({}, { reliefValveResults: {}, flags: [closed] });
		expect(hasReliefValves(solved)).toBe(true);
		const row = reliefTable(reliefProject(), solved, SI_UNITS).rows[0]!;
		expect(row.cells.state).toBe(RELIEF_NO_RESULT);
		expect(row.cells.flow).toBe('—');
		expect(row.flags).toEqual([closed]);
		expect(hasReliefValves(reliefSolved({}, { reliefValveResults: {}, flags: [] }))).toBe(false);
	});
});

describe('Compare (decision 20)', () => {
	/** The transfer example with a relief valve on its discharge (made-up inputs). */
	function withRelief(): Project {
		const base = pumpTransferExample();
		const valve = createComponent('relief_valve', base, {
			setPressure: 5e5,
			capacity: { kind: 'api526', letter: 'J' }
		});
		return withScenarios({ ...base, components: [...base.components, valve] }, [
			{
				id: 'S1',
				name: 'Blocked',
				overrides: [{ kind: 'component', componentId: 'V1', field: 'status', value: 'isolated' }]
			}
		]);
	}

	it("shows each relief valve's flow, state and inlet pressure right after the pumps' rows", () => {
		const rows = defaultRows(withRelief(), [null, null]).map(rowKey);
		const keys = (quantity: string, id?: string) =>
			rowKey({ quantity: quantity as never, ...(id ? { elementId: id } : {}) });
		const relief = rows.indexOf(keys('reliefFlow', 'RV1'));
		expect(rows.slice(relief, relief + 3)).toEqual([
			keys('reliefFlow', 'RV1'),
			keys('reliefState', 'RV1'),
			keys('reliefInletPressure', 'RV1')
		]);
		expect(rows.indexOf(keys('pumpHead', 'P1'))).toBeLessThan(relief);
		// Before the changed elements, so the 40-row limit cuts those first.
		expect(rows.indexOf(keys('valveFlow', 'V1'))).toBeGreaterThan(relief);
	});

	it('gives a relative difference for the flow only', () => {
		expect(
			Object.entries(QUANTITIES)
				.filter(([, spec]) => spec.element === 'relief')
				.map(([q, spec]) => [q, !!spec.relative])
		).toEqual([
			['reliefFlow', true],
			['reliefState', false],
			['reliefInletPressure', false],
			['reliefSetRatio', false],
			['reliefPressureDrop', false]
		]);
		const project = reliefProject();
		const base = { solved: reliefSolved(), converged: true };
		const blocked = {
			solved: reliefSolved({ flow: 0.00444, inletPressure: 550000, state: 'full_lift' }),
			converged: true
		};
		const flow = compareCells(
			{ quantity: 'reliefFlow', elementId: 'RV1' },
			[base, blocked],
			project,
			SI_UNITS
		);
		expect(flow[1]?.diff?.text).toBe('+2.22 (+100 %)');
		const inlet = compareCells(
			{ quantity: 'reliefInletPressure', elementId: 'RV1' },
			[base, blocked],
			project,
			SI_UNITS
		);
		expect(inlet[1]?.diff?.text).toBe('+23.9');
		const state = compareCells(
			{ quantity: 'reliefState', elementId: 'RV1' },
			[base, blocked],
			project,
			SI_UNITS
		);
		expect([state[0]?.text, state[1]?.text, state[1]?.baseText]).toEqual([
			'Partial lift',
			'Full lift',
			'Partial lift'
		]);
	});
});

describe('goal seek (decision 19)', () => {
	const target = { kind: 'component', componentId: 'RV1' } as const;

	it('groups the relief valve after the valves, with its two goals', () => {
		expect(GOAL_GROUPS.indexOf('relief')).toBe(GOAL_GROUPS.indexOf('valve') + 1);
		const project = reliefProject();
		expect(goalHint(project, { quantity: 'relief_valve_flow', elementId: 'RV1' })).toBe(
			'Positive from inlet to outlet: the relieving flow.'
		);
		expect(goalHint(project, { quantity: 'relief_valve_pressure_drop', elementId: 'RV1' })).toBe(
			'Static pressure, inlet minus outlet.'
		);
	});

	it("offers a letter's set only, and every value of a certified capacity", () => {
		const fields = (project: Project) =>
			variableChoices(project)
				.filter((c) => c.target.kind === 'component' && c.target.componentId === 'RV1')
				.map((c) => [c.group, c.field]);
		expect(fields(reliefProject())).toEqual([['relief', 'setPressure']]);
		expect(fields(reliefProject({ capacity: { kind: 'effective', area: 4e-4 } }))).toEqual([
			['relief', 'setPressure'],
			['relief', 'capacity.area']
		]);
		expect(
			fields(
				reliefProject({ capacity: { kind: 'certified', area: 2.5e-4, dischargeCoefficient: 0.7 } })
			)
		).toEqual([
			['relief', 'setPressure'],
			['relief', 'capacity.area'],
			['relief', 'capacity.dischargeCoefficient'],
			['relief', 'capacity.overpressure']
		]);
	});

	it('shows each value in its unit: the set a difference, the area an area', () => {
		const project = reliefProject();
		expect(variableSpec(project, { target, field: 'setPressure' })).toEqual({
			category: 'pressure',
			options: {}
		});
		expect(variableSpec(project, { target, field: 'capacity.area' }).category).toBe('area');
		expect(variableSpec(project, { target, field: 'capacity.dischargeCoefficient' }).category).toBe(
			'dimensionless'
		);
		expect(variableSpec(project, { target, field: 'capacity.overpressure' }).category).toBe(
			'fraction'
		);
	});

	it("raises the set's lower bound to 15 psi where the overpressure is ASME's, and only there", () => {
		const scope = RELIEF_DATA.asmeMinimumSetPressure;
		expect(defaultBounds(reliefProject(), { target, field: 'setPressure' })).toEqual({
			lower: 2.5e5,
			upper: 1e6
		});
		expect(
			defaultBounds(reliefProject({ setPressure: 1.5e5 }), { target, field: 'setPressure' })
		).toEqual({
			lower: scope,
			upper: 3e5
		});
		// A certified overpressure entered: the default does not apply, nor its scope.
		const certified = reliefProject({
			setPressure: 1.5e5,
			capacity: { kind: 'certified', area: 2.5e-4, dischargeCoefficient: 0.7, overpressure: 0.08 }
		});
		expect(defaultBounds(certified, { target, field: 'setPressure' })).toEqual({
			lower: 7.5e4,
			upper: 3e5
		});
		// A set already below the scope (refused by the API) keeps its own value inside the box.
		expect(
			defaultBounds(reliefProject({ setPressure: 5e4 }), { target, field: 'setPressure' }).lower
		).toBe(5e4);
	});

	it("boxes the area in API 526's D to T, widened to hold the case's own", () => {
		const areas = Object.values(RELIEF_DATA.api526Areas);
		const [d, t] = [Math.min(...areas), Math.max(...areas)];
		const effective = (area: number) =>
			defaultBounds(reliefProject({ capacity: { kind: 'effective', area } }), {
				target,
				field: 'capacity.area'
			});
		expect(effective(4e-4)).toEqual({ lower: d, upper: t });
		expect(effective(5e-5)).toEqual({ lower: 5e-5, upper: t });
		expect(effective(0.02)).toEqual({ lower: d, upper: 0.02 });
	});

	it("boxes a certified coefficient and overpressure at half to twice the value, at most 1; on ASME's default its value at the set", () => {
		const certified = (overpressure?: number) =>
			reliefProject({
				capacity: {
					kind: 'certified',
					area: 2.5e-4,
					dischargeCoefficient: 0.7,
					...(overpressure === undefined ? {} : { overpressure })
				}
			});
		expect(defaultBounds(certified(), { target, field: 'capacity.dischargeCoefficient' })).toEqual({
			lower: 0.35,
			upper: 1
		});
		expect(defaultBounds(certified(0.08), { target, field: 'capacity.overpressure' })).toEqual({
			lower: 0.04,
			upper: 0.16
		});
		expect(defaultBounds(certified(), { target, field: 'capacity.overpressure' })).toEqual({
			lower: 0.05,
			upper: 0.2
		});
		const variable = {
			target,
			field: 'capacity.overpressure',
			lower: 0.05,
			upper: 0.2,
			defaults: { lower: 0.05, upper: 0.2 }
		};
		expect(nowText(certified(), variable, { prefs: SI_UNITS })).toBe(
			"Now ASME's 10 % or 3 psi (20.68 kPa), the default (10 % at this set); the search starts at the middle of the bounds"
		);
		expect(nowText(certified(0.08), variable, { prefs: SI_UNITS })).toBe('Now 8 %');
	});

	it("names an area variable by the case's kind of capacity, whatever the names project holds", () => {
		// A base on API 526's J (no area) and a scenario sizing it by an effective area.
		const base: Project = {
			...reliefProject(),
			scenarios: [
				{
					id: 'S1',
					name: 'Sizing',
					overrides: [
						{
							kind: 'component',
							componentId: 'RV1',
							field: 'capacity',
							value: { kind: 'effective', area: 8.3032092e-4 }
						}
					]
				}
			]
		};
		const variable = { target, field: 'capacity.area' };
		expect(variableLabel(base, variable)).toBe('Discharge relief · Orifice area');
		expect(variableLabel(base, withCaseKind(caseProject(base, 'S1'), variable))).toBe(
			'Discharge relief · API 520 effective area'
		);
		// Other fields are left as they are.
		const other = { target, field: 'setPressure' };
		expect(withCaseKind(caseProject(base, 'S1'), other)).toBe(other);
		// A run on the case, named from the base: its view and its notice, the acronym kept.
		const context: WordsContext = {
			labels: base,
			sent: base,
			prefs: SI_UNITS,
			caseWords: 'scenario Sizing',
			caseId: 'S1'
		};
		const sized = {
			kind: 'component',
			componentId: 'RV1',
			field: 'capacity.area',
			lower: 7.09676e-5,
			upper: 0.01677416
		} as const;
		expect(variableView(context, sized).label).toBe('Discharge relief · API 520 effective area');
		const response = goalSeekResponse({
			variables: [
				{
					...goalSeekResponse().result.variables[0]!,
					variable: sized,
					value: 4.470709e-4,
					override: {
						kind: 'component',
						componentId: 'RV1',
						field: 'capacity',
						value: { kind: 'effective', area: 4.470709e-4 }
					}
				}
			]
		});
		expect(foundValueTexts(response, context)).toEqual([
			'Discharge relief API 520 effective area 447.071 mm²'
		]);
		// A certified capacity's area is the valve's actual area, in a sentence lowercase.
		const certified = reliefProject({
			capacity: { kind: 'certified', area: 2.5e-4, dischargeCoefficient: 0.7, overpressure: 0.1 }
		});
		const plain = { ...context, labels: certified, sent: certified, caseId: null };
		expect(variableView(plain, sized).label).toBe('Discharge relief · Actual orifice area');
		expect(foundValueTexts(response, plain)).toEqual([
			'Discharge relief actual orifice area 447.071 mm²'
		]);
	});
});

describe('scenarios (decision 18)', () => {
	const target = { kind: 'component', componentId: 'RV1' } as const;

	it('names and words every value as the form does', () => {
		const project = reliefProject();
		const valve = valveOf(project);
		expect(
			[
				'status',
				'setPressure',
				'capacity',
				'capacity.letter',
				'capacity.area',
				'capacity.dischargeCoefficient',
				'capacity.overpressure'
			].map((f) => fieldLabelFor(valve, f))
		).toEqual([
			'Status',
			'Set pressure',
			'Capacity',
			'API 526 orifice letter',
			'Orifice area',
			'Rated coefficient of discharge (K)',
			'Overpressure at full lift'
		]);
		const certified = valveOf(
			reliefProject({ capacity: { kind: 'certified', area: 1e-4, dischargeCoefficient: 0.7 } })
		);
		expect(fieldLabelFor(certified, 'capacity.area')).toBe('Actual orifice area');
		const text = (field: string, value: unknown, units = SI_UNITS) =>
			changeValueText(
				project,
				{ kind: 'component', componentId: 'RV1', field: field as never, value },
				value,
				units
			);
		expect(text('status', 'locked_closed')).toBe(
			'Locked closed (gagged or blocked: does not open)'
		);
		// A difference: no gauge marker.
		expect(text('setPressure', 5e5)).toBe('500 kPa');
		expect(text('setPressure', 5e5, IMPERIAL_UNITS)).toBe('72.52 psi');
		expect(text('capacity.letter', 'J')).toBe('API 526 J (830.3 mm²)');
		expect(text('capacity.area', 4.470709e-4)).toBe('447.1 mm²');
		expect(text('capacity.dischargeCoefficient', 0.7)).toBe('0.7');
		expect(text('capacity.overpressure', null)).toBe(
			"ASME's 10 % or 3 psi (20.68 kPa) (the default)"
		);
		expect(text('capacity.overpressure', 0.08)).toBe('8 %');
		expect(text('capacity', { kind: 'api526', letter: 'E' })).toBe(
			'API 526 E (126.5 mm²), Kd 0.65 (preliminary)'
		);
	});

	it("holds an area on an effective and a certified capacity, never a letter's; says why", () => {
		const scenario = (field: string, value: unknown, valve: Partial<ReliefValve> = {}) =>
			changeStates(
				withScenarios(reliefProject(valve), [
					{
						id: 'S1',
						name: 'Bigger',
						overrides: [{ kind: 'component', componentId: 'RV1', field: field as never, value }]
					}
				]),
				'S1'
			)[0]!;
		expect(
			scenario('capacity.area', 5e-4, { capacity: { kind: 'effective', area: 4e-4 } }).state
		).toBe('applied');
		expect(
			scenario('capacity.area', 5e-4, {
				capacity: { kind: 'certified', area: 4e-4, dischargeCoefficient: 0.7 }
			}).state
		).toBe('applied');
		expect(scenario('capacity.area', 5e-4)).toMatchObject({
			state: 'not_applicable',
			message:
				"Discharge relief's capacity is given by an API 526 orifice letter (its orifice area applies to an API 520 effective area or a certified capacity)"
		});
		expect(
			scenario('capacity.overpressure', 0.08, { capacity: { kind: 'effective', area: 4e-4 } })
		).toMatchObject({
			state: 'not_applicable',
			message:
				"Discharge relief's capacity is given by an API 520 effective area (its overpressure at full lift applies to a certified capacity)"
		});
		expect(scenario('capacity.letter', 'J').state).toBe('applied');
		void target;
	});

	it("removes the changes of the old kind's values when the base switches kind, and says so", () => {
		const changes = [
			{ kind: 'component', componentId: 'RV1', field: 'capacity.letter', value: 'E' },
			{ kind: 'component', componentId: 'RV1', field: 'setPressure', value: 4e5 }
		] as const;
		const before = withScenarios(reliefProject(), [
			{ id: 'S1', name: 'Smaller valve', overrides: [...changes] }
		]);
		const next = structuredClone(before);
		valveOf(next).capacity = { kind: 'effective', area: 4e-4 };
		const carried = carryChanges(before, trackPipes(before, structuredClone(before)), next);
		expect(carried.project.scenarios?.[0]?.overrides).toEqual([changes[1]]);
		expect(carried.notes).toEqual([
			'The capacity value changes of Discharge relief in Smaller valve were removed: its capacity is given by an API 520 effective area now, not an API 526 orifice letter, and no value carries from one kind of capacity to another.'
		]);
		// Between an effective and a certified capacity, the area goes too (not an actual area).
		const effective = withScenarios(
			reliefProject({ capacity: { kind: 'effective', area: 4e-4 } }),
			[
				{
					id: 'S1',
					name: 'Bigger',
					overrides: [
						{ kind: 'component', componentId: 'RV1', field: 'capacity.area', value: 5e-4 },
						{
							kind: 'component',
							componentId: 'RV1',
							field: 'capacity',
							value: { kind: 'api526', letter: 'K' }
						}
					]
				}
			]
		);
		const certified = structuredClone(effective);
		valveOf(certified).capacity = { kind: 'certified', area: 4e-4, dischargeCoefficient: 0.7 };
		const moved = carryChanges(
			effective,
			trackPipes(effective, structuredClone(effective)),
			certified
		);
		// The whole capacity is kept: it is one value whatever the base's kind.
		expect(moved.project.scenarios?.[0]?.overrides?.map((o) => o.field)).toEqual(['capacity']);
		expect(moved.notes[0]).toMatch(/\(an effective area is not an actual area\)\.$/);
	});
});

describe('flag texts', () => {
	const project = reliefProject();
	const text = (f: Flag, units = SI_UNITS) => flagText(f, { project, prefs: units });

	it('full lift, and beyond it', () => {
		const open = flag({
			code: 'RELIEF_VALVE_OPEN',
			severity: 'info',
			message: 'made-up',
			componentId: 'RV1',
			details: {
				flow: 0.004732647684257,
				totalPressureDifference: 675900,
				setRatio: 1.3518,
				flowRatio: 1.107271031
			}
		});
		expect(text(open)).toBe(
			"At full lift: it relieves 4.733 L/s at a total-pressure difference of 675.9 kPa (135.2 % of its set pressure), 110.7 % of its capacity at full lift: beyond its rated overpressure, where API 520's equation holds and the flow grows with the square root of the pressure difference."
		);
		expect(text(open, IMPERIAL_UNITS)).toMatch(
			/^At full lift: it relieves 75\.01 gpm at a total-pressure difference of 98\.03 psi /
		);
		// Just at full lift: the ratio told apart from 100 %, and no "beyond".
		const at = { ...open, details: { ...open.details, flowRatio: 1 } };
		expect(text(at)).toMatch(/, 100 % of its capacity at full lift\.$/);
		const near = { ...open, details: { ...open.details, flowRatio: 1.00001 } };
		expect(text(near)).toMatch(/, 100\.001 % of its capacity at full lift: beyond/);
	});

	it('closed with no result: the side, why, and the levels that are steady states', () => {
		const closed = flag({
			code: 'RELIEF_VALVE_CLOSED',
			severity: 'info',
			message: 'made-up',
			componentId: 'RV1',
			details: {
				side: 'inlet',
				section: 'floating',
				setHead: 30.6,
				setPressure: 300000,
				pressureLimit: 300000
			}
		});
		expect(text(closed)).toBe(
			'Closed, with no result: the section on its inlet side has no fixed pressure level (undetermined pressure), so the pressure difference across it is undetermined. Every level of that section at which the difference does not exceed its set pressure (300 kPa) is a steady state: every inlet static pressure up to 300 kPa(g) (its back pressure plus its set).'
		);
		const off = flag({
			...closed,
			details: { side: 'outlet', section: 'closed_off', setHead: 30.6, setPressure: 300000 }
		});
		expect(text(off, IMPERIAL_UNITS)).toBe(
			'Closed, with no result: the section on its outlet side is closed off (no flow reaches it), so the pressure difference across it is undetermined. Every level of that section at which the difference does not exceed its set pressure (43.51 psi) is a steady state.'
		);
		// Without the details expected: the API's words, with names for ids.
		expect(
			text({
				...closed,
				message: "relief valve 'RV1' is closed and has no result: made-up",
				details: {}
			})
		).toBe('Relief valve “Discharge relief” is closed and has no result: made-up');
	});

	it("partial lift: the linear convention, against Pentair's typical characteristic", () => {
		const partial = flag({
			code: 'CORRELATION_OUT_OF_RANGE',
			severity: 'warning',
			message: 'made-up',
			componentId: 'RV1',
			details: {
				limit: 'partial_lift',
				lift: 0.5311270926,
				setRatio: 1.05311270926,
				overpressure: 0.1
			}
		});
		expect(text(partial)).toBe(
			'It relieves at partial lift (53.11 %, the pressure difference at 105.3 % of its set; full lift at 110 %): between set and full lift the lift is the linear convention, not a cited law. A typical liquid-trim valve lifts more slowly, surges to full lift near 107 % of set and recloses near 90 % (Pentair TP-V300 Fig. 4-12). A valve that has surged open passes more flow at a lower inlet pressure.'
		);
	});

	it('a viscous liquid: Kv not applied, the viscosity told apart from 0.1 Pa·s', () => {
		const viscous = flag({
			code: 'CORRELATION_OUT_OF_RANGE',
			severity: 'warning',
			message: 'made-up',
			componentId: 'RV1',
			details: { limit: 'viscosity', value: 0.2, lower: 0.1, kv: 0.9794, reynoldsNumber: 893.4 }
		});
		expect(text(viscous)).toBe(
			"The liquid's viscosity (200 mPa·s) is at or above 100 mPa·s, where API 520 (10th edition) corrects the capacity by its viscosity factor Kv (0.9794 at the solved flow, Reynolds number 893.4 on the orifice). Kv is not applied, so the capacity solved is likely overstated and the inlet pressure at this flow understated."
		);
		expect(
			text({ ...viscous, details: { ...viscous.details, value: 0.1 } }, IMPERIAL_UNITS)
		).toMatch(/^The liquid's viscosity \(100 cP\) is at or above 100 cP,/);
	});

	it('flashing at its outlet while it relieves', () => {
		const flash = flag({
			code: 'BELOW_VAPOR_PRESSURE',
			severity: 'invalid',
			message: 'made-up',
			componentId: 'RV1',
			details: { backAbsolutePressure: 101300, vaporPressure: 198674.4 }
		});
		expect(text(flash)).toBe(
			'The absolute static pressure at its outlet is 101.3 kPa(a), below the vapor pressure (198.7 kPa(a)) while it relieves: the jet leaves the valve at that back pressure, so the liquid would flash there and the flow solved is too high.'
		);
		const none = { ...flash, details: { backAbsolutePressure: -5, vaporPressure: 'not given' } };
		expect(text(none)).toMatch(
			/^The absolute static pressure at its outlet is -0\.005 kPa\(a\), below 0 kPa\(a\), below any liquid's vapor pressure/
		);
	});
});

describe('issue texts (RELIEF_VALVE_OUT_OF_RANGE)', () => {
	const scope = (remedy: string) =>
		`relief valve 'RV1': its set pressure of 50000 Pa is below ASME VIII's scope, 15 psi (103421 Pa): below it no cited source gives its overpressure at full lift (ASME's default, 10 % or 3 psi, is for sets within that scope), and API 520's effective coefficient of discharge applies to valves certified within it; ${remedy}`;
	const view = (message: string, units = SI_UNITS) =>
		topologyIssueViews(
			[{ code: 'RELIEF_VALVE_OUT_OF_RANGE', message, componentIds: ['RV1'], connectionIds: [] }],
			reliefProject(),
			true,
			units
		)[0]!;

	it("below ASME VIII's scope, with the remedy the server gives, in SI and US units", () => {
		const letter = scope(
			"enter the valve's certified capacity: its actual orifice area, rated coefficient of discharge and full-lift overpressure"
		);
		expect(view(letter)).toEqual({
			text: "Discharge relief: its set pressure (50 kPa) is below ASME VIII's scope, 15 psi (103.421 kPa): below it no cited source gives its overpressure at full lift (ASME's default, 10 % or 3 psi, is for sets within that scope), and API 520's effective coefficient of discharge applies to valves certified within it. Give its capacity as certified: the valve's actual orifice area, rated coefficient of discharge and full-lift overpressure.",
			links: [{ componentId: 'RV1' }],
			detail: letter
		});
		expect(
			view(scope('enter its certified overpressure at full lift'), IMPERIAL_UNITS).text
		).toMatch(
			/^Discharge relief: its set pressure \(7\.25189 psi\) is below ASME VIII's scope, 15 psi: .* Enter its certified overpressure at full lift\.$/
		);
	});

	it('a capacity the floating point cannot represent', () => {
		const message =
			"relief valve 'RV1': a certified area of 1e-310 m² with a rated coefficient of discharge of 0.7, C = Kd·A = 7e-311 m², with a set pressure of 500000 Pa and an overpressure of 0.1 gives C, the full-lift flow Q_f = 2.32396e-309 m³/s or the band coefficient R = inf that is not a finite positive normal floating-point number; the solver cannot represent this valve";
		expect(view(message).text).toBe(
			'Discharge relief: a certified area of 1e-304 mm² with a rated coefficient of discharge of 0.7, C = Kd·A = 7e-305 mm², with a set pressure of 500 kPa and an overpressure of 10 % gives a capacity, a full-lift flow or a band coefficient that is not a finite positive floating-point number, so the solver cannot represent this valve. Check its set pressure and capacity.'
		);
		// Not in a form expected: the server's words.
		expect(view("relief valve 'RV1': something else").text).toBe(
			"relief valve 'RV1': something else"
		);
	});
});

describe('system curves', () => {
	it('tells the relief valve rule of the API', () => {
		const project: Project = {
			...reliefProject(),
			components: [
				...reliefProject().components,
				{
					...createComponent('pump', reliefProject()),
					id: 'P1',
					name: 'Feed pump'
				} as Component
			]
		};
		const point = systemCurvePoint({
			flow: 0.01,
			reason: 'beyond_limit',
			componentIds: ['RV1'],
			limitFlow: 0,
			passedFlow: 0,
			message: 'made-up'
		});
		expect(systemPointNote(point, { project, units: SI_UNITS }).text).toContain(
			'passes Discharge relief, which passes no flow that way (a relief valve passes no reverse flow, and no flow while the pressure difference across it is below its set pressure).'
		);
	});
});

describe('the result helper', () => {
	it('is a made-up partial lift on API 526 F', () => {
		expect(reliefResult().capacity).toMatchObject({ kind: 'api526', letter: 'F' });
	});
});
