/**
 * Goal seek in the browser (proposal goal-seek.md §6, §7.5): the catalogues read from the
 * published rules, default bounds, the tolerance field's minimum, lapses, Run's reasons, the
 * request, the words of every stop reason and note, the tables and report, and Apply, checked
 * against the shared fixture the API generates with its real trial builder and readers.
 *
 * The networks are the home page's examples and made-up variants; the responses are made up
 * (testing/results.ts goalSeekResponse): no value here is a hydraulic result. Expected values are
 * written by hand from the design's tables, never computed by the code under test.
 */
import { describe, expect, it } from 'vitest';
import openapi from '../api/openapi.json';
import type {
	Component,
	FluidInfo,
	GoalSeekNote,
	GoalSeekResponse,
	Override,
	Project,
	SolvedState
} from '../api/types';
import fixture from './__fixtures__/goal-seek-cases.json';
import { goalSeekResponse } from '../testing/results';
import { QUANTITIES } from './compare';
import {
	deleteComponent,
	insertComponentInConnection,
	updateComponent,
	updateConnection
} from './edit';
import { createComponent } from './factory';
import { pumpTransferExample } from './examples';
import { canonicalJson } from './json';
import { addPipe, removePipe } from './piping';
import {
	applyProblems,
	applyToCase,
	asNewScenario,
	calculatingReason,
	defaultBounds,
	defaultToleranceText,
	differenceText,
	EMPTY_SETUP,
	foundOverrides,
	foundValueTexts,
	GOAL_QUANTITIES,
	goalChoices,
	goalElements,
	goalGroup,
	goalLapse,
	goalNeedProblem,
	goalSeekGoalsTable,
	goalSeekReport,
	goalSeekTrialTable,
	goalValue,
	hasGoal,
	hasVariable,
	keptByScenarios,
	lastSolveText,
	minimumTolerance,
	newGoal,
	newScenarioDescription,
	newVariable,
	noteText,
	nowText,
	outcomeLabel,
	outcomeText,
	purposeText,
	requestIssues,
	requestLineText,
	reservedIds,
	rowIssues,
	runProblems,
	stateChangeText,
	toleranceBounds,
	toleranceProblem,
	toRequest,
	variableBounds,
	variableChoices,
	variableLapse,
	variableSpec,
	type GoalDraft,
	type GoalSeekSetup,
	type VariableDraft,
	type WordsContext,
	variableLabelOf
} from './goal-seek';
import { boundsProblem } from './schema-bounds';
import { applyScenario, caseProject, withScenarios } from './scenarios';
import { IMPERIAL_UNITS, SI_UNITS } from './units';

type JsonObject = Record<string, unknown>;
const SCHEMAS = openapi.components.schemas as unknown as Record<string, JsonObject>;

const transfer = () => pumpTransferExample();

function edited(project: Project, id: string, change: (c: Component) => Component): Project {
	return updateComponent(project, id, change);
}

/** The transfer example with Transfer pump P1 flow-controlled (made-up setpoint and minimum). */
function controlled(minSpeed = 0.5, setpoint = 0.01): Project {
	return edited(
		transfer(),
		'P1',
		(c) => ({ ...c, control: { mode: 'flow', setpoint, minSpeed } }) as Component
	);
}

/** The transfer example with V1 a control valve of `valveType` at `setpoint` (made-up). */
function controlValve(valveType: 'prv' | 'psv' | 'fcv', setpoint: number): Project {
	return edited(
		transfer(),
		'V1',
		(c) =>
			({
				type: 'valve',
				valveType,
				id: c.id,
				name: c.name,
				elevation: c.elevation,
				status: 'active',
				setpoint,
				ports: c.ports
			}) as Component
	);
}

const P1 = { kind: 'component', componentId: 'P1' } as const;
const V1 = { kind: 'component', componentId: 'V1' } as const;
const R1 = { kind: 'component', componentId: 'R1' } as const;

function speedVariable(project = transfer()): VariableDraft {
	return newVariable(project, { target: P1, field: 'speed' });
}

function flowGoal(target: number | null = 0.015): GoalDraft {
	return { ...newGoal({ elementId: 'L2' }, 'link_flow'), target };
}

function oneByOne(project = transfer()): GoalSeekSetup {
	return { goals: [flowGoal()], variables: [speedVariable(project)] };
}

function words(project = transfer()): WordsContext {
	return { labels: project, sent: project, prefs: SI_UNITS, caseWords: 'the base case' };
}

const request = (project = transfer()) => toRequest(oneByOne(project), project, null);

