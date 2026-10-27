import { describe, expect, it } from 'vitest';
import type { Component, PipeConnection, Project } from '../api/types';
import { deepFreeze, enteredFor, link, projectWith, referentialIssues } from '../testing/helpers';
import {
	addBranch,
	addComponentAtPort,
	addsUpstream,
	addPort,
	canJoin,
	connectPorts,
	deleteComponent,
	disconnect,
	EditError,
	hasReservoirLoss,
	insertComponentInConnection,
	joinPlan,
	canAddPort,
	plugPort,
	removePort,
	removePumpCurve,
	reversePiping,
	setPumpCurve,
	updateComponent,
	updateConnection,
	withReservoirLosses
} from './edit';
import { closedLoopProject } from '../testing/closed-loop';
import { EXAMPLES } from './examples';
import {
	COMPONENT_KINDS,
	type ComponentKind,
	createComponent,
	createEmptyProject,
	SHORT_PIPE_LENGTH
} from './factory';
import { connectionAtPort, freePorts, inletPort, outletPort, portRole } from './graph';
import fixtureJson from './__fixtures__/schema-v1.json';
import { projectProblems } from './validate';
import { maxPorts } from './model-rules';
import openapi from '../api/openapi.json';

const fixture = fixtureJson as unknown as Project;

/**
 * Example and fixture projects, frozen so any modification of an input fails the test. The
 * condenser water example is left out: these tests try every edit at every port, and its 86
 * connections repeat the patterns of the projects here (the small closed loop stands in for it).
 */
const SOURCES: [string, () => Project][] = [
	...EXAMPLES.filter((e) => e.slug !== 'condenser-water').map(
		(e) => [e.slug, () => deepFreeze(e.create())] as [string, () => Project]
	),
	['closed-loop', () => deepFreeze(closedLoopProject())],
	['fixture', () => deepFreeze(structuredClone(fixture))]
];

const TWO_PORT_KINDS: ComponentKind[] = [
	'pump',
	'gate',
	'ball',
	'butterfly',
	'globe',
	'check',
	'stop_check',
	'prv',
	'psv',
	'fcv',
	'tee',
	'wye',
	'equipment'
];

/** Schema-valid, port graph consistent (two independent checks) and backend model rules. */
function expectValid(project: Project, context: string) {
	expect(projectProblems(project), context).toEqual([]);
	expect(referentialIssues(project), context).toEqual([]);
}

const TEST_CURVE = {
	id: 'CT',
	name: 'Test curve',
	points: [
		{ flow: 0, head: 10 },
		{ flow: 0.01, head: 8 },
		{ flow: 0.02, head: 4 }
	]
};

/**
 * The project a component of `kind` is added to: as the UI does, a pump needs a curve in the
 * library first (the factory never invents one).
 */
function readyFor(kind: ComponentKind, project: Project): Project {
	return kind === 'pump' && project.pumpLibrary.length === 0
		? deepFreeze(setPumpCurve(project, TEST_CURVE))
		: project;
}

/**
 * A new component of `kind` for a project made by readyFor. A new pump gets a curve id of its
 * own, still to be defined; here, as a user does in the pump form, it is set to use the
 * library's first curve. An assigned-flow node gets the flow, and an equipment item the rating, a
 * user enters where it is added (no default; made-up test inputs, testing/helpers.ts enteredFor).
 */
function newComponent(
	kind: ComponentKind,
	project: Project,
	options: Parameters<typeof createComponent>[2] = {}
): Component {
	const component = createComponent(kind, project, { ...enteredFor(kind), ...options });
	return component.type === 'pump'
		? { ...component, curveId: project.pumpLibrary[0]!.id }
		: component;
}

function totalLength(c: PipeConnection) {
	return c.piping.pipes.reduce((sum, p) => sum + p.length, 0);
}

