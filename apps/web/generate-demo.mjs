/**
 * Generate a demo project: Reservoir -> Valve -> Pump -> Valve -> Tank
 * Run with: node generate-demo.mjs
 */

import pako from 'pako';

// Helper: Convert Uint8Array to base64url
function uint8ArrayToBase64Url(bytes) {
	const binary = Array.from(bytes, (byte) => String.fromCharCode(byte)).join('');
	const base64 = Buffer.from(binary, 'binary').toString('base64');
	return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

// Create the project
const project = {
	id: 'demo_valve_pump_system',
	metadata: {
		name: 'Demo: Reservoir → Valve → Pump → Valve → Tank',
		description: 'A complete pump system with suction and discharge isolation valves.',
		created: new Date().toISOString(),
		modified: new Date().toISOString(),
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
		// 1. RESERVOIR - Water source at ground level
		{
			id: 'reservoir_1',
			type: 'reservoir',
			name: 'Supply Reservoir',
			elevation: 0,
			water_level: 10,
			ports: [{ id: 'outlet_1', nominal_size: 4, direction: 'bidirectional' }],
			downstream_connections: []
		},
		// 2. SUCTION VALVE - Gate valve before pump
		{
			id: 'valve_suction',
			type: 'valve',
			name: 'Suction Isolation Valve',
			elevation: 0,
			valve_type: 'gate',
			position: 1.0,
			ports: [
				{ id: 'inlet', nominal_size: 4, direction: 'inlet' },
				{ id: 'outlet', nominal_size: 4, direction: 'outlet' }
			],
			downstream_connections: []
		},
		// 3. PUMP - Main pump
		{
			id: 'pump_1',
			type: 'pump',
			name: 'Main Pump',
			elevation: 0,
			curve_id: 'curve_1',
			speed: 1.0,
			status: 'on',
			ports: [
				{ id: 'suction', nominal_size: 4, direction: 'inlet' },
				{ id: 'discharge', nominal_size: 4, direction: 'outlet' }
			],
			downstream_connections: []
		},
		// 4. DISCHARGE VALVE - Check valve after pump
		{
			id: 'valve_discharge',
			type: 'valve',
			name: 'Discharge Check Valve',
			elevation: 0,
			valve_type: 'check',
			ports: [
				{ id: 'inlet', nominal_size: 4, direction: 'inlet' },
				{ id: 'outlet', nominal_size: 4, direction: 'outlet' }
			],
			downstream_connections: []
		},
		// 5. TANK - Elevated storage tank
		{
			id: 'tank_1',
			type: 'tank',
			name: 'Storage Tank',
			elevation: 50,
			diameter: 12,
			min_level: 0,
			max_level: 20,
			initial_level: 5,
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
					nominal_diameter: 4,
					length: 15
				},
				fittings: [
					{ type: 'elbow_90_lr', quantity: 1 },
					{ type: 'entrance_sharp', quantity: 1 }
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
					length: 5
				},
				fittings: [{ type: 'reducer_concentric', quantity: 1 }]
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
					length: 3
				},
				fittings: []
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
					length: 80
				},
				fittings: [
					{ type: 'elbow_90_lr', quantity: 4 },
					{ type: 'gate_valve', quantity: 1 }
				]
			}
		}
	],
	pump_library: [
		{
			id: 'curve_1',
			name: 'Centrifugal Pump 4x4',
			points: [
				{ flow: 0, head: 130 },
				{ flow: 50, head: 128 },
				{ flow: 100, head: 122 },
				{ flow: 150, head: 112 },
				{ flow: 200, head: 98 },
				{ flow: 250, head: 80 },
				{ flow: 300, head: 58 },
				{ flow: 350, head: 32 }
			]
		}
	]
};

// Encode the project
const json = JSON.stringify(project);
const jsonBytes = new TextEncoder().encode(json);
const compressed = pako.gzip(jsonBytes, { level: 6 });
const encoded = uint8ArrayToBase64Url(compressed);

console.log('=== Project Encoded Successfully ===\n');
console.log('Original JSON size:', json.length, 'bytes');
console.log('Compressed size:', compressed.length, 'bytes');
console.log('Encoded URL length:', encoded.length, 'characters');
console.log('\n=== Shareable URL ===\n');
console.log('http://localhost:5173/p/' + encoded);
console.log('\n=== Encoded String ===\n');
console.log(encoded);
