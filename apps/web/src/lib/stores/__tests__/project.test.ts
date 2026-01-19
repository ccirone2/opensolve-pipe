import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import {
	projectStore,
	components,
	pumpLibrary,
	fluid,
	settings,
	solvedState,
	isSolved,
	getComponent,
	getPumpCurve
} from '../project';
import { canUndo, canRedo } from '../history';
import type { PumpCurve } from '$lib/models';

describe('projectStore', () => {
	beforeEach(() => {
		projectStore.createNew();
	});

	describe('initialization', () => {
		it('creates a new empty project', () => {
			const project = get(projectStore);
			expect(project.id).toBeTruthy();
			expect(project.metadata.name).toBe('Untitled Project');
			expect(project.components).toEqual([]);
			expect(project.pump_library).toEqual([]);
			expect(project.results).toBeUndefined();
		});

		it('initializes with default fluid (water)', () => {
			const f = get(fluid);
			expect(f.type).toBe('water');
			expect(f.temperature).toBe(68.0);
		});

		it('initializes with imperial units', () => {
			const s = get(settings);
			expect(s.units.system).toBe('imperial');
			expect(s.units.flow).toBe('GPM');
		});
	});

	describe('component operations', () => {
		it('adds a component', () => {
			const id = projectStore.addComponent('reservoir');
			expect(id).toBeTruthy();

			const comps = get(components);
			expect(comps).toHaveLength(1);
			expect(comps[0].id).toBe(id);
			expect(comps[0].type).toBe('reservoir');
		});

		it('adds a component at specific index', () => {
			projectStore.addComponent('reservoir');
			projectStore.addComponent('junction');
			projectStore.addComponent('pump', 1);

			const comps = get(components);
			expect(comps).toHaveLength(3);
			expect(comps[0].type).toBe('reservoir');
			expect(comps[1].type).toBe('pump');
			expect(comps[2].type).toBe('junction');
		});

		it('removes a component', () => {
			const id = projectStore.addComponent('reservoir');
			expect(get(components)).toHaveLength(1);

			projectStore.removeComponent(id);
			expect(get(components)).toHaveLength(0);
		});

		it('updates a component', () => {
			const id = projectStore.addComponent('reservoir');
			projectStore.updateComponent(id, { name: 'Main Reservoir', elevation: 100 });

			const comp = getComponent(id);
			expect(comp?.name).toBe('Main Reservoir');
			expect(comp?.elevation).toBe(100);
		});

		it('moves a component', () => {
			projectStore.addComponent('reservoir');
			const pumpId = projectStore.addComponent('pump');
			projectStore.addComponent('junction');

			projectStore.moveComponent(pumpId, 0);

			const comps = get(components);
			expect(comps[0].type).toBe('pump');
			expect(comps[1].type).toBe('reservoir');
		});
	});

	describe('connection operations', () => {
		it('adds a connection between components', () => {
			const id1 = projectStore.addComponent('reservoir');
			const id2 = projectStore.addComponent('junction');

			projectStore.addConnection(id1, id2);

			const comp = getComponent(id1);
			expect(comp?.downstream_connections).toHaveLength(1);
			expect(comp?.downstream_connections[0].target_component_id).toBe(id2);
		});

		it('removes a connection', () => {
			const id1 = projectStore.addComponent('reservoir');
			const id2 = projectStore.addComponent('junction');

			projectStore.addConnection(id1, id2);
			projectStore.removeConnection(id1, id2);

			const comp = getComponent(id1);
			expect(comp?.downstream_connections).toHaveLength(0);
		});

		it('removes connections when component is deleted', () => {
			const id1 = projectStore.addComponent('reservoir');
			const id2 = projectStore.addComponent('junction');

			projectStore.addConnection(id1, id2);
			projectStore.removeComponent(id2);

			const comp = getComponent(id1);
			expect(comp?.downstream_connections).toHaveLength(0);
		});
	});

	describe('pump curve operations', () => {
		it('adds a pump curve', () => {
			const curve: PumpCurve = {
				id: 'curve-1',
				name: 'Test Pump',
				points: [
					{ flow: 0, head: 100 },
					{ flow: 100, head: 80 }
				]
			};

			projectStore.addPumpCurve(curve);

			const curves = get(pumpLibrary);
			expect(curves).toHaveLength(1);
			expect(curves[0].name).toBe('Test Pump');
		});

		it('removes a pump curve', () => {
			const curve: PumpCurve = {
				id: 'curve-1',
				name: 'Test Pump',
				points: [
					{ flow: 0, head: 100 },
					{ flow: 100, head: 80 }
				]
			};

			projectStore.addPumpCurve(curve);
			projectStore.removePumpCurve('curve-1');

			expect(get(pumpLibrary)).toHaveLength(0);
		});

		it('updates a pump curve', () => {
			const curve: PumpCurve = {
				id: 'curve-1',
				name: 'Test Pump',
				points: [
					{ flow: 0, head: 100 },
					{ flow: 100, head: 80 }
				]
			};

			projectStore.addPumpCurve(curve);
			projectStore.updatePumpCurve('curve-1', { name: 'Updated Pump' });

			const updated = getPumpCurve('curve-1');
			expect(updated?.name).toBe('Updated Pump');
		});
	});

	describe('results operations', () => {
		it('sets results', () => {
			const results = {
				converged: true,
				iterations: 5,
				timestamp: new Date().toISOString(),
				node_results: {},
				link_results: {},
				pump_results: {},
				warnings: []
			};

			projectStore.setResults(results);

			expect(get(solvedState)).toBeDefined();
			expect(get(isSolved)).toBe(true);
		});

		it('clears results', () => {
			projectStore.setResults({
				converged: true,
				iterations: 5,
				timestamp: new Date().toISOString(),
				node_results: {},
				link_results: {},
				pump_results: {},
				warnings: []
			});

			projectStore.clearResults();

			expect(get(solvedState)).toBeUndefined();
			expect(get(isSolved)).toBe(false);
		});
	});

	describe('undo/redo', () => {
		it('can undo an action', () => {
			projectStore.addComponent('reservoir');
			expect(get(components)).toHaveLength(1);
			expect(get(canUndo)).toBe(true);

			const result = projectStore.undo();
			expect(result).toBe(true);
			expect(get(components)).toHaveLength(0);
		});

		it('can redo an undone action', () => {
			projectStore.addComponent('reservoir');
			projectStore.undo();
			expect(get(components)).toHaveLength(0);
			expect(get(canRedo)).toBe(true);

			const result = projectStore.redo();
			expect(result).toBe(true);
			expect(get(components)).toHaveLength(1);
		});

		it('clears redo stack on new action', () => {
			projectStore.addComponent('reservoir');
			projectStore.undo();
			expect(get(canRedo)).toBe(true);

			projectStore.addComponent('junction');
			expect(get(canRedo)).toBe(false);
		});
	});

	describe('metadata and settings', () => {
		it('updates metadata', () => {
			projectStore.updateMetadata({ name: 'My Project', author: 'Test User' });

			const project = get(projectStore);
			expect(project.metadata.name).toBe('My Project');
			expect(project.metadata.author).toBe('Test User');
		});

		it('updates settings', () => {
			projectStore.updateSettings({
				units: { ...get(settings).units, system: 'si', flow: 'L/s' }
			});

			const s = get(settings);
			expect(s.units.system).toBe('si');
			expect(s.units.flow).toBe('L/s');
		});

		it('updates fluid', () => {
			projectStore.updateFluid({ type: 'diesel', temperature: 77 });

			const f = get(fluid);
			expect(f.type).toBe('diesel');
			expect(f.temperature).toBe(77);
		});
	});
});
