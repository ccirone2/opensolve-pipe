/**
 * Piping, pipe definition, and fitting models.
 * Mirrors: apps/api/src/opensolve_pipe/models/piping.py
 */

/** Available pipe materials. */
export type PipeMaterial =
	| 'carbon_steel'
	| 'stainless_steel'
	| 'pvc'
	| 'cpvc'
	| 'hdpe'
	| 'ductile_iron'
	| 'cast_iron'
	| 'copper'
	| 'grp';

/** Display names for pipe materials. */
export const PIPE_MATERIAL_LABELS: Record<PipeMaterial, string> = {
	carbon_steel: 'Carbon Steel',
	stainless_steel: 'Stainless Steel',
	pvc: 'PVC',
	cpvc: 'CPVC',
	hdpe: 'HDPE',
	ductile_iron: 'Ductile Iron',
	cast_iron: 'Cast Iron',
	copper: 'Copper',
	grp: 'GRP (Fiberglass)'
};

/** Common pipe schedules. */
export type PipeSchedule = '5' | '10' | '40' | '80' | '160' | 'STD' | 'XS' | 'XXS';

/** Display names for pipe schedules. */
export const PIPE_SCHEDULE_LABELS: Record<PipeSchedule, string> = {
	'5': 'Schedule 5',
	'10': 'Schedule 10',
	'40': 'Schedule 40',
	'80': 'Schedule 80',
	'160': 'Schedule 160',
	STD: 'Standard',
	XS: 'Extra Strong',
	XXS: 'Double Extra Strong'
};

/** Types of pipe fittings. */
export type FittingType =
	// Elbows
	| 'elbow_90_lr'
	| 'elbow_90_sr'
	| 'elbow_45'
	// Tees
	| 'tee_through'
	| 'tee_branch'
	// Reducers
	| 'reducer_concentric'
	| 'reducer_eccentric'
	| 'expander_concentric'
	| 'expander_eccentric'
	// Valves (as fittings - for K-factor calculation)
	| 'gate_valve'
	| 'ball_valve'
	| 'butterfly_valve'
	| 'globe_valve'
	| 'check_valve_swing'
	| 'check_valve_lift'
	// Entrances and exits
	| 'entrance_sharp'
	| 'entrance_rounded'
	| 'entrance_projecting'
	| 'exit'
	// Other
	| 'strainer_basket'
	| 'strainer_y'
	| 'union'
	| 'coupling';

/** Display names for fitting types. */
export const FITTING_TYPE_LABELS: Record<FittingType, string> = {
	elbow_90_lr: '90° Elbow (Long Radius)',
	elbow_90_sr: '90° Elbow (Short Radius)',
	elbow_45: '45° Elbow',
	tee_through: 'Tee (Through Run)',
	tee_branch: 'Tee (Into Branch)',
	reducer_concentric: 'Concentric Reducer',
	reducer_eccentric: 'Eccentric Reducer',
	expander_concentric: 'Concentric Expander',
	expander_eccentric: 'Eccentric Expander',
	gate_valve: 'Gate Valve',
	ball_valve: 'Ball Valve',
	butterfly_valve: 'Butterfly Valve',
	globe_valve: 'Globe Valve',
	check_valve_swing: 'Check Valve (Swing)',
	check_valve_lift: 'Check Valve (Lift)',
	entrance_sharp: 'Sharp Entrance',
	entrance_rounded: 'Rounded Entrance',
	entrance_projecting: 'Projecting Entrance',
	exit: 'Pipe Exit',
	strainer_basket: 'Basket Strainer',
	strainer_y: 'Y-Strainer',
	union: 'Union',
	coupling: 'Coupling'
};

/** Fitting categories for grouping in UI. */
export const FITTING_CATEGORIES: Record<string, FittingType[]> = {
	Elbows: ['elbow_90_lr', 'elbow_90_sr', 'elbow_45'],
	Tees: ['tee_through', 'tee_branch'],
	'Reducers/Expanders': [
		'reducer_concentric',
		'reducer_eccentric',
		'expander_concentric',
		'expander_eccentric'
	],
	Valves: [
		'gate_valve',
		'ball_valve',
		'butterfly_valve',
		'globe_valve',
		'check_valve_swing',
		'check_valve_lift'
	],
	'Entrances/Exits': ['entrance_sharp', 'entrance_rounded', 'entrance_projecting', 'exit'],
	Other: ['strainer_basket', 'strainer_y', 'union', 'coupling']
};

/** Definition of a pipe segment. */
export interface PipeDefinition {
	/** Pipe material. */
	material: PipeMaterial;
	/** Nominal pipe diameter in project units (typically inches). */
	nominal_diameter: number;
	/** Pipe schedule or class. Default: "40" */
	schedule: string;
	/** Pipe length in project units. */
	length: number;
	/** Override calculated roughness (absolute roughness in project units). */
	roughness_override?: number;
}

/** A fitting or valve in a piping segment. */
export interface Fitting {
	/** Type of fitting. */
	type: FittingType;
	/** Number of this fitting. Default: 1 */
	quantity: number;
	/** User-specified K-factor override. */
	k_factor_override?: number;
	/** Optional description or notes. */
	description?: string;
}

/** A piping segment consisting of a pipe and zero or more fittings. */
export interface PipingSegment {
	/** The pipe definition. */
	pipe: PipeDefinition;
	/** List of fittings in this segment. */
	fittings: Fitting[];
}

/** Create a default pipe definition. */
export function createDefaultPipeDefinition(): PipeDefinition {
	return {
		material: 'carbon_steel',
		nominal_diameter: 4,
		schedule: '40',
		length: 100
	};
}

/** Create a default fitting. */
export function createDefaultFitting(type: FittingType): Fitting {
	return {
		type,
		quantity: 1
	};
}

/** Create a default piping segment. */
export function createDefaultPipingSegment(): PipingSegment {
	return {
		pipe: createDefaultPipeDefinition(),
		fittings: []
	};
}
