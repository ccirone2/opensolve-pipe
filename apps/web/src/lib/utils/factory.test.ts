import { describe, expect, it } from 'vitest';
import { link, projectWith } from '../testing/helpers';
import { pumpTransferExample } from './examples';
import {
	COMPONENT_KINDS,
	componentKind,
	createComponent,
	createConnection,
	createEmptyProject,
	CURVE_PREFIX,
	DEFAULT_NOMINAL_SIZE,
	defaultPipe,
	defaultPiping,
	ID_PREFIX,
	KIND_LABELS,
	MissingFlowError,
	missingEntry,
	newId,
	newProjectId,
	usedIds
} from './factory';
import { INCH } from './units';
import { requiredPortIds } from './model-rules';
import { modelRuleProblems, projectProblems, schemaProblems } from './validate';

describe('createEmptyProject', () => {
	it('is valid, empty and SI', () => {
		const project = createEmptyProject();
		expect(projectProblems(project)).toEqual([]);
		expect(project.components).toEqual([]);
		expect(project.connections).toEqual([]);
		expect(project.pumpLibrary).toEqual([]);
		expect(project.schemaVersion).toBe(1);
		expect(project.methodVersion).toBe('');
		expect(project.settings.units.pressure).toBe('kPa');
		expect(project.fluid).toEqual({ kind: 'builtin', fluidId: 'water', temperature: 293.15 });
		expect(project.metadata.created).toBe(project.metadata.modified);
		expect(Date.parse(project.metadata.created)).not.toBeNaN();
	});

	it('takes an id, a name and a clock', () => {
		const project = createEmptyProject({ id: 'abc', name: 'Mine', now: '2026-02-03T04:05:06Z' });
		expect(project.id).toBe('abc');
		expect(project.metadata).toEqual({
			name: 'Mine',
			created: '2026-02-03T04:05:06Z',
			modified: '2026-02-03T04:05:06Z'
		});
	});

	it('gets a random, schema-valid id', () => {
		const ids = new Set(Array.from({ length: 50 }, () => newProjectId()));
		expect(ids.size).toBe(50);
		for (const id of ids) expect(id).toMatch(/^p[0-9a-f]{18}$/);
		expect(createEmptyProject().id).not.toBe(createEmptyProject().id);
	});
});

describe('ids', () => {
	it('are the first unused number for the prefix, across components, connections and curves', () => {
		const project = pumpTransferExample();
		expect([...usedIds(project)].sort()).toEqual(['C1', 'L1', 'L2', 'L3', 'P1', 'R1', 'R2', 'V1']);
		expect(newId(project, 'R')).toBe('R3');
		expect(newId(project, 'V')).toBe('V2');
		expect(newId(project, 'T')).toBe('T1');
		expect(newId(project, 'L')).toBe('L4');
		expect(newId(project, 'C')).toBe('C2');
		expect(newId(project, 'T', ['T1', 'T2'])).toBe('T3');
		const gap = { ...project, components: project.components.filter((c) => c.id !== 'R1') };
		expect(newId(gap, 'R')).toBe('R1');
	});

	it('use one prefix per kind of component', () => {
		const project = createEmptyProject();
		expect(createComponent('reservoir', project).id).toBe('R1');
		expect(createComponent('reference_node', project).id).toBe('N1');
		expect(createComponent('plug', project).id).toBe('PL1');
		expect(createComponent('tee', project).id).toBe('T1');
		expect(createComponent('wye', project).id).toBe('Y1');
		expect(createComponent('pump', project).id).toBe('P1');
		expect(createComponent('assigned_flow', project, { flow: 0.004 }).id).toBe('AF1');
		for (const kind of [
			'gate',
			'ball',
			'butterfly',
			'globe',
			'check',
			'stop_check',
			'prv',
			'psv',
			'fcv'
		] as const) {
			expect(createComponent(kind, project).id).toBe('V1');
			expect(ID_PREFIX[kind]).toBe('V');
		}
	});
});

describe('reserved ids (page state that names elements: goal-seek.md §6.15)', () => {
	it('a new component and its pump curve never take a reserved id', () => {
		const project = pumpTransferExample();
		expect(createComponent('gate', project, { reserved: ['V2', 'V3'] }).id).toBe('V4');
		const pump = createComponent('pump', project, { reserved: ['P2', 'C2'] });
		expect(pump.id).toBe('P3');
		expect(pump.curveId).toBe('C3');
		expect(createComponent('gate', project).id).toBe('V2');
	});
});