describe('catalogues (x-goal-quantities, x-goal-variables)', () => {
	it('maps each published goal quantity to the Compare row that names and reads it', () => {
		const published = Object.keys(SCHEMAS.GoalSeekRequest!['x-goal-quantities'] as object);
		expect(Object.keys(GOAL_QUANTITIES).sort()).toEqual([...published].sort());
		expect(GOAL_QUANTITIES).toEqual({
			port_pressure: 'portPressure',
			link_flow: 'linkFlow',
			link_velocity: 'linkVelocity',
			link_head_loss: 'linkHeadLoss',
			pump_flow: 'pumpFlow',
			pump_head: 'pumpHead',
			pump_npsh_available: 'pumpNpsha',
			pump_npsh_margin: 'pumpNpshMargin',
			valve_flow: 'valveFlow',
			valve_pressure_drop: 'valvePressureDrop',
			equipment_flow: 'equipmentFlow',
			equipment_pressure_loss: 'equipmentPressureLoss',
			equipment_pressure_drop: 'equipmentPressureDrop',
			boundary_outflow: 'boundaryOutflow'
		});
		for (const [quantity, compare] of Object.entries(GOAL_QUANTITIES)) {
			expect(goalGroup(quantity as keyof typeof GOAL_QUANTITIES)).toBe(QUANTITIES[compare].element);
		}
	});

	it('offers every port, every connection, then pumps, valves and boundaries, by name', () => {
		const elements = goalElements(transfer());
		expect(elements.filter((e) => e.group === 'port').map((e) => e.label)).toEqual([
			'Port 1 of Suction tank',
			'Suction of Transfer pump',
			'Discharge of Transfer pump',
			'Inlet of Discharge isolation valve',
			'Outlet of Discharge isolation valve',
			'Port 1 of Discharge tank'
		]);
		expect(elements.filter((e) => e.group === 'connection').map((e) => e.label)).toEqual([
			'Suction tank → Transfer pump',
			'Transfer pump → Discharge isolation valve',
			'Discharge isolation valve → Discharge tank'
		]);
		expect(elements.filter((e) => e.group === 'pump').map((e) => e.elementId)).toEqual(['P1']);
		expect(elements.filter((e) => e.group === 'valve').map((e) => e.elementId)).toEqual(['V1']);
		expect(elements.filter((e) => e.group === 'boundary').map((e) => e.elementId)).toEqual([
			'R1',
			'R2'
		]);
		const choices = (group: string) =>
			goalChoices(
				transfer(),
				elements.find((e) => e.group === group)!
			);
		expect(choices('port')).toEqual(['port_pressure']);
		expect(choices('connection')).toEqual(['link_flow', 'link_velocity', 'link_head_loss']);
		expect(choices('pump')).toEqual([
			'pump_flow',
			'pump_head',
			'pump_npsh_available',
			'pump_npsh_margin'
		]);
		expect(choices('valve')).toEqual(['valve_flow', 'valve_pressure_drop']);
		expect(choices('boundary')).toEqual(['boundary_outflow']);
	});

	it('says what a quantity needs that the case lacks (needs: vapor pressure, NPSHr)', () => {
		const project = transfer();
		expect(goalNeedProblem(project, 'pump_npsh_margin', 'P1')).toBeNull();
		const noNpshr = {
			...project,
			pumpLibrary: project.pumpLibrary.map((c) => ({ ...c, npshrCurve: null }))
		};
		expect(goalNeedProblem(noNpshr, 'pump_npsh_margin', 'P1')).toBe(
			"the pump's curve has no NPSHr"
		);
		expect(goalNeedProblem(noNpshr, 'pump_npsh_available', 'P1')).toBeNull();
		const glycol: Project = {
			...project,
			fluid: {
				kind: 'builtin',
				fluidId: 'propylene_glycol',
				temperature: 293.15,
				concentration: 0.3
			}
		};
		const info = { vaporPressureAvailable: false } as FluidInfo;
		expect(goalNeedProblem(glycol, 'pump_npsh_available', 'P1', info)).toBe(
			'the fluid has no vapor pressure'
		);
		// Not loaded: not ruled out (the API checks it either way).
		expect(goalNeedProblem(glycol, 'pump_npsh_available', 'P1')).toBeNull();
		const overridden: Project = {
			...glycol,
			fluid: { ...(glycol.fluid as object), overrides: { vaporPressure: 2000 } } as Project['fluid']
		};
		expect(goalNeedProblem(overridden, 'pump_npsh_available', 'P1', info)).toBeNull();
		const custom: Project = {
			...project,
			fluid: { kind: 'custom', name: 'Oil', density: 850, dynamicViscosity: 0.01 }
		};
		expect(goalNeedProblem(custom, 'pump_npsh_margin', 'P1')).toBe(
			'the fluid has no vapor pressure'
		);
	});

	it('offers the numeric allow-list values the case has, never statuses, specs or the fluid', () => {
		const choices = variableChoices(transfer());
		expect(choices.map((c) => c.label)).toEqual([
			'Transfer pump · Speed',
			'Discharge isolation valve · Resistance K',
			'Suction tank · Liquid level',
			'Suction tank · Surface pressure',
			'Discharge tank · Liquid level',
			'Discharge tank · Surface pressure',
			'Pipe 1 of Suction tank → Transfer pump · Length',
			'Pipe 1 of Transfer pump → Discharge isolation valve · Length',
			'Pipe 1 of Discharge isolation valve → Discharge tank · Length',
			'Fluid temperature'
		]);
		expect(choices.map((c) => c.field)).not.toContain('status');
		expect(choices.map((c) => c.field)).not.toContain('spec');
		expect(choices.map((c) => c.field)).not.toContain('fluid');
		expect(choices.find((c) => c.field === 'resistance')?.coefficient).toBe('K');
		// Flow control adds its setpoint, and the speed is the maximum speed.
		const fields = variableChoices(controlled()).filter((c) => c.group === 'pump');
		expect(fields.map((c) => c.label)).toEqual([
			'Transfer pump · Maximum speed',
			'Transfer pump · Flow setpoint'
		]);
		// A valve holding a Cv varies it as a Cv.
		const cv = edited(
			transfer(),
			'V1',
			(c) => ({ ...c, resistance: { kind: 'Cv', value: 120 } }) as Component
		);
		expect(variableChoices(cv).find((c) => c.field === 'resistance')?.coefficient).toBe('Cv');
	});

	it('gives a setpoint the unit of its valve type, and a custom fluid no temperature', () => {
		const target = { target: V1, field: 'setpoint' };
		expect(variableSpec(controlValve('fcv', 0.004), target)).toEqual({
			category: 'flow',
			options: {}
		});
		expect(variableSpec(controlValve('prv', 300000), target)).toEqual({
			category: 'pressure',
			options: { gauge: true }
		});
		expect(variableChoices(controlValve('psv', 0)).map((c) => c.label)).toContain(
			'Discharge isolation valve · Inlet pressure setpoint'
		);
		const custom: Project = {
			...transfer(),
			fluid: { kind: 'custom', name: 'Oil', density: 850, dynamicViscosity: 0.01 }
		};
		expect(variableChoices(custom).map((c) => c.field)).not.toContain('fluid.temperature');
		// A scenario that sets a built-in fluid offers its temperature where the base has none.
		const scenario = withScenarios(custom, [
			{
				id: 'S1',
				name: 'Water',
				overrides: [
					{
						kind: 'project',
						field: 'fluid',
						value: { kind: 'builtin', fluidId: 'water', temperature: 290 }
					}
				]
			}
		]);
		expect(variableChoices(caseProject(scenario, 'S1')).map((c) => c.field)).toContain(
			'fluid.temperature'
		);
	});
});

