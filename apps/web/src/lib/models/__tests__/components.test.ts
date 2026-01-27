/**
 * Tests for component model utility functions.
 */

import { describe, it, expect } from 'vitest';
import {
	getPortElevation,
	createReservoirPorts,
	createPumpPorts,
	createTankPorts,
	type Component,
	type Port
} from '../components';

describe('getPortElevation', () => {
	it('returns component elevation when port has no elevation', () => {
		const component: Component = {
			id: 'R1',
			type: 'reservoir',
			name: 'Test Reservoir',
			elevation: 100,
			water_level: 10,
			surface_pressure: 0,
			ports: createReservoirPorts(4.0),
			downstream_connections: []
		};

		expect(getPortElevation(component, 'P1')).toBe(100);
	});

	it('returns port elevation when explicitly set', () => {
		const ports: Port[] = [
			{ id: 'P1', name: 'Bottom Drain', nominal_size: 4.0, direction: 'bidirectional', elevation: 95 },
			{ id: 'P2', name: 'Side Fill', nominal_size: 6.0, direction: 'bidirectional', elevation: 105 },
			{ id: 'P3', name: 'Top Overflow', nominal_size: 4.0, direction: 'bidirectional', elevation: 120 }
		];

		const component: Component = {
			id: 'T1',
			type: 'tank',
			name: 'Test Tank',
			elevation: 100,
			diameter: 10,
			min_level: 0,
			max_level: 20,
			initial_level: 10,
			surface_pressure: 0,
			ports,
			downstream_connections: []
		};

		expect(getPortElevation(component, 'P1')).toBe(95);
		expect(getPortElevation(component, 'P2')).toBe(105);
		expect(getPortElevation(component, 'P3')).toBe(120);
	});

	it('returns 0 when port elevation is explicitly set to 0', () => {
		const ports: Port[] = [
			{ id: 'P1', name: 'Outlet', nominal_size: 4.0, direction: 'bidirectional', elevation: 0 }
		];

		const component: Component = {
			id: 'R1',
			type: 'reservoir',
			name: 'Test Reservoir',
			elevation: 50, // Component at 50 ft
			water_level: 10,
			surface_pressure: 0,
			ports,
			downstream_connections: []
		};

		// Port elevation is explicitly 0, should not inherit 50
		expect(getPortElevation(component, 'P1')).toBe(0);
	});

	it('supports negative port elevations', () => {
		const ports: Port[] = [
			{ id: 'P1', name: 'Bottom', nominal_size: 4.0, direction: 'bidirectional', elevation: -25 }
		];

		const component: Component = {
			id: 'T1',
			type: 'tank',
			name: 'Underground Tank',
			elevation: -10, // Tank top at -10 ft
			diameter: 10,
			min_level: 0,
			max_level: 20,
			initial_level: 10,
			surface_pressure: 0,
			ports,
			downstream_connections: []
		};

		expect(getPortElevation(component, 'P1')).toBe(-25);
	});

	it('handles mixed ports - some with elevation, some without', () => {
		const ports: Port[] = [
			{ id: 'P1', name: 'Suction', nominal_size: 6.0, direction: 'inlet', elevation: 5 }, // Explicit elevation
			{ id: 'P2', name: 'Discharge', nominal_size: 4.0, direction: 'outlet' } // No elevation, inherits
		];

		const component: Component = {
			id: 'PMP1',
			type: 'pump',
			name: 'Vertical Pump',
			elevation: 10, // Pump body at 10 ft
			curve_id: 'PC1',
			speed: 1.0,
			status: 'on',
			ports,
			downstream_connections: []
		};

		expect(getPortElevation(component, 'P1')).toBe(5); // Uses explicit elevation
		expect(getPortElevation(component, 'P2')).toBe(10); // Inherits component elevation
	});

	it('throws error for non-existent port', () => {
		const component: Component = {
			id: 'R1',
			type: 'reservoir',
			name: 'Test Reservoir',
			elevation: 100,
			water_level: 10,
			surface_pressure: 0,
			ports: createReservoirPorts(4.0),
			downstream_connections: []
		};

		expect(() => getPortElevation(component, 'nonexistent_port')).toThrow(
			"Port 'nonexistent_port' not found on component 'R1'"
		);
	});
});

describe('Port interface', () => {
	it('allows port creation without elevation (undefined)', () => {
		const port: Port = {
			id: 'P1',
			name: 'Port',
			nominal_size: 4.0,
			direction: 'bidirectional'
		};

		expect(port.elevation).toBeUndefined();
	});

	it('allows port creation with explicit elevation', () => {
		const port: Port = {
			id: 'P1',
			name: 'Port',
			nominal_size: 4.0,
			direction: 'bidirectional',
			elevation: 15.5
		};

		expect(port.elevation).toBe(15.5);
	});

	it('allows port creation with zero elevation', () => {
		const port: Port = {
			id: 'P1',
			name: 'Port',
			nominal_size: 4.0,
			direction: 'bidirectional',
			elevation: 0
		};

		expect(port.elevation).toBe(0);
	});

	it('allows port creation with negative elevation', () => {
		const port: Port = {
			id: 'P1',
			name: 'Port',
			nominal_size: 4.0,
			direction: 'bidirectional',
			elevation: -10
		};

		expect(port.elevation).toBe(-10);
	});
});

describe('Port factory functions', () => {
	it('createReservoirPorts returns ports without elevation (undefined)', () => {
		const ports = createReservoirPorts(4.0);
		expect(ports[0].elevation).toBeUndefined();
	});

	it('createTankPorts returns ports without elevation (undefined)', () => {
		const ports = createTankPorts(4.0);
		expect(ports[0].elevation).toBeUndefined();
	});

	it('createPumpPorts returns ports without elevation (undefined)', () => {
		const ports = createPumpPorts(6.0, 4.0);
		expect(ports[0].elevation).toBeUndefined();
		expect(ports[1].elevation).toBeUndefined();
	});
});
