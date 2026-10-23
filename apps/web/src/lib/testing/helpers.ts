/**
 * Shared helpers for unit tests. Not used by the app.
 */
import type { Component, PipeConnection, Project } from '../api/types';
import { createEmptyProject } from '../utils/factory';

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