describe('default bounds (§6.6)', () => {
	const bounds = (project: Project, target: VariableDraft['target'], field: string, context = {}) =>
		defaultBounds(
			project,
			{ target, field, ...(field === 'resistance' ? { coefficient: 'K' as const } : {}) },
			context
		);

	it('pump speed: 20 % to 100 %; a controlled pump strictly above its minimum speed', () => {
		expect(bounds(transfer(), P1, 'speed')).toEqual({ lower: 0.2, upper: 1 });
		expect(bounds(controlled(0.5), P1, 'speed')).toEqual({ lower: 0.51, upper: 1 });
		expect(bounds(controlled(0.505), P1, 'speed')).toEqual({ lower: 0.51, upper: 1 });
		expect(bounds(controlled(0.29), P1, 'speed')).toEqual({ lower: 0.3, upper: 1 });
		// 99 % or more: halfway to 100 %, below the upper bound.
		const high = bounds(controlled(0.995), P1, 'speed');
		expect(high.lower).toBeCloseTo(0.9975, 12);
		expect(high.lower).toBeGreaterThan(0.995);
		expect(high.lower).toBeLessThan(high.upper);
		// The From field refuses the minimum speed itself (x-ordered-fields on Pump).
		const variable = newVariable(controlled(0.5), { target: P1, field: 'speed' });
		expect(
			boundsProblem(0.5, variableBounds(controlled(0.5), variable).lower, String)
		).not.toBeNull();
	});

	it('setpoints, pressures, levels, flows, lengths', () => {
		expect(bounds(controlled(0.5, 0.01), P1, 'control.setpoint')).toEqual({
			lower: 0.001,
			upper: 0.03
		});
		expect(bounds(controlValve('fcv', 0.004), V1, 'setpoint')).toEqual({ lower: 0, upper: 0.012 });
		expect(bounds(controlValve('fcv', 0), V1, 'setpoint')).toEqual({ lower: 0, upper: 0.01 });
		expect(bounds(controlValve('prv', 300000), V1, 'setpoint')).toEqual({
			lower: 0,
			upper: 800000
		});
		expect(bounds(controlValve('psv', 700000), V1, 'setpoint')).toEqual({
			lower: 200000,
			upper: 1200000
		});
		expect(bounds(transfer(), R1, 'surfacePressure')).toEqual({ lower: 0, upper: 500000 });
		// A vacuum stays a vacuum below, clipped to the field's minimum (−1 bar(g)).
		const vacuum = edited(
			transfer(),
			'R1',
			(c) => ({ ...c, surfacePressure: -50000 }) as Component
		);
		expect(bounds(vacuum, R1, 'surfacePressure')).toEqual({ lower: -100000, upper: 450000 });
		expect(bounds(transfer(), R1, 'liquidLevel')).toEqual({ lower: 0, upper: 23 });
		const deep = edited(transfer(), 'R1', (c) => ({ ...c, liquidLevel: 990 }) as Component);
		expect(bounds(deep, R1, 'liquidLevel')).toEqual({ lower: 0, upper: 1000 });
		const pipe = { kind: 'pipe', connectionId: 'L3', pipeIndex: 0 } as const;
		expect(bounds(transfer(), pipe, 'length')).toEqual({ lower: 6, upper: 600 });
	});

	it('assigned flows: a demand, a supply and zero', () => {
		const assigned = (flow: number): Project => ({
			...transfer(),
			components: [
				...transfer().components,
				{
					type: 'assigned_flow',
					id: 'AF1',
					name: 'User',
					elevation: 0,
					flow,
					ports: [{ id: 'port_1', nominalSize: 0.1 }]
				} as Component
			]
		});
		const af = { kind: 'component', componentId: 'AF1' } as const;
		expect(bounds(assigned(0.004), af, 'flow')).toEqual({ lower: 0, upper: 0.012 });
		expect(bounds(assigned(-0.004), af, 'flow')).toEqual({ lower: -0.012, upper: 0 });
		expect(bounds(assigned(0), af, 'flow')).toEqual({ lower: 0, upper: 0.01 });
	});

	it('temperature: the fluid range 1 K inside each end, else ±20 K around the value', () => {
		const project = transfer();
		const fluid = { kind: 'project' } as const;
		expect(bounds(project, fluid, 'fluid.temperature')).toEqual({ lower: 273.15, upper: 313.15 });
		const water = {
			temperatureRange: { min: 273.16, max: 473.15, unit: 'K' },
			freezingPoints: null
		} as unknown as FluidInfo;
		const range = bounds(project, fluid, 'fluid.temperature', { fluid: water });
		expect(range.lower).toBeCloseTo(274.16, 9);
		expect(range.upper).toBeCloseTo(472.15, 9);
		// A glycol: above the freezing point at its concentration (the higher tabulated neighbour).
		const glycol: Project = {
			...project,
			fluid: { kind: 'builtin', fluidId: 'propylene_glycol', temperature: 280, concentration: 0.3 }
		};
		const info = {
			temperatureRange: { min: 230, max: 400, unit: 'K' },
			freezingPoints: [
				{ concentration: 0.2, temperature: 265 },
				{ concentration: 0.4, temperature: 252 }
			]
		} as unknown as FluidInfo;
		expect(bounds(glycol, fluid, 'fluid.temperature', { fluid: info })).toEqual({
			lower: 266,
			upper: 399
		});
	});

	it("resistance: around the valve's own value, the Crane default's K, or 0.01 to 100", () => {
		// A gate valve on its Crane default: centred (geometrically) on the last solve's K.
		const centred = bounds(transfer(), V1, 'resistance', { kOpen: 0.14 });
		expect(centred.lower).toBeCloseTo(0.0014, 15);
		expect(centred.upper).toBeCloseTo(14, 12);
		expect(Math.sqrt(centred.lower * centred.upper)).toBeCloseTo(0.14, 12);
		expect(bounds(transfer(), V1, 'resistance')).toEqual({ lower: 0.01, upper: 100 });
		// An ideal control valve (K = 0 when fully open): 0.01 to 100.
		expect(bounds(controlValve('fcv', 0.004), V1, 'resistance', { kOpen: 0 })).toEqual({
			lower: 0.01,
			upper: 100
		});
		const cv = edited(
			transfer(),
			'V1',
			(c) => ({ ...c, resistance: { kind: 'Cv', value: 120 } }) as Component
		);
		expect(defaultBounds(cv, { target: V1, field: 'resistance', coefficient: 'Cv' })).toEqual({
			lower: 1.2,
			upper: 12000
		});
	});

	it('says the case value now, by the valve default, a scenario and the bounds', () => {
		const prefs = SI_UNITS;
		const ideal = controlValve('fcv', 0.004);
		const variable = newVariable(
			ideal,
			{ target: V1, field: 'resistance', coefficient: 'K' },
			{ kOpen: 0 }
		);
		expect(nowText(ideal, variable, { prefs, kOpen: 0 })).toBe(
			'Now ideal (K = 0, no loss when fully open); the search starts at the middle of the bounds'
		);
		const gate = newVariable(
			transfer(),
			{ target: V1, field: 'resistance', coefficient: 'K' },
			{ kOpen: 0.14 }
		);
		expect(nowText(transfer(), gate, { prefs, kOpen: 0.14 })).toBe(
			'Now default (Crane K 0.14 at the connected diameter); the search starts at the middle of the bounds'
		);
		const speed = speedVariable();
		expect(nowText(transfer(), speed, { prefs })).toBe('Now 100 %');
		const narrow = { ...speed, upper: 0.9 };
		expect(nowText(transfer(), narrow, { prefs })).toBe(
			'Now 100 %, outside the bounds: the search starts at the nearer bound'
		);
		const slower: Override = { kind: 'component', componentId: 'P1', field: 'speed', value: 0.9 };
		const winter = withScenarios(transfer(), [{ id: 'S1', name: 'Winter', overrides: [slower] }]);
		expect(
			nowText(caseProject(winter, 'S1'), speed, { prefs, scenario: winter.scenarios![0] })
		).toBe('Now 90 % (set by Winter)');
	});
});

describe('the tolerance field (x-goal-quantities minimum)', () => {
	it('has a minimum that moves with the target, never below the published absolute minimum', () => {
		expect(minimumTolerance('link_flow', 0.015)).toBeCloseTo(1.5e-8, 20);
		expect(minimumTolerance('link_flow', 0)).toBe(1e-9);
		expect(minimumTolerance('port_pressure', 250000)).toBeCloseTo(0.25, 15);
		expect(minimumTolerance('port_pressure', 0)).toBe(0.1);
		expect(minimumTolerance('port_pressure', null)).toBe(0.1);
		for (const target of [0, 1e-3, 250000, -3e6, 1e8]) {
			const bounds = toleranceBounds('port_pressure', target);
			const min = minimumTolerance('port_pressure', target);
			// A value the field accepts is never below the API's minimum.
			for (const value of [min * 0.999, min, min * 1.001, 1]) {
				const ok = boundsProblem(value, bounds, String) === null;
				if (ok) expect(value).toBeGreaterThanOrEqual(min);
			}
			expect(boundsProblem(0, bounds, String)).not.toBeNull();
		}
	});

	it('says when a target changed after the tolerance puts it below its minimum', () => {
		const goal = {
			...newGoal({ elementId: 'P1', portId: 'discharge' }, 'port_pressure'),
			target: 1e5,
			tolerance: 0.2
		};
		expect(toleranceProblem(goal, SI_UNITS)).toBeNull();
		expect(toleranceProblem({ ...goal, target: 1e6 }, SI_UNITS)).toMatch(
			/^Below the smallest tolerance/
		);
	});

	it('words the default tolerance from the published rule', () => {
		expect(defaultToleranceText('link_flow', SI_UNITS)).toBe(
			'Default tolerance: 0.5 % of the target, at least 0.001 L/s.'
		);
		expect(defaultToleranceText('port_pressure', SI_UNITS)).toBe(
			'Default tolerance: 0.5 % of the target, at least 0.01 m of head.'
		);
		expect(defaultToleranceText('link_velocity', SI_UNITS)).toBe(
			'Default tolerance: 0.5 % of the target, at least 0.001 m/s.'
		);
	});
});