describe('addComponentAtPort', () => {
	it('adds every kind at every free port and stays valid', () => {
		for (const [name, make] of SOURCES) {
			const source = make();
			// Free ports by removing each connection in turn.
			for (const connection of source.connections) {
				const freed = disconnect(source, connection.id);
				for (const end of [
					[connection.fromComponentId, connection.fromPortId],
					[connection.toComponentId, connection.toPortId]
				] as const) {
					for (const kind of COMPONENT_KINDS) {
						const opened = readyFor(kind, freed);
						const port = opened.components
							.find((c) => c.id === end[0])!
							.ports.find((p) => p.id === end[1])!;
						const component = newComponent(kind, opened, { nominalSize: port.nominalSize });
						const result = addComponentAtPort(opened, end[0], end[1], component);
						const context = `${name}: ${kind} at ${end[0]}.${end[1]}`;
						expectValid(result, context);
						expect(result.components).toHaveLength(opened.components.length + 1);
						expect(result.connections).toHaveLength(opened.connections.length + 1);
						expect(connectionAtPort(result, end[0], end[1]), context).toBeDefined();
					}
				}
			}
		}
	});

	it('builds a chain from scratch, orienting each connection with the flow', () => {
		let project = deepFreeze(createEmptyProject({ id: 'chain', now: '2026-01-01T00:00:00Z' }));
		const reservoir = createComponent('reservoir', project, { nominalSize: 0.1016 });
		project = deepFreeze({ ...project, components: [reservoir] });
		project = readyFor('pump', project);

		const pump = newComponent('pump', project, { nominalSize: 0.1016 });
		project = deepFreeze(addComponentAtPort(project, 'R1', 'port_1', pump));
		expect(project.connections[0]).toMatchObject({
			id: 'L1',
			fromComponentId: 'R1',
			fromPortId: 'port_1',
			toComponentId: 'P1',
			toPortId: 'suction'
		});
		// Leaving a reservoir: the cited default entrance (sharp-edged), visible and removable.
		expect(project.connections[0]!.piping).toEqual({
			pipes: [{ materialId: 'carbon_steel', schedule: '40', nominalSize: 0.1016, length: 10 }],
			fittings: [{ type: 'entrance_sharp', quantity: 1, pipeIndex: 0 }]
		});

		const valve = createComponent('check', project, { nominalSize: 0.0762 });
		project = deepFreeze(addComponentAtPort(project, 'P1', 'discharge', valve));
		expect(project.connections[1]).toMatchObject({
			fromComponentId: 'P1',
			fromPortId: 'discharge',
			toComponentId: 'V1',
			toPortId: 'inlet'
		});

		const tank = createComponent('reservoir', project);
		project = deepFreeze(addComponentAtPort(project, 'V1', 'outlet', tank));
		expect(project.connections[1]!.piping.fittings).toEqual([]);
		expect(project.connections[2]).toMatchObject({ fromComponentId: 'V1', toComponentId: 'R2' });
		// Arriving at a reservoir: the default exit loss.
		expect(project.connections[2]!.piping.fittings).toEqual([
			{ type: 'exit', quantity: 1, pipeIndex: 0 }
		]);
		expectValid(project, 'chain');
		expect(project.components.map((c) => c.id)).toEqual(['R1', 'P1', 'V1', 'R2']);
		expect(project.components[1]).toMatchObject({ curveId: 'CT' });
	});

	it('adds a pump to a project without curves; only its curve is then missing', () => {
		const project = disconnect(SOURCES[1]![1](), 'L3'); // gravity example: no pump curves
		const pump = createComponent('pump', project);
		const result = addComponentAtPort(project, 'V1', 'outlet', pump);
		expect(referentialIssues(result)).toEqual([`${pump.id}: missing pump curve ${pump.curveId}`]);
		expect(projectProblems(result)).toEqual([
			`Component "${pump.id}" uses pump curve "${pump.curveId}", which is not in the pump library.`
		]);
	});

	it('adds upstream of an inlet port, connecting the new component by its outlet', () => {
		const pump = createComponent('pump', createEmptyProject());
		const project = deepFreeze(projectWith([pump]));
		const valve = createComponent('gate', project);
		const result = addComponentAtPort(project, 'P1', 'suction', valve);
		expect(result.connections[0]).toMatchObject({
			fromComponentId: 'V1',
			fromPortId: 'outlet',
			toComponentId: 'P1',
			toPortId: 'suction'
		});
		const tee = createComponent('tee', result);
		const upstreamOfValve = addComponentAtPort(result, 'V1', 'inlet', tee);
		expect(upstreamOfValve.connections[1]).toMatchObject({
			fromComponentId: 'T1',
			fromPortId: 'run_outlet',
			toComponentId: 'V1',
			toPortId: 'inlet'
		});
	});

	describe('an assigned-flow node next to a reservoir: the entered flow sets the direction', () => {
		/** A project with R1 alone, or AF1 (flow, m³/s) alone. */
		const withReservoir = () =>
			deepFreeze(projectWith([createComponent('reservoir', createEmptyProject())]));
		const withNode = (flow: number) =>
			deepFreeze(projectWith([createComponent('assigned_flow', createEmptyProject(), { flow })]));
		const ends = (c: PipeConnection | undefined) => [c?.fromComponentId, c?.toComponentId];

		it('runs a supply into the reservoir, with the exit loss where it arrives', () => {
			const project = withReservoir();
			const supply = createComponent('assigned_flow', project, { flow: -0.005 });
			const [connection] = addComponentAtPort(project, 'R1', 'port_1', supply).connections;
			expect(ends(connection)).toEqual(['AF1', 'R1']);
			expect(connection!.piping.fittings).toEqual([{ type: 'exit', quantity: 1, pipeIndex: 0 }]);
			expect(addsUpstream(project.components[0]!, 'port_1', supply)).toBe(true);
		});

		it('runs a demand out of the reservoir, with the entrance loss where it leaves', () => {
			const project = withReservoir();
			const demand = createComponent('assigned_flow', project, { flow: 0.005 });
			const [connection] = addComponentAtPort(project, 'R1', 'port_1', demand).connections;
			expect(ends(connection)).toEqual(['R1', 'AF1']);
			expect(connection!.piping.fittings).toEqual([
				{ type: 'entrance_sharp', quantity: 1, pipeIndex: 0 }
			]);
			expect(addsUpstream(project.components[0]!, 'port_1', demand)).toBe(false);
		});

		it('feeds a demand from a reservoir added after it (an entrance), drains a supply into one (an exit)', () => {
			const demand = withNode(0.005);
			const tank = createComponent('reservoir', demand);
			const [fed] = addComponentAtPort(demand, 'AF1', 'port_1', tank).connections;
			expect(ends(fed)).toEqual(['R1', 'AF1']);
			expect(fed!.piping.fittings).toEqual([{ type: 'entrance_sharp', quantity: 1, pipeIndex: 0 }]);
			expect(addsUpstream(demand.components[0]!, 'port_1', tank)).toBe(true);

			const supply = withNode(-0.005);
			const [drained] = addComponentAtPort(
				supply,
				'AF1',
				'port_1',
				createComponent('reservoir', supply)
			).connections;
			expect(ends(drained)).toEqual(['AF1', 'R1']);
			expect(drained!.piping.fittings).toEqual([{ type: 'exit', quantity: 1, pipeIndex: 0 }]);
		});

		it('orients a connection drawn to a supply or from a demand with the flow', () => {
			const tank = createComponent('reservoir', createEmptyProject());
			for (const [flow, want, fitting] of [
				[-0.005, ['AF1', 'R1'], 'exit'],
				[0.005, ['R1', 'AF1'], 'entrance_sharp']
			] as const) {
				const node = createComponent('assigned_flow', createEmptyProject(), { flow });
				const project = deepFreeze(projectWith([tank, node]));
				const [drawn] = connectPorts(
					project,
					{ componentId: 'R1', portId: 'port_1' },
					{ componentId: 'AF1', portId: 'port_1' }
				).connections;
				expect(ends(drawn)).toEqual(want);
				expect(drawn!.piping.fittings.map((f) => f.type)).toEqual([fitting]);
			}
		});

		it('keeps the default direction for a zero flow, which has none', () => {
			const project = withReservoir();
			const zero = createComponent('assigned_flow', project, { flow: 0 });
			expect(ends(addComponentAtPort(project, 'R1', 'port_1', zero).connections[0])).toEqual([
				'R1',
				'AF1'
			]);
		});
	});

	it('refuses connected ports, unknown ports and reused ids', () => {
		const project = SOURCES[0]![1]();
		const valve = createComponent('gate', project);
		expect(() => addComponentAtPort(project, 'P1', 'suction', valve)).toThrow(EditError);
		expect(() => addComponentAtPort(project, 'P1', 'nope', valve)).toThrow(/has no port/);
		expect(() => addComponentAtPort(project, 'X', 'port_1', valve)).toThrow(/no component/);
		const opened = disconnect(project, 'L3');
		const duplicate = createComponent('reservoir', opened, { id: 'R1' });
		expect(() => addComponentAtPort(opened, 'V1', 'outlet', duplicate)).toThrow(/already used/);
		const clash = createComponent('reservoir', opened, { id: 'L1' });
		expect(() => addComponentAtPort(opened, 'V1', 'outlet', clash)).toThrow(/already used/);
	});
});

