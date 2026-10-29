/**
 * Shared helpers for unit tests. Not used by the app.
 */
import type { Component, EquipmentRating, Orifice, PipeConnection, Project } from '../api/types';
import { createEmptyProject, type ComponentKind, type EnteredValues } from '../utils/factory';

/** Freeze an object graph, so a test fails if code under test modifies its input. */
export function deepFreeze<T>(value: T): T {
	if (value && typeof value === 'object' && !Object.isFrozen(value)) {
		Object.freeze(value);
		for (const child of Object.values(value)) deepFreeze(child);
	}
	return value;
}

/**
 * Referential problems, computed independently of validate.ts: every connection end names an
 * existing component and one of its ports, no port carries two connection ends, and ids are
 * unique. Returns a list of problems (empty when consistent).
 */
export function referentialIssues(project: Project): string[] {
	const issues: string[] = [];
	const componentIds = project.components.map((c) => c.id);
	if (new Set(componentIds).size !== componentIds.length) issues.push('duplicate component id');
	const connectionIds = project.connections.map((c) => c.id);
	if (new Set(connectionIds).size !== connectionIds.length) issues.push('duplicate connection id');
	const endCount = new Map<string, number>();
	for (const c of project.connections) {
		for (const [componentId, portId] of [
			[c.fromComponentId, c.fromPortId],
			[c.toComponentId, c.toPortId]
		] as const) {
			const component = project.components.find((x) => x.id === componentId);
			if (!component) issues.push(`${c.id}: missing component ${componentId}`);
			else if (!component.ports.some((p) => p.id === portId)) {
				issues.push(`${c.id}: missing port ${componentId}.${portId}`);
			}
			const key = `${componentId}.${portId}`;
			endCount.set(key, (endCount.get(key) ?? 0) + 1);
		}
	}
	for (const [key, n] of endCount) if (n > 1) issues.push(`port ${key} used ${n} times`);
	for (const component of project.components) {
		if (component.type === 'pump' && !project.pumpLibrary.some((p) => p.id === component.curveId)) {
			issues.push(`${component.id}: missing pump curve ${component.curveId}`);
		}
	}
	return issues;
}

/** A project holding the given components and connections (and pump curves). */
export function projectWith(
	components: Component[],
	connections: PipeConnection[] = [],
	pumpLibrary: Project['pumpLibrary'] = []
): Project {
	return {
		...createEmptyProject({ id: 'test-project', now: '2026-01-01T00:00:00Z' }),
		components,
		connections,
		pumpLibrary
	};
}

/** A connection with one 10 m carbon steel schedule 40 pipe of the given nominal size. */
export function link(
	id: string,
	from: [string, string],
	to: [string, string],
	nominalSize = 0.1016
): PipeConnection {
	return {
		id,
		fromComponentId: from[0],
		fromPortId: from[1],
		toComponentId: to[0],
		toPortId: to[1],
		piping: {
			pipes: [{ materialId: 'carbon_steel', schedule: '40', nominalSize, length: 10 }],
			fittings: []
		}
	};
}

/**
 * Reservoir R1 → L1 → assigned-flow node AF1 at `flow` (m³/s; positive: a demand). Made-up test
 * inputs: R1 at 0 m with a 20 m liquid level, AF1 at 2 m, one 10 m NPS 4 pipe.
 */
export function assignedFlowProject(flow: number): Project {
	const port = { id: 'port_1', nominalSize: 0.1016, direction: 'bidirectional' } as const;
	return projectWith(
		[
			{
				id: 'R1',
				name: 'Supply tank',
				elevation: 0,
				type: 'reservoir',
				liquidLevel: 20,
				surfacePressure: 0,
				ports: [{ ...port }]
			},
			{
				id: 'AF1',
				name: 'Process user',
				elevation: 2,
				type: 'assigned_flow',
				flow,
				ports: [{ ...port }]
			}
		],
		[link('L1', ['R1', 'port_1'], ['AF1', 'port_1'])]
	);
}

/**
 * The values a user enters for a kind that has no default for them, where it is added (factory.ts
 * ENTRY_KINDS): made-up test inputs, 0.004 m³/s for an assigned-flow node's flow, for an equipment
 * item a rated point of 50 kPa at 15 L/s on a fluid of 999.1 kg/m³, and a 50 mm bore for an
 * orifice plate. Empty for others.
 */
export function enteredFor(kind: ComponentKind): EnteredValues {
	if (kind === 'assigned_flow') return { flow: 0.004 };
	if (kind === 'equipment') {
		return { rating: { kind: 'point', pressureLoss: 50000, flow: 0.015, density: 999.1 } };
	}
	if (kind === 'orifice') return { boreDiameter: 0.05 };
	return {};
}

/**
 * Reservoir R1 (5 m level) → L1 → equipment E1 "Strainer" rated by `rating` → L2 → reservoir R2
 * (0 m), all at 0 m, with 10 m NPS 4 pipes. Made-up test inputs (default rating: 25 kPa at 10 L/s
 * on a fluid of 999.1 kg/m³).
 */