describe('lapses (§6.4, §6.5)', () => {
	it('a deleted element or port lapses; a rename does not', () => {
		const goal = { ...newGoal({ elementId: 'V1', portId: 'outlet' }, 'port_pressure'), target: 1 };
		expect(goalLapse(transfer(), goal)).toBeNull();
		const renamed = edited(transfer(), 'V1', (c) => ({ ...c, name: 'Main valve' }));
		expect(goalLapse(renamed, goal)).toBeNull();
		const deleted = deleteComponent(transfer(), 'V1', { join: true });
		expect(goalLapse(deleted, goal)).toBe('V1 (deleted): no longer exists');
		expect(goalLapse(deleted, { ...flowGoal(), elementId: 'L2' })).toBeNull();
		expect(goalLapse(deleted, { ...flowGoal(), elementId: 'L3' })).toBe(
			'L3 (deleted): no longer exists'
		);
	});

	it('flow control removed, the fluid made custom, a valve no longer a control valve', () => {
		const setpoint = newVariable(controlled(), { target: P1, field: 'control.setpoint' });
		expect(variableLapse(controlled(), setpoint)).toBeNull();
		expect(variableLapse(transfer(), setpoint)).toBe('Transfer pump has no flow control');
		const temperature = newVariable(transfer(), {
			target: { kind: 'project' },
			field: 'fluid.temperature'
		});
		const custom: Project = {
			...transfer(),
			fluid: { kind: 'custom', name: 'Oil', density: 850, dynamicViscosity: 0.01 }
		};
		expect(variableLapse(custom, temperature)).toBe('the fluid is a custom fluid');
		const prv = newVariable(controlValve('prv', 3e5), { target: V1, field: 'setpoint' });
		expect(variableLapse(controlValve('prv', 3e5), prv)).toBeNull();
		expect(variableLapse(transfer(), prv)).toMatch(/^Discharge isolation valve has no/);
		expect(variableLapse(controlValve('fcv', 0.004), prv)).toMatch(/changed type/);
		expect(variableLapse(deleteComponent(transfer(), 'P1', { join: true }), speedVariable())).toBe(
			'P1 (deleted): no longer exists'
		);
	});

	it("a pipe variable lapses when its connection's pipes or ends change, not on a rename", () => {
		const length = newVariable(transfer(), {
			target: { kind: 'pipe', connectionId: 'L3', pipeIndex: 0 },
			field: 'length'
		});
		expect(variableLapse(transfer(), length)).toBeNull();
		const added = updateConnection(transfer(), 'L3', (c) => ({ ...c, piping: addPipe(c.piping) }));
		expect(variableLapse(added, length)).toBe(
			'The pipes of Discharge isolation valve → Discharge tank changed since you chose Pipe 1; choose it again.'
		);
		const back = updateConnection(added, 'L3', (c) => ({ ...c, piping: removePipe(c.piping, 1) }));
		expect(variableLapse(back, length)).toBeNull();
		// A join merges L2 into L3's place: L2 keeps its id with other pipes and ends.
		const l2 = newVariable(transfer(), {
			target: { kind: 'pipe', connectionId: 'L2', pipeIndex: 0 },
			field: 'length'
		});
		const joined = deleteComponent(transfer(), 'V1', { join: true });
		expect(variableLapse(joined, l2)).toMatch(
			/^The pipes of Transfer pump → Discharge tank changed/
		);
		expect(
			variableLapse(
				edited(transfer(), 'R2', (c) => ({ ...c, name: 'Top tank' })),
				length
			)
		).toBeNull();
		// An insertion into a connection drawn against the flow turns it around: other ends.
		const drawn = transfer();
		const against: Project = {
			...drawn,
			connections: drawn.connections.map((c) =>
				c.id === 'L1'
					? {
							...c,
							fromComponentId: 'P1',
							fromPortId: 'suction',
							toComponentId: 'R1',
							toPortId: 'port_1'
						}
					: c
			)
		};
		const suction = newVariable(against, {
			target: { kind: 'pipe', connectionId: 'L1', pipeIndex: 0 },
			field: 'length'
		});
		const gate = createComponent('gate', against);
		const inserted = insertComponentInConnection(against, 'L1', gate);
		expect(variableLapse(inserted, suction)).toMatch(
			/^The pipes of Suction tank → Gate valve V2 changed/
		);
	});
});

describe("Run's reasons (§6.8) and the request", () => {
	it('gives every reason, in order', () => {
		const project = transfer();
		const prefs = SI_UNITS;
		expect(runProblems(EMPTY_SETUP, { ...project, components: [] }, null, prefs)[0]).toBe(
			'Add a component to the network first.'
		);
		expect(runProblems(EMPTY_SETUP, project, null, prefs)).toEqual([
			'Add at least one goal and one variable.'
		]);
		const two = {
			goals: [flowGoal(), { ...newGoal({ elementId: 'P1' }, 'pump_head'), target: 20 }],
			variables: [speedVariable()]
		};
		expect(runProblems(two, project, null, prefs)).toEqual([
			'Goal seek needs as many goals as variables: 2 goals, 1 variable.'
		]);
		const noTarget = { ...oneByOne(), goals: [flowGoal(null)] };
		expect(runProblems(noTarget, project, null, prefs)).toEqual(['Enter a target for each goal.']);
		const deleted = deleteComponent(project, 'P1', { join: true });
		expect(runProblems(oneByOne(), deleted, null, prefs)).toEqual([
			'Remove the goals and variables that no longer apply.'
		]);
		const disordered = {
			...oneByOne(),
			variables: [{ ...speedVariable(), lower: 0.9, upper: 0.5 }]
		};
		expect(runProblems(disordered, project, null, prefs)).toEqual([
			'Each variable needs its From value below its To value.'
		]);
		expect(runProblems(oneByOne(), project, 'solve', prefs)).toEqual([
			'A solve is running; wait for it or cancel it.'
		]);
		expect(runProblems(oneByOne(), project, null, prefs)).toEqual([]);
	});

	it('says why each kind of control waits while something else runs', () => {
		expect(calculatingReason(null, 'solve')).toBe('');
		expect(calculatingReason('goalSeek', 'solve')).toBe(
			'A goal seek is running; Cancel in the header stops it.'
		);
		expect(calculatingReason('goalSeek', 'solve', true)).toBe(
			'A goal seek is running; Cancel stops it.'
		);
		expect(calculatingReason('solveAll', 'goalSeek')).toBe(
			'A solve is running; wait for it or cancel it.'
		);
		// Export (proposal export.md §5.2): never from results about to be replaced.
		expect(calculatingReason(null, 'export', true)).toBe('');
		expect(calculatingReason('solve', 'export', true)).toBe(
			'A solve is running; export when it finishes, or Cancel stops it.'
		);
		expect(calculatingReason('solveAll', 'export', true)).toBe(
			'Solve all is running; export when it finishes, or Cancel stops it.'
		);
		expect(calculatingReason('goalSeek', 'export')).toBe(
			'A goal seek is running; export when it finishes, or Cancel in the header stops it.'
		);
	});

	it('marks a goal or variable already chosen, by the published uniqueBy keys', () => {
		const setup = oneByOne();
		expect(hasGoal(setup, { quantity: 'link_flow', elementId: 'L2' })).toBe(true);
		expect(hasGoal(setup, { quantity: 'link_velocity', elementId: 'L2' })).toBe(false);
		expect(hasVariable(setup, { target: P1, field: 'speed' })).toBe(true);
		expect(hasVariable(setup, { target: P1, field: 'control.setpoint' })).toBe(false);
		expect(
			hasVariable(setup, {
				target: { kind: 'pipe', connectionId: 'L2', pipeIndex: 0 },
				field: 'length'
			})
		).toBe(false);
	});

	it('sends SI values, the coefficient, the scenario only for a scenario, in a stable key order', () => {
		const resistance = newVariable(transfer(), {
			target: V1,
			field: 'resistance',
			coefficient: 'K'
		});
		const setup: GoalSeekSetup = {
			goals: [
				flowGoal(),
				{
					...newGoal({ elementId: 'V1', portId: 'outlet' }, 'port_pressure'),
					target: 150000,
					tolerance: 500
				}
			],
			variables: [speedVariable(), resistance]
		};
		const base = toRequest(setup, transfer(), null);
		expect(Object.keys(base)).toEqual(['project', 'variables', 'goals']);
		expect(base.variables).toEqual([
			{ kind: 'component', componentId: 'P1', field: 'speed', lower: 0.2, upper: 1 },
			{
				kind: 'component',
				componentId: 'V1',
				field: 'resistance',
				coefficient: 'K',
				lower: 0.01,
				upper: 100
			}
		]);
		expect(base.goals).toEqual([
			{ quantity: 'link_flow', elementId: 'L2', target: 0.015 },
			{
				quantity: 'port_pressure',
				elementId: 'V1',
				portId: 'outlet',
				target: 150000,
				tolerance: 500
			}
		]);
		expect(Object.keys(base.variables[1]!)).toEqual([
			'kind',
			'componentId',
			'field',
			'coefficient',
			'lower',
			'upper'
		]);
		const scenario = toRequest(setup, transfer(), 'S1');
		expect(Object.keys(scenario)).toEqual(['project', 'scenarioId', 'variables', 'goals']);
		const pipe = toRequest(
			{
				goals: [flowGoal()],
				variables: [
					newVariable(transfer(), {
						target: { kind: 'pipe', connectionId: 'L3', pipeIndex: 0 },
						field: 'length'
					})
				]
			},
			transfer(),
			null
		);
		expect(pipe.variables).toEqual([
			{ kind: 'pipe', connectionId: 'L3', pipeIndex: 0, field: 'length', lower: 6, upper: 600 }
		]);
	});

	it('names the ids the setup reserves', () => {
		expect(reservedIds({ goals: [flowGoal()], variables: [speedVariable()] }).sort()).toEqual([
			'L2',
			'P1'
		]);
	});
});