describe('insertComponentInConnection', () => {
	it('inserts every two-port kind into every connection and stays valid', () => {
		const turnedAround: string[] = [];
		for (const [name, make] of SOURCES) {
			const source = make();
			for (const drawn of source.connections) {
				// A connection drawn against the port roles (into a port that delivers flow, here
				// only the closed loop's reference node to the tee branch) is split in flow order.
				const role = (id: string, port: string) =>
					portRole(
						source.components.find((c) => c.id === id)!,
						port
					);
				const fromRole = role(drawn.fromComponentId, drawn.fromPortId);
				const toRole = role(drawn.toComponentId, drawn.toPortId);
				const against =
					(fromRole === 'in' || toRole === 'out') && fromRole !== 'out' && toRole !== 'in';
				if (against) turnedAround.push(`${name} ${drawn.id}`);
				const connection: PipeConnection = against
					? {
							...drawn,
							fromComponentId: drawn.toComponentId,
							fromPortId: drawn.toPortId,
							toComponentId: drawn.fromComponentId,
							toPortId: drawn.fromPortId,
							piping: reversePiping(drawn.piping)
						}
					: drawn;
				for (const kind of TWO_PORT_KINDS) {
					const target = readyFor(kind, source);
					const component = newComponent(kind, target);
					const result = insertComponentInConnection(target, connection.id, component);
					const context = `${name}: ${kind} in ${connection.id}`;
					expectValid(result, context);
					expect(result.connections).toHaveLength(target.connections.length + 1);

					const upstream = result.connections.find((c) => c.id === connection.id)!;
					const inlet = inletPort(component)!;
					const outlet = outletPort(component)!;
					expect(upstream).toMatchObject({
						fromComponentId: connection.fromComponentId,
						fromPortId: connection.fromPortId,
						toComponentId: component.id,
						toPortId: inlet.id
					});
					expect(upstream.piping.pipes).toEqual(connection.piping.pipes);
					const downstream = connectionAtPort(result, component.id, outlet.id)!;
					expect(downstream).toMatchObject({
						fromComponentId: component.id,
						toComponentId: connection.toComponentId,
						toPortId: connection.toPortId
					});
					const last = connection.piping.pipes[connection.piping.pipes.length - 1]!;
					expect(downstream.piping.pipes).toEqual([{ ...last, length: SHORT_PIPE_LENGTH }]);
					// Fittings are kept; exit fittings move to the downstream end.
					expect(upstream.piping.fittings.length + downstream.piping.fittings.length).toBe(
						connection.piping.fittings.length
					);
					expect(downstream.piping.fittings.every((f) => f.type === 'exit')).toBe(true);
					expect(upstream.piping.fittings.some((f) => f.type === 'exit')).toBe(false);
				}
			}
		}
		expect(turnedAround).toEqual(['closed-loop L1']);
	});

	it('keeps the order of connections readable (new half right after the old one)', () => {
		const project = SOURCES[0]![1]();
		const result = insertComponentInConnection(project, 'L2', createComponent('globe', project));
		expect(result.connections.map((c) => c.id)).toEqual(['L1', 'L2', 'L4', 'L3']);
	});

	it('refuses components without separate inlet and outlet ports', () => {
		const project = SOURCES[0]![1]();
		for (const kind of ['reservoir', 'plug', 'reference_node'] as const) {
			expect(() =>
				insertComponentInConnection(project, 'L1', createComponent(kind, project))
			).toThrow(/separate inlet and outlet/);
		}
		expect(() =>
			insertComponentInConnection(project, 'L9', createComponent('gate', project))
		).toThrow(/no connection/);
	});
});

