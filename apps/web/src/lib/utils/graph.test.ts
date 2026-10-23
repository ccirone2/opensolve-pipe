import { describe, expect, it } from 'vitest';
import type { Component } from '../api/types';
import { link, projectWith } from '../testing/helpers';
import { closedLoopExample, gravityBranchExample, pumpTransferExample } from './examples';
import { createComponent, createEmptyProject } from './factory';
import {
	componentById,
	connectionAtPort,
	connectionById,
	connectionsOf,
	defaultStart,
	freePorts,
	inletPort,
	isBoundary,
	type NavigationStep,
	neighbors,
	nextOptions,
	onwardFreePort,
	otherEnd,
	outletPort,
	pathTo,
	portById,
	portRole,
	reachable,
	validPathPrefix
} from './graph';

const empty = createEmptyProject();

function make(
	kind: Parameters<typeof createComponent>[0],
	id: string,
	ports?: string[]
): Component {
	const component = createComponent(kind, empty, { id });
	if (ports) {
		component.ports = ports.map((p) => ({
			id: p,
			nominalSize: 0.1016,
			direction: 'bidirectional'
		}));
	}
	return component;
}

/** Walk the navigator: from `path`, follow the option to `otherId`. */
function step(
	project: ReturnType<typeof createEmptyProject>,
	path: NavigationStep[],
	otherId: string
) {
	const option = nextOptions(project, path).find((o) => o.otherId === otherId && !o.loop);
	if (!option) throw new Error(`no way forward to ${otherId}`);
	return [...path, { componentId: otherId, viaConnectionId: option.connection.id }];
}

describe('lookups', () => {
	const project = pumpTransferExample();

	it('find components, connections and ports', () => {
		expect(componentById(project, 'P1')?.name).toBe('Transfer pump');
		expect(componentById(project, 'nope')).toBeUndefined();
		expect(connectionById(project, 'L2')?.fromComponentId).toBe('P1');
		expect(portById(componentById(project, 'P1')!, 'discharge')?.direction).toBe('outlet');
		expect(connectionAtPort(project, 'P1', 'suction')?.id).toBe('L1');
		expect(connectionAtPort(project, 'P1', 'discharge')?.id).toBe('L2');
		expect(connectionAtPort(project, 'R2', 'port_1')?.id).toBe('L3');
		expect(connectionAtPort(project, 'R2', 'port_9')).toBeUndefined();
		expect(connectionsOf(project, 'V1').map((c) => c.id)).toEqual(['L2', 'L3']);
	});

	it('list free ports', () => {
		expect(freePorts(project, 'P1')).toEqual([]);
		const reservoir = make('reservoir', 'R1', ['port_1', 'port_2', 'port_3']);
		const tank = make('reservoir', 'R2');
		const partial = projectWith(
			[reservoir, tank],
			[link('L1', ['R1', 'port_2'], ['R2', 'port_1'])]
		);
		expect(freePorts(partial, 'R1').map((p) => p.id)).toEqual(['port_1', 'port_3']);
		expect(freePorts(partial, 'missing')).toEqual([]);
	});

	it('pick the free port the network goes on from', () => {
		const onward = (p: ReturnType<typeof projectWith>, id: string, preferred?: string) =>
			onwardFreePort(p, id, preferred)?.id;
		// A lone valve or pump: downstream, whatever port is preferred.
		const valve = projectWith([make('gate', 'V1')], []);
		expect(onward(valve, 'V1')).toBe('outlet');
		expect(onward(valve, 'V1', 'inlet')).toBe('outlet');
		expect(onward(projectWith([make('pump', 'P1')], []), 'P1')).toBe('discharge');
		// Arrived at the outlet: only the inlet is left, so the walk goes on upstream.
		const upstream = projectWith(
			[make('gate', 'V1'), make('reservoir', 'R1')],
			[link('L1', ['V1', 'outlet'], ['R1', 'port_1'])]
		);
		expect(onward(upstream, 'V1')).toBe('inlet');
		// A tee: either outlet, the preferred one first.
		const tee = projectWith([make('tee', 'T1')], []);
		expect(onward(tee, 'T1')).toBe('run_outlet');
		expect(onward(tee, 'T1', 'branch')).toBe('branch');
		// Boundary ports go either way.
		const reservoir = projectWith([make('reservoir', 'R1', ['port_1', 'port_2'])], []);
		expect(onward(reservoir, 'R1', 'port_2')).toBe('port_2');
		expect(onward(project, 'P1')).toBeUndefined();
		expect(onward(project, 'missing')).toBeUndefined();
	});

	it('give the other end of a connection', () => {
		const l2 = connectionById(project, 'L2')!;
		expect(otherEnd(l2, { componentId: 'P1', portId: 'discharge' })).toEqual({
			componentId: 'V1',
			portId: 'inlet'
		});
		expect(otherEnd(l2, { componentId: 'V1', portId: 'inlet' })).toEqual({
			componentId: 'P1',
			portId: 'discharge'
		});
	});
});