describe('words (§6.9)', () => {
	const met = goalSeekResponse();

	it("names a valve's resistance by its coefficient once: 'resistance Cv 18.2346', never 'cv Cv'", () => {
		// A made-up value, only formatted here.
		for (const [kind, value, text] of [
			['Cv', 18.2346, 'Cv 18.2346'],
			['K', 0.5, 'K 0.5']
		] as const) {
			const override: Override = {
				kind: 'component',
				componentId: 'V1',
				field: 'resistance',
				value: { kind, value }
			};
			const response = goalSeekResponse({
				variables: [
					{
						...goalSeekResponse().result.variables[0]!,
						variable: {
							kind: 'component',
							componentId: 'V1',
							field: 'resistance',
							coefficient: kind,
							lower: value / 10,
							upper: value * 10
						},
						label: `resistance of valve V1 (${kind})`,
						scale: 'log',
						value,
						override
					}
				]
			});
			const context = { labels: transfer(), sent: transfer(), prefs: SI_UNITS, caseId: null };
			const expected = [`Discharge isolation valve resistance ${text}`];
			expect(foundValueTexts(response, context), kind).toEqual(expected);
			expect(foundValueTexts(response, { ...context, prefs: IMPERIAL_UNITS }), kind).toEqual(
				expected
			);
			expect(variableLabelOf(transfer(), override), kind).toBe(
				`Discharge isolation valve resistance ${kind}`
			);
		}
	});

	it('words a met run, met at the start and stopped early but met', () => {
		expect(outcomeText(met, words(), request())).toEqual({
			tone: 'met',
			title: 'Goal met',
			text: '3 trial solves in 0.4 s on the base case.'
		});
		const start = goalSeekResponse({ stopReason: 'met_at_start' });
		expect(outcomeText(start, words(), request()).text).toBe(
			'The case already meets every goal: nothing to change.'
		);
		const early = goalSeekResponse({ stopReason: 'time_budget' });
		expect(outcomeText(early, words(), request()).text).toContain(
			'Stopped early, but every result is within its tolerance.'
		);
	});

	const notMet = (
		stopReason: GoalSeekResponse['result']['stopReason'],
		notes: GoalSeekNote[] = [],
		extra = {}
	) =>
		goalSeekResponse({
			met: false,
			stopReason,
			message: "The API's sentence.",
			goals: [{ ...met.result.goals[0]!, met: false, value: 0.019, residual: 0.004 }],
			notes,
			...extra
		});
	const note = (code: GoalSeekNote['code'], data: Partial<GoalSeekNote> = {}): GoalSeekNote => ({
		code,
		message: `The API's ${code} sentence.`,
		variables: [0],
		goals: [0],
		evaluations: [],
		variableValues: [],
		goalValues: [],
		stateChanges: [],
		...data
	});

	it('words every way a run ends without meeting its goals', () => {
		const project = transfer();
		const at = notMet(
			'not_reachable',
			[note('closest_at_bound', { variableValues: [1], goalValues: [0.019] })],
			{
				variables: [{ ...met.result.variables[0]!, value: 1, atBound: 'upper' }]
			}
		);
		const atBound = outcomeText(at, words(project), request(project));
		expect(atBound.title).toBe('Goal not met');
		expect(atBound.text).toBe(
			'None of the 3 trial values of Transfer pump · Speed from 20 % to 100 % reaches 15 L/s for Transfer pump → Discharge isolation valve · Flow: the results never cross it between them. The closest, 19 L/s, is at Transfer pump · Speed 100 % (at the upper bound). A narrow crossing between two trial values is possible; narrow the bounds to look closer, widen them, or change another input. You can still apply the closest value.'
		);
		const plateau = notMet(
			'not_reachable',
			[note('closest_on_plateau', { variableValues: [0.2, 0.4], goalValues: [0] })],
			{ variables: [{ ...met.result.variables[0]!, value: 0.4, atBound: null }] }
		);
		expect(outcomeText(plateau, words(), request()).text).toContain('where results do not change');
		const inside = notMet(
			'not_reachable',
			[note('closest_inside', { variableValues: [0.7], goalValues: [0.013] })],
			{ variables: [{ ...met.result.variables[0]!, value: 0.7, atBound: null }] }
		);
		expect(outcomeText(inside, words(), request()).text).toContain(
			'is at Transfer pump · Speed 70 % (inside the bounds)'
		);
		const jump = notMet('jump', [
			note('jump', {
				variableValues: [0.31, 0.3100000001],
				goalValues: [0.012, 0.018],
				stateChanges: [{ elementId: 'V1', aspect: 'valve_state', before: 'closed', after: 'open' }]
			})
		]);
		// A bracket closed to 10⁻¹⁰ of the range: its ends get the digits that tell them apart.
		expect(outcomeText(jump, words(), request()).text).toBe(
			'Transfer pump → Discharge isolation valve · Flow jumps from 12 L/s to 18 L/s between Transfer pump · Speed 31 % and 31.00000001 % (Discharge isolation valve: open (was closed)), so no value there gives 15 L/s. The closest value found is shown.'
		);

		const unsolved = notMet(
			'unsolved_crossing',
			[note('unsolved_crossing', { variableValues: [0.5, 0.6], evaluations: [1] })],
			{
				evaluations: [
					met.result.evaluations[0]!,
					{
						...met.result.evaluations[1]!,
						outcome: 'not_converged',
						goalValues: [null],
						residuals: [null],
						message: 'x'
					}
				]
			}
		);
		expect(outcomeText(unsolved, words(), request()).text).toBe(
			'Transfer pump → Discharge isolation valve · Flow crosses 15 L/s only between Transfer pump · Speed 50 % and 60 %, where the network has no solution (Did not converge).'
		);
		const progress = notMet('no_progress');
		expect(outcomeText(progress, words(), request()).text).toBe(
			'The closest point found misses Transfer pump → Discharge isolation valve · Flow by +4 L/s (tolerance ±0.075 L/s).'
		);
		expect(outcomeText(notMet('evaluation_limit'), words(), request()).text).toBe(
			'Stopped after 3 trial solves, the most one goal seek makes. The best point found is shown.'
		);
		expect(outcomeText(notMet('time_budget'), words(), request()).text).toBe(
			'Stopped after 0.4 s, the time one request may take, with 3 trial solves. The best point found is shown.'
		);
		const none = notMet('no_usable_evaluation', [], {
			evaluations: [
				{
					...met.result.evaluations[0]!,
					outcome: 'topology_error',
					message: 'the setpoint is unreachable'
				}
			]
		});
		expect(outcomeText(none, words(), request())).toEqual({
			tone: 'failed',
			title: 'No result',
			text: "No trial solve gave a result: Rejected: the setpoint is unreachable. Narrow the bounds, or check the case's own solve."
		});
		// A stop reason the app does not know shows the API's sentence.
		const unknown = notMet('future_reason' as never);
		expect(outcomeText(unknown, words(), request()).text).toBe("The API's sentence.");
	});

	it('words every note from its code and data; an unknown code shows the API sentence', () => {
		const ctx = words();
		const req = request();
		const text = (n: GoalSeekNote, response = met) => noteText(n, response, ctx, req);
		expect(text(note('other_crossing', { variableValues: [0.31, 0.35] }))).toBe(
			'Another value may also meet Transfer pump → Discharge isolation valve · Flow: the results crossed the target again between Transfer pump · Speed 31 % and 35 %. Narrow the bounds there to find it.'
		);
		expect(text(note('met_range', { evaluations: [1, 2], variableValues: [0.8, 0.9] }))).toMatch(
			/^2 of the values of Transfer pump · Speed tried at the start and across the bounds, from 80 % to 90 %, meet the goals/
		);
		expect(text(note('met_without_crossing'))).toMatch(
			/is met at a value where the results do not cross/
		);
		expect(text(note('closest_at_bound', { variableValues: [1], goalValues: [0.019] }))).toBe(
			'The closest Transfer pump → Discharge isolation valve · Flow found is 19 L/s, at Transfer pump · Speed 100 %, a bound.'
		);
		expect(
			text(note('closest_on_plateau', { variableValues: [0.2, 0.4], goalValues: [0] }))
		).toMatch(/where the results do not change/);
		expect(text(note('closest_inside', { variableValues: [0.7], goalValues: [0.013] }))).toMatch(
			/at Transfer pump · Speed 70 %\.$/
		);
		expect(text(note('jump', { variableValues: [0.3, 0.31], goalValues: [0.01, 0.02] }))).toMatch(
			/jumps across its target between/
		);
		expect(
			text(note('unsolved_crossing', { variableValues: [0.3, 0.31], evaluations: [0] }))
		).toMatch(/\(Yes\)\.$/);
		expect(
			text(
				note('state_changes', {
					stateChanges: [
						{ elementId: 'P1', aspect: 'pump_status', before: 'running', after: 'no_flow' }
					]
				})
			)
		).toBe('At the values found: Transfer pump: no flow (was running).');
		expect(text(note('start_clipped', { variableValues: [1.2] }))).toBe(
			"Transfer pump · Speed: the case's value 120 % lies outside the bounds; the search started at the upper bound."
		);
		expect(text(note('unusable_evaluations', { evaluations: [1] }))).toBe(
			'1 of 3 trial solves gave no result (the first, trial 2: Yes); the search went around them.'
		);

		expect(text(note('goal_no_effect'))).toMatch(/did not change at any trial/);
		expect(text(note('variable_no_effect'))).toBe(
			'Transfer pump · Speed moves no goal near the point found.'
		);
		expect(text(note('variables_collinear'))).toMatch(/change the goals in the same proportion/);
		expect(text(note('slope_unknown'))).toBe(
			'The effect of Transfer pump · Speed near this point is unknown: its trial solves there gave no result.'
		);
		expect(text(note('sensitive'))).toMatch(
			/apply this value exactly; rounding it to 6 significant digits/
		);
		expect(text(note('a_future_code' as never))).toBe("The API's a_future_code sentence.");
	});

	it('gives both ends of a bracket the digits that tell them apart', () => {
		const text = (n: GoalSeekNote) => noteText(n, met, words(), request());
		const at = (values: number[]) =>
			text(note('unsolved_crossing', { variableValues: values, evaluations: [0] }));
		expect(at([0.02, 0.0200000001])).toMatch(
			/between Transfer pump · Speed 2 % and 2.00000001 %, where/
		);
		expect(
			text(note('jump', { variableValues: [0.31, 0.3100000001], goalValues: [0, 0] }))
		).toMatch(/between Transfer pump · Speed 31 % and 31.00000001 %, from/);
		expect(text(note('other_crossing', { variableValues: [0.31, 0.3100000001] }))).toMatch(
			/between Transfer pump · Speed 31 % and 31.00000001 %\./
		);
		// Equal ends stay at 6 digits.
		expect(text(note('other_crossing', { variableValues: [0.5, 0.5] }))).toMatch(
			/between Transfer pump · Speed 50 % and 50 %\./
		);
	});

	it('names the value reported on a plateau, not its lower end', () => {
		const plateau = notMet(
			'not_reachable',
			[note('closest_on_plateau', { variableValues: [0.2, 0.6], goalValues: [0] })],
			{ variables: [{ ...met.result.variables[0]!, value: 0.6, atBound: null }] }
		);
		expect(outcomeText(plateau, words(), request()).text).toContain(
			'The closest, 0 L/s, is at Transfer pump · Speed 60 % (on a range from 20 % to 60 % where results do not change; of its values, the one nearest the start is shown).'
		);
	});

	it('never says no value gives the target at a jump without a state change', () => {
		// The crossing may be continuous, only steeper than the search resolves: the texts say
		// what was solved.
		const steep = note('jump', { variableValues: [0.3, 0.31], goalValues: [0.012, 0.018] });
		expect(outcomeText(notMet('jump', [steep]), words(), request()).text).toBe(
			'Transfer pump → Discharge isolation valve · Flow jumps from 12 L/s to 18 L/s between Transfer pump · Speed 30 % and 31 % (no element that carries flow changes state there: the change is steeper than the search resolves); no value solved there gives 15 L/s. The closest value found is shown.'
		);
		expect(noteText(steep, met, words(), request())).toBe(
			'Transfer pump → Discharge isolation valve · Flow jumps across its target between Transfer pump · Speed 30 % and 31 %, from 12 L/s to 18 L/s (no element that carries flow changes state there: the change is steeper than the search resolves).'
		);
	});

	it("states met_range's rule for the value shown", () => {
		expect(
			noteText(
				note('met_range', { evaluations: [1, 2], variableValues: [0.8, 0.9] }),
				met,
				words(),
				request()
			)
		).toBe(
			'2 of the values of Transfer pump · Speed tried at the start and across the bounds, from 80 % to 90 %, meet the goals; of all the values tried, the one shown is the nearest the start among those within a tenth of the tolerance (or, with none, within it).'
		);
	});

	it('does not say the search went around failed trials when none was usable', () => {
		const none = notMet('no_usable_evaluation', [], { reportedEvaluation: null });
		expect(
			noteText(note('unusable_evaluations', { evaluations: [0, 1, 2] }), none, words(), request())
		).toBe('3 of 3 trial solves gave no result (the first, trial 1: Yes).');
	});

	it('shows a small difference in plain decimals, a tiny one with a power of ten', () => {
		expect(differenceText(6.9e-6)).toBe('0.0000069');
		expect(differenceText(4)).toBe('4');
		expect(differenceText(0.0432)).toBe('0.043');
		expect(differenceText(6.94e-8)).toBe('6.9×10⁻⁸');
		expect(differenceText(0)).toBe('0');
	});

	it('words why each trial was made and what it gave', () => {
		expect(
			['start', 'scan', 'root', 'probe', 'minimize', 'step', 'slope'].map((p) =>
				purposeText(p as never)
			)
		).toEqual(['Start', 'Scan', 'Root search', 'Probe', 'Closest-value search', 'Step', 'Slope']);
		expect(outcomeLabel({ outcome: 'usable', message: '' })).toBe('Yes');
		expect(outcomeLabel({ outcome: 'not_converged', message: 'm' })).toBe('Did not converge');
		expect(outcomeLabel({ outcome: 'no_value', message: 'no node result' })).toBe(
			'No value: no node result'
		);
		expect(outcomeLabel({ outcome: 'topology_error', message: 'm' })).toBe('Rejected: m');
		expect(outcomeLabel({ outcome: 'fluid_error', message: 'm' })).toBe('Rejected: m');
		expect(outcomeLabel({ outcome: 'not_computed', message: 'm' })).toBe(
			'Not computed (time budget)'
		);
		expect(
			stateChangeText(
				{ elementId: 'P1', aspect: 'pump_control', before: 'active', after: 'max_speed' },
				words()
			)
		).toBe('Transfer pump control: at maximum speed (was held)');
	});

	it("says the last solve's value of a goal, out of date or with none", () => {
		const solved = met.solvedState as SolvedState;
		const response = { success: true, computeTime: 0, solvedState: solved, scenario: null };
		expect(lastSolveText(flowGoal(), response, false, SI_UNITS)).toBe('Last solve: 15 L/s.');
		expect(lastSolveText(flowGoal(), response, true, SI_UNITS)).toBe(
			'Last solve (out of date): 15 L/s.'
		);
		expect(
			lastSolveText({ quantity: 'link_flow', elementId: 'L9' }, response, false, SI_UNITS)
		).toBe('Last solve: no value.');
		expect(lastSolveText(flowGoal(), null, false, SI_UNITS)).toBe('');
	});
});

