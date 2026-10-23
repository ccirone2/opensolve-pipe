import { describe, expect, it } from 'vitest';
import type { Component, Project } from '../api/types';
import { link, projectWith } from '../testing/helpers';
import { EXAMPLES } from './examples';
import { createComponent, createEmptyProject } from './factory';
import fixtureJson from './__fixtures__/schema-v1.json';
import {
	modelRuleIssues,
	modelRuleProblems,
	parseProject,
	projectProblems,
	ProjectValidationError,
	referenceProblems,
	schemaProblems
} from './validate';
import { requiredPortIds } from './model-rules';

const fixture = fixtureJson as unknown as Project;

/** A copy of example 1 (R1 → L1 → P1 → L2 → V1 → L3 → R2), modified by `edit`. */
function example(edit: (p: Project) => void = () => {}): Project {
	const project = EXAMPLES[0]!.create();
	edit(project);
	return project;
}

/** The same, as an untyped value for schema-invalid edits. */
function raw(
	edit: (p: Record<string, unknown> & { components: Record<string, unknown>[] }) => void
) {
	const project = structuredClone(EXAMPLES[0]!.create()) as unknown as Record<string, unknown> & {
		components: Record<string, unknown>[];
	};
	edit(project);
	return project;
}

describe('valid projects', () => {
	it('examples, the empty project and the schema-v1 fixture have no problems', () => {
		for (const e of EXAMPLES) expect(projectProblems(e.create()), e.slug).toEqual([]);
		expect(projectProblems(createEmptyProject())).toEqual([]);
		expect(projectProblems(fixture)).toEqual([]);
	});

	it('parseProject returns the same project', () => {
		const project = example();
		expect(parseProject(structuredClone(project))).toEqual(project);
	});
});

describe('schemaProblems', () => {
	it('reports one readable problem per mistake, naming the element', () => {
		expect(schemaProblems(raw((p) => (p.components[0]!.liquidLevel = -1)))).toEqual([
			'components[0] "R1" › liquidLevel: must be >= 0'
		]);
		expect(schemaProblems(raw((p) => delete p.components[1]!.curveId))).toEqual([
			'components[1] "P1": is missing the required field "curveId"'
		]);
		expect(schemaProblems(raw((p) => (p.components[2]!.colour = 'red')))).toEqual([
			'components[2] "V1": has an unknown field "colour"'
		]);
		expect(schemaProblems(raw((p) => (p.components[2]!.status = 'open')))).toEqual([
			'components[2] "V1" › status: must be one of "active", "isolated"'
		]);
		expect(schemaProblems(raw((p) => (p.components[0]!.elevation = '3')))).toEqual([
			'components[0] "R1" › elevation: must be of type number'
		]);
	});

	it('names nested paths, with ids where there are ids', () => {
		const problems = schemaProblems(
			raw((p) => {
				const ports = (p.components[1] as { ports: { nominalSize: number }[] }).ports;
				ports[1]!.nominalSize = 0;
			})
		);
		expect(problems).toEqual([
			'components[1] "P1" › ports[1] "discharge" › nominalSize: must be > 0'
		]);
		const piping = schemaProblems(
			raw((p) => {
				const connections = p.connections as { piping: { pipes: { length: number }[] } }[];
				connections[2]!.piping.pipes[0]!.length = -5;
			})
		);
		expect(piping).toEqual(['connections[2] "L3" › piping › pipes[0] › length: must be > 0']);
	});

	it('explains identifiers, nullable fields, whole numbers and the root', () => {
		expect(schemaProblems(raw((p) => (p.id = 'has space')))).toEqual([
			"id: must use only letters, digits, '_' or '-'"
		]);
		expect(
			schemaProblems(
				raw((p) => {
					const pipes = (p.connections as { piping: { pipes: Record<string, unknown>[] } }[])[0]!
						.piping.pipes;
					pipes[0]!.innerDiameter = -1;
				})
			)
		).toEqual(['connections[0] "L1" › piping › pipes[0] › innerDiameter: must be > 0']);
		expect(
			schemaProblems(
				raw((p) => {
					const fittings = (
						p.connections as { piping: { fittings: Record<string, unknown>[] } }[]
					)[0]!.piping.fittings;
					fittings[0]!.quantity = 1.5;
				})
			)
		).toEqual(['connections[0] "L1" › piping › fittings[0] › quantity: must be a whole number']);
		expect(schemaProblems(null)).toEqual(['project: must be of type object']);
		expect(schemaProblems({})).toContain('project: is missing the required field "schemaVersion"');
	});

	it('checks a component against the schema its type names', () => {
		// A check-valve status on an isolation valve is an isolation-valve problem.
		expect(schemaProblems(raw((p) => (p.components[2]!.status = 'locked_open')))).toEqual([
			'components[2] "V1" › status: must be one of "active", "isolated"'
		]);
		// Changing the valve family changes which fields are allowed.
		expect(schemaProblems(raw((p) => (p.components[2]!.valveType = 'prv')))).toEqual([
			'components[2] "V1": is missing the required field "setpoint"'
		]);
		expect(schemaProblems(raw((p) => (p.components[2]!.valveType = 'sluice')))).toEqual([
			'components[2] "V1": unknown component type (or branchType / valveType)'
		]);
		expect(schemaProblems(raw((p) => (p.components[0]!.type = 'tank')))).toEqual([
			'components[0] "R1": unknown component type (or branchType / valveType)'
		]);
		expect(schemaProblems(raw((p) => (p.fluid = { kind: 'gas' })))).toEqual([
			'fluid: unknown fluid kind "gas"'
		]);
		expect(
			schemaProblems(
				raw((p) => (p.fluid = { kind: 'custom', name: 'Oil', density: 850, dynamicViscosity: -1 }))
			)
		).toEqual(['fluid › dynamicViscosity: must be > 0']);
	});

	it('rejects non-finite numbers', () => {
		expect(schemaProblems(raw((p) => (p.components[0]!.elevation = Number.NaN)))).not.toEqual([]);
		expect(schemaProblems(raw((p) => (p.components[0]!.elevation = Infinity)))).not.toEqual([]);
	});
});