describe('orientation by port roles', () => {
	/** R1, pump P1 (with a curve) and R2; P1's suction connected to R1 "from the pump". */
	function suctionDrawnFromPump(): Project {
		const r1 = createComponent('reservoir', createEmptyProject(), { id: 'R1' });
		const pump = createComponent('pump', setPumpCurve(createEmptyProject(), TEST_CURVE));
		const r2 = createComponent('reservoir', createEmptyProject(), { id: 'R2' });
		const base = projectWith(
			[r1, pump, r2],
			[
				{ ...link('L1', ['P1', 'suction'], ['R1', 'port_1']) },
				link('L2', ['P1', 'discharge'], ['R2', 'port_1'])
			],
			[TEST_CURVE]
		);
		return deepFreeze({
			...base,
			components: base.components.map((c) => (c.type === 'pump' ? { ...c, curveId: 'CT' } : c))
		});
	}

	/** The component at the other end of the connection at a port. */
	function facing(project: Project, componentId: string, portId: string): string | undefined {
		const c = connectionAtPort(project, componentId, portId);
		if (!c) return undefined;
		return c.fromComponentId === componentId && c.fromPortId === portId
			? c.toComponentId
			: c.fromComponentId;
	}

	it('connectPorts runs the connection with the flow, whichever port it starts from', () => {
		const pump = createComponent('pump', setPumpCurve(createEmptyProject(), TEST_CURVE));
		const r1 = createComponent('reservoir', createEmptyProject(), { id: 'R1' });
		const project = deepFreeze(projectWith([r1, { ...pump, curveId: 'CT' }], [], [TEST_CURVE]));
		const fromSuction = connectPorts(
			project,
			{ componentId: 'P1', portId: 'suction' },
			{ componentId: 'R1', portId: 'port_1' }
		);
		expect(fromSuction.connections[0]).toMatchObject({
			fromComponentId: 'R1',
			fromPortId: 'port_1',
			toComponentId: 'P1',
			toPortId: 'suction'
		});
		const fromDischarge = connectPorts(
			project,
			{ componentId: 'R1', portId: 'port_1' },
			{ componentId: 'P1', portId: 'discharge' }
		);
		expect(fromDischarge.connections[0]).toMatchObject({
			fromComponentId: 'P1',
			fromPortId: 'discharge',
			toComponentId: 'R1',
			toPortId: 'port_1'
		});
		// Explicit piping is turned around with the connection.
		const piping = {
			pipes: [
				{ materialId: 'carbon_steel', schedule: '40', nominalSize: 0.1016, length: 1 },
				{ materialId: 'carbon_steel', schedule: '40', nominalSize: 0.0762, length: 2 }
			],
			fittings: [{ type: 'elbow_90_lr' as const, quantity: 1, pipeIndex: 0 }]
		};
		const turned = connectPorts(
			project,
			{ componentId: 'P1', portId: 'suction' },
			{ componentId: 'R1', portId: 'port_1' },
			piping
		);
		expect(turned.connections[0]!.piping).toEqual(reversePiping(piping));
		expectValid(turned, 'connect from a suction');
	});

	it('inserts a check valve into a connection drawn from a pump suction facing the flow', () => {
		const project = suctionDrawnFromPump();
		const valve = createComponent('check', project);
		const result = insertComponentInConnection(project, 'L1', valve);
		expectValid(result, 'insert into a reversed connection');
		// Flow runs R1 → check valve → pump suction.
		expect(facing(result, valve.id, 'inlet')).toBe('R1');
		expect(facing(result, valve.id, 'outlet')).toBe('P1');
		for (const c of result.connections) {
			expect(['inlet', 'suction']).not.toContain(c.fromPortId);
		}
		// The piping keeps its run from R1: the original pipes stay on the R1 side.
		const upstream = result.connections.find((c) => c.id === 'L1')!;
		expect(upstream).toMatchObject({ fromComponentId: 'R1', toComponentId: valve.id });
		expect(upstream.piping.pipes).toEqual(project.connections[0]!.piping.pipes);
	});

	it('inserts a pump that pushes the same way as the existing one', () => {
		const project = suctionDrawnFromPump();
		const booster = createComponent('pump', project);
		const result = insertComponentInConnection(project, 'L1', booster);
		expect(facing(result, booster.id, 'suction')).toBe('R1');
		expect(facing(result, booster.id, 'discharge')).toBe('P1');
	});

	it('joins a reversed one-pipe connection that carries a reducer without a negative index', () => {
		const valve = createComponent('gate', createEmptyProject());
		const a = createComponent('reservoir', createEmptyProject(), { id: 'A' });
		const b = createComponent('reservoir', createEmptyProject(), { id: 'B' });
		const into: PipeConnection = {
			...link('L1', ['V1', 'inlet'], ['A', 'port_1']), // drawn from the valve to A
			piping: {
				pipes: [{ materialId: 'carbon_steel', schedule: '40', nominalSize: 0.1016, length: 3 }],
				fittings: [{ type: 'reducer_sudden', quantity: 1, pipeIndex: 0 }]
			}
		};
		const project = deepFreeze(
			projectWith([a, valve, b], [into, link('L2', ['V1', 'outlet'], ['B', 'port_1'])])
		);
		const result = deleteComponent(project, 'V1', { join: true });
		expectValid(result, 'join with a reducer');
		// The reducer now lies between the two joined sides.
		expect(result.connections[0]!.piping.fittings).toEqual([
			{ type: 'reducer_sudden', quantity: 1, pipeIndex: 0 }
		]);
		expect(result.connections[0]!.piping.pipes).toHaveLength(2);
	});
});