describe('tables and the report (§6.9)', () => {
	it('lists the results reached and every trial, the reported one marked', () => {
		const response = goalSeekResponse();
		const goals = goalSeekGoalsTable(response, words(), request());
		expect(goals.columns.map((c) => c.label)).toEqual([
			'Reached',
			'Target',
			'Off by',
			'Tolerance',
			'Met'
		]);
		expect(goals.rows[0]).toMatchObject({
			name: 'Transfer pump → Discharge isolation valve · Flow',
			cells: {
				reached: '15 L/s',
				target: '15 L/s',
				offBy: '+0.0000069 L/s',
				tolerance: '±0.075 L/s (default)',
				met: 'Yes'
			}
		});
		const trials = goalSeekTrialTable(response, words(), request());
		expect(trials.columns.map((c) => [c.label, c.unit ?? ''])).toEqual([
			['Why', ''],
			['Transfer pump · Speed', '%'],
			['Transfer pump → Discharge isolation valve · Flow', 'L/s'],
			['Result', ''],
			['States', '']
		]);
		expect(trials.rows.map((r) => r.name)).toEqual(['Trial 1', 'Trial 2', 'Trial 3 (reported)']);
		expect(trials.rows[2]!.cells).toMatchObject({
			why: 'Root search',
			x0: '86.1174',
			g0: '15 L/s',
			result: 'Yes'
		});
		const failed = goalSeekResponse({
			evaluations: [
				{ ...response.result.evaluations[0]!, outcome: 'not_converged', goalValues: [null] }
			]
		});
		expect(goalSeekTrialTable(failed, words(), request()).rows[0]!.cells.g0).toBe(
			'— (Did not converge)'
		);
	});

	it('copies the case, the run, exact values, bounds, the method version and a tab-separated table', () => {
		const response = goalSeekResponse();
		const report = goalSeekReport(response, request(), {
			...words(),
			projectName: 'Pump transfer between two tanks',
			caseText: 'base case',
			startedAt: new Date(2026, 9, 25, 9, 30).getTime(),
			stale: false,
			invalidFlags: [],
			converged: true
		});
		const lines = report.split('\n');
		expect(lines.slice(0, 4)).toEqual([
			'Goal seek: Pump transfer between two tanks',
			'Case: base case',
			'Run: 2026-10-25 09:30; 3 trial solves in 0.4 s; calculation method 1.2.0',
			'Outcome: goal met. Every goal is met, after 3 evaluations.'
		]);
		expect(report).toContain(
			'  Transfer pump · Speed: 86.1174 % (stored 0.8611744213850658), was 100 %; bounds 20 % to 100 %'
		);
		expect(report).toContain('off by +0.0000069 L/s; tolerance ±0.075 L/s (default); met');
		expect(report).toContain('At the values found\n  converged, no physically invalid results');
		expect(report).toContain(
			'Trial\tWhy\tTransfer pump · Speed (%)\tTransfer pump → Discharge isolation valve · Flow (L/s)\tResult\tStates'
		);
		expect(report).toContain('Made-up reference for tests.');
		const stale = goalSeekReport(response, request(), {
			...words(),
			projectName: 'P',
			caseText: 'scenario Winter (S2)',
			startedAt: 0,
			stale: true,
			invalidFlags: ['NPSH available is below NPSH required.'],
			converged: true
		});
		expect(stale).toContain('Case: scenario Winter (S2)');
		expect(stale).toContain('Out of date: the project changed after this goal seek.');
		expect(stale).toContain('1 physically invalid result: NPSH available is below NPSH required.');
	});

	it('writes the run time from a given UTC offset, whatever the machine’s time zone (export.md §2.9)', () => {
		const response = goalSeekResponse();
		const at = (utcOffsetMinutes: number) =>
			goalSeekReport(response, request(), {
				...words(),
				projectName: 'P',
				caseText: 'base case',
				// 2026-10-25 07:30 UTC.
				startedAt: Date.UTC(2026, 9, 25, 7, 30),
				utcOffsetMinutes,
				stale: false,
				invalidFlags: [],
				converged: true
			}).split('\n')[2];
		expect(at(120)).toBe(
			'Run: 2026-10-25 09:30; 3 trial solves in 0.4 s; calculation method 1.2.0'
		);
		expect(at(-300)).toBe(
			'Run: 2026-10-25 02:30; 3 trial solves in 0.4 s; calculation method 1.2.0'
		);
		expect(at(-480)).toMatch(/^Run: 2026-10-24 23:30;/);
	});

	it("locates the server's input problems at their variable or goal", () => {
		const details = [
			'Goal seek: 2 input problem(s).',
			'body.variables.0.lower: Input should be greater than 0',
			'body.goals.0: pump_head applies to a pump, not a tee',
			'project.scenarios.0.overrides.1.value: Input should be a number'
		];
		const issues = requestIssues(details, details[0]);
		expect([...issues.variables]).toEqual([[0, ['From: Input should be greater than 0']]]);
		expect([...issues.goals]).toEqual([[0, ['pump_head applies to a pump, not a tee']]]);
		expect(issues.other).toEqual([
			'project.scenarios.0.overrides.1.value: Input should be a number'
		]);
		const byRow = rowIssues(request(), details, details[0]);
		expect(Object.keys(byRow).sort()).toEqual([
			'g:link_flow\u0000L2\u0000',
			'v:component:P1\u0000speed'
		]);
	});

	it('tells the lines that quote an id or an SI value with names and display units', () => {
		// The API's wording (services/goal_seek.py, services/scenarios.py) for made-up requests.
		const details = [
			'Goal seek: 4 input problem(s).',
			"body.goals.0: component V1 has no port 'port_9'",
			'body.variables.0: connection L2 has 1 pipe, no pipe 3',
			'body.goals.1: link_flow applies to a connection, not a pump',
			"body.goals.2.tolerance: below the smallest this search resolves (10⁻⁶ of the target's magnitude, or 1e-09 m³/s, whichever is larger)",
			"body.goals.3.tolerance: below the smallest this search resolves (10⁻⁶ of the target's magnitude, or 0.1 Pa, whichever is larger)",
			// Elements the project does not have keep their ids; other lines stay as they are.
			'body.goals.4: the project has no component X9',
			'body.variables.1: connection L9 has 1 pipe, no pipe 3',
			'body.variables.2.lower: Input should be greater than 0'
		];
		const context = { project: transfer(), units: IMPERIAL_UNITS };
		const issues = requestIssues(details, details[0], context);
		const GPM = (231 * 0.0254 ** 3) / 60;
		const PSI = (0.45359237 * 9.80665) / 0.0254 ** 2;
		// Values below 10⁻⁴ are shown with an exponent, 6 significant digits (as the dialog's own).
		expect((1e-9 / GPM).toExponential(5)).toBe('1.58503e-5');
		expect([...issues.goals]).toEqual([
			[0, ['Discharge isolation valve has no port “port_9”']],
			[1, ['Flow applies to a connection, not a pump']],
			[
				2,
				[
					`tolerance: below the smallest this search resolves (10⁻⁶ of the target's magnitude, or ${(1e-9 / GPM).toExponential(5)} gpm, whichever is larger)`
				]
			],
			[
				3,
				[
					`tolerance: below the smallest this search resolves (10⁻⁶ of the target's magnitude, or ${(0.1 / PSI).toExponential(5)} psi, whichever is larger)`
				]
			],
			[4, ['the project has no component X9']]
		]);
		expect([...issues.variables]).toEqual([
			[0, ['Piping Transfer pump → Discharge isolation valve has 1 pipe, no pipe 3']],
			[1, ['connection L9 has 1 pipe, no pipe 3']],
			[2, ['From: Input should be greater than 0']]
		]);
		// Without the context, every line as the server wrote it.
		expect(requestIssues(details, details[0]).goals.get(0)).toEqual([
			"component V1 has no port 'port_9'"
		]);
		expect(requestLineText('an unknown_quantity applies to a pump, not a tee', context)).toBe(
			'an unknown_quantity applies to a pump, not a tee'
		);
		const byRow = rowIssues(request(), details, details[0], context);
		expect(byRow['v:component:P1\u0000speed']).toBe(
			'Piping Transfer pump → Discharge isolation valve has 1 pipe, no pipe 3'
		);
	});
});