describe('referenceProblems', () => {
	it('finds broken port-graph references', () => {
		expect(referenceProblems(example((p) => (p.connections[0]!.toComponentId = 'P9')))).toEqual([
			'Connection "L1" (to end) refers to component "P9", which does not exist.'
		]);
		expect(referenceProblems(example((p) => (p.connections[0]!.toPortId = 'inlet')))).toEqual([
			'Connection "L1" (to end) refers to port "inlet" of component "P1", which does not exist.'
		]);
		expect(
			referenceProblems(
				example((p) => {
					p.connections[1]!.fromComponentId = 'R1';
					p.connections[1]!.fromPortId = 'port_1';
				})
			)
		).toEqual(['Port "R1:port_1" has more than one connection ("L1" and "L2"); a port takes one.']);
		expect(
			referenceProblems(
				example((p) => {
					p.connections[0]!.toComponentId = 'R1';
					p.connections[0]!.toPortId = 'port_1';
				})
			)
		).toEqual(['Connection "L1" connects port "R1:port_1" to itself.']);
	});

	it('finds duplicate ids', () => {
		expect(referenceProblems(example((p) => (p.components[3]!.id = 'R1')))).toEqual(
			expect.arrayContaining(['Component id "R1" is used more than once.'])
		);
		expect(referenceProblems(example((p) => (p.connections[1]!.id = 'L1')))).toEqual([
			'Connection id "L1" is used more than once.'
		]);
		expect(referenceProblems(example((p) => (p.components[1]!.ports[1]!.id = 'suction')))).toEqual(
			expect.arrayContaining(['Component "P1" has more than one port "suction".'])
		);
	});
});