describe('neighbors', () => {
	it('lists connections in port order with both ends', () => {
		const project = pumpTransferExample();
		expect(neighbors(project, 'P1')).toEqual([
			expect.objectContaining({
				portId: 'suction',
				otherId: 'R1',
				otherPortId: 'port_1',
				outgoing: false
			}),
			expect.objectContaining({
				portId: 'discharge',
				otherId: 'V1',
				otherPortId: 'inlet',
				outgoing: true
			})
		]);
		expect(neighbors(project, 'missing')).toEqual([]);
	});

	it('lists a connection between two ports of one component once per port', () => {
		const reservoir = make('reservoir', 'R1', ['port_1', 'port_2']);
		const project = projectWith([reservoir], [link('L1', ['R1', 'port_1'], ['R1', 'port_2'])]);
		expect(neighbors(project, 'R1').map((n) => [n.portId, n.otherPortId])).toEqual([
			['port_1', 'port_2'],
			['port_2', 'port_1']
		]);
		// ... but it is not a way forward.
		expect(nextOptions(project, [{ componentId: 'R1' }])).toEqual([]);
	});
});

describe('nextOptions', () => {
	it('follows a chain one way at a time', () => {
		const project = pumpTransferExample();
		let path: NavigationStep[] = [{ componentId: defaultStart(project)! }];
		expect(path[0]!.componentId).toBe('R1');
		const visited = ['R1'];
		for (;;) {
			const options = nextOptions(project, path);
			if (options.length === 0) break;
			expect(options).toHaveLength(1);
			expect(options[0]!.loop).toBe(false);
			path = step(project, path, options[0]!.otherId);
			visited.push(options[0]!.otherId);
		}
		expect(visited).toEqual(['R1', 'P1', 'V1', 'R2']);
		expect(path.map((s) => s.viaConnectionId)).toEqual([undefined, 'L1', 'L2', 'L3']);
	});

	it('offers every branch at a tee, with the ports involved', () => {
		const project = gravityBranchExample();
		const path = step(project, [{ componentId: 'R1' }], 'T1');
		const options = nextOptions(project, path);
		expect(
			options.map((o) => ({ to: o.otherId, via: o.connection.id, port: o.portId, loop: o.loop }))
		).toEqual([
			{ to: 'V1', via: 'L2', port: 'run_outlet', loop: false },
			{ to: 'R3', via: 'L4', port: 'branch', loop: false }
		]);
		// The breadcrumb records the branch taken.
		const viaBranch = step(project, path, 'R3');
		expect(viaBranch).toEqual([
			{ componentId: 'R1' },
			{ componentId: 'T1', viaConnectionId: 'L1' },
			{ componentId: 'R3', viaConnectionId: 'L4' }
		]);
		expect(nextOptions(project, viaBranch)).toEqual([]);
	});

	it('flags a way back to a component on the path as a loop', () => {
		const project = closedLoopExample();
		let path: NavigationStep[] = [{ componentId: defaultStart(project)! }];
		expect(path[0]!.componentId).toBe('N1');
		path = step(project, path, 'T1');
		const atTee = nextOptions(project, path);
		expect(atTee.map((o) => [o.otherId, o.loop])).toEqual([
			['V1', false],
			['P1', false]
		]);
		path = step(project, path, 'P1');
		path = step(project, path, 'V1');
		const options = nextOptions(project, path);
		expect(options).toHaveLength(1);
		expect(options[0]).toMatchObject({ otherId: 'T1', loop: true, loopIndex: 1 });
		expect(options[0]!.connection.id).toBe('L4');
	});

	it('treats a second connection to the previous component as a loop, not the way back', () => {
		const reservoir = make('reservoir', 'R1', ['port_1', 'port_2']);
		const tee = make('tee', 'T1');
		const plug = make('plug', 'PL1');
		const project = projectWith(
			[reservoir, tee, plug],
			[
				link('L1', ['R1', 'port_1'], ['T1', 'run_inlet']),
				link('L2', ['T1', 'run_outlet'], ['R1', 'port_2']),
				link('L3', ['T1', 'branch'], ['PL1', 'port_1'])
			]
		);
		const path = step(project, [{ componentId: 'R1' }], 'T1');
		expect(nextOptions(project, path).map((o) => [o.connection.id, o.otherId, o.loop])).toEqual([
			['L2', 'R1', true],
			['L3', 'PL1', false]
		]);
	});

	it('offers every port of a multi-port reservoir', () => {
		const reservoir = make('reservoir', 'R1', ['port_1', 'port_2', 'port_3']);
		const pumps = ['P1', 'P2'].map((id) => make('pump', id));
		const plug = make('plug', 'PL1');
		const project = projectWith(
			[reservoir, ...pumps, plug],
			[
				link('L1', ['R1', 'port_1'], ['P1', 'suction']),
				link('L2', ['R1', 'port_2'], ['P2', 'suction']),
				link('L3', ['R1', 'port_3'], ['PL1', 'port_1'])
			]
		);
		const options = nextOptions(project, [{ componentId: 'R1' }]);
		expect(options.map((o) => [o.portId, o.otherId])).toEqual([
			['port_1', 'P1'],
			['port_2', 'P2'],
			['port_3', 'PL1']
		]);
		// Two pumps discharging back into the reservoir make loops through it.
		const looped = projectWith(
			[reservoir, ...pumps],
			[
				link('L1', ['R1', 'port_1'], ['P1', 'suction']),
				link('L2', ['P1', 'discharge'], ['R1', 'port_2']),
				link('L3', ['R1', 'port_3'], ['P2', 'suction'])
			]
		);
		const path = step(looped, [{ componentId: 'R1' }], 'P1');
		expect(nextOptions(looped, path)).toEqual([
			expect.objectContaining({ otherId: 'R1', otherPortId: 'port_2', loop: true, loopIndex: 0 })
		]);
	});

	it('handles empty paths and empty projects', () => {
		expect(nextOptions(empty, [])).toEqual([]);
		expect(nextOptions(empty, [{ componentId: 'X' }])).toEqual([]);
		expect(defaultStart(empty)).toBeUndefined();
		expect(reachable(empty, 'X')).toEqual(new Set());
		expect(pathTo(empty, 'X', 'Y')).toBeNull();
	});
});