describe('Apply (§6.10)', () => {
	const speed: Override = {
		kind: 'component',
		componentId: 'P1',
		field: 'speed',
		value: 0.8611744213850658
	};
	const level6: Override = { kind: 'component', componentId: 'R2', field: 'liquidLevel', value: 6 };

	it('writes the exact floats into the base, or upserts them into the scenario it ran on', () => {
		const base = applyToCase(transfer(), null, [speed]);
		expect((base.components.find((c) => c.id === 'P1') as { speed: number }).speed).toBe(
			0.8611744213850658
		);
		const winter = withScenarios(transfer(), [
			{ id: 'S1', name: 'Winter', overrides: [level6, { ...speed, value: 0.9 }] }
		]);
		const scenario = applyToCase(winter, 'S1', [speed]);
		expect(scenario.scenarios![0]!.overrides).toEqual([level6, speed]);
		expect((scenario.components.find((c) => c.id === 'P1') as { speed: number }).speed).toBe(1);
		// A value equal to the base's removes the change.
		const same = applyToCase(winter, 'S1', [{ ...speed, value: 1 }]);
		expect(same.scenarios![0]!.overrides).toEqual([level6]);
		// A whole-fluid override replaces the scenario's fluid change.
		const glycol = {
			kind: 'builtin',
			fluidId: 'propylene_glycol',
			temperature: 280,
			concentration: 0.3
		};
		const fluid = withScenarios(transfer(), [
			{ id: 'S1', name: 'Glycol', overrides: [{ kind: 'project', field: 'fluid', value: glycol }] }
		]);
		const warmer = applyToCase(fluid, 'S1', [
			{ kind: 'project', field: 'fluid', value: { ...glycol, temperature: 290.5 } }
		]);
		expect(warmer.scenarios![0]!.overrides).toEqual([
			{ kind: 'project', field: 'fluid', value: { ...glycol, temperature: 290.5 } }
		]);
	});

	it('adds a new scenario with the run case changes and the values, described, cut at 500', () => {
		const winter = withScenarios(transfer(), [{ id: 'S1', name: 'Winter', overrides: [level6] }]);
		const added = asNewScenario(winter, 'S1', [speed], 'Found.');
		expect(added).toMatchObject({ id: 'S2', name: 'Goal seek 2' });
		expect(added.project.scenarios![1]).toEqual({
			id: 'S2',
			name: 'Goal seek 2',
			description: 'Found.',
			overrides: [level6, speed]
		});
		expect(added.project.scenarios![0]!.overrides).toEqual([level6]);
		const fromBase = asNewScenario(transfer(), null, [speed], 'Found.');
		expect(fromBase.project.scenarios).toEqual([
			{ id: 'S1', name: 'Goal seek 1', description: 'Found.', overrides: [speed] }
		]);
		const response = goalSeekResponse();
		expect(newScenarioDescription(response, request(), words(), '2026-10-25')).toBe(
			'Values found by goal seek on the base case for: Transfer pump → Discharge isolation valve · Flow 15 L/s (met). 2026-10-25.'
		);
		const long = newScenarioDescription(
			response,
			request(),
			{ ...words(), caseWords: 'x'.repeat(600) },
			'd'
		);
		expect(long).toHaveLength(500);
		expect(long.endsWith('…')).toBe(true);
	});

	it('is unavailable without values, out of date, beyond 30 changes or 20 scenarios', () => {
		const response = goalSeekResponse();
		const name = (c: string | null) => c ?? 'Base case';
		const state = { caseId: null, response, stale: false };
		expect(applyProblems(transfer(), state, 'case', name)).toBeNull();
		expect(applyProblems(transfer(), state, 'new', name)).toBeNull();
		expect(applyProblems(transfer(), { ...state, response: null }, 'case', name)).toBe(
			'There are no values to apply.'
		);
		expect(applyProblems(transfer(), { ...state, stale: true }, 'case', name)).toMatch(
			/^Out of date/
		);
		const full = withScenarios(
			transfer(),
			Array.from({ length: 20 }, (_, i) => ({ id: `S${i + 1}`, name: `S${i + 1}`, overrides: [] }))
		);
		expect(applyProblems(full, state, 'new', name)).toBe('A project holds at most 20 scenarios.');
		const crowded = withScenarios(transfer(), [
			{
				id: 'S1',
				name: 'Crowded',
				overrides: Array.from({ length: 30 }, (_, i): Override => ({
					kind: 'component',
					componentId: `X${i}`,
					field: 'speed',
					value: 1
				}))
			}
		]);
		expect(
			applyProblems(crowded, { caseId: 'S1', response, stale: false }, 'case', () => 'Crowded')
		).toBe(
			'Crowded holds 30 changes; these values would add 1, more than the 30 a scenario holds. Remove a change first.'
		);
		expect(foundOverrides(response)).toEqual([response.result.variables[0]!.override]);
	});

	it('says which scenarios keep their own value of a value applied to the base', () => {
		const winter = withScenarios(transfer(), [
			{ id: 'S1', name: 'Winter', overrides: [{ ...speed, value: 0.9 }] }
		]);
		expect(keptByScenarios(winter, [speed])).toEqual([
			{ label: 'Transfer pump speed', scenarios: ['Winter'] }
		]);
		expect(keptByScenarios(transfer(), [speed])).toEqual([]);
	});
});

describe('the shared fixture (generated by the API with its real trial builder and readers)', () => {
	it('applying the values to the case they ran on gives the project the API solved', () => {
		expect(fixture.apply.length).toBeGreaterThanOrEqual(10);
		for (const item of fixture.apply) {
			const project = item.project as unknown as Project;
			const overrides = item.overrides as Override[];
			const applied = applyToCase(project, item.scenarioId, overrides);
			const solvedCase = applyScenario(applied, item.scenarioId).project;
			expect(canonicalJson(solvedCase), item.name).toBe(canonicalJson(item.trial));
		}
	});

	it("each quantity's Compare reader gives the API's goal value", () => {
		expect([...fixture.quantities].sort()).toEqual(Object.keys(GOAL_QUANTITIES).sort());
		let checked = 0;
		for (const item of fixture.goals) {
			const state = item.state as unknown as SolvedState;
			for (const g of item.goals) {
				const goal = g.goal as {
					quantity: keyof typeof GOAL_QUANTITIES;
					elementId: string;
					portId?: string;
				};
				expect(goalValue(state, goal), `${item.name}: ${goal.quantity} ${goal.elementId}`).toBe(
					g.value
				);
				checked++;
			}
		}
		expect(checked).toBeGreaterThan(11);
	});
});
