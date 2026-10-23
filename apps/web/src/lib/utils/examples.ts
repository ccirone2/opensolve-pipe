/**
 * Example projects for the home page ("Open example").
 *
 * They are illustrative: elevations, pipe lengths and sizes, and pump curves are made-up user
 * inputs chosen to show the tool, not data for a real installation or a real pump. Pipe
 * dimensions and roughness, fitting K values and fluid properties are not set here; the
 * solver takes them from its cited library (carbon steel, schedule 40, by nominal size).
 */
import type { Component, Fitting, PipeConnection, Port, Project } from '../api/types';
import { createEmptyProject } from './factory';
import { INCH } from './units';

const ILLUSTRATIVE =
	'Illustrative example: the elevations, pipe lengths and sizes and the pump curve are ' +
	'made-up inputs to show the tool, not data for a real installation or pump.';

/** Fixed timestamp, so example links are stable. */
const EXAMPLE_DATE = '2026-10-21T00:00:00Z';

const NPS3 = 3 * INCH;
const NPS4 = 4 * INCH;

function pipe(
	id: string,
	from: [string, string],
	to: [string, string],
	nominalSize: number,
	length: number,
	fittings: Fitting[] = []
): PipeConnection {
	return {
		id,
		fromComponentId: from[0],
		fromPortId: from[1],
		toComponentId: to[0],
		toPortId: to[1],
		piping: {
			pipes: [{ materialId: 'carbon_steel', schedule: '40', nominalSize, length }],
			fittings
		}
	};
}

function fitting(type: Fitting['type'], quantity = 1): Fitting {
	return { type, quantity, pipeIndex: 0 };
}

function ports(...spec: [string, number, Port['direction']][]): Port[] {
	return spec.map(([id, nominalSize, direction]) => ({ id, nominalSize, direction }));
}

function base(id: string, name: string, description: string): Project {
	const project = createEmptyProject({ id, name, now: EXAMPLE_DATE });
	project.metadata.description = `${description} ${ILLUSTRATIVE}`;
	return project;
}

/** (1) Pump transfer between two tanks: R1 → pipe → P1 → pipe → gate valve → pipe → R2. */
export function pumpTransferExample(): Project {
	const project = base(
		'example-pump-transfer',
		'Pump transfer between two tanks',
		'Water at 20 °C pumped from a suction tank to a discharge tank 10 m higher.'
	);
	const components: Component[] = [
		{
			type: 'reservoir',
			id: 'R1',
			name: 'Suction tank',
			elevation: 0,
			liquidLevel: 3,
			surfacePressure: 0,
			ports: ports(['port_1', NPS4, 'bidirectional'])
		},
		{
			type: 'pump',
			id: 'P1',
			name: 'Transfer pump',
			elevation: 0,
			curveId: 'C1',
			speed: 1,
			status: 'on',
			ports: ports(['suction', NPS4, 'inlet'], ['discharge', NPS3, 'outlet'])
		},
		{
			type: 'valve',
			valveType: 'gate',
			id: 'V1',
			name: 'Discharge isolation valve',
			elevation: 0,
			status: 'active',
			ports: ports(['inlet', NPS3, 'inlet'], ['outlet', NPS3, 'outlet'])
		},
		{
			type: 'reservoir',
			id: 'R2',
			name: 'Discharge tank',
			elevation: 10,
			liquidLevel: 2,
			surfacePressure: 0,
			ports: ports(['port_1', NPS3, 'bidirectional'])
		}
	];
	return {
		...project,
		components,
		connections: [
			pipe('L1', ['R1', 'port_1'], ['P1', 'suction'], NPS4, 5, [fitting('entrance_sharp')]),
			pipe('L2', ['P1', 'discharge'], ['V1', 'inlet'], NPS3, 3),
			pipe('L3', ['V1', 'outlet'], ['R2', 'port_1'], NPS3, 60, [
				fitting('elbow_90_lr', 4),
				fitting('exit')
			])
		],
		pumpLibrary: [
			{
				id: 'C1',
				name: 'Example transfer pump curve (illustrative)',
				points: [
					{ flow: 0, head: 30 },
					{ flow: 0.01, head: 28 },
					{ flow: 0.02, head: 22 },
					{ flow: 0.03, head: 12 }
				],
				efficiencyCurve: [
					{ flow: 0.005, efficiency: 0.45 },
					{ flow: 0.015, efficiency: 0.7 },
					{ flow: 0.025, efficiency: 0.6 }
				],
				npshrCurve: [
					{ flow: 0.005, npshr: 1.5 },
					{ flow: 0.015, npshr: 2.5 },
					{ flow: 0.03, npshr: 5 }
				]
			}
		]
	};
}

/**
 * (2) Gravity-fed branched network: an elevated tank feeds a tee; one branch runs through a
 * globe valve to tank A, the other to tank B. No pump. The tee's run is NPS 4 on both sides (the
 * Crane tee correlations assume equal run diameters, so the example solves without a range
 * flag), reducing to NPS 3 one metre after the tee.
 */
