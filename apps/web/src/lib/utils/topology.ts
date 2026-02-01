/**
 * Topology validation utilities for hydraulic networks.
 *
 * Validates network structure including:
 * - Orphaned branches (disconnected components)
 * - Invalid loop closures
 * - Missing source nodes
 * - Dangling endpoints
 */

import type { Component } from '$lib/models';

// ============================================================================
// Types
// ============================================================================

/** Types of topology validation issues. */
export type TopologyIssueType =
	| 'orphaned_component'
	| 'missing_source'
	| 'dangling_endpoint'
	| 'invalid_loop'
	| 'self_loop'
	| 'duplicate_connection';

/** Severity level of a topology issue. */
export type IssueSeverity = 'error' | 'warning' | 'info';

/** A topology validation issue. */
export interface TopologyIssue {
	/** Type of issue. */
	type: TopologyIssueType;
	/** Severity level. */
	severity: IssueSeverity;
	/** Human-readable message. */
	message: string;
	/** ID of the affected component (if applicable). */
	componentId?: string;
	/** IDs of affected components (for connection issues). */
	connectionIds?: [string, string];
}

/** Result of topology validation. */
export interface TopologyValidationResult {
	/** Whether the topology is valid (no errors). */
	isValid: boolean;
	/** List of issues found. */
	issues: TopologyIssue[];
	/** Number of errors. */
	errorCount: number;
	/** Number of warnings. */
	warningCount: number;
}

// ============================================================================
// Validation Functions
// ============================================================================

/**
 * Validate the topology of a hydraulic network.
 *
 * Checks for:
 * - Orphaned components (not reachable from any source)
 * - Missing sources (no reservoir or tank)
 * - Dangling endpoints (components with no upstream or downstream)
 * - Self-loops (component connected to itself)
 * - Duplicate connections
 */
export function validateTopology(components: Component[]): TopologyValidationResult {
	const issues: TopologyIssue[] = [];

	// Check for empty network
	if (components.length === 0) {
		return {
			isValid: true,
			issues: [],
			errorCount: 0,
			warningCount: 0
		};
	}

	// Build adjacency list
	const downstream = new Map<string, Set<string>>();
	const upstream = new Map<string, Set<string>>();

	for (const component of components) {
		downstream.set(component.id, new Set());
		upstream.set(component.id, new Set());
	}

	for (const component of components) {
		for (const conn of component.downstream_connections) {
			downstream.get(component.id)?.add(conn.target_component_id);
			upstream.get(conn.target_component_id)?.add(component.id);

			// Check for self-loop
			if (conn.target_component_id === component.id) {
				issues.push({
					type: 'self_loop',
					severity: 'error',
					message: `Component "${component.name}" has a connection to itself`,
					componentId: component.id
				});
			}

			// Check for duplicate connections
			const existingDownstream = downstream.get(component.id);
			if (existingDownstream && existingDownstream.has(conn.target_component_id)) {
				// This means we've already added this connection - duplicate!
				// Note: The Set prevents actual duplicates in our tracking, so we need a different approach
				const connCount = component.downstream_connections.filter(
					(c) => c.target_component_id === conn.target_component_id
				).length;
				if (connCount > 1) {
					issues.push({
						type: 'duplicate_connection',
						severity: 'warning',
						message: `Duplicate connection from "${component.name}" to downstream component`,
						connectionIds: [component.id, conn.target_component_id]
					});
				}
			}
		}
	}

	// Find source nodes (reservoirs, tanks, reference nodes)
	const sourceTypes = ['reservoir', 'tank', 'ideal_reference_node', 'non_ideal_reference_node'];
	const sources = components.filter((c) => sourceTypes.includes(c.type));

	if (sources.length === 0) {
		issues.push({
			type: 'missing_source',
			severity: 'error',
			message: 'Network has no source (reservoir, tank, or reference node)'
		});
	}

	// Find reachable components using BFS from all sources
	const reachable = new Set<string>();
	const queue: string[] = sources.map((s) => s.id);

	while (queue.length > 0) {
		const current = queue.shift()!;
		if (reachable.has(current)) continue;
		reachable.add(current);

		// Add downstream neighbors
		const neighbors = downstream.get(current);
		if (neighbors) {
			for (const neighbor of neighbors) {
				if (!reachable.has(neighbor)) {
					queue.push(neighbor);
				}
			}
		}

		// Also traverse upstream to find components that flow into sources
		const upstreamNeighbors = upstream.get(current);
		if (upstreamNeighbors) {
			for (const neighbor of upstreamNeighbors) {
				if (!reachable.has(neighbor)) {
					queue.push(neighbor);
				}
			}
		}
	}

	// Check for orphaned components
	for (const component of components) {
		if (!reachable.has(component.id)) {
			issues.push({
				type: 'orphaned_component',
				severity: 'error',
				message: `Component "${component.name}" is not connected to the network`,
				componentId: component.id
			});
		}
	}

	// Check for dangling endpoints (excluding terminal types)
	const terminalTypes = ['sprinkler', 'plug', 'orifice'];
	for (const component of components) {
		const hasUpstream = (upstream.get(component.id)?.size ?? 0) > 0;
		const hasDownstream = (downstream.get(component.id)?.size ?? 0) > 0;
		const isSource = sourceTypes.includes(component.type);
		const isTerminal = terminalTypes.includes(component.type);

		// Sources should have downstream but no upstream is OK
		if (isSource && !hasDownstream && components.length > 1) {
			issues.push({
				type: 'dangling_endpoint',
				severity: 'warning',
				message: `Source "${component.name}" has no downstream connections`,
				componentId: component.id
			});
		}

		// Terminal components should have upstream but no downstream is OK
		if (isTerminal && !hasUpstream) {
			issues.push({
				type: 'dangling_endpoint',
				severity: 'warning',
				message: `Terminal component "${component.name}" has no upstream connection`,
				componentId: component.id
			});
		}

		// Non-source, non-terminal components should have both
		if (!isSource && !isTerminal && !hasUpstream && !hasDownstream && components.length > 1) {
			issues.push({
				type: 'dangling_endpoint',
				severity: 'warning',
				message: `Component "${component.name}" has no connections`,
				componentId: component.id
			});
		}
	}

	// Count errors and warnings
	const errorCount = issues.filter((i) => i.severity === 'error').length;
	const warningCount = issues.filter((i) => i.severity === 'warning').length;

	return {
		isValid: errorCount === 0,
		issues,
		errorCount,
		warningCount
	};
}

