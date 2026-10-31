/**
 * A small closed loop for tests that need one: a circulation pump and a check valve in a loop,
 * pressurized by an ideal reference node (an expansion tank) on a tee at the pump suction. Test
 * inputs, not an example on the home page (it was one before the condenser water example).
 */
import type { Project } from '../api/types';
import { createEmptyProject } from '../utils/factory';
import { SI_UNITS } from '../utils/units';
import { INCH } from '../utils/units';

const NPS3 = 3 * INCH;

const pipe = (
	id: string,
	from: [string, string],
	to: [string, string],
	length: number,
	elbows = 0
) => ({
	id,
	fromComponentId: from[0],
	fromPortId: from[1],
	toComponentId: to[0],
	toPortId: to[1],
	piping: {
		pipes: [{ materialId: 'carbon_steel', schedule: '40', nominalSize: NPS3, length }],
		fittings: elbows ? [{ type: 'elbow_90_lr' as const, quantity: elbows, pipeIndex: 0 }] : []
	}
});

const port = (id: string, direction: 'inlet' | 'outlet' | 'bidirectional') => ({
	id,
	nominalSize: NPS3,
	direction
});

export function closedLoopProject(): Project {
	const project = createEmptyProject({
		id: 'test-closed-loop',
		name: 'Closed loop with a pump',
		now: '2026-10-21T00:00:00Z',
		units: SI_UNITS
	});
	return {
		...project,
		components: [
			{
				type: 'reference_node',
				referenceType: 'ideal',
				id: 'N1',
				name: 'Expansion tank (pressurization point)',
				elevation: 0,
				pressure: 150_000,
				ports: [port('port_1', 'bidirectional')]
			},
			{
				type: 'branch',
				branchType: 'tee',
				id: 'T1',
				name: 'Pressurization tee',
				elevation: 0,
				lossModel: 'crane',
				ports: [
					port('run_inlet', 'bidirectional'),
					port('run_outlet', 'bidirectional'),
					port('branch', 'bidirectional')
				]
			},
			{
				type: 'pump',
				id: 'P1',
				name: 'Circulation pump',
				elevation: 0,
				curveId: 'C1',
				speed: 1,
				status: 'on',
				ports: [port('suction', 'inlet'), port('discharge', 'outlet')]
			},
			{
				type: 'valve',
				valveType: 'check',
				id: 'V1',
				name: 'Pump check valve',
				elevation: 0,
				status: 'active',
				crackingPressure: 0,
				ports: [port('inlet', 'inlet'), port('outlet', 'outlet')]
			}
		],
		connections: [
			pipe('L1', ['N1', 'port_1'], ['T1', 'branch'], 1),
			pipe('L2', ['T1', 'run_outlet'], ['P1', 'suction'], 2),
			pipe('L3', ['P1', 'discharge'], ['V1', 'inlet'], 2),
			pipe('L4', ['V1', 'outlet'], ['T1', 'run_inlet'], 150, 8)
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
