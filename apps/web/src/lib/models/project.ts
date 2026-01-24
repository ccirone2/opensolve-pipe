/**
 * Project container and metadata models.
 * Mirrors: apps/api/src/opensolve_pipe/models/project.py
 */

import type { Component, PipeConnection } from './components';
import type { FluidDefinition } from './fluids';
import { DEFAULT_FLUID_DEFINITION } from './fluids';
import type { PumpCurve } from './pump';
import type { SolvedState } from './results';
import type { SolverOptions, UnitPreferences } from './units';
import { DEFAULT_SOLVER_OPTIONS, DEFAULT_UNIT_PREFERENCES } from './units';

/** Project metadata and versioning info. */
export interface ProjectMetadata {
	/** Project name. Default: "Untitled Project" */
	name: string;
	/** Project description. */
	description?: string;
	/** Project author. */
	author?: string;
	/** Creation timestamp (ISO 8601 string). */
	created: string;
	/** Last modification timestamp (ISO 8601 string). */
	modified: string;
	/** Project version. Default: "1" */
	version: string;
	/** Parent version for branching. */
	parent_version?: string;
}

/** Project-level settings. */
export interface ProjectSettings {
	/** Unit preferences. */
	units: UnitPreferences;
	/** Enabled design checks. */
	enabled_checks: string[];
	/** Solver configuration. */
	solver_options: SolverOptions;
}

/** Top-level project container. */
export interface Project {
	/** Unique project identifier. */
	id: string;
	/** Project metadata. */
	metadata: ProjectMetadata;
	/** Project settings. */
	settings: ProjectSettings;
	/** Working fluid definition. */
	fluid: FluidDefinition;
	/** Network components. */
	components: Component[];
	/** Port-based connections between components. */
	connections: PipeConnection[];
	/** Available pump curves. */
	pump_library: PumpCurve[];
	/** Solved state (if network has been solved). */
	results?: SolvedState;
}

