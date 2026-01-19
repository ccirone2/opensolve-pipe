/**
 * Solved state and result models.
 * Mirrors: apps/api/src/opensolve_pipe/models/results.py
 */

import type { FlowHeadPoint } from './pump';

/** Flow regime classification. */
export type FlowRegime = 'laminar' | 'transitional' | 'turbulent';

/** Display labels for flow regimes. */
export const FLOW_REGIME_LABELS: Record<FlowRegime, string> = {
	laminar: 'Laminar',
	transitional: 'Transitional',
	turbulent: 'Turbulent'
};

/** Solved state for a node (reservoir, tank, junction, etc.). */
export interface NodeResult {
	/** ID of the component. */
	component_id: string;
	/** Static pressure in project units. */
	pressure: number;
	/** Dynamic pressure (velocity head) in project units. Default: 0 */
	dynamic_pressure: number;
	/** Total pressure in project units. */
	total_pressure: number;
	/** Hydraulic Grade Line elevation. */
	hgl: number;
	/** Energy Grade Line elevation. */
	egl: number;
}

/** Solved state for a link (pipe segment between components). */
export interface LinkResult {
	/** ID of the upstream component. */
	component_id: string;
	/** ID of the upstream node. */
	upstream_node_id: string;
	/** ID of the downstream node. */
	downstream_node_id: string;
	/** Flow rate in project units (positive = forward). */
	flow: number;
	/** Flow velocity in project units. */
	velocity: number;
	/** Head loss across the link in project units. */
	head_loss: number;
	/** Head loss due to pipe friction. Default: 0 */
	friction_head_loss: number;
	/** Head loss due to fittings (minor losses). Default: 0 */
	minor_head_loss: number;
	/** Reynolds number. */
	reynolds_number: number;
	/** Darcy friction factor. */
	friction_factor: number;
	/** Flow regime classification. */
	regime: FlowRegime;
}

/** Solved state for a pump at its operating point. */
export interface PumpResult {
	/** ID of the pump component. */
	component_id: string;
	/** Operating flow rate in project units. */
	operating_flow: number;
	/** Operating head in project units. */
	operating_head: number;
	/** NPSH available at pump suction. */
	npsh_available: number;
	/** NPSH margin (NPSHa - NPSHr) if NPSHR curve provided. */
	npsh_margin?: number;
	/** Pump efficiency at operating point (if efficiency curve provided). */
	efficiency?: number;
	/** Power consumption in kW (if efficiency provided). */
	power?: number;
	/** System curve points. */
	system_curve: FlowHeadPoint[];
}

/** Categories of warnings and design check results. */
export type WarningCategory = 'velocity' | 'pressure' | 'npsh' | 'convergence' | 'topology' | 'data';

/** Display labels for warning categories. */
export const WARNING_CATEGORY_LABELS: Record<WarningCategory, string> = {
	velocity: 'Velocity',
	pressure: 'Pressure',
	npsh: 'NPSH',
	convergence: 'Convergence',
	topology: 'Topology',
	data: 'Data'
};

/** Warning severity levels. */
export type WarningSeverity = 'info' | 'warning' | 'error';

/** Design check warning or solver message. */
export interface Warning {
	/** Warning category. */
	category: WarningCategory;
	/** Warning severity. */
	severity: WarningSeverity;
	/** Related component ID (if applicable). */
	component_id?: string;
	/** Human-readable warning message. */
	message: string;
	/** Additional details. */
	details?: Record<string, unknown>;
}

/** Complete solved state of the network. */
export interface SolvedState {
	/** Whether the solver converged. */
	converged: boolean;
	/** Number of solver iterations. */
	iterations: number;
	/** Solve timestamp (ISO 8601 string). */
	timestamp: string;
	/** Time taken to solve in seconds. */
	solve_time_seconds?: number;
	/** Error message if not converged. */
	error?: string;
	/** Results keyed by node component ID. */
	node_results: Record<string, NodeResult>;
	/** Results keyed by upstream component ID. */
	link_results: Record<string, LinkResult>;
	/** Results keyed by pump component ID. */
	pump_results: Record<string, PumpResult>;
	/** Warnings and design check results. */
	warnings: Warning[];
}

/** Check if the solver converged successfully. */
export function isSolveSuccessful(state: SolvedState): boolean {
	return state.converged && !state.error;
}

/** Get warnings filtered by severity. */
export function getWarningsBySeverity(state: SolvedState, severity: WarningSeverity): Warning[] {
	return state.warnings.filter((w) => w.severity === severity);
}

/** Get warnings for a specific component. */
export function getWarningsForComponent(state: SolvedState, componentId: string): Warning[] {
	return state.warnings.filter((w) => w.component_id === componentId);
}

/** Check if there are any errors in warnings. */
export function hasErrors(state: SolvedState): boolean {
	return state.warnings.some((w) => w.severity === 'error');
}

/** Get the result for a node component. */
export function getNodeResult(state: SolvedState, componentId: string): NodeResult | undefined {
	return state.node_results[componentId];
}

/** Get the result for a link component. */
export function getLinkResult(state: SolvedState, componentId: string): LinkResult | undefined {
	return state.link_results[componentId];
}

/** Get the result for a pump component. */
export function getPumpResult(state: SolvedState, componentId: string): PumpResult | undefined {
	return state.pump_results[componentId];
}
