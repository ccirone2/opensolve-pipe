/**
 * Display names for ids used in the project model: ports, component kinds, statuses, fitting
 * types and fluids. These are names only. Fitting names and fluid names from the API library
 * are preferred where it is available; the fallbacks here are used when it is not.
 */
import type { Component, Fitting, FluidDefinition, Project } from '../api/types';
import { componentKind, KIND_LABELS } from './factory';
import { componentById } from './graph';
import { formatNumber, INCH } from './units';

const PORT_LABELS: Readonly<Record<string, string>> = {
	suction: 'Suction',
	discharge: 'Discharge',
	inlet: 'Inlet',
	outlet: 'Outlet',
	run_inlet: 'Run inlet',
	run_outlet: 'Run outlet',
	branch: 'Branch',
	outlet_1: 'Outlet 1 (run)',
	outlet_2: 'Outlet 2 (branch leg)'
};

/** 'run_inlet' → 'Run inlet', 'port_2' → 'Port 2'. */
export function portLabel(portId: string): string {
	const known = PORT_LABELS[portId];
	if (known) return known;
	const numbered = /^port_(\d+)$/.exec(portId);
	if (numbered) return `Port ${numbered[1]}`;
	return humanize(portId);
}

/** 'elbow_90_lr' → 'Elbow 90 lr' (last-resort label for an id). */
export function humanize(id: string): string {
	const text = id.replace(/_/g, ' ').trim();
	return text ? text.charAt(0).toUpperCase() + text.slice(1) : id;
}

/** 'Gate valve', 'Tee', 'Reservoir', ... */
export function kindLabel(component: Component): string {
	return KIND_LABELS[componentKind(component)];
}

/** The component's name, or its id when it no longer exists. */
export function componentName(project: Project, componentId: string): string {
	return componentById(project, componentId)?.name ?? componentId;
}

/** "Inlet of Gate valve V1". */
export function portOf(project: Project, componentId: string, portId: string): string {
	return `${portLabel(portId)} of ${componentName(project, componentId)}`;
}

/**
 * Nominal pipe size designation: "NPS 4". The library's designation ('2-1/2') is used when the
 * size is in the list given; otherwise the size in inches (nominal size = NPS × 0.0254 m, by
 * definition in the API model).
 */
export function npsLabel(
	nominalSize: number | null | undefined,
	sizes: readonly { nominalSize: number; nps: string }[] = []
): string {
	if (nominalSize === null || nominalSize === undefined) return 'NPS —';
	const match = sizes.find((s) => sameSize(s.nominalSize, nominalSize));
	return `NPS ${match ? match.nps : formatNumber(nominalSize / INCH, 4)}`;
}

/** Nominal sizes are compared with a relative tolerance (they are products of 0.0254). */
export function sameSize(a: number, b: number): boolean {
	return Math.abs(a - b) <= 1e-9 * Math.max(Math.abs(a), Math.abs(b), 1e-12);
}

/** Names of the fitting types, used when the API library is not available. */
const FITTING_NAMES: Readonly<Record<Fitting['type'], string>> = {
	elbow_90_lr: '90° elbow, long radius',
	elbow_90_sr: '90° elbow, short radius',
	elbow_45_lr: '45° elbow, long radius',
	elbow_45_sr: '45° elbow, short radius',
	elbow_90_threaded: '90° elbow, threaded',
	elbow_45_threaded: '45° elbow, threaded',
	bend: 'Bend (angle and radius)',
	entrance_sharp: 'Entrance, sharp-edged',
	entrance_rounded: 'Entrance, rounded',
	entrance_projecting: 'Entrance, projecting (inward)',
	exit: 'Exit (into a reservoir)',
	reducer_sudden: 'Reducer or enlargement, sudden',
	reducer_conical: 'Reducer or enlargement, conical',
	gate_valve: 'Gate valve (inline fitting)',
	ball_valve: 'Ball valve (inline fitting)',
	globe_valve: 'Globe valve (inline fitting)',
	butterfly_valve: 'Butterfly valve (inline fitting)',
	plug_valve: 'Plug valve (inline fitting)',
	swing_check_valve: 'Swing check valve (inline fitting)',
	lift_check_valve: 'Lift check valve (inline fitting)',
	custom: 'Custom fitting (enter K)'
};

export function fittingFallbackName(type: string): string {
	return (FITTING_NAMES as Record<string, string>)[type] ?? humanize(type);
}

/** Names of the built-in fluids, used when the API's fluid list is not available. */
export const FLUID_FALLBACK_NAMES: Readonly<Record<string, string>> = {
	water: 'Water',
	ethylene_glycol: 'Ethylene glycol (aqueous)',
	propylene_glycol: 'Propylene glycol (aqueous)'
};

export function fluidSummary(fluid: FluidDefinition): string {
	return fluid.kind === 'custom'
		? fluid.name
		: (FLUID_FALLBACK_NAMES[fluid.fluidId] ?? humanize(fluid.fluidId));
}

export const ISOLATION_STATUS_LABELS = { active: 'Open', isolated: 'Closed (isolated)' } as const;

export const CHECK_STATUS_LABELS = {
	active: 'Automatic (closes on reverse flow)',
	locked_open: 'Locked open',
	locked_closed: 'Locked closed'
} as const;

export const CONTROL_STATUS_LABELS = {
	active: 'Active (controls to the setpoint)',
	failed_open: 'Failed open',
	failed_closed: 'Failed closed'
} as const;

export const PUMP_STATUS_LABELS = { on: 'On', off: 'Off' } as const;

export const LOSS_MODEL_LABELS = {
	crane: 'Crane TP-410 (flow-split dependent K)',
	ideal: 'Ideal (no fitting loss, as EPANET junctions)'
} as const;

export const FRICTION_METHOD_LABELS = {
	colebrook: 'Colebrook–White (exact, default)',
	swamee_jain: 'Swamee–Jain (EPANET-compatible)'
} as const;