/**
 * Check if adding a connection would create an invalid loop.
 *
 * An invalid loop occurs when the connection would create a cycle
 * that cannot be hydraulically balanced (e.g., no pressure differential).
 *
 * Note: Not all loops are invalid - parallel paths and proper looped
 * networks are valid. This function checks for specific invalid patterns.
 */
export function wouldCreateInvalidLoop(
	components: Component[],
	fromId: string,
	toId: string
): boolean {
	// Build downstream adjacency list with the proposed connection
	const downstream = new Map<string, Set<string>>();

	for (const component of components) {
		downstream.set(component.id, new Set());
	}

	for (const component of components) {
		for (const conn of component.downstream_connections) {
			downstream.get(component.id)?.add(conn.target_component_id);
		}
	}

	// Add proposed connection
	if (!downstream.has(fromId)) {
		downstream.set(fromId, new Set());
	}
	downstream.get(fromId)?.add(toId);

	// Check if toId can reach fromId (would create a cycle)
	const visited = new Set<string>();
	const queue: string[] = [toId];

	while (queue.length > 0) {
		const current = queue.shift()!;
		if (current === fromId) {
			return true; // Found a path back - cycle detected
		}
		if (visited.has(current)) continue;
		visited.add(current);

		const neighbors = downstream.get(current);
		if (neighbors) {
			for (const neighbor of neighbors) {
				if (!visited.has(neighbor)) {
					queue.push(neighbor);
				}
			}
		}
	}

	return false;
}

/**
 * Get components that are not connected to any source.
 */
export function getOrphanedComponents(components: Component[]): Component[] {
	const result = validateTopology(components);
	const orphanedIds = new Set(
		result.issues
			.filter((i) => i.type === 'orphaned_component')
			.map((i) => i.componentId)
			.filter((id): id is string => id !== undefined)
	);

	return components.filter((c) => orphanedIds.has(c.id));
}

/**
 * Check if the network has any loops (cycles).
 */
export function hasLoops(components: Component[]): boolean {
	// Build downstream adjacency list
	const downstream = new Map<string, string[]>();

	for (const component of components) {
		downstream.set(component.id, []);
	}

	for (const component of components) {
		for (const conn of component.downstream_connections) {
			downstream.get(component.id)?.push(conn.target_component_id);
		}
	}

	// DFS with coloring to detect cycles
	const white = new Set(components.map((c) => c.id)); // Unvisited
	const gray = new Set<string>(); // Currently visiting
	const black = new Set<string>(); // Fully processed

	function dfs(node: string): boolean {
		white.delete(node);
		gray.add(node);

		const neighbors = downstream.get(node) ?? [];
		for (const neighbor of neighbors) {
			if (gray.has(neighbor)) {
				return true; // Back edge - cycle found
			}
			if (white.has(neighbor)) {
				if (dfs(neighbor)) {
					return true;
				}
			}
		}

		gray.delete(node);
		black.add(node);
		return false;
	}

	for (const component of components) {
		if (white.has(component.id)) {
			if (dfs(component.id)) {
				return true;
			}
		}
	}

	return false;
}