describe('addBranch', () => {
	it('puts a tee in every connection with its branch port free', () => {
		for (const [name, make] of SOURCES) {
			const source = make();
			for (const connection of source.connections) {
				const result = addBranch(source, connection.id);
				expectValid(result, `${name}: branch in ${connection.id}`);
				const tee = result.components.find((c) => !source.components.includes(c))!;
				expect(tee).toMatchObject({ type: 'branch', branchType: 'tee' });
				expect(freePorts(result, tee.id).map((p) => p.id)).toEqual(['branch']);
				const from = source.components.find((c) => c.id === connection.fromComponentId)!;
				expect(tee.elevation).toBe(from.elevation);
			}
		}
	});

	it('takes a prepared tee or wye, and nothing else', () => {
		const project = SOURCES[0]![1]();
		const wye = createComponent('wye', project, { id: 'Y7' });
		const result = addBranch(project, 'L3', wye);
		expect(freePorts(result, 'Y7').map((p) => p.id)).toEqual(['outlet_2']);
		expect(() => addBranch(project, 'L3', createComponent('gate', project))).toThrow(
			/tee or a wye/
		);
	});
});

describe('deleteComponent', () => {
	it('removes every component with its connections and stays valid', () => {
		for (const [name, make] of SOURCES) {
			const source = make();
			for (const component of source.components) {
				const result = deleteComponent(source, component.id);
				expectValid(result, `${name}: delete ${component.id}`);
				expect(result.components.find((c) => c.id === component.id)).toBeUndefined();
				expect(
					result.connections.some(
						(c) => c.fromComponentId === component.id || c.toComponentId === component.id
					)
				).toBe(false);
			}
		}
	});

	it('joins the neighbors of every component with two connected ports', () => {
		const joinable: string[] = [];
		for (const [name, make] of SOURCES) {
			const source = make();
			for (const component of source.components) {
				const plan = joinPlan(source, component.id);
				expect(canJoin(source, component.id)).toBe(plan !== null);
				if (!plan) {
					expect(() => deleteComponent(source, component.id, { join: true })).toThrow(EditError);
					continue;
				}
				joinable.push(`${name} ${component.id}`);
				const [a, b] = plan.ports.map((p) => connectionAtPort(source, component.id, p.id)!);
				const result = deleteComponent(source, component.id, { join: true });
				const context = `${name}: join ${component.id}`;
				expectValid(result, context);
				// Two connections become one; plugs on other ports go with their stubs.
				expect(result.connections).toHaveLength(
					source.connections.length - 1 - plan.plugIds.length
				);
				expect(result.components).toHaveLength(source.components.length - 1 - plan.plugIds.length);
				const merged = result.connections.find((c) => c.id === a!.id)!;
				expect(totalLength(merged)).toBeCloseTo(totalLength(a!) + totalLength(b!), 12);
				expect(merged.piping.fittings).toHaveLength(
					a!.piping.fittings.length + b!.piping.fittings.length
				);
			}
		}
		// Two-port components, and the fixture's tee whose branch is plugged; not the tees with
		// three connections or the boundaries with one.
		expect(joinable).toEqual([
			'pump-transfer P1',
			'pump-transfer V1',
			'gravity-branch V1',
			'closed-loop P1',
			'closed-loop V1',
			'fixture P1',
			'fixture T1',
			'fixture V1'
		]);
	});

	it('rejoins the line when a tee added as a branch is deleted', () => {
		const source = SOURCES[0]![1](); // pump transfer
		const withTee = deepFreeze(addBranch(source, 'L2')); // P1 → T1 → V1, branch free
		const tee = withTee.components.find((c) => c.type === 'branch')!;
		expect(joinPlan(withTee, tee.id)).toMatchObject({
			ports: [{ id: 'run_inlet' }, { id: 'run_outlet' }],
			plugIds: []
		});
		const freed = deleteComponent(withTee, tee.id, { join: true });
		expectValid(freed, 'join a tee with a free branch');
		expect(freed.connections.map((c) => `${c.id} ${c.fromComponentId}→${c.toComponentId}`)).toEqual(
			['L1 R1→P1', 'L2 P1→V1', 'L3 V1→R2']
		);

		// With the branch plugged, the plug and its stub go too.
		const plugged = deepFreeze(plugPort(withTee, tee.id, 'branch'));
		const plan = joinPlan(plugged, tee.id)!;
		expect(plan.plugIds).toHaveLength(1);
		const result = deleteComponent(plugged, tee.id, { join: true });
		expectValid(result, 'join a tee with a plugged branch');
		expect(result.components.map((c) => c.id)).toEqual(['R1', 'P1', 'V1', 'R2']);
		expect(result.connections.map((c) => c.id)).toEqual(['L1', 'L2', 'L3']);

		// A tee with three real connections cannot join.
		const gravity = SOURCES[1]![1]();
		expect(joinPlan(gravity, 'T1')).toBeNull();
	});

	it('joins in flow order and offsets the downstream fitting indices', () => {
		const project = SOURCES[0]![1]();
		const result = deleteComponent(project, 'V1', { join: true });
		const merged = result.connections.find((c) => c.id === 'L2')!;
		expect(merged).toMatchObject({
			fromComponentId: 'P1',
			fromPortId: 'discharge',
			toComponentId: 'R2',
			toPortId: 'port_1'
		});
		expect(merged.piping.pipes.map((p) => p.length)).toEqual([3, 60]);
		expect(merged.piping.fittings).toEqual([
			{ type: 'elbow_90_lr', quantity: 4, pipeIndex: 1 },
			{ type: 'exit', quantity: 1, pipeIndex: 1 }
		]);
	});

	it('reverses piping that was drawn against the flow', () => {
		const valve = createComponent('gate', createEmptyProject());
		const a = createComponent('reservoir', createEmptyProject(), { id: 'A' });
		const b = createComponent('reservoir', createEmptyProject(), { id: 'B' });
		const into: PipeConnection = {
			...link('L1', ['V1', 'inlet'], ['A', 'port_1']), // drawn from the valve to A
			piping: {
				pipes: [
					{ materialId: 'carbon_steel', schedule: '40', nominalSize: 0.0762, length: 1 },
					{ materialId: 'carbon_steel', schedule: '40', nominalSize: 0.1016, length: 2 }
				],
				fittings: [
					{ type: 'reducer_sudden', quantity: 1, pipeIndex: 0 },
					{ type: 'entrance_sharp', quantity: 1, pipeIndex: 1 }
				]
			}
		};
		const out = link('L2', ['B', 'port_1'], ['V1', 'outlet']); // drawn from B to the valve
		const project = deepFreeze(projectWith([a, valve, b], [into, out]));
		const result = deleteComponent(project, 'V1', { join: true });
		expectValid(result, 'reversed join');
		expect(result.connections).toEqual([
			{
				id: 'L1',
				fromComponentId: 'A',
				fromPortId: 'port_1',
				toComponentId: 'B',
				toPortId: 'port_1',
				piping: {
					pipes: [
						{ materialId: 'carbon_steel', schedule: '40', nominalSize: 0.1016, length: 2 },
						{ materialId: 'carbon_steel', schedule: '40', nominalSize: 0.0762, length: 1 },
						{ materialId: 'carbon_steel', schedule: '40', nominalSize: 0.1016, length: 10 }
					],
					fittings: [
						{ type: 'reducer_sudden', quantity: 1, pipeIndex: 0 },
						{ type: 'entrance_sharp', quantity: 1, pipeIndex: 0 }
					]
				}
			}
		]);
	});

	it('cannot join a component whose ports are connected to each other or left open', () => {
		const reservoir = createComponent('reservoir', createEmptyProject());
		reservoir.ports.push({ id: 'port_2', nominalSize: 0.1, direction: 'bidirectional' });
		const self = projectWith([reservoir], [link('L1', ['R1', 'port_1'], ['R1', 'port_2'])]);
		expect(canJoin(self, 'R1')).toBe(false);
		const open = SOURCES[0]![1]();
		expect(canJoin(disconnect(open, 'L3'), 'V1')).toBe(false);
		expect(canJoin(open, 'R1')).toBe(false);
		expect(canJoin(open, 'missing')).toBe(false);
	});
});