export function gravityBranchExample(): Project {
	const project = base(
		'example-gravity-branch',
		'Gravity-fed branched network',
		'An elevated tank supplies two lower tanks through a tee; the run reduces from NPS 4 to ' +
			'NPS 3 just after the tee. No pump.'
	);
	const components: Component[] = [
		{
			type: 'reservoir',
			id: 'R1',
			name: 'Elevated tank',
			elevation: 40,
			liquidLevel: 3,
			surfacePressure: 0,
			ports: ports(['port_1', NPS4, 'bidirectional'])
		},
		{
			type: 'branch',
			branchType: 'tee',
			id: 'T1',
			name: 'Distribution tee',
			elevation: 10,
			lossModel: 'crane',
			ports: ports(
				['run_inlet', NPS4, 'bidirectional'],
				['run_outlet', NPS4, 'bidirectional'],
				['branch', NPS3, 'bidirectional']
			)
		},
		{
			type: 'valve',
			valveType: 'globe',
			id: 'V1',
			name: 'Branch A globe valve',
			elevation: 5,
			status: 'active',
			ports: ports(['inlet', NPS3, 'inlet'], ['outlet', NPS3, 'outlet'])
		},
		{
			type: 'reservoir',
			id: 'R2',
			name: 'Lower tank A',
			elevation: 5,
			liquidLevel: 2,
			surfacePressure: 0,
			ports: ports(['port_1', NPS3, 'bidirectional'])
		},
		{
			type: 'reservoir',
			id: 'R3',
			name: 'Lower tank B',
			elevation: 0,
			liquidLevel: 2,
			surfacePressure: 0,
			ports: ports(['port_1', NPS3, 'bidirectional'])
		}
	];
	return {
		...project,
		components,
		connections: [
			pipe('L1', ['R1', 'port_1'], ['T1', 'run_inlet'], NPS4, 50, [
				fitting('entrance_sharp'),
				fitting('elbow_90_lr', 2)
			]),
			{
				...pipe('L2', ['T1', 'run_outlet'], ['V1', 'inlet'], NPS4, 1),
				piping: {
					pipes: [
						{ materialId: 'carbon_steel', schedule: '40', nominalSize: NPS4, length: 1 },
						{ materialId: 'carbon_steel', schedule: '40', nominalSize: NPS3, length: 79 }
					],
					fittings: [fitting('reducer_sudden')]
				}
			},
			pipe('L3', ['V1', 'outlet'], ['R2', 'port_1'], NPS3, 20, [fitting('exit')]),
			pipe('L4', ['T1', 'branch'], ['R3', 'port_1'], NPS3, 120, [
				fitting('elbow_90_lr', 3),
				fitting('exit')
			])
		]
	};
}

/**
 * (3) Closed loop: a circulation pump and a check valve in a loop, pressurized by an ideal
 * reference node (an expansion tank) on a tee at the pump suction.
 */
export function closedLoopExample(): Project {
	const project = base(
		'example-closed-loop',
		'Closed loop with a pump',
		'A circulation loop with a check valve, pressurized at the pump suction by a fixed-pressure ' +
			'reference node (an expansion tank).'
	);
	const components: Component[] = [
		{
			type: 'reference_node',
			referenceType: 'ideal',
			id: 'N1',
			name: 'Expansion tank (pressurization point)',
			elevation: 0,
			pressure: 150_000,
			ports: ports(['port_1', NPS3, 'bidirectional'])
		},
		{
			type: 'branch',
			branchType: 'tee',
			id: 'T1',
			name: 'Pressurization tee',
			elevation: 0,
			lossModel: 'crane',
			ports: ports(
				['run_inlet', NPS3, 'bidirectional'],
				['run_outlet', NPS3, 'bidirectional'],
				['branch', NPS3, 'bidirectional']
			)
		},
		{
			type: 'pump',
			id: 'P1',
			name: 'Circulation pump',
			elevation: 0,
			curveId: 'C1',
			speed: 1,
			status: 'on',
			ports: ports(['suction', NPS3, 'inlet'], ['discharge', NPS3, 'outlet'])
		},
		{
			type: 'valve',
			valveType: 'check',
			id: 'V1',
			name: 'Pump check valve',
			elevation: 0,
			status: 'active',
			crackingPressure: 0,
			ports: ports(['inlet', NPS3, 'inlet'], ['outlet', NPS3, 'outlet'])
		}
	];
	return {
		...project,
		components,
		connections: [
			pipe('L1', ['N1', 'port_1'], ['T1', 'branch'], NPS3, 1),
			pipe('L2', ['T1', 'run_outlet'], ['P1', 'suction'], NPS3, 2),
			pipe('L3', ['P1', 'discharge'], ['V1', 'inlet'], NPS3, 2),
			pipe('L4', ['V1', 'outlet'], ['T1', 'run_inlet'], NPS3, 150, [fitting('elbow_90_lr', 8)])
		],
		pumpLibrary: [
			{
				id: 'C1',
				name: 'Example circulator curve (illustrative)',
				points: [
					{ flow: 0, head: 20 },
					{ flow: 0.005, head: 19 },
					{ flow: 0.01, head: 16 },
					{ flow: 0.015, head: 11 }
				]
			}
		]
	};
}

export interface ExampleProject {
	slug: string;
	title: string;
	summary: string;
	create: () => Project;
}

export const EXAMPLES: readonly ExampleProject[] = [
	{
		slug: 'pump-transfer',
		title: 'Pump transfer between two tanks',
		summary: 'Reservoir, pump, gate valve and reservoir in series.',
		create: pumpTransferExample
	},
	{
		slug: 'gravity-branch',
		title: 'Gravity-fed branched network',
		summary: 'An elevated tank feeding two tanks through a tee, no pump.',
		create: gravityBranchExample
	},
	{
		slug: 'closed-loop',
		title: 'Closed loop with a pump',
		summary: 'Pump, check valve and an ideal reference node as the pressurization point.',
		create: closedLoopExample
	}
];

export function exampleProject(slug: string): Project | undefined {
	return EXAMPLES.find((e) => e.slug === slug)?.create();
}