describe('defaultStart', () => {
	it('prefers a reservoir or reference node, else the first component', () => {
		const pump = make('pump', 'P1');
		const valve = make('gate', 'V1');
		const node = make('reference_node', 'N1');
		expect(defaultStart(projectWith([pump, valve, node]))).toBe('N1');
		expect(defaultStart(projectWith([pump, valve]))).toBe('P1');
		expect(defaultStart(gravityBranchExample())).toBe('R1');
		expect(isBoundary(node)).toBe(true);
		expect(isBoundary(pump)).toBe(false);
	});
});

describe('reachable and pathTo', () => {
	it('find connected components only', () => {
		const project = gravityBranchExample();
		expect([...reachable(project, 'R1')].sort()).toEqual(['R1', 'R2', 'R3', 'T1', 'V1']);
		const island = projectWith([...project.components, make('plug', 'PL9')], project.connections);
		expect(reachable(island, 'R1').has('PL9')).toBe(false);
		expect(reachable(island, 'PL9')).toEqual(new Set(['PL9']));
		expect(pathTo(island, 'R1', 'PL9')).toBeNull();
	});

	it('give the shortest path as navigator steps', () => {
		const project = gravityBranchExample();
		expect(pathTo(project, 'R1', 'R2')).toEqual([
			{ componentId: 'R1' },
			{ componentId: 'T1', viaConnectionId: 'L1' },
			{ componentId: 'V1', viaConnectionId: 'L2' },
			{ componentId: 'R2', viaConnectionId: 'L3' }
		]);
		expect(pathTo(project, 'R3', 'V1')).toEqual([
			{ componentId: 'R3' },
			{ componentId: 'T1', viaConnectionId: 'L4' },
			{ componentId: 'V1', viaConnectionId: 'L2' }
		]);
		expect(pathTo(project, 'T1', 'T1')).toEqual([{ componentId: 'T1' }]);
		// Around a loop, the shorter way wins.
		const loop = closedLoopExample();
		expect(pathTo(loop, 'N1', 'V1')?.map((s) => s.componentId)).toEqual(['N1', 'T1', 'V1']);
	});
});

