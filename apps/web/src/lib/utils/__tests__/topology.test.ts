/**
 * Tests for topology validation utilities.
 */
import { describe, it, expect } from 'vitest';
import {
	validateTopology,
	wouldCreateInvalidLoop,
	getOrphanedComponents,
	hasLoops
} from '../topology';
import type { Component, Reservoir, Junction, TeeBranch, Plug } from '$lib/models';

// Helper to create test components
function createReservoir(id: string, name: string, downstream: string[] = []): Reservoir {
	return {
		id,
		name,
		type: 'reservoir',
		elevation: 0,
		water_level: 100,
		surface_pressure: 0,
		ports: [],
		downstream_connections: downstream.map((targetId) => ({ target_component_id: targetId }))
	};
}

function createJunction(id: string, name: string, downstream: string[] = []): Junction {
	return {
		id,
		name,
		type: 'junction',
		elevation: 0,
		demand: 0,
		ports: [],
		downstream_connections: downstream.map((targetId) => ({ target_component_id: targetId }))
	};
}

function createTeeBranch(id: string, name: string, downstream: string[] = []): TeeBranch {
	return {
		id,
		name,
		type: 'tee_branch',
		elevation: 0,
		branch_angle: 90,
		ports: [],
		downstream_connections: downstream.map((targetId) => ({ target_component_id: targetId }))
	};
}

function createPlug(id: string, name: string): Plug {
	return {
		id,
		name,
		type: 'plug',
		elevation: 0,
		ports: [],
		downstream_connections: []
	};
}

describe('validateTopology', () => {
	it('should return valid for empty network', () => {
		const result = validateTopology([]);
		expect(result.isValid).toBe(true);
		expect(result.issues).toHaveLength(0);
	});

	it('should return valid for simple linear network', () => {
		const components: Component[] = [
			createReservoir('r1', 'Reservoir 1', ['j1']),
			createJunction('j1', 'Junction 1', ['p1']),
			createPlug('p1', 'Plug 1')
		];

		const result = validateTopology(components);
		expect(result.isValid).toBe(true);
		expect(result.errorCount).toBe(0);
	});

	it('should detect missing source', () => {
		const components: Component[] = [
			createJunction('j1', 'Junction 1', ['j2']),
			createJunction('j2', 'Junction 2')
		];

		const result = validateTopology(components);
		expect(result.isValid).toBe(false);
		expect(result.issues.some((i) => i.type === 'missing_source')).toBe(true);
	});

	it('should detect orphaned components', () => {
		const components: Component[] = [
			createReservoir('r1', 'Reservoir 1', ['j1']),
			createJunction('j1', 'Junction 1'),
			createJunction('j2', 'Orphaned Junction') // Not connected to network
		];

		const result = validateTopology(components);
		expect(result.isValid).toBe(false);
		expect(result.issues.some((i) => i.type === 'orphaned_component')).toBe(true);
		expect(
			result.issues.find((i) => i.type === 'orphaned_component')?.componentId
		).toBe('j2');
	});

	it('should detect self-loops', () => {
		const components: Component[] = [
			createReservoir('r1', 'Reservoir 1', ['j1']),
			{
				...createJunction('j1', 'Self Loop Junction'),
				downstream_connections: [{ target_component_id: 'j1' }] // Self-loop
			}
		];

		const result = validateTopology(components);
		expect(result.isValid).toBe(false);
		expect(result.issues.some((i) => i.type === 'self_loop')).toBe(true);
	});

	it('should allow branching networks', () => {
		const components: Component[] = [
			createReservoir('r1', 'Reservoir 1', ['t1']),
			createTeeBranch('t1', 'Tee 1', ['j1', 'j2']),
			createJunction('j1', 'Junction 1', ['p1']),
			createJunction('j2', 'Junction 2', ['p2']),
			createPlug('p1', 'Plug 1'),
			createPlug('p2', 'Plug 2')
		];

		const result = validateTopology(components);
		expect(result.isValid).toBe(true);
	});

	it('should warn about dangling sources', () => {
		const components: Component[] = [
			createReservoir('r1', 'Reservoir 1', []), // No downstream
			createJunction('j1', 'Junction 1')
		];

		const result = validateTopology(components);
		expect(result.issues.some((i) => i.type === 'dangling_endpoint')).toBe(true);
	});
});

describe('wouldCreateInvalidLoop', () => {
	it('should detect simple cycle creation', () => {
		const components: Component[] = [
			createReservoir('r1', 'Reservoir 1', ['j1']),
			createJunction('j1', 'Junction 1', ['j2']),
			createJunction('j2', 'Junction 2')
		];

		// Adding j2 -> j1 would create a cycle
		expect(wouldCreateInvalidLoop(components, 'j2', 'j1')).toBe(true);
	});

	it('should allow valid connections', () => {
		const components: Component[] = [
			createReservoir('r1', 'Reservoir 1', ['j1']),
			createJunction('j1', 'Junction 1'),
			createJunction('j2', 'Junction 2')
		];

		// Adding j1 -> j2 is valid (forward direction)
		expect(wouldCreateInvalidLoop(components, 'j1', 'j2')).toBe(false);
	});

	it('should detect indirect cycle', () => {
		const components: Component[] = [
			createReservoir('r1', 'Reservoir 1', ['j1']),
			createJunction('j1', 'Junction 1', ['j2']),
			createJunction('j2', 'Junction 2', ['j3']),
			createJunction('j3', 'Junction 3')
		];

		// Adding j3 -> j1 would create a cycle
		expect(wouldCreateInvalidLoop(components, 'j3', 'j1')).toBe(true);
	});
});

describe('getOrphanedComponents', () => {
	it('should return empty array for connected network', () => {
		const components: Component[] = [
			createReservoir('r1', 'Reservoir 1', ['j1']),
			createJunction('j1', 'Junction 1')
		];

		const orphaned = getOrphanedComponents(components);
		expect(orphaned).toHaveLength(0);
	});

	it('should return orphaned components', () => {
		const components: Component[] = [
			createReservoir('r1', 'Reservoir 1', ['j1']),
			createJunction('j1', 'Junction 1'),
			createJunction('j2', 'Orphaned')
		];

		const orphaned = getOrphanedComponents(components);
		expect(orphaned).toHaveLength(1);
		expect(orphaned[0].id).toBe('j2');
	});
});

describe('hasLoops', () => {
	it('should return false for linear network', () => {
		const components: Component[] = [
			createReservoir('r1', 'Reservoir 1', ['j1']),
			createJunction('j1', 'Junction 1', ['j2']),
			createJunction('j2', 'Junction 2')
		];

		expect(hasLoops(components)).toBe(false);
	});

	it('should return true for network with cycle', () => {
		const components: Component[] = [
			createReservoir('r1', 'Reservoir 1', ['j1']),
			createJunction('j1', 'Junction 1', ['j2']),
			{
				...createJunction('j2', 'Junction 2'),
				downstream_connections: [{ target_component_id: 'j1' }] // Creates cycle
			}
		];

		expect(hasLoops(components)).toBe(true);
	});

	it('should return false for branching without loops', () => {
		const components: Component[] = [
			createReservoir('r1', 'Reservoir 1', ['t1']),
			createTeeBranch('t1', 'Tee 1', ['j1', 'j2']),
			createJunction('j1', 'Junction 1'),
			createJunction('j2', 'Junction 2')
		];

		expect(hasLoops(components)).toBe(false);
	});
});