describe('plugPort, connectPorts and disconnect', () => {
	it('plugs every port that is opened and stays valid', () => {
		for (const [name, make] of SOURCES) {
			const source = make();
			for (const connection of source.connections) {
				const opened = disconnect(source, connection.id);
				expectValid(opened, `${name}: disconnect ${connection.id}`);
				const result = plugPort(opened, connection.fromComponentId, connection.fromPortId);
				expectValid(result, `${name}: plug ${connection.fromComponentId}.${connection.fromPortId}`);
				const plug = result.components[result.components.length - 1]!;
				expect(plug.type).toBe('plug');
				const stub = connectionAtPort(result, plug.id, 'port_1')!;
				expect(stub.piping.pipes[0]!.length).toBe(SHORT_PIPE_LENGTH);
				expect(stub.piping.pipes[0]!.nominalSize).toBe(
					opened.components
						.find((c) => c.id === connection.fromComponentId)!
						.ports.find((p) => p.id === connection.fromPortId)!.nominalSize
				);
			}
		}
	});

	it('reconnects opened ports, closing loops again', () => {
		for (const [name, make] of SOURCES) {
			const source = make();
			for (const c of source.connections) {
				const opened = disconnect(source, c.id);
				const result = connectPorts(
					opened,
					{ componentId: c.fromComponentId, portId: c.fromPortId },
					{ componentId: c.toComponentId, portId: c.toPortId },
					c.piping
				);
				expectValid(result, `${name}: reconnect ${c.id}`);
				expect(result.connections).toHaveLength(source.connections.length);
			}
		}
	});

	it('connectPorts gives a default pipe the default losses at a reservoir, not given piping', () => {
		const opened = disconnect(SOURCES[0]![1](), 'L1'); // pump example: R1 → P1 suction freed
		const ends = [
			{ componentId: 'P1', portId: 'suction' },
			{ componentId: 'R1', portId: 'port_1' }
		] as const;
		const added = connectPorts(opened, ends[0], ends[1]);
		const connection = connectionAtPort(added, 'R1', 'port_1')!;
		expect(connection).toMatchObject({ fromComponentId: 'R1', toComponentId: 'P1' });
		expect(connection.piping.fittings).toEqual([
			{ type: 'entrance_sharp', quantity: 1, pipeIndex: 0 }
		]);
		const given = { pipes: [connection.piping.pipes[0]!], fittings: [] };
		const explicit = connectPorts(opened, ends[0], ends[1], given);
		expect(connectionAtPort(explicit, 'R1', 'port_1')!.piping.fittings).toEqual([]);
	});

	it('withReservoirLosses keeps an entrance or exit already there', () => {
		const project = SOURCES[0]![1](); // L1 has a sharp entrance, L3 an exit
		for (const connection of project.connections) {
			expect(withReservoirLosses(project, connection)).toBe(connection);
		}
		const bare = { ...project.connections[0]!, piping: { ...project.connections[0]!.piping } };
		bare.piping.fittings = [{ type: 'entrance_rounded', quantity: 1, pipeIndex: 0 }];
		expect(withReservoirLosses(project, bare)).toBe(bare);
		expect(hasReservoirLoss(bare.piping)).toBe(true);
		expect(hasReservoirLoss({ pipes: bare.piping.pipes, fittings: [] })).toBe(false);
	});

	it('refuse connected and identical ports', () => {
		const project = SOURCES[0]![1]();
		expect(() => plugPort(project, 'P1', 'suction')).toThrow(/already connected/);
		expect(() =>
			connectPorts(
				project,
				{ componentId: 'P1', portId: 'suction' },
				{ componentId: 'V1', portId: 'outlet' }
			)
		).toThrow(/already connected/);
		const opened = disconnect(project, 'L1');
		expect(() =>
			connectPorts(
				opened,
				{ componentId: 'R1', portId: 'port_1' },
				{ componentId: 'R1', portId: 'port_1' }
			)
		).toThrow(/itself/);
		expect(() => disconnect(project, 'L9')).toThrow(/no connection/);
	});
});