describe('validPathPrefix', () => {
	it('keeps a path that is still valid', () => {
		const project = pumpTransferExample();
		const path = pathTo(project, 'R1', 'R2')!;
		expect(validPathPrefix(project, path)).toEqual(path);
	});

	it('cuts a path at the first step that no longer exists or no longer joins', () => {
		const project = pumpTransferExample();
		const path = pathTo(project, 'R1', 'R2')!;
		const noValve = {
			...project,
			components: project.components.filter((c) => c.id !== 'V1'),
			connections: project.connections.filter((c) => c.id !== 'L2' && c.id !== 'L3')
		};
		expect(validPathPrefix(noValve, path)).toEqual(path.slice(0, 2));
		const rewired = {
			...project,
			connections: project.connections.map((c) =>
				c.id === 'L2' ? { ...c, toComponentId: 'R2', toPortId: 'port_1' } : c
			)
		};
		expect(validPathPrefix(rewired, path)).toEqual(path.slice(0, 2));
		expect(validPathPrefix(project, [{ componentId: 'gone' }])).toEqual([]);
		expect(validPathPrefix(project, [{ componentId: 'P1', viaConnectionId: 'L1' }])).toEqual([
			{ componentId: 'P1' }
		]);
	});
});

describe('port roles', () => {
	it('come from port direction, then from standard port names', () => {
		const roles = (kind: Parameters<typeof createComponent>[0]) => {
			const c = createComponent(kind, empty);
			return Object.fromEntries(c.ports.map((p) => [p.id, portRole(c, p.id)]));
		};
		expect(roles('pump')).toEqual({ suction: 'in', discharge: 'out' });
		expect(roles('gate')).toEqual({ inlet: 'in', outlet: 'out' });
		expect(roles('tee')).toEqual({ run_inlet: 'in', run_outlet: 'out', branch: 'out' });
		expect(roles('wye')).toEqual({ inlet: 'in', outlet_1: 'out', outlet_2: 'out' });
		expect(roles('reservoir')).toEqual({ port_1: 'any' });
		expect(roles('plug')).toEqual({ port_1: 'any' });
	});

	it('pick the inlet and outlet ports', () => {
		const pick = (kind: Parameters<typeof createComponent>[0]) => {
			const c = createComponent(kind, empty);
			return [inletPort(c)?.id, outletPort(c)?.id];
		};
		expect(pick('pump')).toEqual(['suction', 'discharge']);
		expect(pick('check')).toEqual(['inlet', 'outlet']);
		expect(pick('tee')).toEqual(['run_inlet', 'run_outlet']);
		expect(pick('wye')).toEqual(['inlet', 'outlet_1']);
		expect(pick('reservoir')).toEqual(['port_1', 'port_1']);
	});
});