/** Generate a unique project ID. */
export function generateProjectId(): string {
	return `proj_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
}

/** Create default project metadata. */
export function createDefaultMetadata(): ProjectMetadata {
	const now = new Date().toISOString();
	return {
		name: 'Untitled Project',
		created: now,
		modified: now,
		version: '1'
	};
}

/** Create default project settings. */
export function createDefaultSettings(): ProjectSettings {
	return {
		units: { ...DEFAULT_UNIT_PREFERENCES },
		enabled_checks: [],
		solver_options: { ...DEFAULT_SOLVER_OPTIONS }
	};
}

/** Create a new empty project. */
export function createNewProject(): Project {
	return {
		id: generateProjectId(),
		metadata: createDefaultMetadata(),
		settings: createDefaultSettings(),
		fluid: { ...DEFAULT_FLUID_DEFINITION },
		components: [],
		connections: [],
		pump_library: []
	};
}

/** Get a component by ID from a project. */
export function getComponentById(project: Project, componentId: string): Component | undefined {
	return project.components.find((c) => c.id === componentId);
}

/** Get a pump curve by ID from a project. */
export function getPumpCurveById(project: Project, curveId: string): PumpCurve | undefined {
	return project.pump_library.find((c) => c.id === curveId);
}

/** Check if all component IDs are unique. */
export function validateComponentIds(project: Project): string | null {
	const ids = project.components.map((c) => c.id);
	const uniqueIds = new Set(ids);
	if (ids.length !== uniqueIds.size) {
		const duplicates = ids.filter((id, index) => ids.indexOf(id) !== index);
		return `Duplicate component IDs: ${[...new Set(duplicates)].join(', ')}`;
	}
	return null;
}

/** Check if all downstream connection references are valid. */
export function validateConnectionReferences(project: Project): string | null {
	const componentIds = new Set(project.components.map((c) => c.id));
	for (const component of project.components) {
		for (const conn of component.downstream_connections) {
			if (!componentIds.has(conn.target_component_id)) {
				return `Component '${component.id}' references unknown target: '${conn.target_component_id}'`;
			}
		}
	}
	return null;
}

/** Check if all pump curve IDs are unique. */
export function validatePumpCurveIds(project: Project): string | null {
	const ids = project.pump_library.map((c) => c.id);
	const uniqueIds = new Set(ids);
	if (ids.length !== uniqueIds.size) {
		const duplicates = ids.filter((id, index) => ids.indexOf(id) !== index);
		return `Duplicate pump curve IDs: ${[...new Set(duplicates)].join(', ')}`;
	}
	return null;
}

/** Check if all pump components reference valid pump curves. */
export function validatePumpCurveReferences(project: Project): string | null {
	const curveIds = new Set(project.pump_library.map((c) => c.id));
	for (const component of project.components) {
		if (component.type === 'pump' && !curveIds.has(component.curve_id)) {
			return `Pump '${component.id}' references unknown curve: '${component.curve_id}'`;
		}
	}
	return null;
}

/** Check if all pipe connection IDs are unique. */
export function validatePipeConnectionIds(project: Project): string | null {
	const ids = project.connections.map((c) => c.id);
	const uniqueIds = new Set(ids);
	if (ids.length !== uniqueIds.size) {
		const duplicates = ids.filter((id, index) => ids.indexOf(id) !== index);
		return `Duplicate connection IDs: ${[...new Set(duplicates)].join(', ')}`;
	}
	return null;
}

/** Check if all pipe connection references are valid. */
export function validatePipeConnectionReferences(project: Project): string | null {
	const componentMap = new Map(project.components.map((c) => [c.id, c]));

	for (const conn of project.connections) {
		const fromComponent = componentMap.get(conn.from_component_id);
		if (!fromComponent) {
			return `Connection '${conn.id}' references unknown source component: '${conn.from_component_id}'`;
		}
		if (!fromComponent.ports.some((p) => p.id === conn.from_port_id)) {
			return `Connection '${conn.id}' references unknown source port: '${conn.from_port_id}' on component '${conn.from_component_id}'`;
		}

		const toComponent = componentMap.get(conn.to_component_id);
		if (!toComponent) {
			return `Connection '${conn.id}' references unknown target component: '${conn.to_component_id}'`;
		}
		if (!toComponent.ports.some((p) => p.id === conn.to_port_id)) {
			return `Connection '${conn.id}' references unknown target port: '${conn.to_port_id}' on component '${conn.to_component_id}'`;
		}
	}
	return null;
}

/** Validate entire project. Returns array of error messages (empty if valid). */
export function validateProject(project: Project): string[] {
	const errors: string[] = [];

	const componentIdError = validateComponentIds(project);
	if (componentIdError) errors.push(componentIdError);

	const connectionError = validateConnectionReferences(project);
	if (connectionError) errors.push(connectionError);

	const curveIdError = validatePumpCurveIds(project);
	if (curveIdError) errors.push(curveIdError);

	const curveRefError = validatePumpCurveReferences(project);
	if (curveRefError) errors.push(curveRefError);

	const pipeConnIdError = validatePipeConnectionIds(project);
	if (pipeConnIdError) errors.push(pipeConnIdError);

	const pipeConnRefError = validatePipeConnectionReferences(project);
	if (pipeConnRefError) errors.push(pipeConnRefError);

	return errors;
}

/** Update project modified timestamp. */
export function touchProject(project: Project): Project {
	return {
		...project,
		metadata: {
			...project.metadata,
			modified: new Date().toISOString()
		}
	};
}

/** Create a new version (branch) of a project. */
export function branchProject(project: Project, newName?: string): Project {
	const now = new Date().toISOString();
	const newVersion = String(parseInt(project.metadata.version) + 1);

	return {
		...project,
		id: generateProjectId(),
		metadata: {
			...project.metadata,
			name: newName ?? `${project.metadata.name} (copy)`,
			created: now,
			modified: now,
			version: newVersion,
			parent_version: project.metadata.version
		},
		connections: [...project.connections], // Deep copy connections
		results: undefined // Clear results for new version
	};
}

/** Generate a unique connection ID. */
export function generateConnectionId(): string {
	return `conn_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
}

/** Get a connection by ID from a project. */
export function getConnectionById(project: Project, connectionId: string): PipeConnection | undefined {
	return project.connections.find((c) => c.id === connectionId);
}

/** Get all connections from a component. */
export function getConnectionsFromComponent(project: Project, componentId: string): PipeConnection[] {
	return project.connections.filter((c) => c.from_component_id === componentId);
}

/** Get all connections to a component. */
export function getConnectionsToComponent(project: Project, componentId: string): PipeConnection[] {
	return project.connections.filter((c) => c.to_component_id === componentId);
}

/** Get all connections involving a specific port. */
export function getConnectionsForPort(
	project: Project,
	componentId: string,
	portId: string
): PipeConnection[] {
	return project.connections.filter(
		(c) =>
			(c.from_component_id === componentId && c.from_port_id === portId) ||
			(c.to_component_id === componentId && c.to_port_id === portId)
	);
}
