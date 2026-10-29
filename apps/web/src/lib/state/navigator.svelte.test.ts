/**
 * Navigator state (SDD §3.1.1), compiled for the browser so its derived path reacts to edits.
 */
import { describe, expect, it } from 'vitest';
import { testWorkspace } from '../testing/workspace';
import { insertComponentInConnection } from '../utils/edit';
import { closedLoopProject } from '../testing/closed-loop';
import { gravityBranchExample, pumpTransferExample } from '../utils/examples';
import { createComponent, createEmptyProject } from '../utils/factory';
import {
	arrivalPortId,
	connectionBetween,
	defaultActivePort,
	pathAfterInsert,
	resolvePath
} from './navigator.svelte';

describe('navigator helpers', () => {
	it('resolves a path to its valid part, or a new walk from the default start', () => {
		const project = pumpTransferExample();
		const path = [
			{ componentId: 'R1' },
			{ componentId: 'P1', viaConnectionId: 'L1' },
			{ componentId: 'V1', viaConnectionId: 'L1' } // wrong connection: cut here
		];
		expect(resolvePath(project, path)).toEqual(path.slice(0, 2));
		expect(resolvePath(project, [{ componentId: 'gone' }])).toEqual([{ componentId: 'R1' }]);
		expect(resolvePath(createEmptyProject(), [])).toEqual([]);
	});

	it('finds the arrival port and the default port onward', () => {
		const project = pumpTransferExample();
		const path = [{ componentId: 'R1' }, { componentId: 'P1', viaConnectionId: 'L1' }];
		expect(arrivalPortId(project, path)).toBe('suction');
		expect(defaultActivePort(project, path)).toBe('discharge');
		expect(defaultActivePort(project, [{ componentId: 'R1' }])).toBe('port_1');
	});

	it('finds a connection between two components in either direction', () => {
		const project = pumpTransferExample();
		expect(connectionBetween(project, 'P1', 'R1')?.id).toBe('L1');
		expect(connectionBetween(project, 'R1', 'V1')).toBeUndefined();
		expect(connectionBetween(project, 'R1', 'P1', new Set(['L1']))).toBeUndefined();
	});

	it('places an inserted component before or after the current one', () => {
		const base = pumpTransferExample();
		const path = [{ componentId: 'R1' }, { componentId: 'P1', viaConnectionId: 'L1' }];

		const before = createComponent('check', base);
		const withBefore = insertComponentInConnection(base, 'L1', before);
		expect(pathAfterInsert(withBefore, path, before.id, 'L1')).toEqual([
			{ componentId: 'R1' },
			{ componentId: before.id, viaConnectionId: 'L1' }
		]);

		const after = createComponent('gate', base);
		const withAfter = insertComponentInConnection(base, 'L2', after);
		const onward = pathAfterInsert(withAfter, path, after.id, 'L2');
		expect(onward).toEqual([...path, { componentId: after.id, viaConnectionId: 'L2' }]);
	});
});

describe('NavigatorStore', () => {
	it('moves on when there is one way forward and asks at a branch', () => {
		const { nav } = testWorkspace(gravityBranchExample());
		expect(nav.current?.id).toBe('R1');
		expect(nav.next()).toBe('moved');
		expect(nav.current?.id).toBe('T1');
		expect(nav.next()).toBe('choose');
		expect(nav.options.map((o) => [o.otherId, o.portId, o.loop])).toEqual([
			['V1', 'run_outlet', false],
			['R3', 'branch', false]
		]);
		nav.choose(nav.options[1]!);
		expect(nav.path.map((s) => s.componentId)).toEqual(['R1', 'T1', 'R3']);
		expect(nav.next()).toBe('none');
	});

	it('jumps back along the path for a loop option', () => {
		const { nav } = testWorkspace(closedLoopProject());
		nav.setPath([
			{ componentId: 'N1' },
			{ componentId: 'T1', viaConnectionId: 'L1' },
			{ componentId: 'P1', viaConnectionId: 'L2' },
			{ componentId: 'V1', viaConnectionId: 'L3' }
		]);
		expect(nav.next()).toBe('choose');
		const [loop] = nav.options;
		expect(loop).toMatchObject({ otherId: 'T1', loop: true, loopIndex: 1 });
		nav.choose(loop!);
		expect(nav.path.map((s) => s.componentId)).toEqual(['N1', 'T1']);
	});

	it('follows the path through edits, undo and redo', () => {
		const ws = testWorkspace(pumpTransferExample());
		const { nav, store } = ws;
		nav.next();
		nav.next();
		expect(nav.current?.id).toBe('V1');
		ws.remove('V1', true);
		expect(nav.current?.id).toBe('P1');
		store.undo();
		// Undo restores the component and its connection, and with them the walk to it.
		expect(nav.current?.id).toBe('V1');
		store.redo();
		expect(nav.current?.id).toBe('P1');
	});

	it('keeps the piping view on the chosen port until the walk moves', () => {
		const { nav } = testWorkspace(pumpTransferExample());
		nav.next();
		expect(nav.mode).toBe('component');
		expect(nav.activePortId).toBe('discharge');
		nav.showConnection('suction');
		expect(nav.mode).toBe('connection');
		expect(nav.activePortId).toBe('suction');
		expect(nav.activeConnection?.id).toBe('L1');
		nav.next();
		expect(nav.mode).toBe('component');
		expect(nav.activePortId).toBe('outlet');
	});

	it('jumps to a component by the shortest path, or starts a new walk there', () => {
		const ws = testWorkspace(gravityBranchExample());
		ws.nav.jumpTo('R2');
		expect(ws.nav.path.map((s) => s.componentId)).toEqual(['R1', 'T1', 'V1', 'R2']);
		ws.nav.jumpTo('T1');
		expect(ws.nav.path.map((s) => s.componentId)).toEqual(['R1', 'T1']);
		// A component not connected to the start begins its own walk.
		ws.addStandalone('plug');
		expect(ws.nav.path).toEqual([{ componentId: 'PL1' }]);
	});

	it('moves to an element shown from the results along the walk, keeping its neighbours', () => {
		const ws = testWorkspace(pumpTransferExample());
		ws.inspect({ kind: 'component', id: 'P1' });
		expect(ws.nav.path.map((s) => s.componentId)).toEqual(['R1', 'P1']);
		expect(ws.nav.options.map((o) => o.otherId)).toEqual(['V1']);
		// A connection: its 'from' component, with that connection's piping open.
		ws.showElement({ kind: 'connection', id: 'L3' });
		expect(ws.nav.path.map((s) => s.componentId)).toEqual(['R1', 'P1', 'V1']);
		expect(ws.nav.mode).toBe('connection');
		expect(ws.nav.activePortId).toBe('outlet');
		// Back along the walk to an element already on it.
		ws.inspect({ kind: 'component', id: 'R1' });
		expect(ws.nav.path).toEqual([{ componentId: 'R1' }]);
	});
});