describe('createComponent', () => {
	it('makes every kind valid against the API schema and model rules', () => {
		const project = pumpTransferExample(); // has a pump curve
		for (const kind of COMPONENT_KINDS) {
			// An assigned-flow node's flow has no default: given here as a user enters it (made-up).
			const component = createComponent(kind, project, {
				elevation: 2.5,
				nominalSize: 3 * INCH,
				flow: -0.004
			});
			const alone = { ...project, components: [...project.components, component] };
			expect(schemaProblems(alone), kind).toEqual([]);
			// A new pump's own curve is still to be entered; nothing else is missing.
			expect(modelRuleProblems(alone), kind).toEqual(
				component.type === 'pump'
					? [
							`Component "${component.id}" uses pump curve "${component.curveId}", which is not in the pump library.`
						]
					: []
			);
			expect(componentKind(component)).toBe(kind);
			expect(component.elevation).toBe(2.5);
			expect(component.ports.every((p) => p.nominalSize === 3 * INCH)).toBe(true);
			expect(component.name).toContain(component.id);
			expect(KIND_LABELS[kind]).toBeTruthy();
			const required = requiredPortIds(component);
			if (required) expect(component.ports.map((p) => p.id).sort()).toEqual([...required].sort());
		}
	});

	it('uses defaults that leave cited data to the solver', () => {
		const project = createEmptyProject();
		expect(createComponent('reservoir', project)).toMatchObject({
			liquidLevel: 0,
			surfacePressure: 0,
			elevation: 0,
			ports: [{ id: 'port_1', nominalSize: DEFAULT_NOMINAL_SIZE, direction: 'bidirectional' }]
		});
		expect(createComponent('tee', project)).toMatchObject({ lossModel: 'crane' });
		expect(createComponent('wye', project)).toMatchObject({ lossModel: 'crane', angle: 45 });
		for (const kind of ['gate', 'check', 'prv'] as const) {
			const valve = createComponent(kind, project);
			expect(valve).not.toHaveProperty('resistance');
			expect(valve).toMatchObject({ status: 'active' });
		}
		expect(createComponent('check', project)).toMatchObject({ crackingPressure: 0 });
		expect(createComponent('fcv', project)).toMatchObject({ setpoint: 0 });
		expect(DEFAULT_NOMINAL_SIZE).toBe(4 * INCH);
	});

	it("gives a pump a curve id of its own to fill in, never another pump's curve", () => {
		// The library's curves belong to other pumps: a new pump does not take one by itself.
		const transfer = pumpTransferExample();
		expect(createComponent('pump', transfer)).toMatchObject({
			curveId: 'C2',
			speed: 1,
			status: 'on'
		});
		const project = createEmptyProject();
		const pump = createComponent('pump', project);
		expect(pump).toMatchObject({ curveId: 'C1' });
		expect(modelRuleProblems(projectWith([pump]))).toEqual([
			'Component "P1" uses pump curve "C1", which is not in the pump library.'
		]);
		// A curve id a pump refers to before the curve exists is taken too.
		const second = createComponent('pump', projectWith([pump]));
		expect(second).toMatchObject({ id: 'P2', curveId: 'C2' });
		expect(newId(projectWith([pump, second]), CURVE_PREFIX)).toBe('C3');
		const withC1 = {
			...createEmptyProject(),
			components: [createComponent('reservoir', project, { id: 'C1' })]
		};
		expect(createComponent('pump', withC1)).toMatchObject({ curveId: 'C2' });
	});

	it('makes an assigned-flow node only with the flow the user entered: it has no default', () => {
		// SDD §4.11: one port, the flow as given (m³/s, positive leaves the network). No flow is
		// cited as a default, so none is invented, not even 0. Flows are made-up inputs.
		const project = createEmptyProject();
		expect(createComponent('assigned_flow', project, { flow: -0.0125 })).toEqual({
			id: 'AF1',
			name: 'Assigned flow AF1',
			elevation: 0,
			type: 'assigned_flow',
			flow: -0.0125,
			ports: [{ id: 'port_1', nominalSize: DEFAULT_NOMINAL_SIZE, direction: 'bidirectional' }]
		});
		expect(createComponent('assigned_flow', project, { flow: 0 })).toMatchObject({ flow: 0 });
		expect(() => createComponent('assigned_flow', project)).toThrow(MissingFlowError);
		expect(() => createComponent('assigned_flow', project, { flow: Number.NaN })).toThrow(
			MissingFlowError
		);
		// Where it is added, the user is asked for it first.
		expect(missingEntry('assigned_flow', {})).toBe(
			'Enter the flow: an assigned-flow node has no default flow.'
		);
		expect(missingEntry('assigned_flow', { flow: 0 })).toBeNull();
		for (const kind of COMPONENT_KINDS.filter((k) => k !== 'assigned_flow')) {
			expect(missingEntry(kind, {}), kind).toBeNull();
		}
		expect(KIND_LABELS.assigned_flow).toBe('Assigned flow (demand or supply)');
	});

	it('takes an explicit id and name', () => {
		expect(
			createComponent('gate', createEmptyProject(), { id: 'XV-101', name: 'Isolation' })
		).toMatchObject({ id: 'XV-101', name: 'Isolation' });
	});
});

describe('pipes and connections', () => {
	it('default to carbon steel schedule 40 at the given size, 10 m', () => {
		expect(defaultPipe(0.0762)).toEqual({
			materialId: 'carbon_steel',
			schedule: '40',
			nominalSize: 0.0762,
			length: 10
		});
		expect(defaultPiping(0.0508, 1)).toEqual({ pipes: [defaultPipe(0.0508, 1)], fittings: [] });
	});

	it('create a connection with a new id', () => {
		const project = projectWith(
			[createComponent('reservoir', createEmptyProject())],
			[link('L1', ['R1', 'port_1'], ['R1', 'port_1'])]
		);
		expect(
			createConnection(
				project,
				{ componentId: 'A', portId: 'a' },
				{ componentId: 'B', portId: 'b' },
				defaultPiping(0.1)
			)
		).toEqual({
			id: 'L2',
			fromComponentId: 'A',
			fromPortId: 'a',
			toComponentId: 'B',
			toPortId: 'b',
			piping: defaultPiping(0.1)
		});
	});
});