describe('modelRuleProblems', () => {
	it('checks the port ids each component type requires', () => {
		const tee = createComponent('tee', createEmptyProject());
		tee.ports[2]!.id = 'side';
		expect(modelRuleProblems(projectWith([tee]))).toEqual([
			'Component "T1" must have ports run_inlet, run_outlet, branch (it has run_inlet, run_outlet, side).'
		]);
		const node = createComponent('reference_node', createEmptyProject());
		node.ports.push({ ...node.ports[0]!, id: 'port_2' });
		expect(modelRuleProblems(projectWith([node]))).toEqual([
			'Component "N1": a reference node has exactly one port.'
		]);
		for (const kind of ['plug', 'tee', 'wye', 'pump', 'gate', 'check', 'prv'] as const) {
			const component = createComponent(kind, createEmptyProject());
			expect([...(requiredPortIds(component) ?? [])].sort()).toEqual(
				component.ports.map((p) => p.id).sort()
			);
		}
		expect(requiredPortIds(createComponent('reservoir', createEmptyProject()))).toBeNull();
	});

	it('checks FCV setpoints, pump curves and shared ids', () => {
		const fcv = createComponent('fcv', createEmptyProject()) as Component & { setpoint: number };
		fcv.setpoint = 150;
		expect(modelRuleProblems(projectWith([fcv]))).toEqual([
			'Component "V1": an FCV setpoint is a flow between 0 and 100 m³/s.'
		]);
		expect(modelRuleProblems(example((p) => (p.pumpLibrary = [])))).toEqual([
			'Component "P1" uses pump curve "C1", which is not in the pump library.'
		]);
		expect(
			modelRuleProblems(example((p) => p.pumpLibrary.push(structuredClone(p.pumpLibrary[0]!))))
		).toEqual(['Pump curve id "C1" is used more than once.']);
		expect(modelRuleProblems(example((p) => (p.connections[0]!.id = 'R2')))).toEqual([
			'Id "R2" is used by both a component and a connection.'
		]);
		expect(
			modelRuleProblems(
				example((p) => {
					p.pumpLibrary[0]!.points[2]!.flow = 0.01;
					p.pumpLibrary[0]!.efficiencyCurve![1]!.flow = 0.001;
					p.pumpLibrary[0]!.npshrCurve![2]!.flow = 0.015;
				})
			)
		).toEqual([
			'Pump curve "C1": flows must be strictly increasing.',
			'Pump curve "C1": efficiency curve flows must be strictly increasing.',
			'Pump curve "C1": NPSHr curve flows must be strictly increasing.'
		]);
	});

	it("checks a speed-controlled pump's minimum speed is below its maximum (x-ordered-fields)", () => {
		// Made-up control values: the minimum speed equals the maximum, which the API rejects.
		const project = example((p) => {
			const pump = p.components[1] as Extract<Component, { type: 'pump' }>;
			pump.speed = 0.8;
			pump.control = { mode: 'flow', setpoint: 0.01, minSpeed: 0.8 };
		});
		expect(projectProblems(project)).toEqual([
			'Component "P1": control.minSpeed must be below speed.'
		]);
		expect(modelRuleIssues(project)).toEqual([
			{
				text: 'Component "P1": control.minSpeed must be below speed.',
				message: 'The minimum speed of Transfer pump must be below its maximum speed.',
				componentId: 'P1'
			}
		]);
		// It still opens: the rule is the API's, reported before a solve, not a broken link.
		expect(parseProject(structuredClone(project))).toEqual(project);
		const below = example((p) => {
			(p.components[1] as Extract<Component, { type: 'pump' }>).control = {
				mode: 'flow',
				setpoint: 0.01,
				minSpeed: 0.5
			};
		});
		expect(projectProblems(below)).toEqual([]);
	});

	it('checks pipe size sources and fitting parameters', () => {
		const project = example((p) => {
			const [l1, l2, l3] = p.connections as [
				Project['connections'][0],
				Project['connections'][0],
				Project['connections'][0]
			];
			l1.piping.pipes[0] = { materialId: 'custom', length: 3, innerDiameter: 0.1 };
			l2.piping.pipes[0] = { materialId: 'carbon_steel', length: 3, nominalSize: 0.0762 };
			l2.piping.fittings = [
				{ type: 'bend', quantity: 1, pipeIndex: 0, angle: 45 },
				{ type: 'custom', quantity: 1, pipeIndex: 0 }
			];
			l3.piping.fittings = [
				{ type: 'elbow_90_lr', quantity: 1, pipeIndex: 1 },
				{ type: 'reducer_sudden', quantity: 1, pipeIndex: 0 }
			];
		});
		expect(modelRuleProblems(project)).toEqual([
			'Connection "L1", pipe 1: a custom pipe needs an inner diameter and a roughness.',
			'Connection "L2", pipe 1: a library pipe needs a schedule and a nominal size (or an inner diameter).',
			'Connection "L2", fitting 1 (bend) needs radiusRatio.',
			'Connection "L2", fitting 2 (custom) needs kOverride.',
			'Connection "L3", fitting 1 (elbow_90_lr) is on pipe 2, but the connection has 1 pipe segment(s).',
			'Connection "L3", fitting 2 (reducer_sudden) is on pipe 1, but the connection has 1 pipe segment(s) and a reducer needs a following segment.'
		]);
	});
});

