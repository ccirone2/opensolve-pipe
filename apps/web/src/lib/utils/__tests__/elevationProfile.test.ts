import { describe, it, expect } from 'vitest';
import { buildElevationData } from '../elevationProfile';
import type { Component, PipeConnection, Reservoir, Tank, Junction, PumpComponent } from '$lib/models/components';
import type { SolvedState } from '$lib/models/results';

function makeReservoir(id: string, name: string, elevation: number, waterLevel: number): Reservoir {
	return {
		type: 'reservoir',
		id,
		name,
		elevation,
		water_level: waterLevel,
		surface_pressure: 0,
		ports: [{ id: 'P1', name: 'Outlet', nominal_size: 4, direction: 'outlet' }],
		downstream_connections: []
	};
}

function makeTank(
	id: string,
	name: string,
	elevation: number,
	minLevel: number,
	maxLevel: number,
	initialLevel: number
): Tank {
	return {
		type: 'tank',
		id,
		name,
		elevation,
		diameter: 10,
		min_level: minLevel,
		max_level: maxLevel,
		initial_level: initialLevel,
		surface_pressure: 0,
		ports: [{ id: 'P1', name: 'Inlet', nominal_size: 4, direction: 'inlet' }],
		downstream_connections: []
	};
}

function makeJunction(id: string, name: string, elevation: number): Junction {
	return {
		type: 'junction',
		id,
		name,
		elevation,
		demand: 0,
		ports: [
			{ id: 'P1', name: 'Inlet', nominal_size: 4, direction: 'inlet' },
			{ id: 'P2', name: 'Outlet', nominal_size: 4, direction: 'outlet' }
		],
		downstream_connections: []
	};
}

function makePump(id: string, name: string, elevation: number): PumpComponent {
	return {
		type: 'pump',
		id,
		name,
		elevation,
		curve_id: 'curve-1',
		speed: 1.0,
		operating_mode: 'fixed_speed',
		status: 'running',
		viscosity_correction_enabled: true,
		ports: [
			{ id: 'P1', name: 'Suction', nominal_size: 4, direction: 'inlet' },
			{ id: 'P2', name: 'Discharge', nominal_size: 4, direction: 'outlet' }
		],
		downstream_connections: []
	};
}

function makeConnection(
	id: string,
	fromId: string,
	fromPort: string,
	toId: string,
	toPort: string,
	pipeLength: number
): PipeConnection {
	return {
		id,
		from_component_id: fromId,
		from_port_id: fromPort,
		to_component_id: toId,
		to_port_id: toPort,
		piping: {
			pipe: {
				material: 'carbon_steel',
				nominal_diameter: 4,
				schedule: '40',
				length: pipeLength
			},
			fittings: []
		}
	};
}

describe('buildElevationData', () => {
	it('returns empty array for empty components', () => {
		expect(buildElevationData([], [], null)).toEqual([]);
	});

	it('builds a simple linear network (reservoir → pump → tank)', () => {
		const reservoir = makeReservoir('r1', 'Supply Reservoir', 100, 20);
		const pump = makePump('p1', 'Main Pump', 95);
		const tank = makeTank('t1', 'Storage Tank', 110, 5, 15, 10);

		const components: Component[] = [reservoir, pump, tank];
		const connections: PipeConnection[] = [
			makeConnection('c1', 'r1', 'P1', 'p1', 'P1', 50),
			makeConnection('c2', 'p1', 'P2', 't1', 'P1', 200)
		];

		const result = buildElevationData(components, connections, null);

		// Should produce: comp(reservoir), conn, comp(pump), conn, comp(tank)
		expect(result).toHaveLength(5);
		expect(result[0].type).toBe('comp');
		expect(result[0].name).toBe('Supply Reservoir');
		expect(result[0].p1_el).toBe(100);
		expect(result[0].max_el).toBe(120); // elevation + water_level

		expect(result[1].type).toBe('conn');
		expect(result[1].length).toBe(50);

		expect(result[2].type).toBe('comp');
		expect(result[2].name).toBe('Main Pump');

		expect(result[3].type).toBe('conn');
		expect(result[3].length).toBe(200);

		expect(result[4].type).toBe('comp');
		expect(result[4].name).toBe('Storage Tank');
		expect(result[4].min_el).toBe(115); // 110 + 5
		expect(result[4].max_el).toBe(125); // 110 + 15
	});

	it('maps head_change from solved results', () => {
		const reservoir = makeReservoir('r1', 'Reservoir', 100, 20);
		const junction = makeJunction('j1', 'Junction', 100);

		const components: Component[] = [reservoir, junction];
		const connections: PipeConnection[] = [
			makeConnection('c1', 'r1', 'P1', 'j1', 'P1', 100)
		];

		const solvedState: SolvedState = {
			converged: true,
			iterations: 5,
			timestamp: '2026-01-01T00:00:00Z',
			component_results: {
				r1: { component_id: 'r1', port_id: 'P1', pressure: 10, dynamic_pressure: 0, total_pressure: 10, hgl: 120, egl: 120 },
				j1: { component_id: 'j1', port_id: 'P1', pressure: 8, dynamic_pressure: 0, total_pressure: 8, hgl: 118, egl: 118 }
			},
			piping_results: {
				c1: {
					component_id: 'c1',
					upstream_component_id: 'r1',
					downstream_component_id: 'j1',
					flow: 100,
					velocity: 3.5,
					head_loss: 2.5,
					friction_head_loss: 2.0,
					minor_head_loss: 0.5,
					reynolds_number: 100000,
					friction_factor: 0.02,
					regime: 'turbulent'
				}
			},
			pump_results: {},
			control_valve_results: {},
			warnings: []
		};

		const result = buildElevationData(components, connections, solvedState);
		const connElement = result.find((e) => e.type === 'conn');
		expect(connElement?.head_change).toBe(-2.5); // negated head_loss
	});

	it('handles single component with no connections', () => {
		const reservoir = makeReservoir('r1', 'Alone', 100, 10);
		const result = buildElevationData([reservoir], [], null);

		expect(result).toHaveLength(1);
		expect(result[0].type).toBe('comp');
		expect(result[0].name).toBe('Alone');
		expect(result[0].max_el).toBe(110);
	});

	it('handles missing results gracefully', () => {
		const reservoir = makeReservoir('r1', 'Reservoir', 100, 20);
		const junction = makeJunction('j1', 'Junction', 95);

		const components: Component[] = [reservoir, junction];
		const connections: PipeConnection[] = [
			makeConnection('c1', 'r1', 'P1', 'j1', 'P1', 100)
		];

		const result = buildElevationData(components, connections, undefined);
		expect(result).toHaveLength(3);

		const conn = result.find((e) => e.type === 'conn');
		expect(conn?.head_change).toBeUndefined();
	});
});