export function equipmentProject(
	rating: EquipmentRating = { kind: 'point', pressureLoss: 25000, flow: 0.01, density: 999.1 }
): Project {
	const port = { id: 'port_1', nominalSize: 0.1016, direction: 'bidirectional' } as const;
	const reservoir = (id: string, name: string, liquidLevel: number): Component => ({
		id,
		name,
		elevation: 0,
		type: 'reservoir',
		liquidLevel,
		surfacePressure: 0,
		ports: [{ ...port }]
	});
	return projectWith(
		[
			reservoir('R1', 'Supply tank', 5),
			{
				id: 'E1',
				name: 'Strainer',
				elevation: 0,
				type: 'equipment',
				rating,
				ports: [
					{ id: 'inlet', nominalSize: 0.1016, direction: 'inlet' },
					{ id: 'outlet', nominalSize: 0.1016, direction: 'outlet' }
				]
			},
			reservoir('R2', 'Return tank', 0)
		],
		[link('L1', ['R1', 'port_1'], ['E1', 'inlet']), link('L2', ['E1', 'outlet'], ['R2', 'port_1'])]
	);
}

/**
 * Reservoir R1 (5 m level) → L1 → orifice plate O1 "Bypass orifice" → L2 → reservoir R2 (0 m), all
 * at 0 m, with 10 m NPS 4 schedule 40 carbon steel pipes. Made-up test inputs: a 50 mm bore,
 * ISO 5167-2's C and no taps unless `plate` says otherwise.
 */
export function orificeProject(plate: Partial<Orifice> = {}): Project {
	const port = { id: 'port_1', nominalSize: 0.1016, direction: 'bidirectional' } as const;
	const reservoir = (id: string, name: string, liquidLevel: number): Component => ({
		id,
		name,
		elevation: 0,
		type: 'reservoir',
		liquidLevel,
		surfacePressure: 0,
		ports: [{ ...port }]
	});
	return projectWith(
		[
			reservoir('R1', 'Supply tank', 5),
			{
				id: 'O1',
				name: 'Bypass orifice',
				elevation: 0,
				type: 'orifice',
				boreDiameter: 0.05,
				ports: [
					{ id: 'inlet', nominalSize: 0.1016, direction: 'inlet' },
					{ id: 'outlet', nominalSize: 0.1016, direction: 'outlet' }
				],
				...plate
			},
			reservoir('R2', 'Return tank', 0)
		],
		[link('L1', ['R1', 'port_1'], ['O1', 'inlet']), link('L2', ['O1', 'outlet'], ['R2', 'port_1'])]
	);
}

/** Recursively rebuild an object with its keys in reverse order (arrays keep their order). */
export function reverseKeys(value: unknown): unknown {
	if (Array.isArray(value)) return value.map(reverseKeys);
	if (value && typeof value === 'object') {
		return Object.fromEntries(
			Object.keys(value)
				.reverse()
				.map((k) => [k, reverseKeys((value as Record<string, unknown>)[k])])
		);
	}
	return value;
}

/**
 * Reservoir R1 (10 m level) → L1 (two pipes: a pipe of spec PS1, then NPS 4 Sch 40 carbon steel;
 * an elbow on entry RS2, a custom fitting on entry RS1) → gate valve V1 on entry RS1 → L2 (NPS 4
 * carbon steel) → reservoir R2 (0 m), with a project library (CLAUDE.md D22) of two pipe specs
 * (PS1 on carbon steel without a roughness, PS2 a custom pipe) and two resistance entries (RS1 a
 * Cv, RS2 a K stated at 0.09 m). Made-up test inputs.
 */
export function libraryProject(): Project {
	const port = (id: string) => ({ id, nominalSize: 0.1016, direction: 'bidirectional' }) as const;
	const project = projectWith(
		[
			{
				id: 'R1',
				name: 'Upper tank',
				elevation: 0,
				type: 'reservoir',
				liquidLevel: 10,
				surfacePressure: 0,
				ports: [port('port_1')]
			},
			{
				id: 'V1',
				name: 'Gate valve V1',
				elevation: 0,
				type: 'valve',
				valveType: 'gate',
				status: 'active',
				resistance: { kind: 'library', id: 'RS1' },
				ports: [
					{ id: 'inlet', nominalSize: 0.1016, direction: 'inlet' },
					{ id: 'outlet', nominalSize: 0.1016, direction: 'outlet' }
				]
			},
			{
				id: 'R2',
				name: 'Lower tank',
				elevation: 0,
				type: 'reservoir',
				liquidLevel: 0,
				surfacePressure: 0,
				ports: [port('port_1')]
			}
		],
		[link('L1', ['R1', 'port_1'], ['V1', 'inlet']), link('L2', ['V1', 'outlet'], ['R2', 'port_1'])]
	);
	const l1 = project.connections[0] as PipeConnection;
	l1.piping = {
		pipes: [
			{ specId: 'PS1', length: 30 },
			{ materialId: 'carbon_steel', schedule: '40', nominalSize: 0.1016, length: 12 }
		],
		fittings: [
			{ type: 'elbow_90_lr', quantity: 2, pipeIndex: 0, resistanceId: 'RS2' },
			{ type: 'custom', quantity: 1, pipeIndex: 1, resistanceId: 'RS1' }
		]
	};
	project.pipeLibrary = [
		{
			id: 'PS1',
			name: 'NPS 4 measured',
			source: 'test input: a bore measured on site',
			materialId: 'carbon_steel',
			innerDiameter: 0.1,
			nominalSize: 0.1016
		},
		{
			id: 'PS2',
			name: 'Lined 80 mm',
			source: 'test input',
			materialId: 'custom',
			innerDiameter: 0.08,
			roughness: 1.5e-6,
			outerDiameter: 0.09
		}
	];
	project.resistanceLibrary = [
		{ id: 'RS1', name: 'Gate, open', source: 'test input', kind: 'Cv', value: 900 },
		{
			id: 'RS2',
			name: 'Elbow (K)',
			source: 'test input',
			kind: 'K',
			value: 0.3,
			referenceDiameter: 0.09
		}
	];
	return project;
}
