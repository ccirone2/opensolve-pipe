/**
 * Example project for demonstrating OpenSolve Pipe.
 * A typical industrial pumping system: Reservoir → Valve → Pump → Valve → Tank
 */

import type { Project } from '$lib/models';
import { encodeProject } from '$lib/utils';

/** Example pumping system: Reservoir → Suction Valve → Pump → Discharge Valve → Storage Tank */
export const EXAMPLE_PROJECT: Project = {
	id: 'example_pump_system',
	metadata: {
		name: 'Example: Industrial Pump System',
		description:
			'A complete pumping system demonstrating reservoir supply, suction/discharge valves, centrifugal pump with efficiency curve, and elevated storage tank.',
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
		enabled_checks: ['velocity', 'pressure', 'npsh'],
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
		// ========================================
		// 1. Supply Reservoir
		// ========================================
		{
			id: 'reservoir_1',
			type: 'reservoir',
			name: 'Supply Reservoir',
			elevation: 0,
			water_level: 15,
			ports: [{ id: 'outlet_1', nominal_size: 6, direction: 'bidirectional' }],
			downstream_connections: [
				{
					target_component_id: 'valve_suction',
					piping: {
						pipe: {
							material: 'carbon_steel',
							schedule: '40',
							nominal_diameter: 6,
							length: 8
						},
						fittings: [
							{ type: 'entrance_rounded', quantity: 1 },
							{ type: 'gate_valve', quantity: 1 },
							{ type: 'reducer_eccentric', quantity: 1 }
						]
					}
				}
			]
		},
		// ========================================
		// 2. Suction Isolation Valve
		// ========================================
		{
			id: 'valve_suction',
			type: 'valve',
			name: 'Suction Isolation Valve',
			elevation: 0,
			valve_type: 'gate',
			position: 1.0,
			cv: 450,
			ports: [
				{ id: 'inlet', nominal_size: 4, direction: 'inlet' },
				{ id: 'outlet', nominal_size: 4, direction: 'outlet' }
			],
			downstream_connections: [
				{
					target_component_id: 'pump_1',
					piping: {
						pipe: {
							material: 'carbon_steel',
							schedule: '40',
							nominal_diameter: 4,
							length: 6
						},
						fittings: [
							{ type: 'elbow_90_lr', quantity: 1 },
							{ type: 'strainer_y', quantity: 1 }
						]
					}
				}
			]
		},
		// ========================================
		// 3. Centrifugal Pump
		// ========================================
		{
			id: 'pump_1',
			type: 'pump',
			name: 'Main Process Pump',
			elevation: 0,
			curve_id: 'curve_1',
			speed: 1.0,
			status: 'on',
			ports: [
				{ id: 'suction', nominal_size: 4, direction: 'inlet' },
				{ id: 'discharge', nominal_size: 4, direction: 'outlet' }
			],
			downstream_connections: [
				{
					target_component_id: 'valve_discharge',
					piping: {
						pipe: {
							material: 'carbon_steel',
							schedule: '40',
							nominal_diameter: 4,
							length: 5
						},
						fittings: [{ type: 'check_valve_swing', quantity: 1 }]
					}
				}
			]
		},
		// ========================================
		// 4. Discharge Control Valve
		// ========================================
		{
			id: 'valve_discharge',
			type: 'valve',
			name: 'Discharge Control Valve',
			elevation: 2,
			valve_type: 'globe',
			position: 0.85,
			cv: 200,
			ports: [
				{ id: 'inlet', nominal_size: 4, direction: 'inlet' },
				{ id: 'outlet', nominal_size: 4, direction: 'outlet' }
			],
			downstream_connections: [
				{
					target_component_id: 'tank_1',
					piping: {
						pipe: {
							material: 'carbon_steel',
							schedule: '40',
							nominal_diameter: 4,
							length: 150
						},
						fittings: [
							{ type: 'elbow_90_lr', quantity: 4 },
							{ type: 'tee_through', quantity: 1 },
							{ type: 'gate_valve', quantity: 2 },
							{ type: 'exit', quantity: 1 }
						]
					}
				}
			]
		},
		// ========================================
		// 5. Storage Tank
		// ========================================
		{
			id: 'tank_1',
			type: 'tank',
			name: 'Elevated Storage Tank',
			elevation: 75,
			diameter: 20,
			min_level: 2,
			max_level: 25,
			initial_level: 10,
			ports: [{ id: 'port_1', nominal_size: 4, direction: 'bidirectional' }],
			downstream_connections: []
		}
	],
	connections: [
		{
			id: 'conn_1',
			from_component_id: 'reservoir_1',
			from_port_id: 'outlet_1',
			to_component_id: 'valve_suction',
			to_port_id: 'inlet',
			piping: {
				pipe: {
					material: 'carbon_steel',
					schedule: '40',
					nominal_diameter: 6,
					length: 8
				},
				fittings: [
					{ type: 'entrance_rounded', quantity: 1 },
					{ type: 'gate_valve', quantity: 1 },
					{ type: 'reducer_eccentric', quantity: 1 }
				]
			}
		},
		{
			id: 'conn_2',
			from_component_id: 'valve_suction',
			from_port_id: 'outlet',
			to_component_id: 'pump_1',
			to_port_id: 'suction',
			piping: {
				pipe: {
					material: 'carbon_steel',
					schedule: '40',
					nominal_diameter: 4,
					length: 6
				},
				fittings: [
					{ type: 'elbow_90_lr', quantity: 1 },
					{ type: 'strainer_y', quantity: 1 }
				]
			}
		},
		{
			id: 'conn_3',
			from_component_id: 'pump_1',
			from_port_id: 'discharge',
			to_component_id: 'valve_discharge',
			to_port_id: 'inlet',
			piping: {
				pipe: {
					material: 'carbon_steel',
					schedule: '40',
					nominal_diameter: 4,
					length: 5
				},
				fittings: [{ type: 'check_valve_swing', quantity: 1 }]
			}
		},
		{
			id: 'conn_4',
			from_component_id: 'valve_discharge',
			from_port_id: 'outlet',
			to_component_id: 'tank_1',
			to_port_id: 'port_1',
			piping: {
				pipe: {
					material: 'carbon_steel',
					schedule: '40',
					nominal_diameter: 4,
					length: 150
				},
				fittings: [
					{ type: 'elbow_90_lr', quantity: 4 },
					{ type: 'tee_through', quantity: 1 },
					{ type: 'gate_valve', quantity: 2 },
					{ type: 'exit', quantity: 1 }
				]
			}
		}
	],
	pump_library: [
		{
			id: 'curve_1',
			name: 'Goulds 3196 4x6-10',
			manufacturer: 'Goulds Pumps',
			model: '3196 4x6-10',
			rated_speed: 1750,
			impeller_diameter: 10,
			points: [
				{ flow: 0, head: 125 },
				{ flow: 50, head: 123 },
				{ flow: 100, head: 118 },
				{ flow: 150, head: 110 },
				{ flow: 200, head: 98 },
				{ flow: 250, head: 82 },
				{ flow: 300, head: 62 },
				{ flow: 350, head: 38 }
			],
			efficiency_curve: [
				{ flow: 50, efficiency: 0.45 },
				{ flow: 100, efficiency: 0.62 },
				{ flow: 150, efficiency: 0.74 },
				{ flow: 200, efficiency: 0.8 },
				{ flow: 250, efficiency: 0.78 },
				{ flow: 300, efficiency: 0.72 },
				{ flow: 350, efficiency: 0.6 }
			],
			npshr_curve: [
				{ flow: 50, npsh_required: 4 },
				{ flow: 100, npsh_required: 5 },
				{ flow: 150, npsh_required: 7 },
				{ flow: 200, npsh_required: 10 },
				{ flow: 250, npsh_required: 14 },
				{ flow: 300, npsh_required: 19 },
				{ flow: 350, npsh_required: 26 }
			]
		}
	]
};

/** Get the encoded URL for the example project. */
export function getExampleProjectUrl(): string {
	const result = encodeProject(EXAMPLE_PROJECT);
	return `/p/${result.encoded}`;
}