describe('reserved ids (page state that names elements: goal-seek.md §6.15)', () => {
	it('new connections and components of an edit never take a reserved id', () => {
		const project = EXAMPLES[0]!.create();
		const reserved = ['L3', 'L4', 'L5', 'PL1', 'T1'];
		const gate = createComponent('gate', project, { reserved });
		const inserted = insertComponentInConnection(project, 'L3', gate, { reserved });
		expect(inserted.connections.map((c) => c.id)).toEqual(['L1', 'L2', 'L3', 'L6']);
		const free = { ...project, connections: project.connections.filter((c) => c.id !== 'L3') };
		const plugged = plugPort(free, 'V1', 'outlet', { reserved });
		expect(plugged.components.at(-1)?.id).toBe('PL2');
		expect(plugged.connections.at(-1)?.id).toBe('L6');
		const joined = connectPorts(
			free,
			{ componentId: 'V1', portId: 'outlet' },
			{ componentId: 'R2', portId: 'port_1' },
			undefined,
			{ reserved }
		);
		expect(joined.connections.at(-1)?.id).toBe('L6');
		const branched = addBranch(project, 'L3', undefined, { reserved });
		expect(branched.components.at(-1)?.id).toBe('T2');
		const tank = createComponent('reservoir', project, { reserved: ['R3'] });
		expect(
			addComponentAtPort(free, 'V1', 'outlet', tank, { reserved }).connections.at(-1)?.id
		).toBe('L6');
		// Without reserved ids, the first unused ones.
		expect(
			insertComponentInConnection(project, 'L3', createComponent('gate', project)).connections.at(
				-1
			)?.id
		).toBe('L4');
	});
});

describe('updateComponent and updateConnection', () => {
	it('change properties and keep the graph', () => {
		const project = SOURCES[0]![1]();
		const renamed = updateComponent(project, 'P1', (c) => ({
			...c,
			name: 'Main pump',
			elevation: 1
		}));
		expectValid(renamed, 'rename');
		expect(renamed.components[1]).toMatchObject({ name: 'Main pump', elevation: 1 });
		const asCheck = updateComponent(project, 'V1', (c) => ({
			...createComponent('check', project, { id: c.id, name: c.name }),
			ports: c.ports
		}));
		expectValid(asCheck, 'valve family change');
		const longer = updateConnection(project, 'L3', (c) => {
			c.piping.pipes[0]!.length = 80;
			c.piping.fittings.push({ type: 'elbow_45_lr', quantity: 2, pipeIndex: 0 });
			return c;
		});
		expectValid(longer, 'connection edit');
		expect(longer.connections[2]!.piping.pipes[0]!.length).toBe(80);
		expect(project.connections[2]!.piping.pipes[0]!.length).toBe(60);
	});

	it('refuse id changes, removing a connected port and moving connection ends', () => {
		const project = SOURCES[0]![1]();
		expect(() => updateComponent(project, 'P1', (c) => ({ ...c, id: 'P2' }))).toThrow(/id cannot/);
		expect(() => updateComponent(project, 'R1', (c) => ({ ...c, ports: [] }) as Component)).toThrow(
			/is connected/
		);
		expect(() =>
			updateConnection(project, 'L1', (c) => ({ ...c, toComponentId: 'V1', toPortId: 'inlet' }))
		).toThrow(/cannot be changed/);
		expect(() => updateConnection(project, 'L1', (c) => ({ ...c, id: 'L7' }))).toThrow(
			/cannot be changed/
		);
	});
});