describe('projectProblems and parseProject', () => {
	it('reports schema problems first, then graph and rule problems', () => {
		expect(projectProblems(raw((p) => (p.components[0]!.liquidLevel = -1)))).toHaveLength(1);
		expect(projectProblems(example((p) => (p.pumpLibrary = [])))).toHaveLength(1);
		expect(
			projectProblems(
				example((p) => {
					p.pumpLibrary = [];
					p.connections[0]!.toComponentId = 'X';
				})
			)
		).toHaveLength(2);
	});

	it('throws for schema and graph problems, not for solver-level rules', () => {
		expect(() => parseProject(raw((p) => (p.components[0]!.liquidLevel = -1)))).toThrow(
			ProjectValidationError
		);
		expect(() => parseProject(example((p) => (p.connections[0]!.toComponentId = 'X')))).toThrow(
			/does not exist/
		);
		const noCurve = example((p) => (p.pumpLibrary = []));
		expect(parseProject(structuredClone(noCurve))).toEqual(noCurve);
	});

	it('fills schema defaults in place, including inside components and the fluid', () => {
		const reservoir = createComponent('reservoir', createEmptyProject());
		const project = projectWith([reservoir], [], []) as unknown as Record<string, unknown> & {
			components: Record<string, unknown>[];
			settings: Record<string, unknown>;
		};
		delete project.methodVersion;
		delete project.components[0]!.surfacePressure;
		delete (project.components[0]!.ports as Record<string, unknown>[])[0]!.direction;
		delete project.settings.siteElevation;
		project.settings.solverOptions = {};
		project.settings.units = {};
		project.fluid = {
			kind: 'builtin',
			fluidId: 'water',
			temperature: 300,
			overrides: { density: 1000 }
		};
		const parsed = parseProject(project);
		expect(parsed.methodVersion).toBe('');
		expect(parsed.components[0]).toMatchObject({ surfacePressure: 0 });
		expect(parsed.components[0]!.ports[0]!.direction).toBe('bidirectional');
		expect(parsed.settings.siteElevation).toBe(0);
		expect(parsed.settings.solverOptions).toEqual({
			frictionMethod: 'colebrook',
			maxIterations: 100,
			tolerance: 1e-9
		});
		expect(parsed.settings.units).toEqual(createEmptyProject().settings.units);
		expect(parsed.fluid).toEqual({
			kind: 'builtin',
			fluidId: 'water',
			temperature: 300,
			overrides: { density: 1000 }
		});
		expect(projectProblems(parsed)).toEqual([]);
	});

	it('fills defaults of pumps and valves', () => {
		const base = createEmptyProject();
		const pump = createComponent('pump', base) as unknown as Record<string, unknown>;
		const check = createComponent('check', base, { id: 'V1' }) as unknown as Record<
			string,
			unknown
		>;
		const wye = createComponent('wye', base) as unknown as Record<string, unknown>;
		delete pump.speed;
		delete pump.status;
		delete check.status;
		delete check.crackingPressure;
		delete wye.angle;
		delete wye.lossModel;
		const parsed = parseProject(
			projectWith([pump, check, wye] as unknown as Component[], [
				link('L1', ['P1', 'discharge'], ['V1', 'inlet'])
			])
		);
		expect(parsed.components[0]).toMatchObject({ speed: 1, status: 'on' });
		expect(parsed.components[1]).toMatchObject({ status: 'active', crackingPressure: 0 });
		expect(parsed.components[2]).toMatchObject({ angle: 45, lossModel: 'crane' });
	});
});
