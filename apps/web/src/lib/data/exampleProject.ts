/**
 * Example project for demonstrating OpenSolve Pipe.
 * This is a simple pump-to-junction system showing typical usage.
 */

import type { Project } from '$lib/models';
import { encodeProject } from '$lib/utils';

/** A simple pump system example: Reservoir -> Pump -> Junction with demand */
export const EXAMPLE_PROJECT: Project = {
	id: 'example_pump_system',
	metadata: {
		name: 'Example: Pump System',
		description: 'A simple pump system with reservoir, pump, and discharge junction.',
		created: '2026-01-01T00:00:00.000Z',
		modified: '2026-01-01T00:00:00.000Z',
		version: '1'
	},
	settings: {
		units: {
			system: 'imperial',
			length: 'ft',
			diameter: 'in',
			flow: 'GPM',
			pressure: 'psi',
			head: 'ft_head',
			velocity: 'ft/s',
			temperature: 'F',
			viscosity_kinematic: 'ft2/s',
			viscosity_dynamic: 'cP',
			density: 'lb/ft3'
		},
		enabled_checks: [],
		solver_options: {
			max_iterations: 100,
			tolerance: 0.001,
			include_system_curve: true,
			flow_range_min: 0,
			flow_range_max: 500,
			flow_points: 51
		}
	},
	fluid: {
		type: 'water',
		temperature: 68
	},
	components: [
		{
			id: 'reservoir_1',
			type: 'reservoir',
			name: 'Supply Tank',
			elevation: 0,
			water_level: 10,
			downstream_connections: [
				{
					target_component_id: 'pump_1',
					piping: {
						pipe: {
							material: 'carbon_steel',
							schedule: '40',
							nominal_diameter: 4,
							length: 20
						},
						fittings: [{ type: 'elbow_90_lr', quantity: 2 }]
					}
				}
			]
		},
		{
			id: 'pump_1',
			type: 'pump',
			name: 'Main Pump',
			elevation: 0,
			curve_id: 'curve_1',
			speed: 1.0,
			status: 'on',
			downstream_connections: [
				{
					target_component_id: 'junction_1',
					piping: {
						pipe: {
							material: 'carbon_steel',
							schedule: '40',
							nominal_diameter: 4,
							length: 100
						},
						fittings: [
							{ type: 'elbow_90_lr', quantity: 3 },
							{ type: 'gate_valve', quantity: 1 }
						]
					}
				}
			]
		},
		{
			id: 'junction_1',
			type: 'junction',
			name: 'Discharge Point',
			elevation: 50,
			demand: 200,
			downstream_connections: []
		}
	],
	pump_library: [
		{
			id: 'curve_1',
			name: 'Example Pump Curve',
			points: [
				{ flow: 0, head: 120 },
				{ flow: 100, head: 115 },
				{ flow: 200, head: 100 },
				{ flow: 300, head: 75 },
				{ flow: 400, head: 40 }
			]
		}
	]
};

/** Get the encoded URL for the example project. */
export function getExampleProjectUrl(): string {
	const result = encodeProject(EXAMPLE_PROJECT);
	return `/p/${result.encoded}`;
}
