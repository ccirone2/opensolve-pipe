/**
 * Shared helpers for unit tests. Not used by the app.
 */
import type { Component, EquipmentRating, PipeConnection, Project } from '../api/types';
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
 * ENTRY_KINDS): made-up test inputs, 0.004 m³/s for an assigned-flow node's flow and, for an
 * equipment item, a rated point of 50 kPa at 15 L/s on a fluid of 999.1 kg/m³. Empty for others.
 */
export function enteredFor(kind: ComponentKind): EnteredValues {
	if (kind === 'assigned_flow') return { flow: 0.004 };
	if (kind === 'equipment') {
		return { rating: { kind: 'point', pressureLoss: 50000, flow: 0.015, density: 999.1 } };
	}
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