describe('reservoir ports', () => {
	it('can be added and removed', () => {
		let project = SOURCES[0]![1]();
		project = addPort(project, 'R1');
		project = addPort(project, 'R1', { nominalSize: 0.0508, elevation: 1.5 });
		expectValid(project, 'add ports');
		const ports = project.components[0]!.ports;
		expect(ports.map((p) => [p.id, p.nominalSize])).toEqual([
			['port_1', 0.1016],
			['port_2', 0.1016],
			['port_3', 0.0508]
		]);
		expect(ports[2]!.elevation).toBe(1.5);
		const withPump = addComponentAtPort(
			project,
			'R1',
			'port_2',
			newComponent('pump', project, { id: 'P2' })
		);
		expectValid(withPump, 'second pump on port_2');
		project = removePort(project, 'R1', 'port_2');
		expect(project.components[0]!.ports.map((p) => p.id)).toEqual(['port_1', 'port_3']);
		expect(addPort(project, 'R1').components[0]!.ports.map((p) => p.id)).toEqual([
			'port_1',
			'port_3',
			'port_2'
		]);
		expectValid(project, 'remove port');
	});

	it('are limited to reservoirs, to free ports and to 1–16 per reservoir', () => {
		const project = SOURCES[0]![1]();
		expect(() => addPort(project, 'P1')).toThrow(/Only reservoirs/);
		expect(() => removePort(project, 'R1', 'port_1')).toThrow(/already connected/);
		const alone = projectWith([createComponent('reservoir', createEmptyProject())]);
		expect(() => removePort(alone, 'R1', 'port_1')).toThrow(/at least one port/);
		// The bound is the schema's (Reservoir.ports maxItems), not a copy of it.
		const max = maxPorts(alone.components[0]!);
		expect(max).toBe(openapi.components.schemas.Reservoir.properties.ports.maxItems);
		expect(max).toBe(16);
		let full = alone;
		for (let i = 1; i < max; i++) full = addPort(full, 'R1');
		expect(full.components[0]!.ports).toHaveLength(max);
		expectValid(full, '16 ports');
		expect(canAddPort(full.components[0]!)).toBe(false);
		expect(() => addPort(full, 'R1')).toThrow(/at most 16/);
		expect(canAddPort(alone.components[0]!)).toBe(true);
		for (const kind of ['reference_node', 'plug', 'tee', 'pump', 'gate'] as const) {
			expect(canAddPort(createComponent(kind, createEmptyProject())), kind).toBe(false);
		}
	});
});

describe('pump curves', () => {
	it('are added, replaced and removed when unused', () => {
		const project = SOURCES[0]![1]();
		const curve = {
			id: 'C2',
			name: 'Spare',
			points: [
				{ flow: 0, head: 10 },
				{ flow: 0.01, head: 8 },
				{ flow: 0.02, head: 4 }
			]
		};
		const added = setPumpCurve(project, curve);
		expect(added.pumpLibrary.map((c) => c.id)).toEqual(['C1', 'C2']);
		const replaced = setPumpCurve(added, { ...curve, name: 'Renamed' });
		expect(replaced.pumpLibrary[1]!.name).toBe('Renamed');
		expectValid(replaced, 'curves');
		expect(removePumpCurve(replaced, 'C2').pumpLibrary.map((c) => c.id)).toEqual(['C1']);
		expect(() => removePumpCurve(replaced, 'C1')).toThrow(/uses this curve/);
		expect(() => setPumpCurve(project, { ...curve, id: 'P1' })).toThrow(/already used/);
	});
});

describe('reversePiping', () => {
	it('mirrors pipes and fitting positions, and is its own inverse', () => {
		const piping = fixture.connections[1]!.piping; // two pipes, a bend, a reducer and a custom K
		const reversed = reversePiping(piping);
		expect(reversed.pipes).toEqual([...piping.pipes].reverse());
		expect(reversed.fittings.map((f) => [f.type, f.pipeIndex])).toEqual([
			['bend', 0],
			['reducer_sudden', 0],
			['custom', 0]
		]);
		expect(reversePiping(reversed)).toEqual(piping);
	});
});

describe('purity', () => {
	it('never modifies the input project', () => {
		const project = SOURCES[0]![1](); // deep-frozen: any write throws
		const snapshot = JSON.stringify(project);
		addBranch(project, 'L1');
		deleteComponent(project, 'V1', { join: true });
		deleteComponent(project, 'P1');
		updateComponent(project, 'P1', (c) => {
			c.name = 'changed';
			return c;
		});
		updateConnection(project, 'L1', (c) => {
			c.piping.pipes[0]!.length = 1;
			return c;
		});
		insertComponentInConnection(project, 'L3', createComponent('psv', project));
		plugPort(disconnect(project, 'L1'), 'R1', 'port_1');
		expect(JSON.stringify(project)).toBe(snapshot);
	});
});
